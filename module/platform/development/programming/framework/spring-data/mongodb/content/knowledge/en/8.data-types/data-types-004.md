# Strings, Unicode, Enums, and Stored Value Conventions

## 1. Why Do String Types and Storage Conventions Matter?

In an application using **Spring Data MongoDB**, a seemingly simple field such as a customer's name or an order status can cause long-term bugs if storage conventions are inconsistent:

- A **“Tiếng Việt”** name can be represented by multiple different Unicode code point sequences, even though it renders nearly identically.
- Comparing `"PAID"` with `"paid"`, or searching names with and without accents, depends on normalization rules and collation.
- Renaming a Java `enum` constant can render old documents unreadable if the application stores the constant name directly.
- Inconsistent BSON field naming—sometimes `customerName`, sometimes `customer_name`—causes queries, indexes, and aggregations to miss expected data.
- Representing “no status yet” inconsistently as `null`, an empty string, a code like `"unknown"`, or a missing field creates four different handling paths.

This lesson belongs to the **Data Types** chapter of the **SPRING_DATA_MONGODB** module. The goal is to use Spring Data MongoDB to **map strings and enums accurately between Java and BSON**, establish durable value conventions, practice with repositories/`MongoTemplate`, inspect actual documents, and connect those decisions to queries, indexes, aggregations, transactions, reactive access, and performance testing.

**Guiding principle:** before choosing annotations or writing queries, determine *what value is stored*, *how values are compared*, *how older versions are handled*, and *which rules apply across the entire application*.

## 2. BSON String and Java String

### 2.1. How Does MongoDB Store Strings?

MongoDB stores documents in BSON; a **BSON string** holds UTF-8 encoded text data. Java `String` represents text using UTF-16 code units, so string length or character positions in Java do not correspond one-to-one with bytes stored in MongoDB.

Example executed in `mongosh` on a test database:

```javascript
db.string_examples.insertOne({
  _id: "sample-01",
  customer_name: "Đặng Thị Ánh",
  nickname: "Ánh 😊",
  status_code: "paid",
  notes: "",
  optional_note: null
});

db.string_examples.findOne({ _id: "sample-01" });
```

The sample data highlights several distinctions:

| Field | Example | BSON Type | Meaning |
| --- | --- | --- | --- |
| `customer_name` | `"Đặng Thị Ánh"` | `string` | Accented Vietnamese string |
| `nickname` | `"Ánh 😊"` | `string` | String containing a character outside the Basic Multilingual Plane |
| `status_code` | `"paid"` | `string` | Status code defined by convention |
| `notes` | `""` | `string` | Empty string, *not* `null` |
| `optional_note` | `null` | `null` | Field is present, but value is unspecified |
| `field_not_present` | Not present | `missing` when checked via aggregation `$type` | Field is absent |

Do not rely on plain JSON display to conclude types. Use `$type` or Extended JSON to inspect actual BSON data:

```javascript
db.string_examples.aggregate([
  { $match: { _id: "sample-01" } },
  {
    $project: {
      _id: 0,
      nameType: { $type: "$customer_name" },
      notesType: { $type: "$notes" },
      optionalNoteType: { $type: "$optional_note" },
      absentType: { $type: "$field_not_present" }
    }
  }
]);
```

Expected result: `nameType` and `notesType` are both `"string"`, `optionalNoteType` is `"null"`, and `absentType` is `"missing"`.

### 2.2. There Is No Single Definition of “Character Length”

With accented characters and emoji, distinguish among:

- **UTF-8 bytes:** encoded string byte size for storage and transport.
- **UTF-16 code units:** the value of `String.length()` in Java.
- **Unicode code points:** the value of `String.codePointCount(...)`; an emoji may take one or more code points.
- **Grapheme clusters:** user-perceived characters; a single visible character may consist of multiple code points, such as a base letter plus combining marks or an emoji using zero-width joiners.

Java example:

```java
String text = "A😊";

System.out.println(text.length());                 // 3 UTF-16 code units
System.out.println(text.codePointCount(
    0, text.length()));                            // 2 code points
System.out.println(text.getBytes(
    java.nio.charset.StandardCharsets.UTF_8).length); // 5 bytes
```

In MongoDB, `$strLenBytes` counts UTF-8 bytes, while `$strLenCP` counts Unicode code points:

