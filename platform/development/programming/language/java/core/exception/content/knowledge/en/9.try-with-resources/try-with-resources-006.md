# Resource Closing Order Is the Reverse of Creation Order in Java try-with-resources

When using **try-with-resources**, Java automatically calls `close()` on resources that were successfully initialized when exiting the `try` block. If multiple resources are declared in the same `try (...)` header, Java **initializes them from left to right, but closes them in the reverse order: from right to left**. This is an important rule for managing layered, interdependent resources and for predicting outcomes when exceptions occur.

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

The snippet above is **pseudocode following Java syntax**, where `Resource` must be a class implementing `AutoCloseable` and the methods `openA`, `openB`, `openC`, and `use` must exist. When all operations succeed:

~~~text
Initialization: A -> B -> C
Usage:          try body
Closing:        C -> B -> A
~~~

The JVM does not “close everything at once” or in a random order; for resources declared sequentially in the same try-with-resources statement, the closing order is strictly defined by Java. This rule still applies whether the `try` body finishes normally, executes `return`, or throws an exception — as long as the Java thread is still able to execute the exit from the `try` construct.

## 1. Why Is Closing in Reverse Order Necessary?

In real-world systems, resources are often **built in layers**: a later resource uses or wraps an earlier resource.

Intuitive example:

~~~text
Open underlying data stream InputStream
         |
Create InputStreamReader reading from the underlying stream
         |
Create BufferedReader reading from InputStreamReader
         |
        Use
         |
Close BufferedReader
         |
Close the underlying reader / root stream via the chained closing mechanism
~~~

When managing a chain of objects, closing the outer layer first ensures that it performs its final operations (such as flushing) and no longer uses the lower layer after the lower layer has already been closed.

You must not infer that **all independent objects have a dependency relationship** simply because they are declared next to each other. Reverse order is a **language rule**, whereas the reason for creating resources in a particular order depends on the application's design.

Closing in reverse order is commonly called **LIFO** (*last in, first out*): the object initialized last is closed first. With three resources `A, B, C` in the same list, the order is:

| Phase | Order |
| --- | --- |
| Evaluate and initialize resources | `A`, then `B`, then `C` |
| Execute the `try` body | Once all required resources have been successfully initialized |
| Call `close()` | `C`, then `B`, then `A` |

Do not confuse this rule with the garbage collector's object finalization/collection order. Try-with-resources calls `close()` following program control flow; it does **not** wait for the garbage collector to detect that an object is no longer referenced.

## 2. Requirements for an Object to Be Used in try-with-resources

A resource must be of a type that is convertible to `java.lang.AutoCloseable`. The core interface has the following form:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

The signature above describes the API at a basic level. An implementing class is allowed to **narrow or omit** checked exceptions in `close()`:

~~~java
static final class SimpleResource implements AutoCloseable {
    private final String name;

    SimpleResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}
~~~

This is a nested class declaration that can be placed inside a Java class. `SimpleResource.close()` does not declare any checked exception, so code using it does not have to handle `Exception` just because the general definition of `AutoCloseable` has `throws Exception`.

Single-resource syntax:

~~~java
try (SimpleResource r = new SimpleResource("A")) {
    System.out.println("body");
}
~~~

Expected stdout:

~~~text
open A
body
close A
~~~

When there are multiple resources, write the declarations inside the parentheses after `try`, separated by semicolons:

~~~java
try (SimpleResource a = new SimpleResource("A");
     SimpleResource b = new SimpleResource("B")) {
    System.out.println("body");
}
~~~

Output:

~~~text
open A
open B
body
close B
close A
~~~

**Key distinction:** `AutoCloseable.close()` can throw `Exception`, whereas `java.io.Closeable.close()` declares `IOException` and is commonly used for I/O APIs. Concrete classes may have narrower signatures. The impact on a method's `throws` clause depends on the static type of the resource and the checked exceptions that can escape from `close()`.

## 3. When Does Java Close Resources?

