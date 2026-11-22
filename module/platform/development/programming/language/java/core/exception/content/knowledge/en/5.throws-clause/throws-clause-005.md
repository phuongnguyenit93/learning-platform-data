# Checked Exception Propagation Across Multiple Call Layers in Java

In Java, a method can call another method, which in turn calls down to a lower layer. If the lower layer raises a **checked exception** without handling it locally, the exception can **propagate back up the call chain**. For the code to compile, every layer that might allow a checked exception to escape must declare the corresponding exception type in its `throws` clause, or use `try-catch` to handle or translate it.

For example, an application reads configuration along the path `Controller → Service → Repository → File API`. `Files.readString(...)` can throw `IOException`. If `Repository`, `Service`, and `Controller` do not handle it, the `IOException` type must appear in the `throws` contract of the involved methods. At a boundary with sufficient context, the program catches the error and decides to return a message, use fallback data, or abort the operation.

**Key takeaway:** `throws` is a **compile-time declaration of the possibility of throwing a checked exception**. It does not throw, catch, log, or fix errors by itself. An exception only actually moves when the program is running and an exception is thrown.

## 1. Recap: What Is a Checked Exception?

Every object that can be thrown with `throw` must be a `Throwable`. Java categorizes exceptions according to compile-time checking rules:

| Class Branch | Checked? | Examples | Caller's Obligation |
| --- | --- | --- | --- |
| `Exception` but not `RuntimeException` | Yes | `IOException`, `SQLException`, `ParseException` | Catch or declare `throws` if the operation can throw them |
| `RuntimeException` and subclasses | No | `IllegalArgumentException`, `NullPointerException` | Not required to `catch` or `throws` |
| `Error` and subclasses | No | `OutOfMemoryError`, `LinkageError` | Not required to `catch` or `throws` |
| `Throwable` itself | Yes | `new Throwable("...")` | Must handle/declare if it can escape |

Because `IOException` is checked, the compiler checks whether the method calling `Files.readString(path)` catches `IOException` or allows it to propagate out. The same rule applies to each call at higher layers. The compiler checks the *types* of exceptions that may be thrown based on code structure; it does not wait for an exception to occur at runtime.

Some APIs declare multiple checked types, such as `IOException` and a library-defined business exception. When those types can escape a method, `throws` must cover all of them with appropriate types or a valid supertype. `throws Exception` syntactically covers a very broad range, but it usually makes the API contract harder to use than `throws IOException` or a specific type.

## 2. Multi-Layer Call Chain and Propagation Direction

The diagram below illustrates the **method call direction** and the **exception propagation direction**:

```text
Downward on call:
main() ──► controller() ──► service() ──► repository() ──► readFile()
                                                        │
                                                        │ throw IOException
                                                        ▼
Upward on error:
main() ◄── controller() ◄── service() ◄── repository() ◄─┘
  │
  └── catch IOException or continue declaring throws
```

When `readFile()` throws `IOException`:

1. Code after the throw point on the normal execution path of `readFile()` does not run.
2. If `readFile()` does not catch the error, the call inside `repository()` completes abruptly.
3. If `repository()` does not catch it, the error continues up to `service()`; the same happens for `controller()`.
4. When the first compatible `catch` is encountered while unwinding the call stack, the program executes that handler block. Applicable `finally` blocks are executed according to Java rules during exception propagation.
5. If no one catches it, the exception can escape the thread's entry point and be handled as an uncaught exception.

**Separate the two questions.** The compiler asks: "Which checked exception types *might* exit this method?" The runtime asks: "An exception object *was actually* thrown, and where is it currently handled?" Declaring `throws` satisfies the compile-time obligation; unwinding up the stack happens at runtime.

## 3. Java 17+ Example: Propagating Through Four Layers and Catching at the Boundary

Save as `CheckedPropagationDemo.java`:

```java
import java.io.IOException;

public class CheckedPropagationDemo {
    static String readFile() throws IOException {
        throw new IOException("config missing");
    }

    static String repository() throws IOException {
        return readFile();
    }

    static String service() throws IOException {
        return repository();
    }

    static String controller() throws IOException {
        return service();
    }

    public static void main(String[] args) {
        try {
            System.out.println(controller());
        } catch (IOException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("handled at main");
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 CheckedPropagationDemo.java
java CheckedPropagationDemo
```

Exact output:

```text
type=IOException
message=config missing
handled at main
```

In this example:

- `readFile()` is where `IOException` is created and thrown.
- `repository()`, `service()`, and `controller()` have no `catch`; each method declares `throws IOException` to allow the error to pass through.
- `main()` catches and handles it with `catch (IOException ex)`, so it does not need `throws IOException`.
- The statement `System.out.println(controller())` cannot print a successful result in this run: the call `controller()` throws an exception before producing a value as an argument for `println`.
- **The same exception object** can propagate through multiple layers if not replaced. Each `throws` does not create a new exception.

To avoid depending on the filesystem or external data, the example intentionally throws `IOException` directly at the lower layer. In a real application, `readFile()` typically calls `Files.readString(path)` and lets that API's exception propagate out.

## 4. Why Must Every Layer Still Declare `throws`?

Consider an incorrect version:

```java
import java.io.IOException;

class MissingThrowsExample {
    static String storage() throws IOException {
        throw new IOException("failed");
    }

    static String service() {
        return storage(); // compile error: unreported exception IOException
    }
}
```

This example **intentionally does not compile**. Because `storage()` is declared as potentially throwing `IOException`, `service()` must either catch it or declare `throws IOException`.

The fix that allows propagation:

```java
static String service() throws IOException {
    return storage();
}
```

The snippet above is a fix **inside the `MissingThrowsExample` class**, replacing the old `service()` method. Another fix is wrapping the call in `try-catch` if `service()` has an appropriate handling rule.

If `service()` is fixed to use `throws IOException`, code calling `service()` at a higher layer must also satisfy the same requirement. This is the **checked exception obligation chain**, extending until a layer handles it or an entry point continues declaring the error.

A method can declare `throws IOException` even if on its current execution path it does not actually throw the exception. The declaration describes a contractual possibility, not a requirement that the method throw an error on every call. Nor does the compiler infer that a method named `loadSafely` is guaranteed to be safe; it checks the signature and the code's exception analysis rules.

## 5. Three Practical Options at Each Layer

| Option | When to Use | Consequence for the Calling Layer |
| --- | --- | --- |
| **Propagate the original exception** using `throws IOException` | The current layer lacks enough context to resolve it; the error type remains meaningful | The upper layer must handle/declare the checked exception |
| **Catch and handle** using `catch` | There is a reliable recovery rule: fallback data, bounded retry, clear result message | If handled completely and no new checked exception is thrown, the obligation for that exception ends |
| **Translate the exception** using `throw new DomainException("...", cause)` | The layer boundary needs its own contract; you do not want the business API to depend directly on infrastructure errors | The upper layer handles/declares the **new type** if it is checked |

A layer should not automatically "catch everything" just to avoid writing `throws`. If recovery is not possible, catching and returning fake success data can mask data corruption or cause upper layers to make wrong decisions.

Conversely, **not every layer has to propagate**. Once a layer has an appropriate way to handle it, the chain can end there.

## 6. Java 17+ Example: One Layer Handling with a Fallback Value

Save as `HandledAtServiceDemo.java`:

```java
import java.io.IOException;

public class HandledAtServiceDemo {
    static String storage(boolean available) throws IOException {
        if (!available) {
            throw new IOException("storage unavailable");
        }
        return "live-config";
    }

    static String repository(boolean available) throws IOException {
        return storage(available);
    }

    static String service(boolean available) {
        try {
            return repository(available);
        } catch (IOException ex) {
            System.out.println("fallback because: " + ex.getMessage());
            return "default-config";
        }
    }

    static void controller(boolean available) {
        System.out.println("config=" + service(available));
    }

    public static void main(String[] args) {
        controller(false);
        controller(true);
    }
}
```

