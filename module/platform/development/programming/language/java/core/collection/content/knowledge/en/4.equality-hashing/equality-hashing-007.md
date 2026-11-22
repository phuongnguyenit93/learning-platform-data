# Records and Immutable Objects as Keys or Set Elements

A `HashMap` key or `HashSet` element does not just need correct `equals` and `hashCode` methods at creation time. The state that those two methods rely on must remain stable while the object is being used for lookup or deduplication.

Records and immutable value types help satisfy that requirement. However, a record only protects its component fields at the reference level; it does not automatically make every internal object immutable.

This article explains how to choose key components, use records, protect reference data, and handle arrays. The examples use Java 17 or later.

## 1. Why Must Keys and Set Elements Be Stable?

A hash-based structure organizes data based on the hash code of each key or element. During queries, it must locate entries using both the hash code and the corresponding equality relationship.

You can picture it like this:

```text
Insert object using its current key value
        ↓
Store in the hash structure
        ↓
Look up using the same value relationship
```

If data participating in equality or hashing is modified midway, the relationship between the current value and how the object was stored can be broken. The object remains inside the structure, but finding or removing it by its new value is no longer guaranteed to work as expected.

The `Map` and `Set` contracts warn against mutating data in ways that affect equality while an object is in use as a key or member. Programs should never rely on accidental behavior after such mutations. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Immutable objects make reasoning simple: once validly constructed, the value used as a key cannot change out of control.

### Full Immutability vs. Key-Portion Stability

An object may have several mutable fields while using only an immutable identifier in `equals`/`hashCode`. In that case, unrelated mutations do not necessarily corrupt the key.

Even so, separating an **immutable value key type** from a mutable profile is usually clearer:

```text
CustomerKey → only customer-identifying information
CustomerProfile → name, contact info, status, and mutable data
Map<CustomerKey, CustomerProfile> → look up profiles using a stable key
```

There is no need to include every piece of profile data in the key just because it is present on the object.

## 2. What Does a Record Provide?

Consider this declaration:

```java
record CustomerKey(String tenantId, String customerId) {}
```

A record is a class that carries a fixed set of value components. When you do not declare custom replacements, Java provides:

- A `private final` field corresponding to each component.
- A canonical constructor to initialize the components.
- Accessors such as `tenantId()` and `customerId()`.
- `equals`, `hashCode`, and `toString` implementations based on the components.

A record class cannot be subclassed to add extra object state across a class hierarchy. This helps avoid common pitfalls when trying to extend equality semantics between supertypes and subtypes.

Two instances of the same record class whose corresponding components are equal are considered equal by the default generated implementation. For the `String` components in this example, equality is based on string content.

```java
CustomerKey first = new CustomerKey("T1", "C7");
CustomerKey second = new CustomerKey("T1", "C7");

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

You do not need to retain the exact same object reference to look up a value key. A freshly created key with identical components can locate the stored mapping or set member. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

### Records Do Not Promise a Fixed Persistent Hash Value

What you should rely on is consistency with equality, not a specific numerical combination formula produced by the compiler. Do not use `record.hashCode()` as a unique identifier, database key, wire checksum, or value expected to stay identical across all runtimes.

Similarly, `toString()` is convenient for human debugging, but it is not a serialization format meant for programs to parse back into components.

## 3. Design Key Components Before Choosing Syntax

A record makes code shorter; it does not automatically choose the right meaning of identity.

Suppose a customer ID is unique only within each tenant organization:

```java
record CustomerKey(String tenantId, String customerId) {}
```

The two keys:

```text
(T1, C7)
(T2, C7)
```

must be distinct. If only `customerId` were used, data from two tenants could be merged during deduplication or overwritten in a map.

Conversely, suppose you declare a profile record that includes a display name:

```java
record CustomerProfile(CustomerKey key, String displayName) {}
```

Under default equality, two profiles with the same key but different names are not equal. That may be reasonable semantics for a profile snapshot, but it is not the desired semantics for a customer key.

### Questions to Answer

| Question | Design Impact |
| --- | --- |
| Within what scope is the ID unique? | May require adding tenant, environment, or resource type |
| Which fields can change? | Avoid using them as key identity if changes do not create a new identity |
| Do two versions of a profile share the same key? | Separate the key from versioned data |
| Do case sensitivity or whitespace matter? | Requires a clear normalization policy |
| Is there an "unassigned ID" state? | Avoid accidentally collapsing multiple unassigned objects into the same key |
| Does collection component order matter? | Choose `List` or `Set` according to the intended value relationship |

Do not automatically normalize letter case, strip accents, or trim whitespace merely for convenience. Every normalization step alters the boundary of which values are treated as the same key.

## 4. Validating Data with a Compact Constructor

A record can still validate input invariants:

```java
record CustomerKey(String tenantId, String customerId) {
    CustomerKey {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(customerId);

        if (tenantId.isBlank() || customerId.isBlank()) {
            throw new IllegalArgumentException("ids must not be blank");
        }
    }
}
```

This example requires importing `java.util.Objects`. This is a compact constructor for a record with appropriate visibility inside an enclosing demonstration class.

Purposes:

1. Prevent constructing a key with missing required components.
2. Catch invalid data right at the value construction boundary.
3. Enforce the same invariant across every place the key is used in maps or sets.

In a compact constructor, you can adjust parameter values before they are assigned to the component fields. This is useful for defensive copying or applying a business-defined normalization rule.

A record does not automatically reject `null` in reference components. If `null` is invalid, you must check for it explicitly. Default equality can handle `null` reference components without crashing, but "comparable without throwing" is not the same as "valid in the domain model". [Java Language Specification 17: Records and Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10)

## 5. Records Are Only Shallowly Immutable

Consider a record holding a list:

```java
record UnsafeTagKey(List<String> tags) {}
```

The `tags` field is held via a `final` reference, but the referenced list object itself remains mutable:

```java
List<String> source = new ArrayList<>(List.of("red"));
UnsafeTagKey key = new UnsafeTagKey(source);

