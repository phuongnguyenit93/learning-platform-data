# Labeled `break` and `continue` in Nested Loops — Java 17+

## 1. Goal and Main Rules

When there are multiple nested loops, **unlabeled** `break;` and `continue;` by default act on the **nearest loop** enclosing the statement:

- `break;`: terminates the nearest loop, then continues after that loop.
- `continue;`: skips the remaining statements in the **current iteration** of the nearest loop, moving to the update/check step to proceed to the next iteration.

Java allows placing a **label** on a loop, and then specifying the target:

~~~java
outer:
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 3; j++) {
        if (i == 1 && j == 1) {
            break outer; // Terminates the entire for loop labeled outer.
        }
        System.out.println(i + "," + j);
    }
}
System.out.println("done");
~~~

**Exact expected stdout:**

~~~text
0,0
0,1
0,2
1,0
done
~~~

The label `outer` is a programmer-defined name, **not** a variable, not a `goto`, and does not create a new loop. In this lesson, we will clearly distinguish `break outer;` from `continue outer;` and trace the state of counter variables during control transfer.

## 2. Label Syntax and the Two Control-Transfer Statements

~~~java
myLoop:
for (int i = 0; i < 10; i++) {
    // ...
}
~~~

Full form:

- `labelName:` appears **immediately before the statement** being labeled.
- `break labelName;` transfers control to **after the labeled statement**.
- `continue labelName;` transfers to **the next iteration of the labeled loop**, if that label refers to a loop enclosing the `continue` location.

The label name must be a valid Java identifier (for example `outer`, `search`, `nextRow`). A label's scope is limited to the statement it is attached to; you cannot jump to a loop located in another method.

**Key Java distinction:** `break label;` can exit an appropriate **labeled statement**, including a block, whereas `continue label;` **requires** the label to belong to a **loop** (`for`, `while`, `do-while`). This lesson uses labels attached to loops.

## 3. Unlabeled: Only Affects the Inner Loop

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) break;
        System.out.println("pair " + i + "," + j);
    }
    System.out.println("after inner " + i);
}
~~~

**Exact expected stdout:**

~~~text
pair 1,1
after inner 1
pair 2,1
after inner 2
~~~

When `j == 2`, `break;` exits **loop `j`**. Loop `i` still runs the `after inner` statement and continues to the next `i` iteration.

Try replacing `break;` with `continue;`:

~~~java
for (int i = 1; i <= 2; i++) {
    for (int j = 1; j <= 3; j++) {
        if (j == 2) continue;
        System.out.println("keep " + i + "," + j);
    }
}
~~~

**Exact expected stdout:**

~~~text
keep 1,1
keep 1,3
keep 2,1
keep 2,3
~~~

`continue;` only skips the `j == 2` iteration, after which loop `j` still executes **`j++`** and checks `j <= 3`. Therefore `j == 3` is still visited in both outer loop iterations.

## 4. `break outer`: Leaves All Loops Inside the Target

~~~java
outer:
for (int i = 0; i < 3; i++) {
    for (int j = 0; j < 4; j++) {
        if (i == 1 && j == 2) {
            System.out.println("found " + i + "," + j);
            break outer;
        }
        System.out.println("scan " + i + "," + j);
    }
}
System.out.println("after search");
~~~

**Exact expected stdout:**

~~~text
scan 0,0
scan 0,1
scan 0,2
scan 0,3
scan 1,0
scan 1,1
found 1,2
after search
~~~

- When the program reaches the target at `i=1, j=2`, it exits the **outer loop labeled `outer`**.
- The remaining statements and iterations of both loops are skipped.
- The **update parts `j++` and `i++` on the interrupted iteration do not run automatically**.
- Execution continues after the entire outer loop, at `after search`.

A label does not need to match a counter variable name; choose expressive names such as `search` or `outer`.

## 5. `continue outer`: Skips the Rest of the Outer Loop's Iteration

