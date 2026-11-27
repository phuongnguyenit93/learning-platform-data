# OpenSearch Shards, Replicas, and Time-Series Data Management

Amazon OpenSearch Service stores data in indexes, splits each index into shards, and distributes shards across data nodes. Primary shards partition the source data; replica shards are copies of primary shards that improve fault tolerance and can serve search queries. The number of shards, replicas, nodes, and their distribution across Availability Zones directly affect capacity, throughput, latency, recovery time, and cost.

With logs, metrics, events, and observability data, record volume grows continuously. Creating unbounded indexes or keeping all data on high-performance storage tiers inflates shard counts, consumes heap, degrades balance, and steadily drives up cost. Consequently, architectures must combine shard sizing, replica strategies, rollover, retention, snapshots, and storage tiering.

This lesson focuses on Amazon OpenSearch Service domains within the AWS ecosystem. Learners will understand how to choose shard counts, replica counts, distribute data across nodes/AZs, manage time-based indexes using Data Streams and Index State Management (ISM), and transition data from hot storage to UltraWarm and cold storage. Decisions must be grounded in actual workloads, query needs, RPO/RTO, and data retention policies.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Explain indexes, documents, primary shards, replica shards, nodes, and clusters.
- Distinguish the roles of primaries and replicas across writes, reads, availability, and recovery.
- Estimate primary shard counts based on data volume, growth, and workload type.
- Identify over-sharding, under-sharding, shard skew, and unassigned shards.
- Design replica counts and Multi-AZ topologies matching durability/availability targets.
- Understand constraints around changing primary shard counts and choose reindex, shrink, or split when needed.
- Design time-based indexes, rollover aliases, or Data Streams.
- Create index templates to enforce uniform mappings, settings, and policies on new indexes.
- Use ISM to roll over, reduce replicas, force merge, snapshot, migrate tiers, and delete data.
- Distinguish hot, UltraWarm, and cold storage in Amazon OpenSearch Service.
- Monitor shard allocation, cluster health, storage, JVM, indexing/search latency, and lifecycle actions.
- Build retention policies that are auditable, recoverable, and cost-controlled.

## 2. How Does OpenSearch Store Data?

An Amazon OpenSearch Service domain is a cluster composed of specialized nodes:
- **Data nodes** store shards and process indexing/search.
- **Dedicated cluster manager nodes** manage cluster state, node membership, index metadata, and shard allocation; they do not serve regular data queries.
- **Coordinating nodes** accept client requests, route them to appropriate shards, and aggregate results. In many configurations, data nodes also act as coordinating nodes.
- **UltraWarm nodes** serve read-only indexes on the warm tier.
- **Cold storage** stores infrequently accessed indexes backed by Amazon S3; indexes attach to warm nodes when queried.

An index is analogous to a logical table in a database. A document is analogous to a JSON record. A field is a document attribute. OpenSearch uses mappings to define how each field is indexed and queried.

An index can consist of multiple primary shards. Each primary shard is an independent partition of the index. When creating a document, OpenSearch picks the target shard using routing—typically derived from document ID or a routing key. Each primary shard can have one or more replica shards.

Example:

~~~text
Index: orders
  Primary shard 0  ---> Replica shard 0
  Primary shard 1  ---> Replica shard 1
  Primary shard 2  ---> Replica shard 2

Data nodes:
  Node A: Primary 0, Replica 1
  Node B: Primary 1, Replica 2
  Node C: Primary 2, Replica 0
~~~

A replica holds a copy of its corresponding primary's data. OpenSearch places primaries and replicas of the same shard on different nodes so a single node failure cannot lose all copies of a shard. With zone awareness enabled, the service distributes copies across Availability Zones per domain topology.

A shard is the unit of distribution, recovery, and query execution. Too few shards can underutilize cluster resources; too many shards add management and heap overhead. Shard sizing and allocation matter more than simply adding nodes.

## 3. Primary Shards and Replica Shards

### 3.1 Primary Shards

A primary shard is the authoritative partition of an index. When a client sends an index, update, or delete request, OpenSearch resolves the corresponding primary shard. The primary processes the operation and replicates changes to replicas.

The primary shard count is set at index creation. In Amazon OpenSearch Service, the default for an index is commonly **5 primary shards and 1 replica per primary**, totaling 10 shard copies. This default differs from upstream OpenSearch, where the default is often 1 primary and 1 replica. Therefore, never leave defaults unexamined for your workload.

Primary shard count affects:
- Indexing parallelism.
- Number of shards involved per query.
- Size per shard.
- Corresponding replica count.
- Heap, file handle, CPU, and recovery overhead.

### 3.2 Replica Shards

A replica shard is a copy of a primary shard. Replicas serve two roles:

1. **Fault tolerance:** if a node holding a primary fails, an eligible replica can be promoted to primary.
2. **Read capacity:** search requests can route to primaries or replicas, distributing query load.

Replicas do not replace backups. Accidental deletions, bad updates, or corrupted ingestions replicate straight to replicas. To recover data to a prior point in time, you need snapshots or a replayable data source.

### 3.3 Impact of Replicas on Workloads

Suppose an index has 4 primary shards:

| Replica Count | Total Shard Copies | Impact |
|---:|---:|---|
| 0 | 4 | Lower storage and write replication; zero redundancy on shard/node failure |
| 1 | 8 | One extra copy per primary; adds redundancy and read capacity |
| 2 | 12 | Two extra copies; distributes across three AZs with proper topology |
| 3 | 16 | Adds read capacity and redundancy, but increases storage, network, and write work |

Each replica adds roughly a full copy of the index. Increasing replicas scales read capacity and fault tolerance, yet does not increase primary partition count or primary write parallelism the way adding primary shards does.

During continuous writes, primaries replicate changes to replicas. Higher replica counts increase network traffic and write amplification. Benchmark your read/write mix before adding replicas just to "speed things up."

### 3.4 When Can Replicas Be Reduced?

For historical read-only data, some organizations reduce replicas to save storage. Amazon OpenSearch Service can use ISM `replica_count` to automatically reduce replicas after a retention window.

Do this only when:
- Writes to the index have stopped.
- Snapshots or replayable source data exist.
- Availability policies permit reduced redundancy.
- The index no longer serves critical production SLAs.
- Restore tests and runbooks exist.

