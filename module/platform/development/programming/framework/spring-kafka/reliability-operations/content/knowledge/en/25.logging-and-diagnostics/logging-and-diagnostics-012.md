# Correlating logs with broker metrics in Spring Kafka

When a Spring Kafka application reports producer timeouts, rising consumer lag, or slow listener processing, application logs usually show only **what the client sees**. Broker metrics show **how the Kafka cluster is handling requests, replication, and partitions**. Broker logs add server-side causes such as leader errors, ISR changes, authorization denials, or quotas. Accurate diagnostics require aligning all three sources on the same timeline and scope: cluster, broker, client, topic, partition, and request type.

Correlating logs with broker metrics does not mean finding a log line sharing the exact name of a metric. A broker metric is usually a periodic aggregate; a log may represent a single event; a single ProduceRequest can carry multiple records and partitions; and a single record may retry across multiple brokers. Thus, the two data sources **complement and explain each other** rather than always matching one-to-one.

In the **Spring Kafka Reliability Operations** module, the goal is building an investigation workflow that answers:

- What error did the application hit while sending or receiving Kafka records?
- Which broker handled the request at that time?
- Did request latency rise in queuing, local processing, replication, or throttling?
- Did the error affect one topic/partition or the whole cluster?
- Did consumer lag rise because producers sent faster, consumers processed slowly, rebalances occurred, or broker fetches behaved abnormally?
- Do logs and metrics provide enough evidence to decide on retries, pauses, failovers, or opening an incident?

**Core principle:** start from a concrete log, pin down timestamp and scope, then compare against metrics for the exact broker/request/topic in the same window. Never conclude a broker is broken from one application exception alone, and never conclude a record succeeded just because broker throughput looks high.

## 1. Three telemetry layers to correlate

A Kafka pipeline normally has at least three telemetry sources:

| Source | Who emits it? | What does it show? | Key limitation |
|---|---|---|---|
| Application logs | Spring service | Business events, listeners, exceptions, topic/partition/offset, traces | Sees only the application's perspective |
| Kafka client metrics/logs | Producer/consumer JVM | Send/fetch/request latency, retries, errors, poll progress | Does not see full broker/replication state |
| Kafka broker metrics/logs | Kafka brokers/controllers | Request queues, produce/fetch errors, ISR, leaders, quotas, server exceptions | Mostly aggregated, not per-business-record logs |

You can view the relationship as:

~~~mermaid
flowchart TD
    A["Spring application log"] --> D["Incident timeline"]
    B["Kafka producer/consumer metrics"] --> D
    C["Kafka broker metrics"] --> D
    E["Kafka broker/controller logs"] --> D
    D --> F["Isolate cluster / broker / client / topic / partition"]
    F --> G["Choose action and verify result"]
~~~

Each source answers a different piece:

- Application log: “I called send for this topic and got TimeoutException.”
- Producer metric: “Client retries rose, request latency spiked, and buffer waits climbed.”
- Broker metric: “Produce request queue grew, request handler idle dropped, and broker throttling rose.”
- Broker log: “Broker enforced a quota on the client or a partition lacked ISR.”

When all four signals align in one time window, the broker overload/throttling hypothesis is far stronger than looking at one exception alone.

## 2. Define the exact scope before comparing

Before querying logs or metrics, pin down **exactly what is being compared**.

| Dimension | Example | Question |
|---|---|---|
| Environment | prod, staging | Do logs and metrics belong to the same environment? |
| Kafka cluster | kafka-primary | Are you inspecting the exact cluster the app connects to? |
| Service | orders-service | Which service emitted the error? |
| Client ID | orders-producer-2 | Which producer/consumer instance hit the issue? |
| Consumer group | billing-service | Which group has lag or commit failures? |
| Topic | orders.created | Which topic is impacted? |
| Partition | 4 | Is the issue isolated to one partition or many? |
| Broker ID | 2 | Which broker was leader/receiver at that time? |
| Request type | Produce, Fetch, OffsetCommit | Which request type is slow/failing? |
| Time window | 10:05–10:10 UTC | Do logs and metrics cover the same time window? |

An error on broker 2 at 10:05 may involve a partition whose leader moved to broker 4 at 10:07. Querying only the current leader can miss the broker responsible during the incident.

### 2.1. Cluster identity and environment

Do not mix staging logs with production metrics just because topic names match. Keep consistent cluster/environment labels across log fields and metric labels.

If a service connects to multiple Kafka clusters, record the producer role or cluster alias explicitly. A dashboard listing only topic without cluster can blend identically named topics from two different clusters.

### 2.2. Broker ID and broker address

Broker ID is the broker's logical identifier in the cluster; hostnames/IPs can change across deployments. Telemetry pipelines should preserve broker ID, hostname, and cluster identity so investigations work before and after node replacements.

Never use dynamic hostnames as the sole dimension when autoscaling or ephemeral pods are involved.

## 3. Start from an application log with enough context

A helpful Kafka incident log records **operation, outcome, and Kafka coordinates**. Producer example:

~~~json
{
  "timestamp": "2026-11-15T10:05:21.431Z",
  "level": "ERROR",
  "service": "orders-service",
  "environment": "prod",
  "cluster": "kafka-primary",
  "event": "kafka_publish_failed",
  "producerRole": "business",
  "clientId": "orders-producer-2",
  "topic": "orders.created",
  "keyHash": "a8c2...",
  "eventId": "order-event-42",
  "traceId": "example-trace-id",
  "exceptionClass": "TimeoutException",
  "outcome": "failed"
}
~~~

This is an illustrative application-defined log structure; Spring Kafka does not emit all of these fields automatically in this exact schema.

Consumer logs might record:

~~~json
{
  "timestamp": "2026-11-15T10:05:23.008Z",
  "level": "WARN",
  "service": "billing-service",
  "cluster": "kafka-primary",
  "event": "kafka_record_processing_failed",
  "consumerGroup": "billing-service",
  "clientId": "billing-consumer-1",
  "topic": "orders.created",
  "partition": 4,
  "offset": 9812,
  "eventId": "order-event-42",
  "traceId": "example-trace-id",
  "exceptionClass": "DataAccessException"
}
~~~

Useful fields:

- UTC timestamp precise enough to align with metric scrape windows.
- Service, environment, and Kafka cluster.
- Producer client ID or consumer group/client ID.
- Topic, partition, and offset once a ConsumerRecord exists.
- Stable business event ID or correlation ID, if permitted for logging.
- Operation and outcome: send, receive, commit, retry, recovery.
- Normalized exception class/category.
- Trace ID/span ID to locate related traces.

**Never log raw payloads, access tokens, or personal data just to improve correlation.** For sensitive keys, log a hash or an approved business identifier.

### 3.1. Producer logs and consumer logs carry different information