~~~java
nextRow:
for (int row = 0; row < 3; row++) {
    System.out.println("row " + row);

    for (int col = 0; col < 3; col++) {
        if (col == 1) {
            System.out.println("skip rest " + row);
            continue nextRow;
        }
        System.out.println("cell " + row + "," + col);
    }

    System.out.println("row done " + row);
}
System.out.println("after rows");
~~~

**Exact expected stdout:**

~~~text
row 0
cell 0,0
skip rest 0
row 1
cell 1,0
skip rest 1
row 2
cell 2,0
skip rest 2
after rows
~~~

`continue nextRow;` means **skip the rest of the current `row` iteration**:

1. Do not continue running columns after `col == 1`.
2. Do not run the `row done` statement at the end of the outer loop body in that iteration.
3. **Still execute the update part of the `for (row)` loop: `row++`**, then evaluate the condition `row < 3`.
4. If the condition is still true, start a **new inner loop** for the next `row` value.

Thus `continue outer` **is not the same as `break outer`**: it does not stop the entire outer loop; it moves to the next iteration of the outer loop.

## 6. Comparison Table by Control-Transfer Level

Suppose we are inside loop `j` nested inside loop `i` labeled `outer`:

| Statement | Target | Update Current `j`? | Update Current `i`? | Where Does Execution Continue? |
|---|---|---|---|---|
| `break;` | Exits loop `j` | No | Not yet; outer body of `i` continues, updates at end of iteration | After loop `j` |
| `continue;` | Next iteration of `j` | **Yes** (basic for) | Not at that moment | Update/condition of loop `j` |
| `break outer;` | Exits loop `i` | No | **No** | After loop `i` |
| `continue outer;` | Next iteration of `i` | No | **Yes** (basic for) | Update/condition of loop `i` |

The update descriptions in the table apply to **basic `for`** loops with their own update clause. With `while` or `do-while`, `continue` transfers according to the condition-evaluation rules of that loop type; there is no automatic update expression like in basic `for`.

~~~mermaid
flowchart TD
    A["Running body of inner loop j"] --> B{"Statement encountered"}
    B -- "break" --> C["Exit loop j, continue outer body"]
    B -- "continue" --> D["Update and check loop j"]
    B -- "break outer" --> E["Exit loop i labeled outer"]
    B -- "continue outer" --> F["Update and check loop i"]
~~~

## 7. Tracing the Effect of `continue outer` on the Update Clause

To see clearly that the outer loop's update still runs:

~~~java
int updates = 0;

outer:
for (int i = 0; i < 3; i++, updates++) {
    for (int j = 0; j < 2; j++) {
        if (j == 0) continue outer;
    }
}

System.out.println("updates=" + updates);
~~~

**Exact expected stdout:**

~~~text
updates=3
~~~

In each outer iteration, the inner loop encounters `j == 0` and executes `continue outer;`. Even though the rest of the body is skipped, both `i++` and `updates++` in the outer loop update **still run**. After three outer iterations, `updates == 3`.

In a comma-separated update list, expressions are evaluated from left to right. When a mid-body control transfer can occur, reread the update code carefully to avoid misunderstanding which variables are modified.

## 8. Three Loop Levels: Labels Can Exit Multiple Levels

~~~java
stopAll:
for (int a = 0; a < 2; a++) {
    for (int b = 0; b < 2; b++) {
        for (int c = 0; c < 2; c++) {
            if (a == 1 && b == 0 && c == 1) {
                System.out.println("stop " + a + "," + b + "," + c);
                break stopAll;
            }
            System.out.println("triple " + a + "," + b + "," + c);
        }
    }
}
System.out.println("after all");
~~~

**Exact expected stdout:**

~~~text
triple 0,0,0
triple 0,0,1
triple 0,1,0
triple 0,1,1
triple 1,0,0
stop 1,0,1
after all
~~~

