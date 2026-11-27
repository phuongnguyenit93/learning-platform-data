# Amazon MSK, Brokers, and Choosing a Deployment Model

Amazon Managed Streaming for Apache Kafka (Amazon MSK) is an AWS service that manages Apache Kafka infrastructure. Applications continue using the Kafka protocol, producers, consumers, topics, partitions, consumer groups, and compatible Kafka clients. Amazon MSK handles infrastructure operations such as cluster creation, broker node management, hardware maintenance, service-managed software updates, network integration, encryption, and monitoring.

When designing MSK, the key question is not merely "how many brokers do we need?". Architecture teams must define workload profiles, throughput, partition counts, retention, fault tolerance, connection counts, authentication models, deployment Regions/AZs, configuration control, and scaling strategy. Amazon MSK offers two primary cluster deployment options: **MSK Provisioned** and **MSK Serverless**. With Provisioned, users choose between **Standard** or **Express** broker types. Each model manages capacity, storage, and costs differently.

This lesson situates MSK in an AWS context covering Regions/AZs, VPC, IAM, KMS, CloudWatch, streaming integrations, and hybrid architectures. The goal is to select the right deployment model, understand broker and partition roles, protect data, design for high availability, and operate a scalable cluster.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Describe Kafka architecture and the roles of brokers, controllers, topics, partitions, leaders, replicas, and consumer groups.
- Explain which infrastructure layers Amazon MSK manages and which remain the application team's responsibility.
- Distinguish between MSK Provisioned and MSK Serverless.
- Compare Standard brokers and Express brokers across configuration, storage, scaling, throughput, and operations.
- Select a broker type based on workload, control requirements, and cost.
- Design Multi-AZ clusters, replication factors, `min.insync.replicas`, and producer acknowledgements.
- Understand ZooKeeper mode and KRaft mode across Kafka versions.
- Design VPCs, subnets, security groups, bootstrap endpoints, and multi-VPC/account connectivity.
- Choose IAM, SASL/SCRAM, or mutual TLS for client authentication.
- Use CloudWatch, broker logs, and Prometheus for monitoring.
- Identify the distinct roles of MSK Connect and MSK Replicator.
- Evaluate the Standard-to-Express upgrade path, including the in-place upgrade capability announced by AWS on November 19, 2026.

## 2. What Problem Does Amazon MSK Solve?

Apache Kafka is a distributed streaming platform. Producers write events to topics; consumers read events by offset. Topics can be split into multiple partitions to increase parallelism and scalability. Kafka stores data as an ordered log within each partition, supporting replication for durability and fault tolerance.

When self-managing Kafka on Amazon EC2, engineering teams are responsible for many layers:
- Provisioning and replacing EC2 brokers.
- Designing EBS volumes, throughput, and storage capacity.
- Configuring Kafka, metadata management, and broker placement.
- Managing patches, upgrades, broker replacements, and partition reassignments.
- Troubleshooting broker, disk, network, and controller incidents.
- Building monitoring, log collection, backup/replication, and runbooks.
- Managing security, certificates, credentials, and access permissions.

Amazon MSK reduces infrastructure operational overhead by providing managed Kafka clusters on AWS. Users continue working with familiar Kafka APIs and tooling. MSK provides control-plane APIs to create, update, describe, and delete clusters; the data plane continues using the Kafka protocol to create topics, publish, consume, and administer Kafka resources.

MSK fits when:
- Applications already use Kafka clients or the Kafka ecosystem.
- Event streaming is needed across multiple applications or microservices.
- Keeping Kafka APIs, consumer groups, partitions, and ecosystem tools is required.
- Integration with IAM, VPC, CloudWatch, KMS, Lambda, Glue Schema Registry, or Managed Service for Apache Flink is desired.
- You want to reduce broker operations while retaining control over Kafka topology.

If a workload does not require Kafka compatibility, also evaluate other streaming services such as Amazon Kinesis Data Streams. The choice depends on client protocols, partition/shard models, existing ecosystem, integration needs, and operational cost.

## 3. Kafka Architecture and the Role of Brokers

A Kafka cluster consists of multiple brokers. Each broker is a node that handles client requests and stores a subset of partitions or partition replicas.

### 3.1 What Does a Broker Do?

A broker has the following main responsibilities:

- Handling metadata requests from producers and consumers.
- Receiving records sent by producers to partition leaders.
- Persisting log segments to storage.
- Serving fetch requests from consumers.
- Replicating data between leader and follower replicas.
- Participating in consumer group coordination and handling Kafka administrative requests.
- Reporting partition, replica, request, and resource health metrics.

Brokers are not where applications store business logic. Brokers store and distribute events; producers decide which events are written, and consumers process events while tracking progress via offsets.

### 3.2 Topics and Partitions

A topic is the logical name of an event stream. A topic consists of one or more partitions.

Each partition is an ordered, append-only log. Records receive monotonically increasing offsets within the partition. Kafka guarantees ordering within a single partition; it does not guarantee global ordering across partitions.

Producers can select partitions by:
- Specifying the partition explicitly.
- Hashing a key via a partitioner.
- Round-robin or sticky partitioning when no key is provided, depending on client and configuration.

If events with the same key are consistently routed to the same partition, they preserve per-key ordering. For example, use `customerId` as the key so events for one customer are processed in order within a single partition.

Partitions impact:
- Producer/consumer parallelism.
- Number of leaders and replicas distributed across brokers.
- Metadata footprint.
- Consumer group rebalance duration.
- CPU, network, and storage load.
- Monitoring and operational overhead.

Adding partitions does not always make a system faster. Too few partitions cap throughput and consumer parallelism; too many partitions increase metadata overhead, file handles, memory usage, recovery time, and rebalance duration.

### 3.3 Leader and Follower Replicas

Each partition has one leader replica and can have multiple follower replicas. Producers write to the leader; followers replicate the log from the leader. Consumers typically read from the leader depending on client/cluster settings.

Example of a topic with replication factor 3 in a three-AZ cluster:

~~~text
                 Amazon MSK - Region
       AZ-a                 AZ-b                 AZ-c
  +-------------+      +-------------+      +-------------+
  | Broker 1    |      | Broker 2    |      | Broker 3    |
  | Partition 0 |      | Partition 0 |      | Partition 0 |
  | Leader      | ---> | Follower    | ---> | Follower    |
  +-------------+      +-------------+      +-------------+

  Producer ----------------> Partition 0 leader
  Consumer <---------------- Partition 0 leader
~~~

This diagram shows one partition; in practice, a broker holds many leaders and followers across multiple topics/partitions. MSK distributes brokers across AZs according to cluster configuration. Express brokers apply replication across three AZs; with Standard brokers, replication strategy depends on cluster topology and topic configuration.

### 3.4 In-Sync Replicas (ISR)

The ISR is the set of replicas currently caught up closely enough with the leader under Kafka's criteria. When a producer uses `acks=all`, the leader acknowledges writes according to the replication policy and `min.insync.replicas`.

A common configuration for critical topics on a three-AZ cluster:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
enable.idempotence = true
~~~

Meaning:
- Three replicas exist for each partition.
- At least two replicas must remain in the ISR to accept writes under the min ISR setting.
- Producers wait for replica acknowledgements per `acks=all`.
- Idempotent producers reduce the risk of duplicates from retries within the guarantees of the Kafka producer protocol.

If `min.insync.replicas` equals the replication factor, a single replica going temporarily offline can block producer writes. If min ISR is too low, the system may keep accepting writes when data redundancy is degraded. Choose based on durability and availability requirements.

