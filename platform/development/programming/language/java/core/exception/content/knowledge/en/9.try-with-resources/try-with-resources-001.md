# Purpose and Syntax of try-with-resources Since Java 7

> **Context:** Java Core → Exception → Try-with-resources. Since **Java 7**, Java has provided the **try-with-resources** construct (often abbreviated as **TWR**) to automatically call `close()` on resource objects when exiting the `try` block. This construct helps prevent forgetting to close files, streams, sockets, JDBC resources, and many other `AutoCloseable` objects, even when the main operation throws an exception. Since Java 9, the syntax was extended to allow using certain pre-declared resource variables; the core rules remain automatic resource closing and preserving errors in a deterministic order.

## 1. Why Is try-with-resources Needed?

A Java program often uses **lifecycle-managed resources**: files, streams, readers, writers, connections, result sets, or custom resource-managing objects created by the application. Many off-heap resources (file descriptors, sockets, connections, native handles) must be closed in a timely manner; simply waiting for the garbage collector is not a reliable resource-release policy.

Error-prone code:

```java
// Illustrates the idea inside a method, not a standalone program.
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.FileReader("input.txt"));

String line = reader.readLine();
System.out.println(line);
reader.close();
```

If `readLine()` or `println(...)` throws an exception before `reader.close()`, normal execution is interrupted and `close()` is **not called**. The snippet above also lacks a policy for handling the checked `IOException` and depends on a file on disk.

Before Java 7, the common approach was to use `finally` with verbose manual cleanup code:

```java
// Illustrative method, valid when placed inside a class.
static String readFirstLineBeforeJava7(String path)
        throws java.io.IOException {
    java.io.BufferedReader reader = null;
    try {
        reader = new java.io.BufferedReader(
                new java.io.FileReader(path));
        return reader.readLine();
    } finally {
        if (reader != null) {
            reader.close();
        }
    }
}
```

This approach is better than forgetting `close()`, but it still has drawbacks:

- You must manually declare the variable outside `try`, check for `null`, and write `finally`.
- With multiple resources, cleanup code easily becomes long, repetitive, or prone to omissions.
- When both the `try` body **and** `close()` throw exceptions, an exception from `finally` can **mask the original error** if not handled carefully.
- Every `return`/exception branch must be considered to ensure cleanup and preserve diagnostic information.

TWR solves most of **resource closing lifecycle management**:

```java
// Illustrative method, valid when placed inside a class.
static String readFirstLine(String path) throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.FileReader(path))) {
        return reader.readLine();
    }
}
```

When exiting the `try` construct, Java automatically calls `reader.close()` according to language rules; you do not need to write `finally` just to close `reader`.

**Limitation:** TWR does not guarantee that read/write operations succeed, does not automatically roll back written data, and cannot recover from cases where the process/JVM terminates abnormally. It solves **resource lifecycle** according to Java's mechanism, and does not replace transactions or business-level recovery.

## 2. Original Syntax Supported Since Java 7

Most common form:

```java
try (ResourceType resource = resourceInitializer) {
    // Use the resource.
}
```

Where:

- `try` begins the construct.
- The parentheses `(...)` form the **resource specification**, containing one or more resource declarations.
- Each resource must have a type compatible with `java.lang.AutoCloseable`.
- `resourceInitializer` creates/obtains the object; if initialization succeeds, the resource falls under TWR management.
- The braces `{...}` contain the main work.
- Upon exiting the block (normally, via a valid `return`, `break`, `continue`, or an exception), initialized resources are closed according to the rules.
- `catch` and `finally` can be attached if needed to handle errors or clean up other state; they are **not required**.

Minimal example:

```java
try (java.io.StringReader reader = new java.io.StringReader("Java")) {
    System.out.println(reader.read());
}
```

This is a code snippet inside a method, not a standalone file. `StringReader` supports `Closeable`, so it can be used in TWR. `reader.read()` returns the Unicode code point of the first character (here, the character `J`); the example only illustrates syntax.

### 2.1. Single Resource or Multiple Resources

TWR with multiple resources in Java 7:

```java
try (FirstResource first = openFirst();
     SecondResource second = openSecond()) {
    // Use both first and second.
}
```

This is **illustrative code**; `FirstResource`/`SecondResource`/`openFirst()`/`openSecond()` need to be defined. A semicolon `;` separates resources; they can be placed on separate lines for readability. Java initializes them **from left to right**, then closes them in **reverse order**.

Practical example with a reader/writer:

```java
try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(new java.io.FileReader("in.txt"));
     java.io.BufferedWriter writer =
                 new java.io.BufferedWriter(new java.io.FileWriter("out.txt"))) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

This snippet performs real I/O, so it must be placed in a method with `throws IOException` or an appropriate handler, and requires two valid files/paths. Upon exiting the block, `writer` is closed **before** `reader`, regardless of the order in which they are used in the body.

### 2.2. Using `catch` and `finally` with TWR

```java
try (MyResource resource = open()) {
    use(resource);
} catch (java.io.IOException e) {
    report(e);
} finally {
    finishRequest();
}
```

This snippet is only a template; `MyResource` and the methods are not defined. The key point to remember is that **resource closing happens before executing any `catch`/`finally` blocks attached to that construct**. Therefore, the handler can receive either an error from the `try` body or an error thrown during `close()`, depending on exception types and order.

There is no need to write `finally { resource.close(); }` just to close a resource already managed by TWR. Manually closing it a second time may cause errors or side effects depending on the implementation; let TWR handle closing.

## 3. Type Requirement: The Resource Must Be `AutoCloseable`

`java.lang.AutoCloseable` was introduced in Java 7; this interface has the method:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

This is an **illustrative API declaration**, not the full JDK source code. `AutoCloseable` establishes the protocol for closing a resource when leaving scope.

Familiar types:

- `java.io.InputStream`, `OutputStream`, `Reader`, and `Writer` belong to the closeable types in the I/O hierarchy.
- `java.io.Closeable` extends `AutoCloseable`; `Closeable.close()` declares `throws IOException`, which is narrower than `throws Exception`.
- `java.sql.Connection`, `Statement`, and `ResultSet` support `AutoCloseable`, with close methods that can throw `SQLException`.
- Custom classes can `implements AutoCloseable` to bring their own lifecycle into TWR.

The requirement is not "the resource must be a file" or "it must declare a checked exception." Any object implementing the `AutoCloseable` protocol appropriately can be managed.

### 3.1. Two Related but Non-Identical Interfaces

| Characteristic | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Introduced | Java 7 | Before Java 7; since Java 7, a subtype of `AutoCloseable` |
| Core method | `close() throws Exception` | `close() throws IOException` |
| Broadest checked error type in interface signature | `Exception` | `IOException` |
| Can be used in TWR? | Yes | Yes |
| Contract on repeated closing | Not guaranteed that every implementation is idempotent | `Closeable.close()` contract requires closing an already-closed resource to have no effect |

If a resource is declared with type `AutoCloseable`, the compiler may force the method to handle/declare `Exception` even when the concrete runtime object has a `close()` that does not throw any checked exception. With a more specific variable type, the compiler sees the narrower `close()` signature.

Note: `AutoCloseable` classes can define `close()` without declaring any checked exception, for example:

```java
final class SimpleResource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("Đã đóng");
    }
}
```

This is a valid class, though it has no `main`. `throws Exception` is not needed on `close()` because an implementation is allowed to narrow the set of checked exceptions of the interface.

### 3.2. What Code Cannot Be Used in a Resource Specification?

Types that do not implement `AutoCloseable` are invalid:

```java
// INTENTIONALLY INVALID example, does not compile:
try (String message = "hello") {
    System.out.println(message);
}
```

`String` does not implement `AutoCloseable`. Simply being a variable that "can go out of scope" is not enough; TWR needs the ability to call `close()` via the interface.

Another mistake is forgetting **parentheses** or writing a resource expression like a normal argument:

```java
// INTENTIONALLY INVALID:
try (new java.io.StringReader("x")) {
    // In Java 7, an object creation expression cannot be used directly as a resource declaration.
}
```

In Java 7 syntax, the resource must be declared with a variable inside `(...)`. Java 9 extended this to allow an already-declared, effectively final variable, as explained in Section 8.

## 4. Java 17 Program 1: Automatic Closing on Both Success and Failure Paths

This example does not depend on files on disk. We implement a custom resource to observe exactly when `close()` is called.

Create `TryWithResourcesBasics.java`:

```java
public class TryWithResourcesBasics {
    static final class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        void use() {
            System.out.println("Dùng " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static void run(boolean fail) {
        try (TrackedResource resource = new TrackedResource("R")) {
            resource.use();
            if (fail) {
                throw new IllegalStateException("Thao tác lỗi");
            }
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        } finally {
            System.out.println("Kết thúc run");
        }
    }

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 TryWithResourcesBasics.java
java TryWithResourcesBasics
```

Exact stdout:

```text
Mở R
Dùng R
Thân try thành công
Đóng R
Kết thúc run
---
Mở R
Dùng R
Đóng R
Bắt: Thao tác lỗi
Kết thúc run
```

**Analysis:**

1. The `run(false)` call creates the resource, uses it, and completes the `try` body. `close()` is called **before** leaving the construct, then `finally` runs.
2. The `run(true)` call throws `IllegalStateException` inside the body. The line "Thân try thành công" does not run; TWR still calls `close()` before running `catch`.
3. `catch` handles the business error, not resource closing. Here `finally` only illustrates general work outside resource closing.
4. A new resource is opened on each call; the output does not depend on GC, timing, or the filesystem.

**Do not conclude that every program always finishes closing:** TWR executes closing along Java's normal control flow; abnormal JVM/process termination, native crashes, or severe failures can prevent this from happening. Such events require separate data durability policies.

## 5. Initialization Order and Closing Order for Multiple Resources

Java initializes resources in the order they appear in `(...)`, from **left to right**. When exiting the TWR scope, Java closes them in **reverse order**: the last declared resource is closed first.

Create `ResourceCloseOrderDemo.java`:

```java
public class ResourceCloseOrderDemo {
    static final class NamedResource implements AutoCloseable {
        private final String name;

        NamedResource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B");
             NamedResource third = new NamedResource("C")) {
            System.out.println("Thân try");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ResourceCloseOrderDemo.java
java ResourceCloseOrderDemo
```

Stdout:

```text
Mở A
Mở B
Mở C
Thân try
Đóng C
Đóng B
Đóng A
```

This order makes pipelines easier to write: if resource `B` uses resource `A`, declaring `A` first and then `B` typically allows `B` to be closed before `A`.

### 5.1. What If a Resource Initializer Fails?

An important advantage: resources **already initialized successfully** are still closed, even if creating a subsequent resource fails.

Conceptual example:

```java
try (Resource first = openFirst();
     Resource second = openSecondThatThrows()) {
    work(first, second);
}
```

This is illustrative code; the classes and methods are not defined. If `openFirst()` succeeds but `openSecondThatThrows()` throws an exception, `first` is still closed according to the rules. `second` was not successfully initialized, so it is not closed as an acquired resource. If `openSecondThatThrows()` allocated an internal resource and threw before returning an object, its internal cleanup responsibility remains with that initializer's implementation; the outer TWR cannot close a resource it never received.

### 5.2. Resource Initializer Evaluating to `null`

An initializer can evaluate to `null` for a resource reference type. The TWR rule **does not call `close()` on a resource whose value is `null`**. This differs from calling `resource.close()` directly when `resource == null`, which throws `NullPointerException`.

Even though the language handles this case, APIs should not ambiguously use `null` as a valid resource. Cases where opening fails should be expressed clearly through contracts, exceptions, or appropriate structured results.

## 6. Special Case: Both the `try` Body and `close()` Throw Exceptions

This is why TWR is better than a simple `finally` block in many cases. Java does not lose the primary error just because `close()` also fails.

**Concepts:**

- **Primary exception:** the exception escaping from the `try` body/main operation that is prioritized and preserved.
- **Suppressed exception:** an exception thrown while closing a resource when a primary exception already exists; attached to the primary exception via `Throwable.addSuppressed(...)` by the TWR mechanism.
- `Throwable.getSuppressed()` returns an array of exceptions recorded this way.
- `getCause()` and `getSuppressed()` represent two different relationships: cause describes a causal chain, while suppressed records secondary errors during cleanup.

### 6.1. Java 17 Example 3: Primary and Suppressed

Create `SuppressedExceptionDemo.java`:

```java
import java.io.IOException;

public class SuppressedExceptionDemo {
    static final class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (BrokenClose resource = new BrokenClose()) {
            System.out.println("Đang xử lý");
            throw new IOException("Lỗi xử lý");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Số suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Stdout:

```text
Đang xử lý
Đang đóng
Primary: Lỗi xử lý
Số suppressed: 1
Suppressed: Lỗi đóng
```

**Execution flow:**

1. The resource is created successfully.
2. The `try` body prints "Đang xử lý" and then throws `IOException("Lỗi xử lý")`.
3. Java still calls `resource.close()`; the method prints "Đang đóng" and then throws `IOException("Lỗi đóng")`.
4. The exception from the body is **primary**. The error from `close()` is **suppressed** onto the primary exception.
5. `catch (IOException e)` receives the primary exception and uses `getSuppressed()` to inspect the error from closing.

If you only used `finally { resource.close(); }` in an older pattern without handling close errors separately, the exception from `close()` could replace the original error and lose critical information about the operation's root cause.

### 6.2. What If the `try` Body Succeeds but `close()` Throws?

When there is no primary exception from the `try` body, an error thrown during `close()` becomes the **primary exception escaping the construct**. Saying "TWR always prioritizes errors from the `try` body" is only true **when a body error exists**.

With multiple resources, if the body succeeds but one or more `close()` calls fail, the close error from the **first resource closed** (the last resource declared) becomes the primary exception, and subsequent close errors become suppressed exceptions.

### 6.3. Java 17 Example 4: Two Close Failures

Create `MultipleCloseFailuresDemo.java`:

```java
import java.io.IOException;

public class MultipleCloseFailuresDemo {
    static final class Failing implements AutoCloseable {
        private final String name;

        Failing(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Failing first = new Failing("A");
             Failing second = new Failing("B")) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed first: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 MultipleCloseFailuresDemo.java
java MultipleCloseFailuresDemo
```

Stdout:

```text
Thân thành công
Đóng B
Đóng A
Primary: close B
Suppressed count: 1
Suppressed first: close A
```

Resource `B` is closed first. When `B.close()` fails, it becomes the primary exception. Java continues closing `A`; the exception from `A.close()` is attached as suppressed.

**Diagnostic note:** if you only print `e.getMessage()` and ignore suppressed exceptions, secondary close errors are easily missed. A logger that prints the full `Throwable` stack trace typically includes suppressed exceptions; if using a custom log format, verify that it does not drop this information.

## 7. When Do `catch` and `finally` Run?

Given the structure:

```java
try (Resource r = open()) {
    use(r);
} catch (Exception e) {
    handle(e);
} finally {
    reportEnd();
}
```

This is an illustrative template depending on appropriate definitions. General order:

```text
Initialize resources
        ↓
try body
        ↓
Close resources in reverse order
        ↓
Matching catch (if an exception is propagating)
        ↓
finally (if present and no external abnormal termination occurs)
        ↓
Result/exception continues to the caller
```

For a `return` inside the `try` body, TWR also closes the resources before the call completes normally. If `close()` throws an exception after the return value has been computed, the close error can prevent the method from **completing with the expected return**. Do not assume that `return` bypasses resource closing.

### 7.1. A `catch` Block Can Catch Both Body Errors and Close Errors

In `SuppressedExceptionDemo`, `catch(IOException)` receives the body error; in `MultipleCloseFailuresDemo`, it receives the close error. Same syntax, different primary sources.

The compiler checks checked exceptions from initializers, calls in the body, **and `close()`**, so the following example still needs to catch/declare `IOException` even though the body only prints text:

```java
// Illustrative snippet, Resource.close() throws IOException.
try (Resource r = new Resource()) {
    System.out.println("Không có I/O trong thân");
} catch (java.io.IOException e) {
    System.out.println("Đóng lỗi: " + e.getMessage());
}
```

This is an explanatory snippet assuming `Resource` is already defined. If you replace the resource with a class whose `close()` declares no checked exception, the ability to catch checked `IOException` must also be reconsidered based on the exact signatures of the initializer and body.

### 7.2. TWR Is Not Reversed Normal `catch` Handling

Java does not invoke `catch` first and then close the resource. Resources are closed when exiting the TWR portion; attached handlers run after this process. This differs from placing `close()` inside `catch` itself, which misses the success path.

## 8. How Java 7 Syntax Differs from Java 9 and Java 10+

This is an important point when a requirement specifies **"since Java 7"**: you need to distinguish the original feature from syntax added in later versions.

### 8.1. Java 7: Declaring the Resource Variable Directly Inside the `try` Parentheses

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Hello"))) {
    System.out.println(reader.readLine());
}
```

This snippet uses TWR syntax from Java 7. The `reader` variable is declared in the resource specification; it cannot be reassigned afterward in the `try` body. After TWR finishes, a resource variable declared this way is out of scope for subsequent code.

### 8.2. Java 9: Using an Existing Variable If `final` or Effectively Final

Since **Java 9**, you can write:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(
                new java.io.StringReader("Hello"));
try (reader) {
    System.out.println(reader.readLine());
}
```

This is an illustrative snippet inside a method, valid on Java 9+ (including Java 17). `reader` is declared before `try` and is not reassigned after initialization, so it is **effectively final**. The syntax **`try (reader)` without a variable declaration inside** is invalid if compiled with Java 7 language mode.

If `reader` is reassigned to another object after declaration, it is no longer effectively final and is not eligible for direct use in a Java 9 resource specification.

Read the meaning carefully:

- `try (reader)` **does not initialize** a new resource; it uses the object the variable already references.
- When the block exits, the resource is **closed**, even though the `reader` variable remains in lexical scope outside `try`.
- The variable still existing does **not** mean the closed object can continue to be used. You must obey the resource's contract.
- If the resource is opened before entering `try`, an exception occurring **between opening and the start of `try`** can leave the resource unmanaged by TWR. Whenever possible, declaring and initializing directly inside `try(...)` is simpler.

### 8.3. Java 10+: `var` in Resource Declarations

Java 10 introduced local-variable type inference `var`, so in Java 10+ you can write:

```java
try (var reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Hello"))) {
    System.out.println(reader.readLine());
}
```

This is also a valid illustrative snippet in Java 17. TWR appeared in Java 7, but `var` syntax is **not** supported in Java 7 or Java 9. Choose syntax based on your project's Java version; if you want an example to run on Java 7, use explicit type declarations inside the resource parentheses.

### 8.4. Version Summary

| Java Version | Typical Resource Syntax | Key Takeaway |
| --- | --- | --- |
| Java 7/8 | `try (BufferedReader r = new BufferedReader(...))` | Declare resource directly in `try`; multiple resources separated by `;`. |
| Java 9 | `BufferedReader r = ...; try (r)` | Use an existing `final` or effectively final variable. |
| Java 10+ | `try (var r = new BufferedReader(...))` | Use `var` for a local resource variable with an initializer. |
| Java 17 | Supports all three valid forms | Choose based on source compatibility targets and types. |

**Do not say** "Java 7 allows `try (existingVariable)`" or "TWR only exists since Java 9." Both statements are false.

## 9. Java 17 Program 5: Using an Effectively Final Variable

Create `ExistingResourceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.StringReader;
import java.io.IOException;

public class ExistingResourceDemo {
    public static void main(String[] args) throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("Java 17"));

        try (reader) {
            System.out.println("Đọc: " + reader.readLine());
        }
        System.out.println("Đã ra khỏi try-with-resources");
    }
}
```

Run with JDK 17:

```bash
javac -encoding UTF-8 ExistingResourceDemo.java
java ExistingResourceDemo
```

Stdout:

```text
Đọc: Java 17
Đã ra khỏi try-with-resources
```

`reader` is still a valid local variable after the `try` block, but the resource has been closed. The program deliberately **does not call `readLine()` after closing**; continuing to use it depends on the specific resource's behavior and is usually invalid for streams/readers.

If you change the code to:

```java
BufferedReader reader =
        new BufferedReader(new StringReader("a"));
reader = new BufferedReader(new StringReader("b"));
try (reader) {
    // Does not compile: reader has been reassigned and is not effectively final.
}
```

Java 17 rejects `try (reader)` because the variable was reassigned. This is an **intentionally non-compiling snippet**; you need a new resource variable declared inside the parentheses or a different lifecycle design.

## 10. How to Design an `AutoCloseable` Class Safely

You can bring custom objects into TWR by implementing `AutoCloseable`:

```java
final class Session implements AutoCloseable {
    private boolean closed;

    void send(String message) {
        if (closed) {
            throw new IllegalStateException("Session đã đóng");
        }
        System.out.println("Gửi: " + message);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("Đóng session");
        }
    }
}
```

This is a class definition without `main`; it can be used with another Java program that has an entry point. Design points:

- Ensure the resource is in a valid state once the constructor completes.
- `close()` should release only the resources owned by the instance; it should not arbitrarily close shared resources managed by another object.
- Consider idempotency where appropriate: in the example above, a second close does not print again. For `AutoCloseable` in general, never assume every implementation is idempotent.
- Once closed, operations requiring an open state should fail clearly.
- If `close()` can fail, choose an appropriate checked exception type and document the remaining state in the API.
- When a resource is used across multiple threads, a separate synchronization policy is required; TWR does not provide thread safety.

Usage example:

```java
try (Session session = new Session()) {
    session.send("Xin chào");
}
```

This is a snippet inside a method; when run, it prints `Gửi: Xin chào` then `Đóng session`. No `catch` or `throws` is needed because `Session.close()` does not declare any checked exception.

### 10.1. Resource Ownership Matters

Not every `AutoCloseable` variable should be placed in a short-lived TWR. If the caller **does not own** the resource, closing it automatically can break another component's work.

Examples:

- A method that opens a file itself to read: usually **owns** the reader, so it should close it.
- A method that receives an `InputStream` passed in by the caller: read the contract; the caller may expect the stream to remain open for further use.
- Connection pools: a `Connection` object may represent a connection "returned to the pool" when `close()` is called; implementation semantics are defined by the library/pool.
- `System.in`: closing a wrapper around standard input can close the standard input stream itself, affecting the rest of the program.

**Mental model:** "Who opens/acquires the resource, and who is responsible for ending its lifecycle?" Do not blindly apply TWR to shared objects.

## 11. Does TWR Completely Replace `finally`?

**No.** TWR specializes in `AutoCloseable` resources. `finally` remains useful for actions not tied to an `AutoCloseable` resource or that must run whether an operation succeeds or fails, such as recording a completion milestone, releasing a lock per contract, or restoring thread context per policy.

Illustrative example:

```java
try (Resource resource = acquire()) {
    perform(resource);
} catch (java.io.IOException e) {
    reportFailure(e);
} finally {
    recordCompletion();
}
```

This is sample code depending on undefined resources and methods. When the resource is already closed automatically by TWR, `finally` does not need to close it again. If there is a lock, transaction, or custom state to revert, design that responsibility explicitly rather than implicitly delegating everything to `close()`.

### 11.1. Do Not Turn Resource Closing into Business Exception Handling

A connection closing successfully does **not** prove a transaction committed/rolled back as intended. A writer closing successfully does **not** mean the entire file was durably written against a power loss. If you need atomicity, durability, or recoverability, choose transactions, writing to a temporary file and replacing, result checks, or an appropriate application protocol.

TWR only manages **calling `close()`** on the resources handed to it along Java's normal control flow.

### 11.2. Exceptions in `finally` Can Mask the Primary Error

If manual cleanup in `finally` throws an exception, it can overwrite an exception propagating from the `try` body. This is one reason to use TWR: Java automatically organizes suppressed exceptions when `close()` also fails.

Avoid using `return` or throwing a new exception in `finally` unless you deliberately accept altering the result or masking earlier errors.

## 12. Try-with-resources and Checked Exceptions

Sources of checked exceptions that the compiler may require you to handle include:

1. The resource's constructor/initializer.
2. Methods called inside the `try` body.
3. The `close()` method on the resource type according to the signature visible to the compiler.

For example, `AutoCloseable` has `close() throws Exception`, so using a variable with that interface type can force the method to declare `throws Exception`; using a concrete class with `close() throws IOException` may only require `throws IOException`.

Compare two examples **inside a class body**:

```java
static void broad() throws Exception {
    try (AutoCloseable resource = createResource()) {
        System.out.println("Đang xử lý");
    }
}
```

`createResource()` is not defined; assume it has no other checked exceptions itself. Because `resource` has static type `AutoCloseable`, the compiler checks `close() throws Exception`. This is illustrative code.

```java
static void narrow() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader("x"))) {
        System.out.println(reader.readLine());
    }
}
```

`BufferedReader` has read/close methods declaring `IOException`, so declaring `throws IOException` is appropriate. Even though `StringReader` data is in memory, the `BufferedReader` type contract still includes checked exceptions.

### 12.1. `close()` Failing When the Method Is About to `return`

Consider the idea:

```java
static String load() throws java.io.IOException {
    try (MyReader reader = createReader()) {
        return "OK";
    }
}
```

This is an illustrative example; `MyReader`/`createReader()` are not implemented, assuming `close() throws IOException`. Java computes the return value, but still closes the resource before finishing the call. If `close()` throws `IOException`, the call can exit with an exception instead of returning `"OK"`. Therefore, method exit paths must be designed and tested for close-time errors as well.

### 12.2. Should You Catch Every `Exception` to "Swallow" Close Errors?

No. If closing fails, the resource or data may be in an indeterminate state. Catching broadly and falsely reporting success easily hides the root cause. When an error needs handling, catch the appropriate type, log both primary and suppressed exceptions when valuable, and mark the work as failed if necessary.

## 13. TWR in Practice: Reading a File and Processing Data

This complete Java 17 example works with a temporary file so no input setup is needed. It creates a temporary file, writes lines, reads them back using TWR, and then deletes the file in the example's `finally` block; deletion is checked and can throw `IOException`.

Create `FileResourceDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileResourceDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("twr-learning-", ".txt");
        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write("Java");
                writer.newLine();
                writer.write("Try-with-resources");
                writer.newLine();
            }

            try (BufferedReader reader =
                         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 FileResourceDemo.java
java FileResourceDemo
```

**Stdout when file operations succeed:**

```text
Java
Try-with-resources
```

This is a real I/O example, so it can fail due to permissions, insufficient disk space, external file modification, or system errors. **Do not** treat those two lines as guaranteed output if the environment does not allow creating/deleting files; on error, the program can throw `IOException` and print a stack trace to stderr because `main throws IOException`.

Highlights:

- The first TWR owns `BufferedWriter`, so it closes automatically after writing, ensuring writer closure completes before opening the reader.
- The second TWR owns `BufferedReader` and closes it automatically after the loop.
- The outer `finally` is responsible for cleaning up the **temporary file**, which is distinct from closing streams.
- `StandardCharsets.UTF_8` makes the encoding explicit, avoiding dependence on the default charset.
- Using two consecutive TWRs demonstrates separate lifecycles for the writer and reader; no manual `close()` calls are needed.

### 13.1. Can You Both Read and Write in One TWR?

Yes, if you want to own both resources simultaneously and do not need to wait for the writer to close before reading. However, for file data that must be read after writing, a buffered writer may not have flushed all data yet. Closing or calling `flush()` at the right time before reading clarifies the contract. `flush()` does not mean data is durable on disk against a power loss.

## 14. Common Mistakes with try-with-resources

| Misconception or Mistake | Problem | How to Handle It |
| --- | --- | --- |
| "TWR is only for reading files." | Any suitable `AutoCloseable` can be used. | Use for JDBC, streams, and custom resources when ownership is clear. |
| "Resource closing only happens if the try body succeeds." | `close()` is also called when exiting the block due to an exception. | Test both success and failure paths. |
| "You can put `String` in try parentheses." | `String` does not implement `AutoCloseable`. | Use a proper type or move logic to a regular `try`. |
| "Java 7 allows `try (reader)` with an outer variable." | Existing-variable syntax was added in Java 9. | Java 7/8 require declaring the resource directly inside `(...)`. |
| "Java 7 supports `var` for resources." | `var` was introduced in Java 10. | Use explicit types if Java 7 compatibility is required. |
| "Resources can close in any order." | TWR closes in reverse declaration order. | Order dependent resources so the closing order is appropriate. |
| "If the second initializer throws, the first resource isn't closed." | Successfully initialized resources are cleaned up when a later initialization fails. | Ensure constructors do not leak unhanded resources. |
| "When both body and close fail, close hides the body error." | TWR keeps the body error as primary; close can become suppressed. | Inspect `getSuppressed()` and log thoroughly. |
| "If the body has no error, a close error is ignored." | A close error can become the primary exception. | Catch/declare checked exceptions from `close()`. |
| "TWR automatically commits/rolls back the database." | Closing a resource does not guarantee transaction integrity. | Use explicit transaction/commit/rollback policies per API. |
| "A variable declared outside `try` is still usable so the resource is still open." | The variable may remain in scope, but the resource is closed. | Do not operate on it after close unless the API allows it. |
| "`catch (IOException)` is always valid because TWR always involves I/O." | TWR can manage resources that do not declare `IOException`. | Base catches on actual initializer, body, and `close()` types. |
| "Closing a shared stream has no external effect." | `close()` can terminate a resource used by the caller/another component. | Agree on ownership before using TWR. |
| "With TWR, `finally` is never needed anymore." | `finally` is still useful for non-`AutoCloseable` actions. | Separate responsibilities clearly; do not redundantly close resources. |
| "You can call `reader` after TWR if it hasn't been GC'd." | Resource lifecycle does not depend on GC. | Respect the closed state. |

## 15. Frequently Asked Questions

### 15.1. Can you write `try (...)` without `catch` and `finally`?

**Yes**, if it is a valid **try-with-resources** statement. For a regular `try` (without a resource specification), Java requires `catch`, `finally`, or both. TWR allows omitting both because the construct itself defines resource-closing behavior.

### 15.2. In what order are multiple resources closed?

In **reverse** order of their declaration in `(...)`. In `try (A a = ...; B b = ...; C c = ...)`, the opening order is A → B → C, and the closing order is C → B → A.

### 15.3. Is `close()` called if there is a `return` in the `try` body?

**Yes**, along normal Java execution paths. The return value may already be computed, but closing happens before the method finishes; an error in `close()` can replace the return.

### 15.4. Does `close()` run when a resource initializer returns `null`?

No, a resource with a `null` value is skipped when closing. However, the caller still needs to understand whether `null` is a valid state under the contract.

### 15.5. Does TWR automatically start a database transaction?

No. JDBC `Connection` has its own transaction protocol. TWR helps close the connection, statement, and result set; commit/rollback must be designed around auto-commit settings, driver/pool protocols, and business requirements. Do not infer transaction success just because `close()` ran.

### 15.6. If both the `try` body and `close()` fail, which exception does a handler catch?

If the body throws an exception and closing also throws, the body's exception is normally primary, and close errors are attached under `getSuppressed()`. Handlers match against the **primary `Throwable` being thrown**, and do not automatically pick a matching suppressed exception.

### 15.7. How do `AutoCloseable` and `Closeable` differ?

`AutoCloseable.close()` declares `throws Exception`; `Closeable.close()` declares `throws IOException` and has a specific contract for repeated closing. Both can be used in TWR. The compiler checks signatures based on the static type of the resource.

### 15.8. Why is using an existing resource variable in Java 9+ still something to be careful with?

If the variable is declared outside, the resource is still closed after TWR; external code may still hold a reference and accidentally operate on a closed resource. Additionally, opening the resource outside the block requires thinking about any code between opening and the start of TWR management.

## 16. Practice Exercises

### Exercise 1 — Convert `finally` to TWR

Given the illustrative method:

```java
static String firstLine(String path) throws java.io.IOException {
    java.io.BufferedReader reader = null;
    try {
        reader = new java.io.BufferedReader(
                new java.io.FileReader(path));
        return reader.readLine();
    } finally {
        if (reader != null) {
            reader.close();
        }
    }
}
```

Rewrite it using `try (BufferedReader reader = ...) { return reader.readLine(); }`. Compare line count, intent, and what happens if both `readLine()` and `close()` throw errors.

### Exercise 2 — Predict Stdout Order

Run `ResourceCloseOrderDemo` with declaration order `A, B, C`. Then change it to `C, A, B`. Predict the open and close order without running; explain why closing is always the reverse of declaration order.

### Exercise 3 — Body Error and Close Error

Run `SuppressedExceptionDemo`. Replace the body with a print statement that does not throw. When `close()` still throws `IOException`, how does the primary line change? How many elements will `getSuppressed()` have when there is only one close error?

### Exercise 4 — Write Your Own `AutoCloseable`

Create a `TimerScope implements AutoCloseable` class that records a name and prints `Start name` in the constructor and `End name` in `close()`. Use TWR to observe both the success branch and throwing `IllegalStateException`. Do not rely on system time for deterministic stdout.

### Exercise 5 — Compare Java 7 and Java 9

Write two versions of code reading a line from `StringReader`: (A) declaring `BufferedReader` inside `try (...)`, (B) declaring it beforehand and then `try (reader)`. Explain which version compiles with `--release 7` (if your JDK supports compiling at that level) and why version (B) is only valid starting in Java 9. In Java 17 examples, both forms can be used.

### Exercise 6 — Spot the Ownership Bug

An API receives an `InputStream input` provided by the caller and only needs to read 5 bytes. Should it always write `try (input)` to close it? Explain why knowing the ownership contract is necessary, and propose documenting whether "the method will close the stream" or "the caller is responsible for closing."

### Exercise 7 — Checked Exceptions Relationship

Create an `AutoCloseable` whose `close() throws Exception`, while the `try` body throws no checked exception. When writing a method containing this TWR, what kind of checked exception declaration/handler does the compiler require? Try changing the resource type to a subclass whose `close()` declares no checked exception to see the effect of static typing.

### Exercise 8 — Testing When a New Resource Initialization Fails

Create a first `AutoCloseable` whose `close()` prints `"closed first"`, and a second initializer that throws `IllegalStateException`. Verify that the first resource is still closed. Explain why a resource not yet successfully handed over to TWR must manage its own internal allocations inside the initializer.

## 17. Checklist Before Applying TWR

- [ ] Does the resource actually implement `AutoCloseable` or `Closeable`?
- [ ] Do I clearly know **who owns** the resource and who is responsible for closing it?
- [ ] Are all managed resources placed in `try (...)` in the right order?
- [ ] Have I distinguished Java 7's inline declaration syntax from Java 9's effectively final variable syntax?
- [ ] Am I using `var` even though the project needs to compile on Java 7 or 8?
- [ ] Have I accounted for checked exceptions from the initializer, body, and `close()`?
- [ ] Do I know that resources close in reverse order when there are multiple resources?
- [ ] Have I verified that a failure in a later initializer still closes earlier resources?
- [ ] Do I understand primary/suppressed exceptions and avoid accidentally losing diagnostic information?
- [ ] Have I avoided redundantly closing the resource manually in `finally`?
- [ ] If a resource variable remains in scope after TWR, do I avoid using it in an invalid state?
- [ ] Have I distinguished resource cleanup from business transactions/rollback?
- [ ] For real I/O, have I chosen a charset, handled file errors, and designed the data lifecycle properly?
- [ ] Do tests cover success, body failure, close failure, multiple resources, and initializer failure?

**Remember:** try-with-resources has been available since **Java 7**, using `try (Resource r = ...) { ... }` to automatically close `AutoCloseable` objects. Java initializes resources in declaration order, closes them in reverse order, and preserves close errors as **suppressed** exceptions when a primary error already exists. Since **Java 9**, you can write `try (existingResource)` with a `final`/effectively final variable; since **Java 10**, you can use `var` in resource declarations. TWR makes resource lifecycle management much more reliable, but it does not replace contextual exception handling or data-preserving transactions.