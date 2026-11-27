# Rollover and Time-Based Index Management

When Elasticsearch data grows continuously, writing every document into a single index can make that index grow ever larger, make shards hard to manage, and complicate retention policies. For time-oriented lifecycle data such as logs, events, access history, or telemetry, you can split data across multiple indices by generation or time interval, then use aliases, rollover, and lifecycle policies to manage writes, reads, storage, and deletion.

Rollover creates a new index when the current index meets conditions such as age, document count, or shard size. Aliases let the application write to a stable name without needing to know the current physical index. Index Lifecycle Management (ILM) can automate rollovers, move indices through storage phases, and eventually delete expired data.

## 1. Why manage indices over time?

Many systems have data that grows over time and mostly appends new documents:

- Application logs and access logs.
- Business events, audit trails, and action history.
- Sensor data, metrics, and telemetry.
- Search history, clickstreams, or user activity.
- Completed transaction events kept for lookup.

If all data resides in a single index, the index can grow very large and make it difficult to apply different storage policies to newer versus older data. Splitting into smaller indices bounds individual index sizes, makes time-based expiration convenient, and allows different shard/replica configurations across stages.

Example of generation-based index names:

```text
events-000001
events-000002
events-000003
events-000004
```

Each index holds a slice of data. The application uses an alias like `events-write` to send new data; read flows can use a read alias or a pattern like `events-*` to query across multiple generations.

## 2. Concepts to distinguish

| Concept | Meaning |
|---|---|
| Physical index | Actual Elasticsearch index storing documents, e.g., `events-000001` |
| Alias | Logical name pointing to one or more indices, e.g., `events-write` or `events-read` |
| Write index | Index receiving writes when an alias points to multiple indices; marked with `is_write_index` |
| Rollover | Creating a new-generation index and updating the write alias to the new index |
| Index template | Template of settings, mappings, and aliases applied when creating indices matching a pattern |
| ILM policy | Policy automating index lifecycle management across phases and actions |
| Data stream | Structure tailored for append-only time-series data, backed by multiple backing indices |

Rollover does not split documents already stored in old indices. It redirects subsequent writes to a new index. Old indices remain until another policy deletes or moves them.

## 3. Rollover using a write alias

A common deployment pattern is creating an alias dedicated to receiving writes. Initially, the alias points to the first index and that index is marked as the write index.

Example of creating the first index:

```http
PUT /events-000001
Content-Type: application/json

{
  "aliases": {
    "events-write": {
      "is_write_index": true
    }
  }
}
```

The application sends documents to `events-write` instead of writing directly to `events-000001`:

```http
POST /events-write/_doc
Content-Type: application/json

{
  "@timestamp": "2026-11-13T09:30:00Z",
  "eventType": "product_view",
  "message": "A visitor opened a product page"
}
```

When rollover occurs, Elasticsearch creates a new index, such as `events-000002`, and updates the write alias so subsequent writes go to the new index. The old index continues storing historical data. Depending on alias configuration, an alias can also be used for reads; to separate privileges and ensure historical queries cover all generations, you should usually create a dedicated read alias.

### Why is a numeric sequence suffix needed?

For ILM rollover aliases, index names should end with a numeric suffix such as `-000001`. Elasticsearch increments the suffix when creating the next index. For example:

```text
events-000001 -> events-000002 -> events-000003
```

This convention allows rollover to determine the next index name. An arbitrary index such as `events-2026.11.13` does not follow the naming convention required by ILM rollover aliases. If you want calendar-date names, consider data streams or a dedicated scheduled index creation process.

## 4. Calling the Rollover API manually

Elasticsearch provides the Rollover API to create a new-generation index when conditions are satisfied. You can test beforehand with `dry_run`:

```http
POST /events-write/_rollover?dry_run
Content-Type: application/json

{
  "conditions": {
    "max_age": "7d",
    "max_docs": 50000000,
    "max_primary_shard_size": "30gb"
  }
}
```

`dry_run` returns whether conditions have been met without creating a new index. When ready to perform an actual rollover:

```http
POST /events-write/_rollover
Content-Type: application/json

{
  "conditions": {
    "max_age": "7d",
    "max_docs": 50000000,
    "max_primary_shard_size": "30gb"
  }
}
```

Conditions are evaluated with OR logic: meeting just one condition allows rollover to trigger. In the response, fields such as `old_index`, `new_index`, `rolled_over`, and `conditions` show the outcome.

### Commonly used conditions

| Condition | Meaning | When useful |
|---|---|---|
| `max_age` | Maximum age of the index since creation | Limiting how long data stays in a single index |
| `max_docs` | Maximum number of documents for rollover condition | Bounding document count per generation |
| `max_size` | Total size of primary shards | Bounding primary data size of the index |
| `max_primary_shard_size` | Size of the largest primary shard | Preventing an individual shard from growing too large |

