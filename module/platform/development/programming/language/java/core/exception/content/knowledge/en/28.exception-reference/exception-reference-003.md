# Outcome Table for try, catch, finally, and try-with-resources

When reading or writing Java exception-handling code, the important question is not only “which exception is thrown?”, but also **“after the entire `try`/`catch`/`finally` construct, what does the method actually return or which exception escapes?”**. The execution order can be counterintuitive: `finally` runs after a `return` path has already been prepared; if `finally` itself throws or returns, the pending outcome of `try` or `catch` can be replaced. With `try-with-resources`, Java closes resources before executing the `catch`/`finally` attached to that construct, and close failures are normally preserved as *suppressed exceptions* rather than masking the primary exception.

This reference presents **outcome tables** for common combinations in Java 17+, covering execution order, exception precedence, return values, and how to verify them with standalone programs. The examples have explainable stdout; any rule that depends on assumptions is stated explicitly.

## 1. Key Terms to Align On

A Java statement can complete **normally** (*normal completion*) or **abruptly** (*abrupt completion*). The causes of abrupt completion relevant to this reference include:

- `return` — requests returning a result from the method.
- `throw` — throws a `Throwable`.
- `break` or `continue` — transfers control within an enclosing loop or `switch`.
- An exception arising within an expression, such as `parseInt`, a method call, or `close()`.

To read the tables, assume methods have representative code blocks like:

```java
try {
    work();
} catch (IOException ex) {
    recover(ex);
} finally {
    cleanup();
}
```

This is **contextual illustrative code**, where `work`, `recover`, and `cleanup` are application-defined. Whether `IOException` is caught depends on the actual runtime exception type; `catch` only catches exceptions from its corresponding `try` block that match the caught type.

An important term is **pending completion**: when `try` or `catch` has already prepared a `return`/`throw` but has not yet left the construct because `finally` still has to run, that outcome can still be replaced by the completion of `finally`.

## 2. Basic Outcome Table for try/catch/finally

Read the table using these conventions:

- **T**: value prepared to be returned in `try`.
- **C**: value prepared to be returned in `catch`.
- **F**: value returned in `finally`.
- **E1**: exception thrown from `try`; **E2**: exception thrown from `catch`; **E3**: exception thrown from `finally`.
- “`finally` completes normally” means `finally` itself does not `throw`/`return`/`break`/`continue` in a way that alters the exit path.
- The table assumes no other failures arise from class loading, VM termination, or external systems.

| Outcome in `try` | `catch` | Outcome in `finally` | Externally Observed Outcome |
| --- | --- | --- | --- |
| Completes normally | Does not run | Normal | Execution continues after the statement. |
| `return T` | Does not run | Normal | Method returns **T**. |
| Throws **E1**, matching catch exists | Catch completes normally | Normal | Execution continues after the statement. |
| Throws **E1**, matching catch exists | `return C` | Normal | Method returns **C**. |
| Throws **E1**, matching catch exists | Throws **E2** | Normal | **E2** escapes. |
| Throws **E1**, no matching catch | Does not run | Normal | **E1** escapes. |
| Completes normally | Does not run | `return F` | Method returns **F**. |
| `return T` | Does not run | `return F` | Method returns **F**; T is replaced. |
| `return T` | Does not run | Throws **E3** | **E3** escapes; value T is not returned. |
| Throws **E1** | With or without catch | Throws **E3** | **E3** wins over the pending completion, unless an inner mechanism already handled its own error. |
| Throws **E1**, catch returns C | `return C` | `return F` | Returns **F**; C is replaced. |
| Throws **E1**, catch throws E2 | Throws **E2** | Throws **E3** | **E3** escapes; E2 is replaced in normal exception propagation. |

**Core rule:** if `finally` **completes normally**, the pending completion of `try` or `catch` is preserved. If `finally` **completes abruptly**, the completion of `finally` determines the exit path, and the previous completion may be lost from propagation.

That does not mean the JVM automatically attaches the masked exception as suppressed. **Ordinarily, throwing a new exception in `finally` masks the old one without automatically linking them.** Automatic suppression is a key feature of `try-with-resources` (and only in specified cases), not of every `finally` block.

## 3. Execution Order: finally Runs Before the Method Exits

Consider:

```java
static int example() {
    try {
        System.out.println("inside try");
        return 10;
    } finally {
        System.out.println("inside finally");
    }
}
```

This is a valid Java method when placed inside a class. If called and the result is printed, the order is:

```text
inside try
inside finally
```

Only after those two lines does the caller receive the value `10`. `finally` does not run “after the caller has already seen the return”; it runs **before the method finishes**.

The same thing happens when `catch` prepares a `return`:

```java
static int example() {
    try {
        throw new IllegalArgumentException("invalid");
    } catch (IllegalArgumentException ex) {
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
```

By the time the caller receives `-1`, the line `cleanup` has already been printed. If `finally` throws another exception, the caller does not receive `-1`.

## 4. Complete Java 17 Example: Outcome Paths of try/catch/finally

Create the file `TryCatchFinallyOutcomesDemo.java`:

```java
public class TryCatchFinallyOutcomesDemo {

    private static String normalReturn() {
        try {
            System.out.println("normal: try");
            return "T";
        } finally {
            System.out.println("normal: finally");
        }
    }

    private static String caughtReturn() {
        try {
            throw new IllegalArgumentException("bad input");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught: catch");
            return "C";
        } finally {
            System.out.println("caught: finally");
        }
    }

    private static void uncaughtThrow() {
        try {
            throw new IllegalStateException("original");
        } catch (IllegalArgumentException ex) {
            System.out.println("unreachable catch");
        } finally {
            System.out.println("uncaught: finally");
        }
    }

    private static void catchThrows() {
        try {
            throw new IllegalArgumentException("input");
        } catch (IllegalArgumentException ex) {
            System.out.println("catchThrows: catch");
            throw new IllegalStateException("from catch", ex);
        } finally {
            System.out.println("catchThrows: finally");
        }
    }

    private static String finallyReturns() {
        try {
            System.out.println("finallyReturns: try");
            return "T";
        } finally {
            System.out.println("finallyReturns: finally");
            return "F"; // Intentionally demonstrating an anti-pattern.
        }
    }

    private static void finallyThrows() {
        try {
            throw new IllegalArgumentException("original");
        } finally {
            throw new IllegalStateException("finally wins");
        }
    }

    public static void main(String[] args) {
        System.out.println("normal result: " + normalReturn());
        System.out.println("caught result: " + caughtReturn());

        try {
            uncaughtThrow();
        } catch (IllegalStateException ex) {
            System.out.println("outer caught: " + ex.getMessage());
        }

        try {
            catchThrows();
        } catch (IllegalStateException ex) {
            System.out.println("outer catchThrows: " + ex.getMessage());
            System.out.println(
                    "cause: " + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("finallyReturns result: " + finallyReturns());

        try {
            finallyThrows();
        } catch (IllegalStateException ex) {
            System.out.println("outer finallyThrows: " + ex.getMessage());
            System.out.println(
                    "suppressed: " + ex.getSuppressed().length);
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 TryCatchFinallyOutcomesDemo.java
java TryCatchFinallyOutcomesDemo
```

Stdout:

```text
normal: try
normal: finally
normal result: T
caught: catch
caught: finally
caught result: C
uncaught: finally
outer caught: original
catchThrows: catch
catchThrows: finally
outer catchThrows: from catch
cause: IllegalArgumentException
finallyReturns: try
finallyReturns: finally
finallyReturns result: F
outer finallyThrows: finally wins
suppressed: 0
```

**Reading the output:**

1. `normalReturn()` prepares to return T; `finally` runs before T reaches the caller.
2. `caughtReturn()`: the exception in `try` is handled by `catch`, which prepares to return C; `finally` still runs and C is preserved.
3. `uncaughtThrow()`: `catch` does not match `IllegalStateException`, yet `finally` still runs. `IllegalStateException("original")` propagates out to the outer `catch`.
4. `catchThrows()`: a new exception is thrown **inside `catch`**. Sibling `catch` clauses do not catch an exception thrown by another `catch` in the same `try`; `finally` runs and the new exception is caught outside. The cause was explicitly attached by the code.
5. `finallyReturns()` intentionally uses `return` inside `finally` to demonstrate returning F instead of T. This is an **anti-pattern to avoid in production** because it discards the pending exit path.
6. `finallyThrows()`: `IllegalStateException("finally wins")` masks `IllegalArgumentException("original")` thrown by `try`. `suppressed: 0` proves that **a plain `finally` does not automatically add the prior exception to suppressed**.

The program intentionally demonstrates two dangerous patterns (`return`/`throw` in `finally`). Do not copy them into production cleanup unless you deliberately intend to override the outcome and have accounted for the consequences.

## 5. Dedicated Table: return, throw, break, and continue with finally

In addition to `return` and `throw`, `finally` can also affect `break`/`continue` in loops. The general mechanism remains the same: normal completion preserves the prior exit path; a new abrupt completion can replace the prior path.

| Pending Action | `finally` Completes Normally | `finally` Alters Control Flow |
| --- | --- | --- |
| `return value` | Preserves the previously evaluated value | A new `return` or `throw` replaces it. |
| `throw E` | Preserves E | A new `return`/`throw` masks E. |
| `break` | Continues breaking to the target | A context-valid `return`/`throw`/`continue` can replace it. |
| `continue` | Continues the loop at the continue target | A context-valid `return`/`throw`/`break` can replace it. |
| Normal completion | Executes the next statement | The new transfer target is determined by `finally`. |

**Do not put `return`, `break`, or `continue` in `finally` to “keep things tidy.”** Those statements can accidentally swallow exceptions or break loop logic.

Anti-pattern example:

```java
for (int i = 0; i < 3; i++) {
    try {
        process(i);   // May throw.
    } finally {
        continue;     // May mask a pending throw.
    }
}
```

This is an illustrative snippet; `process` is undefined. `continue` inside `finally` intentionally alters the loop's exit path; many static analyzers and linters warn against this pattern. Use `finally` only for cleanup and let it complete normally whenever possible.

## 6. Return Values Are Evaluated Before finally Executes

When encountering `return expression`, Java evaluates **the value of `expression`** first. If `finally` then completes normally, the already-evaluated value is returned to the caller. Modifying a local variable in `finally` does not re-evaluate the expression.

