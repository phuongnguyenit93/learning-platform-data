# Catching in a Lambda, Converting Exceptions, or Choosing a Custom Interface in Java

Lambdas allow passing behavior as a value, but they do not eliminate Java's **checked exception** mechanism. A call inside a lambda body can throw `IOException`, `SQLException`, `InterruptedException`, or another checked exception. Whether it is valid depends on the **functional interface used as the target type** and the `throws` clause on that interface's abstract method.

For example, `java.util.function.Function<T, R>` declares `R apply(T t)` **without `throws IOException`**. Therefore, you cannot directly assign a lambda calling a method that `throws IOException` to `Function<String, String>` and expect the compiler to ignore the exception. Nor can you simply add `throws IOException` to the enclosing method to fix every case: **the lambda body must be compatible with the exception contract of the functional interface itself**.

There are three main approaches:

1. **Catch in the lambda:** use `try-catch` inside the lambda body when you can recover or decide on an appropriate result locally.
2. **Convert the exception:** preserve the `cause` and wrap the checked exception in a meaningful unchecked exception—such as `UncheckedIOException` for I/O errors—when an API requires using `Function`/`Consumer` that does not declare `throws`.
3. **Choose a custom interface with `throws`:** create a `@FunctionalInterface` such as `ThrowingFunction<T,R,E extends Exception>` to preserve the checked exception in the signature; the method calling it must `catch` or `throws` according to the contract.

There is no single right choice for every case. This lesson presents the mechanism based on Java 17+, standalone examples with compile/run commands and stdout results, Stream API integration, lambda/method references, generic `throws E`, `InterruptedException`, common mistakes, and a design decision checklist.

## 1. A Lambda Has a Target Type, and That Type Determines Allowed Exceptions

A lambda such as `name -> read(name)` **has no standalone type independent of its context**. It must be assigned, passed, or cast to a suitable functional interface. The *function type* of the interface specifies the parameters, result, and checked exceptions allowed to escape from that behavior.

Example of two interfaces:

```java
@FunctionalInterface
interface SimpleLoader {
    String load(String key);
}

@FunctionalInterface
interface CheckedLoader {
    String load(String key) throws java.io.IOException;
}
```

These are **two valid illustrative interfaces** when placed in an appropriate scope. Both take a `String` and return a `String`, but they differ in their **exception-throwing contract**.

Suppose we have the method:

```java
static String read(String key) throws java.io.IOException {
    if ("bad".equals(key)) {
        throw new java.io.IOException("cannot read");
    }
    return "DATA:" + key;
}
```

When assigning:

```java
CheckedLoader allowed = key -> read(key); // Valid.
SimpleLoader invalid = key -> read(key);   // Does not compile.
```

This is **code placed in a class containing the `read` method above**, with the second line explicitly marked as an intentionally invalid example. `CheckedLoader.load` declares `throws IOException`, so the lambda is permitted to propagate this checked error to the caller. `SimpleLoader.load` does not declare any checked exceptions, so the lambda must handle or convert `IOException` before exiting its body.

### Common Standard Interfaces

| Functional interface / API | Abstract method | Allows user-declared checked exceptions? |
| --- | --- | --- |
| `Runnable` | `void run()` | No |
| `Supplier<T>` | `T get()` | No |
| `Consumer<T>` | `void accept(T t)` | No |
| `Function<T,R>` | `R apply(T t)` | No |
| `Predicate<T>` | `boolean test(T t)` | No |
| `BiFunction<T,U,R>` | `R apply(T t,U u)` | No |
| `Callable<V>` | `V call() throws Exception` | Yes; the interface allows `Exception` |
| Custom `ThrowingFunction<T,R,E>` | `R apply(T t) throws E` | Yes; type `E` is appropriately bounded |

The last column refers to **checked exceptions permitted to propagate through the contract**; it does not mean that interfaces without `throws` will never throw any errors. `RuntimeException` and `Error` are unchecked and can still occur at runtime.

## 2. Compile Error When Calling a Method With `throws` Inside a Lambda

The following code **intentionally does not compile**:

```java
import java.io.IOException;
import java.util.function.Function;

class InvalidLambda {
    static String load(String key) throws IOException {
        throw new IOException("file unavailable");
    }

    static void example() {
        Function<String, String> reader = key -> load(key);
        // Error: checked IOException is not handled inside the lambda.
    }
}
```

