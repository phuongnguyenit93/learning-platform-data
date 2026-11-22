# Local Variables and Definite Assignment in Java try/catch

When using `try/catch`, a local variable can be **declared** at the beginning of a method but only **assigned a value** in certain branches. If the program reads the variable after `try/catch`, the Java compiler must prove that the variable has been assigned on **every execution path that can reach the read point**. This rule is called **definite assignment** (DA).

A common example:

~~~java
int result;
try {
    result = Integer.parseInt(text);
} catch (NumberFormatException e) {
    System.out.println("Không phải số nguyên");
}
System.out.println(result); // Compile error: result might not have been assigned.
~~~

This is an illustrative snippet inside a method that has a `text` variable. If `Integer.parseInt(text)` throws `NumberFormatException`, control enters `catch` **before the assignment `result = ...` completes**; the `catch` block only prints a message, so at `System.out.println(result)`, the variable might not have a value. Java rejects this at compile time, even if you only intend to call the method with valid numeric strings.

This lesson explains how Java analyzes control-flow paths in `try/catch`, how to fix code in a business-appropriate way, the effects of `return`, `throw`, `finally`, `final` variables, variable scope, and common misconceptions.

## 1. Definition: definite assignment vs. default values

A **local variable** declared inside a method or block is not automatically assigned `0`, `false`, or `null` by Java simply because its type is `int`, `boolean`, or a reference type.

~~~java
static void example() {
    int count;
    // System.out.println(count); // Does not compile: not yet assigned.
    count = 3;
    System.out.println(count);     // Valid.
}
~~~

In this example, `count` exists in syntactic scope from its declaration point, but it is only allowed to be read after Java determines that the required assignment has occurred.

Three concepts should be distinguished:

| Concept | Meaning |
| --- | --- |
| **Scope** | The region in the code where the variable name can be referenced |
| **Definite assignment** | At the point of read, the compiler proves the variable has been assigned on every reachable path |
| **Runtime value** | The concrete value when an execution path actually runs to that point |

For example, a variable declared outside `try` may still be in scope after `catch`, yet **still cannot be read** if it does not satisfy DA.

Do not confuse this with an object's **field** or a `static field`: fields are default-initialized if not explicitly assigned (`0`, `false`, or `null` depending on type). Similarly, elements of a newly created array have default values. The rule requiring proof of assignment before reading is specifically enforced for **local variables**.

## 2. Why does `try/catch` introduce an unassigned path?

Consider this code:

~~~java
int port;
try {
    port = Integer.parseInt(input);
} catch (NumberFormatException e) {
    System.out.println("Sai định dạng");
}
use(port);
~~~

This is a **non-standalone** snippet: assume `input` and the method `use` exist. Even though `port` is assigned inside the `try` block, there are two paths:

~~~text
                  int port;  // unassigned
                           |
                    Integer.parseInt(input)
                       /              \
                Parse succeeds       Throws NumberFormatException
                      |                       |
               port = result         catch prints message
                      |                       |
                      +-----------+-----------+
                                  |
                               use(port)
~~~

The right-hand path reaches `use(port)` without assigning `port`. Therefore, the code **does not compile**, producing an error such as `variable port might not have been initialized`.

Two key points:

1. **An assignment only completes when the right-hand side is evaluated successfully.** In `port = Integer.parseInt(input);`, if `parseInt` throws an error, `port` does not receive a result from that assignment.
2. **The compiler checks every path that can complete normally at the point of use**, not just the path you expect to happen.

If you handle the error in `catch` by logging and continuing, you must still ensure the variable has a valid value or redirect control flow so that an unassigned variable is not read.

## 3. Fix 1: assign a value in both `try` and `catch`

When the business logic has a valid fallback value:

~~~java
static int parseOrFallback(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        result = -1;
    }
    return result;
}
~~~

This method can be placed in a Java 17+ class. Analysis:

- If `parseInt` succeeds, `result` receives the parsed integer.
- If `parseInt` throws `NumberFormatException`, the `catch` block assigns `-1`.
- On **every normal-completion path** of `try/catch`, `result` is assigned before `return result;`. Any path that encounters another uncaught exception completes abruptly and never reaches the `return` statement.

