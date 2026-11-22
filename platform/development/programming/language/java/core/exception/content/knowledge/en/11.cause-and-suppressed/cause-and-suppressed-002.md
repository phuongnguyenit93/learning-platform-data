# Preserving the Cause When Wrapping Exceptions in Java

## 1. Learning Objectives

When a method catches a low-level exception and needs to report the failure using an exception type more appropriate for the upper layer, it can perform **exception wrapping**. Proper wrapping must preserve the **root cause** so developers do not lose critical information about where and why the failure occurred.

For example: a file-reading library throws `IOException`, and the data-import class wants to report `ImportException`. If it only creates `new ImportException("Import failed")`, the stack trace of the read error can be lost from the exception propagated upward. If it creates `new ImportException("Import failed", original)`, the new exception adds business context while still tracing back to the original `IOException` via `getCause()`.

This lesson helps you:

- Distinguish the **outer exception** (*wrapper*) from the **cause** and **suppressed exceptions**.
- Use the `Throwable(String, Throwable)` constructor or the corresponding constructor of `Exception`/`RuntimeException` and their subclasses.
- Design custom exceptions that support a cause, preserving the original `Throwable` object in the error chain.
- Use `initCause(Throwable)` when compatibility with legacy APIs is needed, while understanding its limitations.
- Find the root cause across multiple layers without losing intermediate layer information.
- Decide when to **rethrow the original exception**, when to **wrap**, and when to **handle locally**.
- Avoid anti-patterns such as only copying `getMessage()`, duplicate logging, masking the cause, or converting between checked/unchecked incorrectly.
- Read `printStackTrace()` output and distinguish `Caused by:` from `Suppressed:` during diagnosis.

Standalone programs use Java 17 or later, with `javac`/`java` commands and expected `stdout`.

## 2. Why Losing the `cause` Is a Design Flaw

Suppose a lower layer has the method:

```java
static int parse(String text) {
    return Integer.parseInt(text);
}
```

If `text` does not contain a valid integer, `Integer.parseInt` throws `NumberFormatException`. An application layer might catch the error and translate it into an exception with business meaning:

```java
try {
    return parse(text);
} catch (NumberFormatException original) {
    throw new IllegalStateException("Invalid configuration");
}
```

The two snippets above are **illustrative fragments** inside a class/method with an appropriate `text` variable. The last approach has a problem: the outer exception still has the stack trace of where it was **wrapped**, but the formal link to the original `NumberFormatException` object is not stored. The reader only sees “Invalid configuration” and can no longer directly inspect the parse error, the call that caused it, or the information attached to the old object via the `cause` chain.

The right approach:

```java
try {
    return parse(text);
} catch (NumberFormatException original) {
    throw new IllegalStateException(
            "Invalid configuration: expected an integer", original);
}
```

Here:

- `original` is the exact `NumberFormatException` object that was caught.
- The new `IllegalStateException` represents a failure at the configuration layer.
- The two-argument constructor stores `original` as the **cause**.
- `getCause()` on the wrapper returns a reference to `original`, not a new exception reconstructed from a message.
- When viewing the full stack trace, Java can display both layers and where the original error occurred.

**Principle:** wrapping an exception must add useful information **while preserving the original error**, rather than merely renaming the error and losing the trace path.

## 3. The `Throwable` Model: message, cause, stack trace, and suppressed

A `Throwable` object carries several distinct pieces of information:

| Component | Main API | Meaning |
| --- | --- | --- |
| Exception type | `getClass()` | The layer/failure reason represented by a Java type |
| Message | `getMessage()` | Short description, may be `null` |
| Cause chain | `getCause()` | The exception that caused the current error or was wrapped by it |
| Execution location | `getStackTrace()`, `printStackTrace()` | Relevant frames when the stack trace was recorded |
| Secondary errors | `getSuppressed()` | Additional errors attached to the same Throwable, typically during cleanup |

Relationship diagram:

```text
ImportException: "Cannot import orders"       <-- wrapper
    |
    +-- getCause()
            |
            v
      IOException: "Cannot read orders.csv"    <-- cause
            |
            +-- getCause() == null

Each Throwable in the diagram can have its own stack trace
and getSuppressed() list.
```

