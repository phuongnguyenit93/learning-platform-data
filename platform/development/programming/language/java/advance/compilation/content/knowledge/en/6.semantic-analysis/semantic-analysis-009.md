# Reachability, return, and invalid control-flow branches in Java

A Java program can be syntactically valid and have valid data types, yet still be rejected by `javac` because **a statement is unreachable**, **a value-returning method has a path that ends without returning**, or **`break`/`continue` has no valid target**. These errors belong to semantic analysis and *control-flow* checking during compilation.

For example, after `return 42;` in the same block, an ordinary statement following it has no execution path; conversely, if an `int` method only executes `return` when a condition is true, the case where the condition is false must be considered. In Java, **reachability is a static analysis rule of the language**, not `javac` test-running the program for all input values.

This lesson uses Java 17 or later and focuses on three questions: *Is this statement considered reachable? Can the method's control flow complete normally? And is a control-transfer statement valid inside its enclosing construct?*

## 1. Control constructs and two ways a statement terminates

A statement can **complete normally** (execution flows onward to the next statement) or **complete abruptly** (termination due to `return`, `break`, `continue`, `throw`, or an exception). This differs from the entire process terminating.

~~~java
static int answer() {
    return 42;
}
~~~

When `return 42;` executes, the method exits and returns 42 to the caller. If an ordinary statement immediately follows an unconditional `return` in the same block, the subsequent statement cannot be reached from the start of the block:

~~~java
static int answer() {
    return 42;
    // System.out.println("never"); // uncommenting causes unreachable statement
}
~~~

The snippet above only illustrates the error when uncommented. `return` is a way to complete abruptly; `throw` is as well, differing in that it transfers control to exception handling rather than returning a value normally.

A block `{\u0020...\u0020}` is considered able to complete normally if control flow can pass through its statements and exit the end of the block. This concept is used to check the existence of `return` in methods with a non-`void` return type.

## 2. Reachability is structural checking under JLS rules

A statement is considered *reachable* if Java's analysis rules allow control flow to reach that position. The rules are described in the Java Language Specification, section **Unreachable Statements** (JLS §14.22 for Java SE 17). The compiler does not have to prove all logical conditions or solve the halting problem to distinguish reachable from unreachable.

Basic cases:

- The first statement in a block can be reachable when that block is reachable.
- The next statement depends on whether the preceding statement can **complete normally**.
- After an unconditional `return` or `throw` in the same branch, a subsequent ordinary statement becomes unreachable.
- Constructs `if`, `while`, `do`, `for`, `switch`, labels, `break`, and `try/finally` have their own specific rules.
- The compiler uses **constant expressions** in certain specific rules, especially loop conditions; one should not infer that every precomputable expression value is treated identically across all constructs.

### 2.1. Why do `if (false)` and `while (false)` differ?

This is an important learning exception in Java's reachability rules:

~~~java
class IfFalseAllowed {
    public static void main(String[] args) {
        if (false) System.out.println("never");
        System.out.println("after");
    }
}
~~~

`javac --release 17 IfFalseAllowed.java` **accepts** the program. When run, the output is:

~~~text
after
~~~

The language allows `if (false)` branches of this kind to support code branches that can be toggled by constants during development; this is not evidence that the `if (false)` branch will execute.

Conversely, the following snippet is **rejected**:

~~~java
class WhileFalse {
    void bad() {
        while (false) {
            System.out.println("unreachable");
        }
    }
}
~~~

Running `javac --release 17 WhileFalse.java` yields an `unreachable statement` error on the loop body. The specific rule for `while` treats a constant `false` condition as making the loop body unreachable. The case `do { ... } while (false);` differs: the `do` body can execute **once before checking the condition**, so it can be valid.

**Do not replace** Java's reachability rule set with a speculative rule like “the compiler evaluates every `if` with a constant condition and eliminates unexecuted branches”. The two snippets above are verified with `javac --release 17` and yield different compilation outcomes.

### 2.2. Constant `true`, infinite loops, and `break`

~~~java
class WhileTrueNoBreak {
    static void run() {
        while (true) {
        }
        // System.out.println("after"); // uncommented: unreachable statement
    }
}
~~~

When the loop condition is the constant expression `true` and there is no suitable `break` path recognized by the reachability rules, the loop cannot complete normally. In a `void` method, never terminating is not wrong in itself; only a statement placed after that loop has a reachability issue.

