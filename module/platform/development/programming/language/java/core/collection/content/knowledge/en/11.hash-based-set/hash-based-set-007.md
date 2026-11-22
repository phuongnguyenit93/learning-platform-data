# Mutable Keys, the equals–hashCode Contract, and Lost Elements

## 1. Why Is an Element Still in the Set Yet Cannot Be Found?

Suppose an application inserts a customer into a `HashSet<Customer>` to deduplicate by customer ID. Later, another piece of code mutates that very ID. When iterating over the Set, the application still sees the customer; however, `contains` or `remove` may return `false`. The object did not vanish from memory on its own. The information used to look it up no longer matches the information used when it was placed into the hash structure.

This lesson belongs to the **Hash-Based Sets** topic. The goal is to understand three related but distinct concerns:

- `equals` determines whether two objects are considered the same value or the same entity under the chosen model.
- `hashCode` provides a hash code consistent with that definition of equality.
- While an element resides in a Set, the data that determines its identity must remain stable.

The word **key** in this lesson does not mean the Set stores key–value pairs like a Map. With `HashSet<E>`, the element `E` itself is used for membership lookup. The fields that `equals` and `hashCode` rely on form the **logical key** of the element.

For example, if two customers are considered equal when they share the same `id`, then `id` is the identity data; the display name may simply be descriptive data. If two coordinates are equal when both `x` and `y` are equal, then the pair `(x, y)` is the value-identifying data.

We also need to distinguish **reference identity** from **value equality**:

```java
a == b       // Do both variables point to the same object?
a.equals(b)  // According to the class definition, are the two objects equal?
```

These are two illustrative expressions, not a standalone program. A Set using `equals` does not mean it ignores the hash code and scans every object with `==` on each lookup.

The right learning path is: define the equality rule → understand the hash code requirement → observe what happens when a key changes → choose a stable key design → verify the full lifecycle of the element.

## 2. What Does the equals–hashCode Contract Protect?

For non-`null` references, `equals` must be reflexive, symmetric, transitive, and consistent when the data used for comparison does not change; comparing against `null` must return `false`.

The crucial hash code requirement is:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

The converse is not required. Two unequal objects may still share the same hash code. An object's hash code must remain consistent within a single execution as long as the information used by `equals` does not change; it does not need to remain identical across different application runs. This is the contract of [Object.equals and Object.hashCode in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)).

The following cases must be interpreted differently:

| Relationship between two objects | Hash code relationship | Meaning |
|---|---|---|
| Equal | Same hash code | Satisfies the mandatory requirement |
| Equal | Different hash codes | Contract implementation bug |
| Not equal | Same hash code | Hash collision; not a correctness bug by itself |
| Not equal | Different hash codes | Normal case |

A hash code is not a unique national ID for an object. Do not use a `Set<Integer>` holding `hashCode()` values as a substitute for `Set<Customer>` when deduplicating customers: two distinct customers could be conflated solely because of a hash collision.

When implementing `equals` based on `id`, an easy-to-verify approach is to implement `hashCode` based on the same `id`. Never include an additional field in the hash code if it can differ between two equal objects in a way that produces different hash results. For instance, an `equals` that checks only `id` while `hashCode` also includes `displayName` will break when two different names belong to the same `id`.

Conversely, the hash code does not strictly have to include every field used in `equals`. It can use less information and still satisfy the one-way requirement above, though it is more likely to cause collisions. Therefore, evaluate both correctness and distribution rather than treating "hash all fields" as a mechanical rule.

## 3. Class Contract and Set Usage Conditions Are Two Separate Layers

A mutable class can implement `equals` and `hashCode` sensibly at any given point in time:

```java
// Illustrative snippet in a class with an int code field.
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof Key key && code == key.code);
}

@Override
public int hashCode() {
    return Integer.hashCode(code);
}
```

If `code` changes from `1` to `2`, both equality and the hash code change to reflect the new data. You cannot simply see a changing hash code and conclude that every such class violates `Object`'s contract: the contract is conditioned on whether the data used for comparison has changed.

The problem arises when that object is currently an element of a Set. The [Java 17 Set documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) states that the behavior of a Set is not specified if the value of an object is changed in a manner that affects `equals` comparisons while the object is an element in the Set.

Therefore, two layers must be checked:

1. **Class layer:** do two equal objects always produce the same hash code, and do the properties of `equals` hold?
2. **Structure lifecycle layer:** is the data that determines equality modified between the time the element is added to and removed from the Set?

A class can pass the first layer's checks yet still be misused at the second layer. That is why a test suite that merely creates two objects, calls `equals`, and stops is insufficient to catch lost-element bugs.

