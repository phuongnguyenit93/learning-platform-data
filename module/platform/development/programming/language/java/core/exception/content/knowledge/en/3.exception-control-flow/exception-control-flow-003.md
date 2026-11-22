# Stopping Incomplete Expressions or Statements When an Exception Occurs

> Java Core – Exception · Group: Control Flow · Standalone runnable example with Java 17+.

## 1. What stops when an exception occurs?

Java evaluates expressions to produce values, perform assignments, or invoke methods; at the same time, it executes statements following the control flow. If a step throws an exception, that step **does not complete normally**. Any remaining steps that depend on its completion are skipped. Java transfers control to a matching exception handler, or propagates the error out to the calling method.

The Java specification calls this *abrupt completion*, in contrast to *normal completion*.

Hypothetical example:

```java
int result = first() + second() + third();
```

If `first()` completes but `second()` throws an exception:

1. `first()` **has already run**; any side effects it produced still remain.
2. `second()` **started**, but did not return a normal result.
3. `third()` **is not called** under normal evaluation flow.
4. There is no complete sum to assign to `result`; the assignment statement is incomplete.
5. If a matching `catch` branch exists, the code in that branch is executed. Java does not automatically go back to execute `third()` after handling the exception.

The key is distinguishing **the work that has not been done** from **the side effects that already occurred before the failure point**. An exception does not automatically undo side effects.

## 2. Language basis: abrupt completion of expressions and statements

According to [Java Language Specification §15.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6), if the evaluation of an enclosing expression depends on a subexpression, and that subexpression completes abruptly, the enclosing expression also completes abruptly for the same reason. Subsequent normal evaluation steps are not executed.

JLS §15.7 specifies the evaluation order of operands and arguments. In the corresponding cases, Java evaluates from left to right. If a step on the left throws an exception, the dependent parts that follow are not evaluated.

Statements can also complete abruptly. JLS §14.1 lists reasons such as throwing an exception (`throw`), `return`, `break`, `continue`, and `yield` where applicable. **Not every abrupt completion is an exception**: for example, `return` is a control transfer defined by the language construct, not automatically throwing a `Throwable` object. In this article, we examine the exception case specifically.

```text
Evaluate expression / execute statement
               |
           Current step
            /      \
       Normal    Throws exception
        |               |
        v               v
    Next step      Stop remaining
   if selected    normal evaluation path
                        |
                        v
                  Leave related scope /
                  run cleanup per rules
                        |
                        v
                  Matching catch or
                  propagate exception to caller
```

This diagram shows the general flow. `finally` and `try-with-resources` have their own execution rules when leaving a scope. Some branch selections such as `&&`, `||`, and `?:` intentionally skip operands when evaluation is unnecessary, **even when no exception occurs**.

## 3. Common places interrupted mid-execution

### 3.1. Operands of an operation

```java
int total = calculateLeft() + fail() + calculateRight();
```

When the call to `fail()` throws an exception, `calculateRight()` has not run yet; the result of the entire addition is incomplete. If `calculateLeft()` already incremented a counter or wrote a log, that side effect has still occurred.

Note that evaluation order is different from operator precedence. Parentheses and precedence determine the structure of an expression, while the JLS determines the order in which parts of that structure are evaluated. Do not assume that every expression written on the right is always executed.

For integer division, the operands are evaluated first before the division occurs:

```java
int result = left() / right();
```

If both `left()` and `right()` return normally and `right()` returns 0, the division throws `ArithmeticException` after both calls have run. If `left()` threw an error first, `right()` has not run. Floating-point `double` division by `0.0` follows floating-point rules, typically yielding Infinity or NaN, so do not use it in place of an integer division example.

### 3.2. Argument list of a method or constructor

```java
send(readId(), parseAmount(), auditCode());
```

If `parseAmount()` throws an exception, `readId()` may already have completed, `auditCode()` has not run, and the body of `send` is not executed. Java evaluates argument expressions from left to right; one argument completing abruptly prevents the rest from running.

For constructors, argument expressions also follow left-to-right order. For method invocations on an object and field/array accesses, you need to consult the specific evaluation rules if you want to know the exact timing of `null` checks and related side effects.

### 3.3. Incomplete assignment

Suppose:

```java
int amount = 100;
int[] effects = {0};

try {
    amount = ++effects[0] + fail();
} catch (IllegalStateException ex) {
    System.out.println("caught");
}
```

This is an **illustrative snippet**, assuming `fail()` is defined to return `int` on success but throws `IllegalStateException` in this test case. `++effects[0]` increments the array element from 0 to 1 before the error. The right-hand side of the assignment does not complete, so `amount` remains 100. **The value of `effects[0]` has changed**, because it is a side effect of a subexpression that already ran.

