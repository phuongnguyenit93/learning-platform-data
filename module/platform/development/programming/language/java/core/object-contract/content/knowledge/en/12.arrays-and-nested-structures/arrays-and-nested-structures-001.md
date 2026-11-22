# `equals()` and `hashCode()` of Arrays Default to Identity

## 1. Goal: Arrays with identical data are not necessarily “equal”

In Java, **arrays are objects**, including arrays of primitive types such as `int[]`, `double[]`. However, arrays **do not override** `Object.equals(Object)` or `Object.hashCode()` to compare their elements. By default, arrays use **object identity** rules:

- `arrayA.equals(arrayB)` is `true` when `arrayA` and `arrayB` point to **the exact same array**, not merely because two arrays have the same elements.
- `arrayA == arrayB` also checks for the same reference for two array variables.
- `arrayA.hashCode()` is the object's default identity-based hash code, **not based on element contents**. You must not infer that it is a memory address, or that every array is guaranteed to have a different hash from every other array.
- To compare or hash **by content**, choose the `java.util.Arrays` API appropriate for one-dimensional arrays or nested arrays; or design a wrapper class (value object) with explicit `equals`/`hashCode`.

Semantic standalone example:

```java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};
int[] alias = first;

System.out.println(first == second);        // false
System.out.println(first.equals(second));   // false
System.out.println(first == alias);         // true
System.out.println(first.equals(alias));    // true
```

This is an illustrative snippet (placed inside a method when run), not a standalone program. `first` and `second` are **two separate array objects**; `alias` merely references the `first` array again.

Conversely, `Arrays.equals(first, second)` is `true` because the two `int[]` arrays have equal corresponding elements. These two relations answer **two different questions**: whether they are the same object, and whether their contents are equivalent.

## 2. Why do `Object.equals` and `Object.hashCode` work by identity for arrays?

Java specifies that every array type is a reference type, inheriting appropriate behavior from `Object`. An array itself provides its `length` and elements accessed by index, but does not have an auto-generated content-based `equals` or `hashCode` like many value classes.

If a regular class does not override `equals`, `Object.equals` compares identity by default: `this == other`. The same applies to arrays. `Object.hashCode` provides a default hash code corresponding to object identity. Two calls on **the same array**, when no extraordinary out-of-contract factors are present, return the same hash code within a single run.

Points to remember:

1. **Same reference ⇒ `equals` is true and hashes are the same.** An array remains itself even when its elements change.
2. **Different references ⇒ `array1.equals(array2)` is false**, even when they have equal elements and lengths.
3. **Matching hash codes do not prove the same object.** `hashCode` returns an `int`, so different objects can collide.
4. **Mutating elements does not switch `array.hashCode()` to “content hashing”.** It remains identity-based; whereas `Arrays.hashCode(array)` is computed from the current elements.
5. `System.identityHashCode(array)` returns the object's default identity hash code, even if the object belongs to another class that overrode `hashCode`. Because arrays do not override that method, `array.hashCode() == System.identityHashCode(array)`.

Do not confuse an “identity hash” with a unique ID or a heap address. The Java contract **does not guarantee** unique hash codes across all objects and does not guarantee that default hash code values can be used to identify objects across application runs.

## 3. One-dimensional content comparison: switching from identity to `Arrays.equals`

When the goal is **the data** rather than the array object itself, use `java.util.Arrays` instead of `array.equals(...)`. Order, length, and the equality rules of each element are still respected:

| Data and purpose | Comparison | Corresponding hash |
| --- | --- | --- |
| Same array object | `a == b` or `a.equals(b)` if `a` is non-null | `a.hashCode()` (identity) |
| Two `int[]`, `byte[]`, `double[]` by content | `Arrays.equals(a, b)` appropriate overload | `Arrays.hashCode(a)` |
| Two `String[]` or `Object[]` comparing element-by-element | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| Two `int[][]` or `Object[]` with sub-arrays, comparing inner levels too | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |

```java
import java.util.Arrays;
// Inside main or a method:
int[] first = {1, 2};
int[] second = {1, 2};
System.out.println(first.equals(second));         // false: different identity
System.out.println(Arrays.equals(first, second)); // true: same content
System.out.println(Arrays.hashCode(first)
        == Arrays.hashCode(second));               // true
```

`Arrays.equals` and `Arrays.hashCode` for flat arrays form a **consistent pair**: if two arrays are equal under content comparison, then their two content hash codes must be equal; the reverse is not true due to hash collisions. The overloads handle `null` arrays with explicit types: two `null` arrays are equal, while `null` differs from an empty array. For `float[]`/`double[]`, the methods distinguish `+0.0` from `-0.0`, and treat NaN values as equal according to `Float`/`Double` rules, differing from the primitive `==` operator. The article *Arrays.equals() and Arrays.hashCode() for One-Dimensional Arrays* is where overloads, the hash formula, runnable examples, and these edge cases are explained in detail.

## 4. Why do nested arrays need deep comparison and hashing?

`int[][]` is an array whose direct elements are `int[]` arrays. When using `Arrays.equals(int[][], int[][])`, separate sub-arrays are compared by `Object.equals` of **each sub-array**, not by the numbers inside. The `Arrays.deepEquals`/`Arrays.deepHashCode` pair traverses into sub-arrays to compare/hash contents at the proper level:

```java
// In a method with import java.util.Arrays:
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};
System.out.println(Arrays.equals(a, b));     // false: sub-arrays have different identity
System.out.println(Arrays.deepEquals(a, b)); // true: same values across levels
```

The two `deep*` methods accept an outer array of type `Object[]` (for example `int[][]`), so **do not call** `Arrays.deepEquals(int[], int[])` directly. They handle primitive arrays at nested levels using the appropriate overload, preserving order, distinguishing array types, nulls, and depth; they do not automatically traverse into fields of arbitrary objects. An `Object[]` array containing itself, directly or indirectly, falls outside the defined behavior of `deepEquals/deepHashCode`: a custom cycle-aware algorithm is required. The article *Arrays.deepEquals() and Arrays.deepHashCode() for Nested Arrays* analyzes the cases in depth, while *Limits When Structures Have Circular References* addresses this limitation.

## 5. Do not confuse content comparison with hash collection behavior

`HashMap` and `HashSet` always use `equals/hashCode` of the stored **key/element object**. With a bare `int[]`, they use identity, not automatically calling `Arrays.equals/hashCode`. If you want two newly created arrays with the same elements to represent the same key, you need a **value object** with `equals` based on `Arrays.equals`, `hashCode` based on `Arrays.hashCode`, along with a defensive copy of the mutable array.

If the policy is to compare nested array contents, use the `Arrays.deepEquals`/`Arrays.deepHashCode` pair and copy all mutable rows/elements sufficiently. `final` only prevents the reference from being reassigned; it **does not freeze the array**. The article *Array Fields in Custom Classes and the Requirement to Synchronize equals() with hashCode()* dives into multi-field cases and how to combine hashes.

## 6. Standalone runnable Java 17+ program

The example below compares array identity, one-dimensional array content, nested structures, and the impact of placing arrays directly into `HashSet`/`HashMap`. Finally, it shows an **immutable value object** using a copy of the array to achieve content-based `equals`/`hashCode`.

