# The equals–hashCode Contract and How to Write Key Types

## 1. The problem: two objects can represent the same key

An application may create two distinct key objects to refer to the same account:

```java
AccountKey first = new AccountKey("tenant-a", "u-7");
AccountKey second = new AccountKey("tenant-a", "u-7");
```

The two variables do not necessarily point to the same object. However, if the business rule is "an account is identified by the pair of tenantId and userId," they need to be treated as the same key.

This directly affects:

- Looking up an entry using a new key object with the same data.
- Putting an equivalent key into a `HashMap` to update its value.
- Deduplicating elements in a `HashSet`.
- Removing an entry or checking for existence using an equivalent object.

For hash-table-based data structures to work properly, a key type needs a clear equality relationship and a hash code consistent with that relationship.

This article uses Java 17. The goal is to understand the contract, write a proper immutable key, and recognize mistakes that often surface only when an object is used inside a collection.

## 2. Three different questions: ==, equals, and hashCode

| Mechanism | Question |
| --- | --- |
| `a == b` for references | Do the two references point to the exact same object? |
| `a.equals(b)` | Are the two objects equal according to the type's contract? |
| `a.hashCode()` | What is the hash code used to assist bucketing/lookup in hash structures? |

By default, `Object.equals` uses object identity. Value types can override it to define data-based equality.

`hashCode` returns an `int`. It is not a unique ID, not a cryptographic signature, and has no guarantee of being a memory address. Do not store `hashCode` as a persistent business identifier.

`equals` is what defines equality; having two equal hash codes is not enough to conclude that two objects are equal.

