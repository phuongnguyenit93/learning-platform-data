# Arrays support clone() and multi-dimensional arrays still share sub-arrays

## 1. Core concept

Arrays in Java are **objects**. Although arrays do not declare classes using ordinary syntax, every array type supports `clone()`; arrays also implement the `Cloneable` marker interface. When calling `array.clone()`, Java creates **a new array object with the same runtime type and same length**, then copies each element of the original array into the new array.

The key point is that **array `clone()` is a shallow copy, copying only one level**:

- For `int[]`, `double[]`, `boolean[]`..., elements are primitive values so each array holds a separate copy of values.
- For `String[]`, `Person[]`, `int[][]`..., elements are **references**; `clone()` copies reference values, **without duplicating referenced objects**.
- For multi-dimensional arrays such as `int[][]` or `String[][][]`, elements of the outer array are **references to sub-arrays**. Therefore cloning the outer array **does not clone the sub-arrays**.

Visual example:

```text
int[][] original = { {1, 2}, {3, 4} };
int[][] copy = original.clone();

original ──► outer array A ──► [row X reference, row Y reference]
copy     ──► outer array B ──► [row X reference, row Y reference]
                                          │               │
                                          ▼               ▼
                                      [1, 2]          [3, 4]
```

`original` and `copy` are two different outer arrays, **but `original[0] == copy[0]` and `original[1] == copy[1]` are both true**.

**Keep in mind first:** `clone()` creates a new outer array shell; it does not automatically descend into object elements or inner dimensions.

## 2. Arrays are a special case compared to Object.clone()

In `java.lang.Object`, `clone()` is declared `protected`, returns `Object`, and the default mechanism normally involves `Cloneable`. However, **array types receive special support from Java**:

```java
int[] a = {1, 2, 3};
int[] b = a.clone();  // No cast needed; the result is int[].
```

This is an illustrative snippet that can be placed inside a Java method. For arrays:

1. `clone()` can be called directly as a public method.
2. The expression `a.clone()` has the **corresponding array type** (`int[]` in the example), without requiring a cast from `Object`.
3. The new array has a different reference from the original array, with the same `length` and component type.
4. You do not have to declare `implements Cloneable` for an array, nor catch `CloneNotSupportedException` when calling an array's `clone()`.
5. Contents are copied **one level**, not a recursive deep copy.

The `Cloneable` interface is a **marker interface** (declaring no public `clone()` method). Do not infer that every object implementing `Cloneable` provides a convenient public clone API like arrays do. In particular, for custom-defined classes, `clone()` must be designed and exposed separately if support is truly desired.

## 3. Example 1: primitive arrays and reference arrays

Create file `OneDimensionalCloneDemo.java`:

```java
import java.util.Arrays;

public class OneDimensionalCloneDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 99;

        System.out.println(numbers == numberCopy);
        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.toString(numberCopy));

        Box[] boxes = {new Box(10), new Box(20)};
        Box[] boxCopy = boxes.clone();

        System.out.println(boxes == boxCopy);
        System.out.println(boxes[0] == boxCopy[0]);

        boxCopy[0].value = 77;
        System.out.println(boxes[0].value);

        boxCopy[1] = new Box(88);
        System.out.println(boxes[1].value);
        System.out.println(boxCopy[1].value);
    }
}
```

Compile and run with JDK 17+:

```bash
javac OneDimensionalCloneDemo.java
java OneDimensionalCloneDemo
```

Output:

```text
false
[1, 2, 3]
[99, 2, 3]
false
true
77
20
88
```

Explanation:

- `numbers` and `numberCopy` are two separate `int[]` arrays. Assigning `numberCopy[0] = 99` does not modify element `numbers[0]`, because each slot directly stores an `int` value.
- `boxes` and `boxCopy` are also **two different arrays**, yet slot 0 of both holds the same `Box` reference. Modifying `boxCopy[0].value` modifies the object that `boxes[0]` also points to; output is `77`.
- `boxCopy[1] = new Box(88)` only **replaces the reference in the copied array**. It does not change slot `boxes[1]`, so the value in the original object stays `20`.

