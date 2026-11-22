# minimalCompletionStage() and copy(): Restricting the Recipient's Right to Complete a Future

## 1. The Problem: A CompletableFuture Is Both a Promise of a Result and the Right to Mutate It

`CompletableFuture<T>` combines two groups of capabilities in the same object:

- **Consuming results / asynchronous coordination:** `thenApply`, `thenCompose`, `handle`, `whenComplete`, `thenCombine`, `toCompletableFuture`…
- **Actively controlling completion:** `complete(value)`, `completeExceptionally(error)`, `cancel(...)`, `obtrudeValue(...)`, `obtrudeException(...)`, `completeOnTimeout`, `orTimeout`…

This is very convenient for code that **owns** the future. However, it becomes a problem when the same `CompletableFuture` is handed out directly to external code: the recipient can call `complete("FAKE")` before the real work finishes, `cancel` it, or use `obtrudeValue` to alter the observed result. Such actions break the application's ownership boundaries.

~~~java
class UnsafeService {
    private final CompletableFuture<String> result =
            new CompletableFuture<>();

    public CompletableFuture<String> result() {
        return result; // EXPOSES the original future with complete/cancel rights!
    }

    public void finish() {
        result.complete("trusted");
    }
}
~~~

This is an **illustrative snippet** assuming `import java.util.concurrent.CompletableFuture`. A consumer could call `service.result().complete("fake")` before `finish()` and prevent the real completion from winning the race. If you only want the client to **wait for** or **attach callbacks** to the result, returning the original future directly grants too much authority.

Since Java 9, `CompletableFuture` provides two APIs for enforcing this boundary:

1. `minimalCompletionStage()` — gives the recipient a **restricted CompletionStage<T>** limited to the operations in the `CompletionStage` interface.
2. `copy()` — gives the recipient **a CompletableFuture<T> with independent completion state**, having the same outcome as the source if the copy has not already been completed by the recipient beforehand.

**Core idea:** both APIs protect **control over the completion of the original object**, but **they do not perform a deep copy of the data T, do not automatically stop I/O, and are not a security mechanism against hostile code with full JVM privileges**.

### Learning Objectives

After this lesson, you will be able to:
- Understand the exact signatures and Java 17 semantics of both APIs.
- Distinguish **interface restriction** from an **independent completable copy**.
- Know the effects of `complete`, `cancel`, and `obtrudeValue` on the future returned to the client.
- Understand normal completion flow, exceptional completion, and `CompletionException` chaining.
- Use `CompletionStage.toCompletableFuture()` properly without mistaking it for "reopening" write access to the source.
- Design public APIs so that the component-owned source future stays `private`.
- Recognize shallow data sharing with mutable objects and recommend immutable DTOs/snapshots.
- Know the limitations regarding backpressure, cancellation propagation, timeouts, and liveness.
- Run Java 17+ programs that determine results using `complete()` and callbacks without needing `sleep()`.
- Apply a code review checklist and solve exercises on future access control.

**Scope:** Java SE concurrency (`java.util.concurrent`), framework-independent.

## 2. The Two APIs and Their Formal Contracts

In Java SE 17:

~~~java
public CompletableFuture<T> copy();

public CompletionStage<T> minimalCompletionStage();
~~~

`copy()` returns a **new** `CompletableFuture<T>`. The JDK documentation describes its behavior as equivalent to:

~~~java
CompletableFuture<T> copy = source.thenApply(x -> x);
~~~

This is a **new dependent future**, not an alias of the source. When the source completes normally, the copy completes with the same **value T** if it has not been independently completed beforehand. When the source completes exceptionally, the copy receives an exceptional completion as specified by the Javadoc, with a `CompletionException` wrapping the appropriate cause.

`minimalCompletionStage()` returns a **new** `CompletionStage<T>` that supports only the behaviors defined in the `CompletionStage` interface and cannot be independently completed by state-management operations outside that interface. It also follows the source's outcome when the source completes.

**Core differences:**

| Criterion | Direct `source` | `source.copy()` | `source.minimalCompletionStage()` |
|---|---|---|---|
| API return type | `CompletableFuture<T>` | `CompletableFuture<T>` | `CompletionStage<T>` |
| Recipient calls `thenApply/thenCompose/handle` | Yes | Yes | Yes |
| Recipient calls `complete(value)` directly | Yes, modifies source | Yes, modifies **copy**, not source | Method does not exist on interface |
| Recipient calls `cancel(...)` directly | Yes, cancels source | Yes, cancels **copy** | Method does not exist on interface |
| Recipient calls `join()` directly | Yes | Yes | `join` method does not exist on interface |
| Recipient waits via `toCompletableFuture().join()` | Possible | Possible | Possible; receives a new non-minimal future per standard implementation |
| Active authority to decide source completion | **Yes** | **No** | **No** |
| Result may be the original T reference | Yes | **Yes** | **Yes** |
| Is it a deep copy of T? | No | **No** | **No** |
| Can client create its own dependent stages? | Yes | Yes | Yes |
| Does it automatically control cancelling background tasks? | Not guaranteed | No | No |

Note: the `minimalCompletionStage()` column considers the **API contract and standard implementation**; it does not claim that a Java object cannot be inspected via reflection or in a privileged environment. It should not be used as a security sandbox for untrusted code.

## 3. The Owner vs. Observer Boundary

A good design distinguishes between:

- **Producer/owner:** creates the `CompletableFuture`, manages the actual workflow, and decides normal/exceptional completion.
- **Observer/consumer:** registers callbacks, chains stages, or waits for the result, but **must not decide whether the source has completed**.

Diagram:

~~~text
                   Service (owner)
                          |
              private CompletableFuture<T>
                          |
             complete / completeExceptionally
                          |
           +--------------+---------------+
           |                              |
     minimalCompletionStage()           copy()
           |                              |
    CompletionStage<T>             CompletableFuture<T>
           |                              |
      client compose                  client join/get
      / handle                       / compose
           |                              |
      client does NOT have            client CAN complete
      complete() directly             its own copy
           |                              |
           +--------------+---------------+
                          |
           Does NOT modify source completion
~~~

**Principle:** the owner keeps the source in a field that is never exposed directly. Do not create another method that accidentally returns the original source; otherwise, using `copy` at another endpoint no longer protects overall ownership.

## 4. Why Merely Declaring Return Type CompletionStage Is Not Enough

A common pattern:

~~~java
class Service {
    private final CompletableFuture<String> internal =
            new CompletableFuture<>();

    public CompletionStage<String> status() {
        return internal; // Restricted public type, the actual object is still source!
    }
}
~~~

The **compile-time contract** is `CompletionStage`: code using a variable of this type does not see `complete`. However, in Java, the caller can check the runtime type:

~~~java
CompletionStage<String> published = service.status();
if (published instanceof CompletableFuture<?>) {
    // Can cast to reach the original object itself.
}
~~~

These are illustrative snippets; the `service` class must be instantiated and generic casts handled appropriately where used. Because it returns the **exact source object** whose runtime type is `CompletableFuture`, a caller can cast it to the concrete type to call `complete/cancel/obtrude`.

Therefore, **the return type is only part of the design**. To **truly avoid handing out the source object**, use:

~~~java
public CompletionStage<String> status() {
    return internal.minimalCompletionStage();
}
~~~

The recipient receives **a new wrapper/dependent stage**, not the original source. Or when a signature requires `CompletableFuture` for a legacy API, use:

~~~java
public CompletableFuture<String> statusForLegacyClient() {
    return internal.copy();
}
~~~

Both are snippets inside the class with the `internal` field shown above.

## 5. copy(): Defensive Completion Copy, Yet Still Mutable by the Client

`copy()` might look like an "immutable CompletableFuture", but that is a misconception. It is a **normal CompletableFuture**, and the client can call all mutation methods on **the copy itself**.

What is protected: **mutating the copy does not mutate the source's state**.

### Standalone Example 1: Client Completes the Copy Before the Owner

Save the file **CompletableFutureCopyIsolationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureCopyIsolationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> exposed = source.copy();

        boolean clientCompleted = exposed.complete("client-value");
        boolean sourceWasDone = source.isDone();
        boolean ownerCompleted = source.complete("owner-value");

        System.out.println("clientCompleted=" + clientCompleted);
        System.out.println("sourceWasDone=" + sourceWasDone);
        System.out.println("ownerCompleted=" + ownerCompleted);
        System.out.println("source=" + source.join());
        System.out.println("exposed=" + exposed.join());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac CompletableFutureCopyIsolationDemo.java
java CompletableFutureCopyIsolationDemo
~~~

Stdout:

~~~text
clientCompleted=true
sourceWasDone=false
ownerCompleted=true
source=owner-value
exposed=client-value
~~~

**Explanation:**

1. The source is initially pending; the copy is created and is also pending.
2. The client completes the **copy** with `"client-value"`, so `exposed.complete` returns `true`.
3. The source is **still pending**, so `source.isDone()` returns `false`.
4. The owner calls `source.complete("owner-value")`; this succeeds because the source was not touched by the client.
5. Because the copy was already completed earlier, it **does not change to "owner-value"**.
6. The result the caller sees through the copy now differs from the source. Thus `copy` **does not guarantee that the client will observe the real result** if the client itself actively mutates its copy.

**This is the authority boundary:** the client cannot decide the completion of the **source**, but still has the authority to decide the local outcome on the **copy**. If an API needs to reduce the risk of accidental mutation on the returned object as well, `minimalCompletionStage` is the stricter choice.

### Consequences for Client Callbacks

If the client has already called `complete("client-value")` on the copy and then attaches a `thenApply` callback, the callback sees `client-value`. The owner can still complete the source with `owner-value`, but callbacks on the already-completed copy will not run again.

Do not use `copy` if the requirement is to **force the client to observe the true result regardless of whether the client intentionally mutates its own view**. This API only protects the source; it does not enforce honesty on a client given a mutable copy.

## 6. minimalCompletionStage(): Granting Chaining Rights Without Completion Rights

The return value has type `CompletionStage<T>`. The allowed operations are those on the interface:

~~~java
CompletionStage<String> view = source.minimalCompletionStage();

CompletionStage<Integer> length =
        view.thenApply(String::length);

CompletionStage<String> chain =
        view.thenCompose(value ->
                CompletableFuture.completedFuture(
                        "processed:" + value));
~~~

This is an illustrative snippet inside a method with `source` of type `CompletableFuture<String>`. The client can create **dependent stages** to process data. However, the `CompletionStage` interface **does not** have `complete`, `cancel`, `obtrudeValue`, or `join`.

When the caller only receives `CompletionStage<T>`, the following code **does not compile**:

~~~java
CompletionStage<String> view = source.minimalCompletionStage();

