# Comparison Table of `throw`, `throws`, `catch`, and `finally` in Java

> **Topic:** Java Core — Exception
> 
> **Purpose:** a standalone reference on the syntax, semantics, placement, coordination, and common pitfalls when using the four keywords `throw`, `throws`, `catch`, and `finally`. The main examples use Java 17+ and can be compiled/run directly.

## 1. Quick Comparison Table

| Aspect | `throw` | `throws` | `catch` | `finally` |
| --- | --- | --- | --- | --- |
| Nature | **Statement** that throws a `Throwable` object | **Declaration clause** in a method/constructor signature | **Handler clause** for exceptions after `try` | **Cleanup/finalization clause** after `try` or `catch` |
| Purpose | Explicitly signal an error **at the point of execution** | Declare the **checked exceptions** that may escape a method/constructor | Receive and handle an exception of a compatible type | Execute code when leaving a `try` construct through normal control-exit mechanisms |
| Representative syntax | `throw new IOException("failed");` | `void load() throws IOException` | `catch (IOException ex) { ... }` | `finally { closeResources(); }` |
| Placement | Inside a method, constructor, initializer, or appropriate lambda/block body | After the parameter list, before the method/constructor body | After the `try` block, before `finally` if present | After the `try` block and any `catch` blocks if present |
| Terminator | `;` after the expression | No separate `;` in the header; ends with the signature/body | Block `{ ... }` | Block `{ ... }` |
| Argument | One **expression of type `Throwable`** | Comma-separated list of **exception types** | One parameter of an exception type or a multi-catch | No parameter |
| Creates/throws an exception? | **Yes**: transfers control by throwing | **No**: does not throw or instantiate anything on its own | **No**: receives an already thrown exception; its body can `throw` further | **Not by default**: the `finally` body can still explicitly throw |
| Checked exception handling | Throwing a checked exception must be caught or declared per Java rules | Lets callers know and handle/declare checked exceptions | Can satisfy the requirement to catch a checked exception | Does not replace `catch`/`throws` for checked exceptions |
| Relation to call stack | Starts propagating the exception up the stack | Describes part of the method's compile-time contract | Stops propagation **if** it matches and handles; can rethrow | Runs while exiting the block, including during normal unwinding |
| Can stand alone? | Can be used inside any valid block | Only used in method/constructor declarations | No: must accompany `try` | No: must accompany `try` |
| Notable risks | Throwing the wrong error type, losing the cause, putting secrets in messages | Overly broad `throws Exception`, misunderstanding it as always throwing | Catching too broadly/swallowing errors, hiding bugs and breaking flow | `return` or `throw` inside `finally` masking the original result/error |

**One-line mnemonic:** `throw` is the **action of throwing**, `throws` is the **declaration**, `catch` is **where it is caught**, and `finally` is **where finalization/cleanup runs**.

A single method can certainly use **all four**. Example:

```java
static String load(boolean offline) throws IOException {
    try {
        if (offline) {
            throw new IOException("source unavailable");
        }
        return "DATA";
    } catch (IllegalArgumentException ex) {
        return "INVALID";
    } finally {
        System.out.println("finished");
    }
}
```

This is a **code snippet** that requires importing `java.io.IOException` and placing it inside a class. `throws IOException` declares the checked exception that may escape; `throw` actually throws when `offline` is true; `catch` here only accepts `IllegalArgumentException`, **not** `IOException`; `finally` prints the message when the block exits. Do not assume that just any `catch` catches every exception.

## 2. Look at Control Flow Order Before Learning Syntax

A simple path:

```text
Caller calls method
       |
       v
  Enter try block
       |
       +-- Normal execution ---------> skip catch
       |                                     |
       +-- Throw exception E                 |
               |                             |
               +--> First catch matching E?  |
                         |                   |
                         +-- yes -> handle   |
                         |                   |
                         +-- no -> propagate |
                                             |
                                             v
                                      finally (if present)
                                             |
                              result / continue throwing / branch
```

This is a conceptual model. `finally` is executed before the `try` statement completes along normal exit paths. However, **it is not an absolute guarantee for every JVM scenario**: forced process termination, `System.exit` terminating the VM, a JVM crash, a permanently blocked thread, or situations where an exit point is never reached can prevent `finally` from running.

**Order matters:** if `catch` finishes handling without throwing further, `finally` runs before code after the entire `try/catch/finally` continues. If the exception is not caught, `finally` is still attempted before the exception propagates to the caller.

## 3. `throw`: Explicitly Throw an Exception Right Now

Standard syntax:

```java
throw expression;
```

`expression` must have a type compatible with `Throwable` according to Java language rules, for example:

```java
throw new IllegalArgumentException("quantity must be positive");
```

This is a code snippet inside a method. When the statement executes, normal statements **following it on the same execution path** do not continue, unless the exception is caught by an enclosing matching block.

