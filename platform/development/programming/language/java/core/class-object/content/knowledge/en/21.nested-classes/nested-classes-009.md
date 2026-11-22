# Implicit Reference to the Enclosing Object and Memory Retention Risks in Java

## Learning Objectives

After this lesson, you will be able to:

- Explain the **enclosing instance** of a non-static member inner class and how `outer.new Inner()` associates an Inner object with a specific Outer object.
- Distinguish **inner class**, **static nested class**, anonymous/local class, and lambda regarding the need for outer references/captured state.
- Understand **reachability** in Java GC: an object can only be collected when it is no longer reachable from GC roots according to JVM rules; a long-lived listener/callback/task can keep the outer object alive longer than expected.
- Read a reference path diagram: `GC root → registry → callback/inner → enclosing Outer → fields/payload` and identify **who is holding the reference**, not just where `new` was written.
- Know when `Outer.this` or accessing an Outer instance field actually requires retaining an outer reference; avoid confusing this with accessing static fields.
- Understand version-specific details: JDK 17 `javac` may generate a synthetic `this$0` field, whereas starting in JDK 18 the compiler has an optimization to omit this field when the inner class **does not use** the enclosing instance; bytecode layout is not an API guarantee.
- Distinguish an **application-level memory leak** from a malfunctioning GC: when objects remain reachable, GC keeping them is the correct behavior, even though the application no longer wants to use them.
- Design listener lifecycles with `register`/`unregister`, `AutoCloseable` subscriptions, task cancellation/queue cleanup, cache bounds, and listener ownership.
- Use a **static nested class**/top-level class with an immutable snapshot of the required data to reduce the chance of extending Outer's lifetime; understand that a static nested class can still retain Outer if you explicitly declare an Outer field.
- Discuss `WeakReference`/weak listeners/`WeakHashMap` within their proper limits, without assuming GC behavior from `System.gc()` or predicting when an object will be collected.
- Verify retention risks using deterministic behavioral tests and heap snapshots/dominator/reference chains; do not simulate GC results that are not guaranteed by the JVM.
- Write and run standalone Java 17+ examples with deterministic stdout results.

## 1. What Is an Enclosing Instance?

Two common declarations inside an enclosing class:

~~~java
class Outer {
    static class Nested {
    }

    class Inner {
    }
}
~~~

- `Nested` is a **static nested member class**: a Nested object has no implicit enclosing Outer instance.
- `Inner` is a **non-static member inner class**: creating an Inner from an Outer instance associates Inner with an **immediately enclosing instance** according to Java language semantics.

From outside Outer:

~~~java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

`Outer.Inner` is the **type name**. `outer.new Inner()` is a **qualified instance creation expression**. The qualifier `outer` provides the enclosing instance, rather than an explicit constructor argument that you declare in Inner's parameter list.

### 1.1. What Is That Link Useful For?

Inside an Inner method, `this` refers to Inner itself; `Outer.this` refers to the Outer instance associated with Inner:

~~~java
class Outer {
    private final String id = "A";

    class Inner {
        String ownerId() {
            return Outer.this.id;
        }
    }
}
~~~

Inner can read the private outer field `id` according to Java nested-class access rules. If the outer state is mutable, Inner can observe the new state rather than receiving a default copy of the Outer field.

### 1.2. An Inner Is Distinct from an Outer

One Outer can create multiple Inner objects. Two Outer objects can create Inner objects of the **same `Outer.Inner` type** that are associated with two different enclosing instances. Outer is not automatically cloned each time an Inner is created.

~~~text
Inner A --------------------+
                            |
                            v
                         Outer 1
                            ^
                            |
Inner B --------------------+

Inner C --------------------> Outer 2
~~~

When designing memory ownership, look closely at which Outer an Inner points to and who is pointing to the Inner.

## 2. Program: Verifying the Enclosing Instance Through Behavior

Save **`EnclosingLinkDemo.java`**:

~~~java
public class EnclosingLinkDemo {
    static final class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        class Inner {
            String ownerId() {
                return Outer.this.id;
            }