AWS recommends a replication factor of at least 3 for Standard brokers. RF=1 can take partitions offline during rolling updates; RF=2 can increase data loss risk during certain maintenance or failure scenarios. With Express brokers, three-AZ replication is enforced by the service to enhance availability.

### 3.5 Consumer Groups and Offsets

Consumer groups allow multiple consumers to share reading a topic. Each partition is assigned to at most one consumer in the same group at a time, while one consumer can handle multiple partitions.

Offsets record a consumer's read position. During a consumer group rebalance, partitions may move between consumers. Applications must handle:
- Consumer crashes and restarts.
- Rebalances when adding/removing consumers.
- Record processing taking longer than the poll interval.
- Automatic or manual offset commits.
- Retries and dead-letter topics.
- Duplicate delivery and idempotent processing.
- Rising consumer lag caused by slow downstream dependencies.

Kafka is typically used with an at-least-once model. Exactly-once semantics require proper producer transaction settings, consumer isolation levels, and processing logic; you cannot simply toggle one property and assume every external system outside Kafka executes once.

## 4. Metadata Management: ZooKeeper and KRaft

Kafka must manage cluster metadata such as broker membership, topics, partitions, replicas, and controller state.

Amazon MSK supports two metadata management modes across supported versions:

| Mode | How metadata is managed | Notes |
|---|---|---|
| ZooKeeper mode | Uses MSK-managed ZooKeeper nodes | Available on Kafka versions that still support ZooKeeper |
| KRaft mode | Uses a Kafka controller quorum to manage metadata | MSK supports creating KRaft clusters starting with Kafka 3.7.x |

In KRaft, metadata is managed by controllers within the Kafka cluster instead of an external ZooKeeper ensemble. MSK manages the metadata nodes/controllers for users without requiring customers to provision or operate controllers themselves.

Key points to remember:
- KRaft is supported on Amazon MSK starting with Kafka 3.7.x.
- Clusters can be created in ZooKeeper mode or KRaft mode depending on supported versions and options.
- Kafka 3.7.x uses distinct version suffixes when creating clusters via API to specify KRaft or ZooKeeper.
- Kafka data-plane APIs do not need to change solely because of moving to KRaft.
- Administrative tooling should not depend on direct ZooKeeper connections.
- Use `--bootstrap-server` instead of `--zookeeper`; the `--zookeeper` flag was deprecated and removed in Kafka 3.0.
- MSK manages controllers and does not require customers to access controllers directly for monitoring or operations.

Example KRaft diagram:

~~~text
              Amazon MSK cluster
       +--------------------------------+
       | Broker 1   Broker 2   Broker 3 |
       |     \        |        /        |
       |      \       |       /         |
       |       Kafka KRaft controllers  |
       |       manage cluster metadata  |
       +--------------------------------+
                    |
             Kafka bootstrap
                    |
             Producer / Consumer
~~~

Do not pick a Kafka version solely because it is the newest. Check MSK-supported versions, end-of-support dates, client compatibility, broker type, KRaft mode, and features your application needs.

## 5. Two Cluster Deployment Models

Amazon MSK offers two deployment options:

1. **MSK Provisioned**: users configure and manage cluster sizing at the broker level.
2. **MSK Serverless**: MSK automatically provisions and scales compute/storage for the cluster; users do not choose broker count or broker size.

MSK Provisioned offers two broker types:
- Standard.
- Express.

Do not confuse broker types with deployment options. Both Standard and Express belong to MSK Provisioned; Serverless is a separate deployment option.

| Criterion | Provisioned Standard | Provisioned Express | Serverless |
|---|---|---|---|
| Broker management | Choose count and instance size | Choose broker size/count; MSK manages more operations | MSK manages all broker capacity |
| Storage | User configures EBS, throughput, and retention; tiered storage available | MSK manages elastic pay-as-you-go storage | MSK manages storage |
| Kafka configuration | More flexible | Guardrails and more MSK-managed best-practice defaults | More limited set of supported configs |
| Scaling | Planned adjustments to broker size/count and storage | Flexible scaling with intelligent rebalancing | Automatic based on load within quotas |
| Availability topology | Choose AZs and replication strategy | Requires 3 AZs | MSK manages capacity and placement |
| Cost predictability | Depends on brokers, EBS, throughput, transfer | Brokers and usage-based storage/ingestion | Based on throughput and stored data/partitions |
| Best for | Configuration control, steady workloads | High-throughput workloads, fast scaling, minimal storage management | Variable load, minimizing capacity planning effort |

Decisions must be based on workload and feature requirements. Do not choose Serverless just to avoid broker management; nor choose Provisioned just for configuration knobs the application does not actually need.

## 6. MSK Provisioned Standard Brokers

Standard brokers represent the traditional Kafka model in MSK Provisioned, giving broad control over cluster and storage configuration.

### 6.1 Characteristics

- Choose broker instance family/size from the MSK-supported list.
- Choose the number of brokers per Availability Zone.
- Configure EBS storage per broker.
- Supports provisioned storage throughput, storage autoscaling, and storage capacity alerts.
- Supports tiered storage on compatible Kafka versions and configurations.
- Allows deeper Kafka configuration customization than Express.
- Supports MSK Provisioned authentication and encryption options.
- Can scale vertically by changing broker size and horizontally by changing broker count.

Standard brokers fit when deep customization is needed, workload sizing is relatively well understood, and operations teams are prepared to manage storage/partition balancing.

### 6.2 Choosing Broker Instances

Broker size affects:
- CPU for handling requests, compression, encryption, and replication.
- Memory for page cache, request buffers, and metadata.
- Network throughput.
- Capacity to serve connections and partitions.
- Headroom to absorb rolling maintenance or broker failures.

A broker with low CPU can still bottleneck if network or disk throughput is saturated. Never size on CPU alone.

T3 can suit small workloads, testing, or low traffic within burst limits. M5/M7g/M8g suit production workloads depending on throughput, CPU, memory, and network profiles. Always verify supported broker instance types for the target Region and Kafka version.

### 6.3 EBS Storage

With Standard brokers, storage must be forecasted and monitored. Estimate capacity based on:
- Average and peak ingress rate.
- Retention by time or size.
- Replication factor.
- Compression ratio.
- Data growth rate.
- Duration consumers might fall behind.
- Headroom for compaction, recovery, and operational activities.

Rough sizing formula for a topic:

~~~text
Approximate logical capacity
  = Ingress bytes/second
    x Retention seconds

Approximate physical capacity in cluster
  = Logical capacity
    x Replication factor
    x Headroom factor
~~~

This formula is only for initial budgeting. Actual usage also depends on compression, log segments, indexes, compaction, retention policies, and partition distribution across brokers.

MSK Standard lets you increase EBS storage per broker. Storage cannot be shrunk once increased. Each storage scaling operation has a cooldown period; this can range from several hours to over a day depending on size, utilization, and traffic. Therefore, avoid running storage near its limit and waiting for an alarm before expanding.

### 6.4 Tiered Storage

Tiered storage for Standard brokers allows retaining older data on a lower-cost storage tier while keeping recent data on the performance-optimized primary storage tier.

Benefits:
- Extend retention without proportionally increasing EBS on brokers.
- Reduce pressure on primary storage capacity.
- Support replaying older data using standard Kafka APIs.
- Decouple part of long-term storage cost from broker disk sizing.

