# Testing `null`, `NaN`, `+0.0`, `-0.0`, Arrays, and Nested Structures in the Java Object Contract

An `equals()` method that looks right on ordinary data can still fail when encountering `null`, special floating-point values, arrays, or nested objects. Discrepancies often entail an inconsistent `hashCode()`, or a `compareTo()`/`Comparator` treating two keys as tied while `equals()` does not consider them equal. Consequences can include a `HashSet` holding business-duplicate elements, a `HashMap` failing key lookups, or a `TreeSet` discarding data unexpectedly.

This lesson focuses on **how to define expectations, implement, and test the contract** in Java 17+: distinguishing the `==` operator from value equality, choosing semantics for `double`/`float`, comparing arrays at the right depth, and keeping the contract stable with nested structures. No single comparison rule fits every model: you must decide what "equal" means for a specific object type, then apply that same rule consistently across `equals()`, `hashCode()`, and ordering if needed.

## 1. Invariants to Verify Before Edge Cases

For non-`null` objects `x`, `y`, `z`:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y) == y.equals(x)`.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** results do not change across calls if the state participating in comparison does not change.
5. **Against `null`:** `x.equals(null)` must be `false`.
6. **Hash constraint:** if `x.equals(y)`, it is **mandatory** that `x.hashCode() == y.hashCode()`. Two unequal objects **may still** share a hash; do not use the converse as a standard.
7. **Ordering constraint:** `compareTo`/`Comparator` must be sign-consistent when reversing arguments, transitive, and consistent across comparison equivalence classes. For `TreeSet`/`TreeMap`, two keys yielding `compare(...) == 0` are treated as the same key. If a data type expects uniqueness per `equals`, design the comparator to be **consistent with equals**, meaning `compare(x,y)==0` if and only if `x.equals(y)`.

Tests should create **two independent instances with equal values**, because `x.equals(x)` always returns true due to the `this == other` branch and can mask field-comparison bugs. For every pair specified as equal, verify both directions of `equals` and matching hashes; for every boundary value, test intentional differences.

### Minimum Test Case Table

| Case | What to check | Java platform expectation |
| --- | --- | --- |
| Object against `null` | `x.equals(null)` | `false` |
| Both references `null` | `Objects.equals(null, null)` | `true` |
| Nullable property | Two objects with `null` field in the same position | Equal if other fields match |
| `NaN` with arithmetic operator | `Double.NaN == Double.NaN` | `false` |
| Two `NaN` values under `Double.equals` | Including different bit payloads | `true` |
| `+0.0` vs `-0.0` using `==` | `+0.0 == -0.0` | `true` |
| `+0.0` vs `-0.0` using `Double.equals` | Comparing two wrappers | `false` |
| Primitive arrays with same elements | `Arrays.equals(a,b)` | `true` |
| Two nested arrays with same data | `Arrays.deepEquals(a,b)` | `true` for compatible structures without cycles |
| Nested collection containing arrays | `List.equals` on array-typed elements | Does **not** automatically become content-based array comparison |
| Custom object | `equals` paired with `hashCode` | Two equal objects have equal hashes |
| Key in sorted collection | `compare(x,y)==0` | `TreeSet`/`TreeMap` treats them as one key |

## 2. `null`: Check Both the Receiver and Member Fields

`null` is not an instance on which to invoke a method. The expression `null.equals(x)` is semantically invalid, and if a reference variable is `null` when calling `reference.equals(x)`, it throws `NullPointerException`. Using `Objects.equals(a,b)` compares two references safely:

```java
Objects.equals(null, null);      // true
Objects.equals(null, "value");   // false
Objects.equals("x", "x");        // true
Objects.hashCode(null);          // 0
```

The lines above are illustrative expressions, requiring `import java.util.Objects;` when placed in a Java class.

In a value class with a nullable `name` field, write `Objects.equals(name, that.name)` instead of `name.equals(that.name)`. In an array or collection, clearly distinguish a **`null` collection reference**, an **empty collection**, and a **collection containing a `null` element**. These are three distinct states depending on the business contract.

Do not arbitrarily convert every `null` into a default value if the model does not call for it. If the constructor forbids `null`, use `Objects.requireNonNull(...)` and test that it throws at construction boundaries; if `null` is allowed, `equals`/`hashCode` must handle it consistently.

For ordered comparisons, `Comparator.naturalOrder()` does not accept `null`; `Comparator.nullsFirst(...)` or `nullsLast(...)` establishes a clear rule when an ordering needs to accommodate `null`. An object's `equals()` must never treat itself as equal to `null` just because a comparator places `null` first or last.

## 3. `NaN` and Floating-Point Numbers: `==` Differs From `Double.equals()`

Under IEEE 754 and Java semantics, `NaN` does not equal any value when compared with the `==` operator, including itself:

```java
double a = Double.NaN;
double b = Double.longBitsToDouble(0x7ff8000000000001L);