An incomplete assignment is not equivalent to rolling back the entire expression or transaction.

### 3.4. Array access, casting, and dereferencing

```java
int result = numbers[index()] + bonus();
```

Suppose `numbers` is a single-element array and `index()` returns 5. `index()` may have produced a side effect; the element access throws `ArrayIndexOutOfBoundsException`; `bonus()` has not run.

Similarly, `ClassCastException`, `NullPointerException`, or an exception thrown during an API call can cause the enclosing expression to stop. However, the order of evaluating the target expression, arguments, and runtime checks follows precise rules; you should not make a blanket statement that whenever an NPE occurs, none of the arguments were ever evaluated.

### 3.5. Short-circuiting vs. exceptions

```java
boolean safe = false && mayThrow();
int chosen = true ? 7 : mightFail();
```

In these two lines, the right-hand side of `&&` and the unselected branch of `?:` do not run because of *conditional evaluation* rules, even though **no error occurred**.

With the boolean operators `&` or `|`, Java still evaluates the right-hand side when the left-hand side completes normally. However, an actual exception from the left-hand side still terminates the enclosing expression, preventing the right-hand side from being evaluated.

## 4. Runnable program: tracing what ran and what was skipped

Save the full source code below into a file named **`AbruptCompletionDemo.java`**. No external libraries, input files, or runtime arguments are needed.

```java
public class AbruptCompletionDemo {

    private static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    private static int explode(String label) {
        System.out.println(label);
        throw new IllegalStateException(label);
    }

    private static boolean failBoolean() {
        System.out.println("never-run");
        throw new IllegalStateException("boolean failure");
    }

    private static void accept3(int a, int b, int c) {
        System.out.println("accept3 called");
    }

    public static void main(String[] args) {
        binaryExpression();
        argumentList();
        unfinishedAssignment();
        arrayAccess();
        interruptedStatements();
        finallyOnUnwind();
        conditionalEvaluation();
    }

    private static void binaryExpression() {
        System.out.println("== binary ==");
        try {
            int result = trace("left", 2)
                    + explode("middle")
                    + trace("right", 4);
            System.out.println("result=" + result);
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void argumentList() {
        System.out.println("== arguments ==");
        try {
            accept3(
                    trace("arg1", 10),
                    explode("arg2"),
                    trace("arg3", 30));
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void unfinishedAssignment() {
        System.out.println("== assignment ==");
        int balance = 100;
        int[] effects = {0};

        try {
            balance = ++effects[0] + explode("assignment-failure");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }

        System.out.println("balance=" + balance
                + ", effects=" + effects[0]);
    }

    private static void arrayAccess() {
        System.out.println("== array ==");
        int[] scores = {10};

        try {
            int result = scores[trace("index", 4)]
                    + trace("rhs", 20);
            System.out.println("result=" + result);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("catch=ArrayIndexOutOfBoundsException");
        }
    }

    private static void interruptedStatements() {
        System.out.println("== statements ==");
        try {
            System.out.println("before");
            int value = explode("fail-statement");
            System.out.println("after");
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
        System.out.println("resume-after-catch");
    }

    private static void finallyOnUnwind() {
        System.out.println("== finally ==");
        try {
            try {
                trace("inside", 1);
                explode("cleanup-failure");
            } finally {
                System.out.println("finally");
            }
        } catch (IllegalStateException ex) {
            System.out.println("catch=" + ex.getMessage());
        }
    }

    private static void conditionalEvaluation() {
        System.out.println("== conditional ==");
        boolean ok = false && failBoolean();
        System.out.println("false && failBoolean()=" + ok);

        int chosen = true
                ? trace("selected", 7)
                : explode("unused");
        System.out.println("chosen=" + chosen);
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac -encoding UTF-8 AbruptCompletionDemo.java
java AbruptCompletionDemo
```

**Exact** stdout:

```text
== binary ==
left
middle
catch=middle
== arguments ==
arg1
arg2
catch=arg2
== assignment ==
assignment-failure
catch=assignment-failure
balance=100, effects=1
== array ==
index
catch=ArrayIndexOutOfBoundsException
== statements ==
before
fail-statement
catch=fail-statement
resume-after-catch
== finally ==
inside
cleanup-failure
finally
catch=cleanup-failure
== conditional ==
false && failBoolean()=false
selected
chosen=7
```

The strings that are **not printed** are also evidence: `right`, `arg3`, `accept3 called`, `rhs`, `after`, `never-run`, and `unused`. The compiler does not need to know in advance that `explode` will definitely throw an exception; statically the method has return type `int`, yet at runtime it throws before producing a value.

## 5. Analysis of each scenario

### Mid-calculation operation: `binaryExpression`