Important limitations:
- Applies only to MSK Provisioned Standard brokers.
- Requires a compatible Kafka version.
- Compacted topics are not supported in currently documented tiered storage configurations.
- Initial reads of remote-tier data may experience higher latency.
- Certain log cleanup/partition configurations have restrictions.
- Not suitable for every workload, especially workloads needing frequent random replay at ultra-low latency.

Evaluate retention and consumer access patterns before enabling tiered storage. Do not assume all data shares identical read latency.

## 7. MSK Provisioned Express Brokers

Express is a broker type within MSK Provisioned targeted at high-throughput workloads needing rapid scaling and reduced storage management.

### 7.1 Characteristics

- Storage is fully managed by MSK, scales elastically on demand, and is billed by usage.
- Eliminates forecasting/provisioning EBS volumes as in Standard.
- Brokers ship with best-practice configurations and guardrails on key settings.
- Enforces client throughput quotas to prevent one client from monopolizing cluster resources.
- Supports intelligent rebalancing to automatically distribute partitions when scaling.
- MSK performs continuous hardware maintenance; Express does not use maintenance windows in the traditional Standard manner.
- Supports three-AZ Multi-AZ deployment.
- Select from supported broker sizes; confirm supported instance types and versions per Region.

AWS states that Express can deliver up to 3x throughput per broker, scale up to 20x faster, and recover up to 90% faster than Standard under compared sizes and conditions. These are AWS-documented maximums, not throughput guarantees for every cluster. Benchmark with your real workload.

### 7.2 Guardrails and Limitations

Express reduces deep tuning overhead, yet not every Kafka feature behaves identically to Standard.

Per current AWS documentation at the time of writing:
- Express deploys exclusively across three Availability Zones.
- Express broker sizes use AWS-supported instance families, currently including M7g and M8g; Standard offers a broader list such as T3, M5, M7g, and M8g.
- Express documentation currently lists Kafka 3.6, 3.8, 3.9, and 4.2; version support may change over time and by Region.
- KRaft mode can be selected when creating clusters on supported Express versions, currently documented as Kafka 3.9 and newer.
- Some newer Kafka features or specialized APIs may not yet be fully supported.
- Express does not yet fully support the Kafka Streams API per current feature notes.
- KIP-932 Queues for Kafka are not yet supported per current Express documentation.
- Critical settings may be restricted to protect durability and availability.

If applications depend on Kafka Streams, transactions, compacted topics, custom broker configurations, or specialized plugins, verify the feature support matrix before choosing Express.

### 7.3 Intelligent Rebalancing

When adding or removing brokers, Kafka must redistribute partitions and replicas so new brokers do not sit empty while older brokers stay overloaded.

Intelligent rebalancing on Express automates partition balancing during scaling operations. New Express clusters have this feature enabled by default. For clusters upgraded in-place from Standard to Express, verify intelligent rebalancing status after the upgrade because AWS instructs enabling it before right-sizing broker counts.

## 8. MSK Serverless

MSK Serverless is a cluster model where AWS automatically manages compute and storage capacity. Users do not choose instance types, broker counts, or manually scale cluster capacity as throughput fluctuates.

### 8.1 Characteristics

- Create the cluster in a VPC and select subnets for client connectivity.
- MSK provisions and scales capacity automatically as workloads change.
- Manages partitions and broker capacity under a service-managed model.
- Compatible with Kafka clients.
- Integrates with IAM access control, AWS PrivateLink, AWS Glue Schema Registry, Managed Service for Apache Flink, and Lambda.
- Billed by throughput and stored data/partitions under current pricing.

Serverless fits:
- Workloads with highly variable or unpredictable traffic.
- Teams wanting to prototype streaming without broker sizing.
- Multiple producers/consumers whose capacity demands rise and fall over time.
- Applications not requiring deep broker tuning that fit within service quotas.

### 8.2 Limitations to Know

MSK Serverless requires IAM access control on every cluster. Apache Kafka ACLs are not supported as an authorization mechanism on Serverless. Therefore, applications must use IAM policies and IAM authentication.

Serverless enforces quotas per cluster, account, and Region. Relevant quotas may include:
- Ingress/egress throughput.
- Per-partition throughput.
- Partition count and consumer group count.
- Connection count and connection creation rate.
- Message size.
- Number of connected VPC clients.
- Number of clusters per account.

Quotas may be adjustable via AWS processes and evolve over time. Before moving production workloads to Serverless, inspect the MSK quotas page and Service Quotas in the target Region.

Serverless reduces infrastructure management, but it does not eliminate responsibility for designing partitions, keys, retention, producer retries, consumer lag handling, schema evolution, and idempotent processing.

## 9. Choosing a Deployment Model by Workload

| Workload | Initial recommendation | Rationale and items to verify |
|---|---|---|
| Event pipeline with steady traffic needing custom configs | Provisioned Standard | Control over brokers, storage, throughput, and Kafka configurations |
| High-throughput streaming needing fast scaling | Provisioned Express | Managed storage, high throughput/broker, intelligent rebalancing |
| New workload with uneven traffic wanting to avoid sizing | Serverless | Auto-scales capacity; verify quotas and IAM-only access |
| Heavy use of Kafka Streams API | Standard before confirming Express support | Express has API limitations to verify |
| Long retention via tiered storage | Provisioned Standard | Tiered storage applies to Standard |
| Control over EBS, storage throughput, and broker configs | Provisioned Standard | More flexible than Express |
| Automated partition management during scaling | Express | Built-in intelligent rebalancing |
| Applications needing IAM policy authentication | Provisioned or Serverless | Serverless requires IAM; Provisioned supports IAM alongside other options |
| Extensive specialized Kafka configurations | Standard | Express enforces guardrails and more MSK-managed settings |

Selection process:
1. Determine average and peak ingress/egress.
2. Measure connection counts, partitions, consumer groups, and message sizes.
3. Define retention and replay needs.
4. List mandatory Kafka APIs, plugins, transactions, and features.
5. Choose AZ, RPO, durability, and maintenance requirements.
6. Determine required level of broker/storage control.
7. Compare costs across typical and peak loads.
8. Run benchmarks and fault-injection rehearsals before production.

## 10. Designing Broker Count, AZs, and Replication

### 10.1 Multi-AZ

An MSK Provisioned cluster deploys within an AWS Region and distributes brokers across Availability Zones. When creating a cluster, select subnets matching AZs and the number of brokers per AZ.

For Standard brokers, a three-AZ topology is commonly chosen for production workloads needing AZ fault tolerance. AWS documentation recommends including brokers from multiple AZs in the client bootstrap string so clients can connect if one broker is under maintenance or offline.

Express brokers require three AZs.

### 10.2 Broker Count

Broker count must satisfy:
- Producer throughput.
- Consumer throughput.
- Inter-broker replication traffic.
- Partition and replica counts.
- Connection count.
- CPU and network headroom.
- Ability to sustain load when one broker goes offline.

Do not size by total disk capacity alone. A cluster with plenty of disk space but insufficient CPU or network will still throttle producers and increase consumer lag.

### 10.3 Partition Count

Estimate partitions based on:
- Target throughput.
- Consumer group parallelism.
- Number of keys and key distribution.
- Ordering requirements.
- Broker count and partition-per-broker guidance.
- Rebalance and recovery times.

If one partition receives disproportionate traffic, raising total partition count will not fully fix it if key partitioning still sends all records to one partition. Revisit key design and skew.

AWS publishes recommended partitions per Standard broker by instance size. Treat this as operational guidance rather than a universal constant for every workload. Count both leader and follower replicas when evaluating partitions per broker.