A validation example:

```java
static int requirePositive(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    return quantity;
}
```

This is a method that can be placed inside a class. `IllegalArgumentException` is a `RuntimeException`, so the method is not required to declare `throws IllegalArgumentException`. Even when not required, an API can document `@throws` and input preconditions.

### `throw` Is Not `return`

- `return` ends the method with a value (or with no value for `void`).
- `throw` ends **the current control path** with an exception.
- The caller receives a value only when the control path completes normally; if an exception escapes, the caller does not receive a normal return value from that call.

### `throw` Can Rethrow a Caught Exception

```java
try {
    read();
} catch (IOException ex) {
    recordFailure();
    throw ex;
}
```

This is a code snippet inside a method that declares `throws IOException` (or has an enclosing handler), requiring `IOException` to be imported and `read`/`recordFailure` to be defined. `throw ex;` preserves the exact **Throwable object** that was caught, including its existing stack/cause/suppressed exceptions; it does not create a new wrapper.

### What About `throw null`?

A throw expression can evaluate to `null`; when `throw null;` executes, the JVM raises a `NullPointerException` instead of throwing a useful exception. Do not do this to represent missing data. Use a meaningful exception type with an appropriate message.

## 4. `throws`: Declare Possible Propagation, Not Throwing on Its Own

Syntax:

```java
ReturnType methodName(Parameters...) throws ExceptionType1, ExceptionType2 {
    // method body
}
```

This is a signature template, not standalone code. A real example:

```java
static String readFile(Path path) throws IOException {
    return Files.readString(path);
}
```

This is a method requiring imports for `java.nio.file.Path`, `java.nio.file.Files`, and `java.io.IOException`. The declaration informs callers that they must handle or propagate the possibility of `IOException` (a checked exception). However, **a successful call will not throw an exception merely because the header has `throws`**.

Example with multiple checked exception types:

```java
static void load(Path file)
        throws IOException, java.text.ParseException {
    String raw = Files.readString(file);
    parseRequiredData(raw);
}
```

This is a code snippet with an application-defined `parseRequiredData` and related imports. In real code, ensure `parseRequiredData` actually has a contract that can throw `ParseException`; this is only a template for a `throws` list. Do not declare unrelated error types just "in case".

### Checked vs. Unchecked

| Category | Examples | Compile-time rule |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `ParseException` | When it can escape the method, it must be **caught or declared (`throws`)**, subject to relevant language rules |
| Unchecked exception | `IllegalArgumentException`, `NullPointerException`, `IllegalStateException` | Not required to catch/declare |
| `Error` | `OutOfMemoryError`, `StackOverflowError` | Not required to catch/declare; generally should not be broadly recovered from |

`throws` can also declare unchecked exceptions for documentation purposes, but it does not create a new compile-time obligation for callers the way checked exceptions do.

### Is `throws Exception` a Good Choice?

`throws Exception` can be used in demos, test entrypoints, or adapters for legacy libraries, but public APIs should prefer checked exceptions **that are meaningful to callers**. If every method just says `throws Exception`, callers have trouble knowing which cases to recover from and tend to write overly broad `catch (Exception)` blocks.

Do not claim that a method with `throws IOException` **can only** throw `IOException`. It can still throw unchecked exceptions such as `NullPointerException`; `throws` is not an exhaustive result-type system that excludes all other errors.

## 5. `throw` and `throws` Side by Side

Example:

```java
static String fetch(boolean available) throws IOException {
    if (!available) {
        throw new IOException("dependency offline");
    }
    return "OK";
}
```

This is a method that requires importing `IOException`.

| Question | `throw new IOException(...)` | `throws IOException` |
| --- | --- | --- |
| When does it take effect? | When execution reaches the statement in the body | When the compiler analyzes the signature |
| Creates an exception object? | Yes: the `new IOException` expression | No |
| Causes the caller to receive an exception immediately? | When the branch executes and is not handled | No, only declares the possibility |
| Can list multiple types separated by commas? | No: one throw statement throws one Throwable | Yes: `throws IOException, ParseException` |
| Requires a semicolon? | Yes, after the `throw` statement | No separate `;` before the method body |
| Can be used in a constructor? | Yes, in the body | Yes, in the constructor signature |
| Can be used at a method call site? | Yes if inside a valid block | No: `throws` only belongs in a declaration |

A reader may see `throws IOException` on a signature yet **not see `throw new IOException` inside the method**: `IOException` may originate from a deeper call such as `Files.readString()`. This is valid because checked exceptions propagate up the call stack when uncaught.

## 6. `catch`: Receive Exceptions by Compatible Type

Syntax:

```java
try {
    mayFail();
} catch (IOException ex) {
    handleIoError(ex);
}
```