The official contracts are defined in [Object.equals and Object.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

## 3. The equals contract to maintain

For non-`null` references, the equality relation must satisfy the following properties:

| Property | Condition |
| --- | --- |
| Reflexive | `x.equals(x)` is `true` |
| Symmetric | `x.equals(y)` and `y.equals(x)` return the same result |
| Transitive | If `x` equals `y` and `y` equals `z`, then `x` equals `z` |
| Consistent | The result does not change as long as the information used in the comparison does not change |
| Non-nullity (with `null`) | `x.equals(null)` is `false` |

This is not merely a stylistic convention. If symmetry is violated, the outcome may depend on which side initiates the comparison. If transitivity is violated, an equivalence class of "same key" objects can no longer be defined consistently.

The method must have the exact signature:

```java
@Override
public boolean equals(Object object)
```

Writing `equals(AccountKey other)` only creates an overload if `equals(Object)` is not also overridden. Collections rely on the `Object.equals` contract, so that overload alone does not solve the key problem. Use `@Override` so the compiler helps catch signature mistakes.

## 4. The hashCode contract and the right direction of implication

The core rules:

1. As long as information used in `equals` does not change during a single execution, the hash must remain consistent.
2. Two equal objects must produce the same hash.
3. Two unequal objects are allowed to produce the same hash.

The hash is not required to stay identical across separate runs of a program. Do not use a rule like "unequal objects must have different hashes" as a correctness test.

You can remember it as:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()
    is not enough to conclude a.equals(b) == true
```

A function that always returns `1` can still satisfy the requirement that equal objects have the same hash. However, it forces many keys into the same candidate bucket, degrading distribution and potentially causing poor performance.

Conversely, a function that produces well-distributed hashes using information inconsistent with `equals` can still violate the contract.

### Use consistent information

If `equals` checks only `tenantId` and `userId`, `hashCode` should not include an independently changing display name in its calculation. Two objects that are equal by their identifier pair could differ in display name, leading to different hashes.

The standard, easily verifiable design is to use the exact same equality-defining components in both methods. A hash does not have to "use every single field in the class"; what must be guaranteed is consistency with the equality relation, combined with reasonable distribution.

## 5. How do HashMap and HashSet use the contract?

At a conceptual level, a hash structure uses the hash to narrow down a candidate group, and then distinguishes keys using the equality relation. This should not be treated as a promise about the exact number of times `equals` or `hashCode` will be called.

### 5.1. Equal keys in a map

If `first` and `second` are equal keys with valid hashes:

```java
// Illustrative snippet using AccountKey defined in the full program section.
Map<AccountKey, String> map = new HashMap<>();
map.put(first, "old");

System.out.println(map.get(second));        // old
System.out.println(map.put(second, "new")); // old
System.out.println(map.size());             // 1
```

The second `put` updates the value of the mapping with the equivalent key rather than creating another separate entry according to the key relation.

### 5.2. Equal elements in a set

```java
// Illustrative snippet with two equal AccountKey instances; requires import java.util.*.
Set<AccountKey> keys = new HashSet<>();
System.out.println(keys.add(first));  // true
System.out.println(keys.add(second)); // false
```

A set deduplicates according to the element contract. If an element has a broken `equals/hashCode` implementation, deduplication and lookup results may fail to match business intent.

See [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), and [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 5.3. Hash collisions do not merge two keys into one

Two unequal keys may share the same hash. The data structure must still distinguish them using the equality contract.

Therefore, never implement:

```java
// Illustrates an incorrect implementation; do not use.
return this.hashCode() == other.hashCode();
```

as the complete definition of `equals`.

Likewise, do not put hash values into business logic conditions such as "the hash codes match, so this must be the same user." A hash exists solely to assist lookup structures.

## 6. Choose the right key-defining data before writing code

For a multi-tenant account key, `userId` might only be unique within each tenant. Omitting `tenantId` from `equals` would merge two accounts belonging to different tenants.

You need to determine:

- The uniqueness scope of each component.
- Case sensitivity.
- Whitespace and normalization policies.
- Whether `null` or empty values are allowed.
- Whether the identifier remains stable throughout the time the key is stored.

This article's example chooses a simple policy: both strings must be non-`null`, compared verbatim, case-sensitive, with no automatic whitespace trimming.

Do not call `toLowerCase` or `trim` on one side inside `equals` while hashing the raw unnormalized value. If business rules require normalization, define a consistent rule, perform it at key construction time, and use the normalized representation in both methods.

Structured values should be kept as separate components. Concatenating two fields into a single string without an unambiguous delimiter rule can blur data boundaries.

## 7. Writing an immutable key class

A straightforward, verifiable pattern:

```java
// Class declaration snippet; requires import java.util.Objects.
static final class AccountKey {
    private final String tenantId;
    private final String userId;

    AccountKey(String tenantId, String userId) {
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
        this.userId = Objects.requireNonNull(userId, "userId");
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) {
            return true;
        }
        if (!(object instanceof AccountKey other)) {
            return false;
        }
        return tenantId.equals(other.tenantId)
                && userId.equals(other.userId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, userId);
    }
}
```

Each decision serves a purpose:

- `final class` prevents subclasses from extending the comparison domain outside the intended design.
- Two `final` fields of immutable type `String` keep the key information stable.
- The constructor enforces that both components are non-`null`.
- `this == object` is a fast path for identical references.
- `instanceof` returns `false` when the argument is `null` or of a different type.
- Both fields are compared using `String.equals` rather than `==`.
- The hash is computed from the exact same components that define equality.

`Objects.hash` is a convenience utility for hashing multiple components; it is neither a cryptographic algorithm nor a collision-free guarantee. `Objects.equals` is also useful when a field is allowed to be `null`, though our sample key policy rejects `null` in the constructor. [Objects API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)

You can use IDE code generation tools, but you must still select the right fields and understand the generated contract. Syntactically valid generated code does not automatically pick the right business identity.

## 8. Inheritance and the equality domain

When a key class can be subclassed, hard questions arise: can an instance of a superclass be considered equal to an instance of a subclass, and do new fields in the subclass participate in equality?

For example, suppose a superclass has only coordinates, while a subclass adds color. If the superclass accepts any object with the same coordinates while the subclass also requires matching color, you can end up with:

```text
parent.equals(child) = true
child.equals(parent) = false
```

This violates symmetry. Attempts to "flexibly ignore color when comparing against a parent" can instead break transitivity.

There is no mechanical swap between `instanceof` and `getClass` that solves every inheritance model. First, you must decide the domain of objects that can be considered equal.

For new value key types, the most manageable choices are usually:

- Use a `final` class.
- Use a record with appropriate components.
- Use object composition instead of extending an equality relation that was not designed for hierarchy.

If you must design a class hierarchy with cross-class equality, verify symmetry, transitivity, and hash consistency across the entire domain. Our sample code uses a final class to keep the contract clear.

## 9. Mutating a key after insertion: why can lookup fail?

Suppose a key uses an `id` field in both `equals` and `hashCode`. After inserting the key into a map, code mutates `id` from `1` to `2`.

The information used to locate the key has changed, while the hash structure was never notified to reorganize the corresponding mapping.

You may observe a situation where:

```text
map.size() is still 1
the iterator still sees the key object
map.get(that exact same key object) fails to find it
```

This is not a bug where "the map forgot to hold the reference." The object is still there; the key lookup mechanism is simply no longer compatible with the state used when the entry was stored.

The `Map` contract explicitly states that behavior is not specified if the value of an object is changed in a manner that affects `equals` comparisons while the object is a key in the map. `Set` has a similar restriction for elements affecting equality. The lookup result shown in the full program is an observed demonstration with a running `HashMap`, not a guaranteed behavior to rely on as an application rule. [Map contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### The right way to handle it

Prefer immutable keys. When an identifier needs to change, create a new key object and update the mapping in a controlled manner.

If you must manage a mutable key, remove the mapping using its old state before mutating the key, and then re-insert it with the new state within a flow that prevents uncontrolled concurrent access. Once a key has already been mutated in place, do not assume `remove(key)` will reliably find it to recover.

Changing a field that does not participate in `equals/hashCode` does not necessarily alter key identity, though other constraints must still be considered. Having a setter is not automatically a bug; the core bug is mutating data that determines location/equality while the object is actively stored under a contract that requires stability.

## 10. Records: concise, but you must choose the right components

This is an alternative to the `AccountKey` class above; do not declare both with the same name in the same scope. The full program uses the name `RecordKey` to place both approaches side by side.

```java
// Record declaration snippet; requires import java.util.Objects.
record AccountKey(String tenantId, String userId) {
    AccountKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(userId, "userId");
    }
}
```

A record automatically provides `equals/hashCode` based on all of its components and checks for the exact same record class. It is well suited for value keys when its components accurately express identity and hold stable state.

Important points to keep in mind:

- Adding a component such as a display name automatically includes it in the default equality and hash relation.
- Components are `final` references, but the objects they refer to may still be mutable.
- A record holding a mutable collection can have a hash code that changes when the collection's contents change.
- A record holding an array does not automatically perform deep content equality on the array elements.
- Never depend on a specific numeric hash value or an observed component-combining formula.

If you want a record containing a list of strings to serve as a key, you can make a defensive copy with `List.copyOf` in the compact constructor, accepting its policy of rejecting `null` elements and keeping in mind that it is a shallow copy. If the elements themselves are mutable, a deeper design is required.

See [Record API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html), [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html), and [JLS 8.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).

## 11. Keys containing arrays need content equality and defensive copying

Arrays use `Object` reference equality if you only call `array.equals`. Two separate byte arrays with identical contents are not automatically equal.

To define a key based on byte contents:

- Use `Arrays.equals` for equality.
- Use the corresponding `Arrays.hashCode` for hashing.
- Clone/copy the input array on construction.
- Never return the internal array directly for callers to mutate.

```java
// Class declaration snippet; requires import java.util.Arrays and java.util.Objects.
static final class BytesKey {
    private final byte[] bytes;

