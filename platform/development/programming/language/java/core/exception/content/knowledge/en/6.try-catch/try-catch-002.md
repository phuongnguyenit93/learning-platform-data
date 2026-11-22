# Catching Exceptions by Actual Object Type — `try` and `catch` in Java

> **Context:** Java Core → Exception → Try and catch. When an exception is thrown, Java selects a `catch` block based on the **actual type (runtime class) of the propagating `Throwable` object** and its inheritance hierarchy. The type of the reference variable at the `throw` site, the type name in `throws`, and the class inside `getCause()` each have their own role; they **do not replace** the runtime type of the thrown object when deciding the `catch` branch.

## 1. Key Takeaways

Given two classes:

```text
Throwable
└── Exception
    └── RuntimeException
        └── IllegalArgumentException
            └── NumberFormatException
```

For an object `new NumberFormatException(...)`:

- `catch (NumberFormatException e)` can catch it.
- `catch (IllegalArgumentException e)` can also catch it because it is a superclass.
- `catch (RuntimeException e)`, `catch (Exception e)`, and `catch (Throwable e)` are also compatible.
- `catch (IOException e)` is not compatible because it is on a different inheritance branch.
- If multiple `catch` branches follow the same `try`, **the first compatible branch in source-code order** is selected. Because Java checks for unreachable branches, a branch for a subclass must be placed before the superclass that covers it.

Distinguish two phases immediately:

1. **Compile-time:** the compiler checks syntax, valid types for `catch` parameters, handler ordering, and obligations for checked exceptions.
2. **Runtime:** when an object is actually thrown, the JVM inspects the actual type of the object to find a compatible handler enclosing the execution path.

A variable with a declared type of `Exception` can certainly point to a `NumberFormatException`. What matters to `catch` is the **actual object**, provided the code passes the compiler's checks.

## 2. Detailed Handler Selection Rules

Common form:

```java
try {
    operation();
} catch (SpecificException e) {
    handleSpecific(e);
} catch (GeneralException e) {
    handleGeneral(e);
}
```

This is a **syntax pattern**; the classes `SpecificException`/`GeneralException` and handler methods are not defined—this is not a standalone runnable program.

When `operation()` throws a `Throwable` and the error exits that statement, Java searches for a matching handler in sequence:

1. Identify the `Throwable` object being thrown, for example a `NumberFormatException`.
2. Inspect the handlers belonging to the relevant `try` block, in declaration order.
3. For each `catch (T e)`, check whether the object is an instance of `T` or a subclass of `T`. With multi-catch, matching just one of the declared types is sufficient.
4. Select the **first** handler that satisfies the condition; the variable `e` references the thrown object.
5. If there is no matching handler in the current scope, the error propagates to the calling method; Java continues searching outer handlers and executing cleanup steps according to the rules.
6. If the error goes unhandled up to the thread boundary, the thread's uncaught exception mechanism receives it; one should not assume every uncaught exception must immediately terminate the entire JVM.

**Important:** `catch` does not use an "exact type match" comparison. It supports **polymorphism**: a handler declaring a superclass type can catch an exception belonging to a subclass.

### 2.1. Type Compatibility Check

Intuitively, the selection rule for a single handler can be pictured as:

```java
// Conceptual illustration, not the JVM implementation.
if (thrown instanceof HandlerType) {
    // The corresponding handler can receive the thrown object.
}
```

The snippet above is **illustrative** code, where `HandlerType` represents the actual catch class name. Java compiles handlers into an exception-handling mechanism rather than literally running this `if` statement.

A `catch (Exception e)` can catch `IllegalArgumentException`, `IOException`, or `NullPointerException` because all of them are subclasses of `Exception`. However, it does not catch `AssertionError`, because `AssertionError extends Error` and `Error` does not inherit from `Exception`.

### 2.2. Quick Reference Table

