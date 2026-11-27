# Cluster Health, Shard Allocation, and Disk Watermarks

An Elasticsearch cluster can still respond to requests while not being in a healthy operational state. For example, a cluster may be yellow because replicas have not been allocated; some shards may be unassigned due to missing nodes or allocation rules; near-full disks can cause Elasticsearch to stop allocating new shards and eventually put indices into read-only mode. Checking only whether an endpoint returns HTTP 200 will cause the application to miss critical warning signs before incidents impact users.

Cluster health, shard allocation, and disk watermarks are three closely related mechanisms. Cluster health reports the overall state of shards; allocation explains where shard copies reside or why they remain unassigned; disk watermarks set protective thresholds so Elasticsearch avoids filling disks. This lesson covers reading these statuses, diagnosing root causes, monitoring from Spring Boot, and handling resource shortages safely.

## 1. What does cluster health indicate?

Elasticsearch provides the Cluster Health API to report the status of a cluster or an index. Status is based on whether primary shards and replica shards are allocated.

There are three main states:

| Status | Meaning | Common impact |
|---|---|---|
| green | All primary and replica shards are allocated | The cluster has full shard copies per current configuration |
| yellow | All primary shards are allocated, but at least one replica is unassigned | Primary data can still be served, but redundancy is reduced |
| red | At least one primary shard is unassigned | Part of the index's data may be unavailable for normal reads/writes |

### Green

Green indicates all configured primary and replica shards are active. This is a complete state in terms of allocation, but it does not guarantee every query is fast or every node is healthy. A green cluster can still have hot shards, high CPU, rising search latency, large thread pool queues, or disks approaching watermarks.

Therefore, green is an important signal rather than certification that every workload is performing well.

### Yellow

Yellow means primary shards are allocated, while at least one replica shard is unassigned. Reads/writes can still work against the corresponding primary shards, but the cluster has fewer copies than configured.

Common causes:

- Single-node cluster where indices have a replica count greater than 0.
- Not enough eligible nodes to place replicas.
- Allocation awareness requires a replica in another zone that currently lacks nodes.
- Disk watermarks or allocation filters prevent shard copies from being assigned.
- Replicas are currently recovering or relocating.

In single-node development environments, yellow may be the expected state. In production, prolonged yellow must be investigated because fault tolerance is reduced.

### Red

Red means at least one primary shard is unassigned. Part of the data in the affected index may be unavailable. Some requests may still succeed if they only touch active shards, but a red cluster should never be treated as acceptable for normal production operation.

Possible causes include:

- The node holding the primary shard was lost and no replica was available to promote.
- A shard copy is corrupted or shard data cannot be recovered.
- Disk or allocation rules prevent the shard from being allocated.
- An index is closed or has metadata issues.
- The cluster just suffered a node or storage failure.

A red cluster must be handled shard by shard and index by index. Never delete indices or force-allocate shards arbitrarily just to turn the status green.

## 2. Calling the Cluster Health API

Check the whole cluster:

~~~http
GET /_cluster/health
~~~

Check a single index:

~~~http
GET /_cluster/health/orders?level=indices
~~~

The result may include fields such as:

~~~json
{
  "cluster_name": "search-cluster",
  "status": "yellow",
  "number_of_nodes": 3,
  "number_of_data_nodes": 3,
  "active_primary_shards": 12,
  "active_shards": 20,
  "relocating_shards": 0,
  "initializing_shards": 0,
  "unassigned_shards": 4,
  "delayed_unassigned_shards": 0,
  "number_of_pending_tasks": 0,
  "task_max_waiting_in_queue_millis": 0,
  "active_shards_percent_as_number": 83.3
}
~~~

This is an illustrative example, not numbers from a specific cluster. Response structures may include additional fields depending on the Elasticsearch version.

Notable fields:

