# Closing Resources and Unsubscribing Based on Ownership

When a Java operation opens a file, connection, stream, socket, lock, or registers a listener/callback, the system typically needs a symmetric counterpart: closing the resource, returning the connection, releasing the lock, canceling the subscription, or removing the listener. If cleanup happens at the wrong time or is performed by the wrong party, the program can leak resources, process duplicate events, retain unused objects, or corrupt a resource currently in use by another component.

**Core principle: the component that holds ownership (the owner) is responsible for ending the lifecycle of the resource or registration it owns.** Code that only borrows a resource (the borrower) must not close that resource on its own. This design is especially critical when exceptions occur: control flow can exit a method before reaching cleanup code written at the end of the method body.

This article places resource closing and unsubscribing under the **State Preservation** section of Java Exceptions: a failed operation must still leave the system in a valid lifecycle state, avoiding holding onto unnecessary resources, callbacks, or references.

## 1. What is resource ownership?

*Resource ownership* is a convention that defines which object or scope has the right and obligation to terminate the use of a resource. It is a **design contract**, not a mechanism that Java enforces with a dedicated keyword.

Common roles:

| Role | Example | Obligation |
| --- | --- | --- |
| Owner creating and holding a resource | A service opens an `InputStream` to read a file | Close the stream when leaving the usage scope, even if an exception occurs. |
| Borrower using temporarily | A method receives an `InputStream` from the caller solely for parsing | Do not close the stream unless the contract explicitly transfers ownership. |
| Registration owner | A component calls `eventBus.subscribe(listener)` and receives a handle | Unsubscribe when the component stops, is replaced, or no longer needs events. |
| Ownership-transferring owner | A factory creates a stream and returns it for the caller to manage | Clearly state that the caller is responsible for closing; the factory does not close it before returning. |
| Composite owner | An object creates three child resources and manages them | Close in the appropriate order, handling partial initialization as well. |

An **API illustration** example, not a standalone runnable program:

```java
// The caller owns the passed-in stream.
int parse(InputStream borrowedStream) throws IOException;

// The factory transfers ownership of the newly created stream to the caller.
InputStream openReport() throws IOException;

// The registration object belongs to the caller until the caller calls close().
Registration subscribe(Listener listener);
```

Both of the first two methods involve `InputStream`, yet their closing rules are completely different. That must be stated in the method name, Javadoc, contract documentation, and/or return type.

Merely holding a reference variable does not make a component the owner. Multiple objects may reference the same resource, but **there should be a single, clearly defined mechanism determining when the resource is released**. If a design uses shared ownership or reference counting, the coordination rules must be clearly documented rather than letting each component close it arbitrarily.

## 2. Why isn't cleanup at the end of a method enough?

Consider a Java snippet **illustrating the problem**:

```java
InputStream input = Files.newInputStream(path);
process(input);   // If process throws an exception...
input.close();    // ...this line is never executed.
```

There is no guarantee that `process` will complete normally. An `IOException`, data validation error, callback exception, or other error can cause execution to exit the code block before `close()`.

A more correct variant using `finally`:

```java
InputStream input = Files.newInputStream(path);
try {
    process(input);
} finally {
    input.close();
}
```

`finally` is normally executed when exiting the `try` block, even on a `return` or an exception. However, an exception thrown in `close()` can mask the original exception if written carelessly; the runtime also does not guarantee `finally` execution in every failure outside the JVM's control (such as a forcibly terminated process).

For `AutoCloseable` and `Closeable`, Java provides **try-with-resources**, which is usually the best choice for resources owned within a clear scope.

## 3. Try-with-resources: automatic closing upon exiting scope

Basic syntax:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

This snippet illustrates reading a file; `path` and `process` are assumed to be declared. Once the resource is successfully created, upon exiting the `try` block, Java calls `input.close()`. This applies both when the body succeeds and when it throws an exception.

Key characteristics:

- Variables in the resource declaration must have a type implementing `AutoCloseable`; `Closeable` also extends `AutoCloseable`.
- Java closes resources in the **reverse order of their declaration**. This is useful when a later-opened resource depends on an earlier-opened one.
- If initializing the second resource fails, the first resource that was already created is still closed.
- If both the body and `close()` throw an exception, Java prioritizes the exception from the body; the exception from `close()` is attached to the primary exception's `getSuppressed()`.
- If the body succeeds but `close()` throws an exception, the closing exception can propagate out.
- Try-with-resources does not inherently know whether a resource is "borrowed" or "owned". **Putting a borrowed resource into the resource list will close it**, which can violate the contract.

An **illustrative** example with two resources:

```java
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    runOperation(first, second);
}
```

Here, the declarations `Resource`, `openFirst`, `openSecond`, and `runOperation` are assumed. If both resources are created, Java closes `second` first and then `first`. If creating `second` fails, `first` is still closed. This order avoids closing the underlying resource of a wrapper before closing the wrapper itself, provided the dependency relationship is designed accordingly.

### Java 9+ and pre-existing resources

Since Java 9, a resource variable declared outside, if `final` or **effectively final**, can be used directly in the resource header of `try`:

```java
InputStream owned = Files.newInputStream(path);
try (owned) {
    // Read the stream owned by this scope.
}
```

This is still **a close operation** on `owned`. The syntax does not prove ownership; it is the developer's responsibility to pass a resource into `try` only when that scope is permitted to close it.

## 4. When must a parameter receiver NOT close?

Suppose an API receives a stream created by the caller:

```java
public static int countBytes(InputStream borrowed) throws IOException {
    byte[] buffer = new byte[1024];
    int total = 0;
    int count;
    while ((count = borrowed.read(buffer)) != -1) {
        total += count;
    }
    return total;
}
```

This is an **illustrative method**, without a complete class to run on its own. It reads data but **does not call `close()`**, because the caller is the owner. The caller can continue operating on the stream after the call, if the stream's characteristics and read position allow.

The API documentation should explain:

> This method only borrows `input` for the duration of the call and does not close the stream. The caller retains responsibility for closing the stream.

If the API decides to take over ownership, state it explicitly:

> This method takes ownership of the stream and will close it upon completion or failure.

However, transferring ownership at the call site can raise a question: if validation fails before the API takes over, who closes it? The contract must define **the exact point of ownership transfer**. For APIs that are hard to specify, it is often more maintainable for the caller to retain ownership of the resource and wrap the call in `try-with-resources`.

Also, never automatically close `System.in`, `System.out`, shared connections, shared contexts, or framework-managed streams. Closing a borrowed resource can break unrelated operations downstream.

## 5. Unsubscribing listeners is also resource cleanup

A listener/subscriber registration typically creates a link from the publisher to the callback. The publisher may hold a strong reference to the listener; the listener in turn may hold a UI component, service, cache, or large object. If the component disappears without canceling the registration, callbacks may still be invoked and the object graph may still be kept alive.

An ownership-clear design returns a **handle** upon registration:

```java
Registration registration = eventHub.subscribe(listener);
try {
    doWork();
} finally {
    registration.close();
}
```

This illustrates a `Registration` assumed to be `AutoCloseable` whose `close()` does not declare a checked exception. The handle represents the **right to cancel a single registration**; the code owning the handle must cancel it when no longer needed.

There are two common API styles:

| API | Cleanup approach | Common pitfall |
| --- | --- | --- |
| `addListener(listener)` / `removeListener(listener)` | Owner must call `removeListener` with the exact listener instance | Creating a new lambda when removing, so it does not match the added object. |
| `subscribe(listener)` returning `Registration` or `Subscription` | Owner holds the handle and calls `close` / `unsubscribe` / `cancel` accordingly | Losing track of the handle or confusing ownership when sharing the handle. |

Regarding lambdas:

```java
// Error-prone: two lambda expressions are not a single registration handle.
publisher.addListener(event -> handle(event));
publisher.removeListener(event -> handle(event));
```

In this **illustrative** snippet, `publisher` and `handle` are undefined. The takeaway is never to rely on writing the same lambda expression twice to guarantee removing the right registration. Store the instance instead:

```java
Listener listener = event -> handle(event);
publisher.addListener(listener);
try {
    // Subscriber lifecycle.
} finally {
    publisher.removeListener(listener);
}
```

If the API provides an independent handle, it is generally better to hold the handle rather than relying on callback matching.

## 6. Designing handles to work with try-with-resources

When a registration only needs to exist within a short scope, `Registration` can implement `AutoCloseable`:

```java
public interface Registration extends AutoCloseable {
    @Override
    void close(); // Narrowed signature: does not declare a checked Exception.
}
```

This is a **standalone interface definition**, not a runnable program with `main`. If `subscribe` returns `Registration`, the caller writes:

```java
try (Registration owned = eventHub.subscribe(listener)) {
    eventHub.publish("hello");
}
```

The registration resource is canceled even if a callback or code inside `try` throws an exception. This ties cleanup to lexical scope.

Note: `AutoCloseable.close()` may declare `throws Exception`; an override like the one above narrows it to **not throw a checked exception**, so callers do not have to handle `Exception` just to cancel a simple registration. The `AutoCloseable` specification **does not require** every implementation to be idempotent. If a registration design allows calling `close()` multiple times, that must be implemented and clearly documented.

When a registration outlives a single call—such as a listener for a component that lives for several minutes—the owner should store the handle in a field and close it in the component's `stop()`/`close()` method, rather than creating a short try-with-resources block that cancels the newly registered callback prematurely.

## 7. Complete Java 17 example: owner, borrowed resource, and registration

This example simulates three scenarios:

1. Two resources are created in a single scope; an operation fails and both resources are still closed in reverse order.
2. The caller creates a resource and passes it to a borrowing method; the borrower uses it without closing it.
3. The caller registers a listener, uses the handle to unsubscribe, calls `close()` twice according to the idempotent contract of the **handle in the example**, and then verifies no subscribers remain.

Create the file `OwnershipCleanupDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public class OwnershipCleanupDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    private interface Registration extends AutoCloseable {
        @Override
        void close();
    }

    private static final class Resource implements AutoCloseable {
        private final String name;
        private boolean closed;

        Resource(String name) {
            this.name = name;
            EVENTS.add("open " + name);
        }

        void work(boolean fail) {
            if (closed) {
                throw new IllegalStateException("resource closed");
            }
            if (fail) {
                throw new IllegalStateException("work failed");
            }
            EVENTS.add("work " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                EVENTS.add("close " + name);
            }
        }
    }

    private static final class EventHub {
        private final List<Consumer<String>> listeners = new ArrayList<>();

        Registration subscribe(Consumer<String> listener) {
            Objects.requireNonNull(listener, "listener");
            listeners.add(listener);

            return new Registration() {
                private boolean closed;

                @Override
                public void close() {
                    if (!closed) {
                        closed = true;
                        listeners.remove(listener);
                        EVENTS.add("unsubscribe");
                    }
                }
            };
        }

        void publish(String value) {
            for (Consumer<String> listener : List.copyOf(listeners)) {
                listener.accept(value);
            }
        }

        int subscriberCount() {
            return listeners.size();
        }
    }

    private static void failDuringWork() {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            second.work(true);
        }
    }

    // Borrower: never close a resource owned by the caller.
    private static void useBorrowed(Resource borrowed) {
        borrowed.work(false);
    }

    public static void main(String[] args) {
        try {
            failDuringWork();
        } catch (IllegalStateException ex) {
            EVENTS.add("caught: " + ex.getMessage());
        }

        // This scope is the owner of the Resource.
        try (Resource callerOwned = new Resource("caller-owned")) {
            useBorrowed(callerOwned);
        }

        EventHub hub = new EventHub();
        Registration ownedRegistration =
                hub.subscribe(value -> EVENTS.add("event: " + value));

        hub.publish("one");
        ownedRegistration.close();
        ownedRegistration.close(); // Idempotent per the example's implementation.
        hub.publish("two");
        EVENTS.add("subscribers: " + hub.subscriberCount());

        EVENTS.forEach(System.out::println);
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 OwnershipCleanupDemo.java
java OwnershipCleanupDemo
```

Expected output:

```text
open first
open second
close second
close first
caught: work failed
open caller-owned
work caller-owned
close caller-owned
event: one
unsubscribe
subscribers: 0
```

Why does it produce this output?

- `first` opens before `second`. An exception occurs in `second.work(true)`, yet try-with-resources still closes `second` and then `first` before the exception reaches the outer `catch`.
- `useBorrowed` only calls `work(false)`. `callerOwned` is closed by the **caller's** `try`, not by the borrowing method.
- `subscribe` adds a single listener. After receiving event `one`, the owner closes the registration. Event `two` is no longer delivered to the listener, so there is no `event: two` line.
- The second `close()` call does not change state because the example's implementation checks `closed`; only one `unsubscribe` line appears.
- `subscriberCount()` equal to 0 proves that in this synchronous example, the listener list has been cleaned up. In a real system, concurrent threads and in-flight callbacks must be considered.

**Limitations of the example:** `EventHub` and `Resource` use `ArrayList` and boolean flags to demonstrate single-threaded ordering; they are **not thread-safe**. Do not use this prototype as a multithreaded event bus. In practice, appropriate synchronization, lifecycle, and cancellation policies are required.

## 8. Exceptions thrown during close: getSuppressed()

A subtle issue: the operation body throws error A; during cleanup, `close()` throws error B. Which exception should propagate?

With try-with-resources, the exception from the body is the primary exception; the exception thrown during closing is **suppressed** onto the primary exception. This preserves both causes without letting a cleanup error hide the original error.

Create the file `SuppressedCleanupDemo.java`:

```java
import java.io.IOException;

public class SuppressedCleanupDemo {

    private static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingClose resource = new FailingClose()) {
            throw new IOException("work failed");
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getSuppressed().length);
            System.out.println(ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

Expected output:

```text
work failed
1
close failed
```

`ex.getSuppressed()` is an array of suppressed exceptions. In the example, the main operation produces one `IOException` and `close` produces another `IOException`. If only `close()` fails while the `try` body succeeds, the error from `close()` becomes the primary exception.

Do not "fix" this by swallowing all `close()` errors. A close failure can cause data loss or indicate that an operation did not complete reliably (for example, when flushing a buffer). Define an explicit policy: does the caller need to know about close failures, is the state recoverable, and where should logs be recorded?

An outer `catch` only receives the final exception; for full diagnostics, record both the cause and suppressed exceptions using an appropriate logging system.

## 9. Cleanup in finally, state, and error precedence

`finally` is still necessary for mechanisms not naturally expressed with `AutoCloseable` or when conditional actions must be performed. However, avoid this pattern:

```java
try {
    doWork();
} finally {
    resource.close(); // May throw and mask the exception from doWork().
}
```

This is an illustrative snippet, with `doWork` and `resource` defined elsewhere. If `doWork` throws exception A and `close()` throws exception B, this `finally` block can cause exception B to replace A. If the resource implements `AutoCloseable`, try-with-resources usually preserves both much better.

When using `finally` with callback registration, if `unsubscribe()` can also throw, you must decide how to preserve the original error and report the cleanup error. Do not swallow exceptions by default just because "it is only releasing"; conversely, do not let an unimportant cleanup error break business processing if the cleanup contract genuinely guarantees it is safe to ignore. The decision must be based on the API's semantics.

If there are multiple manual cleanup steps, ensure that one failing step does not accidentally prevent releasing the remaining independent resources. Try-with-resources automatically supports closing multiple resources even if closing one of them throws an exception.

## 10. Partial initialization also needs cleanup

Suppose a component requires three registrations. If the third step fails, the first two still exist. If handles are only closed after everything has initialized successfully, the program can leak right inside the constructor or startup path.

Design approaches:

1. **Create and register within a rollback-capable scope.** When a subsequent step fails, close the resources/handles created earlier.
2. **Transfer ownership only after initialization succeeds.** A factory can hold resources in a temporary scope; once construction finishes, it hands over a composite object whose `close()` manages all of them.
3. **Clarify every failure point.** If opening the second connection throws, is the first connection closed? If a callback is already registered and the rest fails, is the earlier handle canceled?

The snippet below illustrates a composite scope when subscriptions return `AutoCloseable` handles. This is **conceptual illustrative code**, omitting `subscribeA`, `subscribeB`, `run`, and the concrete handle type:

```java
try (Registration first = subscribeA();
     Registration second = subscribeB()) {
    run();
}
```

If `subscribeB()` throws an exception, `first` is closed. But if `subscribeB()` creates a registration and then throws **before returning the handle**, the caller's code has not yet received the handle to cancel it. Therefore, `subscribeB()`'s own implementation must clean up any partial resources it created before reporting the error. This is the distinction between **caller cleanup after receiving a handle** and **internal cleanup when a factory fails partway through**.

### Transferring ownership after construction completes

A composite can own multiple child resources and close them in reverse order. The composite owner must track a `closed` state and define whether `close` can be called multiple times. If the caller cannot construct a valid composite because an exception is thrown partway through, the factory/builder is responsible for closing what was already created; responsibility must not be pushed onto the caller when the caller has not received an object.

## 11. Unsubscribing and concurrency races

For a multithreaded publisher, distinguish two guarantees:

1. **No new callbacks are received after unsubscribing.**
2. **No callbacks are still running when the unsubscribe call returns.**

An API may guarantee (1) for events starting after the cancellation point, but **does not automatically guarantee (2)**. Callbacks already queued or already executing before `unsubscribe()` was called may continue after cancellation, depending on the implementation.

Example sequence:

```text
Thread A: publisher has already selected the listener to invoke
Thread B: owner calls unsubscribe()
Thread B: unsubscribe() returns
Thread A: callback may still run, if the API does not wait for in-flight callbacks
```

To avoid using closed state:

- Callbacks can check lifecycle state before accessing sensitive data.
- The publisher must have synchronization, versioning, or generation tokens when stale events need to be discarded.
- If the API promises that all callbacks have stopped once cancellation completes, an appropriate wait/drain mechanism is required; simply removing an element from a list is not enough.
- When callback cleanup also needs to stop threads, executors, timers, or network listeners, distinguish **cancel request** from **await completion** according to each API's contract.
- Do not hold a lock for a long time and invoke arbitrary callbacks if there is a risk of deadlock or reentrant calls; the exact design depends on the concurrency model.

Documentation for `close()`/`unsubscribe()` should clearly state guarantees regarding in-flight callbacks and thread safety. The `EventHub` example in the earlier section only demonstrates single-threaded behavior and does not provide these concurrency guarantees.

## 12. Cancellation, interruption, and ownership

Not every registration uses `close()`. Some APIs return a `Future`, `Subscription`, or token with a `cancel()` method. The owner of the task/subscription must decide when to cancel, though the semantics are not identical to closing a stream.

- `Future.cancel(boolean mayInterruptIfRunning)` is a cancellation request. The return value indicates whether the cancellation request succeeded according to the `Future`'s state; it does not prove the task has stopped immediately.
- With Reactive Streams APIs, `Subscription.cancel()` requests stopping further signal delivery per the protocol contract; races and in-flight signals must still be understood.
- When a thread is interrupted via `InterruptedException`, do not accidentally lose the interrupt flag if catching and translating the exception. Typically, `Thread.currentThread().interrupt()` is needed before propagating the error in another form, unless the method propagates `InterruptedException` itself or has another explicit policy.
- Canceling a subscription does not implicitly close the producer or resources shared with other subscribers. The owner must cancel only what it owns.

An **illustrative snippet**, assuming a custom `TaskCancelledException` type:

```java
try {
    waitForWork();
} catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new TaskCancelledException("Tác vụ bị ngắt", cause);
} finally {
    registration.close();
}
```

Here `waitForWork`, `TaskCancelledException`, and `registration` are illustrative symbols not fully declared. If `registration.close()` can throw, apply the original-exception preservation policy from sections 8–9. Restoring the interrupt flag allows upstream logic to still recognize the interruption request when the exception is no longer thrown as `InterruptedException`.

## 13. Closing a resource does not mean rollback

Cleanup returns resources and severs links, but **does not automatically undo all business changes**.

Examples:

- Closing a `FileOutputStream` does not delete data already written.
- Closing a JDBC connection is not always equivalent to a rollback under the application contract; transaction management must have explicit commit/rollback rules.
- Unsubscribing a listener does not retract events the callback has already processed.
- Canceling an HTTP request does not prove the server has not written data.
- Closing a network client can abort other requests if the client is a shared resource.

Therefore, separate three responsibilities:

| Responsibility | Goal | Example |
| --- | --- | --- |
| Lifecycle cleanup | Release owned resources/registrations | `close()`, `unsubscribe()`, `removeListener()`. |
| Rollback/compensation | Restore or compensate business changes | Rolling back a transaction, deleting temporary records, or executing a compensating action. |
| Error preservation | Retain primary error and cleanup error details | `getCause()`, `getSuppressed()`, contextual logging. |

When an operation requires **strong exception safety** (failure leaves observable state unchanged), true staging, transactions, or rollback must be designed; merely adding `finally { close(); }` is not enough.

For operations with **basic exception safety**, state may change partially, but object invariants remain valid and no resources are leaked. Determine the appropriate guarantee level rather than guessing.

## 14. Designing lifecycle and public API contracts

A well-designed resource-managing API clearly answers:

- **Who creates?** Who holds ownership of the handle?
- **Who closes?** Caller, callee, container/framework, or lifecycle manager?
- **When to close?** End of method, end of transaction, component stop, or application shutdown?
- **What happens on a second close?** Idempotent, throws an error, or undefined? Do not assume from `AutoCloseable`.
- **What can close throw?** Are cleanup errors important to the caller? Could there still be pending writes?
- **Can other methods be called after close?** If not, which exception signals an invalid state?
- **Are there in-flight callbacks?** Does unsubscribing wait for currently running callbacks to finish?
- **Is the resource shared?** If so, could one borrower accidentally break others by closing it?
- **What if initialization fails partway through?** Are previously created resources properly cleaned up?

Illustrative Javadoc for a registration handle contract (without an implementation):

```java
/**
 * Ownership of a listener registration.
 *
 * <p>Created by {@code subscribe}. The caller must close it when
 * events are no longer needed. Closing multiple times has no additional effect.
 * After close returns, no new callbacks are started;
 * callbacks already running beforehand may continue to completion.
 */
