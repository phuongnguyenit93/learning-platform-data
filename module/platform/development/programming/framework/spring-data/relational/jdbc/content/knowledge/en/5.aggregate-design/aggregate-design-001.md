# Entities, Value Objects, and Domain Model Immutability

When building applications with **Spring Data JDBC**, designing Java classes is not just about mapping columns in a database table. The model needs to express **which objects have their own identity**, **which values only matter by their content**, **which business rules must always hold true**, and **who is allowed to change state**. This is the foundation for defining *aggregate* boundaries, designing repositories, and preventing database data from entering an invalid state.

This lesson uses an order placement example to explain three closely related concepts: **entity**, **value object**, and **immutability**. The examples are placed in the context of Spring Data Relational JDBC, where aggregates are persisted using SQL without a JPA-style persistence context or change tracking.

## 1. Viewing Data Through Business Language

Suppose a store has an order consisting of an order number, customer, order lines, total amount, and status. A purely data-centric organization is to create a class containing getters and setters corresponding to each column. That approach easily leads to a situation where any component in the application can arbitrarily modify the status or total amount.

A *domain model* approach asks different questions:

- Are two orders with the same total amount and status the same order?
- Can two amounts of `100_000 VND` created from two different calls be considered the same value?
- Can a confirmed order return to the newly created state?
- If an order line is modified, must the total amount change accordingly?
- Which changes need to be saved within the same transaction to maintain consistency?

The answers help distinguish **identity**, **value equality**, **invariant**, and **aggregate boundary**. These concepts are related to one another, but they are not synonymous with tables, primary keys, or annotations.

### Core Terminology

| Term | Meaning in the domain model | Example |
| --- | --- | --- |
| Entity | An object with continuous identity over time, even when attributes change | Order number `ORD-2026-0042` |
| Value object | An object identified by attribute values, needing no separate identity | An amount consisting of monetary units and currency code |
| Invariant | A rule that must hold true in all valid states of the model | Do not confirm an order with no order lines |
| Aggregate | A group of entities/value objects that share a consistency boundary when changing | An order together with the order lines belonging to it |
| Aggregate root | The entity acting as the entry point and controlling changes to the aggregate | `PurchaseOrder` |
| Immutability | Once created, an object's state cannot be modified directly | `Money.add(...)` returns a new `Money` object |

## 2. Entity: Identity Matters More Than Attributes

An **entity** is an object where we need to distinguish "that very object" over time. An order remains the same original order after transitioning from `DRAFT` to `CONFIRMED`. Two orders with the same customer, the same amount, and the same status can still be two different entities.

~~~text
Order A: ID = 101, status DRAFT, total = 250_000 VND
     |
     | confirm
     v
Order A: ID = 101, status CONFIRMED, total = 250_000 VND

Order B: ID = 102, status CONFIRMED, total = 250_000 VND
~~~

A before and after confirmation is the same entity. A and B are two different entities even though several attributes are equal.

### 2.1. Business Identity and Technical Key

An entity may have:

- **Technical key**: for example, a database-generated `id BIGINT` to identify the data row.
- **Business identity**: for example, `orderNumber` used by customers and staff for lookup.

These two values can play overlapping roles in a simple model, but they are not necessarily the same. An `id` might only appear after saving to the database, whereas `orderNumber` has already been assigned beforehand.

You should not assume that every object with an `id` is an entity in the domain sense. Conversely, a domain entity may not yet have a database key while in a newly created state.

### 2.2. Entity Equality

In domain analysis, comparing entities means comparing **stable identity**, not all fields. However, implementing Java `equals()`/`hashCode()` for entities using database-generated IDs requires caution:

- Two newly created entities that both have `id == null` do not thereby become the same entity.
- An object added to a `HashSet` and only assigned an ID afterward can have its hash change if `hashCode()` depends on the ID.
- Comparison based solely on `id` also needs to consider entity type scope and ID uniqueness.

There is no single `equals()` formula that applies to every domain. You can use an immutable business identity if it is truly unique and assigned from the start; or keep Java reference identity for entities and use an explicit ID comparison method where needed. The decision must fit the entity lifecycle.

