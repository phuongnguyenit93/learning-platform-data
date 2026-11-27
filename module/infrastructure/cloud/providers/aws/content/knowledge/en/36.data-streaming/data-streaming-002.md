# Kinesis Data Streams, Shards, and Partition Keys

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, Amazon Kinesis Data Streams (KDS) is a service for ingesting and distributing streaming data in real time. Producer applications write data records into a stream; Kinesis distributes records across shards; consumers read and process data as needed. Shard and partition key design largely determines the scalability, load balance, and processing order of a stream.

A partition key is not merely a required field in a write call. It is an architectural decision: records with the same key are mapped to the same shard, enabling in-order processing within the shard and maintaining state per entity such as a customer, device, or order. If you choose a highly concentrated key, a single shard can become overloaded even when the overall stream has plenty of capacity. If you choose a key that is too dispersed, the application can lose required locality and ordering.

After this lesson, learners will be able to:

- Explain the relationship between stream, data record, shard, hash key range, and sequence number.
- Describe how Kinesis uses MD5 to map a partition key to a shard.
- Choose a partition key based on cardinality, load distribution, business ordering, and consumer model.
- Estimate initial provisioned shard counts from write throughput, record rate, and read throughput.
- Distinguish between Provisioned, On-demand Standard, and On-demand Advantage.
- Identify hot shards, hot partition keys, and data skew.
- Explain split, merge, UpdateShardCount, and the impact of resharding on consumers.
- Choose shared-throughput consumers, Enhanced Fan-Out, KCL, or Lambda event source mapping.
- Use the AWS CLI and AWS SDK for Java to create streams, write records, and inspect shards.
- Monitor throughput, throttling, iterator age, and consumer lag to operate a stream reliably.

## 1. Kinesis Data Streams in Streaming Architectures

Kinesis Data Streams ingests, temporarily stores, and delivers records to one or more consumers. Data typically comes from web applications, IoT devices, log agents, clickstreams, CDC pipelines, or transaction systems. Consumers can compute aggregates, detect anomalies, update databases, forward data to analytics platforms, or trigger workflows.

A general flow:

~~~mermaid
flowchart LR
    P1[Web and mobile producers] --> S[Kinesis Data Stream]
    P2[IoT devices and services] --> S
    P3[Logs and CDC producers] --> S
    S --> H1[Shard 1]
    S --> H2[Shard 2]
    S --> H3[Shard 3]
    H1 --> C1[Consumer application A]
    H2 --> C1
    H3 --> C1
    H1 --> C2[Consumer application B]
    H2 --> C2
    H3 --> C2
    C1 --> D1[DynamoDB or OpenSearch]
    C2 --> D2[S3 or analytics]
~~~

Key components:

| Component | Role |
|---|---|
| Producer | Sends data records into the stream using APIs, SDKs, Kinesis Producer Library, or AWS integrations |
| Data stream | A collection of shards acting as the boundary for storing and distributing records |
| Data record | An immutable unit of data consisting of a sequence number, partition key, and payload |
| Shard | An ordered sequence of records and the fundamental unit of capacity |
| Partition key | Value used to map a record to a shard |
| Hash key range | Range of hash values that a shard is responsible for |
| Sequence number | Record position assigned by Kinesis within a shard |
| Consumer | Reads records and processes them according to application logic |

Kinesis does not interpret payload contents. The payload is an immutable sequence of bytes; producer and consumer applications must agree on schema, encoding, versioning, and data processing semantics.

Kinesis Data Streams differs from Amazon Data Firehose. Data Streams provides streams and shards so applications control consumers, ordering, replay within the retention window, and processing topology. Firehose is a managed delivery service for transferring data to supported destinations with less consumer code. The two services can complement each other in the same pipeline.

## 2. Data Records, Streams, and Shards

A stream consists of one or more shards. Each shard holds a sequence of records and provides a unit of throughput. In Provisioned mode, total stream capacity is the sum of the capacities of the provisioned shards. In On-demand mode, Kinesis manages the number of shards according to demand and the stream's capacity mode.

A data record has three logical components:

- Sequence number: assigned by Kinesis after a successful write.
- Partition key: determines how the record is distributed.
- Data blob: byte payload provided by the application.

Illustration of a stream with three shards:

| Shard | Hash key range | Sample sequence numbers |
|---|---|---|
| Shard 1 | Range A | 101, 102, 103 |
| Shard 2 | Range B | 201, 202, 203 |
| Shard 3 | Range C | 301, 302, 303 |

