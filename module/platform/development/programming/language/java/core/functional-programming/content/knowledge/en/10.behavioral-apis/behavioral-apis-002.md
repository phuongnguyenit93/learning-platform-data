# Returning a Supplier or Function from a Method in Java

A Java method does not only return numbers, strings, or data objects. It can also return **behavior** through a functional interface, such as `Supplier<T>` or `Function<T,R>`. The caller receives an object representing an operation and then **decides when to invoke that operation**.

This is an important technique in functional programming and in designing APIs that accept or return behavior (*higher-order functions*): instead of fixing all logic at the definition site, a method can **produce rules, strategies, transformations, or tasks** tailored to configuration parameters.

Two core contracts in `java.util.function`:

- `Supplier<T>`: the functional method `T get()` **takes no input** and **returns a value** when called.
- `Function<T,R>`: the functional method `R apply(T input)` **takes an input** of type `T` and **returns a result** of type `R`.

Both are **functional interfaces**, so a method that creates them can return a lambda, a method reference, or an instance that implements the interface. They do not execute automatically when returned.

After this lesson, you will be able to:
1. Declare methods whose return type is `Supplier<T>` or `Function<T,R>`.
2. Return a lambda or method reference with a valid target type and call `get()` or `apply()` at the call site.
3. Design a factory that takes configuration parameters and **captures** those parameters in the returned behavior.
4. Distinguish between **creating a behavior object**, **evaluating configuration at creation time**, and **executing the lambda body at invocation time**.
5. Build pipelines using `Function.compose`/`andThen`, and understand mutable state, side effects, and common pitfalls.

## 1. What does returning a functional interface mean?

An ordinary method returns a value immediately:

```java
static String greetNow(String name) {
    return "Xin chào, " + name;
}
```

When `greetNow("Lan")` is called, string concatenation happens during that method call and returns a `String`.

Another method can instead return **a rule for producing a string when needed**:

```java
static java.util.function.Supplier<String> greeting(String name) {
    return () -> "Xin chào, " + name;
}
```

Calling `greeting("Lan")` returns a `Supplier<String>`. At this point, the body `() -> ...` has not yet run to build the greeting; the recipient calls `get()` when they want the result:

```java
java.util.function.Supplier<String> supplier = greeting("Lan");
String message = supplier.get(); // "Xin chào, Lan"
```

The three snippets above are **illustrative code fragments assembled by context**: the two `static` methods belong to a class, while the assignment belongs in a calling method. Do not place `static` method declarations inside `main`.

**Make the distinction:** a `Supplier<String>` is an object that can produce/return a `String`, not a `String` itself. Similarly, a `Function<String,Integer>` is a rule for converting a `String` to an `Integer`, not a precomputed integer.

## 2. Structure of a method returning Supplier<T>

Basic pattern:

```java
static java.util.function.Supplier<Integer> answerFactory() {
    return () -> 42;
}
```

`answerFactory()` does not need to return `42` directly. It returns a lambda compatible with `Supplier<Integer>`. The method's declared return type provides the **target type** for the lambda in the `return` statement.

Call site:

```java
java.util.function.Supplier<Integer> answer = answerFactory();
System.out.println(answer.get()); // 42
```

**A Supplier has no parameters at the time `get()` is called.** However, a factory method can certainly accept parameters to **configure** the Supplier:

```java
static java.util.function.Supplier<String> repeatLater(String word) {
    return () -> word + word;
}
```

For example, `repeatLater("Hi").get()` returns `"HiHi"`. The parameter `word` belongs to the `repeatLater` call and is **captured** in the returned lambda. Each call to the factory with a different argument can produce different behavior.

Useful use cases for `Supplier<T>` include: creating values on demand, providing fallbacks, acting as a parameterless factory for an object, encapsulating data reads, and passing an unevaluated computation into an API.

### Supplier does not mean cache

`Supplier<T>` does not by default compute once or memoize its result. If `get()` calls an expensive method or reads changing state, each call to `get()` may redo the work or return a different result. If you want memoization/caching, you must design it explicitly and consider synchronization when used across multiple threads.

