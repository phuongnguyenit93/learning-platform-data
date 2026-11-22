# Multiple Close Failures and Suppressed Exception Order in Java

> **Java Core – Exception** · Section: **Cause and Suppressed** · Java 7+ knowledge on `try-with-resources`, `Throwable.getSuppressed()`, and resource closing order; examples run with **Java 17+**.

## 1. The Problem to Solve

A Java block may open multiple resources: files, sockets, I/O streams, database connections, or custom objects implementing `AutoCloseable`. Even when the main operation fails, Java must still attempt to release all opened resources. However, **if multiple `close()` calls throw exceptions**, which error should the program report first? Is the main error lost, or is closing the remaining resources skipped?

The `try-with-resources` answer:

1. **Close in reverse order of declaration:** the rightmost resource is closed first, moving leftward.
2. **Attempt to close the remaining resources** even if a `close()` call throws an exception.
3. **Preserve the primary exception** (*main exception*) that already occurred in an initializer or the `try` body, if any.
4. **Attach errors from `close()` to the primary** using `Throwable.addSuppressed()`, to be retrieved with `getSuppressed()`.
5. **If there is no primary yet**, the first exception thrown during closing becomes the primary; subsequent closing exceptions are suppressed onto that exception.

As a result, a single primary exception object can carry **multiple suppressed exceptions**, rather than Java stopping cleanup after the first failure or throwing multiple independent exceptions simultaneously.

General example:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    doWork();
}
~~~

This is an illustrative code skeleton; types and methods must be defined to run standalone. If all resources open successfully, the closing order is **C → B → A**.

- If `doWork()` throws exception X and all three close calls fail, **X is the primary**; the suppressed list contains the close failures of **C, B, A** in the order they occurred.
- If `doWork()` succeeds but all three close calls fail, **the close failure of C is the primary**; suppressed contains only **the close failures of B, A**.
- If opening C fails, the body does not run, and C is not successfully registered for closing; B and A are still closed in the order **B → A**. **The failure to open C is the primary**, and the close failures of B/A are suppressed.

This lesson focuses on **multiple close failures and suppressed exception order**. Target skills: distinguishing *primary*, *suppressed*, and *cause*, accurately predicting close/exception order, and retrieving complete data when debugging.

## 2. Distinguishing Three Concepts: Primary, Suppressed, Cause

### Primary exception

The **primary** is the exception holding the main role on the failure path. With try-with-resources, it is usually the exception thrown **before closing begins** (from an initializer or the `try` body). If all preceding steps succeed, the **first** error in the closing sequence becomes the primary.

The primary is the object delivered to the matching `catch` branch, if caught. It is **not necessarily** the first exception that occurred in the entire application: closing may run after successful steps, and the caller may also wrap the exception in another wrapper. Always evaluate within **the scope of a single try-with-resources statement**.

### Suppressed exception

An exception thrown during cleanup can be **suppressed** onto the primary so that it does not mask the cause currently being handled. API:

~~~java
Throwable[] extra = primary.getSuppressed();
~~~

returns an array of `Throwable` objects attached as suppressed exceptions. The element at index 0 is the exception added to the list **earliest**; subsequent elements reflect the order in which they were added.

In the closing sequence C → B → A, if a primary already exists and all three close calls fail:

~~~text
primary       = body failed
suppressed[0] = close C failed
suppressed[1] = close B failed
suppressed[2] = close A failed
~~~

This is an example for the scenario just described, not a rule that *every* suppressed exception in Java comes from `close()`. Application code can call `addSuppressed()` itself; a library may also append information according to its own policy. The array order is the **insertion order**, while the C/B/A order is the specific outcome of how try-with-resources closes resources.

### Cause

`getCause()` represents the **exception that caused** another exception in an *exception chaining* relationship:

~~~java
throw new IllegalStateException("Cannot save document", ioFailure);
~~~

This is illustrative code, assuming `ioFailure` is a suitable Throwable. The new `IllegalStateException` wrapper has **cause = ioFailure**. By contrast, suppressed exceptions are a secondary list **on a Throwable object**, not a single cause link.

