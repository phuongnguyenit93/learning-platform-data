# Why Do Standard `Function`, `Consumer`, and `Supplier` Cause Friction with Checked Exceptions in Java?

> **Topic:** Java Core → Exception → Lambdas and generics. The three familiar functional interfaces in `java.util.function` — `Function<T,R>`, `Consumer<T>`, and `Supplier<T>` — are designed for general-purpose callbacks, but **their abstract methods do not declare `throws` for checked exceptions**. Therefore, a lambda or method reference assigned to these types cannot allow `IOException`, `SQLException`, or any other checked exception to escape directly. This friction comes from the **lambda's target method contract**, not because lambdas "cannot use checked exceptions."

## 1. Know the Three Signatures

Read the three abstract methods (the actual interfaces also have other helper methods):

```java
@FunctionalInterface
interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
interface Consumer<T> {
    void accept(T value);
}

@FunctionalInterface
interface Supplier<T> {
    T get();
}
```

This is a **simplified version to explain the signatures**, not a copy of the entire JDK source code; when writing real code, use `java.util.function.Function`, `Consumer`, and `Supplier`. Parameter names do not matter, but the absence of `throws IOException` or `throws Exception` is crucial.

| Standard Interface | Target Method | Common Use Case | Allows Checked Exceptions to Escape Directly? |
| --- | --- | --- | --- |
| `Function<T,R>` | `R apply(T t)` | Transform from T to R, `stream.map(...)` | No |
| `Consumer<T>` | `void accept(T t)` | Perform side effects, `forEach(...)` | No |
| `Supplier<T>` | `T get()` | Create/provide a value on demand, `orElseGet(...)` | No |

**Note:** "Not declaring checked exceptions" does not mean the callback cannot throw **unchecked `RuntimeException` or `Error`**. They can still occur at runtime even without a `throws` clause.

Valid examples:

```java
java.util.function.Function<String, Integer> length =
        String::length;

java.util.function.Consumer<String> print =
        System.out::println;

java.util.function.Supplier<String> supply =
        () -> "Hello";
```

The snippets above use lambdas/method references that do not throw checked exceptions according to their signatures. In contrast, `Files.readString(path)` or `BufferedReader.readLine()` can throw `IOException` (checked), so they cannot be placed directly into a standard callback without handling them.

## 2. Checked and Unchecked Exceptions: The Issue Is at Compile-Time

In Java:

- **Checked exceptions:** subtypes of `Throwable` not under the `RuntimeException` or `Error` branches; for example, `IOException`, `SQLException`, `ParseException`, `InterruptedException`. When they can escape a method, the code must catch or declare them according to Java rules.
- **Unchecked exceptions:** `RuntimeException`/`Error` and their subtypes. The compiler does not enforce the catch-or-declare obligation as it does for checked exceptions.
- **Lambdas:** can run code that throws errors just like any method; **what is restricted** is the set of checked exceptions they are allowed to let escape, based on the **functional interface serving as the target type**.

The purpose of checked exceptions is so the caller can see and handle failure paths per the API. `Function.apply` does not advertise `IOException`; a call site invoking `Function.apply`, such as the implementation of `Stream.map`, has no declared obligation for checked I/O. Java cannot let a lambda secretly widen that contract.

### 2.1. Code That Intentionally Does Not Compile: `Function`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

class InvalidFunction {
    static void demo() {
        Function<Path, String> read = path -> Files.readString(path);
    }
}
```

This is an **example that intentionally does not compile**: `Files.readString(Path)` declares checked `IOException`, whereas `Function.apply(Path)` does not. The `javac` message typically states "unreported exception IOException; must be caught or declared".

Even if `demo()` is changed to:

```java
static void demo() throws IOException {
    Function<Path, String> read = path -> Files.readString(path);
}
```

it is **still invalid**. `throws IOException` belongs to **`demo()`**, and does not change the signature of `Function.apply()` that the lambda implements. The exception can occur **after `demo()` has already finished**, at the moment another caller runs `read.apply(...)`. The compiler must protect the callback's contract, not just the method where the lambda is created.

### 2.2. Code That Intentionally Does Not Compile: `Consumer`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Consumer;

class InvalidConsumer {
    static void demo() {
        Consumer<Path> delete = path -> Files.delete(path);
    }
}
```

`Files.delete(Path)` can throw checked `IOException`; `Consumer.accept` declares no checked exceptions. Therefore, the snippet above is rejected.

Do not assume "because Consumer returns void, it can throw anything." The return value and checked `throws` rules are two independent aspects.

### 2.3. Code That Intentionally Does Not Compile: `Supplier`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Supplier;

class InvalidSupplier {
    static void demo(Path path) {
        Supplier<String> source = () -> Files.readString(path);
    }
}
```

`Supplier.get()` declares no checked exceptions. Even if `get()` is only called later, the contract still does not allow `IOException` to escape directly.

## 3. Lambdas Do Not Decide Their Own `throws` Signature: Target Typing

A lambda like:

```java
path -> java.nio.file.Files.readString(path)
```

does not carry a "standalone lambda type" with an exception contract automatically inferred from its body. It needs a **target type** — usually a functional interface.

The same file-reading logic can be:

- **Rejected** when the target is `Function<Path,String>`.
- **Valid** when the target is a custom functional interface with `String apply(Path) throws IOException`.
- **Valid** when the lambda catches `IOException` inside and returns a result or converts it to an appropriate unchecked exception.

Example:

```java
@FunctionalInterface
interface ThrowingPathReader {
    String read(java.nio.file.Path path)
            throws java.io.IOException;
}
```

Then:

```java
ThrowingPathReader reader =
        path -> java.nio.file.Files.readString(path);