// view.complete("fake");   // No complete method on the interface.
// view.cancel(true);       // No cancel method on the interface.
// view.join();             // No join method on the interface.
~~~

The commented lines are examples of **compile-time restriction**, not standalone runnable code. If waiting is needed at a system boundary, the interface provides `toCompletableFuture()`.

### Subtlety: The Runtime Object Is Not Just an Abstract Interface

The standard JDK implementation may use an internal subclass extending `CompletableFuture` for the minimal stage. Because of this, some people try casting a minimal stage to `CompletableFuture` and calling `complete/get/join`.

**Do not do that.** Methods not belonging to `CompletionStage` are **unsupported** on a minimal stage; the standard implementation may throw `UnsupportedOperationException`. The right approach is:
- Keep the variable typed as `CompletionStage<T>`.
- Use `thenApply`, `thenCompose`, `handle`, and other interface methods.
- If the caller needs the `Future` API, convert it into an **independent future** via `toCompletableFuture()`.

Do not assume "since it cast to CompletableFuture, the client regained the right to modify the source." If a method is unsupported, casting does not change the stage's contract.

## 7. toCompletableFuture(): A Bridge, Not an Owner-Authority Leak

`CompletionStage<T>.toCompletableFuture()` returns a `CompletableFuture<T>` to interoperate with code that needs the `Future` API such as `join/get`, `get(timeout)`, or `cancel`.

The Javadoc for `CompletableFuture.minimalCompletionStage()` explicitly states: **unless overridden by a subclass**, calling `toCompletableFuture()` on a minimal stage may create **a new non-minimal CompletableFuture** with all methods available. That does not mean it returns the **original source**.

### Standalone Example 2: Mutating the Future from toCompletableFuture Does Not Mutate the Source

Save **MinimalStageBridgeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class MinimalStageBridgeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletionStage<String> published =
                source.minimalCompletionStage();

        CompletableFuture<String> clientBridge =
                published.toCompletableFuture();

        boolean clientCompleted = clientBridge.complete("fake");
        boolean sourceWasDone = source.isDone();

        source.complete("real");
        String stageResult = published
                .thenApply(value -> "observed:" + value)
                .toCompletableFuture()
                .join();

        System.out.println("clientCompleted=" + clientCompleted);
        System.out.println("sourceWasDone=" + sourceWasDone);
        System.out.println("source=" + source.join());
        System.out.println("clientBridge=" + clientBridge.join());
        System.out.println("stageResult=" + stageResult);
    }
}
~~~

Compile and run:

~~~bash
javac MinimalStageBridgeDemo.java
java MinimalStageBridgeDemo
~~~

Stdout:

~~~text
clientCompleted=true
sourceWasDone=false
source=real
clientBridge=fake
stageResult=observed:real
~~~

**Detailed explanation:**

- `published` is a minimal stage tracking the source.
- `clientBridge` is a `CompletableFuture` that is not the source. The client's `complete("fake")` succeeds on its bridge.
- `source.isDone()` remains `false` before the owner completes it.
- The owner later completes `source` with `"real"`; the minimal stage and its `thenApply` chain receive that data.
- `clientBridge` was already independently completed, so it still holds `"fake"`.
- Calling `published.toCompletableFuture()` to **create a new bridge** is valid; it does not require interfering with owner authority.

**Warning:** Do not claim that `toCompletableFuture()` on **every CompletionStage implementation** creates a copy. For a regular `CompletableFuture`, `source.toCompletableFuture()` may return **the source itself**. The leak-prevention guarantee here belongs to the **minimal stage created by CompletableFuture.minimalCompletionStage()**, not to every `CompletionStage` in existence.

## 8. When to Choose copy, When to Choose minimal?

| Condition | What to consider |
|---|---|
| New public API only needs chaining, caller does not need to manipulate `Future` | `CompletionStage<T>` from `minimalCompletionStage()` |
| Legacy API requires returning `CompletableFuture<T>` | `copy()` |
| Client genuinely needs `join/get(timeout)` directly | `copy()` or `minimalStage.toCompletableFuture()` at the boundary |
| Want to prevent the client from accidentally calling `complete` directly on the received value | `minimalCompletionStage()` |
| Want the client to be able to complete/cancel **its own view** without modifying the source | `copy()` |
| Want the client to cancel the **actual computation** owned by the service | Need a **dedicated cancel API** with clear contract and authorization; neither method does this automatically |
| Want a deep copy of a mutable result | Use an immutable DTO/defensive data copy; neither method deep-copies T |
| Want to prevent untrusted code from interfering with the entire JVM | Need a different isolation/security boundary; neither method is a sandbox |

**Common design rule:** expose `CompletionStage<T>` via `minimalCompletionStage()` in your public async contract; only expose `CompletableFuture<T>` via `copy()` when integration genuinely requires the concrete type.

## 9. Standalone Example 3: A Service Exposing Both Types While Keeping Source Private

Save **CompletionOwnershipServiceDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CompletionOwnershipServiceDemo {
    static final class ResultService {
        private final CompletableFuture<String> internal =
                new CompletableFuture<>();

        CompletionStage<String> observe() {
            return internal.minimalCompletionStage();
        }

        CompletableFuture<String> legacyFuture() {
            return internal.copy();
        }

        boolean finish(String value) {
            return internal.complete(value);
        }

        boolean isFinished() {
            return internal.isDone();
        }
    }

    public static void main(String[] args) {
        ResultService service = new ResultService();

        CompletionStage<String> view = service.observe();
        CompletableFuture<String> legacy = service.legacyFuture();

        legacy.complete("legacy-fake");
        boolean ownerWasDone = service.isFinished();

        service.finish("actual");
        String observed = view
                .thenApply(x -> x.toUpperCase())
                .toCompletableFuture()
                .join();

        System.out.println("ownerWasDone=" + ownerWasDone);
        System.out.println("observed=" + observed);
        System.out.println("legacy=" + legacy.join());
    }
}
~~~

