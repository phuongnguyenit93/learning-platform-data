# Type Inference with `throws` and the Risks of `sneaky throw` in Java

Java has a **checked exception** mechanism: if a method or expression can allow a checked exception to escape, the compiler typically forces the calling code to `catch` it or declare an appropriate `throws` clause. However, when a **generic type variable** appears in a `throws` clause, the **type inference** process has special rules. From this arises a technique commonly called **sneaky throw**: allowing a checked exception to actually propagate at runtime, while the signature and checking at the call site do not show the corresponding checked exception obligation.

Key distinctions:

- **Generic `throws E` is valid and useful** when designing APIs for lambdas, method references, or callbacks that may throw their own checked exception types.
- **Lambda type inference checks checked exceptions**; it does not automatically "ignore" `IOException` or `SQLException`.
- **Sneaky throw intentionally exploits a specific type inference case** so that the caller is not required by the compiler to catch a checked exception, even though that exception may actually be thrown.
- **The runtime does not convert `IOException` into `RuntimeException`**. The thrown object retains its original type and identity; only the **compile-time checked exception model** is made to differ from the actual behavior.
- This technique carries significant risks for API contracts, type-specific `catch` blocks, integration code, and maintainability. In most applications, you should **declare checked exceptions transparently, handle them immediately, or wrap them in an unchecked exception with a clear cause**.

This lesson explains the Java 17 JLS foundation, type inference scenarios, runnable examples, examples rejected by the compiler, why the runtime still throws `IOException`, risks in Streams/lambdas, safe alternatives, and self-check questions.

## 1. Three layers to distinguish: object, signature, and inference

Consider an exception:

~~~java
java.io.IOException failure =
        new java.io.IOException("đọc dữ liệu thất bại");
~~~

There are three different questions:

1. **What is the runtime type of the object?** — `java.io.IOException`.
2. **What kind of failure does a method declare?** — For example `throws IOException`, `throws Exception`, `throws E`, or no `throws` clause.
3. **What obligation does the compiler infer at a specific generic call site?** — Depends on type variables, bounds, arguments, target type, and constraints from lambdas/method references.

These questions do not always yield the same type name. For instance, a `FileNotFoundException` object can be thrown from a method with `throws IOException` because it belongs to the `IOException` branch. That still **respects the contract**. Conversely, when an `IOException` object escapes a method without the caller seeing any checked `throws`, there may be a design flaw or a deliberate technique to obscure the contract.

In the examples of this lesson, **`throw`** is the statement that throws an object at runtime, while **`throws`** is the declaration of exception-escaping capability in a method. This difference is fundamental to understanding generic `throws E`.

## 2. Checked and unchecked exceptions in Java 17

Simplified hierarchy:

~~~text
java.lang.Throwable
├── java.lang.Error                       unchecked
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException               checked
    │   └── FileNotFoundException          checked
    ├── java.sql.SQLException             checked
    └── java.lang.RuntimeException        unchecked
        ├── IllegalStateException
        └── IllegalArgumentException
~~~

**Checked exceptions** are types under `Throwable` that do **not** fall under `RuntimeException` or `Error`. For checked exceptions that can escape, code must generally follow the **catch-or-declare** rule.

Simple example:

~~~java
import java.io.IOException;

// Illustrative snippet inside a class.
static void read() throws IOException {
    throw new IOException("không đọc được");
}

static void caller() {
    // read();  // Does not compile without catching or declaring IOException.
}
~~~

A valid fix:

~~~java
// Illustrative snippet inside the class containing read() above.
static void caller() {
    try {
        read();
    } catch (IOException ex) {
        System.out.println("Đã bắt lỗi I/O");
    }
}
~~~

Alternatively, `caller()` can declare `throws IOException` to pass the obligation to the next caller.

**Unchecked exceptions** can escape without the compiler forcing the caller to catch/declare them:

~~~java
static void failFast() {
    throw new IllegalStateException("trạng thái không hợp lệ");
}
~~~

This does not mean unchecked exceptions are "safer" or "not real exceptions." They only differ in **compile-time checking rules**.

## 3. Generic methods with `throws E`

A generic method can declare an exception type using a type parameter:

~~~java
// Illustrative snippet inside a class.
static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
    action.run();
}
~~~

Where `ThrowingAction<E>` is a functional interface:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}
~~~

The type `E` is used in both the **callback signature** and the **`throws` clause of the method receiving the callback**. When called, the compiler has information from the lambda or the type of the callback variable to determine the checked exception that must be handled.

Example:

~~~java
// Illustrative snippet using the two declarations above.
perform(() -> {
    throw new java.io.IOException("lỗi I/O từ lambda");
});
~~~

If the call is inside a method that does not declare `throws IOException` and has no matching `catch`, it is **not allowed to naturally "bypass" this error just because `E` is generic**. The constraint arising from the lambda can force `E` to cover `IOException`, so the caller must handle it.

This is the healthy purpose of generic `throws E`: **propagating the exact checked exception contract from the callback to the caller**, rather than forcing every callback to declare a broad `throws Exception` or converting all errors to unchecked.

## 4. `throws` inference in the JLS: the subtle point

JLS §18 specifies type inference for generic methods and lambda/method reference expressions. Some details can be explained without memorizing the entire algorithm:

- When a type variable `E` appears in a `throws E` clause, the inference system records an informational bound often described as **`throws α`** for the corresponding inference variable.
- If no concrete constraint forces `E` to cover a checked exception, and the upper bounds allow it, inference prefers an **unchecked exception type**.
- In the common case where the upper bound is `Throwable` or `Exception` and no lower bound imposes a checked type, JLS §18.4 has a rule that selects **`RuntimeException`** as the inferred type.
- Conversely, an **actual checked exception appearing in the lambda body** can generate an additional constraint under JLS §18.2.5, preventing `E` from being freely chosen in that way.
- An explicit **type witness** specified by the programmer, such as `SomeClass.<IOException>method(...)`, can also force the caller to obey checked `throws IOException`.

This rule does not mean the compiler "reads the runtime type" by running the program. The compiler solves type constraints from **signatures and source expressions**, without observing failures at runtime.

In particular, `throws α` in JLS explanations is an **internal notation of the inference process**, not syntax where you directly write `throws α` in normal Java code. Programmers write type variables like `E`, while the symbol α is used to describe the algorithm.

## 5. Mechanism of a `sneaky throw` helper

A short variant:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void passThrough(Throwable failure) throws E {
    throw (E) failure;
}
~~~

Syntactically, this method declares that it can throw `E`, a subtype of `Throwable`. Inside, the cast `(E) failure` is an **unchecked cast** because generic information is removed by type erasure, so the `@SuppressWarnings("unchecked")` annotation only suppresses the related warning. The annotation does **not** bypass compiler checking at the caller.

The crux lies in the **signature**:

- The parameter accepted has type `Throwable`, **not `E`**.
- Therefore, passing `new IOException(...)` into the `Throwable` parameter **does not directly impose the constraint `E = IOException`** at the call site.
- Without other constraints, the type variable `E` in `throws E` can be inferred by the compiler as `RuntimeException` according to the rule stated above.
- The caller is not forced to `catch IOException`, even though the `Throwable` object passed in may actually be an `IOException`.

Example:

~~~java
static void hiddenFromSignature() {
    passThrough(new java.io.IOException("I/O ẩn"));
}
~~~

**The statement above compiles**, even though `hiddenFromSignature()` does not declare `throws IOException` and does not catch it. At runtime, `IOException` is still thrown from `passThrough`. This is what gives rise to the name **sneaky throw**.

You should not claim that "Java always infers every `E extends Throwable` as `RuntimeException`." Inference also depends on other constraints from parameters, target types, lambdas, or explicit type arguments. **Sneaky throw exploits one specific scenario** where those constraints do not force `E` to be a checked exception.

## 6. Complete Java 17+ program: an `IOException` actually escapes

Create the file `SneakyThrowDemo.java`:

~~~java
import java.io.IOException;

public class SneakyThrowDemo {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void passThrough(Throwable failure) throws E {
        throw (E) failure;
    }

    static void hiddenFromSignature() {
        passThrough(new IOException("I/O ẩn"));
    }

    static void explicitContract() throws IOException {
        SneakyThrowDemo.<IOException>passThrough(new IOException("I/O khai báo"));
    }

