# Creating Rectangular Matrices and Jagged Arrays — Java 17+

## 1. What Is a Two-Dimensional Array in Java Really?

In Java, a two-dimensional array like `int[][] matrix` is **an array containing references to `int[]` arrays**. Each element in the outer array is **a row**; each row has its own `length` field.

Therefore, Java supports both:

- **Rectangular arrays:** all rows have the same number of columns.
- **Jagged/ragged arrays:** rows can have different lengths, include empty rows, or even unassigned rows (value `null`).

These are not two separate Java data types: **both are declared as `int[][]`**. The difference lies in how they are created and the actual length of each inner `int[]`.

~~~java
int[][] rectangle = new int[2][3];
int[][] jagged = {{1}, {2, 3}, {4, 5, 6}};
~~~

- `rectangle` has **2 rows × 3 columns**; every element defaults to 0.
- `jagged` has **3 rows**, with lengths **1, 2, 3** respectively.

**Mandatory rule:** iterate using `matrix.length` for the number of rows, and `matrix[row].length` for the number of elements in **that specific row**.

## 2. Creating a Rectangular Matrix with `new int[rows][cols]`

~~~java
int[][] table = new int[2][3];
table[0][0] = 7;
table[0][2] = 9;
table[1][1] = 5;

System.out.println(java.util.Arrays.deepToString(table));
~~~

**Exact expected stdout:**

~~~text
[[7, 0, 9], [0, 5, 0]]
~~~

Java allocates an outer array of length 2 and **two separate subarrays**, each of length 3:

~~~text
table (int[][]) ───> outer array length = 2
                       [0] ──> int[] {7, 0, 9} length = 3
                       [1] ──> int[] {0, 5, 0} length = 3

Row indices: 0, 1
Column indices in each row: 0, 1, 2
~~~

| Expression | Result |
|---|---:|
| `table.length` | 2 (number of rows) |
| `table[0].length` | 3 |
| `table[1].length` | 3 |
| `table[0][2]` | 9 |
| `table[1][1]` | 5 |

`int` elements default to 0; for `boolean[][]` the default is false, while elements of object types default to null.

**Important:** A rectangular array created as above has rows of equal length **initially**, but Java does not permanently lock that shape. You can still replace `table[1]` with an array of a different length; when you do, the data becomes a jagged array.

## 3. Creating Arrays with Different Row Lengths Using `new int[rows][]`

~~~java
int[][] jagged = new int[3][];
jagged[0] = new int[]{4, 5};
jagged[1] = new int[0];
jagged[2] = new int[]{6, 7, 8};

System.out.println(java.util.Arrays.deepToString(jagged));
~~~

**Exact expected stdout:**

~~~text
[[4, 5], [], [6, 7, 8]]
~~~

This approach is split into **two stages**:

1. `new int[3][]` creates an outer array of three elements, **each initially null**.
2. Assign each row to a separate `int[]` with whatever length is needed.

~~~text
jagged (int[][]) ──> outer array length = 3
                      [0] ──> {4, 5}     length = 2
                      [1] ──> {}         length = 0
                      [2] ──> {6, 7, 8}  length = 3
~~~

**Do not confuse:**

~~~java
int[][] a = new int[3][];  // Rows a[0], a[1], a[2] are initially null.
int[][] b = new int[3][0]; // There are three real subarrays, each of length 0.
~~~

Accessing `a[0].length` before assigning the row causes Java to throw `NullPointerException`. With `b[0].length`, the result is `0`.

## 4. Direct Initialization with `{ }`

If the values are known ahead of time, you can declare:

~~~java
int[][] rectangular = {
    {1, 2, 3},
    {4, 5, 6}
};

int[][] ragged = {
    {10},
    {20, 30},
    {},
    {40, 50, 60}
};
~~~

Or create and assign using array creation syntax:

~~~java
int[][] values = new int[][]{
    {1, 2},
    {3},
    {}
};
~~~

**Note:** `int[][] x = {{1}, {2, 3}};` is valid at declaration time; however, to assign a whole new array to an already declared variable, you must use `new int[][] { ... }` instead of writing only `{{...}}`.

It can explicitly contain a null row:

~~~java
int[][] partial = {
    {1, 2},
    null,
    {}
};
~~~

The type of `rectangular`, `ragged`, and `partial` is still `int[][]`.

## 5. `length` of the Outer Array and Each Row

~~~java
int[][] matrix = {{10, 20}, {30}, {}};

System.out.println("rows=" + matrix.length);
for (int row = 0; row < matrix.length; row++) {
    System.out.println("row " + row + " length=" + matrix[row].length);
}
~~~

**Exact expected stdout:**

~~~text
rows=3
row 0 length=2
row 1 length=1
row 2 length=0
~~~