Example:

```java
static int value() {
    int x = 5;
    try {
        return x;
    } finally {
        x = 99;
    }
}
```

The method returns **5**, not 99. However, if the expression returns a **reference to a mutable object**, `finally` can mutate that object and the caller will observe the modified data, because the returned reference still points to the same object.

Distinguish between:

- **The primitive value or object reference selected when `return` is evaluated.**
- **The contents of the mutable object pointed to by that reference, which can still be modified after evaluation.**

`return` also does not prevent new failures: if `finally` throws an exception, the prepared value will not reach the caller.

## 7. Complete Java 17 Example: Primitives and Mutable Objects

Create the file `ReturnAndFinallyValueDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ReturnAndFinallyValueDemo {

    private static int primitiveValue() {
        int number = 5;
        try {
            return number;
        } finally {
            number = 99;
            System.out.println("primitive finally: " + number);
        }
    }

    private static List<String> mutableResult() {
        List<String> result = new ArrayList<>();
        result.add("try");
        try {
            return result;
        } finally {
            result.add("finally");
        }
    }

    private static int returnInterruptedByThrow() {
        try {
            return 42;
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        System.out.println("primitive returned: " + primitiveValue());
        System.out.println("mutable returned: " + mutableResult());

        try {
            System.out.println(returnInterruptedByThrow());
        } catch (IllegalStateException ex) {
            System.out.println("no returned value: " + ex.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 ReturnAndFinallyValueDemo.java
java ReturnAndFinallyValueDemo
```

Stdout:

```text
primitive finally: 99
primitive returned: 5
mutable returned: [try, finally]
no returned value: cleanup failed
```

On the last call, `System.out.println(returnInterruptedByThrow())` **does not print 42**, because the argument expression does not return normally: `finally` threw an exception. The outer `println` is only invoked if evaluating its argument completes normally.

With `mutableResult`, the reference is selected for return before `finally`; then `finally` mutates that same list, so the caller sees both elements. This can break contracts if an API exposes an internal mutable collection. Return an immutable snapshot when the caller must not observe post-return mutations.

## 8. When finally Is Not Guaranteed to Run

In normal Java execution, `finally` executes when code exits `try`/`catch` via `return`, `throw`, `break`, or `continue`. However, **you should never claim that `finally` runs under all absolute circumstances**:

- `System.exit` can terminate the JVM before the current stack unwinds through `finally`.
- `Runtime.halt` can stop the JVM immediately.
- A JVM crash, OS process kill, or power loss does not guarantee cleanup runs.
- A thread stuck indefinitely inside `try` never leaves the scope, so `finally` has not run yet.
- The legacy `Thread.stop` is unsafe; do not rely on it for cleanup design.

Therefore, `finally` is an essential cleanup mechanism **within language control flow**, but it does not replace crash recovery, transactions, lease expiration, or durable writes.

## 9. try-with-resources: How Is It Different from a Hand-Written finally?

`try-with-resources` (TWR) was introduced to close `AutoCloseable` resources in a structured way:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

This is an illustrative snippet; you must import `InputStream` and `Files` and define `path`/`parse` according to your application.

Key rules:

1. Resources are **initialized left to right** in the declaration.
2. Successfully initialized resources are **closed in reverse order** when leaving the body.
3. Resource closing occurs on normal completion, `return`, and exception paths (within normal Java control flow).
4. Already-initialized resources are still closed if initializing a subsequent resource fails.
5. An exception from the body takes precedence as the **primary** exception; eligible close failures are added as **suppressed** exceptions on the primary exception.
6. If the body completes normally and the first close in closing order throws, that close error can become the **primary** exception; subsequent close errors are added as suppressed.
7. `catch`/`finally` attached to the **entire TWR statement** execute after the statement's resources have been closed according to these rules. This differs from placing a `catch` inside the body.

Do not assume TWR means “a `finally` is just as good”: with a hand-written `finally`, a new close exception can mask the body exception unless your code explicitly attaches suppressed exceptions. TWR preserves both causes.

## 10. try-with-resources Outcome Reference Table

Conventions:

- **Ebody**: Throwable thrown from the body.
- **Einit**: Throwable thrown while initializing a resource.
- **Eclose-B**, **Eclose-A**: errors while closing B and A, where resources are declared A then B, so **B closes before A**.
- “Suppressed” means accessible via `primary.getSuppressed()`; normally each close error is appended to the array in the order it occurs.
- The table assumes standard exception objects with suppression enabled, distinct thrown objects, and no custom interference.

| Body / Initialization Outcome | Resource Closing | TWR Outcome |
| --- | --- | --- |
| Body normal | All closes succeed | TWR completes normally, execution continues. |
| Body `return V` | All closes succeed | Method returns V after closing. |
| Body throws **Ebody** | All closes succeed | Ebody escapes; no close errors. |
| Body throws **Ebody** | B's close throws **Eclose-B** | Ebody remains primary; Eclose-B is suppressed. |
| Body throws **Ebody** | Both B and A throw on close | Ebody is primary; B's error then A's error are suppressed. |
| Body normal | B's close throws Eclose-B, A closes normally | Eclose-B escapes. |
| Body normal | Both B and A throw on close | Eclose-B is primary; Eclose-A is suppressed on Eclose-B. |
| Body `return V` | A close throws Eclose | Eclose escapes; V is **not returned**. |
| Initializing A succeeds; initializing B throws Einit | A closes normally | Einit escapes; body does not run. |
| Initializing A succeeds; B throws Einit | A's close also throws Eclose-A | Einit is primary; Eclose-A is suppressed. |
| Single resource initialization fails | No such resource to close | Initialization exception escapes; body does not run. |

