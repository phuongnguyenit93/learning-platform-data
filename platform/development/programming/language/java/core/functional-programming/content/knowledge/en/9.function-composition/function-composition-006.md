# `Consumer.andThen()` and the Impact When the Preceding Operation Throws an Exception

## 1. What is `Consumer.andThen()` used for?

In `java.util.function`, `Consumer<T>` is a functional interface representing an **operation that accepts a single value of type `T` and returns no value**. Its abstract method is:

```java
void accept(T value);
```

`Consumer<T>` commonly appears in callbacks, logging, event handling, writing data, or `Iterable.forEach` and `Stream.forEach`. To chain two actions in a **defined order**, Java provides the default method `andThen`:

```java
default Consumer<T> andThen(Consumer<? super T> after)
```

Behaviorally, `first.andThen(second)` creates **a new Consumer**. When `accept(input)` is called on the new Consumer, Java:

1. Calls `first.accept(input)`.
2. If step 1 **completes normally**, calls `second.accept(input)`.
3. If a step **throws an exception**, the exception propagates to the caller; subsequent steps in the chain **do not run**.

Both actions receive **the same input**, rather than receiving a result from the preceding action. `Consumer.accept` returns `void`, so there is no value to pass to the next step.

Example:

```java
Consumer<String> save = id -> System.out.println("Save " + id);
Consumer<String> notify = id -> System.out.println("Notify " + id);

Consumer<String> workflow = save.andThen(notify);
workflow.accept("A01");
```

Output:

```text
Save A01
Notify A01
```

This is an example placed inside a method or `jshell` (requiring `import java.util.function.Consumer;`). The statement creating `workflow` **does not execute** `save` or `notify` yet. The two actions only actually run when `workflow.accept("A01")` is called.

**Key point of this lesson:** if `save` throws an exception, `notify` does not run. If `save` already wrote data before throwing, that data may still remain written. `andThen` does not catch errors, restore data, or perform rollback.

## 2. Ordering contract and exception propagation

The meaning of a `first.andThen(second)` chain can be described with Java pseudocode:

```java
Consumer<T> combined = input -> {
    first.accept(input);
    second.accept(input);
};
```

This is **conceptual code** (assuming `T`, `first`, `second` are already declared in a generic method), not a standalone runnable snippet. It helps show that the second call depends on the first call returning normally. The real implementation also checks that `after` is not `null` immediately when creating the chain.

| Scenario | `first.accept(x)` | `second.accept(x)` | Result of `combined.accept(x)` |
| --- | --- | --- | --- |
| Both succeed | Runs | Runs after `first` | Completes normally |
| `first` throws an exception | Runs up to the throw point | **Does not run** | Throws the exception from `first` |
| `first` succeeds, `second` throws | Runs | Runs up to the throw point | Throws the exception from `second` |
| `after == null` in `andThen(null)` | **Has not run** | No valid action | Throws `NullPointerException` upon composing |
| Only creating `combined` without `accept` | **Has not run** | **Has not run** | Produces the composed Consumer object |

When writing `a.andThen(b).andThen(c)`, the order for a single `accept(x)` call is `a → b → c`. If `b` throws an exception, `c` is skipped, even though `a` has already completed. This is the **sequential execution order** of the action chain within that call, not an asynchronous execution mechanism or transaction coordinator.

### Four things not to assume

- **No "run the next step on failure" condition:** `andThen` is not like `finally`.
- **No rollback:** side effects that already occurred may remain.
- **No automatic retry:** if `first`/`second` fails, `andThen` does not retry.
- **No automatic exception catching:** errors continue propagating outward, unless **the code of a Consumer itself** or the caller of `accept` handles them.

## 3. Complete, runnable Java 17 example

The program demonstrates four scenarios: the entire chain succeeds, the first validation step fails, the second step fails after the first step has mutated state, and a `null` `after` argument.

