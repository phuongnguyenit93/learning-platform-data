# When Repositories Auto-Create Indexes and When Explicit Management Is Required

Spring Data Elasticsearch can automatically create an index when a repository is initialized, but this capability only fits certain deployment approaches. For systems with complex mappings, multiple environments, strict authorization requirements, or safe data upgrades, creating and changing indexes should be managed as a separate deployment step.

To make the right choice, distinguish three mechanisms that are often confused: **Spring Data Repository creating an index from entity metadata**, **Elasticsearch cluster auto-creating an index when receiving a document write to a nonexistent index**, and **the application or deployment pipeline explicitly calling the index creation API**. They differ in timing, permissions, and outcomes.

## 1. How Are Indexes Created Automatically?

### 1.1. Repository Creating an Index Based on @Document

Spring Data Elasticsearch allows annotating an entity with @Document:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

The createIndex attribute of @Document defaults to true. When the corresponding repository is initialized, Spring Data can check the target index. If the index does not exist yet and the entity permits index creation, the repository asks Elasticsearch to create the index along with settings and mapping inferred from the entity metadata.

You can state the intent explicitly:

~~~java
@Document(
    indexName = "products",
    createIndex = true
)
public class ProductDocument {
    // ...
}
~~~

This mechanism is convenient for small applications, learning environments, experimentation, or indexes with simple structures fully described by annotations.

The repository can only create the index when the application can connect to the cluster and the identity in use has permissions for the required operation. If the cluster is unreachable, credentials are invalid, or the account lacks permission to create indexes, repository initialization may fail.

### 1.2. Creating an Index Does Not Mean Updating an Existing Mapping

Suppose the products index already exists. When the repository initializes, Spring Data sees that the index already exists and does not delete and recreate it by default just because annotations in Java changed.

For example, the initial code declares:

~~~java
@Field(type = FieldType.Text)
private String category;
~~~

Later it is changed to:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

The old index can still retain the category field with type text. Metadata in the new code does not automatically convert the old mapping into keyword.

@Document also has the alwaysWriteMapping attribute, which defaults to false in Spring Data Elasticsearch versions that support it. If enabled, Spring Data may write the mapping from the entity when the repository initializes even if the index already exists. However, writing a mapping does not bypass Elasticsearch's limits: you cannot arbitrarily change the type of an already-created field. Check your exact Spring Data version before relying on this option.

Therefore, do not treat createIndex = true as a schema migration mechanism. It solves creating a missing index, not upgrading an index that already contains data.

### 1.3. The Elasticsearch Cluster Can Also Auto-Create Indexes

Elasticsearch has a cluster-level auto index creation mechanism, controlled by the action.auto_create_index setting on the Elasticsearch server side.

When a request writes a document to an index that does not exist yet, the cluster can automatically create the index if this policy allows it. That mechanism operates on the server side and does not depend on whether the application declares createIndex = true.

Here is the key distinction:

| Mechanism | Who Initiates? | Timing | Source of Settings/Mapping |
|---|---|---|---|
| Repository auto-create | Spring Data Elasticsearch | When repository initializes and index does not exist | Entity metadata, annotations, and related configurations |
| Cluster auto-create | Elasticsearch server | When receiving a request that writes to a nonexistent index | Dynamic mapping and cluster defaults/policies |
| Explicit provisioning | Application, migration job, or deployment pipeline | At a defined deployment step | Explicitly managed mapping/settings |

For example, the application declares createIndex = false, yet the cluster still allows auto-create. If the application writes a document to a nonexistent index, Elasticsearch can auto-create the index using dynamic mapping. Thus, createIndex = false does not automatically disable action.auto_create_index.

If you want to control index creation, coordinate Spring Data configuration, account privileges, and the cluster's auto-create policy together.

## 2. When Is Repository Auto-Create Suitable?

### 2.1. Small Projects or Development Environments

Repository auto-create is usually suitable when:

- Only a single application or module manages the index.
- The index has a simple structure.
- The mapping can be fully expressed using annotations.
- There are no complex data migration requirements.
- Development environments can create a new index on application startup.
- The account running the application is allowed to create indexes.

Example:

~~~java
@Document(indexName = "products", createIndex = true)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;
}
~~~

