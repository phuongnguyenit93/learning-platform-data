# Separating Index Management Privileges from Document Read/Write Privileges

In Elasticsearch, document operations and index management operations carry very different levels of impact. A business application normally only needs to search, read, create, update, or delete documents in indexes that have already been prepared. Creating indexes, changing mappings, settings, analyzers, aliases, or deleting indexes typically belongs to a deployment workflow or an administrative tool.

If a single account with index administration privileges is shared across all runtime operations, a configuration bug or vulnerability in the application can affect the schema and data of the entire index. Therefore, identities and privileges should be separated into two groups:

- **Runtime application:** only holds document read/write privileges on the indexes the application needs to use.
- **Index provisioning/migration:** holds privileges to create indexes, manage mappings/settings, and perform migrations or alias changes within its assigned scope.

This applies the *least privilege* principle. The application is granted only the permissions necessary to perform business operations, while permissions to modify index structure are restricted to controlled workflows.

## 1. Distinguishing Documents and Indexes

Elasticsearch organizes data into indexes. An index contains documents structured as JSON; the mapping defines how fields are indexed and queried.

Operations can be divided into two groups:

| Operation Group | Examples | Purpose |
|---|---|---|
| Document read/write | Search, get, index, update, delete document, bulk | Process business data |
| Index management | Create/delete index, mapping, settings, analyzer, alias | Manage structure and data lifecycle |

Examples:

- A product search API calls search on the products index.
- A price update API calls update or index document in products.
- A deployment workflow creates the products_v2 index with a new mapping.
- A migration workflow reindexes data from products_v1 to products_v2.
- After verification, the workflow switches the products alias to the new index.

The first three operations of the business application do not require permissions to create or delete indexes. The latter operations that alter structure or data routing should require appropriate administrative privileges.

An index is an important boundary for granting privileges in Elasticsearch. Permissions are typically assigned to one or more index names, aliases, or data streams via roles. Thus, you can restrict an application to accessing only products instead of granting privileges across all indexes in the cluster.

## 2. How Does Elasticsearch Security Handle Authorization?

Elasticsearch Security uses role-based access control (RBAC). Users or API keys are bound to permissions through roles or role descriptors. A role can contain:

- **Cluster privileges:** cluster-scoped permissions, such as certain administrative or cluster monitoring operations.
- **Index privileges:** permissions on indexes, aliases, or data streams whose names match the declared scope.
- Other permission scopes if supported by security features and version, such as application privileges or Kibana space privileges.

In this context, pay attention to index privileges. Common privileges include:

| Privilege | General Meaning |
|---|---|
| read | Read documents, search, and corresponding read operations |
| write | Perform document write operations such as index, update, and delete |
| create_doc | Create documents in create mode, disallowing overwriting existing documents in the normal way |
| index | Write documents within the granted index privilege scope |
| delete | Delete documents |
| view_index_metadata | Read index metadata such as mapping/settings within the permitted scope |
| create_index | Create indexes |
| delete_index | Delete indexes |
| manage | Manage indexes, including many mapping and settings operations |
| manage_aliases | Manage aliases |

These are privileges at different levels. Do not equate document write privileges with index creation privileges. Granting write does not mean the application should be able to create or delete indexes at will.

The list of privileges and covered actions can change across Elasticsearch versions. When designing a role for a specific API, match privileges against the actions executed by that API in your running cluster version. Do not guess permissions solely from Java method names.

## 3. Role for a Runtime Application with Document Read/Write Only

Suppose a retail application uses the products index. The application needs to:

- Search products.
- Read documents by id.
- Create new products.
- Update products.
- Delete documents when required by business logic.

The application can be granted a role containing only read and write on the products index:

    PUT /_security/role/products_runtime
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products" ],
          "privileges": [ "read", "write" ]
        }
      ]
    }

This role clearly expresses the usage scope:

- The application can read and write documents in products.
- The application is not granted manage or delete_index.
- The application cannot manage aliases or create indexes just because it needs to perform CRUD.
- The application holds no cluster privileges in this example.

If the application only needs to read, grant only read. If the application only creates new documents and never updates or deletes, you can consider a narrower privilege like create_doc, after checking the actual operations the client uses.

### Is view_index_metadata Needed?

Some applications or libraries need to read index metadata to inspect mapping, settings, aliases, or index status. In that case, you may need to additionally grant view_index_metadata on the exact index scope.

