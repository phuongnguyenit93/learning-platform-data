# Schema Design and Primary Key Selection

An online learning platform runs Cloud Run for its course enrollment API, GKE for event processing, and Spanner for transactional data. Every second, thousands of students may enroll, make payments, or submit progress. If the application chooses a monotonically increasing primary key such as `EnrollmentId=1,2,3,...` out of habit from single-machine databases, most new writes can pile into the same **key range**. Spanner may have plenty of compute capacity, yet write latency still climbs because a single data range becomes hot (*hotspot*).

Within the **Spanner** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson focuses on **designing tables, data relationships, and primary keys** tailored to distributed mechanics. The goal is to balance **load distribution, uniqueness, read locality, consistency, and index cost**. Examples use the **GoogleSQL dialect**; Spanner also supports the **PostgreSQL dialect**, though DDL syntax and certain functions differ.

**After this lesson, you will be able to:**

1. Explain how Spanner stores rows in primary key order and partitions them into **splits**.
2. Identify monotonically increasing timestamp/sequence keys that create hotspots and choose appropriate UUIDv4, bit-reversed sequence, or composite keys.
3. Design relational tables, secondary indexes, and interleaved tables based on query patterns.
4. Account for multi-tenancy, transaction locality, row/parent hotspots, and write amplification.
5. Validate designs using schema DDL, query plans, metrics/Key Visualizer, and scenario exercises.

## 1. The Storage Model Dictates Primary Key Selection

Spanner is a distributed relational database that supports strongly consistent transactions and distributes data across many machines. Rows in a table are **ordered by primary key**. Spanner partitions key ranges into **splits** and assigns them to servers; split boundaries adjust dynamically with storage size and load.

~~~mermaid
flowchart TB
    A["Enrollments table<br/>ordered by primary key"] --> S1["Split: key range A–F"]
    A --> S2["Split: key range G–N"]
    A --> S3["Split: key range O–Z"]
    S1 --> N1["Server 1"]
    S2 --> N2["Server 2"]
    S3 --> N3["Server 3"]
    W["Multiple writers"] -->|"Distributed PK"| S1
    W --> S2
    W --> S3
~~~

The diagram is illustrative only: splits do not necessarily align with alphabet letters, one server can serve multiple splits, and Spanner rebalances automatically based on load.

### 1.1. Why Does Key Order Matter?

| Property | Design Implication |
| --- | --- |
| Rows are ordered by PK | **Point lookups** by full PK are efficient; **range scans** by key prefix/range have better locality than arbitrary scans. |
| Splits are key ranges | Writes concentrated at the **end/start of a contiguous range** can overload a single split. |
| Composite keys order left to right | `(TenantId, StudentId, EventTime)` favors queries that know tenant/student; it does not optimize queries that only know EventTime. |
| Primary key is also physical layout | Changing key order alters **load distribution, locality, transactions, and query strategy**—not just a constraint. |
| Secondary indexes have their own key structure | A well-distributed base table can still suffer an **index hotspot** if an index starts with an ascending timestamp. |

**A primary key must uniquely identify each row**, but *uniqueness* alone is not enough: in Spanner, a sound key must also **distribute writes** and serve the dominant queries.

### 1.2. Three Mandatory Questions Before Writing DDL

1. **Write path:** in what order is data generated, does it grow monotonically over time, and is there an extremely hot tenant/account?
2. **Read path:** does the app typically look up by an ID, a tenant, a user, or a list of recent events?
3. **Data relationships:** which rows need to be read/transacted together, and can any parent have an enormous number of children?

For a reliable design, collect read/write ratios, QPS/TPS, per-tenant distribution, data growth, p95/p99 targets, and critical query groups. Never choose keys based on a toy example with only a handful of rows.

## 2. Choosing a Primary Key: Four Common Approaches

### 2.1. Avoid Leading Timestamps or Monotonic IDs on High-Write Tables

An **unsuitable** example for a continuous, high-write event table:

~~~sql
-- GoogleSQL; ANTI-PATTERN example for high-insert workloads.
CREATE TABLE EnrollmentEventsBad (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(64) NOT NULL,
  StudentId STRING(64) NOT NULL,
  Kind STRING(32),
) PRIMARY KEY (CreatedAt, EventId);
~~~

New timestamps continuously increase, so inserts almost always land at the **tail of the keyspace**. Even with a unique `EventId` as the second column, the `CreatedAt` prefix remains sequential. Changing `ASC` to `DESC` does not solve the root issue: it merely moves the hotspot to the **head** of the key range.

