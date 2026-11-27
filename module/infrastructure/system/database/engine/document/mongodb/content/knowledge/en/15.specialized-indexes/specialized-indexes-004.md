# TTL Indexes, Expiration Time, and Background Deletion Latency in MongoDB

## 1. What Problem Does a TTL Index Solve?

A database should not retain every document forever. Many types of data are only valid for a limited window:

- Login sessions, one-time passwords (OTPs), and password-reset tokens.
- Temporary cached data and time-bounded processing requests.
- Technical logs, events, or telemetry metrics that only need to be retained for a number of days.
- Temporary job records after processing finishes.
- Telemetry data with an explicit retention policy.

If an application had to run its own cron job to purge old data, it would need to manage schedules, avoid duplicate workers, and handle failures. MongoDB provides **Time-To-Live indexes (TTL indexes)**, a special type of index that lets the server **automatically delete documents** after they expire.

Example document:

~~~javascript
{
  _id: "SESSION-001",
  userId: "USER-001",
  createdAt: ISODate("2026-01-01T10:00:00.000Z")
}
~~~

If the collection has a TTL index on **createdAt** with **expireAfterSeconds: 3600**, the document becomes eligible for deletion one full hour after **createdAt**, i.e., starting at **11:00:00 UTC** on 2026-01-01.

**Most important point:** TTL is an **asynchronous data cleanup mechanism**, not a timer that deletes down to the exact second. An expired document **can still exist and still be returned by queries** for a period until the background deletion task processes it. If a token expires at 11:00:00, the authentication system must reject the token at that time per business rules, **not wait until the document disappears**.

~~~text
Document is created
       |
       v
Date field + expireAfterSeconds
       |
       v
Expiration timestamp (deadline)
       |
       +------> Application explicitly checks deadline
       |        to reject expired data
       |
       v
TTL monitor runs periodic background scan
       |
       v
Deletes eligible documents
       |
       v
Replication / index updates / logical space reclamation
~~~

## 2. What Is a TTL Index Actually?

A TTL index is a **single-field index** on a field containing a **BSON Date** or an array containing BSON Date values. It carries the **expireAfterSeconds** option to determine when a document becomes eligible for deletion.

Example:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_created_at",
    expireAfterSeconds: 3600
  }
);
~~~

Meaning:

- **{createdAt: 1}:** index on the `createdAt` field, ascending order.
- **expireAfterSeconds: 3600:** each document expires 3,600 seconds after the timestamp stored in `createdAt`.
- **name:** index name for identification, administration, and configuration updates.
- The **mongod** TTL monitor processes documents that have become eligible for deletion.

A TTL index can still support queries on the indexed field just like a regular index, but its special role is **automatic data deletion**. Therefore, creating or modifying a TTL index directly impacts **retention for the entire collection**, not just query speed.

### 2.1. Expiration Time Formula

When configured as a duration relative to a date stored in the document:

\[
\text{expiryTime}=\text{indexedDate}+\text{expireAfterSeconds}
\]

Once the server's current time reaches or passes **expiryTime**, the document is **eligible** for the TTL monitor to delete. Being **eligible** does not mean **already physically deleted**.

Examples:

| `indexedDate` Value | `expireAfterSeconds` | Time Eligible for Deletion |
|---|---:|---|
| 10:00:00 UTC | 60 | 10:01:00 UTC |
| 10:00:00 UTC | 3,600 | 11:00:00 UTC |
| 10:00:00 UTC | 86,400 | 10:00:00 UTC the next day |
| 10:00:00 UTC | 0 | Immediately at `indexedDate` |

In the last row, **0** is a valid value for **expireAfterSeconds**: it does not disable TTL.

### 2.2. BSON Date vs. Date/Time Strings

The following two documents mean different things:

~~~javascript
{
  _id: "GOOD",
  createdAt: ISODate("2026-01-01T10:00:00.000Z")
}

{
  _id: "WRONG_TYPE",
  createdAt: "2026-01-01T10:00:00.000Z"
}
~~~

**GOOD** has `createdAt` of type **BSON Date**. **WRONG_TYPE** only has a string even though it looks like ISO-8601. TTL indexes rely on **BSON Date**; a document whose field is not a Date or an array containing no Dates will **not be deleted by TTL based on that field**.

To check types:

~~~javascript
db.sessions.aggregate([
  {
    $project: {
      _id: 1,
      createdAt: 1,
      createdAtType: { $type: "$createdAt" }
    }
  }
]);
~~~

The output may show **"date"**, **"string"**, **"null"**, or **"missing"**. This distinction is critical when data arrives from REST APIs, JSON imports, or Java mappers.

## 3. Two Expiration Models: Relative Duration vs. Absolute Timestamp

### 3.1. Expire N Seconds After `createdAt`

When retaining logs for 7 days from creation time:

~~~javascript
db.event_logs.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_event_logs_7d",
    expireAfterSeconds: 7 * 24 * 60 * 60
  }
);
~~~

Document:

~~~javascript
db.event_logs.insertOne({
  eventType: "API_REQUEST",
  createdAt: new Date(),
  message: "request completed"
});
~~~

Each document expires based on **createdAt + 604800 seconds**. Every document in the collection shares the same **7-day** retention policy on that index.

**Use when:** data of the same kind has a uniform lifespan, such as 7-day logs or 30-minute session records from creation.

### 3.2. Expire at Each Document's Own Timestamp

When each token has a different **expiresAt**—for example, one token expires in 10 minutes and another in 24 hours:

~~~javascript
db.tokens.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_tokens_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

Insert two tokens:

~~~javascript
const now = new Date();

db.tokens.insertMany([
  {
    _id: "TOKEN-SHORT",
    createdAt: now,
    expiresAt: new Date(now.getTime() + 10 * 60 * 1000)
  },
  {
    _id: "TOKEN-LONG",
    createdAt: now,
    expiresAt: new Date(now.getTime() + 24 * 60 * 60 * 1000)
  }
]);
~~~

With **expireAfterSeconds: 0**, the TTL index uses **expiresAt** directly as the deletion-eligibility timestamp. The application can assign a distinct `expiresAt` per document.

**Use when:** each record has a business-determined deadline, such as OTPs, reset tokens, booking holds, or jobs with varying deadlines.

### 3.3. Do Not Mix Up Relative Duration and Absolute Timestamp

If a document already stores **expiresAt = createdAt + 10 minutes** and the index sets **expireAfterSeconds: 600**, TTL only makes it eligible for deletion **10 minutes after `expiresAt`** — 20 minutes total from `createdAt`.

~~~text
createdAt = 10:00
expiresAt = 10:10

TTL {expiresAt:1}, expireAfterSeconds:0
    -> eligible for deletion at 10:10

TTL {expiresAt:1}, expireAfterSeconds:600
    -> eligible for deletion at 10:20
~~~

Always clarify whether the field represents **"age start time"** or **"final expiration timestamp"** before creating the index.