Do not add this privilege out of habit if runtime only calls document APIs and does not need to read metadata. Inspect authorization error logs and the APIs actually called by your Spring Data/client version.

Example role with metadata read privilege added:

    PUT /_security/role/products_runtime
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products" ],
          "privileges": [
            "read",
            "write",
            "view_index_metadata"
          ]
        }
      ]
    }

Only grant view_index_metadata when actually required. This privilege is not equivalent to manage: it permits reading certain metadata, not modifying mappings or settings.

## 4. Role for Index Creation and Management Workflows

A provisioning or migration workflow may need to perform tasks such as:

- Checking whether an index already exists.
- Creating an index with approved settings and mapping.
- Adding fields or updating mappings within Elasticsearch limits.
- Closing/opening indexes if migration requires it.
- Creating a new versioned index.
- Reading data from the source index and writing data to the destination index during reindex.
- Switching the alias after verifying data.

These operations require corresponding index-management privileges. For example, an index management role can be declared as:

    PUT /_security/role/products_index_migration
    {
      "cluster": [],
      "indices": [
        {
          "names": [ "products", "products-*" ],
          "privileges": [
            "manage",
            "manage_aliases",
            "create_index",
            "read",
            "write"
          ]
        }
      ]
    }

The example above illustrates a dedicated identity for migration. Index name scope is restricted to products and versioned indexes products-*. read/write privileges are used when the workflow needs to read the source index or write data to the destination index; index management privileges serve creating and modifying structure.

Actual roles should be narrowed to the migration steps that need to run. If a workflow only creates a new index, do not grant permission to delete the old index. If it does not switch aliases, do not grant manage_aliases. If a tool only adds permitted mapping fields, choose the narrowest privilege supported by your Elasticsearch version rather than granting broader administrative rights.

The manage privilege has a broad scope on an index. It can allow many administrative operations such as changing mappings and settings. Therefore, grant it only to the migration/provisioning account and restrict names precisely. Do not attach this role to the account used by the runtime application.

Role examples must be tested against your specific version and actions. APIs for creating indexes, updating mappings, changing aliases, reindexing, and deleting indexes may require different sets of privileges. A production workflow should test the role in a test environment and confirm both allowed operations succeed and disallowed operations are rejected.

## 5. Separating Identities and Credentials in Application Architecture

Creating two roles while still sharing a single user that holds both roles does not achieve separation. Runtime identity and provisioning identity must be issued separately.

A deployment model:

    Spring Boot application
       |
       | API key: products_runtime
       v
    Elasticsearch
       |
       +-- products_runtime role
       |      read / write documents
       |
       +-- products_index_migration role
              create index
              manage mapping/settings
              manage aliases

Two credentials are used in two places:

| Credential | Where Used | Purpose |
|---|---|---|
| Runtime credential | Application serving requests | Document read/write |
| Migration credential | Deployment pipeline or migration job | Index creation and schema changes |

Do not place migration credentials in runtime configuration just so the application can create indexes on its own. If runtime can access administrative credentials, a bug in the application could use those permissions even if the runtime role was designed narrowly.

You can use separate users or separate API keys for each purpose. An API key can carry a role descriptor restricting privileges and index scope. Whichever mechanism you choose, credentials must be managed as secrets: stored in a secret manager or the environment's secrets management system, rotated when needed, and never committed to Git.

### Spring Boot Configuration for Runtime

The application receives only the runtime credential:

    spring:
      elasticsearch:
        uris: https://elasticsearch.example.internal:9200

This is an example cluster address configuration. Credentials can be supplied through secret-backed configuration and the authentication mechanism of the Spring Boot/client version in use. If using an API key or custom client configuration, configure headers and credentials according to the corresponding mechanism.

Runtime environment variables hold only credentials with read/write privileges on permitted indexes. The migration pipeline has its own set of secrets and does not pass administrative credentials into request-serving processes.

## 6. Separating Automatic Index Creation from Spring Data CRUD Operations

Spring Data Elasticsearch can automatically create indexes based on entity metadata under certain configurations. This is convenient for small examples or development environments, but can cause the runtime application to require additional index creation and mapping privileges.

Example entity:

    @Document(
        indexName = "products",
        createIndex = false
    )
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

