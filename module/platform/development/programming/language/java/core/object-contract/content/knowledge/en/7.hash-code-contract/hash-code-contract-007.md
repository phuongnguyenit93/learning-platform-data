# Why Does Overriding `equals()` Usually Require Overriding `hashCode()` at the Same Time?

## 1. The Core Problem

In Java, `equals(Object)` answers the question of **whether two objects are considered equal according to the class's definition**. `hashCode()` produces an `int` integer used as a hash code, which is especially important for structures like `HashMap` and `HashSet`.

When you override `equals()` from same-reference comparison to content or identifier comparison, two **different instances in memory** can become equal. If you leave `hashCode()` as inherited from `Object`, you do not guarantee that two equal instances share the same hash code. This violates the **`hashCode()` contract**, causing hash-based collections to miss keys, retain duplicate elements, or handle keys unexpectedly.

Mandatory statement to remember:

**If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.**

The converse is false: two objects with equal hashes **do not have** to be equal according to `equals()`; that may simply be a hash collision.

Therefore, when changing a class's definition of "equality," you must consider **both** methods together. In typical implementations, you override both `equals()` and `hashCode()` based on the same attributes that are meaningful for equality.

## 2. Exact Contracts of the Two Methods

### 2.1. `equals()` Must Be an Equivalence Relation

For non-`null` references and when the information used in comparisons does not change, an `equals()` implementation must guarantee:

- **Reflexive:** `x.equals(x)` is always `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` have the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` are both `true`, then `x.equals(z)` must be `true`.
- **Consistent:** repeated calls with the same relevant information yield the same result.
- **Null comparison:** `x.equals(null)` is `false`.

`Object.equals()` defaults to reference identity comparison, similar to `==` on two object references. Subclasses can override it to compare by data. Doing so expands which objects are considered equal, bringing along the obligation to update the hash accordingly.

### 2.2. What Commitments Does `hashCode()` Make?

According to the Java contract:

1. For the **same object**, if the information used in `equals()` is not modified, multiple calls to `hashCode()` during **a single execution** must produce the same result. The hash code is not required to stay the same across different program runs.
2. If `x.equals(y)` returns `true`, then `x.hashCode() == y.hashCode()` is **mandatory**.
3. If `x.equals(y)` returns `false`, the two hashes are **not required** to differ. Well-distributed hashes help performance, but are not a correctness condition of equality.

Written as implications:

```text
equals(a, b) == true  =>  hashCode(a) == hashCode(b)    [REQUIRED]
hashCode(a) == hashCode(b) => equals(a, b) == true      [FALSE]
equals(a, b) == false => hashCode(a) != hashCode(b)     [NOT REQUIRED]
```

`hashCode()` only produces a 32-bit integer and can collide. The hash itself is **not** a unique ID, not a memory address, and should not be used as a business identifier.

## 3. Why Does Overriding Only `equals()` Easily Break the Contract?

Suppose you have a class representing a key by `tenantId` and `documentId`:

```java
import java.util.Objects;

// Illustrative snippet, not a standalone program.
final class OnlyEqualsKey {
    private final String tenantId;
    private final String documentId;

    OnlyEqualsKey(String tenantId, String documentId) {
        this.tenantId = tenantId;
        this.documentId = documentId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OnlyEqualsKey that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(documentId, that.documentId);
    }