Similarly, an `(OrderId INT64)` from an **ascending sequence** or a time-ordered ID (such as UUIDv1; many time-sortable ID formats) can create a hotspot under concentrated inserts. Never rely on the label "UUID" while ignoring **byte ordering and leading-bit entropy**.

### 2.2. Random UUIDv4 for High-Write Root Tables

Spanner recommends **UUID version 4** for many new tables because values spread broadly and rarely cluster into a single key range.

~~~sql
-- GoogleSQL dialect. Do not run on production databases without approval.
CREATE TABLE Students (
  StudentId UUID NOT NULL DEFAULT (NEW_UUID()),
  Email STRING(320) NOT NULL,
  DisplayName STRING(200),
  CreatedAt TIMESTAMP,
) PRIMARY KEY (StudentId);
~~~

Example inserting and returning the Spanner-generated key:

~~~sql
INSERT INTO Students (Email, DisplayName)
VALUES ('student-lab@example.invalid', 'Lab student')
THEN RETURN StudentId;
~~~

**Benefits:** clients do not coordinate sequence numbers; inserts of new students spread across many key ranges; PK is an immutable identifier. **Trade-offs:** IDs carry no time order or business semantics, and queries by Email/CreatedAt typically require a **secondary index**. Random UUIDv4 also does not optimize range scans like "100 most recent students" without additional index/query design.

Do not treat UUIDv4 as "security": unpredictable IDs **do not replace** IAM checks, tenant ownership validation, and API authorization.

### 2.3. Bit-Reversed Sequences When APIs Require Numeric Keys

If 64-bit integers are required for migration or API contracts, Spanner provides **bit-reversed positive sequences** to scatter generated values rather than clustering them at the end of the keyspace.

~~~sql
-- GoogleSQL dialect; for lab DB illustration only.
CREATE SEQUENCE EnrollmentSeq OPTIONS (
  sequence_kind = 'bit_reversed_positive'
);

CREATE TABLE EnrollmentIds (
  EnrollmentId INT64 NOT NULL
    DEFAULT (GET_NEXT_SEQUENCE_VALUE(SEQUENCE EnrollmentSeq)),
  StudentId STRING(64) NOT NULL,
  CourseId STRING(64) NOT NULL,
) PRIMARY KEY (EnrollmentId);
~~~

Sequence values are **not monotonically increasing in time** and are not contiguous: do not use them as invoice numbers requiring gapless sequences. Spanner also supports `IDENTITY`, `AUTO_INCREMENT`, and `SERIAL` mechanisms (dialect-dependent), but you must inspect **how values are distributed** rather than equating them with single-node RDBMS auto-increment.

When migrating existing numeric IDs, prevent **key collisions** between legacy data and newly generated keys: you may need skipped ranges/sequence configuration and reconciliation before cutover.

### 2.4. Composite Keys for Grouped Queries

Suppose the API frequently reads all enrollments for a student. Composite key:

~~~sql
CREATE TABLE Enrollments (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL DEFAULT (NEW_UUID()),
  CourseId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId);
~~~

Enrollments for the same `StudentId` are stored together by key prefix, speeding up queries like:

~~~sql
-- Use parameters in production; value illustrates UUID type only.
SELECT EnrollmentId, CourseId, Status
FROM Enrollments
WHERE StudentId = @student_id;
~~~

**Trade-offs:** if one `StudentId`/tenant receives massive write volume, locality can become a hotspot. When a query knows only `EnrollmentId`, this composite key **does not support a single-column point lookup**; you must either provide `StudentId` or add an appropriate index.

| Key Type | Best When | Risk to Test |
| --- | --- | --- |
| Leading `UUIDv4` PK | Creating root rows across many writers, ID lookups | Does not inherently support time/group ordering |
| Bit-reversed `INT64` | Numeric key compatibility needed, high insert throughput | Keys lack meaningful ascending order |
| `(StudentId, EnrollmentId)` | Reading/writing per student, in-group operations | Extremely hot student, lookups by EnrollmentId alone |
| `(CreatedAt, EventId)` | Recent scans look convenient | **Write hotspot** if CreatedAt increases continuously |

**Rule:** choose key order based on **actual write and read paths**. No single primary key design is optimal for every table.

## 3. Designing Relationships: Interleaving, Foreign Keys, and Locality

Spanner supports **foreign keys** and **interleaved tables**. The two mechanisms serve different purposes:

- **Foreign key:** enforces data relationships/constraints. It does not necessarily place the two tables physically close together.
- **Interleaving:** physically arranges child rows near their parent row in key order so rows commonly read together enjoy good locality; it also enforces parent–child constraints.

### 3.1. Interleaved Child by Parent Key Prefix

In the `Students` and `Enrollments` example, if most APIs look up enrollments **by student**, you can use:

~~~sql
-- GoogleSQL. Assumes Students(StudentId UUID) table already exists.
CREATE TABLE EnrollmentsInterleaved (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL,
  CourseId STRING(64) NOT NULL,
  Status STRING(32) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId),
  INTERLEAVE IN PARENT Students ON DELETE CASCADE;
~~~

Important requirements:

1. The child table's key must start with the **parent's key columns, matching exact order, names, and types**.
2. The parent row must already exist, or be created within the same transaction per Spanner rules.
3. `ON DELETE CASCADE` deletes child rows when the parent is deleted; use only if it matches the data lifecycle. `ON DELETE NO ACTION` requires deleting/handling children before deleting the parent.
4. Locality **does not mean a row tree stays inside one split forever**: Spanner can split it when data or load grows.
5. For a parent with **millions of children or concentrated writes**, interleaving can complicate hotspots/transactions. Never nest all data under a single "global tenant" root.

~~~mermaid
flowchart TB
    S1["Student A (parent row)"] --> A1["Enrollment A-1"]
    S1 --> A2["Enrollment A-2"]
    S2["Student B (parent row)"] --> B1["Enrollment B-1"]
    S2 --> B2["Enrollment B-2"]
    NOTE["Related rows by<br/>StudentId prefix, not a free JOIN"]
    A1 -.-> NOTE
~~~

**Do not interleave solely because a logical foreign key exists.** If the business frequently queries "all enrollments for a `CourseId` across all students," a `StudentId` key prefix does not optimize that query; you need a secondary index or a different table/query path.

### 3.2. Transaction Locality and Frequently Updated Keys

Co-locating rows accessed/transacted together can reduce work across multiple splits. However, if a single row or key prefix receives **every `UPDATE`** (such as a shared `GlobalCounters` row), that row itself becomes a bottleneck even if other tables have well-distributed keys.

Avoid updating a single global counter on every enrollment when high throughput is required. Consider:

- Counting across **shards** and aggregating on read, if business rules allow.
- Using asynchronous aggregation/analytics for metrics that do not need immediate consistency.
- Keeping write transactions short, limiting the number of rows and keys involved.
- Choosing read consistency based on real requirements; never sacrifice financial accuracy for an untested optimization.

## 4. Multi-Tenant Schemas and Key Prefixes

Suppose a SaaS serves many schools. Every request must only access records belonging to `TenantId`. A straightforward composite key:

~~~sql
CREATE TABLE TenantCourses (
  TenantId STRING(64) NOT NULL,
  CourseId UUID NOT NULL DEFAULT (NEW_UUID()),
  Name STRING(200) NOT NULL,
  Status STRING(32) NOT NULL,
) PRIMARY KEY (TenantId, CourseId);
~~~

When the client sends `tenantId` and `courseId`, queries can filter by the full prefix:

~~~sql
SELECT Name, Status
FROM TenantCourses
WHERE TenantId = @tenant_id
  AND CourseId = @course_id;
~~~

**Data isolation:** a key containing `TenantId` helps structure queries and locality, **but does not enforce authorization**. The API must verify the tenant from the authenticated identity; never trust an arbitrary `tenant_id` in the request payload as proof of permission.

### 4.1. When a Tenant Becomes a Hot Key

A key `(TenantId, CreatedAt, EventId)` can work well for per-tenant event queries, but if **one tenant** generates tens of thousands of events/s, monotonically increasing timestamps **within that tenant** still create a write hotspot.

One way to avoid this is placing a shard or distributed ID before the timestamp:

~~~sql
CREATE TABLE TenantEvents (
  TenantId STRING(64) NOT NULL,
  ShardId INT64 NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  EventId UUID NOT NULL,
  Payload JSON,
) PRIMARY KEY (TenantId, ShardId, CreatedAt DESC, EventId);
~~~

The application computes `ShardId` **deterministically** from `EventId`, e.g., hashing into N logical shards. On write, events for the same tenant spread across multiple key ranges by `ShardId`; each range is ordered by time.

**Read trade-off:** a query for "the 50 most recent events of a tenant" must read **N shards**, fetch the latest entries from each, and merge/sort/limit them. You cannot run a single range scan by tenant and expect global chronological ordering.

Therefore:

- Choose N based on **actual traffic, capacity, and split/node counts**—do not blindly create millions of shards.
- N becomes part of the schema/query contract; changing N later may require migration/backfill.
- `DESC` helps fetch recent items within each shard, **not fix a hotspot** if only one shard is hot.
- Low-volume tenants do not necessarily need hash sharding; do not trade away locality to solve a problem that does not exist.

### 4.2. Conditional Composite Keys