## 3. Structure of a method returning Function<T,R>

Example creating a transformation that adds a prefix to a string:

```java
static java.util.function.Function<String, String> prefixer(String prefix) {
    return value -> prefix + value;
}
```

`prefixer("ID-")` does not return `"ID-123"` directly, because at factory creation time there is no `value` input yet. It returns a `Function<String,String>`, and the caller supplies the data later:

```java
java.util.function.Function<String, String> withId = prefixer("ID-");
String output = withId.apply("123"); // "ID-123"
```

The target type `Function<String,String>` is declared on the factory method. Therefore, the compiler infers `value` as `String` and verifies that the string concatenation result is compatible with `String`.

Another example using a numeric parameter:

```java
static java.util.function.Function<Integer, Integer> add(int offset) {
    return number -> number + offset;
}
```

`add(5).apply(7)` returns `12`. `offset` is the captured configuration; `number` is the new input supplied on each `apply` call. This is the distinction between **configuration parameters at Function creation time** and **processing parameters at Function execution time**.

In heavy computations with primitive `int`, you can use `IntUnaryOperator` (`int applyAsInt(int)`) instead of `Function<Integer,Integer>` to avoid boxing/unboxing. This lesson uses `Function` to highlight behavior-returning APIs.

## 4. Complete Java 17 example: factories returning Supplier and Function

Create the file **`BehaviorFactoryDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

public class BehaviorFactoryDemo {

    static Supplier<String> greeting(String name) {
        String safeName = name == null ? "bạn" : name.strip();
        return () -> "Xin chào, " + safeName;
    }

    static Function<String, String> withPrefix(String prefix) {
        String safePrefix = prefix == null ? "" : prefix;
        return text -> safePrefix + text;
    }

    static Function<Integer, Integer> add(int offset) {
        return number -> number + offset;
    }

    static <T> Supplier<T> constant(T value) {
        return () -> value;
    }

    public static void main(String[] args) {
        Supplier<String> hello = greeting("Lan");
        Function<String, String> withId = withPrefix("ID-");
        Function<Integer, Integer> plus5 = add(5);
        Supplier<Integer> fortyTwo = constant(42);

        System.out.println(hello.get());
        System.out.println(withId.apply("007"));
        System.out.println(plus5.apply(3));
        System.out.println(fortyTwo.get());

        Function<String, String> trimmed = String::strip;
        Function<String, String> normalizedId =
                trimmed.andThen(withPrefix("USER:"));
        System.out.println(normalizedId.apply("  Mai  "));

        Supplier<String> anonymous = greeting(null);
        System.out.println(anonymous.get());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 BehaviorFactoryDemo.java
java BehaviorFactoryDemo
```

**Exact stdout:**

```text
Xin chào, Lan
ID-007
8
42
USER:Mai
Xin chào, bạn
```

Explanation:

1. `greeting("Lan")` returns a `Supplier<String>`; the lambda body executes when `hello.get()` runs.
2. `withPrefix("ID-")` returns a `Function<String,String>`; `apply("007")` uses both the captured prefix and the new argument.
3. `add(5)` creates a configured addition operation; `apply(3)` returns `8`.
4. `constant(42)` is a generic factory `<T> Supplier<T>`; Java infers `T` as `Integer` at this assignment.
5. `trimmed.andThen(withPrefix("USER:"))` builds a pipeline: `String::strip` runs first, then the prefix is added; the input `"  Mai  "` is transformed into `"USER:Mai"`.
6. `greeting(null)` chooses the default name `"bạn"` **when creating the Supplier**, and the lambda later uses the `safeName` value.

Note that `String::strip` has been available since Java 11; Java 17 supports it fully. The null-handling snippets in this example are intentional; any other API should clearly specify its own null policy.

## 5. When is behavior created, and when is it executed?

When calling a factory like:

```java
static Supplier<String> makeLabel(String raw) {
    String trimmed = raw.strip();
    return () -> trimmed.toUpperCase(java.util.Locale.ROOT);
}
```

there are **two points in time**:
1. When `makeLabel("  java  ")` is called, the method runs immediately; `raw.strip()` produces `trimmed = "java"`, and then returns a lambda.
2. When `get()` is called on the received Supplier, the lambda body runs `toUpperCase` and produces `"JAVA"`.

Not every expression inside the factory is deferred. Only the **lambda body** waits until the functional method is called; computation outside the lambda body still happens during behavior creation.

Similarly, with `Function`, configuration parameters can be normalized immediately at creation time, while the `apply(input)` argument arrives later.

### Runnable example: logging to confirm the order

Create the file **`DeferredExecutionDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

public class DeferredExecutionDemo {

    static Supplier<String> delayedMessage(String name) {
        System.out.println("Tạo Supplier cho " + name);
        return () -> {
            System.out.println("Chạy Supplier");
            return "Hello " + name;
        };
    }

    static Function<Integer, Integer> multiplyBy(int factor) {
        System.out.println("Tạo Function nhân " + factor);
        return number -> {
            System.out.println("Chạy Function với " + number);
            return number * factor;
        };
    }

    public static void main(String[] args) {
        Supplier<String> message = delayedMessage("Lan");
        Function<Integer, Integer> times3 = multiplyBy(3);

        System.out.println("Đã tạo hành vi");
        System.out.println(message.get());
        System.out.println(times3.apply(4));
        System.out.println(message.get());
    }
}
```

Run:

```bash
javac -encoding UTF-8 DeferredExecutionDemo.java
java DeferredExecutionDemo
```

**Exact stdout:**

```text
Tạo Supplier cho Lan
Tạo Function nhân 3
Đã tạo hành vi
Chạy Supplier
Hello Lan
Chạy Function với 4
12
Chạy Supplier
Hello Lan
```

Here, the two `"Tạo ..."` lines appear before `"Đã tạo hành vi"` because the code outside the lambda body in the factory executes **immediately**. `"Chạy Supplier"` appears **twice** because `get()` is called twice. The `Function` runs only once because `apply(4)` is called only once.

**Do not equate returning a lambda with asynchronous execution.** Both examples above run on the thread that calls `get()`/`apply()`; they do not create a thread, task scheduler, or Future. If asynchronous execution is needed, the API invoking the behavior must actually provide a mechanism such as `ExecutorService` or `CompletableFuture`.

## 6. Captured variables: final and effectively final

A returned lambda often needs to remember configuration from parameters or local variables in the factory method:

```java
static Function<Integer, Integer> addTax(int tax) {
    int normalizedTax = Math.max(tax, 0);
    return amount -> amount + normalizedTax;
}
```

`tax` is read to compute `normalizedTax`, and `normalizedTax` is an **effectively final** local variable because it is never reassigned. Java allows a lambda to capture a local variable or parameter when that variable is `final` or **effectively final**. They remain available to the lambda after the factory call has finished.

You cannot reassign a captured local variable:

```java
// INTENTIONALLY DOES NOT COMPILE:
static Function<Integer, Integer> broken(int offset) {
    Function<Integer, Integer> operation = x -> x + offset;
    offset++; // offset is no longer effectively final
    return operation;
}
```

The fix is to compute the new configuration into a local variable that is assigned once:

```java
static Function<Integer, Integer> corrected(int offset) {
    int adjusted = offset + 1;
    return x -> x + adjusted;
}
```

Note: **`final` locks reassignment of the reference variable, not the immutability of the object**. For example, a factory can capture a `List` or an `AtomicInteger` and observe its state changing over time. If an API needs pure behavior with stable results, snapshot the necessary data before returning the lambda.

## 7. Snapshots and mutable state when returning a Supplier

Two suppliers can read from the same source using different strategies:
- **Snapshot:** take the value once when creating the factory, then return the stored value.
- **Live view:** hold a reference to the mutable object and read its state on every `get()`.

