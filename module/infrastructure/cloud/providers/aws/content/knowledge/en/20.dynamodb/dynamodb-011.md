# Global Tables and Multi-Region Conflict Resolution

> **Chapter:** DynamoDB  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem through Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless services. Learners develop skills to select services, design and deploy secure applications with observability, recovery, and cost control.

## Learning Objectives

After completing this lesson, learners can:

1. Explain **Amazon DynamoDB Global Tables** and the multi-Region table replica model.
2. Distinguish **Multi-Region Eventual Consistency (MREC)** from **Multi-Region Strong Consistency (MRSC)** in terms of replication, read/write semantics, latency, conflict handling, and limitations.
3. Explain MREC's **last writer wins (LWW)** mechanism and identify the risk of lost updates when multiple Regions write to the same item.
4. Choose the right write model: **write to any Region**, **write to one Region**, or **write to your Region**.
5. Design idempotency, optimistic concurrency, versioning, and data partitioning to minimize conflicts.
6. Understand how global tables affect **transactions, DynamoDB Streams, TTL, GSI/LSI**, and capacity.
7. Design application routing, failover, Region evacuation, RPO/RTO, and recovery testing.
8. Distinguish **same-account** and **multi-account global tables**, and manage IAM, service-linked roles, resource policies, and KMS.
9. Monitor **ReplicationLatency**, throttling, system errors, and replica status using CloudWatch/CloudTrail/CLI.
10. Estimate costs for replicated writes, storage, read capacity, indexes, backups, and multi-Region operations.

## 1. The Problem: Users Across Multiple Regions Modifying the Same Data

An e-commerce application serves customers in Vietnam, Singapore, Europe, and North America. If every request must call a single DynamoDB table located in one Region, distant users experience extra network latency and the system becomes heavily dependent on that single Region's availability.

**DynamoDB Global Tables** keeps replicas of the same table across multiple AWS Regions. The application in each Region can call its **local regional DynamoDB endpoint** to read and write data. DynamoDB automatically manages replication between replicas.

~~~mermaid
flowchart TB
    subgraph SG["ap-southeast-1"]
      APPSG["Orders API - Singapore"]
      DBSG[("Orders replica")]
      APPSG --> DBSG
    end
    subgraph JP["ap-northeast-1"]
      APPJP["Orders API - Tokyo"]
      DBJP[("Orders replica")]
      APPJP --> DBJP
    end
    subgraph EU["eu-west-1"]
      APPEU["Orders API - Ireland"]
      DBEU[("Orders replica")]
      APPEU --> DBEU
    end
    DBSG <-->|"Replication"| DBJP
    DBJP <-->|"Replication"| DBEU
    DBEU <-->|"Replication"| DBSG
~~~

The diagram shows the conceptual architecture. Each replica is a DynamoDB table in its own Region; clients do not send requests to a single "global endpoint" because DynamoDB **does not provide a global endpoint**. The application must decide which Region handles the request and call that Region's endpoint.

### 1.1. Why Are Global Tables Useful?

- **Lower access latency:** copies of data sit close to the application stack and users.
- **Business continuity:** traffic can be shifted to another Region when the current Region suffers an outage.
- **Multi-active:** multiple replicas can accept read/write requests, depending on the consistency mode and write model.
- **Operational isolation:** workloads, IAM, billing, and governance can be separated by Region/account.
- **Global scale:** reduces single-Region dependency for the data layer.

Global Tables improves data-layer availability, but **does not automatically create a complete multi-Region application**. Compute, APIs, authentication, DNS/routing, secrets, queues, observability, and deployments must also be provisioned and tested in standby Regions.

### 1.2. What Global Tables Does Not Solve Automatically

- Does not automatically pick the closest Region for users.
- Does not automatically reroute traffic when the application stack in a Region fails.
- Does not turn MREC into cross-Region strong consistency.
- Does not guarantee multi-item transactions are replicated atomically across Regions.
- Does not automatically resolve business conflicts when two users edit the same order concurrently.
- Does not replace backups, point-in-time recovery, data retention, or disaster recovery runbooks.
- Does not eliminate the need to design idempotency and handle duplicate requests.

## 2. Global Tables Versions: Current vs. Legacy

AWS has two historical versions:

| Version | Common name | Characteristics |
| --- | --- | --- |
| **2019.11.21** | Current / V2 | Uses an existing DynamoDB table and adds replicas via the `UpdateTable` API; supports more Regions, simpler operations, and typically saves write capacity. |
| **2017.11.29** | Legacy / V1 | Uses the separate `CreateGlobalTable` API; historically required creating compatible empty regional tables and linking them; has older Region limits and capacity accounting. |

For new designs, prefer **Global Tables version 2019.11.21 (Current)** as recommended by AWS.

### 2.1. Identifying the Version

For the current version, call **DescribeTable** in a replica's Region. The response includes **GlobalTableVersion = 2019.11.21**.

For the legacy version, a successful **DescribeGlobalTable** call for the global table name indicates the older model. If you do not verify the exact version, do not mix up V1 and V2 replica management procedures.

### 2.2. Why Version Affects Cost

For a 1 KB item and two Regions, AWS documentation illustrates that the Current version consumes fewer replicated write units than Legacy:

| Operation | Legacy 2017.11.29 | Current 2019.11.21 |
| --- | ---: | ---: |
| PutItem | 4 rWRUs total | 2 rWRUs total |
| UpdateItem | 3 rWRUs total | 2 rWRUs total |
| DeleteItem | 3 rWRUs total | 2 rWRUs total |

These figures assume a 1 KB item and two replicas; actual consumption depends on item size, operation, replica count, indexes, and billing mode. Do not apply these numbers directly to all requests or differently configured legacy tables.

### 2.3. Upgrading Legacy

If a system is using Legacy:

1. Verify the exact version via API/CLI.
2. Read the AWS upgrade procedure for version 2017.11.29.
3. Audit Streams, capacity, replica health, indexes, backups, and dependent applications.
4. Create a change plan, monitor replication, and validate after upgrading.
5. Do not simply spin up a new global table and delete old regional tables without a cutover and data reconciliation plan.

Upgrading the version is a control-plane operation with operational impact; follow AWS guidance and test in a staging environment first.

## 3. Two Consistency Modes: MREC and MRSC

When creating a Global Table, choose a consistency mode. If unspecified, the default is **MREC**. A global table cannot have replicas using different consistency modes and **cannot change its consistency mode after creation**.

| Criterion | **MREC — Multi-Region Eventual Consistency** | **MRSC — Multi-Region Strong Consistency** |
| --- | --- | --- |
| Replication | Asynchronous across Regions. | Synchronously replicated to at least one other Region before a write returns success. |
| Strong reads | Strongly consistent reads only guarantee the latest data at the local replica per DynamoDB semantics; does not guarantee seeing a write that just occurred in another Region. | Strongly consistent reads at any replica return the latest version on the global table. |
| Eventual reads | May not reflect a write recently acknowledged in another Region until replication completes. | Can be stale, even for very recent changes in the same or another Region. |
| Same-item conflicts | Resolved via **last writer wins** based on internal timestamps. | Conflicting writes may return **ReplicatedWriteConflictException** for the caller to retry. |
| Latency | Local writes/reads are typically lower; cross-Region replication happens in the background. | Writes and strongly consistent reads require cross-Region communication, resulting in higher latency. |
| Region count | Two or more Regions, expandable across supported Regions. | Exactly **3 Regions**: 3 replicas or 2 replicas + 1 witness. |
| Transactions | Atomic within the Region executing the transaction; not replicated atomically as a cross-Region transaction. | Does not support transaction APIs. |
| TTL | Supported; TTL deletes are replicated. | Does not support TTL deletion. |
| Streams | Enabled by default for replication and cannot be disabled on MREC replicas. | Does not use Streams for replication; Streams can be enabled separately where supported. |
| Multi-account | Supports multi-account model. | Supports same-account only. |
| RPO | Depends on replication lag; typically seconds, though there is no SLA for ReplicationLatency. | RPO of 0 for writes acknowledged as successful. |

### 3.1. Choosing a Mode Based on Business Requirements

Choose **MREC** when:

- A brief window before every Region sees the same change is acceptable.
- Low local write latency is prioritized.
- The application can designate a writer Region per item/data group or tolerate LWW.
- Single-Region transactions are needed and a primary Region can be coordinated.
- TTL or multi-account global tables are required.

Choose **MRSC** when:

- Strongly consistent reads and writes across replicas are critical requirements.
- The business cannot tolerate losing an acknowledged write when a Region fails.
- Higher latency for writes/strong reads due to cross-Region communication is acceptable.
- You do not depend on DynamoDB transactions or TTL.
- The data model fits the three-Region and witness constraints.

**Do not choose MRSC solely because "strong" sounds safer.** Compare latency, quorum availability, transactions, TTL, indexes, and cost against actual business requirements.

## 4. How Does MREC Work?

MREC uses an **active-active, asynchronous replication** model:

1. The application writes to the local replica, for example Singapore.
2. DynamoDB acknowledges the write based on conditions in the receiving Region.
3. DynamoDB reads changes from DynamoDB Streams and replicates them to the other replicas.
4. Each Region receives updates and eventually converges to the same data.
5. If a replica is temporarily unavailable, undelivered changes continue retrying once the replica recovers.

According to AWS documentation, a new item typically propagates to other replicas within about a second or less, though latency varies by Region pair, workload, and throughput. This is **not an SLA** and "one second" must not be treated as a guarantee for every request.

### 4.1. Per-Item Replication

Global Tables replicates **item by item**, not a group of items as a cross-Region transaction. Partitions also replicate in parallel; the arrival order of writes in a receiving Region can differ from the source Region.

For example, Region A commits two items in a transaction:

- Order item transitions to PAID.
- Payment summary increments total amount.

Region B might observe one item already replicated while the other has not yet arrived. The transaction was atomic in Region A, but **is not observed as an atomic transaction in Region B**.

### 4.2. Reading Data Before Replication Completes

Suppose a user updates their address in Singapore:

- The write is acknowledged in Singapore.
- Immediately afterward, an API in Tokyo reads the Tokyo replica.
- If replication has not arrived yet, Tokyo may return the old address.

This is normal MREC behavior. For **read-your-writes** requirements, the application can continue reading from the Region that performed the write for a window of time, or use write routing/homing so subsequent reads return to the appropriate Region.

