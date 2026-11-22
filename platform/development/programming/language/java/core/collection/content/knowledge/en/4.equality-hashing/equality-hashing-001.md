# The Role of equals and hashCode in Searching and Deduplication

A collection does not automatically know that “two customers are the same person” or “two products are the same item.” It needs a rule to decide whether two objects should be considered equal.

In Java, `equals` describes value equality between objects. `hashCode` provides a hash code so structures such as `HashSet` and `HashMap` can organize storage and lookup more efficiently.

The two methods work together without replacing each other:

- `equals` answers **whether two values are considered equal**.
- `hashCode` helps **locate the candidate group that may match**.
- Having the same hash code does not mean being equal.
- If two objects are equal according to `equals`, they must have the same hash code.

This article explains these rules through searching in a list, deduplicating in a set, and looking up by key in a map. The examples use Java 17 or later.

## 1. Distinguishing the Same Object from the Same Value

### 1.1. The == Operator on References

For two object references, `a == b` checks whether they point to the exact same object.

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
```

The two strings are created separately but have the same content. `String` defines `equals` based on content, so its result differs from `==`.

Do not rely on accidental results from the string pool to infer that `==` compares string content. Likewise, collections do not replace `equals` with `==` just because two elements have the same type.

### 1.2. Custom Classes Do Not Automatically Have Field-Based Equality

If a class has only an `id` field but does not override `equals`, two distinct objects with the same `id` still use the default rule inherited from `Object`: equal only when they are the same object instance.

Illustrative example:

```java
final class PlainKey {
    private final String id;

    PlainKey(String id) {
        this.id = id;
    }
}
```

With two calls to `new PlainKey("C7")`, having identical field contents does not automatically establish value equality. If both are added to a `HashSet`, the set may keep both because they are not equal according to the class's rule.

Before choosing a deduplication structure, you must determine **what to deduplicate by**: the entire value, a stable identifier, a tenant ID–customer ID pair, or another criterion. This is a data modeling decision.

## 2. The Contract to Maintain Between equals and hashCode

### 2.1. Equals Must Be a Consistent Relation

For non-`null` references, the properties that must hold include:

| Property | Requirement |
| --- | --- |
| Reflexive | `x.equals(x)` is true |
| Symmetric | `x.equals(y)` and `y.equals(x)` agree |
| Transitive | If x equals y and y equals z, then x equals z |
| Consistent | Does not change its result while the data involved in the comparison remains unchanged |
| Comparison with null | `x.equals(null)` is false |

If symmetry or transitivity is broken, searching or deduplication may depend on how the query is performed. Do not design `equals` as an ad-hoc “roughly similar” check if that relation does not satisfy the properties above.

### 2.2. HashCode Must Be Consistent with Equality

The most important rule:

```text
a.equals(b) == true
        ⇒
a.hashCode() == b.hashCode()
```

The converse is not true. Two unequal objects may still have the same hash code.

A hash code must remain consistent during a single execution while the information used in equality comparisons does not change. The general contract does not require the hash code of every object type to remain identical across separate application runs.

Therefore, whenever you override `equals`, you must normally override `hashCode` accordingly. Do not use a hash code as a unique identifier, memory address, or cryptographic fingerprint. It is simply an `int` serving the hashing contract. [Java 17: Object.equals and hashCode contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

## 3. Where Do Collections Use Equality?

| Structure / Operation | Role of Equality and Hashing |
| --- | --- |
| `List.contains`, `indexOf`, `remove(value)` | Finds elements using the equality relation specified by the API |
| `HashSet.add` | Does not add an element that is already present according to equality |
| `HashSet.contains`, `remove` | Uses hashing to narrow the search, then identifies the matching element |
| `HashMap.put`, `get`, `containsKey` | Searches using the key's equality and hash code |
| `HashMap.containsValue` | Checks value equality; the key's hash code does not serve as an index for values |
| `TreeSet`, `TreeMap` keys | Uses natural ordering or a comparator to determine position and equivalence |

Not every collection relies on hashing. Replacing an `ArrayList` with a `HashSet` can expose a `hashCode` bug even when searching in the list previously appeared to work properly.

The contract of `contains` is typically expressed in terms of value comparison, but an implementation is not required to call `equals` sequentially on every element. It may filter out candidates using hash information first. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 4. Searching in a List Does Not Mean Deduplicating

Suppose `CustomerKey` defines equality by `id`:

```java
CustomerKey first = new CustomerKey("C7");
CustomerKey another = new CustomerKey("C7");

