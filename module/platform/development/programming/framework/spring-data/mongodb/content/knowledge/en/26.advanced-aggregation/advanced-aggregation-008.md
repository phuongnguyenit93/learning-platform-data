# $replaceRoot, $unionWith, and Reshaping Output Documents

## 1. The Problem: Unifying Data Across Different Schemas

In the **Advanced Aggregation** chapter of **Spring Data MongoDB**, a pipeline does more than filter or sum: it can **completely reshape documents** and **merge result streams from multiple collections**.

Suppose a commerce platform stores two event types:

- Collection `order_events` records paid orders. Order details live inside a nested `payload` object.
- Collection `refund_events` records refunds. Refund details live inside a nested `details` object with different field names.

A financial history screen wants **a unified event row** regardless of whether the source is an order or a refund:

~~~json
{
  "eventId": "r-101",
  "source": "REFUND",
  "tenantId": "tenant-a",
  "orderId": "ord-101",
  "netAmountVnd": -40000,
  "occurredAt": { "$date": "2026-11-20T09:10:00Z" }
}
~~~

Order events carry a positive `netAmountVnd`; refund events carry a negative amount. To produce a single output schema, MongoDB must **normalize each source** first, then combine and sort them.

Two core stages:

1. **`$replaceRoot`**: replaces the entire current document with a new document—either promoted from a nested object or constructed via an expression.
2. **`$unionWith`**: appends documents from another collection or subpipeline into the current stream. It behaves like *UNION ALL*, **without automatically deduplicating records**.

These commonly pair with `$match`, `$set`, `$project`, `$sort`, `$group`, and `$limit`. Spring Data MongoDB supports building pipelines with `Aggregation`, `MongoTemplate.aggregate`, version-appropriate builders, and `AggregationOperation` for custom BSON stages.

### Learning Objectives

1. Explain why `$replaceRoot` differs from `$project` and when source fields disappear.
2. Write `$replaceRoot` on embedded objects, use `$mergeObjects` to preserve metadata, and guard against invalid documents.
3. Combine two collections with `$unionWith` without confusing it with `$lookup` or a deduplicating union.
4. Normalize field names, types, and signs of output fields before mapping into DTOs.
5. Build the pipeline in Spring Data MongoDB using `AggregationOperation` and consume `AggregationResults<DTO>`/`Document`.
6. Recognize version limits, tenant security, collation, read cost, sort/pagination rules, and transaction compatibility.
7. Write integration tests verifying real BSON, duplicate rows, filtered branches, and post-union aggregations.

> Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x on a MongoDB version supporting `$unionWith` (introduced in MongoDB 4.4). Verify server, Spring Data, driver versions, and topology constraints before adopting in production. This lesson uses **raw BSON stages** inside `AggregationOperation` where fluent builders vary across versions.

## 2. Quick Comparison: replaceRoot, project, unwind, unionWith, lookup

| Stage | What does it change? | Does it change row count? | When to use? |
|---|---|---|---|
| `$project` | Selects/computes/renames fields on a document | Normally no | Defining the output schema |
| `$set` / `$addFields` | Adds or overwrites specific fields | No | Computing `netAmountVnd` or adding metadata |
| `$replaceRoot` | **Replaces the entire root document** | One valid input to one output | Promoting a nested subdocument or building a new root |
| `$replaceWith` | Equivalent expression-based form of `$replaceRoot` | One valid input to one output | Concise syntax for replacing root with an expression |
| `$unwind` | Emits one row per array element | Can increase or decrease | Processing individual array items |
| `$lookup` | Attaches related docs from another collection | Usually adds an array; depends on later stages | Joining by key or relationship |
| `$unionWith` | **Appends result documents** from another source | Usually increases row count | Combining datasets with normalized schemas |
| `$group` | Emits one document per group | Usually decreases row count | Aggregating, reconciling, or intentional deduplication |

Clarify the requirement upfront:

- “Each order accompanied by its refunds” → usually `$lookup`.
- “Order events **and** refund events interleaved in one timeline” → `$unionWith`.
- “Promote `payload` to become the result document” → `$replaceRoot`.
- “Simply rename a few fields while keeping original metadata” → `$project` or `$set` is simpler.

Never treat `$unionWith` as a way to update two collections; it is a **read-and-transform aggregation stage**, not a write operation unless paired with dedicated write mechanisms.

## 3. Two Collections with Different Schemas

### 3.1. Orders

Source document in `order_events`:

~~~json
{
  "_id": "o-101",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" },
  "payload": {
    "orderId": "ord-101",
    "amount_vnd": 150000,
    "regionCode": "HCM"
  }
}
~~~

### 3.2. Refunds

Source document in `refund_events`:

~~~json
{
  "_id": "r-101",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:10:00Z" },
  "details": {
    "orderRef": "ord-101",
    "refund_vnd": 40000,
    "reason": "RETURN"
  }
}
~~~

Differences:

| Meaning | `order_events` | `refund_events` | Unified output |
|---|---|---|---|
Event key | `_id` | `_id` | `eventId` |
Source | Implicitly ORDER | Implicitly REFUND | `source` |
Tenant | `tenantId` | `tenantId` | `tenantId` |
Order ID | `payload.orderId` | `details.orderRef` | `orderId` |
Amount | `payload.amount_vnd` positive | `details.refund_vnd` positive | `netAmountVnd`: ORDER positive, REFUND negative |
Timestamp | `occurredAt` | `occurredAt` | `occurredAt` |

To visualize a small dataset:

| eventId | source | tenant | orderId | source amount | netAmountVnd |
|---|---|---|---|---:|---:|
| `o-101` | ORDER | tenant-a | ord-101 | 150,000 | +150,000 |
| `o-102` | ORDER | tenant-a | ord-102 | 60,000 | +60,000 |
| `r-101` | REFUND | tenant-a | ord-101 | 40,000 | −40,000 |
| `o-201` | ORDER | tenant-b | ord-201 | 900,000 | +900,000 |
| `r-201` | REFUND | tenant-b | ord-201 | 200,000 | −200,000 |

The timeline for `tenant-a` must return **three rows** with a net total of **170,000 VND**; the two `tenant-b` rows must not appear.