            boolean belongsTo(Outer candidate) {
                return Outer.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        Outer.Inner a = first.new Inner();
        Outer.Inner b = second.new Inner();

        System.out.println("a owner=" + a.ownerId());
        System.out.println("b owner=" + b.ownerId());
        System.out.println("a with first=" + a.belongsTo(first));
        System.out.println("a with second=" + a.belongsTo(second));
        System.out.println("b with second=" + b.belongsTo(second));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac EnclosingLinkDemo.java
java EnclosingLinkDemo
~~~

**Stdout:**

~~~text
a owner=A
b owner=B
a with first=true
a with second=false
b with second=true
~~~

This is a **semantic** verification rather than guessing a synthetic field name in bytecode. `Outer.this == candidate` compares the **reference identity** of the enclosing Outer instance.

An outer variable on the caller side can be reassigned to a different reference after Inner has been created; the old Inner remains associated with the Outer object **used when it was created**.

## 3. Java GC Relies on Reachability, Not on “Whether a Variable Still Has a Name”

The garbage collector does not decide which objects have “lost business value”. It finds objects that are still reachable from **GC roots** (such as live thread stacks, static roots, and JVM runtime references, depending on the root type/implementation) according to a given collection model.

For example:

~~~text
GC root
   |
   v
static listener registry
   |
   v
inner listener object
   |
   v
enclosing Outer object
   |
   v
large byte[] / tree / cache / other fields
~~~

If a **strong reference path** still exists, outer may not be collected, and the objects referenced by outer may also be kept alive along with it.

### 3.1. The Application Concept of a “Memory Leak”

In Java, an **application-level memory leak** is typically a situation where an object is no longer needed by business logic but remains **reachable** because a collection, listener, static cache, pending task, or another owner still holds a reference to it.

The GC is not “wrong” to keep that object: from the reference graph's perspective, it is still reachable.

### 3.2. Reference Paths Matter More Than Reference Cycles

If:

~~~text
Outer -> Inner -> Outer
~~~

but **there is no longer any path from GC roots to either of them**, a standard garbage collector can still collect the entire cycle. Java GC is not pure reference counting where every cycle automatically leaks.

The concerning path is:

~~~text
static registry (root) -> Inner -> Outer
~~~

In that case, **there is a root outside the cycle**, and cleaning up the registry may be a necessary step to break the reference path.

### 3.3. You Cannot Prove GC Behavior with a Short Run

`System.gc()` is only a request/hint to the JVM. You must not infer that “once called, the object has definitely been collected”; collection timing, the collector, and JVM optimizations are factors outside the deterministic output of a Java example.

The programs in this lesson will **verify reference paths, the number of callbacks still registered, and behavior**, rather than printing unreliable “GC has run” conclusions.

## 4. An Inner Listener Can Extend Outer's Lifetime

A typical scenario:

1. A screen/view/controller Outer creates an inner listener.
2. The listener is registered with an EventBus that outlives the screen.
3. The user closes the screen, and the code no longer holds a local Outer variable.
4. EventBus still holds a strong reference to the listener.
5. The listener uses `Outer.this`/instance state, so the reference path to Outer still exists.
6. Outer and the fields it holds may live longer than intended.

This happens **without needing any thread or GC bug**.

### 4.1. Demo of a Registry Keeping Outer Reachable

Save **`ListenerRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerRetentionDemo {
    static final class EventBus {
        private final List<Runnable> callbacks = new ArrayList<>();

        void add(Runnable callback) {
            callbacks.add(callback);
        }

        void remove(Runnable callback) {
            callbacks.remove(callback);
        }

        int size() {
            return callbacks.size();
        }

        void fire() {
            for (Runnable callback : callbacks) {
                callback.run();
            }
        }
    }

    static final class Screen {
        private final String name;
        private final byte[] data = new byte[1024];

        Screen(String name) {
            this.name = name;
        }

        class ClickHandler implements Runnable {
            @Override
            public void run() {
                System.out.println("click " + Screen.this.name
                        + ",bytes=" + Screen.this.data.length);
            }
        }

        ClickHandler attach(EventBus bus) {
            ClickHandler listener = new ClickHandler();
            bus.add(listener);
            return listener;
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        Screen screen = new Screen("Home");
        Runnable registered = screen.attach(bus);

        screen = null; // Only drops the local reference.
        System.out.println("registered=" + bus.size());
        bus.fire();

        bus.remove(registered);
        registered = null;
        System.out.println("after remove=" + bus.size());
    }
}
~~~

Run:

~~~bash
javac ListenerRetentionDemo.java
java ListenerRetentionDemo
~~~

Stdout:

~~~text
registered=1
click Home,bytes=1024
after remove=0
~~~

**Analysis:**

- `screen = null` only drops **one** local reference; it does not force Screen to be collected.
- `bus` still holds the listener, and the listener must access `Screen.this.name` and `Screen.this.data`, so Screen can still be reached through this path.
- `bus.fire()` proves the callback is still active after dropping the local screen reference; there is no need to trigger GC.
- `bus.remove(registered)` removes the callback from the bus in this example. Afterward, all other reference paths must still be considered: you must not claim that Screen is **definitely** garbage-collected immediately.
- `data` is just a small illustrative payload. If screen holds a large graph, a single listener can keep that entire graph reachable.

**Takeaway:** An inner listener is not a copy containing only the String name; it may need a link to the Screen object itself.

## 5. Why Is Storing an Inner in a “Long-Lived” Location More Dangerous?

`Inner` does not automatically cause a leak. The same logic can be used safely when the callback's lifetime is **shorter than or equal to** the required lifetime of Outer.

The risk increases when Inner is stored in:

- A static `List`/`Map`/registry that is not cleaned up.
- An EventBus singleton.
- Scheduled tasks, timer callbacks, or executor queues.
- Long-lived Swing/JavaFX/web listener registries.
- Observer/callback lists managed by a long-lived service.
- A global cache, retained diagnostics hooks, or debug registries.
- Reactive subscriptions that are not disposed.
- Thread-local data of a long-lived thread, if it contains an inner/owner reference.

Do not just ask “In which method was Inner created?”. Ask **where a reference to Inner is still being held, and for how long**.

## 6. Program: A Static Field Registry as a GC Root Path

Save **`StaticRegistryPathDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticRegistryPathDemo {
    private static final List<Runnable> TASKS = new ArrayList<>();

    static final class Owner {
        private final String id;

        Owner(String id) {
            this.id = id;
        }

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("task for " + Owner.this.id);
            }
        }

        void register() {
            TASKS.add(new Task());
        }
    }

    public static void main(String[] args) {
        Owner owner = new Owner("A");
        owner.register();
        owner = null;

        System.out.println("queued=" + TASKS.size());
        TASKS.get(0).run();

        TASKS.clear();
        System.out.println("after clear=" + TASKS.size());
    }
}
~~~

Run:

~~~bash
javac StaticRegistryPathDemo.java
java StaticRegistryPathDemo
~~~

Output:

~~~text
queued=1
task for A
after clear=0
~~~

Notable path:

~~~text
StaticRegistryPathDemo.TASKS
            |
            v
         Owner.Task
            |
            v
         Owner("A")
~~~

`TASKS.clear()` breaks **the path from this list** to Task. If another place still holds Task or Owner, the objects remain reachable. Therefore, the program does **not** print “owner collected”.

### 6.1. Relation Between Class Unloading and Static Fields

Saying overly simplistically that “a static field always lives forever” is also inaccurate: classloaders/classes have their own lifecycles. However, in an application where the class and registry remain long-lived, a static collection is often a significant source of retention.

## 7. Reducing Coupling: A Static Nested Class with Required Data

If a callback only needs an immutable ID or a few small pieces of information, you can create a **static nested listener** instead of a non-static Inner.

~~~java
class Screen {
    private final String id;

    static class Callback implements Runnable {
        private final String idSnapshot;

        Callback(String idSnapshot) {
            this.idSnapshot = idSnapshot;
        }

