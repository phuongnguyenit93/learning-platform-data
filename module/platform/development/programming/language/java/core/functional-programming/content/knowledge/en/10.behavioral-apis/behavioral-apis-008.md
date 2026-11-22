# Recognizing Function and Consumer in CompletableFuture (Java 17+)

## 1. Context: CompletableFuture Accepts Behavior as Functional Interfaces

`CompletableFuture<T>` represents a task or result that may complete in the future with a value of type `T`, or complete exceptionally. It implements `Future<T>` and `CompletionStage<T>`. Methods such as `thenApply`, `thenAccept`, and `thenCompose` accept **behavior** as a lambda or method reference, allowing us to create dependent stages without having to manually call `get()` to wait for the result at each step.

To read the API correctly, the first question is: **Does the callback return a value that the next stage needs, or does it only consume the value?**

- **`Function<T,R>`** takes `T` and returns `R`: suitable for **transforming** data. The prominent method is `thenApply`.
- **`Consumer<T>`** takes `T` and returns no result: suitable for **processing/consuming** the result (logging, sending a notification, updating a data sink). The prominent method is `thenAccept`.
- **`Runnable`** does not receive the previous stage's result and returns no value: used with `thenRun`.
- In addition to those two interfaces, the API also uses `Supplier<T>`, `BiFunction<T,U,R>`, `BiConsumer<T,U>`, and variants with specialized semantics.

"Returns no result" in `Consumer` means the `accept` method has return type `void`; the stage created by `thenAccept` has type `CompletableFuture<Void>`, and when it succeeds, `join()` yields `null`. That does not mean `CompletableFuture<Void>` completes immediately or that the callback is not awaited.

## 2. Reading API Signatures to Distinguish Them

Consider the simplified signatures from `CompletionStage`/`CompletableFuture` (omitting wildcards and override details for focus):

~~~java
<U> CompletableFuture<U> thenApply(Function<? super T, ? extends U> fn);

CompletableFuture<Void> thenAccept(Consumer<? super T> action);

CompletableFuture<Void> thenRun(Runnable action);

<U> CompletableFuture<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
~~~

How to read them:

1. If the callback parameter is `Function<? super T, ? extends U>`, the result of the callback is a **new value U**; the next stage holds `U`.
2. If the callback is `Consumer<? super T>`, it **receives the result T** of the previous stage but does not produce a new result value. The next stage has type `Void`.
3. If the callback is `Runnable`, it has no parameter for the result `T`; it simply runs after the previous stage completes normally.
4. If the callback is `Function<T, CompletionStage<U>>`, the meaning is still "take T and return a value", but that value **is itself an asynchronous stage**. `thenCompose` links/flattens the inner stage into a single `U` stage.

In real code, you can use a method reference instead of a lambda when the signature is compatible:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("  Java  ");

CompletableFuture<String> trimmed =
        source.thenApply(String::trim); // Function<String, String>

CompletableFuture<Integer> length =
        trimmed.thenApply(String::length); // Function<String, Integer>

CompletableFuture<Void> printed =
        trimmed.thenAccept(System.out::println); // Consumer<String>
~~~

`printed` represents the completion of the print action; `length` represents an `Integer` result. These are **two independent dependent branches** from `trimmed`: each branch uses the same `String` value but has a different goal.

## 3. `thenApply`: Function Transforming T into U

Example:

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture(" java ");

CompletableFuture<Integer> number = future
        .thenApply(String::trim)
        .thenApply(String::length);

System.out.println(number.join()); // 4
~~~

Data flow:

~~~text
CompletableFuture<String> (" java ")
    │
    └─ thenApply(String::trim)       [Function<String, String>]
              │                      -> "java"
              └─ thenApply(String::length) [Function<String, Integer>]
                        │
                        └─ CompletableFuture<Integer> (4)
~~~

`thenApply` creates a new stage whose value is returned from `Function.apply`. If the previous stage completes normally with value `x`, the callback `fn.apply(x)` is invoked to produce the result for the dependent stage. If the callback throws an exception, the dependent stage completes exceptionally. If the previous stage already completed exceptionally, `thenApply` is normally **not invoked**; the exception propagates to the dependent stage.