This is a valid solution from a compilation standpoint. However, in terms of business logic, `-1` is only a safe fallback if the API specifies it as a valid replacement value or error indicator. If `-1` can also be normal data, the caller will have difficulty distinguishing success from failure. In that case, use a structured result, handle the error at the caller level, or throw an appropriate exception.

### Assigning a value at declaration

~~~java
static int parseWithDefault(String input) {
    int result = -1;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        System.out.println("Sử dụng giá trị mặc định");
    }
    return result;
}
~~~

`result` is assigned `-1` before `try`, so even if parsing fails, there is a value to return. This approach has the advantage of simplicity, but you should **choose a meaningful default**; do not write `int result = 0;` just to silence the compiler when `0` could mask an error.

## 4. Fix 2: end the error branch with `return`

If parsing fails, the method can immediately return a replacement value:

~~~java
static int parseOrReturn(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        return -1;
    }
    return result;
}
~~~

This snippet **compiles** even though `result` is not assigned in `catch`. The reason: the `catch` branch has `return -1;`, so that branch **cannot reach** `return result;` at the end. Every remaining execution path that can reach the final statement has already assigned `result` successfully.

This is the difference between:

- "**A variable must be assigned on every path in the method**" — this statement is too broad.
- "**A variable must be assigned on every path that can actually reach the read point**" — this is the rule to remember.

There is no need to assign a value to a variable on a path that has already executed `return` and will never read the variable again.

## 5. Fix 3: end the error branch with `throw`

When there is no valid fallback, the handling branch can propagate the error to the caller:

~~~java
static int parseOrThrow(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Không thể đọc số nguyên: " + input, cause);
    }
    return result;
}
~~~

When parsing succeeds, `result` is assigned and returned. When parsing fails, `catch` throws a new exception and **cannot continue normally** to `return result;`. Therefore, the compiler accepts this code.

The `IllegalArgumentException(String, Throwable)` constructor preserves `cause` as the original `NumberFormatException`. Preserving the cause helps diagnose errors instead of merely logging and returning an unclear result.

You can also use `throw cause;` to rethrow the caught object, if the method's contract allows it and keeping the original exception type is meaningful. For checked exceptions, you still need to follow the corresponding `catch` or `throws` rules; that is independent of DA.

## 6. Standalone Java 17+ example

Create the file **`DefiniteAssignmentDemo.java`**:

~~~java
public class DefiniteAssignmentDemo {
    public static void main(String[] args) {
        for (String input : new String[] {"18", "oops"}) {
            System.out.println(
                    "fallback(" + input + ")=" + withFallback(input));
            try {
                System.out.println(
                        "propagate(" + input + ")=" + withPropagation(input));
            } catch (IllegalArgumentException e) {
                System.out.println(
                        "propagate(" + input + ") failed: " + e.getMessage());
            }
        }

        System.out.println(
                "returnOnError(oops)=" + returnOnError("oops"));
        System.out.println(
                "finalLocal(oops)=" + useFinalLocal("oops"));
        System.out.println(
                "handled(9)=" + handled("9"));
    }

