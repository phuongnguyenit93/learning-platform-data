# Separating DocumentOperations, SearchOperations, and IndexOperations

Spring Data Elasticsearch provides several abstractions for Java applications to work with Elasticsearch. Three common abstractions are DocumentOperations, SearchOperations, and IndexOperations. They all relate to data in an index, but serve three distinct groups of tasks:

- **DocumentOperations:** create, read, update, and delete documents; supports batch write operations.
- **SearchOperations:** build and execute search queries, count results, paginate, and retrieve search hit metadata.
- **IndexOperations:** manage the index itself, such as creating/deleting indices, reading or updating mappings, settings, aliases, and refreshing.

ElasticsearchOperations is the unified facade for an application to use document and search operations, while also providing a way to obtain IndexOperations for a specific index. Understanding these boundaries helps place logic in the right layer: saving an entity is not creating an index, searching for documents is not reading a mapping, and managing an index is not processing individual documents.

## 1. Overview of the Abstractions

The relationships between components can be visualized as follows:

~~~text
                 ElasticsearchOperations
                   /                 \
                  /                   \
       DocumentOperations          SearchOperations
       - save / get                - search
       - exists / delete            - count
       - bulk write                 - paging / scroll
                  \                   /
                   \                 /
                    ElasticsearchTemplate
                            |
                            | indexOps(...)
                            v
                     IndexOperations
                     - create / delete
                     - mapping / settings
                     - aliases / refresh
~~~

The diagram illustrates the separation of responsibilities at the API level. DocumentOperations and SearchOperations are groups of operations exposed through ElasticsearchOperations. IndexOperations is a separate abstraction obtained from ElasticsearchOperations via indexOps(...), because it works with the metadata and lifecycle of an index.

Specific interfaces and some method signatures may vary across Spring Data Elasticsearch release trains. When applying them, consult the Javadoc for the version in use. The separation of responsibilities remains the basis for choosing the right API.

## 2. ElasticsearchOperations as the Unified Entry Point

In an application, you can inject ElasticsearchOperations to use high-level operations without having to manually create and manage an Elasticsearch Java Client in every service.

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

ElasticsearchOperations works with Spring Data's entity metadata, so operations by entity type can use information from @Document, @Id, and @Field. It also allows specifying IndexCoordinates when an operation needs to target a specific index.

This facade is suitable when a service needs to coordinate saving documents, searching, and performing index operations within the same business flow. If a service only needs to search, it can depend on a narrower abstraction if the version and application configuration allow injecting the corresponding implementation; however, in many applications, ElasticsearchOperations is the common and convenient entry point.

## 3. DocumentOperations: Operations on Individual Documents

DocumentOperations focuses on indexed documents. Common operations include:

| Operation | Purpose |
|---|---|
| save | Create or overwrite a document by ID |
| get | Retrieve a document by ID |
| exists | Check whether a document exists by ID |
| delete | Delete a document by ID |
| bulk operations | Write or update multiple documents in one batch |

This is the right abstraction for flows that synchronize a single entity or perform CRUD by ID. It is not responsible for creating index templates, setting shard counts, or managing retention.

### 3.1. Saving a Document

Example entity:

~~~java
import java.math.BigDecimal;

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

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

A service can save the entity:

~~~java
public Product save(Product product) {
    return operations.save(product);
}
~~~

Spring Data uses Product's metadata to determine the target index and convert the entity into a document. The @Id property is used as the Elasticsearch document ID. The default index name comes from the @Document metadata, unless another IndexCoordinates is passed to the operation.

### 3.2. Saving to a Specified Index

If the same entity type needs to be written to a specific index, pass IndexCoordinates:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public Product saveToArchive(Product product) {
    return operations.save(
            product,
            IndexCoordinates.of("products-archive")
    );
}
~~~

IndexCoordinates is an object describing the target index or name that the operation will use. It is useful for versioned indices, aliases, or cases where an entity is stored across multiple indices. Index selection rules should be managed centrally to prevent different services from choosing inconsistent names.

### 3.3. Reading a Document by ID

~~~java
public Product findById(String id) {
    return operations.get(id, Product.class);
}
~~~

If you need to specify an index:

~~~java
public Product findInArchive(String id) {
    return operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products-archive")
    );
}
~~~

The get method reads a document by ID. It is appropriate when the document ID is already known and you do not need to run a conditional search query.

### 3.4. Checking Existence and Deleting Documents

~~~java
public boolean exists(String id) {
    return operations.exists(id, Product.class);
}

public String delete(String id) {
    return operations.delete(id, Product.class);
}
~~~

Exact overloads may differ between versions. Choose the overload appropriate for the entity type or IndexCoordinates. If custom routing is used, read, update, or delete operations must also pass routing consistently according to the metadata and corresponding API.

