# Testing Inheritance, State Mutation, and Independence After Copying

## 1. Why Do These Three Test Groups Belong to the Object Contract?

When implementing `Object` methods or building a class with value semantics, you need to verify object behavior **across multiple situations**, not only the case where two objects have identical data. Three categories of cases that readily expose bugs are:

1. **Inheritance:** a subclass adding properties or altering `equals()`/`hashCode()` can break symmetry, transitivity, or the relationship between the two methods.
2. **State mutation:** an object changing properties after creation can alter comparison results and hash codes; this is especially dangerous if the object is currently a key in a `HashMap` or an element of a `HashSet`.
3. **Copying:** a new object may only be a shallow copy, still sharing lists or child objects with the original. Tests must clearly verify the degree of independence promised by the API.

There is no single contract forcing **every** class to compare by value or deep-copy the entire object graph. Before writing tests, determine whether the class has **identity** or **value semantics**, which properties participate in `equals()`/`hashCode()`, which fields are permitted to mutate, and what state sharing or copying the API documentation promises.

## 2. Invariants to Verify

For non-null references `x`, `y`, `z`, the `Object.equals()` contract requires:

| Property | Check | Meaning |
| --- | --- | --- |
| Reflexive | `x.equals(x)` is `true` | An object equals itself |
| Symmetric | `x.equals(y) == y.equals(x)` | Reversing comparison order does not change the result |
| Transitive | If `x.equals(y)` and `y.equals(z)`, then `x.equals(z)` | Three equivalent objects are consistent |
| Consistent | Repeated comparisons yield the same result when relevant state does not change | No unexpected results arise |
| Non-null | `x.equals(null)` is `false` | Does not treat null as a normal object |

Relationship between `equals()` and `hashCode()`:

- If `x.equals(y)` is `true`, it is **mandatory** that `x.hashCode() == y.hashCode()`.
- Two unequal objects **may still** share the same hash code; do not write tests requiring hash codes of all distinct values to differ.
- If state relevant to `equals()` does not change, calls to `hashCode()` within the same run must be consistent. Hash code values do not need to remain identical across separate JVM runs.

You must also test **negative cases** (different types, differing meaningful properties, appropriate null values). A single passing case does not prove the contract holds across the entire input space, so select representative datasets, edge cases, and inheritance scenarios.

For copying, verify these properties separately:

- **Not the same reference:** `copy != original`.
- **Correct initial data:** the copy's contents match the data promised to be copied; if the class uses value equality, you can initially check `copy.equals(original)`.
- **Independence after mutation:** modifying a mutable component on one side does not affect the other side **if** the API promises an independent copy. Check both mutating the original and mutating the copy.
- **Integrity of intentional sharing:** if the documentation specifies that a component is shared, verify that sharing rather than treating it as a bug by default.

## 3. Testing Inheritance: Symmetry and Transitivity Traps

### 3.1. Parent Uses `instanceof`, Subclass Adds Meaningful Fields

Suppose `BaseKey` only stores `id` and considers any object of `BaseKey` or a subclass with the same `id` to be equal:

```java
@Override
public boolean equals(Object other) {
    return other instanceof BaseKey key && id == key.id;
}
```

Then `TaggedKey extends BaseKey` adds a `tag` field, and the subclass's `equals()` requires both `id` and `tag` to match.

Then, with `base = new BaseKey(7)` and `child = new TaggedKey(7, "red")`:

```text
base.equals(child)  → true
child.equals(base)  → false
```

Symmetry is broken. If the subclass also includes `tag` in its hash calculation, a pair of objects deemed equal by the parent class can even have different hash codes, violating the hash rule. Testing only `child.equals(base)` while forgetting the reverse direction will miss the bug.

### 3.2. Trying to Fix Symmetry Yet Breaking Transitivity

An unsafe workaround is: the subclass ignores `tag` when compared with the parent class, yet compares `tag` when both sides are the subclass. Consider:

- `red = TaggedKey(7, "red")`
- `base = BaseKey(7)`
- `blue = TaggedKey(7, "blue")`

If the two classes are written so that `red.equals(base)` and `base.equals(blue)` are both true, yet `red.equals(blue)` is false, the **transitivity** contract is broken. A test with this triple catches the bug that same-type pairwise checks fail to notice.

You cannot arbitrarily add value components in a subclass while the parent still permits cross-type comparison and always preserve the `equals()` rules. The right design depends on the data domain:

- Use a `final` value class so subclasses cannot alter the meaning of equality.
- Use **composition** to add metadata, rather than subclassing a value class that already defines equality.
- Use `getClass()` so equality only works between two objects of the exact same runtime class, if domain semantics accept this distinction; when a subclass overrides, it must still uphold the contract.
- Some hierarchies use a carefully designed `canEqual` protocol; do not assume switching `instanceof` to `getClass()` fits every application.

Tests must reflect the **design decision on cross-type equality**: are a parent class and a subclass with matching data *allowed* to be equal? If not, verify `!parent.equals(child)` and `!child.equals(parent)`. If yes, test all contract rules and pairs/triples of distinct subclasses, rather than testing each override in isolation.

## 4. Testing State Mutation

### 4.1. State Participating in Equality and Hashing

A mutable class can compute `equals()`/`hashCode()` from changeable fields. Having the return values of both methods change with state does not by itself violate the contract: the consistency contract applies **when information used in comparison has not been modified**.

However, inserting an object into a `HashSet` or using it as a `HashMap` key and then mutating a field participating in the hash code can cause lookups to fail: the object was placed under the old hash, while subsequent lookups use the new hash. For these structures, it is best to use **immutable keys**.

A valuable test should step through milestones:

1. Create `a` and `b` with equal values; verify `a.equals(b)` and matching hashes.
2. Mutate an equality-participating field on `a`; verify comparison reflects the new value.
3. Mutate `b` to the same new value; verify the two objects are equal again and share the same hash.
4. If the field can revert to the old value, verify results also revert as designed.
5. If the class is used in hash collections, verify or enforce **do not mutate keys after insertion**, or use an immutable key design; do not turn a lookup bug into a functional expectation of the application.

Distinguish **mutable fields used for display** from **fields participating in logical identity**. Simply asserting that the hash changes on every setter can be wrong: if a property does not belong to equality, it usually **should not** change the hash.

### 4.2. Inherited State

If a subclass adds mutable fields participating in equality, test state transitions on **both parent and subclass fields**, with multiple objects of the same subclass. Ensure `hashCode()` is overridden using the exact same components used by `equals()`. Do not assume every subclass is allowed to extend equality; some metadata fields do not participate in equality.

## 5. Testing Independence After Copying

### 5.1. Shallow Copy and Deep Copy

For a `Profile` object containing a mutable `Address` and `List<String>`:

```text
Original Profile ── address ──> Address("Hue")
                 └─ skills  ──> ["java"]

Shallow copy     ── address ──> same Address
                 └─ skills  ──> same List

Deep copy        ── address ──> new Address("Hue")
                 └─ skills  ──> new List ["java"]
```

A shallow copy may create a **new outer object** while still sharing references to child objects. Therefore, checking only `assertNotSame(original, copy)` is insufficient.

A deep copy does not have to clone immutable objects like `String`, and usually should not copy resources like sockets, locks, or threads. The depth depends on the **class contract** and ownership boundaries, especially when the object graph contains cycles or intentionally shared elements.

### 5.2. Independence Test Matrix

| Operation | Shallow copy sharing references | Contract-compliant deep copy |
| --- | --- | --- |
| Modify `original.address.city` | `shallow.address.city` changes too | `deep.address.city` does not change |
| Add element to `original.skills` | `shallow.skills` sees the new element | `deep.skills` does not change |
| Modify `deep.address.city` | Not applicable | `original.address.city` does not change |
| Add to `deep.skills` | Not applicable | `original.skills` does not change |
| Compare outer object | Copy differs by reference from original | Copy differs by reference from original |
| Compare mutable child object | May be the **same** reference | Must be a **different** reference if independent copy is promised |

If an API uses `clone()` via `Object.clone()`, remember that the default behavior copies fields and **does not automatically deep-copy referenced objects**. A class may need to override `clone()`, provide a copy constructor, or offer a factory for controlled deep copying. Do not equate implementing `Cloneable` with guaranteeing full state independence.

## 6. Standalone, Runnable Java 17+ Example: Detecting Bugs and Verifying Behavior

