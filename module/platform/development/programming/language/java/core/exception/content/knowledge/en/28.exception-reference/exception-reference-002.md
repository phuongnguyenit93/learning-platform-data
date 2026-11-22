# Checked, Unchecked, Exception, and Error Reference Table in Java

## 1. Purpose of This Reference Table

Java uses the `Throwable` type system to represent situations that interrupt the normal flow of execution. When reading a signature like `void read() throws IOException`, seeing a `NullPointerException` in logs, or encountering `NoClassDefFoundError` at startup, you need to distinguish two questions:

1. **Where does that type sit in the inheritance hierarchy?** `Throwable`, `Exception`, `RuntimeException`, or `Error`?
2. **Does the compiler require the caller to catch or declare it?** This is the boundary between **checked** and **unchecked**.

The table below targets Java 17+ and covers the hierarchy, common exceptions, `try/catch/throws` rules, compilable/runnable examples, concurrency/asynchronous cases, and API design principles. It is a **reference and explanatory** document, not advice to “catch all errors” or force every method to throw checked exceptions.

### 1.1. Three Concepts to Distinguish Immediately

- **`Exception` is a class in Java**, not synonymous with everything that can be thrown via `throw`. `Error` does not extend `Exception`.
- **Checked/unchecked is a static checking rule of the compiler**, not a definitive measure of severity, recoverability, or error origin.
- **`RuntimeException` belongs to `Exception` but is unchecked**; this is the detail beginners most commonly confuse.

In Java, `Throwable` is the common superclass of two main branches: `Exception` and `Error`. Under the language's checked-exception classification, a `Throwable` type is **unchecked** if it is `RuntimeException`, `Error`, or one of their subclasses; all other `Throwable` types are **checked**. Therefore, `Exception` itself is checked, whereas `RuntimeException`, despite being a subclass of `Exception`, is unchecked.

## 2. Overview Hierarchy

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable                     checked
          |
          +-- java.lang.Exception                checked
          |     |
          |     +-- IOException                  checked
          |     |     +-- FileNotFoundException
          |     |     +-- ...
          |     +-- SQLException                  checked
          |     +-- ParseException                checked
          |     +-- InterruptedException          checked
          |     +-- ClassNotFoundException        checked
          |     +-- ExecutionException            checked
          |     +-- TimeoutException              checked
          |     |
          |     +-- RuntimeException              UNCHECKED
          |           |
          |           +-- IllegalArgumentException
          |           |     +-- NumberFormatException
          |           +-- IllegalStateException
          |           +-- NullPointerException
          |           +-- IndexOutOfBoundsException
          |           +-- ArithmeticException
          |           +-- CompletionException
          |           +-- CancellationException
          |           +-- UncheckedIOException
          |           +-- ...
          |
          +-- java.lang.Error                     UNCHECKED
                |
                +-- AssertionError
                +-- VirtualMachineError
                |     +-- OutOfMemoryError
                |     +-- StackOverflowError
                +-- LinkageError
                |     +-- NoClassDefFoundError
                |     +-- NoSuchMethodError
                |     +-- ExceptionInInitializerError
                +-- ...
~~~

The tree is **abbreviated** for easy reference and does not list every JDK class. Names without packages in the tree belong to different packages; for example, `IOException` is in `java.io`, `SQLException` is in `java.sql`, and `ExecutionException` and `TimeoutException` are in `java.util.concurrent`.

A user-defined class can also extend `Throwable` directly. In that case, it is still **checked**, provided it does not sit under `RuntimeException` or `Error`. However, in typical application APIs, you should extend `Exception` or `RuntimeException` according to the intended semantics rather than extending `Throwable` directly.

## 3. Main Table: Checked, Unchecked, Exception, and Error

| Concept | Inheritance Relationship | Compiler requires catch/declare? | Common Meaning |
| --- | --- | --- | --- |
| `Throwable` | Superclass of `Exception` and `Error` | **Yes**, when directly throwing a `Throwable` not in the unchecked branch | Base type representing anything that can be thrown |
| `Exception` | `extends Throwable` | **Yes**, for `Exception` itself and its checked subclasses | Errors/conditions that should propagate through APIs by policy |
| Checked exception | `Throwable` excluding `RuntimeException`/`Error` branches | **Yes**, when it can escape the code and is subject to compile-time checking | Many I/O, parsing, and coordination errors |
| `RuntimeException` | `extends Exception` | **No** | Invalid argument/state, programming bugs, or runtime conditions per API design |
| Unchecked exception | `RuntimeException` or `Error` and their subclasses | **No** | Errors/conditions not requiring mandatory declaration |
| `Error` | `extends Throwable`, does **not** extend `Exception` | **No** | JVM/linkage errors, assertions, or other serious conditions |

**Quick mnemonic:** `Exception` does not mean “checked”, because `RuntimeException` is an `Exception` yet unchecked. Conversely, not every `Throwable` is an `Exception`, because `Error` is an independent branch.

### 3.1. Type Classification Formula

For a type `T` extending `Throwable`:

~~~text
If T extends RuntimeException   -> unchecked
If T extends Error              -> unchecked
If T extends Throwable but
  not in the two branches above -> checked
~~~

The word “`extends`” is used here in the sense of a **transitive inheritance subtype relationship**, not necessarily a direct declaration in source code. For instance, `NumberFormatException` extends `IllegalArgumentException` extends `RuntimeException`, so it is unchecked. `NoClassDefFoundError` sits under `LinkageError` extends `Error`, so it is unchecked.

### 3.2. Checked Does Not Mean Minor, Unchecked Does Not Mean Fatal

An `IOException` caused by an unwritable filesystem can fail a critical operation. An `IllegalArgumentException` can be an easily recoverable validation condition. An `AssertionError` is sometimes a failed assertion in a test and does not necessarily cause the JVM to exit immediately every time.

