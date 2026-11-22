# Multidimensional Arrays Are Arrays of References to Subarrays in Java

> **Java core — language-basics / Multidimensional arrays**  
> **Requirements:** JDK 17+; standalone Java examples, no external libraries required.  
> **Goal:** Correctly understand the `int[][]` structure as **an outer array containing references to `int[]` arrays**, distinguish uncreated subarrays (`null`) from created subarrays, explain rows of differing lengths, reference sharing, and working with two index levels.

## 1. The "Array of Arrays" Model Instead of a Contiguous Grid

In Java, `int[][]` is read as "an array whose elements have type `int[]`". Each element of the **outer array** is **a reference** to an `int[]` array or the value `null`. Only the elements **inside the `int[]` arrays** hold primitive `int` values.

~~~text
int[][] grid = new int[2][3];

grid (reference to outer array int[][])
       │
       ▼
  +----------+       +-------------+
  | [0]  ----|------>| int[3]      |  [0, 0, 0]
  | [1]  ----|---+   +-------------+
  +----------+   |   +-------------+
                 +-->| int[3]      |  [0, 0, 0]
                     +-------------+
~~~

At the Java semantic level, `new int[2][3]` creates **an outer array with two reference elements**, and each of those elements points to **a separate `int[3]` subarray**. Therefore:

~~~java
int[][] grid = new int[2][3];
System.out.println(grid.length);       // 2: number of elements in the outer array.
System.out.println(grid[0].length);    // 3: number of elements in row 0.
System.out.println(grid[1].length);    // 3: number of elements in row 1.
System.out.println(grid[0] == grid[1]); // false: two different subarrays.
~~~

The phrasing "2 rows × 3 columns" is useful for visualization, but **you should not infer that Java guarantees storing the entire matrix as a single contiguous region of `int` values**. The two rows are two independent array objects referenced from the outer array.

## 2. Initializing Both Levels or Only the Outer Array

The important difference lies in **which levels have been created with `new`**:

| Syntax | Outer array | Initial subarrays |
| --- | --- | --- |
| `new int[2][3]` | Yes, length 2 | Two distinct `int[3]` arrays containing `0` |
| `new int[2][]` | Yes, length 2 | Both references are `null` |
| `new int[2][0]` | Yes, length 2 | Two valid `int[0]` arrays, non-`null` |
| `new int[0][3]` | Yes, length 0 | No outer array elements, so no rows to access |
| `new String[2][3]` | Yes, length 2 | Two `String[3]` arrays, each string element is `null` |

In `new int[2][]`, the elements of the outer array have **the reference type `int[]`**, so they receive the default value `null`, even though the element type at the deeper level is `int`.

~~~java
int[][] partial = new int[2][];
System.out.println(partial.length);       // 2
System.out.println(partial[0] == null);   // true
System.out.println(partial[1] == null);   // true

partial[0] = new int[3]; // Create row 0, containing [0, 0, 0].
partial[1] = new int[0]; // Create row 1, length 0.
System.out.println(partial[0].length); // 3
System.out.println(partial[1].length); // 0
~~~

Going from `partial[1] == null` before assignment to `partial[1].length == 0` after assignment represents **two completely different states**: a row without an object yet and a row with an empty array object.

With multi-dimensional `new` syntax, you cannot specify a deeper dimension when a preceding dimension is left empty; for example, `new int[][3]` is invalid. You may omit trailing dimensions, such as `new int[2][]` or `new int[2][3][]`.

## 3. Two Index Levels and Checking for `null` Rows

The expression `matrix[row][column]` is semantically equivalent to **obtaining the subarray reference** `matrix[row]` and then indexing `[column]` on that subarray:

~~~java
int[][] matrix = {{10, 20}, {30, 40}};
int[] firstRow = matrix[0];

System.out.println(firstRow[1]); // 20
System.out.println(matrix[0][1]); // 20
~~~

To read `matrix[r][c]` successfully, you need:

1. The variable `matrix` to reference an actual outer array (not `null`).
2. `r` to be between `0` and `matrix.length - 1`.
3. `matrix[r]` not to be `null`.
4. `c` to be between `0` and `matrix[r].length - 1`.

Missing any of these conditions can cause a `NullPointerException` or `ArrayIndexOutOfBoundsException`. An already created outer array does **not** guarantee that all subarrays have also been created.

Example of a safe check when you only want to read if the position exists:

~~~java
static boolean containsCell(int[][] matrix, int r, int c) {
    return matrix != null
            && r >= 0 && r < matrix.length
            && matrix[r] != null
            && c >= 0 && c < matrix[r].length;
}
~~~

The method above uses the short-circuit `&&` operator: if an earlier condition is false, subsequent conditions are not evaluated. Thus it does not accidentally access `matrix[r]` before knowing `r` is valid.

## 4. Rows Do Not Need the Same Length: "Jagged" Arrays

Each element of the outer array is a reference to an `int[]`, so rows can have **different** lengths (*jagged/ragged array*):