Resource closing occurs when the try-with-resources body **completes in any valid way that requires exiting the construct**:

- The body finishes executing all statements normally.
- The body prepares to `return` a value.
- The body throws an exception, even if a `catch` block handles it afterward.
- `break` or `continue` causes control flow to leave the corresponding try-with-resources scope.

If the `try` body waits indefinitely or enters an infinite loop with no exit path, there is no automatic “closing timer” mechanism. Similarly, if the process is forcibly terminated, there is no guarantee that `close()` will run. None of these change the closing order **if** Java gets the chance to perform the closing.

### `return` Still Closes Resources Before the Caller Receives the Value

~~~java
static int returnAfterClosing() {
    try (SimpleResource a = new SimpleResource("A");
         SimpleResource b = new SimpleResource("B")) {
        System.out.println("prepare return");
        return 7;
    }
}
~~~

If the caller runs `System.out.println("value=" + returnAfterClosing());`:

~~~text
open A
open B
prepare return
close B
close A
value=7
~~~

`return` determines the return value first, and then both resources are closed before the method actually completes and the caller receives `7`. If a `close()` call throws an exception, returning the result can be replaced by throwing that exception — as explained in the section on closing failures.

## 4. A Complete Java 17+ Program to Observe the Order

The program below runs multiple scenarios with custom resources to make the output clear. Each resource prints a line when opened and a line when closed; some resources are configured to **throw `IOException` when closed**.

Create the file **`ResourceCloseOrderDemo.java`**:

~~~java
import java.io.IOException;

public class ResourceCloseOrderDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("== normal ==");
        normal();

        System.out.println("== body failure ==");
        bodyFailure();

        System.out.println("== close failure ==");
        closeFailure();

        System.out.println("== initialization failure ==");
        initializationFailure();

        System.out.println("== return ==");
        System.out.println("result=" + returnEarly());
    }

    static void normal() {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false);
             Tracked c = new Tracked("C", false)) {
            System.out.println("body ok");
        } catch (IOException e) {
            System.out.println("unexpected: " + e.getMessage());
        }
    }

    static void bodyFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true)) {
            System.out.println("body throws");
            throw new IllegalArgumentException("work");
        } catch (IllegalArgumentException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        } catch (IOException e) {
            System.out.println("unexpected I/O: " + e.getMessage());
        }
    }

    static void closeFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true)) {
            System.out.println("body ok");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        }
    }

    static void initializationFailure() {
        try (Tracked a = new Tracked("A", true);
             Tracked b = new Tracked("B", true);
             Tracked c = failToInitializeC()) {
            System.out.println("body not reached");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            printSuppressed(e);
        }
    }

    static Tracked failToInitializeC() throws IOException {
        System.out.println("open C failed");
        throw new IOException("init-C");
    }

    static int returnEarly() throws IOException {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false)) {
            System.out.println("return prepared");
            return 7;
        }
    }

    static void printSuppressed(Throwable e) {
        for (Throwable s : e.getSuppressed()) {
            System.out.println("suppressed=" + s.getMessage());
        }
    }
}
~~~

Compile and run (Java 17 or later):

~~~bash
javac ResourceCloseOrderDemo.java
java ResourceCloseOrderDemo
~~~

**Exact stdout:**

~~~text
== normal ==
open A
open B
open C
body ok
close C
close B
close A
== body failure ==
open A
open B
body throws
close B
close A
primary=work
suppressed=close-B
suppressed=close-A
== close failure ==
open A
open B
body ok
close B
close A
primary=close-B
suppressed=close-A
== initialization failure ==
open A
open B
open C failed
close B
close A
primary=init-C
suppressed=close-B
suppressed=close-A
== return ==
open A
open B
return prepared
close B
close A
result=7
~~~

### Verifying the Normal Case

`normal()` initializes three objects `A`, `B`, and `C`. After `body ok`, Java sequentially calls `C.close()`, `B.close()`, and `A.close()`. Because no exception occurs, the `catch` branch does not execute.