| Actual Object Thrown | `catch (NumberFormatException)` | `catch (IllegalArgumentException)` | `catch (Exception)` | `catch (Error)` |
| --- | --- | --- | --- | --- |
| `new NumberFormatException()` | Yes | Yes | Yes | No |
| `new IllegalArgumentException()` | No | Yes | Yes | No |
| `new IllegalStateException()` | No | No | Yes | No |
| `new java.io.IOException()` | No | No | Yes | No |
| `new AssertionError()` | No | No | No | Yes |

The table records **type compatibility**. You cannot arbitrarily combine any handlers into a `try` block and expect the program to always compile: Java also checks for unreachable handler ordering and the status of checked exceptions that can be thrown from the `try` region.

## 3. Java 17 Program: Same Variable Type, Multiple Actual Object Types

This example demonstrates the most easily confused point: all elements in the array have the **variable type `Exception`**, but the actual objects belong to three different classes, so each throw can enter a different `catch` branch.

Save the file `CatchRuntimeTypeDemo.java`:

```java
import java.io.IOException;

public class CatchRuntimeTypeDemo {
    static void propagate(Exception problem) throws Exception {
        throw problem;
    }

    public static void main(String[] args) {
        Exception[] problems = {
                new NumberFormatException("không phải số"),
                new IllegalStateException("trạng thái sai"),
                new IOException("không đọc được")
        };

        for (Exception problem : problems) {
            try {
                propagate(problem);
            } catch (NumberFormatException e) {
                System.out.println("Parse: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("I/O: "
                        + e.getClass().getSimpleName());
            } catch (Exception e) {
                System.out.println("Còn lại: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CatchRuntimeTypeDemo.java
java CatchRuntimeTypeDemo
```

**Exact stdout:**

```text
Parse: NumberFormatException
Còn lại: IllegalStateException
I/O: IOException
```

Case-by-case explanation:

- `problem` has the **declared type `Exception`** in all three iterations.
- In the first iteration, the actual object is `NumberFormatException`. The specific handler catches it.
- In the second iteration, it is `IllegalStateException`. It is neither `NumberFormatException` nor `IOException`, so it is caught by the general handler `catch (Exception e)`.
- In the third iteration, it is `IOException`. The handler `catch (IOException e)` catches it.
- `propagate(Exception problem) throws Exception` executes `throw problem;` and declares the broad checked type `Exception`. This example intentionally uses a general signature to clarify the difference; in real APIs, you should declare narrow, meaningful types whenever possible.

We **do not need to cast** from `Exception` to `NumberFormatException` before throwing. As long as the variable references the right object, its runtime type will be used in handler selection.

### 3.1. Difference Between Variable Type and Object Type

Core pattern:

```java
Exception declaredAsException =
        new NumberFormatException("bad input");
// declaredAsException.getClass() is NumberFormatException.class.
```

This is an illustrative snippet inside a method. On the left, `Exception` is the **static type** that the compiler uses to check which operations can be called, especially for checked exceptions. On the right, a **`NumberFormatException`** object is created. There is no "conversion" that turns the object into a more general `Exception`; the reference is assigned to a superclass type, while the object retains its exact class.

Calling `getClass()` is a way to observe an object's runtime type. The `instanceof` check also reflects the instance/subtype relationship, though you usually do not need to use it manually to select a handler because the `catch` construct already handles that job.

## 4. Inheritance Determines a Handler's Scope

Simplified hierarchy:

```text
Throwable
├── Error
│   └── AssertionError
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        └── IllegalStateException
```

A `catch (IOException e)` can catch `FileNotFoundException` or `EOFException`. However, it does **not** catch `NumberFormatException`, even though both branches ultimately inherit from `Exception`.