Therefore, choose how to handle errors based on the **contract and system state**, not solely on checked/unchecked:
- Is genuine recovery actually possible?
- Have any side effects already occurred before the error was thrown?
- Does the caller have enough information and authority to retry?
- Is a shutdown/restart or data reconciliation required?
- Can invariants still be guaranteed after catching?

## 4. Common Checked Exceptions Table

| Type | Package / Common Source | When Encountered | Key Points to Remember |
| --- | --- | --- | --- |
| `IOException` | `java.io` | File/stream/I/O reading/writing | Checked; many subtypes |
| `FileNotFoundException` | `java.io` | Opening a file that is not found/cannot be opened per API | Subclass of IOException |
| `NoSuchFileException` | `java.nio.file` | Path does not exist in NIO | Checked subclass of IOException via FileSystemException |
| `EOFException` | `java.io` | Unexpected end of data in certain stream APIs | Checked |
| `SQLException` | `java.sql` | JDBC/SQL/driver/database error | Checked; transaction state must be inspected separately |
| `SQLTimeoutException` | `java.sql` | JDBC operation timeout per driver | Checked; does not automatically roll back all side effects |
| `ParseException` | `java.text` | Parsing date/text strings in related APIs | Checked |
| `URISyntaxException` | `java.net` | Malformed URI string per `new URI(String)` | Checked |
| `ClassNotFoundException` | `java.lang` | API loading a class by name cannot find the class | Checked |
| `InterruptedException` | `java.lang` | Waiting thread is interrupted at a supporting API | Checked; preserve/propagate the interruption request |
| `ExecutionException` | `java.util.concurrent` | `Future.get()` observes a failed task | Checked; underlying cause is in `getCause()` |
| `TimeoutException` | `java.util.concurrent` | `Future.get(timeout)` wait expires | Checked; does not automatically cancel the task |
| `ReflectiveOperationException` | `java.lang` | Certain reflection operations | Checked |
| `GeneralSecurityException` | `java.security` | Certain cryptography/certificate APIs | Checked |
| `CloneNotSupportedException` | `java.lang` | `Object.clone()` call is not supported | Checked |

This table does not mean every I/O operation throws `IOException` or every timeout is `TimeoutException`. **The exception type depends on the specific API**: HTTP clients, JDBC, CompletableFuture, sockets, and libraries may use different types.

### 4.1. Can Checked Exceptions Exist Outside `Exception`?

Yes: a direct subclass of `Throwable` that is **not** under `RuntimeException`/`Error` is also checked. For example:

~~~java
class DirectThrowable extends Throwable {
    DirectThrowable(String message) {
        super(message);
    }
}
~~~

This is a class fragment that can be placed in an appropriate Java source file. A method that throws `new DirectThrowable("...")` normally must catch it or declare `throws DirectThrowable`.

However, **you should not design business exceptions by extending Throwable directly** without a special reason: most application code that catches `Exception` will fail to catch it, causing confusing behavior. In practice, `extends Exception` is typically used for checked domain failures or `extends RuntimeException` for unchecked domain failures according to the contract.

## 5. Common Unchecked `RuntimeException` Table

| Type | Typical Scenario | Investigation / Design Approach |
| --- | --- | --- |
| `IllegalArgumentException` | Argument violates a precondition | Check input contract/validation |
| `NumberFormatException` | Failed to parse a number with `Integer.parseInt` and similar APIs | Subclass of IllegalArgumentException |
| `IllegalStateException` | Object or system is not in a permitted state | Check state transitions and preconditions |
| `NullPointerException` | Accessing through null or API requires non-null | Check the null source and line context |
| `IndexOutOfBoundsException` | Index out of collection/array bounds per API | Check size/index |
| `ArrayIndexOutOfBoundsException` | Invalid index in an array | Subclass of IndexOutOfBoundsException |
| `ArithmeticException` | E.g., integer division by zero | Not all floating-point operations behave the same way |
| `ClassCastException` | Incompatible runtime cast | Check types and classloaders |
| `UnsupportedOperationException` | Operation is not supported, e.g., immutable collection | Read the object's contract |
| `ConcurrentModificationException` | Some iterators detect invalid collection modification per contract | Fail-fast is usually best-effort; do not use as a synchronization mechanism |
| `IllegalMonitorStateException` | `wait/notify` or monitor operation with wrong ownership | Check synchronized/lock usage |
| `SecurityException` | API denies action due to the corresponding security mechanism | May be due to policy/config, not just a bug |
| `CompletionException` | CompletionStage/`CompletableFuture.join()` reports source failure | Read `getCause()` |
| `CancellationException` | `Future.get()`/`join()` on a canceled future | Cancellation does not mean the underlying work has stopped |
| `UncheckedIOException` | Unchecked wrapper holding an IOException | Read `getCause()` |
| `DateTimeException` | `java.time` API rejects date/time data | Unchecked in `java.time` |

**`RuntimeException` does not mean “an error automatically generated by the JVM”.** Developers can explicitly `throw new IllegalArgumentException(...)`, frameworks can throw their own unchecked exceptions, and a `RuntimeException` can represent a wrapped infrastructure error. You must inspect the specific type, cause, and contract.

### 5.1. When to Use Application-Defined `RuntimeException`?

For example, when a service invariant is violated:

~~~java
if (amount.signum() < 0) {
    throw new IllegalArgumentException("amount must be non-negative");
}
~~~

This is a fragment assuming `amount` is a `BigDecimal`. Using unchecked exceptions keeps API signatures concise when preconditions are documented, but it does not waive the responsibility to validate data from untrusted sources. If a situation is an expected business outcome (such as quota rejection), an application may choose a result type or a domain exception by convention.

Do not overuse generic `RuntimeException` with vague messages across every layer; custom subtypes or stable error codes can help callers classify failures.

## 6. Common `Error` Table

