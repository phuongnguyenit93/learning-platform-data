# Building Optional Filters and Controlling User-Selected Fields in Query and Criteria

## 1. The Problem: One Search API, Many Condition Combinations

In a **Spring Data MongoDB** application, search requirements rarely have a single fixed set of conditions. An orders screen may let users choose status, customer, amount range, creation date range, tags, keywords, sort order, and which columns to display. Selected conditions vary per request, yet the API must stay **logically sound, safe against untrusted input, and performant at scale**.

For example:

```text
GET /orders?status=PAID&minTotalCents=10000&from=2026-01-01T00:00:00Z
           &sortBy=createdAt&direction=desc&page=0&size=20
```

Another request filters only by customer:

```text
GET /orders?customerId=C-01&page=0&size=20
```

If you write a repository method for every combination, the method count explodes quickly. `MongoTemplate` with `Query` and `Criteria` allows **building controlled dynamic queries** by adding only the conditions actually supplied.

This lesson belongs to the **Query and Criteria** chapter of module `SPRING_DATA_MONGODB` and focuses on two skills:

1. **Building optional filters:** never confusing an absent parameter with `false`, `0`, or an empty string; properly combining `AND`, `OR`, range, array, and text search conditions.
2. **Controlling user-selected fields:** allowing searching, sorting, or projecting only on approved fields; never splicing client-sent field names, MongoDB operators, or raw BSON queries directly.

Beyond reading, writing, and mapping documents via `MongoTemplate`/repositories, how you construct queries impacts **indexes, pagination, transactions, multi-tenant security, integration tests, and slow-query diagnostics**.

## 2. Data Model Used in This Lesson

### 2.1. Sample MongoDB Documents

Use an `orders` collection in a test database, storing monetary amounts in **the smallest unit (cents)** and timestamps in UTC:

```javascript
db.orders.insertMany([
  {
    _id: "O-101",
    tenant_id: "T-A",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(15500),
    buyer_name: "An",
    tags: ["vip", "online"],
    archived: false,
    created_at: ISODate("2026-01-05T10:00:00Z")
  },
  {
    _id: "O-102",
    tenant_id: "T-A",
    customer_id: "C-02",
    status: "NEW",
    total_cents: NumberLong(6500),
    buyer_name: "Lan Anh",
    tags: ["online"],
    archived: false,
    created_at: ISODate("2026-01-06T10:00:00Z")
  },
  {
    _id: "O-103",
    tenant_id: "T-A",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(21000),
    buyer_name: "ANNA",
    tags: ["vip", "retail"],
    archived: true,
    created_at: ISODate("2026-01-08T10:00:00Z")
  },
  {
    _id: "O-201",
    tenant_id: "T-B",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(99000),
    buyer_name: "An",
    tags: ["vip"],
    archived: false,
    created_at: ISODate("2026-01-09T10:00:00Z")
  }
]);
```

`O-201` deliberately belongs to tenant `T-B` and shares `customer_id = "C-01"` with tenant `T-A` orders. This tests a critical bug: **optional conditions must never drop the mandatory tenant condition**.

### 2.2. Entity and Java Property Mapping

