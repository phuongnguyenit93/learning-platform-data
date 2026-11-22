# Shallow Copying and Sharing Subarrays — Java 17+

## 1. Fundamental Nature

In Java, `int[][]` is **an outer array containing references to `int[]` subarrays**. Therefore, **copying the outer array does not mean copying the rows**.

~~~java
int[][] a = {{1, 2}, {3, 4, 5}};
~~~

Here `a.length == 2`, `a[0].length == 2`, `a[1].length == 3`. Each row is a separate array object. A **row reference** can be stored in multiple slots, even across multiple different outer arrays.

~~~text
a (outer array) ---> [reference 0 | reference 1]
                           |              |
                           v              v
                       [1, 2]        [3, 4, 5]
                        int[]           int[]
~~~

**Shallow copy:** only creates a copy of **one array level**, while the reference elements at that level still point to the old objects.

## 2. Comparing Copying Approaches

| Operation on `int[][] a` | New outer array? | New `int[]` rows? |
|---|---|---|
| `int[][] b = a;` | No | No |
| `int[][] b = a.clone();` | **Yes** | **No** |
| `Arrays.copyOf(a, a.length)` | **Yes** | **No** |
| `System.arraycopy(a, 0, b, 0, a.length)` with `b` as a new outer array | Target has its own outer array | **No** |
| Create a new outer array then `clone()` each row | **Yes** | **Yes**, for non-null rows |

Assigning `b = a` creates no copy: `a == b` is `true`. In contrast, `a.clone()` creates a different outer array (`a == b` is `false`), yet typically `a[0] == b[0]` remains `true`.

## 3. `clone()` Creates a New Outer Array, but Shares Rows

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] copy = original.clone();

copy[0][0] = 9;
System.out.println(java.util.Arrays.deepToString(original));
System.out.println(original == copy);
System.out.println(original[0] == copy[0]);
~~~

**Exact expected stdout:**

~~~text
[[9, 2], [3, 4]]
false
true
~~~

`copy[0][0] = 9` modifies **the shared subarray**. Both outer arrays observe the new value.

However, replacing a **row reference** only modifies the outer array holding it:

~~~java
copy[1] = new int[]{8};
System.out.println(java.util.Arrays.deepToString(original));
System.out.println(java.util.Arrays.deepToString(copy));
~~~

**Exact expected stdout (continued):**

~~~text
[[9, 2], [3, 4]]
[[9, 2], [8]]
~~~

Distinguish: `copy[row][col] = value` modifies **an element belonging to the row**; `copy[row] = new int[]{...}` modifies **the reference slot in the outer array**.

## 4. `Arrays.copyOf` and `System.arraycopy` Are Also Shallow Copies at the Outer Level

~~~java
int[][] source = {{1, 2}, {3}};
int[][] copied = java.util.Arrays.copyOf(source, source.length);
int[][] target = new int[source.length][];
System.arraycopy(source, 0, target, 0, source.length);

System.out.println(source == copied);
System.out.println(source[0] == copied[0]);
System.out.println(source[0] == target[0]);
~~~

**Exact expected stdout:**

~~~text
false
true
true
~~~

Because the elements of `int[][]` are references to `int[]`, copying outer array elements only copies **reference values**, without automatically calling `clone()` on the rows.

With `Arrays.copyOf(source, source.length + 1)`, the newly added row slot defaults to `null`, not `new int[0]`.

## 5. Independently Copying Each `int[]` Row

When you want modifying the copy **not to affect `int` data in the original array**, you must create a separate outer array and separate subarrays:

~~~java
static int[][] detachRows(int[][] source) {
    if (source == null) return null;

    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = source[i] == null ? null : source[i].clone();
    }
    return copy;
}
~~~

- Each non-null row is `clone()`d into a new `int[]`.
- An empty row becomes a **new** `int[]` of length 0.
- A null row stays null, without calling `.clone()` on null.
- Each row keeps its own length, so this approach works with **jagged arrays** (*jagged array*).

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = detachRows(a);
b[0][0] = 99;

System.out.println(java.util.Arrays.deepToString(a));
System.out.println(java.util.Arrays.deepToString(b));
~~~

**Exact expected stdout:**

~~~text
[[1, 2], [3]]
[[99, 2], [3]]
~~~

For **`int[][]`**, this approach is sufficient to isolate primitive values. For arrays containing objects with mutable state, copying each row may still not be enough.

## 6. Two Rows Can Reference the Same Subarray

~~~java
int[] shared = {1, 2};
int[][] a = {shared, shared};

a[0][0] = 9;
System.out.println(java.util.Arrays.deepToString(a));
System.out.println(a[0] == a[1]);
~~~

**Exact expected stdout:**

~~~text
[[9, 2], [9, 2]]
true
~~~

This is **sharing right inside the same outer array**. When using `detachRows(a)`, each slot creates a separate new row, which **breaks the shared-reference relationship** even though the values in each row are still copied accurately.