This is a code snippet with imports and application functions. When code inside `try` throws a Throwable, Java selects the first `catch` block whose parameter type is compatible with the actual exception type.

A `catch` block can:

- **Recover** with a business-valid fallback.
- **Translate the error** into a domain exception, preserving `cause`.
- **Record FAILED/CANCELLED state** where the workflow is owned.
- **Perform specialized cleanup** if `finally`/`try-with-resources` does not fit that part.
- **Rethrow** via `throw ex;` when it cannot handle the error at this layer.

Do not assume `catch` automatically means "the error is resolved". If a handler only prints a message and returns a fake result, system state may still be invalid. If `catch` throws a new exception, the caller receives that exception, and `finally` (if present) still runs according to the rules.

### Catch Order: From Specific to General

```java
try {
    load();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

This is a code snippet with `load`/handlers and appropriate imports. `FileNotFoundException` is a subclass of `IOException`; it must be placed first if it needs a separate handler.

The reversed order below **does not compile**:

```java
try {
    load();
} catch (IOException ex) {
    handleIo(ex);
} catch (FileNotFoundException ex) {
    handleMissing(ex); // Unreachable catch: already caught by IOException.
}
```

This is an **intentionally invalid example**. Do not run it as a complete program.

## 7. Multi-catch and the No-Inheritance Rule

Since Java 7, a single handler can catch multiple exception types that are not in a subtype relationship with each other:

```java
try {
    networkOperation();
} catch (SocketTimeoutException | ConnectException ex) {
    markTemporarilyUnavailable(ex);
}
```

This is a code snippet requiring imports for `java.net.SocketTimeoutException`, `java.net.ConnectException`, and application functions. Both types are handled **the same way**, so multi-catch makes sense.

An **invalid** example:

```java
catch (Exception | IOException ex) {
    // Does not compile: IOException is a subtype of Exception.
}
```

In a multi-catch, the parameter is **implicitly final**; the `ex` variable cannot be reassigned. Java selects a handler based on the thrown Throwable type and does not run multiple catch branches for the same exception.

Multi-catch is appropriate when **the handling policy is identical**, not merely to write fewer lines. If a timeout should be retried while an authentication failure should not, separate the handlers.

## 8. `finally`: Runs When Leaving `try` Through Normal Control Paths

Common syntax:

```java
try {
    work();
} finally {
    cleanup();
}
```

This is a code snippet requiring definitions for `work`/`cleanup`. `finally` can accompany `try` even **without `catch`**. It is useful for releasing locks or resetting internal state when exiting the block through normal paths.

An example:

```java
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

This is a code snippet requiring a `lock` variable of type `java.util.concurrent.locks.Lock` and an `updateState` method. `finally` ensures an `unlock()` attempt when leaving the block, but **does not automatically roll back** updates made earlier.

### Normal Situations Where `finally` Runs

- The `try` body finishes normally.
- A `catch` handles an error and finishes.
- The `try` or `catch` body executes `return`.
- The body executes `break` or `continue`, causing control to leave the `try` scope.
- An uncaught exception propagates out of `try`.
- A new exception is thrown from `catch` before exiting.

### Limitations to Remember

Never state that "`finally` **always** runs no matter what happens". Abrupt VM/process termination, being killed, crashes, or never leaving the block (infinite blocking) can prevent `finally` from running. Moreover, if **`finally` itself throws an exception or returns**, it can replace the result/error being propagated.

## 9. `return` Inside `try` and `finally` Execution Order

Consider:

```java
static int getValue() {
    try {
        return 42;
    } finally {
        System.out.println("cleanup");
    }
}
```

This is a method that can be placed in a class. When `getValue()` is called, the runtime prepares to complete the return but executes `finally` first. Therefore, the output `cleanup` appears before the caller receives `42`.

An example to distinguish:

```java
static int snapshot() {
    int result = 1;
    try {
        return result;
    } finally {
        result = 2;
    }
}
```

This method returns **1**, because the primitive return value was already determined before `finally` modified the local variable. This is not a promise that any returned object is immutable: if `finally` **mutates an object** that is already referenced, the caller may observe the mutated object.

### Do Not Return from `finally`

```java
static int misleading() {
    try {
        throw new IllegalStateException("failure");
    } finally {
        return 10;
    }
}
```

This is an **anti-pattern snippet**: it compiles, but returning inside `finally` **masks the original exception**, causing the caller to see `10` even though the operation failed.

Similarly, `finally` throwing a new exception can mask the exception currently propagating. Only perform cleanup there; when cleanup also fails, preserve the original error per contract rather than silently replacing it.

## 10. How Does `finally` Differ from `catch`?

