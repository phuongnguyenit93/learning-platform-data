# Testing That `equals() == true` Always Implies Equal `hashCode()` in Java

## 1. What Needs to Be Proven

In Java, two **non-`null`** objects for which `a.equals(b)` returns `true` must produce the same `hashCode()` result at the time of verification, when the data participating in `equals()` and `hashCode()` has not been modified:

~~~text
If a.equals(b) == true then a.hashCode() == b.hashCode().
~~~

This is the contract of `java.lang.Object`. It matters because hash-based structures like `HashMap` and `HashSet` use the hash code to determine the search bucket before checking equality. If equal objects have different hashes, looking up by an equivalent object can fail.

**The converse is not guaranteed:** having the same hash code **does not mean** two objects are equal. Hash collisions are valid; a hash code is an `int`, whereas the number of distinct object values can be much larger.

| Observed relationship | Contract conclusion |
| --- | --- |
| `a.equals(b) == true` and both hashes are equal | Passes the condition under test |
| `a.equals(b) == true` but hashes differ | **Violates** the contract |
| `a.equals(b) == false` and hashes are equal | Valid; this may be a collision |
| `a.equals(b) == false` and hashes differ | Valid |
| `a == b` | Same object; two hash calls must be stable if relevant data does not change |

Note: a single pair of objects passing this condition **does not prove the entire `equals()` implementation is correct**. `equals()` must also satisfy reflexivity, symmetry, transitivity, and consistency; `x.equals(null)` must be `false`. A good test suite should check those properties too, though the focus of this lesson is the implication from `equals()` to `hashCode()`.

## 2. Why Test Multiple Equal Objects With Distinct References?

Testing only with `a.equals(a)` is too weak: calling `hashCode()` twice on the same unchanged object naturally yields the same result. You must create **at least two separate instances that are logically equal**.

For example, a customer key identified by `tenant` and `customerId`. Two `CustomerKey` instances with equal field pairs must be considered equal, even if constructed in two different places. The same dataset determines **both** `equals()` and `hashCode()`:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof CustomerKey other)) return false;
    return customerId == other.customerId && tenant.equals(other.tenant);
}

@Override
public int hashCode() {
    return Objects.hash(tenant, customerId);
}
~~~

The snippet above only illustrates two methods inside a class with fields `tenant` and `customerId`; a complete, standalone runnable program appears in the next section. What is essential is not specifically using `Objects.hash()`, but that **both computations share the exact same equality policy**. A different hashing algorithm can be written as long as every equal pair still produces the same hash.

## 3. Java 17 Program: Valid Case and Broken Case

The example has two key classes:

- `CustomerKey` implements the contract properly: both `equals()` and `hashCode()` use `tenant` and `customerId`; the fields are `final`.
- `BrokenKey` is intentionally wrong: `equals()` compares labels case-insensitively, whereas `hashCode()` hashes the raw case-sensitive string.

