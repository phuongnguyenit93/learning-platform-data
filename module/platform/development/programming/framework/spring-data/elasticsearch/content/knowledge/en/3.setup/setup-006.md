# Saving, Reading, Searching, and Deleting Documents

Spring Data Elasticsearch enables Spring applications to work with Elasticsearch using Java objects. Instead of manually crafting HTTP requests for every operation, you declare a document class, a repository, or use **ElasticsearchOperations** to save, read, search, and delete data.

In this lesson, we build an example managing product documents in the **products** index. Each document has an identifier, name, category, price, and creation timestamp. Operations are presented in the typical workflow: connecting to Elasticsearch, mapping a Java class, writing data, querying, and deleting data.

## 1. Preparing the Elasticsearch Connection

The application requires a running Elasticsearch instance and a Spring Data Elasticsearch dependency compatible with your Spring Boot version. For a Spring Boot project, you can add the following starter in Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-elasticsearch</artifactId>
</dependency>
~~~

Let Spring Boot manage dependency versions through the project's dependency management. Avoid pairing an incompatible Spring Data Elasticsearch version with an incompatible Elasticsearch Java Client version.

Configure the server address in **application.yml**:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

If Elasticsearch requires authentication, configure credentials using a secret management mechanism appropriate for your deployment environment:

~~~yaml
spring:
  elasticsearch:
    uris: https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Do not commit real passwords to Git. In environments with TLS, configure certificates and authentication according to the Elasticsearch cluster's requirements. Exact property names and configuration details can vary across Spring Boot generations; follow the documentation for your project's version.

When the application starts, Spring Boot creates the connection components needed by Spring Data Elasticsearch. In most applications, you simply inject a repository or **ElasticsearchOperations** without manually creating an HTTP client for each request.

## 2. Declaring the Document Class and Field Mappings

Elasticsearch stores data as JSON documents inside an index. Spring Data Elasticsearch maps those documents to a Java class using annotations in the **org.springframework.data.elasticsearch.annotations** package.

Example **Product** class:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.DateFormat;
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
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date, format = DateFormat.date_optional_time)
    private Instant createdAt;

    public Product() {
    }

    public Product(String id, String name, String category,
                   Double price, Instant createdAt) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.createdAt = createdAt;
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

    public Double getPrice() {
        return price;
    }

    public void setPrice(Double price) {
        this.price = price;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

The main annotations mean:

- **@Document(indexName = "products")** specifies the index storing documents of this class.
- **@Id** marks the field used as the Elasticsearch document **_id**.
- **@Field(type = FieldType.Text)** declares a text field analyzed into tokens, suitable for full-text search.
- **@Field(type = FieldType.Keyword)** declares a field stored as an unanalyzed value, suitable for exact filtering, grouping, and sorting.
- **@Field(type = FieldType.Double)** maps a floating-point numeric field.
- **@Field(type = FieldType.Date, ...)** declares a date-time field.

Choose data types based on query patterns. For example, product names are typically **Text** because users search by partial content; product codes, statuses, and categories are typically **Keyword** because exact matching is needed. If you need both full-text search and exact filtering on the same content, you can declare a multi-field with a **text** field and a **keyword** subfield.

**Double** is convenient for examples, but not the best default choice for all monetary data. For values requiring decimal precision, consider storing the smallest unit as an integer or designing a **scaled_float** mapping with an appropriate scaling factor.

### Creating the Index and Mapping

An index must exist before writing documents. Depending on configuration, Spring Data Elasticsearch can create the index from **@Document** metadata. In applications needing explicit mapping control, you can proactively create the index and mapping using **IndexOperations**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.create();
            indexOperations.putMapping();
        }
    }
}
~~~

The snippet above illustrates the sequence of operations: check whether the index exists, create the index, and apply the mapping derived from the document class. Initialization logic can be placed in a startup component, such as a bean implementing **ApplicationRunner**.