Before the broker acknowledges a produce, the application may know topic/key and exception without final partition/offset. On send success, the callback supplies RecordMetadata containing topic, partition, and offset.

Consumers receive ConsumerRecord, which immediately provides topic, partition, and offset upon delivery. Use these coordinates to trace specific records on the consumer side.

### 3.2. Kafka protocol correlation ID

The Kafka protocol includes a correlation ID for requests/responses on a connection. Client DEBUG logs may emit request/correlation IDs depending on version and logger category. However, application business logs normally have no visibility into that protocol correlation ID.

Do not confuse the Kafka protocol correlation ID with a business event ID or W3C Trace ID. Their scopes and lifecycles differ.

## 4. Broker metrics are aggregates, not per-record logs

Kafka brokers expose metrics via JMX and built-in monitoring hooks. Commonly used metrics include:

| Group | Common JMX metric | Operational meaning |
|---|---|---|
| Broker traffic | MessagesInPerSec | Messages received by the broker over time |
| Broker traffic | BytesInPerSec / BytesOutPerSec | Inbound/outbound byte throughput |
| Produce/Fetch | FailedProduceRequestsPerSec | Rate of failed Produce requests |
| Produce/Fetch | FailedFetchRequestsPerSec | Rate of failed Fetch requests |
| Produce/Fetch | TotalProduceRequestsPerSec | Rate of Produce requests |
| Produce/Fetch | TotalFetchRequestsPerSec | Rate of Fetch requests |
| Request latency | TotalTimeMs | Total request duration by request type |
| Request latency | RequestQueueTimeMs | Time spent waiting in the request queue |
| Request latency | LocalTimeMs | Local broker processing time |
| Request latency | RemoteTimeMs | Wait time for remote processing/replication per request semantics |
| Request latency | ResponseQueueTimeMs | Time waiting in the response queue |
| Request latency | ThrottleTimeMs | Time the request was throttled |
| Replication | UnderReplicatedPartitions | Partitions where replicas lag behind |
| Replication | UnderMinIsrPartitionCount | Partitions below min ISR |
| Replication | IsrShrinksPerSec / IsrExpandsPerSec | ISR shrink/expand activity |
| Availability | OfflinePartitionsCount | Offline partitions count |
| Availability | ActiveControllerCount | Active controller status per cluster |
| Network | NetworkProcessorAvgIdlePercent | Average idle ratio of network processors |
| Request handlers | RequestHandlerAvgIdlePercent | Idle ratio of request handler threads |
| Queues | RequestQueueSize / ResponseQueueSize | Queue depth if supported by metric/version |

Exact object names, metrics, scopes, units, and exports depend on Kafka version, broker distribution, and JMX exporter. These are **familiar JMX names**, not a guarantee every broker version exposes the exact same set.

### 4.1. JMX object name pattern

A broker metric typically has an object name like:

~~~text
kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec
kafka.server:type=BrokerTopicMetrics,name=FailedProduceRequestsPerSec
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce
kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions
~~~

These object names merely illustrate common structure. Topic-specific metrics can add a topic dimension, and different Kafka versions may group metrics differently.

### 4.2. Broker-wide vs. topic-specific metrics

Broker-wide metrics answer “how much total traffic is this broker handling?” Topic-specific metrics answer “which topic is driving traffic or errors?”

Looking only at broker-wide BytesInPerSec can let one high-volume topic mask a failing small topic. Conversely, topic-specific metrics aid isolation while requiring care not to build dashboards with unbounded dynamic topics.

### 4.3. Read RequestMetrics by request type

Kafka has many request types: Produce, Fetch, Metadata, OffsetCommit, JoinGroup, Heartbeat, and others. When request latency climbs, separate by request type.

For instance, rising Produce latency impacts producer sends; rising Fetch latency impacts consumer progress. OffsetCommit request errors are a different issue from produce errors.

Never add Produce and Fetch latencies into one single “Kafka latency” number.

## 5. Client metrics bridge application logs and broker metrics

Producer and consumer clients also export their own metrics. They often bridge application exceptions and broker request metrics.

### 5.1. Producer metrics

| Kafka producer metric | Signal to watch |
|---|---|
| record-send-rate | How many records the producer is sending |
| record-error-rate | Record send error rate per client semantics |
| record-retry-rate | Rising internal producer retries |
| request-latency-avg/max | Request round-trip time to broker |
| record-queue-time-avg/max | Time records wait in producer accumulator |
| bufferpool-wait-time | Producer blocking for buffer memory |
| produce-throttle-time-avg/max | Broker quota/throttling impacting producer |
| connection-count | Number of connections to brokers |
| metadata-age | Age of metadata held by the producer |

When application logs show TimeoutException, check producer retry rate and request latency at the same timestamp. If retries climbed before the final error, the client may have tried recovering transient errors until hitting delivery timeout.

### 5.2. Consumer metrics

| Kafka consumer metric | Signal to watch |
|---|---|
| fetch-rate / fetch-latency | Whether Fetch requests are progressing |
| records-consumed-rate | Rate at which consumer processes/receives records |
| bytes-consumed-rate | Inbound data throughput |
| records-lag-max | Maximum lag across assigned partitions when available |
| commit-latency-avg/max | Slow offset commits |
| commit-rate | Commit frequency |
| heartbeat-rate / heartbeat-response-time | Group membership/heartbeat health |
| assigned-partitions | Number of partitions owned by the consumer |

Exact client metric names and availability depend on Kafka client version and metric scope. Consumer group lag can also be computed by exporters/AdminClient as log end offset minus committed offset, rather than being a single broker metric.

### 5.3. Healthy clients do not prove healthy brokers (and vice versa)

A consumer can fetch smoothly while its listener stalls on a database. A producer can send cleanly while downstream consumer lag grows due to insufficient consumer capacity.

Comparing client metrics against broker metrics distinguishes:

- Broker/network failing to serve requests.
- Client not issuing requests fast enough.
- Listener/business logic unable to keep up.
- Offset commit or transaction issues.

## 6. Aligning logs and metrics on a single timeline

This is the most critical step in incident response.

Suppose application logs show TimeoutException at 10:05:21 UTC. Workflow:

1. Identify log timestamp and timezone.
2. Identify cluster, client ID, topic, and producer/consumer role.
3. Open broker metrics over a window before and after the failure, e.g., 10:00–10:10 UTC.
4. Check broker leader/partition assignment at that exact time.
5. Compare request latency, failed request rate, retries, queue time, ISR, and throttling.
6. Search broker logs around that time by broker ID and request/topic context.
7. Check whether the same client errored on other brokers or only one node.
8. Identify when metrics returned to baseline and application error rates dropped.