Save as file `ArrayIdentityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ArrayIdentityDemo {
    static final class IntArrayKey {
        private final int[] values;

        IntArrayKey(int[] input) {
            Objects.requireNonNull(input, "input");
            this.values = input.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof IntArrayKey that
                        && Arrays.equals(values, that.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        int[] alias = a;

        System.out.println("a == b: " + (a == b));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a == alias: " + (a == alias));
        System.out.println("same identity hash: "
                + (a.hashCode() == System.identityHashCode(a)));
        System.out.println("Arrays.equals(a, b): " + Arrays.equals(a, b));
        System.out.println("content hash equal: "
                + (Arrays.hashCode(a) == Arrays.hashCode(b)));

        Set<int[]> arrays = new HashSet<>();
        arrays.add(a);
        arrays.add(b);
        arrays.add(alias);
        System.out.println("HashSet<int[]> size: " + arrays.size());
        System.out.println("contains new equal-content array: "
                + arrays.contains(new int[] {1, 2, 3}));

        Map<int[], String> map = new HashMap<>();
        map.put(a, "value-a");
        System.out.println("get same reference: " + map.get(alias));
        System.out.println("get equal-content new reference: " + map.get(b));

        Object[] nestedA = {
                new int[] {1, 2},
                new String[] {"x", "y"}
        };
        Object[] nestedB = {
                new int[] {1, 2},
                new String[] {"x", "y"}
        };
        System.out.println("nested Arrays.equals: "
                + Arrays.equals(nestedA, nestedB));
        System.out.println("nested Arrays.deepEquals: "
                + Arrays.deepEquals(nestedA, nestedB));
        System.out.println("nested deepHashCode equal: "
                + (Arrays.deepHashCode(nestedA)
                   == Arrays.deepHashCode(nestedB)));

        IntArrayKey k1 = new IntArrayKey(a);
        IntArrayKey k2 = new IntArrayKey(b);
        Set<IntArrayKey> keys = new HashSet<>();
        keys.add(k1);
        System.out.println("value key equals: " + k1.equals(k2));
        System.out.println("value key found: " + keys.contains(k2));

        a[0] = 99;
        System.out.println("source a now equals b by content: "
                + Arrays.equals(a, b));
        System.out.println("snapshot key still found: "
                + keys.contains(k2));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 ArrayIdentityDemo.java
java ArrayIdentityDemo
```

Expected output:

```text
a == b: false
a.equals(b): false
a == alias: true
same identity hash: true
Arrays.equals(a, b): true
content hash equal: true
HashSet<int[]> size: 2
contains new equal-content array: false
get same reference: value-a
get equal-content new reference: null
nested Arrays.equals: false
nested Arrays.deepEquals: true
nested deepHashCode equal: true
value key equals: true
value key found: true
source a now equals b by content: false
snapshot key still found: true
```

### Result Analysis

**Different original arrays:** `a` and `b` are two arrays, even though they have the same sequence of elements `1, 2, 3`. Because arrays do not override `equals`, `a.equals(b)` returns `false`. `alias` points to `a`, so both `a == alias` and `a.equals(alias)` are true.

**Two kinds of hashes:** `a.hashCode()` is the default identity-based hash code, equal to `System.identityHashCode(a)`. `Arrays.hashCode(a)` is the content hash code; for `a` and `b` with identical contents, the content hash results are equal. Do not try to infer whether data is equal from whether two identity hashes differ or match.

**Hash collections:** `HashSet<int[]>` uses `hashCode`/`equals` of the array object itself, so `a` and `b` are stored as **two distinct keys/elements**. Adding `alias` does not increase the size because it points back to `a`. A new array with the same numbers is also not found. Similarly, `HashMap.get(alias)` finds the value `value-a`, while `get(b)` returns `null` even though `b` contains the same numbers.

**Nested structures:** `Arrays.equals(nestedA, nestedB)` returns `false` because the two inner `int[]` arrays have different references. `Arrays.deepEquals` enters the sub-arrays and confirms the corresponding data is equal; `deepHashCode` of the two structures also matches.

**Value object:** `IntArrayKey` copies the input array right in the constructor, keeps the copy in a `private final` field, and does not expose the internal array externally. Both `equals`/`hashCode` use the contents of `values`, so `k1` and `k2` are equal and found in `HashSet`. After modifying `a[0]` from `1` to `99`, the already-created key `k1` still holds the original copy; looking up with `k2` continues to succeed.

This code uses the array's default `hashCode` **and** `Arrays.hashCode` to illustrate both meanings; it does not print a fixed numeric value for the identity hash code, as that value can change across runs.

## 7. Using an array as a `HashMap` key or `HashSet` element

You need to choose whether the key represents the **identity of an array data region** or the **values of its elements**.

### When array identity is needed

