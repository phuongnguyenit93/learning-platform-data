# Grouping AND, OR, NOR, and Properly Scoping Negation

> **Chapter:** Query and Criteria  
> **Module:** `SPRING_DATA_MONGODB`

In MongoDB, logical query bugs rarely lie in a single comparison; they lie in **the scope of grouping and negation**. A proper filter must ensure every `OR` branch is bounded by the tenant, a `NOR` operation does not accidentally negate authorization conditions, and "not X" has an exact meaning when fields are missing or contain `null`.

Spring Data MongoDB provides `Query` and `Criteria` to express these conditions in Java. They allow combining `andOperator(...)`, `orOperator(...)`, `norOperator(...)`, and `not()`, though these methods **do not share the same scope**. This lesson constructs each MongoDB expression first, then converts it into `Criteria`, and tests it against a BSON dataset containing both complete documents and legacy documents with missing fields.

This content belongs to the `SPRING_DATA_MONGODB` module: connecting, mapping documents, and interacting via `MongoTemplate` or repositories; queries form the foundation for aggregation, indexing, transactions, reactive access, testing, and data performance diagnostics.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **implicit AND** across fields, explicit `$and`, `$or`, `$nor`, and `$not`.
2. Place logical parentheses accurately for expressions like `Tenant AND (A OR B) AND NOT(C OR D)`.
3. Use `Criteria.andOperator(...)`, `orOperator(...)`, `norOperator(...)`, and `Criteria.not()` with the proper scope.
4. Distinguish `$nor` from negating an entire `$and` group, applying De Morgan's laws properly.
5. Recognize how `$ne`, `$nin`, `$not`, and `$nor` interact with BSON `null`, missing fields, or arrays.
6. Write safe dynamic filters, tenant-scoped queries, integration tests, and verify indexes/performance.

## 2. Map of MongoDB Logical Operators

| Expression | BSON Syntax | Interpretation |
| --- | --- | --- |
| `A AND B` | `{ a: 1, b: 2 }` | Both fields must match; this is implicit AND |
| Explicit `A AND B` | `{ $and: [ {a: 1}, {b: 2} ] }` | Convenient when grouping multiple expressions |
| `A OR B` | `{ $or: [ {a: 1}, {b: 2} ] }` | At least one branch matches |
| `NOT(A OR B)` | `{ $nor: [ {a: 1}, {b: 2} ] }` | No branch matches |
| `NOT(field satisfies condition)` | `{ score: { $not: { $gte: 100 } } }` | Negates a condition **on a single field** |
| `field != x` | `{ status: { $ne: "PAID" } }` | Negates a value with `$ne` semantics |
| `field not in set` | `{ status: { $nin: ["PAID","NEW"] } }` | Excludes values in the set |

**Keep in mind:** `$not` is a **field-level operator**, not a top-level negation operator for arbitrary document expressions. To negate **one or more complete conditions**, typically use `$nor` with properly grouped branches.

### 2.1. Group by Logical Operation, Not Method Name Length

Consider two expressions:

```text
E1 = TENANT_A AND (STATUS_NEW OR STATUS_PAID)

E2 = (TENANT_A AND STATUS_NEW) OR STATUS_PAID
```

E1 only permits documents belonging to tenant A. E2 can match `STATUS_PAID` documents of **any tenant**, because the second branch contains no tenant condition.

This is a **data access scope expansion bug**, not merely a result-filtering mistake. When building dynamic queries, place `tenantId` as an outer AND condition wrapping the entire business OR group.

## 3. Running Dataset

Suppose the `orders` collection records orders by `tenantId`, `status`, `active`, `fraud`, and `totalMinor`. Some historical records omit `status`/`fraud` to test null/missing behavior.

### 3.1. Seeding Test Data

```javascript
use shop

db.orders.insertMany([
  { _id: "A-01", tenantId: "T-A", status: "NEW",
    active: true, fraud: false, totalMinor: NumberLong(150),
    orderCode: "ORD-01" },

  { _id: "A-02", tenantId: "T-A", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(750),
    orderCode: "ORD-02" },

  { _id: "A-03", tenantId: "T-A", status: "CANCELLED",
    active: true, fraud: false, totalMinor: NumberLong(900),
    orderCode: "ORD-03" },

  { _id: "A-04", tenantId: "T-A", status: "NEW",
    active: true, fraud: true, totalMinor: NumberLong(50),
    orderCode: "ORD-04" },

  { _id: "A-05", tenantId: "T-A", status: "PAID",
    active: false, fraud: true, totalMinor: NumberLong(1200),
    orderCode: "ORD-05" },

  { _id: "A-06", tenantId: "T-A", status: null,
    active: true, fraud: false, totalMinor: NumberLong(1000),
    orderCode: "ORD-06" },

  { _id: "A-07", tenantId: "T-A", /* missing status */
    active: true, /* missing fraud */ totalMinor: NumberLong(300),
    orderCode: "ORD-07" },

  { _id: "A-08", tenantId: "T-A", status: "NEW",
    active: true, fraud: false, totalMinor: NumberLong(350),
    orderCode: "ORD-08" },

  { _id: "A-09", tenantId: "T-A", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(300),
    orderCode: "ORD-09" },

  { _id: "B-01", tenantId: "T-B", status: "PAID",
    active: true, fraud: false, totalMinor: NumberLong(900),
    orderCode: "ORD-B01" }
])
```

