# Normal or Abrupt Completion Due to Exceptions — Java 17+

When Java **evaluates an expression**, the evaluation can either:

- **Complete normally**: the expression finishes evaluating; if the expression produces a value, that value is ready for use in an enclosing expression, assignment, argument, or statement.
- **Complete abruptly**: part of the evaluation fails—for example, throwing an **exception**. The expression **does not complete along the normal path**; dependent subsequent steps are skipped and control transfers to an appropriate exception handler.

~~~java
int sum = 2 + 3;    // Normal: sum receives 5.

// int bad = 10 / 0; // At runtime: ArithmeticException.
// No normal int result to assign to bad.
~~~

In Java, an invocation returning `void` can also **complete normally** even though it does not produce a value to add or assign. Therefore, do not equate "normal" with "always returning an object or a number."

**Core focus:** when a sub-expression throws an exception, evaluation of the larger expression stops; side effects that **already occurred before the error** are not automatically rolled back.

## 1. Two Outcomes of Expression Evaluation

| Situation | How does it complete? | Consequence |
| --- | --- | --- |
| `4 + 5` | Normally | Yields `int 9` |
| `"Java".length()` | Normally | Yields `int 4` |
| `System.out.println("Hi")` | Normally if printing succeeds | `void` call provides no value that can be added |
| `10 / 0` with `int` operands | Abruptly | Throws `ArithmeticException` |
| `((String) null).length()` | Abruptly | Throws `NullPointerException` |
| `array[99]` if array is too short | Abruptly | Throws `ArrayIndexOutOfBoundsException` |
| `Integer.parseInt("abc")` | Abruptly | Throws `NumberFormatException` |
| `false && risky()` | Normally with `false` | `risky()` **is not called** |
| `true ? 1 : riskyInt()` | Normally with `1` | Unselected branch **is not evaluated** |

An exception **thrown** at one point searches for a matching `catch` block up the call stack. If none handles it, the exception can terminate the running thread. A `catch` that handles the error **does not make Java jump back to finish the interrupted expression**; the program continues from a valid position **after the handling construct**.

## 2. Propagation Rules from Sub-Expressions

Ordinary operands and arguments are evaluated **from left to right**. If a sub-expression throws an exception:

1. Sub-expressions **already completed earlier** remain evaluated; state changes prior to the error persist unless the application provides its own undo mechanism.
2. Sub-expressions **later in line whose turn has not come** will not be evaluated within that same calculation or invocation.
3. The entire enclosing expression **completes abruptly**, returning no normal value to an outer assignment or invocation.
4. A matching `catch` can handle the error and allow the program to continue at a statement after `try/catch`.

Example:

~~~java
int result = left() + fail() + right();
~~~

If `left()` returns a normal value and then `fail()` throws an exception, `right()` **does not run** and the assignment to `result` does not complete. If `left()` already wrote a log or incremented a counter, that change remains.

Flow diagram:

~~~text
Evaluate left() ----> Evaluate fail() ----> Evaluate right()
       |                     |
    succeeds          throws exception
                             |
                             v
                  Skip right() and assignment
                             |
                             v
                   Search for matching catch
~~~

The diagram illustrates only a failure branch; if `fail()` succeeds, evaluation proceeds to `right()`.

## 3. Standalone Runnable Java 17+ Demo

Create a UTF-8 file named **`ExpressionCompletionDemo.java`**:

~~~java
public class ExpressionCompletionDemo {
    static int mark(String label, int value) {
        System.out.println("eval=" + label);
        return value;
    }

    static int fail(String label) {
        System.out.println("eval=" + label);
        throw new IllegalStateException("boom-" + label);
    }

    static int combine(int first, int second, int third) {
        System.out.println("combine=called");
        return first + second + third;
    }

