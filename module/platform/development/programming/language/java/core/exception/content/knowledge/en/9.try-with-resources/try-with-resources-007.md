# Handling Resource Creation Failures in Java `try-with-resources`

In Java, `try-with-resources` does more than automatically close resources when the **`try` body** finishes. It also protects a subtler case: **a resource initialization expression in the `try (...)` header fails before the body begins executing**. When that happens, Java must clean up the resources that were already successfully initialized earlier, preserve the primary exception information, and pass the error to the appropriate handler.

For example:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    use(a, b, c);
}
~~~

If `openA()` succeeds but `openB()` throws an exception, Java **closes `a`**, **does not call `openC()`**, **does not run `use(a,b,c)`**, and then propagates the exception from `openB()`. Java **does not automatically call `close()` on an object `b` that was not completely initialized**. If `a.close()` also fails, the closing exception is attached as a **suppressed exception** of the initialization error from B (under the normal suppression mechanism).

This lesson explains the exact order of initialization, closing, exception catching, and `finally` on Java 17+; distinguishes resource-opening errors from resource-usage errors; points out the limitation when a constructor allocates a resource and then fails; and provides runnable examples along with safe design guidelines.

## 1. Conditions for a Resource to Be Managed Automatically

`try-with-resources` supports resources whose type implements `AutoCloseable`, commonly including `Closeable` types such as `InputStream`, `Reader`, or API-specific connection objects. The `try (...)` header declares one or more resource variables:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    int firstByte = in.read();
    System.out.println(firstByte);
}
~~~

This is an **illustrative snippet inside a method** that has a `path` variable of type `Path` and handles or declares `IOException`. If the `Files.newInputStream(path)` expression succeeds and returns a non-`null` stream, that stream is managed by Java and `close()` will be called when leaving the appropriate construct, even if the body throws an exception.

Key characteristics to remember:

1. **Initialization from left to right.** Each resource-opening expression must complete normally before Java begins the next expression.
2. **Closing in reverse order.** Resources that were successfully initialized are closed from right to left when leaving scope.
3. **The body only runs after all required resource expressions complete normally.**
4. **A failing initialization expression** prevents the body from running; previously initialized resources still need to be closed.
5. Associated `catch` and `finally` blocks of the `try-with-resources` construct itself execute **after the automatic cleanup step** for the managed resources.
6. If a resource expression returns `null` **without throwing an error**, that expression still completes normally; Java skips calling `close()` for a `null` reference. This differs from *initialization throwing an exception*.

Do not confuse "the constructor has started running" with "the resource variable has completed initialization and been placed into the managed scope." If a constructor throws before returning a valid object, the corresponding resource variable is not completely initialized for Java to automatically call `close()` on it.

## 2. Execution Flow When a Resource in the Middle of the List Fails

Suppose there are three resources A, B, and C, declared in that order:

~~~java
try (Resource a = openA();
     Resource b = openB();
     Resource c = openC()) {
    System.out.println("Thân try");
} catch (IOException ex) {
    System.out.println("Lỗi: " + ex.getMessage());
} finally {
    System.out.println("Kết thúc cấu trúc");
}
~~~

This is an **illustrative skeleton**; `Resource`, `openA/B/C()`, and the corresponding imports/signatures need to be defined. If A succeeds but B throws `IOException`, the flow proceeds as follows:

~~~text
Step 1: Evaluate openA()
        └── Succeeds → A becomes a managed resource

Step 2: Evaluate openB()
        └── Throws IOException → stop initializing the list

Step 3: C is not initialized; the try body does not run

Step 4: Close A via A.close()
        ├── If it succeeds: keep the IOException from B
        └── If it throws an error: add the close error to B's suppressed exceptions

Step 5: Transfer to catch (IOException), if applicable

Step 6: Execute the associated finally

Step 7: Continue or propagate the exception, depending on how catch/finally completes
~~~

**Key point:** an error from B does not cause A to be forgotten; A is closed even though the `try` body never executed. As for C, there is no creation call, so there is no C object to close. Do not guess the order from variable names or exception types: you must look at **the declaration order and the actual point of failure**.

If multiple resources have completed initialization—for example, A and B succeed while C fails—Java closes **B then A**. If the closing process itself throws an exception, the closing errors are recorded as suppressed exceptions, while the initialization error from C remains the primary exception of that exit path.

