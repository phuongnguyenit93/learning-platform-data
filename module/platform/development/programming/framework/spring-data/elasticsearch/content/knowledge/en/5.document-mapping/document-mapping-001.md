# @Document, indexName, and Auto-Index Creation Scope

In Spring Data Elasticsearch, `@Document` declares how a Java class represents a document stored in Elasticsearch. The `indexName` attribute specifies the index that operations on the entity target. This annotation also contains the `createIndex` option, which determines whether the repository infrastructure automatically creates the index during initialization.

Three concepts need to be distinguished:

- **Entity mapping:** describes how Java properties are converted into fields in an Elasticsearch document and mapping.
- **Index target:** specifies the index or target name that Spring Data uses for the entity.
- **Index lifecycle:** determines when the index is created, how settings and mappings are configured, and who is responsible for modifying or deleting the index.

`@Document` connects an entity with Elasticsearch metadata. It does not replace mapping design, index version management, or data deployment workflows in a production environment.

## 1. The Role of @Document

`@Document` belongs to the `org.springframework.data.elasticsearch.annotations` package. Place this annotation on an entity class so Spring Data knows the class is stored as a document in Elasticsearch.

Example:

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
    private String category;

    // constructors, getters and setters
}
~~~

In the example:

- `@Document` marks the `Product` class as a document type managed by Spring Data Elasticsearch.
- `indexName` specifies the target index as `products`.
- `@Id` maps the `id` property to the Elasticsearch document ID (`_id`).
- `@Field` provides mapping information for each field, such as `Text` for full-text search and `Keyword` for filtering or exact matching.

`@Document` provides metadata for the converter, repository, and index operation APIs. When saving an entity, Spring Data uses this metadata to determine where to write and how to convert the Java object into a document. When reading results, the converter uses the metadata to convert the document back into an entity.

The annotation does not mean Elasticsearch will create the index as soon as the JVM loads the Java class. Index creation depends on the repository initialization mechanism or index management calls executed in the application.

## 2. indexName Determines the Storage Target

`indexName` is the name of the Elasticsearch index that the entity targets. This is important metadata because repository operations typically rely on the entity type to find the corresponding index.

~~~java
@Document(indexName = "products")
public class Product {
    // fields
}
~~~

When a repository is declared:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

The repository knows `Product` is bound to the `products` index through the `@Document` metadata. The application does not need to repeat the index name in every regular CRUD call.

### 2.1. Index Names Must Follow Elasticsearch Rules

Elasticsearch has its own index naming rules. Index names must be lowercase; they cannot contain certain forbidden characters such as spaces, slashes, commas, or control characters. Therefore, you should use simple, stable names with a consistent convention.

Examples:

| Name | Remarks |
|---|---|
| products | Simple, valid name |
| order-events | Hyphens can be used |
| customer_profiles | Underscores can be used |
| Products | Unsuitable because it contains uppercase letters |
| product search | Invalid because it contains spaces |

You should name indexes based on the data type or search purpose, not mechanically after the Java class name. An index name is part of the deployment contract and can outlive the class name in source code.

### 2.2. indexName Is Not a Relational Table Name

An Elasticsearch index is not completely equivalent to a SQL table. An index contains JSON documents organized into shards and indexed according to a mapping. It does not provide the table model, foreign keys, and general joins of a relational database.

Therefore, `indexName = "products"` only specifies the document target in Elasticsearch. It does not create a `products` table in PostgreSQL or MySQL, nor does it automatically establish relationships with JPA entities.

If the same Java class is used for multiple storage purposes, you must clearly distinguish the metadata of each technology. `@Document` belongs to Spring Data Elasticsearch; `@Entity` belongs to JPA. Do not assume these two annotations share the same lifecycle or data structure creation rules.

### 2.3. One Entity and Multiple Indexes

A `@Document(indexName = "...")` declaration typically describes a single default target for an entity. If an application needs to store or query the same data type across multiple indexes, such as monthly or per-tenant indexes, lower-level APIs can be used to specify `IndexCoordinates` for a specific operation.

