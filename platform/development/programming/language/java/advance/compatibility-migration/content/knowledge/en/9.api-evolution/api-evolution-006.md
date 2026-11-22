# Keeping `equals`, `hashCode`, comparators, and representation formats stable

In Java API evolution, a library can keep all classes, methods, and public signatures intact yet still cause applications using the library to behave differently than before. Seemingly small changes in `equals(Object)`, `hashCode()`, `Comparator`, `Comparable.compareTo`, or the way string representations are generated can break business contracts, data structures, caches, record ordering, digital signatures, or data exchange protocols.

For example: an upgrade adds a `displayName` field to a customer object. If you automatically include that field in `equals` and `hashCode`, two customers with the same identifier but different name spellings suddenly become two different keys. If you change a comparator from ordering by code to ordering by name, a `TreeSet` that previously deduplicated records by code might keep or drop a different set of records. If you change `toString()`, which clients have been using as a CSV format, new data may no longer be parsed accurately by older systems.

This is primarily a **behavioral compatibility risk**. Methods may still be linked successfully by the JVM and source code may still compile, but the meaning of comparison, hashing, sorting, and representation has changed. For safe API evolution, these behaviors must be treated as part of the contract that consumers can depend on, rather than arbitrary implementation details.

## 1. Four contracts often overlooked during version upgrades

| Contract | Where does the application use it? | What can break when it changes? |
|---|---|---|
| `equals` | Duplicate checking, sets, value comparison, business logic | Two objects previously treated as one now become two, or vice versa |
| `hashCode` | `HashMap`, `HashSet`, hash tables and caches using objects as keys | Key lookup fails, unexpected duplicates appear, hash distribution changes |
| `Comparator` / `compareTo` | `TreeMap`, `TreeSet`, sorting, pagination, priority queues, binary search | Element ordering and grouping change; `compare(a,b)==0` can cause key loss |
| Representation format | `toString`, CSV, JSON, logs, audits, cache keys, wire protocols | Old parsers cannot read it, strings are misinterpreted, or data is no longer stable |

What they have in common is that these contracts often do not appear explicitly in the library's ABI. Binary API comparison tools can conclude that public methods still exist, but they cannot prove that the results they return still have the same meaning.

### 1.1. Distinguishing three layers of compatibility

- **Binary compatibility:** old consumer bytecode can link against the new library without encountering errors such as `NoSuchMethodError` or `IllegalAccessError`.
- **Source compatibility:** old consumer source code still compiles when using the new library.
- **Behavioral compatibility:** the assumptions that consumers have relied on still hold true, such as “two keys with the same identifier are equal” or “data is sorted in ascending order by code”.

Changing the body of `equals` in a class might not change any public method descriptor. Therefore, **binary compatibility does not imply behavioral compatibility**.

## 2. The contract of `equals(Object)`

`equals` defines an equivalence relation according to the semantics of an object. `Object.equals` defaults to object identity; value objects typically override it to compare by data or business key.

Java specifies that the `equals` relation on non-`null` references must satisfy these fundamental properties:

1. **Reflexive:** for any non-`null` reference `x`, `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` must produce the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` is also true.
4. **Consistent:** multiple invocations for the same two objects must return the same result if the information used in the comparison has not changed.
5. **Non-nullity:** `x.equals(null)` must be `false`.

This is the basic Java contract. When upgrading a library version, there is also the **application contract**: which attributes determine that two objects are the same entity or the same value?

### 2.1. Decide “equality” based on meaning, not on field count

Consider a value object identifying a product:

```java
import java.util.Objects;

public final class ProductKey {
    private final String tenantId;
    private final String productId;

    public ProductKey(String tenantId, String productId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.productId = Objects.requireNonNull(productId);
    }

    public String tenantId() {
        return tenantId;
    }

    public String productId() {
        return productId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductKey)) return false;
        ProductKey that = (ProductKey) other;
        return tenantId.equals(that.tenantId)
                && productId.equals(that.productId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, productId);
    }
}
```

Here, the contract identity is the pair `(tenantId, productId)`. Two keys with this same pair are considered equivalent, regardless of where the objects were created.

Suppose a later version adds `displayName` for display purposes:

```java
private final String displayName;
```

If `displayName` is purely presentation information, including it in `equals` changes the definition of identity. A key that previously matched a record in the cache may suddenly fail to match just because the display name changed.

You should state explicitly in the API documentation: “Two `ProductKey` instances are equal when they have the same `tenantId` and `productId`; the display name does not participate in identity.” This decision must be maintained across releases unless the project intentionally performs a breaking behavioral change.

### 2.2. Values and entities do not necessarily have the same equality semantics

For a **value object**, `equals` is usually based on all components that make up the value: two coordinates or two monetary amounts with the same normalized attributes are considered equal.

For an **entity**, the contract can be based on a stable identifier. However, an entity not yet assigned an ID, an entity from an ORM proxy, a database-generated ID, and pre-/post-persistence stages all require a dedicated design. You should not mechanically apply “all entities are equal if they share the same ID” when the ID may be `null` or assigned after the object is already used as a key in a collection.

What needs to stay stable is the **published meaning** of the comparison, not a single formula for every kind of object.

### 2.3. Extending classes and the symmetry rule

A base class whose `equals` compares using `instanceof`, followed by a subclass that adds a new field to the comparison, very easily breaks symmetry.

Conceptual example:

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof Point)) return false;
        Point p = (Point) other;
        return x == p.x && y == p.y;
    }
}

class ColoredPoint extends Point {
    final String color;

    ColoredPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof ColoredPoint)) return false;
        ColoredPoint p = (ColoredPoint) other;
        return super.equals(p) && color.equals(p.color);
    }
}
```