The reason is **not** that `Function` cannot represent an operation that fails, but that `Function.apply` **does not have `throws IOException`**. The compiler performs exception analysis on **the lambda body against the target function type** and rejects checked exceptions that could escape without being allowed.

Changing the enclosing signature to `static void example() throws IOException` **does not fix** the incompatibility between the lambda body and `Function.apply`. The lambda body is not executed immediately when the variable is declared; it will execute later when `reader.apply(...)` is invoked, possibly in an entirely different place. Therefore, Java cannot use the `throws` clause of the method **creating the lambda** in place of the `throws` clause of the **functional interface** method.

The same rule applies to method references:

```java
Function<String, String> reader = InvalidLambda::load;
// Also does not compile, because load(String) throws IOException.
```

A method reference is not a "way to bypass checked exceptions"; just like a lambda, it must be compatible with the target function type.

## 3. Approach 1: Catch the Exception Directly Inside the Lambda

If the error can be handled **properly and completely** right where the lambda runs, a `try-catch` inside the body is the most direct approach. For example, an event-accepting task might be allowed to log the failure of each individual event and continue accepting independent events.

Save as `LocalCatchDemo.java`:

```java
import java.io.IOException;
import java.util.function.Consumer;

public class LocalCatchDemo {
    static String load(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("source unavailable");
        }
        return "data:" + id;
    }

    public static void main(String[] args) {
        Consumer<String> consumer = id -> {
            try {
                System.out.println("accepted=" + load(id));
            } catch (IOException ex) {
                System.out.println("error=" + id + ":" + ex.getMessage());
            }
        };

        consumer.accept("ok");
        consumer.accept("bad");
        consumer.accept("next");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LocalCatchDemo.java
java LocalCatchDemo
```

Output:

```text
accepted=data:ok
error=bad:source unavailable
accepted=data:next
```

Explanation:

- `Consumer.accept` does not declare checked exceptions. However, **the lambda itself catches `IOException`**, preventing that checked error from escaping.
- The call with `bad` enters the `catch` block, prints the error, and finishes **the `accept("bad")` call normally**. Because `main` continues calling `accept("next")`, the example prints the final line.
- This approach is only valid when the business policy genuinely permits handling errors per item **locally**. For financial operations or state updates that must succeed as a whole, merely printing the error and treating it as handled can be very dangerous.
- A `catch` inside a lambda does not affect exceptions thrown from **another** `accept` call or tasks running on other threads.

**Do not use an empty `catch(Exception ex) { }`** just to make the compiler accept the lambda. That hides failures, causing incorrect or lost data without the caller knowing.

## 4. With `Function<T,R>`, a `catch` Must Decide on a Return Value

Unlike `Consumer.accept` which returns `void`, `Function.apply` must return a value of type `R` or terminate abruptly. If you catch the error and still want to return a value, choose a **valid fallback according to the contract**—do not automatically return `null` or an empty string.

Pattern placed inside a method:

```java
Function<String, String> safeReader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        return "verified-cache:" + key;
    }
};
```

This is an **illustrative pattern**, assuming `readChecked(String) throws IOException` is already defined and the `verified-cache` result is genuinely a valid fallback value. Not every read failure is suitable for a fallback: a cache may be stale, disallowed, or violate consistency.

If the policy requires **not continuing**, do not return a dummy value. In that case, converting to an unchecked exception with a cause or using an interface with `throws` makes the caller's responsibility clearer.

Another option is returning `Optional<R>` or a `Result<R,E>` to represent failure as data. Only use that option when it fits the API and error details need to be preserved; `Optional.empty()` may be insufficient if the caller needs to know **why** it failed.

## 5. Approach 2: Wrap `IOException` in `UncheckedIOException`

When an API only accepts `Function` or `Consumer`, yet you want to **stop processing and report the failure to the calling layer**, you can wrap the I/O exception in `java.io.UncheckedIOException`.

`UncheckedIOException extends RuntimeException` and takes an `IOException` as its **cause**. This is the appropriate type for I/O errors, not a general-purpose wrapper for all other checked exceptions.

