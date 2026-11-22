# `Objects.deepEquals()` differs from `Objects.equals()` on array arguments

## 1. Objective: distinguishing array references from array contents

`java.util.Objects` provides two static methods that both accept two `Object` arguments and handle `null` safely:

```java
Objects.equals(a, b);
Objects.deepEquals(a, b);
```

**Core difference:** when the two arguments are **two arrays with different references**, `Objects.equals(a, b)` relies on ordinary object `equals`; Java arrays do not override `Object.equals`, so the comparison is **by identity**. By contrast, `Objects.deepEquals(a, b)` has a mechanism for comparing **array contents**, recursing through nested array levels and handling primitive arrays as well.

```java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);                  // false
System.out.println(Objects.equals(first, second));    // false
System.out.println(Objects.deepEquals(first, second)); // true
```

This is an illustrative snippet placed inside a method with `import java.util.Objects;`, not yet a standalone program. Two array creations produce two separate array objects. They contain the same data but do not point to the same object region, so the two comparisons produce different results.

The word *deep* here should be read as **deep comparison of array structures**. It does not mean that every nested `List`, `record`, bean, or business object inside is automatically inspected field-by-field by the library.

## 2. Behavior by argument type

| Case for `a`, `b` | `Objects.equals(a,b)` | `Objects.deepEquals(a,b)` |
| --- | --- | --- |
| Both are `null` | `true` | `true` |
| Only one side is `null` | `false` | `false` |
| Same non-`null` reference | `true` | `true` |
| Two ordinary non-array objects | Uses `a.equals(b)` | Also uses `a.equals(b)` |
| Two distinct `int[]` arrays with the same elements | `false` | `true` |
| Two distinct `String[]` arrays with the same strings | `false` | `true` |
| Two distinct `int[][]` arrays with the same structure/numbers | `false` | `true` |
| Two distinct `List<int[]>` containing arrays with the same numbers | Normally `false` | Still `false`, because `List.equals` does not deep-compare array element contents |
| Two record types whose component is two distinct arrays | Normally `false` | Still `false`, because a record's generated `equals` compares array components by reference |

The table assumes cases labeled "distinct" do not share the corresponding array references, and that objects/classes follow ordinary `equals` rules. A custom class can certainly override `equals` with its own semantics.

`Objects.deepEquals` does not require the arguments to be declared as array types at compile time: its signature accepts `Object`. Thus, it is a convenient way to compare two objects that at runtime turn out to be `byte[]`, `int[]`, `Object[]`, or some nested array form.

## 3. How `Objects.equals()` works

Semantically, `Objects.equals(a, b)` is roughly equivalent to:

```java
return a == b || (a != null && a.equals(b));
```

The snippet above illustrates logic inside a method with two parameters `a`, `b`; it is not a standalone program.

- If `a == b`, including both `null`, return `true`.
- If `a == null` while `b != null`, return `false`, without calling a method on `null`.
- In remaining cases, the result depends on `a.equals(b)` and the `equals` contract of the actual type.

Classes such as `String`, many numeric wrapper classes, `List`, and `record` types generally have value-based equality rules. However, **Java arrays do not override `equals`**, so two arrays with different references will not be considered equal by `Objects.equals`, even if element counts and contents match.

```java
String a = new String("java");
String b = new String("java");
System.out.println(Objects.equals(a, b)); // true

int[] x = {1, 2};
int[] y = {1, 2};
System.out.println(Objects.equals(x, y)); // false
```

This illustrative snippet requires `import java.util.Objects;`. The results of the two groups differ because **the compared element type itself** either has or does not have a value-based `equals` rule, not because `Objects.equals` treats Strings differently from numbers on its own.

## 4. How `Objects.deepEquals()` evaluates arrays and nested arrays

After handling identical references or `null`, `Objects.deepEquals` identifies arrays by runtime type and compares corresponding elements:

1. **Two primitive arrays of the same type**, such as `byte[]` with `byte[]` or `int[]` with `int[]`: compares length and contents by position, equivalent to the appropriate `Arrays.equals` method.
2. **Two reference arrays `Object[]`**, including `String[]`, `Object[][]`, `int[][]`: compares element counts and then deep-compares each pair of elements in turn; if a pair of elements is also an array, comparison continues at that level.
3. **Two values that are not a compatible array pair:** falls back to the left object's ordinary `equals`. Primitive arrays of different types, such as `int[]` and `long[]`, will not be considered equal merely because they represent the same numbers.
4. **Inner non-array object classes:** still use that class's own `equals` contract, without automatically using reflection to compare fields.