Nor should we forbid all mutations on every element. If identity depends only on a stable `id`, changing a note or display name that does not participate in `equals`–`hashCode` may be completely appropriate. What must remain stable is the **identity semantics**, not necessarily the entire state of the object.

## 4. Hash Structures Hold References but Do Not Track Setters

`HashSet` is backed by a `HashMap`, according to the [Java 17 HashSet documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html). You can visualize insertion and lookup as follows:

```text
When adding:
    read the current logical key
        -> compute the hash code
        -> select the search region
        -> check for a matching element
        -> store an entry containing a reference to the object

When searching or removing by object:
    read the logical key at the time of the call
        -> compute the current hash code
        -> search in the corresponding region
        -> check candidate elements
```

In the [OpenJDK 17 HashMap implementation](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java), an entry stores the hash code computed at creation time along with the key reference. A lookup recomputes the hash code from the passed-in object, checks the entry's stored hash code, and only then checks reference identity or `equals`. Mutating a field of the object does not automatically update the stored entry.

This diagram is only a mental model for understanding the bug:

```text
At insertion time:
    object K: code = 1
    stored entry: reference to K, hash information from code = 1

After calling the setter:
    object K: code = 2
    old entry: still retains the hash information from insertion time

When calling contains(K):
    lookup uses hash information from code = 2
```

You do not need to memorize bucket counts or internal formulas to avoid this bug. You only need to recognize that an index built from old information does not automatically adjust when the object is modified through another reference.

In particular, `==` being true between the searched object and the stored object does not guarantee the lookup will succeed: the candidate region search and hash code check may have already eliminated the old entry beforehand.

Nor should you conclude "if two hash codes happen to land in the same bucket, it's safe." In the described implementation, the hash code stored in each entry also participates in the check. More importantly, once membership identity has been altered, the Set's usage condition is no longer upheld.

## 5. Program 1: An Element Gets Lost and the Same Reference Is Added Again

Save the file `MutableKeyFailureDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class MutableKeyFailureDemo {
    static final class Key {
        private int code;

        Key(int code) {
            this.code = code;
        }

        void changeCode(int newCode) {
            code = newCode;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Key key && code == key.code);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(code);
        }
    }

    public static void main(String[] args) {
        Key key = new Key(1);
        Set<Key> keys = new HashSet<>();
        keys.add(key);

        System.out.println("contains before change = " + keys.contains(key));
        key.changeCode(2);
        System.out.println("size after change = " + keys.size());

        long references = 0;
        for (Key stored : keys) {
            if (stored == key) {
                references++;
            }
        }
        System.out.println("same reference seen by iteration = " + references);
        System.out.println("contains after change = " + keys.contains(key));
        System.out.println("remove after change = " + keys.remove(key));
        System.out.println("add same reference again = " + keys.add(key));
        System.out.println("size after re-add = " + keys.size());

        references = 0;
        for (Key stored : keys) {
            if (stored == key) {
                references++;
            }
        }
        System.out.println("same reference occurrences = " + references);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 MutableKeyFailureDemo.java
java MutableKeyFailureDemo
```

Verified run output:

```text
contains before change = true
size after change = 1
same reference seen by iteration = 1
contains after change = false
remove after change = false
add same reference again = true
size after re-add = 2
same reference occurrences = 2
```

This is an **experiment in intentionally misusing a Set**. The code uses language features and APIs available in Java 17 and later. The results were verified using Azul OpenJDK 24.0.2 after compiling with `--release 17`; the mechanism was cross-checked against the OpenJDK 17 source code. The lines after mutating the key are observations of this specific implementation, not a guarantee that every Set implementation or every invalid input will produce the exact same output.

### 5.1. Why Does size Remain 1?

Calling `key.changeCode(2)` only mutates the object. It does not call `keys.remove`, does not call `keys.add`, and does not cause the Set to proactively recount equivalence classes. The stored entry still exists.

The loop sees the same reference once. That confirms the object has not been removed from the structure's entries. It does not prove that the lookup path under the current hash code is still valid.

### 5.2. Why Do Both contains and remove Fail?

Both operations are called with the mutated key. In this example, the current search path does not match the entry created when `code = 1`. Consequently, both checking and removing by the object fail to find the old entry.

Do not try to "fix" this by replacing `remove(key)` with `remove(new Key(2))`: the new probe object also describes the new identity and uses the new hash code. The problem lies in the stale index state, not in whether you used the exact same reference variable.

### 5.3. Why Can Adding the Same Reference Again Produce size 2?

The second `add` uses the new hash information. In this run, it does not detect the old entry and creates another entry pointing to the very same object. When iterating, the same reference is encountered twice.

This is not a valid capability to exploit as a Set containing duplicate elements. It is an observed consequence after the program mutated the identifying information of an element inside the Set.

