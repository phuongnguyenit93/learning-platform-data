# Looking Up the JLS, `Throwable` Javadoc, and Per-API Exception Contracts in Java

When reading or writing Java code, a common question is: **what exceptions can this method throw, how are those exceptions caught or propagated, and which documentation is the authoritative reference?** This cannot be answered accurately from an exception's name alone, a forum snippet, or a single trial run. Java has multiple layers of documentation with distinct scopes of responsibility:

1. **Java Language Specification (JLS):** specifies the language rules, such as `throw`, `throws`, checked exception checking, `catch` branch selection, and how `finally` and `try-with-resources` complete.
2. **`Throwable` Javadoc:** the contract for the components and operations on an error object: message, cause, stack trace, suppressed exceptions, constructors, and `initCause`.
3. **Specific API Javadoc:** which exceptions a method such as `Files.readString`, `Thread.sleep`, `Future.get`, or `CompletableFuture.join` declares, which error corresponds to which condition, when the call returns, and what side effects occur.

The right approach is to **read all three places when needed**, cross-check against the **exact Java version in use**, and then write a small example to verify your understanding. This article uses **JLS Java SE 17 and Java 17 Javadoc** as a consistent baseline; features or signatures from other Java versions must be looked up in their corresponding documentation.

## 1. Documentation Source Map: What to Ask, Where to Read?

| Question | Primary Source | What to Look Up in the Documentation |
| --- | --- | --- |
| Why must `IOException` be caught or declared? | JLS §11.1–§11.2 | Checked/unchecked, compile-time checking |
| How do `throw` and `throws` differ? | JLS §14.18, §8.4.6 | Throw statement vs. clause in the method signature |
| What types does `catch (Exception e)` handle? | JLS §11.2–§11.3, §14.20 | Catchable types, handler ordering, exception analysis |
| Can `finally` override `return` or the original error? | JLS §14.20.2 | Normal/abrupt completion rules |
| Where does a `close()` error go when the `try` body also fails? | JLS §14.20.3 and `Throwable` Javadoc | `try-with-resources`, suppressed exceptions |
| Why does `new Wrapper(message, cause)` differ from `new Wrapper(message)`? | `Throwable` Javadoc | `getCause`, constructors, and cause chain |
| Can `initCause()` be called multiple times? | `Throwable` Javadoc | Single-time cause initialization and error on invalid call |
| What does `getStackTrace()` tell you? | `Throwable` Javadoc | Stack trace, `fillInStackTrace`, possibly empty data |
| Does `Files.readString(path)` have `throws IOException`? | `Files.readString` Javadoc | Signature, `Throws` section, condition semantics |
| Can `Thread.sleep(...)` receive an interrupt? | `Thread.sleep` Javadoc | `InterruptedException`, interrupted status handling |
| How do `join()` and `get()` report errors differently? | `CompletableFuture`, `Future` Javadoc | `CompletionException`, `ExecutionException`, cancellation, interruption |
| Does behavior change in another JDK? | **Version-matched** JLS/Javadoc | `Since`, implementation notes, deprecation |

Do not confuse **general language rules** with the **promises of a specific method**. The JLS determines when a program compiles and how control flow behaves when an error is thrown. It cannot replace the specification stating that `readString` reads UTF-8 or that a `Future.get` deadline may throw `TimeoutException`.

### Three Starting Links

- JLS 17, Chapter 11 — Exceptions: https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html
- JLS 17, Chapter 14 — Statements (`throw`, `try`, `catch`, `finally`, `try-with-resources`): https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html
- Java 17, `Throwable` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html

All examples in this article use the **Java 17 specification**. When a project uses Java 21 or another version, switch both documentation sets to that version before applying conclusions about newer APIs.

## 2. How to Read the JLS for Your Specific Question

The JLS is not a list of programming tips. It presents the **normative rules** of the Java language. When looking something up, read the exact section along with all conditions and exceptions to the rule.

### 2.1. JLS §11 — Exception Kinds and Compile-Time Checking

The JLS distinguishes:

- **Checked exceptions:** classes under `Throwable` that are **not** in the `RuntimeException` or `Error` hierarchy. Common examples include `IOException`, `SQLException`, and `InterruptedException`.
- **Unchecked exceptions:** `RuntimeException` and its subclasses, and `Error` and its subclasses. Programmers are not required to declare these with `throws`.
- **Compile-time exception checking:** if an invocation, statement, or method body can throw a checked exception according to the compiler's analysis, it must be appropriately caught or covered by a compatible `throws` declaration.

Read **§11.2.1** and **§11.2.2** when the question is "how does the compiler determine which exceptions *can be thrown*?". Read **§11.2.3** when you see a compile error like *unreported exception; must be caught or declared to be thrown*.

Example that **intentionally does not compile**, used to look up checked exception errors:

```java
import java.io.IOException;

class IncorrectCheckedHandling {
    static void read() throws IOException {
        throw new IOException("read failed");
    }

    static void run() {
        read(); // Compile error: IOException is not caught or declared.
    }
}
```

There is no command to run the program above because this code is **deliberately written to be rejected by the compiler**. Fix it by declaring `static void run() throws IOException`, or by catching `IOException` and handling it properly here. Do not blindly turn it into `catch (Exception ignored) {}` just to silence the compiler error.

**Note:** the compiler checks **checked exceptions that can arise under static analysis**; it does not guarantee that no other unchecked exceptions will occur at runtime. Java also does not require Javadoc to list every situation such as a `NullPointerException` caused by a bug in caller code.

### 2.2. JLS §8.4.6 — The `throws` Clause

Example:

```java
static String load() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

This is an **illustrative method** that needs to be placed inside a Java class; a program without a `config.txt` file can still compile, though it may fail at runtime. `throws IOException` states that the method may **allow this checked exception to escape**; it does not mean every call is guaranteed to throw an error or that it has already been handled.

The `throws` clause is also part of the overriding contract: an overriding method cannot broaden the set of checked exceptions beyond the superclass/interface method's contract under JLS rules. Do not change a method signature just because a low-level call now uses a different library; consider translating exceptions at an appropriate boundary while **preserving the cause**.

### 2.3. JLS §14.18 — The `throw` Statement

`throw expression;` actually transfers control flow using a `Throwable` object or subclass. By contrast, `throws X` appears in a method or constructor **declaration**. The JLS also explains the static type of the thrown expression, handling `throw null`, and the case where evaluating the expression that creates the exception itself fails.

Do not use `throw` to express normal success states if a return type can represent them more clearly. However, exceptions remain a valid way to report exceptional conditions that the caller must handle.

### 2.4. JLS §14.20 — `try`–`catch`–`finally`

This is where to look when you need to know:

- Which `catch` can intercept an exception and why `catch` order matters.
- Why `finally` still executes on a `return` or `throw` path.
- What happens when `finally` itself returns or throws a new error.
- Which exception is **primary** when both the `try-with-resources` body and `close()` fail.

Example:

```java
static int masked() {
    try {
        throw new IllegalStateException("origin");
    } finally {
        return 10;
    }
}
```

This is an **illustrative method**. It completes normally with `10`; the `return` statement inside `finally` replaces the abrupt completion from `try`. The code is valid at the language level, but it is an anti-pattern to avoid because it masks the root cause of failure.

**Do not infer** that `finally` always completes successfully, always preserves the original error, or always runs when the entire JVM process is terminated abruptly. The JLS specifies the behavior of a Java execution thread under applicable conditions, not a guarantee of data recovery after the operating system kills the process.

## 3. How to Read `Throwable` Javadoc: What Data Does an Error Object Carry?

`Throwable` is the root class of `Exception` and `Error`, defining most diagnostic mechanisms:

| Component | Method | What Not to Misunderstand |
| --- | --- | --- |
| Detail message | `getMessage()` | Can be `null`; not a stack trace or cause |
| Cause | `getCause()` | Can be `null`; not automatically attached when only passing a message |
| Suppressed exceptions | `getSuppressed()`, `addSuppressed(...)` | Secondary errors, not the primary cause |
| Stack trace | `getStackTrace()`, `printStackTrace(...)` | Can be empty if disabled or data is missing |
| Re-record stack | `fillInStackTrace()` | Actively updates the stack info of the object itself |
| Set stack | `setStackTrace(...)` | Should not be used to falsify error locations |
| Attach cause after creation | `initCause(...)` | Can only be initialized once when the cause is uninitialized |

### 3.1. Message Is Not Cause

Compare:

```java
Throwable root = new java.io.IOException("disk unavailable");

