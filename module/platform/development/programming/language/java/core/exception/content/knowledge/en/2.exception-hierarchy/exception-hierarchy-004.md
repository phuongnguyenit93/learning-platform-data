# Checked Exceptions in Java: The Catch-or-Declare Rule

A checked exception is an exception that the Java compiler requires the source code to **handle with `catch` or declare with `throws`** when a call, expression, or statement may throw it. This rule is commonly known as **catch-or-declare** (or catch-or-specify). It allows a method's contract to inform callers about failure scenarios they need to consider, such as reading a file, accessing data, or waiting on a thread.

After this lesson, you should be able to identify checked exceptions from the inheritance hierarchy, explain the `unreported exception` compilation error, choose appropriately between handling locally and propagating responsibility to the caller, and apply the rule to methods, constructors, overriding, and lambdas.

## 1. Position in the Exception Hierarchy

~~~text
java.lang.Throwable
├── java.lang.Error                         (unchecked)
│   └── ...                                 (unchecked)
└── java.lang.Exception                     (checked)
    ├── java.io.IOException                 (checked)
    │   ├── java.io.FileNotFoundException   (checked)
    │   └── ...
    ├── java.sql.SQLException               (checked)
    ├── java.lang.InterruptedException      (checked)
    └── java.lang.RuntimeException          (unchecked)
        ├── NullPointerException            (unchecked)
        ├── IllegalArgumentException        (unchecked)
        └── ...
~~~

- **Checked:** subclasses of `Throwable` that do **not** belong to the `RuntimeException` or `Error` branches. Therefore, `Exception` itself (excluding the runtime branch), `IOException`, `SQLException`, `ClassNotFoundException`, and `InterruptedException` all have compile-time checking.
- **Unchecked:** `RuntimeException`, `Error`, and their subclasses. They can be caught or declared, but the compiler does not require doing so.
- Both checked and unchecked exceptions only **actually occur at runtime**; the difference is that Java enforces a static `catch`/`throws` requirement for checked exceptions.

API examples: `Files.readString(path)` declares `IOException`; `Thread.sleep(millis)` declares `InterruptedException`; `Integer.parseInt(text)` may throw `NumberFormatException` (unchecked). Do not guess the exception type from the operation name: read the method signature and Javadoc.

## 2. How Does the Catch-or-Declare Rule Work?

Suppose a method can throw `IOException`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Illustrative snippet placed inside a class.
static String read(Path file) throws IOException {
    return Files.readString(file);
}
~~~

Every method calling `read(file)` must choose one of two options:

1. **Catch (`catch`):** place the call inside a `try` block and provide `catch (IOException ex)` or an appropriate supertype. Responsibility for handling is then resolved here, unless you explicitly rethrow it.
2. **Declare (`throws`):** add `throws IOException` (or an appropriate supertype, such as `Exception`) to the calling method's signature. If the exception occurs, it will continue propagating to the caller of that method; the next layer must again catch or declare it.

Both approaches can coexist: a method can catch `FileNotFoundException`, while still declaring `IOException` for the remaining I/O errors. The compiler tracks **the exception types that can be thrown according to the source code**; having `throws` does not mean the method always throws an exception.

### Invalid Example

~~~java
// Illustrates a compilation error; not a standalone Java program.
static String invalidRead(Path file) {
    return Files.readString(file);
}
~~~

Because `Files.readString` declares `IOException` but the method above neither catches nor declares it, `javac` will report an error containing a message similar to `unreported exception java.io.IOException; must be caught or declared to be thrown`. Even if the failing code path is never reached at runtime, it will not pass compile-time checking.

## 3. Complete Example: Propagating to the Caller and Catching at the Application Boundary

Create the file `CatchOrDeclareDemo.java`:

~~~java
import java.io.IOException;

public class CatchOrDeclareDemo {
    static String readConfiguration() throws IOException {
        throw new IOException("thiếu config.properties");
    }

