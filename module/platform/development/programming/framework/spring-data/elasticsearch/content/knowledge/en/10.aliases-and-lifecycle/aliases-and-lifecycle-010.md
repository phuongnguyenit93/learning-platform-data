# Distinguishing Cluster Lifecycle Management from Repository Functionality

In a Spring Data Elasticsearch application, two groups of functionality are often confused: **data lifecycle management in the Elasticsearch cluster** and **Spring Data Repository CRUD operations**. Both can affect data, yet they operate at different layers and solve different problems.

Cluster lifecycle management controls indices or data streams throughout their lifetime: when to roll over to a new index, when to move data to another storage tier, when to delete old indices, and when to take snapshots. A Repository is an application-layer abstraction for saving, reading, searching, or deleting documents mapped to Java models.

```text
                Spring Boot application
                ------------------------
                ProductRepository
                ElasticsearchOperations
                         |
                         | document CRUD / query
                         v
                 Elasticsearch cluster
                 ----------------------
                 Index / Data stream
                 Shards / Replicas
                 Aliases
                 ILM / Data Stream Lifecycle
                 SLM / Snapshot repository
```

Repositories send document operations to the cluster. Lifecycle policies are configured on the cluster and executed by Elasticsearch based on index state, age, or conditions. A Repository does not automatically become a retention, rollover, or snapshot scheduler merely because it is declared in the application.

## 1. Two different management layers

| Aspect | Cluster lifecycle management | Spring Data Repository |
|---|---|---|
| Primary target | Indices, data stream backing indices, shards, and snapshots. | Documents mapped to Java entities. |
| Where configured | Elasticsearch cluster settings, lifecycle policies, index templates, and snapshot repositories. | Repository interfaces, entity mappings, query methods, and Spring configuration. |
| Responsibilities | Rollover, moving data tiers, retention, policy-based index deletion, periodic snapshots. | `save`, `findById`, searching, updating, and deleting documents. |
| How triggered | Elasticsearch runs policies on schedule and index state; some actions can be invoked via API. | Application calls repository methods in business flows or application jobs. |
| Scope of impact | Can apply to many indices matching policies or templates. | Data scope of the entity/repository and the index or alias it uses. |
| Application dependency | Policies installed in the cluster continue running even if the Spring application stops. | Requires the application or a component calling the repository to execute operations. |

Example: `ProductRepository.save(product)` writes a product document. An ILM policy can manage `application-logs-*` indices, roll over indices by size, and delete old indices after retention expires. These two responsibilities do not replace each other.

## 2. Repositories manage documents, not the entire index lifecycle

Spring Data Elasticsearch provides a repository abstraction to operate on documents. A repository is commonly declared as:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

The entity specifies the logical index it uses:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // constructors, getters, setters
}
```

If `products` is an alias, the repository can send requests through that alias; Elasticsearch routes to the physical index the alias points to. The repository does not need to know whether the current index is `products-v1` or `products-v2`.

Common operations:

```java
productRepository.save(product);
productRepository.findById("P-100");
productRepository.findAll();
productRepository.deleteById("P-100");
```

These methods operate on documents. They do not define retention policies, automatically roll over indices by size, move shards from hot to warm, or create periodic snapshots.

### `deleteById`, `deleteAll`, and deleting an index are not the same

Clearly distinguish three operation levels:

- `deleteById(id)` deletes the document with the corresponding ID per mapping/repository semantics.
- `deleteAll()` deletes documents within the scope implemented by the repository method; it should not be understood as a command to delete a physical index.
- Deleting an index is an index administration operation, such as calling `IndexOperations.delete()` or the Elasticsearch Indices API `DELETE /<index>`.

Example of index operations via Spring Data:

```java
IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

