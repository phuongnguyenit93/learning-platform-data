# Resource Closing Order and `suppressed exception` in Java

In Java I/O, files, sockets, streams, readers, writers, and many resource-access objects must be **closed promptly** to avoid leaking handles, file locks, connections, or buffered data. Closing can also fail: `close()` can throw an exception while flushing, finalizing a format, or releasing a resource.

`try-with-resources` solves two critical problems:

1. **Automatically closing in reverse order of declaration** for resources that were successfully initialized.
2. **Preserving the primary exception** and attaching errors thrown during closing to the **suppressed exceptions** list so the root cause is not masked.

Understanding these rules explains which exception `catch` receives, why a single failure can carry multiple related errors, and when you should not declare both a wrapper and its underlying stream together.

## 1. Which Objects Can `try-with-resources` Manage?

An object can be used in the resource header of `try` when its type implements `java.lang.AutoCloseable`.

- `AutoCloseable` declares `void close() throws Exception`; an implementation may narrow the exception type or throw no checked exception.
- `java.io.Closeable` extends `AutoCloseable` and declares `close() throws IOException`, so it is commonly seen on `InputStream`, `OutputStream`, `Reader`, and `Writer`.
- `Connection`, `Statement`, and `ResultSet` in JDBC also have resource-closing APIs, though transaction behavior requires checking their separate contracts: `close()` **must not be assumed to mean `commit()`**.
- A custom resource may manage locks, temporary files, memory regions, or application state; it does not have to be an I/O stream.

Basic syntax example:

```java
try (ResourceType resource = openResource()) {
    use(resource);
} // Java automatically calls resource.close() when leaving the block.
```

This is an **illustrative syntax pattern**, not a standalone program: `ResourceType`, `openResource()`, and `use(...)` represent application-defined types and methods.

`try-with-resources` was introduced in Java 7. Since Java 9, an existing resource variable can be used if it is `final` or *effectively final*:

```java
// Illustrative code; reader is already created and never reassigned.
BufferedReader reader = createReader();
try (reader) {
    System.out.println(reader.readLine());
}
```

In this example, `reader` is never reassigned, so it is valid in Java 17+. Even though the variable is created outside the `try` declaration, **the resource will still be closed when leaving the block**; do not use this pattern if the caller needs to keep the reader open.

## 2. Open Left to Right, Close Right to Left

Given:

```java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    doWork();
}
```

Java **evaluates initialization expressions from left to right**: `a`, then `b`, then `c`. Upon exiting the block, Java **closes successfully created resources in reverse order**: `c.close()`, `b.close()`, `a.close()`.

```text
Initialize: A  -->  B  -->  C
                            |
Run try body                v
Close:      A  <--  B  <--  C
```

If one `close()` throws an exception, Java **still attempts to close the remaining resources** registered in the same `try-with-resources`. This differs from careless `finally` blocks, where an exception during the first `close()` can skip subsequent close calls.

### Runnable Example: Observing Closing Order

```java
// CloseOrderDemo.java
public class CloseOrderDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B");
             Resource third = new Resource("C")) {
            System.out.println("work");
        }
    }
}
```

Save the code as `CloseOrderDemo.java`, and run on JDK 17+:

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Exact stdout:

```text
open A
open B
open C
work
close C
close B
close A
```

The same applies when the `try` body exits via `return`, `break`, or throws an exception: resources are still closed before control actually leaves the managed scope. Note that the final outcome can change if `close()` fails (see the error sections).

### Two Meanings of "Closing Order" to Distinguish

**The order across declared resources** follows the reverse-order rule of `try-with-resources`. **The closing order across wrapper layers** is governed by the wrapper's own `close()` logic.

Example:

```text
BufferedReader (outermost)
      |
InputStreamReader
      |
FileInputStream (descriptor-holding layer)
```

If you declare only the **outermost `BufferedReader`** as the resource, when it closes, the corresponding standard classes forward the close request down to wrapped layers. That is a **propagating close chain** inside a single `close()`, not three independent variables closed in reverse order by Java.

Avoid declaring both `FileInputStream` and wrappers over the same file unnecessarily: the wrapper already closes the underlying layer; TWR would then close the raw stream a second time. Many standard `Closeable` classes tolerate repeated closes, but you must not assume every custom implementation is idempotent.

