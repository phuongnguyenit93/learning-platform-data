# Verifying Counts, Data Types, and Consistency After Migration

## 1. Why Does a Completed Migration Not Automatically Mean the Data Is Correct?

In the **SPRING_DATA_MONGODB** module, we use Spring Data MongoDB to connect, map documents, and work with MongoDB through `MongoTemplate` or repositories. Across query design, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics, a recurring need is changing how data is stored without breaking business correctness. The **Data Migration** chapter focuses on that challenge.

Consider an e-commerce application migrating from an old collection to a new MongoDB schema. The migration tool may report processing 100,000 documents, yet it is still possible that:

- Only 99,998 documents were written successfully; two documents were skipped due to bad data.
- The monetary field was stored as BSON double instead of Decimal128, risking arithmetic precision drift.
- The date field was stored as a string or shifted in timezone.
- A document's status changed from PAID to PENDING during mapping.
- An ID was assigned to the wrong customer, even though total document counts match.
- The new collection has all records, yet some reference deleted customers.

Therefore, **post-migration verification** must answer three independent questions:

1. **Is it complete?** Every in-scope source document has a corresponding target record, with no unexpected extra records and no duplicate business keys.
2. **Are the types right?** Values actually have the intended BSON types and schema shape, including missing or null fields.
3. **Is business meaning intact?** IDs, monetary amounts, timestamps, statuses, references, and business invariants remain preserved after transformation.

Matching counts is only a **necessary condition**, never sufficient on its own to declare a migration safe. This lesson builds a repeatable verification workflow that yields concrete evidence to decide whether application traffic can cut over to the new schema.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Define source/target datasets and acceptance criteria prior to comparison.
2. Use countDocuments, aggregations, and key lookups to verify counts and coverage.
3. Use the $type operator to detect wrong BSON types, nulls, and missing fields.
4. Compare normalized post-conversion fields: Decimal128, dates, enums, IDs, and reference integrity.
5. Perform checks via mongosh and Spring Data MongoDB while understanding the limits of sample-based checks.
6. Produce a reconciliation report, handle discrepancies, and re-verify under concurrent writes.

## 2. Running Example: Order Migration

Suppose the application stores data in a single MongoDB database and migrates from collection **orders_legacy** to **orders_v2**. The approved transformation rules are:

| Source field | Target field | Rule |
| --- | --- | --- |
| _id: ObjectId | _id: ObjectId | Preserve ID for per-document reconciliation. |
| totalCents: string | amount: Decimal128 | Parse string as integer cents, divide accurately by 100. |
| createdAt: ISO-8601 string UTC | createdAt: BSON Date | Parse as UTC without shifting the actual instant. |
| customerId: string | customerId: string | Preserve customer identifier. |
| status: string | status: string | Preserve valid status. |

Example source document:

~~~javascript
// orders_legacy
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  totalCents: "125000",
  createdAt: "2026-10-01T10:15:30Z",
  customerId: "C001",
  status: "PAID"
}
~~~

Expected target result:

~~~javascript
// orders_v2
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  amount: NumberDecimal("1250.00"),
  createdAt: ISODate("2026-10-01T10:15:30Z"),
  customerId: "C001",
  status: "PAID"
}
~~~

In this example:

- Each source document must have exactly **one** target document with the same _id.
- All orders in orders_legacy are in scope; orders_v2 contains only documents from the migration under verification.
- Source timestamps are ISO-8601 with explicit timezone designators; source amounts are valid integer strings.
- The customers collection has _id matching the order's customerId.

These are **exercise assumptions**. In systems with excluded data, multiple migration waves, or newly generated IDs, explicitly document eligibility filters, migrationBatchId, and ID mapping tables before running comparisons. Never assume the entire source and target collections belong to the same migration run.

Verification workflow:

~~~mermaid
flowchart TD
    A[Lock scope and transformation rules] --> B[Verify counts]
    B --> C[Verify ID coverage]
    C --> D[Verify BSON types]
    D --> E[Reconcile values and references]
    E --> F[Verify under concurrent writes]
    F --> G{All criteria pass?}
    G -->|Yes| H[Approve cutover]
    G -->|No| I[Record discrepancies and root cause]
    I --> J[Fix migration or data per process]
    J --> B
~~~

## 3. Count Reconciliation: More Than Whole-Collection Counts

### 3.1. Exact Counts Within the Defined Scope