### 3.5. Batch Writing

When ingesting many documents, bulk operations are generally more efficient than calling save for each document sequentially. Spring Data Elasticsearch provides bulk APIs via operations; how IndexQuery, UpdateQuery, or specific bulk objects are created depends on the version.

Conceptual example:

~~~java
public void saveAll(List<Product> products) {
    operations.save(products);
}
~~~

For large lists, split into appropriately sized batches and inspect item-level results if the bulk API returns per-document errors. A bulk request can be partially processed; do not treat an HTTP request success as proof that every document was written.

## 4. SearchOperations: Searching Documents by Criteria

SearchOperations focuses on querying an index. It is suitable when an application needs to search across multiple fields, combine conditions, rank results, paginate, or obtain information about each search hit.

Common capabilities:

- Executing search queries.
- Counting documents matching criteria.
- Pagination and sorting.
- Querying via Criteria or native queries.
- Receiving SearchHits containing entity content along with scores and metadata.
- Using scroll or large-result traversal mechanisms when appropriate for the version.

SearchOperations does not replace DocumentOperations. A search query returns a list of hits; a get by ID is an operation that locates a specific document.

### 4.1. Creating Queries with Criteria

Example finding products in the electronics category with a price greater than 100:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public SearchHits<Product> searchExpensiveElectronics() {
    Criteria criteria = new Criteria("category").is("electronics")
            .and("price").greaterThan(100);

    Query query = new CriteriaQuery(criteria);

    return operations.search(query, Product.class);
}
~~~

CriteriaQuery helps express query conditions in Java. It is suitable for simple or moderate filters. For complex search logic, multiple bool branches, scoring, or specialized Elasticsearch syntax, native queries can be easier to control.

### 4.2. Specifying an Index for Search

~~~java
public SearchHits<Product> searchArchive(Query query) {
    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-archive")
    );
}
~~~

Passing IndexCoordinates lets you query a specific index or alias. If an alias points to multiple indices, Elasticsearch searches across the indices covered by the alias. Verify that mappings across those indices are compatible with the fields in the query.

### 4.3. SearchHits and SearchHit

SearchOperations typically returns SearchHits<T> when complete search result information needs to be preserved. Each SearchHit<T> can provide:

- Content converted into a Java entity.
- Document ID.
- Relevance score for the query.
- Index name and routing if present.
- Highlight fields or other search metadata depending on the query and version.

Example:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    System.out.println(product.getId());
    System.out.println(product.getName());
    System.out.println(hit.getScore());
}
~~~

If you only need entity content, you can convert SearchHits into a list of contents using the appropriate utility API. If the UI needs to display relevance, highlights, or pagination information, keep SearchHits so metadata is not lost.

### 4.4. Count and Pagination

When you only need to know how many documents match a condition, use count instead of searching and loading all results into the application:

~~~java
long count = operations.count(query, Product.class);
~~~

When pagination is needed, configure Pageable on the query and read page information from the result, or use a repository method returning Page according to the appropriate abstraction. For deep offsets, consider result limits and the search_after mechanism for large traversal flows. Exact APIs depend on the Spring Data Elasticsearch version.

## 5. IndexOperations: Managing Indices and Index Metadata

IndexOperations works at the index level, not the document level. It is obtained via ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.IndexOperations;

IndexOperations indexOperations =
        operations.indexOps(Product.class);
~~~

Or by specifying an index name:

~~~java
IndexOperations archiveIndexOperations =
        operations.indexOps(IndexCoordinates.of("products-archive"));
~~~

Common task groups:

| Operation | Purpose |
|---|---|
| exists | Check whether an index exists |
| create / createWithMapping | Create an index, optionally with mapping |
| delete | Delete an index |
| getMapping | Read the actual mapping |
| putMapping | Update the mapping within what Elasticsearch allows |
| getSettings | Read settings |
| refresh | Request an index refresh |
| alias operations | Read, add, or remove aliases |
| stats | Read index statistics if supported by the version's API |

IndexOperations does not save a Product and does not search for Products by content. It manages the structure and state of the index containing the documents.

### 5.1. Checking and Creating an Index