When choosing size thresholds, distinguish primary shard size from size including replicas. Replicas consume cluster storage but are not the primary data evaluated by `max_primary_shard_size`. Monitor the largest shard because a multi-shard index can still develop an unusually hot or oversized shard.

### Rollover is not deleting old indices

After rollover, old indices remain available for historical queries. Rollover does not automatically delete documents, move shards to cheaper storage nodes, or enforce retention limits. Those responsibilities belong to ILM, Data Stream Lifecycle, or dedicated operational workflows.

Do not call the Rollover API from every document write request. Rollover is an index administration operation; let ILM execute it automatically or invoke it from a controlled administrative job.

## 5. Using Index Lifecycle Management (ILM)

ILM automatically applies policies to indices. A policy can define phases such as:

- **Hot:** index receives writes and is queried frequently; typically includes rollover.
- **Warm:** data is written less often; replicas can be reduced, or indices can be force-merged or shrunk depending on architecture.
- **Cold:** data is rarely accessed; more cost-efficient storage configurations can be used.
- **Frozen:** data is very rarely accessed, using storage/search mechanisms appropriate for the deployed version and license.
- **Delete:** deletes the index when its retention period expires.

Not every cluster needs all five phases. Choose based on data type, query frequency, storage cost, node topology, and the capabilities of the Elasticsearch version in use.

### Creating an ILM policy

Example policy for event data: roll over when the largest primary shard reaches 30 GB or the index reaches 7 days of age; delete the index 90 days after rollover.

```http
PUT /_ilm/policy/events-policy
Content-Type: application/json

{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "30gb",
            "max_age": "7d"
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

In this example, `min_age` in the delete phase for a rolled-over index is calculated from the rollover timestamp, not when the first document was written. Thus, an index may exist for roughly 90 days after rollover; total lifetime from index creation to deletion depends on when rollover occurred. Account for retention this way when storage policies have legal or business mandates.

### Creating an index template

A template attaches the ILM policy and rollover alias to new indices matching a pattern. Example:

```http
PUT /_index_template/events-template
Content-Type: application/json

{
  "index_patterns": ["events-*"],
  "priority": 200,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "index.lifecycle.name": "events-policy",
      "index.lifecycle.rollover_alias": "events-write"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "eventType": { "type": "keyword" },
        "message": { "type": "text" }
      }
    },
    "aliases": {
      "events-read": {}
    }
  }
}
```

`events-read` is added to every new index matching the template, so the read alias can query across data generations. Do not set `events-write` as a fixed write-index alias on every index in the template; the write alias must point only to the active index and be managed by rollover/ILM.

### Bootstrapping the first index

After the policy and template exist, create the first index with the write alias:

```http
PUT /events-000001
{
  "aliases": {
    "events-write": {
      "is_write_index": true
    }
  }
}
```

The template applies settings, mappings, and the `events-read` alias. This bootstrap step is essential: if the policy specifies `index.lifecycle.rollover_alias` but the alias does not yet exist or lacks a valid write index, ILM cannot roll over as configured.

### Inspecting ILM

Check policy status:

```http
GET /_ilm/policy/events-policy
```

Check indices managed by ILM and their current actions:

```http
GET /events-000001/_ilm/explain
```

Check aliases:

```http
GET /_alias/events-write
GET /_alias/events-read
```

List indices:

```http
GET /_cat/indices/events-*?v&s=index
```

If an index does not roll over, check whether ILM is running, whether the policy is attached to the index, whether the alias points to the write index, whether the index suffix follows the convention, and whether rollover conditions have been met.

## 6. Write alias and read alias

For multi-generation data, clearly define which alias is used for writes and which is used for reads.

```text
Write application
    |
    v
events-write
    |
    v
events-000004  (current write index)

Historical read application
    |
    v
events-read
    |
    +--> events-000001
    +--> events-000002
    +--> events-000003
    +--> events-000004
```

`events-write` is dedicated to writes. `events-read` points to every generation that needs to be queried. In the ILM example, the template adds `events-read` to each new index, so the read alias continues covering post-rollover indices.

Separating aliases has several benefits:

- Write applications do not need to know the current physical index name.
- Historical queries are not limited to the newest index.
- Write permissions for `events-write` and read permissions for `events-read` can be granted separately.
- Read patterns can be adjusted, such as querying a subset of indices or per-tenant aliases, without altering write logic.

If using a single alias for both reads and writes, understand precisely which indices the alias points to after rollover. Do not assume a write alias always covers every generation. Inspect results with `GET /_alias/{alias}` and design an explicit read alias if the application needs history.

## 7. Connecting aliases with Spring Data Elasticsearch

Spring Data Elasticsearch works with the index name declared in `@Document`. That value can be an alias instead of a physical index name. For ILM-managed indices, the application should not create an index named as the alias at startup.

Example document writing through a write alias:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events-write", createIndex = false)
public class EventDocument {

    @Id
    private String id;

    @Field(name = "@timestamp", type = FieldType.Date)
    private Instant timestamp;

    @Field(type = FieldType.Keyword)
    private String eventType;

    @Field(type = FieldType.Text)
    private String message;

    // Constructors, getters and setters
}
```