Setting createIndex = false expresses that the application does not ask the repository mechanism to automatically create the index for this entity. Mapping and settings must be prepared beforehand by the provisioning workflow.

Once the index exists, the runtime repository can still perform document operations with read/write privileges:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

The lifecycle separation can be organized as follows:

    Deployment / migration pipeline
       |
       | Migration credential
       v
    Create index + settings + mapping
       |
       v
    Verify index
       |
       v
    Deploy application
       |
       | Runtime credential
       v
    Repository CRUD and search

If the index has already been created by a script or migration, runtime does not need schema management permissions to use the repository. The converter still uses entity metadata to map documents; createIndex = false does not disable mapping metadata.

### Where Should IndexOperations Live?

Operations such as:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    indexOperations.createWithMapping();

or:

    indexOperations.putMapping();

belong to the index management workflow. If executed with a runtime credential that only has read/write, Elasticsearch can reject them due to insufficient privileges. That is the intended behavior of privilege separation.

Call provisioning operations using the migration credential inside a controlled job, or through a separate administrative tool. Business services should not call createWithMapping on every user request.

## 7. Required Privileges for Common Operations

The table below helps guide authorization design. This is a business-level classification; exact privileges should be verified against the actions emitted by the API on your Elasticsearch version.

| Operation | Privilege Group Typically Needed | Where It Should Run |
|---|---|---|
| Search documents | read | Runtime |
| Get document by id | read | Runtime |
| Index document | write or narrow appropriate write privilege | Runtime |
| Update document | write | Runtime |
| Delete document | write or delete depending on API and chosen privilege | Runtime |
| Bulk write documents | read/write according to actions in the bulk request | Runtime |
| Read mapping/settings | view_index_metadata | Migration or runtime if truly required |
| Create index | create_index | Provisioning |
| Modify mapping | Mapping management privilege, typically manage | Provisioning |
| Modify settings | Corresponding index management privilege, typically manage | Provisioning |
| Delete index | delete_index or management privilege covering that action | Controlled provisioning |
| Manage aliases | manage_aliases or management privilege covering that action | Provisioning |
| Reindex | read on source, write on destination; plus index creation/management if needed | Migration |

One API may execute multiple actions. For example, repository initialization might check an index, read metadata, or create a mapping depending on configuration. Therefore, do not look only at the repository method name to deduce exact privileges.

## 8. Example Safe Migration Workflow

Suppose the current version uses the products alias pointing to the products-v1 index. The new version needs to change the mapping of the category field from text to keyword.

Changing a field type cannot be handled by overwriting the mapping on the old index in the usual way. The migration workflow can proceed as follows:

1. The pipeline uses the migration credential to create products-v2 with the new mapping.
2. The pipeline reads data from products-v1 and writes it to products-v2 via reindex or a data transformation process.
3. If the system continues writing during reindexing, the pipeline must synchronize new changes or have a clear write-pause/cutover strategy.
4. Verify document counts, error records, and critical queries on products-v2.
5. Switch the products alias to the new index using alias management privileges.
6. The runtime application continues using the products alias with read/write credentials.
7. Only delete products-v1 after the rollback period ends and proper confirmation is obtained.

The runtime application does not need permission to create products-v2, reindex, or switch aliases. It simply continues reading/writing through the alias prepared by provisioning.

### Why Are Aliases Useful?

An alias provides a stable name for the application while the physical index can change across versions. The application does not need to know whether products-v1 or products-v2 is the active index.

Switching an alias is an administrative operation and requires appropriate privileges. If the runtime application could change aliases on its own, a bug or uncontrolled request could cause the application to read/write the wrong index.

## 9. Testing Authorization with Both Allowed and Denied Operations

After creating roles, do not test only that business operations succeed. Test operations that runtime must not be allowed to perform as well.

Example tests using the runtime credential:

| Test | Expected Outcome |
|---|---|
| Search products | Succeeds |
| Get a document in products | Succeeds |
| Index/update document in products | Succeeds if role has write |
| Search an index outside the products scope | Denied |
| Create index products_test | Denied |
| Update mapping of products | Denied |
| Delete index products | Denied |
| Change alias products | Denied |

Next, test the migration credential:

- Create a new index within the granted scope.
- Create mapping and settings.
- Read source and write destination during reindex.
- Switch alias if migration requires it.
- Attempt to access an index outside scope and confirm it is denied.

