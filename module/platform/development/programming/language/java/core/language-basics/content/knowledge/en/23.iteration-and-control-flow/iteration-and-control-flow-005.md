# Unlabeled `break` and `continue` — Java 17+

The two statements `break;` and `continue;` change the execution flow inside loops **without needing labels**.

- **`break;`**: terminates the **nearest enclosing loop or `switch`**.
- **`continue;`**: skips the rest of the **current iteration of the nearest loop**, moving to the preparation step for the next iteration. It does **not** move to the next `case` branch of a `switch`.

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 3) break;
    if (i % 2 == 0) continue;
    System.out.println(i);
}
// Prints only 1.
~~~

For `i = 0` and `i = 2`, `continue` skips the print statement; for `i = 3`, `break` terminates the entire loop.

## 1. Where Do They Differ?

| Criterion | Unlabeled `break;` | Unlabeled `continue;` |
| --- | --- | --- |
| Target | Nearest enclosing loop or `switch` | Nearest enclosing **loop** |
| Current body | Stops immediately | Skips remaining statements in the current iteration |
| After statement | Proceeds to the statement after the exited construct | Prepares the next iteration of the loop |
| In basic `for` | Does not run the update part of the exited loop | **Runs the update part** and then checks the condition |
| In `while` | Exits the loop | Returns to check the condition |
| In `do-while` | Exits the loop | Goes to the condition check at the bottom |
| In `switch` | Exits the nearest `switch` | Only valid if there is a suitable outer loop; advances to the next loop iteration |

**Important:** `if` is not a target of `break` or `continue`. When writing `if (condition) break;`, the `break` statement affects the enclosing loop/`switch`, not merely ending the `if` block.

## 2. Self-Contained Java 17+ Demo

Create a UTF-8 file **`UnlabeledBreakContinueDemo.java`**:

~~~java
public class UnlabeledBreakContinueDemo {
    static void breakFor() {
        for (int i = 0; i < 5; i++) {
            if (i == 3) {
                System.out.println("breakAt=" + i);
                break;
            }
            System.out.println("keep=" + i);
        }
        System.out.println("afterBreakFor");
    }

    static int step(int i) {
        System.out.println("update=" + i);
        return i + 1;
    }

    static void continueFor() {
        for (int i = 0; i < 4; i = step(i)) {
            if (i == 1) {
                System.out.println("skip=" + i);
                continue;
            }
            System.out.println("body=" + i);
        }
        System.out.println("afterContinueFor");
    }

    static void continueWhile() {
        int n = 0;
        while (n < 4) {
            n++;  // Advance before a possible continue.
            if (n % 2 == 0) {
                System.out.println("skipEven=" + n);
                continue;
            }
            System.out.println("odd=" + n);
        }
        System.out.println("afterWhile=" + n);
    }

    static void continueDoWhile() {
        int attempt = 0;
        do {
            attempt++;
            if (attempt == 1) {
                System.out.println("doSkip=" + attempt);
                continue;
            }
            System.out.println("doBody=" + attempt);
        } while (attempt < 2);
        System.out.println("afterDo=" + attempt);
    }

    static void nestedLoops() {
        for (int row = 1; row <= 2; row++) {
            for (int col = 1; col <= 3; col++) {
                if (col == 2) {
                    System.out.println("innerContinue=" + row + "," + col);
                    continue;
                }
                if (row == 2 && col == 3) {
                    System.out.println("innerBreak=" + row + "," + col);
                    break;
                }
                System.out.println("grid=" + row + "," + col);
            }
            System.out.println("outerEnd=" + row);
        }
    }

