# Updating With an Aggregation Pipeline Using AggregationUpdate

## 1. Why Do We Need an Update Mechanism Different From Standard Update?

In the **Writes and Updates** chapter of **Spring Data MongoDB**, we saw how `MongoTemplate` paired with `Query` and `Update` modifies documents without loading entire entities. For instance, `Update.set("status", "ACTIVE")` assigns a new status, and `Update.inc("quantity", 1)` increments a counter in one MongoDB operation.

Sometimes, however, the value to write **depends on fields already stored on the server**. Suppose an invoice has `quantity`, `unitPriceVnd`, `shippingFeeVnd`, and `discountVnd`, and the application needs to recompute:

\[
\text{totalVnd} = \text{quantity} \times \text{unitPriceVnd}
                 + \text{shippingFeeVnd} - \text{discountVnd}
\]

If implemented as "read invoice → compute in Java → write back," another request can alter the quantity or shipping fee between read and write, leaving the final result calculated from stale state.

**Aggregation pipeline updates** let MongoDB evaluate expressions against each document's current fields right inside the update command. Spring Data MongoDB provides `AggregationUpdate` to express this style of update:

~~~java
AggregationUpdate update = Aggregation.newUpdate()
        .set("totalVnd")
        .toValue(/* aggregation expression */);
~~~

This is a syntax skeleton; complete examples below use real expressions. An update on a **single document** remains atomic at the document level. With proper write predicates, the pipeline computes and saves the result from the server-side document state at update time rather than a snapshot copied earlier to Java.

### Expected Outcomes After This Lesson

1. Distinguish `Update` from `AggregationUpdate`, and **aggregation update** from `MongoTemplate.aggregate(...)`.
2. Use `Aggregation.newUpdate()` and `MongoTemplate.updateFirst/updateMulti` to compute fields from stored values.
3. Understand `$set`, `$unset`, `$add`, `$multiply`, `$ifNull`, `$cond`, and `$map` in update pipelines.
4. Avoid traps involving the `$` prefix, BSON field names, stage ordering, and differences between update operators and aggregation expressions.
5. Combine filters, tenant scoping, version checks, and result inspection to uphold business invariants under concurrent writes.
6. Verify BSON integrity, before/after state, missing fields, and performance against real MongoDB.

> Example context: Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and MongoDB **4.2 or newer** (aggregation pipeline updates were introduced in MongoDB 4.2). Verify API details and available expression operators against your project's Spring Data/driver/server versions.

## 2. Three Easily Confused Mechanisms

| Mechanism | Example | Payload Sent to MongoDB | Purpose |
|---|---|---|---|
**Standard Update** | `new Update().set("status", "ACTIVE").inc("quantity", 1)` | Document of **update operators** such as `$set`, `$inc` | Set fields or apply direct atomic operators |
**AggregationUpdate** | `Aggregation.newUpdate().set("totalVnd").toValue(expression)` | **Array of aggregation pipeline stages** in the update command | Compute and transform fields from server-side document state |
**Query Aggregation** | `mongo.aggregate(pipeline, Source.class, Report.class)` | Pipeline executed as a **query/aggregation** | Filter, group, compute, and return results; does not modify source data by default |

BSON example of a standard update:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  { $inc: { quantity: 1 } }
);
~~~

Example of an **aggregation pipeline update**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        totalVnd: {
          $subtract: [
            {
              $add: [
                { $multiply: ["$quantity", "$unitPriceVnd"] },
                "$shippingFeeVnd"
              ]
            },
            "$discountVnd"
          ]
        }
      }
    }
  ]
);
~~~

Notice the **second argument** of `updateOne`: standard updates pass an *update operator document*, whereas pipeline updates pass **an array of stages**. Inside a pipeline, `$set` is an **aggregation stage** whose right-hand value is evaluated as an **aggregation expression**—not identical in semantics to the `$set` update operator in a standard update document.

## 3. Stages Allowed by MongoDB in an Update Pipeline

MongoDB does not permit arbitrary aggregation stages inside an update pipeline. Eligible stages include:

| Stage | Effect When Updating a Document |
|---|---|
| `$set` or `$addFields` | Creates or replaces fields using an expression |
| `$project` | Reshapes which fields remain in the document |
| `$unset` | Removes fields from the document |
| `$replaceRoot` or `$replaceWith` | Rebuilds the root document from an expression |

Read/reporting stages such as `$match`, `$sort`, `$group`, `$lookup`, `$unwind`, `$out`, or `$merge` **cannot be placed arbitrarily as update pipeline stages**. To choose which documents get updated, place conditions in the **`Query`/filter** of `updateFirst` or `updateMulti`, rather than adding `$match` to the update stages.

Example:

~~~javascript
// Correct: select documents via the update command's filter,
// then keep only allowed stages in the pipeline.
db.invoices.updateMany(
  { tenantId: "tenant-a", status: "DRAFT" },
  [
    { $set: { reviewed: true } },
    { $unset: "oldStatusText" }
  ]
);
~~~

Here `$unset` deletes an old field while `status = DRAFT` sits outside the pipeline. If a transformation requires joining multiple collections to compute data, revisit the business model: you may need a separate read/aggregation step, a transaction, or a dedicated read model instead of expecting `AggregationUpdate` to run full reporting pipelines.

### Stage Order Matters

Pipeline stages evaluate **in sequence**. A later stage observes the output of prior stages. Inside a single `$set` stage setting multiple fields, **do not rely on property listing order** assuming one field's expression sees another field assigned in that same stage.

For instance, if you need to compute `subtotal` and then derive `total` from the new `subtotal`, use **two separate stages**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    { $set: { subtotalVnd: { $multiply: ["$quantity", "$unitPriceVnd"] } } },
    { $set: { totalVnd: { $add: ["$subtotalVnd", "$shippingFeeVnd"] } } }
  ]
);
~~~

Do not guess how many stages Spring Data emits from a builder chain without inspecting the generated BSON; when computation dependencies matter, verify the resulting pipeline or inline the expression directly without relying on a newly assigned sibling field.

## 4. Modeling an Invoice in Spring Data MongoDB

The example uses a simple invoice with monetary amounts stored as **integer VND** to keep focus on pipeline mechanics. For currencies with fractional units, design `BigDecimal`/BSON Decimal128 with explicit rounding policies; never carelessly use `double` for money.

**Invoice.java**

~~~java
package com.example.billing;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "invoices")
public record Invoice(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        int quantity,
        long unitPriceVnd,
        long shippingFeeVnd,
        long discountVnd,
        long totalVnd) {
}
~~~

`@MongoId(FieldType.STRING)` keeps `_id` as a BSON String even for 24-character hex strings. A record suits reading and writing full state, yet **you must avoid read-modify-save from stale copies** when concurrent writes can occur without version control.

An initial document:

~~~json
{
  "_id": "inv-101",
  "tenantId": "tenant-a",
  "status": "DRAFT",
  "quantity": 3,
  "unitPriceVnd": 100000,
  "shippingFeeVnd": 10000,
  "discountVnd": 50000,
  "totalVnd": 0
}
~~~

By the formula above, the correct total is:

\[
3 \times 100000 + 10000 - 50000 = 260000\text{ VND}.
\]

Currently `totalVnd` is 0 and needs updating from server-side data. In real environments, ensure `quantity`, `unitPriceVnd`, `shippingFeeVnd`, and `discountVnd` are valid values within numeric bounds and compatible with legacy schemas.

## 5. First Example: Computing Total From Existing Fields

In Spring Data MongoDB, `AggregationExpression` represents a MongoDB server-side expression. You can build expressions with Spring Data operator classes like `ArithmeticOperators`; here we use an explicit `Document`-based implementation to compare the **exact BSON** clearly.

**InvoiceRecalculationService.java**

~~~java
package com.example.billing;

import com.mongodb.client.result.UpdateResult;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class InvoiceRecalculationService {
    private final MongoTemplate mongo;

    public InvoiceRecalculationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public UpdateResult recalculate(String tenantId, String invoiceId) {
        Query query = Query.query(
                Criteria.where("id").is(invoiceId)
                        .and("tenantId").is(tenantId)
                        .and("status").is("DRAFT"));

        AggregationExpression total = context ->
                new Document("$subtract", List.of(
                        new Document("$add", List.of(
                                new Document("$multiply", List.of(
                                        "$quantity", "$unitPriceVnd")),
                                "$shippingFeeVnd")),
                        "$discountVnd"));

        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(total);

        return mongo.updateFirst(query, update, Invoice.class);
    }
}
~~~

Key takeaways:

1. `Query` contains ID, tenant, and status; MongoDB updates only a qualifying document. `id` maps to `_id` via `Invoice.class`.
2. `AggregationExpression` is evaluated **by MongoDB**, not computed over a Java object fetched to memory.
3. `Aggregation.newUpdate().set("totalVnd").toValue(total)` writes the expression's output to `totalVnd`.
4. `mongo.updateFirst(...)` updates the first matching document; since the filter specifies a unique `_id`, at most one document updates.
5. `UpdateResult` lets you check whether a document matched and whether data changed—without loading `Invoice` just to recalculate the total.