Example with `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void saveToArchive(Product product) {
        operations.save(
                product,
                IndexCoordinates.of("products-archive")
        );
    }
}
~~~

The index name passed to a specific operation becomes the target of that operation. You need to clearly manage which index is written to, which index is read from, and how multiple indexes are queried to avoid unexpectedly scattered data.

Do not turn dynamic index selection into logic scattered across controllers or repositories. Place index routing rules in a service that can be controlled and tested.

## 3. createIndex and the Scope of Auto-Index Creation

`@Document` has a `createIndex` attribute. In current Spring Data Elasticsearch versions, the default value of this attribute is `true`.

~~~java
@Document(
    indexName = "products",
    createIndex = true
)
public class Product {
    // fields
}
~~~

When Spring Data Elasticsearch initializes the repository infrastructure and processes entity metadata, this option allows the framework to automatically create the index if it does not already exist. Index creation can use a mapping derived from entity metadata and annotations such as `@Field`.

The important point is the scope of the option:

- `createIndex = true` allows the repository bootstrap mechanism to create the index when needed.
- It does not mean every `save()` call recreates the index.
- It does not mean changing the Java class automatically updates every mapping of an existing index.
- It does not replace the system's settings management, mapping migration, and index lifecycle processes.

Specific behavior also depends on the Spring Data Elasticsearch version and how the application initializes repositories. Check the documentation for the release train your project uses.

### 3.1. When the Index Does Not Exist Yet

Suppose the application declares:

~~~java
@Document(indexName = "products", createIndex = true)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

If the repository is initialized and the `products` index does not exist yet, the bootstrap mechanism can create the index along with its mapping based on the entity metadata. After that, the repository can perform operations against that index.

Conceptual flow:

~~~text
Spring application starts
          |
          v
Repository infrastructure initializes
          |
          v
Read @Document metadata
          |
          v
Check index by indexName
          |
          +---- Index already exists ----> Use existing index
          |
          +---- Index does not exist --> Create index and mapping
                                         if createIndex = true
~~~

This is a convenient mechanism for learning examples, development environments, or applications with simple and stable mappings.

### 3.2. When the Index Already Exists

If the `products` index already exists, the framework does not need to recreate the index. Adding Java properties or changing `@Field` does not mean the old mapping is automatically replaced.

For example, the existing index has the `name` field mapped as `keyword`, while the new entity declares:

~~~java
@Field(type = FieldType.Text)
private String name;
~~~

Merely editing the annotation in source code does not turn the existing mapping into `text`. Elasticsearch does not allow arbitrarily changing certain mapping types of an already indexed field, because doing so can alter how data is stored and searched.

When a mapping needs to change, you usually have to design a migration: create a new index with the right mapping, transfer or reindex the data, verify the results, and then switch the alias or application to the new index. Do not rely on `createIndex = true` to handle migrations automatically.

### 3.3. When Setting createIndex = false

If you do not want repository bootstrap to automatically create the index, declare:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class Product {
    // fields
}
~~~

In that case, index creation becomes the responsibility of another process, such as:

- A deployment or migration script executed before the application starts.
- Provisioning infrastructure that creates indexes, settings, mappings, and aliases.
- A dedicated index administration component in the application.
- An operational workflow controlled by the data platform team.

`createIndex = false` only controls auto-index creation behavior during repository bootstrap. It does not forbid the application from explicitly calling index management APIs. If the index does not exist yet and the application starts writing or searching, operations may fail until the index is created.

## 4. Auto-Index Creation and Proactive Index Management Are Two Different Operational Approaches

Responsibility for index creation can be divided into two models.

| Model | How it works | Suitable when |
|---|---|---|
| Repository bootstrap auto-creation | `@Document(createIndex = true)` lets Spring Data create the index when the repository initializes if the index does not exist yet | Learning, development, small applications, simple mappings |
| Proactive provisioning | `createIndex = false`; migration or deployment process creates the index beforehand | Production, complex mappings, need to control settings, aliases, and change history |

### 4.1. Using IndexOperations to Create Indexes Intentionally

Spring Data Elasticsearch provides `IndexOperations` to check and manage indexes. You can obtain this object from `ElasticsearchOperations` by entity type:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

`indexOps(Product.class)` retrieves index information from `Product`'s metadata, including `indexName`. `exists()` checks whether the target index already exists. `createWithMapping()` creates the index along with the mapping built from the entity metadata.

This example illustrates the application proactively calling the index creation API. In a multi-instance system, you should not let every instance run an uncoordinated index creation process simultaneously. Use a migration or a deployment step that runs once, or implement appropriate contention and initialization error handling.

If custom settings such as analyzers, shard counts, replicas, or storage configurations are needed, prepare the settings along with the mapping during the provisioning step. `createWithMapping()` is convenient when using entity-derived mappings and default configurations; it does not replace a complete production index configuration.

### 4.2. Why Should You Not Delete and Recreate an Index on Every Startup?

An index may contain business data and be used by multiple application instances. If it is deleted and recreated on every startup:

- Indexed data can be lost.
- Running instances may encounter query or write errors.
- Startup may take longer due to reloading data.
- An application deployment can accidentally become a destructive data operation.

Index initialization should be idempotent: re-running it must not lose data or change state unexpectedly. For production, clearly separate checking, creating a new index, reindexing, and switching aliases.

## 5. Combining @Document with Entity Mapping

`@Document` specifies the index and document/index-level options. Field mappings are described by entity metadata, especially `@Field`.

Example:

~~~java
@Document(indexName = "articles", createIndex = true)
public class Article {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant publishedAt;
}
~~~

In the example:

- `title` and `content` are text fields, suitable for full-text queries.
- `status` is a keyword field, suitable for exact filter conditions and aggregations.
- `publishedAt` is mapped as a date type for sorting or filtering by time.

The mapping is inferred from entity metadata when Spring Data creates the mapping. However, inferred mappings do not always meet search requirements. Analyzers, normalizers, multi-fields, dynamic mapping, and special settings may need to be declared explicitly in the mapping or settings.

When designing a mapping, start from actual queries:

| Requirement | Common mapping approach |
|---|---|
| Search for words in content | `text` with an appropriate analyzer |
| Filter by status or code | `keyword` |
| Sort by timestamp | `date` |
| Filter or perform numeric calculations | Appropriate numeric types such as `integer`, `long`, `double` |
| Search text while still sorting by the original value | `text` combined with a `keyword` multi-field if needed |

Do not rely solely on Java types to infer all search behavior. Explicitly determine the generated mapping and verify it on an actual index.

## 6. Using Aliases and Versioned Indexes

In production, physical index names may carry versions, such as `products-v1` and `products-v2`. The application can work through stable aliases such as `products-read` or `products-write`, while the operations team manages which physical index each alias points to.

Architecture example:

~~~text
Spring Data entity
indexName = "products-write"
          |
          v
      write alias
          |
          v
     products-v2

read alias
          |
          v
     products-v2
~~~

In an alias-managed model, the index is created beforehand via migration or deployment. The entity can reference a stable alias, but auto-index creation in repository bootstrap should be disabled:

~~~java
@Document(
    indexName = "products-write",
    createIndex = false
)
public class Product {
    // fields
}
~~~

If the alias does not exist yet and the bootstrap mechanism tries to create an index named `products-write`, the application could accidentally create a real index bearing the intended alias name. Therefore, agree on who creates aliases, who creates physical indexes, and the order of deployment steps.

A version transition workflow may include:

1. Create `products-v2` with the new settings and mapping.
2. Reindex data from the current index to `products-v2`.
3. Verify document counts and critical queries.
4. Switch read/write aliases to the new index via a controlled alias operation.
5. Delete the old index only after a verification period and in accordance with retention policies.

Aliases allow changing the physical index while the application continues using a stable logical name. They do not perform data migration automatically or guarantee compatibility between two indexes.

## 7. Choosing Auto-Index Creation Scope by Environment

A configuration that is convenient locally may not be suitable for production. Choose the lifecycle based on the level of control required.

| Environment | Possible approach | Reason |
|---|---|---|
| Local learning | `createIndex = true` | Reduces initial setup steps |
| Integration test | Create index in test setup and delete in teardown | Each run has a clean data state |
| Shared development | Create index via controlled migration or script | Avoids multiple instances modifying schema simultaneously |
| Staging | Use the same provisioning process as production | Catches mapping and migration errors before release |
| Production | Usually `createIndex = false`, create index via deployment/migration | Controls settings, mapping, permissions, and timing of changes |

There is no single `createIndex` value suitable for every project. What matters is clearly defining which process has permission to create indexes and which process has permission to modify mappings.

## 8. Common Mistakes

### 8.1. Thinking @Document Creates the Index Immediately Upon Declaration

The annotation only provides metadata. The index is created when repository bootstrap or index management code actually executes according to the corresponding configuration. If the application neither initializes a repository nor calls an index creation API, merely declaring the entity is not enough to ensure the index appears.

### 8.2. Thinking Changing indexName Migrates Data

Changing from `products-v1` to `products-v2` only changes the target the entity points to. Spring Data does not automatically copy documents from the old index to the new one. You need reindexing or a separate migration workflow.

### 8.3. Thinking createIndex = false Forbids All Index Creation Operations

This attribute controls repository bootstrap. Application code can still call `IndexOperations.create()` or `createWithMapping()`, and deployment scripts can still create indexes.

### 8.4. Thinking createIndex = true Automatically Updates Mappings

Creating an index when it does not exist and updating the mapping of an existing index are two different tasks. Mapping changes must be evaluated against Elasticsearch's update capabilities; some changes require a new index and reindexing.

### 8.5. Using an Alias Without Disabling Auto-Index Creation

If `indexName` is an alias name, repository bootstrap may create an index with that exact name when the alias does not yet exist. In an alias-managed model, create the alias first and let the deployment process manage physical indexes.

### 8.6. Letting Multiple Instances Run Migrations Simultaneously

Multiple instances checking that an index does not exist and trying to create it simultaneously can cause race conditions. Have a dedicated deployment step create the index or use an appropriate coordination mechanism.

## 9. Practical Selection Workflow

When adding a new Elasticsearch entity, you can follow this sequence:

1. Identify the data and queries that the entity serves.
2. Choose a stable, valid `indexName` with a clear naming convention.
3. Declare `@Document` along with `@Id` and `@Field` for fields that require explicit mapping.
4. Decide whether the index is created during repository bootstrap or by migration/deployment.
5. If using bootstrap, evaluate `createIndex = true` and the generated mapping.
6. If using separate provisioning, set `createIndex = false` and create settings/mappings before the application accesses the index.
7. Inspect the actual mapping in Elasticsearch, test representative queries, and verify CRUD operations.
8. Establish a workflow for changing mappings, reindexing, and switching aliases as the data structure evolves.

A typical choice for lessons or small applications:

~~~java
@Document(indexName = "products", createIndex = true)
public class Product {
    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

A typical choice for production with migration-managed indexes:

~~~java
@Document(indexName = "products-write", createIndex = false)
public class Product {
    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

In the second example, the deployment pipeline is responsible for creating the physical index, mapping, and alias before the application begins receiving traffic.

## 10. Conclusion

`@Document` declares Elasticsearch metadata for an entity; `indexName` specifies the index or target name used by operations on the entity. `createIndex` controls whether repository bootstrap automatically creates the index when it does not exist yet and usually defaults to `true`.

For learning environments or small applications, auto-index creation helps you get started quickly. For production, complex mappings, aliases, or multi-version deployment workflows, indexes should be managed via controlled migration/provisioning and `createIndex = false` is commonly set.

Treat index creation, mapping definition, and migration as part of the data lifecycle. `@Document` helps Spring Data understand the entity; it does not decide the entire Elasticsearch operational strategy for the application.
