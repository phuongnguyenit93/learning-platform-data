# Index Templates, Component Templates, and Supported API Scope

When a Spring Data Elasticsearch application creates multiple indexes, repeating settings and mappings for each index easily leads to inconsistent configurations. Elasticsearch provides **index templates** to apply a shared configuration to new indexes whose names match a pattern. With composable index templates, configuration can be split into small, reusable **component templates** combined in order.

Spring Data Elasticsearch supports working with indexes, mappings, settings, and aliases through abstractions like `IndexOperations`. However, managing composable index templates and component templates belongs to a cluster-level group of Elasticsearch APIs. It is important to distinguish which parts belong to the Spring Data API, which belong to the Elasticsearch Java API Client, and which are native Elasticsearch REST APIs.

This lesson explains the structure of index templates, component templates, how templates are selected by pattern and priority, how to simulate results before creating an index, how to use templates with data streams, and the scope of APIs usable from a Spring Boot application.

## 1. Why Are Index Templates Needed?

Suppose a logging system creates daily indexes:

```text
app-logs-2026.11.12
app-logs-2026.11.13
app-logs-2026.11.14
```

Each index needs the same mapping for the fields `@timestamp`, `level`, `service`, and `message`. If the application had to send identical settings and mappings every time an index was created, configuration would be duplicated across multiple places. A new index could accidentally miss a mapping, use the wrong shard count, or have different field types from earlier indexes.

Index templates solve this by defining a set of settings, mappings, and aliases applied to subsequently created indexes whose names match `index_patterns`.

Conceptual example:

```text
Index template: app-logs-template
index_patterns: ["app-logs-*"]
        |
        +----> app-logs-2026.11.12
        +----> app-logs-2026.11.13
        +----> app-logs-2026.11.14
```

When a new index is created, Elasticsearch finds the matching template, merges the template configuration with the index creation configuration, and creates the index from the final result. Templates standardize configuration across a group of indexes without repeating the entire mapping in every `PUT index` command.

## 2. Composable Index Templates and Component Templates

Modern Elasticsearch provides composable index templates. This structure splits templates into two layers:

- **Component template** holds a reusable piece of settings, mappings, or aliases.
- **Composable index template** specifies index patterns, priority, and how component templates are combined to produce a complete configuration for new indexes.

A component template does not apply to an index merely because it exists. It is only used when referenced in `composed_of` of a composable index template.

```text
Component template: common-settings ----+
                                         |
Component template: event-mappings ------+--> Composable index template
                                         |        index_patterns: events-*
Component template: common-aliases ------+        priority: 300
                                                  |
                                                  v
                                         New index: events-2026.11
```

Splitting configuration allows sharing settings across multiple index groups, sharing standard mappings across applications, and updating parts without duplicating entire templates.

### 2.1. What Does a Component Template Contain?

Component templates are created using the Cluster API:

```http
PUT _component_template/common-event-settings
{
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    }
  },
  "version": 1,
  "_meta": {
    "description": "Common settings for event indices"
  }
}
```

Example component template containing only mapping:

```http
PUT _component_template/common-event-mappings
{
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "message": {
          "type": "match_only_text"
        },
        "level": {
          "type": "keyword"
        }
      }
    }
  },
  "version": 1,
  "_meta": {
    "description": "Common mapping for event documents"
  }
}
```

A component template can contain `settings`, `mappings`, and `aliases` inside the `template` object. The `version` and `_meta` fields help manage versioning and descriptive metadata; they do not replace settings or mappings.

A component template has no `index_patterns` and does not independently pick which indexes receive the configuration. Index selection belongs to composable index templates.

### 2.2. Composable Index Template Combining Component Templates

Create an index template referencing the declared components:

```http
PUT _index_template/app-events-template
{
  "index_patterns": ["app-events-*"],
  "priority": 300,
  "composed_of": [
    "common-event-settings",
    "common-event-mappings"
  ],
  "template": {
    "settings": {
      "number_of_replicas": 0
    },
    "aliases": {
      "app-events-read": {}
    }
  },
  "version": 1,
  "_meta": {
    "owner": "catalog-platform",
    "purpose": "Template for application event indices"
  }
}
```

In this example:

- `index_patterns` selects indexes whose names start with `app-events-`.
- `priority` determines precedence when multiple composable index templates match.
- `composed_of` lists the component templates to merge in.
- `template` holds configuration specific to the index template, which can extend or override configuration from component templates.
- `version` and `_meta` store administrative metadata.

When creating `app-events-2026.11`, Elasticsearch uses the matching template and creates the index with the merged configuration. In the example, component settings set `number_of_replicas` to `1`, while the index template's `template.settings` sets it to `0`; values in the index template's own configuration are applied after the components and override duplicate keys.

## 3. Configuration Merge Order

When Elasticsearch applies a composable index template, configuration order matters:

1. Component templates in `composed_of` are applied in the order declared.
2. The `template` section of the composable index template is applied last.
3. Configuration sent directly in the create-index request can override corresponding values from the template.

If two components declare the same setting or define overlapping parts of a mapping, the later component can override overlapping parts according to Elasticsearch's merge rules. The `template` section of the composable index template takes higher precedence than composed components.

Example:

```text
common-settings
  number_of_replicas = 1
          |
          v
environment-settings
  number_of_replicas = 0
          |
          v
index template's template
  number_of_replicas = 2
          |
          v
Create index request
  number_of_replicas = 3
          |
          v
Final index setting = 3
```

Avoid having multiple components define the same field mapping with different data types. A field cannot be both `keyword` and `date` in the same mapping. Designing components with clear responsibilities reduces conflicts and makes configuration sources easy to trace.

## 4. `index_patterns` and `priority`

`index_patterns` is a list of patterns used to identify index names matched by the template. Patterns commonly use the `*` wildcard.

Examples:

| Pattern | Example Matching Index Names |
|---|---|
| `app-logs-*` | `app-logs-2026.11.13` |
| `orders-*` | `orders-v1`, `orders-2026.11` |
| `metrics-prod-*` | `metrics-prod-host-01` |

Make patterns specific enough to avoid a template accidentally applying to indexes belonging to other applications.

If multiple composable index templates match a new index name, Elasticsearch picks the template with the highest `priority`. Lower-priority composable index templates are not automatically merged into the winning template. To reuse configuration across multiple sources, place shared pieces into component templates and reference them in `composed_of`.

Example with two index templates:

```http
PUT _index_template/all-app-template
{
  "index_patterns": ["app-*"],
  "priority": 100,
  "template": {
    "settings": {
      "number_of_replicas": 1
    }
  }
}
```

```http
PUT _index_template/app-logs-template
{
  "index_patterns": ["app-logs-*"],
  "priority": 300,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    }
  }
}
```

When creating `app-logs-2026.11.13`, both patterns match, but `app-logs-template` has higher priority and is selected. Settings from `all-app-template` are not automatically merged in. If shared settings are needed, move the shared part into a component template and reference it from `app-logs-template`.

Priority is an integer value; if omitted, Elasticsearch defaults to `0`. Establish priority range conventions in your organization to avoid a new template unintentionally overriding another template. Some system templates or templates managed by hosted services may use reserved priorities; check the documentation for your running version and product before setting priorities near reserved ranges.

## 5. When Are Templates Applied?

An index template is applied when a new index is created and its name matches the pattern. The index can be created explicitly via the Create Index API or auto-created on document write if auto-create configuration permits.

Templates do not automatically update already-existing indexes. If you change a mapping or settings in a template, old indexes do not automatically receive the new configuration. To change an existing index, use mapping/settings update APIs if Elasticsearch allows it, or create a new index and reindex data according to a migration workflow.

