# Batched, Checkpointed, and Re-runnable Backfills for Missing Data

Backfilling is the process of iterating through existing documents to populate a missing field, recalculate values, or normalize data structures to meet new requirements. With Spring Data MongoDB, you can implement a backfill using **MongoTemplate**, leveraging key-based queries, conditional updates, and a separate collection to store **checkpoints** (safely processed positions).

The difficulty lies not in updating a single document, but in ensuring the task remains correct when there are millions of documents, the application stops midway, data changes while running, or the same batch must be executed again.

## 1. Objectives and Real-World Scenario

After this lesson, you will be able to:

- Precisely identify the data needing backfill and define verifiable population rules.
- Iterate through data in **bounded-size batches** using keyset pagination instead of large-skip pagination.
- Save the checkpoint **only after all updates in the batch have completed**, and resume from the checkpoint on restart.
- Design **idempotent** updates: re-running does not overwrite values created by the application or a previous run.
- Test failure scenarios, monitor progress, and evaluate query impact on MongoDB.

**Example:** the **users** collection currently has the **emailOptIn** field (boolean) but does not yet have **preferences.notificationChannel**. Confirmed business rules:

| Source data | Value to populate |
| --- | --- |
| emailOptIn = true | preferences.notificationChannel = "EMAIL" |
| emailOptIn = false | preferences.notificationChannel = "NONE" |
| emailOptIn missing or null | Stop and flag the document for inspection; never guess |
| notificationChannel already exists | Preserve it, even if different from the default value |

A document before and after backfill:

~~~json
// Before
{
  "_id": {"$oid": "671000000000000000000001"},
  "emailOptIn": true,
  "preferences": {"language": "vi"}
}

// After
{
  "_id": {"$oid": "671000000000000000000001"},
  "emailOptIn": true,
  "preferences": {
    "language": "vi",
    "notificationChannel": "EMAIL"
  }
}
~~~

The example assumes users' **_id** is **ObjectId**, **emailOptIn** is present and does not change during execution, and **preferences** is either an object or does not exist yet. If real data has **preferences: null**, a string, or an array, handle anomalous data before applying nested-field updates. If source **emailOptIn** can change concurrently, recalculate the value using an aggregation update pipeline on the document at write time or schedule a final reconciliation pass.

## 2. Identifying the Dataset and Safety Invariants

Before writing Java code, measure the number of documents missing the target field and inspect sample records:

~~~javascript
db.users.countDocuments({
  "preferences.notificationChannel": { $exists: false }
});

db.users.find(
  { "preferences.notificationChannel": { $exists: false } },
  { _id: 1, emailOptIn: 1, preferences: 1 }
).limit(5);

db.users.countDocuments({ emailOptIn: { $exists: false } });
db.users.countDocuments({ emailOptIn: { $type: "null" } });
db.users.countDocuments({ preferences: { $type: "null" } });
~~~

**Distinguish missing fields from null fields:** the **$exists: false** condition only selects documents missing the field path; it does not select documents that already have the field set to null. If the business wants to process null as well, intentionally expand both the filter and the transformation rules. Never assume null means missing, as null can be a valid state.

Invariants to maintain:

1. **Populate only missing fields.** Every write must re-verify the missing-field condition, even though the read query already filtered for it.
2. **Save checkpoint only after a batch succeeds.** If any document fails, do not advance the checkpoint past that batch.
3. **Allow batch retries.** A crash between writing data and saving the checkpoint may cause the batch to re-run; the final result must still be correct.
4. **Stable traversal order.** Sort ascending by **_id** and fetch only **_id**s greater than the checkpoint; do not use skip/limit to jump over already-modified documents.
5. **Bound the scope of a run.** Record **upperBoundId** on the first run and process only documents whose _id does not exceed this bound. This bound fixes the key range; it does not create a transactional snapshot of the entire collection.

A checkpoint looks like:

~~~json
{
  "_id": "users_notification_channel_v1",
  "state": "RUNNING",
  "upperBoundId": {"$oid": "671fffffffffffffffffffff"},
  "lastSeenId": {"$oid": "671000000000000000000500"},
  "createdAt": {"$date": "2026-11-20T00:00:00Z"},
  "updatedAt": {"$date": "2026-11-20T00:02:00Z"}
}
~~~

**lastSeenId** marks the last _id of the **completed batch**, not the last document merely read. The **DONE** state indicates the entire dataset within the run's _id bounds has been scanned; to backfill data created afterward, create a new run with a new job ID or design a separate reconciliation mechanism.

## 3. Designing the Backfill Flow