### 3.4. Does TTL Delete Only the Expired Field?

No. A TTL index marks and **deletes the entire document**, not just the `createdAt`/`expiresAt` field value. For example, an account has:

~~~javascript
{
  _id: "USER-001",
  email: "user@example.test",
  profile: { displayName: "Example" },
  resetCodeExpiresAt: ISODate("2026-01-01T10:10:00Z")
}
~~~

Putting a TTL index on **resetCodeExpiresAt** in the **users** collection can cause **the entire user document** to be deleted when the recovery code expires. This is a severe data-modeling bug.

Solution: store recovery codes in a separate temporary collection such as **password_reset_tokens**, or use **$unset** logic and a dedicated job if you genuinely only want to clear a single attribute.

## 4. Creating a TTL Index in `mongosh`

### 4.1. Prepare a Dedicated Lab Collection

~~~javascript
use ttl_index_lab

db.createCollection("sessions");
~~~

If the collection already exists, skip **createCollection** or pick a different collection name. Commands in this lesson mutate data in the target database, so run them only in a test environment.

### 4.2. Create a 30-Minute TTL Index

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_30m",
    expireAfterSeconds: 1800
  }
);
~~~

Insert documents:

~~~javascript
db.sessions.insertMany([
  {
    _id: "S-RECENT",
    userId: "U-001",
    createdAt: new Date()
  },
  {
    _id: "S-OLD",
    userId: "U-002",
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000)
  }
]);
~~~

**S-OLD** is already past 30 minutes from `createdAt` and is therefore **eligible for deletion**. It can still appear in queries immediately after insertion until the TTL monitor processes it.

### 4.3. Inspect TTL Configuration with `getIndexes`

~~~javascript
db.sessions.getIndexes();
~~~

A condensed result looks like:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 }
  },
  {
    name: "ttl_sessions_30m",
    key: { createdAt: 1 },
    expireAfterSeconds: 1800
  }
]
~~~

Actual metadata may include version and additional options depending on MongoDB version. Verify **the single Date-field key**, **expireAfterSeconds**, and **name**.

### 4.4. 0-Second TTL on `expiresAt`

~~~javascript
db.password_reset_tokens.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_reset_token_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

Document:

~~~javascript
db.password_reset_tokens.insertOne({
  tokenHash: "hash-not-plain-text",
  userId: "U-001",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

In production, never store sensitive reset tokens in plaintext. Token generation, hashing, verification, and invalidation must be designed separately; TTL only handles cleanup.

## 5. When Does a Document Actually Disappear? Background Deletion Latency

### 5.1. Expiration Time vs. Deletion Time

Suppose a document has **expiresAt = 10:05:00 UTC** and a TTL index with **expireAfterSeconds: 0**:

~~~text
10:04:59       Document has not expired yet
10:05:00       Expired per business deadline
10:05:01       Application must treat it as no longer valid
10:05:15       Document may still remain in the collection
10:06:00       TTL monitor may have processed it, or may be busy
10:06:30+      Under backlog/heavy load, document may still persist
...            TTL monitor deletes when it gets a turn and resources
~~~

The timestamps after 10:05:00 merely illustrate **potential lag**, not a latency guarantee from MongoDB.

The MongoDB TTL monitor is a background task that typically **runs roughly every 60 seconds**. Consequently, there can be a wait before deletion even begins for newly expired documents. After that, completion time depends on the volume of expired data and system load.

**There is no default SLA promising "guaranteed deletion in exactly 60 seconds."** When millions of documents expire together, the backlog can take significantly longer.

### 5.2. Why Does the TTL Monitor Introduce Latency?

Several reasons:

1. **Scan interval:** a document may expire right after the monitor finishes a check.
2. **Multiple TTL indexes:** the monitor must service multiple indexes/collections.
3. **Large backlog:** hundreds of thousands or millions of documents are already eligible for deletion.
4. **Write and delete load:** actual deletes consume CPU/I/O, update indexes, and impact replication.
5. **Replica set failover:** when primary changes, the TTL deletion process must run on the new primary.
6. **Slow storage or resource pressure:** the server may not complete all pending work within one cycle.
7. **Time series buckets:** deletion may have to wait until the entire bucket expires, not just a single measurement.

Think of TTL as **eventual cleanup**, not a hard real-time scheduler.

### 5.3. TTL Monitor Pass and Sub-Pass Mechanics

In modern MongoDB versions, the TTL background process iterates over TTL indexes and deletes expired documents in phases. For each index, processing moves on to the next index when one of these conditions occurs:

- **50,000 documents** have been deleted from the current index;
- Roughly **one second** has been spent deleting on the current index;
- All currently eligible documents for that index have been deleted.

After visiting the TTL indexes, one **sub-pass** finishes. The monitor continues additional sub-passes if eligible data remains. One **pass** finishes when all eligible documents across all TTL indexes in that round have been processed.

In addition, processing has time limits so a single cleanup cycle does not run indefinitely; TTL deletion is fundamentally a **single-threaded** background task in MongoDB's architecture description. Starting in **MongoDB 6.1**, the server can **batch delete operations** to improve efficiency.

Numbers like **50,000** or **one second** explain fairness and per-index time slicing; they are **not** a promise that MongoDB always deletes 50,000 documents every second.

### 5.4. "Background Task" Does Not Mean Deletion Is Resource-Free

The TTL monitor runs in the background to locate data to remove, yet the resulting **delete** operations are still regular writes that affect:

- collection documents and indexes;
- cache and storage engine;
- journal/replication depending on deployment topology;
- oplog and applying deletes on replica set secondaries;
- disk usage and query serving latency.

TTL can generate heavy load if a large batch of documents expires simultaneously. Therefore, retention design must account for both **document creation rate** and **sustainable deletion rate**.

## 6. Expired Yet Still Present: Handling It at the Application Layer

### 6.1. Do Not Grant Access Based Solely on Document Presence

Suppose an application verifies an OTP using:

~~~javascript
// Business logic bug: document may still exist after expiration.
db.otp_tokens.findOne({
  tokenHash: suppliedHash
});
~~~

If the document is past its expiration yet the TTL monitor has not deleted it, the query can still return a match. This could allow an expired token to be used.

Instead, always enforce **expiresAt**:

~~~javascript
const now = new Date();

const token = db.otp_tokens.findOne({
  tokenHash: suppliedHash,
  expiresAt: { $gt: now },
  status: "ACTIVE"
});
~~~

This query returns only tokens whose deadline is still valid at check time. In production APIs, use a reliable time source, manage clock skew, and check expiration consistently.

### 6.2. Session Validation Query Pattern

~~~javascript
db.sessions.findOne({
  _id: "S-RECENT",
  revoked: { $ne: true },
  expiresAt: { $gt: new Date() }
});
~~~

If the session has expired, the query returns no valid session even if TTL cleanup has not run yet. Note that using **revoked: {$ne:true}** also matches missing fields; if security policy demands explicit state, use **status: "ACTIVE"** or a strict schema rather than an ambiguous negation.

### 6.3. Validating and Consuming a One-Time Token

If an OTP may be used only once, checking and deleting in two separate steps introduces a race condition. Consider an atomic **findOneAndDelete** operation with the deadline predicate:

~~~javascript
const token = db.otp_tokens.findOneAndDelete({
  tokenHash: suppliedHash,
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
});
~~~

If nothing matches, the token is expired, invalid, or already consumed. This example assumes a single valid token per **tokenHash** with an appropriate unique index and controls. Real systems also need brute-force protection, rate limiting, token hashing, tenant/user checks, auditing, and network failure handling.

The TTL index cleans up unused tokens; **enforcing expiration on time is the application's responsibility**.

### 6.4. Distinguishing Retention from Legal Deletion

TTL can form part of a retention strategy, yet it is **unsuitable when immediate, exact-time deletion is required** (e.g., after revoking access, urgent legal requests, or completing sensitive transactions). When immediate event-driven removal is required, the application must run **deleteOne/deleteMany** with appropriate predicates and write acknowledgments—never wait for TTL.

Deleting a document from a collection also does not automatically erase copies in backups, archives, logs, or downstream systems. Data deletion policies must address the entire data lifecycle.

## 7. TTL Indexes Only Work with Proper Time Data Types

### 7.1. BSON Date, Not String or BSON Timestamp

~~~javascript
db.ttl_examples.insertMany([
  {
    _id: "DATE",
    expiresAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "STRING",
    expiresAt: "2026-01-01T00:00:00Z"
  },
  {
    _id: "NULL",
    expiresAt: null
  },
  {
    _id: "MISSING"
  }
]);
~~~

If this collection has a TTL index **{expiresAt: 1}** with **expireAfterSeconds: 0**, MongoDB can delete **DATE** when it expires. **STRING**, **NULL**, and **MISSING** lack a valid BSON Date and will not expire under that TTL index.

**BSON Timestamp** is a distinct internal type (commonly used for replication), not a BSON Date. Never store a Timestamp in a TTL field and expect it to behave like a calendar date/time.

### 7.2. When the Field Is an Array of Date Values

MongoDB supports TTL indexes on fields containing an **array of Date values**. When multiple Dates exist, TTL uses the **earliest date** in the array to compute expiration.

~~~javascript
{
  _id: "ARRAY-DATES",
  cleanupTimes: [
    ISODate("2026-01-01T10:00:00Z"),
    ISODate("2026-01-01T12:00:00Z")
  ]
}
~~~

With **expireAfterSeconds: 0**, the document becomes eligible for deletion at **10:00**, without waiting for 12:00. This easily causes premature data loss if an application stores "a list of deadlines" expecting MongoDB to wait for the latest deadline.

If business logic requires deletion only once **every element** in the array has expired, store a maintained **latestExpiresAt** field instead of placing TTL directly on the date array.

### 7.3. Missing Fields or Wrong Types Cause Data to Live Forever

For example, if an import writes one million documents and 2% have **createdAt** stored as a string due to a mapper bug, that 2% can accumulate without ever being purged by TTL.

MongoDB does not automatically coerce types or treat ISO strings as BSON Dates. Safeguards:

1. Use schema validation requiring the time field to have **bsonType: "date"**.
2. Verify type conversion in drivers/DTOs.
3. Periodically monitor for documents missing the field or having an invalid type.
4. Migrate legacy records in batches before expecting TTL to work across all data.

Example checking documents missing the field:

~~~javascript
db.sessions.countDocuments({
  createdAt: { $exists: false }
});
~~~

Example checking documents where the field exists with the wrong type:

~~~javascript
db.sessions.countDocuments({
  createdAt: {
    $exists: true,
    $not: { $type: "date" }
  }
});
~~~

Be cautious running type-inspection queries on huge collections, as they can incur heavy I/O. If legacy data contains Date arrays or missing fields, define "invalid" accurately for your domain rather than applying a single predicate blindly everywhere.

## 8. Schema Validation for TTL Fields

MongoDB provides **$jsonSchema** to guard document structure on writes. For sessions that require `createdAt`:

~~~javascript
db.createCollection("validated_sessions", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["createdAt", "userId"],
      properties: {
        createdAt: {
          bsonType: "date",
          description: "Session creation time must be BSON Date"
        },
        userId: {
          bsonType: "string"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.validated_sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800, name: "ttl_validated_session_30m" }
);
~~~

If the application tries to insert:

~~~javascript
db.validated_sessions.insertOne({
  userId: "U-001",
  createdAt: "2026-01-01T10:00:00Z"
});
~~~

MongoDB rejects it because **createdAt** is a string rather than a BSON Date. Validators reduce the risk of "documents never expiring due to wrong type".

**Note:** validators do not retroactively modify documents inserted before the rule was enabled. Existing documents must be identified and migrated intentionally. Also, whether to allow Date arrays, null, or missing fields is a separate schema decision; this example specifies **one required BSON Date**.

## 9. Important TTL Index Limitations

### 9.1. TTL Only Supports Single-Field Indexes

~~~javascript
// Valid TTL on a single Date field in a standard collection:
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

Do not create a **compound TTL index** expecting conditional TTL:

~~~javascript
// Wrong intent: compound TTL does not work as standard TTL.
db.events.createIndex(
  { tenantId: 1, createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

MongoDB defines TTL indexes as **single-field**; compound indexes **do not support TTL**, and **expireAfterSeconds** on a compound index does not provide TTL functionality. If you need fast queries by tenant and time, create a **separate query index** and a **separate TTL index**.

~~~javascript
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400, name: "ttl_event_1d" }
);

db.events.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "ix_tenant_event_created" }
);
~~~

The two indexes serve **two distinct purposes**: expiration cleanup and tenant-scoped querying.

### 9.2. Cannot Create a TTL Index on `_id`

The default **_id_** index does not support TTL. You cannot use:

~~~javascript
// Cannot use _id as the key of a TTL index.
db.events.createIndex(
  { _id: 1 },
  { expireAfterSeconds: 3600 }
);
~~~

Even when **_id** is an ObjectId embedding a timestamp, it is **not a BSON Date**, and `_id` does not support TTL. Create a dedicated **createdAt** or **expiresAt** field.

### 9.3. Cannot Apply TTL Indexes to Capped Collections

MongoDB does not support TTL indexes on **capped collections**. Capped collections have their own storage and lifecycle rules (older data is overwritten/evicted by size/count bounds when capacity is reached), which differ from TTL semantics.

### 9.4. Valid `expireAfterSeconds` Values

For standard TTL indexes, **expireAfterSeconds** is an integer from **0** to **2,147,483,647** seconds (inclusive). Do not pass negative numbers, strings, **NaN**, or invalid types.

Never treat **expireAfterSeconds: 0** as disabling TTL; it means **an offset of 0 seconds from the Date field value**.

### 9.5. Does a TTL Index Need to Be Unique?

A TTL index does not imply **unique** by default. Multiple documents can share the same **expiresAt** and all become eligible for deletion together. If business logic needs uniqueness on a key such as **tokenHash**, create a separate unique index per your data model:

~~~javascript
db.tokens.createIndex(
  { tokenHash: 1 },
  { unique: true, name: "uq_token_hash" }
);

db.tokens.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_token_expires_at" }
);
~~~