        @Override
        public void run() {
            System.out.println(idSnapshot);
        }
    }
}
~~~

`Callback` does not automatically have `Screen.this`. If the constructor takes only an immutable String, the callback stores the ID snapshot without needing to retain Screen.

**However:** a static nested class **can still retain Screen** if you declare `private final Screen owner;` yourself or have another closure/field holding owner. The static keyword only eliminates the **automatic enclosing instance**; it is not an “absolute anti-leak tool”.

## 8. Program: A Static Nested Callback That Does Not Need an Outer Object

Save **`StaticNestedCallbackDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticNestedCallbackDemo {
    static final class Registry {
        private final List<Runnable> actions = new ArrayList<>();

        void register(Runnable action) {
            actions.add(action);
        }

        void fire() {
            for (Runnable action : actions) {
                action.run();
            }
        }
    }

    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        static final class Callback implements Runnable {
            private final String id;

            Callback(String id) {
                this.id = id;
            }

            @Override
            public void run() {
                System.out.println("screen id=" + id);
            }
        }

        Runnable createCallback() {
            return new Callback(id);
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        Screen screen = new Screen("Home");

        registry.register(screen.createCallback());
        screen = null;

        registry.fire();
    }
}
~~~

Run:

~~~bash
javac StaticNestedCallbackDemo.java
java StaticNestedCallbackDemo
~~~

Output:

~~~text
screen id=Home
~~~

Callback has only one `String id` field to carry out its behavior, does not contain an explicit Screen field, and has no implicit `Screen.this` according to static nested class semantics.

**Do not draw conclusions about GC timing:** the result only proves that the callback **does not need the Screen instance** to run. Actual memory retention must be evaluated by examining all reference paths.

### 8.1. When Is Retaining an Explicit Outer Reference Still Reasonable?

If the callback needs to manipulate Screen's live state, passing/retaining Screen explicitly may be appropriate. In that case, **limit the lifetime** and provide an unregister/dispose mechanism. A static nested class cannot replace a domain relationship if the callback genuinely needs a live owner.

## 9. Replacing Inner with a Static Nested Class Is Not Enough When a Field Still Holds Owner

An incomplete fix:

~~~java
class Screen {
    static class Callback implements Runnable {
        private final Screen owner;

        Callback(Screen owner) {
            this.owner = owner;
        }

        @Override
        public void run() {
            owner.refresh();
        }
    }

    void refresh() {
    }
}
~~~

This is an illustrative snippet that can compile if placed in an appropriate complete file. Because Callback holds a strong reference to `owner`, a registry retaining Callback can still extend Screen's lifetime.

Distinguish the two paths:

~~~text
Inner handler:  registry -> inner -> enclosing Screen
Nested handler: registry -> nested -> explicit owner Screen
~~~

**Choose a static nested class because the helper does not need the outer instance**; if it does need the outer instance, solve the issue primarily through **lifecycle/registration ownership**, not merely by changing a modifier.

## 10. Foundational Solution: Symmetric Register and Unregister

A listener API needs rules:

1. Register at the moment the component begins needing events.
2. Keep the exact **same listener instance** or a registration token in order to unregister.
3. Unregister when the component stops needing events (close/dispose/unmount/stop).
4. If events can run concurrently, identify any race between remove and an executing callback.
5. Test that the registry no longer holds the subscription after cleanup.
6. Do not assume `remove(new Listener())` removes the old listener if equality/identity does not match.

Many frameworks provide a `Subscription`, `Disposable`, `Registration`, or `AutoCloseable` token. These make ownership clearer than placing a raw callback directly into a static list without keeping a way to remove it.

### 10.1. Why Does Callback Identity Matter?

If the registry stores `Runnable listener = owner.new Handler();`, you should keep that reference until unsubscribing. Calling `owner.new Handler()` again creates a different instance; it is **not automatically equal** to the original callback under `Object.equals`, so it typically fails to remove the original entry.

An explicit registration token reduces this risk.

## 11. Program: Registering with an `AutoCloseable` Subscription

Save **`SubscriptionLifecycleDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class SubscriptionLifecycleDemo {
    static final class Bus {
        private final Map<Integer, Runnable> listeners =
                new LinkedHashMap<>();
        private int nextId;

        Subscription subscribe(Runnable listener) {
            int id = ++nextId;
            listeners.put(id, listener);
            return new Subscription(this, id);
        }

        private void remove(int id) {
            listeners.remove(id);
        }

        int size() {
            return listeners.size();
        }

        void fire() {
            for (Runnable listener : listeners.values()) {
                listener.run();
            }
        }
    }

    static final class Subscription implements AutoCloseable {
        private final Bus bus;
        private final int id;
        private boolean closed;

        Subscription(Bus bus, int id) {
            this.bus = bus;
            this.id = id;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                bus.remove(id);
            }
        }
    }

    static final class View {
        private final String name;

        View(String name) {
            this.name = name;
        }

        class Listener implements Runnable {
            @Override
            public void run() {
                System.out.println("event for " + View.this.name);
            }
        }

        Subscription attach(Bus bus) {
            return bus.subscribe(new Listener());
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        View view = new View("Settings");

        try (Subscription ignored = view.attach(bus)) {
            System.out.println("inside size=" + bus.size());
            bus.fire();
        }

        System.out.println("outside size=" + bus.size());
        bus.fire();
    }
}
~~~

Run:

~~~bash
javac SubscriptionLifecycleDemo.java
java SubscriptionLifecycleDemo
~~~

Output:

~~~text
inside size=1
event for Settings
outside size=0
~~~

**Analysis:**

- Bus holds the listener in the map, and the listener accesses `View.this.name`, so View lies on the reference path.
- `try-with-resources` calls `close()` when exiting the block; close removes the exact subscription ID without needing to create a new listener.
- After `close`, `bus.size()` is 0; `bus.fire()` no longer invokes the listener.
- `close()` is idempotent in this example: repeated calls cause no new side effects.
- This is a **single-threaded** example. In production, Bus may need to synchronize register/remove/fire, handle currently running callbacks, and ensure exception safety.

**Practical note:** sometimes a component's lifetime does not match the lexical scope of `try-with-resources`. You can store `Subscription` in a field and call `close` in `dispose()/onStop()` according to the framework lifecycle.

## 12. An Anonymous Inner Class Can Also Retain Outer

An anonymous class created inside an instance method can use members of the enclosing object. For example:

~~~java
class Screen {
    private final String id = "A";

    Runnable create() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Screen.this.id);
            }
        };
    }
}
~~~

The callback here accesses `Screen.this.id`, so it has a semantic reference relationship to Screen. If the callback is placed into a long-lived registry without unregistering, Screen can remain reachable.

You should not claim that **every anonymous class in every context retains Outer**. An anonymous class in a static context has no enclosing instance of the calling class, and compiler implementations may also optimize away unused references.

### 12.1. Local Classes Behave Similarly When Accessing Outer

~~~java
class Screen {
    private final String name = "Home";

    Runnable createLocal() {
        class LocalHandler implements Runnable {
            public void run() {
                System.out.println(Screen.this.name);
            }
        }
        return new LocalHandler();
    }
}
~~~

A local class is not a member type created with `outer.new LocalHandler()` from outside the method. However, it can still capture the enclosing context/local values according to Java rules, leading to retention if the object is kept alive for a long time.

### 12.2. Retaining Local Variables via Closure

Local/anonymous classes can only use local variables that satisfy **final/effectively final** constraints. If a captured local reference points to a mutable, large object graph, the callback holding that reference can keep the graph reachable, even without needing Outer.

## 13. Program: Member Inner, Anonymous, and Local Classes

Save **`InnerVariantsCaptureDemo.java`**:

~~~java
public class InnerVariantsCaptureDemo {
    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        class MemberHandler implements Runnable {
            @Override
            public void run() {
                System.out.println("member " + Screen.this.id);
            }
        }

        Runnable anonymous() {
            return new Runnable() {
                @Override
                public void run() {
                    System.out.println("anonymous "
                            + Screen.this.id);
                }
            };
        }

        Runnable local() {
            class LocalHandler implements Runnable {
                @Override
                public void run() {
                    System.out.println("local " + Screen.this.id);
                }
            }
            return new LocalHandler();
        }
    }

    public static void main(String[] args) {
        Screen owner = new Screen("A");

        Runnable member = owner.new MemberHandler();
        Runnable anonymous = owner.anonymous();
        Runnable local = owner.local();

        member.run();
        anonymous.run();
        local.run();
    }
}
~~~

Run:

~~~bash
javac InnerVariantsCaptureDemo.java
java InnerVariantsCaptureDemo
~~~

Output:

~~~text
member A
anonymous A
local A
~~~

All three callbacks **actually read** `Screen.this.id`; if a long-lived object retains the callbacks, Screen can be part of the retained reference graph. This example does not rely on what compiler-generated field names the inner classes happen to have.