Compile and run:

~~~bash
javac CompletionOwnershipServiceDemo.java
java CompletionOwnershipServiceDemo
~~~

Stdout:

~~~text
ownerWasDone=false
observed=ACTUAL
legacy=legacy-fake
~~~

Here:
- The service keeps `internal` private; only `finish` has the authority to complete the source.
- The client gets `observe` for chaining, while `legacyFuture` is a copy with the right to complete **the copy** itself.
- A client operating on the legacy view cannot transition the source to done.
- The owner's completion still propagates to the minimal stage view, so the observer sees `ACTUAL`.
- The legacy copy that was already completed with `"legacy-fake"` does not automatically change to `"actual"`.

If the service wants to let callers request cancellation of the real task, design **a separate method** such as `requestCancellation()` with a clear lifecycle and appropriate access control. Do not rely on exposing the original source as an unintended "cancellation channel".

## 10. Completion Flow When the Client Does Not Mutate Its Copy

Suppose `source`, `copy`, and `minimal` are all initially incomplete:

~~~text
t0: source = incomplete
    copy   = incomplete
    minimal= incomplete

t1: source.complete("OK")
      │
      ├─ copy completes normally with "OK"
      └─ minimal completes normally with "OK"
            └─ continuation registered by client runs

Client only observed, did not actively complete/cancel copy.
~~~

If the source already completed before the client calls `copy()` or `minimalCompletionStage()`, the resulting new view is **already completed** according to the source's state. No separate worker is needed just to maintain the two views. These methods are completion-dependency mechanisms, **not tasks that run new async computations**.

If the client completed the copy **before** the source, the copy keeps its own outcome. If the client completed dependent stages it created on the copy, those stages also have outcomes according to the client's graph.

### No Callback Ordering Guarantee

A source may have multiple dependents; the execution order of callbacks triggered by completion is not a contract for building business ordering. Do not use "register callback A before B" as a transactional protocol. If business logic requires ordering, build an explicit chain (`thenCompose`/`thenRun` by dependency) or use an owned sequential executor.

## 11. How Does Exceptional Completion Propagate Through copy/minimal?

Suppose the owner calls:

~~~java
source.completeExceptionally(
        new IllegalStateException("upstream failure"));
~~~

Both `copy()` and `minimalCompletionStage()` will complete exceptionally. Per the JDK, when the source completes exceptionally, the views receive a `CompletionException` with the appropriate cause.

Points to distinguish:

- `join()` on an exceptionally completed `CompletableFuture` may throw `CompletionException`.
- `get()` typically throws `ExecutionException` (checked), whose cause holds the original exception.
- `whenComplete` observes `(value, error)` accordingly.
- `exceptionally` can recover to a different value on **the client's dependent stage**, without any authority to modify the source.
- When the source is cancelled, completion generally propagates to dependents as an exceptional completion; `isCancelled()` on a dependent **is not required** to match `isCancelled()` on the source, because cancellation may be wrapped in a `CompletionException`.

### Standalone Example 4: Source Failure Propagates Through Both Views