Save as `UncheckedStreamDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Locale;
import java.util.function.Function;
import java.util.stream.Stream;

public class UncheckedStreamDemo {
    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("read failed");
        }
        return key.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Function<String, String> adapter = key -> {
            try {
                return read(key);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                        "cannot load " + key, ex);
            }
        };

        Stream<String> pipeline =
                Stream.of("one", "bad", "two").map(adapter);

        System.out.println("pipeline created");

        try {
            pipeline.forEach(value ->
                    System.out.println("value=" + value));
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause().getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 UncheckedStreamDemo.java
java UncheckedStreamDemo
```

Output with the sequential stream in the example:

```text
pipeline created
value=ONE
wrapper=cannot load bad
cause=read failed
```

Because `Stream.map` is a **lazy** operation, creating the pipeline does not execute `adapter.apply`. The error is only thrown when the terminal operation `forEach` is invoked.

The line `value=TWO` is not printed because upon reaching `bad`, the lambda throws `UncheckedIOException` and this sequential stream evaluation terminates with an exception. Do not use this output to claim that **every parallel stream** or pipeline with other operations will process/terminate in the exact same order; execution order and side effects must be considered separately.

The handler outside the terminal operation receives `UncheckedIOException`. It can inspect `ex.getCause()` to find the exact `IOException("read failed")`. **The cause is not lost**, unlike `throw new RuntimeException(ex.getMessage())` which only copies a string.

## 6. When Converting Checked to Unchecked, Design the Handling Boundary

Changing exception types merely to "dodge the compiler" is usually a poor choice. The decision is valid when **the API contract** forces a callback not to declare checked exceptions, yet the application still wants to classify failures at a higher boundary.

| Error source | Potentially suitable wrapper | Notes |
| --- | --- | --- |
| `IOException` when reading files, network, or streams | `UncheckedIOException(message, cause)` | Only accepts a non-`null` `IOException` |
| `SQLException` from a repository | Custom `DataAccessFailure extends RuntimeException` | Pass `SQLException` as cause; do not turn it into `UncheckedIOException` |
| Business checked exception | Custom unchecked exception **if the contract allows** | Do not lose the recovery semantics of the error |
| `InterruptedException` | Usually **propagate or restore the interrupt flag and terminate the task** | Do not treat as a normal error and continue |
| Any existing `RuntimeException` | Can be allowed to propagate | No need to re-wrap just because it is in a lambda |

Example of a custom wrapper:

```java
class DataAccessFailure extends RuntimeException {
    DataAccessFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a valid illustrative class without a standalone `main`. When catching an SQL error:

```java
catch (java.sql.SQLException ex) {
    throw new DataAccessFailure("Cannot load orders", ex);
}
```

This catch branch is an **illustrative snippet inside a lambda or method body** that can throw `SQLException`. By passing `ex` as the cause, the caller retains the original exception type, stack trace, and any suppressed exceptions attached to the cause object.

**Do not** use `new UncheckedIOException(new IOException(sqlException))` just to force an SQL error into an I/O error: it creates misleading diagnostic semantics and confuses upstream handling logic.

## 7. Approach 3: Create a Custom Functional Interface With `throws E`

When you **control the API that invokes the callback**, a custom interface is often better than forcing every lambda to wrap errors. You can declare:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

This is a valid functional interface:

- `T`: input type;
- `R`: result type;
- `E extends Exception`: the checked (or unchecked `Exception` subclass) type that the callback may throw;
- `apply(T) throws E`: a signature that allows the checked exception `E` to escape.

### Java 17+ Program: Preserving `IOException` Through a Custom Interface

Save as `CheckedFunctionDemo.java`:

```java
import java.io.IOException;

