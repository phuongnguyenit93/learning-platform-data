# Nested loops and tracking each counter variable — Java 17+

## 1. Goal: understanding outer and inner loops clearly

**Nested loops** (*nested loops*) are loops placed inside the body of another loop. Each time the outer loop goes through one iteration, the inner loop starts over from its initialization part.

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        System.out.println("i=" + i + ",j=" + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
i=0,j=0
i=0,j=1
i=0,j=2
i=1,j=0
i=1,j=1
i=1,j=2
~~~

Here:

- `i` is the **outer loop counter**: runs through 0 and 1.
- `j` is the **inner loop counter**: runs through 0, 1, 2 **for each value of i**.
- Total iterations of the inner body is **2 × 3 = 6**, because the two iteration counts are independent.
- Only after the inner loop finishes does the outer loop update `i`.

Lesson goal: trace `i` and `j` step by step, know when the inner loop re-initializes, distinguish rectangular/triangular loop patterns, traverse 2D arrays, and control `break`/`continue`.

## 2. Step-by-step execution order

For basic `for`, the order is **initialize → check condition → body → update → re-check**.

When there are two loops:

~~~text
Initialize i = 0
  Check i < 2
    Initialize j = 0
      Check j < 3 → body(i,j) → j++
      Check j < 3 → body(i,j) → j++
      Check j < 3 → body(i,j) → j++
      Check j < 3 → false: exit inner loop
    Continue remaining outer loop body if any statements remain
  Update i++
  Check i < 2 → initialize j = 0 for the next outer iteration
  ...
~~~

~~~mermaid
flowchart TD
    A["Initialize i"] --> B{"Outer loop condition?"}
    B -- "False" --> H["End"]
    B -- "True" --> C["Re-initialize j from start"]
    C --> D{"Inner loop condition?"}
    D -- "True" --> E["Process pair i,j"]
    E --> F["Update j"]
    F --> D
    D -- "False" --> G["Update i"]
    G --> B
~~~

**Note:** the inner loop does not just “continue `j` from the previous outer iteration”. When `j` is declared in the inner `for`, `int j = 0` runs **again each time** the outer loop reaches that `for` statement.

## 3. Trace table for `i` and `j`

For `i = 0..1`, `j = 0..2`:

| Inner body pass | `i` | `j` | Explanation |
|---:|---:|---:|---|
| 1 | 0 | 0 | First pass of the first outer iteration |
| 2 | 0 | 1 | Inner loop updates j |
| 3 | 0 | 2 | Last pass of the inner loop |
| — | 0 | 3 | Condition `j < 3` is false, body does not run |
| 4 | 1 | 0 | Outer loop increments i, **j is re-initialized** |
| 5 | 1 | 1 | Inner loop continues |
| 6 | 1 | 2 | Last pass |
| — | 1 | 3 | Inner loop stops; then i increments to 2 |
| — | 2 | — | Condition `i < 2` is false, outer loop stops |

The **—** rows are check steps, **not body execution passes**.

A useful self-tracing method: build a table with `i`, `j`, outer condition, inner condition, and action, and **record checks that return false separately**. This helps catch off-by-one mistakes (*off-by-one*) or misunderstandings about update timing.

## 4. Rectangles and triangles: iteration count is not always simple multiplication

**Rectangle:** inner loop bound is independent of `i`.

~~~java
int count = 0;
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        count++;
    }
}
System.out.println(count); // 6
~~~

**Triangle:** inner loop bound **depends on `i`**.

~~~java
int count = 0;
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= i; j++) {
        System.out.println(i + "," + j);
        count++;
    }
}
System.out.println("count=" + count);
~~~

**Exact expected stdout:**

~~~text
1,1
2,1
2,2
3,1
3,2
3,3
count=6
~~~

| `i` | Executed `j` values | Inner passes |
|---:|---|---:|
| 1 | 1 | 1 |
| 2 | 1, 2 | 2 |
| 3 | 1, 2, 3 | 3 |
| **Total** | | **1 + 2 + 3 = 6** |

If `i` runs from 1 to `n` and the inner loop runs `j = 1..i`, the iteration count is \(\frac{n(n+1)}2\), not `n * n`. When `n` is large enough, it is still of order `O(n²)`.

## 5. Does the outer counter stay unchanged while the inner loop runs?

With standard coding, **the inner body itself does not increment `i`**, so `i` stays constant throughout a complete run of the inner loop:

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println("start i=" + i);
    for (int j = 0; j < 2; j++) {
        System.out.println("  j=" + j);
    }
    System.out.println("end i=" + i);
}
~~~

**Exact expected stdout:**