### 2.3. An Entity Is Not Synonymous With a Table

An entity may be stored in a table, but **an entity belongs to the domain model**, whereas a table is a storage structure. With Spring Data JDBC:

- The aggregate root is typically mapped to the main table.
- Child entities belonging to the aggregate can be stored in a child table with a foreign key pointing to the root.
- Certain value object attributes can be embedded as multiple columns in the entity's table.

Splitting tables to optimize data storage does not by itself determine the aggregate boundary; that boundary originates from business consistency rules.

## 3. Value Object: Content Matters More Than Identity

A **value object** represents a concept identified by **value**, such as `Money`, `EmailAddress`, `DateRange`, or `ShippingAddress`. Two value objects of the same type, with equal content and obeying the same business rules, can be treated as equivalent without needing separate IDs.

~~~text
Money(100_000, "VND") == Money(100_000, "VND")  // equal by value
Money(100_000, "VND") != Money(100_000, "USD")  // different currency
~~~

Good value objects typically have these characteristics:

1. **No independent identity** to track over time.
2. **Immutable after creation**: operations that "modify" return a new value.
3. **Self-validating**: prevent constructing states that violate rules.
4. **Carry domain behavior**: for example, adding money, checking matching currencies, checking overlapping date ranges.
5. **Compared by value** rather than by object memory address.

### 3.1. `Money` Example Using a Java Record

~~~java
import java.util.Locale;
import java.util.Objects;

public record Money(long minorUnits, String currency) {

    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Amount must not be negative");
        }

        currency = Objects.requireNonNull(currency, "currency")
                .trim()
                .toUpperCase(Locale.ROOT);

        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Currency code must consist of three letters");
        }
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Cannot add two different currencies");
        }
        return new Money(Math.addExact(minorUnits, other.minorUnits()), currency);
    }
}
~~~

This example assumes **non-negative** amounts represented by `minorUnits`: the smallest unit for the currency, such as cents for USD or dong for VND. You should not assume every currency has two decimal places. The three-letter check only validates the code format, not whether the code belongs to a valid currency list; if the domain requires it, an appropriate policy must be added.

Usage:

~~~java
Money a = new Money(150_000, "vnd");
Money b = new Money(50_000, "VND");
Money total = a.add(b);

System.out.println(total);                // Money[minorUnits=200000, currency=VND]
System.out.println(a);                    // Money[minorUnits=150000, currency=VND]
System.out.println(
        a.equals(new Money(150_000, "VND"))
);                                       // true
~~~

`a` remains unchanged after the addition. A Java record automatically provides accessors, `equals()`, `hashCode()`, and `toString()` based on its components. Normalization logic in the compact constructor ensures equivalent inputs have a consistent representation.

### 3.2. When Should a Concept Be a Value Object?

A shipping address stored per order and changed by replacing the entire address is usually well suited as a value object. However, a "registered address" with an ID, verification history, and its own lifecycle can be an entity in a different domain.

The important criterion is **whether the business needs to track its separate identity and history**, not merely whether the object has many data fields.

Examples:

| Concept | Usually is | Reason |
| --- | --- | --- |
| Order | Entity | Needs to track the same order across multiple states. |
| Order line in an order | Child entity or value object, depending on rules | If individual lines need editing/deleting by a stable ID, a child entity is useful; if only the entire list is replaced, it may lean toward a value object. |
| Money amount | Value object | What matters is the monetary quantity and currency. |
| Postal code | Value object | The code value and validation rules are core. |
| Customer | Entity | Has its own lifecycle, identity, and history. |
| Shipping address captured at order placement time | Value object | Preserves the value at transaction time without referencing a changing address object. |

## 4. What Is Immutability?

An **immutable** object does not allow its own observable state to change after initialization. To represent a new state, we create a **new object**.

~~~java
Money current = new Money(100_000, "VND");
Money updated = current.add(new Money(20_000, "VND"));

// current is still 100_000 VND; updated is 120_000 VND.
~~~

