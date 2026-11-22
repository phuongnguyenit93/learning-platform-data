# `AutoCloseable` and `Closeable` in Java: The Foundation of `try-with-resources`

A Java program often works with resources that must be terminated in a timely manner: file read/write streams, database connections, sockets, channels, or stateful sessions. The garbage collector manages the memory of Java objects, but it is **not a replacement for closing resources promptly**. To express "closeable" capability, Java provides the `java.lang.AutoCloseable` interface and the more specialized `java.io.Closeable` interface.

When a resource is declared in the header of a `try-with-resources` statement, Java automatically calls that resource's `close()` method upon exiting the block. This mechanism helps reduce forgotten-close bugs, handles the closing order of multiple resources, and preserves information when both the primary operation and the close operation fail.

**Lesson scope:** understand the exact relationship between `AutoCloseable` and `Closeable`, the `close()` signature, checked exception rules, the multiple-close contract, how to use them with `try-with-resources`, how to write custom resource classes, and design pitfalls to avoid. All complete examples use **Java 17+** and require no external files or services.

## 1. How Do the Two Interfaces Relate?

`AutoCloseable` is in `java.lang` (no import needed). `Closeable` is in `java.io` and **extends `AutoCloseable`**:

```java
public interface AutoCloseable {
    void close() throws Exception;
}

public interface Closeable extends AutoCloseable {
    @Override
    void close() throws IOException;
}
```

This is a **simplified API signature for learning**, not the full JDK source code; `IOException` is in `java.io`. The subinterface `Closeable` redeclares the method with a **narrower** checked exception type: `IOException` is a subclass of `Exception`.

```text
AutoCloseable  (java.lang)
  └─ close() throws Exception
       ▲
       │ extends
Closeable      (java.io)
  └─ close() throws IOException
       ▲
       ├─ InputStream / OutputStream
       ├─ Reader / Writer
       └─ many other I/O resource types
```

Not every `AutoCloseable` object is a `Closeable`. For example, many JDBC APIs such as `java.sql.Connection` implement `AutoCloseable` with the specific error `SQLException`; they are not required to implement `java.io.Closeable`.

Any class that implements `Closeable` is also an `AutoCloseable`, so it can appear in the resource declaration of `try-with-resources`.

## 2. Comparing the Core Contracts

| Comparison Point | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Package | `java.lang` | `java.io` |
| Relationship | General interface for closeable resources | `extends AutoCloseable` |
| `close()` signature | `void close() throws Exception` | `void close() throws IOException` |
| Typical context | I/O, JDBC, channels, self-managed transactions/scopes, objects needing cleanup | Primarily I/O streams and data sources/destinations |
| Calling `close()` multiple times | Not required to be idempotent; documentation **strongly encourages** making it idempotent | Contract: if already closed, calling it again **has no effect** |
| Used with `try-with-resources` | Yes | Yes, because it extends `AutoCloseable` |
| Checked exception seen from interface type | `Exception` | `IOException` |
| Can override `close()` with fewer exceptions? | Yes, e.g., `throws` nothing | Yes, e.g., `throws` nothing |

**Idempotent** for `close()` here means that calling it again after the resource has already been closed produces no additional observable effect under the close contract. `Closeable.close()` is required by its Javadoc to have no effect if the stream is already closed. For plain `AutoCloseable`, that is **not a strict requirement**, though a safe implementation should usually do so anyway.

Neither interface **promises** that every `close()` operation will always succeed. Even when closing fails, responsibility for resource state and ownership must still be clearly designed.

## 3. Why Does `try-with-resources` Require `AutoCloseable`?

Basic structure:

```java
try (Resource resource = createResource()) {
    useResource(resource);
}
```

This is an **illustrative pattern**, assuming `Resource implements AutoCloseable` and the related methods are already defined. Execution flow:

1. Java evaluates the `createResource()` expression to initialize the resource variable inside `(...)`.
2. If initialization succeeds, Java executes the `try` body.
3. When exiting the `try` body via normal Java control flow — normal completion, `return`, `throw`, `break`, or appropriate `continue` — Java calls `resource.close()`.
4. After the close step, the `try-with-resources` statement completes; if there are `catch` or `finally` clauses in the same construct, they execute according to their own rules, **after automatic closing has taken place**.
5. If an error occurs during closing, Java handles the primary exception and `suppressed exceptions` according to special rules.

Unlike manual `close()` calls, developers do not need to repeat the same release logic in every `catch` branch, `return` statement, or at the end of a method.

**Note:** `AutoCloseable` is a **type** requirement so that an object can be placed in the resource list. It does not automatically provide a closing mechanism when the object is garbage collected. Resources placed outside `try-with-resources` still need to be managed according to the API contract.

## 4. Java 17+ Example: Creating a Simple `AutoCloseable`

Save as `SimpleAutoCloseableDemo.java`:

```java
public class SimpleAutoCloseableDemo {
    static class Session implements AutoCloseable {
        private boolean closed;

        Session() {
            System.out.println("open session");
        }

        void work() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("session work");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close session");
            }
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.work();
        }
        System.out.println("after try");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SimpleAutoCloseableDemo.java
java SimpleAutoCloseableDemo
```

Deterministic output:

```text
open session
session work
close session
after try
```

`Session implements AutoCloseable`, so it can be declared in `try (...)`. The compiler automatically generates logic equivalent to an appropriate `finally` block to call `close()` upon completion. The actual signature `Session.close()` **declares no checked exceptions**, so `main()` does not need `throws Exception` just for automatically closing `Session`.

The example deliberately sets `closed = true` and only prints on the first close. This makes `close()` idempotent, even though the `AutoCloseable` interface does not require it. The `work()` method checks the state to reject using the resource after closing.

Do not manually call `session.close()` an extra time inside the `try` body just "to be sure." Once it is declared in the `try-with-resources` header, Java will call it when exiting the block; calling it manually can lead to a double-close in non-idempotent implementations.

## 5. How Do `throws Exception` and `throws IOException` Affect the Compiler?

The difference in `close()` signatures directly relates to the checked exception mechanism:

- `AutoCloseable.close()` is declared `throws Exception`. If the resource is viewed through the **static type `AutoCloseable`**, automatic closing can throw a checked `Exception`; the caller must handle or declare it accordingly.
- `Closeable.close()` is declared `throws IOException`. If the resource is viewed through the **static type `Closeable`**, the checked exception type from closing is narrower.
- A **concrete implementing class** is allowed to override `close()` **without throwing any checked exception**. When `try-with-resources` uses that exact concrete type, the compile-time obligation specifically related to closing can disappear.
- Exceptions from the **`try` body or the resource initialization call** are still checked separately. The `close()` signature does not remove obligations for those exceptions.

### Java 17+ Program: Same Action, Two `close()` Contracts

Save as `CloseContractDemo.java`:

```java
import java.io.Closeable;
import java.io.IOException;

public class CloseContractDemo {
    static class GeneralResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            System.out.println("general-close");
        }
    }

    static class IoResource implements Closeable {
        @Override
        public void close() throws IOException {
            System.out.println("io-close");
        }
    }

    static void usingGeneral() throws Exception {
        try (AutoCloseable resource = new GeneralResource()) {
            System.out.println("general-work");
        }
    }

    static void usingIo() throws IOException {
        try (Closeable resource = new IoResource()) {
            System.out.println("io-work");
        }
    }

    public static void main(String[] args) throws Exception {
        usingGeneral();
        usingIo();
    }
}
```

```bash
javac -encoding UTF-8 CloseContractDemo.java
java CloseContractDemo
```

Output:

```text
general-work
general-close
io-work
io-close
```

`usingGeneral()` declares `throws Exception` because the `AutoCloseable` reference has the signature `close() throws Exception`. `usingIo()` only needs `throws IOException` because `Closeable.close()` narrows the contract. In the demo, neither `close()` operation actually throws an error, but the **potential to throw according to the signature** is still checked at compile time.

The difference becomes clear when using a custom class:

```java
static class QuietResource implements AutoCloseable {
    @Override
    public void close() { }
}

static void useQuiet() {
    try (QuietResource resource = new QuietResource()) {
        System.out.println("work");
    }
}
```

This is an **illustrative method/nested-class snippet**, not a standalone runnable file. `useQuiet()` does not need `throws Exception` just because `QuietResource` implements `AutoCloseable`: the compiler knows the concrete `QuietResource.close()` declares no checked exceptions.

**Common design mistake:** storing resources everywhere via an `AutoCloseable` variable even when the actual resource has a narrower `close()` signature. This can force unnecessarily broad `Exception` declarations or catches. If the actual contract is I/O, using `Closeable` or the concrete type is usually more accurate.

## 6. When Does It Make Sense to Implement `Closeable` Yourself?

`Closeable` is suitable for classes representing a data source or destination that can be closed and may fail with I/O errors:

```java
import java.io.Closeable;
import java.io.IOException;

class TextChannel implements Closeable {
    private boolean closed;

    void send(String text) throws IOException {
        if (closed) {
            throw new IOException("channel closed");
        }
        System.out.println(text);
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            // In a real application: release the associated stream/socket.
        }
    }
}
```

This is a **valid illustrative class**, without a standalone `main`. `TextChannel` models a data source/destination and reports I/O errors as `IOException`. The `closed` state prevents misuse after closing. Repeated `close()` calls perform no new action, in the spirit of the `Closeable` contract.

Not every closeable object is I/O. If a class represents a transaction scope or a custom resource structure, `AutoCloseable` may be more appropriate. If you want the close contract to throw `SQLException`, you cannot choose `Closeable.close() throws SQLException` because `SQLException` is not a subclass of `IOException`. `AutoCloseable` allows designing that specialized exception.

## 7. Standard Library `Closeable` Example: `BufferedReader`

Types like `InputStream`, `OutputStream`, `Reader`, and `Writer` implement `Closeable`. Therefore, they can be used directly with `try-with-resources`. For a standalone example that does not need a file on disk, use `StringReader` as the character source and wrap it with `BufferedReader`.

Save as `ReaderDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReaderDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("alpha\nbeta"))) {
            System.out.println("line1=" + reader.readLine());
            System.out.println("line2=" + reader.readLine());
        }
        System.out.println("reader closed");
    }
}
```

```bash
javac -encoding UTF-8 ReaderDemo.java
java ReaderDemo
```

Output:

```text
line1=alpha
line2=beta
reader closed
```

In this example, `BufferedReader` is the **owning wrapper resource**, declared in the `try-with-resources` header. When `BufferedReader.close()` runs, it also closes the wrapped `StringReader` per the reader class's contract. Thus, there is no need to declare a separate `StringReader` resource just to close the same underlying reader again.

That does not mean every wrapper class in Java automatically takes responsibility for closing the resource passed into it. When using external libraries, **read the API's ownership contract** to know whether the wrapper closes the underlying object.

For real files, you can use `Files.newBufferedReader(path)` or `Files.newInputStream(path)` in `try-with-resources`; these APIs can throw `IOException` when opening, reading, and closing. Machine-dependent file sources should not be used in instructional examples with fixed stdout.

## 8. Multiple Resources: Initialized Left-to-Right, Closed in Reverse

With a list of multiple resources:

```java
try (
    Resource first = new Resource("A");
    Resource second = new Resource("B");
    Resource third = new Resource("C")
) {
    doWork();
}
```

This is an illustrative pattern, assuming the types already exist. Java **initializes A → B → C**, runs the `try` body, and then **closes C → B → A**. This LIFO order is useful when a later-created resource depends on an earlier-created one. A trailing `;` in the resource list is allowed, though not required.

Save as `CloseOrderDemo.java`:

```java
public class CloseOrderDemo {
    static class Step implements AutoCloseable {
        private final String name;

        Step(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Step a = new Step("A");
             Step b = new Step("B");
             Step c = new Step("C")) {
            System.out.println("body");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
```

Output:

```text
open A
open B
open C
body
close C
close B
close A
after
```

