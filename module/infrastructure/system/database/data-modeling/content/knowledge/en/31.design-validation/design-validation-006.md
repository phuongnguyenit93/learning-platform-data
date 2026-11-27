# Testing equals, hashCode, and Invariants of Java Models

## 1. From Data Model to Java Object Contract

The **DATABASE_DATA_MODELING** module trains the ability to turn business requirements into models with entities, relationships, keys, constraints, normalization, indexes, and physical schemas, comparing relational, document, graph, and analytical storage approaches. In the **Design Validation** chapter, DDL and SQL are not the only things requiring verification: Java objects must also accurately embody the model's **identity, equality, and invariants**.

Consider a multi-tenant retail system where an SKU is identified by a triple:

~~~text
tenantCode  = VN-01
catalogCode = MAIN
skuCode     = P0012
~~~

An HTTP request constructs an `Sku` object. A worker reading the database constructs another `Sku` with the exact same three values. These are **two instances** representing the same **business key**.

If the application uses a `HashSet` to deduplicate or a `HashMap` to look up stock, behavior depends on **`equals`/`hashCode`**. If an object mutates after being inserted as a `Map` key, lookups break. If an SCD2 `ProductVersion` is treated as `ProductIdentity`, two versions sharing the same product code can collapse into one and corrupt history.

This lesson validates three layers:

1. **Equality:** when are two objects considered the same value or the same entity?
2. **Hashing:** can equal objects be looked up consistently in hash-based structures?
3. **Immutability and invariants:** which state may change, which must remain fixed, and which conditions must always hold?

**Learning objectives:** design value objects and entity identities; implement `equals`/`hashCode` obeying the Java contract; catch bugs involving `HashSet`/`HashMap`, records, arrays, collections, `BigDecimal`, temporal values, inheritance, and JPA; and build JUnit 5, property-based, and integration tests aligned with database keys, `UNIQUE` constraints, and FKs.

## 2. Choosing Equality Rules by Grain and Identity

Not every pair of objects with matching field values is the same entity.

| Model kind | Example | Required equality rule |
|---|---|---|
| **Value object** | `Sku`, `Money`, `EmailAddress`, `ValidInterval` | Equal normalized constituent values |
| **Entity** | `Customer`, `SalesOrder`, `Product` | Equal stable identity, independent of mutable attributes |
| **Entity version** | `ProductVersion`, `PriceVersion` | Equal version ID, not just equal root entity code |
| **Event** | `OrderCreated` | Equal event ID, not just equal payload |
| **Request** | `CreateOrderRequest` | Equal request ID within tenant/client scope |
| **DTO/snapshot** | `OrderSummary` | May compare snapshot fields if contract specifies |
| **Analytical fact** | One sales line | Equal source line identity, not just equal monetary amount |
| **Aggregate** | `Order` with many lines | Equal aggregate ID; do not recursively compare entire relation graph |

For example, orders `O100` and `O101` may share the same customer, product, quantity, and amount. They remain **two distinct orders**. If `equals` compares content fields and returns `true`, a `HashSet` drops a legitimate order.

Conversely, two `Money` instances with the same amount and currency represent the same **value**, regardless of being separate heap instances.

### 2.1. Before Coding, Write a One-Sentence Invariant

~~~text
Two Sku instances are equal if and only if they share the same tenant,
same catalog, and same code per source rules.

Two SalesOrder instances are equal if and only if they share the same
stable order identity within the appropriate namespace.

Two ProductVersion instances are equal if and only if they share
the same version identifier, not merely the same productId.
~~~

An explicit invariant picks the right fields. Never compare `status`, `description`, `updatedAt`, or `cachedAmount` just because they appear on the class.

### 2.2. Different Grain Means Different Equality

~~~text
ProductIdentity:
  grain = one logical product
  key = (tenantId, sourceSystem, productCode)

ProductVersion:
  grain = one descriptive version with an effective interval
  key = productVersionId

SalesLine:
  grain = one recorded sales line
  key = (tenantId, salesSource, sourceLineId)
~~~

Two product versions share a `productCode` while having distinct `versionId`s. A `Map` keyed by `ProductIdentity` cannot hold both versions simultaneously since each key maps to only one entry.

## 3. The `Object.equals` Contract