Each Java class in this lesson belongs in its appropriate file. Example entity:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public class Order {
    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("customer_id")
    private String customerId;

    private String status;

    @Field("total_cents")
    private long totalCents;

    @Field("buyer_name")
    private String buyerName;

    private List<String> tags;
    private boolean archived;

    @Field("created_at")
    private Instant createdAt;

    protected Order() {}

    public Order(String id, String tenantId, String customerId,
                 String status, long totalCents, String buyerName,
                 List<String> tags, boolean archived, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
        this.buyerName = buyerName;
        this.tags = tags;
        this.archived = archived;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getTotalCents() { return totalCents; }
    public String getBuyerName() { return buyerName; }
    public List<String> getTags() { return tags; }
    public boolean isArchived() { return archived; }
    public Instant getCreatedAt() { return createdAt; }
}
```

In code using `MongoTemplate.find(query, Order.class)`, fields `tenantId`, `customerId`, `totalCents`, `buyerName`, and `createdAt` are **Java properties**. Spring Data relies on `@Field` to generate queries targeting BSON `tenant_id`, `customer_id`, `total_cents`, `buyer_name`, and `created_at`.

With raw `MongoCollection<Document>` or `mongosh`, you must use **actual BSON names**. Distinguishing these two naming layers matters whenever users select sort or filter columns.

## 3. Designing the Search Contract Before Building Criteria

### 3.1. Request DTO Listing Allowed Conditions

A record containing only the options supported by the product:

```java
import java.time.Instant;
import java.util.List;

public record OrderSearchRequest(
    String status,
    String customerId,
    Long minTotalCents,
    Long maxTotalCents,
    Instant createdFrom,
    Instant createdUntil,
    Boolean archived,
    String buyerNameContains,
    List<String> anyTags
) {}
```

Meaning of each value:

| Request Value | Semantics When Present | When Omitted |
|---|---|---|
| `status` | Equals an allowed status | Do not filter by status |
| `customerId` | Equals customer ID | Do not filter by customer |
| `minTotalCents` | `totalCents >= min` | No lower bound |
| `maxTotalCents` | `totalCents <= max` | No upper bound |
| `createdFrom` | `createdAt >= createdFrom` | No start date bound |
| `createdUntil` | `createdAt < createdUntil` | No end date bound |
| `archived` | Equals `true` **or** `false` | Do not filter archived |
| `buyerNameContains` | Contains literal string, case-insensitive | Do not filter by name |
| `anyTags` | Array contains **at least one** selected tag | Do not filter by tag |

**Common pitfall:** because `archived` is a wrapper `Boolean`, it distinguishes three states: `true`, `false`, and `null`. Using a primitive `boolean` in the request DTO conflates omitted with `false`. Likewise, `Long minTotalCents = 0L` is **a valid condition**, not "no condition".

### 3.2. Three Levels of Input Control

1. **Type correctness:** framework parses dates, numbers, booleans; rejects malformed formats.
2. **Semantic correctness:** non-negative amounts, `min <= max`, valid date ranges, reasonable keyword length, bounded tag counts.
3. **Authorization correctness:** tenant comes from a trusted security context, never from a user-editable field scoping their own access.

If the API accepts `status` as a String, verify it belongs to the allowed set (e.g., `NEW`, `PAID`, `CANCELLED`) or use an enum with explicit parsing rules. Never turn arbitrary strings into MongoDB field names or turn client-supplied JSON structures directly into `Criteria` objects.

### 3.3. Distinguishing Null, Empty Strings, and Empty Lists

```text
status = null               → skip status condition
status = ""                 → per contract: skip or return 400, DO NOT default to equals ""
archived = false            → add condition archived = false
minTotalCents = 0           → add total_cents >= 0
anyTags = null              → skip tag filter
anyTags = []                → per contract: skip or return 400
anyTags = ["vip", "online"] → use $in when "any tag" is intended
```

In this lesson, we adopt the policy: **empty strings after trim and empty tag lists are treated as no filter**; non-empty values in invalid formats are rejected. Another product might return HTTP 400 for empty strings so overly broad queries are not run accidentally; document and test whichever policy you pick.

## 4. Building Criteria Piece by Piece Without Concatenating BSON Strings

### 4.1. Design Pattern: A List of AND Conditions

The following example creates a `Query` immutable in *logical intent*: each valid filter appends a `Criteria` to a list. The tenant condition is **always present**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class OrderCriteriaBuilder {
    private static final Set<String> ALLOWED_STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    private OrderCriteriaBuilder() {}

    public static Query build(
            OrderSearchRequest input, String trustedTenantId) {

        if (input == null
                || trustedTenantId == null
                || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException("Missing search context");
        }

        validate(input);

        List<Criteria> andParts = new ArrayList<>();
        andParts.add(
            Criteria.where("tenantId").is(trustedTenantId));

        if (hasText(input.status())) {
            andParts.add(Criteria.where("status")
                .is(input.status().trim()));
        }
        if (hasText(input.customerId())) {
            andParts.add(Criteria.where("customerId")
                .is(input.customerId().trim()));
        }
        if (input.minTotalCents() != null) {
            andParts.add(Criteria.where("totalCents")
                .gte(input.minTotalCents()));
        }
        if (input.maxTotalCents() != null) {
            andParts.add(Criteria.where("totalCents")
                .lte(input.maxTotalCents()));
        }
        if (input.createdFrom() != null) {
            andParts.add(Criteria.where("createdAt")
                .gte(input.createdFrom()));
        }
        if (input.createdUntil() != null) {
            andParts.add(Criteria.where("createdAt")
                .lt(input.createdUntil()));
        }
        if (input.archived() != null) {
            andParts.add(Criteria.where("archived")
                .is(input.archived()));
        }
        if (hasText(input.buyerNameContains())) {
            Pattern literal = Pattern.compile(
                Pattern.quote(input.buyerNameContains().trim()),
                Pattern.CASE_INSENSITIVE);
            andParts.add(Criteria.where("buyerName").regex(literal));
        }
        if (input.anyTags() != null && !input.anyTags().isEmpty()) {
            andParts.add(Criteria.where("tags")
                .in(input.anyTags()));
        }

        Criteria combined = new Criteria().andOperator(
            andParts.toArray(new Criteria[0]));
        return Query.query(combined);
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private static void validate(OrderSearchRequest input) {
        if (hasText(input.status())
                && !ALLOWED_STATUSES.contains(input.status().trim())) {
            throw new IllegalArgumentException("Invalid status");
        }
        if (input.customerId() != null
                && input.customerId().length() > 80) {
            throw new IllegalArgumentException("Customer ID too long");
        }
        if (input.buyerNameContains() != null
                && input.buyerNameContains().length() > 80) {
            throw new IllegalArgumentException("Search text too long");
        }
        if ((input.minTotalCents() != null
                && input.minTotalCents() < 0)
                || (input.maxTotalCents() != null
                && input.maxTotalCents() < 0)) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (input.minTotalCents() != null
                && input.maxTotalCents() != null
                && input.minTotalCents() > input.maxTotalCents()) {
            throw new IllegalArgumentException("Invalid amount range");
        }
        if (input.createdFrom() != null
                && input.createdUntil() != null
                && !input.createdFrom().isBefore(input.createdUntil())) {
            throw new IllegalArgumentException("Invalid time range");
        }
        if (input.anyTags() != null) {
            if (input.anyTags().size() > 20
                    || input.anyTags().stream().anyMatch(
                        tag -> tag == null || tag.isBlank()
                            || tag.length() > 40)) {
                throw new IllegalArgumentException("Invalid tags");
            }
        }
    }
}
```

This is an example of **filter-building logic**, not an entire controller, validation framework, or authorization policy. `trustedTenantId` must be obtained by the application from an authenticated source; never bind it directly from query parameters. `validate` illustrates basic checks; production code should add rules matching business and endpoint requirements.

In the final query, every condition combines via `$and`, including the tenant condition. A client-added `OR` filter can never break out of the tenant scope.

### 4.2. Why Use List<Criteria> Instead of Adding Multiple Conditions on the Same Key?

Suppose the user specifies both a lower and an upper bound. The logical form is:

```javascript
{
  $and: [
    { tenant_id: "T-A" },
    { total_cents: { $gte: NumberLong(10000) } },
    { total_cents: { $lte: NumberLong(20000) } }
  ]
}
```

MongoDB also supports combining operators on a single key:

```javascript
{
  tenant_id: "T-A",
  total_cents: {
    $gte: NumberLong(10000),
    $lte: NumberLong(20000)
  }
}
```

Both forms are semantically equivalent here. However, **you should not call `Query.addCriteria(...)` twice on the same key** when merging creates query structure conflicts, as Spring Data can throw an error for duplicate BSON keys. `List<Criteria>` and `andOperator(...)` offer a clean way to assemble independent filters, even when multiple conditions target the same property.

If you already know both conditions on a property upfront, you can also create one `Criteria.where("totalCents").gte(min).lte(max)` when both bounds are present. Neither choice is universally best; prioritize readability of the logic and the final BSON query.

### 4.3. Execution Example with MongoTemplate

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {
    private final MongoTemplate template;

    public OrderSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> search(
            OrderSearchRequest request, String trustedTenantId) {
        Query query = OrderCriteriaBuilder.build(
            request, trustedTenantId);
        return template.find(query, Order.class);
    }
}
```

This short example illustrates passing `Query` to `MongoTemplate`. In public APIs, you must add **limit, sort, and pagination** as covered in later sections; never let arbitrary requests return the entire collection.

### 4.4. Reading the Mapped Query Meaning Correctly

With `status = "PAID"`, `minTotalCents = 10000`, `archived = false`, and trusted tenant `T-A`, the equivalent query is:

```javascript
db.orders.find({
  $and: [
    { tenant_id: "T-A" },
    { status: "PAID" },
    { total_cents: { $gte: NumberLong(10000) } },
    { archived: false }
  ]
});
// Returns only O-101 in the sample dataset.
```

`O-103` has `archived: true`, so it is excluded; `O-201` belongs to tenant `T-B`, so it is excluded despite having `status: "PAID"` and a higher amount.

**Note on `Query.getQueryObject()`:** the query object is built using Java properties; when mapped against `Order.class` for execution, field names translate per `@Field`. Do not read `query.getQueryObject().toJson()` and conclude it is always the exact final BSON sent by the driver, especially when custom mapping or ID converters exist.

## 5. Controlling User-Selected Fields

Some UIs let users choose: "filter by **customer ID**, **status**, or **archived**". This differs from a request DTO with fixed properties because **the field name itself is an input value**.

Do not write:

```java
// Anti-pattern: field path comes uncontrolled from the request.
String field = request.getParameter("field");
String value = request.getParameter("value");
Query query = Query.query(Criteria.where(field).is(value));
```

A client could pick internal fields, disallowed nested paths, or names starting with special symbols. Even if the value is safely bound, **the field path determines query semantics**. Use an allowlist: permit only server-defined public names, and translate them to **fixed Java properties**.

### 5.1. Typed Field Selection Model

```java
public record SelectedFieldFilter(
    String field,   // "customer", "status", "archived"
    String value
) {}
```

Create a mapper from public names to **properly typed** criteria without plugging in arbitrary client field paths:

```java
import java.util.Set;
import org.springframework.data.mongodb.core.query.Criteria;

public final class SelectedFieldCriteria {
    private static final Set<String> STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    private SelectedFieldCriteria() {}

    public static Criteria create(SelectedFieldFilter filter) {
        if (filter == null) {
            return null;
        }
        if (filter.field() == null || filter.value() == null) {
            throw new IllegalArgumentException("Missing filter field/value");
        }

        String value = filter.value().trim();
        return switch (filter.field()) {
            case "customer" -> {
                if (value.isEmpty() || value.length() > 80) {
                    throw new IllegalArgumentException("Invalid customer");
                }
                yield Criteria.where("customerId").is(value);
            }
            case "status" -> {
                if (!STATUSES.contains(value)) {
                    throw new IllegalArgumentException("Invalid status");
                }
                yield Criteria.where("status").is(value);
            }
            case "archived" -> {
                if (!value.equals("true") && !value.equals("false")) {
                    throw new IllegalArgumentException("Invalid boolean");
                }
                yield Criteria.where("archived")
                    .is(Boolean.parseBoolean(value));
            }
            default -> throw new IllegalArgumentException(
                "Field is not allowed");
        };
    }
}
```

Here public field `"customer"` maps to Java property `customerId`; Spring Data then maps it to BSON `customer_id` when querying with `Order.class`. Fields such as `tenantId` and `internalNote` **are never allowed to be filtered arbitrarily** just because they exist on the entity.

### 5.2. Combining Selected Filters with the Base Query

```java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query base = OrderCriteriaBuilder.build(
    input, authenticatedTenantId);

Criteria selected = SelectedFieldCriteria.create(selectedField);
if (selected != null) {
    base.addCriteria(selected);
}

List<Order> results = mongoTemplate.find(base, Order.class);
```

This snippet assumes two premises:

1. `input`, `authenticatedTenantId`, and `selectedField` were supplied/validated at the service layer; never use a request-supplied tenant value.
2. `OrderCriteriaBuilder.build(...)` uses a top-level `$and`; the added criteria has a **top-level key other than `$and`**, so all conditions still combine via AND. If you change how the base query is structured, re-check adding conditions onto the same key.

For **multiple user-selected filters**, it is safer to assemble all of them into **a single `Criteria` list upfront** rather than appending ad hoc to a finished `Query`. Cap the filter count, reject disallowed duplicate fields, and define behavior when two conditions on the same field conflict.

### 5.3. Why Never Let Users Send MongoDB Operators?

An API should never accept a raw object like:

```json
{
  "field": "status",
  "operator": "$ne",
  "value": "CANCELLED"
}
```

and splice it straight into a BSON query unchecked. Users can supply unintended operators or trigger extremely broad queries. If the product genuinely requires choosing an operator, define a dedicated business operator set such as `EQ`, `GTE`, `LTE`, `IN`, where each field supports only operators appropriate for its data type.

| Public Field | Allowed Property Path | Operators Permitted | Value Type |
|---|---|---|---|
| `customer` | `customerId` | `EQ` | Non-empty String |
| `status` | `status` | `EQ`, bounded `IN` | Status enum |
| `archived` | `archived` | `EQ` | Boolean |
| `total` | `totalCents` | `GTE`, `LTE`, `BETWEEN` | Non-negative Long |
| `created` | `createdAt` | `FROM`, `UNTIL` | Instant |
| `buyerName` | `buyerName` | `CONTAINS_LITERAL` | Length-capped String |

Never turn an API operator into `"$" + input`. Map each field/operator pair via a `switch` or a **strategy table declared in code**. Unsupported combinations must be explicitly rejected rather than silently ignored to run a broader query.

### 5.4. Blocking Dangerous Characters Alone Is Not Enough

A field-name validator like "must not contain `$` or `.`" does not solve the problem. The name `internalNotes` has no special characters yet may still be a sensitive field; `shipment.address.city` has dots yet may be valid if the product approved that specific nested property.

**Business-meaning allowlists** are far more reliable than character checks:

```text
Client field key: "customer"
    ↓
Server allowlist
    ↓
Java property: customerId
    ↓
Spring mapping (@Field)
    ↓
BSON field: customer_id
```

When nested properties exist, declare an exact fixed public key, e.g., `"shippingCity" -> "shippingAddress.city"`, after verifying the entity actually defines that path. Never let clients concatenate `shippingAddress.` with an arbitrary property name.

## 6. Combining AND/OR Without Dropping Tenant

### 6.1. Access-Scoped OR

Requirement: find orders **belonging to tenant T-A**, with status `NEW` **or** `PAID`. The correct structure is:

```javascript
{
  $and: [
    { tenant_id: "T-A" },
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    }
  ]
}
```

Spring Data Criteria:

```java
Criteria visibleToTenant =
    Criteria.where("tenantId").is(authenticatedTenantId);

