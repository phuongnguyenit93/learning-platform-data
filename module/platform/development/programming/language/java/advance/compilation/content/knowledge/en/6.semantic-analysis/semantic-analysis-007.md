# Definite assignment checking and potentially unassigned variables

In Java, a local variable can be declared before having a value:

~~~java
int total;
~~~

This declaration is valid on its own. A problem arises when the program **reads** `total` while the compiler has not proven that every execution path capable of reaching the read point has assigned the variable a valid value. This rule is called **definite assignment (DA)**.

DA is part of **compile-time semantic analysis**, not a check of values by test execution. The `javac` compiler inspects the control flow structure, conditions, branches, loops, and exit points to determine where a variable can be used. That helps block many uninitialized-data bugs before the application runs.

After this lesson, you should be able to explain why two seemingly nearly identical code snippets compile differently, distinguish local variables from fields, design clear initialization approaches, and understand the cases of `final`, `if/else`, loops, conditional operators, `switch`, and exceptions.

## 1. Model: assigning before reading on every reachable path

Imagine the program as a graph consisting of execution points and redirect branches. At a variable use point, `javac` must have grounds that the variable has been assigned on every path **that can complete and reach that location**.

~~~text
               [Start]
                  |
             [int answer;]
                  |
               [if (ok)]
                /     \
           true         false
            |             |
       [answer=10]    [answer=20]
            \             /
             \           /
             [Read answer]
                  |
                [End]
~~~

Both branches assign `answer`, so the read point is accepted. If the assignment in the `false` branch is removed, a path exists to the read point on which the variable has no value, so `javac` reports an error.

More strictly, the rule is **“definitely assigned before using the value”**, not simply “there is an assignment line earlier in the file”. The compiler evaluates the conditions in the program that can bring execution to the read line.

An **invalid** example:

~~~java
class MissingAssignment {
    static void show(boolean enabled) {
        int result;
        if (enabled) {
            result = 10;
        }
        System.out.println(result); // Compile error
    }
}
~~~

When `enabled == false`, the `if` block is skipped; no value is assigned to `result` before printing. `javac MissingAssignment.java` (if saved in the matching file) will report an error like **variable result might not have been initialized**. The formatted message and position may differ between JDK versions.

This differs from `NullPointerException`: in the example above, **no valid classfile can be generated yet to run that code**. The compiler immediately rejects reading a local variable that is not definitely assigned.

## 2. Local variables differ from fields and array elements

Not every variable declaration in Java is subject to the same initialization requirement.

| Data kind | If no initializer expression is written | Example |
| --- | --- | --- |
| Local variable in a method/block | **Receives no default value**; must be definitely assigned before reading | `int local;` |
| Method/constructor parameter | Receives a value when called; considered assigned at method entry | `void f(int count)` |
| Non-`final` instance field | Default-initialized by the JVM before running initializers/constructors | `int amount;` → initially `0` |
| Non-`final` `static` field | Receives a default value when the class is initialized per JVM rules | `static boolean ready;` → initially `false` |
| Elements of a newly created array | Receive the default value of the element type | `new int[2]` → two `0` elements |
| `final` field without an initializer (blank final) | Must be assigned according to special rules during class/object initialization | `final int id;` |

For primitive types, default values include `0`, `false`, or the character `'\u0000'` depending on type. For reference types, the default value is `null`. **A default value does not mean the business data is already valid.**

Standalone runnable Java 17+ example, saved as **`DefaultsVsLocals.java`**:

~~~java
public class DefaultsVsLocals {
    private int score;
    private boolean active;
    private String note;

    public static void main(String[] args) {
        DefaultsVsLocals demo = new DefaultsVsLocals();
        int[] numbers = new int[2];

        int local;
        local = 7;

        System.out.println("field int = " + demo.score);
        System.out.println("field boolean = " + demo.active);
        System.out.println("field String la null = " + (demo.note == null));
        System.out.println("array[0] = " + numbers[0]);
        System.out.println("local = " + local);
    }
}
~~~

~~~sh
javac -encoding UTF-8 DefaultsVsLocals.java
java DefaultsVsLocals
~~~

Exact stdout:

~~~text
field int = 0
field boolean = false
field String la null = true
array[0] = 0
local = 7
~~~

The variable `local` is allowed to be declared without an initializer because there is an assignment `local = 7` before reading. If that assignment is removed while keeping the print statement for `local`, the code will not compile. Fields `score` and `active`, conversely, already receive default values per object initialization rules.