Algorithmic thinking (pseudocode, **not the actual JDK source code**):

```text
deepEqual(a, b):
    if a and b are the same reference: true
    if only one side is null: false
    if both sides are primitive arrays of the same type:
        compare same length and each value at each position
    if both sides are Object[]:
        compare length and deepEqual on each pair of elements
    otherwise:
        a.equals(b)
```

**Order and length always matter.** Two arrays `{1, 2}` and `{2, 1}` are not equal under `deepEquals`; `{1, 2}` and `{1, 2, 2}` are not equal either.

**Reference arrays with different component types can still deep-compare as equal.** For example, a `String[]` and an `Object[]` both containing `"a", "b"` can return `true`, because both are `Object[]` at runtime and each corresponding element is equal. Conversely, `int[]` and `long[]` with the same numeric representation are not equal because they are two different primitive array types.

### Multidimensional and jagged arrays

```java
int[][] m1 = {{1, 2}, {3}};
int[][] m2 = {{1, 2}, {3}};
int[][] m3 = {{1}, {2, 3}};

System.out.println(Objects.deepEquals(m1, m2)); // true
System.out.println(Objects.deepEquals(m1, m3)); // false
```

A two-dimensional array in Java is actually **an array of arrays**. `int[][]` can be treated as an `Object[]` whose elements are `int[]`; from there, deep comparison proceeds row by row. The illustrative snippet requires importing `Objects`.

If a reference array structure nests additional `boolean[]`, `double[]`, `char[]`, or other reference arrays, the corresponding rule applies at each array's position. However, for array structures that **self-reference cyclically** or contain indirect reference cycles, you should not assume the recursive algorithm will terminate safely; the `Arrays.deepEquals` contract is not intended for cyclic structures of that kind.

## 5. Distinguishing from `Arrays.equals()` and `Arrays.deepEquals()`

`java.util.Arrays` provides specific methods for arrays. Choose the method matching the **level of structure to compare**:

| API | Arguments accepted | Mechanism |
| --- | --- | --- |
| `Objects.equals(Object,Object)` | Any two references | Handles `null`, then calls normal `equals`. |
| `Objects.deepEquals(Object,Object)` | Any two references | Handles `null`, deep-compares if a suitable array pair; outside arrays uses `equals`. |
| `Arrays.equals(int[],int[])` and primitive overloads | Two primitive arrays of the same type | Compares **each element's value** in order. |
| `Arrays.equals(Object[],Object[])` | Two reference arrays | Compares each element with `Objects.equals` (nested arrays as elements are still compared by reference). |
| `Arrays.deepEquals(Object[],Object[])` | Two reference arrays | Recursively compares elements that are arrays as well. |

Example:

```java
int[][] x = {{1, 2}, {3, 4}};
int[][] y = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(x, y));      // false
System.out.println(Arrays.deepEquals(x, y));  // true
System.out.println(Objects.deepEquals(x, y)); // true
```

The illustrative snippet requires `import java.util.Arrays;` and `import java.util.Objects;`.

Reason: `int[][]` is an array of `int[]` elements; `Arrays.equals(x,y)` selects the `Object[]` overload and compares **row references**, whereas `Arrays.deepEquals` descends into each row. Meanwhile, `Objects.deepEquals` is convenient because it takes `Object` and handles runtime array types itself.

**A syntax trap:** `Arrays.deepEquals` takes two `Object[]` arguments, so it **cannot be called directly** with two `int[]` variables:

```java
// Arrays.deepEquals(new int[]{1}, new int[]{1}); // Does not compile!
System.out.println(Arrays.equals(new int[]{1}, new int[]{1})); // true
System.out.println(Objects.deepEquals(
        new int[]{1}, new int[]{1}));                       // true
```

With two one-dimensional `int[]` arrays, `Arrays.equals` is usually the clearest API for expressing intent.

## 6. Complete Java 17 example: testing edge cases

