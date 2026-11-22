# Log Replay in Java Logging — Safe Production Operations

## 1. What Is Log Replay and Why Is It Needed?

**Log replay** is the process of **re-reading existing log events** from a source that still holds the data and sending them back through a processing pipeline: parser, collector, index, observability store, or analytics workflow. The goal may be recovering observability data after an outage, backfilling a missing time window, fixing format parsing errors, performing audit reconciliation, or rebuilding search indexes.

A common scenario: a Java application continued writing logs to files while Elasticsearch/the collector was down. After the destination system recovers, the operations team needs to ship the un-ingested records to the query store. Or the system already ingested the logs, but an old parser mishandled timestamps; the raw logs must be re-read into a **new index** with the fixed parser for verification.

~~~text
Java application
    |
    v
File / stdout / archived logs / Kafka topic
    |                              |
    |                  [select offset or time range]
    +--------------+---------------+
                   |
                   v
          Replay reader / shipper
                   |
             parse, validate
                   |
           dedup + rate limit
                   |
                   v
       ISOLATED destination index
                   |
           compare and approve
                   |
                   v
       Cutover or end investigation
~~~

Replay in this context **does not mean re-executing the business logic that produced the log**. Re-sending an INFO line `"payment succeeded"` to a log collector must not trigger another payment. **Observability logs are not themselves business event logs**; they may lack global ordering, required data, durability guarantees, and the schema needed to reconstruct state.

Scenarios where replay should be considered:

- **Backfill:** logs exist in files/topics/archives but are missing from the observability system.
- **Reparse:** an old parser, multiline rule, or timezone mapping was wrong and needs re-interpretation.
- **Reindex:** moving data from a source index to an index with a new mapping/retention.
- **Incident investigation:** reconstructing a bounded set of logs scoped by requestId, service, or time range.
- **Migration:** testing a new observability pipeline with historical data without touching the live pipeline.
- **Disaster recovery:** rebuilding query indexes from a durably stored log archive, provided the source is still complete.

**Operational principle:** re-reading logs must not lose source data, overload the live pipeline, write duplicates outside policy, or recreate data that the organization is obligated to delete.

## 2. Distinguishing Commonly Confused Forms of Replay

| Concept | Input | Destination / Meaning | Main Risk |
| --- | --- | --- | --- |
| **Log replay / re-ingestion** | Log files, Kafka log topics, archives | Re-ingest into the observability pipeline | Duplicates, out-of-order events, wrong timestamps |
| **Log reprocessing** | Stored raw logs | Apply new parser/redaction/enrichment | Schema mismatch, exposing old sensitive data |
| **Reindex** | Already-indexed documents | Create a new index or adjust storage/query structure | Lost mappings, overwrites, conflicts |
| **Kafka consumer replay** | Records still retained in a topic | Consumer re-reads from an earlier offset | Side effects, altering consumer offsets |
| **Event-sourcing replay** | Domain events with schema and contract | Rebuild projections / business state | Side effects, ordering, and schema evolution |
| **Audit review** | Integrity-protected audit store | Reconciliation or forensic investigation | Must not alter or break the chain of evidence |

A plain text log line is not enough to replay a money transfer or email send. If the real goal is **restoring state from domain events**, a dedicated event-sourcing design must be used, controlling command handlers and external side effects. Do not use a general logging pipeline as a command replay system.

Similarly, **reindexing in Elasticsearch** from existing documents is not the same as re-reading lost files. If a document was never ingested and no backup source remains, reindex cannot regenerate that data on its own.

## 3. Define the Goal and the Source of Truth First

Before running a job, answer:

1. **Why replay?** Recovering missing logs, fixing parsing, migration, or verification?
2. **Where is the authoritative source?** Live/original file, rotated file, archive, Kafka topic, object storage, or old index?
3. **Exact scope?** Service, environment, tenant, time range, source files, partition/offset, traceId, or eventCode.
4. **Where will the destination write?** Isolated index, new namespace, test cluster, or approved production destination?
5. **Is overwriting allowed?** If yes, under what condition/version? If no, choose create-only and handle conflicts.
6. **What data must be preserved?** Event timestamp, source identity, raw bytes, ordering, metadata, redaction.
7. **Completion criteria?** How many unique events must be present, which gaps are filled, which parsed fields must match?
8. **Who approves and rolls back?** Operations owner, security, data retention, and the cutover operator.

Do not run a "replay all" command in production when only one day of logs for one service is needed. **A small, bounded scope** reduces cost and blast radius if the source or destination is mistaken.

An example plan:

~~~yaml
replayRunId: replay-20261110-01
purpose: repair-incorrect-timestamp-parsing
source: immutable-archive/orders/2026-11-09/
timeRangeUtc: "2026-11-09T00:00:00Z/2026-11-10T00:00:00Z"
destination: logs-orders-replay-20261110
parserVersion: orders-v4
mode: dry-run-then-bounded-write
maxRecordsPerBatch: 1000
maxRecordsPerSecond: 2000
approvalRef: change-1234
~~~

