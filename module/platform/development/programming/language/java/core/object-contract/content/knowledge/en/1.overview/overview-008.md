# A Learning Roadmap for Java Object Contracts Using One End-to-End Value Object

## 1. Goal and Context

In Java, every ordinary class inherits foundational behavior from `java.lang.Object`. When a class represents a **value** (a value object), two instances at different memory addresses can carry the same business meaning. Therefore, it is necessary to clearly define the concept of "equality", how the object is placed into hash-based structures, how the object is described, and (if needed) how it is ordered.

This lesson uses a single end-to-end scenario: `OrderKey` is an order key consisting of a **store code** (`tenant`) and an **order number** (`number`). For example, `new OrderKey(" shop ", 42)` and `new OrderKey("SHOP", 42)` identify the same order after normalizing the store code. `OrderKey` is a value object: the values of its fields determine its logical identity; the object does not change after creation.

After this lesson, learners should be able to:
- Distinguish `==` (same reference) from `equals` (equality by value per the class's contract).
- State and verify the `equals`/`hashCode` contract, and explain why `HashMap` and `HashSet` depend on both.
- Design `toString` for observation/debugging without mistaking it for a stable storage format.
- Write `Comparable`/`Comparator` matching the equality definition; understand the risks when natural ordering is inconsistent with `equals`.
- Keep value objects immutable, validate inputs, and avoid mutating keys after inserting them into a collection.

## 2. Suggested Roadmap and Completion Criteria

| Stage | Question to answer | Practice on `OrderKey` | Sign of understanding |
|---|---|---|---|
| 0. Foundations | How do object, reference, instance, value, and immutability differ? | Create two separate instances with the same data | Can explain why `a == b` is `false` |
| 1. Equality | When are two orders "the same key"? | Choose the `(tenant, number)` field pair for `equals` | Verify all 5 properties of `equals` |
| 2. Hashing | Why does lookup with a different object still find it? | Override `hashCode` in sync with `equals` | `HashSet` deduplicates, `HashMap` lookup succeeds |
| 3. Representation | What do logs tell us about the object? | Override `toString` with clear information | Read logs without needing memory addresses |
| 4. Ordering | By what rules are keys sorted? | Compare `tenant` then `number` with `Comparable` | `TreeSet` does not lose distinct keys |
| 5. Immutability | What happens if a key changes after hashing? | `private final` fields, input normalization, no setters | Hash value stays unchanged across its lifecycle |
| 6. Integration and testing | Does the contract work in real collections? | Run the end-of-lesson program and variant exercises | Predict and correctly explain all output |

**Practice order:** start with two different references; add equality; immediately add hashing; test with `HashSet`/`HashMap`; improve object printing; finally add natural ordering and test `TreeSet`. There is no need to memorize every method of `Object` all at once.

## 3. Contracts to Master

### 3.1. `==` and `equals`

For two reference-type variables, `a == b` asks whether they point to **the same object**. `a.equals(b)` asks how the class defines "equality". Default `Object.equals` is equivalent to comparing reference identity; a value object usually needs to override it.

The `equals` contract for non-`null` references:
1. **Reflexive:** `x.equals(x)` is always `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` produce the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)` are both true, then `x.equals(z)` is true.
4. **Consistent:** when data participating in comparison does not change, repeated calls return the same result.
5. **With null:** `x.equals(null)` is always `false`.

For `OrderKey`, the entire definition of "equal" is equal normalized `tenant` **and** equal `number`. Do not use variable names, memory addresses, `toString`, or just a single field to infer equality.

### 3.2. `hashCode`

If `x.equals(y)` is `true`, then `x.hashCode() == y.hashCode()` is **mandatory**. The converse is not true: two different objects can still share the same hash code (collision). The hash value of an object must remain consistent while the data used by `equals` does not change.

`HashMap`/`HashSet` use hash codes to guide bucket lookup and use equality to distinguish keys/elements within a bucket. Overriding `equals` while omitting `hashCode` can cause two equal value objects to have different hashes, leading to incorrect lookup/deduplication behavior. Therefore **always override them together**, based on the same set of attributes. `Objects.hash(tenant, number)` is easy to read for examples; performance-sensitive code can use a specific hash-combining operation after benchmarking.

### 3.3. `toString`

`Object`'s `toString` typically produces a string in the form of class name and hexadecimal hash code; this is not a list of business attributes. Override `toString` to support logging and debugging, such as `OrderKey[tenant=SHOP, number=42]`. Do not use `toString` as a basis for comparison or data keys, and do not treat this format as a serialization API. Avoid printing sensitive information in real-world objects.

### 3.4. `Comparable`, `Comparator`, and Consistency

`Comparable<T>` establishes a **natural ordering** for a class via `compareTo` (negative/0/positive for less than/equal in ordering/greater than). `Comparator<T>` expresses an external sorting rule, convenient when multiple different criteria are needed.

For a value object used in `TreeSet` or as a `TreeMap` key, design it so that:

`a.compareTo(b) == 0` ⇔ `a.equals(b)`.

Ordered collections use a comparison result of 0 to determine elements/keys equivalent in order. If this rule is inconsistent with `equals`, `TreeSet` and `HashSet` can produce different element counts. A familiar example: `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, yet these two numbers have `equals` as `false` because their scales differ. This is a point to weigh when choosing value objects or comparators.