For entities, two ideas should be distinguished:

- **The entity still changes in the business domain**: an order can move from `DRAFT` to `CONFIRMED`.
- **The Java object representing one state version can be immutable**: the `confirm()` method returns a new version of the same entity, carrying the same ID but the new status.

~~~text
PurchaseOrder(id=42, status=DRAFT)     --confirm()-->
PurchaseOrder(id=42, status=CONFIRMED)

Two different Java objects; in the domain they represent the same entity ID 42
in two different states.
~~~

### 4.1. Levels of State Protection

**Fully immutable object:**

~~~java
public final class ShippingAddress {
    private final String city;
    private final String street;

    public ShippingAddress(String city, String street) {
        this.city = Objects.requireNonNull(city);
        this.street = Objects.requireNonNull(street);
    }

    public String city() {
        return city;
    }

    public String street() {
        return street;
    }
}
~~~

This example uses `Objects`, which requires `import java.util.Objects;`. Because `String` is immutable, there are no setters, and the class cannot be subclassed, the created value cannot be modified through normal APIs. A `record` can be used to reduce boilerplate.

**Encapsulated mutability:**

~~~java
public class Basket {
    private final List<String> productCodes = new ArrayList<>();

    public void addProduct(String code) {
        // Rules can be checked before modifying.
        productCodes.add(Objects.requireNonNull(code));
    }

    public List<String> productCodes() {
        return List.copyOf(productCodes);
    }
}
~~~

`Basket` is not completely immutable, but callers cannot directly mutate the internal collection through the getter. Changes must go through domain methods.

There is no requirement that every entity must use `final`. What matters is **protecting invariants and restricting uncontrolled state modification**. A mutable entity with clear domain behavior can be a valid design.

### 4.2. `final` Does Not Guarantee Deep Immutability

~~~java
public record CustomerSnapshot(List<String> tags) {
}

List<String> source = new ArrayList<>(List.of("VIP"));
CustomerSnapshot snapshot = new CustomerSnapshot(source);
source.add("BLOCKED"); // snapshot.tags() also sees the new element
~~~

The record component is `final` at the reference level, but the referenced list is still mutable. Fix:

~~~java
public record CustomerSnapshot(List<String> tags) {
    public CustomerSnapshot {
        tags = List.copyOf(Objects.requireNonNull(tags));
    }
}
~~~

`List.copyOf` prevents structural modification of the list and copies elements into an unmodifiable list, but it is a **shallow copy**: if the elements themselves are mutable, the elements can still change state. The same applies to arrays, `Date`, or objects with mutable fields; defensive copying or immutable component value design is required.

## 5. Aggregates and Invariants: Who Has the Right to Change What?

An aggregate groups objects that must remain **consistent within the same business boundary**. All external changes go through the **aggregate root**. The root decides which operations are valid, when to create child entities, and when to reject changes.

~~~text
PurchaseOrder  (AGGREGATE ROOT)
    |
    +--- orderId / customerId / status
    |
    +--- total: Money                  (VALUE OBJECT)
    |
    +--- lines: OrderLine[]            (CHILD ENTITY / VALUE)
            |
            +--- productCode
            +--- quantity
            +--- unitPrice: Money      (VALUE OBJECT)

Customer                             (ANOTHER AGGREGATE ROOT)
    |
    +--- customerId
~~~

In this example, `PurchaseOrder` holds `customerId` to reference an independent customer aggregate. The order root does not "own" all changes to the customer.

Some invariants might be:

- A confirmed order must not have order lines added or removed.
- Each order line must have a positive quantity.
- All order lines share the same currency if the total amount is calculated in a single currency unit.
- The total amount must equal the sum of `quantity × unitPrice` of the active order lines.
- An order without order lines cannot be confirmed.

Instead of allowing independent calls to `setTotal(...)` and `setStatus(...)`, provide domain behaviors such as `addLine(...)`, `removeLine(...)`, `confirm()`. Each operation checks preconditions/postconditions and produces a valid state.