Distinguish clearly between **reassigning an array slot** and **mutating the object behind the reference in that slot**. This is also the key to understanding multi-dimensional arrays.

## 4. Multi-dimensional arrays are actually arrays of arrays

Java does not need to store `int[][]` as a contiguous rectangular block. An `int[][]` is an array holding references to `int[]` arrays; each row array can have different lengths, and a row can even be `null`. A form with rows of differing lengths is commonly called a **jagged/ragged array**.

Consider:

```java
int[][] original = {
    {1, 2},
    {3, 4}
};
int[][] outerCopy = original.clone();
```

This is an illustrative snippet that can be placed inside a method. After the clone statement:

| Expression | Result | Reason |
| --- | --- | --- |
| `original == outerCopy` | `false` | The two outer arrays are two objects |
| `original.length == outerCopy.length` | `true` | Row count is copied |
| `original[0] == outerCopy[0]` | `true` | Both slots hold the same row 0 reference |
| `original[1] == outerCopy[1]` | `true` | Both slots hold the same row 1 reference |
| `original[0][0] == outerCopy[0][0]` | `true` | Reading the same element in the same sub-array |

If assigning `outerCopy[0][0] = 90`, the original array also sees `original[0][0] == 90`. Conversely, `outerCopy[1] = new int[] {7, 8}` only replaces the reference to row 1 **in the new outer array**; row 1 of `original` still keeps `{3, 4}`.

For `int[][][]`, `clone()` also **only copies the outermost dimension**. Inner `int[][]` objects remain shared, along with the `int[]` arrays they point to.

## 5. Example 2: modifying a sub-array element vs. replacing an entire sub-array

Create file `MultidimensionalCloneDemo.java`:

```java
import java.util.Arrays;

public class MultidimensionalCloneDemo {
    public static void main(String[] args) {
        int[][] original = {
            {1, 2},
            {3, 4}
        };

        int[][] copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original[0] == copy[0]);
        System.out.println(Arrays.deepEquals(original, copy));

        copy[0][0] = 90;
        System.out.println(original[0][0]);

        copy[1] = new int[] {7, 8};
        System.out.println(Arrays.toString(original[1]));
        System.out.println(Arrays.toString(copy[1]));

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
    }
}
```

Run:

```bash
javac MultidimensionalCloneDemo.java
java MultidimensionalCloneDemo
```

Output:

```text
false
true
true
90
[3, 4]
[7, 8]
[[90, 2], [3, 4]]
[[90, 2], [7, 8]]
```

Pay special attention to the two operations with very different meanings:

1. **`copy[0][0] = 90`** goes through the shared reference to modify **an element of row 0's array itself**. Hence `original[0][0]` is also `90`.
2. **`copy[1] = new int[] {7, 8}`** only assigns a new row reference into **the outer array `copy`**. The outer array `original` continues pointing to the old row `[3, 4]`.

`Arrays.deepEquals(original, copy)` is initially `true` because the value structures in the rows match. However, `deepEquals` **does not prove the array was deep-cloned**: even two arrays sharing row references can be equal in contents.

## 6. To deep-copy int[][], clone each row

For an `int[][]` where each row contains only primitive values, you can create a new outer array and clone **each non-null sub-array**. Then each `int[]` row is a new object, and `int` data is independent.

Create file `DeepCopyRowsDemo.java`:

```java
import java.util.Arrays;

public class DeepCopyRowsDemo {
    static int[][] copyAllRows(int[][] source) {
        if (source == null) {
            return null;
        }
        int[][] copy = source.clone();
        for (int row = 0; row < source.length; row++) {
            if (source[row] != null) {
                copy[row] = source[row].clone();
            }
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] original = {
            {1, 2},
            null,
            {3}
        };
        int[][] deepCopy = copyAllRows(original);

        System.out.println(original == deepCopy);
        System.out.println(original[0] == deepCopy[0]);
        System.out.println(deepCopy[1] == null);
        System.out.println(Arrays.deepEquals(original, deepCopy));

        deepCopy[0][0] = 42;
        System.out.println(original[0][0]);
        System.out.println(deepCopy[0][0]);
        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(deepCopy));
    }
}
```