~~~text
10:04:50  Producer retry rate starts climbing
10:05:05  Produce request latency rises on broker 2
10:05:12  Broker logs record quota throttle
10:05:21  Spring service logs TimeoutException
10:05:30  FailedProduceRequestsPerSec spikes
10:07:00  Throttling drops after traffic/quota adjustment
10:07:20  Producer retries return to baseline
10:08:00  Application send failures drop
~~~

This timeline is a hypothetical example illustrating correlation. In real incidents, use actual timestamps and metrics from your environment.

### 6.1. Use a sufficiently wide time window

Do not inspect only the single minute containing the error log. Inspect:

- **Before the error:** which metric shifted first?
- **During the error:** which request/replication/queue metrics climbed together?
- **After the error:** which metric recovered first, and how soon afterward did the app recover?

Size the window relative to scrape interval and aggregation window. If Prometheus scrapes every 30 seconds, a 10-second query window may miss samples or distort trends.

### 6.2. Clock synchronization

Application pods, brokers, controllers, Prometheus, and log collectors must share synchronized time (e.g., NTP/chrony). Clock skew makes logs and metrics appear offset from one another.

Store timestamps in UTC, keep timezones explicit, and remember metric timestamps reflect scrape/recording evaluation times rather than when each Kafka record appended.

### 6.3. Scrape interval and rate window

Rate metrics compute across multiple samples. If the query range is too short relative to the scrape interval, results can look empty or noisy.

Use an appropriate range such as 5m or 10m for incident overview, then zoom into narrower windows when sample density allows.

## 7. Broker logs: finding the right logger category

Kafka brokers use varying logging frameworks and logger categories across versions/distributions. Useful categories include:

| Logger/category (reference) | Typically covers |
|---|---|
| kafka.server.KafkaApis | Handling API requests like Produce/Fetch |
| kafka.network.Processor | Network request/response processing |
| kafka.network.RequestChannel | Request queue/response flow |
| kafka.server.ReplicaManager | Replication, ISR, and replica state |
| kafka.cluster.Partition | Leader/partition state |
| kafka.controller | Controller, leadership, and metadata changes |
| kafka.coordinator.group | Consumer group coordination |
| kafka.log.LogManager | Log segments, retention, and storage |
| kafka.authorizer.logger or authorizer implementation logger | Authorization decisions, depending on config/version |

Exact category names and log levels depend on Kafka version, security plugins, and logging config. Never leave DEBUG enabled across the whole broker long-term just to chase one bug; log volume can explode and hurt performance/storage costs.

### 7.1. Broker logs do not record every successful record

Kafka brokers normally do not write an INFO line for each successfully appended record. Produce requests batch multiple records together. Consequently:

- Finding no log for an event ID does not prove the broker never received the record.
- Broker metrics can rise without matching per-record success logs.
- One broker error log can apply to an entire request/batch, not a single business event.
- To verify a specific record, combine producer RecordMetadata, topic/partition/offset, and consumer evidence.

### 7.2. Targeted log-level increases

When DEBUG is necessary, specify the exact logger category, broker, and a short window. Have a runbook to restore log levels after investigation. Never leave request-level DEBUG running in production without evaluating payload exposure, throughput, and disk pressure.

### 7.3. Authorization logs

If a producer logs TopicAuthorizationException, broker authorization logs can show the rejected principal, resource, and operation depending on authorizer/config. That is far stronger evidence than guessing from overall error rates.

Never log secrets, credentials, or tokens in application/broker logs. Restrict access to security audit logs.

## 8. Correlation is not always one-to-one

One application send does not necessarily correspond to one broker request:

- Producers batch multiple records together.
- One ProduceRequest can carry data for multiple partitions/leader brokers.
- Producers retry requests after transient failures.
- A record may route to a new leader broker after a metadata refresh.
- Broker metrics aggregate across many clients and topics.
- Logs may be emitted at request, partition, or controller-event granularity.

Example:

~~~text
KafkaTemplate.send(event A)
KafkaTemplate.send(event B)
KafkaTemplate.send(event C)

Producer accumulator:
  batch topic-X partition-0 -> broker-1
  batch topic-X partition-2 -> broker-3

Broker metrics:
  broker-1 Produce request rate +1
  broker-3 Produce request rate +1
~~~

Do not expect three logical sends to produce three broker request logs. Likewise, one failed request can affect multiple records.

### 8.1. Batching and compression

Producer batching/compression separates request-level bytes, request counts, and record counts. When comparing BytesInPerSec against application send counts, remember byte metrics also reflect serialized/compressed size, protocol overhead, and request aggregation.

An uptick in byte throughput cannot be translated straight into business event counts without knowing size distributions and batching behavior.

### 8.2. Retries and leader changes

A producer may send to an old partition leader, receive an error, refresh metadata, and retry to the new leader. The old broker logs an error while the new broker records a successful request.

During investigations, inspect leader assignments and controller logs over time rather than only the current leader.

## 9. Mapping: which application error maps to which broker metrics?

The table below is a starting point. These are **investigative relationships**, not rigid 1-to-1 exception-to-metric mappings.

| Application/client symptom | Broker metrics to inspect | Broker logs to search |
|---|---|---|
| Producer TimeoutException | Produce TotalTimeMs, RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, FailedProduceRequestsPerSec, throttle | Request timeouts, replication/ISR, quotas, network |
| Rising producer retries | Produce request latency, FailedProduceRequestsPerSec, throttle, network idle | Leader changes, broker overload, request errors |
| NotEnoughReplicas / NotEnoughReplicasAfterAppend | UnderReplicatedPartitions, UnderMinIsrPartitionCount, ISR shrinks | ReplicaManager/Partition ISR events |
| NotLeaderOrFollower | LeaderCount, OfflinePartitionsCount, controller changes | Leader/partition transitions, metadata/controller logs |
| UnknownTopicOrPartition | Topic/partition metadata, OfflinePartitionsCount, controller logs | Topic creation/deletion, metadata/partition errors |
| TopicAuthorizationException | Authorization audit/logs, request failures | Authorizer denials, principal/resource/operation |
| RecordTooLargeException | Request size/produce failures; broker request logs if present | Rejected requests/record size validation |
| Producer throttling | ThrottleTimeMs, produce-throttle-time, request latency | Quota enforcement/throttle messages |
| Consumer Fetch timeout | Fetch TotalTimeMs, FailedFetchRequestsPerSec, RequestQueueTimeMs, network metrics | Fetch errors, leader/replica availability |
| Rising consumer lag | Fetch request rate/latency, BytesOutPerSec, group membership, broker load | Group coordinator/rebalance/leader logs |
| OffsetCommit failure | OffsetCommit request metrics/latency, group coordinator health | Group coordinator errors, generation/member changes |
| Under-replicated partitions | UnderReplicatedPartitions, ISR shrink/expand, OfflinePartitionsCount | ReplicaManager/Partition/controller logs |