The key practical takeaway is: **never fix a lost element by re-adding it**. Doing so can make the state even harder to reason about rather than restoring uniqueness.

### 5.4. Why Is There No ConcurrentModificationException?

Changing the `code` field is not equivalent to a structural modification such as adding or removing an entry through the Set. There is no general mechanism forcing every element setter to notify iterators.

A program that throws no exceptions may still be violating the data structure's usage conditions. Never use "the loop finished normally" as proof that all keys are still findable.

## 6. Program 2: A Broken Contract Differs from Valid Hash Collisions

The next example places two types side by side:

- `BrokenKey` compares by `id`, yet allows two objects with the same `id` to have different hash codes. It is broken by design, even though every field is `final`.
- `CollidingKey` is a record whose identity is `id`, but it intentionally returns hash code `0` for all values. This distribution is poor, yet the "equal objects have equal hash codes" requirement still holds.

Save the file `EqualityHashContractDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class EqualityHashContractDemo {
    static final class BrokenKey {
        private final int id;
        private final int suppliedHash;

        BrokenKey(int id, int suppliedHash) {
            this.id = id;
            this.suppliedHash = suppliedHash;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof BrokenKey key && id == key.id);
        }

        @Override
        public int hashCode() {
            return suppliedHash;
        }
    }

    record CollidingKey(int id) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    public static void main(String[] args) {
        BrokenKey a = new BrokenKey(7, 1);
        BrokenKey b = new BrokenKey(7, 2);
        Set<BrokenKey> broken = new HashSet<>();

        System.out.println("broken keys equal = " + a.equals(b));
        System.out.println("broken hashes equal = "
                + (a.hashCode() == b.hashCode()));
        System.out.println("add broken a = " + broken.add(a));
        System.out.println("add broken b = " + broken.add(b));
        System.out.println("broken set size = " + broken.size());

        CollidingKey x = new CollidingKey(1);
        CollidingKey y = new CollidingKey(2);
        Set<CollidingKey> valid = new HashSet<>();

        System.out.println("collision keys equal = " + x.equals(y));
        System.out.println("collision hashes equal = "
                + (x.hashCode() == y.hashCode()));
        System.out.println("add collision x = " + valid.add(x));
        System.out.println("add collision y = " + valid.add(y));
        System.out.println("contains equal probe = "
                + valid.contains(new CollidingKey(1)));
        System.out.println("add equal probe = "
                + valid.add(new CollidingKey(1)));
        System.out.println("valid set size = " + valid.size());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 EqualityHashContractDemo.java
java EqualityHashContractDemo
```

Verified run output:

```text
broken keys equal = true
broken hashes equal = false
add broken a = true
add broken b = true
broken set size = 2
collision keys equal = false
collision hashes equal = true
add collision x = true
add collision y = true
contains equal probe = true
add equal probe = false
valid set size = 2
```

The `BrokenKey` lines illustrate a class that violates the contract, not a valid way to create a Set with two equal members. The output of the broken example was verified in the environment mentioned in Program 1; do not treat that output as a compatibility requirement for other libraries.

In the `CollidingKey` section, `x` and `y` share the same hash code but are not equal, so both are retained. When adding `new CollidingKey(1)`, the Set recognizes that an equal element is already present and returns `false`.

Two distinct conclusions emerge from this example:

1. `final` fields do not automatically make a broken `equals`–`hashCode` pair correct.
2. Hash collisions do not bypass `equals`, nor do they break uniqueness as long as the structure's invariants are upheld.

Do not choose a constant hash code in production code just to make a "two equal values have the same hash" test pass. That test is a necessary condition; it does not evaluate distribution quality or whether equality changes while an element is in the Set.

## 7. Why Patches That Only Fix the Hash Are Still Insufficient

### 7.1. Keeping a Constant Hash Does Not Preserve Uniqueness

Suppose a class implements `equals` using a mutable `code` field, while `hashCode` always returns `0`. Adding two objects with codes `1` and `2` initially creates two distinct members. Then the second object's code is mutated to `1`.

The two objects are now equal according to `equals`, even though the structure still holds two previously added entries. The Set does not proactively merge them after a setter call.

Here, the hash code never changed at all. The bug still occurs because **the equality relationship changed while the elements were still in the Set**. Thus, the claim "just keeping the hash stable is enough" misses the most critical part.

### 7.2. Caching the Old Hash Code in a Field

If `equals` reads the current code while `hashCode` returns a cached result from the old code, a probe object created with the current value may equal the old object yet produce a different hash code. This patch turns a lifecycle bug into a consistency bug between the two methods as well.

You should only precompute and cache a hash code when the data determining equality is immutable or has been captured into an appropriately stable value. Never use caching to mask identity mutation.

### 7.3. Using identityHashCode While equals Still Uses Data