    static int withFallback(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            result = -1;
        }
        return result;
    }

    static int withPropagation(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "bad integer: " + raw, e);
        }
        return result;
    }

    static int returnOnError(String raw) {
        int result;
        try {
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return -1;
        }
        return result;
    }

    static int useFinalLocal(String raw) {
        final int result = withFallback(raw);
        return result;
    }

    static int handled(String raw) {
        int result;
        try {
            if (raw.isBlank()) {
                return -1;
            }
            result = Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            result = 0;
        }
        return result;
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac DefiniteAssignmentDemo.java
java DefiniteAssignmentDemo
~~~

**Stdout:**

~~~text
fallback(18)=18
propagate(18)=18
fallback(oops)=-1
propagate(oops) failed: bad integer: oops
returnOnError(oops)=-1
finalLocal(oops)=-1
handled(9)=9
~~~

### Why is the program valid?

| Method | On success | On caught error | Why is reading the variable safe? |
| --- | --- | --- | --- |
| `withFallback` | Assigns `result` from parse | Assigns `result = -1` | Every normal branch assigns it |
| `withPropagation` | Assigns then returns | `throw`s another exception | Error branch does not reach the read point |
| `returnOnError` | Assigns then returns at the end | `return -1` immediately | Error branch does not reach the read point |
| `useFinalLocal` | Calls method for result, assigns `final result` | Called method already decided fallback | `final` variable is initialized once, before reading |
| `handled` | Assigns via `parseInt` | Assigns `0` if parse fails; blank input returns `-1` early | Every path reaching `return result` assigns it |

The stdout lines have a deterministic order because the program sequentially processes the string array `{"18", "oops"}` and prints only the caught results. `Integer.parseInt("oops")` throws `NumberFormatException`, a subclass of `IllegalArgumentException`. Because `withPropagation` wraps that error into `IllegalArgumentException`, the `catch` branch in `main` receives the exception as expected.

## 7. Variables declared outside `try` vs. inside `try`

**Scope** is a separate issue from definite assignment.

~~~java
static void scopeExample(String input) {
    try {
        int parsed = Integer.parseInt(input);
        System.out.println(parsed);
    } catch (NumberFormatException e) {
        System.out.println("Sai số");
    }

    // System.out.println(parsed); // Invalid: parsed is out of scope.
}
~~~

Here, `parsed` is declared inside the `try` block. After the closing `}` of the block, this name is no longer in scope. Even though it is definitely assigned in the success branch, you cannot reference `parsed` after `try/catch`.

Conversely:

~~~java
static void scopeAndAssignment(String input) {
    int parsed;
    try {
        parsed = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        parsed = -1;
    }
    System.out.println(parsed);
}
~~~

`parsed` is declared outside `try`, so it remains in scope, and both the success branch and the error-handling branch assign a value. You need **both scope and definite assignment** to read the variable.

The `catch` parameter, such as `NumberFormatException e`, is also only in scope inside the `catch` block itself. The runtime passes the exception object into that parameter; there is no need to manually assign `e` before using `e.getMessage()`.

## 8. Multiple `catch` branches: every path must be considered

Suppose an operation can throw two different exception types:

~~~java
static int readOrFallback(String text, boolean unavailable) {
    int result;
    try {
        if (unavailable) {
            throw new IllegalStateException("Nguồn không sẵn sàng");
        }
        result = Integer.parseInt(text);
    } catch (NumberFormatException e) {
        result = -1;
    } catch (IllegalStateException e) {
        result = -2;
    }
    return result;
}
~~~

This method is valid. If `Integer.parseInt` succeeds, `result` receives the number; if it fails due to format, it receives `-1`; if the source is unavailable, it receives `-2`. Every normal-completion path of `try/catch` before `return` has a value.

However, if the second branch only logs:

~~~java
static int broken(String text, boolean unavailable) {
    int result;
    try {
        if (unavailable) {
            throw new IllegalStateException("Nguồn không sẵn sàng");
        }
        result = Integer.parseInt(text);
    } catch (NumberFormatException e) {
        result = -1;
    } catch (IllegalStateException e) {
        System.out.println("Nguồn lỗi");
    }
    return result; // Does not compile: the second catch branch has not assigned it.
}
~~~

then `return result` could execute after `catch (IllegalStateException e)` without an assignment. You must assign a meaningful value, `return`, or `throw` in that branch.

**Do not only check the `catch` branch you consider common.** The DA rule must consider all paths reaching the read point according to the compiler's control-flow analysis.

## 9. Exceptions on the right-hand side of an assignment

This is an easily overlooked point:

~~~java
int value;
try {
    value = Integer.parseInt(input);
} catch (NumberFormatException e) {
    // value is still not assigned by the assignment above.
}
~~~

Java evaluates the right-hand side `Integer.parseInt(input)` before completing the assignment to `value`. If the call throws `NumberFormatException`, the entire assignment expression does not complete. You cannot assume that `value` was "partially assigned" a value.

Even with complex expressions:

~~~java
int result;
try {
    result = calculate(input);
} catch (IllegalArgumentException e) {
    // No guarantee that result receives a value from calculate(input).
}
~~~

This is an illustrative snippet assuming `calculate` can throw `IllegalArgumentException`. To read `result` afterward, you must handle the `catch` path or initialize it beforehand. DA analysis does not rely on a result that **might** be produced if the method runs successfully; it requires that a result **definitely** exists on every path to the read point.

## 10. `final` local variables: definitely assigned and not assigned twice

`final` does not create a special exception for `try/catch`; it adds the requirement that the variable **cannot be reassigned** once it has a value. A `final` local variable that is not initialized at declaration is often called a *blank final*. For valid execution paths, the compiler also checks *definite unassignment* at the point of assignment to prevent overwriting.

The most readable approach:

~~~java
static int finalLocalExample(String text) {
    final int result = parseOrFallback(text);
    return result;
}

static int parseOrFallback(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1;
    }
}
~~~

