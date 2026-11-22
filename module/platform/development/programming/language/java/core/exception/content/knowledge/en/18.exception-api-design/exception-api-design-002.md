# Choosing Checked or Unchecked by Contract and Handling Capability in Java

A Java API must inform callers **when an operation cannot be completed** and what the caller is expected to do. Deciding between a **checked exception** and an **unchecked exception** is not merely choosing between `extends Exception` and `extends RuntimeException`: it is a decision about the **contract between the API implementer and the API consumer**, especially regarding handling capability, recovery, and the cost of propagating exceptions across multiple layers.

A pragmatic rule of thumb: if a failure condition is an **expected part of the operation** and the API consumer has a **reasonable handling action** (retrying, asking for different input, using a fallback source, skipping a record according to policy, or performing compensation), **a checked exception may be appropriate** to force the caller to consider that scenario. If the error represents **API misuse, a precondition violation, a bug/broken invariant**, or the caller has no recovery policy at that layer, **an unchecked exception is usually appropriate**.

This is a **design guideline**, not a mechanical rule enforced by Java. Some external infrastructure errors are represented by checked `IOException`, while other I/O errors are wrapped in unchecked `UncheckedIOException` when passing through callback APIs that do not declare `throws`. One caller may recover from certain unchecked exceptions, while another caller may be unable to recover from a checked exception. What matters is the **specific contract, API stability, responsibility boundaries, and error semantics**.

This article uses Java 17+ to explain the hierarchy, `catch-or-specify`, how to evaluate recoverability, choosing error types by layer, preserving the cause during exception translation, exceptions in interfaces/overriding, callbacks/asynchrony, retries, transactions, resource-closing errors, `InterruptedException`, testing, and anti-patterns to avoid.

## 1. Checked and Unchecked: What Are They Exactly?

Java classifies exceptions according to the `Throwable` hierarchy:

~~~text
java.lang.Throwable
  ├── java.lang.Error                       [unchecked]
  │     ├── AssertionError
  │     └── VirtualMachineError
  └── java.lang.Exception
        ├── IOException                    [checked]
        ├── SQLException                   [checked]
        ├── InterruptedException           [checked]
        ├── CustomFailure extends Exception [checked, if not under RuntimeException]
        └── java.lang.RuntimeException     [unchecked]
              ├── IllegalArgumentException
              ├── IllegalStateException
              ├── NullPointerException
              └── CustomFailure extends RuntimeException
~~~

According to JLS §11.1.1, **unchecked exception classes** consist of `RuntimeException` and its subclasses, and `Error` and its subclasses. All other exception classes in the `Throwable` branch are **checked**. Typically, a custom checked exception is created by `extends Exception`, while a custom unchecked exception is created by `extends RuntimeException`.

| Factor | Checked | Unchecked |
| --- | --- | --- |
| Common inheritance | `Exception` but not in the `RuntimeException` branch | `RuntimeException` or the `Error` branch |
| Compiler enforces `catch` or `throws`? | Yes, when a checked exception can escape a method and is not handled | No |
| Can be declared in `throws`? | Yes | Yes, though not required |
| Propagates up the call stack if uncaught? | Yes | Yes |
| Carries `message`, `cause`, `stack trace`? | Yes | Yes |
| Can be caught with `catch`? | Yes | Yes, if the policy is appropriate |
| Does the compiler force the caller to **recover successfully**? | No; it only forces catching or declaring | No |
| Used for invalid input / API misuse? | Depends on the contract | Usually `IllegalArgumentException` or an appropriate type |
| Used for recoverable environment errors? | Often a worthwhile option | Can also be appropriate at layers that cannot declare checked exceptions |

**Key point:** `catch-or-specify` is a **compile-time** obligation, not a guarantee that the error has been resolved. A caller can declare `throws` and pass responsibility up to the next layer. Conversely, an unchecked exception can still terminate the program abruptly if no layer handles it.

## 2. Example 1: Contract Differences Right at the Method

Save as `CheckedUncheckedContractDemo.java`:

~~~java
public class CheckedUncheckedContractDemo {
    static class DocumentUnavailableException extends Exception {
        DocumentUnavailableException(String message) {
            super(message);
        }
    }

    static class InvalidDocumentIdException extends RuntimeException {
        InvalidDocumentIdException(String message) {
            super(message);
        }
    }

    static String load(String id) throws DocumentUnavailableException {
        if (id == null || id.isBlank()) {
            throw new InvalidDocumentIdException("id must not be blank");
        }
        if ("offline".equals(id)) {
            throw new DocumentUnavailableException("document store offline");
        }
        return "document:" + id;
    }

