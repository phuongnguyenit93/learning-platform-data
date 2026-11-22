# Practice: Fixing a Class That Has `equals(MyType)` Without Overriding `equals(Object)`

## 1. The Problem to Fix

You receive a Java class representing an identifier key for a book edition. Two objects with the same book code and same revision must be considered equal by value. The class currently has `equals(BookKey)`, and sometimes testing `a.equals(b)` directly returns `true`. However, when passing those objects to an API accepting `Object` or placing them into a `List` or `Set`, the comparison fails.

The goal is to **fix the object equality contract** so that calls through type `Object` and collection APIs all receive proper value comparison. This is a classic bug at the boundary between *overloading* and *overriding*.

After completing this practice, you will be able to:
- Inspect a method signature and recognize that `equals(MyType)` **does not** override `Object.equals(Object)`.
- Explain why a direct call looks right while `List.contains` and `HashSet.contains` can fail.
- Properly override `public boolean equals(Object obj)` and `public int hashCode()`, using `@Override` so the compiler checks them.
- Verify the basic properties of `equals` along with using a value key in hash collections.
- Identify remaining bugs related to `null`, symmetry, subclassing, and mutable fields.

## 2. Analyzing the Buggy Code: Same Name Is Not Enough to Override

Here is the buggy class, looking specifically at the components that govern comparison:

```java
import java.util.Objects;

final class BrokenBookKey {
    private final String code;
    private final int revision;

    BrokenBookKey(String code, int revision) {
        this.code = Objects.requireNonNull(code);
        this.revision = revision;
    }

    // Overload! The parameter is BrokenBookKey, not Object.
    public boolean equals(BrokenBookKey other) {
        return other != null
                && revision == other.revision
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(code, revision);
    }
}
```

Read both signatures carefully:

```java
public boolean equals(BrokenBookKey other) // New method: overload
public boolean equals(Object obj)          // Signature needed to override from Object
```

The second method here is **the required signature**, not a method currently present in the buggy class. Because the class only declares `equals(BrokenBookKey)`, it still inherits `Object.equals(Object)`, meaning that when a call is bound to the `equals(Object)` signature, default equality is **reference identity**.

Overriding `hashCode()` in the buggy class deliberately makes the example clearer: **fixing only the hash code cannot substitute for overriding `equals(Object)`**. Two objects with different references that share the same value and hash code can still be compared as unequal.

### Why do the two calls select different methods?

```java
BrokenBookKey a = new BrokenBookKey("JAVA-21", 2);
BrokenBookKey b = new BrokenBookKey("JAVA-21", 2);
Object viewedAsObject = b;

boolean direct = a.equals(b);               // Selects equals(BrokenBookKey)
boolean viaObject = a.equals(viewedAsObject); // Selects equals(Object)
```

- In `a.equals(b)`, the static (*compile-time*) type of `b` is `BrokenBookKey`; the compiler chooses the overload taking `BrokenBookKey` because it is more specific.
- In `a.equals(viewedAsObject)`, the static type of the argument is `Object`; the compiler selects the `equals(Object)` signature, and at runtime there is no override on `BrokenBookKey`, so `Object.equals(Object)` executes.
- Selecting among **overloads** happens at compile time; selecting the **override** implementation matching the receiver object happens at runtime. The two mechanisms do not replace each other.
- A test that only calls `a.equals(b)` with two variables typed as `BrokenBookKey` can hide the bug.

A quick way to spot the error: try putting `@Override` in front of `equals(BrokenBookKey other)`. The compiler reports an error because this method does not override any method in the superclass. **Do not fix that error by removing `@Override`; you must change the signature properly to `equals(Object)`.**

## 3. Minimal and Correct Fix

For a **final** class whose equality semantics depend on the two fields `code` and `revision`, the standard implementation is:

```java
import java.util.Objects;

public final class BookKey {
    private final String code;
    private final int revision;

    public BookKey(String code, int revision) {
        this.code = Objects.requireNonNull(code, "code");
        this.revision = revision;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof BookKey other)) {
            return false;
        }
        return revision == other.revision
                && code.equals(other.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(code, revision);
    }
}
```

Save the file above as `BookKey.java` and compile with `javac BookKey.java` on JDK 17 or higher. This is a complete library class **without a `main` method**, so by itself it prints nothing to stdout.

Meaning of each part:

1. `@Override` confirms with the compiler that the signature is truly `equals(Object)`. If the parameter type or visibility is mistyped, the error is caught early.
2. `this == obj` quickly recognizes the exact same reference; this branch always returns `true`, preserving *reflexivity*.
3. `obj instanceof BookKey other` rejects `null` and objects of other types; `other` is a Java 16+ pattern variable, compatible with Java 17.
4. Compare only **the fields constituting value identity**: same `revision` and same `code`. Because the constructor rejects `null`, `code.equals(other.code)` is safe.
5. `hashCode()` uses **the exact same fields checked in `equals`**. If `a.equals(b)` is `true`, `a.hashCode() == b.hashCode()` must hold.
6. Declaring the class `final` ensures no subclass adds fields or changes equality rules, reducing the risk of violating symmetry.

If the exercise specifically requires keeping `equals(BookKey)` for legacy source compatibility, that overload can **delegate** to the canonical check path:

```java
public boolean equals(BookKey other) {
    return equals((Object) other);
}
```

The snippet above is an optional supplementary method **inside a class that already overrides `equals(Object)`**. The `(Object)` cast is intentional to select the right overload; keeping `equals(BookKey)` is not required in new designs, and duplicating equality logic in two places should be avoided.

## 4. Program Demonstrating the Bug and the Result After Fixing

The example below is **a standalone program** with two nested classes: one still suffering from the overload and one fixed. It tests calls via `Object`, `List.contains`, `HashSet.contains`, and hash codes.

Create the file `EqualsOverloadRepairDemo.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class EqualsOverloadRepairDemo {
    static final class BrokenBookKey {
        private final String code;
        private final int revision;

        BrokenBookKey(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        // Wrong target: overload, not an override of Object.equals(Object).
        public boolean equals(BrokenBookKey other) {
            return other != null
                    && revision == other.revision
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    static final class FixedBookKey {
        private final String code;
        private final int revision;

        FixedBookKey(String code, int revision) {
            this.code = Objects.requireNonNull(code);
            this.revision = revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof FixedBookKey other)) return false;
            return revision == other.revision
                    && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, revision);
        }
    }

    public static void main(String[] args) {
        BrokenBookKey brokenA = new BrokenBookKey("JAVA-21", 2);
        BrokenBookKey brokenB = new BrokenBookKey("JAVA-21", 2);
        Object brokenAsObject = brokenB;
        Set<BrokenBookKey> brokenSet = new HashSet<>();
        brokenSet.add(brokenA);

        System.out.println("BROKEN");
        System.out.println("typedEquals=" + brokenA.equals(brokenB));
        System.out.println("objectEquals=" + brokenA.equals(brokenAsObject));
        System.out.println("listContains=" + List.of(brokenA).contains(brokenB));
        System.out.println("setContains=" + brokenSet.contains(brokenB));
        System.out.println("sameHash=" + (brokenA.hashCode() == brokenB.hashCode()));

        FixedBookKey fixedA = new FixedBookKey("JAVA-21", 2);
        FixedBookKey fixedB = new FixedBookKey("JAVA-21", 2);
        FixedBookKey different = new FixedBookKey("JAVA-21", 3);
        Object fixedAsObject = fixedB;
        Set<FixedBookKey> fixedSet = new HashSet<>();
        fixedSet.add(fixedA);

        System.out.println("FIXED");
        System.out.println("typedEquals=" + fixedA.equals(fixedB));
        System.out.println("objectEquals=" + fixedA.equals(fixedAsObject));
        System.out.println("listContains=" + List.of(fixedA).contains(fixedB));
        System.out.println("setContains=" + fixedSet.contains(fixedB));
        System.out.println("sameHash=" + (fixedA.hashCode() == fixedB.hashCode()));
        System.out.println("differentRevision=" + fixedA.equals(different));
        System.out.println("equalsNull=" + fixedA.equals(null));
    }
}
```

Run in the directory containing the file:

```bash
javac EqualsOverloadRepairDemo.java
java EqualsOverloadRepairDemo
```

Exact stdout (the program uses only deterministic values):

```text
BROKEN
typedEquals=true
objectEquals=false
listContains=false
setContains=false
sameHash=true
FIXED
typedEquals=true
objectEquals=true
listContains=true
setContains=true
sameHash=true
differentRevision=false
equalsNull=false
```

