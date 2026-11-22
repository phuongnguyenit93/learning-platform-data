# Risks of Letting `this` Escape Before Initialization Completes in Java

A Java object does not become “ready to use” at the moment memory is allocated. While executing a constructor, fields are being assigned values, superclasses and subclasses are initializing in sequence, and **object invariants** may not yet be fully established. If the **`this`** reference is passed to external code too early, that code may observe or call methods on a **partially initialized object**.

This phenomenon is commonly known as **`this` escape in the constructor** or **premature publication**. This is not just a multithreading issue: a listener invoked **right on the same thread** can also see unassigned fields. In a multithreaded environment, it also poses risks regarding *visibility*, *data races*, and breaking the initialization safety guarantees of `final` fields.

This lesson focuses on Java Core — class/object and the `this` keyword, presenting the mechanism, dangerous scenarios, fixes, and the limitations of each measure. Complete examples use **Java 17+**.

## 1. What Does `this` Escape Mean?

In a constructor or instance method, `this` refers to the **current object**. **Escape** occurs when the reference to the object being constructed becomes accessible outside the initialization process before that process finishes.

A common example:

~~~java
class Example {
    Example(EventBus bus) {
        bus.register(this); // Illustration: passing the object under construction to another object.
    }
}
~~~

This snippet is **illustrative code** and does not compile standalone because `EventBus` is not defined. The risk depends on what `register` does: it may **store** the reference in a shared list, immediately **call back** a method on the object, or allow another thread to access that object.

Some manifestations:

- Assigning `this` to a `static` field or a shared storage location directly in the constructor.
- Registering `this` as a **listener/observer** before initialization completes.
- Passing `this` to an API that can retain the reference or invoke a callback immediately.
- Starting a thread/task in the constructor, with a lambda or method reference **capturing `this`**.
- Calling an **overridable** method in the constructor; the subclass version may run before subclass fields are initialized. This is a risk related to *partial initialization*, even though that call does not necessarily publish the object externally.

**Simply writing `this` is not an escape.** The statement `this.name = name;` only assigns a field on the current object; it does not on its own pass the reference outside.

## 2. What State Is the Object in During a Constructor?

For an ordinary class, instance fields initially have **default values** such as `0`, `false`, and `null`. Java then proceeds with the superclass/subclass initialization chain, field initializers, instance initializers, and the constructor body according to language rules. During this process, an intermediate moment might show:

~~~text
Object under initialization
  id        = "ORD-01"   (assigned)
  owner     = null       (unassigned)
  quantity  = 0          (default, unchecked)
  ready     = false      (incomplete)
~~~

This is only a **hypothetical diagram**, not a standalone runnable object. If the contract requires `owner` to always be non-null and `quantity > 0` after successful creation, those conditions are not guaranteed to hold midway through the constructor.

Distinguishing three points in time:

| Point in Time | State |
| --- | --- |
| Immediately after memory allocation | Instance fields hold default values |
| During execution of the initialization chain | Some fields are assigned, others are unassigned; invariants may not hold yet |
| Constructor completes normally | The object must satisfy the invariants designed by the class author |

Java does not automatically check every business invariant. **The class must proactively check and establish them** before giving external code the ability to use the object.

## 3. Why Is `this` Escape Dangerous Even Without Threads?

Many people think bugs only occur when a constructor starts a thread. In reality, **whether synchronous or asynchronous, it does not fix calling a callback before field assignment**. Picture this:

~~~text
Constructor begins
  |
  +--> register listener: this::onEvent
  |
  +--> event emitter invokes listener IMMEDIATELY
  |      |
  |      +--> onEvent reads field while still null
  |
  +--> constructor only then assigns field = "READY"
  |
Constructor completes
~~~

There is no scheduling contention in the diagram above. The callback runs on the same call stack and reads state **before** the field is assigned. Even if `synchronized` is added to several methods, calling back too early on the same thread can still observe incomplete state; moreover, Java monitors are **reentrant**.

**Root cause:** `null` is not a Java bug. An unassigned field has its default value in accordance with the language; the design flaw is **allowing the object to be used when its contract does not yet hold**.

## 4. Runnable Example: Listener Reads a `null` Field Mid-Constructor