When the repository initializes and the index does not exist, Spring Data can create the index with the corresponding mapping. The development team does not need to write an extra manual index creation step for test environments.

### 2.2. Entity Metadata Already Describes the Structure Sufficiently

Repository auto-create is more suitable when settings and mapping can be stably described in source code.

Spring Data Elasticsearch supports annotations such as:

- @Document to specify the index and creation behavior.
- @Setting to supply index settings.
- @Mapping to supply JSON mapping.
- @Field to describe field types and related options.
- @MultiField and @InnerField to describe multiple ways of indexing a property.

Example:

~~~java
@Document(indexName = "articles", createIndex = true)
@Setting(settingPath = "/elasticsearch/settings/articles-settings.json")
@Mapping(mappingPath = "/elasticsearch/mappings/articles-mapping.json")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

The paths above are classpath resources in the application. Settings can contain analyzers, tokenizers, and token filters; mapping can describe fields, nested objects, and other mapping attributes.

If an index needs custom analyzers, settings must be present at index creation time. Do not expect that adding an analyzer to annotations later will automatically update an existing index.

## 3. When Should Repository Auto-Create Be Turned Off?

### 3.1. Production Needs Controlled Index Lifecycles

In production, index creation is typically part of the data deployment workflow. You may need to:

- Review mappings before applying them.
- Control shards, replicas, refresh interval, and analyzers.
- Create versioned indexes such as products-v1, products-v2.
- Reindex data before switching the application to a new schema.
- Switch aliases to change the target index in a controlled manner.
- Track migration status and rollback capability.
- Separate index deployment permissions from the application's document read/write permissions.

In these cases, turn off automatic repository index creation:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {
    // ...
}
~~~

The application can still use the repository to read/write documents in an already-provisioned index. The index must be created beforehand by a migration job, deployment pipeline, or an administrative component granted appropriate permissions.

### 3.2. Runtime Applications Should Not Hold Index Admin Privileges

An application that only needs to search and update documents usually does not need permission to create or delete indexes.

If repository auto-create is enabled, startup initialization may require permission to create indexes and write mappings. This can force runtime credentials to hold broader privileges than necessary.

Separating the two roles reduces privileges:

| Role | Responsibility | Typical Privileges |
|---|---|---|
| Index provisioning/migration | Create indexes, apply settings and mapping, manage aliases | Required index management privileges |
| Runtime application | Search, read, index, or update documents | Read/write privileges on granted indexes |

Specific privilege names and scopes depend on the Elasticsearch version and operations executed. Grant least-privilege permissions according to actual APIs; do not grant cluster administrator rights to an application just so the repository can start up.

### 3.3. Multiple Applications Share One Index

If multiple services write to the same index, do not let each service independently decide the mapping and when the index is created.

For example, the catalog service and search service share the products index. If the two applications declare different metadata, one service might expect price as double while the other expects price as keyword. Whichever application starts first and creates the index can cause mapping or query errors for the other.

Designate one authoritative source of schema management. The remaining services share the same document contract and do not create or modify the mapping themselves.

### 3.4. Complex Mapping or Migration Requirements

Manage indexes explicitly if the index uses:

- Custom analyzers or language analysis plugins.
- Complex nested mappings, multi-fields, and dynamic templates.
- Aliases and multiple versioned indexes.
- ILM/data streams or rollover workflows.
- Mappings shared across multiple applications.
- Reindexing, backfilling, or data migrations.
- Requirements to change field types, analyzers, or document structure.

Changes to field types or analyzers usually cannot be applied directly to an index that already contains data in an arbitrary way. A workflow that creates a new index and reindexes is easier to control.

## 4. Creating Indexes Explicitly with IndexOperations

### 4.1. Using Entity Mapping Metadata

Spring Data Elasticsearch provides IndexOperations through ElasticsearchOperations. When you want to explicitly create an index from entity metadata, you can write:

~~~java
@Service
public class ProductIndexProvisioner {

    private final ElasticsearchOperations operations;