### 4.3. What Does Strongly Consistent Read Mean in MREC?

DynamoDB supports Strongly Consistent Reads on a table or Local Secondary Index at each replica per standard service semantics. However, in MREC, a strong read in Tokyo only guarantees reading the latest data committed at the Tokyo replica; it does not force Tokyo to wait for all recent writes from Singapore to finish replicating.

**Strong consistency at one replica does not mean strong consistency across all Regions.**

### 4.4. No Partial Replication Within Table Scope

A global table replicates all items in the table to all participating Regions. You cannot configure a replica to hold only a subset of items by filtering on tenant or partition key.

If you need different data residency or replication scopes, consider splitting into multiple tables with separate Region sets, or adopting a different data architecture.

## 5. MREC Conflict Resolution: Last Writer Wins

Conflicts can occur when the same item is modified in two Regions before writes finish replicating across both.

Example:

- 10:00:00.100 — Singapore Region writes **shippingAddress = Hanoi**.
- 10:00:00.120 — Tokyo Region writes **shippingAddress = Da Nang**.
- The two writes occur close together before replication completes.

MREC uses **last writer wins (LWW)** based on the write operation's internal timestamp. The version deemed newer wins; the item eventually converges to that version.

~~~mermaid
sequenceDiagram
    participant SG as Replica Singapore
    participant JP as Replica Tokyo
    participant EU as Replica Europe
    SG->>SG: Update item: address = Hanoi
    JP->>JP: Update same item: address = Da Nang
    SG-->>JP: Replicate write from Singapore
    JP-->>SG: Replicate write from Tokyo
    SG-->>SG: Compare internal timestamps
    JP-->>JP: Compare internal timestamps
    SG-->>EU: Replicate winning version
    JP-->>EU: Replicate winning version
    Note over SG,EU: Replicas converge via last writer wins
~~~

### 5.1. LWW Is Not a Field-Level Merge

Do not assume DynamoDB automatically merges two updates to different attributes into a combined item.

For example, two Regions update the same item:

- Singapore changes `phoneNumber`.
- Tokyo changes `preferredLanguage`.

If the writes conflict on the same item, LWW can cause one item version to win and the other change to be lost. DynamoDB does not provide automatic semantic merging of business attributes.

### 5.2. Conflicts Are Not Logged as CloudWatch Alarm Events

LWW conflicts are resolved internally by the replication mechanism; they are not emitted as a separate conflict event type in CloudWatch or AWS CloudTrail.

Therefore, if the business needs to know when two users concurrently edited a record, the application must log it itself:

- Actor/user ID.
- Request/operation ID.
- Processing Region.
- Before and after versions.
- Business timestamp.
- Application-layer conflict/merge outcome, if any.

Do not wait for CloudTrail to report an "LWW conflict" during an investigation.

### 5.3. Why Timestamps Cannot Replace Business Versions

DynamoDB's internal timestamp serves service-level conflict resolution. It is not a business sequence an application can rely on to guarantee:

- An order only transitions along a valid workflow.
- A captured payment is never overwritten by a stale status.
- A record is not updated based on stale data a user read earlier.
- An auditable event is never lost.

Use **business versions**, conditional writes, event logs, or state machines whenever business ordering matters.

## 6. Indexes and Replica Structure

Replicas of the same global table must maintain the same **table name**, **primary key schema**, and item data. Global Tables does not allow each Region to define a different partition key for the same replication group.

### 10.1. Global Secondary Indexes

With Current Global Tables:

- When creating a GSI on one replica, DynamoDB creates the corresponding GSI on the other replicas.
- Index backfilling runs via the service mechanism.
- GSI definitions must stay consistent across replicas.
- Reads on GSIs are **eventually consistent**, even when the table uses MRSC.

Do not use a GSI to satisfy cross-Region strong read-after-write requirements. If strongly consistent reads are needed, read the base table or a Local Secondary Index within supported mode constraints.

### 10.2. Local Secondary Indexes

MREC supports LSIs under standard DynamoDB rules; LSIs must be defined at table creation time and share the same schema across replicas.

**MRSC does not support LSIs.** If the current data model relies on LSIs, redesign access patterns or choose MREC.

### 10.3. Table Attributes That Must Stay Synchronized

Replicas must share the same table name, primary key schema, and index definitions. With multi-account global tables, many settings are automatically synchronized across all replicas; do not assume you can override capacity mode or GSI schemas independently per account.

## 7. Same-Account and Multi-Account Global Tables

Global Tables supports two ownership models.

| Criterion | Same-account | Multi-account |
| --- | --- | --- |
| Ownership | One AWS account manages all replicas. | Each replica belongs to a separate AWS account. |
| Regions | Multiple Regions within the same account. | Each replica is in a different account and Region. |
| Consistency | MREC or MRSC. | MREC only. |
| IAM/KMS boundary | Same account boundary. | Separates IAM, KMS, billing, CloudTrail, and governance per account. |
| Control plane | Account owner manages adding/removing replicas. | Participating accounts join the replication group and grant replication permissions. |
| Use case | Centralized organizational governance. | Independent teams, business units, or account isolation requirements. |

### 11.1. Multi-Account Requirements

- Each replica must reside in a different AWS account; N replicas require N accounts.
- Multi-account global tables only support **MREC**.
- You must start with one regional table and add replicas in other accounts following the AWS workflow.
- Accounts must grant required permissions to the DynamoDB global tables service principal in resource policies.
- `GlobalTableSettingsReplicationMode` must be enabled for replicas so settings synchronize under the multi-account model.

### 11.2. Synchronized vs. Non-Synchronized Settings

Multi-account global tables synchronize many settings so all replicas behave consistently:

**Synchronized settings** include capacity mode, provisioned read/write capacity, auto scaling, LSI/GSI definitions, GSI capacity/auto scaling, Streams definition in MREC, TTL, warm throughput, and on-demand maximum throughput.

**Settings that do not synchronize automatically** and must be configured per replica include:

- Table class.
- Server-side encryption type and KMS key ID.
- Point-in-time recovery.
- Deletion protection and disassociation protection.
- Kinesis Data Streams destination.
- Tags and resource policies.
- CloudWatch Contributor Insights for table/GSI.

Therefore, adding a new replica does not automatically make all security/backup settings match the other Regions. Use IaC and check for drift per account/Region.

### 11.3. Security Boundaries and Account Responsibility

Multi-account creates a blast-radius boundary: if one account's credentials are compromised, an attacker does not automatically gain administrative access to all other accounts. However, replication can still be disrupted if resource policies, IAM, KMS, or Region opt-in are misconfigured.

Each account is responsible for securing its local replica, keys, IAM roles, logs, and costs. Do not treat multi-account as an automatic guarantee of data sovereignty or compliance.

## 8. Regional Endpoints and Request Routing

DynamoDB Global Tables **has no global endpoint**. An application in Region A should call Region A's DynamoDB endpoint to access its local replica. When Region A fails, the best recovery pattern is usually shifting **all requests to the application stack in Region B**, so that stack calls the local DynamoDB replica in B.

~~~mermaid
flowchart TB
    U["Users"] --> ROUTE["Client / Route 53 / Global Accelerator"]
    ROUTE --> SGAPI["API stack Singapore"]
    ROUTE --> JPAPI["API stack Tokyo"]
    SGAPI --> SGDB[("DynamoDB replica SG")]
    JPAPI --> JPDB[("DynamoDB replica Tokyo")]
    SGDB <-->|"Global Tables replication"| JPDB
~~~

### 12.1. Routing Strategies

| Strategy | How it works | Trade-offs |
| --- | --- | --- |
| **Client-driven** | Client chooses a regional API endpoint based on config/health/latency. | Client must know endpoints and failover logic. |
| **Compute-layer routing** | In-Region service decides whether to process locally or forward to the current primary Region. | Code must understand data topology and validate primary status. |
| **Route 53** | DNS failover/latency routing returns the regional application endpoint. | DNS TTL and OS/browser/app caches affect RTO. |
| **AWS Global Accelerator** | Anycast IPs route traffic over the AWS edge to the chosen regional endpoint. | Requires health/routing setup and incurs service cost. |

### 12.2. Do Not Call a Remote DynamoDB Endpoint as the Default Failover Pattern

A common anti-pattern is having the Singapore application hit a DynamoDB error and directly call the Tokyo DynamoDB endpoint while compute and supporting services remain in Singapore.

This introduces cross-Region latency, leaves other dependencies stranded in the impaired Region, and complicates routing control. AWS recommends deploying the application stack in multiple Regions and routing users to a healthy stack in another Region.

### 12.3. DNS TTL and Failover

Route 53 health checks/failover can switch endpoints, but clients and resolvers may cache DNS records. A 60-second TTL is often used as a reference point in failover designs, though not every client honors TTL strictly.

Actual RTO also depends on:

- Failure detection time.
- Time to update routing controls.
- DNS caching.
- Application warm-up/autoscaling.
- SDK/JDBC/HTTP client reconnects.
- Session/token continuity and downstream dependencies.

## 9. Disaster Recovery and Region Evacuation

Global Tables enables shifting workloads to another Region, though procedures differ by consistency mode and write model.

### 13.1. RPO and RTO

- **RPO (Recovery Point Objective):** maximum amount of data loss acceptable upon recovery.
- **RTO (Recovery Time Objective):** maximum time to restore service operation.

| Mode | RPO | RTO |
| --- | --- | --- |
| **MREC** | Depends on replication lag; typically seconds under normal conditions, though unreplicated writes may be delayed when a Region loses connectivity. | Depends on application routing, compute, DNS, dependencies, and failover procedures. |
| **MRSC** | **0 for writes acknowledged as successful**. | Not zero; requires time to shift traffic/compute and may depend on quorum availability. |

### 13.2. Evacuating a Healthy Region with MREC

If Region A is still healthy and you need to move primary to Region B:

1. Block or pause new writes to A.
2. Wait for accepted writes to propagate to B.
3. Use `ReplicationLatency` to estimate wait time.
4. AWS Prescriptive Guidance notes that when A is healthy, waiting roughly **10 times the recent maximum ReplicationLatency** is typically sufficient to assume replication has drained; this is a heuristic, not absolute proof.
5. Switch routing/control plane so B becomes the writable Region.
6. Confirm A no longer receives writes, then open writes in B.
7. Monitor for duplicates, stale writes, and run business reconciliation.