If the problem requires a copy whose rows are independent of the source **yet preserve alias relationships between slots**, you need a different algorithm (for example, an identity map from original rows to copied rows). Do not assume every "deep copy" preserves object-sharing graphs.

## 7. Mutable Object Types: Cloning a Row Still Shares Elements

~~~java
StringBuilder[][] a = {
    {new StringBuilder("A")}
};
StringBuilder[][] b = {a[0].clone()};

b[0][0].append("!");
System.out.println(a[0][0]); // A!
~~~

Even though `a[0] != b[0]`, the two cells `a[0][0]` and `b[0][0]` still reference the same `StringBuilder` object, so `append` mutates the original.

In contrast, `b[0][0] = new StringBuilder("B")` only replaces the reference in **the cell of the new row**, without changing `a[0][0]`.

| Data type | To isolate state, how deep must copying go? |
|---|---|
| `int[][]` | Outer array + each `int[]` row |
| `String[][]` | Outer array + each row is usually enough, because `String` is immutable |
| `StringBuilder[][]` | Outer array + each row + **each mutable `StringBuilder`** |
| `int[][][]` | Must handle all **three array levels** |

`clone()` is not a command to "deep-copy all objects inside".

## 8. Comparing Identity and Contents

~~~java
int[][] a = {{1, 2}, {3}};
int[][] b = detachRows(a);

System.out.println(a == b);
System.out.println(java.util.Arrays.equals(a, b));
System.out.println(java.util.Arrays.deepEquals(a, b));
System.out.println(java.util.Arrays.deepToString(b));
~~~

**Exact expected stdout:**

~~~text
false
false
true
[[1, 2], [3]]
~~~

- `==` compares whether they are **the same outer array object**.
- `Arrays.equals(a,b)` compares **outer-level elements**; for `int[][]`, the elements are `int[]` references, so two new rows with different identities are not equal under this method.
- `Arrays.deepEquals(a,b)` compares **nested contents**.
- `Arrays.deepToString(a)` prints the row contents in a readable form.

**Equal contents do not prove two structures are independent**; you must examine shared references at each level.

## 9. Complete Java 17 Program