if (indexOperations.exists()) {
    indexOperations.delete();
}
```

This is an administrative operation that can delete all data in the corresponding index. Do not place it inside normal CRUD flows when the goal is merely deleting a few products. Inspect the actual alias and index the entity points to before calling it.

Implementation details of repository methods and index APIs can change across Spring Data Elasticsearch versions. When you need to know whether a method targets documents, an index, or an alias, verify the contract for your library version and inspect the request sent to Elasticsearch.

## 3. What is cluster lifecycle management?

Elasticsearch provides lifecycle management mechanisms to operate indices over long periods. Policies can be configured once on the cluster and applied to matching indices.

Common requirements:

- Creating a new index when the current index reaches age, size, or document count limits.
- Moving older indices to data tiers matching access frequency.
- Keeping hot data on nodes suited for frequent queries and moving infrequently accessed data to more economical storage tiers.
- Deleting indices after their retention period.
- Creating periodic snapshots so data can be restored when needed.

Primary mechanisms to distinguish:

| Mechanism | Purpose |
|---|---|
| Index Lifecycle Management (ILM) | Manages index lifecycles across phases and actions, such as rollover, migrate, shrink, force merge, and delete. |
| Data Stream Lifecycle | Manages lifecycles of data stream backing indices according to policies supported by the Elasticsearch version. |
| Snapshot Lifecycle Management (SLM) | Schedules snapshot creation and manages snapshot retention inside snapshot repositories. |
| Index template | Applies settings, mappings, aliases, and lifecycle policies to new indices matching a pattern. |

ILM and Data Stream Lifecycle focus on index/data stream lifecycles. SLM manages snapshot backups. A policy deleting an index after 90 days does not mean snapshots of that index are automatically retained or deleted under the same rule; the two lifecycles must be designed separately.

## 4. Index Lifecycle Management (ILM)

ILM allows defining phases in an index's lifecycle. Common phases include:

- **Hot:** new data experiencing high write and read frequency.
- **Warm:** data written less frequently, which may still need regular queries.
- **Cold:** rarely accessed data, prioritizing resource savings.
- **Frozen:** very rarely accessed data, typically using storage mechanisms tailored for sparse queries.
- **Delete:** deletes the index when retention expires.

Available phases and actions depend on Elasticsearch version, node role/data tier configuration, and environment license/features. Not every cluster has the same topology or supports every action.

### Creating an ILM policy

Example policy for log indices: roll over when a primary shard reaches 50 GB or the index reaches 30 days; delete the index after retention expires measured from rollover per the lifecycle policy.

```json
PUT /_ilm/policy/app-logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "50gb",
            "max_age": "30d"
          }
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

A policy is configuration stored on the cluster. Once an index has the policy attached, Elasticsearch monitors conditions and executes corresponding actions. The Spring application does not need to call `deleteAll()` daily to delete expired indices.

### Attaching a policy to an index and rollover alias

An initial index can be created with a lifecycle policy and write alias:

```json
PUT /app-logs-000001
{
  "settings": {
    "index.lifecycle.name": "app-logs-policy",
    "index.lifecycle.rollover_alias": "app-logs"
  },
  "aliases": {
    "app-logs": {
      "is_write_index": true
    }
  }
}
```

The application writes through the `app-logs` alias. When rollover conditions are met, ILM creates the next index and switches the write alias per configuration. The application continues using the stable alias name.

For indices created automatically in the future, configure an index template so lifecycle settings and aliases are applied consistently. Without proper templates or bootstrap setup, new indices may fail to receive the expected policy.

### Monitoring ILM

Inspect the policy:

```http
GET /_ilm/policy/app-logs-policy
```

Inspect lifecycle status of an index:

```http
GET /app-logs-000001/_ilm/explain
```

The explain API helps determine which phase an index is in, which action is running, or why a step is waiting/failing. Do not rely solely on index names or creation times to conclude a policy has executed.

When troubleshooting errors, read explain details and cluster causes first. Elasticsearch provides a retry API for certain failed ILM steps after the root cause is resolved; do not repeatedly retry while the error condition persists.

## 5. Data Stream Lifecycle

