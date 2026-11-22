# Resources Are Closed on `return` or Abrupt Exit in `try-with-resources`

In Java, `try-with-resources` manages the lifecycle of `AutoCloseable` objects within an **execution scope**. When the program leaves this scope, Java automatically calls `close()` on all successfully initialized resources, even if the `try` body does not reach its closing curly brace.

Notable exit paths include **`return`**, **`throw`**, **`break`**, and **`continue`**. This does not merely mean "Java tries to close the resource": the closing order, exceptions thrown by `close()`, and the final outcome delivered to the caller all follow specific rules.

**Core rules:**

- A `return` inside a `try-with-resources` body **does not skip `close()`**. The resource is closed before the caller receives the result.
- If the body throws an exception, Java still closes the opened resources; if `close()` also throws, the close error is normally **suppressed** under the primary exception.
- If the body intends to `return` but `close()` throws an error, the caller **may receive the exception instead of the return value**.
- With multiple resources, Java initializes them in declaration order and closes them in **reverse order**.
- Do not infer that a resource is guaranteed to be closed in every case where the process/JVM is forcibly terminated; this is a mechanism tied to Java's execution flow, not a guarantee that survives every system failure.

## 1. Syntax and Contract of `AutoCloseable`

Basic form:

```java
try (Resource resource = openResource()) {
    use(resource);
}
```

This is an **illustrative skeleton**, requiring `Resource` to implement `AutoCloseable` and the referenced methods to be defined. `resource` is declared in the *resource specification*, which is the part between the parentheses after `try`.

The `java.lang.AutoCloseable` interface defines the `close()` method. Many Java APIs such as `InputStream`, `Reader`, `Writer`, `Scanner`, and `java.sql.Connection` provide compatible resources. When using `try-with-resources`:

1. Java evaluates the resource initialization expression.
2. If initialization succeeds, the resource is registered to be closed when leaving the scope.
3. The `try` body is executed.
4. When preparing to leave the block, Java calls `close()` on the resources that need to be closed.
5. After the closing step, control transfers to `catch`, `finally`, or the caller according to the final completion reason.

You can combine it with `catch` and `finally`:

```java
try (Resource resource = openResource()) {
    use(resource);
} catch (SomeException ex) {
    handle(ex);
} finally {
    afterAttempt();
}
```

This is also an **illustrative skeleton**, not a standalone Java program. One key point: with `catch`/`finally` attached to the same construct, the **resource-closing step occurs before that handler or `finally` runs**.

There is no need to manually call `resource.close()` in `finally` just to ensure closing. Doing so easily leads to double closing and makes cleanup error handling harder.

## 2. What Does "Abrupt Completion" Mean?

A Java statement or block can either **complete normally** (*normal completion*) or **complete abruptly** (*abrupt completion*).

Examples of abrupt completion reasons:

| Cause | Example | Control-flow consequence |
| --- | --- | --- |
| `return` | `return result;` | Prepares to exit the method |
| `throw` | `throw new IOException(...);` | Prepares to propagate the exception |
| `break` | `break;` | Prepares to exit the matching loop/`switch` |
| `continue` | `continue;` | Prepares to jump to the next iteration |
| Exception from a call | `readLine()` throws `IOException` | Current statement completes abruptly |

`try-with-resources` is designed to **close resources along those exit paths**. It does not wait for execution to reach the closing `}` of the body via the normal path before calling `close()`.

Example:

```java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

This is a **valid illustrative method when placed inside a Java class**. `reader.readLine()` is evaluated to prepare the result, but before the caller receives the `String`, Java closes the reader. If either reading or closing throws `IOException`, the method may throw the exception instead of returning the result.

**Do not confuse:** a resource still being in scope in another block does not mean it remains open after its managing block has ended. When using `try (existingResource)` with a variable declared outside, the variable name may even remain usable, but the object has already been closed.

## 3. `return` in the Body: Closing Before the Method Returns

Consider:

```java
static int calculate() {
    try (TrackedResource resource = new TrackedResource()) {
        return 42;
    }
}
```

This is **illustrative code**, assuming `TrackedResource implements AutoCloseable` and `close()` has an appropriate contract.

Logical flow:

```text
open resource
    ↓