Run the seed snippet **only in an isolated test MongoDB**. IDs `A-01` and `B-01` are BSON Strings, and `totalMinor` is BSON Int64.

| ID | Tenant | Status | Active | Fraud | Total |
| --- | --- | --- | --- | --- | ---: |
| A-01 | T-A | NEW | true | false | 150 |
| A-02 | T-A | PAID | true | false | 750 |
| A-03 | T-A | CANCELLED | true | false | 900 |
| A-04 | T-A | NEW | true | true | 50 |
| A-05 | T-A | PAID | false | true | 1200 |
| A-06 | T-A | null | true | false | 1000 |
| A-07 | T-A | *missing* | true | *missing* | 300 |
| A-08 | T-A | NEW | true | false | 350 |
| A-09 | T-A | PAID | true | false | 300 |
| B-01 | T-B | PAID | true | false | 900 |

**Do not confuse "missing field" with a field containing `null`:** they are two distinct BSON documents. Some negation operators still match both because the positive condition fails to match; however, `$exists` can distinguish them.

## 4. Implicit AND and Explicit $and

MongoDB by default combines multiple fields at **the same filter document level** using AND:

```javascript
db.orders.find({
  tenantId: "T-A",
  active: true
})
```

Logically equivalent to:

```javascript
db.orders.find({
  $and: [
    { tenantId: "T-A" },
    { active: true }
  ]
})
```

Both statements return all orders in T-A with `active: true`, including A-01, A-02, A-03, A-04, A-06, A-07, A-08, and A-09.

### 4.1. Criteria for Simple AND

```java
Query query = Query.query(
    Criteria.where("tenantId").is("T-A")
        .and("active").is(true));

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

`mongoTemplate` is an injected `MongoTemplate`. For a simple single-group field filter, `Criteria.where(...).and(...)` requires less boilerplate than `andOperator(...)`.

### 4.2. AND Across Multiple Groups

When complex grouping is required, use:

```java
Criteria tenant = Criteria.where("tenantId").is("T-A");
Criteria active = Criteria.where("active").is(true);
Criteria amount = Criteria.where("totalMinor").gte(300L);

Criteria all = new Criteria().andOperator(
    tenant, active, amount);

Query query = Query.query(all);
```

Equivalent:

```javascript
{
  $and: [
    { tenantId: "T-A" },
    { active: true },
    { totalMinor: { $gte: NumberLong(300) } }
  ]
}
```

**Do not create two entries with the same field name in a single JSON object** to express two conditions. In Java, patterns like `new Document("totalMinor", ...).append("totalMinor", ...)` overwrite the earlier key; when calling `Query.addCriteria` with two `Criteria` sharing the same key, Spring Data may also reject it for duplicate keys.

For **the same field**, chain operators within one `Criteria`:

```java
Criteria range = Criteria.where("totalMinor")
    .gte(300L)
    .lt(1000L);
```

Or use `new Criteria().andOperator(...)` when two logical groups must both hold simultaneously yet cannot be merged into a single field object.

## 5. OR: Placing Alternatives in the Right Scope

Requirement: orders belonging to tenant T-A with **status NEW or PAID**.

### 5.1. Exact BSON

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ]
})
```

Unordered results: **A-01, A-02, A-04, A-05, A-08, A-09**. B-01 is `PAID` but belongs to T-B, so it is excluded.

All elements inside `$or` are **independent conditions**. With different filters on different fields, `$or` can be more appropriate than `$in` on a single field.

### 5.2. Spring Data Criteria.orOperator

```java
Criteria statusChoices = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    statusChoices);

List<OrderDocument> result = mongoTemplate.find(
    Query.query(scoped), OrderDocument.class);
```

Standard Spring Data mapping converts enum `OrderStatus.NEW`/`PAID` to the string stored in BSON. Field names in `Criteria` are Java properties when using `MongoTemplate` entity mapping; if `@Field` renames a field, the mapper handles the corresponding translation.

For multiple values on **the same field**, you can write it more concisely:

```java
Query query = Query.query(
    Criteria.where("tenantId").is("T-A")
        .and("status")
        .in(OrderStatus.NEW, OrderStatus.PAID));
```

`$in` and an `$or` of equalities on **a single scalar field** usually carry the same value-set selection semantics; however, they are not identical in every situation (especially when each OR branch involves multiple fields or expressions).

### 5.3. OR Example on Two Different Properties

Requirement: T-A and (**status NEW or totalMinor 900 or above**).

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { totalMinor: { $gte: NumberLong(900) } }
  ]
})
```

Results: **A-01, A-03, A-04, A-05, A-06, A-08**. A-06 has `status: null` but amount 1000, so it matches the amount branch.

This example demonstrates that OR is a **union**. A document only needs to satisfy **one** of the branches, yet must still satisfy the outer **tenant condition**.

## 6. NOR: Negating *an Entire OR Group*

`$nor` selects documents where **none of the conditions in the list match**:

```text
NOR(A, B)  =  NOT(A OR B)
           =  (NOT A) AND (NOT B)