Run:

```bash
javac DeepCopyRowsDemo.java
java DeepCopyRowsDemo
```

Output:

```text
false
false
true
true
1
42
[[1, 2], null, [3]]
[[42, 2], null, [3]]
```

The `copyAllRows` method performs:

1. Returns `null` if the input is `null`; this is the policy chosen by the example.
2. Copies the outer array using `source.clone()`.
3. Loops through rows, copying each `int[]` via `clone()`, preserving `null` rows.
4. Returns a new array sharing **no non-null row arrays** with the input, in this case.

Because the innermost data is only `int`, cloning each row suffices to **isolate the numeric elements** of the two-dimensional array. For `int[][][]`, deep copying needs to continue another level. For `Person[][]`, cloning two array levels can still **share `Person` objects**; if objects can be mutated, a separate copying strategy is needed for those objects.

### Important limitation: internal aliasing

If `source[0]` and `source[1]` originally pointed to the same row array, the per-row cloning approach above will create **two distinct new rows**. Thus numeric data is copied, yet the relationship of **two slots pointing to one object** may not be preserved. When the requirement is copying an **object graph** and preserving sharing/circular-reference relationships, a specialized copy algorithm must be designed (typically tracking already-copied objects). One should not claim that every "deep copy" means the exact same thing across all applications.

## 7. How do clone(), Arrays.copyOf(), and System.arraycopy() differ?

Other options also copy only **one level** when elements are references.

| Approach | Primary effect | For `int[][]` |
| --- | --- | --- |
| `source.clone()` | New array of same length, preserving same array type | New outer array, **shares rows** |
| `Arrays.copyOf(source, source.length)` | Creates a new array and copies elements, can specify new length | New outer array, **shares rows** |
| `System.arraycopy(source, 0, dest, 0, n)` | Copies elements into an existing destination array | Copies **row references**, does not clone rows |
| `source.clone()` then clone each `source[row]` | Creates a new outer array and new rows | Independent `int[]` rows |

The methods above do not automatically clone objects behind references. Using `Arrays.copyOf` instead of `clone` is not a way to "fix" sub-array sharing.

Standalone example illustrating semantics (placed inside a method):

```java
int[][] source = {{1}, {2}};
int[][] viaCopyOf = Arrays.copyOf(source, source.length);
int[][] viaArrayCopy = new int[source.length][];
System.arraycopy(source, 0, viaArrayCopy, 0, source.length);

System.out.println(source[0] == viaCopyOf[0]);    // true
System.out.println(source[0] == viaArrayCopy[0]); // true
```

The snippet above requires `import java.util.Arrays;`; both `println` statements output `true`.

One should also distinguish them from helper methods for viewing or comparing contents:

- `Arrays.toString(int[])` displays one dimension, e.g. `[1, 2]`.
- `Arrays.deepToString(Object[])` is useful for displaying multi-dimensional arrays, e.g. `[[1, 2], [3, 4]]`.
- `Arrays.deepEquals(Object[], Object[])` recursively compares **contents of nested arrays**; it **does not tell** whether two arrays share sub-arrays.
- `Arrays.equals(Object[], Object[])` on `int[][]` compares row elements via `equals`; because standard `int[]` arrays do not define content-based equality, two rows with different references will not be equal under this comparison even if containing the same numbers. Use `Arrays.deepEquals` when comparing multi-dimensional array structures by element values.

## 8. Checking aliasing properly

When verifying whether a copy is truly independent, check **references** and perform a controlled mutation, rather than only checking printed contents:

```java
int[][] a = {{1, 2}};
int[][] b = a.clone();

System.out.println(a == b);       // false: different outer arrays
System.out.println(a[0] == b[0]); // true: same sub-array
```

This is an illustrative snippet running inside a Java method.

If later you only replace `b[0]` with another `int[]`, `a[0]` does not automatically change. But when modifying `b[0][0]`, you mutate the row object already being shared.

**Caution when multiple threads access concurrently:** because shallow cloning can share mutable elements, two arrays with different references do not mean two threads are isolated. Creating a clone also does not provide synchronization or an atomic snapshot when another thread is mutating data concurrently.