Create **`ConsumerAndThenDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerAndThenDemo {
    public static void main(String[] args) {
        List<String> trace = new ArrayList<>();

        Consumer<String> validate = id -> {
            trace.add("validate:" + id);
            if (id.startsWith("X")) {
                throw new IllegalArgumentException("blocked " + id);
            }
        };

        Consumer<String> save =
                id -> trace.add("save:" + id);
        Consumer<String> notify =
                id -> trace.add("notify:" + id);

        Consumer<String> workflow =
                validate.andThen(save).andThen(notify);

        // Scenario 1: all steps succeed.
        workflow.accept("A01");

        // Scenario 2: validate throws an exception; save/notify do not run.
        try {
            workflow.accept("X01");
        } catch (IllegalArgumentException ex) {
            trace.add("caught:" + ex.getMessage());
        }

        System.out.println("Trace 1: " + trace);

        // Scenario 3: first action ran, second action fails.
        List<String> effects = new ArrayList<>();

        Consumer<String> charge =
                id -> effects.add("charged:" + id);

        Consumer<String> sendEmail = id -> {
            effects.add("email-attempt:" + id);
            throw new IllegalStateException("mail offline");
        };

        Consumer<String> finish =
                id -> effects.add("finished:" + id);

        try {
            charge.andThen(sendEmail)
                    .andThen(finish)
                    .accept("B02");
        } catch (IllegalStateException ex) {
            effects.add("caught:" + ex.getMessage());
        }

        System.out.println("Trace 2: " + effects);

        // Scenario 4: null after argument is rejected upon composing.
        try {
            save.andThen(null);
        } catch (NullPointerException ex) {
            System.out.println("Null after: NullPointerException");
        }

        System.out.println("Final trace: " + trace);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 ConsumerAndThenDemo.java
java ConsumerAndThenDemo
```

**Exact stdout:**

```text
Trace 1: [validate:A01, save:A01, notify:A01, validate:X01, caught:blocked X01]
Trace 2: [charged:B02, email-attempt:B02, caught:mail offline]
Null after: NullPointerException
Final trace: [validate:A01, save:A01, notify:A01, validate:X01, caught:blocked X01]
```

### Explaining the results

**Scenario 1 — Success.** `workflow.accept("A01")` runs `validate`, `save`, and `notify` with the value `"A01"`. Since all three steps complete normally, the `trace` list has the first three elements: `validate:A01`, `save:A01`, `notify:A01`.

**Scenario 2 — First step throws an exception.** With `"X01"`, `validate` records `validate:X01` into trace and then throws `IllegalArgumentException("blocked X01")`. Therefore `save` and `notify` **are not called** for `"X01"`. The `catch` block outside the `accept` call appends `caught:blocked X01`. The four previously recorded elements remain in `trace`: throwing an exception does not erase logs.

**Scenario 3 — Second step throws an exception.** `charge` records `charged:B02`. `sendEmail` records `email-attempt:B02` and then throws `IllegalStateException`. `finish` **does not run** because the chain stops at the failing step. The `catch` block appends `caught:mail offline`. The entry `charged:B02` remains in `effects`, showing that `andThen` does not undo a completed side effect. In a real system, a recorded payment cannot be assumed cancelled just because an email fails.

**Scenario 4 — `andThen(null)`.** `Consumer.andThen` requires a non-`null` `after` argument. `NullPointerException` occurs **right when creating the chain**, before `accept` can run. Thus `save` also does not run, and `Final trace` remains identical to `Trace 1`.

> The `List<String>` instances in the demo are just tools to record event order. They are used sequentially on a single thread. Do not use a shared `ArrayList` to record concurrently from multiple `accept` calls without protection.

## 4. Composition order with three or more Consumers

`andThen` returns a new `Consumer<T>`, so it can be chained further:

```java
Consumer<String> a = s -> System.out.println("A " + s);
Consumer<String> b = s -> System.out.println("B " + s);
Consumer<String> c = s -> System.out.println("C " + s);

Consumer<String> pipeline = a.andThen(b).andThen(c);
pipeline.accept("X");
```