If `numbers` is an unassigned **local reference variable** (`int[] numbers;`), it too must itself be assigned before accessing `numbers[0]`. The default rule applies to *elements of an already created array*, not auto-initializing the variable referencing the array.

## 3. `if/else`: branches must merge properly

With an `if/else` statement, each branch can bring a different assignment state to the merge point. If both branches can complete normally, **both must ensure the variable is assigned** before the subsequent line reads it.

A valid program, saved as **`BranchAssignment.java`**:

~~~java
public class BranchAssignment {
    static String category(int score) {
        String result;
        if (score >= 60) {
            result = "Dat";
        } else {
            result = "Chua dat";
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(category(80));
        System.out.println(category(35));
    }
}
~~~

~~~sh
javac BranchAssignment.java
java BranchAssignment
~~~

Stdout:

~~~text
Dat
Chua dat
~~~

If `else` is omitted without assigning `result` beforehand, the path with `score < 60` will reach `return result` without a value → DA error.

### Early-return branches can substitute for assignment

A branch that **cannot continue** to the read point because it already executed `return` or `throw` does not need to assign the variable for that read point. Valid example, saved as **`EarlyReturnAssignment.java`**:

~~~java
public class EarlyReturnAssignment {
    static int evaluate(boolean valid) {
        int answer;
        if (!valid) {
            return -1;
        }
        answer = 42;
        return answer;
    }

    public static void main(String[] args) {
        System.out.println(evaluate(false));
        System.out.println(evaluate(true));
    }
}
~~~

~~~sh
javac EarlyReturnAssignment.java
java EarlyReturnAssignment
~~~

Stdout:

~~~text
-1
42
~~~

From this we see that “every branch must have an assignment statement” is an oversimplification: only paths that can reach the read point matter. `return` terminates execution flow of the current method.

### Ternary operator and assigning at declaration

Sometimes the simpler approach is to express both possibilities completely in one expression:

~~~java
String result = score >= 60 ? "Dat" : "Chua dat";
~~~

This is an **illustrative snippet in a context where the `score` variable already exists**, not a standalone program. The conditional expression selects one of two values and assigns it immediately to `result`, so there is no path that skips initialization.

**Do not assign a dummy default value** just to “stop the compiler from reporting an error”, such as `int result = 0;` when `0` has no business meaning. It may make the code compile, but causes a forgotten branch to silently return an incorrect result.

## 4. Why doesn't the compiler just inspect actual runtime values?

The following snippet is **invalid** even though the author thinks `enabled` is “obviously true”:

~~~java
class LocalBooleanCondition {
    static void test() {
        boolean enabled = true;
        int count;
        if (enabled) {
            count = 5;
        }
        System.out.println(count); // DA error
    }
}
~~~

`enabled` is an ordinary local variable, not a constant expression at the point where the analysis rule requires it. Java's DA checking relies on deterministic syntactic/control-flow rules, **not general inference that every variable value in every program can always be precomputed**.

There are some special cases with constant boolean expressions, but DA should not be learned as an engine that “simulates executing every operation”. Having observed one run enter the `if` branch also does not prove that branch is always taken with other inputs.

The right diagnosis is to inspect the variable read location and list the paths that can reach it, rather than only looking at the nearest assignment line.

## 5. Loops: the loop body cannot be assumed to definitely run

An **invalid** example:

~~~java
class LoopAssignmentError {
    static void test(int limit) {
        int last;
        for (int i = 0; i < limit; i++) {
            last = i;
        }
        System.out.println(last); // DA error
    }
}
~~~

If `limit <= 0`, the `for` body may execute **0 times**, so `last` has not been assigned. The compiler does not rely on the hope that callers always pass a positive number.

The fix depends on business semantics:

- If “zero iterations” is a valid case, define its result value, such as `int last = -1;` with a clear contract.
- If the requirement is at least one iteration, **validate the input** or design the algorithm to reflect that.
- If only the value after the last iteration is needed, consider changing the computation so it does not use a potentially unassigned variable.

Runnable example, saved as **`LoopAssignment.java`**:

~~~java
public class LoopAssignment {
    static int lastIndex(int length) {
        if (length <= 0) {
            throw new IllegalArgumentException("length phai duong");
        }

        int last;
        for (int i = 0; i < length; i++) {
            last = i;
            if (i == length - 1) {
                return last;
            }
        }
        throw new IllegalStateException("Khong tim thay gia tri");
    }

