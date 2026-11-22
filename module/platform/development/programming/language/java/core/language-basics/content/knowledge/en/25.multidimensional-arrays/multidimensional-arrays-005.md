# Iterating with Nested Indexed or Enhanced `for` Loops — Java 17+

## 1. Understanding Two-Dimensional Arrays Before Iterating

In Java, a two-dimensional array like `int[][] matrix` is **an array of references to `int[]` arrays**. You can think of each subarray as a row:

~~~java
int[][] matrix = {
    {3, 1, 4},
    {1, 5},
    {},
    {9}
};
~~~

~~~text
Row 0: [3, 1, 4]  -> length = 3
Row 1: [1, 5]     -> length = 2
Row 2: []         -> length = 0
Row 3: [9]        -> length = 1
~~~

- `matrix.length` is the number of **rows**: here it is `4`.
- `matrix[i]` is a **one-dimensional array** `int[]`.
- `matrix[i].length` is the number of elements in **row i**, not necessarily equal to the number of elements in other rows.
- `matrix[i][j]` is the element at row `i`, column/in-row index `j`.
- Indices start at `0`; row `i` has valid element indices from `0` to `matrix[i].length - 1`.

The example above is an array **whose rows have different lengths** (*jagged/ragged array*), a completely valid Java structure. Therefore, when iterating you must check `matrix[i].length`, rather than assuming every row has length `matrix[0].length`.

## 2. Iterating with Two Indexed `for` Loops

The standard form when you need to know element positions:

~~~java
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        System.out.println("[" + i + "][" + j + "]="
                + matrix[i][j]);
    }
}
~~~

The outer loop selects **row i**. The inner loop iterates over the elements **j of that same row i**. With `matrix` from section 1, stdout is:

~~~text
[0][0]=3
[0][1]=1
[0][2]=4
[1][0]=1
[1][1]=5
[3][0]=9
~~~

Row 2 is empty, so the inner loop does not run; there is no `matrix[2][0]` element to print. The iteration order above is **row-by-row** (*row-major traversal*): finishing the current row before moving to the next row.

You can choose clearer variable names:

~~~java
for (int rowIndex = 0; rowIndex < matrix.length; rowIndex++) {
    for (int colIndex = 0;
         colIndex < matrix[rowIndex].length;
         colIndex++) {
        int value = matrix[rowIndex][colIndex];
        // Use value and both indices when needed.
    }
}
~~~

**Advantages:** you know the coordinates, you can assign `matrix[i][j] = ...`, access neighbors, or iterate over only a subrange of indices. **Disadvantages:** longer syntax and you must write boundary conditions carefully.

## 3. Iterating with Nested Enhanced `for` Loops

The enhanced `for` (or *for-each*) loop yields **element values** one by one without requiring the programmer to manage indices:

~~~java
for (int[] row : matrix) {
    for (int value : row) {
        System.out.println(value);
    }
}
~~~

**Exact stdout:**

~~~text
3
1
4
1
5
9
~~~

How to read the syntax:

- `for (int[] row : matrix)`: because `matrix` has type `int[][]`, each element `row` has type **`int[]`**.
- `for (int value : row)`: because `row` has type `int[]`, each `value` is an **`int`**.
- An empty row produces zero inner iterations.
- The order is still one row after another, then each value within the row.

Its strength is concise code with less risk of writing `i < length`/`j < length` conditions incorrectly, making it well-suited for **reading, summing, counting, and linear search** when coordinates are not needed.

Do not write `for (int value : matrix)`: the elements of `int[][]` are `int[]`, not `int`; that code will not compile.

## 4. Choosing the Iteration Style by Purpose

| Need | Recommended | Reason |
|---|---|---|
| Print, sum, or count all values | Nested enhanced `for` | Short and clear |
| Print `(row, column)` of an element | Two indexed `for` loops | Direct access to coordinates |
| Reassign primitive elements | `matrix[i][j] = ...` | Writes directly to the cell in the array |
| Replace an entire subarray at row `i` | `matrix[i] = new int[]{...}` | Requires the row index |
| Compute per-row sums and return `int[]` | Indexed outer loop + enhanced `for` inner loop | Needs the result slot index, not each value's index |
| Compare neighbors `[i][j-1]`, `[i][j+1]` | Indexed `for` with bounds checks | Requires positional access |
| Rows of different lengths | Both styles work | Always uses each individual row's length |

