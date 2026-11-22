# Using `try-catch` to Handle Operations That Can Fail in Java

## 1. Why Do We Need `try-catch`?

When running a Java program, certain operations can fail: converting an invalid string to a number, reading a file, using an invalid array index, or calling an external service. Java represents many such situations with **exceptions**. Instead of letting an unhandled exception abnormally terminate the current execution thread, we can use `try-catch` to **respond intentionally**.

Basic structure:

```java
try {
    // Statements that may throw an exception.
} catch (SomeException ex) {
    // Handle the exact caught exception type.
}
```

- The **`try`** block contains the operations to guard.
- When a statement throws an exception, the remaining statements in the `try` block **do not continue along the normal path**.
- Java looks for a `catch` whose type matches the exception object, checking `catch` blocks in order.
- **`ex`** is the parameter referencing the exception object, allowing access to details such as `getMessage()` or calling `printStackTrace()`.
- After a `catch` finishes handling without rethrowing or returning, execution continues at the statement after the `try-catch` structure.
- If **there is no matching `catch`**, the exception propagates to the caller. If nothing handles it, it may terminate the thread with a stack trace.

`try-catch` does not automatically fix a wrong calculation or make invalid input data valid; it only defines **how to behave when a failure occurs**.

## 2. Minimal Example: Converting a String to a Number

`Integer.parseInt(String)` converts text to an `int`, but a string that does not represent a valid integer causes `NumberFormatException`.

```java
String input = "abc";

try {
    int value = Integer.parseInt(input);
    System.out.println("Gia tri: " + value);
} catch (NumberFormatException ex) {
    System.out.println("Du lieu khong phai so nguyen hop le");
}

System.out.println("Tiep tuc chuong trinh");
```

This is an **illustrative snippet placed inside a method**, not a standalone runnable file. When `input = "abc"`, the line printing the value does not run, the `catch` branch prints the message, and then the statement outside `try-catch` executes.

With `input = "123"`, the `catch` branch does not run, and `value` equals `123`. A variable `value` declared **inside `try`** is not in scope for statements after the block, so if you need to use the result later, you can return it from a method or design appropriate state.

Do not assume every numeric conversion failure can be fixed by substituting an arbitrary value. Depending on requirements, the right choice might be prompting the user to re-enter, rejecting the data, logging and propagating the exception, or returning a result that represents failure.

## 3. Catch Specific Exception Types First

Each `catch` catches the declared exception type or any of its subtypes. Therefore, you should **catch specific types first** and more general types later:

```java
try {
    // Process input, compute.
} catch (NumberFormatException ex) {
    System.out.println("Sai dinh dang so");
} catch (IllegalArgumentException ex) {
    System.out.println("Doi so khong hop le");
}
```

`NumberFormatException` is a subtype of `IllegalArgumentException`. If you place `catch (IllegalArgumentException ...)` **first**, the subsequent `NumberFormatException` catch block becomes unreachable, causing a **compile-time error**. In the example above, the order is written correctly.

Do not catch `Exception` or `Throwable` overly broadly at every layer of a program:

- Catching too broadly causes unexpected programming bugs to be treated like ordinary data errors.
- `Throwable` also includes the `Error` branch, such as `OutOfMemoryError`, which ordinary application code should not attempt to "swallow."
- An empty `catch` discards the failure signal, making debugging difficult.
- When you cannot recover locally, you can **let the exception propagate**, or wrap the cause in an exception with higher-level meaning.

Example of forwarding with a clear cause:

```java
static int parseAge(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Age must be a whole number", ex);
    }
}
```

This is an **illustrative method placed inside a class**. The `IllegalArgumentException(String, Throwable)` constructor preserves the original exception in `getCause()`, which is useful when handling errors at a layer with sufficient context. Do not wrap exceptions mechanically when doing so adds no meaning.

## 4. Multiple `catch` Blocks and Multi-Catch

If different exception types need separate handling, use multiple `catch` blocks. If they need **the same handling**, you can use multi-catch (Java 7+):

```java
try {
    String text = args[0];
    int value = Integer.parseInt(text);
    System.out.println(value);
} catch (ArrayIndexOutOfBoundsException | NumberFormatException ex) {
    System.out.println("Can mot doi so nguyen hop le");
}
```