These are two methods that can be placed in the same class. `final result` is assigned **exactly once** from the value returned by `parseOrFallback`. If the called method terminates abruptly, the assignment does not complete and the calling method does not reach `return result` along that path either.

### Do not fix by assigning twice to `final`

~~~java
final int result = 0;
try {
    result = Integer.parseInt(text); // Error: cannot reassign final.
} catch (NumberFormatException e) {
    System.out.println("Không hợp lệ");
}
~~~

This is a **counterexample that does not compile**. Initializing `result = 0` already assigns the `final` variable; the assignment inside `try` is illegal.

With a *blank final* assigned across multiple `try/catch` branches, the definite assignment **and** definite unassignment rules can be harder to reason about, especially when exceptions can arise at different points inside `try`. Do not assume that a single-assignment pattern on paper will always be valid for `final`; for complex logic, prefer **having each branch return a result** or extracting a value-returning helper method and declaring `final result = ...` outside. This avoids half-initialized variable states and simplifies control flow.

## 11. Does `finally` help a variable become assigned automatically?

`finally` is primarily used for cleanup or executing actions that must run when leaving `try/catch`. It **does not automatically provide a default value** for local variables and does not make the compiler ignore unassigned paths.

Example of a valid method:

~~~java
static int parseWithCleanup(String input) {
    int result;
    try {
        result = Integer.parseInt(input);
    } finally {
        System.out.println("Hoàn tất bước đọc");
    }
    return result;
}
~~~

If parsing succeeds, `result` is assigned, `finally` runs, and then the method returns `result`. If parsing throws `NumberFormatException`, `finally` still normally runs, but the exception continues to propagate out; the error path **does not reach** `return result`. Therefore, reading `result` at the end is valid under DA analysis.

You should not move `System.out.println(result)` into `finally` in the example above when `result` might not be assigned at the time `finally` runs. Before using a variable inside `finally`, you must also ensure it has been assigned on every path that can reach that read point.

An example of assigning a default before entering `try`:

~~~java
static int parseWithFinally(String input) {
    int result = -1;
    try {
        result = Integer.parseInt(input);
    } catch (NumberFormatException e) {
        System.out.println("Dùng fallback");
    } finally {
        System.out.println("Xử lý xong");
    }
    return result;
}
~~~

The method above handles the error path with a default value; `finally` does not replace the initialization `result = -1`.

**Note:** Writing a `return` or a new `throw` carelessly inside `finally` can alter or mask the result or propagating exception. Do not use `finally` as a trick to bypass definite assignment; design success and failure paths clearly.

## 12. `try-with-resources` and variable scope

The try-with-resources syntax extends the problem with automatically closed resources:

~~~java
static String firstLine(String input)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader(input))) {
        return reader.readLine();
    }
}
~~~

`reader` is initialized in the resource declaration of `try`, and the scope of the resource variable is bound to the try-with-resources construct according to Java rules. The body can read `reader` because resource initialization must succeed before entering the `try` body.

