# Return Values Are Evaluated Before finally Executes in Java

> Java Core – Exception · Section: **The finally Block** · Focuses on the evaluation order of `return` expressions, local variables, object references, and cases where `finally` replaces the control flow. Examples use Java 17+.

## 1. Core Rule

When a Java method executes a `return expression;` statement inside a `try` or `catch` block with an associated `finally` block, the semantic sequence is:

1. **Evaluate the entire `expression`** and obtain value `V`, if the expression completes normally.
2. Record the reason for completing the current flow as **returning value `V`**. The method has not yet transferred control completely back to the caller.
3. **Execute the `finally` blocks that must run** along the exit path of the relevant scopes.
4. If the `finally` blocks complete normally, the caller receives **the value `V` evaluated** in step 1.
5. If `finally` completes abruptly instead—for example, by executing its own `return` or `throw`—the new reason may **replace** the pending return request. In that case, the caller **does not necessarily** receive `V`.

This is specified in the [Java Language Specification 17, Section 14.17 – The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17) and [Section 14.20.2 – Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2).

**Key takeaway:** `finally` runs **before the caller receives the result**, but **after the `return` expression has been evaluated**. Do not confuse “`return` is written before `finally`” with “the method has already exited completely before `finally` runs”.

### Execution Flow Diagram

```text
        Encounter return expression;
                      |
                      v
         Evaluate expression first
                 /         \
       Succeeds             Expression throws E
           |                         |
           v                         v
      Has value V                 No V yet
           |                         |
           +-------------+-----------+
                         |
                         v
                   Run finally
                    /        \
          Completes           Completes abruptly
          normally            (another return/throw)
             |                         |
             v                         v
       Use original             New reason may
       reason: return V         replace original
       or throw E               reason
             |                         |
             v                         v
       Caller receives V        Caller receives another
       or exception E           result / another exception
```

The diagram is a visualization of the language rules, not a requirement that the JVM store the value in a variable named `V` or use a fixed bytecode layout. The compiler may choose different implementation strategies as long as JLS semantics are preserved.

## 2. Minimal Code: Modifying a Variable in finally Does Not Change the Returned Value

Consider a method (the snippet below is **illustrative code inside a class**, not a complete program):

```java
static int example() {
    int number = 10;
    try {
        return number;
    } finally {
        number = 99;
    }
}
```

The value of calling `example()` is **`10`**, not `99`.

Step-by-step analysis:

- When `return number;` is encountered, the variable expression `number` is read; its current primitive `int` value is `10`.
- The method records the request to return `10` and transfers control to the `finally` block.
- The `finally` block assigns the local variable `number = 99`; this change actually happens, but it does not alter the value `10` already computed for the return.
- Since `finally` completes normally, the method finishes returning the recorded value.

The same applies to primitive types such as `boolean`, `long`, `double` and to immutable values such as a reference to a `String` object: **reassigning a local variable** in `finally` does not re-evaluate the earlier `return` expression.

Do not explain this as “`finally` does not perform the assignment”: it **does execute**, only the return value was already computed beforehand.

## 3. Complete Java 17 Program and Verified stdout

Save the file **`FinallyReturnDemo.java`** with the following content. Seven scenarios are separated into methods to compare primitive return values, method-call expressions, object references, returning from `finally`, throwing from `finally`, errors while evaluating the `return` expression, and returning from `catch`.