```

Suppose we need T-A orders that are **neither cancelled** nor **flagged as fraud**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $nor: [
    { status: "CANCELLED" },
    { fraud: true }
  ]
})
```

Results: **A-01, A-02, A-06, A-07, A-08, A-09**.

Why do A-06 and A-07 still appear? `status: null` or a missing `status` field does not match `status: "CANCELLED"`; a missing `fraud` field likewise does not match `fraud: true`. Thus **no branch of NOR matches**, so the documents are included.

### 6.1. Criteria.norOperator

```java
Criteria excluded = new Criteria().norOperator(
    Criteria.where("status").is(OrderStatus.CANCELLED),
    Criteria.where("fraud").is(true));

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    excluded);

Query query = Query.query(scoped);
List<OrderDocument> result = mongoTemplate.find(
    query, OrderDocument.class);
```

### 6.2. Limiting the Scope of Negation

**Correct:**

```text
(tenantId = T-A) AND NOT(status = CANCELLED OR fraud = true)
```

**Wrong in a multi-tenant system:**

```text
NOT(tenantId = T-A OR status = CANCELLED OR fraud = true)
```

The second expression does not merely "exclude bad orders in tenant A"; it negates the tenant condition itself and can **select other tenants**. Never put security constraints inside a negated group expecting those constraints to remain enforced.

### 6.3. NOR Differs from NOT of an AND Group

Two formulas:

```text
X = NOT(A OR B)  = (NOT A) AND (NOT B)
Y = NOT(A AND B) = (NOT A) OR  (NOT B)
```

**Not equivalent.** If A is true and B is false, X is false while Y is true.

For example, suppose we want to exclude documents that **simultaneously** have `status PAID` **and** `fraud true`, meaning:

```text
NOT(status = PAID AND fraud = true)
```

Express this by negating a **closed AND group**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $nor: [
    {
      $and: [
        { status: "PAID" },
        { fraud: true }
      ]
    }
  ]
})
```

Do not write `$nor: [{status:"PAID"}, {fraud:true}]` for this requirement. That excludes every document that is PAID **or** fraud true, which is much broader.

Spring Data:

```java
Criteria both = new Criteria().andOperator(
    Criteria.where("status").is(OrderStatus.PAID),
    Criteria.where("fraud").is(true));

Criteria notBoth = new Criteria().norOperator(both);

Criteria scoped = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    notBoth);
```

Note: `norOperator` requires at least one valid expression; do not construct an empty group from input data and expect the framework to infer business intent.

## 7. $not Negates Only *One Condition on a Field*

`$not` is placed **inside a field**:

```javascript
db.orders.find({
  totalMinor: { $not: { $gte: NumberLong(300) } }
})
```

It selects documents whose `totalMinor` **does not satisfy** `$gte: 300`. With the current seed dataset (where all documents have an amount), that yields A-01 and A-04. If a document is **missing totalMinor**, that document can also match `$not` because it fails the positive comparison.

### 7.1. Criteria.not()

```java
Criteria amountNotLarge = Criteria
    .where("totalMinor")
    .not()
    .gte(300L);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("T-A"),
        amountNotLarge));
```

Spring Data uses `not()` to negate **the next operator on the same field**. It does not apply to a complete `Query` and should not be used to "put NOT in front of an orOperator". For instance, calling `not().orOperator(...)` is not valid syntax for negating an OR group in the Criteria API; use `norOperator(...)`.

### 7.2. With Regex

```javascript
db.orders.find({
  orderCode: { $not: /^TEST-/i }
})
```

Semantically equivalent to:

```java
import java.util.regex.Pattern;

Criteria notTestOrder = Criteria
    .where("orderCode")
    .not()
    .regex(Pattern.compile("^TEST-", Pattern.CASE_INSENSITIVE));
```

This is a **condition on the `orderCode` field**, not a negation of the whole BSON document. `$not` with a regex can match documents **missing the `orderCode` field**. If business rules require the order code to exist and not start with TEST, add appropriate existence/data-type conditions.

### 7.3. $not, $ne, $nin, and $nor: When to Use Which?

| Intent | Preferred Expression | Caution |
| --- | --- | --- |
| Field differs from value X | `$ne` | Often matches missing fields too; watch `null` closely |
| Field not in set [X,Y] | `$nin` | Can match missing fields; empty set is very broad |
| Negate one comparison/regex on a field | `$not` | Does not negate the entire query |
| Negate at least one whole-document condition group | `$nor` | Branches must be grouped properly per De Morgan |
| Must belong to an **allowed** set of statuses | `$in` | Fail-closed with an empty allowlist |

For example, `{ status: { $ne: "PAID" } }` on T-A data matches both `status: null` and documents missing `status`. If you want **only specific valid values**, use `$in: ["NEW", "CANCELLED"]` rather than negating PAID and assuming all remaining values are valid.

## 8. Logical Parentheses Blueprint: Combining AND, OR, and NOR

A common business filter:

> Retrieve only tenant T-A orders that are active, have status NEW or PAID, total amount 300 or higher, and are neither cancelled nor flagged as fraud.

Write out the logical expression before translating to Java:

```text
T = tenantId = "T-A"
A = active = true
S = (status = NEW OR status = PAID)
M = totalMinor >= 300
E = NOT(status = CANCELLED OR fraud = true)