## 4. Source Entities and BSON Naming Rules

The records below illustrate Spring Data MongoDB mapping; each top-level `public record` belongs in its own Java file under `com.example.events`.

**OrderPayload.java**

~~~java
package com.example.events;

import org.springframework.data.mongodb.core.mapping.Field;

public record OrderPayload(
        String orderId,
        @Field("amount_vnd") long amountVnd,
        String regionCode) {
}
~~~

**OrderEvent.java**

~~~java
package com.example.events;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "order_events")
public record OrderEvent(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        Instant occurredAt,
        OrderPayload payload) {
}
~~~

**RefundDetails.java**

~~~java
package com.example.events;

import org.springframework.data.mongodb.core.mapping.Field;

public record RefundDetails(
        String orderRef,
        @Field("refund_vnd") long refundVnd,
        String reason) {
}
~~~

**RefundEvent.java**

~~~java
package com.example.events;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "refund_events")
public record RefundEvent(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        Instant occurredAt,
        RefundDetails details) {
}
~~~

Java properties are `amountVnd` and `refundVnd`, whereas BSON stores `amount_vnd` and `refund_vnd`. **Raw MongoDB aggregation expressions** must reference the actual BSON names—such as `"$payload.amount_vnd"`—rather than assuming Spring Data translates every string inside a custom `Document` from Java property names.

`@MongoId(FieldType.STRING)` preserves `_id` as a BSON String; that is a modeling choice for this example, not a requirement for all applications.

## 5. $replaceRoot: Promoting a Nested Document to Root

Suppose you want only the contents of `payload` without the outer envelope metadata:

~~~javascript
db.order_events.aggregate([
  { $match: { _id: "o-101" } },
  { $replaceRoot: { newRoot: "$payload" } }
]);
~~~

Output:

~~~json
{
  "orderId": "ord-101",
  "amount_vnd": 150000,
  "regionCode": "HCM"
}
~~~

**The entire old root is gone.** The output document no longer has `_id`, `tenantId`, or `occurredAt` because those fields were not inside `payload`.

When using `$replaceRoot`:

1. `newRoot` **must evaluate to a document/object**.
2. If `payload` is missing, `null`, or a non-object scalar, the pipeline **can error**.
3. Fields outside the new root disappear, including `_id` unless preserved explicitly.
4. This reshapes only the **aggregation output**—it never alters source BSON documents in the collection.
5. If a sub-field is an array, it is not a valid replacement document on its own; transform or `$unwind` as needed.

Never run `$replaceRoot: { newRoot: "$payload" }` blindly on legacy collections without schema checks.

### 5.1. Guarding Against Missing or Wrong-Type Payloads

To exclude documents lacking an object `payload`:

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      payload: { $type: "object" }
    }
  },
  { $replaceRoot: { newRoot: "$payload" } }
]);
~~~

If business rules require **keeping** documents with null/missing `payload`, construct `newRoot` using `$ifNull` or `$mergeObjects` with a fallback object. However, **`$ifNull` cannot fix a wrong-type scalar** like a string or number; validate schemas or filter by BSON type.

### 5.2. $replaceWith as an Equivalent Form

MongoDB also provides `$replaceWith`:

~~~javascript
db.order_events.aggregate([
  { $match: { _id: "o-101" } },
  { $replaceWith: "$payload" }
]);
~~~

It carries the exact same root-replacement semantics as `$replaceRoot`, taking the expression directly. `$replaceWith` was added in a newer MongoDB version than `$replaceRoot`; verify server compatibility before choosing it when supporting older servers.

## 6. Combining $replaceRoot with $mergeObjects to Preserve Metadata

The timeline needs `eventId`, `source`, `tenantId`, and `occurredAt` alongside fields promoted from `payload`. `$mergeObjects` combines them into a single document:

~~~javascript
db.order_events.aggregate([
  { $match: { tenantId: "tenant-a", payload: { $type: "object" } } },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$payload",
          {
            eventId: "$_id",
            source: { $literal: "ORDER" },
            tenantId: "$tenantId",
            occurredAt: "$occurredAt"
          }
        ]
      }
    }
  }
]);
~~~

Intermediate result:

~~~json
{
  "orderId": "ord-101",
  "amount_vnd": 150000,
  "regionCode": "HCM",
  "eventId": "o-101",
  "source": "ORDER",
  "tenantId": "tenant-a",
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

### 6.1. Merge Order Has Security Implications

`$mergeObjects` takes duplicate keys from the **last operand**. Here `"$payload"` comes first, and trusted outer metadata comes last:

~~~javascript
{ $mergeObjects: ["$payload", { tenantId: "$tenantId", source: "ORDER" }] }
~~~

If a client-influenced `payload` contains `tenantId: "tenant-b"` or `source: "REFUND"`, the outer metadata **overwrites** those spoofed keys. Reversing the operand order would let `payload` overwrite critical security fields.

Even after merging, `payload` may still carry extra fields that must not be exposed. Follow up with a **whitelist `$project`** to lock down the output schema.

### 6.2. $mergeObjects Does Not Replace Schema Validation

Inside `$mergeObjects`:

- A `null` operand is ignored per `$mergeObjects` semantics.
- A non-document scalar operand can fail the pipeline.
- Wrong-typed fields inside `payload` still get lifted to the root.

Always place `$match`/schema validation before `$replaceRoot`; never assume merging “heals” dirty legacy records. If multiple schema versions exist, use explicit migrations or version-branched logic.

## 7. Normalizing Output with $set and $project After replaceRoot

After `$replaceRoot` in Section 6, the document still has `amount_vnd` and `regionCode`. Because the timeline wants `netAmountVnd`, append two stages:

~~~javascript
{
  $set: {
    netAmountVnd: "$amount_vnd"
  }
},
{
  $project: {
    _id: 0,
    eventId: 1,
    source: 1,
    tenantId: 1,
    orderId: 1,
    netAmountVnd: 1,
    occurredAt: 1
  }
}
~~~

These are **two stages** following `$replaceRoot`, not a standalone command. `$set` creates the new field from the promoted root field; `$project` drops `amount_vnd` and everything outside the output contract.

Output:

~~~json
{
  "eventId": "o-101",
  "source": "ORDER",
  "tenantId": "tenant-a",
  "orderId": "ord-101",
  "netAmountVnd": 150000,
  "occurredAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

Path tracking note when chaining stages: `"$amount_vnd"` is **only valid after `payload` has been promoted to root**. Before `$replaceRoot`, the path is `"$payload.amount_vnd"`. Whenever a stage reshapes documents, verify every subsequent path.

## 8. $unionWith: Appending Results from Another Collection

`$unionWith` takes the form:

~~~javascript
{
  $unionWith: {
    coll: "refund_events",
    pipeline: [
      // Stages applied only to refund_events.
    ]
  }
}
~~~

It appends documents emitted by `refund_events` to the stream coming from `order_events`. **There is no join key like `orderId`** and **no automatic deduplication**; it concatenates row streams rather than joining columns onto one row.

### 8.1. Three Core Properties to Remember

1. **Both branches can have different schemas.** MongoDB does not align or validate matching field names between branches automatically.
2. **Duplicates can appear.** If both branches emit the same logical event or the same collection is unioned twice, duplicate rows stay in the stream.
3. **Output order is not guaranteed by branch order.** For an ordered timeline, place an explicit `$sort` **after `$unionWith`**.

Even if some test runs happen to print branch-one rows before branch-two rows, never write UI or test assertions assuming that implicit order.

### 8.2. Difference from $lookup

Suppose order `ord-101` has two refunds:

- `$lookup` returns **one order document** with a two-element `refunds` array.
- `$unionWith` returns **one ORDER row and two REFUND rows** sharing a unified event schema.

Use `$unionWith` for a multi-source event stream; use `$lookup` to enrich a source document with related documents. If you need a net summary report, you can union normalized rows and then `$group`.

## 9. Complete Pipeline: ORDER and REFUND Unified into One Output Schema

This `mongosh` pipeline normalizes **both branches**: ORDER maps `payload.amount_vnd` as positive; REFUND maps `details.refund_vnd` as negative:

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      payload: { $type: "object" },
      "payload.amount_vnd": { $type: "number" }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$payload",
          {
            eventId: "$_id",
            source: { $literal: "ORDER" },
            tenantId: "$tenantId",
            occurredAt: "$occurredAt"
          }
        ]
      }
    }
  },
  { $set: { netAmountVnd: "$amount_vnd" } },
  {
    $project: {
      _id: 0, eventId: 1, source: 1, tenantId: 1,
      orderId: 1, netAmountVnd: 1, occurredAt: 1
    }
  },
  {
    $unionWith: {
      coll: "refund_events",
      pipeline: [
        {
          $match: {
            tenantId: "tenant-a",
            details: { $type: "object" },
            "details.refund_vnd": { $type: "number" }
          }
        },
        {
          $replaceRoot: {
            newRoot: {
              $mergeObjects: [
                "$details",
                {
                  eventId: "$_id",
                  source: { $literal: "REFUND" },
                  tenantId: "$tenantId",
                  occurredAt: "$occurredAt"
                }
              ]
            }
          }
        },
        {
          $set: {
            orderId: "$orderRef",
            netAmountVnd: { $multiply: ["$refund_vnd", -1] }
          }
        },
        {
          $project: {
            _id: 0, eventId: 1, source: 1, tenantId: 1,
            orderId: 1, netAmountVnd: 1, occurredAt: 1
          }
        }
      ]
    }
  },
  { $sort: { occurredAt: -1, source: 1, eventId: 1 } },
  { $limit: 100 }
]);
~~~

### 9.1. Why Filter Tenant in Both Branches?

The leading `$match` filters only **`order_events`**. It **does not apply** to the `refund_events` subpipeline inside `$unionWith`. Omitting `$match` inside the refund branch exposes refunds belonging to **other tenants**.

That is a severe authorization flaw. Always place trusted tenant/authorization filters inside **every source branch**. Never wait until after unioning to filter tenant, especially if earlier stages aggregate or strip security metadata.

### 9.2. Why Identical Aliases and Types?

The ORDER branch uses:

~~~javascript
{ netAmountVnd: "$amount_vnd" }
~~~

The REFUND branch uses:

~~~javascript
{ netAmountVnd: { $multiply: ["$refund_vnd", -1] } }
~~~

If one branch emits `amountVnd` and the other emits `netAmountVnd`, MongoDB unions them cleanly, yet a DTO expecting `netAmountVnd` receives missing values for one branch. Similarly, if refund emits a negative number as a String while order emits a Long, post-union `$sum` fails to aggregate properly.

**Align field names, BSON types, currency units, sign conventions, and business meaning** across branches before unioning.

### 9.3. $limit Must Follow the Global Sort

The trailing `$sort` orders rows from both collections and `$limit` caps the newest 100 rows overall. Placing `$limit: 100` **before `$unionWith`** limits only the first branch, failing to cap the combined stream.

Sorting inside each individual branch without sorting again after union **does not guarantee final order**.

## 10. Java DTO for the Normalized Output

After the pipeline, both ORDER and REFUND share one uniform shape. Model it with a Java record:

**UnifiedEventDto.java**

~~~java
package com.example.events;

import java.time.Instant;

public record UnifiedEventDto(
        String eventId,
        String source,
        String tenantId,
        String orderId,
        long netAmountVnd,
        Instant occurredAt) {
}
~~~

With Section 3's data, `tenant-a` yields three rows ordered descending by timestamp:

| eventId | source | orderId | netAmountVnd | occurredAt |
|---|---|---|---:|---|
| `r-101` | REFUND | ord-101 | −40,000 | 09:10 |
| `o-102` | ORDER | ord-102 | +60,000 | 09:05 |
| `o-101` | ORDER | ord-101 | +150,000 | 09:00 |

Do not reuse `OrderEvent` or `RefundEvent` as the output type: those models have nested objects and different field names. The DTO mirrors **the normalized post-union schema**.

If historical data can lack `occurredAt` or `orderId`, validate or handle fallbacks explicitly. Primitive `long netAmountVnd` cannot represent `null` the way `Long` can; validate inputs and outputs rather than silently substituting defaults.