### Verifying the Case Where the `try` Body Throws an Exception

`bodyFailure()` has the primary exception `IllegalArgumentException("work")`. Even though the `try` body threw an error, Java still attempts to close `B` and then `A`. Both `close()` calls also throw `IOException`, but **they do not replace the `work` exception as the primary error**: the closing errors are added to the **suppressed exceptions** list of the primary exception.

Because `B` closes first, `close-B` appears before `close-A` in `getSuppressed()`. The primary exception type remains `IllegalArgumentException` and the primary message remains `work`.

### Verifying the Case Where Only `close()` Fails

In `closeFailure()`, the `try` body completes normally. When closing `B`, `IOException("close-B")` is thrown; Java continues to close `A`. The `close-A` error occurs afterward, so it is recorded as *suppressed* on the `close-B` exception. Once closing finishes, `catch (IOException e)` receives the primary error `close-B`.

Note the distinction: in the situation where **the `try` body has no error**, the first resource-closing error in closing order can become the primary exception.

### Verifying the Case Where Initialization Fails Mid-Way

`initializationFailure()` successfully creates `A` and then `B`. When reaching resource `C`, the initialization expression `failToInitializeC()` throws `IOException("init-C")` **before successfully creating object `C`**. Java does not execute the `try` body, nor is there a successfully initialized resource `C` to close automatically.

However, `B` and `A` were already created successfully earlier, so they are still closed **in reverse order**, meaning `B` before `A`. If closing them causes errors, those errors are recorded as suppressed exceptions on the initialization error `init-C`.

### Verifying the `return` Case

`returnEarly()` prepares to return `7`, yet it still has to close `B` and then `A` before the caller prints `result=7`. The method's `throws IOException` signature is valid because `Tracked.close()` can throw `IOException`, even though in this run neither resource is configured to fail on close.

## 5. What If the Second or Third Resource Fails to Initialize?

Let's distinguish two situations:

**Situation A — Initializing `B` fails:**

~~~java
try (Resource a = openA();
     Resource b = openBThatThrows();
     Resource c = openC()) {
    runTask();
}
~~~

This is pseudocode used to explain the order. When `openA()` finishes and `openBThatThrows()` throws an error:

1. `A` has been successfully initialized.
2. `B` has not been established as a successfully created resource; `C` has not been initialized yet.
3. The `try` body is not executed.
4. Java closes `A`.
5. The exception from initializing `B` continues to propagate outward; any error when closing `A` may be suppressed onto that exception.

**Situation B — Initializing `C` fails:** `A` and `B` have already been initialized, so both are closed in the order `B` then `A`, as shown in the runnable Java example in Section 4.

Do not say “every resource mentioned in the header is closed”: only resources that **have been successfully initialized and are managed by the construct** have `close()` called automatically. For a constructor that fails partway through, any internal resources that the constructor opened before handing off the object may need to be **cleaned up by the constructor or factory method itself**; the outer try-with-resources cannot automatically close an object that was never successfully constructed.

## 6. Primary Exception and Suppressed Exceptions Mechanism

Using multiple resources often leads to the scenario: **the `try` body fails, and then one or more resources also fail when closing**. Java does not want cleanup errors to accidentally hide the primary cause.

Suppose:

~~~text
body:       throw WorkException("work")
close C:    throw IOException("close C")
close B:    return normally
close A:    throw IOException("close A")
~~~

With try-with-resources, the error relationship is organized as follows:

~~~text
Primary exception:
  WorkException("work")
  ├── suppressed: IOException("close C")
  └── suppressed: IOException("close A")
~~~

The suppressed order reflects the **actual order in which errors are added as resources close**, which normally corresponds to the reverse closing order: `C` then `A` in this example.

### Case Where the `try` Body Succeeds but Multiple `close()` Calls Fail

Suppose `A` and `B` are opened, the `try` body finishes normally, `B.close()` throws an error, and then `A.close()` also throws an error:

~~~text
Primary:    IOException("close B")
Suppressed: IOException("close A")
~~~

