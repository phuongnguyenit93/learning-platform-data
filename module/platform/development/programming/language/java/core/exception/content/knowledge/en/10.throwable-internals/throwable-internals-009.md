# `addSuppressed` and `getSuppressed` in Java — Preserving All Exceptions During Cleanup

## 1. Lesson Objectives

In Java, an operation can **fail the first time** while performing work, and then **fail a second time** when closing a file, stream, socket, or other resource. If only one exception is propagated and the other is discarded, diagnostics will lack critical evidence. `Throwable.addSuppressed(Throwable)` and `Throwable.getSuppressed()` solve the problem of preserving **additional exceptions** alongside the **primary exception**.

Since Java 7, `try-with-resources` has used the suppressed exceptions mechanism to retain resource-closing failures without masking the original exception from the body. Developers can also call `addSuppressed` in manual cleanup code when there is a clear reason to do so.

You will learn:

- The difference between a **primary exception**, a **suppressed exception**, and a **`cause`**.
- How to call `addSuppressed`/`getSuppressed` on `Throwable` and read the exception list.
- The order of primary and suppressed exceptions when one or more resources fail together.
- Behavior when there are no suppressed exceptions, when passing `null`, when adding self, and when adding multiple exceptions.
- How to disable suppression via the protected constructor of `Throwable`/`Exception` and its impact on the API.
- The relationship with `try-with-resources`, `close()`, exceptions from resource initialization, `catch`/`finally`, and `printStackTrace`.
- Common mistakes that lose the root cause and how to preserve error information at the application layer.

The standalone examples use Java 17+; `stdout` results are explicitly noted. Cases that intentionally cause compilation errors or are only code snippets will be marked.

## 2. Three Types of Exception Links: Primary, Suppressed, and Cause

Consider a file-processing program:

```text
Resource opened successfully
       |
       v
Reading data fails: IOException("read failed")    <-- primary
       |
       v
Closing resource also fails: IOException("close failed")
       |
       v
try-with-resources keeps "read failed" as primary
and attaches "close failed" to the suppressed list
```

The primary exception is the object propagated to `catch` or the caller. A suppressed exception is **attached to the primary object**, rather than being thrown in place of the primary exception. You can inspect them via `primary.getSuppressed()`.

Distinguishing the concepts:

| Relationship | API | Typical Meaning |
| --- | --- | --- |
| **Primary exception** | The object currently being handled by `throw`/`catch` | The main failure that caused the current operation to fail |
| **Cause** | `getCause()`, constructors taking a cause, `initCause(...)` | A prior exception that **led to** or was wrapped by the current exception |
| **Suppressed** | `addSuppressed(other)`, `getSuppressed()` | An **additional** failure to retain without replacing the primary exception |

For example: reading a configuration throws `IOException("read")`; closing the source throws `IOException("close")`. The close failure is typically a suppressed exception of the read failure. Conversely, if you intentionally convert a `NumberFormatException` into a `ParseException` to report a parsing error, `NumberFormatException` is typically the **cause** of `ParseException`.

There is no rule that "every subsequent exception automatically becomes suppressed": Java automatically performs attachment in specified constructs, most notably `try-with-resources`. A manual `finally` block does not automatically add a suppressed exception if it throws another exception.

## 3. Two Methods on `Throwable`

### 3.1. `addSuppressed(Throwable exception)`

API declaration:

```java
public final synchronized void addSuppressed(Throwable exception)
```

This method appends the `exception` object to the suppressed list of **the receiver object**, if suppression is enabled for that object.

Example:

```java
Throwable primary = new IllegalStateException("work failed");
Throwable cleanup = new java.io.IOException("cleanup failed");

primary.addSuppressed(cleanup);
```

This is a runnable illustration when placed inside a Java method. After the call, `primary` is still `IllegalStateException("work failed")`; `cleanup` is in `primary`'s set of additional exceptions.

Key behaviors:

- Does not change `getMessage()`, `getCause()`, or the runtime type of the primary object.
- Does not perform a `throw` itself; the method only mutates the attached metadata.
- Multiple suppressed objects can be added, and the insertion order can be observed when calling `getSuppressed()`.
- You cannot add the primary object itself to its own suppressed list.
- You cannot pass `null` as the argument.
- If suppression was **disabled** when constructing the primary object, a valid call stores no additional exceptions.
- You do not need to—and should not—wrap a suppressed exception in a meaningless `RuntimeException` just for type compatibility: the parameter type is `Throwable`.

### 3.2. `getSuppressed()`

Declaration:

```java
public final synchronized Throwable[] getSuppressed()
```

This method returns an **array** containing the recorded suppressed objects. It does not return `null` when the list is empty.

```java
Throwable[] secondaryFailures = primary.getSuppressed();
for (Throwable failure : secondaryFailures) {
    System.out.println(failure.getClass().getSimpleName()
            + ": " + failure.getMessage());
}
```

This is a code snippet assuming `primary` has already been declared.

Rules to remember:

- If there are no additional exceptions, the array length is `0`.
- The array is **a copy representing the list at the time of the call**, not direct write access to the internal list.
- The array contains **references to the `Throwable` objects**, not deep copies of each exception. Mutating an exception object's state (if its API allows) can be seen through multiple references.
- To add a suppressed exception, call `addSuppressed(...)`; do not modify an element of the array returned by `getSuppressed()`.
- `getSuppressed()` can be called multiple times; each call reflects the state recorded at that point in time.

Every `Exception` and `Error` inherits from `Throwable` and therefore has both methods; there is no need to cast to a specific subclass.

## 4. Complete Example: Manually Adding and Reading Suppressed Exceptions

Create the file **`ManualSuppressedDemo.java`**:

```java
import java.io.IOException;

public class ManualSuppressedDemo {
    public static void main(String[] args) {
        IllegalStateException primary =
                new IllegalStateException("operation failed");

        primary.addSuppressed(new IOException("close stream"));
        primary.addSuppressed(new IOException("release channel"));

        System.out.println("primary=" + primary.getMessage());
        System.out.println("count=" + primary.getSuppressed().length);

        for (Throwable suppressed : primary.getSuppressed()) {
            System.out.println("suppressed=" + suppressed.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac ManualSuppressedDemo.java
java ManualSuppressedDemo
```

Exact `stdout`:

```text
primary=operation failed
count=2
suppressed=close stream
suppressed=release channel
```

Explanation:

1. `primary` is the work failure created first.
2. Each `addSuppressed` attaches **another exception object** to `primary`.
3. `getSuppressed()` returns two elements in the order they were added.
4. `primary` retains its type `IllegalStateException` and message `operation failed`; secondary failures do not take the primary failure's place.

In real applications, only call `addSuppressed` when the exceptions genuinely relate to **the same failed operation** and preserving the primary exception is intentional and justified.

## 5. How Does `try-with-resources` Automatically Create Suppressed Exceptions?

Illustration:

```java
try (AutoCloseable resource = acquire()) {
    work(); // Throws the primary exception.
}
```

This is a **code snippet**; you must declare `acquire()`, `work()`, and catch/declare the corresponding checked exception types. Suppose the body throws exception A, and then `resource.close()` throws exception B. `try-with-resources` preserves A as the primary exception and adds B to `A.getSuppressed()`.

This differs from careless manual closing:

```java
try {
    work();
} finally {
    resource.close(); // If this also throws, it can mask the work() exception.
}
```

This is also an illustrative snippet. `finally` still runs when the `try` block throws, but a new exception from `close()` can **replace** the earlier exit reason, causing exception A to be masked if not handled explicitly.

TWR implements the exception-management logic specified in the Java language: **guaranteeing resource closure and retaining information about close failures** via the primary/suppressed relationship.