## 11. Spring Data MongoDB: Building Stages with AggregationOperation

Spring Data provides many aggregation builders, though exact signatures for `replaceRoot`/`unionWith` vary across releases. To keep this example **readable and directly comparable to BSON**, we use `AggregationOperation`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation stage = context ->
        new Document("$replaceRoot",
                new Document("newRoot", "$payload"));
~~~

An `AggregationOperation` represents **a single stage**, whose `toDocument(context)` emits the BSON stage. Constructing raw `Document`s means using physical BSON names and field references prefixed with `$`.

This is an intentional choice when combining two collections with differing schemas:

- Avoids mixing Java mapping metadata from ORDER with metadata from REFUND.
- Avoids coupling to version-specific builder method names.
- Makes stage-by-stage comparison against `mongosh` trivial.

The trade-off is that **raw BSON is not type-safe**, and field path strings are not checked at compile time. Production systems require integration tests, access reviews, and verification of actual emitted BSON commands.

### 11.1. Never Concatenate User Input into JSON

Never write:

~~~java
// DO NOT do this with client input:
String json = "{ $match: { tenantId: '" + userInput + "' } }";
~~~

Instead, bind values into a `Document`:

~~~java
Document match = new Document("$match",
        new Document("tenantId", authenticatedTenantId));
~~~

`authenticatedTenantId` must come from a trusted authentication/authorization context, never an arbitrary client-picked tenant. Always allowlist field names and operators when constructing `Document`s rather than accepting raw BSON queries from clients.

## 12. Full Spring Data Service for Timeline and Net Balance

The code below calls `MongoTemplate.aggregate` with **collection name** and raw `AggregationOperation`s intentionally: ORDER and REFUND have different `@Field` annotations, so each branch references **explicit normalized BSON names**.

**UnifiedEventReportService.java**

~~~java
package com.example.events;

import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.stereotype.Service;

@Service
public class UnifiedEventReportService {
    private final MongoTemplate mongo;

    public UnifiedEventReportService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    private static AggregationOperation stage(Document bson) {
        return context -> bson;
    }

    private static void validateTenant(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
    }

    private List<AggregationOperation> unifiedStages(String tenantId) {
        validateTenant(tenantId);

        Document orderMatch = new Document("$match",
                new Document("tenantId", tenantId)
                        .append("payload", new Document("$type", "object"))
                        .append("payload.amount_vnd",
                                new Document("$type", "number")));

        Document orderMetadata = new Document("eventId", "$_id")
                .append("source", new Document("$literal", "ORDER"))
                .append("tenantId", "$tenantId")
                .append("occurredAt", "$occurredAt");

        Document orderRoot = new Document("$replaceRoot",
                new Document("newRoot",
                        new Document("$mergeObjects", List.of(
                                "$payload", orderMetadata))));

        Document orderSet = new Document("$set",
                new Document("netAmountVnd", "$amount_vnd"));

        Document commonProjection = new Document("_id", 0)
                .append("eventId", 1)
                .append("source", 1)
                .append("tenantId", 1)
                .append("orderId", 1)
                .append("netAmountVnd", 1)
                .append("occurredAt", 1);

        Document refundMatch = new Document("$match",
                new Document("tenantId", tenantId)
                        .append("details", new Document("$type", "object"))
                        .append("details.refund_vnd",
                                new Document("$type", "number")));

        Document refundMetadata = new Document("eventId", "$_id")
                .append("source", new Document("$literal", "REFUND"))
                .append("tenantId", "$tenantId")
                .append("occurredAt", "$occurredAt");

        Document refundRoot = new Document("$replaceRoot",
                new Document("newRoot",
                        new Document("$mergeObjects", List.of(
                                "$details", refundMetadata))));

        Document refundSet = new Document("$set",
                new Document("orderId", "$orderRef")
                        .append("netAmountVnd",
                                new Document("$multiply",
                                        List.of("$refund_vnd", -1))));

        List<Document> refundStages = List.of(
                refundMatch,
                refundRoot,
                refundSet,
                new Document("$project", commonProjection));

        Document union = new Document("$unionWith",
                new Document("coll", "refund_events")
                        .append("pipeline", refundStages));

        return List.of(
                stage(orderMatch),
                stage(orderRoot),
                stage(orderSet),
                stage(new Document("$project", commonProjection)),
                stage(union));
    }

    private Aggregation timelinePipeline(String tenantId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }
        List<AggregationOperation> stages =
                new ArrayList<>(unifiedStages(tenantId));
        stages.add(stage(new Document("$sort",
                new Document("occurredAt", -1)
                        .append("source", 1)
                        .append("eventId", 1))));
        stages.add(stage(new Document("$limit", limit)));
        return Aggregation.newAggregation(stages);
    }

    public List<UnifiedEventDto> timeline(
            String tenantId, int limit) {
        AggregationResults<UnifiedEventDto> results =
                mongo.aggregate(
                        timelinePipeline(tenantId, limit),
                        "order_events",
                        UnifiedEventDto.class);
        return results.getMappedResults();
    }

    public List<Document> timelineDocuments(
            String tenantId, int limit) {
        return mongo.aggregate(
                timelinePipeline(tenantId, limit),
                "order_events",
                Document.class).getMappedResults();
    }

    public List<OrderBalanceDto> balanceByOrder(String tenantId) {
        List<AggregationOperation> stages =
                new ArrayList<>(unifiedStages(tenantId));

        stages.add(stage(new Document("$group",
                new Document("_id", "$orderId")
                        .append("eventCount", new Document("$sum", 1))
                        .append("netVnd",
                                new Document("$sum", "$netAmountVnd")))));
        stages.add(stage(new Document("$project",
                new Document("_id", 0)
                        .append("orderId", "$_id")
                        .append("eventCount", 1)
                        .append("netVnd", 1))));
        stages.add(stage(new Document("$sort",
                new Document("orderId", 1))));

        return mongo.aggregate(
                Aggregation.newAggregation(stages),
                "order_events",
                OrderBalanceDto.class).getMappedResults();
    }
}
~~~

**OrderBalanceDto.java**

~~~java
package com.example.events;