Desired result = T AND A AND S AND M AND E
```

Complete BSON expression:

```javascript
db.orders.find({
  $and: [
    { tenantId: "T-A" },
    { active: true },
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    },
    { totalMinor: { $gte: NumberLong(300) } },
    {
      $nor: [
        { status: "CANCELLED" },
        { fraud: true }
      ]
    }
  ]
})
```

On the sample dataset, the result is **A-02, A-08, A-09**. Other records fail at least one condition: A-01 is below the amount threshold, A-04 is below the threshold and flagged as fraud, A-05 is inactive, A-03 is cancelled, A-06/A-07 lack an allowed status, and B-01 belongs to another tenant.

### 8.1. Writing with Criteria

```java
Criteria allowed = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria excluded = new Criteria().norOperator(
    Criteria.where("status").is(OrderStatus.CANCELLED),
    Criteria.where("fraud").is(true));

Criteria filter = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    Criteria.where("active").is(true),
    allowed,
    Criteria.where("totalMinor").gte(300L),
    excluded);

Query query = Query.query(filter);
List<OrderDocument> matched = mongoTemplate.find(
    query, OrderDocument.class);
```

Here `OrderStatus` and `OrderDocument` are the Java types illustrated later; `mongoTemplate` must be properly injected as an application bean. `Criteria` represents groups like parentheses in a formula, making code review easier than inspecting a multi-branch concatenated query string.

### 8.2. Grouping Order and Authorization

A system may let users build arbitrary filters via a UI. Always distinguish:

- **Mandatory constraints:** `tenantId`, permission scope, soft-delete policy, and data-protection rules.
- **Selection conditions:** status, amount, order type, tags, time range.
- **Exclusion conditions:** fraud flags, forbidden statuses, or data-quality cases.

Place **mandatory constraints in the outermost AND group**. Every input-driven OR or NOR branch must reside inside that scope. However, merely putting `tenantId` in a query **does not authenticate access**: the service must resolve the permitted `tenantId` from the caller's identity/authorization before calling the repository.

## 9. Negation on Null Data and Missing Fields

MongoDB does not apply simple two-valued logic across all comparisons when data can be missing or `null`. Positive vs. negative evaluation also depends on BSON type and the operator used.

### 9.1. Concrete Result Table

For comparison, always keep `tenantId: "T-A"` outside the condition under evaluation:

| Condition | T-A IDs Matched | Special Reason |
| --- | --- | --- |
| `status: "PAID"` | A-02, A-05, A-09 | Only PAID status |
| `status: { $ne: "PAID" }` | A-01, A-03, A-04, A-06, A-07, A-08 | Accepts both null and missing field |
| `$nor: [{status:"PAID"}]` | A-01, A-03, A-04, A-06, A-07, A-08 | Does not match the PAID branch |
| `status: { $in: ["NEW","PAID"] }` | A-01, A-02, A-04, A-05, A-08, A-09 | Allowlist |
| `status: { $exists:true, $ne:null }` | A-01, A-02, A-03, A-04, A-05, A-08, A-09 | Excludes A-06 null and A-07 missing |
| `$nor: [{status:"CANCELLED"}, {fraud:true}]` | A-01, A-02, A-06, A-07, A-08, A-09 | Not cancelled and not fraud true |
| `$nor: [{status:{$exists:true}}]` | A-07 | Only when status field does not exist |

**Important:** `status: null` and `status: { $exists: false }` do not have the same meaning. Querying `{ status: null }` under MongoDB rules typically matches **both null and missing fields**. If you need **BSON null only while the field is present**, combine with `$exists: true` or check `$type: "null"` as needed.

### 9.2. Do Not Accidentally Turn Negation into an Allowlist

Suppose the current application enum only has `NEW`, `PAID`, `CANCELLED`. The filter:

```javascript
{ status: { $ne: "CANCELLED" } }
```

**Is not synonymous** with:

```javascript
{ status: { $in: ["NEW", "PAID"] } }
```

The first also matches `null`, missing, and another status like `REFUNDED` added by a newer version. In security filters or business decisions with a clear set of allowed statuses, **positive filtering with `$in`** is usually safer than negating a few forbidden statuses.

### 9.3. Check Field Existence Before Negating

If the requirement is "has a recorded status and is not CANCELLED", you can express it as:

```javascript
{
  status: {
    $exists: true,
    $ne: null,
    $nin: ["CANCELLED"]
  }
}
```

In Java:

```java
Criteria status = Criteria.where("status")
    .exists(true)
    .ne(null)
    .nin(OrderStatus.CANCELLED);