    public ProductIndexProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndexIfMissing() {
        IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

indexOps(ProductDocument.class) retrieves the index operations bound to entity metadata. exists() checks the target index. createWithMapping() creates the index with settings/mapping derived from the entity and its annotations.

This approach is more explicit than relying on repository initialization timing, while still using Java metadata as the structure source. It is suitable when you want a clear provisioning step in the application or a separate job.

Do not call createWithMapping() unconditionally on every request. Place this operation in a deployment step or controlled initialization.

### 4.2. Creating Index and Mapping as Separate Steps

Some situations require separating index creation and writing the mapping:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping();
}
~~~

create() creates the index with the corresponding settings; putMapping() sends the entity's mapping. This separation makes the two operations explicit and can be useful when settings/mapping need separate handling.

Be aware of failure states between the two steps: if index creation succeeds but writing the mapping fails, the index may exist without the intended mapping. Subsequent runs should not merely check exists() and conclude provisioning succeeded. You need a mechanism to verify the actual mapping and handle partial states.

### 4.3. Using IndexCoordinates When Index Name Is Not Fixed to an Entity

When the index name is determined at runtime, you can use IndexCoordinates:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

This approach is useful with versioned indexes, per-tenant indexes, or dynamically chosen aliases. However, if the index name is not tied directly to an entity class, the application must ensure that settings and mapping are properly supplied for that index.

Repositories typically derive the index name from @Document metadata. For flows using dynamic index names, ElasticsearchOperations and IndexCoordinates are usually more suitable.

## 5. Managing Settings and Mapping Explicitly

### 5.1. Settings and Mapping Have Different Roles

**Index settings** control how the index is structured and operated, for example:

- Number of primary shards and replicas.
- Refresh interval.
- Analyzers, tokenizers, and token filters.
- Other index-level settings.

**Mapping** describes how each field is interpreted, for example:

- text, keyword, date, long, boolean.
- Object and nested.
- Multi-fields.
- Dynamic mapping behavior.
- Analyzers attached to fields.

Settings and mappings can be managed via JSON resources in source code, migration scripts, or deployment tools. Review them as part of the application schema.

### 5.2. Example Settings and Mapping Resources

An illustrative settings file:

~~~json
{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  }
}
~~~

An illustrative mapping file:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "catalog_text",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    }
  }
}
~~~

These are example structures. Shard/replica counts, analyzers, and field types must be chosen based on actual scale, workload, and Elasticsearch version. Do not copy illustrative parameters into production configurations without evaluation.

### 5.3. Do Not Let Annotations and JSON Drift Apart

If the same field is described in Java annotations and JSON mapping, keep the two sources consistent. For instance, if the entity declares category as Keyword while the JSON mapping declares it as text, the converter still serializes values according to Java metadata while the cluster indexes according to the JSON mapping.

You can choose a clear strategy:

- Use annotations as the primary source for simple mappings.
- Use JSON mapping as the primary source for complex mappings, while annotations only hold metadata needed by the converter.
- Generate or validate mappings from a centrally managed schema if multiple applications share an index.

After provisioning, inspect the actual mapping on the cluster to catch discrepancies.

## 6. Cluster auto_create_index and Dynamic Mapping

### 6.1. Server-Side Elasticsearch Configuration

Elasticsearch has the action.auto_create_index setting to allow or deny automatic index creation when a request targets a nonexistent index. This policy is configured on the server side, not in Spring Boot's application.yml.

Depending on the environment, administrators can:

- Allow auto-create globally.
- Deny auto-create.
- Allow or deny based on index patterns.

Exact pattern syntax and policies should follow the documentation for your Elasticsearch version. In production, explicitly specify which indexes are allowed to be auto-created, especially when index names may come from application input.

### 6.2. Dynamic Mapping Can Create Unexpected Schemas

When the cluster auto-creates an index upon receiving a document, Elasticsearch can infer the mapping from the fields in the first document. This is dynamic mapping.

Example first document:

~~~json
{
  "name": "Keyboard",
  "price": 49.9
}
~~~

Elasticsearch can infer name as an appropriate text/keyword type according to default dynamic templates and price as a numeric type. However, if later data sends price as an incompatible string, the request may fail.

Dynamic mapping is convenient for prototyping or flexible data, but can cause:

- Fields inferred with the wrong type.
- Mapping explosion when documents contain many dynamic fields.
- Schema drift across environments.
- Difficulty controlling analyzers and nested structures.
- Failures when data is inconsistent.