Criteria allowedStatuses = new Criteria().orOperator(
    Criteria.where("status").is("NEW"),
    Criteria.where("status").is("PAID")
);

Query q = Query.query(
    new Criteria().andOperator(
        visibleToTenant, allowedStatuses));

List<Order> matches = mongoTemplate.find(q, Order.class);
```

For tenant `T-A` in the sample dataset, this matches `O-101`, `O-102`, `O-103` (depending on additional filters). `O-201` of tenant `T-B` must never appear.

### 6.2. Mistake: Tenant Inside Only One OR Branch

```javascript
// Anti-pattern when all results must stay within T-A:
{
  $or: [
    { tenant_id: "T-A", status: "PAID" },
    { status: "NEW" }
  ]
}
```

The second branch lacks the tenant condition and can return `NEW` orders from any tenant. Safety rule: **place mandatory constraints outside optional OR clauses**, or repeat them accurately in every branch if there is a special verified reason.

### 6.3. OR Over a Status List Can Be Simplified to IN

When multiple values compare equality on the same property:

```java
Criteria.where("status").in(List.of("NEW", "PAID"))
```

is usually cleaner than:

```java
new Criteria().orOperator(
    Criteria.where("status").is("NEW"),
    Criteria.where("status").is("PAID"))
```

When allowing multiple statuses via an API, verify every value belongs to the approved enum/status set and bound list length. For an empty list, explicitly decide whether it means "no filter" or "no results"; the two interpretations differ and should not accidentally depend on `$in: []`.

### 6.4. AND/OR with Optional Conditions

To express:

> Tenant T-A, amount at least 10,000 cents, and (status = PAID **or** status = NEW).

You can write:

```java
List<Criteria> all = new ArrayList<>();
all.add(Criteria.where("tenantId").is(authenticatedTenantId));
all.add(Criteria.where("totalCents").gte(10_000L));
all.add(new Criteria().orOperator(
    Criteria.where("status").is("PAID"),
    Criteria.where("status").is("NEW")
));