### 10.4 Replication and Availability

For critical topics:
- Use replication factor 3 where topology allows.
- Consider `min.insync.replicas=2`.
- Use producer `acks=all` and idempotence where appropriate.
- Monitor `UnderReplicatedPartitions`, `OfflinePartitionsCount`, and ISR shrinks/expands.
- Do not lower RF just to save storage if durability requires multiple copies.
- Test producer retries and client failover when a broker stops.

Replication protects against broker/AZ failures within design limits. It does not replace backups, retention policies, cross-Region DR, or protection against logical bugs like producers writing bad data.

## 11. Designing Topics, Keys, and Retention

Broker capacity is only part of the picture. Topic design governs load distribution and how applications consume data.

### 11.1 Choosing Topic Boundaries

A topic typically represents an event stream with a clear schema, retention, and consumer contract.

Examples:
- `orders.created`
- `orders.cancelled`
- `payments.authorized`
- `inventory.changed`
- `audit.events`

Do not create a new topic per customer or per request. Too many tiny topics create administrative overhead; overly broad topics make schemas, ACLs, and retention hard to manage.

### 11.2 Choosing Keys

Keys should reflect ordering boundaries and partition distribution.

Examples:
- `orderId`: preserves event ordering for an order.
- `customerId`: preserves event ordering for a customer.
- `deviceId`: preserves telemetry ordering for a device.

If one key dominates traffic, it creates a hot partition. Inspect skew by measuring record/byte distribution per partition and consider composite keys or revising consumer semantics. Do not add random suffixes if business logic requires per-entity ordering.

### 11.3 Retention

Retention can be time-based or size-based. Determine:
- How long can consumers stay offline?
- Is replay needed after incidents?
- Does the data contain sensitive information or PII?
- Are there specific compliance retention/audit rules?
- How does storage cost scale with replication factor?
- Is a compacted topic needed to keep the latest state per key?

Long retention aids replay and consumer recovery, though it increases storage costs and data governance needs. Compaction fits key-based state topics, but does not replace event history when full history is needed.

### 11.4 Example: Creating a Topic

Retrieve bootstrap broker strings from the MSK console or API, then run a Kafka CLI version compatible with the cluster.

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_BROKERS" \
  --command-config client.properties \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3
~~~

This example assumes a Provisioned Standard cluster with a three-AZ topology and properly configured client authentication. For Express, check supported topic quotas/configs. For Serverless, follow service-permitted quotas and topic settings.

Describe the topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_BROKERS" \
  --command-config client.properties \
  --describe \
  --topic orders.created
~~~

Modern administrative operations should use `--bootstrap-server`. Do not rely on ZooKeeper connection strings to create topics or administer clusters.

## 12. Producer and Consumer Configuration

### 12.1 Producers

Key parameters:

| Parameter | Purpose | Notes |
|---|---|---|
| `acks` | Write acknowledgement level | `all` usually fits critical topics |
| `enable.idempotence` | Reduces retry duplicates | Verify compatibility and related parameters |
| `retries` | Retries on transient errors | Needs matching timeouts and idempotence |
| `delivery.timeout.ms` | Upper bound on record delivery time | Set based on latency/SLA and retry policy |
| `linger.ms` | Batch accumulation wait time | Can boost throughput while adding latency |
| `batch.size` | Batch size | Balances throughput, memory, and latency |
| `compression.type` | Compresses record batches | Trade off CPU against network/storage |
| `max.in.flight.requests.per.connection` | Unacknowledged requests in flight | Must be compatible with idempotence and ordering |

Conceptual configuration example:

~~~properties
acks=all
enable.idempotence=true
compression.type=lz4
linger.ms=5
batch.size=65536
delivery.timeout.ms=120000
~~~

This is a starting point for benchmarking, not an optimal configuration for every application.

### 12.2 Consumers

Key parameters:

| Parameter | Purpose | Notes |
|---|---|---|
| `group.id` | Consumer group identifier | Use separate groups per workload/logic |
| `enable.auto.commit` | Automatic offset commits | Consider manual commits when strict processing control is needed |
| `auto.offset.reset` | Starting position when no offset exists | `earliest` may replay large volumes of data |
| `max.poll.records` | Max records per poll | Balances batching and processing time |
| `max.poll.interval.ms` | Allowed processing time between polls | Prevents rebalances from slow processing |
| `session.timeout.ms` | Detects disconnected consumers | Tied to heartbeats and group protocol |
| `fetch.min.bytes` | Minimum bytes to return on fetch | Increases batching, may add latency |
| `isolation.level` | Read committed transactions or uncommitted records too | Use `read_committed` when transactional visibility is required |

Consumers must commit offsets in alignment with processing completion. Committing before processing succeeds risks losing events from the application's processing flow on errors. Committing after processing means a crash between processing and commit can cause reprocessing. Design idempotency or transactions accordingly.

## 13. Networking and Bootstrap Endpoints

Amazon MSK runs inside a VPC and creates network interfaces in selected subnets. Brokers are not exposed publicly to the Internet by default. Clients need a network path to broker endpoints and security groups permitting required traffic.

### 13.1 Clients in the Same VPC

Verify:
- Client subnet route tables.
- MSK subnet route tables.
- Broker ENI security groups.
- Client security groups.
- Network ACLs and firewalls.
- DNS resolution.
- Kafka listener ports matching the authentication mode.
- TLS trust chain and client authentication.

Allow only specific client sources to access required listeners. Never open all ports to `0.0.0.0/0`.

### 13.2 Bootstrap Broker Strings

A bootstrap string is the list of broker endpoints clients use to establish initial connections and fetch cluster metadata. Kafka clients then learn partition leaders and connect directly to the corresponding brokers.

Include brokers from multiple AZs in the bootstrap list so clients have multiple entry points during broker maintenance or failures.

Bootstrap endpoints differ by authentication mode, for example:
- IAM.
- SASL/SCRAM.
- TLS/mTLS.
- Unauthenticated if enabled.

Do not hardcode a single broker endpoint across all applications. Store endpoints by environment and deployment config, and plan updates when clusters change.

### 13.3 Connecting from Multiple VPCs and Accounts

MSK multi-VPC private connectivity uses AWS PrivateLink so clients in other VPCs/accounts can connect to a cluster while keeping traffic inside the AWS network.

Benefits:
- Reduces the need for complex VPC peering or Transit Gateway routing.
- Supports VPCs with overlapping CIDRs.
- Supports cluster policies allowing other accounts to create managed VPC connections.
- Suits multi-account architectures and shared streaming platforms.

Check:
- Minimum supported Kafka version.
- Authentication mode (IAM, TLS, or SASL/SCRAM).
- Apache Kafka ACLs when using SASL/SCRAM or mTLS.
- Matching subnets and Availability Zone IDs.
- Connection limits and associated charges.
- Multi-VPC private connectivity operates within the same Region; it is not cross-Region connectivity.

### 13.4 On-Premises and Hybrid

On-premises clients can connect over AWS Site-to-Site VPN or AWS Direct Connect. Design for:
- Routing between data centers and the VPC.
- DNS resolution from on-premises.
- Security groups and firewall rules.
- MTU, packet loss, latency, and throughput.
- TLS and certificate trust.
- Redundancy if VPN or Direct Connect degrades.
- Bandwidth for producers, consumers, and replication.

Never evaluate networking with ping alone. Kafka relies on many long-lived TCP connections, request/response exchanges, and replication traffic. Benchmark using producer/consumer throughput and test broker failover.