Sequence numbers across different shards are independent; you cannot compare 103 against 201 to infer stream-wide order.

Each shard in Kinesis Data Streams has baseline throughput limits:

| Direction | Per-shard limit | Meaning |
|---|---|---|
| Write | 1 MB/second or 1,000 records/second, whichever limit is reached first | Producers must distribute load across multiple shards |
| Read via GetRecords | Total 2 MB/second and up to 5 read transactions/second | Shared-throughput consumers share the read capacity |

These limits apply to shards in both Provisioned and On-demand capacity modes. When records are large, bytes may hit the limit before record count; when records are small, the records/second limit may be hit first.

The default maximum record size is 1 MiB. A stream can be configured to support large records up to 10 MiB in supported cases; the record size limit includes both the partition key and the data payload. Support for large records does not increase a shard's baseline write throughput limit. Consider compressing, splitting payloads, or storing large content in S3 and sending only a reference in the stream.

## 3. Partition Keys and Mapping to Shards

With the default distribution strategy USER_PARTITION_KEY, the producer provides a partition key for each record. Kinesis uses an MD5 hash function to convert the partition key into a 128-bit integer. The service then finds the shard whose hash key range contains that value.

~~~mermaid
flowchart TD
    A[Data record] --> B[Partition key]
    B --> C[MD5 hash 128-bit]
    C --> D{Which range contains the hash key?}
    D -->|Range A| E[Shard 1]
    D -->|Range B| F[Shard 2]
    D -->|Range C| G[Shard 3]
~~~

Important rules:

- The partition key is a Unicode string up to 256 characters long.
- Each shard is responsible for a contiguous hash key range within the hash space.
- Records with the same partition key produce the same MD5 hash value and map to the same shard under the current shard map.
- Different partition keys can land on the same shard if their hashes fall into the same range.
- A partition key is not a shard name and does not directly specify a shard ID.
- You can use ExplicitHashKey to override the hash value generated from the partition key and choose a specific hash position, but you must understand the impact on distribution and ordering.

Example:

| Record | Partition key | Mapping result |
|---|---|---|
| Event A | customer-101 | Shard 1 |
| Event B | customer-202 | Shard 2 |
| Event C | customer-101 | Shard 1 |
| Event D | customer-303 | Shard 3 |

This table is illustrative only. Actual shard placement depends on the stream's current hash key ranges. You cannot deduce the shard from the key name by sight or assume customer-101 always stays on shard 1 after the stream is resharded.

A partition key serves two intertwined roles: distributing load and grouping related records into the same shard. Key design must balance both goals.

## 4. Sequence Numbers and Ordering Scope

Kinesis assigns a sequence number to each successfully written record. The sequence number represents the record's position within the shard and increases over time within that shard; it is not a stream-wide sequence number and should not be used as a business key.

Ordering must be understood accurately:

- Records within the same shard are read in shard order.
- With USER_PARTITION_KEY, records with the same partition key are routed to the same shard, allowing them to be processed in shard order for that entity.
- There is no overall ordering across different shards.
- A sequence number from one shard cannot be directly compared to a sequence number from another shard.
- PutRecords processes each record in a batch independently; the API does not guarantee record order matching the input array order.
- PutRecord has a SequenceNumberForOrdering parameter to enforce strictly increasing sequence numbers for sequential writes from the same client to the same partition key when passing the previous sequence number.

If business logic requires ordering by order ID, device ID, or account ID, use that entity as the partition key or construct a key that keeps the same record group together. If business logic requires global ordering, a multi-shard Kinesis stream does not natively provide a total order; you need a separate sequential pipeline or appropriate coordination mechanism.

Producer retries can also create duplicates. For example, PutRecord is received by Kinesis, but the ACK is lost on the return path. The producer does not know whether the record was written and retries; both attempts can create two records with different sequence numbers. Include a stable event ID or business ID in the payload so consumers can deduplicate.

## 5. Choosing a Partition Key by Business Domain

A good partition key must satisfy three criteria:

1. Have sufficient cardinality to distribute records across multiple shards.
2. Keep records that must be processed in order in the same group.
3. Distribute load relatively evenly across both record count and payload size.

Key selection examples:

| Workload | Typically suitable key | Reason |
|---|---|---|
| Clickstream | sessionId or visitorId | Groups behavior within the same session |
| IoT telemetry | deviceId | Preserves the data sequence per device |
| Orders | orderId | Processes events of an order in sequence |
| Account balances | accountId | Groups transactions for the same account to enforce ordering |
| Multi-tenant logs | tenantId combined with sourceId | Avoids funneling all data into a single tenant key |
| Geospatial data | geohash or cellId | Groups data by spatial region when required by business logic |

No single key works for every workload. For instance, tenantId may be reasonable when there are thousands of relatively uniform tenants, but it causes a hot key if one large tenant generates most of the traffic. Similarly, keying by country has only a few distinct values and easily concentrates load on a handful of shards.

### 5.1. Cardinality and Distribution

Cardinality is the number of distinct key values in the dataset. If a stream has 16 shards but only 3 partition keys, at most a few shards can receive traffic. Conversely, millions of keys can help spread load more evenly, yet if most traffic concentrates on a few keys, hot shards will still occur.

Analyze distribution by:

- Records per key over a time window.
- Total bytes per key, not just record count.
- Share of the largest key relative to total traffic.
- Distribution stability by hour, day, seasonality, and campaigns.
- Impact of a sudden spike from a single tenant, device, or account.

You can sample traffic at the producer, compute top-N keys by record count and bytes, and compare against shard-level IncomingBytes and IncomingRecords.

### 5.2. Composite Partition Keys

If a single field has low cardinality or one tenant carries heavy load, you can combine multiple fields:

- tenantId#deviceId
- tenantId#sessionId
- region#customerId
- accountId#eventCategory

A composite key increases the number of distinct keys and can reduce skew. However, it also splits events of the same entity across multiple keys if the added component varies. Only add fields when the ordering grouping required by the application is preserved.

For example, accountId#eventType puts deposits and withdrawals for the same account onto different keys. If all transactions for an account must be processed in order, this key is unsuitable.

## 6. Hot Shards, Hot Partition Keys, and Data Skew

A hot shard occurs when one shard receives a higher load than the remaining shards. Possible causes include:

- One partition key accounts for a large share of traffic.
- Low key count or uneven key distribution.
- Certain keys have significantly larger payloads.
- Producers send bursts to the same group of keys.
- Provisioned shard count is insufficient for the workload.
- A specific key spikes over a short period.

For example, a stream has 8 shards and total write throughput is 4 MB/s. If traffic is evenly distributed, each shard receives about 0.5 MB/s. But if 40% of traffic comes from a single customerId, the shard holding that key may receive over 1.6 MB/s and get throttled even though total stream throughput is well below total capacity.

Distinguish between:

| Issue | Symptoms | Remediation |
|---|---|---|
| Insufficient total shard capacity | Many shards are near their limits | Increase shard count or switch to On-demand |
| Hot shard due to skew | A few shards are noticeably higher | Analyze keys and hash ranges; redesign keys |
| Single hot partition key | One key exceeds shard limits | Bucket/salt the key if ordering changes are acceptable; consider AUTO for stateless workloads |
| Consumer bottleneck | Iterator age rises even without write throttling | Increase consumer capacity, optimize processing, or use EFO |
| Read contention | Multiple consumers share 2 MB/s/shard | Use Enhanced Fan-Out for consumers needing dedicated throughput |

### 6.1. Does Splitting a Shard Solve a Hot Key?

Splitting a shard divides a shard's hash key range into two smaller ranges. It can relieve load if many different partition keys are distributed across that range. However, if a single partition key generates most of the traffic, all records for that key still have the same hash and will land in one child shard after the split. Therefore, splitting does not automatically distribute a single hot key across multiple shards.

To split the load of a hot entity, you can append a bucket or suffix:

~~~text
customer-101#bucket-0
customer-101#bucket-1
customer-101#bucket-2
customer-101#bucket-3
~~~

Producers distribute records across the buckets. This increases parallelism but breaks strict ordering per customer-101. Consumers must reassemble order using a business sequence, version, reliable timestamp, or merge rule. If you cannot handle ordering after bucketing, do not use this approach for data requiring strict sequentiality.

### 6.2. ExplicitHashKey and Service-Managed Distribution

ExplicitHashKey lets the producer specify a hash value instead of the hash generated from the partition key. It can be used to control record placement or distribute multiple buckets of the same entity. However, when the same logical key is written to different hash ranges, records no longer land on the same shard and no longer preserve key-based ordering.