You can picture it as:

~~~java
Function<String, Integer> parseLength = String::length;
CompletableFuture<Integer> result = future.thenApply(parseLength);
~~~

`Function` **must have an appropriate return value**. A lambda that only calls a `void`-returning method such as `s -> System.out.println(s)` is not suitable for `thenApply` when it does not return a `U` value.

### 3.1. Function Can Change the Type

~~~java
CompletableFuture<Integer> size =
        CompletableFuture.completedFuture("abc")
                .thenApply(String::length);
~~~

Here the input type is `String` and the output type is `Integer`. Do not infer from the name `thenApply` that the stage's type must stay the same.

## 4. `thenAccept`: Consumer Receiving T and Ending with Void

Example:

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture("Java");

CompletableFuture<Void> logged = future
        .thenAccept(value -> System.out.println("Received: " + value));

logged.join();
~~~

Stdout:

~~~text
Received: Java
~~~

Flow:

~~~text
CompletableFuture<String> ("Java")
    │
    └─ thenAccept(value -> print(value)) [Consumer<String>]
                 │
                 └─ CompletableFuture<Void> (completes normally)
~~~

Consumer has a single abstract method `void accept(T value)`. Therefore:

~~~java
Consumer<String> printer = System.out::println;
CompletableFuture<Void> completed = future.thenAccept(printer);
~~~

is a clear way to express using an action that depends on the result of `future`.

**Important note:** `thenAccept` does not pass the original data `T` through for further chaining. If you want to produce a new result after processing, consider `thenApply` with an intentional return value; if you need both a side action and to keep the original result, see `whenComplete` in section 8 or split into two stage branches.

~~~java
CompletableFuture<String> input =
        CompletableFuture.completedFuture("hello");

CompletableFuture<Void> sideEffect =
        input.thenAccept(System.out::println);

// Invalid: sideEffect.thenApply(String::length)
// because the previous stage has type Void, not String.
~~~

When the previous stage completes exceptionally, the Consumer of `thenAccept` does not run and the next stage also completes exceptionally. If `accept` itself throws an exception, the dependent stage also completes exceptionally.

### 4.1. How Is `thenRun` Different?

`thenRun(Runnable)` also returns a `Void` stage, but the callback **does not receive the previous stage's value**:

~~~java
CompletableFuture<Void> done =
        CompletableFuture.completedFuture("ignored")
                .thenRun(() -> System.out.println("Finished"));
~~~

`thenAccept(value -> ...)` can use `value`; `thenRun(() -> ...)` has no `value` parameter. Both only run after the dependent stage completes normally.

## 5. `thenCompose`: Function Returning Another CompletionStage

If the processing function is already an asynchronous API, its signature usually has the form `T -> CompletionStage<U>`. `thenCompose` takes that exact **Function** and chains the returned stage.

Suppose there is an API:

~~~java
static CompletableFuture<String> findNameAsync(int id) {
    return CompletableFuture.completedFuture("User-" + id);
}
~~~

Using `thenCompose`:

~~~java
CompletableFuture<String> name =
        CompletableFuture.completedFuture(7)
                .thenCompose(id -> findNameAsync(id));
// Equivalent: .thenCompose(Demo::findNameAsync)

System.out.println(name.join()); // User-7
~~~

If you use `thenApply` with the same async function:

~~~java
CompletableFuture<CompletableFuture<String>> nested =
        CompletableFuture.completedFuture(7)
                .thenApply(id -> findNameAsync(id));
~~~

`nested` has **two layers of future**, because `thenApply` keeps the future object returned by the callback as the "value" of the next stage. `thenCompose` creates a single `CompletableFuture<String>` that depends on both the previous stage and the stage created by the callback:

~~~text
thenApply(T -> CompletableFuture<U>):
    CompletableFuture<T>
      └─ CompletableFuture<CompletableFuture<U>>

