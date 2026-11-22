# Reflexivity of `equals(Object)` in Java

## 1. What Is Reflexivity?

In the `Object.equals(Object)` contract, **reflexivity** requires that for any non-`null` reference `x`, the call `x.equals(x)` must return `true`.

```text
For all x != null: x.equals(x) == true
```

Here, both sides `x` refer to **the exact same existing object**. This is the minimum rule every custom `equals` implementation must honor: an object must never claim that it is not equal to itself.

Points to distinguish:

- `x == x` is always `true` for a reference `x`: the `==` operator compares reference identity.
- `x.equals(x)` **must** be `true` by contract, though the `equals` method can be overridden incorrectly by a programmer.
- Two **different-reference** objects can still be logically equal if the class defines `equals` based on meaningful properties. That is a different question from an object being equal to itself.
- `null` is not an object on which a method can be called: `null.equals(null)` throws `NullPointerException`. The reflexivity contract is stated only for non-`null` references.

## 2. Why Does This Rule Exist?

`equals` represents a logical equality relation defined by a class. If that relation allowed `x.equals(x) == false`, even the simplest comparison case would no longer be reliable. Checks, algorithms, and APIs that rely on object equality are built on the assumption that an `equals` implementation adheres to the standard contract.

The default `Object.equals` implementation uses identity equality: only the exact same object is equal. Therefore, it is already reflexive. When overriding it for value-based comparison, the developer must **preserve** that property.

Reflexivity does not mean all objects of the same class are equal. Nor does it require all data fields to be non-`null`, immutable, or hold a specific value; every object must equal itself.

## 3. Correct `equals` Implementation and Verification in Java 17

The example below places the `this == other` branch at the start of the method. This is a clear and typically efficient way to ensure that when two references point to the same object, it returns `true` immediately.

Create the file **`ReflexivityDemo.java`**:

```java
import java.util.Objects;

public class ReflexivityDemo {
    static final class Person {
        private final String name;
        private final int age;

        Person(String name, int age) {
            this.name = name;
            this.age = age;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true; // Same object: always equal to itself.
            }
            if (!(other instanceof Person person)) {
                return false; // Also covers other == null.
            }
            return age == person.age
                    && Objects.equals(name, person.name);
        }

        @Override
        public int hashCode() {
            return Objects.hash(name, age);
        }
    }

    static final class BrokenPerson {
        private final String name;

        BrokenPerson(String name) {
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return false; // WRONG: violates reflexivity.
            }
            return other instanceof BrokenPerson person
                    && Objects.equals(name, person.name);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(name);
        }
    }

    public static void main(String[] args) {
        Person p = new Person(null, 20);
        Person q = new Person(null, 20);

        System.out.println("p == p: " + (p == p));
        System.out.println("p.equals(p): " + p.equals(p));
        System.out.println("p.equals(q): " + p.equals(q));
        System.out.println("p.equals(null): " + p.equals(null));

        BrokenPerson broken = new BrokenPerson("An");
        System.out.println("broken.equals(broken): "
                + broken.equals(broken));
        System.out.println("Objects.equals(broken, broken): "
                + Objects.equals(broken, broken));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ReflexivityDemo.java
java ReflexivityDemo
```

Exact output:

```text
p == p: true
p.equals(p): true
p.equals(q): true
p.equals(null): false
broken.equals(broken): false
Objects.equals(broken, broken): true
```

Case-by-case explanation:

1. `p == p` is `true` because both sides are the same reference.
2. `p.equals(p)` is `true` because `this == other` returns immediately, satisfying reflexivity.
3. `p.equals(q)` is also `true`, **but because two distinct objects have the same `name` and `age`**. This belongs to how the class defines value equality; it is not a reflexivity check. The example intentionally uses `name == null` to show that a `null` field does not break reflexivity.
4. `p.equals(null)` is `false` via the `instanceof` check. This differs from calling a method on a `null` reference.
5. `broken.equals(broken)` is `false` due to the faulty branch in `BrokenPerson.equals`, proving that an override can genuinely break the contract.
6. `Objects.equals(broken, broken)` is still `true`, because the `Objects.equals(a, b)` utility checks `a == b` before calling `a.equals(b)`. **Do not use `Objects.equals(x, x)` as the sole test to detect a non-reflexive `equals`**: that check can mask the bug.

Both classes in the example override `hashCode` using the compared fields to maintain the rule regarding equal objects. However, having a reasonable `hashCode` **cannot rescue** an `equals` implementation that already violates reflexivity.

## 4. Is Writing `if (this == other) return true;` Mandatory?

**Not syntactically mandatory.** What is mandatory is the **behavioral outcome**: `x.equals(x)` must be `true`.

For example, if the rest of `equals` compares all fields completely and accurately against themselves, the method can still be reflexive without the first shortcut branch. However, the `this == other` branch offers three clear benefits:

- Makes the contract easy to spot when reading the code.
- Avoids walking through property comparisons when both references are already the same.
- Reduces the risk of self-comparison falling into faulty handling branches.

This branch does not replace checking types, properly comparing fields when two objects are distinct, or obeying other clauses of the `equals` contract. A method can be reflexive yet still broken in other respects.

## 5. Common Mistakes and How to Test

**Mistake 1 — returning `false` when both references are the same.** The `BrokenPerson` example above inverts the required condition. The direct fix is to return `true` when `this == other`.

**Mistake 2 — using `==` instead of `equals` and concluding the entire method is correct.** `x == x` only checks reference identity. It does not test the `equals` implementation, so a class with a broken `equals` still passes `x == x`.

**Mistake 3 — testing indirectly through an optimized utility.** `Objects.equals(x, x)` returns `true` immediately when both references are identical. Call `x.equals(x)` directly to test the class's contract.

**Mistake 4 — confusing `null` with a special object.** You cannot call `null.equals(null)`; do not include `null` in the domain of the reflexivity statement. If you need to compare two potentially `null` references, `Objects.equals(a, b)` is a convenient API, but that serves a different purpose.

**Mistake 5 — making the self-comparison condition depend on data.** For instance, returning `true` only when the `name` field is non-`null` is wrong: an object with `name == null` must still equal itself.

You can write a short regression check without needing a testing library:

```java
static void checkReflexive(Object value) {
    Objects.requireNonNull(value, "value");
    if (!value.equals(value)) {
        throw new AssertionError("equals violates reflexivity");
    }
}
```

This is an **illustrative method snippet**, placed inside an appropriate Java class and called with multiple representative objects (normal cases, `null` fields, boundary values). It directly tests the reflexivity clause. If using JUnit, the equivalent idea is `assertTrue(value.equals(value))` for each non-`null` value.

## 6. Key Takeaways

- Standard statement: **for every non-`null` reference `x`, `x.equals(x)` must return `true`**.
- This is a requirement on the class's `equals` implementation, not merely a property of the `==` operator.
- `if (this == other) return true;` is a common, clear way to implement it, though not mandatory syntax.
- Test `x.equals(x)` directly; `Objects.equals(x, x)` can hide bugs due to its reference-comparison shortcut.
- If an object's `equals` with itself can return `false`, the implementation violates the contract and needs to be fixed.