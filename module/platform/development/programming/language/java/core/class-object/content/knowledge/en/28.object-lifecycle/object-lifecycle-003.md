# Distinguishing Variable Scope from Object Reachability — Java 17+

## Objectives

This lesson is part of the **Object Lifecycle** topic in Java core. After completing it, you will be able to:

- Distinguish the **lexical scope of a variable name** from the **reachability of an object** at runtime.
- Understand that a block-closing `}` and a method `return` are not the moments when Java automatically deletes every object created inside.
- Distinguish **reference variable**, **reference value**, and **heap object**, including multiple aliases pointing to the same object.
- Identify paths that retain objects via return values, instance/static fields, arrays, collections, lambdas, inner classes, event listeners, threads, and task queues.
- Explain Java **pass-by-value**, including when passing a reference type: reassigning a parameter does not change the caller reference, but mutating the referent can affect the caller.
- Understand the converse: a local variable remaining in lexical scope does not guarantee that the referent stays strongly reachable until the end of the block; the JVM/JIT may stop retaining the reference after *last use* according to Java rules.
- Distinguish **eligible to be collected by the garbage collector** from **already collected by the GC**; `System.gc()` does not promise when an object will be reclaimed.
- Distinguish strong, weak, and other reachability levels in `java.lang.ref`; use `WeakReference` and `Reference.reachabilityFence` without predicting non-deterministic GC output.
- Understand that reference cycles A→B→A do not prevent a tracing GC from reclaiming them if the entire graph no longer has a root path.
- Identify logical memory leaks from long-lived maps, static registries, listeners, lambdas, or ThreadLocals retaining objects longer than expected.
- Distinguish object reachability, Java *statement reachability*, access modifiers, `final`, and the lifecycle of resources requiring `close()`.
- Write and run standalone Java 17+ examples, with exact stdout **not depending on GC running at any specific time**.

> **Scope:** Java 17+. Examples with file names, `javac`/`java` commands, and stdout are complete programs. Snippets without `main` are for illustration only. This lesson intentionally avoids using finalizer logs, `Thread.sleep`, or `System.gc()` to assert that GC occurs at a specific source line.

## 1. Two Different Issues

Code snippet:

~~~java
{
    StringBuilder text = new StringBuilder("hello");
    System.out.println(text);
}
// text cannot be referenced by name outside the block.
~~~

The question **"Is the variable text still in scope?"** has the answer **no**: the lexical scope of the local name has ended.

The question **"Has the StringBuilder object been deleted?"** does not have an answer from the `}` brace:

- The object might be referenced by another variable/field.
- A callback/collection might hold it indirectly.
- It might no longer be strongly reachable, but the GC has not reclaimed it yet.
- The JVM/JIT might optimize object liveness earlier than intuition based on source variables would suggest.

In short:

**Scope is about *which name can be used at which source location*. Reachability is about *which reference path still allows continuing to access the object* at runtime.**

### 1.1. An Easy-to-Remember Model

~~~text
Inside the block:
   local text ─────► StringBuilder("hello")

After the block:
   the name "text" is no longer valid in source.

The StringBuilder object:
   may have another reference path;
   may no longer be accessible;
   may not yet be GC reclaimed.
~~~

Do not equate "the local variable disappears" with "the heap object is deleted." Java does not have a mechanism that automatically calls a heap object destructor at every lexical scope boundary.

## 2. How Does the JLS Define Variable Name Scope?