| Property | Meaning | Retrieval API |
| --- | --- | --- |
| Primary | The main exception thrown out of a handling scope | The object received in `catch` |
| Cause | The underlying cause linked when creating/wrapping an exception | `ex.getCause()` |
| Suppressed | Secondary exceptions attached to the same object, typically from cleanup | `ex.getSuppressed()` |

**Do not use the terms “cause” and “suppressed” interchangeably**: a single primary can have both a cause and multiple suppressed exceptions; each suppressed exception also has its own stack trace and cause.

## 3. Closing Order Rule: Right to Left, Even When Close Fails

Resources in the header are initialized from **left to right**, but closed from **right to left**. Example:

~~~java
try (Resource a = open("A");
     Resource b = open("B");
     Resource c = open("C")) {
    work();
}
~~~

This is a non-standalone illustrative example. Timeline if all resources are initialized:

~~~text
open A
open B
open C
work
close C    ← called first
close B    ← still called if close C throws an exception
close A    ← still called if close B throws an exception
~~~

The reason is that try-with-resources semantics are mechanically equivalent to nested resource scopes: the resource opened last is closed first, in *last in, first out* fashion.

This order **also determines the suppressed exception order**. For example, if the body already threw X and C, B, and A all throw when closing, Java encounters C's close error first, then B's, then A's; errors are added to suppressed in that same order.

If a resource reference is `null`, automatic closing **does not call** `close()` on it. If closing a resource completes normally, it **contributes no exception** to suppressed. Therefore, the suppressed entries can be fewer than the number of declared resources.

## 4. Complete Java 17 Program and Verified Stdout

Save the entire program as **`SuppressedCloseOrderDemo.java`**. Every example uses the same `TracedResource` class that can deliberately fail in the initializer or `close()`; messages are hardcoded so output does not depend on filesystem files.

~~~java
import java.io.IOException;

public class SuppressedCloseOrderDemo {
    private static final class TracedResource implements AutoCloseable {
        private final String name;
        private final boolean failClose;