With `Point(1,2)` and `ColoredPoint(1,2,"red")`, comparisons in the two directions can yield different results. This is a violation of the `equals` contract, not merely a code style issue.

Some design strategies include: making value objects `final`; using composition instead of inheritance; restricting comparison rules to the exact runtime class; or a clearly defined inheritance compatibility mechanism. Each choice has different trade-offs regarding extensibility and compatibility; you should not switch between strategies without checking consumers.

### 2.4. `getClass()` and `instanceof` are both contract decisions

- `getClass() == other.getClass()` can restrict equality to the exact runtime class. This is clear for some value types, but may not be suitable for proxies/subclasses.
- `instanceof` allows certain subclasses to participate in equality, but symmetry and transitivity must be protected when subclasses add state.

When a library is being subclassed by many consumers, changing from `instanceof` to `getClass()` can cause two objects that used to be equal to become unequal without any compilation error. That behavior must be treated as a semantic-level API change.

## 3. `hashCode()` is a mandatory companion to `equals`

Java specifies:

- If `a.equals(b)` is `true`, `a.hashCode()` and `b.hashCode()` must be equal.
- Two unequal objects **are allowed** to have the same hash code (collision).
- During a single execution, multiple calls to `hashCode()` on the same object must be consistent if the information used in the calculation has not changed.

The Java contract **does not require** every object to have a hash value that stays unchanged forever across processes, JVMs, or application versions. However, if a project itself uses hash codes as persisted data, shard keys, or cross-process cache keys, the project has created an additional contract of its own that must be managed.

### 3.1. Why must `equals` and `hashCode` be changed together?

`HashMap` and `HashSet` use the hash to choose the search bucket, and then use equality to decide whether two keys are duplicates. If two keys are equal but have different hash codes, lookup and deduplication can fail.

Example of an incorrect implementation:

```java
import java.util.Objects;

final class UserKey {
    private final String id;

    UserKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof UserKey
                && Objects.equals(id, ((UserKey) other).id);
    }

    // Does not override hashCode(): violates the contract.
}
```

Two `UserKey("u-1")` instances can be equal according to `equals` but use the default `Object.hashCode` based on each object's identity. `HashSet` has no basis to treat them as the same key. Both methods must be overridden with the same semantic criteria.

### 3.2. Avoid using mutable state as a hash key

Another common mistake is including mutable fields in `equals` and `hashCode`:

```java
import java.util.Objects;

class MutableKey {
    String code;

    MutableKey(String code) {
        this.code = code;
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof MutableKey
                && Objects.equals(code, ((MutableKey) o).code);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(code);
    }
}
```

If the key is already inside a `HashMap` and `code` is then modified, the hash computed after modification may differ from when it was inserted:

```java
import java.util.HashMap;
import java.util.Map;

Map<MutableKey, String> map = new HashMap<>();
MutableKey key = new MutableKey("A");
map.put(key, "value");

key.code = "B";

// Looking up with a key whose state has changed may fail.
System.out.println(map.get(key));
```

For objects used as keys, prefer immutable fields participating in equality/hashing. If changing the identifier is unavoidable, remove the key from the collection while it still holds its old state, create a new key, and re-insert it. Do not expect `HashMap` to automatically track internal changes inside a key.

### 3.3. A hash change valid under Java can still break applications

Suppose version 1 computes the hash using `Objects.hash(tenantId, productId)`, and version 2 switches to another algorithm while still ensuring equal keys have identical hashes. Under Java's basic contract, this change is not necessarily wrong.

However, the system may have already:

- Stored `hashCode()` directly in a database as a record “ID”.
- Used it to select a partition in a distributed system.
- Used it as an out-of-process cache key.
- Compared hashes across different service versions.

Those usages expose the hash algorithm, which should have remained an implementation detail. When the algorithm changes, records may be redistributed or not found.

For identifiers that need to persist long-term, design a separate **stable key/canonical identifier** with explicit versioning and encoding rules. Do not use `Object.hashCode()` as a durable identifier.

### 3.4. Notes on arrays and records

