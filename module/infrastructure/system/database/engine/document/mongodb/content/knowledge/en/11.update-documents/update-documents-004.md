# Updating Numbers and Timestamps with $inc, $mul, $min, $max, and $currentDate

In MongoDB, update operations do not require reading a document into the application, computing a new value, and writing the entire document back. **Update operators** let you instruct the server to perform addition, multiplication, bound comparisons, or current timestamp assignment directly on the targeted fields.

Five commonly used operators are:

| Operator | Meaning | Business Example |
|---|---|---|
| `$inc` | Increments or decrements a numeric value by an amount | Increment view counts, decrement inventory, add retry attempts |
| `$mul` | Multiplies a numeric value by a factor | Percentage price adjustments, metric unit scaling |
| `$min` | Updates only if the candidate value is **less than** the current value | Record lowest score, earliest start date |
| `$max` | Updates only if the candidate value is **greater than** the current value | Record highest score, latest event timestamp |
| `$currentDate` | Sets the current date/time when the server processes the update | `updatedAt`, state-change timestamp |

These operators work in `updateOne()`, `updateMany()`, and corresponding update APIs. Updating **a single document is atomic**, so the new value computation happens within that write operation. However, this **does not automatically create an atomic transaction across multiple documents**, nor does it make every update idempotent if the command is resent.

## 1. Preparing Data and Understanding Update Structure

Suppose the `inventory` collection stores products along with operational metrics:

```javascript
db.inventory.insertMany([
  {
    _id: "SKU-101",
    name: "Mechanical Keyboard",
    price: NumberDecimal("1200000.00"),
    stock: NumberInt(40),
    metrics: {
      views: NumberLong("250"),
      sold: NumberLong("12"),
      ratingMax: 4.5,
      ratingMin: 3.0
    },
    firstSoldAt: ISODate("2026-03-10T08:00:00Z"),
    lastSoldAt: ISODate("2026-03-15T16:00:00Z"),
    updatedAt: ISODate("2026-03-15T16:00:00Z")
  },
  {
    _id: "SKU-102",
    name: "Wireless Mouse",
    price: NumberDecimal("350000.00"),
    stock: NumberInt(8),
    metrics: { views: NumberLong("30") }
  }
]);
```

BSON numeric values can be `Int32`, `Int64`, `Double`, or `Decimal128`. The `updatedAt` field holds a BSON Date, which differs from an ISO string stored as String.

General form:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },                // Filter: document to update
  { $inc: { stock: -2 } }             // Update: field operations
);
```

Unlike whole-document replacement, an **update document** uses operators such as `$inc`, `$set`, and `$currentDate` to modify only the necessary fields. You can combine **multiple operators on non-conflicting paths**:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: {
      stock: -2,
      "metrics.sold": 2
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
```

The dot in `"metrics.sold"` is **dot notation** to access nested fields. If the parent is a suitable object, the update can create a missing child field. If the parent holds a type that cannot contain that path, such as `metrics: null`, the operation will fail rather than turning every value into an object.

## 2. $inc: Adding or Subtracting a Numeric Amount

Syntax:

```javascript
{ $inc: { fieldName: amount } }
```

With `amount > 0`, the value increases. With `amount < 0`, the value decreases. Multiple numeric fields in the same document can be modified in one update.

### 2.1. Incrementing View Counts

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: { "metrics.views": NumberLong("1") }
  }
);
```

If `metrics.views` was `250`, the result after one update is `251`.

### 2.2. Decrementing Inventory Stock

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $inc: { stock: -3 } }
);
```

If `stock` was `40`, it decreases to `37`. However, using `$inc: -3` alone **does not prevent negative inventory** when remaining stock is less than the deduction amount.

To enforce the invariant against overselling, place the condition directly in the filter:

```javascript
const quantity = 3;

const result = db.inventory.updateOne(
  {
    _id: "SKU-101",
    stock: { $gte: quantity }
  },
  {
    $inc: { stock: -quantity },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount !== 1) {
  print("Product does not exist or insufficient stock");
}
```