public record OrderBalanceDto(
        String orderId,
        long eventCount,
        long netVnd) {
}
~~~

### 12.1. Why Do Stages Use Document Instead of Java Property Names?

In `OrderPayload`, Java `amountVnd` maps to BSON `amount_vnd`. In `RefundDetails`, Java `refundVnd` maps to BSON `refund_vnd`. The raw pipeline deliberately uses:

~~~java
"payload.amount_vnd"
"details.refund_vnd"
"$amount_vnd"
"$refund_vnd"
~~~

**Never write `"$amountVnd"`** expecting a custom `Document` stage to map it to BSON automatically. Even a `TypedAggregation` anchored on `OrderEvent.class` cannot infer mapping metadata for the `refund_events` subpipeline inside `$unionWith` when written as raw BSON.

Spring Data releases include builders like `ReplaceRootOperation` and `UnionWithOperation`; adopt them if your version supports all required pipeline options, mapping context, and semantics. For multi-schema pipelines, **inspecting the actual BSON output is mandatory**.

### 12.2. Why Separate timeline and balanceByOrder Methods?

The timeline needs **all events** sorted chronologically and capped. The per-order balance needs to **group every event for the tenant** and sum net amounts.

Reusing a timeline pipeline truncated with `$limit: 100` before summing would undercount tenants with over 100 events. Thus `balanceByOrder` reuses only the normalization and union stages, **never applying the timeline limit before `$group`**.

### 12.3. Document Is Not the Source Entity

`timelineDocuments(...)` returns `List<Document>` holding **normalized fields**, not raw documents from either collection. To inspect source documents, query the source collections directly. For command-level response metadata, `AggregationResults.getRawResults()` differs from the documents inside `getMappedResults()`.

## 13. Inspecting Results: DTOs, Documents, and Totals

With the sample data:

~~~java
List<UnifiedEventDto> events =
        reportService.timeline("tenant-a", 100);

for (UnifiedEventDto e : events) {
    System.out.println(e.source() + " " + e.orderId()
            + " " + e.netAmountVnd());
}
~~~

`reportService` is the `UnifiedEventReportService` bean. Expected output:

~~~text
REFUND ord-101 -40000
ORDER ord-102 60000
ORDER ord-101 150000
~~~

Reading as `Document`:

~~~java
List<Document> documents =
        reportService.timelineDocuments("tenant-a", 100);

for (Document row : documents) {
    String eventId = row.getString("eventId");
    String source = row.getString("source");
    Object netAmount = row.get("netAmountVnd");

    if (!(netAmount instanceof Number amount)) {
        throw new IllegalStateException(
                "netAmountVnd must be a BSON number");
    }
    System.out.println(eventId + " " + source
            + " " + amount.longValue());
}
~~~

**BSON numeric types can vary**: Int32, Int64, Double, Decimal128. `Number.longValue()` fits when inputs are validated integers within `long` bounds. For fractional currencies or `Decimal128`, convert to `BigDecimal` under financial rules—never route through `double`.

For `balanceByOrder("tenant-a")`:

| orderId | eventCount | netVnd |
|---|---:|---:|
| `ord-101` | 2 | 110,000 |
| `ord-102` | 1 | 60,000 |

**Net total = 170,000 VND.** These figures reflect the rule “ORDER positive, REFUND negative.” Real accounting systems must also model reversals, fees, taxes, currencies, partial refunds, chargebacks, and replayed events.

## 14. $unionWith Does Not Deduplicate: Define Keys and Semantics

`$unionWith` behaves like **UNION ALL**, not **UNION DISTINCT**. If the same event appears in both branches, or one collection is unioned twice, duplicates stay in the output.

Example:

~~~javascript
db.order_events.aggregate([
  { $project: { _id: 0, eventId: "$_id" } },
  {
    $unionWith: {
      coll: "order_events",
      pipeline: [
        { $project: { _id: 0, eventId: "$_id" } }
      ]
    }
  }
]);
~~~

Every `eventId` in `order_events` appears **twice**. MongoDB never deduplicates rows automatically.

### 14.1. Creating a Multi-Source Identifier Key

Never assume `eventId` is globally unique **across collections**. Document `_id: "101"` in ORDER and `_id: "101"` in REFUND remain two separate events.

In a unified timeline, a logical key is:

~~~text
source + ":" + eventId
~~~

Or the tuple `(source, eventId)`. In multi-tenant models where IDs are only tenant-unique, include `tenantId` in the key. Always use **the full namespace** for cursors, checkpoints, response IDs, and deduplication keys.

### 14.2. Intentional Deduplication via $group

To remove **duplicate copies of the same event** on normalized output:

~~~javascript
{
  $group: {
    _id: { source: "$source", eventId: "$eventId" },
    event: { $first: "$$ROOT" }
  }
},
{
  $replaceRoot: { newRoot: "$event" }
}
~~~

Keep in mind that `$first` picks a document based on input order. If duplicate keys carry **differing payloads**, define a deterministic winner rule (revision, timestamp, authoritative source) and `$sort` appropriately before grouping—otherwise selection is non-deterministic. Re-sort afterward if callers expect ordered output.

Specifically, **never deduplicate distinct refunds sharing an `orderId`**. Two valid refunds on one order are two separate events; grouping by `orderId` is for **summing**, not event deduplication.

## 15. Grouping After Union: Turning Events into Summary Reports

Once both sources share `netAmountVnd`, per-order reporting is concise:

~~~javascript
// Append after the $unionWith stage of the normalized pipeline.
{
  $group: {
    _id: "$orderId",
    eventCount: { $sum: 1 },
    netVnd: { $sum: "$netAmountVnd" }
  }
},
{
  $project: {
    _id: 0,
    orderId: "$_id",
    eventCount: 1,
    netVnd: 1
  }
}
~~~

Once `$group` executes, the output schema **changes again**:

~~~text
Before $group:
  eventId, source, tenantId, orderId, netAmountVnd, occurredAt

After $group:
  _id (orderId), eventCount, netVnd

After $project:
  orderId, eventCount, netVnd
~~~

That is why `OrderBalanceDto` must be **distinct from `UnifiedEventDto`**. Never map a net-balance row back to a source entity simply because the pipeline began on `order_events`.

