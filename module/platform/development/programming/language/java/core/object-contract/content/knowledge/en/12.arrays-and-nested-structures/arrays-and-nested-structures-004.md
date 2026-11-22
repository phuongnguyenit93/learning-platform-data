# `Objects.deepEquals()` and How It Handles Two Arguments

`java.util.Objects.deepEquals(Object a, Object b)` is a utility method to check whether **two arguments are equal**, while handling **arrays and nested arrays** by content. The key difference compared to `Objects.equals(a, b)` is: when both arguments are arrays, `deepEquals` can compare corresponding elements, even when an element is another array; whereas `Objects.equals` normally relies on the array's own `equals`, which compares identity.

This is useful when data consists of `int[]`, `String[]`, `int[][]`, `Object[]` containing multiple array types, or nested structures. However, **`deepEquals` does not automatically descend into every field of a regular Java object**: if the two arguments are not arrays, the result still depends on the `equals` of the left-hand object.

## 1. Declaration and meaning

The method belongs to `java.util.Objects`:

~~~java
public static boolean deepEquals(Object a, Object b)
~~~

Both parameters have type `Object`, so you can pass a regular object, a primitive array such as `int[]`, an object array such as `String[]`, a multidimensional array such as `int[][]`, or `null`. There is no need to cast a primitive array to `Object[]`.

Behavior summary:

| Two arguments | Result |
| --- | --- |
| Same reference, including both `null` | `true`. |
| One argument is `null`, the other is non-`null` | `false`. |
| Both are object arrays (`Object[]` or compatible array types) | Compares elements in order and continues descending when an element is an array. |
| Both are primitive arrays of the same type, e.g., `int[]` | Compares element-by-element content following the corresponding `Arrays.equals` rules. |
| Both are nested arrays, e.g., `int[][]` | Compares corresponding sub-arrays recursively. |
| Not both are arrays | Essentially uses `a.equals(b)` after handling `null`/same-reference; does not automatically inspect all fields. |

Arguments that are **the same array** are always equal by the reference-check branch first, even if there are complex structures inside the array. Only for **two independent arrays** does `deepEquals` need to check the elements.

### Important processing order

The main flow can be understood as follows:

1. If `a == b`, return `true` immediately. This case also covers `a == null` and `b == null`.
2. If exactly one argument is `null`, return `false`.
3. For two non-`null` arguments, perform deep comparison appropriate for arrays: if they are object arrays, traverse elements and possibly descend into sub-arrays; if they are two primitive arrays of the same kind, compare contents; the remaining cases use the appropriate `equals` semantics.

This is a behavioral model for learning, not a promise about the exact order of internal calls across every JDK release. What to remember is **comparing arrays by content when appropriate, handling `null` safely, while non-array objects still depend on `equals`**.

## 2. Java 17+ example: two arguments, `null`, arrays, and regular objects

