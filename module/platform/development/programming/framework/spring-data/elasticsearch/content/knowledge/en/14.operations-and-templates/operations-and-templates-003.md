# Choosing an Index via Document Type or IndexCoordinates

Spring Data Elasticsearch needs to know the target index when saving, reading, deleting, or searching documents. There are two common ways to determine the index:

- **Based on an entity type annotated with `@Document`**: the index name is declared in the Java class's metadata. Regular repository and operations calls use this name by default.
- **Passing `IndexCoordinates`**: specifies a particular index or alias at the time an operation is invoked. This is useful when one entity type is stored across multiple indices, when switching index versions, or when the query target is determined at runtime.

The two approaches do not completely replace each other. `@Document` describes the entity's mapping and default index; `IndexCoordinates` specifies the concrete target for a single operation. Whichever approach is chosen, the target index must still have a mapping compatible with the entity.

## 1. Default Index from @Document

Spring Data Elasticsearch uses the `@Document` annotation to describe which index an entity is stored in.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

In this example:

- `@Document(indexName = "products")` declares the default index name as `products`.
- `@Id` maps the `id` property to the `_id` document metadata field.
- `@Field` describes the data types of the fields.
- The mapping metadata of `ProductDocument` is used when Spring Data converts the entity into a document and vice versa.

When using a repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Operations such as:

~~~java
ProductDocument saved = productRepository.save(product);
Optional<ProductDocument> found =
        productRepository.findById("P-1001");
productRepository.deleteById("P-1001");
~~~

use the default index from `ProductDocument`'s metadata, which is `products` in this example.

This approach is suitable when an entity is always associated with a fixed index or alias throughout the application lifecycle.

## 2. What is IndexCoordinates?

`IndexCoordinates` is a Spring Data Elasticsearch object used to specify the target index or indices for an operation.

Import:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
~~~

Create an instance for an index:

~~~java
IndexCoordinates index = IndexCoordinates.of("products-v2");
~~~

You can use an alias name instead of a physical index name:

~~~java
IndexCoordinates index = IndexCoordinates.of("products");
~~~

If `products` is an alias pointing to `products-v2`, operations using `IndexCoordinates.of("products")` will target that alias.

`IndexCoordinates` only describes the operation target. It does not create the index, create the alias, or declare the mapping. The index or alias must be provisioned beforehand with a structure compatible with the entity.

## 3. Using the Document Type to Select the Index

When calling `ElasticsearchOperations` APIs while passing only the entity class, Spring Data retrieves the index from that class's metadata.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument save(ProductDocument product) {
        return operations.save(product);
    }

    public ProductDocument find(String id) {
        return operations.get(id, ProductDocument.class);
    }

    public void delete(String id) {
        operations.delete(id, ProductDocument.class);
    }
}
~~~

In these calls:

- `operations.save(product)` saves the entity using the default index from `@Document`.
- `operations.get(id, ProductDocument.class)` reads by ID from the entity's default index.
- `operations.delete(id, ProductDocument.class)` deletes by ID in the default index.

This keeps code concise because the index is declared centrally on the entity. It works well when an application has a single document model corresponding to a single default index.

You can obtain index management operations by entity type:

~~~java
IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);
~~~

`indexOps(ProductDocument.class)` uses the entity's metadata to determine the corresponding index. This is useful when you need to inspect or operate on the default index declared in `@Document`.

## 4. Using IndexCoordinates to Select the Index at Call Time

When you want to save the same entity type to an index other than the default, pass `IndexCoordinates` to the corresponding overload of `ElasticsearchOperations`.

Example saving to `products-v2`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument saveToV2(ProductDocument product) {
        IndexCoordinates target =
                IndexCoordinates.of("products-v2");

        return operations.save(product, target);
    }
}
~~~

Even though the entity declares `@Document(indexName = "products")`, the `save(product, target)` operation uses the index passed in `target` for that write.

You can read by ID from a specific index:

~~~java
IndexCoordinates target =
        IndexCoordinates.of("products-v2");

ProductDocument product =
        operations.get("P-1001", ProductDocument.class, target);
~~~

Delete by ID in a specific index:

~~~java
operations.delete(
        "P-1001",
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
);
~~~

The overloads accepting `IndexCoordinates` allow a single entity class to be reused across multiple indices without changing the `@Document` annotation each time.

The important thing is to pass the right index in every operation. If you write to `products-v2` but read using an overload that only takes `ProductDocument.class`, Spring Data will fall back to the default index `products` and may not find the document just written.

## 5. Searching Across an Index Selected by IndexCoordinates

`IndexCoordinates` can also be used when searching.

