# Single-Table Design and Data Relationship Modeling

> **Chapter:** DynamoDB  
> **Module:** CLOUD_PROVIDERS_AWS — exploring AWS across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; building skills to select services, design and deploy secure applications, monitor, recover, and control costs.

## Learning Objectives

In relational databases, we usually start with **entities, foreign keys, and data normalization**, then write SQL JOINs to combine information. With **Amazon DynamoDB**, a managed NoSQL key-value/document database from AWS, effective design starts instead from **the queries and mutations the application must execute**. Single-table design (STD) is a technique for organizing **multiple entity types and relationships inside a single table**, using **partition keys (PK)**, **sort keys (SK)**, item collections, and secondary indexes to serve key access patterns with minimal read calls.

This lesson uses a **multi-tenant online learning platform** example. Students enroll in multiple courses; each course has many students and many lessons. A Java application needs fast reads for profiles, course content, bidirectional enrollment lists, and published catalogs while enforcing tenant boundaries.

By the end of this lesson, learners will be able to:

1. Explain that **single-table design is a design pattern**, not a rule that "every app must have only one table."
2. Catalog, size, and prioritize **access patterns before picking keys**.
3. Construct composite `PK`/`SK` keys, entity-type namespaces, and **item collections**.
4. Model **one-to-one, one-to-many, and many-to-many** relationships without hot-path JOINs.
5. Use **GSIs, LSIs, sparse indexes, and overloaded indexes**, evaluating trade-offs against duplication.
6. Understand Query vs. Scan, `KeyConditionExpression`, pagination, consistency, and size limits.
7. Apply **conditional writes, optimistic locking, transactions, and idempotency** to enforce business invariants.
8. Plan for hot partitions, skew, capacity, cost, backup/PITR, and data migrations.
9. Express models using tables, Mermaid diagrams, JSON, AWS CLI, and Java AWS SDK v2 examples.
10. Decide when to choose **single-table, multi-table, or a hybrid model**.

## 1. Access-Pattern-First Mindset

### 1.1. DynamoDB Is Not an RDBMS with Different Syntax

In an RDBMS, you might model:

~~~sql
CREATE TABLE student (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200)
);
CREATE TABLE course (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(300)
);
CREATE TABLE enrollment (
    student_id VARCHAR(64),
    course_id VARCHAR(64),
    enrolled_at TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);
~~~

And then query relationships with `JOIN`. DynamoDB does not provide RDBMS-style **SQL JOINs** in its query API. Even though **PartiQL** offers SQL-like syntax for interacting with tables, it does not turn DynamoDB into a relational join/foreign-key engine.

Therefore, for frequent read paths, we structure items to query by **PK equality + SK range/prefix**, or via a **GSI** keyed for that access pattern.

### 1.2. What Is Single-Table Design?

Instead of separate tables for `Students`, `Courses`, `Lessons`, and `Enrollments`, we can use one table `LearningCore` storing distinct item types:

~~~text
Table: LearningCore
Primary key: PK (String), SK (String)

PK                              SK                       Entity
TENANT#t1#USER#u1               PROFILE                  USER
TENANT#t1#COURSE#c1             META                     COURSE
TENANT#t1#COURSE#c1             LESSON#0001#l1           LESSON
TENANT#t1#COURSE#c1             LESSON#0002#l2           LESSON
TENANT#t1#COURSE#c1             ENROLLMENT#u1            ENROLLMENT
TENANT#t1#COURSE#c1             ENROLLMENT#u2            ENROLLMENT
~~~

**Not every item has to carry the same attributes.** A `COURSE` item has `title` and `category`, whereas an `ENROLLMENT` item has `status`, `studentId`, and `enrolledAt`. Only the table/index key attributes must conform to the declared schema types.

### 1.3. When Is This Approach Helpful?

| Workload characteristic | Worth considering single-table? | Why |
|---|---|---|
| Frequent queries fetching a course and its lessons together | Yes | Items can co-locate under one PK |
| Traversing relationships course → students and vice versa | Yes, via base + GSI | Routes bidirectional access around access patterns |
| Workloads with independent entities rarely read together | Maybe not | Multi-table is simpler |
| Entities needing distinct backups, KMS keys, TTL, or table classes | Usually consider multi-table | Cleaner per-table operational boundaries |
| Rapidly shifting schemas, heavy ad-hoc/analytics queries | Usually consider RDBMS/warehouse | STD requires anticipating access patterns |
| Multi-tenant data requiring tenant-specific table encryption | Consider table-per-tenant | A shared table cannot meet every isolation policy |

**AWS does not require every application to use single-table design.** Modern AWS guidance presents multi-table and aggregate designs as equally valid options depending on access correlation and operational requirements.

### 1.4. Recommended Workflow

~~~mermaid
flowchart TD
    A[Business requirements] --> B[List entities and relationships]
    B --> C[List access patterns / QPS / latency]
    C --> D[Define PK, SK, and item collections]
    D --> E[Verify every pattern via GetItem/Query]
    E --> F{Any new access patterns?}
    F -->|Yes| G[Add GSI / sparse GSI / controlled duplication]
    G --> H[Evaluate write costs and consistency]
    F -->|No| H
    H --> I[Load test, hot keys, pagination, security]
    I --> J[Finalize data contract + migration/runbook]
~~~

**Do not do this:** draw an ERD, mechanically convert every table into items, and rely on `Scan + FilterExpression` to mimic joins. That pattern wastes read capacity and degrades latency at scale.

## 2. Access Patterns Before Creating the Table

### 2.1. Multi-Tenant Education Domain

Entities:

- **Tenant/school:** owns many students and courses.
- **Student/user:** has a profile; can enroll in multiple courses.
- **Course:** has metadata, multiple lessons, and enrollment records.
- **Lesson:** belongs to a course, with an ordering position.
- **Enrollment:** **many-to-many** relationship between users and courses, with `status`/`enrolledAt`.
- **Published catalog:** listing published courses by category.

### 2.2. Query Matrix

| ID | Caller | What to fetch | Illustrative frequency | Target access path |
|---|---|---|---|---|
| AP1 | Profile API | User profile by ID | 500 QPS | Base `GetItem` by PK/SK |
| AP2 | Course API | Single course metadata | 1,000 QPS | Base `GetItem` by PK/SK |
| AP3 | Course page | Ordered lessons of a course | 300 QPS | Base `Query` PK + `begins_with(SK)` |
| AP4 | Teacher portal | Students enrolled in a course | 200 QPS | Base `Query` PK + enrollment prefix |
| AP5 | Student dashboard | Courses a user enrolled in | 700 QPS | `Query` GSI1 by user |
| AP6 | Enrollment service | Is user already enrolled in course? | 300 QPS | Direct edge `GetItem` |
| AP7 | Public catalog | Published courses by category, newest first | 400 QPS | `Query` sparse GSI2 |
| AP8 | Admin | Update status of an enrollment | 100 WPS | Conditional/transactional `UpdateItem` |
| AP9 | Reporting | Monthly enrollment summaries | Batch | S3 export/analytics; never hot API Scan |

These figures are **estimation exercises**; collect real telemetry. Every access pattern should also document **p95/p99 latency, items per query, item sizes, consistency needs, read/write ratio, and data sensitivity**.

### 2.3. Do Not Design Only for Today's Questions

A design spec should look like:

~~~text
AccessPattern:
  id: AP5
  operation: List courses enrolled by user
  input: tenantId, userId, pageSize, nextToken
  frequency: 700 requests/second at peak
  expectedResponse: up to 30 enrollments/page
  consistency: eventual acceptable for dashboard
  requiredAttributes: courseId, status, enrolledAt, courseTitleSnapshot
  authz: caller may query only own tenant/user unless staff
  storagePath: GSI1PK + GSI1SK
~~~

If product later asks to "find a user by email without knowing user ID," evaluate adding an index or search service—never quietly fall back to a full-table scan per request.

## 3. PK/SK and Item Collections

### 3.1. Partition Key and Sort Key

A DynamoDB table can use:

- **Simple primary key:** partition key only—one item per PK.
- **Composite primary key:** partition key + sort key—multiple items can share a PK with distinct SKs.

In our example:

~~~text
PK = "TENANT#" + tenantId + "#COURSE#" + courseId
SK = "LESSON#" + zeroPaddedOrder + "#" + lessonId
~~~

An item is uniquely identified by **(PK, SK)**; writing the same key pair again **replaces the existing item** unless guarded by a condition expression.

### 3.2. What Is an Item Collection?

An **item collection** is the set of items sharing the **same base-table partition key value**.

~~~text
PK = TENANT#t1#COURSE#c1
 ├── SK=META
 ├── SK=LESSON#0001#l1
 ├── SK=LESSON#0002#l2
 ├── SK=ENROLLMENT#u1
 └── SK=ENROLLMENT#u2
~~~

This provides **logical co-location** so `Query PK=...` retrieves related items together. Never claim all items sharing a PK stay pinned to **one fixed physical partition**: DynamoDB uses adaptive capacity and split-for-heat under eligible conditions, especially when **no LSI exists**. What matters is distributing load evenly enough to prevent hot keys.

### 3.3. Key Conventions for Multi-Tenant Design

Proposed pattern:

~~~text
PK = TENANT#<tenantId>#<ENTITY>#<entityId>
SK = <ITEM_TYPE>[#<orderedSuffix>]

Examples:
PK = TENANT#t1#USER#u1
SK = PROFILE

PK = TENANT#t1#COURSE#c1
SK = META
~~~

All access keys (including GSI partition keys if enforcing per-tenant IAM) start with a stable tenant prefix. **Key values are an application contract**, carrying no special meaning to DynamoDB; `#` is just a chosen delimiter.

Never concatenate unvalidated input straight into keys. Validate tenant/user/course identifiers, normalize encoding/casing, and prevent user-controlled delimiters from causing key collisions.

### 3.4. Composite Sort Keys and Prefix Queries

Examples:

~~~text
SK = META
SK = LESSON#0001#l1
SK = LESSON#0002#l2
SK = ENROLLMENT#u1
SK = ENROLLMENT#u2
SK = STATS
~~~

Given a course PK, you can:

- `GetItem PK=courseKey SK=META` for metadata;
- `Query PK=courseKey AND begins_with(SK, "LESSON#")` for lessons;
- `Query PK=courseKey AND begins_with(SK, "ENROLLMENT#")` for enrollments;
- `Query PK=courseKey` for all item types in the collection (watch size and pagination).

**An SK prefix alone works whenever the tenant/course PK is known.** DynamoDB cannot Query by SK without PK equality on the queried index.

### 3.5. Sort Order Is Not Insertion Order

If the sort key is **String**, DynamoDB orders by UTF-8 bytes rather than numerical values:

~~~text
LESSON#1
LESSON#10
LESSON#2
~~~

For correct ordering, use **zero-padded sequences**:

~~~text
LESSON#0001
LESSON#0002
LESSON#0010
~~~

For timestamps, use fixed-format UTC ISO-8601 strings such as `2026-11-20T03:00:00Z` so lexicographical order matches chronological order for uniform precision/timezone. Never mix `+07:00` and `Z` in one sort range if comparing directly.

### 3.6. Avoid Oversized Single Items

DynamoDB caps **each item at 400 KiB** (including attribute names and values per AWS sizing rules). Never pack a list of 100,000 lessons or enrollments into **one** item.

Choose wisely:

- **Nested document in one item:** good for small data updated together with bounded cardinality.
- **Multiple items under one PK:** good for large one-to-many sets needing pagination or independent updates.
- **Private S3 object + metadata pointer in DynamoDB:** good for videos, PDFs, or large blobs.

## 4. Designing a Queryable Sample Schema

### 4.1. The `LearningCore` Table

Logical key schema:

~~~text
Table name: LearningCore
PK: String
SK: String

Optional projected index-key attributes:
GSI1PK: String
GSI1SK: String
GSI2PK: String
GSI2SK: String
~~~

Not every item needs `GSI1PK` or `GSI2PK`. Only items containing all required index-key attributes enter the corresponding GSI. Ensure values match the types declared in the index key schema.

### 4.2. Sample Items

| Entity | PK | SK | Other data | Index keys |
|---|---|---|---|---|
| USER | `TENANT#t1#USER#u1` | `PROFILE` | name, emailHash, createdAt | none |
| COURSE | `TENANT#t1#COURSE#c1` | `META` | title, category, visibility, publishedAt | `GSI2PK=TENANT#t1#CATEGORY#java`, `GSI2SK=PUBLISHED#2026-11-20T03:00:00Z#COURSE#c1` if published |
| LESSON | `TENANT#t1#COURSE#c1` | `LESSON#0001#l1` | title, videoS3Key, duration | none |
| ENROLLMENT | `TENANT#t1#COURSE#c1` | `ENROLLMENT#u1` | userId, status, enrolledAt, titleSnapshot | `GSI1PK=TENANT#t1#USER#u1`, `GSI1SK=ENROLLMENT#c1` |
| ENROLLMENT | `TENANT#t1#COURSE#c1` | `ENROLLMENT#u2` | userId, status, enrolledAt, titleSnapshot | `GSI1PK=TENANT#t1#USER#u2`, `GSI1SK=ENROLLMENT#c1` |

Everything lives in **one table**, yet entity types and key namespaces stay crisp. `titleSnapshot` is a **denormalized field**: if the course title changes, enrollment snapshots can lag; define the consistency contract upfront.

### 4.3. JSON Representation of a User Item

This is logical application JSON, **not** AWS CLI `AttributeValue` format:

~~~json
{
  "PK": "TENANT#t1#USER#u1",
  "SK": "PROFILE",
  "entityType": "USER",
  "userId": "u1",
  "displayName": "Student 1",
  "createdAt": "2026-11-20T03:00:00Z"
}
~~~

### 4.4. JSON Representation of a Course Item and Sparse Catalog

~~~json
{
  "PK": "TENANT#t1#COURSE#c1",
  "SK": "META",
  "entityType": "COURSE",
  "courseId": "c1",
  "title": "Java on AWS",
  "category": "java",
  "visibility": "PUBLISHED",
  "publishedAt": "2026-11-20T03:00:00Z",
  "GSI2PK": "TENANT#t1#CATEGORY#java",
  "GSI2SK": "PUBLISHED#2026-11-20T03:00:00Z#COURSE#c1"
}
~~~

When a course is `DRAFT`, **omit `GSI2PK`/`GSI2SK`** so it never enters the catalog GSI. When transitioning `PUBLISHED → DRAFT`, **REMOVE** both index-key attributes per the data contract. Never update only `visibility` expecting the index to hide the course automatically.

### 4.5. JSON Representation of an Enrollment (Edge)

~~~json
{
  "PK": "TENANT#t1#COURSE#c1",
  "SK": "ENROLLMENT#u1",
  "entityType": "ENROLLMENT",
  "userId": "u1",
  "courseId": "c1",
  "status": "ACTIVE",
  "enrolledAt": "2026-11-20T03:05:00Z",
  "GSI1PK": "TENANT#t1#USER#u1",
  "GSI1SK": "ENROLLMENT#c1"
}
~~~

Each enrollment is **one edge item representing the relationship**. Course → students uses the **base table**; user → courses uses **GSI1**. You do not need two symmetric enrollment items if GSI1 meets latency and consistency requirements. However, GSI1 eventual consistency can delay dashboard updates right after enrollment—handle display or fallback reads on the writer path.

### 4.6. Item Collection Diagram

~~~mermaid
flowchart TD
    T[(LearningCore)] --> U["PK TENANT#t1#USER#u1"]
    T --> C["PK TENANT#t1#COURSE#c1"]
    U --> P["SK PROFILE"]
    C --> M["SK META"]
    C --> L1["SK LESSON#0001#l1"]
    C --> L2["SK LESSON#0002#l2"]
    C --> E1["SK ENROLLMENT#u1"]
    C --> E2["SK ENROLLMENT#u2"]
    E1 -. "GSI1PK=TENANT#t1#USER#u1" .-> U
    M -. "GSI2PK=TENANT#t1#CATEGORY#java" .-> CAT[Catalog GSI2]
~~~

## 5. Modeling Data Relationships

### 5.1. One-to-One

For example, each user has one profile:

~~~text
PK=TENANT#t1#USER#u1  SK=PROFILE
~~~

If auth metadata and display fields are small and always read together, embed them in one item. If secrets, audit logs, or PII carry stricter read permissions, store them in a separate item/table/resource with dedicated IAM/DB authorization.

### 5.2. One-to-Many: Course → Lessons

~~~text
PK=TENANT#t1#COURSE#c1
  SK=META
  SK=LESSON#0001#l1
  SK=LESSON#0002#l2
  SK=LESSON#0003#l3
~~~

A `Query` with `begins_with(SK, "LESSON#")` returns lessons in SK order. Lessons update independently and scale without hitting the 400 KiB limit of a single embedded list.

**Trade-off:** if a course had millions of lessons/events or a viral course took heavy writes onto one PK, split into bucketed/sectioned item collections—accepting multiple queries/fan-out to read the full set.

### 5.3. Many-to-Many: Student ↔ Course

~~~mermaid
flowchart LR
    U1[User u1] -->|enrolled| C1[Course c1]
    U1 -->|enrolled| C2[Course c2]
    U2[User u2] -->|enrolled| C1
    U2 -->|enrolled| C3[Course c3]
~~~

**Edge item model**:

~~~text
Base table:
  PK=TENANT#t1#COURSE#c1
  SK=ENROLLMENT#u1

GSI1:
  GSI1PK=TENANT#t1#USER#u1
  GSI1SK=ENROLLMENT#c1
~~~

Consequences:

- List students in a course: base `Query`.
- List courses for a user: GSI1 `Query`.
- Check if a user is enrolled: base `GetItem` by PK/SK.
- Update enrollment status: one `UpdateItem` on the base item; the GSI updates index keys and projected attributes automatically.
- If GSI1 projects `KEYS_ONLY`, the dashboard must fetch base items afterward; projecting needed fields adds storage and write costs.

**Not an RDBMS foreign key:** DynamoDB does not verify that the course or user exists when creating an edge; enforce this via condition checks, transactions, or application rules.

### 5.4. Adjacency List: When Relationships Are More Complex

An **adjacency list** models nodes and edges under each node's partition key. For multi-type graphs:

~~~text
PK=NODE#course-c1  SK=META
PK=NODE#course-c1  SK=EDGE#STUDENT#u1
PK=NODE#user-u1    SK=META
PK=NODE#user-u1    SK=EDGE#COURSE#c1
~~~

A **dual-edge** approach supports bidirectional base-table queries, but stores **two copies of each relationship**, requiring transactional writes/deletes to stay in sync. Our main example uses **single-edge + GSI** because it is simpler to manage for the known access patterns.

When to pick dual-edge? When **both directions** require strong consistency on the base table, or permissions/latency rule out eventual GSIs. When to pick single-edge + GSI? When eventual consistency on the reverse direction is fine, cutting duplicate base items and writes.

### 5.5. Do Not Turn a GSI into a DB JOIN Engine

If an API needs a user profile plus 100 course metadata items, you can:

- Query enrollment edges on GSI1 projecting `courseId` and `titleSnapshot`;
- Or fetch `courseId`s and call `BatchGetItem` for course META (handling pagination and `UnprocessedKeys`);
- Or adjust the response contract to return course summaries and lazy-load details.

Never query N enrollments and issue N sequential `GetItem` calls in a loop when you can batch and bound requests. That is the classic ORM **N+1** problem happening over DynamoDB APIs.

## 6. GSI and LSI: Querying the Second Dimension

### 6.1. What Is a GSI?

A **Global Secondary Index (GSI)** defines partition/sort keys **different** from the base table. DynamoDB updates the index asynchronously from table mutations under **eventual consistency**.

In our example:

~~~text
Base key: PK, SK

GSI1:
  Partition key: GSI1PK
  Sort key:      GSI1SK

GSI2:
  Partition key: GSI2PK
  Sort key:      GSI2SK
~~~

GSI1 looks up enrollments by user. GSI2 lists published courses by category. **You cannot perform strongly consistent reads from a GSI**, even when the base table supports `ConsistentRead=true`.

### 6.2. How Does an LSI Differ from a GSI?

| Aspect | GSI | LSI |
|---|---|---|
| Partition key | Can differ from base PK | **Same as base PK** |
| Sort key | Can differ from base SK | Different from base SK |
| Added after table creation | Yes, within AWS limits | **No**; only at table creation |
| Consistency | **Eventual only** | Eventual or strong |
| Item collection size | Not subject to LSI's 10 GB constraint | **10 GB limit** on base collection + LSI entries |
| Capacity | Dedicated index consumption and throttling | Consumes base table capacity per semantics |
| Backfill | Adding a GSI to an existing table backfills | Cannot add an LSI afterward |

**State the 10 GB limit accurately:** it applies only when a table has at least one **LSI**, summing base items and projected index entries for **one PK value**. A single-table design **with no LSIs** does not face that fixed 10 GB item-collection ceiling, though other size/throughput/quota limits still apply.

### 6.3. Sparse GSI

A GSI indexes an item only if all required index key attributes are present with valid types. This enables **sparse indexing**:

~~~text
COURSE c1 DRAFT:
  no GSI2PK, no GSI2SK  -> not indexed

COURSE c2 PUBLISHED:
  GSI2PK=TENANT#t1#CATEGORY#java
  GSI2SK=PUBLISHED#2026-11-20T03:00:00Z#COURSE#c2
  -> indexed
~~~

A GSI2 `Query` by category scans only published courses matching that category. Advantage: no `FilterExpression` over drafts. Drawback: you must update keys **whenever status/category changes**, managing consistency and propagation.

### 6.4. Index Overloading

**Overloading** reuses one GSI across multiple entity types and access patterns via distinct key namespaces:

~~~text
GSI1PK=TENANT#t1#USER#u1
GSI1SK=ENROLLMENT#c1

GSI1PK=TENANT#t1#INSTRUCTOR#u2
GSI1SK=COURSE#c1

GSI1PK=TENANT#t1#COUPON#abc
GSI1SK=REDEMPTION#u3
~~~

Requirements: clean namespace separation, never mixing unrelated item types in one Query, and accounted projections/capacity costs. Never overload an index purely to minimize GSI count—it obscures code, increases coupling, and complicates authorization.

### 6.5. Projections and Write Amplification

GSI projection options:

- `KEYS_ONLY`: minimal storage/write cost; requires base-table reads if extra fields are needed.
- `INCLUDE`: copies only specific attributes needed by the query.
- `ALL`: copies every attribute into the index entry; convenient, but expensive and increases write amplification.

For the AP5 dashboard, project `courseId`, `status`, `enrolledAt`, and `titleSnapshot`. For the AP7 catalog, project `title`, `category`, and `publishedAt`. Choose based on the **response contract**, never `ALL` by reflex.

### 6.6. GSI Hot Partitions Can Also Throttle

A GSI2 key like `TENANT#t1#CATEGORY#java` can run hot if the whole platform queries/updates the Java category heavily. Even when base PKs distribute evenly, a **GSI partition key** can become its own hotspot.

For heavy workloads, consider key sharding:

~~~text
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#00
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#01
...
GSI2PK=TENANT#t1#CATEGORY#java#SHARD#0f
~~~

Drawback: the catalog API must **Query multiple shards, merge-sort, and paginate**, raising complexity and request count. Shard only after measuring real traffic skew and considering caching.

## 7. GetItem, Query, Scan, and Pagination

### 7.1. Mapping Every Access Pattern to an API

| Access pattern | API | Query key | Index |
|---|---|---|---|
| AP1 — user profile | `GetItem` | `PK=TENANT#t1#USER#u1, SK=PROFILE` | Base |
| AP2 — course metadata | `GetItem` | `PK=TENANT#t1#COURSE#c1, SK=META` | Base |
| AP3 — lessons by course | `Query` | `PK=:course AND begins_with(SK,"LESSON#")` | Base |
| AP4 — enrollments by course | `Query` | `PK=:course AND begins_with(SK,"ENROLLMENT#")` | Base |
| AP5 — enrollments by user | `Query` | `GSI1PK=:user AND begins_with(GSI1SK,"ENROLLMENT#")` | GSI1 |
| AP6 — check if user enrolled | `GetItem` | `PK=:course, SK=ENROLLMENT#userId` | Base |
| AP7 — published catalog | `Query` | `GSI2PK=:category`, appropriate sort key | GSI2 |

**If a query knows only an email while the schema lacks an email lookup**, DynamoDB cannot synthesize a JOIN or a Query on a non-key attribute. Add an index/access pattern or update the API contract to supply user ID.

### 7.2. GetItem with a Composite Key

Check whether `u1` enrolled in course `c1`:

~~~text
PK = TENANT#t1#COURSE#c1
SK = ENROLLMENT#u1
~~~

`GetItem` is direct key access. To read a just-committed base-table write in the same Region, set `ConsistentRead=true`. Never pass `ConsistentRead` on a GSI.

### 7.3. Query Requires Partition-Key Equality

~~~text
KeyConditionExpression:
    PK = :pk AND begins_with(SK, :prefix)

:pk     = "TENANT#t1#COURSE#c1"
:prefix = "LESSON#"
~~~

DynamoDB requires equality on PK plus an optional SK condition such as `begins_with`, `BETWEEN`, or range comparisons. `ScanIndexForward=false` reverses SK order.

**You cannot Query solely with `begins_with(SK,"LESSON#")` without PK equality** on the target index. Fetching all lessons across all courses requires a dedicated index/access pattern or batch analytics.

### 7.4. FilterExpression Does Not Save Read Capacity

Suppose a course has 20,000 enrollments, of which 300 are active:

~~~text
KeyCondition:
    PK = :course AND begins_with(SK, "ENROLLMENT#")

FilterExpression:
    #status = :active
~~~

`FilterExpression` runs **after DynamoDB reads items matching the key condition**. It does not reduce read capacity consumed for read items. `ProjectionExpression` trims bytes sent over the network, without shrinking the item size DynamoDB meters for base-table Query capacity.

To query active enrollments at high scale, encode status into **SK or a sparse GSI key**, e.g.:

~~~text
GSI3PK=TENANT#t1#COURSE#c1#STATUS#ACTIVE
GSI3SK=ENROLLED#2026-11-20T03:05:00Z#USER#u1
~~~

Every GSI adds write/storage cost and potential hotspots, so measure before adding.

### 7.5. 1 MB Limit per Query Call

`Query` reads up to roughly **1 MB of data** per API call before applying filters/projections, or stops early at `Limit`. When `LastEvaluatedKey` is returned, pass it as `ExclusiveStartKey` on the next call.

~~~mermaid
flowchart TD
    R[Query PK + SK] --> P[Read up to 1 MB or Limit]
    P --> F[Apply FilterExpression if present]
    F --> O[Return Items + LastEvaluatedKey]
    O --> D{Is LastEvaluatedKey empty?}
    D -->|No| N[Query next with ExclusiveStartKey]
    N --> P
    D -->|Yes| E[Done]
~~~

**An empty `Items` page does not necessarily mean the end**: all read items may have been filtered out while `LastEvaluatedKey` remains. Conversely, a non-empty `LastEvaluatedKey` does not guarantee the next page contains matches; stop only when no cursor remains.

### 7.6. Limit and CLI Pagination

- `Limit=20` bounds **evaluated items**, not guaranteeing 20 returned items if `FilterExpression` drops rows.
- AWS CLI has its own pagination: CLI `--max-items` differs from API `--limit`.
- To inspect a single API page, use `--no-paginate --limit 20` and inspect `LastEvaluatedKey`.
- Backends should issue **opaque page tokens** bound to verified tenant auth—never let clients tamper with raw DynamoDB keys.
- Multi-page Queries do not form **a single transactional snapshot** across pages, even with strong consistency enabled per page.

### 7.7. When Is Scan Appropriate?

`Scan` fits **small sandboxes**, rate-limited migrations, offline maintenance, or batch exports/analytics. Never use Scan in hot API paths to filter by non-key fields. Even a `Query` with `FilterExpression` can be costly if a partition holds many items; always compare `ScannedCount` vs. `Count`.

## 8. Consistency, Conditional Writes, and Transactions

### 8.1. Consistency Varies by Source

| Read path | Eventual | Strong |
|---|---|---|
| Base `GetItem` | Yes | Yes |
| Base `Query` | Yes | Yes |
| LSI `Query` | Yes | Yes |
| GSI `Query` | Yes | **No** |
| DynamoDB Streams | Per stream semantics | Not a strong-read query API |

Right after putting an enrollment, a strong base `GetItem` sees the commit, whereas a user-centric GSI1 query may lag because indexes update **asynchronously**. UIs must account for this: an empty GSI check does not prove an enrollment was never created.

### 8.2. Conditional Put Prevents Duplicate Overwrites

Using a unique primary key:

~~~text
PK=TENANT#t1#COURSE#c1
SK=ENROLLMENT#u1
~~~

Unconditional `PutItem` overwrites an existing item at the same key. Block overwrites with:

~~~text
attribute_not_exists(PK) AND attribute_not_exists(SK)
~~~

If the item exists, DynamoDB raises `ConditionalCheckFailedException`. Distinguish **duplicate registration** from **infrastructure errors**; never retry condition failures blindly.

### 8.3. Optimistic Locking

An enrollment item has `version=4`. A client updates with:

~~~text
ConditionExpression: #version = :expected
UpdateExpression: SET #status = :newStatus, #version = :next
~~~

If another writer already bumped it to version 5, the condition fails, preventing a **lost update**. Under high concurrency, use backoff/jitter and clear conflict feedback to users.

### 8.4. Multi-Item Transactions

Enrolling a student may need to:

1. Verify `USER PROFILE` exists.
2. Verify `COURSE META` is open.
3. Put a new `ENROLLMENT` only if absent.
4. Update `COURSE STATS` enrollment count.

~~~mermaid
flowchart TD
    C[Enroll command] --> TX[TransactWriteItems]
    TX --> U[ConditionCheck user exists]
    TX --> M[ConditionCheck course open]
    TX --> E[Put new enrollment if not exists]
    TX --> S[Update course stats]
    U --> ALL{All succeed?}
    M --> ALL
    E --> ALL
    S --> ALL
    ALL -->|Yes| COMMIT[Atomic commit]
    ALL -->|No| STOP[No partial commit]
~~~

`TransactWriteItems` supports up to **100 write actions**, **4 MB** total, across up to 100 distinct items in the same account and Region. Actions include `Put`, `Update`, `Delete`, and `ConditionCheck`; **never target the same item twice in one transaction**.

**Important:** create the `STATS` item when creating the course. A hot counter item causes transaction conflicts on viral courses; consider sharded counters or asynchronous aggregation instead of updating one item per enrollment.

### 8.5. Transactions Do Not Mean End-to-End Exactly-Once

- Within one Region, DynamoDB transactions are **all-or-nothing** across their declared items.
- Network timeouts after commit can leave the client **unsure** if it succeeded; use idempotency keys and state reconciliation.
- `ClientRequestToken` makes identical transaction requests idempotent within AWS's defined window.
- Sending emails/notifications post-commit falls outside DynamoDB transactions; use outboxes, Streams, and event workflows.
- Transactions consume roughly double the capacity of standard operations, so benchmark carefully.

### 8.6. Dual-Edge Requires Atomicity

If modeling a relationship as two items:

~~~text
PK=COURSE#c1 SK=STUDENT#u1
PK=STUDENT#u1 SK=COURSE#c1
~~~

creating or deleting the relationship must update **both**—otherwise an orphaned edge remains. Use transactions, or choose **one edge + GSI** when eventual consistency is acceptable.

### 8.7. TTL Deletes Asynchronously

DynamoDB TTL uses a **Unix epoch timestamp in seconds**. Expired items are purged **asynchronously**, not on the exact second:

- Never rely on TTL alone to revoke access at an exact timestamp;
- Backend logic must check `expiresAt` on reads/writes requiring strict cutoffs;
- TTL fits cleaning up sessions, invitations, and temporary records;
- TTL deletions emit to Streams per AWS semantics;
- Once deleted, corresponding GSI entries are cleaned up by the service.

### 8.8. Global Tables: Do Not Claim Every Cross-Region Read Is Eventual

DynamoDB Global Tables offer modes including **Multi-Region Eventual Consistency (MREC)** and **Multi-Region Strong Consistency (MRSC)** on eligible Regions/features. However, **GSIs remain eventually consistent**, and a DynamoDB transaction **does not become an atomic global transaction across all Regions**. Choose modes based on RPO/RTO/latency, quotas/availability, and conflict-resolution rules.

## 9. Hot Partitions and Write Sharding

### 9.1. Hot PKs Create Bottlenecks

If all enrollments for a viral course hit:

~~~text
PK=TENANT#t1#COURSE#viral
SK=ENROLLMENT#userId
~~~

writes concentrate onto one logical item collection. DynamoDB provides adaptive capacity and can split hot collections under eligible conditions, **but does not erase physical partition, quota, or hot-key limits**.

AWS documents per-physical-partition design limits around **1,000 WCUs/s** and **3,000 RCUs/s**. Never treat these as rigid caps on every logical PK: adaptive capacity, item isolation/splitting, capacity mode, and traffic shape all influence real throughput.

### 9.2. Observing Hotspots

Signals:

- Rising `ThrottledRequests` / `WriteKeyRangeThroughputThrottleEvents`;
- Specific tenant/course IDs showing much higher latency;
- GSI2 key `CATEGORY#java` getting far more reads/writes than other keys;
- Provisioned table still has spare capacity while one key range throttles;
- Specific items/counters hitting high transaction conflict rates.

Monitor CloudWatch metrics, `ConsumedReadCapacityUnits`/`ConsumedWriteCapacityUnits`, and Contributor Insights where policy allows; **never embed PII in partition keys or diagnostic dashboards**.

### 9.3. Sharding Enrollments by Course When Needed

One approach after measuring real load:

~~~text
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#00
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#01
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#02
...
SK=ENROLLMENT#u1

shard = hash(userId) mod shardCount
~~~

Checking one enrollment with `courseId` and `userId` computes the shard and calls `GetItem`. However, listing all enrollments of a course requires **querying all shards, merging, and paginating**. This is a deliberate trade-off; never shard every entity simply because "DynamoDB uses partitions."

When changing `shardCount`, retain shard version/routing metadata so older items remain reachable. Adding a GSI, replica, or cache can be simpler.

### 9.4. 10 GB LSI Limit and Hot Item Collections

Whenever a table has at least one **LSI**, each PK's item collection is capped at **10 GB**, counting base items plus projected LSI entries. Tables **without LSIs** do not face that 10 GB item-collection limit, though item-size, throughput, and quota limits still apply.

Avoid LSIs on **unbounded** item collections (e.g., courses with tens of millions of enrollments) unless growth bounds are proven. Use GSIs, sharding, or archival instead.

### 9.5. Hot GSIs Also Slow Down Writes

An index `GSI3PK=TENANT#t1#STATUS#PENDING` receiving every event of a large tenant can become a hotspot. GSI write throttling propagates back-pressure to base-table writes. Check cardinality, skew, projections, write amplification, traffic bursts, and caching/alternate keys before adding a GSI.

## 10. Multi-Tenant Isolation, IAM, and PII

### 10.1. Tenant-Namespaced Partition Keys

In our example:

~~~text
Base PK  = TENANT#t1#COURSE#c1
GSI1PK   = TENANT#t1#USER#u1
GSI2PK   = TENANT#t1#CATEGORY#java
~~~

This helps the API scope inputs by `tenantId` and isolate tenant queries. Yet **a prefix alone never stops cross-tenant access** if the backend blindly trusts a caller-supplied tenant value.

A sound flow:

~~~text
HTTP request /tenants/t1/courses/c1/students
  -> Verify identity/access token
  -> Resolve tenant membership from trusted source
  -> Check caller has admin permission on course c1
  -> Construct PK for tenant t1 from server-side context
  -> Query DynamoDB with validated key
  -> Return only permitted fields via DTO
~~~

**Never concatenate an unverified query parameter straight into a tenant key.**

### 10.2. DynamoDB IAM Condition `dynamodb:LeadingKeys`

DynamoDB provides the `dynamodb:LeadingKeys` condition key to restrict which **partition key values** a principal can access. Use `ForAllValues` per AWS guidance.

**Conceptual** example when an IAM principal tag `TenantId` is issued by a trusted identity provider:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TenantScopedGetAndQuery",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:Query"],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore/index/*"
      ],
      "Condition": {
        "ForAllValues:StringLike": {
          "dynamodb:LeadingKeys": "TENANT#${aws:PrincipalTag/TenantId}#*"
        }
      }
    }
  ]
}
~~~

**Test policies with real principals** and negative tests: tenant t1 must not Query tenant t2 on either base **or GSI**, even if the client knows IDs. This condition still does not replace user/resource-level authorization.

Note: `LeadingKeys` checks the leading partition key; **every GSI partition key** queried by that role must also follow the tenant prefix. If a GSI uses a shared key like `STATUS#PENDING` without a tenant prefix, that policy will block it—never loosen IAM to wildcards; redesign the index/security model instead.

### 10.3. IAM Identity vs. Application Authorization

AWS IAM governs whether a role may invoke `dynamodb:Query`/`PutItem` on a table/index. The backend still enforces which course enrollments a user may view, their school membership, and instructor privileges.

Also secure **table exports, PITR backups, Streams subscribers, and CloudWatch metrics/logs**. A Streams consumer subscribed to all entity types sees records across entities that regular APIs filter out.

### 10.4. Keys and Attributes May Contain PII

Never put passwords, tokens, raw emails/phone numbers, or payment details into `PK`/`SK`. Keys routinely appear in query logs, traces, CLI outputs, backups, and monitoring tools.

Use opaque IDs and classify PII; project only necessary attributes into GSIs. If email lookup is needed, consider a **normalized email hash/HMAC** index key with proper key management and lookup contracts—plain unsalted hashing alone does not resist dictionary attacks on low-entropy data.

### 10.5. Encryption, KMS, and Table Boundaries

DynamoDB supports encryption at rest; evaluate AWS-owned, AWS-managed, and customer-managed KMS keys against compliance requirements. Single-table stores multiple entities inside one table resource sharing operational settings. If a tenant mandates its own KMS key or independent retention, **table-per-tenant or account-per-tenant** may fit better.

## 11. Cost Model of Single-Table Design

### 11.1. Capacity by Item Size

Core DynamoDB capacity rules:

- Write capacity bills in **1 KiB increments** (rounded up), plus transaction/GSI overhead.
- Strongly consistent reads bill in **4 KiB increments** (rounded up).
- Eventually consistent reads typically consume **half the read units** of strong reads for the same data.
- Transactional reads/writes consume higher capacity than standard calls.
- GSI reads bill against **index entry size**, alongside index write amplification and storage.
- On-demand vs. provisioned, adaptive capacity, burst, and table class all impact cost efficiency.

Do not count only returned attributes: `ProjectionExpression` and `FilterExpression` **do not** shrink the item size DynamoDB reads for base-table Query capacity.

### 11.2. GSI Projections Are a Cost Trade-Off

Suppose course META is 40 KiB, while the catalog only needs `title`/`category`/`publishedAt`. A GSI2 with `ProjectionType=ALL` stores and updates far more data than `INCLUDE` with just those three fields. Pick projections from the **API response contract**.

| Option | Pros | Cons |
|---|---|---|
| `KEYS_ONLY` | Smallest index entries | May require follow-up base-table gets |
| `INCLUDE` | Balances query performance and storage | Must anticipate needed fields |
| `ALL` | Queries return all stored fields | Heavy GSI storage/writes; risks indexing excessive PII |

**Reading from a GSI never auto-fetches unprojected attributes from the base table** the way an LSI can. If an API needs an unprojected field, fetch base items separately or adjust the projection.

### 11.3. One Edge + GSI vs. Two Base Edges?

| Pattern | Read course→users | Read user→courses | Writes | Consistency |
|---|---|---|---|---|
| One edge + GSI1 | Base Query | GSI1 Query | Base Put + GSI sync | GSI eventual |
| Two base edge items | Base Query | Base Query | Two Puts, typically transactional | Both directions can be strong |
| Embed `courseIds` list in USER PROFILE | Hard to list users per course | Single GetItem | Rewrites growing list | 400 KiB limit and contention |
| RDBMS join table | SQL JOIN/index | SQL JOIN/index | Relational INSERT | SQL transactions/FKs |

If dashboards tolerate brief index propagation lag, **one edge + GSI1** is usually optimal; if bidirectional reads require immediate strong consistency and access patterns permit, dual-edge works at higher write cost. Choose by requirements—no single pattern is universally right.

### 11.4. Cost Does Not Drop Automatically Just Because You Use One Table

One table carrying 7 GSIs, `ALL` projections, transactions everywhere, and shared streams can cost more than two or three clean tables. Sum up:

- Base table read/write request units;
- GSI storage + read/write throughput;
- Backfill cost when adding indexes;
- Transactions, conditional failures, and retries;
- Global Tables replication per Region/mode;
- Exports, PITR/backups, Streams, and Lambda consumers;
- CloudWatch/Contributor Insights, KMS, and network transfer;
- On-demand vs. provisioned capacity configuration.

Use the AWS Pricing Calculator and cost-allocation tags by workload/tenant. Never hardcode fixed USD amounts in lessons since pricing varies by Region and date.

## 12. Streams, TTL, Backups, and Schema Migration

### 12.1. Streams on Multi-Entity Tables

A single `LearningCore` table emits DynamoDB Streams records for all entity types:

~~~mermaid
flowchart TD
    TABLE[(LearningCore Stream)] --> ROUTER[Lambda / consumer]
    ROUTER -->|entityType USER| P[Profile sync]
    ROUTER -->|entityType COURSE| S[Search index]
    ROUTER -->|entityType ENROLLMENT| A[Analytics]
    ROUTER -->|entityType LESSON| C[Cache invalidation]
~~~

Stream consumers must:

- Inspect `entityType`/key prefixes and validate schema versions;
- Handle **at-least-once** delivery, duplicates, and poison-pill records;
- Never assume a consumer only receives one entity type;
- Enforce IAM/PII controls and dead-letter failure handling;
- Distinguish stream retention from backups and long-term audit archives.

With multi-table, each table can have its own Streams if teams need operational isolation.

### 12.2. TTL Does Not Replace Business-Time Constraints

Given `expiresAt` (Unix epoch seconds):

~~~json
{
  "PK": "TENANT#t1#INVITE#inv1",
  "SK": "META",
  "entityType": "INVITATION",
  "expiresAt": 1795143600
}
~~~

DynamoDB TTL may delete the item **after** expiration passes, not at that exact second. Backends must check `expiresAt` against current time when validating invitations/tokens. TTL reclaims storage; it is not real-time access control.

### 12.3. PITR and Restore

Backups/PITR in single-table design operate at **table scope**. If one course's enrollments are accidentally deleted, you can:

1. Restore the backup into a **new table** in a controlled environment;
2. Identify the exact item keys to recover;
3. Reconcile against live production data;
4. Reapply missing items idempotently/conditionally;
5. Log audit trails and clean up the temporary table per policy.

**Never overwrite the live production table** with a full restore without weighing lost mutations across all other entities. And never treat Streams or GSIs as independent backup solutions.

### 12.4. Migrating from RDBMS / Multi-Table

~~~mermaid
flowchart TD
    OLD[Legacy tables] --> AP[Finalize access patterns]
    AP --> NEW[Create new DynamoDB table + GSIs]
    NEW --> BACKFILL[Backfill with validation]
    BACKFILL --> DUAL[CDC / dual-write idempotent]
    DUAL --> VERIFY[Reconcile counts and invariants]
    VERIFY --> CANARY[Canary switch reads]
    CANARY --> CUT[Switch writes and monitor]
    CUT --> CLEAN[Retire legacy path after rollback window]
~~~

Risks:

- Duplicate edges or missing users/courses;
- Wrong tenant namespaces and key collisions;
- Broken sort-key ordering if not zero-padded;
- Incomplete GSI propagation/backfill;
- Index write pressure during bulk backfills;
- Unexpected Query pagination or `FilterExpression` costs;
- Old/new services writing mismatched schema contracts;
- Streams consumers processing both backfill and live business events.

### 12.5. Schema Evolution

DynamoDB cannot update an item's **`PK`/`SK`** in-place like regular non-key attributes. Moving keys from:

~~~text
PK=TENANT#t1#COURSE#c1
SK=ENROLLMENT#u1
~~~

to:

~~~text
PK=TENANT#t1#COURSE#c1#ENROLL#SHARD#03
SK=ENROLLMENT#u1
~~~

requires creating a **new item** and deleting the old one—using transactions if atomicity within the same Region/table and size limits is required. Large migrations need dual-read/dual-write or versioned routing across a cutover window.

Add a `schemaVersion` attribute to version item payloads. Keep the `PK`/`SK` contract as stable as possible because every access pattern and IAM tenant policy depends on it.

### 12.6. When Should You Choose Multi-Table or Hybrid?

Choose **multi-table/hybrid** when:

- Entities are independent and rarely queried together;
- IAM, KMS, backup/PITR, TTL, or Streams needs diverge sharply;
- Different teams own separate operational lifecycles;
- Some workloads genuinely need relational JOINs and complex reporting;
- Tenant isolation requires table- or account-level boundaries;
- STD leads to heavy GSI overloading and hard-to-maintain code;
- Locality gains do not outweigh migration and training costs.

**Single-table design is an optimization tool for access patterns**, not a contest to have the fewest tables.

## 13. Lab 1 — Inspecting Schema and Indexes via AWS CLI (Read-Only)

> **Mandatory lab scope: read-only configuration inspection** in an authorized sandbox account/Region. Requires AWS CLI v2, valid IAM credentials, and permissions such as `dynamodb:ListTables`, `dynamodb:DescribeTable`, `dynamodb:DescribeTimeToLive`, `dynamodb:DescribeContinuousBackups`, and CloudWatch read access as needed. Never create tables, scan user records, or read production data.

### 13.1. Verify Account, Profile, and Region

Bash / AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If CloudShell already has session-managed credentials without an `aws-lab-dev` profile, omit the profile variable/flag. Verify account and ARN before running commands.

### 13.2. List Table Names

~~~bash
aws dynamodb list-tables \
  --region "$REGION" \
  --query 'TableNames' \
  --output table
~~~

Empty output may mean wrong account/Region or no tables yet; never create a production table just to study. `ListTables` paginates via AWS CLI paginators depending on version. All resource names here are placeholders.

### 13.3. Inspect Base Primary Key and GSIs

~~~bash
TABLE=LearningCoreSandbox

aws dynamodb describe-table \
  --table-name "$TABLE" \
  --region "$REGION" \
  --query 'Table.{Name:TableName,Status:TableStatus,BillingMode:BillingModeSummary.BillingMode,KeySchema:KeySchema,AttributeDefinitions:AttributeDefinitions,GSIs:GlobalSecondaryIndexes[].{Name:IndexName,Status:IndexStatus,Keys:KeySchema,Projection:Projection},LSIs:LocalSecondaryIndexes[].{Name:IndexName,Keys:KeySchema,Projection:Projection},StreamSpecification:StreamSpecification}' \
  --output json
~~~

Check:

| Property | Question |
|---|---|
| `KeySchema` | Are base PK (`HASH`) and SK (`RANGE`) String as expected? |
| `AttributeDefinitions` | Which types are declared for key/index attributes? |
| `GlobalSecondaryIndexes` | Do `GSI1`/`GSI2` exist with `IndexStatus=ACTIVE`? |
| `Projection` | `KEYS_ONLY`/`INCLUDE`/`ALL`—does it cover API-required fields? |
| `LocalSecondaryIndexes` | Does any LSI impose the 10 GB item-collection limit? |
| `BillingMode` | On-demand or provisioned? |
| `StreamSpecification` | Is Streams enabled with the right view type? |

**Note:** `AttributeDefinitions` in `DescribeTable` is not "all schema columns" of the table. DynamoDB only declares **key attributes** of the table and indexes; non-key attributes vary freely per item without pre-declaration.

### 13.4. Check TTL

~~~bash
aws dynamodb describe-time-to-live \
  --table-name "$TABLE" \
  --region "$REGION" \
  --output json
~~~

If `TimeToLiveStatus=ENABLED`, verify the attribute name and epoch **seconds** format in app code. Never assume TTL-enabled guarantees expired items disappear at the exact expiration second.

### 13.5. Check PITR

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name "$TABLE" \
  --region "$REGION" \
  --query 'ContinuousBackupsDescription.{BackupsStatus:ContinuousBackupsStatus,PITR:PointInTimeRecoveryDescription}' \
  --output json
~~~

This inspects config only without restoring or altering the table. Remember that in single-table design, PITR protects the **entire table**, not individual entity types.

### 13.6. Check CloudWatch Metrics for the Table

Example reading consumed read capacity over the past 30 minutes using GNU `date` in AWS CloudShell:

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions "Name=TableName,Value=$TABLE" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output json
~~~

Interpret metric units and statistics per CloudWatch definitions; `Sum` over a period bucket is not QPS. On Windows PowerShell, replace `date -d` with `Get-Date` formatted as UTC ISO timestamps.

### 13.7. Observation Worksheet

| Check | Lab result | Assessment |
|---|---|---|
| Base PK/SK | ... | Supports GetItem/Query patterns? |
| GSI1 keys/projection | ... | Supports user→enrollments? |
| GSI2 keys/projection | ... | Supports published catalog? |
| LSI count | ... | Any 10 GB item-collection limit? |
| Billing mode | ... | Fits traffic and budget? |
| TTL | ... | App avoids relying on exact-second expiry? |
| PITR | ... | Can recover from data loss? |
| Streams | ... | Do consumers handle multiple entity types? |
| Capacity metrics | ... | Need load tests / hot-key investigation? |

## 14. Lab 2 — Querying Access Patterns (Sandbox Read-Only)

> This section **reads item data**. Run only against your own `LearningCoreSandbox` populated with **dummy data**—never run `GetItem`/`Query` on real personal records. The typed JSON below uses **AWS DynamoDB `AttributeValue`** format, unlike the logical JSON in Section 4.

### 14.1. GetItem — Single Course

~~~bash
aws dynamodb get-item \
  --table-name "$TABLE" \
  --key '{"PK":{"S":"TENANT#t1#COURSE#c1"},"SK":{"S":"META"}}' \
  --projection-expression 'PK,SK,#title,#visibility' \
  --expression-attribute-names '{"#title":"title","#visibility":"visibility"}' \
  --consistent-read \
  --region "$REGION" \
  --output json
~~~

If the table lacks the test item, the response omits `Item`. That is **not an API error**—merely not found. `--consistent-read` is valid on the base table, never on a GSI.

### 14.2. Query — Ordered Lessons in a Course

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --key-condition-expression 'PK = :pk AND begins_with(SK, :prefix)' \
  --expression-attribute-values '{":pk":{"S":"TENANT#t1#COURSE#c1"},":prefix":{"S":"LESSON#"}}' \
  --projection-expression 'PK,SK,#title' \
  --expression-attribute-names '{"#title":"title"}' \
  --no-paginate \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --region "$REGION" \
  --output json
~~~

Inspect `Count`, `ScannedCount`, `LastEvaluatedKey`, and `ConsumedCapacity`. `--limit 20` caps **evaluated items** at the API level rather than guaranteeing 20 returned items. If `LastEvaluatedKey` is present, pass it to `--exclusive-start-key` on the next request.

### 14.3. Query GSI1 — Enrollments by User

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --index-name GSI1 \
  --key-condition-expression 'GSI1PK = :user AND begins_with(GSI1SK, :kind)' \
  --expression-attribute-values '{":user":{"S":"TENANT#t1#USER#u1"},":kind":{"S":"ENROLLMENT#"}}' \
  --no-paginate \
  --limit 20 \
  --return-consumed-capacity INDEXES \
  --region "$REGION" \
  --output json
~~~

**Never pass `--consistent-read` to a GSI Query.** If a newly created enrollment does not show up yet, account for GSI eventual propagation rather than writing duplicate edges. `GSI1` must exist, be `ACTIVE`, and project required fields.

### 14.4. Query GSI2 — Catalog by Category

~~~bash
aws dynamodb query \
  --table-name "$TABLE" \
  --index-name GSI2 \
  --key-condition-expression 'GSI2PK = :category AND begins_with(GSI2SK, :published)' \
  --expression-attribute-values '{":category":{"S":"TENANT#t1#CATEGORY#java"},":published":{"S":"PUBLISHED#"}}' \
  --scan-index-forward false \
  --no-paginate \
  --limit 20 \
  --region "$REGION" \
  --output json
~~~

Because the sort key starts with `PUBLISHED#<timestamp>` in uniform ISO-8601 UTC format, `--scan-index-forward false` returns newest courses first within that category. Across multiple categories or statuses, design explicit key contracts rather than relying on `FilterExpression`.

### 14.5. Do Not Scan Because an Index Is Missing

Never run queries like:

~~~bash
# ANTI-PATTERN for hot API paths; never run in production
aws dynamodb scan \
  --table-name "$TABLE" \
  --filter-expression 'email = :email' \
  --expression-attribute-values '{":email":{"S":"someone@example.test"}}'
~~~

Scan reads items before filtering, causing high cost and latency—and risks scanning out-of-scope user data if IAM is overly broad. For frequent email lookups, add a dedicated index or identity service with proper data protection.

## 15. Lab 3 — Conditional and Transactional Writes (Optional, Mutating)

> **Optional and mutating.** Test only on your own `LearningCoreSandbox` table with dummy tenant IDs, approval, budget, and a cleanup plan. Never run against real student data. The current worker **does not execute any AWS commands**; the commands below are purely instructional examples.

### 15.1. Create an Enrollment with Conditional PutItem

~~~bash
# RUN ONLY against a sandbox table you own.
aws dynamodb put-item \
  --table-name LearningCoreSandbox \
  --item '{"PK":{"S":"TENANT#t1#COURSE#c1"},"SK":{"S":"ENROLLMENT#u1"},"entityType":{"S":"ENROLLMENT"},"userId":{"S":"u1"},"courseId":{"S":"c1"},"status":{"S":"ACTIVE"},"GSI1PK":{"S":"TENANT#t1#USER#u1"},"GSI1SK":{"S":"ENROLLMENT#c1"}}' \
  --condition-expression 'attribute_not_exists(PK) AND attribute_not_exists(SK)' \
  --return-consumed-capacity TOTAL \
  --region ap-southeast-1
~~~

`PutItem` creates the item if absent, or fails with `ConditionalCheckFailedException` if that key already exists. **Never** interpret every `ConditionalCheckFailedException` as a server error to retry.

This snippet **does not verify that `USER PROFILE` or `COURSE META` exist**, so use it strictly to illustrate conditional `Put`. Production systems need full invariant validation/transactions.

### 15.2. `TransactWriteItems` Example

JSON payload to review before running, spanning three **distinct items**: verify user, verify course is published, then insert the edge.

~~~json
{
  "TransactItems": [
    {
      "ConditionCheck": {
        "TableName": "LearningCoreSandbox",
        "Key": {
          "PK": {"S": "TENANT#t1#USER#u1"},
          "SK": {"S": "PROFILE"}
        },
        "ConditionExpression": "attribute_exists(PK)"
      }
    },
    {
      "ConditionCheck": {
        "TableName": "LearningCoreSandbox",
        "Key": {
          "PK": {"S": "TENANT#t1#COURSE#c1"},
          "SK": {"S": "META"}
        },
        "ConditionExpression": "#visibility = :published",
        "ExpressionAttributeNames": {"#visibility": "visibility"},
        "ExpressionAttributeValues": {":published": {"S": "PUBLISHED"}}
      }
    },
    {
      "Put": {
        "TableName": "LearningCoreSandbox",
        "Item": {
          "PK": {"S": "TENANT#t1#COURSE#c1"},
          "SK": {"S": "ENROLLMENT#u1"},
          "entityType": {"S": "ENROLLMENT"},
          "userId": {"S": "u1"},
          "courseId": {"S": "c1"},
          "status": {"S": "ACTIVE"},
          "GSI1PK": {"S": "TENANT#t1#USER#u1"},
          "GSI1SK": {"S": "ENROLLMENT#c1"}
        },
        "ConditionExpression": "attribute_not_exists(PK)"
      }
    }
  ]
}
~~~

In AWS CLI, `--transact-items` expects the **array of actions**, not the outer `{"TransactItems": ...}` wrapper object. Save just the inner **array** into `enroll-actions.json` for AWS CLI:

~~~bash
# MUTATING; illustrative only, not executed by worker.
aws dynamodb transact-write-items \
  --transact-items file://enroll-actions.json \
  --client-request-token training-operation-id \
  --region ap-southeast-1
~~~

In production, use a stable operation ID, scoped IAM, transaction-conflict handling, telemetry, and **never** use placeholder credentials or IDs.

### 15.3. Test Fail-Safe Duplicate Handling

Run `Put` with the same `(PK, SK)` pair twice in the sandbox:

- First call: item is created.
- Second call: `ConditionalCheckFailedException` because the item exists.
- Re-read the base item to distinguish a valid duplicate from a conflicting enrollment status.
- Avoid deleting dummy items immediately if needed for subsequent tests; clean up per procedure.

**Important case:** if two parallel requests hit for the same user/course, DynamoDB's condition check prevents duplicate/overwritten edges—though it still does not prevent external email/payment calls if triggered before the transaction commits.

### 15.4. Cleaning Up Sandbox Resources

`delete-table` is omitted from mandatory lab steps because it **deletes the entire table and data**. For dedicated test stacks/tables, verify ownership, tags, item counts/retention, and snapshot policies before deleting. Never delete a production table or backup just to "finish a lesson."

## 16. Java AWS SDK for Java v2 Examples

### 16.1. Why Use Low-Level `DynamoDbClient` Here?

In single-table design, a single `Query` can return **multiple distinct entity types**. AWS SDK v2 **`DynamoDbEnhancedClient`** provides handy typed mappings when a schema aligns cleanly with one entity, while polymorphic items require careful converter/repository design. This lesson uses **low-level `DynamoDbClient`** to keep PK/SK, indexes, and pagination crystal clear.

Prerequisites:

- Java 17+ or a project-supported Java version;
- AWS SDK v2 DynamoDB dependency;
- IAM role/session credentials—never hardcoded access keys;
- Correct Region matching the table;
- Sandbox table with dummy test data.

### 16.2. Querying Lessons of a Course

~~~java
import java.util.Map;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public final class CourseLessonReader {

    private final DynamoDbClient dynamoDb;

    public CourseLessonReader(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    public QueryResponse loadFirstPage(
            String verifiedTenantId,
            String courseId) {

        // tenantId MUST come from trusted auth/authz context,
        // never directly from a request query parameter.
        String pk = "TENANT#" + verifiedTenantId + "#COURSE#" + courseId;

        QueryRequest request = QueryRequest.builder()
            .tableName("LearningCoreSandbox")
            .keyConditionExpression(
                "PK = :pk AND begins_with(SK, :prefix)")
            .expressionAttributeValues(Map.of(
                ":pk", AttributeValue.builder().s(pk).build(),
                ":prefix",
                AttributeValue.builder().s("LESSON#").build()
            ))
            .limit(20)
            .consistentRead(true)  // Base table or LSI only.
            .build();

        return dynamoDb.query(request);
    }

    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            CourseLessonReader reader = new CourseLessonReader(client);
            QueryResponse page = reader.loadFirstPage("t1", "c1");
            System.out.println("items=" + page.count());
            System.out.println(
                "morePages=" + !page.lastEvaluatedKey().isEmpty());
        }
    }
}
~~~

**Security:** `verifiedTenantId` must come from a trusted auth context. Validate `courseId` and check membership/business permissions before querying private courses.

### 16.3. Proper Pagination

Snippet reading a bounded number of pages so a huge item collection is never scanned unboundedly:

~~~java
QueryRequest request = QueryRequest.builder()
    .tableName("LearningCoreSandbox")
    .keyConditionExpression(
        "PK = :pk AND begins_with(SK, :prefix)")
    .expressionAttributeValues(Map.of(
        ":pk", AttributeValue.builder()
            .s("TENANT#t1#COURSE#c1").build(),
        ":prefix", AttributeValue.builder()
            .s("ENROLLMENT#").build()
    ))
    .limit(25)
    .build();

Map<String, AttributeValue> cursor = Map.of();
int maxPages = 3;

for (int pageIndex = 0; pageIndex < maxPages; pageIndex++) {
    QueryRequest pageRequest = request.toBuilder()
        .exclusiveStartKey(cursor)
        .build();

    QueryResponse response = dynamoDb.query(pageRequest);
    // Process response.items() within authorization and memory bounds.
    System.out.println("pageCount=" + response.count());

    cursor = response.lastEvaluatedKey();
    if (cursor == null || cursor.isEmpty()) {
        break;
    }
}
~~~

This is an **excerpt inside a method** with `DynamoDbClient dynamoDb` and imports in scope, not a standalone Java file. In production APIs, **return `nextToken`** to clients instead of looping three pages on every request. Protect tokens (e.g., signed/encrypted opaque tokens) binding query shape, index, and tenant scope so users cannot alter keys.

### 16.4. Querying a User's GSI1

~~~java
QueryRequest request = QueryRequest.builder()
    .tableName("LearningCoreSandbox")
    .indexName("GSI1")
    .keyConditionExpression(
        "GSI1PK = :pk AND begins_with(GSI1SK, :prefix)")
    .expressionAttributeValues(Map.of(
        ":pk", AttributeValue.builder()
            .s("TENANT#t1#USER#u1").build(),
        ":prefix", AttributeValue.builder()
            .s("ENROLLMENT#").build()
    ))
    .limit(20)
    .build();

QueryResponse response = dynamoDb.query(request);
~~~

**Never enable `consistentRead(true)` on GSI1.** If a just-written enrollment is absent, display the write result optimistically or call a base `GetItem` by `courseId`/`userId`. Never loop GSI Queries indefinitely to "force" strong consistency.

### 16.5. Repository/DTO Layers Should Encapsulate Key Layout

Never let every controller concatenate keys inline:

~~~text
"PK = TENANT#" + userSuppliedTenant + "#COURSE#" + userSuppliedCourse
~~~

Design clean repositories:

~~~text
EnrollmentRepository
  - getEnrollment(VerifiedTenantId, CourseId, UserId)
  - listEnrollmentsByCourse(...)
  - listEnrollmentsByUser(...)
  - createEnrollmentConditionally(...)

CourseRepository
  - getMetadata(...)
  - listLessons(...)
  - listPublishedByCategory(...)
~~~

This centralizes `PK`/`SK`/`GSI` knowledge and key schema versions in one place, simplifying validation, authorization, metrics, and migrations. Never expose raw DynamoDB `AttributeValue` objects from REST APIs.

### 16.6. Java Retries and Never Swallowing Errors

- For `ProvisionedThroughputExceededException` or throttling errors, use AWS SDK v2 backoff/jitter within your SLO; never retry infinitely.
- `ConditionalCheckFailedException` usually means a business conflict or duplicate—not a transient error to retry endlessly.
- For `TransactionCanceledException`, inspect `CancellationReasons` to separate permanent failures from retryable conflicts.
- For timeouts after writes, use idempotency and state reconciliation to avoid duplicate side effects.
- Never log `PK`/`SK` if they hold PII, and never log full item JSON in production.
- On batched writes, check `UnprocessedItems` and retry properly—never treat `BatchWriteItem` as an atomic transaction.

## 17. Design Scenario: Multi-School Course Platform

### 17.1. Requirements

A Java/Spring Boot application serves:

- 50,000 students and 5,000 courses across multiple schools;
- Students enroll in multiple courses, and each course has many students;
- API must fetch course metadata and lessons under 100 ms p95 at target load;
- Student dashboard lists enrolled courses;
- Category catalog lists only published courses;
- A viral course can hit 20,000 enrollments/minute;
- Students must never read enrollments from another tenant;
- Retries must never create duplicate enrollments;
- Historical analytics plus PITR/backup requirements;
- Budget must include GSIs, transactions, and Streams.

These are **illustrative planning figures**, not AWS SLAs or real benchmark numbers.

### 17.2. Core Architecture

~~~mermaid
flowchart TD
    APP[Spring Boot API] --> REPO[DynamoDB repositories]
    REPO --> BASE[(LearningCore Base Table)]
    REPO --> G1[GSI1 - enrollments by user]
    REPO --> G2[GSI2 - published by category]
    BASE --> IC[Course item collection]
    IC --> META[SK META]
    IC --> LESSON[SK LESSON#order#id]
    IC --> EDGE[SK ENROLLMENT#user]
    EDGE -. "GSI1 user-centric keys" .-> G1
    META -. "GSI2 sparse catalog keys" .-> G2
    BASE --> STREAM[DynamoDB Streams]
    STREAM --> S3[Analytics pipeline / S3]
~~~

### 17.3. Access-Pattern Acceptance Tests

| Test | Verification | Passing outcome |
|---|---|---|
| AP1 | `GetItem` PROFILE | Returns the tenant's user |
| AP2 | `GetItem` COURSE META | Returns the course |
| AP3 | `Query` LESSON prefix | Ordered `0001, 0002, ...` |
| AP4 | `Query` ENROLLMENT prefix | Paginated without Scan |
| AP5 | GSI1 `Query` by user | Accurate enrollments, tolerating propagation lag |
| AP6 | `GetItem` enrollment edge | Fast duplicate check |
| AP7 | GSI2 `Query` category | Only published courses, sorted by timestamp |
| Duplicate registration | Two parallel conditional Puts | Only one creates the edge |
| Cross-tenant | User t1 requests t2 | 403/AccessDenied with zero data leak |
| Viral course | Load 20,000 enrollments/min | Meets SLO without bottleneck; shard if needed |
| GSI lag | Write then immediate Query | UX/logic never treats stale GSI as failed write |
| PITR restore | Restore to test table | Recovers items without overwriting production |

### 17.4. How Should a Viral Course Be Sharded?

At 20,000 registrations/minute (~333 writes/second on edge items under one course), DynamoDB adaptive capacity can handle it depending on item size and capacity—so **do not assume upfront it will definitely throttle**. However, adding transactional counters on a single `STATS` item invites contention and limits. Load-test realistically:

1. Measure p99 latency and throttling.
2. Monitor base and GSI write capacity plus hot keys.
3. If counters bottleneck, switch to sharded counters or asynchronous aggregation.
4. If the edge PK itself still runs hot, add deterministic shards.
5. Update AP4 to fan-out Query/merge/paginate across shards and re-measure cost.
6. Never change `shardCount` arbitrarily in ways that break `GetItem` on older enrollments.

### 17.5. Recovery Plan

- Enable PITR per policy and rehearse restores.
- Make Streams consumers idempotent with clear failure sinks and alarms.
- Maintain reconciliation checks between enrollment edges and course/user states.
- Never delete expired items with TTL and treat TTL alone as business authorization.
- Runbook for GSI lag/throttling: check index status/capacity and prevent duplicate writes.
- For aggregate analytics, use S3/Glue/Athena or an analytics store—never Scan the table on user requests.

## 18. Troubleshooting

| Symptom | Possible cause | Check |
|---|---|---|
| `ValidationException: Query condition missed key schema element` | Query lacks PK equality | Check `KeyConditionExpression` and index keys |
| `begins_with(SK)` fails to run | Only SK condition provided, no PK | Add PK equality |
| Query returns empty after Put | Eventual GSI or wrong key prefix | Read base `GetItem`; check GSI propagation |
| Lessons sort `1, 10, 2` | Unpadded String SK | Zero-pad `0001, 0002, 0010` |
| `ResourceNotFoundException` on GSI | Index missing, not `ACTIVE`, or wrong Region/table | `DescribeTable` and `IndexStatus` |
| `ConditionalCheckFailedException` on enrollment | Edge already exists or condition mismatch | Strong `GetItem` to distinguish duplicate |
| Duplicate edge items | Missing conditional `Put` or non-atomic dual-edge | Unique PK/SK + transactions |
| Bidirectional relationship out of sync | Dual-edge update lacked atomicity | Transaction/reconciliation; consider GSI |
| Dashboard misses freshly created enrollment | GSI eventual consistency | Read base table or use optimistic UX |
| Empty `Items` yet pagination continues | `FilterExpression` dropped all items on page | Follow `LastEvaluatedKey` |
| High `Read capacity` despite small response | Post-read filtering; Projection does not cut read size | Redesign index/key; compare `Count` vs. `ScannedCount` |
| API forced to Scan to find email | Missing lookup access pattern/index | Add lookup index or identity service |
| `ItemCollectionSizeLimitExceededException` | LSI present and item collection >10 GB | Shard/archive; avoid LSIs on unbounded sets |
| `ValidationException: Item size too large` | Exceeded 400 KiB/item | Split items or store blobs in S3 |
| GSI updates throttled | Hot GSI PK or insufficient capacity | GSI metrics, sharding/capacity |
| One viral course spikes latency | Hot PK or hot counter item | Distribute traffic, use sharded counters |
| Cross-tenant data leak | Backend trusted client-supplied `tenantId` | Verified tenant context + IAM `LeadingKeys` |
| TTL-expired item still present | TTL deletes asynchronously | Check `expiresAt` in business logic |
| GSI lacks projected attribute | `ProjectionType`/`INCLUDE` omitted field | Fetch from base table or expand projection |
| Transaction canceled | Condition failed, conflict, capacity, or size limit | Inspect cancellation reasons; 100 actions / 4 MB cap |
| Lost updates from concurrent writers | Missing condition/version check | Optimistic locking |
| Orphaned records after deleting user/course | No foreign-key cascade | Delete workflows, Streams, reconciliation |
| Costs surge despite using one table | Many GSIs, `ALL` projections, heavy transactions | Break down capacity and storage costs |
| PITR restore impacts unrelated entities | Table-wide backup boundary | Restore to temp table and selectively reconcile |
| Streams consumer sees unfamiliar record types | Shared single-table stream | Filter/route by `entityType` |
| Global Table differs across Regions | Mode, lag, or conflict handling | Review MREC/MRSC config and data contract |

### 18.1. Ordered Runbook

~~~text
1. Identify account, Region, table, GSI, tenant, and API action.
2. Inspect access pattern: key-based GetItem/Query or falling back to Scan?
3. Inspect Table KeySchema/GSI keys, IndexStatus, and projections.
4. Check PK/SK prefixes, types, zero-padding, and tenant namespaces.
5. Compare Count, ScannedCount, ConsumedCapacity, and LastEvaluatedKey.
6. Separate stale GSI, conditional conflict, throttling, or permissions error.
7. Inspect hot PK/GSI keys, CloudWatch/Contributor Insights, and capacity.
8. Check idempotency, transactions, TTL, and business invariants.
9. Test fixes in a sandbox, load-test, and measure p95/p99 and write amplification.
10. Roll out with migration/rollback plans; monitor errors/costs and log audits.
~~~

## 19. Self-Check Questions and Exercises

### 19.1. Theory Questions

1. How does single-table design differ from "one table per entity" in query foundations?
2. Why must access patterns be known before choosing PK/SK?
3. How does a DynamoDB composite key `(PK, SK)` differ from a simple PK?
4. What is an item collection? Must it remain on one fixed physical partition?
5. How do `GetItem` and `Query` differ when reading enrollments?
6. Can you Query by sort key without partition-key equality?
7. Why doesn't `FilterExpression` reduce read capacity consumed by read items?
8. Does `ProjectionExpression` shrink the item size DynamoDB uses to calculate read capacity?
9. Why can a response return 0 filtered items while `LastEvaluatedKey` is still present?
10. Why do `LESSON#1, LESSON#2, LESSON#10` sort out of order as String SKs?
11. In our example, which index does AP4 (course → students) use?
12. Which index does AP5 (user → courses) use, and what is its consistency?
13. Why is one enrollment edge + GSI1 often simpler than two base-table edge items?
14. When might dual-edge be better than edge + GSI?
15. How do GSIs and LSIs differ on partition keys and consistency?
16. Under what exact condition does the 10 GB item-collection limit apply?
17. Why is a sparse GSI2 good for a published catalog?
18. What must happen to `GSI2PK`/`GSI2SK` when a course switches `PUBLISHED → DRAFT`?
19. How do `KEYS_ONLY`, `INCLUDE`, and `ALL` differ in cost and projection?
20. Why can viral traffic on one course create a hot PK?
21. Sharding enrollments by `userId` helps writes, but how does it affect AP4?
22. What are the max actions and total payload size for `TransactWriteItems`?
23. Which condition stops `PutItem` from overwriting an existing enrollment?
24. Why don't transactions automatically guarantee an email is never sent twice?
25. Does TTL delete items at the exact expiration second?
26. Why doesn't IAM `dynamodb:LeadingKeys` replace backend authorization?
27. How does a GSI PK without a tenant prefix affect per-tenant IAM policies?
28. Why must Streams consumers understand multiple entity types in a single-table setup?
29. Why is restoring an entire single-table production backup in-place dangerous when recovering one enrollment?
30. When is a multi-table or hybrid design preferable?

### 19.2. Brief Suggested Answers

1. Organizes multiple entity types around queries, keys, and item collections rather than one table per entity type.
2. Keys determine what can be queried efficiently, avoiding hot-path Scans and heavy filtering.
3. Composite keys allow multiple items with the same PK and distinct SKs; uniqueness is enforced on the pair.
4. Items sharing a logical PK; physical placement can shift via adaptive capacity and splitting.
5. `GetItem` takes exact `PK+SK`; `Query` takes PK equality plus optional SK conditions/ranges.
6. No—`Query` requires partition-key equality on the chosen table/index.
7. Filters execute after the read step.
8. No; it mainly trims network payload size.
9. The filter discarded every item on that page, while more pages remain.
10. String SKs sort lexicographically, so zero-padding is required.
11. Base-table `Query` by course PK and `ENROLLMENT#` prefix.
12. GSI1, with eventual consistency.
13. Single source-of-truth edge updated once with automatic GSI sync—no dual base copies.
14. When both directions demand strongly consistent reads or face index constraints.
15. GSIs can change PK and are eventual-only; LSIs keep the same PK and can be strong.
16. Only on tables with at least one LSI, counting base items + projected LSI entries per PK.
17. Indexes only published items, avoiding reading and filtering out drafts.
18. Remove both index keys so the course drops out of GSI2.
19. Keys only / chosen attributes / all attributes—trading off storage, writes, and follow-up reads.
20. Heavy writes hitting the same logical PK, counter item, or physical partition range.
21. AP4 must query across all shards, then merge and paginate.
22. 100 actions and 4 MB total.
23. `attribute_not_exists(PK)` (and/or SK) on the target item.
24. Email sends occur outside the DynamoDB transaction; network timeouts/retries can duplicate them.
25. No, TTL runs asynchronously.
26. IAM restricts leading keys, not user permissions over specific courses/resources.
27. It can break or bypass tenant-scoped policies, requiring index/policy redesign.
28. User, course, lesson, and enrollment mutations all share one stream.
29. It would clobber valid recent changes across all other entities; restore to a temp table and merge selectively.
30. When datasets, teams, backups, KMS keys, TTLs, or workloads are independent with low access correlation.

### 19.3. Design Exercise A — One-to-Many

Add **reviews** to each course with these requirements:

- List the 20 newest reviews for a course;
- `GetItem` a single review by `reviewId`;
- Only the review author or an instructor can edit content;
- TTL for temporary moderation drafts.

Hint:

~~~text
PK=TENANT#t1#COURSE#c1
SK=REVIEW#2026-11-20T03:20:00Z#r1
~~~

Analyze the issue: with a timestamp inside SK, **`GetItem` by `reviewId` alone** cannot form SK without knowing the timestamp. You need a **lookup mapping**, another stable SK, a GSI, or an API contract passing the timestamp. Also evaluate whether editing a review updates its timestamp and thus its key.

### 19.4. Design Exercise B — Many-to-Many

An instructor teaches multiple courses, and each course has multiple instructors. Design:

- Query all instructors of a course;
- Query all courses of an instructor;
- Unassigning an instructor must take effect immediately on the very next API call;
- Display instructor names without issuing 100 sequential `GetItem` calls.

Compare:

1. Single-edge + GSI (lighter writes, eventual GSI reads).
2. Dual-edge transaction (strong consistency in both directions).
3. Separate `CourseAssignments` table (decoupled lifecycle and permissions).

Never assume an eventual GSI suffices for immediate permission revocation; authorization checks may require a base-table strong read.

### 19.5. Design Exercise C — Performance Measurement

With 1,000 course IDs following a Zipf distribution (a few courses are scorching hot), design:

- A traffic generator matching production key skew;
- Metrics for consumed read/write units, throttles, p95/p99 latency, and GSI lag;
- Comparison of one PK/course vs. 8 enrollment shards/course;
- AP4 read fan-out cost after sharding;
- Tests for duplicate enrollments and transaction conflicts;
- How to detect when GSI reads lag behind base writes.

**Never declare a design optimal purely by counting tables/indexes**—decide from measured performance, complexity, and real cost.

## 20. Production Deployment Checklist

### Access Patterns and Keys

- [ ] Cataloged entities, relationships, access patterns, QPS, read/write ratios, latency, and consistency requirements.
- [ ] Every critical read uses `GetItem` or `Query` on table/index keys without hot Scans.
- [ ] PKs have sufficient cardinality and standardized tenant prefixes.
- [ ] SK prefixes, versioning, zero-padding, and timestamp formats are documented in the data contract.
- [ ] Items carry `entityType` and `schemaVersion` where needed.
- [ ] One-to-many uses item collections rather than cramming unbounded lists into one item.
- [ ] Many-to-many uses edge/GSI/dual-edge with explicit consistency and atomicity choices.
- [ ] Sharding designs include routing versions and merge-pagination logic.

### Indexes and Capacity

- [ ] GSI partition-key diversity is measured to prevent accidental hot GSI PKs.
- [ ] Sparse index keys are added/removed accurately when status changes.
- [ ] Projections contain only fields the app needs without leaking unnecessary PII.
- [ ] `ConsistentRead=true` is never sent to GSIs.
- [ ] LSIs are created only when strong alternate sorting is essential and the 10 GB item-collection limit is safe.
- [ ] Verified 400 KiB item size and 1 MB Query page behavior with `LastEvaluatedKey` pagination.
- [ ] Load-tested traffic bursts, hot keys, and adaptive capacity, with alarms configured.
- [ ] Estimated billing mode, on-demand/provisioned, Global Table mode, and GSI costs.

### Correctness and Security

- [ ] Conditional writes prevent duplicates; optimistic locking guards concurrent edits.
- [ ] Transactions target distinct items within 100 actions and 4 MB limits.
- [ ] Durable business idempotency operation IDs cover network retries and external side effects.
- [ ] TTL is never used as real-time business authorization or strict expiry enforcement.
- [ ] Least-privilege IAM tested with `LeadingKeys` / tenant-scoped GSIs where suitable.
- [ ] Backend verifies tenant membership and resource ownership rather than trusting client-supplied `tenantId`.
- [ ] No credentials or PII in keys, logs, or over-projected GSIs.
- [ ] PITR/backups, KMS encryption, and restore drills are established.

### Operations and Cost

- [ ] Streams consumers handle multiple entity types, idempotency, and per-type failures.
- [ ] Retries/backoff and alerts differentiate throttling, `ConditionalCheck`, and `TransactionCanceled`.
- [ ] Clear UX/fallback handling for missing/stale GSI results right after writes.
- [ ] Migration plans and rollback windows exist for key-schema/GSI changes.
- [ ] Archival/S3 storage plans exist for growing items or large objects.
- [ ] Cost allocation tracks base, GSI, storage, transactions, PITR, Streams, and logs.
- [ ] Sandboxes use dummy data with clear ownership and cleanup policies.
- [ ] Re-evaluate multi-table/hybrid when isolation or operational boundaries outgrow one table.

**Expected outcome:** learners can design a DynamoDB table serving multiple entities and relationships driven by clear access patterns; select PK/SK/GSI/LSI appropriately, understand consistency and pagination, enforce invariants with conditions and transactions, and operate securely with monitoring, recovery, and cost control.

## Official AWS Documentation

- [Data modeling for DynamoDB tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling.html)
- [Data modeling foundations: single-table vs multiple tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-foundations.html)
- [First steps for modeling relational data](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-modeling-nosql.html)
- [DynamoDB data modeling building blocks](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-blocks.html)
- [Data modeling schema packages and access patterns](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-schemas.html)
- [Adjacency list pattern for many-to-many relationships](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-adjacency-graphs.html)
- [Best practices for partition key design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html)
- [Key condition expressions and Query API](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html)
- [Query filter expression and capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html)
- [Pagination with Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html)
- [Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html)
- [Local secondary indexes and 10 GB item collection limit](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LSI.html)
- [General secondary index design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes-general.html)
- [Read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html)
- [DynamoDB transactions and limits](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html)
- [Optimistic locking with version numbers](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBMapper.OptimisticLocking.html)
- [DynamoDB adaptive capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html)
- [DynamoDB fine-grained IAM access via LeadingKeys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html)
- [DynamoDB time to live (TTL)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)
- [DynamoDB Streams and Lambda](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)
- [DynamoDB point-in-time recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/PointInTimeRecovery.html)
- [Global tables consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html#HowItWorks.ReadConsistency.GlobalTables)
- [AWS SDK for Java 2.x DynamoDB code examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_dynamodb_code_examples.html)
- [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Applicability note:** Table names, AWS accounts/Regions, tenant/user/course IDs, QPS figures, API responses, and code snippets in this lesson are **training examples**. AWS may update features, quotas, consistency modes, pricing, and API details. Before deploying to production, verify current AWS documentation, run benchmarks and security negative tests in a sandbox, protect sensitive data, and maintain rollback plans and change-approval workflows.