**Explaining the results before the fix:** `brokenA.equals(brokenB)` uses the overload and thus returns `true`. Conversely, `brokenA.equals(brokenAsObject)` calls the inherited `equals(Object)` signature and returns `false`. Collection APIs check equality through the `Object.equals(Object)` interface, so the second object—even with the same value—is not found. `sameHash=true` only shows the two hash codes are equal; it does not make `equals(Object)` true by itself.

**Explaining the results after the fix:** `FixedBookKey.equals(Object)` is dispatched even when the argument or variable is viewed through type `Object`. Both `List.contains` and `HashSet.contains` can find an object with a different reference that is equal by value. Hash codes agree with the comparison; different `revision` values are not equal; `null` is not equal to a valid object.

In `HashSet`, the hash code first helps determine where to look, while `equals(Object)` confirms whether two keys are truly equal. Having the same hash code **does not mean** two elements are equal; *hash collisions* are valid. Having a correct `equals` with a broken `hashCode` can also cause lookup failures because two equal objects are placed into different buckets.

## 5. The `equals(Object)` and `hashCode()` Contract to Preserve

For non-`null` references, the core contract of `equals` includes:

| Property | Requirement | Suggested check |
| --- | --- | --- |
| Reflexive | `x.equals(x)` is `true` | Compare an instance with itself |
| Symmetric | `x.equals(y)` and `y.equals(x)` give the same result | Check both directions, including with subclasses if inheritance is allowed |
| Transitive | If `x=y` and `y=z`, then `x=z` in `equals` semantics | Create three instances with the same value fields |
| Consistent | Result stays the same while state used for equality does not change | Call multiple times before modifying data |
| Against null | `x.equals(null)` is `false` | Check explicitly via the `Object` signature |

For `hashCode`, the mandatory rule is **two objects that are equal according to `equals` must have equal hash codes** within the same state observation. The converse **is not required**. If two objects are not equal, their hash codes may still collide.

In value key classes, prefer `final` fields and immutable value types. When using an object as a `HashSet` element or `HashMap` key, **do not mutate fields participating in `equals/hashCode` while the object is stored**: otherwise, the old hash bucket and the new hash code can fall out of sync, causing lookups to fail even with the exact same reference.

## 6. Checklist for Fixing Real Classes in a Project

Apply directly to a class that currently has `equals(MyType)`:

1. **Define equality semantics.** Ask "When are two instances considered to have the same value?" and explicitly list the participating fields. Do not compare every field by default if some fields are only caches, timestamps, or metadata unrelated to identity.
2. **Replace the wrong signature.** Write `@Override public boolean equals(Object obj)`; verify the name `equals`, `Object` from `java.lang.Object`, return type `boolean`, and `public` visibility.
3. **Handle same reference, null, and other types.** Return `true` quickly for `this == obj`, and return `false` when the object is not of the value type.
4. **Compare content according to field type.** Primitive types use `==`; objects use `Objects.equals(a, b)` when nullable or `a.equals(b)` when guaranteed non-null; arrays require `Arrays.equals` or `Arrays.deepEquals` depending on data structure, not reference comparison when value comparison is needed.
5. **Override `hashCode()` in sync.** Same set of fields and same comparison rules; for arrays, consider `Arrays.hashCode`/`Arrays.deepHashCode` accordingly.
6. **Audit callers.** Search for call sites of `equals(MyType)`. When the overloaded API is not needed, remove that method; if it must be kept for compatibility, have it delegate to `equals(Object)` and avoid maintaining two separate algorithms.
7. **Test under type `Object` and through collections.** Test `Object ref = b; a.equals(ref)`, `List.contains(b)`, `HashSet.contains(b)`, and `HashMap.get(b)` (after adding an equal-value key). Do not only test `a.equals(b)` with two concretely typed variables.
8. **Verify bidirectional contracts and data variants.** Include self, equal-value instance, instance differing in one field, `null`, object of another type, and subclasses if inheritance is allowed.

Manual test example requiring no external libraries, using the same `BookKey` class from section 3:

```java
BookKey a = new BookKey("JAVA-21", 2);
BookKey b = new BookKey("JAVA-21", 2);
BookKey c = new BookKey("JAVA-21", 2);
BookKey other = new BookKey("JAVA-21", 3);

if (!a.equals(a)) throw new AssertionError("reflexive");
if (!a.equals(b) || !b.equals(a)) throw new AssertionError("symmetric");
if (!(a.equals(b) && b.equals(c) && a.equals(c))) {
    throw new AssertionError("transitive");
}
if (a.equals(other) || a.equals(null) || a.equals("JAVA-21")) {
    throw new AssertionError("non-equal case");
}
if (a.hashCode() != b.hashCode()) throw new AssertionError("hash consistency");
if (!java.util.Set.of(a).contains(b)) {
    throw new AssertionError("collection lookup");
}
```

