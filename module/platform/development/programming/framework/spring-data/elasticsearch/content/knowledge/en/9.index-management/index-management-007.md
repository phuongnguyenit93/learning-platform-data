# Static Settings, Dynamic Settings, and Update Conditions

An Elasticsearch index has many settings affecting how data is stored, how shards are allocated, how search results are refreshed, and how text is analyzed. Spring Data Elasticsearch can supply settings when creating an index and call APIs to change settings that are permitted to be updated. Before changing a setting, determine its scope, whether it can be changed while the index is open, and whether the change requires reindexing data.

This lesson focuses on **index settings**. These are configurations of a specific index, distinct from mappings that describe field types and indexing behavior, and distinct from cluster settings that apply cluster-wide.

## 1. Settings, Mapping, and Cluster Settings

Elasticsearch organizes index configuration into two major groups:

| Component | Role | Examples |
| --- | --- | --- |
| Index settings | Control how an index operates and is structured. | Number of primary shards, number of replicas, refresh interval, analyzers. |
| Mapping | Define fields, data types, and how fields are indexed. | `text`, `keyword`, `date`, `object`, `nested`. |

In addition, cluster settings control cluster-level or node-level behavior, such as certain shard allocation policies, cluster limits, and operational behaviors. Cluster settings have their own APIs and scope; do not confuse them with index settings just because setting names carry `cluster.*` or `index.*` prefixes.

Examples:

- `index.number_of_replicas` is an index setting.
- `index.refresh_interval` is an index setting.
- `index.analysis.analyzer` defines analyzers belonging to index settings.
- `cluster.routing.allocation.enable` is a cluster-level setting.

Mapping and settings are typically declared together when creating an index, yet they are two separate configuration parts. Changing the replica count does not change field types; changing a mapping from `text` to `keyword` is not an index settings update.

## 2. Static Settings and Dynamic Settings

Elasticsearch classifies index settings by update conditions. Identify the setting category before calling the API.

### 2.1. Dynamic Settings

**Dynamic settings** can be updated while the index is open. After calling the Update Index Settings API successfully, Elasticsearch applies the new value without needing to close the index.

Common examples:

| Setting | Effect |
| --- | --- |
| `index.number_of_replicas` | Number of replica shards per primary shard. |
| `index.refresh_interval` | Periodic interval for changes to refresh and become visible in search. |
| `index.max_result_window` | Result window limit for `from`/`size` pagination queries. |
| `index.routing.allocation.*` | Rules controlling where an index's shards are allocated. |

For example, changing the replica count and refresh interval:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "number_of_replicas": 0,
    "refresh_interval": "30s"
  }
}
~~~

The request above changes the settings of the `products` index while it is open. Setting replicas to `0` is typically appropriate for a single-node learning cluster, because there is no second node to allocate replicas to. In a multi-node cluster, replica count should be chosen according to availability and fault-tolerance requirements.

A larger `refresh_interval` can reduce refresh frequency and improve write throughput, though new data appears in search more slowly. Setting `-1` disables periodic refreshes; in that case, the application must explicitly refresh if it wants to find newly written data during testing. Do not change this setting without understanding its impact on search latency.

### 2.2. Static Settings

**Static settings** usually can only be changed when the index is closed, or can only be declared at index creation time. Exact conditions depend on the setting.

Some static settings can be updated after closing the index. For example, analyzer configurations in `index.analysis` typically require closing the index before updating. General sequence:

1. Close the index.
2. Send the permitted settings update.
3. Reopen the index.
4. Check index status and application behavior.

API example:

~~~http
POST /products/_close
~~~

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "analysis": {
      "analyzer": {
        "catalog_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  }
}
~~~

~~~http
POST /products/_open
~~~

This illustrates the workflow for modifying analyzer settings. The analyzer must be properly referenced in field mappings, and the new configuration should be tested with `_analyze`. Closing an index interrupts read/write/search operations on that index during the update window; plan this operation accordingly.

### 2.3. Static Does Not Mean Modifiable When Closed

Some settings are **final/immutable** after the index has been created. Closing the index does not make them updatable.

The most important example is `index.number_of_shards`: the number of primary shards is decided at index creation time and cannot be changed via the Update Index Settings API afterward, even when the index is closed.

If you need to change the number of primary shards, choose an appropriate data migration strategy, such as:

- Creating a new index with the desired shard count and reindexing data into the new index.
- Using split index when split conditions are met and initial routing shards allow it.
- Using shrink index when reducing primary shards and shrink conditions are satisfied.

Do not send a request updating `number_of_shards` expecting close/open index to solve it. Design an index transition and verify data before switching aliases or application configuration.

## 3. Viewing Current Settings

Before updating, read the existing configuration:

~~~http
GET /products/_settings
~~~

To view default values applied by Elasticsearch as well:

~~~http
GET /products/_settings?include_defaults=true
~~~

The response is structured by index and contains setting values. When reading the result, distinguish explicitly declared values from default values provided by Elasticsearch. Do not blindly copy the entire settings output and send it back, because the payload may contain internal values or settings that do not need changing.

You can read specific settings by filtering setting names in the API or filtering the response on the client side, depending on inspection needs.

## 4. Creating an Index with Settings from the Start

For static or final settings, the safest approach is declaring desired values when creating the index. For example, creating the `products` index with one primary shard, zero replicas, and a custom analyzer:

~~~http
PUT /products
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "catalog_text"
      },
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

