# What Is an Exception and What Problem Does It Solve in Java?

In Java, an **exception** is an object representing an abnormal condition that occurs during program execution, preventing the current operation from continuing along its normal path. Instead of silently returning an incorrect result or forcing every function to check an "error code", Java allows the place where a problem is detected to **throw** an exception object; the runtime system will then look for an appropriate **catch** handler along the call chain to handle it.

For example, a program reads a configuration file to connect to a service, but the configuration file does not exist. It cannot pretend that the data was read. The file-reading code can report an `IOException`; the calling code decides whether to try another path, return an error to the user, cancel the operation, or propagate the error to a higher layer.

This lesson explains **what an exception is, why Java needs an exception mechanism, and how that mechanism works**. The goal is not to turn every undesired situation into an exception, but to keep a clear boundary between **normal control flow** and **failures that must be handled intentionally**.

## 1. The Original Problem: An Operation May Fail to Complete

Consider a function that loads user information. In the happy path, the function takes an ID, looks up the data, and returns the user. But what happens if:

- The database is temporarily unreachable?
- The input data violates an API precondition?
- Code attempts to access a `null` reference?
- Part of the work has completed, while the rest fails?
- Opened resources such as files or connections need to be closed when an error occurs?

If there is only a return type for **success**, it is difficult for the function to express the reason for failure. If every function returns a sentinel value such as `-1`, `null`, or the string `"ERROR"`, the caller must remember to check at every step, and sentinel values can easily be mistaken for valid data.

Example of reporting errors through a sentinel value:

```java
// Illustrates the idea; not a complete API.
int readScore(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException e) {
        return -1; // Does -1 mean "could not parse" or an actual input value?
    }
}
```

Here it is impossible to distinguish "the user entered `-1`" from "could not parse the string as a number". The caller might also forget to check for `-1` and use it in calculations.

Exceptions solve part of this difficulty by creating a **failure-signaling channel separate from the normal return value**. When an exception is thrown, the current computation is interrupted; Java searches for an appropriate handler, and the exception object can carry the error type, message, root cause, and stack trace.

That does not mean every failure should use an exception. An expected outcome such as "out of stock" or "not found in a search query" may fit better with an explicitly typed return value. The **contract of the operation** determines which events belong to the normal branch and which are abnormal.

## 2. The Precise Definition of an Exception

**An exception is an object of class `Throwable`, usually a subclass of `Exception`, thrown by a `throw` statement or raised during JVM execution.** When we say "an exception occurs", we typically mean that an exception object is thrown.

Let us separate three things:

1. **The event/condition causing the problem:** for example, a non-numeric string, a file lacking read permissions, or a `null` reference.
2. **The Java signal:** an object such as `NumberFormatException` or `IOException` representing that problem.
3. **The handling policy:** catching the exception to prompt for re-entry, logging the error, trying an alternative approach, or letting it propagate to a layer that knows how to handle it.

A problem may be detected at a low layer but can only be resolved at a high layer. For example, a file-reading library knows *it could not read the file*, whereas the application knows *whether using a default configuration is allowed or startup must stop*. The exception mechanism allows both layers to keep their proper responsibilities.

**Notable properties** of an exception object:

- **Type:** for example, `IOException` or `IllegalArgumentException`; callers can catch by type.
- **Message:** retrieved via `getMessage()`, describing the context; may be `null`.
- **Cause:** retrieved via `getCause()`, linking a high-level error to the underlying error when translating exceptions.
- **Stack trace:** call frames that help trace the location and execution path; retrieved via `getStackTrace()` or printed via `printStackTrace()`.
- **Suppressed exceptions:** secondary errors attached to the primary one, commonly encountered when closing resources in `try-with-resources`; retrieved via `getSuppressed()`.

The message is not a standardized error code and can change; do not let business logic depend on exact string matching against `getMessage()`.

## 3. How Do Exceptions Change Execution Flow?

Normal statements execute from top to bottom. When an exception is thrown, Java **stops the normal path in the currently executing block**. It searches for a matching `catch` in the nearest `try` construct; if none is found, the exception continues propagating through the chain of calling methods.

Hypothetical example:

```text
main()
  └─ receiveRequest()
       └─ loadConfig()
            └─ readFile()  → throws IOException
```