~~~java
public void ensureProductIndex() {
    IndexOperations indexOperations =
            operations.indexOps(Product.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
~~~

createWithMapping creates an index along with the mapping inferred by Spring Data from entity metadata. This is convenient for learning environments or applications with simple mappings.

In production, index creation typically belongs to a deployment pipeline or dedicated migration. In that case, the entity can declare createIndex = false so repository bootstrapping does not auto-create the index. IndexOperations can still be used by a controlled provisioning step.

Do not call delete and then create index every time the application starts. An index can hold important data and be shared by multiple instances.

### 5.2. Reading Mappings and Settings

~~~java
public void inspectProductIndex() {
    IndexOperations indexOperations =
            operations.indexOps(Product.class);

    Map<String, Object> mapping = indexOperations.getMapping();
    Map<String, Object> settings = indexOperations.getSettings();

    System.out.println(mapping);
    System.out.println(settings);
}
~~~

Mappings describe field types, analyzers, multi-fields, object/nested structures, and related metadata. Settings describe shard count, replicas, refresh interval, and other index configurations.

The mapping read from an index is the actual live configuration. The mapping generated from an entity via createMapping() is only the configuration Spring Data infers from Java metadata. The two structures may differ if the index was created by a template, migration, dynamic mapping, or a previous application version.

### 5.3. Updating Mappings

If new fields need to be added and Elasticsearch permits it, you can generate a mapping from an entity or define an explicit mapping and then call the corresponding update API:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

Document mapping = indexOperations.createMapping();
indexOperations.putMapping(mapping);
~~~

The example above illustrates the API flow. It should not be applied verbatim without inspecting the generated mapping and checking compatibility with the existing index. Elasticsearch does not allow arbitrarily changing the type of an already-indexed field. Some changes require creating a new index, reindexing data, and switching aliases.

### 5.4. Refreshing an Index

Elasticsearch is a near real-time system. Newly written documents may not appear immediately in search until the index is refreshed.

In testing scenarios that need to read right after writing, you can use an appropriate refresh policy or call refresh via IndexOperations:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Explicit refreshes have a cost. Do not call refresh after every save in production just to force search to see documents immediately. Choose a refresh policy based on latency and write throughput requirements.

## 6. Comparing Responsibility Boundaries

| Question or Need | Appropriate Abstraction | Example |
|---|---|---|
| Save a Product | DocumentOperations | save(product) |
| Get Product by ID | DocumentOperations | get(id, Product.class) |
| Delete document by ID | DocumentOperations | delete(id, Product.class) |
| Write multiple documents | DocumentOperations | bulk/saveAll |
| Search Products by criteria | SearchOperations | search(query, Product.class) |
| Count results | SearchOperations | count(query, Product.class) |
| Paginate and read scores | SearchOperations | SearchHits / Pageable |
| Check if index exists | IndexOperations | exists() |
| Create index and mapping | IndexOperations | createWithMapping() |
| Read mapping/settings | IndexOperations | getMapping(), getSettings() |
| Manage aliases | IndexOperations | alias operations |
| Refresh index | IndexOperations | refresh() |

A simple way to remember:

- DocumentOperations works with a document or group of documents.
- SearchOperations works with a result set defined by a query.
- IndexOperations works with the structure and lifecycle of an index.

## 7. How Do Repository and Operations Differ?

Spring Data Elasticsearch also provides the repository abstraction, such as ElasticsearchRepository<Product, String>. Repositories help applications declare CRUD and query methods by entity type.

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByStatus(String status);
}
~~~

Repositories are suitable for common operations that are easy to express via method names or @Query. When you need complex query control, dynamic index selection, hit metadata access, or specialized bulk operations, ElasticsearchOperations and related abstractions are more flexible.

Both approaches can coexist in one application:

- Repositories serve common CRUD and query use cases.
- ElasticsearchOperations serves advanced search, bulk, dynamic queries, or metadata handling.
- IndexOperations serves index management in provisioning steps or administrative tools.

There is no need to replace all repositories with Operations. Choose the API according to the level of control the use case requires.

## 8. Example of Organizing Services by Abstraction

A product search service can use SearchOperations via ElasticsearchOperations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchByCategory(String category) {
        Criteria criteria = new Criteria("category").is(category);
        Query query = new CriteriaQuery(criteria);
        return operations.search(query, Product.class);
    }
}
~~~

A document management service can use CRUD operations:

~~~java
@Service
public class ProductDocumentService {

    private final ElasticsearchOperations operations;

    public ProductDocumentService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product save(Product product) {
        return operations.save(product);
    }

    public Product get(String id) {
        return operations.get(id, Product.class);
    }

    public String delete(String id) {
        return operations.delete(id, Product.class);
    }
}
~~~

An index initialization component can use IndexOperations:

~~~java
@Component
public class ProductIndexProvisioner {

    private final ElasticsearchOperations operations;

