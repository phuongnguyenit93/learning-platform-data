# Index Not Found, Misconfigured Aliases, and Write-Blocked Indices

A Spring Data Elasticsearch application can run normally for a long time and then suddenly fail when saving or searching documents. Three common incident categories are **missing indices**, **misconfigured aliases or unclear write indices**, and **write-blocked indices**.

These issues can surface with the same HTTP status in certain cases, yet their root causes and fixes differ greatly. For example, a 404 error may be caused by a wrong index name, an uncreated alias, or an application writing to a date-based index name that does not exist yet. A 403 error can be an access-denied security error or Elasticsearch placing an index into read-only mode due to disk usage. An alias pointing to multiple indices without an explicit write index can cause write operations to fail even though all target indices exist.

This lesson explains how to classify errors, inspect indices and aliases, diagnose write blocks, configure Spring Data Elasticsearch, recover safely, and build integration tests so issues are caught early.

## 1. Distinguishing the three incident categories

Before changing configuration, determine which step the request is failing at.

| Incident category | Common symptoms | Questions to answer |
|---|---|---|
| Index not found | index_not_found_exception, HTTP 404 | Does the index or alias used by the request exist? |
| Misconfigured alias | Alias does not exist, points to wrong index, or lacks a write index | Which indices does the alias point to, and which index receives writes? |
| Write-blocked index | cluster_block_exception, HTTP 403, or rejected write errors | Which block is active, who enabled it, and why? |

Do not rely solely on HTTP status. Read error.type, error.reason, the resource name in the response, and request logs. A 403 caused by security_exception requires fixing permissions; a 403 caused by cluster_block_exception requires handling the block. Recreating an index does not solve either case.

### A general diagnostic flow

~~~text
Spring Data request fails
           |
           v
Read root cause, error.type, status, and target
           |
           +---- index_not_found_exception
           |           |
           |           v
           |     Check index name / alias / environment
           |
           +---- alias or write index error
           |           |
           |           v
           |     Check alias membership and is_write_index
           |
           +---- cluster_block_exception
           |           |
           |           v
           |     Check index settings, disk, and cluster state
           |
           +---- security_exception
                       |
                       v
                 Check identity and privileges
~~~

Extracting the exact target from the request or logs is a crucial step. Names in @Document, aliases, and IndexCoordinates can differ.

## 2. What does Index not found mean?

Elasticsearch returns index_not_found_exception when a request references an index or alias that cannot be resolved in the cluster the request is calling.

Example:

~~~http
GET /orders/_search
{
  "query": {
    "match_all": {}
  }
}
~~~

If neither an orders index nor an orders alias exists, Elasticsearch cannot execute the search.

Common causes:

- The index has not been created yet.
- The index name is misspelled or has the wrong letter casing.
- The application uses the wrong date, tenant, or environment suffix.
- The alias was expected to be created during provisioning, but that step did not run.
- The index was just deleted, or rollover/migration has not completed.
- The application connected to the wrong cluster.
- Another configuration profile is writing to a different endpoint.
- A request uses an old index name after an alias changed.

Elasticsearch index names must follow Elasticsearch naming rules and are typically lowercase. Do not assume a Java class name or database table name is automatically converted into the desired index name.

### Distinguishing physical indices from aliases

orders-000001 may be a physical index, while orders-write is an alias used for writing. If the application sends requests to orders while provisioning only created orders-write, requests will not automatically treat those two names as equivalent.

Check the actual target used by the repository or template. An alias only works when that alias has already been created in the cluster.

## 3. Inspecting index and alias names with Elasticsearch APIs

The following APIs help identify which resources currently exist.

List indices:

~~~http
GET /_cat/indices?v
~~~

Filter by prefix:

~~~http
GET /_cat/indices/orders*?v
~~~

List aliases:

~~~http
GET /_cat/aliases?v
~~~

Inspect a specific alias:

~~~http
GET /_alias/orders-write
~~~

In Elasticsearch versions that support the Resolve Index API, you can use:

~~~http
GET /_resolve/index/orders-write
~~~

Resolve Index helps distinguish whether a name resolves to a concrete index, an alias, or a data stream. If this API is unavailable in your cluster version, use _cat/indices, _cat/aliases, and the corresponding alias endpoint.

Check index health:

~~~http
GET /_cluster/health/orders-000001?level=indices
~~~

These commands require appropriate monitoring/metadata privileges. If the API returns 403, do not conclude the index does not exist; the current identity may lack permission to view metadata.