### Consistency Boundaries and Transactions

Aggregates are designed so that internal invariants can be maintained within a single transaction when saving. Rules spanning multiple aggregates may require separate coordination mechanisms, such as an application service transaction when the database permits, domain events, outbox, or eventual consistency depending on requirements. You should not merge two objects into one huge aggregate simply because they are related.

The larger an aggregate is, the more expensive loading and saving the entire graph usually becomes, and the higher the update contention. With Spring Data JDBC, this is an especially important consideration because a `save` operation on the root can result in multiple SQL statements for child entities.

## 6. Example Mapping a Value Object in Spring Data JDBC

The `Money` value object has two components: `minorUnits` and `currency`. If it is an attribute of the order, one option is to store it directly into columns of the `purchase_order` table:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_minor_units BIGINT NOT NULL,
    total_currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL
);
~~~

The syntax above uses an identity type compatible with many modern database systems, though DDL details may need adjustment for a specific database. In Spring Data JDBC, `@Embedded` can flatten an object's attributes across multiple columns:

~~~java
import org.springframework.data.relational.core.mapping.Embedded;

@Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "total_")
private final Money total;
~~~

Under the common snake_case column naming strategy, `Money.minorUnits` maps to `total_minor_units` and `Money.currency` maps to `total_currency`. `prefix` helps distinguish when an entity contains multiple value objects of the same type, such as `subTotal` and `shippingFee`.

`onEmpty = USE_NULL` means that when **all columns of the embedded object are null**, the framework can treat the entire object as null. If the domain requires `total` to always exist, in addition to constructor validation, `NOT NULL` constraints should be used in the database as shown in the example.

`@Embedded` is suitable for component objects stored in the same row. It is not a way to create a one-to-many relationship to a child entity table; that case requires the corresponding collection mapping mechanism.

## 7. Immutable Root Entity With `@Id`, `@Version`, and Domain Behavior

The code snippet below illustrates a simple aggregate root, without the order line collection yet so we can focus on entities, value objects, and immutable state:

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public final class PurchaseOrder {

    public enum Status {
        DRAFT, CONFIRMED
    }

    @Id
    private final Long id;

    @Version
    private final Long version;

    private final Long customerId;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "total_")
    private final Money total;

    private final Status status;

    @PersistenceCreator
    public PurchaseOrder(
            Long id,
            Long version,
            Long customerId,
            Money total,
            Status status
    ) {
        if (customerId == null || customerId <= 0) {
            throw new IllegalArgumentException("Invalid customer");
        }

        this.id = id;
        this.version = version;
        this.customerId = customerId;
        this.total = Objects.requireNonNull(total, "total");
        this.status = Objects.requireNonNull(status, "status");
    }

    public static PurchaseOrder draft(Long customerId, Money total) {
        return new PurchaseOrder(null, null, customerId, total, Status.DRAFT);
    }

    public PurchaseOrder confirm() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Only draft orders can be confirmed");
        }
        return new PurchaseOrder(id, version, customerId, total, Status.CONFIRMED);
    }

    public PurchaseOrder withId(Long generatedId) {
        return new PurchaseOrder(generatedId, version, customerId, total, status);
    }

    public PurchaseOrder withVersion(Long persistedVersion) {
        return new PurchaseOrder(id, persistedVersion, customerId, total, status);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }

    public Status getStatus() {
        return status;
    }
}
~~~

This example is **deliberately simplified**: the order only has a total amount supplied at creation time and does not yet compute it from order lines. In a model with `OrderLine`, the total amount should be calculated/validated by aggregate logic rather than trusting a total value sent by the caller.

### Explaining the Decisions

| Detail | Meaning |
| --- | --- |
| `@Table("purchase_order")` | Specifies the table name for the aggregate root in Spring Data Relational. |
| `@Id` | Marks the identifier key used for persistence. `null` indicates the object does not yet have a generated ID. |
| `@Version` | Marks the version for optimistic locking and determining the newness of the aggregate. |
| `@Embedded` | Maps `Money` into columns in the same row as the root entity. |
| `@PersistenceCreator` | Explicitly indicates the constructor used to materialize the object from read data. |
| `final` fields | No way to modify fields directly after initialization. |
| `draft(...)` | Factory creating an initial valid state. |
| `confirm()` | Domain method validating the state transition before creating a new object. |
| `withId(...)` / `withVersion(...)` | Creates a copy with populated/updated persistence attributes; supports materialization and saving immutable objects. |