Save **CompletionViewFailureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class CompletionViewFailureDemo {
    private static String causeType(CompletableFuture<?> future) {
        try {
            future.join();
            return "none";
        } catch (CompletionException e) {
            Throwable cause = e.getCause();
            return cause.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> copy = source.copy();
        CompletionStage<String> stage =
                source.minimalCompletionStage();

        source.completeExceptionally(
                new IllegalStateException("upstream failed"));

        System.out.println("copyCause=" + causeType(copy));
        System.out.println("stageCause=" +
                causeType(stage.toCompletableFuture()));
        System.out.println("sourceExceptional=" +
                source.isCompletedExceptionally());
    }
}
~~~

Compile and run:

~~~bash
javac CompletionViewFailureDemo.java
java CompletionViewFailureDemo
~~~

Stdout:

~~~text
copyCause=IllegalStateException
stageCause=IllegalStateException
sourceExceptional=true
~~~

**Why?** Both views follow the source's exceptional result. `join` surfaces a `CompletionException`; its cause is the `IllegalStateException` passed by the owner. In this example there is no race with the client completing the copy itself, so there is no ambiguity in the outcome.

**Note:** In real systems, if the original exception is already a `CompletionException`, cause wrapping is handled according to `CompletableFuture` rules; do not write code that depends on a fixed number of wrapper layers without checking the `Throwable` type. For logging, preserve the original stack trace and identify the root cause.

## 12. copy and CompletionStage Are Not a Deep Copy of Data T

This is a major trap: `copy()` copies the **completion state/outcome dependency**, not the mutable contents returned by the future.

For example, `T = List<String>`:
- The source completes with a reference to an `ArrayList`.
- The copy completes normally with **that same reference** (per `thenApply(x -> x)` semantics).
- The client can mutate the list and the owner sees the changes if it still holds the reference.
- `minimalCompletionStage` also passes **the value T**, without cloning the object.

### Standalone Example 5: Same Mutable Data Despite Two Different Futures

Save **CompletionViewShallowValueDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class CompletionViewShallowValueDemo {
    public static void main(String[] args) {
        List<String> internalData = new ArrayList<>();
        internalData.add("server");

        CompletableFuture<List<String>> source =
                CompletableFuture.completedFuture(internalData);
        CompletableFuture<List<String>> view = source.copy();

        view.join().add("client");

        System.out.println("sameReference=" +
                (source.join() == view.join()));
        System.out.println("sourceSize=" + source.join().size());
        System.out.println("sourceData=" + source.join());
    }
}
~~~

Compile and run:

~~~bash
javac CompletionViewShallowValueDemo.java
java CompletionViewShallowValueDemo
~~~

Stdout:

~~~text
sameReference=true
sourceSize=2
sourceData=[server, client]
~~~

In this example everything happens sequentially on `main`, so there is no data race; it solely demonstrates **object aliasing**. If threads concurrently read and modify the `ArrayList`, there is also a risk of data races and inconsistent state.

Possible solutions:
- Return a `record`/immutable DTO with unmodifiable fields.
- Use `List.copyOf(mutableList)` when building the result to create a list snapshot; note **shallow copying of elements**: if an element itself is mutable, it can still be mutated.
- Use immutable persistent data structures when safe sharing is needed.
- Do not expose internal collections directly; create a defensive copy of the value **before completing the source** or when creating the view with `thenApply(v -> deepCopy(v))` if a deep copy is truly needed.

### Copy the Data Too If Required

~~~java
CompletableFuture<List<String>> publicCopy =
        internalFuture.thenApply(List::copyOf);
~~~

This is an illustrative snippet where `internalFuture` has type `CompletableFuture<List<String>>`. `List.copyOf` provides an **unmodifiable list**, but **does not deep-copy mutable element objects**. In addition, `List.copyOf` rejects null elements; check the data contract before using it.

If the goal is both completion restriction and snapshotting:
- The owner builds an immutable result.
- Expose `minimalCompletionStage` of the future that already holds the immutable result.
- Or create a result future `thenApply(immutableConversion).minimalCompletionStage()`, ensuring `immutableConversion` fits the domain.

## 13. Cancellation: Cancelling a View Does Not Automatically Cancel the Original Computation

In `CompletableFuture`, cancellation is a form of exceptional completion. It is **not** an action that interrupts I/O or kills an arbitrary worker. The Java docs state that `mayInterruptIfRunning` has no effect for the default `CompletableFuture` implementation.

Consider:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> view = source.copy();

view.cancel(true);
System.out.println(source.isDone()); // false on the same thread, nobody has completed source yet
~~~

The copy is cancelled; the source remains pending. The client can use `cancel` as a way to **stop caring about its own view**, while the owner can still continue the work and complete the source.

For a minimal stage:
- It does not expose `cancel` directly in the interface.
- If the client calls `toCompletableFuture()` and cancels **the bridge**, that action is not guaranteed to cancel the source.
- From a minimal stage, a client can attach callbacks to observe/ignore the result without needing permission to cancel the owner's future.
- If the application needs users to request cancellation of the real computation, **design a separate cancel token/API** with proper permissions and lifecycle; do not treat cancelling a view as sufficient.

### Standalone Example 6: Cancelling the Copy Leaves the Source Intact

Save **CompletionCopyCancellationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletionCopyCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> clientView = source.copy();

        boolean cancelled = clientView.cancel(true);
        boolean ownerWasDone = source.isDone();

        boolean ownerCompleted = source.complete("finished");
        System.out.println("cancelledView=" + cancelled);
        System.out.println("ownerWasDone=" + ownerWasDone);
        System.out.println("ownerCompleted=" + ownerCompleted);
        System.out.println("source=" + source.join());
        System.out.println("viewCancelled=" + clientView.isCancelled());
    }
}
~~~

Command:

~~~bash
javac CompletionCopyCancellationDemo.java
java CompletionCopyCancellationDemo
~~~

Stdout:

~~~text
cancelledView=true
ownerWasDone=false
ownerCompleted=true
source=finished
viewCancelled=true
~~~

The original task still retains the right to complete after the view is cancelled. **Do not assume that cancelling the copy stops the I/O or batch work performed by the owner**.

## 14. Timeout: Be Careful Which Future the API Mutates

`orTimeout(timeout, unit)` and `completeOnTimeout(value, timeout, unit)` **complete the very CompletableFuture that receives the call** if it is not done after the duration.

Therefore:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

source.orTimeout(1, TimeUnit.SECONDS);
// Affects SOURCE — can break ownership if the client received source!
~~~

If the client received a `copy()`:

~~~java
CompletableFuture<String> view = source.copy();
view.orTimeout(1, TimeUnit.SECONDS);
// Affects the client's VIEW; does not cause source to fail with TimeoutException.
~~~

These are illustrative snippets inside a method with `TimeUnit` imported. Importantly, this is **not** a timeout on the underlying I/O; if the source is computed via a remote request, the network call may still be running after the view times out.

**Do not call `minimalStage.toCompletableFuture()` and then `orTimeout` thinking the source will time out.** The bridge is an independent future; a local timeout may be right for the caller, while the owner continues according to its own lifecycle.

### Caller Timeout Does Not Mutate the Future

`get(timeout, unit)` waits for a bounded duration and throws `TimeoutException` if not yet completed. It **does not complete or cancel** any `CompletableFuture` simply because the caller timed out waiting.