The filter and decrement are evaluated together in **one atomic write operation on the document**. When two requests purchase the product nearly simultaneously, `stock >= quantity` is checked against the state seen by each update, avoiding the anti-pattern of reading the old count in the application and overwriting it.

If you also need to create an order in another collection or call an external payment gateway, design a transaction or broader business workflow; a single stock decrement does not cover the entire system.

### 2.3. $inc with Missing Fields and null

Two important states:

| Field value before update | `$inc: { count: 2 }` |
|---|---|
| `count: 5` | Becomes `7` |
| Missing `count` | Creates `count: 2` |
| `count: 0` | Becomes `2` |
| `count: null` | **Errors**, does not treat null as 0 |
| `count: "5"` | Not a valid numeric field; operation errors |

Example:

```javascript
db.counterLab.insertMany([
  { _id: "missing" },
  { _id: "isNull", count: null },
  { _id: "five", count: NumberInt(5) }
]);

// Creates count = 2 because the field does not exist yet:
db.counterLab.updateOne(
  { _id: "missing" },
  { $inc: { count: 2 } }
);

// Field count is null -> operation errors:
db.counterLab.updateOne(
  { _id: "isNull" },
  { $inc: { count: 2 } }
);
```

Do not rely on `$inc` handling `null` automatically. When legacy data may contain null or strings, normalize the schema or run a migration before updating. You can inspect types with `$type`, add a validator for numeric fields, and standardize error handling.

### 2.4. Why $inc Is Safer Than Read–Add–Set

Pattern prone to **lost updates**:

```javascript
const product = db.inventory.findOne({ _id: "SKU-101" });
const newViews = product.metrics.views + 1;

db.inventory.updateOne(
  { _id: "SKU-101" },
  { $set: { "metrics.views": newViews } }
);
```

Two requests can both read `250` and both `$set` it to `251`: one increment is lost.

Use:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $inc: { "metrics.views": NumberLong("1") } }
);
```

MongoDB computes the addition against the document's state during the write operation, avoiding the read–write lost update bug above. This is **single-document atomicity**, not a guarantee that every business request executes only once under all retry scenarios.

## 3. $mul: Multiplying the Current Value by a Factor

Syntax:

```javascript
{ $mul: { fieldName: multiplier } }
```

The target field must hold a valid numeric value. The multiplier can be an integer, Double, or Decimal128. A common use case is scaling prices by a percentage:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $mul: {
      price: NumberDecimal("1.05")
    },
    $currentDate: { updatedAt: true }
  }
);
```

With an initial price of `1200000.00`, the mathematical value after one multiplication is `1260000.0000` (Decimal128 display formatting may vary). Design explicit **currency rounding rules** based on currency units and business contracts; `$mul` does not automatically enforce two decimal places for money.

### 3.1. Factors Greater Than, Less Than, or Equal to 1

| Factor | Meaning | Example starting price 200 |
|---:|---|---:|
| `2` | Double | 400 |
| `1.10` | Increase 10% | 220 |
| `0.80` | Decrease 20% | 160 |
| `1` | Unchanged value | 200 |
| `0` | Sets result to 0 | 0 |
| `-1` | Flip sign | -200 |

Use `$mul` only when the business requirement genuinely calls for **multiplying the current value**. If the goal is "promotional price fixed at 80% of base price", calling `$mul: 0.8` each time a request is processed causes repeated discounting:

```text
Original price:              200
After first $mul 0.8:        160
After second $mul 0.8:       128
```

Jobs that can retry, re-run on a schedule, or be processed by multiple workers need a **base price reference** or an idempotency mechanism. Do not treat `$mul` as an idempotent write.

### 3.2. $mul on a Missing Field: Creates Value 0

Unlike `$inc`, if the field does not exist, `$mul` creates the new field with **value 0 of the same numeric type as the multiplier**:

```javascript
db.priceLab.insertOne({ _id: "missingPrice" });

db.priceLab.updateOne(
  { _id: "missingPrice" },
  { $mul: { price: NumberDecimal("1.20") } }
);

// price is created with Decimal128 value 0,
// NOT 1.20 and NOT null.
```

This makes sense as multiplying a default 0 at the update level, but it **does not produce a valid business starting price**. If you want "use a default price when absent, otherwise multiply by a factor", design a conditional update or aggregation pipeline rather than plain `$mul`.

For existing fields, `$mul` requires a numeric value. Do not run it directly on a string or `null` expecting MongoDB to coerce it to a number.

### 3.3. Numeric Types and Precision When Multiplying

MongoDB supports `Int32`, `Int64`, `Double`, and `Decimal128`. When two operands have different types, MongoDB applies **numeric type conversion** rules for `$mul`:

- `Int32 × Int32` can yield `Int32` or promote to `Int64` when exceeding 32-bit bounds.
- `Int64 × Int64` remains `Int64` when the result fits within supported bounds.
- Operations involving `Double` generally yield `Double` if no Decimal128 is involved.
- If either operand is `Decimal128`, the result belongs to the Decimal128 type under conversion rules.

Integer multiplications exceeding Int64 bounds can raise an error; avoid assuming MongoDB promotes infinitely to arbitrary-precision numbers. For monetary amounts, consider `Decimal128` or integers representing the smallest currency unit, paired with rounding and range rules.

Example using Decimal128 for the multiplier:

```javascript
db.inventory.updateOne(
  { _id: "SKU-102" },
  {
    $mul: { price: NumberDecimal("0.95") }
  }
);
```

If `price` is already Decimal128, the result is computed using decimal arithmetic. Accidentally using Double anywhere in the calculation pipeline can introduce floating-point representation error.

## 4. $min: Update Only When the New Value Is Smaller

Syntax:

```javascript
{ $min: { fieldName: candidateValue } }
```

MongoDB compares the current value against the candidate value. If the candidate is **less than** the current value, the field is replaced with the candidate; if **equal or greater**, the field stays unchanged. If the field **does not exist yet**, MongoDB creates it with the candidate value.

### 4.1. Storing the Lowest Score

```javascript
db.playerStats.insertOne({
  _id: "player-01",
  bestScore: 900,
  worstScore: 120
});

db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 95 } }
);

// worstScore: 95

db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 150 } }
);

// worstScore remains 95.
```

Use `$min` when you want to maintain the **observed minimum** without reading the old value back into the application.

### 4.2. Recording the Earliest Date

```javascript
db.userActivity.insertOne({
  _id: "user-01",
  firstSeenAt: ISODate("2026-04-20T10:00:00Z")
});

db.userActivity.updateOne(
  { _id: "user-01" },
  {
    $min: {
      firstSeenAt: ISODate("2026-04-15T09:30:00Z")
    }
  }
);

// firstSeenAt becomes 2026-04-15T09:30:00Z.
```

When the field consistently uses BSON Date, `$min` is a concise way to retain the **earliest timestamp** across events that may arrive out of order. Still, event timestamps from external systems differ from the server's update-processing time; keep those two concepts distinct.

### 4.3. $min Is Not a Cross-Document Minimum

`$min` in an **update document** maintains the minimum of a field within **the single document being updated**. It differs from the `$min` accumulator used in aggregation `$group` to compute the minimum across **multiple documents**:

```javascript
// Update: keeps the lowest score inside document player-01.
db.playerStats.updateOne(
  { _id: "player-01" },
  { $min: { worstScore: 80 } }
);

// Aggregation: computes the lowest score across the document set.
db.playerStats.aggregate([
  {
    $group: {
      _id: null,
      minScoreAcrossPlayers: { $min: "$worstScore" }
    }
  }
]);
```

The operator name is the same, but **context, syntax, and purpose differ**.

## 5. $max: Update Only When the New Value Is Larger

