# Mapping Value Objects to Nested Documents

## 1. Value Objects in the MongoDB Document Model

In the **Objects and Embedding** chapter of **Spring Data MongoDB**, an essential task is representing domain **value objects** as nested documents inside a root document. This allows the Java application to maintain an expressive object model while leveraging MongoDB's document structure to query and update data via `MongoTemplate` or `MongoRepository`.

A **value object** is an object identified primarily by the *values of its attributes* rather than an independent ID. Examples:

- A shipping address consisting of street, city, and postal code.
- A monetary amount consisting of a decimal value and currency.
- An order line consisting of SKU, product title at purchase, quantity, and unit price.
- A date range consisting of start and end timestamps.

In an order, the shipping address is typically a **snapshot at the time of purchase**. When the buyer later updates their default address, the finalized address inside an existing order should not change automatically. Nesting value objects inside the order expresses this lifecycle boundary clearly.

Value objects differ from entities in several ways:

| Question | Value Object | Entity |
|---|---|---|
| How is it identified? | Set of attribute values and business meaning | Stable ID across state transitions |
| Lifecycle | Usually belongs to a parent aggregate/document | Can exist and evolve independently |
| Modification | Typically replaced with a new value rather than mutating in place | State can change while the ID remains the same |
| Examples | `ShippingAddress`, `Money` | `PurchaseOrder`, `Customer` |
| Typical storage | Embedded document inside parent | Root document with `_id`; may be referenced |

This is a **design guideline**, not a rigid rule: an address can be an entity if the business itself needs to manage, approve, and reference that address independently. Likewise, whether a class has `@Document` or not does not by itself decide whether it is a business value object.

> Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. For other versions, verify the corresponding mapping APIs/metadata. The low-level MongoDB Java Driver operates on BSON, while the main examples use Spring Data mapping.

## 2. When Should You Embed a Value Object?

MongoDB stores a document as key–value pairs where a value can be a **subdocument** or an **array of subdocuments**. An aggregate can therefore be modeled closely to how the application reads it:

~~~mermaid
flowchart TD
    O["PurchaseOrder - root document"] --> A["ShippingAddress - subdocument"]
    O --> L["items - array of OrderLine"]
    L --> M["Money - unit price per line"]
    O --> T["Money - subtotal"]
    O --> I["id, customerId, placedAt"]
~~~

Consider embedding when:

1. The value object is typically read together with its parent document.
2. The value object has no independent update lifecycle and needs no separate ID.
3. The number of nested items is **bounded by business rules**, and total document size stays controllable.
4. Fields that must change consistently can be updated together inside the same document.

Do not embed unbounded transaction histories, page views, reviews, or continuously growing event streams into a single document. MongoDB has a **16 MiB limit per BSON document**; even well below that limit, oversized documents degrade reads, writes, index management, and conflict handling.

**Embedding does not mean arbitrary duplication.** A `ShippingAddress` captured at checkout differs from the customer's current default address. Likewise, a locked-in unit price inside `OrderLine` is not synchronized when a product's catalog price changes later.

## 3. Complete Example: Aggregate with Multiple Value Objects

Let's define the types in package `com.example.orders`. The root document `PurchaseOrder` holds a shipping address, a list of order lines, and a subtotal. Value objects are modeled as **Java records** to emphasize value semantics.

### 3.1. Address as an Embedded Value Object in an Order

**ShippingAddress.java**

~~~java
package com.example.orders;

import org.springframework.data.mongodb.core.mapping.Field;

public record ShippingAddress(
        String street,
        String city,
        @Field("postal_code") String postalCode) {
}
~~~

`ShippingAddress` has neither `@Id` nor `@Document` because it does not need its own collection in this example. `@Field("postal_code")` indicates that Java property `postalCode` is stored under BSON field `postal_code`.

### 3.2. Money as a Value Object with Explicit BSON Type