    // Does not override hashCode(): still inherits Object.hashCode().
}
```

Suppose `first` and `second` are two distinct `OnlyEqualsKey` instances with the same two fields:

```java
OnlyEqualsKey first = new OnlyEqualsKey("T1", "D-10");
OnlyEqualsKey second = new OnlyEqualsKey("T1", "D-10");
// first.equals(second) == true
```

Calling `first.equals(second)` returns `true` by contents. However, the default `Object.hashCode()` is based on object identity. Java **does not guarantee** that two different instances share the same hash code; they usually return different values, though collisions can still happen. Thus this class **fails to guarantee** the mandatory implication "equal implies equal hash codes."

Do not write examples relying on the assumption that `first.hashCode() != second.hashCode()` is guaranteed: Java does not guarantee identity hashes are always distinct. To demonstrate the bug with **deterministic** output, the runnable example below uses a key type that intentionally returns two different hashes for two objects considered equal by `equals()`.

## 4. `HashMap` and `HashSet` Rely on Both Hash and Equality

Conceptually:

1. When adding a key, the hash structure uses `hashCode()` to locate the appropriate storage area/bucket.
2. Within the inspected area, the structure needs to distinguish keys with matching hash codes using equality (or same-reference check).
3. When retrieving with an equivalent key, it must reach a location compatible with the stored key. If two keys are considered equal yet have different hash codes, the search may look in the wrong place and never inspect the target element.

Bucket details, internal operations, and collision-handling levels are implementation details; what you must rely on when programming is the **`equals/hashCode` contract**.

| Operation | When the Contract Is Valid | When `equals` Says Equal but Hashes Differ |
| --- | --- | --- |
| `HashSet.add(second)` after `add(first)` | Equal element is treated as duplicate; size does not grow | May accept the "duplicate" as a new element |
| `HashSet.contains(second)` | Can find the equivalent element that was added | May return `false` |
| `HashMap.get(second)` after `put(first, value)` | Finds the value of the equivalent key | May return `null` even though an equal key exists |
| `HashMap.put(second, value2)` | Updates the mapping of the equivalent key | May create two entries for keys considered equal |

List-based collections such as `ArrayList.contains` and direct comparisons generally use `equals()` without relying on element hash codes; therefore they can yield correct results even when a class has a broken `hashCode()`. Do not assume the class is valid because of that: the bug will surface when switching to `HashSet` or `HashMap`.

## 5. Complete Java 17 Program: Broken Then Fixed

The example below presents two key classes.

- `BrokenKey` intentionally **violates the contract**: `equals()` compares `code`, while `hashCode()` returns the `slot` field ignored by equality. Two instances with the same `code` and different `slot` values are equal yet have different hashes. This is a **deterministic** simulation to make the bug easy to observe.
- `CorrectKey` uses the same combination of `tenantId` and `code` in both `equals()` and `hashCode()`. `label` is purely descriptive information and is excluded from both.

Save the file **`EqualsHashCodeContractDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualsHashCodeContractDemo {
    static final class BrokenKey {
        private final String code;
        private final int slot;

        BrokenKey(String code, int slot) {
            this.code = Objects.requireNonNull(code);
            this.slot = slot;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof BrokenKey that)) return false;
            return code.equals(that.code); // "slot" is not part of equality
        }

        @Override
        public int hashCode() {
            return slot; // WRONG: field ignored by equals
        }
    }

    static final class CorrectKey {
        private final String tenantId;
        private final String code;
        private String label;

        CorrectKey(String tenantId, String code, String label) {
            this.tenantId = Objects.requireNonNull(tenantId);
            this.code = Objects.requireNonNull(code);
            this.label = label;
        }

        void rename(String label) {
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof CorrectKey that)) return false;
            return tenantId.equals(that.tenantId)
                && code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, code);
        }
    }

    public static void main(String[] args) {
        BrokenKey badA = new BrokenKey("X-7", 1);
        BrokenKey badB = new BrokenKey("X-7", 2);
        System.out.println("Bad equals: " + badA.equals(badB));
        System.out.println("Bad hashes equal: "
            + (badA.hashCode() == badB.hashCode()));

        Set<BrokenKey> brokenSet = new HashSet<>();
        brokenSet.add(badA);
        brokenSet.add(badB);
        System.out.println("Broken HashSet size: " + brokenSet.size());

        Map<BrokenKey, String> brokenMap = new HashMap<>();
        brokenMap.put(badA, "saved");
        System.out.println("Broken HashMap lookup: " + brokenMap.get(badB));

        CorrectKey a = new CorrectKey("T1", "X-7", "Ban dau");
        CorrectKey b = new CorrectKey("T1", "X-7", "Ban tai lai");
        CorrectKey c = new CorrectKey("T2", "X-7", "Tenant khac");

        System.out.println("Good equals: " + a.equals(b));
        System.out.println("Good hashes equal: "
            + (a.hashCode() == b.hashCode()));
        System.out.println("Different tenant equal: " + a.equals(c));

        Set<CorrectKey> correctSet = new HashSet<>();
        correctSet.add(a);
        correctSet.add(b);
        correctSet.add(c);
        System.out.println("Correct HashSet size: " + correctSet.size());

        Map<CorrectKey, String> correctMap = new HashMap<>();
        correctMap.put(a, "saved");
        System.out.println("Correct HashMap lookup: " + correctMap.get(b));

        a.rename("Da doi ten");
        System.out.println("Contains after rename: " + correctSet.contains(a));
    }
}
```

Compile/run from the folder containing the file using **JDK 17 or newer**:

```bash
javac EqualsHashCodeContractDemo.java
java EqualsHashCodeContractDemo
```

Output:

```text
Bad equals: true
Bad hashes equal: false
Broken HashSet size: 2
Broken HashMap lookup: null
Good equals: true
Good hashes equal: true
Different tenant equal: false
Correct HashSet size: 2
Correct HashMap lookup: saved
Contains after rename: true
```

**Output explanation, independent of random hash codes:**

1. Both `BrokenKey` objects are equal because they share `code == "X-7"` in content, yet their hashes are `1` and `2` respectively. This case intentionally violates the "equal implies same hash" condition.
2. `HashSet` keeps both violating objects as two elements because they have different hashes and are placed in different locations; `HashMap.get(badB)` fails to find the entry added under `badA`. Do not generalize these hash values 1 and 2 as the standard behavior of `Object.hashCode()`; the example is **a way to reproduce the consequences** of a class with a broken contract.
3. Both `CorrectKey` objects with the same `tenantId` and `code` are equal despite having different `label`s; their hashes are both computed with `Objects.hash(tenantId, code)`.
4. Object `c` has the same `code` but a different tenant, so it is **not equal** to `a`. Omitting `tenantId` from `equals` in this domain would wrongly merge two keys.
5. The correct `HashSet` contains only two distinct keys: `(T1, X-7)` and `(T2, X-7)`. `HashMap.get(b)` finds the value stored using `a`.
6. Changing `a`'s `label` does not alter the equality definition or hash, so the key is still found in the set. If `label` were included in `hashCode()`, renaming could break key lookup.

## 6. How to Implement Matching `equals()` and `hashCode()`

### 6.1. Choose the Set of Fields Based on the **Equality Definition**

Do not automatically put every field into both methods. For example, in `CorrectKey`, the key is `(tenantId, code)`, so both methods are written using **those two fields**; `label` does not participate.

Design rules:

- **Value objects** such as a coordinate pair `(x, y)`: usually compare all attributes that make up the value.
- **Entities** with a stable business ID: can compare the ID; the ID can be a composite `(tenantId, localId)` when uniqueness is scoped.
- **Metadata/cache/log/descriptive fields**: do not automatically become part of equality.
- **Easily mutated attributes**: consider excluding them from equality/hash if the object will be used as a key in hash structures.

There is no requirement that `hashCode()` must use **every** field that `equals()` uses; contractually, you could return a constant hash code (every object hashes to the same value) and still satisfy "two equal objects have equal hashes." However, that can create excessive collisions and hurt performance. Practical coding typically computes the hash from the exact fields participating in equality so the hash is useful, clear, and maintainable. What is critical is **never letting fields ignored by `equals()` change the hash of two equal objects**.

### 6.2. Choosing Tools by Data Type

| Data Type | Appropriate Equality Comparison | Corresponding Hash Component |
| --- | --- | --- |
| `int`, `long`, `boolean` | `==` | `Integer.hashCode`, `Long.hashCode`, `Boolean.hashCode` |
| Nullable `String`/value object | `Objects.equals(a, b)` | `Objects.hashCode(value)` or combined hash |
| Multiple nullable references | Combine `Objects.equals(...)` with `&&` | `Objects.hash(field1, field2, ...)` |
| `float`/`double` | Choose `Float.compare`/`Double.compare` to match a defined IEEE policy; watch out for NaN and signed zero | `Float.hashCode`/`Double.hashCode` accordingly |
| One-dimensional array | `Arrays.equals(a, b)` | `Arrays.hashCode(array)` |
| Multi-dimensional array when deep equality is needed | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(array)` |
| `BigDecimal` | `BigDecimal.equals` by value **and scale**, or a custom canonicalization policy | `BigDecimal.hashCode` if using default `equals`; hash of canonicalized value if using canonicalized equality |