~~~text
start i=0
  j=0
  j=1
end i=0
start i=1
  j=0
  j=1
end i=1
~~~

However, Java **does not automatically forbid** the inner body from modifying `i`. Writing `i++` inside the inner loop, or calling a method that mutates related state, can change the outer iteration count and make the code hard to follow. Practical rule: let `i` be managed by the **outer loop** and `j` by the **inner loop**, unless an algorithm genuinely requires otherwise.

## 6. Variable scope and naming

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        System.out.println(i + j); // Both i and j are in scope.
    }
    // j is no longer in scope here.
}
// i is also no longer in scope here.
~~~

A variable declared in the `for` initialization part only exists within the scope of that `for`. **The inner loop sees `i`**, but code outside the inner loop does not see `j` if `j` is declared inside the inner loop's initializer.

Do not declare another local variable with the same name `i` in the inner loop while the outer loop's `i` is still in scope:

~~~java
// Does not compile due to duplicate local variable name in nested scope:
// for (int i = 0; i < 2; i++) {
//     for (int i = 0; i < 3; i++) { }
// }
~~~

Names like `row`/`column`, `outer`/`inner`, or `studentIndex`/`subjectIndex` are often clearer than `i`/`j` in business code.

## 7. Traversing 2D arrays: use each row's exact length

A 2D array in Java is an **array of arrays**, so each row can have a different length (*jagged array*):

~~~java
int[][] matrix = {
    {1, 2},
    {3, 4, 5}
};

int sum = 0;
for (int row = 0; row < matrix.length; row++) {
    for (int col = 0; col < matrix[row].length; col++) {
        System.out.println(row + "," + col + "=" + matrix[row][col]);
        sum += matrix[row][col];
    }
}
System.out.println("sum=" + sum);
~~~

**Exact expected stdout:**

~~~text
0,0=1
0,1=2
1,0=3
1,1=4
1,2=5
sum=15
~~~

**Do not use** `matrix[0].length` as a shared column bound when rows may be uneven:

~~~java
// Bug-prone for non-rectangular arrays:
// for (int col = 0; col < matrix[0].length; col++) { ... }
~~~

Check `row < matrix.length` and `col < matrix[row].length`. If a row can be `null` in real data, check for null before accessing `.length`.

## 8. Unlabeled `break` and `continue` in nested loops

Without a label, `break;` exits the **innermost loop**; `continue;` skips the rest of the body of the **innermost loop** and moves to the update/condition step for the next iteration.

**Inner loop continue:**

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) continue;
        System.out.println(i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
0,0
0,2
1,0
1,2
~~~

The `j == 1` branch is skipped, yet **the inner loop still updates `j++`**, so `j == 2` is still processed.

**Inner loop break:**

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) break;
        System.out.println("inner " + i + "," + j);
    }
    System.out.println("after inner " + i);
}
~~~

**Exact expected stdout:**

~~~text
inner 1,1
after inner 1
inner 2,1
after inner 2
~~~

`break` at `j == 2` **does not terminate the outer loop**; hence the `i == 2` iteration still runs. Placing `break` at the wrong level can cause the program to run more iterations than intended.

## 9. `break label` and `continue label` to affect the outer loop

Java allows placing a **label** right before a loop:

~~~java
outer:
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= 3; j++) {
        if (i == 2 && j == 2) {
            break outer; // Terminates the entire outer loop.
        }
        System.out.println("seen " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
seen 1,1
seen 1,2
seen 1,3
seen 2,1
~~~

`break outer;` exits the construct labeled `outer`, without continuing subsequent `i` iterations.

Conversely, `continue outer;` skips the rest of the current **outer** loop iteration and jumps to the `i++` update step:

~~~java
outer:
for (int i = 1; i <= 3; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) {
            System.out.println("skip row " + i);
            continue outer;
        }
        System.out.println("check " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
check 1,1
skip row 1
check 2,1
skip row 2
check 3,1
skip row 3
~~~

**Distinction:**

| Statement in inner body | Effect |
|---|---|
| `break;` | Exits inner loop, returns to outer loop body after inner loop |
| `continue;` | Skips remaining inner loop iteration, moves to updating `j` |
| `break outer;` | Exits the entire labeled outer loop |
| `continue outer;` | Skips remaining outer loop iteration, moves to updating `i` |

Use labels sparingly; for complex multi-level logic, extracting into a method returning `boolean` or an explicit result can be easier to maintain.

## 10. Common mistakes when tracking two counters

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `j` is initialized only once for the whole program | Wrong iteration count and result | Remember `for (int j = ...)` is reached again on each outer pass |
| Using `j < matrix.length` instead of row length | Missing or exceeding columns | `j < matrix[i].length` |
| Using `i <= length` when accessing an array | Off-by-one, potential index error | `i < length` |
| Incrementing `i` in the inner loop update when intending `j` | Wrong progression, possible infinite loop | Use `j++` in the inner loop |
| Writing `j <= i` while starting `j = 0` when wanting 1..i | Adds an extra `j == 0` pass | Align bound and initial value |
| Assuming inner `break;` exits both loops | Outer loop keeps running | Use `break outer;` or redesign |
| Assuming inner `continue;` skips the whole row | Only skips one `j` pass | Use `continue outer;` to skip the whole outer pass |
| Using the same local variable name in nested scope | Compile error | Choose distinct names `i`/`j` or `row`/`col` |
| Printing only final result without logging `i,j` while debugging | Hard to locate the bug | Temporarily print each pair and update step |
| Always assuming iteration count = `n*m` | Wrong when `j` bound depends on `i` | Sum iterations for each `i` |
| Overlooking empty or null array rows | Logic bug or NPE | Account for `matrix[row].length == 0`, check null if data allows |
| Using an `O(n²)` nested loop on very large data | Can be slow | Re-evaluate the algorithm/actual complexity |

## 11. Complexity: calculated by total inner loop iterations

If the outer loop has `n` iterations and the inner loop has exactly `m` iterations **on each outer iteration**, total body executions are `n × m`, costing `O(nm)` if each body takes constant time.

If the outer loop is `i = 1..n` and the inner loop is `j = 1..i`, total body executions are:

\[
1 + 2 + \cdots + n = \frac{n(n+1)}{2}
\]

Thus the cost grows as `O(n²)`. If the inner loop exits early via `break`, actual iterations may be lower. If the inner body calls an operation costing `O(k)`, that cost must also be multiplied in during analysis.

Do not merely count **how many `for` statements appear** to conclude complexity; actual bounds and stopping conditions are the deciding factors.

## 12. Complete Java 17 program, runnable via CLI

Save with the exact name **`NestedLoopCountersDemo.java`**:

~~~java
public final class NestedLoopCountersDemo {
    private NestedLoopCountersDemo() {}

    static void rectangle() {
        int pairs = 0;
        for (int i = 0; i < 2; i++) {
            for (int j = 0; j < 3; j++) {
                System.out.println("pair " + i + "," + j);
                pairs++;
            }
            System.out.println("after outer " + i);
        }
        System.out.println("pairs=" + pairs);
    }

    static void triangle() {
        int count = 0;
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= i; j++) {
                System.out.println("triangle " + i + "," + j);
                count++;
            }
        }
        System.out.println("triangleCount=" + count);
    }

    static void jaggedArray() {
        int[][] matrix = {{1, 2}, {3, 4, 5}};
        int sum = 0;
        for (int row = 0; row < matrix.length; row++) {
            for (int col = 0; col < matrix[row].length; col++) {
                int value = matrix[row][col];
                System.out.println("cell " + row + "," + col + "=" + value);
                sum += value;
            }
        }
        System.out.println("sum=" + sum);
    }

    static void innerContinueAndBreak() {
        for (int i = 0; i < 2; i++) {
            for (int j = 0; j < 3; j++) {
                if (j == 1) continue;
                System.out.println("visit " + i + "," + j);
            }
        }
        System.out.println("finish after continue");
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) break;
                System.out.println("inner " + i + "," + j);
            }
            System.out.println("after inner " + i);
        }
    }

    static void labeledBreak() {
        outer:
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= 3; j++) {
                if (i == 2 && j == 2) {
                    System.out.println("stop at 2,2");
                    break outer;
                }
                System.out.println("seen " + i + "," + j);
            }
        }
        System.out.println("after labeled break");
    }

    static void labeledContinue() {
        outer:
        for (int i = 1; i <= 3; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) {
                    System.out.println("skip row " + i);
                    continue outer;
                }
                System.out.println("check " + i + "," + j);
            }
        }
        System.out.println("after labeled continue");
    }

    public static void main(String[] args) {
        System.out.println("== rectangle ==");
        rectangle();
        System.out.println("== triangle ==");
        triangle();
        System.out.println("== jagged ==");
        jaggedArray();
        System.out.println("== continue and break ==");
        innerContinueAndBreak();
        System.out.println("== labels ==");
        labeledBreak();
        labeledContinue();
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file. No Maven, Gradle, preview features, or libraries outside the JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NestedLoopCountersDemo.java
java -cp . NestedLoopCountersDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NestedLoopCountersDemo.java
java -cp . NestedLoopCountersDemo
~~~

### Exact expected stdout

~~~text
== rectangle ==
pair 0,0
pair 0,1
pair 0,2
after outer 0
pair 1,0
pair 1,1
pair 1,2
after outer 1
pairs=6
== triangle ==
triangle 1,1
triangle 2,1
triangle 2,2
triangle 3,1
triangle 3,2
triangle 3,3
triangleCount=6
== jagged ==
cell 0,0=1
cell 0,1=2
cell 1,0=3
cell 1,1=4
cell 1,2=5
sum=15
== continue and break ==
visit 0,0
visit 0,2
visit 1,0
visit 1,2
finish after continue
inner 1,1
after inner 1
inner 2,1
after inner 2
== labels ==
seen 1,1
seen 1,2
seen 1,3
seen 2,1
stop at 2,2
after labeled break
check 1,1
skip row 1
check 2,1
skip row 2
check 3,1
skip row 3
after labeled continue
~~~

**Verification:**

1. `rectangle()` generates 6 pairs `i,j`; `j` resets to 0 when `i` moves from 0 to 1.
2. `triangle()` has iteration counts 1 + 2 + 3, uneven across `i` passes.
3. `jaggedArray()` traverses two rows of different lengths, summing 1+2+3+4+5 = 15.
4. `continue` skips the `j == 1` pass; `break` only exits the inner loop when `j == 2`.
5. `break outer` terminates the entire outer loop at `i=2,j=2`.
6. `continue outer` immediately moves to the next outer pass when `j == 2`; `j == 3` is not evaluated.

## 13. Exercises with answers

### Exercise A — count print statements

~~~java
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 2; j++) {
        System.out.println(i + ":" + j);
    }
}
~~~

