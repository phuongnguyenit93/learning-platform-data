# Preventing Unintended Mapping Creation in Deployment Environments

Elasticsearch can automatically create indexes and infer mappings when receiving new documents, depending on server and application configuration. This is convenient in test environments, but can cause risks during deployment: an index created with the wrong name, fields given unwanted data types, uncontrolled mapping growth, or the application accidentally writing data into an unprepared index.

Spring Data Elasticsearch and Elasticsearch have separate mechanisms to control this. To prevent unintended mapping creation, clearly distinguish:

1. Whether Spring Data automatically creates indexes/mappings when initializing repositories.
2. Whether Elasticsearch automatically creates an index when receiving a write command to a nonexistent index.
3. Whether Elasticsearch automatically adds fields to the mapping of an existing index.
4. Who is responsible for creating indexes, settings, mappings, and aliases during deployment.

## 1. Distinguishing Three Automatic Mechanisms

Three behaviors are frequently confused:

| Mechanism | When Does It Happen? | How to Control |
|---|---|---|
| Spring Data creates index and mapping | When Spring Data infrastructure/repositories initialize and the declared index does not exist | `@Document(createIndex = false)` |
| Elasticsearch auto-creates index | When a write request targets a nonexistent index and the cluster allows auto-create | Cluster setting `action.auto_create_index` |
| Elasticsearch auto-adds fields to mapping | When a document has a new field in an existing index and the mapping allows dynamic mapping | `dynamic: strict`, `dynamic: false`, dynamic templates |

These three mechanisms are independent. For example, disabling index creation in Spring Data does not automatically prevent Elasticsearch from creating an index when the application sends a write request to a nonexistent index name. Likewise, blocking index auto-create does not stop dynamic mapping from adding new fields to an existing index.

Therefore, policies must be defined clearly at both the application layer and the cluster layer.

## 2. Spring Data Elasticsearch Can Auto-Create Indexes at Startup

Spring Data Elasticsearch allows declaring the index on an entity using `@Document`:

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

    // Constructors, getters and setters
}
~~~

With the default configuration of `@Document`, `createIndex` is `true`. Spring Data can check the index when initializing the repository and create the index along with its mapping from entity metadata if the index does not exist yet.

This behavior is useful during local development or integration tests because the application can prepare the index on its own. In production, if indexes must be created via approved migrations or infrastructure, creating them during startup can make the application the owner of mappings unexpectedly.

### Disabling Automatic Index Creation with createIndex = false

You can declare:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

`createIndex = false` instructs Spring Data not to automatically create the index for this entity during repository initialization.

This means:

- The application expects the index to exist before operating.
- The mapping must be prepared by a separate deployment workflow.
- The repository can still read/write once the target index or alias exists with a compatible mapping.
- If the index does not exist yet, operations may fail; the application should not rely on the repository to silently patch a missing index.

`createIndex = false` is neither a mapping creation command nor a cluster policy. It only controls automatic index creation managed by Spring Data.

## 3. Preventing Elasticsearch from Auto-Creating Indexes on Write Requests

Even when Spring Data does not auto-create indexes, a write request to a nonexistent index name can still cause Elasticsearch to create a new index if the cluster permits it.

For example, the application sends a request:

~~~http
POST /products/_doc
Content-Type: application/json

{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard"
}
~~~

If `products` does not exist and the server allows auto-create, Elasticsearch can create the `products` index with a mapping inferred from the document.

This is dangerous if `products` was supposed to be an alias pointing to `products-v1`. One mistimed write can create a physical index bearing the intended alias name, preventing the subsequent deployment workflow from creating the alias with that name.

### Cluster Setting action.auto_create_index

Elasticsearch provides the cluster setting `action.auto_create_index` to control automatic index creation as a side effect of write operations.

You can disable auto-create at the cluster level using the Cluster Settings API:

~~~http
PUT /_cluster/settings
Content-Type: application/json

{
  "persistent": {
    "action.auto_create_index": "false"
  }
}
~~~

When this policy is applied, write operations to a nonexistent index will not auto-create it. Indexes must be created explicitly beforehand using the Create Index API or an authorized provisioning workflow.