In production environments, mappings should be designed and managed deliberately. Changing annotations in Java code does not automatically convert existing data to the new mapping. When changing a field type or analyzer, you typically need to create a new index with the right mapping, migrate data to the new index, and then switch an alias or application config to it.

## 3. Creating a Repository for Data Operations

Spring Data Elasticsearch provides **ElasticsearchRepository**, allowing you to use built-in CRUD methods and declare queries based on method names.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndPriceBetween(
            String category,
            Double minPrice,
            Double maxPrice);
}
~~~

The first type parameter is the **Product** document class; the second type parameter is the type of the identifier field, here **String**.

Extending **ElasticsearchRepository** provides common operations out of the box:

| Method | Purpose |
|---|---|
| **save(entity)** | Saves a document; if a document with the same ID already exists, overwrites that document |
| **saveAll(entities)** | Saves a collection of documents |
| **findById(id)** | Reads a document by ID, returning an **Optional** |
| **findAll()** | Reads documents |
| **existsById(id)** | Checks whether an ID exists |
| **count()** | Counts documents |
| **deleteById(id)** | Deletes a document by ID |
| **delete(entity)** | Deletes the document corresponding to the entity |
| **deleteAll()** | Deletes all documents managed by the repository |

Declared methods like **findByCategory** and **findByCategoryAndPriceBetween** have their names parsed by Spring Data to generate queries. Property names must match properties of the document class. Operators such as **And**, **Or**, **Between**, **LessThan**, **GreaterThan**, **In**, and **Containing** can express conditions, depending on support in your Spring Data Elasticsearch version.

## 4. Saving New Documents

To save a product, create a Java object and pass it to **save**:

~~~java
import java.time.Instant;
import java.util.UUID;

Product product = new Product(
        UUID.randomUUID().toString(),
        "Mechanical Keyboard",
        "accessories",
        89.50,
        Instant.now()
);

Product savedProduct = productRepository.save(product);
~~~

Spring Data converts the object into a JSON document and sends a write operation to the index declared in **@Document**. The corresponding document looks roughly like:

~~~json
{
  "id": "a-generated-id",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5,
  "createdAt": "2026-11-13T12:00:00Z"
}
~~~

The ID value in the JSON example is illustrative. When the application generates IDs itself, ensure uniqueness within the index. If you do not assign an ID, Elasticsearch can generate one using its own mechanism, though managing and updating documents is usually easier to control when the application uses stable IDs.

**save** writes a document by ID. If the ID does not exist yet, a new document is created; if the ID already exists, the document's content is rewritten with the passed object's data. Therefore, when updating a document, load the existing data first if you need to preserve other fields.

## 5. Reading Documents

### Reading by ID

The **findById** method returns **Optional<Product>** because the document might not exist:

~~~java
Optional<Product> result = productRepository.findById(productId);

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product not found");
}
~~~

You can write this more concisely using **orElse**, **orElseGet**, or **orElseThrow** depending on how missing items are handled:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Product not found: " + productId));
~~~

### Reading Multiple Documents

**findAll()** returns documents in the corresponding index:

~~~java
Iterable<Product> products = productRepository.findAll();

for (Product product : products) {
    System.out.println(product.getName());
}
~~~

Do not call **findAll()** to load an entire large index into memory. When data volume is large, use pagination or a query that bounds results.

### Reading with Pagination and Sorting

Repositories support queries accepting **Pageable**. For example, add the following method to **ProductRepository**:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Product> findByCategory(String category, Pageable pageable);
~~~

Call the method for the first page of 20 items, sorted by ascending price:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
        productRepository.findByCategory("accessories", pageRequest);

List<Product> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Page numbers are zero-based (**0**). Page-number pagination fits moderate lists. For very large result sets or stable deep traversal across many pages, consider **search_after** with a deterministic tie-breaker sort field.

## 6. Searching Documents

Searching in Elasticsearch depends on the field's mapping type and the query type. Distinguish full-text search from exact matching:

- **match** is typically used for **text** fields; query text is processed through the analyzer.
- **term** matches an exact value, typically applied to **keyword** fields, identifiers, or status values.
- **range** filters by numeric or date-time intervals.
- **bool** combines multiple conditions using **must**, **should**, **filter**, and **must_not**.

### Searching with Repository Method Names

Example using the two methods declared in **ProductRepository**:

~~~java
List<Product> accessories =
        productRepository.findByCategory("accessories");

List<Product> affordableAccessories =
        productRepository.findByCategoryAndPriceBetween(
                "accessories", 20.0, 100.0);
~~~

The second query combines category and price range conditions. It works well when search criteria are relatively fixed and can be clearly expressed via method names.

### Searching with @Query

When you need to write Elasticsearch Query DSL directly, you can use the **@Query** annotation:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<Product> searchByName(String text);
}
~~~

The JSON string in the annotation is the Query DSL query clause; **?0** is replaced with the first method parameter. The **match** query suits the **name** field mapped as **text**. Maintain valid JSON syntax and exact field names from the mapping.

### Flexible Search with ElasticsearchOperations

When queries have many conditions or are built dynamically from user parameters, **ElasticsearchOperations** lets you construct queries in Java code. The following example uses Spring Data Elasticsearch 5.x's **NativeQuery** API with the Elasticsearch Java API Client:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<Product> searchByName(String text) {
        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.match(m -> m
                        .field("name")
                        .query(text)))
                .withPageable(PageRequest.of(0, 10))
                .build();

        SearchHits<Product> hits =
                operations.search(query, Product.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .collect(Collectors.toList());
    }
}
~~~

In this example:

1. **NativeQuery.builder()** creates the query builder.
2. **withQuery(...)** declares a **match** query on the **name** field.
3. **withPageable(...)** limits results to the first 10 documents.
4. **operations.search(query, Product.class)** executes the query and maps results to **Product**.
5. **SearchHits** contains **SearchHit** entries; each hit holds the document content plus metadata such as ID, relevance score, and highlight info if requested.

You can expand the query by combining **bool** conditions, category filters, price ranges, or sorting. For instance, the category field should use an exact condition on its **keyword** mapping, while the product name should use **match** on its **text** mapping.

Note: **NativeQuery** in the example belongs to the Spring Data Elasticsearch 5.x API. Projects using older versions may use different query APIs. Check the packages and documentation for your exact version rather than copying code verbatim across library generations.

## 7. Updating Documents

The most straightforward way to update a document is to read it by ID, modify the necessary properties, and call **save**:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Product not found: " + productId));

product.setPrice(79.90);
productRepository.save(product);
~~~

Because **save** rewrites the document by ID, the submitted object must contain all fields the application intends to keep. If you instantiate a new object with only the ID and one changed field and call **save**, fields absent from that object may be lost from the stored document.

If you only want to update a few fields without reading the entire document, you can use **ElasticsearchOperations**'s update API with **UpdateQuery**. How **Document**, **UpdateQuery**, and **IndexCoordinates** are constructed depends on the Spring Data Elasticsearch version. Only use partial updates once you have clearly verified behavior regarding missing fields, null fields, and nonexistent documents.

## 8. Deleting Documents

### Deleting by ID

Use **deleteById** when the document ID is known:

~~~java
productRepository.deleteById(productId);
~~~

You can check beforehand if business logic needs to distinguish the non-existent case:

~~~java
if (productRepository.existsById(productId)) {
    productRepository.deleteById(productId);
}
~~~

Checking beforehand adds an extra query, and the document could still change between the two operations. If no special handling is needed when absent, calling **deleteById** directly is usually simpler.

### Deleting an Object or a Set of IDs

~~~java
productRepository.delete(product);
productRepository.deleteAllById(productIds);
~~~

**delete(entity)** deletes the document matching the object's identifier. **deleteAllById** deletes documents whose IDs are in the provided collection.