No single metric proves with 100% certainty that every write from A has finished replicating. Combine write pausing, stream/checkpoints, event sources, and business invariants.

### 13.3. Sudden MREC Region Outage

If A loses connectivity completely:

- Writes acknowledged in A but not yet propagated will not yet exist in B.
- DynamoDB retains pending replication and resumes when A recovers.
- If the application keeps writing in B, new writes to the same item may overwrite older pending writes from A under LWW.
- When A returns, replication resumes; however, business state may need reconciliation if operations were not idempotent.

Application strategies to consider:

- Continue operating with write-to-any-Region for idempotent data, accepting temporary missing state.
- Quarantine accounts/orders potentially missing transactions.
- Replay operations from an upstream event log when source data has not propagated, provided operations are idempotent and carry business operation IDs.
- Partition balances/ledgers into home Regions to bound blast radius.
- Reconcile against sources of truth before letting a financial workflow proceed.

**Do not assume MREC failover has zero data loss.** If the old Region is lost permanently with unreplicated writes, RPO depends on records acknowledged elsewhere or an independent event/backup source.

### 13.4. MRSC Region Offline

MRSC has RPO = 0 for successful writes. When one Region goes offline:

- Remaining Regions can continue if quorum/replica availability requirements are met.
- When the Region returns, DynamoDB catches it up automatically.
- During catch-up, writes and strongly consistent reads against the recovering replica may return errors.
- Remaining Regions continue serving based on quorum availability.

Do not manually recreate tables or copy data just because an MRSC replica is still catching up.

### 13.5. Failover Is More Than Swapping an Endpoint

Before production, test the entire application stack:

- API Gateway/ALB, Lambda/ECS/EC2, and autoscaling.
- IAM roles, Secrets Manager, KMS keys, and VPC endpoints.
- Cognito/identity/session continuity.
- SQS/EventBridge/Step Functions or dependent event sources.
- Local DynamoDB endpoint and regional capacity.
- DNS/Global Accelerator/ARC routing.
- Idempotency, duplicate requests, and business reconciliation.

## 10. IAM, Service-Linked Roles, and KMS

### 14.1. Service-Linked Role for Replication

DynamoDB uses the service-linked role:

**AWSServiceRoleForDynamoDBReplication**

DynamoDB creates this role automatically when an account creates its first global table if the caller has **iam:CreateServiceLinkedRole**. This role allows the service to manage cross-Region replication.

If an IAM resource policy or explicit Deny accidentally blocks the replication service-linked role's permissions:

- Replication can stop.
- The replica can transition to **REPLICATION_NOT_AUTHORIZED**.
- With MREC, if this state persists for more than 20 hours, the replica can be permanently converted into a standalone regional table.
- With MRSC, denying permissions can cause writes/strongly consistent reads to return `AccessDeniedException`; prolonged denial can render the replica inaccessible per AWS limits.

When authoring strict SCPs/resource policies, ensure they do not accidentally block DynamoDB's service-linked role.

### 14.2. IAM Permissions for the Control Plane

Creating a global table or adding a replica may require permissions such as:

- **dynamodb:UpdateTable** on the source table.
- **dynamodb:CreateTable** and **dynamodb:CreateTableReplica** in added Regions.
- Table read/write permissions required by the service to establish replication per documentation.
- **iam:CreateServiceLinkedRole** when creating the role for the first time.
- **dynamodb:CreateGlobalTableWitness** when creating MRSC with a witness.

Permissions must be scoped to exact table ARNs, Regions, and operations. Never grant **dynamodb:\*** across all Regions just to deploy a global table.

### 14.3. Resource Policies and Multi-Account

For multi-account global tables, customers must grant replication permissions to the **DynamoDB global tables service principal** in replica resource policies per AWS guidance.

When editing a resource policy, check:

- Allowed service principal.
- Required actions for replication.
- Appropriate account/Region conditions.
- Explicit Denies from identity policies, SCPs, or resource policies.
- That the service-linked role is not blocked.

A replica may still serve local reads/writes in some scenarios even while cross-account replication has stalled; monitor status/latency to detect this.

### 14.4. Encryption at Rest and KMS

Every DynamoDB replica encrypts data at rest using KMS. Replicas in the same global table must use the **same KMS key type** per service requirements:

- AWS owned key.
- AWS managed key.
- Customer managed key.

With customer managed keys:

- The key policy must allow DynamoDB to use the key.
- Do not disable/delete the key before the replica has been properly removed.
- Revoking decrypt permissions can halt replication and put the replica into an inaccessible encryption credentials state.
- Key IDs/keys can be configured separately per account/Region in multi-account setups, provided they adhere to the same key type and policy requirements.

**Do not delete a KMS key just to decommission a replica.** Remove the replica via the proper procedure first, wait for required table statuses, and only then consider disabling/deleting the key.

## 11. Capacity Planning and Throttling

Global Tables requires capacity for both **application writes and replicated writes**. A write in one Region generates replicated write consumption in the other Regions.

### 15.1. Provisioned Capacity

- Replication consumes write capacity on replicas.
- If application writes + replication writes exceed write capacity, the replica can throttle.
- With global table provisioned mode, write auto scaling settings synchronize across Regions; actual provisioned levels can scale independently per Region.
- Read capacity can be configured differently across Regions to match local read demand in same-account mode.
- Reserve headroom for failover traffic when one Region absorbs load from elsewhere.

Do not size solely for direct writes into one Region. During failover, a Region may absorb far more writes/reads than its normal baseline.

### 15.2. On-Demand Capacity

With on-demand:

- DynamoDB automatically adjusts throughput to traffic.
- Write settings/max throughput have synchronization rules across replicas.
- On-demand has no provisioned capacity target but still has table-level maximum throughput limits and quotas.
- A failover surge can burst differently from baseline; load test and verify account/table quotas.

### 15.3. GSIs and Replicated Writes

GSI updates consume capacity separately per DynamoDB rules. With Global Tables, writing to the base table and updating GSIs can create substantial write consumption in every Region.

A write pattern triggering heavy GSI updates can throttle a replica even when base table capacity looks sufficient. Monitor the base table and each GSI separately.

### 15.4. Hot Partitions and Hot Keys

Replication does not eliminate partition throughput limits. If all Regions update the same hot item or partition key:

- Write contention increases.
- A single item becomes a hotspot.
- MREC faces LWW conflict risks.
- MRSC can raise `ReplicatedWriteConflictException` on concurrent writes.
- GSI partition keys can also become hot keys.

Consider sharding, write distribution, item decomposition, and home Region ownership.



## 12. Choosing a Write Model to Control Conflicts

Even though Global Tables is multi-active at the service layer, the application must still define **who is allowed to write which item and in which Region**. AWS Prescriptive Guidance describes three main write models.

### 6.1. Write to Any Region — No Primary

Every Region can accept writes to the same data.

Suitable for:

- **MRSC**, when the application needs writes from any Region and handles retries on `ReplicatedWriteConflictException`.
- **MREC** if all writes are idempotent or conflicts are acceptable.

Appropriate MREC example: a user sets a bookmark position to an absolute value, e.g., `latestPosition = 25`. If the same request is retried, it does not add to the position again.

Risky MREC example: updating a balance with `ADD 100`. If two Regions both add against unsynchronized copies, LWW can cause one update to be overwritten.

### 6.2. Write to One Region — Application-Managed Primary

The application routes **all writes** to a single active Region. Other Regions serve eventual reads and stand ready to become primary on failover.

Suitable for MREC when:

- Conditional writes based on the latest data are needed.
- `TransactWriteItems` or `TransactGetItems` are required.
- Business logic performs additions/subtractions, state transitions, or non-idempotent updates.
- You want simpler conflict resolution by avoiding multi-Region concurrent writes.

DynamoDB has no built-in automatic global primary Region concept. **The application or an orchestration layer** must track which Region currently holds write permission, update routing, and prevent split-brain during primary failover.

Strongly consistent reads must be executed in the Region currently handling writes if the application needs to read those updates immediately.

### 6.3. Write to Your Region — Each Item Has a Home Region

Partition data into non-overlapping subsets, each owned for writes by a single Region.

Example:

- Users with IDs in shard A are assigned home Region Singapore.
- Users in shard B are assigned home Region Tokyo.
- Each item is updated only in its home Region, while copies can be read elsewhere per consistency needs.

Ways to determine home Region:

- **Intrinsic:** the Region code is embedded in the partition key or an item attribute.
- **Negotiated:** a coordination service issues time-bounded assignments.
- **Table-oriented:** create separate global tables per Region/home-Region group.

This model reduces conflicts and keeps write latency low for global users. However, during failover, item ownership must be transferred while ensuring the old Region stops writing.

### 6.4. Comparing the Three Write Models

| Write model | MREC | MRSC | When to use |
| --- | --- | --- | --- |
| **Write to any Region** | Suitable only if writes are idempotent or LWW is acceptable. | Suitable; still must retry write conflicts. | Bookmarks, idempotent state overwrites, independent metadata. |
| **Write to one Region** | Suitable for transactions, conditional writes, and non-idempotent operations. | Can be chosen to simplify routing, though MRSC permits multi-Region writes. | Ledgers, state workflows, data needing a single writer. |
| **Write to your Region** | Suitable for data partitioned by user/tenant. | Not needed to prevent LWW, though usable for architectural reasons. | User profiles, sessions, or data with a home Region. |

**Do not pick write to any Region for every data type just because the API allows it.** Classify each aggregate: which data can be overwritten, which needs a single writer, and which requires strong consistency.

## 13. MRSC: Strong Consistency Across Replicas

**Multi-Region Strong Consistency (MRSC)** changes global table semantics:

1. The application writes to one replica.
2. DynamoDB synchronously replicates the change to at least one other Region in the topology before returning write success.
3. A strongly consistent read at any replica returns the latest version.
4. Conditional writes evaluate against the latest version.
5. If the same item is being modified in another Region, the write may be rejected with **ReplicatedWriteConflictException**.

~~~mermaid
sequenceDiagram
    participant SG as Replica Singapore
    participant JP as Replica Tokyo
    participant EU as Replica witness/replica
    SG->>JP: Synchronously replicate write
    JP-->>SG: Quorum/ack per service mechanism
    SG-->>APP: Write succeeds
    APP->>JP: Strongly consistent read
    JP-->>APP: Latest version
~~~