Arrays in Java compare by identity if calling `equals` inherited from `Object`; `Objects.equals(array1,array2)` also does not automatically compare elements if the two arrays are different objects. For value objects containing arrays, if content-based comparison is desired, use `Arrays.equals` / `Arrays.hashCode`, or `deepEquals` / `deepHashCode` variants when appropriate for the data model.

A Java `record` automatically generates `equals` and `hashCode` based on its record components. If a component is added to a record, the generated equality/hash behavior can change even when related constructors or APIs are adjusted so that the source still compiles. For an array-typed component, the generated equality does not automatically recognize two different array instances with identical elements as equal. Do not assume records solve all of semantic equality design.

## 4. The contract of `Comparator` and `Comparable`

Java supports two ways of defining ordering:

- `Comparable<T>`: natural ordering declared by the class itself via `compareTo`.
- `Comparator<T>`: a comparison strategy external to the class, allowing multiple different orderings for the same object type.

When comparing `a` and `b`, a negative result means `a` comes before `b`, zero means equivalent **according to the comparator**, and a positive result means `a` comes after `b`. You must not assume the result is strictly -1, 0, or 1; check the sign of the result.

### 4.1. Properties to preserve

A proper comparator must preserve properties such as:

1. **Sign reversal when swapping arguments:** the sign of `compare(a,b)` must be the opposite of the sign of `compare(b,a)`.
2. **Transitivity:** if `a > b` and `b > c` according to the comparator, `a > c` must also hold.
3. **Consistency upon comparator equality:** if `compare(a,b)==0`, then when comparing against another `c`, the signs of `compare(a,c)` and `compare(b,c)` must be the same.
4. **Determinism under the same conditions:** ordering should not depend on state that mutates unexpectedly during sorting or while stored in a sorted collection.

A comparator is not required to be consistent with `equals` for every use case, but **consistency with equals is especially important when used as the contract for a sorted set/map**.

### 4.2. Avoid overflow bugs when using subtraction

You should not write:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

If the difference exceeds the range of `int`, the ordering can become wrong due to overflow. You should write:

```java
Comparator<Integer> safe = Integer::compare;
```

For objects:

```java
import java.util.Comparator;

Comparator<Order> byPriority =
        Comparator.comparingInt(Order::getPriority);
```

Helpers like `comparingInt`, `comparingLong`, and `thenComparing` help express ordering more clearly than manual subtraction.

### 4.3. Comparator returning 0 does not necessarily mean `equals` is true

An important example:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

Set<String> hash = new HashSet<>();
Set<String> sorted = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

hash.add("Java");
hash.add("java");

sorted.add("Java");
sorted.add("java");

System.out.println(hash.size());   // 2
System.out.println(sorted.size()); // 1
```

`String.equals` is case-sensitive, whereas `String.CASE_INSENSITIVE_ORDER` treats the two strings as equivalent according to the comparator. `TreeSet` relies on the comparator to decide whether two elements share the same key position; thus it may keep only one of the two.

This is not a bug in `TreeSet`. It shows that **the definition of duplicates in a sorted set is determined by the comparator**.

When changing a comparator in an upgrade, check:

- Does the number of elements in a `TreeSet` change?
- Which keys in a `TreeMap` are treated as duplicates and could be overwritten?
- Do search/sort APIs still use the same comparison criteria?
- Is already-indexed or paginated data still valid?

### 4.4. `BigDecimal.compareTo` and `equals` demonstrate an intentional difference

`BigDecimal` is a classic example of a type whose natural ordering is **not fully consistent** with `equals`.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

Because `BigDecimal`'s `equals` also considers scale, two numerically equal values may not be equal under object equality. A `HashSet<BigDecimal>` and a `TreeSet<BigDecimal>` can yield different deduplication results.

In financial APIs, you must decide explicitly whether the contract requires “equal numeric value” or “equal value and scale”. Do not silently switch from `equals` to `compareTo` just to fix a test if other consumers rely on scale.

### 4.5. Creating a consistent ordering for a value key

For `ProductKey` above, an ordering by the same two identity components can be written as:

```java
import java.util.Comparator;

Comparator<ProductKey> BY_KEY =
        Comparator.comparing(ProductKey::tenantId)
                  .thenComparing(ProductKey::productId);
```

Because both equality and the comparator are based on the same pair of strings with case-sensitive semantics, two objects with a comparator result of 0 are also equal according to `equals`.

If sorting by `displayName` is a UI requirement, create a separate comparator with a clear purpose-driven name, such as `BY_DISPLAY_NAME`. Do not replace the identity comparator that `TreeMap`, `TreeSet`, or pagination algorithms already use to represent stable keys.

### 4.6. Stable sorting does not mean deterministic ordering

A *stable* sorting algorithm preserves the relative order of elements for which the comparator returns 0. However, if the input comes from a `HashMap` or an SQL query without deterministic ordering, the order of tied elements can still vary across runs.

For APIs returning lists with reproducible ordering, a **deterministic tie-breaker** is needed:

```java
Comparator<Order> BY_CREATED_AT_AND_ID =
        Comparator.comparing(Order::getCreatedAt)
                  .thenComparing(Order::getId);
