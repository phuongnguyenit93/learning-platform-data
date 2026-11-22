# Distinguishing `finally`, `final`, and `finalize()` in Java

The three names **`finally`**, **`final`**, and **`finalize()`** look similar but have completely different meanings in Java. `finally` is part of the exception-handling construct, `final` is a keyword that restricts reassignment or inheritance/overriding, and `finalize()` is a legacy method belonging to object finalization, which has been **deprecated** and is unsuitable for reliable resource cleanup.

Key takeaway: **`finally` is tied to the control flow of `try`; `final` is tied to declarations in source code; `finalize()` is tied to an object lifecycle mechanism whose execution timing is indeterminate.** They are not interchangeable and have no "shorthand/extended" relationship.

## 1. Quick Comparison

| Criterion | `finally` | `final` | `finalize()` |
| --- | --- | --- | --- |
| Syntactic kind | Keyword introducing a block in a `try` statement | Modifier keyword | Instance method on `java.lang.Object` |
| Primary purpose | Run work when exiting `try`/`catch` | Prevent variable reassignment or prevent inheritance/overriding | Legacy finalization mechanism for an object before reclamation |
| Where it appears | After a `try` body or its corresponding `catch` blocks | Declarations of variables, parameters, fields, methods, classes (per language rules) | `protected void finalize() throws Throwable` in subclasses if overridden |
| Execution mechanism | When control leaves the `try` construct through normal or abrupt paths | Checked by the compiler for assignments and inheritance | May be invoked by the finalization system once the object is eligible, **with no guarantee of when or whether it will run** |
| Is it an exception-handling tool? | Related to `try`, but **does not catch exceptions itself** | No | Not a regular exception-handling mechanism |
| Used in modern Java? | Yes, especially for exit/cleanup work outside `AutoCloseable` management | Yes, very common | **Should not be used in new designs** |
| Example | `try { work(); } finally { cleanup(); }` | `final int limit = 10;` | `protected void finalize() throws Throwable` |

**Remember with three short phrases:** `finally` = *executes when leaving `try`*; `final` = *restricts certain changes in code*; `finalize()` = *legacy finalizer mechanism, unreliable for closing resources*.

## 2. `finally`: the final part of a `try` statement

Simple form:

~~~java
try {
    doWork();
} finally {
    cleanup();
}
~~~

With exception handling:

~~~java
try {
    doWork();
} catch (IOException ex) {
    handleIOException(ex);
} finally {
    cleanup();
}
~~~

The snippets above are **structural illustrations** and require the corresponding methods and `import` statements. In Java, `finally` is a **keyword**, not a method name; it has no parameter parentheses `()` and cannot be called as `object.finally()`.

### 2.1. When does `finally` run?

Normally, when execution leaves an associated `try` statement, `finally` runs whether the `try` block:

- completes normally without throwing an exception;
- throws an exception handled by a matching `catch`;
- throws an exception not caught in the current statement and propagating outward;
- is about to execute `return`, `break`, or `continue` that exits the statement;
- or when a selected `catch` block itself throws an exception.

Small example:

~~~java
// Place inside a method.
try {
    System.out.println("Trong try");
} finally {
    System.out.println("Trong finally");
}
System.out.println("Sau try");
~~~

Stdout:

~~~text
Trong try
Trong finally
Sau try
~~~

No exception occurs, yet `finally` still runs. Therefore, thinking of `finally` as "only for handling errors" is wrong.

### 2.2. `finally` does not handle or swallow exceptions by itself

~~~java
// Place inside a method allowed to throw an unchecked exception.
try {
    throw new IllegalStateException("thất bại");
} finally {
    System.out.println("Đã chạy finally");
}
~~~

The line `Đã chạy finally` is printed, and then `IllegalStateException` continues propagating outward if `finally` completes normally. A `finally` block is **not equivalent** to `catch (IllegalStateException)`.

If you want to handle an error, use `catch` at a layer with an appropriate handling strategy. If you want to clean up when leaving an operation, `finally` may be appropriate. The two serve different purposes.

### 2.3. `finally` is not an absolute guarantee if the JVM stops

If the JVM/process is forcibly terminated, `Runtime.halt` is called, a `System.exit` path completes shutting down the virtual machine, or the thread never leaves the `try` block, you should not expect `finally` to complete. Failures such as a crash or power loss can also prevent the work from executing.

