# `deleteById`, `delete`, and `deleteAll`

Spring Data Elasticsearch provides repository methods for deleting documents by ID, by entity, or deleting all data within a repository's scope. These methods have similar names but different blast radii. Picking the wrong method can cause an application to delete far more documents than intended or confuse deleting documents with deleting an index.

This lesson explains how to use `deleteById`, `delete`, `deleteAll`, and related variants; how Spring Data resolves the target index and document to delete; what happens when an ID does not exist; the impact of refresh; and how to perform conditional deletes using `ElasticsearchOperations`.

## 1. What Scopes of Deletion Exist in Elasticsearch?

In Elasticsearch, distinguish at least three operations:

1. **Delete one document:** delete a document by `_id` within an index.
2. **Delete multiple documents:** delete a set of documents by a list of IDs or by a query.
3. **Delete an index:** delete the entire index along with its mappings, settings, and data.

CRUD repositories primarily operate on documents. For example, a repository's `deleteAll()` deletes documents within the index managed by that repository; it is not equivalent to Elasticsearch's delete-index API.

```text
ProductRepository
      |
      +-- deleteById(id) --------> Delete one document by _id
      |
      +-- delete(entity) --------> Delete document by the entity's ID
      |
      +-- deleteAll(entities) ---> Delete the passed entities
      |
      +-- deleteAll() -----------> Delete all documents in the target index

IndexOperations.delete() -------> Delete the entire index, mappings, and settings
```

## 2. Sample Repository

Suppose the application manages products using a `Product` entity:

```java
package com.example.catalog.domain;

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
    private String category;

    public Product() {
    }

    public Product(String id, String name, String category) {
        this.id = id;
        this.name = name;
        this.category = category;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
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
}
```

Repository:

```java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

`@Document(indexName = "products")` sets the entity's default index. `@Id` marks the property used as the document ID. The repository inherits standard CRUD methods from Spring Data.

## 3. `deleteById`: Deleting One Document by ID

`deleteById(ID id)` takes a document ID and requests deletion of the corresponding document in the index managed by the repository.

```java
productRepository.deleteById("p-100");
```

Conceptually, this corresponds to the Elasticsearch command:

```http
DELETE products/_doc/p-100
```

Spring Data reads the index from entity metadata or repository configuration and sends the delete operation to Elasticsearch. The application does not need to assemble REST URLs manually when using the repository abstraction.

### 3.1. No Need to Load the Entity Before Deleting

If the ID is already known, `deleteById` is the direct choice:

```java
public void removeProduct(String id) {
    productRepository.deleteById(id);
}
```

There is no need to call `findById` solely to fetch the entity before deleting it. Doing so adds an extra read request and opens a window where the document could change between the read and delete.

### 3.2. Non-Existent IDs

Under Spring Data's CRUD repository contract, `deleteById` does not require the document to exist; if the entity is not found, the operation is typically ignored silently. At the Elasticsearch layer, the delete response may report `not_found` instead of `deleted`.

Therefore, do not rely on `deleteById` not throwing an exception as proof that the document existed and was deleted. If an API must report explicitly whether a document was "deleted" or "not found," design an appropriate result-checking strategy.

Example pre-check:

```java
public boolean deleteIfExists(String id) {
    if (!productRepository.existsById(id)) {
        return false;
    }

    productRepository.deleteById(id);
    return true;
}
```

This snippet illustrates how to produce a simple boolean response, though the check and the delete are two separate requests. Under concurrent updates, the document could be deleted after `existsById` or modified before the delete finishes. If you need the exact outcome of a single delete command, use a lower-level API that returns a delete result and handle it according to your client version.

### 3.3. The ID Must Match the Index and Routing

An ID only identifies a document within an index. Two different indices can hold unrelated documents with the same `_id`.

If the application uses custom routing when writing documents, the delete operation must use the corresponding routing. The same ID with the wrong routing can prevent Elasticsearch from finding the document on the targeted shard. Ensure document creation, reads, and deletes all follow the same routing rule.

## 4. `delete(entity)`: Deleting by the Entity's ID

`delete(T entity)` takes a Java object and deletes the corresponding document based on the entity's identifier. Spring Data reads the value from the property annotated with `@Id` to identify which document to delete.

```java
Product product = productRepository.findById("p-100")
        .orElseThrow(() -> new IllegalArgumentException("Product not found"));

