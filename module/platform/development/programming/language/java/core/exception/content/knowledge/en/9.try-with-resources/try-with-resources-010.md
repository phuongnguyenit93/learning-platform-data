# Try-with-resources Combined with `catch` and `finally` in Java

> **Context:** Java Core → Exception → Try-with-resources. The `try-with-resources` construct (TWR, introduced in Java 7) manages invoking `close()` on `AutoCloseable` resources. When combined with `catch` and `finally`, the most important point is that **resources are already closed by the TWR mechanism before the `catch` and `finally` blocks attached to that construct are executed**. Therefore, `catch` can handle errors originating from the **`try` body, resource initialization, or `close()`**; `finally` is suitable for completing other tasks without needing to re-close resources already delegated to TWR.

## 1. Syntax Pattern and General Order

Full form:

```java
try (ResourceType resource = acquire()) {
    use(resource);
} catch (SomeException e) {
    handle(e);
} finally {
    afterOperation();
}
```

This is **sample code**; `ResourceType` and the methods are not defined; it is not a standalone runnable file.

- `try ( ... )` declares or references resources to be automatically closed.
- The `{ ... }` body performs work that may succeed or throw an exception.
- When leaving the body (along normal Java control flow), the system invokes `close()` on resources that were successfully initialized, in **reverse order of declaration**.
- A matching `catch` handles any `Throwable` propagating from the TWR construct, if present.
- `finally` performs general completion work according to `try`/`finally` rules, after closing resources and after `catch` if present.
- Both `catch` and `finally` are **optional** for TWR: a standalone `try (resource) { ... }` is valid.

Visualizing the success and failure paths:

```text
      Initialize resource(s)
                │
                ▼
            try body
          /          \
      succeeds     throws Throwable
          \          /
                ▼
        TWR calls close()
    (reverse declaration order)
                │
                ▼
     Any Throwable escaping?
          /          \
        Yes           No
        │              │
        ▼              │
  Matching catch?      │
  (if present)         │
        \              /
                 ▼
              finally
                 │
                 ▼
      Finish or propagate error
```

**Not:** `try body → catch → close → finally`. For handlers attached directly after a TWR, Java **closes before entering the handler**. A new error from `close()` can cause a code path that seemed to succeed to branch into `catch`.

### 1.1. Minimal Example with `catch` and `finally`

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Java"))) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    System.out.println("Đọc hoặc đóng lỗi: " + e.getMessage());
} finally {
    System.out.println("Kết thúc thao tác");
}
```

This is a snippet inside a suitable Java method. `BufferedReader` has `readLine()`/`close()` methods declaring `IOException`; using `catch(IOException)` here is valid. Reading in-memory data and closing usually succeed, producing stdout:

```text
Java
Kết thúc thao tác
```

The `catch` line does not appear because no `IOException` occurred in this run. The presence of `catch` does not create an exception by itself.

## 2. Three Distinct Roles: `try(resource)`, `catch`, and `finally`

| Component | Proper Role | What It Does **Not** Do Automatically |
| --- | --- | --- |
| `try (resource)` | Establishes **temporary ownership** and automatically calls `close()` when leaving the block | Does not guarantee read/write success; does not automatically roll back transactions |
| `catch (T e)` | Selects a handler based on the thrown object's type; recovers, reports, converts, or rethrows | Does not automatically close other resources, revert state, or turn every error into success |
| `finally` | Performs general completion actions within the corresponding `try` scope | Not guaranteed to run if the JVM/process terminates abnormally; should not mask the original exception with a new `return`/`throw` |

A common reason to use TWR **together with** `catch` and `finally` is separation of concerns:

1. Resources are managed centrally, without duplicating closing code on both success and failure paths.
2. The handler focuses solely on the **business decision when the operation fails**.
3. The `finally` block performs a different finishing task, such as recording the completion status of the processing pass, restoring context, or releasing mechanisms that are not `AutoCloseable` resources.

If you only need to auto-close a resource, use a simple TWR **without adding unnecessary `catch`/`finally`**. If you do not know how to handle the exception at the current layer, let it propagate to the caller instead of catching and ignoring it.

## 3. Java 17 Program: Verifying Order on Both Success and Failure Paths

Save the file **`TwrCatchFinallyOrderDemo.java`**:

```java
public class TwrCatchFinallyOrderDemo {
    static final class Probe implements AutoCloseable {
        private final String name;