~~~java
class WhileTrueBreak {
    static int compute() {
        while (true) {
            break;
        }
        return 3;
    }

    public static void main(String[] args) {
        System.out.println(compute());
    }
}
~~~

The second example is valid and prints `3`. An unlabeled `break` terminates the `while` loop, so `return 3;` is reachable.

Subtle point: reachability rules are **not replaced by reasoning over all runtime values**. For example:

~~~java
static void unusual() {
    while (true) {
        if (false) break;
    }
    System.out.println("after");
}
~~~

This snippet is **accepted for reachability** by `javac --release 17`, because the rule for `if` still allows the `break` statement to be considered reachable when checking the loop structure. At execution, the loop never terminates and the `println` line afterward does not run. That is clear proof that “reachable according to the JLS” does not mean “guaranteed to have a runtime path reaching it in practice”.

## 3. Return rules in methods

`return` terminates execution of the enclosing **method**, **constructor**, or **lambda body** according to syntactic context. Rules for the returned value type depend on the corresponding declaration.

### 3.1. Void methods and value-returning methods

In a `void` method, `return;` can be used to exit early, but `return expression;` is not allowed:

~~~java
static void printPositive(int n) {
    if (n <= 0) return;
    System.out.println(n);
}
~~~

In a method declaring return type `int`, normal `return` statements must have an expression validly convertible to `int`. Writing `return;` in this method is wrong. Writing `return "42";` is also wrong because `String` cannot be implicitly converted to `int`.

~~~java
static int doubleValue(int n) {
    return n * 2;
}
~~~

A method with a non-`void` return type **must not be able to complete normally at the end of its method body**. This rule explains the `missing return statement` error: there is at least one path that reaches the end of the method body without completing abruptly in an allowed manner (such as `return` or `throw`).

### 3.2. Why is return missing even though one branch already returned?

Invalid example file `MissingReturn.java`:

~~~java
public class MissingReturn {
    static int sign(int x) {
        if (x > 0) return 1;
    }
}
~~~

The command `javac --release 17 MissingReturn.java` reports:

~~~text
error: missing return statement
~~~

If `x <= 0`, the method passes through `if` without returning. This can be fixed with `else`, or with `return` after the `if`:

~~~java
static int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    return 0;
}
~~~

In this fix, every normal path through the branches reaches a `return`. There is no need to force a single `return` at the end of the method when appropriate terminating branches already exist.

### 3.3. `if (true)` is not sufficient proof of return

Example:

~~~java
class IfTrueMissing {
    static int value() {
        if (true) return 1;
    }
}
~~~

Although at runtime the condition is always true, this snippet is still rejected by `javac --release 17` with `missing return statement`. The rule evaluating whether an `if-then` **can complete normally** is not the same as evaluating `while(true)`; an `if` lacking `else` is still treated as potentially passing through the unexecuted branch. This is another example showing that control-flow checking is based on deterministic structural rules in the JLS.

Writing `return 1;` directly, or explicitly covering the required branches, removes that ambiguity.

### 3.4. throw can substitute for return on an error branch

~~~java
static int parsePositive(String text) {
    int result = Integer.parseInt(text);
    if (result <= 0) {
        throw new IllegalArgumentException("Must be positive");
    }
    return result;
}
~~~

If the data is invalid, the method completes abruptly via `throw`; if valid, `return` finishes with a value. No path completes normally past the end of the method body. Even so, the method can raise `NumberFormatException` at runtime when the string is not a number; static flow checks do not guarantee input data is always valid.

An `int` method with an infinite `while(true) { }` can also compile even though it contains no `return`, because the method body cannot complete normally. The rule does **not** require every call to be guaranteed to return in finite time.

## 4. Control branches: if/else and paths

The compiler inspects branches according to language structure. Valid example:

~~~java
static String classify(int number) {
    if (number < 0) {
        return "âm";
    } else if (number == 0) {
        return "không";
    } else {
        return "dương";
    }
}
~~~

Because all branches are covered by `if/else if/else`, the body cannot complete normally. It can equivalently be written with two guard clauses and a final `return`, like the complete program in section 9.

If the final `else` is omitted without adding a fallback `return`, the compiler may report `missing return statement`. When logic structure grows complex, inspect **every path from the start of the method to the end** yourself. Paths encountering `return` or `throw` will not continue; remaining paths must terminate according to the method's return rule.