### 9.1. Producer TimeoutException

Do not stop at the exception line. Compare:

- Kafka producer request latency and retry rate.
- Broker Produce request queue/local/remote times.
- Produce failure rate.
- Throttle time.
- ISR/under-replicated partitions.
- Network processor and request handler idle percentages.

If only broker 2 shows high request queue/latency while peer brokers look normal, suspect a hotspot or node-specific fault. If the whole cluster spikes together, inspect aggregate load, replication, or network issues.

### 9.2. NotEnoughReplicas

This error relates to replication/ISR conditions when producers request matching acknowledgements. Inspect ISR shrinks, under-replicated partitions, and broker/controller logs around the failure time.

Never resolve it by weakening producer acks without an approved durability decision.

### 9.3. NotLeaderOrFollower

Usually stems from metadata/leadership no longer matching the broker receiving the request, or the broker not being a valid leader/replica for the operation. Inspect controller logs, partition leader transitions, and client metadata refresh/retries.

Brief transient errors during leader elections may self-heal; if sustained, investigate offline partitions, controller health, and broker health.

### 9.4. Consumer lag

Rising lag does not automatically mean broker fetches are broken. The listener may be slow, consumers paused, groups rebalancing continuously, or input rate exceeding processing capacity.

Compare consumer-side records-consumed-rate and listener latency against broker Fetch metrics/BytesOutPerSec, group coordinator logs, and committed offsets.

## 10. Reading RequestMetrics by time component

Kafka RequestMetrics typically break request time into components such as:

- RequestQueueTimeMs
- LocalTimeMs
- RemoteTimeMs
- ResponseQueueTimeMs
- TotalTimeMs
- ThrottleTimeMs

Verify exact names and semantics for your Kafka version and request type.

A conceptual view:

~~~text
Request arrives at broker
    |
    v
RequestQueueTimeMs
    |
    v
LocalTimeMs
    |
    +--> RemoteTimeMs (if request waits on replication/remote work)
    |
    v
ResponseQueueTimeMs
    |
    v
Response sent back to client

ThrottleTimeMs: quota enforcement time per request semantics
TotalTimeMs: total duration per version metric definition
~~~

### 10.1. Rising queue time

If RequestQueueTimeMs grows, requests are waiting before being picked up. Check:

- Did RequestHandlerAvgIdlePercent drop?
- Did RequestQueueSize grow?
- Are broker CPU/GC abnormal?
- Is there a traffic burst or connection surge?
- Does one broker carry a partition leadership hotspot?

Do not blindly raise request handler thread counts; first identify whether CPU, disk, network, or locks are the bottleneck.

### 10.2. Rising local time

High LocalTimeMs indicates the broker spends time executing locally: disk/log appends, metadata, authorization, CPU, or internal work depending on request type.

Correlate with broker CPU, disk latency, page cache, log flush behavior, and broker logs.

### 10.3. Rising remote time

For requests awaiting replication/replica acks, remote time rises when followers lag, inter-broker networking degrades, or ISR/replication is unhealthy.

Inspect UnderReplicatedPartitions, ISR shrinks, replication lag, network throughput, and inter-broker connectivity. Do not assume every Produce request shares identical remote-time semantics; it varies with acks, request type, and version.

### 10.4. Rising throttle time

Quota throttling may be intentional policy enforcement. When throttle time climbs, check the quota entity (user/client-id), broker quota settings, and producer traffic.

One client can be throttled while overall broker CPU/network remain comfortably idle. Never conclude the cluster is overloaded solely from throttle time.

## 11. Replication metrics help explain produce failures

When producers use acks=all, replication health directly affects whether brokers can acknowledge writes.

Signals to watch:

| Metric | Interpretation |
|---|---|
| UnderReplicatedPartitions | Partitions with replicas lagging behind leader |
| UnderMinIsrPartitionCount | Partitions whose ISR is below configured min ISR |
| IsrShrinksPerSec | ISR is shrinking |
| IsrExpandsPerSec | ISR is expanding back |
| OfflinePartitionsCount | Partitions lacking an online leader per metric semantics |
| LeaderCount | Number of partitions led by this broker |

Example:

~~~text
10:00 Producer sends succeed
10:02 IsrShrinksPerSec rises
10:03 UnderReplicatedPartitions rises
10:04 Produce request latency rises
10:05 Application starts receiving NotEnoughReplicas
10:07 Replicas recover, ISR expands
10:08 Producer errors drop
~~~

This is a hypothetical timeline showing how broker metrics supply root-cause context for application exceptions.

### 11.1. min.insync.replicas and acks=all

With acks=all, brokers acknowledge only when ISR meets min ISR conditions. When ISR falls short, produces are rejected rather than acknowledged with weaker durability.

Never lower min.insync.replicas or weaken acks just to quiet error metrics without an approved durability tradeoff. Lower error rates do not automatically mean a safer system.

### 11.2. One down broker can impact many partitions

If one broker hosts many replicas or leads many partitions, a single node fault can spike errors across many topics simultaneously. Look for patterns by broker ID and partition leadership to distinguish a node hotspot from a topic with bad payloads.

## 12. Controller and consumer group logs

Some incidents live outside the Produce/Fetch data path in metadata or consumer group coordination.

### 12.1. Controller logs

During leader elections, broker registrations, topic partition changes, or controller failovers, controller logs are primary evidence.

Compare against:

- LeaderCount shifts.
- OfflinePartitionsCount.
- UnderReplicatedPartitions.
- Producer NotLeaderOrFollower/metadata errors.
- Consumer rebalance rates.

A brief leader election can trigger transient errors while clients refresh metadata; if prolonged, investigate controller stability and broker connectivity.

### 12.2. Group coordinator logs

When consumer logs report rebalances, heartbeat failures, or OffsetCommit errors, check group coordinator logs alongside:

- JoinGroup/SyncGroup/Heartbeat/OffsetCommit request metrics.
- Consumer group membership and generation changes.
- Client max.poll.interval.ms and session timeouts.
- Consumer processing duration and poll progress.
- Coordinator broker load/network health.

Do not mistake a normal deployment rebalance for a coordinator outage. Cross-check deployment events and membership changes in the same window.

### 12.3. Consumer lag is not a single broker log line

Lag is typically calculated as the gap between log end offset and committed offset (or tool-appropriate read position). Computing it requires both topic partition data and consumer group offsets.

Brokers do not emit a log saying “group X lag = 5000” for every group. Use exporters/AdminClient/group monitoring to compute lag and broker logs to explain coordination/replication changes.

## 13. Prometheus: example broker metric queries

Prometheus metric names depend on JMX exporter rules, Kafka exporters, or monitoring stacks. The examples below assume an exporter mapping JMX metrics to illustrative series names; **never copy queries without verifying your actual /metrics endpoint**.

