# `Arrays.deepEquals()` and `Arrays.deepHashCode()` for Nested Arrays in Java

## Lesson Objectives

In Java, **arrays are objects**. Two different arrays can hold the same values yet `==` is still `false`; even `Arrays.equals()` has limitations when the elements of the outer array are themselves **other arrays**. `Arrays.deepEquals()` and `Arrays.deepHashCode()` help compare and compute hash codes **by nested structure** in appropriate cases.

After this lesson, you can:

- Distinguish `==`, `Arrays.equals()`, `Arrays.deepEquals()`, `Arrays.hashCode()`, and `Arrays.deepHashCode()`.
- Explain why `int[][]`, `String[][]`, and `Object[]` containing arrays yield different comparison results between shallow and deep approaches.
- Know the parameter types accepted by the two `deep*` APIs and use `Arrays.equals()/hashCode()` for one-dimensional primitive arrays.
- Understand how sub-arrays, `null`, regular elements, primitive arrays, order, and nested structures are handled.
- Preserve the contract between equality and hash code when building classes containing arrays; recognize the impact of mutable data and self-referential arrays.

## 1. Four common comparisons

Suppose each sub-array is created by a separate `new` expression:

```java
int[][] a = {{1, 2}, {3, 4}};
int[][] b = {{1, 2}, {3, 4}};

System.out.println(a == b);                  // false
System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

This is an illustrative snippet placed inside a method, requiring `import java.util.Arrays;`.

- **`a == b`** compares outer array identity. The two outer arrays are separate, so the result is `false`.
- **`Arrays.equals(a, b)`** checks the length and elements at matching positions of the outer array. Those elements are separate `int[]` arrays, and they do not override `Object.equals()` to compare element by element. Thus the result is `false`.
- **`Arrays.deepEquals(a, b)`** descends into each sub-array and compares corresponding elements using the appropriate rule: here, the inner `int` elements match correspondingly, so the result is `true`.

A two-dimensional array `int[][]` is actually an array whose elements are of type `int[]`. The sub-arrays can have different lengths, and a sub-array element can be `null`. It is not a flat memory matrix forced to have the same number of columns.

### Shallow vs. deep

```text
a: int[][]                    b: int[][]

  a[0] ──► [1, 2]              b[0] ──► [1, 2]
  a[1] ──► [3, 4]              b[1] ──► [3, 4]

Arrays.equals(a, b):
  Compare a[0] with b[0] as two reference elements → different objects → false.

Arrays.deepEquals(a, b):
  Compare a[0] with b[0] by int[] content → true;
  compare a[1] with b[1] by int[] content → true;
  overall result → true.
```

Core point: `deepEquals` compares **element values inside the nested array structure**; it does not require sub-arrays to be at the same address or be the same object.

## 2. Parameter types of `Arrays.deepEquals()` and `Arrays.deepHashCode()`

The two methods have the basic signatures:

```java
public static boolean deepEquals(Object[] a1, Object[] a2);
public static int deepHashCode(Object[] a);
```

Because `int[][]` is an array of `int[]` (each `int[]` is an `Object`), `int[][]` can be passed as an `Object[]`. `String[][]`, `long[][][]`, and `Object[]` can also be passed to these APIs.

Conversely, **one-dimensional primitive `int[]` is not an `Object[]`**:

```java
int[] a = {1, 2};
int[] b = {1, 2};

boolean same = java.util.Arrays.equals(a, b); // true
int hash = java.util.Arrays.hashCode(a);

// The following lines DO NOT COMPILE:
// java.util.Arrays.deepEquals(a, b);
// java.util.Arrays.deepHashCode(a);
```

This is an illustrative snippet inside a method; the two incorrect lines are intentionally commented out.

Choose the API according to the array type at the comparison site:

| Data | Content comparison | Content-based hash computation |
| --- | --- | --- |
| `int[]`, `byte[]`, `char[]`, `boolean[]`,… | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `String[]`, no sub-arrays | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `int[][]` or multidimensional primitive arrays | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |
| `Object[]` containing arrays, or `Object[][]` | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |

For a one-dimensional array containing regular non-array objects, `Arrays.deepEquals` can also be used, though it provides no special deep-comparison benefit. Both paths generally go to the element's `equals()`. **Deep** here only means descending into **nested arrays**; it does not automatically traverse fields of arbitrary Java objects.

## 3. Complete Java 17+: shallow, deep, `null`, and primitive arrays

Create file `DeepArraysDemo.java`:

```java
import java.util.Arrays;