    public ProductIndexProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIfMissing() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

In a production system, ProductIndexProvisioner should be invoked from a deployment step or coordinated administrative process, rather than letting multiple application instances create or modify indices concurrently.

## 9. Choosing Entity Class or IndexCoordinates?

IndexOperations and document/search operations can usually accept either an entity class or IndexCoordinates.

Use the entity class when:

- The target index is determined by @Document.
- Mapping and conversion should be based on entity metadata.
- The application works with one default index for the entity.

Use IndexCoordinates when:

- You need to access a specific alias or index.
- The same entity type is stored in multiple indices.
- There are versioned or archive physical indices.
- You want to operate on an index not directly tied to an entity class.

Example:

~~~java
IndexOperations byEntity =
        operations.indexOps(Product.class);

IndexOperations byName =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

When using IndexCoordinates, ensure the entity mapping is compatible with the specified index. Simply changing the index name does not make the schemas of two indices identical.

## 10. Version and Configuration Considerations

Spring Data Elasticsearch has evolved over time alongside the Elasticsearch client. Some differences you may encounter include:

- Names of concrete templates or underlying clients used.
- Method signatures, overloads, and return types.
- Query creation APIs, NativeQuery, CriteriaQuery, and bulk APIs.
- Ways to configure the client, mapping context, and custom conversions.
- Certain scroll or index administration operations may change or have recommended replacements.

Therefore, do not copy an example from documentation for a different release train without checking your actual dependencies. Verify the versions of Spring Boot, Spring Data Elasticsearch, Elasticsearch Java Client, and Elasticsearch server in use.

Abstractions may keep similar names and goals, yet specific method signatures can still differ. If the IDE reports a missing method, inspect the API of the resolved dependency instead of substituting a similarly named method from another version.

## 11. Common Design Mistakes

### 11.1. Using IndexOperations to Save Documents

IndexOperations manages index metadata. Saving entities must use DocumentOperations, ElasticsearchOperations, or a repository. Mixing the two layers makes services complex and hard to understand.

### 11.2. Using DocumentOperations for Full-Text Search

get by ID does not replace a search query. If you need to filter across multiple fields, rank, or paginate, use SearchOperations.

### 11.3. Creating Indices on Every Business Request

Checking and creating indices should not sit on the path of every save/search request. Index lifecycle is a provisioning responsibility; repeating it adds latency and can cause race conditions.

### 11.4. Treating save as Proof a Document Is Immediately Searchable

Elasticsearch is near real-time. After save, a document may not appear in search until the next refresh. If you need confirmation by ID, use get or exists as appropriate; if you need immediate search in tests, control refresh intentionally.

### 11.5. Treating Entity-Generated Mapping as the Live Mapping

createMapping() reflects current Java metadata. getMapping() reflects the running index. Always read the real mapping when investigating bugs or before a migration.

### 11.6. Using an Alias as If It Were a Physical Index

An alias can point to one or multiple indices and may designate a write index. When managing indices, inspect the alias targets to avoid deleting or restoring the wrong target.

### 11.7. Ignoring Item-Level Errors in Bulk Operations

A bulk request can contain both successful and failed items. Read item results and retry selectively; do not blindly retry the whole batch if operations may have side effects.

## 12. Testing by Abstraction

Each API group should be tested according to its responsibilities:

**DocumentOperations**

- Save creates or updates a document with the correct ID.
- Get returns an entity of the right type.
- Exists reflects document existence.
- Delete removes the right document and uses routing if applicable.
- Bulk checks per-item results and handles errors.

**SearchOperations**

- Query returns the right result set.
- Text/keyword mappings produce appropriate results.
- Sort, score, highlight, and pagination are preserved accurately.
- Count matches the query conditions.
- Queries via an alias search the intended indices.

**IndexOperations**

- Exists accurately reflects index status.
- Create produces the expected mapping/settings.
- GetMapping and getSettings read the actual configuration.
- Aliases point to the right indices and write index.
- Refresh is used properly where data visibility control is needed.

Integration tests should use an Elasticsearch version compatible with the project's client version. Mocking interfaces verifies that a service calls the right abstraction, but cannot validate mappings, Query DSL, or actual shard behavior.

## 13. Conclusion

DocumentOperations, SearchOperations, and IndexOperations divide the Spring Data Elasticsearch API according to what the application is operating on. DocumentOperations handles document CRUD and bulk writes; SearchOperations executes queries and returns search results; IndexOperations manages indices, mappings, settings, aliases, and refreshes.

ElasticsearchOperations provides a unified facade for documents and search, while allowing you to obtain IndexOperations via indexOps(...). Repositories remain suitable for common CRUD and query methods; Operations is useful when you need control over queries, target indices, or result metadata.

Choose the abstraction based on the responsibility of the use case: manipulating documents, searching for a result set, or managing index structure. Keeping these boundaries clear makes services easier to read, easier to test, and avoids mixing business logic with Elasticsearch's lifecycle.