```bash
javac -encoding UTF-8 HandledAtServiceDemo.java
java HandledAtServiceDemo
```

Output:

```text
fallback because: storage unavailable
config=default-config
config=live-config
```

In `service()`, the `IOException` is handled with an **intentional** fallback. Because `catch` returns the default configuration and throws no new checked exception, `service()` does not need `throws IOException`. Consequently, `controller()` does not need to declare this error either. The code only illustrates the mechanism; in a real system, you must determine whether the fallback is safe, permitted by business rules, and whether it loses diagnostic information.

Key point: **successfully handling an exception at a lower layer stops propagation at that layer**. No exception object is forwarded to `controller()` from this failed call.

## 7. Translating Checked Exceptions Between Layers and Preserving the Cause

In a multi-layer system, the API layer should not always know about `IOException`, `SQLException`, or specific error types from infrastructure libraries. A service layer can transform them into an exception matching business semantics.

Save as `ExceptionTranslationDemo.java`:

```java
import java.io.IOException;

public class ExceptionTranslationDemo {
    static class ConfigLoadException extends Exception {
        ConfigLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String storage() throws IOException {
        throw new IOException("disk read failed");
    }

    static String repository() throws IOException {
        return storage();
    }

    static String service() throws ConfigLoadException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ConfigLoadException("cannot load configuration", ex);
        }
    }

    static void controller() {
        try {
            System.out.println(service());
        } catch (ConfigLoadException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage=" + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        controller();
    }
}
```

```bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
```

Output:

```text
type=ConfigLoadException
message=cannot load configuration
causeType=IOException
causeMessage=disk read failed
```

This is an example of **exception contract translation**:

1. `storage()` and `repository()` use the I/O layer's checked `IOException` type.
2. `service()` catches `IOException` and **creates a new object** `ConfigLoadException`, which is also checked because it extends `Exception` rather than `RuntimeException`.
3. `service()` declares `throws ConfigLoadException`; the upper layer only needs to know the new contract.
4. `controller()` catches `ConfigLoadException` and can still trace the original cause via `getCause()`.

**Do not write** `throw new ConfigLoadException(ex.getMessage(), null);` or only create `new Exception(ex.getMessage())` if the goal is to add context while preserving the root cause. Pass the `ex` object as the `cause`. When logging, avoid logging the exact same stack trace repeatedly at every layer.

For business exception classes, choose checked or unchecked depending on the contract: an error that can be handled meaningfully is often suited to checked; invariant violations, invalid arguments, or programming errors typically use unchecked. There is no rule that every `IOException` must be wrapped into a `RuntimeException`.

## 8. Declaring Multiple Checked Exception Types and Superclass Relationships

A method can throw multiple independent checked types:

```java
import java.io.IOException;
import java.text.ParseException;

class MultipleCheckedExample {
    static String readAndParse(int mode) throws IOException, ParseException {
        if (mode == 1) {
            throw new IOException("I/O failed");
        }
        if (mode == 2) {
            throw new ParseException("Invalid format", 0);
        }
        return "OK";
    }

    static String service(int mode) throws IOException, ParseException {
        return readAndParse(mode);
    }
}
```

This snippet compiles (though it has no `main` to run standalone). `IOException` and `ParseException` are two distinct checked types. Because `service()` does not catch them, it must declare both types or an appropriate supertype like `Exception`; declaring specific types tells callers which cases need handling.

In a `catch`, you can use multi-catch if the types do not have a superclass/subclass relationship with each other:

```java
try {
    MultipleCheckedExample.service(1);
} catch (IOException | ParseException ex) {
    System.out.println("failed: " + ex.getMessage());
}
```

This is an illustrative snippet inside a method that has access to `MultipleCheckedExample`. If you catch the supertype `Exception` instead, multiple error types get lumped together, sometimes losing distinct handling decisions.