public class DeepArraysDemo {
    public static void main(String[] args) {
        int[][] left = {{1, 2}, {3, 4}};
        int[][] right = {{1, 2}, {3, 4}};
        int[][] changed = {{1, 2}, {3, 5}};

        System.out.println("same outer reference: " + (left == right));
        System.out.println("shallow equals: "
                + Arrays.equals(left, right));
        System.out.println("deep equals: "
                + Arrays.deepEquals(left, right));
        System.out.println("deep hash equal: "
                + (Arrays.deepHashCode(left)
                   == Arrays.deepHashCode(right)));
        System.out.println("changed equals: "
                + Arrays.deepEquals(left, changed));

        Object[] mixedLeft = {
                new int[] {7, 8},
                new Object[] {new String[] {"A", "B"}, null}
        };
        Object[] mixedRight = {
                new int[] {7, 8},
                new Object[] {new String[] {"A", "B"}, null}
        };
        System.out.println("mixed shallow: "
                + Arrays.equals(mixedLeft, mixedRight));
        System.out.println("mixed deep: "
                + Arrays.deepEquals(mixedLeft, mixedRight));
        System.out.println("mixed hashes match: "
                + (Arrays.deepHashCode(mixedLeft)
                   == Arrays.deepHashCode(mixedRight)));

        int[] singleLeft = {10, 20};
        int[] singleRight = {10, 20};
        System.out.println("single primitive equals: "
                + Arrays.equals(singleLeft, singleRight));
        System.out.println("single primitive hash equal: "
                + (Arrays.hashCode(singleLeft)
                   == Arrays.hashCode(singleRight)));

        int[][] nullableLeft = {null, {9}};
        int[][] nullableRight = {null, {9}};
        System.out.println("nested null equals: "
                + Arrays.deepEquals(nullableLeft, nullableRight));

        left[1][1] = 99;
        System.out.println("after mutation equals: "
                + Arrays.deepEquals(left, right));
    }
}
```

Compile and run commands:

```bash
javac DeepArraysDemo.java
java DeepArraysDemo
```

Expected output:

```text
same outer reference: false
shallow equals: false
deep equals: true
deep hash equal: true
changed equals: false
mixed shallow: false
mixed deep: true
mixed hashes match: true
single primitive equals: true
single primitive hash equal: true
nested null equals: true
after mutation equals: false
```

Explanation:

1. `left` and `right` are created as two separate array objects, so `==` is `false`. `Arrays.equals` is also `false` because the sub-arrays are separate objects.
2. `Arrays.deepEquals(left, right)` is `true` because all corresponding `int[]` rows have the same element count and values; therefore the two `deepHashCode` values must be equal.
3. `changed` differs by one element (`5` instead of `4`), so `deepEquals` is `false`.
4. With `mixedLeft`/`mixedRight`, the structure includes an `int[]`, a nested `Object[]`, a `String[]`, and `null`. Deep comparison handles all these nesting levels.
5. One-dimensional primitive arrays use `Arrays.equals` and `Arrays.hashCode`.
6. Two structures with a `null` sub-array element at the same position can be equal under deep comparison.
7. After changing `left[1][1]` to `99`, the content now differs from `right`, so `deepEquals` changes from `true` to `false`. The APIs do not “freeze” results or store a data snapshot.

## 4. How does `deepEquals` handle elements?

Conceptually, `Arrays.deepEquals(a, b)` for two `Object[]` has the rules:

1. If both outer array references are the same reference (including both `null`), the result is `true`.
2. If one outer array is `null` and the other is not, the result is `false`.
3. If lengths differ, the result is `false`.
4. For each corresponding position, inspect the two elements. If they are corresponding `Object[]`, compare recursively. If they are two primitive arrays of the same kind, use the appropriate primitive element comparison. If not a pair of arrays needing deep comparison, apply the equality relation appropriate for normal objects. As soon as one position is unequal, return `false`.

Therefore, **array type, nesting depth, order, length, and elements** all matter.

### Order is not ignored

```java
int[][] a = {{1}, {2}};
int[][] b = {{2}, {1}};

System.out.println(Arrays.deepEquals(a, b)); // false
```

These lines illustrate code inside a method and require `import java.util.Arrays`. The two arrays contain the same multiset of values if order is ignored, but `deepEquals` is a **positional** comparison, not a set or permutation comparison.

### Different primitive array types are not converted

```java
Object[] a = {new int[] {1, 2}};
Object[] b = {new long[] {1L, 2L}};

