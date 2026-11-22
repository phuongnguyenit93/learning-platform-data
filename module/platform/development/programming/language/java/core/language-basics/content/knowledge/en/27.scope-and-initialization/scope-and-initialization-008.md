# Keeping Variable Scope Small and Declaring Near First Use in Java

> **Java core — language-basics / Scope and Initialization**  
> **Environment:** Java 17+, single-file example, JDK only.  
> **Objective:** Declare variables where they first begin to be needed, restrict their scope to the appropriate block/branch/loop, avoid accidentally reusing stale state, and distinguish scope (*scope*) from the rule requiring assignment before reading (*definite assignment*).

## 1. Principle: smallest sufficient scope

*Scope* is the region of source code where a variable name is in effect. For a local variable declared in a block `{ ... }`, the name is normally in effect from its declaration position to the end of the block. Therefore, **declaring close to first use** helps readers see the intent clearly and avoids unnecessarily extending a variable's scope.

~~~java
static void example(int score) {
    System.out.println("received=" + score);

    if (score >= 60) {
        String message = "PASS"; // Only needed in this branch.
        System.out.println(message);
    }

    // System.out.println(message); // Does not compile: out of scope.
}
~~~

**Practical rule:** If a value is used only in one branch, place the variable inside that branch. If it is used only in a single iteration, place it inside the loop body. If a result must be used after the loop, declare an **accumulator/result variable** outside the loop.

Do not turn this rule into "cramming everything onto one line." Leave enough room for meaningful names, clear validation steps, and avoid forcing a complex expression to become unreadable.

## 2. Before and after: avoid declaring too early

**Before — variables live in a wider scope than needed:**

~~~java
static String oldStatus(boolean enabled, int score) {
    String result = "";
    String label = "";
    if (enabled) {
        label = score >= 60 ? "PASS" : "RETRY";
        result = label + ":" + score;
    } else {
        result = "SKIPPED";
    }
    return result;
}
~~~

**After — move variables into the branch where needed, return early:**

~~~java
static String status(boolean enabled, int score) {
    if (!enabled) {
        return "SKIPPED";
    }

    String label = score >= 60 ? "PASS" : "RETRY";
    return label + ":" + score;
}
~~~

Both versions return the same results for the example inputs, but the latter does not have to maintain `result` and `label` before knowing whether they will be used.

- `label` exists only in the remainder of the method after the early `return` branch; it does not appear in the inactive branch.
- If an intermediate value is used in multiple branches, choose an appropriate common block instead of pointlessly duplicating computation.
- A short method, meaningful variable names, and clear input checks are more important than reducing character count.

## 3. `if`/`else` blocks: place variables where truly needed

~~~java
static String classify(int number) {
    String result;
    if (number < 0) {
        result = "NEG";
    } else if (number == 0) {
        result = "ZERO";
    } else {
        result = "POS";
    }
    return result;
}
~~~

`result` must be outside the branches because it is used after the `if`/`else` chain. This is **justifiably wide scope**, not a design flaw. Each branch assigns a value so Java can prove `result` is assigned before `return`.

If each branch can return immediately, we can avoid the `result` variable:

~~~java
static String classifyDirect(int number) {
    if (number < 0) return "NEG";
    if (number == 0) return "ZERO";
    return "POS";
}
~~~

Case that does not compile due to missing assignment:

~~~java
// DOES NOT COMPILE:
// static int broken(boolean flag) {
//     int value;
//     if (flag) value = 5;
//     return value; // flag=false so value is not guaranteed assigned.
// }
~~~

**Distinction:** Variable `value` is already in *scope* at `return`, but **has not satisfied definite assignment**. Add an appropriate `else`, an intentional default value, or change the return structure to fix it.

## 4. `for` loops: limit control variables and temporary variables

When you do not need to use the index after the loop, declare it directly in the `for` initialization part:

~~~java
int sum = 0; // Result needed after the loop, so placed outside.
for (int i = 1; i <= 4; i++) {
    int square = i * i; // Only serves the current iteration.
    sum += square;
}
System.out.println(sum); // 30.
// System.out.println(i);      // Error: i is out of scope.
// System.out.println(square); // Error: square is out of scope.
~~~

Each iteration runs the body, executing the initialization `square = i * i` with the current index. Do not move `square` outside `for` if there is no need to use it outside the loop.

Enhanced `for` also has an element variable valid only inside the loop body:

~~~java
static int sumPositiveTwice(int[] values) {
    int total = 0; // Needed across multiple iterations.
    for (int number : values) {
        if (number <= 0) {
            continue;
        }
        int contribution = number * 2; // Used for this iteration.
        total += contribution;
    }
    return total;
}
~~~