## 4. Standalone Runnable Java 17+ Example

Create the file **`ObjectContractDemo.java`** with the following content. The program uses a nested `final` value object class so the entire example can be compiled from a single file. Java 17 supports pattern matching with `instanceof`, which is used here.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ObjectContractDemo {
    public static void main(String[] args) {
        OrderKey first = new OrderKey("  shop  ", 42L);
        OrderKey sameValue = new OrderKey("SHOP", 42L);
        OrderKey next = new OrderKey("shop", 43L);

        System.out.println("==: " + (first == sameValue));
        System.out.println("equals: " + first.equals(sameValue));
        System.out.println("hashCode equal: "
                + (first.hashCode() == sameValue.hashCode()));

        Set<OrderKey> unique = new HashSet<>(
                List.of(first, sameValue, next));
        System.out.println("HashSet size: " + unique.size());

        Map<OrderKey, String> status = new HashMap<>();
        status.put(first, "paid");
        System.out.println("HashMap lookup: " + status.get(sameValue));

        Set<OrderKey> sorted = new TreeSet<>(
                List.of(next, sameValue, first));
        System.out.println("TreeSet: " + sorted);
        System.out.println("compareTo == 0: "
                + (first.compareTo(sameValue) == 0));
        System.out.println("toString: " + first);
    }

    public static final class OrderKey implements Comparable<OrderKey> {
        private final String tenant;
        private final long number;

        public OrderKey(String tenant, long number) {
            String normalized = Objects.requireNonNull(tenant, "tenant")
                    .strip()
                    .toUpperCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("tenant is blank");
            }
            if (number <= 0) {
                throw new IllegalArgumentException(
                        "number must be positive");
            }
            this.tenant = normalized;
            this.number = number;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof OrderKey that)) {
                return false;
            }
            return number == that.number && tenant.equals(that.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, number);
        }

        @Override
        public String toString() {
            return "OrderKey[tenant=" + tenant
                    + ", number=" + number + "]";
        }

        @Override
        public int compareTo(OrderKey other) {
            Objects.requireNonNull(other, "other");
            int byTenant = tenant.compareTo(other.tenant);
            return byTenant != 0
                    ? byTenant
                    : Long.compare(number, other.number);
        }
    }
}
```

Run from the directory containing the file with JDK 17 or later:

```bash
javac --release 17 ObjectContractDemo.java
java ObjectContractDemo
```

Expected output (the printing order of `TreeSet` is fixed by `compareTo`; it does not depend on `HashSet` order):

```text
==: false
equals: true
hashCode equal: true
HashSet size: 2
HashMap lookup: paid
TreeSet: [OrderKey[tenant=SHOP, number=42], OrderKey[tenant=SHOP, number=43]]
compareTo == 0: true
toString: OrderKey[tenant=SHOP, number=42]
```

Step-by-step explanation:
- `first` and `sameValue` are two different objects, so `==` returns `false`. The constructor normalized whitespace and uppercase using `Locale.ROOT`, so `equals` returns `true`.
- When `equals` is `true`, these two objects must have the same `hashCode`; the duplicate element is merged by `HashSet`, while `next` with `number=43` is a different key. Consequently, the set has 2 elements.
- `HashMap` can retrieve the value stored with `first` using the key `sameValue`, illustrating value-based lookup.
- `TreeSet` uses `compareTo`: comparing `tenant` first, then `number`. Two objects with the same key yield `compareTo` equal to 0, so the set contains one key 42 and one key 43.
- The displayed string is deliberately chosen by `toString`; do not use this output to implement equality logic.

### Why Is This Example a Valid Value Object?

**Immutable:** The class is declared `final`, both fields are `private final`, and there are no setters. `String` is immutable and `long` is primitive, so callers cannot mutate internal data through a leaked reference. Normalizing and validating directly in the constructor prevents invalid states.

**Meaningful equality:** `equals` is based on the exact two fields that determine the key's meaning. The `this == other` branch is a fast optimization; `instanceof OrderKey` is safe here because the `final` class has no subclasses that could break symmetry.

**Appropriate hashing:** `hashCode` uses the same `tenant` and `number`; both are immutable, so the hash remains stable after placing the object into a `HashMap`.

**Appropriate ordering:** `compareTo` checks both fields in the same semantic order as `equals`; using `Long.compare` avoids bugs from subtracting two `long` values and casting to `int`.

**Clear input boundaries:** A `null` tenant triggers `NullPointerException` from `requireNonNull`; an empty string after `strip` and non-positive order numbers are rejected with `IllegalArgumentException`. Uppercase normalization rules must match the real business domain; the example assumes store codes are case-insensitive.

## 5. Common Mistakes and How to Detect Them

| Mistake | Observable consequence | How to handle |
|---|---|---|
| Overriding only `equals` | `HashSet`/`HashMap` may fail to recognize two equal keys | Override `hashCode` with the same fields |
| `hashCode` includes a field absent from `equals` | Two equal objects may have different hashes | Use the same data sources that determine equality |
| Key has a setter changing fields involved in hashing | Lookup may fail after placing the key into a map/set | Use immutable value objects; do not mutate keys |
| Comparing strings with `==` | Compares references instead of content | Use `String.equals` or `Objects.equals` when nullable |
| `compareTo` checks only `tenant`, omitting `number` | Two orders with different numbers may be merged into one by `TreeSet` | Include all key fields in the comparison rule |
| Using subtraction in integer `compareTo` | Can overflow and return the wrong sign | Use `Integer.compare`/`Long.compare` |
| Auto-generated `toString` containing passwords/tokens | Sensitive data may leak into logs | Include only necessary fields; mask sensitive information |
| Using a freely inheritable class and adding equality fields in a subclass | Risks breaking symmetry/transitivity | Prefer `final` value objects or a consistent equality design |
| Comparing `double`/`BigDecimal` without choosing a normalization policy | Differences in NaN, -0.0, scale, or rounding easily cause surprises | Define the value domain, normalize, and test boundary cases |

**Distinguishing two purposes:** Hashing to find elements quickly and ordering to sort are two separate contracts. `hashCode` does not need to increase with ordering; `compareTo` does not determine hash buckets.

## 6. Self-Testing and Extending the Example

After running the program, work through these exercises in sequence; always predict the output first and then verify:
1. Create `a = new OrderKey("Shop", 42)`, `b = new OrderKey(" SHOP ", 42)`, and `c = new OrderKey("SHOP", 43)`. Check `a.equals(b)`, `b.equals(a)`, `a.equals(c)`, `a.equals(null)`, and `a.equals(a)`.
2. Create `d = new OrderKey("shop", 42)`. Check the chain `a.equals(b)`, `b.equals(d)`, `a.equals(d)` to observe transitivity; also check that hashes match when equal.
3. Temporarily remove `hashCode` in a **separate** test copy of the class and observe `HashSet`/`HashMap`; restore the correct code after the experiment. This is a way to see a contract bug, not an acceptable implementation.
4. In a separate test copy, modify `compareTo` to compare only `tenant` while keeping `equals` unchanged. Compare the element counts of `HashSet` and `TreeSet` when adding keys 42 and 43; explain why the results differ.
5. Try `new OrderKey(null, 1)`, `new OrderKey("   ", 1)`, `new OrderKey("shop", 0)`; identify the exception thrown and the reason.
6. Write automated tests for identity, the 5 properties of `equals`, hash consistency, behavior of `HashMap`/`HashSet`/`TreeSet`, and comparison ordering. The tests only need fixed sample values; for more complex classes, use multiple samples and property-based testing.

A minimal test suite (convertible to JUnit) should include:

| Assertion | Expected correctness |
|---|---|
| `a != b` and `a.equals(b)` | Two different instances with the same value |
| `a.equals(null) == false` | Not equal to null |
| `a.equals(b) == b.equals(a)` | Symmetry |
| `a.equals(b) && b.equals(d) && a.equals(d)` | Transitivity |
| `a.equals(b)` implies `a.hashCode() == b.hashCode()` | Hash contract |
| `map.put(a, "ok"); map.get(b)` returns `"ok"` | Value-based lookup |
| `a.compareTo(b) == 0` and `a.compareTo(c) < 0` | Consistent ordering |
| `new HashSet<>(List.of(a,b,c)).size() == 2` | Proper deduplication |

## 7. Connections to Other Java Mechanisms and Next Steps

- **`record` (Java 16+)** suits many value objects because the compiler automatically provides `equals`, `hashCode`, and `toString` from the components; records do not automatically provide `Comparable`. If input normalization is needed, use a compact constructor and verify equality results on the normalized values.
- **`Objects.equals`, `Objects.hash`, `Objects.requireNonNull`** help express null handling and contracts clearly, though they do not automatically choose the right business attributes for the designer.
- **`Arrays.equals`/`Arrays.hashCode`** (or `deepEquals`/`deepHashCode` versions for appropriate nested structures) must be considered if a value object contains arrays: `array.equals` defaults to reference comparison.
- **`Object.getClass`** helps inspect the runtime class; **`clone`** has its own contract and is usually unnecessary for immutable value objects. **`finalize`** has been phased out of modern Java design (deprecated for removal) and should not be used to manage resources. The `wait`/`notify` methods relate to thread coordination, not the foundation of equality.
- When advancing to entity classes with lifecycle identity, mutable collections, ORMs, or complex inheritance hierarchies, redefine identity/equality according to that model's rules; do not copy a value-object definition blindly into every case.

**Lesson completion criteria:** be able to build `OrderKey` from business requirements, explain each override, run the example successfully, and predict differences between `HashSet`, `HashMap`, and `TreeSet` when a contract is broken.