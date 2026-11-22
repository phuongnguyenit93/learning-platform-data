# Initializing Individual Subarrays and Uncreated Rows in Java

> **Java core — language-basics / Multidimensional arrays**  
> **Environment:** JDK 17+, no preview features or external libraries required.  
> **Goal:** Distinguish creating **the outer array** from creating **each row**, handle rows that are still `null`, allocate rows of different lengths, and safely iterate over an uneven two-dimensional array.

## 1. A Two-Dimensional Array Is an Array Containing References to Subarrays

In Java, `int[][]` is not a mandatory rectangular block. It is **an outer array with component type `int[]`**: each element in the outer array stores a reference to an `int[]` array, or `null`.

~~~java
int[][] rows = new int[3][];
System.out.println(rows.length); // 3: the outer array has three slots.
System.out.println(java.util.Arrays.deepToString(rows));
// [null, null, null]
~~~

`new int[3][]` creates only **the outer array** with three slots. Because its component type is `int[]` (a reference type), all three slots default to `null`: **no rows have been created yet**.

This differs from `new int[3][2]`: when the second dimension's size is provided, Java immediately creates three `int[2]` subarrays and initializes each row's numeric elements to 0.

| Array creation expression | Outer array | Row state immediately after creation |
| --- | --- | --- |
| `new int[3][]` | 3 slots | `null`, `null`, `null` |
| `new int[3][2]` | 3 slots | Each row is an `int[2]` containing `[0, 0]` |
| `new int[0][]` | 0 slots | No rows to access |
| `new int[][] {{1, 2}, null, {}}` | 3 slots | Row of length 2, null row, empty row |

Because rows are separate arrays, Java allows **rows of different lengths** (*ragged/jagged array*).

## 2. Allocating Individual Subarrays After Creating the Outer Array

~~~java
int[][] data = new int[4][];

data[0] = new int[2];           // [0, 0]
data[1] = new int[] {3, 4, 5};  // [3, 4, 5]
data[2] = new int[0];           // []
data[3] = new int[1];           // [0]

System.out.println(java.util.Arrays.deepToString(data));
// [[0, 0], [3, 4, 5], [], [0]]
~~~

Above, `data[0]` and `data[3]` are newly allocated with `new int[n]`, so they hold the default value 0. `data[1]` uses an explicit element list. `data[2]` is **a valid empty array object**, not `null`.

You can assign rows using the shorthand `{...}` syntax **when directly initializing an array variable**, but you **cannot** write `data[1] = {3,4,5};`: that is an assignment to a slot of an existing array, so it requires `new int[] {3,4,5}`.

The number of rows in the outer array is fixed at creation time (`data.length == 4`), though you can **reassign row references** in each slot, or use a new outer array if a different row count is needed.

## 3. A `null` Row Differs from an Empty Row `new int[0]`

~~~java
int[][] sample = new int[2][];
sample[1] = new int[0];

System.out.println(sample[0] == null); // true: row not created yet.
System.out.println(sample[1] == null); // false: empty row exists.
System.out.println(sample[1].length);  // 0.
~~~

| Expression | Uncreated row `sample[0]` | Empty row `sample[1]` |
| --- | --- | --- |
| Check `row == null` | true | false |
| `row.length` | `NullPointerException` | 0 |
| `row[0]` | `NullPointerException` | `ArrayIndexOutOfBoundsException` |
| Iterate `for (int x : row)` | `NullPointerException` | 0 iterations |
| `Arrays.toString(row)` | `"null"` | `"[]"` |

`sample.length` is still 2 because the outer array has two slots; **it does not reflect how many rows have been allocated**. The outer array index must be valid before checking the row's state: `sample[2]` is still out of bounds.

If you need to distinguish "row data not yet loaded" from "loaded with zero elements", preserve the `null`/empty distinction. If business rules forbid null rows, **initialize all rows** or validate explicitly at the input boundary.

## 4. Allocating in a Loop and Uneven Arrays

Rows can be created according to a rule:

~~~java
int[][] triangle = new int[4][];

