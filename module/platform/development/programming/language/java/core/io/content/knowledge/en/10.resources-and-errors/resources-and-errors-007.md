# Cleanup When Creating or Assembling Resources Fails in Java I/O

## 1. The Problem: Partially Opened Before Construction Finishes

In Java I/O, a resource can be a file, socket, stream, reader, writer, temporary file, channel, or an object managing multiple resources. They typically hold file descriptors/handles or buffers that must be closed. If code opens multiple resources or composes wrappers and a **later step throws an exception**, previously opened resources still need to be cleaned up.

Example workflow:

~~~text
open file A         [succeeded]
open file B         [failed]
process A and B     [not run]
cleanup file A      [mandatory]
report error from B [preserve original cause]
~~~

Without cleaning up file A, the application can leak descriptors, hold file locks, or fail to release connections even though the method never returned a result object. This is **partial initialization / partial acquisition**: some resources were allocated, yet overall construction failed.

Two distinct scenarios must be separated:

1. **Resource A was created successfully, then opening resource B fails:** try-with-resources (TWR) can close A automatically.
2. **B's own constructor/factory opened internal resources and then failed:** B was never constructed successfully, so the caller has no B reference to close. The constructor/factory must clean up those internally opened resources itself.

Another error can occur **during cleanup itself**: `close()` can throw an `IOException` or another exception. Correct code must preserve the primary error and avoid masking it with resource-closing errors.

## 2. Resource Ownership Contracts

For consistent cleanup, every API needs clear rules:

- **Whoever opens is responsible for closing**, unless ownership is transferred through a defined contract.
- A method that **returns successfully** with a stream/wrapper can transfer closing responsibility to the caller.
- A method that **fails before returning** must clean up every resource it owns, including partially acquired resources.
- When a wrapper takes ownership of an underlying stream, **closing the wrapper normally closes the base stream**. If both the wrapper and the base stream are closed separately, the resource may be closed multiple times.
- Never silently assume `close()` never fails or is always idempotent. Check the resource's specific contract.

For example, when calling **new BufferedInputStream(raw)**, the wrapper uses `raw`; when closing the wrapper, it closes `raw` per the class contract. For an application-defined decorator, the contract must specify whether the wrapper **owns** or only **borrows** the stream. Avoid both extremes: nobody closing (causing leaks), or multiple parties closing (causing double-close and state errors).

**Keeping a resource alive** is not the same as **holding a Java reference**: the garbage collector may reclaim objects, yet you must not rely on GC or finalizers to release I/O resources promptly. Use try-with-resources or close in `finally`.

## 3. TWR: Resources Open Left to Right, Close Right to Left

Java 17 syntax:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

Initializer expressions run **from left to right**: A, then B, then C. Upon leaving the try block, **successfully initialized** resources close **in reverse order**: C, B, A.

If **openB() throws an exception**:

~~~text
openA()  -> succeeds
openB()  -> throws IOException
openC()  -> NOT called
use(...) -> NOT run
a.close()-> called automatically
exception from openB() propagates out
~~~

There is no complete `b` object to close; TWR is only responsible for resource initializers that **returned successfully**. If `openB()` managed to create an internal raw stream before failing to return `b`, **`openB()` must clean up that raw stream itself**.

TWR applies to types implementing **AutoCloseable** or **Closeable**. `close()` is called even if the body throws, returns, or raises an exception; **try-with-resources manages closing order and suppressed exceptions automatically**. Since Java 9, pre-declared variables can be placed in the try header if they are final or effectively final, though doing so does not change the variable's ownership by itself.

## 4. Runnable Program: Opening B Fails, A Still Closes

Create **`AcquisitionFailureDemo.java`** (UTF-8 source):

~~~java
import java.io.IOException;