If `readFile()` does not handle the exception, it does not return with a success value. The exception is passed to `loadConfig()`; if there is no matching `catch`, it continues to `receiveRequest()`, and then to `main()`. That process is commonly called **exception propagation** and **stack unwinding**.

Whenever a method terminates abnormally, the remaining statements on that execution path do not automatically continue. Once a matching `catch` is found, execution resumes **after the handler according to control-flow rules**, rather than jumping back into the statement that caused the exception.

Standalone Java 17+ example, saved as `PropagationDemo.java`:

```java
public class PropagationDemo {
    static void readSettings() {
        throw new IllegalStateException("Thiếu cấu hình");
    }

    static void startService() {
        readSettings();
        System.out.println("Dịch vụ đã khởi động"); // Does not run
    }

    public static void main(String[] args) {
        System.out.println("Bắt đầu");
        try {
            startService();
            System.out.println("Trong try, sau startService"); // Does not run
        } catch (IllegalStateException e) {
            System.out.println("Đã bắt: " + e.getMessage());
        }
        System.out.println("Chương trình tiếp tục");
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 --release 17 PropagationDemo.java
java PropagationDemo
```

**Exact stdout** in a UTF-8 display environment:

```text
Bắt đầu
Đã bắt: Thiếu cấu hình
Chương trình tiếp tục
```

The print statements for “Dịch vụ đã khởi động” and “Trong try, sau startService” do not run. The `catch` in `main` handles the exception thrown deep inside `readSettings`; after `catch`, the program continues along a valid path.

If there is no matching `catch` along the propagation path and the exception escapes `main`, the `main` thread terminates abnormally; the JVM typically prints the exception type, message, and stack trace to **stderr**. In server or multithreaded applications, an uncaught exception usually terminates only the corresponding thread; you should not assume the entire JVM process always stops in every context.

## 4. What Problems Do Exceptions Solve?

### 4.1. Reporting Failure Without Faking a Success Result

A function declared to return `User` should return a user when it succeeds. If an error prevents completion, the function can throw an exception instead of returning an empty object or dummy data. This helps the caller distinguish "valid data present" from "operation failed to complete".

Be sure to distinguish: **no result yet still valid** (for example, looking up an element that does not exist) can use `Optional<User>` or a dedicated result type; exceptions do not replace API design.

### 4.2. Not Forcing Low-Level Layers to Decide How the Application Reacts

File-handling code knows that it failed, but does not know whether to show a dialog box or switch to a fallback configuration. By throwing an exception, that layer passes information to a layer with enough context to decide.

The benefit is separating **error detection** from **error-handling policy**. In return, programmers must read method contracts and establish a clear handling strategy at appropriate boundaries.

### 4.3. Avoiding Manual Error-Code Checks at Every Call Site

When operation A calls B, B calls C, and C calls D, manual error codes force many intermediate layers to pass error values along even though none of them can handle the error. An exception can pass through those layers to an appropriate `catch`.

This is a tool for making code clearer, **not an exemption from designing contracts and testing error paths**. An overlooked exception can still cause a request flow to fail unexpectedly.

### 4.4. Preserving Diagnostic Context

The exception type and stack trace show which calls the code went through; the message explains the condition, and `cause` links a high-level error to the root error. When "unable to generate report" stems from "unable to read configuration file", the cause chain helps diagnose the exact source.

### 4.5. Supporting Cleanup When the Normal Path Is Interrupted

While using a file, socket, or other resource, an exception can occur before the close statement. `finally` and `try-with-resources` allow developers to place cleanup in a location that executes when leaving scope, even along exception paths. However, no cleanup mechanism guarantees execution in all cases, such as when the JVM is forcibly terminated.

## 5. Basic Hierarchy: `Throwable`, `Exception`, and `Error`

Simplified diagram:

```text
java.lang.Object
  └─ java.lang.Throwable
       ├─ java.lang.Error
       │    ├─ OutOfMemoryError
       │    └─ StackOverflowError
       └─ java.lang.Exception
            ├─ IOException
            ├─ ReflectiveOperationException
            └─ RuntimeException
                 ├─ IllegalArgumentException
                 │    └─ NumberFormatException
                 ├─ IllegalStateException
                 ├─ NullPointerException
                 └─ IndexOutOfBoundsException
```