There is no exception from the `try` body to serve as the primary exception, so the first closing exception is kept as the primary exception. Subsequent closing errors are attached to it.

### How to Read Them in Code

~~~java
try (Tracked a = new Tracked("A", true);
     Tracked b = new Tracked("B", true)) {
    throw new IllegalStateException("operation failed");
} catch (Exception e) {
    System.out.println("Primary: " + e.getMessage());
    for (Throwable suppressed : e.getSuppressed()) {
        System.out.println("Suppressed: " + suppressed.getMessage());
    }
}
~~~

This is an **illustrative snippet** using the `Tracked` class from the main program. It prints the primary error from the `try` body and the preserved closing errors. `getSuppressed()` returns an array containing the attached exceptions without turning them into `getCause()`.

Distinction:

| Property / Method | Meaning |
| --- | --- |
| `getCause()` | A single underlying exception/cause linked via cause |
| `getSuppressed()` | Secondary exceptions retained while the primary exception remains prioritized |
| `getMessage()` | The message of the specific exception object being inspected |
| `printStackTrace()` | Can display the primary error, cause, and suppressed exceptions for diagnosis |

**Suppressed exceptions do not mean those errors are ignored.** They remain important for investigating which resource failed during closing. You should not log only `e.getMessage()` if you need to preserve full resource-closing details.

## 7. How Does try-with-resources Differ from a Manually Written `finally { close(); }`?

Manual closing pattern:

~~~java
Resource a = openA();
Resource b = openB();
try {
    use(a, b);
} finally {
    b.close();
    a.close();
}
~~~

This is **illustrative pseudocode**, not a standalone program. It has at least two risks:

1. If `openB()` fails **before entering `try`**, the `finally` block has not yet started managing `A`, leading to a failure to close the already opened resource.
2. If `b.close()` throws an error, the `a.close()` statement afterward **may not execute**, because control flow exits `finally` before reaching that line.

With try-with-resources, Java arranges the closing mechanism so that all successfully initialized resources are **attempted to be closed in reverse order**, even if closing a later resource throws an error. In addition, Java manages suppressed exceptions according to well-defined rules, preventing errors from the `try` body from being accidentally lost.

A more robust manual `finally` version requires nested `try/finally` blocks, separate exception handling for each close call, and handling partial initialization — which is more error-prone and harder to read. That is why **try-with-resources is preferred** whenever a resource implements `AutoCloseable`.

### Conceptual Diagram of Reverse Closing

~~~text
A created successfully
  └── B created successfully
        └── C created successfully
              └── Run body
                  └── Close C
              └── Close B
          └── Close A
~~~

This is a **conceptual diagram**, not an exact bytecode-for-bytecode transformation. Java can use logic equivalent to nested `try/finally` blocks while tracking the primary exception and suppressed errors.

## 8. Closing Order and Lifecycle of Dependent Resources

Resources may not be independent. For example, APIs often have layered data reading:

~~~java
try (java.io.InputStream raw =
             java.nio.file.Files.newInputStream(path);
     java.io.InputStreamReader decoder =
             new java.io.InputStreamReader(raw,
                     java.nio.charset.StandardCharsets.UTF_8);
     java.io.BufferedReader buffered =
             new java.io.BufferedReader(decoder)) {
    System.out.println(buffered.readLine());
}
~~~

This is an illustrative snippet that requires a `path` variable of type `Path` and appropriate `IOException` handling in the enclosing method.

The management sequence of the construct above is:

1. Initialize `raw`.
2. Initialize `decoder` from `raw`.
3. Initialize `buffered` from `decoder`.
4. Read data.
5. Call `buffered.close()`, then `decoder.close()`, then `raw.close()`.

**Warning about duplicate closing:** Java wrapper classes often **automatically close the underlying resource** when `close()` is called. Therefore, putting all three resources in the same header demonstrates the order, but in real-world design it can cause the underlying layer to receive multiple close calls. You should not assume every resource type tolerates repeated `close()` calls or that every wrapper shares the same ownership policy.