`Objects.hash(...)` is a varargs method; it is convenient for a few fields, but can cause extra array allocation/boxing on hot paths. Optimize manually using multiplication by `31` and type-specific hash methods only when there is a reason and correctness has been verified. Manual combination example:

```java
@Override
public int hashCode() {
    int result = tenantId.hashCode();
    result = 31 * result + code.hashCode();
    return result;
}
```

This snippet belongs to a class with two fields `tenantId` and `code` both verified non-`null`, like `CorrectKey`; it is not a standalone program. `int` multiplication/overflow in hash calculation is normal and deterministic in Java.

### 6.3. When Do You Not Need to Implement Them Yourself?

A Java `record` usually has consistent `equals()` and `hashCode()` generated from its **record components**. For a record serving as a value object where all components genuinely belong to the equality definition, this is a concise choice. However, if a component is an array, the default generated equality does not automatically become deep content comparison; and if a component does not belong to business equality, the default generated code may be unsuitable.

A class that overrides **neither** `equals()` **nor** `hashCode()` and inherits identity behavior from `Object` still has a consistent contract. Problems arise when changing one side without ensuring the other side matches.

## 7. Subtle Mistakes to Avoid

### 7.1. `hashCode()` Is Not an Equality Check

Never replace `a.equals(b)` with `a.hashCode() == b.hashCode()` to decide whether two entities are the same. Two distinct objects can collide on hash; Java provides only a finite `int` space. A hash table still needs to compare keys by equality when candidates share a hash.