| Type | Branch | Common Cause / Message | Handling Direction |
| --- | --- | --- | --- |
| `AssertionError` | `Error` | Failed assertion or explicitly thrown by code | Fix invariant/test or assert condition |
| `OutOfMemoryError` | `VirtualMachineError` | JVM cannot allocate enough memory resources for an operation | Investigate heap/native resources, load, and environment; do not assume catching is safe |
| `StackOverflowError` | `VirtualMachineError` | Call stack exceeds capacity | Find abnormal recursion/call cycles |
| `NoClassDefFoundError` | `LinkageError` | Cannot define/find a required class during linking or previous class init failed | Check dependencies/classpath/cause/init |
| `NoSuchMethodError` | `IncompatibleClassChangeError` under `LinkageError` | Caller binary references a method missing from the runtime binary | Check library versions/descriptors |
| `NoSuchFieldError` | `IncompatibleClassChangeError` | Runtime class lacks a field referenced by bytecode | Check ABI/JAR/runtime |
| `UnsupportedClassVersionError` | `ClassFormatError` under `LinkageError` | Class file version is not supported by the runtime | Compare compiler target and runtime JDK |
| `ExceptionInInitializerError` | `LinkageError` | Static initializer threw an unhandled exception | Inspect `<clinit>` and `getCause()` |
| `LinkageError` | `Error` | Binary linking/loading issue | Verify artifacts, dependencies/modules/classloaders |
| `InternalError` | `VirtualMachineError` | Internal JVM error condition | Collect runtime/JDK evidence; avoid continuing blindly |

**`Error` is not “a more severe checked Exception”.** It is a separate branch under `Throwable` and is unchecked. `Error`s related to the JVM, resources, or linkage are generally not appropriate to catch and continue as if they were ordinary business errors.

### 6.1. `AssertionError` Is a Case Worth Understanding Properly

`AssertionError` can be generated by the `assert` statement when assertions are enabled, or created by code/test frameworks. By default, Java usually **does not enable assertions** when running without `-ea`; do not build security logic or mandatory validation solely using `assert`.

~~~java
assert amount >= 0 : "amount must be non-negative";
~~~

This is a fragment with an already-declared `amount` variable. When assertions are enabled and the condition is false, `AssertionError` may occur; when assertions are disabled, the assert expression has no effect as regular validation. Use explicit parameter checks/exceptions for invariants that must always be enforced.

### 6.2. Does Every `Error` Immediately Terminate the JVM?

There is no absolute rule like that. `AssertionError` can be caught by a test framework to report a test failure; one thread may terminate due to an uncaught `Error` while other threads keep running. However, **you should not rely on catching `Error` to continue safely** after `OutOfMemoryError` or other serious errors: JVM/resource state may no longer satisfy assumptions.

Handling severe errors belongs to runtime supervision, restarts, telemetry, and system recovery strategies. A `catch (Throwable t) { return defaultValue; }` block in the business layer often breaks visibility into dangerous conditions.

## 7. Java 17 Program Classifying `Throwable` — Compilable and Runnable

The following program intentionally creates objects from the four groups to check inheritance relationships using `instanceof`. It also demonstrates catching a checked `IOException` and an unchecked `IllegalArgumentException`.