Spring Data can choose an appropriate constructor according to framework rules; using `@PersistenceCreator` clarifies intent when a type has multiple ways to be instantiated. For constructor binding to work reliably, parameter names must be determinable by the framework, for example via the Java `-parameters` compiler option or appropriate metadata.

**A practical issue:** ID and version can be updated after a save operation. With immutable objects, the repository can **return a new object** with the new ID/version. Therefore, always use the value returned by `save(...)` when further operations are needed:

~~~java
PurchaseOrder draft = PurchaseOrder.draft(
        7L, new Money(125_000, "VND")
);

PurchaseOrder saved = repository.save(draft);

// saved holds the persisted state; use saved.getId() instead of
// assuming draft will be mutated to receive the new ID.
~~~

The specific version value is assigned by the framework according to Spring Data JDBC rules; do not predict the number yourself—use the returned instance instead.

## 8. Repository, Transactions, and Optimistic Locking

A repository for the aggregate root:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

An application service can orchestrate reading, invoking domain behavior, and then saving:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder current = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        PurchaseOrder confirmed = current.confirm();
        return repository.save(confirmed);
    }
}
~~~

Here, the service manages the transaction and selects the operation; `PurchaseOrder.confirm()` itself governs the state transition rule. A controller cannot call `setStatus(...)` because that method does not exist.

### What Happens If Two Requests Modify the Same Entity Simultaneously?

Immutability only prevents directly mutating the state of **a single Java object**. It does not by itself solve two processes reading the same database row and overwriting each other.

~~~text
Database: Order #42, version = 3, status = DRAFT

Request A reads version 3       Request B reads version 3
        |                               |
        v                               v
 A creates CONFIRMED copy        B creates CONFIRMED copy
        |                               |
        v                               v
 A saves with old version 3      B saves with old version 3
        |                               |
        v                               v
 A succeeds, increments version  B no longer matches version
                                        |
                                        v
                              Optimistic locking failure
~~~

`@Version` enables Spring Data JDBC to detect updates based on a stale version and report an optimistic locking failure instead of silently overwriting. However:

- The application must decide whether to return a conflict error or perform a controlled retry.
- A retry must re-read the latest state and re-check invariants; it should not unconditionally replay the stale update.
- For side effects outside the database (sending emails, calling payments), an appropriate coordination mechanism is needed to avoid duplicate actions during retries.
- Manual SQL updates or external tools can bypass the repository's version mechanism if they do not maintain the corresponding condition/version themselves.

Transactions ensure operations within their boundary can commit/rollback according to database capabilities; optimistic locking adds conflict detection. The two mechanisms serve different purposes and can be used together.

## 9. Child Entities in an Aggregate: Local Identity and Lifecycle

A real-world order aggregate typically contains order lines:

~~~text
PurchaseOrder (root)
  ├── OrderLine(lineId=1, productCode="BOOK-A", quantity=2)
  └── OrderLine(lineId=2, productCode="PEN-B",  quantity=4)
~~~

`OrderLine` can be a **child entity** if the business needs to distinguish individual lines by their own ID, such as when adjusting the quantity of a specific line. Even so, it does not necessarily have its own repository. Callers modify order lines **through methods of `PurchaseOrder`**, because the root must control the order's total amount and status.

~~~java
// Sketch of behavior within the aggregate (not a complete mapped class yet).
public PurchaseOrder changeLineQuantity(long lineId, int newQuantity) {
    requireDraft();
    if (newQuantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }

    List<OrderLine> changedLines = replaceQuantity(lines, lineId, newQuantity);
    Money updatedTotal = calculateTotal(changedLines);

    return copyWith(changedLines, updatedTotal);
}
~~~