### 13.1. Failed produce request rate

~~~promql
sum by (cluster, broker) (
  rate(kafka_server_broker_topic_metrics_failed_produce_requests_total[5m])
)
~~~

Shows failed produce request rate per broker. Adjust metric names or labels to match your exporter schema.

### 13.2. Produce request latency

If the exporter emits histograms:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cluster, broker) (
    rate(kafka_network_requestmetrics_totaltimems_bucket{
      request="Produce"
    }[5m])
  )
)
~~~

This is an example histogram query. Some JMX exporters expose gauges/summaries or precomputed quantiles rather than histogram buckets. You cannot apply histogram_quantile without bucket series.

### 13.3. Under-replicated partitions

~~~promql
max by (cluster) (
  kafka_server_replicamanager_under_replicated_partitions
)
~~~

Gauges are usually emitted per broker; cluster-wide aggregation must avoid double-counting partitions if multiple brokers report similar views. For some metrics `max` fits better than `sum`; verify scope before choosing an aggregation.

### 13.4. Request handler idle

~~~promql
avg by (cluster, broker) (
  kafka_server_kafkarequesthandlerpool_requesthandleravgidlepercent
)
~~~

Sustained low values indicate busy request handlers. Cross-check CPU, request queues, request latency, and broker workload; never treat a single generic threshold as proof of overload.

### 13.5. Comparing producer retries and broker errors

When client metrics are exported separately:

~~~promql
sum by (service, client_id) (
  rate(kafka_producer_record_retry_total[5m])
)
~~~

~~~promql
sum by (cluster, broker) (
  rate(kafka_server_broker_topic_metrics_failed_produce_requests_total[5m])
)
~~~

These two queries have different labels and scopes. They cannot be joined directly with an arbitrary PromQL join. Place them on dashboards sharing a time axis, then correlate client ID, broker, and topic via logs/metadata.

### 13.6. Avoid forcing ratios when the denominator is missing

If failed request count appears while total request count is 0 due to exporter restarts or missing metrics, ratios become undefined. Distinguish:

- Zero errors with active traffic.
- Zero traffic.
- Missing metrics.
- Unscrapeable broker/exporter.

Alerts should include telemetry availability and minimum traffic conditions.

## 14. From JMX to Prometheus: understanding labels and exporters

Kafka brokers normally expose JMX metrics. A JMX exporter maps MBean/object names into Prometheus metric names and labels.

Conceptual example:

~~~text
JMX:
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce

Prometheus exporter:
kafka_network_requestmetrics_totaltimems{request="Produce",broker="2",cluster="primary"}
~~~

This mapping is illustrative. Exporter rule files can rename metrics, drop dimensions, rescale units, or add labels. If rules drop request type or broker ID, correlation power drops.

### 14.1. Inspect the metrics endpoint before writing alerts

Workflow:

1. Open the metrics endpoint of the target broker/exporter.
2. Locate the original metric name or MBean pattern.
3. Check TYPE (counter, gauge, histogram/summary).
4. Inspect labels: cluster, broker, topic, request, client.
5. Check units and reset behavior across broker restarts.
6. Compare with Apache Kafka JMX documentation for your exact version.
7. Write the query and test on a populated time range.
8. Test query behavior when a broker is down or exporter is missing.

Do not assume a JMX metric containing “PerSec” is always a Prometheus counter. Exporters may expose it as a precomputed gauge/rate. Calling `rate()` on a rate gauge gives wrong results.

### 14.2. Counter, gauge, and rate

- **Counter**: monotonically increases until process restart; use rate/increase.
- **Gauge**: point-in-time value such as under-replicated partitions; do not use rate.
- **Histogram**: buckets/count/sum; use histogram_quantile when buckets exist.
- **Rate gauge**: already a per-second rate; do not wrap in rate again.

Verify TYPE before building queries.

## 15. Correlating a producer timeout incident

Scenario: a Spring service logs TimeoutException when sending to topic orders.created.

### Step 1 — Locate the application log

Collect timestamp, cluster, client ID, topic, exception category, and trace ID. If an earlier send callback succeeded, note broker/partition/offset; otherwise outcome may be uncertain.

### Step 2 — Check producer client metrics

Inspect:

- record-error-rate and record-retry-rate.
- request-latency-avg/max.
- record-queue-time.
- bufferpool-wait-time.
- produce-throttle-time.
- Connection count/metadata age.

If retries and queue time climbed before the timeout, the producer may have been stalled waiting on brokers or buffers.

### Step 3 — Identify the leader broker

Check topic metadata/partition leadership at the incident time. Identify the partition leader broker, the broker receiving ProduceRequest, and brokers involved in replication.

Do not inspect only the current leader if leadership shifted.

### Step 4 — Check broker metrics

On the involved brokers, compare:

- FailedProduceRequestsPerSec.
- Produce TotalTimeMs and its queue/local/remote components.
- RequestQueueSize.
- RequestHandlerAvgIdlePercent.
- NetworkProcessorAvgIdlePercent.
- UnderReplicatedPartitions and ISR changes.
- ThrottleTimeMs.

### Step 5 — Search broker logs

Filter by timestamp and broker ID, then by logger category/request errors. Check quotas, authorization, leaders, ISR, and networking.

### Step 6 — Draw an evidence-backed conclusion

Example conclusion:

“Producer retries climbed on client orders-producer-2; broker 3 showed elevated Produce request queue and throttle time in the same window; broker logs recorded quota throttling for the matching client identity. Evidence aligns with throttling, requiring quota/traffic tuning.”

If broker evidence is unavailable, never invent causes. Broker logs may lack detail due to log levels or metric scope; explicitly document unverified gaps.

## 16. Correlating consumer lag and fetch latency

Scenario: billing-service lag grows while the listener logs few exceptions.

Cross-check:

1. Consumer logs: rebalances, assigned partitions, pauses/resumes, poll loops, commit errors.
2. Consumer metrics: records-consumed-rate, fetch latency, fetch rate, commit latency, assigned partitions.
3. Broker metrics: Fetch request latency/failures, BytesOutPerSec, request queue/handler idle, network processor idle.
4. Broker logs: group coordinator, leader changes, fetch errors, broker networking issues.
5. Application metrics: listener processing duration, DB latency, worker queue depth.

### 16.1. High fetch latency and low listener duration

Brokers, replicas, or networks may be slowing fetches before records reach the listener. Inspect broker Fetch request metrics, network health, and leader/replica health.

### 16.2. Healthy fetches yet lag still climbs

The listener may be processing slowly, consumer concurrency may be low, batches too large, dependencies slow, or the consumer paused. Broker BytesOutPerSec may look normal while application records-consumed-rate stays low.

### 16.3. Continuous rebalancing