With a wrapper chain where the outer wrapper owns the inner resource, you can consider letting **only the outer wrapper manage closing**, according to the specific API contract:

~~~java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(
                     path, java.nio.charset.StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
~~~

This is an illustrative snippet using `Files.newBufferedReader`. The caller does not have to manually list all the stream/decoder layers when the API returns a single resource that handles closing according to its contract.

The **ownership** principle is just as important as the order: which component is given responsibility for closing, whether the resource is shared, and whether closing the wrapper entails closing the underlying resource.

## 9. Pre-Existing Resources and Java 9+ Syntax

Since Java 9, you can pass an **already-existing resource variable** into try-with-resources, provided it is `final` or **effectively final** and satisfies the `AutoCloseable` type:

~~~java
Tracked resource = new Tracked("existing", false);

try (resource) {
    System.out.println("use existing");
}
~~~

This is an illustrative snippet using the `Tracked` class from the earlier program. When the `try` block ends, the resource is closed automatically even though it was initialized before the `try` header.

With multiple pre-existing variables, the order in which they appear in the list still determines the closing order:

~~~java
Tracked first = new Tracked("first", false);
Tracked second = new Tracked("second", false);

try (first; second) {
    System.out.println("body");
}
~~~

`second` is closed before `first`.

**Note:** In the pre-existing variable example, actual creation occurred in statements before `try`; the closing rule is based on **the listing order in the try-with-resources header**, not on the JVM “remembering object creation history.” For instance, you can declare `try (second; first)`, which will close `first` before `second`. Therefore, the phrasing “reverse of creation order” is most accurate when talking about **declarations that create resources directly inside the `try` header**. When using pre-existing variables, it is more accurate to say **the reverse order of resources in the managed list**.

You should not reuse the same resource object in multiple entries of the list as a trick: it can cause `close()` to be called multiple times on the same object, violating the ownership assumptions of some APIs.

## 10. When a Resource Is `null`

A resource variable can be initialized to `null` if its type is valid:

~~~java
AutoCloseable optional = null;
try (optional) {
    System.out.println("body");
}
~~~

This is a valid example in Java 9 and later because `optional` is effectively final. When the block ends, Java **does not call `close()` on a `null` reference**. It does not throw a `NullPointerException` merely because a resource entry in the `try` header is `null`.

However, that does not mean every resource should allow `null` in API design. If a missing resource is an invalid state, you should check and report an error explicitly rather than using `null` to skip necessary work.

If entries `A`, `B`, `C` include `B == null`, the effective closing sequence is `C` and then `A`; entry `B` has no object to close.

## 11. Closing Order with `catch` and `finally` of the Same Construct

Try-with-resources can be accompanied by `catch` and `finally` clauses:

~~~java
try (Tracked a = new Tracked("A", false);
     Tracked b = new Tracked("B", false)) {
    System.out.println("body");
} catch (java.io.IOException e) {
    System.out.println("catch: " + e.getMessage());
} finally {
    System.out.println("finally");
}
~~~

This snippet uses the previously defined `Tracked` class. If no error occurs, the output order is:

~~~text
open A
open B
body
close B
close A
finally
~~~

**Resources are closed before any `catch` or `finally` clause attached to the try-with-resources construct runs.** If an error from the `try` body or a closing error occurs, the `catch` blocks will observe the exception after the closing process has already been performed according to the rules. `finally` runs after the corresponding `catch` block.

For example, if `B.close()` throws `IOException` while the `try` body throws nothing, `catch (IOException e)` will receive that closing error. If the `try` body throws `IllegalArgumentException` and `B.close()` throws `IOException`, `catch (IOException e)` does **not** automatically catch that suppressed error as the primary exception; you need a handler matching the propagating exception and inspect `getSuppressed()` if needed.

## 12. When `close()` Throws an Error, Does Java Still Close Earlier Resources?

**Yes — under try-with-resources rules**, Java attempts to close the remaining successfully initialized resources in reverse order, even if a `close()` call just threw an exception.

This creates a difference from a manual `finally` block that simply lists:

~~~java
finally {
    b.close();
    a.close();
}
~~~

In that manual snippet, if `b.close()` throws an error and there is no extra handling, Java does not proceed to `a.close()`. With try-with-resources, closing the remaining resources is arranged separately, and any resulting errors are managed using suppressed exceptions.

Even so, you should understand the limits of “attempts to”:

- If a `close()` call **hangs indefinitely**, the thread cannot proceed to close the remaining resources.
- If the process is forcibly killed, there is no guarantee the remaining `close()` calls will run.
- If a `close()` call invokes `System.exit` or `Runtime.halt`, JVM termination rules may prevent further closing.
- If the code or VM encounters an error too severe to continue execution, complete cleanup cannot be guaranteed.

Try-with-resources improves **ordering and error management in normal Java control flow**; it is not a mechanism that guarantees safety regardless of whether the process is still running.

## 13. AutoCloseable, Closeable, and Designing Custom Resources

When writing your own `AutoCloseable` class, you should clearly define:

- What a single `close()` call must do (close a connection, release a lock, flush a buffer, finalize a transaction, or simply reclaim resources).
- Is it safe to call `close()` repeatedly?
- What exception types can `close()` throw?
- Can the resource be shared/owned by multiple components?
- Does closing a wrapper automatically close the underlying object?

Example of a simple class that is safe to close when called repeatedly:

~~~java
static final class IdempotentResource implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        System.out.println("closed once");
    }
}
~~~