## 3. Complete Java 17+ Example: Resource B Fails to Create, Closing A Also Fails

Create the file `ResourceInitFailureDemo.java`:

~~~java
import java.io.IOException;

public class ResourceInitFailureDemo {
    static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Resource(String name, boolean failOnOpen, boolean failOnClose)
                throws IOException {
            System.out.println("Bắt đầu tạo " + name);
            if (failOnOpen) {
                throw new IOException("Tạo " + name + " thất bại");
            }
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("Đã tạo " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            if (failOnClose) {
                throw new IOException("Đóng " + name + " thất bại");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false, true);
             Resource b = new Resource("B", true, false);
             Resource c = new Resource("C", false, false)) {
            System.out.println("Trong thân try");
        } catch (IOException ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Số lỗi suppressed: " + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        } finally {
            System.out.println("Cuối cấu trúc");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ResourceInitFailureDemo.java
java ResourceInitFailureDemo
~~~

**Exact** stdout:

~~~text
Bắt đầu tạo A
Đã tạo A
Bắt đầu tạo B
Đóng A
Lỗi chính: Tạo B thất bại
Số lỗi suppressed: 1
Suppressed: Đóng A thất bại
Cuối cấu trúc
~~~

### Line-by-Line Explanation

- `new Resource("A", false, true)` prints the first two lines: A initializes successfully and is added to the managed list. The last argument `true` simulates `A.close()` throwing an `IOException`.
- `new Resource("B", true, false)` prints `Bắt đầu tạo B`, then throws `IOException("Tạo B thất bại")` **inside the constructor**, before finishing field assignments and before completing creation of resource B.
- As soon as expression B fails, Java stops processing the list: neither `Bắt đầu tạo C` nor `Trong thân try` appears.
- Java calls `A.close()`, printing `Đóng A`. Because A's `close()` also throws, A's closing error is attached as a **suppressed** exception of the primary error.
- `catch (IOException ex)` receives the error `Tạo B thất bại`, not `Đóng A thất bại`, because the `try-with-resources` mechanism gives priority to the initialization error that occurred before cleanup began.
- `ex.getSuppressed()` returns an array containing one error from `A.close()`. `finally` runs after `catch`.

In this example, `catch` completes normally, so the program does not throw an error out of `main`. If there were no matching `catch`, the error from B would propagate to the caller **after** A's closing completes. Any associated `finally` still runs along the propagation path, provided the execution environment continues normally.

This is a practical case where you need to inspect both the **primary error** and **suppressed** exceptions, because if you only log `ex.getMessage()`, you see why opening B failed but miss the fact that A also failed to close successfully.

## 4. What If the First Resource Fails to Create?

When the **very first resource expression** throws an error, no resource in the list has been successfully initialized for `try-with-resources` to call `close()` on. The `try` body does not run. A `catch` outside the automatic management can still catch the error, and `finally` still executes according to the construct's rules.

The file `FirstInitFailureDemo.java` illustrates this:

~~~java
import java.io.IOException;

public class FirstInitFailureDemo {
    static final class Resource implements AutoCloseable {
        Resource() throws IOException {
            System.out.println("Tạo tài nguyên đầu tiên");
            throw new IOException("Không khởi tạo được");
        }

        @Override
        public void close() {
            System.out.println("Không bao giờ in: close()");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Không bao giờ in: thân try");
        } catch (IOException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        } finally {
            System.out.println("Finally chạy");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FirstInitFailureDemo.java
java FirstInitFailureDemo
~~~

Exact stdout:

~~~text
Tạo tài nguyên đầu tiên
Bắt lỗi: Không khởi tạo được
Finally chạy
~~~

There is no `close()` line because the constructor **did not finish creating** the first resource, and there is no line from the `try` body. Do not mistake this for a guarantee that the constructor did not leak anything: if the constructor already opened a file or held a child resource before throwing, the incompletely initialized outer object **is not automatically closed** by `try-with-resources` at the call site. That is the responsibility of the initialization code or factory itself, discussed in section 8.

## 5. If Everything Initializes and Then the `try` Body Throws

You must distinguish an **error in a resource initializer** from an **error in the body**. When all resources have been created successfully, the body runs. If the body throws an exception, Java also closes the resources in reverse order; if a `close()` throws an error, the closing exception can become a suppressed exception of the error from the body.

File `CompletedInitDemo.java`:

~~~java
import java.io.IOException;

public class CompletedInitDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Tạo " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            if (name.equals("B")) {
                throw new IOException("Lỗi đóng B");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A");
             Resource b = new Resource("B")) {
            System.out.println("Trong thân try");
            throw new IllegalStateException("Lỗi xử lý");
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CompletedInitDemo.java
java CompletedInitDemo
~~~

Stdout:

~~~text
Tạo A
Tạo B
Trong thân try
Đóng B
Đóng A
Lỗi chính: Lỗi xử lý
Suppressed: Lỗi đóng B
~~~

Here, unlike section 3, both A and B finished being created, so **both are closed**, in the order B then A. The error from the `try` body is `IllegalStateException`; the error when closing B is recorded as suppressed. Java does not skip closing A just because closing B failed.

Do not conclude that `try-with-resources` makes all closing errors disappear. It **records** them; you need to check the stack trace or `getSuppressed()` to see whether some resources may have failed during closing. The primary exception can come from **initialization**, the **body**, or **closing**, depending on the execution path.

## 6. Multiple Resources: Matrix of Failure Paths

Given:

~~~java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    doWork(a, b, c);
}
~~~

The following table assumes that successfully initialized resources return a non-`null` reference and `close()` can be called according to the `AutoCloseable` contract.

| Failure Point | Resources Successfully Initialized | `close()` Calls Java Makes | Does Body Run? |
| --- | --- | --- | --- |
| `openA()` throws | None | None | No |
| `openB()` throws | A | A | No |
| `openC()` throws | A, B | B then A | No |
| `doWork()` throws | A, B, C | C then B then A | Yes, runs up to the throw point |
| Body completes normally | A, B, C | C then B then A | Yes |
| `C.close()` throws after normal body | A, B, C | C then B then A | Yes |

If multiple `close()` calls in a row also throw, Java still attempts to close the remaining resources. When an initialization error or body error is the primary exception, those closing errors are added to **suppressed exceptions**. If the body succeeds and resource closing itself throws, the first closing exception in closing order can become the primary error, while subsequent closing errors are suppressed.

For a resource that returns `null` when its initializer completes normally, Java **does not call `close()` with `null`**; the next expression is still evaluated and the body can still run. If an API does not allow a `null` result, you should check that condition in the factory rather than treating `null` as an initialization error automatically thrown by the runtime.

## 7. Primary Error, `cause`, and Suppressed Exceptions

Two relationships commonly appear when handling Java exceptions:

- **`getCause()`:** the cause linked to an exception via a constructor or `initCause()`; useful when an API layer wraps an error from an underlying layer.
- **`getSuppressed()`:** secondary exceptions added via `addSuppressed()` or an automatic mechanism such as `try-with-resources`; useful when a primary error path also encounters an error during cleanup.

In the example where initializing B fails and then closing A fails:

~~~text
IOException: Tạo B thất bại          <- primary error
└── Suppressed: IOException: Đóng A thất bại
~~~

This is **suppressed**, not automatically `Caused by`. If B is created by a factory that proactively wraps the root error using the `IOException(message, cause)` constructor, the initialization error of B itself can also have a cause. Both relationships can coexist.

Reading the full information:

~~~java
// Illustrative snippet inside catch (IOException ex).
System.out.println("Primary: " + ex);
Throwable cause = ex.getCause();
if (cause != null) {
    System.out.println("Cause: " + cause);
}
for (Throwable suppressed : ex.getSuppressed()) {
    System.out.println("Suppressed: " + suppressed);
}
~~~

With standard loggers, you usually pass the entire `Throwable` object rather than only `ex.getMessage()` to preserve the stack trace and suppressed branches. **Do not blindly use `ex.getSuppressed()[0]`** without checking that the array has elements; on some execution paths there are no closing errors, so the array is empty.

You should not catch and discard an initialization error just because cleaning up a previously succeeded resource happened. If the initialization error prevents the operation from continuing, preserve it or wrap it with a cause, while recording any closing errors.

## 8. Important Limitation: Resources Partially Allocated in a Constructor

`try-with-resources` **only automatically manages resource expressions that completed normally**. If a constructor or factory begins allocating internal resources and then throws before returning the object to be managed, the caller **does not receive a complete object reference** to close it.

Example of a flawed idea:

~~~java
// Code illustrating dangerous behavior, not a standalone example.
class PartialResource implements AutoCloseable {
    private java.io.InputStream input;

    PartialResource(Path path) throws IOException {
        input = Files.newInputStream(path);  // Stream already opened.
        validateHeader(input);               // If this throws IOException, the constructor fails.
    }

    @Override
    public void close() throws IOException {
        if (input != null) input.close();
    }
}
~~~

If `validateHeader(input)` throws, creating `new PartialResource(path)` **does not complete normally**. Even though the class declares `close()`, `try (PartialResource r = new PartialResource(path))` on the outside **does not automatically call `r.close()`**, because variable `r` never received a successfully initialized object. If the constructor does not clean up the stream itself, the stream can leak.

Good design ensures that the constructor/factory **cleans up any child resources it already allocated before the failure point**, or builds them inside separate `try-with-resources` scopes. Example of a fix idea:

~~~java
// Illustration placed in a class with Path, Files, InputStream, and validateHeader.
// ReturnedResource is an AutoCloseable class that takes ownership of the InputStream.
static ReturnedResource open(Path path) throws IOException {
    java.io.InputStream acquired = java.nio.file.Files.newInputStream(path);
    try {
        validateHeader(acquired);     // May throw IOException.
        return new ReturnedResource(acquired);
    } catch (IOException | RuntimeException ex) {
        try {
            acquired.close();
        } catch (IOException closeFailure) {
            ex.addSuppressed(closeFailure);
        }
        throw ex;
    }
}
~~~

This is a **non-standalone illustrative snippet** that requires defining `ReturnedResource` and `validateHeader`; it demonstrates transferring resource ownership. In the design above, only when validation and creating `ReturnedResource` succeed does the responsibility for closing the stream transfer to the returned object; if an `IOException` or `RuntimeException` occurs in the `try` block, the factory closes the stream itself and keeps any closing error as suppressed.

You must clearly define the **ownership transfer point** and avoid having both the factory and the caller responsible for closing on the success path. Depending on the API, using a dedicated factory, nested `try-with-resources` scopes, or an `AutoCloseable` object with safe initialization logic is easier to control.

**Limitation of this snippet:** it illustrates caught `IOException`/`RuntimeException` exceptions; do not treat it as an absolute recovery mechanism if the JVM/process terminates forcibly or another serious error occurs. Resource allocation and ownership must be designed intentionally.

## 9. Resource Expressions Can Be Factory Methods, Not Necessarily `new`

The resource list can be initialized with a constructor or a factory:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path);
     InputStream input = Files.newInputStream(otherPath)) {
    // Use reader and input.
}
~~~

If `Files.newBufferedReader(path)` successfully returns a reader while `Files.newInputStream(otherPath)` throws `IOException`, Java calls `reader.close()`. If creating the reader in the very first expression fails, there is no complete reader in the list to close automatically.

The `import`s and variables `path`, `otherPath` in the snippet must be provided by the enclosing method. The key point does not depend on whether the expression is written as `new SomeResource()` or `SomeFactory.open()`: **whether the initializer expression completes normally** determines whether Java starts managing that resource.

A good factory should clarify: if the factory throws an exception, does it retain any internal resources? If so, that is an ownership management bug that must be fixed in the factory, because the caller may not receive an object to close.

## 10. Pre-existing Resource Variables Since Java 9: Different from Header Errors

Since Java 9, you can declare an **already existing** resource variable in `try(...)` if that variable is `final` or *effectively final*:

~~~java
// Illustrative snippet in a method that throws IOException.
java.io.InputStream in = java.nio.file.Files.newInputStream(path);

try (in) {
    System.out.println(in.read());
}
~~~

In this example, `in` is created **before entering the `try-with-resources` construct**. If the `Files.newInputStream(path)` call throws, execution has not reached `try (in)`, so `try (in)` cannot handle a resource that was not created. If it succeeds, `try (in)` will close the resource when its scope ends.

This is a memorable difference from opening the resource **directly in the header**:

~~~java
try (java.io.InputStream in = java.nio.file.Files.newInputStream(path)) {
    System.out.println(in.read());
}
~~~

The second approach places the resource-opening expression directly inside the managed region. In both cases, an error occurring before a resource reference is successfully initialized will not cause Java to call `close()` on the unreceived resource. However, when multiple resources are in the header, Java cleans up **the earlier resources that completed initialization** if a later expression fails.

`effectively final` means the variable is never reassigned after being assigned a value, according to Java's rules. You cannot use a variable that is regularly reassigned in the `try (in)` syntax just because it has type `AutoCloseable`.

## 11. When Do `catch` and `finally` Receive Errors?

With the extended construct:

~~~java
try (Resource a = openA(); Resource b = openB()) {
    work(a, b);
} catch (IOException ex) {
    report(ex);
} finally {
    after();
}
~~~

Semantic rule: the automatic resource cleanup block runs according to `try-with-resources` rules **before the associated `catch`/`finally` branches execute**. Therefore, `catch` can receive a primary exception that already carries suppressed exceptions from the closing step.

If B fails to initialize:

~~~text
openA succeeds
openB throws IOException
A.close runs (may add suppressed)
catch (IOException ex) runs
finally runs
~~~

If there is no matching `catch`, `finally` still runs when exiting the construct, and then the exception propagates to the caller if `finally` completes normally.

Another warning: if the associated `catch` or `finally` itself **throws a new exception**, the exit path of the construct can change. For example, a manually written `finally` throwing another error can mask even B's initialization error that already had suppressed exceptions attached. Therefore, do not add an operation that can fail into `finally` without considering how to handle or preserve the primary error.

## 12. Comparison with Manual `try/finally`

Before Java 7, closing resources was often written with `finally`, such as:

~~~java
// Not recommended for AutoCloseable resources.
// Resource r = null is already declared here.
try {
    r = openResource();
    use(r);
} finally {
    if (r != null) {
        r.close();
    }
}
~~~

When managing only one resource and all operations succeed, this can work. But when there are **multiple resources** and one in the middle fails, you have to manually track which earlier resources were created successfully, close them in the right order, catch errors from `close()`, and preserve the primary error.

Manual example with two variables:

~~~java
// Illustrative skeleton code; A/B are both AutoCloseable and the methods have appropriate declarations.
A a = null;
B b = null;
try {
    a = openA();
    b = openB();
    work(a, b);
} finally {
    if (b != null) b.close();
    if (a != null) a.close();
}
~~~

At a glance you can see the risks: if `b.close()` throws, **the `a.close()` line might never execute**; if `work` or `openB` already threw, the exception from `close()` can mask the original error. Writing this correctly and preserving all information requires a lot of extra handling code.

`try-with-resources` eliminates those common manual bugs, **but it cannot fix a constructor/factory that partially allocates resources and does not clean up its own internal resources on failure**.

## 13. Checked Exceptions and the `close()` Contract

`AutoCloseable.close()` declares `throws Exception`; subclasses can narrow the exception type or throw no checked exceptions. For example, `Closeable.close()` declares `throws IOException`. Therefore, when writing `try-with-resources`, the compiler considers all of:

- checked exception types that may be thrown in the resource initialization expressions;
- checked exception types that may arise from the body;
- checked exception types that the resources' `close()` methods may propagate.

In the `ResourceInitFailureDemo` example, both the constructor and `close()` declare `throws IOException`, and `catch (IOException ex)` in `main` is valid. If you remove that `catch` and do not declare `throws IOException` on `main`, the compiler reports an error because `IOException` can escape.

Method signature example:

~~~java
// Illustrative snippet placed inside a class.
static void workWithResources() throws IOException {
    try (Resource a = openA(); Resource b = openB()) {
        doWork(a, b);
    }
}
~~~

This snippet is **not standalone**; it depends on appropriately declared types/methods. `throws IOException` declares the possibility of an error, but **does not automatically close resources** and does not replace the `try-with-resources` construct. The `try (...)` header itself performs the automatic management.

For resources whose `close()` declares `throws Exception`, the enclosing method may need to handle or declare `Exception` (or a specifically inferred checked type) if there is no matching `catch`. You should not arbitrarily declare `throws Exception` for every API; designing resources with a meaningful checked exception type makes handling easier for users.

## 14. Specific Rules When Multiple Resource-Closing Errors Occur

When an initializer or the body has already thrown a primary exception, errors from closing the successfully initialized resources are normally **suppressed** onto the primary exception. For example:

~~~text
B initialization error  <- primary exception
A.close error          <- suppressed on B's error
~~~

If **there is no initialization or body error** and multiple errors occur during closing, the exception from the resource closed first (in reverse declaration order) can become the **primary exception**, while errors from resources closed later become suppressed.

Example with declaration order A, B, C and a completed body:

~~~text
C.close error          <- primary exception during closing
B.close error          <- suppressed
A.close error          <- suppressed
~~~

This mechanism ensures that closing the remaining resources still proceeds even if one close fails, while avoiding losing secondary errors. It does not guarantee that the close operation succeeds; it only preserves the execution path and error information according to Java's rules.

Some custom `Throwable` objects can disable suppression; in that situation `getSuppressed()` may not store secondary errors as in the default case. For standardly constructed `IOException` and `RuntimeException`, suppression is enabled.

## 15. Distinguishing Three Easily Confused Cases

### 15.1. Initializer Throws an Exception

~~~java
try (Resource a = openA();
     Resource b = openB()) {
    work(a, b);
}
~~~

If `openB()` throws: A is closed, B is not considered successfully created, and the body does not run.

### 15.2. Initializer Returns `null`

~~~java
// Illustrative code with a maybeOpen() method that can return null.
try (Resource a = maybeOpen()) {
    System.out.println("Đã vào body");
}
~~~

If `maybeOpen()` **returns `null` without throwing**, the body still runs and Java simply skips closing `a` because `a == null`. If the body code accesses `a`, a `NullPointerException` can occur; that is a body error, different from an initializer error.

### 15.3. Constructor Opens a Child Resource and Then Throws

~~~java
try (CompositeResource r = new CompositeResource(path)) {
    use(r);
}
~~~

If the `CompositeResource` constructor already opened an internal stream and then throws, `r` is not assigned a complete object, so Java **does not call `r.close()`**. The constructor/factory must clean up the child resources it allocated. This is a cause of resource leaks that can happen **even when the caller uses `try-with-resources`**.

## 16. Design and Testing Checklist

When writing a resource-opening API or a `try-with-resources` block with multiple resources, check:

1. **Opening/initialization order:** which resource depends on an earlier one? What exceptions can the open operation throw?
2. **Clear ownership:** after opening succeeds, who is responsible for closing? If opening does not complete, has the factory cleaned up what was allocated?
3. **Failure points at each initializer:** test failures at the first, middle, and last resource; verify earlier resources are closed in reverse order.
4. **Body does not run when initialization is incomplete:** avoid expecting code inside the body to perform rollback steps for initializer errors.
5. **Errors in `close()`:** check both the primary error and `getSuppressed()`, especially when opening a later resource fails and closing an earlier resource also fails.
6. **`catch` handles the right types:** errors from initializers are checked/unchecked according to their actual types; handlers must have a strategy to handle or propagate them.
7. **Outer `finally`:** ensure additional cleanup logic does not mask the primary error or accidentally throw a new exception.
8. **Do not use GC/`finalize()` to fix leaks:** proactive closing and proper ownership design are the solution.
9. **Do not return a fake error object as a valid resource:** if a factory uses `null` to signal failure, the documentation must make that clear; it is better to use an API with an explicit contract for an empty result or throw an exception.
10. **Complete error reporting:** log the exception object to preserve the stack trace, cause, and suppressed exceptions; do not only log the primary error message.

If a design has multiple resources to close, put them in **the same `try-with-resources` or appropriately nested scopes** so Java manages cleanup. Do not manually re-close resources already managed by this mechanism unless there is a specific requirement and you understand the consequences.

## 17. Common Misconceptions

| Misconception | Reality | Fix |
| --- | --- | --- |
| Because B fails to create, A is not closed since the body did not run | Previously initialized resources are still closed. | Track creation order and reverse closing order. |
| B's constructor partially ran, so the caller will definitely call `B.close()` | `B` was not completely created; the caller has no resource reference to close automatically. | Have the constructor/factory clean up child resources on failure. |
| If `openB()` fails, Java still tries `openC()` | Evaluation of the resource list stops at the throw point. | Do not rely on side effects of later initializers. |
| The body has a hand-written `finally`, so it is guaranteed to run when an initializer fails | If the body has not started, statements inside the body do not run. | Put cleanup for partially allocated resources in the factory; use `try-with-resources`. |
| An `A.close()` error replaces B's initialization error | Standard `try-with-resources` records closing errors as suppressed on the primary error. | Inspect `getSuppressed()`. |
| `catch` runs before A is closed | Resources are closed before the associated `catch` runs. | Observe the log order in the example. |
| `try(r)` is enough even if `r` was opened beforehand and opening failed | When opening before `try` throws, the `try` construct has not started. | Handle the error at the opening point or open inside the resource header when appropriate. |
| Returning `null` from an initializer is equivalent to throwing an exception | Returning `null` normally does not prevent the body from running; it only skips calling `close` on `null`. | Design and verify a clear factory contract. |
| `throws IOException` automatically performs cleanup | `throws` only declares the possibility of a checked error. | Use `try-with-resources` or managed cleanup. |
| Only care about the initialization error and ignore closing errors | You can lose information about resources that failed to close. | Preserve stack trace/suppressed exceptions in logs and tests. |

## 18. Self-Check Exercises

**Question 1.** `try (A a = openA(); B b = openB(); C c = openC())`: A succeeds, B throws `IOException`. Which `close()` methods does Java call?

**Answer:** It calls `a.close()`. It does not call `b.close()` (B was not finished being created) or `c.close()` (C was never created).

**Question 2.** When B fails to open, does the `try` body run its first few statements?

**Answer:** No. The entire resource list must initialize normally before entering the `try` body.

**Question 3.** A opens successfully, B fails to open, and then closing A also fails. Which exception takes priority?

**Answer:** The error from B is the primary exception; A's closing error is added to B's suppressed exceptions under normal suppression.

**Question 4.** If C fails to open after A and B opened successfully, what is the closing order?

**Answer:** B then A.

**Question 5.** Does a `catch` attached after `try-with-resources` run before or after `close()` of A/B?

**Answer:** After closing the initialized resources that need to be closed.

**Question 6.** If A's own initializer fails immediately, does Java call `A.close()`?

**Answer:** No, because resource variable A never received a successfully created object. If A's constructor allocated child resources itself, code inside the constructor/factory must handle cleaning those up.

**Question 7.** If `openA()` returns `null` without throwing, does the body run?

**Answer:** Yes, it can run; Java does not call `close()` on a null reference.

**Question 8.** Do `try (InputStream in = Files.newInputStream(path))` and `InputStream in = Files.newInputStream(path); try (in) { ... }` open the stream at the same time?

**Answer:** No. The first opens it inside the resource header; the second opens it before entering the `try (in)` construct. Both manage a successfully opened resource, but the location where an opening error arises differs.

**Question 9.** A constructor opens an internal stream and then throws before returning the object. Can the caller rely solely on `try-with-resources` to close that stream?

**Answer:** No; the caller does not yet own a completely created object. The constructor/factory must have a cleanup policy on failure.

**Question 10.** Why should you log `getSuppressed()` as well?

**Answer:** Because resource-closing errors that occur after an initialization or body error are still important information, even though they do not replace the primary exception.

## References

- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): syntax and semantics of the full construct.
- [Java Language Specification 17 — §14.20.3.1, Basic `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.1): processing model for initialization, automatic closing, and suppressed exceptions.
- [Java Language Specification 17 — §14.20.3.2, Extended `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3.2): relationship with associated `catch` and `finally` blocks.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): `close()` contract, exception types, and usage with `try-with-resources`.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()`, `addSuppressed()`, `getCause()`.
- [Oracle Java Tutorials — The `try-with-resources` Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): explanation of resource closing and suppressed exceptions; historical tutorial examples, with fundamental rules still applicable on Java 17.

**Key takeaway:** if a **resource initializer throws an exception**, Java skips all subsequent initializers and the `try` body, but still **closes previously successfully initialized resources in reverse order**, keeps the initialization error as the primary exception, and records secondary closing errors via suppressed exceptions. Meanwhile, resources partially created inside a constructor/factory must be **safely managed by the allocating code itself**, because the caller does not have a complete object to close.