```javascript
db.string_examples.aggregate([
  {
    $project: {
      customer_name: 1,
      utf8Bytes: { $strLenBytes: "$customer_name" },
      codePoints: { $strLenCP: "$customer_name" }
    }
  }
]);
```

The length expressions above require valid string inputs; for documents with missing or `null` fields, handle conditions before calling them. If the UI enforces a limit of “50 user-visible characters”, limiting solely by `String.length()` or `$strLenCP` may not satisfy the rule; choose a length definition matching your purpose and test combining marks/emoji.

### 2.3. Difference Between UTF-8 Strings and Normalized Unicode

Unicode allows the same accented character to be represented in different ways. For example, **é** can exist as:

- A single precomposed code point: `U+00E9`.
- Two code points: `U+0065` (e) + `U+0301` (combining acute accent).

Visually, the two strings may look very similar, yet their byte sequences and naive comparisons differ. Vietnamese has many accented combinations, making this especially relevant when accepting input from multiple sources, copying from browsers, or syncing across systems.

Observe in Java:

```java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false

String nfc = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC
);
System.out.println(composed.equals(nfc));        // true
```

**NFC (Normalization Form C)** usually fits when storing display text in a consistent representation. **NFD** decomposes characters and combining marks; **NFKC/NFKD** also perform compatibility transformations and should not be applied unconditionally when visual/form distinctions carry business meaning.

Certain strings such as access keys, digital signatures, passwords, external reference codes, or legal content may require preserving every code unit verbatim. **Normalization must follow each field's contract**: do not apply one rule blindly to every string.

## 3. Choosing Conventions for Text Data

### 3.1. Distinguish Display Text, Identifiers, and Search Keys

The following types of strings have different requirements:

| Value Category | Example | Rules to Define |
| --- | --- | --- |
| Display text | `customer_name = "Đặng Thị Ánh"` | Preserve accents and user casing; NFC can be applied if the contract permits |
| Identifier / business code | `order_code = "ORD-2026-0001"` | Format, character set, letter case, uniqueness, and mutability |
| Auxiliary search key | `customer_name_key = "đặng thị ánh"` | Generated by a fixed rule; used solely for filtering/searching, never replacing display text |
| Enum code | `status_code = "paid"` | A stable code from a valid set of values |
| Verbatim data | Content digitally signed or issued by a third-party system | Do not alter, normalize, or strip characters if doing so breaks integrity |

Do not use `customer_name_key` to print the customer's name on an invoice. The original name is preserved for display; the search key can evolve with the search strategy.

### 3.2. Controlled Normalization at the Write Boundary

Example Java helper constructing a search key from a user's name. Simple rule: strip leading/trailing Unicode whitespace via `strip()`, normalize to NFC, and lowercase with `Locale.ROOT`. Do not strip accents or alter internal spaces, as that requires a dedicated business decision:

```java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;

public final class NameText {
    private NameText() {}

    public static String displayName(String input) {
        Objects.requireNonNull(input, "customer name is required");

        String value = Normalizer.normalize(
            input.strip(), Normalizer.Form.NFC
        );

        if (value.isBlank()) {
            throw new IllegalArgumentException("Customer name is blank");
        }
        return value;
    }

    public static String searchKey(String displayName) {
        return Normalizer.normalize(
            displayName, Normalizer.Form.NFC
        ).toLowerCase(Locale.ROOT);
    }
}
```

`strip()` handles whitespace as Java defines Unicode whitespace, which does not mean removing every invisible character, zero-width space, or every whitespace variant worldwide. `Locale.ROOT` produces stable lowercasing independent of the host machine's locale; it is **not equivalent** to natural-language comparison or full Unicode case folding. If you need language-specific Vietnamese search semantics, test **collation** or a dedicated search engine.

**For business codes:** define a dedicated policy. For instance, are voucher codes case-sensitive? If not, canonicalize once using a published rule. Do not automatically uppercase all SKUs, tokens, or partner-issued codes; some systems treat `"AbC"` and `"abc"` as two distinct values.

### 3.3. Store Both Display Text and Search Key When Needed

A customer document can carry both:

```javascript
db.customers.insertOne({
  _id: "customer-01",
  display_name: "Đặng Thị Ánh",
  display_name_key: "đặng thị ánh",
  preferred_locale: "vi"
});
```

Here `display_name_key` is **derived** data. The application must regenerate it **in the same update operation** whenever the display name changes; updating the two fields in separate operations risks divergence if one fails.

