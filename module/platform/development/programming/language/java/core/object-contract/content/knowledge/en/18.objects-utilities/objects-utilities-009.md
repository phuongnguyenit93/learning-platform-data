# `Objects` utilities cannot fix `equals()` or `Comparator` that already violate their contracts

The `java.util.Objects` class provides many handy static methods for comparing, computing hash codes, checking `null`, and working with comparators. Names like `Objects.equals()`, `Objects.deepEquals()`, `Objects.hash()`, and `Objects.compare()` easily lead learners to think the library will automatically guarantee the correctness of every equality or ordering check.

**Reality:** the utilities only provide convenient call patterns, handle certain special cases such as `null` and arrays, or combine hash values. They **cannot automatically fix** an `equals(Object)` lacking symmetry, a `hashCode()` inconsistent with `equals()`, or a `Comparator` lacking transitivity.

## 1. Clearly distinguishing the roles of the methods

| Utility | What can it do? | What can it NOT do on its own? |
| --- | --- | --- |
| `Objects.equals(a, b)` | Compares two references null-safely; if needed, calls `a.equals(b)` | Does not check/fix symmetry, transitivity, or the business meaning of `equals()` |
| `Objects.deepEquals(a, b)` | Deep-compares contents when **both are arrays**; otherwise relies on object equality | Does not automatically fix broken `equals()` on elements or domain classes |
| `Objects.hashCode(o)` | Returns `0` if `o == null`, otherwise calls `o.hashCode()` | Does not produce a valid hash if `o.hashCode()` itself is wrong |
| `Objects.hash(values...)` | Combines multiple values via `Arrays.hashCode(Object[])` | Does not know on its own which attributes `equals()` uses to define equality |
| `Objects.compare(a, b, c)` | Returns `0` if same reference; otherwise delegates to `c.compare(a, b)` | Does not fix a broken comparator, nor turn approximate matching into a valid ordering |

All of these methods are useful when applied **on top of a valid contract**. Calling the standard library does not automatically make input data, custom comparisons, or design decisions correct.

## 2. The `equals()` and `hashCode()` contract remains your class's responsibility

### Equality must be an equivalence relation

For non-`null` object references, the `Object.equals(Object)` contract requires:

- **Reflexive:** `x.equals(x)` is `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` have the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
- **Consistent:** when relevant data does not change, repeated calls return the same result.
- **Null handling:** `x.equals(null)` is `false`.

Additionally, for any equal `x` and `y`:

~~~text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
~~~

The converse is not required: two distinct objects may still share the same hash code (*collision*).

An asymmetric `equals()` might return `true` from A to B yet `false` from B to A. `Objects.equals(A, B)` **does not check both directions**. When both are non-`null` and have different references, it uses `A.equals(B)`, so the symmetry bug remains.

### `Objects.equals()` handles null, does not validate the contract

You can understand `Objects.equals(a, b)` behavior through the roughly equivalent snippet:

~~~java
return a == b || (a != null && a.equals(b));
~~~

This is an **explanatory code fragment** inside a method returning `boolean`.

- Both references `null` → `true`.
- One side `null` and the other non-`null` → `false`.
- Both references point to the same object → `true` without calling `equals()`.
- Two objects with different references → delegates to `a.equals(b)`.

Subtle point: the identical-reference case can return `true` even if the class wrongly implemented `x.equals(x)` to return `false`. This **does not** prove the class obeys reflexivity. When testing the contract, test `x.equals(x)` directly alongside separate instances, rather than only calling `Objects.equals()`.

## 3. `Objects.hash()` does not pick the right fields for you

Suppose the system decides two customers are equal when they share the same `customerId`, regardless of differing `displayName`.

**Correct for equality definition:**

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return Objects.equals(customerId, other.customerId);
}
~~~

This is a **code fragment inside the `Customer` class**. `Objects.equals(customerId, other.customerId)` helps handle a nullable field (if the design permits it), yet does not decide on its own that ID is the business key.

**Wrong when computing hash:**

~~~java
@Override
public int hashCode() {
    return Objects.hash(customerId, displayName);
}
~~~

If two customers have the same ID yet different display names, `equals()` returns `true` while `Objects.hash(customerId, displayName)` can return two different codes. Thus the class has violated the contract, even though `Objects.hash(...)` is a standard API used with completely valid syntax.