### 7.2. Same Hash Code Does Not Mean Same Java Object

`System.identityHashCode(obj)` produces a hash code based on identity, not a RAM address, and is not guaranteed unique. Meanwhile `Object.hashCode()` can be overridden by subclasses. To check for the same instance, use `a == b` on references; to check for equal domain value, use `a.equals(b)` when the class is properly designed.

### 7.3. Mutating a Field Used in Hash After Inserting into `HashSet`/`HashMap`

Suppose `hashCode()` uses `status` and `status` is modified after `set.add(object)`. When `contains(object)` computes the new hash, lookup may search a different location than where it was added. The same applies to fields used in `equals()`. Prefer immutable keys/value objects or include only stable fields in equality/hash.

The `final` keyword on a reference does not guarantee the referenced object is immutable: a `final List<String>` can still have its elements modified. If a field is a mutable array/collection and truly participates in equality, defend with copying, immutable wrappers, or an appropriate design.

### 7.4. Late-Assigned Database IDs

A new entity has `id == null`. If `equals()` only uses `Objects.equals(id, that.id)`, two different new entities both having `null` can be treated as equal; if `hashCode()` relies on the ID and the ID is assigned after `insert`, the hash changes while serving as a key. You need a consistent design for pre-save and post-save states, depending on the ORM framework and ID generation strategy. Do not assume that "overriding both methods" automatically works across every lifecycle stage.

### 7.5. Mismatched Normalization Between Equality and Hash

For example, `equals()` uses `code.equalsIgnoreCase(other.code)` while `hashCode()` uses `code.hashCode()` of the raw string. For `"abc"` and `"ABC"`, equality returns `true` yet raw hashes can differ: the contract is broken. Normalize the code in the constructor according to domain rules (for instance, `toUpperCase(Locale.ROOT)` for technical identifiers where appropriate), then use the **same canonical representation** in both methods.

With `BigDecimal`, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, yet default `equals` returns `false` because their `scale`s differ. If you change equality to compare numeric value via `compareTo`, you must also compute the hash using a normalized policy for equal numeric values; keeping the raw `BigDecimal` hash is dangerous.

### 7.6. Inheritance Breaking Symmetry

If a superclass compares two fields and a subclass compares three fields, `parent.equals(child)` may differ from `child.equals(parent)`. A simple approach for value-representing classes is `final class` to fix the equality relation. With inheritance or ORM proxies, you need a class-typing strategy that is consistent and compatible with the framework. Auto-generating `hashCode()` cannot rescue an `equals()` implementation that violates symmetry.

### 7.7. Assuming Hashes Are Stable Across Multiple Runs