Save the file **HashContractDemo.java** with the entire content below:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashContractDemo {

    static final class CustomerKey {
        private final String tenant;
        private final int customerId;

        CustomerKey(String tenant, int customerId) {
            this.tenant = Objects.requireNonNull(tenant);
            this.customerId = customerId;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof CustomerKey other)) {
                return false;
            }
            return customerId == other.customerId
                    && tenant.equals(other.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, customerId);
        }
    }

    static final class BrokenKey {
        private final String label;

        BrokenKey(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenKey other)) {
                return false;
            }
            return label.equalsIgnoreCase(other.label);
        }

        @Override
        public int hashCode() {
            return label.hashCode(); // Intentionally wrong with equalsIgnoreCase().
        }
    }

    static int verifyAllPairs(CustomerKey[] samples) {
        int checks = 0;
        for (CustomerKey left : samples) {
            for (CustomerKey right : samples) {
                checks++;
                if (left.equals(right)
                        && left.hashCode() != right.hashCode()) {
                    throw new AssertionError(
                            "Equal keys must have equal hash codes");
                }
            }
        }
        return checks;
    }

    public static void main(String[] args) {
        CustomerKey a = new CustomerKey("VN", 42);
        CustomerKey b = new CustomerKey(new String("VN"), 42);
        CustomerKey c = new CustomerKey("VN", 43);
        CustomerKey d = new CustomerKey("SG", 42);

        System.out.println("Different objects: " + (a != b));
        System.out.println("Equal keys: " + a.equals(b));
        System.out.println("Equal hash codes: "
                + (a.hashCode() == b.hashCode()));

        Set<CustomerKey> goodSet = new HashSet<>();
        goodSet.add(a);
        System.out.println("HashSet finds equal key: "
                + goodSet.contains(b));

        int checks = verifyAllPairs(
                new CustomerKey[] { a, b, c, d });
        System.out.println("Pair checks passed: " + checks);

        BrokenKey x = new BrokenKey("A");
        BrokenKey y = new BrokenKey("a");
        System.out.println("Broken equals: " + x.equals(y));
        System.out.println("Broken hash codes equal: "
                + (x.hashCode() == y.hashCode()));

        Set<BrokenKey> badSet = new HashSet<>();
        badSet.add(x);
        System.out.println("Broken HashSet finds equal key: "
                + badSet.contains(y));

        System.out.println("Unequal strings can collide: "
                + ("Aa".hashCode() == "BB".hashCode()));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac HashContractDemo.java
java HashContractDemo
~~~

Standard output:

~~~text
Different objects: true
Equal keys: true
Equal hash codes: true
HashSet finds equal key: true
Pair checks passed: 16
Broken equals: true
Broken hash codes equal: false
Broken HashSet finds equal key: false
Unequal strings can collide: true
~~~

**Analysis:**

1. `a != b` confirms the two keys are two separate objects. `new String("VN")` also creates a separate string object to test equality by **value**, rather than accidentally relying on the same reference.
2. `a.equals(b)` is true because `tenant` and `customerId` match; `Objects.hash(tenant, customerId)` maps both equal keys to the same hash.
3. `goodSet.contains(b)` succeeds after adding `a`, matching what collection users expect.
4. The `verifyAllPairs` method iterates over 4 × 4 = **16 ordered pairs**. Equal pairs must have identical hashes; unequal pairs are not required to have different hashes. This check covers both directions `(a,b)` and `(b,a)`.
5. For `BrokenKey("A")` and `BrokenKey("a")`, `equalsIgnoreCase()` returns `true` yet `String.hashCode()` for `"A"` and `"a"` differ. `HashSet` can fail to find the equivalent key; in this program the result is `false`.
6. `"Aa"` and `"BB"` are two unequal strings that share the same Java string hash code (2112). This collision is valid and illustrates why **you must not write tests requiring two different objects to have different hashes**.

`BrokenKey` is an **intentional counterexample** and must not be used as a key in real systems.

## 4. Fixing the Root Cause: Same Normalization for Equality and Hashing

A common mistake is defining `equals()` case-insensitively while hashing raw data. You should not fix this by arbitrarily changing `hashCode()` to another expression without verifying it corresponds to the exact same equality relation.

If the domain wants keys to be **case-insensitive under a chosen normalization rule**, you can convert the data to a canonical form in the constructor, and then let **both equals and hashCode process that exact normalized value**:

~~~java
import java.util.Locale;
import java.util.Objects;

final class NormalizedKey {
    private final String normalized;

    NormalizedKey(String raw) {
        normalized = Objects.requireNonNull(raw)
                .toLowerCase(Locale.ROOT);
    }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof NormalizedKey other
                && normalized.equals(other.normalized);
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
~~~

This is an **illustrative class**, not a standalone `main` program. In it, `new NormalizedKey("API")` and `new NormalizedKey("api")` are equal and share the same hash. `Locale.ROOT` avoids depending on the machine's default locale during normalization. The `toLowerCase(Locale.ROOT)` rule defines equality by the post-normalized string; it **is not necessarily equivalent to `String.equalsIgnoreCase()` for all Unicode**. If the product needs complex Unicode comparison, the domain must finalize the normalization/case-folding algorithm and use the **exact same canonical representation** for both methods.

An identifier data class as a `record` is also convenient when all components have suitable equality semantics:

~~~java
record CustomerId(String tenant, int number) {
    CustomerId {
        Objects.requireNonNull(tenant);
    }
}
~~~

Java records automatically generate `equals()` and `hashCode()` consistent with their components. However, if a component is a mutable array or mutable object, a record does not automatically guarantee deep immutability; component comparison rules, defensive copying, and mutating data after using it as a key must still be considered.

## 5. Writing the Test Properly

### Testing an Equal Pair

A good contract test follows this order:

1. Prepare two instances with the same identifying data and **distinct references**.
2. Verify the precondition: `assertNotSame(a, b)` and `assertEquals(a, b)`. Without `assertEquals(a,b)`, the implication could pass **vacuously** because the two objects are unequal.
3. Verify the conclusion: `assertEquals(a.hashCode(), b.hashCode())`.
4. Also test `HashSet`/`HashMap` to confirm the integration behavior protected by this contract.

With JUnit Jupiter (JUnit 5), the example below uses `HashContractDemo.CustomerKey` from the Java program above; JUnit Jupiter must be added to the test classpath via Maven/Gradle or the corresponding project configuration:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.HashSet;
import java.util.Set;

class CustomerKeyContractTest {
    @Test
    void equalObjectsMustHaveSameHashCode() {
        var a = new HashContractDemo.CustomerKey("VN", 42);
        var b = new HashContractDemo.CustomerKey("VN", 42);

        assertNotSame(a, b);
        assertEquals(a, b); // Verify the premise equals() == true.
        assertEquals(a.hashCode(), b.hashCode());

        Set<HashContractDemo.CustomerKey> keys = new HashSet<>();
        keys.add(a);
        assertTrue(keys.contains(b));
    }
}
~~~

This is a **JUnit test class**, not executed directly via `java CustomerKeyContractTest`; it is executed by a test runner after adding the dependency. For modern JUnit 5, projects can use the JUnit Platform via Maven Surefire or Gradle `test`.

### Table-Driven Case Testing

Do not use only a single "happy path" pair. Prepare a small yet comprehensive set:

| Case | Expected `equals()` result | Hash assertion |
| --- | --- | --- |
| Two separate objects with all identity fields identical | `true` | **Must be equal** |
| Same value created via different construction paths (builder, constructor, parser) | `true` if domain-equivalent | **Must be equal** |
| Differing in a field checked by `equals()` | `false` | Do not enforce inequality |
| A field ignored by `equals()` | `true` if all key fields match | **Must be equal** |
| Strings differing in case but normalized to the same value by domain rules | `true` per domain rule | **Must be equal** |
| Nullable field | Per equality policy for `null` | If equal, hashes must match |
| Right-hand side object is `null` | `false` | **Do not call `null.hashCode()`** |
| Two instances with equal values, one being a deep copy | `true` if value equality | **Must be equal** |
| Two unequal objects that happen to share the same hash | `false` | Valid, do not fail |

You can iterate over all pairs in the sample set, as `verifyAllPairs()` does in the program, to easily catch combinatorial inconsistencies. For large projects, add property-based testing: generate many domain values, **intentionally construct equivalent pairs**, and verify the implication; purely random generators rarely produce two equal keys, making the test weak.

### Reading the Implication Properly

When coding a test by logic:

~~~java
if (a.equals(b)) {
    assert a.hashCode() == b.hashCode();
}
~~~

This snippet is illustrative only, depends on enabling Java assertions with `-ea`, and assumes both references are non-`null`. If `a.equals(b)` is always `false` due to another bug, the check branch never runs yet the test still "passes". Therefore, you must have **tests that proactively construct equal pairs**, asserting `equals() == true` first and only then checking the hashes.

In real test suites, use the framework's `assertEquals(expected, actual)` or throw `AssertionError`; the Java `assert` keyword is disabled by default unless the JVM is launched with `-ea`.

## 6. Design Mistakes That Easily Cause Test Failures

### `equals()` Inspects One Set of Fields, `hashCode()` Inspects Another

For example, equality compares `id` while hashing also includes `displayName`. Two objects with the same `id` and different names will be equal under `equals()` while their hashes may differ. If a field **does not participate in equality** yet participates in hashing, this is a red flag; update both to follow a single unified logical key design.

Not every field used by `equals()` has to appear directly in the hash formula. A hash function that always returns `0` still preserves the "equal → same hash" condition, though it causes many collisions and degrades hash table performance. The goal is **contract correctness first**, followed by reasonable hash distribution.

### Mutable Keys in `HashMap`/`HashSet`

Suppose a key has a mutable `id` field and `hashCode()` depends on `id`. Add the key to a `HashSet` with `id=1`, then mutate it to `id=2`. On subsequent lookup, the hash table may search a different bucket and fail to find the inserted element. This is a bug even when `equals()` and `hashCode()` are **completely consistent at every point in time**.

- Prefer immutable keys (`final` fields with immutable values or defensive copies of mutable state).
- If identifying data must be mutated, remove the key from the collection **before mutating** and reinsert it once in the new state, provided the workflow is consistent and synchronized if accessed by multiple threads.
- Avoid letting external code silently mutate an array/list inside a key after insertion.

Testing the implication on **stable** instances does not replace testing the lifecycle of a mutable key.

### Arrays and Collections

Java arrays use `Object.equals()` and `Object.hashCode()` unless handled specially—meaning primarily by identity. If a class decides equality based on **array contents**, hashing must likewise be based on the corresponding contents:

~~~java
import java.util.Arrays;

@Override
public boolean equals(Object obj) {
    return obj instanceof ByteKey other
            && Arrays.equals(bytes, other.bytes);
}

@Override
public int hashCode() {
    return Arrays.hashCode(bytes);
}
~~~

The two methods above are illustrative inside a `ByteKey` class with field `byte[] bytes`; to use it as a stable key, you must also copy the array in the constructor and protect getters. For multidimensional arrays, depending on the data type and semantics, consider `Arrays.deepEquals()` and `Arrays.deepHashCode()` accordingly. For collections, equality and hashing of standard implementations are typically content-based, though mutable elements can still alter both results.

### Inheritance and Cross-Type Comparisons

A base class that allows subclasses to compare equal via `instanceof`, while a subclass adds fields to `equals()`, can violate symmetry/transitivity. When fixing the contract, check both **who is considered equal** and how the hash is computed. With `final` value classes, records, or clear type-matching rules, designs are usually easier to verify. Do not simply add a hash test while ignoring an already broken equality premise.

### Floating-Point Numbers, `BigDecimal`, and Normalization

- `BigDecimal("1.0")` and `BigDecimal("1.00")` differ under `equals()` because their scales differ; `compareTo() == 0` **does not imply** `equals() == true`. Writing equality based on `compareTo` while leaving hashing to `BigDecimal.hashCode()` can violate the contract. If the domain considers these representations equivalent, define canonicalization for both equality and hashing.
- For `double`/`float`, `NaN`, `+0.0`, and `-0.0` have comparison rules that must be defined consistently; use the semantics of `Double.equals()/Double.hashCode()` or a unified domain rule, avoiding arbitrary `==` comparisons paired with a different hash.
- For Unicode text, normalization, whitespace, and case sensitivity are **business rules**. Changing only one side easily produces pairs that pass equality yet fail hashing.

## 7. Distinguishing Contract Testing From Collision Testing

These are two separate aspects:

- **Correctness:** if `equals()` returns `true`, then `hashCode()` must be equal, without exception.
- **Distribution quality:** distinct objects ideally distribute evenly to reduce collisions, but this is **not a logical requirement** of `Object`.

Do not use `assertNotEquals(a.hashCode(), b.hashCode())` to test that two objects `a` and `b` are unequal. That test can fail on a completely valid implementation. For instance, `"Aa"` and `"BB"` already have the same hash.

For storage systems and data partitioning, also do not assume `Object.hashCode()` is a stable identifier across processes/JVMs/application versions or a cryptographic hash function. `hashCode()` serves the contract of objects and collections during execution, not as a substitute for a canonical ID, checksum, or cryptographic hash.

## 8. QA Criteria When Reviewing `equals()`/`hashCode()`

1. **Which objects are considered equal?** Document which fields form identity/value equality as well as rules for `null`, normalization, and class types.
2. **Are there independent equivalent instances?** Create `a`, `b` with equal values from different constructors/factories; check `a != b` and `a.equals(b)` first.
3. **Do all equal pairs have equal hashes?** Run tests in both directions and across varied datasets, including boundary values, Unicode strings if supported by the domain, and optional `null` fields.
4. **Are differences verified properly?** Differing in a field participating in equality must cause `equals()` to reflect the requirement; never demand that hashes differ.
5. **Is the hash stable when logical data does not change?** Two consecutive calls on a stable object yield the same `int`. Fields used as keys avoid mutation.
6. **Does hash collection behavior work properly?** After `set.add(a)`, `set.contains(b)` must be true if `a.equals(b)`, assuming keys are not mutated and the collection is used according to contract.
7. **Are there aliases to mutable data?** Mutable arrays/lists/children must be copied or locked against modification if the hash depends on contents.
8. **What about the other `equals()` properties?** Check reflexivity, symmetry, transitivity, consistency, and `equals(null) == false`; the hash contract cannot rescue a poorly designed equality relation.

## 9. Self-Check Exercises

**Exercise 1.** Two objects return `equals() == false` yet have the same `hashCode()`. Is this a contract violation?  
**Answer:** No. Collisions are valid; the requirement only runs in the direction "equal → same hash".

**Exercise 2.** A test uses `if (a.equals(b))` to compare hashes, but `equals()` has a bug and always returns `false`. Has the test proven the actual contract is correct?  
**Answer:** No. It only tests the implication vacuously without confirming the expected equality relation. You must construct pairs that ought to be equal and call `assertEquals(a,b)` first.

**Exercise 3.** `equals()` uses `id` while `hashCode()` uses both `id` and `name`. Which case will catch the bug?  
**Answer:** Two instances with the same `id` but different names. The `equals() == true` premise holds, while the hashes may differ.

**Exercise 4.** Why do mutable keys cause `HashSet.contains()` to fail even when `equals()` and `hashCode()` implementations are consistent?  
**Answer:** Hash tables organize entries by their hash at insertion time; if identifying fields change afterward, the new hash may lead to a different lookup bucket. Use immutable keys or manage remove/update/reinsert safely.

**Exercise 5.** `String` `"Aa"` and `"BB"` have the same hash. Does Java `String` need to be fixed?  
**Answer:** No. They are not equal under `equals()`, so equal hashes are a valid collision.

**Practical takeaway:** The strongest verification for this condition is to **construct multiple object pairs with different identities that are equal per domain rules, verify the `equals() == true` premise, and then enforce equal `hashCode()` values**. Combine this with hash table tests and mutation controls to catch both contract bugs and practical consequences.