thenCompose(T -> CompletableFuture<U>):
    CompletableFuture<T>
      └─ CompletableFuture<U>
~~~

Rule of thumb for recognition: If the callback returns a **synchronous value U**, use `thenApply`; if the callback returns a **`CompletionStage<U>`** and you want to chain the asynchronous flow, use `thenCompose`.

`thenCompose` does not use `Consumer` because the callback must return a stage, not `void`. Nor does it "wait by blocking" like calling `join()` inside the callback; it is composition of asynchronous stages.

## 6. Quick Recognition Table of Common APIs

| Method | Main callback | Stage result | Intent |
| --- | --- | --- | --- |
| `thenApply(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Transform the result |
| `thenApplyAsync(fn)` | `Function<T,U>` | `CompletableFuture<U>` | Transform, scheduled asynchronously |
| `thenAccept(action)` | `Consumer<T>` | `CompletableFuture<Void>` | Consume the result |
| `thenAcceptAsync(action)` | `Consumer<T>` | `CompletableFuture<Void>` | Consume, scheduled asynchronously |
| `thenRun(action)` | `Runnable` | `CompletableFuture<Void>` | Run an action without needing T |
| `thenCompose(fn)` | `Function<T,CompletionStage<U>>` | `CompletableFuture<U>` | Chain an async operation |
| `thenCombine(other,fn)` | `BiFunction<T,U,V>` | `CompletableFuture<V>` | Combine two values into a new value |
| `thenAcceptBoth(other,action)` | `BiConsumer<T,U>` | `CompletableFuture<Void>` | Consume two values |
| `exceptionally(fn)` | `Function<Throwable,T>` | `CompletableFuture<T>` | Recover from error with a value |
| `handle(fn)` | `BiFunction<T,Throwable,U>` | `CompletableFuture<U>` | Transform result or error into U |
| `whenComplete(action)` | `BiConsumer<T,Throwable>` | `CompletableFuture<T>` | Observe success or error |

The table uses simplified generic types for readability; the actual API has `? super`/`? extends` wildcards and some variants return `CompletionStage` when viewed through the `CompletionStage` interface. The core point is **the SAM type and the stage result type**.

`thenCombine` and `thenAcceptBoth` show the rule extended from one to two parameters: **BiFunction** returns a value; **BiConsumer** returns no value.

~~~java
CompletableFuture<Integer> a = CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b = CompletableFuture.completedFuture(3);

CompletableFuture<Integer> total =
        a.thenCombine(b, Integer::sum); // BiFunction<Integer,Integer,Integer>

CompletableFuture<Void> show =
        a.thenAcceptBoth(b, (x, y) -> System.out.println(x + y));
~~~

Not every API named `*Async` takes a `Function`: `supplyAsync` takes `Supplier<T>`, and `runAsync` takes `Runnable`.

## 7. Complete Java 17+ Example Running with Deterministic Stdout

Save as `CompletableFutureCallbacksDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

public class CompletableFutureCallbacksDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture(" java ");

        Function<String, String> trim = String::trim;
        CompletableFuture<Integer> length = source
                .thenApply(trim)
                .thenApply(String::length);
        System.out.println("length=" + length.join());

        Consumer<String> printer =
                s -> System.out.println("accept=" + s);
        CompletableFuture<Void> consumed = source
                .thenApply(String::trim)
                .thenAccept(printer);
        consumed.join();
        System.out.println("Void result=" + consumed.join());

        CompletableFuture<Void> ignored =
                source.thenRun(() -> System.out.println("run=done"));
        ignored.join();

        CompletableFuture<String> composed =
                CompletableFuture.completedFuture(7)
                        .thenCompose(id -> findNameAsync(id));
        System.out.println("composed=" + composed.join());

        CompletableFuture<Integer> failed =
                CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad"))
                        .thenApply(String::length);
        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> -1);
        System.out.println("recovered=" + recovered.join());

        CompletableFuture<String> handled =
                CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("oops"))
                        .handle((value, error) ->
                                error == null ? value.toUpperCase() : "fallback");
        System.out.println("handled=" + handled.join());

        AtomicInteger observations = new AtomicInteger();
        CompletableFuture<Integer> watched =
                CompletableFuture.completedFuture(4)
                        .whenComplete((value, error) ->
                                observations.incrementAndGet());
        watched.join();
        System.out.println("observed=" + observations.get());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> async =
                    CompletableFuture.supplyAsync(() -> "abc", pool)
                            .thenApplyAsync(String::length, pool);
            System.out.println("async=" + async.join());
        } finally {
            pool.shutdown();
        }
    }

    static CompletableFuture<String> findNameAsync(int id) {
        return CompletableFuture.completedFuture("User-" + id);
    }
}
~~~