Object-identity hashing does not automatically align with value-based `equals`. Two objects with different references may share the same `id` and be considered equal, yet per-instance hashing does not guarantee they produce the same result.

If your model's true goal is reference identity, design and choose the data structure specifically for that goal. Do not stitch half of a value-based rule together with half of a reference-based rule to patch a lookup bug.

### 7.4. Random or Time-Based Hashing

If the identity data does not change yet every hash call yields a different result, the class fails the contract even before mutability is considered. Lookups have no stable basis for locating a previous entry.

Fix the **identity model and lifecycle** first, and only then improve hash code distribution. Changing the hash formula alone cannot solve an identity that is mutating outside the structure's control.

## 8. Which Data Should Be Chosen as the Logical Key?

Two common models must be decided based on business semantics:

| Model | Identity question | Appropriate data | How changes happen |
|---|---|---|---|
| Value | Do two values have the same essential content? | Value components, kept immutable | Create a new value |
| Entity | Do two objects represent the same entity? | A stable, established identifier | Change descriptive data, keep identifier |
| Snapshot | Do two snapshots at collection time share the same key info? | Components copied and frozen to the right depth | Capture a new snapshot |
| Reference identity | Is it literally the exact same object? | Object identity semantics | Use only when the problem truly requires it |

There is no universal rule that "all fields belong in equals" or "a single id is always enough" for every class. For example:

- A customer can change their name and remain the same customer.
- A coordinate point whose `x` changes becomes a different coordinate value.
- An email address used as a login name may change through business workflows; it is not automatically a lifelong stable identifier for an account.
- An entity that has not yet been assigned an official ID needs an identity policy before joining a Set keyed by that ID. Do not put multiple "no-id-yet" objects under a vague equality rule and hope the Set will adjust itself once IDs are assigned.

A simple value key can be represented with a record:

```java
// Declaration snippet; can be placed in an appropriate class.
record CustomerKey(long id) {
}
```

`long` is a primitive value; a record's `id` has no setter. When the identifier is properly established and does not need to change, this type expresses intent far more clearly than a large object full of descriptive data.

For keys containing `String`, `String` itself is immutable; however, you still must decide the business policy: is it case-sensitive, should whitespace be normalized, are blank values allowed? Normalizing upon key creation ensures every place uses the same canonical value. Never trigger side-effecting normalization from inside `equals`.

## 9. Program 3: Descriptive Data Can Change When Identity Is Stable

The following example chooses an already-assigned `id` as `Customer`'s identity. The display name does not participate in comparison or hashing.

Save the file `StableIdentitySetDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class StableIdentitySetDemo {
    static final class Customer {
        private final long id;
        private String displayName;

        Customer(long id, String displayName) {
            this.id = id;
            this.displayName = displayName;
        }

        void rename(String newName) {
            displayName = newName;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof Customer customer && id == customer.id);
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Customer original = new Customer(7L, "Lan");
        Set<Customer> customers = new HashSet<>();
        customers.add(original);
        int hashBefore = original.hashCode();

        original.rename("Minh");
        Customer probe = new Customer(7L, "Another name");

        System.out.println("hash unchanged after rename = "
                + (hashBefore == original.hashCode()));
        System.out.println("contains original = " + customers.contains(original));
        System.out.println("contains equal probe = " + customers.contains(probe));
        System.out.println("add equal probe = " + customers.add(probe));
        System.out.println("size = " + customers.size());
        System.out.println("stored reference is original = "
                + (customers.iterator().next() == original));
        System.out.println("stored name = "
                + customers.iterator().next().displayName);
        System.out.println("remove equal probe = " + customers.remove(probe));
        System.out.println("empty after remove = " + customers.isEmpty());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 StableIdentitySetDemo.java
java StableIdentitySetDemo
```

Verified run output:

```text
hash unchanged after rename = true
contains original = true
contains equal probe = true
add equal probe = false
size = 1
stored reference is original = true
stored name = Minh
remove equal probe = true
empty after remove = true
```

Renaming from `Lan` to `Minh` does not change who the customer with `id = 7` is. A probe object with a different name is still recognized by the Set as the same member.

The `add(probe)` call returns `false` and does not replace the stored object. Afterward, the Set still holds the `original` reference with the name `Minh`. This is important to remember when using a Set to "update records": adding an equal object does not mean updating the data of the existing object.

The example marks the class `final` to avoid introducing symmetry issues if a subclass were to alter the equality rule. In a design with inheritance, you must examine the contract between superclass and subclass rather than copying `instanceof` mechanically.

This design is only appropriate when:

- `id` is genuinely stable throughout the managed lifecycle.
- Two objects with the same `id` must be treated as the same customer within the application's scope.
- The display name is not part of the value used to distinguish members.