- status: green, yellow, or red.
- number_of_nodes: total nodes in the cluster.
- number_of_data_nodes: nodes with the data role.
- active_primary_shards: active primary shards.
- active_shards: total active shard copies.
- relocating_shards: shards currently moving between nodes.
- initializing_shards: shards currently initializing/recovering.
- unassigned_shards: unassigned shards.
- number_of_pending_tasks: cluster state tasks waiting.
- task_max_waiting_in_queue_millis: longest task wait time in the queue.

### Choosing the right level

- level=cluster: overall status.
- level=indices: adds per-index details.
- level=shards: adds per-shard details.

Do not call level=shards continuously on every health probe if the cluster has a very large shard count. Detailed data is useful when investigating, yet the request is heavier and the response is larger.

### Timeout and wait_for_status

The Health API supports options to wait for a status or shard condition. Example:

~~~http
GET /_cluster/health/orders?wait_for_status=yellow&timeout=5s
~~~

The request can wait until the cluster reaches at least yellow or the timeout expires. This is helpful in provisioning/tests, but do not set long timeouts on health probes called frequently.

Do not use wait_for_status=green to gate application startup on all replicas being active if a single-node development environment is intentionally yellow. Readiness conditions must match the actual topology.

## 3. Cluster health differs from application health

Cluster health reflects shard allocation in Elasticsearch. It does not directly measure:

- Application API response times.
- Error rates of repository methods.
- Whether mappings match business data.
- Whether queries use filters/sorts efficiently.
- Fine-grained disk latency, CPU saturation, or GC pauses.
- Whether the service account has sufficient privileges on the indices the application uses.

An application can return errors even when the cluster is green due to invalid credentials, missing aliases, or write-blocked indices. Conversely, a yellow cluster can still serve all requests requiring primary shards if unassigned replicas do not impact that access path.

Combine cluster health with allocation, disk, node, thread pool, indexing/search latency, and application-layer error-rate metrics.

## 4. What is shard allocation?

Allocation is the process by which Elasticsearch decides which shard copy goes onto which node. A primary shard and its replicas are shard copies belonging to the same shard group.

Example index with two primaries and one replica:

~~~text
Shard group 0:
  Primary 0 -> Node A
  Replica 0 -> Node B

Shard group 1:
  Primary 1 -> Node B
  Replica 1 -> Node C
~~~

Elasticsearch must obey constraints such as:

- Never place two copies of the same shard group on the same node.
- Nodes must have an appropriate role to hold shards.
- Disks must satisfy allocation policies.
- Allocation awareness and filtering must be satisfied.
- The cluster must have remaining shard capacity within configured limits.
- Nodes and shards must be in states permitting recovery/relocation.

Allocation is not just balancing shard counts evenly. Elasticsearch also weighs capacity, node attributes, disk watermarks, and operational rules.

### Unassigned shards

An unassigned shard is a shard copy not currently placed on any node. With unassigned replicas, the cluster is usually yellow if all primaries remain active. With unassigned primaries, the cluster is red.

Unassigned does not automatically mean data is lost. The cluster may lack an eligible node or be waiting on an allocation condition. Check the allocation explanation to identify the reason.

### Initializing and relocating

- INITIALIZING: the shard is being initialized or recovered on the target node.
- RELOCATING: the shard is moving from a source node to a target node.
- STARTED: the shard copy is active on the node.

A cluster can temporarily show relocating/initializing shards during node joins, rolling restarts, or allocation rebalancing. Monitor duration and progress. If the state lingers, check recovery, disk throughput, and network.

## 5. Checking which node holds each shard

Cat Shards API:

~~~http
GET /_cat/shards?v
~~~

Filter by index:

~~~http
GET /_cat/shards/orders?v
~~~

You can select key columns:

~~~http
GET /_cat/shards/orders?v&h=index,shard,prirep,state,docs,store,node,unassigned.reason
~~~

Useful columns:

- index: index name.
- shard: shard number.
- prirep: p for primary, r for replica.
- state: shard state.
- docs: document count.
- store: shard storage size.
- node: node holding the shard copy.
- unassigned.reason: recorded reason when a shard is unassigned, if available.

Cat APIs are great for quick manual investigation. For automation, prefer structured JSON APIs over parsing text tables when suitable endpoints exist.