source.add("blue");
System.out.println(key.tags()); // [red, blue]
```

No reassignment of the record field occurred. The underlying list object itself mutated.

Because `List.equals` and `List.hashCode` depend on element contents, the equality and hash code of a record containing this component can also change. Putting such a record into a `HashSet` or using it as a map key and then mutating the list is hazardous.

There are two ways mutations can leak in:

- The caller retains a reference to the list passed into the constructor.
- The default accessor returns the same list reference, allowing mutation through `key.tags()`.

Therefore, you cannot assume a key is safe merely by seeing the `record` keyword.

## 6. Defensive Copying with List<String>

If tag order is part of the key's value, you can design it like this:

```java
record OrderedTagKey(List<String> tags) {
    OrderedTagKey {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf` returns an unmodifiable list that does not reflect subsequent additions or removals in the source collection. By contract, it also rejects a `null` source or `null` elements.

Because `String` is immutable, this combination protects both the list structure and the string values used by the key:

```java
List<String> source = new ArrayList<>(List.of("red"));
OrderedTagKey key = new OrderedTagKey(source);

source.add("blue");
System.out.println(key.tags()); // [red]
```

Calling `key.tags().add("green")` will be rejected. The accessor can safely return the stored unmodifiable list without opening an external path for structural mutation. [Java 17: List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

### 6.1. Why Is unmodifiableList(source) Alone Not Enough?

An unmodifiable view such as `Collections.unmodifiableList(source)` remains backed by the source list. If the caller retains `source` and mutates it, the view reflects those changes.

To get a stable structural snapshot, you need a copying mechanism or a method guaranteed not to reflect source mutations, such as `List.copyOf`, rather than merely blocking mutation through one reference.

### 6.2. copyOf Is Still a Shallow Copy

If the component is `List<MutableItem>`, preventing additions or removals on the list does not stop an internal `MutableItem` from mutating its own fields.

If the element's equality or hash code depends on that mutable state, the key can still become unstable. Suitable approaches include:

- Converting each element to an immutable value type.
- Deep-copying the portions actually needed for the key.
- Retaining only immutable identifiers of the elements.
- Redesigning the key so it does not hold a mutable object graph.

Do not treat "copy" as synonymous with "all internal data is now independent".

### 6.3. Choosing List vs. Set Is Part of Key Semantics

`List.of("red", "blue")` is not equal to `List.of("blue", "red")` under list equality. If tag order is meaningless, choosing an immutable set component—such as a `Set<String>` created via `Set.copyOf`—may be more accurate.

However, a `Set` discards duplicate counts; if multiplicity matters, a set is not appropriate. Do not switch collection types just to make data "look immutable" while ignoring equality semantics.

## 7. Arrays in Records Present Two Distinct Problems

Consider:

```java
record ArrayComponentKey(int[] values) {}
```

The first problem is that arrays are mutable. The default constructor and accessor store and return the exact same array reference.

The second problem is that default equality for an array component relies on the array object's reference equality rather than comparing the elements inside:

```java
ArrayComponentKey first =
        new ArrayComponentKey(new int[]{1, 2});

ArrayComponentKey second =
        new ArrayComponentKey(new int[]{1, 2});

System.out.println(first.equals(second)); // false
```

Two distinct array instances with identical contents do not make the records equal by default.

Notably, mutating an array's elements does not necessarily change the array's reference hash code. Yet that does not turn this record into a content-based value key. You must distinguish **hash stability** from **having the required equality semantics**.

If the key requirement is a content-based sequence of integers, merely cloning the array in the constructor while keeping default array equality does not solve the problem. You need all of the following simultaneously:

1. Protect the array from mutation via the constructor input.
2. Prevent the accessor from exposing the mutable internal array.
3. Define content-based equality.
4. Compute a matching content-based hash code.

An explicit immutable class is often easier to explain and maintain for this case.

## 8. An Immutable Key Class for Array Contents

For example:

```java
static final class IntArrayKey {
    private final int[] values;

    IntArrayKey(int[] values) {
        this.values = Objects.requireNonNull(values).clone();
    }

    int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntArrayKey key
                    && Arrays.equals(values, key.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }
}
```

This is a nested class in the demonstration program and requires importing `Arrays` and `Objects`.

How the protective layers work together:

- The `final` class prevents subclasses from adding state and complicating equality.
- The `private final` field retains ownership of the array reference.
- The constructor clones the input array.
- The accessor returns a clone rather than the internal array.
- `Arrays.equals` and `Arrays.hashCode` both operate on the integer sequence contents.

Two keys created from two separate arrays with the same numbers will be equal. Modifying the array passed to the constructor or the array returned by the accessor will not alter the key.

Cloning an `int[]` is sufficient to copy primitive values. For an object array, cloning only copies the element references; you must still account for the mutability of the element objects themselves.

Do not cache a hash code to mask a design that still exposes mutable data. If `equals` changes with mutated data while a cached hash code stays fixed, you create another consistency bug rather than achieving true immutability. [Java 17: Arrays.equals and hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

## 9. If You Customize a Record, Preserve Equality and Reconstruction

Records allow explicit declarations of constructors, accessors, and value methods within language constraints. That does not mean you can arbitrarily alter their semantics without respecting the `Record` contract.

One notable expectation of records is reconstruction: recreating a record using the values obtained from its accessors should produce a record equal to the original:

```text
copy = new R(r.c1(), r.c2(), ...)

r.equals(copy) must hold true.
```

If an accessor clones an array component while `equals` still uses array reference equality, a copy reconstructed from the accessors will not equal the original instance. This is one reason you should not merely add a defensive accessor while ignoring component equality.

If you customize equality on a record containing an array, you must consider `equals`, `hashCode`, the constructor, the accessors, and related invariants together. When a value is no longer naturally described by its public components, a regular value class is often clearer. [Java 17: Record Contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

## 10. Hash Sets and Tree Sets Require Stability Under Different Criteria

For a `HashSet`, the state participating in `equals`/`hashCode` must remain stable.

For a `TreeSet`, the state used by the comparator or natural ordering must also remain stable while the element resides in the tree. An object whose hash code is stable but whose sort field mutates can still end up out of order for tree searches.

An immutable value key type helps in both cases, though you must still choose an appropriate comparator:

- If a comparator inspects only part of the key, two distinct keys may compare as `0`.
- To obey the general `Set` contract fully, the ordering must be consistent with `equals`.
- A record does not automatically implement `Comparable` or generate a natural ordering just because it has value equality.

Choosing between a hash set and a tree set is a separate decision from choosing between a record and a class. One determines the access and deduplication mechanism; the other defines the element's value model. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 11. Updating a Profile Differs from Changing a Key

Given a map:

```java
Map<CustomerKey, CustomerProfile> customers = new HashMap<>();
```

You can update a customer's profile by replacing the value associated with the same immutable key. A change in display name does not require changing the key.

If the identity itself genuinely changes, create a new key and coordinate an explicit migration. You must consider:

- Does the new key already exist?
- Should the existing value be moved or merged?
- Do any secondary sets or indexes still hold the old key?
- How should concurrent readers or writers observe the transition?
- If the operation fails midway, what is the recovery procedure?

Immutable objects do not automatically make a multi-step `remove` and `put` sequence transactional. What they prevent is an object already stored inside a data structure silently changing its key value in place.

Likewise, a record holding immutable data does not automatically make a shared `HashMap` or `HashSet` thread-safe. Key stability and concurrent access coordination are two separate requirements.

## 12. Complete Java 17 Program

Save as `ImmutableKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ImmutableKeyDemo {
    record CustomerKey(String tenantId, String customerId) {
        CustomerKey {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(customerId);
            if (tenantId.isBlank() || customerId.isBlank()) {
                throw new IllegalArgumentException("ids must not be blank");
            }
        }
    }

    record CustomerProfile(CustomerKey key, String displayName) {}

    record OrderedTagKey(List<String> tags) {
        OrderedTagKey {
            tags = List.copyOf(tags);
        }
    }

    record UnsafeTagKey(List<String> tags) {}

    record ArrayComponentKey(int[] values) {}

    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] values) {
            this.values = Objects.requireNonNull(values).clone();
        }