The classes above are only **part** of the Java hierarchy.

- `Throwable` is the root type for objects that can be `throw`n and `catch`ed.
- `Exception` typically represents conditions an application may handle or propagate to callers.
- `RuntimeException` is a subclass of `Exception`, used for **unchecked** exceptions such as `IllegalArgumentException` and `NullPointerException`.
- `Error` indicates serious JVM/environment or class-linkage problems; ordinary business code **should not** broadly catch this group and pretend to continue safely.

**Checked exceptions** are subclasses of `Throwable` that are not `RuntimeException` or `Error`, commonly seen in subclasses of `Exception` such as `IOException`. The compiler requires calling code to catch or declare checked exceptions that may be thrown. **Unchecked exceptions** include `RuntimeException` and its subclasses as well as `Error` and its subclasses; the compiler does not require callers to declare or catch them.

Do not interpret "checked" as guaranteed recoverable, or "unchecked" as guaranteed to be a bug. An `IOException` may be unrecoverable on the spot; an `IllegalArgumentException` may stem from user input that needs to be reported back to the user. The actual situation and API contract determine the action.

## 6. Java Constructs Directly Related to Exceptions

| Construct | Role |
| --- | --- |
| `throw exceptionObject;` | Throws **an object** of type `Throwable`, interrupting normal flow |
| `throws SomeException` | Declares in a method signature that it may propagate the corresponding exception outward; **does not throw by itself** |
| `try { ... }` | Wraps a block of code to be placed under catching/cleanup mechanisms |
| `catch (Type e) { ... }` | Executes when an exception matching the type is propagating from the corresponding `try` |
| `finally { ... }` | Intended for cleanup/end-of-operation tasks, normally runs when leaving `try/catch` |
| `try (resource) { ... }` | Automatically closes `AutoCloseable` resources in reverse order when leaving `try` |

### `throw` and `throws` Are Two Different Things

```java
import java.io.IOException;

class ConfigurationService {
    static String load(boolean reachable) throws IOException {
        if (!reachable) {
            throw new IOException("Không thể truy cập cấu hình");
        }
        return "ready";
    }
}
```

This is an **illustrative class declaration snippet**, without a `main` method to run standalone. `throw new IOException(...)` actually creates and throws the object; `throws IOException` informs callers of this possibility. If a caller writes `ConfigurationService.load(false)`, it must catch or declare `IOException` for the code to compile, because it is a checked exception.

`throws` does not make the file or service work again, nor does it replace `catch`. If callers try to ignore the issue by writing `throws IOException` all the way up the call chain, the top-most layer still needs to decide what happens if the exception escapes.

### `catch` Matches by Type Relationship

`catch` captures exceptions whose type is compatible with the declared parameter type, including subclasses. `catch` branches must be ordered from **most specific to most general**. For example, `NumberFormatException` is a subclass of `IllegalArgumentException`; catching `IllegalArgumentException` first makes a subsequent `NumberFormatException` branch unreachable code, so Java reports a compile-time error.

```java
try {
    int value = Integer.parseInt(text);
    System.out.println(value);
} catch (NumberFormatException e) {
    System.out.println("Dữ liệu không phải số nguyên");
} catch (IllegalArgumentException e) {
    System.out.println("Đối số không hợp lệ");
}
```

This is a **snippet inside a method**, assuming the variable `text` has already been declared. The second branch would catch other `IllegalArgumentException`s raised inside `try`; specifically for `Integer.parseInt` and an input string, the `NumberFormatException` branch is the relevant conversion-error branch.

### `finally` and `try-with-resources`

`finally` normally runs when exiting `try`, whether on success, with a caught exception, with an uncaught exception, or with a `return`; however, it cannot be guaranteed if the process is forcibly killed, the JVM crashes, or special situations occur. Avoid `return` or throwing a new exception inside `finally` because it can **mask an existing exception or return value**.