Result:

```text
A X
B X
C X
```

In terms of order, `a.andThen(b).andThen(c)` is equivalent to `a.andThen(b.andThen(c))` for actions that complete normally. In both compositions, a single `accept` goes through `a`, `b`, then `c`; if an earlier step throws an exception, later steps are skipped. This is not a promise that side effects of actions can be freely reordered: for instance, `save.andThen(notify)` and `notify.andThen(save)` can produce different business behavior.

### Every step receives the same input value

```java
Consumer<String> trimButIgnore = s -> s.trim();
Consumer<String> print = System.out::println;

trimButIgnore.andThen(print).accept("  Java  ");
```

The printed line still has spaces around `Java`! `String.trim()` creates a return value and **does not mutate** `String`; because `Consumer` returns `void`, the result of `trim` is discarded. `print` receives the exact original input string `"  Java  "`.

If you want **the output of the previous step to be the input of the next step**, use `Function<T,R>` with `andThen`, not `Consumer<T>`:

```java
import java.util.function.Function;

Function<String, String> trim = String::trim;
Function<String, String> upper =
        s -> s.toUpperCase(java.util.Locale.ROOT);

String normalized = trim.andThen(upper).apply("  java  ");
// normalized == "JAVA"
```

**Exact comparison:**

| Feature | `Consumer<T>.andThen(after)` | `Function<T,R>.andThen(after)` |
| --- | --- | --- |
| Purpose | Compose actions | Compose transformations |
| Execution method | `accept(T)` | `apply(T)` |
| Output | `void` | Value `R`/new type |
| Parameter received by second step | Same original `T` value | Result produced by the first function |
| If first step throws an exception | Next step is not called | Next step is not called |
| Automatic rollback of side effects | No | No |

## 5. What exactly happens if the first operation throws an exception?

Consider:

```java
Consumer<String> first = value -> {
    System.out.println("before failure");
    throw new IllegalArgumentException("invalid");
};

Consumer<String> second =
        value -> System.out.println("second");

Consumer<String> composed = first.andThen(second);
composed.accept("A");
```

This snippet is a **method illustration** and intentionally throws an exception. When run from a method that does not catch exceptions:

1. Prints `before failure`.
2. Throws `IllegalArgumentException("invalid")`.
3. **Does not** print `second`.
4. The call `composed.accept("A")` terminates with the exception; Java continues propagating the error up the call stack.

Do not hardcode an exact *stack trace* for this example: file names, line numbers, and runtime environments can make the stack trace differ. The output printed before the error and the skipping of the next step are the properties to verify.

If there is another print statement after `composed.accept` without an appropriate `try/catch` or `finally`, that statement does not run in normal execution flow. To control errors, the caller must catch the exception or design each action to handle errors per contract.

### Exception in the second step

If `first` completes, `second` starts and may throw. That exception propagates outward; `andThen` does not distinguish "error from first" and "error from second" by altering the exception. In a chain `first.andThen(second).andThen(third)`, if `second` throws, `third` also does not run.

For severe `Error`s, the same abrupt-termination propagation rule applies: if the preceding call does not complete normally, the next step is not run. Do not broadly catch `Throwable` just to continue a business workflow; system errors may not be suitable for recovery.

## 6. Side effects that already occurred still persist

A `Consumer` often performs side effects: adding an element to a `List`, updating a field, writing logs, sending messages, writing to a database, or calling an HTTP API. When the first action **has already produced a side effect** and then throws an exception (or a later step throws), `andThen` **has no mechanism to undo it**.

Timeline example:

```text
accept(order)
    |
    v
[charge(order)] -- money charged / event recorded
    |
    v
[sendEmail(order)] -- error
    X
[markFinished(order)] -- does not run
```

The final state can be "money charged but email not sent". That is different from "all steps fail and the system automatically reverts to its old state".