Save as **`ThrowableClassificationDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableClassificationDemo {
    static class CustomChecked extends Exception {}
    static class CustomUnchecked extends RuntimeException {}

    static String classify(Throwable t) {
        if (t instanceof Error) return "unchecked Error";
        if (t instanceof RuntimeException) return "unchecked RuntimeException";
        if (t instanceof Exception) return "checked Exception";
        return "checked Throwable";
    }

    static void read() throws IOException {
        throw new IOException("io problem");
    }

    static void validate(int x) {
        if (x < 0) throw new IllegalArgumentException("negative");
    }

    public static void main(String[] args) {
        Throwable[] samples = {
            new IOException(),
            new CustomChecked(),
            new IllegalArgumentException(),
            new CustomUnchecked(),
            new AssertionError(),
            new Throwable()
        };

        for (Throwable t : samples) {
            System.out.println(t.getClass().getSimpleName()
                    + " -> " + classify(t));
        }

        try {
            read();
        } catch (IOException e) {
            System.out.println("caught checked: " + e.getMessage());
        }

        try {
            validate(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("caught unchecked: " + e.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 ThrowableClassificationDemo.java
java ThrowableClassificationDemo
~~~

**Verified stdout when running the program:**

~~~text
IOException -> checked Exception
CustomChecked -> checked Exception
IllegalArgumentException -> unchecked RuntimeException
CustomUnchecked -> unchecked RuntimeException
AssertionError -> unchecked Error
Throwable -> checked Throwable
caught checked: io problem
caught unchecked: negative
~~~

### 7.1. Why Does the Program Classify Correctly?

The order of branches in `classify` is intentional:
1. `Error` first: belongs to the Error branch, not Exception.
2. `RuntimeException` next: is an `Exception` subclass but must be labeled **unchecked**.
3. Remaining `Exception`: checked.
4. Remaining `Throwable`: in the example, a direct `new Throwable()`, checked.

If you swap `if (t instanceof Exception)` and `if (t instanceof RuntimeException)`, every RuntimeException would be misclassified as a checked Exception, because `RuntimeException extends Exception`. This is a common classification logic bug when writing a throwable summary report.

The program creates `AssertionError` as an **object for classification**, without throwing it. This illustrates the inheritance tree without encouraging catching `Error` for business recovery.

### 7.2. What This Example Does Not Imply

- Not every `Error` shares the same handling strategy.
- Not every checked exception should be caught immediately where it occurs.
- Not every RuntimeException is a programming bug; there are runtime wrappers for I/O/async errors.
- Compiling and running this example successfully does not prove every business method should `catch (IOException)`. The API contract must guide the choice.
- Direct `new Throwable()` is used for educational purposes, not as a recommendation to create domain classes extending Throwable.

## 8. Checked Exceptions: Compiler Requires Catch or Declare

Consider the method:

~~~java
static String readFirstLine(Path path) throws IOException {
    return Files.readAllLines(path).get(0);
}
~~~

This is a **Java fragment**, requiring imports for `java.nio.file.Path`, `java.nio.file.Files`, and `java.io.IOException`. `Files.readAllLines` can throw a checked `IOException`. Additionally, `get(0)` can throw an unchecked `IndexOutOfBoundsException` if the file is empty; `throws IOException` does not prevent that unchecked error.

When a caller invokes:

~~~java
String line = readFirstLine(path);
~~~

If the call can throw a checked `IOException`, the caller must either:
- **Catch it** with an appropriate `catch` block, or
- **Declare `throws IOException`** (or a valid supertype) to propagate it.

Catch example:

~~~java
try {
    String line = readFirstLine(path);
    use(line);
} catch (IOException e) {
    handleIoFailure(e);
}
~~~

Propagation example:

~~~java
static void process(Path path) throws IOException {
    String line = readFirstLine(path);
    use(line);
}
~~~

These are both **fragments**; the functions `use`/`handleIoFailure` are hypothetical. Simply having `throws` in a signature **does not mean the JVM catches the exception automatically**; it informs the compiler/caller that a checked exception may escape. If nothing catches it eventually, the exception can still reach the thread boundary/uncaught handler.

### 8.1. Compile Error When Omitting Catch/Throws

Suppose we have:

~~~java
static void readFile() throws IOException {
    throw new IOException("disk error");
}

static void caller() {
    readFile();
}
~~~

This is a fragment that intentionally **does not compile**: `caller` does not handle the checked exception declared by `readFile`. The compiler typically reports something equivalent to “unreported exception IOException; must be caught or declared to be thrown”. This is an illustrative diagnostic; the exact wording may vary by compiler/version.

Two ways to fix it:

~~~java
static void caller() throws IOException {
    readFile();
}
~~~

Or:

~~~java
static void caller() {
    try {
        readFile();
    } catch (IOException e) {
        report(e);
    }
}
~~~

These are two **independent fragment options** for the same method; do not put both methods with the same signature in one class and compile them together. `report` needs to be defined. If you merely catch and ignore it, the compiler is satisfied, but the program is **not necessarily business-correct**. The compiler only checks the **type contract**, not whether recovery succeeded.

### 8.2. A `throws Exception` Signature Is Valid but Often Too Broad

A method declaring:

~~~java
void execute() throws Exception {
    readFile();
}
~~~

can propagate `IOException` out via the `Exception` supertype. However, the caller loses specificity: it does not know which checked types are actually exposed by the public API. In stable APIs, prefer sufficiently specific checked types or a domain exception with a cause. For frameworks/callbacks that use the `throws Exception` convention, it can still be used per contract.

**`throws Exception` does not restrict what can escape solely to `Exception`:** RuntimeException and Error can still occur without being declared. Likewise, `throws Exception` does not mean the method always throws an exception.

## 9. Unchecked Exceptions: Compiler Does Not Force Declaration, Yet They Still Propagate

~~~java
static int parseCount(String raw) {
    return Integer.parseInt(raw);
}
~~~

This is a fragment. If `raw` is invalid, `Integer.parseInt` can throw an unchecked `NumberFormatException`; the compiler does not require `parseCount` to declare `throws NumberFormatException`. The caller can catch it if appropriate recovery exists, but is not forced to.

A developer **may** write:

~~~java
static int parseCount(String raw) throws NumberFormatException {
    return Integer.parseInt(raw);
}
~~~

Although this `throws` clause is optional, it can be used to emphasize the contract. For public APIs, Javadoc is usually where unchecked exception conditions are documented; relying on the compiler alone is not enough.

### 9.1. Unchecked Does Not Mean Always Let It Crash

If user input has an invalid format, the HTTP layer can catch `NumberFormatException` at the validation boundary and return an appropriate 400 error message. However, the catch should:
- catch only the expected type;
- know which input failed;
- not mask an unexpected `NullPointerException`;
- not turn an error into a fake “success” result.

For example, `Integer.parseInt("abc")` throws `NumberFormatException`; that is an unchecked type, yet a controller can translate it into a validation error **by contract**. There is no contradiction between “unchecked” and “handleable”.

## 10. What Does `catch (Exception)` Catch?

| Catch clause | Checked Exception subclass | RuntimeException subclass | Error subclass | Direct Throwable |
| --- | --- | --- | --- | --- |
| `catch (IOException e)` | Only IOException and subclasses | No, unless a type has a matching subtype relationship — there is no RuntimeException subclass of IOException in the JDK tree | No | No |
| `catch (Exception e)` | **Yes** | **Yes** | **No** | No |
| `catch (RuntimeException e)` | No | **Yes** | No | No |
| `catch (Error e)` | No | No | **Yes** | No |
| `catch (Throwable t)` | **Yes** | **Yes** | **Yes** | **Yes** |

This table describes **type matching once a throwable has been thrown**. It does not mean catching every type is good policy. `catch (Exception)` will catch `IllegalArgumentException` and `NullPointerException`, so it can mask bugs if it returns an unclassified fallback. However, `catch (Exception)` does not catch `OutOfMemoryError` or `NoSuchMethodError`.

### 10.1. Ordering `catch` Blocks from Specific to General

~~~java
try {
    read();
} catch (IOException e) {
    handleIo(e);
} catch (Exception e) {
    handleOther(e);
}
~~~

This is a fragment with hypothetical `read`/`handleIo`/`handleOther`. If an exception is an IOException, the first branch handles it. Placing `catch (Exception)` before `catch (IOException)` makes the second branch **unreachable** because IOException is a subtype of Exception, resulting in a compile error.

Do not write `catch (RuntimeException)` before `catch (IllegalArgumentException)` because IllegalArgumentException is a subtype of RuntimeException, which causes the same issue.

### 10.2. Should You `catch (Throwable)` to “Avoid Crashing”?

In ordinary business layers, **no**. Catching Throwable can swallow `OutOfMemoryError`, `StackOverflowError`, or `LinkageError` and keep running in an untrusted state. At certain special platform boundaries (such as task execution frameworks or test runners), broad catching may be needed to record, rethrow, or monitor, but you should not turn every Throwable into `null` or a success result.

Some `Error`s may be intentional assertions. Catching them in a **test framework** to report test failure is different from catching them in data-saving code and reporting “saved”.

## 11. `throw` and `throws` Are Not the Same

- `throw expression;` is the statement that **throws a Throwable object** at runtime.
- `throws Type1, Type2` is the **signature declaration** of exceptions that may propagate out, especially important for checked exceptions.

Example:

~~~java
static void openFile() throws IOException {
    throw new IOException("unavailable");
}
~~~

This is a valid fragment in a Java class after importing `IOException`. `throws IOException` does not create an error; `throw new IOException(...)` is what actually throws when the code runs.

With unchecked:

~~~java
static void requirePositive(int count) {
    if (count <= 0) {
        throw new IllegalArgumentException("count must be positive");
    }
}
~~~

Declaring `throws IllegalArgumentException` is not required, even though the method can throw it.

### 11.1. Does Java Allow `throw` on a Non-Throwable Value?

No: `throw "error";` is invalid because a String is not a subtype of Throwable. Java checks the type of the thrown expression. There is no automatic conversion of arbitrary objects into exceptions.

With application-defined exceptions:

~~~java
class InvalidDocumentException extends Exception {
    InvalidDocumentException(String message) {
        super(message);
    }
}
~~~

This is a checked fragment. Changing `extends Exception` to `extends RuntimeException` means the compiler no longer requires callers to catch/declare it. That decision **changes the compile-time contract** of the API, not just the class name.

## 12. How to Design Checked and Unchecked Custom Exceptions

Two examples:

~~~java
public final class StorageUnavailableException extends Exception {
    public StorageUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public final class InvalidRequestException extends RuntimeException {
    public InvalidRequestException(String message) {
        super(message);
    }
}
~~~

These are **two independent public class fragments**, which need to be saved in `StorageUnavailableException.java` and `InvalidRequestException.java` if compiled separately in an appropriate package. The first class is checked; the second is unchecked.

### 12.1. Selection Criteria

**Checked is appropriate when:**
- The error is part of the contract where the caller must confirm it was handled or declare propagation.
- Callers typically have a meaningful business action (retry, switch source, report a clear error, cleanup).
- The module accepts expanding `throws` signatures and propagation across layers.

**Unchecked is appropriate when:**
- A precondition or invariant is violated that code must fix/validate.
- There is no reasonable recovery at every intermediate layer.
- The API/framework/functional interface follows an unchecked convention.
- An infrastructure error is intentionally wrapped (e.g., `UncheckedIOException`), while **preserving the cause** and documenting the contract.

These criteria are **heuristics**; there is no universal rule like “I/O is always checked and validation is always unchecked” for every library. A domain “insufficient quota” case may use a Result, a checked exception, or an unchecked domain exception depending on how the API is structured.

### 12.2. Preserving the Cause When Wrapping

~~~java
try {
    writeToDisk();
} catch (IOException e) {
    throw new UncheckedIOException("Write failed", e);
}
~~~

This is a fragment with a hypothetical `writeToDisk` and `import java.io.UncheckedIOException`. `UncheckedIOException` is a subclass of RuntimeException, allowing an I/O error to cross a boundary that forbids checked declarations; the **cause remains the IOException**, readable via `getCause()`.

Do not use `new RuntimeException(e.getMessage())` if you need to preserve the stack/cause from I/O, because the message does not retain the full cause information.

## 13. Checked Exceptions with `try-with-resources`

`AutoCloseable.close()` is declared to potentially throw `Exception`. When using a resource whose static type is only `AutoCloseable`, the compiler may require handling `Exception` from closing, even if the body throws nothing.

~~~java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using");
    }
}
~~~

This is a Java 9+ fragment (works on Java 17): the resource variable must be *effectively final* when using the `try (resource)` syntax. Because the static type of `close` is `throws Exception`, the outer signature usually has to declare/catch an appropriate exception.

If the static type is `java.io.Closeable`, `close()` declares a narrower `throws IOException`. This is why the **type of the resource** affects checked exceptions from cleanup.

### 13.1. Primary and Suppressed

If the try body throws A and `resource.close()` throws B, try-with-resources keeps A as the primary exception and places B in `A.getSuppressed()`. If the body completes normally but close throws B, B can become the primary exception. With multiple resources, Java closes them in reverse order and there can be multiple suppressed exceptions.

This does not change whether exceptions are checked or unchecked: an `IOException` from close is still checked when the API requires catch/declare; a `RuntimeException` from close is still unchecked. Suppressed is a **relationship between Throwable objects**, not a new classification group.

## 14. `InterruptedException`: A Special Checked Exception for Coordination

`InterruptedException` is a checked exception that appears in blocking APIs supporting interruption, such as `Thread.sleep`, `BlockingQueue.take`, or `Future.get` when the waiting thread is interrupted.

~~~java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is a fragment inside an appropriate `void` method/lambda. If it cannot be propagated, you typically restore the interrupt flag and finish the work cooperatively. If the method allows `throws InterruptedException`, it can be propagated to the caller.

**Do not swallow `InterruptedException` and loop forever**: it may be a cancellation/shutdown request. At the same time, do not treat every interrupt as a business error thrown by another task; it is a signal acting on the waiting thread.

### 14.1. `CancellationException` Is Unchecked

`Future.cancel(...)` can cause `Future.get()` to throw `CancellationException`; it extends RuntimeException and is therefore unchecked. These two types represent two different events:
- `InterruptedException`: the **waiting thread** was interrupted.
- `CancellationException`: the Future was observed in a canceled state.

Neither guarantees the underlying remote side effect rolled back. When a caller cancels after a timeout, the task may still continue running if it does not cooperate. Do not catch both and return “succeeded”.

## 15. `Future` and `CompletableFuture`: Exception Comparison Table

| API / Scenario | Exception Observed by Caller | Checked? | Notes |
| --- | --- | --- | --- |
| `Future.get()` when task fails | `ExecutionException` | **Yes** | Task error is in `getCause()` |
| `Future.get()` when waiting thread is interrupted | `InterruptedException` | **Yes** | Task has not necessarily stopped |
| `Future.get(timeout, unit)` when timed out | `TimeoutException` | **Yes** | Does not automatically cancel the task |
| `Future.get()` after future is canceled | `CancellationException` | No | Subclass of RuntimeException |
| `CompletableFuture.join()` when stage fails | Usually `CompletionException` | No | Cause holds error from source stage |
| `CompletableFuture.join()` on canceled future | `CancellationException` may be thrown directly | No | Cancellation does not automatically interrupt the supplier |
| `CompletableFuture.get()` when stage fails | `ExecutionException` | **Yes** | `get()` follows the Future contract |
| `CompletableFuture.orTimeout(...)` when stage times out | Future completes exceptionally with `TimeoutException` | TimeoutException type is checked | `join()` usually wraps it in unchecked `CompletionException` |
| `whenComplete` callback itself throws RuntimeException | Dependent stage may fail | No for RuntimeException | If upstream already failed, the upstream error takes precedence per whenComplete contract |

**Common point of confusion:** the same `TimeoutException` is a **checked type**, yet if wrapped in `CompletionException` and observed through `join()`, the caller receives an **unchecked wrapper**. The underlying type does not change; only the error representation channel at the boundary changes.

### 15.1. `CompletableFuture.cancel(true)` Is Not Like Every `FutureTask.cancel(true)`

`CompletableFuture` implements Future, but the `mayInterruptIfRunning` parameter in `CompletableFuture.cancel(boolean)` is not used to interrupt the supplier. It can complete the future with `CancellationException` while the running computation continues. Even with `FutureTask`, interruption is a cooperative mechanism, not a forced rollback of work.

Therefore, an “unchecked CancellationException” classification says nothing certain about the state of external side effects.

## 16. Reflection and Binary Compatibility: Checked vs. Error

Two commonly confused names:

| Type | Checked? | Meaning |
| --- | --- | --- |
| `ClassNotFoundException` | Yes | An API call looking up a class by name cannot find the class (e.g., `Class.forName`) |
| `NoClassDefFoundError` | No, belongs to Error | JVM cannot use/define a required class at linking/initialization; cause may be a missing class or failed init |

Similarly:
- `InvocationTargetException` (checked, reflection) can wrap a throwable thrown by the invoked method.
- `ExceptionInInitializerError` (unchecked Error) is typically related to a failed static initialization.
- `NoSuchMethodException` (checked, reflection when looking up a method) differs from `NoSuchMethodError` (unchecked Error, binary incompatibility at linking).

Do not handle `NoSuchMethodError` by returning a default value as a normal business response. It usually requires comparing the **actual class/JAR loaded by the JVM, method descriptors, dependency versions, and build/deploy artifacts**. `ClassNotFoundException` also requires verifying the appropriate classloader/module path, but its compile-time catch/declare rules differ.

### 16.1. Class Initialization Errors Can Produce a Chain of Symptoms

A static initializer throwing an exception can lead to `ExceptionInInitializerError` on the first access. Subsequent accesses to the class marked as erroneous can lead to `NoClassDefFoundError`. Read the **original cause and log at the first occurrence** rather than only looking at a later error.

There is no rule that “NoClassDefFoundError always means a missing JAR”; sometimes the class exists, but earlier initialization failed.

## 17. Checked Exceptions and Overriding

Important rules when overriding an instance method:
- The implementation **must not declare new or broader checked exceptions** than those permitted by the overridden method's signature.
- It may **declare narrower checked exceptions** or declare none at all.
- Unchecked exceptions are not subject to the same checked-exception restriction; they must still adhere to the contract and Liskov/API design semantically.

Example:

~~~java
interface Reader {
    String read() throws IOException;
}

final class FileReaderImpl implements Reader {
    @Override
    public String read() throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("missing");
    }
}
~~~

This is a fragment, requiring an `IOException` import or qualified name. `FileNotFoundException` is a subclass of IOException, so the override is valid. If the implementation instead declared `throws SQLException`, it would be **invalid** because SQLException is a checked exception outside the bounds of `Reader.read()`.

Omitting `throws` in the implementation is permitted, but callers accessing through a `Reader` reference still see the interface's `throws IOException` contract at compile time.

### 17.1. Why Does This Rule Exist?

If an API promises to throw only checked IOException, another implementation cannot suddenly force callers to handle checked SQLException under a new signature without breaking the type contract. This preserves substitutability between an interface/base class and its implementations.

Do not put `throws Exception` on an interface just so future implementations can freely throw any checked exception, unless the API genuinely needs that broad contract.

## 18. Checked Exceptions in Lambdas and Method References

A lambda must be compatible with the signature of its **functional interface**. `java.util.function.Function<T,R>` only has `R apply(T t)` and declares no checked exceptions. Therefore:

~~~java
Function<Path, String> loader = path -> Files.readString(path);
~~~

This fragment **intentionally does not compile** (assuming imports), because `Files.readString` can throw checked `IOException` whereas `Function.apply` does not allow `throws IOException`.

Several proper ways to handle this:
1. Use a custom `ThrowingFunction<T,R>` interface with `throws IOException` when the API controls the interface.
2. Catch IOException inside the lambda and convert it to `UncheckedIOException` **with the cause**, if the pipeline contract accepts unchecked exceptions.
3. Return a typed `Found/Failed` result instead of only the success value.
4. Redesign so I/O runs at a layer that already has permission to handle checked exceptions.

Example fragment with a wrapper:

~~~java
Function<Path, String> loader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException("Cannot load " + path, e);
    }
};
~~~

This is a fragment requiring imports for `Function`, `Path`, `Files`, `IOException`, and `UncheckedIOException`. Wrapping with a cause preserves source information; do not catch and return an empty string if an empty string is also valid data.

### 18.1. Streams Do Not Automatically Understand Checked Exceptions

`stream.map(...)` accepts a Function and does not automatically add a checked `throws IOException` to the lambda signature. Avoid using an unclear-contract “sneaky throws” hack just to bypass the compiler, especially in shared libraries. Choose an adapter/wrapper/result with an explicit policy.

## 19. Multi-Catch and Common Types

Java supports catching multiple exception types that have no direct subclass relationship:

~~~java
try {
    performIoAndDbOperation();
} catch (IOException | SQLException e) {
    report(e);
}
~~~

This is a fragment with hypothetical functions; both checked exceptions must be throwable according to compile-time analysis of the try block (and imported). Multi-catch is valid only when the alternatives have no prohibited parent–child relationship. `catch (IOException | FileNotFoundException e)` is invalid because FileNotFoundException is a subclass of IOException.

In a multi-catch, the variable `e` has specific typing rules and is effectively final; you must use operations available on the appropriate common type (e.g., `Throwable.getMessage()`), without assuming `e` is always an IOException.

If `IOException` needs a retry while `SQLException` needs a rollback with different steps, **do not merge them** just to save lines of code. Multi-catch is appropriate when the handling policy is genuinely identical.

## 20. Common Misconceptions

### Misconception 1 — “Every `Exception` is checked”

False, because `RuntimeException extends Exception` yet is unchecked. Ask whether the type sits under RuntimeException or Error.

### Misconception 2 — “`Error` is a subclass of `Exception`”

False. The two classes are **two separate branches under Throwable**. `catch (Exception)` does not catch Error.

### Misconception 3 — “Checked means safe to recover; unchecked means unrecoverable”

False. Checked/unchecked is a compiler type-contract choice, not proof of transactional or side-effect safety. An `IOException` can occur after a file is partially written; a `NumberFormatException` can be safely translated into a validation error.

### Misconception 4 — “`throws` handles the error”

False. `throws` only declares the propagation path; it does not catch, roll back, or log.

### Misconception 5 — “Broad catching makes a system stable”

`catch (Exception)` can mask a RuntimeException caused by a bug. `catch (Throwable)` can even mask an Error. Without genuine recovery and a clear error state, catching only produces wrong results.

### Misconception 6 — “`RuntimeException` never needs to be documented in API docs”

The compiler does not require declaring it, but public APIs still need Javadoc/contracts for conditions such as invalid arguments, illegal states, or timeout wrappers that callers must know about.

### Misconception 7 — “`Error` always stops the entire JVM immediately”

Not absolutely. For example, an assertion can be caught by a test framework. However, being catchable does not mean it is safe to continue after a serious error.

### Misconception 8 — “`Exception.getCause()` is always non-null”

No. Many exceptions are created without a cause. Check before dereferencing `getCause()`, especially in generic logging/unwrapping code.

### Misconception 9 — “Checked exceptions annoy callers, so just convert every error to RuntimeException”

Wrapping a checked exception into an unchecked one can be necessary at boundaries that do not support checked exceptions, but **you must preserve the cause and semantics**. Turning every error into `RuntimeException("failed")` loses business classification capability.

### Misconception 10 — “Returning `Optional.empty()` after a catch handles checked IOException”

The compiler accepts it, but the caller can no longer distinguish “not found” from “storage error” if empty is a valid value. Propagate the exception or return a `Failed` result.

### Misconception 11 — “`CancellationException` is checked like `InterruptedException`”

No. `CancellationException` extends IllegalStateException/RuntimeException and is unchecked; `InterruptedException` is checked.

### Misconception 12 — “`CompletionException` and `ExecutionException` are the same”

Both can wrap the underlying cause from a task, but `CompletionException` is unchecked while `ExecutionException` is checked. Compare the `join` vs. `get` boundaries to understand why.

### Misconception 13 — “`NoClassDefFoundError` = `ClassNotFoundException`”

No. They have different inheritance trees, occur at different times, and have different API/runtime semantics. Inspect the specific classloader, dependencies, and cause.

### Misconception 14 — “`Error` in Java code means the ERROR log level”

No. `java.lang.Error` is a Throwable class; log severity `ERROR` is a concept defined by logging frameworks. An `IOException` can be logged at the ERROR level without **becoming a `java.lang.Error`**.

## 21. Hands-On Compiler and Runtime Experiments

In addition to the runnable program in Section 7, try three short experiments yourself.

### Experiment A — Compiler Forces Handling Checked Exceptions

~~~java
import java.io.IOException;

public class CheckedCompileTest {
    static void fail() throws IOException {
        throw new IOException("read failed");
    }

    public static void main(String[] args) {
        fail(); // Intentional compile error: missing catch or throws.
    }
}
~~~

This is a **Java file that intentionally does not compile**. Run `javac CheckedCompileTest.java` and observe the diagnostic about the unreported checked exception. Then add `throws IOException` to `main` **or** wrap `fail()` in `try/catch` and recompile. When leaving `throws IOException` on `main` and running without a catch, the program throws IOException out to the `main` boundary; that is different behavior from compile-time success.

### Experiment B — Unchecked Requires No Declaration

~~~java
public class UncheckedCompileTest {
    static void fail() {
        throw new IllegalArgumentException("invalid");
    }

    public static void main(String[] args) {
        fail();
    }
}
~~~

This Java file **compiles**; at runtime it throws IllegalArgumentException, and if uncaught, the main thread terminates with a stack trace. Do not confuse “compiles” with “succeeds at runtime”.

### Experiment C — `catch (Exception)` Does Not Catch `AssertionError`

~~~java
public class ErrorCatchTest {
    public static void main(String[] args) {
        try {
            throw new AssertionError("assertion failed");
        } catch (Exception e) {
            System.out.println("caught Exception");
        }
    }
}
~~~

This Java file can **compile**, but at runtime `AssertionError` does not enter `catch (Exception)` because Error is not an Exception. This is a short experiment in a learning environment, **not** a recommendation for production applications to intentionally throw Error for business control flow.

If you want to record assertion failures in a controlled way in tests, use a test framework; do not add `catch (Throwable)` to make a program “always print success”.

## 22. Decision Tree When Reading an Exception in Logs

~~~text
Encountering a Throwable in Java
|
+-- Is it Error or a subclass?
|      +-- Yes -> unchecked; inspect VM/linkage/assertion/runtime
|      +-- No
|
+-- Is it RuntimeException or a subclass?
|      +-- Yes -> unchecked; inspect cause, input, invariant, wrapper
|      +-- No
|
+-- Is it Exception or a subclass?
|      +-- Yes -> checked; caller must catch/declare per Java rules
|      +-- No -> direct Throwable / other branch: checked
|
+-- How to handle it?
       +-- Genuine recovery exists -> catch precisely and verify outcome
       +-- No recovery -> propagate/wrap preserving cause
       +-- Side effects occurred -> verify state, do not assume rollback
       +-- Across async boundary -> inspect ExecutionException/CompletionException cause
~~~

The classification tree clarifies **types and compiler obligations**, but deciding **how to recover** still depends on the business contract. There is no default rule like “checked → retry” or “unchecked → ignore”.

## 23. Checklist When Designing or Reviewing Exception Handling

- [ ] Clearly know whether the exception belongs to `Throwable`, `Exception`, `RuntimeException`, or `Error`.
- [ ] Do not call every subclass of `Exception` checked.
- [ ] Do not assume `catch (Exception)` will catch `Error`.
- [ ] Understand that checked requires `catch` or `throws` at points where it can propagate.
- [ ] Choose custom exception types deliberately; avoid extending Throwable directly unless necessary.
- [ ] If a public API throws unchecked exceptions for preconditions, document and test them.
- [ ] Do not use `catch (Throwable)` to hide errors and return a default value.
- [ ] Do not log and rethrow at every layer causing duplicates; preserve the cause when wrapping.
- [ ] Do not swallow `InterruptedException`; propagate or restore the interrupt status appropriately.
- [ ] Distinguish checked `ExecutionException` from unchecked `CompletionException`.
- [ ] Distinguish `ClassNotFoundException` from `NoClassDefFoundError` and `NoSuchMethodException` from `NoSuchMethodError`.
- [ ] Know that `try-with-resources` can throw checked exceptions from `close()` and preserve suppressed errors.
- [ ] Do not use `Optional.empty()`, `null`, or `false` to mask errors when the contract does not specify it.
- [ ] If an exception occurs after side effects or a timeout, do not assume rollback.
- [ ] If an error involves runtime JAR/linkage issues, verify the loaded binaries rather than only editing source lines.
- [ ] Test both compile-time checked cases and runtime unchecked paths.
- [ ] Choose Error handling appropriate to severity; do not attempt to continue in an untrusted state.

## 24. Reinforcement Exercises

### Exercise 1 — Accurate Classification

For each of the following types, note: **nearest parent in the main hierarchy**, **checked/unchecked**, and **whether the compiler forces catch/declare**:

~~~text
IOException
NumberFormatException
RuntimeException
SQLException
CancellationException
InterruptedException
CompletionException
ExecutionException
AssertionError
OutOfMemoryError
ClassNotFoundException
NoClassDefFoundError
Throwable
Exception
Error
UncheckedIOException
TimeoutException
~~~

Answer guide: every subclass of RuntimeException or Error is unchecked. IOException/SQLException/InterruptedException/ExecutionException/TimeoutException/ClassNotFoundException are checked. Throwable and Exception themselves are checked. UncheckedIOException and CompletionException belong to RuntimeException; AssertionError and OutOfMemoryError belong to Error.

### Exercise 2 — Fixing a Compile Error

Given a method `load() throws IOException` and a caller that neither declares `throws` nor catches it, write **two** fixes. Explain why one fix delegates responsibility to a higher-level caller while the other can recover immediately in the current method.

### Exercise 3 — Distinguishing `catch` Behavior

Given code with `catch (Exception e)`, predict whether it catches `NullPointerException`, `IOException`, and `StackOverflowError`. The answers are, respectively: **yes**, **yes**, **no**; then prove it using the inheritance hierarchy rather than guessing by name.

### Exercise 4 — API and Binary Errors

An application compiles against a library that has `Client.send(String)`, but at runtime it runs with a JAR version missing that method. Which group does `NoSuchMethodError` belong to? Can it be fixed by adding `throws IOException` to the calling method? The fix should focus on the **JAR/ABI version loaded at runtime**.

### Exercise 5 — Async and Timeout

A task throws `IOException`; caller A retrieves it via `Future.get()`, caller B retrieves it via `CompletableFuture.join()`, and caller C calls `Future.get(timeout)` and times out. Identify the appropriate wrapper or observed error and explain why **a wait timeout** does not prove the task has stopped.

### Exercise 6 — Checked Exceptions in Lambdas

Try using `Files.readString(path)` inside `Stream.map`. What does the compiler report? Design an approach that preserves `cause` using `UncheckedIOException` or returns a typed Result, and test that a read failure is not turned into a fake empty string.

### Exercise 7 — Do Not Equate Errors with Business Results

A user-lookup method returns `Optional.empty()` when the user does not exist. If the database throws a checked `SQLException`, should you catch it and return an empty Optional? Answer based on the absence vs. failure contract, negative caching risks, and caller behavior.

## 25. Summary

**Four facts to remember:**

1. `Throwable` is the root of the hierarchy of objects permitted to be thrown in Java. `Exception` and `Error` are two separate branches.
2. **Checked** = subtypes of Throwable **not belonging to** the RuntimeException or Error branches; the compiler generally requires catching/declaring them when they can propagate.
3. **Unchecked** = RuntimeException, Error, and all their subclasses. `RuntimeException` **is also an Exception**; `Error` **is not an Exception**.
4. The compiler checks types; it **does not prove** that the program recovered properly, does not roll back automatically, and does not guarantee that serious errors allow safe continuation.

When designing APIs, use the classification table to understand compiler obligations; then decide on `catch`, `throws`, wrappers, typed results, and monitoring based on the **business contract and the actual state of the work**.