Each resource variable declared in `try (...)` is a single-assignment variable within that scope; it cannot be reassigned inside the `try` body. After the `try-with-resources` statement finishes, variables declared directly in the resource list are no longer in scope afterward.

## 9. If Opening the Second Resource Fails, What Happens to the First?

The Java specification guarantees that resources **already successfully initialized** in the same `try-with-resources` are closed if a subsequent resource **fails to initialize**. Execution does not need to enter the `try` body for the closing mechanism to take effect.

Save as `FailedOpenDemo.java`:

```java
import java.io.IOException;

public class FailedOpenDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name, boolean fail) throws IOException {
            this.name = name;
            System.out.println("init " + name);
            if (fail) {
                throw new IOException("open " + name + " failed");
            }
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false);
             Resource b = new Resource("B", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 FailedOpenDemo.java
java FailedOpenDemo
```

Output:

```text
init A
init B
close A
caught=open B failed
```

A finished initializing, so it is closed. B threw an exception right in the constructor before becoming a successfully initialized resource in `try-with-resources`, so Java **does not have a received B object on which to call `close()` automatically**. The `try` body does not run.

**Important limitation:** if a resource's constructor creates an internal resource and then fails before returning a complete object, that constructor/factory itself must clean up what it allocated. The outer `try-with-resources` can only automatically close resources that were successfully initialized and registered in its list.

## 10. Primary Exceptions and `suppressed exceptions`

A particular benefit of `try-with-resources` is preserving error traces when **both the `try` body and `close()`** fail.

- If the `try` body throws exception `E`, and then `close()` throws exception `C`, Java continues throwing **E as the primary exception**, while attaching **C to `E.getSuppressed()`**.
- If the `try` body completes normally but `close()` throws `C`, then `C` can become the primary exception propagated outward.
- If there are multiple resources and multiple `close()` calls fail, Java still attempts to close the remaining resources, and the additional errors are recorded in the `suppressed` list per the JLS mechanism.
- `getSuppressed()` **differs from `getCause()`**. Cause describes a causal relationship between exceptions; suppressed records additional exceptions retained while handling a primary exception.

### Java 17+ Program: Two `close()` Errors Accompanying One `try`-Body Error

Save as `SuppressedDemo.java`:

```java
public class SuppressedDemo {
    static class Faulty implements AutoCloseable {
        private final String name;

        Faulty(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
            throw new IllegalStateException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Faulty a = new Faulty("A");
             Faulty b = new Faulty("B")) {
            System.out.println("body");
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
```

Output:

```text
open A
open B
body
close B
close A
primary=work failed
count=2
suppressed=close B failed
suppressed=close A failed
```

Both resources are requested to close in the order B then A. The error from the `try` body remains the primary `IllegalArgumentException("work failed")`; the two close errors are attached in the order they occurred. There is no separate `catch` invocation for each suppressed exception.

If you remove the `throw new IllegalArgumentException("work failed")` statement in the `try` body, B's close error becomes the primary exception and A's close error is suppressed onto B's error. This is the case of **the `try` body succeeding while cleanup fails**.

Do not hide close errors with an empty `catch (Exception ex) { }`. In real systems, depending on severity, the application needs to record both the primary exception and the suppressed errors for investigation.

## 11. Order of `catch` and `finally` When Using `try-with-resources`

You can add `catch` and `finally` after a `try-with-resources` statement:

```java
try (Resource resource = openResource()) {
    useResource(resource);
} catch (IOException ex) {
    handleIoFailure(ex);
} finally {
    finishOperation();
}
```

This is a **syntax pattern**; the `Resource` type and methods must be defined with matching signatures. Ordering rules:

1. Initialize resources.
2. Run the `try` body if initialization succeeds.
3. Automatically close initialized resources in reverse order.
4. Select the first matching `catch` branch if an exception is currently being thrown.
5. Execute `finally` if present, before completing the transfer of control.

If an `IOException` occurs **during closing** while the `try` body threw no error, `catch (IOException ex)` can still catch this exception. If the `try` body throws `IllegalStateException` and `close()` throws an `IOException` that gets suppressed, `catch (IOException)` is **not** selected solely because of the suppressed exception.