**Correct when only ID determines equality:**

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(customerId);
}
~~~

Or you can use `Objects.hash(customerId)`; the same ID will generate the same result in both cases. They **do not necessarily return the same number**: `Objects.hashCode(x)` with `x != null` is literally `x.hashCode()`, whereas `Objects.hash(x)` hashes an argument array with **one element**, so it typically uses a different formula. Choose **the same strategy across all instances of the same class**, without comparing the two methods as if their numbers meant the exact same thing.

`Objects.hashCode(null)` returns `0`, yet safe `null` handling cannot save a case where two equal objects have different data hashed.

## 4. `Objects.compare()` does not validate the Comparator

A valid comparator must establish an ordering with consistent properties, especially transitivity:

- If `compare(a, b) < 0` and `compare(b, c) < 0`, then `compare(a, c) < 0`.
- If `compare(a, b) == 0`, comparing `a` and `b` against any third value must yield **the same result sign**.
- The sign of `compare(a, b)` is opposite the sign of `compare(b, a)`.

Returning `0` for two values simply because they are "close within epsilon" is a common bug. Suppose `a=0`, `b=1`, `c=2` and the closeness threshold is `1`:

~~~java
Comparator<Integer> near = (a, b) ->
    Math.abs((long) a - b) <= 1 ? 0 : Integer.compare(a, b);
~~~

This is an **illustrative fragment of a broken comparator**, with `import java.util.Comparator;`. We have `near.compare(0, 1) == 0`, `near.compare(1, 2) == 0`, yet `near.compare(0, 2) < 0`. The "equal under comparator" groups are not transitive; the ordering is invalid. Using `long` in the subtraction only avoids `int` difference overflow, **not fixing the logic error**.

Calling:

~~~java
Objects.compare(0, 1, near);
Objects.compare(1, 2, near);
Objects.compare(0, 2, near);
~~~

still yields the three respective results `0`, `0`, and a negative number: the utility merely forwarded the work to the supplied comparator. Using a broken comparator in `List.sort()` can lead to unreliable results or exceptions on certain data/algorithms; using it in `TreeSet`/`TreeMap` can cause keys that are "duplicates" under the comparator to be managed inconsistently.

One more detail: `Objects.compare(a, b, c)` returns `0` immediately if `a == b`, without calling `c.compare(a, b)` in that case. Therefore, testing with **the same reference** can mask a bug where a comparator fails to return `0` for an object with itself. When validating a comparator, call `compare(...)` directly on representative pairs and triples.

### Do not write a Comparator using subtraction

~~~java
Comparator<Integer> broken = (a, b) -> a - b;
Comparator<Integer> correct = Integer::compare;
~~~

`broken.compare(Integer.MIN_VALUE, 1)` returns a positive number due to `int` overflow, whereas `Integer.compare(Integer.MIN_VALUE, 1)` returns a negative number as expected for ascending order. Passing `broken` into `Objects.compare(...)` **does not** make subtraction safer. Fix the comparator using `Integer.compare`, `Comparator.comparingInt(...)`, or appropriate type-specific comparisons.

## 5. Runnable Java 17 example: three kinds of bugs and corresponding utilities