| Expression | Meaning |
|---|---|
| `matrix.length` | Number of elements in the outer array, commonly called **the number of rows** |
| `matrix[row]` | Reference to the subarray at row `row` |
| `matrix[row].length` | The **individual** length of that row (if non-null) |
| `matrix[row][col]` | Value at a cell with valid row and column indices |

**There is no** shared `matrix.columns` field, nor is `matrix[0].length` guaranteed by Java to be the column count for every row. Only when you **have established and maintained** the rectangular matrix invariant does a common column length make sense.

## 6. Preserving the Right Shape When Using Arrays

Creating a rectangular or jagged array determines how algorithms read it. Use `matrix.length` for the number of rows, `matrix[row].length` for the length of **the current row**, and check `matrix[row] != null` before using `.length` if rows are allowed to be unallocated. You must handle `new int[0][3]` (no rows), `new int[2][0]` (two empty rows), and `new int[2][]` (two initially `null` rows) according to the data contract.

Standard `for` loops and enhanced `for` loops will be analyzed for modification/reading purposes in the lesson **Iterating with Nested Indexed or Enhanced `for` Loops**. This section focuses on **creating data and maintaining shape invariants**.

## 7. Replacing a Row Can Turn a Rectangular Matrix into a Jagged Array

~~~java
int[][] matrix = new int[2][3];
matrix[1] = new int[]{7};

System.out.println(java.util.Arrays.deepToString(matrix));
System.out.println(matrix[0].length + "," + matrix[1].length);
~~~

**Exact expected stdout:**

~~~text
[[0, 0, 0], [7]]
3,1
~~~

The element `matrix[1]` is a **variable holding a subarray reference**, so it can be reassigned to a new array. The `length` field of each individual subarray remains fixed, but **replacing a row reference** can cause row lengths to differ.

If the problem strictly requires a rectangular matrix, the program must **enforce the contract** that all rows exist and have the same length; the `int[][]` declaration does not enforce that forever on its own.

## 8. Checking Whether Data Is Rectangular

A useful convention: an empty outer array is considered an empty rectangle; a null outer array or one with a null row does not qualify.

~~~java
static boolean isRectangular(int[][] data) {
    if (data == null) return false;
    if (data.length == 0) return true;
    if (data[0] == null) return false;

    int columns = data[0].length;
    for (int[] row : data) {
        if (row == null || row.length != columns) {
            return false;
        }
    }
    return true;
}
~~~

| Input | `isRectangular` |
|---|---|
| `new int[2][3]` | true |
| `new int[2][0]` | true |
| `new int[0][3]` | true by the convention in the method |
| `{{1, 2}, {3}}` | false |
| `new int[2][]` with unassigned rows | false |
| `null` | false |

This check costs `O(rows)` because it only reads the length of each row; there is no need to traverse all values. However, it only checks **the current state** — if a row is replaced afterward, the result may change.



## 9. Complete Java 17+ Program, Run via CLI