| Dominant Query | Candidate Key / Index | Trade-off |
| --- | --- | --- |
| Find course by tenant + course ID | PK `(TenantId, CourseId)` | No global point lookup by CourseId alone |
| Read enrollments by student | PK `(StudentId, EnrollmentId)` | Needs an index if querying from CourseId |
| Recent events per student | `(StudentId, EventTime DESC, EventId)` | A hot student can become a hotspot |
| Event writes for an ultra-hot tenant | `(TenantId, ShardId, CreatedAt DESC, EventId)` | Tenant-wide reads require fan-out and merge |
| System-wide random lookups by ID | Standalone UUIDv4 PK | Does not co-locate data for the same tenant |

In Spanner, **adding more key columns does not mean better distribution**: you must evaluate the **distribution of the leading key prefix** and actual write patterns.

## 5. Secondary Indexes: Optimizing Reads While Risking New Hotspots

Choosing a primary key by `StudentId` optimizes reading one student's data. However, the course service needs to find **all enrollments for a course**; this is where secondary indexes add value.

### 5.1. An Index Tailored to a Real Query

~~~sql
CREATE INDEX EnrollmentsByCourse
ON Enrollments(CourseId, StudentId)
STORING (Status, CreatedAt);
~~~

Query:

~~~sql
SELECT StudentId, Status, CreatedAt
FROM Enrollments
WHERE CourseId = @course_id;
~~~

Spanner can use the index when appropriate; `STORING` duplicates extra columns in the index to avoid reading back from the base table for certain queries. This increases **storage** and **write amplification**: every UPDATE to an indexed/stored column may also update index entries.

Do not index every column hoping every query will be fast. Each index adds write overhead, storage cost, and backfill/schema-change duration. Use **query plans/EXPLAIN and workload metrics** to justify its value.

### 5.2. An Index Can Be Hot Even When the Primary Key Is Not

Suppose a log table has an evenly distributed UUIDv4 PK, but adds:

~~~sql
-- RISK: index begins with monotonically increasing timestamp.
CREATE INDEX LogsByCreatedAt
ON EventLogs(CreatedAt);
~~~

Every inserted message may have to **write an index entry at the tail of the index keyspace**. A well-distributed base table does not cure an index hotspot.

Options depending on the problem:

- If queries always know `UserId`: index `(UserId, CreatedAt DESC)`; the workload must have enough active users to distribute load.
- If querying globally by time: consider a **sharded time index**, fan-out reads, or offloading analytical workloads to a suitable system.
- If only looking up a few events by PK: consider dropping low-value indexes to cut write amplification.

### 5.3. Null-Filtered and Unique Indexes

In the **GoogleSQL dialect**, a `NULL_FILTERED` index excludes rows with NULL in the index key columns:

~~~sql
CREATE NULL_FILTERED INDEX EnrollmentsByCompletedAt
ON Enrollments(CompletedAt DESC);
~~~

This applies only when the actual table has a nullable `CompletedAt TIMESTAMP` column; this is a **schema extension concept**, not something to run directly on an `Enrollments` table lacking that column. The index stays smaller if most enrollments are incomplete, but queries that must include NULL rows **cannot** rely solely on this index for complete results.

A **unique index** enforces uniqueness on the index key; with `UNIQUE NULL_FILTERED`, rows excluded due to NULL **are not subject to that index's uniqueness constraint**. For emails/usernames requiring uniqueness, canonicalize values, specify NULL rules, and define tenant scope clearly before adding a unique index.

Note: in the **PostgreSQL dialect**, the equivalent syntax uses `INCLUDE` instead of `STORING`, and partial indexes filter NULLs via `WHERE ... IS NOT NULL`. Never mix the two dialects in one DDL file.

## 6. Changing Schemas and Primary Keys in Running Systems

Spanner supports many **online** schema changes such as adding columns, tables, or indexes. Nevertheless, changes affecting **primary keys, referencing keys, row ordering, or API contracts** are typically data migration projects; do not treat them as simple, risk-free `ALTER` commands.

### 6.1. Migrating from Sequential Keys to UUIDs

Suppose a legacy table uses an ascending `OrderId INT64` and has developed a write hotspot. Recommended process:

1. **Measure and pinpoint the hotspot source:** is it the table PK, a secondary index, or a shared counter row?
2. **Design the new key:** UUIDv4 or bit-reversed sequence per compatibility needs; decide how legacy IDs will be looked up.
3. **Create the new table** with the updated PK in an approved environment; add a unique index/mapping if legacy ID lookups remain necessary.
4. **Backfill** in bounded batches, verifying row counts, checksums/reconciliation, and CPU/I/O impact.
5. **Sync changes during transition** via CDC/outbox or an equivalent mechanism; avoid naive dual-writes that cannot reconcile partial failures where one side succeeds and the other fails.
6. **Cut over reads/writes progressively**, monitoring latency, conflicts, duplicate keys, and backlog; prepare a rollback plan before accepting new writes.
7. **Clean up old tables/indexes** once zero dependencies are verified, with backups and approval.

