# Supplier<T> for operations that supply a value with no arguments

## Lesson objectives

`Supplier<T>` is a functional interface in the `java.util.function` package representing **the behavior of supplying a value of type `T` when requested, taking no arguments at call time**. It is useful when you need to defer data creation, delegate the responsibility of creating a value elsewhere, pass a factory, or configure how to obtain a fallback value.

After this lesson, you can:

- Read the `T get()` contract and write an appropriate lambda, method reference, or constructor reference.
- Distinguish **creating a Supplier** from **calling a Supplier**, as well as when and how many times the value is computed.
- Use `Supplier` with `Optional.orElseGet`, `Stream.generate`, factory APIs, and value-providing operations.
- Understand that `Supplier` does not guarantee purity, caching, uniqueness, thread safety, or non-`null` results.
- Choose properly among `Supplier<T>`, `Function<T,R>`, `Callable<T>`, `Runnable`, and primitive variants.
- Recognize bugs involving checked exceptions, side effects, mutable data sources, and resource handling.

## 1. Contract of Supplier<T>

The equivalent core API definition:

```java
package java.util.function;

@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

This is a way to **illustrate the API signature**, not a snippet to recompile into `java.util.function.Supplier` in an application. `Supplier<T>` has one abstract method `get()`:

| Component | Meaning |
| --- | --- |
| `T` | Type of the supplied value, such as `String`, `User`, `List<Order>`, ... |
| Parameter list of `get()` | **Empty**, written `()` |
| Return type | `T`; each call may return a different object or value |
| `throws` clause | Declares no checked exceptions |
| Function descriptor | `() -> T` |

Because `Supplier<T>` is a functional interface, it can be implemented with a zero-argument lambda expression:

```java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get(); // "Xin chào"
```

You must import `java.util.function.Supplier` at the top of the file or use the fully qualified name. The `()` part is important: `Supplier` has no parameters, so `name -> name.toUpperCase()` is a **one-parameter** lambda and cannot be assigned to `Supplier<String>`.

A Supplier takes no arguments at **the time `get()` is called**, but the function can **capture** variables from the enclosing scope or reference objects/services. Do not interpret "takes no parameters" as "does not depend on external data" or "always returns the same value".

## 2. Three common ways to create a Supplier

### 2.1. Zero-argument lambda

```java
Supplier<String> constant = () -> "READY";
Supplier<Integer> answer = () -> 42;
Supplier<List<String>> emptyNames = () -> new ArrayList<>();
```

`constant.get()` yields `"READY"`; `answer.get()` yields `42` (boxed into `Integer`). With `emptyNames`, **each call creates a new `ArrayList`** because `new` executes inside the body every time `get()` is called.

The snippets above are illustrative code that require importing `java.util.function.Supplier`, `java.util.List`, and `java.util.ArrayList`, and placing them inside an appropriate Java method or initializer block.

### 2.2. Constructor reference: `ClassName::new`

When a class has a compatible no-argument constructor:

```java
Supplier<StringBuilder> builderFactory = StringBuilder::new;

StringBuilder first = builderFactory.get();
StringBuilder second = builderFactory.get();
System.out.println(first == second); // false
```

`StringBuilder::new` is a concise way to supply a new object; it is functionally equivalent to `() -> new StringBuilder()`. Each call to `get()` runs the constructor again. The constructor must match the descriptor `() -> StringBuilder`; a constructor requiring mandatory parameters will not fit `Supplier` unless you use a lambda capturing known arguments, such as `() -> new Person("An")`.

Do not infer that every constructor reference or **every Supplier implementation** creates a new object: for example, `() -> existingObject` returns the same existing reference, whereas `StringBuilder::new` guarantees creating a new instance in this example.

### 2.3. Zero-argument method reference

```java
java.time.Clock clock = java.time.Clock.systemUTC();
Supplier<java.time.Instant> now = clock::instant;

