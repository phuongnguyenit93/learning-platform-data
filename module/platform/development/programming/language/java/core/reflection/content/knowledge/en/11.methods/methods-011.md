# `Method.invoke` does not automatically wait for a returned `Future` or `CompletionStage`

## 1. The nature of `Method.invoke` when a method returns an asynchronous result

`java.lang.reflect.Method.invoke(Object receiver, Object... args)` **calls the target method and waits for that method call itself to return or throw an error**. If the called method returns `Future<T>`, `CompletionStage<T>`, or `CompletableFuture<T>`, the return value of `invoke` is the **Future/Stage object** (typed as `Object`). `invoke` does not automatically call `get()`, `join()`, wait for completion, or unwrap the inner value `T`.

Distinguish three milestones:

1. **Invocation:** Reflection performs access checks, accepts arguments, and runs the Java method body.
2. **Return:** the method body returns a reference to a `Future`/`CompletionStage`. The `Method.invoke` call finishes as soon as that value is obtained, even if the task it represents is not done yet.
3. **Completion:** the task completes successfully, fails, or is cancelled later; the caller decides to observe or wait for the result using appropriate async APIs.

Illustrative example placed inside a method with valid `service` and `Service`:

```java
Method m = Service.class.getMethod("loadAsync");
Object returned = m.invoke(service); // May immediately return an incomplete CompletionStage
CompletionStage<?> stage = (CompletionStage<?>) returned;
Object value = stage.toCompletableFuture().join(); // Actively wait if not yet completed
```

**Important note:** Reflection does not create threads on its own and does not make a synchronous method asynchronous. If **the target method body itself** executes `Thread.sleep`, a blocking I/O query, or `future.get()` **before returning**, the thread executing `invoke` still has to wait for that method body to finish. Conversely, a method may return an already completed `CompletableFuture.completedFuture(value)`, so reading the result afterward requires no waiting. Whether the async object is already completed depends on the target method's logic, not on Reflection.

The return type of `Method.invoke` is always declared as `Object`: Java boxes primitive results; `void` methods yield `null`. If a method merely starts a background task and returns `void`, Reflection likewise only receives `null` and has **no Future to wait on** through its return value.

## 2. Three common async types

| Type | Characteristics | If waiting is needed | If chaining processing is needed |
| --- | --- | --- | --- |
| `Future<T>` | Focuses on the result, `isDone`, `get`, `cancel` | `future.get()` or `get(timeout, unit)` | The `Future` interface does not define callback composition |
| `CompletionStage<T>` | Represents a stage and dependencies between stages | `stage.toCompletableFuture().get()` or `join()` | `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally`, ... |
| `CompletableFuture<T>` | Implements **both** `Future<T>` and `CompletionStage<T>` | `get` or `join` | Has the full suite of composition APIs |

**`Future` and `CompletionStage` do not extend each other.** For example, the result of `ExecutorService.submit(...)` is only guaranteed to implement `Future`, not necessarily `CompletionStage`. A custom `CompletionStage` implementation does not necessarily implement `Future` either. `CompletableFuture` is a case that supports both; do not cast an arbitrary `Future<?>` to `CompletableFuture<?>`.

`Future.isDone() == true` **does not mean the task succeeded**: it also returns `true` when cancelled or completed exceptionally. You must observe the result, error, or cancellation status via the specific API.

## 3. Full Java 17+ example: `invoke` does not wait for completion

Save the entire program below in **`ReflectAsyncDemo.java`**, without a `package` declaration.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Future;

public class ReflectAsyncDemo {
    private static final CompletableFuture<String> pendingFuture =
            new CompletableFuture<>();
    private static final CompletableFuture<String> pendingStage =
            new CompletableFuture<>();

    public static Future<String> findLater() {
        return pendingFuture;
    }

    public static CompletionStage<String> loadLater() {
        return pendingStage;
    }

    public static CompletionStage<String> failedLater() {
        return CompletableFuture.failedFuture(
                new IllegalStateException("async-failure"));
    }

    public static CompletionStage<String> failBeforeReturn() {
        throw new IllegalArgumentException("sync-failure");
    }

