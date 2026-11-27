# findById, findAllById, and Optional

In Spring Data Elasticsearch, `findById` and `findAllById` are two read operations based on the `_id` identifier. `findById` takes a single ID and returns `Optional<T>` to represent that the document may or may not exist. `findAllById` takes a collection of IDs and returns the found entities as `Iterable<T>`.

Both methods belong to Spring Data's repository abstraction, so you do not need to write Query DSL manually just to fetch documents by ID. `Optional` helps code clearly express a potentially absent result, while `findAllById` fits cases where you need to read multiple documents whose IDs are already known.

It is important to distinguish lookup by ID from searching by attribute. `findById("product-1001")` looks up the document with that matching `_id`. A method such as `findBySku("SKU-1001")` queries by a business field and typically goes through search. The two operations differ in semantics, performance, and data visibility timing.

## 1. Repository and ID Type

Suppose the application stores products in the `products` index. The entity uses `String` as its identifier:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    protected Product() {
    }

    public Product(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
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
}
```

Repository:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

The first generic parameter is the entity type (`Product`); the second parameter is the type of the property annotated with `@Id` (`String`). The repository inherits CRUD operations, including `findById` and `findAllById`.

If the entity uses `Long` as the `@Id` property type, the repository must declare `ElasticsearchRepository<Product, Long>`. Keep these two types consistent rather than picking generic types by guesswork.

## 2. `findById`: Finding One Document by `_id`

The common signature inherited from Spring Data `CrudRepository`:

```java
Optional<Product> findById(String id);
```

The method takes an ID and returns `Optional<Product>`:

- If the document exists, the Optional contains the mapped entity.
- If the document does not exist, the result is `Optional.empty()`.
- If a connection, authentication, mapping, or other system error occurs, the operation may throw an exception. Such errors are not converted into `Optional.empty()` by default.

Example:

```java
Optional<Product> result = productRepository.findById("product-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product does not exist");
}
```

This snippet is valid because it checks `isPresent()` before calling `get()`. However, in application code there are usually cleaner and safer ways to express this using `Optional` methods.

### 2.1 The ID Must Be the Document ID

Suppose a document has the metadata:

```json
{
  "_index": "products",
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001",
    "name": "Mechanical Keyboard"
  }
}
```

The call:

```java
productRepository.findById("product-1001");
```

looks up by `_id`. The call:

```java
productRepository.findById("SKU-1001");
```

only finds the document if the document's `_id` itself is `SKU-1001`. Spring Data does not automatically interpret that string as the `sku` field.

To search by SKU, you need a field-based query method or an explicit query:

```java
Optional<Product> findBySku(String sku);
```

This is a query on a business attribute, distinct from the inherited `findById` method.

### 2.2 `findById` and Document Visibility Timing

Elasticsearch provides a GET document-by-ID API with real-time semantics by default. This differs from `_search`, which uses searchers and only sees changes after a refresh.

Therefore, after writing a document, a lookup by ID can see the new document before a search query on `sku` or `name` sees it. This is normal Elasticsearch behavior.

If `findById` returns empty, check the ID, index/alias, and actual document. If a field query returns empty immediately after a write, check refresh visibility before concluding that the save operation failed.

## 3. `Optional<T>` Represents a Potentially Absent Result

`Optional<T>` is a Java container type used to represent a value that may or may not be present. With `findById`, Optional makes the API explicit that a valid ID does not guarantee the corresponding document still exists.

```java
Optional<Product> found = productRepository.findById(id);
```

Two primary states:

```java
Optional<Product> present = Optional.of(product);
Optional<Product> absent = Optional.empty();
```

A proper Optional does not hold `null`. If there is no result, it is `Optional.empty()`. If there is a result, it contains the entity.

### 3.1 `orElse`

`orElse(defaultValue)` returns the contained entity if the Optional has a value; otherwise, it returns the default value:

```java
Product product = productRepository.findById(id)
    .orElse(defaultProduct);
```

Use a default value only when business rules genuinely define a valid fallback. For product data, fabricating an empty `Product` when not found often masks ID bugs or missing-record states.

One detail to watch: the expression passed to `orElse(...)` is evaluated before the method is invoked. For example:

```java
Product product = productRepository.findById(id)
    .orElse(createDefaultProduct());
```

`createDefaultProduct()` is still called even when the Optional already holds a product. If creating the fallback is expensive or has side effects, this can be undesirable.

### 3.2 `orElseGet`

`orElseGet(Supplier)` invokes the supplier only when the Optional is empty:

```java
Product product = productRepository.findById(id)
    .orElseGet(() -> createDefaultProduct());