```java
public class FinallyReturnDemo {
    private static int calculate() {
        System.out.println("evaluate calculate()");
        return 7;
    }

    private static int primitive() {
        int value = 10;
        try {
            System.out.println("try primitive");
            return value + 1;
        } finally {
            value = 99;
            System.out.println("finally primitive value=" + value);
        }
    }

    private static int expression() {
        try {
            return calculate();
        } finally {
            System.out.println("finally expression");
        }
    }

    private static StringBuilder reference() {
        StringBuilder text = new StringBuilder("A");
        try {
            System.out.println("try reference");
            return text;
        } finally {
            text.append("B");
            text = new StringBuilder("C");
            System.out.println("finally reference local=" + text);
        }
    }

    private static int override() {
        try {
            System.out.println("try override");
            return 1;
        } finally {
            System.out.println("finally override");
            return 2; // Compiles, but shadows the return value from try.
        }
    }

    private static int throwFromFinally() {
        try {
            System.out.println("try throw");
            return 3;
        } finally {
            System.out.println("finally throw");
            throw new IllegalStateException("cleanup failed");
        }
    }

    private static int failedExpression() {
        try {
            System.out.println("try parse");
            return Integer.parseInt("bad");
        } finally {
            System.out.println("finally parse");
        }
    }

    private static int returnFromCatch() {
        try {
            throw new IllegalArgumentException("bad input");
        } catch (IllegalArgumentException ex) {
            System.out.println("catch returns");
            return 5;
        } finally {
            System.out.println("finally catch");
        }
    }

    public static void main(String[] args) {
        System.out.println("== primitive ==");
        System.out.println("result=" + primitive());

        System.out.println("== expression ==");
        System.out.println("result=" + expression());

        System.out.println("== reference ==");
        StringBuilder result = reference();
        System.out.println("result=" + result);

        System.out.println("== override ==");
        System.out.println("result=" + override());

        System.out.println("== throw ==");
        try {
            System.out.println("result=" + throwFromFinally());
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== failed expression ==");
        try {
            System.out.println("result=" + failedExpression());
        } catch (NumberFormatException ex) {
            System.out.println("caught=NumberFormatException");
        }

        System.out.println("== catch return ==");
        System.out.println("result=" + returnFromCatch());
    }
}
```

### Compile and Run

Use JDK 17 or newer in the directory containing `FinallyReturnDemo.java`:

```bash
javac --release 17 -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
```

**Exact stdout:**

```text
== primitive ==
try primitive
finally primitive value=99
result=11
== expression ==
evaluate calculate()
finally expression
result=7
== reference ==
try reference
finally reference local=C
result=AB
== override ==
try override
finally override
result=2
== throw ==
try throw
finally throw
caught=cleanup failed
== failed expression ==
try parse
finally parse
caught=NumberFormatException
== catch return ==
catch returns
finally catch
result=5
```

The output above was verified by **compiling with `javac --release 17` and running on a JDK supporting Java 17**. The exception messages are created by the code itself; the program does not depend on how the JVM formats stack traces or the `NumberFormatException` message to produce stdout.

## 4. Detailed Analysis of the Seven Cases

### 4.1. `primitive()`: The Expression Value Is Locked In Before finally

In `primitive()`:

```java
int value = 10;
try {
    System.out.println("try primitive");
    return value + 1;
} finally {
    value = 99;
    System.out.println("finally primitive value=" + value);
}
```

Sequence:

1. Prints `try primitive`.
2. Reads `value == 10` and computes `value + 1 == 11` for the return expression.
3. Enters `finally`, assigns `value = 99`, and prints `finally primitive value=99`.
4. `finally` completes normally; the method returns **`11`**, and the caller prints `result=11`.

If you mistakenly think the method “re-reads the variable `value`” at the end, you would predict `99` — which is wrong. A `return` expression is not automatically re-evaluated after `finally`.

### 4.2. `expression()`: Calls Inside return Execute Before finally

For:

```java
try {
    return calculate();
} finally {
    System.out.println("finally expression");
}
```

The call to `calculate()` happens immediately when evaluating the `return` expression; it prints `evaluate calculate()` and returns `7`. **After `7` has been obtained**, Java runs `finally` and prints `finally expression`. Only then does the caller receive `7`.

Therefore, stdout cannot be reversed to `finally expression` before `evaluate calculate()`. The same holds if the `return` expression contains arithmetic operations, array accesses, or other calls: they are evaluated according to expression evaluation rules before `finally` runs, provided evaluation completes normally.