Do not treat `getCause()` and `getSuppressed()` as two names for the same mechanism. `cause` explains the **caused-by / wrapped-by** relationship; suppressed holds **additional** errors (for example, closing a resource failed after reading a file failed).

A wrapper typically has a stack trace captured at the **wrapping site**; the cause keeps the stack trace at the **originating site**. Keeping both tells you not only *which error occurred* but also *which layer translated the error*.

## 4. Constructor Accepting a Cause: The Most Common Approach

Many Java exception classes provide constructors such as:

```java
new RuntimeException("context", cause);
new IllegalStateException("context", cause);
new java.io.IOException("context", cause);
```

These are illustrative expressions requiring a declared `cause` variable of type `Throwable`. Custom classes should provide a similar constructor when wrapping is needed.

Example definition:

```java
class ImportException extends Exception {
    ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a valid Java class. Calling `super(message, cause)` lets the `Exception` superclass store the cause using `Throwable`'s built-in mechanism. There is no need to declare a custom `Throwable rootCause` field if you only want standard behavior.

### Why does the cause parameter have type `Throwable`?

`Throwable` is the superclass of both `Exception` and `Error`. A constructor accepting `Throwable` preserves the exact source error object without forcing it to share the same hierarchy as the wrapper.

However, the ability to **pass an `Error`** does not mean an application should catch every `Error` and convert it into a recoverable exception. Many `Error` types indicate serious JVM or runtime environment failures; keep your catch and wrap scope aligned with your contract.

### Use the cause-accepting constructor, not message reconstruction

If you already have `IOException original`, avoid:

```java
throw new IOException(original.getMessage());
```

This snippet creates a new `IOException`, but does not store `original` as its cause. The message may look similar, yet the causal link is lost.

Write instead:

```java
throw new IOException("Unable to read configuration", original);
```

In both illustrative snippets, `original` is assumed to be caught or declared. The second form preserves the original error object. Adding context should still remain concise and describe **which operation failed**.

## 5. Complete Example: Wrapping `NumberFormatException` as a Configuration Error

Create **`PreservedCauseDemo.java`**:

```java
public class PreservedCauseDemo {
    static class ConfigurationException extends Exception {
        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static int readPort(String text) throws ConfigurationException {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException original) {
            throw new ConfigurationException(
                    "Port must be an integer", original);
        }
    }