Save the entire program below into the file `ObjectsDeepEqualsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ObjectsDeepEqualsDemo {
    record Box(int[] values) {}

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};

        System.out.println("same reference: " + (a == b));
        System.out.println("equals int[]: " + Objects.equals(a, b));
        System.out.println("deepEquals int[]: " + Objects.deepEquals(a, b));
        System.out.println("Arrays.equals int[]: " + Arrays.equals(a, b));

        int[][] matrixA = {{1, 2}, {3, 4}};
        int[][] matrixB = {{1, 2}, {3, 4}};

        System.out.println("equals int[][]: "
                + Objects.equals(matrixA, matrixB));
        System.out.println("Arrays.equals int[][]: "
                + Arrays.equals(matrixA, matrixB));
        System.out.println("deepEquals int[][]: "
                + Objects.deepEquals(matrixA, matrixB));
        System.out.println("Arrays.deepEquals int[][]: "
                + Arrays.deepEquals(matrixA, matrixB));

        Object[] mixedA = {
                new byte[]{1, 2}, new String[]{"x", "y"}, null
        };
        Object[] mixedB = {
                new byte[]{1, 2}, new String[]{"x", "y"}, null
        };
        System.out.println("mixed nested arrays: "
                + Objects.deepEquals(mixedA, mixedB));

        System.out.println("different primitive types: "
                + Objects.deepEquals(new int[]{1}, new long[]{1}));

        List<int[]> listA = List.of(new int[]{1, 2});
        List<int[]> listB = List.of(new int[]{1, 2});
        System.out.println("list of arrays: "
                + Objects.deepEquals(listA, listB));

        Object[] outerA = {List.of(new int[]{1, 2})};
        Object[] outerB = {List.of(new int[]{1, 2})};
        System.out.println("array with nested list: "
                + Objects.deepEquals(outerA, outerB));

        Box boxA = new Box(new int[]{1, 2});
        Box boxB = new Box(new int[]{1, 2});
        System.out.println("record containing array: "
                + Objects.deepEquals(boxA, boxB));
        System.out.println("record component arrays: "
                + Objects.deepEquals(boxA.values(), boxB.values()));

        System.out.println("both null: "
                + Objects.deepEquals(null, null));
        System.out.println("one null: "
                + Objects.deepEquals(null, a));
        System.out.println("ordinary strings: "
                + Objects.deepEquals("java", new String("java")));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac ObjectsDeepEqualsDemo.java
java ObjectsDeepEqualsDemo
```

Stdout:

```text
same reference: false
equals int[]: false
deepEquals int[]: true
Arrays.equals int[]: true
equals int[][]: false
Arrays.equals int[][]: false
deepEquals int[][]: true
Arrays.deepEquals int[][]: true
mixed nested arrays: true
different primitive types: false
list of arrays: false
array with nested list: false
record containing array: false
record component arrays: true
both null: true
one null: false
ordinary strings: true
```

How to read the key results:

- `Objects.equals(a,b)` is `false` because `int[]` uses `Object.equals` by reference. `Objects.deepEquals(a,b)` is `true` because each number at the corresponding position matches.
- `Arrays.equals(matrixA,matrixB)` is `false`: this is a *shallow* comparison of the `int[]` row elements. Both deep comparisons return `true`.
- `mixedA` and `mixedB` are `Object[]` arrays containing `byte[]`, `String[]`, and `null`; all corresponding element pairs deep-compare as equal.
- `new int[]{1}` and `new long[]{1}` are not two arrays of the same type, so `deepEquals` returns `false`.
- Two `List<int[]>` instances do not automatically become a deep array comparison. `List.equals` calls `equals` on the `int[]` elements, meaning reference comparison, resulting in `false`. Even when the list sits inside an `Object[]`, `deepEquals` still only delegates to `List.equals` at that list level.
- Two `Box` records with different references whose component is two new arrays: default `record.equals` uses the array component's equality rule, which is by reference. To compare array contents, you must call `Objects.deepEquals` on **the array components themselves**, or manually implement deep equality for the enclosing type.
- Both `null` gives `true`; one `null` gives `false`, without needing manual null checks before calling `Objects.deepEquals`.

## 7. Why doesn't `deepEquals` automatically deep-compare every object containing arrays?

Consider two data types:

```java
record Snapshot(int[] bytes) {}
record CollectionBox(List<int[]> items) {}
```

These are two Java 17 record declarations that can be placed at top level, not a standalone program.

