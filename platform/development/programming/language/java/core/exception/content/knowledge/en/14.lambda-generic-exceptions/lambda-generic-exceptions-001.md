# Checked Exceptions in Lambdas Under Java's Function Type Contract

In Java, a lambda expression does not have its own `throws` list. Whether a lambda is allowed to let a **checked exception** escape depends on the **functional interface** to which the lambda expression is assigned or passed. More precisely, the compiler checks the exceptions that the lambda body can throw against the **`throws` clause of the function type/functional descriptor** of the target type.

This explains why **the same operation can compile when written as a `Callable` but fail to compile when written as a `Supplier`**, and why a method referenced with `::` that declares `throws IOException` sometimes cannot be used directly in `Stream.map`.

Key takeaways:

1. `Runnable.run()`, `Supplier.get()`, `Function.apply()`, and `Consumer.accept()` in the standard Java library **do not declare any checked exceptions**.
2. `Callable.call() throws Exception` allows the lambda body to throw checked exceptions that are subtypes of `Exception`.
3. You can define your own functional interface with `throws IOException` or a generic parameter `E extends Exception` if the caller needs to receive and handle checked errors.
4. If the target function type does not allow a checked exception, the lambda must **handle it inside its body** or **convert it to an error type permitted by the contract**, rather than adding `throws` after the `->` arrow.
5. Assigning a lambda to a different type does not change the nature of the error source; **the target type determines the compile-time checking contract**.

## 1. Distinguishing checked exceptions from unchecked exceptions

Java uses `Throwable` as the root of its exception hierarchy. For compile-time checking:

| Category | Examples | Must be caught or declared under checked exception rules? |
| --- | --- | --- |
| **Checked exception** | `IOException`, `SQLException`, `ParseException`, custom `Exception` not extending `RuntimeException` | Yes |
| **Unchecked exception** | `RuntimeException` and its subclasses such as `IllegalArgumentException`, `NumberFormatException` | No |
| **Unchecked `Error`** | `Error` and its subclasses | No; typically represents serious errors, not used for business validation |

Example source method:

```java
static String load(String key) throws java.io.IOException {
    if ("missing".equals(key)) {
        throw new java.io.IOException("source unavailable");
    }
    return "value:" + key;
}
```

This is an **illustrative method**. When calling `load(key)`, the calling code must satisfy the checked `IOException` contract: either place the call inside an appropriate `try-catch`, or be inside a method/lambda that is permitted to propagate that checked exception outward.

With lambdas, the difference is that **a lambda does not declare `throws IOException` using its own syntax**. It must rely on the functional interface of its context.

## 2. A lambda needs a functional interface as its target type

A **functional interface** is an interface with exactly **one abstract method according to the rules for determining a function type**, although it may also have `default`, `static`, or methods corresponding to `public` methods of `Object`.

Example:

```java
@FunctionalInterface
interface CheckedReader {
    String read(String key) throws java.io.IOException;
}
```

A matching lambda:

```java
CheckedReader reader = key -> {
    if (key.isBlank()) {
        throw new java.io.IOException("blank key");
    }
    return "value:" + key;
};
```

These are **illustrative declarations**, placed within a valid Java class/scope. The `key` parameter and the return value of the lambda are constrained by `CheckedReader.read(String)`. Because the abstract method declares `throws IOException`, the body can throw the checked `IOException`.

If we change the target type:

```java
java.util.function.Function<String, String> reader = key -> {
    if (key.isBlank()) {
        throw new java.io.IOException("blank key"); // Does not compile.
    }
    return "value:" + key;
};
```

The code above **intentionally does not compile**. `Function.apply(T)` does not have `throws IOException`. A lambda cannot introduce a new checked exception type outside the contract of the target function type.

### Lambdas do not have their own `throws` syntax

There is no valid Java syntax like the following:

```java
// Intentionally INVALID SYNTAX.
Function<String, String> reader =
        (String key) throws IOException -> load(key);
```

The `throws` declaration belongs to a **method** or **the abstract method of a functional interface**, not between the parameter list and the `->` arrow of a lambda.

You can write `throws` on the method containing the lambda if that method actually produces a checked exception in **its own** execution path, but doing so **does not** grant a lambda assigned to `Function` the right to throw `IOException`. Those are two different checking contracts.

## 3. What does a "function type" or "functional descriptor" contain?

When the compiler checks a lambda, it examines the target function type with the essential information:

- **Number and types of parameters**.
- **Return type**.
- **The types in `throws`** permitted by the function type.
- Constraints inferred from generic types, method type parameters, or the target type.

Example:

```java
@FunctionalInterface
interface Parser {
    int parse(String text) throws java.text.ParseException;
}
```

The expression:

```java
Parser parser = text -> {
    if (text.isBlank()) {
        throw new java.text.ParseException(
                "empty input", 0);
    }
    return text.length();
};
```

is valid because `Parser.parse(String)` declares `throws ParseException`. However, the exact same body, if assigned to `ToIntFunction<String>`, would be invalid if `ParseException` escapes unhandled, because `ToIntFunction.applyAsInt` declares no checked exceptions.