Setting replica count to 0 eliminates replica promotion if the primary node fails. That is a durability trade-off, not merely a disk-saving tweak.

## 4. Cluster Health and Shard Allocation

OpenSearch reports cluster status based on how primary and replica shards are allocated.

| Status | Meaning | Action |
|---|---|---|
| Green | All primary and replica shards are allocated | Monitor trends and capacity |
| Yellow | All primaries are allocated, but one or more replicas are unassigned | Check nodes, AZs, disk watermarks, replica counts, and allocation rules |
| Red | At least one primary shard is unassigned | Prioritize restoring data/primaries; check node failures and snapshots |

Yellow does not mean primary data is lost, though redundancy is degraded. Red means part of an index's data cannot be queried completely.

Common causes of unassigned shards:
- Insufficient data nodes or offline nodes.
- Replicas cannot reside on the same node as their primary.
- Insufficient disk space or breached disk watermarks.
- Allocation awareness/filters exclude all eligible nodes.
- Shard recovery or relocation is throttled.
- Exceeded per-node or cluster-wide shard limits.
- Mapping, plugin, or version incompatibilities after cluster changes.
- Newly added nodes lack capacity to accept shards yet.

Useful inspection APIs:

~~~http
GET _cluster/health?pretty
GET _cluster/health?level=indices
GET _cat/nodes?v
GET _cat/shards?v
GET _cat/allocation?v
GET _cluster/allocation/explain
~~~

`_cluster/allocation/explain` gives exact reasons why a shard is unassigned or why it resides on its current node. Never blindly add nodes or disable allocation rules before reading the explanation.

## 5. Choosing Primary Shard Count

### 5.1 Target Shard Sizes

AWS recommends starting with these reference ranges:

| Workload Type | Suggested Primary Shard Size |
|---|---:|
| Low-latency search | 10–30 GiB |
| Log analytics and write-heavy workloads | 30–50 GiB |

These are starting benchmarks, not hard limits for every index. Oversized shards slow down recovery, relocation, and segment queries. Undersized shards inflate shard counts, metadata, heap usage, file handles, and scheduling overhead.

Avoid creating hundreds of tiny shards just to touch every node. For a 5 GiB index, one primary shard often makes more sense than many primary shards of a few hundred MiB each.

### 5.2 Estimation Formula

Rough estimate for primary shard count:

~~~text
Primary shard count
  ≈ (Source data + Growth allowance)
     x (1 + Indexing overhead)
     / Target primary shard size
~~~

Where:
- Source data is the expected raw volume to index.
- Growth allowance covers expected expansion over the planning horizon.
- Indexing overhead accounts for mappings, inverted indexes, doc values, stored fields, and Lucene structures.
- Target shard size is the desired primary shard size.

The ratio of source data to on-disk index size varies by mapping, analyzer, compression, and field types. AWS uses an illustrative factor near 1.1 in sizing examples; index a representative sample to measure your actual ratio.

### 5.3 Shard Count Calculation Example

A log workload is projected to produce 360 GiB of indexed data over a cycle. Target 40 GiB per primary shard with 10% overhead allowance:

~~~text
Primary shards
  ≈ 360 x 1.1 / 40
  ≈ 9.9
~~~

You can start with 10 primary shards. With one replica, total shard copies equal 20.

Before finalizing, verify:
- Data node count.
- Shard copies per node.
- JVM heap.
- CPU and network bandwidth.
- Period-over-period growth.
- Recovery capacity during node outages.
- Shards from other indexes in the domain.

### 5.4 Avoid Over-Planning for Distant Growth

Suppose current data is only 60 GiB, projected to reach 300 GiB next year. Creating 10 primary shards upfront yields 6–7 GiB shards today, imposing tiny-shard overhead immediately.

Consider a balanced middle path:
- Start with fewer shards so current shard sizes are healthy.
- Use rollover to create new indexes at size thresholds.
- When legacy indexes outgrow targets, reindex into a new index with adjusted primary shard counts.
- Benchmark before changing designs.

For time-series data, size-based rollover generally keeps shard sizes steadier than mechanically creating one index per day.

## 6. Shard Count vs. Data Nodes and JVM Heap

Beyond shard size, control shard count per node. Every shard carries metadata, segments, file handles, caches, and background work. Too many tiny shards exhaust heap and CPU even when total disk usage is modest.

AWS provides reference guidelines:
- Aim to stay at or below 25 shards per GiB of data node JVM heap.
- Through OpenSearch Service 2.15, the limit is typically 1,000 shards per node.
- For OpenSearch Service 2.17 and later, supported limits scale at 1,000 shards per 16 GiB of JVM heap, up to 4,000 shards per node.
- Some configurations like Multi-AZ with Standby have stricter limits; current documentation specifies at most 1,000 shards per node and 75,000 shards cluster-wide for that mode.

Service limits are hard technical ceilings, not design targets. Clusters often degrade well before hitting ceilings.

For example, on a node with 16 GiB JVM heap:
- Using the 25 shards/GiB guideline, a conservative starting ceiling is roughly 400 shards per node.
- Do not consume the full 1,000-shard quota simply because the service permits it.

Count both primary and replica shards. An index with 10 primaries and 2 replicas contributes 30 shard copies to the cluster.

## 7. Distributing Shards Across Nodes and Availability Zones

### 7.1 Node-Level Distribution

OpenSearch distributes shard copies to prevent placing a primary and its replica on the same node. Still, uneven shard counts, mixed node sizes, or allocation filters can introduce storage/CPU skew.

An index with 12 primary shards generally spreads evenly when data node count is 2, 3, 4, 6, or 12. This is merely a balancing hint; shard size and workload remain primary drivers.

Monitor:
- Shards per node.
- Primary/replica distribution.
- Storage used per node.
- CPU and JVM pressure.
- Search/indexing queues.
- Request latency.
- Shard relocations and recoveries.

### 7.2 Zone Awareness

With Multi-AZ domains, OpenSearch Service places primaries and replicas in distinct AZs. If one AZ fails, copies in surviving AZs continue serving requests.

In Multi-AZ without Standby, AWS recommends at least one replica per index if cross-AZ redundancy is needed. With zero replicas, there is no copy to place in another AZ.

### 7.3 Multi-AZ with Standby