Kinesis also supports the service-managed record distribution strategy AUTO. In this mode, the service automatically distributes records across shards; the partition key and ExplicitHashKey passed by the producer are ignored. This fits stateless workloads where records can be processed independently and partition-key ordering is not needed. The default strategy USER_PARTITION_KEY fits when you need control over record grouping and per-key ordering.

Do not switch to AUTO merely to avoid a hot key if consumers depend on ordering. Re-verify producer APIs and application behavior before changing the distribution strategy.

## 7. Calculating Shard Count in Provisioned Mode

In Provisioned capacity mode, operators specify the number of shards. You must calculate throughput by both bytes and records, because a shard has two independent write limits.

For an initial estimate:

\[
N_{write} =
\max\left(
\left\lceil \frac{W_{MB/s}}{1} \right\rceil,
\left\lceil \frac{W_{records/s}}{1000} \right\rceil
\right)
\]

If shared-throughput consumers read a total of R MB/s:

\[
N_{read} = \left\lceil \frac{R_{MB/s}}{2} \right\rceil
\]

Initial shard count:

\[
N = \max(N_{write}, N_{read})
\]

Then add headroom for peaks, bursts, skew, and growth. This is an initial capacity estimate; validate it with load testing and shard-level metrics.

### 7.1. Sizing Example

Suppose a system has:

- Peak average write throughput: 6 MB/s.
- Write rate: 4,500 records/s.
- Total read throughput across shared consumers: 3 MB/s.

Calculation:

- By write bytes: ceil(6 / 1) = 6 shards.
- By record count: ceil(4,500 / 1,000) = 5 shards.
- By read throughput: ceil(3 / 2) = 2 shards.

Thus, at least 6 shards are needed based on theoretical capacity. With 30% headroom, choose around 8 shards and test actual distribution.

If three shared consumers all read the full stream, do not multiply 2 MB/s per consumer. They share the total 2 MB/s read throughput per shard. If each consumer needs dedicated throughput and low latency, evaluate Enhanced Fan-Out.

### 7.2. Why Not Use Total MB/s Alone?

Two workloads with the same total bytes but different record sizes can require different shard counts. For example:

- 500 records/s at 2 KB each: roughly 1 MB/s, hitting the byte limit first.
- 1,500 records/s at 200 bytes each: roughly 0.3 MB/s, hitting the 1,000 records/s limit first.

Therefore, you must account for both IncomingBytes and IncomingRecords. Also consider short bursts, key skew, and consumer read throughput.

## 8. Capacity Modes: Provisioned, On-demand Standard, and On-demand Advantage

Kinesis Data Streams offers three capacity mode options:

| Mode | Capacity management | When it fits |
|---|---|---|
| Provisioned | Operator specifies shard count and adjusts as needed | Predictable traffic, need control over shards/hash ranges |
| On-demand Standard | Kinesis automatically manages shard count based on actual throughput | Variable or unpredictable traffic |
| On-demand Advantage | Account-level option for On-demand with warm throughput and a distinct pricing structure | Large steady On-demand workloads or needing pre-warmed capacity ahead of peaks |

### 8.1. Provisioned

Provisioned fits when traffic is predictable and precise shard count control is needed. Operators can use UpdateShardCount to uniformly scale the shard count up or down, or SplitShard/MergeShards to adjust a specific hash range. Adjustments require monitoring because the shard map and consumer topology change.

### 8.2. On-demand Standard

On-demand Standard removes the need to specify a shard count. The stream automatically scales capacity with usage. Per current AWS documentation, a stream can accommodate up to double the peak write throughput observed over the previous 30 days. If traffic exceeds twice the prior peak within a 15-minute window, throttling may occur while the service scales; producers should retry with backoff.

On-demand automatically splits shards when it detects increasing load, but it does not always isolate a single skewed partition key. A single key can still exceed a shard's limit. If a workload has severe hot keys and requires targeted hash-range splits, Provisioned mode may be more suitable.

### 8.3. On-demand Advantage

On-demand Advantage is an account-level setting within a Region, applied to On-demand streams. This mode adds proactive warm throughput capability, a simpler pricing structure, and higher registered consumer limits in supported Regions. Before enabling it, check minimum usage commitments, pricing, Region support, and actual account usage. Do not choose it solely because a stream experiences a single short burst.

## 9. Resharding: Split, Merge, and Changing Shard Count

Resharding changes the number of shards to adjust capacity and parallelism. In Provisioned mode, there are three important operations:

- **SplitShard:** splits one shard into two child shards at a hash key boundary.
- **MergeShards:** merges two adjacent shards into one shard.
- **UpdateShardCount:** adjusts the shard count using uniform scaling.

During a split, the parent's hash key range is divided into two contiguous ranges. New records are mapped according to the new shard map. During a merge, two adjacent ranges are combined into one new range.

~~~mermaid
flowchart TD
    P[Parent shard: range 0-999] --> C1[Child shard A: range 0-499]
    P --> C2[Child shard B: range 500-999]
    C1 --> N1[Consumer processes child A]
    C2 --> N2[Consumer processes child B]
~~~

Important notes:

- SplitShard and MergeShards are asynchronous operations; the stream transitions to UPDATING and then back to ACTIVE.
- Old shards do not immediately vanish from history; they retain lineage to child shards.
- Records already written to the parent remain on the parent; new records matching the new hash ranges go to the children.
- Consumers must respect parent-child lineage so they do not skip records or process them out of order.
- KCL tracks shard leases and checkpoints in DynamoDB, automatically discovering new shards and distributing processors.
- Custom consumers built on GetRecords must track parent shards, child shards, and checkpoints during resharding.

### 9.1. Choosing the Right Operation

| Situation | Action |
|---|---|
| Whole stream grows steadily | UpdateShardCount to increase shard count |
| A specific hash range is hot due to multiple keys | Targeted SplitShard |
| Two adjacent shards have low load | MergeShards |
| On-demand stream sees overall load growth | Let Kinesis manage capacity, monitor throttling |
| A single partition key is hot | Revisit key design; a simple split may not solve it |

Resharding changes the shard map, not payloads already written. Nor does it automatically increase consumer processing capacity if worker count, database connections, or downstream services remain the bottleneck.

## 10. Producers: Writing Records to a Stream

Producers can write individual records with PutRecord or batches with PutRecords.

| API | Characteristics | Notes |
|---|---|---|
| PutRecord | Sends a single record and returns shard ID and sequence number | Can use SequenceNumberForOrdering for sequential writes on the same key |
| PutRecords | Sends up to 500 records in one request | Can partially succeed; must inspect each response record |
| Kinesis Producer Library (KPL) | Supports batching, aggregation, and retries | Reduces API calls; consumers must deaggregate user records, using KCL or a compatible utility |

PutRecords does not guarantee ordering matching the order of records in the request. Some records may succeed while others fail. Producers must check FailedRecordCount and retry only the failed records rather than resending the entire batch unnecessarily. Retries can create duplicates if an earlier write actually succeeded but the ACK was lost; payloads should include a stable event ID.

### 10.1. Writing Records with the AWS CLI

Create a Provisioned stream with four shards:

~~~bash
aws kinesis create-stream \
  --stream-name orders-events \
  --shard-count 4 \
  --region ap-southeast-1
~~~

Create an On-demand Standard stream:

~~~bash
aws kinesis create-stream \
  --stream-name telemetry-events \
  --stream-mode-details StreamMode=ON_DEMAND \
  --region ap-southeast-1
~~~

Check status and capacity mode:

~~~bash
aws kinesis describe-stream-summary \
  --stream-name orders-events \
  --region ap-southeast-1
~~~

List shards:

~~~bash
aws kinesis list-shards \
  --stream-name orders-events \
  --region ap-southeast-1
~~~

Write a record using customer ID as the partition key:

~~~bash
aws kinesis put-record \
  --stream-name orders-events \
  --partition-key customer-101 \
  --data fileb://order-event.json \
  --region ap-southeast-1
~~~

In order-event.json, the payload can contain eventId, orderId, customerId, eventType, eventVersion, and occurredAt. Use a stable event ID so consumers can deduplicate when producers retry.

### 10.2. Writing Records with the AWS SDK for Java 2.x

Java producer example using customerId as the partition key:

~~~java
import java.util.UUID;

import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.kinesis.KinesisClient;
import software.amazon.awssdk.services.kinesis.model.PutRecordRequest;
import software.amazon.awssdk.services.kinesis.model.PutRecordResponse;

