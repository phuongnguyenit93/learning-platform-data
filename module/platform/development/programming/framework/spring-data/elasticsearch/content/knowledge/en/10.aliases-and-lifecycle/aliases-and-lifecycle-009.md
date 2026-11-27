# Retention Policies, Snapshots, and Search Data Recovery

A search system needs a plan for the entire data lifecycle: which index data is written to, how long it is kept, when it moves to another storage tier, when it is deleted, and how to recover when an incident occurs. In Elasticsearch, aliases let applications work with stable logical names; Index Lifecycle Management (ILM) or an appropriate lifecycle mechanism automates index management; snapshot repositories and Snapshot Lifecycle Management (SLM) support backups and backup retention.

Three responsibilities must be distinguished:

- **Index retention:** decides how long online searchable data is kept and when indices are deleted.
- **Snapshot:** creates backups that can be used to restore indices or cluster data within the chosen snapshot scope.
- **Snapshot retention:** decides how long backups are kept and when old snapshots can be deleted.

Snapshots do not replace index retention. Conversely, ILM deleting an index does not mean the corresponding snapshot is also deleted. A complete policy must manage both data serving live queries and backup copies.

## 1. Why is a data lifecycle policy needed?

Search data typically grows continuously. Logs, audit events, telemetry, transaction history, and business content have different write rates, lifespans, and recovery requirements.

Without a lifecycle policy:

- Old indices continue consuming storage even when they no longer hold query value.
- Shards grow in size and increase storage, recovery, and management costs.
- Critical data may be deleted accidentally or lack backups.
- Old snapshots accumulate and fill repository storage.
- When the cluster fails, the team does not know which backup can be restored or how long recovery takes.

Retention must start from business requirements. For example, operational logs may only need online searchability for 30 days; audit records may need longer retention under organizational policy; personal data may have to be deleted under legal mandates. Do not pick retention durations merely because of a default value in configuration.

### 1.1. Identifying requirements before configuring

For each data category, determine:

| Requirement | Question |
|---|---|
| Online duration | How long do users need to search the data? |
| Total retention duration | How long must the data exist under business or regulatory rules? |
| Query frequency | How frequently are recent data and older data queried? |
| RPO | What is the maximum acceptable data loss upon recovery? |
| RTO | How quickly must the system return to operation? |
| Volume | What are the daily write rate and storage growth? |
| Recovery scope | Do you need to recover a single index, a group of indices, or the entire cluster? |
| Privacy | Are there requirements to erase data from indices, snapshots, and backups? |

RPO (Recovery Point Objective) describes the maximum acceptable data loss, usually expressed as a time interval. RTO (Recovery Time Objective) describes the target time to restore service. Snapshot schedules, write rates, and recovery times must be designed around these two metrics.

## 2. Aliases as a logical naming layer for indices

Applications do not necessarily have to access physical indices directly. An alias is a logical name that can point to one or more indices and can serve as a read or write endpoint.

Example:

~~~text
Application
   |
   +---- read ----> logs-read
   |                  |
   |                  +----> logs-000041
   |                  +----> logs-000042
   |
   +---- write ---> logs-write
                      |
                      +----> logs-000042 (write index)
~~~

When rollover creates a new index, the write alias can be switched to the new index while the application keeps writing to the same logs-write name. The read alias can point to all indices still within the search retention window.

An alias does not delete data automatically and is not a backup. It is a routing layer that decouples application names from physical index names. Know which indices an alias points to before restoring, deleting, or modifying lifecycles.

You can inspect aliases with:

~~~http
GET /_alias/logs-read,logs-write
~~~

Or use the CAT API for a tabular view:

~~~http
GET /_cat/aliases?v
~~~

## 3. Retention and ILM

Index Lifecycle Management (ILM) lets you define phases and actions so Elasticsearch manages indices by age or lifecycle conditions. A policy can roll over indices, move data to appropriate tiers, optimize indices, or delete indices upon expiration.

Common phases:

| Phase | Typical role |
|---|---|
| Hot | Receives writes and serves frequent queries |
| Warm | Less frequently modified data, can be optimized to reduce cost |
| Cold | Infrequently accessed data, prioritizing resource savings |
| Frozen | Very rarely accessed data, can use searchable snapshots depending on architecture |
| Delete | Deletes the index once retention expires |