For example, after editing the `common-event-mappings` component template, the already-existing index `app-events-2026.10` does not automatically change its mapping. A new index like `app-events-2026.11` can receive the new mapping upon creation.

This is especially important for mappings. Elasticsearch generally does not permit changing an already-indexed field's type from `text` to `keyword` or from `keyword` to `date` in place on the same index. Manage index versions and aliases to deploy non-disruptive changes.

## 6. Inspecting Stored Templates and Configurations

Retrieve a component template:

```http
GET _component_template/common-event-settings
```

Retrieve a composable index template:

```http
GET _index_template/app-events-template
```

List all component templates:

```http
GET _component_template
```

List all composable index templates:

```http
GET _index_template
```

These APIs help confirm the template was created, names referenced in `composed_of` are accurate, and patterns/priorities match the design.

If a template references a nonexistent component template, creating or updating the index template may fail unless the request is explicitly configured to ignore missing components. In a standard workflow, create component templates first, then create the composable index template referencing them.

## 7. Simulating a Template Before Creating an Index

Elasticsearch provides the Simulate Index Template API to preview the merged configuration a template will produce. This is a useful step before applying a template to real indexes.

### 7.1. Simulating a Template Definition

You can submit an unsaved template definition to inspect the output:

```http
POST _index_template/_simulate
{
  "index_patterns": ["app-events-*"],
  "priority": 300,
  "composed_of": [
    "common-event-settings",
    "common-event-mappings"
  ],
  "template": {
    "settings": {
      "number_of_replicas": 0
    }
  }
}
```

The response shows the settings, mappings, and aliases after components are merged. Use the output to spot missing configurations or unexpected overrides.

### 7.2. Simulating a Saved Template by Name

You can simulate a saved composable index template by its name:

```http
POST _index_template/_simulate/app-events-template
```

The response reveals the merged configuration of that template. When investigating conflicts, note information about other templates with overlapping patterns if your version's response includes it.

### 7.3. Simulating Configuration for a Specific Index Name

To find out which template will be selected for a specific index, use the Simulate Index API:

```http
POST _index_template/_simulate_index/app-events-2026.11.13
```

This API is helpful when multiple templates share patterns. It checks which template is selected and the final configuration before sending an index creation command.

Simulating does not create an index and does not replace real cluster verification. Nor does it prove that all subsequent document write requests will succeed; access permissions, ingest pipelines, cluster resources, and input data can still cause separate errors.

## 8. Creating an Index and Verifying Template Application

Once the template is saved and simulated properly, create a new index:

```http
PUT app-events-2026.11.13
```

Check settings:

```http
GET app-events-2026.11.13/_settings
```

Check mapping:

```http
GET app-events-2026.11.13/_mapping
```

Check aliases:

```http
GET app-events-2026.11.13/_alias
```

The actual result is the final confirmation for the created index. If settings or mappings do not match expectations, review patterns, priority, component order, and overrides in the `template` section. Also check whether the index already existed beforehand; templates only apply upon creation.

## 9. Using Index Templates with Data Streams

A data stream is an Elasticsearch abstraction for append-only time-series data such as logs, metrics, or events. A data stream manages underlying backing indices and routes writes to the current write index.

To create a data stream, you need a composable index template matching the stream name and containing the `data_stream` property. The mapping must include an appropriate timestamp field, normally `@timestamp` of type `date`.

Example:

```http
PUT _index_template/app-logs-stream-template
{
  "index_patterns": ["app-logs-*"],
  "priority": 500,
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_replicas": 1
    },
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "message": {
          "type": "match_only_text"
        }
      }
    }
  }
}
```

Create the data stream:

```http
PUT _data_stream/app-logs-api
```

Write a document:

```http
POST app-logs-api/_doc
{
  "@timestamp": "2026-11-13T09:30:00Z",
  "service": "catalog-api",
  "message": "Application started"
}
```

Data streams require a timestamp field per Elasticsearch rules. Backing indices are created according to the data stream's lifecycle; the application writes via the data stream name instead of managing individual backing index names itself.