### Using HEAD to check existence

You can check whether an index or alias exists using a HEAD request:

~~~http
HEAD /orders
~~~

A successful result indicates the resource can be resolved under the current endpoint and permissions. HEAD does not tell you whether the alias has a write index, whether the mapping is right, or whether the index is write-blocked.

Therefore, checking existence is only an initial step, not a complete health check.

## 4. Where does Spring Data Elasticsearch get the index name?

Spring Data Elasticsearch can obtain the index name from entity annotations or from IndexCoordinates passed into Operations.

Example:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private String status;
}
~~~

When using a repository for this entity, the index name configured on @Document is a key part of determining the target.

With Operations, the target can be specified explicitly:

~~~java
operations.save(
    order,
    IndexCoordinates.of("orders")
);
~~~

If the application uses aliases, orders in the annotation or IndexCoordinates can itself be an alias. In that case, the alias must exist and point to the right index.

### Dynamic indices by tenant or time

Some applications select indices by month, tenant, or data type:

~~~java
String indexName = "orders-" + YearMonth.now();
IndexCoordinates coordinates =
    IndexCoordinates.of(indexName);

operations.save(order, coordinates);
~~~

If the code builds the suffix orders-2026-11 while index provisioning only created orders-2026-10, the operation will hit index not found when auto-create is disabled or the user lacks index creation privileges.

Do not rely on system dates in multiple places to build index names independently. Centralize index selection rules in a single component and test month boundaries, timezones, tenants, and environments.

### Is automatic index creation a good fix?

Elasticsearch can auto-create an index in some configurations when receiving a write request to a non-existent name. This behavior depends on cluster settings, auto-create policies, and user privileges.

Auto-create can mask wrong index names or create indices with incorrect default mappings. For critical indices, deliberately provision index templates, mappings, settings, and aliases before the application writes data.

## 5. Creating indices properly in Spring Data

Spring Data Elasticsearch provides IndexOperations to check, create, and manage indices.

Example:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("orders-000001"));

if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

Mappings can be created from an entity:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Order.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

Method signatures and mapping creation depend on the Spring Data Elasticsearch version. If mappings are managed via resource files, index templates, or migrations, use the same configuration source as production.

### Avoiding race conditions when multiple instances create indices simultaneously

Calling exists() and then create() involves two separate requests. If multiple instances start up simultaneously, they may both see that the index does not exist and both call create. One instance succeeds while the other may receive resource-already-exists.

Do not treat this error as a critical data failure if the index has already been created properly. However, handle it idempotently and verify that the existing mapping/settings are compatible instead of ignoring all exceptions.

A centralized provisioning workflow or controlled migration job is usually easier to operate than having every application instance create indices in production.

### @Document(createIndex = false)

Depending on the Spring Data Elasticsearch version, @Document supports an option controlling automatic index creation when repository infrastructure initializes. If the application uses separate provisioning, you can disable automatic index creation to prevent unintended resource creation.

Whichever option is used, the application must still ensure the index/alias exists before executing requests. Disabling auto-create does not create the index; it only changes startup behavior.

## 6. What are aliases used for?

An alias is a logical name pointing to one or more physical indices. Applications can continue using a stable alias while the target index changes across versions or rollovers.

Example:

~~~text
orders-read  -> orders-000001, orders-000002
orders-write -> orders-000002
~~~

- orders-read is a read alias that can point to multiple indices.
- orders-write is a write alias pointing to the active index.
- orders-000001 and orders-000002 are physical indices.

Benefits of aliases:

- Applications do not need to know specific index versions.
- You can reindex to a new index and then switch the alias.
- You can read data across multiple indices.
- You can separate read aliases and write aliases to express clear intent.
- You can switch aliases in a single atomic _aliases request.

An alias is not a physical index and does not store documents of its own. It is a routing name pointing to indices.

## 7. Aliases pointing to multiple indices and write index

An alias can point to multiple indices for searching. However, when writing, Elasticsearch needs to know which index is the destination.

Example alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-000001",
        "alias": "orders"
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders"
      }
    }
  ]
}
~~~

The orders alias now points to two indices. Without an explicitly designated write index, write operations through the alias may fail because Elasticsearch does not know which index should receive the document.

Set the write index explicitly:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-000001",
        "alias": "orders",
        "is_write_index": false
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders",
        "is_write_index": true
      }
    }
  ]
}
~~~

Then write requests to the orders alias are routed to orders-000002. Searches through the alias can still read both indices.