Supplier<Double> random = Math::random;
```

`clock::instant` is a method reference bound to receiver `clock`; `Math::random` references a no-argument static method. Both match `() -> T`. The value of `now.get()` depends on time, while `random.get()` depends on a random source; neither is a pure function.

A method reference like `String::length` is **unbound** (has no receiver) and therefore requires a `String` as an input parameter; it fits `Function<String,Integer>` or `ToIntFunction<String>`, not `Supplier<Integer>`. To get a Supplier, use a bound method reference: `"Java"::length`.

## 3. Creating a Supplier vs. calling get()

Consider:

```java
Supplier<String> value = () -> expensiveLookup();
```

Conceptually, creating the lambda provides an object representing the behavior; **the body `expensiveLookup()` has not run yet**. Only when the consumer calls `value.get()` does the lookup happen. This is **deferred execution**. If the consumer never calls `get()`, the lookup in the body never occurs.

Conversely:

```java
String alreadyComputed = expensiveLookup();
Supplier<String> value = () -> alreadyComputed;
```

`expensiveLookup()` runs **before** creating the Supplier; subsequent calls to `get()` simply return the same precomputed value. When you need to defer work, put the work inside the Supplier's body rather than computing it beforehand and capturing the result.

A Supplier specifies **how to obtain a value**; it does not specify **when, how many times, or on which thread** the recipient will call it. An API may call it zero times, once, or many times; read that API's contract. Using `Supplier` does not by itself create memoization, make the result fixed, or build a caching mechanism.

### A Supplier can create new objects, return existing ones, or change results

```java
Supplier<String> sameText = () -> "A";
Supplier<List<String>> fresh = ArrayList::new;

java.util.concurrent.atomic.AtomicInteger sequence =
        new java.util.concurrent.atomic.AtomicInteger(0);
Supplier<Integer> next = sequence::incrementAndGet;
```

- `sameText.get()` returns `"A"` every time.
- `fresh.get()` creates a new list every time.
- `next.get()` yields `1`, `2`, ... in turn because the body mutates state.

Therefore, the name `Supplier` carries no promise that every call returns the same value, has no side effects, or always allocates a new object.

## 4. Java 17 program: deferral, fallback, constructor, and multiple get() calls

Create the file **`SupplierDemo.java`**:

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class SupplierDemo {
    record Ticket(String level) {
        Ticket() {
            this("Standard");
        }
    }

    static String defaultName(AtomicInteger calls) {
        calls.incrementAndGet();
        return "Khách";
    }

    static String greet(Supplier<String> nameSupplier) {
        return "Xin chào, " + nameSupplier.get();
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        Supplier<String> fallback = () -> defaultName(creations);

        System.out.println("Trước get: " + creations.get());
        System.out.println("Chào: " + greet(fallback));
        System.out.println("Sau get: " + creations.get());

        Optional<String> present = Optional.of("An");
        String eager = present.orElse(defaultName(creations));
        String lazy = present.orElseGet(fallback);
        System.out.println("orElse: " + eager);
        System.out.println("orElseGet: " + lazy);
        System.out.println("Sau hai fallback: " + creations.get());

        String missing = Optional.<String>empty().orElseGet(fallback);
        System.out.println("Thiếu tên: " + missing);
        System.out.println("Tổng lượt tạo: " + creations.get());

        Supplier<Ticket> tickets = Ticket::new;
        System.out.println("Ticket: " + tickets.get().level());

        AtomicInteger ids = new AtomicInteger(100);
        Supplier<Integer> nextId = ids::incrementAndGet;
        System.out.println("IDs: " + nextId.get() + ", " + nextId.get());

        List<String> marks = Stream.generate(() -> "A")
                .limit(3)
                .toList();
        System.out.println("Stream: " + marks);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SupplierDemo.java
java SupplierDemo
```

**Output:**

```text
Trước get: 0
Chào: Xin chào, Khách
Sau get: 1
orElse: An
orElseGet: An
Sau hai fallback: 2
Thiếu tên: Khách
Tổng lượt tạo: 3
Ticket: Standard
IDs: 101, 102
Stream: [A, A, A]
```

**Trace the execution flow step by step:**

1. `fallback` is created without calling `defaultName`. Thus the `creations` counter starts at `0`.
2. `greet(fallback)` calls `nameSupplier.get()` exactly once. The body runs `defaultName(creations)`, returns `"Khách"`, and increments the counter to `1`.
3. `present.orElse(defaultName(creations))` must **evaluate the argument** `defaultName(creations)` before calling `orElse`. Even though `present` already contains `"An"`, the counter still increments to `2`; the final result remains `"An"`.
4. `present.orElseGet(fallback)` takes a Supplier. Because `present` has a value, it does not call `fallback.get()`, and the counter stays at `2`.
5. `Optional.empty().orElseGet(fallback)` calls the Supplier because there is no value, returns `"Khách"`, and increments the counter to `3`.
6. `Ticket::new` references the no-argument constructor of `Ticket`. `tickets.get()` creates an object with `level = "Standard"`.
7. `ids::incrementAndGet` is a Supplier that reads and mutates the counter; two calls return `101` and `102`.
8. `Stream.generate(() -> "A").limit(3).toList()` requests three elements from the Supplier and ends with the list `[A, A, A]`.