~~~mermaid
flowchart TD
    A["Start job"] --> B["Read or create checkpoint"]
    B --> C{"Checkpoint DONE?"}
    C -- Yes --> Z["Finish"]
    C -- No --> D["Find up to N documents missing field, _id > lastSeenId"]
    D --> E{"Batch empty?"}
    E -- Yes --> F["Mark DONE"] --> Z
    E -- No --> G["Compute value and conditionally update each document"]
    G --> H{"Entire batch succeeded?"}
    H -- No --> I["Log error, stop; keep checkpoint"] 
    H -- Yes --> J["Save batch last _id to checkpoint"]
    J --> D
~~~

**Why use keyset pagination?** Once a document gets the field populated, it no longer matches the **$exists: false** condition. If you use **skip(500)** to fetch the next page, the earlier documents have disappeared from the result set and skipping 500 elements can skip over unprocessed records. Furthermore, large skips force MongoDB to scan many unused results. Traversing by **_id > lastSeenId** avoids depending on the relative position of documents.

## 4. Implementing with Spring Data MongoDB

The snippet below illustrates a sequential job using **MongoTemplate**, which can be invoked from an operational tool or an intentionally enabled **ApplicationRunner**. Never run resource-intensive migrations by default on every instance at application startup.

~~~java
package example.migration;

import java.time.Instant;
import java.util.List;

import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class NotificationChannelBackfill {
    private static final String USERS = "users";
    private static final String CHECKPOINTS = "migration_checkpoints";
    private static final String JOB_ID = "users_notification_channel_v1";
    private static final String TARGET = "preferences.notificationChannel";
    private static final int BATCH_SIZE = 500;

    private final MongoTemplate mongo;

    public NotificationChannelBackfill(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void run() {
        // Upper bound captured when the job is first created.
        ObjectId upperBoundCandidate = findCurrentMaxId();
        if (upperBoundCandidate == null) {
            markEmptyCollectionDone();
            return;
        }

        Query checkpointKey = Query.query(Criteria.where("_id").is(JOB_ID));
        mongo.upsert(
            checkpointKey,
            new Update()
                .setOnInsert("state", "RUNNING")
                .setOnInsert("upperBoundId", upperBoundCandidate)
                .setOnInsert("createdAt", Instant.now()),
            CHECKPOINTS
        );

        Document checkpoint = mongo.findById(
            JOB_ID, Document.class, CHECKPOINTS
        );
        if (checkpoint == null) {
            throw new IllegalStateException("Cannot read migration checkpoint");
        }
        if ("DONE".equals(checkpoint.getString("state"))) {
            return;
        }
        if (!"RUNNING".equals(checkpoint.getString("state"))) {
            throw new IllegalStateException("Unexpected checkpoint state");
        }

        ObjectId upperBound = checkpoint.getObjectId("upperBoundId");
        ObjectId lastSeenId = checkpoint.getObjectId("lastSeenId");
        if (upperBound == null) {
            throw new IllegalStateException("Checkpoint has no upperBoundId");
        }

        while (true) {
            Criteria idRange = lastSeenId == null
                ? Criteria.where("_id").lte(upperBound)
                : Criteria.where("_id").gt(lastSeenId).lte(upperBound);

            Query batchQuery = Query.query(new Criteria().andOperator(
                    idRange,
                    Criteria.where(TARGET).exists(false)
                ))
                .with(Sort.by(Sort.Direction.ASC, "_id"))
                .limit(BATCH_SIZE);
            batchQuery.fields().include("_id").include("emailOptIn");

            List<Document> users = mongo.find(
                batchQuery, Document.class, USERS
            );
            if (users.isEmpty()) {
                // Guard checkpoint to avoid overwriting another instance's progress.
                UpdateResult done = mongo.updateFirst(
                    checkpointGuard(lastSeenId),
                    new Update()
                        .set("state", "DONE")
                        .set("finishedAt", Instant.now()),
                    CHECKPOINTS
                );
                requireSingleMatch(done);
                return;
            }

            for (Document user : users) {
                ObjectId id = user.getObjectId("_id");
                Boolean emailOptIn = user.getBoolean("emailOptIn");
                if (id == null || emailOptIn == null) {
                    // Do not swallow errors and advance the checkpoint past this document.
                    throw new IllegalStateException(
                        "Invalid source data for user " + id
                    );
                }

                String channel = emailOptIn ? "EMAIL" : "NONE";
                Query onlyMissing = Query.query(
                    Criteria.where("_id").is(id)
                        .and(TARGET).exists(false)
                );

                // A field just written by another thread will not be overwritten.
                mongo.updateFirst(
                    onlyMissing,
                    new Update().set(TARGET, channel),
                    USERS
                );
            }

            ObjectId batchLastId =
                users.get(users.size() - 1).getObjectId("_id");

            // Advance checkpoint only after all updates above succeed.
            UpdateResult saved = mongo.updateFirst(
                checkpointGuard(lastSeenId),
                new Update()
                    .set("lastSeenId", batchLastId)
                    .set("updatedAt", Instant.now()),
                CHECKPOINTS
            );
            requireSingleMatch(saved);
            lastSeenId = batchLastId;
        }
    }

    private Query checkpointGuard(ObjectId expectedLastSeenId) {
        return Query.query(
            Criteria.where("_id").is(JOB_ID)
                .and("state").is("RUNNING")
                .and("lastSeenId").is(expectedLastSeenId)
        );
    }

    private void requireSingleMatch(UpdateResult result) {
        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Checkpoint changed concurrently; stop and retry job"
            );
        }
    }

    private ObjectId findCurrentMaxId() {
        Query query = new Query()
            .with(Sort.by(Sort.Direction.DESC, "_id"))
            .limit(1);
        query.fields().include("_id");
        Document latest = mongo.findOne(query, Document.class, USERS);
        return latest == null ? null : latest.getObjectId("_id");
    }

    private void markEmptyCollectionDone() {
        Query key = Query.query(Criteria.where("_id").is(JOB_ID));
        mongo.upsert(
            key,
            new Update()
                .setOnInsert("state", "DONE")
                .setOnInsert("finishedAt", Instant.now()),
            CHECKPOINTS
        );
        Document checkpoint = mongo.findById(
            JOB_ID, Document.class, CHECKPOINTS
        );
        if (checkpoint == null) {
            throw new IllegalStateException("Cannot read migration checkpoint");
        }
        if ("DONE".equals(checkpoint.getString("state"))) {
            return;
        }
        // Case where the collection was emptied after the job had already started.
        if (!"RUNNING".equals(checkpoint.getString("state"))) {
            throw new IllegalStateException("Unexpected checkpoint state");
        }
        requireSingleMatch(mongo.updateFirst(
            checkpointGuard(checkpoint.getObjectId("lastSeenId")),
            new Update()
                .set("state", "DONE")
                .set("finishedAt", Instant.now()),
            CHECKPOINTS
        ));
    }
}
~~~