```javascript
db.customers.updateOne(
  { _id: "customer-01" },
  {
    $set: {
      display_name: "Đặng Thị Ánh Nguyễn",
      display_name_key: "đặng thị ánh nguyễn"
    }
  }
);
```

A single `updateOne` on one document is atomic. If derived keys must stay synchronized across multiple write paths, centralize the logic in a shared service or add extra safeguards; MongoDB does not know which Java rule generated the derived key.

## 4. String Comparison: Equality, Collation, and Search

### 4.1. Direct Comparison Is Not Linguistic Search

Unless a different collation is configured, MongoDB uses **simple binary comparison**. Consequently, values differing in letter case or Unicode encoding may not be treated as equal:

```javascript
db.customers.find({ display_name: "Đặng Thị Ánh" });

// Different letter case:
db.customers.find({ display_name: "đặng thị ánh" });
```

Do not assume MongoDB will automatically strip Vietnamese accents or perform fuzzy matching. Define clearly whether the product wants:

- **Exact match:** exact stored string per the normalization convention.
- **Case-insensitive match:** ignoring uppercase/lowercase differences.
- **Accent-insensitive match:** whether accents are ignored; in Vietnamese, stripping accents often collapses distinct names.
- **Prefix/full-text/fuzzy search:** extended search requirements needing dedicated design.

### 4.2. MongoDB Collation

MongoDB provides **collation** to compare/sort strings according to locale rules and comparison strength. Example for Vietnamese:

```javascript
db.customers.find({ display_name: "đặng thị ánh" })
  .collation({ locale: "vi", strength: 2 });
```

At `strength: 2`, collation typically ignores case differences while still considering accent differences (unless other options alter that behavior). `strength: 1` typically ignores accent differences in primary comparisons as well; test specific Vietnamese word pairs before using it to merge values or enforce uniqueness.

**Collation does not replace input normalization rules.** Verify actual behavior against NFC/NFD, accents, the letter `đ`, whitespace, and typical user inputs. No single collation setting fits every kind of name, address, SKU, and business code.

### 4.3. Indexes Must Match the Query's Collation

If you frequently look up names case-insensitively, you can create an index with the same collation in a test database:

```javascript
db.customers.createIndex(
  { display_name: 1 },
  { collation: { locale: "vi", strength: 2 } }
);

db.customers.find({ display_name: "đặng thị ánh" })
  .collation({ locale: "vi", strength: 2 })
  .explain("executionStats");
```

A query aiming to use a collation index must match the index's collation (especially for string keys). A `simple` index and a locale-specific index are not interchangeable. Use `explain("executionStats")` to observe the execution plan, index keys/documents examined, timing, and sort satisfaction.

If you create a **unique index with collation**, values treated as equal under that collation will be rejected on insert/update. That is a business decision; avoid accidentally treating two distinct customer names as one identity. For accounts/usernames, define a separate canonical key and uniqueness rule rather than placing unique constraints directly on display names.

### 4.4. Regex Does Not Automatically Benefit from Collation

Queries like:

```javascript
db.customers.find({
  display_name: { $regex: "^đặng", $options: "i" }
});
```

use case-insensitive regex, yet `$regex` **is not collation-aware in the way a collation equality match is**, and typically cannot leverage case-insensitive collation indexes effectively. For incremental search features, consider normalized search keys, prefix indexes, or an appropriate full-text/search engine. Avoid accepting raw user-supplied regex without length bounds, escaping, and cost controls.

## 5. Java Enums When Persisted to MongoDB

### 5.1. Default Behavior: Enums Usually Persist by Constant Name

In standard Spring Data MongoDB mapping, a Java enum is stored as a BSON string using the **enum constant name** (equivalent to `name()`), for example:

```java
public enum PaymentStatus {
    PENDING,
    PAID,
    REFUNDED
}
```

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.annotation.Id;