If regional totals are needed, define how refund regions are determined: a refund might need to inherit the original order's region rather than storing its own `regionCode`. `$unionWith` does not join keys automatically; add source attributes or a separate join step if needed.

## 16. $sort, $skip, $limit, and Cross-Request Stability

A timeline might use:

~~~javascript
{ $sort: { occurredAt: -1, source: 1, eventId: 1 } },
{ $skip: 20 },
{ $limit: 20 }
~~~

`occurredAt DESC` puts newest events first; `source ASC, eventId ASC` breaks ties on identical timestamps. Even so:

- Stable sorting on static data **does not create a snapshot** across separate API calls.
- New inserts at the head of the timeline can cause the next offset page to repeat an already-seen event.
- Deletions or timestamp edits can skip events.
- Deep `$skip` remains costly because the server reads and normalizes rows from both collections first.

For deep scrolling, consider a **keyset cursor** on the sort tuple (`occurredAt`, `source`, `eventId`). However, the “after cursor” filter must be applied **to both branches** under the same ordering rule—never filter only ORDER and union unbounded REFUNDs.

### 16.1. How Stage Placement Affects Results

| Stage placement | Effect |
|---|---|
`$match tenant` in both branches | Prevents cross-tenant mixing |
Early `$project` in each branch | Shrinks intermediate payloads; keeps schemas aligned |
`$unionWith` after normalization | Both streams share uniform fields |
`$sort` after union | Orders the entire combined timeline |
`$limit` after sort | Returns top N events across the combined stream |
`$group` after union | Aggregates across both sources |
`$limit` before revenue `$group` | Risks undercounting totals |

Never assume two per-branch `$sort` stages stay sorted after unioning, and never apply limits in Java after fetching all rows when the server can bound them first.

## 17. Performance, Indexes, Collation, and Deployment Limits

### 17.1. $match Each Source to Cut Read Cost

Candidate indexes when querying tenant timelines chronologically:

~~~javascript
db.order_events.createIndex(
  { tenantId: 1, occurredAt: -1, _id: 1 },
  { name: "idx_order_tenant_time_id" }
);

db.refund_events.createIndex(
  { tenantId: 1, occurredAt: -1, _id: 1 },
  { name: "idx_refund_tenant_time_id" }
);
~~~

Both collections maintain **separate indexes**. A single B-tree index cannot span two collections. Even when each branch uses its index for `$match`, the final post-union `$sort` still sorts the combined intermediate stream. Source indexes do not eliminate post-union sort work.

When filters add status, time windows, or event types, tailor indexes to the workload rather than assuming `{tenantId, occurredAt}` optimizes every `$unionWith` query.

### 17.2. Inspecting explain and Profiler Stats

Run an equivalent pipeline with:

~~~javascript
db.order_events.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $unionWith: {
      coll: "refund_events",
      pipeline: [
        { $match: { tenantId: "tenant-a" } }
      ]
    }
  }
]);
~~~

This is an **abbreviated diagnostic pipeline**, not the full normalization pipeline from Section 9. On the real pipeline, check `keysExamined`, `docsExamined`, sort/group stages, and timings. Diagnostics tools can display union branch execution stats differently across server versions; never rely on a single field if both branches are not visible.

Also measure:

- Documents read per branch before filtering vs. rows emitted after normalization.
- CPU and memory for `$replaceRoot`/`$mergeObjects`/`$sort`/`$group`.
- Network payload, p95/p99 latency, and growth rates of both collections.
- Write overhead of new indexes on event inserts.
- BSON type conversions when deserializing into Java DTOs or `Document`s.

### 17.3. Collation and String Comparisons

If the two collections have **different default collations**, or string sorting/grouping requires locale rules, check `$unionWith` collation rules and set an aggregation-level collation where supported by your API version.

String comparisons can behave differently under case/locale rules, affecting sorting, grouping, and deduplication. Never assume all collections share one collation or case-insensitive IDs. For event keys, prefer deterministic canonical comparisons.

### 17.4. Limits and Unsupported Combinations

- `$unionWith` requires **MongoDB 4.4+** and imposes restrictions on subpipelines, execution environments, and topologies.
- Do not assume `$unionWith` works in all transactions; MongoDB restricts `$unionWith` inside transactions. Verify against your server version if code runs under `@Transactional` or client session transactions.
- `$unionWith` subpipelines cannot arbitrarily include write stages like `$out` or `$merge`.
- Combinations with views, collations, sharding, or search stages carry version-specific rules—check documentation for your exact server version.
- For large groups/sorts, MongoDB enforces stage memory limits; depending on version, `allowDiskUse` or pre-aggregation may be needed.

Never extrapolate from a standalone latest-version test instance to assume every production version or topology behaves identically.

## 18. Security and Reliability of Multi-Source Data

When merging collections, a bug in one branch has wide impact:

### 18.1. Tenant and Authorization

- Filter `tenantId` in both ORDER and REFUND using a **trusted auth context**.
- Never blindly trust a tenant from a raw query parameter.
- Never filter tenant **after** `$group`: cross-tenant numbers have already been mixed.
- If permissions differ by event type, enforce per-type checks in each branch.
- Never expose arbitrary `payload`/`details` fields; apply a whitelist `$project`.

### 18.2. Monetary and Event Integrity

- `amount_vnd`/`refund_vnd` must be valid numbers and non-negative as source amounts.
- Never mix VND and foreign currencies into one `netAmountVnd` without currency conversion or grouping by currency.
- Refunds can be partial; never “deduplicate by `orderId`” and drop valid refunds.
- If events carry `CANCELLED`/`REVERSED` states, define explicitly whether they enter the timeline and net balance.
- Write-path retries can insert duplicates; unique event IDs and idempotency on **writes** are usually stronger than post-union deduplication.
- When collections change concurrently during a query, never assume aggregation gives a strict cross-collection business snapshot across arbitrary topologies and read concerns.

### 18.3. Logging and Sensitive Fields

BSON pipelines can contain tenant IDs, order IDs, and monetary amounts. With a MongoDB Java Driver `CommandListener` or profiler, enable logging only per policy, redact sensitive values, and bound retention.