## 14. Security: Authentication, Authorization, and Encryption

### 14.1 IAM Access Control

IAM access control combines authentication and authorization. Clients authenticate with AWS credentials/roles; IAM policies govern which Kafka actions a client can perform on clusters, topics, and consumer groups.

Advantages:
- Eliminates maintaining separate usernames/passwords per client.
- Integrates with IAM roles for EC2, ECS, EKS, Lambda, or other AWS workloads.
- Manages permissions by principal and resource.
- Supports auditing access events via AWS mechanisms.

Notes:
- MSK Serverless requires IAM access control.
- With IAM authorization, Apache Kafka ACLs do not govern permissions for IAM identities; IAM policies are required.
- Non-Java clients require supported Kafka versions and libraries per documentation.
- Use separate roles for producers, consumers, and admins.

### 14.2 SASL/SCRAM

SASL/SCRAM uses usernames/passwords stored in AWS Secrets Manager and associated with the cluster. MSK enforces TLS for client-broker traffic when SCRAM is configured.

Suitable when existing systems already have Kafka clients using SCRAM or require dedicated credential management. Manage:
- Secret lifecycle.
- Rotation.
- Secret read permissions.
- Kafka ACLs for authorization.
- Credential revocation procedures.
- Never write passwords into source code, logs, or public config files.

### 14.3 Mutual TLS (mTLS)

mTLS authenticates clients via certificates. MSK uses AWS Private CA to sign client certificates in supported setups.

Manage:
- CAs and trust chains.
- Certificate issuance/renewal.
- Private key protection.
- Identity mapping to Kafka ACLs.
- Certificate revocation and compromised-certificate handling procedures.

Amazon MSK does not support certificate revocation lists (CRLs) per current documentation. Therefore, revoking/managing client certificates must combine appropriate ACLs and security groups; do not assume a CRL will automatically block a compromised certificate.

### 14.4 Encryption at Rest and in Transit

Two encryption layers address two distinct risks:

- At rest: encrypts stored data with an AWS KMS key per cluster settings.
- In transit: TLS between clients and brokers, as well as between broker/metadata components per MSK settings.

When using IAM, SASL/SCRAM, or mTLS, client-broker traffic must use TLS under MSK-supported security combinations. Never use plaintext listeners for sensitive production data.

### 14.5 Topic and Consumer Group Authorization

Apply least privilege:
- Producers only get write permissions on required topics.
- Consumers only get read permissions on required topics and groups.
- Admin roles are separated from runtime roles.
- Connector roles access only required topics/sources/sinks.
- Restrict topic creation/deletion permissions in production.
- Periodically review wildcard ACLs and IAM resource policies.

## 15. MSK Connect and MSK Replicator

These two services complement MSK, though neither is a broker type.

### 15.1 MSK Connect

MSK Connect is a managed service for running Kafka Connect connectors. Connectors read from or write to external systems, such as:
- Amazon S3.
- OpenSearch.
- Databases.
- Data warehouses.
- Other SaaS or Kafka-compatible systems.

MSK Connect manages workers and connector lifecycles. Users still select plugins and configure connectors, IAM roles, networking, secrets, capacity, and error handling.

Do not confuse MSK Connect with brokers:
- Brokers store topics/partitions and serve the Kafka protocol.
- Connectors move or integrate data between Kafka and external systems.

### 15.2 MSK Replicator

MSK Replicator replicates topic data and metadata between source and target Kafka clusters under supported configurations. It can be used for:
- Cross-Region replication.
- Disaster recovery.
- Cluster migrations.
- Splitting workloads across Regions.
- Migrating from self-managed Kafka to MSK.

MSK Replicator operates asynchronously. Replication latency depends on inter-Region distance, throughput, partition counts, and capacity of both clusters.

Distinguish carefully:
- Replicator can sync topic data/configs and consumer offsets within supported capabilities.
- Replicator does not replicate internal state of stateful applications like Flink/Kafka Streams.
- Stateful applications may require rebuilding state or custom checkpoint restoration during migration.
- Cross-Region replication does not replace failover/failback testing.

## 16. Scaling and Capacity Management

### 16.1 Vertical Scaling

Vertical scaling changes broker size to increase CPU, memory, or network capacity. This typically adds compute capacity without requiring partition redistribution in the same way horizontal scaling does.

With Standard brokers:
- Broker sizes can be changed within supported instance types.
- Scaling down has restrictions; AWS documentation notes you cannot move to a smaller broker size in certain Standard update flows.
- Maintain headroom so rolling operations do not overload the cluster.

With Express:
- Broker sizes can be changed among supported options.
- More configurations and guardrails are managed by MSK.
- Intelligent rebalancing helps distribute resources during scaling.

### 16.2 Horizontal Scaling

Horizontal scaling adds or removes brokers. When adding brokers, address partition placement and leader/follower distribution.

With Standard, adding brokers does not mean existing partitions automatically rebalance optimally onto the new brokers. Plan reassignment and use Kafka reassignment tools or Cruise Control per MSK guidance.

With Express, intelligent rebalancing helps manage partition movement during scaling. Verify feature status, especially on clusters recently upgraded in-place from Standard.

### 16.3 Storage Scaling

With Standard:
- EBS storage can be increased.
- Provisioned storage cannot be shrunk.
- Storage autoscaling can expand based on thresholds.
- Monitor disk utilization, retention, and growth rates.
- Each storage scaling action has a cooldown period.

With Express and Serverless, MSK manages storage capacity. Users still monitor retained data volume, retention, throughput, and usage costs.

### 16.4 Partition Reassignment and Headroom

Partition movement generates extra network and disk I/O. If a cluster is already near saturation, rebalancing can raise producer latency and inflate consumer lag.

Before scaling:
1. Check CPU, network, disk, and request latency.
2. Check under-replicated/offline partitions.
3. Check partition counts per broker.
4. Assess replication traffic and background operations.
5. Schedule a maintenance window or low-traffic period when needed.
6. Monitor reassignment progress and consumer lag.
7. Verify leader distribution after completion.

## 17. Monitoring and Logging

Amazon MSK integrates with CloudWatch to collect Kafka metrics. Provisioned clusters can also enable Open Monitoring with Prometheus.

### 17.1 Metrics to Monitor

| Metric/group | Meaning | Signal to investigate |
|---|---|---|
| CPU User/System | Broker processing load | Sustained high CPU, lack of headroom |
| BytesInPerSec | Write throughput | Sudden spikes or skewed load across brokers |
| BytesOutPerSec | Read throughput | Rising consumer traffic or egress bottleneck |
| Request latency | Request processing duration | Slow producer/consumer responses |
| UnderReplicatedPartitions | Replicas falling behind | Replication lag, broker/network/storage issues |
| OfflinePartitionsCount | Partitions with no available leader | Risk of read/write disruption |
| ActiveControllerCount | Cluster-level controller health | Abnormal values or controller elections |
| Consumer lag | Gap between log end and consumer offset | Slow or stalled consumers |
| Disk/storage usage | Storage consumption | Growing retention, disk nearing capacity |
| Connection count | Client connection volume | Connection storms or unbounded pools |
| Network throughput | Broker network load | Saturation or rising cross-AZ traffic |

Metric names and monitoring levels can differ across Standard, Express, and Serverless. Check current metric namespaces and dimensions for your broker type.

### 17.2 Monitoring Levels

MSK Provisioned offers monitoring levels such as:
- Default/cluster-level.
- Per-broker.
- Per-topic-per-broker.
- Per-topic-per-partition.