    public static void main(String[] args) {
        System.out.println(lastIndex(3));
    }
}
~~~

~~~sh
javac LoopAssignment.java
java LoopAssignment
~~~

Stdout:

~~~text
2
~~~

This method returns `last` **right inside the assigned branch**; if the loop finishes without returning, the remaining path executes `throw` with an exception. It clarifies the control flow structure rather than merely fixing a compiler error with an arbitrary value. The example is also suitable for JDK 17+.

### `do-while` and `break`

`do-while` executes the loop body at least once before checking the condition. Standalone example:

~~~java
public class DoWhileAssignment {
    public static void main(String[] args) {
        int value;
        do {
            value = 9;
        } while (false);
        System.out.println(value);
    }
}
~~~

~~~sh
javac DoWhileAssignment.java
java DoWhileAssignment
~~~

Stdout:

~~~text
9
~~~

In this case it can be proven that `value` is assigned before printing. However, if the `do` body has complex `break`/`continue` branches or the assignment is only on some paths, each path must be re-examined; one cannot conclude “any do-while means every variable is assigned”.

## 6. Short-circuit: branches of `&&` and `||` also determine assignment state

The logical operators **`&&`** and **`||`** perform short-circuit evaluation:

- For `a && b`, if `a` is `false`, `b` is not evaluated.
- For `a || b`, if `a` is `true`, `b` is not evaluated.

Therefore, an assignment inside `b` does not necessarily occur on every execution.

An **invalid** example:

~~~java
class ShortCircuitError {
    static void test(boolean enabled) {
        int count;
        boolean ok = enabled && ((count = 5) > 0);
        System.out.println(count); // DA error
    }
}
~~~

If `enabled` is `false`, the expression `count = 5` does not execute. `ok` still has a valid boolean value, but `count` is not guaranteed to have been assigned.

It can be rewritten so the assignment clearly happens on every path:

~~~java
int count = 5;
boolean ok = enabled && count > 0;
~~~

These are two illustrative statements inside a method taking parameter `boolean enabled`. In real code, avoid embedding assignments inside logical expressions if doing so makes assignment reasoning hard to read.

### DA can differ between the true and false branches

Java has detailed rules to analyze **variables definitely assigned when a boolean expression is true or false**. For example, an assignment on the right-hand side of `&&` can be guaranteed on a path that exists only when the entire expression is `true`.

Runnable example, saved as **`BooleanFlowAssignment.java`**:

~~~java
public class BooleanFlowAssignment {
    static void show(boolean enabled) {
        int count;
        if (enabled && ((count = 5) > 0)) {
            System.out.println("count = " + count);
        }
    }

    public static void main(String[] args) {
        show(false);
        show(true);
    }
}
~~~

~~~sh
javac BooleanFlowAssignment.java
java BooleanFlowAssignment
~~~

The program's stdout has only one line:

~~~text
count = 5
~~~

The `if` branch executes only when the right-hand side has been evaluated and assigned `count`, so the read point **inside that branch** is valid. If `System.out.println(count)` is moved outside the `if`, the `enabled == false` path causes DA to fail. This is an example showing that **the variable read location** directly affects the compiler's conclusion.

## 7. `switch`: every entry and exit matters

With a `switch` statement, the number of cases, `default`, `break`, and fall-through behavior determine whether the variable is assigned at the next point. A valid example, saved as **`SwitchAssignment.java`**:

~~~java
public class SwitchAssignment {
    static String label(int code) {
        String value;
        switch (code) {
            case 1:
                value = "Mot";
                break;
            case 2:
                value = "Hai";
                break;
            default:
                value = "Khac";
                break;
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println(label(1));
        System.out.println(label(9));
    }
}
~~~

~~~sh
javac SwitchAssignment.java
java SwitchAssignment
~~~

Stdout:

~~~text
Mot
Khac
~~~

If the `default` branch is removed, a case where `code` matches neither `1` nor `2` can exit `switch` without having assigned `value`. The `return value` statement at the end is then invalid.

With Java 17+, a **switch expression** usually expresses computing the result value more clearly:

~~~java
String value = switch (code) {
    case 1 -> "Mot";
    case 2 -> "Hai";
    default -> "Khac";
};
~~~

This is an **illustrative snippet inside a method having variable `int code`**, not a standalone program. Every completion path of the switch expression produces a value assigned to `value`. Depending on the type of the selector expression and the cases, Java imposes exhaustiveness requirements. It avoids a class of bugs from forgetting to assign the result when designing multi-branch statement forms.

## 8. `try/catch`: exception paths must also be considered

For a `try` block, a statement can throw an exception before reaching the next assignment. Therefore, “there is an assignment line inside `try`” cannot be treated as sufficient for all paths.

Runnable example, saved as **`TryCatchAssignment.java`**:

~~~java
public class TryCatchAssignment {
    static int parseOrDefault(String input) {
        int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            value = -1;
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println(parseOrDefault("42"));
        System.out.println(parseOrDefault("abc"));
    }
}
~~~

~~~sh
javac TryCatchAssignment.java
java TryCatchAssignment
~~~

Stdout:

~~~text
42
-1
~~~

If `parseInt` succeeds, `value` receives the result; if it throws `NumberFormatException`, the `catch` branch assigns `-1`. Both paths continuing to `return value` have assigned the variable.

An **invalid** case:

~~~java
class IncompleteCatchAssignment {
    static int parse(String input) {
        int value;
        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("Gia tri khong hop le");
        }
        return value; // DA error: catch branch does not assign value
    }
}
~~~

If the intent is to report an error and terminate, an appropriate exception can be thrown via `throw` or another value returned per contract. One should not automatically use `-1` if `-1` is valid data in the business domain.

A `finally` block has its own control-flow rules, especially when combined with `return`, `throw`, and assigning `final` variables. When encountering complex structures, list every path that can complete normally; avoid reasoning solely by line order on screen.

## 9. `final` variables: definite assignment and definite unassignment

For a `final` local variable without an initializer (blank final), Java also needs to ensure **no reassignment** after a valid assignment.

Two related yet distinct ideas:

- **Definitely assigned (DA):** The variable is definitely guaranteed to have a value before reading.
- **Definitely unassigned (DU):** Before an assignment to a blank final, the compiler must guarantee the variable has not yet been assigned on the relevant path.

Valid example, saved as **`FinalAssignment.java`**:

~~~java
public class FinalAssignment {
    static int choose(boolean priority) {
        final int limit;
        if (priority) {
            limit = 100;
        } else {
            limit = 20;
        }
        return limit;
    }