This is an illustrative snippet inside a method that has an appropriate `args` variable. Both exceptions require the same response: "a valid integer argument is needed." Types in the same multi-catch **must not have a direct subtype/supertype relationship**; for example, `catch (NumberFormatException | IllegalArgumentException ex)` is a compile-time error because one branch already subsumes the other.

When designing real programs, it is better to check `args.length` to detect a missing argument, and then use `catch (NumberFormatException)` for the conversion failure. Do not use exceptions to replace ordinary conditional branches.

**Once an exception is caught**, only the first matching `catch` runs; execution does not "fall through" to lower `catch` blocks. A `catch` block can throw a new exception; that new exception is not handled by other `catch` blocks of the **same `try` structure**, and must instead be handled by an appropriate enclosing scope.

## 5. Handling Checked/Unchecked Exceptions According to the Operation's Contract

If an API can throw checked `IOException`, such as `Files.readString`, the caller must **catch** it or declare `throws` per Java rules. Conversely, `Integer.parseInt("abc")` throws unchecked `NumberFormatException`, which is not required to be declared, though it can still be caught when invalid data is an expected scenario.

~~~java
static String readText(java.nio.file.Path file)
        throws java.io.IOException {
    return java.nio.file.Files.readString(file);
}
~~~

`throws` only allows a checked exception to exit the method; it is not a handler. `Error` types like `OutOfMemoryError` are also unchecked, though generally unsuitable to catch and continue business logic. The `Throwable` hierarchy, compiler rules, and throwing exceptions yourself are explained in depth in the next two lessons.

## 6. `finally` Still Performs Normal Cleanup

~~~java
try {
    System.out.println("start");
    throw new IllegalStateException("bad");
} catch (IllegalStateException ex) {
    System.out.println("caught");
} finally {
    System.out.println("cleanup");
}
~~~

These three print statements output `start`, `caught`, and `cleanup` in order. `finally` normally runs when an exception or `return` exits the block, though **it is not guaranteed when the JVM/process is terminated abruptly**. Avoid `return` or throwing new exceptions in `finally` if doing so could mask the previous result or exception.

## 7. Closing Resources with `try-with-resources`

~~~java
static String firstLine(java.nio.file.Path file)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(file)) {
        return reader.readLine();
    }
}
~~~

Resources must support `AutoCloseable`; Java closes them automatically when leaving the block via normal completion or an exception. If there are multiple resources, they are **closed in reverse order of initialization**. When both the body and closing fail, the close exception may appear in `getSuppressed()`; checked I/O exceptions **must still be caught or declared**, and do not automatically turn into success.

In this `try-catch` lesson, the key takeaway is **handling failures appropriately**. A dedicated lesson on `finally` and `try-with-resources` covers return behavior, masking, close order, and suppressed exceptions in depth.


## 8. Standalone Java 17+ Program with Deterministic Output

Create a file named **`TryCatchDemo.java`**:

```java
import java.io.IOException;

public class TryCatchDemo {
    static class TrackedResource implements AutoCloseable {
        void use() {
            System.out.println("Dang su dung tai nguyen");
        }

        @Override
        public void close() {
            System.out.println("Da dong tai nguyen");
        }
    }

    static String checkValue(int value) throws IOException {
        if (value < 0) {
            throw new IOException("Gia tri am");
        }
        return "OK";
    }

    public static void main(String[] args) {
        try {
            int number = Integer.parseInt("abc");
            System.out.println("So: " + number);
        } catch (NumberFormatException ex) {
            System.out.println("Sai dinh dang: " + ex.getClass().getSimpleName());
        }

        int divisor = 0;
        try {
            int result = 12 / divisor;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("Khong the chia cho 0");
        } finally {
            System.out.println("Finally da chay");
        }

        try {
            String value = checkValue(-1);
            System.out.println(value);
        } catch (IOException ex) {
            System.out.println("Checked: " + ex.getMessage());
        }

        try (TrackedResource resource = new TrackedResource()) {
            resource.use();
        }

        int[] numbers = {3, 5};
        try {
            System.out.println(numbers[2]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Chi so vuot gioi han");
        }

        System.out.println("Chuong trinh van tiep tuc");
    }
}
```