Query query = Query.query(
    new Criteria().andOperator(
        all.toArray(new Criteria[0])));
```

With **optional filters**, only add `orOperator(...)` when at least one valid branch exists. Never construct an empty OR group expecting Spring Data and MongoDB to treat it as "no filter". Use a helper that builds branch lists, validates inputs, and avoids duplicates.

## 7. Ranges, Timestamps, and Lists: Defining Exact Semantics

### 7.1. Zero Values, Inclusive Bounds, and Exclusive Bounds

For `totalCents`:

```java
Criteria.where("totalCents").gte(0L);
Criteria.where("totalCents").lte(10_000L);
```

Both `gte` and `lte` are inclusive. If you want `[0, 10000)`, use `gte(0).lt(10000)`. Never convert integer cents to `double` just for comparison; ensure consistent BSON types and business units.

For time intervals, a **half-open** model is usually clearer:

```text
createdFrom  = 2026-01-01T00:00:00Z (inclusive)
createdUntil = 2026-02-01T00:00:00Z (exclusive)

2026-01-31T23:59:59.999Z → included
2026-02-01T00:00:00Z     → excluded
```

There is no need to fabricate `"23:59:59.999999..."` for end-of-day. However, when users pick dates in their own timezone, the controller must convert **start-of-day in the defined timezone** into the corresponding UTC `Instant`. Never silently assume the OS timezone or assume all requests are UTC if the product operates on local calendar days.

### 7.2. Array Search: Any and All Are Two Different Requirements

With `tags: ["vip", "online"]`:

```java
// Has at least one selected tag.
Criteria.where("tags").in(List.of("vip", "retail"));

// Must contain all selected tags.
Criteria.where("tags").all(List.of("vip", "retail"));
```

In the sample dataset, the `any` condition matches `O-101` and `O-103` in tenant `T-A`, whereas the `all` condition on those two tags matches only `O-103`. This is not a minor syntax difference; it is a business distinction that must be explicit in the API.

When searching documents inside an object array, `Criteria.elemMatch(...)` is essential whenever multiple conditions must apply to **the same array element**. Never use two separate dot-notation paths assuming MongoDB binds them to a single element.

### 7.3. Missing, Null, and False

```javascript
{ archived: false }                 // Matches value false
{ archived: { $exists: false } }    // Matches documents missing the field
{ archived: null }                  // Matches null or missing field
```

These three conditions are not equivalent. If legacy data has documents missing `archived` yet business rules treat them as "unarchived", define how schema/migrations or explicit query conditions handle that. A `Boolean archived` in the request only decides whether to add the filter; it does not resolve differences between BSON null and missing.

If business logic must distinguish all three states `false`, `true`, and missing, design a dedicated filter status enum rather than overloading `Boolean null` in the request.

## 8. Literal String Search and Regex Limits

Searching `buyerName` containing a keyword can use `Criteria.where("buyerName").regex(...)`, though you must distinguish **literal strings** from **user-written regexes**.

### 8.1. Pattern.quote Preserves Literal Meaning

```java
String keyword = "A.B";
Pattern safe = Pattern.compile(
    Pattern.quote(keyword),
    Pattern.CASE_INSENSITIVE
);

Criteria byBuyerName = Criteria.where("buyerName")
    .regex(safe);
```

`Pattern.quote("A.B")` ensures the dot is treated as a literal `.` character rather than a regex wildcard. Conversely:

```java
// Do not use when input comes from a normal literal search box:
Pattern unsafe = Pattern.compile(userText);
```

If `userText = ".*"`, such a regex matches almost every string and makes the query overly broad. In the builder example in section 4, `buyerNameContains` is capped at 80 characters and always passed through `Pattern.quote(...)`.

**Do not conflate regex injection with BSON operator injection:** `Pattern.quote` ensures parameters behave as literals inside regexes; field/operator allowlists ensure queries only reference approved properties and operators. Both layers of defense are necessary in flexible search APIs.

### 8.2. Regex Impact on Indexes

MongoDB can leverage B-tree indexes for **case-sensitive, start-anchored literal prefix** regexes, such as `/^An/`. Substring regexes matching anywhere, or regexes with `i` ignoring case, struggle to use this type of index effectively. A case-insensitive collation index does not automatically make case-insensitive `$regex` index-friendly.

If the product needs large-scale autocomplete, consider:

- Prefix search on a normalized canonical field with an appropriate index.
- Input length caps, debouncing, concurrency caps, and page size limits.
- Separating **original display name** from **normalized search key** when ignoring case/diacritics.
- MongoDB Search / Atlas Search or a dedicated search engine when full-text, fuzzy matching, tokenization, or complex wildcards are needed.

Never blindly raise `maxPoolSize` when substring queries scan too many documents; focus optimization on search patterns and indexes.

### 8.3. Do Not Allow Arbitrary Regex Field Selection

An API accepting `field = "buyerName"` and `value = "A.B"` must still pass through an allowlist:

```java
// The only field supported for literal text search in this example:
if (!"buyerName".equals(publicField)) {
    throw new IllegalArgumentException("Not searchable as text");
}
Criteria safeText = Criteria.where("buyerName").regex(
    Pattern.compile(Pattern.quote(text),
        Pattern.CASE_INSENSITIVE));
```

Do not let users pick an arbitrary field on the entity and issue `$regex` against it: its BSON type might not be String, its data might be sensitive, and performance varies per field.

## 9. Sorting, Pagination, and Bounding Results on Allowed Fields

Just like filtering, client-supplied `sortBy` and `direction` must never be passed straight into queries unchecked. Some properties hold internal data, lack indexes, or are unsuitable for sorting.

### 9.1. Separate Allowlist for Sorting

```java
import java.util.Locale;
import java.util.Map;
import org.springframework.data.domain.Sort;

public final class SafeOrderSort {
    private static final Map<String, String> SORT_FIELDS = Map.of(
        "createdAt", "createdAt",
        "total", "totalCents",
        "customer", "customerId"
    );

    private SafeOrderSort() {}