public class CheckedFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("file unavailable");
        }
        return "data:" + key;
    }

    static <T, R, E extends Exception> R invoke(
            T input, ThrowingFunction<T, R, E> function) throws E {
        return function.apply(input);
    }

    public static void main(String[] args) {
        ThrowingFunction<String, String, IOException> loader =
                CheckedFunctionDemo::read;

        try {
            System.out.println("value=" + invoke("ok", loader));
            invoke("bad", loader);
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 CheckedFunctionDemo.java
java CheckedFunctionDemo
```

Output:

```text
value=data:ok
caught=file unavailable
```

Analysis:

1. The method reference `CheckedFunctionDemo::read` is compatible with `ThrowingFunction<String,String,IOException>` because `apply` is permitted to throw `IOException`.
2. The generic method `invoke` declares `throws E`, allowing the original exception object to propagate out.
3. `main` catches the specific `IOException`. There is no need to create a new unchecked wrapper.
4. In the example, `loader` is passed as the custom interface, **not `Function<String,String>`**; even though the parameter/result types match, the two exception contracts are not automatically unified.

This is a suitable choice for callbacks in internal libraries, batch processing, or workflows where the caller genuinely has the responsibility to handle the checked exception.

## 8. Using a Custom Interface With the Stream API: Not Automatically Compatible

A common misconception:

```java
ThrowingFunction<String, String, IOException> loader =
        CheckedFunctionDemo::read;

// INVALID:
// Stream.of("a", "b").map(loader);
```

This is an illustrative snippet, assuming `ThrowingFunction` is already declared. The reason is not type erasure, but that **`Stream.map` requires `Function<? super T, ? extends R>`**, not a custom `ThrowingFunction`. The two interfaces are not the same type, and `Function.apply` itself does not declare `throws IOException`.

When you **do not control the signature of a standard API**, choose:

- **An adapter** from the throwing interface to `Function` with a transparent error-wrapping or error-representation policy.
- **Changing the processing flow** to a method that accepts `ThrowingFunction` if you have control over the API design.
- **Returning a result representing the error** for each element, if the policy does not want to stop the entire pipeline.

Do not try to cast `(Function<String,String>) loader`: two independent interfaces are not automatically compatible, and a cast does not alter the `throws` clause of the functional method.

## 9. Reusable Adapter: From `IOFunction` to `Function`

If many places in a project need to use Streams with I/O operations, you can centralize the wrapping logic in an adapter instead of duplicating `try-catch` in every lambda.

Save as `IoAdapterDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;
import java.util.stream.Stream;

public class IoAdapterDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IOFunction<T, R> checked) {
        return value -> {
            try {
                return checked.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("cannot read " + key);
        }
        return "loaded:" + key;
    }

    public static void main(String[] args) {
        Function<String, String> loader =
                unchecked(IoAdapterDemo::read);

        try {
            Stream.of("a", "bad", "c")
                    .map(loader)
                    .forEach(x -> System.out.println("value=" + x));
        } catch (UncheckedIOException ex) {
            System.out.println("io=" + ex.getCause().getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 IoAdapterDemo.java
java IoAdapterDemo
```

Output for the sequential pipeline:

```text
value=loaded:a
io=cannot read bad
```

Here, the callback that the adapter **receives** has the `throws IOException` contract; the callback that the adapter **returns** is a `Function<T,R>` that declares no checked exceptions. Thus, the wrapping step is performed **right at the type-conversion boundary**.

The adapter's policy is **fail fast**: an error from one element prevents the sequential pipeline from completing normally. If you need to collect all errors to report later, do not use this fail-fast adapter; instead, design a `Result` or a dedicated error collector.

**Limitation:** `IOFunction` and the adapter above only handle `IOException`. For `SQLException` or other checked exceptions, create an adapter matching the module's error contract; do not catch broad `Exception` and automatically wrap everything the same way.

## 10. Using `Result` to Retain Both Success Data and Per-Item Errors

When processing multiple independent records, the requirement is sometimes **not to stop the entire batch** when a single record fails. Catching the error and converting each outcome into a stateful value is more appropriate than wrapping the error and halting the stream.

Save as `ResultPipelineDemo.java`:

```java
import java.io.IOException;
import java.util.stream.Stream;

public class ResultPipelineDemo {
    record Outcome(String key, String value, IOException error) {
        boolean success() {
            return error == null;
        }
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("disk unavailable");
        }
        return "DATA-" + key;
    }

    public static void main(String[] args) {
        Stream.of("a", "bad", "c")
                .map(key -> {
                    try {
                        return new Outcome(key, read(key), null);
                    } catch (IOException ex) {
                        return new Outcome(key, null, ex);
                    }
                })
                .forEach(result -> {
                    if (result.success()) {
                        System.out.println("ok=" + result.key()
                                + ":" + result.value());
                    } else {
                        System.out.println("fail=" + result.key()
                                + ":" + result.error().getMessage());
                    }
                });
    }
}
```

```bash
javac -encoding UTF-8 ResultPipelineDemo.java
java ResultPipelineDemo
```

Output:

```text
ok=a:DATA-a
fail=bad:disk unavailable
ok=c:DATA-c
```

Here, the `Stream.map` lambda **does not throw any checked exceptions outward**; it always returns an `Outcome` for handled cases. The `Outcome` type holds a reference to the original `IOException`, so you can still inspect the stack trace, cause, and suppressed exceptions if needed.

`record` is a standard feature in Java 17, so the example requires no external Result library. In production systems, you should design clear invariants: each outcome must be **either a success or a failure**, never both at once; you can use a sealed hierarchy or factory methods instead of a public record constructor when needed.

The advantage of this approach is representing errors **as part of the result**. In return, downstream layers must proactively check the status; if `error` is ignored, failures can still be "swallowed" at the business layer.

## 11. `InterruptedException` in Lambdas Needs a Dedicated Policy

`InterruptedException` represents a cooperative interruption/cancellation signal in many APIs such as `Thread.sleep(...)`. You should not treat it like `IOException` and merely log it or wrap it as unchecked to let the task continue normally.

When an interface does not declare `throws InterruptedException`, two approaches are usually reasonable:

- If you can **change the interface contract**, choose a functional interface with `throws InterruptedException` and propagate the signal to the task-coordination layer.
- If forced to use `Runnable`, catch `InterruptedException`, **restore the interrupt flag** with `Thread.currentThread().interrupt()` when the API has cleared it, and then terminate the operation or execute the appropriate cancellation procedure.

Illustrative Java 17+ program, save as `InterruptLambdaDemo.java`:

```java
public class InterruptLambdaDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Runnable task = () -> {
            try {
                Thread.sleep(10_000);
                System.out.println("completed sleep");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("interruptFlag="
                        + Thread.currentThread().isInterrupted());
            }
        };

        Thread worker = new Thread(task);
        worker.start();
        worker.interrupt();
        worker.join();

        System.out.println("finished=" + !worker.isAlive());
    }
}
```

```bash
javac -encoding UTF-8 InterruptLambdaDemo.java
java InterruptLambdaDemo
```

Output under normal execution conditions:

```text
interruptFlag=true
finished=true
```

If the interrupt signal arrives **before the thread starts `sleep`**, the interrupt status is already set and `Thread.sleep` throws `InterruptedException`; if it arrives **during sleep**, it wakes the operation with that exception. Both paths enter the catch block, the flag is restored, and `Runnable.run()` finishes. `join()` makes `main` wait for `worker` to finish before printing the final line.

The example intentionally coordinates the worker with a single explicit interrupt and **does not illustrate a complete task cancellation system**. In real code, consider thread-stopping policies, resource cleanup, handling interruption while waiting, and executor shutdown.

**Do not throw `UncheckedIOException` for `InterruptedException`.** Besides having the wrong parameter type, it also misrepresents the cause/I/O contract.

## 12. `Callable` and `Runnable` Differ in Their Checked Exception Contracts

It is not always necessary to create your own functional interface. The standard library already provides `java.util.concurrent.Callable<V>`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

This is a simplified API signature for learning purposes. `Callable.call()` allows checked exceptions, whereas `Runnable.run()` does not. Therefore, a call that throws `IOException` can match the target type `Callable<String>`:

```java
Callable<String> task = () -> readChecked("profile");
```

This snippet illustrates usage inside a method where `Callable` is imported and `readChecked(String) throws IOException` exists. If you call `task.call()` directly, its signature is `throws Exception`, so the caller must catch or declare `Exception` accordingly.

If you submit a `Callable` to `ExecutorService.submit(...)`, checked exceptions thrown by the task are typically observed at `Future.get()` via `ExecutionException` whose cause is the error from the task. **Do not assume `Future.get()` will directly throw the `IOException` itself according to its signature.** `Future.get()` can also throw `InterruptedException` if the waiting thread is interrupted.

Conversely, `CompletableFuture.supplyAsync(...)` accepts a `Supplier<T>` which has no checked `throws`. Thus, switching from `Runnable` to `supplyAsync` does not automatically solve checked exceptions in a lambda. Depending on the API, you need an adapter/error wrapper or a different error-reporting mechanism. Asynchronous wrappers can surface `CompletionException` when accessing the result; inspect the cause chain rather than assuming all errors will appear as the exact same type.

## 13. Method References Must Follow the Same Rules as Lambdas

Suppose:

```java
static String read(String key) throws IOException { /* ... */ }
```

Then:

```java
ThrowingFunction<String, String, IOException> ok = MyClass::read;

// Function<String, String> invalid = MyClass::read;
```

This is an **illustrative pattern** using the class name `MyClass`, with `ThrowingFunction` already declared and properly imported. The first assignment is allowed because the interface accepts checked `IOException`. If you uncomment the second line, it will not compile because `Function.apply` does not declare `IOException`.

Method references are useful for concise syntax, **but they do not remove checked exceptions**. If there are overloaded methods, the compiler also performs overload resolution based on the target type of the method reference; changing the target type can affect which specific method is referenced. Check the actual signature rather than assuming every `MyClass::read` always maps to one method.

In the `CheckedFunctionDemo` program, the method reference `CheckedFunctionDemo::read` was used in a complete example with `throws IOException`.

## 14. Generics Help Preserve Checked Exception Types, but Do Not Create Generic Exception Classes

The declaration:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

is **completely valid**. The generic interface has a type parameter `E` to represent the exception type allowed to be thrown, **but the interface itself does not extend `Throwable`**.

Key distinctions:

- `<E extends Exception> ... throws E` in a generic method is valid per JLS §8.4.6.
- `catch (E ex)` where `E` is a type variable is invalid; a type variable cannot be used as an exception parameter type.
- `class GenericFailure<E> extends Exception` is invalid; Java prohibits a generic class from directly or indirectly extending `Throwable`.
- `ThrowingFunction<T,R,E>` can throw an instance of a **non-generic** exception class such as `IOException`, `SQLException`, or a custom `DataLoadException`.

If you need a callback that can throw **multiple independent checked exception types** in a single execution, a single type parameter `E` can sometimes make type inference less precise or force choosing a superclass such as `Exception`. You can define an explicit `throws IOException, SQLException` contract when those two types are a stable part of the API, or use a result-type-based design. Do not automatically force every callback into `throws Exception` if the caller needs to know precisely what can go wrong.

## 15. Three Different Policies When an Element Fails

For a batch containing keys `a, bad, c`, the exact same read error can lead to three different outcomes:

| Policy | How it is expressed | Effect |
| --- | --- | --- |
| **Continue after handling** | Catch in the lambda, record properly, and continue | Processes the next item; the error must be recorded per the contract |
| **Fail fast** | Convert to an unchecked exception with cause | Stops the current processing path when the exception propagates; higher layer receives the error |
| **Accumulate per-item failures** | Return `Result`/`Outcome` | Still produces results for independent items; caller classifies per-item errors |
| **Propagate checked** | Functional interface with `throws E` | Calling layer catches/declares `E`; commonly used when controlling the API |
| **Cancellation** | Propagate `InterruptedException` or restore interrupt and terminate | Signals a request to stop work without pretending success |

Do not rely on the `try-catch` structure alone to dictate the entire business policy. Catching an error is a **language mechanism**; continuing, retrying, skipping, wrapping, returning a result, or cancelling the task is an **application decision**.

For example, if each element writes data to a database and all elements share one transaction, catching `SQLException` and continuing can leave the transaction in an inconsistent state. If they are independent reads that can report per-item errors, `Result` may be suitable instead.

## 16. Avoid Broad Catches That Accidentally Swallow Runtime Errors

When writing a general adapter, the following approach is problematic:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (Exception ex) {
        return "";
    }
};
```

This is an **anti-pattern to avoid**. `catch (Exception)` catches many unrelated `RuntimeException`s such as `NullPointerException` or `IllegalStateException`, then replaces every error with an empty string. The caller cannot distinguish a valid empty string from a serious failure.

If the policy requires handling `IOException`, **catch `IOException` specifically**:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        throw new UncheckedIOException(
                "Reading key failed: " + key, ex);
    }
};
```

This is an illustrative snippet assuming `readChecked(String) throws IOException` exists and imports are declared. Preserving the cause helps diagnose where the error originated. If `key` contains sensitive data, do not include it directly in the message/log.

A generic `catch(Exception) { throw new RuntimeException(ex); }` adapter can hide both `InterruptedException` and runtime errors that did not need wrapping in the first place. Only use it if the API genuinely intends for all checked errors to be converted according to a documented policy, and design a separate path for cancellation/interruption.

## 17. Each Lambda Has Its Own `try-catch` Scope

Placing a `try-catch` around the statement **creating the lambda** does not mean it surrounds later execution:

```java
Function<String, String> reader;

