# Counter variable lifecycle in `for` — Java 17+

A basic `for` loop commonly uses a **counter variable** to track the number of iterations or the current position being processed. Understanding accurately *when the variable is initialized, when it changes, and its scope of use* helps avoid off-by-one errors, out-of-scope variable usage, and non-terminating loops.

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
// Prints sequentially: 0, 1, 2.
~~~

In this example, `i` is **declared and initialized once** when the `for` statement starts, taking values 0, 1, 2 across the body iterations; after updating to 3, the condition becomes false and the loop finishes. The variable `i` is **no longer in accessible scope** after the `for` statement because it was declared in the initialization part.

## 1. Distinguishing the counter value from the name's scope

In `for (int i = 0; i < 3; i++)`, the `int i = 0` part runs only **once each time execution enters the `for` statement**; that same variable `i` receives values 0, 1, 2 across the body passes. After the final pass, the update brings `i` to 3 and then the condition is false. If `i` is declared in the `for` header, code after the loop **cannot reference the name `i`**; this is a compile-time scope rule, not a runtime value check.

| Situation | What to track |
| --- | --- |
| One `for` statement running multiple passes | Initialized once, updated after each normal pass or a `continue` targeting the loop |
| `for` statement inside an outer loop or a method called repeatedly | **Each entry into the statement** is a fresh initialization |
| `break` stops mid-way | There is no final update for the exited iteration |
| Variable declared inside `for` | Usable in condition, update, and body; goes out of scope after `for` |
| Variable declared before `for` | Remains in scope after the loop to inspect the final value |

Therefore, when you want to observe the value after the loop, declare the variable outside. When you want to limit the counter strictly to a single traversal operation, declaring it in the `for` header is usually safe and readable. The examples below focus on **scope, re-initialization, and exit paths**, while the order of the three parts was introduced in the previous `for` lesson.
## 2. CLI-runnable Java 17+ program

Create a UTF-8 file named **`ForCounterLifecycleDemo.java`**:

~~~java
public class ForCounterLifecycleDemo {
    static void zeroIterations() {
        for (int i = 3; i < 3; i++) {
            System.out.println("unreachable");
        }
        System.out.println("zero=done");
    }

    static void declaredOutside() {
        int index = 0;
        for (; index < 3; index++) {
            System.out.println("external=" + index);
        }
        System.out.println("externalAfter=" + index);
    }

    static int step(int i) {
        System.out.println("step=" + i);
        return i + 1;
    }

    static void continueAndBreak() {
        for (int i = 0; i < 4; i = step(i)) {
            if (i == 1) {
                System.out.println("continueAt=1");
                continue;
            }
            if (i == 3) {
                System.out.println("breakAt=3");
                break;
            }
            System.out.println("seen=" + i);
        }
    }

    static void nested() {
        for (int row = 0; row < 2; row++) {
            for (int col = 0; col < 2; col++) {
                System.out.println("grid=" + row + "," + col);
            }
        }
    }

    static void twoCounters() {
        for (int left = 0, right = 3;
             left < right;
             left++, right--) {
            System.out.println("pair=" + left + "," + right);
        }
    }

    static void repeatedEntry() {
        for (int run = 1; run <= 2; run++) {
            int sum = 0;
            for (int i = 0; i < 2; i++) {
                sum += i;
            }
            System.out.println("run=" + run + ",sum=" + sum);
        }
    }

    public static void main(String[] args) {
        System.out.println("== initial false ==");
        zeroIterations();

        System.out.println("== outer scope ==");
        declaredOutside();

        System.out.println("== continue and break ==");
        continueAndBreak();

        System.out.println("== nested ==");
        nested();

        System.out.println("== two counters ==");
        twoCounters();

        System.out.println("== re-enter ==");
        repeatedEntry();
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file; use **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ForCounterLifecycleDemo.java
java ForCounterLifecycleDemo
~~~

**Exact expected stdout** of the `java ForCounterLifecycleDemo` command alone:

~~~text
== initial false ==
zero=done
== outer scope ==
external=0
external=1
external=2
externalAfter=3
== continue and break ==
seen=0
step=0
continueAt=1
step=1
seen=2
step=2
breakAt=3
== nested ==
grid=0,0
grid=0,1
grid=1,0
grid=1,1
== two counters ==
pair=0,3
pair=1,2
== re-enter ==
run=1,sum=1
run=2,sum=1
~~~

The output of `java -version` and `javac -version` varies by environment and is not part of the fixed stdout block. The program requires no external libraries.

## 3. Counter scope depends on declaration placement

### Declaring directly inside `for`

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i); // Valid.
}
// System.out.println(i); // Does NOT compile: i is out of scope.
~~~

The scope of `i` declared in **ForInit** includes the relevant parts of the `for` statement: condition, update, and body. Once the statement ends, the name `i` can no longer be used outside.

Saying “the variable lives until exiting the loop” is an intuitive way to describe scope; the compiler decides **whether a variable can be accessed** based on declaration scope, not on whether the variable's physical memory has been freed.

### Declaring before `for`

~~~java
int i = 0;
for (; i < 3; i++) {
    System.out.println(i);
}
System.out.println("after=" + i); // after=3.
~~~

Because `i` is declared outside, it **remains in scope** after the loop ends. The initialization slot in the `for` header can be left empty, though the `;` must still be kept.

When `int i` already exists in the enclosing scope, you cannot redeclare `int i` in the initialization part of a nested `for` in a conflicting scope:

~~~java
int i = 10;
// for (int i = 0; i < 3; i++) { } // Duplicate variable name error.
for (int j = 0; j < 3; j++) { } // Valid.
~~~