@Document(collection = "payments")
public record PaymentDocument(
    @Id String id,
    PaymentStatus status
) {}
```

When written via a repository with default configuration, you might observe:

```javascript
{
  "_id": "pay-001",
  "status": "PAID"
}
```

This is a **document example**, not a runnable `mongosh` command. If custom converters are registered, enum storage may differ. Do not guess the BSON type solely from the `enum` keyword in Java; check `$type` or the raw document after writing.

### 5.2. Why Is Persisting `enum.name()` Risky?

Suppose in a later version a developer renames `PENDING` to `WAITING_FOR_PAYMENT` for clarity. MongoDB still holds `"PENDING"` in older documents. When the converter tries to map the old string onto the new enum, reading can fail because no constant shares that name anymore.

Code changes to consider:

| Code Change | Impact When Storing Default Enum Names |
| --- | --- |
| Renaming `PAID` to `COMPLETED` | Legacy data containing `"PAID"` may fail to decode |
| Removing an old constant | Older documents still contain that value |
| Adding a new constant | Older code may fail to read documents written by newer code |
| Reordering enum constants | Does not affect string names, though dangerous if anything elsewhere stores ordinals |
| Merging/splitting statuses | Requires migration and explicit business rules |

**Never persist `enum.ordinal()`** as a long-term data contract if constants may ever be reordered, added, or removed. Inserting one new constant in the middle shifts the meaning of previous numbers.

### 5.3. Decoupling Stable Codes from Enum Names

A maintainable design separates:

- **Java constant name:** used in code; can be renamed during refactoring.
- **Storage code (`code`):** part of the data contract; versioned and not changed arbitrarily.
- **Display label:** locale/UI-dependent; never used as an identifier.

Example:

```java
public enum OrderStatus {
    WAITING_FOR_PAYMENT("pending"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unsupported status code: " + code
        );
    }
}
```

If you rename `WAITING_FOR_PAYMENT` to `AWAITING_PAYMENT`, the code `"pending"` stays intact. This decouples Java code refactoring lifecycles from the BSON contract.

In systems that must read historical data from very old versions, `fromCode` can support aliases under an explicit migration plan—for example mapping both `"PENDING_PAYMENT"` and `"pending"` to one business state during transition. Document which aliases exist and when they will be retired; **never silently map unknown codes to `PAID`**.

### 5.4. Do Not Use Display Labels as Enum Codes

Do not store `"Đã thanh toán"` as the primary status code if the product may change languages, revise wording, or integrate multiple services. Instead:

```text
Storage code:        "paid"
Java constant name:  OrderStatus.PAID
Vietnamese label:    "Đã thanh toán"
English label:       "Paid"
```

Labels can be translated at the UI layer based on the status code. Storage codes belong to a locale-independent value set.

## 6. Designing Spring Data MongoDB Documents with Stable Codes

### 6.1. Explicit String Code Mapping

Example order storing customer name, search key, and status code. Store the code string in the persisted entity to keep BSON data stable, while business logic converts via `OrderStatus`:

```java
import java.time.Instant;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("customer_name")
    String customerName,

    @Field("customer_name_key")
    String customerNameKey,

    @Field("status_code")
    String statusCode,

    @Field("created_at")
    Instant createdAt
) {
    public OrderStatus orderStatus() {
        return OrderStatus.fromCode(statusCode);
    }

    public static OrderDocument create(
        String id,
        String customerName,
        OrderStatus status,
        Instant createdAt
    ) {
        String display = NameText.displayName(customerName);
        return new OrderDocument(
            id,
            display,
            NameText.searchKey(display),
            status.code(),
            createdAt
        );
    }
}
```

In this snippet, `@MongoId(FieldType.STRING)` instructs storing `id` as a BSON string in `_id`. `@Field` defines explicit BSON names, avoiding mixing camelCase and snake_case. `OrderStatus` and `NameText` from the preceding examples are supporting Java types for this entity.

If the application prefers using `OrderStatus` directly as a Java field instead of `String`, you can write Spring Data `@WritingConverter` and `@ReadingConverter` implementations to translate between the enum and the code string. When doing so, register the converters in `MongoCustomConversions`, assess any impact on other enums, and test round-trips thoroughly. This lesson uses **explicit String codes** to avoid introducing unintended global converters.

### 6.2. Writing and Reading via Repository

```java
import java.time.Instant;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
```

In a service with `OrderRepository` injected:

```java
OrderDocument saved = orderRepository.insert(
    OrderDocument.create(
        "order-1001",
        "Đặng Thị Ánh",
        OrderStatus.PAID,
        Instant.parse("2026-11-20T01:00:00Z")
    )
);

OrderDocument reloaded = orderRepository
    .findById(saved.id())
    .orElseThrow();