This diagram is a conceptual model and does not depict DynamoDB's internal quorum protocol details.

### 7.1. Three Required Regions

MRSC requires **exactly three Regions** in one of two topologies:

- **Three full replicas:** each Region has a readable/writable replica.
- **Two replicas + one witness:** two Regions host table replicas, and the third Region hosts a DynamoDB-managed witness.

Witness:

- Participates in the consistency/quorum architecture.
- Has no table endpoint for applications to read or write.
- Does not appear as a customer-managed DynamoDB table in the account.
- Incurs no storage or replicated write costs like a full replica.
- Resides in a different Region from the two full replicas.

You cannot add a fourth replica to an existing MRSC table. Adding/removing replicas or witnesses is tightly constrained; design the topology upfront and review AWS lifecycle procedures before making changes.

### 7.2. Current Region Support

As of **20/11/2026**, AWS has announced MRSC support across 15 Regions:

- **North America:** US East (N. Virginia), US East (Ohio), US West (Oregon), Canada (Central).
- **Europe:** Europe (Ireland), Europe (London), Europe (Paris), Europe (Frankfurt), Europe (Stockholm), Europe (Spain).
- **Asia Pacific:** Asia Pacific (Tokyo), Asia Pacific (Seoul), Asia Pacific (Osaka), Asia Pacific (Mumbai), Asia Pacific (Singapore).

Since **23/09/2026**, AWS expanded MRSC to allow choosing any combination of three Regions from those 15 supported Regions, including cross-continental configurations across North America, Europe, and Asia Pacific. Support may continue evolving; always check AWS documentation before choosing Regions.

### 7.3. Latency and Quorum

MRSC requires inter-Region communication for writes and strongly consistent reads. Consequently:

- Write latency is higher than an MREC local write.
- Strongly consistent read latency also increases by the round-trip to the nearest participating Region.
- Eventually consistent reads do not incur the extra cross-Region latency under MRSC semantics.
- If no second Region is available to form quorum, the remaining Region can only serve eventually consistent reads; writes and strongly consistent reads cannot proceed normally.

**RPO of 0 does not mean RTO of 0.** Applications still need routing, standby compute stacks, DNS, authentication, quotas, and recovery runbooks.

### 7.4. ReplicatedWriteConflictException

When two Regions attempt to modify the same item nearly simultaneously, one write may be temporarily rejected. The application should:

1. Identify the specific error rather than blindly retrying `ValidationException`/`AccessDenied`.
2. Use exponential backoff and jitter.
3. Preserve an idempotency key for the business operation.
4. Re-read the latest state if business logic depends on current state.
5. Recompute the update from the new version, then retry.
6. Cap retry attempts and return a controlled error if conflicts persist.

Do not blindly retry a payment charge or order creation without an idempotency key; retries can cause duplicate business side effects.

### 7.5. Key MRSC Limitations

| Feature | MRSC |
| --- | --- |
| Transactions (TransactWriteItems/TransactGetItems) | **Not supported**. |
| TTL deletion | **Not supported**. |
| Local Secondary Index (LSI) | **Not supported**. |
| Global Secondary Index (GSI) | Supported; GSI reads are eventually consistent. |
| DynamoDB Streams | Not used as the replication engine and not enabled by default; Streams can be enabled separately where supported. |
| Multi-account global table | **Not supported**, same-account only. |
| ReplicationLatency metric | Not emitted for MRSC. |

### 7.6. When a Region Recovers After an Outage

MRSC automatically catches up data for the recovering Region. Before it finishes catching up, writes and strongly consistent reads against the recovering replica may return errors; the remaining healthy Regions continue processing under quorum.

Do not attempt to recreate the table or manually copy data just because an MRSC replica is catching up.

Do not try to switch to MREC by flipping a setting on an existing table. Consistency mode cannot be changed after creation.

## 14. Data Modeling to Avoid Conflicts

Global Tables does not replace data modeling. How you split items determines the blast radius of conflicts.

### 8.1. Separate Independently Updated Attributes

If multiple user groups or services update different parts of the same profile, split them into separate items:

~~~text
PK = USER#1001, SK = PROFILE
PK = USER#1001, SK = CONTACT
PK = USER#1001, SK = PREFERENCES
PK = USER#1001, SK = NOTIFICATION_SETTINGS
~~~

If Singapore only updates `CONTACT` and Tokyo only updates `PREFERENCES`, they write to different items and avoid LWW conflicts on the same item.

Trade-off: reading the full profile may require multiple items/`Query`, and multi-item transactions still carry per-Region replication semantics.

### 8.2. Prefer Absolute Assignment Over Increments in MREC

Retry-friendly / idempotent examples:

~~~text
SET latestViewedPosition = 125
SET notificationEnabled = true
SET deliveryStatus = "SHIPPED"
~~~

Conflict-prone examples if written to the same item from multiple Regions:

~~~text
ADD walletBalance : 100
ADD totalOrderCount : 1
SET inventory = inventory - 1
~~~

In MREC, operations based on the local replica's current value can overwrite each other when two Regions update concurrently. When exact arithmetic is required:

- Use a **single-writer Region** for the item/ledger.
- Write append-only event/ledger records with unique operation IDs.
- Use MRSC if suitable and transactions/TTL are not required.
- Or redesign the data model to preserve invariants.

### 8.3. Use Unique Deterministic Keys for Append-Only Data

A new event can be stored under a deterministic key derived from the operation ID:

~~~json
{
  "PK": "ORDER#10023",
  "SK": "EVENT#PAYMENT#TXN-2026-00091",
  "eventType": "PaymentCaptured",
  "operationId": "TXN-2026-00091",
  "amount": 125000,
  "currency": "VND",
  "originRegion": "ap-southeast-1"
}
~~~

If the same operation is retried across Regions with the same primary key, the application can use a conditional `PutItem` to avoid creating two records in a single replica. However, in MREC, the condition is evaluated only on the receiving replica and does not replace a global transaction; routing and idempotency design remain essential.

### 8.4. Optimistic Concurrency with Business Versions

An item can contain:

~~~json
{
  "PK": "ORDER#10023",
  "status": "PAID",
  "version": 8,
  "updatedBy": "billing-service",
  "updatedAt": "2026-11-20T03:00:00Z"
}
~~~

The application reads version 8 and writes only if the current version is still 8. On success, it increments to version 9. This is **optimistic concurrency control (OCC)**.

- With **MREC**, OCC only guards against the local replica's state. If two Regions both read version 8, both can accept the conditional write locally before replication arrives. Use home Region/single writer or another coordination mechanism to guarantee exclusivity.
- With **MRSC**, the condition evaluates against the latest global version; concurrent writes may receive `ReplicatedWriteConflictException` and must retry/re-read.

### 8.5. Do Not Use Application Clocks to Simulate LWW

Do not attach a client timestamp and assume the largest timestamp wins correctness. Client clocks drift, requests arrive late, and business order does not necessarily match wall-clock time.

If auditing or business ordering is needed, store a **domain-service-managed sequence/version**, operation ID, and origin metadata.

## 15. Transactions, Streams, and TTL on Global Tables

### 9.1. Transactions on MREC Are Atomic Only Within the Source Region

MREC supports DynamoDB transaction APIs under standard DynamoDB limits, but transactions are atomic only in the Region where the request executes.

Example `TransactWriteItems`:

1. Update Order status = PAID.
2. Write Payment record.
3. Decrement Inventory.

In the source Region, all three operations succeed or fail as a single transaction. When replicated to other Regions, each item propagates independently; a read in a receiving Region may observe partial updates before all items arrive.

If the application requires remote Regions never to expose an incomplete state, use a **commit marker/version** or a read-projection pattern that publishes state only once all records are present; do not assume transactions replicate atomically.

### 9.2. MRSC Does Not Support Transaction APIs

MRSC does not support **TransactWriteItems** or **TransactGetItems**. If your application depends on multi-item transactions, MRSC may be unsuitable even if you want per-item strong consistency.

Consider:
- MREC with a single-writer Region for transactional aggregates.
- Splitting aggregates and using workflows/outbox/sagas.
- Using another datastore if strong transactions across multiple records/Regions are mandatory.

### 9.3. DynamoDB Streams with MREC

MREC uses DynamoDB Streams as its replication mechanism:

- Streams are enabled by default on replicas and cannot be disabled while a table is an MREC global table.
- Each replica has its own stream.
- A stream can contain changes originating in that Region as well as replicated changes.
- Per-item change order is preserved per Streams semantics; relative order between different items may differ across replicas.
- Replication may coalesce closely spaced changes into a single replicated write; stream records across replicas are not necessarily identical.

If you want to process only local-origin writes, add an **originRegion** attribute to the item/event and filter Stream records in Lambda. Do not rely solely on stream names to distinguish origin.

### 9.4. DynamoDB Streams with MRSC

MRSC does not use Streams for replication, so Streams is not enabled by default. You can enable Streams on a replica where supported; per documentation, stream records across MRSC replicas have the same content and order.

Do not assume Streams serves as the replication bus for MRSC.

### 9.5. TTL on MREC

MREC supports TTL:

- The TTL attribute name configuration is synchronized across replicas.
- When TTL deletes an item in one Region, the delete is replicated to the other Regions.
- The TTL delete in the originating Region consumes no write capacity under TTL mechanics.
- Receiving replicas still consume replicated write capacity for replicated deletes.
- If provisioned capacity is low, normal writes plus TTL deletes can trigger throttling.

### 9.6. No TTL on MRSC

MRSC does not support TTL deletion. If the application depends on automatic expiry, design cleanup using another mechanism with clear idempotency and routing, or choose MREC.

## 16. Monitoring Global Tables

Monitoring Global Tables should be split into two areas:

1. **Replication health:** is data propagating between Regions on schedule?
2. **Table/application health:** is any replica experiencing throttling, errors, high latency, or capacity issues?

### 16.1. ReplicationLatency on MREC

The CloudWatch metric **ReplicationLatency** is emitted for MREC Global Tables:

- Unit: **milliseconds**.
- Tracks the elapsed time from when an item is written at the source replica to when it appears at the receiving replica.
- Dimensions include **TableName** and **ReceivingRegion**; queried in the source Region for a specific destination Region pair.
- Useful statistics: **Average, Minimum, Maximum**.
- There is no SLA on ReplicationLatency.

Values vary by geographic distance, workload, throughput, and replication state. Do not hardcode a threshold like "always under 1 second" across every Region pair.