When called with `tenant-a` and `inv-101`, `totalVnd` updates to `260000` (assuming data hasn't changed and no errors occur). For a matching document, computation and field write occur within a single server-side update.

### 5.1. Aggregation Operators Require Proper Field References

In the expression above:

~~~javascript
{ $multiply: ["$quantity", "$unitPriceVnd"] }
~~~

`"$quantity"` is a **field reference**, whereas `"quantity"` without `$` is a string literal in an expression. If you forget `$`, MongoDB does not magically recognize it as a Java property.

Similarly, `List.of("$quantity", "$unitPriceVnd")` inside `Document` is merely **Java syntax constructing a BSON expression**—no arithmetic happens when Java calls `List.of`.

### 5.2. Inspecting the Update Outcome

~~~java
UpdateResult result =
        invoiceRecalculationService.recalculate("tenant-a", "inv-101");

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

Assume this snippet runs in a service or test holding an injected `invoiceRecalculationService` bean. Interpretation:

- `matched == 1`: a document satisfied the filter at update time.
- `matched == 0`: wrong ID/tenant, status changed, or document deleted; do not guess the cause from this count alone.
- `modified == 0` with `matched == 1` may mean the computed total equaled the stored value; it **does not** mean the update failed.

If a workflow must differentiate "not found" from "already transitioned," it can re-read **after** the operation to explain why, though that follow-up read never replaces the protective predicate inside the write command.

## 6. Direct Comparison With Update.set and Update.inc

A fixed change:

~~~java
import org.springframework.data.mongodb.core.query.Update;

Update classic = new Update()
        .set("status", "APPROVED")
        .inc("quantity", 1);
~~~

Here `"APPROVED"` is a literal value supplied by Java, and `$inc` is a MongoDB update operator.

When using a pipeline to increment from the currently stored value, you need an **aggregation expression**:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        quantity: { $add: ["$quantity", 1] }
      }
    }
  ]
);
~~~

`$inc` is **not an aggregation pipeline stage**. When you only need to increment a numeric field, `Update.inc(...)` is shorter and states intent clearly. `AggregationUpdate` pays off when you need formulas, missing/null handling, multi-step transformations, or expressions like `$cond` and `$map`.

| Requirement | Standard Update | AggregationUpdate |
|---|---|---|
`status = "APPROVED"` | `Update.set(...)` | `$set` stage with literal |
`quantity = quantity + 1` | `Update.inc(...)` | `$set` + `$add` expression |
`total = quantity * price + fee - discount` | No concise direct `Update` operator | Use `$multiply`/`$add`/`$subtract` |
If field missing, default 0 then add | `inc` handles some cases, not arbitrary null policies | `$ifNull` + `$add` per policy |
Classify status from multiple fields | Requires other code/methods | `$cond` or `$switch` |
Transform every array element | Array operators, array filters | `$map`/`$filter`, combined with expressions |

Never convert every minor update into a pipeline just "because it's more powerful." Command simplicity, clarity of business invariants, and actual performance should guide your choice.

## 7. Handling Missing/Null and Defaults in Expressions

When legacy documents lack `discountVnd` or store `discountVnd: null`, `$subtract` on null can evaluate to null instead of the right monetary amount. Express a policy like "missing discount means 0" with `$ifNull`:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101", status: "DRAFT" },
  [
    {
      $set: {
        totalVnd: {
          $subtract: [
            {
              $add: [
                { $multiply: ["$quantity", "$unitPriceVnd"] },
                { $ifNull: ["$shippingFeeVnd", 0] }
              ]
            },
            { $ifNull: ["$discountVnd", 0] }
          ]
        }
      }
    }
  ]
);
~~~

In Spring Data, the Java side can express this explicitly:

~~~java
AggregationExpression safeTotal = context ->
        new Document("$subtract", List.of(
                new Document("$add", List.of(
                        new Document("$multiply", List.of(
                                "$quantity", "$unitPriceVnd")),
                        new Document("$ifNull", List.of(
                                "$shippingFeeVnd", 0)))),
                new Document("$ifNull", List.of(
                        "$discountVnd", 0))));

AggregationUpdate recalculateSafely = Aggregation.newUpdate()
        .set("totalVnd").toValue(safeTotal);
~~~

This snippet applies defaults only to **shipping fee and discount**; it still requires `quantity` and `unitPriceVnd` to hold valid numeric types. If legacy data contains strings instead of numbers, run a migration or controlled type conversion with proper error handling. Never blindly treat "every null field as 0," which can hide corrupted data.

### Numeric Limits

The example uses `long`, yet large inputs can exceed 64-bit integer limits or cause MongoDB arithmetic operators to widen numeric types according to server arithmetic rules. In real financial systems, control precision, bounds, Decimal128, and rounding rules; never change a Java type and assume server expressions preserve identical semantics.

### Strings Starting With a `$` Sign

Inside an aggregation expression, `"$status"` is interpreted as a **field reference**. To write a string literal `"$VIP"`, wrap it explicitly as a literal:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [ { $set: { displayTag: { $literal: "$VIP" } } } ]
);
~~~

Similarly when building raw expressions in Java:

~~~java
AggregationExpression dollarText =
        context -> new Document("$literal", "$VIP");