try {
    reader = key -> readChecked(key); // Still a compile error.
} catch (RuntimeException ex) {
    // Not the place to handle checked IOException from the lambda body.
}
```

This is an **intentionally non-compiling** example, assuming `readChecked` throws `IOException`. Checked exceptions inside the lambda body do not propagate when the lambda is created, so a `try-catch` around the assignment cannot alter the contract of `Function.apply`.

If the lambda wraps the checked exception into an unchecked one, the caller can catch it when **invoking** the callback:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};

try {
    System.out.println(reader.apply("bad"));
} catch (UncheckedIOException ex) {
    System.out.println("failure=" + ex.getCause().getMessage());
}
```

These are two illustrative snippets inside a method body; imports and `readChecked` must be defined. In the Stream API, the invocation point is typically the terminal operation; with `ExecutorService`, the callback may run on a worker thread and the exception is surfaced through `Future`.

**You must distinguish between when a lambda is declared and when the callback is invoked.** Otherwise, you may catch errors in a scope that will never witness that exception.

## 18. Prefer Explicit API Contracts Over "Sneaky Throw"

Some code uses generic casts or type tricks to throw checked exceptions **as if** they were unchecked, often called *sneaky throw*. While such techniques exist, they obscure the contract: the calling layer does not see the real error type in `throws`, even though a checked exception can still appear at runtime.

