# Avoiding this Escape When an Object Is Not Yet Fully Initialized in Java

**This escape** occurs when a reference to an object under construction is given to other code before initialization completes. Code that receives the reference can call methods or read fields while the object is still in an intermediate state.

This is a different bug from a constructor calling an overridden method: the two risks can occur together, but **calling an override early does not automatically prove that this has escaped**. This article focuses on callbacks, listeners, registries, threads/tasks, and ensuring safety when publishing objects across threads.

## 1. What Does Initialization Timing Mean?

When an object is allocated, instance fields initially have default values: references are null, numbers are 0, booleans are false. Then the chain of constructors and initializers runs according to Java rules. A final field also only receives its assigned value when the corresponding assignment executes.

~~~java
final class Settings {
    private final String endpoint;
    private int retryCount = 3;

    Settings(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Before the endpoint assignment line runs, that field still holds its default value of null. The constructor's responsibility is to validate data and bring the object into a valid state **before letting external code use it**.

## 2. Common Escape Paths

| Pattern in constructor | Why it needs checking |
| --- | --- |
| `registry.register(this)` | The registry may retain the reference or call the object immediately. |
| `eventBus.subscribe(this::onEvent)` | A method reference holds this as the receiver; the callback may run before fields are ready. |
| `eventBus.subscribe(e -> this.handle(e))` | A lambda can also close over this. |
| `new Thread(this::run).start()` | The new thread may read state while the constructor has not finished. |
| `executor.execute(this::run)` | The executor may execute immediately or hand off work to another thread. |
| Assigning this to a static variable or shared collection | External code can find the incomplete object. |
| Passing this to another dependency | The dependency may store the reference or trigger a callback. |

Not every occurrence of writing this in a constructor is an escape. `this.endpoint = endpoint`, or a private helper that only processes local fields without publishing the reference, are normal operations. Conversely, a lambda that does not write the word this can still retain the reference if it calls a method or reads an instance field.

## 3. Runnable Example: Callback Sees an Incomplete State

Save to **EscapeDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.Consumer;

public class EscapeDemo {
    static final class CallbackBus {
        private Consumer<String> listener;

        void subscribe(Consumer<String> callback) {
            listener = Objects.requireNonNull(callback);
            listener.accept("subscribed");
        }
    }

    static final class UnsafeObserver {
        private String label;

        UnsafeObserver(CallbackBus bus) {
            bus.subscribe(this::onMessage);
            label = "ready";
        }

        private void onMessage(String event) {
            System.out.println(
                    "unsafe: label=" + label + ", event=" + event);
        }
    }

    static final class SafeObserver {
        private final String label;

        private SafeObserver(String label) {
            this.label = Objects.requireNonNull(label);
        }

        static SafeObserver create(CallbackBus bus, String label) {
            Objects.requireNonNull(bus);
            SafeObserver ready = new SafeObserver(label);
            bus.subscribe(ready::onMessage);
            return ready;
        }

        private void onMessage(String event) {
            System.out.println(
                    "safe: label=" + label + ", event=" + event);
        }
    }

    static class Base {
        Base() {
            System.out.println("override: " + describe());
        }

        String describe() {
            return "base";
        }
    }

    static final class Derived extends Base {
        private final String detail;

        Derived() {
            detail = "ready";
        }

        @Override
        String describe() {
            return detail;
        }
    }

    public static void main(String[] args) {
        new UnsafeObserver(new CallbackBus());
        SafeObserver.create(new CallbackBus(), "ready");
        new Derived();
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 EscapeDemo.java
java EscapeDemo
~~~

Deterministic output:

~~~text
unsafe: label=null, event=subscribed
safe: label=ready, event=subscribed
override: null
~~~

- **unsafe:** the constructor registers a callback holding a reference to the object. CallbackBus calls the callback synchronously right inside subscribe, before label = "ready" runs, so the callback reads null.
- **safe:** the factory completes the SafeObserver constructor before registering the callback. A callback invoked immediately still sees that label is ready.
- **override:** Base() calls describe(), and Java dispatches to Derived.describe() before the detail field is assigned. This is the risk of calling an override in a constructor; this snippet does not show the reference being published to a registry or another thread, so it must be distinguished from this escape.

CallbackBus only simulates synchronous callbacks, not a multithreaded event bus. The output is deterministic because the listener is called immediately inside subscribe.

## 4. Difference Between this Escape and Early Override Calls

Calling an overridable method from a constructor can execute subclass logic while subclass fields still hold default values. This escape occurs when a reference is exposed outside the initialization process and other code can retain or use it. A single situation may include both, but you need to identify the actual path.

For example, `System.out.println(this)` or string concatenation with this can call an overridden toString(); this is a method call worth checking. To confirm an escape, check whether the object is given to a logger/formatter or external dependency that might retain or use it. The core fix is to avoid early polymorphic hooks and avoid publishing the reference before invariants are ready.

## 5. Do Not Start Threads or Tasks from a Constructor

The following snippet illustrates a dangerous design:

~~~java
final class UnsafeWorker {
    private String configuration;

    UnsafeWorker(java.util.concurrent.Executor executor) {
        executor.execute(() -> process(configuration));
        configuration = "loaded";
    }

    private void process(String value) {
        System.out.println("configuration=" + value);
    }
}
~~~

If the executor runs tasks synchronously, such as a direct executor, process is guaranteed to receive null. With a thread pool, the result also depends on execution scheduling and synchronization mechanisms; you must not rely on the assumption “the task will surely run after the constructor”. Do not use Thread.sleep to mask the problem, because waiting for a period of time does not create valid invariants or a proper happens-before relationship.

## 6. The Safe Approach: Finish Constructing Before Starting

Save the following program to **SafeThreadDemo.java**:

~~~java
import java.util.Objects;

public class SafeThreadDemo {
    static final class Worker {
        private final String configuration;

        private Worker(String configuration) {
            this.configuration =
                    Objects.requireNonNull(configuration, "configuration");
        }

        static Thread start(String configuration) {
            Worker ready = new Worker(configuration);
            Thread thread = new Thread(ready::runJob, "worker");
            thread.start();
            return thread;
        }

        private void runJob() {
            System.out.println("Worker config=" + configuration);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = Worker.start("loaded");
        worker.join();
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SafeThreadDemo.java
java SafeThreadDemo
~~~

Stdout:

~~~text
Worker config=loaded
~~~

The factory only calls Thread.start() after the Worker constructor completes. Under the Java Memory Model, actions of the creating thread prior to Thread.start() happen-before actions of the new thread. Thread.join() also helps main wait for the worker to finish. This guarantees that state assigned before start can be observed according to the contract of start; it does **not** automatically make subsequent mutable operations thread-safe.

The same pattern applies to listeners: finish constructing the object, and only then register the callback. If registration fails, define how to handle the error and clean up resources; if the listener retains a long-lived reference, provide a way to unregister when the object stops operating.

## 7. final Fields, Safe Publication, and Their Limits

Java provides special guarantees for final fields when an object is constructed properly and this does not escape during construction. However, these guarantees do not fix a callback reading a field before its assignment occurs, nor do they turn all mutable state into thread-safe state.

| Claim | Assessment |
| --- | --- |
| final String name always has its final value at every point in the constructor | False: before the assignment, an early call can still see the default value. |
| final makes publishing this from the constructor always safe | False: avoiding early escape remains an important condition. |
| final List&lt;String&gt; makes the list's contents immutable | False: final prevents reassigning the reference; it does not automatically prevent modifying the list. |
| volatile on a single field makes the whole object thread-safe | False: multi-field invariants and operations require appropriate synchronization design. |
| Finish construction and then publish via Thread.start(), a lock, or an appropriate synchronization mechanism | Provides a visibility relationship according to the contract of that mechanism. |

Safe publication is passing a fully initialized reference to other code via a mechanism that guarantees visibility, such as Thread.start(), a consistently used lock, a volatile reference, or an appropriate concurrent collection. After publishing, subsequent mutable accesses must still be synchronized if multiple threads use the object together.

## 8. Callbacks, Lambdas, and Object Lifecycle

The expressions `this::onMessage` and `event -> onMessage(event)` can capture the current object as the receiver. A lambda that uses only independent local variables does not necessarily capture this, but the dependency that the lambda calls may still have lifecycle or synchronization issues.

For objects that need to register listeners, open sockets, or start tasks, you can separate two phases:

~~~text
constructor
   ↓
assign fields and check invariants
   ↓
constructor completes
   ↓
register / start / publish
   ↓
active
   ↓
unregister / stop / close
~~~

A static factory can centralize this ordering so callers do not forget the startup step. Only use the start/stop model when an object genuinely has a lifecycle that needs managing; there is no need to force every data object into that model.

## 9. Review Checklist and Exercises

When reviewing a constructor, ask in order:

1. What state must be valid when the object is ready?
2. Is this, this::method, an instance lambda, a listener, or the object passed to a registry?
3. Can a dependency invoke the callback synchronously during registration?
4. Does any thread/task start before the constructor completes?
5. If multiple threads are involved, which mechanism provides happens-before and protects subsequent updates?
6. Can a test force the callback to run immediately to reproduce the bug deterministically?
7. Is unregistering or resource cleanup needed when the object stops?

**Scenario A.** A constructor registers `eventBus.register(this::onEvent)` before assigning handler, and the event bus invokes callbacks synchronously. Conclusion: the callback may read a null handler; move registration to after the constructor completes.

**Scenario B.** A superclass constructor calls toString(), which is overridden by a subclass. Conclusion: there is an early override call risk; to conclude this escape, check whether the reference is given to external code to retain or use.

**Scenario C.** A factory creates a Worker and only then calls Thread.start(). Conclusion: actions before start happen-before actions in the new thread; that does not replace synchronization for later changes.

**Takeaway:** the constructor prepares state; callbacks, listeners, registries, and threads/tasks should only receive the object after the entire constructor completes. With multiple threads, pair this with safe publication and proper synchronization for subsequent updates.
