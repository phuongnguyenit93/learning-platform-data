# Controlling Indexes or Schemas and Avoiding Implicit Changes at Startup

## 1. Why do NoSQL schemas and indexes also need version management?

In the **Spring Boot Integration** module, data does not live solely in a SQL database. An application may store documents in MongoDB, write events to Cassandra, build search read models in Elasticsearch/OpenSearch, access DynamoDB, or use Couchbase. These datastores are more flexible than traditional SQL tables in some ways, yet **flexibility does not mean there is no schema, index, or data contract**.

Consider a Catalog service storing product data in MongoDB. A new release adds a query `findByTenantIdAndExternalId` and marks `(tenantId, externalId)` as unique. A developer adds `@Indexed` or `@CompoundIndex` and deploys 12 pods simultaneously. If the framework is configured to create indexes automatically at startup, multiple pods may race to build the index on a collection containing millions of documents. Several problems can occur:

- Index builds consume heavy I/O, memory, and CPU on the database cluster right during a traffic surge.
- A **unique index** fails to build because duplicate keys already exist in historical data; some pods fail to start.
- Old and new pod versions carry **conflicting index definitions**; deployment order becomes a failure source.
- A process holding overly broad DDL privileges alters structures without review or approval.
- A search engine auto-creates an index on write with **unwanted dynamic mapping**, guessing the wrong field types.

The issue is not just annotations or frameworks. It is a problem of **schema change ownership**, **cross-version compatibility**, **migration cost**, and **multi-replica rollout ordering**.

Objectives of this lesson:

1. Distinguish Java domain models, actual persisted schemas, query indexes, and data constraints.
2. Identify where Spring Data or a datastore can implicitly create or alter structures at startup or on write.
3. Separate **controlled migrations** from the startup lifecycle of traffic-serving application replicas.
4. Roll out safely across multiple pods, historical data, and asynchronous event streams.
5. Verify changes through testing, monitoring, rollbacks, and runbooks.

~~~mermaid
flowchart LR
    A["Spring Boot app replicas"] --> B["Repository / HTTP adapter"]
    B --> C[("NoSQL datastore")]
    D["Dedicated migration pipeline"] -->|"Approved, DDL privileges"| C
    E["Schema/index manifest"] --> D
    A -. "Startup: compatibility check only" .-> C
~~~

Deployment principle: **normal runtime apps read and write data with least privilege; schema and index changes are governed by a separate, versioned, observable migration process**.

## 2. How “schema” differs across NoSQL datastores

Do not copy PostgreSQL migration assumptions blindly onto every NoSQL store. Each datastore defines different structural boundaries:

| Datastore | Key structures | Risky change examples | What to manage |
| --- | --- | --- | --- |
| **MongoDB** | Collections, JSON/BSON documents, indexes (compound, unique, TTL, partial), validators. | Adding a unique index on data with duplicates; lowering TTL and wiping historical records. | Index definitions, collection validation, backfills, legacy document compatibility. |
| **Apache Cassandra** | Keyspaces, tables, partition/clustering keys, columns, secondary indexes/materialized views. | Changing partition keys, altering query shapes, or incomplete schema agreement. | CQL migrations, new-table/backfill strategies for key changes, cluster capacity. |
| **Elasticsearch/OpenSearch** | Indices, mappings, analyzers, settings, templates, aliases. | Incompatible field type/analyzer changes on populated indices; rogue dynamic mappings. | Versioned indices, reindexing, alias switches, catching up changes during cutover. |
| **DynamoDB** | Table key schemas, GSIs/LSIs, capacity, TTL settings, attribute shapes. | Adding a GSI on a huge table, bad key design, treating GSIs as strongly consistent reads. | IaC, online GSI backfills, capacity planning, query contract limits. |
| **Couchbase** | Buckets, scopes, collections, primary/secondary indexes, query plans. | Building large indexes concurrently across starting nodes; queries failing before indexes come online. | Out-of-band index provisioning, index readiness states, query rollout timing. |

Document databases may allow documents to hold varying fields, yet **the application still has a logical schema**: required fields, field types, versions, ID conventions, validation, and query expectations. Lacking enforced DDL everywhere does not mean consumers tolerate arbitrary payload changes.