    static boolean check(String label, boolean value) {
        System.out.println("eval=" + label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("== normal ==");
        int normal = mark("left", 2) + mark("right", 3);
        System.out.println("normal=" + normal);

        System.out.println("== abrupt operand ==");
        try {
            int unused = mark("before", 1)
                    + fail("middle")
                    + mark("after", 9);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== abrupt argument ==");
        try {
            int unused = combine(
                    mark("arg-1", 10),
                    fail("arg-2"),
                    mark("arg-3", 30));
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("argumentCaught=" + ex.getMessage());
        }

        System.out.println("== arithmetic ==");
        try {
            int quotient = mark("numerator", 10)
                    / mark("denominator", 0);
            System.out.println("unexpected=" + quotient);
        } catch (ArithmeticException ex) {
            System.out.println("divisionError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== references ==");
        String text = null;
        try {
            int size = text.length();
            System.out.println("unexpected=" + size);
        } catch (NullPointerException ex) {
            System.out.println("nullError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== arrays ==");
        int[] values = {7, 8};
        try {
            int element = values[mark("bad-index", 3)];
            System.out.println("unexpected=" + element);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("arrayError="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("== skip evaluation ==");
        boolean andResult = false && check("skip-and", true);
        boolean orResult = true || check("skip-or", false);
        int selected = true ? mark("selected", 7)
                : fail("skip-branch");
        System.out.println("and=" + andResult);
        System.out.println("or=" + orResult);
        System.out.println("selected=" + selected);

        System.out.println("== prior side effect ==");
        int counter = 0;
        try {
            int unused = mark("counter-start", counter++)
                    + fail("counter-fail");
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("sideEffectCaught="
                    + ex.getMessage());
        }
        System.out.println("counterAfter=" + counter);

        System.out.println("== catch and finally ==");
        int recovered;
        try {
            recovered = mark("recover-left", 4)
                    + fail("recover-right");
        } catch (IllegalStateException ex) {
            recovered = 99;
            System.out.println("recoveredFrom=" + ex.getMessage());
        } finally {
            System.out.println("finally=cleanup");
        }
        System.out.println("recoveredValue=" + recovered);
        System.out.println("program=continued");
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the folder containing the file, using **JDK 17 or newer**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ExpressionCompletionDemo.java
java ExpressionCompletionDemo
~~~

**Exact expected output** of `java ExpressionCompletionDemo` (excluding the output of the `-version` commands):

~~~text
== normal ==
eval=left
eval=right
normal=5
== abrupt operand ==
eval=before
eval=middle
caught=boom-middle
== abrupt argument ==
eval=arg-1
eval=arg-2
argumentCaught=boom-arg-2
== arithmetic ==
eval=numerator
eval=denominator
divisionError=ArithmeticException
== references ==
nullError=NullPointerException
== arrays ==
eval=bad-index
arrayError=ArrayIndexOutOfBoundsException
== skip evaluation ==
eval=selected
and=false
or=true
selected=7
== prior side effect ==
eval=counter-start
eval=counter-fail
sideEffectCaught=boom-counter-fail
counterAfter=1
== catch and finally ==
eval=recover-left
eval=recover-right
recoveredFrom=boom-recover-right
finally=cleanup
recoveredValue=99
program=continued
~~~

Lines prefixed with `unexpected=` **do not appear** because the corresponding expression threw an exception before completing normally.

## 4. Reading the Demo Output

### 4.1. Normal Completion

~~~java
int normal = mark("left", 2) + mark("right", 3);
~~~

`mark("left", 2)` and `mark("right", 3)` run left → right, both returning normal `int`s. Addition receives 2 and 3, completes with 5, and the assignment to `normal` succeeds.

### 4.2. Sub-Expression Throws Exception: Later Parts Do Not Run

~~~java
mark("before", 1) + fail("middle") + mark("after", 9)
~~~

`mark("before", 1)` ran. `fail("middle")` logged and then threw `IllegalStateException`. Therefore:

- `mark("after", 9)` **is not called**.
- The outer addition **has no normal value**.
- `catch (IllegalStateException ex)` catches the exception and prints `boom-middle`.

The expression inside the `try` block does not resume in place after the exception is handled.

### 4.3. Argument Fails: Target Method Is Never Called

~~~java
combine(mark("arg-1", 10), fail("arg-2"), mark("arg-3", 30))
~~~

The first argument runs; the second argument throws an exception. The third argument **is not evaluated**, and the `combine` method itself **is not called**; hence there is no `combine=called` line.

A method taking three parameters does not mean Java evaluates them concurrently or evaluates all of them regardless of errors.

### 4.4. Exceptions from Operations

`int` division by integer 0 throws `ArithmeticException`. Both operands in:

~~~java
mark("numerator", 10) / mark("denominator", 0)
~~~

are evaluated before division detects the zero divisor. Thus both `eval=...` lines appear, yet there is no `quotient` result.

**Important difference:** `double` divided by `0.0` follows floating-point rules and can produce `Infinity` or `NaN` instead of `ArithmeticException`. Do not mechanically apply integer division-by-zero rules to all numeric types.

### 4.5. Null and Array Access

Calling `text.length()` when `text == null` throws `NullPointerException`. In `values[mark("bad-index", 3)]`, index 3 finishes evaluating and then the array access throws `ArrayIndexOutOfBoundsException` because the array has only two elements, with valid indices 0 and 1.

The exception class name in logs helps distinguish **the kind of failure**, though not every exception's full message is identical across JDKs. The demo prints only `getClass().getSimpleName()` to keep stdout stable.

### 4.6. Skipped Evaluation Is Normal Semantics, Not an Exception

~~~java
boolean a = false && check("skip-and", true);
boolean b = true || check("skip-or", false);
int c = true ? mark("selected", 7) : fail("skip-branch");
~~~

In the two boolean expressions, the left side already determines the result, so the right side is not called. With the ternary operator, only the chosen branch is evaluated. All of these expressions **complete normally**, even though part of the syntax is not evaluated.

Therefore, **"a sub-expression did not run" does not mean "an exception occurred."**

### 4.7. Side Effects Before an Error Are Not Automatically Rolled Back

~~~java
int counter = 0;
int value = mark("counter-start", counter++)
        + fail("counter-fail");
~~~

`counter++` returns the old value and increments `counter` to 1 before `fail(...)` throws an exception. `value` does not receive a normal assignment result, yet `counter` remains 1 after the exception is caught.

This is not a transaction. Restoring state requires explicit handling/undo design; `try/catch` by itself does not restore prior variables or I/O operations.

### 4.8. `catch` and `finally` Have Different Roles

In the last part of the demo, the computation for `recovered` completes abruptly, yet `catch` catches the exception and **actively assigns a fallback value of 99**. The `finally` block prints the cleanup line and then the program continues.

- `catch` handles matching exception types; it does not automatically synthesize a result for the broken expression.
- `finally` normally executes when leaving `try/catch`, even if an exception occurred, though there are cases where the JVM/process cannot finish cleanup (such as forced termination).
- If `finally` itself throws a new exception, that exception can override how the block completes. Avoid `return` or throwing new exceptions inside `finally` unless genuinely intentional.

In application code, prefer **try-with-resources** to close `AutoCloseable` resources instead of manually managing multiple complex exit paths unnecessarily.

## 5. One Failing Part Affects the Entire Enclosing Expression

Example:

~~~java
int total = 5 + Integer.parseInt("abc") * 2;
~~~

The expression is grouped as `5 + (parseInt("abc") * 2)`. When `parseInt` throws `NumberFormatException`:

1. The invocation does not return a normal `int`.
2. Multiplication lacks enough operands to compute a value.
3. Addition receives no value for its right operand.
4. Assignment to `total` does not complete.
5. Control transfers according to exception-handling rules.

If this is user-input processing, catch `NumberFormatException` where you can report an error, request re-entry, or apply a **specified** fallback value rather than silently guessing a replacement.

## 6. Checked and Unchecked Exceptions

The **checked / unchecked** distinction concerns compile-time **declaration or handling requirements**; it does not change the rule that an expression throwing an exception completes abruptly.

| Kind | Examples | What does the compiler require? |
| --- | --- | --- |
| Checked exception | `java.io.IOException` | Normally must be caught with `catch` or declared with `throws` |
| Unchecked exception | `ArithmeticException`, `NullPointerException`, `NumberFormatException` | Not required to be caught or declared with `throws` |
| Serious error under `Error` | `OutOfMemoryError` | Also unchecked; generally should not be handled like an input error |

An exception can arise deep inside a method call and propagate out through enclosing expressions. Whether checked or unchecked, if unhandled appropriately, the normal execution path cannot finish as expected.

## 7. Distinguish Abrupt Expression Completion from Statements

An **expression** can complete abruptly due to an exception. Java **statements** also have other forms of abrupt completion such as `return`, `break`, or `continue` in appropriate contexts.

~~~java
static int example(boolean stop) {
    if (stop) {
        return 1; // Method exits at return.
    }
    return 2;
}
~~~

`return` in the example is a **control-flow statement**, not a numeric operator or an exception value. Thus, when specifically discussing **expressions throwing exceptions**, avoid conflating `return` with "an exception thrown by addition."

## 8. Writing More Maintainable Code

When an expression contains multiple calls that can fail, it is often better to separate steps to clearly define failure points and fallback policies:

~~~java
String text = "42";
int parsed;
try {
    parsed = Integer.parseInt(text);
} catch (NumberFormatException ex) {
    parsed = 0; // Use only if the problem allows a fallback of 0.
}
int total = parsed * 2;
~~~

This makes clear:

- Which input needs to be parsed.
- Which exception type can occur and is caught.
- Whether a fallback value is actually permitted.
- Multiplication begins **only after** the parse step has been resolved.

There is no need to catch every `RuntimeException` or `Exception` unconditionally. Catch **errors that can be handled meaningfully at the right business boundary**, so programming bugs are not hidden.

## 9. Self-Check Exercises

1. **Normal:** How does `int n = 3 * (2 + 1);` complete?  
   *Answer:* Normally, `n = 9`.
2. **Early stop:** In `first() + fail() + last()`, if `fail()` throws an exception, does `last()` run?  
   *Answer:* No; the entire addition completes abruptly.
3. **Arguments:** If the second argument of a three-argument call throws an exception, do the third argument and the method body run?  
   *Answer:* No.
4. **Short-circuiting:** `false && risky()` does not call `risky()`; is this abrupt completion?  
   *Answer:* No; the entire expression completes normally with `false`.
5. **State:** `int x = 0;` then evaluate `x++ + fail()`; after catching the exception, what is `x`?  
   *Answer:* `1`, because the increment already occurred before the exception was thrown.
6. **Division by 0:** How do `int x = 10 / 0;` and `double y = 10.0 / 0.0;` differ?  
   *Answer:* The first throws `ArithmeticException`; the second produces positive floating-point infinity per floating-point rules.
7. **`catch`:** Does catching an exception from `Integer.parseInt("abc")` mean the original expression resumes computing?  
   *Answer:* No; a new control-flow path must be chosen (such as re-prompting or assigning a valid fallback).

## Checklist

- [ ] Distinguish **normal** completion from **abrupt completion due to an exception**.
- [ ] When a sub-expression fails, the enclosing expression produces no normal result.
- [ ] Operands/arguments whose turn has not arrived **will not be evaluated** after an exception.
- [ ] Side effects that already happened **do not automatically roll back**.
- [ ] Understand that `&&`, `||`, and `?:` can skip branches **and still complete normally**.
- [ ] Distinguish the responsibilities of `try`, `catch`, and `finally`.
- [ ] Know that checked/unchecked is a compile-time contract issue and does not change exception propagation mechanics.
- [ ] Catch and handle errors where the application can make an accurate decision.

**Conclusion:** Evaluating a Java expression can either **complete with a normal result** or **stop abruptly due to an exception**. When an exception occurs, subsequent steps do not proceed, while prior side effects remain; handling via `catch` is **a new control-flow path**, not "continuing" the broken computation.