productRepository.delete(product);
```

Conceptually, the operation still deletes the document by `_id` in the `products` index. It does not compare all properties like `name` and `category` to match the object.

### 4.1. The Entity Must Have a Valid ID

Because Spring Data needs to know which document to delete, the passed entity must have a valid ID. For example:

```java
Product product = new Product("p-100", null, null);
productRepository.delete(product);
```

If your mapping and Spring Data version allow extracting the ID from an object containing only an ID, the other properties do not need to be loaded just to perform a delete. Still, in business code, prefer objects with clear provenance and avoid constructing sparse dummy entities if doing so misleads readers into thinking the entire entity is matched.

Do not pass an entity without an ID:

```java
Product product = new Product(null, "Keyboard", "accessories");
productRepository.delete(product);
```

An entity without an ID does not identify a target document. Depending on the version and mapping path, Spring Data may reject the operation for a null ID or fail to build a valid delete request.

### 4.2. `delete(entity)` Does Not Delete by Object Content

Suppose two documents have the same name but different IDs:

```json
{"_id": "p-100", "name": "Keyboard", "category": "accessories"}
{"_id": "p-200", "name": "Keyboard", "category": "accessories"}
```

Calling `delete` with the entity whose ID is `p-100` targets only document `p-100`. Document `p-200` remains.

If the goal is to delete every document with `category = accessories`, use a query-based delete rather than `delete(entity)`.

## 5. `deleteAll(Iterable)`: Deleting a Specified Set of Entities

The CRUD repository has an overload accepting a collection of entities:

```java
List<Product> products = List.of(
        new Product("p-100", "Keyboard", "accessories"),
        new Product("p-200", "Mouse", "accessories")
);

productRepository.deleteAll(products);
```

This method deletes the passed entities based on each entity's ID. It does not mean deleting every document in the index.

Ensure the list contains entities with valid IDs belonging to the index managed by the repository. For large datasets, consider request costs and bulk delete approaches suitable for your Spring Data Elasticsearch/client version.

## 6. `deleteAllById`: Deleting a Set of Documents by ID

Modern Spring Data versions include `deleteAllById(Iterable<? extends ID> ids)` in the CRUD repository hierarchy. When exposed by the repository interface in your project's version, this method deletes documents whose IDs are in the list:

```java
productRepository.deleteAllById(List.of("p-100", "p-200", "p-300"));
```

This is a good fit when the application has a list of IDs and does not need to load the entities. Check `ElasticsearchRepository` and its superinterfaces for your exact release train to confirm the method is available.

If your version does not yet provide `deleteAllById`, you can iterate and call `deleteById` or use a suitable bulk/delete API. For large numbers of IDs, avoid sending a separate request per ID when a bulk approach is available.

## 7. `deleteAll()`: Deleting All Documents Within Repository Scope

`deleteAll()` has the widest impact among the CRUD repository delete methods:

```java
productRepository.deleteAll();
```

In Spring Data Elasticsearch, this operation executes against the index managed by the repository and deletes the documents within that scope. The implementation is typically based on delete-by-query with a query matching all documents.

The conceptual Elasticsearch command is:

```http
POST products/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}
```

`deleteAll()` does not delete the index structure. The `products` index, mappings, settings, and aliases remain after the documents are deleted.

### 7.1. Be Careful When Multiple Entities Share One Index

Modern Elasticsearch does not use document types to isolate entities the way very old Elasticsearch versions did. If multiple entity classes point to the same index, `deleteAll()` can delete every document in that index, including documents written by other entity classes.

Example:

```java
@Document(indexName = "catalog")
public class Product { ... }