Use JDK 17 or later. In the directory containing `TryCatchDemo.java`, run the same commands on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 TryCatchDemo.java
java TryCatchDemo
```

**Exact stdout** (when compilation succeeds, `javac` prints nothing):

```text
Sai dinh dang: NumberFormatException
Khong the chia cho 0
Finally da chay
Checked: Gia tri am
Dang su dung tai nguyen
Da dong tai nguyen
Chi so vuot gioi han
Chuong trinh van tiep tuc
```

Step-by-step explanation:

1. `Integer.parseInt("abc")` throws `NumberFormatException`; the `So:` line is skipped and the matching `catch` prints the exception name.
2. `12 / divisor` with `divisor == 0` causes `ArithmeticException`; `catch` prints the message and `finally` always runs along this normal execution path.
3. `checkValue(-1)` explicitly throws `IOException` (a checked exception), which is handled by `catch` with message `Gia tri am`.
4. `TrackedResource` is created in try-with-resources; `resource.use()` prints one line, then `close()` prints the next line upon exiting the block.
5. Accessing `numbers[2]` on a two-element array causes `ArrayIndexOutOfBoundsException`, which is handled; execution continues to the final print statement.

Catching these exceptions here is for **demonstration**; it does not mean real applications should catch array index errors to hide invalid indexing. Fix array access conditions and use `catch` for failures that the application has a sensible way to handle.

## 9. Choosing a Strategy Instead of "Swallowing" Exceptions

There are several strategies depending on business requirements.

| Situation | Typically Appropriate Strategy |
| --- | --- |
| User enters a non-numeric string | Catch `NumberFormatException`, show a clear message, and ask for re-entry |
| Input file does not exist or cannot be read | Catch `IOException` at a layer that knows whether to retry, report an error, or cancel the operation |
| Argument violates a precondition before processing | Check upfront and throw `IllegalArgumentException` when it is an API misuse |
| Low-level component fails and upper layer needs context | Throw an appropriate exception preserving the original **cause** |
| No way to recover at the current layer | Let the exception propagate or declare an appropriate `throws` |
| Resource must be closed | Use `try-with-resources` if the resource supports it |

Example of what **not to write**:

```java
try {
    doWork();
} catch (Exception ex) {
    // Ignore all errors
}
```

This is just an illustration with an undefined `doWork()` method. Broad, silent catching like this can trick the program into acting as though work succeeded even when data was not saved or resources were not handled properly.

Instead, define clear **postconditions**: if conversion fails, do not return a wrong value as if valid; if writing a file fails, do not report "saved"; if a request fails, respond with the corresponding failure status rather than continuing with missing data.

## 10. Common Mistakes When Using `try-catch`

1. **Wrapping too much code in `try`:** makes it hard to tell which line can fail and risks catching unintended errors. Keep `try` scopes small enough for clear handling.
2. **Catching a superclass before a subclass:** can cause an unreachable catch block and a compile-time error; catch specific types before general ones.
3. **Using multi-catch for types with an inheritance relationship:** `catch (NumberFormatException | IllegalArgumentException ex)` is invalid.
4. **Catching `Exception` and ignoring it:** hides bugs, breaks diagnosability, and can leave the program in an invalid state.
5. **Confusing `throws` with `catch`:** `throws` declares that an exception may propagate; `catch` handles it on the spot.
6. **Assuming `finally` is guaranteed even when the JVM crashes or the process is killed:** no such guarantee exists.
7. **Closing resources manually in an unsafe way:** use try-with-resources whenever possible.
8. **Arbitrarily catching `Error` or `Throwable`:** system-level error conditions usually cannot be recovered from as application code wishes.
9. **Creating a new exception without keeping the cause:** loses the root source of the error; when wrapping, consider `new SomeException(message, cause)`.
10. **Using exceptions instead of ordinary condition checks:** check `args.length`, array bounds, and preconditions first; only use `catch` when an operation can genuinely fail.

**Remember:** `try` identifies operations that may fail; `catch` handles the right **exception type** when an appropriate response exists; `finally` covers steps needed upon leaving the block, and `try-with-resources` closes resources. The goal is to keep program behavior **clear, compliant with requirements, and diagnosable**—not to suppress every error message at any cost.