List<CustomerKey> list =
        new ArrayList<>(List.of(first, another));

System.out.println(list.size()); // 2
System.out.println(list.contains(new CustomerKey("C7"))); // true
```

This is an illustrative snippet; the `CustomerKey` class is defined in full in the program at the end of the article.

The list retains two equal elements because `List` allows duplicate occurrences. `contains` only answers whether at least one matching element exists.

When calling `remove(new CustomerKey("C7"))`, the list removes a single matching occurrence according to the `remove(Object)` contract; it does not automatically remove every element with the same ID.

Distinguish three requirements:

- **Search:** is there a matching element?
- **Count:** how many occurrences are there?
- **Deduplicate:** keep a single representative according to a chosen rule.

The same `equals` rule can participate in all three, but the data structure and operation determine the final outcome.

## 5. How Does HashSet Combine Hashing with equals?

You can view the mechanism conceptually:

```text
Value to add or find
        ↓
Obtain hash code to guide the lookup
        ↓
Inspect candidates in the relevant bucket/region
        ↓
Use the equality relation to confirm a match
        ↓
Match found: use the existing element
No match: no corresponding value exists yet
```

This is a conceptual model to understand the roles, not a description of the internal layout of every JDK version. You do not need to know table sizes or internal treeification thresholds to write `equals`/`hashCode` properly.

With two equal keys:

```java
Set<CustomerKey> unique = new HashSet<>();

System.out.println(unique.add(new CustomerKey("C7"))); // true
System.out.println(unique.add(new CustomerKey("C7"))); // false
System.out.println(unique.size());                     // 1
```

The second addition does not create another element. The `false` return value of `add` indicates that the set did not change because an equivalent element was already present.

A set also does not automatically merge domain data. If two objects are defined as equal by ID but hold different display information, calling `add` again is not a command to update the fields of the existing element. If you need “ID → latest profile,” a `Map` or an explicit update workflow expresses that intent more accurately. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

## 6. Hash Collisions Do Not Lose Distinct Values

`"Aa"` and `"BB"` are a short example of strings that produce the same hash code under `String`'s rule:

```java
String left = "Aa";
String right = "BB";

System.out.println(left.equals(right)); // false
System.out.println(left.hashCode());    // 2112
System.out.println(right.hashCode());   // 2112
```

When added to a `HashSet`:

```java
Set<String> values = new HashSet<>(List.of(left, right));
System.out.println(values.size()); // 2
```

The two strings have the same hash but are not equal, so they remain two distinct values. Hash-based structures are designed to handle collisions, not to store only a single element per integer hash value. [Java 17: String.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode())

A `hashCode` implementation that returns the same constant for every object can still satisfy the “equal objects have the same hash” condition. However, it degrades distribution and can lead to poor lookup performance.

Conversely, a hash function that produces diverse values but gives two equal objects different hashes **violates the contract** and is not an acceptable optimization.

### Two Issues to Keep Separate

| Issue | Correctness | Performance |
| --- | --- | --- |
| Collision between two unequal values | Allowed | Excessive collisions can increase lookup work |
| Two equal values having different hashes | Violates the contract | Cannot be treated merely as a slowdown |
| Well-distributed hash consistent with equals | Satisfies the required foundation | Supports more efficient lookups |

You do not need to demand a collision-free hash function; that cannot be guaranteed for an unbounded set of inputs when the output has a finite number of values.

## 7. HashMap Uses the Key's Rules

For example, a profile table keyed by customer ID:

```java
Map<CustomerKey, String> customers = new HashMap<>();

customers.put(new CustomerKey("C7"), "old");
String previous =
        customers.put(new CustomerKey("C7"), "updated");