// a == b               => false
// Double.isNaN(a)       => true
// Double.isNaN(b)       => true
// Double.compare(a, b)  => 0
// Double.valueOf(a).equals(Double.valueOf(b)) => true
```

`b` has a different NaN payload from `a` in raw bits. `Double.equals` uses `Double.doubleToLongBits` to inspect bits with **canonicalized NaN values**. Hence it treats all NaN values as equal. `Double.hashCode` uses a compatible bit interpretation, so NaN values deemed equal by `Double.equals` also share the same hash. `Float.equals`/`Float.hashCode` apply the corresponding rule to `float`.

**Do not use `x == y` for `double` in an `equals()` while using `Double.hashCode(x)` if you intend NaNs to be equal**: two objects with model-equivalent NaNs will be rejected by `equals` while other components may match. This might not break the one-way hash implication, yet it **diverges from the intended semantics**. To implement `Double`-style semantics, use `Double.compare(a,b)==0` and `Double.hashCode(a)`, or `Double.doubleToLongBits(a)==Double.doubleToLongBits(b)` with the corresponding hash.

### `+0.0` and `-0.0`: Same Operator, Different Wrapper

```java
// +0.0 == -0.0                                      => true
// Double.compare(-0.0, +0.0) < 0                     => true
// Double.valueOf(+0.0).equals(Double.valueOf(-0.0)) => false
// Double.hashCode(+0.0) == Double.hashCode(-0.0)    => false
```

Reason: `+0.0` and `-0.0` have different bit representations, even though `==` considers them equal. `Double.compare` defines a total order convenient for sorting: `-0.0` precedes `+0.0`; NaNs follow all other numeric values and are compared as a single group. Test `Double.compare(a,b)` at `-Infinity`, finite numbers, `-0.0`, `+0.0`, `+Infinity`, and `NaN` when a class requires ordering.

If the business domain wants to **treat both zeros as the same value**, normalize both before comparison **and before hashing**, for example:

```java
static double normalizeZero(double value) {
    return value == 0.0d ? 0.0d : value;
}

static boolean sameMetric(double left, double right) {
    return Double.compare(normalizeZero(left), normalizeZero(right)) == 0;
}

static int metricHash(double value) {
    return Double.hashCode(normalizeZero(value));
}
```

These are illustrative methods placed inside a class. This rule preserves `Double.compare` behavior for NaN, merges `+0.0` with `-0.0`, and avoids violating the hash contract. Choose this approach **only when it matches the object's specification**; do not silently alter rules in a codebase that already depends on distinguishing signed zeros. When floating-point numbers represent measurements, decide separately whether a tolerance is acceptable; **never arbitrarily use approximate comparison `abs(a-b) < epsilon` for `equals`**, because that relation is generally non-transitive (A is near B, B is near C, yet A is not near C) and also makes hash keys hard to keep valid.

## 4. Arrays: An Array's Own `equals()`, `Arrays.equals`, and `Arrays.deepEquals`

Java arrays **do not override `Object.equals`**, so `a.equals(b)` compares object identity. Two distinct arrays containing the exact same elements still return `false`. Use `Arrays.equals` to compare elements in one dimension:

```java
int[] a = {1, 2};
int[] b = {1, 2};