The index is created with full settings and mapping in a single request. This avoids creating an index first with default configuration and later having to alter settings that should be decided upfront.

When designing an index for real environments, shard count should be based on data size, read/write throughput, cluster topology, and growth plans. Do not choose shard counts out of habit or copy them from learning environments.

## 5. Updating Dynamic Settings with the REST API

Example changing `refresh_interval` while the index is open:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index.refresh_interval": "5s"
}
~~~

You can send one or more settings in the same request. Include only the settings that genuinely need to change in the payload. Elasticsearch checks the caller's permissions and value validity before applying.

To check after updating:

~~~http
GET /products/_settings?filter_path=*.settings.index.number_of_replicas,*.settings.index.refresh_interval
~~~

A dynamic setting update succeeding does not mean every change takes effect instantaneously across all nodes. Changing replica count can trigger shard allocation and synchronization; monitor cluster health and allocation until the system reaches the desired state.

## 6. Updating Static Settings That Require Closing the Index

For settings permitted to be updated when the index is closed, the workflow can run as follows:

~~~http
POST /products/_close
~~~

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding", "trim"]
        }
      }
    }
  }
}
~~~

~~~http
POST /products/_open
~~~

When operating manually, verify the index is closed before sending settings and reopen it after the update succeeds. If the update request fails, check the index state and handle it so the index is not left closed accidentally.

Changing an analyzer definition does not re-analyze previously indexed data. The new analyzer can be used for subsequent indexing or searches per the corresponding configuration, but existing tokens in the inverted index were still produced by the previous analyzer. To change index-time analysis for all data, reindex into a new index.

Some search analyzers may support reloading separately, such as when using synonym filters designed for reloading. This is a specialized mechanism per filter type and Elasticsearch version; do not assume all static settings can be reloaded while the index is open.

## 7. Conditions to Check Before Updating

Not all settings share the same conditions. Before calling the API, verify the following points:

| Condition | Question to Answer |
| --- | --- |
| Scope | Is this an index setting, mapping, or cluster setting? |
| Setting category | Dynamic, static but updatable when closed, or final/immutable? |
| Index state | Does the index need to be closed? Are applications currently depending on it? |
| Permissions | Does the account have privileges to manage index settings? |
| Compatibility | Are the setting and value supported by the current Elasticsearch version? |
| Data | Does the change alter how existing data is indexed? Is reindexing needed? |
| Operational impact | Will it cause shard relocation, downtime, or increased load? |
| Rollback capability | Have old values and a recovery plan been recorded? |

Notably, settings that can be updated while an index is open can still have performance impacts. For example, lowering refresh frequency increases search latency; increasing replicas increases storage usage and network load; changing allocation can move shards across nodes.

## 8. Settings in Spring Data Elasticsearch

Spring Data Elasticsearch can provide settings when creating an index via entity metadata. The `@Setting` annotation lets you specify a settings file on the classpath.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products")
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "catalog_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructors, getters, and setters
}
~~~

The file `src/main/resources/elasticsearch/products-settings.json` can contain settings like:

~~~json
{
  "index": {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  }
}
~~~

When Spring Data creates the index from entity metadata, settings from the file are applied along with the corresponding mapping. `@Field(analyzer = "catalog_text")` references the analyzer declared in settings.

`@Setting` describes configuration for the index creation step. It is not an automatic migration mechanism to update existing indexes every time the application starts. If the index was already created beforehand, editing the settings file does not automatically alter the running index's configuration.

## 9. Updating Settings via `IndexOperations`

`ElasticsearchOperations` provides `IndexOperations` to manage indexes from Java code. You can obtain the operations instance for an entity:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void inspectIndex() {
        IndexOperations indexOperations = operations.indexOps(Product.class);
        boolean exists = indexOperations.exists();

        if (exists) {
            var currentSettings = indexOperations.getSettings(false);
            // Record or verify the required settings
        }
    }
}
~~~

For dynamic settings, you can create a `Document` containing the values to update and call `putSettings`. Illustrative example for the Spring Data Elasticsearch 5.x API:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.IndexOperations;

IndexOperations indexOperations = operations.indexOps(Product.class);

Document updateSettings = Document.parse("""
    {
      "index": {
        "number_of_replicas": 0,
        "refresh_interval": "10s"
      }
    }
    """);

indexOperations.putSettings(updateSettings);
~~~

Method names and parameter types can differ across Spring Data Elasticsearch versions. Use the API corresponding to your project's dependency version. The principle remains the same as the REST API: `putSettings` sends the settings to be changed; it does not turn a final setting into an updatable one.