For learning and building maintainable libraries, choose one of the three **explicit** mechanisms:

- An intentional `try-catch` that recovers directly inside the lambda.
- A meaningful unchecked wrapper with a cause, such as `UncheckedIOException` or a custom domain runtime exception.
- A custom functional interface with `throws E` where the caller manages the checked exception.

When a batch needs to continue, an `Outcome`/`Result` representing failure is also more transparent than hiding exceptions behind hard-to-read casts. Overusing `throws Exception` broadly or "hiding" checked exceptions does not make an application's error model more accurate.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assigning a lambda calling `throws IOException` to `Function<T,R>` without catching | Does not compile | Catch in the lambda, use an adapter/wrapper, or use an interface with `throws` |
| Adding `throws IOException` to the method *creating* the lambda | Does not change `Function.apply`'s contract | Handle according to the function type, not the assignment site |
| Switching to a method reference `Class::read` to "bypass checked" | Still must be compatible with the target type | Use a target interface that allows `throws` |
| Catching `Exception` and returning `null`/empty string for all errors | Hides failures and violates data contracts | Catch the exact type, define a valid fallback |
| Wrapping `IOException` in a runtime wrapper without the cause | Loses diagnostic trail | Pass `ex` as the cause |
| Using `UncheckedIOException` for `SQLException` | Violates error-type contract | Create an appropriate domain exception or wrapper |
| Returning `Optional.empty()` even though the caller needs the failure reason | Loses error type, message, stack trace | Return a `Result`/`Outcome` containing the error |
| Passing `ThrowingFunction` directly to `Stream.map` | Incompatible with standard `Function` | Use an adapter or a custom API accepting `ThrowingFunction` |
| Expecting `catch(IOException)` around Stream creation to catch errors from `map` | Lazy pipeline; errors occur during terminal operation | Place handling at the actual execution point |
| Catching `InterruptedException` and silently continuing | Can lose the cancellation signal | Propagate interrupt or restore flag and terminate |
| Re-wrapping every `RuntimeException` without adding meaning | Long chains, obscures error types | Let appropriate errors propagate |
| Using callbacks in a parallel stream and relying on sequential side effects | Order/completion may differ from assumptions | Design concurrency/ordering handling explicitly |
| Creating a custom generic exception `MyException<E>` | Java forbids generic subtypes of `Throwable` | Use a non-generic exception; put generics on the interface/result |
| Testing only the happy path | Fails to verify error policy and cause | Test failure paths, output lines, cause chains, and interrupts |