If the business requirement is to store multiple name versions of the same customer at different points in time, you need an appropriate versioned key. Do not keep `equals` solely on `id` and expect the Set to retain every version.

Another option is to separate the key from the mutable data:

```java
// Model snippet, not a standalone program.
record CustomerKey(long id) {
}

final class CustomerProfile {
    private String displayName;

    CustomerProfile(String displayName) {
        this.displayName = displayName;
    }

    void rename(String newName) {
        displayName = newName;
    }
}

// When both key lookup and updating descriptive data are needed:
// Map<CustomerKey, CustomerProfile> profiles = new HashMap<>();
```

This expresses that identity and updatable content have separate responsibilities. However, choosing a Map depends on the problem's operations; you do not need to replace every Set with a Map just because an element has a descriptive field.

## 10. final and record Only Help Within What They Protect

A `final` reference-type field prevents reassigning the reference itself after initialization; it does not prevent mutating the referenced object.

For example:

```java
// Illustrative snippet.
final List<String> tags = new ArrayList<>();
tags.add("A");   // Valid: modifies the List contents.
tags.add("B");   // Still valid.
```

Records do not automatically freeze an entire object graph either. The [Java 17 Record documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) describes records as shallowly immutable: the components are fixed by direct value or reference, but an object behind a reference can still be mutable.

If a record contains a `List<String>`, the default generated equality and hash code methods will depend on the List component's contents. Mutating the contents of that List can alter the identity of the record.

### 10.1. Program 4: Defensive Copy for a List Component

`UnsafeKey` accepts the external List directly. `SafeKey` uses a compact constructor to capture a snapshot that cannot be mutated through that external List.

Save the file `RecordKeySnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class RecordKeySnapshotDemo {
    record UnsafeKey(List<String> tags) {
    }

    record SafeKey(List<String> tags) {
        SafeKey {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("A"));
        UnsafeKey unsafe = new UnsafeKey(input);
        SafeKey safe = new SafeKey(input);
        Set<UnsafeKey> unsafeSet = new HashSet<>();
        Set<SafeKey> safeSet = new HashSet<>();
        unsafeSet.add(unsafe);
        safeSet.add(safe);

        System.out.println("unsafe contains before change = "
                + unsafeSet.contains(unsafe));
        input.add("B");

        System.out.println("input size = " + input.size());
        System.out.println("unsafe tags size = " + unsafe.tags().size());
        System.out.println("safe tags size = " + safe.tags().size());
        System.out.println("unsafe contains after change = "
                + unsafeSet.contains(unsafe));
        System.out.println("safe contains original = " + safeSet.contains(safe));
        System.out.println("safe contains equal snapshot = "
                + safeSet.contains(new SafeKey(List.of("A"))));

        try {
            safe.tags().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutate safe tags = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 RecordKeySnapshotDemo.java
java RecordKeySnapshotDemo
```

Verified run output:

```text
unsafe contains before change = true
input size = 2
unsafe tags size = 2
safe tags size = 1
unsafe contains after change = false
safe contains original = true
safe contains equal snapshot = true
mutate safe tags = UnsupportedOperationException
```

The `unsafeSet` portion is an experiment that intentionally mutates identity data after adding an element; the post-mutation results are observations on the verified implementation. The `safeSet` portion keeps the key stable in this example.

### 10.2. What to Copy and How Far Does Protection Reach?

In the constructor:

```java
SafeKey {
    tags = List.copyOf(tags);
}
```

The `tags` parameter is replaced with the result of `List.copyOf` before being assigned to the record component. According to [List.copyOf in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), the returned List is unmodifiable, does not reflect subsequent modifications to the input collection, and rejects a `null` collection or `null` elements.

In the example, the elements are immutable `String` instances, so there is no remaining path to mutate the identifying content through those strings. If the component were `List<MutableTag>`, copying only the List would not be enough: the `MutableTag` objects could still be mutated through shared references.

In that case, you need one of these deliberate choices:

- Convert each element into an immutable value used as the key.
- Perform a defensive copy deep enough for the parts participating in identity.
- Use only an immutable identifier of the nested element.
- Change the model so mutable nested data does not participate in the key.

You do not need to deep-copy the entire object graph if data is unrelated to identity. However, you must know exactly which reference paths could alter `equals` or `hashCode`.

### 10.3. Indirect Mutation Paths That Are Easily Missed

A key can change without any direct setter on the key class:

- A constructor retains an input array or List still owned by the caller.
- A getter returns an internal collection directly.
- A nested object inside the key has a setter.
- A collection serving as a key has elements added, removed, or replaced.
- Calling code holds another reference to the same object and mutates it through that reference.