```

With the sample dataset, the query for tenant A returns `A-01, A-02, A-05, A-08, A-09`. Yet in a database with historical enum values unknown to the new application, that condition can still match statuses **other than CANCELLED** that are unrecognized. When the requirement is "only NEW or PAID", using `in(NEW, PAID)` directly is clearer and stricter.

### 9.4. Do Not Apply Negation to Mismatched Field Types

If BSON contains `fraud: "false"` as a String from an older version, that is **not** BSON Boolean `false`. The query `{ fraud: { $ne: true } }` will still match this string, which does not prove the order passed fraud screening and was validly marked false.

The proper solution is to define a data-type contract, audit legacy records, and run migrations; do not use `$nor`/`$ne` to mask schema inconsistencies.

## 10. Grouping on the Same Field, Multiple ORs, and Query.addCriteria Limits

### 10.1. Never Overwrite Keys in JSON

This example is **invalid for the intended logic**:

```javascript
// ANTI-PATTERN: duplicate $or key in one object.
{
  $or: [{ status: "NEW" }, { status: "PAID" }],
  $or: [{ fraud: false }, { active: true }]
}
```

In a JavaScript/BSON document, a repeated key can cause the first expression to be overwritten or trigger unexpected behavior. MongoDB also discourages constructing documents with duplicate field names. Similarly, calling `query.addCriteria(or1)` followed by `query.addCriteria(or2)` when both share the `$or` key can be rejected by Spring Data due to duplicate criteria.

If the intent is **(NEW OR PAID) AND (fraud=false OR active=true)**, use an `$and` group containing **two separate `$or` groups**:

```javascript
db.orders.find({
  tenantId: "T-A",
  $and: [
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    },
    {
      $or: [
        { fraud: false },
        { active: true }
      ]
    }
  ]
})
```

Spring Data:

```java
Criteria statusOr = new Criteria().orOperator(
    Criteria.where("status").is(OrderStatus.NEW),
    Criteria.where("status").is(OrderStatus.PAID));

Criteria flagOr = new Criteria().orOperator(
    Criteria.where("fraud").is(false),
    Criteria.where("active").is(true));

Criteria filter = new Criteria().andOperator(
    Criteria.where("tenantId").is("T-A"),
    statusOr,
    flagOr);
```

### 10.2. Why AND/OR Inside an Array Differs from AND on Nested Fields

Suppose a document contains an array:

```javascript
{
  _id: "O-ARRAY",
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 9 }
  ]
}
```

Query:

```javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 5 }
})
```

**Matches this document** because `sku=A` is satisfied by the first element, while `qty>=5` is satisfied by the second element. Two AND conditions on array dot paths **do not automatically require the same element**.

If you need the same element to satisfy `sku=A AND qty>=5`:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
})
```

This query **does not match** `O-ARRAY`. In `Criteria`, use `elemMatch(...)` to scope conditions onto **a single array element**. This is also a form of "proper scoping with parentheses", alongside document-level AND/OR/NOR.

## 11. Java Model and Tenant-Scoped Service