    public static Sort fromRequest(String publicField, String direction) {
        String requested = (publicField == null || publicField.isBlank())
            ? "createdAt" : publicField;
        String property = SORT_FIELDS.get(requested);
        if (property == null) {
            throw new IllegalArgumentException("Sort field is not allowed");
        }

        String order = (direction == null || direction.isBlank())
            ? "desc" : direction.toLowerCase(Locale.ROOT);

        Sort.Direction sortDirection = switch (order) {
            case "asc" -> Sort.Direction.ASC;
            case "desc" -> Sort.Direction.DESC;
            default -> throw new IllegalArgumentException(
                "Sort direction must be asc or desc");
        };

        return Sort.by(sortDirection, property)
            .and(Sort.by(Sort.Direction.ASC, "id"));
    }
}
```

Public key `"total"` maps to Java `totalCents` and then BSON `total_cents`. Public key `"customer"` similarly becomes `customer_id`. The allowed sort set is **independent** of the filter set: a field may be fine for equality filtering yet unsuitable for sorting due to missing indexes or security requirements.

Appending `id` as a tie-breaker stabilizes pagination order across documents sharing identical `createdAt` or `totalCents`. Still, under concurrent inserts/deletes, offset pagination can duplicate or skip items across requests; when strict consistency or deep paging is needed, consider keyset/range pagination.

### 9.2. Safe Pageable Instead of Arbitrary skip/limit

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

public final class SafeOrderPage {
    private SafeOrderPage() {}

    public static Pageable fromRequest(
            int page, int size, String sortBy, String direction) {
        if (page < 0 || page > 1_000 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page/size");
        }
        long offset = (long) page * size;
        if (offset > 10_000L) {
            throw new IllegalArgumentException("Offset is too large");
        }

        return PageRequest.of(page, size,
            SafeOrderSort.fromRequest(sortBy, direction));
    }
}
```

Numbers 100, 1,000, and 10,000 are **example limits**, not defaults or MongoDB limits. Choose caps based on SLAs, UX, and system benchmarks. Capping offsets at the API layer prevents queries from skipping too many results; on huge datasets, adopt a different pagination strategy.

### 9.3. Identical Filter for Content and Count

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.query.Query;

public Page<Order> searchPaged(
        OrderSearchRequest request,
        String trustedTenantId,
        int pageIndex,
        int pageSize,
        String sortBy,
        String direction) {

    Pageable pageable = SafeOrderPage.fromRequest(
        pageIndex, pageSize, sortBy, direction);

    Query contentQuery =
        OrderCriteriaBuilder.build(request, trustedTenantId);
    contentQuery.with(pageable);

    List<Order> content =
        mongoTemplate.find(contentQuery, Order.class);

    // Build a fresh Query with the exact same filter, without skip/limit.
    Query countQuery =
        OrderCriteriaBuilder.build(request, trustedTenantId);
    long total = mongoTemplate.count(countQuery, Order.class);

    return new PageImpl<>(content, pageable, total);
}
```

This illustrative method belongs to a service with `mongoTemplate` injected. Do not run count on a query carrying `skip`/`limit` expecting the unpaginated total. `Page` supplies total count at the cost of an extra count query, which can be significant with complex filters. If the UI only needs to know whether a next page exists, consider `Slice` with sensible bounds.

**Crucially:** count and content must use **the exact same tenant condition and filters**. If you add a `SelectedFieldFilter` to the content query yet forget to apply it to count, `totalElements` will disagree with the displayed result set. In production code, encapsulate `Criteria` construction in a single factory shared by both paths.

### 9.4. Never Fetch Unbounded Row Counts

```java
// Unsuitable for free-form search endpoints on large collections:
List<Order> all = mongoTemplate.find(query, Order.class);
```

An unbounded query can send massive payloads over the wire, spike heap/GC pressure, and tie up MongoDB cursors. Enforce limits/page sizes at the service layer, alongside rate limiting for public APIs. Never rely on a UI currently showing 20 rows to assume the server queries only 20 documents.

## 10. User-Selected Output Columns: Projection Must Have an Allowlist

Some UIs let users select columns:

```json
{
  "columns": ["orderId", "customer", "status", "total"]
}
```

This is a **projection** requirement, distinct from choosing fields to filter or sort. If clients could pass arbitrary column names into `query.fields().include(...)`, the API could accidentally expose internal fields like `internalNote`, `riskScore`, or `tenantId`, even if not intended for response display.

### 10.1. Mapping Public Columns to Java Properties

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.data.mongodb.core.query.Query;

public final class SafeOrderColumns {
    private static final Map<String, String> ALLOWED = Map.of(
        "orderId", "id",
        "customer", "customerId",
        "status", "status",
        "total", "totalCents",
        "created", "createdAt"
    );

    private static final List<String> DEFAULT =
        List.of("orderId", "customer", "status", "total");

    private SafeOrderColumns() {}

    public static List<String> normalize(List<String> requested) {
        List<String> source = (requested == null || requested.isEmpty())
            ? DEFAULT : requested;
        if (source.size() > ALLOWED.size()) {
            throw new IllegalArgumentException("Too many columns");
        }

        Set<String> unique = new LinkedHashSet<>();
        for (String column : source) {
            if (column == null || !ALLOWED.containsKey(column)
                    || !unique.add(column)) {
                throw new IllegalArgumentException(
                    "Unknown or duplicate column");
            }
        }
        return List.copyOf(unique);
    }

    public static void apply(Query query, List<String> normalized) {
        if (normalized == null || normalized.isEmpty()) {
            throw new IllegalArgumentException("No columns selected");
        }
        for (String column : normalized) {
            String property = ALLOWED.get(column);
            if (property == null) {
                throw new IllegalArgumentException("Column not allowed");
            }
            query.fields().include(property);
        }

        // MongoDB returns _id by default in inclusion projections.
        if (!normalized.contains("orderId")) {
            query.fields().exclude("id");
        }
    }
}
```

`SafeOrderColumns` accepts only fixed public keys, preventing clients from requesting `"$where"`, internal fields, or arbitrary property paths from MongoDB. `query.fields().include("customerId")` still uses the **Java property** because the call uses `mongoTemplate.find(query, Order.class)`; Spring Data maps it to BSON `customer_id`.

In MongoDB `find` projections, `_id` is retained by default when other fields are included, so the example calls `exclude("id")` whenever the user omits `orderId`. Standard inclusion/exclusion rules **forbid arbitrary mixing**, but excluding `_id` is a valid exception.

### 10.2. Avoid Saving Entities Loaded via Projection

```java
Query q = OrderCriteriaBuilder.build(
    input, authenticatedTenantId);

List<String> selectedColumns =
    SafeOrderColumns.normalize(requestedColumns);
SafeOrderColumns.apply(q, selectedColumns);
q.with(SafeOrderPage.fromRequest(0, 20, "createdAt", "desc"));

List<Order> partialOrders =
    mongoTemplate.find(q, Order.class);
```

`partialOrders` holds **only partially loaded** entities. Unprojected properties carry null/default values in Java. **Never call `mongoTemplate.save(partialOrders.get(0))`** to update statuses or transactions: saving an object missing fields can overwrite unloaded data.

In APIs, **map read data to read-only DTOs** and return only approved values. Both selecting columns to **query** and selecting columns to **serialize in responses** must be controlled; never blindly return all properties on an entity.

### 10.3. Mapping Public Columns to Responses