Create a file named **`ThisEscapeDemo.java`** as follows. The program uses only one thread, so the output can be predicted accurately.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class EventBus {
    private final List<Runnable> listeners = new ArrayList<>();

    synchronized void register(Runnable listener) {
        listeners.add(Objects.requireNonNull(listener));
    }

    void fireAll() {
        List<Runnable> snapshot;
        synchronized (this) {
            snapshot = List.copyOf(listeners);
        }
        for (Runnable listener : snapshot) {
            listener.run();
        }
    }
}

class EarlySubscriber {
    private String status;

    EarlySubscriber(EventBus bus) {
        bus.register(this::onEvent);
        bus.fireAll();          // Callback runs before status is assigned.
        this.status = "READY";
    }

    private void onEvent() {
        System.out.println("early=" + status);
    }
}

class SafeSubscriber {
    private final String status;

    private SafeSubscriber(String status) {
        this.status = Objects.requireNonNull(status);
    }

    static SafeSubscriber create(EventBus bus, String status) {
        Objects.requireNonNull(bus);
        SafeSubscriber result = new SafeSubscriber(status);
        bus.register(result::onEvent);
        return result;
    }

    private void onEvent() {
        System.out.println("safe=" + status);
    }

    String status() {
        return status;
    }
}

public class ThisEscapeDemo {
    public static void main(String[] args) {
        EventBus firstBus = new EventBus();
        new EarlySubscriber(firstBus);
        firstBus.fireAll();

        EventBus secondBus = new EventBus();
        SafeSubscriber ready = SafeSubscriber.create(secondBus, "READY");
        secondBus.fireAll();
        System.out.println("value=" + ready.status());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ThisEscapeDemo.java
java ThisEscapeDemo
~~~

**Exact stdout:**

~~~text
early=null
early=READY
safe=READY
value=READY
~~~

### Why Does `early=null` Appear?

1. `new EarlySubscriber(firstBus)` creates the object; the `status` field is initially `null`.
2. The constructor calls `bus.register(this::onEvent)`. The method reference **binds the current receiver**, namely the object under construction, and passes the callback to `EventBus`.
3. `bus.fireAll()` runs the callback **right inside the constructor**. `onEvent()` reads `status`, which is still `null` at this point, so it prints `early=null`.
4. The constructor proceeds to assign `this.status = "READY";`, and then finishes.
5. The `firstBus.fireAll()` call outside the constructor prints `early=READY`.

This is a bug that can be reproduced **with certainty** in the program, without relying on which thread runs first. `this::onEvent` does not display the word `this` inside a callback body, yet registering that method reference itself passed the object reference outside.

### Why Does `SafeSubscriber` Avoid This Bug?

The `SafeSubscriber(String)` constructor performs only internal work, completing the assignment of the `final status` field before returning. The `create(...)` factory executes in this order:

~~~text
new SafeSubscriber(status)
           |
           v
   constructor COMPLETES
           |
           v
   bus.register(result::onEvent)
           |
           v
        return result
~~~

Because registration happens only **after** the constructor completes, callbacks triggered by the bus will not encounter a partially constructed object along this design path.

`EventBus.register` and the listener snapshot section in `fireAll` use the **same monitor**, so there is also a proper *happens-before* path between registration and another thread taking a snapshot using that monitor. Copying the list and then running callbacks **outside** the `synchronized` block also avoids holding the lock while executing listener code. This example illustrates a simple registration mechanism, not a production event bus with unsubscription, backpressure, or callback error handling.

**Key takeaway:** changing the order to **initialize completely first, register afterward** is more important than merely adding the `final` or `synchronized` modifier while still registering too early.

## 5. Risks of Starting a Thread in a Constructor

Another common example is letting a task run before the object's fields have been set:

~~~java
class UnsafeWorker {
    private int expected;

    UnsafeWorker() {
        new Thread(() -> System.out.println(expected)).start();
        expected = 42;
    }
}
~~~

This is an **illustrative class**, with no `main` or guaranteed output. The lambda references `expected`, which is an instance field of `this`. It is passed to the new thread before the `expected = 42` statement executes.

**A single run may print `0` or `42`**, and you should not design around either outcome. The new thread may be scheduled before the assignment occurs. Even if the thread is scheduled later, without establishing proper synchronization relationships for shared accesses, the program can still encounter visibility issues under the Java Memory Model.

`Thread.start()` creates a *happens-before* relationship from **actions occurring before the `start()` call** to actions in the started thread. It **does not automatically guarantee** that assignments performed **after** the `start()` call are already visible to the new thread.

Therefore, the following code has an ordering error:

~~~java
new Thread(this::runTask).start();
this.expected = 42; // Too late to serve as a precondition for the task.
~~~

This is also an **illustrative snippet**, not complete code. The issue is not only with `new Thread`: passing a callback capturing `this` to `ExecutorService.submit`, `CompletableFuture.runAsync`, or a scheduler in a constructor carries similar risks if the task starts too early.

## 6. A Better Approach When an Object Needs to Run Its Own Task

Separate **state initialization** from **starting execution**. For example, the standalone file **`SafeWorkerDemo.java`**:

~~~java
import java.util.Objects;

final class Worker {
    private final String taskName;
    private final int expected;

    private Worker(String taskName, int expected) {
        this.taskName = Objects.requireNonNull(taskName);
        if (taskName.isBlank()) {
            throw new IllegalArgumentException("taskName rỗng");
        }
        if (expected < 0) {
            throw new IllegalArgumentException("expected âm");
        }
        this.expected = expected;
    }

    static Worker create(String taskName, int expected) {
        return new Worker(taskName, expected);
    }

    Thread startAsync() {
        Thread thread = new Thread(
                () -> System.out.println(taskName + "=" + expected));
        thread.start();
        return thread;
    }
}

public class SafeWorkerDemo {
    public static void main(String[] args) throws InterruptedException {
        Worker worker = Worker.create("job", 42);
        Thread running = worker.startAsync();
        running.join();
        System.out.println("done");
    }
}
~~~

Command to run:

~~~bash
javac -encoding UTF-8 SafeWorkerDemo.java
java SafeWorkerDemo
~~~

**Stdout:**

~~~text
job=42
done
~~~

Here:

- `Worker.create` completes the constructor before returning the instance.
- The caller executes `startAsync()` only **after having a valid object**.
- `taskName` and `expected` are assigned before `thread.start()`; the *happens-before* rule of `Thread.start()` allows the new thread to see the prior state.
- `join()` in `main` ensures the thread has finished before printing `done`, so the order of the two output lines is consistent.

**Limitations:** this example intentionally allows running only a single task. A real-world API must decide whether `startAsync()` can be called multiple times, who manages threads, task cancellation, errors, and resources. If a one-time start operation is desired, appropriate state management and synchronization mechanisms must be added; the “start after constructor” pattern by itself does not solve all concurrent lifecycle issues.

## 7. Common Ways `this` Is Published Too Early

| Situation in Constructor | Why Can It Escape? | Typically Better Approach |
| --- | --- | --- |
| `Global.current = this;` | Other code can read the shared field | Publish after initialization completes, using safe publication |
| `listeners.add(this);` | The listener registry retains the object and may invoke a callback | Register after the constructor, via a factory or an activate step |
| `eventBus.register(this::handle)` | The method reference captures the `this` receiver | Register after the object is complete |
| `executor.submit(() -> useField())` | The lambda implicitly captures `this` | Submit after initialization, once state is valid |
| `new Thread(this::run).start()` | Another thread can read the object immediately | Start in a separate method after initialization |
| `external.attach(this)` | The external API may store or call back the object | Examine the API contract, move attach outside the constructor |
| Registering a callback via an anonymous inner class | The inner class may hold a reference to the enclosing instance | Pass the callback outside only after the object completes |
| Constructor calls an overridable method | The subclass method reads uninitialized fields | Do not call overridable methods from a constructor |

**Do not assume** that every method receiving `this` necessarily stores it. If a method only immediately reads a few already-stabilized fields, the risk may differ. However, a constructor should not depend on non-publishing behavior of an external API when doing so could create an access path to an incomplete object.

### Escapes Do Not Necessarily Write `this` Explicitly

Forms that can **capture the receiver**:

~~~java
register(this::handle);
register(() -> handle());
executor.execute(() -> System.out.println(this.state));
~~~

These are **illustrative lines**, depending on appropriate definitions of `register`, `executor`, `handle`, and `state`. `handle()` inside the lambda is still ultimately an instance method call on the enclosing object. Therefore, searching solely for the character string `register(this)` in the code is not enough to detect every escape case.

## 8. Constructor Calling an Overridable Method: A Related Bug

Another hazard occurs **without sharing the object with another thread**: a superclass constructor calls an instance method that can be overridden by a subclass. Java still performs **dynamic dispatch** to the subclass implementation, even though subclass initialization has not finished running.

Create a standalone file **`OverridableConstructorDemo.java`**:

~~~java
class BaseView {
    BaseView() {
        show();
    }

    void show() {
        System.out.println("base");
    }
}

class ChildView extends BaseView {
    private String label = "READY";

    @Override
    void show() {
        System.out.println("child=" + label);
    }
}

public class OverridableConstructorDemo {
    public static void main(String[] args) {
        ChildView child = new ChildView();
        child.show();
    }
}
~~~

Compile/run:

~~~bash
javac OverridableConstructorDemo.java
java OverridableConstructorDemo
~~~

Stdout:

~~~text
child=null
child=READY
~~~

**Why?**

1. `new ChildView()` starts initialization, calling `BaseView()` as part of the constructor chain.
2. Inside the `BaseView()` constructor, the `show()` call is a **virtual call**. Because the actual object is `ChildView`, the `ChildView.show()` implementation runs.
3. At that point, the subclass field initializer `label = "READY"` **has not yet run**, so `label` currently has the default value `null`.
4. After the superclass constructor completes, the field initializer of `ChildView` assigns `"READY"`.
5. The `child.show()` call from `main` then prints `child=READY`.

This is a bug where **an object is used before initialization is complete**, not necessarily an “escape to an external object.” Yet it is similar in nature: executing code has relied on invariants of an incomplete part of the object.

**Good design practice:** a constructor should invoke only operations that are safe during initialization, avoiding calls to overridable methods. If helpers are needed, consider appropriate `private` or `static` helpers, or `final` methods whose responsibilities are confined to state that is guaranteed to be initialized. Avoid calling subclass methods that depend on subclass fields from a superclass constructor.

## 9. `final` Fields Do Not Automatically Solve `this` Escape

The Java Memory Model provides special guarantees for **`final` fields** when an object is **properly constructed** and its reference does not escape before the constructor completes.

Conceptual example:

~~~java
final class Config {
    private final int port;

    Config(int port) {
        this.port = port;
    }

    int port() {
        return port;
    }
}
~~~

This is an illustrative class definition without `main`. When an object is properly constructed, `final` semantics can help another thread observe values set in the constructor according to special rules, even in some cases where object publication is not synchronized through other mechanisms.

**However, if `this` escapes during the constructor**, that critical condition is broken: another thread may read a field before the assignment takes place, and one cannot rely on the proper-construction guarantee to assume all fields definitely hold their final values.

Do not overgeneralize and conclude that `final` solves all publication concerns:

- `final` does not make an otherwise mutable object thread-safe as a whole.
- A `final List<T>` prevents reassigning the **field reference**; it does not make a mutable list immutable on its own.
- **Non-final** fields still require attention to synchronization and visibility if shared across threads.
- A `final` field might be assigned at the end of a constructor, yet a callback **running before that assignment** still cannot expect to read that value.

**Safety principle:** prevent `this` from escaping before the constructor finishes **and** design an object publication path across threads that conforms to the Java Memory Model.

## 10. How Does Safe Publication Differ From Complete Initialization?

These are two related yet distinct concerns:

1. **Valid state before publication:** the object must be completely constructed, with necessary preconditions and invariants established.
2. **Safe publication path across threads:** when one thread passes a reference to another thread, proper visibility/happens-before relationships are needed so the receiving thread observes the written data.

Some mechanisms that typically establish an appropriate synchronization path include:

- Writing the reference to a `volatile` field and reading it back via the corresponding `volatile` mechanism.
- Registering/retrieving the reference properly under the same `synchronized` monitor.
- Using concurrent structures with suitable safety contracts such as `BlockingQueue`, or task execution mechanisms whose documentation specifies memory-consistency effects.
- Constructing the object completely and then having a new thread use it via `Thread.start()`, where actions before `start()` *happens-before* actions of that thread.
- Using static state safely initialized through the class initialization mechanism when appropriate.

None of the mechanisms in this list turns **a callback that ran too early** into correct behavior. If `onEvent()` is called right before `status = "READY"`, the callback still observes the pre-update state, regardless of locks or whether it runs on the same thread.

Comparison table:

| Initialization Complete Before Exposing Reference? | Inter-Thread Publication Properly Synchronized? | Assessment |
| --- | --- | --- |
| No | No | Risks both partial initialization and visibility issues |
| No | Yes | Can still observe an incomplete object |
| Yes | No | Avoids early callbacks, but is insufficient for all mutable data and multithreaded visibility |
| Yes | Yes | Stronger foundation; state changes **after** publication must still be synchronized if mutable state is shared |

The specific guarantees of `final` fields have special exceptions and details; this table serves as a system design guide and does not replace the strict rules in JLS §17.

## 11. Static Factory: Construct First, Register Afterward

A clear API pattern is **private constructor + static factory**:

~~~java
final class RegisteredService {
    private final String id;

    private RegisteredService(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id không hợp lệ");
        }
        this.id = id;
    }

    static RegisteredService create(Registry registry, String id) {
        RegisteredService service = new RegisteredService(id);
        registry.add(service);
        return service;
    }

    String id() {
        return id;
    }
}
~~~

This is an **illustrative snippet** and is not standalone because `Registry` is not defined. The main point: `new RegisteredService(id)` must **complete** before `registry.add(service)`.

A factory makes the execution order more centralized and easier to inspect than a constructor that registers `this` directly. However, to ensure **multithreaded** safety, `Registry` must enforce appropriate publication/visibility rules; moving registration into a factory while using an unsynchronized shared global `ArrayList` can still lead to data races.

### Why Not Simply Register at the End of the Constructor?

Example:

~~~java
Service(Registry registry) {
    this.id = "READY";
    registry.add(this);
}
~~~

Registering on the **last line** is usually better than registering before field assignments, yet it still happens **before the constructor completes** in the strict sense. If the registry calls back into the object synchronously, the callback executes inside the constructor; if a subclass still has fields to initialize, those may certainly still be incomplete. Therefore, for classes that can be subclassed or have complex lifecycle contracts, **do not treat “the last line of the constructor” as equivalent to “after initialization.”**

A factory or an activation step invoked by the caller after the `new` expression finishes provides a clearer lifecycle boundary.

## 12. Two-Phase Create–Start: Caller Responsibility

Another approach is to require external code to construct the object first and then explicitly activate it:

~~~java
Worker worker = new Worker(configuration);
worker.start();
~~~

This is a **call pattern**, not a standalone program. The constructor sets up the data. Only `start()` registers listeners, starts threads, or connects to external resources.

Advantages:

- Distinguishes between an object that is **constructed** and an object that is **active**.
- Allows the caller to configure and validate before any callbacks or background work occur.
- Easier to document and test the creation and startup phases separately.

Disadvantages:

- The caller may **forget to call `start()`** or call it multiple times.
- States such as `NEW`, `RUNNING`, `CLOSED`, along with out-of-order call behavior, must be defined.
- If multiple threads can call `start()`, state transitions and registration must be synchronized; checking an ordinary boolean flag is not safe enough on its own.

If construction and registration need to be combined into a single API for callers, an **internal factory that constructs first and registers afterward** can reduce missed-start bugs. There is no single best choice for every system; the essential requirement is **never letting other code observe the object while invariants are not yet guaranteed**.

## 13. Listener and Framework Scenarios

The risk of this escape is especially common in event-driven architectures:

~~~java
class Handler {
    private String token;

