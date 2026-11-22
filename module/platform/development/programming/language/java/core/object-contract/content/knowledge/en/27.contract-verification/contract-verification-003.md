# Testing `equals()`: Consistency, `null`, and Different-Type Objects

## 1. Goal and Context

In Java, `Object.equals(Object)` answers whether two objects are **equal according to the equality relation defined by the class**. The default implementation in `Object` checks identity; value classes typically override it to compare data. An `equals()` method that works on two identical-looking objects can still violate the contract when encountering `null`, an object of a different type, or when called repeatedly.

This lesson focuses on three checks that are easily overlooked:

1. **Consistency:** for the same pair of objects, if the information participating in comparison has not changed, repeated calls to `equals()` must yield the same result.
2. **Comparison with `null`:** for any non-`null` object `x`, `x.equals(null)` must return `false`, without throwing `NullPointerException`.
3. **Different-type objects:** test values of types incompatible with the class's equality model; for the `AccountKey` value class in this lesson, the result must be `false`, without throwing `ClassCastException`.

These three checks belong to the general contract of `Object.equals(Object)`. For a reliable design, you must also test **reflexivity** (`x.equals(x)`), **symmetry** (`x.equals(y) == y.equals(x)`), and **transitivity** (if `x == y` and `y == z` under `equals`, then `x == z`). The `==` symbol in this explanation denotes logical equality, not a replacement for calling `equals()` in code.

If a class overrides `equals()`, inspect `hashCode()` at the same time: **two equal objects must have the same hash code**. Two unequal objects are still allowed to share the same hash code.

## 2. Understanding the Scenarios to Test

### 2.1. Conditional Consistency

The Java contract specifies that repeated calls to `x.equals(y)` must return the same result **provided no information used in `equals` comparisons on `x` and `y` is modified**. Therefore, you need to test both equal pairs and unequal pairs, repeated multiple times under the same state.

For example, if two account keys share `username` and `tenantId`, `equals()` must not depend on the current time, random numbers, external state, or method call order. If a field used in `equals()` is modified, the result may validly change; that is not automatically a consistency violation. However, placing an object with mutable key fields into a `HashSet` or using it as a `HashMap` key is very dangerous because its hash bucket may no longer match.

A 100-iteration test helps catch common bugs, but **cannot prove correctness for all states and all interactions**. Immutable design and testing across multiple datasets provide better practical assurance.

### 2.2. `null` Is a Valid Comparison Argument

`a.equals(null)` must be `false` for `a != null`. This differs from calling `null.equals(a)`: the latter expression cannot dispatch a method and will throw `NullPointerException`.

`Objects.equals(a, b)` is a helper supporting two potentially `null` references:

- `Objects.equals(null, null)` returns `true`.
- `Objects.equals(null, a)` returns `false` if `a` is non-`null`.
- When `a` is non-`null`, `Objects.equals(a, b)` uses `a.equals(b)`.

To directly test the contract of the overridden method, write `!a.equals(null)`. Checking only `Objects.equals(null, a)` will **not invoke** `a.equals(...)` and will not catch bugs in that method.

### 2.3. Different-Type Objects

For a value class that only accepts the same type, calls such as `key.equals("alice")` and `key.equals(new Object())` must safely return `false`. An `instanceof` check before casting avoids `ClassCastException`; the expression `null instanceof AccountKey` also evaluates to `false`.

**Scope note:** the `Object.equals()` contract does not require *every* pair of objects of different classes to be unequal. A polymorphic design can allow equality between two different classes if strictly defined while still preserving symmetry, transitivity, and consistency. For the `final` account key below, the right choice is to equal only `AccountKey` objects. Do not copy the expectation "different class is always false" into a design that requires cross-class equality without analyzing it first.

## 3. Recommended Test Matrix