public class OrderEventProducer {
    public static void main(String[] args) {
        String streamName = "orders-events";
        String customerId = "customer-101";
        String eventId = UUID.randomUUID().toString();

        String payload = """
            {
              "eventId": "%s",
              "eventType": "OrderPlaced",
              "orderId": "order-1001",
              "customerId": "%s",
              "eventVersion": 1
            }
            """.formatted(eventId, customerId);

        try (KinesisClient kinesis = KinesisClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            PutRecordRequest request = PutRecordRequest.builder()
                    .streamName(streamName)
                    .partitionKey(customerId)
                    .data(SdkBytes.fromUtf8String(payload))
                    .build();

            PutRecordResponse response = kinesis.putRecord(request);

            System.out.println("Shard: " + response.shardId());
            System.out.println("Sequence: " + response.sequenceNumber());
        }
    }
}
~~~

In production applications, do not generate a new event ID when retrying the same business operation. Generate the ID at the business boundary and preserve it across all retries. Add a retry policy with exponential backoff and jitter for throttling or transient errors; log shard ID, sequence number, and event ID for investigation.

## 11. Consumers and Data Reading Models

Consumers can read shards directly or use queue consumers in supported scenarios. With stream consumers, each shard is a unit of reading with its own ordering and checkpoint.

### 11.1. Shared-Throughput Consumers

GetRecords uses a pull model. Consumers not using Enhanced Fan-Out share up to 2 MB/s read throughput per shard and a limit of 5 GetRecords calls/second/shard. If multiple consumers read the entire stream concurrently, they can contend for throughput and increase latency.

Shared throughput fits when:

- There are few consumer applications.
- Read throughput is modest.
- Sharing capacity among consumers is acceptable.
- You want to optimize retrieval cost.

### 11.2. Enhanced Fan-Out

Enhanced Fan-Out (EFO) gives each registered consumer dedicated read throughput, up to 2 MB/s per shard per consumer. Kinesis pushes records to consumers over HTTP/2 via SubscribeToShard, reducing contention with other consumers.

Typically, On-demand Standard and Provisioned support up to 20 registered consumers per stream; On-demand Advantage supports up to 50 in AWS-listed Regions. Registered consumers and queues share the corresponding quota. EFO incurs separate retrieval/consumer-shard-hour charges per the pricing model.

EFO fits when multiple independent applications need to read the entire stream, or when a consumer requires low latency and dedicated throughput.

### 11.3. Kinesis Client Library

The Kinesis Client Library (KCL) manages shard discovery, leases, checkpoints, load balancing, and record processors. KCL stores consumer metadata in DynamoDB. When shards split or merge, KCL tracks parent-child lineage to process parent data before moving to child shards according to the library's lifecycle.

KCL fits when building Java consumers or applications requiring per-shard stateful processing. Use a currently supported KCL version; do not build consumers by arbitrarily polling shards if the application needs resharding management and durable checkpointing.

### 11.4. Lambda Event Source Mapping

AWS Lambda can read from Kinesis Data Streams via event source mapping. Lambda manages polling, batching, and checkpointing according to configuration. Consumers must handle duplicate records safely because invocations can be retried. For large batches, consider partial batch responses so successfully processed records are not replayed when only one record fails.

Whether using KCL or Lambda, monitor consumer lag and design side effects to be idempotent. Kinesis retention is only the window during which records remain readable; a consumer lagging behind the retention window risks losing the ability to replay old records.

## 12. Retention Period and Replay

Kinesis Data Streams stores records for a finite duration. Default retention is 24 hours and can be increased up to 365 days. Records older than retention are no longer available for consumers to read.

The retention period is a safety window for consumers to recover from downstream outages, not a long-term storage archive. If you need long-term retention, move data to S3, a data lake, or an appropriate archive store.

When increasing retention, records that have not yet expired under the previous retention remain available longer; data that already expired before the increase is not recovered. When reducing retention, records older than the new limit can become inaccessible almost immediately. Reducing retention should be strictly controlled.

Retention beyond 24 hours incurs additional charges. Choose retention based on incident detection time, consumer fix time, replay duration, and audit requirements.

## 13. Monitoring and Diagnosing Shards

CloudWatch provides metrics at the stream level and optionally at the shard level. Basic stream-level metrics are emitted automatically; shard-level enhanced monitoring must be enabled separately and incurs CloudWatch metrics charges.

Metrics to monitor:

| Metric | Meaning | Signs to investigate |
|---|---|---|
| IncomingBytes | Bytes written to stream/shard | Rapid growth or uneven distribution |
| IncomingRecords | Number of records written | One shard has an abnormally high record rate |
| WriteProvisionedThroughputExceeded | Records throttled on write | Producer cannot write all data |
| ReadProvisionedThroughputExceeded | GetRecords throttled | Shared consumers competing for read capacity |
| GetRecords.IteratorAgeMilliseconds | Age of the last record read by consumer | Consumer falling behind |
| SubscribeToShardEvent.MillisBehindLatest | How far behind latest an EFO consumer is | Consumer processing cannot keep up |
| PutRecords.FailedRecords | Number of failed records in a batch | Need per-record retries |
| PutRecords.ThrottledRecords | Records throttled in PutRecords | Need appropriate capacity or key strategy |

If stream-level IncomingBytes is low while one shard's IncomingBytes is high, there may be a hot shard. Enable enhanced monitoring to pinpoint the specific shard, then correlate with hash ranges and partition key distribution at the producer.

Alerts should focus on:

- WriteProvisionedThroughputExceeded increasing continuously.
- ReadProvisionedThroughputExceeded increasing continuously.
- Iterator age approaching a significant fraction of the retention period.
- PutRecords.FailedRecords or ThrottledRecords rising.
- Shard-level IncomingBytes/IncomingRecords heavily skewed across shards.
- Rising consumer processing latency or downstream errors.

Do not look only at aggregate throughput. Overall stream utilization may be low while a single shard is throttled due to a hot key.

## 14. Security and Cost

Kinesis Data Streams supports server-side encryption with AWS KMS. You can use an AWS owned key or a customer managed key depending on control requirements. Data transmitted via AWS SDK/APIs must use TLS. IAM policies should restrict producers to write-only and consumers to read-only access on the required streams.

Commonly used actions:

- Producer: kinesis:PutRecord, kinesis:PutRecords.
- Shared consumer: kinesis:GetShardIterator, kinesis:GetRecords, kinesis:DescribeStreamSummary, kinesis:ListShards.
- EFO consumer: kinesis:RegisterStreamConsumer, kinesis:SubscribeToShard, kinesis:DescribeStreamConsumer.
- Operations: kinesis:DescribeStreamSummary, kinesis:UpdateShardCount, kinesis:SplitShard, kinesis:MergeShards, and corresponding monitoring actions.

With a customer managed KMS key, grant key usage permissions to the relevant principals. Do not grant stream administration permissions to producers just so they can write records.

Primary cost drivers depend on capacity mode and consumption pattern:

- Provisioned: shard-hours and associated billing components.
- On-demand Standard: bytes written/read and applicable pricing dimensions.
- On-demand Advantage: distinct pricing structure and minimum usage commitment.
- Extended retention: retention beyond 24 hours.
- Enhanced Fan-Out: consumer-shard-hours and data retrieval per pricing.
- Enhanced shard-level metrics: CloudWatch custom metrics.
- KMS: operations using a customer managed key per KMS pricing.

Before choosing a mode, estimate write bytes, write records, read throughput, consumer count, retention, and burst levels. Actual prices vary by Region and mode; use the AWS Pricing Calculator and the Kinesis pricing page at deployment time.

## 15. Common Issues and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| ProvisionedThroughputExceededException on write | A shard exceeded byte or record limits | Check shard metrics, increase shard count, or adjust partition keys |
| One shard is hot despite spare stream capacity | Hot partition key or key skew | Analyze top keys; use composite/bucket keys if ordering change is acceptable |
| PutRecords returns HTTP success with failed records | Partial batch failure | Inspect each response record and retry only failed records |
| Slow consumer reads | Consumer CPU/downstream bottleneck or shared read contention | Scale workers/throughput, optimize processing, or use EFO |
| IteratorAgeMilliseconds rising | Consumer cannot keep up with producer | Increase processing capacity, reduce per-record time, check throttling |
| Consumer skips data after resharding | Not tracking parent-child lineage | Use KCL or implement proper shard discovery/checkpointing |
| Sequence numbers out of expected order | Reading multiple shards or using PutRecords | Clarify ordering scope; use same key/shard and PutRecord when sequentiality is required |
| Records cannot be replayed | Retention expired | Increase retention appropriately and archive long-term to S3 |
| On-demand still throttled | Traffic spiked too fast or single key exceeded shard limit | Retry with backoff, check peak history and hot keys; consider warm throughput/Provisioned |
| Cost spikes | Too many shards, EFO consumers, extended retention, or metrics | Review capacity mode, consumer count, retention, and enhanced monitoring |