Syntax:

```javascript
{ $max: { fieldName: candidateValue } }
```

If the candidate value is **greater**, replace the field; if equal or smaller, leave it unchanged. A missing field is created with the candidate value.

### 5.1. Highest Score

```javascript
db.playerStats.updateOne(
  { _id: "player-01" },
  { $max: { bestScore: 950 } }
);

// bestScore: 950

db.playerStats.updateOne(
  { _id: "player-01" },
  { $max: { bestScore: 870 } }
);

// bestScore remains 950.
```

You can track both extrema of the same data stream by updating **two different fields** in one operation:

```javascript
const observedScore = 785;

db.playerStats.updateOne(
  { _id: "player-01" },
  {
    $min: { worstScore: observedScore },
    $max: { bestScore: observedScore },
    $currentDate: { updatedAt: true }
  }
);
```

This makes sense when `worstScore` and `bestScore` share the same numeric type and measurement unit/scale.

### 5.2. Recording the Latest Timestamp

```javascript
db.userActivity.updateOne(
  { _id: "user-01" },
  {
    $max: {
      lastSeenAt: ISODate("2026-04-21T18:45:00Z")
    }
  }
);
```

If an event arrives delayed over the network, `$max` prevents an older event from overwriting `lastSeenAt` with an earlier timestamp.

**Do not confuse `lastSeenAt` from an event timestamp with `updatedAt` written by the server.** When ingesting historical events, an event from last month may be imported today; `lastSeenAt` should reflect the latest known event, whereas `updatedAt` reflects when the record was updated.

## 6. $min/$max Compare Using BSON Order, Even Across Different Types

An important distinction: `$min` and `$max` do not require the two values to share the same numeric type. They use **BSON comparison order** when encountering different types.

Relevant order, from lowest to highest:

```text
MinKey < Null < Number < String < Object < Array < BinData
       < ObjectId < Boolean < Date < Timestamp < ... < MaxKey
```

Example:

```javascript
db.mixedTypeLab.insertOne({
  _id: "demo",
  threshold: null
});

db.mixedTypeLab.updateOne(
  { _id: "demo" },
  { $max: { threshold: 100 } }
);

// Number sorts after Null -> threshold becomes 100.

db.mixedTypeLab.updateOne(
  { _id: "demo" },
  { $min: { threshold: "50" } }
);

// String sorts after Number in BSON -> still keeps Number 100.
```

This **does not mean** `"50"` is automatically converted to the number `50`. If a field mixes String, Double, Date, and Null, the value retained by `$min`/`$max` may no longer make business sense.

Production fields should enforce a **consistent schema**: scores as numeric, prices as Decimal128 or integer minor units, timestamps as BSON Date. Enforce this with MongoDB JSON Schema validation, API validation, or legacy data migrations.

### 6.1. How Does This Differ from $gt/$lt in Filters?

Inequality predicates like `{ score: { $gt: 10 } }` generally apply **type bracketing**: they evaluate values compatible with the operand's type. By contrast, `$min`/`$max` updates can compare **across types** using BSON comparison order.

Therefore, do not infer `$max` behavior from what a `$gt` query returns on mixed-type data. MongoDB does not automatically coerce all BSON types into a single unified type.

## 7. $currentDate: Update Timestamp Written by MongoDB

Syntax:

```javascript
{
  $currentDate: {
    updatedAt: true
  }
}
```

With `true`, MongoDB creates or overwrites the field with the **current BSON Date** at the time of the operation. You can also specify the type explicitly:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $currentDate: {
      updatedAt: { $type: "date" }
    }
  }
);
```

Both forms select BSON Date.

### 7.1. Date and Timestamp Are Two Distinct BSON Types

`$currentDate` supports:

| Syntax | BSON Type Written | Common Purpose |
|---|---|---|
| `{ updatedAt: true }` | Date | Application update timestamp |
| `{ updatedAt: { $type: "date" } }` | Date | Explicitly specify Date type |
| `{ touchTs: { $type: "timestamp" } }` | Timestamp | Specialized cases requiring BSON Timestamp |

Example:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $currentDate: {
      updatedAt: true,
      internalTouchTimestamp: { $type: "timestamp" }
    }
  }
);
```