Inspect group coordinator logs, Heartbeat/JoinGroup/SyncGroup metrics, consumer max.poll.interval.ms, session timeouts, deployment events, and listener processing duration. Do not blame broker load for every rebalance.

## 17. Correlating ISR and under-replicated partitions

A broker can keep accepting requests while replication degrades. Producers with acks=all may then time out or receive NotEnoughReplicas.

Investigate:

- On which brokers did UnderReplicatedPartitions rise?
- Did UnderMinIsrPartitionCount rise?
- When did ISR shrink/expand events occur?
- Are replica fetchers/networks slow?
- Are disk latency or broker GC abnormal?
- Do broker logs show partition/replica state transitions?
- How are producer acks and min.insync.replicas configured?

### 17.1. Do not look only at cluster averages

A cluster can have mostly healthy brokers and one broker suffering a disk/network fault. Average CPU or average latency can hide that single node.

Inspect per-broker metrics and latency distributions. Compare leader partitions and replicas on the impacted node.

### 17.2. ISR recovery also needs observation

Once fixed, expanding ISRs and falling under-replicated counts signal recovery. Still verify producer failures and latency return to baseline too.

Do not close the incident solely because UnderReplicatedPartitions hit 0 if the application still hits timeouts or consumer backlog has not caught up.

## 18. Throttling and quotas: which broker metrics match client logs?

Quotas can apply by user, client ID, or other entities depending on Kafka config. Producers may observe rising send latency or throttle behavior while broker metrics record throttle time.

Cross-check:

- Actual client ID, principal, and quota entity.
- Producer produce-throttle-time.
- Broker RequestMetrics ThrottleTimeMs.
- Produce request latency.
- BytesInPerSec and request rates.
- Broker/authorizer/quota logs if available.
- Quota configs and recent changes.

One throttled client does not mean the whole cluster is overloaded. If only one client ID is impacted, investigate that client's quota and traffic profile.

### 18.1. Quotas can be expected behavior

When quotas protect the cluster, rising throttle time may reflect policy working as designed. The question is whether traffic should be constrained per SLO, not treating every throttle as a broker bug.

If raising quotas, evaluate aggregate capacity impact and fairness to peer clients.

## 19. Authorization and topic metadata errors

### 19.1. Authorization

Application logs may record TopicAuthorizationException or ClusterAuthorizationException. Cross-check broker authorizer logs by principal, topic/resource, and operation.

Verify producers hold WRITE/DESCRIBE permissions and consumers hold READ/DESCRIBE/GROUP permissions per security config. Never resolve this by granting broad permissions to all principals.

### 19.2. UnknownTopicOrPartition

If the application logs UnknownTopicOrPartitionException, check:

- Does the topic exist in the right cluster?
- Are producer/consumer pointing at the right bootstrap cluster?
- Is the partition count right?
- Is metadata cache stale?
- Was the topic recently deleted/recreated?
- Do controller logs show topic/partition state errors?

Broker throughput metrics can look healthy even when a topic is missing or partition mapping is wrong. This shows why aggregate metrics cannot replace broker/controller logs.

### 19.3. Metadata and leader changes

Producer/consumer metadata refreshes can emit transient errors during leadership transitions. Compare client metadata age, retries, broker LeaderCount, and controller logs. If errors spike briefly and recover, separate transient failover from sustained cluster instability.

## 20. Network and broker resource pressure

When many clients slow down together, look for broker/node signals:

| Signal | What to investigate |
|---|---|
| Low NetworkProcessorAvgIdlePercent | Network processors busy |
| Low RequestHandlerAvgIdlePercent | Request handlers busy |
| Rising RequestQueueSize | Request backlog |
| Rising ResponseQueueSize | Possible response processing/network bottleneck |
| Rising Produce/Fetch latency | Request path slow |
| High BytesIn/BytesOut | Traffic spike or network capacity |
| Rising broker CPU/GC | JVM resources |
| High disk latency | Log append/replication likely slow |
| Network retransmits/drops | Transport layer issue |
| Unusual connection count growth | Client churn/connection pressure |

No single metric proves node overload. Low network processor idle may reflect high yet healthy throughput within capacity; combine throughput, latency, and error rates.

### 20.1. Request queue rises while CPU stays low

The bottleneck may be request handler pools, locks, I/O, or network dependencies rather than CPU. Inspect broker thread dumps, disk, network, and request types.

### 20.2. High CPU while request latency stays normal

Traffic may have climbed while the broker still handles it cleanly. Never alert on CPU alone without checking latency, failed requests, queues, and replication.

## 21. Structured logging for brokers and applications

To make log searches effective, standardize fields on the application side and parse broker logs into structured fields when log formats allow.

Fields to retain:

- UTC timestamp.
- Cluster, environment, broker ID, hostname.
- Logger/category, severity, exception class.
- Request type or operation.
- Client ID/principal when present and permitted.
- Topic/partition when included in the log.
- Trace ID/span ID in application logs.
- Deployment/version/config revision.
- Message/request correlation ID when available.

Broker logs will not always carry event IDs or trace IDs since brokers do not decode business payloads or propagation headers by default. Do not expect Trace ID in broker logs unless broker logging is specifically instrumented to extract headers.

### 21.1. Log levels and volume

A debugging workflow should:

1. Target a specific broker.
2. Target the relevant logger category.
3. Raise the log level briefly if safely supported.
4. Capture the exact time window.
5. Restore the log level.
6. Assess disk/log ingestion impact.

Never enable cluster-wide DEBUG indefinitely. Broker logs can expose principals, topic names, network metadata, or sensitive operational info.

### 21.2. Log retention and sampling

Log pipelines can drop, sample, or delay logs. Metric scrapes can also miss samples during exporter/broker restarts. When evidence is absent, note telemetry limits rather than claiming an event never happened just because logs are missing.

## 22. Illustrative log queries

The examples below use generic search syntax; adapt for Elasticsearch, Loki, Splunk, or your organization's log system.

Find application producer timeouts:

~~~text
service="orders-service"
event="kafka_publish_failed"
exceptionClass="TimeoutException"
timestamp within incident window
~~~

Find broker Produce errors:

~~~text
cluster="kafka-primary"
brokerId=2
logger contains "KafkaApis" or "ReplicaManager"
timestamp within incident window
~~~

Find ISR changes:

~~~text
cluster="kafka-primary"
logger contains "ReplicaManager" or "Partition"
message contains "ISR" or "replica"
timestamp within incident window
~~~

Find consumer group coordination:

~~~text
cluster="kafka-primary"
logger contains "GroupCoordinator"
message contains group ID or generation
timestamp within incident window
~~~

These queries are pseudo-queries, not verbatim syntax for every log platform. Standardize parsers and field names in your real environment.

## 23. Using traces for extra correlation

Distributed tracing links application spans between producers and consumers via Kafka headers. Trace IDs help locate:

- The HTTP request creating the event.
- The producer send span.
- The consumer receive/listener span.
- Database or HTTP dependency spans.
- Retry/DLT operations when instrumented.

However, broker metrics/logs normally lack Trace IDs by default. Thus traces cannot replace broker telemetry. Use traces to understand **one business execution**, and broker metrics to understand **cluster behavior**.

Never use Trace ID as a business event ID. A record can be replayed under a fresh trace; business event ID is the right key for deduplication/reconciliation.

## 24. Common correlation mistakes

**Wrong timezone.** Application logs are UTC while dashboards show local time or vice versa. Standardize on UTC and verify clock sync.

**Inspecting only the current partition leader.** Leadership may have moved during the incident. Obtain historical controller/metadata evidence.

**Comparing broker-wide metrics directly against one client log.** Broker metrics aggregate across clients/topics; match scope and dimensions.

**Treating one ProduceRequest as one record.** Producer batching packs multiple records/partitions together.

**Searching broker logs for an event ID and concluding no record arrived.** Brokers do not log every successful record by default.

**Calling rate() on a gauge.** Verify metric TYPE and exporter mapping before writing PromQL.

**Assuming JMX PerSec is always a counter.** Some metrics are already rate gauges; applying rate again distorts values.

**Merging Produce and Fetch latencies.** They are distinct request paths impacting producers and consumers separately.

**Blaming the broker for all consumer lag.** Lag can stem from listeners, databases, pauses, low concurrency, or ingress spikes.

**Ignoring retries.** Clients may retry successfully before the app sees a final failure; retry rate is an early warning.

**Ignoring queue/local/remote/throttle breakdowns.** Looking only at TotalTimeMs hides the real bottleneck.

**Treating missing metric samples as zero.** Down exporters or restarting brokers leave gaps; alerts need telemetry availability checks.

**Enabling cluster-wide DEBUG.** Can spike log volume, disk pressure, and expose metadata.

**Using unbounded dynamic client IDs as metric labels.** High cardinality strains monitoring backends.

**Omitting deployment context.** A rollout can trigger rebalances/connection churn right when metrics shift.

**Equating correlation with causation.** Two metrics moving together do not prove one caused the other; verify with logs/error details and test hypotheses.

## 25. Runbook: correlating logs with broker metrics during an incident

### Phase A — Identify the symptom

1. Classify symptom: producer send error, consumer fetch/lag, offset commit, transaction abort, or DLT failure.
2. Gather application logs and pick the earliest failure timestamp.
3. Identify environment, cluster, service, client ID/group, topic, and partition.
4. Assess severity and blast radius: one client, one broker, one topic, or multiple clusters.

### Phase B — Build the timeline

1. Normalize timestamps to UTC.
2. Select a time window covering before/during/after the incident.
3. Align application logs, client metrics, broker metrics, and broker logs on the same timeline.
4. Account for scrape intervals, aggregation windows, and missing samples.
5. Identify which metric shifted before the application exception.

### Phase C — Isolate broker/request

1. Identify the leader/receiver broker at the incident time.
2. Select the matching request type: Produce, Fetch, OffsetCommit, Metadata, or group coordination.
3. Inspect request queue, local, remote, response queue, total, and throttle times.
4. Inspect FailedProduce/FailedFetch, replication, ISR, and offline partitions.
5. Search broker/controller/group coordinator logs around the same time.
6. Compare per-broker signals against cluster-wide signals.

### Phase D — Conclude and act

1. Document evidence supporting the hypothesis.
2. Document missing or unverified data.
3. Act on root cause: ACLs, quotas, topics, broker resources, replication, networking, or application backpressure.
4. Never weaken durability or skip offsets just to turn metrics green.
5. Monitor metrics/logs after remediation.
6. Confirm application errors, consumer lag, and business outcomes recover together.

### 25.1. Incident record template

~~~text
Incident:
  Start time (UTC):
  Environment / Kafka cluster:
  Affected service / client ID / consumer group:
  Topic / partition:
  Broker(s) involved:
  Application symptom:
  Client metric evidence:
  Broker metric evidence:
  Broker log evidence:
  Controller/group coordinator evidence:
  Root cause confidence:
  Action taken:
  Recovery evidence:
  Remaining uncertainty:
~~~

This template separates observed facts from hypotheses. If broker logs lacked detail or metrics lacked client/topic dimensions, document those limits clearly.

## 26. Testing and verifying correlation capability

You do not need an integration test for every broker metric in every service, yet you should validate telemetry pipelines and runbooks in a test/staging Kafka environment with broker metrics/logs.

### 26.1. Baseline produce/consume

1. Send a known batch of records to a test topic.
2. Capture application send logs and producer outcomes.
3. Verify broker MessagesIn/BytesIn and Produce request metrics respond.
4. Consume records and verify client fetch/records-consumed metrics.
5. Compare log timeline against broker metrics in the same window.
6. Verify you do not deduce exact record counts from request counts when batching is on.

### 26.2. Controlled produce failure

Use a test principal lacking write ACLs or misconfigured topic/partition in an isolated cluster.

Verify:

- Application logs capture the right exception/category.
- Producer client error/retry metrics reflect the behavior.
- Broker authorization/request logs show evidence if logging is configured to emit it.
- Do not expect broker MessagesIn to rise for records rejected before append.
- After fixing ACL/topic, send outcomes recover.

### 26.3. Broker throttling

In a quota-enabled test environment, generate controlled traffic above quota.

Verify:

- Producer throttle time increases.
- Broker ThrottleTimeMs or quota metrics respond if present.
- Send latency rises accordingly.
- Broker-wide CPU may stay low.
- When traffic drops or quota adjusts legitimately, latency/throttle recover.

### 26.4. Replication degradation

In a multi-broker test cluster, induce a controlled replica unavailability.

Verify:

- ISR shrink/under-replicated metrics change.
- Broker/replica logs capture state transitions.
- Producer acks=all sees matching errors when min ISR is not met.
- After replica recovery, ISR expands and producer outcomes normalize.

Never test replica loss or weaken durability in production just to verify dashboards.

### 26.5. Consumer lag and rebalance

Induce a slow listener or pause consumers in a controlled test.

Verify:

- Application logs show processing latency/rebalance context.
- Consumer lag rises.
- Fetch/OffsetCommit/group coordinator metrics/logs reflect the condition.
- Broker Fetch path may stay healthy even when the listener is slow.
- After recovery, lag catches up and offsets advance.

### 26.6. Exporter/telemetry failure

Stop the JMX exporter or sever collector connectivity in a test environment.

Verify:

- Dashboards indicate missing telemetry instead of falsely showing zero.
- Alerts fire on exporter/broker scrape failures.
- Application Kafka processing continues unaffected by monitoring pipeline outages.
- Log retention/collection recovers if required.