### 9.1. Regular Templates vs. Data Stream Templates

| Characteristic | Regular Index | Data Stream |
|---|---|---|
| How writes work | Write to a specific index name or alias | Write to the data stream name |
| Structure | A standalone index | A stream comprising multiple backing indices |
| Timestamp | Not required for every index | Requires a timestamp field per data stream rules |
| Rollover | Can be managed via aliases/ILM | Built into the data stream lifecycle |
| Template | Standard composable index template | Composable index template with `data_stream` |

Do not declare `data_stream` on a template if that pattern is used to create regular indexes. Separate patterns and templates for the two purposes to avoid confusion when creating resources.

## 10. Aliases in Index Templates

Index templates can declare aliases so new indexes automatically join a shared alias.

Example:

```http
PUT _index_template/orders-template
{
  "index_patterns": ["orders-v*"],
  "priority": 300,
  "template": {
    "mappings": {
      "properties": {
        "status": {
          "type": "keyword"
        },
        "createdAt": {
          "type": "date"
        }
      }
    },
    "aliases": {
      "orders-read": {}
    }
  }
}
```

When creating `orders-v1`, the `orders-read` alias is attached automatically. When creating `orders-v2`, that alias is also attached to the new index if the template still matches.

Templates keep alias declarations consistent, though they do not execute the entire read/write alias switch workflow during migration. During migration, use the Aliases API to point the alias to the new index and remove it from the old index in an appropriate operation.

## 11. Managing Templates When Using Spring Data Elasticsearch

Spring Data Elasticsearch has abstractions for operations on a specific index. You can obtain `IndexOperations` from `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class OrderIndexService {

    private final ElasticsearchOperations operations;

    public OrderIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean indexExists() {
        IndexOperations indexOperations = operations.indexOps(
                IndexCoordinates.of("orders-v1"));
        return indexOperations.exists();
    }
}
```

`IndexOperations` focuses on the lifecycle and metadata of a specific index. Common operations, depending on the Spring Data Elasticsearch version, include:

- Checking index existence (`exists`).
- Creating and deleting indexes (`create`, `delete`).
- Creating or retrieving mappings (`createMapping`, `getMapping`).
- Updating mappings (`putMapping`).
- Reading/updating settings (`getSettings`, `putSettings`).
- Refreshing the index.
- Working with aliases.

These APIs are suited when the application needs to operate on a known index. They should not be confused with the full Cluster API for managing component templates and composable index templates.

### 11.1. Entity Annotations Do Not Replace Index Templates