Not every index needs to pass through every phase. A small system may only need hot and delete. Available storage tiers and actions depend on Elasticsearch version, license, index type, and cluster configuration.

### 3.1. Rollover creating a new index

Rollover closes writes to the current index and switches the write alias to a new index when a condition is met, such as:

- Index reaches maximum age.
- Primary shard reaches target size.
- Index reaches target document count.

Example policy rolling over when an index is one day old or a primary shard exceeds 50 GB:

~~~http
PUT /_ilm/policy/logs-retention-policy
Content-Type: application/json

{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_primary_shard_size": "50gb"
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "forcemerge": {
            "max_num_segments": 1
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
~~~

This is an illustrative example, not numbers suitable for every system. Choose shard sizes and rollover timing based on ingest rate, node capacity, query times, and operational requirements. Force merging can consume significant I/O resources and must be accounted for in cluster load.

### 3.2. Attaching an ILM policy via an index template

With an alias-based index model, an index template can declare the policy and rollover alias for new indices:

~~~http
PUT /_index_template/logs-template
Content-Type: application/json

{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": {
      "index.lifecycle.name": "logs-retention-policy",
      "index.lifecycle.rollover_alias": "logs-write"
    },
    "mappings": {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "message": {
          "type": "text"
        },
        "level": {
          "type": "keyword"
        }
      }
    },
    "aliases": {
      "logs-read": {}
    }
  }
}
~~~

Then create the initial index and attach the write alias:

~~~http
PUT /logs-000001
Content-Type: application/json

{
  "aliases": {
    "logs-write": {
      "is_write_index": true
    }
  }
}
~~~

Subsequent writes can be sent to logs-write. When rollover conditions reach their threshold, ILM creates the next index and updates the write alias. logs-read continues providing a read endpoint across matching indices.

Index templates primarily apply at index creation time. Modifying a template does not automatically alter settings or mappings of existing indices. Inspect existing indices via APIs and plan separate migrations if changes are required.

### 3.3. Inspecting ILM status

You can inspect the policy:

~~~http
GET /_ilm/policy/logs-retention-policy
~~~

Inspect the lifecycle state of indices:

~~~http
GET /logs-*/_ilm/explain
~~~

The explain output identifies which phase each index is in, which action is running, next execution, and any errors if lifecycle execution paused. When an index is not deleted on schedule, inspect ILM status instead of immediately deleting it manually.

### 3.4. Data stream retention

For append-only data such as logs and events, data streams may fit better than self-managed indices and aliases. Data streams organize data into backing indices, letting you write to a logical stream and roll over when needed.

You can manage backing index lifecycles with ILM via index templates. Some Elasticsearch versions also offer Data Stream Lifecycle with simpler retention configuration for data streams. Choose one lifecycle mechanism suited to your version and data model, consult the corresponding documentation, and avoid conflicting policies managing the same backing index.

## 4. Index retention vs. snapshot retention

These two retention periods serve different purposes:

~~~text
Application data
      |
      v
Active index
      |
      | ILM: rollover / phase transition / delete
      v
Expired index deleted from cluster

Snapshot repository
      ^
      | periodic snapshot
      |
Index and metadata at backup time
      |
      | SLM: snapshot schedule / retention
      v
Old snapshots retained or deleted per separate policy
~~~

For example, log indices are kept online for 90 days while snapshots are kept for 30 days. When ILM deletes an index after 90 days, snapshots older than 30 days may already have expired. If log recovery within one year is required, snapshot schedules and retention must be designed to meet that requirement.

Conversely, keeping a snapshot for one year does not make data appear automatically in online search. To query it again, you must restore the snapshot into an index or data stream on a suitable cluster.

## 5. What is a snapshot?

A snapshot is a backup of one or more indices, data streams, and optionally global cluster state or feature state. Snapshots are stored in a snapshot repository supported by Elasticsearch.

Snapshots have several characteristics:

- Snapshots are Elasticsearch's official backup mechanism.
- Snapshots are taken incrementally: segments already present in the repository can be reused, so only new or changed data needs to be added.
- Multiple snapshots can share segment data inside the repository.
- Snapshots store metadata needed to restore indices, including mappings and settings of the backed-up indices.
- Global cluster state can be included or excluded optionally.

A snapshot is not a byte-for-byte copy of a running data directory. Never manually copy, modify, or delete internal files inside a repository using filesystem or object storage tools. Use snapshot APIs to manage repositories and snapshots.

### 5.1. How do snapshots differ from replicas?

| Criterion | Replica shard | Snapshot |
|---|---|---|
| Purpose | Increase availability and read capacity within the cluster | Backup for recovery after data loss or incident |
| Location | Inside the same Elasticsearch cluster | Inside an independent repository |
| Accidental index deletion | Recovery not guaranteed | Can restore if snapshot remains |
| Full cluster loss | Both primary and replica may be lost | Can restore onto another compatible cluster |
| History | Reflects current shard state | Preserves point-in-time states captured by snapshots |

Replicas are not backups. If an application accidentally deletes documents or a destructive operation propagates across the cluster, replicas synchronize that state. Snapshots provide a more independent recovery point.

## 6. Snapshot repositories

A snapshot repository is where Elasticsearch stores snapshot data. Common repository types include:

- Shared filesystem (fs).
- Amazon S3.
- Azure Blob Storage.
- Google Cloud Storage.
- Repositories or plugins supported by the deployed version and platform.

Repositories should reside outside the lifecycle of data nodes. If snapshots are stored on the same disk or machine as the cluster, a physical failure can destroy both live data and backups.

### 6.1. Example registering a filesystem repository

For an fs repository, configure path.repo in elasticsearch.yml on relevant nodes and ensure the path is mounted with consistent permissions across the cluster. After configuring and restarting nodes as required, register the repository:

~~~yaml
path.repo: ["/mnt/es-backups"]
~~~

~~~http
PUT /_snapshot/prod-backup
Content-Type: application/json

{
  "type": "fs",
  "settings": {
    "location": "/mnt/es-backups",
    "compress": true
  }
}
~~~

The path in the example must reside under an allowed path.repo and be accessible from all required nodes. Do not use a local directory that exists on only one node in a multi-node cluster.

For cloud repositories, install the required plugin and configure credentials via supported security mechanisms. Never hardcode access keys or secrets directly into source code, committed config files, or log output.

### 6.2. Verifying a repository

After registering, verify the repository:

~~~http
POST /_snapshot/prod-backup/_verify
~~~

List repositories:

~~~http
GET /_snapshot
~~~

Only add a repository to backup schedules after confirming the cluster can write to and read from the repository successfully. In multi-cluster environments, follow repository rules: never let multiple clusters write to the same repository simultaneously. A second cluster can register the repository in read-only mode if needed for restore or snapshot inspection.

## 7. Taking a manual snapshot

Example of taking a snapshot for log indices:

~~~http
PUT /_snapshot/prod-backup/logs-snapshot-2025-04-18?wait_for_completion=true
Content-Type: application/json

{
  "indices": "logs-*",
  "ignore_unavailable": true,
  "include_global_state": false,
  "partial": false
}
~~~

Notable options:

- indices: specifies indices or data streams to back up.
- ignore_unavailable: decides whether to ignore indices that do not exist or are unavailable.
- include_global_state: whether to include global cluster state in the snapshot.
- partial: decides whether to accept a snapshot containing only a subset of shards; for normal backups, avoid accepting partial snapshots if full recovery is the goal.
- wait_for_completion: if enabled, the request waits until the snapshot completes; for large snapshots, you can create asynchronously and check status later.

A snapshot must not be considered successful merely because the request was submitted. Check the final state and succeeded/failed shard counts.

### 7.1. Checking snapshot status

Read a specific snapshot:

~~~http
GET /_snapshot/prod-backup/logs-snapshot-2025-04-18
~~~

View status:

~~~http
GET /_snapshot/prod-backup/logs-snapshot-2025-04-18/_status
~~~

Inspect results to confirm the snapshot completed, no unexpected shard failures occurred, and all required indices are included in the snapshot.

## 8. Automating snapshots with Snapshot Lifecycle Management