For resources implementing `AutoCloseable` (such as `BufferedReader`), prefer `try-with-resources`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileReaderExample {
    static String readFirstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

This snippet is an **illustrative class without `main`**; behavior depends on the actual file path and contents. Whether `readLine` succeeds, returns `null` at end-of-file, or throws an exception, Java attempts to close `reader` when leaving the `try` block. If both the body and `close()` throw exceptions, the exception from closing is typically stored in the **suppressed** list of the primary exception, preserving the original error trace. If the body has no error but closing fails, the exception from `close()` can propagate outward.

`try-with-resources` does not automatically roll back transactions, undo all side effects, or guarantee that remote resources close successfully; it manages calling `close()` on the declared resources.

## 7. Complete Example: Receiving Input, Reporting Errors, Handling, and Continuing

Save the following program as `ExceptionBasicsDemo.java` and run it with **Java 17+**:

```java
public class ExceptionBasicsDemo {
    static int readPositiveInteger(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("Giá trị phải lớn hơn 0");
        }
        return value;
    }

    static int calculatePrice(String quantityText) {
        int quantity = readPositiveInteger(quantityText);
        return quantity * 100;
    }

    public static void main(String[] args) {
        String[] inputs = {"3", "0", "abc"};

        for (String text : inputs) {
            try {
                int price = calculatePrice(text);
                System.out.println(text + " -> " + price);
            } catch (NumberFormatException e) {
                System.out.println(text + " -> không phải số nguyên");
            } catch (IllegalArgumentException e) {
                System.out.println(text + " -> số lượng không hợp lệ: "
                        + e.getMessage());
            }
        }

        System.out.println("Đã xử lý tất cả đầu vào");
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 --release 17 ExceptionBasicsDemo.java
java ExceptionBasicsDemo
```

**Exact stdout** in a UTF-8 display environment:

```text
3 -> 300
0 -> số lượng không hợp lệ: Giá trị phải lớn hơn 0
abc -> không phải số nguyên
Đã xử lý tất cả đầu vào
```

Branch-by-branch breakdown:

1. `"3"` parses to `int 3`, which is valid; `calculatePrice` returns `300` as a normal value.
2. `"0"` parses to a number but does not satisfy the precondition of `readPositiveInteger`; `throw new IllegalArgumentException(...)` terminates the normal branch and throws the exception to the matching `catch` inside the loop in `main`.
3. `"abc"` causes `Integer.parseInt` to throw `NumberFormatException` before reaching the positive-number check. Because `catch (NumberFormatException e)` appears before `IllegalArgumentException`, it is selected.
4. After each exception is handled, the loop moves to the next iteration; no statements in the failed invocation continue running from the interrupted point.

The example uses a unit price of `100` to keep the output easy to follow; real applications need range validation, overflow protection, and appropriate input-handling choices. `NumberFormatException` is an exception, but invalid input can be translated into an **expected validation result** at the interface; that choice depends on the interface layer's contract.

## 8. When an Exception Is Not Caught: What Actually Happens?

If there is no compatible `catch`, the exception continues propagating up to callers. In a console application, an exception escaping `main` typically prints a stack trace and terminates the main thread with an error status. The stack trace displays the call frame locations for diagnosis—for example, from `readPositiveInteger` through `calculatePrice` to `main`—along with the exception type name.

In a multithreaded program, if one thread has an uncaught exception, that thread may terminate while other threads may continue running. In server frameworks, the framework layer usually sets an exception-handling boundary per request, so one request can fail while the entire JVM stays alive. Therefore, the claim "throwing an exception crashes the program" is an inaccurate generalization.

Distinguish **being thrown** from **being handled effectively**: a `catch` can capture an exception yet return incorrect data, ignore the cause, or log it and continue in a corrupted state. That is not safe handling.

## 9. Choosing Where to Catch and How to Handle Exceptions

Catch an exception only when the current layer **knows something meaningful to do**: try a fallback, request new input, restore a valid state, add context to the error, or translate it into a response at an API boundary.

Typical options:

- **Recover:** the primary file path fails and the application has an allowed fallback configuration. Catch `IOException`, try the fallback path, and report clearly if it still cannot be loaded.
- **Translate into an explicit result:** the interface layer catches user input conversion errors and returns a structured validation error.
- **Add context and rethrow:** the service layer knows which operation failed; wrap `IOException` in an exception appropriate to the API, preserving `cause`.
- **Allow propagation:** the current layer has no safe strategy; keep the `throws` contract for checked exceptions or let unchecked exceptions travel up to a responsible layer.

Example of translating an error while preserving the root cause:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class AppSettings {
    static String load(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException cause) {
            throw new IllegalStateException(
                    "Không nạp được cấu hình từ " + path, cause);
        }
    }
}
```

This is an **illustrative class without `main`**. If reading fails, the caller sees `IllegalStateException` with a contextual message; `getCause()` returns the original `IOException`. Do not overuse converting checked exceptions to unchecked ones just to avoid handling them; only change the type when it fits the current layer's API contract.

Place handling at **boundaries capable of making decisions**: for instance, a console UI chooses the message and prompts again, an HTTP adapter translates errors into the proper HTTP status code per contract, and a scheduler records a failed job and applies a valid retry policy. Do not catch a database error and return "user not found" when the two situations have different meanings.

## 10. Exceptions Are Not Meant to Replace Every Business Branch

Ask: is a condition **frequent and valid** for the business domain? If "out of stock" is a branch that must be displayed normally, a result type containing an `OUT_OF_STOCK` status is often clearer than throwing an exception across multiple layers. If "inventory is never negative" is an internal invariant and inventory suddenly becomes negative, an exception can represent the contract violation.

Common ways to report outcomes:

| Case | A Potentially Suitable Design |
| --- | --- |
| Looking up an ID that may normally not exist | `Optional<User>` or a result with a `NOT_FOUND` status |
| Order rejected due to out-of-stock | An `OrderResult` type containing a rejection code |
| User input fails validation rules | A list of validation errors; or conversion errors handled at the boundary |
| Calling an API with arguments violating the programmer contract | `IllegalArgumentException` |
| Required file access failure | `IOException`, handled or propagated with context |
| System violates an internal invariant | Exception describing an invalid state, propagating to a responsible layer |

The options above are not rigid rules. Some APIs intentionally design **domain exceptions** to represent business rejections. Even then, the exception is still Java's signaling mechanism; what it means is determined by the contract. What matters most is that callers know how to handle it and do not treat an expected rejection as an infrastructure failure.

## 11. How Do Exceptions Differ from Compile Errors and Logic Errors?

Exceptions are a **runtime** mechanism. They do not replace `javac`'s syntax and type checks:

- `int n = "5";` is a type error at **compile time**; you cannot use `try/catch` to "catch" that error in a running program.
- `Integer.parseInt("x")` **compiles**, but at runtime throws `NumberFormatException`.
- `int sum = Integer.MAX_VALUE + 1;` compiles and executes `int` addition with overflow according to Java integer rules; by default it **does not throw an exception**. This can be a logic error if the business logic requires an exact mathematical result.
- A login request with an incorrect password can return "rejected" completely normally; an exception is not necessarily involved.

Do not misdiagnose using rules like "no exception means the program is correct" or "an exception means it is definitely a programming bug". Testing correctness, data consistency, and business branches is still necessary.

## 12. Common Mistakes When Catching Exceptions

### Catching and Ignoring

```java
try {
    performOperation();
} catch (Exception ignored) {
    // No logging and no recovery strategy.
}
```

This is an **illustrative snippet**, assuming `performOperation()` is already defined. This approach loses the failure signal. Only ignore a specific exception type when the contract allows it and there is a clear reason.

### Catching Too Broadly or Catching `Throwable`

`catch (Exception e)` can lump together many error types that need different handling, hiding bugs and losing the appropriate action for each type. `catch (Throwable t)` can even catch `Error`, which business layers should not try to handle like ordinary errors. There are special framework boundaries that need broad catches to log a final failure, but that is an intentional architectural decision.

### Translating to a New Error While Losing `cause`

```java
// Poor: does not preserve the original cause.
catch (IOException e) {
    throw new IllegalStateException("Không đọc được dữ liệu");
}
```

You should preserve the cause when changing types:

```java
catch (IOException e) {
    throw new IllegalStateException("Không đọc được dữ liệu", e);
}
```

Both snippets are **parts of a try/catch block**, not standalone programs. Preserving `cause` allows the stack trace to reflect the underlying failure as well.

### Using Exceptions Instead of Normal Control Flow

Throwing an exception for every loop step or every normal check makes code hard to read, forces readers to trace non-linear branches, and can incur unnecessary overhead when thrown very frequently. Use conditions, states, or explicit result types for expected branches.

### Showing Stack Traces to End Users

Stack traces are for developers and operators; they can contain internal paths, class names, sensitive information, and system structure. Applications should provide user-appropriate messages while logging necessary diagnostics in a protected location. Do not put secrets into exception messages.

### Retrying Every Exception

Not every error is transient, and not every operation is safe to repeat. Retrying an order-creation request can create duplicate orders if the first attempt succeeded in writing before the response was lost. Only retry when the cause, backoff policy, timeout, idempotency, and side effects have been reviewed.

### Forgetting Cleanup or Using `finally` Unsafely

An exception can skip a `close()` call at the end of `try`. Prefer `try-with-resources` for `AutoCloseable`. Do not `return` inside `finally` and accidentally overwrite a result or mask a propagating exception.

## 13. How to Read an Exception When Troubleshooting Real Errors

When a runtime error occurs, check in order:

1. **Type name:** `NumberFormatException` points to number conversion, `IOException` relates to I/O operations; the type name is only a hint, not enough to conclude the root cause.
2. **Message:** states relevant values/states if safe, but do not rely on message text as conditional logic.
3. **Stack trace:** find the call frame belonging to application code where the operation failed, then trace callers to see what conditions led there. The throwing line inside a library is not necessarily where the application bug is.
4. **Cause:** follow the `getCause()` chain down to identify the deeper underlying error when exceptions are wrapped.
5. **Suppressed:** check when multiple errors occur, especially during resource closing.
6. **Context:** input data, JDK version, configuration, resources, timing, and preceding operations; avoid logging secret data.
7. **Contract:** determine whether to recover, return a business result, or report a technical error to a higher layer.

An exception being **caught** does not necessarily mean it has been **resolved**. Proper handling means keeping the system in a valid state, giving an appropriate signal to the caller, and not losing information needed for investigation.

## 14. Self-Check Questions

**Scenario 1.** A file-reading function throws `IOException`. The calling method can only display a message and ask the user to choose another file. What should be done?  
You can `catch` at the UI layer to report the error and let the user choose again, because this layer has a valid recovery strategy.

**Scenario 2.** `methodA()` calls `methodB()`; `methodB()` throws an uncaught `IllegalStateException`. Does the statement immediately after the `methodB()` call in `methodA()` continue?  
No, the call terminates abnormally and the exception continues propagating. Code can resume at a matching `catch` further up the call stack.

**Scenario 3.** Does adding `throws IOException` to a method make file-reading errors disappear?  
No. It only changes the declared contract and allows the exception to propagate; a handling policy still must be decided.

**Scenario 4.** A user searches for a record that does not exist. Is throwing an exception mandatory?  
No. If "not found" is an expected outcome, you can use `Optional` or an explicit business status.

**Scenario 5.** Why should you use `try-with-resources` when reading a file?  
Because the resource is closed upon leaving the block through a structured mechanism, even when an exception occurs, and Java preserves suppressed exceptions in the appropriate situations.

**Scenario 6.** Why must `catch (NumberFormatException e)` come before `catch (IllegalArgumentException e)`?  
Because `NumberFormatException` is a subclass of `IllegalArgumentException`. If the superclass is caught first, the subclass branch afterward is unreachable and the compiler rejects it.

## 15. Key Takeaways for Using Exceptions Properly

- **An exception is a typed signal**, thrown at runtime to represent a problem that prevents the normal path from continuing.
- When an exception occurs, Java **propagates it through the call stack** to a compatible `catch`; statements after the throw point on the interrupted branch do not automatically continue.
- Exceptions help **separate problem detection from handling decisions**, preserve diagnostic information, and support resource cleanup when exiting along an abnormal path.
- `throw` is used to throw; `throws` declares the possibility of throwing; `catch` is only useful when that layer truly knows how to handle it; `try-with-resources` manages `AutoCloseable` resources.
- **Not every undesired outcome needs an exception.** Choose between a normal return value and an exception based on the contract, the nature of the event, and the caller's responsibility.