Example:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Chuỗi không phải số");
} catch (IllegalArgumentException e) {
    System.out.println("Tham số sai theo quy tắc khác");
}
```

This is a **snippet inside a method**. `NumberFormatException` inherits from `IllegalArgumentException`, so both handlers are **type-compatible**, but the more specific handler placed first receives the object. The later handler will only be considered if the earlier handler is incompatible with a different exception being thrown.

### 4.1. Why Must a Subclass `catch` Be Placed Before Its Superclass?

The following snippet is **intentionally wrong and does not compile**:

```java
try {
    Integer.parseInt("abc");
} catch (IllegalArgumentException e) {
    System.out.println("Đã bắt");
} catch (NumberFormatException e) {
    System.out.println("Không thể tới đây");
}
```

`IllegalArgumentException` already covers `NumberFormatException`. The second handler has no chance of receiving any remaining object of type `NumberFormatException`, so Java reports an error such as "exception NumberFormatException has already been caught".

Correct order from **specific to general**:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException e) {
    System.out.println("Sai định dạng số");
} catch (IllegalArgumentException e) {
    System.out.println("Sai tham số");
}
```

This is also an illustrative snippet, without `main`. The order here does not change the object's type; it determines **the first handler that gets a chance to catch it**.

### 4.2. Each Exception Enters Only One `catch` Branch of the Same `try`

Once a matching handler is selected, Java does not continue executing the remaining `catch` blocks like a chain of `if` statements. If you need detailed classification before consolidating into common handling, have the specific handler call a shared helper method, or normalize the information at a responsible layer. Do not expect a trailing `catch (Exception)` to run after `catch (NumberFormatException)`.

## 5. Checked Exceptions Affect the Compiler, Not Runtime Matching

**Checked** and **unchecked** are rules about whether catching or declaring is required at compile time:

- Checked exceptions include subclasses of `Throwable` that are not under the `RuntimeException` or `Error` branches, such as `IOException`.
- Unchecked exceptions include `RuntimeException`, `Error`, and their subclasses, such as `NumberFormatException` or `AssertionError`.

Even though `NumberFormatException` is unchecked, `catch (Exception e)` still catches it because `NumberFormatException extends RuntimeException extends Exception`.

Conversely, a custom class that **directly inherits from `Throwable`** can be checked, yet `catch (Exception)` still cannot catch it because that class is not under `Exception`. Therefore:

**Whether an exception is checked or unchecked is not the criterion for selecting a handler at runtime. The type inheritance relationship is.**

### 5.1. Static Type Affects `throws` Obligations

Example:

```java
// This is an illustrative snippet inside a method, not a complete program.
Exception e = new NumberFormatException("sai số");
// throw e; // If uncommented: typically requires catching or declaring Exception.
```

Because the expression `e` has the **declared type `Exception`**, the compiler evaluates `throw e;` according to this broad checked type, even though the concrete object in the illustrative run is unchecked. This does not mean `catch` will select based on `Exception`: at runtime, if the thrown object is still `NumberFormatException`, `catch (NumberFormatException)` still matches.

Distinguish this from **precise rethrow** since Java 7: under certain conditions with a `catch` parameter variable that is not reassigned, the compiler can infer the specific set of checked exceptions when encountering `throw e;`. That is a special language rule for checked-exception analysis and does not change how runtime handler selection works.

### 5.2. Example of `throws IOException` with a Subclass at Runtime

Method:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("Không tìm thấy dữ liệu");
}
```

The illustrative snippet above is valid because `FileNotFoundException extends IOException`. The caller can write `catch (FileNotFoundException e)` before `catch (IOException e)` if the `try` block can receive that kind of error. At runtime, if a `FileNotFoundException` object itself is thrown, the narrow handler is selected. The name `IOException` in the `throws` clause only advertises the checked type that the caller must account for; it does not "turn" the object into class `IOException`.

## 6. Java 17 Program: Multiple Subclasses of `IOException`

The second example emphasizes that **the same method declaring `throws IOException`** can throw a different subtype on each run; the handlers process it according to its actual type.

Save `CatchIoSubtypeDemo.java`:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchIoSubtypeDemo {
    static void read(String mode) throws IOException {
        switch (mode) {
            case "missing" ->
                    throw new FileNotFoundException("Thiếu tệp");
            case "empty" ->
                    throw new EOFException("Hết dữ liệu");
            default ->
                    throw new IOException("Lỗi I/O chung");
        }
    }

    public static void main(String[] args) {
        for (String mode : new String[] {"missing", "empty", "other"}) {
            try {
                read(mode);
            } catch (FileNotFoundException e) {
                System.out.println(mode + ": thiếu tệp");
            } catch (EOFException e) {
                System.out.println(mode + ": hết dữ liệu");
            } catch (IOException e) {
                System.out.println(mode + ": lỗi I/O chung");
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CatchIoSubtypeDemo.java
java CatchIoSubtypeDemo
```