```

Difference:

| Usage | When is the fallback value created? |
|---|---|
| `orElse(createDefaultProduct())` | Always evaluated before calling `orElse` |
| `orElseGet(() -> createDefaultProduct())` | Created only when the Optional is empty |

Do not use a fallback to turn a "not found" case into a dummy entity if business logic needs to distinguish the two states clearly.

### 3.3 `orElseThrow`

If the document is required to exist in the business context, you can throw an exception when it is not found:

```java
Product product = productRepository.findById(id)
    .orElseThrow(() -> new ProductNotFoundException(id));
```

Example custom exception:

```java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
```

`orElseThrow` turns the Optional result into a guaranteed existing entity or terminates the flow with a clear exception. In modern Java, the no-arg `orElseThrow()` can also throw `NoSuchElementException`, though a domain-specific exception usually makes mapping to HTTP 404 in the web layer clearer.

### 3.4 `ifPresent` and `ifPresentOrElse`

When you only need to perform an action if a result exists:

```java
productRepository.findById(id)
    .ifPresent(product -> auditLog(product));
```

Java 9 and later include `ifPresentOrElse` to handle both cases:

```java
productRepository.findById(id)
    .ifPresentOrElse(
        product -> auditLog(product),
        () -> auditMissingProduct(id)
    );
```

Do not use callbacks just to shorten code if the branches are complex. When you need to return a value, `map`, `orElseThrow`, or a local variable is often easier to read.

### 3.5 `map` and `filter`

`map` transforms the value inside the Optional without manual empty checks:

```java
Optional<String> productName = productRepository.findById(id)
    .map(Product::getName);
```

If there is no Product, the result stays `Optional.empty()`. If present, the result contains the product name.

`filter` keeps the value if the predicate holds:

```java
Optional<Product> availableProduct = productRepository.findById(id)
    .filter(Product::isAvailable);
```

If the product does not exist or fails the condition, the resulting Optional is empty. Use `filter` when the business meaning is truly "no matching result"; if you need to distinguish missing from unavailable, handle those two states separately.

## 4. Using `findById` in a Service

Repositories should focus on data access. Services express business rules and decide whether a missing record is normal, requires a fallback, or should raise an error.

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequired(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public boolean exists(String id) {
        return repository.existsById(id);
    }
}
```

In a service, there is no need to check `isPresent()` and then call `get()` when `orElseThrow` can be used. This avoids separating the check from the access and makes the missing-document behavior explicit.

### 4.1 Mapping Not Found to HTTP 404

If the service is called from a REST controller, a domain exception can be mapped to 404:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    public ResponseEntity<Product> getById(@PathVariable String id) {
        return ResponseEntity.ok(service.getRequired(id));
    }
}
```

A `@ControllerAdvice` can catch `ProductNotFoundException` and return `404 Not Found`. Example:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleProductNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(exception.getMessage());
    }
}
```

This is one design option. If an API wants to return `404` directly when an Optional is empty, the controller can also convert the Optional into a `ResponseEntity` via the appropriate API. The key is keeping HTTP semantics consistent and not turning infrastructure failures into 404s.

## 5. `findAllById`: Reading Multiple Documents by ID

When you already have a collection of IDs and need the corresponding documents, use:

```java
Iterable<Product> findAllById(Iterable<String> ids);
```

Example:

```java
List<String> ids = List.of(
    "product-1001",
    "product-1002",
    "product-1003"
);

Iterable<Product> products = productRepository.findAllById(ids);
```

The method returns the entities found. The return type is `Iterable<Product>` per the repository contract; it is not `Optional<List<Product>>`.

### 5.1 Important Rules of `findAllById`

According to the Spring Data repository contract:

- Input IDs must be non-null, and the iterable itself must not be `null`.
- If some IDs do not exist, the corresponding entities simply do not appear in the result.
- The result may contain fewer entities than the number of input IDs.
- Element order in the result is not guaranteed to match the order of input IDs.
- Do not rely on returning duplicate elements if the input contains duplicate IDs.

Example input:

```java
List<String> ids = List.of(
    "product-1003",
    "missing-id",
    "product-1001"
);
```

If the first and last documents exist, the result contains only the two found Products. `missing-id` does not produce a `null` element or an empty Optional inside the iterable. Therefore, you cannot directly assume the first element of the result corresponds to the first input ID.

### 5.2 Converting Iterable to List

If the service layer needs a `List`, convert it explicitly:

```java
import java.util.ArrayList;
import java.util.List;

public List<Product> findProducts(List<String> ids) {
    List<Product> result = new ArrayList<>();
    productRepository.findAllById(ids).forEach(result::add);
    return result;
}
```

Or use a stream from the `Iterable`:

```java
import java.util.stream.StreamSupport;

List<Product> result = StreamSupport
    .stream(productRepository.findAllById(ids).spliterator(), false)
    .toList();
```

No conversion is needed if the caller only iterates over the `Iterable` once. Keeping the more general return type also avoids creating unnecessary collections.

### 5.3 Preserving the Order of the Input ID List

The `findAllById` contract does not guarantee result order. If an API needs to return products in the exact order requested by the client, map the results by ID and rebuild the list.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public List<Product> findInRequestedOrder(List<String> ids) {
    Map<String, Product> foundById = new HashMap<>();

    productRepository.findAllById(ids).forEach(product ->
        foundById.put(product.getId(), product)
    );

    List<Product> ordered = new ArrayList<>();
    for (String id : ids) {
        Product product = foundById.get(id);
        if (product != null) {
            ordered.add(product);
        }
    }

    return ordered;
}
```

This snippet preserves the order of found IDs. If the input contains the same ID multiple times, the result list may also repeat the corresponding entity because the loop iterates over the input. If the API should not return duplicates, deduplicate the IDs before calling the repository or while assembling the result.

### 5.4 Detecting Missing IDs

If business logic needs to know which IDs do not exist, compare the requested list against the found entities:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public Set<String> findMissingIds(List<String> ids) {
    Map<String, Product> foundById = new HashMap<>();

    productRepository.findAllById(ids).forEach(product ->
        foundById.put(product.getId(), product)
    );

    Set<String> missing = new HashSet<>(ids);
    missing.removeAll(foundById.keySet());
    return missing;
}
```

`Set` works well when you only need the set of missing IDs without preserving order. If the API needs input order, use `LinkedHashSet` or build the list according to the input. Validate for nulls before calling the repository; `List.of(...)` and `List.copyOf(...)` automatically reject null elements.

## 6. `findAllById` Is Not `findAll`

The two methods serve different purposes:

| Method | Meaning | When to use |
|---|---|---|
| `findById(id)` | Fetch one document by `_id` | The ID of the document to read is known |
| `findAllById(ids)` | Fetch documents by a list of `_id`s | A collection of IDs to read is already known |
| `findAll()` | Fetch documents within the repository/index scope using the appropriate pagination API | Need to iterate over data by page or sort |
| `findBySku(sku)` | Search by business field `sku` | Only SKU is known, not `_id` |

Do not call `findAll()` and filter in Java just to retrieve a few known IDs. That loads many unnecessary documents and wastes memory, network bandwidth, and search resources.

Likewise, do not use `findAllById` when the real requirement is searching by criteria such as category, status, or price range. In those cases, use field queries, derived queries, or Query DSL.

## 7. Complete Service Example

A service can expose both single-ID and multi-ID read operations:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final ProductRepository repository;

    public ProductLookupService(ProductRepository repository) {
        this.repository = repository;
    }

    public Optional<Product> findOptional(String id) {
        return repository.findById(id);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
    }

    public List<Product> findMany(Iterable<String> ids) {
        List<Product> products = new ArrayList<>();
        repository.findAllById(ids).forEach(products::add);
        return products;
    }
}
```

The service keeps two clear policies:

- `findOptional` lets the caller decide how to handle a missing document.
- `getRequired` treats a missing document as a business error and throws a clear exception.
- `findMany` returns the found documents; callers must follow the contract that missing IDs have no corresponding elements.

Avoid creating a single method that always returns `null` when not found. `Optional` or an exception communicates intent much more clearly.

## 8. Reading Many IDs in Large Batches

`findAllById` is convenient for a reasonably sized set of IDs. However, if the input contains tens or hundreds of thousands of IDs, a single large call can create oversized requests/responses, increase memory pressure, and raise latency.

For large batches, split into suitably sized chunks:

```java
import java.util.ArrayList;
import java.util.List;