The example shows that the same interface can express a fixed value, a factory, a fallback, or stateful generation. Its actual behavior comes from **the Supplier's body** and how the API uses it.

## 5. Supplier with Optional.orElseGet: lazy fallback

A very common case is obtaining a fallback value when an `Optional<T>` is empty:

```java
String result = maybeName.orElseGet(() -> loadDefaultName());
```

`loadDefaultName()` only runs if `maybeName` is empty. Comparison:

| API | Argument | When the fallback value is computed |
| --- | --- | --- |
| `optional.orElse(value)` | Value `T` | Argument expression is evaluated before the call, even if Optional already has a value |
| `optional.orElseGet(supplier)` | `Supplier<? extends T>` | Calls `supplier.get()` when Optional is empty |
| `optional.orElseThrow(supplier)` | `Supplier<? extends X>` for exception | Calls Supplier to create the exception when Optional is empty |

If the fallback is just a cheap constant like `"N/A"`, `orElse("N/A")` is easy to read and completely appropriate. If the fallback is expensive or has intentional side effects, `orElseGet` is usually the right choice. Do not assign a precomputed value to a Supplier and assume the operation is deferred.

```java
// Wrong lazy intent: loadDefaultName() already ran.
String cached = loadDefaultName();
String first = optional.orElseGet(() -> cached);

// Right if you only want it to run when the value is missing.
String second = optional.orElseGet(() -> loadDefaultName());
```

The snippets in this section are **context illustrations**; `optional` and `loadDefaultName` must be defined. A `Supplier` can return `null`; when `Optional` is empty, `orElseGet` returns the Supplier's result, even `null`. Do not assume the generic signature `T` means never null.

`Optional.orElseThrow(() -> new IllegalArgumentException("Missing"))` also takes a Supplier, but this is an **exception-creating** Supplier, called only when no value is present. It differs from `orElseGet` because its purpose is to throw an exception.

## 6. Factory: decoupling callers from object creation

Instead of letting a service decide how to instantiate its own dependency, you can pass a Supplier:

```java
// Illustration with two classes defined in the application:
class Processor {
    private final Supplier<Connection> connectionFactory;

    Processor(Supplier<Connection> connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    void execute() {
        Connection connection = connectionFactory.get();
        // Use connection, manage resource closing per contract.
    }
}
```

This is **architectural illustration code**, not a standalone program; the `Connection` type and resource-closing procedure depend on the specific library. The key point is that `Processor` only knows it can request a `Connection` when needed, without knowing how to configure or instantiate it. In tests, pass a Supplier returning a fake instead of a real connection.

However, you must clearly define the **lifecycle**:

- `() -> new Service()` may create a new Service on each call.
- `() -> existingService` returns the same instance.
- A caching-wrapped Supplier may create once and reuse.
- A Supplier reading configuration or remote data may return different values at different times.

`Supplier<T>` **does not say** whether the product is a singleton or prototype. If a resource needs closing (`AutoCloseable`), the caller and provider must have a clear contract on who owns it and when to close it. Passing a Supplier does not automatically solve resource management.

### What if the constructor needs parameters?

Suppose `Product` has a constructor `Product(String name)`. The method reference `Product::new` with one argument matches `Function<String,Product>`, **not** `Supplier<Product>`. If the name is already known where the factory is configured, you can capture it:

```java
// Illustration: Product(String) must be defined beforehand.
String configuredName = "Book";
Supplier<Product> defaultProduct =
        () -> new Product(configuredName);
```

Use `Function<String,Product>` if the name must be decided **per call**; use `Supplier` when no extra arguments need to be passed to `get()`.

## 7. Generating elements with Stream.generate

`Stream.generate(Supplier<? extends T>)` builds a source-wise infinite Stream that is **sequential** and **unordered** per the API. Whenever the pipeline needs an element, the Supplier can be called to supply it. Because the source is unbounded, you need an operation like `limit(n)` or an appropriate stopping condition before collecting all results.

```java
List<Integer> squares = java.util.stream.Stream
        .generate(new java.util.concurrent.atomic.AtomicInteger(0)::incrementAndGet)
        .limit(4)
        .map(n -> n * n)
        .toList();
```