        Probe(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        void use() {
            System.out.println("Dùng " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static void run(boolean fail) {
        try (Probe p = new Probe("R")) {
            p.use();
            if (fail) {
                throw new IllegalStateException("Lỗi thân try");
            }
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally: kết thúc lượt");
        }
    }

    public static void main(String[] args) {
        run(false);
        System.out.println("---");
        run(true);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 TwrCatchFinallyOrderDemo.java
java TwrCatchFinallyOrderDemo
```

**Exact stdout:**

```text
Mở R
Dùng R
Thân try thành công
Đóng R
Finally: kết thúc lượt
---
Mở R
Dùng R
Đóng R
Catch: Lỗi thân try
Finally: kết thúc lượt
```

**Analysis:**

- `run(false)`: initialize → use → body succeeds → `close()` → skip `catch` → `finally`.
- `run(true)`: initialize → use → throw `IllegalStateException` → `close()` → `catch` → `finally`.
- The line `Đóng R` always appears **before `Catch: ...`** when the body fails.
- `finally` does not need to call `p.close()` again. It only performs independent work when the processing pass ends.
- The `Probe` resource has a `close()` method that declares no checked exceptions, so there is no need to handle `IOException`/`Exception` from this `close()` alone.

This is the clearest scenario to observe the "TWR combined with catch and finally" behavior.

## 4. Errors in `close()` Can Also Trigger `catch`

Learners sometimes assume that a `catch` attached to TWR only handles errors in the `try` **body**. That is incorrect: an exception from `close()` can be the exception escaping the entire protected section.

Example: the body completes successfully, but the resource fails to close.

Create **`TwrCloseFailureDemo.java`**:

```java
import java.io.IOException;

public class TwrCloseFailureDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close được gọi");
            throw new IOException("Không thể đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingResource r = new FailingResource()) {
            System.out.println("Công việc đã xong");
        } catch (IOException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally: ghi nhận kết thúc");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwrCloseFailureDemo.java
java TwrCloseFailureDemo
```

Stdout:

```text
Công việc đã xong
Close được gọi
Catch: Không thể đóng
Finally: ghi nhận kết thúc
```

Key points to understand:

- The `try` body does not actively throw an exception.
- Upon leaving the body, Java calls `close()` and receives `IOException`.
- `catch(IOException)` catches the exception from **closing the resource**.
- `finally` runs after the handler.
- Because `close()` declares `throws IOException`, this checked handler is valid, even though the `try` body only prints a single line.

**When is a `close()` error a serious problem?** With writers/buffered streams, closing may flush data and fail; therefore, you must not assume `Công việc đã xong` is proof that data was written successfully and durably. Let close errors affect the business outcome if the contract requires it.

## 5. Both the `try` Body and `close()` Fail: Primary and Suppressed

This is an important difference between TWR and some manual resource-closing `finally` patterns. If the body throws an exception **and** closing the resource also throws an exception, Java keeps the exception from the body as the **primary exception** and attaches the close error to `getSuppressed()`.

These two relationships are not synonymous:

- `getCause()`: "which exception caused this exception?" — typically used when code creates a wrapper and passes `cause`.
- `getSuppressed()`: "which exceptions were placed in the suppressed list?" — TWR automatically uses this mechanism for errors occurring during close after a primary exception already exists.

Create **`TwrSuppressedWithFinallyDemo.java`**:

```java
import java.io.IOException;

public class TwrSuppressedWithFinallyDemo {
    static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close thất bại");
            throw new IOException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingClose r = new FailingClose()) {
            System.out.println("Thân đang chạy");
            throw new IllegalStateException("Lỗi xử lý");
        } catch (IllegalStateException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed[0]: "
                    + e.getSuppressed()[0].getMessage());
        } catch (IOException e) {
            System.out.println("Lỗi chỉ xảy ra khi đóng: "
                    + e.getMessage());
        } finally {
            System.out.println("Finally: hoàn tất");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 TwrSuppressedWithFinallyDemo.java
java TwrSuppressedWithFinallyDemo
```

Stdout:

```text
Thân đang chạy
Close thất bại
Primary: Lỗi xử lý
Suppressed count: 1
Suppressed[0]: Lỗi đóng
Finally: hoàn tất
```

Step-by-step explanation:

1. The `try` body throws `IllegalStateException("Lỗi xử lý")`.
2. Java proceeds to close the resource; `close()` throws `IOException("Lỗi đóng")`.
3. The exception from the body is kept as **primary**, and the close error is attached as suppressed.
4. `catch(IllegalStateException)` is selected based on the **primary** exception's type, not the suppressed exception's type.
5. `catch(IOException)` does not run on this path, even though the suppressed exception is `IOException`.
6. `finally` runs after `catch`.

Having `catch(IOException)` in the program is valid because `close()` can produce an `IOException` as primary when there is no body error.

### 5.1. What if Only Closing Fails?

If you remove `throw new IllegalStateException(...)` from the body, when `close()` throws `IOException` there is no primary exception from the body. In that case, the closing `IOException` becomes the **primary** exception, so the `catch(IOException)` branch will execute. Do not write `catch(IllegalStateException)` assuming it will always handle close errors as well.

### 5.2. Why Inspect Suppressed Exceptions?

If you only print `e.getMessage()`, developers will not see the close error. With a logger that records full stack traces, suppressed exceptions are usually displayed; if building custom logging, consider recording `getSuppressed()` as well.

Do not "handle" a suppressed exception as if the primary error disappeared. It is additional diagnostic information, not an independent `catch` flow that triggers automatically.

## 6. Multiple Resources: Closing in Reverse Order and Handling Errors After All Closes

Given:

```java
try (Resource first = openFirst();
     Resource second = openSecond();
     Resource third = openThird()) {
    work();
} catch (Exception e) {
    report(e);
} finally {
    finish();
}
```

This is sample code, not a standalone program. **Initialization** order: `first → second → third`. **Closing** order: `third → second → first`. If `third.close()` throws an error, Java still proceeds to close the remaining resources per language rules; subsequent exceptions may be suppressed.

Create **`TwrMultipleResourcesDemo.java`**:

```java
import java.io.IOException;

public class TwrMultipleResourcesDemo {
    static final class Named implements AutoCloseable {
        private final String name;

        Named(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() throws IOException {
            System.out.println("Đóng " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Named a = new Named("A");
             Named b = new Named("B")) {
            System.out.println("Thân thành công");
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        } finally {
            System.out.println("Finally");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwrMultipleResourcesDemo.java
java TwrMultipleResourcesDemo
```

Stdout:

```text
Mở A
Mở B
Thân thành công
Đóng B
Đóng A
Primary: close B
Suppressed: close A
Finally
```

Because the body succeeded, the first close error (on `B`) becomes primary, and the error when closing `A` is suppressed onto it. The handler runs **after Java has attempted to close both resources**; `finally` runs after the handler.

### 6.1. When the Body Also Fails with Multiple Resources

Suppose the body throws `IllegalStateException("body")` before closing `B` and `A`, while both `close()` calls throw `IOException`. Then:

- Primary is `IllegalStateException("body")`.
- The close errors of `B` and `A` are recorded as suppressed in the order they occur.
- `catch(IllegalStateException)` receives the primary exception.
- `finally` runs after the handler completes.

Do not rely on `catch(IOException)` to catch each close error in this situation. Those errors do not become primary when a main error from the body already exists; you must read `getSuppressed()`.

### 6.2. What if Initializing the Second Resource Fails?

A resource that was already successfully initialized is still closed if opening a subsequent resource fails. For example:

```java
try (Resource a = openA();
     Resource b = openBThatThrows()) {
    work();
} catch (IOException e) {
    report(e);
} finally {
    finish();
}
```

This is an illustration, assuming `openA` returns a resource and `openBThatThrows` has `throws IOException`. If opening `a` succeeds and opening `b` throws `IOException`, Java closes `a` before entering the handler. If `a.close()` also throws, the error from opening `b` is kept as primary and the error from closing `a` is suppressed.

TWR cannot close an object whose initializer **has not returned / completed initialization**. If an initializer opens an auxiliary resource internally and throws mid-way, the code inside the initializer is responsible for not leaking that auxiliary resource.

## 7. Which Errors Does `catch` Handle? Selection by Primary Exception

After TWR, `catch` operates according to the **standard handler selection mechanism**: matching the runtime type of the thrown exception object against the type declared in `catch`.

| Error Source | Possible Primary | Suitable Handler |
| --- | --- | --- |
| Reading a file in body fails | `IOException` | `catch(IOException)` or a supertype |
| Business validation in body fails | `IllegalStateException` | `catch(IllegalStateException)` or `catch(Exception)` |
| Body succeeds, `close()` throws `IOException` | `IOException` | `catch(IOException)` |
| Body throws `IllegalStateException`, `close()` throws `IOException` | `IllegalStateException` with `IOException` suppressed | `catch(IllegalStateException)`; an `IOException` handler does not catch suppressed errors |
| Resource initialization throws `FileNotFoundException` | `FileNotFoundException` | `catch(FileNotFoundException)` or `catch(IOException)` |
| Body throws `AssertionError`, `close()` succeeds | `AssertionError` | `catch(Error)` or `catch(Throwable)` by type, **not** `catch(Exception)` |

Place specific handlers before parent handlers:

```java
try (java.io.BufferedReader reader = openReader()) {
    consume(reader);
} catch (java.io.FileNotFoundException e) {
    System.out.println("Không tìm thấy file");
} catch (java.io.IOException e) {
    System.out.println("Lỗi I/O");
} finally {
    System.out.println("Hoàn tất");
}
```

The snippet above is a sample; `openReader` and `consume` must be defined with appropriate checked exceptions. If `catch(IOException)` is placed before `catch(FileNotFoundException)`, the subsequent subtype handler is shadowed and the compiler rejects it.

**Rule of thumb:** do not use `catch(Exception)` just to avoid investigating which errors can occur. A broad handler can catch bugs like `NullPointerException`, but it cannot automatically recover corrupted data. At the boundary of an independent task, catching broadly may be reasonable if it always reports `FAILED` and isolates state; inside a data-reading method, catching specific types is usually clearer.

## 8. `finally` Runs After `catch` — But There Are Important Caveats

A `finally` block attached to TWR normally runs:

- when both the body and close succeed;
- when an exception is successfully handled by `catch`;
- when an exception has no matching handler and continues to propagate;
- when `catch` executes a `return` or throws another exception;
- when the `try` body has a valid `return`.

However, **you cannot promise it "always runs under all circumstances"**: if the JVM/process is terminated abruptly, power is lost, a native crash occurs, or control never returns to normal Java execution, there is no absolute guarantee.

### 8.1. Do Not Accidentally Swallow the Original Exception

If `finally` only logs completion or safely restores a context, a prior exception continues propagating normally after `finally` finishes.

If `finally` executes a `return` or throws a new exception, the result can **replace** the pending exception. That is why you should avoid `return` in `finally` and be careful with operations that can throw new errors there.

Bad design example:

```java
// Anti-pattern inside a method, not a standalone program.
try (Resource resource = acquire()) {
    perform(resource);
} finally {
    return; // Can mask a propagating exception.
}
```

If `perform` throws an exception, a `return` in `finally` can prevent the caller from receiving that error. TWR cannot preserve the primary exception when the author deliberately redirects control flow inside `finally`.

### 8.2. Exceptions Thrown in `finally` Are Not Caught by a Sibling `catch`

```java
try (Resource resource = acquire()) {
    System.out.println("Công việc");
} catch (Exception e) {
    System.out.println("Lỗi trong try/close");
} finally {
    throw new IllegalStateException("Lỗi finally");
}
```

This is sample code requiring a resource definition. `IllegalStateException` is thrown **inside `finally`**, not inside the TWR body protected by this `catch`, so the attached `catch(Exception)` handler does not catch that new exception. Only an outer caller can receive it.

**Recommendation:** keep `finally` small and simple, avoiding operations that might fail. For closing resources, delegate to TWR instead of repeating it in `finally`.

## 9. Java 17 Program: New Exception in `catch`, `finally` Still Runs

Create **`TwrCatchRethrowFinallyDemo.java`**:

```java
public class TwrCatchRethrowFinallyDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Close");
        }
    }

    static void doWork() {
        try (Resource r = new Resource()) {
            System.out.println("Thân try");
            throw new IllegalArgumentException("Input sai");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
            throw new IllegalStateException("Không hoàn tất", e);
        } finally {
            System.out.println("Finally: giải phóng context");
        }
    }

    public static void main(String[] args) {
        try {
            doWork();
        } catch (IllegalStateException e) {
            System.out.println("Caller: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 TwrCatchRethrowFinallyDemo.java
java TwrCatchRethrowFinallyDemo
```

Stdout:

```text
Thân try
Close
Catch: Input sai
Finally: giải phóng context
Caller: Không hoàn tất
Cause: IllegalArgumentException
```

Notes:

1. `close()` runs before the internal handler.
2. The handler creates a new **wrapper `IllegalStateException`**, keeping the original `IllegalArgumentException` as `cause`.
3. `finally` still runs as the handler prepares to throw the wrapper outward.
4. The `catch` in `main` receives the wrapper **after** the `finally` block in `doWork` finishes.
5. `getCause()` holds the original exception; do not confuse it with `getSuppressed()`, which is used for resource-closing errors.

To keep the example simple, `Resource.close()` does not throw a checked exception. For real resources, design the `close()` contract accordingly.

## 10. `return` in the `try` Body and Close Failure

TWR calls `close()` **before completing `return` to the caller**. If `close()` fails, the code may not return the prepared value.

Create **`TwrReturnCloseDemo.java`**:

```java
import java.io.IOException;

public class TwrReturnCloseDemo {
    static final class CloseFails implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Close");
            throw new IOException("Lỗi đóng");
        }
    }

    static String calculate() {
        try (CloseFails resource = new CloseFails()) {
            System.out.println("Chuẩn bị return");
            return "SUCCESS";
        } catch (IOException e) {
            System.out.println("Catch: " + e.getMessage());
            return "FALLBACK";
        } finally {
            System.out.println("Finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + calculate());
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwrReturnCloseDemo.java
java TwrReturnCloseDemo
```

Stdout:

```text
Chuẩn bị return
Close
Catch: Lỗi đóng
Finally
Kết quả: FALLBACK
```

Because `close()` throws an error, the call does not return `"SUCCESS"` as the `try` body prepared. `catch(IOException)` selects a different return path; `finally` executes before `calculate()` returns `"FALLBACK"` to the caller.

**In practice**, only use a "fallback" if there is genuinely a valid recovery path. If closing a writer fails, you should not return a fake "success" just because there is a `catch`. This example demonstrates control-flow order, not an endorsement of swallowing close errors.

## 11. Resource Variable Scope: Difference Between Declaring in `try` and External Variables

### 11.1. Java 7: Resource Declared Inside `try (...)` Parentheses

```java
try (java.io.BufferedReader reader = openReader()) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    // reader is NOT in scope here.
    System.out.println(e.getMessage());
} finally {
    // reader is NOT in scope here.
    System.out.println("Hoàn tất");
}
```

This is an illustrative snippet, assuming `openReader()` returns a `BufferedReader` with an appropriate checked exception contract. The variable `reader` declared in the resource specification is scoped to the resource specification and the TWR body; **it cannot be accessed directly in attached `catch`/`finally` blocks**.

Intentionally invalid example:

```java
try (java.io.BufferedReader reader = openReader()) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    reader.close(); // Does not compile: reader is no longer in scope.
}
```

There is no need to try calling `reader.close()` again in the handler; TWR has already handled closing (if the resource was initialized successfully).

### 11.2. Java 9+: Externally Declared and Effectively Final Variables

Since Java 9, the following syntax is valid for `final` or **effectively final** variables:

```java
java.io.BufferedReader reader = openReader();
try (reader) {
    System.out.println(reader.readLine());
} catch (java.io.IOException e) {
    System.out.println("Lỗi: " + e.getMessage());
} finally {
    System.out.println("Đã rời try");
}
```

The `reader` variable remains in the outer lexical scope, so handlers can reference it if they need to inspect properties. **However, the object has already been closed by TWR upon leaving the block**; do not assume the variable still being in scope means the resource is still open.

One drawback of opening a resource **before** `try (reader)`: if code between the open call and entering TWR throws an exception, ownership of the resource may not have been transferred to TWR yet. Whenever possible, declaring and initializing directly inside `try (...)` usually reduces risk.

**Version note:** TWR was introduced in Java 7; using an existing variable `try (reader)` has been supported since Java 9; `var` syntax in local/resource variable declarations has been available since Java 10. All of these can be used appropriately on Java 17.

## 12. `catch`, `finally`, and Checked Exceptions from `close()`

`AutoCloseable.close()` declares `throws Exception`. An implementing class can narrow the exception type, for example `Closeable.close() throws IOException`, or `close()` can declare no checked exceptions at all.

The compiler checks for checked exceptions that can arise from:

1. The resource initializer (constructor or method creating the resource).
2. Calls/statements inside the `try` body.
3. `close()` on the static resource type visible to the compiler.

Example:

```java
static void useResource() throws Exception {
    try (AutoCloseable resource = acquire()) {
        System.out.println("Sử dụng");
    } finally {
        System.out.println("Kết thúc");
    }
}
```

This is an illustrative method requiring `acquire()` to be defined. `finally` is present but **does not catch** checked exceptions; because the static type of the resource is `AutoCloseable`, `close()` can throw `Exception`, so declaring `throws Exception` may be necessary.

If you do not want a broad `throws` declaration, you can catch the type matching the API:

```java
static void run() {
    try (MyResource resource = new MyResource()) {
        System.out.println("Thao tác");
    } catch (java.io.IOException e) {
        System.out.println("I/O thất bại: " + e.getMessage());
    } finally {
        System.out.println("Kết thúc");
    }
}
```

This code is **illustrative only**: it assumes `MyResource.close() throws IOException` and the constructor declares no other checked exceptions. You cannot arbitrarily use `catch(IOException)` if the resource and body have no compatible source of that checked exception; the compiler will report "exception IOException is never thrown in body of corresponding try".

### 12.1. Is `catch(Exception)` Necessary?

Not by default. If the resource can only throw `IOException`, a specific handler is usually sufficient. If you need to handle multiple checked exception types with the **same** policy, you can use multi-catch:

```java
try (Resource resource = acquire()) {
    process(resource);
} catch (java.io.IOException | java.sql.SQLException e) {
    reportFailure(e);
} finally {
    markFinished();
}
```

This example depends on `Resource`/`acquire`/`process` actually being able to throw both types. `catch(Exception)` is broader than multi-catch because it also catches many unchecked exceptions. If you place a broad handler, make sure it does not swallow errors and pretend the work succeeded.

## 13. Nested Try-with-resources and Handler Placement

A program can have a TWR inside another TWR, with each block owning its own resource.

Example:

```java
try (OuterResource outer = openOuter()) {
    try (InnerResource inner = openInner(outer)) {
        use(inner);
    } catch (InnerException e) {
        handleInner(e);
    } finally {
        afterInner();
    }
} catch (OuterException e) {
    handleOuter(e);
} finally {
    afterOuter();
}
```

This is pseudocode following Java syntax; types and methods are not defined.

Order if both resources are opened and execution proceeds normally:

1. Inner TWR body runs.
2. `inner.close()`.
3. Inner `finally` runs (and inner `catch` if a matching error occurs).
4. Outer TWR body continues or finishes.
5. `outer.close()`.
6. Outer `catch`/`finally` run conditionally.

If the inner handler **rethrows** an exception or throws a wrapper, the exception can propagate to the outer scope **after** inner cleanup. When the outer resource closes and throws an additional exception, primary/suppressed logic applies across the relevant TWR levels. Do not assume both `finally` blocks run simultaneously or that the outer handler is chosen before the inner handler.

### 13.1. Is an Exception Thrown in `catch` Caught by a Sibling Handler?

**No.** The `catch` clauses attached to the same `try` are alternative handlers for exceptions escaping the protected TWR section. A **new** exception thrown by a handler itself will not be caught by subsequent `catch` clauses of the same construct; it propagates to an enclosing `try` or the caller.

For example, in `TwrCatchRethrowFinallyDemo`: the inner handler creates a new `IllegalStateException`, `finally` still runs, and the handler in `main` receives the wrapper.

### 13.2. `finally` Outside TWR vs. `finally` Attached to TWR

Sometimes you want to separate the resource management block from the handlers:

```java
try {
    try (Resource resource = acquire()) {
        perform(resource);
    }
} catch (Exception e) {
    report(e);
} finally {
    after();
}
```

This is an illustrative pattern. The inner TWR auto-closes the resource on exit; the outer `try`'s `catch` is evaluated after the inner TWR completes. The resulting order **is still close before outer catch/finally**, but the boundary of each construct must be read accurately to reason about the error source.

## 14. Do Not Confuse Auto-Closing with Transactions and State Recovery

TWR **only** manages resources implementing `AutoCloseable` that are declared/referenced in the resource specification. It does not automatically provide:

- atomicity across multiple data writes;
- rollback of changes to objects on the heap;
- JDBC transaction rollback after an error, unless the protocol/driver itself has specific behavior and is configured accordingly;
- guarantees that an HTTP request was not processed on the server if the client throws an exception;
- durable flushing of data to storage on power loss;
- safe automatic retries when the business outcome is uncertain.

Example in JDBC:

```java
// Illustrative code, depends on actual DataSource and SQL.
try (java.sql.Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateInventory(connection);
        insertOrder(connection);
        connection.commit();
    } catch (java.sql.SQLException e) {
        connection.rollback();
        throw e;
    }
} catch (java.sql.SQLException e) {
    reportFailure(e);
} finally {
    markRequestFinished();
}
```

Here, **`rollback()` is an explicit call**, not automatically inserted by TWR. If `rollback()` also throws an error, a diagnostic strategy is needed, especially when an original error already exists. Behavior when closing a connection, returning a connection to a pool, or transaction state when a process dies depends on the API/driver/pool; do not infer transaction safety solely from `try(connection)` syntax.

In real systems, assign responsibilities clearly: the transaction layer decides commit/rollback; TWR manages the connection lifecycle; the handler reports failure status to the caller; and `finally` handles non-transactional finishing tasks.

## 15. Common Pitfalls

| Misconception | Reality |
| --- | --- |
| "If the `try` body throws an error, `catch` runs before the resource closes." | TWR closes successfully initialized resources **before** directly attached handlers. |
| "With TWR, you never need `catch`." | TWR handles closing; if this layer needs to handle errors, still use an appropriate `catch`. |
| "With TWR, `finally` is forbidden." | `finally` is still valid and useful for other completion work. |
| "You must write `finally { resource.close(); }`." | The resource is already auto-closed by TWR; closing it twice can cause side effects or errors. |
| "A `close()` error cannot enter `catch`." | If close fails and that exception becomes primary, a matching handler will catch it. |
| "If both body and close fail, `catch` catches the close error." | Normally the body error is primary and the close error is suppressed. |
| "`getSuppressed()` is the same as `getCause()`." | They represent different relationships; suppressed describes secondary errors, cause describes the reason for a wrapper. |
| "If `catch` executes, `finally` does not run." | `finally` still executes under normal Java control flow. |
| "`finally` can safely `return` after an exception." | `return` in `finally` can mask exceptions; avoid it. |
| "An exception thrown from `finally` is caught by the preceding `catch`." | No; a sibling handler does not catch errors thrown from its own `finally`. |
| "A resource variable declared in `try(...)` can be used in `catch`." | No, the scope of a resource variable declared in the specification does not extend to external handlers. |
| "A variable used in Java 9 `try(reader)` is guaranteed to remain open afterward." | The variable remains in scope, but the resource is already closed. |
| "`catch(IOException)` is always valid in TWR." | There must be a possible checked `IOException` source from the initializer, body, or close. |
| "TWR automatically rolls back files, databases, HTTP." | TWR automatically calls `close()`; transactions and business state are separate responsibilities. |
| "It is always safe to close a resource passed in by the caller." | Ownership must be agreed upon; closing a shared resource can break external code. |
| "`catch(Throwable)` helps a program survive any JVM error." | It can catch `Error` by type, but it does not guarantee safe recovery or that the process will remain alive. |

## 16. Practice Exercises

### Exercise 1 — Predict the Order

Without running the program, predict the stdout of `TwrCatchFinallyOrderDemo` for `run(false)` and then `run(true)`. Pinpoint the exact positions of `Đóng R`, `Catch: ...`, and `Finally: ...`. Then run it to verify.

### Exercise 2 — Error Only in `close()`

Run `TwrCloseFailureDemo`. Modify `close()` so it does not throw an exception; explain why the `catch(IOException)` handler can become invalid **if no other checked `IOException` source remains**. Update the code sensibly without adding unnecessary checked handlers.

### Exercise 3 — Primary and Suppressed

Run `TwrSuppressedWithFinallyDemo`. Change the body error from `IllegalStateException` to `IOException`, while keeping `close()` throwing `IOException`. Predict the primary message, suppressed count, and which handler receives the exception. Write a test verifying `getSuppressed()[0].getMessage()`.

### Exercise 4 — Adding a Third Resource

Add `Named c = new Named("C")` to `TwrMultipleResourcesDemo`. Predict the order of `Mở A/B/C`, `Đóng C/B/A`, which resource's close error is primary, and the order of suppressed exceptions. Then verify the program with Java 17.

### Exercise 5 — `return` Replaced by a Close Error

In `TwrReturnCloseDemo`, change `CloseFails.close()` to a method that prints `Close` without throwing `IOException`. Adjust `catch` if required by the compiler. Distinguish the output when the resource closes successfully from the output when `close()` throws a checked exception.

### Exercise 6 — Exception Thrown in the Handler

In `TwrCatchRethrowFinallyDemo`, remove passing `e` to the `IllegalStateException` constructor. Observe whether `getCause()` is still `IllegalArgumentException`. Why is it important to preserve the cause when converting a low-level exception into a high-level wrapper?

### Exercise 7 — Resource Variable Scope

Write two versions: Java 7 declaring `BufferedReader r` directly in `try(...)`, and Java 9+ declaring the variable beforehand and using `try(r)`. Compare referencing `r` inside `catch`/`finally`, then explain why **even though the variable still exists, the resource has already been closed**.

### Exercise 8 — Designing with Ownership

A method receives an `InputStream` from the caller and only reads a few bytes. Should it close the input itself using TWR or leave closing responsibility to the caller? Provide two corresponding reasonable API contracts, clearly describe closing responsibility, and write tests for the chosen contract.

### Exercise 9 — Transactions Do Not Auto-Rollback

In the JDBC example, if updating inventory succeeds but inserting the order fails, which part of the code is responsible for rollback? Where is `catch(SQLException)` in the transaction block called, where does TWR close the connection, and should `finally` be used to commit? Explain why you cannot simply close the connection and assume rollback is guaranteed.

## 17. Checklist for Applying TWR + catch + finally

- [ ] Does the resource actually implement `AutoCloseable`/`Closeable`, and does the current layer have ownership to close it?
- [ ] Did I write `try(...)` declaring/reusing the resource validly for the project's Java version?
- [ ] Do I remember **close before catch and finally** for a TWR construct with directly attached handlers?
- [ ] Did I account for **reverse closing** order when there are multiple resources?
- [ ] If initializing the second resource fails, is the first resource still properly cleaned up by TWR?
- [ ] Can the handlers receive errors from the initializer, body, and `close()`?
- [ ] If both the body and close fail, do I know how to inspect `getSuppressed()` without losing the primary exception?
- [ ] Did I order `catch` clauses appropriately, specific before general?
- [ ] Does `finally` only perform other finishing work, without re-closing resources already managed by TWR?
- [ ] Did I avoid `return` and unnecessary new exceptions in `finally`?
- [ ] Do I know that a sibling `catch` does not catch new exceptions thrown from its own `catch` or `finally`?
- [ ] Am I avoiding accessing a resource variable outside its declaration scope?
- [ ] Did I resolve checked exceptions from the constructor, body, and `close()` according to the compiler contract?
- [ ] Am I avoiding confusing automatic `close()` with transaction commit/rollback or data durability?
- [ ] Do tests cover the success path, body error, close error, multiple resources, primary/suppressed, and `finally` order?

**Conclusion:** TWR ensures resources are owned and closed according to the rules, `catch` handles **exceptions escaping the TWR section after closing**, and `finally` handles independent finishing work. Remember **initialize → body → close → matching catch → finally**, observe both **primary and suppressed**, and do not let actions in `finally` mask the original error. That is the foundation for reliable Java error handling when resources must be released.