RuntimeException lost =
        new IllegalStateException("load failed: " + root.getMessage());

RuntimeException preserved =
        new IllegalStateException("load failed", root);
```

This is an illustrative snippet inside a method. `lost.getCause()` is `null`, whereas `preserved.getCause() == root` is `true`. When a formatter prints the stack of `preserved`, an investigator can inspect the **`Caused by:`** chain and the root cause. When only the message is kept, the logger cannot reconstruct the stack frames from `root`.

### 3.2. Constructors with Cause and `initCause()`

A constructor taking `(String message, Throwable cause)` is usually the clearest way to wrap an error. `initCause(...)` exists to support exceptions created without an initialized cause, but it is not a setter that can be changed at will: calling it again after a cause has already been set throws `IllegalStateException`; setting an object as its own cause is also invalid.

In particular, a constructor that has **initialized the cause to `null`** differs from a constructor that leaves the cause *uninitialized*. `getCause() == null` by itself does not guarantee that calling `initCause(...)` is allowed; you must check which constructor was used.

### 3.3. Suppressed Exceptions and `try-with-resources`

Suppose `read()` throws `IOException("read failed")` and then `close()` also throws `IOException("close failed")`. With `try-with-resources`, typically:

```text
IOException: read failed      <-- primary exception
  Suppressed: IOException: close failed
