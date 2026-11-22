# Configuring `enableSuppression` and `writableStackTrace` in Java `Throwable`

A `Throwable` object in Java carries multiple types of information to explain a failure: **message**, **cause** (`cause`), **suppressed exceptions** (`suppressed exceptions`), and a **stack trace** describing the location/call stack. For intentionally designed exception classes, Java provides two options at construction time:

- **`enableSuppression`**: whether attaching and storing additional exceptions via `addSuppressed()` is enabled.
- **`writableStackTrace`**: whether the object is constructed with a stack trace that can be recorded and updated.

The two flags are **independent**. Disabling `enableSuppression` does not automatically omit the stack trace; disabling `writableStackTrace` does not automatically clear `cause` or the message; disabling both also **does not prevent the exception from being thrown and caught**. These options are primarily useful when designing a **specialized exception class**, because they alter the diagnostic information that APIs, loggers, and `try-with-resources` can retain.

On Java 17+, the flags are configured at object creation time, via the four-parameter constructor of the form `(String message, Throwable cause, boolean enableSuppression, boolean writableStackTrace)` that `Throwable`/`Exception`/`RuntimeException` provide with **`protected`** access. Therefore, user code typically defines a **subclass of the exception** and passes the flags to `super(...)`, rather than calling the four-parameter constructor of `Throwable` directly from client code without access privileges.

## 1. The four pieces of information in a `Throwable`

Consider standard exception creation:

~~~java
// Illustrative snippet inside a method.
Throwable original = new IllegalArgumentException("đầu vào sai");
IllegalStateException wrapped =
        new IllegalStateException("không xử lý được", original);
~~~

The `wrapped` object carries pieces of information with distinct meanings:

| Information | Common API | Meaning |
| --- | --- | --- |
| Message | `getMessage()` | Description of the failure, e.g., `không xử lý được` |
| Cause | `getCause()` | The prior exception that led to the current exception, here `original` |
| Suppressed exceptions | `getSuppressed()`, `addSuppressed(Throwable)` | Additional errors that occurred during processing or cleanup, such as `close()` failing |
| Stack trace | `getStackTrace()`, `printStackTrace()`, `fillInStackTrace()` | The call frames recorded at the time the stack trace was captured |

**`cause` and `suppressed` are not synonymous.** For example, an `IOException` from a read step can be the primary exception, while a stream-closing error is attached by `try-with-resources` as suppressed. When a business layer wraps an `IOException` into another exception, the `IOException` can become the `cause` of the wrapping exception.

Under normal construction, the stack trace is populated when a `Throwable` is built, but some classes and constructors may choose not to collect or may alter that information. The two flags in this lesson do not decide whether a call throws an exception; they decide **what diagnostic information the object retains**.

## 2. Four-parameter constructor syntax

The relevant base classes provide the constructor:

~~~java
// Illustrative signature, not a standalone declaration outside a class.
protected Throwable(
        String message,
        Throwable cause,
        boolean enableSuppression,
        boolean writableStackTrace)
~~~

`Exception` and `RuntimeException` also have a four-parameter constructor with the corresponding meaning, at `protected` access. To use it safely, define a dedicated exception class:

~~~java
public class ConfigurableFailure extends RuntimeException {
    public ConfigurableFailure(
            String message,
            Throwable cause,
            boolean enableSuppression,
            boolean writableStackTrace) {
        super(message, cause, enableSuppression, writableStackTrace);
    }
}
~~~

This is a **valid standalone class** if saved in `ConfigurableFailure.java`. Because it extends `RuntimeException`, it is an **unchecked exception**; if a checked exception is needed, the class can extend `Exception` and use the corresponding constructor.

The parameters:

1. `message`: detail message, may be `null`; returned by `getMessage()`.
2. `cause`: the cause of the current exception, may be `null`; returned by `getCause()`.
3. `enableSuppression`: enables/disables the ability to record additional exceptions.
4. `writableStackTrace`: enables/disables generating and writing the stack trace on **this object itself**.

Example creating an exception with full information:

~~~java
ConfigurableFailure detailed =
        new ConfigurableFailure("lỗi chi tiết", null, true, true);
~~~

Example creating a minimal exception:

~~~java
ConfigurableFailure minimal =
        new ConfigurableFailure("lỗi tối giản", null, false, false);
~~~

The snippets above assume the `ConfigurableFailure` class has been declared. Creating `minimal` does not throw an error by itself; when you need to transition to exception handling, you use `throw minimal;`.