Create the file **`SupplierStateDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SupplierStateDemo {

    static Supplier<String> snapshot(StringBuilder source) {
        String captured = source.toString();
        return () -> captured;
    }

    static Supplier<String> live(StringBuilder source) {
        return source::toString;
    }

    static Supplier<Integer> nextSequence(AtomicInteger counter) {
        return counter::incrementAndGet;
    }

    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        Supplier<String> frozen = snapshot(source);
        Supplier<String> current = live(source);

        System.out.println("Trước: " + frozen.get() + "/" + current.get());
        source.append("B");
        System.out.println("Sau: " + frozen.get() + "/" + current.get());

        Supplier<Integer> next = nextSequence(new AtomicInteger(10));
        System.out.println("Số tiếp: " + next.get());
        System.out.println("Số tiếp: " + next.get());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SupplierStateDemo.java
java SupplierStateDemo
```

**Exact stdout:**

```text
Trước: A/A
Sau: A/AB
Số tiếp: 11
Số tiếp: 12
```

`frozen` captures an immutable `String` created at the time `snapshot` is called. `current` holds the `source` receiver for the method reference `source::toString`, so it sees updated content. `next` holds an `AtomicInteger` and calls `incrementAndGet` on each `get()`, producing an incrementing sequence.

`AtomicInteger` supports atomic operations on its numeric value, but **does not make arbitrary multi-variable logic thread-safe**. `StringBuilder` is not safe for concurrent reads/writes across multiple threads without proper coordination. The example above runs sequentially, so stdout is deterministic.

Do not confuse a factory returning `Supplier<T>` with a factory that always returns a new object: a `Supplier` may return the same instance, a snapshot, a fresh value each time, or a value read from current state. The **business contract** must make this behavior clear.

## 8. Composing returned Functions into pipelines

`Function<T,R>` has default methods for combining transformations:
- `andThen(after)`: runs the current Function **first**, then runs the `after` Function.
- `compose(before)`: runs the `before` Function **first**, then runs the current Function.
- `Function.identity()`: returns a Function that leaves its input value unchanged.

Example:

```java
Function<String, String> strip = String::strip;
Function<String, String> prefix = text -> "ID:" + text;

Function<String, String> a = strip.andThen(prefix);
Function<String, String> b = prefix.compose(strip);
```

This is an **illustrative code fragment**; it requires `import java.util.function.Function;` and must be placed inside a method. For the same input, both `a` and `b` strip first and add the prefix afterward. The new `Function` created by `andThen`/`compose` is still unevaluated behavior; the chain of transformations only runs when `apply(input)` is called.

A factory that builds a pipeline:

```java
static Function<String, String> createNormalizer(String prefix) {
    Function<String, String> strip = String::strip;
    Function<String, String> upper =
            text -> text.toUpperCase(java.util.Locale.ROOT);
    Function<String, String> decorate =
            text -> prefix + text;
    return strip.andThen(upper).andThen(decorate);
}
```

With `createNormalizer("CODE:").apply(" java ")`, the result is `"CODE:JAVA"`. `prefix` is captured when `decorate` is created; the `andThen` expression constructs the composed Function without running the transformation on `" java "` before `apply` is called.

**Order matters.** Changing `upper.andThen(decorate)` to `decorate.andThen(upper)` can alter the prefix itself. When transformations have side effects or wrap checked exceptions, order also affects observable behavior.

## 9. Designing behavior-returning APIs: static factories, instance methods, and generics

Using `static` is not mandatory; an instance method can return a Supplier or Function and read the object's fields:

```java
class TextService {
    private final String prefix;

    TextService(String prefix) {
        this.prefix = prefix;
    }

    java.util.function.Function<String, String> formatter() {
        return value -> prefix + value;
    }
}
```

This snippet is a valid class; inside a calling method, you can write:

```java
TextService service = new TextService("TAG-");
java.util.function.Function<String, String> format = service.formatter();
String output = format.apply("1"); // "TAG-1"
```