| Case | Test data | Expected result |
| --- | --- | --- |
| Reflexivity | `a.equals(a)` | `true` |
| Equal values | `a.equals(b)` where `a` and `b` are created separately with the same identity fields | `true` |
| Different values | `a.equals(d)` with different `tenantId` | `false` |
| Consistency when equal | Repeat `a.equals(b)` without changing state | Always `true` |
| Consistency when unequal | Repeat `a.equals(d)` without changing state | Always `false` |
| `null` | `a.equals(null)` | `false`, no exception |
| Different type: String | `a.equals("alice")` | `false`, no exception |
| Different type: Object | `a.equals(new Object())` | `false`, no exception |
| Symmetry | `a.equals(b)` and `b.equals(a)` | Both values identical |
| Transitivity | `a.equals(b)`, `b.equals(c)`, `a.equals(c)` | All three are `true` |
| Compatible hash | `a.equals(b)` is `true` | `a.hashCode() == b.hashCode()` |
| Collection integration | Add `a` to `HashSet`, look up `b` | `contains(b)` is `true` |

The values `a`, `b`, `c`, `d` must be constructed explicitly and intentionally. Testing an object only against itself is insufficient to detect bugs when comparing **two distinct instances with equal values**.

## 4. Complete, Runnable Java 17+ Verification Example

`AccountKey` represents a key by username and tenant. The class is marked `final` so type checking via `instanceof AccountKey` cannot encounter subclasses altering the definition of equality. The `final` fields keep the information participating in comparison stable after creation.

```java
// File: EqualsContractTest.java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class EqualsContractTest {
    private static final class AccountKey {
        private final String username;
        private final int tenantId;

        AccountKey(String username, int tenantId) {
            this.username = Objects.requireNonNull(username, "username");
            this.tenantId = tenantId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof AccountKey other)) {
                return false;
            }
            return tenantId == other.tenantId
                    && username.equals(other.username);
        }

        @Override
        public int hashCode() {
            return Objects.hash(username, tenantId);
        }
    }

    private static void check(String name, boolean passed) {
        if (!passed) {
            throw new AssertionError("FAIL - " + name);
        }
        System.out.println("PASS - " + name);
    }

    public static void main(String[] args) {
        AccountKey a = new AccountKey("alice", 7);
        AccountKey b = new AccountKey("alice", 7);
        AccountKey c = new AccountKey("alice", 7);
        AccountKey d = new AccountKey("alice", 8);

        check("phan xa", a.equals(a));
        check("doi xung", a.equals(b) && b.equals(a));
        check("bac cau",
                a.equals(b) && b.equals(c) && a.equals(c));

        boolean equalBefore = a.equals(b);
        boolean differentBefore = a.equals(d);
        boolean consistent = true;
        for (int i = 0; i < 100; i++) {
            if (a.equals(b) != equalBefore
                    || a.equals(d) != differentBefore) {
                consistent = false;
                break;
            }
        }
        check("nhat quan 100 lan",
                equalBefore && !differentBefore && consistent);

        check("khong bang null", !a.equals(null));
        check("khac kieu String", !a.equals("alice"));
        check("khac kieu Object", !a.equals(new Object()));
        check("khac gia tri", !a.equals(d));

        check("hashCode tuong thich",
                a.hashCode() == b.hashCode());

        Set<AccountKey> keys = new HashSet<>();
        keys.add(a);
        check("HashSet tim thay khoa bang nhau", keys.contains(b));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac EqualsContractTest.java
java EqualsContractTest
```

Exact output for the code above:

```text
PASS - phan xa
PASS - doi xung
PASS - bac cau
PASS - nhat quan 100 lan
PASS - khong bang null
PASS - khac kieu String
PASS - khac kieu Object
PASS - khac gia tri
PASS - hashCode tuong thich
PASS - HashSet tim thay khoa bang nhau
```