```

If `createdAt` is not unique, `id` helps fix the ordering among records with the same timestamp. For cursor-based or offset-based pagination, changing the ordering or tie-breaker between versions can cause duplicate or skipped records. Sort order must be treated as part of the response contract.

### 4.7. `null`, locale, case, and Unicode are decisions that must be fixed

A comparator can accept or reject null; this policy must be consistent:

```java
Comparator<String> NULL_LAST =
        Comparator.nullsLast(Comparator.naturalOrder());
```

If an upgrade switches from null-first to null-last, paginated data or priority results can change while the code still compiles.

String comparison also depends on the goal:

- `String.compareTo` compares according to Java string lexicographic order, not the alphabetical order of a natural language.
- `Collator` can use language/locale rules. Results can be affected by locale configuration, collation data, and environment versions.
- Case folding, Unicode normalization, and diacritic handling can turn previously distinct strings into equivalent ones, or vice versa.

If ordering has business value or needs to be stable across services, choose a formal rule, document the locale and algorithm version where appropriate, and test with accented data, uppercase/lowercase letters, and special Unicode characters.

## 5. Representation formats: from `toString` to JSON, CSV, and cache keys

An object often has multiple types of representations:

- Human-readable representations for developers: `toString()` and logs.
- Representations for clients: JSON, XML, CSV, Protobuf, or published text formats.
- Representations used as keys: identifier strings, canonical keys, cache keys.
- Long-lived representations: records stored in a database, event logs, messages, or digital signatures.

They should not be treated as a single contract. `toString` is generally suited for debugging, whereas wire formats and persisted formats require explicit rules, versioning, and compatibility testing.

### 5.1. Why should `toString()` not be used as a data protocol?

Suppose the initial version has:

```java
public String toString() {
    return tenantId + ":" + productId;
}
```

Clients split the string by `:` to extract the two fields. An upgrade changes it to:

```java
public String toString() {
    return "ProductKey[tenant=" + tenantId
            + ", id=" + productId + "]";
}
```

The `toString()` call still exists and has the same `String` return type. However, clients parsing the old string can break immediately. Even the old format `tenantId + ":" + productId` is unsafe if one of the components contains a `:` character without escaping rules.

A better approach is to provide separate APIs:

```java
public String toDisplayString() {
    return "Product " + productId + " (tenant " + tenantId + ")";
}

public String toExternalId() {
    // Returns an identifier with the specified encoding/escaping.
    return encodeKey(tenantId, productId);
}
```

`encodeKey` here represents a separately defined encoding algorithm; it should not be replaced with string concatenation without delimiter rules. For identifiers used across different systems, the encoding, escaping, and format version must be published.

### 5.2. Numeric string representations must have locale and precision rules

A `String.format` or `NumberFormat` call using the default locale may produce different decimal or thousands separators depending on the environment.

Illustrative example:

```java
import java.util.Locale;

String output = String.format(Locale.US, "%.2f", 1234.5);
System.out.println(output); // 1234.50
```

Setting an explicit locale makes the output less dependent on machine configuration. For currency, separately specify precision, rounding mode, unit, and scale. `BigDecimal` helps avoid many binary representation issues of `double`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("1234.5");
String decimal = amount
        .setScale(2, RoundingMode.HALF_UP)
        .toPlainString();

System.out.println(decimal); // 1234.50
```

`RoundingMode.HALF_UP` is merely the choice in the example; real financial contracts may require HALF_EVEN or another rule. Do not silently change the rounding mode when updating a formatting library.

### 5.3. Date and time: pin the timezone and representation standard

Do not depend on `ZoneId.systemDefault()` when formatting timestamps exchanged between systems, unless that is the specified contract.

Example of representing an instant in UTC:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

Instant createdAt = Instant.parse("2025-01-02T03:04:05Z");
String timestamp =
        DateTimeFormatter.ISO_INSTANT.format(createdAt);