Higher granularity helps locate hot partitions and broker imbalances, but emits more metrics and can incur higher CloudWatch costs. Choose a level fitting investigation needs and budget.

### 17.3 Broker Logs

MSK Provisioned can deliver broker logs to:
- Amazon CloudWatch Logs.
- Amazon S3.
- Amazon Data Firehose.

Logs aid investigation of authentication failures, request errors, broker events, and operational activity. Create and grant permissions on log destinations before enabling delivery.

### 17.4 Open Monitoring

Provisioned clusters can enable a Prometheus exporter to scrape JMX/host metrics. You can use Amazon Managed Service for Prometheus, Amazon Managed Grafana, or any Prometheus-compatible observability system.

Open Monitoring enables deep analysis, though you must account for network transfer and metric storage/query costs. Do not enable every per-partition metric unless needed.

### 17.5 Alerts and Runbooks

Configure alerts for:
- Non-zero offline partitions.
- Persistent under-replicated partitions.
- Consumer lag exceeding SLA.
- CPU/network/storage exceeding operational thresholds.
- Spikes in broker connection or authentication failures.
- Disk nearing capacity on Standard.
- Rising Replicator lag.
- DMS/connector errors if the pipeline includes integration components.

Link every alert to a runbook and owner. Avoid paging on a single brief datapoint if normal workloads exhibit short bursts.

## 18. Amazon MSK Cost

Cost depends on deployment option, broker type, broker count, storage, throughput, retention, data transfer, and monitoring.

### 18.1 Provisioned Standard

Typical cost components:
- Broker instance-hours.
- Provisioned EBS storage.
- Provisioned storage throughput if used.
- Tiered storage if enabled.
- Data transfer per AWS rules.
- CloudWatch metrics/logs and integrated services.

Provisioned but unused storage still incurs charges. Over-provisioning EBS inflates bills; under-provisioning risks running out of disk.

### 18.2 Provisioned Express

Typical cost components:
- Broker-hours.
- Usage-based managed storage.
- Data ingestion/storage per Express pricing.
- CloudWatch monitoring/logging and optional integrations.

Express may need fewer brokers for the same throughput compared to Standard, yet you should never assume Express is always cheaper. Benchmark, model costs for your actual workload and retention, and compare total cost.

### 18.3 Serverless

Serverless bills by streamed data and storage/partitions per current pricing. You do not pay for user-selected broker instances, but throughput, partition counts, and retention still drive costs.

Serverless suits variable traffic; for steady, sustained high-throughput workloads, Provisioned may offer better economics depending on Region and configuration.

### 18.4 Monitoring and Replication Costs

CloudWatch enhanced metrics can incur per-metric charges. Prometheus, log delivery, S3 retention, and cross-Region replication also carry separate charges.

A cost model should include:
- Baseline throughput.
- Peak throughput.
- Retention.
- Replication factor.
- Partition count.
- Data transfer.
- Monitoring level.
- Replicators/connectors.
- Growth and burst headroom.

## 19. Creating a Cluster and Connecting Clients: Hands-On Workflow

Example deploying a Provisioned Standard cluster for an order events workload.

### Step 1: Prepare the Architecture

Define:
- Target Region.
- Three AZs for production.
- Three private subnets, one per AZ.
- Dedicated security group for MSK.
- Client workloads running in VPC or hybrid connectivity.
- Authentication using IAM or SASL/SCRAM.
- KMS key for encryption at rest.
- CloudWatch metrics and broker log destinations.

### Step 2: Create the Cluster

In the Amazon MSK console:
1. Choose Create cluster.
2. Select cluster type Provisioned.
3. Choose a supported Kafka version.
4. Choose broker type Standard or Express.
5. Choose broker size and brokers per AZ.
6. Select three AZs for a proper production topology.
7. Configure storage/throughput if Standard.
8. Select VPC, private subnets, and security group.
9. Enable authentication and encryption.
10. Choose monitoring level and broker log destinations.
11. Create the cluster and wait for the ACTIVE state.

If choosing Express, verify Kafka version, broker size, 3 AZs, and required APIs/features. If choosing Serverless, select client subnets/VPCs and configure IAM access control per guidance.

### Step 3: Retrieve Bootstrap Brokers

Use the MSK console or API to obtain the bootstrap broker string matching your authentication mode. Never use an endpoint from another environment's cluster.

Example command to describe a cluster:

~~~bash
aws kafka describe-cluster \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN"
~~~

Replace `ap-southeast-1` and the ARN with your actual environment values. Bootstrap broker strings can be retrieved with the corresponding API such as `get-bootstrap-brokers`.

### Step 4: Configure Clients

With IAM authentication, Java clients can use the `AWS_MSK_IAM` mechanism and a compatible version of the `aws-msk-iam-auth` library.

Example `client.properties`:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=AWS_MSK_IAM
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required;
sasl.client.callback.handler.class=software.amazon.msk.auth.iam.IAMClientCallbackHandler
~~~

Clients need AWS credentials via IAM roles/profiles or a secure credentials provider. Never put long-lived access keys into configuration files.

### Step 5: Create Topics and Test Producers/Consumers

Use a Kafka CLI matching your Kafka version. Create topics according to your designed partition/replication policy, then send and read test events.

Verify:
- Clients connect to the right listener.
- TLS and authentication succeed.
- Producers receive acknowledgements.
- Consumers read records.
- Offsets are committed.
- Consumer groups behave properly.
- CloudWatch metrics appear.
- Broker logs arrive at the destination.

## 20. In-Place Upgrade from Standard to Express (Updated November 19, 2026)

Previously, the common approach to migrate a workload from Standard to Express was creating a new cluster and using MSK Replicator or MirrorMaker 2 to move topics and clients. On November 19, 2026, AWS announced **in-place upgrades** from Standard brokers to Express brokers for eligible MSK Provisioned clusters.

Because this is a recent capability, verify documentation and Region availability before planning. Not every Standard cluster is eligible for an in-place upgrade.

### 20.1 Prerequisites

Per the November 19, 2026 AWS announcement, the cluster must meet key requirements:

- MSK Provisioned running Standard brokers.
- Kafka version 3.9 and KRaft metadata mode.
- Cluster deployed across three Availability Zones.
- Tiered storage disabled.
- Broker instance type on the supported list.
- Partition count within Express quotas.
- Topic/broker configurations satisfying Express guardrails, including:
  - `replication.factor=3`
  - `min.insync.replicas=2`
  - `unclean.leader.election.enable=false`
  - `segment.ms` at least 60,000 ms
  - `max.message.bytes` not exceeding 8 MiB
  - `max.compaction.lag.ms` at least 24 hours

If the cluster is on an older Kafka version or ZooKeeper mode, upgrade to Kafka 3.9 and migrate to KRaft first. Execute step by step following AWS procedures, with rehearsals and proper backups/rollback plans.

### 20.2 Pre-Upgrade Assessment

AWS provides an assessment API to inspect broker/topic configurations before starting. For example:

~~~bash
aws kafka create-assessment \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-type UPDATE_BROKER_TYPE \
  --assessment-parameters TargetInstanceType=express.m8g.large
~~~

Capture the assessment ARN from the response, then describe the assessment and read findings:

~~~bash
aws kafka describe-assessment \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-arn "$ASSESSMENT_ARN"
~~~

~~~bash
aws kafka list-assessment-findings \
  --region ap-southeast-1 \
  --cluster-arn "$CLUSTER_ARN" \
  --assessment-arn "$ASSESSMENT_ARN"