The helpers `requireDraft`, `replaceQuantity`, `calculateTotal`, and `copyWith` in the snippet above represent domain logic to be implemented when designing the full aggregate. The goal is to illustrate the flow: **validate → create new collection → recalculate dependent values → create new root**, rather than allowing callers to mutate the collection and set the total amount arbitrarily.

### How Spring Data JDBC Views Relationships Within an Aggregate

Spring Data JDBC supports mapping relationships belonging to an aggregate via mechanisms such as `@MappedCollection`, for example:

~~~java
@MappedCollection(idColumn = "purchase_order_id", keyColumn = "line_position")
private final List<OrderLine> lines;
~~~

With a collection mapped like this, `idColumn` describes the foreign key column pointing to the root, while `keyColumn` can store the element index when mapping a `List`. The mapping also requires a compatible `OrderLine` class and matching child table schema; this is only an illustrative declaration.

Understand the differences:

| Business relationship | Design mindset | Mapping suggestion |
| --- | --- | --- |
| An order has many order lines belonging to its lifecycle | Same aggregate, root controls add/remove/modify | Child entity collection such as `@MappedCollection` |
| An order has a total amount | Value object belonging to root state | `@Embedded` into columns of the root |
| An order references an independently existing customer | Two separate aggregates | Hold `customerId` or a form of ID reference |

In Spring Data JDBC, an object referenced directly within an aggregate structure is generally interpreted by the framework as belonging to the same aggregate. If `PurchaseOrder` points directly to the `Customer` root entity as an owned graph, the system may misinterpret its lifecycle and persistence behavior. For independent aggregates, use an appropriate ID/reference instead of an owned object relationship.

### Cost of Saving an Aggregate With Collections

For many Spring Data JDBC mapping styles, when saving an existing aggregate, the framework may delete and re-insert referenced child entities even if some elements have not changed; the root is updated separately. Therefore:

- `save(root)` does not mean only a single `UPDATE` statement is issued.
- Immutability at the Java level does not mean only changed fields are written to the database.
- An overly large aggregate can cause more SQL, logging, locking, and version conflicts than necessary.
- If two groups of data have independent lifecycles and transactions, consider splitting the aggregate before trying to solve it with pool configuration.

You should observe the actual SQL produced by the Spring Data JDBC version and mapping style in use to evaluate the concrete cost.

## 10. Designing APIs That Protect Invariants

A common mistake is building a model with all public setters:

~~~java
// Example of a design that easily violates invariants.
order.setStatus(Status.CONFIRMED);
order.setTotal(new Money(0, "VND"));
order.getLines().clear();
~~~

If the business requires a confirmed order to have at least one order line and the total amount to match the lines, those three calls can create an invalid state with no component taking responsibility for enforcement.

A domain-behavior API makes responsibilities clear:

~~~java
PurchaseOrder updated = order
        .addLine("BOOK-A", 2, new Money(85_000, "VND"))
        .addLine("PEN-B", 1, new Money(15_000, "VND"))
        .confirm();
~~~

This example illustrates the target API; the simplified `PurchaseOrder` class in section 7 does not yet implement `addLine`. In a full design, `addLine` must:

1. Check that the order still allows modifications.
2. Validate the product code, quantity, and currency.
3. Create a new set of order lines or perform controlled mutation.
4. Recalculate the total amount from the lines, avoiding manual synchronization of two data sources.
5. Return the next valid aggregate state.

With immutable objects, each step returns a new copy. If using a tightly encapsulated mutable entity, the same logic can execute inside a method modifying a private collection. Both approaches can preserve invariants; the choice depends on complexity, aggregate size, and mapping needs.

### Invariants Across Different Layers

