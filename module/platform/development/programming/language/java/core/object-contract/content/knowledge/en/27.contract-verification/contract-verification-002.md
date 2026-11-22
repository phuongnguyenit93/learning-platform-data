# Testing Reflexivity, Symmetry, and Transitivity of `equals()` in Java

`equals(Object)` is a method on `java.lang.Object`, overridden by classes when they need to express the concept of **two objects being equal in value**. If not overridden, the default `Object.equals()` behavior is equivalent to comparing reference identity (`==`). When overriding, a class must follow the `equals()` contract so comparison results remain stable and compatible with structures like `HashSet` and `HashMap`.

The three properties to test in this lesson are **reflexivity**, **symmetry**, and **transitivity**. Testing with both equal-value and different-value objects, along with cases at inheritance type boundaries, is more important than only checking a single pair of objects.

## 1. Exact Statement of the Three Properties

For non-`null` object references `x`, `y`, `z`:

| Property | Mandatory rule | Verification question |
| --- | --- | --- |
| **Reflexive** | `x.equals(x) == true` | Does an object equal itself? |
| **Symmetric** | `x.equals(y) == y.equals(x)` | Does reversing the comparison order change the result? |
| **Transitive** | If `x.equals(y)` and `y.equals(z)` are both `true`, then `x.equals(z)` must be `true` | Is a chain of equal objects consistent? |

Symmetry means **both directions yield the same Boolean value**, even when both are `false`. Transitivity is an implication: it only requires `x.equals(z)` to be `true` when **both premise conditions** are `true`. Do not misinterpret it as "if `x` does not equal `y` and `y` does not equal `z`, then `x` must not equal `z`".

Two equal-value objects do not have to share the same reference: `new Key("A", 1)` and another `new Key("A", 1)` object can satisfy `equals() == true` while `==` is `false`.

The `equals()` contract also specifies **consistency** when the information used for comparison has not changed and `x.equals(null) == false` for any non-`null` `x`. When `equals()` returns `true`, the `hashCode()` of both objects must also be equal; the converse is not required to hold. Therefore, good tests typically check these related conditions as well.

## 2. Designing the Test Dataset

You should not just create one object and check `a.equals(a)`; that check does not touch comparison behavior between **two independent instances**. For a value key class `Key(code, version)`, there should be at least:

- Three instances with **distinct references but equal values**: `a = Key("A", 1)`, `b = Key("A", 1)`, `c = Key("A", 1)`. This group forms the chain `a = b`, `b = c` to genuinely test transitivity.
- One instance differing in the first or second property, such as `Key("A", 2)` and `Key("B", 1)`, to ensure comparison also returns `false` when appropriate.
- `null` cases and boundary values (empty string, 0, negative numbers) if permitted by the data domain; for **non-final** classes, include relevant subtypes.
- If multiple fields make up object identity, vary **one field at a time** between two samples to catch fields forgotten in `equals()`.

Tests cannot prove a method is correct for all infinite inputs, but they validate the rules on an intentional sample set. With a small set, iterating over all **pairs** and **triples** significantly increases the chance of detecting violations compared to a few isolated assertions.

## 3. Standalone, Runnable Java 17+ Example

Create the file **`EqualsContractDemo.java`** with the following content. The `Key` class is an immutable value type, declared `final` so subclasses cannot arise to alter the definition of equality. The `NearNumber` part intentionally violates the contract to illustrate a transitivity bug.