    BytesKey(byte[] bytes) {
        this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object object) {
        return object instanceof BytesKey other
                && Arrays.equals(bytes, other.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }
}
```

Declaring `private final byte[]` alone is not enough: `final` locks the array reference, not its elements.

Also, do not replace `Arrays.hashCode(bytes)` with `Objects.hash(bytes)` assuming it performs equivalent byte-content hashing. When a primitive array is passed as a single object to varargs, it is not hashed element-by-element the way a content-based key requires.

For nested arrays or object arrays, choose `equals/deepEquals` and `hashCode/deepHashCode` according to the exact level of content that defines identity. Never mix deep equality comparison with reference-based hashing. [Arrays API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

## 12. Equality, ordering, and special values

`HashMap/HashSet` rely on the hash/equality contract. `TreeMap/TreeSet` locate entries using `compareTo` or a `Comparator`. To satisfy the general map/set contract, ordering must be consistent with `equals`.

For example, `BigDecimal("1.0")` and `BigDecimal("1.00")` return `0` from `compareTo`, but `equals` returns `false` because their scales differ. When choosing key types and collection structures, remember that "numerical equality" and "type equality" can differ.

Do not try to tweak `hashCode` to fix an inconsistent comparator. Design the equality relation and ordering around the same intent, or deliberately choose a model while understanding its contract boundaries.

References: [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

When a key contains floating-point numbers, establish clear semantics for `NaN` and signed zeros; use the consistent comparison/hashing logic provided by wrapper types or appropriate code generators. Never add an "approximately equal within epsilon" rule to `equals` without considering that it breaks transitivity.

For identifiers assigned after object creation—such as a temporary entity whose ID is not yet populated—determine when the object acquires a stable identity. Do not assume that every object with a `null` ID represents the same key.

## 13. Complete program

Save as `EqualityKeyDemo.java`.

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class EqualityKeyDemo {
    static final class AccountKey {
        private final String tenantId;
        private final String userId;

        AccountKey(String tenantId, String userId) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            this.userId = Objects.requireNonNull(userId, "userId");
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof AccountKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && userId.equals(other.userId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, userId);
        }
    }

    record RecordKey(String tenantId, String userId) {
        RecordKey {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(userId, "userId");
        }
    }

    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void setId(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof MutableKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    static final class CollisionKey {
        private final int id;

        CollisionKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof CollisionKey other && id == other.id;
        }

        @Override
        public int hashCode() {
            return 1;
        }
    }

    static final class BytesKey {
        private final byte[] bytes;

        BytesKey(byte[] bytes) {
            this.bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object object) {
            return object instanceof BytesKey other
                    && Arrays.equals(bytes, other.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    public static void main(String[] args) {
        AccountKey first = new AccountKey("tenant-a", "u-7");
        AccountKey equal = new AccountKey("tenant-a", "u-7");
        AccountKey otherTenant = new AccountKey("tenant-b", "u-7");

        System.out.println("Same reference: " + (first == equal));
        System.out.println("Equal content: " + first.equals(equal));
        System.out.println("Equal hash: "
                + (first.hashCode() == equal.hashCode()));
        System.out.println("Different tenant equal: "
                + first.equals(otherTenant));

        Map<AccountKey, String> users = new HashMap<>();
        users.put(first, "old");
        System.out.println("Lookup with equal key: " + users.get(equal));
        System.out.println("Previous value: " + users.put(equal, "new"));
        System.out.println("Map size: " + users.size());

        Set<AccountKey> keys = new HashSet<>();
        System.out.println("First set add: " + keys.add(first));
        System.out.println("Equal set add: " + keys.add(equal));

        RecordKey recordA = new RecordKey("tenant-a", "u-7");
        RecordKey recordB = new RecordKey("tenant-a", "u-7");
        System.out.println("Record equality: " + recordA.equals(recordB));

        Map<CollisionKey, String> collisions = new HashMap<>();
        collisions.put(new CollisionKey(1), "one");
        collisions.put(new CollisionKey(2), "two");
        System.out.println("Collision map size: " + collisions.size());
        System.out.println("Collision lookup: "
                + collisions.get(new CollisionKey(2)));

        MutableKey mutable = new MutableKey(1);
        Map<MutableKey, String> unsafe = new HashMap<>();
        unsafe.put(mutable, "value");
        mutable.setId(2);
        System.out.println("Mutated key same reference present: "
                + (unsafe.keySet().iterator().next() == mutable));
        System.out.println("Mutated key lookup: " + unsafe.get(mutable));
        System.out.println("Mutated map size: " + unsafe.size());

        byte[] input = {1, 2};
        BytesKey bytesKey = new BytesKey(input);
        input[0] = 9;
        byte[] returned = bytesKey.bytes();
        returned[1] = 9;
        System.out.println("Defensive bytes equality: "
                + bytesKey.equals(new BytesKey(new byte[] {1, 2})));

        record ArrayRecord(byte[] bytes) {}
        System.out.println("Array record equality: "
                + new ArrayRecord(new byte[] {1, 2})
                        .equals(new ArrayRecord(new byte[] {1, 2})));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked EqualityKeyDemo.java
java EqualityKeyDemo
```

The code has been verified against the Java 17 API baseline on a newer JDK with no unchecked warnings.

Observed stdout:

```text
Same reference: false
Equal content: true
Equal hash: true
Different tenant equal: false
Lookup with equal key: old
Previous value: old
Map size: 1
First set add: true
Equal set add: false
Record equality: true
Collision map size: 2
Collision lookup: two
Mutated key same reference present: true
Mutated key lookup: null
Mutated map size: 1
Defensive bytes equality: true
Array record equality: false
```

### Explanation of results

- The two `AccountKey` instances are distinct objects so `==` returns `false`, but they share the same identifier pair so `equals` is `true` and their hashes are equal.
- A different tenant makes the keys unequal even with the same user ID.
- Looking up with an equivalent key returns the original mapping; `put` updates the value so the map size remains `1`.
- The set rejects adding an equal element a second time.
- The record with two string components provides the expected value-based equality relation.
- `CollisionKey` always returns the same hash, but `equals` still distinguishes IDs, so the map retains both mappings.
- `MutableKey` is mutated after insertion: the program observes that the key reference is still inside the map, yet `get` fails to find it. This situation steps outside guaranteed usage conditions; do not rely on getting this exact result in other programs.
- `BytesKey` retains the content `1, 2` even after both the input array and the returned array are modified, thanks to defensive copying.
- Two records holding two separate byte arrays with identical contents are still not equal under the default record implementation.

The example intentionally includes `MutableKey` and `CollisionKey` solely to demonstrate risks and contract boundaries, not to recommend them as production keys.

## 14. Checklist for verifying a key type before use

Using at least three distinct objects with identical data plus objects differing in each component, verify:

1. Reflexivity, symmetry, and transitivity.
2. Comparison against `null` and against an unrelated type.
3. Consistent results when relevant state does not change.
4. Two equal objects produce equal hashes.
5. Differing in any identity component makes `equals` return `false` when business rules require it.
6. Looking up and removing entries using a newly constructed equivalent key in `HashMap`.
7. Proper deduplication in `HashSet`.
8. Constructors and getters do not expose mutable state that determines the hash.
9. Edge cases such as empty strings, Unicode, `null` (if permitted), arrays, and nested components.
10. Consistency with any comparator if the type is used in ordered data structures.

Do not require two unequal objects to have different hashes in correctness tests. You can evaluate hash distribution and performance separately on representative datasets, but do not turn a performance preference into a non-existent contract requirement.

Do not write tests asserting a specific hardcoded hash number for a record. Test the relationships your application actually needs: equality, stability, and proper collection access.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Overriding `equals` while keeping the default `hashCode` | Equal objects may not be found as the same key | Implement both using the same identity components |
| Writing `equals(MyKey)` instead of `equals(Object)` | Only overloads the method; collections do not use the intended contract | Use the exact `Object` signature and `@Override` |
| Comparing strings with `==` | Depends on string instance sharing/interning | Use `String.equals` or `Objects.equals` |
| Using equal hash codes as the definition of `equals` | Distinct keys get merged on hash collisions | Compare the actual identity fields |
| Computing hash from fields not checked by `equals` | Can violate the rule that equal objects must have the same hash | Use consistent information across both methods |
| Using mutable fields as key identity | Hash/equality changes while stored in a collection | Separate stable key identity from mutable data |
| Relying only on `final` for arrays/collections | Underlying elements can still be mutated | Make defensive copies and control element mutability |
| Allowing subclasses to extend equality arbitrarily | Easily breaks symmetry or transitivity | Design the comparison domain; prefer `final` classes or composition |
| Treating records as deeply immutable | Components can still hold mutable objects or arrays | Inspect component types and copy appropriately |
| Mutating a key in place and calling `remove` to recover | Lookup may fail under the mutated state | Keep keys stable; update mappings in a controlled flow |
| Persisting `hashCode` as a business ID | Collisions and lack of cross-run stability guarantees | Use an identifier specifically designed for persistence |

## 16. Self-check and practice

### Questions

1. Can two keys with identical data have `==` evaluate to `false` while `equals` evaluates to `true`?
2. If `a.equals(b)` is `true`, what condition must their hashes satisfy?
3. Are two equal hashes sufficient to conclude that two keys are equal?
4. Why is omitting the tenant from a multi-tenant key a design bug even if the code compiles cleanly?
5. How does `equals(AccountKey)` differ from `equals(Object)`?
6. Why shouldn't `hashCode` use a mutable field that lies outside the `equals` identity?
7. Does `private final byte[]` automatically create an immutable key?
8. Does a record containing an array automatically compare array contents?
9. Why can a map still contain a key object while lookup fails after the key is mutated?
10. What relationship does `TreeMap` use to locate keys, and what consistency is required?

### Exercises

- Write a `ProductKey` consisting of `shopId` and `sku`, with an explicit `null` policy.
- Create three separate objects with the same data and verify all properties of `equals`.
- Use one instance to `put` an entry and a separate equivalent instance to `get` and `remove` it.
- Insert equivalent keys into a `HashSet` and verify the element count.
- Create a record version of the key, comparing the amount of boilerplate code and the assumptions made about its components.
- Add a display name field to your data model but keep it out of the key; explain why the identifier remains stable.
- Write a key backed by a byte array and verify that mutating the input array or the getter return value does not alter the internal hash.
- Intentionally create a hash collision in a learning environment and prove that two distinct keys still coexist in a map.
- Compare using `BigDecimal` as a key in a hash structure versus an ordered structure, noting the observed equality behavior.

### Reference answers

1. Yes; value equality is distinct from reference identity.
2. Both hashes must be equal.
3. No; hash collisions are permitted.
4. The equality relation erroneously merges distinct business identities.
5. The first signature only overloads the method if a proper override is absent; the second signature implements the `Object` contract used by collections.
6. Two equal objects could differ in that extra field and produce different hashes.
7. No; only the array reference is `final`, whereas its elements can still be modified.
8. No; you must explicitly define content-based equality and hashing if that is the intended identity.
9. The state used for locating the key changed while the hash structure was not reorganized; the `Map` contract guarantees no longer hold.
10. It uses `compareTo` or a `Comparator`; ordering should be consistent with `equals` to satisfy the general `Map` contract.