For changes requiring the index to be closed, coordinate the close, put settings, and open operations explicitly using `IndexOperations` or the appropriate REST API. Do not put this sequence inside application startup logic without controlling downtime and error handling.

## 10. Settings and Index Lifecycle

Settings are typically applied at different points in time:

~~~mermaid
flowchart TD
    A["Design index"] --> B["Declare settings and mapping"]
    B --> C["Create index"]
    C --> D["Write and search documents"]
    D --> E{"Need to change setting?"}
    E -->|No| D
    E -->|Yes| F{"Setting type?"}
    F -->|Dynamic| G["Update while index is open"]
    F -->|Modifiable static| H["Close index"]
    H --> I["Update setting"]
    I --> J["Open index"]
    F -->|Final/immutable| K["Create new index or use split/shrink if appropriate"]
    G --> L["Verify settings and cluster health"]
    J --> L
    K --> M["Migrate data / switch alias"]
    L --> D
    M --> D
~~~

For important indexes, manage changes via versioned migrations rather than ad-hoc manual updates. A migration should know the current state, target values, update conditions, verification steps, and how to recover if the operation fails.

## 11. Reindexing When Changing Analysis or Structure

Some changes only affect operational behavior, while others affect how documents are indexed. Distinguish them:

| Change | Is Reindexing Needed? |
| --- | --- |
| Increasing `number_of_replicas` | No reindexing needed; Elasticsearch allocates additional replicas. |
| Changing `refresh_interval` | No reindexing needed. |
| Adding or changing an index-time analyzer definition | Usually requires reindexing so tokens of old documents are regenerated using the new analyzer. |
| Changing the mapping type of an existing field | Usually requires a new index and reindexing. |
| Changing primary shard count by creating a new index | Requires migrating data to the new index or using split/shrink operations where appropriate. |

Example creating a new index with new settings and mapping:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 0,
    "analysis": {
      "analyzer": {
        "catalog_text_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "catalog_text_v2"
      },
      "sku": { "type": "keyword" }
    }
  }
}
~~~

Migrating data:

~~~http
POST /_reindex
Content-Type: application/json

{
  "source": {
    "index": "products"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Reindex copies documents from source to destination; it does not automatically create desired destination settings or mappings. Therefore, `products-v2` must be created beforehand with the necessary settings/mapping. For systems continuously receiving writes, plan how to sync changes occurring during reindexing before switching aliases or application endpoints.

## 12. Checking and Verifying After Updating

After every change, verify both configuration and behavior:

1. Read back settings via `GET /<index>/_settings`.
2. Confirm the index is open and in the expected state.
3. Check cluster health and shard allocation if replicas or allocation changed.
4. If an analyzer changed, run `_analyze` to verify the new tokens.
5. Test writing and searching a representative document.
6. Confirm the Spring Data application connects to the right index/alias.
7. Record old values, new values, and migration results for traceability.

Do not treat a successful HTTP status as the sole proof. For example, updating replicas may succeed while shards are still allocating; an analyzer change may be saved while old documents still hold old tokens.

## 13. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Settings update rejected because index is open | The setting requires the index to be closed. | Check setting category, close index per plan, update, and reopen. |
| Updating `number_of_shards` fails | It is a final setting after index creation. | Create a new index, reindex, or use split/shrink if conditions are met. |
| Index fails to reopen after update | New setting is invalid or an operational error occurred on reopen. | Read response and logs, fix cause, and reopen; confirm state before finishing migration. |
| Changed analyzer but old results do not change | Old documents still have tokens created by the old analyzer. | Reindex data into a new index with the new analyzer. |
| Application starts but settings do not change | `@Setting` is only used at index creation; index already exists. | Manage updates via migrations or `IndexOperations`/REST API. |
| Replicas remain unassigned | Cluster lacks suitable nodes, allocation is restricted, or nodes lack resources. | Check `_cluster/health`, allocation explain, and cluster configuration. |
| Refresh interval changed but search still lags | New value was not verified properly, refresh is disabled, or request needs explicit refresh. | Re-read setting and check refresh/search visibility. |

## 14. Safe Settings Management Workflow

When preparing an index settings change, follow this sequence:

1. Identify the actual index or alias the application uses.
2. Read current settings and save relevant values.
3. Look up update conditions for each setting in your running Elasticsearch version.
4. Classify as dynamic, static updatable when closed, or final/immutable.
5. Determine whether closing the index, reindexing, splitting, or shrinking is needed.
6. Assess impact on search, writes, shard allocation, storage, and downtime.
7. Prepare new values, update commands, verification steps, and rollback plan.
8. Apply the change in a migration or appropriate maintenance window.
9. Re-read settings, verify cluster health, and test application operations.
10. Switch aliases or finalize the release only when the new index meets requirements.

In Spring Data Elasticsearch, `@Setting` helps declare settings for index creation, while `IndexOperations` provides APIs to read and update indexes in code. Actual update permissions remain governed by Elasticsearch: dynamic settings can be changed while the index is open, some static settings require closing the index, and final settings such as primary shard count must be decided at index creation or handled through a data migration strategy.