The TTL index does not automatically enforce uniqueness on `tokenHash`. Adding another index has maintenance overhead and must be weighed against the workload.

### 9.6. Cannot Change TTL by Re-Calling `createIndex`

Suppose you already have:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800, name: "ttl_sessions_30m" }
);
~~~

Calling **createIndex** again with the same key and a different **expireAfterSeconds: 3600** is not the standard way to modify an existing index. MongoDB validates index specifications and can reject incompatible option changes. Use **collMod** as shown in Section 10.

### 9.7. A Hidden TTL Index Still Deletes Data

A **hidden index** is hidden from the query planner, yet it still exists and is maintained. If it is a TTL index, automatic deletion **continues to run**.

~~~javascript
db.sessions.hideIndex("ttl_sessions_30m");
~~~

This command **does not pause TTL deletion**. Do not use **hideIndex** as a "pause expiration" switch. Changing retention policies requires a dedicated procedure; toggling the server-level TTL monitor carries severe operational risks.

## 10. Modifying TTL Expiration with `collMod`

### 10.1. Changing from 30 Minutes to 60 Minutes

If a TTL index on **createdAt** currently has **expireAfterSeconds: 1800**, use **collMod**:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 3600
  }
});
~~~

Or target the index by name depending on API/version:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    name: "ttl_sessions_30m",
    expireAfterSeconds: 3600
  }
});
~~~

**collMod** modifies the TTL property **without rebuilding the entire index**. Note that an old index name like **ttl_sessions_30m** no longer reflects a 60-minute retention; choose index names so they do not mislead operators, and update operational docs accordingly.

### 10.2. Shortening TTL Can Trigger a "Delete Storm"

Suppose a collection keeps 30 days of logs. Changing **expireAfterSeconds** to 1 day means all documents aged 2–30 days **immediately become expired**. The TTL monitor may kick off a massive deletion backlog right after the configuration change.

Risks:

- Spikes in CPU/I/O and write latency;
- replication lag;
- degraded performance for live queries;
- heavy resource usage updating indexes;
- storage fragmentation and disk space not shrinking immediately by the logical deleted volume.

MongoDB recommends considering **deleting overdue data in small batches before shortening TTL**, and only then running **collMod**. Batch deletions should be rate-limited while protecting primary queries and monitoring replication.

### 10.3. Converting a Regular Index to a TTL Index

Starting in **MongoDB 5.1**, MongoDB supports converting an eligible **single-field regular index** into a TTL index by adding **expireAfterSeconds** via **collMod**.

For example, a regular index with key **{createdAt: 1}**:

~~~javascript
db.runCommand({
  collMod: "sessions",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 1800
  }
});
~~~

Before converting, verify:

1. The existing index has a supported field, type, and definition;
2. Existing documents have valid BSON Date `createdAt` values;
3. How many documents are already older than 30 minutes;
4. Whether the system can absorb the deletion load and retention policy;
5. Backups and recovery procedures are ready in case the index was misconfigured.

**Adding a TTL index on existing data can immediately make huge numbers of documents eligible for deletion** as soon as the index build completes. Never treat this as "just adding a query-optimization index".

### 10.4. Dropping a TTL Index Stops New Deletions Without Restoring Data

~~~javascript
db.sessions.dropIndex("ttl_sessions_30m");
~~~

Once the TTL index is dropped, remaining documents stop being cleaned up by that TTL index. However, documents **already deleted by TTL will not magically come back**.

**Dropping an index is not a data rollback.** Distinguish restoring a retention configuration from restoring deleted documents from backups.

## 11. TTL on Replica Sets and Sharded Clusters

### 11.1. Replica Sets

In a replica set, the TTL monitor actively deletes documents only when the node is in the **primary** state. **Secondaries** do not run independent TTL deletion loops to decide which documents to delete; they **apply delete operations replicated from the primary**.

~~~text
             Replica set

             PRIMARY
       TTL monitor finds expired docs
                  |
                  v
         Delete documents
                  |
                  v
             Oplog entries
               /      \
              v        v
         SECONDARY  SECONDARY
          Apply        Apply
          deletes      deletes
~~~

This keeps TTL deletions consistent with replication. During failover or replication lag, when a document expires and when replicas reflect its removal can diverge.

If an application reads from secondaries, expired data can still be visible during replication lag—even after the primary deleted it. Therefore, **explicit `expiresAt` predicates in queries and authorization logic** remain essential.

### 11.2. Sharded Clusters

In a sharded cluster, data is distributed across multiple shards. TTL deletion is executed by the **primary `mongod` of each respective shard**, following cluster operational rules. Do not think of TTL as a single cluster-wide job running once at `mongos`.

Factors affecting latency:

- proportion of expired documents on each shard;
- shard key distribution and write volume;
- number of TTL indexes per shard;
- replication lag and resource headroom on each replica set;
- chunk migrations/balancer activity and cluster state.

One shard holding older data than others can accumulate a much larger TTL backlog. Monitor each node/shard individually, not just cluster-wide averages.

### 11.3. TTL Indexes Do Not Replace Shard Keys or Ensure Tenant Isolation

If a collection stores multi-tenant data, a TTL index on **expiresAt** deletes based on each document's expiration time. It does not check tenant permissions, does not create a compound `tenantId+expiresAt` index, and does not replace tenant filtering in the application.

Authorization, query indexing, and TTL policy are three separate concerns:

~~~text
Authorization: tenantId / role
Query speed:   {tenantId:1, expiresAt:1} (if appropriate)
TTL cleanup:   {expiresAt:1}, expireAfterSeconds:0
~~~

## 12. TTL with Time Series Collections: Additional Bucket Latency

MongoDB supports **time series collections** for storing time-ordered measurements. Time series collections pack documents into **buckets** and have distinct TTL rules.

Example creating a time series collection with 24-hour retention:

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensorId",
    granularity: "seconds"
  },
  expireAfterSeconds: 24 * 60 * 60
});
~~~

Here, **expireAfterSeconds** is a **time series collection creation option**, unlike creating a regular TTL index on an arbitrary field.

### 12.1. The Entire Bucket May Have to Expire Before Deletion

With time series, MongoDB deletes a bucket once **all measurements in the bucket have expired** per the corresponding policy. This means an individual measurement may have passed its retention deadline while the bucket still holds newer measurements, so it remains until the whole bucket qualifies for cleanup.

~~~text
Bucket:
  measuredAt 10:00
  measuredAt 10:15
  measuredAt 10:40