    static String startService() throws IOException {
        return readConfiguration();
    }

    public static void main(String[] args) {
        try {
            System.out.println(startService());
        } catch (IOException ex) {
            System.out.println("Không khởi động: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CatchOrDeclareDemo.java
java CatchOrDeclareDemo
~~~

Exact output:

~~~text
Không khởi động: thiếu config.properties
~~~

Explanation of the execution flow:

1. `readConfiguration()` executes `throw new IOException(...)`. The `throw` keyword **throws an exception object**; `throws IOException` in the signature **declares the possibility of throwing**.
2. `startService()` does not catch it, so it must declare `throws IOException`. The exception travels from `readConfiguration` through `startService` up to `main`.
3. `main()` catches `IOException`, chooses an appropriate message, and continues to the end of the program. The normal print statement inside the `try` block is skipped when the exception occurs.

If you change `main` to `public static void main(String[] args) throws IOException` and call `startService()` directly, the code still **compiles**, but because no Java layer here catches the exception, the application will terminate abnormally and the JVM typically prints a stack trace. Declaring `throws` does not mean the error has been recovered from.

In practice, `readConfiguration()` might use `Files.readString(Path.of("config.properties"))` instead of throwing a fixed exception. When using a real path, success/failure will depend on the filesystem and access permissions.

## 4. Choosing `catch` or `throws`?

| Scenario | Typical Choice | Reason |
| --- | --- | --- |
| User interface layer that can ask to select another file | `catch` | Has a concrete recovery plan. |
| File-reading utility function that does not know how to report errors to the user | `throws IOException` | Preserves failure information for the decision-making layer. |
| Service layer needing to add business context | Catch and throw an appropriate exception, with `cause` | The caller understands which operation failed. |
| Thread interrupted while waiting | Declare `InterruptedException` or catch and restore the interrupt flag | Respects the cancellation/interruption request. |
| Programming bugs such as invalid arguments or `null` access | Fix the root cause; unchecked if needed to represent contract violations | No need to force the catch-or-declare workflow. |

Principle: **catch where you can decide what to do with the error**; if it cannot be handled reasonably yet, usually declare it or wrap it into an exception with context while preserving the original cause. Avoid `catch (Exception ex) { }` because it swallows the error, making subsequent operations assume everything succeeded. Also avoid merely calling `printStackTrace()` and returning dummy data as if the read succeeded.

`throws Exception` and `catch (Exception ex)` are valid in the language, but they obscure the specific error types the API intends to expose and easily catch unexpected programming bugs. Prefer sufficiently specific checked exception types unless the API genuinely has a broad contract.

## 5. Important Rules on Scope and Types

### Supertypes, Subtypes, and Multiple Exceptions

- `catch (IOException ex)` also handles subclasses such as `FileNotFoundException` and `NoSuchFileException` when they occur.
- When there are multiple `catch` blocks, place **specific types first, general types last**. If `catch (IOException)` is placed before `catch (FileNotFoundException)`, the latter branch is unreachable and the compiler reports an error.
- A method can declare `throws IOException, SQLException`. Callers must cover both with appropriate `catch` blocks or declare them further.
- You can use multi-catch `catch (IOException | SQLException ex)` when the types are alternatives with no inheritance relationship between them. Do not write `IOException | FileNotFoundException`: the second type is a subtype of the first.
- `catch` does not automatically catch every `Throwable`: only objects compatible with the declared type match; an uncaught exception propagates outward.

Example of catching specific before general (illustrative snippet placed inside a method with a `Path file` variable):

~~~java
try {
    String content = Files.readString(file);
    System.out.println(content);
} catch (java.nio.file.NoSuchFileException ex) {
    System.out.println("Không tìm thấy tệp được yêu cầu.");
} catch (IOException ex) {
    System.out.println("Không thể đọc tệp: " + ex.getMessage());
}
~~~

If `IOException` cannot be thrown from the `try` block according to the compiler's analysis and you still write `catch (IOException)`, Java may report an error like `exception IOException is never thrown in body of corresponding try statement`. Therefore, do not add `catch` blocks just "to be safe," especially with checked exceptions.

### `throws` and the Method Contract

For checked exceptions, the declaration on a method/constructor is part of the **API contract**: call sites must prepare to handle it. `throws IOException` allows declaring a supertype of `FileNotFoundException` because a caller catching `IOException` also covers the subtype.

A method may declare a checked exception even if its current execution path does not actually throw it. However, do not declare overly broad or unrelated types without a contract-based reason. In API design, specific checked exception types help users determine how to recover.

### Overriding (`override`) and Implementing Interfaces

An overriding method **must not add new or broader checked exceptions** than the overridden method; it may declare none, or declare narrower checked types permitted by the parent contract. The following example is valid:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Repository {
    String load() throws IOException;
}

class TextRepository implements Repository {
    @Override
    public String load() throws FileNotFoundException {
        return "demo";
    }
}
~~~

If `TextRepository.load()` declares `throws Exception` or `throws SQLException`, the code is invalid because the `Repository.load()` contract only permits `IOException` and its subtypes. Unchecked exceptions are not subject to this `throws` restriction. When a class implements multiple interfaces with the same signature, it must satisfy all relevant contracts.

### Constructors, Initializers, and Lambdas

- Constructors follow the same catch-or-declare rules as methods. If calling `new FileInputStream(path)` can throw `FileNotFoundException`, the constructor containing that call must also handle or declare it.
- Object initialization code / initializer blocks have context-specific rules; you cannot arbitrarily throw checked exceptions out of a static initializer by attaching a `throws` clause to the block. For instance initializers, the relevant constructors must be considered.
- Lambdas and method references are also checked by the compiler against the `throws` contract of the abstract method declared by the functional interface. `Runnable.run()` does not declare any checked exceptions, so you cannot directly throw `IOException` from a lambda assigned to `Runnable`. Conversely, `Callable.call()` declares `throws Exception`, so you can write:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

// Illustrative snippet inside a method.
Callable<String> task = () -> Files.readString(Path.of("config.properties"));
~~~

The lambda above only **creates the task**; it does not read the file at declaration time. When the task is invoked, `Callable.call()` may throw a checked exception. Similarly, Stream functions such as `Function.apply` do not declare checked exceptions, so `stream.map(x -> Files.readString(x))` will not compile without appropriate handling.

## 6. Combining try-with-resources with Checked Exceptions

An I/O operation can fail when **opening**, **reading**, or **closing** a resource. `try-with-resources` guarantees that `close()` is called when exiting the `try` block, even when an exception is being handled.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

// Illustrative snippet placed inside a class.
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

`Files.newBufferedReader`, `reader.readLine`, and `reader.close` can all produce `IOException`; `throws IOException` on `firstLine` covers the responsibility for both reading and closing. If the body and the close call both throw errors, the error from closing is typically attached as a **suppressed exception** to the primary error in the try-with-resources mechanism; inspect it with `getSuppressed()` when diagnosing issues. Do not carelessly close resources manually in `finally`, as an error during closing can mask the original error.

`finally` is useful for cleanup logic not based on `AutoCloseable`, but it does not replace the catch-or-declare rule for checked exceptions. Moreover, `return` or `throw` inside `finally` can obscure a previously produced result or exception, so they should be avoided.

## 7. Translating and Preserving the Exception Cause

Sometimes a layer needs to expose errors at a different level of abstraction. You can create a custom checked exception by extending `Exception`, and pass the original exception as `cause`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ConfigurationException extends Exception {
    ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ConfigurationLoader {
    static String load(Path path) throws ConfigurationException {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
            throw new ConfigurationException("Không đọc được cấu hình: " + path, ex);
        }
    }
}
~~~

Here `ConfigurationLoader.load` **does not need to declare `IOException`** because it has caught it; instead, it must declare the newly thrown `ConfigurationException`. Callers of `load` are then responsible for catching or declaring the new checked exception. `getCause()` retains the original `IOException` for diagnostics.

If you must adapt to an API that does not allow declaring checked exceptions (for example, a functional interface), you can convert an `IOException` into an `UncheckedIOException` with the full `cause`, though that is an intentional design choice; callers are no longer forced by the compiler to handle it. Do not silently swallow errors or turn all exceptions into `RuntimeException` just to make the code compile.

## 8. Special Case: InterruptedException

`Thread.sleep`, `Object.wait`, and many other blocking operations can throw `InterruptedException` (checked). The preferred approach in a layer that can propagate it is to declare `throws InterruptedException` so the caller can decide how to cancel the task.

If a method cannot declare it and must catch this exception, it is usually necessary to **restore the interrupt status** so code at higher layers can observe the signal:

~~~java
// Illustrative snippet of a method inside a class.
static void pauseBriefly() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
~~~

`Thread.sleep` clears the interrupted flag when throwing `InterruptedException`; calling `interrupt()` again restores the signal for subsequent checks. In a program with a task loop, after restoring the interrupt flag you should exit or yield control rather than continuing to run indefinitely. Do not mechanically apply this pattern to every `IOException`, as their semantic purposes differ.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling a method that declares a checked exception without `catch`/`throws` | Compilation error `unreported exception` | Catch the appropriate type or declare it on the calling method. |
| Confusing `throw` and `throws` | Assuming a declaration means the error is handled | `throw` performs the throw; `throws` describes the contract. |
| Adding `throws Exception` to every layer | API loses specific information, shifting vague responsibility | Declare specific exceptions or catch where handling is possible. |
| Catching `Exception` with an empty catch block | Loses failure signals, making debugging difficult | Recover properly, propagate, or wrap with the cause. |
| Catching a supertype before a subtype | Subsequent `catch` is unreachable; code fails to compile | Order specific branches before general ones. |
| Adding `throws SQLException` in an override when the interface only allows `IOException` | Violates the method contract | Keep the checked exception set the same or narrower than the parent's. |
| Catching `InterruptedException` without propagating or restoring the interrupt flag | Loses the task cancellation signal | Use `throws InterruptedException` or `Thread.currentThread().interrupt()` and stop appropriately. |
| Throwing a new exception while dropping `cause` | Loses the original error trace | Use a constructor accepting `cause` or `initCause` when appropriate. |

## 10. Self-Check

1. How does `IOException` differ from `NullPointerException` in compile-time requirements? **Answer:** `IOException` is checked, so it must be caught or declared when it can occur; `NullPointerException` is unchecked and has no such requirement.
2. A declares `throws IOException`, and B calls A without catching it. What must B do? **Answer:** B must declare `throws IOException` or an appropriate supertype, continuing to pass responsibility to B's callers.
3. Can `catch (Exception ex)` catch `IOException`? **Yes**, though it is often too broad; consider catching precisely and not swallowing errors.
4. In an override of a parent method with `throws IOException`, can you declare `throws FileNotFoundException`? **Yes**, because `FileNotFoundException` is a subclass of `IOException`.
5. Does using `throws IOException` in `main` guarantee the application will not stop when an I/O error occurs? **No**; it only propagates the exception out of `main` without performing recovery.

## References

- Java Language Specification 17, [§11.1.1 and §11.2 — Exception Types and Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html).
- Oracle Java Tutorials, [The Catch or Specify Requirement](https://docs.oracle.com/javase/tutorial/essential/exceptions/catchOrDeclare.html) (introductory page for JDK 8; the core rules still apply).
- Oracle Java Tutorials, [The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html).

**Key Takeaway:** `throws` is part of the error-propagation contract; `catch` is where you provide the handling logic. Choose the handling point based on actual recovery capability and always preserve essential information about the exception's cause.