@Document(indexName = "catalog")
public class Category { ... }
```

If `ProductRepository` calls `deleteAll()` on the `catalog` index, do not assume it only deletes documents created from the `Product` class. A full-index delete query does not automatically filter by Java class.

Therefore, only use `deleteAll()` when you are certain all data in the target index is meant to be deleted. If an index is shared, use an explicit conditional query or separate indices along data boundaries.

### 7.2. `deleteAll()` Differs from `IndexOperations.delete()`

The two methods have completely different scopes:

| Method | Impact | Index still exists? |
|---|---|---:|
| `repository.deleteAll()` | Deletes documents within the repository's index scope | Yes |
| `repository.deleteAll(entities)` | Deletes documents with IDs in the iterable | Yes |
| `indexOperations.delete()` | Deletes the index along with its data, mappings, and settings | No |

Example deleting an index with `IndexOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexAdminService {

    private final ElasticsearchOperations operations;

    public ProductIndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean deleteProductsIndex() {
        IndexOperations indexOperations = operations.indexOps(
                IndexCoordinates.of("products"));
        return indexOperations.delete();
    }
}
```

This is an index administration operation; it must be access-controlled and should not be exposed behind a routine CRUD endpoint. Once an index is deleted, the application must recreate the index/mappings before writing data again.

## 8. Comparing Delete Methods

| Method | Input | Deletion scope | Requires loading entity? |
|---|---|---|---:|
| `deleteById(id)` | One ID | One document | No |
| `delete(entity)` | One entity with ID | One document by entity ID | Not necessarily |
| `deleteAll(entities)` | Iterable of entities | Documents by IDs in the iterable | Has object/ID |
| `deleteAllById(ids)` | Iterable of IDs | Documents by IDs in the iterable | No |
| `deleteAll()` | None | All documents in target index | No |
| `IndexOperations.delete()` | None | Entire index | No |

Choose the method based on the dataset to delete. If only the ID is known, use an ID-based method. If you already have the entity and want to delete that exact document, use `delete(entity)`. If you want to delete by business criteria, use a query-based delete. Use `deleteAll()` only when all documents in the index genuinely need to be removed.

## 9. Conditional Deletion with `ElasticsearchOperations`

CRUD repository methods are not flexible enough for every case. When you need to delete all documents matching a condition, you can use `ElasticsearchOperations.delete(Query, Class, IndexCoordinates)`.

Example deleting products in the `discontinued` category:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void deleteDiscontinuedProducts() {
        Criteria criteria = new Criteria("category").is("discontinued");
        CriteriaQuery query = new CriteriaQuery(criteria);

        operations.delete(
                query,
                Product.class,
                IndexCoordinates.of("products"));
    }
}
```

`CriteriaQuery` expresses the deletion filter, while `IndexCoordinates` specifies the target index. APIs and query builder types may vary across release trains; consult the Javadoc for your project's Spring Data Elasticsearch version.

Before executing a query-based delete, run the corresponding search query to inspect which documents will be affected. For large-scope operations, log the condition, target index, expected count, and requesting user/process.

### 9.1. Query-Based Deletion and the Delete By Query API

Delete By Query finds documents matching a query and deletes them. This differs from deleting a single document by ID. It can consume substantial resources on large result sets and is affected by refreshes, conflicts, or concurrent writes while the operation is running.

In the REST API, example deleting products with `INACTIVE` status:

```http
POST products/_delete_by_query
{
  "query": {
    "term": {
      "status": "INACTIVE"
    }
  }
}
```

Do not send `match_all` when the goal is only to delete a subset of data. Verify the query beforehand with `_search` to confirm its scope.

## 10. Deleting in Services and REST APIs