In Java, `equals` on any non-null object must satisfy:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` return the same boolean.
3. **Transitive:** if `x` equals `y` and `y` equals `z`, then `x` equals `z`.
4. **Consistent:** if compared data does not change, repeated calls return the same result.
5. **Non-null:** `x.equals(null)` is `false`.

These rules are Java's `Object` contract, not optional style tips. `Map`, `Set`, and frameworks rely on them.

### 3.1. `==` Is Not `equals` for References

~~~java
Sku a = new Sku("VN-01", "MAIN", "P0012");
Sku b = new Sku("VN-01", "MAIN", "P0012");
Sku alias = a;

System.out.println(a == alias);  // true: same instance
System.out.println(a == b);      // false: different instances
System.out.println(a.equals(b)); // true: same Sku value
~~~

`==` on object references compares **instance identity**, not business keys. On primitives like `int`, `==` compares primitive values.

### 3.2. Approximate Comparison Does Not Belong in `equals`

A proximity comparison:

~~~java
boolean approximatelyEqual(double a, double b) {
    return Math.abs(a - b) < 0.1;
}
~~~

violates transitivity:

~~~text
a = 0.00, b = 0.09, c = 0.18

a ~ b: true
b ~ c: true
a ~ c: false
~~~

Never use a tolerance threshold as a value object's `equals`. For measurements requiring tolerance, add **`isApproximatelyEqual(other, tolerance)`** or quantize measurements into exact buckets per business rules before constructing keys.

## 4. The `hashCode` Contract: Equal Objects Must Have Equal Hashes

Core contract:

> If `x.equals(y)` is `true`, then `x.hashCode()` must equal `y.hashCode()`.

The converse **is not required**: distinct objects may share a hash code. `HashMap`/`HashSet` resolve bucket collisions by calling `equals`.

~~~text
equals(x, y) == true  => hash(x) == hash(y)
hash(x) == hash(y)    does NOT imply equals(x, y) == true
~~~

### 4.1. Hash Collisions Do Not Break the Contract

~~~java
@Override
public int hashCode() {
    return 1;
}
~~~

If `equals` is right, a constant hash does not violate equal-implies-same-hash, yet gives **terrible hash distribution** as size grows. Aim for consistent hashes with useful spread, not absolute uniqueness.

### 4.2. `hashCode` Is Not a Distributed Identifier

Never use `hashCode` as:

- A business key or `PRIMARY KEY`.
- A globally unique system ID.
- A cryptographic digest, signature, or password hash.
- A stable partition key across service versions without an explicit contract.
- A creation or commit ordering measure for entities.

It is strictly an in-memory bucket code for Java structures. If you need UUIDs, namespaced composite keys, or checksums, design dedicated types.

## 5. `Sku` Record: Basic Immutable Value Object

Java 17 example:

~~~java
import java.util.Objects;

public record Sku(
        String tenantCode,
        String catalogCode,
        String skuCode
) {
    public Sku {
        tenantCode = requireNonBlank("tenantCode", tenantCode);
        catalogCode = requireNonBlank("catalogCode", catalogCode);
        skuCode = requireNonBlank("skuCode", skuCode);
    }

    private static String requireNonBlank(String field, String value) {
        Objects.requireNonNull(value, field);
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }
}
~~~

A record auto-generates **`equals`, `hashCode`, and `toString`** from its components. All components here are immutable `String`s, and the compact constructor rejects `null` or blank whitespace strings. Without setters and with immutable strings, key content cannot change after construction.

~~~java
Sku a = new Sku("VN-01", "MAIN", "P0012");
Sku b = new Sku("VN-01", "MAIN", "P0012");
Sku c = new Sku("VN-02", "MAIN", "P0012");

System.out.println(a.equals(b));                  // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a.equals(c));                  // false
~~~

**Tenant must be part of equality** when SKUs are unique only within a tenant. If the real source treats codes as case-insensitive or requires canonicalization, adapt the constructor and tests per source rules rather than forcing one rule onto every system.

### 5.1. Records Are Not Meant for Every Entity

Records fit **value carriers** with clear components. An entity with an ID, state lifecycle, lazy relations, and ORM proxies often fits a regular class better. The goal is the right identity/equality contract, not forcing every class to be a record.

## 6. Final Class with Hand-Written `equals`/`hashCode`

You can build a clean value object without `record`:

~~~java
import java.util.Objects;

public final class SkuKey {
    private final String tenantCode;
    private final String catalogCode;
    private final String skuCode;

    public SkuKey(String tenantCode, String catalogCode, String skuCode) {
        this.tenantCode = Objects.requireNonNull(tenantCode);
        this.catalogCode = Objects.requireNonNull(catalogCode);
        this.skuCode = Objects.requireNonNull(skuCode);
    }

    public String tenantCode() { return tenantCode; }
    public String catalogCode() { return catalogCode; }
    public String skuCode() { return skuCode; }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof SkuKey other)) return false;
        return tenantCode.equals(other.tenantCode)
            && catalogCode.equals(other.catalogCode)
            && skuCode.equals(other.skuCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantCode, catalogCode, skuCode);
    }
}
~~~

Making the class `final` prevents subclasses from altering equality semantics. `final` fields holding immutable `String`s keep hashes stable throughout the object's lifetime.

### 6.1. What Must Be Reviewed

- Do `equals` and `hashCode` use **the exact same semantic fields**?
- Can any field be `null`? Is `Objects.equals` used consistently?
- Are any included fields mutable?
- Can subclasses or proxies change runtime type checks?
- Could two instances with the same ID yet different states wrongly compare unequal?
- Does an auto-generated `toString` expose sensitive fields?

Whenever `equals` fields change, re-check `hashCode`, tests, and every map/set usage.

## 7. `HashSet`/`HashMap`: Practical Verification

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

Sku first = new Sku("VN-01", "MAIN", "P0012");
Sku sameValue = new Sku("VN-01", "MAIN", "P0012");

Set<Sku> seen = new HashSet<>();
seen.add(first);
seen.add(sameValue);
System.out.println(seen.size()); // 1

Map<Sku, Integer> stock = new HashMap<>();
stock.put(first, 10);
System.out.println(stock.get(sameValue)); // 10
~~~

A test checking only `first.equals(sameValue)` misses **forgetting to override `hashCode`**. Always test:

- Bidirectional `equals`.
- Matching `hashCode` on equal objects.
- `Set` does not store two entries for equivalent keys.
- `Map` retrieves values using a distinct instance carrying the same value.

**`HashSet` does not preserve insertion order.** If order-line ordering matters, model `lineNo`/`position` explicitly and pick the right collection rather than inferring order from hashes.

## 8. Mutable Keys: Lookup Loss After Mutation

~~~java
import java.util.Objects;

public final class MutableSkuKey {
    private String code;

    public MutableSkuKey(String code) {
        this.code = code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableSkuKey that
            && Objects.equals(code, that.code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
~~~

~~~java
Map<MutableSkuKey, String> map = new HashMap<>();
MutableSkuKey key = new MutableSkuKey("P0012");

map.put(key, "Nutrition Bar");
key.setCode("P0099");

String value = map.get(key); // Likely not found.
~~~

The entry was placed in a bucket computed from the old hash. Once `code` changes and shifts the hash, lookup checks the wrong bucket. Even if a rare collision happened to land in the same bucket, mutating a hash **while the key sits in a map** already breaks the map's operational contract.

### 8.1. Correct Policy

- Use **immutable value objects** as keys.
- When a business code changes, construct a new key and remove/reinsert the entry.
- For entities with mutable `status`, `name`, or `address`, exclude those fields from identity-based equality.
- When the business allows product codes to change, use a **durable entity identity** plus **alias/history** instead of mutating active referenced keys.

## 9. Immutability Differs from Domain Invariants

An object can be immutable yet **business-invalid** — e.g., an `OrderId` wrapping a `null` UUID or a `ValidInterval` whose start is after its end.

| Guarantee kind | Example | Verification |
|---|---|---|
| Unchanging reference | `final` field | Reference cannot be reassigned |
| Unchanging contents | `List`, `Map`, `byte[]` | Defensive copies and immutable elements |
| Valid value domain | `quantity > 0` | Constructor/method guards |
| Stable identity | `orderId` | Never changes when status changes |
| Valid state | `CONFIRMED` requires ≥1 line | Workflow invariant |
| Valid relationships | `orderLine` matches order/tenant | FK / aggregate validation |
| Valid time bounds | `validFrom < validTo` | Value object / DB constraint |
| Non-overlapping versions | Two versions of same identity never intersect | Transaction / `EXCLUDE` |
| No money leak | Total refunds never exceed captured payments | Multi-row transaction |

**`final` does not mean deeply immutable.** A `final` field referencing an `ArrayList` still observes mutations to that list. Meanwhile, an entity can have mutable state while preserving **immutable identity** and every domain invariant across state transitions.

## 10. Records Are Shallowly Immutable and Do Not Copy Collections

Dangerous example:

~~~java
import java.util.List;

public record OrderSnapshot(List<String> skuCodes) {
}
~~~

~~~java
List<String> input = new java.util.ArrayList<>();
input.add("P0012");
OrderSnapshot snapshot = new OrderSnapshot(input);
input.add("P0099");

// snapshot.skuCodes() contents can be mutated externally.
~~~

The record holds a `final` reference to the list, yet **the list itself remains mutable**. Since `List.equals`/`hashCode` depend on elements, the record's `hashCode` mutates over time too.

### 10.1. Copy on Construction

~~~java
import java.util.List;
import java.util.Objects;

public record OrderSnapshot(List<String> skuCodes) {
    public OrderSnapshot {
        Objects.requireNonNull(skuCodes, "skuCodes");
        skuCodes = List.copyOf(skuCodes);
    }
}
~~~

When `input` is a mutable `List`, `List.copyOf` produces an unmodifiable snapshot. Because the elements are **immutable `String`s**, this suffices to make the component immutable.

~~~java
List<String> input = new java.util.ArrayList<>();
input.add("P0012");
OrderSnapshot snapshot = new OrderSnapshot(input);

input.add("P0099"); // Does not alter snapshot.
snapshot.skuCodes().add("X"); // UnsupportedOperationException
~~~

**`List.copyOf` does not deep-copy elements.** If the `List` holds `MutableAddress`, those elements can still be mutated. Use immutable elements or deep-copy per business needs. Also note `List.copyOf` rejects `null` elements; confirm that policy explicitly.

## 11. Arrays: Records Do Not Compare `byte[]` Contents by Default

Consider:

~~~java
public record BinaryTag(byte[] bytes) {
}
~~~

First problem: arrays are mutable; callers can mutate the input array after construction or mutate the array returned by the accessor. Second problem: two `byte[]` arrays with identical bytes are **distinct array objects**, and default array equality uses `Object.equals` (reference equality).

If `BinaryTag` is a value object by **byte contents**, implement both defensive copying and content-based equality:

~~~java
import java.util.Arrays;
import java.util.Objects;

public record BinaryTag(byte[] bytes) {
    public BinaryTag {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BinaryTag that
            && Arrays.equals(bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
~~~

- Cloning in the constructor blocks caller mutation through the source array.
- Cloning in the accessor blocks mutation through the returned array.
- `Arrays.equals` compares byte-by-byte; `Arrays.hashCode` hashes byte contents.
- Add length/format constraints if the business key requires a fixed byte size.

Calling **`Objects.equals(bytesA, bytesB)`** does not compare array contents — it still delegates to the array object's reference `equals`.

## 12. Code Normalization and Equality Must Follow the Source Contract

Two strings:

~~~text
"P0012"
"p0012"
~~~

may represent the same or different SKUs depending on source rules. Never blindly call `equalsIgnoreCase` or lowercase everything if codes are genuinely case-sensitive.

If a business namespace **mandates case-insensitivity**, normalize inside the constructor:

~~~java
import java.util.Locale;
import java.util.Objects;

public record CaseInsensitiveCode(String value) {
    public CaseInsensitiveCode {
        Objects.requireNonNull(value, "value");
        value = value.trim().toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("code cannot be blank");
        }
    }
}
~~~

The record's `equals`/`hashCode` then operate on a **canonicalized value**. Remember this is only an example for domains adopting that policy.

### 12.1. Questions to Lock Down Before Normalizing

- Is it case-sensitive or case-insensitive?
- Is leading/trailing whitespace significant?
- Are leading zeros in `"0012"` significant?
- Is Unicode normalization needed?
- Do all sources share one coding standard or distinct namespaces?
- Does database collation / unique indexing match Java's comparison?
- When importing legacy data, will normalization introduce collisions?

In particular, parsing `"0012"` to integer `12` and formatting back to string is wrong whenever leading zeros are part of the identifier.

### 12.2. Java `String` Equality Does Not Automatically Match SQL Collation

`String.equals` compares Java UTF-16 code units, whereas SQL `UNIQUE` semantics depend on column types, collations, and settings. If the app treats `"AbC"` and `"abc"` as equal while the DB `UNIQUE` treats them as distinct, two write paths can store two rows Java views as the same key. Conversely, the DB might reject two codes Java views as distinct.

Define one clear canonicalization contract and test **Java → database → Java round-trips** covering Unicode, letter case, and whitespace edge cases.

## 13. `BigDecimal`, Scale, and Money

`BigDecimal.equals` compares both numeric value and scale:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));            // false
System.out.println(a.compareTo(b) == 0);    // true
~~~

Numerically, both represent `10`. Yet `BigDecimal.equals` treats them as unequal due to differing scale. **`compareTo` is inconsistent with `equals`** here, causing `HashSet` and `TreeSet` (which uses natural ordering) to yield different sizes.

### 13.1. Designing `Money` Around Domain Policy

If the domain defines two monetary values with equal numeric amount and currency as equal:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        amount = amount.stripTrailingZeros();
    }
}
~~~

With `Money`:

- `10.0 VND` and `10.00 VND` canonicalize to the same value.
- `10 USD` and `10 VND` **are not equal** because currencies differ.
- `stripTrailingZeros` may yield negative scale or scientific notation when formatted; display formatting is a separate concern.
- If the business enforces a **fixed scale per currency**, lock down precision, rounding, and minor units before constructing `Money`.
- For **scientific/engineering measurements** where trailing precision carries meaning, do not strip scale arbitrarily.

Never use `double` for money when exact decimal math and explicit rounding rules are required.

### 13.2. `double` and Tolerance Ranges

`double` brings `NaN`, `Infinity`, `+0.0`/`-0.0`, and binary representation error. If a value object wraps `double` and serves as a key, specify those edge cases explicitly.

Never implement `equals` as "within epsilon" because it breaks transitivity. When measurements must be grouped within a threshold, use a dedicated similarity helper or quantize into **exact buckets** before building keys.

## 14. Time and the Meaning of Equality

Two representations can denote the same **absolute instant**:

~~~java
import java.time.OffsetDateTime;

OffsetDateTime local = OffsetDateTime.parse(
    "2026-07-01T07:00:00+07:00"
);
OffsetDateTime utc = OffsetDateTime.parse(
    "2026-07-01T00:00:00Z"
);

System.out.println(local.equals(utc)); // false
System.out.println(
    local.toInstant().equals(utc.toInstant())
); // true
~~~

If the domain key represents an **absolute instant**, normalizing to `Instant` makes sense. If it represents a **store calendar date**, business time zone and local date matter; `LocalDate` or `ZonedDateTime` carry different semantics.

### 14.1. Half-Open Interval Invariant

An interval using `[start, endExclusive)` avoids boundary overlaps:

~~~java
import java.time.Instant;
import java.util.Objects;

public record ValidInterval(Instant start, Instant endExclusive) {
    public ValidInterval {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(endExclusive, "endExclusive");

        if (!start.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                "start must precede endExclusive"
            );
        }
    }

    public boolean contains(Instant instant) {
        Objects.requireNonNull(instant);
        return !instant.isBefore(start)
            && instant.isBefore(endExclusive);
    }
}
~~~

Interval `[01/07, 01/08)` includes the start of July 1 and excludes the start of August 1. The constructor enforces **one valid interval**, yet cannot prevent two versions of the same product from overlapping; cross-row invariants belong to the aggregate or database.

### 14.2. Distinct Timestamps Must Not Be Conflated

- `eventTime`: when the business event occurred.
- `receivedAt`: when the server received it.
- `validFrom`/`validTo`: business validity interval.
- `knownFrom`/`knownTo`: interval during which the system accepted the fact.
- `createdAt`: technical record creation timestamp.

Never extract business event time from timestamped IDs (UUIDv7/Snowflake), and never substitute `receivedAt` for valid time when retroactive corrections exist.

## 15. Inheritance Can Break Symmetry

Suppose a superclass considers any `BaseProduct` with the same code equal:

~~~java
public class BaseProduct {
    protected final String code;

    public BaseProduct(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BaseProduct that
            && code.equals(that.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

A subclass `ColoredProduct` adds `color` and overrides `equals` to compare only against `ColoredProduct` matching both `code` and `color`. Now:

~~~text
base.equals(colored)  = true
colored.equals(base)  = false
~~~

This violates **symmetry**. Whenever a subclass adds a field to equality that the superclass knows nothing about, rethink the design.

Options:

- For value objects, prefer **`record` or `final` classes** to lock equality semantics.
- Use **composition** rather than inheritance just to add components.
- For mandatory hierarchies, define a shared equality contract across types and test symmetry/transitivity across all subtypes.
- `getClass()` guards type mismatches yet trades off poorly with dynamic ORM proxies/subclasses.

No single `equals` snippet works for every entity hierarchy.

## 16. Entities Compare by Identity, Not Full State

An `Order` moves through:

~~~text
orderId = O100
DRAFT -> CONFIRMED -> SHIPPED

totalAmount may adjust per policy.
~~~

It remains **the same order**. If `equals` depended on `orderStatus`, `lines`, or `totalAmount`, every state change would alter equality and hash codes.

For entities, the appropriate rule is **stable identity**:

> Two `SalesOrder` instances are equal if they represent the same identified order within the proper namespace.

ID value object:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "orderId");
    }
}
~~~

An entity's state can mutate while its `orderId` stays immutable. When you need to compare **content snapshots**, write an explicit `compareContent` method or a dedicated immutable DTO — never turn `entity.equals` into a full-state deep comparison.

### 16.1. Never Include Bidirectional Relationships in `equals`/`hashCode`

If `Order.equals` traverses every `OrderLine` and `OrderLine.equals` traverses back to `Order`, you risk infinite recursion or triggering unintended lazy graph loads. Deep graph equality is also expensive and unstable over time.

For ORM entities, declare identity fields explicitly rather than comparing all association fields.

## 17. JPA/Hibernate: Post-Persist Assigned IDs Carry Specific Risks

An ORM entity using `@GeneratedValue` moves through lifecycle states:

~~~text
Transient: id = null
Persisted: id = 123
Detached:  id = 123
Reloaded:  another instance, id = 123
~~~

Mistake one: treating two transient entities with `id = null` as equal. Mistake two: computing `hashCode` from `id` when `id` shifts from `null → 123` while the entity sits in a `HashSet`.

### 17.1. Three Design Strategies to Evaluate

**A. Do not override `equals`/`hashCode`:** entities use reference equality. Simple within a single instance lifecycle, yet two instances across different persistence contexts representing the same DB row are not equal.

**B. Pre-persist assigned IDs:** assign a UUID or durable ID at object construction. With a stable contract, ID-based equality stays constant across persistence.

**C. Persisted-ID equality with special rules:** two entities with **non-null equal IDs** are equal; transient entities equal only themselves by reference. Hashing must either avoid changing when an ID arrives (e.g., constant entity-type hash, trading off hash distribution) or forbid using transient entities as hash keys before persist — and ORM proxies must still be handled carefully.

Never copy a JPA `equals` snippet without testing it against your actual framework, proxies, and entity lifecycle.

### 17.2. Testing with a Real ORM

- Two transient entities remain unequal despite both having `id = null`.
- Persisting an entity does not break a `HashSet` holding it.
- Detached and reloaded entities obey the chosen equality policy.
- Proxies and concrete instances preserve symmetry and transitivity.
- Updating status/name does not alter identity.
- Calling `equals`/`hashCode` never triggers lazy collection loading.
- No infinite recursion across bidirectional associations.

## 18. Distinguishing Product Identity from SCD2 Version Identity

In a temporal model:

~~~text
Product logical identity:
  productId = P01

Product versions:
  versionKey = 1001, category = FOOD, valid [01/01, 01/08)
  versionKey = 1002, category = GIFT, valid [01/08, +∞)
~~~

Both versions share `productId`, yet represent **distinct version rows**, requiring two distinct key types:

~~~java
public record ProductId(
    String tenantCode,
    String sourceSystem,
    String productCode
) {
}

public record ProductVersionId(long value) {
}
~~~

A `Map` by `ProductId` looks up the logical product; a `Map` by `ProductVersionId` looks up the exact version referenced by a fact. Putting both versions into a `Map` keyed by `ProductId` causes the newer version to overwrite the older one.

### 18.1. `validFrom` Is Rarely a Durable Version Key

If `(productId, validFrom)` is used as the version key, a retroactive correction editing `validFrom` mutates the key. When auditability and revision tracking matter, prefer an immutable surrogate version ID paired with separate valid-time and known-time fields.

Java `equals` cannot prevent **two validity intervals for the same product from overlapping**. That is a cross-row/version constraint requiring transactional validation or `EXCLUDE`.

## 19. Java Equality Must Align with Database `UNIQUE` Constraints

Suppose an SKU business key is **`(tenant_code, catalog_code, sku_code)`**:

~~~sql
CREATE TABLE catalog_sku (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,

    CONSTRAINT uq_catalog_sku_business
        UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

Section 5's `Sku` value object has the exact same three components. Still, **never assume `Java.equals` and SQL `UNIQUE` always agree**.

| Difference | Java | Database |
|---|---|---|
| Letter case | `String.equals` is case-sensitive | Collation/type/index may differ |
| Whitespace | Compares exact contents | `CHAR`/collation/normalization may differ |
| Unicode | Compares UTF-16 code units | Collation/normalization may differ |
| Null | `Objects.equals(null, null)` is `true` | `UNIQUE` on nullable columns has distinct semantics |
| Decimal | `BigDecimal.equals` checks scale | `NUMERIC` normally compares numerically |
| Timestamp | `OffsetDateTime` distinguishes offset | `timestamptz` compares instant |
| Multi-tenant | Easy to omit tenant in `equals` | Composite `UNIQUE` can include tenant |
| Soft delete | Entity still carries ID | Partial unique index may cover active rows only |

### 19.1. A Java `Set` Does Not Replace a Real `UNIQUE` Constraint

Two workers can concurrently check "SKU `P0012` does not exist yet" and both `INSERT`. An in-process `HashSet` in one worker knows nothing about the other process.

The authoritative database needs properly scoped `UNIQUE` constraints, conflict-handling transactions, and supporting checks. Service-level checks provide fast feedback, never authoritative race protection.

### 19.2. Round-Trip Test Pattern

For each sample business key:

1. Construct the immutable Java key.
2. Serialize/persist per schema.
3. Read back and reconstruct the value object.
4. Verify `equals`/`hashCode` per contract.
5. Attempt a duplicate insert under the same tenant/collation.
6. Attempt the same code in another tenant if policy allows.
7. Test letter case, Unicode forms, whitespace, and leading zeros.

If Java considers two keys equal while the DB accepts two rows — or vice versa — fix **the canonicalization contract or DB constraint**, not just the test assertion.

## 20. Domain Invariants Can Span Beyond One Object

`equals`/`hashCode` cover only part of model validation. These rules cannot be enforced by a single object's equality alone:

- A `CONFIRMED` `Order` must have at least one `OrderLine`.
- `SUM(successfulRefund)` never exceeds allowed `capturedAmount`.
- Two product versions never overlap `valid_period`.
- A sales line never links to a product version from the wrong date.
- An SKU has at most one primary category on any given date.
- An event is processed at most once per `requestId` across multiple workers.

### 20.1. A State-Conditional Invariant

~~~java
import java.util.List;
import java.util.Objects;

public final class OrderDraft {
    private final OrderId orderId;
    private final List<OrderItem> items;

    public OrderDraft(OrderId orderId, List<OrderItem> items) {
        this.orderId = Objects.requireNonNull(orderId);
        this.items = List.copyOf(items);
    }

    public void validateBeforeConfirm() {
        if (items.isEmpty()) {
            throw new IllegalStateException(
                "confirmed order must contain at least one line"
            );
        }
    }
}
~~~

In a real system, **`OrderItem`** must also be immutable or deep-copied; this snippet focuses on the minimum-line rule. Even when `validateBeforeConfirm` passes, the confirmation transaction must re-verify persisted state **under authoritative concurrency control**.

### 20.2. Assigning Responsibility Across Layers

| Layer | Protects |
|---|---|
| Value-object constructor | Value domains, format, component immutability |
| Aggregate/domain method | State transitions and intra-aggregate rules |
| Database constraint | PK/FK/UNIQUE/CHECK/EXCLUDE |
| Transaction/locking/versioning | Cross-row invariants and concurrent writes |
| ETL/CDC/reconciliation | Multi-source data, late arrivals, corrections |
| API authorization | Permissions and tenant/actor boundaries |

A sound design never dumps all responsibility onto `equals`.

## 21. JUnit 5 Tests for the Equality Contract

A test verifying only `a.equals(b)` misses `hashCode`, symmetry, or `Set` lookup failures. A thorough test class exercises collection behavior too. The example below uses **Java 17 and JUnit Jupiter**, assuming Section 5's `Sku` record is in scope.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SkuTest {

    @Test
    void equalKeysFollowObjectContract() {
        Sku a = new Sku("VN-01", "MAIN", "P0012");
        Sku b = new Sku("VN-01", "MAIN", "P0012");
        Sku c = new Sku("VN-01", "MAIN", "P0012");

        assertNotSame(a, b);
        assertEquals(a, a); // reflexive

        assertEquals(a, b);
        assertEquals(b, a); // symmetric

        assertEquals(b, c);
        assertEquals(a, c); // transitive

        assertEquals(a.hashCode(), b.hashCode());
        assertFalse(a.equals(null));
    }

    @Test
    void allBusinessKeyPartsAffectEquality() {
        Sku base = new Sku("VN-01", "MAIN", "P0012");

        assertNotEquals(base, new Sku("VN-02", "MAIN", "P0012"));
        assertNotEquals(base, new Sku("VN-01", "ALT", "P0012"));
        assertNotEquals(base, new Sku("VN-01", "MAIN", "P0013"));
    }

    @Test
    void hashSetAndHashMapRecognizeEquivalentInstances() {
        Sku a = new Sku("VN-01", "MAIN", "P0012");
        Sku b = new Sku("VN-01", "MAIN", "P0012");

        Set<Sku> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);

        assertEquals(1, keys.size());
        assertTrue(keys.contains(b));

        Map<Sku, Integer> stock = new HashMap<>();
        stock.put(a, 10);
        assertEquals(Integer.valueOf(10), stock.get(b));
    }

    @Test
    void rejectsNullAndBlankComponents() {
        assertThrows(NullPointerException.class,
            () -> new Sku(null, "MAIN", "P0012"));

        assertThrows(IllegalArgumentException.class,
            () -> new Sku("VN-01", "MAIN", " "));
    }
}
~~~

### 21.1. Testing Hash Consistency

~~~java
@Test
void immutableSkuHasStableHash() {
    Sku sku = new Sku("VN-01", "MAIN", "P0012");
    int before = sku.hashCode();

    for (int i = 0; i < 100; i++) {
        assertEquals(before, sku.hashCode());
    }
}
~~~

Looping on `hashCode()` **does not prove deep immutability** if an object wraps a collection that the test never mutated externally. Write dedicated aliasing tests.

### 21.2. Never Assert "Two Unequal Keys Must Have Different Hashes"

Hash collisions **are legal**. Therefore:

~~~text
assertNotEquals(a, b)
does NOT imply
assertNotEquals(a.hashCode(), b.hashCode())
~~~

A test demanding unique hashes for every distinct key pair violates the contract. Measure **hash distribution** across representative datasets as a performance/quality check instead of treating an isolated collision as a bug.

## 22. Testing Defensive Copies and Record Immutability

For Section 10's `OrderSnapshot`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderSnapshotTest {

    @Test
    void isNotAffectedByMutableInput() {
        List<String> input = new ArrayList<>();
        input.add("P0012");

        OrderSnapshot snapshot = new OrderSnapshot(input);
        input.add("P0099");

        assertEquals(List.of("P0012"), snapshot.skuCodes());
    }

    @Test
    void accessorDoesNotExposeMutableInternalState() {
        OrderSnapshot snapshot = new OrderSnapshot(List.of("P0012"));

        assertThrows(UnsupportedOperationException.class,
            () -> snapshot.skuCodes().add("P0099"));
    }

    @Test
    void equivalentContentHasEqualHash() {
        OrderSnapshot a = new OrderSnapshot(List.of("A", "B"));
        OrderSnapshot b = new OrderSnapshot(
            new ArrayList<>(List.of("A", "B"))
        );

        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
    }
}
~~~

### 22.1. Testing `byte[]` Wrappers

~~~java
@Test
void binaryTagUsesDefensiveCopiesAndContentEquality() {
    byte[] source = {1, 2, 3};
    BinaryTag first = new BinaryTag(source);
    BinaryTag second = new BinaryTag(new byte[] {1, 2, 3});

    source[0] = 9;
    byte[] exposed = first.bytes();
    exposed[1] = 8;

    assertArrayEquals(new byte[] {1, 2, 3}, first.bytes());
    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

Place this test inside a JUnit 5 test class importing `Assertions`, `Test`, and Section 11's `BinaryTag`. It verifies both alias leak paths, not just `Arrays.equals`.

### 22.2. Testing Temporal Boundaries

~~~java
@Test
void validIntervalIsHalfOpenAndRejectsInvalidBounds() {
    var start = java.time.Instant.parse("2026-07-01T00:00:00Z");
    var end = java.time.Instant.parse("2026-08-01T00:00:00Z");

    assertThrows(IllegalArgumentException.class,
        () -> new ValidInterval(start, start));
    assertThrows(IllegalArgumentException.class,
        () -> new ValidInterval(end, start));

    ValidInterval interval = new ValidInterval(start, end);
    assertTrue(interval.contains(start));
    assertFalse(interval.contains(end));
}
~~~

Never replace the right bound with `23:59:59.999` hoping it covers every precision. Keep `[from, to)` consistent across Java and SQL.

## 23. Property-Based Testing: Verifying Contracts Across Many Inputs

Hand-crafted unit tests miss subtle Unicode forms, boundary characters, decimal scales, time zones, or namespaces. **Property-based testing** generates broad inputs and verifies type invariants across all of them.

Use libraries like **jqwik** or **QuickTheories** if adopted by your project. To illustrate the idea in plain Java, use a deterministic seeded loop:

~~~java
import java.util.Random;

Random random = new Random(20261122L);

for (int i = 0; i < 10_000; i++) {
    String tenant = "T-" + random.nextInt(20);
    String skuCode = "P-" + random.nextInt(10_000);

    Sku a = new Sku(tenant, "MAIN", skuCode);
    Sku b = new Sku(tenant, "MAIN", skuCode);
    Sku c = new Sku(tenant, "MAIN", skuCode);

    if (!(a.equals(b) && b.equals(a)
            && b.equals(c) && a.equals(c))) {
        throw new AssertionError("equality contract broken");
    }
    if (a.hashCode() != b.hashCode()) {
        throw new AssertionError("hash contract broken");
    }
}
~~~

This snippet is an **illustrative algorithm** meant for a test method, not a standalone Java file. Inside JUnit, prefer **`Assertions`** over Java's `assert` keyword, which is disabled unless `-ea` is passed to the JVM.

### 23.1. Properties Worth Generating and Asserting

1. Equal normalized values → `equals` true and matching `hashCode`.
2. Distinct business key components → `equals` false per policy.
3. Reflexive, symmetric, transitive, and non-null.
4. `Set`/`Map` recognize equivalent instances.
5. Creating from a mutable collection and mutating the input leaves the object unchanged.
6. Mutating accessor outputs (or attempting to) leaves the object unchanged.
7. Serializing/deserializing value objects preserves meaning.
8. Database round-trips preserve business keys.
9. Two entity instances with differing status yet identical identity remain equal per policy.
10. Two `ProductVersion`s with differing version IDs never collapse.

### 23.2. Generating Boundary Inputs

- `null`, empty strings, and whitespace.
- Unicode strings with alternate normalization forms.
- Codes with leading zeros and mixed letter case.
- `BigDecimal` `0.0`, `0.00`, negatives, and high precision.
- `double` `+0.0`/`-0.0`, `NaN`, `Infinity` where permitted.
- Timestamps representing the same `Instant` in different offsets.
- Collections that are empty, single-element, multi-element, or contain duplicates.
- `byte[]` that are empty, zero-filled, or large.
- Same `ProductId` across distinct versions.
- Transient, persisted, detached, and proxied entities.

Never copy real customer data to make test fixtures look "realistic."

## 24. Testing Entities Across ORM Lifecycle Stages

With JPA/Hibernate, test against a **real persistence context**, not just `new Entity(...)`.

| Stage | Scenario | Invariant to hold |
|---|---|---|
| Transient | Two newly created entities with `id = null` | Not equal merely because both are `null` |
| Persisted | ID assigned on `INSERT` | Hashing/equality does not lose items in collections |
| Managed | Entity inside persistence context | Identity policy holds |
| Detached | Entity leaves session | Identity preserved |
| Reloaded | Separate instance reading same DB row | Equality matches design policy |
| Proxied | ORM generates subtype/proxy | Symmetry/transitivity preserved |
| Updated | Status/name changes | Identity remains stable |
| Archived | Soft-deleted or deactivated | ID never reused contrary to policy |

If using reference equality, test explicitly which APIs must not assume equality across detached/reloaded objects. If using ID equality, test **ID lifecycle, proxy handling, and hash stability**.

### 24.1. Beware of Code Generators

Annotations or IDE generators building `equals`/`hashCode` over **all fields** of an entity can cause:

- Infinite recursion across bidirectional associations.
- Accidental triggering of lazy loading.
- Hash mutations when status or collections change.
- Two orders with different IDs yet identical contents collapsing into one.
- PII leaking into logs via auto-generated `toString`.

Inspect generated code and declare identity fields explicitly.

## 25. Java and PostgreSQL Integration Testing

Value-object tests verify Java only; database uniqueness and concurrency invariants require dedicated integration tests.

Suppose the SKU key schema is:

~~~sql
CREATE TABLE catalog_sku (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,
    CONSTRAINT uq_catalog_sku_business
        UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

### 25.1. Cross-Layer Comparison Matrix

| Scenario | Java | PostgreSQL |
|---|---|---|
| Same tenant/catalog/code | `equals` true | `UNIQUE` rejects second row |
| Different tenant, same code | `equals` false | Accepted if key is tenant-scoped |
| Different catalog, same tenant/code | `equals` false | Accepted if catalog is in key |
| Different case, case-sensitive source | `equals` false | Collation/index must align |
| Leading zeros | Preserved | Text column must not strip |
| `BigDecimal` differing scale | Per `Money` policy | Matching `NUMERIC`/rounding |
| Two product versions, same BK | Distinct by `versionId` | SCD2 permits if non-overlapping |
| Two overlapping valid intervals | Each object individually valid | `EXCLUDE`/transaction rejects pair |
| Two workers writing same SKU | Local `HashSet` insufficient | `UNIQUE` + conflict handling |

### 25.2. Test Concurrency Rather Than `SELECT` Before `INSERT`

Two workers can simultaneously run:

~~~text
A: SELECT finds no SKU P0012
B: SELECT finds no SKU P0012
A: INSERT SKU P0012
B: INSERT SKU P0012
~~~

Relying on in-memory `Set`s or pre-insert `SELECT`s lets both writers race. Authoritative DB `UNIQUE` constraints must guard the race, and the app must handle constraint violations or `ON CONFLICT` properly.

### 25.3. Integration Test Template

1. Initialize test database using real migrations.
2. Insert SKU under business key A.
3. Attempt duplicate insert A; assert rejection by the right constraint.
4. Insert same code under tenant B; assert acceptance if policy allows.
5. Read SKU back into Java; assert `equals`/`hashCode` against request-built key.
6. Test collation, case, and Unicode per source contract.
7. Run two concurrent transactions inserting the same key.
8. Use `ProductVersion` data to test overlaps and gaps.
9. Verify failed transactions leave zero partial state.

Tests against a real database carry far more weight than mocking with `HashMap` when proving durable data invariants.

## 26. Distributed Data, Document, Graph, and Analytical Modeling

### 26.1. Identity Across Multiple Tenants and Regions

Two regions can independently generate local order number `1001`. In Java, keys must preserve namespace:

~~~java
import java.util.UUID;

public record TenantOrderKey(UUID tenantId, UUID orderId) {
    public TenantOrderKey {
        if (tenantId == null || orderId == null) {
            throw new IllegalArgumentException("Both ID parts required");
        }
    }
}
~~~

Still, right `equals` **does not guarantee** UUIDs are collision-free across independent DBs or stop retries from allocating two order IDs. You need scoped ID allocation, source identity, and idempotency keys.

### 26.2. Document Models

An `Order` document embeds an array of items. The domain entity uses `documentId`/`aggregateId` for identity; a snapshot DTO may compare **contents** after defensive copying. Using deep document equality as entity identity causes editing one item to turn the old order into "a different order" inside a `Set`.

### 26.3. Graph Models

A `Customer–Product` graph may hold two `PURCHASED` edges at different timestamps. Using only endpoints for edge equality collapses two distinct purchases. Clarify the grain: **current relationship state** vs. **purchase event with `eventId`/time**.

### 26.4. Analytical Modeling

A sales fact may key off `sourceLineId`; two facts with matching `quantity` and `netAmount` remain distinct if they represent two real sales lines. An SCD2 dimension carries its own version ID; keying a `Set` on `productId` drops historical versions.

**An `equals` right for `ProductId` is wrong for `ProductVersionId` or `SalesLineId`.**

## 27. Migrations: Changing Equality Changes the Data Contract

Suppose SKUs were initially unique per `(catalogCode, skuCode)`. Expanding to multi-tenant changes the key to `(tenantCode, catalogCode, skuCode)`.

Blast radius:

1. Value object adds `tenantCode`.
2. `equals`/`hashCode` and tests change.
3. `HashMap`/`Set` caches and deduplicators need the new key.
4. `UNIQUE` index scope changes.
5. APIs, event payloads, and consumers may require tenant.
6. Legacy rows missing tenant must be backfilled or quarantined.
7. Redis keys, partition keys, and idempotency scopes may shift.
8. Serializers/deserializers and old snapshots need migration.
9. Legacy consumers dropping tenant can mis-deduplicate.
10. Versioned contracts are needed so rolling deploys don't mix key meanings.

Never treat changing equality on a cross-system business key as a harmless internal refactor.

### 27.1. When Business Codes Change While the Entity Remains One

If product `P0012` renames to `SKU-2026-12`, you may need:

~~~text
ProductIdentity: stable durableProductId
ProductCodeAlias: sourceSystem + code + validPeriod
ProductVersion: attribute versions keyed by versionId
~~~

Identify the entity by `durableProductId`, aliases by code and time, and versions by `versionId`. Never redefine entity equality around mutable names/codes and lose history.

## 28. Anti-Patterns to Catch in Code Review

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Overriding `equals` alone | Hash collections malfunction | Override matching `hashCode` |
| Hashing mutable status/name | Key lost inside `Map` | Immutable keys or stable entity ID |
| Entity `equals` over all fields | Broken identity, lazy loads, recursion | Explicit identity rule |
| Two transient `null`-ID entities compare equal | New entities accidentally collapse | Handle transient entities per policy |
| Record holding mutable `List` | Hash/values mutate via alias | Copy collections, immutable elements |
| Record holding raw `byte[]` | Reference equality | `Arrays.equals`/`hashCode` and clone |
| Tolerance threshold in `equals` | Breaks transitivity | Separate approximate-comparison method |
| Inconsistent `BigDecimal.scale` handling | `10.0` ≠ `10.00` unexpectedly | Domain canonicalization |
| Matching customers by name/email | Conflating distinct people | Durable identity, crosswalk |
| Omitting tenant/source from key | Multi-source collisions | Namespaced composite key |
| `Map` keyed by `ProductId` holding SCD2 versions | Drops versions | Key by `ProductVersionId` |
| Using `hashCode` as DB `PRIMARY KEY` | Collisions | Real UUID/PK/`UNIQUE` |
| Testing only `a.equals(b)` | Misses hash contract | Test `HashSet`/`HashMap` |
| Service `Set` replacing DB `UNIQUE` | Race across writers | Constraints + transactions |
| Java normalizes differently from SQL | Duplicates or false conflicts | Round-trip integration tests |
| Default `getClass()` with ORM proxies | Broken `equals` | Framework-specific review & tests |
| `toString` printing PII fields | Data leaked to logs | Restrict exposed fields |
| Unversioned equality policy changes | Cache/migration/consumer bugs | ADRs, compatibility, backfills |

## 29. Practice Exercise: Validating an Order and Product Model

A retail marketplace has these requirements:

- Multiple tenants reuse identical SKU codes.
- `Product` has a stable identity; category evolves via SCD2.
- `Order` is created offline and synced via UUID.
- `CreateOrder` may be retried multiple times.
- `OrderLine` stores locked `capturedUnitPrice`/currency.
- One `Order` may contain two lines for the same SKU with different promos.
- `Refund` has its own lifecycle.
- Line-level sales facts must resolve the exact `ProductVersion` as of sale date.
- Stack: Java 17, PostgreSQL, and JUnit 5.

### 29.1. Part A — Lock Down Equality Policies

For each type—**`Sku`, `ProductIdentity`, `ProductVersion`, `SalesOrder`, `OrderLine`, `Money`, `CreateOrderRequestKey`, `OrderCreatedEvent`**—specify:

1. Grain of one instance.
2. Business identifier / technical key.
3. Exact fields included in equality.
4. Which fields may mutate.
5. Safe as a `HashMap` key / `HashSet` element?
6. Supporting database constraints?

### 29.2. Part B — Java Implementation

Implement:

- Immutable `Sku` with tenant/catalog/code.
- `Money` using `BigDecimal`/`Currency` with explicit scale rules.
- Immutable `OrderId` wrapping UUID.
- `OrderSnapshot` with defensive `List` copying.
- `BinaryTag` with content-based byte equality and two-way cloning.
- `ValidInterval` enforcing `[from, to)`.
- `ProductVersionId` distinct from `ProductId`.
- `CreateOrderRequestKey` with tenant/client/`requestId` for idempotency.

### 29.3. Part C — Unit, Property, and Integration Tests

Verify:

1. Reflexive, symmetric, transitive, consistent, non-null.
2. Equal-implies-same-hash; `HashSet`/`HashMap` recognize equivalent instances.
3. Different tenant or catalog never compares equal.
4. Letter case, leading zeros, and Unicode match source rules.
5. `Money` `10.0` vs. `10.00` follows policy.
6. Snapshot cannot be mutated via input or accessor.
7. `[01/07, 01/08)` includes left bound, excludes right bound.
8. Two `ProductVersion`s for the same product with distinct version IDs never collapse.
9. Entity pre/post-persist keeps chosen hash contract intact.
10. Two `CreateOrder` requests sharing an idempotency key never create two orders.
11. Two concurrent `INSERT` transactions for the same SKU allow at most one to succeed.
12. Overlapping SCD2 intervals are rejected; facts resolve the right version as of sale date.

### 29.4. Starting SQL

~~~sql
CREATE TABLE sku_identity (
    sku_id uuid PRIMARY KEY,
    tenant_code text NOT NULL,
    catalog_code text NOT NULL,
    sku_code text NOT NULL,
    UNIQUE (tenant_code, catalog_code, sku_code)
);
~~~

**Passing criteria:** every type has an explicit equality policy; value objects are immutable and domain-valid; `Map`/`Set` never lose keys; entities preserve identity across lifecycles; Java and database share namespaces; cross-row and concurrency invariants have transaction tests.

## 30. Sign-Off Checklist and Conclusion

- **Grain:** is this an entity, value, version, snapshot, or event?
- **Identity:** do key components include full tenant/source/namespace scope?
- **`equals`:** reflexive, symmetric, transitive, consistent, non-null?
- **`hashCode`:** do all equal objects share hashes over stable fields?
- **Collections:** do `HashSet`/`HashMap` locate equivalent instances?
- **Records:** are `List`/`Map`/`Set`/arrays and inner elements immutable or copied?
- **Arrays:** are `Arrays.equals`/`hashCode` used when content equality is intended?
- **Numerics:** do `BigDecimal` scale, rounding, currency, `NaN`, and tolerance follow policy?
- **Temporal:** are `Instant`/offsets/time zones and `[from, to)` right?
- **Inheritance:** could subclasses or proxies break symmetry or transitivity?
- **ORM:** are transient, persisted, detached, proxied, and late-ID states tested?
- **Relationships:** does `equals` avoid infinite recursion and lazy loading?
- **Domain invariants:** do constructors/methods, transactions, and DB constraints reinforce each other?
- **Database:** do `UNIQUE`/FK/`CHECK`/`EXCLUDE` and Java equality agree on keys?
- **Distribution:** do multi-writer and retry flows have properly scoped IDs/idempotency?
- **History:** is `ProductId` distinct from `ProductVersionId`, and do corrections preserve keys?
- **Tests:** do JUnit, property, integration, and concurrency suites cover edge cases?
- **Migrations:** do equality changes account for caches, APIs, events, and legacy rows?
- **Security:** does `toString`/logging avoid leaking sensitive data?

**Conclusion:** `equals`, `hashCode`, and immutability are **executable parts of data modeling decisions**, not mere Java syntax details. Value objects must compare by agreed canonical values and stay immutable once used as keys; entities must retain stable identity across state changes; versions need dedicated identities; and the database must guard invariants across concurrent transactions and writers. When **business semantics, Java types, and storage schemas** align and are tested together, teams avoid subtle failures like collapsing distinct entities, broken lookups, bad deduplication, and corrupted historical data.