In `Snapshot`, the generated `equals` method only compares the `bytes` component according to that component's own rule. Because `bytes` is an array, that rule is **reference comparison**; `Objects.deepEquals(new Snapshot(...), new Snapshot(...))` does not use reflection to inspect components and does not change this behavior.

In `CollectionBox`, the generated `equals` calls `List.equals` on `items`. `List.equals` compares elements by position, but the elements here are `int[]`, so arrays with different references are still not equal. Using `Objects.deepEquals` on two `CollectionBox` instances does not change that mechanism either.

A custom class can implement `equals` using `Arrays.equals`, `Arrays.deepEquals`, or `Objects.deepEquals` for each field depending on its semantics. **Important boundary:** `deepEquals` automatically recurses through **arrays**, then stops automatic recursion when it hits a non-array object and calls that object's own `equals`.

If business logic requires comparing the values of each array inside a `List<int[]>`, you must design a function that iterates through pairs of elements and calls `Arrays.equals` for each `int[]`, or convert the element structure to an immutable value type with an appropriate `equals` contract. `Objects.deepEquals(listA,listB)` does not provide that algorithm out of the box.

## 8. Pairing deep comparison with `hashCode()`

Java's general rule: if `a.equals(b) == true`, then `a.hashCode() == b.hashCode()`. When overriding `equals` to compare **array contents** of a class, `hashCode` must also be computed compatibly with those contents.

| Data comparison approach | Corresponding hash code computation |
| --- | --- |
| `Arrays.equals(int[],int[])` | `Arrays.hashCode(int[])` |
| `Arrays.equals(Object[],Object[])` | `Arrays.hashCode(Object[])` |
| `Arrays.deepEquals(Object[],Object[])` | `Arrays.deepHashCode(Object[])` |
| `Objects.deepEquals(int[][],int[][])` | `Arrays.deepHashCode(int[][])` |

There is no corresponding general-purpose `Objects.deepHashCode(Object)` method in `java.util.Objects`. You must pick the `Arrays.hashCode`/`Arrays.deepHashCode` function that matches **the array type and equality semantics**. `Objects.hashCode(array)` only calls the array object's hash according to object rules; it is **not** a deep hash by array content. `Objects.hash(array)` is also not a general replacement for `Arrays.deepHashCode` and has varargs characteristics that easily cause confusion with `Object[]` arrays.

If a class uses `Arrays.deepEquals` for an `int[][]` field yet computes the hash using `System.identityHashCode` or the array's `Object.hashCode`, two objects with equal contents can have different hashes, violating the contract.

### Complete example: matrix key with deep equality

Save as `DeepMatrixKeyDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class DeepMatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] rows;

        MatrixKey(int[][] input) {
            Objects.requireNonNull(input, "input");
            rows = new int[input.length][];
            for (int i = 0; i < input.length; i++) {
                rows[i] = Objects.requireNonNull(
                        input[i], "row " + i).clone();
            }
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof MatrixKey other)) return false;
            return Arrays.deepEquals(rows, other.rows);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(rows);
        }

        @Override
        public String toString() {
            return Arrays.deepToString(rows);
        }
    }

    public static void main(String[] args) {
        int[][] external = {{1, 2}, {3, 4}};
        MatrixKey original = new MatrixKey(external);
        MatrixKey same = new MatrixKey(
                new int[][]{{1, 2}, {3, 4}});

        System.out.println("equals: " + original.equals(same));
        System.out.println("same hash: "
                + (original.hashCode() == same.hashCode()));

        Map<MatrixKey, String> map = new HashMap<>();
        map.put(original, "saved");
        System.out.println("lookup: " + map.get(same));

        external[0][0] = 99;
        System.out.println("lookup after input changed: "
                + map.get(same));

        MatrixKey changed = new MatrixKey(external);
        System.out.println("changed differs: "
                + original.equals(changed));
        System.out.println("original data: " + original);
    }
}
```

Compile/run:

```bash
javac DeepMatrixKeyDemo.java
java DeepMatrixKeyDemo
```

Stdout:

```text
equals: true
same hash: true
lookup: saved
lookup after input changed: saved
changed differs: false
original data: [[1, 2], [3, 4]]
```