Data streams are an append-only way of organizing data, typically suited for time-based logs, metrics, or events. A data stream manages multiple backing indices; applications write to the data stream name instead of picking physical indices themselves.

```text
Application writes events
       |
       v
  Data stream: app-events
       |
       +--> .ds-app-events-...-000001
       +--> .ds-app-events-...-000002
       +--> .ds-app-events-...-000003
```

Data Stream Lifecycle can manage backing index retention according to supported policies. This suits append-only data where most documents have timestamps and are written continuously.

A data stream is not like a repository. The repository only sends documents to the configured index/data stream name; cluster lifecycle policies handle rollover or retention. When choosing between ILM and Data Stream Lifecycle, verify your Elasticsearch version's capabilities and stored data type, avoiding applying two conflicting management mechanisms to the same index stream simultaneously.

## 6. Snapshot Lifecycle Management (SLM)

Deleting indices via retention is not a backup. If an index is deleted accidentally or bad data is written, ILM cannot recover lost data. SLM schedules snapshot creation in snapshot repositories and manages snapshot retention periods.

Example daily snapshot policy:

```json
PUT /_slm/policy/daily-app-logs
{
  "schedule": "0 30 1 * * ?",
  "name": "<app-logs-{now/d}>-snapshot",
  "repository": "my_backup_repository",
  "config": {
    "indices": ["app-logs-*"],
    "ignore_unavailable": true,
    "include_global_state": false
  },
  "retention": {
    "expire_after": "30d",
    "min_count": 5,
    "max_count": 50
  }
}
```

Snapshot repositories must be registered and configured beforehand with supported storage such as a shared filesystem or object storage. Test restores, not just whether snapshot jobs completed successfully. Snapshots are not instantaneous copies of every change after snapshot time; RPO/RTO depend on snapshot schedules, recovery duration, and operational processes.

## 7. Why doesn't a Repository replace ILM?

Suppose an application has a `LogRepository` and needs to keep logs for 90 days. One might think of running a daily job:

```java
logRepository.deleteByTimestampBefore(cutoff);
```

This is conditional document deletion at the application layer. It differs from ILM:

- The repository job must be scheduled and executed by the application. If the job fails to run, data is not deleted.
- The job can generate delete queries over vast numbers of documents, impacting cluster resources and search load.
- The job must handle pagination/batching, retries, partial failures, and progress tracking.
- ILM manages indices by cluster lifecycle state without needing the application to enumerate individual documents to drop old indices.

For time-partitioned logs or events, rollover and deleting old indices are typically far more efficient than deleting individual documents. However, ILM deletes entire indices upon expiration. If individual documents have varying expiration times and cannot be grouped into time buckets/indices, you may need an application job, Delete By Query, or a different storage model.

Elasticsearch does not provide legacy automatic per-document TTL. Declaring an `expiresAt` field on an entity does not make documents disappear automatically. The application must query/delete by that field or organize data into indices/data streams with appropriate lifecycles.

## 8. Choosing ILM, Data Stream Lifecycle, or a Repository job?

| Scenario | Appropriate approach |
|---|---|
| Append-only logs/events stored by day/week and deleted by index age | Data stream with appropriate lifecycle or ILM for time-based indices. |
| Indices needing size-based rollover, data tier migration, and retention deletion | ILM. |
| Periodic backups and backup retention needed | SLM and snapshot repositories. |
| Deleting a single product at user request | Repository `deleteById` or corresponding document operation. |
| Deleting a group of documents by business condition | Repository query/Delete By Query or controlled batch service. |
| Documents have distinct expirations that cannot be grouped into time-based indices | Application job or appropriate document deletion process; do not use ILM as per-document TTL. |
| Changing mappings/analyzers and moving to a new index | Create a new versioned index, reindex, verify, and switch alias. |