Therefore, checking that "the class has no setters" is only the first step. You must inspect input data, output data, and nested components inside the key.

For arrays, you must also decide whether equality semantics are by reference or by content. Do not assume that every reference component of a record is automatically deep-compared the way you expect. Choose a key type that clearly expresses its semantics rather than merely picking concise syntax.

## 11. What If Business Logic Truly Requires Changing a Key?

### 11.1. Prefer Creating a New Key

With immutable value keys, "changing the code" should generally be modeled as removing the old value and inserting the new value:

```java
// Snippet in a single-threaded flow, with an initially valid Set.
record CodeKey(int code) {
}

Set<CodeKey> keys = new HashSet<>();
CodeKey oldKey = new CodeKey(1);
CodeKey replacement = new CodeKey(2);
keys.add(oldKey);

if (keys.contains(replacement)) {
    throw new IllegalStateException("Replacement key already exists");
}
if (!keys.remove(oldKey)) {
    throw new IllegalStateException("Old key is missing");
}
if (!keys.add(replacement)) {
    throw new IllegalStateException("Replacement was not added");
}
```

This snippet illustrates the order of operations, not a general-purpose transaction. It assumes no other threads interfere, no side effects exist in `equals`–`hashCode`, and no errors occur between steps. Required types like `Set` and `HashSet` are imported in the enclosing program.

Checking for conflicts upfront avoids removing the old key only to discover the new key is already in use. In an application with multiple related structures, changing an identifier requires a unified business workflow with an appropriate failure policy.

Creating a new key does not mutate the old key held by another structure. This is a major advantage over mutating a widely shared object in place.

### 11.2. If You Must Keep a Mutable Object

The minimum order of operations in a controlled scenario is:

```text
1. While the old key is still intact, check for conflicts with the new value.
2. Remove the element from all indexes that depend on the key about to change.
3. Verify that the removal succeeded.
4. Mutate the identity data.
5. Re-insert into the indexes under the new key.
6. Handle errors and conflicts according to the designed policy.
```

The condition "while the old key is still intact" is essential. If you mutate first and then call `remove`, the program falls into the exact lost-element situation we are studying.

An object may simultaneously be:

- An element in a `HashSet`.
- A key in a `HashMap`.
- A component of a composite key elsewhere.
- An element in a structure sorted by that attribute.

Removing from one Set does not fix the other indexes. When multiple places hold references, enforcing this workflow becomes much harder; that is why immutable keys usually reduce control overhead significantly.

### 11.3. Do Not Ignore Conflicts

Suppose a customer with code `2` already exists, and a customer with code `1` is changed to `2`. After removing the old customer, `add` under the new key may return `false` because an equivalent member already exists.

A Set cannot decide whether to merge, reject, overwrite, or keep a version history. That is a business policy. Ignoring the return value of `add` easily turns an identity conflict into silent data loss in the processing flow.

For multithreaded systems, the sequence `contains` → `remove` → `add` does not automatically become atomic just because the structure supports concurrency on individual operations. You must design a coordination mechanism for the entire update request.

## 12. Diagnosing a Set Showing Signs of Lost Elements

A symptom worth investigating is: iteration finds the object, yet `contains` with that very object returns `false`. Start with the key's data and mutation paths.

### 12.1. Collect Meaningful Information

At the insertion boundary, you can record diagnostic information:

- The identity value at insertion time.
- The current identity value.
- The hash code at insertion time and currently, if recorded.
- When and where the mutation occurred.
- Which other structures hold the same object.

You cannot recover "the hash code at insertion time" by calling `hashCode` after the object has changed. A fresh call reads the current state; it does not provide history.

Nor should you look only at `toString`: that method might not print the identity fields, or it might also read the new values. You must observe the exact data that `equals`–`hashCode` actually uses.

### 12.2. Inspect Mutation Paths, Including Indirect Ones

Look for setters, operations that update nested collections, constructors that retain input data, and getters that expose mutable objects. Also check code that maps data or assigns identifiers after the object has already been added to the Set.

An unchanged hash code is not enough to conclude safety: two objects that were originally unequal may have become equal after data mutation. You must compare identity semantics, not just hash numbers.

### 12.3. Pause Mutations Before Recovering

If data continues mutating during inspection, rebuilding the Set can immediately become corrupted again. First, block or fix the path causing the bug.

Do not apply a generic fix such as:

```java
// Unfounded patch: do not use as a recovery procedure.
keys.add(lostKey);
```

The first example already showed that re-adding can create an additional entry for the same reference.

Similarly, do not assume that increasing capacity, forcing the Set to resize, wrapping it in another wrapper, or calling `contains` multiple times will repair the index. Those actions do not establish a valid key model.

### 12.4. Controlled Rebuild and Duplicate Resolution