The snippet above **is valid Java syntax**: the expression `new AtomicInteger(0)::incrementAndGet` evaluates the receiver once when creating the method reference, then uses the same counter for `get()` calls. However, separating the counter into its own variable helps readers clearly see its lifecycle and state. A clear, compilable way is to separate the state source:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();
java.util.function.Supplier<Integer> next =
        counter::incrementAndGet;

java.util.List<Integer> squares = java.util.stream.Stream
        .generate(next)
        .limit(4)
        .map(n -> n * n)
        .toList(); // [1, 4, 9, 16]
```

In learning materials, prefer the second example so it is clear the counter is created **once**, then incremented across calls. The `Stream.generate(() -> "A").limit(3)` pattern in the main program is a constant source.

**Note:** `generate` does not guarantee that generation is pure or safe when run in parallel. A Supplier that mutates shared mutable state can make results depend on call count, order, and execution thread. If you need consecutive integers, `IntStream.rangeClosed(1, 4)` is usually clearer than a Supplier with a counter. In the counter example, using `AtomicInteger` prevents lost updates but does not turn generation into a pure function.

Different terminal operations can also request different numbers of elements; do not assume the Supplier will always be called exactly `n` times in every optimized pipeline or processing mode. With the simple sequential illustrative source and pipeline `limit(n).toList()`, we receive exactly `n` elements.

## 8. Supplier for default values and on-demand initialization

Several Java APIs accept a Supplier to defer creating a value or error:

```java
// Optional<T>
String fallback = optional.orElseGet(() -> "Guest");

// Objects.requireNonNullElseGet: uses Supplier if value == null;
// Supplier must provide a non-null result, otherwise NPE is thrown.
String nonNull = java.util.Objects.requireNonNullElseGet(
        possiblyNull,
        () -> "Guest"
);

// If Optional is empty, create and throw an exception.
String required = optional.orElseThrow(
        () -> new IllegalStateException("No name")
);
```

This is an illustrative snippet; `optional` and `possiblyNull` must be declared in scope. Other APIs may choose to call the Supplier multiple times, run it on another thread, or apply their own conditions. When programming with `Supplier`, read the contract of **the method receiving it**.

### Supplier and Map.computeIfAbsent do not share the same signature

`Map.computeIfAbsent(K, Function<? super K,? extends V>)` takes a **Function with key parameter `K`**, not `Supplier<V>` directly:

```java
java.util.Map<String, String> cache = new java.util.HashMap<>();
Supplier<String> defaultUser = () -> "Guest";

String user = cache.computeIfAbsent(
        "profile:42",
        key -> defaultUser.get()
);
```

The mapping function here receives `key` and decides to call `Supplier.get()`. If value creation actually depends on the key, writing `key -> loadByKey(key)` is clearer than forcing a Supplier. Regarding concurrency, `HashMap` does not protect against concurrent access; `ConcurrentHashMap` has its own contract and constraints for computation—do not use a plain `HashMap` to cache across multiple threads without synchronization.

### Supplier with ThreadLocal.withInitial

`ThreadLocal.withInitial(Supplier<? extends S>)` accepts a way to create the initial value **for each thread when needed**:

```java
ThreadLocal<StringBuilder> buffer =
        ThreadLocal.withInitial(StringBuilder::new);
```

Each thread can receive its own `StringBuilder` the first time it calls `buffer.get()`. This isolates data per thread, though you still must mind the lifecycle, especially with thread pools: call `remove()` at the appropriate time to avoid holding state longer than intended.

## 9. Checked exceptions: Supplier.get() does not declare throws

`Supplier<T>.get()` has no `throws IOException` or any checked exception. Therefore, a lambda assigned to a Supplier cannot let a checked exception escape directly:

```java
// Does not compile if readFile() declares throws IOException.
Supplier<String> invalid = () -> readFile();
```

You can design around this in one of the following ways:

**Separate I/O from where a pure Supplier is needed.** Read data at the boundary layer and pass a Supplier returning the normalized result:

```java
// Illustration: value has already been read and validated.
String value = readFile(); // in a method with throws or try/catch
Supplier<String> ready = () -> value;
```

This does not defer I/O; it clarifies responsibility.

**Catch the exception inside the lambda**, handle a fallback if the business contract allows, or wrap it into an unchecked exception while preserving the cause:

```java
Supplier<String> safe = () -> {
    try {
        return readFile();
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
};
```

Wrapping an exception changes how the caller receives errors; consider retry, logging, and transaction policies.

**Define a custom checked supplier** when you need to keep checked exceptions in the contract:

```java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}