## 14. Does a Lambda Have an “Implicit Outer Reference” Like a Member Inner Class?

A lambda `() -> ...` does not create a *named member inner class* with an enclosing instance using the `outer.new Inner()` syntax. However, a lambda **can capture `this`** or another reference if its body uses instance state.

For example:

~~~java
class Screen {
    private String status = "open";

    Runnable capturingOwner() {
        return () -> System.out.println(status);
    }
}
~~~

The lambda needs to read `status` from the Screen instance, so a retained lambda can hold a path to Screen.

By contrast:

~~~java
Runnable withSnapshot() {
    String snapshot = status;
    return () -> System.out.println(snapshot);
}
~~~

The second lambda only needs the captured String snapshot. If the String is immutable and there is no other captured Screen reference, the callback can run without needing the Screen object. The exact closure representation is a compiler/runtime detail; reason from **the references the body needs to use**, not from synthetic field names.

### 14.1. Lambda `this` Differs from Anonymous Class `this`

- Inside a lambda written in a Screen instance context, `this` lexically refers to **Screen**.
- Inside an anonymous class `new Runnable() { ... }`, `this` refers to the **anonymous Runnable object**; to refer to Screen, use `Screen.this`.

This is a semantic difference, not an anti-memory-leak trick. Both can retain the owner if they use the owner.

## 15. Program: A Lambda Capturing Owner vs. a Lambda Capturing a Value

Save **`LambdaCaptureRetentionDemo.java`**:

~~~java
public class LambdaCaptureRetentionDemo {
    static final class Screen {
        private String title;

        Screen(String title) {
            this.title = title;
        }

        Runnable live() {
            return () -> System.out.println("live=" + title);
        }

        Runnable snapshot() {
            String captured = title;
            return () -> System.out.println("snapshot=" + captured);
        }

        void rename(String next) {
            title = next;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen("Before");

        Runnable live = screen.live();
        Runnable snapshot = screen.snapshot();

        screen.rename("After");

        live.run();
        snapshot.run();
    }
}
~~~

Run:

~~~bash
javac LambdaCaptureRetentionDemo.java
java LambdaCaptureRetentionDemo
~~~

Output:

~~~text
live=After
snapshot=Before
~~~

**Explanation:**

- `live` reads the instance field through the live Screen: therefore it sees After.
- `snapshot` captures a String value/reference corresponding to the time the callback was created and sees Before.
- Both can be stored as `Runnable`; choosing between live state and snapshot state strongly affects retention/lifecycle.
- Do not capture a mutable object into a local variable and call that an immutable snapshot: the reference to the mutable object is still shared.

### 15.1. Case Where the Callback Only Uses Static Members

A lambda/method that uses only static data may not need to retain the owner; do not conclude from the fact that a lambda is created **inside an instance method** that it definitely captures `this`. Look at which objects the code actually references.

## 16. A Method Reference Can Also Capture a Receiver

The expression `this::onEvent` creates a callback bound to the current `this` receiver. A registry retaining the callback can keep the receiver reachable. Similarly, `someObject::method` retains the receiver object needed to invoke the method.

By contrast, a static method reference `Logger::log` does not need a receiver instance, although it may need data arguments.

### 16.1. Runnable Program

Save **`MethodReferenceRetentionDemo.java`**:

~~~java
public class MethodReferenceRetentionDemo {
    static final class Screen {
        private final String id;

        Screen(String id) {
            this.id = id;
        }

        void onEvent() {
            System.out.println("event " + id);
        }