### 5.1. Runnable Example: Body Failure and Close Failure

Create the file **`BodyAndCloseFailureDemo.java`**:

```java
import java.io.IOException;

public class BodyAndCloseFailureDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing resource");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            System.out.println("doing work");
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException failure) {
            System.out.println("primary=" + failure.getMessage());

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac BodyAndCloseFailureDemo.java
java BodyAndCloseFailureDemo
```

`stdout` result:

```text
doing work
closing resource
primary=body failed
suppressed=close failed
```

Execution flow:

- The body throws `IllegalStateException("body failed")`. This is the reason the block terminates abruptly.
- When leaving TWR, Java calls `close()`; the line `closing resource` is printed.
- `close()` throws `IOException("close failed")`. Because a primary exception already exists, TWR attaches the close failure to `getSuppressed()` on the `IllegalStateException`.
- The handler receives **`IllegalStateException`**, not `IOException`.
- The `IOException` object still retains its full message, stack trace, and its own cause when stored in the suppressed list.

Do not write `catch (IOException)` to catch the close failure separately in this example: the close failure has become a suppressed exception of the primary and must be inspected through the primary.

## 6. If the Body Succeeds, an Exception from `close()` Is the **Primary Exception**

Not every exception from `close()` is suppressed. If the body completes normally, while closing the resource fails, the close failure **propagates directly**.

Create the file **`CloseOnlyFailureDemo.java`**:

```java
import java.io.IOException;

public class CloseOnlyFailureDemo {
    static class BrokenClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("cannot close");
        }
    }

    public static void main(String[] args) {
        try (BrokenClose resource = new BrokenClose()) {
            System.out.println("work succeeded");
        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);
        }
    }
}
```

```bash
javac CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

`stdout`:

```text
work succeeded
closing
primary=cannot close
suppressed count=0
```

There was no prior work exception, so `IOException("cannot close")` becomes the primary exception. Because it is the only failure, `getSuppressed()` returns an empty array.

This is why when logging TWR failures you should not assume that **every `IOException` from `close()` is stored under suppressed**. You need to determine the execution path and the exception object that escaped.

## 7. Multiple Resources: Closing Order and the Suppressed List

TWR closes resources in the **reverse order** of how they appear in the resource specification. When multiple `close()` calls fail, the order in `getSuppressed()` reflects the sequence in which they were attached during closing.

### 7.1. Body Throws, Both Resources Fail to Close

Create the file **`MultipleSuppressedDemo.java`**:

```java
import java.io.IOException;

