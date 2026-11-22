# Using Short-Circuiting for Null Checks and Array Bounds — Java 17+

## 1. Core Lesson

In Java, the logical operators **`&&` (short-circuit AND)** and **`||` (short-circuit OR)** may **skip evaluating the right-hand operand** if the result is already determined by the left-hand operand.

This is the basis for safely checking in order: **reference not `null` → non-negative index → index less than `array.length` → then access element**.

~~~java
int[] values = {4, 0, -2};
int index = 0;

boolean positive = values != null
        && index >= 0
        && index < values.length
        && values[index] > 0;

System.out.println(positive); // true
~~~

If `values == null`, the expression `values.length` **is not evaluated**. If `index` is out of bounds, `values[index]` **is not accessed**. However, this holds only when checks are placed **in the right order and use short-circuit operators**.

## 2. Rules for `&&` and `||`

Given two boolean expressions `left` and `right`:

| Expression | When is `right` skipped? | Result when skipped |
|---|---|---|
| `left && right` | When `left == false` | `false` |
| `left || right` | When `left == true` | `true` |

Specifically:

~~~java
boolean a = false;
boolean b = true;

boolean andResult = a && b; // false
boolean orResult = b || a;  // true
~~~

Java evaluates the left-hand operand first. **If necessary**, the right-hand operand is then evaluated; this is not an "accidental compiler optimization" but **the operator's semantics**.

~~~mermaid
flowchart TD
    A["Evaluate left side of &&"] --> B{"Is left side true?"}
    B -- "No" --> C["Return false, skip right side"]
    B -- "Yes" --> D["Evaluate right side and use result"]
    E["Evaluate left side of ||"] --> F{"Is left side true?"}
    F -- "Yes" --> G["Return true, skip right side"]
    F -- "No" --> H["Evaluate right side and use result"]
~~~

Expressions like `a && b && c` are grouped by left-associativity; the whole chain can stop as soon as a false condition is found. Similarly, `a || b || c` can stop as soon as true is encountered.

## 3. Checking `null` in the Right Order

Suppose a `String` reference may be null:

~~~java
String name = null;

boolean valid = name != null && !name.isBlank();
System.out.println(valid); // false, does not throw NullPointerException
~~~

The left side `name != null` is false, so Java **does not call** `name.isBlank()`. If the order is reversed:

~~~java
String name = null;
// boolean invalid = !name.isBlank() && name != null;
// At runtime: NullPointerException because isBlank() is called first.
~~~

**Rule:** the safety condition must **precede the operation that depends on it**.

| Recommended | Why? |
|---|---|
| `obj != null && obj.isReady()` | Does not call method on null |
| `text != null && !text.isEmpty()` | Does not access null String |
| `array != null && array.length > 0` | Does not read `length` on null |
| `boxed != null && boxed > 0` | Does not unbox null wrapper |

Writing `&&` anywhere is not automatically safe. For example, `obj.isReady() && obj != null` still dereferences null **before** checking.

## 4. Guarding One-Dimensional Array Bounds

For an `int[] array` of length `n`, a valid index must belong to the interval **`[0, n)`**:

\[
0 \le \text{index} < \text{array.length}
\]

Java does **not** support chained mathematical syntax like `0 <= index < array.length`. You must write two separate conditions.

~~~java
static boolean positiveAt(int[] array, int index) {
    return array != null
            && index >= 0
            && index < array.length
            && array[index] > 0;
}
~~~

This method has the following properties:

1. Null array → `false`, does not access `length`.
2. Negative index → `false`, does not access element.
3. `index == array.length` → `false`: this is **the position immediately after the last element**.
4. Valid index → only then checks `array[index] > 0`.
5. Empty array → always returns `false` for any `int` index.

With `int[] values = {4, 0, -2}`, valid indices are `0`, `1`, `2`, **not 3**.

**Very common off-by-one bug:**

~~~java
// index <= array.length // WRONG for element access
// index < array.length  // RIGHT when paired with index >= 0
~~~

Negative indices cannot be omitted either: Java does **not** treat `array[-1]` as the last element like some other languages.

## 5. Checking Potentially Null Element Values

A reference array such as `String[]` can be **non-null**, yet one of its elements is **null**:

~~~java
String[] names = {"Java", null, "Go"};

boolean startsWithJ = names != null
        && 1 >= 0
        && 1 < names.length
        && names[1] != null
        && names[1].startsWith("J");