Example helper producing an ordered result map matching normalized selections:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OrderRowMapper {
    private OrderRowMapper() {}

    public static Map<String, Object> toPublicRow(
            Order order, List<String> selectedColumns) {
        Map<String, Object> row = new LinkedHashMap<>();
        for (String column : selectedColumns) {
            switch (column) {
                case "orderId" -> row.put(column, order.getId());
                case "customer" -> row.put(column, order.getCustomerId());
                case "status" -> row.put(column, order.getStatus());
                case "total" -> row.put(column, order.getTotalCents());
                case "created" -> row.put(column, order.getCreatedAt());
                default -> throw new IllegalArgumentException(
                    "Unapproved output column");
            }
        }
        return row;
    }
}
```

Never pass unvalidated `selectedColumns` to this helper. A fixed typed DTO API is generally simpler and easier to maintain than a dynamic map; maps make sense only when the product truly requires request-driven columns. For sensitive data, pair allowlists with authorization policies per data type or role.

### 10.4. Projection Is Not Authorization

A `@Field` annotation or `query.fields().include(...)` does not stop unauthorized access if a query omits the tenant filter. Conversely, a properly tenant-scoped query returning every entity field can still leak restricted attributes. Enforce all layers together:

```text
Identity & permissions: resolve trusted tenant, role
      ↓
Mandatory filter: bound which documents may be read
      ↓
Allowlisted fields: bound which data may be returned
      ↓
Pagination/Sort: bound result volume and order
      ↓