This is why `andThen` is **not** a transaction manager, saga orchestrator, retry framework, or error handler. Actions are simply called one after another according to `Consumer`'s contract. Whether a step has lasting effect or can be undone depends on the system it acts upon.

### Be careful with retries

If the caller catches an exception and retries the **entire** chain, a step that succeeded on the previous attempt may run again:

```java
// Illustrative business code, not a standalone program.
// try {
//     charge.andThen(sendEmail).accept(order);
// } catch (RuntimeException ex) {
//     charge.andThen(sendEmail).accept(order); // Could charge again!
// }
```

Do not automatically retry when actions have non-**idempotent** side effects. In real processing, you may need idempotency keys, state checks, deduplication, outbox, compensating actions, or transactions. Choose the mechanism according to the nature of the system: for example, database operations inside a transaction can roll back when appropriate, whereas sending emails or calling external services are not automatically part of the same database transaction.

## 7. Error handling: choosing where to catch exceptions based on the goal

### Approach A — Let the error propagate, caller decides

Suitable when an error must stop the entire chain:

```java
try {
    validate.andThen(save).andThen(notify).accept("X01");
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}
```

If `validate` throws, `save` and `notify` do not run. The caller can return an API error, mark a failed status, or handle it per the application contract. Catching the error outside **does not make the subsequent steps run**.

### Approach B — Handle the error *inside* an action

Only suitable if continuing after the error is intentional. For example, logging is a "best effort" action where a logging failure must not block updating another metric:

```java
Consumer<String> safeLog = value -> {
    try {
        writeLog(value); // Assumes this method is available.
    } catch (RuntimeException ex) {
        // Here the application must have an appropriate error-recording policy.
    }
};

Consumer<String> next = value -> updateMetric(value);
safeLog.andThen(next).accept("A01");
```

This is **illustrative code**, where `writeLog` and `updateMetric` represent methods in the application, not built-in JDK definitions. When `safeLog` catches the exception itself and finishes normally, `next` is called. However, do not use this approach to swallow **validate** or **charge** errors: letting the next step continue could violate business rules. Catch the right exception types, track errors thoroughly, and consider the goal of each action.

### Approach C — Always perform cleanup with `finally`

If cleanup must run even if an action throws, put it in `finally` or use `try-with-resources` when managing resources:

```java
try {
    first.andThen(second).accept(value);
} finally {
    cleanup.accept(value);
}
```

This example assumes `first`, `second`, `cleanup`, and `value` are already declared. `finally` runs when control leaves `try` normally or abruptly, including when an action inside `try` throws an exception. If `cleanup` also throws, consider how to preserve information about the original error; resource handling with `try-with-resources` is often helpful because it supports *suppressed exceptions*.

**Do not replace `finally` with `first.andThen(cleanup)`** if the goal is ensuring cleanup is called: when `first` throws, `cleanup` in `andThen` does not run.

### Approach D — Use a value representing the result for the next processing step

When you need to branch on success/failure and return detailed information, you can design a `Function<Input, Result>` returning a result type containing success/error status, and then decide whether to perform side effects at the orchestration layer. `Consumer<T>` only has `accept(T)` returning `void`, so it does not directly provide a channel for returning business status.

Another option is validating before creating the action chain, e.g., parsing/validating into a verified value before performing writes. This reduces the chance of side effects occurring before invalid data is detected, though it **does not eliminate all errors** from network, I/O, or concurrency.

## 8. `andThen(null)` and a null input value are different

The call:

```java
Consumer<String> print = System.out::println;
// print.andThen(null); // Throws NullPointerException immediately upon composing.
```

Differs from:

```java
Consumer<String> print = System.out::println;
print.accept(null); // PrintStream.println(String) prints "null".
```

`after == null` is rejected by `Consumer.andThen` per contract. But whether `value == null` when calling `accept` is accepted **depends on each Consumer**: `System.out.println` has its own null handling, whereas `value -> value.length()` will throw `NullPointerException`. Therefore, specify null-input rules at API boundaries instead of assuming all Consumers share the same policy.