Spring Data Elasticsearch allows declaring index metadata on entities:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders-v1", createIndex = true)
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private java.time.Instant createdAt;
}
```

`@Document`, `@Field`, `@Setting`, or `@Mapping` describe metadata and configuration attached to an entity/index via Spring Data's mechanism. They do not automatically create reusable component templates or composable index templates on the cluster.

If Elasticsearch already has an index template matching the index name, the template is applied by Elasticsearch when Spring Data creates the new index. Spring Data does not need to read the template and merge components itself; that is Elasticsearch's responsibility when handling the Create Index API.

Conversely, if the index already exists, `createIndex = true` does not mean Spring Data will delete the old index and recreate it to apply a new template. Modifying existing indexes requires a separate migration workflow.

### 11.2. API Scope of Spring Data and Elasticsearch

Three API layers should be distinguished:

| API Layer | Primary Scope | Used for Templates? |
|---|---|---|
| Spring Data `IndexOperations` | Creating/deleting a specific index, mappings, settings, aliases, refresh | Do not assume it includes full composable/component template management APIs; check the interface of your release train |
| Elasticsearch Java API Client | Official Java client for Elasticsearch REST APIs, including APIs in cluster and indices namespaces | Can use corresponding requests to manage component templates, index templates, and simulate |
| Elasticsearch REST API | All endpoints supported by that server version | The most direct and explicit way to manage templates, data streams, and simulations |

In common Spring Data Elasticsearch release trains, `IndexOperations` is the abstraction for index-level operations. Index templates and component templates belong to Elasticsearch's cluster/index template management APIs. If your Spring Data version does not provide dedicated abstractions for these APIs, the application can:

- Use the Elasticsearch Java API Client configured alongside Spring Boot to call the corresponding endpoints.
- Call the Elasticsearch REST API from a separate deployment or migration tool.
- Manage templates via infrastructure-as-code or operational pipelines before the application begins writing data.

Do not assume an `IndexOperations` method can create a component template just because it can create an index or mapping. Check the Javadoc and API of the exact Spring Data Elasticsearch version in your project.

## 12. Calling Template APIs from the Elasticsearch Java API Client

Spring Boot / Spring Data Elasticsearch uses the Elasticsearch Java API Client in modern versions. When you need to manage templates from Java, you can inject `co.elastic.clients.elasticsearch.ElasticsearchClient` and call the corresponding API on the client.

Example service structure:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ElasticsearchTemplateAdminService {

    private final ElasticsearchClient client;

    public ElasticsearchTemplateAdminService(ElasticsearchClient client) {
        this.client = client;
    }

    // Use client.cluster().putComponentTemplate(...)
    // and client.indices().putIndexTemplate(...)
    // with request types from the matching Elasticsearch Java API Client version.
}
```

Endpoints map to the corresponding API groups:

- Component templates: Cluster API, such as `cluster().putComponentTemplate(...)`, `cluster().getComponentTemplate(...)`, and `cluster().deleteComponentTemplate(...)`.
- Composable index templates: Indices API, such as `indices().putIndexTemplate(...)`, `indices().getIndexTemplate(...)`, and `indices().deleteIndexTemplate(...)`.
- Template simulation: Indices API with the client version's corresponding simulate requests.

Request classes and builders are generated per Elasticsearch Java API Client version. Type structures for `settings`, `mappings`, `aliases`, `composed_of`, and `data_stream` may vary across client releases. Use request types from the exact dependency managed by Spring Boot/Spring Data, rather than adding an incompatible major client version to the classpath.

If templates are managed by the deployment workflow, it is usually best to let an administrative pipeline create/update templates using the REST API or infrastructure tooling. The runtime application only needs read/write permissions on required indexes; it does not necessarily need cluster-level permissions to modify templates.

## 13. Commonly Used Template Management APIs

Key REST endpoints:

| Purpose | Endpoint |
|---|---|
| Create/update component template | `PUT _component_template/{name}` |
| Read component template | `GET _component_template/{name}` |
| List component templates | `GET _component_template` |
| Delete component template | `DELETE _component_template/{name}` |
| Create/update composable index template | `PUT _index_template/{name}` |
| Read composable index template | `GET _index_template/{name}` |
| List composable index templates | `GET _index_template` |
| Delete composable index template | `DELETE _index_template/{name}` |
| Simulate template definition | `POST _index_template/_simulate` |
| Simulate saved template | `POST _index_template/_simulate/{name}` |
| Simulate template for index name | `POST _index_template/_simulate_index/{index}` |

Template APIs require appropriate cluster privileges. A service account with only document indexing permissions may lack privileges to create or delete templates. Separate template administration privileges from runtime privileges in production deployments.

There are also APIs for legacy index templates and dedicated APIs for data streams. For new development, prefer composable index templates and check documentation for the running Elasticsearch server version.

## 14. Legacy Index Templates and Composable Templates

Elasticsearch previously offered legacy index templates via the `_template` endpoint. Composable index templates were introduced to address composing component templates, priority control, and clearer configuration management.

| Legacy Template | Composable Template |
|---|---|
| `_template/{name}` API | `_index_template/{name}` API |
| No component template composition under the new model | Uses `composed_of` to compose component templates |
| Older priority/merging mechanism | Uses `priority` to pick the single best-matching composable template |
| Legacy management structure | Better suited for modern template design and data streams |