### 2.1. Four schema layers to separate

1. **Application model:** Java `record`, `@Document`, `@Table`, JSON/BSON mapping, repository queries.
2. **Persisted data contract:** actual stored records, schema versions, optional fields, legacy data transformation rules.
3. **Physical query structures:** indexes, partition keys, mappings/analyzers, materialized views, GSIs.
4. **Operational configuration:** TTL, retention, capacity, replication/consistency settings, and DDL permissions.

A Java annotation expresses developer **intent**, yet does not necessarily alter existing server structures immediately. Conversely, a write API call on the server can trigger new structures **without any Java annotation** if the datastore allows implicit creation. Both sides must be controlled.

## 3. Why avoid running DDL automatically at startup?

Application startup executes concurrently and repeatedly due to:

- Rolling updates, HPA scale-outs, node replacements, and crash loops.
- Canary and blue-green deployments where two versions run side by side.
- Health checks, readiness retries, multi-tenant or multi-context startup.
- Spring Batch workers or scheduled jobs spinning up extra processes against the same datastore.

When startup creates or alters indexes, an **expensive operational action turns into an implicit side effect**, introducing concrete risks:

| Risk | Example | Outcome |
| --- | --- | --- |
| Concurrent changers | 10 pods simultaneously request creating one unique index. | Contention, noisy alerts, inconsistent startup failures. |
| No historical data check | Duplicate keys already exist. | Migration fails mid-rollout. |
| Broken compatibility | New app alters mapping while old app still writes legacy types. | Runtime errors or unreadable records. |
| Unmanaged resource load | Index build competes for I/O with live traffic. | Latency spikes and timeouts on APIs/consumers. |
| Overly broad privileges | App service account holds `CREATE`/`ALTER`/`DROP`. | Code bugs or misconfigurations mutate schema accidentally. |
| No audit trail | Unclear who created an index or changed a TTL. | Hard to roll back or trace incidents. |

**Idempotent migrations** are necessary but not sufficient. For example, `CREATE INDEX IF NOT EXISTS` might not check whether an existing index **actually matches** the new definition. An index sharing the same name with wrong column order, uniqueness flags, or TTL still breaks queries and contracts.

The goal is not “never change schemas,” but ensuring **every change has an owner, preflight checks, impact assessment, verification, and a rollback plan**.

## 4. MongoDB: disable auto-index creation and manage indexes separately

Spring Data MongoDB offers annotations like `@Indexed`, `@CompoundIndex`, `@TextIndexed`, and `@GeoSpatialIndexed` alongside entity-driven index support. However, **annotations describe mapping intent**; automatic index creation depends on Spring Data MongoDB's `autoIndexCreation` setting.

In Spring Boot 3.x, **declare your intent explicitly** rather than relying on version defaults:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
      auto-index-creation: false
~~~

With automatic index creation disabled, do not work around it by adding a startup listener or `ApplicationRunner` calling `createIndex`/`ensureIndex`. If the project customizes `MongoMappingContext` or `MongoTemplate`, verify the custom configuration does not override this policy.

### 4.1. Annotations document intent—they do not replace migrations

~~~java
package com.example.integration.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customer_profiles")
@CompoundIndex(
        name = "uq_tenant_external",
        def = "{ 'tenantId': 1, 'externalId': 1 }",
        unique = true)
public class CustomerProfile {
    @Id
    private String id;
    private String tenantId;
    private String externalId;
    private String displayName;

    // Constructors, getters, and domain logic omitted.
}
~~~

`@CompoundIndex` documents the intended index, yet under the production configuration above **does not make the app build the index at startup**. The migration owner must create, verify, and publish the index **before** deploying code that relies on uniqueness enforcement or query performance.

Watch out for legacy data: if `tenantId` or `externalId` is missing or `null`, a unique compound index may behave unexpectedly. Enforce required fields, clean up duplicate/null values, and consider a **partial index** only when the contract explicitly allows documents outside the unique constraint.

### 4.2. Creating indexes via an intentional migration

Example MongoDB migration executed by a dedicated account **after verifying zero duplicates**:

~~~javascript
// Executed in a controlled migration session, never during app startup.
db.customer_profiles.createIndex(
  { tenantId: 1, externalId: 1 },
  {
    name: "uq_tenant_external",
    unique: true
  }
);

db.customer_profiles.getIndexes();
~~~

Check for duplicates before adding a unique index:

~~~javascript
db.customer_profiles.aggregate([
  {
    $group: {
      _id: { tenantId: "$tenantId", externalId: "$externalId" },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
~~~

This query is a **starting audit check**, not a complete data plan: account for missing/`null` keys, collation, normalization (case, whitespace), tenant scope, and dataset size. Use supporting indexes or run audits during low-traffic windows to avoid overloading the cluster with full scans.

**When an index already exists:** calling `createIndex` with the same name but different options throws an error; never treat that error as “already exists, ignore.” Migrations must **compare exact keys and options, plan deliberate rebuilds**, and never drop active production indexes recklessly.

### 4.3. TTL indexes can delete real data

Example collection storing temporary events:

~~~javascript
db.integration_events.createIndex(
  { expiresAt: 1 },
  { name: "ttl_integration_events", expireAfterSeconds: 0 }
);
~~~

In MongoDB, TTL indexes evaluate a date field (e.g., BSON Date). `expireAfterSeconds: 0` marks documents eligible for expiration at the timestamp stored in `expiresAt`; the **TTL monitor deletes asynchronously**, neither guaranteeing millisecond-exact deletion nor replacing strict retention compliance mechanisms.

Lowering a TTL from days to minutes can mark huge volumes of historical records eligible for deletion immediately; require dry-runs, affected-row counts, backups, delete-load checks, and explicit approval. Never alter TTL indexes automatically at startup.

## 5. Cassandra: CQL schemas and partition key compatibility

In Spring Data Cassandra on Spring Boot 3.x, disable automatic schema generation/alteration from entity mappings:

~~~yaml
spring:
  cassandra:
    keyspace-name: integration_app
    contact-points: cassandra.internal
    local-datacenter: dc1
    schema-action: none
~~~

`schema-action: none` ensures the application **performs no schema management actions** while setting up mappings; keyspaces and tables must be provisioned beforehand. If the project defines custom `SessionFactory` or `CqlSession` beans, verify they do not execute DDL either.

### 5.1. CQL migrations executed once

~~~sql
-- Example CQL executed by an operational migration workflow.
CREATE TABLE IF NOT EXISTS integration_app.order_events (
    tenant_id text,
    event_id text,
    occurred_at timestamp,
    payload text,
    schema_version int,
    PRIMARY KEY ((tenant_id), event_id)
);
~~~

The key `((tenant_id), event_id)` sets **`tenant_id` as the partition key** and `event_id` as the clustering key. This illustrates querying by tenant and event ID, yet may be unsuitable if a single tenant accumulates millions of events in one partition. Real designs must follow **access patterns**, partition sizing, hot-partition avoidance, time buckets, consistency, and retention.

In Cassandra, changing an existing table's **partition or clustering key** cannot be done like a simple `ALTER TABLE ADD column`. The standard approach is:

1. Create a new table with keys/partitioning tailored to the new query.
2. Backfill data with rate limiting and completeness checks.
3. Switch read/write paths or maintain bounded dual-writes per a verified cutover plan.
4. Reconcile data, monitor consistency/latency, and drop the old table only after the rollback window expires.

### 5.2. Do not confuse schema agreement with data readiness

CQL changes take time to propagate across nodes (**schema agreement**). Accepting a DDL statement does not mean backfills, index builds, or materialized views are ready for production traffic. Migrations must wait for healthy completion, verify query plans/latencies, and only then expose the new structure to apps.

Do not slap secondary indexes onto every column whenever a new filter appears. Secondary indexes, materialized views, and SAI (where supported) carry distinct costs and limits depending on Cassandra version, data cardinality, and query shapes. Design **tables per query**, benchmark under realistic load, and choose indexing strategies deliberately.

## 6. Elasticsearch/OpenSearch: decouple indices, mappings, and aliases from startup

In search engines, mappings govern field types, analyzers, and document indexing. Many changes—like switching a field from `text` to `keyword` or altering an analyzer—**cannot be applied in place to re-interpret existing indexed documents**.

With Spring Data Elasticsearch, disable repository-driven index creation via `createIndex = false`:

~~~java
package com.example.integration.search;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders-search", createIndex = false)
public class OrderSearchDocument {
    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String orderId;

    @Field(type = FieldType.Text)
    private String description;

    // Constructors/getters omitted.
}
~~~

Assuming `orders-search` is an **alias** pointing to a versioned physical index, this annotation **only controls Spring Data's index-creation behavior**; it **does not disable** server-side auto-creation if the cluster allows creating indices automatically on write to an unknown name. Configure server-side permissions/settings and provisioning properly so a misnamed target never spawns an unintended physical index with dynamic mapping.

### 6.1. Create a new versioned index and swap the alias

General workflow:

~~~text
orders-search (alias) -> orders-search-v1

Migration:
  1. Create orders-search-v2 with new mapping, analyzers, and settings.
  2. Backfill/reindex data from authoritative source or v1 as appropriate.
  3. Catch up changes occurring during the backfill window.
  4. Verify counts, query correctness, lag, and access permissions.
  5. Switch alias orders-search from v1 to v2 in a controlled step.

orders-search (alias) -> orders-search-v2
~~~

Example REST request declaring an explicit mapping:

~~~http
PUT /orders-search-v2
Content-Type: application/json

{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "tenantId": { "type": "keyword" },
      "orderId": { "type": "keyword" },
      "description": { "type": "text" }
    }
  }
}
~~~

Once `v2` is populated and validated, swap the alias atomically:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "orders-search-v1", "alias": "orders-search" } },
    { "add": { "index": "orders-search-v2", "alias": "orders-search" } }
  ]
}
~~~