The guarantee of `finally` is a **Java control-flow rule while execution continues**, not a durable transaction recovery mechanism. Requirements such as crash-safe data persistence need different strategies.

## 3. `final`: a modifier checked at compile time

`final` has different meanings depending on where it appears, all aimed at restricting certain modifications:

- **`final` variable/field/parameter:** cannot be reassigned once assigned a value according to definite assignment rules.
- **`final` method:** cannot be overridden (or hidden, in corresponding static method cases) in a subclass.
- **`final` class:** cannot be subclassed.
- **Single `catch` parameter declared `final`:** the caught exception reference variable cannot be reassigned. A multi-catch parameter is implicitly final by the language.

`final` **does not close resources, does not stop errors from propagating, and does not create a `try` or `catch`**.

### 3.1. `final` local variables

~~~java
final int maxRetries = 3;
System.out.println(maxRetries); // 3

// Does not compile if uncommented:
// maxRetries = 4;
~~~

Once assigned, the variable cannot be reassigned. A `final` local variable that is not initialized at its declaration can be assigned **once on every valid control-flow path** verified by the compiler:

~~~java
final int limit;
if (premiumUser) {
    limit = 100;
} else {
    limit = 20;
}
// From here on, limit is assigned and cannot be reassigned.
// premiumUser is a boolean variable in the enclosing scope.
~~~

The condition is that both branches do not cause the variable to be assigned twice on the same execution path. The compiler enforces **definite assignment** rules; it is not "having `final` means it must have a value right on the declaration line."

### 3.2. `final` on an object reference does not make the object immutable

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B");            // Valid: mutates the object's state.
System.out.println(builder);   // AB

// Does not compile:
// builder = new StringBuilder("C");
~~~

`final` protects **the variable `builder` from being reassigned to another reference**. It does not forbid calling methods that mutate the state of the referenced object.

Similarly, `final List<String> items = new ArrayList<>();` does not make `items` an immutable list; `items.add("x")` is still valid. If immutability is needed, the object's API design must also guarantee it (for example, using immutable values, defensive copies, or appropriate immutable collections).

Distinguish between:
- **`final` reference:** the reference variable cannot be reassigned.
- **Immutable object:** the object itself does not allow its observable state to change after creation.
- **Unmodifiable view:** forbids modification operations through a view, though the underlying data may still be changed elsewhere depending on the implementation.

These three concepts are not synonymous.

### 3.3. `final` fields, constructors, and initialization

~~~java
class Order {
    private final long id;

    Order(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}
~~~

A `final` instance field can be initialized at declaration or assigned during initialization/constructors according to Java rules. In the case above, every successfully constructed `Order` has `id` assigned exactly once.

With `static final`:

~~~java
class Defaults {
    static final int MAX_SIZE = 100;
    static final String APP_NAME = "Training";
}
~~~

`static final` is a common way to express class-level constants or configuration values. However, **not every `static final` field is a compile-time constant**; for example, `static final StringBuilder BUFFER = new StringBuilder();` has a final reference, but the object is still mutable. Language-level constant variables have specific criteria regarding primitive/`String` types and constant expressions.

### 3.4. `final` classes and methods

~~~java
final class ImmutableTag {
    private final String value;

    ImmutableTag(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    String value() {
        return value;
    }
}
~~~

`final class ImmutableTag` forbids writing a subclass `extends ImmutableTag`. However, declaring a `final class` **does not by itself guarantee immutability**: a final class can still contain mutable fields.

Final methods:

~~~java
class BaseService {
    public final String version() {
        return "1.0";
    }
}

class ChildService extends BaseService {
    // Cannot override method version().
}
~~~

The compiler prevents a subclass from defining an overriding `version()` method with the matching signature. Unlike `finally`, `final` executes no statements when a method finishes.

## 4. Complete Java 17+ Example Combining `final` and `finally`

Create the file `FinalAndFinallyDemo.java`:

~~~java
public class FinalAndFinallyDemo {
    static final class Receipt {
        private final int id;
        private final StringBuilder notes = new StringBuilder();

        Receipt(int id) {
            this.id = id;
        }

        final String label() {
            return "R-" + id;
        }

        void append(String text) {
            notes.append(text);
        }

        String notes() {
            return notes.toString();
        }
    }

    static int process(boolean fail) {
        try {
            System.out.println("Trong try");
            if (fail) {
                throw new IllegalStateException("xử lý lỗi");
            }
            return 7;
        } catch (IllegalStateException ex) {
            System.out.println("Trong catch: " + ex.getMessage());
            return -1;
        } finally {
            System.out.println("Trong finally");
        }
    }