### Deleting All Documents

~~~java
productRepository.deleteAll();
~~~

**deleteAll()** has a broad impact because it deletes all documents belonging to the repository. Only invoke it when business logic truly requires emptying the dataset, such as in test environments or controlled administrative tasks. Never place this call in a normal user request flow.

If conditional deletion is needed, build a delete-by-query operation using the API supported by your Spring Data Elasticsearch version. Verify conditions carefully before execution because the operation can delete many documents at once.

## 9. Grouping Operations into a Service

In Spring applications, controllers typically call services; services enforce business rules and use repositories. Example simple service:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        if (product.getId() == null || product.getId().isBlank()) {
            product.setId(UUID.randomUUID().toString());
        }
        return repository.save(product);
    }

    public Optional<Product> getById(String id) {
        return repository.findById(id);
    }

    public List<Product> getAll() {
        List<Product> result = new ArrayList<>();
        repository.findAll().forEach(result::add);
        return result;
    }

    public Product updatePrice(String id, Double newPrice) {
        Product product = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + id));

        product.setPrice(newPrice);
        return repository.save(product);
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

This service illustrates responsibility organization; real applications need input validation, valid pricing rules, exception handling, and API-appropriate error responses. If IDs are generated in another layer or follow custom naming rules, apply those rules instead of the UUID in the example.

## 10. Understanding Consistency Between Writing and Searching

Elasticsearch is a near real-time search system. After writing or deleting a document, changes may not appear immediately in search results because the index must be refreshed. Consequently, a successful **save** does not mean every subsequent search query will instantly see that document.

When testing, avoid assuming that writing guarantees immediate visibility via full-text search. If a test needs immediate read-back via search, use a refresh mechanism appropriate for your version and configuration. Avoid forcing refreshes after every write in high-load environments as it can hurt performance.

Also distinguish:

- Reading by ID checks the document directly by identifier.
- Full-text search runs against the inverted index and is affected by analyzers.
- **keyword** queries match exact values, making them suitable for exact filters.
- Search results may be ranked by relevance score, not necessarily in document insertion order.

## 11. Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cannot connect to Elasticsearch | Wrong URI, server not running, network or TLS error | Check address, port, connection logs, and certificates |
| Authentication error | Missing or invalid credentials | Check environment configuration and account privileges |
| Index does not exist | Index not created or wrong index name | Check **@Document** and index initialization process |
| Mapping error on write | Java value incompatible with declared field type | Compare data types, actual mapping, and payload |
| Search does not return expected results | Wrong query type or analyzer | Check **text**/**keyword** mapping and pick appropriate **match**/**term** |
| Newly written data not yet visible in search | Elasticsearch has not refreshed the index yet | Check refresh timing and testing approach |
| Update loses other fields | Rewriting document with a partially populated object | Read existing document before modifying and calling **save**, or use partial update |

When errors occur, inspect both application exceptions and Elasticsearch responses. Details such as index name, field name, data type, connection state, and query body usually pinpoint the root cause faster.

## 12. Complete Operational Workflow

A typical document processing flow can be implemented in the following order:

1. Start Elasticsearch and configure URIs, authentication, and TLS if needed.
2. Declare the document class with **@Document**, **@Id**, and mappings for each field.
3. Create the index and mapping before writing data if the application needs to control initialization.
4. Declare a repository extending **ElasticsearchRepository**.
5. Use **save** or **saveAll** to write documents.
6. Use **findById** to read by ID; use repository queries or **ElasticsearchOperations** to search.
7. Read the existing document, update properties, and save again; use partial update APIs when appropriate.
8. Use **deleteById**, **delete**, or delete-by-query to remove data within the right scope.

For basic CRUD operations, repositories keep code concise and readable. When you need dynamic queries, result metadata, complex conditions, or control over index operations, **ElasticsearchOperations** provides finer control. Both approaches can coexist in a single application: repositories handle common operations while operations handle specialized queries.
