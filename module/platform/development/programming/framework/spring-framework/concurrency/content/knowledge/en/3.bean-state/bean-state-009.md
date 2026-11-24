# Tracing State Shared Through Arguments and Return Values

## 1. Objective: Seeing Where State Is Actually Shared

In the Spring Framework, a `singleton` bean is often invoked concurrently by many requests and threads. Risk does not come solely from fields inside the bean: mutable state can enter **the bean through an argument**, travel through multiple service/repository/callback layers, and **escape outside through a return value**. Two seemingly independent calls can still hold references to the same object and corrupt each other's data.

This lesson teaches how to trace **reference paths, mutation rights, and access timing**. After studying it, you should be able to answer five questions for any invocation:

1. Where is the object created, who owns it, and can it be mutated?
2. Does the parameter receive **an isolated value** or **a reference to the same mutable object**?
3. Does the method mutate the parameter object, store it in a field/cache, or forward it to another thread?
4. Is the return value a fresh value, a snapshot, a view, or the internal object itself?
5. How many threads can read/write that object at the same time, and what mechanism protects it?

**Scope:** tracing bean state across Java and Spring data flows; understanding correctness issues and design options. This is not a survey of all concurrency primitives.

## 2. Vocabulary and Reference Model to Master

- **State:** data describing an object at a point in time, such as `Cart.items`, `Order.status`, or `Service.lastRequest`.
- **Mutable object:** an object whose contents can change after creation, e.g., `ArrayList`, `HashMap`, a DTO with setters, arrays, `StringBuilder`.
- **Immutable value:** an object whose observable state cannot change after creation, e.g., `String`, `Integer`, or a record designed so all nested data is also immutable.
- **Reference/alias:** two distinct variables pointing to the same object. `a == b` being true for two reference variables means identical identity; `a.equals(b)` can be true even for two distinct objects.
- **Ownership:** the convention defining which component is allowed to mutate and manage an object's lifecycle. Java does not enforce ownership via ordinary reference types.
- **Escape:** a reference intended to remain internal escaping outward, such as saving an argument in a singleton field, capturing it in a long-lived callback, or returning an internal collection.
- **Snapshot:** a point-in-time copy of values. A *shallow* snapshot copies only the outer structure; mutable elements inside may still be shared.
- **Thread confinement:** state accessed by only one thread during its relevant lifecycle. A local variable only has its own reference slot on the stack; the object it points to can still be shared.

Java passes arguments **by value** (*pass-by-value*). For primitives, the numeric/boolean value is copied; for reference types, **the reference value is copied**, while the underlying object is not copied automatically. Therefore, inside a method, reassigning a parameter variable does not point the caller's variable to a new object, yet mutating state on the object both variables point to lets the caller observe the change.

```text
Caller                         Bean method                      Return
  request ── reference ───────► parameter
     │                              │
     └────────► Mutable DTO ◄───────┘
                    │
                    ├──── bean.field = parameter  (escape/retention)
                    ├──── executor.submit(() -> use(parameter))  (cross-thread)
                    └──── return parameter  (escape/alias)
                              │
callerResult ─────────────────┘ same identity, no automatic copy created
```

The diagram depicts possible paths, not a claim that every method retains or returns its input object. At every arrow, verify what is actually passed and whether any copying occurs.

## 3. Tracing an Argument from Caller into the Bean

Suppose a controller calls `service.process(command)`. Do not stop at the variable name `command`; follow the **concrete object** moving through the call:

| Checkpoint | Key question | Signals to inspect |
| --- | --- | --- |
| Controller / caller | Is `command` freshly created for this call or pulled from a field/cache/session? | `new` sites, factories, cache lookups, injection |
| At DTO construction | Are internal fields copied? | Constructors, setters, `List.copyOf`, copy constructors |
| Entering service | Does the method only read, mutate directly, or retain the reference? | `setX`, `add`, `put`, `this.current = command` |
| Across downstream calls | Is the DTO itself or its mutable elements passed to other methods? | Parameter forwarding, lambda captures, callbacks, events |
| Crossing to async | Does the task start before or after the caller keeps mutating the DTO? | `@Async`, executors, futures, queues, latches |
| Returning | Does the caller get a new value or a reference held in multiple places? | `return command`, `return this.items`, copy/snapshot |