## 3. What Are Primary Exceptions and Suppressed Exceptions?

A `try-with-resources` block can fail in **multiple places**:

1. While opening/initializing a resource.
2. While executing logic inside the `try` body (`read`, `write`, parsing, data processing...).
3. While closing one or more resources.

If the `try` body failed, that exception is typically the **primary exception**: the direct reason the task failed. If `close()` calls subsequently fail as well, Java does not lose the primary error; it attaches the close errors to `primary.getSuppressed()`.

API to inspect them:

```java
Throwable primary = ...; // Illustrative code: value caught by catch.
Throwable[] secondaryFailures = primary.getSuppressed();
```

`getSuppressed()` returns a `Throwable` array (which may be empty). Suppressed exceptions are **not synonymous** with an exception's cause:

- `getCause()` describes a causal relationship where one exception *wraps* or links to another error.
- `getSuppressed()` describes additional errors retained during error handling/cleanup.
- A single `Throwable` can have both a cause and suppressed exceptions; they are two **distinct** relationships.

Java automatically creates the suppressed relationship when executing `try-with-resources`; applications rarely need to call `addSuppressed()` manually for standard resource management.

## 4. If Both `try` Body and `close()` Fail: The Body's Error Is Primary

Consider the following program. Both resources throw `IOException` on close; the `try` body also throws another `IOException`.

```java
// BodyAndCloseFailureDemo.java
import java.io.IOException;

public class BodyAndCloseFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("work");
            throw new IOException("work failed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac BodyAndCloseFailureDemo.java
java BodyAndCloseFailureDemo
```

Stdout:

```text
work
close B
close A
primary=work failed
suppressed=close B failed
suppressed=close A failed
```

Sequence of events:

1. `A` is created, then `B` is created.
2. The `try` body throws `IOException("work failed")`: this is the **primary**.
3. Java calls `B.close()` first; it throws `"close B failed"` and this error is **suppressed** under the primary error.
4. Java continues calling `A.close()`; `"close A failed"` is **suppressed** next.
5. The outer `catch (IOException ex)` receives **`work failed`**, not a `close()` exception. `getSuppressed()` supplies both secondary errors.

This is why `try-with-resources` is more reliable than letting `finally` throw a new error that masks the original cause.

## 5. If the `try` Body Succeeds Yet Multiple `close()` Calls Fail

The primary exception does not always originate from the `try` body. If the business logic runs **normally**, yet closing operations fail:

- The first exception thrown in the **closing sequence** becomes primary.
- Exceptions from subsequent closes become suppressed exceptions of that primary.
- All registered resources are still attempted to be closed.

### Runnable Example

```java
// CloseOnlyFailureDemo.java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("work completed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

Stdout:

```text
work completed
close B
close A
primary=close B failed
suppressed=close A failed
```

`B.close()` runs first, so `"close B failed"` becomes primary. Even though closing `B` failed, `A.close()` is still called; `"close A failed"` is suppressed. Therefore, **never conclude success simply because the `try` body finished running**. A file write can fail during `close()` when remaining buffered data is flushed out.

### Quick Decision Table

| Scenario | Primary Exception | Suppressed Exceptions |
| --- | --- | --- |
| `try` body succeeds, all `close()` succeed | None | None |
| `try` body fails, all `close()` succeed | Body error | Empty |
| `try` body fails, multiple `close()` fail | Body error | `close()` errors in order of occurrence |
| `try` body succeeds, multiple `close()` fail | Error from the first `close()` in **closing order** | Subsequent close errors |
| Initializing a resource fails after prior resources succeeded | Initialization error | Errors when closing prior resources, if any |

When there is no primary error from the body or initialization, a `close()` error can escape even after the application finished its core work.

## 6. Mid-Initialization Failure: Only Successfully Created Objects Are Closed

Declarations in `try-with-resources` can also throw exceptions. If opening `A` succeeds yet creating `B` fails:

- The `try` body **does not run**.
- Only `A` was successfully initialized/registered, so Java attempts to close `A`.
- The error opening `B` is primary; any error closing `A` (if thrown) becomes suppressed.
- It must not try to close `B` as though initialization had completed.

### Runnable Example: Failure Opening B

```java
// InitializationFailureDemo.java
import java.io.IOException;