With `{2, -1, 3, 0, 5}`, the sum is `(2 + 3 + 5) * 2 = 20`. Variable `contribution` is only initialized when the number is positive; avoid creating an empty variable and reassigning it across every branch.

**Reasonable exception:** If you need the index after the loop to report the stopping position or reuse an expensive-to-create object, you may declare it outside; however, make the reason clear and do not accidentally carry stale state across iterations.

## 5. `while`, array traversal, and input checks

With a `while` loop, the control variable may need to be used after the loop as well:

~~~java
int steps = 0;
while (steps < 3) {
    int nextStep = steps + 1;
    System.out.println("step=" + nextStep);
    steps++;
}
System.out.println("done=" + steps);
~~~

`steps` is outside because it is used in the condition and after the loop. `nextStep` only serves the body, so it is declared inside the body.

When traversing a string array, place the transformation variable **after the null check**, right before using it:

~~~java
static String firstNonBlank(String[] values) {
    for (String value : values) {
        if (value == null) {
            continue;
        }
        String normalized = value.trim();
        if (!normalized.isEmpty()) {
            return normalized;
        }
    }
    return "NONE";
}
~~~

`normalized` is not created when `value == null`; it exists only in the loop body after its declaration point. `firstNonBlank` above requires a non-null array argument; if the contract permits a null array, add a check at the start of the method.

To retrieve information after a loop, returning directly when found is reasonable; there is no need to keep a `found` variable from the start if only the first match is needed.

## 6. Small scope does not automatically make duplicate names valid

Two sibling blocks can reuse local `attempt`; declaring `attempt` again in a nested block while the outer local is still in scope remains an error:

~~~java
{
    int attempt = 1;
    System.out.println(attempt);
}
{
    int attempt = 2; // Valid: the previous scope has ended.
    System.out.println(attempt);
}
~~~

When a local shares a field's name, Java allows *shadowing*, but you must distinguish the short name from `this.field` or `ClassName.staticField`. In maintainable code, prefer names that reflect intent and keep scopes small; duplicate declaration and shadowing rules must still be obeyed.

## 7. `final`, `var`, and boundaries of the advice

In Java 17, `final` and `var` can make a variable's intent clearer, but they **do not change scope rules**:

~~~java
static String upper(String raw) {
    if (raw == null) return "MISSING";

    final String cleaned = raw.trim();
    if (cleaned.isEmpty()) return "EMPTY";

    var result = cleaned.toUpperCase(java.util.Locale.ROOT);
    return result;
}
~~~

- `final` forbids reassigning `cleaned` after it has been assigned; it does not by itself make the referenced object immutable and does not widen scope.
- `var` infers the local variable type from the initializer expression; `result` still has normal local scope. You cannot write `var x;` without an initializer.
- If the type is not obvious when reading the initializer expression, an explicit declaration such as `String result = ...` is often clearer.
- Do not promote every intermediate result to a field or static variable just to "make it usable everywhere": that changes state and data sharing, rather than simplifying scope.

*Scope* only states **where a name can be referenced**. The object a local variable points to can still live on if another reference exists after the local leaves scope; a closing brace `}` does not determine garbage collection timing.

## 8. Standalone Java 17+ program

Create the file **SmallScopeDemo.java**:

~~~java
import java.util.Locale;

public final class SmallScopeDemo {
    private static String status(boolean enabled, int score) {
        if (!enabled) {
            return "SKIPPED";
        }
        String label = score >= 60 ? "PASS" : "RETRY";
        return label + ":" + score;
    }

    private static int sumPositiveTwice(int[] values) {
        int total = 0;
        for (int number : values) {
            if (number <= 0) {
                continue;
            }
            int contribution = number * 2;
            total += contribution;
        }
        return total;
    }

    private static int squareSum(int limit) {
        int sum = 0;
        for (int i = 1; i <= limit; i++) {
            int square = i * i;
            sum += square;
        }
        return sum;
    }

    private static String firstNonBlank(String[] values) {
        for (String value : values) {
            if (value == null) {
                continue;
            }
            String normalized = value.trim();
            if (!normalized.isEmpty()) {
                return normalized;
            }
        }
        return "NONE";
    }

    private static String classify(int number) {
        String result;
        if (number < 0) {
            result = "NEG";
        } else if (number == 0) {
            result = "ZERO";
        } else {
            result = "POS";
        }
        return result;
    }

