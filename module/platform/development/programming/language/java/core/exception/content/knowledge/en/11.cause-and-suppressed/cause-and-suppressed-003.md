# Distinguishing the Outermost Exception from the Deepest Cause in Java

When a Java operation fails, the exception that the top layer **catches or observes** is not necessarily the exception that **started the failure chain at the lowest layer**. An I/O layer may throw an `IOException`; the service layer catches the I/O error and throws an `IllegalStateException` with `IOException` as its cause; the startup layer then wraps the service error into a `RuntimeException`. In that case, there are three different exception objects and three messages serving different contexts.

Useful terminology:

- **Outermost exception** is the `Throwable` object currently observed at the handling or logging point, such as the `ex` parameter in a top-level `catch`. It may be a newly created object wrapping an error from a lower layer.
- **Immediate cause** is the result of `outer.getCause()` when it is non-`null`.
- **Deepest cause (sometimes called root cause in a technical sense)** is the object at the end of a finite `getCause()` chain, where `getCause() == null`.
- **Suppressed exception** is accessed via `getSuppressed()`; it is a separate branch and **does not automatically belong to the `getCause()` chain**.

**Key point:** "the deepest cause in a `Throwable` chain" is not automatically synonymous with **the business, infrastructure, or operational root cause**. The cause chain is merely the exception links created by the source code; finding the actual failure requires combining input data, logs, system state, and the operation context.

This lesson explains how to read outermost/cause/deepest, how to preserve information when wrapping exceptions, how to distinguish cause from suppressed, how to avoid losing causes, and how to traverse the chain safely on Java 17+.

## 1. An error can pass through multiple layers and change exception names

Suppose an application has three layers:

~~~text
Application startup layer: start()
    └── Service layer: service()
        └── Data access layer: repository()
~~~

At the lowest layer, `repository()` encounters a device read failure and throws:

~~~java
throw new java.io.IOException("ổ đĩa không phản hồi");
~~~

The `service()` layer cannot load the configuration. Instead of throwing the raw `IOException` directly, this layer can wrap it:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException("không tải cấu hình", ex);
}
~~~

The `start()` layer further provides startup context:

~~~java
catch (IllegalStateException ex) {
    throw new RuntimeException("khởi động thất bại", ex);
}
~~~

The final object that the caller of `start()` sees is `RuntimeException("khởi động thất bại")`. However, its `getCause()` points to `IllegalStateException("không tải cấu hình")`, and that object's `getCause()` points to `IOException("ổ đĩa không phản hồi")`.

Object structure:

~~~text
RuntimeException: khởi động thất bại     ← OUTERMOST at caller
    │
    └── cause → IllegalStateException: không tải cấu hình
                    │
                    └── cause → IOException: ổ đĩa không phản hồi
                                     │
                                     └── cause → null  ← DEEPEST
~~~

When the application catches `RuntimeException`, Java **does not automatically pass the deepest exception into the `catch` variable**. That variable references the exception being thrown outward; to inspect deeper causes, you need to call `getCause()` layer by layer.

## 2. Four concepts to distinguish

| Concept | How to identify | Practical meaning |
| --- | --- | --- |
| Outermost | The object just caught, received from an API, or logged | Classifies the error at the current boundary; usually carries context understandable to the calling layer |
| Immediate cause | `outer.getCause()` | The closest error that led to creating/wrapping the outermost exception |
| Deepest cause | The final layer along the `getCause()` chain down to `null` | The exception at the bottom of the recorded cause-link chain |
| Suppressed | `outer.getSuppressed()` or suppressed on any cause | Secondary errors, often occurring while cleaning up resources while a primary error already exists |

Example:

~~~java
Throwable deepest = new java.io.IOException("không đọc được");
Throwable middle = new IllegalStateException("dịch vụ thất bại", deepest);
Throwable outer = new RuntimeException("yêu cầu thất bại", middle);

System.out.println(outer.getMessage());                    // yêu cầu thất bại
System.out.println(outer.getCause().getMessage());         // dịch vụ thất bại
System.out.println(outer.getCause().getCause().getMessage()); // không đọc được
~~~

This is an **illustrative snippet inside a single method**. The three objects have **distinct identities**. An exception object created at a higher layer does not erase the lower-layer object if the constructor stores the cause properly.

