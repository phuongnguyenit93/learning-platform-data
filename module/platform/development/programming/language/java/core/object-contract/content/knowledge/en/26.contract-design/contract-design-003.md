# Choosing Immutable Components for Value Objects and Keys in Java

## 1. The Problem to Solve

In Java design, a **value object** represents a value by its **content**, rather than by the identity of a changing entity. For example, a currency code, date range, coordinates, normalized product code, or a composite key `(tenantId, productCode)` can be modeled as a value object.

An object used as a **key** in a `HashMap`/`HashSet` must also keep the attributes participating in `equals()` and `hashCode()` stable for as long as it resides in the hash structure. If those attributes change, the object may sit in a "bucket" computed from the old hash, while a new lookup uses the new hash.

Therefore, when choosing the components (*component/field*) of a value object or key, do not merely ask "does this field have business meaning?"—also ask:

- Is the value stable throughout the object's entire lifecycle?
- If it is a reference, are **the referenced object itself** and all state used for comparison immutable?
- Does the data type's comparison match the business semantics?
- Does input data need normalization before computing equality?
- Does the object protect itself against mutation through constructor arguments or accessors?
- Which fields truly define value equality? Which fields are only descriptive data that should not participate in the key's identity?

**Immutability** means that the state observable through the object's API cannot change after construction. `final` on a variable/field only prevents reassigning that reference; it does **not** automatically make the object it points to immutable.

## 2. The Relationship Between Immutability, `equals()`, and `hashCode()`

Key Java contracts:

- `equals()` must be reflexive, symmetric, transitive, and consistent when the information used for comparison does not change; comparing against `null` must return `false`.
- If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` is mandatory. The converse is **not** required: equal hashes can still correspond to two different values.
- While an object is acting as a hash key, state contributing to `equals()`/`hashCode()` must not be modified. Even when the program holds **the exact same reference**, changing the hash can cause `get()` or `containsKey()` to fail to find the key.

Immutability is the simplest and strongest way to uphold this contract. However, **a key can still be valid if its class is mutable yet strictly never mutated while inside the map**; the problem is that this condition becomes hard to maintain and verify as the system grows. Preferring immutable keys eliminates this entire class of bugs.

For **ordered** structures such as `TreeMap`/`TreeSet`, you also need a stable `compareTo()` or `Comparator` that aligns with the domain's concept of key equality. If the ordering comparison treats two values as equivalent while `equals()` does not treat them as equal, tree collection behavior can diverge from hash collections.

## 3. Which Component Types Should You Choose?

A practical rule of thumb is to use values with immutable state, clear equality semantics, and no reachable path to observable mutable state.

| Component Group | Usually Suitable as an Immutable Component? | What Must Be Considered |
| --- | --- | --- |
| Primitives `int`, `long`, `boolean`, ... | Yes | Choose types/units that accurately express the data domain; be cautious with `float`/`double` |
| `String`, `UUID`, wrappers `Integer`/`Long`, `BigInteger` | Yes | Normalization rules, comparison, and value domain |
| `LocalDate`, `LocalDateTime`, `Instant`, `Duration`, `ZoneId` | Yes | Distinguish local date, global instant, time zone, and time unit |
| `BigDecimal` | Immutable itself | `equals()` considers `scale`; `compareTo()` may produce a different result |
| `enum` | Yes | Choose stable business constants; do not rely on `ordinal()` as a long-term persisted code |
| Custom value objects with all-immutable components | Yes | Must ensure end-to-end immutability and correct `equals()/hashCode()` |
| `List`, `Set`, `Map` | Only when the structure **and** all related elements/keys/values are safe | `List.copyOf`, `Set.copyOf`, `Map.copyOf` only shallow-copy element references |
| Arrays `byte[]`, `int[]`, object arrays | No, if exposed directly | Arrays are always mutable; need defensive copies and content-based equality if used as a value |
| `Date`, `Calendar`, `StringBuilder`, `ArrayList`, `HashMap` | Not directly | Mutable; must be converted to an immutable representation or deep-copied where appropriate |
| `AtomicInteger`, `AtomicReference` | Not directly | Being thread-safe for individual operations **does not mean immutable** |
| `ByteBuffer`, JPA entities, DTOs with setters | Usually no | State, cursor position, relationships, and data can change |

**Note on collections:** a collection that forbids `add()`/`remove()` can still contain mutable objects. When a child object is modified, the logical state of the key still changes even though the container does not allow adding/removing elements.

**Note on time types:** `java.util.Date` is mutable, whereas `java.time.Instant` is immutable. A key representing "order date" should consider `LocalDate`; a key representing "exact point in time" should consider `Instant`. The two concepts cannot be swapped while ignoring time zones.

## 4. Java 17 Example: Normalized Immutable Key

Placed in file `ImmutableKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class ImmutableKeyDemo {
    record ProductKey(String tenant, String sku, int revision) {
        ProductKey {
            Objects.requireNonNull(tenant, "tenant");
            Objects.requireNonNull(sku, "sku");

            tenant = tenant.trim().toLowerCase(Locale.ROOT);
            sku = sku.trim().toUpperCase(Locale.ROOT);

            if (tenant.isEmpty() || sku.isEmpty()) {
                throw new IllegalArgumentException("Empty tenant or sku");
            }
            if (revision < 0) {
                throw new IllegalArgumentException("Negative revision");
            }
        }
    }

    public static void main(String[] args) {
        ProductKey first = new ProductKey(" Store-A ", " ab-10 ", 2);
        ProductKey equivalent = new ProductKey("store-a", "AB-10", 2);
        ProductKey differentVersion = new ProductKey("store-a", "AB-10", 3);

        Map<ProductKey, String> inventory = new HashMap<>();
        inventory.put(first, "Available");

        System.out.println(first.equals(equivalent));
        System.out.println(first.hashCode() == equivalent.hashCode());
        System.out.println(inventory.get(equivalent));
        System.out.println(inventory.get(differentVersion));
        System.out.println(first);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Output:

```text
true
true
Available
null
ProductKey[tenant=store-a, sku=AB-10, revision=2]
```

Explanation:

1. `ProductKey` is a `record` with three immutable components: `String`, `String`, `int`. Java generates `equals()`, `hashCode()`, accessors, and `toString()` from the record components.
2. The *compact constructor* is where data is normalized **before** the record finishes initialization; the normalized `tenant`/`sku` parameters are assigned to their corresponding fields.
3. `Locale.ROOT` normalizes letter case using rules independent of the host machine's locale. This is only an **example policy**: a system with case-sensitive SKUs must not apply this policy.
4. Two keys representing the same normalized triple have `equals() == true` and equal hashes; looking up the map with a new key works.
5. `revision` is part of the key value because this example defines each revision as a distinct key. If the problem domain uses only SKU to determine identity, you must not automatically include `revision` in equality.

**Design rule:** choose the set of components from the **business semantics of the key** first, then ensure every chosen component has safe state. Adding too many mutable fields or presentation data into `equals()`/`hashCode()` can make the key fragile.

## 5. Typical Bug: Mutating a Component of a Key Inside a `HashMap`

The file `MutableKeyDemo.java` demonstrates a bug even without replacing the reference to the key:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MutableKeyDemo {
    public static void main(String[] args) {
        List<String> key = new ArrayList<>(List.of("A"));
        Map<List<String>, String> map = new HashMap<>();

        map.put(key, "found");
        System.out.println(map.get(key));

        key.set(0, "B");
        System.out.println(map.get(key));
        System.out.println(map.containsKey(List.of("A")));
        System.out.println(map.size());
    }
}
```

Run:

```bash
javac -encoding UTF-8 MutableKeyDemo.java
java MutableKeyDemo
```

Output on Java 17:

```text
found
null
false
1
```

Exact explanation:

- `ArrayList.equals()` and `ArrayList.hashCode()` are based on element contents.
- When `["A"]` is inserted into the map, the map uses the list's hash at that moment.
- After `key.set(0, "B")`, the hash of that same list changes; looking up with the new `key` does not find the stored entry. `List.of("A")` is also not equal to the key that has turned into `["B"]`.
- `map.size()` is still `1`: the entry does not vanish on its own; the problem lies in the consistency between the storage slot and the key used for lookup. The buckets described are only to explain the behavior; the lookup results in the example use the concrete keys `"A"` and `"B"`.

**Do not** mutate a mutable key while it is in a map and then rely on `remove(key)` to reliably take the element out: `remove` itself uses the current hash. When a key's value needs to change, delete the entry using **the original still-valid key**, then insert a new entry with a different immutable key; if the map has already been corrupted by key mutation, you need a recovery strategy compatible with the entire structure.

## 6. `record` and `final` Do Not Guarantee Deep Immutability

`record` expresses value objects concisely and auto-generates methods based on components. However, a record only fixes **component references**; it does not automatically freeze child objects.

Problematic example:

```java
record UnsafeGroupKey(String tenant, java.util.List<String> members) {}
```

The code above is just a type definition. If you pass an `ArrayList` into `UnsafeGroupKey`, external callers can still mutate the original list; the `members()` accessor also returns that same list. Since `List.equals()`/`hashCode()` depend on elements, the record's hash changes along with the list.

### The Right Way When Elements Themselves Are Immutable

File `DefensiveRecordDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class DefensiveRecordDemo {
    record GroupKey(String tenant, List<String> members) {
        GroupKey {
            if (tenant == null || tenant.isBlank()) {
                throw new IllegalArgumentException("Missing tenant");
            }
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        GroupKey key = new GroupKey("T1", source);
        Map<GroupKey, String> map = Map.of(key, "team");

        source.add("Chi");

        System.out.println(key.members());
        System.out.println(map.get(new GroupKey("T1", List.of("An", "Bình"))));

        try {
            key.members().add("Dũng");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Unmodifiable");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 DefensiveRecordDemo.java
java DefensiveRecordDemo
```

Output:

```text
[An, Bình]
team
Unmodifiable
```

`List.copyOf` prevents callers from mutating the structure via `source` and affecting the list structure inside the key, and the list returned by `members()` disallows add/remove operations. The elements here are immutable `String` instances so they can be shared safely. If `members` were `List<Member>` where `Member` is mutable, **this code would not be enough**: you would need to convert `Member` to an immutable value object or copy each `Member` according to the contract.

`List.copyOf`, `Set.copyOf`, and `Map.copyOf` create collections that cannot be modified through their APIs, yet they **do not deep-copy** elements/keys/values; these factories also reject `null` elements (with `Map.copyOf`, neither keys nor values may be `null`).

**Be careful with constructors/accessors:**

- Constructor copies, but accessor returns an internal mutable reference → state still leaks.
- Accessor returns a copy, but constructor stores the input reference directly → caller can still mutate from outside.
- Both sides must be protected when child data is mutable, or use **truly immutable child data types**.

## 7. Arrays Are a Special Case Requiring Separate Handling

Java arrays are always mutable. Furthermore, the default `equals()`/`hashCode()` on arrays uses **array identity**, not content comparison. For example, two `new byte[] {1, 2}` instances are two distinct objects; `array1.equals(array2)` is `false`.

If you use a `record BlobKey(byte[] data)`, the generated `equals()`/`hashCode()` methods **do not automatically compare arrays by content**; at the same time, `data()` can allow direct mutation of the array. You must choose one of two approaches:

1. Convert the array data into an immutable value type with appropriate content-based equality.
2. Write a custom class or record with defensive copies on input/output and matching `Arrays.equals()`/`Arrays.hashCode()`; if array elements are references, you must also decide the depth of copying.

### Example of an Immutable Class Holding `byte[]` Content

File `ByteArrayKeyDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public class ByteArrayKeyDemo {
    static final class ByteArrayKey {
        private final byte[] data;

        ByteArrayKey(byte[] data) {
            this.data = data.clone();
        }

        byte[] bytes() {
            return data.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ByteArrayKey that)) return false;
            return Arrays.equals(data, that.data);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(data);
        }
    }

    public static void main(String[] args) {
        byte[] source = {1, 2};
        ByteArrayKey key = new ByteArrayKey(source);
        Map<ByteArrayKey, String> map = new HashMap<>();
        map.put(key, "OK");

        source[0] = 9;
        byte[] exposed = key.bytes();
        exposed[1] = 8;

        System.out.println(Arrays.toString(key.bytes()));
        System.out.println(key.equals(new ByteArrayKey(new byte[] {1, 2})));
        System.out.println(map.get(new ByteArrayKey(new byte[] {1, 2})));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ByteArrayKeyDemo.java
java ByteArrayKeyDemo
```

Output:

```text
[1, 2]
true
OK
```

Two `clone()` calls—in the **constructor** and the **accessor**—protect against mutation from both directions; `Arrays.equals`/`Arrays.hashCode` align on content. For a `byte[]` array, `clone()` suffices to copy the primitive element data. For `MutableItem[]`, `clone()` creates only a **new array**, without cloning each `MutableItem`.

You should also check `null` explicitly if the API allows or forbids `null`. In this example, passing `null` to the constructor triggers a `NullPointerException` at the `clone()` call; in production APIs, use `Objects.requireNonNull(data, "data")` to make the contract explicit.

## 8. Immutable State Can Leak Through Multiple Layers

Consider `List<List<String>>`: calling only `List.copyOf(outer)` makes the outer list unmodifiable, yet the inner lists remain mutable if the original source was mutable. If a key object contains nested lists, you must copy **both the outer container and each inner container** that needs protection.

Illustrative snippet, applicable when the leaf elements are all immutable `String` values:

```java
List<List<String>> snapshot = source.stream()
        .map(List::copyOf)
        .toList();
```

The snippet above uses an existing `source` of type `List<List<String>>` and Java 17+; `Stream.toList()` returns an unmodifiable list. If the structure goes one level deeper to `List<List<Member>>` with a mutable `Member`, the `Member` part is still unresolved. For `Map<Key, Value>`, you must evaluate **both keys and values** if value state is part of the value object; `Map.copyOf` does not make mutable values immutable.

Comparing three commonly confused approaches:

| Approach | Collection structure via resulting reference | Mutable child data |
| --- | --- | --- |
| `new ArrayList<>(original)` | Modifiable; new container | Elements still shared |
| `Collections.unmodifiableList(original)` | Unmodifiable via view; view reflects structural changes from `original` | Elements still shared |
| `List.copyOf(original)` | Unmodifiable via resulting list; structure captured at copy time | Elements still shared |

When the input is already immutable, `List.copyOf` may return the same instance; this is not a bug because the goal is structural stability. When the input experiences concurrent modifications from another thread, the copying process needs a dedicated consistent-snapshot mechanism if the domain requires it.

## 9. Numeric Equality Does Not Always Match `equals()`: `BigDecimal`

`BigDecimal` is **immutable**, yet two numbers with the same numeric value are not necessarily `equals()`. `BigDecimal.equals()` considers both **value and scale**, whereas `compareTo()` compares by numeric value.

File `BigDecimalKeyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalKeyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);
        System.out.println(new HashSet<>(List.of(a, b)).size());
        System.out.println(new TreeSet<>(List.of(a, b)).size());
    }
}
```

Run:

```bash
javac -encoding UTF-8 BigDecimalKeyDemo.java
java BigDecimalKeyDemo
```

Output:

```text
false
true
2
1
```

`HashSet` uses `equals()`/`hashCode()`; `TreeSet` uses sort ordering (here `BigDecimal.compareTo()`). The two collections therefore have different ways of determining duplicate elements.

If the domain considers `1.0` and `1.00` to represent the same value, establish a **canonical form** right when creating the key; for example, calling `stripTrailingZeros()` and normalizing zero according to business needs. If scale carries business meaning (declared precision, units, invoice formatting), you can **intentionally preserve scale** to distinguish them. Do not change `equals()` to follow `compareTo()` while forgetting `hashCode()`; both methods must be compatible.

For money, choosing a numeric type is also tied to **units, currency codes, and rounding rules**. A key consisting of `(amount, currency)` must clearly specify how `amount` is normalized; a `long` counting minor units is only suitable when the domain clearly defines the number of decimal places and range.

### `double`/`float` Require Explicit Comparison Policies

Floating-point types have `NaN`, infinities, and two zero values `+0.0`/`-0.0`. You should not assume ordinary mathematical comparison rules suffice to define a key. `Double.equals()` and wrapper methods have special rules for `NaN` and the sign of zero; primitive `==` itself behaves differently. If you need keys based on continuous measurements, define rounding, precision, and canonical representation **before** choosing components; avoid implementing `equals()` using an `epsilon` tolerance since it can break transitivity.

## 10. Choosing the Right Fields Based on Business Semantics

Immutability is only a technical prerequisite. A key must also contain **the exact fields that define value identity** within its scope of use.

Consider a product with an unchanging `productId`, a `displayName` that can be renamed, and a `price` updated over time:

- If a map wants to look up **the product entity** by a long-lived key, `productId` is usually a good candidate; putting `displayName` or `price` into the key ties the key to volatile attributes.
- If a map wants to look up **a quote at a specific version**, the pair `(productId, priceVersion)` can make sense. `priceVersion` should be a value fixed inside a newly created key, not a mutable field modified in place.
- If the business key is `(tenantId, externalCode)`, both components must have clear rules for case, whitespace, Unicode, and `null`.

Example contract model:

```text
Entity Product:
    id = P-42             // stable identity
    displayName = "..."   // mutable attribute
    price = ...            // mutable attribute

Value Key:
    ProductId("P-42")     // immutable value
    ProductVersion("P-42", 7) // intentionally distinguished version
```

This is an illustrative diagram, not Java code to compile. A **value object** can be a component of an entity, but a value object does not mean an entity. Nor is there a mandatory rule that "every field of an object must participate in `equals()`": for ordinary classes, metadata/derived state fields can be excluded from equality by contract; for records by default, equality is computed over **all** record components.

### Normalize Before Creating the Key

Decide explicitly:

- Does letter case matter? `toLowerCase(Locale.ROOT)` is a locale-independent choice if the business wants case-insensitivity, though not appropriate for every identifier or natural text.
- Should you strip leading/trailing whitespace, normalize Unicode, collapse multiple spaces, or standardize separators? If so, the rule must be consistent between writes and lookups.
- Are `null`, empty strings, and `"unknown"` equivalent representations? Consider rejecting invalid states right in the constructor.
- If a key is a composite of multiple components, does order in a `List` matter? If order does not matter, consider a set type and rules for handling duplicates.
- If the key is used for storage/caching across multiple application versions, are the schema and normalization stable? When changing the key policy, consider migration, cache invalidation, and data compatibility.

**Do not mutate a key in place to "normalize later"**; normalize at creation time and then publish an immutable object.

## 11. Designing an Immutable Class When `record` Does Not Fit

`record` has advantages: concise syntax, `private final` components, accessors without setters, and generated equality over all components. Even so, a record is not always suitable:

- You need comparison based on a **subset** of fields, or there is derived/cached state outside equality.
- You want to hide storage representation, such as a byte array, while still using content-based equality.
- You need to extend another class: a record cannot `extends` an arbitrary class (records extend `java.lang.Record`).
- You need tight control over accessors so mutable references never leak.

An immutable `final class` typically follows these principles:

1. Declare the class `final` (or strictly control subclassing), and close fields with `private final`.
2. Validate and normalize all input data in the constructor/factory before storing.
3. Defensively copy every mutable component that needs private ownership on **input**.
4. Provide no mutator methods; protect **output** via immutable values, copies, or read-only interfaces with clear contracts.
5. Implement `equals()`/`hashCode()` consistently over **the fields that truly define the value**, not relying on references of mutable arrays/collections.
6. If there are derived fields or a cached hash, ensure caching does not alter publicly observable behavior and does not break the equality contract.
7. Check safe publication/initialization, especially when the object will be used across multiple threads; `final` supports the Java memory model, but does not fix leaking `this` during construction or storing unprotected mutable references.

If you want to use `Lombok @Value`, `@EqualsAndHashCode`, or auto-generated code, you must still verify the exact equality components and deep immutability; annotations do not automatically deep-copy mutable internal objects.

## 12. Do Not Confuse Immutable, Unmodifiable, and Thread-Safe

- **Immutable object:** the observable state of the object itself cannot change after initialization. A `String` is a common example.
- **Unmodifiable view:** an API view that disallows modification, while the underlying source data can still change. `Collections.unmodifiableList(mutableList)` is an example.
- **Unmodifiable snapshot container:** the resulting structure cannot be modified and does not reflect structural mutations to the source after copying, such as `List.copyOf(source)`; mutable child contents can still change.
- **Thread-safe mutable object:** can change state under concurrency according to its contract, such as `AtomicInteger`. It does not become immutable.

Therefore, a structure like the following is not a truly immutable key:

```java
record CounterKey(String label, java.util.concurrent.atomic.AtomicInteger value) {}
```

`AtomicInteger` is mutable. The record holds a fixed `value` reference, yet the integer inside can still change, and the record's default equality for `AtomicInteger` uses that object's own equality rather than automatically expressing equality by the held numeric value. If the key must capture the number at construction time, read `int snapshot = value.get()` and store an `int` or an immutable wrapper in the key.

**Snapshot consistency:** reading individual fields of an object being updated by multiple threads can produce a key with fields coming from two different points in time. Defensive copying and `final` do not automatically guarantee a consistent multi-field snapshot; you need a locking protocol, a safely published immutable snapshot, or a versioning mechanism when needed.

## 13. Testing Value Object and Map Key Contracts

Write tests based on **observable behavior**, not merely checking for `final` or `record`.

| Test Scenario | Expected Correct Behavior |
| --- | --- |
| Two differently written inputs that normalize to the same key | `equals() == true` and equal hashes |
| Two keys with different identity data | `equals() == false` per defined rules |
| Lookup using a different instance with equal value | `map.get(equivalentKey)` finds the right entry |
| Mutating input array/list after key creation | Key value, hash, and lookup result remain unchanged |
| Calling accessor and attempting to mutate returned data | Cannot mutate internal state of the key |
| Deeply nested components, mutable elements | No unintended path to mutate key state |
| `null`, empty, invalid data | Rejected or handled according to documented policy |
| `BigDecimal` with different scale, special floating-point numbers | Equality/key behavior matches business convention |
| Long-lived cache/map writes | Keys remain stable across frequent operations and do not depend on presentation fields |

One particularly valuable test is:

1. Create a key from a **mutable source**.
2. Insert the key into a `HashMap`.
3. Mutate the mutable source and try mutating data via the accessor.
4. Create a new key equivalent to **the original value**.
5. Verify that `get(newEquivalentKey)` still finds the entry, and the old key's `equals()/hashCode()` remain unchanged.

This test routinely catches forgotten defensive copies in constructors or accessors. For records containing arrays, you must also test content-based equality instead of array identity.

## 14. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix It |
| --- | --- | --- |
| "Field is `final List<T>`, so the value object is immutable" | Only the reference is final; the list/elements remain mutable | Protect both container and elements |
| "Records automatically deep-copy every component" | Records do not copy mutable references | Use compact constructors and copy appropriately |
| "`List.copyOf` always deep-copies" | Referenced elements are still shared | Use immutable value elements or copy each element |
| "Arrays in a record are automatically compared element-wise" | Arrays compare by identity by default | `Arrays.equals/hashCode` plus defensive copies |
| "`BigDecimal("1.0")` and `BigDecimal("1.00")` are the same key" | `equals()` considers scale | Canonicalize if the business wants them equal |
| "Equal hashes mean `equals()` is true" | Collisions are valid | Confirm with `equals()` |
| "Keys only need stable hashes; changing equality is fine" | `equals()` is part of the lookup contract | Stabilize all state participating in equality |
| "Using selling price/display name to identify products" | Attributes change easily, not necessarily identity | Use an immutable identifier suited to the data domain |
| "Immutable means thread-safe in every situation" | Taking a snapshot from a mutable source can be inconsistent | Ensure proper snapshot and publication |
| "Just copying an object yields an independent key" | Might only be a shallow copy | Inspect every reference and ownership boundary |

## 15. Process for Selecting Components for a New Key

**Step 1 — Define the business equality relation.** Write the sentence: "Two keys are equal if and only if ...". Example: "Same tenant, same SKU under case-insensitive rules, same revision number."

**Step 2 — Choose immutable representations.** Prefer primitives, `String`, `UUID`, `java.time`, and genuinely immutable nested value objects. For arrays/collections, determine exact ownership and copying depth.

**Step 3 — Normalize and validate at the boundary.** Lock down locale, nullability, Unicode, scale, units of measure, and versioning. Reject invalid states at object creation.

**Step 4 — Create an immutable API.** You can use a record for purely immutable component sets, or a `final class` when you need deep control, special comparison, protective getters, or encapsulation.

**Step 5 — Ensure `equals/hashCode` share the same semantics.** For tree collections, you also need a comparator consistent with the intended key-duplication definition.

**Step 6 — Test against mutation and for equivalent lookup.** Mutate input data or any extractable references; verify the key and map are unaffected.

**Step 7 — Document the contract.** Record which fields participate in identity, how normalization works, which aliases are allowed, and the impact when the key schema changes.

## 16. Self-Check Questions

1. A `record OrderKey(String id, List<OrderLine> lines)` uses `List.copyOf(lines)`, but `OrderLine` has setters. Is it truly an immutable key? Why?
2. If you use a `byte[]` to store a SHA-256 digest, why shouldn't you just create `record Digest(byte[] bytes)` and let Java generate `equals/hashCode`?
3. Why does `Collections.unmodifiableList(original)` behave differently from `List.copyOf(original)` when `original` continues to be modified?
4. A system treats prices `1.0` and `1.00` as equivalent. What policy must be decided before putting `BigDecimal` into a key?
5. When should you use `ProductId(id)`, when do you need `ProductVersion(id, version)`, and why shouldn't a constantly changing product name be placed into a long-lived key?
6. Why does `final AtomicInteger counter` fail to prove that an object's state is immutable?

**Remember:** good components for value objects and keys must have **correct equality semantics**, **stable state**, and **no mutation leaks via internal references**. `record`, `final`, and unmodifiable collections are supporting tools; the deep immutability contract and `equals()/hashCode()` still must be explicitly designed and tested.