| Layer | Example rule | Why it is needed |
| --- | --- | --- |
| Value object constructor/factory | Non-negative `Money`, well-formed currency code | Prevents invalid domain values from existing at creation time. |
| Aggregate root method | Do not confirm an order lacking lines | Protects business state transition rules. |
| Application service | Check permissions, coordinate multiple roots | Decides who does what and in what context. |
| Database constraint | `NOT NULL`, `UNIQUE`, `CHECK`, appropriate foreign keys | Protects data from external access, concurrency bugs, or code bypassing the domain model. |
| Optimistic locking / transaction | Reject updates based on stale versions, commit/rollback | Maintains consistency under concurrent operations. |

Do not try to cram every condition into request validation annotations, because an entity can be created by a batch job, message handler, or internal code without going through HTTP validation. Core rules must be protected where all paths converge: value objects, aggregates, and the database when appropriate.

## 11. Differences to Remember When Using Spring Data JDBC

Entity/value object design applies broadly, but the persistence infrastructure affects how it is implemented.

### 11.1. Spring Data JDBC Is Not JPA

| Aspect | Spring Data JDBC | JPA/Hibernate (for comparison) |
| --- | --- | --- |
| Ownership model | Focused on aggregate root and owned components | Entity graphs and relationships can be managed with many mapping styles. |
| Persistence context tracking dirty fields | No such mechanism like JPA | Typically has dirty checking for managed entities. |
| Saving modified objects | Typically calls repository `save(...)` explicitly | Managed entities can be flushed automatically within a transaction. |
| Relationship between independent aggregates | Typically stores ID/ID-based reference | Can use entity associations like `@ManyToOne` in the JPA style. |
| JPA-style entity proxy lazy loading | Does not rely on that persistence context/lazy-loading model | Can have lazy associations depending on mapping. |

Do not take JPA examples using `@Entity`, `@OneToMany`, `@ManyToOne` and assume they apply verbatim to Spring Data JDBC. Spring Data JDBC uses Spring Data Relational annotations such as `@Table`, `@MappedCollection`, `@Embedded` together with Spring Data Commons annotations such as `@Id` and `@Version`.

### 11.2. Immutability and Materialization

The framework needs to construct entities from database data. With immutable classes, suitable approaches include:

- A constructor explicitly declaring the properties to restore; use `@PersistenceCreator` when disambiguation is needed.
- Records for simple value objects or entity cases where genuinely appropriate.
- For storage-updated properties (ID/version), provide a way to create copies via `withId(...)`/`withVersion(...)` or a copy creator style supported by the framework.
- Ensure property mapping and constructor parameter names are resolved properly; avoid ambiguous overloaded constructors.

A persistence constructor should not secretly make network calls or regenerate business identifiers: it must reconstruct the persisted state. If complex invariants are needed, design creation via factory methods separately from restoration from valid stored data, while keeping data constraints in the database.

### 11.3. Distinguishing Immutable Objects From Immutable Business Facts

For example, an issued invoice may be a **business document whose content cannot be modified** according to domain rules. That is immutability at the business level. Conversely, `PurchaseOrder` can be represented by an immutable Java class yet still transition states via new versions. A system may need both:

- **Immutable implementation:** prevents direct mutation so code is easier to reason about.
- **Immutable business fact:** prevents domain operations from altering finalized data even if the implementation allows copying.

Do not infer business immutability solely from the Java `final` keyword.

## 12. Considerations When Choosing Immutable Entities

### Benefits

- Easier to reason about because an object does not change when passed between functions.
- Prevents callers from accidentally mutating internal collections or fields.
- Creates clear state transition paths through domain methods.
- Useful when comparing before-and-after snapshots, logging events, or checking invariants.
- Eliminates many bugs caused by sharing mutable references within a processing flow.

### Trade-offs

- Requires creating copies upon modification; aggregates containing many elements may incur memory/copy overhead.
- Mapping database-generated IDs/versions requires valid constructors or withers.
- Excessive copying can make APIs verbose if the model is not well organized.
- Immutability does not eliminate transactions, race conditions, lost updates, or synchronization requirements across multiple instances.
- With Spring Data JDBC, data access performance still depends on SQL generated by the repository; immutable objects do not automatically turn saves into minimal updates.