`break stopAll` leaves all three levels because the outermost loop `a` is the labeled statement. However, using labels is not always the most maintainable solution: when there are many loops and complex stopping conditions, consider **extracting a method** so you can use `return` clearly.

## 9. Labels and `switch` Nested Inside a Loop

When a `switch` is also inside a loop, an unlabeled `break;` exits the **nearest switch**, whereas `break outer;` can exit the labeled enclosing loop. `continue outer;` can move to the next loop iteration from inside the switch:

~~~java
outer:
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 0 -> {
            System.out.println("switch:continue");
            continue outer;
        }
        case 1 -> {
            System.out.println("switch:break");
            break outer;
        }
        default -> System.out.println("switch:other");
    }
    System.out.println("switch:post=" + i);
}
System.out.println("switch:done");
~~~

**Exact expected stdout:**

~~~text
switch:continue
switch:break
switch:done
~~~

Because `i == 0` transfers directly to the outer loop's update, `switch:post=0` is not printed. With `i == 1`, `break outer` stops the outer loop; `switch:post=1` is also not printed.

**Do not confuse:** an unlabeled `continue;` does **not** target a standalone switch; it requires an enclosing loop. Conversely, `break;` inside a switch statement normally ends the switch.

## 10. Validity Conditions, Label Scope, and Compilation Errors

**Valid example:** label attached directly to a loop:

~~~java
retry:
while (true) {
    break retry;
}
~~~

**Invalid example:** label attached to a non-loop block; `continue` cannot target that label:

~~~java
// outer: {
//     continue outer; // Compile error: label does not refer to a loop.
// }
~~~

**Valid example with a block:** labeled `break` can exit a labeled block:

~~~java
scope: {
    System.out.println("before");
    break scope;
}
System.out.println("after");
~~~

**Exact expected stdout:**

~~~text
before
after
~~~

Other errors to avoid:

- Writing `break nonexistent;` or `continue nonexistent;` when there is no enclosing label with that exact name → compile error.
- Using a label on a loop that **does not enclose the control-transfer site** → invalid.
- Using `continue` targeting a `switch` or a block → invalid; the target must be a loop.
- Reusing a label name in a nested region causing a duplicate label → compile error.
- Thinking a label is a variable or object that can be assigned or passed to a method → wrong; a label name only has syntactic control-flow meaning.

Labeled `break`/`continue` **cannot jump across a method/lambda boundary to an outside loop**. If the flow is complex, pass results back via `return` instead of trying to "jump" across methods.

## 11. Comparing `break outer`, `continue outer`, and `return`

| Statement | What Does It End? | Does the Program Continue After the Outer Loop? |
|---|---|---|
| `break outer;` | The labeled loop statement | Yes, after the outer loop |
| `continue outer;` | **Current iteration** of the labeled loop | Possibly, after subsequent iterations when the loop actually finishes |
| `return;`/`return value;` | The entire current method | No, the caller continues after the call |
| `throw exception;` | Transfers flow via exception | Depends on where the exception is caught |

Example searching for an element in a matrix:

~~~java
static int[] find(int[][] matrix, int target) {
    for (int row = 0; row < matrix.length; row++) {
        for (int col = 0; col < matrix[row].length; col++) {
            if (matrix[row][col] == target) {
                return new int[]{row, col}; // Exits the method.
            }
        }
    }
    return new int[]{-1, -1};
}
~~~

This is a situation where `return` is usually **easier to read than `break label`** if the goal upon finding the element is to terminate the entire search method. `break outer` is suitable when you need to exit the loops but still have shared post-loop processing.

**Caution with `finally`:** If control transfers out of a `try` block with a `finally` clause, Java still executes `finally` according to language rules before completing the transfer; avoid putting unexpected side effects or `return` inside `finally` that make reasoning difficult.

## 12. Complete Standalone Java 17 Program

Create a file with the exact name **`LabeledLoopControlDemo.java`**:

~~~java
public final class LabeledLoopControlDemo {
    private LabeledLoopControlDemo() {}

    static void plainBreak() {
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) break;
                System.out.println("pair " + i + "," + j);
            }
            System.out.println("after inner " + i);
        }
    }

    static void plainContinue() {
        for (int i = 1; i <= 2; i++) {
            for (int j = 1; j <= 3; j++) {
                if (j == 2) continue;
                System.out.println("keep " + i + "," + j);
            }
        }
    }

    static void labeledBreak() {
        search:
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 4; j++) {
                if (i == 1 && j == 2) {
                    System.out.println("found " + i + "," + j);
                    break search;
                }
                System.out.println("scan " + i + "," + j);
            }
        }
        System.out.println("after search");
    }

    static void labeledContinue() {
        nextRow:
        for (int row = 0; row < 3; row++) {
            System.out.println("row " + row);
            for (int col = 0; col < 3; col++) {
                if (col == 1) {
                    System.out.println("skip rest " + row);
                    continue nextRow;
                }
                System.out.println("cell " + row + "," + col);
            }
            System.out.println("row done " + row);
        }
        System.out.println("after rows");
    }

    static void updateAfterContinue() {
        int updates = 0;
        outer:
        for (int i = 0; i < 3; i++, updates++) {
            for (int j = 0; j < 2; j++) {
                if (j == 0) continue outer;
            }
        }
        System.out.println("updates=" + updates);
    }

    static void threeLevels() {
        stopAll:
        for (int a = 0; a < 2; a++) {
            for (int b = 0; b < 2; b++) {
                for (int c = 0; c < 2; c++) {
                    if (a == 1 && b == 0 && c == 1) {
                        System.out.println("stop " + a + "," + b + "," + c);
                        break stopAll;
                    }
                    System.out.println("triple " + a + "," + b + "," + c);
                }
            }
        }
        System.out.println("after all");
    }

    static void insideSwitch() {
        outer:
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 0 -> {
                    System.out.println("switch:continue");
                    continue outer;
                }
                case 1 -> {
                    System.out.println("switch:break");
                    break outer;
                }
                default -> System.out.println("switch:other");
            }
            System.out.println("switch:post=" + i);
        }
        System.out.println("switch:done");
    }

    public static void main(String[] args) {
        System.out.println("== break ==");
        plainBreak();
        System.out.println("== continue ==");
        plainContinue();
        System.out.println("== break label ==");
        labeledBreak();
        System.out.println("== continue label ==");
        labeledContinue();
        System.out.println("== update ==");
        updateAfterContinue();
        System.out.println("== 3 levels ==");
        threeLevels();
        System.out.println("== switch ==");
        insideSwitch();
    }
}
~~~

**Requirements:** JDK 17 or higher; open a terminal in the directory containing the file. Do not use external libraries beyond the JDK, Maven/Gradle, or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 LabeledLoopControlDemo.java
java -cp . LabeledLoopControlDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\LabeledLoopControlDemo.java
java -cp . LabeledLoopControlDemo
~~~

### Exact expected stdout

~~~text
== break ==
pair 1,1
after inner 1
pair 2,1
after inner 2
== continue ==
keep 1,1
keep 1,3
keep 2,1
keep 2,3
== break label ==
scan 0,0
scan 0,1
scan 0,2
scan 0,3
scan 1,0
scan 1,1
found 1,2
after search
== continue label ==
row 0
cell 0,0
skip rest 0
row 1
cell 1,0
skip rest 1
row 2
cell 2,0
skip rest 2
after rows
== update ==
updates=3
== 3 levels ==
triple 0,0,0
triple 0,0,1
triple 0,1,0
triple 0,1,1
triple 1,0,0
stop 1,0,1
after all
== switch ==
switch:continue
switch:break
switch:done
~~~