For stable business indexes, create the mapping before ingesting real data.

### 6.3. Coordinating the Mechanisms

Illustrative configurations:

| @Document.createIndex | action.auto_create_index | Result When Index Does Not Exist |
|---|---|---|
| true | Allowed | Repository can create the index from entity metadata at startup |
| true | Denied | Repository auto-create is rejected by the cluster |
| false | Allowed | Repository does not proactively create; subsequent writes can still trigger cluster auto-create |
| false | Denied | Index must be provisioned beforehand; writes to a missing index fail |

The outcome also depends on account permissions, repository initialization timing, and specific configuration. This table describes coordination principles, not a substitute for testing in a real environment.

## 7. Managing Versioned Indexes and Aliases

### 7.1. Do Not Modify Old Schemas Directly on Major Changes

When the current mapping is no longer suitable, such as needing to change a field type or analyzer, a common workflow is creating a new versioned index:

~~~text
products-v1  -> currently serving index
products-v2  -> new index with updated mapping/settings
products     -> alias pointing to the active index
~~~

An alias lets the application use a stable logical name while physical indexes change across versions.

### 7.2. Basic Migration Workflow

A blue-green index workflow can include:

1. Create products-v2 with reviewed settings and mapping.
2. Reindex data from products-v1 to products-v2.
3. Verify document counts, sample data, and critical queries.
4. Pause or sync changes occurring during reindexing if data consistency must be guaranteed.
5. Switch the products alias from the old index to the new index using an appropriate alias operation.
6. Monitor the application after switching.
7. Only delete the old index after the rollback period expires and data safety is confirmed.

If the application continues writing during reindexing, design a way to synchronize new writes to avoid losing updates. Depending on the workload, you can pause writes temporarily, dual-write, use change capture, or run a final sync pass before switching the alias.

### 7.3. Repositories and Aliases

An entity can declare its index name as the logical alias:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // ...
}
~~~

In the cluster, the products alias can point to products-v1 or products-v2. The application does not need to change the repository when switching aliases if the mapping contract is compatible.

When using an alias as a write target, ensure the alias has the right write index configured if it points to multiple indexes. Switching aliases should be performed via the alias API and appropriate deployment policy.

## 8. Avoiding Errors When Multiple Instances Start Simultaneously

### 8.1. Race Condition During Index Creation

In an environment with multiple application instances, two instances can start simultaneously and both see that the index does not exist:

~~~mermaid
sequenceDiagram
    participant A as App instance A
    participant B as App instance B
    participant ES as Elasticsearch
    A->>ES: exists(products) -> false
    B->>ES: exists(products) -> false
    A->>ES: create(products)
    B->>ES: create(products)
    ES-->>A: created
    ES-->>B: resource_already_exists_exception
~~~

One instance succeeds, while the other may receive an error because the index was created between the two checks. Therefore, the if-not-exists-then-create pattern is not a distributed lock and does not eliminate race conditions.

You can address this by:

- Running provisioning once in a pipeline or migration job.
- Using a lock/leader election mechanism if provisioning must run in a multi-instance environment.
- When handling duplicate creation errors, re-checking the actual index and mapping; only treat it as success if the schema meets requirements.
- Not swallowing all exceptions merely assuming another instance already created the index.

### 8.2. Deployment Order

With explicit management, the deployment order should be:

~~~mermaid
flowchart TD
    A[Review schema and mapping] --> B[Provision index]
    B --> C[Verify settings and mapping]
    C --> D[Deploy application]
    D --> E[Smoke test read/write]
    E --> F[Monitor and verify]
~~~

If the application is deployed before the new index is ready, requests may fail with index_not_found_exception. The pipeline should ensure provisioning and verification complete before bringing the application version depending on the new schema into service.

## 9. Verifying Indexes Before and After Provisioning

### 9.1. Checking Index Existence

You can check via IndexOperations:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

boolean exists = indexOperations.exists();
~~~

Or call the Elasticsearch API:

~~~http
HEAD /products
~~~

A successful response indicates the index exists and the endpoint can answer that request. It does not prove the mapping is correct or that the application has sufficient permissions for document operations.