A lambda can access fields through the enclosing instance. The `final`/`effectively final` rule applies to captured local variables and parameters, **not requiring every field accessed by a lambda to be final**. However, mutable fields can make the result depend on state at the time `apply` is called; make sure your API clearly specifies whether it captures a snapshot or reads live state.

With generics, a factory can be reused across many types:

```java
static <T> Supplier<T> constant(T value) {
    return () -> value;
}
```

For example, `Supplier<String> a = constant("Java");` and `Supplier<Integer> b = constant(10);` are both valid. Specifying an explicit return type helps callers know they are receiving **behavior** rather than direct data.

You cannot declare a method as `var make() { ... }` to infer its return type; `var` is for certain local type inference contexts, not as a replacement for method return types. In addition, declaring `var f = () -> 42;` is **intentionally invalid** because a standalone lambda needs a target type. In `return () -> 42;` inside a method with return type `Supplier<Integer>`, the return type itself provides the target type, making the expression valid.

## 10. Choosing Supplier or Function?

| Problem | Choice | Reason |
| --- | --- | --- |
| Produce a value on demand with no new arguments | `Supplier<T>` | The caller simply invokes `get()`. |
| Return a rule to transform an input provided later by the caller | `Function<T,R>` | The caller invokes `apply(input)`. |
| Return a true/false condition for an input | `Predicate<T>` | `test(input)` expresses a boolean check more clearly. |
| Return an action with no input and no result | `Runnable` | `run()` is simple and in `java.lang`. |
| Return an action that takes an input and produces no result | `Consumer<T>` | `accept(input)`. |
| Return a transformation with two arguments | `BiFunction<T,U,R>` | `apply(left,right)`. |
| Return a factory that may throw a checked exception | `Callable<T>` or an appropriate custom interface | `Callable.call()` declares `throws Exception`; do not force Supplier to throw checked exceptions. |

Choosing the interface by its semantic meaning avoids code like `Function<Void,T>` to simulate a no-input action: `Supplier<T>` is usually more appropriate, because `Function<Void,T>` still has a functional method taking a `Void` argument and requires calling `apply(null)` if used that way.

There is also no need to invent a new functional interface when standard types already express the contract. Conversely, if an API needs domain-specific semantics, custom checked exceptions, multiple parameters, or domain-meaningful default methods, you can define a custom interface and return it.

## 11. Exceptions, null, and resource safety

### 11.1. Checked exceptions

`Supplier.get()` and `Function.apply()` do not declare checked exceptions. If a lambda body calls an API that throws `IOException`, the compiler requires catching and handling it (or translating it into an appropriate unchecked exception), or using an interface with a suitable `throws` contract.

**Do not** use a lambda with a broad catch that silently swallows errors just to force the signature to fit `Supplier` or `Function`; behavior must report errors clearly according to the API contract.

### 11.2. Null

Java does not automatically guarantee that a Supplier will not return null or that a Function will not receive null. For example:

```java
static java.util.function.Function<String, String> safeUpper() {
    return value -> value == null
            ? ""
            : value.toUpperCase(java.util.Locale.ROOT);
}
```

This is a valid method declaration fragment; an application may choose a different policy such as `Objects.requireNonNull(value)`. What matters is documenting the contract: whether null is allowed, what a null result means, and when errors are raised.

### 11.3. Early-closed resources

Be careful when returning a lambda that uses a closed resource:

```java
// DANGEROUS PATTERN: do not use in production applications.
static Supplier<String> broken(java.io.BufferedReader reader) {
    return () -> reader.toString(); // illustrates capturing a reference
}
```

This snippet only shows the lambda holding a reference to `reader`; `toString()` does not read data from the reader and therefore **is not an example that triggers a read-from-closed-resource error**. The real problem occurs when the callback attempts to perform an operation on a resource that has already been closed (such as reading a line inside `get()`), so you must tie the resource's lifecycle to the lifetime of the behavior's use, or design the factory to open and close the resource on each invocation when appropriate.