Run in mongosh:

~~~javascript
const sourceCount = db.orders_legacy.countDocuments({});
const targetCount = db.orders_v2.countDocuments({});

printjson({
  sourceCount,
  targetCount,
  missingByCount: sourceCount - targetCount
});
~~~

**countDocuments(filter)** counts documents matching the filter. **estimatedDocumentCount()** estimates from collection metadata—suitable for quick approximations, but **unsuitable as primary evidence for migration acceptance**.

Expected result under the lesson's assumptions:

~~~text
sourceCount = 100000
targetCount = 100000
missingByCount = 0
~~~

If the migration includes only orders with specific statuses, both counts must share the **exact same eligibility definition**, whether via status filters, batch IDs, or manifest IDs. For example, if target has migrationBatchId:

~~~javascript
db.orders_v2.countDocuments({
  migrationBatchId: "batch-2026-11"
});
~~~

Never compare a filtered source count against the **entire** target if target already holds records from another wave. Likewise, equal totals are insufficient: one missing document and one extra document still balance the total count.

### 3.2. Checking Distribution by Status

Count each status group to uncover discrepancies masked by totals:

~~~javascript
db.orders_legacy.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);

db.orders_v2.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Compare both **group keys** and **counts** between the two results. For instance, both totals could be 100,000 while 20 PAID orders turned into PENDING—a total count comparison misses this, whereas grouping by status catches it.

You can extend grouping by date, tenant, region, or source channel as long as post-conversion grouping rules match source rules. When dates shift from string to BSON Date, normalize to the same timezone before grouping.

### 3.3. Checking That Source IDs Exist in Target

Since both collections live in the **same database** in this example, use $lookup to find source IDs lacking a target match:

~~~javascript
db.orders_legacy.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "_id",
      as: "targetMatches"
    }
  },
  {
    $match: {
      "targetMatches.0": { $exists: false }
    }
  },
  { $project: { _id: 1 } },
  { $limit: 20 }
]);
~~~

Any returned document represents a source ID missing from target. Check the reverse direction to catch out-of-scope target records:

~~~javascript
db.orders_v2.aggregate([
  {
    $lookup: {
      from: "orders_legacy",
      localField: "_id",
      foreignField: "_id",
      as: "sourceMatches"
    }
  },
  {
    $match: {
      "sourceMatches.0": { $exists: false }
    }
  },
  { $project: { _id: 1 } },
  { $limit: 20 }
]);
~~~

Note: both queries return at most 20 **sample discrepancies**, not the total discrepancy count. To sign off, replace $limit with **$count** or record results across full partitions and confirm zero discrepancies. For large datasets, shard by _id range or tenant and checkpoint progress. Looking up _id uses the default index, though $lookup can still be resource-intensive on very large collections.

If the migration generates new _ids, preserve **legacyId** or a unique sourceId → targetId mapping table to execute both checks. Total counts alone do not prove a one-to-one mapping.

## 4. Verifying BSON Types and Document Shape

### 4.1. Why Java Types Do Not Prove BSON Types

Spring Data MongoDB can coerce values when reading documents into POJOs or records. A BSON string or double may still deserialize into a BigDecimal or target Java type. Consequently, a repository test returning a readable object **does not prove** data in the database has the intended storage type.

For our example:

- amount must be BSON **decimal** (Decimal128), not double, string, or int.
- createdAt must be BSON **date**, not string.
- customerId and status must be BSON **string** and present.
- _id must be **objectId** per the agreed contract.

Inspect actual stored type distributions directly via aggregation:

~~~javascript
db.orders_v2.aggregate([
  {
    $group: {
      _id: {
        amountType: { $type: "$amount" },
        createdAtType: { $type: "$createdAt" },
        customerIdType: { $type: "$customerId" },
        statusType: { $type: "$status" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Expect only a single group:

~~~javascript
{
  _id: {
    amountType: "decimal",
    createdAtType: "date",
    customerIdType: "string",
    statusType: "string"
  },
  count: 100000
}
~~~

The **$type** aggregation operator returns the BSON type name of an expression. When a field is absent, it returns **"missing"**; when null, it returns **"null"**. Both states differ and must be handled if the schema requires the field.

### 4.2. Locating Documents with Invalid Types

~~~javascript
db.orders_v2.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" },
      customerIdType: { $type: "$customerId" },
      statusType: { $type: "$status" }
    }
  },
  {
    $match: {
      $or: [
        { amountType: { $ne: "decimal" } },
        { createdAtType: { $ne: "date" } },
        { customerIdType: { $ne: "string" } },
        { statusType: { $ne: "string" } }
      ]
    }
  },
  { $limit: 20 }
]);
~~~

The returned result must be empty. To get the **total count** of invalid documents, replace $limit with $count as before. You can also check _id by adding **{ $type: "$_id" }** to $project if _id is required to be an ObjectId.

For collections with flexible schemas, do not apply one rigid rule set to every document. When schema versions or document types coexist, **group by version/type** and validate against the matching contract. Optional fields may be legitimately missing, whereas required fields cannot be ignored merely because the app supplies a default during deserialization.

### 4.3. Extra Caution with Money and Timestamps

Error-prone conversions:

| Data | Risky conversion | Verification / design approach |
| --- | --- | --- |
| "125000" cents → currency | Passing through double with implicit rounding | Use BigDecimal/Decimal128 and exact decimal division. |
| Long → int | Value exceeds int range | Detect overflow; standardize on BSON int or long. |
| String timestamps | Parsing with machine default timezone | Standardize offset/UTC and precision; compare instants, not strings. |
| "true"/"false" → boolean | Case-sensitivity mismatch or defaulting to null | Define valid value set; verify actual bool type. |
| String ID → ObjectId | String is not a valid 24-hex-character ID | Check ID format rules, uniqueness, and references. |
| null/missing → default value | Turning missing data into business-meaningful values | Populate defaults only when explicitly specified by migration rules. |

Example converting amount accurately in Java:

~~~java
import java.math.BigDecimal;

public final class MoneyMigration {

    private MoneyMigration() {}

    public static BigDecimal centsToAmount(String totalCents) {
        // Source string must be a valid integer with an explicit error policy.
        return new BigDecimal(totalCents).movePointLeft(2);
    }
}
~~~

In a Spring Data MongoDB entity, you can specify storing BigDecimal as Decimal128:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "orders_v2")
public class OrderV2 {
    @Id
    private ObjectId id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private Instant createdAt;
    private String customerId;
    private String status;
}
~~~

This entity shows the storage-type declaration; it does not replace direct inspection of the persisted BSON. Date mapping can depend on converter configuration, driver/Spring Data versions, and application timezone conventions, so verify actual BSON Date values.

## 5. Verifying Per-Document Consistency

Once ID coverage and types are confirmed, verify **value equivalence according to the transformation rules**. Comparing raw JSON between source and target fails because field names and types changed; instead, normalize source values and compare them against target.

### 5.1. Comparing Amounts, Dates, Customers, and Statuses

When both collections reside in the same database and _id is preserved, you can use this pipeline:

~~~javascript
db.orders_legacy.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "_id",
      as: "target"
    }
  },
  // Documents lacking target were already caught in the coverage check.
  { $unwind: "$target" },
  {
    $set: {
      sourceCentsDecimal: {
        $convert: {
          input: "$totalCents",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      sourceInstant: {
        $dateFromString: {
          dateString: "$createdAt",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      expectedAmount: {
        $divide: ["$sourceCentsDecimal", NumberDecimal("100")]
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $eq: ["$sourceCentsDecimal", null] },
          { $eq: ["$sourceInstant", null] },
          { $ne: ["$expectedAmount", "$target.amount"] },
          { $ne: ["$sourceInstant", "$target.createdAt"] },
          { $ne: ["$customerId", "$target.customerId"] },
          { $ne: ["$status", "$target.status"] }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalCents: 1,
      expectedAmount: 1,
      "target.amount": 1,
      createdAt: 1,
      "target.createdAt": 1,
      customerId: 1,
      "target.customerId": 1,
      status: 1,
      "target.status": 1
    }
  },
  { $limit: 20 }
]);
~~~

How it works:

1. $lookup retrieves the matching target document per source ID; $unwind unwraps the single-element array into an object.
2. $convert parses cents into Decimal128, turning parse failures into null so they are reported instead of aborting the pipeline.
3. $dateFromString normalizes source timestamps into BSON Date.
4. $divide uses a Decimal128 divisor for exact decimal comparison.
5. $match keeps unparseable source records or records where any field differs from target.

The pipeline returns up to **20 mismatched samples** for investigation. For acceptance, count all mismatches instead of stopping at $limit, and confirm the ID coverage check in Section 3 reported 0 missing records. Numeric and date comparisons must follow agreed rounding/precision rules. For example, if source has microsecond precision while BSON Date stores milliseconds, confirm the precision-truncation rule beforehand.

For very large datasets, per-document $lookup reconciliation can incur heavy I/O. Partition by _id range, tenant, or batch, persist per-partition results, and verify total checked partitions. Place partition $match filters as early as possible in the pipeline.

### 5.2. Aggregate Totals Check to Catch Systematic Drift

In addition to per-document checks, compare monetary totals in the **same unit**. Source stores cents so its sum is divided by 100; target stores currency units:

~~~javascript
db.orders_legacy.aggregate([
  {
    $set: {
      cents: {
        $convert: {
          input: "$totalCents",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $group: {
      _id: null,
      invalidRows: {
        $sum: { $cond: [{ $eq: ["$cents", null] }, 1, 0] }
      },
      totalCents: { $sum: "$cents" }
    }
  },
  {
    $project: {
      _id: 0,
      invalidRows: 1,
      expectedAmount: {
        $divide: ["$totalCents", NumberDecimal("100")]
      }
    }
  }
]);

db.orders_v2.aggregate([
  {
    $group: {
      _id: null,
      actualAmount: { $sum: "$amount" }
    }
  },
  { $project: { _id: 0, actualAmount: 1 } }
]);
~~~

The criterion here is **invalidRows = 0** and expectedAmount equal to actualAmount under exact Decimal128 comparison. Never silently accept a monetary tolerance if the migration contract demands exact cent preservation. Note that $sum ignores non-numeric values, so run type checks first and never rely on matching totals as sole proof.

If totals diverge, group further by status, month, or tenant to isolate the affected subset. When source values might exceed Decimal128 range, capture conversion errors before drawing conclusions from totals.

### 5.3. Checking References and Business Constraints

MongoDB does not enforce foreign keys automatically as many relational databases do. Thus, an order document existing does not prove customerId still points to a valid customer.

If customers._id stores string customer IDs like "C001" in the same database:

~~~javascript
db.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { "customer.0": { $exists: false } } },
  { $project: { _id: 1, customerId: 1 } },
  { $limit: 20 }
]);
~~~

Such checks must reflect business reality: a system might permit legacy orders to reference hidden or soft-deleted customers; in that case, define valid states explicitly rather than flagging all of them as errors.

Additional invariants commonly verified:

- **Uniqueness:** _id is always unique within a collection; if a new _id was generated, also check legacyId/orderCode for duplicates and consider a unique index.
- **Attribute preservation:** non-negative totals if business forbids negatives, status within allowed values, creation dates not in the future unless permitted.
- **Cross-field invariants:** e.g., REFUNDED status requires a matching refundAmount; PAID status requires a payment timestamp.
- **Cross-collection relations:** customer, product, paymentId, and invoiceId must resolve to the corresponding records in the right schema version.
- **Arrays and nested objects:** preserve element counts, meaningful ordering, and distinct elements.
- **System metadata:** tenantId, audit fields, version, createdAt/updatedAt, and soft-delete flags are not accidentally dropped.

## 6. Using Spring Data MongoDB in Migration Verification

MongoTemplate lets you write lightweight checks in Java when verification steps belong in test suites or acceptance jobs.

Example verifying counts and a raw BSON type sample:

~~~java
package example.migration;

import java.util.Date;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MigrationVerificationSmokeTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void sourceAndTargetHaveEqualCounts() {
        long source = mongoTemplate.count(
            new Query(), "orders_legacy"
        );
        long target = mongoTemplate.count(
            new Query(), "orders_v2"
        );
        assertEquals(source, target);
    }

    @Test
    void sampleTargetHasExpectedRawBsonTypes() {
        // Read raw Document from driver so Java converters do not mask BSON types.
        Document raw = mongoTemplate.getCollection("orders_v2")
            .find()
            .first();

        assertNotNull(raw, "Target collection must not be empty");
        assertInstanceOf(Decimal128.class, raw.get("amount"));
        assertInstanceOf(Date.class, raw.get("createdAt"));
        assertInstanceOf(String.class, raw.get("customerId"));
        assertInstanceOf(String.class, raw.get("status"));
    }
}
~~~

**This is only a smoke test.** A count test can miss one missing document plus one extra document; inspecting a single document via first() does not prove the entire collection has valid types. For sign-off, use aggregations covering all records, ID-level reconciliation, and per-partition reporting. For large datasets, build a batched reconciliation job tracking checked counts, bounded mismatch IDs, and checkpoints.

If running verification against a production database, use read-only credentials and avoid accidentally calling repository.save/delete or mutating collection commands. Verification routines are designed to be read-only; repairing issues belongs in a separate, safely repeatable migration workflow.

### 6.1. When Comparing from Java

For this lesson's monetary conversion rule, avoid comparing via:

~~~java
// Unsuitable for money: introduces floating-point inaccuracy into reconciliation.
double amount = Double.parseDouble(totalCents) / 100.0;
~~~

Instead:

~~~java
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal(totalCents).movePointLeft(2);
BigDecimal actual = decimal128FromMongo.bigDecimalValue();

if (expected.compareTo(actual) != 0) {
    // Record discrepancy by ID and include in the reconciliation report.
}
~~~

BigDecimal.compareTo compares numeric value; BigDecimal.equals also checks scale (e.g., 1.0 vs 1.00). If your contract requires preserving scale, verify scale explicitly. MongoDB Decimal128 has finite range and precision limits; migrations must explicitly handle source values that cannot be represented.

## 7. When the Source Continues Changing During Verification

A common source of false mismatches is counting the source at 10:00 while new orders arrive at 10:01 and checking the target at 10:02. Both counts can be accurate at their respective moments yet fail to reflect **the same dataset**.

Options depend on infrastructure and requirements:

| Strategy | Approach | Key considerations |
| --- | --- | --- |
| Pause writes (maintenance window) | Drain/block writes, capture snapshot, verify | Easiest to reconcile, but requires maintenance downtime. |
| Partition by watermark | Fix max timestamp/ID or migrationBatchId; compare identical scope | Watermark criteria must be stable; insufficient if older records are still updated. |
| Backfill + change stream | Load history, stream ongoing changes, drain lag before cutover | Must verify ordering, resume tokens, idempotency, and pending events. |
| Appropriate snapshot/transaction | Read critical slices from a consistent point when supported | Never hold massive, long-lived transactions or full-collection scans solely for checks. |

In replica sets and sharded clusters, read concern, write concern, replication lag, and visibility timing affect verification queries. Document the exact source, target, cutoff timestamp, checkpoint, and read consistency mode; **majority read** alone does not make two queries executed at different times observe the same snapshot.

If data keeps changing, safely bound the scope by ID/version or watermark, verify records inside that scope, confirm the change stream has drained up to the checkpoint, and re-verify immediately before cutting over read/write traffic.

### 7.1. Large-Scale Verification Performance

- Partition by stable key ranges such as _id, tenantId, or batch ID; prefer **keyset pagination** over large skips.
- Identify indexes supporting _id, legacyId, migrationBatchId, or common filters; do not build indexes during peak hours without assessing impact.
- Read in batches with bounded concurrency to avoid saturating CPU, I/O, network, or MongoDB connection pools.
- Run **exhaustive** verification when signing off on critical data cutovers; stratified sampling supplements this for fast bug detection.
- You can hash/checksum normalized records, provided you define canonical rules for field order, array order, Decimal128, null/missing, Unicode, and UTC timestamps. Two raw JSON checksums can differ even when business values match.
- Log mismatched IDs and grouped counts; cap logged examples so sensitive data is not inadvertently exposed.

A migration bug affecting 1% of orders in a single month can easily slip past 100 collection-wide random samples. Use targeted sampling across tenants, time windows, statuses, boundary values, and unusual source types alongside exhaustive checks.

## 8. Reconciliation Reports and Sign-Off Decisions

Persist a dedicated verification report for each migration run so it remains self-explanatory without guessing context:

| Metric | Example value | Acceptance criterion |
| --- | ---: | --- |
| Scope | orders_legacy → orders_v2, batch A | Locked and documented with filter and timestamp. |
| Source eligible | 100.000 | Deterministic comparison baseline. |
| Target in scope | 100.000 | Matches source count. |
| Source IDs missing in target | 0 | Must equal 0. |
| Target IDs missing in source | 0 | Must equal 0, barring approved exceptions. |
| Documents with wrong BSON type/schema | 0 | Must equal 0. |
| Documents with mismatched values | 0 | Must equal 0. |
| Broken references | 0 | Must equal 0 or match documented business exceptions. |
| Total amount delta | 0.00 | Must equal 0 at agreed unit and precision. |
| Change-stream lag at cutover | 0 unapplied events | Reached target checkpoint. |

*Numbers in the table are illustrative examples, not actual database execution results.*

A practical report should also include:

1. Run/batch ID, migration script version, source/target database and collection, and schema contract revision.
2. Scope filters, watermark or snapshot details, start/end timestamps, and concurrent-write handling strategy.
3. Checked counts, error counts by category, sample mismatched IDs, and group checksums/totals if applicable.
4. Pass/fail status per invariant, approved exceptions, sign-off owner, and rollback plan.
5. Rerun status after remediation, without overwriting the original failed report.

**PASS criteria** should be explicit and automatable: matching counts, bidirectional ID coverage, zero wrong BSON types, zero normalized value mismatches, zero unhandled constraint violations, and all changes caught up through the migration window. If errors are found, never manually patch a few documents and declare success; find the root cause, fix the logic or data via process, re-run over the affected scope, and re-verify.

## 9. Common Pitfalls

| Pitfall | Consequence | Remedy |
| --- | --- | --- |
| Comparing total document counts only | Misses offsetting gaps/extras and mis-mappings | Verify bidirectional IDs, BSON types, and per-document values. |
| Using estimatedDocumentCount for sign-off | Estimates may diverge from exact reality | Use countDocuments with an explicit scope filter. |
| Checking via mapped Java entities | Converters can mask wrong BSON types | Read raw Documents or run $type aggregations. |
| Converting money through double | Calculation/rounding drift | Use BigDecimal and Decimal128 matching the contract. |
| Comparing dates as raw strings | Ignores offsets, precision, and instant equivalence | Normalize to Instant/BSON Date in an explicit timezone. |
| Running unbatched $lookup across huge sets | Long-running queries and database load spikes | Partition, index, checkpoint, and monitor load. |
| Checking live data without a watermark | Comparing two different snapshots in time | Fix snapshot/scope, use CDC, or use a maintenance window. |
| Ignoring null/missing fields | Undetected loss of required values | Check $type and required fields. |
| Ignoring logical foreign keys | Document exists but references invalid targets | Run $lookup or relational integrity jobs. |
| Sampling a few records as full proof | Rare or partition-specific bugs slip through | Run exhaustive checks for sign-off; use sampling to assist. |

## 10. Suggested Practice Exercise

Create at least 6 source orders representing: valid order, zero amount, fractional cents after conversion, different statuses, timestamps near UTC day boundaries, and malformed source data. Populate the target collection using the agreed migration rules, and then intentionally introduce three discrepancies:

1. Omit one document and add one extra document not in source so total counts still match.
2. Change one document's amount from Decimal128 to double.
3. Change one document's status or timestamp while keeping the same _id.

Run the checks from Sections 3–5 and note which query catches each defect. Finally, fix the migration script, re-run idempotently, and produce a reconciliation report with zero discrepancies. If you have customer data, add a dangling customerId reference to verify cross-collection integrity checks.

**Self-assessment questions:**

- Why is sourceCount = targetCount insufficient for cutting over to the new schema?
- When Spring Data reads amount as BigDecimal, how do you prove MongoDB actually stored it as Decimal128?
- If both collections change during verification, what information is needed to know you are comparing the same dataset?
- When source stores cent strings and target stores Decimal128, why shouldn't you compare raw JSON or convert through double?

Post-migration verification is a **contractual reconciliation activity**, where every conclusion rests on defined scope, transformation rules, and measurable evidence. A finished job run only proves execution ended; the system should cut over to new data only after completeness, types, and consistency are proven against accepted business invariants.

## 11. References

- [Spring Data MongoDB – MongoTemplate Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): querying and counting documents with MongoTemplate.
- [Spring Data MongoDB – Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): mapping between Java objects and BSON.
- [MongoDB – countDocuments()](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/): query-based counting.
- [MongoDB – $type (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): identifying BSON types, null, and missing fields.
- [MongoDB – $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): comparing data and references across collections.
- [MongoDB – $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): type conversion and conversion error handling.
- [MongoDB – Decimal128](https://www.mongodb.com/docs/manual/tutorial/model-monetary-data/): modeling monetary and decimal data.