There is no single "best" loop style in all cases. Choose the one that expresses what needs to be done; both styles generally visit elements in the same order when traversing from start to finish.

## 5. Modifying Values: The Enhanced `for` Loop Variable Trap

Consider the array:

~~~java
int[][] data = {{1, 2}, {3}};
for (int[] row : data) {
    for (int value : row) {
        value = value * 10;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout:**

~~~text
[[1, 2], [3]]
~~~

`value` is only a **local variable** receiving a copy of each element's `int` value. Reassigning `value` does **not write back** into `row[j]`.

To modify the integers inside the array, use indices:

~~~java
for (int i = 0; i < data.length; i++) {
    for (int j = 0; j < data[i].length; j++) {
        data[i][j] *= 10;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout (continuing the example):**

~~~text
[[10, 20], [30]]
~~~

However, the `row` variable in `for (int[] row : data)` **holds a reference to the subarray currently being visited**, so **modifying elements through `row`** still affects the array:

~~~java
for (int[] row : data) {
    if (row.length > 0) {
        row[0] = 0;
    }
}
System.out.println(java.util.Arrays.deepToString(data));
~~~

**Exact stdout (continuing the example):**

~~~text
[[0, 20], [0]]
~~~

Distinguish carefully:

- `value = 99;`: only reassigns the local `int` variable.
- `row[0] = 99;`: assigns into an element of the **existing subarray**.
- `row = new int[]{99};`: only reassigns the loop's reference variable `row`; **does not change** `data[i]`.
- `data[i] = new int[]{99};`: replaces the actual subarray reference at row `i`.

## 6. Combining Both Traversal Styles: Sum, Element Count, and Per-Row Sums

Compute total sum and element count with enhanced `for`:

~~~java
int sum = 0;
int count = 0;
for (int[] row : matrix) {
    for (int value : row) {
        sum += value;
        count++;
    }
}
System.out.println(sum);
System.out.println(count);
~~~

With `matrix = {{3,1,4},{1,5},{},{9}}`, **exact stdout**:

~~~text
23
6
~~~

An empty row contributes **0 values** to both the sum and the count. The number of elements in an array with differing row lengths must be computed using `count` (or the sum of `row.length`), **not** `matrix.length * matrix[0].length`.

When you need **per-row** sums in the same order as the original rows, combine an indexed outer loop with an enhanced `for` inner loop:

~~~java
int[] rowSums = new int[matrix.length];
for (int i = 0; i < matrix.length; i++) {
    for (int value : matrix[i]) {
        rowSums[i] += value;
    }
}
System.out.println(java.util.Arrays.toString(rowSums));
~~~

**Exact stdout:**

~~~text
[8, 6, 0, 9]
~~~

Neither approach modifies `matrix` when only reading elements.

## 7. Empty Rows, `null` Rows, and a `null` Outer Array

Java can create a two-dimensional array where some subarrays have **not yet been created**:

~~~java
int[][] partial = new int[3][];
partial[0] = new int[]{2, 3};
partial[1] = null;
partial[2] = new int[0];
~~~

`partial.length == 3`, but:

| Row | Value | Can elements be iterated immediately? |
|---|---|---|
| `partial[0]` | `[2,3]` | Yes, 2 elements |
| `partial[1]` | `null` | **No**; `.length` or enhanced `for` on this row throws `NullPointerException` |
| `partial[2]` | Empty array | Yes, inner loop runs 0 iterations |

Defensive traversal when data may contain `null` rows:

~~~java
int total = 0;
if (partial != null) {
    for (int[] row : partial) {
        if (row == null) {
            continue;
        }
        for (int value : row) {
            total += value;
        }
    }
}
System.out.println(total);
~~~

**Exact stdout:**

~~~text
5
~~~

The `row == null` check must happen **before** accessing `row.length` or iterating `for (int value : row)`. If even the outer array can be null, you must also check `matrix != null` before reading `matrix.length` or looping over it.

Not every program should **skip null**: sometimes null is a data error and should throw `IllegalArgumentException`. The handling policy is determined by the problem; the important thing is **not to confuse null with an empty array**.

## 8. Printing Multidimensional Arrays and Common Mistakes

~~~java
int[][] matrix = {{1, 2}, {3}};
System.out.println(java.util.Arrays.deepToString(matrix));
~~~

**Exact stdout:**

~~~text
[[1, 2], [3]]
~~~

`Arrays.deepToString(matrix)` displays **nested subarrays**. `Arrays.toString(matrix)` operates directly only on **the outer array**, so it may print reference representations of the subarrays instead of all numeric values; do not use that output for data comparison.

Pitfalls to avoid:

| Mistake | Consequence | Fix |
|---|---|---|
| `j < matrix.length` in the inner loop | Number of rows is not necessarily the element count of row `i` | `j < matrix[i].length` |
| `j < matrix[0].length` for all rows | May go out of bounds or miss elements | Use each row's own length |
| `j <= matrix[i].length` | Hits an out-of-bounds index | Use `<`, not `<=` |
| Iterating `for (int v : matrix)` | Type mismatch: each outer element is `int[]` | `for (int[] row : matrix)` |
| Assigning `v = ...` expecting the array to change | Only changes the loop variable | Use `matrix[i][j] = ...` |
| Not checking for `null` rows when data allows them | `NullPointerException` | Check the row before the inner loop |
| Using `matrix.length * matrix[0].length` to count all elements | Wrong for differing row lengths, crashes if there are no rows | Sum `row.length` or count in the loop |
| Printing `Arrays.toString(matrix)` | Does not produce a readable nested value string | `Arrays.deepToString(matrix)` |

## 9. Complete Java 17+ Program

Create a file with the exact name **`NestedArrayIterationDemo.java`**:

~~~java
import java.util.Arrays;

public final class NestedArrayIterationDemo {
    private NestedArrayIterationDemo() {}

    static void showIndexed(int[][] matrix) {
        for (int rowIndex = 0; rowIndex < matrix.length; rowIndex++) {
            int[] row = matrix[rowIndex];
            System.out.println("row " + rowIndex
                    + " length=" + row.length);

            for (int colIndex = 0; colIndex < row.length; colIndex++) {
                System.out.println("cell[" + rowIndex + "]["
                        + colIndex + "]=" + row[colIndex]);
            }
        }
    }

    static int[] sumAndCount(int[][] matrix) {
        int sum = 0;
        int count = 0;
        for (int[] row : matrix) {
            for (int value : row) {
                sum += value;
                count++;
            }
        }
        return new int[]{sum, count};
    }

    static int[] rowSums(int[][] matrix) {
        int[] sums = new int[matrix.length];
        for (int i = 0; i < matrix.length; i++) {
            for (int value : matrix[i]) {
                sums[i] += value;
            }
        }
        return sums;
    }

    static int[][] doubledCopy(int[][] matrix) {
        int[][] result = new int[matrix.length][];
        for (int i = 0; i < matrix.length; i++) {
            result[i] = Arrays.copyOf(matrix[i], matrix[i].length);
            for (int j = 0; j < result[i].length; j++) {
                result[i][j] *= 2;
            }
        }
        return result;
    }

    static int sumSkippingNullRows(int[][] matrix) {
        if (matrix == null) return 0;
        int sum = 0;
        for (int[] row : matrix) {
            if (row == null) continue;
            for (int value : row) {
                sum += value;
            }
        }
        return sum;
    }

    public static void main(String[] args) {
        int[][] grid = {{3, 1, 4}, {1, 5}, {}, {9}};

        System.out.println("matrix=" + Arrays.deepToString(grid));
        System.out.println("rows=" + grid.length);
        showIndexed(grid);

        int[] stats = sumAndCount(grid);
        System.out.println("enhanced sum=" + stats[0]);
        System.out.println("enhanced count=" + stats[1]);
        System.out.println("row sums=" + Arrays.toString(rowSums(grid)));

        int[][] doubled = doubledCopy(grid);
        System.out.println("doubled=" + Arrays.deepToString(doubled));
        System.out.println("original=" + Arrays.deepToString(grid));

        for (int[] row : grid) {
            for (int value : row) {
                value += 100; // Does not write into the original int element.
            }
        }
        System.out.println("after local value change="
                + Arrays.deepToString(grid));

        grid[0][1] = 7; // When coordinates are needed, use indices.
        System.out.println("after indexed change="
                + Arrays.deepToString(grid));

        for (int[] row : grid) {
            if (row.length > 0) {
                row[0] *= 10; // Modify through the subarray reference.
            }
        }
        System.out.println("after row reference change="
                + Arrays.deepToString(grid));

        int[][] withNullRow = {{2, 3}, null, {}, {5}};
        System.out.println("nullable sum="
                + sumSkippingNullRows(withNullRow));
    }
}
~~~

**Requirements:** JDK 17 or newer; no external libraries or preview features needed. Run the terminal in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NestedArrayIterationDemo.java
java -cp . NestedArrayIterationDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NestedArrayIterationDemo.java
java -cp . NestedArrayIterationDemo
~~~

### Exact expected stdout

~~~text
matrix=[[3, 1, 4], [1, 5], [], [9]]
rows=4
row 0 length=3
cell[0][0]=3
cell[0][1]=1
cell[0][2]=4
row 1 length=2
cell[1][0]=1
cell[1][1]=5
row 2 length=0
row 3 length=1
cell[3][0]=9
enhanced sum=23
enhanced count=6
row sums=[8, 6, 0, 9]
doubled=[[6, 2, 8], [2, 10], [], [18]]
original=[[3, 1, 4], [1, 5], [], [9]]
after local value change=[[3, 1, 4], [1, 5], [], [9]]
after indexed change=[[3, 7, 4], [1, 5], [], [9]]
after row reference change=[[30, 7, 4], [10, 5], [], [90]]
nullable sum=10
~~~

**Output explanation:** there are 4 rows, yet only 6 elements in total; the sum is `3+1+4+1+5+9=23`. Reassigning the `value` variable using enhanced `for` does not modify the numbers inside `grid`. Writing `grid[0][1] = 7` changes one position; modifying `row[0]` through the `int[]` row variable also changes the array's data. `withNullRow` is handled by skipping the null row, so `2+3+5=10`.

## 10. Practice and Solutions

**A.** Given `int[][] a = {{2, 4}, {}, {6}}`, how many rows and elements are there?  
**Answer:** `a.length == 3`; total number of elements is `2+0+1=3`, not `3*2`.

**B.** Replace the indexed loops with enhanced `for` when you only need to print values:

~~~java
for (int i = 0; i < a.length; i++) {
    for (int j = 0; j < a[i].length; j++) {
        System.out.println(a[i][j]);
    }
}
~~~

**Answer:**

~~~java
for (int[] row : a) {
    for (int value : row) {
        System.out.println(value);
    }
}
~~~

**C.** Why does `for (int value : a)` fail when `a` has type `int[][]`?  
**Answer:** elements of `a` have type `int[]`; the outer loop must declare `int[] row`.

**D.** Given `int[][] a = {{1}, {2,3}}`, does `for(int[] row:a) for(int v:row) v=0;` zero out the array?  
**Answer:** **no**; it only reassigns the variable `v`, without modifying the array. You need `a[i][j]=0`.

**E.** When should you use `matrix[i][j]` instead of enhanced `for`?  
**Answer:** when you need **indices**, need to directly modify cells by coordinate, or need to access neighbors and restrict traversal to a range of positions.

**F.** If `matrix[1] == null`, can you write `matrix[1].length`?  
**Answer:** no; it will throw `NullPointerException` when executed. You must check `matrix[1] != null` or define a policy rejecting null.

## 11. Checklist and Conclusion

- [ ] Understand `int[][]` as an array containing `int[]` arrays.
- [ ] Know that row count is `matrix.length` and row `i`'s length is `matrix[i].length`.
- [ ] Iterate with indices using `i < matrix.length`, `j < matrix[i].length`.
- [ ] Iterate with enhanced `for` using `int[] row` outside and `int value` inside.
- [ ] Do not assume all rows have the same length or are all non-`null`.
- [ ] Distinguish reassigning an enhanced `for` variable from modifying elements via indices or a row reference.
- [ ] Know how to combine an outer indexed loop with an inner enhanced `for` loop when computing per-row sums.
- [ ] Use `Arrays.deepToString` to print nested array contents.
- [ ] Run `NestedArrayIterationDemo.java` on JDK 17+ and compare stdout.

**Conclusion:** Two indexed `for` loops are suitable when you need **coordinates or element modification**, while nested enhanced `for` loops are suitable when you only need **to read values**. Both must respect the length of **each individual row** in Java multidimensional arrays; check for `null` when subarrays might not have been created.