If the business requirement wants two different arrays to always be two separate keys, even when they contain the same elements, `HashMap<int[], V>` or `HashSet<int[]>` can reflect that requirement. This often appears when tracking **a specific array object** in memory.

However, expectations must be stated clearly: looking up with a **newly created array having the same elements** will not match the old array. This is not a collection bug.

If a specialized structure is needed to check key identity when other key classes have value-based `equals`, Java also has `IdentityHashMap`; however, for arrays, `equals` itself is already identity-based. `IdentityHashMap` has its own semantics and should only be chosen when intentionally using references to identify keys.

### When array content value is needed

If two arrays `{1, 2, 3}` must be treated as the same logical key, **do not use a bare `int[]` as a key expecting `HashMap` to call `Arrays.equals`**. You need a wrapper class like `IntArrayKey` in the example: implement `equals` with `Arrays.equals`, implement `hashCode` with `Arrays.hashCode`, and protect immutability.

You can use another immutable structure with an element-wise equality contract, such as an immutable list containing copied values. However, you must understand the element type properly; a `List<int[]>` still holds array elements, and element comparison can continue to rely on sub-array identity.

### What if the array mutates after being inserted into the map?

Two cases must be distinguished:

- **Key is a bare `int[]`:** modifying elements does not change the array's default identity `equals`/`hashCode`. With the same key reference, lookup using it retains normal identity semantics. However, if the business requirement expected content comparison, the design was unsuitable from the start.
- **Key is a content-comparing wrapper that holds a mutable array reference:** modifying elements can cause `hashCode` to change while the key remains in the hash bucket determined by the old hash. `get`/`contains` may fail to find the key. This is a common design bug.

Therefore, a wrapper used as a hash key should **copy the input data** and, if it provides an accessor method, also return a **defensive copy**, rather than letting external code modify the data used by `equals`/`hashCode`. `private final int[] values` by itself **only fixes the reference to the array**; it does not make the array elements immutable.

## 8. Distinguishing APIs by use case

| Specific need | Appropriate API / design | What to avoid |
| --- | --- | --- |
| Ask whether two variables point to the same array | `a == b`, or `a.equals(b)` when `a` is guaranteed non-`null` | Using `Arrays.equals` if identity is required. |
| Compare two `int[]` arrays element-by-element | `Arrays.equals(a, b)` | Using `a.equals(b)` and concluding the contents differ. |
| Generate a corresponding content hash for `int[]` | `Arrays.hashCode(a)` | Using `a.hashCode()` as a content fingerprint. |
| Compare two `String[]` arrays by their element strings | `Arrays.equals(a, b)` | Forgetting that each reference element uses that class's own `equals`. |
| Compare two multidimensional/nested arrays by content | `Arrays.deepEquals(a, b)` when the root is `Object[]` | Calling `Arrays.equals` at the outer level and thinking it goes deep through all levels. |
| Generate a corresponding hash for a nested array | `Arrays.deepHashCode(a)` | Mixing `deepEquals` with shallow `Arrays.hashCode` when used as a value object contract. |
| Use array content as a hash key | Value object copying the array, `Arrays.equals`/`Arrays.hashCode` pair or corresponding deep pair | Using bare `int[]` and expecting collections to recognize equal values. |
| Check if two arrays are equal when one or both may be `null` | `Arrays.equals`, or `Arrays.deepEquals` for appropriate nested arrays | Calling `a.equals(b)` on `a == null`. |

Besides `equals`, the `Arrays` utility class also has `mismatch` to find the first differing index of two arrays and `compare` for lexicographical comparison via corresponding overloads. These are different questions from an array object's equality contract; only use them when identifying the mismatch position or comparison order is valuable for the problem.

## 9. Common pitfalls when working with arrays and nested structures

### Pitfall 1: Comparing arrays with `equals` and concluding the data differs

`new int[]{1,2}.equals(new int[]{1,2})` is `false`, because they are two different array objects. If you want to know whether `int[]` contents are equal, you must use `Arrays.equals`.

### Pitfall 2: Seeing equal hashes of two arrays and assuming they are equal