In this example, **setOnInsert** initializes the checkpoint only if the job does not exist yet; restarts read back the stored **upperBoundId** and **lastSeenId**. Checkpoint updates use a compare-previous-value condition (**compare-and-set**): if another instance modified the checkpoint, the current job stops instead of moving the cursor backward.

The code updates each document with **updateFirst** for easy observability and error handling. For high throughput, you can use **BulkOperations** per batch to reduce round trips, but only save the checkpoint once the entire bulk operation is confirmed successful. If a bulk write partially fails, keep the checkpoint unchanged and re-run the batch with conditional updates. Checkpoint reliability depends on write acknowledgement; for critical tasks, configure an appropriate **write concern**, typically **majority**, for both data and checkpoints.

Note: the write filter in the example protects the target field, but assumes the source **emailOptIn** remains stable during the backfill. If the source can change, use a pipeline update that computes the value from current data in the same atomic write, or run a reconciliation pass afterward. An _id scan is also not a true snapshot: late-inserted documents with an _id smaller than the cursor may not appear in this run.

## 5. Idempotency and Checkpoint Semantics

Suppose a batch has 500 documents:

| Failure point | Actual data | On re-run |
| --- | --- | --- |
| Before writing any document | Unchanged | Re-reads the same batch |
| After writing 300/500 documents | 300 documents have the new field, checkpoint unchanged | Re-reads batch; documents that already have the field are not overwritten |
| After writing 500/500, before saving checkpoint | Entire batch has been populated | Re-reads; documents no longer match the missing-field filter |
| After checkpoint is saved | Cursor advances to batch's last _id | Continues from higher _id |
| Another instance updated checkpoint | Potential schedule conflict | Compare-and-set fails; stops and re-reads state |

Document writes and checkpoint writes **are not in a shared transaction** in this example. Therefore, the accurate model is **at-least-once processing** combined with idempotent updates to reach the desired end state. Do not expect strictly-once execution in an absolute sense.

Never automatically skip failed documents and advance the checkpoint, as doing so can permanently omit data. If individual errors must be tolerated, use an explicit error/dead-letter queue, recording the reason, retry rules, and per-_id reconciliation.

## 6. Indexes, Resource Limits, and Performance

**_id** has a default index, making it well-suited for range conditions and sorting. However, filtering for missing fields with **$exists: false** may require scanning many documents to locate records needing updates. A sparse index does not automatically optimize queries looking for a **non-existent** field.

Before running on large datasets, inspect the execution plan:

~~~javascript
db.users.find({
  _id: {
    $gt: ObjectId("671000000000000000000000"),
    $lte: ObjectId("671fffffffffffffffffffff")
  },
  "preferences.notificationChannel": { $exists: false }
}).sort({ _id: 1 }).limit(500).explain("executionStats");
~~~