If an alias points to only one index, Elasticsearch can default that index as the write index in appropriate cases. Even so, for aliases serving multiple indices, explicitly declaring is_write_index avoids ambiguity.

### Symptoms of an alias missing a write index

Errors usually indicate that no write index is defined for the alias or that the alias cannot be used as a write target. The HTTP status and exception wrapper may differ by API/client version.

When encountering this error:

1. Check whether the alias exists.
2. List all indices the alias points to.
3. Check is_write_index.
4. Confirm the selected index is the latest index or the right index per business rules.
5. Fix the alias atomically after verifying data and mappings.

Do not solve this by renaming @Document to a physical index name if the architecture intends to use stable aliases.

## 8. Read aliases and write aliases should be separated

A common design:

~~~text
Application
   |
   +---- Search / get collection ----> orders-read
   |
   +---- Index / update / delete ----> orders-write
                                          |
                                          v
                                    orders-000042
~~~

Separating aliases clarifies intent and reduces the risk of a write query accidentally using a multi-index read alias.

Example configuration:

- orders-read: points to indices still retained for searching.
- orders-write: points to exactly one index receiving writes.
- orders-000042: the newest physical index.

For an entity repository using a single indexName, you can configure the alias the repository uses according to your application's pattern. If different read/write aliases are needed, use a custom repository fragment or a service using ElasticsearchOperations with distinct IndexCoordinates per operation.

Do not assume every repository method can automatically pick two different aliases from a single annotation. Clearly define read paths and write paths in your repository design.

## 9. Atomic alias switching when creating a new index

During manual reindexing or rollover, do not remove an alias first and add it back afterward in two separate requests. During that gap, the application may receive index not found errors.

Elasticsearch supports multiple actions in a single _aliases request. Example switching orders-write from an old index to a new index:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "orders-000001",
        "alias": "orders-write"
      }
    },
    {
      "add": {
        "index": "orders-000002",
        "alias": "orders-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Alias changes within the same request are applied atomically in the cluster state. The application never observes a window where the alias is completely missing between two steps.

### Safe cutover sequence

1. Create the new index with the desired mapping and settings.
2. Confirm the new index exists and its mapping is accurate.
3. Reindex or load the necessary data.
4. Reconcile document counts and critical data.
5. Switch aliases in a single _aliases request.
6. Verify read/write aliases after cutover.
7. Delete the old index only when the retention policy permits and you have confirmed rollback is no longer needed.

If concurrent writes occur during reindexing, you need a strategy to synchronize changes made during the transition window. Simply copying a snapshot and switching the alias can lose updates arriving after the snapshot.

## 10. Rollover and write aliases

Rollover creates a new index when the current index meets conditions such as age or size. A write alias acts as a stable write endpoint.

Example creating a write alias:

~~~http
PUT /orders-000001
{
  "aliases": {
    "orders-write": {
      "is_write_index": true
    },
    "orders-read": {}
  }
}
~~~

Call rollover:

~~~http
POST /orders-write/_rollover
{
  "conditions": {
    "max_age": "30d",
    "max_primary_shard_size": "40gb"
  }
}
~~~

Elasticsearch creates the next index following the naming convention and moves the write alias to the new index if conditions are met. Supported rollover conditions vary by version and index type; check the actual cluster documentation.

After rollover, verify the alias:

~~~http
GET /_cat/aliases/orders-write?v
~~~

If the application writes to the alias but the alias was not moved properly, it may continue writing to the old index or encounter write-target errors. Do not only check that the new index was created; check where the alias actually points.

## 11. What is a write-blocked index?

Elasticsearch has index blocks to prevent certain operations when protecting the cluster or data. Common blocks:

| Setting | General impact |
|---|---|
| index.blocks.write | Blocks write operations to the index |
| index.blocks.read_only | Places the index in read-only mode |
| index.blocks.read_only_allow_delete | Blocks normal writes while allowing deletes per block semantics |
| index.blocks.metadata | Blocks certain metadata operations |
| index.blocks.read | Blocks read operations |

Exact impact and management APIs depend on the Elasticsearch version. In write incidents, the first three settings are the ones to check first.

A block may be enabled manually by an operator to protect an index during maintenance. It may also be set automatically by Elasticsearch when disk usage exceeds the flood-stage watermark.

### Symptoms in the response

An error example may indicate the index is read-only or blocked due to the flood-stage disk watermark:

~~~json
{
  "error": {
    "type": "cluster_block_exception",
    "reason": "blocked by: [FORBIDDEN/12/index read-only / allow delete (api)];"
  },
  "status": 403
}
~~~

Specific messages vary by version and cause. Preserve error.type and error.reason verbatim in logs for accurate classification.

## 12. Disk flood-stage can automatically set a read-only block

Elasticsearch monitors disk usage across nodes. When disk exceeds watermarks, the cluster may stop allocating new shards or switch indices into read-only mode to avoid running out of disk space.

The flood-stage watermark is a critical protective threshold. When a node crosses this threshold, Elasticsearch can automatically set index.blocks.read_only_allow_delete on indices with shards residing on the affected node.

As a result, an application can suddenly fail to write even though no code changed.

### Proper remediation procedure

1. Check disk usage across nodes.
2. Identify nodes and shards exceeding the watermark.
3. Free up or expand storage according to operational procedures.
4. Wait for Elasticsearch to update watermark status.
5. Check index settings to see whether the block still exists.
6. Remove the block only after the root cause is resolved and according to operational policy.
7. Test a controlled small write operation and monitor the cluster.

Do not merely clear the block while disk is still full. Elasticsearch may reapply the block, or the cluster may suffer severe failures.

### Checking disk

You can use:

~~~http
GET /_cat/nodes?v&h=name,disk.used_percent,disk.avail,disk.total
~~~

View allocation per node:

~~~http
GET /_cat/allocation?v
~~~

Column names and metrics depend on the version. Combine this with infrastructure monitoring to track disk over time, growth rates, and free capacity.

## 13. Checking index block settings

Inspect index settings:

~~~http
GET /orders-000001/_settings?flat_settings=true
~~~

You can filter block settings:

~~~http
GET /orders-000001/_settings/index.blocks.*?flat_settings=true
~~~

If the index has index.blocks.write: true or index.blocks.read_only: true, write operations may be rejected.

Some blocks are enabled at the cluster level or by other policies. If index settings do not reveal the cause, check cluster settings, audit logs, operator automation, and the full error reason.

### Removing a block after confirming the cause

Example removing the read-only-allow-delete block:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.read_only_allow_delete": null
}
~~~

Removing an operator-placed write block:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.write": null
}
~~~