### 11.1. Entity and Enum

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    OrderStatus status,
    Boolean active,
    Boolean fraud,
    Long totalMinor,
    String orderCode
) {}
```

`Boolean` and `Long` are used instead of primitives so missing/`null` data is not conflated with a default value. In newer business logic, fields can be required non-null and validated at write boundaries; this model allows reading legacy data for demonstration.

### 11.2. Fail-Closed Dynamic Filter

Suppose a screen accepts:

- `allowedStatuses`: permitted statuses to choose from; **empty = no results**.
- `includeHighValueNew`: whether to also include NEW orders at or above the amount threshold.
- `excludeFraudAndCancelled`: whether to exclude orders flagged as fraud or CANCELLED.
- `tenantId`: tenant resolved by the service from an authorized user.

File `OrderSearchService.java`:

```java
package com.example.shop.orders;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {

    private final MongoTemplate template;

    public OrderSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> search(
            String permittedTenantId,
            Collection<OrderStatus> allowedStatuses,
            boolean includeHighValueNew,
            long minimumAmount,
            boolean excludeFraudAndCancelled) {

        Objects.requireNonNull(
            permittedTenantId, "permittedTenantId");
        Objects.requireNonNull(
            allowedStatuses, "allowedStatuses");

        if (permittedTenantId.isBlank()) {
            throw new IllegalArgumentException("Blank tenant");
        }
        if (allowedStatuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "Allowed statuses must not contain null");
        }
        if (minimumAmount < 0) {
            throw new IllegalArgumentException(
                "minimumAmount must be non-negative");
        }

        List<Criteria> alternatives = new ArrayList<>();

        if (!allowedStatuses.isEmpty()) {
            alternatives.add(
                Criteria.where("status").in(allowedStatuses));
        }
        if (includeHighValueNew) {
            alternatives.add(new Criteria().andOperator(
                Criteria.where("status").is(OrderStatus.NEW),
                Criteria.where("totalMinor").gte(minimumAmount)
            ));
        }

        // No permitted options: do not hit the database.
        if (alternatives.isEmpty()) {
            return List.of();
        }

        List<Criteria> required = new ArrayList<>();
        required.add(
            Criteria.where("tenantId").is(permittedTenantId));

        required.add(new Criteria().orOperator(
            alternatives.toArray(new Criteria[0])));

        if (excludeFraudAndCancelled) {
            required.add(new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)
            ));
        }

        Criteria filter = new Criteria().andOperator(
            required.toArray(new Criteria[0]));

        Query query = Query.query(filter)
            .with(Sort.by(
                Sort.Order.desc("totalMinor"),
                Sort.Order.desc("id")))
            .limit(50);

        return template.find(query, OrderDocument.class);
    }
}
```

**Tenant scope is always in the outermost AND group.** Two OR branches are added depending on inputs, yet neither branch can "escape" `tenantId`. The no-options path returns `List.of()` without issuing an unexpectedly broad query.

The limit of `50` merely illustrates endpoint protection; in practice, configure limits from product requirements and proper pagination. Do not use a 50-item result as complete history for data exports.

**Regarding security:** `permittedTenantId` must be derived from or verified against user identity/authorization. The word "permitted" in a parameter name does **not** by itself prove authorization.

### 11.3. Watch the Difference Between OR and Business Conjunction

In the service just written, a document matching **any** branch in `alternatives` is selected, and must still satisfy all other AND constraints. If the product wants "select statuses in allowlist **and simultaneously** meet the amount threshold", do not use OR; put the threshold condition into the AND group.

Breaking prose requirements into explicit logical operations **before coding** prevents bugs the compiler cannot catch.

## 12. Integration Testing Logical Groups with Real BSON

Unit tests mocking `MongoTemplate` only prove the service called a method; they do not verify Spring Data's final filter or how MongoDB evaluates `$nor` when fields are missing. Therefore, use a dedicated test MongoDB instance, inserting BSON via the Java driver to produce **true null and missing fields**.

### 12.1. JUnit 5 Fixture

File `LogicalCriteriaIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class LogicalCriteriaIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static Document order(
            String id, String tenant,
            String status, Boolean fraud,
            boolean active, long total) {

        Document d = new Document("_id", id)
            .append("tenantId", tenant)
            .append("active", active)
            .append("totalMinor", total)
            .append("orderCode", "ORD-" + id);

        if (status != null) {
            d.append("status", status);
        }
        if (fraud != null) {
            d.append("fraud", fraud);
        }
        return d;
    }

    private static List<String> ids(List<OrderDocument> items) {
        return items.stream().map(OrderDocument::id).toList();
    }

    private List<String> findIds(Criteria criteria) {
        return ids(template.find(
            Query.query(criteria), OrderDocument.class));
    }

    @BeforeEach
    void seed() {
        // Delete data ONLY in an isolated test database.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        Document nullStatus = order(
            "A-06", "T-A", null, false, true, 1000)
            .append("status", null);

        Document missingStatusAndFraud = order(
            "A-07", "T-A", null, null, true, 300);

        collection.insertMany(List.of(
            order("A-01", "T-A", "NEW", false, true, 150),
            order("A-02", "T-A", "PAID", false, true, 750),
            order("A-03", "T-A", "CANCELLED", false, true, 900),
            order("A-04", "T-A", "NEW", true, true, 50),
            order("A-05", "T-A", "PAID", true, false, 1200),
            nullStatus,
            missingStatusAndFraud,
            order("A-08", "T-A", "NEW", false, true, 350),
            order("A-09", "T-A", "PAID", false, true, 300),
            order("B-01", "T-B", "PAID", false, true, 900)
        ));
    }

    @Test
    void orGroupStaysInsideTenantScope() {
        Criteria allowed = new Criteria().orOperator(
            Criteria.where("status").is(OrderStatus.NEW),
            Criteria.where("status").is(OrderStatus.PAID));

        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            allowed);

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-04", "A-05",
                "A-08", "A-09")
            .doesNotContain("B-01");
    }

    @Test
    void norExcludesEitherConditionButKeepsMissingFields() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-06",
                "A-07", "A-08", "A-09");
    }

    @Test
    void norOfAndIsDifferentFromNorOfIndividualTerms() {
        Criteria paidAndFraud = new Criteria().andOperator(
            Criteria.where("status").is(OrderStatus.PAID),
            Criteria.where("fraud").is(true));

        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            new Criteria().norOperator(paidAndFraud));

        // Only A-05 is simultaneously PAID and fraud=true.
        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-03", "A-04",
                "A-06", "A-07", "A-08", "A-09");
    }

    @Test
    void notPaidIncludesNullAndMissingStatus() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            Criteria.where("status").ne(OrderStatus.PAID));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-01", "A-03", "A-04",
                "A-06", "A-07", "A-08");
    }

    @Test
    void nestedAndOrNorSelectsOnlyIntendedOrders() {
        Criteria filter = new Criteria().andOperator(
            Criteria.where("tenantId").is("T-A"),
            Criteria.where("active").is(true),
            new Criteria().orOperator(
                Criteria.where("status").is(OrderStatus.NEW),
                Criteria.where("status").is(OrderStatus.PAID)),
            Criteria.where("totalMinor").gte(300L),
            new Criteria().norOperator(
                Criteria.where("status")
                    .is(OrderStatus.CANCELLED),
                Criteria.where("fraud").is(true)));

        assertThat(findIds(filter))
            .containsExactlyInAnyOrder(
                "A-02", "A-08", "A-09");
    }
}
```

Here `OrderStatus`/`OrderDocument` are the two types from section 11. The test uses `MongoTemplate.getCollection("orders")` to insert raw BSON, so A-06 has `status: null` while A-07 truly **lacks the `status` and `fraud` fields**.

**Execution warning:** `collection.deleteMany(new Document())` wipes the entire `orders` collection of whichever database the test connects to. The test must be configured to point to an **isolated** test MongoDB, such as Testcontainers—never a production or shared database. `@DataMongoTest` needs the package import matching your actual Spring Boot version; the example uses the common namespace in supported Spring Boot releases.

### 12.2. Proactively Detecting a Mis-Scoped OR Group

**Counter-example:**

```java
Criteria unsafe = new Criteria().orOperator(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("T-A"),
        Criteria.where("status").is(OrderStatus.NEW)),
    Criteria.where("status").is(OrderStatus.PAID));