The contract only requires the hash code to be consistent **within a single execution** when relevant equality information does not change. Do not write `hashCode()` or `identityHashCode()` to a database as a persistent ID, and do not use it as a shared inter-process key without an explicit algorithm and data contract. Use a stable business domain ID for that purpose.

## 8. How to Check When Reviewing a Class

Before accepting a class that overrides `equals()`:

1. **Read the equality definition in plain words:** "Two instances are equal when ..."; specify clearly whether that means same value or same entity by ID.
2. **Inspect the list of fields compared in `equals()`:** is namespace, tenant, or entity type missing? Were display names, caches, or volatile state accidentally included?
3. **Check hash across equal pairs:** every pair with `a.equals(b) == true` must give `a.hashCode() == b.hashCode()`. The hash field set does not have to be syntactically identical, but must be **logically compatible**.
4. **Check null, different types, same-object reference:** `equals(null)` is `false`, `equals(this)` is `true`; symmetry and transitivity are not broken.
5. **Check stability:** after putting the object into a `HashSet` or using it as a `HashMap` key, are fields affecting equality/hash modified?
6. **Check with real collections:** adding two equal objects to a `HashSet` must yield a single unique element; `HashMap.get(equalKey)` must return the stored value. Test with differing fields and hash collisions where appropriate.
7. **Review generated code:** IDEs, Lombok, and records help avoid typos, but do not understand business rules automatically; always review which fields are included/excluded.

Example of minimal checks (snippet applicable to the `CorrectKey` class above):

```java
CorrectKey x = new CorrectKey("T1", "D1", "A");
CorrectKey y = new CorrectKey("T1", "D1", "B");
CorrectKey z = new CorrectKey("T2", "D1", "A");

assert x.equals(y);
assert y.equals(x);
assert x.hashCode() == y.hashCode();
assert !x.equals(z);
assert !x.equals(null);
```

`assert` statements are only executed by the JVM when assertions are enabled (for instance running `java -ea ...`); in automated tests, use an appropriate testing assertion framework. This is an illustrative snippet placed in a scope where `CorrectKey` can be referenced, not a standalone Java program.

## 9. Self-Check

**Question 1.** `a.equals(b)` returns `true`, yet `a.hashCode()` and `b.hashCode()` differ. What is wrong and where does it break?

**Answer:** The class violates the `hashCode()` contract. `HashSet` may contain two equivalent elements; `HashMap.get(b)` may fail to find the value stored using `a`.

**Question 2.** Two objects are unequal yet share the same hash. Is that necessarily a bug?

**Answer:** No. Hash collisions are allowed; good hashes reduce collisions for performance. Hash structures still use equality key comparisons to resolve them.

**Question 3.** If neither method is overridden and the default `Object.equals/hashCode` is used, does that violate the contract?

**Answer:** No. Because default `Object.equals` only treats the exact same instance as equal, the default hash is compatible with identity equality. Problems usually arise when overriding `equals()` to treat two different instances as equal without overriding a compatible hash.

**Question 4.** Can `hashCode() { return 42; }` be used for all objects?

**Answer:** Contractually, yes: every equal pair is guaranteed to have the same hash. However, hash structure performance can degrade significantly because all keys pile into the same hash, so in practice compute hashes from meaningful equality components.

**Question 5.** A class has `equals()` based on `id` and `hashCode()` based on `(id, lastModified)`. What bug do two instances with the same ID but different timestamps cause?

**Answer:** `equals()` says they are equal while their hashes may differ, violating the mandatory condition. The `lastModified` field must not affect the hash if `equals()` ignores it.

**Question 6.** When overriding `hashCode()` while keeping the default `equals()`, is the contract automatically violated?

**Answer:** Not automatically. Identity equality only requires the same instance to return a consistent hash within an execution while equality information does not change. However, mutating hash-relevant state while the object serves as a key can still break lookups; and once content-based equality is designed, both must be implemented in sync.

---

**Takeaway:** `equals()` defines **who is equal to whom**; `hashCode()` must produce the same value for those pairs. Overriding `equals()` usually forces you to override `hashCode()` so you do not break the contract inherited from `Object`. Write and review both methods as a pair, pick the field set by semantics, keep those components stable, and test in practice using `HashSet`/`HashMap`.