You can choose **immutable value objects almost by default**, while entities can be fully immutable or tightly encapsulated mutable objects. Invariant correctness, code understandability, and actual persistence cost matter more than forcing a single style on every aggregate.

## 13. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Treating every DTO/table row as a domain entity | Model is dragged toward database structure, lacking domain behavior | Determine identity and lifecycle from domain rules. |
| Value object with setters | Other parts of the system can observe unexpected value changes | Use records/immutable classes, returning new values on operations. |
| Record containing a mutable `List` | Callers indirectly mutate state assumed to be immutable | Copy collections and consider deep immutability. |
| Comparing entities by all fields | The same entity after a state change is treated as two entities | Define an appropriate identity strategy. |
| Using DB-generated ID in `hashCode()` before and after save | Hash changes while the object is already in a hash collection | Use a stable equality strategy or avoid depending on mutable IDs. |
| Public setters for status, total, lines | Callers bypass invariants | Provide methods expressing business intent and checking state. |
| Exposing a mutable child list | Callers insert/delete children outside the root | Return unmodifiable views or copies; mutations go through the root. |
| A root directly owning another root | Aggregate bloats and gets lifecycles wrong | Reference independent aggregates via ID. |
| Assuming every `save` only writes changed fields | Overlooks cost of child updates/deletions/reinsertions | Observe SQL and reconsider aggregate size. |
| Assuming immutability alone solves concurrency | Lost updates still occur at the database | Use `@Version`, transactions, and conflict handling strategies. |

## 14. Self-Practice Scenarios

### Scenario A — Choosing Entity or Value Object?

A customer can save multiple addresses. The shipping address is captured on each order and must keep its exact content even if the customer edits the address in their profile.

**Design direction:** `Customer` is an aggregate root with its own identity. The address attached to the order fits well as an immutable snapshot value object. The order holds the address value at order placement time rather than referencing the profile to change automatically.

### Scenario B — Shopping Cart Invariant

The rule requires every line quantity to be greater than 0 and the total amount to always equal the sum of the lines. A controller calls `setQuantity(0)` and then `setTotal(100_000)`.

**Problem:** invariants can be broken because logic is scattered. **Design direction:** the controller calls `cart.changeQuantity(lineId, requestedQuantity)`, the aggregate root validates and recalculates the total itself; do not provide an independent setter for derived values.

### Scenario C — Two Staff Members Confirming the Same Order Simultaneously

Both read order version 5. The first saves successfully; the second proceeds to save the immutable object created from version 5.

**Handling direction:** the `@Version` field detects the stale save. The application re-reads the state, re-applies domain rules, and returns a conflict error or performs a conditional retry. Do not automatically retry all side effects outside the database.

### Scenario D — Overly Broad Aggregate

An order is persisted along with all payment history, customer account addresses, and shipping history tables; a small change forces saving a large graph.

**Design direction:** ask which components genuinely need to be consistent within the same transaction. Separate entities with independent lifecycles into distinct aggregates, store reference keys, and build coordination mechanisms if needed. This reduces write costs and avoids a root owning data outside its responsibility.

## 15. Key Takeaways

To design good aggregates in Spring Data JDBC:

1. **Choose an entity when identity is needed; choose a value object when content-based equality is needed.**
2. **Place invariants where the data is owned:** value objects validate their own values, and aggregate roots control member changes.
3. **Design APIs around domain behavior:** `confirm()`, `changeQuantity()`, or `replaceAddress()` express intent better than chains of setters.
4. **Protect immutability at the right level:** immutable value objects, defensive copies for collections, and clear entity modification strategies.
5. **Understand Spring Data JDBC characteristics:** the root is the unit of aggregate persistence, child mapping differs from JPA, and `save` can generate multiple SQL statements.
6. **Handle concurrency at the persistence layer:** IDs identify entities, `@Version` detects stale writes, and transactions/constraints help maintain consistency.

The goal of the model is not to make every Java class immutable at all costs. The goal is to ensure **every accepted state is valid**, **every change has business intent**, and **aggregate boundaries are small and clear enough for Spring Data JDBC to persist reliably**.