**Note:** Java does not force the lambda author to **actually** throw a checked exception declared by the target type. A lambda that throws no checked exceptions at all can still implement an interface that declares `throws IOException`.

## 4. Comparing common functional interfaces

| Functional interface | Functional method | Checked `throws` of the functional method |
| --- | --- | --- |
| `Runnable` | `void run()` | None |
| `Supplier<T>` | `T get()` | None |
| `Consumer<T>` | `void accept(T t)` | None |
| `Function<T,R>` | `R apply(T t)` | None |
| `Predicate<T>` | `boolean test(T t)` | None |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | None |
| `Callable<V>` | `V call() throws Exception` | `Exception` |
| Custom `CheckedReader` | `String read(String) throws IOException` | `IOException` |
| Custom `ThrowingFunction<T,R,E>` | `R apply(T) throws E` | Type parameter `E` per its bound |

The type names in the table belong to `java.lang.Runnable`, `java.util.concurrent.Callable`, `java.util.function`, or custom interfaces. You should not memorize a simplistic rule like "lambdas cannot throw checked exceptions": a lambda **can throw them** when the functional interface contract allows it.

### `Runnable` and `Callable` differ on checked exceptions

A lambda using `Runnable`:

```java
Runnable action = () -> {
    throw new java.io.IOException("I/O failed"); // Does not compile.
};
```

The `run()` method does not declare checked `IOException`.

The same idea with `Callable`:

```java
java.util.concurrent.Callable<String> action = () -> {
    throw new java.io.IOException("I/O failed");
};
```

The `Callable` snippet **is valid**: `call() throws Exception` allows `IOException`.

However, when the caller invokes `action.call()` through **the `Callable<String>` type**, the compiler sees `throws Exception`, so the caller must catch or declare the corresponding **`Exception`** type—it does not infer that this lambda only throws `IOException`.

## 5. Complete Java 17+ example: same operation, three handling contracts

The program does not need to read a real file; a simulated method throws checked `IOException` so the output is completely deterministic.

Save the entire contents into **`CheckedLambdaContractDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.Callable;
import java.util.function.Function;

public class CheckedLambdaContractDemo {

    @FunctionalInterface
    interface CheckedReader {
        String read(String key) throws IOException;
    }

    static String load(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("source unavailable");
        }
        return "value:" + key;
    }

    static void inspect(String key) {
        CheckedReader checked =
                CheckedLambdaContractDemo::load;

        try {
            System.out.println(
                    "checked=" + checked.read(key));
        } catch (IOException ex) {
            System.out.println(
                    "checked error=" + ex.getMessage());
        }

        Function<String, String> converted = value -> {
            try {
                return load(value);
            } catch (IOException cause) {
                throw new UncheckedIOException(
                        "cannot resolve " + value, cause);
            }
        };

        try {
            System.out.println(
                    "function=" + converted.apply(key));
        } catch (UncheckedIOException ex) {
            System.out.println(
                    "function error=" + ex.getMessage());
            System.out.println(
                    "function cause="
                    + ex.getCause().getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        inspect("ok");
        inspect("missing");

        Callable<String> task = () -> load("ok");
        try {
            System.out.println("callable=" + task.call());
        } catch (Exception ex) {
            System.out.println(
                    "callable error=" + ex.getClass().getSimpleName());
        }

        Runnable action = () -> {
            try {
                load("missing");
            } catch (IOException ex) {
                System.out.println(
                        "runnable handled=" + ex.getMessage());
            }
        };
        action.run();
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 CheckedLambdaContractDemo.java
java CheckedLambdaContractDemo
```

**Exact stdout:**

```text
checked=value:ok
function=value:ok
checked error=source unavailable
function error=cannot resolve missing
function cause=IOException
callable=value:ok
runnable handled=source unavailable
```

### Reading the three contracts

**`CheckedReader`:** the abstract method `read(String) throws IOException` allows a lambda or method reference to propagate checked `IOException` outward. A caller using `CheckedReader` catches `IOException` directly.

**`Function<String,String>`:** `apply` does not allow checked `IOException`. The lambda must catch the error inside its body; for example, wrapping the I/O error into `UncheckedIOException` and **preserving `cause`**. A caller of `Function` is not forced to have a `catch`, yet may still encounter the unchecked exception at runtime.

**`Callable<String>`:** `call() throws Exception` allows the method body to call `load` without catching `IOException` inside. However, the caller via `Callable` must handle `Exception` according to `call`'s declaration.

**`Runnable`:** `run()` has no checked `throws`, so the lambda must catch `IOException` itself. In the example, the action only prints an error line and does not rethrow, which demonstrates the syntax. In real systems, recovery/error-reporting decisions should not simply `println` and silently treat the task as successful.

**Important:** `UncheckedIOException` is appropriate when converting a checked I/O error to unchecked, because it requires an `IOException` as its cause. For non-I/O checked exceptions, choose another contract-appropriate wrapper; do not try to force every checked exception into `UncheckedIOException`.

## 6. The target type determines checked exceptions at lambda assignment time

A lambda representing a function call:

```java
() -> load("missing")
```

**does not have a standalone type like a regular `String` expression**. A lambda is checked in a target-type context when assigned to a variable, passed as an argument, or cast to a functional interface.

Example with the same expression:

```java
java.util.concurrent.Callable<String> c =
        () -> load("missing"); // Valid.

java.util.function.Supplier<String> s =
        () -> load("missing"); // Does not compile.
```

This is an illustrative snippet, assuming `load` is a method that throws `IOException`. `Callable.call` allows `Exception`; `Supplier.get` does not allow checked `IOException`.

### Can you add `throws IOException` to the enclosing method to fix it?

No, if the error is inside a lambda body assigned to `Supplier`:

```java
// Intentionally DOES NOT COMPILE.
static java.util.function.Supplier<String> build()
        throws java.io.IOException {
    return () -> load("missing");
}
```

`build()` only **creates and returns a lambda**; it does not execute the call to `load`. The `throws IOException` contract on `build` does not change `Supplier.get()`'s contract when the lambda is invoked later.

If you want to keep the checked exception for the caller to handle, change the **target type** to a functional interface with `throws IOException`. If you want to keep `Supplier`, handle or convert the error inside the lambda.

## 7. Method references `::` follow the exact same rules

It is not only lambdas of the form `x -> method(x)`; **method references** are also checked against the target functional interface.

Example:

```java
static String loadFile(String key) throws java.io.IOException {
    if (key.isEmpty()) {
        throw new java.io.IOException("empty key");
    }
    return key;
}
```

With a custom interface that allows `IOException`:

```java
@FunctionalInterface
interface CheckedLoader {
    String load(String key) throws java.io.IOException;
}

CheckedLoader good = Example::loadFile;
```

These are illustrative declarations, where `Example` is the class containing `loadFile`.

However:

```java
java.util.function.Function<String, String> bad =
        Example::loadFile; // Does not compile because IOException is checked.
```

The compiler message may mention `incompatible thrown types` or `unreported exception` depending on the context. The essence is identical to a lambda: **the target type's functional descriptor does not permit the checked exception type that the referenced call may throw**.

### You cannot "fix" a method reference with an arbitrary cast

Casting to `Function<String,String>` does not remove `IOException` from the source method. You must choose an appropriate function type or write a lambda adapter with a proper `try-catch`.

Switching to `Callable` does not solve every case either: `Callable` takes no parameters and returns a value; a method reference with a signature that accepts arguments only fits if the target type's parameter list can be mapped correctly.

## 8. Defining a generic functional interface with `E extends Exception`

In reusable libraries, a generic interface can describe a transformation operation with both input/output types and a **checked exception type**:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

The three type parameters mean:

- **`T`:** input type.
- **`R`:** output type.
- **`E`:** exception type allowed to be thrown, bounded to subtypes of `Exception`.

Example of a data-parsing method with a custom checked exception:

```java
final class ParseFailure extends Exception {
    ParseFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

ThrowingFunction<String, Integer, ParseFailure> parser =
        value -> {
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException cause) {
                throw new ParseFailure("invalid integer", cause);
            }
        };
```

This is an illustrative snippet and needs to be placed in an appropriate class/scope. `ParseFailure` is checked because it extends `Exception` without extending `RuntimeException`. `throws E` on the functional method allows the lambda to throw `ParseFailure` when `E` is instantiated to that type.

### `E` does not make Java catch the exception automatically

The caller still has to handle it:

```java
try {
    int value = parser.apply("12");
    System.out.println(value);
} catch (ParseFailure ex) {
    System.out.println(ex.getMessage());
}
```

Because the static type of `parser` carries `E=ParseFailure`, the compiler knows the specific checked exception type. This is one advantage of an interface with a generic exception parameter compared to simply writing `throws Exception` for all operations.

### Note when an operation has multiple checked exceptions

A single parameter `E` represents **one static exception type**. If code can throw two independent checked exceptions, such as `IOException` and `SQLException`, you cannot always express both precisely with just one `E` without widening to a common supertype like `Exception`.

Common options include:

- Defining the functional method with `throws IOException, SQLException` if that is the exact contract of the module.
- Translating errors into a custom checked exception at the abstraction layer and preserving `cause`.
- Using a typed result design if errors are a normal part of business logic.
- Accepting `E=Exception` if the library genuinely needs that level of generality, while understanding that callers will have to handle the broader type.

Do not force a generics design that erases the meaning of error types just to write a shorter API.

## 9. Adapting `ThrowingFunction` to `Function`: changing the contract, not erasing errors

`Stream.map` accepts `Function<? super T, ? extends R>`, meaning `Function.apply` **declares no checked exceptions**. If you have a `ThrowingFunction`, you cannot pass it directly to `map` just because it has the same parameter count.

You can write an adapter:

```java
static <T, R, E extends Exception>
java.util.function.Function<T, R> unchecked(
        ThrowingFunction<T, R, E> action) {

    return value -> {
        try {
            return action.apply(value);
        } catch (RuntimeException ex) {
            throw ex;
        } catch (Exception cause) {
            throw new IllegalArgumentException(
                    "conversion rejected", cause);
        }
    };
}
```