System.out.println(reloaded.orderStatus()); // PAID
```

Expected document shape after persisting:

```javascript
{
  "_id": "order-1001",
  "customer_name": "Đặng Thị Ánh",
  "customer_name_key": "đặng thị ánh",
  "status_code": "paid",
  "created_at": ISODate("2026-11-20T01:00:00Z")
}
```

Depending on Spring Data MongoDB configuration, the document may also include the `_class` metadata field. This example does not assume every setup strips that type hint. Actual values must be read back from the collection.

### 6.3. Querying with `MongoTemplate` Using Java Property Names

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findPaid(MongoTemplate template) {
    Query query = Query.query(
        Criteria.where("statusCode").is(OrderStatus.PAID.code())
    );
    return template.find(query, OrderDocument.class);
}
```

When Spring Data builds the query using `OrderDocument` mapping metadata, Java property `statusCode` translates to BSON field `status_code`. In `mongosh`, however, you must use the stored field name:

```javascript
db.orders.find({ status_code: "paid" });
```

Do not confuse a raw query `{ statusCode: "paid" }` with a `MongoTemplate` query using the Java property name; raw queries do not inspect annotations to rename fields.

### 6.4. Conditional Status Updates Preserving Conventions

If an order may only transition from `pending` to `paid`, use a conditional update to avoid overwriting a status changed by a concurrent request:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import com.mongodb.client.result.UpdateResult;

public void markPaid(MongoTemplate template, String id) {
    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("statusCode").is(OrderStatus.WAITING_FOR_PAYMENT.code())
    );

    Update update = new Update()
        .set("statusCode", OrderStatus.PAID.code());

    UpdateResult result = template.updateFirst(
        query, update, OrderDocument.class
    );

    if (result.getMatchedCount() != 1) {
        throw new IllegalStateException(
            "Order in pending status not found"
        );
    }
}
```

A single-document write in MongoDB is atomic, and the status predicate rejects concurrent transitions that are no longer valid. It does not replace multi-document transactions when a workflow must modify multiple collections. For external payment reconciliation, design dedicated idempotency and confirmation workflows.

## 7. Field Naming and Stored Value Conventions

A convention should be clear enough that Java developers, `mongosh` operators, and analytics systems all interpret the same data identically.

### 7.1. BSON Field Names

Example choosing **snake_case** for MongoDB fields and camelCase for Java properties:

| Java Property | BSON Field | Expected BSON Type |
| --- | --- | --- |
| `id` | `_id` | `string` (per `@MongoId(FieldType.STRING)`) |
| `customerName` | `customer_name` | `string` |
| `customerNameKey` | `customer_name_key` | `string` |
| `statusCode` | `status_code` | `string` |
| `createdAt` | `created_at` | `date` |

This is an **example convention**, not a mandatory MongoDB requirement. A system already using camelCase consistently can keep using it. What matters is consistency, documentation, and avoiding renames without a migration plan.

Never turn arbitrary user input directly into **dynamic field names**. Special characters such as dots, `$`, and field-path rules complicate querying, updating, and import/export; dynamic keys need a clear strategy such as arrays of `{key, value}` pairs or controlled maps.

### 7.2. Stored Values Must Have a Contract

Example contract for `status_code`:

| Stored Code | Meaning | Example Transition |
| --- | --- | --- |
| `"pending"` | Order awaiting payment confirmation | To `"paid"` or `"cancelled"` |
| `"paid"` | Payment confirmed | Fulfillment steps managed in appropriate fields/workflows |
| `"cancelled"` | Order cancelled | Typically a terminal business state |

These codes are **examples** for learning schema design; do not assume real domains only have three states or allow identical state transitions.

Pick a consistent value style, such as lowercase ASCII with underscores for multi-word codes: `"awaiting_payment"`, `"partially_refunded"`. Do not mix `"PAID"`, `"Paid"`, `"Đã thanh toán"`, and `1` in the same field, because their equivalence exists only in the developer's head, not in BSON.

### 7.3. Null, Missing, Empty, and Unknown Must Be Defined

The four representations below have different meanings:

```javascript
{ "_id": "a", "status_code": "pending" }
{ "_id": "b", "status_code": "" }
{ "_id": "c", "status_code": null }
{ "_id": "d" }
```

In real data:

- `"pending"`: a specific recognized status.
- `""`: empty string; should not be implicitly interpreted as “unpaid” unless specified.
- `null`: field is present without a value.
- `missing`: document lacks the field, possibly from an older schema version.

MongoDB's query `{ status_code: null }` matches both null values and missing fields. To distinguish them, use `$type` or `$exists`:

```javascript
db.orders.find({ status_code: { $type: "null" } });
db.orders.find({ status_code: { $exists: false } });
db.orders.find({ status_code: "" });
```

If business rules require the status field to always be valid, reject null/empty on write, add validation, and prepare a backfill plan for legacy data. **Never default to `"paid"`** when data is missing or an unrecognized code appears; that can cause severe payment errors.

## 8. Inspecting Actual BSON Data

### 8.1. Reading Raw BSON After Writing via Spring Data

A repository returning the right entity does not prove BSON actually uses the desired field names and types. Spring Data can translate on both read and write. After saving, use `MongoTemplate.getCollection(...)` to read directly through the driver:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;

public void inspectRaw(
    MongoTemplate template,
    String id
) {
    Document raw = template.getCollection("orders")
        .find(eq("_id", id))
        .first();

    if (raw == null) {
        throw new IllegalStateException("Document does not exist");
    }

    System.out.println(raw.toJson());
    System.out.println(raw.keySet());
    System.out.println(raw.get("customer_name"));
    System.out.println(raw.get("status_code").getClass().getName());
}
```