    public static void main(String[] args) {
        System.out.println(choose(true));
        System.out.println(choose(false));
    }
}
~~~

~~~sh
javac FinalAssignment.java
java FinalAssignment
~~~

Stdout:

~~~text
100
20
~~~

Each call executes only one branch; on both branches, `limit` is assigned exactly once before being read. Conversely, the following snippet is **invalid**:

~~~java
class FinalReassignment {
    static void test() {
        final int limit;
        limit = 10;
        limit = 20; // Error: final variable is already assigned
    }
}
~~~

For a `final` variable already assigned at declaration, a subsequent assignment is likewise rejected:

~~~java
final int max = 10;
// max = 11; // Invalid if uncommented
~~~

A `final` reference does not mean the object it points to is immutable: you can mutate object state if the API allows it; the `final` rule here restricts **reassigning the reference variable itself**.

### Blank final fields differ from blank final locals

A `final` field without an initializer also needs to be assigned per initialization rules. For instance fields, constructors/initializers must ensure each object has a value for the field when initialization finishes; for static final fields, class initialization must satisfy the corresponding requirement. This is not a license to read an uninitialized field.

Runnable example, saved as **`FinalFieldDemo.java`**:

~~~java
public class FinalFieldDemo {
    private final int code;

    public FinalFieldDemo(int code) {
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    public static void main(String[] args) {
        System.out.println(new FinalFieldDemo(7).getCode());
    }
}
~~~

~~~sh
javac FinalFieldDemo.java
java FinalFieldDemo
~~~

Stdout:

~~~text
7
~~~

If the assignment `this.code = code` in the constructor is removed, the compiler will report that the blank final field might not have been initialized. Constructors calling one another via `this(...)` must also obey the assign-exactly-once rule; do not add the assignment in both the calling constructor and the called constructor.

## 10. DA does not guarantee a business-meaningful value

DA **only confirms that a valid assignment occurred**, not that the assigned value is good. For example:

~~~java
int divisor = 0;
int result = 100 / divisor;
~~~

`divisor` is definitely assigned, yet integer division by 0 causes an `ArithmeticException` at runtime. Similarly:

~~~java
String name = null;
// name.length(); // Throws NullPointerException if executed
~~~

`name` is assigned, yet a null value can still cause an error when used. In Java, DA analysis is not a general nullability analysis system.

In particular, the following code compiles but may return an unintended result:

~~~java
int price = -1;
System.out.println(price);
~~~

It satisfies DA because `-1` was assigned before printing; whether a negative unit price is valid must come from data validation and business rules.

| Mechanism | Key question |
| --- | --- |
| Syntax checking | Are the statements syntactically valid Java? |
| Type checking | Do assignments, operators, and method calls have valid types? |
| Definite assignment | Is the variable definitely assigned on paths reaching the read point? |
| Definite unassignment for blank final | Is it certain the variable has not yet been assigned before this assignment? |
| Runtime checks | Are data, exceptions, and resources safe during execution? |
| Business testing | Are the results correct according to requirements independent of code? |

Do not handle a DA error by assigning an arbitrary value and treating that as “having fixed the bug”. If a branch lacks an assignment, perhaps that branch itself lacks business behavior that needs to be defined.

## 11. Techniques for reading DA errors and fixing the root cause

When `javac` reports that a variable might not have been initialized:

1. **Locate the read point:** The line `return result` or `System.out.println(result)` is where a value must be guaranteed to exist.
2. **Find the declaration:** Which scope is the variable in? Is it a local without an initializer, or a field/parameter with different rules?
3. **Enumerate the paths:** Do `if/else`, `switch`, a 0-iteration loop, `break`, `continue`, `return`, `throw`, `try/catch`, and short-circuiting create a path that skips the assignment?
4. **Check the contract:** Is the missing-value case valid? If yes, a meaningful default value or a type representing absence is needed; if no, reject the data or exit the method intentionally.
5. **Simplify:** Prefer declaring with a meaningful initializer, simplifying branches with `return`, or extracting methods to reduce the number of states to track.
6. **Compile and test both paths:** A fix valid under DA can still be wrong for business logic; test normal, boundary, and error branches.

For example, if the requirement only allows using the value when `enabled` is `true`, the clear approach is placing the read statement **inside the assigned branch**, or returning early when not enabled. If the value must exist even when `enabled` is `false`, a value/behavior must be added for that branch.

### Why does the error sometimes appear “at the end of the method”?

The compiler usually points to **the first read point that fails DA**, not necessarily where the author “forgot to assign”. Therefore, do not only fix the red-underlined line: look upward at the branches that can skip the assignment.

A DA error can also surface when you add a new `if` branch, modify a `break`, or move a print statement outside a branch region. That is a consequence of changing the **control-flow graph**, even though the variable declaration did not change.

## 12. Consolidation exercises

**Exercise 1 — Two branches.** From `MissingAssignment`, add `else { result = 20; }`; predict the DA state at the print point. Then replace the else branch with `return;` and explain to yourself why it is also valid.

**Exercise 2 — Do not assume loops run.** From `LoopAssignmentError`, try `limit = 3` and `limit = 0` *in reasoning*, then explain why the compiler rejects it before running. Choose a valid contract to fix it.

**Exercise 3 — Short-circuit.** With `ShortCircuitError`, prove that `enabled == false` can skip assigning `count`. Move the print point into the `if` branch like `BooleanFlowAssignment` and compare.

**Exercise 4 — Switch.** Remove `default` in `SwitchAssignment` and try compiling. Which values of `code` leave `value` without an assignment? Rewrite using a switch expression and compare clarity.

**Exercise 5 — Final.** Try assigning `limit` a second time in `FinalAssignment`; explain the DU violation. With `FinalFieldDemo`, remove the field assignment in the constructor and confirm the compile error.

**Exercise 6 — Business testing.** In `DefaultsVsLocals`, could a field value of `0` represent “no data yet” or a valid unit price? Write a validation condition suitable for a specific application's requirements.

### Self-assessment questions

1. **What question does DA answer?** — Does every path capable of reaching a variable read point guarantee the variable was assigned beforehand?
2. **Does a local variable `int x;` automatically have value `0`?** — No; it must be definitely assigned before reading.
3. **What value does a field `int score;` have before an initializer/constructor assigns more?** — The default value `0` of `int`.
4. **Why can an assignment inside `for` still be insufficient?** — The loop might execute 0 times.
5. **Why can reading inside the true branch of `&&` be valid?** — That branch might only be reachable when the expression containing the assignment has executed.
6. **What does a blank final need in addition to DA?** — The definite unassignment rule before being assigned, to prevent reassignment.
7. **Does DA guarantee a variable is non-`null` or non-zero?** — No; it does not prove runtime validity or business correctness.

**Knowledge connection:** Definite assignment is a concrete example of how `javac` uses **control flow and language rules** to detect bugs before runtime. When you understand this rule thoroughly, it becomes easier to read errors involving local variables, `final`, `if` branches, loops, and exceptions, while also knowing when to fix the control-flow design instead of just adding default values.