### 4.3. `reference()`: The Reference Is Locked In, While Object State Can Still Change

This is the case that most often causes major misunderstandings:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text.append("B");
    text = new StringBuilder("C");
}
```

What is returned is **the reference value pointing to the original `StringBuilder` object**, not an immutable snapshot of the entire object. What happens:

1. The variable `text` points to the `StringBuilder("A")` object.
2. `return text;` evaluates and retains **that reference** to return.
3. In `finally`, `text.append("B")` mutates **the very object selected for return** from content `A` to `AB`.
4. Afterward, `text = new StringBuilder("C")` only reassigns the **local variable** `text` to a new object; the reference value chosen in step 2 does not change.
5. The caller receives the original object, which now has content `AB`.

Thus, the program prints `finally reference local=C` in `finally`, while the caller prints `result=AB`. There is no contradiction: **the reference value** was chosen before `finally`, whereas **the state of the object that the reference points to** can be modified afterward.

| Operation in `finally` | Changes the reference value selected for `return`? | Can the caller observe the effect? |
| --- | --- | --- |
| `text.append("B")` | No | **Yes**, because the returned object was mutated |
| `text = new StringBuilder("C")` | No | **No**, if only the local variable is reassigned |
| `text = null` | No | Does not turn the return value into `null` |
| Modifying a field/array of the returned object | No | Yes, if that state resides on the object the caller receives |

Hence, the statement “the return value does not change in `finally`” should be phrased carefully: for a **reference to a mutable object**, the *reference* does not change, but the *object* can still change.

### 4.4. `override()`: Another return in finally Overrides the Previous Return Intent

Consider:

```java
static int override() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

This is **syntactically valid Java**, but it is strongly recommended **not to use it in production code**.

- `return 1;` has been evaluated, recording the completion reason as “return 1”.
- The `finally` block executes `return 2;`, creating a **new abrupt completion reason** of “return 2”.
- According to JLS Section 14.20.2, the new reason from `finally` **replaces** the old reason.
- The caller receives `2`; this is not because `return 1` was recomputed or a local variable was changed.

In the full program, the order is `try override` → `finally override` → `result=2`.

**Treat `return` in `finally` strictly as an example of language semantics, not a design technique**. It can mask results and serious errors, making code difficult to maintain and analyze.

### 4.5. `throwFromFinally()`: finally Throws an Exception, Caller Does Not Receive the Computed Result

In:

```java
static int throwFromFinally() {
    try {
        return 3;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Java has already computed the return value `3`, but `finally` throws `IllegalStateException`. The request to return `3` **is discarded**, and the caller receives the exception control path. Therefore, there is no `result=3` line in stdout; the `catch` branch in the caller prints `caught=cleanup failed`.

Evaluating the `return` expression may already have produced side effects before the exception from `finally` occurs. The exception does not automatically roll back those side effects.

This is one reason cleanup must be handled carefully. If a cleanup block can throw an error, the method might fail to return an already-computed result; how this is handled should be deliberate rather than accidental due to complex `finally` code.

### 4.6. `failedExpression()`: The return Expression Fails to Produce a Value

In:

```java
try {
    return Integer.parseInt("bad");
} finally {
    System.out.println("finally parse");
}
```

The call `Integer.parseInt("bad")` throws `NumberFormatException` **during expression evaluation**. No `int` result is produced to record a return value. Java still executes `finally` as required, prints `finally parse`, and then the parse exception propagates to the caller (because `finally` completes normally).

In the program, the caller catches the exact type and prints `caught=NumberFormatException`. There is no `result=...` line from this call. This is the fundamental difference between:

- **Successful `return` expression**: there is a value `V` pending to be returned.
- **Throwing `return` expression**: there is no `V`; the reason for control transfer is throwing an error, not returning a value.

If `finally` throws a second exception, that second exception can replace the original parse error. Avoid writing `finally` blocks with multiple unchecked exception paths.

### 4.7. `returnFromCatch()`: return Inside catch Also Goes Through finally

Consider:

```java
try {
    throw new IllegalArgumentException("bad input");
} catch (IllegalArgumentException ex) {
    System.out.println("catch returns");
    return 5;
} finally {
    System.out.println("finally catch");
}
```

This snippet belongs inside an illustrative method. `try` throws an error; `catch` catches and handles it, then initiates a request to return `5`. Before the caller receives `5`, `finally` still runs and prints `finally catch`. The final result is `5`.

Stdout order: `catch returns` → `finally catch` → `result=5`.

**It is not only `return` inside `try` that triggers `finally`**. A `return` inside `catch` of the same construct is subject to the exact same cleanup rules.

## 5. Distinguishing Primitive Values, References, and Object State

Java **passes by value** when returning results from a method call: the result can be a primitive value or a reference value.

### With Primitive Types

```java
int x = 10;
try {
    return x;
} finally {
    x++;
}
```

Assume this is inside a method returning `int`. The returned result is `10`, not `11`. The variable `x` changed in `finally`, but the earlier `return` expression is not recomputed.

Expressions such as `return x + 2;`, `return x++;`, or `return method();` follow the same order: the entire `return` expression is evaluated before `finally`.

**The `x++` case:** the value of the postfix increment is the value **before incrementing**, while the variable `x` is incremented as a side effect before control moves to `finally`:

```java
int x = 4;
try {
    return x++; // the selected return value is 4, x becomes 5.
} finally {
    x = 100;
}
```

This example returns `4`. It illustrates that both the side effect of the `return` expression and the work in `finally` execute, without causing the selected value to be re-evaluated.

### With Reference Types

```java
StringBuilder builder = new StringBuilder("Hello");
try {
    return builder;
} finally {
    builder.append(" Java");
}
```

The caller receives a reference to **the same object**, whose content when used may be `Hello Java`. Returning does not clone the object or “freeze” its entire state. An API design that wants to preserve immutable state should return an immutable object, an appropriate copy, or avoid mutating the object after selecting it for return.

### With Immutable String

```java
String name = "A";
try {
    return name;
} finally {
    name = name + "B";
}
```

The result is `"A"`. Because `String` is immutable, concatenation creates a new `String`; reassigning the variable `name` does not modify the old `String` object. The key point remains that **the returned reference was selected beforehand**, not that Java has a special rule for `String`.

## 6. When finally Has a New return/throw: Exact Precedence Rules

The JLS describes the control flow of `try-finally` in terms of **reasons for abrupt completion**. Given a prior reason `R` from `try`/`catch`:

- **`finally` completes normally:** reason `R` remains in effect. For `return V`, it returns `V`; for `throw E`, it continues throwing `E`.
- **`finally` completes abruptly for a new reason `S`:** the entire construct completes with `S`; reason `R` is replaced.

Comparison table:

| In `try`/`catch` | In `finally` | Outcome |
| --- | --- | --- |
| `return 10;` | Logs only, completes normally | Caller receives `10` |
| `return 10;` | Reassigns local variable, completes normally | Caller still receives `10` |
| `return object;` | Mutates the state of the same object | Caller receives the same reference and sees the mutated object |
| `return 10;` | `return 20;` | Caller receives `20`; old return is shadowed |
| `return 10;` | `throw new RuntimeException();` | Caller does not receive `10`; exception propagates |
| `throw new IOException(...);` | Logs, completes normally | Original `IOException` continues propagating |
| `throw new IOException(...);` | `return 20;` | Original exception is shadowed; caller receives `20` |
| `throw new IOException(...);` | `throw new IllegalStateException(...);` | The new exception may replace the original error |

The last two rows are examples of **dangerous behavior that is valid according to the language** (assuming appropriate declarations/handlers). They illustrate why `return` in `finally` is usually considered a design bug. Do not use it to “quick-fix” an error by forcing a method to always return successfully.

### Cleanup and Suppressed Exceptions Are a Separate Case

`try-with-resources` has specialized rules for closing resources. When both the `try` body and `close()` throw exceptions, the resource-closing exception is normally added to the primary exception's `getSuppressed()` list rather than replacing it by default the way a hand-written `finally` throwing a new error does.

This does not change the evaluation order of `return` expressions: Java still applies the language rules for execution flow and resource closing. However, **do not mix** the suppressed-exception rule for resources with the rule for a manual `finally` that executes `throw`.

If resource opening/closing needs to be managed, prefer `try-with-resources` with `AutoCloseable` when appropriate, rather than a complex `finally` that can easily swallow exceptions.

## 7. Return in try/catch/finally: Order Analysis for Other Cases

### 7.1. Multiple returns in Conditional Branches

```java
static int choose(boolean valid) {
    try {
        if (valid) {
            return 1;
        }
        return 2;
    } finally {
        System.out.println("cleanup");
    }
}
```

In a valid program, if `valid == true`, the return expression `1` is evaluated before `finally`; if `false`, `2` is evaluated before `finally`. Both paths print `cleanup` before the caller receives the result.

`finally` does not force a method to have only a single `return`; the branches decide the result beforehand, and `finally` simply runs cleanup along the path exiting the scope.

### 7.2. Return Without an Expression in a void Method

```java
static void save(boolean valid) {
    try {
        if (!valid) {
            return;
        }
        System.out.println("saving");
    } finally {
        System.out.println("cleanup");
    }
}
```

With `return;` in a `void` method, there is no value `V` to compute, yet control still passes through `finally` before the caller resumes. Do not assume `finally` only runs when `return` has a value.

### 7.3. A Method Called Inside a return Expression Has Side Effects

```java
static int logAndCompute() {
    System.out.println("compute");
    return 30;
}