Stdout:

```text
missing: thiếu tệp
empty: hết dữ liệu
other: lỗi I/O chung
```

Interpretation:

- In `"missing"` mode, the method creates `FileNotFoundException` and the `FileNotFoundException` handler catches it.
- In `"empty"` mode, the method creates `EOFException` and the `EOFException` handler catches it.
- In `"other"` mode, the method creates `IOException` itself and the general `IOException` handler catches it.
- All three satisfy the `throws IOException` declaration; this declaration does not force every call to throw the exact same subtype.
- When a specific handler matches, the final `catch (IOException)` branch does not execute afterward.

**Design point:** catch a specific subtype when the caller has a distinct action to take—for example, allowing another file to be chosen if not found, finishing reading upon EOF according to an appropriate contract, or stopping the operation on other I/O errors. If there is no distinct action, a single general `catch (IOException)` may be sufficient.

## 7. Runtime Type Determines Matching, but Handler Order Still Matters

When multiple handlers are compatible with an object, Java selects the **first handler in the same `catch` chain**. However, the compiler rejects arrangements that make later branches unreachable.

Consider `new NumberFormatException()`:

```text
catch (NumberFormatException e)  ← compatible and comes first: catches the error
catch (IllegalArgumentException e) ← also compatible, but does not run
catch (Exception e)              ← also compatible, but does not run
```

If you change the order and put `catch (Exception e)` at the top, the subsequent subclass handlers are shadowed and cause a compile error. Therefore, the practical rule that is both semantically right and accepted by the compiler is:

> **Place subclass/specific `catch` blocks first, and superclass/general `catch` blocks after.**

Not all exception classes have a parent–child relationship. For instance, `FileNotFoundException` and `NumberFormatException` do not cover each other; type-wise, they can be placed in either order if the `try` block can produce the corresponding checked types. Ordering matters most when there is a **subsumption relationship**.

### 7.1. A Note on Nested `try` Blocks

Java does not compare every `catch` in the entire program at once. Handlers in the `try` **closest to where the error occurs** are checked first within their control scope; only if no matching handler is found does the error propagate outward.

Example:

```java
try {
    try {
        Integer.parseInt("abc");
    } catch (IllegalArgumentException e) {
        System.out.println("Bắt bên trong");
    }
} catch (NumberFormatException e) {
    System.out.println("Bắt bên ngoài");
}
```

This is an illustrative snippet placed inside a method. Because the inner `IllegalArgumentException` catches `NumberFormatException`, the outer handler is not executed. The exception has already been handled in a closer scope; there is no "mechanism that picks the most specific handler across the entire program".

If the inner handler **rethrows** the exception, it can propagate to the `catch` of the enclosing `try`, but that is a subsequent propagation step—not Java skipping the inner handler to pick the outer one automatically.

## 8. Multi-Catch Also Matches by Object Type

Since Java 7, handlers with the same logic can be combined:

```java
catch (java.io.IOException | IllegalArgumentException e) {
    System.out.println("Không xử lý được yêu cầu: " + e.getMessage());
}
```

The snippet above is an illustrative `catch` clause and must follow an appropriate `try` block. A multi-catch matches if the object is an instance of **at least one** of the listed types. `IOException` and `IllegalArgumentException` belong to two separate branches, so they can be written together.

Java **does not allow** types in the same multi-catch to have a direct or indirect inheritance relationship such that one branch already covers another. Invalid example:

```java
// INVALID:
catch (NumberFormatException | IllegalArgumentException e) {
    System.out.println(e);
}
```

`NumberFormatException extends IllegalArgumentException`, so declaring both alternatives is redundant and rejected by the compiler.

### 8.1. Standalone Java 17 Program with Multi-Catch