## 20. Decision Checklist

Before writing a lambda that calls a method with `throws`, ask yourself:

1. **What is the target type?** Does `Runnable`/`Function`/`Consumer` omit checked exceptions, or does `Callable`/a custom interface allow them?
2. **Which specific exception types can occur?** `IOException`, `SQLException`, `InterruptedException`, or a custom checked exception?
3. **Do you control the API receiving the lambda?** If so, consider an interface with `throws` to preserve the checked exception as-is.
4. **Can the error be validly recovered at the item level?** If so, catch locally with a clear fallback or recording mechanism.
5. **If not recoverable, must the pipeline/task stop?** You can wrap it in an unchecked exception with a cause and handle it at the boundary layer.
6. **Does the caller need a result for every element?** If so, consider `Result`/`Outcome` instead of throwing an error that stops the entire batch.
7. **Is the error an interrupt?** Propagate the signal or restore the interrupt status and terminate according to policy.
8. **Where is the lambda's execution path?** Direct call, Stream terminal operation, executor, or async callback? Place the catch where it can actually witness the error.
9. **Is the original information preserved?** Use `getCause()`, log the full `Throwable`, and preserve suppressed exceptions if the original error has any.
10. **Verify with the compiler and tests:** code that runs on the happy path does not prove the checked-exception path is right; compile against the target JDK and test failure scenarios as well.