~~~

ERROR-level findings are blockers that must be resolved. Review WARNING/INFO findings and document decisions before upgrading.

### 20.3 Starting the Upgrade

The workflow calls `UpdateBrokerType` with a target instance type and topic reassignment mode.

Two modes exist:
- `AUTO`: MSK manages migrating all topics to Express in batches.
- `MANUAL`: MSK adds Express brokers, and operations shifts topics in groups while verifying each step.

Example starting AUTO mode:

~~~bash
aws kafka update-broker-type \
  --cluster-arn "$CLUSTER_ARN" \
  --current-version "$CURRENT_VERSION" \
  --target-instance-type kafka.m7g.large-express.m8g.large \
  --topic-reassignment AUTO
~~~

Replace the example values with your actual current Standard instance, valid Express target, and cluster current version.

During the transition, Standard and Express brokers coexist. MSK moves partition replicas and leaders via Kafka procedures. Applications continue using the existing cluster endpoints; topic offsets are preserved per the AWS-documented upgrade flow.

### 20.4 Monitoring and Verification

Monitor:
- Cluster operation state.
- Topic reassignment progress.
- Broker types and partition counts on each broker.
- `PartitionCount`, `BytesInPerSec`, `BytesOutPerSec`.
- `LeaderCount` on Standard brokers.
- `ActiveControllerCount`.
- `OfflinePartitionsCount`.
- Producer/consumer throughput and latency.
- Consumer lag and stateful application health.

Once all topics have moved, validate applications for at least one full processing cycle. If issues arise, topics can be moved back to Standard while Standard brokers remain in the cluster.

### 20.5 Completion and Rollback Boundaries

Decommission Standard brokers only after confirming:
- All topics/partitions have moved completely.
- Producer/consumer throughput and latency meet baselines.
- Stateful applications operate normally.
- Zero offline partitions exist.
- Consumer groups and offsets are intact.
- Dashboards/alerts have been updated.

Once Standard brokers are decommissioned, rolling back to Standard is no longer an in-place operation. You must provision a new cluster and migrate data using MSK Replicator or another supported migration path.

While Standard and Express brokers coexist, both broker groups are billed. Express metrics differ from Standard; for example, replace `KafkaDataLogsDiskUsed` with `StorageUsed` and remove EBS metrics like `BurstBalance` from dashboards accordingly.