This is an **illustrative method** inside a class that defines `ThrowingFunction`. Its meaning:

1. The adapter takes a function **that may throw checked `E`**.
2. The inner lambda implements `Function.apply`, which has no checked `throws`.
3. If the source throws a `RuntimeException`, the adapter leaves that unchecked error as-is.
4. If the source throws a checked `Exception`, the adapter wraps it in `IllegalArgumentException` with `cause`.
5. The caller receives a regular `Function` and can pass it to `Stream.map`.

**Design warning:** `IllegalArgumentException` in the example is merely an illustrative choice for an input parse/convert operation. For I/O errors, you can use `UncheckedIOException`; for asynchronous operations or business errors, choose another wrapper type that matches the contract.

An adapter **does not make errors disappear**. It converts a checked error path into an unchecked error path; the application still needs to decide where to handle it at an appropriate boundary.

### Why catch `RuntimeException` before `Exception`?

A `RuntimeException` is also a subclass of `Exception`. If you only write `catch (Exception ex)` and wrap everything, the adapter could wrap programming bugs like `NullPointerException`, misleading investigation and changing the runtime type the caller expected.

Separating:

```java
catch (RuntimeException ex) {
    throw ex;
} catch (Exception cause) {
    throw new IllegalArgumentException(
            "conversion rejected", cause);
}
```

preserves unchecked errors intact and wraps only the remaining exceptions in the checked category. `Error` is not caught by these branches; avoid a broad `catch (Throwable)` just to "turn everything into success".

## 10. Complete Java 17+ example: custom generic function and `Stream.map`

Save the file **`ThrowingStreamAdapterDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class ThrowingStreamAdapterDemo {

    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static final class ParseFailure extends Exception {
        private static final long serialVersionUID = 1L;

        ParseFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static Integer strictPositive(String text)
            throws ParseFailure {

        final int number;
        try {
            number = Integer.parseInt(text);
        } catch (NumberFormatException cause) {
            throw new ParseFailure("not integer", cause);
        }

        if (number <= 0) {
            throw new ParseFailure("not positive", null);
        }
        return number;
    }

    static <T, R, E extends Exception> Function<T, R> unchecked(
            ThrowingFunction<T, R, E> action) {

        return value -> {
            try {
                return action.apply(value);
            } catch (RuntimeException ex) {
                throw ex;
            } catch (Exception cause) {
                throw new IllegalArgumentException(
                        "conversion rejected", cause);
            }
        };
    }

    static void runCase(String first, String second) {
        ThrowingFunction<String, Integer, ParseFailure> parser =
                ThrowingStreamAdapterDemo::strictPositive;

        Function<String, Integer> normal = unchecked(parser);

        try {
            List<Integer> values =
                    Stream.of(first, second)
                            .map(normal)
                            .toList();

            System.out.println("values=" + values);

        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "failed=" + ex.getMessage());
            System.out.println(
                    "cause=" + ex.getCause().getClass().getSimpleName());
            System.out.println(
                    "detail=" + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("2", "3");
        runCase("2", "abc");
        runCase("0", "4");
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ThrowingStreamAdapterDemo.java
java ThrowingStreamAdapterDemo
```

**Exact stdout:**

```text
values=[2, 3]
failed=conversion rejected
cause=ParseFailure
detail=not integer
failed=conversion rejected
cause=ParseFailure
detail=not positive
```

### Analyzing the success and failure paths

**`runCase("2","3")`:** the lambda as `ThrowingFunction` calls `strictPositive` twice, returning a valid `Integer` each time. The `Function` adapter throws no exception; `Stream.toList()` completes and prints `[2, 3]`.

**`runCase("2","abc")`:** `Integer.parseInt("abc")` throws unchecked `NumberFormatException`. `strictPositive` catches it and converts it to checked `ParseFailure("not integer", cause)`. The adapter catches `Exception` and wraps it into unchecked `IllegalArgumentException("conversion rejected", cause)`. The outer handler prints the direct cause as `ParseFailure` with message `not integer`. For deeper inspection, `ParseFailure.getCause()` is still `NumberFormatException`.

**`runCase("0","4")`:** `strictPositive("0")` parses the number `0`, but the rule requires a positive value, so it throws `ParseFailure("not positive", null)`. The stream stops due to the exception before completing the rest along the success path; the adapter wraps it and the caller receives the same wrapper type as above, but with a different cause message.

### Why can't you just write `Stream.of(...).map(parser)`?

`parser` has type `ThrowingFunction<String,Integer,ParseFailure>`. `Stream.map` requires a `Function`. The two interfaces are two **different Java types**, and the target `Function.apply` also does not allow checked `ParseFailure`. Having the same parameter/return shape does not make them the same type or give them the same error contract.

An adapter is an **intentional conversion** between two contracts. If the pipeline is large or error handling is complex, it may be better to move the checked parsing step outside the stream or use a structured result type.

## 11. Why can't you catch checked exceptions "outside the stream" if the lambda is invalid?

A common mistake is writing:

```java
// Intentionally DOES NOT COMPILE.
try {
    java.util.stream.Stream.of("a", "b")
            .map(value -> readFile(value))
            .toList();
} catch (java.io.IOException ex) {
    System.out.println("read failed");
}
```

Here `readFile(String)` is assumed to declare `throws IOException`. `Stream.map` still requires `Function.apply` not to throw checked `IOException`. **An outer handler does not make an invalid lambda valid.** The compiler must first check the lambda body independently against the functional descriptor.

The right approaches:

1. **Catch `IOException` inside the lambda**, returning a valid fallback or converting to an unchecked wrapper.
2. **Use a custom throwing function and an adapter** to make the policy explicit.
3. **Move the I/O operation outside the stream** into a loop method with `throws IOException`, if you want to preserve the checked error as-is for the caller.
4. **Use a result type** such as a record/sealed hierarchy to represent success/failure as data, if the pipeline needs to handle multiple failures without aborting mid-stream.

Do not use an outer `catch (IOException)` expecting the compiler to look through every lambda and automatically expand `Function.apply`'s contract.

### What error type can an outer handler catch after using an adapter?

If the adapter converts `IOException` to `UncheckedIOException`, the caller can catch `UncheckedIOException`. If the adapter converts `ParseFailure` to `IllegalArgumentException`, the caller can catch `IllegalArgumentException`.

The outer handler **does not automatically catch `ParseFailure`** just because it sits inside the wrapper's `getCause()`. Java selects `catch` blocks based on **the exception object actually thrown**, without traversing causes automatically.

## 12. Handling inside the lambda: meaningful fallbacks instead of swallowing errors

A syntactically valid approach:

```java
java.util.function.Function<String, Integer> parse = value -> {
    try {
        return Integer.parseInt(value);
    } catch (NumberFormatException ex) {
        return 0;
    }
};
```

`NumberFormatException` is unchecked, and the lambda returns `0` on error. In Java terms, there is no checked exception issue; however, **semantically**, both the valid string `"0"` and `"abc"` return `0`. If the caller needs to distinguish the two cases, this fallback **loses information**.

The same applies to checked `IOException`:

```java
java.util.function.Supplier<String> supplier = () -> {
    try {
        return readRequiredConfig();
    } catch (java.io.IOException ex) {
        return "";
    }
};
```

This is an illustrative snippet, assuming `readRequiredConfig()` declares `throws IOException`. The code compiles, but if the config is required and an empty string is still valid data, the caller has no idea an error occurred.

**Only choose a fallback when the contract truly permits recovery.** In another example, if data may be missing and the caller is allowed to use a verified default, a fallback can be a reasonable policy.

### Structured result types

You can define:

```java
sealed interface ReadResult
        permits ReadResult.Success, ReadResult.Failure {

    record Success(String value) implements ReadResult {}

    record Failure(String code, String message)
            implements ReadResult {}
}
```

This is **Java 17 illustrative code**, which can be placed in an appropriate file/class. A `Function<String,ReadResult>` can catch `IOException` internally and return `Failure`, allowing the pipeline to distinguish data from failure without throwing a checked exception out of `Function.apply`.

This design is useful when you need to aggregate **multiple error results** instead of letting the stream stop at the first failure. However, it also makes the data types richer; do not force every simple operation to use a sealed result.

## 13. Reading the static type of a function variable when calling it

Do not confuse **the lambda's body** with **the method signature the caller uses**.

Suppose:

```java
@FunctionalInterface
interface ReaderAction {
    String read() throws java.io.IOException;
}

ReaderAction action = () -> "cached";
```

This is an illustrative snippet. The lambda body does not throw any checked exception at all. Yet:

```java
String value = action.read(); // Must catch/declare IOException.
```

The compiler uses the static type `ReaderAction`, whose `read()` declares `throws IOException`. There is no compile-time mechanism that infers backward from a specific lambda implementation to remove the checked exception obligation when the caller uses the interface.

Conversely, if you use:

```java
java.util.function.Supplier<String> supplier = () -> "cached";
String value = supplier.get(); // Does not require IOException.
```

then the functional method declares no checked exceptions, so the caller is not forced to catch/declare `IOException` for this `get()` call.

This is similar to Java's overriding rules: the compiler enforces **the contract of the static type used at the call site**, rather than guessing every actual runtime implementation branch.

## 14. Generic lambdas do not automatically "erase" the exception contract

When using:

```java
ThrowingFunction<String, Integer, java.io.IOException> f =
        value -> {
            throw new java.io.IOException("read failed");
        };
```

the lambda is valid because `E` is `IOException`. Calling `f.apply("x")` requires handling or declaring `IOException`.

If changed to:

```java
ThrowingFunction<String, Integer, Exception> f =
        value -> {
            throw new java.io.IOException("read failed");
        };
```

the lambda is also valid, but a caller using this variable type sees the broader `throws Exception`. **The chosen generic exception type affects obligations at the call site.**

### Erasure and generic exception parameters

At runtime, generic type information for `E` is affected by *type erasure*. The compiler still uses `E` to check both the source and the caller at compile time, but you should not write runtime logic like:

```java
// Intentionally INVALID: cannot catch a type parameter E.
catch (E ex) {
    // ...
}
```

Java does not allow using a generic type variable `E` as the type in a `catch` clause like that. That is why many general-purpose adapters catch `Exception`, distinguish `RuntimeException` first, and handle the remaining checked exceptions according to the adapter's contract.

### Inference does not replace API design

In a generic method using `ThrowingFunction<T,R,E>`, the compiler can infer `E` from a lambda or method reference in specific circumstances. However, do not assume inference will always pick the exact checked exception types in a complex expression or automatically allow passing a throwing function to `Function`.

Where clarity matters, declare variables with an explicit type:

```java
ThrowingFunction<String, Integer, ParseFailure> parser =
        MyParser::parsePositive;
```

This is illustrative, with `MyParser.parsePositive` defined compatibly. An explicit type lets callers and reviewers immediately see which checked error type is permitted.

## 15. `Callable`'s `throws Exception` does not mean every task runs asynchronously

`Callable<V>` is a functional interface from `java.util.concurrent`. It allows `call() throws Exception`, but **the interface itself does not require a new thread**.

If you write:

```java
java.util.concurrent.Callable<String> task =
        () -> readRequiredConfig();

String result = task.call();
```

this is illustrative, with `readRequiredConfig` as a hypothetical checked `IOException` method. Calling `task.call()` directly runs synchronously on the current thread; the caller must handle/declare `Exception` per `Callable`'s type.

If submitted to an `ExecutorService`:

```java
java.util.concurrent.Future<String> future =
        executor.submit(task);

try {
    String result = future.get();
} catch (java.lang.InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable original = ex.getCause();
    // Handle/log according to the actual policy.
}
```

This is an **illustrative snippet**; the `executor` and `task` variables must be validly declared in the corresponding scope.

- `submit` dispatches the task to the executor.
- `Future.get()` can throw checked `InterruptedException` or `ExecutionException`; it does not directly throw every `IOException` that the `Callable` body threw.
- When the task fails, `ExecutionException.getCause()` typically points to the task's original exception.
- Interruption must be handled according to policy; for example, restoring the interrupt flag when not rethrowing `InterruptedException`.

Therefore, there are **two contracts** to distinguish: `Callable.call() throws Exception` on the task, and `Future.get()` when the caller retrieves the result from the executor.

## 16. `CompletableFuture` and async APIs also have their own boundaries

`CompletableFuture.supplyAsync` takes a `Supplier<U>`, and `Supplier.get()` **does not let checked exceptions escape**. Therefore:

```java
// Intentionally DOES NOT COMPILE if readRequiredConfig() throws IOException.
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(
                () -> readRequiredConfig());
```

You must catch or convert the error inside the lambda:

```java
java.util.concurrent.CompletableFuture<String> result =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> {
            try {
                return readRequiredConfig();
            } catch (java.io.IOException cause) {
                throw new java.io.UncheckedIOException(
                        "config read failed", cause);
            }
        });
```

This is an illustrative skeleton. When retrieving the result:

- `result.join()` may report failure with an unchecked `CompletionException`, carrying the relevant cause.
- `result.get()` uses the `Future` contract with checked `InterruptedException`/`ExecutionException`.
- Distinguish between the async infrastructure's wrapper error and the actual underlying exception in `getCause()`.

Merely writing `throws IOException` on the method that creates the `CompletableFuture` does not make `Supplier.get()` allow checked `IOException`.

### Do not assume the executor "catches every error for you"

The framework may hold onto a task's exception to be queried via `Future`. The fact that the caller does not see an exception thrown immediately at `submit` does not mean the work succeeded. Observe asynchronous status and results at the proper boundary.

## 17. Checked exceptions and `throws` when a functional interface inherits from multiple sources

A functional interface can inherit equivalent abstract methods through interface inheritance. Java determines the function type according to rules for signatures, return types, and the set of permitted checked exceptions.

Simple example:

```java
interface ActionA {
    void run() throws java.io.IOException;
}

interface ActionB {
    void run() throws java.sql.SQLException;
}

@FunctionalInterface
interface CombinedAction extends ActionA, ActionB {
}
```

This is a **valid illustrative skeleton** when two methods with the same signature can be merged into one functional method. However, a lambda implementing `CombinedAction` **cannot arbitrarily throw `IOException` or `SQLException`** just because each parent interface allows one of them. To satisfy **both contracts**, the set of checked exceptions permitted by the function type can be narrowed significantly; with two independent branches like in this example, the lambda cannot let either checked exception escape in a way that violates the other contract.

A lambda that throws no checked exceptions at all is the straightforward case:

```java
CombinedAction action = () ->
        System.out.println("combined action");
```

A subtle note is that the **inferred function type** may be stricter than a specific declaration in a parent interface. When a problem involves multiple combined interfaces or complex generics, verify the target type specification with the compiler instead of guessing that `throws` lists are simply summed together.

## 18. Adapters and the policy of preserving the cause

When converting a checked exception to unchecked to satisfy `Function`, the choice of wrapper should be deliberate:

| Original checked exception | A potentially suitable conversion | Condition to watch |
| --- | --- | --- |
| `IOException` | `UncheckedIOException(message, cause)` | `cause` must be an `IOException` |
| Business checked exception | Custom `RuntimeException(message, cause)` | Preserve business code and meaning |
| `SQLException` | A wrapper suited to the repository/service layer | Do not expose raw SQL details to clients |
| `ParseException` | A suitable validation exception | Do not turn every parse error into a system error |
| Already a `RuntimeException` | Usually rethrow if no context change is needed | Do not wrap pointlessly |

**Do not use `throw new RuntimeException(ex.getMessage())`** if you want to preserve the original cause type and stack trace. That constructor only takes a string and drops `cause`. Choose `new RuntimeException("context", ex)` or a specialized subtype when translating errors.

Example:

```java
try {
    return checkedOperation();
} catch (SomeCheckedException cause) {
    throw new DomainOperationException(
            "Cannot complete operation", cause);
}
```

This is an illustrative snippet with application-defined types/methods. What matters is **passing the `cause` object**, not just the message, and only changing the exception type at a genuinely meaningful boundary.

### Do not use "sneaky throw" to blindly bypass the compiler

Some libraries use generic tricks or special helpers to throw checked exceptions through APIs that do not declare `throws`. Although the runtime may allow the exception to be thrown, this technique **obscures the compile-time contract**, leaving callers of `Function` without guidance to catch the actual checked exception type.

If the educational goal or API requirement is to respect checked exceptions, prefer **a throwing functional interface that declares `throws`**, an explicit `try-catch`, or **a wrapper with `cause`**. Avoid using compiler-bypass tricks as a substitute for design.

## 19. `finally` and resources inside lambdas

A lambda can contain its own `try-with-resources`:

```java
java.util.concurrent.Callable<String> loader = () -> {
    try (var reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
};
```

This is an illustrative snippet with a valid `Path` variable `path`. Because `Callable.call() throws Exception`, the lambda is allowed to let checked `IOException` from opening, reading, or closing the resource escape. The resource is still closed before `call` actually returns, even if the body returns early or throws an error.

If you replace `Callable<String>` with `Supplier<String>` for the same body, it is invalid unless the checked `IOException` is handled or converted. **`try-with-resources` does not automatically eliminate checked exceptions** thrown while opening, reading, or closing.

Also:

- If the `try` body throws checked exception `E1` and `close()` throws `E2`, `try-with-resources` typically keeps `E1` as the primary exception and attaches `E2` as suppressed.
- If the `try` body is about to return a value but `close()` throws checked `IOException`, the return path can be replaced by an exception that the target functional interface contract must permit or a handler must handle.
- Do not return a stream or lazy iterator that depends on a closed resource from a lambda and assume the caller can use it normally.

## 20. Common compilation and design mistakes

| Misconception or error | Why it is wrong | How to handle it |
| --- | --- | --- |
| "Lambdas can never throw checked exceptions" | Depends on the functional descriptor's `throws` | Use an interface with checked `throws` |
| "A lambda declares `throws IOException` after `->`" | Java syntax does not support it | Put `throws` on the functional method |
| Assigning a lambda calling `Files.readString` directly to `Supplier` | `Supplier.get` does not declare `IOException` | Catch/wrap or use a custom interface |
| Adding `throws IOException` to the method that creates `Supplier` | Does not alter `Supplier.get`'s contract | Handle the error in the lambda or change the target type |
| Wrapping `Stream.map` in `catch(IOException)` expecting the lambda to throw | Violates checked exception rules inside `Function.apply` | Change the representation or use an adapter |
| Using `Callable` but the caller only catches `IOException` when calling `call()` | `Callable.call` declares `throws Exception` | Catch/declare `Exception` or use a narrower interface |
| Thinking method references ignore checked `throws` | They must also satisfy the target functional descriptor | Use an appropriate target type/adapter |
| Writing an adapter that catches every `Exception` and always wraps it | Can unnecessarily wrap `RuntimeException` | Keep unchecked errors as-is; intentionally wrap checked errors |
| Wrapping with a message without passing `cause` | Loses the link to the original error | Pass `Throwable cause` |
| Using `UncheckedIOException` for every checked exception | Its constructor/purpose is for `IOException` | Use a wrapper matching the original type |
| Using `catch (Throwable)` in a lambda and swallowing errors | Can hide serious `Error`s | Catch only errors the application can handle |
| Only printing the stack trace and returning a dummy value | Caller assumes the operation succeeded | Use real recovery or an explicit failure result |
| Equating creating a `Callable` with async execution | `Callable` is just an interface | Distinguish direct `call()` from `submit()` |
| Thinking `Future.get()` throws every exception from `call()` directly | `get()` typically uses `ExecutionException` | Inspect `getCause()` |
| Thinking a stream with `map` processes all elements before throwing | An exception can abort the pipeline | Consider a result type to aggregate errors |

## 21. Checklist for designing lambdas with checked exceptions

Before writing a lambda that calls a `throws` method:

1. **Identify the target type:** is it `Runnable`, `Supplier`, `Function`, `Callable`, or a custom interface?
2. **Read the functional descriptor:** what are the parameter types, return type, and actual checked `throws` list?
3. **Identify checked exception sources:** which calls can throw `IOException`, `SQLException`, or a custom checked exception?
4. **Compare against the descriptor's `throws`:** are the checked types escaping the body permitted?
5. **If not permitted**, is there a handling policy inside the lambda? Do not merely swallow errors or return a misleading fallback.
6. **If the caller needs to handle checked exceptions directly**, should you define a custom functional interface with explicit `throws`?
7. **If the API is fixed on `Function`/`Supplier`**, which adapter best expresses the intent of converting checked to unchecked?
8. **If a wrapper is created**, does it preserve `cause` and avoid accidentally wrapping unchecked errors that should pass through untouched?
9. **If using generics**, is `E` specific enough, or is it accidentally widening to `Exception` too broadly?
10. **If using a method reference**, are the source method and target type compatible in parameters, return type, and checked `throws`?
11. **If running in a stream**, is it understood that an error will abort the pipeline rather than automatically aggregating all errors?
12. **If running asynchronously**, how does the caller observe errors via `Future.get()`/`join()`?
13. **If the lambda manages resources**, are checked exceptions considered from initialization, the `try` body, and `close()`?
14. **Have both success and failure paths been compiled/tested?** Verify both compile-time errors from descriptors and runtime cause propagation.

## 22. Self-check exercises

**Exercise A — `Runnable` or `Callable`?**

```java
Runnable a = () -> {
    throw new java.io.IOException("failed");
};
```

Does this compile?

**No.** `Runnable.run()` does not declare checked `IOException`. With `Callable<Void>`, the lambda can throw `IOException` if parameter/return constraints also match.

**Exercise B — the same lambda under different types:**

```java
java.util.concurrent.Callable<String> c =
        () -> load("item");

java.util.function.Supplier<String> s =
        () -> load("item");
```

If `load(String) throws IOException`, which statement is valid?

**`Callable` is valid**, whereas `Supplier` is invalid if `IOException` is not handled inside the lambda.

**Exercise C — adding `throws` to the enclosing method:**

Can you simply add `throws IOException` to the method `createSupplier()` so that the lambda `() -> load()` can be assigned to `Supplier`?

**No.** Checking the lambda body still relies on `Supplier.get()`, not on `createSupplier()`'s `throws` clause.

**Exercise D — method reference:**

`ReadAction` has `read() throws IOException`. Can a method reference to `readFile() throws IOException` implement that interface?

**Yes**, if parameter and return types are also compatible. However, it does not automatically implement `Supplier`, which has no checked `throws`.

**Exercise E — generic exception:**

Does `ThrowingFunction<String,Integer,ParseFailure>` allow the caller to catch `ParseFailure` specifically?

**Yes.** The type `E=ParseFailure` is used at compile time for the functional method `apply`.

**Exercise F — does an adapter make checked exceptions disappear at runtime?**

**No.** An adapter may wrap a checked error into an unchecked wrapper; the caller can inspect the original error via `getCause()` if the adapter preserves the cause.

**Exercise G — `Future`:**

`Callable.call()` throws `IOException` when executed in an executor. Does `future.get()` necessarily throw `IOException` directly?

**No.** When the task fails, `get()` typically throws `ExecutionException`, and `getCause()` points to the original error.

**Exercise H — `catch` outside a stream:**

Does `try { stream.map(v -> readFile(v)).toList(); } catch (IOException ex) { ... }` allow the `Function.apply` body to throw `IOException`?

**No.** The lambda must satisfy `Function`'s descriptor first; an outer handler cannot fix that compile-time error.

**Exercise I — fallback:**

`Supplier` catches `IOException` and returns an empty string. Is that always the right handling?

**No.** It is only right if an empty string is a contract-permitted fallback. Otherwise, it hides failures and can mislead the caller.

**Exercise J — unchecked wrapper:**

Why is `new UncheckedIOException("context", cause)` preferable to `new RuntimeException(cause.getMessage())` for an `IOException`?

Because `UncheckedIOException` accurately represents the I/O source type and **preserves the `cause` object**, whereas copying only the message loses the original error's stack trace, cause chain, and suppressed exceptions.

## Conclusion

**Checked exceptions in lambdas are governed by the contract of the target function type, not by a `throws` list written on the lambda.** With `Runnable`, `Supplier`, `Function`, and standard functional interfaces without checked `throws`, the body must handle or convert checked errors. `Callable.call() throws Exception` and custom functional interfaces with `throws IOException` or `throws E` can allow propagating checked errors to the caller.

Distinguish between **the compile-time target type**, **the actual runtime exception**, and **how the system invokes the lambda** (directly, in a stream, via an executor, or via `CompletableFuture`). When an adapter is needed, preserve `cause` and express the error policy clearly. When the caller needs to handle a checked exception of a narrow type, use a **functional interface with the appropriate `throws` contract** rather than hiding errors, parsing messages, or trying to bypass compiler checks.