For eligible production domains, AWS recommends Multi-AZ with Standby. Key requirements include:
- Three Availability Zones.
- Three dedicated cluster manager nodes.
- Data node count of three or a multiple of three.
- At least two replicas per index, yielding three data copies (one primary and two replicas).
- Supported instance types, storage types, and domain configurations.

Each AZ holds a complete data copy. One AZ remains on standby and serves no search traffic during normal operations. When AWS detects an infrastructure failure, standby activates to preserve availability.

For Multi-AZ with Standby, verify specific limits on shard counts, shard sizes, instance types, and UltraWarm node counts before selecting the topology.

### 7.4 Replicas Are Not Cross-Region DR

Multi-AZ protects against certain node/AZ failures within a single Region. It does not fully protect against:
- Accidental index deletion.
- Bad mappings corrupting data.
- Corrupted data ingestion.
- Application bugs overwriting records.
- Region-wide outages.
- Point-in-time recovery needs.

Use snapshots and cross-Region disaster recovery plans tailored to your RPO/RTO.

## 8. Changing Primary Shard Counts

Primary shard count is locked at index creation and cannot be changed simply by updating `number_of_shards` on a live index.

Common options:

| Option | Purpose | Conditions / Trade-offs |
|---|---|---|
| Reindex | Copies documents to a new index with new shard count/mapping | Consumes time, CPU, disk, and network; requires dual-write or cutover |
| Shrink | Merges multiple primary shards into fewer shards | Source must be read-only and meet allocation prerequisites |
| Split | Creates a new index with more primary shards | Depends on `number_of_routing_shards` and split prerequisites |
| Rollover | Creates a new index for subsequent data | Leaves existing index shard count unchanged |

### 8.1 Reindex

Create the destination index with desired settings/mappings, then run reindex:

~~~http
PUT orders-v2
{
  "settings": {
    "number_of_shards": 6,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "order_id": { "type": "keyword" },
      "created_at": { "type": "date" },
      "status": { "type": "keyword" }
    }
  }
}

POST _reindex
{
  "source": {
    "index": "orders-v1"
  },
  "dest": {
    "index": "orders-v2"
  }
}
~~~

This is a structural example; in production, monitor task status, throttling, version conflicts, ingest pipelines, routing, and writes occurring during reindexing.

Cutover workflow typically includes:
1. Create the destination index and mappings.
2. Reindex historical data.
3. Sync new writes via dual-writes, CDC, or a planned freeze window.
4. Reconcile counts, aggregates, and sample documents.
5. Flip read/write aliases to the new index.
6. Monitor queries and indexing.
7. Delete the old index only after the rollback window closes.

### 8.2 Shrink and Split

Shrink helps when an index has too many small primary shards. Split helps when an index grows large and needs greater parallelism.

Both operations impose prerequisites on routing, shard allocation, and index state. Before executing, review docs for your running OpenSearch version, verify temporary disk headroom, and test on a clone.

Never rely on shrink/split as a substitute for a sound rollover strategy on incoming time-series data.

## 9. Designing Indexes for Time-Series Data

Logs, metrics, and events typically carry a timestamp field. Common patterns:

| Pattern | Organization | Best Suited For |
|---|---|---|
| Single long-lived index | Writes all data to one index | Low volume, simple retention |
| Daily indexes | `logs-2026.11.20` | High volume, day-granularity deletion |
| Weekly/monthly indexes | `logs-2026.11` or weekly | Moderate growth, fewer indexes |
| Rollover alias | Alias points to current write index | Automated size/age rollover |
| Data Stream | Stream name backed by multiple indexes | Append-only time-series data |

Avoid daily indexes if daily volume is only a few hundred MiB—that spawns excessive tiny shards. Conversely, monthly indexes on heavy write workloads can create oversized shards and slow recovery.

Choose cadence based on:
- Ingest rate and growth.
- Primary shard count.
- Target shard size.
- Time-range query patterns.
- Retention and compliance rules.
- Replay/backfill requirements.
- Rollover frequency and metadata management overhead.

Practical rule: let size/age rollover govern shard sizes instead of assuming every calendar day generates identical volume.

## 10. Index Templates and Mappings

Index templates apply settings and mappings to new indexes matching a pattern, preventing inconsistent auto-generated schemas.

Components to define:
- `number_of_shards`.
- `number_of_replicas`.
- `refresh_interval`.
- ISM policy applied via `ism_template` or policy APIs.
- Timestamp field.
- `keyword`, `text`, `date`, numeric, and boolean types.
- Dynamic mapping policy.
- Analyzers/normalizers if needed.
- Alias or data stream settings.

Example log template:

~~~json
PUT _index_template/logs-template
{
  "index_patterns": ["logs-*"],
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "30s"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "service": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "level": { "type": "keyword" },
        "message": { "type": "text" },
        "status_code": { "type": "integer" },
        "duration_ms": { "type": "long" }
      }
    }
  }
}
~~~

`keyword` fits exact matches, filters, sorts, and aggregations. `text` fits full-text search. Marking every field `text` bloats inverted indexes and forces aggregations to rely on fielddata or dedicated sub-fields.

Never allow dynamic mapping to create unbounded fields from unvalidated payloads. JSON logs often contain arbitrary keys; standardize schemas, use `dynamic: false`, or apply bounded dynamic templates where appropriate.

## 11. Data Streams for Logs and Metrics

A Data Stream provides a single logical name for ingesting and querying time-series data. Underneath, the stream manages multiple backing indexes rolled over by time or size.

Characteristics:
- Every document must contain a timestamp field.
- Data follows an append-only model.
- Write requests route to the current write backing index.
- Search requests span all backing indexes in the stream.
- Backing indexes are created from an index template with `data_stream`.
- Rollover creates a new backing index and promotes it to the write index.

Data Streams fit continuously arriving logs, metrics, and events where older documents are rarely updated.

### 11.1 Creating a Data Stream

Create an index template:

~~~http
PUT _index_template/app-logs-template
{
  "index_patterns": ["logs-app-*"],
  "data_stream": {},
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "30s"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "application": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "message": { "type": "text" }
      }
    }
  }
}
~~~

Create the stream:

~~~http
PUT _data_stream/logs-app-prod
~~~

Ingest a document:

~~~http
POST logs-app-prod/_doc
{
  "@timestamp": "2026-11-20T04:30:00Z",
  "application": "checkout",
  "environment": "prod",
  "message": "payment authorization completed"
}
~~~

Search:

~~~http
GET logs-app-prod/_search
{
  "query": {
    "range": {
      "@timestamp": {
        "gte": "now-24h"
      }
    }
  }
}
~~~

### 11.2 Rolling Over a Data Stream

You can roll over manually:

~~~http
POST logs-app-prod/_rollover
~~~

Or use ISM to roll over automatically by age, size, or document count.

Notes:
- ISM policies apply to backing indexes as they are created.
- Attaching a policy to a data stream affects future backing indexes.
- `rollover_alias` is unnecessary for data streams because policies detect the stream from backing indexes.
- Every document requires a valid timestamp.
- Data Streams are append-only; updating/deleting individual documents requires targeting backing indexes or using supported APIs.

### 11.3 Backfills and Late-Arriving Data

Data Streams write new documents to the current write index even if a document's `@timestamp` is in the past—such as during log replays or backfills.

OpenSearch still filters accurately by `@timestamp` in queries, yet backing index lifecycles evaluate index age and policies. Therefore:
- Distinguish event time from ingest time.
- Define explicit backfill procedures.
- Decide whether historical backfills belong in the live stream or a separate historical index.
- Avoid letting late data violate deletion/archival assumptions.

### 11.4 Data Streams and Cold Storage

Note an important constraint: migrating a Data Stream backing index to cold storage detaches that index from the Data Stream. Even if migrated back to UltraWarm, it remains a standalone index and does not automatically reattach to the stream. Queries targeting the Data Stream name will no longer return data from detached backing indexes.

The current write index cannot move to cold storage; roll over first before migrating older backing indexes. Snapshot recovery of a Data Stream with UltraWarm backing indexes may also fail to restore full stream state; prior to taking snapshots intended for full stream recovery, migrate backing indexes back to hot storage per AWS guidance.

If historical searches must always resolve through one stream name, carefully evaluate cold storage and design archive/query paths before enabling lifecycle transitions.

## 12. Rollover Aliases for Traditional Indexes

When data does not fit Data Streams, use index aliases with a write index.

The `legacy-logs-*` pattern is kept separate from the Data Stream above so two templates never collide on the same index. Create the template settings before creating the index:

~~~http
PUT _index_template/legacy-logs-settings
{
  "index_patterns": ["legacy-logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "plugins.index_state_management.rollover_alias": "legacy-logs-write"
    }
  }
}
~~~

Create the initial index with write and read aliases:

~~~http
PUT legacy-logs-000001
{
  "aliases": {
    "legacy-logs-write": {
      "is_write_index": true
    },
    "legacy-logs-read": {}
  }
}
~~~

Applications write via `legacy-logs-write` and search via `legacy-logs-read`.

When the index crosses thresholds:

~~~http
POST legacy-logs-write/_rollover
{
  "conditions": {
    "max_age": "1d",
    "max_size": "50gb"
  },
  "aliases": {
    "legacy-logs-read": {}
  }
}
~~~

`max_age`, `max_size`, and `max_docs` in the rollover API combine via logical OR: meeting any single condition triggers rollover. Check `rolled_over` in the response to confirm rollover occurred.

Rollover creates a new index, shifts the write alias to the new index, and retains the old index for historical reads. Aliases shield applications from index name changes on every rollover.

## 13. Index State Management (ISM)

ISM automates index management operations based on age, size, or document count. A policy is a state machine consisting of:
- State: current index state, e.g., hot, warm, cold, delete.
- Action: operations executed upon entering a state.
- Transition: conditions advancing to the next state.

Common actions:
- `rollover`: creates a new index for an alias or data stream.
- `replica_count`: adjusts replica count.
- `force_merge`: merges segments.
- `snapshot`: creates a snapshot in a configured repository.
- `warm_migration`: moves the index to UltraWarm.
- `cold_migration`: moves the index to cold storage.
- `delete`: deletes a standard index.
- `cold_delete`: deletes an index in cold storage.

In Amazon OpenSearch Service, ISM APIs typically use the `_plugins/_ism` prefix. Older Elasticsearch/OpenSearch domains may use the legacy `_opendistro` prefix.

### 13.1 Attaching Policies to Indexes

Create a policy in OpenSearch Dashboards or via API:

~~~http
PUT _plugins/_ism/policies/logs-retention
{
  "policy": {
    "description": "Rollover and log lifecycle management",
    "default_state": "hot",
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "warm",
            "conditions": {
              "min_index_age": "30d"
            }
          }
        ]
      },
      {
        "name": "warm",
        "actions": [
          {
            "warm_migration": {}
          }
        ],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "90d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "delete": {}
          }
        ],
        "transitions": []
      }
    ],
    "ism_template": {
      "index_patterns": ["logs-*"],
      "priority": 100
    }
  }
}
~~~

The example illustrates hot-to-warm-to-delete assuming UltraWarm is enabled on the domain. It is not yet a complete production retention policy: add snapshots, cold storage, or retention windows per organizational rules.

Apply a policy manually to an index:

~~~http
POST _plugins/_ism/add/logs-2026.11.20
{
  "policy_id": "logs-retention"
}
~~~

Inspect policy and managed index state:

~~~http
GET _plugins/_ism/policies/logs-retention
GET _plugins/_ism/explain/logs-2026.11.20
~~~

### 13.2 ISM Templates

You can declare `ism_template` inside a policy so it automatically attaches to newly created indexes matching a pattern. This is a field on the ISM policy itself.

In Amazon OpenSearch Service, do not rely on the legacy approach of attaching ISM policies from index templates via legacy settings. AWS updated the mechanism; use `ism_template` inside the policy per current documentation.

`ism_template` applies only to new indexes created after the policy/template takes effect. Existing indexes must have policies attached explicitly or via a migration step.

### 13.3 Rollover with ISM

For alias-based indexes, you need:
- Index names ending in digits, such as `logs-000001`.
- An alias designated as the write alias.
- Setting `plugins.index_state_management.rollover_alias` pointing to that alias.
- A policy containing a `rollover` action.

Example action:

~~~json
{
  "rollover": {
    "min_index_age": "1d",
    "min_primary_shard_size": "30gb",
    "copy_alias": true
  }
}
~~~

Conditions inside the action combine via OR. Once any condition is met, ISM can roll over on the next policy evaluation. `copy_alias: true` preserves read aliases such as `legacy-logs-read` on the new index. Data streams do not require a rollover alias setting.

### 13.4 ISM Does Not Run Instantaneously

ISM runs on a periodic job cycle. On Amazon OpenSearch Service, jobs typically run every 5–8 minutes depending on version; clusters in `red` state pause ISM execution. Therefore, do not treat `min_index_age: 30d` as a sub-second exact schedule.

Actions can also take time for shard migration, force merges, snapshots, or cold migration. Monitor policy execution, retries, and errors. When an action fails, inspect the explain API and resolve the root cause before retrying.

### 13.5 Sample Hot → Warm → Cold → Delete Policy

Example for a domain with UltraWarm and cold storage enabled. The 10/90/365-day windows are illustrative only:

~~~json
PUT _plugins/_ism/policies/logs-hot-warm-cold
{
  "policy": {
    "description": "Lifecycle for historical logs",
    "default_state": "hot",
    "schema_version": 1,
    "states": [
      {
        "name": "hot",
        "actions": [],
        "transitions": [
          {
            "state_name": "warm",
            "conditions": {
              "min_index_age": "10d"
            }
          }
        ]
      },
      {
        "name": "warm",
        "actions": [
          {
            "warm_migration": {},
            "retry": {
              "count": 5,
              "delay": "1h"
            }
          }
        ],
        "transitions": [
          {
            "state_name": "cold",
            "conditions": {
              "min_index_age": "90d"
            }
          }
        ]
      },
      {
        "name": "cold",
        "actions": [
          {
            "cold_migration": {
              "timestamp_field": "@timestamp"
            }
          }
        ],
        "transitions": [
          {
            "state_name": "delete",
            "conditions": {
              "min_index_age": "365d"
            }
          }
        ]
      },
      {
        "name": "delete",
        "actions": [
          {
            "cold_delete": {}
          }
        ],
        "transitions": []
      }
    ],
    "ism_template": {
      "index_patterns": ["logs-*"],
      "priority": 100
    }
  }
}
~~~

Notes:
- Cold migration via ISM must specify `timestamp_field`.
- Cold indexes must use `cold_delete`, not the regular `delete` action.
- Policies evaluate index age and job cycles, not document event timestamps.
- For Data Streams, cold migration detaches backing indexes from the stream.
- Verify snapshots/restore, retention, compliance, and query paths before enabling deletion policies.

## 14. Hot, UltraWarm, and Cold Storage

Amazon OpenSearch Service offers storage tiers with distinct performance and cost profiles.

| Tier | Backing Storage | Purpose | Access Method |
|---|---|---|---|
| Hot | Instance store or EBS on data nodes | Fresh indexes, frequent writes/reads | Standard search and indexing |
| UltraWarm | Amazon S3 with warm node caching | Read-only data, fewer writes and queries | Search via OpenSearch API; potentially higher latency than hot |
| Cold | Amazon S3 with managed metadata | Infrequently accessed historical data, on-demand analysis | Attach/migrate back to warm to query |

### 14.1 Hot Storage

Hot storage fits:
- Newly ingested data.
- Low-latency query requirements.
- Frequently updated indexes.
- Continuous indexing and refresh workloads.

Hot capacity comes from EBS or instance stores tied to data node types. Scaling hot nodes raises costs even when stored data is rarely queried.

### 14.2 UltraWarm

UltraWarm stores read-only data in S3 backed by node caches. It suits logs, audits, and historical data that still need searchability without hot-tier speed.

Characteristics:
- Indexes on the warm tier are read-only.
- Writing again requires migrating the index back to hot.
- Requires UltraWarm and dedicated cluster manager nodes enabled.
- Warm node counts and instance types must match managed volume.
- Migrating to warm typically triggers force merges, consuming time and resources.
- Queries may be slower than hot due to storage/caching mechanics.

UltraWarm still supports OpenSearch APIs and Dashboards. Benchmark real queries—especially heavy aggregations or wide time-range scans.

### 14.3 Cold Storage

Cold storage targets rarely accessed data for forensics, audits, or periodic historical investigations.

Characteristics:
- Backed by Amazon S3.
- Requires UltraWarm enabled on the same domain.
- Supported on OpenSearch/Elasticsearch 7.9 and later per service prerequisites.
- Cold indexes attach to warm nodes when queried.
- Supports cold ↔ warm migration workflows.
- Cold indexes require timestamp metadata for ISM cold migration.
- Cannot write directly to cold indexes.

Cold storage is not an always-warm query pool. Data must reattach to warm nodes before searching. Factor attach/migration lead times into investigation runbooks and retrieval SLAs.

### 14.4 Choosing Tiers by Age and Query Frequency

Example policy:
- 0–10 days: hot, continuous ingest and frequent queries.
- 10–90 days: UltraWarm, mostly reads and investigations.
- 90–365 days: cold, queried only on demand.
- Over 365 days: snapshot/archive or delete per retention policy.

This is only an example. Payment, security, or regulatory workloads may demand longer retention, dedicated snapshots, and stricter recovery SLAs.

## 15. Force Merge and Optimizing Historical Indexes

Every shard comprises multiple Lucene segments. Updates/deletes create new documents or mark old ones deleted; merging segments reclaims deleted space and lowers segment counts scanned per query.

Force merge can:
- Compact many segments into fewer segments.
- Reduce read/query overhead on read-only indexes.
- Prepare indexes prior to UltraWarm migration.
- Reclaim disk space from deleted documents.

However, force merge is resource-intensive:
- Generates heavy I/O and CPU.
- Can require temporary free disk headroom.
- Increases cluster load.
- Unsuitable for actively ingested indexes.
- Never run simultaneously across every index during peak hours.

Run force merge only after rollover when writes have stopped, or via workload-aware procedures. You can invoke ISM's `force_merge` action in the warm state.

## 16. Snapshots and Recoverability

Replicas protect against certain node/shard failures, whereas snapshots enable point-in-time data recovery.