Snapshot Lifecycle Management (SLM) lets you define snapshot schedules and old snapshot cleanup policies. SLM manages snapshot lifecycles inside repositories, while ILM manages index lifecycles inside clusters.

Example policy creating a snapshot daily at 01:30 and retaining snapshots by limits:

~~~http
PUT /_slm/policy/daily-logs-backup
Content-Type: application/json

{
  "schedule": "0 30 1 * * ?",
  "name": "<daily-logs-{now/d}>",
  "repository": "prod-backup",
  "config": {
    "indices": ["logs-*"],
    "ignore_unavailable": true,
    "include_global_state": false,
    "partial": false
  },
  "retention": {
    "expire_after": "30d",
    "min_count": 7,
    "max_count": 50
  }
}
~~~

Meaning:

- schedule: execution schedule using a cron expression supported by SLM.
- name: snapshot name pattern; the date portion is generated using date math.
- repository: destination repository.
- config.indices: scope of data to back up.
- retention.expire_after: maximum age before a snapshot becomes eligible for expiration.
- min_count: minimum number of snapshots to keep when possible.
- max_count: upper limit on snapshots to retain.

SLM retention can evaluate both snapshot age and minimum/maximum counts. Choose values carefully so you do not delete recovery points the organization needs. A policy does not guarantee successful backups just by being defined; monitor each run's result and repository errors.

### 8.1. Monitoring SLM

Read a policy:

~~~http
GET /_slm/policy/daily-logs-backup
~~~

Check status and statistics:

~~~http
GET /_slm/status
~~~

View execution history:

~~~http
GET /_slm/stats
~~~

Check recent snapshots in the repository against the expected schedule. If a backup fails, alert before exceeding the system's committed RPO.

## 9. Restoring snapshots

Restore recreates indices or data streams from a snapshot. You can restore to the original cluster after an incident or restore to another cluster for testing, data investigation, or environment migration.

Before restoring:

1. Confirm the repository is accessible and the snapshot still exists.
2. Check the Elasticsearch version that created the snapshot and the target cluster's version.
3. Identify the indices or data streams to restore.
4. Check whether target index names already exist or conflict with aliases.
5. Decide whether global state and feature states need to be restored.
6. Assess storage capacity, duration, and load on the target cluster.

### 9.1. Inspecting which indices are in a snapshot

List snapshots:

~~~http
GET /_snapshot/prod-backup/_all
~~~

Inspect a specific snapshot's details to determine included indices, state, and stored metadata. Pick the right snapshot for the recovery point needed; snapshot names do not replace checking completion status.

### 9.2. Restoring a single index

Example restoring a log index from a snapshot:

~~~http
POST /_snapshot/prod-backup/logs-snapshot-2025-04-18/_restore
Content-Type: application/json

{
  "indices": "logs-000042",
  "ignore_unavailable": true,
  "include_global_state": false,
  "include_aliases": false,
  "rename_pattern": "logs-(.+)",
  "rename_replacement": "restore-logs-$1"
}
~~~

The example renames the restored index to restore-logs-000042 to avoid overwriting or colliding with an existing index. When using a rename pattern, ensure the resulting name is valid and does not clash with existing indices.

Setting include_aliases to false avoids automatically restoring aliases from the snapshot when aliases are currently managed separately by the cluster. Once the restored index is verified, attach aliases according to plan. If aliases must be restored, check conflicts and impacts on read/write flows first.

### 9.3. Restoring multiple indices or data streams

The indices field can specify multiple indices or patterns. When restoring a data stream, the snapshot must contain the data stream and required backing index data; restore steps must follow the instructions for the corresponding Elasticsearch version.

Do not mechanically restore the entire cluster state onto a live production cluster. Global state can hold metadata such as persistent settings, templates, policies, and other cluster configs. Restoring everything can overwrite active configurations. When you only need to recover index data, typically exclude global state and handle aliases/templates/policies separately.

### 9.4. Monitoring the restore process

After submitting the restore request, monitor recovery:

~~~http
GET /_cat/recovery/restore-logs-*?v
~~~

Check shard status:

~~~http
GET /_cluster/health/restore-logs-*
~~~

Inspect mappings and settings of restored indices:

~~~http
GET /restore-logs-*/_mapping
~~~

~~~http
GET /restore-logs-*/_settings
~~~

Only switch read/write aliases after index recovery finishes and data is verified as appropriate.

## 10. Version compatibility during restore

Snapshots are tied to the Elasticsearch version that created them. Restores must obey Elasticsearch's version compatibility rules. In general, you cannot restore a snapshot created by a newer version into an older cluster; restoring across major versions also has restrictions and requires following supported upgrade paths.

Before executing:

- Record source and target versions.
- Consult snapshot/restore documentation for the exact versions.
- Confirm plugins, analyzers, and features used on the source cluster exist on the target cluster.
- Test restoring in staging or a temporary cluster if data is critical.

Do not assume snapshots are an arbitrary interchange format across all versions. To migrate data to an incompatible version, you may need supported step-by-step upgrades, reindex-from-remote, or another data migration workflow.

## 11. Restore testing and data verification

A backup is only valuable if it can be restored within target timeframes. Therefore, conduct periodic restore drills.

After restoring, verify:

1. The snapshot completed without unexpected shard failures.
2. Desired indices or data streams appeared.
3. Cluster health and shard allocation reached an acceptable state.
4. Mappings and settings match application requirements.
5. Document counts and data timestamps align with the snapshot.
6. Read/write aliases are attached to the right indices.
7. Key business queries run successfully.
8. Spring Data Elasticsearch applications can read and write as expected.
9. Actual restore duration satisfies RTO.

Record snapshot timestamps, restore times, storage sizes, index counts, shard counts, and verification results. Drill results help tune backup schedules, repository resources, and RTO/RPO targets.

## 12. Access control and protecting backups

Snapshot repositories often contain data equivalent in sensitivity to production data. Protect both access paths and storage locations:

- Grant snapshot create, read, and delete privileges only to required roles.
- Secure repositories via filesystem or cloud storage access controls.
- Use encryption in transit and at rest where supported by the platform.
- Manage credentials via secret stores or cluster security mechanisms.
- Restrict which clusters are allowed to write to a repository.
- Monitor repository capacity and write failures.
- Keep copies in a different failure domain from the source cluster.

If personal data deletion requests arise, evaluate active indices, valid snapshots, off-cluster backups, and expiration workflows. Deleting a document from an index does not remove that document from previously created snapshots. Do not promise complete erasure solely based on a single Elasticsearch delete operation.

## 13. Combining lifecycles with Spring Data Elasticsearch applications

Spring Data Elasticsearch focuses on entity mapping and document operations. Retention, rollover, and snapshots generally belong to Elasticsearch's operational layer, managed via index templates, ILM, SLM, data stream lifecycles, or corresponding admin APIs.

Applications should use an alias or data stream as a stable target name if the architecture requires rollover. Example:

~~~java
@Document(indexName = "logs-write", createIndex = false)
public class LogEvent {

    @Id
    private String id;

    @Field(name = "@timestamp", type = FieldType.Date)
    private Instant timestamp;

    @Field(type = FieldType.Keyword)
    private String level;

    @Field(type = FieldType.Text)
    private String message;

    // constructors, getters and setters
}
~~~

Here logs-write is an alias created and managed by provisioning. createIndex = false prevents repository bootstrap from auto-creating a physical index named after the alias if the alias does not exist yet. ILM handles rollover and index deletion per policy; SLM handles snapshots and snapshot retention.

Do not let individual Spring Boot instances create, delete, or alter lifecycle policies on startup. Operational changes should be centrally managed through deployment pipelines or controlled admin tooling. This prevents race conditions and ensures environments apply consistent configurations.

### 13.1. Writing through an alias

Repositories use entity metadata and the alias as the target:

~~~java
public interface LogEventRepository
        extends ElasticsearchRepository<LogEvent, String> {
}
~~~

When calling save, Spring Data uses the indexName declared on @Document. Elasticsearch routes write requests through the write alias to the current active index. When ILM rolls over, the alias is updated and the application keeps writing to the same logical name.

For read queries, specify an alias or index pattern covering the exact data retention window to search. A write alias usually points only to the write index; do not assume it also serves as a read alias for all history.