### 9.2. Checking Mapping and Settings

After creating the index, read the actual mapping and settings:

~~~http
GET /products/_mapping
GET /products/_settings
~~~

Check:

- Are field names correct?
- Are field types correct?
- Are analyzers and search analyzers configured?
- Are object/nested settings right for query requirements?
- Are shards/replicas and refresh interval right for the environment?
- Is dynamic mapping enabled intentionally?

You can use IndexOperations APIs to retrieve mapping/settings instead of calling HTTP directly. Verification should be done with an account having permission to read the corresponding index metadata.

### 9.3. Checking Data and Queries

After confirming the mapping, test:

- Indexing a representative document.
- Reading the document back by ID.
- Running a full-text query.
- Running an exact match on a keyword field.
- Testing nested queries if nested mapping is used.
- Testing sorts, aggregations, and date ranges if the application uses them.

An index being created successfully does not mean data and queries are already right. Smoke tests should reflect the application's critical operations.

## 10. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Repository initialization fails because it cannot create the index | Cluster unavailable, bad credentials, or lacking index creation permissions | Check connectivity, permissions, and consider disabling auto-create if using separate provisioning |
| index_not_found_exception | Index has not been provisioned and cluster does not auto-create | Create the index before running repository operations |
| resource_already_exists_exception | Multiple instances created the index concurrently or another process just created it | Re-verify index/mapping; use a single provisioning job |
| Index exists but field type is wrong | Old mapping was not changed by new annotations | Create a new index and reindex if needed |
| Field appears with unexpected type | Cluster auto-create and dynamic mapping inferred from first document | Provision mapping explicitly and control auto-create |
| Analyzer does not exist on index creation | Settings missing analyzer or resource not loaded | Check @Setting, resource files, and index creation order |
| createIndex = false yet index still appears | Cluster-level action.auto_create_index allows creation on write | Check server configuration and application privileges |
| Index creation succeeds but writing mapping fails | Invalid mapping or insufficient permissions | Check response, schema, and mapping management privileges |
| Application starts slowly or fails when cluster is temporarily unavailable | Provisioning occurs during repository initialization | Separate provisioning into a deployment step and control readiness |

When encountering errors, identify which mechanism created or intended to create the index. Check application logs, Elasticsearch responses, and the actual mapping rather than looking only at @Document.

## 11. Choosing a Strategy by Environment

| Environment/Scenario | Commonly Suitable Strategy |
|---|---|
| Local learning or demo | Repository auto-create with createIndex = true |
| Integration test using temporary index | Create index in test setup, delete after test if safe |
| Staging with production-like mapping | Provision via migration/pipeline matching production |
| Production, single app owning a simple index | Auto-create can be used if permissions and lifecycle are controlled |
| Production, multiple services sharing an index | One authoritative source for provisioning/schema |
| Complex mapping, custom analyzers | Explicitly managed settings/mapping |
| Changing field types or analyzers | Create new versioned index, reindex, and switch alias |
| Runtime credentials lack admin privileges | Disable repository auto-create and provision before deploy |

There is no single right choice for every system. The decision should depend on who owns the index, who is allowed to change the schema, mapping complexity, deployment methods, and data safety requirements.

## 12. Practical Selection Checklist

Before enabling auto-create, answer:

1. Is this index used by a single application or shared across multiple services?
2. Can the mapping be fully and stably expressed via entity metadata?
3. Are there analyzers, nested fields, aliases, rollovers, or migrations needing separate management?
4. Is the runtime application allowed to create indexes?
5. Does the cluster allow auto-create on write requests?
6. If multiple instances start at once, who is responsible for creating the index?
7. When the mapping changes, how will old data be handled?
8. Can settings/mapping be verified before deploying the application?

If the answers show that the index has a lifecycle independent of the application lifecycle, manage provisioning in a separate step. If the index is simple, has a single owner, and the environment allows it, repository auto-create is a convenient choice.

The core takeaway is clearly distinguishing **creating a missing index**, **updating a mapping**, and **schema/data migration**. Repository auto-create addresses the first within the scope of entity metadata. Cluster auto-create is a server-side policy. Explicit management provides control over the entire index lifecycle, access permissions, and data transitions as the system evolves.