~~~java
int[][] rows = new int[3][];
rows[0] = new int[] {2, 4};
rows[1] = new int[0];
rows[2] = new int[] {9};

System.out.println(rows.length);    // 3
System.out.println(rows[0].length); // 2
System.out.println(rows[1].length); // 0
System.out.println(rows[2].length); // 1
~~~

You can initialize concisely with an array initializer list:

~~~java
int[][] triangle = {
    {1},
    {2, 3},
    {4, 5, 6}
};
~~~

Inside a loop, do not force the column count to be `rows[0].length` for every row. Check the length **of each individual row**:

~~~java
static int sumAll(int[][] rows) {
    int sum = 0;
    for (int[] row : rows) {
        if (row == null) {
            continue; // Skip uncreated rows according to the example contract.
        }
        for (int value : row) {
            sum += value;
        }
    }
    return sum;
}
~~~

The `sumAll` method handles both empty rows and `null` rows, provided the outer array `rows` itself is non-`null`. For `triangle` above, the result is 21. For the initial `rows` example, the sum is 15.

## 5. Two Rows Can Reference the Same Subarray

Just like object reference variables, **two elements of the outer array can hold the same reference**:

~~~java
int[] shared = {10, 20};
int[][] aliases = {shared, shared};

System.out.println(aliases[0] == aliases[1]); // true
aliases[0][0] = 99;
System.out.println(aliases[1][0]);             // 99
~~~

Updating `aliases[0][0]` mutates **the shared subarray object**, so reading through `aliases[1][0]` also sees 99.

**However, reassigning a row reference does not modify the other row:**

~~~java
aliases[0] = new int[] {1};
// aliases[0] points to the new subarray [1].
// aliases[1] still points to the old subarray [99, 20].
~~~

These are two different kinds of operations:

| Operation | What happens |
| --- | --- |
| `aliases[0][0] = 99` | Modifies **an element of the subarray** that row 0 currently references |
| `aliases[0] = new int[] {1}` | Replaces **the reference at row 0** with a reference to a new array |
| `aliases[1] = aliases[0]` | Makes two rows reference the same current subarray |

You cannot treat a row of `int[][]` as a "value copy" on every assignment. These are **references**, not a *deep copy*.

## 6. Copying the Outer Array Still Shares the Rows

Calling `matrix.clone()` creates a new outer array, but its elements are still **references to the old rows**. Therefore, modifying `copy[0][1]` can cause `matrix[0][1]` to change as well; whereas assigning `copy[0] = new int[]{8}` only changes the copy's row reference. These two operations connect directly to the model in section 5.

If you need independent `int` data, copy each non-`null` subarray into a new outer array. The lesson **Shallow Copying and Sharing Subarrays** analyzes `clone()`, `Arrays.copyOf()`, arrays with multiple aliases, and mutable object elements in full.

## 7. Standalone Java 17+ Program