## 9. When is shallow copy enough and when is deep copy needed?

**Shallow copy is enough** in cases such as:

- One-dimensional arrays containing primitive values.
- Arrays containing immutable objects such as `String`, when the application only needs to separate **reference slots** and does not need to duplicate immutable objects.
- The application intentionally shares elements to avoid memory copying, with an explicit contract on mutation rights.

**Copying additional levels is needed** when:

- You want to modify a cell in a sub-array **without changing the original array**.
- You want to pass data to another component without allowing that component to modify the original rows.
- You want to create an independent snapshot of a mutable nested structure, with a clear definition of independence and which reference relationships must be preserved.

For arrays of mutable objects, cloning the array is only **the first step**. You must know how to copy the objects themselves; not every object has `clone()`, and calling clone recursively does not automatically handle reference cycles or sharing relationships.

When designing new APIs, factories, copy constructors, or `copy()` methods that clearly describe shallow/deep semantics are usually easier to understand than assuming `clone()` will "copy everything".

## 10. Common mistakes and how to avoid them

| Misconception | Consequence | How to handle |
| --- | --- | --- |
| "Calling `clone()` duplicates every sub-array." | Modifying `copy[0][0]` changes original data | For `int[][]`, clone the outer array then clone each row |
| "Two different outer arrays share no data." | Both arrays can still share the same rows or element objects | Check `original[i] == copy[i]` |
| "`Arrays.copyOf` is a deep copy." | Still shares row references | Determine required copy depth, copy level by level |
| "`Arrays.deepEquals` proves deep copy." | Two structures can match in contents while aliasing the same sub-arrays | Check identity and test independent mutation |
| "`int[][]` is always rectangular." | Prone to `NullPointerException` or index errors | Support `null`/varying-length rows per real data |
| "Cloning `Person[][]` two levels deep clones `Person` too." | `Person` objects remain shared by reference | Copy element objects with a separate policy |
| "Having `Cloneable` allows calling `clone()` publicly." | For ordinary classes, `Object.clone()` is `protected` | Use the copy API exposed by the class; arrays are a special case |
| "Cloning each row preserves all object relationships." | Rows that originally aliased each other may no longer alias | When preserving aliases/cycles is needed, use an appropriate graph-copy algorithm |

## 11. Practice checklist

1. **Determine the required copy level:** outer array only, all sub-arrays, or element objects too?
2. **Look at the element type at each level:** `int` is a primitive value; `int[]` and `Person` are objects pointed to by references.
3. **For multi-dimensional arrays, remember `clone()` only copies the first array.**
4. **Check `null` and ragged arrays:** do not assume all rows have the same length or are non-`null`.
5. **Test both content mutation and reference reassignment:** `copy[i][j] = value` differs from `copy[i] = newRow`.
6. **Distinguish `==` and `Arrays.deepEquals`:** the former checks same object; the latter checks nested values.
7. **Keep the ownership contract clear:** is the receiver allowed to mutate shared sub-arrays/objects?
8. **If a graph copy is needed**, design how to handle shared references, cycles, and mutable state before coding.

**Self-check:**

- `int[] a = {1}; int[] b = a.clone(); b[0] = 2;` — what is `a[0]`? **1**, because they are two separate primitive arrays.
- `int[][] a = {{1}}; int[][] b = a.clone(); b[0][0] = 2;` — what is `a[0][0]`? **2**, because both outer arrays hold references to the same sub-array.
- Does `b[0] = new int[] {9};` after cloning the outer array make `a[0]` point to the new array? **No**, because it only replaces a slot of outer array `b`.
- If `Arrays.deepEquals(a, b)` returns `true`, are `a` and `b` guaranteed to be independent? **No**, the comparison only checks contents.
- For `int[][]`, what is needed to modify a copy's row without modifying the original row? **Copy the outer array and each non-null `int[]` row**.

**Remember:** Java arrays have a convenient `clone()`, yet **array cloning only copies one level**. An `int[][]` is an array holding references to `int[]` arrays, so cloning the outer array still shares the rows. At whichever level an independent copy is desired, copy explicitly at that level.