If any condition is false, `check(...)` throws `AssertionError` and the program terminates with failure, so the result does not depend on enabling the `-ea` flag. `a`, `b`, and `c` are **three separate objects**; `equals()` compares values, while `a == b` is `false`. `d` has a different tenant and is therefore not equal to `a`.

In `equals(Object)`, `this == obj` is a valid optimization for same-reference checks; `instanceof` handles both `null` and other types; `hashCode()` uses the exact two fields used by `equals()`. You do not need to test that two different keys must produce different hashes: hash collisions are valid.

## 5. Implementation Bugs That Tests Should Catch

### Bug 1: Casting Before Checking

**Incorrect** example (illustrative fragment only, not a standalone program):

```java
@Override
public boolean equals(Object obj) {
    AccountKey other = (AccountKey) obj;
    return username.equals(other.username)
            && tenantId == other.tenantId;
}
```

When `obj` is `null`, accessing `other.username` throws `NullPointerException`; when the object is of a different type, the cast causes `ClassCastException`. Checking `instanceof`, or checking `null` and class before casting, is the fix.

### Bug 2: Accidentally Overloading Instead of Overriding

```java
// WRONG: signature differs from equals(Object), does not override Object.equals.
public boolean equals(AccountKey other) {
    return other != null
            && username.equals(other.username)
            && tenantId == other.tenantId;
}
```

`a.equals(b)` may invoke the `equals(AccountKey)` overload and appear to work, but collections or `Object`-typed reference expressions still use `Object.equals(Object)`. Always use the exact signature `public boolean equals(Object obj)` and include `@Override`; this annotation helps the compiler catch a signature that fails to override the intended method.

### Bug 3: Omitting an Identity Field or Using Mutable State

If `equals()` only compares `username` when the business rules also require `tenantId`, two accounts belonging to different tenants could be treated as equal. Testing `a.equals(d)` in the example will catch this bug.

Do not include volatile fields such as current time, last access time, counters, or random values in equality if they are not part of a stable identity. Objects used as keys in `HashMap` or elements of `HashSet` should have their equality-related fields immutable while stored.

### Bug 4: `equals()` and `hashCode()` Out of Sync

If `equals()` treats two distinct instances as equal while `hashCode()` still uses the default value inherited from `Object`, looking up an equivalent object in a hash structure can fail. Verify both the hash rule and `HashSet.contains`/`HashMap.get` behavior, since that is where the bug surfaces most readily.

### Bug 5: Insufficient Path Coverage in Testing

Calling `equals()` only once or only comparing `a.equals(a)` is not enough. When designing tests, include at least one pair equal by value but with distinct references, one unequal pair, `null` arguments, multiple incompatible types, and repeated calls.

For classes with many branches or nullable fields, expand the matrix with `null` in each allowed field, all combinations of boundary values, differences at each individual field, and reversed comparison order. You can split the check groups into separate JUnit unit tests or parameterized tests so that failures pinpoint the exact case.

## 6. Distinguishing Commonly Confused Concepts

- **`==` on references:** compares reference identity, does not automatically compare the values of two distinct objects.
- **`equals(Object)`:** the equality relation provided by the class; `Object`'s default ties it to identity.
- **`Objects.equals(a, b)`:** null-safe comparison helper; may skip calling `a.equals` when `a` is `null`.
- **`hashCode()`:** value supporting hash structures; must be consistent with equality, not a unique identifier.
- **`compareTo()`/`Comparator`:** expresses ordering; compatibility with `equals()` must be evaluated separately according to data structure and business requirements.

**Checklist before accepting an `equals()` implementation:** exact `equals(Object)` signature; reflexivity–symmetry–transitivity rules; consistency when compared data does not change; `equals(null) == false`; safe handling of unsupported types; matching `hashCode`; actual testing with collections.

## 7. Official Documentation

- [Java SE 26 — `Object.equals(Object)` and `hashCode()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [Java SE 26 — `Objects.equals(Object,Object)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object))
- [Java SE 26 — `HashSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HashSet.html)