| Question | `catch` | `finally` |
| --- | --- | --- |
| Selects an exception type? | Yes, based on parameter type | No |
| Receives Throwable as a variable `ex`? | Yes | No |
| Runs when `try` completes normally? | No | Yes, if `finally` is present and control exits normally |
| Can handle/swallow the original error? | Yes | Not automatically, though `return`/`throw` in its body can mask the error |
| Typically used for | Recovery, translation, error mapping, reporting | Cleanup, releasing locks, updating flags/lifecycle |
| Requires `catch` to exist? | Needs `try`, does not need `finally` | Needs `try`, does not need `catch` |
| What if `catch` rethrows? | The handler rethrows | `finally` is still attempted before the exception escapes |
| Can it replace try-with-resources? | No | Can be done manually, but error-prone when `close()` also throws |

`catch` and `finally` **do not replace each other**. Do not catch an exception just because you need to release a resource, and do not add `finally` just to swallow errors with `return`.

## 11. All Four Keywords Working Together in a Realistic Flow

A common pattern in an I/O handling layer:

```java
static String readOrFallback(String path) {
    try {
        return readFile(path); // readFile may throw IOException.
    } catch (IOException ex) {
        return "DEFAULT";
    } finally {
        recordAttemptFinished();
    }
}
```

This is a code snippet requiring `readFile`/`recordAttemptFinished` and an import for `IOException`. If `readFile` succeeds normally, `catch` is skipped, `finally` runs, and the caller receives the content. If `IOException` occurs, the handler returns the fallback, and `finally` runs before the caller receives `"DEFAULT"`.

**Important condition:** a fallback is only valid when business requirements allow it. For example, secondary configuration having a default is normal; returning `0` on a failure to read an account balance is a serious bug.

For an input error such as `IllegalArgumentException`, which is not caught by the `IOException` handler, `finally` still runs, and then the input error propagates to the caller. This is confirmed in the standalone runnable program in Section 12.

## 12. Complete Java 17+ Program and Verified Output

The following integrated example demonstrates:

1. `throw` creates `IllegalArgumentException` when the key is invalid.
2. `throws IOException` on `read(...)` lets a checked exception escape when the simulated dependency is offline.
3. `catch (IOException)` turns an I/O error into a dedicated fallback without swallowing validation errors.
4. `finally` increments the counter **on success, when catching `IOException`, and when an unchecked exception propagates**.
5. `try-with-resources` closes resources in reverse order and stores close errors in `getSuppressed()` when the body also failed.
6. If the body succeeds but resource close throws, the first close error becomes the primary exception.