Examine **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. Reading far more documents than returned indicates that scanning for missing fields consumes significant I/O. For very large datasets, you can prepare a dedicated flag/queue for documents needing migration and an index tailored to that flag; benchmark this approach before adopting it.

Safe operations require attention to:

- Start with small batches (e.g., 100–500) and scale up gradually after measuring duration, CPU, I/O, replication lag, and impact on user queries.
- Project only the fields needed to compute values; bound in-memory documents per batch and use **_id** as the cursor.
- Run a single coordinated job. Compare-and-set protects the checkpoint, but does not fully replace job ownership/leasing when multiple instances may start.
- Avoid logging personal data; prefer logging job ID, _id range, scanned count, updated count, error count, and batch duration.
- Support pausing/throttling when production load increases. Consider **maxTimeMS** on queries and backoff retries for transient errors; never infinitely retry data errors.

If using **ReactiveMongoTemplate**, apply the same principles: read in bounded batches, process sequentially using **concatMap** or concurrency-bounded streams, and wait for the data write publisher to complete before writing the checkpoint. Never place checkpointing in a reactive branch that could complete before update branches finish.

## 7. Transactions, Multiple Workers, and Concurrent Data Changes

MongoDB guarantees atomicity for updates on a **single document**. When multiple documents and the checkpoint must be grouped into a single transactional unit, Spring Data MongoDB can use **MongoTransactionManager**, but MongoDB transactions require a compatible topology (replica set or sharded cluster) and long-running transactions over large sets incur high overhead. In practice, backfilling millions of documents is usually better served by small batches, idempotent updates, and durable checkpoints.

To scale across multiple workers, do not let them all share a single **lastSeenId** without partitioning the data. You can split into non-overlapping _id ranges, each with its own checkpoint, or use a queue with leases and ownership conditions. Each worker must have a clear update boundary, expired-lease recovery, and write conditions that prevent overwriting newer changes.

For live data receiving direct writes, follow **expand–migrate–contract**: the new application supports both old and new documents; start writing the new field for all new documents; run the backfill; reconcile; and only then require the field in read logic and validation. Never change read code to assume all documents have the field before the job is verified complete.

## 8. Testing and Reconciling Results

Integration tests to write using **@DataMongoTest** and a test MongoDB instance (such as Testcontainers):

| Scenario | Expected result |
| --- | --- |
| Document missing field, emailOptIn = true/false | New field populated per rules |
| Document already has notificationChannel = "PUSH" | Value "PUSH" preserved |
| Invalid emailOptIn or mistyped preferences | Job errors out, checkpoint does not pass the bad document |
| Stop after a few updates in a batch, then re-run | Batch completes, existing data is not overwritten |
| Second run with checkpoint DONE | Exits safely without modifying documents |
| Two concurrent runs saving the same checkpoint | One compare-and-set fails, checkpoint is not rolled back |
| Document added after job starts | Understand upperBoundId limit and follow-up run handling |

After the job reports DONE, reconcile the data within the run's bounds:

~~~javascript
const checkpoint = db.migration_checkpoints.findOne({
  _id: "users_notification_channel_v1"
});

db.users.countDocuments({
  _id: { $lte: checkpoint.upperBoundId },
  "preferences.notificationChannel": { $exists: false }
});

db.users.countDocuments({
  _id: { $lte: checkpoint.upperBoundId },
  emailOptIn: true,
  "preferences.notificationChannel": "EMAIL"
});
~~~

The ideal missing-field count within the managed scope is **0**, assuming valid source data and no concurrent writes reintroducing gaps. Compare counts and inspect random samples against business rules; **DONE** only confirms the scan loop finished, not that data is accurate if source rules were wrong or data changed after scanning.

For rollback, avoid running a blanket delete of the new field: the application may have already written valid values after the backfill. If undo capability is required, design ahead of time a way to identify only documents modified by the job (such as audit logs or a migration marker with safe update conditions), and test recovery on a data copy.

## 9. Pre-Operation Checklist

1. Computation rules for the new field have been confirmed by the data owner; nulls and anomalous records have been addressed.
2. Job has a unique ID, explicit _id bounds, configurable batch size, and durable checkpoints.
3. Updates use document-level guards; re-running does not overwrite application-created values.
4. Crash scenarios before/after checkpoints and duplicate launches have been tested; baseline metrics exist for reconciliation.
5. Query plan, write load, and replication lag have been measured on a realistic sample; pause and resume mechanisms exist.
6. The application continues to read both old and new schemas until migration and reconciliation complete.

The **desired outcome** of a safe backfill is not merely filling in fields: the system continues serving traffic normally, mid-run failures can resume from checkpoints, and the same batch can be re-run without corrupting data.