```java
import java.util.List;
import java.util.Objects;

public class EqualsContractDemo {
    static final class Key {
        private final String code;
        private final int version;

        Key(String code, int version) {
            this.code = Objects.requireNonNull(code);
            this.version = version;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Key other)) {
                return false;
            }
            return version == other.version && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return 31 * code.hashCode() + version;
        }
    }

    // Intentionally violates transitivity: within 1 unit is "equal".
    static final class NearNumber {
        private final int number;

        NearNumber(int number) {
            this.number = number;
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof NearNumber other
                    && Math.abs((long) number - other.number) <= 1;
        }

        @Override
        public int hashCode() {
            return 0; // Same hash is valid, but lookup performance may be poor.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void verify(List<Key> values) {
        Key a = values.get(0);
        Key b = values.get(1);
        Key c = values.get(2);

        check(a != b && b != c && a != c,
                "Fixtures must be three distinct instances");
        check(a.equals(b) && b.equals(c),
                "Fixtures must include an equal chain");
        check(!a.equals(values.get(3)), "Version difference not detected");
        check(!a.equals(values.get(4)), "Code difference not detected");
        System.out.println("PASS fixtures");

        for (Key x : values) {
            check(x.equals(x), "Reflexive property failed");
        }
        System.out.println("PASS reflexive");

        int pairCount = 0;
        for (Key x : values) {
            for (Key y : values) {
                pairCount++;
                check(x.equals(y) == y.equals(x), "Symmetry failed");
            }
        }
        System.out.println("PASS symmetric (" + pairCount + " pairs)");

        int tripleCount = 0;
        for (Key x : values) {
            for (Key y : values) {
                for (Key z : values) {
                    tripleCount++;
                    if (x.equals(y) && y.equals(z)) {
                        check(x.equals(z), "Transitivity failed");
                    }
                }
            }
        }
        System.out.println("PASS transitive (" + tripleCount + " triples)");

        for (Key x : values) {
            check(!x.equals(null), "Null comparison failed");
            for (Key y : values) {
                if (x.equals(y)) {
                    check(x.hashCode() == y.hashCode(),
                            "Equal objects must share hashCode");
                }
            }
        }
        System.out.println("PASS null/hashCode");
    }

    public static void main(String[] args) {
        List<Key> values = List.of(
                new Key("A", 1),
                new Key("A", 1),
                new Key("A", 1),
                new Key("A", 2),
                new Key("B", 1));

        verify(values);

        NearNumber x = new NearNumber(1);
        NearNumber y = new NearNumber(2);
        NearNumber z = new NearNumber(3);
        check(x.equals(y) && y.equals(z) && !x.equals(z),
                "Broken example must violate transitivity");
        System.out.println("Broken transitivity: "
                + x.equals(y) + ", " + y.equals(z) + ", " + x.equals(z));
    }
}
```

Compile with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 EqualsContractDemo.java
java EqualsContractDemo
```

Expected stdout output:

```text
PASS fixtures
PASS reflexive
PASS symmetric (25 pairs)
PASS transitive (125 triples)
PASS null/hashCode
Broken transitivity: true, true, false
```

### Explaining Each Verification Group

**`PASS fixtures`:** the three objects `a`, `b`, `c` have the same `code/version` but each object is created with a separate `new` statement. Verifying this premise is especially useful: without three equal objects, the transitivity loop could "pass" without ever inspecting a chain of distinct-reference objects.

**`PASS reflexive`:** the loop calls `x.equals(x)` for all 5 samples, so an override returning false when an object meets itself will be caught.

**`PASS symmetric (25 pairs)`:** 5 × 5 **ordered** pairs are checked with `x.equals(y) == y.equals(x)`. For any pair where reversing the order causes one side to return `true` and the other to return `false`, an `AssertionError` is thrown. Including different-value pairs helps catch asymmetric comparisons caused by subclasses or wrong property comparisons.

**`PASS transitive (125 triples)`:** 5 × 5 × 5 **ordered** triples are examined. Whenever `x.equals(y) && y.equals(z)` is true, the test requires `x.equals(z)` to be true. The `if` condition is the **logical definition of the contract**, not "skipping" the check; `fixtures` has already ensured there is a positive distinct-reference chain to test.

**`PASS null/hashCode`:** tests `x.equals(null)` for all samples and checks that every equal pair shares the same `hashCode()`. These are two supporting conditions, not replacements for the three core rules.

**`Broken transitivity: true, true, false`:** `NearNumber(1)` is considered equal to `NearNumber(2)`, `NearNumber(2)` equals `NearNumber(3)`, yet `NearNumber(1)` does not equal `NearNumber(3)`. "Within a tolerance of 1" is a **non-transitive relation**, and therefore unsuitable as a definition of `equals()`. Returning a constant `0` in `hashCode()` here avoids adding a `hashCode` violation; it still cannot fix the transitivity bug.

## 4. Situations Where `equals()` Easily Violates the Contract

### 4.1. Asymmetry Between Parent and Subclass

A familiar bug: the parent class allows comparison with any subclass via `instanceof Parent`, whereas the subclass only accepts the subclass type itself (for instance, because it adds a `color` field).

```java
// Illustrates two condition snippets in equals(); not a standalone program.
// Parent.equals:
return other instanceof Parent p && this.id == p.id;