Create the file **`ThrowThrowsCatchFinallyDemo.java`**:

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class ThrowThrowsCatchFinallyDemo {
    private static int finallyCount;
    private static final List<String> EVENTS = new ArrayList<>();

    static String read(String key) throws IOException {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key must not be blank");
        }
        if ("offline".equals(key)) {
            throw new IOException("source unavailable");
        }
        return "VALUE:" + key;
    }

    static String request(String key) {
        try {
            return read(key);
        } catch (IOException ex) {
            return "FALLBACK:" + ex.getClass().getSimpleName();
        } finally {
            finallyCount++;
        }
    }

    static final class Resource implements AutoCloseable {
        private final String name;
        Resource(String name) {
            this.name = name;
            EVENTS.add("open-" + name);
        }
        @Override
        public void close() throws IOException {
            EVENTS.add("close-" + name);
            throw new IOException("close-" + name + "-failed");
        }
    }

    static void bodyAndCloseFailure() throws IOException {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            EVENTS.add("body-failed");
            throw new IOException("body-failed");
        }
    }

    static void onlyCloseFailure() throws IOException {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            EVENTS.add("body-ok");
        }
    }

    static String suppressedMessages(Throwable ex) {
        List<String> messages = new ArrayList<>();
        for (Throwable suppressed : ex.getSuppressed()) {
            messages.add(suppressed.getMessage());
        }
        return String.join(",", messages);
    }

    static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        String success = request("A");
        String fallback = request("offline");
        check("VALUE:A".equals(success), "success");
        check("FALLBACK:IOException".equals(fallback), "fallback");
        System.out.println("RETURN: " + success);
        System.out.println("CATCH: " + fallback);

        try {
            request("");
            throw new AssertionError("expected validation exception");
        } catch (IllegalArgumentException ex) {
            check("key must not be blank".equals(ex.getMessage()), "validation");
            System.out.println("THROW_UNCHECKED: " + ex.getMessage());
        }
        check(finallyCount == 3, "finally must run three times");
        System.out.println("FINALLY_COUNT: " + finallyCount);

        EVENTS.clear();
        try {
            bodyAndCloseFailure();
            throw new AssertionError("expected body failure");
        } catch (IOException ex) {
            check("body-failed".equals(ex.getMessage()), "body primary");
            check("close-B-failed,close-A-failed".equals(suppressedMessages(ex)),
                    "body suppressed");
            System.out.println("BODY_PRIMARY: " + ex.getMessage());
            System.out.println("BODY_SUPPRESSED: " + suppressedMessages(ex));
            System.out.println("BODY_EVENTS: " + String.join(",", EVENTS));
        }

        EVENTS.clear();
        try {
            onlyCloseFailure();
            throw new AssertionError("expected close failure");
        } catch (IOException ex) {
            check("close-B-failed".equals(ex.getMessage()), "close primary");
            check("close-A-failed".equals(suppressedMessages(ex)),
                    "close suppressed");
            System.out.println("CLOSE_PRIMARY: " + ex.getMessage());
            System.out.println("CLOSE_SUPPRESSED: " + suppressedMessages(ex));
            System.out.println("CLOSE_EVENTS: " + String.join(",", EVENTS));
        }
        System.out.println("CHECKS: PASS");
    }
}
```

**Compile/run with JDK 17 or later** (no external libraries required):

```bash
javac -encoding UTF-8 ThrowThrowsCatchFinallyDemo.java
java ThrowThrowsCatchFinallyDemo
```

**Verified standard output:**

```text
RETURN: VALUE:A
CATCH: FALLBACK:IOException
THROW_UNCHECKED: key must not be blank
FINALLY_COUNT: 3
BODY_PRIMARY: body-failed
BODY_SUPPRESSED: close-B-failed,close-A-failed
BODY_EVENTS: open-A,open-B,body-failed,close-B,close-A
CLOSE_PRIMARY: close-B-failed
CLOSE_SUPPRESSED: close-A-failed
CLOSE_EVENTS: open-A,open-B,body-ok,close-B,close-A
CHECKS: PASS
```

This output comes from compiling and running the program with `javac`/`java` on a modern JDK and uses only valid Java 17 syntax and APIs. The `check` helper throws `AssertionError` if any condition fails expectations; thus `CHECKS: PASS` only appears after all demo verification branches succeed.

### Result Analysis

- `RETURN: VALUE:A`: no exception; `read("A")` returns data normally, and `catch` does not run.
- `CATCH: FALLBACK:IOException`: `read("offline")` **actually executes `throw new IOException`**; `request` catches the checked exception and returns the fallback per the demo's contract.
- `THROW_UNCHECKED`: a blank key causes `IllegalArgumentException` to propagate through `request` because it only has `catch(IOException)`; the outer caller catches and verifies it.
- `FINALLY_COUNT: 3`: all three calls to `request` pass through `finally` despite different return/error paths.
- `BODY_PRIMARY` and `BODY_SUPPRESSED`: the body exception is kept as the primary; close errors for B and A are in suppressed in reverse closing order.
- `CLOSE_PRIMARY` and `CLOSE_SUPPRESSED`: the body succeeds, B closes first and fails so it becomes primary; A's close error is suppressed.
- `BODY_EVENTS` / `CLOSE_EVENTS`: opens A then B, closes B then A (LIFO). Subsequent closes are still attempted after the first close failure.

This example makes `Resource.close()` always throw for demonstration purposes. Do not do this in a production resource: close errors should only be thrown when cleanup genuinely fails to complete per the resource's contract.

## 13. Why Is try-with-resources Usually Better Than Writing `finally` Manually to Close?

A commonly seen manual pattern:

```java
InputStream input = Files.newInputStream(path);
try {
    process(input);
} finally {
    input.close();
}
```

This is a code snippet inside a method compatible with `IOException`, assuming `Path path`, `process`, and imports exist. If `process(input)` throws an exception and `input.close()` also throws, the close exception can **mask the body error**, making the root cause harder to diagnose.

Recommended syntax when the resource implements `AutoCloseable`:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

This equivalent snippet requires the same imports and method contract as above. With `try-with-resources`:

- Resources are initialized from left to right.
- When leaving the scope, initialized resources are closed from right to left.
- If the body already threw a Throwable, secondary close errors are typically attached to the primary's `Throwable.getSuppressed()`.
- If the body succeeds but the first close throws, that close error can be the primary exception.
- If a later resource's initializer fails, earlier initialized resources are still attempted to be closed.
- A `null` resource reference (semantically valid in some cases) does not have `close()` called on it.

`try-with-resources` does not replace business transactions/rollbacks. Closing a connection does not mean prior writes have been undone; transaction and driver semantics must be checked separately.

### Note on `throws` of `AutoCloseable.close()`

`AutoCloseable.close()` is declared with `throws Exception`, whereas `Closeable.close()` (in `java.io`) has a narrower declaration with `IOException`. When writing a method that uses a resource whose `close()` throws a checked exception, the compiler requires that error to be caught or declared.

Do not assume a method cannot throw just because the body does not throw: `close()` can still throw.

## 14. `throw new`, `throw ex`, and Wrapping Exceptions with a Cause

Three forms that are easy to confuse:

```java
throw new IllegalArgumentException("bad parameter");
```

This is a code snippet: **creates and throws a new instance**.

```java
catch (IOException ex) {
    throw ex;
}
```

This code snippet sits inside a `try/catch` and compatible signature: **rethrows the exact caught instance**.

```java
catch (IOException ex) {
    throw new RepositoryUnavailableException("repository unavailable", ex);
}
```

This is a code snippet requiring a `RepositoryUnavailableException` with a constructor accepting `Throwable cause`. It **translates the error** to a type meaningful at the boundary while preserving the source error via `getCause()`.

Do not do this:

```java
catch (IOException ex) {
    throw new RuntimeException("operation failed");
}
```

without good reason, because it loses the cause and the origin path of the original error. At the same time, even when preserving the cause, **do not print the entire message/cause directly into API responses**: dependency exceptions may contain URLs, tokens, credentials, or personal data.

For exception translation, choose a business-meaningful error type rather than wrapping everything in a generic `RuntimeException`.

## 15. Must a `try` Always Have Both `catch` and `finally`?

**No.** All of the following forms are valid:

**Only try/catch:**

```java
try {
    work();
} catch (KnownFailure ex) {
    recover(ex);
}
```

**Only try/finally:**

```java
try {
    work();
} finally {
    cleanup();
}
```

**Try/catch/finally:**

```java
try {
    work();
} catch (KnownFailure ex) {
    recover(ex);
} finally {
    cleanup();
}
```

**Try-with-resources:**

```java
try (Resource resource = openResource()) {
    workWith(resource);
}
```

All of these are conceptual code snippets requiring definitions for `KnownFailure`, `Resource`, and the corresponding methods. With a traditional `try`, there must be at least **one `catch` or one `finally`**. With `try-with-resources` having a resource specification, an explicit `catch`/`finally` is not required.

If `finally` is present, its position is always **after** the `catch` blocks of the same statement. Do not place `catch` after `finally`. A single `try` block can have multiple `catch` blocks, but only one `finally` directly attached to it; if multi-level cleanup is needed, use nested scopes or helpers.

## 16. Checked Exceptions from Deeper Calls: No Need to Rethrow Manually

```java
static void copy(Path source, Path destination) throws IOException {
    Files.copy(source, destination);
}
```

This is a method requiring imports from `java.nio.file` and `java.io`. `Files.copy` can throw a checked exception, so `copy` can simply declare `throws IOException` and let the caller decide how to handle it. There is no need for:

```java
static void copy(Path source, Path destination) throws IOException {
    try {
        Files.copy(source, destination);
    } catch (IOException ex) {
        throw ex;
    }
}
```

because this `catch` block **adds nothing** compared to letting the error propagate. A `catch` is only useful when it performs real work such as owned rollback, adding safe context, translating the exception type, or recording meaningful state.

Key point: `throws` **does not turn checked exceptions into unchecked ones**, nor does it guarantee an error will be caught. It only participates in the compile-time contract and allows the exception to continue propagating if it occurs.

## 17. Rethrow and Precise Rethrow

Java allows rethrowing the catch parameter:

```java
try {
    mayThrowFileOrSql();
} catch (Exception ex) {
    record(ex);
    throw ex;
}
```

This is a code snippet with a method `mayThrowFileOrSql` having a checked-exception contract and a user-defined `record`. From Java 7 onward, the compiler can use **precise rethrow analysis** to infer the set of checked exception types that the statement can throw if the catch parameter is effectively final (not reassigned), instead of always requiring `throws Exception`.

For example, if `mayThrowFileOrSql()` can only throw `IOException` and `SQLException`, the enclosing method can declare just those two types when precise rethrow conditions are satisfied. Conversely, if `ex` is reassigned, the analysis may no longer be sufficiently precise under language rules.

This is a **compile-time** feature. At runtime, `throw ex` still throws the exact same object. However, a `catch(Exception)` solely to rethrow without doing anything extra is still usually unnecessary; do not add a catch block just to exercise a compiler feature.

## 18. `catch(Exception)` vs. `catch(Throwable)`

| Handler | Covers | Risk if used indiscriminately |
| --- | --- | --- |
| `catch (Exception ex)` | Checked exceptions and `RuntimeException` | Swallows bugs, masks `InterruptedException`, turns failures into fake results |
| `catch (Throwable t)` | All `Exception` **and `Error`** | Can mask `OutOfMemoryError`/`StackOverflowError` and leave the application running in an untrusted state |
| `catch (IOException ex)` | I/O hierarchy | Narrower, though still requires a valid policy |
| `catch (InterruptedException ex)` | Interruption signal for blocking operations | Needs to be propagated or have the flag restored/task exited per contract |

`catch(Exception)` is not always wrong: at an HTTP boundary or top-level job runner, a generic fallback for unexpected errors after specific handlers can be reasonable. What you must not do is **copy broad catch blocks across every layer and swallow errors**.

`catch(Throwable)` can exist in frameworks or test harnesses to observe failures of a unit of execution, but should not be treated as a way to "recover from any Error". A resource-starved VM may not even be capable of executing complex error-reporting logic.

## 19. Do Not Swallow `InterruptedException` in a Broad Catch

Example of a task running in a thread pool:

```java
while (true) {
    try {
        process(queue.take());
    } catch (Exception ex) {
        logger.warn("retry", ex);
    }
}
```

This is an **anti-pattern snippet** with application-defined `queue`, `process`, and `logger`. `BlockingQueue.take()` can throw `InterruptedException`, which is a subclass of `Exception`. A generic catch can swallow the cancellation signal, keeping the worker running.

If the method can declare it:

```java
void receive(BlockingQueue<Job> queue) throws InterruptedException {
    process(queue.take());
}
```

This is a code snippet requiring an import for `BlockingQueue` and definitions for `Job`/`process`. Propagating checked interruption is usually clearer.

Inside `Runnable.run()`, checked `InterruptedException` cannot be thrown:

```java
@Override
public void run() {
    try {
        process(queue.take());
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

This is a snippet inside an application class with queue/cleanup. Once caught, restore the interrupt flag and exit the execution path appropriately; do not restore it and loop back into `while(true)` ignoring the interruption request, as that can create a hot loop.

A layer that owns the entire interruption protocol may handle and consume the signal intentionally, but that must be a deliberate decision rather than a side effect of an overly broad catch.

## 20. `finally` Does Not Mean Rollback and Does Not Guarantee `close` Succeeds

An anti-pattern:

```java
try {
    chargeCustomer(); // May have already committed.
    sendReceipt();    // May fail.
    return true;
} finally {
    logFinished();
}
```

This is a code snippet with defined business methods. `finally` only calls `logFinished()` on exit. It **does not automatically undo** the charge. If `chargeCustomer()` succeeded and `sendReceipt()` failed, the caller may receive an exception even though the customer was already charged.

Similarly:

- `lock.unlock()` in `finally` releases the lock; it does not undo mutated state.
- `connection.close()` is not by default equivalent to a transaction rollback across all drivers/pools.
- `future.cancel(true)` is a cancellation request, not a guarantee that prior side effects have disappeared.
- `Files.delete(...)` in `finally` can itself fail or delete the wrong file if paths are not carefully managed.

If rollback is needed, identify the transaction owner, commit/rollback conditions, indeterminate states, and how rollback failures are preserved. In many systems, use idempotency, transactional outbox, or compensation where appropriate.

## 21. Decision Table: Which Keyword to Use?

| You need to… | Usually appropriate tool | How to think about it |
| --- | --- | --- |
| Reject an invalid parameter immediately | `throw` | `throw new IllegalArgumentException(...)` |
| Inform callers a method may fail due to I/O | `throws` | `readFile(...) throws IOException` |
| Handle an I/O error with a valid fallback | `catch (IOException ex)` | Use a fallback only when meaningful per contract |
| Translate an adapter error to a domain error | `catch` + `throw new ...(..., ex)` | Preserve `cause` |
| Simply forward an I/O error from an intermediate method | `throws IOException` | No pointless catch-and-rethrow |
| Release a lock even if the body fails | `finally` | `unlock()` in `finally` |
| Close an `AutoCloseable` resource, preserving close errors | `try-with-resources` | Auto-closes, supports suppressed exceptions |
| Catch multiple errors with the same handling | Multi-catch | `catch (A | B ex)` for unrelated types |
| Report unexpected errors at an API boundary | Dedicated fallback catch | Return a public error code, do not leak stack traces |
| Task interrupted while waiting | `catch(InterruptedException)` or `throws` | Propagate, or restore and stop |
| Recover after a partial commit | Not just the four keywords | Transaction/idempotency/compensation |
| Keep all errors from `try` and `close` | `try-with-resources` + `getSuppressed()` | Body primary, close suppressed when appropriate |

This table is a guide, not a substitute for the contract of the API in use. Validation errors, domain errors, dependency errors, and cancellation have very different policies, even though all can be represented as `Throwable`.

## 22. Common Syntax and Reasoning Mistakes

| Mistake | Problem | How to fix |
| --- | --- | --- |
| Writing `throws new IOException(...)` | `throws` takes **types**, not instances | Use `throw new IOException(...)` in the body |
| Writing `throw IOException;` | `throw` needs a **Throwable expression**, not a class name | Create/obtain an instance |
| Writing `throw "error";` | `String` is not a `Throwable` | Throw an appropriate exception type |
| Thinking `throws` makes an exception happen on every call | A declaration does not throw on its own | Find the actual `throw` or throwing call |
| Thinking `catch(IOException)` also catches `NullPointerException` | Not in the same hierarchy branch | Catch the specific type you need to handle; let bugs propagate |
| Putting `catch(IOException)` after `catch(Exception)` | The subclass handler is unreachable | Catch specific types first |
| Using `catch(Exception | IOException)` | Multi-catch has a parent–child relationship | Only combine unrelated types |
| Omitting `catch`/`finally` from a traditional `try` | Standalone `try { }` syntax is invalid | Add `catch`/`finally` or use TWR |
| Thinking `finally` runs **before** `catch` | Wrong order | For a matching exception: `catch` then `finally` |
| Returning in `finally` to "ensure a result is returned" | Can mask exceptions/returns from `try` | Do not return in `finally` |
| New exception in `finally` masking the main error | Loses primary diagnostics | Use TWR or preserve the original error |
| Catching `IOException` and returning fake success | Corrupted business state | Fallback only when the contract permits |
| Wrapping a new exception without passing `cause` | Loses root error | Pass `ex` to a constructor accepting `cause` |
| Catching `Exception` and swallowing interrupt | Task fails to stop | Handle `InterruptedException` separately |
| Believing `finally` always runs even on process crash | No absolute guarantee | Lifecycle cleanup + out-of-process recovery |
| Believing `close` equals rollback | Side effects may already be committed | Check transaction semantics |
| Writing `Throwable` message directly to clients | Can leak secrets/PII | Safe error codes + policy-compliant logging |

## 23. Self-Practice Exercises and Guided Answers

### Question 1 — Determine the Output

```java
static int example() {
    try {
        return 5;
    } finally {
        System.out.println("F");
    }
}
```

When calling `System.out.println(example());`, the program prints `F` then `5`. **Why?** The return value is prepared, but `finally` runs before the method completes.

### Question 2 — Distinguish the Two Clauses

```java
static void run() throws IOException {
    throw new IOException("io");
}
```

**Is `throws IOException` the runtime cause of throwing the error?** No: the runtime cause is the executed `throw new IOException("io")` statement. `throws` informs the compiler/caller that a checked exception may escape the method.

### Question 3 — Swapped Catch Order

```java
try {
    read();
} catch (Exception ex) {
    handleGeneric(ex);
} catch (IOException ex) {
    handleIo(ex);
}
```

**Does it compile?** No, because the earlier `Exception` handler already catches `IOException`; the subsequent `IOException` handler is unreachable. Fix by placing the `IOException` handler first or removing the separate handler if the policy is identical.

### Question 4 — Does `finally` Mask the Error?

```java
static int example() {
    try {
        throw new RuntimeException("failure");
    } finally {
        return 99;
    }
}
```

**What does the caller receive?** The method returns `99` and the original exception is masked. This is why **you should avoid returning from `finally`**.

### Question 5 — When Both Body and Close Throw

A `try-with-resources` opens A then B; the body throws `IOException("body")`; `B.close` and `A.close` both throw. **What is the primary exception?** The body error. **In what order are they closed?** B then A. **Where are the close errors?** In `primary.getSuppressed()` in the order they occurred.

These exercise snippets are placed in an appropriate method/class context with imports added as needed. Only the program in Section 12 is designed as a complete standalone Java file.

## 24. Final Reference Checklist

- [ ] Distinguish **`throw` (action)** from **`throws` (declaration)**.
- [ ] When using checked exceptions, the method has an appropriate handler or `throws` per contract.
- [ ] Catch based on the actual `Throwable` type; subclass before superclass.
- [ ] Do not catch `Exception`/`Throwable` overly broadly just to make errors disappear.
- [ ] When translating exceptions, choose the right code/type and preserve `cause` when needed.
- [ ] `finally` runs on normal exit paths, **not as an absolute guarantee regardless of JVM/process state**.
- [ ] Do not `return` inside `finally` and avoid letting an exception from `finally` mask the primary error.
- [ ] For `AutoCloseable`, prefer `try-with-resources` and inspect `getSuppressed()` when close errors occur.
- [ ] Do not equate a thrown exception with "no side effects occurred".
- [ ] Do not log secrets, tokens, or PII directly into exception messages or client responses.
- [ ] Distinguish interruption/cancellation from business errors, especially in workers.
- [ ] Test success, checked failure, unchecked failure, catch mapping, `finally`, close failure, and suppressed errors.

**In summary:** `throw` makes an error **happen**, `throws` describes checked errors that **may escape**, `catch` decides **whether to handle that error type at this layer**, and `finally` handles **finalization/cleanup when exiting the block**. Using them properly is not just about valid syntax, but also about preserving root causes, not masking failure states, and not creating fake successes.