**Access scope note:** because the constructor on `Throwable` is `protected`, client code outside an allowed scope such as `new Throwable("x", null, false, false)` will not compile. Use an appropriate subclass and expose the subclass constructor according to your design intent.

## 3. `enableSuppression=true`: storing additional errors

When suppression is enabled, the call:

~~~java
// Illustrative snippet inside a method with a Throwable variable primary.
primary.addSuppressed(new java.io.IOException("lỗi đóng"));
~~~

can add a secondary `Throwable` to `primary`'s list. Calling:

~~~java
Throwable[] extra = primary.getSuppressed();
~~~

will return an array of the recorded errors, in the order they were added. For a normal `Throwable` with suppression enabled and no additional errors yet, `getSuppressed()` returns an empty array.

This mechanism is used by Java in `try-with-resources` when the primary operation throws an error and closing the resource also throws an error. The primary error still takes precedence as the propagated exception; the close exception is recorded as supplementary information.

Logical example:

~~~text
Reading data throws IOException("lỗi đọc")
    |
    +-- close() throws IOException("lỗi đóng")
    |
    v
Primary exception: lỗi đọc
    Suppressed: lỗi đóng
~~~

Note that Java **does not automatically attach every second exception as suppressed**. That mechanism exists in specific contexts such as `try-with-resources`, or when the developer explicitly calls `addSuppressed()`. A hand-written `try/finally` can cause an exception from `finally` to mask the earlier error if not handled properly.

## 4. `enableSuppression=false`: `addSuppressed()` does not record errors

When a `Throwable` object is constructed with `enableSuppression=false`:

- The suppressed list of **that object** is disabled.
- Calling `getSuppressed()` returns an **empty array**.
- Calling `addSuppressed(validThrowable)` does not store the new exception on that object.
- Disabling suppression **does not** erase `message`, `cause`, or automatically disable the stack trace.
- The object can still be `throw`n, `catch`ed, used as the `cause` of another object, and printed/logged as an exception.

Example:

~~~java
// Illustrative snippet inside a method, with ConfigurableFailure defined.
ConfigurableFailure failure =
        new ConfigurableFailure("không xử lý được", null, false, true);

failure.addSuppressed(new java.io.IOException("đóng tệp lỗi"));
System.out.println(failure.getSuppressed().length); // 0
~~~

The biggest concern arises with `try-with-resources`: if **the primary error thrown in the body is an object with suppression disabled**, Java may still call `addSuppressed()` to attempt to attach the resource-closing error, but this information will **not be saved on the primary object**.

Therefore, while disabling suppression may be intentional in a specialized exception class, **you should not disable it for errors used in code that needs to trace resource-closing failures**.

API rules still apply: `addSuppressed(null)` does not become a valid operation, and attempting to suppress the object itself is also misuse; do not treat the `false` flag as a way to bypass all argument-checking rules. Specific cases should be checked against the `Throwable.addSuppressed` contract.

## 5. `writableStackTrace=true`: stack trace is collected normally

With `writableStackTrace=true`, the `Throwable` constructor normally collects the stack trace at construction time. These are the frames showing the call path near the point where the exception was created, especially useful for locating the error.

~~~java
// Illustrative snippet when the object has been created.
StackTraceElement[] frames = failure.getStackTrace();
for (StackTraceElement frame : frames) {
    System.out.println(frame.getClassName() + "." + frame.getMethodName());
}
~~~

Important aspects:

- `getStackTrace()` returns a `StackTraceElement` array; the first position typically corresponds to the point where the stack trace was filled in.
- `printStackTrace()` can display the stack trace along with `cause` and `suppressed` information.
- `fillInStackTrace()` can update the stack trace location according to the current stack state, when writing the stack trace is permitted.
- `setStackTrace(StackTraceElement[])` allows setting a validly supplied stack trace per the API contract.
- Performing `throw ex;` on an existing object **does not automatically mean capturing a new stack trace** at the `throw` line.

Although the stack trace usually has at least one frame for ordinary application exceptions, Java allows special situations where the VM or a custom `Throwable` class does not provide full frames. Therefore, you should not write applications that depend on a fixed frame index without checking the array.

## 6. `writableStackTrace=false`: the object does not record a stack trace

When `writableStackTrace=false`, the four-parameter constructor does not collect a normal stack trace for the object; the stack trace is left as **`null` in internal state**. At the public API surface:

- `getStackTrace()` returns an **empty array**.
- `fillInStackTrace()` **does not update** the stack trace and returns the `Throwable` itself.
- `setStackTrace(...)` **does not change** the object's stack trace.
- `printStackTrace()` can still print the class name and message, as well as `cause` or `suppressed` branches if present, but without the normal stack trace frames of the disabled object.
- `throw`/`catch` on the object still works normally.
- If `enableSuppression=true`, you can still store suppressed exceptions with **their own stack traces**, even though the primary object has no frames.

Example:

~~~java
// Illustrative snippet inside a method, with ConfigurableFailure defined.
ConfigurableFailure failure =
        new ConfigurableFailure("không lưu vị trí", null, true, false);

failure.fillInStackTrace();
failure.setStackTrace(new StackTraceElement[] {
        new StackTraceElement("Demo", "run", "Demo.java", 42)
});
System.out.println(failure.getStackTrace().length); // 0
~~~

Do not confuse this with `setStackTrace(new StackTraceElement[0])` on an object with `writableStackTrace=true`: both situations can currently yield an empty array, but **the stack trace writing configuration is different**. An object disabled via the constructor does not return to a writable state merely by calling `setStackTrace` or `fillInStackTrace`.

Because no frames remain, identifying where the error was created or raised can become difficult. Only choose this configuration when you have a clear reason and other diagnostic information is sufficient.

## 7. Two independent flags: four combinations

| `enableSuppression` | `writableStackTrace` | `addSuppressed()` | `getStackTrace()` |
| --- | --- | --- | --- |
| `true` | `true` | Records secondary errors | Writes/reads normal stack trace |
| `true` | `false` | Still records secondary errors | No frames for the primary object |
| `false` | `true` | Does not record secondary errors | Still has normal stack trace |
| `false` | `false` | Does not record secondary errors | No stack trace for the primary object |

There is no rule that "disabling one flag forces disabling the other". If you only want to reduce the cost of recording stack traces for a specialized exception type, **you do not have to disable suppression**; disabling suppression separately should only be done when you genuinely accept losing the ability to attach secondary errors.

Both flags are **construction-time** configurations. The public API does not have a simple setter named `setEnableSuppression(boolean)` or `setWritableStackTrace(boolean)` to arbitrarily re-enable them on an already-created object.

## 8. Complete Java 17+ example: testing all four combinations

Save the file `ThrowableFlagsDemo.java`:

~~~java
import java.io.IOException;

public class ThrowableFlagsDemo {
    static class ConfigurableFailure extends RuntimeException {
        ConfigurableFailure(String message, Throwable cause,
                            boolean enableSuppression, boolean writableStackTrace) {
            super(message, cause, enableSuppression, writableStackTrace);
        }
    }

    static void show(String name, boolean suppress, boolean trace) {
        ConfigurableFailure ex = new ConfigurableFailure(name, null, suppress, trace);
        ex.addSuppressed(new IOException("đóng tài nguyên"));
        System.out.println(name + ": suppressed=" + ex.getSuppressed().length
                + ", stackAvailable=" + (ex.getStackTrace().length > 0));
    }