for (int row = 0; row < triangle.length; row++) {
    triangle[row] = new int[row + 1];
    for (int col = 0; col < triangle[row].length; col++) {
        triangle[row][col] = row + col;
    }
}
// [[0], [1, 2], [2, 3, 4], [3, 4, 5, 6]]
~~~

Each assignment `triangle[row] = new int[row + 1]` creates **a separate subarray**. The inner loop uses `triangle[row].length` instead of taking the length of a fixed row: in an uneven array, the valid column count can vary by row.

A standard two-dimensional array can still be created concisely:

~~~java
int[][] rectangular = new int[2][3];
// [[0, 0, 0], [0, 0, 0]]
~~~

For higher-dimensional array types, Java can also allocate only a number of leading dimensions; unallocated dimensions at deeper levels contain null. Specifying a size after a dimension that has already been omitted is invalid: `new int[][3]` **does not compile**.

## 5. Safe Iteration When Uncreated Rows Exist

A simple nested `for-each` loop can throw an NPE if it encounters a null row:

~~~java
// Unsafe if data has a null row:
// for (int[] row : data) {
//     for (int number : row) {
//         System.out.println(number);
//     }
// }
~~~

Check before iterating over the subarray:

~~~java
static long sumNonNullRows(int[][] values) {
    if (values == null) {
        return 0; // Only when the contract allows treating a null outer array as empty.
    }

    long sum = 0;
    for (int[] row : values) {
        if (row == null) {
            continue; // Uncreated row.
        }
        for (int number : row) {
            sum += number;
        }
    }
    return sum;
}
~~~

If you need to **count elements**, increment the counter only when actually visiting an `int` value; do not use `values.length` as the element count. For an uneven array, the element count is **the sum of `row.length` across all non-null rows**, not "number of rows × number of columns".

Another policy is to throw `IllegalArgumentException` when encountering a null row, to ensure the data is complete. Choose and clearly document **one contract**; do not silently skip missing rows if the problem treats them as errors.

## 6. Distinguishing Modifying a Cell from Reassigning a Row Reference

After a row has been allocated, `data[0][1] = 9` updates an element of the existing row; `data[0] = new int[]{9}` replaces the entire reference in the outer array. If another variable is still holding the old row, that variable continues to see the old object. Similarly, `data.clone()` only copies **the outer array**, so both copies can still share the rows. The lesson **Shallow Copying and Sharing Subarrays** explores ways to create independent copies in depth; the demo section below also provides a per-row copy method with a `null` check for readers to run and experiment with.

## 7. Standalone Java 17+ Program

Create the file **PartialRowsDemo.java**:

~~~java
import java.util.Arrays;

public final class PartialRowsDemo {
    private static long sumNonNullRows(int[][] values) {
        if (values == null) {
            return 0;
        }
        long sum = 0;
        for (int[] row : values) {
            if (row == null) {
                continue;
            }
            for (int number : row) {
                sum += number;
            }
        }
        return sum;
    }

    private static int countElements(int[][] values) {
        if (values == null) {
            return 0;
        }
        int count = 0;
        for (int[] row : values) {
            if (row != null) {
                count += row.length;
            }
        }
        return count;
    }