Once you know the current canonical data and have stopped identity mutations, one recovery approach is to read the data to keep, convert it into stable keys, and build a new structure.

Before deduplicating, however, you must define a policy. Two current entries sharing the same key might hold two different profiles or two update histories. Building a new `HashSet` could silently drop one of the equivalent values; that is not a valid business decision by itself.

A careful investigation and recovery procedure typically includes:

1. Record a trace of existing entries so they can be reconciled.
2. Determine the current canonical key of each entry.
3. Group conflicting entries by canonical key.
4. Decide whether to keep, merge, or reject according to business rules.
5. Create stable keys and rebuild the index.
6. Switch to the new index only after verification is complete.

With a Set that has been used outside its specified conditions, do not treat the behavior of lookup or removal operations as a reliable foundation for automated repair. Rely on canonical data and an application-controlled workflow.

Building a new Set from old references does not automatically make the elements immutable either. If objects with mutable keys are still shared, the bug can recur.

## 13. Does Changing Collection Type or Wrapping Read-Only Solve It?

| Change | What it can provide | What must still hold |
|---|---|---|
| `HashSet` to `LinkedHashSet` | Encounter order according to the structure's rules | Hashing and equality keys must still be stable |
| Switching to `TreeSet` | Uniqueness and comparison-based ordering | Data used for comparison must be stable; not a cure for arbitrarily mutating keys |
| Concurrent Set structures | Operation coordination under their own contract | Does not automatically track setters or re-index element identities |
| Unmodifiable Set wrapper | Restricts adding or removing through the wrapper | Does not automatically freeze objects inside |
| Copying the Set | Creates another container structure | Does not automatically copy or make elements immutable |
| `final Set<Key> keys` | Prevents reassigning the `keys` variable to another Set | Does not prevent mutating the Set or mutating each Key |

This table is a design reasoning aid, not a claim that all structures share the same internals. When switching collection types, read its specific contract. A sorted tree and a hash table have different mechanisms, yet both require the indexing data to satisfy their usage conditions.

Container-level read-only access and element-level immutability are two different levels of protection. For instance, disallowing `add` does not mean nobody else holds a reference to call `customer.rename` or mutate a List inside a key.

The [Java 17 Set documentation on Unmodifiable Sets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable) also notes that mutable elements can cause a Set to behave inconsistently or make its contents appear to change. Therefore, `Set.copyOf` is not a tool for "deep-freezing" arbitrary objects.

In multithreaded programming, there are two separate questions: are operations on the structure properly coordinated, and are element identities stable? Solving the first question does not automatically solve the second.

## 14. Testing by Contract and by Lifecycle

A good test suite should use objects representing business rules rather than merely asserting a convenient `HashSet` output.

### 14.1. Testing Both Methods Together

For objects `a`, `b`, `c` expected to share the same identity, test:

- Reflexivity: `a.equals(a)`.
- Symmetry: `a.equals(b)` and `b.equals(a)` agree.
- Transitivity when the corresponding input relationships hold.
- Comparing with `null` returns `false`.
- When `a.equals(b)`, both hash codes are equal.
- When identity data does not change, repeated hash code calls remain constant within the same run.

Do not write tests requiring two unequal objects to have different hash codes. Such a test rejects valid collisions.

### 14.2. Testing Membership Behavior

With a valid key design, add `a` and then verify using a different object `b` that has a different reference but the same identity:

```text
add(a)             -> true
contains(b)        -> true
add(b)             -> false
size()             -> 1
remove(b)          -> true
isEmpty()          -> true
```

This is the expected scenario for a simple case starting from an empty Set, with two valid equal elements and no intervening mutations. It does not require any specific hash value.

### 14.3. Testing Allowed Attribute Updates

If the design allows changing `displayName` without changing `id`, test after renaming:

- The hash code remains unchanged.
- A probe object with the same `id` is still equal.
- `contains` and `remove` still work by the same identity.
- Adding an object with the same `id` does not create another member.

This is a lifecycle test like Program 3. It directly protects the decision that the name is not the identity.

### 14.4. Testing Data Sharing Inside Keys

For a key that accepts a collection, try mutating the original collection after creating the key. If the goal is a snapshot, the key's value must not change with the input.

Also try mutating through getters. If a getter returns a structure that allows modifying identifying content, a one-time defensive copy in the constructor may still not be enough protection.

For collections containing mutable objects, also test mutating nested components. A test that only adds an element to the original List will miss a mutation path through a child object.

### 14.5. Testing Identity-Change Flows and Conflicts

When business logic includes changing an identifier, cover at least these scenarios:

- The new key does not exist yet.
- The new key already belongs to another member.
- The old key is no longer in the structure.
- An error occurs midway if the update flow can throw exceptions.
- An object is indexed in multiple places.
- Update requests can run concurrently.