## 27. Designing a correlation dashboard

A strong dashboard aligns rows along a shared time axis:

### Row 1 — Application

- Producer logical send errors/successes.
- Listener errors and processing duration.
- Retry/DLT recovery outcomes.
- Offset commit failures.
- Business event completion latency.

### Row 2 — Kafka clients

- Producer record error/retry/send rates.
- Producer request latency and queue time.
- Consumer fetch latency/records-consumed-rate.
- Consumer commit latency.
- Assigned partitions and rebalance activity.

### Row 3 — Broker requests

- Produce/Fetch request rates and failures.
- Request queue/local/remote/response/total times.
- Throttle time.
- Request queue size and handler/network idle.

### Row 4 — Replication/controller

- Under-replicated partitions.
- Under-min-ISR count.
- ISR shrink/expand rates.
- Offline partitions and leader counts.
- Controller changes/availability.

### Row 5 — Infrastructure

- Broker CPU, heap, GC.
- Disk latency/space.
- Network throughput/retransmits.
- JVM threads/connections.
- Exporter scrape health.

All panels must share cluster/environment filters and timezone. Document drilldowns from application logs to client ID, topic/partition, broker ID, and broker logs.

## 28. Alerting: alerting on combined signals

A producer timeout alert is far sharper when combining:

- Rising application send failures.
- Rising producer retry rate or request latency.
- Rising broker Produce failures/queues/throttles.
- Healthy metric exporter.

A replication alert should combine:

- Sustained rise in UnderReplicatedPartitions.
- ISR shrink activity.
- Rising producer errors or ack latency.
- Offline partitions/under-min-ISR when present.

A consumer lag alert should combine:

- Continuously growing lag.
- Records-consumed-rate trailing input rate.
- Listener processing latency or poll gaps.
- Fetch path and group coordinator health.

Do not apply one global threshold across all topics. Critical, DLT, and audit streams may need tailored SLOs/alerts.

### 28.1. Alerting on missing telemetry

If a broker exporter goes down, FailedProduceRequests data vanishes. An alert watching only that metric will not fire because the series disappears.

Add separate alerts for target scrape failures, missing expected brokers, or stale samples. **No metric does not mean the metric equals 0.**

### 28.2. Alerts should not rely solely on log counts

Log sampling, rate limiting, and logger levels change log volume without faithfully reflecting failure counts. Use well-defined metrics for rates/ratios, and logs to explain individual events.

## 29. Inherent limits of correlation

Some gaps cannot be eliminated completely:

1. **Aggregation:** broker metrics combine many clients/records/requests.
2. **Batching:** one request can contain many records.
3. **Retries:** one logical send can spawn multiple requests.
4. **Sampling:** logs/traces may be sampled or dropped.
5. **Scrape interval:** metric scrapes may not align with exact log timestamps.
6. **Clock skew:** timestamps across apps, brokers, and monitoring can drift.
7. **Leadership changes:** the handling broker can shift mid-incident.
8. **Version differences:** Kafka JMX names, labels, and request metric semantics evolve.
9. **Exporter mapping:** JMX-to-Prometheus rules can rename/rescale or drop dimensions.
10. **Broker log policy:** brokers do not log per-record successes by default.
11. **Client-side errors:** serialization or local buffer failures happen before brokers ever see a request.
12. **Outcome uncertainty:** client timeouts do not always prove the broker failed to append the record.

When logs and metrics diverge, do not force them to match numerically. Check whether they measure the same operation, request type, broker, time window, and semantics.

## 30. Code review and operations checklist

Before deploying a Kafka service to production, verify:

1. Application logs record UTC timestamps, service, cluster, and operation.
2. Producer logs include client ID/topic/event correlation where possible.
3. Consumer logs include group/topic/partition/offset.
4. Exceptions are classified by type/category rather than message text alone.
5. Kafka client metrics are collected for producers/consumers.
6. Broker JMX metrics are exported from all required brokers and controllers.
7. Broker logs have retention, parsing, and access controls.
8. Metric labels include appropriate cluster/broker/request/topic dimensions.
9. Metric TYPEs and units are verified before writing PromQL.
10. Dashboards separate Produce, Fetch, OffsetCommit, and group coordination.
11. Request queue/local/remote/throttle breakdowns are inspected when latency climbs.
12. Replication/ISR/offline partition metrics have alerts.
13. Time sync and scrape intervals are well understood.
14. Historical leader changes can be queried across incident windows.
15. Never assume broker logs emit one line per successful record.
16. Never substitute Trace ID for business event ID.
17. Exporter failures alert separately from zero traffic/errors.
18. Runbooks link application logs → client metrics → broker metrics/logs.
19. Integration/staging tests verified produce failure, quota, replication, and consumer lag patterns.
20. Incident conclusions clearly separate evidence, hypotheses, and unverified items.

## 31. Version-specific reference documentation

When building dashboards and runbooks, consult documentation matching your exact Kafka version, broker distribution, and exporter:

- **Apache Kafka Monitoring documentation**: broker, producer, consumer, and request metrics.
- **Apache Kafka JMX MBean reference**: BrokerTopicMetrics, RequestMetrics, ReplicaManager, controller, and network metrics.
- **Apache Kafka Broker Configs**: replication, min ISR, request handlers, quotas, and logging.
- **Apache Kafka Producer Configs**: acks, retries, delivery timeout, request timeout, and client ID.
- **Apache Kafka Consumer Configs**: max poll interval, session timeout, fetch, and group settings.
- **Spring for Apache Kafka Reference — Logging / Monitoring**: listener containers, KafkaTemplate, Micrometer, and application events.
- **Spring Kafka Javadoc — KafkaTemplate / listener containers**: send results, consumer metadata, lifecycle, and error handling.
- **Micrometer Documentation**: Kafka client metrics, meters, counters, gauges, timers, and cardinality.
- **Prometheus Documentation**: scrape health, rate/increase, histogram queries, and alerting.
- **Kafka JMX Exporter documentation**: mapping MBeans into Prometheus metrics and labels.

Metric names, JMX object names, logger categories, request breakdowns, and units can change across Kafka versions/distributions. Prometheus metric names also depend on exporter rules. Before putting a query or alert into production, verify live series on your metrics endpoint and compare with your running dependency's Javadoc/MBean reference.

**Conclusion:** correlating logs with broker metrics is the practice of joining **a specific application symptom** with **aggregated client and broker signals** on the same cluster, broker, request type, and timeline. Application logs tell operations and exceptions; Kafka client metrics reveal retry/send/fetch behavior; broker metrics reveal request queues, latency, throttling, and replication; broker logs explain server-side events. Keeping each source's scope and semantics clear lets operations pinpoint root causes without jumping to false conclusions from a single metric or isolated log line.