System.out.println(timestamp);
```

For data with local timezones, you must specifically define how offsets, time zone regions, second/nanosecond precision, and daylight saving time are handled. Switching from local time to UTC without versioning the schema can cause clients to misinterpret timestamps.

### 5.4. Charset is part of the wire format contract

When converting strings to bytes or vice versa, specify the charset:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

If the JVM is left to choose the default charset, results may depend on the environment or change upon upgrading the JDK. JEP 400 makes UTF-8 the default charset for standard Java APIs in standard environments starting from JDK 18; even so, data-exchange code should still specify encoding by contract for easier testing and integration.

### 5.5. JSON and DTOs: preserve the schema, not just `toString`

For JSON, the contract can include field names, data types, nullability, units, timezones, requiredness, enum formatting, and behavior when new fields appear. A change such as:

```json
{"customerId":"C-42","amount":"12.50"}
```

to:

```json
{"id":"C-42","amount":12.5}
```

can break old parsers/validators even though to a human reader the two objects appear to hold nearly identical information. Renaming `customerId` to `id` and changing the string `amount` to a JSON number are both schema changes that must be managed.

A new field that is merely optional may be compatible with some clients, but not necessarily with all clients—especially clients that reject unknown fields or compare JSON responses verbatim. Contract tests based on actual clients and the evolution policy of the format in use are necessary.

### 5.6. Enums, Maps, and serialization order

- Do not use `enum.ordinal()` as a persisted or wire-protocol value: adding or reordering enum constants changes the ordinal.
- `enum.name()` can be used when the constant name is treated as part of the public schema; renaming an enum constant is a contract change.
- Do not rely on `HashMap` iteration order to produce text requiring determinism. If a canonical representation is needed, define an explicit field/key order.
- For data used for digital signatures or digest computation, you must define the exact byte sequence: charset, escaping, normalization, field ordering, number formatting, and newlines.

A format change may not cause any compilation error, yet still alter hashes/digests, signatures, or how clients reconstruct canonical bytes.

## 6. API evolution example: adding a field while preserving the identity contract

Suppose version 1 of a customer management library has:

```java
import java.util.Objects;

public final class CustomerRef {
    private final String tenantId;
    private final String customerId;

    public CustomerRef(String tenantId, String customerId) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public String tenantId() { return tenantId; }
    public String customerId() { return customerId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CustomerRef)) return false;
        CustomerRef that = (CustomerRef) other;
        return tenantId.equals(that.tenantId)
                && customerId.equals(that.customerId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, customerId);
    }
}
```

Applications use `CustomerRef` as a key:

```java
Map<CustomerRef, CustomerProfile> profiles = new HashMap<>();
profiles.put(new CustomerRef("T1", "C42"), profile);

CustomerProfile found =
        profiles.get(new CustomerRef("T1", "C42"));
```

Version 2 wants to add `displayName`. There are two ways to evolve:

**The breaking-change-prone way:** add `displayName` to `equals` and `hashCode` because the IDE auto-regenerates methods based on all fields. Two objects with the same tenant and customer ID but different names will no longer be equal; old lookups can fail.

**The contract-preserving way:** keep `tenantId` and `customerId` as the identity; let `displayName` participate in display, without changing `equals` and `hashCode`. If full profile comparison is needed, create a separate profile comparison API.

Version 2 can keep the old constructor and add a new constructor:

```java
public CustomerRef(String tenantId, String customerId) {
    this(tenantId, customerId, null);
}

public CustomerRef(String tenantId, String customerId,
                   String displayName) {
    this.tenantId = Objects.requireNonNull(tenantId);
    this.customerId = Objects.requireNonNull(customerId);
    this.displayName = displayName;
}
```

Keeping the old constructor can support source and binary compatibility for clients calling the two-parameter signature, but **does not automatically guarantee behavioral compatibility**. You must still preserve equality/hashing rules and external formats. At the same time, check serialization/ORM if this object is persisted under a different schema.

### 6.1. Do not mix UI ordering with identity ordering

If version 1 has a comparator by `customerId` and version 2 wants to display customers by `displayName`, publish a second comparator:

```java
Comparator<CustomerRef> BY_ID =
        Comparator.comparing(CustomerRef::tenantId)
                  .thenComparing(CustomerRef::customerId);

Comparator<CustomerRef> BY_DISPLAY_NAME =
        Comparator.comparing(
                CustomerRef::displayName,
                Comparator.nullsLast(String::compareTo))
                  .thenComparing(CustomerRef::tenantId)
                  .thenComparing(CustomerRef::customerId);
```

`BY_ID` is appropriate for key ordering consistent with identity. `BY_DISPLAY_NAME` is a UI ordering with tie-breakers for deterministic output; it must not by default replace a comparator used in a `TreeMap` where key ordering is treated as part of the contract.

## 7. Test the contract instead of only testing the return value of the new API

When upgrading the JDK or a library, the test suite must cover the data and behaviors that consumers care about. A few isolated tests for `equals` are not enough if the application uses sorted collections, caches, serialization, or JSON protocols.

### 7.1. Testing basic `equals` and `hashCode` laws

JUnit Jupiter example for `ProductKey`:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProductKeyContractTest {
    @Test
    void equalKeysHaveEqualHashCodes() {
        ProductKey first = new ProductKey("T1", "P7");
        ProductKey second = new ProductKey("T1", "P7");
        ProductKey different = new ProductKey("T1", "P8");

        assertEquals(first, first);
        assertEquals(first, second);
        assertEquals(second, first);
        assertEquals(first.hashCode(), second.hashCode());
        assertNotEquals(first, different);
        assertNotEquals(first, null);
    }
}
```