Elasticsearch typically returns authorization errors such as HTTP 403 when an identity lacks privileges for an action. Record the denied endpoint/action to determine which permission genuinely needs to be added. Do not resolve errors by granting all on every index.

### Checking Privileges via API

Elasticsearch Security provides APIs to inspect privileges of a user or API key, depending on the version and authentication mechanism. You can use privilege-check APIs to confirm an identity holds the required privileges on specific resources.

In addition to API checks, run integration tests using the actual runtime credential in a test environment. Tests should simulate both permitted requests and administrative requests that must be denied.

## 10. Index and Alias Scopes Must Be Declared Carefully

Roles restrict permissions by names. For example:

    "names": [ "products" ]

only expresses scope for the name products. If the application uses aliases, data streams, or version-suffixed indexes, declare the exact resource names actually accessed by requests.

Do not use overly broad wildcards like * if the application only needs one group of indexes. A role with names = ["*"] along with write or manage privileges can extend impact to other indexes in the cluster.

For migrations, permissions may be needed on both source and destination indexes:

- Source: read to read documents.
- Destination: create_index/manage to create the index and mapping; write to write documents.
- Alias: alias management privilege on the involved indexes.

If reindexing across multiple indexes or tenants, determine the exact index name patterns and avoid granting permissions beyond the job's tenant or data domain.

## 11. Notes on API Keys and Secret Management

API keys can be created with role descriptors restricting privileges and expiration. This is a useful way to issue separate credentials for runtime and migration.

Principles:

- Create a runtime API key with the required read/write privileges on specific indexes.
- Create a separate migration API key for the provisioning pipeline.
- Set appropriate expiration and rotation procedures.
- Do not write API keys into source code, logs, documentation, or committed configuration files.
- Do not pass the migration key into runtime containers or processes if the application does not need it.
- Revoke old keys when rotating or when a pipeline is no longer used.

If using username/password instead of API keys, also separate users by purpose and restrict roles similarly.

Do not treat HTTPS connection encryption as a substitute for authorization. TLS protects data in transit; roles and privileges decide what an identity is permitted to do on Elasticsearch.

## 12. Common Misconceptions

### Thinking write Includes Index Creation

write is for document write operations. Creating an index is an index management operation and requires a corresponding privilege like create_index. Do not grant index management permissions just because a service needs to save documents.

### Granting manage to the Application to Avoid 403 Errors

manage has a broad scope and can allow changing mappings/settings or other administrative actions. If runtime only needs search and CRUD, grant read/write on the exact index.

### Using the Same API Key for Runtime and Migration

If a key holds administrative privileges for migration to work, runtime can use those same privileges too. Create separate credentials to limit the blast radius if runtime has a bug or is compromised.

### Setting createIndex = true While Granting Only read/write

If repository lifecycle attempts to create an index or mapping at startup, the runtime credential may be rejected. When indexes are managed by a pipeline, set createIndex = false and provision indexes before deploying the application.

### Thinking createIndex = false Removes Mapping Metadata

This attribute controls automatic index creation behavior. Spring Data still needs entity metadata and the converter to map documents when reading/writing.

### Granting Privileges on All Indexes

Broad wildcards enlarge a credential's blast radius. Use narrow index names, aliases, or patterns per application and environment.

### Testing Only Successful Operations

A role might run CRUD fine while still holding unintended administrative permissions. Test creating indexes, editing mappings, deleting indexes, and changing aliases to ensure runtime is denied.

### Assuming Every Spring Data API Calls Only One Elasticsearch Action

One method at the Spring layer may trigger multiple requests or metadata checks depending on configuration and version. When encountering 403, inspect the actual action in the error/log and grant the exact privilege needed.

## Conclusion

Document read/write and index management are two sets of responsibilities that require separate authorization. Runtime applications normally only need read/write on the indexes or aliases they use. Only provisioning/migration workflows need privileges like create_index, manage mapping/settings, and manage_aliases within a controlled index scope.

In Spring Data Elasticsearch, you can set createIndex = false on entities when indexes are created by a separate pipeline. Runtime still uses repositories or ElasticsearchOperations to operate on documents with restricted credentials. Separating users or API keys, scoping index names, testing both allowed and denied operations, and keeping migration credentials out of runtime processes help reduce the risk of unintended schema changes or accidental data deletion in production.