| API | Affects | When expired |
|---|---|---|
| `source.get(timeout)` | Only the caller's wait | Throws `TimeoutException`; source may still be pending |
| `source.orTimeout(...)` | `source` itself | Source completes exceptionally if not done |
| `source.completeOnTimeout(value, ...)` | `source` itself | Source completes normally with `value` if not done |
| `source.copy().orTimeout(...)` | The new copy | Copy completes exceptionally; source remains controlled by owner |
| `source.minimalCompletionStage().toCompletableFuture().orTimeout(...)` | The new bridge | Bridge completes exceptionally, does not complete source |

**Note**: achieving a true overall deadline requires managing scheduling, queueing, I/O timeouts, and cleanup. A view's timeout is not a termination guarantee for the worker.

## 15. Completion Behavior When the Source Already Succeeded Before Creating the View

These two APIs do not create new tasks that need to run. If the source is already done:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> copy = source.copy();
CompletionStage<String> minimal = source.minimalCompletionStage();

System.out.println(copy.join());
System.out.println(minimal.toCompletableFuture().join());
~~~

This is an integrated snippet importing `CompletableFuture` and `CompletionStage`. Both stdout lines are `ready`.

When the source is not yet done, the new view tracks the future completion. When the source is already done, the view has the corresponding completion. There is no need to use `supplyAsync` to "induce asynchrony" just because you are creating a dependent stage.

### Which Thread Can the Client's Callback Run On?

`thenApply` without the `Async` suffix may run immediately on the thread creating the callback if the source is already done, or on the thread completing the source, or on other threads participating in completion. Do not rely on the callback's thread name to infer the owner.

If a callback is blocking or heavy, the client should use `thenApplyAsync(fn, executor)` with an appropriate executor to avoid occupying the thread that completes the source. `copy()` and `minimalCompletionStage()` themselves do not grant the client a new executor.

## 16. Chains of Dependent Stages Can Still Be Completed by the Client

Even when the client only receives `CompletionStage<T>`, the client has the right to **create dependent stages**. The stages produced by `thenApply`, `thenCompose`, `handle`, etc. have their own completion semantics. If the client converts a dependent stage into its own `CompletableFuture`, the client can mutate **the stage owned by the client**, not the source.

Example:

~~~java
CompletionStage<Integer> projected =
        serviceView.thenApply(String::length);

CompletableFuture<Integer> ownFuture =
        projected.toCompletableFuture();

ownFuture.complete(0); // The caller's own result.
~~~

This is a method snippet integrating with `serviceView` returning `CompletionStage<String>`. The client forcing `ownFuture` to `0` does not mean the service's original future returned a string of length 0.

**Do not treat views as "proof that data cannot be forged by the recipient"**. If a client controls its own output pipeline, it can fabricate a result on its side. The important boundary is that **it cannot alter the truth of the service-owned source through the exposed API**.

## 17. A Small Interface Is Good Design, But You Must Check the Implementation

A common saying is: "Just return CompletionStage and everything is safe." That is **not enough**, because the concrete source can still be cast if returned directly.

Compare:

~~~java
public CompletionStage<String> unsafeReadOnly() {
    return internal; // the original object itself
}

public CompletionStage<String> betterReadOnly() {
    return internal.minimalCompletionStage();
}
~~~

If there is a `getInternalFuture()` method, exposure elsewhere can render all protections meaningless. You must review the entire public API, callback registries, and object graph.

Even with a minimal stage:
- `T` is still passed by reference; if mutable, the client can still mutate the value.
- The client can structure callbacks that create new CPU or I/O workloads; this API does not govern the resources of **all client-created operations**.
- The client can decide the outcome of its own **copies** or **dependent stages**.
- Java reflection or high-privilege environments are a separate security problem; a minimal stage is not a boundary against untrusted malicious code.
- If code subclasses and overrides methods, rely on the public contract and test the implementation rather than assuming every runtime class behaves identically to the exact JDK internal class.

**Right design:** keep the source future private, minimize the public interface, use immutable results, and provide separate cancellation and ownership APIs when truly needed.

## 18. Comparing completedStage and completedFuture

Java 9+ also provides:

~~~java
CompletableFuture<String> mutableFuture =
        CompletableFuture.completedFuture("ok");

CompletionStage<String> minimalStage =
        CompletableFuture.completedStage("ok");
~~~

`completedFuture("ok")` returns a `CompletableFuture` that is already done **yet still exposes mutation methods like `obtrudeValue`**. Thus "already completed" does not mean "immutable from an observer's perspective".

`completedStage("ok")` returns a `CompletionStage` supporting interface-only semantics similar to a minimal stage, when the result is **already available**. If a computation is still pending and you need to publish a view, use `source.minimalCompletionStage()`.

Similarly:
- `failedFuture(Throwable)` returns a full `CompletableFuture` completed exceptionally.
- `failedStage(Throwable)` returns a minimal `CompletionStage` completed exceptionally.

### Choosing completedStage in API Design

~~~java
public CompletionStage<String> cachedLookup(String key) {
    if (key.isBlank()) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("key blank"));
    }
    return CompletableFuture.completedStage("cached:" + key);
}
~~~

This is a standalone method placed inside a class and requires importing `CompletionStage` and `CompletableFuture`. It returns an already-completed stage with a restricted API; there is no need to create a mutable source `CompletableFuture` when the result is already known.