Compile and run:

~~~bash
javac CompletableFutureCallbacksDemo.java
java CompletableFutureCallbacksDemo
~~~

Stdout:

~~~text
length=4
accept=java
Void result=null
run=done
composed=User-7
recovered=-1
handled=fallback
observed=1
async=3
~~~

Why is the output order predictable? The initial stages use `completedFuture` or `failedFuture`, so non-async callbacks can run immediately on the calling thread upon registration; the program calls `join()` at each step before printing the next line. The last part uses a dedicated executor, but the program only prints after `async.join()` completes. The example is designed to explain callbacks and return types, **not to rely on arbitrary scheduling order to demonstrate print order**.

## 8. Exception Handling: Function and Consumer Still Appear, with Different Meanings

### 8.1. `exceptionally` Accepts a Function to *Recover*

~~~java
CompletableFuture<Integer> number =
        CompletableFuture.<Integer>failedFuture(
                new IllegalStateException("unavailable"))
                .exceptionally(error -> 0);

System.out.println(number.join()); // 0
~~~

`exceptionally` takes `Function<Throwable, ? extends T>` to provide a **fallback value of type T** when the previous stage completes exceptionally. If the previous stage succeeds, the recovery callback **does not run**. This differs from `thenApply`: `thenApply` runs on the success branch; `exceptionally` runs on the failure branch.

An error-handling callback that only logs and returns no value is **not valid** as the entire argument to `exceptionally`:

~~~java
// Wrong because the lambda does not return Integer:
// failed.exceptionally(error -> System.out.println(error));
~~~

If you want to log and recover, write a lambda with a return value:

~~~java
CompletableFuture<Integer> safe = number.exceptionally(error -> {
    System.err.println(error.getMessage());
    return -1;
});
~~~

In this snippet, because `number` has already been successfully recovered to `0`, the next `exceptionally` does not run. This is intentional to illustrate that **where you place the recovery callback determines whether it receives the error**; to log the original error, attach the callback to the unrecovered failed stage.

### 8.2. `handle` Accepts a BiFunction to *Transform Both Cases*

~~~java
CompletableFuture<String> status =
        CompletableFuture.<String>failedFuture(
                new RuntimeException("service down"))
                .handle((value, error) ->
                        error == null ? value : "default");

System.out.println(status.join()); // default
~~~

`handle(BiFunction<T,Throwable,U>)` is called when the previous stage completes, whether successfully or exceptionally. Normally, on the success branch `error == null`, and on the error branch `error != null`; if needed, it can return a `U` different from `T`. The lambda has a **return value**, because the callback is a `BiFunction`.

### 8.3. `whenComplete` Accepts a BiConsumer to *Observe*

~~~java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("ok")
                .whenComplete((value, error) -> {
                    if (error == null) {
                        System.out.println("completed=" + value);
                    } else {
                        System.err.println("failed=" + error);
                    }
                });
~~~

`whenComplete(BiConsumer<T,Throwable>)` is commonly used for logging, metrics, lightweight cleanup, or observing both success and failure. It **does not change the success value**, and does not turn an error into a success merely by logging it. If the `whenComplete` callback throws an error, the downstream stage may complete exceptionally; if the original stage already failed, the original error takes precedence according to the API contract.

Distinguish clearly:

| Need | API | Why |
| --- | --- | --- |
| Transform a successful result | `thenApply` | `Function<T,U>` returns U |
| Use a successful result without producing a new U | `thenAccept` | `Consumer<T>` returns void |
| Recover from an error with a fallback value | `exceptionally` | `Function<Throwable,T>` returns T |
| Transform from either result or error | `handle` | `BiFunction<T,Throwable,U>` returns U |
| Record result or error and preserve original state | `whenComplete` | `BiConsumer<T,Throwable>` returns void |

## 9. Synchronous, Asynchronous, and Callback Execution Threads

The name `CompletableFuture` can easily mislead people into thinking every callback runs on a separate thread. In reality:

- `thenApply`, `thenAccept`, and `thenCompose` **without the Async suffix** may run on the thread that completes the previous stage or another thread registering/driving completion; **do not assume a specific fixed thread**.
- `thenApplyAsync`, `thenAcceptAsync`, and `thenComposeAsync` are variants that schedule the callback asynchronously. When no executor is passed, `CompletableFuture` typically uses `ForkJoinPool.commonPool()` per the class's execution policy (with a fallback when the common pool lacks sufficient parallelism).
- Pass an `Executor` to the corresponding overloads when you need to control where execution happens or how threads are provisioned.
- `thenApply` and `thenAccept` differ in the **callback contract**; the `Async` variants differ in **how execution is scheduled**. Those are two independent axes of distinction.

Example with a custom executor (placed inside a program with `main`):

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<Void> pipeline =
            CompletableFuture.supplyAsync(() -> "data", executor)
                    .thenApplyAsync(String::toUpperCase, executor)
                    .thenAcceptAsync(System.out::println, executor);

    pipeline.join();
} finally {
    executor.shutdown();
}
~~~

When using callbacks with blocking I/O, you should not overuse the common pool without considering load characteristics and executor strategy. The fact that `thenAccept` is a Consumer does not by itself determine which thread the callback runs on synchronously.

`join()` and `get()` are calls that **wait for the result**; they should be placed at the boundary where the result is actually needed, avoiding arbitrary `join()` calls inside each async callback because that can block and reduce asynchronous composability. `join()` throws `CompletionException` for wrapped errors; `get()` can throw checked `ExecutionException` and `InterruptedException`. This does not change the nature of `Function`/`Consumer`, but it affects how you handle pipeline errors.

## 10. Nulls, Errors, Side Effects, and Differences in Chainability

### 10.1. A Null Result Is Valid, but Callbacks Must Be Prepared

~~~java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

CompletableFuture<String> copied =
        empty.thenApply(value -> value); // Completes with null.
~~~

Here `thenApply` can still run because the previous stage **completed normally**, even though the value is null. If you write `String::length`, receiving a null receiver will throw `NullPointerException` and the dependent stage becomes an exceptional completion. `thenAccept` can also receive null as its argument; the Consumer author must decide how to handle it.

### 10.2. Side Effects and Errors in Consumer Are Not "Swallowed"

~~~java
CompletableFuture<Void> logged =
        CompletableFuture.completedFuture("x")
                .thenAccept(value -> {
                    throw new IllegalStateException("log failed");
                });

// logged.join() will throw CompletionException
// with a cause related to IllegalStateException.
~~~

Having no `U` result means there is no business value to pass forward, **not that the callback cannot fail**. If the Consumer's side effect matters, you must observe or integrate its `CompletableFuture<Void>` stage into the appropriate orchestration flow.

### 10.3. Consumer Is Not a Way to Preserve the Value

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("abc");

CompletableFuture<Void> consumed =
        source.thenAccept(System.out::println); // loses T in this branch

CompletableFuture<String> kept =
        source.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println(value);
            }
        }); // still CompletableFuture<String>
~~~

`whenComplete` is designed for observing results, though both examples have side effects; therefore, be careful if callbacks are attached multiple times or if the flow has retries at the application layer.

### 10.4. Ordering Between Multiple Branches Is Not Guaranteed