AWS reference:
[Announcing in-place upgrades from Standard brokers to Express brokers for Amazon MSK (19 Nov 2026)](https://aws.amazon.com/blogs/big-data/announcing-in-place-upgrades-from-standard-brokers-to-express-brokers-for-amazon-msk/)

## 21. Maintenance, Version Upgrades, and Operations

MSK manages many infrastructure tasks, yet clusters still require maintenance planning.

### 21.1 Kafka Versions

- Track end-of-support dates.
- Run MSK-supported versions compatible with clients.
- Read release notes prior to upgrading.
- Test plugins, Kafka Connect, Kafka Streams, and admin tooling.
- Rehearse on staging clusters.
- Maintain headroom for rolling restarts.
- Monitor partition availability, ISR, and consumer lag.

MSK may enforce version support policies and automatically upgrade end-of-support versions under published terms. Never leave production clusters on legacy versions without a plan.

### 21.2 Broker Maintenance and Client Resilience

Brokers can go offline during maintenance, patching, hardware failures, or network events. Kafka clients must:
- Include multiple bootstrap brokers.
- Retry with backoff and jitter.
- Refresh metadata.
- Reconnect after leader changes.
- Handle timeouts and duplicates.
- Avoid unbounded connection pools or connection storms.
- Monitor producer errors and consumer rebalances.

### 21.3 Cluster Configuration

MSK allows creating configuration revisions and applying them to clusters within supported broker type/version bounds. Express manages more settings with guardrails; Standard allows broader customization.

Never apply bulk production configuration changes without:
1. Backing up current configuration.
2. Assessing impact.
3. Testing on staging.
4. Applying during an appropriate window.
5. Monitoring metrics and errors.
6. Having a rollback plan.

## 22. Common Issues and Investigation Paths

| Symptom | Possible cause | Investigation path |
|---|---|---|
| Client timeout | Security group, routing, DNS, or broker endpoint | Check network path, ports, and bootstrap string |
| Authentication failed | Wrong IAM policy, secret, certificate, or listener | Verify auth mode, role, secret, and TLS |
| Producer throttling | Broker/client throughput quota or cluster saturation | Inspect BytesIn, request latency, CPU, and quotas |
| Rising consumer lag | Slow consumer, rebalance, or downstream failure | Inspect lag, processing time, and group membership |
| Offline partition | Insufficient replicas/ISR or broker/network failure | Check broker health, ISR, RF, and min ISR |
| Under-replicated partition | Followers falling behind leader | Check disk, network, CPU, and replication traffic |
| Disk nearing capacity (Standard) | Long retention, rising ingress, or undersized storage | Check retention, bytes in, storage autoscaling |
| Partition skew | Hot keys or skewed partition assignment | Analyze per-partition traffic and keys |
| Connection storm | Simultaneous client restarts or overly aggressive retries | Backoff/jitter, pool lifecycle, connection metrics |
| Continuous rebalancing | Consumer timeouts, slow processing, or rapid autoscaling | Check poll interval, heartbeats, and processing duration |
| Upgrade blocked | Incompatible version, quota, config, or partition count | Read assessment/operation findings |
| Express API not working | Kafka feature unsupported on Express | Check feature support matrix and version |

## 23. Production Design Checklist

- [ ] Average and peak workload ingress/egress defined.
- [ ] Topic, partition, replica, and consumer group counts determined.
- [ ] Partition keys designed to avoid hot partitions.
- [ ] Retention, replay, and compaction policies defined.
- [ ] Provisioned Standard, Provisioned Express, or Serverless selected with clear criteria.
- [ ] Kafka version and feature support verified.
- [ ] ZooKeeper or KRaft mode chosen appropriately for the version.
- [ ] Multi-AZ deployed per availability requirements.
- [ ] Replication factor and min ISR aligned with durability targets.
- [ ] Producers configured with appropriate retries, idempotence, and acknowledgements.
- [ ] Consumers handle offsets, retries, duplicates, and rebalances safely.
- [ ] Bootstrap broker string spans multiple AZs.
- [ ] VPC, subnets, routes, security groups, and DNS verified.
- [ ] IAM/SCRAM/mTLS chosen based on threat model and client support.
- [ ] Encryption at rest and in transit properly enabled.
- [ ] Secret/certificate management and rotation procedures established.
- [ ] Dashboards/alerts configured for CloudWatch metrics, broker logs, and consumer lag.
- [ ] Partition quotas, connection quotas, and service quotas verified.
- [ ] Broker throughput and client behavior benchmarked.
- [ ] Broker failures, AZ disruptions, and client reconnects rehearsed.
- [ ] Runbooks written for scaling, upgrades, failover, and recovery.
- [ ] Costs estimated for brokers, storage, data transfer, metrics, and retention.
- [ ] If upgrading Standard to Express, in-place prerequisites and rollback boundaries verified.

## 24. Practice Exercises

### Exercise 1: Choosing a Deployment Model

An application emits order events with heavily fluctuating campaign traffic. The team does not yet know exact peak throughput and does not need deep broker customization.

Task: propose an initial model and limits to check.

Suggested answer: try MSK Serverless if IAM-only access, quotas, and feature support fit. Benchmark throughput/partition, check Regional quotas, connections, and costs by data in/out/retention. If sustained high load or custom configs are needed, compare Provisioned Express/Standard.

### Exercise 2: Choosing Standard or Express

A streaming platform has high throughput, needs rapid scaling, and wants to minimize EBS management. Applications use standard Kafka APIs.

Answer: Provisioned Express is a strong candidate. Check three-AZ deployment, Kafka version, broker size, quotas, API support, and storage/throughput pricing. If applications rely heavily on the Kafka Streams API or specialized configs, verify feature support before committing.

### Exercise 3: Replication Factor

A critical topic runs on a three-AZ Standard cluster. The project team proposes RF=1 to save storage.

Task: analyze the risk.

Answer: RF=1 has no follower replicas; a broker or AZ failure can take partitions offline or cause data loss. AWS recommends RF of at least 3 for production Standard brokers; weigh durability against storage cost before deciding.

### Exercise 4: Choosing a Partition Key

Topic `orders` has traffic concentrated on one large customer. The team uses `customerId` as the key and observes one hot partition.

Answer: keying by customer preserves per-customer ordering, but a hot customer concentrates load. Clarify actual ordering requirements, consider finer keys like `orderId` or composite keys if business logic permits, and benchmark. Never change keys if doing so breaks required ordering.

### Exercise 5: Consumer Lag

A consumer group has 24 consumers, but the topic only has 12 partitions.

Answer: at any moment, at most 12 consumers in the group can be assigned partitions; the remaining consumers receive no partitions. Adding consumers does not increase parallelism unless partition count increases. Inspect per-record processing rate, partition design, and quotas.

### Exercise 6: Choosing Authentication

An ECS workload needs access to MSK Provisioned and the organization wants to avoid managing passwords.

Answer: IAM access control is a good fit if Kafka clients/drivers support it. Attach an IAM task role, write least-privilege IAM policies for topics/groups/cluster, and enable TLS. Verify Java/non-Java client version compatibility.

### Exercise 7: Serverless Quotas

MSK Serverless starts throttling during a sharp campaign throughput spike.

Answer: inspect aggregate and per-partition ingress/egress quotas, hot partitions, message sizes, connections, and request rates. Optimize keys/partitions, batching/compression, and request quota increases if warranted. Do not merely add consumers if the bottleneck is a partition leader or throughput quota.

### Exercise 8: Standard to Express

A Standard cluster runs Kafka 3.8, ZooKeeper mode, and tiered storage. The team wants an in-place upgrade to Express.

Answer: not yet eligible under the November 19, 2026 AWS announcement. You must upgrade to Kafka 3.9, migrate to KRaft, address tiered storage (clusters with tiered storage are not supported in the announced in-place flow), verify three-AZ topology, config guardrails, and partition quotas. Rehearse, run the assessment, and finalize only after applications are verified.

## 25. Self-Check Questions

1. How does Amazon MSK differ from self-managed Kafka on EC2?
2. What responsibilities does a broker have in a Kafka cluster?
3. How do topics and partitions differ?
4. Within what scope does Kafka guarantee ordering?
5. What are the roles of leader and follower replicas?
6. What is ISR?
7. What do `replication.factor=3` and `min.insync.replicas=2` achieve?
8. What are consumer groups and offsets used for?
9. How does ZooKeeper mode differ from KRaft mode?
10. How does MSK Provisioned differ from MSK Serverless?
11. How do Standard brokers differ from Express brokers in storage and configuration?
12. Why do Express clusters deploy across three AZs per current documentation?
13. When is tiered storage useful and what limitations should be noted?
14. Why can too many partitions cause overhead?
15. How does IAM access control differ from SASL/SCRAM and mTLS?
16. Does MSK Serverless support Kafka ACLs to authorize IAM identities?
17. How does MSK Connect differ from MSK Replicator?
18. Which components should be checked when consumer lag rises?
19. Which technology powers multi-VPC private connectivity?
20. What are the key prerequisites for the Standard-to-Express in-place upgrade announced on November 19, 2026?

Suggested answers:

1. MSK manages much of the broker/control-plane infrastructure; users still manage topics, clients, schemas, and workloads.
2. Receives requests, stores partitions/replicas, serves produce/fetch requests, and performs replication.
3. A topic is a logical stream; a partition is an ordered log within a topic.
4. Within each individual partition, not across an entire multi-partition topic.
5. Leaders accept writes and serve reads; followers replicate data.
6. The set of replicas currently in sync according to Kafka's criteria.
7. RF=3 creates three replicas; min ISR=2 requires at least two synchronized replicas to accept writes under that setting.
8. Groups divide partitions across consumers; offsets record read positions.
9. ZooKeeper uses external nodes to manage metadata; KRaft uses Kafka controllers.
10. Provisioned lets users choose broker capacity; Serverless manages compute/storage capacity automatically.
11. Standard uses user-managed EBS and flexible configs; Express uses managed storage and tighter guardrails.
12. It is Express's required topology per current AWS documentation.
13. Retains older data on a lower-cost tier; verify version, topic policies, and remote read latency.
14. Increases metadata, file handles, memory, recovery time, and rebalance overhead.
15. IAM uses IAM principals/policies; SCRAM uses usernames/passwords in Secrets Manager; mTLS uses client certificates.
16. Serverless requires IAM and does not support Kafka ACLs as an authorization mechanism.
17. Connect runs connectors integrating external systems; Replicator copies topics/metadata between clusters.
18. Consumer processing, partition assignments, rebalances, downstream systems, and brokers/networking.
19. AWS PrivateLink.
20. Provisioned Standard, Kafka 3.9 KRaft, three AZs, no tiered storage, configs/partitions/brokers meeting Express requirements, and zero blocker assessment findings.

## 26. Official References

- [What is Amazon MSK?](https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html)
- [Amazon MSK broker types](https://docs.aws.amazon.com/msk/latest/developerguide/broker-instance-types.html)
- [Amazon MSK Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-broker-types-standard.html)
- [Amazon MSK Express brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-broker-types-express.html)
- [What is MSK Serverless?](https://docs.aws.amazon.com/msk/latest/developerguide/serverless.html)
- [Amazon MSK quotas](https://docs.aws.amazon.com/msk/latest/developerguide/limits.html)
- [Best practices for Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/bestpractices.html)
- [Metadata management: ZooKeeper and KRaft](https://docs.aws.amazon.com/msk/latest/developerguide/metadata-management.html)
- [Supported Apache Kafka versions](https://docs.aws.amazon.com/msk/latest/developerguide/supported-kafka-versions.html)
- [IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control.html)
- [SASL/SCRAM authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password-howitworks.html)
- [Mutual TLS authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication.html)
- [Multi-VPC private connectivity](https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html)
- [Monitoring an MSK Provisioned cluster](https://docs.aws.amazon.com/msk/latest/developerguide/monitoring.html)
- [Tiered storage for Standard brokers](https://docs.aws.amazon.com/msk/latest/developerguide/msk-tiered-storage.html)
- [Amazon MSK FAQ](https://aws.amazon.com/msk/faqs/)
- [In-place upgrades from Standard to Express brokers (19 Nov 2026)](https://aws.amazon.com/blogs/big-data/announcing-in-place-upgrades-from-standard-brokers-to-express-brokers-for-amazon-msk/)

Amazon MSK features, broker sizes, Kafka versions, Region availability, API support, and quotas evolve over time. Before deploying, verify documentation for your exact Region/version and run performance, failure, and client compatibility tests against real workloads.