enter try body
    ↓
evaluate return expression 42
    ↓
Java calls resource.close()
    ↓
if close completes normally
    ↓
caller receives 42
```

If `close()` throws an unhandled exception, the path changes: `return 42` can be **replaced by the exception from `close()`**. Therefore, saying "when `return` is hit, the resource is still closed" is true, but incomplete. You must also ask "did `close()` succeed?" to know what the caller actually receives.

### The `return` Value Is Computed Before Closing

With a return expression:

```java
try (Resource resource = openResource()) {
    return compute(resource);
}
```

the semantic order is **compute `compute(resource)`**, prepare the value, then close the resource, and only then complete the return if no other completion reason intervenes.

If `compute(resource)` throws an exception before producing a result, Java still closes the resource and continues along the exception path.

This also explains why returning an **independent value** such as an `int`, an already-read `String`, or a materialized DTO is usually more appropriate than returning an object that still requires the resource to stay open. Do not return a lazily reading `Stream` or iterator if the underlying data source is closed before the caller consumes it.

## 4. Complete Java 17+ Example: `return`, `throw`, `break`, `continue`

To observe the exact sequence without depending on files or the operating system, use a mock resource that prints when opened and closed.

Save the file **`ResourceExitFlowDemo.java`**:

```java
public class ResourceExitFlowDemo {

    static final class Trace implements AutoCloseable {
        private final String name;