Create a file with the exact name **`RectangularJaggedArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class RectangularJaggedArrayDemo {
    private RectangularJaggedArrayDemo() {}

    static void describe(String name, int[][] matrix) {
        System.out.println(name + " rows=" + matrix.length);
        for (int row = 0; row < matrix.length; row++) {
            if (matrix[row] == null) {
                System.out.println(name + " row " + row + "=null");
            } else {
                System.out.println(name + " row " + row
                        + " length=" + matrix[row].length
                        + " values=" + Arrays.toString(matrix[row]));
            }
        }
    }

    static int sum(int[][] matrix) {
        int total = 0;
        for (int[] row : matrix) {
            if (row == null) continue;
            for (int value : row) {
                total += value;
            }
        }
        return total;
    }

    static boolean validCell(int[][] matrix, int row, int col) {
        return matrix != null
                && row >= 0 && row < matrix.length
                && matrix[row] != null
                && col >= 0 && col < matrix[row].length;
    }

    static boolean isRectangular(int[][] matrix) {
        if (matrix == null) return false;
        if (matrix.length == 0) return true;
        if (matrix[0] == null) return false;
        int columns = matrix[0].length;
        for (int[] row : matrix) {
            if (row == null || row.length != columns) {
                return false;
            }
        }
        return true;
    }

    static int[][] copyRows(int[][] source) {
        int[][] copy = new int[source.length][];
        for (int row = 0; row < source.length; row++) {
            copy[row] = source[row] == null
                    ? null
                    : Arrays.copyOf(source[row], source[row].length);
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] rectangle = new int[2][3];
        rectangle[0][0] = 1;
        rectangle[0][2] = 3;
        rectangle[1][1] = 5;
        describe("rectangle", rectangle);
        System.out.println("rectangle deep=" + Arrays.deepToString(rectangle));
        System.out.println("rectangle sum=" + sum(rectangle));
        System.out.println("rectangle shape=" + isRectangular(rectangle));

        int[][] jagged = new int[3][];
        jagged[0] = new int[]{4, 5};
        jagged[1] = new int[0];
        jagged[2] = new int[]{6, 7, 8};
        describe("jagged", jagged);
        System.out.println("jagged deep=" + Arrays.deepToString(jagged));
        System.out.println("jagged sum=" + sum(jagged));
        System.out.println("jagged shape=" + isRectangular(jagged));

        System.out.println("jagged valid 0,1=" + validCell(jagged, 0, 1));
        System.out.println("jagged valid 1,0=" + validCell(jagged, 1, 0));
        System.out.println("jagged valid 2,2=" + validCell(jagged, 2, 2));
        System.out.println("jagged valid 3,0=" + validCell(jagged, 3, 0));

        int[][] zeroRows = new int[0][3];
        int[][] zeroColumns = new int[2][0];
        System.out.println("zero rows=" + zeroRows.length);
        System.out.println("zero cols rows=" + zeroColumns.length
                + ",row0=" + zeroColumns[0].length);
        System.out.println("zero rows rectangular=" + isRectangular(zeroRows));
        System.out.println("zero cols rectangular=" + isRectangular(zeroColumns));

        int[][] partial = new int[2][];
        partial[1] = new int[]{9};
        describe("partial", partial);
        System.out.println("partial sum=" + sum(partial));
        System.out.println("partial shape=" + isRectangular(partial));

        try {
            System.out.println(jagged[1][0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty row index=OUT_OF_BOUNDS");
        }
        try {
            System.out.println(partial[0].length);
        } catch (NullPointerException ex) {
            System.out.println("null row length=NULL_POINTER");
        }

        int[][] shallow = rectangle.clone();
        shallow[0][0] = 99;
        System.out.println("shallow original=" + rectangle[0][0]);

        int[][] separate = copyRows(rectangle);
        separate[0][0] = -1;
        System.out.println("separate original=" + rectangle[0][0]
                + ",copy=" + separate[0][0]);

        jagged[0] = new int[]{1};
        System.out.println("replaced row length=" + jagged[0].length);
        System.out.println("jagged after replacement=" + Arrays.deepToString(jagged));
    }
}
~~~

**Requirements:** JDK 17 or higher; terminal in the directory containing the file. No external libraries beyond the JDK, Maven, Gradle, or preview features needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RectangularJaggedArrayDemo.java
java -cp . RectangularJaggedArrayDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RectangularJaggedArrayDemo.java
java -cp . RectangularJaggedArrayDemo
~~~

### Exact expected stdout

~~~text
rectangle rows=2
rectangle row 0 length=3 values=[1, 0, 3]
rectangle row 1 length=3 values=[0, 5, 0]
rectangle deep=[[1, 0, 3], [0, 5, 0]]
rectangle sum=9
rectangle shape=true
jagged rows=3
jagged row 0 length=2 values=[4, 5]
jagged row 1 length=0 values=[]
jagged row 2 length=3 values=[6, 7, 8]
jagged deep=[[4, 5], [], [6, 7, 8]]
jagged sum=30
jagged shape=false
jagged valid 0,1=true
jagged valid 1,0=false
jagged valid 2,2=true
jagged valid 3,0=false
zero rows=0
zero cols rows=2,row0=0
zero rows rectangular=true
zero cols rectangular=true
partial rows=2
partial row 0=null
partial row 1 length=1 values=[9]
partial sum=9
partial shape=false
empty row index=OUT_OF_BOUNDS
null row length=NULL_POINTER
shallow original=99
separate original=99,copy=-1
replaced row length=1
jagged after replacement=[[1], [], [6, 7, 8]]
~~~

**Verification:**

1. `rectangle`: two rows, three elements each; sum `1+3+5=9`; `isRectangular` is true.
2. `jagged`: three rows of lengths 2, 0, 3 respectively; sum `4+5+6+7+8=30`; not rectangular.
3. `validCell` checks the row index, non-null row, column index, and row length.
4. `new int[0][3]` creates **0 rows**; `new int[2][0]` creates **2 empty rows**.
5. `partial` has one null row and one row of length 1; the `sum` method in the example intentionally skips null rows.
6. Accessing `jagged[1][0]` causes an out-of-bounds error because row 1 is empty; `partial[0].length` causes a null-pointer error because row 0 is null.
7. `rectangle.clone()` copies the outer array but shares the rows: modifying `shallow[0][0]` changes `rectangle[0][0]` to 99.
8. `copyRows` creates separate `int[]` rows; changing the copy to -1 does not change the original array.
9. Replacing `jagged[0]` with an array of length 1 is valid because this is a **row reference** assignment.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Correct approach |
|---|---|---|
| Thinking Java has a separate rectangular matrix type | Misunderstanding the `int[][]` structure | An outer array containing subarrays |
| `new int[3][]` then accessing `a[0][0]` | `NullPointerException` because the row has not been created | Assign `a[0] = new int[...]` first |
| Using `matrix[0].length` for all rows | Out-of-bounds error or missed elements | Use `matrix[row].length` |
| Thinking `matrix.length` is the total number of cells | Incorrect size calculation | `matrix.length` is only the number of rows |
| Using `matrix[row].length` on a null row | `NullPointerException` | Check for null rows |
| Using `<= length` when iterating | `ArrayIndexOutOfBoundsException` | Use `< length` |
| Assuming `new int[0][3]` can access `[0]` | The outer array has no rows | Check `matrix.length > 0` |
| Assuming `new int[2][0]` has column cells | The rows have length 0 | Do not access `[row][0]` |
| Thinking each `length` field can be modified | An array's length field is final | Replace the entire row reference with a new array |
| Thinking `matrix.clone()` copies every row | Both structures still share subarrays | `Arrays.copyOf` each row |
| Assuming no null rows exist just because the type is `int[][]` | Crash at `.length` | Establish a data contract and check |
| Assuming rows stay the same size forever | Replacing a row breaks rectangular shape | Verify/maintain the size invariant |

## 11. Exercises with Solutions

### A — Distinguishing Rectangular and Jagged Arrays

~~~java
int[][] a = new int[2][3];
int[][] b = {{1}, {2, 3}};
~~~

**Answer:** `a` is initially a 2×3 rectangular matrix; `b` is a jagged array with two rows of lengths 1 and 2. Both have type `int[][]`.

### B — Outer Array Created, but Row Not Created

~~~java
int[][] a = new int[2][];
// System.out.println(a[0].length);
~~~

**Answer:** `a.length == 2`, but `a[0] == null`. If the line accessing `.length` is uncommented, the program throws `NullPointerException`. Fix:

~~~java
a[0] = new int[3];
System.out.println(a[0].length);
~~~

**Exact stdout:**

~~~text
3
~~~

### C — Sum of Rows of Differing Lengths

~~~java
int[][] a = {{1, 2}, {}, {3, 4}};
int total = 0;
for (int[] row : a) {
    for (int value : row) {
        total += value;
    }
}
System.out.println(total);
~~~

**Answer:** prints `10`. The empty row has 0 iterations.

### D — Index Access

~~~java
int[][] a = {{5}, {6, 7}};
System.out.println(a[1][1]);
// System.out.println(a[0][1]);
~~~

**Answer:** prints `7`; `a[0][1]` is out of bounds because the first row only has length 1.

### E — Copying a Two-Dimensional Array

~~~java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 9;
System.out.println(a[0][0]);
~~~

**Answer:** prints `9`, because `clone()` only copies the outer array, while `a[0]` and `b[0]` still reference the same subarray.

### F — Replacing a Row Changes the Shape

~~~java
int[][] a = new int[2][2];
a[1] = new int[4];
System.out.println(a[0].length + "," + a[1].length);
~~~

**Answer:** prints `2,4`. Java allows replacing a row with an array of a different length.

## 12. Checklist and Conclusion

- [ ] Know that `int[][]` is an array containing `int[]` arrays.
- [ ] Create rectangular matrices with `new int[rows][cols]`.
- [ ] Create jagged arrays with `new int[rows][]` and then create each row.
- [ ] Distinguish a `null` row from an empty row `new int[0]`.
- [ ] Read the number of rows with `matrix.length` and each row's actual column count with `matrix[row].length`.
- [ ] Iterate properly over rows of varying lengths without assuming a shared column count.
- [ ] Check both row/column bounds and null status before accessing elements.
- [ ] Understand that `new int[0][3]` and `new int[2][0]` are different structures.
- [ ] Know that replacing a row reference can make data non-rectangular.
- [ ] Distinguish single-level copying `clone()` from per-row copying `Arrays.copyOf`.
- [ ] Know how to verify rectangular shape when a problem requires rows of equal length.
- [ ] Compile and run `RectangularJaggedArrayDemo.java` on Java 17+ and verify stdout.

**Conclusion:** In Java 17+, `int[][]` **is not required to be a rectangular block**; each row is a separate array with its own length and reference. `new int[r][c]` creates rows that initially have the same length, whereas `new int[r][]` allows allocating rows of different sizes. To iterate correctly and safely, always rely on **`matrix.length` for the number of rows and `matrix[row].length` for the length of the current row**, while handling empty/null rows according to the data contract.