The test above checks several important examples, but does not fully prove every property across the entire data set. For complex types, build additional property-based tests for symmetry, transitivity, consistency, and equal-hash-when-equal.

### 7.2. Testing behavior when used in collections

A more business-meaningful test:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class ProductKeyCollectionsTest {
    @Test
    void logicalIdentityWorksAsHashKey() {
        ProductKey key1 = new ProductKey("T1", "P7");
        ProductKey key2 = new ProductKey("T1", "P7");

        Map<ProductKey, String> map = new HashMap<>();
        map.put(key1, "READY");

        assertEquals("READY", map.get(key2));

        Set<ProductKey> set = new HashSet<>();
        set.add(key1);
        set.add(key2);
        assertEquals(1, set.size());
    }
}
```

This test expresses the true meaning of the key: another client creating an equivalent object can still retrieve the stored value. When a new display field is added to the class, the test must continue protecting the original identity definition.

### 7.3. Testing comparators and consistency with equality

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Comparator;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;

class ProductKeyOrderTest {
    private static final Comparator<ProductKey> BY_KEY =
            Comparator.comparing(ProductKey::tenantId)
                      .thenComparing(ProductKey::productId);

    @Test
    void comparisonZeroMatchesLogicalIdentity() {
        ProductKey a = new ProductKey("T1", "P1");
        ProductKey b = new ProductKey("T1", "P1");
        ProductKey c = new ProductKey("T1", "P2");

        assertEquals(0, BY_KEY.compare(a, b));
        assertEquals(a, b);
        assertTrue(BY_KEY.compare(a, c) < 0);

        TreeSet<ProductKey> set = new TreeSet<>(BY_KEY);
        set.add(a);
        set.add(b);
        set.add(c);
        assertEquals(2, set.size());
    }
}
```

If a comparator is not designed to be consistent with equality, document the reason clearly and test the desired collection behavior. For comparators used for UI lists, consistency with `equals` may not be a goal; for `TreeSet`/`TreeMap` used as key storage, it is usually a critical requirement.

### 7.4. Golden tests for data representation

When a format is a public contract, store a sample data set and expected outputs:

| Sample input | What must be fixed |
|---|---|
| Strings with Vietnamese diacritics, emojis, and combining Unicode characters | Charset, normalization, and escaping |
| Currency with decimal places, negative values, and large numbers | Scale, precision, rounding, decimal separator |
| Instants with offsets and date rollovers | Timezone, offset, timestamp format |
| Empty strings, null, missing fields | Rules for representing null/missing values |
| New enums and deprecated enums | Schema/value names and ability to read older versions |
| JSON objects with new fields or changed field order | Unknown fields policy, field order if committed to |

If byte-for-byte output matters, compare **bytes** instead of only comparing objects after deserialization. If the contract allows differing JSON field orders, tests should compare by schema/semantics rather than verbatim string snapshots.

### 7.5. Comparing old and new versions on the same fixture

A useful migration workflow:

```text
Finalized fixture set
        |
        +--> run with library v1 --> equality/hash/order/format results
        |
        +--> run with library v2 --> equality/hash/order/format results
                                        |
                                        v
                             compare against contract
```

You do not need to expect **every numeric hash value** between two versions to always be identical unless the system has a specific contract for that. The property “equal objects have equal hashes” must be preserved; and if hashes are persisted or used cross-process, you must test the exact hash value or the published canonical hash algorithm.

Running each version separately allows comparing behavior without having to load two versions of the same class name into a single class loader. If there are consumers compiled against library v1, you also need to run the old binaries against library v2 to verify the separate binary compatibility layer.

## 8. Migration when changing equality, comparators, or formats is unavoidable

It is not always possible to keep the old contract forever. For example, new identity rules may need to add a tenant, currency unit, or legal jurisdiction; a pagination system may need to change ordering; a protocol may require a new date/time format. In such cases, treat this as a **breaking behavioral change** and establish a migration strategy.

### 8.1. Explicitly document old and new contracts

A change table can record:

| Component | Old version | New version | Affected consumers |
|---|---|---|---|
| Equality | By `customerId` | By `tenantId + customerId` | Caches, HashSet, deduplication |
| Hash | By customer ID | By tenant/customer pair | Cache keys, partitions, maps |
| Comparator | By createdAt | By createdAt then ID | List APIs, pagination, TreeSet |
| JSON field | `createdAt` as local text | `createdAt` as ISO-8601 UTC | Clients, event subscribers |

Do not merely write “improve comparator” or “refactor equals” in the changelog. Describe **which set of inputs will produce different results** and how consumers should migrate.

### 8.2. Versioning behavior when parallel support is needed

For sort orders, two clearly named comparators/APIs can be provided:

```java
Comparator<Order> LEGACY_ORDER = ...;
Comparator<Order> ORDER_V2 = ...;
```

