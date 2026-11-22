# The First Matching `catch` Block Is Executed in Java

When an exception occurs in a `try` block, Java searches for a `catch` branch that can receive the **actual exception object**. For `catch` blocks belonging to the same `try`, Java evaluates them **from top to bottom in declaration order** and executes only **the first branch with a compatible type**. Once this branch is selected, Java does not continue running the remaining `catch` blocks of the same construct, even if their types could also catch that object.

This is a rule from the Java Language Specification (JLS) §14.20.1. Mastering it helps you write parent/child exception handlers in the right order, predict control flow, recognize unreachable `catch` code, and avoid confusing an exception rethrown from a `catch` block with a new exception handled by an adjacent branch.

## 1. A Quick Look at the Branch Selection Rule

```java
try {
    throw new NumberFormatException("not a number");
} catch (NumberFormatException ex) {
    System.out.println("specific");
} catch (IllegalArgumentException ex) {
    System.out.println("general");
}
```

This is valid code when placed inside a method. The sole output is:

```text
specific
```

`NumberFormatException` extends `IllegalArgumentException`, so in terms of type relationship **both `catch` blocks can accept** this exception. However, the `catch (NumberFormatException ex)` branch appears first, so it is selected. `catch (IllegalArgumentException ex)` does not run for this throw.

More precisely:

1. Evaluate and execute the `try` block.
2. If `try` completes normally, **no `catch` block runs**.
3. If `try` completes abruptly by throwing an exception object `V`, evaluate the `catch` blocks of this `try` construct **from left to right in the specification**, corresponding to top-to-bottom order in source code.
4. Select the **first** `catch` whose catchable type is compatible with the **actual runtime type** of `V`, and assign `V` to the `catch` parameter.
5. If the selected `catch` block handles it and completes normally, the entire `try-catch` can complete normally. If it executes a `throw` or `return`, the enclosing construct continues according to that new completion reason.
6. If there is no matching `catch`, the exception **continues propagating** to the outer context.

**A single exception throw does not cause all compatible `catch` branches to run.** The `catch` blocks are mutually exclusive alternative handlers, not sequential processors.

## 2. Actual Type, Inheritance Relationships, and Compatibility

The thrown exception must be an object of `Throwable` or a subclass. For a standard `catch (T ex)` to catch object `V`, the runtime type of `V` must be assignable to type `T`. A branch using a parent type can catch a child-type object.

Example of a typical inheritance hierarchy:

```text
Throwable
├── Error
│   └── OutOfMemoryError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
```

This tree only shows the classes used in this lesson. From the tree above:

| Object being thrown | `catch` that can accept it | Incompatible `catch` |
| --- | --- | --- |
| `new NumberFormatException(...)` | `NumberFormatException`, `IllegalArgumentException`, `RuntimeException`, `Exception`, `Throwable` | `IOException` |
| `new FileNotFoundException(...)` | `FileNotFoundException`, `IOException`, `Exception`, `Throwable` | `RuntimeException` |
| `new EOFException(...)` | `EOFException`, `IOException`, `Exception`, `Throwable` | `FileNotFoundException` |
| `new OutOfMemoryError(...)` | `OutOfMemoryError`, `Error`, `Throwable` | `Exception` |

Note: the table describes **type compatibility**, not advice to catch `OutOfMemoryError` in an application. Errors under the `Error` branch usually need to propagate and be investigated at an appropriate level.

If inside `try` you have:

```java
IOException failure = new FileNotFoundException("settings.ini");
throw failure;
```

then the actual thrown object is `FileNotFoundException`. Regardless of the variable `failure` being declared as `IOException`, `catch` selection at runtime is based on **the actual class of the object**, not merely the declared type of the variable. The compiler still uses declared type information and exception analysis to check which `catch` branches are valid in code.

## 3. Specific Exceptions Must Come Before General Exceptions

Within the same `catch` chain, if the type of one branch is a subclass of the type in another branch, place the **subclass before the superclass**. Placing the superclass branch first will catch all subclass objects, causing the later subclass branch to never be selected.

**Correct:**