```

The bug is that the `status = PAID` branch omits `tenantId = T-A`. Run against the same fixture, this query returns **B-01**. You can write a negative test to deliberately demonstrate the bug before fixing it:

```java
// COUNTER-EXAMPLE: this is a broken query, used only to illustrate the bug.
assertThat(findIds(unsafe)).contains("B-01");
```

Then fix it by placing `tenantId` in the outermost AND group as in `orGroupStaysInsideTenantScope`. In security testing, do not merely assert that expected IDs appear; also assert that **no documents from other tenants** are present in the results.

### 12.3. Additional Matrix for Real Data

| Scenario | Expectation to Verify |
| --- | --- |
| `fraud` is BSON Boolean false | Not excluded by `$nor: [{fraud:true}]` |
| `fraud` is missing or null | Distinguished from false per business policy |
| `status` is missing | Can match `$ne`/`$nor`; does not match string allowlist |
| `status` is a String absent from new enum | MongoDB query runs on BSON; handle reading converter when materializing results |
| Two `$or` groups must both hold | Must be placed inside `$and`, not duplicate `$or` keys |
| Multiple conditions on one array element | `$elemMatch` instead of just AND across dotted paths |
| Empty allowlist input | Fail-closed: return empty results or input error, do not drop filter |
| User-selected OR + mandatory tenant | All branches remain inside the authorized tenant |
| `$nor` group with no branches | Service handles separately, does not build an ambiguous query |
| MongoDB with large data | Measure `explain` and examined document counts, not just tiny fixtures |

## 13. Indexes and Cost of OR/NOR Groups

`$and`, `$or`, and `$nor` are logical operators. They **do not guarantee** MongoDB will use indexes in the same way.

### 13.1. AND and Compound Indexes

If typical queries always scope by `tenantId`, then filter `status` and `totalMinor`, consider an index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  totalMinor: -1,
  _id: -1
})
```

This is only a **candidate index**. When a query uses OR with multiple status values, or sorts differently from the index order, MongoDB may need multiple index scan branches or an extra sort stage. Test the plan on a representative dataset rather than guessing from Java method names.

### 13.2. OR and Per-Branch Indexes

MongoDB can optimize `$or` using indexes when the branches and conditions permit. If one branch has low selectivity or lacks a useful index, the overall plan may need to read many documents.

Example:

```javascript
db.orders.find({
  tenantId: "T-A",
  $or: [
    { status: "NEW" },
    { totalMinor: { $gte: NumberLong(900) } }
  ]
})
```

Do not assume a single index on `status` makes this entire query efficient. Consider `totalMinor`, selectivity, index key order, and tenant distribution.

### 13.3. NOR and Negation Conditions Often Have Low Selectivity

`$nor`, `$ne`, and `$nin` can match most documents, including missing fields. An index on a negated field does **not** guarantee a small result set or low cost.

If the business requirement has a defined set of allowed statuses, `$in` with an allowlist can be both stricter and easier to optimize than negating a few forbidden values. However, final performance must still be **measured**.

### 13.4. Inspecting explain

```javascript
db.orders.find({
  tenantId: "T-A",
  active: true,
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ],
  $nor: [
    { fraud: true },
    { status: "CANCELLED" }
  ]
})
.sort({ totalMinor: -1, _id: -1 })
.limit(20)
.explain("executionStats")
```

Inspect `totalDocsExamined`, `totalKeysExamined`, `nReturned`, index/sort stages, and execution time. A `find` query may run fast on a 10-document fixture yet crawl on millions of documents, especially when negation conditions lack selectivity.

With `MongoTemplate`/repositories, inspect **the actual BSON command sent to the driver** via command monitoring/logging when diagnosing issues; `Query.getQueryObject()` prior to mapping may not reflect final BSON field names and custom conversions.

## 14. Options with Repositories, @Query, and Reactive Access

`MongoTemplate` fits well when building optional AND/OR/NOR groups. Static queries, however, can also be written using repository `@Query`:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("""
        {
          'tenantId': ?0,
          '$or': [
            { 'status': 'NEW' },
            { 'status': 'PAID' }
          ],
          '$nor': [
            { 'status': 'CANCELLED' },
            { 'fraud': true }
          ]
        }
        """)
    List<OrderDocument> findAllowedNotFlagged(String tenantId);
}
```

This assumes `MongoRepository` is also imported and uses Java text blocks (Java 15+). When conditions vary heavily by input, write `Criteria` instead of creating dozens of `@Query` variants. Field names in the string and BSON enum representations should be verified against the application's mapping configuration.

With **reactive access**, `ReactiveMongoTemplate` also accepts `Query`/`Criteria`:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

public Flux<OrderDocument> findByLogicalFilter(
        ReactiveMongoTemplate reactiveTemplate,
        String tenantId) {

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        new Criteria().orOperator(
            Criteria.where("status").is(OrderStatus.NEW),
            Criteria.where("status").is(OrderStatus.PAID)),
        new Criteria().norOperator(
            Criteria.where("fraud").is(true),
            Criteria.where("status")
                .is(OrderStatus.CANCELLED)));

    return reactiveTemplate.find(
        Query.query(filter), OrderDocument.class);
}
```