This example assumes a connection to a test database. `getCollection("orders")` returns the driver collection, which does not automatically map to Java entities. Printing `Document.toJson()` shows the shape of the data, while checking exact BSON types can be done with `$type` and canonical Extended JSON in `mongosh`.

### 8.2. Extended JSON and `$type`

```javascript
const order = db.orders.findOne({ _id: "order-1001" });

if (order != null) {
  print(EJSON.stringify(order, null, 2, { relaxed: false }));
}

db.orders.aggregate([
  { $match: { _id: "order-1001" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      nameType: { $type: "$customer_name" },
      keyType: { $type: "$customer_name_key" },
      statusType: { $type: "$status_code" },
      createdAtType: { $type: "$created_at" }
    }
  }
]);
```

With the entity and mapping above, expected results are `"string"` for ID, name, search key, and status code, and `"date"` for timestamp. If `_id` is ObjectId or `status_code` is a number/different string, inspect the actual write path and active converters.

### 8.3. Profiling Inconsistencies in a Collection

After a migration or application change, the same field may hold multiple types and codes. Group to inspect:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        type: { $type: "$status_code" },
        value: "$status_code"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

When grouping by `value`, remember this is an aggregation expression; missing fields, nulls, and result rendering may require separating via `$type` as shown. On large datasets, this pipeline can be resource-intensive and should run within an appropriate scope or test/replica environment.

If `"PAID"`, `"paid"`, and `"Đã thanh toán"` coexist, **do not bulk-rewrite immediately**. First identify the canonical code, any app versions still writing old values, transitional read logic, and a rollback plan.

## 9. How Do Indexes and Queries Affect String/Enum Conventions?

### 9.1. Indexing Status Codes and Timestamps

An admin dashboard often lists the newest orders in `paid` status:

```javascript
db.orders.createIndex({
  status_code: 1,
  created_at: -1
});

db.orders.find({ status_code: "paid" })
  .sort({ created_at: -1 })
  .limit(20)
  .explain("executionStats");
```

This is an example for a test database. If application code uses Java field `statusCode` with `@Field("status_code")`, raw MongoDB indexes must target the BSON name `status_code`. Index selection should reflect real query shapes, status distribution skew, sort requirements, and actual statistics; do not assume every query needs its own dedicated index.

Enum codes belong to a small value set, giving status fields low selectivity in some systems. Pairing with `created_at`, `customer_id`, or other predicates depending on query patterns may be more useful than a single-field index; evaluate with `explain` and realistic data volumes.

### 9.2. Letter Case, Collation, and Uniqueness

For normalized status codes like `"paid"`, **store a single canonical form** rather than applying language-specific collation. For display names, locale and matching collation indexes may be warranted as discussed in Section 4.

Example **unique index** on a canonicalized username:

```javascript
db.accounts.createIndex(
  { username_key: 1 },
  { unique: true }
);
```

This assumes `username_key` is generated by the application under a fixed contract and is never missing on managed accounts. A unique index can allow multiple documents missing the field depending on index type and options, so required fields should combine validation and proper index design. Do not apply identical rules to usernames, emails, and personal names; each has distinct identity semantics.

### 9.3. Aggregating by Enum Code