ThrowingSupplier<String, java.io.IOException> fileSource =
        () -> readFile();
```

You cannot pass `ThrowingSupplier` directly to a method expecting `Supplier`, because they are two different interfaces. An adapter with an appropriate error-handling rule is needed. The snippets above are **illustrative**, assuming `readFile()` already exists and declares `throws IOException`.

Unchecked exceptions such as `IllegalStateException` can still be thrown from a Supplier and propagate to the caller of `get()` even though they are not listed in `throws`.

## 10. Supplier compared to other functional interfaces

| Interface | Descriptor | Key difference |
| --- | --- | --- |
| `Supplier<T>` | `() -> T` | No parameters, returns a result |
| `Function<T,R>` | `(T) -> R` | One input; transforms data |
| `BiFunction<T,U,R>` | `(T,U) -> R` | Two inputs |
| `Predicate<T>` | `(T) -> boolean` | Returns a logical condition |
| `Consumer<T>` | `(T) -> void` | Takes a value, performs an action |
| `Runnable` | `() -> void` | No parameters, returns no result |
| `Callable<T>` | `() -> T throws Exception` | Returns a result, allows checked exceptions |
| `IntSupplier` | `() -> int` | Returns a primitive `int` |
| `LongSupplier` | `() -> long` | Returns a primitive `long` |
| `DoubleSupplier` | `() -> double` | Returns a primitive `double` |
| `BooleanSupplier` | `() -> boolean` | Returns a primitive `boolean` |

`Callable<T>` belongs to `java.util.concurrent` and is commonly used for result-bearing tasks in asynchronous execution mechanisms. It differs from `Supplier<T>` in its ability to declare `throws Exception`; it does not mean every `Callable` automatically runs on another thread.

Example:

```java
java.util.function.IntSupplier count = () -> 3;
java.util.function.BooleanSupplier ready = () -> true;
java.util.concurrent.Callable<String> task = () -> "done";
Runnable notification = () -> System.out.println("Done");
```

For tasks that only perform an action with no result, `Runnable` can express intent better than `Supplier<Void>` returning `null`. For continuous generation of large numbers of primitives, primitive suppliers avoid the boxing typical of `Supplier<Integer>` or `Supplier<Long>`.

### Supplier and asynchronous APIs

`CompletableFuture.supplyAsync(supplier)` takes a Supplier and runs the value-providing function in an asynchronous task (with the default executor or a supplied executor). A runtime error from the Supplier completes the future exceptionally; execution timing and thread are determined by the execution mechanism, not by the `Supplier` interface itself.

```java
java.util.concurrent.CompletableFuture<Integer> future =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> 40 + 2);