TTL = 1 hour

The 10:00 measurement reaches 1 hour at 11:00,
but the bucket contains data up to 10:40;
the bucket may not be deleted before 11:40,
and then still waits for TTL background cleanup.
~~~

This is a logical illustration with sample timestamps; exact bucket closure depends on bucket/granularity settings and MongoDB version.

**Conclusion:** Time series TTL can exhibit longer latency than the ~60-second monitor cycle alone, because it waits for whole-bucket expiration.

### 12.2. Partial TTL on Time Series

Starting in **MongoDB 7.0**, MongoDB supports **partial TTL indexes** on time series collections under specific rules: the TTL index uses **timeField** as its key, while **partialFilterExpression** filters on **metaField**. This allows a shorter retention period for measurements matching specific metadata compared to the collection's overall retention.

This capability **does not mean** regular collections can create compound TTL indexes or TTL indexes with arbitrary partial filter expressions. Always verify against your exact server version, collection type, and `timeField`/`metaField` rules.

### 12.3. Do Not Confuse TTL Indexes with Collection `expireAfterSeconds`

| Storage Type | Typical Configuration Mechanism |
|---|---|
| Standard collection | **createIndex({dateField:1}, {expireAfterSeconds:N})** |
| Time series collection | **expireAfterSeconds** in collection config; partial TTL index supported in specific cases from 7.0 |
| Supported clustered collection | Collection-level retention configurable per that collection type's documentation |

Do not copy time series collection options verbatim onto a standard collection.

## 13. Monitoring the TTL Monitor and Deletion Backlog

### 13.1. Reading `metrics.ttl` in `serverStatus`

In `mongosh`:

~~~javascript
const status = db.serverStatus();
printjson(status.metrics.ttl);
~~~

Metrics typically present in supported versions:

- **metrics.ttl.deletedDocuments:** count of documents deleted by TTL in the current statistics lifetime.
- **metrics.ttl.passes:** number of completed TTL passes.
- **metrics.ttl.subPasses:** number of completed TTL sub-passes.

Sample structure (illustrative numbers):

~~~javascript
{
  deletedDocuments: NumberLong(250000),
  passes: NumberLong(120),
  subPasses: NumberLong(340)
}
~~~

These counters are **cumulative**, not "documents deleted per second". To measure deletion rate, take the **delta between two samples** divided by elapsed time.

~~~javascript
const first = db.serverStatus().metrics.ttl;
// Take second reading after an interval managed by monitoring.
const second = db.serverStatus().metrics.ttl;
~~~

The snippet only illustrates the data source; two consecutive commands run back-to-back cannot measure rate. In production, monitoring polls metrics on a fixed interval and handles counter resets (restarts/rotations) properly.

### 13.2. Checking the List of TTL Indexes

~~~javascript
db.sessions.getIndexes();
~~~

Verify the Date field, index name, **expireAfterSeconds**, and index state. If a collection lacks a TTL index due to a failed migration or accidental drop, do not expect the monitor to clean it up.

### 13.3. Checking the Backlog of Expired Documents

For **expiresAt + 0 seconds** TTL:

~~~javascript
const now = new Date();

db.tokens.countDocuments({
  expiresAt: {
    $type: "date",
    $lte: now
  }
});
~~~

The count represents an **estimate of deletion-eligible documents still present at query time**, not a guarantee that all of them will disappear in the next cycle. Data may also continue changing concurrently while the query runs.

For **createdAt + 1800 seconds** TTL:

~~~javascript
const cutoff = new Date(Date.now() - 1800 * 1000);

db.sessions.countDocuments({
  createdAt: {
    $type: "date",
    $lte: cutoff
  }
});
~~~

These queries can be expensive on huge, high-traffic collections. Do not schedule full scans every second to "monitor TTL". Rely on indexes and scale-appropriate sampling/metrics.

### 13.4. Observing Active TTL Operations

MongoDB can display active TTL monitor deletes in **db.currentOp()** or corresponding monitoring tools, depending on privileges and version:

~~~javascript
db.currentOp();
~~~

Not seeing a TTL delete in `currentOp` **does not prove the monitor is disabled**: it may simply be between runs or finishing very quickly.

### 13.5. Useful Operational Metrics

| Metric | Interpretation |
|---|---|
| **Expired-but-present document count** | Backlog of overdue documents still visible to queries. |
| **TTL deletedDocuments rate** | Actual deletion throughput over a measurement interval. |
| **TTL passes/subPasses** | Monitor activity and processing rounds. |
| **Replication lag** | Whether secondaries are keeping up with deletes from primary. |
| **Disk I/O, cache pressure** | Operational impact during heavy deletion. |
| **Write latency p95/p99** | Whether TTL deletions affect the primary workload. |
| **Collection count/storage size** | Retention trends and potential data accumulation. |

To measure **actual TTL latency**, you can sample documents with known **expiresAt** timestamps and observe when they disappear in a controlled measurement environment. There is no automatic deletion-timestamp field left behind after a document is deleted, so detailed measurement may require external instrumentation outside the source collection.

## 14. Things That Can Stop TTL or Make It Unusually Slow

### 14.1. Wrong Date Field Type

A document storing **"2026-01-01T10:00:00Z"** as a string is not automatically treated as a Date when TTL evaluates it.

**Fix:** schema validation, proper BSON Date mappers, and migrating mistyped records.

### 14.2. Missing Field or Null Value

A document without the indexed Date field is ineligible for expiration under that TTL index.

**Fix:** define the business rule for missing `expiresAt`. If every token must expire, enforce **required + bsonType:"date"** via validator.

### 14.3. Incorrect Timezone Storage or Clock Skew

If an application computes `expiresAt` using a clock skewed by several minutes, documents can expire earlier or later than intended.

**Fix:** use consistent UTC/`Instant` timestamps, NTP synchronization, avoid confusing milliseconds with seconds, and monitor clock skew across components.

### 14.4. TTL Monitor Has Not Drained the Backlog Yet

The system just enabled TTL on a collection with millions of overdue documents. The monitor drains them gradually according to resources and pass limits.

**Fix:** break historical cleanup into controlled batches before enabling or shortening TTL; monitor metrics and replication.

### 14.5. Node Is a Secondary

The TTL monitor actively deletes only on the replica set primary; secondaries apply replicated deletes. Checking metrics on a secondary does not reflect primary monitor activity.

**Fix:** verify topology and read preferences; monitor the primary and replication.

### 14.6. TTL Monitor Disabled by Operational Configuration

MongoDB has a server parameter **ttlMonitorEnabled**, enabled by default on applicable `mongod` instances. Disabling the TTL monitor prevents documents from being purged and can also affect internal subsystems relying on TTL.

MongoDB recommends **not disabling the TTL monitor in production**, unless instructed by MongoDB Support or under a carefully reviewed operational plan.

To **inspect** on a deployment with proper privileges:

~~~javascript
db.adminCommand({
  getParameter: 1,
  ttlMonitorEnabled: 1
});
~~~

Do not casually include **setParameter ttlMonitorEnabled=false** in test scripts, as it can affect multiple collections and internal features.

### 14.7. TTL Index Was Dropped or Misconfigured

If **expireAfterSeconds** is missing on the index in **getIndexes()**, the collection may not have the expected TTL index, or the index was altered/replaced.

**Fix:** verify against the actual index catalog and migration history rather than assuming Java annotations guarantee the index exists in MongoDB.

## 15. Java Sync Driver: Creating a TTL Index and Writing BSON Dates

The Java Sync Driver provides **MongoCollection.createIndex()** and **IndexOptions.expireAfter()**. The example below sets a 0-second TTL on **expiresAt** so each document has its own deadline.

### 15.1. Creating the Index in Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

import java.util.Date;
import java.util.concurrent.TimeUnit;

public final class TtlIndexExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be provided"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("ttl_index_lab");
            MongoCollection<Document> tokens =
                    database.getCollection("tokens_java");

            tokens.createIndex(
                Indexes.ascending("expiresAt"),
                new IndexOptions()
                    .name("ttl_tokens_java")
                    .expireAfter(0L, TimeUnit.SECONDS)
            );

            Date now = new Date();
            Date expiresAt = new Date(
                    now.getTime() + TimeUnit.MINUTES.toMillis(10)
            );

            tokens.insertOne(
                new Document("tokenHash", "demo-hash")
                    .append("createdAt", now)
                    .append("expiresAt", expiresAt)
            );

            System.out.println("Inserted token with expiration " + expiresAt);
        }
    }
}
~~~

Java's **Date** class is encoded to BSON Date by the appropriate codec. While this example uses `Date`, applications can use **Instant** in the domain layer and convert cleanly.

**Note:** this snippet demonstrates index creation, not a complete secret-token storage system. In production, index creation should be handled via controlled migrations rather than having every application instance uncoordinatedly create critical structures.

### 15.2. Querying Unexpired Tokens in Java

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gt;

Document token = tokens.find(
        and(
            eq("tokenHash", suppliedHash),
            eq("status", "ACTIVE"),
            gt("expiresAt", new Date())
        )
).first();
~~~

This query **filters out expired documents itself** even if the monitor has not purged them yet. **suppliedHash** is assumed to be safely processed and passed through the typed query builder rather than raw unvalidated JSON concatenation.

### 15.3. Relative TTL in Java

~~~java
tokens.createIndex(
    Indexes.ascending("createdAt"),
    new IndexOptions()
        .name("ttl_tokens_created_at_1h")
        .expireAfter(1L, TimeUnit.HOURS)
);
~~~

This illustrates **a different index with retention relative to `createdAt`**. In a real collection, having multiple TTL indexes on different fields can cause a document to be deleted according to **whichever expiration condition is met first**. Do not accidentally create both an **expiresAt TTL** and a **createdAt TTL** if the domain expects a single deadline.

### 15.4. Reading Index Metadata in Java

~~~java
for (Document indexSpec : tokens.listIndexes()) {
    System.out.println(indexSpec.toJson());
}
~~~

The Java driver uses **listIndexes()**, whereas **mongosh** provides the **getIndexes()** helper.

## 16. Spring Data MongoDB: TTL via `@Indexed` and `IndexOperations`

Spring Data MongoDB supports defining indexes via annotations and creating indexes through **MongoTemplate.indexOps()**. What matters is that the configuration is actually created in MongoDB; merely declaring an annotation in code does not guarantee the index exists.

### 16.1. Entity Using `expiresAt`

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "verification_tokens")
public class VerificationTokenDocument {

    @Id
    private String id;

    private String tokenHash;

    @Indexed(name = "ttl_verification_token", expireAfterSeconds = 0)
    private Instant expiresAt;

    // Constructor, getters, setters...
}
~~~

**Instant** is ideal for representing absolute UTC timestamps in Java. Spring Data MongoDB maps `Instant` to BSON Date using configured converters. If your system uses custom converters, verify the actual representation stored in MongoDB.

### 16.2. Do Not Confuse Annotations with Created Indexes

Depending on version and **auto-index creation** configuration, Spring Data MongoDB may not automatically create indexes from annotations at startup. After deployment, verify with:

~~~javascript
db.verification_tokens.getIndexes();
~~~

Confirm the index genuinely has **{expiresAt:1}** and **expireAfterSeconds:0**. When running multiple application instances, use a coordinated migration or mechanism to ensure indexes are created consistently.

### 16.3. Creating Indexes via `MongoTemplate`

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

// mongoTemplate is injected.
mongoTemplate.indexOps("verification_tokens").ensureIndex(
    new Index()
        .on("expiresAt", Sort.Direction.ASC)
        .named("ttl_verification_token")
        .expire(0, TimeUnit.SECONDS)
);
~~~

This example uses **IndexOperations** to manage indexes explicitly. If an index with the same key already exists with different TTL options, calling **ensureIndex** does not replace a proper migration using **collMod**.

### 16.4. Valid Query in Spring Data

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tokenHash").is(suppliedHash)
            .and("status").is("ACTIVE")
            .and("expiresAt").gt(Instant.now())
);
~~~

This query enforces validity in business logic. TTL cleanup still operates independently in the database. For concurrent authentication flows, handle atomic consume/revoke and replay protection as separate business logic.

## 17. TTL and Storage Strategies for Logs, Sessions, and Cache

### 17.1. Session Records

For sessions with a fixed 30-minute lifetime from creation:

~~~javascript
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1800 }
);
~~~

If sessions support renewal (sliding expiration), a fixed **createdAt TTL** can delete sessions that are still active. When the domain supports renewal, store an **expiresAt** updated on each extension and use **expireAfterSeconds: 0**, or choose another session model matching your contract.

### 17.2. Cache Entries

~~~javascript
db.cache_entries.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

When reading cache entries, always check **expiresAt > now**. Otherwise, the application could serve stale cached entries before the monitor deletes them. TTL is no replacement for cache staleness checks.

### 17.3. Audit and Business Events

Some audit records must be retained for legal, compliance, or investigation purposes. Never add a TTL index solely to save disk space unless a retention policy has been approved.

For general operational logs, TTL can be appropriate, though TTL deletes still generate I/O and replication load. When data needs long-term retention at lower cost, consider **archiving** before deletion.

### 17.4. Data with Different Lifetimes by Type or Tenant

For example, Tenant A retains 7 days while Tenant B retains 30 days. A TTL index **createdAt + 7 days** will not inspect `tenantId` to apply different lifetimes. Instead, store an **expiresAt** field computed according to each tenant's policy:

~~~javascript
{
  tenantId: "TENANT-A",
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  expiresAt: ISODate("2026-01-08T00:00:00Z")
}
~~~

~~~javascript
{
  tenantId: "TENANT-B",
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  expiresAt: ISODate("2026-01-31T00:00:00Z")
}
~~~