### Quick Decision Table

| Situation | Tends to fit best |
| --- | --- |
| Callback is allowed to skip a failing record after recording it; records are independent | `try-catch` inside the lambda |
| `Stream.map` must stop when I/O fails and the caller is responsible | Wrap `IOException` in `UncheckedIOException`, preserving cause |
| Writing an internal API accepting a callback where the caller must handle checked exceptions explicitly | `ThrowingFunction<T,R,E>` / `ThrowingConsumer<T,E>` |
| Need to report success/failure individually for each item | `Result`/`Outcome` |
| Submitting a value-returning task with checked exceptions to an executor | `Callable<V>` and handle `Future.get()`/`ExecutionException` |
| Callback may be interrupted | `throws InterruptedException` contract or catch + restore flag and terminate |
| Library forces `Supplier<T>`/`Function<T,R>` | Transparent policy-based adapter; do not use sneaky throw |

## 21. Self-Check Questions

**Q1.** Why does `Function<String,String> f = x -> read(x);` not compile if `read` declares `throws IOException`?  
Because `Function.apply` does not declare `IOException`, so the lambda is not allowed to let this checked exception escape.

**Q2.** Is adding `throws IOException` to the method declaring variable `f` enough?  
**No.** Exception checking of the lambda body is based on the target function type, not the signature of the method creating the lambda.

**Q3.** What error type is `UncheckedIOException` used to wrap?  
**`IOException`.** It is an unchecked wrapper with a constructor taking an `IOException`, and its cause is preserved.

**Q4.** Does `Stream.map` run its callback immediately when called?  
**No.** `map` is a lazy intermediate operation; the callback is evaluated when an appropriate terminal operation is invoked.

**Q5.** Can `ThrowingFunction<String,String,IOException>` hold a method reference pointing to a method that `throws IOException`?  
**Yes**, because `apply` declares `throws IOException`.

**Q6.** Can `ThrowingFunction` be passed directly to `Stream.map`?  
**No**, because `map` requires standard `Function`; you need an adapter or a different API.

**Q7.** If you want to continue processing records after an individual failure while keeping the error intact, what can you use?  
A `Result`/`Outcome` containing either the success value or the exception object, then process each result.

**Q8.** How do `Callable.call()` and `Runnable.run()` differ regarding checked exceptions?  
`Callable.call() throws Exception`; `Runnable.run()` declares no checked exceptions.

**Q9.** Should you catch `InterruptedException` in a `Runnable`, merely log it, and ignore the stop request?  
**No.** You should propagate it if the contract allows, or restore the interrupt flag and terminate the task according to policy.

**Q10.** Does wrapping a checked exception in an unchecked one mean the exception has been "successfully handled"?  
**No.** That only **changes the propagation contract**. The layer receiving the wrapper still has to apply the actual handling policy.

## References

- [JLS Java SE 21 — §15.27.3, Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.27.3).
- [JLS Java SE 21 — §11.2.3, Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).
- [JLS Java SE 21 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6).
- [Java SE 21 API — `Function<T,R>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Function.html).
- [Java SE 21 API — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/UncheckedIOException.html).
- [Java SE 21 API — `Callable<V>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html).
- [Java SE 21 API — `Stream<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).

**Takeaway:** When a lambda can throw a checked exception, look at the **target functional interface**. Catch locally when you have a valid recovery policy; wrap in an unchecked exception **with cause** when a standard API prevents propagating checked exceptions and the caller needs to know about the failure; or use a **custom interface with `throws`** when you control the API and want to preserve the exact checked-exception contract. For multiple independent records, you can use `Result`/`Outcome` to represent errors as data instead of swallowing errors or forcing the entire pipeline to stop.