If you attach two `thenAccept` calls to the same async source, both are dependent stages and there is no default guarantee on their completion order. If ordering is a business requirement, chain stages explicitly via `thenCompose` or `thenRun`/`thenAccept` and wait on the corresponding combined stage.

## 11. Common Mistakes and How to Fix Them

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using `thenApply(s -> println(s))` | `println` returns void, but Function must return U | Use `thenAccept(System.out::println)` |
| Expecting `thenAccept` to return `T` | Consumer does not produce a value U | Use `thenApply` or `whenComplete` depending on the goal |
| Using `thenApply` for a Future-returning function and expecting flattening | `thenApply` keeps the inner Future as the value | Use `thenCompose` |
| Using `thenAccept` to chain an async API | Consumer does not return a stage to compose | Use `thenCompose` |
| Assuming `thenRun` receives the previous result | Runnable has no parameters | Use `thenAccept` if you need T |
| Assuming `whenComplete` has handled/resolved the error | BiConsumer only observes, does not provide a recovery value | Use `exceptionally` or `handle` |
| Writing `exceptionally(e -> log(e))` without returning T | Function requires an appropriate return value | Log and then `return fallback;` |
| Thinking every callback runs on a new thread | Non-Async versions make no specific thread guarantee | Use the Async overload + Executor if needed |
| Calling `join()` repeatedly inside each callback | Blocking makes the pipeline inefficient | Chain with `thenApply`/`thenCompose`, wait at the end |
| Ignoring the `Void` stage after a side effect | Callback errors still live on the dependent stage | Combine/check that stage with `join`, `whenComplete`, or monitoring |

## 12. Short Exercises with Answers

**Question 1.** Given `CompletableFuture<String> f`. You want to turn the string into an integer length—which API and interface should you use?

Answer: `f.thenApply(String::length)`, corresponding to `Function<String,Integer>` and returning `CompletableFuture<Integer>`.

**Question 2.** You want to print the String result to the console, with no need for a new result value?

Answer: `f.thenAccept(System.out::println)`, corresponding to `Consumer<String>`, returning `CompletableFuture<Void>`.

**Question 3.** Which callback receives the result and returns a `CompletableFuture<User>` from another API to continue without creating two layers of Future?

Answer: `thenCompose(id -> findUserAsync(id))`. This is a Function returning `CompletionStage<User>`, not a Consumer.

**Question 4.** Does `thenAccept` run when the previous future completes exceptionally?

Answer: No. The dependent stage completes exceptionally; you need `exceptionally`, `handle`, or `whenComplete` to handle/observe the error path as intended.

**Question 5.** Why does `handle` use `BiFunction` while `whenComplete` uses `BiConsumer`?

Answer: Both receive `(value, error)`, but `handle` **returns a new U** to determine the next result, whereas `whenComplete` **returns no value** and is used primarily for observing while preserving the previous stage's state.

**Question 6.** Do `thenApplyAsync` and `thenAcceptAsync` take the same kind of callback?

Answer: No. `thenApplyAsync` takes a Function, `thenAcceptAsync` takes a Consumer; the `Async` suffix only relates to the execution scheduling mechanism.

## Takeaways

To recognize callbacks in `CompletableFuture`, read the method signature and look at **the result the behavior must return**:

- **`Function<T,U>` = takes T, returns U**, commonly seen in `thenApply` (transform) and `thenCompose` (returns a CompletionStage to chain async).
- **`Consumer<T>` = takes T, returns void**, commonly seen in `thenAccept` (consume result).
- **`Runnable` = takes no T, returns void**, commonly seen in `thenRun`.
- **`BiFunction`** turns two inputs into a new result; **`BiConsumer`** observes/consumes two inputs and returns no result.
- For error handling, **`exceptionally` = recovery Function**, **`handle` = transforming BiFunction**, and **`whenComplete` = observing BiConsumer**.

Stages returning `Void` still carry meaning for **completion and failure**. Choosing the right interface preserves data types, chains stages accurately, and handles exceptions intentionally.