    static void switchInsideFor() {
        for (int value = 0; value < 4; value++) {
            switch (value) {
                case 0:
                    System.out.println("caseZero");
                    break; // Only exits switch.
                case 1:
                    System.out.println("continueLoop");
                    continue; // Moves to the next for iteration.
                case 2:
                    System.out.println("caseTwo");
                    break;
                default:
                    System.out.println("caseDefault");
            }
            System.out.println("afterSwitch=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("== break for ==");
        breakFor();

        System.out.println("== continue for ==");
        continueFor();

        System.out.println("== continue while ==");
        continueWhile();

        System.out.println("== continue do-while ==");
        continueDoWhile();

        System.out.println("== nested loops ==");
        nestedLoops();

        System.out.println("== switch inside for ==");
        switchInsideFor();
        System.out.println("done");
    }
}
~~~

Using **JDK 17 or higher**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 UnlabeledBreakContinueDemo.java
java UnlabeledBreakContinueDemo
~~~

**Exact expected stdout** of the `java UnlabeledBreakContinueDemo` command alone:

~~~text
== break for ==
keep=0
keep=1
keep=2
breakAt=3
afterBreakFor
== continue for ==
body=0
update=0
skip=1
update=1
body=2
update=2
body=3
update=3
afterContinueFor
== continue while ==
odd=1
skipEven=2
odd=3
skipEven=4
afterWhile=4
== continue do-while ==
doSkip=1
doBody=2
afterDo=2
== nested loops ==
grid=1,1
innerContinue=1,2
grid=1,3
outerEnd=1
grid=2,1
innerContinue=2,2
innerBreak=2,3
outerEnd=2
== switch inside for ==
caseZero
afterSwitch=0
continueLoop
caseTwo
afterSwitch=2
caseDefault
afterSwitch=3
done
~~~

`java -version` and `javac -version` display different details depending on the JDK environment and are not part of the fixed stdout. The example requires no external libraries.

## 3. `break`: Completely Exits the Nearest Loop

~~~java
int[] numbers = {2, 4, -1, 8};
for (int n : numbers) {
    if (n < 0) {
        break;
    }
    System.out.println(n);
}
// Prints: 2, 4. Value 8 is not processed.
~~~

Upon encountering `-1`, `break` immediately exits the loop; no subsequent iteration is started. When looking for the first matching element, exiting early with `break` often saves unnecessary steps.

`break` does not terminate the containing method: Java continues running the statements **after the loop**. To terminate the method itself, use `return` appropriately.

In **nested** loops, an unlabeled `break;` exits only the **nearest inner loop**:

~~~java
for (int row = 0; row < 2; row++) {
    for (int col = 0; col < 3; col++) {
        if (col == 1) break;
        System.out.println(row + ":" + col);
    }
}
// Prints 0:0 then 1:0.
~~~

The outer loop still executes its next iteration. If the business logic requires exiting multiple levels, redesign the control flow (for example, using a helper method returning a `boolean` or `return`); labeled `break` is a separate topic, not the behavior of unlabeled `break;`.

## 4. `continue`: Skips the Remainder of the Current Iteration

~~~java
int[] values = {3, -1, 5};
for (int value : values) {
    if (value < 0) {
        continue;
    }
    System.out.println(value);
}
// Prints 3 then 5.
~~~

The `continue` statement **does not exit the loop completely**: it only skips the statements placed after it in the body *of the current iteration*. The loop continues if more iterations remain and the condition permits.

**Easy-to-forget detail:** with basic `for`, `continue` still executes the update clause:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
// Prints 0 then 2, terminates normally.
~~~

In the full program, `step(i)` logs output, proving that even the iteration with `continue` at `i == 1` still produces the line `update=1`.

With `while`, `continue` jumps straight back to the condition, so you must ensure the control variable **has already advanced**:

~~~java
int i = 0;
while (i < 3) {
    i++;
    if (i == 2) continue;
    System.out.println(i);
}
// Prints 1 then 3.
~~~

If `i++` is placed after `continue`, it is very easy to create an infinite loop. With `do-while`, `continue` jumps to **the condition check after the body**, rather than jumping unconditionally to the top of the body.

## 5. `switch` Inside a Loop: Targets Can Differ

~~~java
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 0:
            System.out.println("zero");
            break;    // Exits switch, NOT for.
        case 1:
            continue; // Moves to the next for iteration.
        default:
            System.out.println("other");
    }
    System.out.println("after-switch");
}
~~~