int result = future.join(); // 42 if execution succeeds
```

This is an illustrative example; in real applications, consider executors, task cancellation, timeouts, and error handling. Do not share a Supplier with mutable state across multiple tasks and assume it is thread-safe.

## 11. Issues with null, side effects, and thread safety

**Null results.** The signature `T get()` does not forbid `null` by itself. A Supplier can return `null`; the API using it may allow, forbid, or handle it specially. For example, `Objects.requireNonNullElseGet` requires the Supplier to provide a non-null result when the input is null. If a value may be absent, consider using `Optional<T>` at meaningful API boundaries instead of making the caller guess.

**Side effects.** A `Supplier` can make network calls, write logs, increment counters, create files, or emit events. An API accepting a Supplier may call it again if needed; therefore, **non-idempotent** operations like charging money, sending emails, or writing orders should not be hidden inside `get()` without a clear invocation contract and duplicate protection.

**Stateful Suppliers.** Using an internal counter or `Iterator` makes call order affect the result; state the semantics clearly, especially when used in Streams or multithreaded programs.

**Concurrency.** `Supplier<T>` makes no thread-safety guarantee. `AtomicInteger` only protects the counter itself; other captured objects must also be examined. If a Supplier has shared mutable state, use proper synchronization or avoid sharing across threads.

**Memoization.** `Supplier` does not cache by default. If you need to compute only on the first call and reuse, you must design it yourself or use a holder/cache with a clear contract for synchronization, object publication, null handling, and retry on failure. A caching Supplier is not necessarily equivalent to a fresh-creating Supplier; check whether callers expect a separate instance each time.

**Resource management.** `Supplier<InputStream>` may open a new stream on each `get()`; the consumer must close the stream per the contract. A Supplier returning the same already-closed stream from a previous call will be unsuitable if callers expect a new connection/resource.

## 12. Common mistakes and how to fix them

1. **Confusing Supplier with Function:** `x -> x.trim()` has one parameter. For Supplier use `() -> "text"`; when you want to receive data at call time, use `Function<String,String>`.
2. **Mixing up creating a Supplier and executing it:** `Supplier<T> s = () -> expensive()` defers work; `T x = expensive(); Supplier<T> s = () -> x` already computed it beforehand.
3. **Assuming `get()` only runs once:** check the caller's contract; if called multiple times, the body can run multiple times.
4. **Using `orElse(expensive())` expecting laziness:** the argument is still evaluated. Use `orElseGet(() -> expensive())` if you only need a fallback when missing.
5. **Passing a constructor reference with the wrong arity:** `Product::new` for a constructor requiring parameters cannot be used directly as `Supplier<Product>`; capture configuration in a lambda or use `Function`.
6. **Hiding checked exceptions:** `Supplier.get()` declares no checked exceptions. Catch/convert errors intentionally or use a custom checked functional interface.
7. **Assuming Suppliers are always pure:** a Supplier can read a clock, random generator, database, and mutate state. Inspect the specific body.
8. **Abusing unbounded `Stream.generate`:** an infinite pipeline should not call `toList()` without a stopping condition; use `limit` or an appropriate finite source.
9. **Not defining object lifecycle:** a Supplier may return a singleton or a new instance; document ownership and resource-closing needs clearly.
10. **Assuming `Supplier<Integer>` is always optimal for integers:** if boxing pressure matters, look at `IntSupplier`.
11. **Confusing `Supplier.get()` and `Optional.get()`:** `Supplier.get()` executes value-supplying behavior; `Optional.get()` retrieves a present value or throws `NoSuchElementException` when empty.

## 13. Reinforcement exercises

**Exercise 1 — Deferral.** Write a `Supplier<String>` returning `"Hello"`. Print a message inside the lambda and check whether the message appears before or after calling `get()`.

**Exercise 2 — Multiple calls.** Use `AtomicInteger` to write a `Supplier<Integer>` supplying numbers increasing from `1`. Call it three times and explain why the result is not fixed even though `get()` takes no parameters.

**Exercise 3 — Factory.** Given a class `Box` with a no-argument constructor, write a `Supplier<Box>` using a constructor reference. Compare the identity of two instances obtained via `get()`.

**Exercise 4 — Fallback.** Suppose you have `Optional.of("An")` and a method `loadGuest()` that logs. Compare the number of log calls when calling `orElse(loadGuest())` versus `orElseGet(() -> loadGuest())`.

**Exercise 5 — Choosing an interface.** Which interface should be chosen for each need: supplying a `long` with no arguments; transforming a `String` into an `Integer`; running a task that returns no result; a task that may throw `IOException` in its contract?

**Exercise 6 — Debugging.** An application uses `Stream.generate(database::fetchNext).limit(10)`. Examine the possibility of the source returning `null`, call count, data finiteness, thread safety, connection lifecycle, and retry policy before using it.

**Answer hints:** (1) `() -> "Hello"`; the body only runs when `get()` is called. (2) `AtomicInteger counter = new AtomicInteger(); Supplier<Integer> next = counter::incrementAndGet;` returns `1, 2, 3`. (3) `Supplier<Box> f = Box::new;`; if the constructor creates a new object, two `get()` calls return two different references. (4) `orElse` evaluates the fallback immediately; `orElseGet` skips the fallback when Optional has a value. (5) `LongSupplier`, `Function<String,Integer>`, `Runnable`, `Callable<T>` or a custom functional interface declaring `throws IOException` depending on the contract.

## 14. Application summary

When you need to pass **value-supplying behavior taking no arguments**, `Supplier<T>` is the concise contract: `() -> T`. Lambdas `() -> ...`, constructor references, and bound method references are common implementations. The strength of `Supplier` is **deferring value creation/retrieval until the consumer actually calls `get()`**, especially in fallbacks or factories.

To use it properly, determine who calls it, when it is called, how many times it may be called, whether values are created fresh or cached, whether it can return null, whether it has side effects, whether checked exceptions exist, and whether synchronization or resource closing is needed. These belong to **the contract of the Supplier body and the API using it**, and are not guaranteed by the name `Supplier` alone.