// Child.equals:
return other instanceof Child c
        && super.equals(other)
        && this.color.equals(c.color);
```

If `p` is `Parent(id=7)` and `c` is `Child(id=7, color="red")`, then `p.equals(c)` can be `true` while `c.equals(p)` is `false`. This is a **symmetry violation**. A simple way to avoid this when a class is designed as a value type that does not need inheritance: declare the class `final`. If inheritance exists, the type comparison policy must be designed carefully (for example, consistently using `getClass()` as designed) and tested in every direction across concrete types.

### 4.2. Using "Approximate Equality" as `equals()`

Rounding, comparing with an epsilon, or distance thresholds easily break transitivity. When approximate floating-point comparison is needed, place the comparison in a **separate method** such as `approximatelyEqual`, stating the tolerance explicitly; do not default to using it as `Object.equals()`. For `double`, you also need to clearly define the meaning of `NaN`, `+0.0`, and `-0.0`, and use a comparison strategy consistent with the hash function.

### 4.3. Missing a Field or Depending on Mutable Data

If `equals()` depends on `id` and `version` but only compares `id`, two objects that should differ are treated as equal. If `equals()` relies on mutable fields, the comparison result between the same two objects can change when state changes. The consistency contract only requires results to remain stable **when the relevant data has not changed**; however, using an object as a `HashMap` key or `HashSet` element and then mutating fields involved in `equals/hashCode` can cause lookups to fail.

### 4.4. Testing the Wrong Direction or Wrong Condition

- Checking only `assertTrue(a.equals(b))` does not check `b.equals(a)`. You must check **both directions**, especially when objects have different runtime types.
- Repeating `x=y=z` with the same reference does not prove the test covered transitivity across three separate instances.
- Do not require `x.equals(z)` when `x.equals(y)` or `y.equals(z)` is `false`; the transitivity premise does not hold.
- `Objects.equals(a,b)` helps compare safely when `null` is possible, but this utility itself **cannot fix** an asymmetric or non-transitive `equals()` on the objects.
- Do not use `assertEquals(a,b)` alone to conclude symmetry: the framework executes one comparison call without automatically checking both directions as required by the contract.

## 5. Integrating into a Project Test Suite

In JUnit 5, the three properties can be expressed as separate tests using the same fixture (for example, `List<Key> samples`), following the same approach as the pure Java loops above:

```java
// Illustrative snippet inside a JUnit 5 test class that already has samples.
@Test
void reflexive() {
    for (Key x : samples) {
        assertTrue(x.equals(x));
    }
}

@Test
void symmetric() {
    for (Key x : samples) {
        for (Key y : samples) {
            assertEquals(x.equals(y), y.equals(x));
        }
    }
}

@Test
void transitive() {
    for (Key x : samples) {
        for (Key y : samples) {
            for (Key z : samples) {
                if (x.equals(y) && y.equals(z)) {
                    assertTrue(x.equals(z));
                }
            }
        }
    }
}
```

This is an **illustrative snippet**; it requires importing `org.junit.jupiter.api.Test` and assertions from `org.junit.jupiter.api.Assertions`, declaring `Key`/`samples` in the test class, and configuring JUnit 5 in the project. The program in Section 3 is a **complete example needing no external libraries** so it can be compiled and run immediately.

For real-world classes with many input shapes, increase coverage using parameterized tests or data generation (*property-based testing*): check independently constructed objects, all variations of identity-defining fields, boundary values, subtypes (if any), and repeated calls when state does not change. Always include at least one fixture ensuring two independent instances **are expected to be equal**, and one independent triple **whose transitivity premise holds**; otherwise, many assertions can pass vacuously.

## 6. Checklist When Reviewing `equals()`

1. Does `x.equals(x)` always return `true` for `x != null`?
2. Do `x.equals(y)` and `y.equals(x)` always return the same result, even when the two objects belong to types in an inheritance relationship?
3. When `x.equals(y)` and `y.equals(z)` are `true`, is `x.equals(z)` `true`? Have **three distinct-reference objects** been tested?
4. Does `x.equals(null)` return `false`, is the result stable when data does not change, and do equal pairs have the same `hashCode()`?
5. Does the fixture set cover both **equal** and **unequal** cases, single-property variations of each key attribute, and domain boundary cases?

A reliable `equals()` test must catch both "two equal objects treated as unequal" bugs and logical violations of the equality relation; at the same time, it must not confuse transitivity with approximate comparison.