With **TTL expiresAt + 0**, each document has its own deadline without needing a compound TTL index. Test the `expiresAt` calculation thoroughly and do not allow clients to pick retention periods beyond authorized limits.

## 18. Safely Deploying TTL on Collections with Existing Data

### 18.1. Risky Scenario

An **application_logs** collection has 80 million documents spanning several years. The team wants 7-day retention and runs:

~~~javascript
db.application_logs.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_application_logs_7d",
    expireAfterSeconds: 604800
  }
);
~~~

If most documents are already older than 7 days, they **become eligible for deletion the moment the index build completes**. This can create a huge backlog and heavily impact the server for an extended period.

### 18.2. Recommended Procedure

1. **Confirm retention policy:** who approved it, which data is eligible for deletion, and whether archive/backup is required.
2. **Assess the data:** count/sample overdue documents, measure volume, verify Date field types, and inspect distribution across shards/tenants.
3. **Review topology and load:** primary/secondaries, write concern, peak hours, and capacity headroom.
4. **Throttled historical cleanup:** if massive overdue data exists, delete in small rate-limited, monitored batches instead of flipping TTL on abruptly.
5. **Create or update the TTL index:** use `createIndex` or `collMod` as appropriate.
6. **Monitor backlog and performance:** `metrics.ttl`, replication lag, and write/query latency.
7. **Post-deployment follow-up:** do not treat `createIndex` succeeding as meaning old data is already gone.

### 18.3. Example Batched Historical Cleanup

A `mongosh` script illustrating how to **select a small batch of `_id`s** and delete them; use in a controlled environment:

~~~javascript
const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
const batchSize = 200;

const ids = db.application_logs
  .find(
    { createdAt: { $lt: cutoff } },
    { _id: 1 }
  )
  .limit(batchSize)
  .toArray()
  .map(d => d._id);

if (ids.length > 0) {
  const result = db.application_logs.deleteMany({
    _id: { $in: ids },
    createdAt: { $lt: cutoff }
  });
  printjson(result);
}
~~~

This script deletes **at most 200 selected documents per run** and stops without looping infinitely. Subsequent runs should be **coordinated, rate-limited, and observed via metrics**. On very large collections, choose keys, indexes, and batch strategies carefully; **deleteMany** has no native **limit** option, so bound each batch by fetching IDs first.

### 18.4. Disk Space Behavior After Deletes

MongoDB/WiredTiger can reuse freed space internally rather than **immediately returning physical file space to the filesystem**. Therefore, deleting 100 GB of data does not mean OS-reported free disk space increases by 100 GB right away.

Operations like **compact** have specific prerequisites and operational impacts; consult your server version documentation and plan carefully. Never run `compact` or rebuilds impulsively just because OS disk usage metrics do not drop immediately.

## 19. Choosing Between TTL, Explicit Deletion Jobs, and Archiving

| Requirement | TTL Index | Explicit Deletion Job | Archive / Backup |
|---|---|---|---|
| Purge data after a relative/absolute deadline | Suitable; eventual cleanup. | Suitable if richer conditions are needed. | Does not replace hot-data cleanup. |
| Delete at exact second-level timing | **Not guaranteed.** | Requires careful timing/load design; still has real-world lag. | Not meant for immediate deletion. |
| Delete based on multiple fields/complex rules | Limited; TTL is single-field. | More flexible. | Can classify data prior to storage. |
| Archive before deleting | TTL does not archive. | Job can archive then delete. | Part of the workflow. |
| Per-document varying deadlines | Use **expiresAt + 0**. | Can use custom queries. | Policy-dependent. |
| Guarantee token invalidation at exact deadline | **No.** | Business queries must check deadline. | Unrelated. |
| Long-term time series retention | Supported per bucket/time series. | Can apply specialized workflows. | Consider when historical data is needed. |

TTL shines when **expired data can be removed asynchronously** and deletion criteria depend solely on time. When you must enforce business state, preserve history, synchronize across systems, or perform event-driven deletions, pair it with dedicated workflows.

## 20. Common Mistakes

### 20.1. Expecting a Token to Disappear Exactly at `expiresAt`

**Wrong:** "The document is still in the collection, so the token is still valid."

**Right:** check **expiresAt > now** in authentication logic; TTL only cleans up afterward.

### 20.2. Using `expireAfterSeconds = 0` to Disable TTL

**Wrong:** 0 means never expire.

**Right:** 0 means the deadline equals the BSON Date stored in the field. To disable deletion, change the design/index/config appropriately—never set TTL to 0.

### 20.3. Storing Timestamps as Strings

**Wrong:** **"2026-01-01T10:00:00Z"** is automatically treated as a Date by TTL.

**Right:** store a BSON Date, such as **ISODate(...)** in `mongosh` or `Date`/`Instant` via an appropriate converter.

### 20.4. Trying to Create a Compound TTL by Tenant

**Wrong intent:** **createIndex({tenantId:1,expiresAt:1}, {expireAfterSeconds:0})**.

**Right:** single-field TTL on `expiresAt`; create a separate compound index to serve tenant-scoped queries if needed.

### 20.5. Putting TTL on the Users Collection to Expire OTPs

**Wrong:** TTL on **resetCodeExpiresAt** in the `users` document will only delete the reset code.

**Right:** TTL deletes **the entire document**, so store OTPs/tokens in a dedicated collection or use a different field-cleanup mechanism.

### 20.6. Forgetting to Check Documents Without the TTL Field

**Wrong:** every document expires automatically even if `expiresAt` is missing.

**Right:** documents missing the Date field can live indefinitely. Use validation and monitoring.

### 20.7. Date Arrays with Multiple Deadlines

**Wrong:** TTL picks the latest date in the array.

**Right:** TTL picks the **earliest eligible date** to calculate expiration.

### 20.8. Shortening TTL from 30 Days to 1 Day During Peak Hours

**Wrong:** it's only changing one index option, so impact is minimal.

**Right:** millions of documents can immediately become eligible for deletion; plan batched cleanup and monitor load.

### 20.9. Hiding a TTL Index to Pause Deletion

**Wrong:** `hideIndex` makes the server stop cleaning up.

**Right:** a hidden TTL index **keeps deleting**; hiding only affects the query planner.

### 20.10. Believing Secondaries Delete Independently on Schedule

**Wrong:** every replica set member runs independent TTL cleanup.

**Right:** primary generates deletes and secondaries replicate them; read lag can still expose expired documents.

### 20.11. Reading `metrics.ttl.deletedDocuments` as an Instantaneous Rate

**Wrong:** `deletedDocuments = 200000` means 200,000 documents/second.

**Right:** it is a cumulative counter; take deltas over time and handle resets.

### 20.12. Using TTL as Backup or Archive

**Wrong:** TTL saves old data elsewhere before deleting.

**Right:** TTL only deletes; archiving requires a separate pipeline before retention removes data.