**MRSC does not emit ReplicationLatency**, because its synchronization mechanism differs from MREC. Do not treat the missing metric as broken MRSC replication.

### 16.2. DynamoDB Metrics to Monitor Per Replica

| Metric | Meaning | Used for |
| --- | --- | --- |
| **ConsumedReadCapacityUnits** | Consumed read capacity. | Observing read workload per table/index. |
| **ConsumedWriteCapacityUnits** | Consumed write capacity. | Detecting write pressure and replication load. |
| **ReadThrottleEvents** | Number of throttled read events. | Detecting insufficient read capacity/quotas/hot partitions. |
| **WriteThrottleEvents** | Number of throttled write events. | Detecting write capacity bottlenecks or hot keys. |
| **ThrottledRequests** | Requests throttled across supported dimensions. | Measuring impact on the application. |
| **SuccessfulRequestLatency** | Latency of successful requests by operation. | Comparing latency across Regions. |
| **SystemErrors** | HTTP 500 errors from DynamoDB/Streams. | Investigating service errors and retries. |
| **UserErrors** | Client/request errors per metric definition. | Auditing validation, access, or request patterns. |
| **ConditionalCheckFailedRequests** | Conditional writes failed because condition was unmet. | Analyzing optimistic concurrency / business contention. |
| **OnlineIndexConsumedWriteCapacity** | Capacity consumed during index creation/backfill per metric support. | Tracking GSI impact. |

Some metrics require specific dimensions. For example, **SystemErrors** requires both **TableName** and **Operation**; an alarm filtering only on TableName may miss datapoints. Verify CloudWatch metric dimensions before creating alarms.

### 16.3. CloudWatch Contributor Insights

Contributor Insights helps identify partition keys/top contributors driving heavy load or throttling. For MRSC, AWS notes that Contributor Insights data is reported only in the Region where the operation occurred. Do not treat one Region's report as a global aggregate.

### 16.4. Application-Level Metrics to Emit Yourself

DynamoDB does not know whether a write is business-valid. Applications should emit metrics/logs for:

- Processing Region and the item's home Region.
- Business operation ID, aggregate version, and idempotency outcome.
- Conditional check failures.
- `ReplicatedWriteConflictException` and retry counts.
- Read-after-write fallbacks.
- Failover routing decisions and Region switch timestamps.
- Reconciliation backlog, quarantined records, and duplicate operations.

Do not write raw PII or full item payloads to CloudWatch logs solely to measure conflicts.

### 16.5. CloudTrail and Data Conflicts

CloudTrail is useful for auditing **control-plane changes**, such as `UpdateTable`, replica add/remove, resource policy, and IAM changes. Enabling DynamoDB data events in appropriate scope can audit certain data-plane API calls.

However, LWW conflict resolution does not create a dedicated CloudTrail event. Use application logs / business event logs to track actors and business conflicts.

## 17. Read-Only AWS CLI: Inspecting Global Tables

The commands below only query state; they do not create replicas, alter policies, write items, or change capacity. Use an authorized AWS profile/role in the right Region.

### 17.1. Verify AWS Account and Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Do not confuse the CLI's AWS caller identity with an application end user. Global Tables replicas are accessed by the workload's IAM principal, not a Cognito end user.

### 17.2. View Replicas and Current Version

~~~bash
aws dynamodb describe-table \
  --table-name orders \
  --region ap-southeast-1
~~~

Inspect fields:

- **TableStatus**.
- **GlobalTableVersion**.
- **Replicas[].RegionName**.
- **Replicas[].ReplicaStatus** and `ReplicaStatusDescription`.
- **GlobalTableWitnesses** if present in the response.
- `BillingModeSummary`, `ProvisionedThroughput`, `GlobalSecondaryIndexes`, and `StreamSpecification`.

Run `DescribeTable` in each Region to verify replica status/ARN. Do not check only the source table and assume all replicas are `ACTIVE`.

### 17.3. Check Legacy Version

~~~bash
aws dynamodb describe-global-table \
  --global-table-name orders \
  --region ap-southeast-1
~~~

This command is for **Legacy 2017.11.29**. If it returns `GlobalTableNotFoundException`, the table is likely not a legacy global table; use `DescribeTable` to inspect the current version.

### 17.4. View Auto Scaling and TTL

~~~bash
aws dynamodb describe-table-replica-auto-scaling \
  --table-name orders \
  --region ap-southeast-1

aws dynamodb describe-time-to-live \
  --table-name orders \
  --region ap-southeast-1
~~~

With MREC, TTL settings synchronize. With MRSC, TTL is not supported. Inspect each Region and remember that replica-level read auto scaling can be configured differently per Region.

### 17.5. View Continuous Backups/PITR

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name orders \
  --region ap-southeast-1
~~~

PITR/backups are configured per replica in that Region; in multi-account global tables, do not assume these settings synchronize automatically. Verify critical replicas and restore plans.

### 17.6. Read ReplicationLatency

Example retrieving `ReplicationLatency` in source Region Singapore for the receiving replica in Tokyo:

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ReplicationLatency \
  --dimensions Name=TableName,Value=orders Name=ReceivingRegion,Value=ap-northeast-1 \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 60 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

Notes:

- Applies to MREC only.
- The **ReceivingRegion** dimension is the receiving Region; the source Region is determined by the Region where you query the metric.
- The time range is an illustrative UTC window; substitute the incident window.
- Datapoints may not be sorted by timestamp.
- Missing datapoints can mean no writes occurred, wrong dimensions/Region, or metrics not yet emitted; do not conclude replication is broken from a single query.

### 17.7. Read Table Throttling and System Errors

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name WriteThrottleEvents \
  --dimensions Name=TableName,Value=orders \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Sum \
  --region ap-southeast-1
~~~

For **SystemErrors**, you must specify the dimension pair `TableName` + `Operation` per the metric definition; do not omit `Operation` and assume an alarm will receive data.

### 17.8. Read CloudTrail Control-Plane Changes

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateTable \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --region ap-southeast-1
~~~

You can look up replica/configuration changes during an incident window. CloudTrail lookup does not replace replication metrics or application logs; event history/retention also has CloudTrail limits.

### 17.9. Mutating Commands Not to Run in This Lesson

Do not execute the following commands in a read-only lab:

~~~text
aws dynamodb update-table
aws dynamodb create-global-table
aws dynamodb update-global-table
aws dynamodb delete-table
aws dynamodb update-time-to-live
aws dynamodb update-continuous-backups
aws dynamodb put-resource-policy
aws dynamodb delete-resource-policy
aws dynamodb update-item
aws dynamodb put-item
~~~

These operations modify data, replication, backups, permissions, or cost. Run them only in a dedicated sandbox or through a reviewed IaC/change process.

## 18. Java SDK v2: Calling the Local Replica and Handling Conditional Writes

A Java application should instantiate its DynamoDB client pointing to the **application stack's Region**. Never hard-code a global endpoint; Global Tables has no such endpoint.