Legacy templates have been deprecated in modern Elasticsearch versions after composable templates were introduced. Exact support or removal status depends on the server version. For new systems, use `_index_template` and `_component_template`; for older clusters, check upgrade documentation before converting.

Do not maintain both models in parallel without understanding precedence rules between them. When migrating, list legacy templates, review patterns, convert needed configurations to component/composable templates, simulate results, and verify new indexes before removing legacy configurations.

## 15. Managing Template Changes and Index Migrations

Templates configure indexes created in the future. When changing a template, plan for both new indexes and existing indexes.

Example changing the `customerCode` mapping from `text` to `keyword`:

1. Create a new version of the component template with `customerCode` mapped as `keyword`.
2. Update the composable index template to reference the new component.
3. Use the Simulate Index API with the planned index name to confirm the mapping.
4. Create a new index, such as `orders-v2`.
5. Reindex data from `orders-v1` to `orders-v2` if historical data must be retained.
6. Verify documents, mappings, and queries on the new index.
7. Switch read/write aliases to the new index using the Aliases API.
8. Only delete the old index after verifying migration and retention policy allows it.

Set `version` and `_meta` on component/index templates to track changes. You can store template definitions as JSON/YAML in a repository and deploy via pipeline, giving mapping changes history and reviewability.

Do not use `PUT _index_template` as an operation to fix mappings across all existing indexes. Updating a template does not run a migration and does not alter already-indexed data.

## 16. Access Permissions and Operations

Creating or deleting templates is a cluster administration operation. Assign privileges by role:

- **Template administrator/deployment pipeline:** holds privileges to manage component templates, index templates, and data streams if needed.
- **Application runtime:** holds read/write privileges on specific indexes or data streams.
- **Read-only analyst:** only holds search/read permissions on appropriate data.

Do not grant cluster-wide template management privileges to every application merely because it uses Spring Data Elasticsearch. Template changes can affect many subsequently created indexes, so changes must be reviewed and controlled.

In multi-team environments, name component templates by shared scope and clear ownership. Avoid overly broad component templates that could inadvertently alter mappings across unrelated index groups.

## 17. Pre-Release Template Verification Workflow

A reliable deployment workflow can include:

1. Identify the index pattern or data stream to target.
2. Split settings, mappings, and aliases into component templates by responsibility.
3. Create the composable index template with `index_patterns`, `priority`, `composed_of`, and custom template overrides.
4. Inspect saved component templates and index templates.
5. Call `_simulate` to check the merged configuration result.
6. Call `_simulate_index/{index}` to identify which template is chosen for a specific index name.
7. Create a test index and read back `_settings`, `_mapping`, and `_alias`.
8. Verify the Spring Data Elasticsearch application can write/read documents with the new mapping.
9. Deploy the template before the application begins creating new indexes.
10. For incompatible changes, create a new versioned index, reindex, and switch aliases per the migration workflow.

## 18. Summary

Composable index templates define which indexes receive configuration via `index_patterns` and `priority`. Component templates split settings, mappings, and aliases into reusable pieces; index templates combine them through `composed_of` and add specific overrides in `template`. When multiple composable templates match, the one with the highest priority wins; lower-priority templates are not merged automatically.

Templates are applied only when creating a new index or creating a new backing index in a data stream's lifecycle. Modifying a template does not automatically alter existing indexes. Simulate APIs let you preview the merged result and winning template before creating real resources.

In Spring Data Elasticsearch, `IndexOperations` primarily manages a specific index's mapping, settings, and aliases. Managing component templates, composable index templates, and simulations belongs to Elasticsearch's APIs; applications can use the Elasticsearch Java API Client or REST API matching the server/client version. Clearly distinguishing these API layers helps pick the right tool, avoid relying on an abstraction that lacks full support, and manage templates safely across the index lifecycle.