a.equals(b);        // false
Arrays.equals(a,b); // true
Arrays.hashCode(a) == Arrays.hashCode(b); // true
```

`import java.util.Arrays;` is required when placing these expressions into a complete class. `Arrays.equals` provides overloads for primitive arrays and object arrays. For `Object[]`, element comparison uses each element's `equals` semantics; if an element is itself an array, that comparison remains a **reference comparison**.

For multi-level structures, use `Arrays.deepEquals(Object[],Object[])` and `Arrays.deepHashCode(Object[])`:

```java
Object[] first = {new int[]{1, 2}, new Object[]{"A", new String[]{"B"}}};
Object[] second = {new int[]{1, 2}, new Object[]{"A", new String[]{"B"}}};

Arrays.equals(first, second);     // false: array-typed elements are different references
Arrays.deepEquals(first, second); // true: compares nested arrays by content
Arrays.deepHashCode(first) == Arrays.deepHashCode(second); // true
```

A two-dimensional array like `int[][]` is also an array of `int[]` references, so `deepEquals/deepHashCode` is required when expecting content comparison at every level. `Arrays.deepEquals` applies to `Object[]` at the outer level; **do not** call `Arrays.deepEquals(int[], int[])` directly because no such overload exists. For one-dimensional primitive arrays, choose `Arrays.equals(int[],int[])` and `Arrays.hashCode(int[])`.

Two array references that are both `null` are treated as equal by `Arrays.equals`, whereas one `null` and one empty array are unequal. `Arrays.deepEquals` also handles two `Object[]` references that are both `null`. Self-referential cyclic structures (an array referencing itself, or two arrays referencing each other in a cycle) **are not suitable for this deep recursion**; design graph comparison with dedicated cycle detection when data contains cycles.

**Do not mechanically pair `Arrays.deepEquals(...)` with `Arrays.hashCode(...)`.** If equality is evaluated at all levels, hashing must likewise inspect all levels; otherwise two equal objects can produce different hashes.

### `record` and Arrays: Auto-Generated `equals` May Not Compare Deeply

Java `record` auto-generates `equals`/`hashCode` from its components, yet an array-typed component still uses the array's identity comparison behavior. Therefore:

```java
record IntBundle(int[] values) {}

new IntBundle(new int[]{1, 2})
    .equals(new IntBundle(new int[]{1, 2})); // false
```

That is why you must not assume a `record` automatically performs deep equality for every component type. If an array is part of value identity, write a custom contract and appropriate defensive copying, or represent it with an immutable collection type that has content semantics.

## 5. Lists, Sets, Maps, and Nested Structures

`List.equals` compares elements sequentially by order; `Set.equals` compares element sets regardless of order; `Map.equals` compares key–value mappings. These contracts rely on the `equals/hashCode` of the elements or keys/values, so **inner contents are not automatically compared deeply if the element type itself lacks a value contract**.

```java
List<List<String>> left = List.of(List.of("a", "b"), List.of("c"));
List<List<String>> right = List.of(List.of("a", "b"), List.of("c"));
// left.equals(right) => true: nested Lists have element-wise equality.