Example counting orders by status:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status_code",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } }
]);
```

If the field holds variants like `"PAID"`, `"paid"`, and `"Paid"`, grouped output will fail to represent a unified status contract. Temporary transformations in pipelines can patch reports, but fix the root cause producing non-canonical values rather than only merging them at report time.

## 10. Controlling Data with Validation and Migration

### 10.1. Server-Side Schema Validation in MongoDB

MongoDB supports `$jsonSchema` validators. Example configuration fragment for the `orders` collection:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["customer_name", "status_code", "created_at"],
    properties: {
      customer_name: { bsonType: "string" },
      customer_name_key: { bsonType: "string" },
      status_code: {
        bsonType: "string",
        enum: ["pending", "paid", "cancelled"]
      },
      created_at: { bsonType: "date" }
    }
  }
}
```

The snippet above is a **validator fragment**, not a complete `mongosh` command. Integrate it via your environment's schema management workflow and account for legacy documents before enabling strict validation levels/actions. A validator does not automatically know how `customer_name_key` is derived from `customer_name`; cross-field invariants must still be enforced by the application and verified by tests.

Beyond database validators, use API/service-layer validation to reject invalid codes as soon as requests arrive. **Never trust client-supplied status codes** for privileged workflow transitions such as payment confirmation; a code may be type-valid while still being an illegal state transition.

### 10.2. When Stored Enum Codes Must Change

Suppose legacy data stores `"PENDING"` and newer versions want `"pending"`. A typical process requires:

1. Identifying application versions still reading/writing `"PENDING"`.
2. Building controlled compatibility reading if two versions run concurrently during rollout.
3. Dry-running the conversion on a test database, recording document counts and unexpected values.
4. Coordinating code rollout, switching write paths to canonical codes, and migrating data in safe order.
5. Inspecting `$type`, `status_code` distribution, queries, and statistics post-migration.
6. Removing aliases and temporary rules once old data is confirmed cleaned up.

An `updateMany` command can rewrite unambiguous values, scoped strictly to the right collection, filter, and migration phase. Never run it on production data without verifying compatibility and rollback plans.

### 10.3. Versioning Unicode Normalization Conventions

If the application originally only called `trim` on names and later adopted NFC or generated `customer_name_key`, older documents may not satisfy the new rule. One option is adding `text_normalization_version` or tracking versions through migrations when differences impact search/indexes.

Avoid running `lowercase` or stripping accents across source display data to “clean” it, as that destroys content that should be preserved. When new search requirements emerge, build derived keys from display data using a consistent rebuild strategy and reconcile record counts before/after.

## 11. Testing and Diagnosing Edge Cases

### 11.1. What Should a Test Suite Protect?

| Scenario | What to Verify |
| --- | --- |
| Accented Vietnamese names | Read/write preserves expected display text and Unicode code points |
| NFC and NFD forms of the same name | Normalized consistently if the field contract specifies NFC |
| Names containing non-BMP emoji | Not split mid-surrogate pair; length validated using the right metric |
| Empty/blank/null/missing strings | Validation and reading logic distinguish each case accurately |
| Case-insensitive name lookup | Query, collation, and index agree on matching rules |
| Java enum renamed while stored code unchanged | Old data still decodes via stable code |
| Unknown enum code encountered from legacy data | Detected or routed through defined compatibility handling |
| Persisted via repository | Raw BSON uses `customer_name`, `status_code`, and expected types |
| Name update | `customer_name_key` updates atomically alongside display name |
| Concurrent status transition requests | Disallowed state transitions do not overwrite newer statuses |

### 11.2. Java Tests for Unicode and Enums

JUnit 5 example:

```java
import java.text.Normalizer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TextAndCodeTest {

    @Test
    void nfcMakesEquivalentAccentedTextEqual() {
        String nfd = Normalizer.normalize(
            "Tiếng Việt", Normalizer.Form.NFD
        );
        String nfc = NameText.displayName(nfd);

        assertEquals(
            Normalizer.normalize("Tiếng Việt", Normalizer.Form.NFC),
            nfc
        );
    }

    @Test
    void enumCodeIsIndependentOfDisplayLabel() {
        assertEquals("paid", OrderStatus.PAID.code());
        assertEquals(OrderStatus.PAID, OrderStatus.fromCode("paid"));
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderStatus.fromCode("Đã thanh toán")
        );
    }
}
```