AggregationUpdate update = Aggregation.newUpdate()
        .set("displayTag").toValue(dollarText);
~~~

Never concatenate raw expressions from user input assuming they will be treated as literals. Distinguish plain text input, field paths, and BSON operators to prevent logic bugs and unintended queries.

## 8. Conditional Updates With $cond

Suppose business logic classifies an order based on **current quantity**:

- If `quantity >= 10`, label it `BULK`.
- Otherwise, label it `RETAIL`.

MongoDB supports `$cond`:

~~~javascript
db.invoices.updateOne(
  { _id: "inv-101" },
  [
    {
      $set: {
        orderClass: {
          $cond: {
            if: { $gte: ["$quantity", 10] },
            then: "BULK",
            else: "RETAIL"
          }
        }
      }
    }
  ]
);
~~~

An equivalent Java expression:

~~~java
AggregationExpression orderClass = context ->
        new Document("$cond", new Document(
                "if", new Document("$gte", List.of("$quantity", 10)))
                .append("then", "BULK")
                .append("else", "RETAIL"));

AggregationUpdate update = Aggregation.newUpdate()
        .set("orderClass").toValue(orderClass);
~~~

For multi-branch conditions, MongoDB offers `$switch`; Spring Data also offers conditional expression builders. For highly complex policies, consider keeping business rules in the domain layer or a controlled write model: expressive power does not mean every business rule should be buried in a hard-to-test pipeline.

### Update Eligibility Differs From Computed Condition

The `$cond` example **does not block updating** an already `PAID` invoice; it only picks the value for `orderClass`. To **update only DRAFT invoices**, put `Criteria.where("status").is("DRAFT")` into the **filter**:

~~~java
Query draftOnly = Query.query(
        Criteria.where("id").is("inv-101")
                .and("tenantId").is("tenant-a")
                .and("status").is("DRAFT"));

mongo.updateFirst(draftOnly, update, Invoice.class);
~~~

This is key when handling state: **the filter guards which documents may be modified**, while expressions determine **the resulting values**.

## 9. Transforming Arrays With $map in an Update Pipeline

A standout strength of aggregation updates is transforming **every element** of an embedded array without pulling the whole array into Java.

Suppose a `purchase_orders` document holds:

~~~json
{
  "_id": "ord-7",
  "status": "DRAFT",
  "lines": [
    { "sku": "A", "quantity": 2, "unitPriceVnd": 50000 },
    { "sku": "B", "quantity": 3, "unitPriceVnd": 20000 }
  ]
}
~~~

We want to add `lineTotalVnd` to each line item using `quantity * unitPriceVnd`. Pipeline:

~~~javascript
db.purchase_orders.updateOne(
  { _id: "ord-7", status: "DRAFT" },
  [
    {
      $set: {
        lines: {
          $map: {
            input: { $ifNull: ["$lines", []] },
            as: "line",
            in: {
              $mergeObjects: [
                "$$line",
                {
                  lineTotalVnd: {
                    $multiply: ["$$line.quantity", "$$line.unitPriceVnd"]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

Inside `$map`:

- `input` selects the source array.
- `as: "line"` binds a local variable name for each element.
- `"$$line"` is an **element variable**, distinct from `"$lines"` which references the root document's field.
- `$mergeObjects` retains existing fields on each line and adds `lineTotalVnd`.
- `$multiply` computes using the current line's values.

Spring Data can accept this array transformation via `AggregationUpdate`:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;

AggregationExpression recalculateLines = context ->
        new Document("$map", new Document(
                "input", new Document("$ifNull", List.of("$lines", List.of())))
                .append("as", "line")
                .append("in", new Document("$mergeObjects", List.of(
                        "$$line",
                        new Document("lineTotalVnd",
                                new Document("$multiply", List.of(
                                        "$$line.quantity",
                                        "$$line.unitPriceVnd")))))));

AggregationUpdate update = Aggregation.newUpdate()
        .set("lines").toValue(recalculateLines);
~~~

This is a **raw BSON expression**; if your Java model uses `@Field("unit_price_vnd")` on `unitPriceVnd` inside line items, use the **actual BSON field name** in the raw expression, e.g., `"$$line.unit_price_vnd"`. Do not assume every expression path auto-maps Java property names like `Criteria.where(...)`.

### Caution When Replacing the Whole Array

`$map` builds a brand-new array for `lines`. Every element is recomputed and the `lines` field is rewritten. If you only need to update **one line matching a specific SKU**, positional operators or `arrayFilters` are simpler, cheaper, and more suitable.

Never use `$map` over an unbounded growing array: MongoDB caps BSON documents at **16 MiB**, and evaluating expressions over large arrays consumes CPU and memory. Measure workloads and consider splitting line items into a dedicated collection when data volume or lifecycle warrants it.

## 10. Stage Ordering, $unset, and Schema Migration

Pipeline updates are useful for **in-place schema migrations**. Suppose legacy documents contain `legacyAmount` and need `amountVnd` under the new standard before removing the old field:

~~~javascript
db.invoices.updateMany(
  {
    status: "DRAFT",
    legacyAmount: { $type: "number" }
  },
  [
    { $set: { amountVnd: "$legacyAmount" } },
    { $unset: "legacyAmount" }
  ]
);
~~~

The `$set` stage copies the old field's value, and `$unset` removes the old field. Order is critical: deleting `legacyAmount` first leaves nothing for the later stage to copy. The filter restricts migration to eligible documents.

**Checklist before running a real migration:**

1. Audit the current schema, including missing/null fields, numeric BSON types, and malformed records.
2. Plan rollback or backward-compatible reads during multi-version rolling deployments.
3. Run in checkpointed batches and monitor write throughput and index maintenance overhead.
4. Use tightly scoped queries; avoid unintended collection-wide updates.
5. If migrating identifier fields, remember `_id` is immutable; do not treat changing `_id` like editing an ordinary field.
6. Verify outcomes with raw BSON inspections and migrated document counts.

Not every migration is safe inside a single `updateMany`; across millions of documents, a mid-run failure leaves the dataset **partially migrated**. Design idempotency and safe re-runnability.

## 11. Concurrency, Atomicity, and Optimistic Locking

### 11.1. Why Do Pipelines Help Reduce Read–Modify–Write Races?

Suppose two concurrent requests try to **increment a counter** based on its stored value.

~~~text
Common bug:
  A reads counter = 5
  B reads counter = 5
  A saves counter = 6
  B saves counter = 6
Result: one increment is lost.
~~~

Instead of reading and writing back a stale copy, use an update operator:

~~~javascript
db.counters.updateOne(
  { _id: "monthly-billing" },
  { $inc: { processed: 1 } }
);
~~~

Or a conceptually equivalent aggregation pipeline expression:

~~~javascript
db.counters.updateOne(
  { _id: "monthly-billing" },
  [
    {
      $set: {
        processed: {
          $add: [
            { $ifNull: ["$processed", 0] },
            1
          ]
        }
      }
    }
  ]
);
~~~

Both updates on the **same document** are executed atomically at the document level by MongoDB rather than having the app write `6` from a stale read. For simple increments, `$inc` is more direct; for complex multi-field formulas, pipelines make sense.

### 11.2. Single-Document Atomicity Does Not Equal a Collection-Wide Transaction

`mongo.updateMulti(query, aggregationUpdate, Invoice.class)` can ask MongoDB to update **multiple documents**, evaluating expressions per document. Still, **the entire set of documents is not guaranteed to be atomic as a single transaction** simply by using a pipeline.

If a business action must edit an invoice, deduct inventory, and write a ledger entry **together** across collections, evaluate MongoDB transactions on a supported session/topology, or use a reservation/outbox/idempotency flow. Pipeline updates do not replace transactions.

### 11.3. With @Version, Filters Still Need Expected Checks

Spring Data MongoDB's `@Version` supports optimistic locking on appropriate write paths, notably when saving a loaded entity. With manually constructed `MongoTemplate.updateFirst(...)` calls, **never assume the query automatically verifies an expected version**.

For example, if business logic permits confirming an invoice only while `DRAFT` and still at the client's read `version`, place that condition explicitly in the filter; if the pipeline increments version, align all write paths on one policy.

~~~java
Query expected = Query.query(
        Criteria.where("id").is(invoiceId)
                .and("tenantId").is(tenantId)
                .and("status").is("DRAFT")
                .and("version").is(expectedVersion));

AggregationExpression nextVersion = context ->
        new Document("$add", List.of("$version", 1));

AggregationUpdate update = Aggregation.newUpdate()
        .set("version").toValue(nextVersion);

UpdateResult result = mongo.updateFirst(
        expected, update, VersionedInvoice.class);
~~~

This snippet is a **conditional operation pattern**, assuming the project defines `VersionedInvoice` (separate from `Invoice` in Section 4) with `id`, `tenantId`, `status`, and `version` mapped properly and an explicit version-bump policy. It is not a standalone copy-paste class. When using `@Version` on a real entity, verify how Spring Data auto-increments version on updates so you **never double-increment** or leave non-compliant write paths behind.

If `getMatchedCount() == 0`, no document was updated due to missing ID, wrong tenant, changed status, or stale version. The business layer can report a conflict or reload and **re-evaluate the decision before retrying**. Never blindly retry updates with side effects like awarding points, transferring funds, or confirming transactions.

### 11.4. Write Concern and Uncertain Errors

A timeout after sending a command does not prove MongoDB did not write. For **non-idempotent** updates such as incrementing counters or appending entries, retrying without an event/idempotency key can apply the change twice. Distinguish driver-level retryable writes from **business-level idempotency**, and configure write concern, error handling, and event IDs/checkpoints appropriately.

## 12. Field Mapping, BSON Types, and Raw Expression Pitfalls

Spring Data MongoDB lets you use Java property names in `Criteria` and `Update` when given an entity type, for example:

~~~java
@Field("unit_price_vnd")
private long unitPriceVnd;
~~~

Here `Criteria.where("unitPriceVnd").gte(10000)` maps to `unit_price_vnd`. Yet an `AggregationExpression` built with `new Document("$multiply", List.of("$quantity", "$unitPriceVnd"))` is an explicit BSON structure: **do not rely on the framework traversing raw Documents to rewrite `$`-prefixed strings**.

Two safe approaches:

1. In raw expressions, use the **exact stored BSON field name**, e.g. `"$unit_price_vnd"`, and inspect the emitted command.
2. Use Spring Data's expression builder classes to leverage mapping context where supported, still verifying the serialized representation in your version.

For nested documents or arrays, pay extra attention to `@Field`-renamed properties and `$$line` variables. Raw expressions are also never the place to interpolate client-supplied field path strings.

### BSON Types and Null Values

| Actual Stored Data | Risk During Computation | Typical Policy Needed |
|---|---|---|
`quantity` is valid BSON int/long | Multiplication may overflow numeric bounds | Cap quantities, check overflow, or pick wider types |
`discountVnd` missing/null | `$subtract` can produce null | Use `$ifNull` if business allows defaulting to 0 |
`unitPriceVnd` is String in legacy data | Arithmetic operators fail or reject type | Run controlled migration or conversion |
`amount` is Double | Binary floating-point rounding errors on money | Use Decimal128/`BigDecimal` and explicit rounding policy |
`lines` is not an array | `$map` can throw an error | Schema validation, `$isArray`, or clean malformed records first |
`currency` differs across lines | Summing money becomes invalid | Sum only matching currencies or apply explicit FX policy |

MongoDB Schema Validation helps prevent malformed writes going forward, though it does not replace application validation or migrations for existing data.

## 13. Performance: Fewer Round Trips, Not Automatically Cheaper

Aggregation pipeline updates eliminate the step of **fetching the document to Java to compute and write back**, cutting round trips and stale-snapshot risks. Even so, the server still reads the needed fields, evaluates expressions, and persists the result.

Key factors:

- **Filter and indexes:** `{ _id: ... }` uses the default unique index; `{ tenantId, status }` needs an index matched to workload, especially for multi-document updates.
- **Expression complexity:** simple `$add` differs substantially from `$map` across thousands of elements or heavy string manipulation.
- **Document size:** rewriting large arrays or wide documents increases CPU, memory, I/O, and oplog volume.
- **Indexes on modified fields:** updating indexed fields adds index-maintenance work.
- **Contention rate:** many workers hitting one hot document still bottleneck even though each command is atomic.
- **Consistency policy:** transactions, write concerns, retries, and replication lag affect latency.

### Queries and Indexes

For recalculating an invoice by ID and tenant:

~~~javascript
db.invoices.find({
  _id: "inv-101",
  tenantId: "tenant-a",
  status: "DRAFT"
}).explain("executionStats");
~~~

`explain` on the equivalent lookup shows the **document selection path**. It does not measure full computation and write cost of the update pipeline; pair it with command monitoring, profiling, and load metrics. Never extrapolate production performance from a single tiny test document.

### Choosing an Update Strategy

| Scenario | Preferred Approach |
|---|---|
Increment a counter by one | `Update.inc` |
Assign a constant value | `Update.set` |
Load full aggregate, apply domain logic, enforce version | `save` with appropriate optimistic locking |
Compute a field from multiple stored fields | `AggregationUpdate` |
Transform all array elements via an expression | `AggregationUpdate` + `$map`, if size is bounded |
Modify a single array element by ID/condition | Positional operator / `arrayFilters` if suitable |
Update multiple collections sharing an invariant | Transaction or designed consistency workflow |

## 14. Testing AggregationUpdate Against Real MongoDB

Unit tests that merely construct `AggregationUpdate` and mock `MongoTemplate` never prove MongoDB executes expressions accurately, especially across BSON types and field paths. Write integration tests against real MongoDB (e.g., Testcontainers) with an isolated schema. In Spring Boot 3.x, `@DataMongoTest` loads MongoDB test infrastructure, yet **does not start a server automatically**.

### 14.1. Testing the Total Formula

~~~java
package com.example.billing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationExpression;
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class InvoiceAggregationUpdateTest {
    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void setUp() {
        // Delete only in a dedicated test database.
        mongo.remove(new Query(), Invoice.class);
        mongo.insert(new Invoice(
                "inv-101", "tenant-a", "DRAFT",
                3, 100000L, 10000L, 50000L, 0L));
    }

    @Test
    void calculatesTotalFromCurrentServerFields() {
        AggregationExpression total = context ->
                new Document("$subtract", List.of(
                        new Document("$add", List.of(
                                new Document("$multiply", List.of(
                                        "$quantity", "$unitPriceVnd")),
                                "$shippingFeeVnd")),
                        "$discountVnd"));
        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(total);

        Query draftInvoice = Query.query(
                Criteria.where("id").is("inv-101")
                        .and("tenantId").is("tenant-a")
                        .and("status").is("DRAFT"));

        var result = mongo.updateFirst(
                draftInvoice, update, Invoice.class);

        assertThat(result.getMatchedCount()).isEqualTo(1);
        Invoice after = mongo.findById("inv-101", Invoice.class);
        assertThat(after).isNotNull();
        assertThat(after.totalVnd()).isEqualTo(260000L);

        Document bson = mongo.getCollection("invoices")
                .find(new Document("_id", "inv-101"))
                .first();
        assertThat(bson).isNotNull();
        assertThat(bson.get("totalVnd")).isInstanceOf(Number.class);
        assertThat(((Number) bson.get("totalVnd")).longValue())
                .isEqualTo(260000L);
    }

    @Test
    void doesNotTouchOtherTenantOrWrongStatus() {
        AggregationExpression constant = context ->
                new Document("$literal", 999L);
        AggregationUpdate update = Aggregation.newUpdate()
                .set("totalVnd").toValue(constant);

        Query wrongTenant = Query.query(
                Criteria.where("id").is("inv-101")
                        .and("tenantId").is("tenant-b"));

        assertThat(mongo.updateFirst(
                wrongTenant, update, Invoice.class).getMatchedCount())
                .isZero();
        assertThat(mongo.findById(
                "inv-101", Invoice.class).totalVnd())
                .isZero();
    }
}
~~~

This test verifies the formula computes accurately from stored fields and enforces tenant isolation. The test **does not** prove performance or every concurrent update edge case; add parallel tests, null/missing field tests, and input boundary tests.

### 14.2. Edge Cases Worth Testing

| Scenario | Expected Outcome |
|---|---|
`discountVnd = 0` | Total = item cost + shipping fee |
`discountVnd` null/missing | Pipeline with `$ifNull` applies 0 policy cleanly, or errors distinctly |
`quantity = 0` | Follows fee/discount policy; never negative if business forbids |
`status = PAID` | `DRAFT` filter skips update |
Mismatched `tenantId` | `matchedCount = 0` |
Two threads concurrently apply counter increment | No lost increments using atomic server-side expression |
Re-running total calculation with unchanged inputs | Idempotent output, no unintended extra additions |
Retrying counter-increment pipeline after timeout | Idempotency guard or prior-outcome reconciliation |
`unitPriceVnd` is String or null | Caught by validation/migration or error handling |
Empty/null `lines` array | `$map` uses proper fallback policy |
Field uses `@Field` differing from Java property | Raw expression references exact BSON field name |

### 14.3. Inspecting Emitted Commands and BSON Stages

MongoDB Java Driver supports `CommandListener` receiving `CommandStartedEvent`. In test environments, you can register a listener on `MongoClient` creation to inspect the `update` command and its `updates` array; each entry carries filter `q` and update `u`. For aggregation pipeline updates, `u` is a **pipeline array**, not a standard `{ "$set": ... }` update document.

Expected structure example:

~~~json
{
  "update": "invoices",
  "updates": [
    {
      "q": {
        "_id": "inv-101",
        "tenantId": "tenant-a",
        "status": "DRAFT"
      },
      "u": [
        {
          "$set": {
            "totalVnd": {
              "$subtract": [
                {
                  "$add": [
                    { "$multiply": ["$quantity", "$unitPriceVnd"] },
                    "$shippingFeeVnd"
                  ]
                },
                "$discountVnd"
              ]
            }
          }
        }
      ],
      "multi": false
    }
  ]
}
~~~

This is a trimmed command illustration, not a byte-for-byte guarantee. When checking raw BSON, note distinctions among String/Int32/Int64/Decimal128 and mapped field names. Capture commands only in authorized environments; never leak invoices, addresses, or customer data into production logs.

## 15. Common Mistakes When Using AggregationUpdate

| Mistake | Consequence | Fix |
|---|---|---|
Confusing `AggregationUpdate` with `aggregate()` queries | Expecting a report instead of writing data | Distinguish update pipelines from read aggregations |
Putting `$match` in update stages | Server rejects disallowed stage | Put predicates inside `Query` |
Writing `$inc` as a pipeline stage | Invalid update pipeline semantics | Use `$add` in expressions or `Update.inc` |
Forgetting `$` before field names in raw expressions | Computes against literal string instead of field value | Use `"$quantity"`, inspect real BSON |
Omitting `$literal` for strings starting with `$` | String gets treated as field reference | Wrap with `$literal` where needed |
Assuming assignments in one stage run sequentially | Expression reads unexpected value | Split dependent stages or inline full expression |
Raw expression uses Java name despite `@Field` | Reads nonexistent field, yields null/error | Use physical BSON name or mapping-aware builders |
Ignoring null/missing values in arithmetic | Null result or business error | Apply `$ifNull`/validation/migration |
Calling `updateMulti` expecting collection-wide atomicity | Failure mid-batch leaves partial state | Use transaction or idempotent re-runnable jobs |
Assuming pipeline updates enforce `@Version` | Overwrites if query lacks expected version | Add CAS predicates and explicit version policy |
Returning partial entity and calling `save` instead of pipeline | Drops unloaded fields | Update fields directly on the server |
Using `$map` to edit a single simple array element | Unnecessarily rewrites entire array | Consider positional operators/`arrayFilters` |
Retrying non-idempotent updates after timeout | Double-increments/double-subtracts | Use event IDs, idempotency keys, or conditional predicates |
Ignoring `matchedCount` | Misses wrong status or wrong tenant errors | Classify no-match per API contract |
Not testing against real MongoDB | Misses stage/BSON/mapping bugs | Run integration tests on isolated collections |

## 16. Practice Exercises

**Exercise 1 — Rewriting the calculation.** Create the `invoices` collection from Section 4. Compare loading the entity and computing in Java against using `AggregationUpdate` to compute `totalVnd` directly. Verify the value `260000`, count round trips, and explain the race risk when another request updates quantity mid-flight.

**Exercise 2 — Distinguishing $set and $inc.** Write `Update.inc("quantity", 1)` and the pipeline `$set: { quantity: { $add: ["$quantity", 1] } }`. Explain why `$inc` is not a pipeline stage and when the first option is simpler.

**Exercise 3 — Handling missing/null.** Seed three invoices with `discountVnd` set to `0`, `null`, and missing. Compare direct `$subtract` against `$ifNull`. Explain what business policy should apply when discount data is invalid.

**Exercise 4 — Stage ordering.** Write a pipeline computing `subtotalVnd` in stage one and `totalVnd` in stage two. Reverse the order on a document lacking `subtotalVnd` to observe what happens. Explain why stage order differs from property order within a single stage.

**Exercise 5 — Conditional labels with $cond.** Set `orderClass = BULK` when `quantity >= 10`, else `RETAIL`. Allow updating only `DRAFT` invoices for the active tenant; verify `PAID` invoices remain untouched.

**Exercise 6 — Transforming arrays.** Create an order with two line items. Use `$map`/`$mergeObjects` to add `lineTotalVnd` per line. Then rename the Java field with `@Field("unit_price_vnd")` and confirm the raw expression must reference the exact BSON field name.

**Exercise 7 — Concurrency and idempotency.** Have two workers update the same counter. Compare unversioned read-modify-save with server-side increments. Simulate a timeout retry and design a way to prevent applying an event twice.

**Exercise 8 — Migration.** Seed legacy records with `legacyAmount`; use an update pipeline to populate `amountVnd` and drop `legacyAmount`. Filter by type, make it safe to re-run, report migrated counts, and plan a rolling upgrade.

**Exercise 9 — Performance.** Across many invoices, compare per-ID updates against filtered/indexed `updateMulti`. Measure `matchedCount`, `modifiedCount`, p95 latency, server load, and partial-failure state. Never assume multi-document writes are atomic just because the pipeline executes server-side.

## 17. Key Takeaways

**`AggregationUpdate`** is Spring Data MongoDB's builder for **aggregation pipeline updates**, calculating and transforming values from **stored document state in MongoDB** instead of forcing a full read-to-Java-and-save cycle. Pairing `Aggregation.newUpdate()`, `set(...).toValue(...)`, and `MongoTemplate.updateFirst/updateMulti` executes arithmetic, conditionals, and array transforms via aggregation expressions.

Keep **update operators** (`$inc`, standard `$set`) distinct from **aggregation pipeline stages/expressions** (`$set` stage, `$add`, `$multiply`, `$ifNull`, `$cond`, `$map`). Document selection filters belong in `Query`; value expressions live in the pipeline; stage ordering affects visibility across stages. Raw BSON expressions must match stored field names and explicitly distinguish field references from string literals.

A single-document update is atomic at the document level, yet does not automatically create a **multi-document** transaction, does not replace optimistic locking without expected-version predicates, and does not make non-idempotent writes safe to retry blindly. Always inspect `matchedCount`, BSON types, legacy schemas, indexes, and emitted commands; write integration tests covering edge cases and concurrency before shipping pipeline updates to production.