Save `MultiCatchRuntimeDemo.java`:

```java
import java.io.IOException;

public class MultiCatchRuntimeDemo {
    static void execute(String input) throws IOException {
        if (input == null) {
            throw new IOException("Nguồn trống");
        }
        int number = Integer.parseInt(input);
        if (number <= 0) {
            throw new IllegalArgumentException("Phải dương");
        }
        System.out.println("OK: " + number);
    }

    public static void main(String[] args) {
        for (String input : new String[] {"5", "abc", "0", null}) {
            try {
                execute(input);
            } catch (IOException | IllegalArgumentException e) {
                System.out.println("Lỗi: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 MultiCatchRuntimeDemo.java
java MultiCatchRuntimeDemo
```

Stdout:

```text
OK: 5
Lỗi: NumberFormatException
Lỗi: IllegalArgumentException
Lỗi: IOException
```

`NumberFormatException` is caught by the multi-catch **via the `IllegalArgumentException` alternative**. `IOException` is caught via the other alternative. The same handler block uses `getClass().getSimpleName()` to observe the actual subtype, so the printed names still differ.

The variable `e` in a multi-catch is **implicitly final** and cannot be reassigned. The common static type of `e` is also not necessarily any single specific subtype; if you need an API specific to one subtype, use a separate handler or check the type carefully.

## 9. `catch (Exception)` Does Not Catch Every `Throwable`

A fundamental condition of the hierarchy:

```text
Throwable
├── Exception
│   └── RuntimeException
│       └── NumberFormatException
└── Error
    └── AssertionError
```

`catch (Exception e)` can handle `NumberFormatException`, but it does **not** catch `AssertionError` because `Error` does not inherit from `Exception`. `catch (Throwable t)` can catch both **in terms of types**, but it should not be used as a "catch-all" solution in application code.

### 9.1. Demonstration Without Triggering a Real JVM Error

Save `CatchThrowableBranchesDemo.java`:

```java
public class CatchThrowableBranchesDemo {
    static void fail(boolean useError) {
        if (useError) {
            throw new AssertionError("Tình huống kiểm thử");
        }
        throw new IllegalStateException("Trạng thái không hợp lệ");
    }

    public static void main(String[] args) {
        for (boolean useError : new boolean[] {false, true}) {
            try {
                fail(useError);
            } catch (Exception e) {
                System.out.println("Exception: "
                        + e.getClass().getSimpleName());
            } catch (Error e) {
                System.out.println("Error: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CatchThrowableBranchesDemo.java
java CatchThrowableBranchesDemo
```

Stdout:

```text
Exception: IllegalStateException
Error: AssertionError
```

The example **deliberately creates `AssertionError` to explain the type system**; this is not a recommendation to catch `Error` to try recovering from VM errors like `OutOfMemoryError` or `StackOverflowError`. Do not trigger real VM errors just to test handlers, as doing so can leave the process without enough resources to run normally.

### 9.2. Checked/Unchecked Does Not Determine the Handler

- `IOException` is checked and is under `Exception`.
- `IllegalStateException` is unchecked and is also under `Exception`.
- `AssertionError` is unchecked, but it is under `Error`.

Both checked and unchecked exceptions follow the same `catch` selection rule based on **runtime type**. The checked/unchecked classification only governs certain compile-time obligations.

## 10. Wrappers and `cause`: Java Catches the Outer Thrown Class

An exception can contain another exception as its **cause** (`cause`). Example:

```java
throw new IllegalStateException(
        "Không hoàn tất thao tác",
        new java.io.IOException("Nguồn dữ liệu lỗi"));
```

Here:

- The object **being thrown** is `IllegalStateException`.
- Its `getCause()` points to `IOException`.
- A handler `catch (IllegalStateException)` or `catch (Exception)` can catch the wrapper.
- A handler `catch (IOException)` does not automatically extract `cause` to catch it; to handle the cause, you need to inspect it after catching the wrapper at an appropriate layer.