Removing a read-only block:

~~~http
PUT /orders-000001/_settings
{
  "index.blocks.read_only": null
}
~~~

Target the exact setting that is enabled and the exact index. Do not mechanically send all settings to false if blocks are managed by cluster policies or automated mechanisms. For flood-stage, free disk space first before checking whether to clear the block.

## 14. Distinguishing blocks from access permission errors

Both blocks and access permission issues can return HTTP 403, but their fixes differ.

| Error type / reason | Common meaning | Handling direction |
|---|---|---|
| cluster_block_exception | Index or cluster is blocking the operation | Check block settings, disk, and policies |
| security_exception | User/API key lacks privileges | Check roles and index privileges |
| index_not_found_exception | Cannot resolve index or alias | Check name, alias, cluster |
| Alias write index error | Alias cannot determine target write index | Check alias membership and is_write_index |
| mapper_parsing_exception | Payload does not match mapping | Check fields and mapping |

Do not grant broader permissions just to fix cluster_block_exception. Similarly, do not clear blocks when the real error is security_exception.

### Checking permissions

Elasticsearch security APIs can help identify the current user and privileges if the identity is permitted to call the corresponding API. Example:

~~~http
GET /_security/_authenticate
~~~

Checking specific privileges requires APIs and privileges appropriate to the security version in use. In a Spring application, confirm the credentials used by the right profile and client bean, not just the credentials an operator uses in Kibana.

## 15. Diagnosing from Spring Data exceptions

Spring Data Elasticsearch uses the Elasticsearch Java API Client and Spring's exception translation mechanism. The exception an application receives may be a client exception or a DataAccessException/Spring exception wrapping the underlying cause.

Do not log only exception.getMessage() and discard the cause. Record:

- Operation running: index, save, search, update, delete, or bulk.
- Target index/alias.
- Document ID if appropriate.
- HTTP status.
- Elasticsearch error.type.
- Elasticsearch error.reason.
- Root cause class.
- Correlation ID or job ID.
- Profile/cluster identity (without logging secrets).

Example service-level handling:

~~~java
try {
    return repository.save(order);
} catch (DataAccessException ex) {
    Throwable rootCause = NestedExceptionUtils.getMostSpecificCause(ex);

    log.error(
        "Unable to save order to Elasticsearch: {}",
        rootCause.getMessage(),
        ex
    );

    throw ex;
}
~~~

