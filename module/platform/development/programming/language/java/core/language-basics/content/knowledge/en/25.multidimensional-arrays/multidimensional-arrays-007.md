# `Arrays.deepToString()` and `Arrays.deepEquals()` in Java

> **Java core — language-basics / Multidimensional arrays**  
> **Environment:** JDK 17+, single-file program, no external libraries required.  
> **Goal:** Display and compare **nested contents** of multidimensional arrays; distinguish ordinary `toString`/`equals` from the two `deep...` methods, understand `null` rows, uneven arrays, and the limitations of deep comparison.

## 1. Why Do Multidimensional Arrays Need `deep...` Methods?

In Java, a two-dimensional array is actually **an array containing references to subarrays**:

~~~java
int[][] grid = {{1, 2}, {3}};
System.out.println(java.util.Arrays.deepToString(grid));
// [[1, 2], [3]]
~~~

If you call `Arrays.toString(grid)`, Java treats each **element of the outer array** as an `int[]` object. Each subarray element is typically formatted as a string like `[I@...` containing an identity hash code, **not** a list of numbers. That identity string depends on the runtime and should not be used as expected output.

`Arrays.deepToString(grid)` traverses the array levels and prints the inner contents. Similarly, `Arrays.deepEquals(a, b)` compares subarray contents rather than only comparing the references of each row.

| Need | One-dimensional array | Multidimensional / nested array |
| --- | --- | --- |
| Print elements | `Arrays.toString(array)` | `Arrays.deepToString(outer)` |
| Compare elements | `Arrays.equals(a, b)` | `Arrays.deepEquals(a, b)` |
| Same array object? | `a == b` | `a == b` only compares outer references |
| Create a copy? | `Arrays.copyOf` / `clone` | Must also copy each row to make them independent |

**Important note on types:** `deepToString` and `deepEquals` accept a parameter of type `Object[]`. `int[][]` works because its elements are `int[]` (references); **`int[]` is not an `Object[]`**. To print/compare an `int[]` directly, use `Arrays.toString(int[])` and `Arrays.equals(int[], int[])`.

## 2. `Arrays.deepToString()`: Viewing Contents Across Multiple Levels

~~~java
import java.util.Arrays;

int[][] matrix = {{1, 2}, {3, 4}};
System.out.println(Arrays.deepToString(matrix));
// [[1, 2], [3, 4]]
~~~

`deepToString` automatically recognizes when an element is an array and continues formatting the inner elements. It also handles **ragged arrays** (*ragged array*) — rows do not have to be the same length:

~~~java
int[][] jagged = {{1, 2}, null, {}, {7}};
System.out.println(Arrays.deepToString(jagged));
// [[1, 2], null, [], [7]]
~~~

Here `null` represents **a row without an array object yet**, whereas `[]` represents **a row that has been created with length 0**. These two states are different and are displayed differently.

With arrays nested to more levels, `deepToString` continues descending into those levels. If a leaf element is an ordinary object (not an array), its representation depends on `String.valueOf(element)`/`toString()` of that object; not every class has a `toString()` that represents its domain values.

## 3. `Arrays.deepEquals()`: Comparing Each Row by Contents

Two arrays have identical values, yet their rows were created **independently**:

~~~java
int[][] first = {{1, 2}, {3}};
int[][] second = {{1, 2}, {3}};

System.out.println(first == second);                   // false
System.out.println(Arrays.equals(first, second));      // false
System.out.println(Arrays.deepEquals(first, second));  // true
~~~

Why?

1. `first == second` is false: the two **outer arrays** are different objects.
2. `Arrays.equals(first, second)` compares the outer array elements. Each element is an `int[]`, and subarrays do not override `equals` to compare by value: the row references differ, so it returns false.
3. `Arrays.deepEquals(first, second)` descends into each row and compares each numeric value; having the same sizes, order, and contents yields true.

If a row contains different elements, the number of rows differs, or a row's length differs, `deepEquals` returns false. The comparison **is order-sensitive**: `{{1,2},{3}}` is not equal to `{{2,1},{3}}` under `deepEquals`.

Two outer references pointing to the same array will also compare equal, though that is not the main purpose of deep comparison: it is most useful when two structures are **separate objects**.

## 4. Uneven Nested Arrays, `null` Rows, and Empty Arrays

~~~java
int[][] a = {{1, 2}, null, {}, {7}};
int[][] b = {{1, 2}, null, {}, {7}};
int[][] c = {{1, 2}, {}, null, {7}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepEquals(a, c)); // false
~~~

`a` and `b` have the same structure, the same `null`/empty rows, and the same elements. `c` swapped those two states, so it is not equal to `a`.