## 9. Checked exceptions and unchecked exceptions

The abstract method of `Consumer<T>` is `void accept(T t)` which **does not declare `throws` for any checked exception**. Therefore, a lambda/method reference passed to `Consumer<T>` cannot freely throw an uncaught checked exception, such as `IOException`.

Compilation error example:

```java
// INVALID if writeToFile declares throws IOException:
// Consumer<String> write = value -> writeToFile(value);
```

It can be handled right inside the action:

```java
Consumer<String> write = value -> {
    try {
        writeToFile(value); // Method in the application.
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(ex);
    }
};
```

This is an **illustrative snippet** with `writeToFile` assumed to exist. `UncheckedIOException` is an unchecked exception, so when it is thrown through an `andThen` chain, subsequent steps are still skipped according to the same rule. Converting exceptions should have a clear reason; not every error should be wrapped as an unchecked exception.

Conversely, `IllegalArgumentException` or `IllegalStateException` are unchecked exceptions and can be thrown directly from a Consumer, as in the complete program.

## 10. `andThen` does not automatically guarantee thread safety

`first.andThen(second)` performs two calls in order within **each `accept` invocation**, but if multiple threads concurrently call `accept` on the same composed Consumer, calls **can interleave** with each other:

```text
Thread A: first(A) -------- second(A)
Thread B:      first(B) -------- second(B)
```

Thus the global order is not necessarily `first(A), second(A), first(B), second(B)`. If actions touch an `ArrayList`, a plain counter, or shared resources, you must consider synchronization, state ownership design, or routing data through an appropriate queue/actor/transaction.

In Java Streams, using `parallelStream().forEach(composedConsumer)` can invoke the same Consumer on multiple elements simultaneously. `forEach` on a parallel stream also does not guarantee encounter order of side effects. If the requirement is only transforming/collecting data, prefer `map`, `reduce`, `collect`, or `toList`; `andThen` is better suited for **a chain of actions with well-defined side effects**.

Even when individual actions are thread-safe, "execute first then second" on an input **is not automatically an atomic transaction** when interleaved with other calls.

## 11. Distinguishing `Consumer.andThen` and related APIs

| API | What is composed? | Behavior when first step throws |
| --- | --- | --- |
| `Consumer<T>.andThen(Consumer<? super T>)` | Two actions receiving the same `T` | Next step does not run |
| `BiConsumer<T,U>.andThen(BiConsumer<? super T,? super U>)` | Two actions receiving the same `T,U` pair | Next step does not run |
| `Function<T,R>.andThen(Function<? super R,? extends V>)` | Two transformations, output of first step to next step | Next step does not run |
| `Function<T,R>.compose(Function<? super V,? extends T>)` | `before` function then current function | Current function does not run if `before` fails |
| `Predicate<T>.and(Predicate<? super T>)` | Two logical conditions | Can short-circuit when first condition is `false`; if it throws, error propagates |

Do not confuse the **execution order** of `Consumer.andThen` with `Predicate.and`: `Predicate.and` is a logical operation, so when the first condition returns `false`, the second condition may not be evaluated due to short-circuiting, even without an exception. For `Consumer.andThen`, if the first action completes normally, the second action is called regardless of what it printed or how it mutated state, because `Consumer` returns no boolean or status.

## 12. Common mistakes

**Mistake 1 — Thinking `andThen` always runs both steps.** If the first step throws, the next step does not run. Write tests for both the success path and error paths.

**Mistake 2 — Thinking an exception triggers rollback.** Side effects that occurred before the throw may still exist. Do not re-run a payment/order recording workflow without an idempotency strategy.

**Mistake 3 — Using `andThen(cleanup)` instead of `finally`.** Cleanup is skipped when the first action throws; use `try/finally` or `try-with-resources` depending on the resource type.

**Mistake 4 — Catching all exceptions and ignoring them so the next step runs.** This can hide data validation or payment failures. Only recover when business rules truly allow it.