        private TracedResource(String name, boolean failOpen, boolean failClose)
                throws IOException {
            System.out.println("open " + name);
            if (failOpen) {
                throw new IOException("open " + name + " failed");
            }
            this.name = name;
            this.failClose = failClose;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static TracedResource open(
            String name, boolean failOpen, boolean failClose)
            throws IOException {
        return new TracedResource(name, failOpen, failClose);
    }

    private static void report(IOException ex) {
        System.out.println("primary=" + ex.getMessage());
        Throwable[] suppressed = ex.getSuppressed();
        for (int i = 0; i < suppressed.length; i++) {
            System.out.println("suppressed[" + i + "]="
                    + suppressed[i].getMessage());
        }
    }

    private static void bodyFails() {
        System.out.println("== body fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, true)) {
            System.out.println("body");
            throw new IOException("body failed");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void closeOnlyFails() {
        System.out.println("== close only fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, true)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void openFails() {
        System.out.println("== open fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", true, true)) {
            System.out.println("unreachable body");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void middleCloseFails() {
        System.out.println("== middle close fails ==");
        try (TracedResource a = open("A", false, true);
             TracedResource b = open("B", false, true);
             TracedResource c = open("C", false, false)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
    }

    private static void clean() {
        System.out.println("== clean ==");
        try (TracedResource a = open("A", false, false);
             TracedResource b = open("B", false, false)) {
            System.out.println("body ok");
        } catch (IOException ex) {
            report(ex);
        }
        System.out.println("after");
    }

    public static void main(String[] args) {
        bodyFails();
        closeOnlyFails();
        openFails();
        middleCloseFails();
        clean();
    }
}
~~~

### Compile and run

Use JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 SuppressedCloseOrderDemo.java
java SuppressedCloseOrderDemo
~~~

**Exact stdout** verified after compiling and running:

~~~text
== body fails ==
open A
open B
open C
body
close C
close B
close A
primary=body failed
suppressed[0]=close C failed
suppressed[1]=close B failed
suppressed[2]=close A failed
== close only fails ==
open A
open B
open C
body ok
close C
close B
close A
primary=close C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
== open fails ==
open A
open B
open C
close B
close A
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
== middle close fails ==
open A
open B
open C
body ok
close C
close B
close A
primary=close B failed
suppressed[0]=close A failed
== clean ==
open A
open B
body ok
close B
close A
after
~~~

The program was compiled with `javac --release 17` and executed to verify the output. No input files, external libraries, or JUnit runs are required. All failure scenarios are caught and printed in a consistent format.

## 5. Explaining the Case Where the Body Fails and All Three Closes Also Fail

The `bodyFails()` method opens A, B, and C successfully; the `try` body prints `body` and then throws:

~~~java
throw new IOException("body failed");
~~~

At that point, the primary already exists **before the closing phase begins**. Java proceeds in order:

1. Calls `c.close()`, prints `close C`, receives `IOException("close C failed")`, and adds it to the suppressed list of the body exception.
2. Calls `b.close()`, prints `close B`, receives `IOException("close B failed")`, and adds it as the next suppressed exception.
3. Calls `a.close()`, prints `close A`, receives `IOException("close A failed")`, and adds it as the third suppressed exception.
4. Delivers the primary `IOException("body failed")` to `catch`; the handler prints the primary and iterates over the suppressed array.

**Required order in this construct:**

~~~text
primary=body failed
suppressed[0]=close C failed
suppressed[1]=close B failed
suppressed[2]=close A failed
~~~

This is why it is important to read **both primary and suppressed**. If you only print `ex.getMessage()`, you only see `body failed` and lose track of the three issues during closing.

**Do not misunderstand:** there are no three independent `throw` statements exiting the method at once. Java continues performing cleanup and attaches the closing exceptions to a single primary.

## 6. Explaining the Case Where Only Close Fails

In `closeOnlyFails()`, all resources initialize successfully and the `try` body prints `body ok`, with no exception before closing begins.

- C closes first and throws. Because there is no primary yet, `close C failed` is chosen as the **primary**.
- B closes next and also throws; B's error is suppressed onto C's error.
- A closes last and also throws; A's error is the second suppressed exception.

Output:

~~~text
primary=close C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

**The first close failure is not `suppressed[0]`**, because when there is no prior error, the first close failure **is already the primary**. This differs from Section 5, where the primary originated from the `try` body, so all close errors belonged in suppressed.

Hence, you cannot conclude that a successful body means the method definitely succeeded: `close()` can turn an apparently normal execution into an exception.

## 7. Explaining the Case Where the Last Initializer Fails

In `openFails()`:

~~~java
try (TracedResource a = open("A", false, true);
     TracedResource b = open("B", false, true);
     TracedResource c = open("C", true, true)) {
    System.out.println("unreachable body");
}
~~~

This is an excerpt from the full program and requires `catch`/`throws` as shown above. A and B open successfully. C starts initializing and prints `open C`, but the constructor throws `IOException("open C failed")` **before returning** a valid `TracedResource`.

Consequences:

- **The body does not run**, so there is no `unreachable body` line.
- **C is not automatically closed** by this resource specification, because C's initializer did not complete and never handed over resource C to be managed. There is no `close C` in stdout.
- **B and A were successfully registered**, so they are still closed, in the order B → A.
- The failure to open C is the primary; the close failures of B and then A are suppressed in order.

~~~text
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

You must distinguish between **an initializer that has started executing** and **a resource that has been successfully initialized**. If a factory internally opens a file or socket and fails before handing over the resource, the caller cannot know about those intermediate resources. The factory/constructor must design its own cleanup.

## 8. If the Outermost Resource Closes Successfully, Where Do Suppressed Exceptions Start?

In `middleCloseFails()`:

- C closes first and **does not fail**.
- B closes next, **throwing the first error** → B's error is the primary.
- A closes last and also fails → A's error is suppressed.

~~~text
primary=close B failed
suppressed[0]=close A failed
~~~

Because C did not throw an exception, C **does not appear in the suppressed array**. The length of suppressed **does not have to equal the number of declared resources**, nor the number of closed resources. Only exceptions actually added to the list appear.

In the `clean()` branch, opening, body, and closing all complete normally, so **there is no primary and no suppressed**. The program prints `after` once all resources are closed. This serves as a control case showing that cleanup runs even when no error occurs.

## 9. Decision Table for Determining Primary and Suppressed

Assume the header declares A, B, C from left to right. Each row is an independent run:

| Scenario | Close order attempted | Primary | Suppressed list in order |
| --- | --- | --- | --- |
| Body throws X, C/B/A all fail close | C, B, A | X | C, B, A |
| Body succeeds, C/B/A all fail close | C, B, A | C failure | B, A failures |
| Body succeeds, C closes ok, B/A fail | C, B, A | B failure | A failure |
| Body succeeds, C/B close ok, A fails | C, B, A | A failure | Empty |
| C fails on init, B/A fail close | B, A | Open C failure | B, A failures |
| B fails on init, A fails close | A | Open B failure | A failure |
| Body throws X, all closes succeed | C, B, A | X | Empty |
| Body and all closes succeed | C, B, A | None | None |

**Deduction formula:** Write down the resources **that initialized successfully**. Reverse that list to find the `close()` sequence. If there is an exception from the body/initializer, keep it as the primary; every close failure goes into suppressed. If there is no main exception yet, the first close failure becomes the primary; subsequent close failures go into suppressed.

This table assumes exceptions are created normally, suppression is enabled (the default for standard exceptions in the examples), no other code manually calls `addSuppressed()`, and no new exception from an outer `catch`/`finally` replaces the control flow.

## 10. Why Does Java Still Attempt to Close Remaining Resources?

The try-with-resources model is equivalent in closing behavior to **nested resource scopes**, each with its own cleanup:

~~~java
try (Resource a = openA()) {
    try (Resource b = openB()) {
        try (Resource c = openC()) {
            doWork();
        }
    }
}
~~~

This is an illustrative structure; appropriate types/methods must be defined. Observably, resources in the same header are handled like that nested structure, which is why the last-created resource leaves scope first.

One way to illustrate the idea for **a single** resource (*pseudocode*, not a verbatim copy of compiler-generated code):

~~~java
Throwable primary = null;
try {
    body();
} catch (Throwable error) {
    primary = error;
    throw error;
} finally {
    if (resource != null) {
        if (primary != null) {
            try {
                resource.close();
            } catch (Throwable closeError) {
                primary.addSuppressed(closeError);
            }
        } else {
            resource.close();
        }
    }
}
~~~

Variables/methods in the pseudocode are symbolic. With multiple resources, the nested scopes continue closing from the inside out even when an inner resource throws, so one close failure does not mean skipping the remaining resources.

This contrasts with manually calling close without exception handling:

~~~java
c.close();
b.close();
a.close();
~~~

If `c.close()` throws an exception on the first line, the two calls `b.close()` and `a.close()` **might not run**. Even when using a manual `finally`, accurately reproducing the primary/suppressed mechanism of try-with-resources requires careful error management and is prone to missing or masking the root cause.

## 11. What Does getSuppressed() Return and How to Iterate Over It?

`Throwable.getSuppressed()` returns a `Throwable[]` array containing the objects attached to that exception. A primary may have 0, 1, or more suppressed exceptions.

Example:

~~~java
catch (IOException ex) {
    System.err.println("PRIMARY: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("SUPPRESSED: " + suppressed);
    }
}
~~~

This is an illustrative handler within an appropriate `try` context, not a standalone program.

### What does the order in the array mean?

By API contract, suppressed exceptions are returned in the **order they were suppressed/added**. Try-with-resources closes in reverse order of declaration, so if every resource throws on close and a primary already exists, the array order usually matches the **order of the close failures**.

For example, if C, B, and A all throw:

~~~text
getSuppressed()[0] → C.close() failure
getSuppressed()[1] → B.close() failure
getSuppressed()[2] → A.close() failure
~~~

However, if `C.close()` succeeds, there is no entry for C. If the body already called `primary.addSuppressed(extra)` manually before cleanup, the list may **contain `extra` before the close errors**. Therefore, you should not infer a specific resource solely from an array index without knowing how the exception was constructed.

### Can you call addSuppressed manually?

Yes. The API:

~~~java
primary.addSuppressed(other);
~~~

attaches another `Throwable` to `primary` when suppression is enabled. It is useful in custom cleanup mechanisms, but you **should not manually re-add close errors** already added by try-with-resources, as that causes duplicates and distorts interpretation.

API rules to remember:

- `addSuppressed(null)` throws `NullPointerException`.
- `primary.addSuppressed(primary)` throws `IllegalArgumentException` because self-suppression is not allowed.
- By default, standard exceptions enable suppression. If an exception is created with suppression disabled, `addSuppressed()` does not store additional suppressed exceptions.
- `getSuppressed()` returns a new array on every call; mutating the returned array does not affect the internal list of the exception.

These properties help distinguish suppressed exceptions from an application-managed collection. In typical business code, **reading suppressed exceptions for diagnostics** is far more common than calling `addSuppressed` manually.

## 12. Printing Stack Traces So Suppressed Errors Are Not Missed

If a program only logs:

~~~java
System.err.println(ex.getMessage());
~~~

it is impossible to tell how many suppressed exceptions the primary has, nor to see the originating stack trace of each error. For debugging, keep the full `Throwable` object when logging:

~~~java
ex.printStackTrace();
~~~

Per the Java API, `printStackTrace()` displays the primary exception, its causes, and associated suppressed exceptions, with indentation to distinguish them.

Illustrative format example:

~~~text
java.io.IOException: body failed
    at ...
    Suppressed: java.io.IOException: close C failed
        at ...
    Suppressed: java.io.IOException: close B failed
        at ...
    Suppressed: java.io.IOException: close A failed
        at ...
~~~

**This is not verbatim output.** Frame counts, line numbers, class names, and elisions like `... N more` depend on the call stack and JVM formatting. You should not write tests that compare the entire `printStackTrace()` output verbatim.

With a suitable logging framework, pass the **exception object** to the logger rather than just its message; for example, with `java.util.logging`:

~~~java
logger.log(java.util.logging.Level.SEVERE, "Processing failed", ex);
~~~

This is an illustrative snippet assuming a `logger` variable is already declared. A good observability setup should capture **primary, cause, suppressed, and stack trace** while still complying with policies against logging sensitive data.

## 13. Cause and Suppressed When Wrapping Exceptions

Suppose a processing layer does not want to expose `IOException` directly to the caller, so it wraps it:

~~~java
try {
    executeWork();
} catch (IOException ex) {
    throw new IllegalStateException("Batch processing failed", ex);
}
~~~

This is illustrative code, assuming `executeWork()` is declared to throw `IOException`.

If `ex` has three suppressed exceptions, the new wrapper has:

- `wrapper.getCause() == ex`.
- `ex.getSuppressed()` still contains the three close errors.
- `wrapper.getSuppressed()` **does not automatically copy** those three errors onto the wrapper.

To inspect the close errors, an investigator must follow **cause** to reach `ex` and then inspect `getSuppressed()` on it. If you only check `getSuppressed()` on the new wrapper, the array will very likely be empty. This is why logging tools should support the **entire Throwable tree**, not just the outermost exception.

**Do not blindly copy suppressed exceptions onto the wrapper**: having the same error appear multiple times can cause duplicate logs and alter the causal structure. Keeping the original exception as the cause usually preserves the data already.

## 14. When Suppression Is Disabled

A subclass of `Throwable` can use the protected constructor to set `enableSuppression=false`:

~~~java
class NoSuppressionException extends Exception {
    NoSuppressionException(String message) {
        super(message, null, false, true);
    }
}
~~~

This is an illustrative class definition, which can be placed at top level or inside another class. The third argument `false` **disables suppression**, while the fourth argument `true` still allows recording the stack trace. These two features are independent.

If a `NoSuppressionException` is the primary in the body and subsequent close calls throw:

- Java still executes the closing mechanism for opened resources.
- It still attempts to suppress the close errors onto the primary according to the standard rules.
- Because **the primary has suppression disabled**, the close errors are not stored in the suppressed array.
- `primary.getSuppressed().length` will be 0.

This is crucial when debugging a system that uses custom exceptions: **an empty suppressed array is not absolute proof that all closes succeeded**. Suppression may have been disabled by the exception's design.

Do not disable suppression or stack traces on business exceptions purely for performance optimization without considering diagnosability. If observing multiple cleanup failures matters, keep suppression enabled.

## 15. What If an Outer finally Throws?

Given:

~~~java
try (Resource a = openA(); Resource b = openB()) {
    work();
} catch (IOException ex) {
    report(ex);
} finally {
    after();
}
~~~

This is a non-standalone illustrative structure. Closing `a`/`b` occurs **before the `catch`/`finally` of the extended try-with-resources** handles the result. After cleanup and error handling, an outer `finally` still executes according to Java rules.

If that outer `finally` itself throws another exception, the final control-flow outcome may switch to the new exception; that is **the `finally` rule**, separate from the suppression mechanism performed by try-with-resources.

In production code, avoid complex manual cleanup in `finally` when try-with-resources is already in use, and do not use `return` inside `finally` in a way that accidentally masks an exception carefully preserved from resource cleanup.

## 16. Opening Resources Can Also Fail Before the Body Starts

Suppressed exceptions are not limited to cases where the body ran. If initializing the third resource fails, earlier resources are still closed and may throw exceptions. In the `openFails()` example:

~~~text
open A
open B
open C
close B
close A
primary=open C failed
suppressed[0]=close B failed
suppressed[1]=close A failed
~~~

B and A are closed even though the `try` body **was never entered**. Therefore, if a program encounters a connection/file initialization failure, you **must still inspect suppressed** to see whether previously opened connections/files were released cleanly.

Conversely, C's initializer started but did not return resource C successfully, so this construct does not attempt `C.close()`. If factory C opened an intermediate resource and then failed, cleanup responsibility lies with the factory itself, not with the resource specification that never received C.

## 17. Relevance of the Close Exception Type

`AutoCloseable.close()` is declared to throw `Exception`. A concrete class often narrows this type, as in `TracedResource.close() throws IOException`. During compile-time checked exception analysis, Java considers exceptions that can come from the initializer, body, and close.

Thus, an example like:

~~~java
static void handle() throws IOException {
    try (TracedResource resource = open("R", false, true)) {
        System.out.println("work");
    }
}
~~~

is an illustration based on the `TracedResource` class from the main program. This method must declare or handle `IOException`, even though the body only prints text, because the initializer/close can still throw `IOException`.

If a resource has static type `AutoCloseable` and `close()` is declared to throw `Exception`, you may need to handle or declare a broader checked type. Multi-catch or separate `catch` clauses still apply according to subtype relationships.

Not every close failure is an `IOException`: implementations may throw unchecked exceptions. The primary/suppressed mechanism operates on the actual `Throwable`s thrown; check the resource's contract.

## 18. Common Misconceptions

- **“When multiple closes fail, the last error wins.”** False: if the body/initializer already failed, it remains the primary; if not, **the first close failure** is the primary.
- **“Suppressed always starts with the error from the first resource closed.”** Only true if a primary already existed before closing; if not, the first close failure itself is the primary.
- **“Resources declared first are closed first.”** False: closing proceeds from **right to left**.
- **“If B.close fails, A.close does not run.”** False for try-with-resources: Java still attempts to close earlier resources.
- **“If the body runs normally, no exception is thrown.”** False: `close()` can produce the primary.
- **“If the last initializer fails, no resources are closed.”** False: earlier resources that initialized successfully are closed.
- **“A failing initializer is still automatically closed.”** Not if it failed before handing over a successfully initialized resource; the factory must clean up internally.
- **“A suppressed error is a lost error.”** False: normally it can be retrieved via `getSuppressed()`.
- **“Suppressed and cause are the same list.”** False: `getCause()` is the causal link; `getSuppressed()` returns the array of suppressed exceptions.
- **“Wrapping the primary in a wrapper automatically moves suppressed to the wrapper.”** False: suppressed exceptions on the primary are preserved when the primary becomes the cause, not copied as suppressed on the wrapper.
- **“Modifying an element in the array from getSuppressed mutates the original Throwable.”** False: the getter returns a fresh array.
- **“An empty suppressed array proves close had no errors.”** Not necessarily; suppression may have been disabled.
- **“With three resources, there are always three suppressed exceptions.”** False: resources that close cleanly produce no error; when there is no prior primary, the first close failure becomes the primary.
- **“Printing only IOException's message is enough.”** You easily lose suppressed exceptions, the cause, and stack traces.
- **“Try-with-resources automatically rolls back file/database writes.”** False: it manages resource closing, not transactions.
- **“An outer finally always preserves an existing primary.”** If `finally` itself throws or returns abnormally, it can mask or alter control flow.

## 19. How to Solve an Output-Prediction Problem Yourself

For any problem with multiple resources, proceed step by step:

1. **List the initializers** from left to right, marking the first initializer that does not complete normally, if any.
2. **Record the resources that opened successfully**. If the *n*-th initializer fails, initializers after *n* do not run.
3. **Determine whether the body runs**, and whether the body throws any exception.
4. **Determine the initial primary**: the initializer/body exception if any; otherwise, there is no primary before closing.
5. **Reverse the list of successfully opened resources** to get the closing order (rightmost first).
6. **Walk through each close in order**. If close succeeds: add no error. If close fails and there is no primary yet: make it the primary. If a primary already exists: attach it to suppressed (unless suppression is disabled or an API edge case applies).
7. **Only after cleanup, evaluate any outer catch/finally**; check whether the handler alters or propagates the exception.
8. **Write stdout in chronological order of occurrence**, not by `catch` declaration order or left-to-right resource order.

### Exercise 1

Declare A, B, C. Body throws X; `C.close()` succeeds; `B.close()` throws Y; `A.close()` throws Z. What are primary and suppressed?

**Answer:** primary X; suppressed [Y, Z]. The closing order is still C → B → A, but C contributes no suppressed exception because it did not fail.

### Exercise 2

Declare A, B, C. Body succeeds; `C.close()` throws X; `B.close()` throws Y; `A.close()` succeeds.

**Answer:** primary X; suppressed [Y]. `A.close()` is still called despite the two previous failures.

### Exercise 3

A opens successfully; B fails to initialize with X; `A.close()` throws Y.

**Answer:** the body does not run. Primary X; suppressed [Y]. B is not automatically closed if it did not initialize successfully.

### Exercise 4

Body throws X, and the closes throw Y then Z. Later, code wraps X with `new IllegalStateException("failed", X)`. Where are Y and Z?

**Answer:** Y and Z are suppressed on X. The new wrapper has cause X; the wrapper's suppressed list does not automatically contain Y/Z.

### Exercise 5

Body succeeds, C closes normally, B fails close with X, A fails close with Y. Can we write `suppressed[0]=X`?

**Answer:** No. X is the **primary**; `suppressed[0]` is Y.

### Exercise 6

A primary is created with suppression disabled; body throws primary, and both `A.close()` and `B.close()` fail. Can you rely on `getSuppressed().length == 0` to claim both closes succeeded?

**Answer:** No. Cleanup exceptions may not have been recorded because suppression was disabled.

## 20. Official Java Documentation

- [Java SE 17 JLS – try-with-resources (Section 14.20.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource specification syntax, resource lifecycle, and cleanup.
- [Java SE 17 JLS – basic try-with-resources (Section 14.20.3.1)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1): equivalence to nested `try` blocks, primary and suppressed.
- [Java SE 17 JLS – extended try-with-resources (Section 14.20.3.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2): combining cleanup with `catch` and `finally`.
- [Java SE 17 API – Throwable.addSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#addSuppressed(java.lang.Throwable)): rules for attaching suppressed exceptions.
- [Java SE 17 API – Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): suppressed exception array and return order.
- [Java SE 17 API – AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): contract of the `close()` method.
- [Oracle Java Tutorials – try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): basic examples of primary and suppressed; for version-specific precision, prefer the Java 17 JLS.

**Conclusion:** When multiple resources are present, Java closes them in **reverse order of declaration** and still attempts to close the rest if one close fails. If an exception already occurred in an initializer or the body, that exception is the **primary**, and close failures are added to suppressed in the order they occur. If only closing fails, **the first close failure is the primary**, and subsequent failures are suppressed. For thorough debugging, inspect **primary, cause, suppressed, and stack trace**, not just the main error's message.