A regular `finally` **does not replace** the automatic closing mechanism. A sensible resource management approach is usually to let `try-with-resources` handle closing, while `finally` performs final steps that do not belong to closing that same resource.

## 12. Reusing `final` or *Effectively Final* Variables Since Java 9

There are two ways to place a resource in the list:

**Declaring the resource in `try`:**

```java
try (MyResource resource = new MyResource()) {
    use(resource);
}
```

**Using a reference to an existing variable (Java 9+):**

```java
MyResource resource = new MyResource();
try (resource) {
    use(resource);
}
```

Both snippets are **illustrative patterns** with `MyResource implements AutoCloseable` and `use(...)` already defined. In the second form, the `resource` variable must be assigned and must be `final` or **effectively final**: not reassigned after its initial assignment.

An invalid example if you try to reassign before the block:

```java
MyResource resource = new MyResource();
resource = new MyResource();
try (resource) {       // Compile error: variable is not effectively final.
    use(resource);
}
```

This is an **intentionally non-compiling example**. In valid code, after the `try (resource)` block ends, the outer variable name `resource` may still be in scope, but **the object has already had `close()` called**. That the variable still references the object does not mean it is still safe to use.

Note on **ownership:** a resource should only be closed in the place responsible for owning its lifecycle. Using `try (existingResource)` means this code **is taking responsibility for closing** the object when exiting the block. If that resource must continue to be used by another owner, you should not arbitrarily put it into `try-with-resources`.

Additionally, Java 10+ allows using `var` when declaring a resource, such as `try (var resource = factory()) { ... }`, if type inference is valid. Using `var` can preserve the concrete type of the resource, thereby helping the compiler infer the exact checked exception types from `close()`.

## 13. `null` Resources and Special Cases

If a valid resource variable is initialized to `null`, Java **does not call `close()` for the `null` value**:

```java
try (MyResource resource = null) {
    System.out.println("body");
}
```

This is an illustrative snippet when `MyResource implements AutoCloseable`. It does not throw `NullPointerException` merely because the resource is `null`; however, if the `try` body calls `resource.someMethod()`, an NPE can still occur under normal rules.

Using a `null` resource is rarely good design; it can mask an initialization error. If a resource is optional, conditions and lifecycle should be designed explicitly.

**Do not over-assume that "any object with a `close()` method can be used in `try-with-resources`."** Java requires the resource's type to be a class or interface assignable to `AutoCloseable`. A custom class that has `void close()` but **does not implement `AutoCloseable`** will be rejected as a resource.

Intentionally non-compiling example:

```java
class FakeResource {
    void close() { }
}

class InvalidResourceDemo {
    void run() {
        try (FakeResource resource = new FakeResource()) {
            System.out.println("work");
        }
    }
}
```

To fix this, implement `AutoCloseable` or `Closeable` as appropriate and override `close()` with the right contract.

## 14. Principles for Implementing `close()` Safely

When designing your own resource class, you need to care about more than just an `implements AutoCloseable` clause.

### 14.1. Ensure Cleanup Actually Happens

`close()` must release resources per its contract: closing file handles, unregistering listeners, ending usage sessions, or returning allocated resources. **Do not create an empty `close()` just to make a type pass the compiler** if the object actually owns resources that need cleanup.

If multiple cleanup steps are needed, you must decide the order and how to preserve error information. One failing step must not necessarily skip all remaining steps.

### 14.2. Track Closed State and Avoid Repeated Closing

Although `AutoCloseable` does not require idempotency, its Javadoc strongly encourages it. `Closeable` explicitly requires that closing an already-closed stream has no effect.

Simple pattern:

```java
@Override
public void close() {
    if (closed) {
        return;
    }
    closed = true;
    releaseOwnedResources();
}
```

This is a **design pattern**, assuming an appropriate `closed` field and `releaseOwnedResources()` method. Marking before cleanup helps reduce the risk of re-entrancy or double-closing in some resource classes; however, you must design carefully if cleanup can fail partway through. For resources with complex lifecycles, a single boolean flag may not be enough to represent closing-in-progress, failed-close, or thread safety.