public interface Registration extends AutoCloseable {
    /**
     * Cancels the registration represented by this handle.
     */
    @Override
    void close();
}
```

This Javadoc is only appropriate for **an implementation that actually guarantees everything described**. Do not copy it onto every event bus; in particular, the promise of "no new callbacks" requires proper synchronization under concurrency.

If a method returns a handle by transferring ownership, it can document:

```java
/**
 * Registers a listener and transfers registration ownership to the caller.
 *
 * @param listener callback receiving events, must not be null
 * @return handle that must be closed by the caller when events are no longer needed
 * @throws NullPointerException if {@code listener == null}
 */
Registration subscribe(Listener listener);
```

This is an illustrative signature snippet; `Listener` is not declared. Real APIs may use a different callback type.

## 15. Common design mistakes

**1. Using `try-with-resources` on a borrowed resource.** The syntax is valid, but the semantics are wrong: it calls `close()` on the caller's resource. Identify the owner before writing `try`.

**2. Closing too early.** Subscribing inside a `try` block that ends right after creating the UI; when the UI actually runs, the listener has already been canceled. The cleanup scope must match the usage lifecycle, not just the shortest lexical scope.

**3. Failing to close when a constructor or startup fails.** Some resources were created, but the object is never returned to the caller; the implementation itself must roll back the successful acquisitions.

**4. Failing to unsubscribe callbacks.** The publisher retains the listener indefinitely, leading to callbacks after the component stops, retained references, and sometimes duplicate event processing.

**5. Using a new lambda to remove an old listener.** Store the exact instance or keep the registration handle returned by the API.

**6. Swallowing all close errors.** Especially with flushing streams, a close failure can indicate that data was not fully written. Distinguish cleanup that cannot fail from cleanup with consequences.

**7. Assuming every close is idempotent.** `AutoCloseable` does not guarantee this for every implementation. Define it yourself or follow the library's specific contract.

**8. Cleaning up only on success, skipping the exception path.** Use try-with-resources or an appropriate `finally`; test failure paths before and after acquisition.

**9. Assuming unsubscribe immediately stops multithreaded callbacks.** Depending on the API, callbacks already running or queued may continue. Lifecycle synchronization is needed for stronger guarantees.

**10. Confusing cleanup with rollback.** Closing a resource does not restore modified data. If the API promises unchanged state on failure, separate transaction/compensation logic is needed.

## 16. Testing exception safety of cleanup

Test scenarios near lifecycle boundaries:

| Scenario | What to assert |
| --- | --- |
| Operation succeeds | The resource owner closes it once per contract, or the exact number of times required by the logic. |
| `try` body throws an exception | The resource is still closed; the primary exception is not lost. |
| Error creating the second resource | The already-opened first resource is closed, with no dangling registration. |
| Both processing and `close()` throw | The primary exception remains intact; the close error is in `getSuppressed()`. |
| Method only borrows resource | The caller's resource remains open after the call; the caller closes it. |
| Subscribe then clean up | The listener receives no new events per the API guarantee; the handle is not forgotten. |
| Closing handle twice | The outcome matches the documented idempotency policy. |
| Unsubscribing concurrently with publish | No data race/deadlock; behavior matches the contract for in-flight callbacks. |
| Write operation fails partway through | Verify side effects/rollback per the API guarantee, separate from resource release. |

With `OwnershipCleanupDemo`, checking the `EVENTS` list reveals the closing order, and `subscribers: 0` shows the registration was removed. In real applications, test at the adapter or integration level to catch leaked file handles, connections, listeners, and still-running tasks.

Prefer **testing behavior** over asserting implementation details. For example, if the contract only promises that the resource is eventually closed, do not force the implementation to make exactly one internal `close` call if an idempotent mechanism is allowed.

## 17. Exercises and self-check questions

**Scenario A:** The method `parse(InputStream input)` receives a stream from the caller. Should it write `try (input)`?

**Answer:** Only if the contract transfers ownership to `parse`. If the API only borrows the stream, the method must not close it. The caller should wrap creation and the call in `try-with-resources`.

**Scenario B:** A component registers three listeners, but the third registration throws an exception. Who cancels the first two listeners?

**Answer:** The component holding the first two registrations during initialization must cancel them before reporting failure. If the factory has not yet returned the component to the caller, the caller cannot perform this internal cleanup.

**Scenario C:** Inside try-with-resources, the processing body throws `IOException("write")` and `close()` throws `IOException("close")`. What does the caller normally receive?

**Answer:** The caller receives the primary exception `"write"`; the `"close"` exception is in `getSuppressed()`. With a hand-written `finally` calling `close()` directly, the close error could mask the processing error.

**Scenario D:** `unsubscribe()` returns, yet a callback that already started on another thread is still running. Is the API definitely broken?

**Answer:** Not necessarily. Check whether the contract guarantees waiting for in-flight callbacks or only prevents the registration from receiving new events. If running callbacks must also be blocked/drained, appropriate synchronization or completion waiting must be designed.

**Scenario E:** A shared HTTP client object is used by ten requests. Should each request call `client.close()`?

**Answer:** No, if the client is owned by the application/lifecycle manager and requests only borrow it. Each request only cleans up the resources it owns (for example, its own body/response per the library's contract). The owner of the shared client closes it at the end of the application's lifecycle.

## 18. Practical rule of thumb

The easiest rule to verify is to draw an **acquire -> release** pair for every resource, subscription, or task: who takes responsibility, when it is released, which error paths go through cleanup, and what happens if cleanup itself fails. Put short-lived owned resources in try-with-resources; use explicit handles/lifecycle methods for long-lived registrations; leave borrowed resources intact; and account for partial initialization and concurrency races. When done right, exceptions can fail an operation without turning a failure into a resource leak or a corrupted lifecycle state.