### Comparing primary and replica

Verify whether a shard group has its primary and replica on different nodes. If a replica is unassigned, find the root cause before changing replica counts or allocation rules.

Never try to place a replica on the same node as its primary. Elasticsearch deliberately prevents this so replicas are not lost alongside the primary during a node failure.

## 6. Using Allocation Explain to find root causes

The Cluster Allocation Explain API answers why a shard is unassigned or why it is allocated to a specific node.

Example querying replica shard 0 of the orders index:

~~~http
GET /_cluster/allocation/explain
{
  "index": "orders",
  "shard": 0,
  "primary": false
}
~~~

If no specific shard is specified, the API may pick a shard to explain by default. When investigating, specify index, shard, and primary/replica so results are targeted.

The response may contain:

- current_state: current state.
- unassigned_info: details on why the shard is unassigned.
- can_allocate: yes, no, or throttled.
- allocate_explanation: overall description.
- node_allocation_decisions: per-node decisions.
- deciders: allocation deciders allowing or rejecting each node.

Illustrative decision example:

~~~json
{
  "index": "orders",
  "shard": 0,
  "primary": false,
  "current_state": "unassigned",
  "can_allocate": "no",
  "allocate_explanation": "cannot allocate because disk usage exceeds the high watermark",
  "node_allocation_decisions": [
    {
      "node_name": "data-1",
      "node_decision": "no",
      "deciders": [
        {
          "decider": "disk_threshold",
          "decision": "NO",
          "explanation": "the node is above the high watermark"
        }
      ]
    }
  ]
}
~~~

Exact fields vary by version and cluster state. Read the deciders to find the blocking condition instead of relying on a single allocate_explanation line.

### Common deciders

| Decider | Possible meaning |
|---|---|
| disk_threshold | Disk watermark blocks allocation |
| filter | Node fails allocation include/exclude/require rules |
| awareness | Insufficient nodes in the required failure domain |
| same_shard | Cannot place two copies of the same shard on one node |
| max_retry | Shard exceeded automatic allocation retry limit |
| throttling | Cluster is limiting concurrent recoveries/relocations |
| enable | Allocation is disabled for that operation type |
| replica_after_primary_active | Replica waiting for primary to become active |

Decider names and response details depend on Elasticsearch version. Use allocation explain instead of guessing from yellow/red status.

## 7. What are disk watermarks?

Disk watermarks are utilization thresholds Elasticsearch uses to govern shard allocation and protect nodes from running out of disk space.

Common thresholds include:

- low watermark: restricts allocating new shards onto nodes whose disks are filling up.
- high watermark: restricts additional shards and may trigger moving shards off the node.
- flood-stage watermark: critical threshold where Elasticsearch can set indices read-only-allow-delete to stop disks from filling further.

Watermarks can be configured as percentages of used space or as minimum free disk space. When configured as percentages, higher usage brings the node closer to the threshold. When configured by free space, the node must maintain at least a specified amount of free space.

Default values and headroom calculations can change across Elasticsearch versions. Do not memorize one set of numbers and apply them to every cluster; read the effective cluster settings of your running version.

### Low watermark

When a node crosses the low watermark, Elasticsearch generally avoids allocating additional shards onto that node. Existing shards are not necessarily moved away immediately simply because the low watermark was crossed.

This prevents the node from accepting even more data as free space shrinks.

### High watermark

When a node crosses the high watermark, Elasticsearch can attempt to relocate shards off the node to lower disk usage. Relocation succeeds only if an eligible destination node with sufficient disk space exists.

If all data nodes exceed the high watermark, the cluster has nowhere to move shards. Allocation explain will show destination nodes rejected by the disk decider.

### Flood-stage watermark

Flood-stage is the final protective threshold. When crossed, Elasticsearch can set index.blocks.read_only_allow_delete on indices with shards on the affected node.

This causes write operations to be rejected. Search can still work if shards and indices have no corresponding read block.

Once disk usage drops below the appropriate threshold, Elasticsearch has mechanisms to handle the flood-stage block automatically depending on version and cluster state. Operators should check actual settings and root causes before manually clearing blocks.