**Comparison:** `plainBreak` still lets the outer loop continue; `plainContinue` skips a single `j`; `labeledBreak` stops searching after `1,2`; `labeledContinue` skips the remainder of each row; `updates=3` confirms the outer loop update still runs; `threeLevels` exits all three levels; labels in `insideSwitch` target the outer loop.

## 13. Exercises with Answers

### A — Where does unlabeled `break` stop?

~~~java
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) break;
        System.out.println(i + ":" + j);
    }
}
~~~

**Answer:**

~~~text
0:0
1:0
~~~

Loop `j` stops at `j==1`, yet loop `i` still gets its second iteration.

### B — Exiting both loops

~~~java
outer:
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (i == 0 && j == 1) break outer;
        System.out.println(i + "," + j);
    }
}
~~~

**Expected stdout:**

~~~text
0,0
~~~

Stops the entire `outer` loop upon reaching the pair `0,1`.

### C — Skipping the rest of a row

~~~java
nextRow:
for (int i = 0; i < 2; i++) {
    for (int j = 0; j < 3; j++) {
        if (j == 1) continue nextRow;
        System.out.println(i + "," + j);
    }
}
~~~

**Expected stdout:**

~~~text
0,0
1,0
~~~

`continue nextRow` skips the remaining columns of the current row, then moves to the next row.

### D — Can a block label be used with `continue`?

~~~java
// block: {
//     continue block;
// }
~~~

**Answer:** no; labeled `continue` can only target a loop. For a labeled block, `break block;` can be used to exit an appropriate block.

### E — After `continue outer`, does `i++` run?

With `outer: for (int i=0; i<3; i++)`, `continue outer;` is called from the inner loop when `i=1`.

**Answer:** yes. Control transfers to **the update step of the labeled for loop**, `i++` changes 1 to 2, and then the condition `i<3` is checked.

## 14. Common Mistakes and Conclusion

| Mistake | Consequence | Fix |
|---|---|---|
| Using `break;` in the inner loop to exit both | Outer loop keeps running | `break outer;` |
| Using `continue;` in the inner loop to skip an entire row | Only skips one inner iteration | `continue outer;` |
| Confusing `continue outer` with ending the outer loop | Outer loop continues to the next iteration | Use `break outer` if you need to stop completely |
| Thinking `continue outer` skips the outer for's update | Misunderstands counter variables | Basic `for` still runs the outer update |
| `continue someBlock;` | Does not compile | Labels must be attached to a loop |
| Label is not on a construct enclosing the statement | Does not compile | Place the label on the target outer loop |
| Overusing many labels and multi-level jumps | Hard to maintain | Extract into a method and use `return` when clear |
| Confusing `break;` in a switch with `break outer;` | Exits at the wrong level | Identify the labeled switch/loop you want to leave |

**Checklist:**

- [ ] Know that unlabeled `break;` and `continue;` default to affecting the nearest loop.
- [ ] Know the syntax `label: for (...) { ... }`.
- [ ] Know that `break label;` completely exits the labeled loop.
- [ ] Know that `continue label;` skips the remainder of the current iteration of the labeled loop.
- [ ] Know that `continue outer;` in a basic `for` still runs the outer loop's update.
- [ ] Understand that `break outer;` does not run updates after the interrupted iteration.
- [ ] Distinguish block labels from loop labels; `continue` only accepts loop labels.
- [ ] Recognize cases with a switch nested inside a loop and pick the right label.
- [ ] Test counter variables, stopping branches, and code running after the loop.
- [ ] Run `LabeledLoopControlDemo.java` with JDK 17+ and verify the exact stdout.

**Conclusion:** In nested loops, **`break outer` completely leaves the outer loop**, whereas **`continue outer` only skips the active outer iteration and moves to that loop's update/check step**. Without labels, standard `break`/`continue` only affect the nearest loop. Use labels when you genuinely need to jump across loop levels; if an algorithm has too many complex exit points, extract a method for easier comprehension and testing.