Amazon OpenSearch Service provides:
- Automated snapshots managed by the service on its schedule and retention.
- Manual snapshots stored in user-configured S3 repositories.

Manual snapshots are commonly used when:
- You need control over exact backup timing.
- Retention must exceed automated snapshot windows.
- Planned index or domain restores are required.
- Cross-domain or cross-Region migrations/DR are needed within compatibility bounds.

When using manual snapshots:
1. Create an S3 bucket and appropriate IAM role/policy.
2. Register the snapshot repository with the domain.
3. Trigger snapshots on schedule.
4. Monitor snapshot status.
5. Test restores into a staging domain.
6. Verify indexes, aliases, mappings, document counts, and queries.

Snapshots can run slowly when domains have huge shard counts or undersized dedicated master nodes. AWS recommends sizing dedicated master nodes to shard counts and keeping shard counts reasonable.

Snapshots do not replace restore testing. An untested backup does not prove RTO.

### 16.1 Snapshots and Data Streams

If a Data Stream has backing indexes migrated to UltraWarm, snapshot recovery may fail to restore complete Data Stream state. AWS recommends moving all backing indexes back to hot storage before taking snapshots meant for full stream recovery.

Cold migration also detaches backing indexes from Data Streams. Verify query and snapshot architectures before migrating backing indexes to cold.

## 17. Retention, Compliance, and Data Deletion

Define retention policies jointly with data owners, security, finance, and compliance.

Key questions:
- Which data must be retained and for how long?
- Is retention measured from event time or ingest time?
- Does the data contain PII, payment data, or secrets?
- Are there legal hold or eDiscovery requirements?
- Who is authorized to change policies or delete indexes?
- Do snapshots carry independent retention?
- Must data be purged across hot, warm, cold, and snapshots?
- Is proof of completed deletion required?

Deleting an index via ISM does not erase backup copies in snapshots. If snapshots retain the data, it remains recoverable until snapshots expire. Align deletion policies across index lifecycles, snapshot lifecycles, and upstream data stores.

For sensitive data, evaluate field-level filtering, encryption, access controls, audit logging, and cross-system deletion workflows.

## 18. Monitoring Shards, Nodes, and Lifecycles

### 18.1 Common Observability APIs

| API | Purpose |
|---|---|
| `GET _cluster/health` | Cluster status |
| `GET _cat/indices?v` | Primary/replica counts, doc counts, and storage per index |
| `GET _cat/shards?v` | Status, node, and size of each shard |
| `GET _cat/allocation?v` | Shard count and disk allocation per node |
| `GET _cat/nodes?v` | Node roles, heap, CPU, and resources |
| `GET _cluster/allocation/explain` | Explains unassigned shards or placement |
| `GET _plugins/_ism/explain/<index>` | ISM policy and action state |
| `GET _data_stream` | List of Data Streams and backing indexes |
| `GET _data_stream/<name>/_stats` | Data Stream statistics |

Example finding largest indexes:

~~~http
GET _cat/indices?v&s=store.size:desc
~~~

Inspecting shard allocation:

~~~http
GET _cat/shards?v&s=store:desc
GET _cat/allocation?v
~~~

Inspecting lifecycle status:

~~~http
GET _plugins/_ism/explain/logs-*
~~~

### 18.2 CloudWatch Metrics

Amazon OpenSearch Service integrates with CloudWatch. Key metrics to track include:

| Metric / Group | Meaning | Signal to Investigate |
|---|---|---|
| `ClusterStatus.green/yellow/red` | Cluster health | Sustained yellow/red |
| `FreeStorageSpace` | Available disk space | Disk approaching watermarks |
| `JVMMemoryPressure` | JVM heap pressure | Sustained high heap, frequent GC |
| `CPUUtilization` | CPU load | High CPU accompanied by queue growth |
| `SearchLatency` | Search latency | p95/p99 breaches SLA |
| `IndexingLatency` | Write latency | Slow ingestion |
| `IndexingRate` | Document indexing rate | Unusual drops or spikes |
| `SearchRate` | Query rate | Traffic surge or query fan-out |
| `Nodes` | Active node count | Node drops or instability |
| `MasterReachableFromNode` | Cluster manager reachability | Nodes losing contact with manager |
| `ThreadpoolSearchQueue` | Search thread pool queue | Queued queries piling up |
| `ThreadpoolWriteQueue` | Write thread pool queue | Queued writes piling up |
| `WarmToColdMigrationQueueSize` | Warm-to-cold migration queue | Delayed lifecycle transitions |
| `SnapshotFailure` | Snapshot errors | Risk of missing valid backups |

Exact metric names and dimensions vary by domain type, engine version, and tier. Consult current CloudWatch metric references when setting alarms.

### 18.3 Specific Shard Metrics

Monitor:
- Average and max percentile shard sizes.
- Shards per node.
- Primary-to-replica ratio.
- Unassigned shard count.
- Relocating/initializing shards.
- Under-replicated shards.
- Disk skew.
- Hot partitions/indexes.
- Segment counts.
- Recovery duration.

Do not look solely at aggregate cluster storage. One node can run out of disk while others stay mostly empty due to shard skew.

## 19. Common Troubleshooting

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| Prolonged yellow cluster | Unassigned replicas, low disk on nodes, or allocation constraints | Check allocation explain, node count, AZ awareness |
| Red cluster | Unassigned primary shard | Inspect node failures, recovery, and snapshots |
| Oversized shards | Rollover failing or too few primaries | Check index age/size, policy execution, reindex plan |
| Too many small shards | Daily index on low volume or excessive primaries | Consolidate periods, reindex/shrink, roll over by size |
| One node nearly full | Shard/storage skew | Inspect cat allocation, shard sizes, and relocations |
| High JVM pressure | Too many shards, huge mappings, or heavy queries | Check shard/heap ratio, mappings, fielddata, queries |
| Rising search latency | Query fan-out, oversized shards, hot node, or cold tier | Inspect search profiles, per-node latency, tiering |
| Rising indexing latency | Replica/write pressure, frequent refreshes, merges, or disk bottleneck | Inspect write queue, replica count, refresh interval |
| Warm migration fails | UltraWarm capacity, force merge, or index state | Check ISM explain, warm capacity, migration logs |
| Cold migration fails | Missing timestamp field or cold storage disabled | Verify domain config, timestamp mapping, ISM action |
| ISM not running | Red cluster, policy error, or retrying action | Check ISM explain, cluster health, job status |
| Data Stream missing older data | Backing index detached during cold migration | Check Data Stream API, cold index list, query paths |
| Snapshot restore missing stream state | Backing index resided in UltraWarm | Move indexes back to hot before snapshot/restore workflow |