System.out.println(Arrays.deepEquals(a, b)); // false
```

Although the displayed numbers have the same magnitude, `int[]` and `long[]` are two different array types. There is no automatic primitive widening rule to make arrays structurally “equal”.

### Jagged arrays and arrays with `null` elements

```java
int[][] a = {{1}, null, {2, 3}};
int[][] b = {{1}, null, {2, 3}};
int[][] c = {{1}, {}, {2, 3}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepEquals(a, c)); // false
```

A `null` row differs from an empty array `new int[0]`. The method does not automatically treat absent data as an empty array.

### Non-array elements

```java
Object[] a = {"hello", Integer.valueOf(7)};
Object[] b = {new String("hello"), Integer.valueOf(7)};

System.out.println(Arrays.deepEquals(a, b)); // true
```

When an element is not an array, `deepEquals` relies on the objects' `equals()`. There is no “deep reflection” to automatically access `private` fields inside arbitrary classes. If a class defines identity-based `equals`, different objects of that class will not automatically be equal just by being placed inside `Object[]`.

The examples in this section are method-body snippets, not standalone runnable Java files.

## 5. `Arrays.deepHashCode()` computes hashes of nested structures

`Arrays.deepHashCode(Object[] a)` computes a hash code from the elements of the outer array. If an element is a sub-array:

- Reference sub-arrays (`Object[]`) are processed deeply by applying `deepHashCode` to that sub-array.
- Primitive sub-arrays, such as `int[]` or `double[]`, use the `Arrays.hashCode` appropriate for that array type.
- Regular object elements are hashed based on the object's `hashCode()`; `null` elements are handled according to the algorithm's rules.

Hash aggregation follows sequential combination of elements. For non-nested arrays, it matches the `31 * result + elementHash` accumulation idea; for nested arrays, `elementHash` can be the deeply computed hash of the sub-array.

Example:

```java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepHashCode(a)
        == Arrays.deepHashCode(b));           // true
```

You do not need to memorize a specific hash number to use the API correctly. What matters is the **relationship** between the two operations:

```text
Arrays.deepEquals(a, b) == true
                  ↓ required
Arrays.deepHashCode(a) == Arrays.deepHashCode(b)
```

**Do not reverse the direction:** two arrays that differ under deep comparison can still have the same deep hash. A hash code is an `int`, so collisions can happen with any good hash function.

### Why must a consistent method pair be used?

If you define “equality” for an object containing arrays using `Arrays.deepEquals`, that object's `hashCode` function must have a compatible relationship; `Arrays.deepHashCode` is the natural way to implement it. Conversely, if you use `Arrays.hashCode` on an **outer array** containing sub-arrays, it treats sub-arrays as reference elements. Separate sub-arrays with the same content are not required to have the same hash under shallow computation.

Therefore, do not arbitrarily pair a deep comparison with a shallow hash function when sub-arrays determine content equality.

## 6. Pitfall: `Arrays.hashCode`/`Arrays.equals` on the outer array

For `int[][]`, each element of the outer array is an `int[]`. `int[]` does not override `equals()` and `hashCode()` by element value, so **shallow** operations handle sub-arrays according to default object rules.

Compare:

```java
int[][] a = {{1, 2}};
int[][] b = {{1, 2}};

boolean shallow = Arrays.equals(a, b);       // false
boolean deep = Arrays.deepEquals(a, b);      // true
boolean deepHashesEqual =
        Arrays.deepHashCode(a)
        == Arrays.deepHashCode(b);           // true
```

You should not print or assert a fixed result for `Arrays.hashCode(a) == Arrays.hashCode(b)` here: the identity hash codes of the sub-arrays could coincidentally match, though that does not make `Arrays.equals(a, b)` become `true`. By design, shallow hashing is **not guaranteed to be compatible** with deep equality criteria.

Another perspective is replacing sub-arrays with a shared reference:

```java
int[] row = {1, 2};
int[][] a = {row};
int[][] b = {row};

System.out.println(Arrays.equals(a, b)); // true
```

The two outer arrays are different, yet both contain **the exact same object** `row`, so shallow element comparison also yields `true`. This is not proof that `Arrays.equals` compares data deeply. Deep comparison will be true even when each side has a new sub-array with the same content.

## 7. When an array structure has aliases (shared sub-arrays)

`deepEquals` compares **content by position**; it does not require the internal reference graph to have the same object-sharing pattern.

```java
int[] shared = {4, 5};
Object[] left = {shared, shared};
Object[] right = {new int[] {4, 5}, new int[] {4, 5}};