Do not write a test asserting "mutating a key inside a Set must make `contains` return `false`." That is an observable symptom of misuse, not correct behavior the application should depend on.

## 15. Common Misconceptions and Implementation Mistakes

| Claim or practice | Problem | Appropriate mindset |
|---|---|---|
| "A Set disallows duplicates so it cannot reach an invalid state" | Ignores element conditions and equality rules | Check both class contract and key lifecycle |
| Overriding only `equals` when value equality is needed | Hash behavior may no longer match | Design both methods as a pair |
| `equals` by `id`, hash by both id and name | Two objects with the same id can hash differently | Choose hash inputs consistent with equality |
| Including all fields in equals/hash via code generation | Descriptive fields or mutable collections may unintentionally become identity | Choose semantics before generating code |
| Assuming `final` means data is immutable | Only fixes the direct reference | Inspect the referenced objects |
| Assuming `record` means ignoring Lists or nested objects | Records do not deep-copy automatically | Snapshot and protect identifying components |
| Calling key setter before `remove` | Removal lookup uses the new key | Remove while the old key is valid or use a new immutable value |
| Re-adding a lost element | Can create another entry for the same object | Diagnose and recover in a controlled manner |
| Using a constant hash to "never lose the bucket" | Equality can still change; distribution is also poor | Keep identity stable, not just the hash number |
| Ignoring the return value of `add` during updates | Unaware the new key already existed | Design a conflict policy |
| Using an unmodifiable Set to protect keys | Internal objects can still be mutated | Protect at the identity-data level |
| Assuming no exceptions means correct usage | Semantic bugs can occur silently | Verify model invariants |

A useful habit is to inspect every field participating in `equals` and ask: "Who can change this data, through which references, and at what time?" If the answer extends beyond the Set's control boundary, consider separating out an immutable key.

Do not scan only for setters in the class itself. A shared array, List, or child object is often a subtler source of bugs than an obvious method named `setId`.

## 16. Practice Exercises

### Exercise 1: Customer Renaming

A class has an immutable `id` and a mutable `displayName`. `equals` uses `id`; `hashCode` uses both `id` and `displayName`.

Identify the bug before running any Set.

**Hint:** Two objects with the same `id` but different names are considered equal by `equals`, while the hash formula can produce different results. This is a contract bug without even waiting for an object to be mutated after insertion.

### Exercise 2: Mutating Coordinates

A point has mutable `x` and `y`; both methods rely on `x` and `y`. The program adds the point to a `HashSet`, then increments `x`.

Explain why the class can compare sensibly at each moment in time while the Set usage is still wrong.

**Hint:** The value-identifying rule changed while the element was in the Set. Use an immutable point and create a new point, or manage removal and re-insertion before and after the change in a controlled flow.

### Exercise 3: Hash Always 0

Two initially distinct elements are added to a Set. Then one element is mutated to equal the other. The hash of both is always `0`.

Does the unchanging hash make this process valid?

**Hint:** No. The condition regarding the equality relationship has been violated. The Set does not automatically merge two entries when a setter makes them equal.

### Exercise 4: Record Containing a List

Create `record SearchKey(List<String> filters)`. The constructor receives an `ArrayList`, and the caller adds a filter to that List after `SearchKey` is already in a Set.

Design a snapshot-based version and state its limitations.

**Hint:** Copying with `List.copyOf` in a compact constructor can be appropriate if you want to forbid `null` and elements are immutable strings. If nested elements are mutable, you must further protect the data participating in identity.

### Exercise 5: ID Assigned Later

An object is created without an official ID, placed into a Set keyed by that ID, and only receives its ID after persisting data.

Propose a sensible lifecycle boundary.

**Hint:** Establish a stable identity before joining a Set keyed by that identity, or use another stable key with clear semantics. Do not assume an "unassigned" ID and an assigned ID are two states that the same index will automatically update between.

### Exercise 6: Set Has size 1 but contains Returns false

Describe the data to collect and one action you should not take.

**Hint:** Compare the identity at insertion time with the current identity, inspect direct or indirect mutation paths, and check where else references are held. Do not immediately re-add to "make sure it's there"; first stop the path mutating the key and determine the canonical state.

### Exercise 7: Changing a Key to an Existing Value

A Set manages customers by ID. You want to change A's ID to B's existing ID.

State the decision that the Set cannot make on its own.

**Hint:** Whether to keep A, keep B, merge, reject, or store versions is a business policy. The update flow must check and handle conflicts; `add` returning `false` does not automatically produce a correct update outcome.

When designing a new key yourself, write down three things right in the design decision: which data defines equality, through which paths that data can change, and when an object is allowed to enter or leave indexed structures.