## 19. Timing of Copy Creation and Race Conditions

When the owner and client act on different futures at the same time:
- The owner completes the source.
- The client completes/cancels the copy.
- These operations may occur concurrently.
- **Whichever completion arrives first on the copy** determines the copy's outcome (aside from subsequent overrides/`obtrude` calls made by the client itself).
- The source is only controlled by the owner and parties that actually hold a reference to the source.

Therefore, never promise "the copy will always reflect the final result of the source" in cases where the client intentionally completes the copy before the source. `copy` is **defensive completion isolation**, not a live proxy that the consumer cannot interfere with.

For a minimal stage, the client has no direct `complete` method. When the source completes, the minimal stage reflects the outcome per the contract, and the client can choose to create derivatives to compute further or recover from errors.

### Cancellation and Exceptional Propagation

If the source is cancelled, the source itself may report `isCancelled() == true`. A dependent `copy` may complete exceptionally with a `CompletionException` wrapping `CancellationException`, so `copy.isCancelled()` should not be assumed to stay strictly in sync with `source.isCancelled()`. To classify upstream cancellation, inspect the exception cause chain rather than relying solely on the cancel flag of derivatives.

However, if the client calls `copy.cancel(...)` directly, the copy will have cancelled status from that call, while the source is not cancelled.

## 20. Side Effects, Data Races, and Consistency

A future is only a **vehicle for reporting an outcome**, not a transaction. If the source completes after side effects have already occurred:
- The client calling `copy.cancel()` does not roll back a transaction.
- The client calling `minimalStage.toCompletableFuture().complete("fake")` does not cause the database to write `"fake"` or the owner to lose its state.
- The client mutating a mutable DTO can affect the service if both share the same reference.
- If the producer publishes an object and then continues mutating it asynchronously, callbacks may read changing data, leading to a data race.
- If client code inside a callback throws an exception, the dependent stage may fail, but that does not necessarily fail the source.

Preventive steps:
1. Return immutable value types or defensive snapshots.
2. Keep the source private; do not expose aliases via getters or public collections.
3. Do not invoke external callbacks inside long-held critical sections.
4. Use `whenComplete` to observe outcomes, avoiding unexpected exceptions in logging.
5. Set timeouts on external operations and propagate compatible deadlines.
6. Define upstream cancellation in a dedicated API/service method when you truly want to cancel work.
7. If write consistency is required, use domain-appropriate transactions, idempotency, or compensation; a view future does not replace these mechanisms.

## 21. Common Mistakes in Code Reviews

**Mistake 1 — Returning a private `CompletableFuture` directly.** The client can `complete`/`cancel` the source itself.

**Mistake 2 — Only changing the return type to `CompletionStage` while still returning the source object.** The client can cast the concrete object back to `CompletableFuture` and interfere.

**Mistake 3 — Thinking `copy()` is an immutable future.** It is a full `CompletableFuture`; the client can still `complete`/`cancel`/`obtrude` **the copy**.

**Mistake 4 — Thinking `minimalCompletionStage()` is merely an interface mask over the same source.** The API returns a new stage with restricted completion semantics.

**Mistake 5 — Calling `join()` directly on the `CompletionStage` interface.** The interface has no `join`; use `toCompletableFuture()` at the boundary if needed.

**Mistake 6 — Casting a minimal stage to `CompletableFuture` and calling `complete`/`join`.** Not guaranteed; the standard implementation may throw `UnsupportedOperationException` for methods outside `CompletionStage`.

**Mistake 7 — Thinking `toCompletableFuture()` on a minimal stage returns the original source.** The Java docs state it creates a new non-minimal future by default, without handing out the source.

**Mistake 8 — Thinking every `toCompletableFuture()` is a defensive copy.** For a regular `CompletableFuture`, it may return the instance itself; check the implementation/contract.

**Mistake 9 — Thinking `copy()` deep-copies the payload T.** It shares the result reference like an identity map; mutable payloads remain shared.

**Mistake 10 — Calling `completeOnTimeout`/`orTimeout` on the source from the client.** Mutates the source outcome without authority; use a view/copy if only a local timeout is needed.

**Mistake 11 — Believing cancelling a copy stops the owner's I/O.** Cancelling a copy does not automatically propagate backward to the source computation.

**Mistake 12 — Believing `CompletableFuture.cancel(true)` always interrupts the worker.** `mayInterruptIfRunning` has no effect per the default CF Javadoc.

**Mistake 13 — Confusing exceptional propagation with the cancellation flag.** A copy receives `CompletionException`/cause; `isCancelled` may not match the source.

**Mistake 14 — Failing to protect shared mutable results.** Completion isolation is not data isolation.

**Mistake 15 — Calling `obtrudeValue` on a copy and thinking the source changed.** It affects the copy; calling it on the source breaks owner semantics.

**Mistake 16 — Using restricted APIs as a sandbox.** The recipient can still forge outcomes in its own graph or interact with a mutable `T`; a different security boundary is needed for untrusted code.

**Mistake 17 — Not handling duplicate completion.** If the source is already complete, a subsequent `complete` returns `false`; do not accidentally ignore the fact that "another owner already completed it".

**Mistake 18 — Attaching long blocking callbacks to non-Async stages.** Can occupy the thread completing the source; use an `Async` overload with an appropriate executor.

**Mistake 19 — Failing to shut down the owned executor.** `copy`/`minimal` do not manage worker lifecycles, resource cleanup, or deadlines.