This is **a verification snippet to place inside a method** (such as `main` or a test), not a standalone program; the checks use `AssertionError` directly so they run even when the JVM does not have the `-ea` flag enabled.

## 7. Choices and Notable Pitfalls

### `instanceof`, `getClass()`, and inheritance

The `BookKey` example is a `final` class; the `instanceof BookKey` check matches the scope of instances of that class. If a class is **not final** and a subclass adds fields, comparisons between superclass and subclass easily break symmetry or transitivity. You must choose and test a clear inheritance policy:

- `getClass() == obj.getClass()` only accepts **the exact same runtime class**, often suitable for strict type-distinguishing equality, though it rejects subclasses or proxies.
- `instanceof` accepts subtypes; you must ensure subclasses do not alter comparison logic in a way that violates the contract.
- Marking value classes `final` or choosing a consistent equality design is usually easier to control. Do not blindly replace `getClass` with `instanceof` in polymorphic code without evaluating the consequences.

### Other confusion with overloading

- `equals(MyType)` and `equals(Object)` can coexist, but overloading often causes surprises because results vary depending on a variable's static type. If both are kept, ensure they share the same rules.
- `equals(Object)` without `@Override` still works if the signature is exact; `@Override` catches signature mistakes and should always be used.
- Overriding `equals(Object)` while forgetting `hashCode()` can cause `HashMap`/`HashSet` to malfunction on equal-value objects.
- Comparing `String` with `==` checks reference identity, not content. For book edition codes, use `String.equals` or `Objects.equals`.
- `Objects.equals(a,b)` only calls `equals(Object)` per the contract, so it cannot magically fix a class that only has `equals(MyType)`.
- Do not use `System.identityHashCode` to build `hashCode` for a class with value equality.

### When to use `record`?

If the goal is an immutable data-carrier class with no special rules and whose components naturally form its identity, Java 17 provides `record`:

```java
public record BookKeyRecord(String code, int revision) {
    public BookKeyRecord {
        java.util.Objects.requireNonNull(code, "code");
    }
}
```

A record automatically generates `equals(Object)` and `hashCode()` from the declared components, helping prevent forgotten overrides. This is a new design choice, **not a mandatory fix for an existing class** (especially if inheritance from another class or specific API/serialization requirements exist).

## 8. Self-Check Questions and Mini Exercise

1. **Why was `x.equals(y)` `true` while `((Object)x).equals(y)` was `false` before the fix?** Because the first call used the `equals(MyType)` overload, whereas the second call only saw `equals(Object)` and the class had not overridden it.
2. **Is merely changing `equals(MyType)` to `equals(Object)` enough?** No; you must ensure the value comparison logic is correct, `hashCode()` follows the same fields, and the contract properties are verified.
3. **If two objects have equal hash codes, must `equals` return `true`?** No. Hash collisions are permitted for unequal objects.
4. **Why is adding `@Override` a good debugging step?** The compiler verifies that the method actually overrides a superclass method, thereby catching the wrong `equals(MyType)` signature.
5. **If `revision` changes from 2 to 3, what problem can an object inside a `HashSet` encounter?** Its hash code and equality change while the object is already sitting in an old bucket; fields involved in equality should be immutable.

**Extended practice:** Add a `region` field to `BookKey` yourself and decide whether region forms part of a book edition's identity. Update `equals(Object)` and `hashCode()` together, write at least two objects differing in `region` to demonstrate your chosen rule. Test via an `Object` variable and `HashSet.contains`, then reverse your decision on `region` and observe the difference.

**Key takeaway:** When value comparison of Java objects is needed in generic code and collections, **the mandatory signature is `public boolean equals(Object)`**. `equals(MyType)` is only an overload; a single direct call succeeding does not prove that `Object`'s contract has been overridden.

## References

- [Java SE 21 — `Object.equals(Object)` and `Object.hashCode()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html).
- [Java SE 21 — `Set` and element conditions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).
- [Java SE 21 — `HashSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).
- [Java Language Specification — Overriding and hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8).
- [Java Language Specification — Method invocation: method lookup and selection](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12).