```

is valid inside a class/method with the corresponding imports or fully qualified names. However, `ThrowingPathReader` **is not automatically** a `Function<Path,String>`; you cannot pass the `reader` variable directly into `Stream.map(...)`, because `map` requires the standard `Function`.

That is why an **adapter** between the two callback types is sometimes needed.

## 4. Method References Face the Exact Same Constraint

Not just lambdas:

```java
// INTENTIONALLY INVALID:
java.util.function.Function<java.nio.file.Path, String> read =
        java.nio.file.Files::readString;
```

`Files.readString(Path)` declares `throws IOException`, so that method reference is incompatible with the abstract method `Function.apply`.

Conversely:

```java
ThrowingPathReader read =
        java.nio.file.Files::readString;
```

can be valid if `ThrowingPathReader` is defined as in Section 3.

**Method references do not bypass checked exception rules.** They are shorthand for converting an existing method into a callback of a matching functional interface; exception type checking still relies on the target method.

## 5. Why Do `Stream.map(...)` and `forEach(...)` Commonly Expose This Issue?

The Stream API uses the standard functional interfaces, for example:

```java
<R> java.util.stream.Stream<R> map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

This is the conceptual signature of `Stream<T>.map`, not a standalone program. The `mapper` parameter accepts type `Function`; therefore, a lambda passed to `map` is still restricted by the checked `throws` of `Function.apply`.

For example, a learner wants to read multiple files:

```java
// INTENTIONALLY INVALID — readString has checked IOException:
java.util.List<String> content = paths.stream()
        .map(path -> java.nio.file.Files.readString(path))
        .toList();
```

Assume `paths` is `List<Path>`. Even though the code is inside a method that might declare `throws IOException`, the callback accepted by `map` is still `Function<Path,String>`, which **does not declare checked exceptions**.

Similarly, `forEach` uses `Consumer`:

```java
// INTENTIONALLY INVALID — Files.delete(path) has checked IOException:
paths.forEach(path -> java.nio.file.Files.delete(path));
```

It is not because Stream or `List.forEach` forbids I/O, but because the **callback type at the call site** does not allow checked exceptions to escape directly.

### 5.1. Streams Are Typically Lazy

In a Stream pipeline, `map` is an **intermediate operation**. The registered lambda may not run immediately when the pipeline is constructed. Typically, it is invoked during the execution of a **terminal operation** such as `toList()`, `collect(...)`, `forEach(...)`, or `reduce(...)`.

This affects where errors are caught:

```java
var pipeline = inputs.stream().map(converter);
try {
    var results = pipeline.toList();
    // Use results.
} catch (RuntimeException e) {
    // Unchecked error from converter may appear during the terminal operation.
}
```

This illustrative snippet assumes `inputs`/`converter` are already defined. If `converter` wraps checked `IOException` into `UncheckedIOException`, the error may surface at `toList()`, not at the time you call `map(converter)`.

Do not conclude a pipeline "succeeded" just because the expression `stream.map(...)` returned a Stream.

### 5.2. Parallel Streams and Side-Effect Policies

If a lambda performs I/O via `parallelStream()`, execution/completion order may be non-deterministic; an exception from one worker can cause the terminal operation to fail while other side effects have already occurred. Do not assume rollback, log ordering, or that "once an error occurs, all other tasks stop immediately."

Be especially careful with a `Consumer` writing/deleting files or performing transactional operations: parallel execution and exceptions do not automatically guarantee atomicity.

## 6. Approach 1: Catch Checked Exceptions Inside the Lambda

When a standard API requires a `Function` and you have a way to **genuinely handle** the error right there, you can use `try/catch` directly inside the lambda body.

### 6.1. Return a Meaningful Fallback, Do Not Arbitrarily Hide Errors

Create **`FunctionCatchInsideDemo.java`**:

```java
import java.io.IOException;
import java.util.List;
import java.util.function.Function;

public class FunctionCatchInsideDemo {
    static int parseSize(String input) throws IOException {
        if ("bad".equals(input)) {
            throw new IOException("Nguồn không khả dụng");
        }
        return input.length();
    }

    public static void main(String[] args) {
        Function<String, Integer> safeLength = input -> {
            try {
                return parseSize(input);
            } catch (IOException e) {
                System.out.println("Ghi nhận lỗi: " + input);
                return -1;
            }
        };

        List<Integer> results = List.of("cat", "bad", "xy")
                .stream()
                .map(safeLength)
                .toList();

        System.out.println("Kết quả: " + results);
    }
}
```

Compile/run on Java 17:

```bash
javac -encoding UTF-8 FunctionCatchInsideDemo.java
java FunctionCatchInsideDemo
```

Stdout:

```text
Ghi nhận lỗi: bad
Kết quả: [3, -1, 2]
```

**Explanation:**

1. `parseSize` declares `throws IOException`; inside it is a controlled simulated failure path.
2. The `safeLength` lambda catches `IOException` itself, so no checked exception escapes `Function.apply`.
3. The value `-1` in this example is a **sentinel** agreed upon for failure to make it easy to observe; it is not a safe default fallback for every problem.
4. The stream is executed via `toList()`, which triggers the callback.
5. If `-1` is also a valid value in the domain, or the caller needs to know the I/O cause, this design can easily become ambiguous. In that case, use an explicit result type or let the error propagate through a different contract.

### 6.2. Avoid "Catch and Treat as Success"

Anti-pattern:

```java
Function<Path, String> unsafe = path -> {
    try {
        return Files.readString(path);
    } catch (IOException ignored) {
        return "";
    }
};
```

This is an illustrative snippet requiring imports for `Path`/`Files`/`IOException`. If an empty string is valid file data, the caller cannot distinguish between an "actually empty file" and "reading the file failed." Do not use this approach just to get past the compiler.

If a fallback is part of the **product contract** — for example, a verified backup cache — returning a fallback is fine; clearly document when the fallback applies and its impact on state.

## 7. Approach 2: Convert Checked Exceptions to Unchecked and Preserve `cause`

When you cannot handle the error validly inside the callback, yet the API requires `Function`/`Consumer`/`Supplier`, you can wrap the checked exception in an appropriate unchecked exception and let the error **propagate up** to where failure is decided.

For `IOException`, Java provides `java.io.UncheckedIOException`:

```java
try {
    return java.nio.file.Files.readString(path);
} catch (java.io.IOException original) {
    throw new java.io.UncheckedIOException(
            "Không đọc được file", original);
}
```

This is an illustrative method/lambda snippet that must be placed in an appropriate `return` context. Advantages:

- `UncheckedIOException extends RuntimeException`, so the `Function.apply` callback is allowed to throw it.
- `getCause()` preserves the original `IOException` object for tracing.
- The caller receives **`UncheckedIOException`**, not `IOException` directly when invoking the callback.
- The error is not swallowed or disguised as a success value.

**Do not** replace it with `throw new RuntimeException(original.getMessage())`: that copies the message but loses the cause link. When using a wrapper, prefer a constructor that accepts a cause.

### 7.1. Java 17: I/O Adapter from `ThrowingFunction` to `Function`

Create **`UncheckedFunctionAdapterDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class UncheckedFunctionAdapterDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> source) {
        Objects.requireNonNull(source);
        return value -> {
            try {
                return source.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException(
                        "Không thể chuyển đổi dữ liệu", e);
            }
        };
    }

    static int readSize(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("Không đọc được bad");
        }
        return key.length();
    }

    public static void main(String[] args) {
        Function<String, Integer> mapper =
                unchecked(UncheckedFunctionAdapterDemo::readSize);

        try {
            System.out.println(
                    List.of("good", "bad", "later")
                            .stream()
                            .map(mapper)
                            .toList());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 UncheckedFunctionAdapterDemo.java
java UncheckedFunctionAdapterDemo
```

Stdout:

```text
Wrapper: UncheckedIOException
Cause: IOException
Cause message: Không đọc được bad
```

**Execution flow:**

1. `IoFunction.apply` **has** `throws IOException`, so the method reference `readSize` is a valid target for `IoFunction`.
2. `unchecked(...)` returns a standard `Function<T,R>`, catching `IOException` and throwing `UncheckedIOException`.
3. `Stream.map(...)` accepts `Function` and compiles.
4. When the terminal `toList()` runs, the element `"bad"` causes `readSize` to throw `IOException`.
5. The unchecked wrapper escapes to the terminal operation site and is caught by `catch (UncheckedIOException)`.
6. `"later"` is not transformed in this sequential pipeline after the exception fails the terminal operation; the example does not rely on this assumption for work recovery.

**Not a magic adapter:** the adapter changes **how the error is reported**; it does not turn failure into success, does not roll back side effects, and does not guarantee safe retries. It is appropriate when the API boundary already accepts unchecked failures and the caller has a diagnostic/recovery policy.

### 7.2. What If It Is Not `IOException`?

`UncheckedIOException` only accepts **`IOException`** as its cause. For other checked exceptions, you can create an appropriate `RuntimeException` subclass or use `RuntimeException("...", cause)` to preserve the cause when it fits the contract.

Do not wrap all existing `RuntimeException`s in another wrapper without a reason: it loses classification details and complicates the stack trace. A specialized adapter should catch **only the expected checked exceptions**, letting unchecked programming errors propagate as-is.

## 8. Approach 3: Use a Custom `ThrowingFunction<T,R,E>` with `throws E`

When **you control the API accepting the lambda**, the clearest way to express a checked exception contract is sometimes to create a custom functional interface:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
```

If `E` is `IOException`, the lambda can let `IOException` escape, and the caller of the method accepting the callback must handle it. This interface uses a **generic type parameter `E`** to declare the checked exception that may occur.

Similarly:

```java
@FunctionalInterface
interface ThrowingConsumer<T, E extends Exception> {
    void accept(T input) throws E;
}

@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}
```

These three types are **custom definitions**, not standard interfaces from `java.util.function`. The name `ThrowingFunction` and the generic `E extends Exception` are a design convention; Java does not include them out of the box in `java.util.function`.

### 8.1. How Does Generic `E` Help?

Consider:

```java
static <T, R, E extends Exception> R call(
        T input, ThrowingFunction<T, R, E> operation) throws E {
    return operation.apply(input);
}
```

This is an illustrative method to be placed inside a class. Because `operation` can throw `E`, the `call` method declares `throws E`. If the lambda is bound to `IOException`, the caller can catch `IOException` instead of being forced to catch a broad `Exception`.

A generic exception type can improve contract precision. However, type inference has its own rules; if the program is complex or has multiple independent exceptions, you may need explicit type parameters/signatures. Do not assume a single generic `E` perfectly represents every union of checked exceptions.

### 8.2. Java 17: Preserve Checked Exceptions via a Custom Functional Interface

Create **`ThrowingFunctionDemo.java`**:

```java
import java.io.IOException;