`trace("left", 2)` prints `left` and completes. `explode("middle")` prints `middle` and then throws `IllegalStateException`. A value for the next addition operand does not exist, so `trace("right", 4)` does not run. The statement printing `result` does not run. The `catch` branch prints `catch=middle`.

### Second argument fails: `argumentList`

`trace("arg1", 10)` runs. `explode("arg2")` throws an error; `trace("arg3", 30)` has not run. Therefore `accept3 called` is not printed: the body of `accept3` never started.

### Side effect already completed: `unfinishedAssignment`

`++effects[0]` already changed the value from 0 to 1. When `explode("assignment-failure")` throws an error, the outermost assignment does not complete, so `balance` remains 100. Thus the final line prints `balance=100, effects=1`. **The two variables have different post-error states** even though they appear in the same statement.

### Out-of-bounds access: `arrayAccess`

`trace("index", 4)` prints `index`, after which Java detects that index 4 exceeds the single-element array. `ArrayIndexOutOfBoundsException` prevents the addition with `trace("rhs", 20)` from executing. The catch branch prints a fixed error type name, independent of how the JVM formats the message.

### Next statement does not run: `interruptedStatements`

The program prints `before`. The initializer expression for `value` calls `explode("fail-statement")` and throws an exception. The `after` line **is not executed**. After the catch prints the error message, the statement after the `try/catch` structure runs and prints `resume-after-catch`. Java does not resume from the middle of the `value` initialization statement.

### Cleanup on control transfer: `finallyOnUnwind`

`explode("cleanup-failure")` causes the `try` body to complete abruptly. Before the outer handler receives the error, the inner `finally` block runs and prints `finally`. Because this block completes normally, the original exception continues to the outer catch, which prints `catch=cleanup-failure`. Running `finally` does not mean returning to the interrupted step.

### Unselected branch not evaluated: `conditionalEvaluation`

`false && failBoolean()` does not call `failBoolean()`, so it does not throw an exception. The conditional operator selects `trace("selected", 7)` and does not run `explode("unused")`. This is skipping due to normal branch selection, which should be distinguished from stopping due to an exception.

## 6. If there is no local catch, which statement runs next?

Consider the flow:

```text
main()
  |
  +-- process()
        |
        +-- stepA()   → succeeds, side effects remain
        |
        +-- stepB()   → throws exception
        |
        +-- stepC()   → does not run
  |
  +-- code after process() call inside try → does not run
  |
  +-- matching catch → handles error
  |
  +-- statement after try/catch → runs if handler completes normally
```

An exception propagates to the calling method when it is not handled locally. It does not automatically terminate the entire JVM: a handler in an outer caller may handle it and continue at a new location. If there is no handler, the exception may reach the thread's uncaught-exception handler.

Additional comparison:

| Origin point | Incomplete step | Resume point when handled |
| --- | --- | --- |
| Variable initialization `int x = bad();` | Initialization value and subsequent statements in the exited block | Inside the matching `catch` |
| Method arguments `run(a(), bad(), c())` | `c()` and the body of `run` | `catch` of the calling scope |
| Condition `if (badBoolean())` | Neither true nor false branch selected | Matching `catch` |
| Condition `while (badBoolean())` | Condition evaluation pass does not complete | Outer or matching enclosing `catch` |
| Return value `return bad();` | No normal return value produced | Handler found across scopes |
| Reading records with catch **inside** loop | Only the rest of processing the failing record | Code in handler, then next loop iteration logic |
| Exception escapes loop, catch **outside** | Loop does not automatically resume | Handler outside the loop |

If you want to retry after an error, the application must **explicitly write a loop/retry** and account for the side effects of the previous attempt. Catching an error alone does not re-execute anything.

## 7. Why can `finally` and resources still run?

According to JLS §14.20, when leaving a `try` block because of an exception, the related handling parts are applied according to these rules:

- If a matching `catch` is found, the catch block is executed instead of continuing the try body.
- The associated `finally` block is executed when leaving the construct in the situations specified by the language. If `finally` completes normally, the previous reason for abrupt completion can continue to propagate.
- If `finally` completes abruptly due to another exception or `return`, the previous control result may be replaced. Therefore, avoid `throw` and `return` inside `finally`.
- `try-with-resources` closes resources automatically. If the body throws an error and `close()` also throws an error, the exception from the body takes precedence and the close error usually appears in `getSuppressed()` of the primary exception.

These operations are **separate cleanup paths**, not a continuation of evaluating the skipped operands or statements. Abrupt JVM termination can prevent cleanup from running as usual; do not interpret `finally` as an absolute guarantee in all circumstances.

## 8. What happens to state and transactions?