**Answer:** 6 lines, in order:

~~~text
0:0
0:1
1:0
1:1
2:0
2:1
~~~

### Exercise B — inner bound depends on outer loop

~~~java
int count = 0;
for (int i = 1; i <= 4; i++) {
    for (int j = 1; j <= i; j++) count++;
}
System.out.println(count);
~~~

**Answer:** `10`, because 1+2+3+4 = 10.

### Exercise C — fix out-of-bounds array traversal

~~~java
int[][] matrix = {{5}, {6, 7}};
// Wrong: uses matrix[0].length for all rows.
~~~

**Answer:**

~~~java
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        System.out.println(matrix[i][j]);
    }
}
~~~

**Exact stdout:** three lines `5`, `6`, `7`.

### Exercise D — which loop does `break` exit?

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) break;
        System.out.println(i + "," + j);
    }
}
~~~

**Answer:**

~~~text
0,0
1,0
~~~

`break` exits the inner loop at `j == 1`, but the outer loop still advances from 0 to 1.

### Exercise E — stop both loops

To exit both loops when finding `matrix[i][j] == target`, you can place a label:

~~~java
search:
for (int i = 0; i < matrix.length; i++) {
    for (int j = 0; j < matrix[i].length; j++) {
        if (matrix[i][j] == target) {
            break search;
        }
    }
}
~~~

**Answer:** `break search` exits the labeled outer loop and all loops inside it. Inside a search method, another approach is to `return` immediately at the found position.

## 14. Checklist and conclusion

- [ ] Distinguish outer loop counter `i` and inner loop counter `j`.
- [ ] Know that the inner loop's initializer runs again **on each outer loop pass**.
- [ ] Can build a trace table of `i,j` pairs and false-condition steps.
- [ ] Distinguish a rectangular `n×m` loop from a triangular `1+...+n` loop.
- [ ] Keep `i` updated by the outer loop and `j` by the inner loop unless there is a special requirement.
- [ ] Understand `i`/`j` variable scope and avoid duplicate-name declarations.
- [ ] Traverse 2D arrays using `matrix.length` and `matrix[row].length`.
- [ ] Understand unlabeled `break;`/`continue;` only affect the innermost loop.
- [ ] Distinguish `break outer;` and `continue outer;`.
- [ ] Can calculate iteration count/complexity based on actual inner loop bounds.
- [ ] Check boundary values, empty rows, and stopping conditions.
- [ ] Run `NestedLoopCountersDemo.java` with JDK 17+ and compare exact stdout.

**Conclusion:** To understand nested loops, always trace by **pairs of `i,j` values**: hold `i` for one outer pass, let `j` run until stopping, then update `i` and re-initialize `j`. When the inner bound depends on `i`, the iteration count is a **sum over each outer pass**, no longer simply a product. Knowing the exact scope of `break`/`continue` helps prevent control-flow bugs.