List<int[]> leftArrays = List.of(new int[]{1, 2});
List<int[]> rightArrays = List.of(new int[]{1, 2});
// leftArrays.equals(rightArrays) => false: int[] elements compare by identity.
```

These are illustrative expressions inside a class with `import java.util.List;`. With nested objects, clearly define which levels participate in identifying the object and which levels are ignored. An object wrapping `List<List<String>>` will compare contents across List levels under built-in contracts, whereas when a list contains `int[]` or custom objects that do not override `equals`, extra handling is required.

For a `Map` whose keys are arrays or mutable objects, subtle bugs easily arise: mutating fields participating in `equals/hashCode` **after insertion into a `HashMap`/`HashSet`** can prevent finding the key again because the lookup bucket differs from the insertion bucket. The solution is designing keys whose equality-related state is appropriately fixed, and **defensively copying** when storing or returning mutable arrays/collections.

If you need to compare a nested structure mixing `Map`, `List`, arrays, and custom objects, you cannot solely call `Objects.deepEquals` and assume a universal deep-equality contract for all collection kinds. `Objects.deepEquals` only has special array handling when both arguments are arrays; it does not recursively understand the business rules of an arbitrary object graph.

## 6. Complete Java 17 Example: Verifying Equality, Hashing, and Nested Data

Create **`ObjectContractEdgeCases.java`**. `Snapshot` is a value class with nullable `name`, a `double`, a primitive array, and `List<List<String>>`. The constructor creates copies of the array and Lists so callers cannot mutate state participating in `equals/hashCode` after creation. In this example, inner Lists must not contain `null` elements; the outer List must also not contain `null` Lists when not `null` overall.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class ObjectContractEdgeCases {
    private static final class Snapshot {
        private final String name;
        private final double metric;
        private final int[] samples;
        private final List<List<String>> groups;

        Snapshot(String name, double metric, int[] samples,
                 List<List<String>> groups) {
            this.name = name;
            this.metric = metric;
            this.samples = samples == null ? null : samples.clone();
            this.groups = groups == null ? null
                    : groups.stream().map(List::copyOf).toList();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Snapshot that)) {
                return false;
            }
            return Objects.equals(name, that.name)
                    && Double.compare(metric, that.metric) == 0
                    && Arrays.equals(samples, that.samples)
                    && Objects.equals(groups, that.groups);
        }

        @Override
        public int hashCode() {
            int result = Objects.hash(name, Double.hashCode(metric), groups);
            return 31 * result + Arrays.hashCode(samples);
        }
    }

    record IntBundle(int[] values) {}

    private static void check(boolean result, String description) {
        if (!result) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        double otherNaN = Double.longBitsToDouble(0x7ff8000000000001L);
        int[] a = {1, 2};
        int[] b = {1, 2};

        Object[] deepA = {new int[]{1, 2},
                new Object[]{"A", new String[]{"B"}}};
        Object[] deepB = {new int[]{1, 2},
                new Object[]{"A", new String[]{"B"}}};

        List<List<String>> groupsA = List.of(List.of("a", "b"), List.of("c"));
        List<List<String>> groupsB = List.of(List.of("a", "b"), List.of("c"));

        Snapshot first = new Snapshot(null, Double.NaN, a, groupsA);
        Snapshot second = new Snapshot(null, otherNaN, b, groupsB);
        Snapshot plusZero = new Snapshot(null, +0.0, a, groupsA);
        Snapshot minusZero = new Snapshot(null, -0.0, b, groupsB);
        Snapshot emptyA = new Snapshot(null, 0.0, null, null);
        Snapshot emptyB = new Snapshot(null, 0.0, null, null);

        // Verify contract, independent of running with java -ea.
        check(!first.equals(null), "non-null object must differ from null");
        check(first.equals(first), "reflexivity");
        check(first.equals(second) && second.equals(first), "symmetry");
        check(first.hashCode() == second.hashCode(), "equal objects' hashes");
        check(!plusZero.equals(minusZero), "signed zeros are distinct");
        check(emptyA.equals(emptyB), "null fields must compare safely");
        check(Arrays.equals(a, b), "primitive array contents");
        check(Arrays.deepEquals(deepA, deepB), "nested array contents");
        check(Arrays.deepHashCode(deepA) == Arrays.deepHashCode(deepB),
                "nested array hash");

        Set<Snapshot> snapshots = new HashSet<>();
        snapshots.add(first);
        snapshots.add(second);

        System.out.println("Objects.equals(null,null): "
                + Objects.equals(null, null));
        System.out.println("snapshot.equals(null): " + first.equals(null));
        System.out.println("null fields equal: " + emptyA.equals(emptyB));
        System.out.println("NaN == NaN: " + (Double.NaN == Double.NaN));
        System.out.println("raw NaN bits differ: "
                + (Double.doubleToRawLongBits(Double.NaN)
                    != Double.doubleToRawLongBits(otherNaN)));
        System.out.println("Double.equals(NaN payloads): "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(otherNaN)));
        System.out.println("+0.0 == -0.0: " + (+0.0 == -0.0));
        System.out.println("Double.equals(+0.0,-0.0): "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));
        System.out.println("Double.compare(-0.0,+0.0)<0: "
                + (Double.compare(-0.0, +0.0) < 0));
        System.out.println("array Object.equals: " + a.equals(b));
        System.out.println("Arrays.equals: " + Arrays.equals(a, b));
        System.out.println("nested Arrays.equals: "
                + Arrays.equals(deepA, deepB));
        System.out.println("Arrays.deepEquals: "
                + Arrays.deepEquals(deepA, deepB));
        System.out.println("Arrays.deepHashCode match: "
                + (Arrays.deepHashCode(deepA) == Arrays.deepHashCode(deepB)));
        System.out.println("record array equals: "
                + new IntBundle(new int[]{1, 2})
                    .equals(new IntBundle(new int[]{1, 2})));
        System.out.println("nested List.equals: "
                + groupsA.equals(groupsB));
        System.out.println("NaN snapshots equal: " + first.equals(second));
        System.out.println("NaN snapshot hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("signed-zero snapshots equal: "
                + plusZero.equals(minusZero));
        System.out.println("HashSet size: " + snapshots.size());
    }
}
```