Save with the name **`ShallowArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class ShallowArrayDemo {
    private ShallowArrayDemo() {}

    static int[][] detachRows(int[][] source) {
        if (source == null) return null;
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null ? null : source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3, 4, 5}};
        int[][] alias = source;
        int[][] shallow = source.clone();
        int[][] copied = Arrays.copyOf(source, source.length);
        int[][] arrayCopied = new int[source.length][];
        System.arraycopy(source, 0, arrayCopied, 0, source.length);

        System.out.println("alias outer=" + (source == alias));
        System.out.println("clone outer=" + (source == shallow));
        System.out.println("clone row0=" + (source[0] == shallow[0]));
        System.out.println("copyOf row1=" + (source[1] == copied[1]));
        System.out.println("arraycopy row0=" + (source[0] == arrayCopied[0]));

        shallow[0][0] = 9;
        System.out.println("source after shallow=" + Arrays.deepToString(source));

        copied[1] = new int[]{8};
        System.out.println("source row1=" + Arrays.toString(source[1]));
        System.out.println("copied row1=" + Arrays.toString(copied[1]));

        arrayCopied[1][1] = 7;
        System.out.println("source after arraycopy="
                + Arrays.deepToString(source));

        int[][] independent = detachRows(source);
        independent[0][0] = 100;
        System.out.println("original=" + Arrays.deepToString(source));
        System.out.println("independent=" + Arrays.deepToString(independent));
        System.out.println("independent shares row0="
                + (source[0] == independent[0]));
        System.out.println("deep equals changed="
                + Arrays.deepEquals(source, independent));
        System.out.println("deep equals fresh="
                + Arrays.deepEquals(source, detachRows(source)));

        int[][] ragged = {{4}, null, {}};
        int[][] raggedCopy = detachRows(ragged);
        System.out.println("ragged copy=" + Arrays.deepToString(raggedCopy));
        System.out.println("null preserved=" + (raggedCopy[1] == null));
        System.out.println("row detached=" + (ragged[0] != raggedCopy[0]));

        int[] same = {1, 2};
        int[][] repeated = {same, same};
        int[][] repeatedShallow = repeated.clone();
        int[][] repeatedDetached = detachRows(repeated);
        System.out.println("same source rows=" + (repeated[0] == repeated[1]));
        System.out.println("same shallow rows="
                + (repeatedShallow[0] == repeatedShallow[1]));
        System.out.println("same detached rows="
                + (repeatedDetached[0] == repeatedDetached[1]));

        repeated[0][0] = 6;
        System.out.println("repeated=" + Arrays.deepToString(repeated));
        System.out.println("repeated detached="
                + Arrays.deepToString(repeatedDetached));

        StringBuilder[][] objects = {{new StringBuilder("A")}};
        StringBuilder[][] rowCopy = {objects[0].clone()};
        rowCopy[0][0].append("!");
        System.out.println("mutable original=" + objects[0][0]);
        rowCopy[0][0] = new StringBuilder("B");
        System.out.println("mutable original after replace=" + objects[0][0]);
        System.out.println("mutable copy=" + rowCopy[0][0]);

        int[][][] cube = {{{1}}};
        int[][][] cubeCopy = cube.clone();
        System.out.println("3d level2 shared=" + (cube[0] == cubeCopy[0]));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ShallowArrayDemo.java
java -cp . ShallowArrayDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShallowArrayDemo.java
java -cp . ShallowArrayDemo
~~~

### Exact expected stdout

~~~text
alias outer=true
clone outer=false
clone row0=true
copyOf row1=true
arraycopy row0=true
source after shallow=[[9, 2], [3, 4, 5]]
source row1=[3, 4, 5]
copied row1=[8]
source after arraycopy=[[9, 2], [3, 7, 5]]
original=[[9, 2], [3, 7, 5]]
independent=[[100, 2], [3, 7, 5]]
independent shares row0=false
deep equals changed=false
deep equals fresh=true
ragged copy=[[4], null, []]
null preserved=true
row detached=true
same source rows=true
same shallow rows=true
same detached rows=false
repeated=[[6, 2], [6, 2]]
repeated detached=[[1, 2], [1, 2]]
mutable original=A!
mutable original after replace=A!
mutable copy=B
3d level2 shared=true
~~~

**Explanation:** `clone()`, `Arrays.copyOf`, and `System.arraycopy` on `int[][]` still share rows; `detachRows` creates new `int[]` rows. Modifying an element of a shared row affects the original, whereas replacing an entire row reference in a separate outer array does not. For `StringBuilder[][]`, copying rows does not copy mutable objects.

## 10. Common Mistakes

| Mistake | Why is it wrong? | Fix |
|---|---|---|
| `b = a` creates a copy | Only adds another reference name | Use `clone` or copy rows depending on need |
| `a.clone()` is a deep copy | Only copies the outer array | Clone each `int[]` row |
| `Arrays.copyOf(a, a.length)` copies all `int[]` | Only copies row references | Create new subarrays |
| `System.arraycopy` automatically clones child objects | Only copies elements from the source array | Deep-copy according to data needs |
| `b[0][0]` and `b[0]` are the same kind of operation | One edits a cell, one replaces a row | Identify the exact reference level |
| `source[i].clone()` when a row is null | Throws `NullPointerException` | Check for null first |
| `Arrays.equals` is enough to compare matrices by value | It compares outer-level elements | Use `Arrays.deepEquals` |
| Checking only `a != b` to confirm independence | Rows can still be shared | Compare identity at each level |
| Cloning a `StringBuilder[]` row copies each `StringBuilder` | The objects are still shared | Create new objects for each mutable element |
| Two source rows share an object and per-row cloning keeps the alias | Cloning each row breaks the alias | If internal aliases must be preserved, use an identity map |

## 11. Exercises with Solutions

**A — Predict the output:**

~~~java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 7;
b[1] = new int[]{8};
System.out.println(Arrays.deepToString(a));
System.out.println(Arrays.deepToString(b));
~~~

**Answer:**

~~~text
[[7], [2]]
[[7], [8]]
~~~

**B — Why is `a == b` false yet modifying a row is still visible in `a`?** Because shallow copying creates a new outer array, while `a[i] == b[i]` can still be true.

**C — Safely copy a jagged array with null rows:** use `detachRows` from section 5; `{{1}, null, {}}` is copied into content structure `[[1], null, []]` with independent non-null rows.

**D — Want two rows to still share a reference after copying?** Do not directly use an independent per-row clone method; you need a source-row → copied-row map to reuse the same new row at the corresponding positions.

**E — For `StringBuilder[][]`, is copying each row enough?** Not if the requirement is not to share object state. You must create a copy of the `StringBuilder` (or corresponding mutable object) in each cell.

## 12. Checklist and Conclusion

- [ ] Understand that `int[][]` holds **row references**.
- [ ] Distinguish reference assignment from a shallow copy.
- [ ] Know that `clone()`, `Arrays.copyOf`, and `System.arraycopy` at the outer level still share subarrays.
- [ ] Understand that `b[row][col] = x` differs from `b[row] = new int[]{...}`.
- [ ] Copy independent `int[]` rows, including empty and null rows.
- [ ] Recognize when multiple rows point to the same `int[]` object.
- [ ] Distinguish subarrays from mutable objects stored inside subarray elements.
- [ ] Use `Arrays.deepEquals` and `Arrays.deepToString` for their intended purposes.
- [ ] Run `ShallowArrayDemo.java` with Java 17+ and verify stdout.

**Conclusion:** Shallow copying a multidimensional array in Java creates **a new outer array while still sharing the subarrays**. Modifying the contents of a shared row affects all references to that row; replacing a row reference inside a separate outer array does not. For `int[][]`, to make data independent, copy **both the outer array and each inner `int[]`**.