When troubleshooting, gather evidence from APIs and metrics first. Never bump replicas, delete indexes, or disable allocation awareness merely to turn the cluster green without understanding the impact.

## 20. Example Log Analytics Architecture on AWS

An e-commerce application logs from ECS/EKS and Lambda. Logs stream through an ingestion pipeline to Amazon OpenSearch Service for incident search and operational analytics.

~~~text
ECS / EKS / Lambda
       |
       | Application logs + @timestamp
       v
Amazon Data Firehose / OpenSearch Ingestion
       |
       v
Amazon OpenSearch Service domain
       |
       +---- Hot data nodes
       |       - 0-10 days
       |       - Frequent indexing + search
       |
       +---- UltraWarm
       |       - 10-90 days
       |       - Read-only investigation
       |
       +---- Cold storage (S3-backed)
       |       - 90-365 days
       |       - Attach when needed for forensics
       |
       +---- Snapshot repository in S3
               - Backup/restore per policy
~~~

A sound design can include:
- Multi-AZ with Standby for production if domain/Region/instance rules permit.
- Index templates or Data Streams to standardize mappings.
- Primary shard counts sized around throughput and shard targets.
- Replica counts matching HA targets.
- ISM rollover to cap backing index sizes.
- ISM warm/cold migrations aligned with retention.
- Dedicated snapshot schedules.
- CloudWatch dashboards and alarms.
- Access policies scoped to application and security teams.

Ingestion pipelines should standardize timestamps, service names, environments, severity, and trace IDs. Avoid unbounded dynamic fields from unvalidated payloads so mapping explosions never overload the cluster.

## 21. Shard and Lifecycle Management Runbook

### 21.1 Before Creating an Index

1. Estimate daily/weekly/monthly data volume.
2. Measure source-to-index ratio on sample data.
3. Choose target shard size.
4. Calculate primary shard count.
5. Determine replica count per HA needs.
6. Verify shard/heap ratio and node capacity.
7. Create templates and mappings.
8. Verify policies, aliases, and data streams.

### 21.2 When Cluster Load Increases

1. Check cluster health.
2. Identify top indexes by storage.
3. Inspect shard counts and shard sizes.
4. Check CPU, heap, disk, and queues.
5. Pinpoint hot indexes or hot partitions.
6. Inspect query fan-out and ingest patterns.
7. Scale nodes or tune shards/indexes from measurements.
8. Rehearse changes in staging.

### 21.3 When an Index Reaches Rollover Age

1. Confirm the index hit size/age thresholds.
2. Check ISM explain.
3. Confirm the new backing index was created.
4. Verify the write alias or data stream write index.
5. Confirm the old index stopped receiving writes.
6. Monitor search and ingest via alias/stream.
7. Check policy transitions toward warm.

### 21.4 Before Migrating to Warm/Cold

1. Confirm the index is read-only.
2. Verify snapshots and retention.
3. Check query patterns and latency expectations.
4. Confirm UltraWarm/cold storage is enabled.
5. Verify timestamp fields if using ISM cold migration.
6. Check whether Data Stream backing indexes will detach from the stream.
7. Monitor migration queues and action status.
8. Rehearse attaching a cold index back to warm in staging.

### 21.5 Before Deleting

1. Confirm retention has expired.
2. Confirm no legal holds exist.
3. Verify snapshots/backups satisfy policy.
4. Confirm no write aliases or active consumers depend on the index.
5. Confirm cold indexes use `cold_delete`.
6. Retain lifecycle and approval evidence.
7. Monitor reclaimed storage capacity.

## 22. Production Design Checklist

- [ ] Source data volumes and growth rates are measured.
- [ ] Source-to-index ratio is benchmarked.
- [ ] Primary shard count reflects target shard size and workload.
- [ ] Shard size sits within suitable search or log ranges.
- [ ] Both primaries and replicas are counted in per-node shard totals.
- [ ] Shards per GiB of JVM heap stay within operational limits.
- [ ] Per-node shard quotas are not treated as sizing targets.
- [ ] Replica count meets HA, read capacity, and durability targets.
- [ ] Primaries and replicas distribute across nodes/AZs as designed.
- [ ] Multi-AZ with Standby meets 3-AZ, dedicated master, data node count, and replica rules.
- [ ] Snapshots/restores are tested; replicas are never treated as backups.
- [ ] Appropriate time-series strategy chosen: index-per-period, rollover alias, or Data Stream.
- [ ] Data Streams have timestamp fields and append-only workloads.
- [ ] Index templates enforce consistent mappings and settings.
- [ ] Dynamic mapping is controlled.
- [ ] Rollover thresholds match shard sizes and ingest rates.
- [ ] ISM policies apply to new indexes via `ism_template`.
- [ ] ISM policies have retries, monitoring, and owners.
- [ ] Warm/cold tiers are benchmarked for latency and retention.
- [ ] Impact of cold migration on Data Stream backing indexes is understood.
- [ ] Snapshot retention aligns with index retention.
- [ ] CloudWatch alarms cover health, disk, heap, latency, queues, and migrations.
- [ ] Runbooks exist for unassigned shards, shard skew, rollover, restore, and deletion.
- [ ] Retention and deletion rules are approved by compliance/business owners.

## 23. Practice Exercises

### Exercise 1: Calculating Primary Shards

A log index is projected to hold 420 GiB of indexed data per month. Target shard size is 35 GiB. Ignore growth for this exercise.

Tasks:
1. Estimate primary shard count with 10% overhead.
2. With 1 replica, what is the total shard copy count?

Answers:
- Primary shard count ≈ 420 × 1.1 / 35 = 13.2, rounded up to roughly 14.
- With one replica: 14 × 2 = 28 shard copies.

### Exercise 2: Identifying Over-Sharding

An index is only 4 GiB yet was created with 20 primary shards and 1 replica.

Task: identify the problem and remediation.

