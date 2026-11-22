# `Consumer<T>` in Java: performing an operation without returning a result

## 1. What is `Consumer<T>`?

`Consumer<T>` is a **functional interface** in the `java.util.function` package. It describes an operation that **takes a value of type `T`, performs an action, and returns no result**. The name `Consumer` suggests that the operation *consumes* the input: logging, printing data, sending a notification, updating an object, calling a service, or passing data to a destination.

Its single abstract method (SAM) is:

~~~java
void accept(T value);
~~~

This is an **illustrative signature** of a method inside the interface, not a standalone Java program. Call `accept(value)` to execute the action. Because it is a functional interface, you can provide the action using a **lambda** or **method reference**. For example:

~~~java
Consumer<String> print = message -> System.out.println(message);
print.accept("Hello Java");
~~~

The snippet above is placed inside a method with `import java.util.function.Consumer;`. The printed output is:

~~~text
Hello Java
~~~

Important point: **`accept` has return type `void`**, which does not mean it performs no work or does not change state. On the contrary, `Consumer` is often chosen when the goal is an intentional *side effect*. However, a `Consumer` lambda may also simply observe data or do nothing; the API does not force it to cause a change.

### Learning objectives

Learners should be able to:

- Declare, accept, and invoke `Consumer<T>` via `accept`; read the type of `T`.
- Use a lambda or method reference to represent an action that returns no result.
- Distinguish `Consumer<T>` from `Function<T,R>`, `Predicate<T>`, `Supplier<T>`, and `Runnable`.
- Chain actions with `andThen` and properly understand order, errors, and behavior with `null`.
- Use `Consumer` at appropriate processing points such as `Iterable.forEach`, `Stream.forEach`, callbacks, or action-accepting methods.
- Control side effects, parallel execution effects, and common mistakes.

Standalone examples in this article use **Java 17 or later**.

## 2. Structure and API contract

The main public members can be summarized in the following table:

| Member | Kind | Role |
| --- | --- | --- |
| `void accept(T t)` | **Single abstract method** | Performs the action on one input |
| `Consumer<T> andThen(Consumer<? super T> after)` | **Default method** | Creates a composed `Consumer` that runs the current action followed by `after` |

The interface is also annotated with `@FunctionalInterface` in the standard library. The `andThen` method has a default body, so it **does not add another SAM**. That is why `Consumer<T>` can still be used with lambdas.

### Why use the generic type `T`?

`T` is the input type, checked at compile time. For example:

~~~java
Consumer<String> printName = System.out::println;
Consumer<Integer> printNumber = System.out::println;
~~~

For `printName`, `accept` takes `String`; for `printNumber`, `accept` takes `Integer`. The same method reference `System.out::println` can match multiple signatures, and the compiler chooses the overload based on the **target type**.

A `Consumer<Order>` is not automatically a `Consumer<Object>` because Java generics are invariant. When an API wants to accept an action that handles `T` or supertypes of `T`, a useful parameter pattern is `Consumer<? super T>`; `Consumer.andThen` also uses this pattern. Do not use arbitrary casts to trick the compiler.

### `accept` has no result to pass onward

The example below is **invalid**:

~~~java
// Compile error: accept(...) returns void and cannot be assigned to a variable.
Consumer<String> printer = System.out::println;
String text = printer.accept("Java");
~~~

This is an intentional error example. If you want to **transform `String` into `String`**, use `Function<String,String>`; if you want to **check a condition**, use `Predicate<String>`. Choose the interface by its input and output contract, not just because the lambda syntax looks similar.

## 3. Writing `Consumer` with lambdas and method references

### 3.1. Single-expression lambda

~~~java
Consumer<String> print = text -> System.out.println(text);
print.accept("Java");
~~~

On the left, `text` is a parameter whose type `String` is inferred by the compiler from `Consumer<String>`. The right-hand side executes a print statement. There is no `return` value.

### 3.2. Multi-statement block lambda

~~~java
Consumer<String> printUpper = text -> {
    String normalized = text.trim().toUpperCase(java.util.Locale.ROOT);
    System.out.println(normalized);
};
printUpper.accept("  java  "); // Prints JAVA
~~~

With a block lambda for `Consumer`, you can use `return;` to exit early, **you cannot write `return someValue;`**. An expression with a return value such as `list.add(item)` is sometimes allowed as a *statement expression* for a `void`-compatible lambda; however, to make the side effect clear to readers, you can use a block and explicitly ignore the result.