Compile/run with JDK 17+:

```bash
javac ObjectContractEdgeCases.java
java ObjectContractEdgeCases
```

Standard output:

```text
Objects.equals(null,null): true
snapshot.equals(null): false
null fields equal: true
NaN == NaN: false
raw NaN bits differ: true
Double.equals(NaN payloads): true
+0.0 == -0.0: true
Double.equals(+0.0,-0.0): false
Double.compare(-0.0,+0.0)<0: true
array Object.equals: false
Arrays.equals: true
nested Arrays.equals: false
Arrays.deepEquals: true
Arrays.deepHashCode match: true
record array equals: false
nested List.equals: true
NaN snapshots equal: true
NaN snapshot hashes equal: true
signed-zero snapshots equal: false
HashSet size: 1
```

Explanation of verification meaning:

- `first` and `second` use two NaNs with different bit payloads, independent `int[]` arrays, and two independent `List<List<String>>` structures. They are still equal because `Snapshot.equals` handles each type properly; `hashCode` yields the same result and `HashSet` retains only one instance per equality.
- `plusZero` and `minusZero` differ because they intentionally follow `Double.compare` semantics, matching the `Double.hashCode` hashing component. This is a design decision, not a requirement that every numeric object must distinguish both zeros.
- `emptyA`/`emptyB` test nullable `name`, `samples`, and `groups`. `Arrays.equals(null,null)` and `Objects.equals(null,null)` support this rule without throwing `NullPointerException`.
- Two `IntBundle` records carrying arrays with identical contents are still unequal, because arrays compare by identity.
- `Snapshot` defensively copies in the constructor and provides no getter returning the mutable array directly. If a getter is needed, it must return `samples.clone()` or an unmodifiable view/copy; you must also ensure nested elements are not mutable objects that alter equality.

The example uses cycle-free data and inner lists that contain no `null`. If the input contract permits `null` sublists or `null` elements, you must choose an appropriate copying strategy and equality definition before using it in production.

## 7. Testing Ordered Comparisons: Avoiding Comparators That Lose Keys

`Comparable`/`Comparator` is an **ordering** contract, not a duplicate of `equals`. For example, `Comparator.comparingDouble(...)` orders according to `Double.compare`, so it distinguishes signed zeros and groups NaNs. However, if a comparator only checks `metric` while `Snapshot.equals` also checks `name`, `samples`, and `groups`, two distinct `Snapshot` objects can be ranked `0`. With `TreeSet`/`TreeMap`, that causes one of them to be treated as a duplicate key.

An appropriate comparator must inspect all identifying components in a manner consistent with `equals`, or document that the sorted collection uses a **different key concept**. For arrays and nested structures, defining lexicographical ordering requires clear rules (element order, length, `null`, signed zeros, NaN), avoiding reliance on `toString` or hash values.

Test cases for the comparator if used:

1. `sign(compare(x,y)) == -sign(compare(y,x))`, checking signs safely with `Integer.signum`.
2. If `compare(x,y)>0` and `compare(y,z)>0`, then `compare(x,z)>0`; similarly for `<0`.
3. If `compare(x,y)==0`, then the signs of `compare(x,z)` and `compare(y,z)` must match for all `z`.
4. If consistency with equals is needed: `compare(x,y)==0` holds precisely when `x.equals(y)`; specifically test `null` (when supported by the comparator), NaN, signed zeros, equal-content arrays, and differing nested fields.
5. With `TreeSet`, test inserting two equal instances and two distinct instances per specification to make sure they are not erroneously merged.

Do not write comparators of the form `(int)(a-b)` for floating-point or wide integer numbers: this can overflow, truncate fractional parts, turn NaN into bogus values, and break transitivity. Use `Double.compare`, `Integer.compare`, or an appropriate standard comparator.