Create the file **ArrayOfArraysDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayOfArraysDemo {
    private static void printRows(String label, int[][] rows) {
        System.out.println(label + "Length=" + rows.length);
        for (int r = 0; r < rows.length; r++) {
            int[] subarray = rows[r];
            String value = subarray == null
                    ? "null"
                    : Arrays.toString(subarray);
            System.out.println(label + "[" + r + "]=" + value);
        }
    }

    public static void main(String[] args) {
        int[][] rectangular = new int[2][3];
        System.out.println("rectRows=" + rectangular.length);
        System.out.println("rectColumns0=" + rectangular[0].length);
        System.out.println("rectColumns1=" + rectangular[1].length);
        System.out.println("rectDistinct="
                + (rectangular[0] != rectangular[1]));
        rectangular[0][1] = 7;
        System.out.println("rectRow0=" + Arrays.toString(rectangular[0]));
        System.out.println("rectRow1=" + Arrays.toString(rectangular[1]));

        int[][] partial = new int[3][];
        printRows("partial", partial);
        partial[0] = new int[] {2, 4};
        partial[1] = new int[0];
        partial[2] = new int[] {9};
        printRows("ragged", partial);
        System.out.println("lastLength=" + partial[2].length);

        int[] shared = {10, 20};
        int[][] aliases = {shared, shared};
        System.out.println("sharedRowsSame=" + (aliases[0] == aliases[1]));
        aliases[0][0] = 99;
        System.out.println("sameRowSeen=" + aliases[1][0]);

        int[] oldRow = aliases[0];
        aliases[0] = new int[] {1};
        System.out.println("afterReplaceRowsSame="
                + (aliases[0] == aliases[1]));
        System.out.println("oldRow=" + Arrays.toString(oldRow));
        System.out.println("newRow=" + Arrays.toString(aliases[0]));
        System.out.println("remainingRow=" + Arrays.toString(aliases[1]));

        int[][] copiedOuter = partial.clone();
        System.out.println("cloneOuterSame=" + (copiedOuter == partial));
        System.out.println("cloneRowSame="
                + (copiedOuter[0] == partial[0]));
        copiedOuter[0][1] = 55;
        System.out.println("mutatedSource=" + partial[0][1]);
        copiedOuter[0] = new int[] {8};
        System.out.println("sourceRow=" + Arrays.toString(partial[0]));
        System.out.println("copiedRow=" + Arrays.toString(copiedOuter[0]));

        int[][] noRows = new int[0][3];
        int[][] zeroWidth = new int[2][0];
        System.out.println("noRows=" + noRows.length);
        System.out.println("zeroWidthRow=" + zeroWidth[0].length);
        System.out.println("zeroWidthNonNull=" + (zeroWidth[0] != null));

        System.out.println("outerType=" + partial.getClass().getTypeName());
        System.out.println("innerType=" + partial[0].getClass().getTypeName());

        try {
            int[][] missingRow = new int[1][];
            System.out.println(missingRow[0].length);
        } catch (NullPointerException ex) {
            System.out.println("nullRowError=NullPointerException");
        }
        System.out.println("deepRagged=" + Arrays.deepToString(partial));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ArrayOfArraysDemo.java
java ArrayOfArraysDemo
~~~

**Exact expected stdout:**

~~~text
rectRows=2
rectColumns0=3
rectColumns1=3
rectDistinct=true
rectRow0=[0, 7, 0]
rectRow1=[0, 0, 0]
partialLength=3
partial[0]=null
partial[1]=null
partial[2]=null
raggedLength=3
ragged[0]=[2, 4]
ragged[1]=[]
ragged[2]=[9]
lastLength=1
sharedRowsSame=true
sameRowSeen=99
afterReplaceRowsSame=false
oldRow=[99, 20]
newRow=[1]
remainingRow=[99, 20]
cloneOuterSame=false
cloneRowSame=true
mutatedSource=55
sourceRow=[2, 55]
copiedRow=[8]
noRows=0
zeroWidthRow=0
zeroWidthNonNull=true
outerType=int[][]
innerType=int[]
nullRowError=NullPointerException
deepRagged=[[2, 55], [], [9]]
~~~

The `rectDistinct=true` output shows that each row of `new int[2][3]` is an independent subarray. `partial[r]=null` indicates an uncreated subarray. `sharedRowsSame=true` and `sameRowSeen=99` demonstrate that two rows can reference the same subarray; `cloneRowSame=true` shows that copying the outer array still shares the rows.

On the last line, `Arrays.deepToString(partial)` prints the nested structure by contents, unlike `Arrays.toString(partial)` which may display hard-to-read subarray identity strings.

## 8. Common Mistakes, Checklist, and Exercises

| Misconception or mistake | Correct understanding |
| --- | --- |
| `int[][]` is a single contiguous block of `int` cells | It is an outer array containing **references to `int[]`** |
| `new int[2][]` has already created two `int[]` arrays | Wrong: both rows are currently `null` |
| `new int[2][3]` uses one shared row object | Wrong: each row is a separate subarray |
| All rows must have the same length | Wrong: each subarray can have its own length |
| `matrix.length` is the number of columns | Wrong: it is the number of elements in the outer array (number of rows when organized by rows) |
| `matrix[r].length` can always be read | Requires `r` to be valid and `matrix[r] != null` |
| Assigning `a[1] = a[0]` copies the row's values | Wrong: it assigns a **reference**, causing both rows to share the same array |
| `a.clone()` copies all subarrays | Wrong: it only creates a new outer array; the row references are copied |
| `new int[2][0]` and `new int[2][]` are the same | Wrong: an empty row is not a `null` row |
| Using `Arrays.toString` on `int[][]` to inspect all numbers | Prefer `Arrays.deepToString` for multi-level display |

**Exercise 1.** Create `int[][] data = new int[3][];`. Check `data[0] == null`, then assign `new int[2]`, `new int[0]`, and `new int[] {5}` to the three rows respectively. Print the length of each row.

**Exercise 2.** Initialize `int[][] jagged = {{1}, {2, 3}, {4, 5, 6}};`, write two loops to compute the sum, and explain why the inner loop must rely on `jagged[row].length`.

**Exercise 3.** Create two rows that both reference `int[] shared`, update an element through the first row, and read it through the other row. Then reassign the first row to a new subarray and predict the result.

**Exercise 4.** Compare `new int[0][3]`, `new int[2][0]`, and `new int[2][]` in terms of row count, `null` status, and valid subarray lengths.

**Exercise 5.** Use `clone()` on the outer array and prove that `outerCopy[0] == original[0]`. Then write a method to copy each `int[]` so that modifying the copy does not affect the original.

### Key Takeaway

**`int[][]` is an array where each element has type `int[]`, meaning a reference to a subarray.** The `new int[rows][columns]` form creates both the outer array and the rows; `new int[rows][]` creates only the outer array, with rows initially `null`. Rows can have different lengths, share references, or be replaced with other arrays; therefore, check each row individually and understand reference copying clearly.