This mechanism avoids the misconception that Java automatically "unwraps" the cause chain to pick a handler. **It compares the type of the object being thrown**, rather than searching for the deepest matching type inside `getCause()`.

### 10.1. Java 17 Program Demonstrating Wrapper/Cause

Create `CatchWrapperTypeDemo.java`:

```java
import java.io.IOException;

public class CatchWrapperTypeDemo {
    static void load() {
        IOException original = new IOException("Không đọc được");
        throw new IllegalStateException("Không tải được dữ liệu", original);
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (IllegalStateException e) {
            System.out.println("Đã bắt: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CatchWrapperTypeDemo.java
java CatchWrapperTypeDemo
```

Stdout:

```text
Đã bắt: IllegalStateException
Cause: IOException
Message: Không tải được dữ liệu
```

In this snippet, `IOException` is only **created and passed to the constructor** as the cause; it does not propagate out of `load()` as the main exception object. Therefore, `load()` does not need to declare `throws IOException`. The handler in `main` catches `IllegalStateException` as expected.

**Reverse scenario:** if the wrapper is an `IOException` with an `IllegalStateException` as its cause, the selected handler is still based on the `IOException` wrapper class. The cause holds diagnostic and contextual information; it does not replace the matching mechanism.

### 10.2. Does Rethrowing Change the Runtime Type?

`throw e;` rethrows **the exact same object** that `e` references. It does not automatically convert the object to the variable's declared type.

Example:

```java
// Illustrative snippet in a method with throws Exception.
Exception e = new NumberFormatException("Sai số");
throw e;
```

If thrown successfully at runtime, the object is still a `NumberFormatException`. The `throws Exception` declaration is required due to static type checking in this typical case, yet a compatible handler in the caller will evaluate the actual object type.

By contrast, `throw new IllegalStateException("...", e)` creates a new wrapper: **the runtime type of the propagating exception has become `IllegalStateException`**, while `e` is the cause. That is a major distinction when deciding whether to rethrow or translate an exception.

## 11. Can an Exception Thrown Inside `catch` Be Caught by the Next `catch` Branch?

No. The `catch` branches of the same `try` are **alternative handlers**, not nested around each other. A new exception thrown **inside a handler itself** will not be caught by subsequent handlers attached to the same `try`.

Example:

```java
try {
    try {
        throw new NumberFormatException("bad");
    } catch (NumberFormatException e) {
        throw new IllegalStateException("Bọc lỗi", e);
    } catch (IllegalStateException e) {
        System.out.println("Không bắt wrapper từ catch phía trên");
    }
} catch (IllegalStateException e) {
    System.out.println("Wrapper được bắt ở try ngoài");
}
```

This is an illustrative snippet inside a method. The `NumberFormatException` handler is selected when the original exception is thrown; that handler then creates a new `IllegalStateException`. The remaining `IllegalStateException` handler of **the same inner `try`** does not run; the compatible handler of the **outer** `try` catches the wrapper.

Note that the compiler only checks for unreachable branches according to type rules, whereas the difference between an error thrown in `try` and an error thrown in `catch` is a **handler-scope** rule. Do not assume that two handler branches form a sequential processing pipeline.

## 12. Role of `finally` and Try-with-Resources

When an exception is thrown and a matching handler is found, the relevant `finally` blocks are executed according to Java rules upon exiting the scope. This mechanism supports cleanup, but **does not re-decide** which exception type is propagating.

```java
try {
    throw new NumberFormatException("bad");
} catch (IllegalArgumentException e) {
    System.out.println("Đã bắt ngoại lệ con qua kiểu cha");
} finally {
    System.out.println("Đã dọn dẹp");
}
```

The illustrative snippet above prints:

```text
Đã bắt ngoại lệ con qua kiểu cha
Đã dọn dẹp
```

`NumberFormatException` is actually thrown, yet the `IllegalArgumentException` handler still catches it due to inheritance.

**Important caveat:** if `finally` itself throws another exception or executes `return`, it can replace or mask the result or pending exception. Avoid writing `return` inside `finally` or throwing new errors from cleanup code if your goal is to preserve the original cause.