    private static String upper(String raw) {
        if (raw == null) {
            return "MISSING";
        }
        final String cleaned = raw.trim();
        if (cleaned.isEmpty()) {
            return "EMPTY";
        }
        var result = cleaned.toUpperCase(Locale.ROOT);
        return result;
    }

    public static void main(String[] args) {
        System.out.println("statusOff=" + status(false, 78));
        System.out.println("statusPass=" + status(true, 78));
        System.out.println("statusRetry=" + status(true, 42));

        System.out.println("positiveTwice="
                + sumPositiveTwice(new int[] {2, -1, 3, 0, 5}));
        System.out.println("positiveEmpty="
                + sumPositiveTwice(new int[0]));
        System.out.println("squareSum=" + squareSum(4));

        System.out.println("firstNonBlank=" + firstNonBlank(
                new String[] {" ", null, " Java ", "Other"}));
        System.out.println("firstMissing=" + firstNonBlank(
                new String[] {null, "   "}));

        System.out.println("negative=" + classify(-2));
        System.out.println("zero=" + classify(0));
        System.out.println("positive=" + classify(9));

        System.out.println("upper=" + upper(" java "));
        System.out.println("upperEmpty=" + upper("   "));
        System.out.println("upperMissing=" + upper(null));

        {
            int attempt = 1;
            System.out.println("firstBlock=" + attempt);
        }
        {
            int attempt = 2;
            System.out.println("secondBlock=" + attempt);
        }

        int steps = 0;
        while (steps < 3) {
            int nextStep = steps + 1;
            System.out.println("step=" + nextStep);
            steps++;
        }
        System.out.println("done=" + steps);
    }
}
~~~

Compile/run in the directory containing the file (PowerShell, Command Prompt, or Bash):

~~~bash
javac -encoding UTF-8 SmallScopeDemo.java
java SmallScopeDemo
~~~

**Exact expected stdout:**

~~~text
statusOff=SKIPPED
statusPass=PASS:78
statusRetry=RETRY:42
positiveTwice=20
positiveEmpty=0
squareSum=30
firstNonBlank=Java
firstMissing=NONE
negative=NEG
zero=ZERO
positive=POS
upper=JAVA
upperEmpty=EMPTY
upperMissing=MISSING
firstBlock=1
secondBlock=2
step=1
step=2
step=3
done=3
~~~

The methods `status`, `firstNonBlank`, and `upper` declare variables only when truly needed. `sumPositiveTwice` and `squareSum` place the accumulator outside the loop but the temporary variable inside. `attempt` is allowed to be declared twice in two blocks with non-overlapping scopes. `steps` can still be read after the loop because it was declared outside.

## 9. Common errors, checklist, and exercises

| Symptom | Appropriate adjustment |
| --- | --- |
| Declaring many variables at the top of a method, used much later | Move declarations closer to first use |
| Variable only used in one `if` branch but placed outside | Move inside the branch if the result is not needed afterward |
| Temporary variable used only for one iteration placed outside `for` | Declare and initialize inside the loop body |
| Sum/count needed after the loop but declared inside | Move the accumulator to an enclosing block |
| Using `i` after `for (int i = ...)` | If truly needed, declare `i` before the loop; otherwise, use a separate result |
| In-scope local redeclared in an inner block | Rename or restructure the blocks |
| Variable in scope but not guaranteed to have a value | Fix *definite assignment* on all paths |
| Using a field/static to bypass local scope limits | Consider parameters/return values before expanding shared state |

**Exercise 1.** Write a function counting even numbers in `int[]`, declaring variable `even` only where needed and keeping `count` wide enough to return after the loop.

**Exercise 2.** Write a function finding the first non-blank string in `String[]`, avoiding keeping `normalized` outside the loop. Why check for null before calling `trim()`?

**Exercise 3.** Given two `if` branches assigning to a shared result, try placing `result` inside a branch and explain the error when doing `return result` afterward. Rewrite with valid definite assignment or early return.

**Exercise 4.** Variable `int i` needs to be printed after a `for` loop. Compare `for (int i = ...)` with `int i = 0; for (; ...)` to choose the right scope.

**Exercise 5.** Write two sibling blocks both using local `temp`; then nest the second block inside the first to observe the duplicate-name error. Explain why a field can be shadowed by a local while overlapping local-local declarations cannot.

### Key Takeaway

**Declare locals close to where they are used and keep scope as narrow as sufficient.** Temporary variables belonging to a branch or loop iteration should stay inside that block; accumulators used after the loop belong outside the loop. Small scope reduces accidental misuse of names and state, but does not replace definite assignment rules, readability, or clean API design.