MongoDB BSON `Date` represents an instant in milliseconds since the Unix epoch and displays as `ISODate(...)` in `mongosh`. BSON `Timestamp` is a specialized internal type commonly seen in replication/oplog contexts; it is not the default choice for purchase dates, expiration dates, or `updatedAt`.

The `updatedAt` field need not already exist: `$currentDate` **creates the field automatically**. If it exists, it **overwrites** it with the current time.

### 7.2. Comparison with Setting new Date() on the Client

Taking the timestamp from the application side:

```javascript
const clientNow = new Date();

db.inventory.updateOne(
  { _id: "SKU-101" },
  { $set: { updatedAt: clientNow } }
);
```

Using `$currentDate`:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  { $currentDate: { updatedAt: true } }
);
```

With `new Date()`, the timestamp is generated at the **client** before sending the command, depending on the client's clock and network latency. With `$currentDate`, the value is determined when MongoDB executes the update. Even so, this is not an absolute global clock guarantee: hosts can experience clock skew, and distributed event ordering still requires explicit ordering/sequence rules.

### 7.3. Updating Status Together with a Timestamp

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" },
    $currentDate: { updatedAt: true }
  }
);
```

The `status: "PAID"` condition prevents invalid state transitions if the order changed concurrently. `$currentDate` records the time **of the status update** within the same document.

If `createdAt` should be set only on **initial insert**, use `$setOnInsert` with an appropriate value or a pipeline/upsert design; never apply `$currentDate` to `createdAt` on every update, as it would overwrite the creation date.

### 7.4. $currentDate Differs from When the Business Event Occurred

Suppose an application receives an event created on day 1 and ingests it into MongoDB on day 3. When storing the event:

- `eventAt` should hold the source timestamp if it has suitable reliability and semantics.
- `receivedAt` or `updatedAt` uses `$currentDate` to record when the system processed it.

These are two different kinds of timestamps and should not be conflated when reporting on actual business event times.

## 8. Combining All Five Operators in One Update

MongoDB allows multiple update operators in the same update document **provided they do not modify conflicting paths**.

Sales statistics example:

```javascript
db.salesStats.insertOne({
  _id: "SKU-101",
  soldUnits: NumberLong("100"),
  revenue: NumberDecimal("125000000.00"),
  minOrderValue: NumberDecimal("50000.00"),
  maxOrderValue: NumberDecimal("2500000.00"),
  lastSaleAt: ISODate("2026-05-01T08:00:00Z")
});
```

When receiving an order for 2 units totaling 1,900,000 with transaction timestamp 2026-05-02:

```javascript
const orderValue = NumberDecimal("1900000.00");
const saleAt = ISODate("2026-05-02T10:30:00Z");

db.salesStats.updateOne(
  { _id: "SKU-101" },
  {
    $inc: {
      soldUnits: NumberLong("2"),
      revenue: orderValue
    },
    $min: { minOrderValue: orderValue },
    $max: {
      maxOrderValue: orderValue,
      lastSaleAt: saleAt
    },
    $currentDate: { updatedAt: true }
  }
);
```

After the operation:

- `soldUnits` increases by 2.
- `revenue` increases by the order value.
- `minOrderValue` retains the smallest value observed.
- `maxOrderValue` retains the largest value.
- `lastSaleAt` advances only if the transaction time is later.
- `updatedAt` records when MongoDB processed the write.

**Note:** this is a single-document statistics example. It does not guarantee an order is processed only once. If a consumer replays the event, `$inc` adds to revenue and unit counts again. Financial figures require unique event IDs, idempotency, reconciliation, and sometimes transactions/outbox patterns.

### 8.1. Do Not Update the Same Field with Two Modifiers