**Inheritance relationships determine `throws` coverage:** if a child method can throw `FileNotFoundException`, `throws IOException` is sufficient because `FileNotFoundException extends IOException`. There is no need to write both `throws FileNotFoundException, IOException` unless you want to document it explicitly for readers; under compilation rules, the latter already covers the former.

Similarly, `throws Exception` covers every checked exception under the `Exception` branch, though it does not cover a direct checked `Throwable` that is not an `Exception`. `throws Throwable` is too broad for ordinary APIs because it also includes `Error`-branch errors in the contract.

## 9. `throws` on Methods and Constructors: Design Boundaries

`throws` is permitted in both method and constructor declarations:

```java
import java.io.IOException;

class ResourceHolder {
    ResourceHolder(String location) throws IOException {
        if (location == null || location.isBlank()) {
            throw new IOException("location missing");
        }
    }
}
```

If you call `new ResourceHolder("")`, the compiler requires the caller to `catch` or declare `throws IOException`. The obligation is identical to a method call. This snippet illustrates a valid class without `main`.

### Remember the Method Overriding Rule

When overriding a method, the overriding version **must not declare additional or broader checked exceptions** beyond what the parent method's contract allows. It may declare fewer or compatible subtypes.

Valid example:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface ConfigSource {
    String load() throws IOException;
}

class FileSource implements ConfigSource {
    @Override
    public String load() throws FileNotFoundException {
        throw new FileNotFoundException("missing");
    }
}

class InMemorySource implements ConfigSource {
    @Override
    public String load() {
        return "local";
    }
}
```

`FileNotFoundException` is a subclass of `IOException`, so it is valid. `InMemorySource` declaring no checked exceptions is also valid. However, if an implementation tries to declare `throws Exception`, it broadens the checked exception contract compared to `IOException` and is rejected at compile time.

When a variable is declared with type `ConfigSource`, calling `source.load()` must still obey the interface's `throws IOException` contract at compile time, even if the actual object is an `InMemorySource` that throws no checked exceptions.

**Note:** Overriding cannot add new checked exceptions; it can still throw unchecked exceptions. What the compiler checks is part of the type contract, not a guarantee that runtime code is completely error-free.

## 10. Where Can `throws` on `main` Send an Exception?

Java allows declaring:

```java
import java.io.IOException;

class MainThrowsExample {
    public static void main(String[] args) throws IOException {
        perform();
    }

    static void perform() throws IOException {
        throw new IOException("operation failed");
    }
}
```

This program **compiles**, but when run, the exception escapes `main` and is handled as an uncaught exception of the startup thread. The JVM/JDK typically prints error details and a stack trace; exact lines and paths depend on the environment, so stdout does not need to be fixed.

Declaring `throws IOException` on `main` solves the compilation issue; **it does not mean the failure is handled**. In a command-line tool, you may intentionally let an error terminate the program; in a service, API, or background job, the boundary usually needs proper logging, response, and cleanup rules.

Because an exception does not automatically retry the failed method, do not think of `throws` as "handing the work off to the JVM and then continuing normally." Without a compatible `catch`, the execution path of that call terminates abruptly.

## 11. `try-with-resources` and Errors Occurring at Multiple Steps

In I/O applications, a method can fail during business logic **and** when closing a resource. `try-with-resources` manages closing `AutoCloseable` objects in the reverse order of their initialization. If the `try` body throws an exception and `close()` also throws an exception, the close error is typically stored in `getSuppressed()` on the primary exception.

Save as `SuppressedPropagationDemo.java`:

```java
import java.io.IOException;