public class AcquisitionFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        Resource(String name, boolean failClose) {
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:" + name);
            if (failClose) {
                throw new IOException("close-" + name + " failed");
            }
        }
    }

    static Resource open(String name, boolean failClose)
            throws IOException {
        System.out.println("open:" + name);
        if ("B".equals(name)) {
            throw new IOException("open-B failed");
        }
        return new Resource(name, failClose);
    }

    public static void main(String[] args) {
        try (Resource a = open("A", true);
             Resource b = open("B", false)) {
            System.out.println("body");
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            for (Throwable other : primary.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

Compile and run using JDK 17 or later:

~~~bash
javac -encoding UTF-8 AcquisitionFailureDemo.java
java AcquisitionFailureDemo
~~~

Expected stdout, matching exact call order:

~~~text
open:A
open:B
close:A
primary=open-B failed
suppressed=close-A failed
~~~

Points to observe:

- **open(A)** succeeds, so A is added to the list of resources to close.
- **open(B)** throws `IOException`; the body never executes (no `body` line).
- A still closes automatically even though the body was never entered.
- Closing A **also fails**, yet B's exception remains **primary**.
- The `IOException` from closing A is attached to **primary.getSuppressed()**, allowing both problems to be recovered.

If closing A does not fail, the suppressed list is empty; that does not affect automatic closing. If `open(B)` succeeds, B closes before A when leaving `try`.

## 5. Primary Exception and Suppressed Exceptions

When two errors occur together, we must determine **which error explains the primary cause**:

~~~text
Error from initialization / body -> primary exception
Error inside close()             -> suppressed exception
~~~

With TWR:

- If an initializer or body throws and `close()` also throws, the initial error is kept as **primary**; close errors are added to the suppressed list.
- If no error comes from initializers/body yet `close()` throws, the close error of the first resource closed can become primary; subsequent close errors are suppressed.
- Remaining TWR resources are still attempted to be closed even if closing an earlier resource failed.

This is a major advantage over manual code like:

~~~java
// WRONG if you want to preserve the business error:
try {
    work();
} finally {
    resource.close();
}
~~~

If `work()` throws and `resource.close()` also throws, the final exception can **mask** the exception from `work()`. Furthermore, if closing one resource in `finally` throws, subsequent cleanup statements after it may be skipped. With TWR, Java handles multiple closes and suppressed exceptions consistently.

For investigation, log or display the **primary exception**, the **cause chain**, and **suppressed exceptions**. Inspecting only the final exception while ignoring suppressed ones easily loses evidence of failed resource cleanup.

**Suppressed does not mean unimportant**: a failed close can relate to unflushed data or unreleased resources. Applications need handling rules proportional to the operation's criticality while keeping the primary error to locate the first cause.

## 6. When a Wrapper Constructor Fails, Outer TWR Is Not Enough

Consider a factory creating a raw stream and then creating a wrapper:

~~~java
// Illustrative code snippet; UNSAFE if wrapping can fail.
InputStream raw = Files.newInputStream(path);
return createCustomWrapper(raw);
~~~

If `createCustomWrapper(raw)` throws an exception, the method fails to return a wrapper and `raw` stays open. The caller has no wrapper to close. You must ensure that **if ownership transfer fails, whoever opened raw closes raw itself**.

One technique is keeping ownership inside the factory during construction, transferring ownership only after creating the wrapper succeeds:

~~~text
factory opens raw       -> factory owns raw
factory creates wrapper -> may succeed/fail
  succeeds              -> return wrapper, transfer ownership to caller
  fails                 -> factory closes raw then rethrows original error
caller closes wrapper   -> wrapper closes raw per contract
~~~

For standard Java wrappers like `BufferedInputStream`, a simple constructor may not declare checked `IOException`; however, a custom decorator may validate headers, read metadata, open auxiliary files, or throw exceptions. **Never rely on a constructor looking simple to skip partial-acquisition cleanup rules.**

## 7. Runnable Program: Factory Rollback When Wrapper Fails

Create **`WrapperFactoryFailureDemo.java`**:

~~~java
import java.io.IOException;

public class WrapperFactoryFailureDemo {
    static final class Handle implements AutoCloseable {
        Handle() {
            System.out.println("acquire:raw");
        }

        @Override
        public void close() throws IOException {
            System.out.println("close:raw");
            throw new IOException("close-raw failed");
        }
    }

    static final class Wrapper implements AutoCloseable {
        private final Handle raw;

        Wrapper(Handle raw, boolean fail) throws IOException {
            System.out.println("construct:wrapper");
            if (fail) {
                throw new IOException("wrapper failed");
            }
            this.raw = raw;
        }

        @Override
        public void close() throws IOException {
            raw.close();
        }
    }

    static Wrapper create(boolean fail) throws IOException {
        Handle raw = new Handle();
        try {
            // Ownership transfers to Wrapper only when constructor returns.
            return new Wrapper(raw, fail);
        } catch (IOException | RuntimeException | Error primary) {
            try {
                raw.close();
            } catch (Throwable cleanupFailure) {
                primary.addSuppressed(cleanupFailure);
            }
            throw primary;
        }
    }

    public static void main(String[] args) {
        try (Wrapper wrapper = create(true)) {
            System.out.println("body");
        } catch (IOException primary) {
            System.out.println("primary=" + primary.getMessage());
            for (Throwable other : primary.getSuppressed()) {
                System.out.println("suppressed=" + other.getMessage());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 WrapperFactoryFailureDemo.java
java WrapperFactoryFailureDemo
~~~

Expected stdout:

~~~text
acquire:raw
construct:wrapper
close:raw
primary=wrapper failed
suppressed=close-raw failed
~~~

**Why is this right?**

1. `Handle` is opened: the factory holds ownership.
2. The `Wrapper` constructor starts and throws `IOException`, so **no complete `Wrapper` exists**; `try-with-resources` in `main` has no resource to close.
3. The factory catches the open/wrap failure and attempts to close `Handle` before propagating the error to the caller.
4. If closing `Handle` also throws, the factory adds the cleanup error to the **original exception's suppressed list**, without replacing the wrapper-failure cause.
5. If `Wrapper` constructs successfully, the factory returns `Wrapper` and the caller is responsible for closing it; the factory does not close `raw` on the success path because `Wrapper` now owns `raw`.

In this factory, the catch branch covers `IOException`, `RuntimeException`, and `Error` thrown during construction; catching `Throwable` in the inner block is solely to **retain cleanup failures** as suppressed. In production applications, consider severe errors like `VirtualMachineError` or `ThreadDeath` and the API's exception contract. This is a pattern illustrating ownership/cleanup, not advice to catch all `Throwable` and continue running normally.

**Design constraint:** the example assumes the wrapper **does not close `raw` itself when its constructor fails**. If a wrapper already takes ownership and cleans up `raw` before throwing, the factory and wrapper must agree on a contract to avoid double-close. Avoid assuming `close()` on every resource is safe to call repeatedly.

## 8. Self-Cleanup When a Constructor Opens Multiple Internal Resources

A constructor might open `A` then `B` before the object is fully built:

~~~text
new Composite():
    open A          -> succeeds
    open B          -> fails
    no Composite exists for caller.close()
~~~

The caller cannot use try-with-resources to close a `Composite` instance **that was never returned**. The constructor or factory building `Composite` must place `A`'s ownership inside a cleanup region before attempting `B`.

A more reliable solution in many designs is separating **factory resource acquisition** from a **constructor attaching already-valid references**, or using clearly scoped TWR. Structured pseudocode pattern:

~~~java
// Code snippet: createComposite takes resource ownership
// during construction. Types A/B/Composite assume matching APIs.
A a = openA();
try {
    B b = openB();
    try {
        return new Composite(a, b); // Transfer ownership on success
    } catch (IOException | RuntimeException | Error primary) {
        try {
            b.close();
        } catch (Throwable cleanup) {
            primary.addSuppressed(cleanup);
        }
        throw primary;
    }
} catch (IOException | RuntimeException | Error primary) {
    try {
        a.close();
    } catch (Throwable cleanup) {
        primary.addSuppressed(cleanup);
    }
    throw primary;
}
~~~

This is an **illustrative code snippet**, where types `A`, `B`, `Composite`, and `openA`/`openB` are application-defined. The goal is showing ownership scopes for `A` and `B` and the rollback mechanism as each step fails. In real APIs, encapsulate this logic into a clear-contract factory, thoroughly test failure paths, and avoid tangling deeply nested catch blocks.

Important: if `B`'s constructor **opens an internal handle itself and throws** before returning `B`, `B`'s own constructor/factory must clean up that handle. Outer catch blocks can only close `A` or instances of `B` that returned successfully.

### Using TWR When Results Do Not Outlive the Block

If resources only serve a local operation, TWR is the simplest choice:

~~~java
// Snippet inside a method with Path source, target.
try (var input = java.nio.file.Files.newInputStream(source);
     var output = java.nio.file.Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

If opening `output` fails, `input` closes automatically. If copying fails, both `output` and `input` are still attempted to be closed in reverse order. In this case, **there is no need to transfer stream ownership outward**.

Conversely, if you must **return a wrapper outward** for the caller to use after the factory ends, never place the raw stream inside a TWR that always closes upon leaving the factory. For instance, returning `new BufferedInputStream(raw)` from inside `try (raw)` returns a wrapper whose underlying stream is already closed. Use the factory ownership-transfer pattern described earlier.

## 9. When a Wrapper's close() Owns the Underlying Stream

Many standard Java wrappers also close the wrapped stream:

~~~java
// Snippet: BufferedInputStream owns underlying raw.
InputStream raw = Files.newInputStream(path);
BufferedInputStream wrapped = new BufferedInputStream(raw);
wrapped.close(); // Normally closes raw via wrapper too.
~~~

Once ownership has transferred to `wrapped`, the caller should **close `wrapped`** rather than independently closing both `wrapped` and `raw`. TWR with two nested resources can double-close `raw` if the wrapper already closed it first:

~~~java
// Understand the contract clearly because raw may be closed twice:
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream wrapped = new BufferedInputStream(raw)) {
    // ...
}
~~~

Standard library streams often tolerate repeated closes, yet for custom `AutoCloseable` types, double-close can be unsafe or cause side effects. If the goal is recovering from wrapper-creation failures, use explicit ownership contracts and factory rollback.

**Do not design a custom wrapper that closes a caller's resource if the caller only lent the resource**, unless the API explicitly states it. If the wrapper only borrows `raw`, the caller still closes `raw` under its own contract; pick one convention and apply it consistently.

## 10. Cleaning Up Temporary Files and Side Effects When Creating Multiple Resources

In Java I/O, resources are not just streams. An operation may:

1. Create a temporary directory/file.
2. Open an output stream for writing.
3. Wrap it in compression or encryption streams.
4. Write data.
5. Rename the temporary file to the target file.

If steps 2-4 fail, closing the stream alone **does not delete the temporary file**. You need **compensating cleanup** for side effects: delete that operation's temporary file, yet only when certain it was created by this operation and ownership was not handed elsewhere.

Example flow:

~~~text
create temp file -> write to temp -> close succeeds
                       |                 |
                       | error           v
                       v           publish/rename
                  close stream           |
                  delete temp if left    v
                                    result file
~~~

Use `Files.deleteIfExists(temp)` in appropriate cleanup; if deletion fails, preserve the primary error and record the cleanup error as well. Avoid deleting the target file or data that existed before the task began. For publish/rename steps, atomicity and durability guarantees also depend on the filesystem and dedicated design.

**Cleanup is not equivalent to rolling back all changes:** closing an `OutputStream` does not restore contents of a partially written file. When data integrity is needed, build in a temporary file, verify success, and only then publish.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Opening A and B before starting try/finally | If B fails, A can leak | Start TWR from resource A or use rollback cleanup |
| Assuming TWR closes objects a constructor never returned | Internal handles can still leak | Constructor/factory cleans up its own acquired resources |
| Closing in finally throws and masks original error | Loses the primary error cause | Prefer TWR and suppressed exceptions |
| Returning a wrapper from a factory inside TWR owning raw | Raw is closed before caller uses it | Transfer ownership when factory returns successfully |
| Both wrapper and caller closing the base stream | Can double-close | Publish one clear owner |
| Not closing source when creating a wrapper throws | Resource leak | Catch, close source, rethrow primary |
| Ignoring `getSuppressed()` | Loses close error details | Inspect primary, cause, and suppressed |
| Catching exception, logging only, and returning half-built object | Invalid object | Roll back and rethrow |
| Assuming close cannot fail | Misses flush or file/socket close errors | Have a policy for `IOException` on close |
| Closing resources in wrong dependency order | Wrapper uses already closed raw | Close in reverse ownership/dependency order |
| Only closing stream while leaving broken temp files | Leftover files or partial data | Clean up task-owned side effects too |
| Relying on GC to close I/O | No guarantee on release timing | Proactive TWR/closing |

## 12. Design and Verification Workflow

When writing resource-building/assembly code, ask yourself:

1. **What does each step create?** File descriptor, stream, buffer, temp file, socket, lock...
2. **Who owns it after creation succeeds?** The factory or the wrapper object?
3. **What happens if the next step fails?** Where is the previously created resource closed?
4. **What if closing also fails?** Is the primary exception preserved and the cleanup exception suppressed or reported separately per contract?
5. **On success, who closes at the end?** Does the caller take ownership via return value, or does the method close within scope?
6. **Are there side effects beyond closeable resources?** Temp files, transactions, renames, external state...
7. **Are there tests simulating every failure point?** Failure opening A, failure opening B, failure wrapping, body failure, failure closing A/B, and simultaneous dual-failure cases.

For multi-layered resources, draw an **ownership diagram** before optimizing. In a simple pipeline, TWR can handle everything; in a factory returning a wrapper externally, establish a clear ownership-transfer boundary. Never add a catch block just to close a resource already closed by TWR, as that can cause double-close and mask errors.

### Scenario-Based Behavior Check

| Scenario | Expected Behavior |
| --- | --- |
| Opening A fails before A is created | No A to close; A's factory must clean up anything opened internally |
| Opening A succeeds, opening B fails | A is closed; B's error is preserved |
| Body fails, closing B and A both fail | Body error is primary; B and A close errors are suppressed |
| Body succeeds, closing B fails, closing A succeeds | B's close error is reported; A is still closed |
| Wrapper construction fails after raw opens | Raw is closed under factory ownership |
| Wrapper construction succeeds | Caller closes wrapper; wrapper closes raw if it owns it |
| Temp file created successfully yet write fails | Stream is closed; task's temp file is cleaned up |
| Cleanup also fails | Preserve both primary and cleanup failure; never claim complete success |

## 13. Self-Check Exercises

**Question 1.** In `try (A a = openA(); B b = openB())`, if `openB` throws `IOException`, is `A` closed?  
**Answer:** Yes, if `openA` returned `A` successfully. TWR closes `A` when `B`'s initializer fails.

**Question 2.** If `B`'s constructor opened a `Socket` and then threw before returning `B`, can the caller's TWR close that `Socket`?  
**Answer:** Not automatically. `B` was never constructed, so `B`'s constructor/factory must clean up the internal `Socket`.

**Question 3.** The body throws `IOException`, and `A.close` also throws `IOException`: which error is primary in TWR?  
**Answer:** The error from the body remains primary; the close error is placed in `getSuppressed()`.

**Question 4.** A factory opens an `InputStream` and then creates a wrapper. If wrapper initialization fails, which owner must close the `InputStream`?  
**Answer:** The factory retains ownership until the wrapper is successfully returned; the factory must close the `InputStream` and propagate the original error.

**Question 5.** Should you write `try (InputStream raw = openRaw()) { return new BufferedInputStream(raw); }`?  
**Answer:** No if the wrapper is returned for the caller to read later; `raw` is closed when leaving `try`, leaving the wrapper without an open source.

**Question 6.** Is closing both the wrapper and the raw stream at the same time always safe?  
**Answer:** No. The wrapper may have already closed `raw`; custom resources may not support double-close. Establish one clear ownership rule.

**Question 7.** If a task partially writes a temp file and hits `IOException`, is closing the `OutputStream` alone enough to roll back?  
**Answer:** Not yet. Closing does not delete or restore file contents; you may need to delete the temp file and publish only after writing completes.

## 14. Java SE 17 References

- [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): close contract; some resource types do not safely support repeated closing.
- [Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): close interface for I/O.
- [Java Tutorial — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): closing resources in reverse order, suppressed exceptions.
- [Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): inspecting secondary errors thrown during cleanup.
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html): example of a wrapper owning an underlying input stream.

**Key Takeaway:** TWR automatically closes **successfully initialized** resources when later steps fail, while preserving primary and suppressed exceptions. However, if a constructor or factory opens internal resources and fails before returning the object, **internal cleanup is the responsibility of that constructor/factory itself**. When composing streams, define clearly when ownership transfers; when cleanup fails, preserve the original error alongside close-failure details.