**Do not design rollback as merely flipping a connection string:** once data is written to the new table, reverting to the old table may require reverse replication/reconciliation. Especially for payments, test duplicate handling, idempotency, and consistency from the start.

### 6.2. Index Backfill and Schema Change Cost

When adding a secondary index to a populated table, Spanner must **backfill** the index. The database continues serving traffic, but backfilling consumes resources and can affect CPU/latency. For large indexes:

- Check **current load and headroom capacity**, scheduling changes within an approved maintenance/change window.
- Monitor backfill progress and query plans once the index is ready.
- Verify critical queries include matching filter predicates, especially for `NULL_FILTERED`.
- Measure index storage growth and write overhead afterward; drop unhelpful indexes via review.

### 6.3. Commit Timestamps and TTL: Avoiding Accidental Hotspots

Spanner supports storing **commit timestamps** in appropriately defined columns. This is useful for auditing write times, but placing an ascending commit timestamp as the **leading PK column** or **leading secondary index column** can create the same hotspot as a regular timestamp. Use it as a **non-leading data column** whenever query needs allow.

**TTL / row deletion policies** clean up expired data in the background, but deletion runs **asynchronously**, not instantaneously to the exact second; verify retention policies, parent–child relationships, and regulatory retention requirements. TTL does not cure a key hotspot.

## 7. Proving Designs with Measurements

### 7.1. Baseline Metrics to Collect

| Signal Group | What to Measure |
| --- | --- |
| **Traffic** | Inserts/updates/reads per second, distribution by tenant/user, row size, peak bursts. |
| **Latency** | p50/p95/p99 by operation, deadline exceeded errors, and transaction aborts/retries. |
| **Resources** | CPU utilization, storage, write throughput, node/processing unit counts. |
| **Key distribution** | Hot ranges, split patterns, and skew across key prefixes. |
| **Queries** | Query plans, index usage, scanned rows/bytes, lock/transaction conflicts. |
| **Index cost** | Number of indexes updated per write, backfill time, storage size, and latency. |
| **Business** | Idempotent writes, tenant data correctness, and error recovery behavior. |

**Key Visualizer** generates heatmaps of activity across key ranges, helping locate where reads/writes cluster. Pair it with Cloud Monitoring, query statistics, and transaction insights to determine whether heat is in the **primary table, a secondary index, or a single row/key group**.

~~~mermaid
flowchart TD
    ALERT["Write p99 or ABORTED rises"] --> KV["Key Visualizer:<br/>which key range is hot?"]
    KV --> PK{"Primary table or index?"}
    PK -->|Primary table| K["Check key prefix, sequential IDs,<br/>tenant skew, and hot counters"]
    PK -->|Secondary index| I["Check leading index key<br/>and write amplification"]
    K --> TEST["Propose new schema/query,<br/>test with representative load"]
    I --> TEST
    TEST --> VERIFY{"Did p99, skew, and cost<br/>improve?"}
    VERIFY -->|No| KV
    VERIFY -->|Yes| KEEP["Record ADR and rollout plan"]
~~~

**Note:** Spanner splits and balances load automatically, yet it cannot "fix" a monotonically increasing timestamp sequence simply by adding more servers. When all new writes hit one edge of the same range, the bottleneck lies in the **key/traffic model**, not just total capacity.

### 7.2. Signals to Avoid Misdiagnosis

| Symptom | Do Not Jump to Conclusion | Investigation Step |
| --- | --- | --- |
| Total CPU still low, write p99 high | "Need to double the nodes" | Inspect hot ranges and write/key distribution. |
| UUIDv4 PK yet slow inserts | "UUID isn't working" | Check timestamp-leading indexes, mutation counts, quotas, and transaction conflicts. |
| One tenant has high p99 | "Whole DB lacks capacity" | Measure per-tenant QPS/row hotspots, key prefix, and transaction scope. |
| Queries by CourseId scan too much data | "Must change PK of every table" | Inspect index/query plans first; consider a CourseId index. |
| Write p99 jumped after adding an index | "Must keep index for fast reads" | Measure write amplification and balance read/write trade-offs. |

To compare two designs, benchmark with identical **datasets, read/write ratios, tenant distributions, node/PU counts, cache profiles, and concurrency**. A lab with a few dozen rows only validates DDL/logic; **it does not prove key distribution at scale**.