Do not merely send commands to clear blocks while disks remain full. The block may be reapplied or the node may remain in a dangerous state.

## 8. Checking node disk usage

Cat Nodes API:

~~~http
GET /_cat/nodes?v&h=name,roles,cpu,heap.percent,ram.percent,disk.used_percent,disk.avail,disk.total
~~~

Cat Allocation API:

~~~http
GET /_cat/allocation?v
~~~

These APIs help inspect:

- Which nodes have high disk usage.
- How much disk space remains free.
- How many shards are allocated per node.
- Whether disk usage is skewed across nodes.

Cat Allocation is useful for inspecting disk space and shard counts. It does not replace allocation explain when you need to know why a specific shard is rejected.

### Checking disk from the OS

Infrastructure monitoring must also watch the filesystem backing Elasticsearch's data path. Pay attention to:

- The actual disk partition holding the data path.
- Disk quotas or container volume limits.
- Filesystem inodes if the environment enforces inode limits.
- Space consumed by logs, snapshot caches, and temp files.
- Disk latency and throughput.
- Data growth rate over time.

Free space on the host does not guarantee free space inside a container volume if quotas or separate volumes are used.

Never manually delete files inside Elasticsearch's data directory. That can corrupt shard data. Free disk space by deleting indices via APIs under retention policies, expanding volumes, or cleaning data/logs outside the data path per operational procedures.

## 9. Reading effective disk watermark settings

Inspect cluster settings:

~~~http
GET /_cluster/settings?include_defaults=true&flat_settings=true
~~~

Look for relevant settings:

- cluster.routing.allocation.disk.threshold_enabled
- cluster.routing.allocation.disk.watermark.low
- cluster.routing.allocation.disk.watermark.high
- cluster.routing.allocation.disk.watermark.flood_stage
- cluster.routing.allocation.disk.watermark.*.max_headroom

Some settings appear under persistent, transient, or defaults. Effective values must be determined according to cluster setting precedence.

### Percentage vs. free-space

Example configuration by percentage:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.disk.watermark.low": "85%",
    "cluster.routing.allocation.disk.watermark.high": "90%",
    "cluster.routing.allocation.disk.watermark.flood_stage": "95%"
  }
}
~~~

Example configuration by free space:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.disk.watermark.low": "50gb",
    "cluster.routing.allocation.disk.watermark.high": "30gb",
    "cluster.routing.allocation.disk.watermark.flood_stage": "10gb"
  }
}
~~~

These are syntax examples only, not recommended values for every cluster. When using free-space thresholds, values must decrease with severity: low requires more free space than high, and flood-stage requires the least free space.

### Max headroom

Some versions support max headroom for percentage-based watermarks to cap the maximum free space required on very large disks. Configuring percentages without understanding headroom can lead to misinterpreting effective thresholds.

Check docs and effective settings for the exact running version before making changes. Do not copy watermarks from another cluster without considering node capacities, data growth, and recovery requirements.

## 10. Why can disk watermarks turn a cluster yellow or red?

Suppose a node is nearly out of disk space:

1. Low watermark keeps Elasticsearch from allocating new shards onto that node.
2. High watermark may trigger relocating shards off the node.
3. If no destination node has enough space, replica or primary recovery can be blocked.
4. Unassigned shard copies turn the cluster yellow or red depending on whether primaries or replicas are unassigned.
5. If flood-stage is crossed, indices can be marked read-only-allow-delete and write requests fail.

A cluster can turn yellow because replicas have nowhere to go even while primaries stay active. If the node holding a primary fails while replicas are unassigned, data can transition to red.

Thus, yellow caused by disk pressure is not just a redundancy concern. It can be an early warning before a node failure makes part of the data unavailable.

## 11. Other causes of unassigned shards

Disk space is a common cause, but not the only one.

### Insufficient nodes

A single node cannot hold both the primary and replica copy of the same shard group. If an index has a replica count greater than 0, replicas remain unassigned and the cluster is usually yellow.