Example to avoid:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  {
    $inc: { stock: 5 },
    $max: { stock: 0 }
  }
);
```

Both modifiers target `stock` in the same update; MongoDB will report **conflicting update paths** rather than adding first and clamping afterward. Similarly, avoid using both `$set` and `$currentDate` on `updatedAt` in one update.

When sequential expressions on the same field are required, use an **aggregation pipeline update** with stages expressing the exact computation.

## 9. When Clamping or Complex Formulas Are Needed: Update Pipelines

The modifiers above offer concise syntax and are usually efficient. However, business rules sometimes require:

- Computing a new value from another field in the same document;
- Clamping a value within a range;
- Falling back to a default when a field is missing/null before computing;
- Applying multiple transformation steps to the same field.

MongoDB supports updates via **aggregation pipelines**. For example, adding 15 points while capping at 100:

```javascript
db.players.updateOne(
  { _id: "player-01" },
  [
    {
      $set: {
        score: {
          $min: [
            100,
            { $add: [{ $ifNull: ["$score", 0] }, 15] }
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
```

Here `$min` is an **aggregation expression**, not the `$min: { score: ... }` update modifier. `$add` sums values, `$ifNull` substitutes `0` when the field is missing/null, and `$$NOW` retrieves the server time for pipeline expressions. On a single document, the calculation and write still execute in a single update operation.

Example discounting by up to 30% while staying at or above `floorPrice`:

```javascript
db.inventory.updateOne(
  { _id: "SKU-101" },
  [
    {
      $set: {
        price: {
          $max: [
            "$floorPrice",
            {
              $multiply: [
                "$price",
                NumberDecimal("0.70")
              ]
            }
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
```

This example assumes `price` and `floorPrice` are both valid existing Decimal128 fields. If data may be missing, add validation or explicit fallbacks. Pipeline computations evaluate more expressions; choose the simplest approach that satisfies business rules.

## 10. Upsert, Missing Fields, and Initial Values

`upsert: true` means that if the filter matches no documents, MongoDB can insert a new document derived from the filter and update according to upsert rules.

```javascript
db.dailyMetrics.updateOne(
  { _id: "2026-05-02" },
  {
    $inc: { views: NumberLong("1") },
    $currentDate: { updatedAt: true },
    $setOnInsert: { createdBy: "metrics-worker" }
  },
  { upsert: true }
);
```

If the document does not exist yet:

- `_id` is taken from the equality filter.
- `views` is initialized to the `$inc` increment.
- `updatedAt` receives the update timestamp.
- `createdBy` is assigned only on creation.

If the document already exists:

- `views` is incremented on top of the current value.
- `updatedAt` is refreshed.
- `$setOnInsert` has no effect.

**Do not apply `$setOnInsert` and `$inc` to the same path to initialize a value two different ways.** For complex initialization logic, move it into a pipeline or explicitly create the document in a separate business step.

### 10.1. Behavior Matrix for Missing Fields and null

| Operator | Missing field | Existing field = `null` |
|---|---|---|
| `$inc: { x: 5 }` | Creates `x = 5` | Error |
| `$mul: { x: 5 }` | Creates `x = 0` matching multiplier numeric type | Not a valid numeric value |
| `$min: { x: 5 }` | Creates `x = 5` | BSON order: Null < Number, keeps `null` |
| `$max: { x: 5 }` | Creates `x = 5` | BSON order: Number > Null, changes to `5` |
| `$currentDate: { x: true }` | Creates current BSON Date | Overwrites with current BSON Date |

This table assumes valid data types and parent paths. Using dot notation into a non-object parent, or violating schema validation, will cause the operation to error.

## 11. Atomicity, Concurrency, and Retries

### 11.1. A Single Document Is the Atomicity Boundary

Consider this update:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-101",
    stock: { $gte: 2 }
  },
  {
    $inc: {
      stock: -2,
      "metrics.sold": 2
    },
    $currentDate: { updatedAt: true }
  }
);
```

If the update succeeds, changes within the same document apply as one atomic operation. Another reader will never observe "stock decremented while metrics.sold not yet incremented" as a partial state of a successful update.

However, if business data spans two documents (e.g., inventory and orders), you still need a multi-document consistency design. `updateMany()` applies updates atomically **per document**, without making the entire collection update all-or-nothing like a transaction.

### 11.2. $inc and $mul Are Not Idempotent

An **idempotent** write is one where repeating the same request produces no further change after the first execution.

| Operation | Does repeating the same operation keep the result unchanged? |
|---|---|
| `$inc: { views: 1 }` | **No**; adds again |
| `$mul: { price: 1.1 }` | **No**; multiplies again |
| `$min: { low: 5 }` | With stable value/type, repeating the same candidate does not lower `low` further |
| `$max: { high: 9 }` | With stable value/type, repeating the same candidate does not raise `high` further |
| `$currentDate: { updatedAt: true }` | **No**; each successful execution writes a new timestamp |

Especially after a client timeout or network drop, do not assume the request failed to execute and blindly resend `$inc`. MongoDB drivers support **retryable writes** under supported conditions with operation tracking, yet systems still need **business-level idempotency** when upstream services, consumers, or jobs can emit duplicate events.

A common pattern is storing a unique `eventId` and updating stats exactly once under a guarded workflow. When recording events and updating stats across two collections, consider transactions or an event-log + deduplicated materialized-view design.

### 11.3. Hot Counters and Throughput

Even though `$inc` is safe for simple increments, thousands of writers incrementing **a single document** concurrently can create write contention. If a counter is merely a view count tolerant of asynchronous aggregation, consider sharding the counter across multiple documents or logging events and aggregating later. Never switch inventory, balances, or financial invariants to eventual consistency without proper safeguards.

## 12. Java and Spring Data MongoDB Examples

The examples below demonstrate using the same update operators from Java applications.

### 12.1. MongoDB Java Sync Driver

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.currentDate;

MongoCollection<Document> inventory =
    database.getCollection("inventory");

int quantity = 2;

UpdateResult result = inventory.updateOne(
    and(
        eq("_id", "SKU-101"),
        gte("stock", quantity)
    ),
    combine(
        inc("stock", -quantity),
        inc("metrics.sold", quantity),
        currentDate("updatedAt")
    )
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException("Insufficient stock or product does not exist");
}
```

The builders `Updates.inc()`, `Updates.mul()`, `Updates.min()`, `Updates.max()`, and `Updates.currentDate()` construct BSON updates via the driver API. Ensure Java numeric types match your BSON schema; for example, represent money using an explicit decimal model rather than silently converting everything to `double`.

### 12.2. Spring Data MongoDB

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
    Criteria.where("_id").is("SKU-101")
            .and("stock").gte(2)
);

Update update = new Update()
    .inc("stock", -2)
    .inc("metrics.sold", 2)
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "inventory"
);
```

Spring Data provides corresponding methods such as `Update.inc()`, `multiply()`, `min()`, `max()`, and `currentDate()` depending on the version. For nested paths or Java fields mapped to different MongoDB field names, verify the actual entity/collection mapping rules.

## 13. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Reading counter then `$set`ting incremented value on client | Lost increments under concurrent writers | Use `$inc` |
| Using `$inc` on a `null` field | Update errors | Normalize data, define numeric defaults |
| Expecting `$mul` on a missing field to set the multiplier | Actually creates `0` | Initialize field properly first or use a pipeline |
| Using `$mul: 0.9` every time a promotion applies | Compounded discounting on retries | Compute from base price, enforce idempotency |
| Using `Double` for money and expecting exact decimal math | Representation and rounding errors | Use Decimal128/integer minor units per contract |
| Using `$min` or `$max` on fields mixing String/Number | Compares by BSON order, wrong arithmetic meaning | Enforce single type via validator/migration |
| Using `$currentDate` on `createdAt` in every update | Overwrites creation timestamp | Set once on insert, refresh only `updatedAt` |
| Confusing BSON Timestamp with BSON Date | Different type and semantics | Use Date for business timestamps |
| Applying `$inc` and `$max` to the same field in one update | Conflicting update paths error | Use a pipeline or separate logic |
| Treating `updateMany()` as a collection-wide transaction | Partial updates possible on error outside transaction | Define proper transaction boundaries |
| Unconditionally retrying `$inc` after timeout | Double counting | Use retryable writes/idempotency/readback |
| Decrementing stock without filter check | Negative inventory | Use conditional atomic updates |

## 14. Practice Exercises

### Exercise 1 — Counters and Stock

Create the document `{ _id: "P1", views: 0, stock: 5 }`. Write:
1. A command to increment `views` by 1.
2. A command to decrement `stock` by 3 only when enough stock remains.
3. Check `matchedCount` and `modifiedCount` after each operation.
4. Explain why you should not read stock on the client and `$set` a new number when multiple requests arrive concurrently.

### Exercise 2 — Price Multiplication and Handling null/Missing

Create three documents with `price` set to `Decimal128("100.00")`, missing `price`, and `price: null`. Test `$mul: { price: NumberDecimal("1.10") }`. Predict and observe the behavior in each case. Then design a business-correct price initialization rule.

### Exercise 3 — Tracking Extrema

A sensor emits values `[22, 18, 26, 21]` in arbitrary order. Create a document with `minValue` and `maxValue`, updating via `$min`/`$max` after each event. Predict the final result. If the sensor could emit String `"18"` instead of a Number, explain why BSON type enforcement matters.

### Exercise 4 — Event Time vs. Update Time

Ingest an event with `eventAt = 2026-01-01` on 2026-01-03. Write an update using:
- `$min` to keep `firstEventAt`;
- `$max` to keep `lastEventAt`;
- `$currentDate` to record `updatedAt`.

Explain why these three fields can hold very different timestamps.

### Exercise 5 — Clamping Scores Within Bounds

The `score` field is currently `95`; you want to add `15` while capping at `100`. Why cannot this be safely expressed by modifying `score` with both `$inc` and `$min` in one update? Write an update pipeline using `$add`, `$min`, and `$$NOW`.

### Exercise 6 — Handling Retries

A consumer replays a "sold two units" event after statistics were already updated, because the first attempt timed out. If the same `$inc` runs again, how does the sold count become incorrect? Propose an `eventId` identifier, a way to verify whether the event was already applied, and an appropriate transaction boundary or asynchronous projection.

## 15. References

- [MongoDB – Update Operators](https://www.mongodb.com/docs/manual/reference/mql/update/)
- [MongoDB – $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB – $mul](https://www.mongodb.com/docs/manual/reference/operator/update/mul/)
- [MongoDB – $min](https://www.mongodb.com/docs/manual/reference/operator/update/min/)
- [MongoDB – $max](https://www.mongodb.com/docs/manual/reference/operator/update/max/)
- [MongoDB – $currentDate](https://www.mongodb.com/docs/manual/reference/operator/update/currentDate/)
- [MongoDB – BSON comparison order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB – Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)

## Conclusion

`$inc` and `$mul` update numeric values directly inside a document; `$min` and `$max` maintain extrema via comparisons; `$currentDate` records the current date/time from MongoDB. What matters goes beyond syntax: remember that **a missing field differs from null**, BSON types affect arithmetic and comparisons, single-document updates are atomic yet resending `$inc`/`$mul` can still corrupt totals, and event timestamps differ from system processing timestamps.

Apply operators according to business boundaries: conditional `$inc` to guard inventory, `$min`/`$max` to track earliest/latest bounds, `$currentDate` to track last modification, and aggregation pipelines when multi-step formulas target the same field. Combined with consistent schemas, appropriate indexes, idempotency, and reconciliation, update operations become both clearer and safer under concurrent load.