Create the file **`ObjectsContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectsContractDemo {

    // Wrong: equals checks only ID, hashCode checks name as well.
    static final class BrokenCustomer {
        private final String id;
        private final String displayName;

        BrokenCustomer(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenCustomer other)) {
                return false;
            }
            return Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, displayName);
        }
    }

    // Correct: both equals and hashCode are based on the immutable ID.
    static final class GoodCustomer {
        private final String id;
        private final String displayName;

        GoodCustomer(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof GoodCustomer other)) {
                return false;
            }
            return Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    // Wrong: same ID, yet only the allowMatch=true side recognizes the other.
    static final class OneWay {
        private final String id;
        private final boolean allowMatch;

        OneWay(String id, boolean allowMatch) {
            this.id = Objects.requireNonNull(id);
            this.allowMatch = allowMatch;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof OneWay other)) {
                return false;
            }
            return allowMatch && Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    public static void main(String[] args) {
        BrokenCustomer brokenA = new BrokenCustomer("C-1", "A");
        BrokenCustomer brokenB = new BrokenCustomer("C-1", "B");

        System.out.println("broken equals: "
                + Objects.equals(brokenA, brokenB));
        System.out.println("broken same hash: "
                + (brokenA.hashCode() == brokenB.hashCode()));

        GoodCustomer goodA = new GoodCustomer("C-1", "A");
        GoodCustomer goodB = new GoodCustomer("C-1", "B");
        Set<GoodCustomer> unique = new HashSet<>();
        unique.add(goodA);
        unique.add(goodB);

        System.out.println("good equals: "
                + Objects.equals(goodA, goodB));
        System.out.println("good same hash: "
                + (goodA.hashCode() == goodB.hashCode()));
        System.out.println("good set size: " + unique.size());

        OneWay yes = new OneWay("same", true);
        OneWay no = new OneWay("same", false);
        System.out.println("one way forward: " + Objects.equals(yes, no));
        System.out.println("one way backward: " + Objects.equals(no, yes));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        System.out.println("array equals: "
                + Objects.equals(arrayA, arrayB));
        System.out.println("array deep equals: "
                + Objects.deepEquals(arrayA, arrayB));
        System.out.println("deep equals broken customers: "
                + Objects.deepEquals(brokenA, brokenB));

        Comparator<Integer> near = (a, b) ->
                Math.abs((long) a - b) <= 1
                ? 0 : Integer.compare(a, b);

        System.out.println("near 0,1: " + Objects.compare(0, 1, near));
        System.out.println("near 1,2: " + Objects.compare(1, 2, near));
        System.out.println("near 0,2: " + Objects.compare(0, 2, near));

        Comparator<Integer> subtraction = (a, b) -> a - b;
        System.out.println("overflow sign broken: "
                + (Objects.compare(Integer.MIN_VALUE, 1, subtraction) > 0));
        System.out.println("overflow sign fixed: "
                + (Objects.compare(Integer.MIN_VALUE, 1, Integer::compare) < 0));

        System.out.println("null equals: " + Objects.equals(null, null));
        System.out.println("null hashCode: " + Objects.hashCode(null));
    }
}
~~~

Compile and run:

~~~bash
javac ObjectsContractDemo.java
java ObjectsContractDemo
~~~

**Output:**

~~~text
broken equals: true
broken same hash: false
good equals: true
good same hash: true
good set size: 1
one way forward: true
one way backward: false
array equals: false
array deep equals: true
deep equals broken customers: true
near 0,1: 0
near 1,2: 0
near 0,2: -1
overflow sign broken: true
overflow sign fixed: true
null equals: true
null hashCode: 0
~~~

Explanation:

1. The two `BrokenCustomer` instances share the same ID, so `Objects.equals(...)` returns `true`. However, the two names `"A"` and `"B"` yield different hashes from `Objects.hash(id, displayName)`; using the utility does not rescue the `equals/hashCode` contract.
2. The two `GoodCustomer` instances share the same ID and have matching hashes. `HashSet` deduplicates the identical-ID instance, so the size is `1`.
3. The two `OneWay` instances with the same ID return different results depending on call direction. `Objects.equals(...)` preserves the asymmetry bug because it delegates to the left operand.
4. The two `int[]` arrays have different references so `Objects.equals(...)` returns `false`, yet `Objects.deepEquals(...)` compares array contents and returns `true`. For two `BrokenCustomer` instances (not arrays), `deepEquals` still returns `true` via ID-based `equals`, **without detecting the two differing hash codes**.
5. Comparator `near` gives `0` for `0,1` and `1,2` yet `-1` for `0,2`; that demonstrates inconsistency for a comparator-based equivalence relation.
6. Subtraction on `int` overflows, inverting the comparison sign; replacing it with `Integer.compare` fixes **the comparator**, while `Objects.compare` merely forwards the call.
7. `Objects.equals(null, null)` and `Objects.hashCode(null)` show the null-handling benefit of the utilities.

The example intentionally uses broken classes to illustrate what not to do; **do not use `BrokenCustomer` or `OneWay` as keys in a real system**. By contrast, `GoodCustomer` has an immutable ID key and synchronized `equals()/hashCode()`.

## 6. How "deep" is `deepEquals()`?

`Objects.deepEquals(a, b)` is especially useful when **both arguments are arrays**, including nested arrays. Example:

~~~java
Object[] x = {new int[] {1, 2}, new String[] {"A", "B"}};
Object[] y = {new int[] {1, 2}, new String[] {"A", "B"}};

System.out.println(Objects.deepEquals(x, y)); // true
~~~

This is an **illustrative code snippet** with `import java.util.Objects;`. The function handles inner arrays by content via `Arrays`' deep comparison mechanism.

However, `deepEquals()` **is not a tool that automatically inspects arbitrary object graphs**:

- For two ordinary non-array objects, it still relies on the object's `equals()` to determine equality. If the implementation is wrong, the result can be wrong.
- For `List<int[]>`, calling `Objects.deepEquals(listA, listB)` on two separate lists uses `List.equals()`; at the element level, two separate arrays still have identity equality. The utility does not automatically replace `List.equals()` with a deep-comparison algorithm for array elements.
- For arrays with cyclic references (*cyclic arrays*), do not assume the deep-comparison method can handle arbitrary graphs; recursion can cause `StackOverflowError`.

If a domain type containing arrays needs **value equality**, design a wrapper class whose `equals()` calls the appropriate `Arrays.equals`/`Arrays.deepEquals` and whose `hashCode()` matches (`Arrays.hashCode`/`Arrays.deepHashCode`), with defensive copying if data can change. The utility cannot infer those rules on its own.

## 7. Fixing at the root: designing proper contracts and concrete tests

### For `equals()`

1. Define "two equal objects" according to business rules: same identity or same value fields?
2. Implement `public boolean equals(Object)` with the exact signature and `@Override`.
3. Test pairs and triples of **distinct instances** to verify reflexivity, symmetry, and transitivity; test `null` and wrong types.
4. If the requirement is only "close within a threshold", extract it into `isCloseTo(...)` or a similar API. Approximate matching does not guarantee transitivity and is usually unsuitable as `equals()`.

### For `hashCode()`

1. Choose fields/keys that produce **the same hash value whenever `equals()` is `true`**.
2. Ensure keys do not change while the object is inside a `HashSet`/`HashMap`.
3. Specifically test two instances with `equals()==true` and equal hashes. Do not require distinct objects to have distinct hashes.
4. Choose `Objects.hashCode(singleKey)` or `Objects.hash(key1, key2, ...)` when matching the equality definition. Choosing an API does not replace deciding which fields are valid.

### For `Comparator`

1. Use `Comparator.comparing(...)`, `comparingInt/Long/Double(...)`, or `Integer.compare`/`Long.compare` instead of manual subtraction prone to overflow.
2. Test sign symmetry, transitivity, and the `compare(a,b)==0` rule against any third value.
3. Do not put non-transitive approximate matching into a comparator used for sorting; if "close within threshold" lookup is needed, use a dedicated filtering/matching method.
4. Account for `null`, NaN, negative zero, and multi-criteria ordering. `Objects.compare(a,b,c)` **does not automatically handle one-sided null**: if `a` differs from `b`, the comparator is called and may throw if it does not support `null`.
5. If used in `TreeSet`/`TreeMap`, determine whether `compare(a,b)==0` properly represents "two duplicate keys" for your needs. Using a comparator different from the object's equality rule can cause ordered sets to behave differently from `HashSet`.

### Quick diagnostic table

| Symptom | Cause to check first | Fix |
| --- | --- | --- |
| `Objects.equals(a,b)` differs from `Objects.equals(b,a)` | `a.equals(b)` / `b.equals(a)` lacks symmetry | Fix `equals()` on the domain type |
| Two objects are equal yet `HashSet` treats them as different | `hashCode()` is inconsistent or key data was mutated | Align keys used in `equals()/hashCode()` and keep them immutable while stored |
| `Objects.deepEquals(...)` does not compare as intended | Data is not an array or elements have different equality than expected | Define equality at the proper data layer |
| `Objects.compare(...)` gives strange ordering | Comparator overflows, lacks transitivity, or mishandles null/NaN | Fix the comparator; test triples and edge values |
| `TreeSet` drops "different" elements | Comparator returns `0` for keys meant to be distinct | Add a stable secondary tie-breaker key matching business rules |

**Key takeaway:** `Objects` makes code **shorter, more readable, and `null`-safe where designed to support it**. It cannot define domain equality or ordering contracts on your behalf. When `equals()`, `hashCode()`, or `Comparator` is wrong, you must **fix it where the rules are defined and test the contract**; wrapping calls in `Objects.equals()`, `Objects.hash()`, or `Objects.compare()` does not turn broken rules into right ones.