Do not return a Stream or a callback that depends on an already-closed source assuming "creating the lambda early means the resource is still open." Execution time determines whether the resource must still be alive.

## 12. Common pitfalls

1. **Returning data instead of behavior:** a method declared to return `Supplier<String>` must return a Supplier (e.g., `() -> "x"`), not `"x"` directly.
2. **Calling the wrong functional method:** `Supplier.get()` takes no arguments; `Function.apply(input)` requires one argument.
3. **Confusing execution timing:** computation before `return` runs when the factory is called; the lambda body runs only when invoked.
4. **Assuming Supplier caches automatically:** `get()` may re-run and return a different value.
5. **Reassigning a captured local variable:** captured local variables/parameters must be final or effectively final.
6. **Assuming final makes an object immutable:** a lambda can observe changing state in a mutable object.
7. **Assuming a lambda runs asynchronously on its own:** you need an executor/scheduler for true async execution.
8. **Wrong target type:** `Function<String,Integer>` is different from `Supplier<Integer>`, even if both can produce a number.
9. **Assuming var infers a lambda's type:** `var f = x -> x + 1;` lacks a target type; a method return type or an explicitly typed variable can provide it.
10. **Ignoring checked exceptions:** standard `Supplier`/`Function` do not declare checked exceptions on their functional methods.
11. **Wrong compose/andThen order:** `f.andThen(g)` runs `f` first; `f.compose(g)` runs `g` first.
12. **Letting behavior hold onto a closed resource:** a factory and its callback have different lifecycles.
13. **Using shared mutable state in parallel Streams without control:** being able to return a lambda does not make it thread-safe.
14. **Hard-to-read APIs from returning an overly generic `Function`:** when behavior has specific business meaning, name the factory method clearly and document null handling, side effects, and execution timing.

## 13. Self-check exercises

**Question 1.** What does the method `static Supplier<Integer> make(int n) { return () -> n * 2; }` return when `make(4)` is called?

**Answer:** It returns a `Supplier<Integer>`, not the number `8` yet. Only after that does `make(4).get()` return `8`.

**Question 2.** Write a factory that creates a Function multiplying a value by a given factor:

```java
static java.util.function.Function<Integer, Integer> multiplyBy(int factor) {
    return value -> value * factor;
}
```

`multiplyBy(3).apply(5)` returns `15`. `factor` is captured, while `value` is provided at application time.

**Question 3.** Does `Supplier<List<String>>` guarantee returning a new list on every `get()` call?

**No.** The functional interface only specifies that `get()` returns a `List<String>`; whether it creates a new instance, uses a cache, or returns a shared instance depends on the implementation.

**Question 4.** Why is `var supplier = () -> 42;` invalid, whereas `static Supplier<Integer> make() { return () -> 42; }` is valid?

Because the first case lacks a **target type** for the lambda, whereas `make`'s return type `Supplier<Integer>` provides the target type in the `return` statement.

**Question 5.** `Function<String,String> a = String::strip;` and `Function<String,String> b = s -> "ID:" + s;`. What does `a.andThen(b).apply("  Java  ")` return?

**Answer:** `"ID:Java"`, because `strip` runs first and the prefix is added afterward.

**Question 6.** If a Supplier holds a reference to a `StringBuilder` and the caller modifies its contents after creating the Supplier, can the result of `get()` change?

**It can change**, if the Supplier reads the `StringBuilder`'s state when `get()` runs. If the factory created a `String` snapshot and captured that string instead, the result will not change when the builder is modified.

**Question 7.** Which style should you use when you only need to compute a value immediately, with no need to defer or reuse behavior?

Using a method that returns data directly is usually clearer. Returning `Supplier`/`Function` is valuable when the API genuinely needs to pass, compose, configure, or defer behavior.

**Key takeaway:** A method returning `Supplier<T>` or `Function<T,R>` is a **behavior factory**. `Supplier` is invoked via `get()` with no arguments; `Function` uses `apply(input)`. Be explicit about **target type, captured values, execution timing, and state contract** so callers understand the exact behavior.