**Mistake 5 — Expecting the output of the first action to become the input of the next action.** Both Consumers receive the same `T`; use `Function.andThen` if you want to chain output/input values.

**Mistake 6 — Assuming creating the chain already runs it.** `first.andThen(second)` returns a Consumer; actions happen when `accept` is called.

**Mistake 7 — Thinking `andThen` runs in parallel.** Its contract describes sequential order per invocation; concurrency only occurs if the caller invokes from multiple threads or an action spawns asynchronous work itself.

**Mistake 8 — Confusing exceptions in step one and step two.** When diagnostics are needed, name actions clearly, log appropriate context, and let the original exception be identifiable. Do not rely on `andThen` to classify errors.

**Mistake 9 — Passing `null` for `after`.** `andThen(null)` throws `NullPointerException` upon composing. Distinguish this from a null input value to `accept`.

**Mistake 10 — Using Consumer for a transformation that needs to return data.** `Consumer` discards results; if the next step needs the processed value, use `Function` or build an explicit intermediate data model.

## 13. Practice exercises

1. Create three Consumers `a`, `b`, `c`, each appending its step name to a `List<String>`. Call `a.andThen(b).andThen(c).accept("A")`. Predict the exact `List` after the call.
2. Replace `b` with a Consumer that throws `IllegalStateException("B failed")` **before recording its trace**. After catching the exception outside `accept`, which elements remain in the `List`? Why did `c` not run?
3. Make `a` record `a:A` and then throw. When calling `a.andThen(b).accept("A")`, is `a:A` still in the list? Distinguish between "a side effect already occurred" and "the action completed normally".
4. In `ConsumerAndThenDemo`, replace `workflow.accept("X01")` with `workflow.accept("A02")`. Predict the three additional entries in `Trace 1` corresponding to `validate`, `save`, `notify`, with no `caught:blocked X01`.
5. Try `Consumer<String> c = System.out::println; c.andThen(null);`. Determine when `NullPointerException` occurs and whether `println` runs.
6. Write an example `first.andThen(cleanup)` where `first` throws an exception; then fix it to `try { first.accept(x); } finally { cleanup.accept(x); }`. Compare the trace before and after.
7. Suppose `charge` can deduct real money and `sendEmail` can fail. Analyze why retrying the entire `charge.andThen(sendEmail)` risks charging twice; propose an idempotency key or an appropriate failure-handling mechanism.
8. Write a `Function<String,String>` that trims whitespace and chain it with an uppercase function using `andThen`. Compare with a `Consumer<String>` that trims whitespace but discards the result: which string does the subsequent print step receive?
9. Analyze an application where multiple threads call the same `Consumer`. Why does the order `first(x)` before `second(x)` not guarantee every call executes as a transaction?
10. Create a `Consumer<String> validate` that throws an exception on an empty string; design a test verifying `save` **is not called** when `validate` fails and **is called exactly once** when data is valid.

## 14. Checklist when applying `Consumer.andThen`

- Identify **which action must run first** and which action should only run when the previous step succeeds.
- Identify **which exception types** each step can throw, which caller will handle them, and whether the next step should continue.
- Identify **existing side effects** if a step fails midway; do not assume rollback.
- For tasks requiring retries, check **idempotency**, transactions, or compensating mechanisms.
- If cleanup is needed despite errors, use `finally`/`try-with-resources` rather than just chaining `andThen`.
- If a transformed value needs to be passed to the next step, use `Function.andThen` or build an intermediate data model.
- If callbacks can run concurrently, check thread safety and ordering rules across invocations.
- Test at least three paths: **success**, **first step fails**, **later step fails**; verify both exceptions and any remaining side effects.

**Technical conclusion:** `Consumer.andThen` is an operation for **chaining `void` actions in sequence**. When a preceding action throws an exception, the subsequent action does not run and the exception propagates outward; changes that already occurred before the throw point may still persist. Understanding this small contract helps avoid major bugs in event handling, data updates, retries, and business logic with side effects.