System.out.println(Arrays.deepEquals(left, right)); // true
```

In `left`, both positions reference `shared`. In `right`, they point to two different `int[]` arrays. However, at each position, the inner data matches correspondingly, so deep comparison yields `true`. If your business requirement needs to know whether two positions share the same instance, `deepEquals` **is not** that check; check reference identity with `==` position by position.

Another issue is **mutable aliasing**: modifying `shared[0]` will change the observable content at both positions of `left`, while `right` remains unchanged. The `deepEquals`/`deepHashCode` result of the same structure can change over time if a sub-array is mutated.

## 8. Self-referential arrays or arrays containing cycles

An `Object[]` array can directly or indirectly contain a reference to itself:

```java
Object[] cycle = new Object[1];
cycle[0] = cycle;
```

For a structure like that, **you must not rely on `Arrays.deepEquals` or `Arrays.deepHashCode`**. The Java API documentation states that the behavior of deep operations is **undefined** when an array contains itself as an element, directly or indirectly. In some environments, recursion can lead to a `StackOverflowError`; this is not a standard result that an application can rely upon.

If the data model genuinely has an object graph containing cycles (for example, parent/child nodes referencing each other), you need to design a specialized comparison/hash algorithm that tracks visited objects and has explicit rules for cycles. It cannot be replaced simply with a `deep*` call.

**Best use scope:** finite nested array structures without self-containing reference cycles.

## 9. Applying to `equals()` and `hashCode()` of a class containing arrays

By default, an array-typed field uses the `equals()` method inherited from `Object`, which compares **the identity of the array object**. If the business model wants to treat two objects as equal when their nested array data is identical, it must be implemented explicitly.

Java 17+ example using a simple value object class. The following is **a standalone program** to show how to use the deep API pair:

Create file `DeepValueEqualityDemo.java`:

```java
import java.util.Arrays;

public class DeepValueEqualityDemo {
    static final class MatrixValue {
        private final int[][] values;

        MatrixValue(int[][] source) {
            this.values = copy(source);
        }

        private static int[][] copy(int[][] source) {
            if (source == null) {
                return null;
            }
            int[][] result = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                result[i] = source[i] == null
                        ? null : source[i].clone();
            }
            return result;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixValue other)) {
                return false;
            }
            return Arrays.deepEquals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(values);
        }
    }

    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        MatrixValue a = new MatrixValue(input);
        MatrixValue b = new MatrixValue(new int[][] {{1, 2}, {3}});
        MatrixValue c = new MatrixValue(new int[][] {{1, 2}, {4}});

        System.out.println("equal values: " + a.equals(b));
        System.out.println("equal hashes: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different values: " + a.equals(c));

        input[0][0] = 99;
        System.out.println("safe from source mutation: "
                + a.equals(b));
    }
}
```

Compile and run:

```bash
javac DeepValueEqualityDemo.java
java DeepValueEqualityDemo
```

Output:

```text
equal values: true
equal hashes: true
different values: false
safe from source mutation: true
```

Here `MatrixValue` is a `final` class, so pattern matching with `instanceof` does not raise complex inheritance choices. `Arrays.deepEquals` compares nested array data, while `Arrays.deepHashCode` computes the hash from the same data, preserving the required direction of the contract.

The constructor copies **the outer array and each `int[]` row**, so modifying `input` after creating `MatrixValue` does not affect the object. The fields have no setter or getter methods returning the internal array directly; in this example, the object keeps its data stable throughout its lifecycle. If the structure instead uses nested reference arrays containing mutable objects, per-layer `clone()` like in this example **is not enough** to guarantee complete immutability; an appropriate deep copying or encapsulation strategy must be considered.

### Why not use arrays directly as keys if content equality is desired?

`HashMap<int[][], String>` still accepts arrays as keys, but array keys do not automatically use `Arrays.deepEquals`:

```java
Map<int[][], String> map = new HashMap<>();
map.put(new int[][] {{1, 2}}, "found");