Conversely, two **sequential** `for (int i = ... )` statements can declare the same name `i` because the previous loop's scope has already ended.

## 4. `continue`, `break`, and the update part

**`continue`** in a basic `for` skips the remaining statements of the current iteration, yet still proceeds to the **update part** before checking the next condition. The demo shows:

~~~text
seen=0
step=0
continueAt=1
step=1
seen=2
step=2
breakAt=3
~~~

Specifically: upon hitting `continue` at `i == 1`, Java still calls `step(1)`, gets 2, and then checks the condition. Upon hitting `break` at `i == 3`, Java leaves the loop **immediately**: there is no `step=3`.

| Execution path | Does the update part run? |
| --- | --- |
| Body finishes normally | Yes |
| `continue;` targeting this `for` loop | Yes |
| `break;` exiting this loop | No |
| `return;` / `throw ...;` from body | Not via normal flow |
| Condition is false before body | No |

With nested loops or labeled `continue`/`break`, you must examine **which statement the control statement targets**, rather than concluding every `continue` runs the update of every `for` loop.

## 5. The counter does not automatically start at 0

`for` does not tie variables to a 0, 1, 2... convention; the author decides the initial value, condition, and how it updates:

~~~java
for (int n = 5; n >= 1; n--) {
    System.out.print(n + " ");
}
// Prints: 5 4 3 2 1 (with a trailing space).
~~~

You can use **two variables of the same type** in initialization and multiple update expressions separated by commas:

~~~java
for (int left = 0, right = 3;
     left < right;
     left++, right--) {
    System.out.println(left + "," + right);
}
// Prints: 0,3 then 1,2.
~~~

The condition part in `for` is **a single boolean expression**, not a comma-separated list of conditions. Use `&&` or `||` if you need to combine conditions. The update part is also not required to be `i++`: you can use `i += 2` or another assignment, as long as the loop is guaranteed an appropriate termination mechanism.

**The `for` body can run 0 times** if the condition is false immediately after initialization. In the example `for (int i = 3; i < 3; i++)`, only initialization and the first check occur; neither body nor update runs.

## 6. Each entry into the `for` statement is a fresh initialization

When the same `for` statement is executed again (for example, inside an outer loop body or a method called again), its initialization part runs **again from the start**.

~~~java
for (int run = 1; run <= 2; run++) {
    for (int i = 0; i < 2; i++) {
        System.out.print(i);
    }
    System.out.println();
}
// Prints two lines: 01 then 01.
~~~

The inner loop's `i` starts at 0 each time execution enters the inner loop statement; it **does not continue from the previous run's value**.

In two nested loops, use distinct names like `row` and `col` to express each role. Accidentally swapping variables in the condition or update can cause the loop to run incorrectly or never terminate.

### Distinguishing basic `for` from enhanced `for`

~~~java
int[] numbers = {4, 5};
for (int value : numbers) {
    System.out.println(value);
}
~~~

This is **enhanced for**. The `value` variable represents the element on each iteration; there are no explicit initialization/condition/update parts written by the author. Do not apply basic `for` rules like `i++` literally to this form.

## 7. Common mistakes

| Misconception | Correct rule |
| --- | --- |
| “`int i = 0` in `for` runs again on every pass.” | Initialized only once **per entry into the `for` statement** |
| “`i` declared inside `for` can be used after the loop.” | No; it is out of scope |
| “`continue` skips the update part too.” | In basic `for`, update still runs if `continue` targets that loop |
| “`break` still runs `i++` one more time.” | No |
| “`for` always executes at least one pass.” | It can run 0 passes |
| “Two sequential `for` loops cannot use the same name `i`.” | They can, as long as declaration scopes do not overlap |
| “Every counter must be `int` or start at 0.” | Choose an appropriate type/start; just keep syntax and condition valid |
| “`for (int i = 0; i < n; i++);` has the following block as its body.” | The `;` gives the loop an **empty body** |

**Avoid infinite loops and numeric overflow:** Always verify that the update moves the variable toward the stopping condition. With fixed-width integers, `i++` can overflow and wrap around; do not assume every increment will reach an arbitrary mathematical bound.

## 8. Self-check exercises

1. `for (int i=0; i<3; i++)`: which values does the body run with?  
   *Answer:* 0, 1, 2; the value 3 is only used in the final check.
2. Can `i` declared in the `for` header be printed after the loop's closing `}`?  
   *Answer:* No, it is out of scope.
3. If `int i=0; for (;i<2;i++) {}`, what is `i` equal to after the loop?  
   *Answer:* 2.
4. When the body hits `continue` targeting a basic `for`, what does Java do next?  
   *Answer:* Executes the update part and then checks the condition.
5. If the body hits `break`, does the update part run?  
   *Answer:* No.
6. How many times does `for (int i=4; i<4; i++)` run its body?  
   *Answer:* 0 times.
7. When a `for` loop inside an outer loop is executed twice, how many times does the inner loop's initialization run?  
   *Answer:* Twice, once on each entry into the inner loop.

## Checklist

- [ ] Remember the order **initialize → check → body → update → re-check**.
- [ ] Know that a counter declared in ForInit is in scope for the loop, not outside.
- [ ] Distinguish a variable declared **before the loop** from one declared **in the loop header**.
- [ ] Understand that `continue` (targeting the loop) still executes the update, while `break` does not.
- [ ] Know that initialization runs again when the `for` statement is entered another time.
- [ ] Check initial condition, update, and stopping point to avoid wrong or infinite looping.

**Conclusion:** The counter variable in basic `for` has a clear syntactic lifecycle: initialized upon entering the loop, checked and updated on each pass, and accessible only within its declaration scope. Mastering the execution order along with `continue`/`break` helps predict variable values accurately and write safe loops.