public class SuppressedPropagationDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void storage() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws IOException {
        storage();
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedPropagationDemo.java
java SuppressedPropagationDemo
```

Output:

```text
primary=read failed
suppressedCount=1
suppressed=close failed
```

`IOException("read failed")` propagates from `storage()` to `service()` and then `main()`, just like a normal checked exception. `IOException("close failed")` **does not replace the primary error**, but is attached to `getSuppressed()`. That allows full tracing instead of losing the error from the read operation.

If only closing the resource fails and there is no error in the `try` body, the close error becomes the primary exception. `try-with-resources` does not exempt you from declaring checked exceptions thrown by closing; the compiler still checks checked types that automatic resource closing can throw.

## 12. Do Not Equate `throws` with Asynchronous Execution and Lambdas

When using callbacks, lambdas, or executors, checked exceptions must still conform to the functional interface's signature. For example, `Supplier<T>.get()` **does not declare any checked exceptions**. Therefore, the following snippet **intentionally does not compile**:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;

class InvalidSupplierExample {
    static String read() throws IOException {
        throw new IOException("read failed");
    }

    static void submit() {
        CompletableFuture.supplyAsync(() -> read());
        // Error: Supplier lambda cannot let checked IOException escape.
    }
}
```

Calling an API with `Async` in its name does not bypass checked exception rules. If you actually want to pass the error through `CompletableFuture`, you need to design an appropriate error result or wrap the cause in an unchecked wrapper according to the API contract. When `join()` observes an abnormally completed task, a `CompletionException` may appear with the original cause. This is the concurrency library's failure-propagation mechanism; having `throws IOException` does not automatically transfer the error to the calling thread.

The synchronous examples earlier in this article clearly illustrate `throws` through direct call chains; the async behavior is simply a point to keep in mind if the design is extended.

## 13. `InterruptedException` Is a Checked Exception Requiring Its Own Policy

An important checked exception example in multithreaded programs is `InterruptedException`, commonly raised by blocking/waiting operations such as `Thread.sleep(...)`. An upper layer can let it propagate:

```java
static void waitForWork() throws InterruptedException {
    Thread.sleep(100);
}

static void service() throws InterruptedException {
    waitForWork();
}
```

If this layer is not allowed to add `InterruptedException` due to its API contract, catching it usually requires **restoring the interrupt flag** and then terminating/canceling the operation according to policy:

```java
static void serviceWithoutCheckedThrows() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Both snippets are illustrative methods within a class. Calling `interrupt()` informs the calling layer that the thread has a cancellation request; in real applications, avoid continuing work as if nothing happened. Do not adopt "swallow the exception and continue" as a general rule for `InterruptedException`.

## 14. Common Mistakes When Propagating Checked Exceptions Across Layers

| Mistake | Problem | How to Fix |
| --- | --- | --- |
| Declaring `throws IOException` only at the lower layer and forgetting the next calling layer. | Compiler reports `unreported exception ... must be caught or declared`. | Add `throws` at the layer that needs to propagate it, or handle it at that layer. |
| Thinking `throws` catches and handles the error automatically. | The exception still propagates when an actual `throw` happens at runtime. | Place `catch` at a boundary with enough information to handle it. |
| Wrapping every method in `catch (Exception ex) { }`. | Swallows errors and loses the cause; upper layers may mistake it for success. | Only catch types you can handle; propagate or translate errors if needed. |
| Having every layer `catch`, log, and then `throw ex;`. | Duplicate logs and scattered logging responsibility; verbose code that adds no value. | Choose one appropriate layer to log/surface the error; only catch when adding context or recovering. |
| Converting an exception to `new RuntimeException(ex.getMessage())`. | Loses the `cause` and original stack trace chain. | Use `new RuntimeException("context", ex)` when the contract chooses unchecked. |
| Declaring `throws Exception` or `throws Throwable` at every layer. | Imprecise contract, making it hard to distinguish error categories. | Use a specific checked type or a domain-specific business exception. |
| Adding a new checked exception to an overriding method even though the interface does not allow it. | Violates overriding rules. | Design the interface upfront or use an appropriate exception translation rule. |
| Returning a default value even when data is severely corrupted. | Masks the failure and can lead to inconsistent state. | Only use a fallback with a valid business basis; otherwise propagate the error. |
| Ignoring `getSuppressed()` when resource closing fails. | Missing secondary information that could help investigation. | Use `try-with-resources`, and record both the primary and suppressed exceptions when needed. |

## 15. How to Read and Design a Module's Exception Contract

For each layer, answer the following:

1. **Exception source:** Which method raises it? Is it checked or unchecked? What does the API's `throws` declare?
2. **Layer's role:** Does this layer have enough information to recover? For example, if reading configuration fails, is there an approved default dataset?
3. **Decision:** Catch and handle, propagate the original type via `throws`, or translate into a checked exception appropriate for the boundary?
4. **Contract with callers:** Does the signature accurately advertise the checked exception types that may escape? If overriding or implementing an interface, does it violate any bounds?
5. **Diagnostic information:** When wrapping an exception, is `cause` preserved? When closing resources, are `suppressed` exceptions preserved?
6. **Termination point:** Which layer turns the error into a message, typed result, API response, or task termination decision? Do not let different layers make conflicting decisions.

A reasonable design diagram, when each layer has a distinct role:

```text
Repository: throws IOException
        |
        v
Service: catches IOException
         throws ConfigLoadException (cause = IOException)
        |
        v
Controller: catches ConfigLoadException
            -> build appropriate response
```

This diagram is not a template for every project. If a service API is inherently a pure I/O API and `IOException` is meaningful to callers, propagating the original type is fine. If the service layer can recover safely, it can terminate the exception chain itself. Base the decision on the contract and handling capability, not on trying to write fewer `throws` clauses at all costs.

## 16. Self-Check Questions

**Question 1.** `repository() throws IOException` is called inside `service()`. If `service()` does not catch the error, must it declare `throws IOException`?  
**Yes.** If the checked exception can escape `service()`, the compiler requires declaring that type or an appropriate supertype.

**Question 2.** Does `throws IOException` create an `IOException` object at each layer?  
**No.** It only declares the contract. Without catching/wrapping, the original exception object can propagate across multiple calls.

**Question 3.** If `service()` catches `IOException` and returns a valid fallback, is `controller()` required to declare `throws IOException` just because `IOException` existed at a lower layer?  
**No.** If the error is completely handled and there is no path for that checked exception to escape `service()`, the upper layer has no such obligation.

**Question 4.** If `service()` catches `IOException` and throws `ConfigLoadException extends Exception`, what contract must the calling layer follow?  
**`ConfigLoadException`.** This is the new checked exception; preserve the old `IOException` via `getCause()` so context is not lost.

**Question 5.** Does declaring `throws IOException` cover `FileNotFoundException`?  
**Yes.** Because `FileNotFoundException` is a subclass of `IOException`.

**Question 6.** Can an implementation add `throws Exception` when the interface method only declares `throws IOException`?  
**No.** An overriding method must not broaden the checked exceptions permitted by the parent method.

**Question 7.** If `main() throws IOException`, has the program caught the error?  
**Not yet.** This is still a propagation declaration. If the error actually escapes `main` without a compatible handler, it is an uncaught exception.

**Question 8.** Can a `Supplier<String>` lambda throw a checked `IOException` just because it is passed to `CompletableFuture.supplyAsync`?  
**No.** `Supplier.get()` does not declare checked exceptions; you must design an appropriate wrapping or result-transfer mechanism.

## Standard References

- [JLS Java SE 21 — §11.1.1 The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).
- [JLS Java SE 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [JLS Java SE 21 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).
- [JLS Java SE 21 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6).
- [JLS Java SE 21 — §8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).
- [JLS Java SE 21 — §14.20 The `try` statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).

**Remember:** `throws` lets a layer **advertise** a checked exception type that it has not handled, and upper layers continue to bear responsibility for catching or declaring it. The propagation chain only stops when there is appropriate handling or when the exception exits the entry point. When translating errors at a layer boundary, preserve the `cause` and declare the new checked exception properly.