        Trace(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    static int returnCase() {
        System.out.println("CASE return");

        try (Trace first = new Trace("A");
             Trace second = new Trace("B")) {
            System.out.println("body: prepare return 7");
            return 7;
        }
    }

    static void throwCase() {
        System.out.println("CASE throw");

        try (Trace resource = new Trace("T")) {
            System.out.println("body: throw");
            throw new IllegalArgumentException("bad request");
        } catch (IllegalArgumentException ex) {
            System.out.println("catch: " + ex.getMessage());
        }
    }

    static void breakCase() {
        System.out.println("CASE break");

        for (int i = 0; i < 2; i++) {
            try (Trace resource = new Trace("break-" + i)) {
                System.out.println("body: break at " + i);
                break;
            }
        }

        System.out.println("after break loop");
    }

    static void continueCase() {
        System.out.println("CASE continue");

        for (int i = 0; i < 2; i++) {
            try (Trace resource = new Trace("continue-" + i)) {
                System.out.println("body: continue at " + i);
                continue;
            }
        }

        System.out.println("after continue loop");
    }

    public static void main(String[] args) {
        System.out.println("returned=" + returnCase());
        throwCase();
        breakCase();
        continueCase();
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 ResourceExitFlowDemo.java
java ResourceExitFlowDemo
```

**Exact stdout:**

```text
CASE return
open A
open B
body: prepare return 7
close B
close A
returned=7
CASE throw
open T
body: throw
close T
catch: bad request
CASE break
open break-0
body: break at 0
close break-0
after break loop
CASE continue
open continue-0
body: continue at 0
close continue-0
open continue-1
body: continue at 1
close continue-1
after continue loop
```

### Branch-by-Branch Analysis

**`returnCase()`:**

- Opens A then B in declaration order.
- The body executes `return 7`.
- Java closes B then A (**reverse declaration order**).
- Only after both `close()` calls complete normally does the caller print `returned=7`.

If `return` bypassed closing, the two `close` lines would not appear before `returned=7`. The example proves the opposite.

**`throwCase()`:**

- The body throws `IllegalArgumentException`.
- Before the `catch` handler attached to the same construct handles the exception, Java calls `close T`.
- The handler prints `catch: bad request`, meaning it receives the exception from the body after the resource has been closed.

**`breakCase()`:**

- The loop starts at `i=0`, and resource `break-0` is created.
- `break` requests leaving the loop, but Java **closes the resource first**.
- Iteration `i=1` does not run; then `after break loop` is printed.

**`continueCase()`:**

- In each iteration, a resource is opened in that iteration's own `try`.
- `continue` requests jumping immediately to the next step of the loop, but first the current resource is closed.
- Thus the order is always open → use → close for each iteration, before moving to the next iteration.

Both loop-exit forms trigger closing. However, if `close()` throws an exception, the `break` or `continue` path **can be replaced by an exception-throwing path**, instead of transferring to the intended target.

## 5. When the Body Throws an Exception, `close()` Runs Before the Outer Handler

With:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    throw new IllegalArgumentException("invalid content");
} catch (IllegalArgumentException ex) {
    System.out.println("caught: " + ex.getMessage());
}
```

This is an **illustrative snippet**, requiring a `path` variable of type `Path`, and handling/declaring the checked `IOException` that may arise when opening/closing the reader. The body throws an unchecked exception, yet that does not skip `reader.close()`.

For a `try-with-resources` with an attached `catch`, the intuitive equivalent flow is:

```text
open resource
  → run try body
  → exception occurs
  → close resource
  → select construct's catch
  → handle or continue propagating
```

This is useful when `catch` logs an error after an operation: the resource registered in the construct has already gone through the closing step before the handler runs. However, you must **not** conclude that closing always succeeded; if `close()` failed, you need to inspect the exception or suppressed exceptions.

### Does It Differ If the Handler Is at an Outer Level?

Suppose:

```java
try {
    try (Resource resource = openResource()) {
        doWork(resource);
    }
} catch (RuntimeException ex) {
    recoverOrReport(ex);
}
```

This is an **illustrative skeleton**. When an unchecked exception escapes the inner `try`, the resource is closed before control transfers to the outer handler. Nested handling scopes do not disable automatic closing, because each `try-with-resources` protects the lifecycle of its own resources.

## 6. If `close()` Throws When the Body Intends to `return`

This is a case that is easy to misunderstand:

```java
static int compute() {
    try (FailingResource resource = new FailingResource()) {
        return 123;
    }
}
```

Suppose `FailingResource.close()` throws `IllegalStateException("close failed")`. Then:

1. The body has evaluated `123` and is preparing to return.
2. `close()` is invoked by the `try-with-resources` mechanism.
3. `close()` throws `IllegalStateException`.
4. The method **does not complete by returning `123`**, and instead terminates with the exception from `close()`, unless that exception is handled in an appropriate enclosing handler.

This is not Java "forgetting to return the result", but the rule that prioritizes the **new abrupt completion** from closing over the pending return path.

**Why is there no suppressed exception in this case?** The `try` body only prepared to `return`; it did not throw any primary exception. When `close()` is the sole source of an exception, the close error becomes the primary exception observed.

Comparison:

| Body status | `close()` status | What the caller typically observes |
| --- | --- | --- |
| `return 123` | Normal | Receives `123` |
| `return 123` | Throws `Eclose` | Receives `Eclose` instead of `123` |
| Normal completion | Throws `Eclose` | Receives `Eclose` |
| Throws `Ebody` | Normal | Receives `Ebody` |
| Throws `Ebody` | Throws `Eclose` | Receives `Ebody`; `Eclose` is suppressed |

The bottom row of the table is a major advantage of `try-with-resources` over a manual `finally` block that executes a new `throw`.

## 7. When Both the Body and `close()` Throw: Suppressed Exceptions

Suppose the body throws `IllegalArgumentException("body failed")` and then closing the resource throws `IllegalStateException("close failed")`.

Java needs to preserve the **primary operation failure** while still recording the **cleanup failure**. With `try-with-resources`, in the normal scenario:

- The exception from the body is kept as the **primary exception**.
- The exception from `close()` is added to the primary exception's `getSuppressed()` list.
- An enclosing handler catches the primary exception; to investigate close errors, inspect the array returned by `getSuppressed()`.

This is how Java prevents a cleanup failure from accidentally **completely overwriting** the original error.

### `getSuppressed()` Differs from `getCause()`

`Throwable.getCause()` represents the **cause chain**, typically passed by the programmer via a constructor like `new X(message, cause)`. `Throwable.getSuppressed()` represents **secondary exceptions attached to the primary exception**, typically resource-closing errors.

A primary exception can have both a `cause` and multiple suppressed exceptions; these are two distinct relationships.

When `try-with-resources` manages close errors automatically, do not look only at `ex.getCause()` and conclude there were no secondary errors. You need to check `ex.getSuppressed()` if cleanup status matters.

### How Many Close Errors Are Recorded?

With multiple resources, each `close()` is called in reverse order, even if an earlier `close()` threw an error. If the body already threw a primary exception and multiple closes fail, the close errors are added to the suppressed list.

For example, declaring A then B, the body throws E, and both `B.close` and `A.close` throw errors:

```text
open A
open B
try body throws E
B.close() throws EB
A.close() throws EA
caller catches E
E.getSuppressed() typically has [EB, EA]
```

Here `[EB, EA]` is notation illustrating the order, not a Java statement. The exact output will be verified by the next program.

## 8. Complete Java 17+ Example: Replaced Return and Suppressed Close Errors

Save the file **`CloseFailureFlowDemo.java`**:

```java
public class CloseFailureFlowDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failsOnClose;

        Tracked(String name, boolean failsOnClose) {
            this.name = name;
            this.failsOnClose = failsOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
            if (failsOnClose) {
                throw new IllegalStateException(
                        "close failed: " + name);
            }
        }
    }

    static int returnThenCloseFails() {
        System.out.println("CASE return-close-error");

        try (Tracked resource = new Tracked("R", true)) {
            System.out.println("body: return 9");
            return 9;
        }
    }

    static void bodyAndCloseFail() {
        System.out.println("CASE body-and-close-errors");

        try (Tracked first = new Tracked("A", true);
             Tracked second = new Tracked("B", true)) {
            System.out.println("body: throw");
            throw new IllegalArgumentException("work failed");
        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        }
    }

    static void closeOnlyFailure() {
        System.out.println("CASE close-only-error");

        try (Tracked resource = new Tracked("C", true)) {
            System.out.println("body: normal");
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(
                    "returned=" + returnThenCloseFails());
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
        }

        bodyAndCloseFail();
        closeOnlyFailure();
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 CloseFailureFlowDemo.java
java CloseFailureFlowDemo
```

**Exact stdout:**

```text
CASE return-close-error
open R
body: return 9
close R
caught: close failed: R
suppressed count: 0
CASE body-and-close-errors
open A
open B
body: throw
close B
close A
primary: work failed
suppressed count: 2
suppressed: close failed: B
suppressed: close failed: A
CASE close-only-error
open C
body: normal
close C
caught: close failed: C
```

### Analysis of the Three Failure Paths

**`returnThenCloseFails()`:** the body prepares to return `9` but `R.close()` throws `IllegalStateException`. The call inside `"returned=" + returnThenCloseFails()` does not complete normally, so **the line `returned=9` is not printed**. The outer handler catches the close error. Because the body did not throw a primary error, the suppressed list is empty.

**`bodyAndCloseFail()`:** the body throws `IllegalArgumentException("work failed")`. The two opened resources are closed **B first, A second**. Both `close()` calls throw `IllegalStateException`; Java attaches these errors to the primary exception. The handler catches the primary error and prints the two suppressed exceptions in the order B, A.

**`closeOnlyFailure()`:** the `try` body completes normally, but `close()` throws `IllegalStateException`. The handler receives the close exception itself. This confirms that `try-with-resources` does not silently ignore cleanup errors.

In real systems, you need a policy for when closing fails: log it, fail the task, retry at an appropriate layer, or mark the data as not guaranteed to have been fully written. Do not report a false success just because the `try` body printed "done".

## 9. `break` and `continue` Still Close Resources

These two statements do not exit the entire method, but they **leave the `try` scope** when transferring control outside the body. Therefore, `try-with-resources` still performs closing.

Structural example:

```java
for (int i = 0; i < 10; i++) {
    try (Resource resource = open(i)) {
        if (shouldSkip(i)) {
            continue;
        }

        if (shouldStop(i)) {
            break;
        }

        use(resource);
    }
}
```

This is an illustrative skeleton requiring definitions for `Resource`, `open`, `shouldSkip`, `shouldStop`, and `use`. Execution paths:

- If `shouldSkip(i)` is `true`, the current iteration's resource is closed **before** the loop starts the next iteration.
- If `shouldStop(i)` is `true`, the resource is closed **before** exiting the loop.
- If `use(resource)` completes normally, the resource is still closed at the end of the `try` body.
- If `use(resource)` throws an exception, the resource is still closed during the abrupt exit.

**Note:** if `close()` raises an error on the `continue` or `break` path, the control transfer can be replaced by an uncaught exception. Thus the loop may not jump where you expect if cleanup fails.

### Labeled `break` and Labeled `continue`

Java has `break label;` and `continue label;`. When the statement transfers control out of one or more `try-with-resources` scopes, the resources of the scopes being exited are closed according to the corresponding rules. If a labeled statement **does not leave a particular `try-with-resources` scope**, that scope's resources are not closed solely because a transfer statement ran.

Therefore, you must consider **which scopes are actually exited**, rather than relying merely on whether a `break`/`continue` keyword appears in the code.

## 10. How Does a `return` in an Outer `catch` or `finally` Affect Things?

Consider:

```java
static int recover() {
    try (Tracked resource = openTracked()) {
        throw new IllegalArgumentException("bad input");
    } catch (IllegalArgumentException ex) {
        return 0;
    } finally {
        System.out.println("request finished");
    }
}
```

This is an illustrative skeleton with an appropriate `Tracked` type and `openTracked()`. Sequence:

1. Open the resource and run the `try` body.
2. The body throws `IllegalArgumentException`.
3. The resource is closed.
4. The `catch` handler decides to `return 0`.
5. The `finally` block of the same construct executes.
6. If `finally` completes normally, the caller receives `0`.

If `finally` **also `return`s or `throw`s**, it can override the decision from `catch`. That is the abrupt-completion rule of `finally`, which is **separate** from the automatic resource-closing mechanism, though both can occur within the same construct.

Do not use `finally` to return fallback values or swallow errors. Place recovery policy in an appropriate `catch` block; let `try-with-resources` handle the resource lifecycle.

## 11. Exceptions During Resource Initialization Also Close Already-Opened Resources

Not every abrupt exit starts in the `try` body. Even an **initializer** in the resource list can fail:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    doWork(first, second);
}
```

This is an illustrative snippet. If `openFirst()` succeeds, but `openSecond()` throws an exception:

- `first` was successfully initialized, so Java calls `first.close()`.
- `second` was not successfully initialized, so there is no valid `second` resource on which to call `close()`.
- The body `doWork(first, second)` **does not run**.
- The exception from `openSecond()` is the primary error.
- If `first.close()` also throws an error, the close error can be attached as **suppressed** under the initialization error.

For a resource whose initializer returns `null`, Java **does not call `close()` on `null`** as part of resource closing. However, using a `null` resource variable inside the `try` body can throw `NullPointerException` just like any other Java call.

### Reasoning Example

```text
open A succeeds
open B throws "init B failed"
close A
catch sees "init B failed"
```

If `close A` also throws, the close exception is recorded as a secondary error under the suppression rules; it does not cause the skipped `try` body to start running.

Thus, `try-with-resources` also prevents **resource leaks when initialization partially succeeds**.

## 12. How `try-with-resources` Differs from Hand-Written `try-finally` When Both Fail

Consider manual code:

```java
Resource resource = openResource();
try {
    doWork(resource);
} finally {
    resource.close();
}
```

This is an illustrative snippet requiring appropriate declarations/methods. On the normal closing path, it looks similar to `try-with-resources`. But when:

- `doWork(resource)` throws exception `Ebody`;
- `resource.close()` in `finally` throws exception `Eclose`;

a new `throw` from `finally` can **mask `Ebody`**. There is no automatic mechanism that adds `Eclose` to `Ebody.getSuppressed()` merely because `close()` was written in a plain `finally`.

With `try-with-resources`:

```java
try (Resource resource = openResource()) {
    doWork(resource);
}
```

Java compiles the construct using the primary-error and close-error management mechanism, keeping `Ebody` as the primary exception and attaching `Eclose` to the suppressed list. This is why **`try-with-resources` should be preferred for `AutoCloseable` objects** over manually closing in `finally`.

### Should You Manually Call `close()` Inside the `try` Body?

If you manually call `resource.close()` inside the body and then let `try-with-resources` close it again, you risk **double-closing**. Not every `AutoCloseable` guarantees that repeated closing is harmless. Design ownership clearly; in most cases, let Java alone call `close()` when leaving the scope.

### `close()` Throwing Checked Exceptions

`AutoCloseable.close()` may declare `throws Exception`. The checked exception type that must be handled is checked against the **static type of the resource**. If invoked through a variable of type `AutoCloseable`, a method may need `throws Exception`; if using `BufferedReader`, the relevant checked exceptions are typically under `IOException`.

Therefore, this snippet:

```java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using resource");
    }
}
```

is a **Java 9+ illustrative method**, using a parameter `resource` that is not reassigned and having the `throws Exception` signature to satisfy the checked exception that closing may throw. It also illustrates that using a variable declared outside in the resource specification is valid when the parameter is *effectively final*.

## 13. Closing Order with Multiple Resources and Abrupt Exit

With:

```java
try (R a = openA();
     R b = openB();
     R c = openC()) {
    return calculate(a, b, c);
}
```

this is an illustrative skeleton with hypothetical classes/methods. Java opens the resources in the order **A → B → C** and closes them in the order **C → B → A** when leaving the scope.

If `calculate` returns normally, Java prepares the return value yet still closes all three resources before the caller receives it.

If `calculate` throws exception `E`, Java still calls all three `close()` methods; any close errors can be attached as suppressed on `E`.

If `c.close()` throws while the body is preparing to `return`, that close exception can become the primary error. Closing `b` and `a` is still attempted; if they also throw errors, those secondary errors can be attached as suppressed on the primary error from `c.close()`.

**Do not conclude that one failing `close()` causes Java to skip the remaining resources.** The closing mechanism is designed to attempt closing all successfully initialized resources, in reverse order.

### When Multiple Resources Depend on Each Other

For example, a reader wrapping an input stream: `reader.close()` may already close the underlying stream. If you declare both in the resource list, Java may call close on the stream a second time. Many standard streams tolerate this, but some custom `AutoCloseable` implementations may not be safe under repeated closing.

Register only **the resources owned by the current scope**, based on the closing contract of the wrapper and the underlying source, rather than automatically adding every object that has a `close()` method to the list.

## 14. Thread Interruption and Resource Closing

A thread can be asked to stop work via the interrupt mechanism. However, `Thread.interrupt()` **does not automatically throw an exception at arbitrary points during execution** and does not guarantee that every API will stop immediately.

If an operation inside a `try-with-resources` body throws `InterruptedException` and that exception exits the body, all registered resources are still closed according to the abrupt-exit rules.

Skeleton example:

```java
static void consume(AutoCloseable resource)
        throws Exception {
    try (resource) {
        Thread.sleep(1_000);
    }
}
```

This is a Java 17+ illustrative method in which the `resource` parameter is not reassigned. If `Thread.sleep` throws `InterruptedException` because the sleeping thread is interrupted, the resource is closed before the exception leaves the method. If an upper layer catches `InterruptedException` and chooses to stop the task, it should normally handle the interrupt status according to policy (for example, restoring the interrupt flag when it cannot rethrow).

Distinguish between **exiting the body via an exception** (where the closing mechanism takes effect) and a thread that is still running inside a blocking call or an infinite loop without leaving `try`. In the latter case, the resource is not necessarily closed at the moment you observe it.

## 15. When Is Automatic Closing Not Guaranteed to Happen?

`try-with-resources` operates according to the execution rules of the Java language. However, you cannot promise that `close()` will always run in scenarios outside this model:

- `Runtime.getRuntime().halt(...)` terminates the JVM directly.
- `System.exit(...)` initiates JVM shutdown; there is no guarantee that all threads currently inside `try-with-resources` will finish their work and close resources.
- The process is forcibly killed by the operating system, the JVM suffers a fatal crash, or the system loses power.
- A thread is stuck in an operation that never exits, so the `try` block is never left.
- `close()` is called, but `close()` itself hangs indefinitely or fails midway; invoking the method does not prove that resource release completed successfully.

Do not use a shutdown hook as a substitute for per-scope resource lifecycle management; shutdown hooks are likewise not guaranteed across every kind of process termination.

**Practical rule:** `try-with-resources` is reliable for normal Java completion paths, including `return`, `throw`, `break`, and `continue`; however, it does not replace crash-recovery procedures, transaction mechanisms, or shutdown policies.

## 16. Relationship Between Scope, Ownership, and Early-Exit Closing

Three concepts should be kept separate:

| Concept | Question to answer | Example |
| --- | --- | --- |
| Scope | Can the variable name still be accessed from the current code? | A variable declared in `try (...)` cannot be used after the construct |
| Lifetime | Is the resource already closed or still ready for use? | `try (external)` closes `external` when leaving the block |
| Ownership | Which component is responsible for closing it? | A method that opens a file itself usually closes it itself |

Since Java 9, you can declare a variable beforehand and pass it into `try`:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    return reader.readLine();
}
```

This is an **illustrative method body** given a valid `path` and an appropriate checked-exception signature. The variable `reader` was declared outside `try`, yet when the method prepares to `return`, the resource is still closed. The requirement for using an external variable in a resource specification is that it must be `final` or *effectively final*.

If a variable remains in scope after leaving `try (reader)`, that **does not permit continuing to read through the closed reader**. Variable scope does not extend resource lifetime.

### Do Not Close a Resource Still Owned by Someone Else

If a caller passes in a stream it still needs to use, a helper method that arbitrarily writes `try (callerStream)` and `return`s early will cause the stream **to be closed before the caller uses it further**. The syntax works, but the ownership design is wrong.

It is better to agree on a clear contract: the function that **creates and owns** a resource is usually responsible for closing it; a function that only **borrows** a resource usually does not close it if the caller will use it afterward. Some APIs transfer ownership to the callee, but that must be explicitly documented.

## 17. Common Misconceptions

| Misconception | Reality | Practice |
| --- | --- | --- |
| "`return` runs immediately and skips `close()`" | Java closes before completing `return` | Wrap resources that need closing in `try-with-resources` |
| "With `break`/`continue`, the resource is not closed" | Exit paths from the scope still trigger closing | Ensure the corresponding `try` scope is actually exited |
| "`close()` always runs after `catch`" | `close()` runs before handlers attached to the same construct | Check suppressed exceptions from the handler |
| "Even if `close()` fails, `return` is guaranteed to succeed" | A close error can replace the `return` path | Do not ignore close exceptions |
| "If both body and close fail, only the close error is visible" | With `try-with-resources`, the body error is primary and close is suppressed | Check `getSuppressed()` |
| "A suppressed exception is `cause`" | `getCause()` and `getSuppressed()` are different | Use the right diagnostic API |
| "If B's `close()` fails, A is not closed" | Java still attempts to close the other opened resources | Design `close()` to be independent and safe |
| "If `openB()` fails, `openA()` leaks" | Already-opened A is closed when B's init fails | Place resources in the same resource specification when appropriate |
| "Variable in scope means resource is open" | Scope does not mean lifetime | Do not use a closed resource |
| "Any object with `close()` works in `try`" | The type must implement `AutoCloseable` | Check the type and closing contract |
| "`try-with-resources` guarantees closing even on power loss/halt" | No absolute guarantee outside normal execution | Design separate shutdown/crash recovery |
| "Closing a resource automatically rolls back prior effects" | Closing does not mean rollback | Use transaction/compensation contracts when needed |
| "You can call `close()` yourself and let auto-close run again" | May cause double-close | Clarify ownership and avoid duplicate closing |

## 18. Checklist Before Using `try-with-resources`

1. **Check the type:** does the resource actually implement `AutoCloseable`? Which checked exceptions can `close()` throw?
2. **Determine ownership:** is this a resource that the current scope is responsible for closing?
3. **Bound the scope:** are all operations needing the resource contained within the `try` body?
4. **Consider `return`:** the value is evaluated before closing; if close fails, the caller may not receive that value.
5. **Consider `throw`:** if the body throws an exception, Java will attempt to close, and close errors may appear in `getSuppressed()`.
6. **Consider `break` and `continue`:** does the statement actually leave the resource-managed region? Does it depend on the next iteration?
7. **Consider multiple resources:** open left → right, close right → left; check whether a wrapper already closes the underlying source.
8. **Consider initializer failures:** resources already initialized before the failure point are still closed.
9. **Consider handlers:** a `catch` attached to `try-with-resources` runs after the closing step; it should be broad enough to catch expected errors, without swallowing errors that have no handling plan.
10. **Consider result completeness:** a succeeding body does not guarantee the whole call succeeded if `close()`/flush fails.
11. **Consider suppressed errors:** if the system logs errors, should it also record the secondary close errors?
12. **Consider shutdown/crash:** is there a mechanism to handle cases where the process does not go through normal Java exit paths?
13. **Test:** cover the success path, early `return`, `try`-body exceptions, `close()` failures, initializer failures, and multiple resources failing together.

## 19. Self-Check Exercises

**Exercise A.** In `try (R r = new R()) { return 5; }`, is `r.close()` called?

**Yes**, when the method prepares to leave the body via `return`, provided the resource was initialized and the JVM continues normal execution. `close()` runs before the caller receives `5`.

**Exercise B.** If `close()` throws `IllegalStateException` while `try` is preparing to return `5`, does the caller always receive `5`?

**No.** The exception from `close()` can replace the `return` path, so the caller receives the error instead of `5` if there is no appropriate handler.

**Exercise C.** `try` throws `IOException("read failed")`, and `close()` throws `IOException("close failed")`. With `try-with-resources`, which error is primary?

**Normally `"read failed"`**, while `"close failed"` is stored in the primary exception's `getSuppressed()`.

**Exercise D.** Resource A is opened before B. On a `return` inside the body, is A or B closed first?

**B before A.** Java closes in reverse declaration order, regardless of whether the exit is via `return` or normal completion.

**Exercise E.** A loop opens one resource per iteration. Inside the `try` body there is a `continue;`. Is the current iteration's resource closed before the next iteration?

**Yes**, if `continue` leaves that `try-with-resources` scope. The closing mechanism runs before control continues the loop.

**Exercise F.** `openA()` succeeds, `openB()` fails, and the `try` body has not run. Is A closed?

**Yes.** Resources that have already been successfully initialized are closed when a later resource's initialization fails.

**Exercise G.** Both the body and two close calls fail. Where can the caller inspect those close errors?

Via **`getSuppressed()`** on the primary exception, in the order of the close calls that produced them.

**Exercise H.** A resource's `close()` was called, but `close()` itself failed with an error. Can we conclude the resource was definitely released successfully?

**No.** "Having called `close()`" does not guarantee "closed successfully"; the actual state depends on the resource's contract and implementation.

**Exercise I.** Is calling `System.exit(...)` inside a `try-with-resources` body the same as a normal `return`?

**No.** Terminating the process/JVM does not guarantee closing open resources via `finally`/`try-with-resources` execution paths. Do not use `System.exit` as a substitute for normal closing procedures.

**Exercise J.** `try (external)` automatically closes the resource, but `external` was declared outside and is still visible after `try`. Can you keep using it?

**You should not**, unless the specific resource contract defines an operation as valid after closing. Variable scope and closed state are two different things.

## Conclusion

**`try-with-resources` closes successfully initialized resources before completing any scope-exit path**, including `return`, `throw`, `break`, and `continue`. With multiple resources, closing order is **the reverse of initialization order**. When the body throws an error and `close()` also throws, Java preserves the primary exception and records the close error as a **suppressed exception**. However, if the body only prepares to `return` and `close()` throws an error, the return result can **be replaced by the close exception**.

Good design combines three things: **a sufficiently narrow usage scope**, **clear resource ownership**, and **honest handling of errors both in the body and during closing**. This mechanism handles many exit paths in Java, but it does not replace transaction management or recovery guarantees when a process is terminated abnormally.