This is a minimal logging example. In a real application, the adapter or exception handler should extract status and Elasticsearch error type from the cause according to the client version. Do not parse message strings with brittle regexes when typed exceptions or structured responses are available.

### Do not retry every error

- Index not found: immediate retries usually do not help if provisioning has not created the resource.
- Alias missing write index: retries do not fix aliases.
- Read-only block: retries add load and continue failing.
- Security exception: retries do not grant permissions.
- Mapping error: retrying the same payload keeps failing.
- Transient timeout: may retry per policy, but requires idempotency and attempt limits.

Classify errors before deciding to retry, create indices, switch aliases, or stop a job.

## 16. Designing startup checks for the application

Applications can check prerequisites at startup or in readiness checks:

- Cluster endpoint responds.
- Required indices/aliases resolve.
- Write alias has the right write index.
- Required mappings exist.
- Index is not write-blocked if the service needs to write.
- Service account has necessary privileges.
- Index templates and lifecycle policies align.

Do not automatically clear blocks or arbitrarily recreate indices inside a startup check. Startup checks should detect and report contextual errors. Modifying cluster state should belong to controlled provisioning/operations workflows.

### Readiness vs. liveness

If Elasticsearch is temporarily unavailable, readiness can mark the instance as unable to serve Elasticsearch-dependent traffic. Liveness should reflect whether the process is alive; do not continuously restart the application just because the cluster temporarily lost connectivity.

If all replicas restart due to an Elasticsearch error, the system can create a connection storm when the cluster recovers.

### Health indicators

Spring Boot Actuator can provide an Elasticsearch health indicator depending on starter and version. You can use a custom health indicator to check critical aliases or indices in addition to checking cluster connectivity.

Health checks should not perform real write operations on every probe. Use metadata/read-only checks or a controlled canary strategy if the write path needs verification.

## 17. Managing indices and aliases through provisioning

For production, manage the index lifecycle with a deliberate workflow:

1. Create index templates with settings and mappings.
2. Create the physical index or let rollover create it per policy.
3. Create read/write aliases.
4. Verify is_write_index.
5. Grant proper privileges to the service account.
6. Check index blocks and cluster health.
7. Allow the application to receive traffic.

Provisioning can be executed by a deployment job, migration tool, or infrastructure automation. The runtime application only needs to use stable aliases and report clear errors if resources are not ready.

### Do not let multiple instances race to manage aliases

If every instance creates indices and updates aliases at startup, multiple instances may run unsynchronized operations. This easily leads to mispointed aliases or unintended write index switches.

A migration/provisioning job with clear ownership makes index and alias changes inspectable, auditable, and rollback-capable.

## 18. Integration tests for index not found and aliases

Tests should use real Elasticsearch or compatible Testcontainers to verify alias behavior.

### Testing missing index

- Create a test index with a different name from the target.
- Run a search or write against the non-existent target.
- Verify the application receives the expected error.
- Do not auto-create indices outside test policy.

If auto-create is enabled, disable it in the test cluster or use a user without auto-create privileges to properly test index not found.

### Testing an alias pointing to one index

- Create orders-000001.
- Create alias orders-write with is_write_index: true.
- Write through the alias.
- Verify the document appears in the physical index.

### Testing an alias pointing to multiple indices

- Create two physical indices.
- Create a read alias pointing to both.
- Verify searches through the read alias find documents in both.
- Create a write alias or configure an explicit write index.
- Test the multi-index alias case without a write index and verify the error.

### Testing alias switching

- Create an old index and a new index.
- Attach the write alias to the old index.
- Perform _aliases remove/add in a single request.
- Write through the alias after cutover.
- Verify new documents go to the new index and old data remains readable via the read alias as designed.

## 19. Integration tests for write blocks

Tests can enable a block on a test index:

~~~http
PUT /orders-test/_settings
{
  "index.blocks.write": true
}
~~~

Then attempt a save operation and confirm the request fails due to the block.

Remove the block when the test finishes:

~~~http
PUT /orders-test/_settings
{
  "index.blocks.write": null
}
~~~

Tests should use a dedicated index and ensure cleanup even when assertions fail. Do not enable blocks on indices shared with other tests.

For read_only_allow_delete caused by flood-stage, do not simulate flood-stage by filling up CI disk space. You can test application exception handling with fixtures/error mapping, while block semantics should be tested on a dedicated, controlled Elasticsearch environment.

### Testing distinction between 403 block and 403 security