## 8. Safe Hands-On Practice with a GoogleSQL Lab Database

**Goal:** create a UUID root table, a prefix-based child table, and a secondary index for course lookups; compare against sequential PK designs and evaluate query plans.

**Prerequisites:** the project must already have a **dedicated Spanner instance + GoogleSQL lab database** with approved billing/quotas. DDL changes create tables/indexes and may incur costs. Do not run on production databases; do not write real personal data. Learners should proceed only with schema-update and data-write permissions on the lab database.

### 8.1. Read Metadata Without Modifying Resources

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export INSTANCE_ID="YOUR_LAB_SPANNER_INSTANCE"
export DATABASE_ID="YOUR_LAB_GOOGLESQL_DATABASE"

gcloud config set project "$PROJECT_ID"
gcloud spanner instances describe "$INSTANCE_ID" --project="$PROJECT_ID"
gcloud spanner databases describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"
gcloud spanner databases ddl describe "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID"
~~~

**If `LabStudents` or `LabEnrollments` tables already exist, stop.** Choose an empty lab database or an authorized new namespace/name; never overwrite another team's tables. If the database uses the PostgreSQL dialect, do not run the GoogleSQL examples below.

### 8.2. DDL for Two Tables and One Index

In **Spanner Studio** for the verified lab database, apply:

~~~sql
CREATE TABLE LabStudents (
  StudentId UUID NOT NULL DEFAULT (NEW_UUID()),
  DisplayName STRING(100) NOT NULL,
) PRIMARY KEY (StudentId);

CREATE TABLE LabEnrollments (
  StudentId UUID NOT NULL,
  EnrollmentId UUID NOT NULL DEFAULT (NEW_UUID()),
  CourseId STRING(64) NOT NULL,
  Status STRING(24) NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
) PRIMARY KEY (StudentId, EnrollmentId),
  INTERLEAVE IN PARENT LabStudents ON DELETE CASCADE;

CREATE INDEX LabEnrollmentsByCourse
ON LabEnrollments(CourseId, StudentId)
STORING (Status, CreatedAt);
~~~

**Why this design?** UUIDv4 `StudentId` provides well-distributed root IDs, while `(StudentId, EnrollmentId)` groups enrollments per student. The `CourseId` index supports course-based lookups without changing the child table's PK.

### 8.3. Testing Two Query Paths

Create a test student and save the returned UUID:

~~~sql
INSERT INTO LabStudents (DisplayName)
VALUES ('Demo student')
THEN RETURN StudentId;
~~~

Then pass the **`@student_id` UUID parameter** from the result and a lab course ID in an application or Spanner Studio with bind parameter support:

~~~sql
INSERT INTO LabEnrollments
  (StudentId, CourseId, Status, CreatedAt)
VALUES
  (@student_id, 'java-basic-lab', 'ACTIVE', CURRENT_TIMESTAMP())
THEN RETURN EnrollmentId;

-- Read path by StudentId (primary key prefix).
SELECT EnrollmentId, CourseId, Status
FROM LabEnrollments
WHERE StudentId = @student_id;

-- Read path by CourseId (can use secondary index).
SELECT StudentId, Status, CreatedAt
FROM LabEnrollments
WHERE CourseId = 'java-basic-lab';
~~~

Never concatenate the returned UUID into SQL strings manually; use client parameter binding. Inspect the query plan in Spanner Studio or via a read-only `gcloud` command:

~~~bash
gcloud spanner databases execute-sql "$DATABASE_ID" \
  --instance="$INSTANCE_ID" --project="$PROJECT_ID" \
  --sql="SELECT StudentId, Status FROM LabEnrollments WHERE CourseId = 'java-basic-lab'" \
  --query-mode=PLAN
~~~

Observe whether Spanner selects the index; with tiny datasets, the optimizer may pick another valid plan. To force an index explicitly in **GoogleSQL**, use an index hint after confirming the index exists:

~~~sql
SELECT StudentId, Status, CreatedAt
FROM LabEnrollments@{FORCE_INDEX=LabEnrollmentsByCourse}
WHERE CourseId = 'java-basic-lab';
~~~

**Lab evidence:** root table uses UUID, child shares the parent prefix, queries by `StudentId` and `CourseId` return accurate results, and the query plan is inspected. **Do not** claim hotspot immunity was proven from a few small INSERTs.

### 8.4. Cleaning Up Created Resources

After recording results, drop only **the lab tables and index** if permitted by the owner. With interleaved tables, drop **children/indexes before parents** in dependency order. Do not delete the entire database/instance because they may be shared; never run `DROP TABLE` on an unverified environment.