    public static void main(String[] args) {
        try {
            readPort("abc");
        } catch (ConfigurationException failure) {
            System.out.println("outer="
                    + failure.getClass().getSimpleName());
            System.out.println("message=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run on Java 17+:

```bash
javac PreservedCauseDemo.java
java PreservedCauseDemo
```

Exact `stdout`:

```text
outer=ConfigurationException
message=Port must be an integer
cause=NumberFormatException
```

Explanation:

1. `Integer.parseInt("abc")` throws `NumberFormatException`.
2. `readPort` catches the exception thrown in its body.
3. `new ConfigurationException(..., original)` creates a new error object with the context “Port must be an integer”.
4. `main` receives `ConfigurationException` and can handle the configuration failure according to the application contract.
5. `failure.getCause()` is still the original `NumberFormatException`; the parse error's message and stack trace remain intact in the cause chain.

You do not need to call `fillInStackTrace()` manually or construct a new `NumberFormatException` to “reconstruct” the cause. Keeping **a reference to the original error** is what preserves everything that object recorded.

## 6. Multi-Layer Cause Chains

In a layered system, an error can be wrapped multiple times:

```text
IOException                 error in data-reading API
     |
     | wrapped into
     v
StorageException             storage-layer error
     |
     | wrapped into
     v
ImportException              business-layer error
```

When traversing `getCause()` from the outermost exception:

```text
ImportException
  -> StorageException
      -> IOException
          -> null
```

This is a **cause** chain, not a suppressed list. Each layer should provide useful context rather than meaninglessly repeating “failed”.

### Runnable Example: Cause Across Three Layers

Create **`CauseChainDemo.java`**:

```java
import java.io.IOException;

public class CauseChainDemo {
    static class StorageException extends Exception {
        StorageException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class ImportException extends Exception {
        ImportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readSource() throws IOException {
        throw new IOException("source unavailable");
    }

    static String load() throws StorageException {
        try {
            return readSource();
        } catch (IOException original) {
            throw new StorageException("cannot load source", original);
        }
    }

    static void importData() throws ImportException {
        try {
            load();
        } catch (StorageException original) {
            throw new ImportException("cannot import records", original);
        }
    }

    public static void main(String[] args) {
        try {
            importData();
        } catch (ImportException failure) {
            Throwable current = failure;
            while (current != null) {
                System.out.println(
                        current.getClass().getSimpleName()
                        + ": " + current.getMessage());
                current = current.getCause();
            }
        }
    }
}
```

```bash
javac CauseChainDemo.java
java CauseChainDemo
```

`stdout`:

```text
ImportException: cannot import records
StorageException: cannot load source
IOException: source unavailable
```

The chain is built as follows:

- `readSource()` creates the root `IOException`.
- `load()` catches that error and wraps it in `StorageException`.
- `importData()` wraps `StorageException` in `ImportException`.
- `main` follows each cause link without needing to know I/O error details when writing business logic.

For a throwable coming from an **arbitrary source** or custom library, cause-traversal code should ideally detect reference cycles to avoid infinite loops if an error chain is constructed abnormally. For the linear chain produced by the three methods in this example, the `while` loop terminates when `getCause() == null`.

### Do not wrap at every layer if no information is added

If `load()` and `importData()` simply pass along the I/O error without adding any meaning, wrapping at both layers can clutter logs, lengthen stack traces, and obscure the API contract. Wrap when crossing an **abstraction boundary** or when adding valuable context.

## 7. `initCause(Throwable)`: When No Suitable Constructor Exists

Some legacy exception classes do not have a constructor that accepts a cause. In that case, `Throwable.initCause(cause)` can be used to link the cause **after creating the object**, provided the cause has not yet been initialized.

Example:

```java
LegacyException wrapper = new LegacyException("cannot process");
wrapper.initCause(original);
throw wrapper;
```

This is an illustrative snippet assuming `LegacyException` already exists and `original` is a `Throwable`. It is still best to use a cause-accepting constructor if the API provides one.

### Limitations of `initCause`

- Can only be called **once** while the cause state is still uninitialized.
- If the cause has already been initialized (even if recorded as `null` by a constructor), calling `initCause` again throws `IllegalStateException`.
- Cannot pass **the target throwable itself** as its own cause; self-causation throws `IllegalArgumentException`.
- Passing `null` can set the cause when uninitialized; do not treat it as a way to “reset” the cause relationship.
- `initCause` returns the `Throwable` receiving the call, which is convenient for certain styles of writing, though chaining is not required.
- In new code that you control, a `(String, Throwable)` constructor is usually clearer and safer than constructing the object and remembering to link the cause later.

### Runnable Example: Setting the Cause Once

Create **`InitCauseDemo.java`**:

```java
import java.io.IOException;

public class InitCauseDemo {
    static class LegacyException extends Exception {
        LegacyException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("disk failed");
        LegacyException wrapper =
                new LegacyException("load operation failed");

        wrapper.initCause(root);
        System.out.println("cause=" + wrapper.getCause().getMessage());

        try {
            wrapper.initCause(new IOException("second cause"));
        } catch (IllegalStateException failure) {
            System.out.println("second init rejected");
        }

        try {
            LegacyException self = new LegacyException("self");
            self.initCause(self);
        } catch (IllegalArgumentException failure) {
            System.out.println("self cause rejected");
        }
    }
}
```

```bash
javac InitCauseDemo.java
java InitCauseDemo
```

`stdout`:

```text
cause=disk failed
second init rejected
self cause rejected
```

`super(message)` in the custom exception leaves the cause uninitialized per `Throwable(String)`, so the first `initCause(root)` succeeds. The subsequent call is rejected. For self-causation, Java also refuses to set a cause pointing directly to the same object.

### Do not call `initCause` after a cause-accepting constructor

Illustrative code:

```java
IOException wrapped = new IOException("cannot read", original);
wrapped.initCause(anotherFailure); // Wrong: cause has already been initialized.
```

This snippet throws `IllegalStateException` at runtime (assuming `original` and `anotherFailure` are valid `Throwable` objects), because the constructor already set the cause. Do not use `initCause` as a mechanism to “change the cause” later.

## 8. `cause` Is Not a `suppressed exception`

Both kinds of links can coexist:

```text
ImportException: cannot import
    |
    +-- cause: IOException("read failed")
    |
    +-- suppressed: IOException("close failed")
```

Typical scenarios:

- **Wrapping a lower-layer error:** `new ImportException("...", original)` → uses `cause`.
- **File read fails, and closing the file also fails in TWR:** the read error is primary; the close error is typically `suppressed`.
- **File close fails when the body succeeds:** the close error can be primary, not necessarily suppressed.
- **A business error is both wrapped and has a cleanup failure:** the wrapper has a cause; suppressed errors may sit on the cause itself or on the wrapper depending on the actual layer and resource-management mechanism. Do not assume suppressed exceptions always reside at the outermost layer.

### Runnable Example: Having Both a Cause and a Suppressed Error

Create **`CauseAndSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseAndSuppressedDemo {
    public static void main(String[] args) {
        IOException readFailure =
                new IOException("read failed");
        readFailure.addSuppressed(
                new IOException("reader close failed"));

        IllegalStateException wrapper =
                new IllegalStateException("cannot load report", readFailure);

        System.out.println("outer=" + wrapper.getMessage());
        System.out.println("cause=" + wrapper.getCause().getMessage());
        System.out.println("outer suppressed="
                + wrapper.getSuppressed().length);
        System.out.println("cause suppressed="
                + wrapper.getCause().getSuppressed().length);
        System.out.println("cleanup="
                + wrapper.getCause().getSuppressed()[0].getMessage());
    }
}
```

```bash
javac CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
```

`stdout`:

```text
outer=cannot load report
cause=read failed
outer suppressed=0
cause suppressed=1
cleanup=reader close failed
```

Explanation: `readFailure` has one suppressed exception; it is carried intact inside the wrapper's cause. A cause-accepting constructor **does not move** the suppressed list from the cause to the wrapper. Therefore `wrapper.getSuppressed().length == 0`, while the suppressed exception remains on `wrapper.getCause()`.

In logs, `printStackTrace()` on the wrapper typically formats the cause chain and each throwable's suppressed exceptions in structure; you should not check only `wrapper.getSuppressed()` and conclude there were no cleanup errors on deeper causes.

## 9. Combining `try-with-resources` with Exception Wrapping

`try-with-resources` automatically closes `AutoCloseable` resources in reverse order. When the body fails and `close()` also fails, Java keeps the body error as primary and attaches the close error as suppressed. If an outer layer wraps the primary error, **it should preserve the exact primary object along with its suppressed exceptions**.

### Runnable Example: Preserving Both Cause and Suppressed Through a Wrapper

Create **`WrappedResourceFailureDemo.java`**:

```java
import java.io.IOException;

public class WrappedResourceFailureDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class OperationException extends Exception {
        OperationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void execute() throws OperationException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        } catch (IOException original) {
            throw new OperationException("report generation failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            execute();
        } catch (OperationException failure) {
            Throwable cause = failure.getCause();
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause=" + cause.getMessage());
            System.out.println("suppressed="
                    + cause.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac WrappedResourceFailureDemo.java
java WrappedResourceFailureDemo
```

`stdout`:

```text
outer=report generation failed
cause=read failed
suppressed=close failed
```

Step by step:

1. `execute()` enters the TWR block with `BrokenResource`.
2. The body throws `IOException("read failed")`.
3. `close()` throws `IOException("close failed")`; the JVM/TWR attaches this error to `getSuppressed()` of the read error.
4. The `catch (IOException original)` handler receives the primary object that already holds the suppressed exception.
5. `new OperationException(..., original)` wraps **that exact object** and preserves the cause link.
6. The caller can inspect the cause, and then access the suppressed exception attached to that cause.

If you wrote `new OperationException(original.getMessage(), null)` or only copied the message, both the cause relationship and the close error would be lost from the propagated exception. This is a practical example of why preserving the error object matters more than preserving a text string.

## 10. When Should You `throw original;` Instead of Wrapping?

**Not every exception needs a wrapper.** If the current call layer does not change the meaning or need to translate the contract, rethrowing the original exception is often simpler and more faithful.

Example:

```java
static String readLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    try {
        return reader.readLine();
    } catch (java.io.IOException original) {
        // Can record genuinely useful context here.
        throw original;
    }
}
```

This is a **method fragment**. `throw original;` propagates **the exact same IOException object**, preserving its message, cause, suppressed exceptions, and stack trace. However, a `catch` block that only rethrows without adding value is usually redundant; you can simply let the exception propagate.

Use a wrapper when:

- Crossing an abstraction boundary: I/O → storage → business logic.
- Upper layers should not depend on a detailed technical error type, yet still need traceability.
- The API needs to add contextual details such as operation name, data source, or transaction ID (without exposing secrets).
- The upper layer's error-handling policy has a different contract for a clear reason.

Keep the original error or handle it directly when:

- The method's API already declares the appropriate checked exception type.
- There is no useful new semantics to add in a wrapper.
- The caller needs to handle the exact original type.
- Catching only to log and rethrow without adding anything: logging should happen at an appropriate boundary to avoid duplicate logs.

### Do not wrap and swallow the exception

Anti-pattern:

```java
try {
    save();
} catch (Exception original) {
    new IllegalStateException("Save failed", original);
    // Not thrown: the new exception is discarded.
}
```

This is an **intentionally flawed code snippet** requiring a definition of `save()`. Merely instantiating a wrapper without `throw` or passing it to an error-reporting mechanism does not inform the caller that the operation failed. Be sure to write:

```java
throw new IllegalStateException("Save failed", original);
```

if the policy is indeed to propagate the failure as an unchecked exception.

## 11. Checked and Unchecked Exceptions When Wrapping

Wrapping can change **the exception type the caller must handle**; that is an API design decision, not merely a logging decision.

Example of a method calling a checked API:

```java
static void load() throws java.io.IOException {
    throw new java.io.IOException("missing file");
}
```

If the calling method wraps it as `IllegalStateException`:

```java
static void initialize() {
    try {
        load();
    } catch (java.io.IOException original) {
        throw new IllegalStateException(
                "Startup configuration could not be loaded", original);
    }
}
```

These are **illustrative method fragments** in the same class; `initialize()` does not need to declare `throws IOException`, because it handles the `IOException` by throwing an unchecked wrapper. However, this **does not mean the error has been recovered from**. The caller can still fail at runtime if no appropriate handler is present.

If using a checked wrapper:

```java
class StartupException extends Exception {
    StartupException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

then a method throwing `StartupException` must declare `throws StartupException` or the caller must handle it accordingly. Distinguish the options:

| Choice | Impact on caller | Cause preserved |
| --- | --- | --- |
| Rethrow original checked exception | Caller continues to catch/declare that checked type | Keeps original object |
| Wrap into a new checked exception | Caller catches/declares the new checked type | Yes, if `original` is passed as cause |
| Wrap into an unchecked exception | No compile-time catch/throws requirement | Yes, if `original` is passed as cause |
| Instantiate wrapper and ignore it | Caller may assume the operation succeeded | No valid error reporting |
| Copy only `original.getMessage()` | May change contract, but loses cause link | No |

Choose checked vs. unchecked based on the caller's ability to handle it, module conventions, and how expected the failure is. Do not use unchecked exceptions merely to “escape the compiler” without designing a failure-handling strategy.

## 12. Mistakes to Avoid When Writing Custom Exceptions

### 12.1. Do not forget to pass the cause to the superclass

Mistake:

```java
class BadImportException extends Exception {
    BadImportException(String message, Throwable cause) {
        super(message); // Cause is received but ignored.
    }
}
```

This is a **syntactically valid class that is functionally wrong** if the API promises to preserve the cause. The `cause` parameter is ignored; `getCause()` on the wrapper will not point to the original error by default.

Fix:

```java
class GoodImportException extends Exception {
    GoodImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

### 12.2. Do not store the cause in a custom field while bypassing the standard API

Avoid having only:

```java
class NonstandardException extends Exception {
    private final Throwable original;

    NonstandardException(Throwable original) {
        this.original = original;
    }
}
```

This illustrative class compiles, but `Throwable.getCause()` does not reflect the custom `original` field. Standard loggers and diagnostic tools will not automatically discover the cause through the standard API. If domain-specific data is needed, still call `super(message, cause)`, and add business fields **without replacing** the cause.

### 12.3. Do not turn the cause into a string

`cause.toString()` can provide a helpful message, but it does not replace a `Throwable` link. Storing only an error string can lose the exception type, stack trace, suppressed exceptions, and subclass fields.

### 12.4. Do not set the cause twice

If a constructor has already called `super(message, cause)`, calling `initCause(newCause)` afterward typically throws `IllegalStateException`. A throwable does not have a contract for repeatedly changing its cause once set.

### 12.5. Do not use `catch (Throwable)` just to wrap everything

`Throwable` includes `Error`. Catching and converting every `Error` into a `RuntimeException` may look “uniform,” but it can mask serious JVM or resource errors that the program cannot safely handle. Only catch types that match your contract and handling strategy.

### 12.6. Do not lose the original failure site by recreating the cause

Snippet:

```java
catch (java.io.IOException original) {
    throw new IllegalStateException(
            "Cannot read", new java.io.IOException(original.getMessage()));
}
```

This snippet is **wrong for preserving diagnostics**: the new “cause” is a different `IOException` object whose stack trace is recorded at the **re-creation site**, not where the original error occurred. Pass `original` directly.

## 13. Printing Stack Traces and Reading the Cause Chain

Calling:

```java
failure.printStackTrace();
```

typically prints the exception to `System.err`, including relevant `Caused by:` and `Suppressed:` links. Do not expect stack traces on a single line or fixed source line numbers: class, file, module, line location, and frame elision details can vary across builds and JVMs.

Conceptual example:

```text
ImportException: cannot import
    at ImportService.importData(...)
Caused by: StorageException: cannot read
    at StorageService.load(...)
Caused by: IOException: access denied
    at FileService.open(...)
```

This is an **abbreviated diagram**, not exact program `stdout`; `...` denotes illustrative frames.

Many loggers accept a `Throwable` object directly:

```java
logger.error("Import failed", failure);
```

This is an **illustrative logging-framework snippet**, not standalone Java SE syntax because `logger` depends on a library API. The goal: pass **the `Throwable` object**, not just `failure.getMessage()`. The exact API signature and formatting depend on the specific logging library.

Do not log the same exception at every layer and then rethrow it unnecessarily. A common practice is for lower layers to only add context when wrapping, while the final handling boundary decides on logging and user-facing messages.

### Additional information in messages

A good wrapper message should state the operation and safe context:

- `"Cannot parse import batch 42"`.
- `"Cannot load application configuration"`.
- `"Could not persist invoice"`.

Avoid overly generic messages like `"error"`, while also not putting passwords, tokens, sensitive data payloads, full connection strings, or unnecessary user data into errors or logs. Because a cause itself can contain sensitive information, logging and stack-trace exposure policies remain important.

## 14. Complete Example: Omitting vs. Preserving the Cause

Create **`CauseLossComparisonDemo.java`**:

```java
import java.io.IOException;

public class CauseLossComparisonDemo {
    static IllegalStateException withoutCause(IOException original) {
        return new IllegalStateException("service failed");
    }

    static IllegalStateException withCause(IOException original) {
        return new IllegalStateException("service failed", original);
    }

    public static void main(String[] args) {
        IOException root = new IOException("database unavailable");

        IllegalStateException lost = withoutCause(root);
        IllegalStateException kept = withCause(root);

        System.out.println("lost cause=" + (lost.getCause() == null));
        System.out.println("kept identity="
                + (kept.getCause() == root));
        System.out.println("root message="
                + kept.getCause().getMessage());
    }
}
```

```bash
javac CauseLossComparisonDemo.java
java CauseLossComparisonDemo
```

`stdout`:

```text
lost cause=true
kept identity=true
root message=database unavailable
```

The key point is that `kept.getCause() == root` evaluates to `true`: the cause-accepting constructor retains **the exact original** `IOException` object, without making a copy. Conversely, `withoutCause` stores no link; a tool given only `lost` cannot traverse `getCause()` to find `root`.

## 15. Diagnosing Causes Safely

When you need to find the root cause in a system with many wrappers, you can follow `getCause()`. However, avoid writing an unbounded loop in case a `Throwable` from a custom library creates an unusual structure.

Example using `IdentityHashMap` to stop if the same **throwable object** is encountered again:

Create **`SafeCauseTraversalDemo.java`**:

```java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class SafeCauseTraversalDemo {
    static void show(Throwable failure) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        Throwable current = failure;
        while (current != null && visited.add(current)) {
            System.out.println(
                    current.getClass().getSimpleName()
                    + ": " + current.getMessage());
            current = current.getCause();
        }
    }

    public static void main(String[] args) {
        IOException root = new IOException("read failed");
        IllegalStateException middle =
                new IllegalStateException("load failed", root);
        RuntimeException outer =
                new RuntimeException("request failed", middle);

        show(outer);
    }
}
```

```bash
javac SafeCauseTraversalDemo.java
java SafeCauseTraversalDemo
```

`stdout`:

```text
RuntimeException: request failed
IllegalStateException: load failed
IOException: read failed
```

`IdentityHashMap` uses object identity for keys, which is suitable when you want to avoid revisiting the same `Throwable`. This loop only follows `getCause()`; it **does not** automatically traverse `getSuppressed()` at each layer. If building a complete exception-analysis tool, you must traverse both cause and suppressed links as a graph while tracking visited objects to prevent cycles.

In normal applications, loggers and `printStackTrace()` already present enough information; do not write a custom exception-tree traversal system unless you have a real need.

## 16. Decision Table: Rethrow, Wrap, or Handle?

| Situation | Usually appropriate handling | Reason |
| --- | --- | --- |
| Same checked exception type still fits the method contract | Let propagate or `throw original;` | Preserves exact original type, fewer wrapper layers |
| Crossing from I/O layer to business API with its own error contract | `throw new DomainException(context, original);` | Adds context and preserves cause |
| Current layer can safely retry/recover | Handle specifically here | No need to throw to upper layers if resolved |
| Checked exception becomes an unrecoverable startup failure | Can wrap as unchecked with cause | Caller needs a clear stop/logging policy |
| Resource close error occurs when a TWR body error already exists | Keep primary, let close become suppressed | Preserves both errors |
| Custom exception lacks a cause-accepting constructor | `initCause(original)` once, if valid | Maintains traceability in legacy APIs |
| Custom exception you are designing from scratch | Constructor `(String, Throwable)` | Explicit contract and safer |
| Intermediate layer only catches to print a message then rethrows | Consider removing redundant catch | Avoids duplicate logs and lost context |
| Encountering a serious `Error` | Do not catch/wrap indiscriminately | Safe recovery conditions may not exist |

These are design guidelines, not absolute rules. Final decisions should follow the API contract, recoverability, data criticality, and operational policy.

## 17. Common Misconceptions

**“Wrapping an error in a new exception automatically preserves the cause.”** False. If the constructor does not accept `cause`, the causal link may not be stored.

**“Just concatenate `original.getMessage()` into the wrapper's message.”** False. A message does not replace the `Throwable` object, stack trace, or suppressed exceptions.

**“`getCause()` returns a new error created by `RuntimeException`.”** False. If the constructor receives `original`, `getCause()` returns that exact reference.

**“`initCause` can be called as many times as needed.”** False. The cause can generally only be initialized once; subsequent attempts throw `IllegalStateException`.

**“You can set the wrapper itself as its own cause.”** False. Direct self-causation is rejected.

**“`getCause()` and `getSuppressed()` are the same.”** False. Cause represents the causal/wrapping relationship; suppressed records additional errors.

**“Wrapping an error that has suppressed exceptions moves them to the wrapper.”** False. Suppressed exceptions stay on the original cause object unless code explicitly adds them to the wrapper.

**“Wrapping a checked exception into an unchecked one means the error is handled.”** False. It only changes the compile-time checking contract; runtime can still fail.

**“You should catch `Throwable` to wrap `Error` as well for consistency.”** This should not be the default; many `Error` types indicate unrecoverable situations.

**“Every layer should wrap with another exception even without adding information.”** No. Deep wrapper chains complicate diagnosis.

**“To log the cause, `getMessage()` is enough.”** Insufficient in many cases; the message omits the stack trace, cause, and suppressed exceptions.

**“`printStackTrace()` only displays the outermost exception.”** Incorrect: it is designed to show the cause chain and relevant suppressed exceptions.

**“If a custom exception stores an `original` field, Java tools will recognize it as the cause.”** Not automatically. Call `super(message, cause)` or link via `initCause` when valid.

**“Using `new IOException(original.getMessage())` is equivalent to keeping the old `IOException`.”** False. It is a new object with a new stack trace and no link to the original object.

**“If there is a cause, you don't need to check suppressed exceptions.”** False. Resource-close errors may reside in the suppressed list of an underlying cause.

## 18. Self-Check Questions

1. **When wrapping `IOException` into `ImportException`, how do you preserve the cause?** Use `new ImportException("context", original)` and call `super(message, cause)` in the custom class.
2. **Does writing only `new ImportException(original.getMessage())` preserve the original object?** No.
3. **What type does `getCause()` return?** `Throwable` or `null`, depending on the cause state.
4. **Does `getCause()` return the exact object passed to the constructor?** Yes; it does not clone it.
5. **How does a cause differ from a suppressed exception?** Cause describes the causal/wrapping relationship; suppressed records secondary errors, typically during cleanup.
6. **A failed read `IOException` has a suppressed exception from `close()`. After wrapping the `IOException`, where is the suppressed exception?** On the cause `IOException` object itself unless explicitly moved/modified.
7. **Should you create a new exception with only the cause's message and pass it as the cause?** No, because that loses the original object and stack trace.
8. **Can `initCause` replace a cause already set by a constructor?** No; re-initializing throws `IllegalStateException`.
9. **Is passing an exception object as its own cause valid?** No, it throws `IllegalArgumentException`.
10. **When the method contract already allows checked `IOException` and there is no new context, is a wrapper needed?** Usually no; you can let the exception propagate.
11. **Does wrapping `IOException` into `IllegalStateException` fix the read error?** No.
12. **What happens if a handler creates a wrapper but does not `throw` it?** The caller may not be notified of the error; the wrapper is simply a discarded object.
13. **Should you catch every `Error` to wrap it into a business exception?** No; many `Error` types represent critical failures.
14. **Should you log an exception at every layer and rethrow it?** Usually no; choose an appropriate logging boundary to avoid duplication.
15. **Does a long chain of wrapper → cause → cause lose the root error?** No, as long as each layer preserves the corresponding cause object.
16. **Should you traverse `getCause()` infinitely without checks when analyzing custom error objects?** No. General-purpose tools can track object identity to prevent cycles.
17. **Can the same `Throwable` have both a cause and suppressed exceptions?** Yes; they serve two different purposes.
18. **When should `initCause` be used?** Primarily for compatibility with legacy exception APIs that lack a suitable constructor and when the cause has not yet been set.

## 19. Java 17 Documentation

- [Java SE 17 — Throwable constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructors storing `message`, `cause`, suppression, and stack trace.
- [Java SE 17 — Throwable.getCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getCause()): accessing the stored cause.
- [Java SE 17 — Throwable.initCause](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#initCause(java.lang.Throwable)): one-time cause initialization and its limitations.
- [Java SE 17 — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): additional errors independent of cause.
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): constructor with `(String, Throwable)`.
- [Java SE 17 — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception capable of accepting a cause.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): throwing, catching, and checking exceptions.
- [Java Language Specification 17 — §14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): primary/suppressed behavior during resource closing.

**Remember:** When you need to wrap an exception, pass **the exact caught exception object** to a cause-accepting constructor, such as `throw new DomainException("meaningful context", original);`. That lets upper layers handle an appropriate error type while still tracing `getCause()` back to the root cause along with its stack trace and suppressed exceptions. Use `initCause()` only when necessary and valid; never treat copying a message as a substitute for preserving the cause chain.