### Why Doesn't a Close Error Mask Ebody?

TWR is specified to preserve the primary work failure. If the body throws `IOException("read failed")` and `close()` also throws `IOException("close failed")`, the escaping exception is **"read failed"**, while `"close failed"` is in `getSuppressed()`.

By contrast:

```java
Resource resource = open();
try {
    work(resource);   // Throws Ebody.
} finally {
    resource.close(); // Throws Eclose.
}
```

This is an illustrative snippet; written this way, if `close()` throws, Eclose can replace Ebody. To preserve it like TWR does, you would have to write extra code to manage suppressed exceptions properly. Therefore, for scope-owned resources, **prefer try-with-resources**.

## 11. Complete Java 17 Example: Body Failure and Multiple Close Failures

Create the file `TryWithResourcesOutcomesDemo.java`:

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class TryWithResourcesOutcomesDemo {

    private static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;
        private final List<String> events;

        Resource(String name, boolean failOnClose, List<String> events) {
            this.name = name;
            this.failOnClose = failOnClose;
            this.events = events;
            events.add("open " + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close " + name);
            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static void printFailure(Throwable primary) {
        System.out.println("primary: " + primary.getMessage());
        System.out.println("suppressed count: "
                + primary.getSuppressed().length);
        for (Throwable s : primary.getSuppressed()) {
            System.out.println("suppressed: " + s.getMessage());
        }
    }

    private static void bodyFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = new Resource("B", true, events)) {
            events.add("body failed");
            throw new IllegalStateException("body error");
        } catch (IllegalStateException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        } catch (IOException ex) {
            throw new AssertionError("unexpected close-only", ex);
        }
    }

    private static void closeFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = new Resource("B", true, events)) {
            events.add("body OK");
        } catch (IOException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        }
    }

    private static String returnButCloseFails() throws IOException {
        List<String> events = new ArrayList<>();
        try (Resource x = new Resource("X", true, events)) {
            System.out.println("body returns");
            return "VALUE";
        }
    }

    private static Resource openSecond(List<String> events)
            throws IOException {
        events.add("open B failed");
        throw new IOException("init B failed");
    }

    private static void initFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = openSecond(events)) {
            events.add("body unreachable");
        } catch (IOException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE: BODY FAILURE");
        bodyFails();

        System.out.println("CASE: CLOSE FAILURE");
        closeFails();

        System.out.println("CASE: RETURN/CLOSE");
        try {
            System.out.println(returnButCloseFails());
        } catch (IOException ex) {
            printFailure(ex);
        }

        System.out.println("CASE: INIT FAILURE");
        initFails();
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 TryWithResourcesOutcomesDemo.java
java TryWithResourcesOutcomesDemo
```

Stdout:

```text
CASE: BODY FAILURE
open A
open B
body failed
close B
close A
primary: body error
suppressed count: 2
suppressed: close B failed
suppressed: close A failed
CASE: CLOSE FAILURE
open A
open B
body OK
close B
close A
primary: close B failed
suppressed count: 1
suppressed: close A failed
CASE: RETURN/CLOSE
body returns
primary: close X failed
suppressed count: 0
CASE: INIT FAILURE
open A
open B failed
close A
primary: init B failed
suppressed count: 1
suppressed: close A failed
```

Explaining the output:

- **BODY FAILURE:** Ebody is `IllegalStateException("body error")`. Closing B and A both throw `IOException`, yet the body error remains primary and the two close errors are suppressed in the order B then A.
- **CLOSE FAILURE:** the body succeeds; B is the first resource to close and fails, so B's error is primary. A still closes even though B failed; A's error is suppressed.
- **RETURN/CLOSE:** the body prepared to return `"VALUE"` but `close X` throws, so the caller receives `IOException` and **does not print `VALUE`**. `Resource X` records events into its own list that the demo does not print; thus stdout for this case starts directly at “body returns”.
- **INIT FAILURE:** A was created, opening B failed. The body does not run. Java closes A; because A also throws, A's close failure is suppressed onto B's initialization failure.

The `Resource` instances in the demo only record events and throw controlled exceptions, so the output order does not depend on asynchronous threads. In production, `close()` can partially close and then fail; “`close` was called” **does not mean cleanup definitely succeeded**.

## 12. When TWR Has Outer catch and finally, What Is the Order?

Consider:

```java
try (Resource r = openResource()) {
    System.out.println("body");
} catch (IOException ex) {
    System.out.println("catch");
} finally {
    System.out.println("finally");
}
```

This is an illustrative snippet; `Resource`/`openResource` are application-defined. In this form, the resource is closed **before entering the TWR statement's `catch` or `finally`**. If `close` throws `IOException` and the body had no error, `catch` can catch the exception produced by `close`.

Sequence:

```text
initialize resource
body
close resource
matching catch (if an exception occurred)
finally
continue or propagate exception out
```

If both the body and `close` complete normally, `catch` does not run and only `finally` runs. If the body throws Ebody and `close` throws Eclose, a `catch` matching **Ebody** can inspect `Ebody.getSuppressed()` to see Eclose.

**Distinguish from a `catch` inside the body:**

```java
try (Resource r = openResource()) {
    try {
        work(r);
    } catch (IOException ex) {
        recover(ex);
    }
}
```

This is an illustrative snippet. A `catch` **inside the body** only catches errors thrown within the inner `try` block; it **does not catch errors from `r.close()`**, which occur after the body finishes. To catch a close exception, you need a `catch` outside the TWR or an appropriate enclosing `try`.

## 13. A finally After TWR Can Still Replace the Primary Exception

If TWR produces an exception that already has suppressed exceptions, and a `finally` attached outside the TWR goes on to throw another exception, then **the `finally` exception can replace the exception from TWR**, preventing the caller from directly observing Ebody along with its suppressed exceptions.

Anti-pattern example:

```java
try (Resource r = openResource()) {
    throw new IOException("body");
} finally {
    throw new IllegalStateException("finally failed");
}
```

This is an illustrative snippet; the types/imports must exist in the project and the method must handle checked exceptions according to its contract. The natural exit outcome is `IllegalStateException("finally failed")` rather than `IOException("body")`. Thus, **TWR preserves resource-closing errors, but it does not protect against an outer `finally` with an abrupt completion**.

In production, do not call cleanup code that can easily throw without handling it in `finally` in a way that accidentally masks the original error. Prefer clear resource scopes and controlled error recording/aggregation.

## 14. Distinguishing cause and suppressed Exceptions

The two mechanisms serve different purposes:

| Mechanism | API | Meaning |
| --- | --- | --- |
| **Cause** | `Throwable.getCause()`, cause-accepting constructors, or `initCause` per contract | This exception was created to wrap/interpret an underlying root-cause exception from a lower layer. |
| **Suppressed** | `Throwable.getSuppressed()`, `addSuppressed` | Secondary exceptions retained because another exception took precedence, typically close errors in TWR. |

Example:

```java
IOException original = new IOException("read failed");
IllegalStateException wrapper =
        new IllegalStateException("service failed", original);

wrapper.addSuppressed(new IOException("cleanup failed"));
```

The above is a valid Java snippet when placed inside a method with `IOException` imported. `wrapper.getCause()` is `original`; `wrapper.getSuppressed()[0]` is the cleanup error. They are not the same chain.

In a real exception, both cause and suppressed exceptions can exist at the same time. Full stack trace printing typically displays both, but tests should not assert on them merely by searching log strings. Use the `getCause()` and `getSuppressed()` APIs directly to verify error structure.

### Some Limitations of Suppressed Exceptions

- `addSuppressed` does not allow suppressing **the same `Throwable` object on which the method is called**; doing so can throw `IllegalArgumentException`.
- Suppression can be disabled via a special `Throwable` constructor; in that case, adding suppressed exceptions can be ignored per contract.
- `getSuppressed()` returns an array; do not assume every arbitrary exception has suppressed entries.
- TWR has rules that automatically handle resource-closing exceptions in appropriate cases; a plain `finally` has no equivalent guarantee.

Some systems create domain errors with suppression disabled or use specialized exceptions. If you need to log all cleanup failures, you must understand the contract of the `Throwable` and the resources in use.

## 15. Multiple Resources: Open Left to Right, Close Right to Left

Example:

```java
try (A a = new A();
     B b = new B(a);
     C c = new C(b)) {
    doWork(a, b, c);
}
```

This is an illustrative snippet; the types and methods are assumed. The normal order is:

```text
open A
open B
open C
body
close C
close B
close A
```

If B fails to initialize, the already-created A must be closed; C **has not been initialized**, so there is no C to close. If C fails to initialize, B then A are closed.

Closing in reverse order reflects dependencies: later resources often depend on earlier ones. However, not every resource can be safely closed under that rule if it has a special contract; when you need to coordinate cleanup actively, design scopes and ordering accordingly.

### AutoCloseable and Closeable

`AutoCloseable.close()` may declare `throws Exception`. `java.io.Closeable.close()` declares `throws IOException` and has its own detailed contract. When defining a class that implements `AutoCloseable`, you can override `close()` with a narrower exception type, or even declare no checked exception at all.

Example:

```java
final class InMemoryHandle implements AutoCloseable {
    @Override
    public void close() {
        // Cleanup does not throw a checked exception.
    }
}
```

This is a syntactically valid standalone class declaration. The declared types of the resource and `close` affect which checked exceptions the compiler requires callers to handle or declare.

## 16. Returning from a TWR Body Does Not Skip Closing

A common misconception:

```java
try (Resource r = acquire()) {
    return calculate(r);
}
```

This is an illustrative snippet. Java **evaluates `calculate(r)` first**, prepares the return value, and then closes `r`. If closing succeeds, the value is returned. If `close()` throws, the close error can replace the `return` completion.

Therefore, in a file-reading API:

```java
try (InputStream input = Files.newInputStream(path)) {
    return parse(input);
}
```

returning succeeds only if `parse` completes and closing the resource does not throw an exception out per contract. This is usually desirable: for example, an output stream may need to flush/close, and a close failure signals that data was not fully persisted.

Do not place `return` in `finally` to “keep the result at all costs,” as doing so can swallow critical I/O errors.

## 17. What If catch Handles a Body Error and Then close Fails?

Consider:

```java
try (Resource r = acquire()) {
    try {
        work(r);
    } catch (IOException ex) {
        recover(ex);
    }
}
```

If `work` throws `IOException` but `recover` handles it and **the body completes normally**, the resource is closed afterward. If `close` throws, the close exception becomes the error observed outside the TWR.

Conversely, if `recover` **throws a new exception**, that becomes the TWR body's error and a close exception can be suppressed onto it. This shows the table can only answer accurately when you know **the final completion of the body**, not just the initial exception in `work`.

For example:

| Behavior in Body | Close Behavior | Outcome |
| --- | --- | --- |
| `work` fails, inner catch handles it and body finishes normally | Close normal | TWR completes normally. |
| `work` fails, inner catch handles it and body finishes normally | Close throws Eclose | Eclose is primary. |
| `work` fails, inner catch throws Enew | Close normal | Enew escapes. |
| `work` fails, inner catch throws Enew | Close throws Eclose | Enew is primary; Eclose is suppressed. |

Do not just count “an exception was thrown somewhere” to predict the final outcome; you must trace **whether it was caught/recovered before leaving the scope**.

## 18. Exceptions in Resource Initialization Expressions

TWR can fail **before the body executes**:

```java
try (Resource a = openA();
     Resource b = openB()) {
    work();
}
```

If `openB()` throws an exception:

- The already-opened A will be closed according to TWR rules.
- B was not successfully created, so there is no B object to close.
- `work()` does not run.
- If closing A also throws, the exception from `openB` is primary and A's close error is suppressed.
- A `catch` outside the TWR can handle the initialization exception and inspect suppressed exceptions.

If `openB` itself has side effects **before throwing without returning a resource object**, the caller's TWR cannot automatically close whatever was opened inside `openB` without a returned handle. **A factory method must clean up any internal resources it successfully acquired before failing.**

## 19. Null Resources and Existing Resource Variables

In `try-with-resources`, a resource variable may hold `null`; Java skips the corresponding `close` call when the reference is `null`, rather than throwing a `NullPointerException` on close. However, using null resources often makes logic and ownership harder to read; choose a clear contract instead.

Since Java 9, TWR can use a `final` or **effectively final** variable declared outside:

```java
InputStream stream = Files.newInputStream(path);
try (stream) {
    consume(stream);
}
```

This is an illustrative snippet; you must import the classes and declare `path` and `consume` appropriately. Java will close the referenced resource upon leaving the scope. Even though the variable is declared outside, **`try (stream)` still means TWR owns the responsibility of calling `close`**; do not apply this carelessly to a shared resource managed by another caller.

If a caller only lends a stream, do not put it into TWR unless the contract allows that API to close the stream. If a resource must be used across multiple steps with broader ownership, the closing scope must belong to the true owner.

## 20. Can IOException or Error in close Be Suppressed?

TWR operates on `Throwable`, not just `IOException`. A `close()` method can throw an unchecked exception or an `Error`; if the body already completed with another `Throwable`, an eligible close failure can be recorded as suppressed on the primary error.

However, **do not use this mechanism to swallow `Error`** or assume recovery is possible after `OutOfMemoryError`/serious VM errors. Such errors can leave the runtime without enough resources to operate properly. Avoid writing `catch(Throwable)` to turn everything into a successful outcome.

For resources outside the JVM, a `close` throwing an `Error` also does not imply that data was rolled back. The goal of TWR is to manage close calls and exception precedence **within Java control flow**, not distributed transactions.

## 21. finally and Cleanup on return or throw: Avoid Altering the Outcome

A well-behaved cleanup block tends to look like:

```java
Resource r = acquire();
try {
    work(r);
} finally {
    r.close();
}
```

This is an illustrative structure. It releases the resource across multiple exit paths, but still carries the risk of a close error masking a `work` error as explained earlier. When the resource is `AutoCloseable`, prefer TWR.

If you must manage multiple cleanup errors manually, design the primary and suppressed exceptions clearly, or create a structured outcome. Never write logic like “if an error occurs, `return null` in `finally`” because it erases the failure path.

**Also avoid calling logging code that might throw inside `finally` without a safeguard:** if the logger/appender fails and `finally` throws, the main business exception can be masked. Keep cleanup simple and controlled, and track failures at the appropriate layer.

## 22. Is finally the Right Place to Restore Interrupts?

`InterruptedException` is typically thrown by blocking operations such as `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, or `Future.get`, ending the wait. When catching `InterruptedException`, you can propagate it or restore the interrupt flag if you cannot propagate a checked exception:

```java
try {
    waitForWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    cleanupOwnedResources();
}
```

This is an illustrative snippet with assumed `waitForWork`/`cleanupOwnedResources`. Note: **restoring the flag before `finally`** can cause interruptible blocking cleanup to be interrupted immediately. If cleanup needs to wait for a bounded time, you must design the order of catching, closing, and restoring the flag deliberately.

TWR with an outer `catch` has the advantage that resource `close` runs before `catch` restores the flag. Still, `close` can throw an exception and needs an appropriate policy. Do not use `return` in `finally` to erase `InterruptedException`; doing so can prevent callers from knowing a stop was requested.

## 23. TWR Does Not Make I/O Operations or Transactions Atomic

TWR guarantees **scoped resource closing when Java flow exits the block**, not that:

- File writes are rolled back if the body fails.
- An HTTP request is canceled on the server when the client closes the socket.
- A database rolls back after connection `close()` if the transaction lacks a clear contract.
- A sent message is recalled when an error happens after publishing.
- Locks/permits are released properly if code acquired them in the wrong scope.
- An async task stops when the caller closes a shared resource.

If file writing must be atomic by contract, you need a temporary-file and filesystem-appropriate commit/rename strategy, not just try-with-resources. For databases, you need designed transactions/rollbacks; for networks, you need idempotency and UNKNOWN/PENDING states when outcomes cannot be verified.

The “outcome” in the TWR table is **the Java control-flow outcome of the method**, not a guarantee that no external side effects occurred.

## 24. Checked Exceptions from close and Compilation Limits

A class typed as `AutoCloseable` generally declares `close() throws Exception`. Therefore, a TWR using a resource of static type `AutoCloseable` may require the method to:

- Declare an appropriate `throws Exception`; or
- Catch the necessary checked exception type.

Example:

```java
static void demo(AutoCloseable r) throws Exception {
    try (r) {
        System.out.println("using resource");
    }
}
```

This is a valid method when placed in a class; parameter `r` is effectively final if not reassigned. `throws Exception` comes from the possibility that `AutoCloseable.close()` throws checked `Exception`.

If a subtype overrides `close()` without throwing a checked exception and the resource variable has that subtype as its static type, the compiler may not require `throws Exception` solely due to `close`. The concrete static type of the resource, not just runtime behavior, affects compile-time exception checking.

`catch` is selected by **the runtime class of the `Throwable`**, but the validity of many checked `catch` clauses is also checked by the compiler based on exceptions that can be thrown according to static types. Do not add `catch(IOException)` when the compiler determines the `try` block has no path that can throw that checked type.

## 25. Construct Selection Table for API Design

| Need | Construct to Consider | Reason |
| --- | --- | --- |
| Run code that may fail and handle well-defined errors | `try/catch` with specific exception types | Recover or translate at the right boundary. |
| Always run cleanup other than resource closing | `try/finally`, keeping `finally` completing normally | Cleanup across normal exit paths. |
| Manage a scope-owned `AutoCloseable` | `try-with-resources` | Standard closing order, preserves suppressed exceptions. |
| Multiple interdependent resources | TWR declared in acquisition order | Closes in reverse order, even if later acquisition fails. |
| Return a computed result after cleanup | `return` in `try`; no unintended `return`/`throw` in `finally` | Value evaluated before cleanup, reaches caller unless cleanup alters outcome. |
| Preserve both body error and close error | TWR or proper explicit `addSuppressed` | Avoids masking the primary cause. |
| Multi-step transactions | Transaction/domain workflow, often combined with TWR for connections | TWR does not replace transactions. |
| Observability on failure | Logging/counters at an owning boundary | Avoids throwing from `finally` and losing the original error. |

A construct can be syntactically valid yet violate the contract. Choose based on resource type, ownership, exceptions to preserve, post-failure state, and how callers handle errors.

## 26. Common Misconceptions

**“If there is a `return` in `try`, `finally` does not run.”** False. The return is prepared, `finally` runs, and only then does the method return if `finally` completes normally.

**“`return` in `finally` only overwrites a local variable.”** False. A `return` in `finally` can completely replace a pending `return` or `throw`.

**“`finally` always runs, even if the JVM is killed.”** False. It is a language mechanism within normal control flow, not a guarantee across process crashes or halts.

**“An exception in `catch` is caught by another `catch` in the same statement.”** False. `catch` clauses of the same `try` are not chained to handle exceptions thrown from a `catch` clause; the new exception goes through `finally` and to the caller or an outer `catch`.

**“Throwing an exception in `finally` automatically saves the old exception as suppressed.”** False for a plain `finally`. If `Efinally` wins, `Etry` can be lost from normal propagation.

**“TWR only closes when there is no `return`.”** False. TWR closes resources before leaving the scope, including when the body returns.

**“TWR closes left to right.”** False. It creates left to right and closes right to left.

**“If the second resource fails to initialize, the first resource is not closed.”** False. Successfully initialized resources are still cleaned up by TWR.

**“A close error during a body throw replaces the body error.”** Not under normal TWR rules; the close error is normally suppressed onto the body exception.

**“If the body returns and close fails, the value is still returned.”** False; a close failure can replace the pending `return`.

**“Cause and suppressed are the same.”** False. Cause represents the causal/wrapping chain; suppressed holds secondary errors not chosen as primary.

**“A `catch` inside the body can catch a resource close error.”** No, if closing happens after the inner `try` block has completed; you need a `catch` outside the TWR statement.

**“Using TWR guarantees a database transaction rolls back.”** False. Resource cleanup is not equivalent to transaction commit/rollback.

**“Having TWR close a borrowed resource is harmless.”** False. The scope must own closing responsibility; a shared resource may still be used by other components.

**“Using `catch(Throwable)` is a safe way to catch all exceptions.”** Usually wrong for business recovery: it can swallow serious `Error`s, bugs, or misinterpret interruption/cancellation.

## 27. Checklist for Reading a try/catch/finally Snippet

When predicting the outcome, follow these steps:

1. **Identify the exception or `return` actually produced in `try`.** Do not guess from method names.
2. **Identify the first matching `catch`** in the same `try`, if any.
3. **Trace the completion of `catch`**: does it handle normally, `return`, or throw a new exception?
4. **If it is TWR, before reaching an outer `catch`, process resource closes** in reverse initialization order.
5. **Classify close errors:** does the body/init have a primary `Throwable`? If yes, close errors are normally suppressed; if not, the first close exception in closing order can be primary.
6. **Identify which scope `finally` is attached to**: an outer TWR `finally` differs from a `try/finally` nested inside the body.
7. **Determine the completion of `finally`**: normal completion preserves the prior outcome; a new `throw`/`return` replaces it.
8. **If there is a `return` expression**, it is evaluated before cleanup; check whether `finally` mutates the returned object.
9. **Inspect the exception escaping to the caller** and its cause/suppressed relationships.
10. **Distinguish Java outcomes from external side effects**: closing does not guarantee transaction rollback.
11. **Check ownership/lifecycle**: was the resource created by this scope or merely borrowed?
12. **Compare against the contract**: ask whether the object/method remains usable and in a valid state after failure.

Do not solve problems with the shortcut “`finally` always wins.” **`finally` only replaces the completion when it itself completes abruptly**; when it completes normally, it preserves the pending `return`/`throw`.

## 28. Outcome Lookup Exercises

**Question 1.** `try` prepares `return 7`, `finally` only prints a line and completes normally. What does the method return?

**Answer:** `7`, after `finally` runs.

**Question 2.** `try` throws `IllegalArgumentException`, a matching `catch` returns `-1`, `finally` completes normally. What is the result?

**Answer:** `-1`. The exception was handled by `catch`, and `catch`'s pending return was not replaced.

**Question 3.** `try` throws E1, there is no matching `catch`, `finally` throws E2. What does the caller see? Does E1 automatically become suppressed?

**Answer:** The caller sees E2; E1 is not automatically attached as suppressed by a plain `finally`.

**Question 4.** `try` returns a reference to an `ArrayList`, and then `finally` adds an element to the list. Does the caller see the list before or after the change?

**Answer:** The reference was selected earlier, but the mutable object was modified in `finally`, so the caller sees the added element.

**Question 5.** TWR declares A, B, C; the body completes normally. Closing C and A throws `IOException`, while B closes normally. Which exception is primary?

**Answer:** C's close error is primary because C closes first. A's close error becomes suppressed on C's error.

**Question 6.** A TWR body throws Ebody, and both B and A fail to close. What is the precedence?

**Answer:** Ebody is primary; B's error then A's error are suppressed in closing order, assuming suppression is enabled and the `Throwable`s are valid.

**Question 7.** A is created successfully, creating B throws Einit, and closing A also fails. Does the body run? What does the caller see?

**Answer:** The body does not run; Einit is primary, and A's close error is suppressed.

**Question 8.** A TWR body returns `"OK"`, and `close` throws `IOException`. Does the caller receive `"OK"` or `IOException`?

**Answer:** `IOException`; the pending return is replaced by the exceptional completion of `close`.

**Question 9.** Given `try (r) { try {work();} catch(IOException e) {recover();} }`. Closing `r` throws `IOException` after the body completes. Does the inner `catch` catch it?

**Answer:** No; closing happens after the body. A `catch` outside the TWR is needed to catch exceptions from `close`.

**Question 10.** Given `try (r) {throw Ebody;} finally {throw Efinally;}` and `r.close()` also throws an error. What does the caller see?

**Answer:** During TWR handling, the close error can be suppressed onto Ebody; then `finally` throws Efinally and replaces the pending outcome. The caller sees Efinally, and does not automatically receive Ebody or its suppressed exceptions unless code explicitly preserves them.

## 29. Summary

The core rules can be remembered in two sentences:

- **`try/catch/finally`:** determine the completion of `try` or `catch`, then check whether `finally` completes normally or replaces it with a new completion.
- **`try-with-resources`:** resources initialize left→right and close right→left; a body/init exception is kept as primary while close errors are suppressed when a primary exists; if no primary exists, a close error can become the primary error and even replace a pending `return`.

Use the tables to **predict control flow**, then also check **state, resources, cause, suppressed exceptions, and ownership** to evaluate whether an API is truly safe. In production code, avoid unintended `return`/`throw` in `finally` and prefer `try-with-resources` for `AutoCloseable`, while still designing dedicated transactions/rollbacks when operations have side effects outside the JVM.