~~~sql
-- Only for the exact lab database after verifying name/owner.
DROP INDEX LabEnrollmentsByCourse;
DROP TABLE LabEnrollments;
DROP TABLE LabStudents;
~~~

If your environment prohibits schema modifications, complete the lab **on paper**: explain key ordering, read paths, and a Key Visualizer validation plan. You do not need to create new projects, instances, or databases just for the theory portion.

## 9. Design Exercises and Solutions

### Exercise A — Time-Ordered Signup Events

A table receives **8,000 inserts/s** from many Cloud Run instances:

~~~sql
CREATE TABLE SignupEvents (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(64) NOT NULL,
  UserId STRING(64) NOT NULL,
) PRIMARY KEY (CreatedAt, EventId);
~~~

**Prompt:** explain why adding Spanner nodes may not solve write p99, and propose two alternative designs.

**Solution:** `CreatedAt` increases monotonically as the leading PK column, funneling writes to the head/tail of the keyspace. Option 1: use `EventId UUIDv4` as PK and add targeted indexes without accidentally creating a timestamp-leading index. Option 2: `(ShardId, CreatedAt DESC, EventId)` using a distributed hash so writes spread across multiple ranges; recent-event queries will need to fan out across N shards and merge. Verify with Key Visualizer rather than testing with a few hundred rows.

### Exercise B — Skewed Multi-Tenant Load

A SaaS has **200 tenants**, yet one tenant generates **70% of writes**. The team proposes `PRIMARY KEY(TenantId, CreatedAt, EventId)`.

**Prompt:** what risk remains, and when should you add a shard?

**Solution:** rows for each tenant cluster by prefix, but the "whale" tenant still writes sequentially into a time-ordered key range. Consider `(TenantId, ShardId, CreatedAt DESC, EventId)` with a deterministic hash shard and measure load; accept fan-out for tenant-wide queries. If tenants write lightly or queries demand extreme locality, extra sharding may not be worthwhile.

### Exercise C — Bidirectional Queries for Enrollments

The application needs to **(1)** find all enrollments for a student and **(2)** list students enrolled in a course. You chose `PRIMARY KEY(StudentId, EnrollmentId)`.

**Prompt:** how do you satisfy the second query without redoing the PK?

**Solution:** add a secondary index led by `CourseId`, such as `(CourseId, StudentId)`; use `STORING` for frequently queried columns to avoid base-table lookups if worth the cost. Measure index maintenance overhead and avoid redundant indexes. If the child PK interleaves under the student parent, consider lifetime/`ON DELETE` behavior and per-student data size.

### Exercise D — Natural Keys and Uniqueness

The system allows email signup. A designer wants `Email` as the PK because it is human-readable, but emails can **change** and the same address may appear in independent tenants.

**Prompt:** how should you design the key and unique constraint?

**Solution:** use a **stable surrogate key** (e.g., `StudentId UUIDv4`) as the PK; store `TenantId` and **canonicalized** Email as business columns, and add a **tenant-scoped unique index** if required. Canonicalization must follow clear rules, and a `UNIQUE NULL_FILTERED` index does not enforce uniqueness for filtered-out NULL rows. Changing an email then avoids migrating every child key.

### Exercise E — Estimating Write Amplification

A table receives **5,000 inserts/s**. Each INSERT touches one base row and **three** secondary indexes, excluding other internal overhead.

**Prompt:** estimate the number of logical object updates and explain why this figure is not the number of RPCs or physical writes.

**Solution:** in a simplified model, expect **5,000 × (1 + 3) = 20,000 logical object updates/second** (base + index entries). This is **not** the number of RPCs or physical writes due to batching, transactions, internals, schema/index coverage, and implementation differences. The takeaway is that every additional index incurs meaningful maintenance cost.

### Exercise F — Hot Counter in a Well-Distributed Table

The `Payments` table uses an evenly distributed UUIDv4 PK, yet every transaction runs `UPDATE DailyTotals SET Total = Total + ... WHERE Day = @today`. Latency p99 climbs and transactions abort frequently.

**Prompt:** why doesn't UUIDv4 save you here, and how can you improve it?

**Solution:** the single hot row `DailyTotals(@today)` is a write contention point. You can split counters across multiple shards and sum on read/periodically, or compute via streaming analytics if immediate consistency isn't required. For money, maintain an idempotent ledger and reconciliation; never replace an exact tally with an approximate counter when business rules require precision.

## 10. Pre-Production Schema Review Checklist