String result = map.get(new int[][] {{1, 2}});
// result is null because the lookup key is a new array object
```

This is an illustrative snippet requiring `import java.util.Map;` and `import java.util.HashMap;` inside a method.

If you want to compare keys by nested array content, use an immutable wrapper class implementing content-based `equals/hashCode` like `MatrixValue`. Do not expect `HashMap` to automatically call `Arrays.deepEquals` for each array key.

**Note on `record` containing arrays:** a record auto-generates `equals/hashCode` for its components following each type's contract. An array component still has the equality/hash semantics of the array object itself (not automatically deep-compared). Therefore, `record Payload(int[][] values) {}` does not automatically replace a wrapper with `Arrays.deepEquals/deepHashCode` if business logic needs nested array content comparison.

## 10. Common mistakes

1. **Using `Arrays.equals` for `int[][]` and being surprised by `false`.** Elements of the outer array are sub-arrays; use `Arrays.deepEquals` when you want to compare row contents.
2. **Using `Arrays.deepEquals` for one-dimensional `int[]`.** Does not compile because the signature requires `Object[]`; use `Arrays.equals`.
3. **Calling `Arrays.deepHashCode` and concluding two arrays with the same hash are definitely equal.** Wrong: collisions can still occur; use `deepEquals` to conclude equality.
4. **Comparing deeply in `equals` but hashing shallowly in a wrapper's `hashCode`.** Can violate the contract between two content-equal objects; use a consistent function pair.
5. **Assuming `deepEquals` automatically deep-compares all user-defined objects.** For non-array elements, results follow the element class's `equals`.
6. **Ignoring order, length, array type, or `null`.** These differences usually cause `deepEquals` to return `false`; deep comparison is not type conversion or set comparison.
7. **Passing cyclic structures into `deepEquals/deepHashCode`.** Undefined behavior; an algorithm designed for cyclic graphs is required.
8. **Using an object containing mutable arrays as a `HashMap` key.** If elements used to compute the hash change while the object is in the table, lookups may fail. Encapsulation/copying and ensuring stable data for equality/hash are required.
9. **Confusing identical data structure with identical alias topology.** Two positions pointing to the same sub-array can still deep-equal a structure containing two independent copies of that sub-array.

## 11. Self-check

Consider the following variables:

```java
int[][] a = {{1, 2}, null};
int[][] b = {{1, 2}, null};
int[][] c = {{2, 1}, null};
int[][] d = {{1, 2}, {}};

boolean q1 = a == b;
boolean q2 = Arrays.equals(a, b);
boolean q3 = Arrays.deepEquals(a, b);
boolean q4 = Arrays.deepHashCode(a)
          == Arrays.deepHashCode(b);
boolean q5 = Arrays.deepEquals(a, c);
boolean q6 = Arrays.deepEquals(a, d);
```

Illustrative snippet placed inside a method that has `import java.util.Arrays`.

**Answers and reasons:**

- `q1 = false`: the two outer arrays are two different objects.
- `q2 = false`: at the first position, `a[0]` and `b[0]` are two `int[]` arrays differing in identity; shallow comparison stops here.
- `q3 = true`: the first two sub-arrays are both `[1, 2]` and the next two elements are both `null`.
- `q4 = true`: when deep comparison yields `true`, the deep hash codes must be equal.
- `q5 = false`: `[1, 2]` differs from `[2, 1]` due to element order.
- `q6 = false`: a `null` row is not equivalent to an empty row.

An extension exercise: create two `Object[]` each containing `new int[] {1,2}` and `"abc"`, then compare `Arrays.equals`, `Arrays.deepEquals`, `Arrays.hashCode`, `Arrays.deepHashCode`. Explain why deep comparison can be `true` even when shallow comparison is `false`, and why an equal hash result should not be used as proof that two values are equal.

## Summary

- **`Arrays.equals`/`Arrays.hashCode`** is suitable for content comparison of one-dimensional primitive arrays, or object arrays that do not need to descend into sub-arrays.
- **`Arrays.deepEquals`/`Arrays.deepHashCode`** is suitable for `Object[]` containing nested array structures, including `int[][]` and `String[][]`; they descend through sub-arrays to compare and compute hashes by content.
- **`deepEquals(a, b) == true` ⇒ deep hashes of `a` and `b` are equal**, but having the same deep hash does not guarantee two arrays are equal.
- The `deep*` methods do not automatically handle arbitrary cyclic object graphs, do not automatically compare internal fields of arbitrary objects, and do not automatically make data immutable. When using nested arrays in `equals/hashCode` or as keys in hash structures, an appropriate contract and data-state protection must be designed.