Example with `NativeQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<ProductDocument> searchProducts(
        ElasticsearchOperations operations,
        String keyword,
        String indexName
) {
    Query query = Query.of(q -> q
            .match(m -> m
                    .field("name")
                    .query(keyword)
            )
    );

    NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .build();

    IndexCoordinates target = IndexCoordinates.of(indexName);

    return operations.search(
            nativeQuery,
            ProductDocument.class,
            target
    );
}
~~~

In this example:

- `NativeQuery` describes the search criteria.
- `ProductDocument.class` tells Spring Data which entity type to convert the results into.
- `IndexCoordinates.of(indexName)` specifies the index the Search API will query.
- `SearchHits<ProductDocument>` contains the results along with search metadata.

The same query can be used for different indices as long as their mappings are compatible with the query and entity.

### Searching with Multiple Conditions

Example filtering by status and searching content:

~~~java
Query query = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("wireless keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value("PUBLISHED")
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(
                nativeQuery,
                ProductDocument.class,
                IndexCoordinates.of("products-v2")
        );
~~~

Index selection is independent of the query. The query defines which documents to find; `IndexCoordinates` defines where to look.

## 6. Distinguishing Entity Class from IndexCoordinates

These two parameters have different roles:

| Component | Role |
|---|---|
| `ProductDocument.class` | Specifies the entity type, mapping metadata, and how data is converted |
| `@Document(indexName = "products")` | Specifies the entity's default index |
| `IndexCoordinates.of("products-v2")` | Overrides the target index for a specific operation |
| `NativeQuery` | Describes the search criteria |
| `SearchHits<ProductDocument>` | Search results already converted into entities |

Example:

~~~java
operations.search(
        nativeQuery,
        ProductDocument.class,
        IndexCoordinates.of("products-archive")
);
~~~

Spring Data still uses `ProductDocument` metadata to map the results into `ProductDocument` objects. Only the target index is replaced with `products-archive`.

Therefore, the target index must have fields and data types matching how the entity is converted. `IndexCoordinates` does not automatically make a differently structured mapping compatible with the entity.

## 7. Using IndexCoordinates During Index Version Migration

A typical case is when an application has `products-v1` and `products-v2` during a migration phase.

You can use the same entity to read data from the old index and write it to the new index:

~~~java
IndexCoordinates oldIndex =
        IndexCoordinates.of("products-v1");

IndexCoordinates newIndex =
        IndexCoordinates.of("products-v2");

ProductDocument oldProduct =
        operations.get("P-1001", ProductDocument.class, oldIndex);

if (oldProduct != null) {
    operations.save(oldProduct, newIndex);
}
~~~

This example illustrates a single-document operation. For real migrations, you need to handle pagination/batches, per-document errors, mapping differences, and concurrent updates occurring during the transition.

If the v2 structure changes compared to the old entity, use a mapper to convert between the old model and new model rather than assuming you can write the old entity as-is to the new mapping.

## 8. Using IndexCoordinates with Aliases

In production, applications should generally access indices through a stable alias:

~~~java
IndexCoordinates products =
        IndexCoordinates.of("products");
~~~

The `products` alias can point to `products-v1` or `products-v2`. The application does not need code changes when the alias is switched to a new physical index.

Example creating an index and alias via the Elasticsearch API:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "status": {
        "type": "keyword"
      }
    }
  },
  "aliases": {
    "products": {
      "is_write_index": true
    }
  }
}
~~~

Once the alias exists, the application can use:

~~~java
operations.save(product, IndexCoordinates.of("products"));
~~~

For write operations, if an alias points to multiple indices, a write index must be clearly designated. Do not assume every alias can accept writes unambiguously.

If an alias points to multiple indices, the Search API can search across the indices represented by the alias. Ensure mappings are compatible across those indices and that results are not misinterpreted as coming from a single index.

## 9. Managing IndexOperations by Entity Type or Coordinates

Spring Data provides two ways to obtain `IndexOperations`:

~~~java
IndexOperations byEntity =
        operations.indexOps(ProductDocument.class);

IndexOperations byCoordinates =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

- `indexOps(ProductDocument.class)` retrieves index operations based on the entity's metadata.
- `indexOps(IndexCoordinates.of("products-v2"))` targets the specified index.

Operations such as checking index existence, deleting an index, or managing mappings should be executed intentionally and with appropriate permissions.

Example checks:

~~~java
boolean defaultIndexExists =
        operations.indexOps(ProductDocument.class).exists();

boolean version2Exists =
        operations.indexOps(
                IndexCoordinates.of("products-v2")
        ).exists();
~~~

Do not treat having `IndexOperations` as proof that the index has been created. `IndexCoordinates` only identifies the target. If the index does not exist yet, create it first via migration, provisioning, or the appropriate administrative API.

## 10. When to Use Document Type vs. IndexCoordinates?

| Need | Index Selection Approach |
|---|---|
| Entity is always saved to one default index | Use `@Document(indexName = "...")` and class-based overloads |
| Standard Repository CRUD | Use `@Document` metadata |
| Same entity needs to be written to another versioned index | Use `IndexCoordinates` with `ElasticsearchOperations` |
| Select index by tenant or at runtime | Use `IndexCoordinates` after validating the target name |
| Read data from an archive index | Use `IndexCoordinates` |
| Search via a stable alias | Use `IndexCoordinates.of("alias")` |
| Manage an entity's default index | `operations.indexOps(Entity.class)` |
| Manage a specific index | `operations.indexOps(IndexCoordinates)` |

The repository abstraction is typically tied to the entity's index metadata. When the target index needs to change per request or per tenant, use `ElasticsearchOperations` or a custom repository fragment to express that choice clearly.

## 11. Notes on Selecting Indices Dynamically by Tenant

A multi-tenant application may want to store each tenant's data in a separate index, for example:

- `products-tenant-a`
- `products-tenant-b`
- `products-tenant-c`

Coordinates can be built at runtime:

~~~java
IndexCoordinates target =
        IndexCoordinates.of("products-" + tenantId);

operations.save(product, target);
~~~

However, you should not concatenate client-supplied strings directly into index names. You must:

1. Validate the tenant ID against an authenticated identity.
2. Map the tenant to an authorized index.
3. Only allow operations on a managed list of indices/aliases.
4. Ensure the index is created beforehand with a compatible mapping.
5. Grant Elasticsearch permissions scoped to the tenant.
6. Pass the same target index to all read, write, update, and delete operations.

Example using a resolver:

~~~java
public class TenantIndexResolver {

    public IndexCoordinates resolve(String tenantId) {
        String indexName = switch (tenantId) {
            case "tenant-a" -> "products-tenant-a";
            case "tenant-b" -> "products-tenant-b";
            default -> throw new IllegalArgumentException(
                    "Unknown tenant: " + tenantId
            );
        };

        return IndexCoordinates.of(indexName);
    }
}
~~~

Then the service uses the resolver's result:

~~~java
IndexCoordinates target = tenantIndexResolver.resolve(tenantId);
ProductDocument saved = operations.save(product, target);
~~~

This example illustrates a static allowlist. Multi-tenant systems can use a registry or stored configuration to map tenants to indices. The key point is that the target index must be decided from an authenticated context, not taken arbitrarily from the request.

## 12. Common Pitfalls

### Writing to a Dynamic Index but Reading Using Default Metadata

Example:

~~~java
operations.save(product, IndexCoordinates.of("products-v2"));

ProductDocument found =
        operations.get("P-1001", ProductDocument.class);
~~~

The save command writes to `products-v2`, whereas the get command uses the default index `products`. If you want to read the exact document just written, pass the same coordinates:

~~~java
ProductDocument found = operations.get(
        "P-1001",
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
);
~~~

### Thinking IndexCoordinates Creates Mappings Automatically

`IndexCoordinates.of("products-v2")` does not create the index or mapping. Provision the index and mapping before writing data.

### Target Index Mapping Incompatible with Entity

Sending the same entity to an index with different field types can cause read or write errors. Check each index's mapping and use a separate document mapper if schemas differ.

### Using a Write Alias Without a Write Index

If an alias points to multiple indices without a designated write index, write operations may be rejected. Configure the alias with `is_write_index` when needed.

### Using Uncontrolled Index Names

If index names are concatenated from untrusted requests, the application may operate on the wrong index. Use a resolver/allowlist and restricted Elasticsearch permissions.

### Treating the Entity Class as If It Were an Index Name

`ProductDocument.class` provides mapping metadata, not an arbitrary index target. To pick a different index, pass `IndexCoordinates` explicitly.

## 13. Selection and Usage Workflow

When writing a service that interacts with Elasticsearch:

1. Determine whether the entity has one default index or needs multiple indices.
2. Declare `@Document(indexName = "...")` for the default index.
3. Use class-based overloads for normal CRUD.
4. When runtime index selection is needed, create `IndexCoordinates` from configuration or a validated resolver.
5. Pass coordinates to the corresponding save, get, delete, and search operations.
6. Ensure the target index/alias exists and its mapping is compatible.
7. If using aliases for version rollout, designate a write index and plan the alias switch.
8. If mappings differ across indices, use appropriate document projections/mappers.
9. Verify the actual target index via Elasticsearch APIs in the deployment environment.

## Conclusion

An entity type with `@Document` defines the default index and mapping metadata that Spring Data uses to convert documents. `IndexCoordinates` lets you specify a particular index or alias when calling `ElasticsearchOperations`, which is very useful for index versioning, archiving, or runtime target selection. When using coordinates, pass them consistently across operations and ensure the target index has been provisioned with a compatible mapping.