static int example() {
    try {
        return logAndCompute() + 2;
    } finally {
        System.out.println("cleanup");
    }
}
```

When calling `example()`, the result is `32`. The line `compute` must print before `cleanup` because the call is inside the `return` expression. Adding `2` also completes before `finally` if `logAndCompute()` returns normally.

If `logAndCompute()` throws an exception before returning a result, there is no `32`; Java goes through `finally` along the exception path as in Section 4.6.

### 7.4. Multiple Nested finally Blocks

```java
static int nested() {
    try {
        try {
            return 9;
        } finally {
            System.out.println("inner");
        }
    } finally {
        System.out.println("outer");
    }
}
```

The return value is `9`. The reason `return 9` is established first, after which Java runs `finally` **from the inner scope to the outer scope**, so stdout inside the method is `inner` then `outer`. If an inner `finally` throws an error, control can still pass through the outer `finally`; the caller may receive an exception instead of `9`. The snippet above is an illustrative method in a class, not a standalone Java file.

## 8. Distinguishing “Pending return” from “Method Has Finished Returning”

A useful annotation in code reviews:

```text
return expression;   // Selects the value to return and requests control transfer.
finally { ... }      // Executes before the method transfers control back to the caller.
caller               // Receives the result unless a new reason overrides it.
```

The JLS calls what `return` produces an **abrupt completion** reason; *abrupt* here does not mean “an error is occurring”. A `return` statement is an intentional way to complete, while `throw` is another abrupt reason. `finally` can run on both paths.

Waiting to finish returning does not guarantee there are no side effects in `finally`. If `finally` modifies a file, database, cache, collection, or the object the caller is about to receive, those changes can still be observed. Conversely, `finally` can also throw an error and prevent the caller from **receiving** the already-computed value.

**Do not describe this mechanically as “Java copies the entire object into a return memory area”.** The language only guarantees that the expression value is evaluated before `finally`. For objects, that value is a reference, not a deep copy; bytecode details or temporary storage locations are up to the compiler/JVM.

## 9. Techniques for Writing Clearer Code

### 9.1. Use finally Only for Cleanup; Avoid return in finally

Recommended pattern:

```java
static int calculateSafely() {
    try {
        return 10;
    } finally {
        System.out.println("cleanup");
    }
}
```

The example above illustrates returning from `try` while `finally` completes normally. In real applications, cleanup might release locks/resources, update cleanup state, or log at an appropriate level.

Misleading pattern:

```java
static int calculateBadly() {
    try {
        return 10;
    } finally {
        return 20; // Shadows the return intent of try.
    }
}
```

This is **compilable code that should not be used**, except when demonstrating `finally` semantics itself. An even more dangerous bug is a `return` in `finally` masking a real exception from `try`, causing the program to report false success.

### 9.2. Separate Computation from Cleanup When Convenient

If computation has many side effects, you can write:

```java
static int clearer() {
    int answer;
    try {
        answer = compute();
    } finally {
        cleanUp();
    }
    return answer;
}
```

This is **illustrative code**: `compute()` and `cleanUp()` must be defined/imported appropriately. If `compute()` and `cleanUp()` complete normally, the return result is clearly handled after cleanup. If `compute()` throws an error, `finally` still runs, and then the exception propagates (unless `finally` produces a new error). Do not use this pattern to bypass cleanup rules; it simply makes some cases easier to read.

For resource-handling code, `try-with-resources` is usually clearer than a complex `finally` that closes resources manually.

### 9.3. Do Not Unexpectedly Mutate an Object About to Be Returned

If a method returns a mutable object, consider its state at the moment the caller receives it. Mutating the object in `finally` is **valid in Java** but can mislead readers into thinking the caller receives the old state.

Prefer finalizing the object before writing `return`, or returning an immutable copy when the contract requires no further modification. If cleanup with side effects is unavoidable, clearly document that boundary so reading the API and writing tests are unambiguous.

## 10. How to Predict the Output of a finally Snippet

To answer interview questions or debug real code, follow this order:

1. **Identify where `return` or `throw` occurs.** Is it in `try`, `catch`, or `finally`?
2. **Evaluate the `return` expression immediately when `return` is reached.** Note the chosen value or reference. If the expression throws an error, record the exception instead of assuming a return value.
3. **List side effects that occurred** in the `return` expression itself: incrementing variables, modifying arrays, calling methods, printing logs, etc.
4. **Execute `finally` in scope order**, from inner to outer. Distinguish reassigning a local variable from mutating an object's contents.
5. **Determine whether `finally` completes normally or abruptly.** If `finally` has a `return`/`throw`, update the final control reason.
6. **Deduce what the caller observes:** a primitive value, a reference (and object state), an exception, or another control path.
7. **Read stdout chronologically:** lines printed inside the `return` expression must appear before lines printed in `finally`; a result line printed by the caller only appears if the call actually returns normally.

Illustrative exercise (placed inside a method returning `int`):

```java
int count = 4;
try {
    return count++;
} finally {
    count = 100;
    System.out.println("finally count=" + count);
}
```

Explanation: the expression `count++` selects **4** as the return value and then increments the variable to **5**; `finally` assigns the variable to **100** and prints `finally count=100`; the caller receives **4** if `finally` completes normally.

If someone predicts the caller receives `100`, point out that both the increment and the assignment actually happen, but they do not **recompute** the value of the already-completed `return` expression.

## 11. Common Misconceptions

- **“`finally` runs before `return`, so `return` uses the new value in `finally`.”** False: the `return` expression is evaluated **first**; only transferring control to the caller is deferred.
- **“Assigning a variable in `finally` has no effect at all.”** False: the assignment affects the existing variable, but it does not change the value already selected to be returned.
- **“Returning an object means a snapshot of the object before `finally`.”** False: Java returns **the reference value**, and a mutable object can still change.
- **“Reassigning a reference variable to a new object in `finally` makes the caller receive the new object.”** False: the reference value was selected before the reassignment.
- **“`finally` has a `return`, but the caller still gets `try`'s `return` because `try` ran first.”** False: a `return` in `finally` can replace `try`'s return reason.
- **“`finally` throws an error, but the caller still receives the previous return value.”** False: if `finally` completes with `throw`, the caller receives the exception path.
- **“A throwing `return` expression still produces a return value.”** False: there is no value `V` when the expression completes abruptly.
- **“`finally` only runs when an exception occurs.”** False: it also runs when `try` succeeds, returns normally, or returns from `catch`, per the construct's rules.
- **“Returning from `catch` skips `finally`.”** False: `finally` still executes before control is completely transferred.
- **“`finally` always runs in every absolute situation.”** Do not claim this: when the JVM/process terminates abruptly, cleanup code may not get a chance to run.
- **“`return` in `finally` is a guaranteed way to avoid reporting errors.”** It can **mask serious errors**, which is not proper recovery.
- **“`try-with-resources` and a hand-written `finally` that throws use the same suppressed mechanism.”** False: suppressed exceptions are a specific rule for automatic resource closing.

## 12. Self-Check Questions

**Q1.** Why does `int x=10; try {return x;} finally {x=99;}` return `10`?

*Answer:* Because the expression `return x` is read as `10` before `finally`. Assigning `99` afterward does not cause the selected value to be re-evaluated.

**Q2.** With `return text;`, where `finally` calls `text.append("B")` and then `text = new StringBuilder("C")`, what does the caller receive?

*Answer:* The same original object selected before `finally`, but its content may have had `"B"` appended. Reassigning the local variable only changes that variable's reference.

**Q3.** If `finally` contains `return 2;` while `try` already evaluated `return 1;`, what is the result?

*Answer:* The caller receives `2`, because `finally` completes abruptly with a new return reason that replaces the old return request.

**Q4.** If `finally` throws `IllegalStateException` while `try` is requesting to return `3`, does the caller receive `3`?

*Answer:* No. The `throw` reason from `finally` can replace the pending return; the caller sees the exception.

**Q5.** If the `Integer.parseInt("bad")` expression in `return` throws an error, does `finally` run?

*Answer:* Yes, according to normal `try`/`finally` rules; there is no `int` value to return. If `finally` completes normally, `NumberFormatException` propagates outward.

**Q6.** Does `return` inside `catch` skip `finally`?

*Answer:* No; `finally` still runs before the caller receives the value, unless replaced by a new control reason.

**Q7.** For `return x++;` where `x` is initially `4` and `finally` assigns `x=100`, what value does the method return?

*Answer:* `4`. The postfix increment returns the old value; the increment side effect and the assignment in `finally` do not cause the return result to be recomputed.

**Q8.** Why should you not use `return` in `finally` to “guarantee a result”?

*Answer:* Because it can shadow the result from `try`/`catch` or mask a real exception, causing the caller to receive a false success state.

## 13. Official References

- [Java SE 17 JLS Section 14.17 – The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): expression evaluation order, return value, and control deferred by `finally`.
- [Java SE 17 JLS Section 14.20.2 – Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): rules for how abrupt completion reasons are preserved or replaced.
- [Java SE 17 JLS Section 14.1 – Normal and Abrupt Completion of Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.1): distinguishing `return` and `throw` as control-transfer reasons.
- [Java SE 17 JLS Section 15.6 – Normal and Abrupt Completion of Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.6): when the `return` expression itself throws an exception.
- [Java SE 17 JLS Section 14.20.3 – try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource-closing semantics and suppressed exceptions.
- [Java SE 17 API – StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): example of a mutable object when returning a reference.

**Conclusion:** `return expression;` **selects the value or reference before `finally` executes**. If `finally` completes normally, the caller receives the selected value; modifying a local variable does not recompute the return, whereas mutating the object's state can still be observed through the same reference. If `finally` executes its own `return` or `throw`, it can **replace the pending result**. The safest design is to use `finally` for cleanup, not to decide the return result.