For wire formats, you can publish a new schema version, a versioned API endpoint, or a new DTO. During migration, the server can support reading both old and new formats, while only writing a single canonical format once consumers are ready.

For equality, immediately changing `equals` of a public class currently used as a key can have wide impact. When old semantics cannot be maintained, consider creating a new key type with a clear name like `TenantCustomerKey` rather than silently altering `CustomerKey`.

### 8.3. Reprocessing stored state and indexes

If a hash or comparator has been used as a storage structure, migration may require:

- Rebuilding caches or invalidation so old keys are not carried over to the new algorithm.
- Reindexing sorted data or search structures.
- Migrating partitions/shards if the distribution key actually changed.
- Re-issuing pagination cursors under the new sort version.
- Transforming persisted data to the new schema.
- Allowing reading of the old format during the transition period.

In particular, never modify the fields used in the hash of **a key currently inside a HashMap/HashSet** and expect the collection to reorganize itself. You must rebuild the collection or move entries under the new keys.

### 8.4. Rolling out according to consumer versions

In multi-service systems, producers and consumers might not update simultaneously. Test the relevant combinations:

- Old producer ↔ old consumer: baseline.
- New producer ↔ new consumer: target contract.
- New producer ↔ old consumer: backward compatibility when rolling out the producer first.
- Old producer ↔ new consumer: forward compatibility when rolling out the consumer first.

For representation formats, explicitly identify which combinations are guaranteed to be supported. If a change introduces breaking behavior, use a rollout order, feature flag, or versioned endpoint instead of assuming all services will upgrade at once.

## 9. Notable special scenarios

### 9.1. ORM entities and proxies

JPA/Hibernate or similar frameworks can generate proxy subclasses. Relying in `equals` on `getClass`, pre-/post-persistence IDs, or lazy-loaded fields can lead to unexpected results.

When modifying entities, test simultaneously:

- A new entity without an ID or not yet saved.
- A saved entity with a stable ID.
- An entity loaded in a different transaction/session.
- A proxy and the original entity if the framework creates proxies.
- An entity placed in a `HashSet` before and after persistence state changes.

There is no single `equals` formula suitable for all ORMs. It must be based on the identity model, lifecycle, and framework requirements.

### 9.2. Cache and idempotency

A service might use `CustomerKey` as a key for a cache or duplicate-handling filter. If equality or the canonical key changes, the same request may no longer be recognized as a duplicate. The consequence can be processing a transaction twice, bypassing the cache, or returning incorrect data.

For idempotency keys, use a published identifier or canonical representation, rather than relying on the default `toString`/`hashCode` of a business object. Test both old and new service versions with the same set of requests.

### 9.3. Comparators in databases and pagination

An API may sort data in Java while the database query also has an `ORDER BY`. If the two sides use different collation rules, the ordering may not match. This is particularly dangerous with pagination/cursors: a record can move between pages when ordering or tie-breakers change.

Describe the sort key in a way that can be reproduced on both the server and the database, paying attention to null ordering, locale/collation, timezones, and duplicate values. If you change the comparator, version the cursor or invalidate old cursors under a published policy.

### 9.4. Compatibility with Kotlin/Scala or non-Java clients

Other JVM clients can also use `equals`/`hashCode` and Java collections, though they may automatically generate equality according to their own language's class/value types. When modifying a public Java API, inspect existing JVM consumers and how they map data.

If non-JVM clients receive JSON or text, they do not care directly about Java methods, but will be affected if wire representation, list ordering, or null/encoding rules change.

### 9.5. Logs and audits are not merely presentation

Changing `toString` may be acceptable when it is strictly for debugging, but if logs are parsed by systems using regular expressions, used for audits, or trigger alerts, the actual format has become an operational contract.

For these streams, prefer structured logging with a stable schema. New log fields should be added intentionally; do not use `toString` output from complex entities as machine-parsed messages.

## 10. Process for evaluating an API change

When changing a value object, comparator, or serializer, you can follow this sequence:

### Step 1: Inventory where the behavior is used

Search for calls to `equals`, `hashCode`, `compareTo`, `Comparator`, `sort`, `TreeSet`, `TreeMap`, `HashSet`, `HashMap`, serializers, and places turning objects into strings. Do not look only for direct calls: many collections and frameworks invoke these methods implicitly.

### Step 2: Document the intended contract

Identify the identity components, which fields are ignored, null rules, the equality-comparator relationship, tie-breaker ordering, precision/rounding, timezone, charset, and output schema. Distinguish what must remain stable from uncommitted details.

### Step 3: Lock in fixtures from the currently released version

Gather representative cases such as same ID/different name, multi-tenant codes, nulls, Unicode, numerically equal values with different scales, timestamps with offsets, keys with duplicate sort keys, and edge cases. Keep the verified expected behavior of the old version.

### Step 4: Implement the change and run contract tests