System.out.println(previous); // old
System.out.println(customers.size()); // 1
System.out.println(customers.get(new CustomerKey("C7"))); // updated
```

Even though each call creates a new key object, equality by `id` paired with a consistent hash allows the map to locate the existing mapping.

The second `put` replaces the value associated with the same logical key rather than creating an additional entry. You do not need to hold on to the exact original key reference to perform a lookup.

Keep these distinctions clear:

- `containsKey(key)` checks key equality.
- `containsValue(value)` checks value equality.
- Values may be duplicated across multiple keys.
- When a map permits `null` values, `get(key) == null` is not sufficient to conclude that the key is absent.

Do not assume that the map replaces the stored key object instance with the newly passed key object, or that it preserves any specific reference identity beyond what the API guarantees. What you should rely on is mapping by logical key. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 8. Writing a Key Type That Matches the Data Domain

Suppose we only need to identify customers by `id` within a well-defined scope:

```java
static final class CustomerKey {
    private final String id;

    CustomerKey(String id) {
        this.id = Objects.requireNonNull(id);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        return other instanceof CustomerKey key
                && id.equals(key.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

This is a nested class that can be placed inside an enclosing class; it requires importing `java.util.Objects`.

Design decisions in this example:

1. `id` must not be `null`; the constructor validates it immediately.
2. The class is `final`, preventing a hierarchy of subclasses from altering the meaning of equality.
3. `equals` has the exact signature `equals(Object)`, not an overload accepting only `CustomerKey`.
4. Two keys are equal when they have the same ID.
5. The hash is derived from the ID itself, so two equal keys have the same hash.
6. The `id` field is `final` and of type `String` (which is immutable), keeping the rule stable while the object acts as a key.

`@Override` helps catch signature mistakes. If you accidentally write `equals(CustomerKey other)`, that does not override `Object.equals(Object)`, and collections will continue using unintended behavior.

Do not treat this pattern as a rule that “every class must compare by id.” A coordinate value type might compare both components; a multi-tenant key requires including the tenant ID as well.

### Multiple Fields Must Carry the Same Meaning in Both Methods

For a key consisting of `tenantId` and `customerId`, two customers with the same customer ID in different organizations must not be deduplicated together.

A concise representation in Java 17:

```java
record TenantCustomerKey(String tenantId, String customerId) {}
```

The equality and hashing methods are generated automatically based on the record components. Two records belonging to different tenants will be distinct.

A record is appropriate when its declared components directly define the desired value semantics. However, a record does not automatically make every referenced inner object immutable. If a component is a mutable list, you must consider its impact on equality and hashing. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

## 9. Choosing the Right Data for Equality

Before writing code, answer these questions:

- Are two objects with the same ID but different names considered the same key?
- Is the ID unique across the entire system or only within a single tenant?
- Is the value case-sensitive?
- Should whitespace or input formatting be normalized?
- Can a field change after the object is stored?
- How should a newly created object without a stable ID be handled?

Do not casually use display names, mutable email addresses, or unassigned IDs as unique identifiers. If case-insensitive comparison is required, you must design both normalization and a matching hash calculation; changing `equals` alone while computing the hash from the raw string easily breaks the contract.

`hashCode` may use a subset of the information used by `equals` and remain valid, provided that any two equal objects always yield the same hash. However, omitting too much information can increase collisions. An easy-to-verify approach is to build the hash from the exact immutable value components used to determine equality.

If only a single feature needs deduplication by a special criterion, changing `equals` across an entire shared class may not be the right move. Instead, you can create a dedicated key type or project objects to an appropriate key for that feature. Changing a class's equality changes the meaning of searching and deduplication in every collection that relies on it.

## 10. Do Not Mutate Key State While Stored in a Hash Structure

Suppose a key's `hashCode` depends on a customer ID. After inserting it into a `HashMap`, the program mutates that ID.

The storage bucket was determined using the old state, whereas subsequent lookups compute from the new state. At that point, lookup or removal behavior is no longer guaranteed to work as expected.

Such a bug easily feels paradoxical: iterating over the collection still shows the object, yet looking it up by its expected value fails to find it. Do not write tests that assert a specific output for cases where a key has been mutated in violation of its usage contract.

Design guidelines:

- Use immutable value keys separated from frequently changing profile entities.
- Do not include mutable fields in key equality.
- If a key's identity genuinely must change, remove the entry using the old state first, then re-insert it with the new key through an explicit procedure.
- In systems shared across multiple components, prefer controlled update operations rather than exposing direct field mutation.

Marking a reference to a mutable object `final` is not enough: if the hash depends on the inner object's contents, those contents can still change. You must examine all data participating in equality.

## 11. Limitation: Not All Deduplication Is Driven by hashCode

`TreeSet` uses natural ordering or a comparator to locate and distinguish elements. Two elements that compare as `0` are treated as equivalent in a tree set.

If a comparator examines only the product name, two products with different IDs but the same name will be treated as a single value, even if `equals` considers them distinct. Fixing `hashCode` will not solve that problem because a tree set does not rely on hashes to determine element position.

To honor the equality-based `Set` contract fully, the ordering must be consistent with `equals`. Therefore, when diagnosing “why elements disappear during deduplication,” first determine whether the structure in use is a hash set or a tree set. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Similarly, a search operation using a custom predicate may inspect attributes different from those used by `equals`. Do not treat every data-matching operation as the same equality relation.

## 12. Complete Java 17 Program

Save as `EqualityHashDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualityHashDemo {
    static final class PlainKey {
        private final String id;

        PlainKey(String id) {
            this.id = id;
        }
    }

    static final class CustomerKey {
        private final String id;

        CustomerKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof CustomerKey key
                    && id.equals(key.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    record TenantCustomerKey(String tenantId, String customerId) {}

    public static void main(String[] args) {
        PlainKey plainA = new PlainKey("C7");
        PlainKey plainB = new PlainKey("C7");
        Set<PlainKey> plainSet = new HashSet<>(List.of(plainA, plainB));
        System.out.println("plain equals = " + plainA.equals(plainB));
        System.out.println("plain set size = " + plainSet.size());

        CustomerKey first = new CustomerKey("C7");
        CustomerKey sameValue = new CustomerKey("C7");
        System.out.println("same reference = " + (first == sameValue));
        System.out.println("value equals = " + first.equals(sameValue));
        System.out.println("same hash = "
                + (first.hashCode() == sameValue.hashCode()));

        List<CustomerKey> list =
                new ArrayList<>(List.of(first, sameValue));
        System.out.println("list size = " + list.size());
        System.out.println("list contains fresh key = "
                + list.contains(new CustomerKey("C7")));

        Set<CustomerKey> unique = new HashSet<>();
        System.out.println("first add = " + unique.add(first));
        System.out.println("equal add = " + unique.add(sameValue));
        System.out.println("unique size = " + unique.size());
        System.out.println("set contains fresh key = "
                + unique.contains(new CustomerKey("C7")));

        Map<CustomerKey, String> customers = new HashMap<>();
        customers.put(first, "old");
        String previous = customers.put(sameValue, "updated");
        System.out.println("previous map value = " + previous);
        System.out.println("map size = " + customers.size());
        System.out.println("lookup with fresh key = "
                + customers.get(new CustomerKey("C7")));

        String left = "Aa";
        String right = "BB";
        Set<String> collisions = new HashSet<>(List.of(left, right));
        System.out.println("collision values equal = " + left.equals(right));
        System.out.println("left hash = " + left.hashCode());
        System.out.println("right hash = " + right.hashCode());
        System.out.println("collision set size = " + collisions.size());
        System.out.println("collision lookup = "
                + collisions.contains(new String("BB")));

        Set<TenantCustomerKey> scoped = new HashSet<>();
        scoped.add(new TenantCustomerKey("T1", "C7"));
        scoped.add(new TenantCustomerKey("T2", "C7"));
        System.out.println("tenant-scoped size = " + scoped.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EqualityHashDemo.java
java EqualityHashDemo
```

Stdout:

```text
plain equals = false
plain set size = 2
same reference = false
value equals = true
same hash = true
list size = 2
list contains fresh key = true
first add = true
equal add = false
unique size = 1
set contains fresh key = true
previous map value = old
map size = 1
lookup with fresh key = updated
collision values equal = false
left hash = 2112
right hash = 2112
collision set size = 2
collision lookup = true
tenant-scoped size = 2
```

How to read the verification output:

1. `PlainKey` does not override equality, so two distinct objects with the same ID remain two separate elements in the set.
2. `CustomerKey` defines value equality: different references are equal and share the same hash.
3. The list keeps both occurrences, yet finds a match when queried with a fresh key of the same value.
4. The hash set adds the logical key only the first time; the equivalent addition returns `false`.
5. The map replaces the value when given an existing logical key, and can then be queried using a fresh key instance.
6. Two strings with a hash collision remain two distinct elements and are both retrievable.
7. The tenant-scoped record key preserves two customers who share the same local ID under different tenants.

The program does not print the iteration order of `HashSet` or `HashMap` directly, so stdout does not depend on traversal order that those classes do not guarantee. Nor does it rely on default identity hash codes or object memory addresses to produce deterministic output.

## 13. Common Pitfalls to Check

| Pitfall | Impact or Fix |
| --- | --- |
| Comparing strings with `==` | Checks reference identity only; use content equality when that is the requirement |
| Overriding `equals` while keeping an incompatible hash | Hash sets/maps may fail to find or deduplicate properly; update both to satisfy the contract |
| Overriding only `hashCode` so “same ID means same person” | A hash code alone does not define equality; a matching `equals` is required |
| Treating equal hashes as equal values | Collisions are valid; `equals` must still distinguish values |
| Including every field automatically without domain consideration | Changing names or statuses can unintentionally alter value identity |
| Mutating hash-participating fields while used as a key | Can break the relationship between the stored bucket position and lookup state |
| Writing `equals(MyType)` instead of `equals(Object)` | Creates an overload instead of an override; use `@Override` to catch this |
| Asymmetric equality between superclass and subclass | Matching results become inconsistent; design clear equality boundaries |
| Treating `HashSet.add` with a duplicate key as a profile update | A set does not automatically merge fields |
| Treating a hash code as a persistent or security ID | Neither unique nor backed by general guarantees suitable for those purposes |

## 14. How to Verify a Key Class

A valuable test suite should verify that:

1. An object is equal to itself.
2. Two objects with the same identifying value are equal in both directions.
3. Multiple objects with the same identifying value satisfy transitivity.
4. Two equal objects produce the same hash code.
5. Two distinct keys are not merged merely because of a hash collision.
6. Lookups in `HashSet` and `HashMap` using a newly constructed object with the same value succeed.
7. Assigning a new value to the same logical key preserves the expected entry count.
8. Scoping components such as tenant or environment participate in equality when required by the domain.
9. Data used as a key cannot be mutated uncontrollably.

Do not test that “two unequal objects must have different hashes”: that is not part of the contract. Likewise, do not assert a specific hardcoded hash value unless the type itself specifies a public formula that must be verified, such as the `String` example in this article.

## 15. Self-Practice

1. Two objects are unequal but have the same hash. Is `HashSet` required to keep only one?  
   **Answer:** no. A collision does not create equality; the set can still hold both.

2. Two objects are equal but have different hashes. What is wrong?  
   **Answer:** the class violates the `equals`–`hashCode` contract.

3. Why can a `List` hold two equal keys while `contains` still returns `true` when searching with a fresh key?  
   **Answer:** a list allows multiple occurrences; searching and deduplicating are two distinct operations.

4. Two customers with the same ID in two different tenants are merged when added to a set. What should you check?  
   **Hint:** check whether key equality includes the required tenant scope.

5. When using a record as a key, do you still need to consider the mutability of its components?  
   **Answer:** yes. A record does not automatically freeze mutable objects referenced inside it.

A search or deduplication structure works properly only when the value relation of its elements is designed properly. Define equality first, keep the hash consistent with it, and protect the stability of the data acting as a key.