Output DTOs help prevent leaking internal document structures, yet **never replace** database-side authorization and filtering.

## 19. Integration Testing on Real MongoDB

Mocking `MongoTemplate` only checks method calls—it **never verifies** that MongoDB handles `$replaceRoot`, `$unionWith`, `$mergeObjects`, or raw BSON names properly. Test against a real MongoDB version supporting `$unionWith`, such as Testcontainers. Spring Boot's `@DataMongoTest` configures the Spring Data MongoDB test slice, yet **does not start a MongoDB server automatically**.

### 19.1. Seeding and Testing Both Collections

**UnifiedEventReportServiceTest.java**

~~~java
package com.example.events;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(UnifiedEventReportService.class)
class UnifiedEventReportServiceTest {

    @Autowired MongoTemplate mongo;
    @Autowired UnifiedEventReportService reports;

    private Date at(String instant) {
        return Date.from(Instant.parse(instant));
    }

    @BeforeEach
    void seed() {
        // Delete data only in an isolated test database.
        mongo.getCollection("order_events").deleteMany(new Document());
        mongo.getCollection("refund_events").deleteMany(new Document());

        mongo.getCollection("order_events").insertMany(List.of(
                new Document("_id", "o-101")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:00:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-101")
                                        .append("amount_vnd", 150000L)
                                        .append("regionCode", "HCM")),
                new Document("_id", "o-102")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:05:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-102")
                                        .append("amount_vnd", 60000L)
                                        .append("regionCode", "HN")),
                new Document("_id", "o-201")
                        .append("tenantId", "tenant-b")
                        .append("occurredAt", at("2026-11-20T09:30:00Z"))
                        .append("payload",
                                new Document("orderId", "ord-201")
                                        .append("amount_vnd", 900000L))));

        mongo.getCollection("refund_events").insertMany(List.of(
                new Document("_id", "r-101")
                        .append("tenantId", "tenant-a")
                        .append("occurredAt", at("2026-11-20T09:10:00Z"))
                        .append("details",
                                new Document("orderRef", "ord-101")
                                        .append("refund_vnd", 40000L)
                                        .append("reason", "RETURN")),
                new Document("_id", "r-201")
                        .append("tenantId", "tenant-b")
                        .append("occurredAt", at("2026-11-20T09:15:00Z"))
                        .append("details",
                                new Document("orderRef", "ord-201")
                                        .append("refund_vnd", 200000L))));
    }

    @Test
    void timelineUnifiesShapeAndFiltersBothTenants() {
        List<UnifiedEventDto> rows = reports.timeline("tenant-a", 100);

        assertThat(rows).hasSize(3);
        assertThat(rows).extracting(UnifiedEventDto::eventId)
                .containsExactly("r-101", "o-102", "o-101");
        assertThat(rows).extracting(UnifiedEventDto::source)
                .containsExactly("REFUND", "ORDER", "ORDER");
        assertThat(rows).extracting(UnifiedEventDto::tenantId)
                .containsOnly("tenant-a");
        assertThat(rows).extracting(UnifiedEventDto::netAmountVnd)
                .containsExactly(-40000L, 60000L, 150000L);
    }

    @Test
    void outputDocumentHasWhitelistedShape() {
        List<Document> rows = reports.timelineDocuments("tenant-a", 100);
        Document refund = rows.get(0);

        assertThat(refund.getString("source")).isEqualTo("REFUND");
        assertThat(refund.getString("orderId")).isEqualTo("ord-101");
        assertThat(refund.containsKey("_id")).isFalse();
        assertThat(refund.containsKey("details")).isFalse();
        assertThat(refund.containsKey("payload")).isFalse();
        assertThat(refund.containsKey("reason")).isFalse();

        Object amount = refund.get("netAmountVnd");
        assertThat(amount).isInstanceOf(Number.class);
        assertThat(((Number) amount).longValue()).isEqualTo(-40000L);
    }

    @Test
    void groupAfterUnionUsesAllEventsNotTimelineLimit() {
        List<OrderBalanceDto> balances =
                reports.balanceByOrder("tenant-a");

        assertThat(balances).containsExactly(
                new OrderBalanceDto("ord-101", 2L, 110000L),
                new OrderBalanceDto("ord-102", 1L, 60000L));
    }

    @Test
    void otherTenantDoesNotLeakIntoResult() {
        List<UnifiedEventDto> tenantB = reports.timeline("tenant-b", 100);
        assertThat(tenantB).extracting(UnifiedEventDto::eventId)
                .containsExactly("o-201", "r-201");
        assertThat(tenantB).extracting(UnifiedEventDto::tenantId)
                .containsOnly("tenant-b");
    }
}
~~~

**Note:** `tenantB` above verifies `occurredAt DESC` ordering. Since `o-201` occurred at 09:30 and `r-201` at 09:15, the result is `o-201, r-201`. This confirms sorting happens **after unioning**, independent of branch order.

### 19.2. Testing Malformed Data Cases

Additional tests to include:

| Case | Objective |
|---|---|
`payload = null` or missing | Match filter excludes non-object documents before `$replaceRoot` |
`payload` is a String | Prevents `$replaceRoot` from running on a wrong-type scalar |
`payload.amount_vnd` missing or String | Not treated as a valid monetary value |
`details.refund_vnd` null/wrong type | Explicit policy instead of silently mis-summing |
Order and refund share the same `eventId` | Namespaced keys prevent conflating distinct events |
Two distinct refunds on the same `orderId` | Not deduplicated in net-balance reports |
Payload forged with `tenantId`/`source` | Outer metadata in `$mergeObjects` wins; `$project` whitelists |
Tenant with 0 ORDER events but existing REFUND | Refund branch still appears after union |
Identical timestamps | Sort tie-broken deterministically by `source`/`eventId` |
More events than timeline limit | `balanceByOrder` still aggregates every event |
Server lacking `$unionWith` | Test surfaces version incompatibility rather than ignoring silently |
Amounts exceeding Int64 or Decimal128 | Verify mapping and numeric precision rules |

### 19.3. Inspecting BSON Commands and Execution