public List<Product> findInBatches(List<String> ids, int batchSize) {
    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    List<Product> all = new ArrayList<>();

    for (int start = 0; start < ids.size(); start += batchSize) {
        int end = Math.min(start + batchSize, ids.size());
        List<String> batch = ids.subList(start, end);
        productRepository.findAllById(batch).forEach(all::add);
    }

    return all;
}
```

`batchSize` has no universal optimal value. Measure document size, ID count, response bytes, latency, and cluster load. When splitting into batches, the order of results within each batch is still not guaranteed to match the ID order in that batch; if global ordering is needed, rebuild it from the input as shown earlier.

In common versions of Spring Data Elasticsearch, multi-ID lookups may be implemented via multi-get rather than running a search query. However, rely on the repository contract and version-specific documentation rather than depending on unguaranteed internal implementation details.

## 9. Common Pitfalls

### 9.1 Calling `get()` When the Optional Can Be Empty

```java
Product product = repository.findById(id).get();
```

If no document exists, the code throws `NoSuchElementException`. Use `orElseThrow` with a meaningful business exception or handle the Optional explicitly.

### 9.2 Using `orElse(null)` and Passing Null Around

```java
Product product = repository.findById(id).orElse(null);
```

This defeats the benefit of Optional and pushes null-handling risks to subsequent lines. If the caller genuinely accepts an absent result, keep the `Optional<Product>` return type across the service API. If a result is mandatory, use `orElseThrow`.

### 9.3 Confusing SKU with `_id`

`findById("SKU-1001")` does not search the `sku` field. Use a query method `findBySku` or a query against the mapped field.

### 9.4 Assuming `findAllById` Preserves Input Order

The contract does not guarantee order. If order matters, map results by ID and reconstruct the list according to the input.

### 9.5 Assuming Missing IDs Produce Nulls in the Result

Missing IDs are omitted; the returned iterable can be shorter than the input. If you need to know which IDs are missing, compare the requested ID set with the IDs of the found entities.

### 9.6 Treating Connection Errors as Missing Documents

`Optional.empty()` indicates that no matching document exists. Connection errors, authentication failures, timeouts, or mapping errors are normally represented by exceptions. Do not catch all exceptions and return empty, as that misrepresents infrastructure failures as missing data.

### 9.7 Calling `findAllById` with Null Input

Do not pass a null iterable or null ID elements. Validate inputs at the service/API layer and return an appropriate input error before calling the repository.

### 9.8 Using findAll to Fetch a Few Documents

If you already have the IDs, use `findAllById`. Reading the entire index and filtering in Java is wasteful and can hit pagination limits.

## 10. Checklist When a Document Is Not Found

When `findById` returns empty, verify:

1. Does the passed ID match the exact value used when writing?
2. Is `@Id` placed on the right property of the entity?
3. Does `ElasticsearchRepository<Product, ID>` declare the right ID type?
4. Does `@Document(indexName = ...)` point to the right index or alias?
5. Which physical index is the alias pointing to?
6. Does the document exist in the index via a direct GET API call?
7. Is the application connecting to the right cluster/environment?

Direct check examples:

```http
GET /products/_doc/product-1001
GET /_alias/products
GET /_cat/indices/products*?v
```

If the direct GET API finds the document while the repository does not, focus on checking index name, ID type, mapping metadata, and repository configuration. If the GET API also does not find it, check the write operation, actual ID, and target index.

For `findAllById`, log the requested ID set and compare it against the IDs in the result. Never assume the result count always equals the input element count.

## 11. Usage Principles

- Use `findById` when `_id` is known and you need to retrieve one document.
- Keep the `Optional<T>` result until the business layer decides how to handle absence.
- Use `orElseThrow` when the document must exist; use `orElseGet` when a well-defined fallback exists.
- Use `findAllById` when you already have a set of IDs to read.
- Remember that `findAllById` returns an `Iterable`, may omit missing entities, and does not guarantee input order.
- If order matters, rebuild the result using the original ID list.
- If you need to know which IDs are missing, compare the input ID set against the found IDs.
- For large batches, split requests according to measured sizes and monitor memory/latency.
- Use field queries when only SKU, category, or other business attributes are known.
- Distinguish missing documents from connection errors, timeouts, and mapping errors.

## 12. Summary

`findById` reads a single document by `_id` and returns `Optional<T>`, clearly representing whether the entity is present or absent. `Optional` provides operations such as `orElse`, `orElseGet`, `orElseThrow`, `ifPresent`, `map`, and `filter` to handle results without relying on null. When a document must exist, `orElseThrow` with a domain exception is usually the clearest expression.

`findAllById` takes an iterable of IDs and returns the found entities as `Iterable<T>`. Non-existent IDs are skipped, the result may have fewer items than the input, and ordering is not guaranteed. If you need to preserve order or report missing IDs, correlate results by ID instead of relying on element position.

Finally, keep in mind that these two methods retrieve by document identifier. They differ from searching by business fields like SKU or product name. Using the right abstraction keeps CRUD code readable, makes missing-document handling explicit, and avoids loading unnecessary data.