The term "outermost" is **relative to the observation point**. If you catch immediately inside `repository()`, `IOException` can be the object caught there. If the service layer wrapped and propagated the error, `IllegalStateException` is the outermost at the service caller. If the startup layer wraps it again, `RuntimeException` becomes the outermost at the outermost caller.

You should not assign a fixed "outermost" role to a specific exception class in every context.

## 3. Complete Java 17+ program: traversing from outermost to deepest

Save the file `CauseChainDemo.java`:

~~~java
import java.io.IOException;

public class CauseChainDemo {
    static void repository() throws IOException {
        throw new IOException("ổ đĩa không phản hồi");
    }

    static void service() {
        try {
            repository();
        } catch (IOException ex) {
            throw new IllegalStateException("không tải cấu hình", ex);
        }
    }

    static void start() {
        try {
            service();
        } catch (IllegalStateException ex) {
            throw new RuntimeException("khởi động thất bại", ex);
        }
    }

    public static void main(String[] args) {
        try {
            start();
        } catch (RuntimeException outer) {
            System.out.println("Ngoài cùng: " + outer.getMessage());
            Throwable current = outer;
            int level = 0;
            while (current != null) {
                System.out.println("Tầng " + level + ": "
                        + current.getClass().getSimpleName()
                        + " - " + current.getMessage());
                if (current.getCause() == null) {
                    System.out.println("Sâu nhất: " + current.getMessage());
                }
                current = current.getCause();
                level++;
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CauseChainDemo.java
java CauseChainDemo
~~~

Exact stdout:

~~~text
Ngoài cùng: khởi động thất bại
Tầng 0: RuntimeException - khởi động thất bại
Tầng 1: IllegalStateException - không tải cấu hình
Tầng 2: IOException - ổ đĩa không phản hồi
Sâu nhất: ổ đĩa không phản hồi
~~~

### Layer-by-layer flow analysis

1. `repository()` creates and throws an `IOException` object to simulate an I/O failure.
2. `service()` catches `IOException` and creates a **new object** `IllegalStateException("không tải cấu hình", ex)`. The second argument links the I/O error as the **cause**.
3. `start()` catches `IllegalStateException` and creates another object `RuntimeException("khởi động thất bại", ex)` with the service error as its cause.
4. `main()` receives the `RuntimeException` from the startup layer; that is the **outermost at `main`**.
5. The loop starts from the outermost and calls `getCause()` layer by layer until `null`. The deepest error in the chain is `IOException("ổ đĩa không phản hồi")`.
6. In this example, every wrapping constructor **preserves the cause**, so no layer is lost from the chain.

This output intentionally prints only the **simple class name and message** for stability. A real stack trace also contains frames with file names and line numbers, which should be recorded when diagnosing real-world failures.

## 4. `getCause()` is a cause link, not an "auto-discovered Java exception"

`Throwable.getCause()` returns **the cause reference that was set** on the object, or `null` when no cause is available. It does not query the system on its own, does not analyze stack traces to infer deeper errors, and does not automatically find the "root cause" from logs.

Two common ways to link a cause:

~~~java
// Approach 1: Constructor taking message and cause.
throw new IllegalStateException("bước nghiệp vụ thất bại", original);
~~~

~~~java
// Approach 2: Some legacy Throwables support initCause.
// Use when the cause has not been initialized beforehand.
IllegalStateException wrapper = new IllegalStateException("bước nghiệp vụ thất bại");
wrapper.initCause(original);
throw wrapper;
~~~

Both snippets are **illustrative in a context where `original` is non-`null`**. You must not arbitrarily call `initCause()` after a constructor has already set a cause, even if it was set to `null`. Most modern Java code should prefer the `(message, cause)` constructor when the exception class provides it.

Wrapping an error is **not mandatory**: if an upper layer has no reason to add context or change the contract, it can `throw ex;` (rethrow the same object) and avoid creating an extra cause layer. A 10-layer-deep chain is not inherently more useful than a short chain if the layers merely repeat the same message.

You should also avoid creating a new exception while **discarding the original error**:

~~~java
// Not good if investigation information needs to be preserved.
catch (IOException ex) {
    throw new IllegalStateException("không tải cấu hình");
}
~~~

In that case, `IllegalStateException` has `getCause() == null` even though an `IOException` actually occurred. Anyone inspecting only the `getCause()` chain from the outside will **not be able to recover** the I/O error from this new wrapper object alone.

Prefer:

~~~java
catch (IOException ex) {
    throw new IllegalStateException("không tải cấu hình", ex);
}
~~~

Note on the example: the `catch` blocks above need to be placed inside a method with a `try` block containing a call that can throw `IOException`.

## 5. Is the deepest exception the real root cause?

Not necessarily. **Deepest cause is a data-structure term**, whereas **root cause in operational diagnostics** is the answer to "why did the system fail to achieve the expected outcome?".

Example 1: A chain `IllegalStateException → IOException`, where the deepest error is `IOException("Connection reset")`. However, the operational cause might be network configuration, a proxy, firewall rules, connection exhaustion, or an overloaded server. `IOException` itself does not uniquely point to that cause.

Example 2: `InvalidOrderException → NumberFormatException`. The deepest object may be `NumberFormatException`, but the core business bug could be malformed CSV data or an API contract that allowed an empty string through.

Example 3: A low layer throws `NullPointerException`, and a high layer wraps it as `ServiceException`. The `NullPointerException` at the end of the chain may reflect a bug, but finding the cause requires checking which variable was `null`, which request triggered it, and which code violated an invariant.

Therefore, when analyzing an incident:

- Start from the **outermost** to understand which high-level operation failed.
- Read the **entire cause chain**, not just the two ends.
- Cross-reference the **stack trace**, logs, inputs, and runtime state.
- Check **suppressed exceptions**, especially when resources are used.
- Conclude the real root cause from **execution evidence**, not merely because an object sits at the deepest position.

Many libraries name the result of traversing to the end of `getCause()` as `rootCause` in their API. This is a convenient naming convention, not automatic proof of the operational cause.

## 6. If `getCause()` is `null`

`null` can have several meanings:

1. The object is genuinely the initial error with no wrapper before it.
2. The API author did not set a cause, even though the current error occurred after another error.
3. The error was intentionally raised as a standalone business failure, with no `Throwable` cause to record.
4. A wrapper was constructed improperly, losing the cause chain.

Therefore, **you must not infer** that an exception with `getCause() == null` is guaranteed to be the first error that ever occurred in the entire application.

Example:

~~~java
// Illustrative snippet placed inside a method.
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    IllegalStateException wrapped = new IllegalStateException("dữ liệu không hợp lệ");
    System.out.println(wrapped.getCause() == null); // true
}
~~~

`NumberFormatException` occurred, but `wrapped` did not store it. In logs of `wrapped`, the technical deepest cause is `wrapped` itself; that is merely **the bottom of the remaining chain**, not the entire system history.

Do not call `outer.getCause().getMessage()` unconditionally. If the cause is `null`, you will trigger a new `NullPointerException` right inside your error-handling logic.

## 7. A single exception can be both outermost and deepest

There are not always three layers:

~~~java
try {
    throw new IllegalArgumentException("tuổi âm");
} catch (IllegalArgumentException ex) {
    System.out.println(ex == ex);                  // true
    System.out.println(ex.getCause() == null);     // true
}
~~~

This illustrative snippet contains **only one exception object**, which is both the object caught at the outermost point of the example and the final layer in the cause chain. The expression `ex == ex` only illustrates object identity; in real code you would compare against another reference if you needed to check whether a new wrapper was created.

When writing a `deepestCause(Throwable t)` function, if `t` is non-`null` and `t.getCause() == null`, the technical result is usually `t` itself, **not `null`**. Conversely, if your API chooses to return `null` to indicate "no separate cause", that is a **different contract** that must be named and documented clearly.

## 8. `cause` is a linked chain; `suppressed` are secondary branches

`Throwable` does not only have a reference to a cause; it also has an **array of suppressed exceptions**. To visualize:

~~~text
IllegalStateException: không nạp được dữ liệu  ← outermost
    |
    └── Caused by: IOException: đọc tệp lỗi   ← deepest via getCause()
                       |
                       ├── Suppressed: IOException: đóng tệp lỗi
                       └── Suppressed: ... (if there are more)
~~~

In this structure:

- The outermost is `IllegalStateException` because it is being caught at the upper layer.
- `IllegalStateException.getCause()` points to `IOException("đọc tệp lỗi")`.
- `IOException("đọc tệp lỗi").getCause()` is `null`, so it is the deepest cause.
- The error `IOException("đóng tệp lỗi")` is in **`getSuppressed()` of the read error**, not in `getCause()`.
- `outermost.getSuppressed()` can be empty even if a lower cause has suppressed exceptions.

**Different relationships:** `cause` returns at most **one direct reference** per `Throwable`, whereas `suppressed` can contain **multiple objects**. Each suppressed exception can in turn have its own cause and suppressed exceptions.

A traversal loop that only runs:

~~~java
Throwable current = outermost;
while (current != null) {
    System.out.println(current);
    current = current.getCause();
}
~~~

will **not print suppressed exceptions**. That is not a bug in `getCause()`; the code is simply traversing only one kind of link.

## 9. Java 17+ program: inspecting cause and suppressed together

Save the file `SuppressedCauseChainDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedCauseChainDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("đóng tệp lỗi");
        }
    }

    static void read() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("đọc tệp lỗi");
        }
    }

    static void service() {
        try {
            read();
        } catch (IOException ex) {
            throw new IllegalStateException("không nạp được dữ liệu", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException outer) {
            Throwable root = outer.getCause();
            System.out.println("Ngoài cùng: " + outer.getMessage());
            System.out.println("Sâu nhất: " + root.getMessage());
            System.out.println("Suppressed ngoài cùng: " + outer.getSuppressed().length);
            System.out.println("Suppressed nguyên nhân: " + root.getSuppressed().length);
            System.out.println("Lỗi phụ: " + root.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SuppressedCauseChainDemo.java
java SuppressedCauseChainDemo
~~~

Exact stdout:

~~~text
Ngoài cùng: không nạp được dữ liệu
Sâu nhất: đọc tệp lỗi
Suppressed ngoài cùng: 0
Suppressed nguyên nhân: 1
Lỗi phụ: đóng tệp lỗi
~~~

Explanation:

1. In `read()`, the `try-with-resources` body throws `IOException("đọc tệp lỗi")` as the **primary exception**.
2. Upon exiting the body, Java automatically invokes `Resource.close()` and encounters `IOException("đóng tệp lỗi")`; the close error is added to the **suppressed** list of the read error.
3. `service()` catches the read error (which already has the suppressed exception), then creates a new `IllegalStateException` with the read error as its cause.
4. `main()` catches `IllegalStateException` as the outermost exception. Because no suppressed exceptions were attached to the new wrapper, `outer.getSuppressed().length == 0`.
5. The wrapper's cause is `IOException("đọc tệp lỗi")`, so `root.getSuppressed().length == 1`.
6. The program accesses the first element `getSuppressed()[0]` because the execution path of **this fixed example** is guaranteed to produce one suppressed exception. In general-purpose code, you must check the array length before indexing.

If you only read `outer.getMessage()`, you lose information about the read error. If you only read `outer.getCause().getMessage()`, you miss the close error. Both can be important, but they serve different roles.

## 10. How to read `printStackTrace()` and `Caused by:` sections

`Throwable.printStackTrace()` on a typical wrapper chain can output something like:

~~~text
java.lang.RuntimeException: khởi động thất bại
    at Example.start(Example.java:...)
    at Example.main(Example.java:...)
Caused by: java.lang.IllegalStateException: không tải cấu hình
    at Example.service(Example.java:...)
    ...
Caused by: java.io.IOException: ổ đĩa không phản hồi
    at Example.repository(Example.java:...)
    ...
~~~

This is an **illustrative diagram**, not fixed output from `CauseChainDemo.java`: class/file names, line numbers, frame elision, and stack trace printing depend on the actual code.

When reading from top to bottom:

- The first line describes the **outermost** exception being printed.
- Each `Caused by:` section represents a deeper cause link.
- The last `Caused by:` section usually corresponds to the **deepest cause of a finite chain**.
- `Suppressed:` lines, if present, are secondary errors and can appear under **any `Throwable` layer**, not just the outermost.
- `... N more` lines (when they appear) are shorthand for duplicate stack frames in the related chain; they are **not** new exception objects.

Do not equate the *topmost stack trace line* with the *bottom of the cause chain*. The outermost exception has its own stack trace from when the wrapper was created; the deepest exception has its own stack trace, usually near where the low-level error originated.

## 11. Stack traces and cause chains are two different dimensions of information

A `Throwable` can have a stack trace with call frames and **no cause**. Conversely, a wrapper can have a `cause` while being configured not to record a stack trace for itself. Therefore:

- `getStackTrace()` returns the **frames** recorded for the current object.
- `getCause()` returns **another `Throwable` object** designated as the cause.
- `getSuppressed()` returns **other `Throwable` objects** recorded as secondary errors.

For example, if:

~~~java
Throwable error = new IllegalArgumentException("sai dữ liệu");
Throwable wrapper = new IllegalStateException("không xử lý được", error);
~~~

then `wrapper.getStackTrace()` is not "the same thing" as `wrapper.getCause().getStackTrace()`. They describe different creation/trace-recording points of different objects.

When rethrowing the same object with `throw ex;`, Java **does not create a new wrapper by default**, so the object identity and cause chain remain unchanged. With `throw new SomeException("...", ex);`, you get a new outermost object, typically carrying a stack trace at the wrapping site.

Calling `fillInStackTrace()` or `setStackTrace()` can alter an object's trace according to the API contract, so you should not assume a stack trace is immutable forever across all libraries. However, those changes do not create additional cause links.

## 12. Finding the deepest cause: the simple case

For exceptions created by an application via normal wrapping, the cause chain is typically finite and ends at `null`. When you are sure there are no cycles, a straightforward implementation is:

~~~java
// Illustrative code inside a class.
static Throwable deepestCause(Throwable error) {
    if (error == null) {
        return null;
    }
    Throwable current = error;
    while (current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

Example:

~~~java
Throwable low = new java.io.IOException("I/O lỗi");
Throwable outer = new IllegalStateException("dịch vụ lỗi", low);

System.out.println(deepestCause(outer) == low); // true
~~~

These snippets are **illustrative and need to be placed inside a class**, with the `deepestCause` method in an accessible scope or invoked appropriately. The function returns the last exception along `getCause()`, without accessing `getSuppressed()`.

However, the simple `while` loop **assumes the chain has no reference cycles**. In diagnostic tooling that must handle arbitrary inputs from other libraries, you should guard against abnormal cyclic `getCause()` chains.

## 13. A `cause` chain can form a cycle: no finite "bottom"

Java does not allow an object to set **itself** as its own cause via `initCause`, but custom code can still create a **cycle across multiple objects** if `cause` links are wired improperly.

For example, A points to B, and B points back to A:

~~~text
Exception("A") ──cause──> Exception("B")
      ^                         |
      └────────cause────────────┘
~~~

If you use a plain `while (current.getCause() != null)` loop, it will run infinitely. A safe traversal should track **already-seen `Throwable` objects by reference identity**, and if a previously seen object is encountered again, report a cycle instead of claiming a deepest cause.

File `CauseWalkerDemo.java`:

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class CauseWalkerDemo {
    static void printChain(Throwable outer) {
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        Throwable current = outer;
        int index = 0;

        while (current != null) {
            if (!visited.add(current)) {
                System.out.println("Phát hiện vòng: " + current.getMessage());
                return;
            }
            System.out.println(index + ": " + current.getMessage());
            Throwable next = current.getCause();
            if (next == null) {
                System.out.println("Đáy chuỗi: " + current.getMessage());
                return;
            }
            current = next;
            index++;
        }
    }

    public static void main(String[] args) {
        Exception a = new Exception("A");
        Exception b = new Exception("B");
        a.initCause(b);
        b.initCause(a);
        printChain(a);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CauseWalkerDemo.java
java CauseWalkerDemo
~~~

Exact stdout:

~~~text
0: A
1: B
Phát hiện vòng: A
~~~

In this example, **no deepest cause exists under the definition "`getCause() == null`"** — following the links forever just returns to A. This chain was constructed intentionally for safety testing, not as an exception design to use in applications.

`IdentityHashMap` is used to compare by **object identity (`==`)**, without depending on any custom `equals()` implementation. Any utility that traverses both `cause` and `suppressed` should also account for the possibility of an object being referenced repeatedly along different paths.

## 14. `getSuppressed()` can appear at any layer

When analyzing an outermost exception `outer`, you should not check suppressed exceptions only on `outer` and conclude the entire chain has no secondary errors. A secondary error can be attached to the first cause, the second cause, or deeper:

~~~text
Outer A
└── cause B
     ├── suppressed S1
     ├── suppressed S2
     └── cause C
          └── suppressed S3
~~~

The above is a **relationship diagram**, not a representation of absolute execution order. If the goal is to display a complete failure chain, you need to inspect **both `getCause()` and `getSuppressed()` on every encountered object**, with a mechanism to avoid cycles and duplicate references.

In short:

- To get only the **deepest cause**: follow `getCause()`.
- To get **all related errors**: traverse both `cause` and `suppressed`, tracking visited objects by identity.
- To find the **actual operational cause**: combine with system data and knowledge of the operation.

A suppressed exception can also indicate a critical resource failure, such as failing to flush/save data when closing a stream; in some situations, that secondary error is more important to handle than part of the outermost error. The ordering in the `Throwable` tree is a storage model for **exception information**, not a priority ranking for incident remediation.

## 15. When to wrap an exception and when to rethrow?

**Wrapping an exception** is appropriate when a layer wants to add valuable context or translate a technical error into an error that belongs to that layer's contract.

File-reading layer example:

~~~java
// Illustrative snippet inside catch (IOException ex).
throw new ConfigurationLoadException("Không nạp được cấu hình", ex);
~~~

This snippet requires a `ConfigurationLoadException` class defined with a `(String, Throwable)` constructor. It should explain the operation the current layer is responsible for and preserve the cause.

**Rethrowing the same exception** is appropriate when the current layer has no way to handle it and the exception type already fits the contract for the caller:

~~~java
// Illustrative snippet inside catch (IOException ex),
// enclosing method declares throws IOException.
throw ex;
~~~

Avoid wrapping repeatedly at every layer with nearly identical messages:

~~~text
RuntimeException("lỗi")
└── RuntimeException("lỗi")
    └── RuntimeException("lỗi")
        └── IOException("lỗi đọc")
~~~

The chain above preserves the cause, but it can make logs long and hard to read without improving diagnosability. Conversely, **dropping the cause** when wrapping produces an outermost exception with no link back to the error source. Choose wrapping based on **abstraction boundaries and genuinely new information**, not out of habit.

In public APIs, also consider that messages and diagnostic details may contain sensitive data; keep internal causes aligned with logging policies and what is returned to users.

## 16. Familiar wrappers in Java

Many APIs create an exception at an execution boundary to report that a task, reflective call, or asynchronous chain completed abnormally. Some examples:

- `ExecutionException` commonly appears when calling `Future.get()` and the task failed; its cause can be the exception thrown by the task.
- `CompletionException` commonly appears in certain `CompletableFuture` paths and can wrap the actual error in its cause.
- `InvocationTargetException` can appear when invoking a method via reflection; `getCause()` or the historical API `getTargetException()` lets you inspect the error thrown by the invoked method.
- Framework-specific exception classes can also wrap `IOException`, `SQLException`, or a business exception.

You should not **automatically unwrap every wrapper layer** without inspecting the failure condition. For example, `ExecutionException` tells the caller that **the failure path relates to an asynchronous task result**, while its cause tells you what failed inside. Both pieces of context are useful.

Another note: `Future.get()` can also throw other error types such as `InterruptedException` or `CancellationException`. Do not assume that every exception emerging from an async API is guaranteed to have a cause or a deeper layer.

## 17. Collecting error data at the handling boundary

A good diagnostic strategy when handling high-level exceptions:

1. **Log the operation name and safe context**, such as request type, non-sensitive transaction ID, and processing stage.
2. **Keep the outermost exception**, because it shows which layer considered the incident a failure.
3. **Pass the entire `Throwable` when logging** instead of only the `getMessage()` string; an appropriate logger can display the stack trace, cause, and suppressed exceptions.
4. **Traverse `getCause()`** when you need to group errors by layer or find the lowest-level exception.
5. **Inspect `getSuppressed()`** on layers where resources are closed or cleanup logic runs.
6. **Do not log the same exception at every layer** if you are only forwarding it; duplicate logging creates noise and makes it harder to determine the actual number of incidents.
7. **Do not rely on fixed message strings** as control-flow APIs; prefer exception types, documented error codes, or structured results.

Brief illustrative example:

~~~java
// Illustrative snippet inside catch (Exception ex).
logger.error("Không xử lý được yêu cầu", ex);
~~~

`logger` in the example needs to be a logger whose API matches the `error(String, Throwable)` signature. This is a **conceptual pattern**, not a standalone program; the goal is to pass the **`Throwable` object** to the logging system, preserving cause/suppressed information instead of only `ex.getMessage()`.

At the API layer returned to users, you can display a safe message while internal logs retain detailed information according to your observability policy. Do not automatically expose full stack traces to end users.

## 18. Common mistakes

| Misconception | Consequence | Fix |
| --- | --- | --- |
| The exception caught in `catch` is always the original error | Misses wrappers and fails to find the lower-layer error | Traverse `getCause()` when needed |
| `outer.getCause()` is always the deepest cause | With multiple layers, it is only the immediate cause | Traverse to the final cause or detect cycles |
| `getCause() == null` proves the error never had another cause | The cause may not have been recorded when wrapping | Check exception-creation code and related logs |
| Wrapping an exception while dropping the original object | Loses the causal relationship and trace of the earlier error | Use the `(message, cause)` constructor |
| `throw ex` creates another wrapper | In practice it rethrows the same object | Distinguish rethrowing from `throw new` |
| Checking suppressed only on the outermost exception | Secondary errors may live on a deeper cause | Inspect suppressed on each `Throwable` layer |
| Treating suppressed as the cause | Wrong relationship model | Distinguish `getCause()` from `getSuppressed()` |
| Always trusting the deepest cause as the final operational cause | Can misdiagnose system/data issues | Cross-check inputs, environment, stack traces, and logs |
| Calling `getCause().getMessage()` without a `null` check | Can throw `NullPointerException` inside the handler | Check `getCause()` first |
| Traversing `getCause()` unboundedly on arbitrary `Throwable`s | Can hit reference cycles | Track visited objects by identity |
| Logging only `ex.getMessage()` | Loses stack trace, cause, and suppressed | Log the full exception object |
| Wrapping exceptions at every layer with repetitive messages | Long cause chains, noisy logs | Wrap only at boundaries that add new context |
| Indexing `getSuppressed()[0]` without checking | `ArrayIndexOutOfBoundsException` if the array is empty | Check the array length before indexing |

## 19. Self-check exercises

**Q1.** `RuntimeException("start", IllegalStateException("service", IOException("read")))`: which exception is the outermost?

**Answer:** `RuntimeException("start")` if that is the object the caller is catching or observing at the current boundary.

**Q2.** Which object is the deepest if the `getCause()` chain ends at `IOException("read")`?

**Answer:** `IOException("read")`.

**Q3.** Does `outer.getCause()` always return the deepest cause?

**Answer:** No. It returns the **immediate cause**; you must continue following `getCause()` to reach the final layer.

**Q4.** If the outermost exception has `getCause() == null`, can we conclude no lower-level error ever occurred?

**Answer:** No. An error may not have been stored as the cause when creating a wrapper.

**Q5.** The deepest `IOException` has a suppressed `IOException("close fail")`. Is the close error in the `getCause()` chain?

**Answer:** Not simply by virtue of being suppressed. You must inspect `getSuppressed()` on the object that holds the secondary error.

**Q6.** To preserve the original error when converting `IOException` into `IllegalStateException`, what should you write?

**Answer:** `throw new IllegalStateException("new layer description", ex);`.

**Q7.** If there is only a single exception object and `getCause() == null`, which object is the deepest cause under technical traversal?

**Answer:** That same object.

**Q8.** When a `getCause()` chain has a cycle A → B → A, is there a finite deepest cause?

**Answer:** No. Traversal code must detect the cycle and report an abnormal chain.

**Q9.** An outermost wrapper has its own stack trace, and its cause has its own stack trace. Must the two traces be identical?

**Answer:** No; the two objects may have been created at different locations.

**Q10.** Why shouldn't you diagnose using only the deepest cause?

**Answer:** Because it is only the bottom of the exception link chain and does not necessarily point to the real operational/business cause; additional context and evidence are still required.

## 20. Official references

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `initCause()`, `getSuppressed()`, `addSuppressed()`, `printStackTrace()`, and stack traces.
- [Java SE 17 API — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception commonly encountered in the I/O layer.
- [Java SE 17 API — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): exception wrapper for a failed task result.
- [Java SE 17 API — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper in asynchronous completion handling.
- [Java SE 17 API — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): error thrown when invoking a method via reflection.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): exception hierarchy, throwing, and handling.
- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): suppressed exception mechanism when closing resources.

**Conclusion:** the outermost exception is the object observed at the handling point; the deepest cause is the finite end of the `getCause()` link chain; and `getSuppressed()` stores separate secondary error branches. Preserve the cause when wrapping, check suppressed exceptions on relevant layers, and combine the full stack trace with execution context before concluding the root cause of an incident.