If the constructor or resource initialization expression fails, the body may not run; Java applies the relevant resource-closing rules and propagates the appropriate exception. This does not cause a result variable declared outside `try` to be automatically assigned.

Another example:

~~~java
String content;
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader(input))) {
    content = reader.readLine();
} catch (java.io.IOException e) {
    content = "fallback";
}
System.out.println(content);
~~~

This is an **illustrative snippet inside a method that has `input`**. Both the successful read path and the `catch` path assign `content`. However, reading and closing the resource can throw checked exceptions, and any exceptions not caught by the `catch` block will cause the method to complete abruptly. The case where `reader.readLine()` returns `null` when there are no lines is still an **assigned value**, even though the application may need to check for `null` according to business logic.

## 13. DA is a static check, not a measurement of input values

Java determines definite assignment using the language's flow analysis rules. It does not trial-run the program, wait for actual data, or attempt to prove arbitrary assumptions about user input.

Example:

~~~java
int parsed;
try {
    parsed = Integer.parseInt("123");
} catch (NumberFormatException e) {
    System.out.println("Đầu vào sai");
}
System.out.println(parsed); // Does not rely on the assumption that "123" is always valid.
~~~

This is an **illustrative snippet that does not compile**. Even though a human reader knows `"123"` is valid, the compiler still analyzes exception paths according to Java rules, rather than proving every runtime behavior of a library by interpreting string literals.

Conversely, `int parsed = 123;` clearly assigns the variable at declaration. DA analysis also evaluates certain specific language control structures such as `if/else`, `return`, `throw`, boolean expressions, and loops according to defined rules; not every condition is evaluated as an arbitrary logical theorem.

**If the program compiles**, Java protects you from reading an unassigned local variable on analyzed paths. That **does not guarantee the assigned value is correct**. Assigning `-1` just to get past the compiler may satisfy DA while introducing a data-domain bug.

## 14. A concise pattern: returning directly from each branch

When you do not need to keep an intermediate variable, this is often the most readable pattern:

~~~java
static int parseSafe(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1;
    }
}
~~~

Here there is no local variable `result` to track across multiple paths. If parsing succeeds, return the number; if it fails, return the fallback. For checked exceptions, a similar method can use `throws` to propagate the error to the caller; choose the approach that fits the contract.

If you need to clearly distinguish success/failure when `-1` can also be valid data, consider a structured result:

~~~java
record ParseResult(boolean success, int value) {}

static ParseResult parseWithStatus(String text) {
    try {
        return new ParseResult(true, Integer.parseInt(text));
    } catch (NumberFormatException e) {
        return new ParseResult(false, 0);
    }
}
~~~

These are two Java 17+ declarations that can be placed together in a class or in an appropriate scope. `value = 0` when `success = false` is merely a placeholder component that does not represent a successful result; the caller should check `success` before using `value`. Returning from both branches avoids unassigned local variable situations while providing a clearer error-reporting contract than an ambiguous sentinel.

## 15. Common mistakes

**Mistake 1 — Assuming local variables automatically receive `0`/`null`.**  
Local variables do not have default initialization for reading. Fields and newly created array elements follow different rules.

**Mistake 2 — Assuming declaring outside `try` is enough.**  
Declaration determines the variable's scope. It does not guarantee the variable is assigned on every path after `catch`.

**Mistake 3 — Looking only at the successful parse path.**  
You must consider the path where an exception occurs **before the assignment completes**. A `catch` block that only logs may leave the variable unassigned.

**Mistake 4 — Assigning a meaningless default.**  
`int port = 0;` may make the code compile, but it causes wrong results if `0` is misinterpreted by the caller as a valid port. Use a contract-approved fallback or reflect failure clearly.

**Mistake 5 — Confusing `return`/`throw` with continuing execution.**  
A `catch` branch that has already executed `return` or `throw` cannot reach the statement after `try/catch` along that path. There is no need to assign a variable just to satisfy an unreachable read point.

**Mistake 6 — Missing one `catch` branch.**  
If the first branch assigns the variable but the second branch only logs and completes normally, the variable may still be unassigned at the read point.