A service can wrap repository operations and define how the application responds:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public void deleteById(String id) {
        repository.deleteById(id);
    }

    public void delete(Product product) {
        repository.delete(product);
    }

    public void deleteAll() {
        repository.deleteAll();
    }
}
```

A controller can expose an endpoint to delete a single product:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        service.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
```

This example returns `204 No Content` after calling `deleteById` following idempotent endpoint semantics. If the API must return `404 Not Found` when the document does not exist, the service needs a check strategy or a delete result from a lower-level API. Calling `existsById` before deleting can encounter race conditions if data changes concurrently.

Do not expose `deleteAll()` as a routine CRUD endpoint. If bulk deletion functionality exists, enforce authentication, authorization, scope validation, quantity limits, and clear auditing.

## 11. Refresh and Visibility of Delete Results

Elasticsearch is a near-real-time search engine. A delete operation may be acknowledged before search results reflect the change until the shard refreshes.

This creates a distinction between:

- Outcome of the delete command: Elasticsearch has processed the delete request.
- Outcome of search: the document disappears from search results only after a refresh updates searcher visibility.

In tests, if you delete a document and immediately invoke `_search`, you may need to refresh the index before asserting:

```http
POST products/_refresh
```

Spring Data Elasticsearch provides `RefreshPolicy` to control refresh behavior for write/delete operations via entity or operations configuration, depending on the version. Common Elasticsearch options are:

| Refresh policy | General meaning |
|---|---|
| `NONE` | Requests no special refresh; search sees changes on the next scheduled refresh |
| `IMMEDIATE` | Requests an immediate refresh so changes quickly become visible to search |
| `WAIT_UNTIL` | Waits for the next scheduled refresh instead of proactively forcing an immediate refresh |

Example declaring a policy on an entity in supported Spring Data versions:

```java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

@Document(
    indexName = "products",
    refreshPolicy = RefreshPolicy.WAIT_UNTIL
)
public class Product {
    // Fields
}
```

Check the package and API of `RefreshPolicy` in your version. Do not set `IMMEDIATE` for all production operations solely for instant search visibility; frequent refreshes can degrade indexing performance. Choose a policy strictly according to business consistency requirements.

## 12. Bulk Deletes, Performance, and Limits

Deleting ID by ID can generate many requests if an application processes a large list:

```java
for (String id : ids) {
    productRepository.deleteById(id);
}
```

For large ID sets, consider `deleteAllById`, `deleteAll(entities)`, the Bulk API, or Delete By Query depending on data structure and version. These reduce round trips, though operations are not free: Elasticsearch must still process delete operations, update segment metadata, and perform merges when needed.

Points to consider:

- Split into reasonably sized batches rather than sending a massive list at once.
- Track deleted counts, conflicts, and per-item errors when using bulk operations.
- Avoid running multiple large delete-by-query tasks simultaneously on the same index.
- Define a clear policy for documents updated while delete-by-query is running.
- Do not refresh after every document unless specifically required by business logic.
- Grant the minimum delete privileges needed to the application account.

If the goal is purging an entire old index according to data lifecycle rules, deleting the index or using ILM/data stream lifecycle may be more appropriate than deleting individual documents. That is a data management decision, not merely swapping one repository method for another.

## 13. Access Control and Protecting Delete Operations

Elasticsearch separates document-deletion permissions from index-deletion permissions. An application account can be granted permission to delete documents on a specific index without permission to delete the index or administer the cluster.

In real applications:

- Grant `delete` or the privileges matching the delete APIs the application uses on the required indices.
- Grant `delete_index` only to index administration processes when strictly necessary.
- Separate runtime accounts from migration/administration accounts.
- Audit bulk deletions and deletions of sensitive data.
- Verify the target index/alias before running cleanup jobs.
- Do not allow users to pass arbitrary index names into delete APIs without validation.

If a repository targets an alias instead of a concrete index, understand which indices the alias resolves to and how deletes affect documents in those target indices.

## 14. Common Pitfalls

### Calling `delete(entity)` with a Null ID