    public static void main(String[] args) throws Exception {
        Method find = ReflectAsyncDemo.class.getMethod("findLater");
        Method load = ReflectAsyncDemo.class.getMethod("loadLater");

        Object rawFuture = find.invoke(null);
        Object rawStage = load.invoke(null);

        System.out.println("Future result: " + (rawFuture instanceof Future<?>));
        System.out.println("Stage result: "
                + (rawStage instanceof CompletionStage<?>));

        Future<?> future = (Future<?>) rawFuture;
        CompletionStage<?> stage = (CompletionStage<?>) rawStage;
        System.out.println("Future done before completion: " + future.isDone());
        System.out.println("Stage done before completion: "
                + stage.toCompletableFuture().isDone());

        pendingFuture.complete("future-ok");
        pendingStage.complete("stage-ok");

        System.out.println("Future get: " + future.get());
        System.out.println("Stage join: " + stage.toCompletableFuture().join());

        CompletionStage<?> failed = (CompletionStage<?>)
                ReflectAsyncDemo.class.getMethod("failedLater").invoke(null);
        System.out.println("Invoke returned failed stage: " + (failed != null));
        try {
            failed.toCompletableFuture().join();
        } catch (CompletionException ex) {
            System.out.println("Async cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            ReflectAsyncDemo.class.getMethod("failBeforeReturn").invoke(null);
        } catch (InvocationTargetException ex) {
            System.out.println("Sync cause: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac ReflectAsyncDemo.java
java ReflectAsyncDemo
```

Deterministic output:

```text
Future result: true
Stage result: true
Future done before completion: false
Stage done before completion: false
Future get: future-ok
Stage join: stage-ok
Invoke returned failed stage: true
Async cause: IllegalStateException
Sync cause: IllegalArgumentException
```

**Why does this result prove `invoke` does not automatically wait?** Both `CompletableFuture`s are initialized in an **incomplete** state, and **only the `complete(...)` calls further down complete them**. After running `find.invoke(null)` and `load.invoke(null)`, the program proceeds to `isDone()` and receives `false` for both. If `Method.invoke` waited for completion, the program could never reach the `complete` calls located later on the same thread.

The two `get`/`join` calls happen **after** `complete`, so they read the results immediately. If you moved `join` before `complete` on the same thread, the program would wait forever.

`find.invoke(null)` and `load.invoke(null)` use a `null` receiver because the methods are `static`. For instance methods, you must pass an instance of the declaring class or a compatible type.

The program also intentionally separates two failure cases: `failedLater` **returns a stage successfully as far as the direct call is concerned**, yet the stage completed exceptionally; `failBeforeReturn` throws an error **before returning a value**. The two scenarios have different error-propagation paths, presented in the next section.

## 4. `InvocationTargetException` vs. completion errors

### 4.1. Exception immediately when calling the method via reflection

If code **inside the target method** throws an error before returning, `Method.invoke` wraps that exception in `java.lang.reflect.InvocationTargetException`. This is Reflection's mechanism, independent of whether the method declares returning a `Future`.

```java
// Illustrative snippet in a method, with method/receiver already defined.
try {
    Object result = method.invoke(receiver);
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Method itself failed: " + original);
}
```

For example, if the method body itself calls `future.get()` and receives `ExecutionException` **before returning**, `Method.invoke` can also wrap `ExecutionException` inside `InvocationTargetException` because that is an exception escaping directly from the method body.

Other invocation errors include `IllegalAccessException` (insufficient permission to access the method) or `IllegalArgumentException` (incompatible receiver/arguments); do not confuse them with the state of an async result.

### 4.2. Exception occurring when Future/Stage completes

If the method returns a `Future` or `CompletionStage` normally, and then the work represented by that object fails, **`Method.invoke` has already finished**. It cannot wrap an error arising later into a new `InvocationTargetException`. When the caller retrieves completion, the async APIs reflect the corresponding state:

| Way to observe | Success | Failure | Cancelled |
| --- | --- | --- | --- |
| `Future.get()` | Returns value; may block | `ExecutionException` containing cause | `CancellationException` |
| `Future.get(timeout, unit)` | Returns value if within deadline | `ExecutionException` containing cause | `CancellationException`; `TimeoutException` if timed out |
| `CompletableFuture.join()` | Returns value; may block | Usually throws `CompletionException` with cause | `CancellationException` |
| `CompletionStage.whenComplete(...)` | Receives value | Receives throwable to handle | May receive cancellation as exceptional completion depending on stage |

`Future.get` declares `InterruptedException` and `ExecutionException` (plus `TimeoutException` on the timed variant). `CompletableFuture.join` declares no checked exceptions, typically using `CompletionException`/`CancellationException`. If clean recovery from thread interruption is needed, `get` is better suited to handle `InterruptedException` deliberately. When catching `InterruptedException` without rethrowing, normally restore the interrupt flag via `Thread.currentThread().interrupt()`.

**Two error layers must be tracked independently:** Reflection invocation can succeed while the Future/Stage fails; or invocation fails before there is even a Future/Stage to track.

## 5. Choosing async handling vs. intentional waiting

### 5.1. Continuing a non-blocking pipeline with `CompletionStage`

When the application does not need the result immediately on the current thread, you can keep the stage object and register handlers:

```java
// Illustrative snippet in a method; Service/service defined by the application.
Method method = Service.class.getMethod("loadAsync");
Object returned = method.invoke(service);

if (returned instanceof CompletionStage<?> stage) {
    stage.whenComplete((value, failure) -> {
        if (failure != null) {
            System.err.println("Async failed: " + failure);
        } else {
            System.out.println("Async value: " + value);
        }
    });
}
```

`whenComplete` registers an action to run when the stage completes. If the stage **is already complete**, a callback without the `Async` suffix may run immediately on the thread registering it; if the stage completes later, the callback may run on the thread completing the stage. Thus "not calling `get/join`" does not guarantee every callback runs on a different thread. When you need control over where callbacks execute, consider `whenCompleteAsync(..., executor)` or corresponding `*Async` APIs.

If there are multiple dependent steps, use:

- `thenApply` to transform `T` into `U`.
- `thenCompose` when the transformation function itself returns `CompletionStage<U>` and a flat pipeline is needed.
- `thenAccept` when only consuming the result without returning a new value.
- `exceptionally`, `handle`, or `whenComplete` to handle/observe exceptional completion, depending on desired semantics.

Do not discard the stage if the caller needs to receive the result, handle errors, or perform cancellation. `Method.invoke` does not manage the async result's lifecycle on the application's behalf.

### 5.2. Waiting on the current thread when business logic requires it

You can branch on the **actual object's runtime type**:

```java
// Illustrative snippet: requires imports java.util.concurrent.*;
// handle ReflectiveOperationException, InterruptedException,
// ExecutionException, and TimeoutException per method contract.
Object returned = method.invoke(receiver);

if (returned instanceof CompletionStage<?> stage) {
    Object value = stage.toCompletableFuture().get(3, TimeUnit.SECONDS);
    System.out.println(value);
} else if (returned instanceof Future<?> future) {
    Object value = future.get(3, TimeUnit.SECONDS);
    System.out.println(value);
} else {
    System.out.println(returned);
}
```

For `CompletionStage`, the interface does not declare `get` or `join`; call `toCompletableFuture()` to obtain a `CompletableFuture` per the completion contract. When a time limit is needed, `get(timeout, unit)` can throw `TimeoutException`. A timeout on the **waiting** side does not automatically ensure the background task stopped; to cancel, use appropriate cancellation mechanisms and understand the implementation's semantics.

Checking `CompletionStage` before `Future` is a clear branching order because a `CompletableFuture` implements **both**. Waiting can block the thread: avoid calling `get/join` directly on a UI thread, event-loop, or bounded executor if the task needs that very thread to complete.

### 5.3. When is `isDone` useful?

`isDone` can be used for a **quick status check** of a `Future` without waiting. However, `isDone == false` does not tell whether the task is "still running" or "not yet scheduled"; `isDone == true` does not guarantee success. If the application needs the result reliably, it still must await completion or register callbacks. Avoid checking `isDone` repeatedly in a busy-spin loop that wastes CPU.

## 6. A policy-explicit adapter: `invokeRaw` and `invokeAndWait`

When building a dynamic invoker (plugin dispatcher, test runner, serializer adapter), make the caller's waiting contract explicit. The following is a **valid compilable class** if saved to `InvocationAdapter.java`:

```java
import java.lang.reflect.Method;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

public final class InvocationAdapter {
    public static Object invokeRaw(Method method, Object receiver,
                                   Object... args)
            throws ReflectiveOperationException {
        return method.invoke(receiver, args);
    }

    public static Object invokeAndWait(Method method, Object receiver,
                                       Object... args)
            throws ReflectiveOperationException, InterruptedException,
                   ExecutionException {
        Object returned = method.invoke(receiver, args);

        if (returned instanceof CompletionStage<?> stage) {
            return stage.toCompletableFuture().get();
        }
        if (returned instanceof Future<?> future) {
            return future.get();
        }
        return returned;
    }
}
```

**Meaning:**

- `invokeRaw` preserves the semantics of `Method.invoke`: returns the method's result directly, including an incomplete async object.
- `invokeAndWait` is **application-implemented behavior**, awaiting completion if the runtime result implements `CompletionStage` or `Future`. Normal methods return their values as before.
- `method.invoke(...)` can throw `InvocationTargetException` (subclass of `ReflectiveOperationException`) when the target method throws directly. `get` can throw `ExecutionException` and `InterruptedException`; these are two distinct error phases.
- This simple snippet sets no timeout. Production APIs should specify **timeout/deadline, interruption, cancellation, and execution context**. Do not automatically turn every Reflection call path into an unbounded wait.

A design point: a method may declare its return type as `Object` yet actually return a `CompletionStage`. `instanceof` on the **runtime value** detects this case; do not rely solely on signature metadata to decide "wait or not".

## 7. Role of `Method.getReturnType()` and generic return type

Reflection allows inspecting the **declared return type**, for example:

```java
Class<?> declared = method.getReturnType();
boolean returnsStageType =
        CompletionStage.class.isAssignableFrom(declared);
boolean returnsFutureType =
        Future.class.isAssignableFrom(declared);
```

This is an illustrative snippet placed in a method with a valid `method` variable. These two checks answer: **does the signature declare a type in the Stage/Future family?** They do not tell whether the runtime result has completed, succeeded, or failed. If a method declares `Object` yet returns `CompletableFuture`, `getReturnType()` is still `Object.class`; after invoking, inspect the returned reference itself with `instanceof`.

`getGenericReturnType()` can supply the signature's `Type`, such as `CompletionStage<String>` when generic metadata is retained, yet **does not turn `invoke` into a call capable of waiting for completion**. Generic types do not hold runtime task state.

Edge cases to remember:

- `void method()` may launch a background task while `invoke` returns `null`; no Future can be inferred from this value.
- `Future<T>` may already be completed before `invoke` finishes: `get` then returns immediately.
- A method returning `Future<T>` that **waits for an inner Future before returning** still makes `invoke` wait for the method body; that is not an "auto-wait for Future" feature of Reflection.
- Instance methods require a compatible receiver; static methods can pass `null` as the receiver. Wrong receiver/arguments cause synchronous invocation errors.
- If the invoked method throws directly before returning a Future, the caller only gets `InvocationTargetException`; there is no new async result from that call.

## 8. Common mistakes

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| `String s = (String) method.invoke(target)` when method returns `Future<String>` | The value Reflection receives is a **Future**, not the inner `String` | Receive `Future<?>`/`CompletionStage<?>` and resolve the result per contract |
| Thinking `invoke` automatically waits until the Future finishes | `invoke` only waits for **the method body to return** | Wait via `get/join` if required, or chain a pipeline |
| Thinking `Method.invoke` always returns immediately | The target method can block itself before returning | Analyze the method body and where waiting happens |
| Confusing `InvocationTargetException` with async errors | Completion errors appear after the method returns and through the async object | Track both error layers |
| Casting every `Future` to `CompletableFuture` | The two types are not equivalent; other implementations may not extend CF | Check runtime types and handle each contract |
| Calling `join` on an event-loop that is needed to complete the Future | Can deadlock | Use composition or a separate executor; avoid blocking the same thread |
| Seeing `isDone() == true` and assuming the task succeeded | Done includes failure and cancellation | Use `get/join` or error callbacks to classify |
| Ignoring the async return value | No way left to track errors or results | Return the stage, register callbacks, or manage task lifecycle explicitly |

### Illustration of a simple deadlock

```java
CompletableFuture<String> pending = new CompletableFuture<>();
System.out.println(pending.join()); // Waits until pending is completed
pending.complete("done");          // Unreachable on the same thread
```

This is an **illustrative code fragment**, not a standalone program. Without another thread calling `complete`, `join` waits forever and the line below is never reached. If a framework places `get/join` inside a callback on the very thread/event-loop needed to run the completing work, the same problem can occur.

## 9. Self-check questions

1. `Method.invoke` calls a method returning an incomplete `Future<String>`. What runtime type does the returned reference have, and what is wrong with `(String) invoke(...)`?
2. Why can `invoke` still block for a long time even though the method returns `CompletableFuture`?
3. Method A throws `IllegalStateException` before `return`. Method B returns a stage that later completes exceptionally with `IllegalStateException`. How do the two error paths to the caller differ?
4. Compare `future.get()` with `stage.thenApply(...)` in terms of waiting behavior and when callbacks run.
5. Can `CompletableFuture` match both `Future` and `CompletionStage` branches in `instanceof`? Which branch should be preferred when composition is desired?
6. A method declares return type `Object` yet at runtime returns `CompletionStage<?>`. Why is checking `getReturnType()` alone insufficient?
7. A method returns `void` yet starts a background task. How should the API be designed so callers can wait for or track the result?
8. Why should timeouts and interruption/cancellation policies be specified if an application decides to await completion?

**Takeaway:** `Method.invoke` synchronizes **the direct method call**, whereas the completion state of `Future`/`CompletionStage` is **an independent contract**. Async results are only awaited/observed when the caller explicitly performs `get`, `join`, or registers appropriate composition. Always distinguish errors of the method running via Reflection (`InvocationTargetException`) from errors of the returned task (`ExecutionException`, `CompletionException`, `CancellationException`).

## 10. Official references

- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): return value and exceptions thrown by the invoked method.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, cancellation, `isDone`.
- [Java SE 17 — `CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): composing stages and handling completion.
- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `get`, `join`, error handling, and implementing both `Future`/`CompletionStage`.
- [Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): errors from the method body via Reflection.