**Mistake 7 — Using a variable out of scope.**  
A variable declared inside a `try` block cannot be read after leaving that block, even if it was assigned a value in the success branch. This is a scope error, distinct from a DA error.

**Mistake 8 — Using `final` and then trying to reassign.**  
`final int x = 0;` followed by `x = ...;` is always invalid. If you need a value from branches, return the result from a method and assign `final` once.

**Mistake 9 — Relying on `finally` to make a variable "definitely have a value".**  
`finally` does not automatically initialize locals. When reading a variable inside `finally`, you must also consider error paths occurring before the assignment.

**Mistake 10 — Thinking that without `catch`, every path must assign the variable.**  
If an exception propagates out and the method terminates abruptly, that path does not reach the read point after `try`. DA checks paths that can reach the read point; it does not force unreachable paths to assign.

**Mistake 11 — Silencing compile errors with an empty `catch`.**  
`catch (Exception ignored) {}` does not make a failed assignment succeed. It can also hide the root error and make diagnosis harder.

## 16. Self-check questions

1. Why does `int x; System.out.println(x);` not compile, whereas reading a newly created `int` field is valid?
2. Does `int value; try { value = Integer.parseInt(text); } catch (NumberFormatException e) { }` allow reading `value` after the block? Why?
3. Is it necessary to assign `value` in the `catch` branch if that branch ends with `return -1;`?
4. If a `catch` branch throws `IllegalArgumentException`, can it reach `return value;` after `try/catch`?
5. In the pattern `int result = -1; try { result = parseInt(text); } catch (...) {}`, what makes the code compile? What is the business risk?
6. Can a variable `parsed` declared inside `try` be used outside `try/catch`? Is this a scope error or a DA error?
7. A `try` has two `catch` blocks; the first assigns `result` and the second only logs. Is it definitely assigned enough to read `result` afterward?
8. Why does an exception thrown on the right-hand side leave the assignment on the left-hand side incomplete?
9. Can a `final int x = 0;` variable be reassigned inside `try`? How can you avoid branching assignments for `final`?
10. When can a variable be read after `try/finally` even if an operation inside `try` can throw an exception before the assignment?
11. Why is the fact that `Integer.parseInt("123")` almost certainly succeeds with that data not a reliable reason to skip DA analysis?
12. If a fallback sentinel is also valid data, what clearer result approach is available?
13. Can you use `return Integer.parseInt(text);` in `try` and `return -1;` in `catch` to avoid an intermediate variable?
14. In the main example, why does `withPropagation("oops")` not read an unassigned variable even though the error branch does not assign `result`?

### Suggested answers

1. Locals do not have default initialization; fields have default values.
2. No; parsing can throw before the assignment and `catch` does not assign it.
3. No; `return` terminates the error path before the read point.
4. No; that branch terminates abruptly and looks for an outer handler.
5. Having a default value before `try`; it can mask errors or return a misleading value.
6. No, because the variable is out of scope.
7. No, because the second `catch` path can still reach the read point unassigned.
8. Because the right-hand side is evaluated before assignment and terminated abruptly.
9. No; return the result from a helper or have every branch `return`, then initialize `final` once.
10. When every path that can complete normally to the read point has assigned it; paths where an exception propagates out do not reach there.
11. DA is compiler flow analysis, not based on runtime expectations about strings.
12. Return a result type with status, use a representation that distinguishes success/failure, or throw an exception per the contract.
13. Yes; both branches return directly.
14. Because the error branch `throw`s an exception and cannot reach `return result;`.

## 17. Key takeaways

**A local variable must be definitely assigned at the point of read, not necessarily assigned in every branch appearing in the source code.** With `try/catch`, trace every path that can reach the point where the variable is used: the success branch has an assignment, the `catch` branch has a valid assignment, or the failure branch ends with `return`/`throw` and never reaches the read point. Distinguishing **scope**, **definite assignment**, **default values**, and **business error semantics** will help you fix the root cause rather than adding a dummy value just to make the code compile.