## 8. Designing Test Data and Automated Tests

To verify the contract systematically, build a case matrix rather than testing a single pair:

| Data group | Representative cases | What to assert |
| --- | --- | --- |
| `null` | `null` object; `null`/non-`null` fields; `null`/empty arrays | No unexpected exceptions, obeys equality rules |
| Floating-point | normal numbers, two NaNs with different bits, `±0.0`, `±Infinity` | Equality, hash, and ordering match specification |
| Arrays | same reference, two independent arrays with equal elements, differing elements, differing lengths | Proper shallow/deep behavior; matching hash |
| Nested | `List<List<T>>`, arrays inside `List`, arrays inside `Map`, child objects | Proper semantics at each level |
| Stability | Mutable inputs modified after constructor | Key state remains unchanged if class promises immutability |
| Equivalence | three objects `x,y,z` with equal contents and boundary data | Reflexivity, symmetry, transitivity, hash |
| Collections | `HashSet`/`HashMap` and `TreeSet`/`TreeMap` if a comparator exists | No erroneous merging or lost key lookups |

Use descriptive test names, such as `equalInstancesWithDistinctNaNPayloadsShareHash`, `negativeZeroAndPositiveZeroFollowChosenPolicy`, `nestedPrimitiveArraysUseDeepEquality`, and `defensiveCopyKeepsHashStable`. With JUnit 5, you can organize `@ParameterizedTest` with `@MethodSource` to run value pair tables and call assertions such as `assertEquals`/`assertNotEquals`/`assertTrue`. Remember that `assertEquals(double, double)` in testing libraries has its own rules for floating-point types; when verifying the **exact contract you built**, assert explicit expressions such as `Double.compare(...)`, `x.equals(y)`, `Objects.equals(...)`, `Arrays.equals(...)`, or `Arrays.deepEquals(...)`, rather than assuming every `assertEquals` overload uses primitive `==` logic.

With property-based testing (such as jqwik or QuickTheories) if available in the project, generate values including controlled `null`s, varying array sizes, nested collections, and different NaN bit patterns; check the invariants in Section 1 instead of fixed outputs alone. For recursive data, set a depth limit and avoid cycles when the contract does not yet support cycles.

### Common Bugs to Proactively Catch

- Calling `a.equals(b)` with nullable `a` throws `NullPointerException`; use `Objects.equals` or ensure non-null first.
- Using `==` for a `double` field while expecting all NaNs to be equal; use `Double.compare`/`Double.hashCode` under the same policy.
- Treating `+0.0` and `-0.0` as equal in `equals` while using raw `Double.hashCode` in `hashCode`; this violates the hash contract. Normalize identically before both operations.
- Using `Arrays.equals` for `int[][]` or `Object[]` containing sub-arrays and assuming deep comparison; pair `Arrays.deepEquals` and `deepHashCode` properly.
- Letting a record auto-generate equality for an array component when content comparison is desired; change the representation type or implement an explicit contract.
- Using mutable arrays/collections as hash key fields while allowing external callers to mutate them; design defensive copies and immutable APIs.
- Writing a comparator that checks only part of an object and using `TreeSet` as if it enforced uniqueness across all of `equals`.
- Testing only the same reference, skipping two independent instances, boundary values, and the hash relationship.

**Self-check:** (1) Can two `double` NaNs with different bit payloads be equal under `Double.equals`? Yes. (2) Is `+0.0 == -0.0` true while `Double.equals` differs? Yes. (3) For two independent `int[][]` with identical data, should you use `Arrays.equals` or `Arrays.deepEquals`? `deepEquals`. (4) If you normalize signed zeros in `equals`, must you also normalize when hashing? Mandatory. (5) Do `HashMap` and `TreeMap` share the same definition of duplicate keys? No: `HashMap` relies on equality/hashing, whereas `TreeMap` relies on a comparator or natural ordering.

**Core principle:** establish one unified value semantics across **comparison – hashing – ordering – key immutability**, and then specifically test `null`, NaN, both signs of zero, 1D/multidimensional arrays, and every level of nested data. It is precisely these edge cases that expose an object contract that looks right yet proves too fragile for Java collections.