Write one test for an index block and one test for a user lacking privileges. Verify the application classifies the error type accurately rather than turning both into the same "index not found" message.

## 20. Common errors and solutions

| Symptom | Possible cause | Solution |
|---|---|---|
| index_not_found_exception on save | Index/alias does not exist yet or wrong target | Resolve name and check provisioning |
| Only one profile gets 404 | Endpoint or index suffix differs across environments | Compare effective configuration and cluster |
| Alias exists but writes fail | Alias points to multiple indices without write index | Set is_write_index explicitly |
| Writing to old index after rollover | Write alias did not switch | Check alias and rollover result |
| HTTP 403 on write | Block or security privilege | Read error.type and reason |
| cluster_block_exception after disk pressure | Flood-stage set read-only-allow-delete | Free disk space, verify, then clear block |
| security_exception | Service account lacks index privileges | Grant least-privilege permissions |
| Index auto-created with wrong mapping | Auto-create hid provisioning mistake | Use templates and proactive index management |
| Startup index creation fails intermittently | Multiple instances racing exists/create | Provision once and handle create races |
| Search via alias missing old data | Read alias does not point to all indices | Check membership and cutover |
| Repository uses wrong index | Wrong @Document or IndexCoordinates | Inspect actual target in logs |
| Block cleared but error returns | Disk or policy root cause unresolved | Resolve root cause before clearing |
| Tests pass but production returns 404 | Tests use pre-created dedicated index | Verify provisioning and aliases in a production-like setup |

## 21. Step-by-step troubleshooting runbook

When the application reports it cannot write documents:

**Step 1 — Preserve the original error.** Record operation, target, status, error.type, and error.reason. Do not log only a wrapped service-layer message.

**Step 2 — Identify the cluster.** Check the endpoint and profile the instance is using. An index may exist in staging but not in production.

**Step 3 — Resolve the target.** Check whether the name is an index, alias, or data stream. List alias membership and the write index.

**Step 4 — Check index state.** Check whether the index is open, mappings/settings match expectations, and which blocks are active.

**Step 5 — Check disk and allocation.** If there is a read-only block, inspect disk watermarks, nodes, and allocation before changing settings.

**Step 6 — Check permissions.** Confirm the service identity has required privileges on the target index or alias.

**Step 7 — Fix the root cause.** Provision resources from templates, switch aliases atomically, grant least-privilege permissions, or resolve disk issues and clear blocks per procedure.

**Step 8 — Verify both writes and reads.** Write a test document with a known ID, read it back by ID or search after refresh, and verify the document landed in the expected physical index.

**Step 9 — Monitor after recovery.** Watch 404/403 errors, indexing rejections, disk usage, and alias targets to confirm the incident does not recur.

Do not delete indices or clear blocks solely to make errors disappear. Those actions can cause data loss or mask the original cause.

## 22. Operational checklist

- [ ] Index/alias names are centrally managed.
- [ ] Endpoints and profiles are verified per environment.
- [ ] Index templates, mappings, and settings are provisioned before writes.
- [ ] The application clearly knows whether it writes to a physical index or a write alias.
- [ ] Read and write aliases have clear, distinct purposes.
- [ ] Multi-index aliases have explicit is_write_index.
- [ ] Rollover moves the write alias to the new index properly.
- [ ] Alias cutover uses a single atomic _aliases request.
- [ ] Required indices/aliases are checked in readiness or startup validation.
- [ ] Logs preserve status, error.type, error.reason, and target.
- [ ] cluster_block_exception is distinguished from security_exception.
- [ ] Disk watermarks and index block settings are monitored.
- [ ] Read-only blocks are cleared only after the root cause is resolved.
- [ ] Index not found, alias, or write-block errors are not blindly retried.
- [ ] Integration tests exist for missing indices and alias write indices.
- [ ] Alias switching and post-cutover data verification are tested.
- [ ] Write blocks vs. missing privileges are tested separately.
- [ ] Tests use isolated indices without impacting shared data.
- [ ] Multiple application instances do not race to provision indices/aliases.

Index not found, misconfigured aliases, and write blocks all cause Elasticsearch requests to fail, yet each requires a distinct remedy. Identify the exact target Spring Data is using, inspect alias membership and write indices, read block settings alongside disk state, and only then modify the cluster. Provisioning indices with explicit mappings, separating read/write aliases, performing atomic cutovers, and logging structured error details help applications avoid silent misconfigurations and recover safely when Elasticsearch rejects operations.