An object freshly created per HTTP request **can usually be safe** if nobody shares it concurrently and it does not escape into state outliving the request. However, receiving a DTO as a parameter does not prove that DTO is private: the caller might pass the same object to two jobs, put it in a cache, or hand it to an async task.

Subtle ways state can become shared:

- Storing an argument in a singleton bean's field, a `static` object, registry, cache, or shared collection.
- Returning an internally managed object, array, `List`, or `Map` directly.
- Passing a mutable element inside a collection to another component.
- Capturing a reference inside a lambda, callback, listener, or `Runnable` to run later.
- Using a dependent bean with mutable fields even though the current bean has no fields.
- Using `ThreadLocal` or a context holding a mutable object and then handing that same object to another thread. ThreadLocal does not make an object immutable.

A field declared `final` only prevents **reassigning the field reference**; it does not prevent `list.add(...)` on the list held by that field.

## 4. Java Example: The Same Object Passed via Parameter and Returned

File `AliasFlowDemo.java` runnable on Java 17+:

```java
import java.util.ArrayList;
import java.util.List;

public class AliasFlowDemo {
    static final class RequestData {
        private final List<String> tags;

        RequestData(List<String> tags) {
            this.tags = tags; // Intentionally retains the exact reference
        }

        List<String> tags() {
            return tags; // Intentionally exposes internal collection
        }
    }

    static List<String> process(RequestData request) {
        request.tags().add("server");
        return request.tags();
    }

    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("caller"));
        RequestData request = new RequestData(callerTags);

        List<String> returned = process(request);

        System.out.println(callerTags);
        System.out.println(callerTags == returned);

        returned.add("outside");
        System.out.println(request.tags());
    }
}
```

```bash
javac AliasFlowDemo.java
java AliasFlowDemo
```

Result:

```text
[caller, server]
true
[caller, server, outside]
```

Reference path analysis:

1. `callerTags` is a mutable `ArrayList` created by the caller.
2. `RequestData`'s constructor assigns `this.tags = tags`; it is the exact same list, even though the field is `final`.
3. `process` mutates the list via the `request` parameter, so the caller observes `"server"`.
4. `process` returns that exact list; `returned == callerTags` is `true`.
5. When the caller mutates `returned`, `request.tags()` changes too. There is no concurrency in this demo, yet when multiple threads perform these steps concurrently, data races and business rule violations occur.

**Takeaway:** two differently named variables in two different classes do not mean two independent regions of state. Track object identity, not just variable names.

## 5. Distinguishing Local Parameters from Objects Inside Parameters

The following method only reassigns its local parameter variable, so it does not change the caller's reference:

```java
static void replace(List<String> values) {
    values = new ArrayList<>(); // Only local variable 'values' points elsewhere
    values.add("new");
}
```

This is an illustrative fragment; assume `List` and `ArrayList` are imported. Conversely, `values.clear()` or `values.add(...)` acts on the exact object the caller passed in.

With a primitive parameter like `int count`, incrementing `count++` inside the method does not mutate the caller's primitive variable. However, if the primitive is a **field inside an object** and the method calls `request.setCount(...)`, the shared object is still mutated.

Do not equate these two statements:

- "The method has no shared mutable local variables" is a claim about **local variable slots**.
- "The method operates on no shared mutable state" is a much stronger claim about **the entire reachable object graph**: parameter objects, their elements, injected beans, and returned objects.

A service with no mutable fields can still perform non-thread-safe operations if callers pass the same `ArrayList` from different threads to mutate together. Conversely, a stateless service that only reads immutable inputs and builds immutable outputs is usually easy to use safely across many requests.

## 6. Tracing State Exiting Through Return Values

A return value is a critical escape point. Check how a method builds its return value before judging safety.