The snippet above is a method placed in an appropriate Java service/class with `Criteria`, `Query`, and `OrderStatus` imported. Using the reactive template **does not change MongoDB semantics** and does not automatically make a large query cheap. Test reactive queries with `StepVerifier` or equivalent tools, verifying the publisher is subscribed to and no other tenant appears.

Writing across multiple documents in a transaction or aggregating status reports are separate concerns; correct AND/OR/NOR logic is still required in those operations, though choosing transactions or aggregation does not substitute for proper logical grouping.

## 15. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| OR query returns documents from another tenant | `tenantId` is only inside one OR branch | Put tenant in the outermost AND group and write an anti-leak test |
| `$nor` returns documents missing `fraud` | Missing field does not match `fraud:true` | Define missing/null policy; add existence/allowlist conditions |
| Using NOR to negate an AND group excludes too much | Wrote `$nor:[A,B]` instead of `$nor:[{$and:[A,B]}]` | Apply De Morgan's law, test A true / B false |
| `Criteria.not().orOperator(...)` fails to work | `not()` is field-level, does not negate an OR group | Use `norOperator(...)` |
| Query contains two `$or` keys | Duplicate JSON/BSON key or duplicate key in `addCriteria` | Group two separate ORs inside `$and` |
| `$ne: "PAID"` returns null/missing statuses | Negation on values rather than an allowlist | Use `$in` with allowed statuses |
| Array filter disagrees with "same element" requirement | Dotted paths can match across different elements | Use `$elemMatch` |
| Query is slow despite having an index | Low-selectivity OR/NOR group, mismatched index | Run `explain` and bound tenant/sort/limit |
| New query misses old data | Inconsistent BSON field types | Audit schema and migrate, test with raw BSON |
| Empty optional condition widens query | Service drops allowlist or creates empty group | Fail-closed, clear validation, skip DB call when unauthorized |

## 16. Practical Exercise

A ticketing system stores a `tickets` collection with:

- `tenantId`: mandatory tenant.
- `status`: `OPEN`, `CONFIRMED`, `CANCELLED`, possibly missing in old data.
- `priority`: integer.
- `fraudFlag`: boolean.
- `lines`: array of ticket items with `eventCode` and `quantity`.

Implement the following requirements:

1. Retrieve tenant T-A tickets satisfying **(status OPEN or CONFIRMED) and priority 5 or higher**.
2. Retrieve tickets that are **not** simultaneously status CONFIRMED and fraudFlag true, still scoped to tenant T-A.
3. Rewrite item 2 using `$nor` with **one `$and` group**; prove why `$nor` of two independent branches is wrong.
4. If `fraudFlag` is missing on an old ticket, should that ticket pass `$nor:[{fraudFlag:true}]`? State your business decision and write the appropriate query.
5. Write a query finding tickets with **one `lines` element** having `eventCode="E1"` and `quantity>=2`. Compare results against AND over two dotted paths.
6. Write an integration test with at least one ticket from another tenant, one missing `status`, and one with `fraudFlag:null`.
7. Propose an index for the primary query and inspect `explain("executionStats")` on a representative dataset.

**Hints:** for item 1, put `tenantId` at the outer level, add `new Criteria().orOperator(...)` for status and `priority>=5` inside `andOperator(...)`. For item 2, use `norOperator(new Criteria().andOperator(...))`. For arrays, `elemMatch` expresses "same element". Do not treat missing `fraudFlag` as verified `false` unless business rules explicitly state so.

## 17. References

- Spring Data MongoDB — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria`, operators, and `MongoTemplate`.
- Spring Data MongoDB — [Criteria API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `andOperator`, `orOperator`, `norOperator`, and `not`.
- MongoDB Manual — [`$and`](https://www.mongodb.com/docs/manual/reference/operator/query/and/), [`$or`](https://www.mongodb.com/docs/manual/reference/operator/query/or/), [`$nor`](https://www.mongodb.com/docs/manual/reference/operator/query/nor/), and [`$not`](https://www.mongodb.com/docs/manual/reference/operator/query/not/).
- MongoDB Manual — [`$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/): multiple conditions that must match within the same array element.
- MongoDB Manual — [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): distinguishing existing fields from missing fields.

## Key Takeaways

**AND** can be implicit across fields or explicit via `$and`; **OR** selects documents matching at least one branch; **NOR** negates **the entire OR**; and **`$not` negates only a single field's condition**. Do not confuse `NOT(A AND B)` with `NOT(A OR B)`. Always place **tenant and mandatory constraints in the outer AND group**, handle null/missing using explicit business conventions, use `$elemMatch` for conditions on the same array element, test against real BSON, and measure indexes before deploying queries to production.