System.out.println(startsWithJ); // false, does not call startsWith on null
~~~

The guard sequence must distinguish **null array** from **null element**:

~~~java
static boolean startsWithJAt(String[] names, int index) {
    return names != null
            && index >= 0
            && index < names.length
            && names[index] != null
            && names[index].startsWith("J");
}
~~~

Omitting `names[index] != null` can cause `NullPointerException` at the end. Do not assume `names != null` guarantees every element exists and is non-null.

**Readability:** If you reuse the same `names[index]` too many times and data may change concurrently, validate/synchronize beforehand; merely repeating a guard expression does not make the operation atomic.

## 6. Using `||` to Reject Invalid Data

When you want to detect an **invalid** index, you can use the negated condition:

~~~java
static boolean invalidIndex(int[] array, int index) {
    return array == null || index < 0 || index >= array.length;
}
~~~

Here:

- If `array == null` is true, Java returns `true` immediately; `array.length` is not accessed.
- If `index < 0` is true, the subsequent condition is also skipped.
- Only after passing both guards is `array.length` read.

Common pattern inside a method:

~~~java
if (array == null || index < 0 || index >= array.length) {
    return false; // Or throw per API contract
}
return array[index] > 0; // After the guard, index is valid
~~~

Two ways to express the same condition domain:

| Meaning | Logic pattern |
|---|---|
| Valid for access | `array != null && index >= 0 && index < array.length` |
| Invalid | `array == null || index < 0 || index >= array.length` |
| Access element if valid | `guard && array[index] > 0` |
| Reject before accessing | `if (invalid) return ...;` then `array[index]` |

This is an application of **De Morgan's laws** when conditions have no side effects. Choose the phrasing that matches business semantics and is easy to verify.

## 7. `&` and `|` Do NOT Short-Circuit on Booleans

Java has the operators `&` (non-short-circuit AND) and `|` (non-short-circuit OR) usable on booleans. They **evaluate both sides**, unlike `&&` and `||`.

~~~java
int[] numbers = null;

// boolean unsafe = numbers != null & numbers.length > 0;
// If run: NullPointerException because the right side is still evaluated.
~~~

Similarly:

~~~java
int[] values = {4, 0};

// boolean unsafe = (values != null) & (values[99] > 0);
// If run: ArrayIndexOutOfBoundsException.
~~~

**Do not replace `&&` with `&` in a null guard.** Likewise for `|`, do not use it in place of `||` when relying on skipping a dangerous access on the right side:

~~~java
// values == null | values.length == 0
// If values is null, accessing values.length still runs and can throw NPE.
~~~

Comparison table:

| Operator | Used with boolean | Evaluates right side when left side already decides result? |
|---|---|---|
| `&&` | Yes | No |
| `||` | Yes | No |
| `&` | Yes | **Yes** |
| `|` | Yes | **Yes** |

`&`/`|` are also used in integer bitwise operations; that is a different feature. This lesson compares only **boolean semantics**.

## 8. Two-Dimensional Arrays Can Have Null Rows or Varying Row Lengths

In Java, `int[][]` is an **array of references to individual rows**. One row may be null, and another may have its own length (*jagged array*). Do not assume every row has length `matrix[0].length`.

~~~java
static boolean positiveAt2D(int[][] matrix, int row, int col) {
    return matrix != null
            && row >= 0
            && row < matrix.length
            && matrix[row] != null
            && col >= 0
            && col < matrix[row].length
            && matrix[row][col] > 0;
}
~~~

Correct order:

1. Outer array is non-null.
2. `row` is within `[0, matrix.length)`.
3. Row `matrix[row]` is non-null.
4. `col` is non-negative and less than **the length of that specific selected row**.
5. Only then read `matrix[row][col]`.

Moving `matrix[row] != null` before the `row` bounds check can still throw `ArrayIndexOutOfBoundsException`. Reading `matrix[row].length` before ensuring the row is non-null can throw `NullPointerException`.

## 9. Boxed `Boolean` Can Also Be `null`

With primitive `boolean`, only `true` or `false` is possible. With the `Boolean` wrapper, it can also be `null`:

~~~java
Boolean enabled = null;
boolean allowed = enabled != null && enabled;

System.out.println(allowed); // false
~~~

When `enabled == null`, the `enabled` operand on the right is not evaluated, avoiding null auto-unboxing.