Exceptions change control flow; they **do not create an automatic rollback**. From the `unfinishedAssignment` example, we saw `effects[0]` remained 1. The same principle applies to many side effects:

- Variable assignments, field mutations, and collection updates completed before the error.
- Partial content written to a file.
- An HTTP request sent or an event emitted to another system.
- Database changes, depending on the actual transaction state and rollback mechanism.

To achieve atomicity, you must design explicitly: validate before writing, use transactions, staging, compensating actions, or per-unit error handling. Do not try to hide failures with a `catch (Exception)`.

Example of a complex expression that is often hard to analyze:

```java
save(updateCounter() + parseInput() + recordAudit());
```

The snippet above is **illustrative, non-standalone code** because the methods are not defined. When `parseInput()` fails, `updateCounter()` may already have updated state, while `recordAudit()` and `save()` have not run. If business rules allow, you can redesign it to validate input before causing side effects:

```java
int parsed = parseInput();
int counted = updateCounter();
int audit = recordAudit();
save(parsed + counted + audit);
```

This is a **deliberate reordering decision**; do not change the order of real API calls without checking contracts and business requirements.

## 9. Output prediction exercise

The snippet below is placed inside the body of a valid Java method. It accurately illustrates an interrupted assignment statement where a prefix increment has already completed.

```java
int x = 4;
try {
    x = ++x + Integer.parseInt("oops");
    System.out.println("done");
} catch (NumberFormatException ex) {
    System.out.println("caught");
}
System.out.println("x=" + x);
```

Analysis: `++x` changes `x` to 5, then `Integer.parseInt("oops")` throws `NumberFormatException`. The outer addition/assignment has no completed value, so `x` is not overwritten with the sum. The `done` line does not run; the catch prints the message and the following line prints the current state.

Stdout:

```text
caught
x=5
```

**Check questions:**

1. If `bad()` is the second argument in a three-argument call and it throws an error, which argument(s) may have run, which have not, and is the target method body called?
2. Why did `++effects[0]` take effect while the `balance = ...` assignment did not complete?
3. If there is no catch in the current method, does Java run the statement immediately after the throw site before exiting the method?
4. Does `finally` running when an exception occurs mean the entire original expression resumed evaluation?
5. How does `false && mayThrow()` differ from an exception occurring in the middle of an addition?
6. Why should you not assume that `getMessage()` of a runtime exception is always identical across all JDKs?

**Hints:** (1) Arguments to the left that completed earlier may have run; arguments to the right and the method body have not run. (2) Side effects of subexpressions completed before the error still persist. (3) No, the exception propagates to the caller. (4) No, that is cleanup. (5) Short-circuiting is normal completion via branch selection. (6) Messages may depend on implementation/context; test the error type and behavior instead.

## 10. Common misconceptions to avoid

- "Whenever an exception happens, the whole expression hasn't done anything yet." **False:** completed steps and side effects may remain.
- "After catching, Java goes back to evaluate the next operand." **False:** control moves to the handler and then after the handler.
- "Arguments after the failing argument still run because they are inside the same method parentheses." **False** per argument evaluation order.
- "The assignment didn't finish, so every variable on the right-hand side stays unchanged." **False:** side effects may already have occurred.
- "The right-hand side of `&&` didn't run, which means an exception occurred." **False:** normal short-circuiting does not throw an exception.
- "Using `finally` makes the failing operation continue." **False:** it is cleanup when leaving the scope.
- "If you don't catch an exception in a loop, the loop automatically moves to the next record." **False:** the exception can exit the loop completely.
- "Exceptions only apply to `RuntimeException`." **False:** checked exceptions, unchecked exceptions, and `Error` can all halt the execution path.
- "Using `catch (Throwable)` guarantees safety." **False:** it includes serious `Error` types that applications usually cannot recover from.
- "Exceptions automatically roll back databases/files." **False:** rollback depends on separate mechanisms.
- "Java picks evaluation order randomly." **False:** the JLS specifies many evaluation orders that must be followed. Even so, minimize expressions with multiple side effects for maintainability.

## 11. Authoritative references

- [JLS 17 §15.6 – Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6): rules when a subexpression throws an exception.
- [JLS 17 §15.7 – Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): operands, arguments, and evaluation order.
- [JLS 17 §14.1 – Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.1): reasons for abrupt completion of statements.
- [JLS 17 §14.20 – The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): catch, finally, and try-with-resources.
- [JLS 17 §15.12.4 – Runtime Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): how target expressions and arguments of an invocation are evaluated.

**Learning outcome:** When looking at a Java statement that throws an exception, you should be able to identify *the failing step*, *the steps that already ran*, *the steps that were skipped*, *remaining side effects*, *the cleanup path*, and *the resume point after the handler*.