Java Language Specification (JLS) `6.3 describes the scope of a declaration as the region in source where that declaration can be referred to by name according to name resolution rules.

~~~java
static void example() {
    {
        int count = 3;
        System.out.println(count);
    }
    // System.out.println(count); // Does not compile: out of scope.
}
~~~

The same applies to reference variables:

~~~java
static void example() {
    {
        Object local = new Object();
        System.out.println(local != null);
    }
    // local can no longer be used by name here.
}
~~~

**Distinguishing three layers of concepts:**

| Concept | What does it ask? | Who decides? |
| --- | --- | --- |
| Lexical scope | Can a local/parameter name be used at this source location? | Java compiler/JLS |
| Runtime execution frame/liveness | Which values need to be kept while the method is running? | JVM/JIT according to Java semantics |
| Object reachability | Does the object have a path for continuing computation to access it? | Runtime reference graph, optimizations, and GC |

You should not assume every source variable occupies a fixed stack slot until the end of the block. The JVM/JIT may use registers, eliminate unnecessary locals, shorten liveness, or eliminate allocations if behavior is preserved.

## 3. Program 1 — Block Scope Does Not Create a GC Event

Save **`BlockScopeDemo.java`**:

~~~java
public class BlockScopeDemo {
    static class Note {
        final String text;

        Note(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        {
            Note local = new Note("inside");
            System.out.println(local.text);
        }
        System.out.println("after");

        // System.out.println(local); // Invalid.
    }
}
~~~

Run:

~~~bash
javac --release 17 BlockScopeDemo.java
java BlockScopeDemo
~~~

Stdout:

~~~text
before
inside
after
~~~

We have demonstrated that **the name `local` cannot be used** after the block. There is no evidence that the JVM ran GC between the two println calls.

## 4. Reference Variables Are Different from Objects

Example:

~~~java
Box first = new Box("A");
Box second = first;
~~~

Two reference variables can point to the same object:

~~~text
first ─────┐
           ├────► Box("A")
second ────┘
~~~

`first = null` changes **the reference value of first**, does not modify second, and does not delete the Box object. The `==` operator on reference operands checks identity, while `equals` may compare values depending on the class.

A local is not a "container holding the whole object" according to source semantics: a local holds a reference value, and the object can be accessed through multiple paths.

### 4.1. Program 2 — An Alias Retains the Object

Save **`ReferenceAliasDemo.java`**:

~~~java
public class ReferenceAliasDemo {
    static class Box {
        String label;

        Box(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = first;

        System.out.println("same=" + (first == second));
        first = null;

        System.out.println("first null=" + (first == null));
        System.out.println("second label=" + second.label);
        second.label = "B";
        System.out.println("second updated=" + second.label);
    }
}
~~~

Run:

~~~bash
javac --release 17 ReferenceAliasDemo.java
java ReferenceAliasDemo
~~~

Stdout:

~~~text
same=true
first null=true
second label=A
second updated=B
~~~

### 4.2. `final` Does Not Make an Object Immortal

`final Box reference = ...` prevents reassigning that variable; it does not make the referent immutable on its own, does not guarantee it lives forever, and does not prevent GC once no needed path remains. `final` is a variable/field assignment rule, not a special weak/strong reference type.

## 5. Returning a Reference from a Method Is a Form of Object Escape

An object created in a method can be **returned**:

~~~java
static Book createBook() {
    Book local = new Book("Java");
    return local;
}
~~~

After return, local goes out of scope, but the caller receives the reference value:

~~~java
Book received = createBook();
~~~

The object can continue to be used. There is no automatic cloning, nor is it true that "every object created in a method dies when the method ends."

### 5.1. Program 3 — Local Goes Out of Scope, Object Returned Remains Accessible

Save **`ReturnReferenceDemo.java`**:

~~~java
public class ReturnReferenceDemo {
    static class Book {
        final String title;

        Book(String title) {
            this.title = title;
        }
    }

    static Book makeBook() {
        Book local = new Book("Effective Java");
        return local;
    }

    public static void main(String[] args) {
        Book received = makeBook();
        System.out.println("title=" + received.title);
        System.out.println("received null=" + (received == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 ReturnReferenceDemo.java
java ReturnReferenceDemo
~~~

Stdout:

~~~text
title=Effective Java
received null=false
~~~

## 6. Passing a Reference to a Method: Java Is Pass-by-Value

When passing a reference type argument, Java passes **a copy of the reference value** to the parameter.

~~~java
static void reassign(Box parameter) {
    parameter = new Box("other");
}
~~~

Reassigning `parameter` does not change the caller variable. Conversely:

~~~java
static void mutate(Box parameter) {
    parameter.label = "changed";
}
~~~

the method modifies the object that both the caller and callee can reference. The parameter goes out of scope when the method returns, but the caller may still retain the object.

### 6.1. Program 4 — Reassigning Differs from Mutating

Save **`ParameterScopeDemo.java`**:

~~~java
public class ParameterScopeDemo {
    static class Box {
        String label;

        Box(String label) {
            this.label = label;
        }
    }

    static void reassign(Box parameter) {
        parameter = new Box("other");
        System.out.println("inside reassign=" + parameter.label);
    }

    static void mutate(Box parameter) {
        parameter.label = "changed";
        System.out.println("inside mutate=" + parameter.label);
    }

    public static void main(String[] args) {
        Box caller = new Box("original");
        reassign(caller);
        System.out.println("after reassign=" + caller.label);
        mutate(caller);
        System.out.println("after mutate=" + caller.label);
    }
}
~~~

Run:

~~~bash
javac --release 17 ParameterScopeDemo.java
java ParameterScopeDemo
~~~

Stdout:

~~~text
inside reassign=other
after reassign=original
inside mutate=changed
after mutate=changed
~~~

The scope of a parameter is source-level. The caller reference remains usable after the method returns.

## 7. An Instance Field Can Retain an Object Longer Than the Local That Created It

~~~java
Holder holder = new Holder();
{
    Item local = new Item("A");
    holder.item = local;
}
// local is out of scope; holder.item can still be used.
~~~

Graph:

~~~text
holder ──► Holder object ──item──► Item("A")
~~~

If Holder remains reachable, there is a reference path from Holder to Item. `private` only affects the ability to reference the field by name from other code; it does not cause the GC to ignore the field. `final` restricts reassigning the field; it does not make the target deep-immutable on its own.

### 7.1. Program 5 — A Field Retains Its Referent

Save **`FieldRetainsObjectDemo.java`**:

~~~java
public class FieldRetainsObjectDemo {
    static class Item {
        final String name;

        Item(String name) {
            this.name = name;
        }
    }

    static class Holder {
        Item item;
    }

    public static void main(String[] args) {
        Holder holder = new Holder();

        {
            Item local = new Item("retained");
            holder.item = local;
        }

        System.out.println("through field=" + holder.item.name);
        holder.item = null;
        System.out.println("field cleared=" + (holder.item == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 FieldRetainsObjectDemo.java
java FieldRetainsObjectDemo
~~~

Stdout:

~~~text
through field=retained
field cleared=true
~~~

After `holder.item=null`, we only know that Holder no longer holds a reference through that field; the GC may not have run yet, and other aliases may exist.

## 8. Collections Hold References, Not "Local Variable Names"

An `ArrayList<Item>` holds references to its elements. When code calls `items.add(local)`, the list has a reference path to the object. The creator local going out of scope does not automatically remove the list element.

Similarly, an array cell `slots[0]=local` also holds a reference. `items.clear()` or `slots[0]=null` removes the corresponding reference path; it does not delete other aliases or force GC.

### 8.1. Program 6 — Collection Retention

Save **`CollectionReachabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CollectionReachabilityDemo {
    static class Item {
        final String code;

        Item(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) {
        List<Item> items = new ArrayList<>();

        {
            Item temporary = new Item("A");
            items.add(temporary);
        }

        System.out.println("size=" + items.size());
        System.out.println("first=" + items.get(0).code);

        items.clear();
        System.out.println("cleared size=" + items.size());
    }
}
~~~

Run:

~~~bash
javac --release 17 CollectionReachabilityDemo.java
java CollectionReachabilityDemo
~~~

Stdout:

~~~text
size=1
first=A
cleared size=0
~~~

### 8.2. Program 7 — Array Cell Retention

Save **`ArrayAliasDemo.java`**:

~~~java
public class ArrayAliasDemo {
    static class Counter {
        int value;
    }

    public static void main(String[] args) {
        Counter[] slots = new Counter[1];

        {
            Counter local = new Counter();
            local.value = 5;
            slots[0] = local;
        }

        slots[0].value++;
        System.out.println("through array=" + slots[0].value);

        slots[0] = null;
        System.out.println("slot cleared=" + (slots[0] == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 ArrayAliasDemo.java
java ArrayAliasDemo
~~~

Stdout:

~~~text
through array=6
slot cleared=true
~~~

## 9. Static Fields and Lifetimes Longer Than a Method

A static field is class-level state:

~~~java
class Cache {
    static Object retained;
}
~~~

A method can store a reference into a static field; after the method returns, the reference through Cache can still retain the object.

We do not state unconditionally that "every static field exists until JVM shutdown" because classloader/class unloading/liveness may differ depending on the runtime. However, static caches and registries in an application are a very common source of **long-lived retention**.

### 9.1. Program 8 — Static Reference After Method Return

Save **`StaticReferenceDemo.java`**:

~~~java
public class StaticReferenceDemo {
    static class Store {
        static StringBuilder kept;
    }

    static void build() {
        StringBuilder local = new StringBuilder("stored");
        Store.kept = local;
    }

    public static void main(String[] args) {
        build();
        System.out.println("static value=" + Store.kept);

        Store.kept = null;
        System.out.println("static cleared=" + (Store.kept == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
~~~

Stdout:

~~~text
static value=stored
static cleared=true
~~~

Returning from method build does not cause the StringBuilder to disappear immediately, because the class-level field continues to hold the reference.

## 10. Important: A Variable **Remains in Scope**, Yet the Object Can Lose Liveness Before the Closing Brace

This is the converse direction that is often overlooked:

~~~java
static void work() {
    byte[] data = new byte[1_000_000];
    System.out.println(data.length);

    doOtherWork();
    // The name data is still in lexical scope.
}
~~~

After the last use of `data.length`, the JVM/JIT can determine that the reference is no longer needed for any continuing computation. JLS `12.6.1 allows optimizing transformations to reduce the set of reachable objects compared to naive reasoning from locals; for example, the runtime may treat a variable/parameter that is no longer used as no longer holding a reference.

Thus:

- **The name is still in scope** ≠ **the referent must remain strongly reachable until the end of the block**.
- An optimizing runtime must preserve *observable Java behavior*. If the source later actually reads data in a valid read, the optimization must not produce an incorrect result.
- Last-use analysis and stack/register liveness are runtime/compiler concerns; they do not redefine the lexical scope of a variable name.
- Do not rely on a finalizer output or GC log to claim the exact line at which an object is freed.

**In summary:** name scope is a source/compile-time concept; reachability is runtime in nature and is legitimately optimized by the JVM.

## 11. `x = null` Is Not `delete x`

~~~java
Object value = create();
use(value);
value = null;
~~~

The final assignment changes the value of the local reference. It can sometimes help shorten retention in a long-running frame, though the JIT may recognize the last use on its own. Do not add `=null` to every method as a memory-cleanup ritual.

In particular, if `other=value` occurred before assigning null, `other` still holds the object. If `value` was already added to a cache/list/field, assigning null to the local does not remove those other references.

### 11.1. Program 9 — Reassignment Does Not Destroy the Old Object

Save **`ReassignmentDemo.java`**:

~~~java
public class ReassignmentDemo {
    static class Data {
        final int value;

        Data(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Data first = new Data(1);
        Data alias = first;

        first = new Data(2);
        System.out.println("first=" + first.value);
        System.out.println("alias=" + alias.value);
        System.out.println("same=" + (first == alias));

        alias = null;
        System.out.println("alias null=" + (alias == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 ReassignmentDemo.java
java ReassignmentDemo
~~~

Stdout:

~~~text
first=2
alias=1
same=false
alias null=true
~~~

## 12. A Lambda Can Capture a Reference and Be Retained Longer Than the Block

A final/effectively final local can be captured by a lambda:

~~~java
Runnable action;
{
    StringBuilder builder = new StringBuilder("A");
    action = () -> System.out.println(builder);
}
action.run();
~~~

`builder` goes out of lexical scope, but the lambda still needs the captured value. How the JVM creates or lays out the lambda object is an implementation detail; the semantics guarantee that the callback can use the referent.

**Effectively final** means the reference variable is not reassigned; it does **not** mean the StringBuilder object is immutable. The lambda can `append` content.

### 12.1. Program 10 — A Captured Reference Remains Usable

Save **`LambdaCaptureDemo.java`**:

~~~java
public class LambdaCaptureDemo {
    public static void main(String[] args) {
        Runnable action;

        {
            StringBuilder builder = new StringBuilder("A");
            action = () -> {
                builder.append("!");
                System.out.println("captured=" + builder);
            };
        }

        action.run();
        action.run();
    }
}
~~~

Run:

~~~bash
javac --release 17 LambdaCaptureDemo.java
java LambdaCaptureDemo
~~~

Stdout:

~~~text
captured=A!
captured=A!!
~~~

A callback stored in a registry/listener/timer can retain the entire graph of objects it captures after the registering method has returned.

## 13. Inner Classes, Listeners, Event Buses, and Closure Retention

A **non-static inner class** has an enclosing instance according to Java semantics. Retaining the inner object can retain the outer object, especially when inner methods need outer state.

A listener added to a long-lived EventBus can retain references through captured values:

~~~text
EventBus ──listeners──► Listener / lambda ──capture──► Session
~~~

Even when the local Session variable has gone out of scope, the graph may still be reachable. That retention is **intentional** if the session still needs events, but it can be a logical memory leak if the session has expired and the listener is not unsubscribed.

**How to avoid it:**
- `subscribe` should return a handle/token; use `removeListener`/`unsubscribe`.
- Do not capture an entire large Controller when only a small immutable ID is needed.
- A static nested class does not implicitly have an enclosing instance, so it is suitable when outer state is not needed.
- If using a weak listener strategy, you must still understand the lifecycle/reference paths; WeakReference does not automatically solve every leak.

### 13.1. Program 11 — A Listener Remains After the Local Goes Out of Scope

Save **`ListenerRetentionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerRetentionDemo {
    interface Listener {
        String event();
    }

    static class EventBus {
        private final List<Listener> listeners = new ArrayList<>();

        void subscribe(Listener listener) {
            listeners.add(listener);
        }

        int size() {
            return listeners.size();
        }

        String firstEvent() {
            return listeners.get(0).event();
        }
    }

    static void register(EventBus bus) {
        StringBuilder state = new StringBuilder("session");
        bus.subscribe(() -> state.toString());
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        register(bus);
        System.out.println("listeners=" + bus.size());
        System.out.println("event=" + bus.firstEvent());
    }
}
~~~

Run:

~~~bash
javac --release 17 ListenerRetentionDemo.java
java ListenerRetentionDemo
~~~

Stdout:

~~~text
listeners=1
event=session
~~~

## 14. Task Queues/Executors Also Retain Object References

If a Runnable captures a Payload and sits in an executor's queue:

~~~text
executor ──► queue ──► Runnable ──► captured payload
~~~

then the fact that the method creating the Runnable has finished does not cause the captured payload to lose accessibility. Live threads can retain objects currently in use through their own stack frames/locals.

`Future.cancel`/executor shutdown must not be interpreted as "every captured object is immediately GC'd": the task might still be running, still in the queue, or the application might hold Future/result references. You need to understand the concrete lifecycle.

### 14.1. Program 12 — Deferred Action

Save **`DeferredTaskDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.Queue;

public class DeferredTaskDemo {
    static final Queue<Runnable> TASKS = new ArrayDeque<>();

    static void schedule() {
        StringBuilder payload = new StringBuilder("job");
        TASKS.add(() -> System.out.println("task=" + payload));
    }

    public static void main(String[] args) {
        schedule();
        System.out.println("queued=" + TASKS.size());

        Runnable action = TASKS.remove();
        action.run();

        System.out.println("remaining=" + TASKS.size());
    }
}
~~~

Run:

~~~bash
javac --release 17 DeferredTaskDemo.java
java DeferredTaskDemo
~~~

Stdout:

~~~text
queued=1
task=job
remaining=0
~~~

Removing from the queue eliminates one retaining path, but `action` still holds the Runnable at the time it runs. Do not infer GC timing from those operations.

## 15. Reference Graph, GC Roots, and "Through Which Path Is It Still Reachable?"

An object can be retained indirectly:

~~~text
Root / live service
       |
       v
   Cache Map
       |
       +──► UserSession
                  |
                  +──► Events List
                  |      |
                  |      +──► Event
                  |
                  +──► byte[] Buffer
~~~

To know whether Event or Buffer is still accessible, you must find a path from live computation/GC roots through Map/Session/List. Do not just check whether a local variable that once created it has gone out of scope.

The JVM collector defines appropriate GC roots from thread/VM/class references and traverses references. Enumeration details may depend on the implementation; do not treat every local name in scope as a root that must live until the end of the block.

### 15.1. A Static Field Is Not Necessarily "Immortal" in Every JVM

A class can be unloaded when classloader/VM liveness permits. However, in an application server, static caches and classloader retention can still keep a graph alive longer than intended. Design eviction/cleanup around lifecycle rather than relying on absolute statements about static fields.

## 16. Reference Cycles Do Not Force Objects to Live Forever

Two objects A and B can reference each other:

~~~text
A ──next──► B
▲           |
└───────────┘
~~~

If a root path to A or B still exists, the entire cycle is reachable. If no path from roots/live computations to the cycle remains, the entire graph can be reclaimed.

Java tracing garbage collection is not simply "counting incoming references"; if objects are only referenced by each other but are no longer reachable from roots, they do not become immortal on their own.

### 16.1. Program 13 — Cycle and Cleared Locals

Save **`ReferenceCycleDemo.java`**:

~~~java
public class ReferenceCycleDemo {
    static class Node {
        final String label;
        Node next;

        Node(String label) {
            this.label = label;
        }
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;

        System.out.println("cycle=" +
                a.next.next.label + "/" + b.next.next.label);

        a = null;
        b = null;

        System.out.println("locals cleared=" +
                (a == null && b == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 ReferenceCycleDemo.java
java ReferenceCycleDemo
~~~

Stdout:

~~~text
cycle=A/B
locals cleared=true
~~~

The result only demonstrates that the locals are null. It is not a measurement that the collector has reclaimed A/B. If another static field holds A, the entire cycle may still be reachable.

## 17. WeakReference and the Non-Determinism of GC Timing

`java.lang.ref.WeakReference<T>` is a reference object that does not keep its referent **strongly reachable** merely because the WeakReference exists.

~~~java
Object strong = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(strong);
~~~

When no strong reachability path to the referent remains, the GC may clear the weak reference, at which point `weak.get()` returns null. **There is no guarantee on when that happens**.

Do not write a test:

~~~java
// strong = null;
// System.gc();
// System.out.println(weak.get() == null);
// Cannot promise a fixed true/false output.
~~~

`System.gc()` only requests/hints to the collector; it does not confirm which objects have been reclaimed. `WeakHashMap` also does not cause every key/object to be collected if other strong paths exist, especially when the value itself retains the key.

### 17.1. Program 14 — WeakReference with Deterministic Stdout

Save **`WeakReferenceBasicsDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceBasicsDemo {
    static class Payload {
        final String value;

        Payload(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Payload strong = new Payload("ready");
        WeakReference<Payload> weak = new WeakReference<>(strong);

        boolean same = weak.get() == strong;
        System.out.println("same while strong used=" + same);
        System.out.println("value=" + strong.value);

        Reference.reachabilityFence(strong);
        strong = null;

        System.out.println("strong cleared=" + (strong == null));
        System.out.println("GC outcome not asserted");
    }
}
~~~

Run:

~~~bash
javac --release 17 WeakReferenceBasicsDemo.java
java WeakReferenceBasicsDemo
~~~

Stdout:

~~~text
same while strong used=true
value=ready
strong cleared=true
GC outcome not asserted
~~~

When comparing `weak.get() == strong`, the strong reference is used in the expression, so the referent is strongly reachable, allowing the identity comparison to be accurate. `Reference.reachabilityFence` specifies a point up to which strong reachability is guaranteed. The example does not measure the timing of weak.get() after strong=null.

## 18. `Reference.reachabilityFence` and `System.gc()` Do Not Serve the Same Purpose

- `Reference.reachabilityFence(obj)`: guarantees the object remains strongly reachable up to the call point, especially useful when a native/external resource operation needs the owning Java object to stay reachable.
- `System.gc()`: hints to the JVM to perform garbage collection. Does not guarantee that a specific object will be collected.
- `obj=null`: reassigns a variable/field reference.
- `close()`: releases an external resource according to its API contract.
- Exiting `try-with-resources`: the Java language guarantees closing according to control flow, not via GC.

Do not use reachabilityFence to artificially keep objects alive unnecessarily long; and do not use System.gc as a substitute for evict/remove/close.

## 19. Resource Lifetime Differs from Object Lifetime

A Java object may manage a file descriptor, socket, database connection, or native handle. When a local reference goes out of scope, GC is not required to close the resource immediately. Finalization is deprecated and should not be used as a cleanup mechanism.

`AutoCloseable` and try-with-resources determine when `close()` is called according to program control flow.

### 19.1. Program 15 — Deterministic Close, Unrelated to GC

Save **`ResourceScopeDemo.java`**:

~~~java
public class ResourceScopeDemo {
    static class Resource implements AutoCloseable {
        final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("opened=" + name);
        }

        void use() {
            System.out.println("used=" + name);
        }

        @Override
        public void close() {
            System.out.println("closed=" + name);
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource("R")) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Run:

~~~bash
javac --release 17 ResourceScopeDemo.java
java ResourceScopeDemo
~~~

Stdout:

~~~text
opened=R
used=R
closed=R
after try
~~~

`closed=R` is the result of try-with-resources. The Resource Java object may still be reachable or not yet reclaimed afterward, but the logical resource is closed on time.

## 20. Access Modifiers and GC Reachability Are Independent

`private` is a Java access-control modifier; it does not turn a field reference into a weak reference. `final` restricts reassignment under source rules; it does not make the referenced object deeply immutable or immortal.

~~~java
class Holder {
    private final Object payload;

    Holder(Object payload) {
        this.payload = payload;
    }
}
~~~

A reachable Holder has a field reference to payload; the path exists even though the caller is not permitted to write `holder.payload` directly.

### 20.1. Program 16 — A Private Field Retains Payload

Save **`PrivateFieldDemo.java`**:

~~~java
public class PrivateFieldDemo {
    static class Payload {
        final String name;

        Payload(String name) {
            this.name = name;
        }
    }

    static class Holder {
        private final Payload payload;

        Holder(Payload payload) {
            this.payload = payload;
        }

        Payload payload() {
            return payload;
        }
    }

    static Holder create() {
        Payload local = new Payload("kept");
        return new Holder(local);
    }

    public static void main(String[] args) {
        Holder holder = create();

        System.out.println("payload=" + holder.payload().name);
        System.out.println("present=" + (holder.payload() != null));
    }
}
~~~

Run:

~~~bash
javac --release 17 PrivateFieldDemo.java
java PrivateFieldDemo
~~~

Stdout:

~~~text
payload=kept
present=true
~~~

`local` goes out of scope when create() returns, yet Holder retains payload through its private field.

## 21. Logical Memory Leaks in a Language with GC

An object is properly kept alive by GC while strong paths remain, yet the application may retain it **much longer than needed**. For example, a static Map keeps a UserSession after the user logs out; GC cannot reclaim a graph still held by the map.

Sources:
- Unbounded static Map/List cache without eviction.
- Listeners that are not unregistered.
- ThreadLocal per-request values in pooled threads that are not removed.
- Lambdas retaining an overly large controller/context graph.
- Queued tasks retaining payloads and results.
- Cyclic graphs that still have a root path from a static registry.
- Strong values in a WeakHashMap retaining keys in reverse.
- Long-lived application singletons holding request-scoped fields.

Generally sound solutions:
- Remove/evict expired entries; bounded cache + TTL.
- Return and close subscription handles.
- `ThreadLocal.remove()` in `finally`.
- Shutdown/cancel executors according to their lifecycle.
- Do not capture unnecessary objects.
- Use heap dumps/retaining paths to identify what retains an object.
- Do not try to "fix a leak" with `System.gc()` if the graph is still strongly reachable.

### 21.1. Program 17 — A Static Registry Retains Session Beyond Method Return

Save **`RegistryRetentionDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RegistryRetentionDemo {
    static class Session {
        final String id;

        Session(String id) {
            this.id = id;
        }
    }

    static class Registry {
        private static final Map<String, Session> SESSIONS =
                new HashMap<>();

        static void keep(Session session) {
            SESSIONS.put(session.id, session);
        }

        static Session find(String id) {
            return SESSIONS.get(id);
        }

        static void remove(String id) {
            SESSIONS.remove(id);
        }

        static int size() {
            return SESSIONS.size();
        }
    }

    static void register() {
        Session local = new Session("S1");
        Registry.keep(local);
    }

    public static void main(String[] args) {
        register();

        System.out.println("size after add=" + Registry.size());
        System.out.println("found=" + Registry.find("S1").id);

        Registry.remove("S1");
        System.out.println("size after remove=" + Registry.size());
        System.out.println("lookup now=" +
                (Registry.find("S1") == null));
    }
}
~~~

Run:

~~~bash
javac --release 17 RegistryRetentionDemo.java
java RegistryRetentionDemo
~~~

Stdout:

~~~text
size after add=1
found=S1
size after remove=0
lookup now=true
~~~

The Session local in register() has gone out of scope before println, yet the static registry still holds the reference. After remove, the registry drops its reference; **this does not assert that the GC has reclaimed Session**.

## 22. Programs Without a Local Variable Still Have Object Semantics

~~~java
System.out.println(new StringBuilder("hello").length());
~~~

There is no named local reference to the StringBuilder, yet the expression has Java object semantics. The JIT may perform scalar replacement/escape analysis and avoid a physical allocation when valid; there is also no guarantee it is reclaimed immediately after `;`.

**Important:** The Java source abstraction and the optimized runtime representation do not necessarily map one-to-one with every physical heap allocation.

## 23. Statement Reachability Is a Completely Different Concept

Java compile-time analysis also uses the term **unreachable statement** (JLS `14.22):

~~~java
static void f() {
    return;
    // System.out.println("never"); // If uncommented: unreachable.
}
~~~

This is control-flow reachability of a statement, **not** object reachability from GC roots. Do not use an unreachable statement error to infer that an object has been collected.

Similarly, a shadowed variable or a private field says nothing about GC. An immutable String does not by itself make an object strongly reachable any longer; string literals/interning have their own sharing behavior and do not generalize well to all object identities.

## 24. Scenario Comparison

| Scenario | About variable/scope | About object reachability | Do we know GC has run? |
| --- | --- | --- | --- |
| Local in a block then `}` | Name exits lexical scope | An alias/field/return may still remain | **No** |
| `b=a; a=null` | a changes reference | b can still retain the object | No |
| Method `return local` | local is not in caller scope | caller holds the reference | No |
| `holder.field=local` | local may go out of scope | reachable holder retains the object | No |
| `list.add(local)` | local may go out of scope | list element holds the reference | No |
| `staticField=local` | local may go out of scope | static path may retain it long-term | No |
| Lambda captures local | name goes out of scope | callback retains captured value | No |
| `local=null` | name may still be in scope | depends on aliases and future uses | No |
| Cycle A→B→A, no root path | not decisive | cycle can be unreachable | No |
| WeakReference only | unrelated to local name | GC may clear it | No |
| Last use before `}` | name is still in scope | JVM may reduce liveness | No |
| `try-with-resources` exits block | local leaves scope | wrapper may still be alive | **close()** via control flow |

## 25. Common Misconceptions Table

| Misinterpretation | What Is Correct |
| --- | --- |
| "Out of scope ⇒ object is destroyed immediately." | The lexical name goes out of scope; the object may still have references or not be GC'd yet. |
| "The reference variable is the object itself." | The variable holds a reference value; the object is a separate entity. |
| "Assigning null deletes all objects." | It only changes one reference; other aliases still remain. |
| "Method return ⇒ every object in the method dies." | Return values/fields/collections/callbacks can retain objects. |
| "Having a local name in scope ⇒ GC must keep the referent until }." | The JIT can shorten liveness based on last use. |
| "Every static field unconditionally lives until JVM exit." | Classloader/class unloading can affect it. |
| "Private fields do not retain objects because callers cannot see them." | Java source accessibility is not reachability. |
| "Reference cycles definitely cannot be GC'd." | Unreachable cycles are still collectible. |
| "System.gc() forces weak references to become null." | There is no timing guarantee. |
| "Finalizers are used to measure GC/close files on time." | Finalization is deprecated and unreliable. |
| "A locally created listener disappears automatically after registration." | The registry can retain the callback/captured data. |
| "Closing a resource is equivalent to the heap object being reclaimed." | Resource lifecycle differs from GC. |
| "An unreachable statement means an unreachable object." | Compile-time control flow differs from runtime GC. |
| "Final makes the referent immutable and immortal." | Final only restricts reassigning the field/variable. |

## 26. Reachability Analysis Procedure

For any code snippet with `new` and multiple assignments:

1. Identify the specific **object** being created.
2. Identify the **variables** holding references, without confusing variables with objects.
3. Track aliases and reassignments.
4. Check values returned from methods and caller references.
5. Check owner fields, arrays, lists, maps, and nested object graphs.
6. Check static registries, caches, and classloader/lifecycle.
7. Check lambdas, inner classes, listeners, tasks, futures, and live threads.
8. Look for root paths and edges; do not just look for local variable names.
9. Distinguish cleared references from remaining paths.
10. Consider *last use* / JVM optimizations, and do not treat the lexical end as a GC event.
11. With WeakReference, do not predict when it will be cleared.
12. For external resources, use close/try-with-resources.
13. When investigating a leak, use controlled heap dump/retaining paths/dominator analysis.
14. Write tests that verify deterministic alias/field/collection semantics instead of GC timing.

## 27. Program 18 — Contract Tests Independent of GC

Save **`ReachabilityContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReachabilityContractTest {
    static class Item {
        final String id;

        Item(String id) {
            this.id = id;
        }
    }

    static class Holder {
        Item item;
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static Holder make() {
        Item local = new Item("A");
        Holder holder = new Holder();
        holder.item = local;
        return holder;
    }

    public static void main(String[] args) {
        Holder holder = make();

        check("A".equals(holder.item.id),
                "local object retained in field");

        List<Item> list = new ArrayList<>();
        list.add(holder.item);

        Item alias = holder.item;
        holder.item = null;

        check(list.get(0) == alias, "alias identity");

        list.clear();
        check(list.isEmpty(), "list cleared");
        check("A".equals(alias.id), "alias accessible");

        System.out.println("reachability semantics checks passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 ReachabilityContractTest.java
java ReachabilityContractTest
~~~

Stdout:

~~~text
reachability semantics checks passed
~~~

The check helper runs on its own without depending on `assert`, which is disabled by default without `-ea`. The test does not need GC and only verifies Java alias/reference semantics.

## 28. Exercises and Answers

**Question 1.** When a local reference goes out of scope, what is certain?  
**Answer:** The local name cannot be used outside the scope. It is unknown whether the object has been GC'd.

**Question 2.** Does `Object b=a; a=null;` cause the old referent to die yet?  
**Answer:** No; b still holds the reference.

**Question 3.** If a method executes `return local;`, can the caller use the object?  
**Answer:** Yes, through the returned reference.

**Question 4.** Does `private Object payload` make payload unreachable to the GC?  
**Answer:** No; access control is independent of reference paths.

**Question 5.** Does `list.clear()` immediately delete objects from the heap?  
**Answer:** No, it only removes elements from the List; there are still aliases and GC timing to consider.

**Question 6.** Can a `static Map` retain sessions for too long?  
**Answer:** Yes; eviction/removal according to lifecycle is needed.

**Question 7.** Does Java force all cycles A↔B to live forever?  
**Answer:** No; cycles unreachable from roots can be reclaimed.

**Question 8.** Does `System.gc()` guarantee that WeakReference returns null?  
**Answer:** No.

**Question 9.** If a local is still in scope but has no future use, can its liveness end early?  
**Answer:** Yes, the JVM/JIT can optimize it according to the JLS.

**Question 10.** What is `Reference.reachabilityFence` used for?  
**Answer:** To preserve strong reachability up to a specific program point.

**Question 11.** Does exiting a `try-with-resources` block force GC to run?  
**Answer:** No; Java calls close according to control-flow rules.

**Question 12.** Can a lambda retained after a block access its captured object?  
**Answer:** Yes.

**Question 13.** Does assigning a parameter reference = null make the caller variable null?  
**Answer:** No; Java is pass-by-value.

**Question 14.** Does `final StringBuilder b` prevent appending?  
**Answer:** No; final restricts reassigning the reference.

**Question 15.** If a program does not declare a local name for `new Object()`, do object semantics still exist?  
**Answer:** Yes; the JVM may optimize physical allocation, but it must preserve behavior.

**Question 16.** Does "Unreachable statement" mean the object has been GC'd?  
**Answer:** No; statement reachability is a compile-time analysis.

**Question 17.** Can you state the exact source line at which an object is reclaimed?  
**Answer:** There is no such general guarantee.

**Question 18.** When a memory leak is caused by a static registry, what should you do?  
**Answer:** Identify the retaining paths and release entries according to their lifecycle; GC cannot collect an object that still has a strong path.

## 29. Knowledge and Code Review Checklist

- [ ] Know how to separate variable name scope and heap object reachability?
- [ ] Know that aliases after `x=null` can still retain the object?
- [ ] Consider return values, owner fields, lists, arrays, and static maps?
- [ ] Consider lambdas, listeners, inner classes, queued tasks, and live threads?
- [ ] Avoid treating lexical `}` as a GC trigger?
- [ ] Avoid assuming a local still in scope forces the referent to live until the end of the block?
- [ ] Understand that the JVM can shorten liveness after last use?
- [ ] Avoid using finalizers/System.gc for deterministic tests?
- [ ] Understand that WeakReference clearing timing is not guaranteed?
- [ ] Recognize unreachable cycles?
- [ ] Distinguish private/final modifiers from strong reference retention?
- [ ] Distinguish resource close from heap reclamation?
- [ ] Verify whether caches/listeners are removed/unsubscribed when their lifecycle ends?
- [ ] Check ThreadLocal cleanup in pooled threads?
- [ ] Limit the size/lifetime of static caches?
- [ ] Use a heap profiler when needed to inspect retaining paths?
- [ ] Verify that demos compile cleanly on Java 17+ and produce deterministic stdout?
- [ ] Avoid making claims about GC timing that are not in the Java spec?

## 30. References

- [Java Language Specification SE 17, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): lexical scope of declarations/locals.
- [JLS SE 17, `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): local declarations and rules.
- [JLS SE 17, `12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): creating object instances.
- [JLS SE 17, `12.6.1 — Implementing Finalization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1): object reachability and compiler optimizations that can shorten the liveness of references.
- [JLS SE 17, `14.22 — Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.22): statement reachability is not GC reachability.
- [Java SE 17 java.lang.ref Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): weak/soft/phantom references.
- [Java SE 17 Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): explicit strong reachability up to a point.
- [Java SE 17 WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability and get().
- [Java SE 17 System.gc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): explicit collection request limitations.
- [Java SE 17 AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource cleanup.
- [JLS SE 17, `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource lifecycle.
- [Oracle JDK 17 GC Tuning — Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): reachability/finalization/explicit GC concerns.

## Conclusion

**Variable scope** is a rule about names in source code. **Object reachability** is a runtime relationship: which reference paths from continuing computations/roots still allow accessing the object.

A local variable going out of scope does **not** cause the object to be destroyed immediately: return values, fields, collections, callbacks, threads, and static registries can retain the object. Conversely, a local name remaining in scope does **not** force the JVM to keep the referent until the end of the block if it is no longer needed for future use and valid optimizations shorten liveness.

Do not conclude that an object has been GC'd upon assigning null, exiting a method, or calling System.gc. If an object no longer has strong paths, it **can** be processed by the collector at an indeterminate time. For logical retention, solve it through **reference ownership and lifecycle** (`remove`, `unsubscribe`, bounded cache, `close`); for testing, test **deterministic Java reference semantics**, not GC timing.