    public static void main(String[] args) {
        show("true/true", true, true);
        show("true/false", true, false);
        show("false/true", false, true);
        show("false/false", false, false);

        Throwable root = new IllegalArgumentException("lỗi gốc");
        ConfigurableFailure minimal = new ConfigurableFailure("thất bại", root, false, false);
        minimal.fillInStackTrace();
        minimal.setStackTrace(new StackTraceElement[] {
            new StackTraceElement("Demo", "work", "Demo.java", 5)
        });
        System.out.println("cause=" + minimal.getCause().getMessage());
        System.out.println("stack sau cập nhật=" + minimal.getStackTrace().length);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ThrowableFlagsDemo.java
java ThrowableFlagsDemo
~~~

**Verified output on Java 17+ for this program:**

~~~text
true/true: suppressed=1, stackAvailable=true
true/false: suppressed=1, stackAvailable=false
false/true: suppressed=0, stackAvailable=true
false/false: suppressed=0, stackAvailable=false
cause=lỗi gốc
stack sau cập nhật=0
~~~

Explanation:

1. `show(...)` creates each exception with its own set of flags. The `true/false` label at the start of each line is in the order **suppression/stack trace**, not the value of the cause or the thrown error.
2. With suppression enabled, a secondary `IOException` is added so `getSuppressed().length == 1`. With suppression disabled, the add call does not store it so the length is `0`.
3. With writable stack trace enabled, the `ConfigurableFailure` object created in a call chain has a stack trace available; with the flag disabled, `getStackTrace()` returns an empty array.
4. `minimal` is an object with both features disabled, yet it still carries the cause `IllegalArgumentException("lỗi gốc")`, because this configuration **does not disable the cause relationship**.
5. The `fillInStackTrace()` and `setStackTrace(...)` calls do not turn `minimal` into an object with a writable stack trace. Hence the last line is `0`.

`ex.getStackTrace().length > 0` is used to illustrate stack trace availability in normal program execution; do not generalize that every Java object in every circumstance and every JVM is guaranteed to have a positive frame count.

## 9. Practical application: resource-closing errors lost from `getSuppressed()`

This is the difference with the greatest impact on error handling. `try-with-resources` has a mechanism that prioritizes the exception from the body or initializer as the **primary error**, while attempting to preserve errors raised when closing resources as suppressed.

If the primary exception itself is created with `enableSuppression=false`, the automatic suppressed-addition process may still be invoked per Java semantics, but **no secondary error is saved on that exception**.

File `SuppressedFlagsDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedFlagsDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đóng tài nguyên");
            throw new IOException("lỗi đóng");
        }
    }

    static class TaskFailure extends Exception {
        TaskFailure(boolean suppression) {
            super("lỗi tác vụ", null, suppression, true);
        }
    }

    static void run(boolean suppression) {
        try (Resource resource = new Resource()) {
            throw new TaskFailure(suppression);
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Suppressed: " + ex.getSuppressed().length);
        }
    }

    public static void main(String[] args) {
        System.out.println("Suppression bật");
        run(true);
        System.out.println("Suppression tắt");
        run(false);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SuppressedFlagsDemo.java
java SuppressedFlagsDemo
~~~

Exact stdout:

~~~text
Suppression bật
Đóng tài nguyên
Lỗi chính: lỗi tác vụ
Suppressed: 1
Suppression tắt
Đóng tài nguyên
Lỗi chính: lỗi tác vụ
Suppressed: 0
~~~

Points to observe:

- `TaskFailure` is a **checked exception** because it extends `Exception`, but the `run` method catches it via `catch (Exception)`; there is no need to declare `throws` to propagate the error outward.
- Both runs execute `close()`, and `close()` throws `IOException` in both.
- The run with suppression enabled retains the close error in `getSuppressed()`; the run with suppression disabled keeps `TaskFailure` as the primary error but **does not retain the secondary `IOException` information** in the list.
- `writableStackTrace` is passed `true` in both runs; the different result is due to the suppression flag, not the stack trace.

This explains why **you should not disable suppression for ordinary business or I/O exceptions**. When diagnostic data from resource closing can be critical, disabling it can make incident investigation significantly harder.

## 10. `cause` is independent of both flags

The four-parameter constructor takes **`cause` separately**. Disabling suppression and writable stack trace on the outer exception **does not clear** the cause passed in:

~~~java
// Illustrative snippet, ConfigurableFailure declared.
Throwable root = new java.io.IOException("đọc cấu hình lỗi");
ConfigurableFailure wrapper =
        new ConfigurableFailure("khởi động thất bại", root, false, false);

System.out.println(wrapper.getMessage());      // khởi động thất bại
System.out.println(wrapper.getCause() == root); // true
~~~

The `root` object has its own stack trace according to how it was created. Thus, a wrapping exception with its stack trace disabled **can still contain a cause that has a stack trace**; printing the cause chain can provide the root error's trace. However, you should not assume a cause is always present or always informative enough: `getCause()` may be `null`.

Distinguish the two tasks when debugging:

- **Cause:** find *why this exception was created from a prior exception*.
- **Suppressed:** find *additional exceptions that occurred during processing/cleanup*.

An object can have a cause without suppressed exceptions, suppressed exceptions without a cause, both, or neither. The primary object's stack trace is a third, separate channel of information.

There is a constructor implementation detail to know: passing `cause` directly to the four-parameter constructor (including `null`) is how **the cause state is initialized**. You should not plan to call `initCause()` afterward on the same object just to change the cause; `initCause()` is designed for exceptions whose cause has not yet been initialized. If a cause is needed, determine it and pass it into the constructor per the design contract.

## 11. Configuration flags belong to the current `Throwable`, not propagated automatically

Suppose:

~~~java
// Illustrative snippet with ConfigurableFailure defined.
Throwable root = new IllegalArgumentException("đầu vào sai");
ConfigurableFailure wrapper =
        new ConfigurableFailure("không hoàn thành", root, false, false);
~~~

The suppression/trace flags on `wrapper` apply to **wrapper**. They **do not alter** the properties or stack trace of `root`. If `root` has suppressed exceptions, they remain attached to `root`; if the wrapper disables suppression, only the wrapper's suppressed list stops recording additions.

Similarly:

~~~java
// Illustrates the case where wrapper retains secondary errors even though wrapper's stack trace is disabled.
ConfigurableFailure wrapper =
        new ConfigurableFailure("thất bại", null, true, false);
wrapper.addSuppressed(new IllegalStateException("lỗi phụ"));
~~~

The wrapper object has no stack trace frames of its own, yet `getSuppressed()` can still return the secondary `IllegalStateException`, and the secondary exception can have its own stack trace.

The two flags **are not dynamically inherited** by every exception created later; each object has state according to its constructor and how it was created. This is an important point when reading `printStackTrace()` of a multi-level cause/suppressed chain.

## 12. How does `printStackTrace()` show the difference?

For a normally constructed `Throwable` with a writable stack trace, `printStackTrace()` typically prints information like:

~~~text
com.example.Failure: thao tác lỗi
    at com.example.Service.run(Service.java:25)
    at com.example.Main.main(Main.java:10)
    Suppressed: java.io.IOException: lỗi đóng
        at ...
Caused by: java.lang.IllegalArgumentException: đầu vào sai
    at ...
~~~

This is an **illustrative diagram, not fixed stdout**: class names, paths, line numbers, and abbreviated layouts vary by code/JDK and stack trace depth.

When `writableStackTrace=false`, the **primary exception's frame section** is typically absent; however, the message can still appear. When `enableSuppression=false`, suppressed exceptions added via `addSuppressed()` do not appear from the primary object. If there is a cause, the cause's stack trace can still be presented.

The absence of frames does not mean the exception was not thrown or that there was no error. It can be a **configuration decision**, so do not conclude "no stack trace means no call stack".

## 13. When should you consider disabling `writableStackTrace`?

Normal `Throwable` constructors collect a stack trace, and this process can have overhead. In some very specialized systems, developers may consider an exception type that only serves as an **internal control-flow signal**, thrown/caught very frequently, where the throw site is already well known and call stack information is not needed for each occurrence.

But this is a **trade-off**, not a default to apply:

1. Measure with **your own application's benchmarks/profiles**, rather than assuming every trace disablement yields significant system-level performance gains.
2. Determine whether losing the stack trace makes production investigation harder. Rare, hard-to-reproduce errors usually need stack traces.
3. Check whether exceptions are being used for a normal control-flow case; if so, **returning an appropriate value or result type** is usually clearer than using exceptions frequently.
4. If you must optimize a specialized exception, consider keeping suppression enabled when code may pass through `try-with-resources` or mechanisms that need to preserve secondary errors.
5. Evaluate logging, metrics, and observability. Some systems treat stack traces as required data for grouping incidents.

**Do not use `writableStackTrace=false` as a way to hide sensitive information.** Data security must rely on message design, logging policies, access control, and filtering. An error object lacking a trace may still contain `message`, `cause`, or other data that needs protection.

## 14. When should or shouldn't suppression be disabled?

Disabling suppression is only appropriate when an exception class is **specially designed** and the author can be certain that storing secondary errors has no value or will not be used. This is a narrow case.

Reasons to keep the default `true` in most code:

- `try-with-resources` relies on suppressed exceptions so resource-closing errors are not lost when a primary error has already occurred.
- Some manual cleanup/audit strategies also use `addSuppressed()` to retain secondary errors.
- Logging tools can print suppressed exceptions to help trace every failing step.
- If suppression is disabled, valid `addSuppressed()` calls **do not store data**, making it easy for handling code to assume errors were preserved when in fact they were not.
- Disabling suppression on one object does not mean other objects will automatically disable it; avoid mixed states that are hard to reason about without a design contract.

In general, the potential cost of losing diagnostic information usually outweighs the assumed benefit of disabling suppression broadly. For business, I/O, database, and distributed-operation exceptions, prioritize traceability and cause preservation.

## 15. Common API pitfalls and misconceptions

| Misconception / misuse | Reality and fix |
| --- | --- |
| `enableSuppression=false` means the exception cannot be `throw`n | False. The exception is still thrown/caught according to its type. Only storing secondary errors is disabled. |
| `writableStackTrace=false` also clears message and cause | False. Message/cause are independent of that object's stack trace. |
| Disabling suppression stops `try-with-resources` from calling `close()` | False. The resource is still closed; only recording the close error as suppressed on the primary error is affected. |
| `getSuppressed().length == 0` proves there was no close error | Not necessarily. Suppression may have been disabled, or there simply was no secondary error. |
| `getStackTrace().length == 0` proves no error occurred at all | False. The stack trace may have been disabled or altered; check the error type and context. |
| `fillInStackTrace()` automatically re-enables `writableStackTrace` | False. With the flag `false`, it does not update the object's stack trace. |
| `setStackTrace(...)` always gives the object stack frames | False. An object created with writable trace disabled will not accept changes. |
| Passing `cause=null` means the constructor has not set the cause | The constructor taking cause directly initializes the cause state. Do not plan to replace it with `initCause()` afterward. |
| Disabling flags on the wrapper also strips trace/suppressed from the cause | False. Flags belong to each individual `Throwable` and do not alter the cause object. |
| Calling `new Throwable(message, cause, false, false)` in any client code | The four-parameter constructor is `protected`; use it in a subclass or permitted context. |
| Setting both flags to `false` for all errors to speed things up | Loses critical data; only optimize with profiling, a clear contract, and accepted trade-offs. |
| Logging only `getMessage()` is enough | Can lose cause, suppressed, and stack trace; prefer logging the entire `Throwable` object at an appropriate boundary. |

## 16. Self-check questions

**Question 1.** Does `enableSuppression=false` make `getCause()` return `null`?

**Answer:** No. Cause is independent information; if a non-`null` cause is passed to the constructor, `getCause()` still returns that reference.

**Question 2.** Can an exception with its stack trace disabled be rethrown with `throw ex;`?

**Answer:** Yes. `writableStackTrace=false` does not change whether the exception can be thrown/caught.

**Question 3.** What does a `Throwable` created with `writableStackTrace=false` return from `getStackTrace()`?

**Answer:** An empty array, for the four-parameter constructor mechanism described.

**Question 4.** Can `setStackTrace()` be used to re-enable stack trace recording that was disabled via the constructor?

**Answer:** No. The call does not restore stack trace recording for that object.

**Question 5.** If `try-with-resources` has a body error and a close error, but the body error has suppression disabled, what happens?

**Answer:** The body error remains the primary exception; the close error will not be saved in its `getSuppressed()` under normal suppression mechanics.

**Question 6.** Do the two flags always have to take the same value?

**Answer:** No. All four combinations `true/true`, `true/false`, `false/true`, `false/false` are valid and meaningful.

**Question 7.** Does disabling the wrapper's stack trace erase the cause's stack trace?

**Answer:** No. The cause is a different object with its own state.

**Question 8.** Can the direct four-parameter signature of `Throwable` be called from any ordinary code class?

**Answer:** No; that constructor is `protected`. An exception subclass can call `super(message, cause, enableSuppression, writableStackTrace)`.

**Question 9.** If an exception type is commonly used to report I/O errors, should suppression be disabled by default?

**Answer:** No. Suppressed exceptions may be the only place recording a resource-closing error that occurred alongside the primary error.

**Question 10.** Why are the two flags not a default performance solution?

**Answer:** Because they can lose diagnostic information, while performance benefits depend on usage and require actual measurement.

## 17. Official references

- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): four-parameter constructor, `getCause()`, `addSuppressed()`, `getSuppressed()`, `getStackTrace()`, `setStackTrace()`, and `fillInStackTrace()`.
- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): `protected` constructor for custom checked exceptions with the two flags.
- [Java SE 17 API — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): `protected` constructor with suppression and writable stack trace.
- [Java Language Specification 17 — §14.20.3, `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): closing resources and how secondary exceptions are stored when a primary error occurs.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): exceptions, propagation, and handling per Java semantics.

**Conclusion:** `enableSuppression` controls **storing secondary errors**, while `writableStackTrace` controls **recording the stack trace** of the `Throwable` itself. They are configured at object creation time, do not alter throw/catch capability, and do not automatically clear the cause. Most applications should preserve full diagnostic information; only disable one or both flags for specialized exception classes when the consequences are clearly understood and accepted.