## 21. Hands-On Self-Check Exercises

### Exercise 1 — Creating a 90-Second TTL

Create a **short_lived** collection in the lab database with a TTL index **{createdAt:1}** and **expireAfterSeconds:90**:

~~~javascript
use ttl_index_lab

db.short_lived.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 90, name: "ttl_short_lived_90s" }
);
~~~

Insert one fresh document and one document with `createdAt` 10 minutes in the past:

~~~javascript
db.short_lived.insertMany([
  {
    _id: "NEW",
    createdAt: new Date(),
    description: "Should live about 90 seconds or longer"
  },
  {
    _id: "OLD",
    createdAt: new Date(Date.now() - 10 * 60 * 1000),
    description: "Already eligible for deletion"
  }
]);
~~~

Observe **db.short_lived.find()** at different intervals. The goal is to see that **OLD is immediately eligible for deletion yet not guaranteed to vanish instantaneously**, while NEW becomes eligible after 90 seconds plus potential background lag.

### Exercise 2 — Absolute Expiration Index

Configure TTL **expireAfterSeconds:0** on **expiresAt** for the **one_time_codes** collection. Create two documents with `expiresAt` set to 2 minutes and 15 minutes from creation. Explain why a single TTL index handles both deadlines.

### Exercise 3 — Wrong BSON Type

Insert into the TTL-enabled collection:

~~~javascript
db.short_lived.insertOne({
  _id: "STRING_DATE",
  createdAt: new Date().toISOString(),
  description: "Wrong BSON type"
});
~~~

Query with **$type** to confirm `createdAt` is a string and explain why its survival past expiration is not a TTL monitor bug.

### Exercise 4 — Inspecting Backlog

Read:

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Count documents with **createdAt <= now - 90 seconds** in the lab collection and compare with TTL metrics. Why does a single reading of **deletedDocuments** not tell you how many records were deleted over a short window?

### Exercise 5 — Changing Retention Duration

Describe a plan to shorten a log collection's TTL from **30 days to 7 days** when millions of old documents exist. Write the **collMod** command to run, after explaining the data-check, batched cleanup, replication lag, and rollback steps.

### Exercise 6 — Protecting a Login Endpoint

Given session document:

~~~javascript
{
  sessionId: "S-001",
  userId: "U-01",
  status: "ACTIVE",
  expiresAt: ISODate("2026-01-01T10:10:00Z")
}
~~~

At 10:10:01 UTC, the document is still in MongoDB. Should the API accept or reject it? Write the query with **expiresAt > now** and explain why the TTL monitor is not an access-control layer.

### Exercise 7 — Time Series TTL

A time series bucket holds measurements from 10:00 to 10:40, with a 1-hour TTL. Why might the 10:00 measurement still exist after 11:00? Distinguish **bucket expiration** from **monitor cleanup delay**.

### Exercise 8 — When Business Rules Require Archiving

A system must keep hot logs for 7 days while retaining audit data in an archive for 3 years. Propose a pipeline:

~~~text
New event -> Hot MongoDB collection
                         |
                         v
                  Archive pipeline
                         |
                         v
                  Durable archive
                         |
                         v
                TTL cleanup hot data
~~~

List the checks needed to prevent data loss if TTL deletes hot records before archiving completes.

## 22. Review Questions

1. What feature distinguishes a TTL index from a regular single-field index?
2. What does **expireAfterSeconds:3600** on `createdAt` mean?
3. How does **expireAfterSeconds:0** on `expiresAt` differ from using 0 to "disable" TTL?
4. Why can an expired token still be returned by **findOne**?
5. Can background deletion latency exceed 60 seconds? Why?
6. Are documents missing the TTL field or storing timestamps as strings deleted by TTL?
7. When a TTL field is an array of BSON Dates, does MongoDB use the earliest or latest date?
8. Can a TTL index be created on a compound key **{tenantId:1,expiresAt:1}**?
9. Can **hideIndex** be used to pause TTL deletion?
10. Why can shortening TTL on a large collection cause a sudden deletion spike?
11. Which command modifies `expireAfterSeconds` on an existing TTL index?
12. What do **metrics.ttl.passes** and **subPasses** help observe?
13. How does TTL deletion work across primary and secondaries in a replica set?
14. Why can a time series bucket remain after the earliest measurement's expiration time?
15. In Java/Spring Data, what should you verify to be sure `expiresAt` is stored as a BSON Date?
16. If TTL deletes a user document just because a reset code expired, where is the mistake?

## 23. Summary

A TTL index is a useful tool for automatically cleaning up documents when **retention can be expressed via a Date value**. However, you must distinguish **three points in time**:

~~~text
1. Time the data is created
           |
           v
2. Time the data expires
     = Date + expireAfterSeconds
     or = expiresAt when expireAfterSeconds:0
           |
           | Application must explicitly reject expired data
           v
3. Time the TTL monitor actually deletes the document
     = asynchronous, may lag > 60 seconds under heavy load
~~~

**Core principles:**

1. Standard TTL indexes are **single-field indexes containing a BSON Date**; compound TTL and TTL on `_id` are not supported.
2. **expireAfterSeconds** specifies seconds past the document's Date; **0** is used when the Date itself is the deletion deadline.
3. TTL **deletes the entire document**, not just one field.
4. **The TTL monitor runs asynchronously** and does not guarantee immediate deletion at expiration; applications must check deadlines explicitly when serving data.
5. **Mistyped/missing fields do not expire automatically**, so schema validation and legacy data migration are necessary.
6. **Arrays of Dates** use the **earliest** timestamp to determine the TTL threshold.
7. **Hidden TTL indexes still delete**, and changing TTL on an existing index requires **collMod** as documented.
8. **Shortening TTL can trigger a massive deletion backlog**; plan batched cleanup and monitor load.
9. **Replica set primaries execute TTL deletion** while secondaries replicate deletes; time series collections have additional bucket-level deletion rules.
10. TTL is one part of the **data lifecycle**, not a substitute for authorization logic, immediate deletion, backups, or archiving.

### Official Documentation

- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — configuration, limitations, background deletion, passes/sub-passes, and replication.
- [Expire Data from Collections](https://www.mongodb.com/docs/manual/tutorial/expire-data/) — TTL with relative durations and absolute timestamps.
- [collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — modifying `expireAfterSeconds` on an index.
- [Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/) — `ttlMonitorEnabled` and `mongod` parameters.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hidden TTL indexes still perform expiration.
- [Time Series Automatic Removal](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — retention and bucket-based removal.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — `createIndex`/`IndexOptions` and BSON Date mapping.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — `@Indexed`, `IndexOperations`, and conversions.

When deploying TTL in a real system, check the documentation for your **current MongoDB/driver version**, verify the BSON type of the timestamp field, inspect overdue data volume, and review topology. Design TTL as **end-of-lifecycle cleanup**, while having business logic explicitly verify whether a record **is valid for use right now**.