If only true should be accepted, another option is:

~~~java
boolean allowed = Boolean.TRUE.equals(enabled);
~~~

This handles null safely, but do not confuse checking a `Boolean` with checking **array index bounds**: both issues can appear together and require independent guards.

## 10. Exceptions and Side Effects: Short-Circuiting Does Not Protect Everything

`&&`/`||` only skip **unevaluated operands**. They do not roll back earlier side effects and do not handle errors occurring inside the left side.

~~~java
int index = 0;
int[] values = {10, 20};

boolean result = index++ < values.length
        && values[index] > 0;

// Avoid writing this: index has already incremented before the right side uses index.
~~~

Although this expression might work for some inputs, it easily breaks at boundaries: e.g., if `index` starts at `values.length - 1`, the left side can be true, increment `index` to `values.length`, and the right side accesses out of bounds.

**A guard should not mutate the variable it is checking.** Better:

~~~java
int index = 1;
boolean valid = values != null
        && index >= 0
        && index < values.length;
if (valid) {
    int current = values[index];
    index++; // Explicit update in a separate statement
}
~~~

When multiple threads concurrently modify the reference, index, or array contents, ordinary guards **do not guarantee atomicity or thread safety**. Use appropriate synchronization or data ownership per requirements rather than just adding more `&&` checks.

## 11. When to Split into `if` Statements and Guard Clauses?

A short condition such as:

~~~java
boolean safe = array != null
        && index >= 0
        && index < array.length;
~~~

is usually very easy to understand. However, when multiple properties must be validated or you need **distinct error messages** for null, negative index, and too-large index, guard clauses are clearer:

~~~java
static int requireElement(int[] array, int index) {
    if (array == null) {
        throw new IllegalArgumentException("array is null");
    }
    if (index < 0 || index >= array.length) {
        throw new IndexOutOfBoundsException("invalid index: " + index);
    }
    return array[index];
}
~~~

Advantages:

- Pinpoints the exact reason for rejection.
- Separates validation from the read operation.
- Allows testing each error branch independently.
- Avoids overly long boolean conditions or repeated operations with side effects.

Java 17 also provides `Objects.checkIndex(index, length)` to check indices in `[0, length)`; it throws an exception if invalid. However, when the array itself may be null, you still must handle null **before** accessing `array.length`.

**Choose the API based on its contract:** query functions can return false on invalid input; mandatory accessors can throw meaningful exceptions. Do not silently return a default value if that obscures the distinction between invalid and valid data.

## 12. Complete Java 17 Example with Deterministic Output

Create a file named exactly **`ShortCircuitArrayGuardDemo.java`**:

~~~java
public final class ShortCircuitArrayGuardDemo {
    private ShortCircuitArrayGuardDemo() {}

    static boolean positiveAt(int[] array, int index) {
        return array != null
                && index >= 0
                && index < array.length
                && array[index] > 0;
    }

    static boolean invalidIndex(int[] array, int index) {
        return array == null || index < 0 || index >= array.length;
    }

    static boolean startsWithJAt(String[] names, int index) {
        return names != null
                && index >= 0
                && index < names.length
                && names[index] != null
                && names[index].startsWith("J");
    }

    static boolean positiveAt2D(int[][] matrix, int row, int col) {
        return matrix != null
                && row >= 0
                && row < matrix.length
                && matrix[row] != null
                && col >= 0
                && col < matrix[row].length
                && matrix[row][col] > 0;
    }

    static boolean traced(String label, boolean answer) {
        System.out.println("called " + label);
        return answer;
    }

    static int requireElement(int[] array, int index) {
        if (array == null) {
            throw new IllegalArgumentException("array is null");
        }
        if (index < 0 || index >= array.length) {
            throw new IndexOutOfBoundsException("invalid index: " + index);
        }
        return array[index];
    }