The `MatrixKey` class compares each row's contents of the matrix with `Arrays.deepEquals` and computes the corresponding hash with `Arrays.deepHashCode`. The constructor proactively **clones each row**, so mutating the input matrix after key creation does not alter the internal state of the key. This example is limited to `int[][]` matrices without `null` rows; if business logic allows `null` rows, the constructor must apply an appropriate policy.

**Immutability and defensive copying are critical when acting as a hash key:** If an array or sub-element is modified after placing the key into a `HashMap`/`HashSet`, both `equals` and the hash code can change, causing the collection to fail to find the entry by the expected value. In this example, both array levels are copied and no getter exposes `rows`, so the internal data of the key remains stable after creation.

## 9. Common mistakes when choosing a comparison method

| Mistake | Why it is wrong or incomplete | Appropriate approach |
| --- | --- | --- |
| `Objects.equals(new int[]{1}, new int[]{1})` expecting `true`. | Arrays do not override `equals`. | `Arrays.equals` or `Objects.deepEquals`. |
| `Arrays.equals(matrix1, matrix2)` on `int[][]` expecting element-by-element comparison. | `int[][]` is shallow-compared by row references. | `Arrays.deepEquals(matrix1,matrix2)`. |
| Calling `Arrays.deepEquals` directly with two `int[]`. | That overload requires `Object[]`, and `int[]` is not `Object[]`. | `Arrays.equals(int[],int[])`. |
| Assuming `Objects.deepEquals` always inspects every field of a record/class. | For two non-array objects, it uses the object's `equals`. | Override `equals` on the enclosing class or compare the array field directly. |
| Assuming `Objects.deepEquals(List<int[]>, List<int[]>)` always compares numbers inside the arrays. | `List.equals` uses `equals` of the `int[]` elements, i.e., by reference. | Iterate the list and use `Arrays.equals` on corresponding arrays. |
| Using `Objects.hashCode(array)` with deep `equals`. | The hash is not based on array contents. | Use the matching `Arrays.hashCode`/`Arrays.deepHashCode`. |
| Using a mutable array as a hash key while still modifying its contents. | The hash can change, and the collection does not re-index automatically. | Defensive copying, freezing data, or using an immutable key. |
| Choosing `deepEquals` without considering ordering requirements. | Arrays are compared by position, not as a set of elements. | If order-insensitive comparison is needed, design a separate algorithm. |
| Comparing two arrays of different primitive types just because the numeric values look identical. | `int[]` and `long[]` are two distinct array types. | Convert values intentionally when business logic allows. |

Another subtle trap is an array with cyclic references. Recursive APIs such as `Arrays.deepEquals`, `Arrays.deepHashCode`, and `Arrays.deepToString` should not be treated as general graph processors. For `Arrays.deepEquals` and `deepHashCode`, behavior on array structures containing cycles may be undefined by the contract. If the data is a graph with cycles, a graph comparison algorithm that tracks visited nodes is needed rather than relying solely on deep array comparison.

## 10. Self-check exercises

1. Two `int[]` arrays created by two `new` statements have the same contents: what do `Objects.equals` and `Objects.deepEquals` return?
2. Why can `Arrays.equals(int[][],int[][])` be `false` while `Arrays.deepEquals(int[][],int[][])` is `true`?
3. What does `Objects.deepEquals(null,null)` return? What if one side is an array and the other is `null`?
4. Are `Objects.deepEquals(new int[]{1},new long[]{1})` equal? Why?
5. Will two `List<int[]>` with the same numeric structure but containing separate arrays automatically be equal via `Objects.deepEquals`?
6. Why doesn't `Objects.deepEquals` automatically make two records containing arrays with different references equal?
7. In a class that overrides `equals` to compare an `Object[][]` field using `Arrays.deepEquals`, which API should be used to compute that field's hash code?
8. What risk arises when a `MatrixKey` used in a `HashMap` still has external code holding a reference to its internal array and modifying its contents?
9. When should `Arrays.equals(int[],int[])` be chosen over `Objects.deepEquals`?
10. Why does deep array comparison not necessarily mean "deep comparison of every object" in a data structure?

**Key takeaway:** `Objects.equals` calls ordinary object equality; for arrays, that is usually **same reference**. `Objects.deepEquals` adds **content comparison for array pairs**, including primitive arrays and multidimensional nested arrays, but does not automatically drill down into classes/`List` instances containing arrays. When building a value class with deep comparison, always choose the matching `hashCode` and keep the data participating in equality stable.