**Mistake 20 — Deep-copying too late after the source has exposed a mutable value.** The client may have already grabbed the reference earlier; design immutability right at the boundary.

## 22. Checklist for Public Async APIs

- [ ] Is the component-owned source `CompletableFuture<T>` kept `private`?
- [ ] Does the public API actually only need `CompletionStage<T>`?
- [ ] Have you avoided `return internal;` even when the return type is an interface?
- [ ] If the client needs a full `CompletableFuture`, did you use `copy()`?
- [ ] Is it understood that the client can complete/cancel **its own copy**, but cannot complete the source?
- [ ] If using minimal, is it understood that the client can still use `toCompletableFuture()` to wait for the result?
- [ ] Do you avoid assuming every `CompletionStage` implementation is defensive on `toCompletableFuture()`?
- [ ] Is a mutable result `T` protected by an immutable DTO/defensive copy?
- [ ] Do you distinguish normal completion from exceptional/cancelled completion?
- [ ] Do callbacks avoid blocking the owner thread unnecessarily?
- [ ] Is there a separate cancellation API if the client needs to cancel real work?
- [ ] Are local caller timeouts implemented without unintentionally mutating the source?
- [ ] Have side effects that occurred before cancellation been accounted for?
- [ ] Have you checked the race between client completing the copy vs. source completing, without assuming the view always reflects the owner?
- [ ] If using a Java subclass of `CompletableFuture`, have you tested the contract overrides?
- [ ] Have you tested the case where the source completes before the view is created?
- [ ] Have you tested source failures and cause propagation?
- [ ] Are the owner executor/queue and shutdown properly controlled?
- [ ] Is there public documentation stating "clients only observe, they do not control the source"?

## 23. Practice Questions with Answers

**Q1.** `CompletableFuture<String> internal` is returned as-is through a method declared `CompletionStage<String> result()`. Is the source fully protected?

**Answer:** No. The runtime object is still the original `CompletableFuture`, so a client can cast it if it obtains that reference. Use `minimalCompletionStage()` to avoid exposing the source.

**Q2.** `CompletableFuture<String> exposed = internal.copy()`; the client calls `exposed.complete("fake")`. Does the source change?

**Answer:** No. `copy()` is a separate dependent `CompletableFuture`. The client only modifies the outcome of the copy.

**Q3.** `CompletionStage<String> view = internal.minimalCompletionStage()`. Can the client call `view.complete("fake")` directly?

**Answer:** No. The `CompletionStage` interface has no `complete` method.

**Q4.** The client calls `view.toCompletableFuture().complete("fake")`. Is the source completed with `"fake"`?

**Answer:** For a standard `CompletableFuture` minimal stage, no. `toCompletableFuture` creates a new non-minimal future per the Javadoc, without returning the source.

**Q5.** The source completes normally with an `ArrayList<String>`. Does the copy receive an independent list?

**Answer:** No. `copy` passes the same `T` reference. If data isolation is needed, create a snapshot/immutable result.

**Q6.** The source completed exceptionally. What do the copy and minimal stage see?

**Answer:** The corresponding exceptional completion, per the Javadoc with a `CompletionException` wrapping the cause. Calling `join` on a `CompletableFuture` view may throw `CompletionException`.

**Q7.** The client calls `copy.cancel(true)`; is the source task guaranteed to have stopped?

**Answer:** No. Only the copy is cancelled; by default `CompletableFuture.cancel` does not guarantee interrupting the computation or propagating backward to the source.

**Q8.** If an API needs synchronous waiting and the caller cannot yet use `CompletionStage`-only, what should you do?

**Answer:** Consider returning `copy()` for a legacy API, or calling `minimalStage.toCompletableFuture()` at the caller to `join/get` without exposing the source.

**Q9.** What is the main difference between `completedFuture(value)` and `completedStage(value)`?

**Answer:** `completedFuture` returns a full `CompletableFuture` with mutation methods; `completedStage` returns an already-completed, interface-limited `CompletionStage`.

**Q10.** Is `minimalCompletionStage` meant to defend against malicious code running in the same JVM?

**Answer:** No. It is an API/encapsulation boundary for completion authority, not a security sandbox.

**Q11.** If the client calls `copy.orTimeout(...)` and it times out, does the source automatically complete exceptionally?

**Answer:** No. The timeout is set on the copy; the source remains controlled by the owner. Background I/O is not automatically killed either.

**Q12.** Why is `source.copy()` equivalent to `source.thenApply(x -> x)`?

**Answer:** Both create a new dependent future, pass the normal result through an identity function, and propagate exceptional outcomes according to `CompletionStage` rules.

## 24. Official Documentation

- **CompletableFuture, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **CompletionStage, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Future, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **CompletionException, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html
- **CancellationException, Java SE 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CancellationException.html
- **Java 17 API, CompletableFuture.copy():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#copy()
- **Java 17 API, CompletableFuture.minimalCompletionStage():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html#minimalCompletionStage()

**Summary:** `minimalCompletionStage()` provides **a CompletionStage that restricts completion-manipulation rights**, while `copy()` provides **a separate CompletableFuture that can be mutated without changing the source**. They help a service retain ownership of completing/cancelling the original future. However, neither **deep-copies data T, automatically cancels background work, guarantees the client will see the source outcome if it intentionally completes its own view, nor replaces security/transaction boundaries**. Keep the original future private, expose the right abstraction, and return immutable results whenever possible.