public class MultipleSuppressedDemo {
    static class Resource implements AutoCloseable {
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
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {

            System.out.println("body");
            throw new IllegalArgumentException("body failed");

        } catch (IllegalArgumentException failure) {
            System.out.println("primary=" + failure.getMessage());

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac MultipleSuppressedDemo.java
java MultipleSuppressedDemo
```

`stdout`:

```text
body
close second
close first
primary=body failed
suppressed=close second failed
suppressed=close first failed
```

Exact sequence:

1. `first` is created, then `second`.
2. The body throws `IllegalArgumentException("body failed")` as the primary exception.
3. Java calls `second.close()` **first**, recording `IOException("close second failed")` as suppressed.
4. Java calls `first.close()`, recording `IOException("close first failed")` as the next suppressed exception.
5. `catch` receives the body failure and reads the list of two additional exceptions in the order they were recorded.

Another resource might close successfully; in that case, no corresponding suppressed exception is added. Closing order does not depend on the order in which resources are used in the block body.

### 7.2. Body Succeeds, Both Closes Fail

Create the file **`CloseOrderPrimaryDemo.java`**:

```java
import java.io.IOException;

public class CloseOrderPrimaryDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException(name + " close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {

            System.out.println("body succeeded");

        } catch (IOException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed count="
                    + failure.getSuppressed().length);

            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac CloseOrderPrimaryDemo.java
java CloseOrderPrimaryDemo
```

`stdout`:

```text
body succeeded
close second
close first
primary=second close failed
suppressed count=1
suppressed=first close failed
```

Closing `second` fails first; at that moment there is no primary exception from the body. Therefore `second`'s close failure becomes primary, and `first`'s subsequent close failure is attached as suppressed. This explains why **suppressed placement depends on order and timing of failures**, not just which API throws the exception.

### 7.3. Exception During Second Resource Initialization

Another noteworthy scenario:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    work();
}
```

This is an **illustrative snippet**. If `openSecond()` throws after `first` has been initialized successfully, TWR will close `first`. If `first.close()` also throws, the close failure can be attached as suppressed to `second`'s initialization failure. This rule preserves the original failure **during the initialization phase**, not only failures inside the body.

### 7.4. Do Not Equate Suppressed Order with a Global Timeline

A `Throwable` object can have suppressed exceptions added manually at any appropriate stage. Therefore, the suppressed list is not an immutable timeline of the entire application. It only reflects the objects recorded through the corresponding mechanism. To determine root causes, inspect the message, stack trace, cause, context, and resource history.

## 8. API Misuse: Cannot Self-Suppress or Pass `null`

`Throwable.addSuppressed` validates its input to prevent nonsensical error structures.

### 8.1. Adding Self: `IllegalArgumentException`

```java
Throwable failure = new IllegalStateException("root");
failure.addSuppressed(failure); // Error: self-suppression.
```

This is a snippet with an intentional runtime error. A primary exception cannot be a suppressed exception of itself. A self-referential structure would be very difficult to interpret when printing a stack trace, and Java actively prevents direct self-suppression.

### 8.2. Adding `null`: `NullPointerException`

```java
Throwable failure = new IllegalStateException("root");
failure.addSuppressed(null); // Error: null is not a valid Throwable.
```

This is a snippet that intentionally causes a runtime error. The suppressed argument must be a non-null `Throwable` object.

### 8.3. Runnable Example: Testing Both Cases

Create the file **`SuppressedValidationDemo.java`**:

```java
public class SuppressedValidationDemo {
    public static void main(String[] args) {
        IllegalStateException root =
                new IllegalStateException("root");

        try {
            root.addSuppressed(root);
        } catch (IllegalArgumentException failure) {
            System.out.println("self: "
                    + failure.getClass().getSimpleName());
        }

        try {
            root.addSuppressed(null);
        } catch (NullPointerException failure) {
            System.out.println("null: "
                    + failure.getClass().getSimpleName());
        }

        System.out.println("count=" + root.getSuppressed().length);
    }
}
```

```bash
javac SuppressedValidationDemo.java
java SuppressedValidationDemo
```

`stdout`:

```text
self: IllegalArgumentException
null: NullPointerException
count=0
```

Both additions fail; `root`'s suppressed list remains empty. Do not "work around" this by catching and ignoring the API error: the right thing to do is **not pass `null` and not self-reference** in the first place.

**Subtle point:** the restriction is against adding **the receiver object itself**. Java does not require every suppressed object to have a different type or message. An exception can have the same type and message as another exception and still be a valid suppressed object.

## 9. `getSuppressed()` Returns an Empty Array and Does Not Let the Caller Mutate the Internal List

To iterate safely:

```java
for (Throwable secondary : failure.getSuppressed()) {
    // Log or analyze the secondary cause.
}
```

This is an illustrative snippet where `failure` is a `Throwable`. There is no need to check `getSuppressed() != null`; a normal object with no suppressed exceptions returns a zero-length array.

### Runnable Example: Modifying the Returned Array Does Not Modify the Suppressed List

Create the file **`SuppressedArraySnapshotDemo.java`**:

```java
import java.io.IOException;

public class SuppressedArraySnapshotDemo {
    public static void main(String[] args) {
        Exception primary = new Exception("main");
        primary.addSuppressed(new IOException("original"));

        Throwable[] snapshot = primary.getSuppressed();
        snapshot[0] = new IOException("replacement");

        System.out.println("snapshot="
                + snapshot[0].getMessage());
        System.out.println("stored="
                + primary.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac SuppressedArraySnapshotDemo.java
java SuppressedArraySnapshotDemo
```

`stdout`:

```text
snapshot=replacement
stored=original
```

The returned array is an independent snapshot of **element slots**, so assigning to `snapshot[0]` does not change the primary's internal array. However, the elements of the original snapshot are still references to the actual `Throwable` objects; if you call `snapshot[0].addSuppressed(...)` before replacing the element, you are mutating that actual exception object.

Also, do not cache the snapshot array expecting it to update automatically if `primary` gains new suppressed exceptions. To see new data, call `getSuppressed()` again.

## 10. Distinguishing `getCause()` and `getSuppressed()`

The two APIs serve **two different directions of linkage**. Both can be combined on the same exception object.

Create the file **`CauseVsSuppressedDemo.java`**:

```java
import java.io.IOException;

public class CauseVsSuppressedDemo {
    public static void main(String[] args) {
        IllegalArgumentException parseCause =
                new IllegalArgumentException("invalid number");

        IOException failure =
                new IOException("cannot import", parseCause);
        failure.addSuppressed(
                new IllegalStateException("temporary file cleanup failed"));

        System.out.println("primary=" + failure.getMessage());
        System.out.println("cause=" + failure.getCause().getMessage());
        System.out.println("suppressed="
                + failure.getSuppressed()[0].getMessage());
    }
}
```

```bash
javac CauseVsSuppressedDemo.java
java CauseVsSuppressedDemo
```

`stdout`:

```text
primary=cannot import
cause=invalid number
suppressed=temporary file cleanup failed
```

**Interpretation:**

- `IOException("cannot import", parseCause)` is the current failure, with a **cause** explaining the deeper parsing failure.
- `addSuppressed(...)` retains an additional failure that occurred during cleanup.
- `getCause()` returns **a single** cause (or `null`), whereas `getSuppressed()` returns **an array** of additional failures (possibly empty).
- Suppressed does not replace cause; a suppressed exception can itself have its own cause and suppressed exceptions.

Example diagnostic tree:

```text
IOException: cannot import                 [primary]
  Caused by: IllegalArgumentException     [cause]
    invalid number
  Suppressed: IllegalStateException       [suppressed]
    temporary file cleanup failed
```

This is a **conceptual diagram**, not the exact `printStackTrace()` output of any specific JVM version. Actual stack trace formatting may indent differently, elide duplicate frames, or lay out sections differently.

Do not build a cause chain or suppressed list just to get a pretty stack trace. Choose the linkage based on the nature of the failure.

## 11. Disabling Suppression: An Empty List Does Not Prove Cleanup Succeeded

An exception subclass can call the `protected` constructor with `enableSuppression=false`. In that case, `addSuppressed(validThrowable)` can still be called validly, but it **does not store** the secondary exception, and `getSuppressed()` always returns an empty array on that object.

~~~java
class NoSuppressionFailure extends RuntimeException {
    NoSuppressionFailure(String message) {
        super(message, null, false, true);
    }
}
~~~

In `try-with-resources`, if the body throws `NoSuppressionFailure` and then `close()` also fails, closing **can still have failed** even though the primary exception contains no suppressed exceptions. Therefore, do not treat `getSuppressed().length == 0` as confirmation that all cleanup steps succeeded.

Do not disable suppression out of habit. Combinations of `enableSuppression`/`writableStackTrace`, how constructors apply those flags, and their effects on cause/stack trace are covered thoroughly in the `Throwable` configuration lesson; here, just remember the boundary: the API for reading secondary exceptions cannot recover a secondary exception that the primary object **chose not to store**.

## 12. If a Resource Is Closed Multiple Times, Are Suppressed Exceptions Deduplicated?

`addSuppressed` is not a unique `Set`. Aside from direct self-suppression and a `null` argument, the API does not use message, class, or stack trace to deduplicate by content.

Example:

```java
Throwable primary = new IllegalStateException("work");
Throwable cleanup = new java.io.IOException("cleanup");
primary.addSuppressed(cleanup);
primary.addSuppressed(cleanup);
```

This is a valid snippet: the same **`cleanup` object** is added twice. The list reflects both additions. Consequently:

- Do not interpret the number of suppressed elements as the number of unique resources if code might add the same exception multiple times.
- Avoid manually adding an exception multiple times when it has already been recorded automatically by TWR.
- Do not use `addSuppressed` as a substitute for business-level deduplication.

When you see two identical cleanup error lines in logs, inspect resource management and where `addSuppressed` is called rather than jumping to the conclusion that the JVM "closed the resource twice" without evidence.

## 13. How Do Stack Traces Display Suppressed Exceptions?

`Throwable.printStackTrace()` is designed to display both the cause structure and suppressed exceptions. In common textual stack traces, a suppressed exception appears as an indented entry with a prefix such as `Suppressed:` under its enclosing exception; causes typically appear with the `Caused by:` label.

Snippet example:

```java
try (FailingResource resource = acquire()) {
    performWork();
} catch (Exception failure) {
    failure.printStackTrace();
}
```

This is an **illustrative snippet** requiring appropriate definitions of `FailingResource`, `acquire()`, and `performWork()`. `printStackTrace()` typically writes to `System.err`, so you should not assert on the exact full stack trace text like the fixed `stdout` in the runnable examples.

When debugging, read:

1. The type and message of the **primary**.
2. The stack frames showing where the primary failure originated.
3. `Caused by` to trace deeper causes.
4. `Suppressed` to see failures during cleanup or additional operations.
5. The resource path and related open/close policies.

Every suppressed exception is a `Throwable` that can have its own stack trace and cause. Do not log only `failure.getMessage()` if the application needs full forensic detail; structured logging or printing the entire throwable is usually more useful, while following security rules so sensitive data is not exposed.

### "Suppressed" Does Not Mean the Error Was Safely Handled

The name "suppressed" means the exception **was not thrown as the primary** in that situation. It does not guarantee that cleanup succeeded or that the consequences can be ignored. Failing to close an output file can mean data was not properly flushed; that failure still matters operationally and must be examined.

## 14. When Should You Call `addSuppressed` Manually?

`try-with-resources` already manages most `AutoCloseable` resource cases. Manual usage is typically only needed when a coordination layer performs **multiple cleanup operations that cannot be cleanly expressed with TWR**, and wants to preserve the primary exception instead of letting a cleanup failure obscure it.

Conceptual pattern example:

```java
try {
    doWork();
} catch (java.io.IOException primary) {
    try {
        cleanup();
    } catch (java.io.IOException cleanupFailure) {
        primary.addSuppressed(cleanupFailure);
    }
    throw primary;
}
```

This is an **illustrative snippet** requiring `doWork()`/`cleanup()` to be defined, the enclosing method to catch/declare `IOException`, and cleanup rules on the success path as well. The goal is to show how to preserve the original failure when **both operations fail**; it is **not** a complete template replacing `finally` or `try-with-resources`, because it only cleans up on the error path and does not address the normal-completion branch.

When implementing multi-resource cleanup manually, you must consider all branches:

- Work succeeds, cleanup succeeds.
- Work succeeds, cleanup fails (the cleanup failure must be propagated or handled).
- Work fails, cleanup succeeds (keep the work failure).
- Work fails, cleanup also fails (keep the work failure, attach the cleanup failure).
- Resource initialization fails after another resource has already opened.
- Multiple cleanups fail together; do not stop at the first cleanup failure if the contract requires attempting to clean up the rest.

Because this logic is error-prone, **prefer TWR** whenever resource ownership scope and API types allow.

### Do Not "Suppress" an Unrelated Exception

`addSuppressed` has no technical constraint requiring the additional exception to come from `close()`. However, attaching a completely unrelated exception will mislead anyone reading the stack trace about causal relationships. Only use it when the failures arise within the same unit of work or clearly related cleanup.

### Do Not Use `initCause` as an Arbitrary Substitute for `addSuppressed`

`initCause`/cause constructors represent a **causal chain**: exception A led to exception B or was wrapped by B. A cleanup failure occurring **alongside or after a work failure** is not usually the cause that made the earlier work fail. Attaching cleanup as the cause of the primary exception can create a false causal story; suppressed is the more appropriate relationship.

## 15. Real-World Scenarios and How to Choose Handling

| Scenario | Exception That Should Be Primary | Suppressed Should Contain |
| --- | --- | --- |
| Reading a file fails, then closing the reader fails | Read failure | Reader close failure |
| Writing data succeeds, only flush/close fails | Flush/close failure | Likely none |
| TWR body fails, two resources fail to close | Body failure | Both close failures in sequence |
| TWR body succeeds, two resources fail to close | First close failure in closing order | Subsequent close failure |
| Creating second resource fails, closing first fails | Second resource creation failure | First resource close failure |
| Parse exception wrapped into a business exception | Business exception, with parse as **cause** | Secondary failures only if any |
| Resource throws an exception with suppression disabled | Primary depends on execution path | May fail to store secondary failures |
| Manual cleanup throws a new exception in `finally` without catching | New exception may replace old one | Not automatically attached as suppressed like TWR |

Actual results still depend on which failure occurs first, which resources were successfully initialized, which exception types are thrown, and whether suppression is enabled on **the primary object**.

### Application Example: Accurate Multi-Layer Logging

An orchestrating function may need to log a failure with both its cause and suppressed exceptions. Instead of only:

```java
System.err.println(failure.getMessage());
```

consider passing the full throwable object to an appropriate logging framework or diagnostic output:

```java
failure.printStackTrace(System.err);
```

These are two **illustrative command snippets** assuming `failure` is a `Throwable`. Printing the full exception allows Java to render cause/suppressed details; printing only the message omits most of the additional error context.

In production, use a logger capable of recording the exception object. Do not log repeatedly at every layer when the same exception continues to propagate upward, as that creates duplicate log entries and makes it harder to pinpoint the primary incident.

## 16. Common Mistakes and Misconceptions

**"A suppressed exception is an error that is completely ignored."** False. It is still stored on the primary object and can be read/printed for diagnostics; not becoming primary does not mean it can be ignored operationally.

**"Whenever `close()` throws, the close failure is always suppressed."** False. When the body succeeds, the first close failure can become the primary exception.

**"`getSuppressed()` returns `null` if there are no secondary exceptions."** False. It returns an empty array.

**"`addSuppressed` throws the secondary exception instead of the primary."** False. The method only attaches metadata to a `Throwable` object; it does not `throw`.

**"You can call `root.addSuppressed(root)`."** False. Self-suppression is rejected with `IllegalArgumentException`.

**"`addSuppressed(null)` is simply ignored."** False. `null` is rejected with `NullPointerException`.

**"Modifying `getSuppressed()[0]` mutates the internal list."** False. The returned array is a copy; mutating its element slots does not alter the internal list.

**"`cause` and `suppressed` both just point to the root error; either works the same."** False. Cause represents a causal chain; suppressed records additional failures, especially failed cleanup.

**"`try-with-resources` only keeps one close failure even if multiple resources fail."** False. Multiple suppressed exceptions can be stored in the order recorded, depending on suppression settings and exit path.

**"The close failure of the first resource always becomes primary because it is listed on the left."** False. Java closes right-to-left; when the body succeeds, the first resource to be closed and fail can supply the primary exception.

**"Disabling suppression also disables all parameter validation."** False. `null` and self-suppression remain invalid.

**"Every `Throwable` allows storing suppressed exceptions."** Not necessarily. Subclasses can disable suppression at construction time.

**"A manual `finally` automatically creates suppressed exceptions just like TWR."** False. If `finally` throws a new exception, it can mask the old one. Preserving it requires manual design or TWR.

**"`getSuppressed().length == 0` proves there were no cleanup failures."** Not guaranteed. There may have been no failure, the failure may not have been attached to the primary, or suppression on the primary may have been disabled.

**"Suppressed elements are copies of `Throwable`, so they no longer have real stack traces."** False. The array contains references to the original recorded `Throwable` objects.

**"You can ignore a `close` failure because it is stored in suppressed."** False. A failure closing an output stream can have consequences for data integrity, transactions, or resource leaks and must be evaluated according to application requirements.

## 17. Self-Check Questions

1. **Does `Throwable.addSuppressed(x)` change the primary exception to `x`?** No. It attaches `x` under the primary exception.
2. **When is a `close()` failure suppressed?** When a primary exception is already propagating and TWR records the additional close failure onto it.
3. **If only `close()` fails, with no body failure, what is the typical result?** The close failure becomes the primary exception.
4. **What type does `getSuppressed()` return?** `Throwable[]`.
5. **With no suppressed exceptions, how long is the returned array?** `0`.
6. **What exception does calling `addSuppressed(root)` on `root` throw?** `IllegalArgumentException`.
7. **What exception does `addSuppressed(null)` throw?** `NullPointerException`.
8. **Given resources A then B in a TWR header, in what order are they closed?** B then A.
9. **Body succeeds, B fails to close then A fails to close: which is primary?** B's close failure, with A's close failure as suppressed on B's failure.
10. **Body throws E, both B and A fail to close: what is primary?** E; the close failures are attached as suppressed according to the rules, if suppression is enabled.
11. **Can a single exception have both `getCause()` and `getSuppressed()`?** Yes. Those two relationships are semantically independent.
12. **If suppression is disabled when creating an exception, what does `getSuppressed()` do?** Always returns an empty array for that object.
13. **Does `Throwable[] result = ex.getSuppressed(); result[0] = ...;` modify the internal list?** No.
14. **Can `printStackTrace()` represent suppressed exceptions?** Yes, it is designed to display them alongside causes and stack traces.
15. **Should you replace TWR with `finally { resource.close(); }` for simplicity?** Usually no, because it can easily lose the primary exception when `close()` also fails.
16. **Should you add the same exception multiple times just to increase the suppressed count?** No, unless there is a genuine reason to record it multiple times; the API is not a unique-resource counter.
17. **If suppressed contains an `IOException`, will `catch (IOException)` after TWR automatically catch that secondary failure when the primary is `IllegalStateException`?** No. Handlers match on **the primary's type**; to read the secondary `IOException`, iterate over `getSuppressed()`.
18. **Does a suppressed exception mean the application handled it safely?** No; it can still represent a serious cleanup failure.

## 18. Java 17 Authoritative Sources

- [Java SE 17 API — Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): parameter validation and storing suppressed exceptions.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): secondary exception list, returned array, and disabled suppression.
- [Java SE 17 API — Throwable constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `enableSuppression` and `writableStackTrace`.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): primary/suppressed semantics and resource closing order.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): `close()` contract and checked exceptions.
- [Java SE 17 API — Throwable.printStackTrace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#printStackTrace()): printing causes, stack traces, and suppressed exceptions.

**Takeaway:** `addSuppressed` attaches an additional failure to **a primary `Throwable` object**, while `getSuppressed()` returns those additional failures as an array. In `try-with-resources`, Java automatically uses this mechanism to keep the work failure as **primary** and store cleanup failures as **suppressed**. Read both `cause` and `suppressed` when diagnosing issues, and do not mistake suppression for the error having been resolved.