### 3.3. Method reference

If the lambda only calls a matching method directly, a method reference is often cleaner:

~~~java
Consumer<String> print = System.out::println;
print.accept("One");
~~~

`System.out` is a specific object; `::println` is a reference to an instance method. Another example: `Consumer<String> action = logger::info;` only makes sense if `logger` exists and the `info` method accepts a compatible type. Not every method reference matches `Consumer`: the compiler still checks the parameter count and types, exceptions, and compatibility with `void`.

### 3.4. Callbacks accepting `Consumer`

A custom API can accept an action as a parameter:

~~~java
static void processName(String name, Consumer<String> action) {
    action.accept(name);
}
~~~

This is an **illustrative method** that must be placed in a class with `Consumer` imported. You can call `processName("Lan", System.out::println)` or pass a logging lambda. Turning the action into a parameter lets you reuse the orchestration logic while the caller decides what to do with the data.

If `action` is `null`, calling `action.accept` throws `NullPointerException`; when designing a public API, you can use `Objects.requireNonNull(action, "action")` to fail fast with a clearer message.

## 4. `andThen`: chaining operations in order

The method:

~~~java
Consumer<T> andThen(Consumer<? super T> after)
~~~

is an **illustrative API signature**, not a standalone program. With `first.andThen(second)`, the returned `Consumer` will:

1. Run `first.accept(input)`.
2. After step one completes normally, run `second.accept(input)`.

**Both actions receive the same input value**; the result of the first action is not passed to the second action because `accept` returns `void`. `andThen` creates a combined action object; it does not run anything until `accept` is called (or an API like `forEach` calls it for you).

Illustrative example:

~~~java
Consumer<String> mark = s -> System.out.println("START " + s);
Consumer<String> save = s -> System.out.println("SAVE " + s);
Consumer<String> pipeline = mark.andThen(save);
pipeline.accept("A1");
~~~

Result:

~~~text
START A1
SAVE A1
~~~

### What happens when an error occurs?

If `first.accept(input)` throws an exception, `second.accept(input)` **does not run**; the exception is propagated to the caller. If `second` throws an exception, the first action may already have produced side effects, and there is no automatic rollback mechanism. Therefore, `andThen` **is not a transaction**.

`first.andThen(null)` throws `NullPointerException` per the API contract of `Consumer.andThen`. This differs from calling `first.accept(null)`: `Consumer` does not forbid `null` inputs by itself; whether `null` is accepted depends on the implementation.

A useful aspect of `Consumer<? super T>`: you can chain a `Consumer<Object>` after a `Consumer<String>`, because an action accepting `Object` can handle any `String`. However, this is still a sequence of actions; if you need to **pass the output of one transformation to the next step**, use `Function.andThen` or design a data pipeline.

### Warning about order and mutable objects

The exact same `input` reference is passed to both actions. If `first` mutates the state of a mutable object, `second` may see the modified state. Thus, the order in `andThen` matters and usually cannot be reversed arbitrarily.

For example, `validate.andThen(save)` makes sense when `validate` throws an exception on invalid data; `save.andThen(validate)` would write data before checking it, leading to different consequences. For processing that requires atomicity, you must use transactions or appropriate compensation rather than expecting `andThen` to provide it.

## 5. Complete Java 17 program

Problem: process three orders. For each order, record an event in a list and add the amount to a counter. Use separate `Consumer<Order>` instances for each action, then combine them with `andThen`. The example runs sequentially so the order is easy to observe.