| Structure | `Arrays.deepToString(...)` |
| --- | --- |
| `new int[][] {{1}, {2, 3}}` | `"[[1], [2, 3]]"` |
| `new int[2][]` | `"[null, null]"` |
| `new int[][] {{}, {}}` | `"[[], []]"` |
| `new int[0][]` | `"[]"` |

`deepToString((Object[]) null)` returns the string `"null"`. `deepEquals((Object[]) null, (Object[]) null)` returns true, while comparing a null outer array with an empty outer array returns false. You must distinguish a **null outer array**, an **outer array with null rows**, and an **empty outer array**.

Primitive array types such as `int[]` and `long[]` inside `Object[]` are still compared by contents; there is no need to box each number into `Integer`.

## 5. Mixed Arrays and `equals` of Object Elements

You can place multiple kinds of subarrays alongside ordinary objects in one `Object[]`:

~~~java
Object[] values = {
    "Java",
    new int[] {4, 5},
    new String[] {"A", "B"},
    null
};
System.out.println(Arrays.deepToString(values));
// [Java, [4, 5], [A, B], null]
~~~

`deepEquals` compares recursively if both corresponding elements are arrays. If they are **non-array objects**, it relies on the `equals` contract of those objects:

~~~java
Object[] textA = {new String("OK")};
Object[] textB = {"OK"};
System.out.println(Arrays.deepEquals(textA, textB)); // true

Object[] builderA = {new StringBuilder("OK")};
Object[] builderB = {new StringBuilder("OK")};
System.out.println(Arrays.deepEquals(builderA, builderB)); // false
~~~

`String` overrides `equals` by contents; `StringBuilder` does not override `equals` by contents, so two separate builders with the same text are still not equal. **Deep** in `deepEquals` means **recursing into elements that are actually arrays**, not automatically comparing every field inside arbitrary objects.

Two subarrays of different types (`int[]` and `long[]`) do not become equal merely because they hold the same numeric values; the comparison rules still require matching array types.

## 6. Deep Comparison Is NOT Deep Copying

`Arrays.deepEquals` returns a `boolean` result and **does not copy any objects**. `Arrays.deepToString` produces a display string and also **does not copy data**.

Meanwhile, copying an outer array via `clone()`/`Arrays.copyOf` is still a **shallow copy**: the subarrays continue to be shared.

~~~java
int[][] source = {{1, 2}, {3}};
int[][] shallow = source.clone();

shallow[0][0] = 9;
// source[0][0] == 9 because both outer arrays still point to the same row 0.
~~~

To independently copy all `int` values, you must create a new row for each existing row:

~~~java
static int[][] copyRows(int[][] source) {
    if (source == null) return null;
    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = source[i] == null ? null : source[i].clone();
    }
    return copy;
}
~~~

This approach preserves null rows while creating a **new row object** for every non-null row. For arrays containing mutable objects, even when cloning each row, the element objects may still be shared and require a copying strategy according to the business contract.

## 7. Performance Notes, Self-Referential Arrays, and Versions

- Both methods traverse the elements that need to be displayed/compared; cost grows with the total number of nested elements. `deepEquals` can stop early at the first difference, but the worst case when everything matches still takes time proportional to the number of elements.
- For nested arrays containing **reference cycles** such as an `Object[]` containing itself, `deepToString` has a mechanism to mark circular references in the formatted output. Do not design business logic that depends on circular-reference formatting; avoid circular structures unless necessary.
- `Arrays.deepEquals` **should not be used to compare cyclically self-referential array structures**: the API specification does not guarantee meaningful results for an array containing itself directly or indirectly. Define custom cycle handling if the problem requires it.
- If an array contains `double[]` or `float[]` elements, `deepEquals` uses the corresponding primitive array comparison rules of `Arrays.equals`, not a plain `==` for each number. If floating-point numbers need to be compared within a tolerance threshold, implement a custom check as required.

The syntax and APIs in this lesson work on Java 17+ without the `--enable-preview` flag.

## 8. Standalone Java 17+ Program

Create the file **DeepArraysDemo.java**:

~~~java
import java.util.Arrays;