| Return pattern | What it actually is | Risk / capability |
| --- | --- | --- |
| `return internalList;` | The exact internal list | Caller can mutate bean data; multiple callers can mutate concurrently |
| `return Collections.unmodifiableList(internalList);` | View blocking writes through the view variable | If backing `internalList` changes, the view reflects those changes |
| `return List.copyOf(internalList);` | Unmodifiable collection containing a snapshot at copy time | **Shallow** copy; mutable elements inside can still be shared |
| `return new ArrayList<>(internalList);` | New mutable outer list | Caller mutates its own list structure, yet mutable elements stay shared |
| `return new Result(total, status);` | Fresh result object | Safer if all fields and nested objects are immutable |
| `return this;` | Same stateful instance | Can expose the object's entire mutable API |
| `return CompletableFuture<T>;` | Handle to a future result | Once completed, `T` can still be a shared mutable object |

No single copy call solves every case automatically. Decide **what level of snapshot is required**: copying only the outer list, copying each element DTO, or converting to fully immutable value objects. `List.copyOf` requires non-null elements; if data can contain nulls, pick another strategy and document the contract clearly.

### 6.1. Example: Read-Only View vs. Snapshot

File `ViewVsSnapshotDemo.java` runnable on Java 17+:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(original);
        List<String> snapshot = List.copyOf(original);

        original.add("B");

        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot blocks add");
        }
    }
}
```

```bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

Result:

```text
view=[A, B]
snapshot=[A]
snapshot blocks add
```

`view` forbids modification through the view itself, yet still observes changes to `original`; `snapshot` preserves the list structure as of creation time. This example uses `String` (immutable). If elements were `MutableAddress` or `ArrayList`, even with a snapshot of the outer list, each element's contents could still be mutated from elsewhere.

### 6.2. Designing Immutable DTOs with Defensive Copies

File `ImmutableBoundaryDemo.java` runnable on Java 17+:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableBoundaryDemo {
    record Command(String id, List<String> tags) {
        Command {
            tags = List.copyOf(tags);
        }
    }

    record Result(String id, int count) {}

    static Result handle(Command command) {
        return new Result(command.id(), command.tags().size());
    }

    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("first"));
        Command command = new Command("R-1", callerTags);

        callerTags.add("later");
        Result result = handle(command);

        System.out.println(command.tags());
        System.out.println(result.id() + ":" + result.count());
    }
}
```

```bash
javac ImmutableBoundaryDemo.java
java ImmutableBoundaryDemo
```

Result:

```text
[first]
R-1:1
```

Records do not automatically turn mutable components deeply immutable. The constructor normalizes with `List.copyOf` to sever aliasing with the caller's list. Because elements here are `String`s, this snapshot suffices for the example. If the record held `List<MutableItem>`, immutable elements or element copying would be needed too. The moment of copying must also be protected if another thread is concurrently mutating the source list.

In real APIs, build a *result DTO* describing the data the caller needs rather than returning an entity cached/managed by a bean. Separating the **data contract** from **internal object identity** makes code far easier to trace and test.

## 7. Bean Scope Does Not Replace Checking Reference Sharing

In Spring, scopes affect instance lifecycle; they do not automatically make mutable objects thread-safe.

| Scope / situation | What is usually true | What must still be checked |
| --- | --- | --- |
| `singleton` (default) | One bean instance per bean definition in a Spring container | Concurrent requests/threads calling it and accessing fields or retained data |
| `prototype` | Spring creates an instance when the container is asked for the bean | If injected once into a singleton, the singleton normally keeps that injected instance; not recreated per call |
| `request` | Instance bound to an active HTTP request | Did the reference pass to async / get saved in a singleton; is request scope still active when accessed? |
| Method local | Each invocation gets its own local variables | Is the object pointed to by a local variable shared? |
| `final` bean dependency | Dependency reference cannot be reassigned | Does the dependency hold mutable fields or unsynchronized caches? |

Example of an **unsafe Spring pattern** (fragment requiring a Spring project and a `Cart` definition):

```java
@Service
class CartService {
    private Cart lastCart;