Handling depends on the goal:

- Add eligible data nodes.
- Lower replica count in environments not needing redundancy.
- Intentionally accept yellow in development, while documenting expected status.

Do not reduce replicas in production merely to make health green if the system requires fault tolerance.

### Allocation awareness

Clusters can be configured to spread shard copies across different zones or racks. If a required zone lacks nodes or disk capacity, replicas can stay unassigned.

Check node attributes and awareness settings before altering policies.

### Allocation filtering

Indices or clusters can have include, exclude, or require rules. If all eligible nodes are excluded, shards cannot be assigned.

Inspect index settings and cluster settings for allocation filters. Do not delete filters arbitrarily if they exist to pin data to specific node tiers or regions.

### Shard limits

Clusters enforce limits on how many shards can be open/allocated per node or cluster-wide. Exceeding limits causes new index creation or shard allocation to fail.

Check shard limits appropriate for your version and license. Solutions typically involve reducing unnecessary shards/indices, scaling node capacity appropriately, or adjusting index design.

### Disabled allocation or throttled recovery

Maintenance operations may temporarily disable allocation. Clusters can also throttle recovery when many shards need to move simultaneously.

Check cluster settings and recovery status before re-enabling allocation. Do not enable allocation while a maintenance procedure intentionally disabled it without understanding the reason.

## 12. Monitoring shard recovery and relocation

When a node rejoins or shards move to another node, Elasticsearch performs recovery. Recovery consumes disk I/O, network bandwidth, and CPU.

View recovery:

~~~http
GET /_cat/recovery?v
~~~

View detailed index recovery:

~~~http
GET /orders/_recovery?human=true&detailed=true
~~~

Track relocation:

~~~http
GET /_cat/shards/orders?v
~~~

Fields can show:

- Current shard state.
- Source node and target node.
- Files/bytes recovered.
- Recovery percentage.
- Recovery duration.
- Current stage.

Slow recovery is not necessarily an error. With large shards, slow disks, or constrained networks, recovery can take a while. Compare progress over time and inspect resources.

### Avoid adding load while the cluster is recovering

Avoid running huge reindex jobs, force merges, heavy snapshots, or unbounded bulk ingestion concurrently during cluster recovery, as disk and network resources compete.

If recovery concurrency or bandwidth needs adjustment, measure impact and tune to capacity. Setting limits too high can degrade primary workloads.

## 13. Cluster health and index lifecycle

Index lifecycle affects shard counts, disk usage, and allocation.

For time-series append data, rollover bounds the size of each backing index. ILM can transition indices through hot, warm, cold, and delete phases per policy.

Key notes:

- Each backing index carries its own primary and replica settings.
- Rollover creates new indices from the matching template.
- Too many shards increase cluster overhead.
- Overly large indices lengthen recovery times.
- Shrinking requires specific preconditions and workflows.
- Force merging can consume heavy disk/CPU.
- Retention should delete indices via policy rather than manually deleting files.

Cluster health should be monitored per critical index, not solely cluster-wide. A low-priority index can turn overall health yellow while transactional indices remain green, or vice versa.

## 14. Monitoring cluster health from Spring Boot

Spring Boot applications can use Spring Boot Actuator and Elasticsearch health indicators if supported by dependencies/versions. Health indicators typically verify connectivity, though they do not necessarily verify business prerequisites such as write alias targets or policy-compliant shard allocation.

You can build a custom health indicator for specific requirements, such as requiring critical indices to exist and the cluster not to be red.

Illustrative pseudocode:

~~~java
@Component
public class ElasticsearchClusterHealthIndicator
        implements HealthIndicator {

    private final ElasticsearchClient client;

    public ElasticsearchClusterHealthIndicator(
            ElasticsearchClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            ClusterHealthResponse response =
                client.cluster().health();

            String status = response.status().jsonValue();

            if ("red".equals(status)) {
                return Health.down()
                    .withDetail("clusterStatus", status)
                    .build();
            }

            return Health.up()
                .withDetail("clusterStatus", status)
                .withDetail(
                    "unassignedShards",
                    response.unassignedShards()
                )
                .build();

        } catch (Exception ex) {
            return Health.down(ex).build();
        }
    }
}
~~~