No `int`-returning hash function guarantees uniqueness for all possible arrays. Equal hashes can be a **collision**, for both identity hashes and content hashes. Compare accurately using the appropriate equality API instead of replacing `equals` with `hashCode()==hashCode()`.

### Pitfall 3: Using `Arrays.equals` for `int[][]`

`int[][]` is an array containing `int[]` arrays. Outer-level `Arrays.equals` only compares each sub-array using their `equals`, returning `false` for two new structures with the same numeric matrix. To go deep, use `Arrays.deepEquals`; when hashing content for a corresponding wrapper, use `Arrays.deepHashCode`.

### Pitfall 4: Using `Arrays.deepEquals` without considering reference cycles

If an `Object[]` contains itself or arrays form a cycle, the deep algorithm is not a solution for comparing cyclic graphs. Avoid designing cyclic data within the scope of `deepEquals`/`deepHashCode`, or implement a comparison algorithm with visited-node tracking and an explicit contract.

### Pitfall 5: Overriding only `equals` of a wrapper

If a wrapper defines equality via `Arrays.equals(values, other.values)` without overriding the corresponding `hashCode`, two wrappers with equal content may receive different default hashes and cannot be reliably used as hash keys. Both `Arrays.hashCode(values)` for one-dimensional arrays, or the corresponding deep pair when the policy is nested array content comparison, are required.

### Pitfall 6: Shallow copying and thinking it is deeply immutable

`array.clone()` copies the **outer array**, but for an `Object[]` containing sub-arrays or mutable objects, elements are copied as references. External code can still mutate those sub-arrays. If a wrapper is meant to act as a hash key **across the entire nested structure**, deep copying appropriate to the data domain must be considered to ensure every component participating in equality/hash cannot be modified externally.

### Pitfall 7: Using `Arrays.toString` as a key string and then hashing

`Arrays.toString(int[])` is useful for display, but for a nested `Object[]`, the result can contain strings describing the identity of sub-array elements. Use `Arrays.deepToString` to display ordinary nested arrays when needed, yet **the display string is not a serialization format or canonical identity standard** for all element types. Do not turn debug output into an identity rule without specification.

## 10. Testing checklist

When working with array wrapper classes or structures storing arrays, you should check:

1. Two arrays with **different references, same elements**: `a.equals(b)` is false, `Arrays.equals(a,b)` is true.
2. Two variables pointing to **the same array**: identity comparison is true, even when elements are modified.
3. Two arrays with **different lengths** or differing in at least one element: `Arrays.equals` is false.
4. `null`: `Arrays.equals(null, null)` with a specified overload returns true; calling a method on a `null` reference throws an error.
5. Reference arrays with `null` elements: `Arrays.equals(Object[], Object[])` must produce the right result at each position.
6. Two nested arrays with **separate sub-arrays** but the same content: outer `Arrays.equals` is false, `Arrays.deepEquals` is true.
7. If using content comparison, every equal pair must yield the same corresponding `Arrays.hashCode`/`Arrays.deepHashCode`; equal hashes **do not imply** equality.
8. With `HashMap`/`HashSet`: clearly determine whether you want array identity or element values; also test querying with a new array having the same elements.
9. With an immutable wrapper: modifying the original array after key creation, and modifying the copy if there is a data-export API, must **not change** the `equals`/`hashCode` results of the stored key.
10. With nested structures: clearly determine whether they contain cycles, mutable objects, and whether shallow or deep comparison is needed.

## 11. Summary

Java arrays use default `equals()` and `hashCode()` based on **object identity**, so two separately created arrays with identical elements are still not equal according to `array1.equals(array2)`. When the problem requires **content semantics**, `Arrays.equals`/`Arrays.hashCode` is the corresponding pair for one-dimensional arrays; `Arrays.deepEquals`/`Arrays.deepHashCode` handles acyclic nested reference arrays appropriately. If an array is used as a key in a hash collection and requires content comparison, place it inside an **immutability-protecting value object**, designing `equals` and `hashCode` with the same criteria. Distinguishing between identity, content, shallow comparison, and deep comparison determines the correctness of all lookup operations.