| Question | Acceptance Criterion |
| --- | --- |
| Is the PK stable, unique, and non-identifying? | Clear invariant; mutable emails are not accidentally used as parent keys. |
| Is the leading key column sequential under heavy writes? | No, or hotspot mitigation is designed and proven via benchmarks. |
| Do common queries have matching key/index prefixes? | Query plans and latencies meet SLOs on representative data. |
| Do interleaving/foreign keys serve real relationships? | Chosen for locality/integrity, not blindly interleaving every relation. |
| Are hot tenants or oversized parents isolated? | Distribution data, headroom, and shard/fan-out plans exist. |
| Do secondary indexes cause hot writes or excessive cost? | Leading index keys, storage, and write amplification verified. |
| Can DDL migrations/rollbacks be executed safely? | Backfill, data reconciliation, cutover/rollback plans, and owner assigned. |
| Is monitoring sufficient to catch key design flaws? | Cloud Monitoring, query metrics, Key Visualizer, and alert/incident runbooks ready. |
| Is multi-tenant security enforced at the app layer? | IAM/database roles and authorization enforced; PK prefix is not a security boundary. |

### Self-Check

1. **Why does an ascending `OrderId` heat up one split?** — Continuous inserts target the same edge of one key range, regardless of how many machines Spanner has.
2. **Where does UUIDv4 excel?** — Spreading inserts across the keyspace; not for chronological ordering.
3. **How does a bit-reversed sequence differ from a normal ascending sequence?** — Values are bit-reversed to avoid piling writes at one end; do not use it for contiguous sequential numbering.
4. **Why is the first column of a composite key crucial?** — It shapes locality and range scans/prefix filters, directly impacting write distribution.
5. **Is interleaving identical to a foreign key?** — No; interleaving also governs physical locality and requires the parent key prefix.
6. **Why can an index be hot when the PK is not?** — An index has its own keyspace, e.g., an index led by an ascending timestamp.
7. **Is `STORING` free?** — No; it consumes storage and adds index maintenance overhead on data changes.
8. **What is the trade-off of hash sharding?** — It distributes writes, but tenant-wide time queries must read and merge across multiple shards.
9. **What does changing the PK of a table with millions of rows entail?** — Usually a schema + data + query-contract migration involving backfill, cutover, and rollback planning.
10. **Can 20 lab INSERTs prove hotspot resistance?** — No; you need load testing and Key Visualizer on a representative data distribution.

## 11. Official Documentation

- [Spanner — Schema and data model](https://cloud.google.com/spanner/docs/schema-and-data-model): row ordering, splits, interleaved tables, and foreign keys.
- [Spanner — Schema design best practices](https://cloud.google.com/spanner/docs/schema-design): avoiding sequential key hotspots, hash sharding, and key order.
- [Spanner — Primary key default values](https://cloud.google.com/spanner/docs/primary-key-default-value): UUIDv4, `IDENTITY`, and bit-reversed sequences.
- [Spanner — Primary keys overview](https://cloud.google.com/spanner/docs/primary-keys-overview): how Spanner distributes keys and migrations.
- [Spanner — Migrate primary keys](https://cloud.google.com/spanner/docs/migrating-primary-keys): migrating legacy keys and avoiding sequence collisions.
- [Spanner — Secondary indexes](https://cloud.google.com/spanner/docs/secondary-indexes): indexes, `STORING`/`INCLUDE`, null filtering, and unique constraints.
- [Spanner — GoogleSQL DDL](https://cloud.google.com/spanner/docs/reference/standard-sql/data-definition-language): syntax for creating tables, PKs, and interleaving.
- [Spanner — Schema updates](https://cloud.google.com/spanner/docs/schema-updates): schema changes and online index backfills.
- [Spanner — Key Visualizer](https://cloud.google.com/spanner/docs/key-visualizer): heatmaps to detect hot key ranges.
- [Spanner — Commit timestamps](https://cloud.google.com/spanner/docs/commit-timestamp): timestamp semantics and hotspot risks.
- [Spanner — Time to live](https://cloud.google.com/spanner/docs/ttl): asynchronous data deletion policies.
- [gcloud spanner databases ddl describe](https://cloud.google.com/sdk/gcloud/reference/spanner/databases/ddl/describe) and [execute-sql](https://cloud.google.com/sdk/gcloud/reference/spanner/databases/execute-sql): inspecting DDL and query plans.

**Conclusion:** in Spanner, a primary key defines both **row identity** and **how data and write load are distributed**. Use UUIDv4/bit-reversed sequences when spreading inserts, composite keys when business locality is needed, and sharding when a group becomes too hot—while also checking secondary indexes, interleaving, and transaction hotspots. A design is only trustworthy once **query patterns, p99 latency, Key Visualizer, cost, and migration paths** are validated on a representative workload.