## 16. Lab Exercise: Designing an IoT Telemetry Stream

An IoT platform ingests telemetry from 50,000 devices. Each device sends an average of one record per second, with an average payload of 500 bytes. The system needs two consumers:

- Consumer A aggregates device state in real time.
- Consumer B detects anomalies and sends alerts.

Business requirements: records from the same device must be processed in order; both consumers must read independently.

### 16.1. Choosing the Partition Key

Use deviceId as the partition key so all records for a device go to the same shard. Do not use a static key such as telemetry or iot because all traffic would funnel into a single shard. If a particular device or gateway sends an unusually high volume, monitor hot keys separately.

### 16.2. Estimating Write Throughput

- Total record rate: 50,000 records/s.
- Payload rate: 50,000 × 500 bytes = 25,000,000 bytes/s, roughly 25 MB/s.
- At 1 MB/s/shard limit: at least 25 shards needed by bytes.
- At 1,000 records/s/shard limit: at least 50 shards needed by record count.

Initial shard count must follow the higher limit: minimum 50 shards. Then add headroom for bursts, key sizes, and traffic growth. For example, pick 65–70 shards for testing in Provisioned mode, then tune using real metrics.

### 16.3. Choosing the Consumer Mode

Two consumers both read the full stream. At the minimum of 50 shards, shared GetRecords provides a theoretical maximum aggregate read capacity of about 100 MB/s across all shared consumers combined; the two consumers share this capacity and are also subject to per-shard read call limits. If each consumer requires dedicated throughput, stable latency, or zero contention with other consumers, EFO provides up to 2 MB/s/shard per consumer. Account for additional cost and the registered consumer quota.

### 16.4. Operations

1. Create the stream with the appropriate capacity mode.
2. Write records with partition key deviceId.
3. Enable shard-level monitoring.
4. Monitor IncomingBytes, IncomingRecords, and write throttling per shard.
5. Use EFO if both consumers need independent throughput.
6. Monitor iterator age or MillisBehindLatest for each consumer.
7. Test a bursting device to observe hot-key behavior.
8. Test resharding and verify consumers handle parent/child shards properly.
9. Increase retention if consumers need a recovery window longer than 24 hours.
10. Archive data requiring long-term storage to S3.

The exercise should prove that traffic distributes evenly enough, per-deviceId ordering is preserved within requirements, and both consumers can catch up on the stream after an outage.

## Conclusion

Shards are the fundamental unit of capacity and ordering in Kinesis Data Streams. Partition keys are hashed with MD5 into hash keys and mapped to shard hash ranges. Records with the same key land on the same shard under the current shard map, enabling per-entity ordered processing. Conversely, unevenly distributed keys can cause hot shards and throttling.

Good design starts with the business model: choose keys with suitable cardinality, maintain the right ordering scope, size for both bytes and records, and pick capacity modes and consumer models aligned with actual load. Provisioned gives fine-grained shard and resharding control; On-demand reduces capacity management overhead but does not eliminate single-key limits. Consumers must handle duplicates, checkpoints, and shard lineage; retention must be long enough for recovery without replacing long-term storage.

## References

- [Amazon Kinesis Data Streams terminology and concepts](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Kinesis Data Streams quotas and limits](https://docs.aws.amazon.com/streams/latest/dev/service-sizes-and-limits.html)
- [Choose the right mode to stream in](https://docs.aws.amazon.com/streams/latest/dev/how-do-i-size-a-stream.html)
- [Create and manage Kinesis data streams](https://docs.aws.amazon.com/streams/latest/dev/working-with-streams.html)
- [PutRecord API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecord.html)
- [PutRecords API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecords.html)
- [Service-managed record distribution strategy](https://docs.aws.amazon.com/streams/latest/dev/service-managed-record-distribution.html)
- [Split a shard](https://docs.aws.amazon.com/streams/latest/dev/kinesis-using-sdk-java-resharding-split.html)
- [MergeShards API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_MergeShards.html)
- [Resharding, scaling, and parallel processing](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-scaling.html)
- [Read data from Kinesis data streams](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Enhanced Fan-Out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Change the data retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Monitor Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Develop producers using Kinesis Producer Library](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-kpl.html)
- [AWS SDK for Java 2.x Kinesis client](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/kinesis/KinesisClient.html)
- [Amazon Kinesis Data Streams pricing](https://aws.amazon.com/kinesis/data-streams/pricing/)