### 4.1. Return inside a lambda is not a return from the outer method

~~~java
static int sizeOfLongNames(java.util.List<String> names) {
    long count = names.stream()
        .filter(name -> {
            if (name.length() < 5) return false;
            return true;
        })
        .count();
    return Math.toIntExact(count);
}
~~~

The two `return` statements inside the lambda belong to the **lambda**, and do not exit `sizeOfLongNames`. The outer method still needs `return Math.toIntExact(count);`. Inside a block-style lambda body, return paths must match the target type of the functional interface; a lambda's `return` cannot be treated as an exit from the enclosing method.

## 5. switch statements and switch expressions

`switch` in Java has two roles to distinguish:

- **`switch` statement** controls execution flow; `case` arms can contain statements, and in colon form can have fall-through according to rules.
- **`switch` expression** produces **a value**; branches must obey rules for providing a result or completing abruptly appropriately.

### 5.1. A switch statement does not guarantee return if a branch is missing

Intentionally invalid file `SwitchIncompleteReturn.java`:

~~~java
public class SwitchIncompleteReturn {
    static int value(int n) {
        switch (n) {
            case 1: return 1;
            case 2: return 2;
        }
    }
}
~~~

`javac --release 17 SwitchIncompleteReturn.java` rejects it with `missing return statement`: values of `n` other than 1 or 2 let `switch` complete normally. Fix with an appropriate `default: return ...;`, or add `return` after `switch`.

A `break` in a `switch` statement exits `switch`, **not** the method. If the method needs to return a value, a `return` must still be ensured on all paths.

### 5.2. Switch expressions using arrow or yield

~~~java
static int points(String grade) {
    return switch (grade) {
        case "A" -> 10;
        case "B" -> 8;
        default -> 0;
    };
}
~~~

This is a switch **expression**, having a value type compatible with `int`. With a `String` selector, having `default` covers values not matching the two listed cases.

When a statement block is needed in an arm, use `yield` to supply the value:

~~~java
static int adjusted(String grade) {
    return switch (grade) {
        case "A" -> {
            int bonus = 2;
            yield 8 + bonus;
        }
        default -> 0;
    };
}
~~~

`yield` supplies a value to the **switch expression**, rather than returning directly from the enclosing method like `return`; in the example, the outer `return` returns the value of the entire switch expression. In a switch expression using an arrow block, a branch cannot complete normally without producing a value.

Intentionally invalid file:

~~~java
class SwitchExpressionMissing {
    static int value(String s) {
        return switch (s) {
            case "A" -> 1;
            default -> {
                int unused = 1;
            }
        };
    }
}
~~~

`javac --release 17` reports `switch rule completes without providing a value` on the `default` branch. The fix is replacing the block with `default -> 0;` or adding `yield 0;` inside the block.

Do not use `break 10;` instead of `yield 10;` in Java 17 switch expressions. `yield` and `break` have different responsibilities.

## 6. break, continue, and valid labels

Both `break` and `continue` are ways to complete abruptly, yet **their control-transfer targets differ**:

| Construct | Unlabeled `break;` | Unlabeled `continue;` |
|---|---|---|
| `for`, `while`, `do` | Exits the nearest enclosing loop | Jumps to the next iteration of the nearest loop |
| `switch` statement outside a loop | Exits `switch` | Invalid because there is no enclosing loop |
| `switch` statement inside a loop | Exits `switch`, normally continuing the loop body | Continues the enclosing loop |
| Plain `if` block | Unlabeled `break` has no valid target if not inside a loop/switch | Unlabeled `continue` is invalid if not inside a loop |

Example:

~~~java
static int firstOdd(int[] values) {
    for (int value : values) {
        if (value % 2 == 0) continue;
        return value;
    }
    return -1;
}
~~~

If an even number is encountered, `continue` skips the rest of the current iteration; if the first odd number is encountered, `return` exits the method; if the array finishes, `return -1` ensures no return path is missing.

### 6.1. Labeled break and labeled continue

~~~java
static int countPositive(int[][] matrix) {
    int count = 0;
    outer:
    for (int[] row : matrix) {
        for (int n : row) {
            if (n < 0) break outer;
            if (n == 0) continue;
            count++;
        }
    }
    return count;
}
~~~