DTO/response serialization: public API contract
```

In particular, if using raw `Document` or computed aggregations, check output aliases and physical BSON names instead of assuming every stage applies entity mapping like `MongoTemplate.find(..., Order.class)`.

## 11. Controlling Advanced Operators and Query Complexity

### 11.1. Designing Resource Limits as Part of the Input Contract

Beyond field and operator allowlists, enforce:

| Limit | Example Policy | Why |
|---|---|---|
| Filter count | Max 10 public conditions | Prevents overly complex query trees |
| Values in `IN` | Max 20–50 | Prevents overly broad/multi-value queries |
| Keyword length | Max 80 characters | Reduces slow-regex risk and abnormal inputs |
| `OR` branches | Max 10 | Caps query complexity |
| Page size | Max 100 | Bounds returned data volume |
| Offset | Capped or keyset | Avoids deep `skip` |
| Sort fields | Indexed/benchmarked allowlist | Prevents arbitrary sorts on large datasets |
| Time span | Capped per SLA, e.g., 90 days for standard APIs | Stops one request from scanning years of data |

These numbers are illustrative discussion baselines, **not fixed MongoDB or Spring Data limits**. Choose actual limits from your workload, indexes, database capacity, and SLAs.

### 11.2. Never Accept Arbitrary Pipelines or BSON from Clients

Never pass raw JSON such as:

```json
{
  "query": {
    "$expr": { "$gt": ["$total_cents", 0] }
  }
}
```

directly into `BasicQuery` or the raw driver just because "the API supports flexible filtering". Operators like `$expr`, `$regex`, `$where`, `$lookup`, or complex aggregation stages must be **selected by server-side logic**, checked for authorization, and resource-bounded. No character filter can make a client-controlled pipeline safe.

`BasicQuery` allows writing explicit BSON/JSON queries in Spring Data, which fits when **developers control the query structure**. For user-facing business inputs, `Criteria` and allowlists keep boundaries far easier to review.

### 11.3. Separating Input Errors from Database Errors

For HTTP APIs:

- Unapproved fields, invalid operators, or malformed dates/numbers: **400 Bad Request** per API policy.
- User lacks permission to view data/tenant: **403 Forbidden** or appropriate security response; never rely on an empty query result as proof of authorization.
- Query timeouts, network failures, or MongoDB outages: handle as infrastructure errors; never report "not found" when the query actually failed.

Never log raw tokens, URIs containing passwords, sensitive data, or full queries containing PII in production logs. For performance monitoring, logging endpoint name, filter count, allowlisted field names, latency, and error status is sufficient in most cases.

## 12. Indexes and Performance Verification for Optional Filters

A query builder can produce dozens of combinations, yet you cannot create a separate index for **every field combination**. Start from actual workloads: common filters, common sorts, tenant distribution, request frequency, and latency targets.

### 12.1. Compound Indexes for Key Combinations

If most queries filter by `tenant_id` and `status`, then sort by newest `created_at`, test:

```javascript
db.orders.createIndex(
  { tenant_id: 1, status: 1, created_at: -1, _id: 1 },
  { name: "ix_tenant_status_created" }
);
```

Matching:

```javascript
db.orders.find({
  tenant_id: "T-A",
  status: "PAID"
}).sort({ created_at: -1, _id: 1 }).limit(20);
```

**Key order in an index matters.** With equality filters on `tenant_id` and `status`, MongoDB can use the trailing keys for sorting. Yet if a request **omits status**, this compound index does not serve sorting by `created_at` efficiently because `status` precedes it. You may need an additional index for common status-less queries:

```javascript
db.orders.createIndex(
  { tenant_id: 1, created_at: -1, _id: 1 },
  { name: "ix_tenant_created" }
);
```

Do not blindly deploy every example index. Each index adds storage, RAM, update, and maintenance costs. Pick indexes from real metrics and measure impact on important queries.

### 12.2. Range Conditions and Sorting

When filtering by amount:

```javascript
db.orders.find({
  tenant_id: "T-A",
  total_cents: { $gte: NumberLong(10000) }
}).sort({ total_cents: -1 }).limit(20);
```

you can evaluate:

```javascript
db.orders.createIndex(
  { tenant_id: 1, total_cents: -1, _id: 1 },
  { name: "ix_tenant_total" }
);
```

A query simultaneously combining a **total range**, a **time range**, and a **sort by customer** is much harder to optimize than three simple equality queries. Do not throw every field into one wide index expecting MongoDB to accelerate every combination.

### 12.3. Running explain on Representative Combinations

Run in `mongosh`:

```javascript
db.orders.find({
  tenant_id: "T-A",
  status: "PAID"
}).sort({ created_at: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.orders.find({
  tenant_id: "T-A",
  total_cents: { $gte: NumberLong(10000) }
}).sort({ total_cents: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.orders.find({
  tenant_id: "T-A",
  buyer_name: /an/i
}).limit(20).explain("executionStats");
```

Compare metrics:

| Indicator | What to Investigate |
|---|---|
| `IXSCAN` | MongoDB used an index, though it may still scan many keys |
| `COLLSCAN` | MongoDB scanned the collection; normal when data is tiny |
| `totalKeysExamined` | Number of index keys inspected |
| `totalDocsExamined` | Number of documents inspected |
| `nReturned` | Actual number of documents returned |
| Expensive `SORT` stage | Index does not satisfy sort order, or dataset is too large |
| High latency on regex | Substring/case-insensitive matches often scan broadly |

On four sample documents, MongoDB will readily pick `COLLSCAN` because data is tiny; never conclude from a tiny test plan that an index is useless. Benchmark with production-like distributions and cardinality across multiple runs.

### 12.4. Count and Pagination Also Need Measurement

Fetching a 20-item page may be fast while counting **all matching results** remains costly. With regexes or wide ranges, `Page` adds substantial load compared to returning a single page. Count only when UX genuinely requires it, cache counts where appropriate, or use `Slice`/has-next.

User-selectable sorting must restrict to fields reviewed for index coverage and performance. Some public fields **should stay out of `SORT_FIELDS`** when data distribution and indexes cannot support them, even if displayed in the UI.

## 13. Integration Testing Query/Criteria with Real MongoDB

### 13.1. Contracts to Test

| Scenario | Expected Outcome |
|---|---|
| No optional filters, tenant = `T-A` | Sees only `O-101`, `O-102`, `O-103` |
| Tenant = `T-A`, `status = PAID` | Sees only `O-101`, `O-103` |
| Tenant = `T-A`, `archived = false` | Sees only `O-101`, `O-102` |
| Tenant = `T-A`, `status = PAID`, `archived = false` | Sees only `O-101` |
| Tenant = `T-A`, `minTotalCents = 0` | Returns all three orders; zero condition is not dropped |
| Tenant = `T-A`, `minTotalCents = 10000` | Sees only `O-101`, `O-103` |
| Tenant = `T-A`, `anyTags = ["retail"]` | Sees only `O-103` |
| Tenant = `T-A`, date range Jan 06 to before Jan 08 UTC | Sees only `O-102` |
| Filter `customerId = C-01`, tenant = `T-A` | Never returns `O-201` of tenant `T-B` |
| `SelectedFieldFilter` with field `"tenantId"` | Rejected because not on allowlist |
| Sort by unknown field | Rejected before hitting MongoDB |
| Selecting unapproved output column | Rejected, no data leaked |
| Oversized page size or deep offset | Rejected per policy |
| Literal keyword containing regex metacharacters | Treated as literal text, not raw regex |

### 13.2. JUnit 5 + Spring Data MongoDB Test Example

The snippet below assumes `@DataMongoTest` connects to an isolated integration-test MongoDB, never shared with real data. Inside that test database only, seed data:

```java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderCriteriaBuilderTest {
    @Autowired
    MongoTemplate template;

    @BeforeEach
    void seed() {
        // Isolated test database only.
        template.getCollection("orders").deleteMany(
            new org.bson.Document());
        template.insertAll(List.of(
            order("O-101", "T-A", "C-01", "PAID",
                15500L, "An", List.of("vip", "online"), false,
                "2026-01-05T10:00:00Z"),
            order("O-102", "T-A", "C-02", "NEW",
                6500L, "Lan Anh", List.of("online"), false,
                "2026-01-06T10:00:00Z"),
            order("O-103", "T-A", "C-01", "PAID",
                21000L, "ANNA", List.of("vip", "retail"), true,
                "2026-01-08T10:00:00Z"),
            order("O-201", "T-B", "C-01", "PAID",
                99000L, "An", List.of("vip"), false,
                "2026-01-09T10:00:00Z")
        ));
    }

    private static Order order(
            String id, String tenant, String customer, String status,
            long total, String name, List<String> tags,
            boolean archived, String at) {
        return new Order(id, tenant, customer, status, total, name,
            tags, archived, Instant.parse(at));
    }

    private static OrderSearchRequest request(
            String status, Long min, Boolean archived) {
        return new OrderSearchRequest(
            status, null, min, null,
            null, null, archived, null, null);
    }

    @Test
    void tenantFilterIsAlwaysApplied() {
        var q = OrderCriteriaBuilder.build(
            request(null, null, null), "T-A");

        assertThat(template.find(q, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-102", "O-103");
    }

    @Test
    void falseIsAnActualFilterValue() {
        var q = OrderCriteriaBuilder.build(
            request("PAID", null, false), "T-A");

        assertThat(template.find(q, Order.class))
            .extracting(Order::getId)
            .containsExactly("O-101");
    }

    @Test
    void zeroAndPositiveRangeAreNotDropped() {
        var zero = OrderCriteriaBuilder.build(
            request(null, 0L, null), "T-A");
        assertThat(template.find(zero, Order.class)).hasSize(3);

        var threshold = OrderCriteriaBuilder.build(
            request(null, 10000L, null), "T-A");
        assertThat(template.find(threshold, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-103");
    }

    @Test
    void selectableFieldMustBeOnAllowlist() {
        assertThatThrownBy(() -> SelectedFieldCriteria.create(
            new SelectedFieldFilter("tenantId", "T-B")))
            .isInstanceOf(IllegalArgumentException.class);

        var query = OrderCriteriaBuilder.build(
            request(null, null, null), "T-A");
        query.addCriteria(SelectedFieldCriteria.create(
            new SelectedFieldFilter("customer", "C-01")));

        assertThat(template.find(query, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-103");
    }

    @Test
    void sortAndProjectionRejectUnknownFields() {
        assertThatThrownBy(() ->
            SafeOrderSort.fromRequest("internalNote", "desc"))
            .isInstanceOf(IllegalArgumentException.class);

        assertThatThrownBy(() ->
            SafeOrderColumns.normalize(
                List.of("orderId", "secretToken")))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

These tests demonstrate actual query-builder and mapping behavior, not merely assertions on constructed `Criteria` objects. If your project uses a newer Spring Boot release, `@DataMongoTest` package/dependencies may differ; adjust to match your version. Never run `deleteMany(new Document())` on shared development or production databases as it wipes the entire collection.

### 13.3. Testing Projection and Pagination

Add a test:

```java
Query q = OrderCriteriaBuilder.build(
    request(null, null, null), "T-A");

List<String> columns = SafeOrderColumns.normalize(
    List.of("customer", "total"));
SafeOrderColumns.apply(q, columns);
q.with(SafeOrderPage.fromRequest(
    0, 2, "createdAt", "desc"));

List<Order> partial = template.find(q, Order.class);
assertThat(partial).hasSize(2);

for (Order order : partial) {
    var publicRow = OrderRowMapper.toPublicRow(order, columns);
    assertThat(publicRow.keySet())
        .containsExactly("customer", "total");
}
```

This snippet assumes placement inside the test class in section 13.2, reusing helper `request(...)`. Also inspect raw commands/projections or write a dedicated `org.bson.Document` test to confirm no unexpected BSON fields are returned, including `_id` when omitted by the API.

For stable sorting, seed multiple documents with identical `created_at` and verify the `_id` tie-breaker. For pagination, test count and content using **the same filter**, oversized page sizes, negative pages, and deep offsets. Do not test only the first page on a three-record dataset.

### 13.4. Testing Input Errors and Security

At a minimum, include cases for:

- `minTotalCents > maxTotalCents` and inverted date ranges.
- `archived = false`, `minTotalCents = 0`, and blank strings.
- Tag lists exceeding limits or containing null/blank entries.
- Status values outside the allowed set.
- Internal or nonexistent field names, sort directions outside `asc`/`desc`.
- Keywords containing `.`, `*`, `[`, and overly long strings.
- Queries containing `OR` branches still enforcing mandatory tenant scope.
- User `T-A` attempting to query `O-201` or `C-01` of `T-B` without authorization.

Security tests must verify **actual returned data**, not just isolated validation helper methods. That is why real MongoDB integration tests carry far more value than mocking `MongoTemplate.find(...)` in multi-tenant scenarios.

## 14. Diagnosing Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Selected `archived=false` yet query does not filter | Used `if (Boolean.TRUE.equals(...))` or primitive boolean | Check `input.archived() != null` |
| `minTotalCents=0` gets skipped | Checked `> 0` instead of `!= null` | Distinguish omitted from 0 |
| Adding two criteria on the same field fails | Top-level duplicate keys or broken Criteria structure | Merge ranges or use `andOperator` |
| Results contain another tenant's documents | Tenant condition omitted or inside only one OR branch | Keep mandatory tenant outside OR, test multi-tenant data |
| Found in `mongosh` yet missing via template | Wrong Java/BSON property or `_id` type | Check `@Field`, `QueryMapper`, and raw documents |
| Querying user-selected fields leaks sensitive data | Missing allowlist/authorization | Map public keys → server-approved properties |
| Arbitrary `sortBy` slows responses | Unindexed sort, unsuitable cardinality/type | Allowlist sorts, add indexes, benchmark |
| `buyerNameContains = ".*"` matches everything | Raw regex used without quoting literal | Use `Pattern.quote` |
| Query drops results when using projection | Missing DTO fields or excluded `_id` | Verify field list and DTO contract |
| `save` erases fields after projected read | Partial entity passed to replace/save | Use read-only DTOs or targeted atomic updates |
| `Page.totalElements` disagrees with content | Count misses filters or carries paging options | Share the same query factory, keep skip/limit out of count |
| Date range query shifts by a day | Inconsistent local timezone handling | Convert business timezone dates cleanly to UTC |
| Regex is slow despite a collation index | `$regex` is not collation-aware like equality/sort | Design canonical fields, prefixes, or search indexes |
| Tag search yields wrong semantics | Confused `$in` (any) with `$all` (all) | State API contract clearly and test |

### 14.1. Repeatable Investigation Workflow

1. Capture the **normalized request** and tenant/role from the security context, keeping PII out of logs.
2. Inspect the list of appended filters: which conditions were omitted, which equal `false` or `0`?
3. Verify public fields mapped to valid Java properties, and `@Field` translated to the right BSON names.
4. Run the equivalent query in `mongosh` against the exact database/collection on sample or test data.
5. Run `explain("executionStats")` and check filter, sort, index, scan, count, and page size.
6. Write regression tests for the failing input: added optional filters, invalid sorts, cross-tenant attempts, null/missing data.

Do not react by enlarging connection pools, raising timeouts, or dropping mandatory conditions just to make queries return results. Separate logic, mapping, index, and network issues before fixing.

## 15. Practice Exercise: Order Search API with Selectable Columns

**Context:** a tenant administrator wants to list orders with optional filters for status, amount range, creation dates, customer, tags, or keyword; they can also pick public columns and sort order. All data must remain strictly scoped to the authenticated tenant.

1. **Seed data:** insert the four documents from section 2, confirming `O-201` belongs to another tenant.
2. **Define DTO:** create `OrderSearchRequest` and standardize null/empty semantics, Booleans, 0 values, and half-open date ranges.
3. **Build Query:** implement `OrderCriteriaBuilder.build(input, trustedTenantId)`, appending optional filters via a `Criteria` list.
4. **Control selectable fields:** permit users to pick only `customer`/`status`/`archived` for equality, rejecting any other name.
5. **AND/OR:** add finding `NEW` or `PAID` orders while still enforcing tenant; prove `O-201` is never returned when logged in as tenant `T-A`.
6. **Safe input:** test `buyerNameContains = ".*"`, huge strings, invalid statuses, and inverted amount ranges; verify policy enforcement.
7. **Sort/page:** use `SafeOrderSort` and `SafeOrderPage`, enforcing page size and offset caps. Sort by `createdAt` with `id` tie-breaker.
8. **Projection:** create a public column allowlist returning only selected `orderId`/`customer`/`status`/`total`/`created` fields.
9. **Count:** share the same query factory for content and count, verifying `Page.totalElements` matches the filter.
10. **Indexes:** test `{ tenant_id: 1, status: 1, created_at: -1, _id: 1 }`; benchmark with and without status, with regex, and when sorting by total.
11. **Integration tests:** verify `false`, `0`, null, `$in`, tenant isolation, public output columns, and rejected parameters.
12. **Justify choice:** explain why `MongoTemplate/Criteria` fits better than writing dozens of derived repository methods for every filter combination.

**Completion criteria** — learners demonstrate that:

- With zero optional filters, the **tenant filter still holds**.
- Values `0` and `false` are preserved accurately.
- Only **approved fields/operators** appear in queries and responses.
- `AND`, `OR`, ranges, arrays, and literal regex queries maintain exact semantics.
- Pagination and sorting are bounded, and counts share the same filter.
- Java property ↔ BSON mapping is accurate, and performance is evaluated via `explain` rather than guesswork.

## 16. Summary of Principles

| Question | Choice to Apply |
|---|---|
| Multiple optional filters? | Collect present `Criteria` into one `Query` via `andOperator` or equivalent |
| Need to preserve `false` and `0`? | Use wrapper `Boolean`/`Long` and check `!= null` |
| Users pick a field to filter? | Public key → allowlist → fixed Java property → Spring BSON mapping |
| Users pick an operator? | Server-defined business operator enum/table, never raw BSON |
| Have OR branches? | Place tenant/authorization filters **outside OR** |
| Searching user-entered text? | `Pattern.quote` for literals; validate length and consider search indexes |
| Have date ranges? | Standardize timezone, use `[from, until)` |
| Have tag lists? | Clarify `$in` = any, `$all` = all |
| Users pick sort order? | Sort allowlist + direction validation + tie-breaker + index |
| Users pick output columns? | Projection allowlist + read-only DTO/response; never save partial entities |
| Paginated API? | Cap size/offset, keep count filter-aligned, evaluate `Page` cost |
| Slow query? | Read `explain("executionStats")` and align indexes with workload |

**Conclusion:** A good dynamic filter is not one that accepts any arbitrary input structure. It is **a bounded contract** between request and MongoDB: appending only valid conditions, always enforcing mandatory access filters, allowing only server-approved fields and operators, bounding resources, and verifying behavior against real data. This forms a safe foundation for `MongoTemplate`, custom repositories, aggregation, and search APIs as query requirements grow.

**References for your project version:** [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html), [Spring Data MongoDB — Criteria](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html), [MongoDB — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/), [MongoDB — Query and Sort Indexing](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/sort-order/), and [MongoDB — $regex](https://www.mongodb.com/docs/manual/reference/operator/query/regex/). During implementation, verify APIs and behavior against your project's actual Spring Data MongoDB, Spring Boot, and Java Driver versions.