        int[] values() {
            return values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof IntArrayKey key
                        && Arrays.equals(values, key.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        CustomerKey first = new CustomerKey("T1", "C7");
        CustomerKey equalKey = new CustomerKey("T1", "C7");
        System.out.println("record value equality = " + first.equals(equalKey));
        System.out.println("record equal hashes = "
                + (first.hashCode() == equalKey.hashCode()));

        Map<CustomerKey, String> customers = new HashMap<>();
        customers.put(first, "Lan");
        System.out.println("lookup with fresh record = " + customers.get(equalKey));
        customers.put(equalKey, "Lan updated");
        System.out.println("map size after update = " + customers.size());

        Set<CustomerKey> scoped = new HashSet<>();
        scoped.add(first);
        scoped.add(equalKey);
        scoped.add(new CustomerKey("T2", "C7"));
        System.out.println("tenant-scoped set size = " + scoped.size());

        CustomerProfile before = new CustomerProfile(first, "Lan");
        CustomerProfile after = new CustomerProfile(first, "Lan updated");
        System.out.println("profiles with changed name equal = "
                + before.equals(after));
        System.out.println("profile keys still equal = "
                + before.key().equals(after.key()));

        List<String> externalTags = new ArrayList<>(List.of("red"));
        OrderedTagKey stable = new OrderedTagKey(externalTags);
        Set<OrderedTagKey> stableSet = new HashSet<>();
        stableSet.add(stable);
        externalTags.add("blue");
        System.out.println("copied tags = " + stable.tags());
        System.out.println("stable key lookup = "
                + stableSet.contains(new OrderedTagKey(List.of("red"))));
        try {
            stable.tags().add("green");
        } catch (UnsupportedOperationException expected) {
            System.out.println("tag accessor does not allow structural mutation");
        }

        List<String> mutableTags = new ArrayList<>(List.of("red"));
        UnsafeTagKey unsafe = new UnsafeTagKey(mutableTags);
        UnsafeTagKey oldValue = new UnsafeTagKey(List.of("red"));
        System.out.println("unsafe key initially equal = " + unsafe.equals(oldValue));
        mutableTags.add("blue");
        System.out.println("unsafe key equal after external mutation = "
                + unsafe.equals(oldValue));

        ArrayComponentKey rawA = new ArrayComponentKey(new int[]{1, 2});
        ArrayComponentKey rawB = new ArrayComponentKey(new int[]{1, 2});
        System.out.println("default record array equality = " + rawA.equals(rawB));

        int[] externalArray = {1, 2};
        IntArrayKey arrayKey = new IntArrayKey(externalArray);
        Set<IntArrayKey> arrayKeys = new HashSet<>();
        arrayKeys.add(arrayKey);
        externalArray[0] = 99;
        int[] returnedArray = arrayKey.values();
        returnedArray[1] = 88;
        System.out.println("protected array value = "
                + Arrays.toString(arrayKey.values()));
        System.out.println("protected array key lookup = "
                + arrayKeys.contains(new IntArrayKey(new int[]{1, 2})));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Stdout:

```text
record value equality = true
record equal hashes = true
lookup with fresh record = Lan
map size after update = 1
tenant-scoped set size = 2
profiles with changed name equal = false
profile keys still equal = true
copied tags = [red]
stable key lookup = true
tag accessor does not allow structural mutation
unsafe key initially equal = true
unsafe key equal after external mutation = false
default record array equality = false
protected array value = [1, 2]
protected array key lookup = true
```

How to read the verification output:

1. Two records with the same tenant and customer ID are equal, share the same hash code, and look up the same mapping.
2. Putting a value with an equivalent key updates the entry rather than creating an extra mapping.
3. The same local customer ID under a different tenant remains a distinct set member.
4. A profile with a changed display name is a different profile value, yet the keys of the two profiles remain equal.
5. The record that defensively copies `List<String>` is unaffected when elements are added to the input list.
6. That record's accessor does not permit structural mutation of the stored list.
7. The non-defensive record suffers an observable value change through an input list alias.
8. Two separate array components are not compared by content under default record equality.
9. The `IntArrayKey` class protects both ingress and egress paths, so mutating external arrays does not affect set lookup.

The program does not query a set after deliberately corrupting a stored key. The "unsafe" section only compares the value before and after mutation to demonstrate shallow immutability, avoiding any promise of a specific lookup output for a corrupted key state.

It also avoids printing hardcoded record hash values or `HashSet`/`HashMap` iteration orders, ensuring the output does not depend on incidental implementation details.

## 13. How to Verify an Immutable Key Type

A meaningful test suite should include:

1. Creating two separate keys with identical values and verifying `equals`.
2. Verifying that equal keys produce the same hash code.
3. Looking up an entry in a map or set using a newly constructed key with the same value.
4. Confirming that differing scope components make keys unequal when required.
5. Attempting to mutate constructor input data after creation and verifying the key does not change.
6. Attempting to mutate data returned by accessors and verifying the key is unaffected.
7. Testing nested elements, not just the outer container.
8. Verifying that invalid input data is rejected according to contract.
9. If a comparator is used, verifying its consistency with equality.
10. If a record is customized, verifying that reconstructing a record from its accessors yields an instance equal to the original.

Do not assert that "two unequal keys must have different hash codes": collisions are legal. Do not use a hardcoded numeric hash value as general proof of a record's correctness.

## 14. Common Mistakes

| Misconception | What to Remember |
| --- | --- |
| The `record` keyword makes all internal data immutable | A record only makes its component fields `final`; referenced objects can still be mutable |
| A `final` field prevents mutating list or array contents | `final` prevents reassigning the reference, not mutating the referenced object |
| `List.copyOf` performs a deep copy | It does not copy the element objects themselves |
| Wrapping the source in an unmodifiable view is sufficient | The source can still be mutated through another alias |
| A record with an array component compares array contents automatically | Default record equality does not use `Arrays.equals` |
| Cloning an array on input is enough | An accessor that returns the internal array still exposes a mutation path |
| Caching the hash code can save a mutable key | Equality and hash code can become inconsistent |
| Every profile field should be a key component | Choose components based on value identity and avoid volatile attributes |
| A record automatically has a natural ordering for `TreeSet` | You must implement `Comparable` or provide an appropriate `Comparator` |
| Immutable keys make a collection thread-safe | Concurrent access coordination is still required separately |

## 15. Self-Practice

1. Is `record Key(List<String> ids) {}` safe as a hash key if the caller retains the `ArrayList` passed into it?  
   **Answer:** Not yet. The caller can mutate the list and change the key's value.

2. Why is `List.copyOf` more suitable than an unmodifiable view when you need a snapshot of a string list?  
   **Answer:** The result does not reflect subsequent additions or removals on the source collection; combined with immutable `String` elements, the component values remain stable.

3. Are two records of the same type containing two separate `int[]` arrays with identical numbers equal by default?  
   **Answer:** No. You need a content-based equality design if that behavior is required.

4. A customer changes their display name. Should a different customer key be created simply because a profile record includes a name field?  
   **Hint:** Separate the stable key from the profile and clearly define business identity.

5. Can a record containing `List<MutableItem>` be made a safe key solely by calling `List.copyOf`?  
   **Answer:** Not if mutable element state participates in equality or hashing.

A well-designed key type preserves identity semantics and prevents search-critical state from changing out of control. Records offer a concise representation, but true immutability must still be designed all the way down to internal components.