Method names, response types, and API client builders must match your Elasticsearch Java API Client version. This shows the structure for a custom indicator; if a default health indicator already exists, avoid registering a duplicate without reason.

### Readiness and liveness

Readiness answers whether an instance should receive traffic. Liveness answers whether the process is alive.

Reasonable policies might be:

- Cluster red: readiness for Elasticsearch-dependent features can be down.
- Cluster yellow: readiness can remain up if needed primary shards are active and the system accepts reduced redundancy.
- Cluster unreachable: readiness down for Elasticsearch-dependent services.
- Disk warning without write blocks: readiness can remain up while emitting alerts/metrics.
- Misconfigured write alias: readiness for write services should be down or degraded.

Do not automatically restart the application via liveness solely because Elasticsearch is temporarily red or unreachable. That does not fix the cluster and can trigger restart storms.

### Health indicators must not be too heavy

Do not call heavy diagnostic APIs on every probe if Kubernetes polls probes frequently. Use lightweight cluster health checks for probes and run allocation/disk diagnostics in lower-frequency monitoring jobs.

Do not perform real write operations on every health check. If write-path verification is needed, use controlled canaries separate from frequent readiness probes.

## 15. Metrics to monitor

Cluster health is an aggregate metric. To catch issues before the cluster turns red, monitor multiple indicators.

| Group | Metric or signal |
|---|---|
| Cluster | health status, active primaries, active shards, unassigned shards |
| Allocation | unassigned reason, relocating, initializing, recovery duration |
| Disk | used percent, free bytes, watermark proximity, disk latency |
| Node | CPU, heap, GC, memory, network, filesystem |
| Indexing | indexing rate, bulk latency, rejected writes |
| Search | search latency p50/p95/p99, query rate, failed searches |
| Thread pool | queue size, rejected count for write/search |
| Cluster state | pending tasks, task wait time |
| Application | repository error rate, timeouts, retry counts, target index/alias |

### Alerts to configure

Useful alerts include:

- Cluster status turns red immediately.
- Prolonged yellow beyond acceptable operational windows.
- Unassigned primaries greater than 0.
- Prolonged unassigned replicas.
- Disk approaching low/high/flood-stage watermarks.
- Node disk exceeding forecast thresholds.
- Spikes in write rejections or 429s.
- Stalled recovery making no progress.
- Rising pending cluster tasks and long queue waits.
- Required aliases or indices failing to resolve.

Thresholds and alert durations must be tuned to cluster baselines. Never use one uniform threshold for every environment or workload.

## 16. Distinguishing cluster health from disk pressure and write blocks

A cluster can be yellow with no write blocks. Conversely, an index can be write-blocked even when health is green.

Examples:

| Health | Disk/block | Interpretation |
|---|---|---|
| green | Normal disk, no block | Full allocation; still monitor latency and load |
| yellow | Unassigned replicas on single node | Primaries work, but redundancy is reduced |
| yellow | Disk watermark blocks replica allocation | Address capacity or node placement |
| green | One index has operator write block | Shard copies may be active, yet index refuses writes |
| red | Unassigned primary | Part of the data may be unavailable |
| yellow | Single-node cluster, replica count 1 | May be expected state in development |

Do not rely on health status alone to conclude writes can succeed. Read block settings and operation error responses.

## 17. Safe sequence for handling disk watermarks

When a node approaches full disk:

**Step 1: Identify nodes and filesystems.** Use Cat Nodes, Cat Allocation, and OS monitoring to see which disk is filling up.

**Step 2: Identify space-consuming shards.** Use Cat Shards and index stats to find the largest indices/shards on the node.

**Step 3: Investigate growth.** Determine whether growth comes from normal ingestion, stalled rollovers, broken retention, or logs/snapshots consuming disk.

**Step 4: Add capacity.** Expand volumes or add eligible nodes; delete old indices only when retention policy permits.