Create the file **`ConsumerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

public class ConsumerDemo {
    record Order(String id, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A1", 120),
                new Order("B2", 80),
                new Order("C3", 50)
        );

        List<String> events = new ArrayList<>();
        AtomicInteger total = new AtomicInteger();

        Consumer<Order> recordEvent =
                order -> events.add("Processed " + order.id());

        Consumer<Order> addAmount =
                order -> total.addAndGet(order.amount());

        Consumer<Order> process =
                recordEvent.andThen(addAmount);

        orders.forEach(process);

        System.out.println(events);
        System.out.println(total.get());

        Consumer<String> printUpper =
                value -> System.out.println(value.toUpperCase(Locale.ROOT));
        printUpper.accept("done");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ConsumerDemo.java
java ConsumerDemo
~~~

**Exact stdout:**

~~~text
[Processed A1, Processed B2, Processed C3]
250
DONE
~~~

Explanation:

- `record Order(String id, int amount)` creates an immutable data type at the record-component level, suitable for storing simple order information.
- `recordEvent` appends a descriptive string to `events`; this is a **side effect** and the `List` used here is mutable.
- `addAmount` updates a counter. `AtomicInteger.addAndGet` returns the new number, but the `Consumer` lambda ignores the return value.
- `recordEvent.andThen(addAmount)` creates a compound action; `orders.forEach(process)` calls that action on each element in list order.
- `System.out.println(events)` prints the three events in processing order; total `120 + 80 + 50 = 250`.
- `printUpper` is a `Consumer<String>` that stores no result and simply prints the transformed string.

**Practical limitation:** `AtomicInteger` makes updating the individual counter safe across multiple threads, but `ArrayList events` in the example **is not safe for concurrent modification by multiple threads**. Do not casually switch this example to `parallelStream().forEach(process)`. Moreover, even though individual additions are safe, the combination of recording an event and adding to the total does not become an atomic operation.

## 6. `Consumer` with Collections and Stream

### 6.1. `Iterable.forEach`

`Iterable.forEach(Consumer<? super T> action)` takes a `Consumer` and calls it with the traversed elements. With an ordered `List`, learners typically see actions run in traversal order. Use it when the primary goal is **performing an action on each element**:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
names.forEach(System.out::println);
~~~

This is a **code snippet inside a method** with `import java.util.List;`. It prints `An`, `Bình`, `Chi` in order. If the goal is to **create a new list**, prefer transforming data and collecting results instead of using `forEach` to mutate an external list.

### 6.2. `Stream.forEach`

In the Stream API, `forEach(Consumer<? super T> action)` is a **terminal operation**. Example:

~~~java
List.of("a", "bb", "ccc").stream()
        .filter(s -> s.length() >= 2)
        .forEach(System.out::println);
~~~

The program above prints `bb` and `ccc` in the sequential stream case shown. The pipeline does not return a resulting collection from `forEach`; the operation is primarily a side effect. `Stream.forEach` is defined as an operation that does not guarantee order when executed on a parallel stream, and each action may run on a different thread.

If you need to preserve *encounter order* on an ordered stream, there is `forEachOrdered`. However, **preserving order does not mean all shared state becomes thread-safe** or transactional. If you need a data structure as a result, use `map`, `filter`, `collect`, `toList`, or an appropriate reduction.

### 6.3. Why `peek` is not the place for business logic

`Stream.peek(Consumer<? super T>)` is an **intermediate** operation; it is useful for observing/debugging a pipeline, but intermediate operations are generally lazy. A pipeline may not execute intermediate operations if there is no terminal operation; additionally, Stream optimizations may skip unnecessary steps or elements, such as `count()` in certain cases. Do not put critical behavior like recording payments, sending emails, or updating business state inside `peek` and assume every element is guaranteed to be processed once.

When a side effect is the final goal, `forEach` can be appropriate. When the goal is transforming data into a result, prefer pure operations and collectors.

## 7. Comparing `Consumer` with related functional interfaces

| Functional interface | Conceptual signature | Choose when |
| --- | --- | --- |
| `Consumer<T>` | `T -> void` | Performing an action with one input |
| `BiConsumer<T,U>` | `(T,U) -> void` | Action requiring two inputs |
| `Function<T,R>` | `T -> R` | Transforming data and needing a result |
| `Predicate<T>` | `T -> boolean` | Evaluating a true/false condition |
| `Supplier<T>` | `() -> T` | Creating/supplying a value when called |
| `Runnable` | `() -> void` | Running an action with no input |

**Practical scenario:** if the system needs to convert an `Order` to a DTO, use `Function<Order,OrderDto>`; if it needs to check whether an order is valid, use `Predicate<Order>`; if it needs to log or emit an event about the order, `Consumer<Order>` is usually appropriate.

`Runnable` belongs to `java.lang` and has a `run()` method taking no parameters. `Consumer<T>` has `accept(T)`, so it receives data from the caller. Choosing the right interface makes the API reflect intent.

### Primitive types and autoboxing

`Consumer<Integer>` takes an `Integer` object; if you continuously process `int` values, you can use `IntConsumer` to avoid unnecessary boxing. The `java.util.function` package also includes:

- `IntConsumer`, `LongConsumer`, `DoubleConsumer`: accept a corresponding primitive value and return `void`.
- `BiConsumer<T,U>`: accepts two objects and returns `void`.
- `ObjIntConsumer<T>`, `ObjLongConsumer<T>`, `ObjDoubleConsumer<T>`: accept one object and one corresponding primitive value.

Example snippet inside a method:

~~~java
java.util.function.IntConsumer printDouble =
        value -> System.out.println(value * 2);
printDouble.accept(6); // Prints 12

java.util.function.BiConsumer<String, Integer> printEntry =
        (name, score) -> System.out.println(name + ": " + score);
printEntry.accept("An", 9); // Prints An: 9
~~~

`BiConsumer` also has `andThen`, but with two parameters; do not confuse it with `BiFunction<T,U,R>`, because `BiFunction` must return a value.

## 8. Side effects, captured variables, and state bugs

### 8.1. Lambdas and effectively final

A lambda can use local variables declared `final` or **effectively final**. Valid example:

~~~java
List<String> log = new ArrayList<>();
Consumer<String> addLog = item -> log.add(item);
addLog.accept("saved");
~~~

This is code placed in a method with appropriate imports. The reference variable `log` is not reassigned, so it is effectively final, but **the contents of the List object can still be mutated**. `Consumer` does not make side effects pure or thread-safe.

Intentional error example:

~~~java
int count = 0;
Consumer<String> counter = text -> count++; // Does not compile
~~~

`count` is a local variable captured and then modified by the lambda, violating the effectively final rule. Do not mechanically work around this with an `int[]` array just to mutate the value; that usually makes state hard to manage and does not guarantee concurrent safety.

### 8.2. Should you use `AtomicInteger` to compute a sum?

If the main goal is **computing a sum**, prefer reduction:

~~~java
int sum = List.of(10, 20, 30).stream()
        .mapToInt(Integer::intValue)
        .sum(); // 60
~~~

This returns a clear result without updating variables outside the pipeline. Using a `Consumer` to update an `AtomicInteger` is more appropriate when the state-updating action itself is the explicit goal, and correctness must be evaluated in the specific execution environment.

### 8.3. Parallel streams and thread safety

Do not assume `parallelStream().forEach(consumer)` will invoke `Consumer` sequentially or in source order. If multiple threads modify an `ArrayList`, `HashMap`, or other mutable variables without proper coordination, race conditions, lost data, or unpredictable results can occur. Likewise, just because an object like `AtomicInteger` has atomic updates does not mean an entire workflow with multiple side effects is safe.

Only choose parallel execution when the algorithm can be split safely, the combining operation satisfies the contract, and there is evidence of benefit. For work that needs an aggregated result, a proper collector/reduction is usually simpler and easier to test.

### 8.4. Checked exceptions in `Consumer`

`Consumer.accept(T)` does not declare any checked exceptions. Therefore, a `Consumer` lambda cannot directly let a checked exception escape from a called method without handling or converting it appropriately. For example, `Files.writeString(path, text)` can throw `IOException`; if placed in a lambda passed to `forEach`, you must decide whether to handle it on the spot, capture the error in a business result, use an API whose contract allows checked exceptions, or wrap it into an unchecked exception **with clear error context**.

Do not swallow exceptions with `catch (Exception ignored) {}` just to make code compile. In `andThen`, an exception in the first step prevents the second step from running; an exception in the second step does not automatically undo the first action.

### 8.5. `null` and validation

`Consumer<T>` does not guarantee it will never receive `null`. For example, `Consumer<String> printUpper = s -> System.out.println(s.toUpperCase());` will throw `NullPointerException` if `accept(null)` is called. If the contract requires non-null data, check explicitly beforehand or inside the action. If `null` is a valid value, define how to handle it rather than assuming every Consumer behaves the same way.

## 9. Common mistakes and how to fix them

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Trying to assign the result of `consumer.accept(x)` | `accept` returns `void` | Use `Function` when an output is needed |
| Thinking `andThen` runs immediately when declared | It only creates a new Consumer | Call `accept` or pass it to an executing API |
| Using `andThen` like `Function.andThen` | Both consumers receive the **same** input; no result is passed | Use `Function` for transformation pipelines |
| Calling `andThen(null)` | `after` must be non-null | Pass a valid action |
| Treating `andThen` as a transaction | A later failure does not roll back the earlier step | Design separate error handling/transactions |
| Reassigning a local variable captured by a lambda | Violates effectively final | Return a result or use an appropriate state-managing object |
| Using `forEach` to build a new `List` with `add` | Side effect outside pipeline, hard to control | Use `map(...).toList()` or `collect` |
| Using `parallelStream().forEach` to mutate a shared `ArrayList` | Concurrent access contention on shared state | Avoid mutable shared state; use a proper collector |
| Relying on `peek` for business writes | Lazy/optimizations may skip calls | Choose an explicit terminal action or process outside the pipeline |
| Hiding checked exceptions inside a lambda | Loses business error details | Build an appropriate error-handling contract |
| Too many side effects in one Consumer | Hard to debug and reuse | Split into named actions, keeping clear order via `andThen` when appropriate |
| Using `Consumer<Integer>` on a large-integer hot path | Boxing/unboxing can add overhead | Consider `IntConsumer` and benchmark appropriately |

## 10. Guided practice exercises

### Exercise 1 — Print content with a prefix

Write a `Consumer<String> printer` that prints `"LOG: "` plus the message. Call `printer.accept("start")`; the expected output is `LOG: start`. Rewrite it with a method reference if a matching instance method exists.

### Exercise 2 — Run two actions in sequence

Create `Consumer<String> first` printing `"A:"` + string and `Consumer<String> second` printing `"B:"` + string. Combine `first.andThen(second)`, call it with `"x"`, and verify the output is `A:x` followed by `B:x`. Then modify `first` to throw `IllegalStateException` and observe why `second` does not run.

### Exercise 3 — Create a callback to record results

Write a method `static void notifyName(String name, Consumer<String> callback)` that only calls `callback.accept(name)` when the name is not blank. Pass `System.out::println` or a lambda that appends to a list. Test with an empty name, `null`, and a valid name; state the method's handling contract.

### Exercise 4 — Distinguish consuming and transforming

Given `List<String> words = List.of("a", "bb", "ccc");`:
1. Use `Consumer<String>` and `forEach` to print the words.
2. Use `Function<String,Integer>` with `map` to create the list of lengths `[1, 2, 3]`.
3. Explain why you cannot directly replace `Function` with `Consumer` in step 2.

### Exercise 5 — Check correctness with side effects

From a list of orders with `amount`, compare two ways to compute the total: updating external state via `Consumer<Order>` and using `mapToInt(...).sum()`. Test with an empty list, duplicate data, and different orders. When the sum may exceed `int`, consider `mapToLong` or an appropriate monetary model. Explain your choice for production code.

### Exercise 6 — Specialized Consumers

Write an `IntConsumer` that prints the square of an integer and a `BiConsumer<String,Integer>` that prints a name and score. Explain the parameter-type difference and why `IntConsumer` can avoid boxing compared to `Consumer<Integer>`.

## 11. Self-check questions

**1. What does `Consumer<T>` take and what does it return?** It takes a value `T`; `accept` returns `void`.

**2. How many SAMs does `Consumer<T>` have?** One, which is `accept(T)`. `andThen` is a default method so it does not add a SAM.

**3. Does `andThen` pass a value from the first action to the second?** No. Both actions receive the same input, running sequentially when the composed consumer is called.

**4. What happens if the first action throws an exception?** The subsequent action is not executed and the exception propagates. Side effects already performed before the error may still remain.

**5. Is `Consumer` required to produce a side effect?** No. `void` only specifies returning no value; the actual effect depends on the implementation.

**6. When should you avoid `Consumer`?** When you need a result for further computation (`Function`), a boolean check (`Predicate`), or collecting results through a Stream without shared state.

**7. Why can calling `accept(null)` fail?** Because the generic `T` is a reference type with no non-null guarantee; a lambda or method reference may dereference `null`.

**8. With a parallel stream, is `Consumer` automatically safe?** No. Shared mutable state and the independence of side effects must be evaluated separately.

## 12. Summary and references

**`Consumer<T>` is a functional interface dedicated to representing an action `T -> void`.** `accept` is the single abstract method; `andThen` lets you chain actions in order, with the same input and no automatic rollback. When you need a new result, use `Function` or data aggregation. When you want to perform an action, you can pass `Consumer` as a callback, use it with `Iterable.forEach` or `Stream.forEach`, while explicitly managing side effects, exceptions, `null`, ordering, and concurrency.

Authoritative documentation to look up exact contracts: Java SE 17 Javadoc for `java.util.function.Consumer`, `java.util.function.BiConsumer`, `java.util.function.IntConsumer`, `java.lang.Iterable`, and `java.util.stream.Stream`.