Understand the scope properly:

- This setting controls **automatic index creation on write**.
- It does not replace explicit index creation via administrative APIs.
- It does not stop dynamic mapping from adding fields to an existing index.
- This is a cluster-level configuration and can affect multiple applications and integrations sharing the cluster.

In multi-system environments, disabling auto-create globally can impact indexes used for logging, monitoring, security, or other integrations. Coordinate with Elasticsearch administrators to configure an allowlist policy aligned with operational needs. `action.auto_create_index` also supports allow/deny name patterns; pattern ordering and rules must be checked carefully against the running Elasticsearch version.

## 4. Controlling Dynamic Mapping on Existing Indexes

An index may already exist yet still automatically add new fields when documents contain properties absent from the mapping.

Example first document:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard"
}
~~~

If the mapping has not declared `name`, Elasticsearch can automatically infer the data type from the value. Later, another document sends an extra field:

~~~json
{
  "sku": "KB-1002",
  "name": "Wireless Keyboard",
  "supplierNote": "Imported batch"
}
~~~

With default dynamic mapping, the `supplierNote` field can be added to the mapping. When input data changes continuously, the mapping can grow unpredictably.

### dynamic: strict

If you want every field to be explicitly declared in the mapping, you can use:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

With `dynamic: strict`, documents with undeclared fields are rejected with a mapping error. For example, `supplierNote` is not in the mapping, so the index request fails.

This is suitable when schemas need strict enforcement. Errors are caught immediately at write time rather than silently creating new fields.

### dynamic: false

If you want to keep unknown data in `_source` without indexing those fields, you can use:

~~~json
{
  "mappings": {
    "dynamic": false,
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

With `dynamic: false`, undeclared fields are not added to the mapping. Values can still reside in `_source`, but are not indexed for querying like regular fields.

Choose `false` when the application needs to store extended data without needing to search on those fields. If all unknown fields must be rejected, use `strict`.

### Comparing Dynamic Modes

| Value | Behavior When Encountering an Undeclared Field |
|---|---|
| `true` | Automatically adds the field to the mapping using inference rules |
| `false` | Does not add the field to the mapping; value can still remain in `_source` |
| `strict` | Rejects documents containing undeclared fields |
| `runtime` | Can create a runtime field instead of indexing the field in the normal way |

`dynamic` can be set at the mapping level or at the object level to control a specific scope. A nested object can have its own dynamic policy. Inspect the actual mapping to see which policy applies to each part of the document.

## 5. Using Dynamic Templates When Controlled Dynamic Data Is Needed

Not every application has a completely fixed schema. Some systems have open sets of attributes while still wanting consistent mapping rules.

**Dynamic templates** let you define mapping rules based on field names or data types detected by Elasticsearch.

For example, dynamic string fields can be mapped as keyword:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "string_fields_as_keyword": {
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword"
          }
        }
      }
    ],
    "properties": {
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

A dynamic template does not disable dynamic mapping. It only dictates the data type created for new fields matching the condition. Fields not matching the template can still be mapped under default dynamic rules.

If the requirement is rejecting all fields outside the schema, use `dynamic: strict`. If a dynamic data region is needed, isolate that region into a dedicated object and define an appropriate template or data type.

### Using flattened for Objects with Many Dynamic Keys

If a document contains a map with arbitrary keys, such as partner-specific extended attributes:

~~~json
{
  "attributes": {
    "color": "black",
    "layout": "ANSI",
    "vendorFeatureCode": "X-91"
  }
}
~~~

If each key becomes a separate mapping field, the field count can grow rapidly. Elasticsearch offers the `flattened` type to store and search an object structure with many keys without creating a separate mapping for every key.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "flattened"
      }
    }
  }
}
~~~

`flattened` suits open metadata needing basic key/value lookup. It has limitations in query types and analysis capabilities compared to individually mapped fields. If range queries, numeric aggregations, or specialized analyzers are needed per attribute, declare fields with explicit types.

## 6. Preparing Indexes with a Dedicated Provisioning Workflow

In production, index settings and mappings should be created before the application serves requests. They can be managed via:

- Deployment scripts using Elasticsearch APIs.
- Infrastructure as Code or cluster administration tools.
- Dedicated migration jobs holding privileges to create indexes and update mappings.
- Version-controlled index templates.

The runtime application only needs read/write permissions on the required indexes or aliases. Separating these permissions prevents an application configuration bug from creating indexes or altering cluster structure.

### Creating an Index Explicitly with the Elasticsearch API

Example creating a versioned index with strict mapping:

~~~http
PUT /products-v1
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
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

In this example:

- `products-v1` is the versioned physical index.
- `products` is the alias used by the application.
- `dynamic: strict` rejects fields outside the schema.
- Fields are declared explicitly with appropriate data types.
- The `products` alias is created alongside the index, avoiding a window where the application sees the index without its alias.

The application can declare `@Document(indexName = "products", createIndex = false)` to use the provisioned alias.

### What Role Do Index Templates Play?

Index templates apply settings, mappings, and aliases to new indexes whose names match a pattern.

Example:

~~~http
PUT /_index_template/products-template
Content-Type: application/json

{
  "index_patterns": ["products-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "name": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword"
            }
          }
        },
        "status": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

A template does not create an index by itself. It is only applied when a matching index is created. For instance, after installing the template, the provisioning workflow still needs to create `products-v1` or an index with a matching name.

This enables applying the same mapping policy consistently to newly versioned indexes.

## 7. Creating Indexes Explicitly with Spring Data Elasticsearch

If provisioning is implemented in Java, Spring Data provides `IndexOperations` to manage indexes and mappings.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
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

`createWithMapping()` creates the index along with the mapping inferred from entity metadata. If the entity has appropriate settings configured, the index creation process can apply those settings as well.

This is an example for an intentional provisioning job. Do not let every production application instance run this code on startup if indexes are managed by a dedicated deployment pipeline.

Additional notes:

- `exists()` only checks state at call time; two instances can both see the index missing.
- There must be a single provisioning actor, or index creation conflicts must be handled intentionally.
- The provisioning account needs permissions to create indexes and manage mappings.
- The runtime account should hold minimal permissions required for reading/writing data.

If using an alias as `indexName`, do not call `createWithMapping()` on an already-existing alias as though it were a physical index to create anew. Create versioned indexes and aliases via the appropriate provisioning workflow.

## 8. Configuring Entities for Deployment Environments

An entity can describe the desired mapping while disabling automatic index creation:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;
}
~~~

`indexName = "products"` can be an alias created beforehand by provisioning. `createIndex = false` keeps the repository from auto-creating the index at initialization.

This configuration does not replace the mapping already created in Elasticsearch. The actual mapping of the target alias must be compatible with how Spring Data converts the entity.

Configuration can be organized by environment:

| Environment | Common Policy |
|---|---|
| Local development | Automatic index creation may be enabled for convenient experimentation |
| Integration test | Create index in test setup and clean up according to test lifecycle |
| Staging | Use migration/provisioning before deploying the application |
| Production | Disable Spring Data create index, control cluster auto-create, manage mappings explicitly |

If using separate profiles, ensure the production profile is actually activated in the deployment pipeline. Do not rely on local defaults to infer production configuration.

## 9. Verifying Permissions of the Runtime Account

Even with automatic mechanisms turned off, the application account might still hold privileges to create indexes or update mappings. To protect index structures, grant permissions following the least-privilege principle.

A runtime account typically only needs privileges matching application operations, such as reading, searching, indexing/updating/deleting on designated aliases or indexes. Only a separate provisioning account needs permissions to create indexes, update mappings, create templates, or alter aliases.

Exact privileges depend on operation types and Elasticsearch version. Verify against the privilege API of your running cluster version and test with the actual account.

Do not use a superuser account for normal application connections. If runtime has broad administrative privileges, a bug in an index name or request can create or modify resources unexpectedly.

## 10. Managing Mapping Changes with Versioned Indexes and Aliases

When an incompatible mapping change occurs, do not haphazardly modify an index serving production.

A common workflow:

~~~mermaid
flowchart TD
    A["Mapping v1 serving via products alias"] --> B["Create products-v2 with new mapping"]
    B --> C["Reindex data from products-v1 to products-v2"]
    C --> D["Verify counts and queries"]
    D --> E["Switch products alias to products-v2"]
    E --> F["Application continues using products alias"]
~~~

Example alias switch:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Aliases shield the application from knowing which physical index version is active. The application continues using `products`; the deployment pipeline handles creating the new index, reindexing, and switching the alias.

If the application writes during reindexing, design a strategy to sync new changes, pause writes, or use controlled dual-write. Switch the alias only after data has been verified.

## 11. Inspecting Actual Mappings and Indexes

Do not look solely at Java annotations to conclude the mapping on the cluster is right. Inspect Elasticsearch directly.

### Inspecting an Index or Alias

~~~http
GET /_resolve/index/products
~~~

This API determines which physical indexes or aliases the name `products` resolves to.

### Inspecting Mapping

~~~http
GET /products/_mapping
~~~

Verify:

- Do fields have the expected data types?
- Does the mapping have `dynamic: strict` or the intended policy?
- Have any unexpected fields appeared?
- Are multi-fields and analyzers accurate?

### Inspecting Index Templates

~~~http
GET /_index_template/products-template
~~~

Verify whether the template is installed with the right pattern, settings, and mapping.

### Inspecting Index List

~~~http
GET /_cat/indices/products*?v
~~~

This command helps spot unexpectedly created physical indexes, such as `products` appearing alongside `products-v1` even though the application was supposed to use only an alias.

## 12. Common Deployment Mistakes

### Only Setting createIndex = false and Thinking All Auto-Create Is Blocked

The annotation only controls Spring Data's index creation behavior. If the cluster still permits auto-create, a write request to a nonexistent index can still create an index.

Also control `action.auto_create_index` at the cluster level.

### Turning Off Auto-Create but Forgetting Provisioning

When the index has not been created yet, application writes receive errors instead of auto-creating the index. That is the intended behavior of the policy, so the pipeline must create the index before the application starts receiving traffic.

### Turning Off Dynamic Mapping Without Checking Fields

`dynamic: false` does not raise errors on unknown fields; it simply does not index them. If you want to catch invalid schema payloads, use `dynamic: strict` and handle write errors appropriately.

### Using strict While Missing Valid Fields

If an application version sends a new field before the mapping is updated, Elasticsearch rejects the document. Deploy compatible mappings before deploying code that uses new fields.

### Using a Fixed Index Name When Wanting Versioned Indexes

If the application writes directly to `products-v1`, switching indexes requires changing application configuration. Using a stable alias reduces this coupling.

### Leaving Index Admin Privileges on the Runtime User

A bug in an index name or request can create unintended resources. Separating provisioning and runtime accounts limits the blast radius.

### Creating Different Mappings Across Environments

If local uses dynamic mapping while production uses strict mapping, code may work locally yet fail on deployment. Put settings/mapping into the same versioned workflow and verify in staging.

## 13. Recommended Deployment Workflow

When preparing an index change for production:

1. Define the schema and fields that need to be indexed.
2. Declare mappings, analyzers, settings, and dynamic policy.
3. Place index templates or mappings into source-controlled migrations.
4. Create physical indexes before deploying the application.
5. Create aliases if the application uses a stable alias.
6. Configure entities with `@Document(createIndex = false)`.
7. Control `action.auto_create_index` cluster-wide according to shared policy.
8. Grant separate provisioning and runtime permissions.
9. Verify mappings, aliases, and indexes via Elasticsearch APIs.
10. Deploy the application after indexes are ready.
11. Monitor mapping errors when writing documents.
12. When incompatible mapping changes occur, create a new versioned index, reindex, and switch aliases according to plan.

## Conclusion

Preventing unintended mapping creation requires multi-layer control. Use `@Document(createIndex = false)` so Spring Data does not auto-create indexes during repository initialization; configure `action.auto_create_index` to control Elasticsearch auto-creating indexes on writes to nonexistent names; use `dynamic: strict` or `false` to control new fields in existing indexes. In production, create indexes, settings, mappings, and aliases through a versioned provisioning workflow, grant separate privileges for provisioning and runtime, and only then deploy the application.