### 14.3. Do Not Turn `close()` Into a Place That Loses Important Exceptions

If `close()` can throw a checked exception, you should declare a **meaningful narrow type**, or declare no checked exception if it cannot fail. `AutoCloseable` permits `throws Exception`, but you should not abuse that to return arbitrary errors unrelated to the closing task.

According to the `AutoCloseable` Javadoc, avoid designing `close()` to throw `InterruptedException`: when it is suppressed due to another primary error, handling the interrupt status can become unpredictable. If cleanup can be interrupted, an appropriate contract and way to preserve the cancellation signal are needed.

### 14.4. Who Owns the Closing Responsibility?

Libraries often have multiple wrapper layers. If a wrapper owns the underlying stream/connection, closing the wrapper **may** close the underlying stream/connection. However, you cannot assume that for every library. Read the specific class documentation before letting multiple layers share closing ownership.

Things to avoid:
- Two components both claiming "ownership" and closing the same non-idempotent object.
- Returning a resource object that has already been closed inside a `try-with-resources` scope.
- Putting a shared object into a small call's `try-with-resources`, causing other users to receive a closed resource.
- Relying on finalizers, the garbage collector, or JVM shutdown instead of timely cleanup.

## 15. When Is `try-with-resources` Not Needed?

Not every object that implements `AutoCloseable` always holds an external resource. Some APIs share the interface because there are both cases that need closing and cases that do not.

For example, `java.util.stream.Stream` is related to `AutoCloseable` via `BaseStream`. A stream created from an I/O source like `Files.lines(path)` needs to be closed per the resource contract. But a purely in-memory stream, such as `List.of(1, 2, 3).stream()`, typically owns no file handles, so wrapping it in `try-with-resources` on its own is unnecessary.

Conversely, `Connection`, `PreparedStatement`, `ResultSet`, `BufferedReader`, or file streams in appropriate APIs usually have resources to release. Even when a resource throws no checked exceptions on close, `try-with-resources` can still be a clear way to define its lifecycle.

**Selection rule:** not "whenever it implements `AutoCloseable`, wrap it every time," but rather "when the current code is responsible for closing this resource and wants to guarantee cleanup along normal Java control flow, prefer `try-with-resources`."

## 16. Common Mistakes

| Mistake or Misconception | Reality and Fix |
| --- | --- |
| "`Closeable` is an interface completely separate from `AutoCloseable`." | False; `Closeable extends AutoCloseable`. |
| "Both `close()` methods declare `throws Exception`." | False; `Closeable.close() throws IOException`. |
| "A class with a method named `close` can automatically be used with `try-with-resources`." | False; the resource type must implement `AutoCloseable` directly or indirectly. |
| "`AutoCloseable.close()` is required to be idempotent." | False; it is only strongly encouraged. `Closeable.close()` has the contract that calling it again has no effect. |
| "If the second resource fails to open, the first resource is forgotten." | False; Java automatically closes previously initialized resources that succeeded. |
| "Closed in order A → B → C because they were declared that way." | False; closed C → B → A. |
| "`catch` runs before closing resources." | False; automatic closing is performed before the `catch`/`finally` of the same `try-with-resources`. |
| "A `close()` error always overwrites an error in the `try` body." | False; when a primary error already exists, close errors are usually stored in `getSuppressed()`. |
| "A suppressed error will automatically trigger a separate `catch`." | False; `catch` selection is based on the primary exception thrown. |
| "The variable is still in scope, meaning the resource is still open." | False; the resource may already have been closed upon exiting the block. |
| "`try-with-resources` guarantees `close()` runs even if the JVM is killed." | No; it relies on control flow still passing through Java's execution mechanism. |
| "No need to read the wrapper contract because Java knows to close all related components." | No; Java closes registered resources; ownership relationships inside a wrapper are an API contract. |
| "Just catch `IOException` for every `AutoCloseable`." | No; the checked exception type depends on the `close()` signature of the resource type and operations in the body. |

## 17. Code Review Checklist

When encountering an object with `close()`, check in order:

1. **Resource type:** does it implement `AutoCloseable`? Is it `Closeable` or a specialized class with a narrower `close()`?
2. **Ownership:** does the current method own and bear responsibility for ending the object's lifecycle?
3. **Usage:** can the resource be declared directly in `try (...)`, or can an existing `final`/effectively final variable be used since Java 9?
4. **Exceptions on open, use, and close:** what checked types does the API declare? Should they be caught locally or declared with `throws` to an outer layer?
5. **Dependency order:** if there are multiple resources, do the initialization and reverse-closing orders match the wrapper relationships?
6. **On failure:** are the primary exception and `getSuppressed()` preserved? Is `cause` lost when translating errors?
7. **Idempotency and reuse:** is the resource used after closing, or is there a risk of double-close?
8. **Recoverability:** if cleanup fails, does the system have an appropriate policy for logging, aborting the operation, or stopping the service?

A typical structure worth preferring:

```java
try (SomeCloseable resource = open()) {
    return process(resource);
} catch (IOException ex) {
    throw new DataAccessException("Cannot process resource", ex);
}
```

This is a **non-standalone illustrative pattern**, assuming `SomeCloseable implements Closeable`, `open()`/`process(...)` have appropriate signatures, and `DataAccessException` is an exception type with a constructor accepting `cause`. The resource is closed **before the `catch` branch of the same construct handles the error**. Wrapping the exception gives upper layers a meaningful contract while preserving the original error.

If `process(resource)` returns an object that still needs to use the resource after the method finishes (such as a lazy stream or an iterator directly backed by a file), closing right before `return` can render the result unusable. In that case, you must redesign ownership and lifecycle rather than applying the pattern mechanically.

## 18. Self-Check

**Q1.** What is the inheritance relationship between `Closeable` and `AutoCloseable`?  
`Closeable extends AutoCloseable`. Every `Closeable` can be used with `try-with-resources`.

**Q2.** How do the `close()` signatures on the two interfaces differ?  
`AutoCloseable.close() throws Exception`; `Closeable.close() throws IOException`.

**Q3.** Why might `try (AutoCloseable r = ...)` require `throws Exception` even if the actual object's close does not throw?  
Because compile-time checking relies on the **static type** and the `AutoCloseable.close()` signature, not just a single runtime behavior.

**Q4.** If A, B, and C are declared in the same `try (...)`, in what order are they closed?  
**C, B, A**, the reverse of the initialization order.

**Q5.** If initializing B fails after A has already been initialized, is A closed?  
**Yes**, A is automatically closed according to `try-with-resources` rules.

**Q6.** If the `try` body throws an error and `close()` throws another error, which error takes precedence?  
The `try`-body error is typically the **primary exception**; the close error is attached via `getSuppressed()`.

**Q7.** Is calling `close()` twice on an `AutoCloseable` always safe and without effect?  
**There is no general guarantee.** `AutoCloseable` encourages idempotency, whereas `Closeable` specifies that calling it again after already closed has no effect.

**Q8.** Can a class with `public void close()` that does not implement the appropriate interface be used in `try (...)`?  
**No**. Java checks that the resource's type is a subtype of `AutoCloseable`.

**Q9.** For `try-with-resources` with `catch` and `finally`, is the order "close → catch → finally" correct?  
**Correct in terms of phases**: if there is a matching `catch` branch, it runs after closing; `finally` runs after the catch phase, per Java semantics.

**Q10.** When using `try (existing)` since Java 9, what conditions must the `existing` variable meet?  
The variable must be previously assigned, be `final` or **effectively final**, and have an appropriate type. Exiting the block means the resource has been requested to close even though the variable name may remain in scope.

## Official References

- [Java SE 21 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html).
- [Java SE 21 API — `Closeable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html).
- [JLS Java SE 21 — §14.20.3 `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Key takeaway:** `AutoCloseable` is the general resource-closing contract; `Closeable` is a more specific I/O contract with `IOException` and idempotent `close()` behavior. Both enable `try-with-resources` to close resources in the right order, manage exceptions when cleanup fails, and make resource lifecycle ownership clear.