The example intentionally includes a broken equality class so **tests catch the bug**; the remaining checks illustrate how to verify proper designs. Save the code as `ObjectContractVerification.java`.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class ObjectContractVerification {
    // Broken design: parent class treats subclass with the same id as equal.
    static class BaseKey {
        final int id;

        BaseKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BaseKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static final class TaggedKey extends BaseKey {
        final String tag;

        TaggedKey(int id, String tag) {
            super(id);
            this.tag = tag;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof TaggedKey key
                    && super.equals(key)
                    && tag.equals(key.tag);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + tag.hashCode();
        }
    }

    // Consistent design: only compares value objects with the same runtime class.
    static class StrictKey {
        final int id;

        StrictKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other != null
                    && getClass() == other.getClass()
                    && id == ((StrictKey) other).id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static final class StrictTaggedKey extends StrictKey {
        final String tag;

        StrictTaggedKey(int id, String tag) {
            super(id);
            this.tag = tag;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof StrictTaggedKey key
                    && super.equals(key)
                    && tag.equals(key.tag);
        }

        @Override
        public int hashCode() {
            return 31 * super.hashCode() + tag.hashCode();
        }
    }

    static final class MutableKey {
        String code;

        MutableKey(String code) {
            this.code = code;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key
                    && Objects.equals(code, key.code);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(code);
        }
    }

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Profile {
        final String name;
        final Address address;
        final List<String> skills;

        Profile(String name, Address address, List<String> skills) {
            this.name = name;
            this.address = address;
            this.skills = skills;
        }

        Profile shallowCopy() {
            return new Profile(name, address, skills);
        }

        Profile deepCopy() {
            return new Profile(
                    name,
                    new Address(address.city),
                    new ArrayList<>(skills)
            );
        }
    }

    public static void main(String[] args) {
        BaseKey parent = new BaseKey(7);
        TaggedKey child = new TaggedKey(7, "red");
        boolean badSymmetry = parent.equals(child) == child.equals(parent);
        System.out.println("Broken inheritance symmetry valid: " + badSymmetry);

        StrictKey strictParent = new StrictKey(7);
        StrictTaggedKey s1 = new StrictTaggedKey(7, "red");
        StrictTaggedKey s2 = new StrictTaggedKey(7, "red");
        StrictTaggedKey s3 = new StrictTaggedKey(7, "red");

        boolean strictSymmetry =
                strictParent.equals(s1) == s1.equals(strictParent);
        boolean transitive =
                s1.equals(s2) && s2.equals(s3) && s1.equals(s3);
        boolean equalHash =
                s1.equals(s2) && s1.hashCode() == s2.hashCode();

        System.out.println("Strict inheritance symmetry valid: " + strictSymmetry);
        System.out.println("Strict value transitivity valid: " + transitive);
        System.out.println("Equal strict values share hash: " + equalHash);

        MutableKey first = new MutableKey("A");
        MutableKey second = new MutableKey("A");
        boolean equalBefore = first.equals(second);
        int initialHash = first.hashCode();

        Set<MutableKey> set = new HashSet<>();
        set.add(first);
        first.code = "B";

        System.out.println("Mutable values equal before: " + equalBefore);
        System.out.println("Mutable values equal after: " + first.equals(second));
        System.out.println("Mutable hash changed: "
                + (first.hashCode() != initialHash));
        System.out.println("Mutated key found in HashSet: " + set.contains(first));

        Profile original = new Profile(
                "Mai", new Address("Hue"), new ArrayList<>(List.of("java")));
        Profile shallow = original.shallowCopy();
        Profile deep = original.deepCopy();

        original.address.city = "Da Nang";
        original.skills.add("spring");

        System.out.println("Shallow shares nested state: "
                + (shallow.address.city.equals("Da Nang")
                && shallow.skills.contains("spring")));
        System.out.println("Deep preserves initial state: "
                + (deep.address.city.equals("Hue")
                && deep.skills.equals(List.of("java"))));
        System.out.println("Deep owns separate mutable references: "
                + (deep.address != original.address
                && deep.skills != original.skills));

        deep.address.city = "Ha Noi";
        deep.skills.add("testing");

        System.out.println("Reverse mutation independent: "
                + (original.address.city.equals("Da Nang")
                && original.skills.equals(List.of("java", "spring"))));
    }
}
```

Compile and run:

```bash
javac ObjectContractVerification.java
java ObjectContractVerification
```

Output on OpenJDK/Java 17 with the example code above:

```text
Broken inheritance symmetry valid: false
Strict inheritance symmetry valid: true
Strict value transitivity valid: true
Equal strict values share hash: true
Mutable values equal before: true
Mutable values equal after: false
Mutable hash changed: true
Mutated key found in HashSet: false
Shallow shares nested state: true
Deep preserves initial state: true
Deep owns separate mutable references: true
Reverse mutation independent: true
```

**Interpreting the output:**

- The first line is `false` **intentionally** to demonstrate that the test catches a broken design. It must never be treated as the expected result of a production implementation.
- With `StrictKey`, parent and subclass never compare equal across different runtime classes; two `StrictTaggedKey` objects with identical `id`/`tag` are still equal and share the same hash. This is **one design choice**, not the only way to resolve equality under inheritance.
- After changing `"A"` to `"B"`, `MutableKey` changes its hash; on Java 17's `HashSet`, lookup in this example returns `false`. This illustrates the risk of breaking the stable hash key assumption, **not** a guarantee that every hash collection or every value pair will always return `false` after every mutation.
- The shallow copy sees changes in `Address` and `List`, whereas the deep copy keeps its initial values and likewise does not affect the original when mutated in the reverse direction.

Note that the example tests a few representative cases and prints the results for observation. In a real test suite, use assertions to **fail immediately when an expected contract is broken**, and record intentional failure cases as bug-verifying tests rather than passing product tests.

## 7. Converting Into Automated Tests With Assertions

A helper with no external library dependencies can assert the essential properties (placed inside a test class):

```java
static void checkEqualityContract(Object a, Object b, Object c) {
    if (!a.equals(a) || !b.equals(b) || !c.equals(c)) {
        throw new AssertionError("Reflexivity failed");
    }
    if (a.equals(null) || b.equals(null) || c.equals(null)) {
        throw new AssertionError("Null equality failed");
    }
    if (a.equals(b) != b.equals(a)
            || b.equals(c) != c.equals(b)
            || a.equals(c) != c.equals(a)) {
        throw new AssertionError("Symmetry failed");
    }
    if (a.equals(b) && b.equals(c) && !a.equals(c)) {
        throw new AssertionError("Transitivity failed");
    }
    if (a.equals(b) && a.hashCode() != b.hashCode()) {
        throw new AssertionError("Equal objects have different hashes");
    }
}
```

This is an **illustrative helper snippet**, not a standalone Java program. It only checks the objects passed in, so you still need to choose data reflecting inheritance structures and key states. In JUnit 5, this can be replaced with `assertEquals`, `assertFalse`, `assertNotSame`, and `assertAll`; equality testing in particular should include three objects and both comparison directions.

For code with `clone()` or a copy constructor, a good test typically follows this structure:

1. Create an object containing **at least two levels of mutable references**, not just strings/primitives.
2. Copy it and compare initial data; distinguish `same object` from `same value`.
3. Mutate nested state on the original, asserting the copy remains valid per contract.
4. Mutate nested state on the copy, asserting the original remains valid.
5. If there is a collection, mutate both its **structure** (add/remove) and **mutable elements inside**, because copying into a new `ArrayList` can still share the elements inside the list.
6. For types with value equality, test `equals()`/`hashCode()` before and after mutations; do not compare hashes between two different states as an invariant.

## 8. Commonly Missed Testing Mistakes

| Omission | Consequence | Addition |
| --- | --- | --- |
| Calling only `parent.equals(child)` | Misses broken symmetry in the reverse direction | Test both directions |
| Testing only two objects | Misses transitivity violations via a third object | Construct representative triples |
| Assuming two hashes differ when two objects are unequal | Places a wrong requirement on `hashCode()` | Only require equal hashes when `equals()` is `true` |
| Testing only initial state | Misses bugs when mutable fields change | Test state transitions |
| Mutating a hash key inside `HashMap` and blaming the collection | Ignores the requirement to use keys with stable hashes | Freeze the key or avoid mutating after insertion |
| Checking only `copy != original` | Fails to detect aliases to nested mutable fields | Check child references and two-way mutations |
| Copying only the list container | Mutable elements may still be shared | Check deeply down to the level requiring independence |
| Requiring every copy to satisfy `equals(original)` | Wrong if the class defines equality by identity | Confirm equality semantics first |
| Assuming default `clone()` is a deep copy | Shallow copy leaks shared state | Read the contract and write matching tests |
| Testing only one subclass | Hard to catch broken cross-type equality as the hierarchy grows | Test multiple runtime types and corresponding pairs/triples |

## 9. Completion Criteria

A reliable verification suite for the object contract must be able to answer:

- **Inheritance:** Are parent/subclass objects permitted to be equal, and are both comparison directions consistent? Do object triples preserve transitivity? Are hashes identical when equals is true?
- **State:** Which fields form logical identity? Which setters are permitted to alter equality/hashing? Is a mutable key being used inside hash collections?
- **Copying:** Is the copy shallow or deep per contract? Which levels of the mutable graph must be independent? Do mutations in **both directions** cause unintended side effects?

From those answers, build tests using assertions and data representing each design decision. **Do not infer correctness from a single passing comparison or a copy with a different outer reference**: it is precisely inheritance, state mutation, and reference-sharing scenarios that most often expose gaps in the contract.