## 14. Designing retention and backups by data type

Do not apply a single policy to all indices. A reference classification:

| Data type | Online retention | Snapshot/backup considerations |
|---|---|---|
| Operational logs | Short to medium term, per investigation needs | Periodic snapshots if needed for incident investigation or compliance |
| Audit events | Per audit and legal policies | Long-term snapshots, strict access control, and recovery testing |
| Telemetry | Per monitoring and trend analysis needs | Selective backups or long-term archive |
| Search content rebuildable from database | Keep as needed for search | Can rebuild index from primary source, though rebuild time must be evaluated |
| Non-reconstructible data | Per data contract | High priority for snapshots and restore drills |

If Elasticsearch is purely a read model rebuildable from a primary database, snapshots may serve rapid recovery rather than being the sole source of truth. Evaluate index rebuild time, event replay capability, and acceptable data loss. If data exists solely in Elasticsearch, backup requirements must be stricter.

## 15. Common mistakes

### 15.1. Treating replicas as backups

Replicas reside in the same cluster and synchronize changes with primaries. Accidental deletions or logic bugs propagate to replicas. You need an independent snapshot repository.

### 15.2. Configuring ILM while forgetting snapshots

ILM can delete indices according to policy. If data must be recoverable after deletion time, valid snapshots or another source of truth to rebuild from must exist.

### 15.3. Creating snapshots without checking results

A submitted snapshot request does not guarantee the snapshot completed successfully. Check status, failed shards, and alert when scheduled runs fail.

### 15.4. Never testing restores

Repositories can lose access permissions, snapshots may be version-incompatible, or restore duration may exceed RTO. Restore drills verify backups are usable.

### 15.5. Placing the repository in the same failure domain

If a repository resides on the same disk or infrastructure that fails alongside the cluster, an outage can destroy both live data and backups. Use independent storage with separate protection policies.

### 15.6. Deleting indices manually while managed by ILM

Deleting indices outside policy can leave aliases, lifecycle states, and recovery plans inconsistent. Identify which policy owns an index and use controlled actions.

### 15.7. Restoring over production indices or aliases

Restores can fail due to existing names or alter read/write traffic if aliases are restored. Restore to a temporary name, verify, and only then switch aliases.

### 15.8. Retaining snapshots indefinitely

Incremental snapshots still consume metadata and segment storage. Retaining snapshots forever causes repositories to grow continuously. Define explicit SLM retention and monitor capacity.

## 16. Sample operational workflow

A workflow can be implemented in the following order:

1. Classify data and define online retention periods.
2. Design indices or data streams, read/write aliases, and rollover rules.
3. Create appropriate index templates and ILM policies.
4. Create an independent snapshot repository and verify access permissions.
5. Configure SLM policies matching RPO and backup retention.
6. Monitor ILM, SLM, repository status, capacity, and snapshot errors.
7. Periodically restore to a test environment or temporarily named indices.
8. Verify mappings, settings, document counts, queries, and aliases after restore.
9. Measure recovery time and adjust RTO/RPO if reality diverges from targets.
10. Review retention when business, regulatory, or cost requirements change.

Commonly used check commands:

~~~http
GET /_ilm/policy
GET /logs-*/_ilm/explain
GET /_alias/logs-read,logs-write
GET /_snapshot
GET /_snapshot/prod-backup/_all
GET /_slm/policy
GET /_slm/status
GET /_slm/stats
~~~

Results should be monitored with alerts rather than inspected manually only during incidents.

## 17. Conclusion

Retention policies determine how long search data remains online; ILM or appropriate lifecycle mechanisms manage rollovers, phase transitions, and index deletion. Snapshots create independent recovery points inside repositories, while SLM manages backup creation schedules and backup retention.

Aliases enable Spring Data Elasticsearch applications to continue using stable logical names when physical indices roll over or get restored. Applications should focus on reading/writing documents; deployment pipelines or operations manage index templates, lifecycle policies, and snapshot policies.

A backup strategy is only complete when snapshots are verified and restores are rehearsed. Design retention, snapshot schedules, independent repositories, access controls, and recovery workflows around actual RPO/RTO. Always verify indices, mappings, settings, and aliases after restoring before putting data back into service.