    private static int[][] deepCopy(int[][] source) {
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
        int[][] data = new int[4][];
        System.out.println("outerLength=" + data.length);
        System.out.println("initial=" + Arrays.deepToString(data));
        System.out.println("row1Null=" + (data[1] == null));

        data[0] = new int[2];
        data[1] = new int[] {3, 4, 5};
        data[2] = new int[0];
        data[3] = new int[1];
        System.out.println("allocated=" + Arrays.deepToString(data));
        System.out.println("row0Length=" + data[0].length);
        System.out.println("emptyRowLength=" + data[2].length);
        System.out.println("emptyRowIsNull=" + (data[2] == null));

        data[0][1] = 9;
        data[3][0] = 7;
        System.out.println("edited=" + Arrays.deepToString(data));

        int[] savedRow = data[1];
        data[1][0] = 8;
        System.out.println("savedAfterMutation=" + Arrays.toString(savedRow));

        data[1] = new int[] {6};
        System.out.println("afterReplace=" + Arrays.deepToString(data));
        System.out.println("oldSavedRow=" + Arrays.toString(savedRow));
        System.out.println("sum=" + sumNonNullRows(data));
        System.out.println("elementCount=" + countElements(data));

        int[][] copy = deepCopy(data);
        copy[0][0] = 99;
        System.out.println("afterCopySource=" + Arrays.deepToString(data));
        System.out.println("afterCopyNew=" + Arrays.deepToString(copy));

        int[][] rectangular = new int[2][3];
        System.out.println("rectangular=" + Arrays.deepToString(rectangular));

        int[][] incomplete = new int[1][];
        try {
            System.out.println(incomplete[0].length);
        } catch (NullPointerException ex) {
            System.out.println("uncreatedRow=NullPointerException");
        }
        try {
            System.out.println(data[2][0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("emptyRow=ArrayIndexOutOfBoundsException");
        }
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 PartialRowsDemo.java
java PartialRowsDemo
~~~

**Exact expected stdout:**

~~~text
outerLength=4
initial=[null, null, null, null]
row1Null=true
allocated=[[0, 0], [3, 4, 5], [], [0]]
row0Length=2
emptyRowLength=0
emptyRowIsNull=false
edited=[[0, 9], [3, 4, 5], [], [7]]
savedAfterMutation=[8, 4, 5]
afterReplace=[[0, 9], [6], [], [7]]
oldSavedRow=[8, 4, 5]
sum=22
elementCount=4
afterCopySource=[[0, 9], [6], [], [7]]
afterCopyNew=[[99, 9], [6], [], [7]]
rectangular=[[0, 0, 0], [0, 0, 0]]
uncreatedRow=NullPointerException
emptyRow=ArrayIndexOutOfBoundsException
~~~

`initial` shows creating only the outer array; `allocated` shows per-row allocation and uneven lengths. `uncreatedRow` differs from `emptyRow`: one is null, while the other is an object of length 0. `afterCopySource` and `afterCopyNew` show that copying each row produces independent numeric data.

## 8. Common Mistakes and Exercises

| Mistake / misconception | How to handle it |
| --- | --- |
| `new int[3][]` pre-creates three `int[]` rows | Wrong: initially all three row references are null |
| `matrix[i].length` when `matrix[i] == null` | Guard or initialize the row first; otherwise NPE |
| Assuming `new int[0]` is null | Wrong: it is an empty array object |
| Using one row's length for all rows | Use `matrix[i].length`, because each row can have a different length |
| `matrix[i] = {1, 2};` after creating the outer array | Use `matrix[i] = new int[]{1, 2};` |
| `new int[][2]` | Wrong: you cannot omit an earlier dimension's size and then declare a later dimension's size |
| `matrix.clone()` automatically copies each row | Only copies the outer array; clone each row to make them independent |
| Iterating over all rows without checking for null | May throw NPE; handle according to the data contract |

**Exercise 1.** Create `int[][] rows = new int[3][];`, print `Arrays.deepToString(rows)`, and then allocate rows of lengths 2, 0, and 4 respectively.

**Exercise 2.** Distinguish the output when accessing `rows[1].length` before the row is allocated versus after assigning `rows[1] = new int[0]`.

**Exercise 3.** Use two `for` loops to create a four-row triangular array where row `i` has length `i + 1` and element `[i][j] = i + j`.

**Exercise 4.** Write a method to count the actual number of elements in an uneven array that may contain null rows; test it with `{{1, 2}, null, {}, {3}}`.

**Exercise 5.** Compare `Arrays.copyOf(matrix, matrix.length)` with copying each row via `matrix[i].clone()`. When modifying a numeric cell in the copy, does the original change?

### Key Takeaway

**`new int[rows][]` creates only the outer array; rows are initially `null` until subarrays are assigned.** Each row can have its own length, including 0. **A null row is not an empty row**: you must allocate or guard before using `length`, indexing, or iterating. Copying the outer array does not automatically copy the rows; to get independent data, copy each subarray.