```java
try {
    readConfig();
} catch (FileNotFoundException ex) {
    System.out.println("Không tìm thấy tệp");
} catch (IOException ex) {
    System.out.println("Lỗi I/O khác");
}
```

This is an illustrative snippet inside a method, assuming `readConfig()` is declared `throws IOException` and `FileNotFoundException` is imported from `java.io`. The first branch handles the specialized case; the second branch serves as a fallback for the remaining `IOException`s.

**Incorrect — does not compile:**

```java
try {
    readConfig();
} catch (IOException ex) {
    System.out.println("I/O");
} catch (FileNotFoundException ex) {
    System.out.println("Không tìm thấy tệp");
}
```

In the incorrect snippet, `IOException` comes first and is a superclass of `FileNotFoundException`, so every `FileNotFoundException` is caught by the first branch. The Java compiler rejects the later branch with a diagnostic such as **exception FileNotFoundException has already been caught**. This is a compile-time error, not a branch that is simply skipped at runtime.

The same rule applies to:

- `catch (Exception ex)` placed before `catch (IOException ex)`.
- `catch (RuntimeException ex)` placed before `catch (IllegalArgumentException ex)`.
- `catch (IllegalArgumentException ex)` placed before `catch (NumberFormatException ex)`.
- `catch (Throwable ex)` placed before any `Throwable` subclass.

Ordering is **not required to be more specific** between two classes *without a parent/child relationship*, such as `IOException` and `SQLException`; in that case, each branch catches different types. However, you should arrange them in an order that is readable and meaningful for your business logic.

## 4. Java 17+ Program: Verifying the First Matching `catch`