**Step 5: Verify allocation.** Use Allocation Explain to confirm target nodes can accept shards and the disk decider no longer rejects them.

**Step 6: Check blocks.** Inspect index settings to see whether read_only_allow_delete or other blocks remain active.

**Step 7: Restore writes.** Clear blocks only per root cause and policy; test controlled writes.

**Step 8: Monitor recovery.** Watch shard relocation, recovery, disk, and write rejections after restoration.

Never manually delete segment files or shard data from the filesystem. Never lower watermarks to force allocation onto full nodes. Those actions can corrupt data or incapacitate the cluster.

## 18. Recovering unassigned shards

Once allocation explain identifies the reason, take the appropriate action:

| Reason | Handling direction |
|---|---|
| Insufficient nodes for replicas | Add eligible nodes or reduce replicas where acceptable |
| Disk watermark | Free/expand disk and verify allocation |
| Allocation filter | Fix filters or add matching nodes |
| Awareness | Add nodes in the right zone/rack or review policy |
| Allocation disabled | Re-enable per procedure once maintenance ends |
| Recovery throttled | Monitor progress and tune capacity/concurrency carefully |
| Max retry | Find root cause, then trigger allocation retry if appropriate |
| Primary lost without replica | Restore from snapshot or evaluate specialized shard recovery |

### Reroute is not a universal fix

The Cluster Reroute API lets operators request manual allocation commands. However, reroute can be rejected by allocation deciders or alter redundancy.

Use reroute only after reading allocation explanation and having a clear plan. Never run allocate_stale_primary or allocate_empty_primary just to turn the cluster green without accepting data-loss risk. Force-recovering primaries can discard recent data or create empty shards.

If a primary cannot recover, prioritize restoring from a verified snapshot. Use risky recovery options only when incident procedures have evaluated and approved them.

## 19. Configuring replicas across environments

Single-node development cannot place replicas on separate nodes. You can set replica count 0 on dev/test indices if redundancy is not required:

~~~http
PUT /orders-dev/_settings
{
  "number_of_replicas": 0
}
~~~

Production should choose replica counts based on:

- Number of data nodes and failure domains.
- Availability SLOs.
- Read throughput.
- Disk capacity.
- Recovery time.
- Replication and network overhead.

Do not set replica counts higher than available nodes/failure domains can accommodate without clear intent. Conversely, having more nodes than replicas does not guarantee cross-zone distribution unless awareness is configured.

## 20. Configuring allocation awareness

If a cluster spans multiple availability zones, configure node attributes and awareness so primary/replica copies spread across failure domains.

Example node config:

~~~yaml
node.attr.zone: zone-a
~~~

On a node in another zone:

~~~yaml
node.attr.zone: zone-b
~~~

Cluster setting:

~~~http
PUT /_cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.awareness.attributes": "zone"
  }
}
~~~

If strict awareness is needed to prevent placing replicas when a zone is missing, consider forced awareness settings per Elasticsearch version docs. Forced awareness can leave replicas unassigned when a zone fails; that is an intentional trade-off to avoid putting both primary and replica in the same failure domain.

Awareness does not replace backups. Replicas protect against certain node failures, not accidental deletions, corruption, or business bugs where snapshots are required.

## 21. Integration tests for health and allocation

You can use Testcontainers to run a compatible Elasticsearch instance in integration tests. Scenarios include:

- Create an index with 1 primary and 1 replica on a single node; assert health is yellow due to the unassigned replica.
- Create an index with replica count 0; assert health is green once the primary is active.
- Check Cat Shards or Cluster Health API to assert unassigned shard count.
- Verify allocation explain returns the expected decider in a reproducible setup.
- Enable index.blocks.write and verify writes fail even while the cluster stays green.
- Test service health indicators distinguishing red, yellow, and connection failures.

Single-node Testcontainers cannot reproduce all multi-node or multi-zone allocation cases. Testing awareness, relocation, and node loss requires a multi-node test cluster or dedicated environment.

### Do not test flood-stage by filling CI disks