File **`DeepEqualsArgumentsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DeepEqualsArgumentsDemo {
    public static void main(String[] args) {
        System.out.println(Objects.deepEquals(null, null));
        System.out.println(Objects.deepEquals(null, new int[] {1, 2}));

        int[] first = {1, 2};
        int[] second = {1, 2};
        int[] alias = first;

        System.out.println(first == second);
        System.out.println(Objects.equals(first, second));
        System.out.println(Objects.deepEquals(first, second));
        System.out.println(Objects.deepEquals(first, alias));
        System.out.println(Objects.deepEquals(first, new int[] {1, 3}));
        System.out.println(Objects.deepEquals(first, new long[] {1, 2}));

        String left = new String("Java");
        String right = new String("Java");
        System.out.println(left == right);
        System.out.println(Objects.deepEquals(left, right));

        String[] names1 = {"Lan", "An"};
        String[] names2 = {"Lan", "An"};
        System.out.println(Objects.equals(names1, names2));
        System.out.println(Objects.deepEquals(names1, names2));
        System.out.println(Arrays.equals(names1, names2));
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac DeepEqualsArgumentsDemo.java
java DeepEqualsArgumentsDemo
~~~

Standard output:

~~~text
true
false
false
false
true
true
false
false
false
true
false
true
true
~~~

Explanation by group:

- `deepEquals(null, null)` returns `true`; only one side `null` returns `false`. Thus calling this method does not throw `NullPointerException` merely because one parameter is `null`.
- Two independent `int[]` containing `{1, 2}` have `first == second` as `false`. `Objects.equals(first, second)` is also `false` because `int[]` does not override `Object.equals` to compare elements. Yet `Objects.deepEquals(first, second)` is `true`.
- `alias = first` is the same reference, so `deepEquals(first, alias)` is `true`. If `2` is replaced with `3`, contents differ so it is `false`. An `int[]` and a `long[]` containing similar-looking numbers are still two different primitive array types, not automatically coerced into a common type by `deepEquals`.
- Two independent `String`s have `==` as `false` but `deepEquals` as `true`: for non-array strings, comparison uses `String.equals`, not reflection/comparing internal fields of the string.
- For two independent `String[]`, `Objects.equals` returns `false`, while `Objects.deepEquals` and `Arrays.equals` both return `true` when corresponding elements have the same content.

Note: `Arrays` is imported in the example to demonstrate same-level array comparison; it is not required when calling only `Objects.deepEquals`.

## 3. Nested arrays: where does “deep” happen?

Consider two `int[][]` matrices. In Java, this is an **array containing references to `int[]` arrays**, so comparing the outer array must continue comparing sub-array contents.

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(a == b);                    // false
System.out.println(java.util.Arrays.equals(a, b));     // false
System.out.println(java.util.Arrays.deepEquals(a, b)); // true
System.out.println(java.util.Objects.deepEquals(a, b)); // true
~~~

This is an illustrative snippet in a method body. `Arrays.equals(a, b)` here only compares the **elements of the outer array**; each element is an `int[]`, and `int[]` does not have content-based `equals`. `Arrays.deepEquals(a, b)` and `Objects.deepEquals(a, b)` descend into each `int[]` and thus yield `true`.

The comparison can be visualized as:

~~~text
a: int[][{1, 2}, {3}]
b: int[][{1, 2}, {3}]

Outer level: same element count?        Yes
  a[0] and b[0]: compare {1, 2} vs {1, 2}  Equal
  a[1] and b[1]: compare {3} vs {3}        Equal
Conclusion:                                true
~~~

For an `Object[]` array containing mixed elements, `deepEquals` also knows how to distinguish regular elements from array elements:

~~~java
Object[] x = {
    "Java",
    new int[] {1, 2},
    new Object[] {"nested", new long[] {9, 10}}
};
Object[] y = {
    new String("Java"),
    new int[] {1, 2},
    new Object[] {"nested", new long[] {9, 10}}
};

System.out.println(java.util.Objects.equals(x, y));     // false
System.out.println(java.util.Objects.deepEquals(x, y)); // true
~~~

`"Java"` and `new String("Java")` have equal content; the `int[]` has the same elements and the inner `long[]` has the same elements. The two outer arrays have different references yet are equal under deep comparison.

**Java does not automatically “flatten” arrays:** nesting structure, length, and element order still matter. For example, `int[][] {{1, 2}, {3}}` is **not** equal to `int[][] {{1}, {2, 3}}`, even though concatenating all numbers in order gives `1, 2, 3`.

## 4. `Objects.deepEquals`, `Objects.equals`, and `Arrays.equals`

These APIs answer slightly different questions:

| API | Parameters | Notable comparison behavior |
| --- | --- | --- |
| `Objects.equals(a, b)` | Two `Object`s | `null`-safe; if both are non-`null`, calls `a.equals(b)`. Arrays normally compare references. |
| `Objects.deepEquals(a, b)` | Two `Object`s | `null`-safe; if both arguments are arrays, performs deep comparison appropriate for arrays; if regular objects, relies on `equals`. |
| `Arrays.equals(a, b)` | Two one-dimensional arrays with matching overload | Compares elements at the current level; for nested arrays containing sub-arrays, does not automatically deep-compare sub-arrays. |
| `Arrays.deepEquals(a, b)` | Two `Object[]`s | Deeply compares elements/sub-arrays. Can be used with `int[][]` because each `int[][]` is a reference array containing `int[]`; cannot be called directly with two `int[]`. |

A very important point about data types: `Arrays.deepEquals(Object[] a, Object[] b)` requires **a reference array at the outer level**. Because `int[]` is not an `Object[]`, the statement `Arrays.deepEquals(new int[]{1}, new int[]{1})` **does not compile**. For two `int[]`, use `Arrays.equals` or `Objects.deepEquals`.

### Choosing the tool by data type

- Two `int[]` or `double[]` of the same type: `Arrays.equals` clearly expresses one-dimensional content comparison intent.
- Two one-dimensional `String[]`: `Arrays.equals` is sufficient if only comparing each `String`.
- Two `int[][]` or two `Object[]` containing sub-arrays: `Arrays.deepEquals` or `Objects.deepEquals` when deep comparison is desired.
- Two parameters currently typed as `Object`, which may or may not be arrays: `Objects.deepEquals` handles both cases according to the stated rules.
- Two regular objects, unrelated to arrays: `Objects.equals` usually expresses intent more clearly; using `Objects.deepEquals` does not provide deep comparison of internal object fields.

## 5. “Deep” does not mean automatically comparing every property of a class

Suppose a class `Box` contains an `int[]` field, but **does not override `equals`**. When passing two independent `Box` instances to `Objects.deepEquals`, the result is still `false`, even when the two inner arrays have identical content.

File **`DeepEqualsObjectDemo.java`**:

~~~java
import java.util.Objects;

public class DeepEqualsObjectDemo {
    static final class Box {
        private final int[] values;

        Box(int[] values) {
            this.values = values;
        }
    }

    record ArrayRecord(int[] values) {}

    public static void main(String[] args) {
        Box first = new Box(new int[] {4, 5});
        Box second = new Box(new int[] {4, 5});

        System.out.println(first == second);
        System.out.println(Objects.deepEquals(first, second));
        System.out.println(Objects.deepEquals(first.values, second.values));

        ArrayRecord r1 = new ArrayRecord(new int[] {4, 5});
        ArrayRecord r2 = new ArrayRecord(new int[] {4, 5});

        System.out.println(r1.equals(r2));
        System.out.println(Objects.deepEquals(r1, r2));
        System.out.println(Objects.deepEquals(r1.values(), r2.values()));
    }
}
~~~

Run:

~~~bash
javac DeepEqualsObjectDemo.java
java DeepEqualsObjectDemo
~~~

Standard output:

~~~text
false
false
true
false
false
true
~~~

Analysis:

- `Box` is a regular class that does not override `equals`, so `Box.equals` inherits from `Object` and only compares identity. `Objects.deepEquals(first, second)` does not automatically inspect the `values` field: result is `false`.
- But when passing **the two arrays `first.values` and `second.values` themselves**, `deepEquals` compares elements and returns `true`.
- A Java record generates `equals` based on its components, yet for an **array** component, comparison still follows array identity when the two records are different. Therefore two independent `ArrayRecord` instances containing `int[]` with identical content still have `equals` return `false`.
- To make two instances of a class or record **equal by array content**, you must build the `equals`/`hashCode` semantics of the enclosing type yourself, rather than merely changing the outer call to `Objects.deepEquals(box1, box2)`.

This helps distinguish **deep comparison on arrays passed as arguments** from **deep comparison across fields of any arbitrary object**. Java only provides the first case in `Objects.deepEquals`.

## 6. Using `Objects.deepEquals` in a value object's `equals`

A common application is a class holding a nested array structure that wants to define equality based on all elements. When overriding `equals`, you can use `Objects.deepEquals(data, that.data)`. However, **`hashCode` must use the hashing algorithm corresponding to deep comparison**.

File **`MatrixKeyDemo.java`** (Java 17+):

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] data;

        MatrixKey(int[][] source) {
            Objects.requireNonNull(source);
            data = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                int[] row = Objects.requireNonNull(source[i]);
                data[i] = Arrays.copyOf(row, row.length);
            }
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixKey that)) {
                return false;
            }
            return Objects.deepEquals(data, that.data);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(data);
        }
    }

    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3}};
        MatrixKey first = new MatrixKey(source);
        MatrixKey sameValue = new MatrixKey(new int[][] {{1, 2}, {3}});
        MatrixKey different = new MatrixKey(new int[][] {{1, 2}, {4}});

        System.out.println(first == sameValue);
        System.out.println(first.equals(sameValue));
        System.out.println(first.hashCode() == sameValue.hashCode());
        System.out.println(first.equals(different));

        Map<MatrixKey, String> names = new HashMap<>();
        System.out.println(names.put(first, "old"));
        System.out.println(names.put(sameValue, "new"));
        System.out.println(names.put(different, "other"));
        System.out.println(names.size());
        System.out.println(names.get(first));

        source[0][0] = 99;
        System.out.println(first.equals(sameValue));
    }
}
~~~

Compile/run:

~~~bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
~~~

Standard output:

~~~text
false
true
true
false
null
old
null
2
new
true
~~~

Meaning:

1. `first` and `sameValue` are two independent `MatrixKey` objects, but their matrix data is identical so `equals` returns `true`.
2. `hashCode` uses `Arrays.deepHashCode(data)` so that two matrices equal under `Objects.deepEquals` also have equal hash codes. This is a **mandatory** requirement of the `equals`/`hashCode` contract.
3. `different` contains value `4` at another position, so it is not equal to `first`.
4. Adding `sameValue` to `HashMap` replaces the value for the existing logical key; `size()` does not increase. Key `different` creates a second entry.
5. The constructor copies **each sub-array**, so modifying `source[0][0]` externally does not alter data inside `first`. This keeps the key's hash stable after being used in `HashMap`.

The example allows rows of different lengths (`int[][]` is an array of arrays) but rejects `null` rows with `requireNonNull`. That is a design decision of `MatrixKey`, not a limitation of `Objects.deepEquals`: deep comparison itself can compare corresponding `null` positions.

**Do not replace `Arrays.deepHashCode(data)` with `Objects.hashCode(data)`:** for arrays, `Objects.hashCode` delegates to the array's own `hashCode`, which is not a deep content hash. Two `MatrixKey`s equal by array data could receive mismatched hashes and break usage as keys in hash collections.

## 7. Important corner cases

### 7.1. Both arguments `null`

~~~java
Objects.deepEquals(null, null);             // true
Objects.deepEquals(null, new Object[0]);    // false
Objects.deepEquals(new int[0], new int[0]); // true
~~~

Two empty arrays with different references are still equal by content if of matching type/structure. An empty array is not the same as `null`.

### 7.2. Two arrays with the same data but different primitive array types

~~~java
Objects.deepEquals(new int[] {1, 2}, new long[] {1, 2}); // false
Objects.deepEquals(new int[] {1}, new int[] {1});         // true
~~~

`Objects.deepEquals` **does not perform numeric type conversion** to treat `int[]` and `long[]` as the same value structure. If business logic wants comparison after type normalization, a dedicated conversion/comparison must be defined.

### 7.3. Reference arrays can have different runtime types

~~~java
Objects.deepEquals(
    new String[] {"Java"},
    new Object[] {"Java"}
); // true
~~~

Both arguments are reference arrays (`Object[]`) with one element of equal content; deep comparison can return `true` even if the runtime array classes differ. Do not interpret `deepEquals` as requiring the `getClass()` of the two arrays to be identical.

### 7.4. How `NaN` and `+0.0/-0.0` are compared in floating-point arrays

`Arrays.equals` operations for `float[]`/`double[]` have rules based on canonicalized bits corresponding to `Float.equals`/`Double.equals`: `NaN` representations are considered equal and `+0.0` differs from `-0.0`. Because `Objects.deepEquals` uses the corresponding array semantics, take note:

~~~java
Objects.deepEquals(
    new double[] {Double.NaN},
    new double[] {Double.NaN}
); // true

Objects.deepEquals(
    new double[] {+0.0},
    new double[] {-0.0}
); // false
~~~

If business logic needs different floating-point rules, do not assume `deepEquals` uses the exact comparison you want. Define an appropriate comparison, and also consider the equality and hash code contract if implementing `equals`.

### 7.5. Arrays containing circular references

If an `Object[]` array contains **itself** as an element, or arrays reference each other forming a cycle, deep traversal may recurse indefinitely and cause errors such as `StackOverflowError`. The `Arrays.deepEquals` documentation does not define behavior for arrays containing circular references. Do not use `Objects.deepEquals` as a general graph-comparison algorithm capable of handling cycles; if data is a graph, design an algorithm that tracks visited nodes.

### 7.6. Elements are custom objects

~~~java
class Item {
    final int id;
    Item(int id) { this.id = id; }
}

Object[] left = {new Item(1)};
Object[] right = {new Item(1)};
System.out.println(java.util.Objects.deepEquals(left, right)); // false
~~~

The snippet above is illustrative code in an appropriate class and method declaration context. Because `Item` does not override `equals`, comparing two `Item` instances inside the array still uses identity only. `deepEquals` **does not automatically open each `Item` to compare the `id` field**. If you want `Item` elements to be equal by value, implement `Item.equals` and `Item.hashCode` appropriately.

## 8. Common mistakes and how to avoid them

1. **Assuming `Objects.equals` is enough for arrays.** For two independent `int[]` or `String[]` with identical content, `Objects.equals` normally returns `false`. Choose `Arrays.equals` or `Objects.deepEquals` when comparing content.
2. **Using `Arrays.equals` on nested arrays and expecting deep comparison.** For `int[][]`, elements at the outer level are `int[]`s. Choose `Arrays.deepEquals` or `Objects.deepEquals` when you want to compare each sub-array.
3. **Thinking `Objects.deepEquals` reflects every field of a class.** For two regular objects, the method relies on the class's `equals`. It does not automatically compare nested fields or properties.
4. **Using `Objects.deepEquals` in `equals` but forgetting to update `hashCode`.** For multidimensional arrays, use the corresponding `Arrays.deepHashCode` to avoid breaking hash collection contracts.
5. **Allowing the array structure to mutate after using it as a `HashMap` key.** When data used in `equals`/`hashCode` changes, the map may fail to find the entry. Use defensive copies and immutable value object design when appropriate.
6. **Using deep comparison on cyclic graphs.** Cases where an array contains itself or cycles through other arrays are not guaranteed to be safe.
7. **Treating “business-equivalent value” and “`deepEquals` true” as the same thing.** `deepEquals` respects array type, element order, and component object `equals`; it does not automatically normalize text, numbers, order, or business identifiers.

## 9. Process for choosing a comparison method

When comparing two values in Java:

1. **Check the actual data type:** regular object, primitive array, reference array, nested array, or an object containing an array field.
2. **If you want to know whether they are the same instance**, use `==` on references.
3. **If you only want to compare values of two regular objects**, use `Objects.equals(a, b)` when `null` handling is needed, ensuring that type has an appropriate `equals`.
4. **If it is a typed one-dimensional array**, use `Arrays.equals(a, b)`.
5. **If it is a multi-level array**, choose `Arrays.deepEquals` for an `Object[]` at the outer level or `Objects.deepEquals` for two `Object`-typed values.
6. **If writing a value object containing arrays**, implement `equals` comparing array fields by content and `hashCode` over the same data; protect against unintended mutation.
7. **If there are special requirements** such as numeric tolerance comparison, ignoring order, normalizing text, or data with circular references, write a custom comparison algorithm suited to the contract and problem goal.

## 10. Self-check questions

1. Why is `Objects.equals(new int[]{1,2}, new int[]{1,2})` `false` while `Objects.deepEquals(...)` is `true`?
2. When both arguments are `null`, what is the result of `Objects.deepEquals`? What if exactly one argument is `null`?
3. Why can `Arrays.equals(a, b)` on two independent `int[][]` with identical content return `false`, while `Arrays.deepEquals(a,b)` returns `true`?
4. If `Box` has an `int[] values` field but does not override `equals`, does calling `Objects.deepEquals(box1,box2)` automatically compare each element of `values`?
5. Why should a class using `Objects.deepEquals(matrix1,matrix2)` in `equals` use the corresponding `Arrays.deepHashCode(matrix)` in `hashCode`?
6. What does `Objects.deepEquals(new int[]{1}, new long[]{1})` return? Does the method automatically convert `int` to `long`?
7. If an `Object[]` array contains a reference to itself, why can we not assume deep comparison will always terminate safely?

**Key takeaway:** `Objects.deepEquals(a, b)` accepts **two `Object` arguments**, checks same-reference/`null` first, and then compares **array content, including nested arrays** when both arguments are arrays. For regular objects, it still relies on `equals`. When using deep comparison in `equals` of a class containing arrays, always keep a matching `hashCode` and protect data from unintended mutation.