Save as `CatchOrderDemo.java`:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchOrderDemo {
    static void fetch(int code) throws IOException {
        switch (code) {
            case 0 -> throw new FileNotFoundException("profile.txt");
            case 1 -> throw new EOFException("partial data");
            case 2 -> throw new IllegalArgumentException("invalid code");
            default -> System.out.println("fetch=OK");
        }
    }

    public static void main(String[] args) {
        for (int code = 0; code < 4; code++) {
            try {
                fetch(code);
            } catch (FileNotFoundException ex) {
                System.out.println("file=" + ex.getMessage());
            } catch (IOException ex) {
                System.out.println("io=" + ex.getClass().getSimpleName());
            } catch (RuntimeException ex) {
                System.out.println("runtime=" + ex.getMessage());
            }

            System.out.println("done=" + code);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CatchOrderDemo.java
java CatchOrderDemo
```

Output:

```text
file=profile.txt
done=0
io=EOFException
done=1
runtime=invalid code
done=2
fetch=OK
done=3
```

Iteration-by-iteration explanation:

1. `code = 0`: `fetch()` throws `FileNotFoundException`. The `catch (FileNotFoundException)` branch is selected first even though `IOException` is also compatible.
2. `code = 1`: `fetch()` throws `EOFException`, which is a subclass of `IOException` but not `FileNotFoundException`. The first branch does not match, so the `IOException` branch runs.
3. `code = 2`: `IllegalArgumentException` belongs to `RuntimeException`; the two I/O branches do not match, so the `RuntimeException` branch runs. The fact that `fetch()` only declares `throws IOException` does not prevent it from throwing an unchecked exception.
4. `code = 3`: no exception occurs, only `fetch=OK` is printed; all three `catch` blocks are skipped.

The `done=...` line appears after every iteration because each selected `catch` completes normally. If a `catch` rethrows an error or another unhandled exception occurs, that line does not necessarily run.

## 5. No Exception Means No `catch` Runs

`catch` does not act like a mandatory `else` branch after every `try`. If the entire `try` completes normally, Java skips the `catch` blocks:

```java
try {
    System.out.println("try complete");
} catch (RuntimeException ex) {
    System.out.println("will not print in this run");
}
System.out.println("after");
```

This is an illustrative snippet inside a method, producing:

```text
try complete
after
```

`catch (RuntimeException ex)` is valid even though the `try` block contains no explicit call that throws an unchecked exception. However, no runtime error occurs during this execution, so it does not run.

If you place `catch (IOException ex)` on a `try` **that cannot throw checked `IOException`** (and has no resource that can throw it when closing), the compiler can reject it with `exception IOException is never thrown in body of corresponding try statement`. Whether a `catch` is valid at compile time and whether it is selected at runtime are two different questions.

## 6. A Selected `catch` Does Not "Fall Through" to Lower `catch` Blocks

Consider this code:

```java
try {
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("first");
} catch (RuntimeException ex) {
    System.out.println("second");
} catch (Exception ex) {
    System.out.println("third");
}
System.out.println("after");
```

Output:

```text
first
after
```

All three branches can accept an `IllegalArgumentException` object through inheritance, yet only the first branch runs. After that branch completes normally, control transfers to the statement **after the entire `try-catch`**, not to the second `catch`.

This differs from some traditional `switch` constructs that can *fall through*. `catch` blocks have no fall-through mechanism; you do not need to write `break` to stop a `catch` chain.

If you want shared handling for multiple exception types, you can write a **multi-catch** or move the shared logic into a method, rather than expecting multiple `catch` branches to run together.

## 7. A `catch` Throws a New Exception: Can the Adjacent Branch Catch It?

**No.** The `catch` blocks of a `try` only select a branch to handle an exception from the `try` part (including extended rules with resources). If a selected `catch` branch **throws a new exception**, the remaining `catch` branches **at the same level** are not tried for that new exception.

Example:

```java
try {
    throw new IllegalArgumentException("input");
} catch (IllegalArgumentException ex) {
    throw new IllegalStateException("translated", ex);
} catch (IllegalStateException ex) {
    System.out.println("not selected for the new error");
}
```

This is a **syntactically valid illustrative snippet** inside a method, but at runtime the `IllegalStateException` propagates out of the `try-catch` construct if there is no handler at an outer layer. The `catch (IllegalStateException)` branch is only an option for an error thrown from `try`, not for handling a new error from the preceding `catch` branch.

In practice, translating an exception at a handling layer may be necessary; you should attach `cause` to preserve the original reason, like the `new IllegalStateException("translated", ex)` constructor above.

## 8. Java 17+ Program: Nested `catch` and Translated Exceptions

Save as `NestedCatchDemo.java`:

```java
import java.io.IOException;

public class NestedCatchDemo {
    static void process() {
        try {
            try {
                throw new IOException("disk");
            } catch (IOException ex) {
                System.out.println("inner=" + ex.getMessage());
                throw new IllegalStateException("service failed", ex);
            } catch (RuntimeException ex) {
                System.out.println("unreached sibling");
            } finally {
                System.out.println("inner-finally");
            }
        } catch (IllegalStateException ex) {
            System.out.println("outer=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("after");
    }

    public static void main(String[] args) {
        process();
    }
}
```

```bash
javac -encoding UTF-8 NestedCatchDemo.java
java NestedCatchDemo
```

Output:

```text
inner=disk
inner-finally
outer=service failed
cause=IOException
after
```

Execution flow:

1. The inner `try` throws `IOException`; the inner `catch (IOException)` branch matches and executes.
2. This branch creates a new `IllegalStateException`, keeping `IOException` as `cause`.
3. The adjacent `catch (RuntimeException)` branch is **not** executed for the error just thrown inside the first `catch` branch.
4. The `finally` block of the inner construct still runs and completes normally.
5. The `IllegalStateException` propagates to the outer `try` construct; the outer `catch (IllegalStateException)` receives it.
6. The outer branch completes normally, so `after` is printed.

This example demonstrates two rules simultaneously: **only one `catch` is selected per `try` construct**, and nested `try-catch` constructs can handle **different exception objects at different points in time**.

## 9. Searching `catch` Per `try` Scope, Not Scanning Every `catch` in the Program

The word "first" only makes sense once **the `try` construct under consideration** is identified. Java searches for the nearest handler along the exception's propagation path. The `catch` blocks of the same `try` are checked in declaration order; if no branch matches, the exception continues outward and may encounter a `try-catch` in the calling method.

```text
caller(): try {
    service(): try {
        repository(): throw FileNotFoundException
    } catch (IOException) {
        // selected in service() if the error reaches here and catch matches
    }
} catch (Exception) {
    // only receives if the exception passes through service() unhandled
}
```

This is an explanatory call-flow diagram, **not Java syntax**.

A `catch (Exception)` in a closer enclosing `try` can be selected before a `catch (FileNotFoundException)` at a farther calling layer. There is no algorithm that searches for "the most specific catch class across the entire application." Java prioritizes **handler scope** first, then selects **the first compatible branch** within that scope.

Similarly, an exception object can travel from `repository()` up to `service()` and then `controller()` if there is no suitable `catch` at a lower layer. The `throws` clause describes compile-time checked-exception obligations; it does not change the runtime `catch` branch selection rule.

## 10. `multi-catch` Has Multiple Types but Only One Handler Block

Since Java 7, the syntax `catch (IOException | SQLException ex)` allows **one `catch` branch to accept one of several types**. As far as handler selection goes, this is **still a single `catch` branch**. Java does not execute separate sub-branches just because it sees the `|` operator.

Save as `MultiCatchDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchDemo {
    static void work(int mode) throws IOException, SQLException {
        if (mode == 0) {
            throw new IOException("disk");
        }
        if (mode == 1) {
            throw new SQLException("database");
        }
        System.out.println("work=OK");
    }

    public static void main(String[] args) {
        for (int mode = 0; mode < 3; mode++) {
            try {
                work(mode);
            } catch (IOException | SQLException ex) {
                System.out.println("handled="
                        + ex.getClass().getSimpleName() + ":" + ex.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
```

Output:

```text
handled=IOException:disk
handled=SQLException:database
work=OK
```

Several limitations:

- Types in the same `multi-catch` must not have a parent/child class relationship with each other. For example, `catch (FileNotFoundException | IOException ex)` is **invalid**, because `FileNotFoundException extends IOException`.
- The parameter `ex` in a `multi-catch` is **implicitly final**: you cannot reassign that variable.
- You can call common members of the types, such as `ex.getMessage()`.
- If the errors require different handling strategies, writing separate `catch` blocks is clearer.
- If there is another `catch` after the `multi-catch`, the **first compatible branch** rule still applies.

## 11. `catch` and Checked Exceptions Are Checked Separately by the Compiler

The Java compiler checks the types of checked exceptions that a `try` block can throw. It also checks cases where a `catch` branch is completely shadowed by a preceding branch.

Compare three cases:

| Code | Status | Explanation |
| --- | --- | --- |
| `catch (IOException)` then `catch (FileNotFoundException)` | Invalid | The first branch already covers every `FileNotFoundException`. |
| `catch (FileNotFoundException)` then `catch (IOException)` | Valid when `try` can throw the relevant checked exceptions | The specific branch handles missing-file errors; the general branch handles the rest. |
| `catch (IOException)` then `catch (SQLException)` | Can be valid | Neither type is a parent/child of the other; `try` must be able to throw those checked exceptions accordingly. |

A `try` containing only `System.out.println("ok")` does not allow freely adding `catch (java.io.IOException)` when no operation can throw checked `IOException`. Conversely, branches catching `RuntimeException` or `Exception` have broader allowance rules because they include unchecked exceptions; do not infer that every `catch` type requires an explicit `throw` statement.

**The order and validity of `catch` blocks are checked at compile time; selecting a branch for a specific object happens at runtime.** These are two distinct steps. Compile-time results also depend on the `throws` signatures of called methods, not just on what you observed in a single test dataset.

## 12. `finally` Runs After Selecting `catch`, Not as the Next `catch` Branch

In `try-catch-finally`, if an exception occurs in `try`, Java selects the matching `catch` branch as described above, executes the `catch` block, and then executes `finally` according to language rules before finishing the exit from the construct.

```java
try {
    throw new IllegalArgumentException("invalid");
} catch (IllegalArgumentException ex) {
    System.out.println("caught");
} catch (RuntimeException ex) {
    System.out.println("not used");
} finally {
    System.out.println("cleanup");
}
System.out.println("after");
```

This illustrative snippet inside a method prints:

```text
caught
cleanup
after
```

`finally` is not an additional `catch` and does not depend on which `catch` branch was selected; its purpose is to execute cleanup code according to standard rules. If a `catch` block finishes abruptly due to `throw` or `return`, `finally` still runs before that completion reason continues propagating, provided the program actually goes through normal Java execution mechanics.

**Be careful:** if `finally` itself throws an exception or executes `return`, the new reason can replace the pending error/value. In application code, avoid `return` inside `finally` and avoid losing the primary exception during cleanup operations.

## 13. `try-with-resources`: Resource Closing Errors Are Handled Before `catch` Selection

With `try-with-resources`, resources are closed automatically. If the `try` body throws an error and `close()` also throws an error, the exception from `close()` is normally added to `getSuppressed()` of the primary exception. When reaching the `catch` branches, **the primary exception type** determines which branch is selected.

Java 17+ example, save as `ResourceCatchDemo.java`:

```java
import java.io.IOException;

public class ResourceCatchDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalStateException("work");
        } catch (IOException ex) {
            System.out.println("io=" + ex.getMessage());
        } catch (IllegalStateException ex) {
            System.out.println("selected=" + ex.getMessage());
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 ResourceCatchDemo.java
java ResourceCatchDemo
```

Output:

```text
selected=work
suppressed=close
```

Even though `close()` throws `IOException`, the primary error of this execution is `IllegalStateException("work")` thrown in the `try` body. `IOException` is attached as suppressed rather than becoming a separate primary exception to trigger the `catch (IOException)` branch. Therefore, the `catch (IllegalStateException)` branch is selected.

If the `try` body completes normally but `close()` throws `IOException`, the closing error can become the primary exception and `catch (IOException)` is then selected. This is why you must understand the relationship between primary and suppressed errors rather than merely counting how many exceptions occurred.

## 14. Why Should You Usually Catch Specific Types?

The following code is often hard to maintain:

```java
try {
    performBusinessOperation();
} catch (Exception ex) {
    System.out.println("Something went wrong");
}
```

This is an illustrative snippet with `performBusinessOperation()` defined elsewhere. `catch (Exception)` can accept many kinds of checked exceptions and `RuntimeException`s, causing the program to apply a single handling strategy to very different situations. It also **does not catch `Error`** because `Error` is a separate branch of `Throwable`.

A better design is usually:

1. Identify the errors that can be handled at this layer (for example, `FileNotFoundException` to report a missing configuration).
2. Place the `catch` for the specific situation first, followed by an appropriate parent type if broader handling is needed.
3. Only use `catch (Exception)` at boundaries with a clear centralized error-handling requirement, and do not assume the application state has recovered.
4. Preserve the error object or `cause` when translating exceptions; do not just log `ex.getMessage()` and discard the stack trace if investigation is needed.
5. Do not use `catch (Throwable)` as a way to "block every problem" in normal business logic, because it also catches serious `Error`s.

Remember that **there is no rule that "the JVM automatically prioritizes the most specific type."** The JVM evaluates branches in source-code order. Developers themselves must order them so specialized branches are used properly.

## 15. Common Misconceptions and Mistakes

| Misconception | Reality |
| --- | --- |
| "If three `catch` blocks are compatible, all three run." | Only the first matching branch of the same `try` runs. |
| "The JVM automatically picks the most specific `catch` regardless of order." | Java checks declaration order; a parent branch before a child branch causes a compile error due to shadowing. |
| "If a variable is declared as `IOException`, the actual exception cannot enter `catch (FileNotFoundException)`." | If the runtime object is `FileNotFoundException`, it can be caught by the specialized branch. |
| "`catch (Exception)` catches every `Error`." | No; `Exception` and `Error` are two separate branches under `Throwable`. |
| "An error thrown from the first `catch` will try the second `catch`." | No; the new error propagates to the outer construct. |
| "`finally` runs instead of a `catch`." | No; `finally` has its own execution rules after the `try`/`catch` block has been determined. |
| "Two types in `multi-catch` mean two consecutive `catch` blocks." | No; it is a single branch that can accept one of the declared types. |
| "If no exception occurs, the last `catch` is the default path." | No `catch` runs if `try` completes normally. |
| "Only `catch` branches in the failing method are considered." | Exceptions can propagate up to calling methods until a matching handler is found. |
| "A suppressed error when closing a resource still triggers a `catch` of its own type." | The branch is selected based on the primary exception thrown out of the `try-with-resources` construct. |

## 16. How to Determine Which Branch Runs

When reading any piece of code, follow these four steps:

**Step 1.** Identify the exact **thrown exception object** and its runtime type; inspect `cause` and `suppressed` only when tracing origins, because they do not themselves become the object being classified by `catch`.

**Step 2.** Identify the **nearest `try` construct enclosing the throw point** through which exception propagation is passing. If the error originates from a `catch`, look for a handler in the enclosing construct rather than an adjacent `catch` branch.

**Step 3.** Within that `try` construct, read each `catch` branch **from top to bottom**, checking type compatibility: is the actual type of the error assignable to this `catch` type? If yes, stop searching at the first branch.

**Step 4.** Track whether the selected branch completes normally, executes `return`, or throws again; then consider `finally` and enclosing constructs to determine how the call finishes.

Thought exercise example:

```java
RuntimeException ex = new NumberFormatException("bad");
try {
    throw ex;
} catch (NumberFormatException caught) {
    System.out.println("A");
} catch (IllegalArgumentException caught) {
    System.out.println("B");
} catch (RuntimeException caught) {
    System.out.println("C");
}
System.out.println("D");
```

Output:

```text
A
D
```

The variable `ex` is declared as `RuntimeException`, but the actual object is `NumberFormatException`. Branch `A` matches first, branches `B` and `C` do not run; the `try-catch` construct completes normally, so `D` is printed.

## 17. Self-Check

**Question 1.** Both `catch (IOException)` and `catch (Exception)` can accept `FileNotFoundException`. Which branch runs?  
The **first compatible `catch` branch in declaration order**. In the order just stated, that is `IOException`.

**Question 2.** Can you put `catch (Exception)` before `catch (IOException)` to "prioritize general exceptions"?  
**No.** The subsequent `IOException` branch is completely shadowed and rejected by the compiler.

**Question 3.** If `catch (IOException)` catches an error and then executes `throw new IllegalStateException(...)`, will an adjacent `catch (RuntimeException)` branch receive the new error?  
**No.** The new exception needs a `catch` in an enclosing construct or will continue propagating upward.

**Question 4.** Does `catch (IOException | SQLException ex)` execute twice for a single `IOException`?  
**No.** That is **one** single `catch` branch.

**Question 5.** When `try` completes normally, which `catch` branch runs?  
**None.** Control continues after the `try-catch` construct, with `finally` executed if present.

**Question 6.** Can `catch (Exception)` catch `OutOfMemoryError`?  
**No.** `OutOfMemoryError` belongs to `Error`. It can be caught by a compatible type such as `Error` or `Throwable`, though being able to catch it does not mean you can safely recover.

**Question 7.** If a `FileNotFoundException` is stored in an `IOException` variable and thrown, can `catch (FileNotFoundException)` receive it?  
**Yes.** Handler selection is based on the runtime type of the object.

**Question 8.** The `try-with-resources` body throws `IllegalStateException`, while `close()` throws a suppressed `IOException`. Is `catch (IOException)` selected because of that secondary error?  
**No.** The handler branch is selected based on the primary `IllegalStateException` being thrown.

## References

- [Java Language Specification, Java SE 21 — §14.20.1: Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.1).
- [JLS 21 — §14.20.2: Execution of `try-finally` and `try-catch-finally`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.2).
- [JLS 21 — §14.20.3: `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS 21 — §11.2.3: Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).

**Key Takeaway:** For a `try` handling an exception, Java uses **the actual type of the thrown object** and **the source-code order of `catch` blocks**, selecting **the first compatible branch**. Place child types before parent types, do not expect subsequent `catch` blocks to run as well, and trace `finally` as well as outer `try-catch` constructs when a new exception is thrown.