    public Cart inspect(Cart argument) {
        lastCart = argument; // Retains caller's reference inside singleton
        return lastCart;     // Hands retained reference back out to caller
    }
}
```

Assume `org.springframework.stereotype.Service` is imported. In this design, `argument` moves into a long-lived field and is returned, so a subsequent request can overwrite `lastCart`; two threads can also access the mutable `Cart` simultaneously. Adding `volatile` to `lastCart` only improves visibility of the **field reference**; it does not make operations on `Cart` atomic, does not separate ownership, and does not stop one request from reading another request's state.

A safer version usually needs no `lastCart` field at all: read needed data from the command, compute with local immutable values, and return a new `CartResult`. If shared state must genuinely be retained (e.g., a cache), specify clearly what is stored, how atomic updates work, lifetime, synchronization policy, and what kind of snapshot is returned.

## 8. Crossing Thread Boundaries: Arguments Can Still Share Identity

With executors, `CompletableFuture`, or `@Async`, the caller can keep running after submitting a task. If the task holds the same reference to a mutable DTO, state can change **before the task reads it**. That differs from passing an immutable snapshot captured prior to submission.

An important `ExecutorService` rule: actions in the thread prior to submitting a task *happen-before* actions in the task; and actions in the task *happen-before* the caller successfully retrieves the result via `Future.get()`. That rule **does not** create an immutable snapshot of arguments and does not automatically order mutations performed after submission.

### 8.1. Complete Example: Task Reads a Mutation Made After Submission

File `AsyncAliasDemo.java` runnable on Java 17+:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncAliasDemo {
    static final class Payload {
        private String message;

        Payload(String message) {
            this.message = message;
        }

        void setMessage(String message) {
            this.message = message;
        }

        String message() {
            return message;
        }
    }

    public static void main(String[] args) throws Exception {
        Payload payload = new Payload("before");
        CountDownLatch allowRead = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> result = executor.submit(() -> {
                allowRead.await();
                return payload.message();
            });

            payload.setMessage("after");
            allowRead.countDown();
            System.out.println(result.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AsyncAliasDemo.java
java AsyncAliasDemo
```

Result:

```text
after
```

What happened?

- The task was submitted while `payload.message` was still `"before"`, yet it did not receive a copy of `Payload`.
- The caller mutated the same object to `"after"` and only then called `countDown()`.
- The worker waited on `await()`; once the latch opened, it read the mutated object. The *happens-before* relationship from the latch makes the outcome deterministic in this example.
- `result.get()` waits for task completion. Without the latch, whether the task reads before or after the caller's mutation depends on scheduling; never rely on `sleep` to guess the outcome.

**Contract fix:** create an immutable `PayloadSnapshot` before submitting, and pass the snapshot into the task; or transfer ownership to the task, with the caller committing never to mutate it again. If both sides must mutate, design an appropriate synchronization/queue mechanism. Never try to fix this by scattering `volatile` across every field.

### 8.2. `@Async` in Spring

Spring illustration with immutable input (requires Spring dependencies, `@EnableAsync` enabled, and calling the method **through a Spring proxy**):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record InspectCommand(String id, List<String> codes) {
    InspectCommand {
        codes = List.copyOf(codes);
    }
}

record InspectResult(String id, int codeCount) {}

@Service
public class InspectService {
    @Async
    public CompletableFuture<InspectResult> inspect(InspectCommand command) {
        InspectResult result =
                new InspectResult(command.id(), command.codes().size());
        return CompletableFuture.completedFuture(result);
    }
}
```

This is a **Spring integration pattern**, not a standalone `javac` program because it requires project files, packages, and Spring configuration. A public Java file would be named `InspectService.java`. `@Async` dispatches work to a Spring-managed executor when invoked through the appropriate interception mechanism; it **does not automatically copy parameters**. Self-invocation—calling `this.inspect(...)` within the same bean—normally bypasses the `@Async` proxy in default proxy mode. Depending on configuration, an explicit executor may be needed to bound resources.

In the example, `InspectCommand` snapshots the list at construction and its elements are immutable `String`s; data read by the task cannot be altered by the caller via the original list. The return value is also a fresh `InspectResult` containing only immutable values. Note that an `@Async` thread normally does not automatically inherit transactions or arbitrary thread-local contexts from the caller thread; propagate permitted context via explicit mechanisms rather than retaining an entire request object just to read one property later.

## 9. Buggy State Across Field and Return: Interleaving Between Two Requests

Consider a singleton bean with a `currentUser` field. Each request calls `begin(user)` then `finish()` to get its user back. Even if individual calls were protected with `synchronized`, **the business sequence** can still interleave without per-request state design.

Runnable example `CrossRequestLeakDemo.java` (Java 17+), using latches to create deterministic ordering without `sleep`:

```java
import java.util.concurrent.CountDownLatch;