        Runnable boundCallback() {
            return this::onEvent;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen("A");
        Runnable callback = screen.boundCallback();

        callback.run();
        screen = null;
        callback.run();
    }
}
~~~

Run:

~~~bash
javac MethodReferenceRetentionDemo.java
java MethodReferenceRetentionDemo
~~~

Output:

~~~text
event A
event A
~~~

`screen = null` does not cause the callback to lose the receiver it needs to call `onEvent`. This is a clear example of retention **without writing an Inner class manually**.

## 17. Pending Tasks Can Retain Owner, Not Just Listeners

A task in a queue/executor/scheduler can hold:

- An inner Runnable that needs `Outer.this`.
- A lambda that needs `this` or object fields.
- Captured local references to a payload/object graph.
- A method reference with a receiver.

While a task sits in a long-lived queue, the referenced objects can remain reachable **until the task runs and is removed from the queue, or cancellation/cleanup breaks the path per the API**.

Do not assume that simply “stopping displaying the UI” cancels all related tasks.

### 17.1. Deterministic Example with a Self-Managed Queue

Save **`PendingTaskRetentionDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Queue;

public class PendingTaskRetentionDemo {
    static final class WorkQueue {
        private final Queue<Runnable> pending = new ArrayDeque<>();

        void enqueue(Runnable action) {
            pending.add(action);
        }

        void runOne() {
            pending.remove().run();
        }

        void clear() {
            pending.clear();
        }

        int size() {
            return pending.size();
        }
    }

    static final class Page {
        private final String id;

        Page(String id) {
            this.id = id;
        }

        Runnable action() {
            return () -> System.out.println("work for " + id);
        }
    }

    public static void main(String[] args) {
        WorkQueue queue = new WorkQueue();
        Page page = new Page("P1");

        queue.enqueue(page.action());
        page = null;

        System.out.println("pending=" + queue.size());
        queue.runOne();
        System.out.println("after run=" + queue.size());

        queue.enqueue(() -> System.out.println("never printed"));
        queue.clear();
        System.out.println("after clear=" + queue.size());
    }
}
~~~

Run:

~~~bash
javac PendingTaskRetentionDemo.java
java PendingTaskRetentionDemo
~~~

Output:

~~~text
pending=1
work for P1
after run=0
after clear=0
~~~

`runOne()` removes the task from the queue before calling `run`, so the queue size returns to 0. `clear()` discards a task that has not yet run without invoking its body.

In a real scheduler, **whether a cancelled task is immediately removed from the queue** and how a running callback is handled depend on the library/implementation; read the API contract and use the required cleanup. Do not generalize a universal policy for all executors from a simple queue demo.

## 18. Breaking the Reference Path: Solutions by Holding Point

A leak-fixing strategy needs to locate **the holder keeping the reference too long**:

| Holder | Common Reference Path | Appropriate Action |
| --- | --- | --- |
| EventBus singleton | bus → listener → owner | Unsubscribe when owner stops operating |
| Static List/Map | static field → inner callback → outer | Remove/clear according to scope and eviction policy |
| Scheduler | scheduler queue → Runnable → screen | Cancel the task properly and drop pending references when the API supports it |
| Timer/Observer | timer → handler → owner | Stop/dispose the observer/timer when closing owner |
| Cache | cache → key/value → owner | Bound the cache, remove/evict entries, and use minimal necessary keys/values |
| ThreadLocal | long-lived thread → ThreadLocal value → owner | Remove at the appropriate time according to the thread lifecycle |
| GUI component | parent registry → listener → owner | Detach the listener when the component unmounts/closes |
| Explicit nested owner field | static nested → owner | Only retain the field when needed; clear/unregister when done |
| Lambda capturing this | registry → closure → this | Capture an immutable snapshot if only values are needed; or unsubscribe |
| Method reference `this::handler` | registry → bound receiver | Unsubscribe and evaluate the receiver's lifetime |

**Do not “fix” it merely by assigning the local variable to null** if the registry still holds the object. You need to break the reference path on **the long-lived owner side** or change the data representation.

## 19. Is `WeakReference` an Automatic Solution?

`WeakReference<T>` allows a reference that **does not maintain strong reachability** of its referent solely via the weak reference. If the referent is no longer strongly reachable, the GC may clear the reference; afterward, `get()` may return null.

However:

- There is no guarantee **when** the GC runs or clears the weak reference.
- If there is still **one** strong reference path to Outer from another registry/lambda/field, a weak reference does not make the object disappear.
- A weak listener can be collected **too early** if nothing holds a strong reference to a listener you still want to remain active.
- Using weak references does not replace ownership/lifecycle documentation.
- Weak references do not automatically prevent a callback from running after the owner has been logically disposed if races are not controlled.
- Weak references can make debugging and reasoning about event ordering harder.

Prefer **lifecycle-aligned unsubscribe/close** when the framework supports it. Use a weak listener when the framework/library provides suitable semantics and you genuinely want the callback to disappear automatically when the owner is no longer strongly held.

### 19.1. Weak Callback Design Example (Snippet)

~~~java
final class WeakCallback implements Runnable {
    private final java.lang.ref.WeakReference<Screen> owner;

    WeakCallback(Screen screen) {
        owner = new java.lang.ref.WeakReference<>(screen);
    }

    @Override
    public void run() {
        Screen current = owner.get();
        if (current != null) {
            current.refresh();
        }
    }
}
~~~

This is an **illustrative snippet** requiring a `Screen` class with `refresh()`. If `owner.get()` returns a non-null Screen, the local `current` acts as a strong reference while the callback uses it. If it returns null, the callback skips the work.

Do not write stdout claiming “after `System.gc` it will definitely print null”, because GC timing and collectability are not guaranteed.

## 20. `WeakHashMap` Does Not Solve Every Retention Path

`WeakHashMap<K,V>` holds keys via weak references, whereas values are normally held strongly. If a value in turn holds a strong reference back to the key, you can create the path:

~~~text
WeakHashMap (root)
      |
      +-- strong value --> Value --> Key
      |
      +-- weak key ------> Key
~~~

Even though the map uses weak keys, the **value → key** path can keep the key strongly reachable and the entry does not disappear as expected. This is a common cache design mistake.

With an inner callback as the value, if the callback holds a reference to the outer key, this situation is particularly noteworthy. You must examine the entire reference graph, not just the map type.

### 20.1. Do Not Use `System.gc()` as an Acceptance Test

A test like:

~~~java
System.gc();
// assert weak.get() == null;
~~~

is unreliable. A GC invocation is not required to reclaim the referent immediately. Instead of testing collection in ordinary unit tests, verify **unregister, clear, and that owner references are no longer in the registry**, and use heap analysis when a leak is suspected in a real application.

## 21. Observing Bytecode: `this$0` Is a Compiler Detail, Not a Contract

With JDK 17 `javac`, a member inner class typically has a **synthetic field** with a name such as `this$0` to store the enclosing Outer reference. This is a compiler implementation detail, not a field you should read/write directly from Java source.

**Important version-specific details:**

- According to the Oracle JDK 18 release notes, **before JDK 18**, `javac` typically generated a synthetic `this$...` field for an inner class even when the enclosing instance was unused.
- **Starting in JDK 18**, `javac` can **omit the unused field** when the inner class does not reference the enclosing instance; the constructor form still follows inner creation rules.
- When the inner class **actually uses** `Outer.this` or instance state, that link semantics must be preserved; do not take the optimization for the “unused” case and conclude that a callback that actually reads Outer also does not retain Outer.
- Other compilers/JVMs may generate different bytecode. Do not rely on the reflection field name `this$0` for business logic.

This means the statement “**every** non-static inner object on **every** JDK always retains the entire Outer until GC” is **too absolute**. The memory retention risk is real, but you must check **the actual reference path and the compiler/version**.

### 21.1. How to Observe This Yourself Without Writing Tests Expecting a Fixed Field

Save **`BytecodeOuterLink.java`**:

~~~java
public class BytecodeOuterLink {
    private final String name = "Outer";

    class Used {
        String read() {
            return BytecodeOuterLink.this.name;
        }
    }

    class Unused {
        int value() {
            return 7;
        }
    }

    public static void main(String[] args) {
        BytecodeOuterLink owner = new BytecodeOuterLink();

        System.out.println(owner.new Used().read());
        System.out.println(owner.new Unused().value());
    }
}
~~~

Compile/run:

~~~bash
javac BytecodeOuterLink.java
java BytecodeOuterLink
~~~

Output:

~~~text
Outer
7
~~~

Afterward, you can inspect the compiler-generated fields/methods using the JDK tool `javap`:

~~~bash
javap -p "BytecodeOuterLink$Used"
javap -p "BytecodeOuterLink$Unused"
~~~

Double quotes in the example work in many command shells, but in shells that expand the `$` character (such as some Bash contexts) you should use **single quotes**:

~~~bash
javap -p 'BytecodeOuterLink$Used'
javap -p 'BytecodeOuterLink$Unused'
~~~

**There is no fixed stdout for `javap` in this lesson**, because bytecode layout depends on the version/compiler. Observe that Used needs outer state and Unused does not, then compare with the release notes of the JDK you are running.

### 21.2. Consider Source-Level Semantics Before Synthetic Fields

Having a compiler-generated field optimized away does not turn the syntax `owner.new Unused()` into `new Outer.Unused()`. A member Inner is still a non-static class and the creation expression still requires the proper qualifier. Only **representation/runtime retention** can differ when the enclosing reference is genuinely unneeded.

## 22. A Method/Field Using Only Static Data Does Not Logically Need to Retain Outer

Consider:

~~~java
class Outer {
    private static final int VERSION = 17;

    class Inner {
        int version() {
            return VERSION;
        }
    }
}
~~~

Inner's source only reads a static member; computationally, the method does not need the state of a specific Outer object. This is a case where compiler optimization may omit the reference to the enclosing instance on a suitable JVM/JDK, as noted earlier.

However, to express the design intent that **no outer instance is needed**, declaring a **static nested class** is usually clearer:

~~~java
class Outer {
    private static final int VERSION = 17;

    static class Nested {
        int version() {
            return VERSION;
        }
    }
}
~~~

Clients can instantiate `new Outer.Nested()` without creating an Outer first. This reduces coupling and avoids relying on compiler optimizations.

## 23. Impact of References to Large Arrays and Object Graphs

An Inner might only read a small `Outer.this.id`, but while Outer remains reachable, **the other fields of Outer** can also remain reachable, for example:

- A `byte[]` for images/caches/buffers.
- A `List` containing thousands of objects.
- A graph of view models/DOM-like trees.
- Connections/handlers stored in fields.
- Other listener objects and the state of a screen/session.

Therefore, holding a reference to **one Outer** can have a *retained size* much larger than Outer's shallow size.

**Distinguish two metrics when using a heap analyzer:**

- *Shallow size*: the memory belonging to the object itself.
- *Retained size*: the total memory that could be freed if the object/dominator path were removed as defined by the analyzer, depending on the graph.

Do not mechanically sum field sizes and treat that as the retained size; shared objects have multiple reference paths and dominator relationships that require analysis.

## 24. Example: Instead of Retaining the Entire Screen, Retain Only an ID Snapshot

If the callback only needs to log the ID when an event occurs:

**Prone to retaining the owner unnecessarily:**

~~~java
class Screen {
    private final String id;

    Screen(String id) {
        this.id = id;
    }

    class LoggerHandler implements Runnable {
        public void run() {
            System.out.println(Screen.this.id);
        }
    }
}
~~~

**Clearer lifetime:**

~~~java
class Screen {
    private final String id;

    Screen(String id) {
        this.id = id;
    }

    static final class LoggerHandler implements Runnable {
        private final String idSnapshot;

        LoggerHandler(String idSnapshot) {
            this.idSnapshot = idSnapshot;
        }

        public void run() {
            System.out.println(idSnapshot);
        }
    }

    Runnable newLogger() {
        return new LoggerHandler(id);
    }
}
~~~

Both snippets are **class snippets**, presented separately and not sharing a single file. In the static nested version, the callback only holds an immutable String ID, with no path to Screen unless another reference is passed/retained.

**Do not apply this technique** when the callback needs to update Screen live. In that case, retain the owner properly and manage the registration lifecycle.

## 25. Weak-Reference versus Explicit Cancellation: Choosing by Contract

| Goal | Typically Suitable | Trade-offs / Caveats |
| --- | --- | --- |
| Callback lives only as long as the UI component | Unsubscribe/dispose when closing the UI | Lifecycle cleanup must be implemented on every exit path |
| Async task must be cancelled when owner stops | Cancel/queue cleanup and lifecycle token | An already-running callback may still require coordination |
| Callback only needs small immutable data | Static nested class or lambda capturing a snapshot | Do not use if a live owner is actually needed |
| Owner is intentionally long-lived and callback uses live owner | Hold strong owner reference with explicit lifecycle | This is not a leak if intended |
| Want owner to be GC'd when nothing holds it strongly | Weak owner reference with null check | Collection timing is non-deterministic |
| Framework has a weak listener API | Follow the framework convention properly | The listener may disappear if not strongly held long enough |
| Cache with keys that no longer need to be kept | Bounded cache/weak keys depending on the domain | Values can refer back to keys; weak refs do not fix every graph |
| Data is used across multiple threads | Immutable snapshot or synchronization | Publication/cancellation races still exist |

Do not just ask “should I use weak or strong?”. Answer **who owns the subscription, when it should be stopped, and whether the callback needs to run after the owner disappears**.

## 26. Thread Safety and Callback Cleanup

Simply having a reference to Outer is not a data race by itself. However, if the callback executes on another thread and accesses mutable Outer fields, appropriate Java Memory Model rules must be satisfied.

For example:
- Shared mutable fields require synchronization/volatile/locks/atomic operations depending on the contract.
- Calling `close()` on a subscription concurrently with event dispatch may still let a currently running callback finish; define a clear boundary for what “unsubscribed” means.
- A simple `ArrayList`-based EventBus is not suitable for concurrent register/fire/remove without protection.
- Immutable snapshot data helps reduce races, though holder reference/publication must still be handled properly.
- A callback reading a String snapshot does not mean a sequence of external updates is atomic.

### 26.1. Concurrent Registry Example Using an Appropriate Library (Snippet)

~~~java
private final java.util.concurrent.CopyOnWriteArrayList<Runnable>
        listeners = new java.util.concurrent.CopyOnWriteArrayList<>();
~~~

This structure provides thread-safe collection operations according to the `CopyOnWriteArrayList` contract, however:

- The listener object can still retain Outer through a captured reference.
- `remove` still needs to be called when the lifecycle ends.
- Snapshot iteration semantics may allow a callback that existed when iteration started to still be invoked even if it is removed mid-dispatch.
- Shared mutable state inside the callback still needs its own concurrency controls.

**A thread-safe collection does not prevent memory retention on its own.**

## 27. Heap Inspection: Verifying a Leak via GC Root Paths

When an application's heap grows after opening and closing a screen multiple times, do not conclude there is a leak from a single snapshot alone.

Practical investigation workflow:

1. **Reproduce the workflow** that creates/destroys the owner (open/close screen, subscribe/unsubscribe) repeatedly in a controlled manner.
2. Monitor heap usage after actual GC cycles have occurred; distinguish warm-up, intentional caches, allocation rate, and live set.
3. Capture an appropriate heap dump or live-object histogram, keeping in mind that a heap dump may contain sensitive data.
4. Use Memory Analyzer/VisualVM/JDK tooling to find instances of Screen/View/Outer after their lifecycle should have ended.
5. Inspect **paths to GC roots**, **incoming references**, the **dominator tree**, and retained size; identify the registry/listener/task/cache owner.
6. Check whether an Inner/lambda/anonymous instance holds a reference/captured receiver to Outer, without relying solely on the field name `this$0`.
7. Fix **the root holding the reference**: unregister, cancel, clear the cache/queue, or switch to a static nested class/snapshot if consistent with the contract.
8. Re-run the workflow and compare live counts/retained paths. Do not promise immediate GC in a unit test.

### 27.1. Commonly Used Tools

- **VisualVM**: profiler, heap dump browsing, and inspecting instances/references.
- **Eclipse Memory Analyzer (MAT)**: dominators, retained heap, and paths to GC roots.
- **JDK Mission Control / JFR**: allocation/GC telemetry and application runtime diagnostics.
- **`jcmd`** and JDK diagnostic commands: can collect histograms/heap info/dumps according to the options of the JDK in use.
- **`javap -p`**: inspect details of generated fields/methods of a specific class file; does not replace heap analysis.

Do not run heap dumps on sensitive production data without appropriate access, storage, and deletion policies.

## 28. Avoid Fixing Leaks by Forcing Every Field to `null`

Setting a local reference to null sometimes helps code avoid holding a local longer than needed, but it **does not remove the reference in the registry**. For example:

~~~java
Screen screen = new Screen();
bus.add(screen.new Handler());

screen = null;
~~~

This is an illustrative snippet requiring an appropriate `Screen`/`bus`. The registry still holds the handler. The **proper solution** is usually to remove the registration or change how the callback retains the owner.

Similarly, `System.gc()` does not break any reference path. It does not replace fixing the lifecycle.

## 29. Do Not Assume Every Nested Class Retains Outer

Distinguish among the following:

| Nested/Callback Kind | Implicit Enclosing Outer Instance? | Risk of Retaining Outer |
| --- | --- | --- |
| Non-static member `Outer.Inner` | Yes by inner class semantics; physical field depends on compiler/usage | When a reference to Outer is actually needed/present and the callback is retained |
| Static member `Outer.Nested` | No | Only if other explicit/captured references retain Outer |
| Member record inside Outer | Implicitly static | No implicit enclosing Outer |
| Member interface/enum | Implicitly static | No implicit enclosing Outer |
| Local class in instance context | Can bind/capture enclosing context per language rules | When using state/refs leading to Outer |
| Local class in static context | No enclosing Outer instance from a static method | Can retain captured local objects |
| Anonymous class in instance context | Can capture/use enclosing instance | When using owner/captured references |
| Lambda using instance field/`this` | Captures the receiver it needs to use | Can retain Outer |
| Lambda using only immutable captured local | Does not need owner for that reason | Can retain another captured object |
| Bound method reference `owner::method` | Retains the receiver needed for the call | Can retain owner |
| Unbound/static method reference | Does not require holding a specific owner instance | Depends on any other captured values |

**Read the actual semantics and reference graph**, rather than classifying by file names like `Outer$1.class` or by whether the code sits inside Outer's braces.

## 30. Common Design Mistakes

| Mistake | Fix / Correct Understanding |
| --- | --- |
| “Inner is created locally in a method, so it dies when the method returns.” | If held by a registry, inner remains reachable after the method. |
| “`owner = null` definitely frees owner.” | Other reference paths remain from callbacks/listeners/queues. |
| “Java GC does not collect cycles, so Outer↔Inner leaks.” | GC can collect unreachable cycles; check the roots. |
| “Every Inner object on every JDK always has a `this$0` field.” | JDK 18 javac may omit an unused outer field; implementation-dependent. |
| “A static nested class never retains Outer.” | It can still retain an explicit Outer field or other references. |
| “Using `WeakReference` means no cleanup is needed.” | Weak refs do not replace lifecycle; callbacks may be lost too early. |
| “`WeakHashMap` always causes keys to be GC'd.” | A value holding a strong reference back to the key can keep the key alive. |
| “One `System.gc()` call proves there is no leak.” | There is no GC timing guarantee. |
| “A thread-safe EventBus does not leak.” | Thread safety and retention are two separate concerns. |
| “Copy Outer so the listener does not hold the old object.” | Copying can break semantics and still share components; fix ownership. |
| “Create a new listener to call remove for the old listener.” | The registry may rely on identity/equality; the exact reference/token is needed. |
| “Anonymous classes and lambdas always capture outer the same way.” | A lambda only retains the receiver if its body/references require it; `this` semantics differ. |
| “Every Inner must always be converted to static.” | If inner legitimately needs a live Outer, lifecycle management is the focus. |
| “A weak listener is better than a strong listener in every case.” | It may be collected while the callback is still needed. |
| “Once the UI screen closes, the timer cancels automatically.” | Depends on framework/lifecycle; stop/cancel as needed. |
| “An unregistered callback cannot currently be executing.” | Concurrent dispatch may have a callback in flight; a clear race contract is needed. |
| “Retained size equals Inner's shallow size.” | Inner can hold a large Outer graph via one reference. |
| “A single heap dump is enough to prove a leak.” | Reproduction, lifecycle expectations, and roots/retained paths are needed. |

## 31. Code Review Checklist for Inner Callbacks

1. Does Inner genuinely need to call Outer's instance state/methods?
2. If not, can a **static nested class** or top-level helper be used?
3. If only a small ID/config is needed, can an immutable snapshot be captured instead of the whole Outer?
4. Which service will the Callback/Inner be registered with? Does the service's lifetime outlast the owner's?
5. Who stores the registration token/reference? Who is responsible for unsubscribing?
6. Are all cleanup branches covered: success, exception, close, cancellation, timeout, unmount?
7. Can the callback still be running during unsubscribe? Does the API require atomicity?
8. Are there pending executor/scheduler tasks when the owner stops?
9. Does any static cache/registry/listener list hold the callback long-term?
10. Is a `this::method` or `() -> instanceField` lambda capturing the receiver?
11. Is an anonymous/local class reading `Outer.this` or captured mutable references?
12. Is any weak listener held strongly long enough as needed?
13. Is `WeakHashMap` used with values referencing back to weak keys?
14. Does Outer hold large payloads/graphs causing a large retained size?
15. Is there a benchmark/test repeating multiple open-close cycles to observe registry size?
16. Is there a heap dump path to GC roots confirming the exact retention chain?
17. Was a test accidentally written calling `System.gc()` and asserting the object is cleared immediately?
18. Are assumptions being extrapolated from a synthetic field name on one JDK to every other JDK?
19. If Inner is changed to a static nested class, do business behavior and lifetime semantics remain correct?
20. Has the ownership contract been explained to callers of the API?

## 32. Self-Verification Lifecycle Program Without Relying on GC

Save **`ListenerLifecycleContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerLifecycleContractTest {
    static final class Bus {
        final List<Runnable> handlers = new ArrayList<>();

        void add(Runnable callback) {
            handlers.add(callback);
        }

        void remove(Runnable callback) {
            handlers.remove(callback);
        }
    }

    static final class Owner {
        private final String id;

        Owner(String id) {
            this.id = id;
        }

        class Handler implements Runnable {
            @Override
            public void run() {
                if (Owner.this.id.isBlank()) {
                    throw new IllegalStateException();
                }
            }
        }

        Handler subscribe(Bus bus) {
            Handler handler = new Handler();
            bus.add(handler);
            return handler;
        }
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        Owner owner = new Owner("A");

        Owner.Handler handler = owner.subscribe(bus);

        check(bus.handlers.size() == 1, "registered");
        check(bus.handlers.contains(handler), "same handler");

        bus.handlers.get(0).run();
        bus.remove(handler);

        check(bus.handlers.isEmpty(), "cleanup");
        System.out.println("listener lifecycle checks passed");
    }
}
~~~

Run:

~~~bash
javac ListenerLifecycleContractTest.java
java ListenerLifecycleContractTest
~~~

Output:

~~~text
listener lifecycle checks passed
~~~

The test checks the **register/unregister contract** using deterministic behavior. It draws no conclusions about Owner's GC timing. If a production bug involves retention, add an appropriate lifecycle integration test and heap analysis.

## 33. Review Exercises and Solutions

**Question 1.** What does `Outer.Inner x = outer.new Inner()` provide?  
**Answer:** Creates an Inner associated with the current enclosing Outer instance of `outer`.

**Question 2.** Which object does an Inner using `Outer.this.id` reference?  
**Answer:** The enclosing Outer object associated with the Inner.

**Question 3.** Does `new Outer.Nested()` require an enclosing Outer instance?  
**Answer:** No, if Nested is an accessible static member class.

**Question 4.** A registry holds an Inner listener that reads Outer fields; is assigning `outer=null` enough for Outer to be GC'd?  
**Answer:** No; registry → listener → Outer may still be a strong path.

**Question 5.** Once the registry removes the listener, is Outer guaranteed to be collected immediately?  
**Answer:** No. Other refs may remain, and GC timing is not guaranteed.

**Question 6.** If Outer ↔ Inner form a cycle with no GC root pointing to them, do they leak by default?  
**Answer:** No; the garbage collector can collect unreachable cycles.

**Question 7.** What change did JDK 18 make regarding `this$0`?  
**Answer:** `javac` can omit the synthetic enclosing-instance field when the inner class does not use the outer instance.

**Question 8.** Does the JDK 18 optimization remove the `outer.new Inner()` requirement for a non-static member Inner?  
**Answer:** No. Source-level creation syntax/enclosing rules still apply.

**Question 9.** Can an Inner that actually reads `Outer.this.id` use that data after the caller drops the local Outer reference?  
**Answer:** Yes, if Inner is still retained; it needs the semantic link to Outer.

**Question 10.** Can a static nested callback holding `private final Outer owner` keep Outer reachable?  
**Answer:** Yes. An explicit strong owner reference is still a reference path.

**Question 11.** When a callback only needs an immutable String ID, which design approach generally reduces coupling?  
**Answer:** A static nested callback or lambda that captures only the ID snapshot, without capturing the whole owner.

**Question 12.** Can the lambda `() -> println(this.status)` retain the owner?  
**Answer:** Yes, because the body uses the `this` receiver/instance state.

**Question 13.** Does a lambda that only captures a local String snapshot always retain Outer?  
**Answer:** Not because of capturing the String snapshot; however, you must examine all captured references/implementation.

**Question 14.** What does `this` inside an anonymous Runnable point to?  
**Answer:** The anonymous Runnable object; for the enclosing Outer, use `Outer.this` if present.

**Question 15.** What does `this` inside a lambda placed in an Outer instance method point to?  
**Answer:** According to lexical scope, the Outer instance.

**Question 16.** Does `owner::onEvent` retain the owner receiver needed to invoke the method?  
**Answer:** It can create a strong reference to the receiver; check the callback's lifecycle.

**Question 17.** Can an unexecuted callback in a queue retain Outer?  
**Answer:** Yes, if the callback retains Outer/a captured reference and the queue still holds the callback.

**Question 18.** Is every cancelled scheduled task immediately removed from the queue?  
**Answer:** There is no general guarantee; it depends on the scheduler implementation/configuration.

**Question 19.** What is the clearest cleanup mechanism for an EventBus listener?  
**Answer:** Keep the registration token/reference and unregister/close when the owner stops.

**Question 20.** Why might creating a new Handler and then calling remove fail to delete the old Handler?  
**Answer:** The new Handler is a different object, and Object.equals defaults to identity if not overridden.

**Question 21.** Does `WeakReference` guarantee `get()==null` immediately after `System.gc()`?  
**Answer:** No. GC has unguaranteed timing/behavior.

**Question 22.** Why might a weak listener be lost too early?  
**Answer:** There is no longer a strong root holding the listener while business logic still needs the callback.

**Question 23.** Can a `WeakHashMap` whose value points back to the key retain the key?  
**Answer:** Yes; a strong path from the value to the key can prevent the key from being collected.

**Question 24.** How can an Outer containing a large byte[] retained by an Inner affect retained size?  
**Answer:** It can keep the entire payload graph reachable, larger than Inner's shallow size.

**Question 25.** Should you rely on the reflection field name `this$0` to find the owner?  
**Answer:** No; synthetic fields/names/compiler layout are not a public API contract.

**Question 26.** Why does a thread-safe listener list not fix a memory leak on its own?  
**Answer:** Thread safety of operations is distinct from the lifetime of stored listener references.

**Question 27.** Are all inner classes bad design?  
**Answer:** No. When business logic needs to bind to Outer and the lifecycle is managed, Inner is well suited.

**Question 28.** If a callback reads live outer state, can it be replaced with an ID snapshot while preserving behavior?  
**Answer:** Not necessarily; a snapshot can alter semantics. Clarify whether live state or a snapshot is needed.

**Question 29.** In a heap dump, what should you look for to explain why Outer is not collected?  
**Answer:** Path to GC roots and incoming strong reference chains, dominators/retained size.

**Question 30.** What should a retention unit test assert instead of immediate GC?  
**Answer:** The remaining number of subscriptions/tasks, unregister/cancel with the exact identity, registry cleanup, and behavior after close.

**Question 31.** If a callback has receiver `this::handler` and is stored in a global map, what can be retained?  
**Answer:** The receiver object and the graph reachable from the receiver if there is no cleanup.

**Question 32.** Since a static nested class does not hold an implicit outer reference, how else can it cause a leak?  
**Answer:** Retaining Outer or a large graph through explicit fields, callbacks, or other references.

## 34. References

- Java Language Specification Java SE 17, [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance semantics.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): qualified inner class creation.
- Java Language Specification, [`15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this`.
- Java Language Specification, [`15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda lexical scoping/capture.
- Java Platform API Java 17, [`WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability.
- Java Platform API, [`WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys and value references.
- Java Platform API, [`AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): lifecycle/close.
- Java Platform API, [`CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): thread-safe listener registry pattern, note lifecycle.
- Java Platform API, [`System.gc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): a GC request, not confirmation of immediate collection.
- Oracle JDK 18 Release Notes, [Enclosing Instance Fields Omitted from Inner Classes That Don't Use Them](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): `javac` compiler change regarding unused `this$` synthetic fields.
- Java Platform Tools, [`javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspect class file fields/methods.
- Java Platform Tools, [`jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JDK diagnostics/heap inspection.

## Summary

A **non-static member Inner** created with `outer.new Inner()` has an enclosing instance according to Java source-level semantics, allowing the use of `Outer.this` and access to outer instance fields. If an Inner callback is retained in a long-lived registry/task/cache and actually needs the enclosing Outer, it can **keep Outer along with many of Outer's components reachable**, even when the caller no longer holds a local variable pointing to Outer. This is memory retention caused by ownership/lifecycle, not by GC “not knowing how to collect cycles”.

Do not blindly assert that every Inner on every compiler always has a `this$0` field: starting in JDK 18, `javac` can omit this synthetic field if the enclosing instance **is not used**. To reduce risk, use a **static nested class or a callback capturing immutable values** when the owner is not needed; when a live owner is needed, **register/unregister/cancel/close explicitly** according to the lifecycle. A static nested class with an explicit owner field can also retain Outer, so merely changing the `static` keyword does not replace managing references.

Finally, do not measure “success” using `System.gc()`. Verify subscription counts, callback identity, and task cleanup, and use **heap snapshots + paths to GC roots** when retention is suspected in a real application. Choosing where a callback is held and when it is released matters more than any trick for forcing GC.