    public static void main(String[] args) {
        try {
            System.out.println("ok=" + load("A-1"));
            load("offline");
        } catch (DocumentUnavailableException ex) {
            System.out.println("checked=" + ex.getMessage());
        }

        try {
            load("");
        } catch (InvalidDocumentIdException ex) {
            System.out.println("unchecked=" + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CheckedUncheckedContractDemo.java
java CheckedUncheckedContractDemo
~~~

Output:

~~~text
ok=document:A-1
checked=document store offline
unchecked=id must not be blank
~~~

Explanation:

- `DocumentUnavailableException extends Exception` is checked; `load` declares `throws DocumentUnavailableException` and the caller catches that type.
- `InvalidDocumentIdException extends RuntimeException` is unchecked; the compiler does not require adding it to `throws`. It expresses an **API precondition violation**.
- A caller can still catch the unchecked exception if it genuinely needs to turn a parameter error into a UI message. However, another layer might simply need to fix the bug of passing an invalid argument.
- The two error types have **different meanings**: a temporarily unavailable document might suggest retrying, whereas an empty ID must be fixed at the input; the exception kind should not be chosen based solely on where the exception is created.

If you omit `try-catch` or `throws` for `DocumentUnavailableException`, the compiler rejects the call when analyzing that a checked exception may be thrown. Even when the code compiles, a real policy is still needed after catching it.

## 3. What Does Reasonable Handling Capability Mean?

A useful question to ask before designing an exception type is: **can the specific caller return the system to a valid state after the failure?**

Meaningful handling actions may include:

1. **Bounded retry**, when the error is likely transient and the operation can be safely retried.
2. **Switching to a verified fallback source**, when the fallback does not corrupt data.
3. **Requesting corrected input**, such as choosing another file or reconfiguring a storage location.
4. **Skipping the failed item with recording**, if items are independent and policy allows it.
5. **Compensation/rollback**, when an operation fails after partially modifying state.
6. **Propagating the error to a layer with decision authority**, via `throws` or a domain exception with a cause.
7. **Shutting down the task cleanly**, when there is no opportunity for recovery, but the current layer is responsible for shutdown, cleanup, returning error details, or reporting failure status.

**Simply logging and swallowing an exception does not count as recovery.** Similarly, writing `catch (Exception ex) { throw new RuntimeException(ex); }` on its own only changes how the error propagates; it does not help recovery.

A command-processing system might have caller A as a user interface, which can prompt the user to fix a path; caller B might be an automated job, which cannot ask the user and can only report failure. It is the same `IOException`, yet the strategy differs between the two layers. Therefore, the checked/unchecked decision must consider the **target API consumer**, not just the exception name.

## 4. Decision Table for Practical Scenarios

| Scenario | Option Worth Considering | Rationale / Notes |
| --- | --- | --- |
| Caller passes an index outside the documented range | `IndexOutOfBoundsException` unchecked | Violation of the API usage contract |
| Required parameter receives `null` | `NullPointerException` unchecked or explicit validation | Code can be fixed at the boundary |
| Method called when the object is already closed | `IllegalStateException` unchecked | State does not permit the operation |
| User selects a nonexistent file | `IOException` / checked domain exception | Caller can choose another file; not mandatory for every API |
| Reading from a device/network fails transiently | Checked or unchecked domain exception | Consider retry authority, idempotency, framework, and calling layer |
| Business rule error where the caller is asked to adjust | Checked domain exception, validation result, or unchecked | Depends on whether failure is an expected business path and the communication contract |
| SQL error at the repository | `SQLException` checked in the JDBC API | Service layer can translate to a checked/unchecked domain failure |
| I/O error inside `Stream.map` | `UncheckedIOException` | `Function.apply` does not declare checked exceptions |
| Invariant violation due to an internal bug | Unchecked, sometimes `AssertionError` in debugging | Do not force callers to handle it as a recoverable failure |
| Bulk input API needing to report many invalid rows | `Result` / list of errors instead of throwing repeatedly | Per-item failure is an expected outcome |
| Thread is interrupted while waiting | `InterruptedException` checked | Must propagate or restore the interrupt according to contract |
| JVM encounters `OutOfMemoryError` | `Error`, do not create a custom business Error | Usually not reliably recoverable; design for shutdown/monitoring |

This is a **guideline table**, not a mandatory mapping in the JLS. Even an environment-caused error can be represented as unchecked when the target API design requires it; in that case, clearly document the error type, preserve the cause, and state the handling policy.

## 5. Example 2: Checked Exception When the Caller Has a Fallback Option

Suppose an API fetches data from an external service. If the access path temporarily fails but there is cached data **verified to be valid**, the caller can choose a fallback. This is a scenario where a checked exception helps the caller consider its options.

Save as `CheckedFallbackDemo.java`:

~~~java
import java.io.IOException;

public class CheckedFallbackDemo {
    static String remoteRead(boolean unavailable) throws IOException {
        if (unavailable) {
            throw new IOException("remote unavailable");
        }
        return "fresh-value";
    }

    static String readWithFallback(
            boolean remoteUnavailable, String cached) throws IOException {
        try {
            return remoteRead(remoteUnavailable);
        } catch (IOException ex) {
            if (cached != null) {
                return cached;
            }
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("remote="
                    + readWithFallback(false, "cached-value"));
            System.out.println("fallback="
                    + readWithFallback(true, "cached-value"));
            readWithFallback(true, null);
        } catch (IOException ex) {
            System.out.println("propagate=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedFallbackDemo.java
java CheckedFallbackDemo
~~~

Output:

~~~text
remote=fresh-value
fallback=cached-value
propagate=remote unavailable
~~~

In the example, `readWithFallback` uses the cache only when cached data exists. If there is no cache, it **rethrows the original IOException** so the upper layer can decide. This is an intentional error policy.

In real applications, a cache that “has data” is not necessarily “safe enough to use”: you also need to consider data age, consistency, access permissions, version, and freshness requirements. **Do not perform a fake fallback** by returning an empty string or fabricated data just to avoid an exception.

## 6. Example 3: Misuse Errors Should Be Detected via Unchecked Exceptions

If a caller passes a `quantity` of 0 to an API whose contract accepts only positive numbers, this is usually a **precondition violation**. The caller must fix the input before calling; the compiler does not need to force checked exception handling everywhere.

Save as `ArgumentContractDemo.java`:

~~~java
public class ArgumentContractDemo {
    static int price(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return Math.multiplyExact(quantity, 10);
    }

    public static void main(String[] args) {
        System.out.println("price=" + price(3));

        try {
            price(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentContractDemo.java
java ArgumentContractDemo
~~~

Output:

~~~text
price=30
invalid=quantity must be positive
~~~

Argument errors are checked **with code that always runs**, not with `assert`, which can be disabled. Using `Math.multiplyExact` also catches arithmetic overflow with `ArithmeticException` when a large quantity causes overflow.

Another scenario to distinguish: a user enters `"abc"` into a quantity field. This is an input validation error at the UI/API boundary. The request-handling layer can return a `ValidationResult` or map `NumberFormatException` to a field error; it is not necessary to create a mandatory checked exception across every layer just because the user can correct the data.

## 7. Placing Contract Boundaries: Infrastructure, Domain, Interface

Consider the layers:

~~~text
HTTP / CLI / Batch boundary
          |
          v
Application service
          |
          v
Repository / external client
          |
          v
Database / file / network
~~~

An infrastructure error like `SQLException` or `IOException` can have different semantics at each layer:

- **Repository** understands errors in technical terms: database connection, corrupted file, access limits.
- **Application service** understands business goals: unable to load order, unable to generate report, unable to save payment.
- **HTTP/UI boundary** understands the next action: return an error code, suggest retrying, ask to fix parameters, cancel the transaction, display a message, or alert operations.

Not every layer needs to wrap exceptions. Only **translate the error type when crossing a meaningful boundary**, for example when a repository does not want to expose `SQLException` as part of the service's public contract.

When translating, prefer a constructor of the form:

~~~java
public OrderLoadException(String message, Throwable cause) {
    super(message, cause);
}
~~~

This is an **illustrative constructor** of a class extending Exception or RuntimeException that has a corresponding constructor. `message` carries the meaning at the current layer; `cause` preserves **the exact original error object** along with its stack trace and suppressed exceptions. Avoid using only `new OrderLoadException(ex.getMessage())` if diagnosing the cause chain is still needed.

## 8. Example 4: Translating an Infrastructure Error into a Checked Domain Exception

Suppose the repository layer can throw `IOException`, but the service wants to publish a business-meaningful error so the caller can choose a fallback source or display an unavailable status.

Save as `CheckedTranslationDemo.java`:

~~~java
import java.io.IOException;

public class CheckedTranslationDemo {
    static final class ReportUnavailableException extends Exception {
        ReportUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() throws IOException {
        throw new IOException("storage offline");
    }

    static String loadReport() throws ReportUnavailableException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ReportUnavailableException(
                    "Report cannot be loaded", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(loadReport());
        } catch (ReportUnavailableException ex) {
            System.out.println("domain=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + ex.getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedTranslationDemo.java
java CheckedTranslationDemo
~~~

Output:

~~~text
domain=Report cannot be loaded
causeType=IOException
causeMessage=storage offline
~~~

This is **exception translation**, not “successful handling”. The caller knows the service did not complete the operation and receives the domain error type published by the service. A service interface can use `throws ReportUnavailableException` to force direct callers to consider this case.

If the service simply passes through `IOException` and the contract already promises IOException, wrapping it is unnecessary. Conversely, if the calling layer should not depend on infrastructure APIs, a stable domain exception allows changing the underlying implementation with minimal impact on callers.

## 9. Example 5: Translating to Unchecked at an API Boundary When Justified

An API may choose an unchecked domain exception for service failures to avoid forcing callers across many layers to add `throws`, or because a callback framework does not support checked exceptions. Even then, **a clear error type name and preservation of the root cause** are still required.

Save as `UncheckedTranslationDemo.java`:

~~~java
import java.io.IOException;

public class UncheckedTranslationDemo {
    static final class StorageFailure extends RuntimeException {
        StorageFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readStorage() throws IOException {
        throw new IOException("disk unavailable");
    }

    static String service() {
        try {
            return readStorage();
        } catch (IOException ex) {
            throw new StorageFailure("Service data unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(service());
        } catch (StorageFailure ex) {
            System.out.println("domain=" + ex.getMessage());
            System.out.println("checkedRequired=false");
            System.out.println("causeIsIOException="
                    + (ex.getCause() instanceof IOException));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UncheckedTranslationDemo.java
java UncheckedTranslationDemo
~~~

Output:

~~~text
domain=Service data unavailable
checkedRequired=false
causeIsIOException=true
~~~

The line `checkedRequired=false` describes the compile-time contract: `StorageFailure extends RuntimeException` does not require `throws`. **It does not prove the error has been resolved**. Without a catch block, StorageFailure will still propagate.

Do not turn every checked exception into an unchecked one just to silence compiler warnings. Before translating, determine **who takes responsibility for handling it** and whether the public API adequately documents the new error type. Switching to unchecked can cause existing callers to no longer be reminded by the compiler to handle a scenario that the business once considered important.

## 10. `throws` Is Part of the Contract, Not an Exhaustive List of All Errors

Example signature:

~~~java
String fetchReport(String key) throws ReportUnavailableException;
~~~

This is an **illustrative interface method**, assuming ReportUnavailableException is a checked exception.

Meaning: the program may allow that checked exception to escape at runtime, and the caller must catch or declare that type (or an appropriate supertype). This does **not** mean:

- The method **always** throws an error on every run.
- No other unchecked exceptions can occur.
- Writing `catch` guarantees the caller has recovered.
- The compiler forces the caller to know every possible environment error as a checked exception.

Checked exceptions can be handled locally with `catch` or propagated with `throws`. `throws RuntimeException` is also valid syntax, but it does not create the same compiler obligation.

**Do not write `throws Exception` out of habit** if the public API can use more specific error types. An overly broad type makes it hard for callers to know whether to retry, fix input, show a message, or stop. However, if an API genuinely has a contract for multiple independent failures that cannot be clearly expressed by specific types, consider separate interfaces, an error type/domain hierarchy, or a Result.

## 11. Interfaces and Overriding: Constraints on Checked Exceptions

An interface is a contract for all implementations. Java does not allow overriding a method with a signature that throws **broader checked exceptions** than the contract it overrides (JLS §8.4.8.3).

Valid example:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}

class MemoryLoader implements Loader {
    @Override
    public String load() {
        return "cached";
    }
}
~~~

These are **two valid declarations** when in the same file/package; the implementation narrows the contract by throwing no checked exceptions. At a call site using a reference of type `Loader`, the compiler still relies on the interface's `throws IOException`.

### Example 6: The Declared Type of the Reference Determines Checked Obligations

Save as `InterfaceContractDemo.java`:

~~~java
import java.io.IOException;

public class InterfaceContractDemo {
    interface Loader {
        String load() throws IOException;
    }

    static class MemoryLoader implements Loader {
        @Override
        public String load() {
            return "cached";
        }
    }

    public static void main(String[] args) {
        Loader asInterface = new MemoryLoader();
        MemoryLoader asConcrete = new MemoryLoader();

        try {
            System.out.println("interface=" + asInterface.load());
        } catch (IOException ex) {
            System.out.println("unexpected I/O");
        }

        System.out.println("concrete=" + asConcrete.load());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceContractDemo.java
java InterfaceContractDemo
~~~

Output:

~~~text
interface=cached
concrete=cached
~~~

It is the same runtime MemoryLoader object, yet two reference types lead to different **compile-time contracts**. `asInterface.load()` requires handling/declaring IOException; `asConcrete.load()` declares no checked exceptions.

Invalid example:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
interface Service {
    void run() throws java.io.IOException;
}

class InvalidService implements Service {
    @Override
    public void run() throws Exception {
    }
}
~~~

Overriding with `throws Exception` widens the allowed checked exceptions compared to `throws IOException`, so the compiler rejects it. To implement it, use the same or a narrower checked type, handle the error internally, or intentionally change the interface contract.

**Consequence when designing libraries:** adding a new checked exception to `throws` on a public method can break previously compiling client code. Contract changes require evaluating source-compatibility impact.

## 12. When Using Callbacks/Streams, Checked Exceptions May Not Fit the Contract

Several standard functional interfaces such as `Function<T,R>`, `Consumer<T>`, `Supplier<T>`, and `Runnable` **do not declare checked exceptions** on their abstract methods. Therefore, a lambda passed to `Stream.map` cannot directly throw a checked `IOException` outward.

The following snippet **intentionally does not compile**:

~~~java
// ASSUME read(String) throws IOException:
java.util.function.Function<String, String> f =
        text -> read(text); // IOException is not handled inside the lambda.
~~~

This cannot be fixed merely by adding `throws IOException` to the method **creating the lambda**; the lambda body must be compatible with the **target function type**.

Three common options:

1. **Catch directly inside the lambda** when a genuinely valid fallback value exists.
2. **Wrap IOException in UncheckedIOException** and preserve the cause, if the callback must report the error to an outer layer and the interface does not declare checked exceptions.
3. **Design a custom functional interface with throws E** when you control the API and want to preserve checked exceptions across callbacks.

### Example 7: Adapting I/O to Function

Save as `CallbackExceptionDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class CallbackExceptionDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IOFunction<T, R> operation) {
        return input -> {
            try {
                return operation.apply(input);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String fetch(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("remote read failed");
        }
        return "ok:" + id;
    }

    public static void main(String[] args) {
        Function<String, String> f = unchecked(CallbackExceptionDemo::fetch);
        System.out.println(f.apply("A"));

        try {
            f.apply("bad");
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper="
                    + ex.getClass().getSimpleName());
            System.out.println("cause=" + ex.getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackExceptionDemo.java
java CallbackExceptionDemo
~~~

Output:

~~~text
ok:A
wrapper=UncheckedIOException
cause=remote read failed
~~~

The adapter makes clear **where the checked contract is converted to unchecked**. The application does not assume every IOException is unrecoverable; it simply states that calls through a standard Function do not have `throws IOException`. The receiver of the callback must still have an appropriate failure-handling mechanism.

If writing a new API where callers are allowed to catch checked exceptions, using a dedicated interface such as `IOFunction` instead of always forcing through `Function` may be a better choice.

## 13. When Failure Is a Normal Outcome, Consider Result/Outcome

Not every “unsuccessful” case needs to throw an exception. For example, when importing a batch of order codes, a few malformed codes are an **expected scenario**, and you may want to report all errors so the user can fix them together.

A result value with an explicit status may be more appropriate:

~~~text
parse item
  ├── valid   -> Success(value)
  └── invalid -> Failure(code, field)
~~~

When using Result, the caller must check the status without catching an exception for every element. However, **do not turn serious infrastructure errors into values that look like success** or drop the cause when operations need it.

### Example 8: Distinguishing Validation Results from Exceptional Failures

Save as `ValidationResultDemo.java`:

~~~java
import java.util.List;

public class ValidationResultDemo {
    record ValidationResult(String raw, Integer value, String errorCode) {
        boolean success() {
            return errorCode == null;
        }
    }

    static ValidationResult parsePositive(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) {
                return new ValidationResult(raw, null, "NOT_POSITIVE");
            }
            return new ValidationResult(raw, value, null);
        } catch (NumberFormatException ex) {
            return new ValidationResult(raw, null, "INVALID_INTEGER");
        }
    }

    public static void main(String[] args) {
        for (String raw : List.of("10", "bad", "-2", "8")) {
            ValidationResult result = parsePositive(raw);
            if (result.success()) {
                System.out.println("ok=" + result.value());
            } else {
                System.out.println("error=" + result.errorCode());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidationResultDemo.java
java ValidationResultDemo
~~~

Output:

~~~text
ok=10
error=INVALID_INTEGER
error=NOT_POSITIVE
ok=8
~~~

This problem does not require a checked exception for the caller to choose a retry. Invalid values are normal input data in a validation workflow and are represented with stable codes. In production applications, the record may need a constructor/factory to enforce the “success XOR failure” invariant.

**Do not misunderstand this to mean Result is always better than exceptions**. If an API naturally recovers via exceptions or failures are exceptional, using exceptions avoids complicating the happy path. The decision depends on both failure frequency and caller needs.

## 14. Retry Does Not Mean Retrying Every Exception

Some checked exceptions reflect the environment and **may** be transient, but not every error of the same type should be retried.

For example, `IOException` can be caused by intermittent networking, a permanently missing file, denied read permissions, or corrupted data. The class name alone is not enough to conclude that a retry is safe.

Before retrying, ask:

- **Is the error likely transient?** A connection failure differs from a permanently nonexistent file.
- **Is the operation idempotent?** Retrying a payment command after a timeout can create duplicate transactions if the server already processed the request before the connection dropped.
- **Are there attempt and time limits?** Do not retry indefinitely.
- **Is there backoff/jitter?** Depending on the system, avoid putting concurrent load spikes on a failing service.
- **Is there a cancellation/interrupt signal?** Must stop when requested.
- **Is there a condition to switch to a fallback or report a final failure?**

### Example 9: Bounded Retry, for an Illustrative I/O Error Only

Save as `RetryPolicyDemo.java`:

~~~java
import java.io.IOException;

public class RetryPolicyDemo {
    private static int calls;

    static String readRemote() throws IOException {
        calls++;
        if (calls == 1) {
            throw new IOException("temporary outage");
        }
        return "READY";
    }

    static String retryAtMostThreeTimes() throws IOException {
        IOException last = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return readRemote();
            } catch (IOException ex) {
                last = ex;
                System.out.println("retry-after=" + attempt);
            }
        }

        throw last;
    }

    public static void main(String[] args) {
        try {
            System.out.println("result=" + retryAtMostThreeTimes());
            System.out.println("calls=" + calls);
        } catch (IOException ex) {
            System.out.println("failed=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RetryPolicyDemo.java
java RetryPolicyDemo
~~~

Output:

~~~text
retry-after=1
result=READY
calls=2
~~~

The example intentionally omits sleeping so stdout is deterministic, illustrating only a bounded recovery action. It is **not** a production-ready retry policy for distributed systems. In production, you should classify transient errors, use backoff, ensure idempotency, handle cancellation, enforce a time budget, and account for the possibility that a transaction completed even though the response was lost.

When exhaustion occurs, the example rethrows the last `IOException`. The caller still sees the real failure; the code does not silently return a fake value.

## 15. Preserving Cause and Suppressed Exceptions When Translating Error Types

An exception can contain:

- `getMessage()`: error information at the current layer.
- `getCause()`: the earlier exception that caused the current error.
- `getStackTrace()`: the stack frames associated with where the Throwable's stack trace was recorded.
- `getSuppressed()`: secondary errors, typically arising when closing resources in try-with-resources.

When wrapping a checked exception into a checked or unchecked domain exception via `super(message, cause)`, the JVM **keeps a reference to the cause**, rather than automatically copying the suppressed list onto the wrapper. Secondary errors can still be accessed through the cause.

### Example 10: Read Error as Primary, Close Error as Suppressed

Save as `SuppressedDomainDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedDomainDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class ImportFailure extends Exception {
        ImportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws ImportFailure {
        try {
            repository();
        } catch (IOException ex) {
            throw new ImportFailure("Import unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (ImportFailure ex) {
            Throwable root = ex.getCause();
            System.out.println("domain=" + ex.getMessage());
            System.out.println("cause=" + root.getMessage());
            System.out.println("causeSuppressed="
                    + root.getSuppressed()[0].getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuppressedDomainDemo.java
java SuppressedDomainDemo
~~~

Output:

~~~text
domain=Import unavailable
cause=read failed
causeSuppressed=close failed
wrapperSuppressed=0
~~~

Key point: **translating an exception with a cause** does not lose the resource-closing error on the IOException object; it remains in `root.getSuppressed()`. However, the new wrapper does not automatically have those same suppressed exceptions. When logging, pass the **Throwable object** to the logger to display the cause chain and suppressed exceptions rather than taking only `getMessage()` and discarding the rest.

## 16. `InterruptedException` Should Not Be Wrapped or Swallowed Like a Normal Error

`InterruptedException` is a special checked exception that typically indicates a blocking operation was requested to stop. Many methods such as `Thread.sleep` **clear the interrupt flag when throwing InterruptedException**.

When interrupted:

- If the signature allows it, **propagate `InterruptedException` up to the layer authorized to cancel the task**.
- If the API (for example, `Runnable.run()`) cannot declare this checked exception, you should generally **restore the interrupt flag** with `Thread.currentThread().interrupt()` and then exit or transition according to the cancellation policy.
- Do not just log and continue a long operation as if no signal was received, unless there is a clear reason and contract.
- Do not wrap `InterruptedException` into `UncheckedIOException`: it is the wrong type and misrepresents the error semantics.

### Example 11: Preserving the Interrupt Status

Save as `InterruptContractDemo.java`:

~~~java
public class InterruptContractDemo {
    static void runTask() {
        Thread.currentThread().interrupt();

        try {
            Thread.sleep(1);
            System.out.println("unexpected");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.println("restored="
                    + Thread.currentThread().isInterrupted());
        }
    }

    public static void main(String[] args) {
        runTask();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptContractDemo.java
java InterruptContractDemo
~~~

Output:

~~~text
restored=true
~~~

Because the interrupt flag is set right before calling sleep, the call detects the interruption and throws InterruptedException. In the catch block, the program resets the flag, preserving the signal for outer logic. The demo exits immediately afterward; a real task should have a stop policy, cleanup, and report the cancelled status.

The fact that InterruptException is checked **does not automatically make it recoverable by retrying**. Its contract semantics are usually cooperative task cancellation/stopping.

## 17. Checked Exceptions and Asynchronous APIs

Asynchronous APIs have different exception boundaries than direct calls. For example, `CompletableFuture.supplyAsync` takes a `Supplier<T>` that does not declare checked exceptions. If the task can throw IOException, the lambda typically has to catch and wrap the error as unchecked; the caller observes the failure through `join()` or `get()`.

Notable types to remember:

- `CompletionException`: unchecked wrapper commonly seen when `CompletableFuture.join()` fails.
- `ExecutionException`: checked wrapper commonly seen when calling `Future.get()`.
- `InterruptedException`: can be thrown when the thread waiting on `Future.get()` is interrupted.
- `CancellationException`: unchecked, indicating the task was cancelled in many APIs.
- A checked exception thrown by code inside the task may be **wrapped**, so do not assume the caller of join/get will directly see the exact original exception type.

### Example 12: Cause Chain Through CompletableFuture

Save as `AsyncFailureDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        throw new IOException("storage down");
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

        try {
            System.out.println(future.join());
        } catch (CompletionException ex) {
            System.out.println("outer="
                    + ex.getClass().getSimpleName());
            System.out.println("wrapper="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("root="
                    + ex.getCause().getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncFailureDemo.java
java AsyncFailureDemo
~~~

Output:

~~~text
outer=CompletionException
wrapper=UncheckedIOException
root=storage down
~~~

The calling layer receives a CompletionException and can inspect the cause chain. Do not try to catch IOException around `future.join()` thinking it handles it directly: IOException is checked and join's signature does not declare it.

The example uses a deterministic failing task with no other tasks or result races. In real applications, consider executors, timeouts, cancellation, transaction state, and where errors are logged.

## 18. Exceptions, Transactions, and Data Consistency

Just because a caller “can catch” does not mean it **should continue the transaction**. For example, a multi-step order-saving operation can fail at the last step after some changes have already occurred. In that case:

- Catch the error to **roll back or compensate** before returning a result.
- If integrity cannot be guaranteed, report the ambiguous state and escalate the error to the coordinating layer.
- Avoid automatically retrying a command with side effects if there is no **idempotency key** or deduplication mechanism.
- Do not swallow SQLException and return a fake success; the system may not have saved the data properly.
- If using a transaction framework, understand the framework's **rollback rules**, because checked/unchecked exceptions may be interpreted differently depending on configuration. That is a framework policy, **not a JLS rule**.

A checked exception may need to be propagated up rather than handled at the repository. An unchecked exception may need to be translated into a stable response code at the HTTP boundary. Design decisions should be based not only on what the compiler requires, but also on **state control and post-failure actions**.

## 19. Principles for Protecting Public Contracts When Choosing Error Types

When a public API chooses checked or unchecked, maintain meaningful boundaries for callers:

- **Stable error names and types** help callers decide whether to fix input, fall back, retry, or stop; do not return a generic `RuntimeException("failed")` for every case.
- **Precondition violations** are typically reported with `IllegalArgumentException`, `NullPointerException`, or an appropriate unchecked type. Do not rely on `assert`, which can be disabled, to validate public inputs.
- **Do not leak unintended infrastructure dependencies.** If switching from JDBC to HTTP forces callers to rewrite countless `catch (SQLException)` blocks, the abstraction design may be flawed; translate at the boundary that owns the contract and preserve `cause`.
- **Do not misuse `Error` for business logic**, and do not build deep custom exception hierarchies if the classes do not differ in handling actions.
- **Consider upgrade impact.** Adding/removing checked `throws`, changing exception classes, or switching checked to unchecked can change caller source code or behavior, even when binary linkage still works.
- **Document and test the actual outcomes.** Callers need to know the error types, triggering conditions, state postconditions, and retryability—not just the class name.

The articles on dependency boundaries and compatibility when changing exception contracts examine the last two risks in depth. Here, the criterion for choosing checked/unchecked remains **the caller's reasonable handling capability and responsibility**.

## 20. Anti-Patterns: Three Ways to Make Error Contracts Hard to Use

### A. “Every error is a RuntimeException because it's easier to write”

~~~java
catch (java.io.IOException ex) {
    throw new RuntimeException("failed");
}
~~~

This is **non-standalone, problematic illustrative code**. It both uses an overly generic error type and drops the cause. A caller cannot tell what operation failed and cannot inspect the original IOException via getCause.

Fix according to the layer's contract:

~~~java
catch (java.io.IOException ex) {
    throw new StorageFailure("Cannot load report", ex);
}
~~~

The latter assumes `StorageFailure(String, Throwable)` is declared; it can extend RuntimeException if this layer genuinely wants an unchecked domain failure.

### B. “Every error is checked because it might happen”

Do not declare `throws Exception` on every public method just to “document failure possibilities”. That makes it hard for callers to distinguish input errors, retryable errors, and programmer bugs. Unchecked exceptions still exist outside the throws list.

Publish **the checked types that callers are expected to handle**, and document important unchecked ones if callers need to know about them. Do not try to list every RuntimeException that the JDK might throw.

### C. “Caught means succeeded”

~~~java
try {
    saveOrder();
} catch (Exception ex) {
    System.out.println("cannot save");
}
return true;
~~~

This is **illustrative code with a broken policy**: if saving fails, returning a fake success can cause serious data corruption. Catching does not automatically perform rollback, retry, or create a valid state.

Fix with an **explicit policy**: roll back and return failure, translate the exception with a cause, or use a correctness-preserving fallback; never use logging as a substitute for error handling.

## 21. Decision Process for Checked vs. Unchecked

When designing a public method, you can follow this process:

1. **Identify the operation and target callers.** Who calls the API: an interactive user, an internal service, a callback, a batch job, or an external library?
2. **List the meaningful failure categories.** Input errors, invalid state, unavailable resources, connection failures, timeouts, cancellation, invalid data, internal invariants.
3. **Assign the expected action to each category.** Fix input, retry, fallback, rollback, skip with logging, stop, alert operations, or fix a bug.
4. **Distinguish expected outcomes from exceptional failures.** If “no result” is a normal path, `Optional` or `Result` may fit. If callers must be forced to consider it, a checked exception can help.
5. **Evaluate error semantics.** Misuse/preconditions are usually unchecked; recoverable environment errors are often worth considering as checked.
6. **Check framework/API constraints.** Functional interfaces, reactive/async APIs, interface overrides, and client code affect feasible contracts.
7. **Choose stable names and hierarchy.** Avoid overly broad `Exception` types and overly deep hierarchies with no distinct handling policies.
8. **Design message/cause/metadata.** Provide a `(String, Throwable)` constructor when translating; add error codes or fields when callers need structured handling.
9. **Decide where handling occurs.** What is the receiving layer authorized to do? If it cannot handle the error, propagate it instead of an empty catch.
10. **Consider side effects and retries.** Ensure idempotency, transactions, backoff, cancellation, and resource cleanup where applicable.
11. **Write tests from the caller's perspective.** Test the happy path, each failure type, the cause chain, rollback, retries, and unhandled cases.
12. **Assess compatibility when changing contracts.** For published libraries, adding or removing checked throws is not just an internal change.

### Short Decision Table

| Question | Suggestion |
| --- | --- |
| **Must** the caller have an explicit handling policy? | Consider checked |
| Does the caller have no reasonable recovery at every call site? | Consider unchecked or propagate to a boundary |
| Is the error caused by API misuse / input violating preconditions? | Usually unchecked or validation result |
| Is the error a frequent business outcome? | Consider Result/Optional/status code |
| Does the target API not support checked throws? | Adapter/unchecked with cause or a custom interface |
| Does the service layer need to hide JDBC/file details? | Translate to an appropriate domain exception, preserving cause |
| Did the error occur due to interruption while waiting? | Propagate or restore interrupt, handle cancellation |
| Does the error have partial side effects? | Roll back/compensate before considering recovery |
| Does a public signature change affect many callers? | Check source compatibility and migration path |

## 22. Self-Check Questions

**1.** Does a checked exception mean the caller has already recovered successfully?  
**No.** The compiler only enforces `catch` or `throws`; recovery depends on application logic.

**2.** Can a RuntimeException be caught and handled?  
**Yes.** Unchecked means not required at compile time, not “uncatchable”.

**3.** What type is usually appropriate for passing a negative argument to an API that accepts only positive numbers?  
Unchecked `IllegalArgumentException` or a validation result according to the contract.

**4.** Must IOException always be wrapped in a checked domain exception?  
**No.** Depending on the layer and policy, you can propagate IOException, wrap in a checked domain exception, wrap in an unchecked domain exception, or recover.

**5.** Why is writing only `new RuntimeException(ex.getMessage())` when wrapping an error poor practice?  
Because it loses the cause reference, the original error type, its stack trace, and any accompanying suppressed exceptions.

**6.** If an interface method declares no checked exceptions, can an implementation add `throws IOException`?  
**No**, when IOException is not permitted by the overriding contract.

**7.** Can a public API declare `throws RuntimeException`?  
**Yes**, but the compiler does not force callers to catch or specify it.

**8.** Why can adding a checked exception to a public API break client code?  
Because existing callers that did not previously catch or declare the new exception may fail to compile.

**9.** When a “not found” outcome occurs frequently and is expected, is it mandatory to create an exception?  
**No.** You can choose Optional/Result if it fits the contract.

**10.** Should every IOException be retried?  
**No.** You must evaluate whether it is transient, idempotency, attempt limits, backoff, and cancellation.

**11.** When catching InterruptedException in a Runnable, how do you avoid losing the signal?  
Usually by restoring the flag with `Thread.currentThread().interrupt()` and exiting/cancelling according to policy.

**12.** Will a checked exception from an async task always escape directly from CompletableFuture.join() as the same type?  
**No.** The task may wrap the error, and join typically throws CompletionException; you must inspect the cause chain.

**13.** Does a new wrapper automatically copy suppressed exceptions from its cause?  
**No.** The cause's suppressed exceptions remain on the cause object and can be read via getCause().getSuppressed().

**14.** Is catching Exception and logging it always recovery?  
**No.** That may only be recording it; you still need to decide whether to return failure, retry, roll back, fall back, or propagate the error.

**15.** Why is “all external errors are checked, all code errors are unchecked” not completely accurate?  
Because API policy also depends on recovery authority, caller capability, frameworks, layer boundaries, and contract stability; the same I/O error can appear as both IOException and UncheckedIOException.

## 23. Standard References

- [JLS Java SE 21 — §11.1.1: The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1) — classification of checked and unchecked exceptions.
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2) — catch-or-specify obligation and contract.
- [JLS 21 — §8.4.6: Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6) — throws declarations.
- [JLS 21 — §8.4.8.3: Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3) — limits on checked exceptions when overriding.
- [Oracle Java Tutorials — Unchecked Exceptions: The Controversy](https://docs.oracle.com/javase/tutorial/essential/exceptions/runtime.html) — guidance on choosing by recoverability; tutorial guidance, not a replacement for the JLS.
- [Oracle Java Tutorials — The Catch or Specify Requirement](https://docs.oracle.com/javase/tutorial/essential/exceptions/catchOrDeclare.html).
- [Java SE 21 — Throwable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html) — cause, suppressed, stack trace.
- [Java SE 21 — IOException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/IOException.html).
- [Java SE 21 — UncheckedIOException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/UncheckedIOException.html).
- [Java SE 21 — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

**Remember:** Choosing checked or unchecked is designing an **error-handling contract**. Checked exceptions require callers to consider the failure at compile time; unchecked exceptions do not create that obligation, yet may still require handling at a boundary. Start from what the caller can do on failure, preserve technical causes when translating error types, avoid broad catches or swallowing errors, and test both recovery paths and unrecoverable failure paths.