Answer: each primary is roughly 0.2 GiB, far below guidelines. Reindex into a new index with fewer primary shards, validate mappings/queries, and cut over via aliases. You cannot simply update `number_of_shards` on the existing index.

### Exercise 3: Replica Count

A domain index has 3 primary shards with 2 replicas per primary.

Task: what is the total shard copy count and relative data footprint compared to zero replicas?

Answer: 3 × (1 + 2) = 9 shard copies. There are three copies of every data partition; storage is roughly three times primary-only, excluding minor overhead.

### Exercise 4: Yellow Cluster

Cluster health is yellow: all primaries are assigned, while several replicas remain unassigned.

Task: list three root causes to check.

Answer:
- Insufficient data nodes or offline nodes.
- Disk watermarks/capacity blocking allocation.
- Zone awareness, allocation filters, or replica placement conflicts.
Use `_cluster/allocation/explain` to pinpoint the exact cause.

### Exercise 5: Choosing Multi-AZ

A production domain needs high availability in a 3-AZ Region, and the team wants Multi-AZ with Standby.

Task: list the key configuration requirements.

Answer: three AZs, three dedicated cluster manager nodes, data node count of three or a multiple of three, at least two replicas per index, and supported instance/storage types.

### Exercise 6: Data Streams

An append-only logging system emits `@timestamp`. The team wants a single stable write endpoint and automatic creation of backing indexes.

Answer: Data Streams fit well. Create an index template with `data_stream`, timestamp mapping, and settings, then write/search via the stream name and configure ISM rollover.

### Exercise 7: Cold Storage

An old Data Stream backing index moves to cold storage, and users no longer see that data when querying the stream name.

Answer: cold migration detaches the backing index from the Data Stream. The index can be queried independently after reattaching to warm via supported workflows; redesign query paths if historical data must always appear under one stream.

### Exercise 8: ISM Not Triggering

A policy moves indexes to warm after 30 days, yet a 31-day-old index has not migrated.

Answer: check cluster health, ISM explain, policy attachment, action retries, UltraWarm capacity, and job intervals. ISM skips runs when cluster health is red, and migrations take time to execute.

## 24. Self-Check Questions

1. How do an index and a shard differ?
2. What role does a primary shard play?
3. What do replica shards provide beyond redundancy?
4. Why are replicas not backups?
5. How many primaries and replicas does Amazon OpenSearch Service typically create by default?
6. Why should you avoid creating too many tiny shards?
7. What are the reference shard sizes for search and log analytics?
8. What factors enter the primary shard count estimation formula?
9. Why must replicas be included when estimating shards per node?
10. How do green, yellow, and red cluster states differ?
11. Why does Multi-AZ without Standby require replicas?
12. What key configurations does Multi-AZ with Standby require?
13. Can `number_of_shards` be modified directly on an existing index?
14. When should you use reindex, shrink, or split?
15. What workloads suit Data Streams?
16. What does rollover change about the write index?
17. How do states, actions, and transitions interact in ISM?
18. Why is an ISM job not a precision-timed cron?
19. How does UltraWarm differ from cold storage?
20. Why can cold migration of backing indexes affect Data Stream queries?
21. When is force merge appropriate?
22. How do snapshots differ from replicas?
23. Which metrics reveal shard skew?
24. What must be verified before deleting an index?

Suggested Answers:

1. An index is a logical collection of documents; a shard is a physical partition of that index.
2. Stores authoritative partition data and handles incoming indexing operations.
3. Replicas serve search requests and can be promoted if a primary fails.
4. Logic errors and accidental deletes/writes replicate directly to replicas.
5. Five primary shards and one replica per primary under Amazon OpenSearch Service defaults.
6. Every shard consumes heap, CPU, metadata, and file handles.
7. Search: 10–30 GiB; log/write-heavy: 30–50 GiB.
8. Source data size, growth allowance, indexing overhead, and target shard size.
9. Replicas are shard copies consuming storage, heap, and allocation slots.
10. Green: all shards assigned; yellow: missing replicas; red: at least one missing primary.
11. So a copy exists in another AZ.
12. Three AZs, three dedicated masters, data nodes in multiples of three, at least two replicas per index, and supported configurations.
13. No; create a new index via reindex, or use shrink/split where eligible.
14. Reindex is flexible; shrink reduces shards; split increases shards.
15. Append-only logs, metrics, and events with timestamps.
16. Creates a new backing index/index and moves the write target to it.
17. State is the current phase, action is the operation executed, and transition defines conditions to advance.
18. Jobs run periodically with jitter and pause if cluster state is red.
19. UltraWarm is read-only S3-backed with warm caches; cold archives historical data and reattaches to warm when queried.
20. Cold migration detaches backing indexes from the Data Stream.
21. Once indexes are read-only, to compact segments, speed queries, and prepare for warm tiers.
22. Replicas are live intra-cluster copies; snapshots are point-in-time recovery backups.
23. Shard count, storage per node, CPU, JVM, allocation, and relocations.
24. Retention expiration, legal holds, snapshots, alias/consumer dependencies, and approvals.

## 25. Official Reference Documentation

- [Choosing the number of shards - Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp-sharding.html)
- [Operational best practices for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp.html)
- [Configuring a multi-AZ domain](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-multiaz.html)
- [Dedicated master nodes](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-dedicatedmasternodes.html)
- [Index State Management in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ism.html)
- [Managing indexes in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managing-indices.html)
- [Managing time-series data with Data Streams](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/data-streams.html)
- [UltraWarm storage](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ultrawarm.html)
- [Cold storage](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cold-storage.html)
- [Creating index snapshots](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-snapshot-create.html)
- [OpenSearch Data Streams](https://docs.opensearch.org/latest/opensearch/data-streams/)
- [OpenSearch Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/)
- [OpenSearch rollover API](https://docs.opensearch.org/latest/api-reference/index-apis/rollover/)
- [OpenSearch shard routing](https://docs.opensearch.org/latest/search-plugins/searching-data/search-shard-routing/)
- [OpenSearch Cluster Allocation Explain API](https://docs.opensearch.org/latest/api-reference/cluster-api/cluster-allocation/)

Features, shard quotas, instance limits, engine versions, and storage tier capabilities change across versions and Regions. Before deploying, check documentation for your exact domain and benchmark with realistic data, queries, and retention policies.