When `i == 0`, the `break` statement goes to the `after-switch` statement **within the same for iteration**. When `i == 1`, `continue` skips `after-switch` altogether, updates `i++`, and evaluates the next iteration. When `i == 2`, the `default` branch runs and then prints `after-switch`.

Here is the key difference between the two keywords:

| Statement Position | `break;` | `continue;` |
| --- | --- | --- |
| Inside `for`, without an enclosing `switch` | Exits `for` | Next iteration of `for` |
| Inside `switch` nested inside `for` | Exits `switch` | Next iteration of `for` |
| Inside the inner loop of two nested loops | Exits inner loop | Next iteration of inner loop |
| Inside a standalone `switch`, not in a loop | Valid, exits `switch` | **Invalid**, no loop to continue |

Do not confuse `break` of a `case:` style `switch` with `case ->` semantics: arrow-style rules automatically separate branches, while unlabeled `break;` is still used to exit an appropriate loop or switch.

## 6. Comparison with `return` and Effect on Resource Cleanup

| Statement | Primary Meaning |
| --- | --- |
| `break;` | Exits nearest loop / switch |
| `continue;` | Skips the remainder of the nearest loop iteration |
| `return;` or `return value;` | Exits the currently executing **method** |
| `throw ...;` | Throws an exception, transferring to the exception handling mechanism |

Even though `break` or `continue` changes the destination, `finally` blocks that are required to execute under Java rules still run when exiting through them; do not use these two statements to bypass resource cleanup. For streams/files, prefer `try-with-resources` when guaranteed closing is required.

If an intentional infinite loop is needed, you can use `while (true)` combined with a `break` condition. If the goal is merely to skip an invalid value across iterations, `continue` usually expresses the intent more accurately.

## 7. Common Mistakes

| Misconception | Correct Behavior |
| --- | --- |
| "`break` inside nested loops exits both loops." | Unlabeled `break` only exits the nearest applicable construct |
| "`continue` ends the entire loop." | It only ends the **current iteration** |
| "`continue` in `for` also skips `i++`." | The update part still runs if `continue` targets that `for` loop |
| "`continue` in `while` automatically increments the counter." | No; ensure progress manually |
| "`break` in a `switch` inside a loop exits the loop." | It only exits the nearest `switch` |
| "`continue` advances to the next `case`." | It advances to the next **loop** iteration, not a `case` label |
| "Being inside an `if` is enough to use `break`." | There must be a suitable enclosing loop or switch |
| "`continue` can be used in a standalone `switch`." | No; it must be inside an appropriate loop |

## 8. Self-Check Exercises

1. `for (int i=0; i<4; i++) { if (i==2) break; print(i); }` — what does it print?  
   *Answer:* 0, 1.
2. Replacing `break` with `continue` above — what does it print?  
   *Answer:* 0, 1, 3.
3. With two nested loops, does `break;` in the inner loop stop the outer loop as well?  
   *Answer:* No.
4. Does `continue;` in a basic `for` run the update part?  
   *Answer:* Yes.
5. Which construct does `break;` inside a `switch` within a `while` exit?  
   *Answer:* The nearest `switch`.
6. Where does `continue;` inside a `switch` within a `while` jump?  
   *Answer:* To the condition check step of the nearest `while`.
7. Why is `continue` before the update statement dangerous in a `while` loop?  
   *Answer:* The control variable may never change, causing an infinite loop.

## Checklist

- [ ] `break;` exits the nearest loop or switch, without automatically ending the method.
- [ ] `continue;` skips the remainder of the current iteration of the nearest loop.
- [ ] Understand update differences across basic `for`, `while`, and `do-while`.
- [ ] Identify the **inner** loop accurately when loops are nested.
- [ ] Distinguish `break` for `switch` from `continue` targeting an outer enclosing loop.
- [ ] Ensure progress conditions and proper resource handling.

**Conclusion:** Unlabeled `break;` **exits the nearest loop/`switch` construct**, while unlabeled `continue;` **skips the rest of the iteration in the nearest loop**. Always identify the exact enclosing construct and next update step to avoid stopping at the wrong level or creating an infinite loop.