public class InitializationFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name + " failed");
        }
    }

    static Resource open(String name) throws IOException {
        System.out.println("open " + name);
        if ("B".equals(name)) {
            throw new IOException("open B failed");
        }
        return new Resource(name);
    }

    public static void main(String[] args) {
        try (Resource a = open("A");
             Resource b = open("B")) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac InitializationFailureDemo.java
java InitializationFailureDemo
```

Stdout:

```text
open A
open B
close A
primary=open B failed
suppressed=close A failed
```

There is no `body` line and no `close B`. Variable `b` never received a successfully constructed resource to register. In real code, if **the constructor/factory itself** acquires an internal resource and fails *before returning the object*, the factory must guarantee cleanup of what it acquired; the caller's `try-with-resources` only manages resources **that finished initializing and registering**.

This is an important distinction between **a resource created successfully that fails later** and **a resource that was never successfully created**.

## 7. What If a Resource Is `null`, or the Block Has `return`?

A valid resource expression can evaluate to `null` (though best avoided); in that case TWR **skips calling `close()`** on the `null` value.

```java
// Illustrative code: Resource implements AutoCloseable.
try (Resource first = maybeNullResource();
     Resource second = openResource()) {
    use(second);
}
```

If `first == null`, only `second` is closed. If `second` fails during initialization, `first` is only closed if it was non-null.

Furthermore, `close()` runs before the method completes a `return` inside the `try` body. If code prepares to `return` yet `close()` throws an exception, the method call can **terminate with an exception instead of returning a value**. Primary/suppressed rules still apply to exceptions actually thrown. Thus, never design a method to "return success" while ignoring writer close errors when data integrity matters.

## 8. Why Manual `finally` Blocks Easily Lose the Original Error

Consider this illustrative snippet that **should not be used as-is**:

```java
InputStream input = openInput();
try {
    process(input); // Can throw IOException("read failed")
} finally {
    input.close();   // Can also throw IOException("close failed")
}
```

The code assumes `openInput()` and `process(...)` already exist. If both `process(input)` and `input.close()` throw exceptions, the exception from `close()` in `finally` can **replace** the exception from the `try` body as it exits. Moreover, if multiple resources are opened manually and one `close()` fails, remaining close calls in `finally` may be skipped unless wrapped in separate `try` blocks.

Safer equivalent:

```java
try (InputStream input = openInput()) {
    process(input);
}
```

TWR preserves `read failed` as primary and adds `close failed` as suppressed. This does not mean close errors are "unimportant"; they are retained for logging and investigation without obscuring the initial failure.

If resources must be managed in a specialized way (such as multi-step manual cleanup), actively preserve the original exception and attempt each cleanup step. `Throwable.addSuppressed(Throwable)` can be used when you genuinely need to build a similar mechanism yourself, while avoiding attaching an exception as suppressed to itself and avoiding overusing it for normal control flow.

## 9. Relationship Between I/O Wrappers and Closing Order

An I/O pipeline often uses wrappers:

```java
// Illustrative code: path is a defined java.nio.file.Path.
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                Files.newOutputStream(path), StandardCharsets.UTF_8))) {
    writer.write("Xin chào");
}
```

Required imports are `java.io.BufferedWriter`, `java.io.OutputStreamWriter`, `java.nio.file.Files`, and `java.nio.charset.StandardCharsets`. In this chain:

1. `Files.newOutputStream(path)` opens a byte stream to the file resource.
2. `OutputStreamWriter` converts characters into UTF-8 bytes.
3. `BufferedWriter` holds a character buffer.
4. TWR closes the **outermost `BufferedWriter`**; standard wrappers finish writing any unwritten data and close the wrapped resource.

This is **one TWR variable spanning multiple I/O layers**. There is no need to declare a separate raw `OutputStream` and also add `BufferedWriter` to the resource list hoping to "close in the right order"; doing so can close the raw layer twice. Conversely, if you have **two independent resources** (such as an input stream and a separate output stream not wrapping each other), declare both and remember they close in **reverse declaration order**.

### `flush()` Differs from `close()`

- `flush()` requests pushing buffered data down to the next layer, while the resource **remains open**.
- `close()` ends the lifecycle, and standard output wrappers typically finish flushing/encoding before closing the underlying layer; these operations **can throw errors**.
- Successful `flush()`/`close()` does not by itself guarantee data was durably persisted to the storage device; that is a separate layer of I/O/OS guarantees.

A practical example: the `try` body writes via `BufferedWriter` without errors; upon leaving the block, `close()` forces remaining buffered data to the file. If the actual write fails at that moment, `close()` can throw `IOException`. Do not log errors only from `writer.write(...)` and assume closing always succeeds.

## 10. Ownership: Whoever Owns the Resource Decides Closing

`try-with-resources` **always closes** the resources you place in its managed list upon exiting the block. That is only sound design if that code scope **owns** them.

| Scenario | Approach |
| --- | --- |
| Method opens a file itself to read/write | Use TWR, typically on the outermost wrapper created by the method |
| Method receives `InputStream` from caller for temporary processing | Do not close it unless the contract transfers ownership |
| Using `System.in`/`System.out` from multiple places | Avoid closing wrappers around standard streams in helpers because `close()` can propagate to the shared stream |
| A `Closeable` shared across multiple tasks | Only the owner closes it after all tasks complete |
| An object passed by caller requesting the method to close it | May use TWR, but document the ownership-transfer contract explicitly |

Illustrative example:

```java
// Function borrows reader: caller manages lifecycle.
static String firstLine(BufferedReader borrowed) throws IOException {
    return borrowed.readLine();
}
```

Do not put `borrowed` into `try (borrowed)` inside the helper unless closing is authorized. Conversely, for internally created resources, TWR ensures cleanup even when errors occur.

**Note on transactions:** Closing a `Connection` or data-access session can release resources, yet commit/rollback handling and their errors must follow the API contract. Do not treat TWR's automatic closing rule as a transaction commit mechanism.

## 11. `AutoCloseable` and `Closeable`: Exception Scope

Two related interfaces with different signatures:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

```java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
```

These are **condensed signatures for explanation**, not code to redefine in your project.

Because `AutoCloseable.close()` may declare `Exception`, code using a generic `AutoCloseable` resource may need `catch (Exception)` or `throws Exception`. `Closeable.close()` restricts the checked exception to `IOException`, which is convenient for Java I/O. If a specific `close()` method declares no checked exception, the compiler will not require `throws/catch` solely for closing.

The `AutoCloseable` documentation **does not require every implementation to be idempotent**. `Closeable`'s contract specifies that closing again has no further effect, yet you must not assume the same for a custom wrapper implementing only `AutoCloseable`. Custom resources need clear definitions for repeated-close behavior, post-close state, and cleanup exceptions.

### Can an Exception Have Suppression Disabled?

Normally, exceptions thrown while closing are added to the primary exception via TWR mechanics. However, `Throwable` has a specialized constructor allowing **suppression to be disabled** for an exception instance. Thus `getSuppressed()` can be empty even after suppressed additions in unusual configurations. For `IOException` and standard exceptions in our examples, suppression is enabled as normal.

That is an advanced corner case and does not change normal `try-with-resources` rules in Java I/O.

## 12. Logging, Catching Errors, and Testing Properly

### Only an Outer `catch` Around TWR Sees Close Errors

A typical structure:

```java
try (BufferedReader reader = openReader()) {
    consume(reader);
} catch (IOException e) {
    log(e);
}
```

This is illustrative code with application-provided `openReader()`, `consume()`, and `log()`. When `catch` wraps the entire `try-with-resources` block, it receives both `try`-body errors and close errors (depending on exception types).

If you place `catch` **inside** the `try` body wrapping only the read calls, it cannot handle close errors occurring **after** that body finishes. To observe cleanup failures, place the handler outside the closing scope or let the exception propagate to the caller.

### Do Not Inspect Only `getMessage()`

Using `printStackTrace()` or a logger capable of logging the **full `Throwable` object** typically displays suppressed exceptions. If a logging system stores only messages, iterate over `getSuppressed()`:

```java
// Illustrative code inside a catch block, with e as Throwable.
System.err.println("primary: " + e);
for (Throwable suppressed : e.getSuppressed()) {
    System.err.println("suppressed: " + suppressed);
}
```

When investigating, distinguish the initial read/write failure, flush/close failures, errors opening a subsequent resource, and cleanup order. If nested close errors occur inside a custom wrapper, suppressed exceptions may also appear at different levels in the exception tree; logging tools should preserve the `Throwable` structure.

### Minimum Test Suite

1. Open and close three resources with no errors: verify left-to-right open order and right-to-left close order.
2. `try` body throws an exception, all `close()` calls succeed: verify primary is the body's error.
3. `try` body fails and two `close()` calls fail: verify primary remains the body's error and `suppressed` contains both close errors.
4. `try` body succeeds yet two `close()` calls fail: verify the first close error is primary and the remaining one is suppressed.
5. `A` succeeds, `B` fails to create: verify body does not run, `A` closes, and `A`'s close error is suppressed.
6. `null` resource: verify no `close()` call occurs on null.
7. Buffered writer wrapper: verify closing the outermost wrapper completes output and close errors are surfaced.
8. Caller-owned stream: verify helper does not close resources outside its ownership scope.

## 13. Common Mistakes

| Mistake | Consequence | Proper Practice |
| --- | --- | --- |
| Assuming closing order matches declaration order | Misunderstanding cleanup flow | TWR closes in **reverse declaration order**. |
| Thinking one `close()` failure skips remaining resources | Misunderstands TWR mechanics | TWR still attempts to close remaining initialized resources. |
| Thinking every close error becomes primary | Loses business-logic failure context | When body/init already failed, close failures are **suppressed**. |
| Checking only `getCause()` for all errors | Misses suppressed errors | Also check `getSuppressed()`. |
| Using naive `finally` to close and throwing another error | Can mask the `try` body error | Prefer TWR. |
| Declaring both wrapper and raw stream as resources when wrapper closes raw | Duplicate close and confusing ownership | Put TWR on the outermost wrapper when it owns the source. |
| Closing a reader passed in by the caller | Breaks shared stream | Close only resources you own or received ownership transfer for. |
| Assuming `try` body completing means file write succeeded | Errors can happen at flush/close | Handle close errors and observe exceptions. |
| Assuming `close()` also means `commit()` | Can break transaction semantics | Use transaction APIs per contract. |
| Logging only `exception.getMessage()` | Hides suppressed errors | Log the full `Throwable` or iterate suppressed exceptions. |

## 14. Self-Check

**Question 1.** In what order does `try (A a = ...; B b = ...; C c = ...)` close when all three were created successfully?

**Answer:** `c.close()`, `b.close()`, `a.close()`.

**Question 2.** The `try` body throws `IOException("body")`, then `B.close()` and `A.close()` both throw errors. Which primary exception does `catch` receive?

**Answer:** The `"body"` error; the `B` and `A` close errors are in `getSuppressed()` in order of occurrence.

**Question 3.** The `try` body succeeds, `B.close()` throws an error, and then `A.close()` also throws an error. Which error is primary?

**Answer:** `B`'s close error, because `B` closes first; `A`'s close error is suppressed under `B`'s error.

**Question 4.** `A` is created successfully, then creating `B` fails. Is `B` automatically closed?

**Answer:** No successfully initialized `B` exists to close; Java closes `A`, and any error closing `A` is recorded as suppressed on the error opening `B`.

**Question 5.** Do `getCause()` and `getSuppressed()` mean the same thing?

**Answer:** No. Cause expresses causal/wrapping relationships; suppressed holds additional errors occurring during cleanup or cases explicitly added by the application.

**Question 6.** A `BufferedWriter` wraps an `OutputStreamWriter` wrapping a `FileOutputStream`. When the method owns the entire chain, which resource do you declare in TWR?

**Answer:** Usually only the **outermost** writer, since `close()` on standard wrappers propagates down and closes underlying layers.

**Question 7.** A helper only borrows the caller's `InputStream`; should it place it in TWR?

**Answer:** No, unless the contract grants closing responsibility to the helper.

**Question 8.** Why must we care about `close()` errors even when `write()` threw no error?

**Answer:** A writer may still hold data in its buffer or encoder state; flushing/finalizing on close can be the moment an I/O error surfaces.

**Key Takeaway:** **TWR initializes left to right and closes right to left.** If an error already occurred in the `try` body or during initialization, `close()` errors are preserved as **suppressed exceptions** (under standard suppression rules). If the body succeeds and multiple closes fail, **the first close error to occur** is primary, and subsequent close errors are suppressed. Close only the resources you own and always inspect `getSuppressed()` when investigating failures.