With try-with-resources, if both the block body and `close()` throw exceptions, Java typically keeps the error from the block body as the primary exception and attaches the close error to `getSuppressed()`. Outer `catch` blocks match against **the primary exception being thrown**, not directly against suppressed exceptions.

## 13. Quick Check Questions

### 13.1. Can an `Exception` variable be caught by `catch (IOException)`?

**Yes**, if the actual object thrown is `IOException` or a subtype and the code is valid under checked-exception rules. In `CatchRuntimeTypeDemo`, `problem` has the variable type `Exception`, yet the third iteration is properly caught by `catch (IOException)`.

### 13.2. Does `catch (Exception)` catch all unchecked exceptions?

**No.** It catches unchecked exceptions under the `RuntimeException` branch, because `RuntimeException extends Exception`. It does not catch unchecked types under the `Error` branch, such as `AssertionError`.

### 13.3. Does `catch (Throwable)` catch every error regardless of where it occurs?

**No.** It is a broad handler in Java's type system, but it only handles `Throwable`s that reach the handler on **the protected control flow**. It does not automatically catch exceptions occurring on another thread, does not protect against abnormal JVM/process termination, and does not roll back side effects.

### 13.4. Is the narrowest handler always chosen even if placed after a broader handler?

**No.** Java uses the **first compatible handler in the corresponding `catch` scope**. The compiler blocks many orderings where a later handler would be shadowed by an earlier broad handler. Java does not search for the "narrowest handler across the entire call stack" and skip a closer handler.

### 13.5. If `getCause()` is `IOException`, does `catch (IOException)` catch an `IllegalStateException` wrapper?

**No.** `cause` is a causal relationship for diagnostics and does not participate directly in `catch` selection. To handle semantically by cause, first catch the appropriate wrapper and then inspect the cause intentionally.

### 13.6. If `catch (IllegalArgumentException)` catches `NumberFormatException`, what does `e.getClass()` return?

It returns **`NumberFormatException.class`**, because the variable `e` still references the subclass object. Java does not change the object's actual class just because the handler has a broader declared type.

### 13.7. Can one exception be handled by two handlers of the same `try` block?

**Not automatically.** A thrown exception selects one first handler. If the handler rethrows or creates a new exception, a handler in an enclosing scope may catch it next, but not a subsequent branch of the same `catch` chain.

## 14. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "A variable of type `Exception` can only be caught by `catch (Exception)`." | The object's actual type can be a subtype; a compatible narrow handler can still catch it. |
| "`throws IOException` changes the actual exception into `IOException`." | The `throws` clause declares a checked contract; a `FileNotFoundException` object keeps its own class. |
| "`catch` only matches the exact same class name." | A superclass type also catches objects belonging to subclasses. |
| "`catch` blocks run sequentially like multiple independent `if` checks." | Only the first compatible handler of the same `try` is executed. |
| "Placing `catch (Exception)` before `catch (NumberFormatException)` is valid because it is broader." | The later branch is shadowed and rejected by the compiler. |
| "Unchecked exceptions cannot be caught by `catch`." | Unchecked exceptions do not require compile-time handling, but they can still be caught. |
| "`catch (Exception)` catches `AssertionError` because it is also a Throwable." | `AssertionError` is under `Error`, which is a separate branch from `Exception`. |
| "Handlers automatically inspect `getCause()` to pick a matching error class." | Handlers only match against the type of the object being thrown. |
| "An exception thrown inside `catch` will be handled by the next `catch` branch." | It exits to the outer scope unless handled by a new `try`. |
| "Catching an error restores all prior state back to how it was." | `catch` does not automatically roll back data changes, I/O, or transactions. |
| "Catching `Throwable` everywhere is safer." | It can mask serious runtime errors and allow the program to continue in an untrusted state. |
| "A stack trace is a list of handlers that were tried." | A stack trace reflects the call chain and origin of the error, not a full log of `catch` branches tested. |

## 15. Practice Exercises

### Exercise 1 — Predict the Handler by Actual Class

Given the illustrative snippet:

```java
Exception problem = new NumberFormatException("Sai");
try {
    throw problem;
} catch (NumberFormatException e) {
    System.out.println("A");
} catch (IllegalArgumentException e) {
    System.out.println("B");
} catch (Exception e) {
    System.out.println("C");
}
```

This snippet is placed inside a method where checked-exception obligations are handled by the handlers. **Answer:** prints `A`. Although `problem` is a variable of type `Exception`, the actual object is `NumberFormatException`. If you remove `catch (NumberFormatException)`, the output becomes `B`; if you also remove `catch (IllegalArgumentException)`, the output becomes `C`.

### Exercise 2 — Fix the Unreachable Handler Error

Starting from:

```java
try {
    Integer.parseInt("x");
} catch (RuntimeException e) {
    System.out.println("Rộng");
} catch (NumberFormatException e) {
    System.out.println("Hẹp");
}
```

Swap the order so that the `NumberFormatException` handler comes first. Explain why the original snippet does not compile: `NumberFormatException` is a subclass of `RuntimeException` and is already covered by the broader handler.

### Exercise 3 — Swap the Wrapper and Predict the Handling Branch

In `CatchWrapperTypeDemo`, try replacing `IllegalStateException` with `java.io.UncheckedIOException` having an `IOException` cause, then update the outer handler to catch `UncheckedIOException` or `RuntimeException`. Explain why `catch (IOException)` does not automatically catch the wrapper. If you use the actual constructor `new UncheckedIOException(original)`, remember to import `java.io.UncheckedIOException`.

### Exercise 4 — Trace an Exception Across Multiple Layers

Write three methods `main() → service() → parse()`. In `parse()`, throw `NumberFormatException`; in `service()`, declare `throws Exception` or forward the exception appropriately; in `main()`, specifically catch `NumberFormatException`. Explain **the static type read by the compiler at each call site** and **the runtime type matched by the handler**.

### Exercise 5 — Replace a `catch` Chain with Multi-Catch

In `MultiCatchRuntimeDemo`, replace the multi-catch handler with two separate handlers for `IOException` and `IllegalArgumentException` so each type displays a different message. Is a separate handler for `NumberFormatException` required? **Not required** because `IllegalArgumentException` already covers it, though one can be added **before** the parent handler if a distinct parse-error message is needed.

### Exercise 6 — Error Thrown Inside a Handler

Predict the stdout of the example in Section 11. Explain why the outer handler receives the new `IllegalStateException` and why the remaining `catch (IllegalStateException)` handler of the inner `try` does not run.

## 16. Comprehension Checklist

- [ ] Distinguish **variable type**, **declared type in `throws`**, and **object runtime type**.
- [ ] Diagram the relationship `NumberFormatException → IllegalArgumentException → RuntimeException → Exception → Throwable`.
- [ ] Explain why `catch (IOException)` catches `FileNotFoundException` and `EOFException`.
- [ ] Place subclass handlers before superclass handlers to avoid unreachable catch errors.
- [ ] Run `CatchRuntimeTypeDemo.java` and explain all three stdout lines.
- [ ] Run `CatchIoSubtypeDemo.java` and correctly predict the handler for each subtype.
- [ ] Write a multi-catch with two unrelated types and state why overlapping types are disallowed.
- [ ] Know that `catch (Exception)` catches unchecked `RuntimeException`s but does not catch `Error`s.
- [ ] Distinguish wrapper and cause; handlers match based on the wrapper being thrown, without descending into `cause`.
- [ ] Recognize that an exception thrown from a `catch` requires an appropriate handler in another scope.
- [ ] Avoid confusing `finally`/try-with-resources with handler selection or rollback.
- [ ] Design `catch` blocks around actual recovery capability rather than swallowing errors unconditionally.

**Final reminder:** The **runtime type** of the thrown `Throwable` object determines which `catch` blocks are compatible; the `try` scope and branch ordering determine which handler is selected; the compiler checks type and checked-exception rules before the program runs. Understanding all three together lets you accurately predict exception-handling flow in Java.