```

This is a diagram of the error structure, not stdout with fixed line numbers. The resource-closing error is in `getSuppressed()` of the primary exception; it is **not** `getCause()` simply because it happened later. If you use a manual `finally` and `close()` throws an error, the behavior may differ and the cleanup error can mask the original error.

### 3.4. Stack Traces Are Not Permanently Immutable Records

Normal `Throwable` constructors record the stack when the object is created (subject to API conditions). Rethrowing **the same object** is not required to create a new trace. `fillInStackTrace()` can update the trace. The `protected` constructor with `writableStackTrace=false` allows disabling stack recording, in which case `getStackTrace()` is empty.

An exception shared across multiple requests can carry a stack/cause/suppressed list that does not match individual incidents. When investigating performance or concurrency issues, pay attention to object ownership, but do not sacrifice stack traces for unexpected errors just to save allocations.

## 4. How to Read an API's Javadoc Page

Find the right class or interface, then locate the **exact overload** of the method. For each method, read in this order:

1. **Module/package/class:** for example `java.base` → `java.nio.file` → `Files`.
2. **Method signature:** name, parameter types, generic types, `static`/instance, return type, and `throws` in the signature.
3. **Main description:** success conditions, boundary conditions, resource-handling behavior, and ordering of side effects.
4. **Parameters / Returns / Throws:** the specific condition corresponding to each documented exception.
5. **`Since`, `@Deprecated`, `See Also`, implementation notes:** used to determine the version or limits of guarantees.
6. **Page for each listed exception type:** if you need to understand `TimeoutException`, `ExecutionException`, or `CancellationException`, read that class's Javadoc next.
7. **Links to the JLS or superinterface:** when the contract is constrained by the language or an overridden method.

Do not just read a single `throws IOException` line and stop. For example, `Files.readString` also involves character decoding, large data, and file closing. The `Throws` section may also document notable unchecked exceptions. **Do not conclude that "because `Throws` does not list `NullPointerException`, it can never happen."** Unchecked exceptions due to programming bugs or input objects can still occur under general semantics.

### 4.1. Exact Overload and Parameter Types

A class can have multiple methods with the same name. `Future.get()` differs from `Future.get(long timeout, TimeUnit unit)`: the second overload can additionally throw `TimeoutException`. `Files.readString(Path)` and `Files.readString(Path, Charset)` have different parameters, even though both can throw `IOException`.

Also distinguish `Thread.sleep(long)` from other overloads and newer API versions. Copying a link to the wrong overload can lead to a wrong answer even within the same class.

### 4.2. `Throws` Does Not Prescribe How to Handle

If Javadoc says `IOException` when reading a file fails, that **does not mean** a repository must catch it and return an empty string. Handling policy belongs to the application layer: propagate the error, retry when safe, return cached data, or report failure. The API contract describes what happens; **business logic decides the response**.

### 4.3. Check `Since` and the Project Version

`CompletableFuture.failedFuture(...)` has existed since Java 9. Other APIs or overloads may appear in newer versions. When an application targets Java 17, consult Java 17 documentation and test with `javac --release 17` to catch accidental use of signatures present in a newer JDK but **not in the target release's API**.

Javadoc is not the policy of every framework: a JDBC, Spring, or HTTP client library may wrap or translate exceptions. You must read the **actual API being called**, including intermediate layers where present, rather than assuming a JDK class's contract applies verbatim through a framework wrapper.

## 5. Case Study: `Files.readString(Path)` and `Integer.parseInt(String)`

These are two useful examples because one method has a checked exception, while the other typically reports invalid input with an unchecked exception.

### `Files.readString(Path)`

The Java 17 Javadoc for `java.nio.file.Files.readString(Path)` specifies return type `String` and `throws IOException`. It reads file contents as UTF-8 (in the single-parameter overload) and documents I/O failure cases or undecodable byte sequences. When called:

```java
static String readConfig(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

This is an **illustrative method**, placed inside a Java class. The compiler enforces handling `IOException` properly because it is checked; the caller can catch it at the appropriate layer. If a default configuration is desired, the fallback decision must be permitted by the application contract.

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

### `Integer.parseInt(String)`

`Integer.parseInt` can throw `NumberFormatException` when the string is not a valid number format. This is a subclass of `IllegalArgumentException`/`RuntimeException`, so the caller is **not forced by the compiler** to declare `throws NumberFormatException`.

```java
static int parseQuantity(String input) {
    return Integer.parseInt(input);
}
```

This is an illustrative method, excluding full business validation. When input comes from a user, invalid format is usually an expected scenario that should return an input validation error. If internal code always passes a valid literal and it unexpectedly fails, that may be a different bug. **The exception class name alone does not determine the recovery policy.**

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html

## 6. Case Study: `Thread.sleep` and `InterruptedException`

The Java 17 Javadoc for `Thread.sleep(...)` declares `InterruptedException` when the sleeping thread is interrupted. When the exception is thrown, the thread's interrupted status is cleared according to the `sleep` contract.

A method can **propagate the interrupt**:

```java
static void pause() throws InterruptedException {
    Thread.sleep(100);
}
```

If a method cannot declare `InterruptedException`, such as `Runnable.run()`, it may need to **catch, restore the flag, and exit**:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

This is an illustrative snippet inside a `void`-returning method. It **does not** mean you must always swallow or always restore every interrupt request: rely on the contract of the component being executed. The key point is not to turn an interrupt signal into fake success by continuing an infinite loop.

Do not equate `InterruptedException` of the **waiting thread** with an exception thrown by an asynchronous task on another thread. That distinction is especially important when reading `Future.get()`.

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

## 7. Case Study: `Future.get` and `CompletableFuture.join`

These two APIs are closely related, but their error-observation contracts differ.

| Call | Exceptions to Watch | Meaning |
| --- | --- | --- |
| `Future.get()` | `InterruptedException` | The waiting thread was interrupted |
| `Future.get()` | `ExecutionException` | The awaited task completed exceptionally; use `getCause()` |
| `Future.get()` | `CancellationException` | The future was cancelled (unchecked) |
| `Future.get(timeout, unit)` | Also `TimeoutException` | **This wait** timed out; does not itself fail the future |
| `CompletableFuture.join()` | `CompletionException` | The stage completed exceptionally, usually wrapping the cause |
| `CompletableFuture.join()` | `CancellationException` | Can be thrown directly if the future itself was cancelled |
| `CompletableFuture.get()` | `InterruptedException`, `ExecutionException` | Contract compatible with `Future.get()` |
| `CompletableFuture.orTimeout(...)` | Future completes exceptionally with `TimeoutException` if the deadline wins | Differs from a single `get(timeout, unit)` call's timeout |
| `CompletableFuture.completeOnTimeout(v, ...)` | Future completes normally with `v` if the deadline wins | Can mask the difference between a fallback and a real result |

`join()` does not declare `InterruptedException` or `ExecutionException`, but **that does not turn every error into a return value**. It reports failures through an unchecked path. If a `CompletableFuture` already holds a `CompletionException`, `get()` has its own way of presenting the cause; do not assume every path always has the same number of wrappers.

Javadoc:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Lookup tip:** when an exception is observed in a controller, determine whether it originated **in the supplier**, in a **`thenApply`/`handle` callback**, or at the **waiting `get()` call**. Two different failure sites can produce the same wrapper class. `getCause()` and the stack trace help trace the exact origin.

## 8. Standalone Java 17+ Example: Verifying the Looked-Up Contracts

Create the file **`ApiExceptionContractDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ApiExceptionContractDemo {
    static String parseStatus(String text) {
        try {
            return "value=" + Integer.parseInt(text);
        } catch (NumberFormatException invalid) {
            return "invalid number";
        }
    }

    static void checkedReadFailure() throws IOException {
        throw new IOException("disk offline");
    }

    static void preciseRethrow() throws IOException {
        try {
            checkedReadFailure();
        } catch (Exception original) {
            throw original;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("parseGood=" + parseStatus("25"));
        System.out.println("parseBad=" + parseStatus("abc"));

        try {
            preciseRethrow();
        } catch (IOException failure) {
            System.out.println("checked=" + failure.getMessage());
        }

        Thread.currentThread().interrupt();
        try {
            Thread.sleep(1000);
        } catch (InterruptedException interrupted) {
            System.out.println("sleepInterrupted="
                    + interrupted.getClass().getSimpleName());
            System.out.println("flagAfterSleepThrows="
                    + Thread.currentThread().isInterrupted());
            Thread.currentThread().interrupt();
            System.out.println("flagRestored="
                    + Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted(); // Clear the flag so subsequent examples are not affected.
        }

        CompletableFuture<String> failure =
                CompletableFuture.failedFuture(
                        new IOException("async disk offline"));

        try {
            failure.join();
        } catch (CompletionException wrapper) {
            System.out.println("joinWrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("joinCause="
                    + wrapper.getCause().getClass().getSimpleName());
        }

        try {
            failure.get();
        } catch (ExecutionException wrapper) {
            System.out.println("getWrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("getCause="
                    + wrapper.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 ApiExceptionContractDemo.java
java ApiExceptionContractDemo
```

Output:

```text
parseGood=value=25
parseBad=invalid number
checked=disk offline
sleepInterrupted=InterruptedException
flagAfterSleepThrows=false
flagRestored=true
joinWrapper=CompletionException
joinCause=IOException
getWrapper=ExecutionException
getCause=IOException
```

What these checks demonstrate:

- `Integer.parseInt` throws `NumberFormatException` for `"abc"`; the `catch` branch intentionally turns the input error into a status string.
- `checkedReadFailure()` throws checked `IOException`. `preciseRethrow()` uses `catch (Exception original) { throw original; }` yet is still permitted by the compiler to declare `throws IOException` because the catch parameter is **effectively final** and precise analysis determines which checked exceptions can escape under JLS §11.2.2. Reassigning the catch parameter or adding other checked exceptions inside `try` can change this conclusion.
- `Thread.sleep` encounters the interrupted status and throws `InterruptedException`; when caught, the flag has already been cleared. The example intentionally restores the flag and clears it at the end **only to isolate the demo program**; real business code should not clear interrupt requests arbitrarily.
- On the same `CompletableFuture.failedFuture(IOException)`, `join()` reports via `CompletionException`, while `get()` reports via `ExecutionException`; both have `IOException` as their cause.

The results use controlled inputs, independent of real files or thread races, so stdout can be verified deterministically.

## 9. Standalone Java 17+ Example: `Throwable`, Cause, and Cleanup Errors

Create the file **`ThrowableDocumentationDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class ThrowableDocumentationDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void read() throws IOException {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        }
    }

    public static void main(String[] args) {
        try {
            read();
        } catch (IOException original) {
            IllegalStateException wrapper =
                    new IllegalStateException("import failed", original);

            System.out.println("outer=" + wrapper.getMessage());
            System.out.println("causeType="
                    + wrapper.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + wrapper.getCause().getMessage());
            System.out.println("suppressedCount="
                    + original.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + original.getSuppressed()[0].getMessage());

            StringWriter output = new StringWriter();
            wrapper.printStackTrace(new PrintWriter(output));
            String trace = output.toString();
            System.out.println("containsCause="
                    + trace.contains("Caused by: java.io.IOException: read failed"));
            System.out.println("containsSuppressed="
                    + trace.contains(
                            "Suppressed: java.io.IOException: close failed"));
        }

        Exception legacy = new Exception("legacy");
        legacy.initCause(new IOException("first cause"));
        boolean secondRejected = false;

        try {
            legacy.initCause(new IOException("second cause"));
        } catch (IllegalStateException expected) {
            secondRejected = true;
        }

        System.out.println("initCauseOnce=" + secondRejected);
        System.out.println("causeStill="
                + legacy.getCause().getMessage());
    }
}
```

Compile and run:

```bash
javac --release 17 ThrowableDocumentationDemo.java
java ThrowableDocumentationDemo
```

Output:

```text
outer=import failed
causeType=IOException
causeMessage=read failed
suppressedCount=1
suppressedMessage=close failed
containsCause=true
containsSuppressed=true
initCauseOnce=true
causeStill=first cause
```

**Analysis:**

1. `read()` throws `IOException("read failed")` from the `try` body.
2. `FailingResource.close()` also throws `IOException("close failed")`.
3. Under the `try-with-resources` contract, the read exception is primary and the close error is recorded in its suppressed exceptions.
4. The wrapper `IllegalStateException("import failed", original)` **preserves the original object**, allowing readers to trace both the primary and secondary errors.
5. `printStackTrace` displays `Caused by:` and `Suppressed:`; the example uses stable substring checks instead of printing line-specific stack frames.
6. `initCause` succeeds the first time on an `Exception` created with a message-only constructor; the second call is rejected and the previously assigned cause remains unchanged.

A different constructor that has already initialized the cause (even to `null`) may disallow `initCause`. When designing your own exception classes, prefer constructors accepting `cause` rather than creating an object and trying to set the cause elsewhere.

## 10. Understanding How the JLS and Javadoc Complement Each Other

Consider the same snippet:

```java
static String read(Path path) throws IOException {
    return Files.readString(path);
}
```

This is an illustrative snippet requiring imports for `Path`, `Files`, and `IOException`. Three statements should be distinguished:

- **`Files.readString` Javadoc:** describes the read operation and the exceptions that may arise under the API contract.
- **JLS §11.2:** explains why checked `IOException` must be handled or allowed to propagate via the method's `throws` clause.
- **`Throwable` Javadoc:** explains how to inspect cause, message, stack, and suppressed exceptions if the caller catches or wraps the error.

Reading only the JLS does not tell you the UTF-8 details of `Files.readString`. Reading only the `Files` Javadoc does not fully explain why the compiler rejects a method missing `throws`. Reading only `Throwable` does not tell you which method produces the error.

### A 7-Step Workflow When Encountering an Unfamiliar Exception

1. **Identify the API and the running/build version.** Note the package, class, method, overload, parameter types, and Java release.
2. **Read the Javadoc signature.** Pay attention to checked exceptions in `throws`, root interfaces, and overload variants.
3. **Read the `Throws` section and method description.** Note the exact failure conditions and whether state or resources change before throwing.
4. **Cross-check the JLS when the question involves the compiler or control flow.** Use §11.2 for checked exceptions, §14.18 for `throw`, and §14.20 for `catch`/`finally`/resources.
5. **Read `Throwable` if there is a wrapper/cause/suppressed exception.** Determine where the root cause sits and whether any secondary error was lost.
6. **Run a minimal program with deterministic inputs.** Compile with `javac --release` for the exact target version. Do not use a single successful run to claim no case can fail.
7. **State conclusions and limits clearly.** Separate "guaranteed by JLS", "guaranteed by API Javadoc", "merely observed behavior on a specific JVM", and "application business decision".

## 11. Reading Stack Traces and Causes to Trace Violated Contracts

If a log looks like:

```text
java.util.concurrent.CompletionException: java.io.IOException: disk offline
    at ...
Caused by: java.io.IOException: disk offline
    at ...
```

This is an **illustration**, not complete stdout. Distinguish:

- `CompletionException`: a wrapper describing the failure of an asynchronous stage.
- `IOException`: the cause exception type, likely from an internal I/O operation.
- Stack frames: where the exception's stack was created/filled and the call path; not necessarily the entire request history across multiple threads.
- `getCause()`: the cause link to trace the underlying error; not always just one level deep.
- `getSuppressed()`: secondary errors, not synonymous with cause.

A logger that accepts the `Throwable` itself generally preserves this information better than logging only `getMessage()`. However, a formatter or backend can be configured to truncate stacks, so check the actual logging setup.

To classify errors at a handling boundary, you can unwrap known technical wrappers such as `CompletionException` and `ExecutionException`, but do not strip every wrapper automatically: a business exception may carry important context about the operation that failed. When logging, preserve enough of the chain for diagnosis.

## 12. Distinguishing API Contracts from Implementation Details

Javadoc sometimes includes an **implementation note** or describes behavior specific to one implementation. Understand the guarantee levels:

- **JLS specification** is the language rule; valid Java code must satisfy those requirements.
- **Javadoc API contract** describes the promised behavior for the class/method, including the stated `Throws` conditions.
- **Implementation note** may explain the strategy in a particular implementation, which is not necessarily guaranteed for every implementation of the same interface.
- **Runtime observations** such as stack frame counts or callback ordering across threads do not automatically become language guarantees.

For example, `CompletableFuture.cancel(boolean)` notes regarding its `mayInterruptIfRunning` argument for the `CompletableFuture` implementation that it is not used to interrupt the computation the way `FutureTask` might. Therefore, do not infer from the name `cancel(true)` that the supplier will always be interrupted.

Another example: `AutoCloseable.close()` has a signature permitting `throws Exception`, while subinterfaces like `Closeable` narrow the checked exception. You cannot look only at the broader interface and conclude that every concrete `close()` declares `throws Exception`.

For third-party API methods, check the dependency version. A library upgrade can change wrapper types or when errors are thrown without changing JLS rules.

## 13. Common Pitfalls When Looking Up Exceptions

| Pitfall | Why It Goes Wrong | How to Verify |
| --- | --- | --- |
| Using newer Java Javadoc for a Java 17 project | The API/overload might not exist in Java 17 | Pick the exact `/java/javase/17/` page and test with `javac --release 17` |
| Looking only at the method name | You do not know which overload is being called | Match full name, parameters, and return type |
| Assuming `Throws` lists every possible runtime error | Unchecked exceptions from code or state may not all be listed | Combine JLS, method semantics, and real inputs |
| Thinking `throws` is an error-handling statement | It is only a declaration | See §8.4.6 and §11.2 |
| Thinking checked exceptions are always recoverable | Compiler mechanism differs from business policy | Read failure conditions and design handling boundaries |
| Thinking unchecked exceptions can be ignored | They may be bugs or expected invalid inputs | Check the contract and handle appropriately |
| Thinking every `Exception` is checked | `RuntimeException` is unchecked | See JLS §11.1 classification |
| Thinking `getMessage()` is the cause | Message is just a string | Use `getCause()` and `printStackTrace()` |
| Thinking `finally` always preserves the prior error | A return/throw in `finally` can mask errors | Read JLS §14.20 and test dual-error cases |
| Thinking `getSuppressed()` holds every cause | Suppressed and cause have different meanings | Read `Throwable`, test `try-with-resources` |
| Thinking a `Future.get(timeout)` timeout means the work was cancelled | An expired wait does not automatically cancel the future | Read the exact overload and cancellation policy |
| Thinking `join()` and `get()` throw the same exception types | One is unchecked, the other has checked `ExecutionException` | Read both `Future` and `CompletableFuture` |
| Copying code that runs on a newer JDK and assuming it is valid for Java 17 | Easy to use APIs absent in the target release | Compile with `--release 17` |
| Relying on a single online answer | May omit version or boundary conditions | Cross-check authoritative sources and run a minimal test |

## 14. Lookup Exercises and Self-Check

**Q1.** Where do you look up whether `catch(IOException e)` catches `FileNotFoundException`?  
**Answer:** The JLS on exception types and handler selection; `FileNotFoundException` is a subclass of `IOException`, so an `IOException` handler can catch it if the exception reaches that point.

**Q2.** Where do you look up whether `Thread.sleep` clears the interrupted status when throwing `InterruptedException`?  
**Answer:** The Javadoc of `Thread.sleep` for the exact overload/version. Do not conclude this from the `InterruptedException` class name alone.

**Q3.** `throw new IOException(...)` does not compile in a `void run()` method with no catch/throws. Where do you look?  
**Answer:** JLS §11.2 (checked exception checking), §14.18 (`throw`), and §8.4.6 (`throws`).

**Q4.** Does `new RuntimeException("failed")` automatically have a cause?  
**Answer:** No cause object is attached just from having a message. To preserve the original exception, use a constructor taking `Throwable` where appropriate.

**Q5.** In `try-with-resources`, both the `try` body and `close()` fail. Where do you look?  
**Answer:** JLS §14.20.3 on resources and `Throwable` Javadoc on `getSuppressed()`.

**Q6.** Can `initCause` be called twice to replace the cause?  
**Answer:** No. Read the `Throwable.initCause` contract and prefer creating a wrapper with the cause from the start.

**Q7.** Does `CompletableFuture.join()` force the caller to `catch (ExecutionException)`?  
**Answer:** No. `join` uses an unchecked error path such as `CompletionException`, unlike `get()`.

**Q8.** Calling `future.get(100, MILLISECONDS)` times out, yet the work keeps running. Does this contradict the Javadoc?  
**Answer:** No. The timeout here limits a single wait; it does not mean the future has been cancelled.

**Q9.** If the Javadoc only shows `throws IOException`, can you guarantee `NullPointerException` will never occur?  
**Answer:** No. The documented exception list is not a proof that no unchecked exception can occur in any situation.

**Q10.** Does `throws IOException` automatically roll back any changes made before the error?  
**Answer:** No. The JLS governs exception propagation; rollback or compensation belongs to transaction/business contracts.

**Q11.** Is an `Error` caught by `catch (Exception e)`?  
**Answer:** No under normal inheritance rules: `Error` and `Exception` are two separate branches under `Throwable`. Avoid catching broad `Throwable` to make an application "never fail".

**Q12.** If an API inherits a method from another interface, which documentation should you check?  
**Answer:** The implementing class's Javadoc, the root interface's Javadoc, and JLS rules on overriding/checked exceptions. Distinguish the shared contract from implementation-specific behavior.

## 15. Checklist for Code Review and Production Investigation

When encountering a puzzling exception in a pull request or production:

1. Record the **target JDK** and running JDK; do not vaguely look up "current Java".
2. Identify the method signature and the **exact overload** being called.
3. Classify checked/unchecked using JLS rules rather than guessing from the name.
4. Read the `Throws` section and specific conditions in the Javadoc.
5. Distinguish errors **originating inside the task** from errors **when observing/waiting for the result**.
6. Check `getCause()` and `getSuppressed()` if there is a wrapper or a resource-closing failure.
7. Verify whether `finally` and `try-with-resources` preserve the primary error.
8. Check resource/data state after failure; `throws` does not roll back automatically.
9. If using a new wrapper, preserve the cause via a constructor that takes a cause.
10. Use `javac --release` and a deterministic example to verify the exact target version's API.
11. Clearly separate conclusions **guaranteed by the specification** from observations of "it ran like this".
12. Cite the exact JLS/Javadoc links in technical notes, avoiding documentation from a different release.

## 16. Reference List of Official Documentation to Revisit

| Topic | Official Documentation |
| --- | --- |
| JLS: exception kinds, checked exceptions, handlers | https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html |
| JLS: method `throws` | https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6 |
| JLS: `throw` statement | https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18 |
| JLS: `try`, `catch`, `finally`, `try-with-resources` | https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20 |
| `Throwable` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html |
| `AutoCloseable` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html |
| `Files` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html |
| `Integer` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html |
| `Thread` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html |
| `Future` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html |
| `CompletableFuture` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html |
| `CompletionException` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html |
| `ExecutionException` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html |

**Conclusion:** The JLS answers **which rules the Java language uses to handle exceptions**. The `Throwable` Javadoc answers **how an error object stores and presents diagnostic data**. The **specific API method's** Javadoc answers **when the method can fail and what is guaranteed**. Using all three sources, choosing the right version, and verifying with a minimal Java test is the reliable way to resolve an exception question.