This is an illustrative nested class. In a multithreaded program, if an object can be closed concurrently from multiple threads, appropriate synchronization must be designed; a plain `closed` field alone is not enough to guarantee thread safety.

**Not every library's `close()` is idempotent.** Check the contract of the specific resource, especially when combining wrappers that auto-close underlying layers with a multi-resource list.

If a resource requires multiple steps during closing, ensure error handling does not accidentally skip an important step or mask the root cause. In complex cases, adding suppressed exceptions allows retaining information about multiple failures, though an appropriate logging and failure-reporting policy is still needed.

## 14. Common Misconceptions

**Misconception 1: “Declare A then B, and Java closes A first.”**  
No. If they are in the same try-with-resources header, Java closes `B` before `A`.

**Misconception 2: “Java closes resources concurrently.”**  
No. `close()` calls are executed sequentially in reverse closing order. Only if `close()` itself actively uses asynchronous operations might its internal behavior differ.

**Misconception 3: “If the body throws an error, resources are not closed.”**  
No. Successfully initialized resources are still attempted to be closed when exiting the `try` scope.

**Misconception 4: “If closing B fails, A will definitely not be closed.”**  
That is not true for try-with-resources in normal Java control flow. Java continues attempting to close `A` and manages the suppressed exception.

**Misconception 5: “If C's constructor fails, Java must still call `C.close()`.”**  
No. If `C` was not successfully initialized, it never becomes a managed resource; only `A` and `B`, which succeeded earlier, are closed according to the rules.

**Misconception 6: “Any close error replaces the body error.”**  
No. When the `try` body has already thrown the primary error, close errors are normally attached via `getSuppressed()`.

**Misconception 7: “If the body has no error, a close error is only suppressed.”**  
No. The first closing error can become the primary exception when no other error is propagating.

**Misconception 8: “`getCause()` and `getSuppressed()` are the same.”**  
No. Cause describes a causal relationship; suppressed holds additional errors that do not replace the primary exception.

**Misconception 9: “If `return` is written inside try, the caller receives the value before close.”**  
No. Closing occurs before the call completes. If close throws a checked exception, the caller may receive the error instead of the value.

**Misconception 10: “Pre-existing resource variables always close in reverse chronological order of when they were created.”**  
No. With Java 9+ syntax `try (first; second)`, the closing order is the reverse of **how they are listed in the header**, regardless of when the two variables were created.