A single system can use multiple mechanisms simultaneously: Repositories for business CRUD, ILM for log indices, Data Stream Lifecycle for events, and SLM for snapshots. Clearly define which indices belong to which policy and who owns deploying the configuration.

## 9. Role of `IndexOperations` in Spring Data

Spring Data Elasticsearch provides `ElasticsearchOperations` and `IndexOperations` for index-level tasks such as checking existence, creating/deleting indices, reading mappings/settings, and alias operations per APIs supported by the library version.

Example:

```java
@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean exists() {
        return operations.indexOps(ProductDocument.class).exists();
    }
}
```

`IndexOperations` lets the application perform certain index administration tasks, but it is not an ILM execution engine. Creating policies, attaching policies, checking lifecycle status, and managing snapshots require corresponding cluster APIs or infrastructure deployment tools.

If the application needs to call ILM APIs from Java, you can use the Elasticsearch Java API Client configured in Spring Boot. Policies can also be deployed externally using REST APIs, deployment scripts, or infrastructure-as-code. The choice depends on operational workflows and service account privileges.

### Separating application privileges and admin privileges

An application serving user requests typically only needs read/write permissions on business aliases or indices. It is not necessary to grant index creation/deletion, ILM policy editing, or snapshot deletion rights to every application instance.

You should separate:

- **Runtime application identity:** required document read/write privileges.
- **Index provisioning identity:** privileges to create indices, mappings, templates, and aliases during deployment.
- **Lifecycle administration identity:** privileges to manage ILM, Data Stream Lifecycle, and SLM policies.
- **Snapshot/restore identity:** privileges needed to operate snapshot repositories and restore data.

Separating privileges reduces the chance that a bug in a CRUD endpoint accidentally deletes an index or alters cluster-wide retention.

## 10. Spring bean lifecycle also differs from data lifecycle

Spring has the concept of bean lifecycle: beans are instantiated, dependencies are injected, initialization callbacks run, and beans are destroyed when the ApplicationContext closes. This is the lifecycle of objects inside the JVM.

Elasticsearch index lifecycle is the lifecycle of data resources inside the cluster. These two concepts are independent:

- The `ProductRepository` Spring bean is created when the application starts.
- The `products-v1` index may already exist before the application runs.
- The application can stop while ILM continues processing indices inside the cluster.
- Closing the ApplicationContext does not delete repository data or indices.
- Deleting an index does not destroy the Spring repository bean.

Therefore, do not use `@PostConstruct` or `@PreDestroy` to trigger rollover, retention, or index deletion as a default lifecycle mechanism. Those callbacks are tied to application process lifecycles and can run multiple times as application replicas start and stop.

## 11. Designing Spring Data and lifecycle policy architecture

A clean architecture can divide responsibilities as follows:

```text
                 Deployment / Platform
                         |
             Create templates and policies
                         |
                         v
                Elasticsearch cluster
                ├── Alias / Index templates
                ├── ILM / Data Stream Lifecycle
                └── SLM / Snapshot repository
                         ^
                         |
                 Spring Boot application
                 ├── Repository: document CRUD
                 ├── Operations: mapping/index APIs
                 └── Service: business rules
```

Example with logs:

1. Deployment creates the lifecycle policy and index template for `app-logs-*`.
2. Cluster creates the initial index with write alias or data stream as designed.
3. Spring Boot writes events through the alias/data stream.
4. ILM or Data Stream Lifecycle rolls over and deletes old indices per policy.
5. SLM creates periodic snapshots in the backup repository.
6. Monitoring tracks policy status, shards, storage, and snapshot results.

Repositories do not need to know which date each physical index was created on. They only need to use a stable alias/data stream name and compatible mappings.

## 12. Monitoring and operations

A successfully created policy does not automatically mean data is being managed properly. Actual status must be monitored.

Commonly used APIs:

```http
GET /_ilm/status
GET /_ilm/policy/app-logs-policy
GET /app-logs-000001/_ilm/explain
GET /_data_stream/app-events
GET /_slm/policy/daily-app-logs
GET /_slm/stats
GET /_snapshot/my_backup_repository/_all
```