### 18.1. Creating a Regional Client

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class DynamoClients {
    private DynamoClients() {}

    public static DynamoDbClient forSingapore() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

Illustrative example. In production, retrieve Region from deployment configuration/environment; obtain IAM credentials via the AWS SDK default credential provider chain (task role, execution role, or workload identity) rather than committing access keys.

### 18.2. Conditional Update Using Business Version

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import java.util.Map;

public final class OrderStateRepository {
    private final DynamoDbClient dynamoDb;
    private final String tableName;

    public OrderStateRepository(DynamoDbClient dynamoDb, String tableName) {
        this.dynamoDb = dynamoDb;
        this.tableName = tableName;
    }

    public void markPaid(String orderId, long expectedVersion) {
        var request = UpdateItemRequest.builder()
            .tableName(tableName)
            .key(Map.of(
                "PK", AttributeValue.builder().s("ORDER#" + orderId).build(),
                "SK", AttributeValue.builder().s("STATE").build()
            ))
            .updateExpression("SET #status = :paid, #version = :next")
            .conditionExpression("#version = :expected")
            .expressionAttributeNames(Map.of(
                "#status", "status",
                "#version", "version"
            ))
            .expressionAttributeValues(Map.of(
                ":paid", AttributeValue.builder().s("PAID").build(),
                ":expected", AttributeValue.builder().n(Long.toString(expectedVersion)).build(),
                ":next", AttributeValue.builder().n(Long.toString(expectedVersion + 1)).build()
            ))
            .build();

        try {
            dynamoDb.updateItem(request);
        } catch (ConditionalCheckFailedException staleVersion) {
            throw new IllegalStateException(
                "Order state changed; reload and re-evaluate the operation",
                staleVersion
            );
        } catch (DynamoDbException serviceError) {
            if ("ReplicatedWriteConflictException".equals(serviceError.awsErrorDetails() == null
                    ? null : serviceError.awsErrorDetails().errorCode())) {
                throw new IllegalStateException(
                    "Concurrent write in another Region; retry with backoff",
                    serviceError
                );
            }
            throw serviceError;
        }
    }
}
~~~

This is a learning example assuming a table with partition key `PK`, sort key `SK`, and an item carrying a `version` attribute. Production code must add safe logging, retry policies, timeouts, idempotency, and HTTP error mapping appropriate for the application.

### 18.3. Warning When Using This Example with MREC

With MREC, the conditional expression evaluates against the state of the **replica receiving the request**. Two Regions can simultaneously see version 8 and both accept an update to version 9 before replication catches up. Therefore, the code above **does not turn MREC into a global compare-and-swap**.

Use write-to-one-Region or write-to-your-Region if you need globally meaningful OCC in MREC. With MRSC, conditional writes evaluate against the latest version; you still must handle `ReplicatedWriteConflictException`.

### 18.4. Retry Policy

- Retry only transient/retryable errors.
- Use exponential backoff with jitter so clients do not retry in lockstep.
- Cap the retry count and total duration.
- Use an operation ID / idempotency key for business actions.
- After a conflict, re-read the item/version and recompute the business decision.
- Do not retry a financial command if the provider/ledger does not support idempotency.

Do not catch every `DynamoDbException` and retry; `AccessDenied`, `ValidationException`, or `ConditionalCheckFailed` require different handling.

## 19. Practical Exercises with Suggested Answers

### Exercise 1 — Choosing a Consistency Mode

**Prompt:** An application has customers across multiple Regions and only updates bookmark positions by writing absolute values. Eventual convergence after a short delay is acceptable.

**Answer:** MREC works well with write-to-any-Region if writes are idempotent. Monitor `ReplicationLatency` and tolerate eventual reads. MRSC offers strong consistency but increases latency and restricts transactions/TTL/Region topology; no need to pick it if business requirements do not demand it.

### Exercise 2 — Address Conflict

**Prompt:** The same user item has `phoneNumber` edited in Singapore and `preferredLanguage` edited in Tokyo almost simultaneously. After replication, one change is lost.

**Answer:** This is the LWW risk on the same item; DynamoDB does not merge attributes semantically. Split `CONTACT` and `PREFERENCES` into separate items, assign a home Region per user, or use MRSC if appropriate.

### Exercise 3 — Counter in MREC

**Prompt:** Two Regions concurrently execute `ADD inventorySold = 1` on an MREC item.

**Answer:** Both updates can conflict and LWW can drop one increment. Route updates to a single writer/home Region, write append-only operation records with unique IDs, or use MRSC for the counter item if transactions are unnecessary and limitations are acceptable.

### Exercise 4 — Conditional Write in MREC

**Prompt:** Two Regions concurrently read `version = 8` and write with condition `version = 8`, and both succeed at their local replicas.

**Answer:** MREC conditional writes evaluate only local state. They are not a global compare-and-swap. Use a single writer/home Region or choose MRSC when conditions must evaluate against the latest version.

### Exercise 5 — Choosing an MRSC Topology

**Prompt:** A system needs strong consistency and wants three replicas in Singapore, Tokyo, and Ireland.

**Answer:** As of this lesson, MRSC supports 15 Regions and allows cross-continental three-Region configurations per AWS's announcement on 23/09/2026. However, validate latency/quorum and business constraints; MRSC does not support transactions, TTL, LSI, or multi-account.

### Exercise 6 — MRSC Write Conflict

**Prompt:** A Java client receives `ReplicatedWriteConflictException` when two requests update the same order item from two Regions.

**Answer:** Retry with exponential backoff/jitter, re-read the item/version, and recompute the business operation. Use an operation ID to prevent duplicate side effects. Do not retry infinitely or retry every `DynamoDbException`.

### Exercise 7 — Transactions and Replication

**Prompt:** An MREC transaction updates Order, Payment, and Inventory. A receiving Region already sees Order = PAID but does not yet see the Payment item.

**Answer:** This is normal semantics: transactions are atomic within the source Region, while items replicate individually. Use a commit marker/version or projection logic that exposes state only once all records arrive; never assume remote transaction atomicity.

### Exercise 8 — TTL and Capacity

**Prompt:** An MREC table experiences heavy TTL expirations; a provisioned-mode replica starts seeing rising `WriteThrottleEvents`.

**Answer:** TTL deletes in the source Region consume no write capacity, but replicated deletes consume capacity in receiving Regions. Capacity must cover application writes + replicated TTL deletes. Inspect auto scaling, workload, and hot partitions.

### Exercise 9 — Streams and Origin Region

**Prompt:** A Lambda reading DynamoDB Streams in Singapore processes an event created in Tokyo and replicated to Singapore, causing a side effect to run twice.

**Answer:** MREC replica streams can contain both local and replicated changes. Attach an `originRegion` or business event ID, filter for local-origin events if required by the architecture, and keep consumers idempotent. Do not assume each stream record represents a single unique business operation.

### Exercise 10 — Multi-Account Global Table

**Prompt:** Three business units in three accounts want one replica per account, each managing its own KMS keys and backups.

**Answer:** Evaluate multi-account Global Tables MREC; each replica resides in its own account/Region, grant resource policies to the replication service principal, enable settings replication, and manage non-synchronized settings like KMS/PITR/deletion protection per account. MRSC does not support multi-account.

### Exercise 11 — Rising ReplicationLatency

**Prompt:** CloudWatch `ReplicationLatency` Average jumps from 400 ms to 8 seconds between Singapore and Tokyo.

**Answer:** Verify the exact source/receiving pair, workload, throttling, hot keys, replica status, service-linked role, resource policies, KMS, and Region health. Do not blindly increase capacity before identifying the root cause. This metric has no SLA, so compare against freshness SLOs and baselines.

### Exercise 12 — MREC Failover

**Prompt:** Singapore unexpectedly loses connectivity; Tokyo continues writing to order items. When Singapore recovers, several older pending writes get overwritten by LWW.

**Answer:** This is an inherent risk of MREC during Region isolation. Use write routing/home Regions, idempotent operation logs, quarantine/reconciliation, and business audits. For data requiring RPO=0, evaluate MRSC if its constraints fit.

### Exercise 13 — Checking Global Tables Version

**Prompt:** CLI `DescribeTable` returns `GlobalTableVersion = 2019.11.21`.

**Answer:** This is the Current version. Use `UpdateTable`/`DescribeTable` and the current replica model. If a table uses Legacy 2017.11.29, management relies on separate APIs; never mix the two command sets.

### Exercise 14 — Witness Cannot Be Queried

**Prompt:** A team tries calling `GetItem` against the MRSC witness Region and finds no table endpoint.

**Answer:** A witness is not a full replica and does not serve reads/writes. It is a DynamoDB-managed quorum component. Applications only call the two full replica Regions.

### Exercise 15 — Design Choice for Inventory Reservation

**Prompt:** You must atomically reserve inventory, create an order, and record a payment intent; requests can arrive from multiple Regions simultaneously.

**Answer:** MRSC does not support transaction APIs. MREC write-to-any-Region risks conflicts. Use a single-writer/home Region for the aggregate, execute transactions in the primary Region, and use workflows/outbox/sagas for cross-service operations. If changing the data model, split ledger/reservation records with idempotency keys.

## 20. Self-Check Questions

**Question 1.** What is DynamoDB Global Tables?  
**Answer:** A multi-Region, multi-active feature that automatically replicates table data across AWS Regions.

**Question 2.** Does DynamoDB Global Tables provide a global endpoint?  
**Answer:** No. Applications call the regional endpoint of the local replica.

**Question 3.** Which version is the Global Tables current version?  
**Answer:** **2019.11.21**.

**Question 4.** If no consistency mode is specified when creating a global table, what is the default?  
**Answer:** **MREC**.

**Question 5.** Can MREC be changed to MRSC after creation?  
**Answer:** No. Consistency mode cannot be changed once a global table is created.

**Question 6.** Does MREC replicate synchronously or asynchronously?  
**Answer:** Asynchronously; replicas converge after replication lag.

**Question 7.** How does MREC handle concurrent writes to the same item?  
**Answer:** **Last writer wins**, based on internal timestamps.

**Question 8.** Does LWW merge individual attributes according to business semantics?  
**Answer:** No. The application must implement custom merging/versioning if needed.

**Question 9.** Does ReplicationLatency have a fixed one-second SLA?  
**Answer:** No. AWS publishes no SLA for this metric.

**Question 10.** Does an MREC strong read in Region B always see a write that just occurred in Region A?  
**Answer:** No. A strong read only guarantees the local state of replica B; replication must finish first.

**Question 11.** What are the three main write models?  
**Answer:** Write to any Region, write to one Region, and write to your Region.

**Question 12.** Which kinds of writes fit MREC write-to-any-Region?  
**Answer:** Idempotent writes or cases where conflict/LWW risk is acceptable.

**Question 13.** When should you use an MREC single-writer Region?  
**Answer:** When you need transactions, conditional writes based on the latest state, or non-idempotent operations.

**Question 14.** Where does MRSC synchronize a write before returning success?  
**Answer:** To at least one other Region under service quorum mechanics.

**Question 15.** Exactly how many Regions does MRSC require?  
**Answer:** Three Regions: three replicas or two replicas plus one witness.

**Question 16.** Does a witness serve GetItem/PutItem requests?  
**Answer:** No. A witness is not a full replica and has no application read/write endpoint.

**Question 17.** Does MRSC support TransactWriteItems?  
**Answer:** No.

**Question 18.** Does MRSC support TTL deletion?  
**Answer:** No.

**Question 19.** Does MRSC support LSI?  
**Answer:** No. GSIs are supported, though GSI reads are eventually consistent.

**Question 20.** Which error can an MRSC concurrent write conflict return?  
**Answer:** **ReplicatedWriteConflictException**.

**Question 21.** Which consistency mode does Multi-account Global Tables support?  
**Answer:** **MREC** only.

**Question 22.** Within what scope are MREC transactions atomic?  
**Answer:** Only within the Region where the transaction is invoked; individual items replicate separately to other Regions.

**Question 23.** Why are MREC Streams enabled by default?  
**Answer:** DynamoDB uses Streams to read changes and replicate them to other replicas.

**Question 24.** Does a TTL delete replicated to a receiving Region consume write capacity?  
**Answer:** Yes, replicated deletes consume write capacity in receiving Regions.

**Question 25.** Which CloudWatch metric tracks MREC replication lag?  
**Answer:** **ReplicationLatency**, measured in milliseconds, per source/receiving Region pair.

**Question 26.** Does MRSC emit the ReplicationLatency metric?  
**Answer:** No.

**Question 27.** Does Global Tables automatically redirect traffic when a Region fails?  
**Answer:** No. Applications require routing/failover for compute and requests.

**Question 28.** Why shouldn't you call a remote DynamoDB endpoint when the local Region fails?  
**Answer:** You should route requests to the application stack in a healthy Region and call its local endpoint, avoiding cross-Region calls and stranded dependencies in the failed Region.

**Question 29.** Does MRSC's RPO of 0 mean RTO is 0?  
**Answer:** No. Application routing, compute, DNS, and dependency failover still take time.

**Question 30.** Why is an idempotency key needed when retrying an MRSC write?  
**Answer:** So the same business operation does not produce duplicate side effects or transactions upon retry.

**Question 31.** Which IAM role does DynamoDB use for cross-Region replication?  
**Answer:** The **AWSServiceRoleForDynamoDBReplication** service-linked role.

**Question 32.** What can happen if a resource policy denies the service-linked role?  
**Answer:** Replication can stop and the replica can enter `REPLICATION_NOT_AUTHORIZED`.

**Question 33.** Can you replicate only a subset of items in the same global table?  
**Answer:** No. Global Tables replicates all table items; split into separate tables if different replication scopes are needed.

**Question 34.** Does Global Tables replace backups/PITR?  
**Answer:** No. Replication also propagates erroneous deletes/updates; backups and recovery remain necessary.

**Question 35.** How do multi-account global tables help?  
**Answer:** They separate ownership, IAM/KMS, governance, CloudTrail, and cost allocation across accounts.

## 21. Knowledge Summary and AWS Reference Documentation

Global Tables is a powerful multi-Region data foundation, but making the right choice depends on **consistency requirements, write model, data model, and recovery design**.

### 26.1. Remembering the Two Consistency Modes

- **MREC:** asynchronous replication, LWW conflict resolution, low local latency; requires idempotency and home Region/single writer when business logic is sensitive to lost updates.
- **MRSC:** synchronous replication/quorum, strongly consistent reads/writes, and RPO=0 for successful writes; trades off higher latency, fixed three-Region topology, no transactions/TTL/LSI, and same-account only.

### 26.2. Pre-Production Checklist

1. Verify **Global Tables version**; prefer 2019.11.21 Current.
2. Choose **MREC or MRSC** based on consistency, latency, transaction, and TTL requirements.
3. Choose a **write model** per aggregate; do not let every Region write the same item without conflict analysis.
4. Design **business event IDs, versions, idempotency, and auditing**.
5. Validate semantics of **conditional writes, transactions, Streams, TTL, and GSI/LSI**.
6. Deploy the application stack in each Region and call the **local DynamoDB endpoint**.
7. Design routing, failover, Region evacuation, RPO/RTO, and split-brain prevention.
8. Verify capacity/auto scaling, hot partitions, GSI write pressure, and failover headroom.
9. Protect the replication service-linked role, resource policies, SCPs, and KMS.
10. For multi-account, verify each account/Region, settings replication, and non-synchronized settings.
11. Dashboard **ReplicationLatency** for MREC along with throttling/errors per replica.
12. Maintain CloudTrail, business logs, reconciliation, and runbooks for replication issues/conflicts.
13. Test Region isolation, failover, replica catch-up, and business correctness with AWS Fault Injection Service when appropriate.
14. Track replicated write costs, storage, backups/PITR, indexes, Streams, CloudWatch, and KMS.
15. Conduct regular recovery drills and prove the application meets SLOs after failover.

**Conclusion:** Global Tables automates replication, but it does not automatically decide which data is right when multiple Regions write concurrently. MREC requires applications to manage conflicts and tolerate eventual consistency; MRSC delivers per-item strong consistency with clear latency and topology trade-offs. Combined with the right write model, idempotency, routing, IAM/KMS, monitoring, and DR testing, DynamoDB Global Tables provides a reliable foundation for multi-Region AWS applications.

### Official AWS Documentation

- [DynamoDB Global Tables overview](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html) — same-account/multi-account models and consistency modes.
- [How Global Tables work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html) — MREC, MRSC, transactions, TTL, Streams, and replication.
- [Using DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html) — write modes, routing, failover, RPO/RTO, and capacity.
- [Write modes with Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.writemodes.html) — write-to-any, single-primary, and home Region.
- [Routing strategies](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.request-routing.html) — client, compute, Route 53, and Global Accelerator.
- [Evacuation processes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.evacuation.html) — shifting workloads away from a live or offline Region.
- [Global Tables versions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_versions.html) — Current 2019.11.21 and Legacy 2017.11.29.
- [Global Tables security](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/globaltables-security.html) — service-linked roles, IAM, and KMS.
- [Multi-account Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_MA_HowItWorks.html) — cross-account replication and settings.
- [Global Tables billing](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/global-tables-billing.html) — replicated write units and pricing.
- [DynamoDB metrics and dimensions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html) — ReplicationLatency and per-table/operation metrics.
- [DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html) — strongly/eventually consistent reads.
- [AWS announcement — MRSC additional Regions, 23 September 2026](https://aws.amazon.com/about-aws/whats-new/2026/09/dynamodb-mrsc-additional-regions/) — 15 Regions and cross-continental configurations.
- [DynamoDB global tables best practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/globaltables-bestpractices.html) — version, deletion protection, and CloudFormation deployment.


## 22. Global Tables Cost

Global Tables increases cost compared to a single-Region table because each replica has its own storage, reads, replicated writes, and supporting features.

### 19.1. Billable Components

| Component | What to evaluate |
| --- | --- |
| **Replicated writes** | rWRUs for on-demand or rWCUs for provisioned; incurred in Regions hosting replicas. |
| **Reads** | RRUs/RCUs based on request volume and read consistency in each Region. |
| **Storage** | Data stored in each replica Region. |
| **GSI writes/storage** | Indexes carry separate capacity and storage usage per DynamoDB pricing. |
| **Backups/PITR** | Backup/point-in-time recovery settings per replica by Region. |
| **Streams** | Stream reads, Lambda consumers, and downstream processing if used by the application. |
| **CloudWatch** | Metrics, alarms, dashboards, and additional custom metrics/logs. |
| **KMS** | Customer managed keys, API requests, and key administration per configuration. |
| **Replica bootstrap** | When adding a new replica, account for initialization/restore costs and resulting usage under current pricing. |

### 19.2. Replicated Write Units

With Current Global Tables, replicated writes are metered as **rWRU** in on-demand mode or **rWCU** in provisioned mode. These units have pricing aligned with single-Region DynamoDB write units and are incurred in **every Region hosting a replica**.

Illustrative example:

- A 1 KB write into a global table with two replicas.
- Each replica incurs replicated write usage under the billing model.
- Total write cost depends on replica count, item size, operation, and global table version.

Do not count only writes sent directly by the application. Replication and TTL deletes also generate write consumption in receiving Regions.

### 19.3. Data Transfer and Witness

Per current Global Tables billing documentation, DynamoDB **does not charge cross-Region data transfer fees for replication between Regions** of a global table. However, application traffic, API calls, event pipelines, or other services transferring data cross-Region incur their own charges.

With MRSC using a witness, the witness does not incur storage or replicated write unit costs like a full replica. Do not confuse a witness with a Region capable of serving application reads/writes.

### 19.4. Multi-Account Cost Allocation

In multi-account global tables, each account pays for resources and requests consumed on its local replica, including reads, writes, storage, and associated data transfer. This enables per-account cost allocation; combine with tags, Cost Explorer, and CUR for team-level chargeback.

### 19.5. TTL and Replicated Delete Costs

With MREC:

- TTL deletion in the Region executing the delete consumes no write capacity under TTL mechanics.
- Replicated deletes sent to the remaining Regions consume replicated write units at the destinations.
- Overly low provisioned capacity can throttle if replicated TTL deletes plus application writes exceed capacity.

### 19.6. How to Estimate

Hypothetical example:

- 2 million writes/day.
- 1.5 KB average item size.
- 3 replica Regions.
- 10 million reads/day, distributed across the three Regions.
- 2 GSIs and PITR enabled on every replica.

You cannot simply multiply "2 million writes × price of one write" to estimate the bill. Account for:

1. Item size and write units per operation.
2. rWRU/rWCU across replica count and global table version.
3. GSI update units.
4. Read consistency and read units.
5. Storage per Region and backup/PITR.
6. TTL deletes, Streams consumers, Lambda, and CloudWatch.
7. Regional pricing, account ownership, and supporting services.

Use **AWS Pricing Calculator**, Cost Explorer, and Cost and Usage Reports (CUR) to reconcile actual usage. Prices vary by Region and over time.

## 23. Dashboards and Alerts

A Global Tables dashboard should include a panel group for **each replica Region** as well as source/receiving Region pairs.

### 20.1. Suggested Dashboard

~~~mermaid
flowchart TB
    A["Regional write/read traffic"] --> D["Global Tables dashboard"]
    B["ReplicationLatency by Region pair"] --> D
    C["Throttles / SystemErrors / UserErrors"] --> D
    E["Replica status / resource policies / KMS"] --> D
    F["Application conflicts / retries / idempotency"] --> D
    G["Failover routing / business reconciliation"] --> D
    D --> H["CloudWatch alarms + incident runbook"]
~~~

### 20.2. Reference Alarms

| Signal | Illustrative condition | Action |
| --- | --- | --- |
| **ReplicationLatency Average** | Exceeds baseline over multiple periods. | Identify source/receiving pair and workload. |
| **ReplicationLatency Maximum** | Sustained spike or breaches freshness SLO. | Check capacity, Region health, IAM/KMS. |
| **WriteThrottleEvents** | Increases on base table or GSI. | Check provisioned capacity, auto scaling, hot keys. |
| **ReadThrottleEvents** | Increases at a replica. | Check read traffic and GSI/partition hotness. |
| **SystemErrors** | Increases by TableName + Operation. | Check service errors, retries, and AWS Health. |
| **ConditionalCheckFailedRequests** | Unusual spike. | Investigate contention/version conflicts and business behavior. |
| **ReplicaStatus** | No longer ACTIVE or shows an error state. | Check permissions, KMS, Region opt-in, and replication SLR. |
| **Application retry rate** | Exceeds baseline or hits retry exhaustion. | Distinguish transient conflicts from misconfiguration. |
| **Business reconciliation gap** | Source operation count differs from destination. | Quarantine/replay/reconcile using business IDs. |

Concrete thresholds must be derived from SLOs, baselines, and business tolerance. Never apply the same replication latency threshold to every Region pair.

### 20.3. Missing Data

- An MREC table with no writes during a window may emit no `ReplicationLatency` datapoints.
- MRSC does not emit `ReplicationLatency`.
- Metrics dimensioned by operation may appear only when requests occur.
- A Region without traffic does not mean the replica is broken.

Configure appropriate missing-data treatment and combine with heartbeat/synthetic checks. Never turn missing `ReplicationLatency` into a red alarm on MRSC.

## 24. Runbook: Replication Lag, Conflicts, and Region Failover

### 21.1. Rising ReplicationLatency on MREC

1. Identify the source Region and `ReceivingRegion` of the metric.
2. Inspect Average/Maximum over the same time window.
3. Check writes/throughput, throttling, and hot partitions on source/receiving replicas.
4. Inspect replica status, DynamoDB Streams settings, and resource policies.
5. Inspect the service-linked role `AWSServiceRoleForDynamoDBReplication`.
6. Check KMS key policy / disabled keys.
7. Check Region opt-in, account permissions, and AWS Health events.
8. If the application requires immediate freshness, route reads to the Region that just wrote or apply a home Region policy.
9. Once lag clears, reconcile business data/versions across replicas.

Do not simply raise capacity when the true root cause is a revoked resource policy or KMS access.

### 21.2. Replica in REPLICATION_NOT_AUTHORIZED State

Investigation steps:

- Identify the account/Region owning the replica.
- Inspect resource-based policies and explicit Denies.
- Ensure the replication service principal / service-linked role has permissions per AWS policy.
- Check SCPs, permissions boundaries, and policy conditions.
- Restore appropriate KMS/resource policy permissions.
- Monitor replica status and replication latency after remediation.

With MREC, if this state persists beyond **20 hours**, AWS warns the replica may be permanently converted into a standalone regional table. Multi-account replication also emits notifications/escalations when customer-caused lag persists; remediate early rather than waiting for automatic disassociation thresholds.

### 21.3. ReplicationLatency Increases While IAM/KMS Are Valid

Check:

- Throughput and write bursts.
- Hot partitions/keys.
- Large item sizes or GSI write pressure.
- Throttled requests in source/receiving Regions.
- Regional service health.
- Whether the application's own Streams/Lambda processing (if used) is being confused with DynamoDB's built-in replication.

### 21.4. MREC Conflict or Lost Update

1. Identify the item key and the Regions that issued writes.
2. Cross-check operation IDs, business versions, and source events.
3. Verify the current write model: any Region, single primary, or home Region.
4. Determine whether the conflict is acceptable under LWW.
5. If not, shift writes to single-writer/home Region or split the item.
6. Recover lost data from the business event log / source of truth if available.
7. Add version checks, idempotency, and metrics for future protection.

DynamoDB does not expose a historical conflict log for applications to download; business auditing must be captured at the application layer.

### 21.5. MRSC ReplicatedWriteConflictException

- Check item keys and per-Region request rates.
- Retry with exponential backoff/jitter.
- Re-read the item if the business decision depends on fresh state.
- Use an idempotency key so retries do not duplicate side effects.
- If conflicts persist continuously, consider serializing writes per item or revising the data model.

Do not raise retry counts indefinitely; doing so causes load amplification and higher latency.

### 21.6. Region Evacuation

For MREC single-primary:

1. Block writes to the currently active Region.
2. Confirm replication has caught up using metrics/checkpoints and a controlled wait window.
3. Update global routing controls.
4. Enable writes in the new Region.
5. Monitor for duplicate/stale operations.
6. Keep the old Region read-only/isolated until confident no split-brain remains.

For MREC write-to-any-Region, decide whether temporary gaps or late writes are tolerable. For MRSC, verify quorum and that remaining Regions satisfy consistency requirements before shifting traffic.

## 25. Real-World Architecture Scenarios

### Case A — User Profile for Global Users

**Requirement:** Users can update display names, avatar preferences, and bookmarks from multiple Regions. If two devices update near each other, the system accepts the last state winning.

**Choice:** MREC, write-to-any-Region for idempotent fields, or split items by attribute group. Use business versions and audit events if conflicts need to be surfaced to users.

**Avoid:** Using `ADD` on a shared item to count actions across multiple Regions if lost updates are unacceptable.

### Case B — Inventory and Order Reservation

**Requirement:** Two Regions may receive orders for the last unit of a product simultaneously; overselling inventory must be prevented.

**Choice:** Do not default to MREC write-to-any-Region with an inventory counter. Use single-writer/home Region for the inventory item, reservation workflows, and conditional writes in the primary Region; or evaluate MRSC if the operation fits a single item without needing transaction APIs.

**Trade-off:** MRSC provides per-item strong consistency but lacks `TransactWriteItems`/TTL. If you must atomically reserve inventory + create an order + payment across multiple items, design a workflow/saga/ledger or choose a more suitable model.

### Case C — Payment Ledger

**Requirement:** Never lose or double-record financial transactions; auditing and reconciliation are mandatory.

**Choice:** MREC single-writer Region for ledger aggregates, append-only records with unique operation IDs, payment provider idempotency, transactions within the primary Region, and replication to read Regions. Maintain a controlled failover runbook and reconcile event logs.

**Avoid:** Allowing two Regions to execute `ADD balance` on the same MREC item without write coordination.

### Case D — Global User Entitlements Requiring Strong Reads

**Requirement:** After granting access permissions, any Region must immediately read the latest entitlement.

**Choice:** Evaluate MRSC because of strongly consistent reads across replicas. Check latency, quorum, the three supported Regions, confirm no need for TTL/transactions/LSI, and accept the same-account constraint.

**Avoid:** Using a GSI to read the latest entitlement, since GSI reads are eventually consistent.

### Case E — Multi-Account Business Units

**Requirement:** Orders, Billing, and Analytics are owned by different AWS accounts needing local replicas and cost separation.

**Choice:** Multi-account Global Tables **MREC**, placing each replica in its own account/Region; grant resource policies to the replication service principal, enable settings replication, and configure KMS/backups/resource policies separately per account.

**Avoid:** Expecting multi-account MRSC or per-replica overrides of every table setting.

### Case F — Region Outage in MREC

**Requirement:** Singapore suffers a sudden outage; Tokyo continues accepting writes.

**Choice:** Shift traffic to the Tokyo stack; identify the range of data that may not have propagated; use upstream event logs/idempotency to reconcile once Singapore recovers. For data that cannot tolerate gaps, quarantine aggregates in unverified states.

**Avoid:** Claiming RPO=0 just because Global Tables was `ACTIVE` prior to the outage.

## 26. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Global Tables has a single global endpoint." | False; applications call the local regional endpoint. |
| "MREC replicates synchronously." | MREC is asynchronous and converges after replication lag. |
| "MRSC is just faster MREC." | MRSC uses synchronous replication/quorum with different latency trade-offs. |
| "An MREC strong read in Region B immediately sees a write from Region A." | Strong reads only guarantee local replica state; remote writes must replicate to B first. |
| "LWW merges different attributes automatically." | Conflicts resolve at the item/version level; there is no semantic field merge. |
| "LWW conflicts appear in CloudTrail." | There is no dedicated LWW conflict event; the application must audit separately. |
| "MREC transactions are atomic across all Regions." | Atomic only in the Region invoking the transaction; remote replicas may observe items step by step as replication arrives. |
| "MRSC supports TransactWriteItems." | MRSC does not support transaction APIs. |
| "MRSC can have as many replicas as desired." | Exactly three Regions: 3 replicas or 2 replicas + 1 witness. |
| "A witness is a read/write replica." | A witness does not serve application reads/writes. |
| "MRSC supports TTL." | MRSC does not support TTL deletion. |
| "MRSC supports LSIs like MREC." | MRSC does not support LSIs; GSI reads remain eventual. |
| "GSI reads in MRSC are always strong." | GSI reads are eventually consistent. |
| "Global Tables automatically routes users to the nearest Region." | Applications must route requests themselves. |
| "Failover only requires changing the DynamoDB Region in the SDK." | You must shift the application stack, routing, auth, dependencies, and state. |
| "An offline MREC Region still guarantees all writes exist in other replicas." | Unreplicated writes may be delayed until the Region recovers. |
| "MREC needs no idempotency because DynamoDB manages replication." | Application retries and duplicate business operations still require idempotency. |
| "A Region can filter to replicate only certain items in the same global table." | Global Tables replicates all table items. |
| "TTL deletes are free on all replicas." | Source TTL deletes consume no write capacity; replicated deletes consume write capacity in receiving Regions. |
| "ReplicationLatency has a 1-second SLA." | There is no SLA; latency varies by workload and Region pair. |
| "No ReplicationLatency metric means MRSC is broken." | MRSC does not emit this metric. |
| "Both same-account and multi-account support MRSC." | Multi-account supports MREC only. |
| "Disabling a KMS key only affects encryption at read time." | It can halt replication and make the replica inaccessible. |
| "Replica ACTIVE means the application is DR-ready." | Compute, routing, IAM, capacity, and recovery workflows still require testing. |
| "Global Tables replaces backups/PITR." | No; replication propagates erroneous deletes/updates too, so backups/restore and retention still require separate management. |


## 27. Production Readiness Checklist for Global Tables

Use this checklist during architecture reviews and DR drills:

1. **Version:** confirm Global Tables version 2019.11.21 Current; if still on Legacy, plan an upgrade per AWS guidance.
2. **Consistency mode:** document why MREC or MRSC was chosen; verify transaction, TTL, LSI, GSI, multi-account, and latency constraints.
3. **Write ownership:** define write-to-any, single-primary, or home Region per aggregate; prevent split-brain on failover.
4. **Conflict strategy:** implement idempotency keys, business versions, optimistic concurrency, and audit trails; specify clearly when LWW is acceptable.
5. **Regional routing:** each application stack calls the local DynamoDB endpoint; include health checks, failover controls, and DNS/client cache testing.
6. **Data model:** split items with independent lifecycles/updates; audit hot keys, partition distribution, item size, and GSI write amplification.
7. **Transactions/Streams/TTL:** test semantics in both source and receiving Regions; never assume transactions replicate atomically.
8. **Capacity:** account for application writes plus replicated writes, GSI/TTL traffic, bursts, and failover headroom per replica.
9. **IAM/KMS:** protect `AWSServiceRoleForDynamoDBReplication`, resource policies, SCPs, and KMS key policies; prevent explicit Denies from blocking replication.
10. **Multi-account:** if used, verify each replica account/Region, settings replication, resource policies, and independently configured settings.
11. **Monitoring:** dashboard `ReplicationLatency` for MREC, throttles/errors/status per replica, plus application conflict/retry/business metrics.
12. **Backups:** configure PITR/backups independently per replica as needed; test restores and reconciliation.
13. **DR:** define realistic RPO/RTO; maintain live evacuation and offline-Region runbooks; never claim MREC RPO=0.
14. **Testing:** test duplicate requests, concurrent writes, Region isolation, catch-up, permission denials, and failover in appropriate lab/staging environments.
15. **Cost:** budget for replicated writes across all Regions, storage, reads, GSIs, backups, Streams, CloudWatch, KMS, and multi-account allocation.
16. **Operations:** establish owners, incident severity levels, rollback, change control, and regular drills.

Global Tables delivers its full value only when **consistency semantics, write ownership, routing, and recovery processes** are designed together. Validate these decisions with realistic workloads and drills before relying on a multi-Region architecture in production.