This is an **illustrative plan**, not a configuration schema supported by every tool. Avoid using real production names or connection secrets in documentation or over-privileged replay manifests.

## 4. Source of Truth, Timestamps, and Log Completeness

A log set may exist in multiple places:

~~~text
Java / Logback / Log4j 2 / JUL
        |
        +--> stdout/container runtime logs
        +--> live application.log
        +--> rotated + compressed files
        |
        v
Filebeat / Fluent Bit / OpenTelemetry Collector
        |
        +--> buffering / disk queue / Kafka
        |
        v
Search index / object archive / dashboard / backup
~~~

**The trustworthy data source** is not necessarily the first file found. A file may have been rotated, truncated, deleted, cover only part of the time window, or contain logs redacted differently from elsewhere. An old index may be missing records due to an ingestion outage. A backup may be older than the range that needs reconstruction.

An event can have several types of timestamps:

- **Event timestamp:** when the Java application created the event; must be preserved on replay to analyze the actual day it occurred.
- **Observed/ingest timestamp:** when the collector received it, or on a later replay; may be hours or days after the event.
- **Replay timestamp:** when the replay job reprocessed it. Should be stored separately as metadata.
- **Source offset/position:** where the record sits in a file/partition; not business time.

If a parser reassigns every timestamp to `"now()"`, old logs can appear as new errors today, skewing dashboards and alerts. **Never replace event time with replay time** unless there is an explicit migration contract and the original field is still preserved.

You must also document **gaps where data no longer exists**: if retention has already deleted records in Kafka or old files are lost, there is no way to replay records absent from the source. Results must clearly state the unrecoverable portion rather than claiming full recovery.

## 5. Delivery Guarantees: At-Most-Once, At-Least-Once, and Exactly-Once

During replay, a record may be read and sent multiple times, especially after a timeout:

~~~text
Reader sends event E -> Sink has written E
          |
       ACK lost
          |
Reader retries E -> Sink receives E again
~~~

The models:

| Semantics | Meaning | Consequence |
| --- | --- | --- |
| At-most-once | Each record is attempted at most once under the defined mechanism | May lose records if failure happens after advancing the cursor |
| At-least-once | Retries until acknowledged per policy | May produce duplicates |
| Exactly-once | Produces no duplicate observable effect within a **specific transactional boundary** | Requires matching source, sink, and transaction/idempotency design |

**At-least-once + idempotent sink** is a common strategy for log backfill. However, do not claim end-to-end exactly-once merely because Kafka has transactional processing: if the destination is an HTTP API, database, email, or Elasticsearch outside a linked transaction, you still need a mechanism to prevent duplicate effects at the destination.

Distinguish **records read**, **send attempts**, and **unique events stored**. When measuring completion, having more attempts than unique events due to retries is not automatically an error.

## 6. Designing Meaningful Deduplication Keys

If the source has an eventId that is **stable across all replays**, it can be used as a key together with a namespace scope:

~~~text
dedupKey = sourceIdentity + ":" + eventId
~~~

An eventId that is unique only **within a single source** is not guaranteed to be unique company-wide. Therefore, include service/source/tenant or partition in the key according to the contract.

Sources with built-in positions:

- **Kafka:** typically has topic + partition + offset for a physical record; offsets are per partition, with no topic-wide total order.
- **File:** has file identity + byte offset + boundary/length, but watch out for file rotation, inode reuse, file copies, and line endings.
- **JSON log:** may have an application-generated eventId, stable as soon as the LogEvent is emitted.
- **Search document:** has `_id`; verify whether the ID is already a stable event ID or is auto-generated anew by the backend on each ingest.

If there is no eventId, a content hash is a fallback **only after** evaluating whether identical content could represent two valid events. Two identical log lines from two different requests are not necessarily duplicates; hashing only the message can mistakenly drop real events.

Another issue: **same ID, different content**. Do not ignore this silently. It may indicate schema corruption, mapping bugs, ID collision, or a modified record; it requires alerting/conflict quarantine and a policy resolution workflow.

When replaying intentionally to **fix corrupted data**, the goal may be replacing the old document by version or writing to a new index; do not use create-only with the same ID and then wonder why the new data does not appear.

## 7. Checkpoints and Cursors: Where to Resume After Stopping?

A **checkpoint** stores the **next position to read** for each source/partition/file, allowing a job to stop and resume without rescanning all data.

~~~text
file-2026-11-09.log
    byte offset: 8,192,000
        |
        v
Replay batch records
        |
        v
Sink ACK + validate
        |
        v
Commit checkpoint for that source
~~~

Safety rules:

1. Do not advance the checkpoint merely because a record was **read** or **enqueued**; know the destination's acknowledgment condition.
2. Keep a separate cursor per file/partition, along with identity, parser version, and replayRunId when needed.
3. If the job restarts after the sink writes successfully but before the checkpoint commits, the record may be re-sent; **the destination must be idempotent**.
4. If a record fails to parse, have an explicit policy: halt, move to durable quarantine before advancing, or handle according to severity.
5. Do not share checkpoints between the live pipeline and replay if doing so alters live progress.
6. If the source file was replaced/truncated or the topic passed retention, do not trust an old offset to still point to the same data.
7. Use count reconciliation, per-batch checksums/hashes, and completion markers for sign-off.

**Do not automatically commit production offsets while a replay job is still experimental**, and do not reuse a live group/registry out of convenience. The goal of replay is to stay independent of active operational streams.

## 8. Standalone Java 17+ Example: Idempotent Replay to an Isolated Destination

This example uses the **Java Standard Library** and requires no Kafka, database, or file write permissions. It simulates 5 log positions with one duplicated delivery, one DEBUG record filtered out **by an illustrative policy**, and three events stored into a Map representing an **isolated index**.

Each event has a source and an eventId; when replaying a second time from offset 0, the program does not create a second copy in the index. If the same key has different content, the code **throws an exception** rather than overwriting or treating it as a valid duplicate.