Meaning:

- `/_ilm/status` reports whether ILM is running or stopped.
- `/_ilm/policy/...` reads the policy definition.
- `/_ilm/explain` explains an index's lifecycle status.
- `/_data_stream/...` inspects the data stream and backing indices.
- `/_slm/policy/...` reads snapshot policy configuration.
- `/_slm/stats` views SLM execution statistics.
- `/_snapshot/.../_all` lists snapshots in the repository.

Beyond these APIs, monitor index counts, primary shard sizes, unassigned shards, disk usage, rollover timing, lifecycle errors, and periodic restore results. A snapshot is truly useful only after the restore process has been tested.

## 13. Common design mistakes

| Practice | Problem | Resolution |
|---|---|---|
| Using `repository.deleteAll()` to replace ILM retention | Application must run its own jobs and delete document-by-document; does not manage shard/index lifecycles. | Use ILM or Data Stream Lifecycle when retention is by index/time bucket. |
| Thinking `expiresAt` automatically deletes documents | Field is just data, not automatic TTL. | Create a document deletion job or partition indices by time. |
| Using ILM to replace snapshot backups | Deleting indices does not create restorable backups. | Configure SLM and test restores separately. |
| Giving every application index-deletion and policy-editing rights | Expands blast radius during bugs or credential leaks. | Separate runtime privileges from admin privileges. |
| Attaching policies to indices manually while forgetting new indices | Rolled-over/new indices may miss the lifecycle policy. | Use index templates/data stream templates and verify new indices. |
| Creating indices on startup of every application replica | Multiple instances perform admin operations concurrently, risking races or unintended configuration. | Manage indices via migrations/provisioning; only enable auto-create when explicitly designed. |
| Deleting old indices immediately after alias switch | Loses rollback path and risks losing unverified data. | Keep old indices for the rollback window and backup policy. |
| Testing only repository CRUD | Fails to catch stopped ILM/SLM or stalled retention. | Monitor cluster lifecycle APIs and snapshot restores. |

## 14. Responsibility selection checklist

Before deploying, answer these questions:

1. Is data stored per document or by time-based indices/data streams?
2. Does retention apply to whole indices or individual documents?
3. Is rollover needed by age, size, or document count?
4. Is moving data across data tiers required?
5. How often must data be backed up and how long are snapshots retained?
6. Which CRUD permissions does the repository actually need? Who is permitted to create/delete indices and modify policies?
7. Are new indices created via templates, migrations, or auto-configuration?
8. How will failed policies, failed snapshots, or indices missing policies be detected?
9. Have restore and rollback procedures been tested?

## 15. Key takeaways

- Repositories are Spring Data abstractions for document operations; they are not cluster index lifecycle management engines.
- `save`, `findById`, and `deleteById` operate on documents; `deleteAll` must not be confused with deleting a physical index.
- `IndexOperations` provides certain index admin operations, but does not replace ILM or SLM.
- ILM manages index rollovers, phases, and retention; Data Stream Lifecycle manages backing index lifecycles for data streams per version capabilities.
- SLM schedules periodic snapshots and manages backup retention; restores must be tested.
- ILM deletes indices according to policy, not individual documents based on an `expiresAt` field.
- Spring bean lifecycle is JVM object lifecycle, distinct from index lifecycle in an Elasticsearch cluster.
- Separate runtime CRUD privileges from index, lifecycle policy, and snapshot administration privileges.
- Aliases/data streams provide stable access names so applications avoid depending on physical index names.

Proper separation of responsibilities lets Spring Data Repositories focus on document business logic, while the Elasticsearch cluster handles long-term index and data operations. When designing a system, clearly define the unit of retention, backup mechanisms, administrative privileges, and monitoring so you avoid substituting CRUD jobs for lifecycle policies or confusing document deletion with index deletion.