`createIndex = false` prevents Spring Data from trying to create a physical index named `events-write` when initializing mappings/repositories. Aliases and physical indices must be bootstrapped by ILM/templates or a separate deployment workflow.

The repository can write documents through the alias:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface EventRepository
        extends ElasticsearchRepository<EventDocument, String> {
}
```

When calling `save`, requests go to `events-write`; Elasticsearch routes them to the current write index. The application does not need to change index names in code after each rollover.

### Reading through a read alias

To search across full history, use the read alias. With `ElasticsearchOperations`, you can specify `IndexCoordinates` for read operations:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class EventSearchService {

    private final ElasticsearchOperations operations;

    public EventSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void searchAllEvents(Query query) {
        operations.search(
            query,
            EventDocument.class,
            IndexCoordinates.of("events-read")
        );
    }
}
```

The example omits `SearchHits` processing to focus on alias selection. Exact APIs may vary slightly across Spring Data versions. What matters is that read operations target an alias covering the generations to search, while write operations target the write alias.

## 8. Condition-based rollover vs. daily index creation

Rollover relies on conditions such as age or size; it does not necessarily create an index right at midnight each day. If you need to group data by calendar day, you can use index names like:

```text
orders-2026.11.11
orders-2026.11.12
orders-2026.11.13
```

The application or a scheduled job selects the daily index, and an index template provides mappings/settings for each index. Historical queries usually use wildcards or a read alias spanning multiple days.

Comparing the approaches:

| Approach | Advantages | Limitations |
|---|---|---|
| Daily/monthly indices | Index name clearly reflects time range, easy scheduled deletion | Requires custom index creation and write routing; uneven traffic causes skewed index sizes |
| Condition-based rollover | Index size and age are bounded by thresholds; application writes through a stable alias | Index boundaries do not necessarily match calendar days; requires proper alias and ILM/bootstrap |
| Data stream | Convenient model for append-only time-based data | Requires timestamp mapping and understanding of data stream backing indices/retention |

Do not create an index for overly small time intervals if traffic is low, because many tiny indices increase shard overhead, cluster state size, and management cost. Conversely, overly large indices can make recovery, relocation, and queries harder to control.

## 9. When should you use a Data Stream?

Data streams are designed for time-series data, typically append-only data such as logs, metrics, and events. The data stream name is the logical access point; underneath, Elasticsearch manages backing indices and rollovers.

Key characteristics:

- Documents must include a configured timestamp field, typically `@timestamp` of type `date`.
- Documents are written to the data stream name; Elasticsearch sends data to the current write backing index.
- Queries on the data stream name can search across the stream's backing indices.
- Rollover and retention can be managed via ILM or Data Stream Lifecycle depending on version and needs.
- Data streams fit append-only flows best; if the application frequently updates/deletes old documents, carefully evaluate operation routing and whether a data stream fits.

Creating a data stream requires a matching index template first:

```http
PUT /_index_template/app-events-template
Content-Type: application/json

{
  "index_patterns": ["app-events*"],
  "data_stream": {},
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "eventType": { "type": "keyword" },
        "message": { "type": "text" }
      }
    }
  }
}
```

Then create the stream:

```http
PUT /_data_stream/app-events
```

Write documents via the stream name:

```http
POST /app-events/_doc
Content-Type: application/json

{
  "@timestamp": "2026-11-13T09:30:00Z",
  "eventType": "login",
  "message": "User signed in"
}
```

This is a minimal example. In production, the template should combine settings, mappings, lifecycle policies, and permissions matching the running Elasticsearch version. Data streams can be a simpler choice than alias rollover for append-only event streams, though they are not a universal replacement for every index.

## 10. Shards, replicas, and index sizing

Rollover is only effective when thresholds align with shard topology. An index with multiple primary shards distributes data, yet every shard carries memory, file descriptor, segment, and cluster metadata overhead.

Some principles:

- Choose primary shard counts based on expected size and throughput per index generation.
- Monitor the size of the largest primary shard, not just total index size.
- Use `max_primary_shard_size` if the goal is preventing an individual shard from becoming too large.
- Configure replicas according to availability and fault-tolerance requirements; replicas do not replace backups/snapshots.
- Avoid rolling over too frequently and flooding the cluster with tiny indices.
- Monitor total shard count and node capacity before increasing index count.

No single shard threshold fits every cluster. Measure size, indexing rate, search latency, and recovery time in a production-like environment before finalizing policies.

## 11. Querying and deleting historical data

When using a read alias, queries can span many indices. To reduce the volume of data scanned, filter by timestamp and fields useful for routing/filtering.

Example of searching events in a time range:

```http
GET /events-read/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "@timestamp": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

When retention expires, ILM can delete old indices. Deleting an index is an index-level operation, faster than deleting individual documents via delete-by-query once the entire index has expired and holds no data to keep.

Distinguish data retention from snapshots/backups. Deleting an index via ILM does not automatically delete snapshots stored in a repository. If data deletion mandates also apply to backups, implement a separate snapshot lifecycle policy.

## 12. Monitoring and troubleshooting rollover

Common symptoms:

| Symptom | Possible cause | What to check |
|---|---|---|
| ILM reports rollover alias missing | Alias was not created or name is wrong | `GET /_alias/events-write` and check `index.lifecycle.rollover_alias` |
| Unable to determine write index | Alias lacks `is_write_index` or points to multiple indices missing the write flag | Inspect alias metadata and bootstrap index |
| Rollover does not run | Policy not attached, ILM stopped, conditions unmet, or action retrying | `GET /events-000001/_ilm/explain` |
| Creating new index fails | Invalid template, invalid mapping/settings, or missing privileges | Check cluster logs, template, and index creation privileges |
| Application writes to old index | Application writes to physical index name instead of alias | Check `@Document(indexName=...)` and request target |
| Queries miss old data | Reads target an alias pointing only to the current index or read alias is not attached to old indices | Check `GET /_alias/events-read` |
| Too many small indices | Rollover thresholds too low or scheduled index granularity too fine | Re-evaluate max_age/max_docs/max_primary_shard_size |

When ILM fails, inspect the current step and message in `_ilm/explain` before retrying or adjusting the policy. Do not delete a managed index just to clear an error state without understanding the impact on aliases and retention.

## 13. Key operational notes

### Changing policies

When updating an ILM policy, indices currently attached to that policy may pick up changes according to ILM's update semantics. Inspect the active policy and each index's state before changing rollover or retention thresholds.

### Syncing data when switching generations

Rollover only redirects new writes. If the application has backfill or parallel write streams, ensure no documents are dropped and handle retries/idempotency. Atomic alias updates shift the write target, but do not replace data-delivery guarantees in the pipeline.

### Access privileges

Regular applications only need privileges to write through the write alias and read through the read alias. Privileges to create indices, trigger rollovers, alter templates, and modify ILM policies should belong to dedicated operational roles. Do not grant broad cluster admin rights to a service just so it can index documents.

### Index names and timezones

For daily indices, define which timezone partitions the days. An event with a UTC timestamp grouped by local date can land in a different index if producers and consumers disagree on timezone. For age-based rollover, index age is based on creation/rollover time rather than timestamps inside documents.

## 14. Index lifecycle design workflow

When deploying time-oriented data, you can follow this sequence:

1. Identify the data type, write throughput, historical query needs, and retention period.
2. Choose scheduled indices, rollover aliases, or data streams based on write and query patterns.
3. Design a mapping with an explicit time field, usually `@timestamp` of type `date`.
4. Choose shard and replica counts based on expected generation size.
5. Create an index template to standardize mappings/settings for every new index.
6. For ILM aliases, create the policy, attach policy/template, and bootstrap the first index with its write alias.
7. Create a read alias covering all generations needing queries.
8. Configure Spring Data to use the alias or data stream, avoiding hardcoded physical index names.
9. Test rollover with dry run, verify aliases, and monitor `_ilm/explain`.
10. Test historical queries, retention, snapshots, and recovery procedures before production operation.

## 15. Conclusion

Rollover and time-based index management help control data growth, shard size, and retention limits. Rollover shifts writes to a new-generation index; aliases preserve stable access names; index templates guarantee consistent mappings/settings; ILM automates rollovers and storage/deletion phases.

In Spring Data Elasticsearch, configure applications to write through a write alias or data stream and read through an alias covering the needed data generations. Do not create new physical indices per request and do not depend on the current index name in code. For append-only time-based data, data streams are worth considering; for alias rollover models, properly bootstrap an index with a numeric suffix, configure the write alias, and verify ILM. Designing retention, shards, read aliases, and snapshots together makes the data lifecycle predictable and easier to operate.