To inspect raw pipelines sent from Java, register a MongoDB Driver `CommandListener` listening for `CommandStartedEvent` in integration tests. Verify:

- The leading stage has `$match` tenant for ORDER.
- `$unionWith.pipeline` has its own `$match` tenant for REFUND.
- `$replaceRoot` uses `$mergeObjects` with trusted metadata last.
- Both `$project` stages emit identical field names.
- `$sort`/`$limit` appear after unioning.

When running `explain("executionStats")`, evaluate indexes and latencies on representative datasets. Never mistake a test passing on a handful of documents for production performance proof.

## 20. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
Assuming `$replaceRoot` only appends child fields | Old root is replaced and metadata vanishes | Use `$mergeObjects` or `$project` deliberately |
`newRoot` evaluates to null/scalar | Aggregation can fail | Filter for object type or provide valid fallback |
Placing metadata before payload in `$mergeObjects` | Payload can overwrite `tenant`/`source` | Put trusted metadata last, then whitelist output |
Still using `"$payload.amount_vnd"` after `$replaceRoot` | Path is no longer valid | Use `"$amount_vnd"` once payload is promoted |
Confusing `$unionWith` with `$lookup` | Wrong shape: concatenated rows vs. joined array | Choose based on timeline vs. relational enrichment |
Assuming union deduplicates automatically | Revenue can be double-counted | Define event keys and deduplicate explicitly when needed |
Branches emit different amount field names | Missing DTO fields and wrong group sums | Normalize to `netAmountVnd` in both branches |
Forgetting to negate REFUND | Net balance increases instead of decreasing | Enforce sign convention and test |
Omitting tenant filter in union branch | Cross-tenant data leakage | Put trusted `$match` inside every branch |
Placing `$limit` before union or summary `$group` | Truncated timeline or undercounted report | Limit after global sort; never limit before revenue `$group` |
Relying on implicit union order | Flaky UI and tests | Sort globally with tie-breakers |
Raw expressions using Java property names instead of BSON | Unexpected missing/null fields | Verify `@Field` mappings and BSON commands |
Mapping union output back to source entity | Missing/wrong fields | Create a dedicated output DTO |
Deduplicating by `orderId` | Drops legitimate multiple refunds | Deduplicate by namespaced event key |
Assuming `$unionWith` works in any transaction | Unsupported at runtime | Check MongoDB version and transaction/topology limits |
Testing only ORDER without seeding REFUND | Misses bugs in the union branch | Integration test both collections |
Ignoring per-source indexes and latencies | Pipeline degrades as data grows | Run `explain`, track metrics, index each collection |

## 21. Practice Exercises

**Exercise 1 — Replace root.** Create an `order_events` document with a `payload` object. Run `$replaceRoot: { newRoot: "$payload" }` and list which fields vanish. Test a missing payload and explain why type checks are needed.

**Exercise 2 — Merge metadata.** Use `$mergeObjects` to preserve `eventId`, `tenantId`, and `source`. Inject `tenantId: "tenant-b"` inside `payload` and verify trusted outer metadata wins when placed last. Add a whitelist `$project`.

**Exercise 3 — Union two schemas.** Insert 2 orders and 1 refund. Normalize each branch to `eventId/source/orderId/netAmountVnd/occurredAt`, then run `$unionWith`. Verify refunds carry a negative sign.

**Exercise 4 — Tenant isolation.** Add events for `tenant-b`. Remove `$match` inside the `$unionWith` subpipeline in a test environment to observe the leak, then restore the filter and add a regression test.

**Exercise 5 — UNION ALL and deduplication.** Union `order_events` with itself and verify each event appears twice. Use `$group` by `(source, eventId)` to deduplicate and explain the role of `$first` plus sorting.

**Exercise 6 — Net balance report.** After unioning, `$group` by `orderId` to compute `netVnd` and `eventCount`. Verify `ord-101` nets 110,000 and `ord-102` nets 60,000; never apply a timeline limit prior to grouping.

**Exercise 7 — Spring Data.** Implement raw-BSON `AggregationOperation` stages with `MongoTemplate.aggregate`; compare `AggregationResults<UnifiedEventDto>` with `AggregationResults<Document>`. Assert output fields match the whitelist.

**Exercise 8 — `@Field` mapping.** Rename Java field to `amountVnd` while keeping BSON `amount_vnd` via `@Field`. Write a test proving raw stages use the physical BSON name rather than the Java property name.

**Exercise 9 — Paging.** Seed 1,000 events per source; compare post-union sort/limit vs. pre-union limit. Test offset paging under concurrent inserts, then design a keyset cursor on `(occurredAt, source, eventId)`.

**Exercise 10 — Performance.** Add tenant/time indexes on each collection, run `explain`, and benchmark on large data. Record `docsExamined`, `keysExamined`, CPU, memory, and p95 latency, identifying whether the bottleneck lies in filtering, `$replaceRoot`, unioning, or sorting.

**Exercise 11 — Data integrity.** Test multiple refunds on one order, null amounts, replayed events, and multiple currencies. Define explicitly when a report must fail vs. exclude/quarantine an event rather than silently emitting wrong sums.

## 22. Key Takeaways

**`$replaceRoot`** replaces **the entire current document** with a new document; pairing it with `$mergeObjects` and `$project` promotes nested objects while preserving trusted metadata and locking down the output schema. Always verify `newRoot` has object type, protect overwritten fields, and update field paths after reshaping.

**`$unionWith`** appends results from another collection/pipeline with **UNION ALL** semantics: **no key join, no automatic deduplication, no order guarantee, and no automatic schema alignment**. Each branch must enforce tenant/authorization filters and normalize field names, types, units, and signs before unioning. Sort and limit after unioning for timelines; group over **all matching rows** for summaries.

In **Spring Data MongoDB**, use `Aggregation`/`MongoTemplate.aggregate` with version-appropriate builders or `AggregationOperation` carrying explicit BSON stages. When using raw `Document`s, field names must match **physical BSON names** rather than expecting Spring Data to rewrite every string expression. Shape DTOs around the **final output**, verify on real MongoDB, and evaluate indexes, server version, collation, transaction limits, write-path idempotency, and multi-tenant isolation before going to production.