    public static void main(String[] args) {
        try {
            hiddenFromSignature();
        } catch (Throwable ex) {
            System.out.println("Thực tế: " + ex.getClass().getSimpleName()
                    + " - " + ex.getMessage());
        }

        try {
            explicitContract();
        } catch (IOException ex) {
            System.out.println("Rõ ràng: " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SneakyThrowDemo.java
java SneakyThrowDemo
~~~

Exact stdout:

~~~text
Thực tế: IOException - I/O ẩn
Rõ ràng: I/O khai báo
~~~

Analysis:

1. `hiddenFromSignature()` has no `throws`. Calling `passThrough(new IOException(...))` allows the compiler to infer an unchecked choice for `E`, so the call is valid regarding checked exceptions.
2. The actual object thrown is still `IOException`; `ex.getClass().getSimpleName()` prints `IOException`. No new `RuntimeException` class is created.
3. `catch (Throwable ex)` is broad enough to catch the object that escaped the method regardless of whether it is checked or unchecked. This is a choice **strictly for illustration**; normal applications should not catch `Throwable` broadly and hide `Error`s as well.
4. `explicitContract()` uses the **type witness** `<IOException>`, causing `passThrough` to be invoked as a method with `throws IOException`. Therefore, `explicitContract()` itself must declare `throws IOException` or handle the error.
5. `main()` has a valid `catch (IOException)` around the `explicitContract()` call because the **static signature** of this method declares `throws IOException`.

The difference between the two parts of the program is not that the runtime knows which exception type will appear. The difference lies in the **contract the compiler sees** when checking each call.

## 7. Why is there no `ClassCastException` at `(E) failure`?

A natural question: if the compiler infers `E = RuntimeException`, why doesn't `(E) failure` inside the helper throw `ClassCastException` when the object is an `IOException`?

Explanation: Java generics use **type erasure**. For a type variable `E extends Throwable`, the cast expression in generic code does not equate to the JVM always checking the object against the concrete type `RuntimeException` at that throw site. In this helper, the base runtime bound of `E` is `Throwable`; the `IOException` object satisfies that bound.

The `throw` instruction in the JVM throws an object of type `Throwable`; there is no runtime mechanism that automatically enforces matching the exception type against the **`throws` list inferred by the compiler at the call site**. Generic signatures and `throws` clauses largely serve **compile-time language checking**, not a runtime exception filter.

**Do not overgeneralize:** there are other unchecked casts in Java that will generate runtime checks and can throw `ClassCastException`, especially when a value is cast to a more specific, narrower concrete type. The conclusion here applies to the **helper pattern shown**, not a guarantee that every generic cast is safe.

Additionally, the helper only throws the same object; if there are other exception-wrapping layers in the program, they may create their own cause or stack trace, but that is the work of those layers rather than happening automatically due to type inference.

## 8. Compile time and runtime can "disagree" about exceptions

Compare the following two statements:

| Question | Compiler at the `hiddenFromSignature()` call | Runtime if the helper throws `IOException` |
| --- | --- | --- |
| Is there a static `throws IOException` to handle? | No | Does not use the signature to block the thrown object |
| Can it be caught with `catch (RuntimeException)` if the object is `IOException`? | A `RuntimeException` catch can be valid in code | **No**. `IOException` is not a subtype of `RuntimeException` |
| Can it be caught with `catch (Exception)` or `catch (Throwable)`? | Broad enough branches can be valid | Yes, because `IOException` belongs to those branches |
| Actual type of the object? | Not inferred solely from the choice of `E` | `IOException` |
| Is the caller reminded by the compiler to `catch IOException`? | No in the verified sneaky path | The exception can still escape if no matching runtime handler exists |

A `catch (RuntimeException ex)` is allowed in code without checked `throws`, but **it does not "neutralize" the `IOException`** that was sneakily thrown. If the program only catches `RuntimeException`, the `IOException` object can continue propagating to the outermost handler.

Similarly, Java's `catch` dispatch mechanism is based on the **runtime type of the object**, not on the type `E` that the compiler inferred for an earlier generic call.

## 9. Unexpected compile error: `catch (IOException)` is not considered reachable

The following `CatchCheckedBad.java` file is written **intentionally not to compile**:

~~~java
import java.io.IOException;

class CatchCheckedBad {
    @SuppressWarnings("unchecked")
    static <E extends Throwable> void pass(Throwable t) throws E {
        throw (E) t;
    }

    static void run() {
        try {
            pass(new IOException("I/O"));
        } catch (IOException ex) {
            System.out.println("Đã bắt IOException");
        }
    }
}
~~~

Compile:

~~~bash
javac -encoding UTF-8 CatchCheckedBad.java
~~~

Key message from Java 17 `javac`:

~~~text
error: exception IOException is never thrown in body of corresponding try statement
~~~

**Why?** At the generic call `pass(new IOException(...))`, the compiler can choose an unchecked `E` and does not consider the `try` body to have a declared checked `IOException`. Therefore, `catch (IOException)` **based solely on that call** is deemed invalid at compile time, even though at runtime an `IOException` object can actually be thrown.

This is one of the clearest risks: **a dishonest contract prevents the caller from writing a specialized checked handler naturally**.

The proper fix, if you are allowed to change the API, is to **declare `throws IOException` explicitly**, or use a controlled type witness in a method that already declares `throws IOException`, like `explicitContract()` in section 6. If you are forced to interact with legacy code that uses sneaky throw, you must clearly understand where the exception escapes and decide on a testable handling boundary; do not use `catch (Throwable)` indiscriminately to hide all system errors.

## 10. Lambdas do not automatically ignore checked exceptions

A lambda only has meaning when bound to a **functional interface target type**. `Runnable.run()` does not declare any checked exceptions:

~~~java
@FunctionalInterface
interface Runnable {
    void run();
}
~~~

This is an abbreviated signature of `java.lang.Runnable`, not advice to redefine `Runnable` in application code. Therefore:

~~~java
import java.io.IOException;

// INTENTIONALLY WRONG:
class RunnableCheckedBad {
    Runnable x = () -> {
        throw new IOException("checked");
    };
}
~~~

does not compile. `javac` reports something like:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

**Reason:** the lambda body can throw checked `IOException`, but the single abstract method `Runnable.run()` does not allow that exception to escape.

You cannot fix this by adding `throws IOException` to the enclosing method containing the lambda assignment and expecting the `Runnable` target type to change. The lambda body must conform to the signature of the **functional interface** it implements. An enclosing method with `throws IOException` only declares exceptions directly for that method's body, not by altering `Runnable.run()`.

There are three appropriate design approaches: use a functional interface with a matching `throws` clause, handle the error directly inside the lambda, or wrap the error into an unchecked exception with its cause preserved.

## 11. Generic functional interfaces help propagate checked exceptions properly

Definition:

~~~java
@FunctionalInterface
interface ThrowingAction<E extends Exception> {
    void run() throws E;
}
~~~

And the generic method:

~~~java
static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
    action.run();
}
~~~

If the lambda body throws `IOException`, inference must reflect that checked type:

~~~java
// Illustrated inside a method that already declares throws IOException or has a catch.
perform(() -> {
    throw new java.io.IOException("lambda I/O");
});
~~~

If a caller simply tries to write:

~~~java
static void ordinaryCaller() {
    perform(() -> {
        throw new java.io.IOException("lambda I/O");
    });
}
~~~

then this snippet **does not compile** because the checked exception is unhandled. This is desirable: the caller sees the responsibility for errors coming from the callback.

Cases with no checked exception in the lambda, such as a lambda that only logs or throws `IllegalStateException`, can infer an appropriate type without requiring `throws IOException`.

## 12. Complete Java 17+ program: generic lambdas honoring the contract

Save as `GenericLambdaDemo.java`:

~~~java
import java.io.IOException;

public class GenericLambdaDemo {
    @FunctionalInterface
    interface ThrowingAction<E extends Exception> {
        void run() throws E;
    }

    static <E extends Exception> void perform(ThrowingAction<E> action) throws E {
        action.run();
    }

    static void checkedCase() throws IOException {
        perform(() -> {
            throw new IOException("lambda I/O");
        });
    }

    static void uncheckedCase() {
        perform(() -> {
            throw new IllegalStateException("lambda trạng thái");
        });
    }

    static void noThrowCase() {
        perform(() -> System.out.println("Lambda bình thường"));
    }

    public static void main(String[] args) {
        try {
            checkedCase();
        } catch (IOException ex) {
            System.out.println("Đã bắt: " + ex.getMessage());
        }

        try {
            uncheckedCase();
        } catch (IllegalStateException ex) {
            System.out.println("Unchecked: " + ex.getMessage());
        }

        noThrowCase();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericLambdaDemo.java
java GenericLambdaDemo
~~~

Exact stdout:

~~~text
Đã bắt: lambda I/O
Unchecked: lambda trạng thái
Lambda bình thường
~~~

Analysis:

1. `checkedCase()` contains a lambda that actually throws `IOException`; the compiler requires this method to declare or catch the checked exception. Here the signature has `throws IOException`.
2. `main()` catches `IOException` because `checkedCase()`'s signature declares that type.
3. `uncheckedCase()` has a lambda that throws `IllegalStateException`; this is unchecked, so no checked `throws` declaration is needed.
4. `noThrowCase()` uses a lambda that completes normally. No checked exception needs to be declared.
5. The generic method `perform` **does not make the error disappear**; it passes the contract type `E` from the callback up to the caller. This is a transparent generic `throws` model, in contrast to sneaky throw actively hiding the checked type.

The same principle applies to **method references** with matching `throws`, for example a method reference to a checked data-reading method used with a functional interface declaring `throws IOException`. The signature of the target type remains the key condition, not just lambda or `::` syntax.

## 13. Inference without checked errors vs. intentionally hiding errors

Two calls may look similar:

~~~java
// No checked exception produced in the lambda:
perform(() -> System.out.println("x"));
~~~

~~~java
// Checked IOException in the lambda:
perform(() -> { throw new java.io.IOException("lỗi"); });
~~~

In the first call, there is no constraint requiring `IOException` to be covered, so the compiler can infer a suitable unchecked exception for `E`. In the second call, the lambda body contributes a checked exception constraint; the compiler cannot arbitrarily discard it and still treat the program as valid.

**Sneaky throw differs in that the checked object is passed into a `Throwable` parameter, rather than through a lambda body checked against `throws E`.** As a result, the constraint that would make `E` accurately represent the object's checked type is missing.

Evaluate an API by the path of type information propagation:

~~~text
Safe generic callback:
lambda throws IOException
        ↓ (checked exception constraint)
ThrowingAction<E>.run() throws E
        ↓
perform(...) throws E
        ↓
caller must catch/declare IOException

Sneaky helper:
IOException object → Throwable parameter
        ↓ (does not force E = IOException)
passThrough(Throwable) throws E
        ↓ (can infer E = RuntimeException)
caller does not have to catch/declare IOException
        ↓
runtime still throws the IOException object
~~~

The diagram describes the **compile-time contract**, not a runtime wrapper chain; with the sneaky helper, no `RuntimeException` object is automatically created along this path.

## 14. Risks of sneaky throw for public API contracts

The biggest issue is not whether the helper is short or long, but that **API consumers cannot understand it correctly from the signature**.

Example:

~~~java
public void process() {
    passThrough(new java.io.IOException("không kết nối được"));
}
~~~

A reader sees `process()` without `throws IOException`. If the implementation or library does not document the sneaky exception behavior, callers may:

- Catch only `RuntimeException` assuming all undeclared errors are unchecked.
- Fail to implement cleanup or rollback appropriate for I/O errors.
- Not know which boundary to use to catch a runtime `IOException`.
- Log without proper categorization, making diagnosis harder.
- Write tests expecting `RuntimeException` and receive `IOException` instead.

More importantly, **refactoring** can change the compiler's outcome if type inference constraints at the call site change. A call with an explicit type argument `<IOException>` is not the same as a call left to compiler inference; changing a generic signature can also alter `throws` obligations.

**Do not treat unchecked inference as permission regarding the contract.** Java has special inference rules, but API designers are still responsible for providing understandable and testable behavior.

## 15. Dangers of using sneaky throw with callbacks, Streams, and external libraries

Standard Java APIs such as `Runnable`, `Supplier<T>`, `Function<T,R>`, `Consumer<T>`, and `Predicate<T>` **do not declare checked exceptions** in their primary abstract methods. If a lambda inside wants to call an API that throws `IOException`, the compiler rejects the direct checked path:

~~~java
// INTENTIONALLY WRONG if readFromDisk() throws IOException.
java.util.function.Supplier<String> supplier = () -> readFromDisk();
~~~

Some developers turn to a sneaky helper to smuggle the checked exception through the lambda without changing types. That may run, but it causes the callback to **violate the semantic expectations** of the API's callers.

Examples of risks in a Stream pipeline:

- A `map(...)` expression may be deferred until the terminal operation; the actual exception arises when the pipeline is executed.
- A multi-step pipeline can make the error location hard to trace.
- `catch (IOException)` around the terminal operation may **not be accepted by the compiler** if it only relies on the Stream API signature that does not declare checked `IOException`.
- When using asynchronous libraries or frameworks, the exception may also be wrapped, passed through a future/result object, or logged elsewhere according to the library's own contract.
- Downstream code may misclassify the error if it relies on the assumption that "callbacks cannot throw checked exceptions."

There is no rule that every Stream API will automatically **convert `IOException` to unchecked**. How an exception propagates in a Stream depends on the thrown object and the enclosing layers; sneaky throw allows a checked exception to escape through a site whose signature does not reflect it.

In production applications, **explicitly wrapping `IOException` into `UncheckedIOException`** is a clearer choice if an API forces you to use a `Function` that does not declare checked exceptions.

## 16. First alternative: `UncheckedIOException` with preserved cause

If a lambda using standard I/O APIs needs to fit `Function<T,R>`, one option is to catch `IOException` and convert it into `UncheckedIOException`:

~~~java
// Illustrative code inside a lambda with variable name.
try {
    return readName(name);
} catch (java.io.IOException ex) {
    throw new java.io.UncheckedIOException("Không đọc được " + name, ex);
}
~~~

`UncheckedIOException` is an unchecked class provided by Java **specifically for wrapped I/O errors**, whose `getCause()` returns the original `IOException`. This makes it clear to callers that there is an **unchecked wrapper** to be handled according to the API contract, rather than sneaking an `IOException` through an undeclared signature.

**Do not use `UncheckedIOException` for all checked exceptions**. Its constructor requires an `IOException` as its cause; for `SQLException` or business exceptions, choose a semantically appropriate unchecked wrapper or design a different result/callback interface.

## 17. Complete Java 17+ example: explicit adapter for Stream

File `CheckedLambdaAdapterDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.function.Function;

public class CheckedLambdaAdapterDemo {
    static String readName(String name) throws IOException {
        if ("missing".equals(name)) {
            throw new IOException("không đọc được " + name);
        }
        return name.toUpperCase();
    }

    static Function<String, String> reader() {
        return name -> {
            try {
                return readName(name);
            } catch (IOException ex) {
                throw new UncheckedIOException("Lỗi đọc: " + name, ex);
            }
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(List.of("ok", "missing").stream()
                    .map(reader()).toList());
        } catch (UncheckedIOException ex) {
            System.out.println("Bao ngoài: " + ex.getMessage());
            System.out.println("Nguyên nhân: " + ex.getCause().getMessage());
        }
    }
}
~~~

Java 17 commands:

~~~bash
javac -encoding UTF-8 CheckedLambdaAdapterDemo.java
java CheckedLambdaAdapterDemo
~~~

Exact stdout:

~~~text
Bao ngoài: Lỗi đọc: missing
Nguyên nhân: không đọc được missing
~~~

Explanation:

1. `reader()` returns `Function<String,String>`, which is the type `Stream.map()` uses.
2. `readName("ok")` succeeds and returns `"OK"`. `readName("missing")` throws `IOException`.
3. The lambda catches `IOException` and **creates an explicit `UncheckedIOException`**, passing the cause through the constructor.
4. When the terminal operation `toList()` executes the pipeline, the unchecked wrapper escapes; no list is printed because the `map` operation did not complete.
5. `catch (UncheckedIOException)` in `main` is valid and receives the exact wrapper type; `getCause()` reveals the original I/O error.
6. The example intentionally simulates an error via a condition on the name, independent of actual files. The execution of `List.of(...).stream()` in the example is sequential, keeping the result deterministic.

If the calling code uses a `Stream` of real data, you still need to decide on **fail-fast, continuing partially, storing errors per element, or returning an aggregated result**. `UncheckedIOException` is more transparent than sneaky throw, but it does not decide business policy on its own.

## 18. Second alternative: `ThrowingFunction` or `ThrowingSupplier`

If you control the API, you can design a functional interface with an exception type parameter:

~~~java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}
~~~

And a processing method:

~~~java
static <T, E extends Exception> T supply(
        ThrowingSupplier<T, E> supplier) throws E {
    return supplier.get();
}
~~~

When passing a lambda that throws `IOException`:

~~~java
// Illustrative snippet inside a method with throws IOException.
String value = supply(() -> readName("missing"));
~~~

`readName` is a method with `throws IOException`. When inferred against the functional interface above, `IOException` does not "disappear": the caller of `supply` must handle or declare it according to the actual contract.

**Drawback:** a custom `ThrowingSupplier` cannot always directly replace `java.util.function.Supplier` in standard APIs. You need an adapter with a clear policy at the conversion boundary, or use APIs designed for checked callbacks.

**Advantage:** both the callback and the caller see the error path through compile-time checking. This is an especially useful option for internal libraries designed naturally around I/O, databases, or operations with checked exceptions.

## 19. Third alternative: handle locally or return a structured result

Not every failure of a processing step needs to be thrown across multiple layers:

~~~java
// Illustrative example of a method that can return a result type.
record ReadResult(String value, String error) {
    static ReadResult success(String value) {
        return new ReadResult(value, null);
    }

    static ReadResult failure(String reason) {
        return new ReadResult(null, reason);
    }
}
~~~

This is a valid Java 17 record; the example code does not express the full invariants of a result object, so in a real system you must ensure the two states of success/failure are unambiguous.

For batch processing, a result structure containing `value` or `error` per element can make more sense than letting a checked exception escape sneakily through `Stream.map()`. The caller can:

- Collect both successes and failures.
- Identify which elements need retrying.
- Avoid using exceptions to represent an expected, common outcome.
- Apply a dedicated policy for partial success.

Be careful to avoid returning a fake success when the operation actually failed. A good option does not just satisfy the compiler; it must preserve **failure semantics**.

## 20. Comparing `sneaky throw`, checked generic APIs, and unchecked wrappers

| Criterion | Transparent generic API `throws E` | Sneaky throw | `UncheckedIOException` |
| --- | --- | --- | --- |
| Is the callback's checked exception represented at the call site? | Yes, when constraints/type witness propagate the checked type | Can be inferred as unchecked at the call site | No checked `throws` needed; the wrapper is unchecked |
| Type of thrown object | Usually preserves the callback's original exception | Preserves the original checked exception | Creates a **new wrapper object** |
| Does the caller know to `catch IOException`? | Yes when the contract declares `IOException` | Usually not; specialized catch may fail to compile | Caller catches `UncheckedIOException` and inspects `IOException` via cause |
| Cause/stack trace | Depends on the original object; wrapper not required | Does not automatically create cause/wrapper | Preserves `IOException` cause; wrapper has its own stack trace |
| Contract clarity | High | Low unless documented very explicitly | Higher if the API documents the wrapper type |
| Recommended for typical applications? | Yes, when checked is appropriate | Generally avoid | Yes, at API boundaries that do not support checked exceptions and for I/O errors |
| Main risk | Complex generic signatures if overused | Hides runtime checked type from the compiler | Shifts checked obligation to unchecked; caller must know the runtime contract |

No option is free. With an unchecked wrapper, the compiler still does not **force** the caller to `catch`; what it improves is **transparency about the actual object and how to retrieve the cause**, not automatically restoring checked exception obligations.

## 21. Sneaky throw differs from Java's precise rethrow

Java has another mechanism often confused with sneaky throw: **precise rethrow analysis** in appropriate `catch` cases.

Example:

~~~java
import java.io.IOException;
import java.sql.SQLException;

// Illustrative snippet inside a class where operation() throws two checked types.
static void process() throws IOException, SQLException {
    try {
        operation();
    } catch (Exception ex) {
        throw ex;
    }
}
~~~

Here `operation()` must be defined with `throws IOException, SQLException`, and the variable `ex` is not reassigned. The compiler can analyze the specific checked exception types arising from the `try` block to accept the `throws IOException, SQLException` clause instead of forcing the method to declare a broad `throws Exception`.

**This is not sneaky throw**:

- The appropriate checked types still appear in the method contract.
- Callers must still catch or declare them.
- It does not attempt to use an unconstrained type variable to erase checked obligations.
- The analysis depends on JLS-specified conditions, including the *effectively final* status of the catch parameter and what can be thrown from the `try` block.

Do not lump every case where the compiler infers a narrower `throws` under the "sneaky" label. Precise inference to **preserve** a contract is different from a trick that intentionally **hides** an exception type.

## 22. Sneaky throw differs from `throw new RuntimeException(ex)`

Compare:

~~~java
// Illustrated inside catch (IOException ex).
throw new RuntimeException("Không thể đọc dữ liệu", ex);
~~~

and:

~~~java
// Illustrated in the same context, with passThrough(...) helper already defined.
passThrough(ex);
~~~

In the first case:

- Creates **a new `RuntimeException` object**.
- The new object has `IOException` as its `cause`.
- An outer `catch (RuntimeException)` can catch the wrapper.
- `getCause()` and the stack trace show both the wrapping layer and the original I/O error.

In the second case:

- Does not create a new wrapper.
- If the helper throws `ex`, the escaping object is still the `IOException` itself.
- `catch (RuntimeException)` will **not** catch `IOException`.
- Object identity and data on the original exception are preserved.
- The static `throws` of the calling method may not reflect `IOException`.

The second technique is more surprising, because consumers of the method cannot deduce from the signature that a specific checked exception will escape.

## 23. Explicit type witnesses can change `throws` obligations

Returning to the helper:

~~~java
static <E extends Throwable> void passThrough(Throwable failure) throws E {
    throw (E) failure;
}
~~~

This is **illustrative code without the suppress-warnings annotation**; the generic cast itself may generate an unchecked warning. When calling:

~~~java
passThrough(new java.io.IOException("I/O"));
~~~

the compiler can infer `E` as an unchecked type if there are no other specific constraints. But if you write:

~~~java
SomeClass.<java.io.IOException>passThrough(
        new java.io.IOException("I/O"));
~~~

where `SomeClass` is the class declaring `passThrough`, `E` has been explicitly specified by the caller as `IOException`, placing the call on the checked exception path. The caller must handle or declare `IOException`.

This difference only concerns **static checking**: at runtime, both calls still receive the same exception object type if the argument is constructed the same way.

However, you should not use type witnesses as a "fix for sneaky throw" for external callers. A well-designed public API should declare its error contract directly, rather than forcing users to understand generic internals and attach special type arguments to make the compiler recognize checked exceptions.

## 24. The truth about `@SuppressWarnings("unchecked")`

The annotation name can mislead beginners:

~~~java
@SuppressWarnings("unchecked")
static <E extends Throwable> void passThrough(Throwable t) throws E {
    throw (E) t;
}
~~~

The annotation above:

- **Does not convert** `IOException` into an unchecked exception.
- **Does not rewrite** `throws E` into `throws RuntimeException`.
- **Does not alter** runtime `catch` dispatch.
- **Does not guarantee** that the cast is safe for a specific concrete type.
- Only **suppresses compiler warnings** of the unchecked cast kind within its scope.

The reason the caller is not forced to handle `IOException` in some calls lies in the **generic signature and the inference result for `E`**, not in the annotation.

When reviewing code with `@SuppressWarnings("unchecked")`, do not automatically conclude there is a sneaky throw. Many valid generic APIs also need to use controlled unchecked casts. However, if the annotation appears next to a `<E extends Throwable> ... throws E` helper that takes a `Throwable` parameter independent of `E`, that is a sign to review the exception contract.

## 25. Common misconceptions in this topic

| Statement or habit | Why is it incorrect? | Correct understanding |
| --- | --- | --- |
| "Generic `throws E` always drops checked exceptions." | Lambdas can contribute checked constraints; type witnesses can set `E` concretely. | Examine all inference constraints and the target type. |
| "Sneaky throw turns `IOException` into `RuntimeException`." | The runtime type of the object does not change. | The compiler may infer `E` as unchecked, while the object remains `IOException`. |
| "`catch (RuntimeException)` definitely catches sneaky errors." | `IOException` is not in the `RuntimeException` branch. | Dispatch follows the actual runtime class. |
| "Just write `catch (IOException)` around the sneaky call." | The compiler may consider the `try` block not to throw checked `IOException`. | Declare the checked contract or handle at an appropriate boundary. |
| "Once `@SuppressWarnings` is used, everything is safe." | The annotation only hides warnings; it does not fix logic. | Evaluate casts and contracts independently. |
| "A lambda in `Runnable` can throw `IOException` if the outer method has `throws IOException`." | The target method `Runnable.run()` does not declare checked exceptions. | Use a matching functional interface or handle/wrap inside the lambda. |
| "`Function<T,R>` automatically converts checked to unchecked." | The API has no such exception transformation mechanism. | Wrap explicitly if needed or use a different API. |
| "Every generic method with a `throws` type variable is sneaky." | Many generic methods propagate checked constraints properly. | Distinguish constrained `throws E` callbacks from helpers that decouple `Throwable` from `E`. |
| "Sneaky throw is only a compile-time issue with no runtime consequences." | Checked objects can still escape and miss expected handlers. | Design an error policy and test runtime paths. |
| "Unchecked wrappers and sneaky throw are the same." | Wrappers create a new object with a cause; sneaky throw usually throws the original object. | Distinguish identity, cause, and runtime type. |
| "Once `E=RuntimeException` is inferred, the JVM will checkcast the `IOException` object to `RuntimeException`." | Not the behavior of the type-erased generic helper here. | Understand erasure and the JVM's `Throwable` throw mechanism. |
| "No need to preserve the cause when wrapping." | Loses context and the underlying error's stack trace. | Use the `(message, cause)` constructor. |
| "Just use `catch(Throwable)` to fix everything." | Can mask `Error`s as well, leading to uncontrolled error handling. | Fix the API or use a purpose-built boundary. |

## 26. How to spot sneaky throw in code review

A practical checklist:

1. Is there a generic helper of the form `<E extends Throwable> ... throws E`?
2. Is the type variable `E` actually constrained by parameter/functional interface types, or does it only appear in `throws` and a cast?
3. Does the method take a `Throwable` independent of `E` and use `throw (E) t`?
4. Do callers omit declaring checked exceptions despite passing `IOException`, `SQLException`, or another checked exception?
5. Is there `@SuppressWarnings("unchecked")` near the related generic cast?
6. Are `Runnable`, `Supplier`, `Function`, `Stream.map`, or callbacks that do not declare checked exceptions involved?
7. What runtime exception is actually thrown — the original type or a wrapper?
8. Do outer handlers only catch `RuntimeException`, or is there a strategy suited to the actual type?
9. Are public API users clearly informed in documentation about which checked exceptions can escape?
10. Is there a more transparent option: checked generic callback, `UncheckedIOException`, custom unchecked wrapper, result object, or local handling?

If the helper is used in a legacy library and cannot be changed immediately, you must test **actual failure scenarios**, not just compile the calling code. Document clearly in technical docs where checked exceptions can escape outside the signature, and plan to eliminate the contract mismatch when possible.

## 27. Testing error paths without being misled by the compiler

When you suspect an API uses sneaky throw, you should have both kinds of tests:

**Compile-time tests:** verify whether certain calls are valid or rejected as expected. For example, `RunnableCheckedBad.java` and `CatchCheckedBad.java` in this lesson **intentionally do not compile**. This is evidence that the compiler does not treat those two cases as equivalent to declaring `throws IOException`.

**Runtime tests:** create a concrete checked exception object and observe the final object caught by a boundary:

~~~java
// Illustrative snippet with the passThrough helper defined.
try {
    passThrough(new java.io.IOException("sự cố"));
} catch (Throwable ex) {
    System.out.println(ex.getClass().getName());
}
~~~

This pattern is for testing/diagnostics only. In production code, `catch(Throwable)` is too broad for most business logic; avoid swallowing `OutOfMemoryError`, `ThreadDeath`, or `Error` types that should not be handled like normal business errors.

With a well-designed unchecked wrapper, you can assert `ex instanceof UncheckedIOException` and `ex.getCause() instanceof IOException`. With a sneaky helper, you can verify that **the exact same `Throwable` object** is thrown, though that test does not prove the API should be used that way.

## 28. Self-check questions

**Question 1.** Does `IOException` automatically become `RuntimeException` when passing through a sneaky helper?

**Answer:** No. The runtime object remains `IOException`; only the compile-time inference of `throws E` may avoid forcing the caller to handle the checked exception.

**Question 2.** Can a lambda `() -> { throw new IOException(); }` be assigned directly to `Runnable`?

**Answer:** No, because `Runnable.run()` does not declare checked `IOException`.

**Question 3.** Why can `perform(() -> { throw new IOException(); })` with `ThrowingAction<E>` force the caller to handle `IOException`?

**Answer:** The checked exception from the lambda body generates a constraint on type `E` in the `throws` clauses of the target functional interface and the generic method.

**Question 4.** In a sneaky helper taking `Throwable`, why does the `Throwable` parameter matter?

**Answer:** Because passing `new IOException()` does not directly force `E=IOException`; the type variable in `throws E` can be inferred as unchecked when no other constraints exist.

**Question 5.** Can a sneaky `IOException` object be automatically caught by `catch(RuntimeException)`?

**Answer:** No. Catching depends on the runtime type, and `IOException` is not a subtype of `RuntimeException`.

**Question 6.** If only a sneaky call is inside `try`, can `catch(IOException)` be rejected by the compiler?

**Answer:** Yes. In the verified example, `javac` reports that `IOException` is not considered a checked exception that can be thrown from the `try` body based on static information.

**Question 7.** Is `@SuppressWarnings("unchecked")` what makes `throws E` unchecked?

**Answer:** No. It only suppresses the cast warning; the outcome is due to type inference and generic constraints.

**Question 8.** How does calling `SneakyThrowDemo.<IOException>passThrough(...)` differ from letting the compiler infer automatically?

**Answer:** The type witness explicitly specifies `E=IOException`; the call is checked according to checked `throws IOException`.

**Question 9.** Why is `UncheckedIOException` usually more transparent than sneaky throw in Streams?

**Answer:** Because the caller sees an **intentional runtime wrapper exception type**, and the original I/O error is preserved in `getCause()`, instead of a checked exception escaping a signature that does not declare it.

**Question 10.** Is generic `throws E` always an anti-pattern?

**Answer:** No. It is useful and semantically sound with functional interfaces/callbacks that declare `throws E` and propagate checked constraints to the caller.

**Question 11.** Is precise rethrow `catch(Exception ex) { throw ex; }` the same as sneaky throw?

**Answer:** No. Precise rethrow infers the checked exceptions actually allowed to be thrown from the `try` block under JLS rules; the caller still receives an accurate `throws` contract.

**Question 12.** When refactoring a public API that currently uses sneaky throw, what should you do?

**Answer:** Identify which runtime exceptions actually escape, decide on a transparent checked or unchecked contract, preserve the cause if wrapping, update tests/callers, and document compatibility changes.

## 29. Official references

- [Java Language Specification 17 — §18.1.3, Bounds](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.1.3): describes the informational bound `throws α` when an inference variable appears in `throws`.
- [Java Language Specification 17 — §18.2.5, Checked Exception Constraints](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.2.5): checked exception constraints from lambdas/method references.
- [Java Language Specification 17 — §18.4, Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): when no suitable lower bounds exist and upper bounds allow, an inference variable in `throws` can be resolved to `RuntimeException`.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): compile-time checked exception checking rules.
- [Java Language Specification 17 — §15.27.3, Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): lambdas and target functional interfaces.
- [Java Language Specification 17 — §4.6, Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): meaning of type erasure.
- [Java SE 17 API — `java.io.UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): unchecked wrapper with `IOException` as cause.
- [Java SE 17 API — `java.util.function.Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional interface used in Streams, without checked `throws` on `apply`.

**Conclusion:** Generic `throws E` is a valid API design feature, especially when combined with lambdas and functional interfaces that have checked exceptions. **Sneaky throw** occurs when a type variable used in `throws` is not constrained enough to preserve the checked exception type; the compiler may infer an unchecked type, while the runtime still throws the real `IOException` object. Because of the risks to contracts and caller handlers, prefer **transparent catch-or-declare, callbacks with `throws E`, semantically appropriate unchecked wrappers, or structured result objects** instead of hiding checked exceptions.