These REST examples are **illustrative** for Elasticsearch; verify version syntax and OpenSearch differences before executing. If an alias serves both reads and writes, manage `is_write_index` and concurrent writes during the swap. Switching an alias **does not automatically sync** updates emitted after reindexing started—use CDC/outbox, reconciled dual-writes, or the authoritative source to close the gap.

**Dynamic mapping** is a second hidden source of schema drift: even if application startup creates no indices, writing a document with an unexpected field can mutate the mapping if permitted by the server. For strict contracts, consider `dynamic: strict`, versioned index templates, and CI contract tests. Avoid turning `dynamic: strict` on blindly if legitimate extensible metadata is needed; isolate arbitrary metadata in dedicated containers instead.

## 7. DynamoDB and Couchbase: app startup is not a migration pipeline

### 7.1. DynamoDB

In DynamoDB, **table partition/sort keys**, GSIs/LSIs, TTLs, and capacity modes are infrastructure resources best managed via **IaC** (CloudFormation, CDK, Terraform, or your organization's approved tooling). Adding a field to a Java entity/DTO does not magically provision a **GSI** for querying it.

Key considerations:

- A new GSI requires **backfilling** and passes through transitional states before becoming active; applications must not query an index before it is ready.
- GSIs normally offer **eventual consistency**; never expect strongly consistent read-after-write from a GSI just because a base-table transaction succeeded.
- TTL expiration runs asynchronously; never treat TTL as exact-to-the-second deletion or the sole compliance mechanism.
- Changing key designs is not just changing an annotation: it typically requires a new table, data migration, dual-reads/writes, and a cutover.

Grant the Spring Boot runtime SDK only required table read/write IAM permissions—**never table/index administration privileges** in normal runtime processes. Give migration jobs separate identities/permissions and monitor them so building a GSI on a huge table never degrades live availability.

### 7.2. Couchbase

In Couchbase, buckets, scopes, collections, and primary/secondary indexes must be provisioned to fit query workloads. Adding a repository query method does not mean the required index is online. Building large indexes or altering collection layouts consumes cluster resources and causes drift across environments.

Use separate provisioning/migration steps, check `index state` and query plans, and roll out new code only once indexes are online. With multiple replicas, never let every pod run `CREATE INDEX` while serving live traffic. Even with flexible JSON schemas, manage versions, validation, and legacy document transformations explicitly.

## 8. Designing a migration pipeline separate from app startup

A sound pipeline produces **versioned artifacts**, runs once per target datastore, and records execution results:

~~~mermaid
flowchart TD
    A["Pull request changing model/query"] --> B["Design contract + access pattern"]
    B --> C["Versioned migration + review"]
    C --> D["Preflight: duplicates, capacity, current schema"]
    D --> E["Create index/schema in separate rollout"]
    E --> F["Wait for index/schema readiness"]
    F --> G["Backfill + reconciliation + metrics"]
    G --> H["Deploy app using new structure"]
    H --> I["Monitor + clean up old version"]
~~~

Concrete principles:

1. **Version migrations** per datastore and collection/table/index, documenting ID, goal, risk, and execution status.
2. **Execute migrations under a single owner** (CI/CD job, release task, or dedicated migration tool); block concurrent runs targeting the same namespace.
3. **Separate migration credentials** from runtime application credentials, granting scoped DDL privileges only to migrations.
4. **Preflight drift checks:** verify current structures match the expected baseline, check duplicates/nulls, and confirm disk/I/O headroom before building indexes.
5. **Verified idempotency:** re-running succeeds without extra side effects, yet **fails loudly** if an existing definition differs from the desired spec.
6. **Observable progress:** duration, index build status, backfill lag, mismatched record counts, p95/p99 latency, replication lag, and quota/capacity.
7. **Gated rollout:** new app code uses new queries/indexes only once migrations are ready, while older code stays compatible through the transition window.

A migration manifest/changelog entry might look like:

~~~yaml
# Example pipeline-managed migration metadata, not Spring Boot config.
id: catalog-2026-11-21-04
store: mongodb
target: customer_profiles
operation: create-compound-unique-index
indexName: uq_tenant_external
preconditions:
  - no-duplicate-tenant-external-key
  - enough-disk-and-io-headroom
postconditions:
  - index-spec-matches-approved-definition
  - index-visible-to-application
rollbackPolicy: reviewed-manual-plan
~~~

These keys are illustrative conventions; no default Spring library interprets or executes this YAML automatically. What matters is preserving **change requests and execution evidence** for traceability.

### 8.1. Never use startup hooks to replace a migration pipeline

Avoid this pattern in traffic-serving applications:

~~~java
// Do NOT use in production services.
@Bean
ApplicationRunner createIndexesOnEveryStartup(MongoTemplate template) {
    return args -> template.indexOps("customer_profiles")
            .ensureIndex(new Index()
                    .on("tenantId", Sort.Direction.ASC)
                    .on("externalId", Sort.Direction.ASC)
                    .unique());
}
~~~

Even though `ensureIndex` can be a no-op in some cases, this turns startup into an unapproved migration with unpredictable cost repeated across every replica. **Better:** run DDL in an isolated migration pipeline, and restrict startup to verifying the store meets the expected contract.

## 9. Read-only compatibility checks at startup

Disabling automatic DDL does not mean starting “blind.” If a feature depends on a new index or mapping, startup can **read metadata using read-only permissions** and fail readiness if the datastore has not reached a compatible version.

Example migration marker document stored in MongoDB:

~~~json
{
  "_id": "catalog",
  "schemaVersion": 4,
  "lastMigration": "catalog-2026-11-21-04"
}
~~~

A read-only preflight check in Spring Boot:

~~~java
package com.example.integration.catalog;

import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration(proxyBeanMethods = false)
class CatalogSchemaCompatibilityConfiguration {

    @Bean
    ApplicationRunner verifyCatalogSchema(MongoTemplate mongoTemplate) {
        return args -> {
            Document marker = mongoTemplate
                    .getCollection("integration_schema_metadata")
                    .find(eq("_id", "catalog"))
                    .first();

            if (marker == null) {
                throw new IllegalStateException(
                        "Catalog schema marker is missing");
            }

            Integer version = marker.getInteger("schemaVersion");
            if (version == null || version < 4 || version > 5) {
                throw new IllegalStateException(
                        "Unsupported catalog schema version: " + version);
            }
        };
    }
}
~~~

This is a **minimal baseline check**, not proof that every index is intact. A marker is only trustworthy if the **migration pipeline updates it after verifying all postconditions**. When critical index readiness must be confirmed, startup or readiness preflights can **inspect and compare index definitions** (keys, uniqueness, partial/TTL options) with read permissions—never modifying them.

Crucial rules for rolling deployments:

- App versions N and N+1 may run simultaneously. Support a **compatible version range** rather than strictly asserting `schemaVersion == currentVersion` on every replica.
- Scope version markers accurately per **datastore/database/tenant**; avoid a global marker claiming success while one namespace remains unmigrated.
- When the datastore is temporarily unreachable, handle startup/readiness failure per SLOs and resilience rules; never trigger DDL or reset schemas on error.
- Keep metadata checks lightweight so simultaneous restarts do not create load spikes; cache status appropriately with bounded retry/backoff.

**Read-only permissions on runtime app startup** add defense in depth: even if code accidentally calls a collection/index creation API, the server rejects it instead of mutating schemas silently.

## 10. Expand–migrate–contract when multiple versions run concurrently

Upgrades must never assume “every pod switches versions instantaneously.” Suppose you want to split `customerFullName` into `givenName` and `familyName` inside documents:

| Phase | Change | Completion criteria |
| --- | --- | --- |
| **Expand** | Readers support both old and new formats; writers start emitting new fields when appropriate. | Old code still works; required schemas/indexes provisioned beforehand. |
| **Migrate** | Backfill historical data with checkpoints and error tracking; optional bounded dual-writes. | Target migration percentage reached; backlogs and drift reconciled. |
| **Cutover** | Point consumers, queries, or search aliases to the new structure. | Latency, metrics, and correctness meet SLOs. |
| **Contract** | Stop reading/writing old fields; remove old indexes/tables safely. | Zero legacy processes remain; rollback and retention windows passed. |

~~~mermaid
sequenceDiagram
    participant Old as App N
    participant New as App N+1
    participant DB as NoSQL
    participant Migrator as Migration pipeline
    Migrator->>DB: Expand backward-compatible schema/index
    Old->>DB: Read/write old contract
    New->>DB: Read both contracts
    Migrator->>DB: Backfill data
    New->>DB: Switch to new contract
    Note over Old,New: Wait until all old replicas exit cluster
    Migrator->>DB: Clean up old structures with approval
~~~

In Elasticsearch/OpenSearch, expand typically means **creating physical index v2, reindexing, and swapping aliases**; in Cassandra, changing a partition key means **creating a new table and shifting traffic**; in MongoDB, adding fields/indexes in the existing collection works if compatibility is preserved.

Backfills require **checkpoints, idempotency, rate throttling, and resumability after crashes**. Use Spring Batch or a dedicated job—never kick off long backfills inside API pod startup. When publishing events to Kafka/RabbitMQ or updating NoSQL read models, include event IDs and schema versions so consumers deduplicate and handle out-of-order delivery cleanly.

## 11. Controlling risks with unique indexes, TTL, and index builds

### 11.1. Unique indexes: not just a performance tweak

A unique index enforces a **business rule**. If historical records contain duplicates, index creation fails. If the app keeps accepting writes, new duplicates can slip in **after the preflight check but before the index takes effect**.

A solid plan:

1. Agree on exact uniqueness semantics (tenant scope, case normalization, null/blank handling, collation, soft deletes).
2. Audit and resolve existing duplicates with audit trails and reconciliation.
3. Ensure all write paths stop producing new duplicates (idempotency, validation, staged checks).
4. Build the unique index when the cluster has capacity and verify final index state.
5. Run concurrent insert/update tests to confirm enforcement works.

Multi-source write systems must never rely solely on HTTP endpoint validation: Batch jobs, broker consumers, and admin scripts can also insert duplicates. Datastore unique indexes provide a final safeguard, provided key shapes and duplicate-handling paths are tested.

### 11.2. TTL and retention changes can be irreversible

TTL indexes or settings govern **real data deletion**, not just cache eviction. Lowering a TTL can permanently purge historical records. In NoSQL systems, expiration runs asynchronously and can spike disk I/O. For audit, billing, or compliance data, clearly separate mandatory retention data from disposable temporary records.

### 11.3. Index builds impact live queries

Building an index over large datasets generates CPU, I/O, and network pressure, replica lag, and extra storage usage. “Online” DDL does not mean zero impact. Before executing:

- Estimate index size, free disk headroom, build duration, and latency budgets.
- Check managed service rate limits/quotas and potential impact on co-located workloads.
- Monitor progress with explicit abort/rollback criteria if p95/p99 breaches thresholds.
- Never trigger multiple heavy index builds or backfills simultaneously during rolling deploys.
- Route app traffic to queries needing the new index only after the index is active and contract tests pass.

## 12. Security and separating application vs. migration permissions

Privilege separation enforces discipline far better than code conventions alone:

| Identity | Required privileges | Must not have |
| --- | --- | --- |
| **Application runtime** | Read/write documents/records and query existing indexes in granted collections/tables. | Broad rights to drop collections, alter schemas, or create indexes freely. |
| **Migration runner** | Scoped DDL/index/schema changes, updating version markers, reading verification metrics. | Unrelated app secrets or full cluster admin rights when unnecessary. |
| **Read-only preflight/monitor** | Inspecting schema versions, index/schema state, and permitted metrics. | Any mutation or deletion rights. |

Exact privilege syntax varies by datastore: custom MongoDB roles, Cassandra `GRANT` per keyspace/table, Elasticsearch/OpenSearch index/alias roles, or IAM policies for DynamoDB tables/indexes. Never assume a built-in role named `readWrite` excludes every index-creation command; inspect **exact granted actions**.

Store secrets in a secret manager, isolate credentials per environment, and keep URIs/credentials out of logs. Keep migration audit trails capturing operator, version, timestamp, target, before/after specs, and outcome. When CI/CD runs DDL jobs, serialize runs per target so concurrent pipelines never apply conflicting changes.

## 13. Proper testing: proving startup never alters schemas

An application context booting cleanly **does not prove no implicit DDL ran**. Write targeted tests:

| Test | Assertion to prove |
| --- | --- |
| MongoDB with `auto-index-creation: false` | Context/repository startup creates no missing collection/index; only migrations do. |
| MongoDB index spec drift | Startup neither drops nor rebuilds; preflight detects mismatched spec and fails clearly. |
| MongoDB unique index with duplicates | Migration fails gracefully instead of looping index builds per pod. |
| MongoDB TTL change | Dry-run reports eligible deletions; retention never shifts silently. |
| Cassandra `schema-action: none` | Startup runs no `CREATE`/`ALTER` keyspace/table; missing schema reports clearly. |
| Elasticsearch `createIndex=false` | Repository startup creates no index; server auto-create and dynamic mapping stay controlled. |
| Elasticsearch reindex + alias | Index v2 contains full data, lag closed, alias swap drops zero updates. |
| Multiple concurrent replicas | Single migration runner owns DDL; runtime runs read-only preflight only. |
| Rolling deploy N and N+1 | Both versions remain schema-compatible during expand and migrate phases. |
| Interrupted backfill | Resumes from checkpoint without creating duplicates or regressing newer versions. |
| Runtime account lacking DDL rights | Unintended DDL calls are denied; valid read/write paths still succeed. |
| App downgrade/rollback | Never assume index/key schemas revert automatically; contract stays compatible or recovery exists. |

Use Testcontainers or dedicated test clusters for MongoDB/Cassandra/Elasticsearch/OpenSearch, and approved test environments for DynamoDB/Couchbase. In startup tests, **snapshot metadata before and after startup** to compare indexes, collections, schemas, mappings, and aliases—never rely solely on HTTP health returning 200.

An integration test workflow:

1. Start an empty datastore or snapshot holding an **older schema version** via migration fixtures.
2. Boot the application **using a runtime identity without DDL permissions**.
3. Verify the app only reads metadata and fails clearly when the schema is incompatible.
4. Execute the migration **separately**; inspect resulting index specs/options and version marker.
5. Boot apps N and N+1; run contract CRUD/queries, concurrent writes, and simulated backfill crashes.
6. Diff metadata post-test to confirm zero stray changes from startup, repositories, or automatic writes.

Never run all tests under a single admin account and declare there is no DDL risk: overly broad test credentials hide accidental runtime DDL calls.

## 14. Observability and schema/index incident response

### 14.1. Signals to collect

- **Migration status:** change ID, start/end timestamps, executor, target, preflight/outcome, errors, completion time.
- **Index health:** build progress, online/ready status, size, memory/disk usage, errors, and spec drift.
- **Query performance:** read/write latency p50/p95/p99, slow queries, full scans, query plans, workload saturation.
- **Cluster capacity:** CPU, I/O, disk, replication lag, schema agreement, indexing throughput, throttling.
- **Backfill/reindex:** pending queue depth, source vs. target counts, checksum/count diffs, duplicates/rejections.
- **Contract compatibility:** deserialization failures, unknown fields, mapper errors, mapping/type rejections, rejected queries.

Scope metric labels by datastore, collection/index type, and migration ID with bounded cardinality. Never put document IDs, emails, tokens, or unbounded tenant keys into public metric labels or alerts.

### 14.2. Runbook: new app release fails right after rollout

Suppose new code queries index `uq_tenant_external`, yet one environment missed the migration:

1. **Isolate scope:** identify failing pods, repositories, datastores, connection credentials, and namespaces.
2. **Inspect actual structure with read-only access:** index list/specs, options, version markers, aliases, index build state.
3. **Assess impact:** unindexed queries may run slowly while still returning valid results, whereas missing schemas/mappings break operations outright—distinguish the two.
4. **Do not re-enable auto-create in production as a hotfix** without evaluating data state and build load.
5. **Recover safely:** pause rollout or shift traffic off the new version, run the verified migration, or revert to an app version compatible with the current schema.
6. **Monitor:** query latency, lag, locks/I/O, backfill progress, duplicates, and all replica states.
7. **Follow up:** add preflights, release gates, and tests so environments cannot skip migrations again.

### 14.3. Runbook: unique index creation fails

1. Capture the exact error, index name/spec, and count of duplicate records per true uniqueness rules.
2. Halt or guard write paths that could introduce new duplicates while remediating.
3. Reconcile and clean duplicates **under business ownership**—never delete arbitrary records just to clear a key conflict.
4. Re-run the migration after verifying preconditions; confirm index creation and constraint enforcement.
5. Resume rollout after verifying all writers (HTTP, Batch, broker consumers) share identical idempotency and normalization rules.

**Never “fix” schema failures by dropping the collection or wiping all indexes** just to make the app boot. Schema failures are **data and contract issues**, not mere DDL syntax errors.

## 15. Pre-release checklist for NoSQL applications

- [ ] Defined **schema/index owners** and migration version tracking for every datastore.
- [ ] Disabled or tightly controlled framework auto-creation of indexes/schemas at startup, distinct from **server-side auto-create and dynamic mapping**.
- [ ] Stripped unnecessary DDL rights from runtime service accounts; migrations use separate, approved, audited credentials.
- [ ] Preflight checks and historical data plans prepared for unique indexes, TTLs, partition keys, analyzers, GSIs, and retention changes.
- [ ] Idempotent migrations compare **full specifications**; same name with mismatched spec fails as drift.
- [ ] Pipelines create and verify indexes/schemas before app N+1 depends on them, gating on index builds/backfills.
- [ ] Apps N and N+1 remain compatible during rolling/canary/blue-green rollouts; cleanup waits until zero old consumers remain.
- [ ] Backfills/reindexes use checkpoints, throttling, deduplication, and reconciliation; async events include schema versions and ordering guards.
- [ ] Startup runs only **lightweight read-only preflights**; zero DDL, backfills, or unexpected data mutations.
- [ ] Tests verify metadata before/after startup, multiple replicas, drift, legacy schemas, rollbacks, and failed migration recovery.
- [ ] Dashboards monitor query/index latency, migration history, lag, and include runbooks for schema/index incidents.

**Conclusion:** whether using MongoDB, Cassandra, Elasticsearch/OpenSearch, DynamoDB, or Couchbase, **indexes and schemas are operational assets to be governed like contracts**, not implicit side effects fired every time Spring Boot boots. Separating migrations from runtime, enforcing least privilege, versioning rollouts, and testing multi-replica and rollback paths ensures NoSQL integrations deliver both performance and data integrity as the system evolves.