public class ThrowingFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static <T, R, E extends Exception> R execute(
            T input, ThrowingFunction<T, R, E> action) throws E {
        return action.apply(input);
    }

    static int loadLength(String input) throws IOException {
        if ("bad".equals(input)) {
            throw new IOException("Dữ liệu không đọc được");
        }
        return input.length();
    }

    public static void main(String[] args) {
        try {
            int result = ThrowingFunctionDemo
                    .<String, Integer, IOException>execute(
                            "cat", ThrowingFunctionDemo::loadLength);
            System.out.println("Length: " + result);

            ThrowingFunctionDemo
                    .<String, Integer, IOException>execute(
                            "bad", ThrowingFunctionDemo::loadLength);
        } catch (IOException e) {
            System.out.println("Checked: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ThrowingFunctionDemo.java
java ThrowingFunctionDemo
```

Stdout:

```text
Length: 3
Checked: IOException
Message: Dữ liệu không đọc được
```

**Key points:**

- `ThrowingFunction.apply` allows checked `E`.
- `execute(...)` declares `throws E`, so the original exception can escape **without an unchecked wrapper**.
- At the call site, the example explicitly specifies generic arguments, including `IOException`, to make it easy to follow when learning; in simple cases the compiler can infer the types.
- There is no need for a broad `catch(Exception)` or `throws Exception` if the actual contract only requires `IOException`.
- If you want to pass `ThrowingFunction` directly to standard `Stream.map`, it still will not work: `map` accepts `Function`, not this custom type.

### 8.3. Why Doesn't Defining Your Own Interface Solve `Stream.map` Directly?

In Java, lambdas are target-typed, but `Stream.map` already declares:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

The method signature of `map` belongs to the standard library; creating `ThrowingFunction` **does not replace `map`'s parameter type**. To apply it, you must:

1. Write an **adapter** from `ThrowingFunction` to `Function`, deciding to convert errors to unchecked or handle them otherwise; or
2. Write your own processing method/pipeline that accepts `ThrowingFunction` and declares `throws E`; or
3. Use a regular loop with `try/catch`/`throws` when checked exception logic is central.

This is a constraint of the **target API**, not a generics issue that makes the `throws` keyword disappear.

## 9. `Consumer<T>`: Handling Side Effects and Checked Exceptions

`Consumer.accept` takes an object and returns `void`; side-effect operations are typically writing files, deleting files, saving data, sending events, or updating state. These operations are especially prone to checked exceptions.

A `Consumer` with `forEach` can:

- Catch errors and continue processing the next element **if that is the chosen policy**.
- Catch and throw an unchecked wrapper, which typically stops the loop immediately due to the exception.
- Record errors into a structured result managed externally (requiring concurrency and thread-safety considerations).
- Never let a checked exception escape directly per `Consumer.accept`.

### 9.1. Java 17: Catch Individual Errors When the Policy Allows Continuing

Create **`ConsumerFailurePolicyDemo.java`**:

```java
import java.io.IOException;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerFailurePolicyDemo {
    static void process(String name) throws IOException {
        if ("bad".equals(name)) {
            throw new IOException("Không xử lý được bad");
        }
        System.out.println("OK: " + name);
    }

    public static void main(String[] args) {
        Consumer<String> consumer = name -> {
            try {
                process(name);
            } catch (IOException e) {
                System.out.println("FAILED: " + name);
            }
        };

        List.of("one", "bad", "two").forEach(consumer);
        System.out.println("Hoàn tất lượt forEach");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ConsumerFailurePolicyDemo.java
java ConsumerFailurePolicyDemo
```

Stdout:

```text
OK: one
FAILED: bad
OK: two
Hoàn tất lượt forEach
```

This example deliberately chooses to **continue after a failed element**, because elements are treated as independent in the simulated scenario. This is **not the right default** for real-world data-writing operations.

If the failure of one element must fail the entire batch, merely printing "FAILED" and continuing as if it succeeded is wrong. In that case, use a batch result structure that represents failed elements, or throw a wrapper and let the caller handle batch state; also consider side effects that already occurred earlier.

### 9.2. Write a Regular Loop When Clear Checked Semantics Are Needed

Instead of `forEach`:

```java
static void deleteAll(java.util.List<java.nio.file.Path> files)
        throws java.io.IOException {
    for (java.nio.file.Path path : files) {
        java.nio.file.Files.delete(path);
    }
}
```

This is a **complete method**, but it must be placed inside a class. It keeps checked `throws IOException` explicit, uses a regular `for` loop, and needs no `Consumer` adapter.

When the primary job is I/O that can fail, a regular loop is often **easier to understand** than forcing a standard `Consumer` and wrapping exceptions across multiple layers. Not every task has to use Streams/lambdas to be modern Java.

## 10. `Supplier<T>`: Providing Values, but `get()` Disallows Checked Exceptions

`Supplier<T>` is very common for lazy value creation, `Optional.orElseGet(...)`, cache APIs, and object creation hooks. If value initialization involves checked I/O or SQL, lambdas hit the same limitation.

Invalid example:

```java
java.util.function.Supplier<String> config =
        () -> java.nio.file.Files.readString(path);
```

Assume `path` has type `Path`. `Files.readString` has `throws IOException`, so it does not compile when used directly with `Supplier.get`.

### 10.1. Java 17: `Supplier` Converting IOException to Unchecked

Create **`SupplierCheckedDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Supplier;

public class SupplierCheckedDemo {
    static String readConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không tải được config");
        }
        return "ready";
    }

    static Supplier<String> createSupplier(boolean fail) {
        return () -> {
            try {
                return readConfig(fail);
            } catch (IOException e) {
                throw new UncheckedIOException("Lỗi cấu hình", e);
            }
        };
    }

    public static void main(String[] args) {
        Supplier<String> good = createSupplier(false);
        Supplier<String> bad = createSupplier(true);

        System.out.println("Good: " + good.get());
        try {
            System.out.println("Bad: " + bad.get());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SupplierCheckedDemo.java
java SupplierCheckedDemo
```

Stdout:

```text
Good: ready
Wrapper: UncheckedIOException
Cause: Không tải được config
```

`createSupplier(...)` only creates the callback object; `readConfig(...)` is executed **when `get()` is called**, not when constructing the supplier. Hence the error occurs inside `get()`. The `Supplier.get` signature does not declare checked exceptions, so the unchecked wrapper keeps the failure path valid for the target API.

### 10.2. `Optional.orElseGet` Is Also Subject to This Rule

`Optional.orElseGet(Supplier<? extends T>)` takes a standard `Supplier`. If the fallback must call a checked I/O API, the code needs to handle/wrap the exception the same way. Java does not exempt checked exceptions just because it is a "fallback."

One more note: `Optional.orElseGet` only calls the supplier when the Optional is empty, so errors from the supplier **can only occur on the fallback path**. Do not neglect testing this branch.

## 11. `Callable<V>` Differs from `Supplier<V>` in Checked `throws`

The standard library has `java.util.concurrent.Callable<V>`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

Because `Callable.call()` declares `throws Exception`, a lambda calling an API that throws checked `IOException` can be assigned to `Callable<String>`. This is a very clear contrast with `Supplier.get()`.

| Criterion | `Supplier<T>` | `Callable<V>` |
| --- | --- | --- |
| Target method | `T get()` | `V call() throws Exception` |
| Can checked exceptions escape? | No | Yes; within `Exception` |
| Package | `java.util.function` | `java.util.concurrent` |
| Accepted directly by `Stream.map`? | No; `map` takes `Function` | No; `map` takes `Function` |
| Commonly used in | Lazy values, Optional, factory callbacks | Executor/service tasks, work that can fail |

`Callable` is not a `Supplier` by another name. The two interfaces have different purposes and signatures; you cannot pass a `Callable` directly to an API expecting a `Supplier` without an adapter.

### 11.1. Java 17: `Callable` Preserves Checked Exceptions

Create **`CallableVsSupplierDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.function.Supplier;

public class CallableVsSupplierDemo {
    static String load(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không có dữ liệu");
        }
        return "loaded";
    }

    public static void main(String[] args) {
        Callable<String> task = () -> load(true);
        Supplier<String> good = () -> {
            try {
                return load(false);
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        };

        System.out.println("Supplier: " + good.get());
        try {
            System.out.println("Callable: " + task.call());
        } catch (IOException e) {
            System.out.println("Checked: " + e.getMessage());
        } catch (Exception e) {
            System.out.println("Other: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CallableVsSupplierDemo.java
java CallableVsSupplierDemo
```

Stdout:

```text
Supplier: loaded
Checked: Không có dữ liệu
```

**Why is `catch(IOException)` valid?** `Callable.call()` declares `throws Exception`, so it can throw the checked subtype `IOException`. The remaining `catch(Exception)` handler covers other checked exceptions permitted by `Callable`'s contract.

If you replace the `task.call()` call with `good.get()` inside a `try` that only has `Supplier.get()`, a checked `IOException` handler with no corresponding checked source will be rejected by the compiler. When an unchecked wrapper is used, you must catch the appropriate wrapper type.

### 11.2. `Runnable` Also Declares No Checked Exceptions

`Runnable.run()` is `void run()`, with no checked `throws`. Therefore, a lambda passed to `new Thread(() -> ...)` or `Executor.execute(Runnable)` faces a similar restriction to `Consumer`. In contrast, `Callable.call` allows `throws Exception`.

**However:** when submitting a `Callable` to `ExecutorService.submit` and retrieving the result with `Future.get()`, task failures are typically wrapped in `ExecutionException` (whose cause is the error from the task). Do not assume a checked `IOException` is automatically thrown directly from `Future.get()`. Each layer has its own exception contract.

## 12. Generic `E extends Exception` and Type Inference Limits

A custom interface can be written as:

```java
@FunctionalInterface
interface CheckedMapper<T, R, E extends Exception> {
    R map(T input) throws E;
}
```

Here `E` is a type variable representing **an exception family declared via a type parameter**. When an API owns the callback, it can propagate the checked obligation from the callback to the caller:

```java
static <T, R, E extends Exception> R convert(
        T value, CheckedMapper<T, R, E> mapper) throws E {
    return mapper.map(value);
}
```

However, keep several limitations in mind:

- `E` does not suddenly make `java.util.function.Function` declare checked exceptions.
- A generic parameter is a Java type, not a "union exception" syntax. For multiple checked exceptions without a narrow common subtype relationship, the API may need `throws Exception` or multiple type parameters/an appropriate design.
- Type inference is constrained by the call context and the lambda; in complex examples, check the inferred signature rather than assuming every call infers the narrowest subtype.
- Do not build an entire generic utility framework just to replace an easy-to-read `for` loop.
- Java does not have checked-exception polymorphism as an arbitrary "effect system"; `throws` rules remain tied to declared methods and interfaces.

### 12.1. Why Not Use `E extends Throwable` Arbitrarily?

Syntactically, a functional interface can declare `throws E` with `E extends Throwable`. However, widening to `Throwable` can force API callers to handle scenarios under `Error` or declare overly broad signatures that do not fit normal obligations. `E extends Exception` is usually more appropriate when the goal is supporting checked exceptions in application code.

## 13. Writing a General Adapter: Pros and Pitfalls

An internal library sometimes wants a generic adapter:

```java
@FunctionalInterface
interface CheckedFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}

static <T, R, E extends Exception>
java.util.function.Function<T, R> unchecked(
        CheckedFunction<T, R, E> source) {
    return input -> {
        try {
            return source.apply(input);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException(
                    "Callback thất bại", e);
        }
    };
}
```

These are **two illustrative declarations** that must be placed properly inside a class/interface. Mechanism:

1. `CheckedFunction` allows checked `E` to escape.
2. The adapter catches unchecked `RuntimeException` and **rethrows it as-is**.
3. The adapter catches remaining checked `Exception`s and wraps them in a `RuntimeException` with a `cause`.
4. The adapter's result has type `Function<T,R>` to pass to standard APIs.

However, this approach has drawbacks:

- After wrapping, the caller must handle the runtime wrapper, **and must not expect `IOException` directly**.
- A generic wrapper loses quick classification of checked exceptions without inspecting `getCause()`; a specialized adapter for `IOException` using `UncheckedIOException` may be better.
- `Exception` is a broad catch scope; you must decide whether to preserve existing `RuntimeException`s that represent other errors. The snippet above does so.
- Never use an adapter to silently swallow exceptions, or replace all errors with `null`/out-of-contract default values.
- If the API processes in parallel, the adapter must respect the callback's thread safety and manage side effects separately.

### 13.1. Do Not "Sneaky Throw" Just to Bypass the Compiler

There are generics/erasure tricks that allow throwing a checked exception through an API that does not declare it (*sneaky throw*). This can cause callers of `Function.apply` to unexpectedly receive a checked exception at runtime that the signature never let them anticipate.

In most applications, prefer the three contract-explicit approaches:

1. Catch and genuinely handle inside the callback.
2. Wrap in an unchecked exception with `cause` and accept the changed error-reporting contract.
3. Use an API/functional interface that allows checked exceptions, or a regular loop.

Compiler-bypassing tricks hurt readability, can complicate handling at the caller, and make unit tests/exception policies opaque.

## 14. Resources and `try-with-resources` in Lambdas

A lambda can open a resource and close it automatically with `try-with-resources`:

```java
Function<Path, String> load = path -> {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Không thể đọc dòng đầu", e);
    }
};
```

This is an **illustrative snippet** (requires importing `Path`, `Files`, `Function`, `IOException`, `UncheckedIOException`). Thanks to TWR, the reader is closed when leaving the callback. Because `Files.newBufferedReader(...)`, `readLine()`, and `close()` can all throw `IOException`, the callback catches and converts it to `UncheckedIOException`.

Points to watch out for:

- A lambda invoked multiple times may open/close many separate resources; consider performance and lifecycle.
- If both the reading body and `close()` fail, TWR preserves primary/suppressed exceptions per `Throwable` rules; the wrapper has `cause` set to the primary exception, so `getCause().getSuppressed()` can still be inspected.
- Do not pass a closed resource out of the callback and reuse it arbitrarily.
- If a callback returns a `Stream<String>` from `Files.lines(path)`, you must clearly design **who owns and closes the stream**; you cannot always close it immediately before the caller consumes the elements.
- `Files.lines` has checked `IOException` on open, and some subsequent read errors may be reported as unchecked I/O while the stream is consumed; understand the specific API contract.

### 14.1. Lazy Streams and Where I/O Errors Occur

A call supplying data to a Stream may not consume the file immediately. Closing the source too early or keeping the resource open indefinitely can cause errors at a later stage.

This is an **ownership/resource lifetime** issue alongside the callback's checked exception issue. Do not conclude that a `Function` adapter alone solves resource closing as well.

## 15. `CompletableFuture`: Different Callback, Different Contract

Methods such as `CompletableFuture.supplyAsync(Supplier<U>)` also accept a `Supplier` **that declares no checked exceptions**. Therefore:

```java
// INTENTIONALLY INVALID if readChecked() throws IOException:
java.util.concurrent.CompletableFuture.supplyAsync(
        () -> readChecked());
```

will hit the same checked constraint.

If converted to an unchecked wrapper inside the supplier, a failing `CompletableFuture` will complete **exceptionally**. When calling `join()`, the caller typically receives `CompletionException`, and must inspect the cause chain according to `CompletableFuture`'s contract. Do not assume `join()` throws checked `IOException` directly.

When using `get()` on `Future`/`CompletableFuture`, the API declares `ExecutionException` along with wait-related exceptions; continue distinguishing the **root error**, the **unchecked wrapper inside the callback**, and the **synchronization wrapper on the future**.

### 15.1. Implications for Retry Policies

A callback operation that partially wrote data before failing does not automatically become safe to retry just because it ran inside a future/stream. To retry, you must know whether the operation is idempotent or has appropriate transactions/compensation. Exception wrapping preserves diagnostics; it does not undo side effects.

## 16. When Should You Drop Streams/Lambdas and Write a Loop?

Sometimes the best answer is not to force checked I/O into `Function` or `Consumer`.

Example of reading multiple files and **reporting checked IOException directly**:

```java
static java.util.List<String> readAll(
        java.util.List<java.nio.file.Path> paths)
        throws java.io.IOException {
    java.util.List<String> results =
            new java.util.ArrayList<>();
    for (java.nio.file.Path path : paths) {
        results.add(java.nio.file.Files.readString(path));
    }
    return results;
}
```

This is a valid Java method placed inside a class. Advantages:

- The `throws IOException` signature reflects I/O failures.
- No adapter or wrapper is needed just to fit `Stream.map`.
- Iteration order and failure location are easy to read.
- You can control stopping on error, cleanup, and handling what has already completed.

**The downside is nothing to fear:** it takes a few more lines than a Stream, but the error contract is crystal clear. Prioritize readability and preserving semantics over "functional" syntax at all costs.

## 17. Comparing Approaches by Contract

| Need | Typically Suitable Approach | What to Avoid |
| --- | --- | --- |
| Error has a valid business fallback per element | `try/catch` directly inside the standard lambda | Returning an ambiguous sentinel and pretending it succeeded |
| Library API requires `Function`/`Consumer`/`Supplier` and cannot be changed | Wrap in unchecked with cause, or structured result if API supports it | Forcing checked exceptions through tricks |
| You control the API accepting the lambda | `ThrowingFunction`/`ThrowingConsumer`/`ThrowingSupplier` with `throws E` | Over-engineering complex abstractions without need |
| Task invoked as a `Callable` | Use `Callable.call() throws Exception` | Thinking `Callable` is a subtype of `Supplier` |
| Batch file read/write needing to propagate checked exceptions to caller | Regular `for` loop with `throws IOException` | Forcing a stream and swallowing errors |
| Stream pipeline reading files lazily | Design resource lifetime and terminal operation placement | Closing resources too early / failing to close them |
| Async supplier | Propagate error with cause, use future's exception policy | Expecting checked `IOException` to escape directly from `join()` |
| Processing multiple independent elements | Meaningful per-item results or error collection | Claiming all elements succeeded when some failed |

## 18. Common Mistakes

### 18.1. "Lambdas cannot throw exceptions"

False. Lambdas can throw unchecked exceptions, and can throw checked exceptions **if the target type's functional method allows it**, such as `Callable.call() throws Exception` or a custom `ThrowingFunction.apply() throws IOException`.

### 18.2. "Just add `throws IOException` to the enclosing method"

False if the checked exception is **inside a `Function.apply` callback** that declares no checked exceptions. The allowed exception set is determined by the target functional interface's method.

### 18.3. "When `Stream.map` contains I/O, Java automatically converts checked to unchecked"

False. The compiler rejects a callback with unhandled checked exceptions. Unchecked types appear only when you or a specific API explicitly wrap them.

### 18.4. "Use `Function<T,R>` with `throws E` in the generic type arguments"

False. Standard `Function` only has two type parameters T/R; it has no exception type parameter. You cannot write `Function<T,R,IOException>`.

### 18.5. "Method references are exempt from `throws` rules"

False. `Files::readString` undergoes checked exception checking against the target just like a lambda calling `Files.readString(path)`.

### 18.6. "Wrapping every exception as unchecked is always good"

No. It changes the caller's contract and can obscure error classification. Use it only when architecturally appropriate and preserve the cause, rather than turning every failure into a meaningless type.

### 18.7. "`UncheckedIOException` is for all checked exceptions"

False. `UncheckedIOException`'s constructor is for `IOException`. For `SQLException` or other checked exceptions, choose another appropriate wrapper/design.

### 18.8. "`Callable` can be passed directly for a `Supplier`"

False. They are independent interfaces, even though both return a value. Their abstract method signatures differ: `get()` vs `call() throws Exception`. An adapter with a clear exception policy is needed to convert between them.

### 18.9. "Switching to `parallelStream` will automatically solve `IOException`"

False. Parallelism does not change the target methods `Function.apply`/`Consumer.accept`. It also makes side effects and processing order harder to reason about.

### 18.10. "Exceptions in `map` occur immediately when writing `map(...)`"

Not necessarily. Streams are typically lazy: the callback runs when the terminal operation executes. Place handlers around the scope containing **the operation that actually consumes the pipeline**.

### 18.11. "Having a `catch` means all prior state was rolled back"

False. If a `Consumer` wrote/deleted files before an error occurred, prior side effects are not automatically undone. Checked/unchecked is only an error-reporting contract, not a transaction.

### 18.12. "Catching and returning `null` is neutral"

False. `null` can be mistaken for valid data, cause a `NullPointerException` far from the original error, or lose diagnostic details. Use a structured result, a valid fallback, or propagate the failure.

## 19. Frequently Asked Questions

### 19.1. Why didn't standard interfaces add `throws Exception` for convenience?

That was a standard library API design choice: most general-purpose callbacks were designed so they do not force every caller to handle a broad checked `Exception`. If `Function.apply` declared `throws Exception`, countless APIs and call sites using it would have to change signatures or catch errors, even when callbacks never do I/O.

This benefits many pure operations, though it is inconvenient when callback tasks have checked failures; Java lets you create specialized functional interfaces when needed.

### 19.2. Can you write `try/catch` outside `stream.map(...)`?

A `try/catch` outside alone **does not fix the lambda's compile-time error** if the lambda still lets a checked exception escape. First, the lambda must satisfy `Function.apply` by handling it internally, converting it to unchecked, or using another API. Then the outside can catch the unchecked wrapper when the terminal operation runs.

### 19.3. Can you attach `throws IOException` to the lambda itself?

Java lambda expressions have no syntax to declare `throws` like a standalone method declaration. They inherit their checked `throws` capability from the abstract method of the target functional interface.

### 19.4. How do you preserve the stack trace and root cause?

Wrap the error using a constructor that accepts a cause, such as `new UncheckedIOException("...", e)` or `new RuntimeException("...", e)`, and log the `Throwable` at the boundary. Do not keep only the message or replace the original error with a new message.

### 19.5. Is `ThrowingFunction` part of the standard JDK?

No. It is a common custom name; a project can define its own or use a helper library. Read the specific contract if using a third-party library, as different adapters wrap errors differently.

### 19.6. What is risky about using `Supplier` for lazy I/O?

Sometimes the caller invokes `get()` multiple times, potentially opening resources multiple times or triggering side effects repeatedly. `Supplier` **does not** promise memoization. If result caching is needed, build an explicit caching policy and resource lifecycle.

### 19.7. When should `Callable` be used?

When an API actually accepts `Callable`, or a task fits the `call() throws Exception` contract. Do not use `Callable` just to squeeze a callback into `Stream.map`, because `map`'s input type is `Function`.

## 20. Practice Exercises

### Exercise 1 — Identify the Compile Error

Read the three examples `InvalidFunction`, `InvalidConsumer`, and `InvalidSupplier`. For each example, write down the **target method** and which API declares checked `IOException`. Explain why adding `throws IOException` to the enclosing method does not solve it.

### Exercise 2 — Change the Target Type

Given the method `loadLength(String) throws IOException`, try assigning the method reference to `Function<String,Integer>` and `ThrowingFunction<String,Integer,IOException>`. Identify which one compiles and why.

### Exercise 3 — Fallback or Error Signal?

In `FunctionCatchInsideDemo`, suppose the value `-1` is also a valid length in a new model. Replace it with a result type that has an explicit success/failure status, or let the error propagate via a callback with checked `throws`.

### Exercise 4 — Wrapper and Cause

In `UncheckedFunctionAdapterDemo`, replace `new UncheckedIOException("...", e)` with `new RuntimeException(e.getMessage())`. Can the caller still retrieve the original `IOException` via `getCause()`? Why is this a diagnostic regression?

### Exercise 5 — Continue or Stop the Batch?

Run `ConsumerFailurePolicyDemo`. Change the handler from printing `FAILED` to throwing `UncheckedIOException` so the entire loop stops at the element `"bad"`. Predict whether the line `OK: two` still appears. Describe how to report batch failure to the caller.

### Exercise 6 — Using Callable

Run `CallableVsSupplierDemo`. Replace `Callable` with `Supplier` and have the lambda directly call `load(true)`. What issue does the compiler report? Compare `Callable.call` and `Supplier.get`.

### Exercise 7 — Lazy Streams

Create a `Stream<String>` with `map` using a `Function` that prints `"mapping X"` and returns the result. Without running a terminal operation, observe that the callback has not executed yet. Add `toList()` and explain when the callback runs.

### Exercise 8 — Loop Instead of Stream

Write a `readAll(List<Path>) throws IOException` method using a loop, then try the same logic using `stream().map(Files::readString).toList()`. Compare compilability, the caller's contract, and how `IOException` is preserved when you want to propagate it directly.

### Exercise 9 — Exceptions in CompletableFuture

Use `CompletableFuture.supplyAsync` with a supplier that wraps `IOException` into `UncheckedIOException`. Use `join()` and observe the `CompletionException`/cause chain per the API contract. Distinguish the callback's wrapper from the future's wrapper.

### Exercise 10 — Resource Management

Use `try-with-resources` inside a callback to open a reader, read, and close it. If the callback returns a lazy `Stream` reading from the same reader, explain why closing the resource before the stream is consumed is an ownership design bug.

## 21. Checklist Before Using Lambdas with I/O/SQL

- [ ] Have I identified whether the callback target is `Function`, `Consumer`, `Supplier`, or another interface?
- [ ] Have I read the target's **abstract method** signature to see if it declares checked `throws`?
- [ ] Am I avoiding expecting `throws IOException` on the enclosing method to automatically fix a contract-violating lambda?
- [ ] Do I recognize that both lambdas and method references obey the target's checked `throws`?
- [ ] When using `Stream.map`, do I know the lambda typically runs during the terminal operation?
- [ ] If catching inside the lambda, do I have a genuine recovery/fallback policy rather than hiding errors?
- [ ] If wrapping as unchecked, am I preserving the cause and avoiding redundantly wrapping `RuntimeException`?
- [ ] Have I chosen `UncheckedIOException` strictly for `IOException`?
- [ ] If defining a custom `ThrowingFunction<T,R,E>`, does the API accepting the callback fully declare `throws E`?
- [ ] Do I remember that a custom `ThrowingFunction` cannot be passed directly to `Stream.map` without an adapter?
- [ ] Have I considered a regular loop to keep checked `IOException` transparent?
- [ ] For a `Consumer` with side effects, do I know the state of already-processed elements when an error occurs?
- [ ] For a `Supplier`, do I know `get()` may be called multiple times and is not guaranteed to memoize?
- [ ] Do I distinguish `Supplier.get` from `Callable.call throws Exception`?
- [ ] When using futures, have I checked the exact exception contract of `join()`/`get()`?
- [ ] Are resources opened in a lambda closed at the right time, especially with lazy streams?
- [ ] Have I tested the success path, checked failure, wrapper cause, and post-error side effects?

**Conclusion:** `Function.apply`, `Consumer.accept`, and `Supplier.get` **do not declare checked `throws`**, so lambdas/method references assigned to them cannot let checked exceptions escape directly. There are three clear ways to handle this: **catch and handle inside the callback**, **convert to an unchecked wrapper with a cause**, or **choose/create a callback API that declares `throws`**; when needed, a regular `for` loop keeps checked I/O contracts clearer. The difference lies in the **functional interface's signature**, not a general limitation of Java lambda syntax.