`break outer;` transfers control out of the `for` loop labeled `outer`, rather than only exiting the inner loop. Unlabeled `continue;` applies to the nearest `for (int n : row)` loop. If `continue outer;` is written, the target `outer` must designate an **iteration statement** (loop) enclosing that location.

A statement can be labeled to serve as a target for `break label;` if the label encloses that statement, whereas **`continue label;` is valid only when the label is attached to a loop**.

### 6.2. Control-flow errors blocked by the compiler

First invalid file:

~~~java
class BreakOutside {
    void bad() {
        break;
    }
}
~~~

`javac --release 17 BreakOutside.java` rejects it: `break outside switch or loop`.

Second invalid file:

~~~java
class ContinueSwitch {
    static void bad(int n) {
        switch (n) {
            case 1: continue;
            default: break;
        }
    }
}
~~~

`javac --release 17 ContinueSwitch.java` rejects it: `continue outside of loop`. `switch` is not an iteration statement. If `switch` is inside a loop, an unlabeled `continue` can apply to that loop.

Third invalid file:

~~~java
class LabelContinueNonLoop {
    static void bad() {
        start: {
            continue start;
        }
    }
}
~~~

This case is rejected with `not a loop label: start`: the label `start` is attached to a block, not to a loop. Replacing `continue start;` with `break start;` is a valid construct to terminate the matching labeled block.

`break` or `continue` cannot arbitrarily jump into a block that has not started; Java does not support `goto`-style jumps to arbitrary code locations.

## 7. How try/catch/finally affects return flow

A method can `return` inside `try` or `catch`, yet `finally` will execute when control leaves the `try` construct in normal cases per language semantics. Therefore, `finally` must also be considered before concluding the observed result.