Unit tests like these verify Java rules. To ensure Spring Data MongoDB persists the expected BSON, write **integration tests against a real MongoDB** (such as Testcontainers), persist via the repository, inspect raw documents via `MongoTemplate.getCollection(...)` or `mongosh`, and confirm `status_code` is a BSON string, field names match, and Unicode strings round-trip faithfully.

Example integration assertion snippet inside a MongoDB-configured test:

```java
OrderDocument input = OrderDocument.create(
    "unicode-check-01",
    "Đặng Thị Ánh 😊",
    OrderStatus.PAID,
    java.time.Instant.parse("2026-11-20T01:00:00Z")
);
orderRepository.insert(input);

org.bson.Document raw = mongoTemplate
    .getCollection("orders")
    .find(com.mongodb.client.model.Filters.eq(
        "_id", "unicode-check-01"
    ))
    .first();

org.junit.jupiter.api.Assertions.assertNotNull(raw);
org.junit.jupiter.api.Assertions.assertEquals(
    "paid", raw.getString("status_code")
);
org.junit.jupiter.api.Assertions.assertEquals(
    "Đặng Thị Ánh 😊", raw.getString("customer_name")
);
```

This sample assumes `orderRepository` and `mongoTemplate` are injected in the test, an isolated test database is configured, and the document ID does not yet exist. This is a test-authoring guide, not output from a test run.

### 11.3. Diagnosing Real-World Issues

| Symptom | Investigation Steps |
| --- | --- |
| Names look alike but `equals` query misses | Check NFC/NFD, letter case, accents, invisible whitespace, collation |
| Vietnamese sorting looks wrong | Check locale/strength/collation on query and index |
| Reading legacy documents fails after enum rename | BSON stored old `enum.name()`; missing converter or compatibility mapping |
| Report counts `PAID` and `paid` separately | Inconsistent enum code conventions |
| `MongoTemplate` query finds data while raw `mongosh` does not | Java property name mapped via `@Field`; raw query must use BSON name |
| Name truncated inside emoji | Enforced length in UTF-16 code units instead of appropriate length metric |
| Unique index rejects distinct names | Collation or canonicalization merges values business treats as distinct |
| Regex search is slow | Regex query cannot leverage collation equality index efficiently; missing bounds/prefix |
| Index unused even though field exists | Wrong BSON name, collation mismatch, key order, or low selectivity |
| Reactive and imperative paths write different forms | Different converters/clients/configs; inspect raw BSON from both paths |

**Performance:** When analyzing string queries, use `explain("executionStats")` to observe `COLLSCAN`/`IXSCAN`, documents/keys examined, and sort stages. Collation indexes can take more storage than simple binary indexes; avoid adding multiple indexes just to work around inconsistent casing conventions. Standardizing codes at write time reduces long-term complexity.

**Reactive access:** `ReactiveMongoRepository` and `ReactiveMongoTemplate` follow the same string/enum mapping rules when configured with identical converters. Reactive execution does not automatically normalize Unicode, generate canonical codes, or fix migration bugs. When an operation updates multiple documents in a single business flow, design consistency/transactions and retries suited to your MongoDB deployment; reactive transactions may require `ReactiveMongoTransactionManager`.

## 12. String and Enum Data Design Checklist

1. Classify each field as **display text**, **business code**, **search key**, or **verbatim data**.
2. Decide Unicode normalization rules (if any) per field; test NFC/NFD, combining marks, and emoji.
3. Define letter case, accent, and whitespace rules, as well as locale-aware search behavior.
4. Distinguish null, missing, empty string, and `unknown` codes; only use each when it has explicit business meaning.
5. Define durable enum codes independent of Java constant names or UI display labels.
6. Standardize BSON field names, use `@Field` deliberately, and understand repository/`MongoTemplate` mapping.
7. Choose indexes and collation matching real queries; verify with `explain`.
8. Inspect persisted BSON documents and Java round-trips rather than relying solely on annotations.
9. Plan legacy data compatibility when changing names, Unicode forms, or enum value sets.
10. Test edge cases and monitor live data to detect inconsistent values.

A solid storage convention keeps **Vietnamese strings intact**, **enum codes stable across code releases**, and **MongoDB queries aligned with actual BSON values**. In Spring Data MongoDB, combine explicit mapping, controlled normalization, raw data inspection, matching indexes/collation, and integration tests so systems can evolve without losing data meaning.