Spring Data cannot identify which document to delete. Ensure the entity has an `@Id` value before calling the method.

### Assuming `delete(entity)` Matches on All Attributes

The method deletes the document by the entity's ID. To delete by field criteria, use query-based deletion via `ElasticsearchOperations` or the Delete By Query API.

### Calling `deleteAll()` When Only a Subset of Documents Should Be Deleted

`deleteAll()` spans every document in the target index. Use a conditional query or a list of IDs to restrict the scope.

### Confusing Document Deletion with Index Deletion

`repository.deleteAll()` keeps the index and mappings. `IndexOperations.delete()` deletes the entire index. Pick the operation that matches your intent.

### Search Still Returns Documents Immediately After Deletion

This can be due to Elasticsearch's refresh delay. Check the delete response and refresh policy, and refresh in tests when needed.

### Using the Wrong Routing

If a document was written with custom routing, the delete operation must use the matching routing. Check metadata/routing and repository or operations configuration.

### Missing Delete Permissions

Authorization errors can occur if a role lacks document delete or delete-by-query privileges. Grant the right privilege for the specific index; do not work around this by giving every application an admin account.

## 15. Testing Delete Operations

When testing against real Elasticsearch or Testcontainers, verify both documents and indices:

```java
@Test
void deleteByIdRemovesTheDocument() {
    Product product = new Product("p-100", "Keyboard", "accessories");
    productRepository.save(product);

    productRepository.deleteById("p-100");

    // Refresh or wait for the configured refresh policy before a search-based assertion.
    assertThat(productRepository.existsById("p-100")).isFalse();
}
```

This snippet illustrates the test flow; waiting for refresh and initializing Elasticsearch depend on your project's test setup. You can also test:

- `delete(entity)` deletes only the document with the entity's ID.
- `deleteAll(entities)` deletes only the passed IDs.
- `deleteAll()` deletes documents in the target index while the index itself remains.
- `IndexOperations.exists()` still returns `true` after `repository.deleteAll()`.
- Query-based deletion removes only documents matching the criteria.
- Behavior for non-existent IDs matches the contract expected by the application API.

Do not rely solely on mocked repositories if the goal is verifying that Elasticsearch actually deletes documents or that refresh behaves properly. Integration tests against real Elasticsearch uncover issues with mappings, index coordinates, routing, and permissions.

## 16. Process for Selecting and Executing Delete Operations

Before deleting, define the objective clearly:

1. If you know one ID, use `deleteById(id)`.
2. If you already have an entity and want to delete the document by its ID, use `delete(entity)`.
3. If you have a list of IDs, use `deleteAllById(ids)` when supported by your version.
4. If you have a list of entities, use `deleteAll(entities)`.
5. If you need to delete by condition, construct an explicit query and use `ElasticsearchOperations.delete(...)` or the Delete By Query API.
6. Use `deleteAll()` only when every document in the target index must be deleted.
7. Use `IndexOperations.delete()` only when the intent is to delete the entire index and its metadata.
8. Configure a refresh policy and result-verification approach aligned with consistency requirements.
9. Verify permissions, routing, aliases, and index scope before executing high-impact operations.

## 17. Summary

`deleteById` deletes a single document by ID; `delete(entity)` deletes the document using the ID extracted from the entity; `deleteAll(entities)` or `deleteAllById(ids)` deletes a specified set of documents. `deleteAll()` deletes all documents within the repository's managed index scope without deleting the index itself. To delete the entire index, use `IndexOperations.delete()` or the corresponding index-management API.

When choosing a delete operation, pay attention to the target index, ID, custom routing, refresh, and Elasticsearch permissions. In particular, never use `deleteAll()` on a shared index when you only intend to remove data for one entity class. For business conditions or large datasets, query-based deletes and bulk APIs offer better control. Understanding the exact scope of each method keeps CRUD operations safe and predictable in Spring Data Elasticsearch.