Create **ReplayLogDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ReplayLogDemo {
    record Event(String source, String eventId,
                 String level, String code) {}

    record Positioned(long offset, Event event) {}

    record Result(int scanned, int inserted, int duplicates,
                  int filtered, long nextOffset) {}

    static Result replay(List<Positioned> input,
                         Map<String, Event> target,
                         long startOffset) {
        int scanned = 0;
        int inserted = 0;
        int duplicates = 0;
        int filtered = 0;
        long next = startOffset;

        for (Positioned line : input) {
            if (line.offset() < startOffset) {
                continue;
            }
            if (line.offset() < next) {
                throw new IllegalArgumentException("Out of order");
            }

            scanned++;
            Event event = line.event();
            if ("DEBUG".equals(event.level())) {
                // Illustrative policy: do not replay DEBUG.
                filtered++;
            } else {
                String key = event.source() + ":" + event.eventId();
                Event previous = target.putIfAbsent(key, event);
                if (previous == null) {
                    inserted++;
                } else if (previous.equals(event)) {
                    duplicates++;
                } else {
                    throw new IllegalStateException(
                            "Conflicting event ID: " + key);
                }
            }
            next = line.offset() + 1;
        }

        return new Result(scanned, inserted, duplicates, filtered, next);
    }

    public static void main(String[] args) {
        Event created =
                new Event("orders", "evt-100", "INFO", "ORDER_CREATED");
        Event failed =
                new Event("orders", "evt-101", "ERROR", "PAYMENT_TIMEOUT");

        List<Positioned> archive = List.of(
            new Positioned(0, created),
            new Positioned(1, failed),
            new Positioned(2, failed), // Same event delivered twice.
            new Positioned(3, new Event(
                    "orders", "evt-102", "DEBUG", "CACHE_HIT")),
            new Positioned(4, new Event(
                    "orders", "evt-103", "WARN", "ORDER_DELAYED"))
        );

        Map<String, Event> isolatedIndex = new LinkedHashMap<>();

        Result first = replay(archive, isolatedIndex, 0);
        Result replayed = replay(archive, isolatedIndex, 0);
        Result resumed = replay(
                archive, isolatedIndex, first.nextOffset());

        System.out.println("first=" + first);
        System.out.println("replay=" + replayed);
        System.out.println("resume=" + resumed);
        System.out.println("indexedUnique=" + isolatedIndex.size());
        System.out.println("keys=" +
                String.join(",", isolatedIndex.keySet()));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac ReplayLogDemo.java
java ReplayLogDemo
~~~

**Deterministic** output:

~~~text
first=Result[scanned=5, inserted=3, duplicates=1, filtered=1, nextOffset=5]
replay=Result[scanned=5, inserted=0, duplicates=4, filtered=1, nextOffset=5]
resume=Result[scanned=0, inserted=0, duplicates=0, filtered=0, nextOffset=5]
indexedUnique=3
keys=orders:evt-100,orders:evt-101,orders:evt-103
~~~

### Reading the Output

- **First pass:** scanned 5 positions; wrote 3 unique events; detected one duplicate of evt-101; skipped one DEBUG per the demo policy; next offset is 5.
- **Replay from the beginning:** re-scanned 5 positions without increasing the indexed event count; 4 records matched existing IDs and were counted as duplicates (evt-101 appeared twice), while DEBUG was still filtered.
- **Resume from checkpoint 5:** no new positions remained, so `scanned=0` and the index still holds three events.
- **Key ordering:** `LinkedHashMap` preserves insertion order in the demo; it does not prove that a distributed backend provides a similar global order.

### Important Limitations

1. The Map lives only in RAM; when the process restarts, dedup state and checkpoints **vanish**, so the example **does not prove durability or exactly-once**.
2. The code does not write files, talk to a collector, handle retries/ACKs, or coordinate a transaction between target writes and checkpoints.
3. The checkpoint is just a `long` on a single linear source. Production requires per-Kafka-partition or per-file-identity cursors; never use one number across all sources.
4. DEBUG is excluded **only to illustrate policy**. If the goal is full log recovery, do not filter DEBUG arbitrarily. For mandatory audit/security logs, follow separate retention and verification policies.
5. Using `source:eventId` as the key in the example omits complex escaping/normalization. Production needs an identifier contract that prevents collisions across tenants/services.
6. `Map.putIfAbsent` is not an atomic operation across Kafka, databases, and checkpoint files. A real destination must support conditional upsert/create-only and proper ACK tracking.
7. If the same ID has a different payload, the demo throws `IllegalStateException`. Production needs alerting, durable quarantine, and conflict resolution; never skip a corrupted record and mark the job complete.

**Key takeaway:** a second replay may re-read many events without necessarily creating more **unique documents**, provided identity is stable and the sink is designed to be idempotent.

## 9. Replaying from Files and Rotated Logs

With Logback `RollingFileAppender`, Log4j 2 `RollingFile`, or JUL `FileHandler`, data may reside in open files, rotated files, compressed files, or archives. Key guidelines:

- **Prefer reading stable snapshots/archives** rather than live files currently being written or rotated.
- Track **file identity + offset**, not just filename. The same `application.log` name can point to a different inode/file after rotation.
- Understand UTF-8 encoding, line endings, multiline Java stack traces, and JSON Lines. **Byte offset is not equivalent to line count**.
- Multiple files split by day or process have no global order; do not concatenate everything by filename and assume event-time order.
- If files are compressed, decompress/stream using tools with size limits and without overwriting the original logs.
- Verify source checksums, sizes, expected record counts, and timestamp ranges.
- Distinguish logs **truncated** by rotate/copytruncate from missing files, avoiding replaying stale data or skipping lost segments.

### Filebeat Registry

**Filebeat** stores file-reading state in its **registry**, including harvester/offset positions. When output has not ACKed and the process restarts, Filebeat may resend records that already reached the sink; this is one reason duplicates easily occur under at-least-once delivery.

**Do not delete or edit a running production Filebeat registry to "start over from the beginning."** Doing so can affect multiple inputs, cause massive duplication, alter live cursors, and make recovery harder for operators.

For backfills, consider a **separate** instance/config, separate data path/registry, include paths restricted to read-only archives, and output to an **isolated index/namespace**. Check filestream behavior by version, fingerprint, and file identity policy; a copied or renamed file may or may not be recognized as new depending on configuration.

**At-least-once does not guarantee all data still exists:** if a file rotated and was deleted before the shipper caught up, the source is gone and another backup is required.

## 10. Replaying with the OpenTelemetry Collector `filelog` Receiver

OpenTelemetry Collector Contrib includes the **`filelog` receiver** to tail and parse files. Some versions support `start_at: beginning` or `start_at: end` when the receiver starts.

An **illustrative isolated-source example**, which must be paired with an exporter/pipeline for your deployed collector version and is not a complete collector config:

~~~yaml
receivers:
  filelog/replay:
    include:
      - /archive/logs/order-service-2026-11-09.log
    start_at: beginning
    include_file_path: true
    encoding: utf-8
~~~

**Warning about offsets:** `start_at: beginning` governs the starting position for files **without recovered state**. According to the file input operator documentation, if persistent storage already holds offsets for a file, the stored state may take precedence; do not assume changing a single `start_at` key will force the receiver to re-read every record.

A cautious workflow:

1. Use a dedicated replay config/instance with read-only archive files.
2. Ensure replay storage/checkpoints are separate from the collector serving live logs.
3. Configure source/path/encoding properly; if logs are multiline, configure the appropriate operator.
4. Route output to a new sink with resource and batching limits.
5. Verify source files, record counts, parsed fields, lag, and duplicates.
6. Do not publish new dashboards or switch production routes before sign-off.

Do not assume every OTel Collector distribution includes the `filelog` receiver: it belongs to distributions that bundle the component, such as `collector-contrib`. Exact field names, versions, and processors must be checked against the reference for your running version.

## 11. Kafka Replay: Group IDs, Partitions, and Offsets

Kafka is well suited for storing event/log streams in topics with retention. However, **an offset is a position within a single partition**, not a business ID, and there is no single global order across a multi-partition topic.

Common replay approaches:

- A **dedicated consumer group** to re-read data still in the topic without affecting the live group's cursor.
- Using **`seek(TopicPartition, offset)`** or `seekToBeginning(...)` once the consumer has been assigned the relevant partitions.
- Determining offset ranges by timestamp or targeted inspection when backfilling a specific time window.
- For a new group with **no committed offsets**, `auto.offset.reset=earliest` can allow reading from the earliest **still-retained** offset when no offset exists.
- For a group that already has valid committed offsets, simply adding `auto.offset.reset=earliest` **will not make it re-read from the start**.

An **illustrative Java Kafka consumer fragment**, not standalone; it requires the Apache Kafka Clients dependency, an initialized consumer, and assigned partitions:

~~~java
TopicPartition partition =
        new TopicPartition("app-logs", 0);

// Use only in a dedicated replay consumer that has already been assigned.
// startOffset must be verified to still exist.
consumer.seek(partition, startOffset);

// poll() will fetch data from the seeked position per Kafka semantics.
ConsumerRecords<String, String> batch =
        consumer.poll(Duration.ofSeconds(1));
~~~

Do not run this fragment on a live consumer with arbitrary offsets, as it can cause a production group to replay records or skip data. Use a dedicated replay group, a principal scoped to read permissions, a topic allowlist, and an isolated output.

**Retention is a hard boundary:** `"earliest"` means the earliest offset **still retained**, not offset 0 in history. For topics that have already purged old data, you need archives, tiered storage, or backups if supported and permitted.

**Commit discipline:** commit replay progress only after processing reaches the defined ACK level; committing before the sink persists data can drop events. Retrying after a lost ACK can create duplicates; use a stable dedup key and an idempotent sink.

For Kafka 4.x, check the API/consumer config documentation for the exact version in use; additional offset reset options may appear in newer releases. Do not build scripts from old documentation and apply them blindly to a different cluster.

## 12. Elasticsearch/OpenSearch Reindex: Different from Re-Reading Log Files

If data is **already in an index**, Elasticsearch provides the **Reindex API** to copy documents from a source index to another destination index; it does not read raw files. A **learning-only** request example—do not run against a real system without verifying names, permissions, and mappings:

~~~http
POST /_reindex?wait_for_completion=false
Content-Type: application/json

{
  "source": {
    "index": "logs-orders-2026-11-09",
    "query": {
      "range": {
        "@timestamp": {
          "gte": "2026-11-09T00:00:00Z",
          "lt": "2026-11-10T00:00:00Z"
        }
      }
    }
  },
  "dest": {
    "index": "logs-orders-replay-20261110",
    "op_type": "create"
  },
  "conflicts": "proceed"
}
~~~

**Notes:**

- Source and destination must be different.
- Source requires `_source` to be enabled to reindex documents as required by the API.
- The API **does not automatically copy settings and mappings**; create the destination index with the right schema/template/retention beforehand.
- With `op_type=create`, documents with an existing ID at the destination cause version conflicts instead of overwriting. `conflicts: proceed` lets the job continue on defined conflict cases, but **does not mean all errors are ignored**.
- If the destination is an append-only data stream, `create`-only semantics must be respected.
- `wait_for_completion=false` returns a task ID if the job is accepted; **you must monitor the task and final outcome**, rather than treating the initial response as all documents indexed.
- The operation can increase cluster load, requiring throttling, batching, and monitoring of disk/CPU, shard failures, and version conflicts.
- To fix misparsed data, reindexing into a new index may require a controlled ingest pipeline/script; `create`-only does not replace existing documents.

For OpenSearch, APIs/fields and versions may look similar, but check the documentation for your specific version. Do not assume Elasticsearch and OpenSearch behave identically in every feature.

## 13. Replay and Parser/Schema Evolution

A major reason to replay is **fixing log parsing**. For example, an old parser treated `durationMs` as the string `"15ms"`, while the new parser wants the number `15`; or old multiline rules split a Java stack trace into multiple records.

When reprocessing:

1. Identify the **raw format/schema version** of the source for each period. Do not parse all historical files assuming today's encoder.
2. Select a new `parserVersion` and store `replayRunId`/`processorVersion` metadata for traceability.
3. Use **golden samples** covering INFO/WARN/ERROR, Unicode, exceptions, nulls, nested JSON, and malformed lines.
4. Preserve the **original event timestamp** and source identity; create separate `observedAt`/`replayedAt` fields.
5. Separate counts of **raw records**, **logical events after multiline**, **parsed events**, and **rejected/quarantined** records.
6. Check mappings/index templates and schema compatibility before loading large volumes.
7. Compare key fields: service, severity, requestId, traceId, eventCode, errorCode, and timestamps.
8. If redaction changed, ensure old records are still handled according to data permissions and retention; replay must not un-redact secrets from archives.

If the old parser already discarded stack trace lines and no raw files remain, the new parser **cannot recover the lost lines**. Replay can only use data that still exists in the source.

## 14. Replay Must Isolate Side Effects

In production, the biggest danger is feeding historical data through a pipeline that triggers **alerts, emails, webhooks, tickets, security decisions, or business commands**.

~~~text
Old ERROR log -> replay -> live alert rule -> "new incident"
Old AUDIT log -> replay -> automated workflow -> repeated action
Old event    -> replay -> side-effecting consumer -> writes data a second time
~~~

Therefore:

- Create a **replay index/namespace** and attach `replayRunId` and `sourceType=backfill` per policy.
- Separate replay ingestion from pipelines with actions such as email/webhook/ticket.
- For alerting dashboards, distinguish event timestamp from replay ingest timestamp; exclude replay sources from realtime alerts until data is verified.
- For Kafka topics containing **domain events**, ensure the replay consumer is **projection-only or side-effect disabled**; do not re-emit transactions/commands.
- Do not update the original production data lake/index without a cutover and rollback plan.
- Do not grant a replay job write/delete permissions broader than the approved scope.

A historical ERROR log is not an incident that just happened. However, do not lose real security/audit trails; use proper routing and record the replay so it can support investigations.

## 15. Privacy, Retention, and Legal Hold

Replay can **bring deleted or retention-expired personal data back into an index**, especially after restoring from backup. Guard against this just as carefully as in data restoration workflows.

Questions before replaying:

- Is the data in the source/archive still permitted to be processed for the current purpose?
- Which personal data has erasure/anonymization requests? Is there a deletion ledger/tombstone that must be applied before writing to the destination?
- Is there a legal hold or obligation to retain certain events, and what is its exact scope?
- Does the new destination enforce the same masking, ACL, encryption, retention, and access-limit policies?
- Were secrets/tokens accidentally logged in old records? If so, filter/redact them properly before ingestion.
- Has sharing with external processors/collectors been documented under contract?

**Do not use replay as a way to bypass deletion policies.** If the current index has legitimately erased PII, loading an old raw archive without applying the deletion ledger can "resurrect" that information.

Similarly, just because data lives in an audit log does not mean it can be propagated freely to another system. Replay for a new purpose still requires proper legal basis, authorization, and retention.

## 16. Batching, Backpressure, Cost, and Timing

A large replay can generate heavier load than live traffic even though the source is old data:

- CPU and heap for JSON/Grok/multiline/redaction.
- Disk/network bandwidth when reading archives and sending to collectors.
- Queues and retries in shippers, Kafka, and exporters.
- Storage/index merges, shard allocation, disk watermarks, and search latency.
- Retention pressure when the same data is also held in a replay index.
- Cloud ingest, indexing, egress, or object retrieval costs.

Controls to define:

| Control | Benefit |
| --- | --- |
| `maxRecordsPerSecond` or bytes/s | Caps replay load |
| `maxBatchSize` | Bounds memory and request size |
| `maxInflightBatches` | Prevents unbounded backlog buildup |
| Retry with backoff/jitter | Reduces load when the sink slows down |
| Bounded queue / durable spool | Prevents losing control of memory |
| Pause/resume + checkpoint | Allows safe stopping |
| Error/timeout monitoring | Detects failures before it is too late |
| Separate replay capacity | Limits impact on live ingestion |

**A larger queue does not make the sink faster.** If the accepted rate exceeds the indexed rate for a sustained period, the backlog grows until full; you must lower the replay rate or scale the destination.

Test a small batch during low-traffic hours, reconcile unique event counts and throughput, and then ramp up within approved limits. Do not replay days of ERROR logs with full stack traces into a live index when the cluster is near its disk watermark.

## 17. Dedicated Metrics and Dashboards for Replay

Useful metrics:

~~~text
replay_records_read_total{run,source}
replay_events_parsed_total{run,parser_version}
replay_events_rejected_total{run,error_code}
replay_events_inserted_total{run,destination}
replay_events_duplicate_total{run,destination}
replay_conflicts_total{run,destination}
replay_batches_failed_total{run,destination}
replay_bytes_read_total{run,source}
replay_checkpoint_offset{run,partition}
replay_backlog_records{run,source}
replay_ingest_latency_seconds{run,destination}
~~~

**Cardinality note:** if `replayRunId` is a unique value generated frequently, evaluate label/retention policies; never put `eventId`, `requestId`, `userId`, or raw messages into metric labels. Store `runId` in structured audit/governance logs and use bounded grouping labels for core metrics.

Counts to distinguish:

- **Read:** how many physical records were read from the source?
- **Parsed:** how many valid logical events remained after multiline/validation?
- **Inserted:** how many new unique events were stored at the destination?
- **Duplicate:** how many records matched an existing event and were idempotently skipped?
- **Conflict:** same ID but different payload or destination version?
- **Rejected/quarantine:** how many inputs could not be processed and await a decision?
- **Lag:** difference between event time and replay/ingest time; do not mistake history for a new incident.
- **Checkpoint:** how far has each partition/file progressed?

A reconciliation check over a **defined scope**:

~~~text
read_records
  = inserted + duplicates + filtered + rejected_or_quarantined
    + other_explicitly_accounted_outcomes
~~~

This formula is a **classification balance sheet** when every record is counted in exactly one branch, not an absolute identity for every pipeline. A malformed multiline event may span multiple lines; therefore, agree upfront whether you are counting **physical lines or logical events**. Report what is durably acknowledged, not merely accepted/enqueued.

## 18. Controlled Production Runbook

A practical runbook:

### Phase A — Planning

1. Record incident/change ID, `replayRunId`, reason, owner, time window, and data source.
2. Verify which archive/backup/topic source is complete, its checksums, and readability.
3. Define the exact scope by source, tenant, service, file/partition, offset, and UTC range.
4. Check retention, legal hold, deletion requests, PII/secrets, and read/write permissions.
5. Define stable event ID, dedup policy, conflict handling, parser version, and expected schema.
6. Choose an **isolated** destination, separate TTL/retention, and a rollback/cutover plan.
7. Set QPS/bytes limits, batch size, resource budget, checkpoint storage, and stop conditions.

### Phase B — Dry-Run and Trial

8. Verify connectivity, read-only permissions on the source, and write permissions only on the approved destination.
9. Run a very small slice (canary) or a dry-run that only counts/analyzes metadata.
10. Verify timestamps, severity, requestId, traceId, exceptions, multiline handling, and redaction.
11. Reconcile expected counts/hashes against output, and check duplicates/conflicts.
12. Measure impact on the live cluster; confirm no side-effecting consumers or alerts fired.

### Phase C — Monitored Replay

13. Start by batch/partition, keeping cursors independent per source.
14. Wait for durable ACKs per sink semantics before checkpointing.
15. Monitor read/inserted/duplicate/rejected/backlog, throughput, and latency.
16. If errors spike or the destination overloads, **pause** and investigate; do not increase concurrency unboundedly.
17. Stop cleanly at the defined snapshot/range boundary without spilling into live logs.

### Phase D — Verification and Closure

18. Reconcile counts, sampling, checksums/eventIds, timestamp ranges, and key fields.
19. Verify conflicted/quarantined records are resolved or documented with an open reason.
20. Verify deletion ledger/retention/ACLs and confirm no business alerts were misfired.
21. If cutover is needed, switch aliases/dashboards per the change plan; keep rollback capability.
22. Store the replay manifest, results, parser version, checkpoints, rationale, and approver in the appropriate governance store.
23. Clean up temporary resources and replay indexes per approved retention; do not delete original sources outside scope.

**Do not declare completion just because a job returned HTTP 200 or "submitted."** Many destinations run asynchronously; wait for task completion and re-verify the data.

## 19. Testing Replay and Resilience

| Test Case | What It Must Prove |
| --- | --- |
| First-time replay | Full set of unique events appears at the destination |
| Second replay of the same data | Document count does not grow outside policy |
| Lost ACK followed by retry | Idempotency prevents duplicates |
| Source has same ID with different payload | Conflict is detected, not silently overwritten |
| Checkpoint before/after sink write | No dropped records; retries process cleanly |
| Multi-partition Kafka | Independent offsets/cursors and correct per-partition ordering |
| File rotate/truncate | Does not jump to the wrong file identity/offset |
| Java multiline exception | One `Throwable` is one logical event, not dozens of records |
| Old vs. new parser | Fields/timestamps map accurately, schema version is clear |
| Source missing data due to retention | Reports the gap instead of claiming full recovery |
| Collector timeout / 429 | Backoff, pause, and replay resume work properly |
| Data containing PII/secrets | Redaction and access controls remain enforced |
| Data subject to erasure request | Not resurrected in the new destination |
| Live alert rules | Historical logs do not trigger unexpected tickets/pages |
| Low disk / index mapping conflict | Job halts safely and reports errors |
| Restore replay state | Cursors/manifests recover as designed |
| Async reindex | Tracks actual task completion and checks destination |

Prepare fixtures containing plain text logs, JSON, Unicode, stack traces, error codes, requestIds, and eventIds, using **synthetic data only**. Test with multiple concurrent workers to surface duplicate, race, and ordering issues. If side-effecting consumers exist, provide a controlled simulation/no-op mode.

For Java unit tests, the JDK example in this article only proves in-memory Map idempotency. End-to-end sign-off requires integration tests against a real backend or testcontainers and an isolated destination.

## 20. Dangerous Misconceptions

**"Log replay means re-running requests."** No. Observability logs record what happened, not commands authorized to re-execute business logic.

**"Setting `auto.offset.reset=earliest` makes every Kafka consumer re-read."** False if the consumer group already has valid committed offsets. Offset reset applies under specific conditions, and earliest only covers **retained data**.

**"Delete the production Filebeat registry to start over."** This can corrupt live ingestion progress and duplicate logs at scale. Use a separate replay reader/registry instead.

**"`start_at: beginning` always ignores checkpoints."** For the `filelog` receiver, persisted offsets may take precedence. Isolate receiver storage and check behavior for your version.

**"Logs with the same message are duplicates."** Two independent requests can log the same ERROR message. You need stable identity and source scope.

**"One record read = one document indexed."** Parsing, filtering, dedup, quarantine, retries, and indexing have distinct outcomes.

**"Reindex will recover logs missing from the index."** Reindex only uses documents in the existing source; you need files/archives to backfill un-ingested data.

**"Reindex automatically copies mappings and settings."** Elasticsearch requires preparing the destination; do not rely on the source schema appearing automatically.

**"Setting `op_type=create` means there can never be duplicates."** It prevents overwriting by ID within an API call, but requires a **stable ID**; if each ingest generates a new `_id`, the same event is still stored multiple times.

**"Replaying old logs into the live index is harmless."** It can spike disk usage, alerts, and ingest costs, and mix event time with ingestion time.

**"Increasing the queue size makes replay finish faster."** Queues absorb bursts; they do not increase the sink's sustainable throughput.

**"All data in backups can be loaded back."** Not necessarily: retention, erasure rights, legal holds, and redaction must be re-verified.

**"Seeing task accepted means it's done."** You need job completion, per-batch acknowledgments, counts, conflicts, and destination readbacks.

**"Sorting by timestamp gives exact order."** Clock skew, same-timestamp events, multi-partition Kafka, and async delivery mean there is no reliable global order without a sequence/ordering contract.

## 21. Pre-Run Checklist

- [ ] Rationale, owner, approval, and `replayRunId` are documented.
- [ ] Source still holds data for the requested time window; checksums/manifests verified.
- [ ] Scope is bounded by service, tenant, UTC time, file/partition/offset.
- [ ] Log replay is distinguished from domain-event replay and side effects.
- [ ] Destination index/namespace is **isolated** with least-privilege write permissions.
- [ ] Live pipeline offsets/registries are untouched.
- [ ] Stable `eventId`/dedup key and conflict-handling strategy are defined.
- [ ] Checkpoints are persisted only after ACKs per sink semantics.
- [ ] Retry/backoff, rate limiting, bounded queues, and pause/resume are in place.
- [ ] Parser, multiline, schema, timezone, and severity mappings are tested.
- [ ] Original event timestamps are preserved; replay metadata is stored separately.
- [ ] Alerts, webhooks, commands, or already-executed business logic are not re-triggered.
- [ ] Deletion ledger, PII/secrets, retention, legal hold, and ACLs are checked.
- [ ] Metrics for read/parsed/inserted/duplicate/conflict/rejected/lag are available.
- [ ] Canary/dry-run, count/ID reconciliation, and per-batch error checks are ready.
- [ ] Cutover/rollback and post-completion resource cleanup plans are ready.

**Conclusion:** Log replay in **production operations** is a way to **re-read stored observability data** to backfill, fix parsers, or rebuild indexes. It is safe when the source, scope, identity, checkpoint, ACK boundary, and destination are clearly defined; when idempotency prevents duplicates; and when replay is isolated from live system side effects. **Replay cannot recover data that is no longer at the source, does not guarantee exactly-once through retries alone, and must never bypass retention or privacy rules.**

## 22. References

- [Apache Kafka Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/): `auto.offset.reset`, consumer groups, and operational parameters in Kafka 4.4; verify against your actual version.
- [Apache KafkaConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html): `seek`, `seekToBeginning`, and offset behavior.
- [Elastic Filebeat — How Filebeat works](https://www.elastic.co/docs/reference/beats/filebeat/how-filebeat-works): registry, file identity, offsets, and at-least-once delivery.
- [OpenTelemetry Collector Contrib — File Log Receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/filelogreceiver/README.md): `filelog` receiver, `start_at`, `include`, `encoding`, and multiline.
- [OpenTelemetry Collector file input operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/file_input.md): persisted offsets may take precedence over `start_at`.
- [Elastic — Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex): source/destination, `_source`, `op_type`, `conflicts`, tasks, and mappings.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): distinguishing timestamp, observed timestamp, body, resource, and attributes.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): file/rolling appenders and log output mechanisms.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): file and supported output destinations.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): security, retention, limiting sensitive data, and log controls.
- [Oracle Java SE 17 — Map.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putIfAbsent(K,V)): semantics of the in-memory idempotent example.