    public static void main(String[] args) {
        final Receipt receipt = new Receipt(17);
        receipt.append("A");
        receipt.append("B");
        System.out.println("Receipt: " + receipt.label() + " / " + receipt.notes());
        System.out.println("Thành công: " + process(false));
        System.out.println("Thất bại: " + process(true));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinalAndFinallyDemo.java
java FinalAndFinallyDemo
~~~

Exact stdout:

~~~text
Receipt: R-17 / AB
Trong try
Trong finally
Thành công: 7
Trong try
Trong catch: xử lý lỗi
Trong finally
Thất bại: -1
~~~

**Explanation:**

1. `Receipt` is a `final` class, so no valid subclass can exist. The `id` field is `final` and assigned in the constructor, while `label()` is a `final` method and cannot be overridden.
2. The `receipt` variable in `main` is a **final reference**. You cannot reassign `receipt = new Receipt(...)` in the rest of the method, yet you can still call `receipt.append(...)`, mutating the internal `StringBuilder`. Hence the output is `AB`.
3. When `process(false)` runs, `try` prepares to return `7`. **`finally` executes before the call finishes**, so `Trong finally` appears before `Thành công: 7`.
4. When `process(true)` runs, `try` throws `IllegalStateException`, `catch` prints the message and prepares to return `-1`. The `finally` block still executes before `main` prints `Thất bại: -1`.
5. `final` on variables/classes/methods **does not determine** whether `finally` runs. The two keywords control independent aspects.

### A compile error confirming the meaning of `final`

The following `InvalidChild.java` file **intentionally fails to compile**:

~~~java
final class NonExtendable { }
class InvalidChild extends NonExtendable { }
~~~

When running `javac InvalidChild.java`, the compiler reports an error containing a message similar to:

~~~text
error: cannot inherit from final NonExtendable
~~~

The error is detected **at compile time**; it has nothing to do with runtime exceptions, `try`, `catch`, or `finally`.

## 5. `finalize()`: a legacy method related to object lifecycle

`finalize()` is an **instance method** defined on `java.lang.Object`. In the historical finalization mechanism, an object overriding `finalize()` could be called by the system once it became unreachable through normal access, before memory might be reclaimed according to that mechanism's rules.

Traditional signature:

~~~java
// Legacy API illustration; NOT recommended for use.
@Override
protected void finalize() throws Throwable {
    try {
        // Legacy finalizer logic, unreliable for releasing resources.
    } finally {
        super.finalize();
    }
}
~~~

The snippet above is an **illustrative method body placed inside a class**, not a standalone runnable program; it may trigger deprecation warnings depending on the JDK version. Do not write new code using this design.

Key points to know:

- `finalize` is a **method name**, unlike the keywords `final` and `finally`. It has `()`, can be overridden in some legacy classes, and follows method access/exception rules.
- Finalization **is not synonymous with garbage collection**: GC decides when to manage and reclaim memory; a finalizer is a legacy callback mechanism attached to certain objects when eligible.
- **There is no guarantee of when `finalize()` will run, nor any guarantee that it will run before the program exits.** `System.gc()` is only a hint/request and does not turn finalization into a deterministic schedule.
- A finalizer may never be called if the object remains referenced, the JVM exits early, or finalization is disabled. Relying on it to close files/sockets/connections easily causes resource leaks.
- Uncaught exceptions thrown in a finalizer are not handled like normal errors from application calls; under the historical finalization contract, it provides no reliable error-reporting channel to the caller thread. Thus, a finalizer is not the right place for business error handling.
- Finalizers carry performance and security risks, unpredictable behavior, and **object resurrection** (an object being made reachable again). This complicates lifecycles and race conditions.

**Status across Java versions:** `Object.finalize()` has been marked deprecated since Java 9. JEP 421 introduced **deprecating finalization for removal in JDK 18** and set the direction for removing this mechanism in the future. Since this lesson targets Java 17+, distinguish **deprecated in Java 17** from the **for-removal milestone in JDK 18**. Even on versions that still provide the API, developers should avoid writing new code that relies on finalization.

Do not call `someObject.finalize()` directly to "trigger GC." If the method is accessible and called manually, that is just a normal Java method invocation in that context; it **does not force GC to reclaim the object** and may cause cleanup to run at the wrong time or multiple times.

## 6. Why not use `finalize()` instead of `finally`?

Suppose code needs to open an OS resource such as a file, socket, or database connection. What you need is to **close the resource when you are done using it**, not wait until GC might reclaim the object.

| Issue | `finally` / `try-with-resources` | `finalize()` |
| --- | --- | --- |
| Relevant timing | When leaving the specified `try` scope | Indeterminate; depends on object lifecycle and runtime conditions |
| On the caller's active execution path? | Yes | Not part of the caller's normal control flow |
| Can cleanup order be reasoned about? | Yes, per `try` and resource-closing rules | Unreliable for managing resource order |
| Suitable for `AutoCloseable`? | Prefer `try-with-resources` | No |
| What if cleanup fails? | Can be caught/propagated; `try-with-resources` supports suppressed exceptions | No reliable error-handling path for the caller |
| Recommended for new code | Yes | No |

`finally` runs when exiting a `try` statement (under the execution rules described). Finalization is not tied to the moment a method call finishes using a resource. Despite their similar names, **they have no functional inheritance relationship and cannot substitute for each other**.

A practical point: **manually written `finally` is not always the best way to close resources either**. For `AutoCloseable`, prefer `try-with-resources` because Java closes the resource automatically and preserves suppressed exceptions when both the `try` body and `close()` throw errors.

## 7. Java 17+ Example: `try-with-resources` Instead of a Finalizer

Create the file `FinallyResourceDemo.java`:

~~~java
public class FinallyResourceDemo {
    static class Resource implements AutoCloseable {
        Resource() {
            System.out.println("Mở tài nguyên");
        }

        void work(boolean fail) {
            System.out.println("Đang xử lý");
            if (fail) {
                throw new IllegalStateException("lỗi tác vụ");
            }
        }

        @Override
        public void close() {
            System.out.println("Đóng tài nguyên");
        }
    }

    static void run(boolean fail) {
        try (Resource resource = new Resource()) {
            resource.work(fail);
        } catch (IllegalStateException ex) {
            System.out.println("Bắt lỗi: " + ex.getMessage());
        } finally {
            System.out.println("Finally của run");
        }
    }

    public static void main(String[] args) {
        run(false);
        run(true);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinallyResourceDemo.java
java FinallyResourceDemo
~~~

Exact stdout:

~~~text
Mở tài nguyên
Đang xử lý
Đóng tài nguyên
Finally của run
Mở tài nguyên
Đang xử lý
Đóng tài nguyên
Bắt lỗi: lỗi tác vụ
Finally của run
~~~

**Walkthrough:**

1. `Resource implements AutoCloseable` declares how to close the resource via `close()`. This is an **active, predictable contract** at the end of the resource's usage scope.
2. `run(false)`: `work` succeeds → `close()` is called automatically → no `catch` runs → `finally` prints the closing message.
3. `run(true)`: `work` throws `IllegalStateException` → the resource is closed **before** the statement's `catch` runs → `catch` prints the message → `finally` prints the last line.
4. The program does not need to override `finalize()`, does not need `System.gc()`, and does not depend on whether GC reclaims the object within any timeframe.

For production code, `AutoCloseable` and `try-with-resources` are the primary approach for managing closeable resources. If you want to customize cleanup behavior, put it in `close()` with a clear contract rather than in a finalizer.

## 8. Common Misconceptions About `finally`

### 8.1. `return` inside `try` does not skip `finally`

~~~java
// Illustrative snippet inside a class.
static int compute() {
    int number = 5;
    try {
        return number;
    } finally {
        number = 9;
    }
}
~~~

The method returns **5**, provided `finally` completes normally. The expression `return number` is evaluated before `finally` executes; reassigning the local variable in `finally` does not recompute the return value. If the return type is a reference to a mutable object, mutating the object itself in `finally` can be observed by the caller — distinguish that from reassigning the reference variable.

### 8.2. `return` or `throw` inside `finally` can mask errors

~~~java
// Intentional example showing an anti-pattern.
static int unsafe() {
    try {
        throw new IllegalStateException("lỗi ban đầu");
    } finally {
        return 42; // Masks the original error; DO NOT write this.
    }
}
~~~

Calling `unsafe()` returns **42** instead of throwing `IllegalStateException`. Similarly, if `finally` throws another exception, it can replace the exception currently propagating. Avoid `return` in `finally`; when cleanup itself can fail, consider `try-with-resources` or an appropriate policy that preserves the primary error.

### 8.3. `final` does not protect against exceptions

~~~java
final String text = null;
System.out.println(text.length()); // Still throws NullPointerException.
~~~

`final` only prevents reassigning `text`. It does not guarantee non-`null`, does not replace input validation, does not generate a `catch`, and does not release resources. Likewise, a `final` class can throw any valid exception produced by code inside the class.

### 8.4. `final` can be used in `catch`, but that is not `finally`

~~~java
try {
    throw new IllegalArgumentException("sai");
} catch (final IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
~~~

This is valid: the parameter variable `ex` cannot be reassigned, though it can still be used to read error details. This is `final` syntax on a parameter, **not a `finally` block**. With multi-catch, the parameter is treated as final by Java rules even if you omit the keyword.

### 8.5. `finally` does not alter `final` / override relationships

If you mark a method `final`, subclasses cannot override that method. Adding `try/finally` inside the method does not make it lose its `final` status. Conversely, no `final` modifier causes `finally` blocks inside a method to behave differently.

## 9. `final` and Multithreading: Distinguish from Cleanup

In the Java Memory Model, `final` fields have special rules that help provide **initialization safety** when an object is constructed properly and its reference is not improperly published during construction. However, **`final` does not automatically make methods thread-safe**.

For example, a `final StringBuilder buffer` field guarantees the field variable itself will not change its reference after assignment, but `StringBuilder` is still mutable and not designed for unsynchronized concurrent updates. If multiple threads call `buffer.append`, you still need a synchronization strategy or a different data structure.

This further clarifies the three names:

- `final` relates to declaration constraints and, for final fields, certain visibility rules for initialized data.
- `finally` relates to when an execution region completes.
- `finalize()` is a legacy lifecycle mechanism and is even harder to predict with multiple threads; it is not a synchronization tool.

Do not infer from the word *final* that data, resource operations, or object lifecycles are "finally safe" in every sense.

## 10. When Resource Cleanup Is Needed, What Should You Choose?

**For closeable resources:**

~~~java
// Illustrative snippet inside a method with throws IOException.
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
~~~

This is a code fragment; `path` is a `Path` in the enclosing scope and the method must handle or declare `IOException`. `try-with-resources` closes `reader` when leaving the block, even if reading fails. This construct is designed specifically for `AutoCloseable` resources.

**For final work not belonging to `AutoCloseable`:**

~~~java
// Illustrative snippet inside a method.
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

The snippet above assumes `lock` is a valid lock object and `updateSharedState()` is declared; the principle is that the lock is released in `finally` when the body completes or throws an error. With `Lock` in `java.util.concurrent.locks`, this is a common pattern. `unlock()` must be called by the thread holding the lock and only after `lock.lock()` succeeds.

**For highly specialized fallback resource management:** Java provides `Cleaner` and the reference APIs in `java.lang.ref`. These should only be used if you understand lifecycles, cleanup non-determinism, and cannot express closing responsibility directly. `Cleaner` does not replace timely `close()`, and you should not assume it offers real-time guarantees or will run before the JVM exits.

**Do not choose `finalize()` for new code.** If you encounter a finalizer in legacy systems, identify the resource it manages, move the cleanup responsibility to an appropriate active mechanism, test both success and failure paths, and gradually remove the dependency on finalization.

## 11. Syntactic Distinction: The Three Names Are Not Interchangeable

| Syntax | Meaning / Result |
| --- | --- |
| `try { run(); } finally { cleanup(); }` | Valid: `finally` is a block belonging to the `try` statement. |
| `final int n = 1;` | Valid: variable `n` cannot be reassigned. |
| `final class A { }` | Valid: class `A` cannot be subclassed. |
| `final void m() { }` | Valid in a class method declaration, depending on context: prevents overriding. |
| `protected void finalize() throws Throwable { ... }` | Historical finalizer override syntax, but deprecated/discouraged. |
| `finally int x = 1;` | Invalid: `finally` is not a variable modifier. |
| `try { run(); } final { cleanup(); }` | Invalid: `final` does not open a cleanup block. |
| `finalize { cleanup(); }` | Invalid: `finalize` is not a keyword of the `try` statement. |
| `object.finally()` | Invalid: `finally` is a keyword and cannot be used as a method identifier. |
| `finalize()` instead of `resource.close()` | Not a reliable resource-management mechanism and does not guarantee GC closes it on time. |

Snippets with `...` in the table are only illustrative syntax, **not standalone compilable Java files**. Only examples given with a file name and run command are complete programs.

## 12. Common Mistakes When Learning and Using Them

| Misconception | Why is it wrong? | What to do instead |
| --- | --- | --- |
| `final` is shorthand for `finally` | One keyword restricts assignment/inheritance; the other opens a block in `try`. | Check whether the context is a declaration or exception control flow. |
| `finally` only runs when an exception occurs | When `try` succeeds, `finally` still runs on exit from the statement. | Test both normal and error paths. |
| `finally` automatically `catch`es all errors | An unhandled error keeps propagating after `finally`, if `finally` completes normally. | Use `catch` when error handling is needed. |
| A `final` variable referencing an object means the object cannot change | `final` prevents reassigning the variable, not mutating the object. | Use immutable objects / defensive copies when needed. |
| A `final` class is guaranteed immutable | A class that cannot be subclassed can still hold mutable state. | Inspect all fields and methods. |
| A `final` method cannot throw exceptions | Restricting overriding is unrelated to throwing `Throwable`. | Distinguish a method's contract from its modifiers. |
| `finalize()` is called immediately when a variable goes out of scope | Variable scope does not determine when or whether GC/finalization runs. | Close resources actively. |
| `System.gc()` guarantees finalizers run | GC is not a reliable timer for finalization. | Do not depend on finalizers for cleanup. |
| Using a finalizer to close streams/connections | Timing is indeterminate, risking resource leaks or hard-to-control behavior. | Use `AutoCloseable` and `try-with-resources`. |
| `return` inside `finally` is harmless | It can mask a pending `return` or exception. | Avoid arbitrary `return`/`throw` in `finally`. |
| Using `finally` to close resources while ignoring errors from `close()` | A closing exception can mask the primary error. | Prefer `try-with-resources` to preserve suppressed exceptions. |
| Calling `finalize()` manually is equivalent to running GC | It is just a method call (when accessible), not forcing GC to reclaim the object. | Design an explicit `close()` API. |

## 13. Self-Check Questions

1. **Is `finally` a keyword or a method?** — A keyword opening a block in a `try` statement, typically to run work when exiting the statement.
2. **Does `final` on a reference variable prevent calling methods that mutate the object?** — No. It only prevents reassigning the variable's reference.
3. **Can you write `class Child extends FinalClass` when `FinalClass` is declared `final`?** — No, the compiler rejects it.
4. **Can a `final` method contain `try/catch/finally`?** — Yes; `final` does not restrict exception-handling constructs inside it.
5. **If `try` throws no error, does `finally` still run?** — Yes, when exiting the statement along the normal path.
6. **If `try` throws an uncaught error, does `finally` finish handling the error?** — No; it runs and then the error continues propagating if `finally` completes normally.
7. **Is `finalize()` guaranteed to be called before the process terminates?** — No; there is no such guarantee.
8. **At which milestone was `Object.finalize()` deprecated?** — Deprecated since Java 9; JEP 421 marked it deprecate-for-removal in JDK 18.
9. **To close a `BufferedReader`, should you prefer `finalize()`, `final`, or `try-with-resources`?** — `try-with-resources` and `AutoCloseable`; the other two options do not handle timely closing.
10. **If `finally` has a `return` and `try` is throwing an error, what can happen?** — `return` can replace the exception exit path, causing the original error to be masked.

## 14. Official References

- [Java Language Specification 17 — §14.20, The `try` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): execution rules for `try`, `catch`, and `finally`.
- [Java Language Specification 17 — §4.12.4, `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): `final` variables and definite assignment.
- [Java Language Specification 17 — §8.1.1.2, `final` Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): `final` classes cannot have subclasses.
- [Java Language Specification 17 — §8.4.3.3, `final` Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.3.3): `final` methods and overriding.
- [Java SE 17 API — `java.lang.Object.finalize()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()): method contract and deprecation status.
- [OpenJDK JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): context for deprecate-for-removal in JDK 18, finalization risks, and alternatives.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): active resource-closing mechanism used with `try-with-resources`.

**Conclusion:** `finally` is a block that executes when leaving `try`; `final` is a compiler-checked modifier for variables, fields, classes, and methods; `finalize()` is a method belonging to the legacy finalization mechanism and should not be used for resource cleanup. When you need resource management, choose `try-with-resources`/`close()`; when you need final logic for an execution region, use `finally`; when you need declaration constraints, use `final`.