Do not write data until a container fills the CI filesystem. That can disrupt runners and cause flaky tests. Instead:

- Unit test flood-stage error response classification.
- Integration test enabling a write block on a test index to confirm block handling.
- Use a dedicated test cluster to verify real disk watermarks with safe resource caps.

## 22. Runbook when the cluster turns yellow or red

When receiving an alert:

1. Call Cluster Health API at cluster and index levels.
2. Determine whether unassigned shards are primaries or replicas.
3. Use Cat Shards to identify index, shard, node, and state.
4. Call Allocation Explain for unassigned shards.
5. Check disk watermarks and allocation settings.
6. Check whether any nodes disconnected, restarted, or ran out of capacity.
7. Check allocation awareness, filters, and shard limits.
8. Pick remediation matching the decider.
9. Monitor recovery/relocation.
10. Confirm health and data integrity after recovery.

For red clusters, identify the exact affected primary shards and data before taking action. If a primary has no recoverable copy, evaluate snapshots and disaster recovery procedures. Never force-allocate empty primaries just to silence a red alert.

## 23. Common mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| Cluster yellow on single node | Replicas cannot sit on the same node as primaries | Accept for dev or add nodes/adjust replicas |
| Cluster red after node loss | Primary shard has no active copy | Restore node/replica or snapshot |
| Replicas unassigned despite free disk | Awareness/filter/shard limit | Use allocation explain |
| Shards do not leave full node | No eligible destination node with enough disk | Add capacity and inspect deciders |
| Writes rejected while health green | Index block or security privileges | Inspect index settings and error type |
| Index read-only after disk pressure | Flood-stage watermark | Resolve disk, then verify/clear block |
| Prolonged recovery | Large shards, slow disk/network, or many recoveries | Track recovery and capacity |
| Cluster health green yet search slow | Hot shards, heavy queries, or node saturation | Check latency, shard/node stats, and thread pools |
| Pending tasks climbing | Slow cluster state updates or many changes | Check master nodes and allocation churn |
| Allocation explain shows throttled | Recovery concurrency is capped | Track progress; avoid sudden load spikes |
| Replicas clustered in one zone | Awareness unconfigured or wrong node attributes | Configure and verify failure-domain placement |
| Flaky yellow tests | Tests do not control replica/node topology | Use fixed topology and matching assertions |

## 24. Monitoring and operational checklist

- [ ] Monitor cluster health green/yellow/red.
- [ ] Monitor health individually for critical indices.
- [ ] Alert when unassigned primaries occur.
- [ ] Monitor prolonged unassigned replicas.
- [ ] Monitor initializing and relocating shards.
- [ ] Use Cat Shards to inspect node placement.
- [ ] Use Allocation Explain for unassigned shards.
- [ ] Monitor disk used/free on each data node.
- [ ] Monitor low, high, and flood-stage watermarks.
- [ ] Read effective cluster settings instead of assuming defaults.
- [ ] Monitor read-only-allow-delete and write blocks.
- [ ] Monitor recovery progress, disk latency, and network.
- [ ] Verify allocation awareness/filters and shard limits.
- [ ] Never manually delete files in Elasticsearch data paths.
- [ ] Never lower watermarks to mask lack of capacity.
- [ ] Never force-allocate stale/empty primaries without assessing data loss.
- [ ] Separate readiness and liveness.
- [ ] Never call heavy diagnostic APIs too frequently inside health probes.
- [ ] Maintain Testcontainers tests for health, replicas, and write blocks.
- [ ] Maintain a runbook for yellow/red and disk pressure incidents.

Cluster health shows shard copy availability, allocation explain pinpoints why shards are unassigned, and disk watermarks protect the cluster when node capacity drops. All three signals should be read together: yellow may mean missing replicas due to topology, red may mean lost primaries, and write blocks can occur even when health is green. Monitoring per-node disk, unassigned shards, recovery, and allocation deciders catches incidents early. When resolving issues, fix the underlying capacity, node placement, or policy cause before altering allocation/blocks, then confirm shard recovery and read/write health afterward.