Test basic Java rules, collection behavior, comparators, and data formatting. If there is a schema/wire protocol, run consumer tests; if there are persisted hashes/keys, test their migration.

### Step 5: Evaluate compatibility by layer

| Compatibility layer | Checks |
|---|---|
| Source | Recompile supported consumers/sources |
| Binary | Run old consumer binaries against the new artifact when needed |
| Object behavior | Equality/hash, collection lookup, comparator order |
| Data | Schema, encoding, format, old/new parsers |
| Operations | Cache, idempotency, partitions, indexes, pagination, logs |

### Step 6: Release with a migration guide

If the change breaks behavior, documentation needs to state affected inputs, old/new behavior, migration steps, ability to read old data, rollout order, and rollback guidance. Do not rely solely on semver or a generic changelog.

### Step 7: Monitor after deployment

Observe meaningful metrics such as cache miss rate, duplication rate, idempotency conflicts, deserialization errors, parsing errors, shifts in sort/page distribution, and the volume of data needing reindexing. If there is a mechanism supporting two formats in parallel, monitor usage of the old format before removing it.

## 11. Common misconceptions

**“The `equals` and `hashCode` methods still exist, so the API is compatible.”** Having the same signatures only helps partially with binary/source compatibility. The meaning of the results can still change.

**“Unequal objects must have different hashes.”** No. Hash collisions are allowed; only the direction “if equal, then equal hashes” is mandatory.

**“Hash codes must remain invariant across all JVMs and all processes.”** That is not part of the general Java contract. If a durable identifier is needed, design a dedicated key API and version the algorithm.

**“Using a comparator to sort only affects display order.”** In `TreeMap` and `TreeSet`, the comparator also determines when two keys are considered duplicates. Changing the comparator can change the entire data set.

**“A comparator returning 0 means `equals` is always true.”** Not by default. `BigDecimal` and case-insensitive comparators are clear examples.

**“If sort is stable, the output order is always deterministic.”** Not if the comparator ties many elements and the input order is non-deterministic. A stable tie-breaker is needed for paginated or snapshot APIs.

**“Adding a field to a record does not affect equality.”** A record's auto-generated equality/hash is based on its components, so changing a record's structure can change its semantic contract.

**“`toString` is only for debugging, so it can be changed arbitrarily.”** True for APIs that do not commit to a format and have no dependent consumers; false if systems already use the output as exchange data, cache keys, audits, or parser inputs.

**“The JSON contains the same information, so renaming a field or changing number/string type is still compatible.”** No. Clients may enforce strict schemas or rely on exact field types.

**“Just recompiling all consumers is enough.”** Compilation does not detect changes in semantic equality, comparators, cache keys, or wire representations. Contract tests and data migration plans are needed.

## 12. Checklist for keeping contracts stable

- [ ] Accurately defined which fields/attributes constitute equality.
- [ ] `equals` satisfies reflexivity, symmetry, transitivity, consistency, and non-nullity.
- [ ] `hashCode` is based on the same equality criteria; hash keys do not mutate while inside a collection.
- [ ] Evaluated impact on `HashMap`, `HashSet`, caches, and idempotency.
- [ ] Identified which comparators define identity ordering and which are strictly for presentation.
- [ ] Verified correctness, transitivity, and cases where the comparator returns 0.
- [ ] Evaluated consistency with `equals` when using `TreeMap` or `TreeSet`.
- [ ] API ordering has explicit tie-breakers when paginating or when reproducible results are required.
- [ ] Policies for null, locale, Unicode, case, and collation are specified.
- [ ] `toString` is not used as a wire format without a clearly published contract.
- [ ] Numeric scale, rounding, timezone, charset, and JSON data types are fixed.
- [ ] `hashCode` or `enum.ordinal()` is not used as a persisted identifier without a dedicated versioning mechanism.
- [ ] Built fixtures/golden tests for old and new versions.
- [ ] Tested old data and old consumers in the actual deployment order.
- [ ] Considered reindexing, cache invalidation, persisted key conversion, and cursor versioning if needed.
- [ ] Breaking behaviors are announced in release notes/migration guides, not just in code diffs.

## 13. Conclusion

In Java API evolution, `equals`, `hashCode`, comparators, and representation formats are **behavioral contracts** that can be just as important as public method signatures. They determine whether objects are considered the same value, whether keys are found in collections, in what order records are sorted, and how data is interpreted outside the JVM.

To maintain compatibility, establish stable equality and hash criteria without inadvertently introducing mutable state or display fields into identity; maintain comparators with clear semantics and appropriate tie-breakers; and define representations with explicit schemas, encodings, locales, timezones, and precision. When changes are unavoidable, treat them as behavioral breaking changes, provide a migration path, and verify with contract tests against real consumers, caches, and data.

**An API can still compile and link successfully yet no longer be compatible with what API users have come to rely upon.** Protecting these behavioral contracts is a core part of a safe Java compatibility migration strategy.