**Money.java**

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record Money(
        @Field(targetType = FieldType.DECIMAL128) BigDecimal amount,
        String currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

`Money` pairs an **amount** with a **currency**. Never compare two amounts in different currencies as if they were equivalent. Using `BigDecimal` avoids binary floating-point rounding errors typical of `double` in financial calculations; `FieldType.DECIMAL128` requests storing `amount` as BSON Decimal128 when mapped.

BSON Decimal128 has precision and range bounds. Rounding rules, scale, minor units, and currency conversion remain the responsibility of the business layer. Inspect legacy data before switching storage from String or Double to Decimal128.

### 3.3. A Line Item Containing Another Value Object

**OrderLine.java**

~~~java
package com.example.orders;

public record OrderLine(
        String sku,
        String titleAtPurchase,
        int quantity,
        Money unitPrice) {
}
~~~

Each `OrderLine` contains another `Money`. This forms a **multi-level value object graph**:

~~~text
PurchaseOrder
  ├─ shippingAddress: ShippingAddress
  ├─ items: List<OrderLine>
  │    └─ unitPrice: Money
  └─ subtotal: Money
~~~

`titleAtPurchase` and `unitPrice` are finalized transaction facts. If `OrderLine` needs its own revision history, line identifier, or independent lifecycle, re-evaluate whether it is still a pure value object.

### 3.4. Root Document with Its Own Identifier

**PurchaseOrder.java**

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record PurchaseOrder(
        @MongoId(FieldType.STRING) String id,
        String customerId,
        @Field("ship_to") ShippingAddress shippingAddress,
        List<OrderLine> items,
        Money subtotal,
        Instant placedAt) {
}
~~~

`@Document(collection = "orders")` binds the aggregate root to the `orders` collection. `@MongoId(FieldType.STRING)` explicitly maps the ID to `_id` as a BSON String, preventing a string that happens to look like an ObjectId from being unexpectedly converted. `@Field("ship_to")` renames the address field, while `ShippingAddress` still keeps its Java property `postalCode`.

When saving the object below via `MongoTemplate`:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

PurchaseOrder order = new PurchaseOrder(
        "order-9001",
        "customer-101",
        new ShippingAddress("12 Example Street", "Ha Noi", "100000"),
        List.of(new OrderLine(
                "BOTTLE-500",
                "Water Bottle 500 ml",
                2,
                new Money(new BigDecimal("129000.00"), "VND"))),
        new Money(new BigDecimal("258000.00"), "VND"),
        Instant.parse("2026-11-20T08:00:00Z"));

mongoTemplate.save(order);
~~~

Assuming `mongoTemplate` is an injected bean in a service, the resulting BSON document has a structure similar to the following—dates and Decimal128 shown in **MongoDB Extended JSON**, omitting metadata like `_class` if present:

~~~json
{
  "_id": "order-9001",
  "customerId": "customer-101",
  "ship_to": {
    "street": "12 Example Street",
    "city": "Ha Noi",
    "postal_code": "100000"
  },
  "items": [
    {
      "sku": "BOTTLE-500",
      "titleAtPurchase": "Water Bottle 500 ml",
      "quantity": 2,
      "unitPrice": {
        "amount": { "$numberDecimal": "129000.00" },
        "currency": "VND"
      }
    }
  ],
  "subtotal": {
    "amount": { "$numberDecimal": "258000.00" },
    "currency": "VND"
  },
  "placedAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

A single read of `PurchaseOrder` restores value objects across multiple levels without querying separate address or currency collections. MongoDB does not enforce the Domain-Driven Design aggregate concept; the application itself decides invariant boundaries and update patterns.

## 4. What Steps Does Mapping Perform?

For an entity accessed through `MongoTemplate` or `MongoRepository`, Spring Data MongoDB typically uses `MongoMappingContext` and `MappingMongoConverter` to:

1. Resolve root document metadata, including collection name and `_id`.
2. Read property and annotation metadata for each Java type.
3. Write scalar properties, then convert each value object into a subdocument.
4. Iterate over collections such as `List<OrderLine>` to write an array of documents.
5. On read, reconstruct the root object and each nested object via the appropriate constructor or creator method.

| Java Property | BSON Location | Notes |
|---|---|---|
| `PurchaseOrder.id` | `_id` | `@MongoId(FieldType.STRING)` on the aggregate root |
| `PurchaseOrder.shippingAddress` | `ship_to` | Renamed via `@Field` |
| `ShippingAddress.postalCode` | `ship_to.postal_code` | Renamed on the nested value object |
| `PurchaseOrder.items` | `items` | BSON array |
| `OrderLine.unitPrice.amount` | `items[].unitPrice.amount` | Decimal128 value inside each element |
| `PurchaseOrder.subtotal.amount` | `subtotal.amount` | Decimal128 |
| `PurchaseOrder.placedAt` | `placedAt` | BSON Date via supported conversion |

**There is no need to place `@Document` on every value object.** Spring Data can store a regular class or record as an embedded document whenever it is a property of an aggregate root. Conversely, if you register a custom converter for a value object that writes a simple BSON scalar like String, the stored shape may **no longer be an embedded document**. Decide intentionally and test the representation.

### What Does Placing @Id on a Value Object Mean?

`@Id` is not a marker meaning "this is a MongoDB object." It designates the identifier property and carries special mapping to `_id`. Value objects that do not require independent identity usually **do not need `@Id`**; adding an ID can mislead readers about value equality semantics.

MongoDB only enforces uniqueness of `_id` per **root document in a collection**—it does not assign global IDs to embedded objects. If business requirements truly need identifying individual array elements for targeted updates, add an **application-managed element key** inside the array, or consider promoting the element to its own entity/document.

## 5. Constructor Mapping and Immutability

Value objects are commonly designed to be immutable to prevent uncontrolled state changes. Java records provide a canonical constructor and component accessors; Spring Data can use that metadata to restore objects on read.

In our example:

- `ShippingAddress("...", "...", "...")` is constructed from `street`, `city`, and `postal_code`.
- `OrderLine` is constructed from each array element's fields, including nested `Money`.
- `PurchaseOrder` is constructed once all component values have been converted.

Two records with identical component values are equal according to the generated `equals`. This fits value objects well, though remember `BigDecimal.equals` distinguishes scale—for example, `1.0` differs from `1.00` under `equals`. If the domain needs numeric equality on amounts, define normalization, exchange-rate, or comparison rules rather than relying on default `equals` as a substitute for monetary policy.

### 5.1. Using an Immutable Class Instead of a Record

For classes with multiple constructors or stricter invariant control, you can use `@PersistenceCreator` to specify how objects are restored:

~~~java
package com.example.orders;

import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Field;

public final class ContactValue {
    @Field("contact_name")
    private final String name;
    private final String phone;

    @PersistenceCreator
    public ContactValue(String name, String phone) {
        this.name = name;
        this.phone = phone;
    }

    public ContactValue(String name) {
        this(name, null);
    }

    public String getName() { return name; }
    public String getPhone() { return phone; }
}
~~~

Assuming `ContactValue` is a property on a mapped entity, the annotated constructor receives `name` and `phone` by **Java property name**; `@Field("contact_name")` handles translation to the BSON name. For regular classes, ensure constructor parameter name metadata is available, such as compiling with `-parameters`. If parameter names are missing or a property fails to materialize, reading can fail.

A value object constructor should only check pure invariants, such as rejecting blank currency codes. Avoid calling external APIs, sending emails, or writing to databases in constructors: reading a single document can instantiate many value objects.

### 5.2. Immutable Records Can Still Hold Mutable Objects

`record PurchaseOrder(..., List<OrderLine> items, ...)` only makes the **list reference** final; it does not make a mutable `ArrayList` passed into it immutable. If a caller passes a mutable list, the in-memory aggregate's state can still be altered through that list.

You can perform a defensive copy in the canonical constructor:

~~~java
public PurchaseOrder {
    items = List.copyOf(items);
}
~~~

This snippet is a constructor body placed **inside the `PurchaseOrder` record** of our example, not a separate class. It requires `items` and its elements to be non-null; if legacy documents omit the `items` field, reading them can fail. Therefore, whenever adding new constraints or constructor validation, plan a legacy data compatibility strategy.

## 6. Querying on Nested Fields

Spring Data MongoDB lets you query using **Java property paths** whenever an entity class supplies mapping context. For example, finding orders with postal code `100000`:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<PurchaseOrder> byPostalCode(
        MongoTemplate template, String postalCode) {
    Query query = Query.query(
            Criteria.where("shippingAddress.postalCode").is(postalCode));
    return template.find(query, PurchaseOrder.class);
}
~~~

Spring Data uses `@Field` metadata on `PurchaseOrder` and `ShippingAddress` to map `shippingAddress.postalCode` to **`ship_to.postal_code`** in BSON.

Queries in MongoDB shell or directly through the Java Driver must use BSON names:

~~~javascript
db.orders.find({ "ship_to.postal_code": "100000" });
~~~

Likewise, repositories can declare derived queries:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, String> {

    List<PurchaseOrder> findByShippingAddress_City(String city);
}
~~~

The underscore in `findByShippingAddress_City` explicitly separates nested property path segments in Spring Data derived method names. Do not confuse it with a BSON field name; Spring Data still maps it to `ship_to.city`.

### 6.1. Querying Inside Value Object Arrays

To find orders containing **a line item** with SKU `BOTTLE-500` and quantity at least 2:

~~~java
Query query = Query.query(
        Criteria.where("items").elemMatch(
                Criteria.where("sku").is("BOTTLE-500")
                        .and("quantity").gte(2)));

List<PurchaseOrder> matching =
        mongoTemplate.find(query, PurchaseOrder.class);
~~~

`$elemMatch` ensures **both conditions apply to the same array element**. Writing separate conditions for `items.sku` and `items.quantity` can be satisfied by two different line items within the same order.

In real applications, configure result limits, pagination, and indexes aligned with queries. Indexes on nested paths or arrays are **indexes on the root document's collection**, not separate indexes on the value object class.

~~~javascript
db.orders.createIndex({ "ship_to.postal_code": 1, placedAt: -1 });
db.orders.createIndex({ "items.sku": 1 });
~~~

The first index can serve filtering by postal code and sorting by timestamp; the second is a candidate **multikey index** for the `items` array. These are examples, not a mandate to add indexes without analyzing workload. Use `explain("executionStats")` to inspect the query plan and weigh write/index costs.

## 7. Partial Updates of Embedded Documents

A value object is a cohesive concept in the domain model, but at the BSON layer you can update either the **entire subdocument** or **a single field inside the subdocument**:

| Update Style | Behavior | When Appropriate |
|---|---|---|
| `$set: { "ship_to.city": "Da Nang" }` | Modifies only `city` inside `ship_to` | Editing one specific property allowed by business rules |
| `$set: { "ship_to": { ... } }` | Replaces the **entire** `ship_to` object | Replacing the value object cleanly per immutability semantics |
| `save(PurchaseOrder)` | Persists the aggregate per Spring Data save semantics | When business logic acts on the whole aggregate; requires concurrent write control |

Example updating the city:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean changeDestinationCity(
        MongoTemplate template, String orderId, String city) {
    Query byId = Query.query(Criteria.where("id").is(orderId));
    Update update = new Update().set("shippingAddress.city", city);
    UpdateResult result =
            template.updateFirst(byId, update, PurchaseOrder.class);
    return result.getModifiedCount() == 1;
}
~~~

Because `PurchaseOrder.class` is supplied, Spring Data maps nested property names to the right BSON fields. An update on a **single document** executes atomically at the document level in MongoDB. Note that `getModifiedCount() == 0` can mean the ID was not found *or* the value already matched the stored value; check `getMatchedCount()` too if business logic needs to distinguish them.

Replacing the **entire value object**:

~~~java
ShippingAddress replacement = new ShippingAddress(
        "35 New Street", "Da Nang", "550000");

Update update = new Update().set("shippingAddress", replacement);
mongoTemplate.updateFirst(
        Query.query(Criteria.where("id").is("order-9001")),
        update,
        PurchaseOrder.class);
~~~

Replacing the whole subdocument helps preserve invariants across `street`, `city`, and `postalCode` when they must be validated together. On the flip side, an object copy built from an earlier read can **overwrite newer updates** by another writer if applied unconditionally.

### 7.1. Concurrency and @Version on the Aggregate Root

A value object does not need its own version if it is only replaced through its parent aggregate. To handle concurrent updates on the root document, add `@Version` on the root entity for optimistic locking across Spring Data write paths that support it:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record VersionedOrder(
        @MongoId(FieldType.STRING) String id,
        @Version Long version,
        ShippingAddress shippingAddress) {
}
~~~

This is a **separate illustrative model**, not a replacement for `PurchaseOrder`. When using `save` on an entity with `@Version`, Spring Data detects concurrent modifications and throws an optimistic locking exception. Always capture and use the updated version returned from save, especially with immutable records; never reuse a stale instance to overwrite newer state.

Handcrafted `updateFirst` commands must be evaluated separately for version criteria and framework version handling; do not assume a manual update automatically provides the same concurrency check as `save`. For compare-and-set behavior, put the expected version in the query filter and update the version explicitly.

### 7.2. Value Object Arrays and Array Filters

For `items`, updating `items.0.quantity` couples logic to array index position, which breaks easily if items are reordered. If business logic must modify a specific line, pick a meaningful line identifier key (SKU if unique within an order, or an application-managed line key) and use positional operators or array filters accordingly.

Never assume `items.sku` is unique: the same SKU can appear multiple times in an order due to promotions, batches, or pricing tiers. If lines need independent updates, adding a stable `lineId` inside array items or separating into its own entity may fit better.

## 8. Nulls, Missing Fields, and Schema Evolution for Value Objects

MongoDB allows documents in the same collection to vary in structure. This directly impacts restoring immutable value objects:

~~~json
{
  "_id": "order-old",
  "customerId": "customer-101",
  "ship_to": {
    "street": "12 Example Street",
    "city": "Ha Noi"
  }
}
~~~

This legacy document lacks `ship_to.postal_code`, `items`, and `subtotal`. Record constructors may receive `null` for some reference components, whereas constructors with `Objects.requireNonNull` or `List.copyOf` will throw during restoration.

Distinguish:

- **Missing field**: the key does not exist in BSON.
- **Field present with null**: the key exists with a null value.
- **Empty subdocument**: `ship_to: {}`, distinct from `ship_to: null`.
- **Empty array**: `items: []`, distinct from missing `items`.
- **Incompatible type**: previously `subtotal` was a number, now it is a `Money` document with `amount` and `currency`.

Recommended policy:

1. Define invariants of the new value object and how historical records should be read.
2. When changing representations, implement **backward-compatible reads** during rollout or migrate/backfill before enforcing the new schema.
3. Write tests covering both old and new BSON documents; verify both read and write directions.
4. For large backfills, run checkpointed batches and monitor load; avoid rewriting historical data unnecessarily.

Do not treat new constructor validation as a migration tool. It can render the application unable to read existing orders.

## 9. Polymorphic Types, _class, and Converters

For value objects with a **concrete declared type** such as `ShippingAddress` or `Money`, Spring Data usually has enough metadata to restore the object. When a property is declared as an **interface** or base class and holds multiple subtypes at runtime, the framework may need a **type hint** to identify the subtype when reading.

Spring Data MongoDB can store type metadata such as `_class` in certain cases and supports configuring or aliasing type metadata. Never strip or alter type metadata just to make BSON "cleaner" without understanding the impact on:

- Existing polymorphic value objects.
- Reading back through interface/abstract types.
- Schema evolution when renaming Java packages or classes.
- Data written by other applications using different models.

If compatibility with external systems that do not use Java class names is needed, consider a **business discriminator** such as `kind` paired with application-controlled reading/writing converters, or appropriate type alias configurations. Changing how `_class` is stored on existing data requires testing and a migration plan.

**Custom converters** such as `@WritingConverter`, `@ReadingConverter`, and `MongoCustomConversions` are useful when a value object has a specialized representation. For example, a currency code or unit of measurement can be encoded as a scalar. Note that if a converter changes `Money` from a document to a String, queries on `subtotal.amount` and corresponding indexes will stop working unless adjusted. Always treat converter changes as schema decisions.

## 10. Testing Mapping Against Raw BSON

Unit tests on a record only verify that the Java constructor and `equals` work. To confirm Spring Data writes the right **nested fields and BSON types**, write integration tests against a real MongoDB instance. Spring Boot 3.x provides `@DataMongoTest` to focus on MongoDB mapping/repositories, though this annotation **does not start a MongoDB server on its own**. You can provide a database via Testcontainers and configure the URI matching your test setup.

Example test in package `com.example.orders`:

~~~java
package com.example.orders;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class EmbeddedValueObjectMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void persistsNestedValuesAndRestoresThem() {
        PurchaseOrder order = new PurchaseOrder(
                "order-9001",
                "customer-101",
                new ShippingAddress("12 Example Street", "Ha Noi", "100000"),
                List.of(new OrderLine(
                        "BOTTLE-500", "Water Bottle 500 ml", 2,
                        new Money(new BigDecimal("129000.00"), "VND"))),
                new Money(new BigDecimal("258000.00"), "VND"),
                Instant.parse("2026-11-20T08:00:00Z"));

        mongo.save(order);

        Document raw = mongo.getCollection("orders")
                .find(eq("_id", "order-9001"))
                .first();
        assertThat(raw).isNotNull();

        Document address = raw.get("ship_to", Document.class);
        assertThat(address.getString("postal_code")).isEqualTo("100000");
        assertThat(raw.containsKey("shippingAddress")).isFalse();

        Document subtotal = raw.get("subtotal", Document.class);
        assertThat(subtotal.get("amount")).isInstanceOf(Decimal128.class);

        PurchaseOrder restored =
                mongo.findById("order-9001", PurchaseOrder.class);
        assertThat(restored).isNotNull();
        assertThat(restored.shippingAddress())
                .isEqualTo(order.shippingAddress());
        assertThat(restored.items()).hasSize(1);
        assertThat(restored.items().get(0).unitPrice().currency())
                .isEqualTo("VND");
    }
}
~~~

Tests should isolate databases/collections so they do not depend on data from previous runs. For real projects, also cover:

| Test | What It Proves |
|---|---|
| Two-level value object readback | `ShippingAddress` and `Money` materialize properly |
| Renamed nested field | `shippingAddress.postalCode` actually persists at `ship_to.postal_code` |
| Decimal128 | `subtotal.amount` has the right BSON type instead of silently storing Double/String |
| Nested property queries | `MongoTemplate` and repositories return expected documents |
| Array queries | `$elemMatch` does not cross-match criteria across different elements |
| Whole child replacement | No stale fields linger when no longer used in a newer schema |
| Partial updates | Only target fields change; sibling fields stay intact |
| Schema compatibility | Missing/null values load per designed policy |
| Concurrency | Two concurrent updates cannot silently overwrite; version checks work |

If a query is slow, use `explain("executionStats")` to examine scanned documents, multikey indexes, sorts, and returned payload size. Embedding simplifies reads, but does not automatically make every nested query fast.

## 11. Common Mistakes When Mapping Value Objects

| Mistake | Consequence | Fix |
|---|---|---|
| Putting `@Document` and `@Id` on every child class | Blurs boundary between entities and value objects | Use only when independent identity and lifecycle are needed |
| Assuming `@Field` on nested objects does not affect queries | Queries target wrong BSON fields | Use typed queries and inspect raw BSON |
| Renaming fields without migrating data | Old documents read null or fail | Plan compatibility readers and backfills |
| Assuming records are always deeply immutable | Mutable lists or objects inside can still be mutated | Design immutable value objects and appropriate defensive copies |
| Storing money as `double` and expecting exact comparisons | Decimal precision loss and unpredictable queries | Use BigDecimal/Decimal128 per data contract |
| Overwriting `ship_to` from an old read | Clobbers recent updates | Enforce concurrency controls with versions or compare-and-set |
| Querying nested fields via driver with Java property names | Raw queries fail to match documents | Use physical BSON field names like `ship_to.postal_code` |
| Embedding unboundedly growing lists | Documents bloat and exceed BSON size limits | Bound arrays or split into separate collections |
| Stripping `_class` unexpectedly on polymorphic data | Cannot resolve subtypes when reading | Design type hints/discriminators and test migrations |
| Skipping tests against real BSON data | Bugs appear only in production queries or deployments | Write integration tests covering reads, writes, and updates |

## 12. Practice Exercises

**Exercise 1 — Value objects and field mapping.** Create a `Reservation` aggregate containing `GuestName`, `DateRange`, and `RoomPrice` as records. Persist nested documents, rename one BSON field using `@Field`, inspect the raw document, and explain why value objects do not need `@Id`.

**Exercise 2 — Querying nested data.** Extend `PurchaseOrder` with an address containing city, district, and postal code. Write repository, `MongoTemplate`, and MongoDB shell queries by postal code; explain the corresponding Java property and BSON field names.

**Exercise 3 — Arrays of value objects.** Create two order lines with the same SKU but different unit prices. Write an `$elemMatch` query finding orders containing a line with that SKU and quantity of 2 or more. Show why two separate array conditions can yield incorrect matches.

**Exercise 4 — Updates and concurrency.** Simulate two concurrent requests updating the shipping address. Compare saving the full aggregate with `save`, `$set` on a single field, and a version-conditional update; point out when an update gets overwritten.

**Exercise 5 — Legacy data.** A collection currently has `shippingAddress` with a numeric `zip` field, while the new version wants a String `postal_code`. Propose compatible reading, migration/backfill, and tests ensuring leading zeros in postal codes are not lost.

## 13. Key Takeaways

In **Spring Data MongoDB**, value objects are well suited to **embedded documents** when they carry value semantics, are read with the parent aggregate, and do not need an independent lifecycle or ID. Java records or immutable classes express the domain model clearly; `@Field` and `MappingMongoConverter` bridge Java properties to BSON names and types across nested objects and arrays.

Embedding must go hand in hand with **document size limits, snapshot policies, nested queries/indexes, document-level atomic updates, concurrency control, and schema compatibility**. Use `MongoRepository` for entity-aligned queries, `MongoTemplate` for flexible nested queries and updates, and always verify raw BSON in integration tests when guaranteeing physical storage layout.