public class CrossRequestLeakDemo {
    static final class SingletonLikeService {
        private String currentUser;

        void begin(String user) {
            currentUser = user;
        }

        String finish() {
            return currentUser;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SingletonLikeService bean = new SingletonLikeService();
        CountDownLatch firstBegun = new CountDownLatch(1);
        CountDownLatch secondBegun = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            bean.begin("Lan");
            firstBegun.countDown();
            try {
                secondBegun.await();
                System.out.println("Lan sees " + bean.finish());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread second = new Thread(() -> {
            try {
                firstBegun.await();
                bean.begin("Minh");
                secondBegun.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();
    }
}
```

```bash
javac CrossRequestLeakDemo.java
java CrossRequestLeakDemo
```

Result when threads are not interrupted externally:

```text
Lan sees Minh
```

`firstBegun` and `secondBegun` establish explicit ordering and visibility. The bug is that **state was stored in the wrong place**—a field of a shared instance—so Lan's request receives Minh's data. Simple fix: do not store `currentUser` in a singleton field; pass the user as an argument to the processing function and return that invocation's own result, or store per-request/transaction state with explicit identifiers and lifecycle.

Adding `synchronized` individually to `begin()` and `finish()` still leaves the design flaw between the two calls. Using locks requires enclosing **the entire invariant** in an appropriate critical section; however, an architecture that avoids keeping request state in singletons is usually far better.

## 10. Process for Tracing a Data Flow in a Real Project

For an endpoint or service call, start at the **suspected input value** and walk its *reference graph*, rather than starting by changing every bean's scope.

### Step 1 — Identify the Root Object and Ownership

Record: data type, creation site, which bean/request owns it, who is allowed to mutate it, and when its lifecycle ends. For instance, a `List<OrderItem> items` pulled from a cache differs from a list deserialized from a JSON request body specifically for a single request.

### Step 2 — Trace Paths Through Arguments

Follow method calls, including DTO fields and collection elements. If `serviceA(A)` calls `serviceB(A.getItems())`, that `List` itself may be shared even though `serviceB` did not receive the entire DTO. Flag setter calls, `clear`, `sort`, `removeIf`, `computeIfAbsent`, or operations on managed entities.

### Step 3 — Find Retention or Escape Points

Common places to check: assignments to `this.field`/`static`, caches, listeners, events carrying mutable payloads, callbacks/lambdas, future creation, queue insertion, or storing in request/session attributes. A method that looks like it merely "forwards data" can cause an object to outlive its caller.

### Step 4 — Trace Return Paths and Intermediate Mutations

Use a short tracking table:

| Milestone | Concrete object | Action | Who can mutate next? |
| --- | --- | --- | --- |
| Controller | `request.tags` | Builds list from input | Controller / methods receiving it |
| Service | `command.tags` | Points to the same list if uncopied | Service and caller |
| Executor | `capturedCommand` | Lambda captures reference | Worker; caller if alias remains |
| Bean field | `lastTags` | Retains reference | Any invocation seeing the field |
| Return | `result.tags` | Returns original list or a copy | Caller and any remaining owners |
| Safe boundary | `List.copyOf(tags)` of immutable elements | Snapshotted before async run | Caller only reads snapshot; original input managed by caller |

Fill in actual object names and mutation moments; never conclude solely from type names. For nested objects, keep tracing down to the mutable elements.

### Step 5 — Check Concurrency and Happens-Before

Determine which thread creates, mutates, and reads; whether they share an executor; whether a task can run after the caller method returns; and whether locks/atomics/queues/futures are used properly. You need both **execution ordering and mutation rights**. `Future.get()` lets you observe a completed result, yet does not prevent another thread from continuing to mutate a mutable result object afterwards.

### Step 6 — Observe with Tools

- Debugger: set breakpoints at constructors, field writes, async submission points, and returns; compare reference identity with `==` when holding two concrete variables.
- Logging/tracing: log explicit `traceId`/`requestId`, thread name, event type (created/copied/mutated/returned), and a diagnostic object tag; avoid logging sensitive payloads.
- `System.identityHashCode(object)` can aid identification in diagnostic logs, yet **is not guaranteed unique** and is not a stable object ID across runs.
- Thread dumps/JFR: useful when identifying threads waiting on/holding monitors or access timings; they do not by themselves reveal semantic DTO ownership.
- Tests: use `assertSame` to prove aliasing, `assertNotSame` to verify distinct object identity, and snapshot assertions; use latches to reproduce read/write timing.

Never use logs showing "identical contents" to conclude "identical object": two independent objects can still satisfy `equals`. Likewise, never use `System.identityHashCode` as a data key in production.

## 11. Design Strategies to Cut Unwanted Sharing Paths

**A. Stateless beans, immutable inputs and outputs.** Ideal for pure computation: caller passes an immutable command in; service builds a fresh result; never store `lastRequest`, `tempResult`, or `currentUser` in singleton fields.

**B. Explicit ownership transfer.** When performance requires mutable objects, stipulate that after submission the caller must not mutate or read the object concurrently until the task completes; enforce via API design and tests. Verbal promises without technical boundaries break easily.

**C. Defensive copying at boundaries.** Copy before a bean retains state or launches a callback, and copy when returning internal mutable structures. Choose shallow or deep copying according to element types. Never read a collection while another thread is mutating it without synchronization just because you plan to "copy it immediately."

**D. Intentional shared mutable state.** When sharing is required, pick suitable structures/primitives: `ConcurrentHashMap.compute` for atomic single-key updates, locks for multi-field invariants, atomic types for independent single values, queues for message passing. Never assume a thread-safe collection makes a multi-operation sequence atomic.

**E. Separate data context from thread context.** Pass trace IDs, tenant IDs, or needed permissions according to the method contract or supported propagation mechanisms. `@Async` switches threads; `ThreadLocal` in a worker does not automatically match the caller's values. Never pass an entire `HttpServletRequest` or request-scoped bean across async just to read one property later.

**F. Meaningful API returns.** Return IDs, immutable DTOs, immutable snapshots, or operation results; avoid returning raw mutable entities or cached objects if callers must not mutate internal state. Apply the same principle to event payloads and cache results.

A useful contract explicitly states: "Method does not mutate input; retains no input reference after returning; output shares no mutable state with repository caches." That is testable and far clearer than "service is thread-safe."

## 12. Testing Focused on Aliasing and Leaked State

Test in three layers, from simple to concurrent:

1. **Alias/identity tests:** caller builds a mutable object, invokes the service, then mutates both the original and returned objects; check which side changes. Assert `assertSame`/`assertNotSame` only when identity itself is part of the contract.
2. **Mutation isolation tests:** construct commands/results per the API, mutate the original source afterwards, and verify snapshots remain unchanged; for nested mutables, mutate elements as well.
3. **Concurrent scheduling tests:** have two calls share the bean, with the same or distinct objects; use `CountDownLatch` to enforce deterministic ordering, record reads/writes, and verify each request gets its own result. Set timeouts so tests never hang.
4. **Async completion tests:** verify input is snapshotted before submission, results after `Future.get()` are accurate, errors/timeouts/cancellations are handled, and the service retains no reference after completion.
5. **Load tests and observation:** for real caches/shared state, increase concurrency and measure races, queuing, latency, errors, and memory impact; stress tests complement but never replace thread-safety reasoning.

Example JUnit 5 assertions as a **fragment** (assuming `ImmutableBoundaryDemo` classes/constructors exist and JUnit 5 is imported):

```java
var source = new ArrayList<>(List.of("one"));
var command = new ImmutableBoundaryDemo.Command("id-1", source);

source.add("two");

assertEquals(List.of("one"), command.tags());
assertNotSame(source, command.tags());
assertThrows(UnsupportedOperationException.class,
        () -> command.tags().add("three"));
```

These assertions verify the snapshot contract of the outer collection; they do not prove all nested objects are immutable or that all concurrent calls are safe. Additional tests may be needed for each mutable type at deeper layers.

## 13. Common Mistakes and Accurate Explanations

| Misconception / bug | Why it is wrong | How to verify / fix |
| --- | --- | --- |
| "Parameters are local so they are always safe." | Local variables are private, yet the underlying object can be shared by multiple threads | Trace identity, nested references, and mutations |
| "Java passes objects by reference." | Java passes **a copy of the reference value**; reassigning the parameter variable does not change the caller's variable | Test both reassigning parameters and mutating objects |
| "`final` fields guarantee the object is immutable." | Only fixes the field reference; internal collections can still be mutated | Immutable elements + defensive copies |
| "`@Async` clones request DTOs before running." | It dispatches execution; it does not automatically deep-copy inputs | Snapshot/ownership before submission |
| "Returning `unmodifiableList` is a snapshot." | The wrapper can reflect changes to the backing list | Use `List.copyOf` or deep snapshots when needed |
| "`List.copyOf` copies all nested objects." | It only snapshots the outer structure | Copy mutable elements or use value objects |
| "A singleton bean with synchronized methods is enough." | Locking individual methods may fail to protect business sequences and leaked ownership | Protect the full invariant or remove per-request fields |
| "Prototype beans are always fresh per call." | Ordinary injection into a singleton resolves at injection time | Check actual bean retrieval/lifecycle |
| "`volatile` fixes every race." | Visibility differs from atomicity and multi-step invariants | Atomics, locks, immutable data, or message passing |
| "`Future.get()` makes the result object immutable." | It synchronizes completion/observation, without forbidding later mutations | Build immutable results, retain no mutable aliases |
| "Two objects satisfying `equals` are the same instance." | Value equality differs from `==` identity | Track distinct identities; avoid confusion in logs |

## 14. Integrated Practice: Tracing a Bug Across Three Spring Layers

Suppose a `@RestController` receives a product list; a `@Service` takes the list, saves it in a `lastItems` field, and computes a total; another service returns `lastItems` for debugging. Meanwhile, an `@Async` method also uses that list.

Perform the following steps:

1. Draw the object graph starting from the request body: DTO, list, each item, singleton field, async lambda, result. Distinguish **same reference**, **shallow copy**, and **deep copy** at every edge.
2. Identify two leaks: input retained in the singleton and the backing list returned outside. Explain why a caller can corrupt another request's data.
3. Write a stateless version: immutable DTO or defensive copy, processing with local variables, fresh result DTO; if auditing is required, append immutable events to a synchronized store and return only snapshots.
4. Write a test mutating the backing list after calling the constructor to verify the input snapshot; write a test mutating the result (if designed mutable) to verify internal state is unaffected.
5. Add an `@Async` task, mutating the original list after submission and before the task reads using a latch. Observe the original bug, then replace with an immutable snapshot to guarantee the outcome; never use `Thread.sleep` to fake timing.
6. Write an ownership table per object: owner, creation site, who mutates it, where it is returned, when its lifecycle ends, and whether synchronization exists. Explain why merely changing bean scope or adding `volatile` is insufficient.

### Completion Criteria

- [ ] Correctly explain Java pass-by-value and recognize two `==` references pointing to the same object.
- [ ] Trace a mutable object from caller → parameter → field/callback/async → return.
- [ ] Distinguish views, shallow snapshots, deep copies, and immutable results.
- [ ] Demonstrate that local variables are insufficient to conclude reachable state is thread-safe.
- [ ] Spot per-request state mistakenly retained inside a singleton bean.
- [ ] Know why `@Async` and `Future` do not automatically prevent caller and task from mutating the same DTO concurrently.
- [ ] Propose APIs with clear ownership, boundary copying, and deliberate context and concurrency handling.
- [ ] Use assertion-based tests coordinated with latches to reproduce bugs without guessing timing.

**Learning takeaway:** to judge whether a bean shares state safely, trace **objects and mutation rights across every argument, return value, and thread boundary**, rather than merely counting fields on the bean or looking at variable names. When ownership, lifetime, and mutation are made explicit, race conditions and cross-request data leaks become straightforward to explain, test, and prevent.