    Handler(EventSource source) {
        source.addListener(this::handle);
        token = loadToken();
    }

    private void handle() {
        useToken(token);
    }
}
~~~

This snippet is **illustrative only**, because `EventSource`, `loadToken`, and `useToken` are not defined. The constructor publishes the callback before `token` is set. The framework may invoke the listener immediately upon registration or from another thread, causing `handle()` to read `token == null`.

An even harder-to-spot variant:

~~~java
Handler(EventSource source) {
    source.addListener(event -> this.handle(event));
    configure();
}
~~~

The lambda still captures `this`; the longer syntax does not change the problem.

When integrating with a framework, you should ask:

1. Can `addListener` invoke the callback **immediately during registration**?
2. Does it store the callback for another thread to invoke?
3. Does it have a contract regarding **thread confinement** and memory visibility?
4. When tearing down the object, where must **unsubscribe** happen?
5. Can the callback run concurrently with `close()`?

Do not infer from the API name that `addListener` only stores the reference and will not invoke it immediately. The exact behavior depends on the framework's documentation or source code.

## 14. Can Escapes Be Avoided Simply by Using `private` or `synchronized`?

**No.** Each modifier has its own purpose:

| Measure | What Does It Help With? | Does It Fix this Escape on Its Own? |
| --- | --- | --- |
| `private field` | Prevents external code from accessing the field directly | No: a callback inside the class can still read the field early |
| `final field` | Restricts reassignment; has special visibility semantics when properly constructed | No: does not protect against callbacks running before assignment |
| `synchronized` | Supports mutual exclusion/visibility when the same monitor is used properly | No: a synchronous callback running too early still sees incomplete state |
| `volatile` | Establishes JMM visibility/ordering relationships for volatile accesses | No: does not turn an unassigned value into an assigned value |
| `Thread.sleep(...)` | Alters scheduling timing in an unguaranteed way | No; not a reliable synchronization mechanism |
| Factory constructs first, then registers | Avoids publishing the object before the constructor finishes | Directly helpful, but multithreaded publication must still be ensured |
| Not calling overridable methods in the constructor | Avoids premature dynamic dispatch to subclasses | Helpful for the risk of using uninitialized subclass fields |

Another design mistake is placing `synchronized` on a constructor: in Java, there is no syntax for declaring a **`synchronized` constructor** as there is for methods. Having a constructor enter a `synchronized` block on its own also does not solve every early-callback path.

## 15. Testing and Detecting this Escape

Some bugs can be tested **deterministically**, such as `ThisEscapeDemo`: the event bus invokes the callback before the constructor finishes assigning fields. For race bugs caused by starting a thread in a constructor, a single “passing” run does not prove the code is safe.

Useful checks:

- **Simulate immediate callbacks:** have a stub/mock registry invoke the listener immediately upon registration, then verify that the object never exhibits invalid state.
- **Simulate concurrent activation:** use `CountDownLatch` or `Phaser` to coordinate threads in tests; avoid relying on `Thread.sleep` to trigger races. If you want to demonstrate a specific race, design explicit synchronization checkpoints.
- **Re-check invariants after the factory returns:** once the factory returns, confirm that all required fields are valid.
- **Audit constructors:** look for `this` being assigned to a registry/static field, callback, thread, executor, or passed into an external API.
- **Audit overridable methods:** check for constructors calling `init()`, `notifyListeners()`, `toString()`, `hashCode()`, or other overridable instance methods that depend on subclass state.
- **Check JMM guarantees:** for objects passed between threads, identify the *happens-before* relationship and the mechanism protecting mutable state.

**Note:** timing-dependent buggy code can pass millions of test runs and still be wrong. Static analysis, code review, and clear lifecycle design are generally more important than merely trying to reproduce the bug through repeated runs.

### Example of Contract Testing Instead of Schedule Testing

For the factory `SafeSubscriber.create(bus, "READY")`, what needs to be verified is that the callback, even when triggered by the bus immediately after registration, **never observes unassigned state along the defined path**. For a constructor that registers a listener, a mock registry that triggers the callback during registration will catch the bug immediately.

You should also test **failure** behavior: if the constructor throws an exception, the registry must not retain a listener pointing to a partially initialized object. A factory makes it easy to uphold this rule because registration is performed only **after `new` completes normally**.

## 16. Step-by-Step Constructor Review Process

When evaluating a new constructor, follow these steps:

1. **List invariants:** which fields must be non-null, which numbers must be within valid bounds, and which resources must be ready?
2. **Identify completion timing:** have field initializers, superclass/subclass constructors, and the constructor body truly finished?
3. **Trace receiver publication paths:** `this`, method references `this::m`, lambdas capturing fields or calling instance methods, listeners, threads, and static registries.
4. **Check for synchronous callbacks:** can a called API immediately invoke a method back on the object?
5. **Check new threads:** does any task run before the final field assignments? Is an appropriate *happens-before* relationship in place?
6. **Avoid virtual calls in constructors:** especially in classes that can be subclassed and overridden.
7. **Separate activation from construction:** move registration/starting into a factory or a method called after the constructor.
8. **Ensure safe publication:** if the object is shared across multiple threads, use an appropriate synchronization mechanism during handoff.
9. **Maintain post-initialization protection:** proper publication does not replace synchronization for mutable fields that continue to be modified.
10. **Write adversarial tests:** immediate callbacks, boundary inputs, constructor exceptions, concurrent starts, and stop/start lifecycles.

In many cases, this process detects risks simply by **reading the line order**, before the program is even run.

## 17. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| “`this` only escapes when you write `register(this)`” | A lambda or `this::method` can also capture the receiver | Review callbacks, anonymous classes, and method references as well |
| “Running on a single thread is safe” | A synchronous callback can run mid-constructor | Do not publish the object before its state is ready |
| “Threads usually run slower than constructors” | There is no such guaranteed execution order | Start tasks after the constructor; apply JMM rules properly |
| “Assigning `final` fields is enough” | Fields may be read before assignment; escaping breaks the proper-construction condition | Prevent escapes and design safe publication |
| “`synchronized` will fix every bug” | Does not prevent early callbacks; monitors are reentrant | Adjust the lifecycle and publication order |
| “Registering on the last line of the constructor is completely safe” | The object has not exited the constructor yet; subclasses may not be initialized | Register after `new` succeeds |
| “A superclass constructor can freely call overridable methods” | The subclass override runs while subclass fields still hold default values | Do not call overridable methods in constructors |
| “Not reproducing a race means there is no race” | Nondeterministic scheduling and visibility can mask bugs | Perform code review, coordinated tests, and verify happens-before |
| “A static factory makes everything thread-safe on its own” | An unsynchronized shared registry still has data races | Combine a factory with an appropriate publication mechanism |
| “An object with `private` fields cannot be observed prematurely” | The object's own public callback can read and expose the values | Do not pass the receiver outside too early |

## 18. Practice Exercises

**Exercise 1.** In the `Listener(EventBus bus)` constructor, the code calls `bus.register(this::onEvent)` before assigning `token = "OK"`. If the bus invokes the callback immediately, what value can `onEvent` see? Why?

**Exercise 2.** Is the statement `this.name = name;` in a constructor a this escape? What about `registry.put(id, this)`?

**Exercise 3.** Why does `new Thread(() -> System.out.println(value)).start(); value = 42;` in a constructor not guarantee that the new thread prints 42?

**Exercise 4.** A factory creates `new Service(settings)` and then calls `registry.add(service)`. What risk does this mitigate? When the registry is used across multiple threads, what else must be considered?

**Exercise 5.** A superclass constructor calls `render()`, and a subclass overrides `render()` and reads the field initializer `String label = "READY"`. Why can `null` be observed?

**Exercise 6.** For a class with multiple `final` fields, can complete safety be inferred if the constructor exposed `this` to another thread from the start? Explain.

**Exercise 7.** Given an event bus that can invoke listeners immediately inside `register`, propose a design so that the listener is registered once the object is complete while the caller still calls only a single object-creation API.

**Exercise 8.** If the constructor has already completed, yet two threads update the same `ArrayList` inside the object without synchronization, does avoiding this escape solve the bug on its own?

### Reference Answers

1. It can read `null` because the field has not been assigned yet, even though the callback runs on the same thread as the constructor; this is an **initialization order** bug.
2. `this.name = name;` only assigns a field and does not publish the receiver. Putting `this` into a registry can make the object accessible from outside, so it is an escape risk.
3. `Thread.start()` does not guarantee that an assignment **after** the start call happens before the new thread's operation; additionally, proper visibility may be missing.
4. Registration occurs after the constructor, avoiding publishing a partially initialized object; the registry requires appropriate **safe publication/synchronization** when threads share it.
5. Dynamic dispatch selects the subclass override while the superclass constructor is running, before the subclass field initializer executes; the field still holds the default value `null`.
6. No. The special guarantees of `final` rely on proper construction; premature publication breaks the precondition required to rely on those guarantees.
7. Use a **private constructor + static factory**: construct and validate the object first, then register the callback, then return the instance; ensure the registry uses appropriate synchronization.
8. No. Avoiding escapes only solves premature publication bugs; mutable state still requires its own concurrency design.

## 19. References

- [Java Language Specification 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object creation order and initialization semantics.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): semantics of the `this` expression.
- [Java Language Specification 17, §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): the happens-before relationship in the Java Memory Model.
- [Java Language Specification 17, §17.5 — `final` Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): special guarantees for final fields and proper construction conditions.
- [Oracle Java SE 17 API — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, and thread lifecycle.

**Remember:** `this` escape is dangerous when **an object under initialization is published to other code**, especially via listeners, callbacks, threads, or registries. The most important prevention is to **complete the constructor and establish invariants before registering or starting activity**, avoid calling overridable methods in constructors, and ensure *safe publication* if multiple threads use the object. `final`, `volatile`, or `synchronized` cannot substitute for proper lifecycle ordering.