    public static void main(String[] args) {
        int[] scores = {4, 0, -2};
        System.out.println("positive[0]=" + positiveAt(scores, 0));
        System.out.println("positive[1]=" + positiveAt(scores, 1));
        System.out.println("positive[2]=" + positiveAt(scores, 2));
        System.out.println("negative index=" + positiveAt(scores, -1));
        System.out.println("end index=" + positiveAt(scores, 3));
        System.out.println("null array=" + positiveAt(null, 0));
        System.out.println("empty array=" + positiveAt(new int[0], 0));

        System.out.println("invalid null=" + invalidIndex(null, 0));
        System.out.println("invalid end=" + invalidIndex(scores, 3));
        System.out.println("valid index=" + !invalidIndex(scores, 2));

        String[] names = {"Java", null, "Go"};
        System.out.println("name[0]=" + startsWithJAt(names, 0));
        System.out.println("name[1]=" + startsWithJAt(names, 1));
        System.out.println("name null=" + startsWithJAt(null, 0));

        int[][] grid = {null, {3, 0}, {}};
        System.out.println("grid null row=" + positiveAt2D(grid, 0, 0));
        System.out.println("grid positive=" + positiveAt2D(grid, 1, 0));
        System.out.println("grid col end=" + positiveAt2D(grid, 1, 2));
        System.out.println("grid empty row=" + positiveAt2D(grid, 2, 0));

        Boolean enabled = null;
        System.out.println("nullable Boolean="
                + (enabled != null && enabled));

        boolean left = false;
        boolean skippedAnd = left && traced("and-right", true);
        System.out.println("&& skipped=" + skippedAnd);

        left = true;
        boolean skippedOr = left || traced("or-right", false);
        System.out.println("|| skipped=" + skippedOr);

        boolean eagerAnd = false & traced("and-eager", true);
        System.out.println("& evaluated=" + eagerAnd);

        boolean eagerOr = true | traced("or-eager", false);
        System.out.println("| evaluated=" + eagerOr);

        int[] missing = null;
        try {
            boolean unsafe = missing != null & missing.length > 0;
            System.out.println(unsafe);
        } catch (NullPointerException ex) {
            System.out.println("eager null=NullPointerException");
        }

        try {
            boolean unsafe = scores != null & scores[99] > 0;
            System.out.println(unsafe);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("eager index=ArrayIndexOutOfBoundsException");
        }

        System.out.println("required element=" + requireElement(scores, 0));
        try {
            requireElement(scores, 3);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("required invalid=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later; terminal in the directory containing the file; no Maven, Gradle, or external libraries needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ShortCircuitArrayGuardDemo.java
java -cp . ShortCircuitArrayGuardDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ShortCircuitArrayGuardDemo.java
java -cp . ShortCircuitArrayGuardDemo
~~~

**Exact expected stdout:**

~~~text
positive[0]=true
positive[1]=false
positive[2]=false
negative index=false
end index=false
null array=false
empty array=false
invalid null=true
invalid end=true
valid index=true
name[0]=true
name[1]=false
name null=false
grid null row=false
grid positive=true
grid col end=false
grid empty row=false
nullable Boolean=false
&& skipped=false
|| skipped=true
called and-eager
& evaluated=false
called or-eager
| evaluated=true
eager null=NullPointerException
eager index=ArrayIndexOutOfBoundsException
required element=4
required invalid=invalid index: 3
~~~

### How to Verify the Output

1. `positiveAt` rejects null arrays, empty arrays, negative indices, and indices equal to `length`; only accesses the element after guards pass.
2. `invalidIndex` uses short-circuit OR: a null array or out-of-bounds index safely yields true.
3. `startsWithJAt` checks both the array and **element** before invoking a method on the String.
4. `positiveAt2D` checks for null rows, per-row lengths, and out-of-bounds columns.
5. `Boolean enabled = null` avoids NPE thanks to the guard before unboxing.
6. The two lines `&& skipped` and `|| skipped` **do not print `called and-right` or `called or-right`**, proving the right side was skipped.
7. `&` and `|` still print `called and-eager` and `called or-eager` because they do not short-circuit.
8. Both `eager ...` cases throw NPE/AIOOBE; the example catches the exact types and prints fixed messages.
9. `requireElement` illustrates using an explicit exception instead of a default value.

## 13. Common Mistakes

| Mistake or misconception | Consequence | Correct approach |
|---|---|---|
| `array.length > 0 && array != null` | NPE if array is null | Check `array != null` first |
| `array != null & array.length > 0` | `&` always evaluates the right side | Use `&&` |
| `array == null | array.length == 0` | `|` always evaluates the right side | Use `||` |
| `index < array.length` without negative check | Negative indices can still cause invalid access | `index >= 0 && index < array.length` |
| `index <= array.length` | Allows index equal to length | Use `index < array.length` |
| `array != null && array[index] > 0` | Guards null only, not index | Add both bounds checks |
| `names != null && names[i].isBlank()` | Element `names[i]` may be null | Check `names[i] != null` |
| `matrix[row].length` before checking row | Row may be out of bounds or null | Guard matrix, row index, row reference, then col |
| `array[index++]` inside a guard | Index may change between check and access | Separate index update from validation |
| `&&` automatically synchronizes all data | Not atomic if another thread mutates the data | Use appropriate synchronization/ownership |
| Thinking `&&` and `&` differ only in performance | Side effects and exceptions can differ | Choose based on semantics |
| Using a null guard but still accessing outside it | The guard protects only the controlled block | Validate at access point or design a clear API |
| Nullable `Boolean` auto-converts null to false | Unboxing null throws NPE | Guard `!= null` or use `Boolean.TRUE.equals` |

## 14. Exercises with Answers

### Exercise A — checking a valid index

Given `int[] values = {5, 8, 13};` and an `index`, write a condition that reads `values[index]` only when the array exists and the index is valid.

**Answer:**

~~~java
boolean valid = values != null
        && index >= 0
        && index < values.length;
if (valid) {
    System.out.println(values[index]);
}
~~~

If `index == 3` or `-1`, the access block is skipped.

### Exercise B — `&&` vs. `&`

~~~java
int[] a = null;
boolean safe = a != null && a.length > 0;
// boolean unsafe = a != null & a.length > 0;
~~~

**Answer:** `safe == false`, throws no error. If the `unsafe` line runs, the right side still reads `a.length` and throws `NullPointerException`.

### Exercise C — guard with `||`

~~~java
int[] a = {2, 3};
int i = -1;
boolean invalid = a == null || i < 0 || i >= a.length;
System.out.println(invalid);
~~~

**Answer:** `true`; Java stops at `i < 0`, without evaluating the last operand.

### Exercise D — null String element

~~~java
String[] names = {null, "Java"};
int i = 0;
boolean ok = names != null
        && i >= 0 && i < names.length
        && names[i] != null && names[i].startsWith("J");
System.out.println(ok);
~~~

**Answer:** `false`, does not throw NPE.

### Exercise E — two-dimensional array

~~~java
int[][] matrix = {null, {3, 4}};
System.out.println(positiveAt2D(matrix, 0, 0));
System.out.println(positiveAt2D(matrix, 1, 1));
~~~

**Answer:**

~~~text
false
true
~~~

The method `positiveAt2D` is defined in the standalone example above.

### Exercise F — bug when index changes inside the guard

~~~java
int[] values = {10, 20};
int index = 1;
// boolean ok = index++ < values.length && values[index] > 0;
~~~

**Answer:** the left side compares `1 < 2`, yielding true, but increments `index` to 2; the right side `values[2]` causes `ArrayIndexOutOfBoundsException`. Keep `index` unchanged during the guard, and update it in a separate statement.

## 15. Checklist and Conclusion

- [ ] Remember `&&` skips the right side when the left side is false; `||` skips the right side when the left side is true.
- [ ] Do not confuse `&&`/`||` with boolean `&`/`|`.
- [ ] Always check `array != null` before `array.length`.
- [ ] Check both `index >= 0` and `index < array.length`.
- [ ] For reference arrays, check `array[index] != null` before calling methods on the element.
- [ ] For two-dimensional arrays, guard each level in the proper order.
- [ ] Use `array == null || index < 0 || index >= array.length` when detecting invalid indices.
- [ ] Understand that short-circuiting skips right-side effects, but does not roll back operations that already occurred.
- [ ] Do not increment/decrement the index inside guard comparisons if it will be used again.
- [ ] Distinguish single-thread data-safety checks from true thread safety.
- [ ] Choose between returning boolean or throwing an exception based on the API contract.
- [ ] Compile/run `ShortCircuitArrayGuardDemo.java` with Java 17+ and verify the exact stdout.

**Conclusion:** Short-circuiting works best when **guards are placed before operations that could fail**, in the order **null → non-negative index → index less than length → element exists → access**. `&&` and `||` provide the semantic guarantee to skip the right-hand side; `&` and `|` do not. Clear guards without side effects, combined with boundary tests, keep Java 17+ code readable, logically sound, and free from unnecessary `NullPointerException`/`ArrayIndexOutOfBoundsException`.