**Misconception 11: “The outer wrapper and all underlying layers must all be declared in the same header.”**  
Not necessarily. Closing the wrapper may automatically close the underlying layer; you need to understand the ownership contract to avoid duplicate closing.

**Misconception 12: “Try-with-resources guarantees close after the JVM is killed.”**  
No. When there is no longer an opportunity to run Java code, neither `finally` nor try-with-resources can guarantee execution.

**Misconception 13: “A `null` resource will cause close to throw NullPointerException.”**  
No. A resource entry whose value is `null` does not have `close()` called on it automatically.

**Misconception 14: “Any object can be used in try (...) because Java will look for a close method.”**  
No. The static type of the resource must be compatible with `AutoCloseable`; merely having a method named `close()` without implementing the appropriate interface is not enough.

## 15. Self-Check Questions

1. Given `try (A a = ...; B b = ...; C c = ...)`, what are the initialization and closing orders, respectively?
2. Why does LIFO resource closing usually make sense when a new object is built on top of an existing object?
3. A method executes `return` from inside a try-with-resources block: are the resources closed before or after the caller receives the result?
4. If the `try` body throws `IllegalArgumentException("work")`, and both `B.close()` and `A.close()` throw `IOException`, which exception is primary?
5. In question 4, in what order does `getSuppressed()` contain the errors?
6. If the `try` body finishes normally, but `B.close()` fails and then `A.close()` fails, which exception is primary?
7. If resource `C` fails to initialize, which resources initialized successfully before it does Java close?
8. If `B`'s constructor opens an internal socket and then throws before successfully constructing `B`, who is responsible for reclaiming that socket?
9. Why can a manually written `finally { b.close(); a.close(); }` miss calling `a.close()`?
10. In a try-with-resources with `catch` and `finally`, are resources closed before or after those blocks?
11. Given pre-existing `Tracked first` and `Tracked second`, in what order will `try (second; first)` close them?
12. If a resource entry has the value `null`, does Java automatically call `close()` on `null`?
13. Why does putting both `BufferedReader` and the underlying `InputStream` in the header sometimes lead to duplicate resource closing?
14. Is it enough for a class to simply declare a `void close()` method to be used in try-with-resources?
15. Can try-with-resources guarantee all resources are closed if one `close()` hangs indefinitely?
16. When designing a custom `AutoCloseable`, why is it necessary to clearly define ownership and behavior if `close()` is called multiple times?

### Suggested Answers

1. Initialization `A -> B -> C`, closing `C -> B -> A`.
2. So that the newer layer stops using the underlying resource before the underlying layer is closed.
3. Before the caller receives the result.
4. The `work` error from the `try` body is primary.
5. `close-B` then `close-A`, because `B` closes first.
6. `close-B` is primary, and `close-A` is suppressed.
7. Closes `B` then `A`; does not automatically close `C`, which failed to initialize.
8. The constructor/method opening the resource is responsible for cleaning up anything not yet handed over.
9. If `b.close()` throws an error, the statement to close `a` may not be executed.
10. Before the `catch` and `finally` blocks attached to that construct.
11. Closes `first` then `second`, the reverse of the listing order.
12. No.
13. Wrappers typically already close the underlying resource in `close()`, leading to multiple close calls.
14. No, it must be compatible with `AutoCloseable`.
15. No; the thread cannot advance to the remaining close calls if it is stuck.
16. To avoid missing closes, duplicate closes, or corrupting a resource used by multiple components.

## 16. Key Takeaways

**Resources in try-with-resources are initialized from left to right and closed from right to left.** If the `try` body throws an error, Java still attempts to close the successfully initialized resources; closing errors are normally stored as **suppressed exceptions** on the primary error. If there was no prior error, the first closing error can become primary. If initialization stops partway through, the resources already opened successfully are still closed in reverse order. For pre-existing resource variables in Java 9+, closing order is based on their listing position in the header; design ownership clearly and use try-with-resources to avoid missed cleanup compared to manual `finally`.