public final class DeepArraysDemo {
    private static int[][] copyRows(int[][] source) {
        if (source == null) {
            return null;
        }
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null ? null : source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3}};
        int[][] second = {{1, 2}, {3}};

        System.out.println("outerSame=" + (first == second));
        System.out.println("shallowEqual=" + Arrays.equals(first, second));
        System.out.println("deepEqual=" + Arrays.deepEquals(first, second));
        System.out.println("deepText=" + Arrays.deepToString(first));
        System.out.println("flatText=" + Arrays.toString(first[0]));
        System.out.println("flatEqual=" + Arrays.equals(first[0], second[0]));

        int[][] jagged = {{1, 2}, null, {}, {7}};
        int[][] jaggedTwin = {{1, 2}, null, {}, {7}};
        System.out.println("jaggedText=" + Arrays.deepToString(jagged));
        System.out.println("jaggedEqual=" + Arrays.deepEquals(jagged, jaggedTwin));

        Object[] mixed = {
            "Java", new int[] {4, 5}, new String[] {"A", "B"}, null
        };
        Object[] mixedTwin = {
            "Java", new int[] {4, 5}, new String[] {"A", "B"}, null
        };
        System.out.println("mixedText=" + Arrays.deepToString(mixed));
        System.out.println("mixedEqual=" + Arrays.deepEquals(mixed, mixedTwin));

        Object[] stringsA = {new String("OK")};
        Object[] stringsB = {"OK"};
        System.out.println("stringEqual="
                + Arrays.deepEquals(stringsA, stringsB));

        Object[] buildersA = {new StringBuilder("OK")};
        Object[] buildersB = {new StringBuilder("OK")};
        System.out.println("builderEqual="
                + Arrays.deepEquals(buildersA, buildersB));

        Object[] absent = null;
        System.out.println("nullText=" + Arrays.deepToString(absent));
        System.out.println("nullEqualNull="
                + Arrays.deepEquals(absent, (Object[]) null));
        System.out.println("nullEqualEmpty="
                + Arrays.deepEquals(absent, new Object[0]));

        int[][] shallow = first.clone();
        shallow[0][0] = 9;
        System.out.println("outerCopySame=" + (first == shallow));
        System.out.println("sharedRow=" + (first[0] == shallow[0]));
        System.out.println("sourceAfterShallow=" + Arrays.deepToString(first));
        System.out.println("deepEqualAfterChange="
                + Arrays.deepEquals(first, second));

        int[][] independent = copyRows(first);
        independent[0][1] = 77;
        System.out.println("independentRowSame="
                + (first[0] == independent[0]));
        System.out.println("sourceAfterDeepCopy=" + Arrays.deepToString(first));
        System.out.println("newDeepCopy=" + Arrays.deepToString(independent));
    }
}
~~~

Compile and run in the directory containing the file (PowerShell, Command Prompt, or Bash):

~~~bash
javac -encoding UTF-8 DeepArraysDemo.java
java DeepArraysDemo
~~~

**Exact expected stdout:**

~~~text
outerSame=false
shallowEqual=false
deepEqual=true
deepText=[[1, 2], [3]]
flatText=[1, 2]
flatEqual=true
jaggedText=[[1, 2], null, [], [7]]
jaggedEqual=true
mixedText=[Java, [4, 5], [A, B], null]
mixedEqual=true
stringEqual=true
builderEqual=false
nullText=null
nullEqualNull=true
nullEqualEmpty=false
outerCopySame=false
sharedRow=true
sourceAfterShallow=[[9, 2], [3]]
deepEqualAfterChange=false
independentRowSame=false
sourceAfterDeepCopy=[[9, 2], [3]]
newDeepCopy=[[9, 77], [3]]
~~~

`shallowEqual=false` yet `deepEqual=true` shows that two independent outer arrays can still have deeply equal contents. `sharedRow=true` proves that cloning the outer array reuses the old rows, while `independentRowSame=false` proves that `copyRows` created separate rows.

### Exercises and Checklist

**Exercise 1.** Create two `int[][]` arrays with independent rows that contain the same values; predict `==`, `Arrays.equals`, and `Arrays.deepEquals`.

**Exercise 2.** Given `{{1, 2}, null, {}}`, predict the output of `Arrays.deepToString` and explain the difference between a null row and an empty row.

**Exercise 3.** Use an `Object[]` containing an `int[]`, a `String[]`, and a `null`; compare it with `deepEquals` against a newly created structure with the same contents.

**Exercise 4.** Call `Arrays.deepEquals` on two `Object[]` arrays each containing a separate `StringBuilder("A")`. Why is the result not the same as two `String("A")` objects?

**Exercise 5.** `clone()` the outer array, modify an element in row 0, and observe the original. Then use `copyRows` to demonstrate that the copied rows are independent.

**Checklist:** Is the data truly a nested array? Are there null rows or uneven lengths? Do you need to compare **deep contents** or **same reference**? Do elements override `equals`? Are there reference cycles or a need for deep copying?

### Key Takeaway

**`Arrays.deepToString` displays nested arrays; `Arrays.deepEquals` compares the contents of subarrays.** `Arrays.toString` and `Arrays.equals` only operate on one level of the outer array. Deep comparison is **not** deep copying; copying an outer array still shares subarrays unless copies of each row are created.