~~~java
static int safeParse(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

If `safeParse("12")` is called, the `finally` block prints `cleanup` before the call returns 12 to the caller. If `safeParse("x")` is called, `catch` handles `NumberFormatException`, `finally` prints `cleanup`, and then -1 is returned.

One must distinguish **executing `finally`** from **`finally` completing normally**. If `finally` itself executes `return` or `throw`, it can replace the earlier exit reason:

~~~java
class FinallyReturn {
    static int f() {
        try {
            return 1;
        } finally {
            return 2;
        }
    }
}
~~~

Java 17 **compiles** this and calling `f()` returns 2, yet writing `return` inside `finally` is very hard to maintain and can mask exceptions or results from `try`. Normally let `finally` perform cleanup operations only, or use **try-with-resources** when managing `AutoCloseable`.

With more complex code, `javac` also has to check flow through `catch` and `finally`; a statement after `try` can be unreachable if every exit path completes abruptly. However, in business logic, avoid relying on hard-to-read return/throw combinations inside finally.

## 8. Combining with definite assignment and semantic analysis

**Reachability** answers whether a statement can be reached according to language rules. **Definite assignment** checks whether a local variable has definitely been assigned before being read. They are related in flow analysis, yet not identical.

~~~java
static int maybeValue(boolean flag) {
    int n;
    if (flag) {
        n = 10;
    }
    // return n; // error: variable n might not have been initialized
    return 0;
}
~~~

`return n;` would be reachable, yet the variable `n` is not guaranteed to be assigned if `flag` is `false`. To return n, a value must be assigned in both branches, or initialized before `if`.

~~~java
static int definite(boolean flag) {
    int n;
    if (flag) {
        n = 10;
    } else {
        n = 20;
    }
    return n;
}
~~~

All paths reaching `return n;` have assigned `n`, so the snippet is valid.

Similarly, a method can have all expressions validly typed yet still lack `return`; or have complete `return` paths yet fail to resolve a symbol/method. `javac` evaluates several distinct semantic rules, and the first error message is usually the best starting point for investigation.

## 9. Complete Java 17 program and verified stdout

Create a file **`FlowDemo.java`** with the following full code (no `package`). This is a standalone program covering multiple return paths, switch expressions, break/continue, labels, and finally.

~~~java
public final class FlowDemo {
    static String classify(int n) {
        if (n < 0) return "âm";
        if (n == 0) return "không";
        return "dương";
    }

    static int points(String grade) {
        return switch (grade) {
            case "A" -> 10;
            case "B" -> 8;
            default -> 0;
        };
    }

    static int firstOdd(int[] values) {
        for (int value : values) {
            if (value % 2 == 0) continue;
            return value;
        }
        return -1;
    }

    static int countPositive(int[][] matrix) {
        int count = 0;
        outer:
        for (int[] row : matrix) {
            for (int n : row) {
                if (n < 0) break outer;
                if (n == 0) continue;
                count++;
            }
        }
        return count;
    }

    static int safeParse(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            return -1;
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println(classify(-3));
        System.out.println(classify(0));
        System.out.println(classify(4));
        System.out.println(points("A"));
        System.out.println(firstOdd(new int[]{2, 4, 7, 8}));
        System.out.println(firstOdd(new int[]{2, 4}));
        System.out.println(
            countPositive(new int[][]{{1, 0, 2}, {3, -1, 9}, {10}})
        );
        System.out.println(safeParse("12"));
        System.out.println(safeParse("x"));
    }
}
~~~

In a terminal in the directory containing `FlowDemo.java`, run:

~~~sh
javac --release 17 -encoding UTF-8 FlowDemo.java
java FlowDemo
~~~

Verified **exact** stdout:

~~~text
âm
không
dương
10
7
-1
3
cleanup
12
cleanup
-1
~~~

Why does it produce this output?

| Line | Control-flow explanation |
|---|---|
| `âm`, `không`, `dương` | Three input values branch into different `return` guards in `classify` |
| `10` | Switch expression selects `case "A"`, returning the value for `points` |
| `7` | `continue` skips 2, 4; encountering 7 triggers `return` immediately |
| `-1` | No odd numbers in the second array; loop ends and executes `return -1` |
| `3` | Counts 1, 2, 3; encountering -1, `break outer` skips 9 and the last row |
| `cleanup` then `12` | `try` prepares to return 12; `finally` runs before the caller prints the result |
| `cleanup` then `-1` | `catch` prepares to return -1 due to parse error; `finally` runs before the caller prints |

The code was checked by compiling with `javac --release 17` and executing on the JVM; the outputs above are not untested guesses. All `return` outcomes and control-transfer statements in the example have valid targets.

## 10. Intentionally invalid programs to practice reading javac errors

Save each error example into its corresponding **separate file**. They are intentionally presented for the compiler to reject, and must not be merged into `FlowDemo.java` if you want the section 9 example to remain runnable.

| File | Error scenario | Primary Java 17 javac diagnostic |
|---|---|---|
| `MissingReturn.java` | `int` method only returns when `x > 0` | `missing return statement` |
| `WhileFalse.java` | Statements inside `while (false)` | `unreachable statement` |
| `BreakOutside.java` | `break;` outside loop/switch | `break outside switch or loop` |
| `ContinueSwitch.java` | `continue;` in switch without an enclosing loop | `continue outside of loop` |
| `SwitchIncompleteReturn.java` | Switch statement missing branch/return for some values | `missing return statement` |
| `SwitchExpressionMissing.java` | A block arm of a switch expression does not `yield` a value | `switch rule completes without providing a value` |
| `WrongReturnType.java` | `int` method returns `String` | `incompatible types: String cannot be converted to int` |
| `LabelContinueNonLoop.java` | `continue label;` targets a labeled block that is not a loop | `not a loop label` |

The compile-error results listed in the table were verified with classes matching the exact contents described. Depending on the JDK version, caret position, error count, and formatting details may differ, but the corresponding semantic cause remains unchanged.

### 10.1. Distinguishing unreachable errors and missing return errors

Two easily confused errors:

~~~java
class UnreachableConcrete {
    void bad() {
        throw new IllegalStateException();
        System.out.println("unreachable");
    }
}
~~~

The command `javac --release 17 UnreachableConcrete.java` reports `unreachable statement`: the `println` statement cannot be reached according to block structure.

~~~java
class MissingReturn {
    static int sign(int x) {
        if (x > 0) return 1;
    }
}
~~~

The command `javac --release 17 MissingReturn.java` reports `missing return statement`: there is no unreachable statement; the issue is that **a path passes past the end of the `int` method body**.

The distinction:

- **Unreachable:** a code position exists that cannot be reached according to static analysis rules.
- **Missing return:** the body of a value-returning method can complete normally without `return` or a valid abrupt completion.
- **Incorrect return type:** `return` is present, yet the expression cannot validly convert to the declared type.
- **Invalid control target:** `break`/`continue` is present, yet the structure does not allow the transfer target.

Fix errors by identifying **the path graph** and the responsibility of each branch, rather than adding `return null;`, `break;`, or random casts.

## 11. Easily overlooked situations

### 11.1. Return in constructors

Constructors declare no return type and can use `return;` (without an expression) to finish early. Constructors **cannot execute `return value;`**. Unlike `int` methods, constructors are allowed to complete normally: at that point, the object finishes initialization per language rules.

~~~java
class State {
    State(boolean skip) {
        if (skip) return;
        System.out.println("initialize");
    }
}
~~~

This is a valid illustrative class; a separate main method is needed to run it. In practice, be careful with early `return` paths in constructors because they can leave object state not set up as intended.

### 11.2. continue is not the same as break

In a loop:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

When run inside a valid method, the output is `0` and `2` (each value on one line). `continue` skips the rest of iteration `i == 1`, then proceeds to the update step of `for`. If `continue` is replaced with `break`, the loop terminates when `i == 1`, so only `0` is printed.

### 11.3. Switch types and control branches

In a switch statement with colon labels, a `case` missing `break` can fall through into the code of the subsequent `case` if structure permits. With a switch expression, the result must follow expression rules; an arm block must not complete normally without supplying a value.

Java 17 also checks duplicate `case` labels, compatibility of labels with the selector, accessibility, declaration scope, and other constraints. A switch error can be a type or label error even before reachability/return checking.

### 11.4. The compiler does not replace runtime testing

A method with complete returns can still behave incorrectly at runtime, such as a loop handling missing cases, returning a wrong value, or throwing an unexpected exception. A loop considered reachable also does not guarantee it terminates. Combine the compiler's **static checks** with unit tests of conditional branches and boundary tests such as empty arrays, negative inputs, `null`, and parse failures.

## 12. How to self-check a method before compiling

Sketch control flow just enough to inspect:

~~~text
                 [Entry]
                    |
               [Condition?]
                /        \
             true        false
              |            |
         [return 1]     [return 0]
              \            /
               [Caller resumes]
~~~

For a method with a return type:

1. Mark every **return/throw** point.
2. For each `if`, inspect the true path, false path, and the point after `if`.
3. For `switch`, inspect all selector values not matching cases, `default`, fall-through, or switch expressions.
4. For loops, distinguish constant `true`/`false` conditions, `break` possibilities, and the fact that a loop may not run.
5. For `try/catch/finally`, inspect all exit paths and whether `finally` alters completion outcomes.
6. For `break`/`continue`, identify the target clearly inside enclosing constructs; `continue label` must target a loop.
7. Look for statements placed after a segment that cannot complete normally; check according to reachability rules, avoiding reasoning solely by runtime intuition.
8. Ensure no path **falls off the end of a value-returning method body**; if one does, fix the branch design or return a valid value.

If still unsure, create a separate minimal class and compile with `javac --release 17 -encoding UTF-8`. This isolates reachability, missing return, and invalid control-target errors from other issues in a large project.

## 13. Guided verification exercises

**Exercise 1:** Predict the compilation result of `if(false) { System.out.println("x"); }` and `while(false) { System.out.println("x"); }`. Then run the compiler. Explain why the JLS has distinct rules for the two constructs.

**Exercise 2:** Will an `int` method containing `if (true) return 1;` with no other `return` compile? Verify; hint: the rule for whether `if-then` can complete normally is not equivalent to compiler optimization.

**Exercise 3:** With a `while(true)`, add a `break` reachable according to reachability rules. Insert `return 5;` after the loop and explain why it is valid. Try removing `break`, and see what the compiler reports while keeping `return 5;` afterward.

**Exercise 4:** Write a method `int score(String level)` using a switch expression with `case "A"`, `case "B"`, and `default`. Then try writing `default -> { int x = 0; }` without `yield`; observe the error.

**Exercise 5:** Write two nested loops and test `break;`, `break outer;`, `continue;`, `continue outer;`. Predict which iteration continues and which statements remain reachable. Finally try `continue` to a label of a non-loop block to observe the compiler error.

**Exercise 6:** Write a method with `return` inside `try` and a `finally` that only logs; predict the output order. Try `return` inside `finally` in a small separate program, then explain why that construct can lose error info/return values.

Distinguish four layers of conclusions when reading a Java program: **valid syntax**, **valid expression types**, **valid compile-time control flow**, and **runtime behavior matching requirements**. `javac` strictly checks the first three layers according to language rules; the last layer still requires modeling, experimentation, and real testing.