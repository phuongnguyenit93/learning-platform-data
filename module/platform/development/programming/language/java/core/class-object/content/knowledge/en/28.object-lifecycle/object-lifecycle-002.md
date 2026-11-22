# Local Variables, Fields, and Reference Paths That Keep Objects Alive — Java 17

## Objectives

When writing Java, we create objects with `new`, store references in local variables, instance fields, static fields, array elements, or collections, and then pass those references through method calls. To understand the **object lifecycle**, what matters is not merely which variables are declared, but **whether any reference path still leads from an active context to the object**.

An object is **reachable** if the program can still access it along appropriate reference paths. The garbage collector (GC) can reclaim the memory of objects that are **no longer reachable under the rules of the JVM/Java Memory Model**, but when reclamation occurs is a runtime decision: **Java does not guarantee that exiting a block, setting a variable to `null`, or calling `System.gc()` will immediately collect an object**.

This lesson belongs to **Java Core — Class/Object — Object Lifecycle**, using Java 17, focusing on:

- Distinguishing between **object**, **reference variable**, **reference value**, and **reference path**.
- Understanding the different effects of **local variables**, **instance fields**, **static fields**, **array elements**, **collections**, **closures/lambdas**, **inner classes**, and **ThreadLocal** on reachability.
- Reading a **reference graph** starting from **GC roots**; determining when an object still has a strong path and when it can become unreachable.
- Distinguishing between **how long a variable name is in effect (scope)**, **when a reference is live (liveness)**, **when an object is eligible for collection**, **when GC actually collects it**, and **resource lifecycle**.
- Identifying **memory leaks in the Java sense**: objects that remain reachable even though the program no longer needs them.
- Using `WeakReference`, `ReferenceQueue`, `WeakHashMap`, `Reference.reachabilityFence`, and `AutoCloseable` properly when appropriate, without turning GC into the primary cleanup mechanism.
- Practicing reading scenarios involving aliases, reassignment, cycles, object graphs, listener registration, caches, and thread pools.

The programs have individual file names, `javac --release 17`/`java` commands, and deterministic stdout; statements about GC timing are stated with appropriate caveats.

## 1. An Object Is Not Synonymous with a Reference Variable

Consider:

```java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;
```

There is **one `StringBuilder` object** created. The two local variables `first` and `second` hold **two reference values** pointing to that same object.

`first` and `second` are not two "object copies". The assignment `second = first` copies the reference value; it does not call a constructor or clone.

Graph:

```text
Local variable first  ─┐
                       ├──▶ StringBuilder("A")
Local variable second ─┘
```

If `first = null;`, the reference path from `first` disappears, **but `second` still points to the object**. You cannot conclude that an object is no longer reachable solely from one variable becoming null.

### Definitions to Keep Separate

- **Object**: a runtime entity with identity/state/behavior.
- **Variable**: a typed storage location for a value; with a reference type, the value is usually a reference or null.
- **Reference**: a value that helps refer to an object (or null).
- **Alias**: multiple references pointing to the same object.
- **Reference graph**: objects/roots are nodes; references form the edges.
- **Reachability**: whether or not a valid path exists from an accessible source to an object, with the corresponding reference types and JVM rules.

## 2. Runnable: Two Local References Keeping One Object Alive

Save **`LocalAliasesDemo.java`**:

```java
public class LocalAliasesDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("Java");
        StringBuilder second = first;

        System.out.println(first == second);
        first = null;

        second.append(" 17");

        System.out.println(second);
        System.out.println(first == null);
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 LocalAliasesDemo.java
java LocalAliasesDemo
```

Stdout:

```text
true
Java 17
true
```

Setting `first = null` only changes **the value of one local variable**. It does not delete the object and does not invalidate the alias `second`.

## 3. What Does "Keeping an Object Alive" Mean Exactly?

In practical terms, a usable **strong reference** path from a **GC root** is the reason the GC does not treat the target object as garbage. However, two levels should be distinguished:

1. **Reasoning model:** a live root points to object A; A has a field pointing to B; B has a field pointing to C. While the path root → A → B → C remains, C remains strongly reachable.
2. **JVM implementation:** the compiler/JIT and collector determine liveness/roots at appropriate points and may optimize variables and allocation. A variable remaining in lexical scope **does not automatically force** the object to stay alive until the end of the block.

In other words, **the scope of a variable name is not a countdown timer for GC**.

### Common Execution-Time GC Roots

Depending on the collector and observation point, places considered as roots may include:
- References that are still **live** in the stack frames/registers of active threads.
- Certain references from the static state of live classes.
- Runtime/JNI/native handles and special structures managed by the JVM.
- References needed for subsequent execution.

Not every local variable ever declared or every static field that has ever existed is a **permanent root**. An instance field **is not a root by itself**: it only adds an edge if the object owning that field is already reachable.

## 4. Reading a Reference Path from a Root to an Object

Suppose:

```text
[GC root: live local variable]
             │
             ▼
          Session
             │ user
             ▼
            User
             │ cart
             ▼
         ShoppingCart
             │ items
             ▼
         ArrayList
             │ element[0]
             ▼
          CartItem
```

If a live local reference points to Session, and the instance fields/collection elements are held as shown, then CartItem has a **strong reference path** from the root.

If Session is no longer reachable along any strong root/path, the entire graph may no longer be strongly reachable, except for other paths (such as another static cache holding User or CartItem).

### Important Rule

There does not need to be **a direct local variable** pointing to CartItem. An indirect path through multiple fields and collection elements can still keep CartItem reachable.

## 5. Local Variables: Declaration Location and Lifetime

A *local variable* is declared in a method, constructor, block, `for`, or other appropriate scopes:

```java
void process() {
    Object item = new Object();
    use(item);
}
```

When `process()` is called, the reference `item` can be a root-reachable reference for as long as it is still needed for execution. After the method returns, with the caller neither receiving nor storing item elsewhere, that local reference path no longer exists.

However:
- There is no rule that "after `}`, the JVM immediately calls GC".
- An object can become unnecessary **before** `}` if there are no remaining uses affecting execution and the runtime can prove liveness appropriately.
- A reference can *escape* via a return, field, collection, or callback, causing the object to live longer than the method call.
- The JVM may optimize allocation; one should not assert that a heap object is always actually materialized for every `new`.

**Scope determines where you may use a local name. Reachability determines along which live paths an object can still be accessed.** The two concepts are related but not identical.

## 6. Runnable: A Block Scope Does Not Determine GC

Save **`LocalScopeDemo.java`**:

```java
public class LocalScopeDemo {
    public static void main(String[] args) {
        StringBuilder retained;

        {
            StringBuilder temporary = new StringBuilder("data");
            retained = temporary;
        }

        System.out.println(retained);
        retained.append("-kept");
        System.out.println(retained);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LocalScopeDemo.java
java LocalScopeDemo
```

Stdout:

```text
data
data-kept
```

The name `temporary` goes out of scope when leaving the block, but the object remains accessible via `retained`. A variable's scope **does not constrain the object's lifetime** once the reference has been copied elsewhere.

## 7. Reassignment Only Changes One Edge

```java
Node a = new Node("A");
Node b = new Node("B");

a = b;
```

After the last line, reference variable `a` also points to object B. The original object A **may** lose the path from `a`, but whether it remains reachable depends on whether another path points to A.

Idealized graph:

```text
Before:
a ──▶ [A]
b ──▶ [B]

After a = b:
a ──┐
    ├──▶ [B]
b ──┘
[A] no longer has an edge from these two locals.
```

There is no corresponding `delete A` command in Java. The GC tracks reachability on its own; it is not identical to assignment.

### Setting `null` Is Also Reassignment

`a = null;` does not call a destructor on the old target object. It only removes the reference edge from one storage location; other references may keep the object alive.

## 8. Runnable: Reassignment Does Not Destroy Aliases

Save **`ReferenceReassignmentDemo.java`**:

```java
final class Item {
    final String id;

    Item(String id) {
        this.id = id;
    }
}

public class ReferenceReassignmentDemo {
    public static void main(String[] args) {
        Item original = new Item("old");
        Item alias = original;
        Item replacement = new Item("new");

        original = replacement;

        System.out.println(original.id);
        System.out.println(alias.id);
        System.out.println(original == alias);
        System.out.println(original == replacement);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
```

Stdout:

```text
new
old
false
true
```

Even though `original` is repointed, the old object still has the reference `alias` in the part of the program that still uses it.

## 9. Java Passes Parameters by Value — The Value Can Be a Reference

When calling:

```java
change(object);
```

Java passes **a copy of the reference value** into the parameter. This is *pass-by-value*, not "pass-by-reference" in the sense that a function can directly change the reference variable in the caller.

Consequences:
- The method can **mutate the object** through the reference (if the object/method allows it).
- The method **cannot reassign the caller's local variable itself** simply by reassigning the formal parameter.
- If the method stores the reference in a field/static/list, the object can escape beyond the caller's lifetime.

### Two Operations to Compare

```java
void replace(StringBuilder p) {
    p = new StringBuilder("new");
}

void change(StringBuilder p) {
    p.append("!");
}
```

`replace` changes the local parameter; `change` modifies the state of the shared object.

## 10. Runnable: Assigning to a Parameter vs. Modifying an Object

Save **`ParameterReferenceDemo.java`**:

```java
public class ParameterReferenceDemo {
    static void replace(StringBuilder value) {
        value = new StringBuilder("replaced");
    }

    static void mutate(StringBuilder value) {
        value.append("!");
    }

    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("hello");

        replace(text);
        System.out.println(text);

        mutate(text);
        System.out.println(text);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ParameterReferenceDemo.java
java ParameterReferenceDemo
```

Stdout:

```text
hello
hello!
```

In `replace`, a new object is created, but the new reference **does not escape the method**; that differs from `mutate`, which acts on the exact object the caller still holds.

## 11. *Instance Fields* Create Edges That Persist Beyond a Method

An instance field resides inside its owning object:

```java
final class Profile {
    Address address;
}
```

When a reachable `Profile` has an `address` field pointing to `Address`, the path:

```text
root → Profile → address → Address
```

can keep Address strongly reachable.

An instance field **is not a root by itself**. The primary condition is whether the owner object Profile is reachable, and there may also be other edges pointing to Address.

### Field Assignment Changes the Graph

`profile.address = replacement;` replaces the edge from Profile to the new Address. The old Address is not necessarily collected if another variable still holds it.

`profile.address = null;` removes an edge. It does not necessarily make the old Address unreachable if another map/cache/owner still holds it.

## 12. Runnable: A Local Only Holds the Owner, the Owner Field Holds the Child

Save **`InstanceFieldGraphDemo.java`**:

```java
final class Address {
    final String city;

    Address(String city) {
        this.city = city;
    }
}

final class User {
    final String name;
    Address address;

    User(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}

public class InstanceFieldGraphDemo {
    public static void main(String[] args) {
        Address first = new Address("Hanoi");
        User user = new User("An", first);

        first = null;

        System.out.println(user.name);
        System.out.println(user.address.city);

        user.address = new Address("Hue");
        System.out.println(user.address.city);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InstanceFieldGraphDemo.java
java InstanceFieldGraphDemo
```

Stdout:

```text
An
Hanoi
Hue
```

After `first = null`, the owner `user` still holds Address("Hanoi") via its field. After changing the field, the old Address object may no longer have a path from this graph, **but there is no proof of GC timing**.

## 13. Field Chain: Long Paths Are Normal

Suppose:

```java
company.department.manager.address.city
```

The expression accesses multiple fields. If `company` is a usable reference and each field points to an appropriate object, then reading `city` traverses multiple **edges** in the graph.

A diagram:

```text
live root
  └──▶ company
           └── department ──▶ Department
                                └── manager ──▶ Manager
                                                 └── address ──▶ Address
```

When you need to explain memory retention:
1. Identify the object being retained (for example, Address).
2. Find all **incoming strong edges** to it.
3. Trace back to the GC root keeping the graph alive.
4. Determine which edge should have been removed when the business operation ended.

An object can have **multiple independent paths**. Removing one path is not enough if another path still connects a root to the object.

## 14. An Array Is a Set of Slots Holding References

With an array of references:

```java
Object[] slots = new Object[3];
Object value = new Object();
slots[0] = value;
```

The array `slots` is an object. The element `slots[0]` is a slot holding a reference to `value`.

If a root still holds the array:
- `slots[0]` is an edge holding the target object.
- `value = null;` only drops the local edge; the array still holds it.
- `slots[0] = null;` removes the edge from the array.
- A primitive array such as `int[]` stores primitive values, not references to `Integer` objects for each element.

Especially with long arrays, a single element holding a reference to a bulky object can unintentionally keep a large object graph reachable.

## 15. Runnable: An Array Element Holds an Object

Save **`ArrayReferenceDemo.java`**:

```java
public class ArrayReferenceDemo {
    public static void main(String[] args) {
        StringBuilder[] slots = new StringBuilder[2];

        StringBuilder value = new StringBuilder("kept");
        slots[0] = value;

        value = null;

        System.out.println(slots[0]);
        System.out.println(slots[1] == null);

        slots[0] = null;
        System.out.println(slots[0] == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ArrayReferenceDemo.java
java ArrayReferenceDemo
```

Stdout:

```text
kept
true
true
```

This is a **reference graph** demo, not proof that GC ran when `slots[0] = null`.

## 16. Collections Hold References to Elements

A collection such as `ArrayList<Customer>`, `HashSet<Customer>`, or `HashMap<Key,Value>` can store those references inside its internal structure.

Example:

```java
List<Order> orders = new ArrayList<>();
Order order = new Order(...);
orders.add(order);
order = null;
```

If `orders` remains reachable, then `Order` still has a strong reference path through the collection.

### Operations That Change Retention Paths

- `list.remove(element)` or `list.clear()` removes the references held by the list to the appropriate entries.
- `map.remove(key)` or `map.clear()` removes the map's mappings/references.
- `set.remove(element)` removes the corresponding entry.
- **Aliases elsewhere** still need to be considered.
- `clear` does not trigger GC immediately; it only changes the graph/collection state.
- A collection also typically still has its own live internal backing arrays/buckets as part of the collection object; capacity does not mean old element references remain held after clearing under the appropriate contract.

### Maps Hold Both Keys and Values

In a regular `HashMap<K,V>`, when the map object is reachable, it holds **strong references** to both keys and values. A single value can in turn hold many objects beneath it.

## 17. Runnable: A List Retains an Object After the Local Changes

Save **`ListRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> values = new ArrayList<>();

        StringBuilder original = new StringBuilder("saved");
        values.add(original);

        original = null;

        System.out.println(values.get(0));
        System.out.println(values.size());

        values.clear();

        System.out.println(values.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ListRetentionDemo.java
java ListRetentionDemo
```

Stdout:

```text
saved
1
true
```

After `original = null`, the list still retains the StringBuilder. After `clear()`, the path from the list to the element is removed; this does not assert that the element has been collected by GC.

## 18. Static Field: A Retention Path Spanning Beyond One Method and Multiple Instances

Example:

```java
final class Cache {
    static Object saved;
}
```

If the corresponding class is still considered live by the JVM under class loading/lifetime rules, a static field `Cache.saved` pointing to an object can be a strong reference path retaining that object.

`Cache.saved` does not belong to **a specific Cache instance**. It is state of the class, which can be used by many methods and many objects.

### Scenario That Commonly Causes Leaks

```java
static final List<Session> sessions = new ArrayList<>();
```

`final` only prevents **reassigning the reference field `sessions`**. It **does not** prevent `sessions.add(...)` and does not stop the collection from keeping Session objects longer than necessary.

### Static Is Not Synonymous with Existing Forever

One should not claim that "a static object always lives until the JVM shuts down" in every environment:
- Class loaders/modules and class unloading have their own lifetime rules.
- Objects in static fields can be replaced, removed, or become unreachable when the class/class loader is no longer alive.
- Certain runtime optimizations affect object materialization/liveness.

In a long-running application, **a static cache/list is a root path to investigate first** when retention is suspected, though it must be verified in practice.

## 19. Runnable: A Static Reference Keeps Holding Across Multiple Calls

Save **`StaticReferenceDemo.java`**:

```java
final class SharedCache {
    static StringBuilder saved;

    static void remember(StringBuilder value) {
        saved = value;
    }

    static void clear() {
        saved = null;
    }
}

public class StaticReferenceDemo {
    static void createAndRemember() {
        StringBuilder temporary = new StringBuilder("cached");
        SharedCache.remember(temporary);
    }

    public static void main(String[] args) {
        createAndRemember();

        System.out.println(SharedCache.saved);
        System.out.println(SharedCache.saved != null);

        SharedCache.clear();

        System.out.println(SharedCache.saved == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 StaticReferenceDemo.java
java StaticReferenceDemo
```

Stdout:

```text
cached
true
true
```

The local `temporary` has exited the method, yet the reference was stored in the static field. `clear()` removes **the static cache → object edge**, rather than invoking a destructor.

## 20. Static Field, Instance Field, and Local: Summary Table

| Reference Holder Type | What Does It Belong To? | How Long Can the Reference Path Last? | Typical Mistake |
| --- | --- | --- | --- |
| Local variable | Execution of a method/block | While the reference is still needed for execution | Equating scope with lifetime |
| Formal parameter | A single method/constructor call | Can escape if stored/returned | Thinking reassigning a parameter inside a method changes the caller's variable |
| Instance field | An owner object | While the owner is reachable and the field holds the reference | Thinking the field itself is a GC root |
| Static field | Runtime class state | Can span across multiple methods/instances | Cache without eviction, thinking static always lives forever |
| Array element | Array object | While the array is reachable and the entry still holds a reference | Setting only the local to null while forgetting the array |
| Collection entry | Collection/backing structure | While the collection is reachable and the entry exists | Forgetting to remove a listener/cache/map item |
| Lambda/closure field | Functional object | While the callback/functional object is reachable | Storing a lambda long-term while forgetting the captured object |
| Non-static inner class | Inner instance | Can retain the enclosing instance | Outer unexpectedly retained |
| ThreadLocal mapping | State attached to a thread | According to thread/cleanup rules | Not removing in a thread pool |

This table describes **reference paths**; it does not provide a specific GC schedule.

## 21. A *Reference Cycle* Is Not a Memory Leak by Itself

Two objects holding each other:

```java
Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;
```

Graph:

```text
root → A ──▶ B
       ▲     │
       └─────┘
```

If a root still holds A, both A and B are reachable. If no path remains from roots to A/B, **the cycle A↔B alone is not enough to keep the two objects strongly reachable**.

This differs from some memory management models based solely on simple reference counting. Reachability/tracing garbage collectors in the JVM can collect cyclic object graphs when the graph is unreachable; there is no need to manually "break every cycle" just so the GC can handle it.

**However**, if a static map, long-lived thread, or root object still holds A, the entire cycle remains reachable and can become a leak in the sense of unintended memory usage.

## 22. Runnable: Reading a Reference Cycle

Save **`ReferenceCycleDemo.java`**:

```java
final class Node {
    final String label;
    Node next;

    Node(String label) {
        this.label = label;
    }
}

public class ReferenceCycleDemo {
    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;

        System.out.println(a.next.label);
        System.out.println(b.next.label);
        System.out.println(a.next.next == a);

        a = null;
        System.out.println(b.next.label);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceCycleDemo.java
java ReferenceCycleDemo
```

Stdout:

```text
B
A
true
A
```

After `a = null`, the local `b` still points to B, and B.next points to A. Do not claim the cycle is collected at this point. If all roots/paths to the graph disappear, cyclicity by itself does not prevent GC.

## 23. Two Independent Paths: Removing One Still Leaves the Other

An object can reside in both collections:

```text
root → customersCache ──▶ Customer#42
root → recentCustomers ───▶ Customer#42
```

Removing the entry from `customersCache` **is not enough** if `recentCustomers` still holds the same object.

When analyzing memory retention, ask:
1. How many **incoming strong paths** point to the object?
2. Where does each path start?
3. Does any root path live longer than the expected object lifecycle?
4. Who owns the responsibility to remove/clear the reference?
5. If a fix only cleans up one container, does another container still retain it?

An object can be a key in Map A, a value in Map B, a listener on EventBus, and a field of a singleton service all at the same time.

### Object Identity vs. Key Equality

Map/Set rely on `equals/hashCode` for lookup logic; however, they still store **actual object references** in their entries. Two objects being equal according to `equals` does not mean they are the same object in the memory graph.

## 24. Runnable: Two Containers Retaining the Same Object

Save **`MultipleOwnersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class MultipleOwnersDemo {
    public static void main(String[] args) {
        List<StringBuilder> left = new ArrayList<>();
        List<StringBuilder> right = new ArrayList<>();

        StringBuilder shared = new StringBuilder("shared");

        left.add(shared);
        right.add(shared);

        left.clear();

        System.out.println(right.get(0) == shared);
        System.out.println(right.get(0));

        right.clear();
        System.out.println(right.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MultipleOwnersDemo.java
java MultipleOwnersDemo
```

Stdout:

```text
true
shared
true
```

After left is cleared, right still holds shared. In this program, the local `shared` is also another path; therefore, even clearing both lists does not prove that the object immediately became unreachable.

## 25. A Returned Object Can Outlive the Method That Created It

```java
static StringBuilder make() {
    StringBuilder local = new StringBuilder("created");
    return local;
}
```

Upon returning, the reference is passed to the caller:

```java
StringBuilder result = make();
```

The local `local` disappears after the call, but the caller has `result`. The object **escapes via the return value**.

Conversely, if a method creates an object, uses it only locally, and neither stores nor returns it, after the last point where it is used it can become unreachable (depending on other paths).

### Do Not Interpret Returning as Copying an Object

Java returns the reference value; it does not automatically clone the StringBuilder. If the caller modifies the returned object, the caller is modifying the very same object that the method created.

## 26. Runnable: Return Transfers a Reference Path to the Caller

Save **`ReferenceReturnDemo.java`**:

```java
public class ReferenceReturnDemo {
    static StringBuilder create() {
        StringBuilder local = new StringBuilder("hello");
        return local;
    }

    public static void main(String[] args) {
        StringBuilder returned = create();
        returned.append("-caller");

        System.out.println(returned);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReferenceReturnDemo.java
java ReferenceReturnDemo
```

Stdout:

```text
hello-caller
```

The completion of the `create` method does not end the lifetime of the returned object.

## 27. Lambdas and Captures Can Keep an Object Alive Beyond a Method

A lambda can capture an **effectively final local variable**. If a functional object contains or otherwise retains a reference to the captured object, and the functional object itself is stored long-term, the reference path to the captured object can extend beyond the local scope.

Example:

```java
StringBuilder data = new StringBuilder("A");
Runnable task = () -> System.out.println(data);
```

Even after the method that created the lambda has returned, a caller or registry holding `task` can also retain `data`.

**Two things must be distinguished:**
- A lambda captures a local **reference value**, not "a local variable living on the stack forever".
- The Java compiler/JVM is free to choose lambda implementation details; you should not build logic relying on field names inside a synthetic lambda class.

### Effectively Final

A captured local variable must be final or effectively final. That **does not** make the referenced object immutable.

`StringBuilder` can still be modified through the `append` method. If you try to reassign the captured local variable itself, the compiler rejects it.

## 28. Runnable: A Callback Retains an Object After Method Return

Save **`LambdaCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LambdaCaptureDemo {
    static final List<Runnable> TASKS = new ArrayList<>();

    static void register() {
        StringBuilder message = new StringBuilder("captured");
        TASKS.add(() -> System.out.println(message));
    }

    public static void main(String[] args) {
        register();
        TASKS.get(0).run();

        TASKS.clear();
        System.out.println(TASKS.isEmpty());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 LambdaCaptureDemo.java
java LambdaCaptureDemo
```

Stdout:

```text
captured
true
```

`register` has already returned before `TASKS.get(0).run()`, yet the lambda can still print the message because the callback is held by the registry. `clear` removes the path from TASKS to the callback; GC is not verified by the output here.

## 29. Listener Registration: A Very Common Source of Retention

An owner object registers a callback with a long-lived event bus:

```text
GC root
  └── static EventBus
        └── listeners list
              └── lambda/listener
                    └── captured view/controller
                          └── UI subtree
```

If the screen has closed but the listener remains in the bus, the screen graph may remain reachable.

This is a **memory leak in the application sense**: memory is not reclaimed because the code still retains a reference that it **no longer has any intended use for**.

How to handle it:
- Register and unregister following the same lifecycle: `addListener`/`removeListener`.
- Return a `Registration`/`Subscription` that has `close()`.
- For frameworks with a lifecycle, use the appropriate cleanup API such as `dispose`, `stop`, or `onDestroy` as applicable.
- Weak listeners are an option in some designs, but they do not automatically replace defining the owner lifecycle.
- Do not just call `System.gc()`: the strong path to the listener still exists.

## 30. Runnable: Controlled Listener Registration and Unregistration

Save **`ListenerRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EventBus {
    private final List<Runnable> listeners = new ArrayList<>();

    void subscribe(Runnable listener) {
        listeners.add(listener);
    }

    void unsubscribe(Runnable listener) {
        listeners.remove(listener);
    }

    void fire() {
        for (Runnable listener : listeners) {
            listener.run();
        }
    }

    int count() {
        return listeners.size();
    }
}

public class ListenerRetentionDemo {
    public static void main(String[] args) {
        EventBus bus = new EventBus();
        StringBuilder screen = new StringBuilder("screen");

        Runnable listener = () -> System.out.println(screen);

        bus.subscribe(listener);
        bus.fire();

        System.out.println(bus.count());
        bus.unsubscribe(listener);
        System.out.println(bus.count());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ListenerRetentionDemo.java
java ListenerRetentionDemo
```

Stdout:

```text
screen
1
0
```

Removing the registration deletes a **reference path** from EventBus to the callback. The local variables `listener` and `screen` still exist in main in this example; the act of unsubscribing does not mean immediate GC.

## 31. Non-Static Inner Classes Typically Retain the Enclosing Instance

In Java 17, a **non-static inner class** has an enclosing instance association. If the inner object needs to use members of the outer object, there is clearly a path pointing from the inner instance to the outer instance.

```java
class Outer {
    String name;

    class Inner {
        String label() {
            return name;
        }
    }
}
```

If a long-lived registry holds Inner, it can retain Outer via the enclosing-instance reference/association. This matters when Outer is a controller/activity/window with a large graph.

### Use a Static Nested Class When Outer Is Not Needed

`static class Nested` does not by itself require an enclosing Outer instance. If the nested implementation only needs its own data, a static nested class with a constructor taking the exact dependencies can avoid unintentionally retaining the owner via a reference.

**Do not make overly absolute claims about the shape of synthetic fields**: the compiler/JVM has implementation freedom. What needs to be understood is the source-level enclosing instance design and usage of outer state.

## 32. Runnable: An Inner Object Uses Outer State

Save **`InnerOuterReferenceDemo.java`**:

```java
final class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    class Inner {
        String describe() {
            return "outer:" + Outer.this.label;
        }
    }

    Inner createInner() {
        return new Inner();
    }
}

public class InnerOuterReferenceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("parent");
        Outer.Inner inner = outer.createInner();

        outer = null;

        System.out.println(inner.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InnerOuterReferenceDemo.java
java InnerOuterReferenceDemo
```

Stdout:

```text
outer:parent
```

Even though the local `outer` is assigned null, the inner instance still accesses the outer state through `Outer.this`. This is a clear example of an **indirect** reference path extending beyond the local.

## 33. A Bound Method Reference Can Also Retain Its Receiver

Java method references have two different semantic forms:

```java
Runnable task = object::run;
```

With a **bound instance method reference**, `object` is the receiver evaluated/bound when the method reference is created. The functional object can retain the receiver for use when the callback is invoked later.

Conversely:

```java
Function<Item, String> fn = Item::label;
```

this is an **unbound** instance method reference: the receiver is passed in when calling `fn.apply(item)`. Creating `fn` does not by itself capture a specific Item object.

### When Analyzing Retention

A long-lived scheduler/registry holding `object::onEvent` can indirectly retain the entire graph of the receiver object. You need to unregister/cancel following the proper lifecycle.

## 34. Runnable: A Bound Receiver Remains Used by the Callback

Save **`BoundMethodReferenceDemo.java`**:

```java
final class Printer {
    private final String value;

    Printer(String value) {
        this.value = value;
    }

    void print() {
        System.out.println(value);
    }
}

public class BoundMethodReferenceDemo {
    public static void main(String[] args) {
        Printer printer = new Printer("receiver");
        Runnable callback = printer::print;

        printer = null;
        callback.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BoundMethodReferenceDemo.java
java BoundMethodReferenceDemo
```

Stdout:

```text
receiver
```

`callback` still has the receiver bound from when the method reference was created. It is not that the local `printer` still holds a non-null value.

## 35. `ThreadLocal`: Retention Paths Attached to Long-Lived Threads

`ThreadLocal<T>` lets each thread access a "private" value via thread-local storage. However, when using a **thread pool**, a worker thread can survive long after a single request.

If code:

```java
CURRENT_USER.set(userContext);
```

and then forgets:

```java
CURRENT_USER.remove();
```

the value from the old request may remain attached to the thread being reused. Problems include:
- Context leakage between two requests.
- Retaining references to large object graphs longer than necessary.
- Unpredictable behavior when the next task runs on the same worker thread.
- Class-loader retention in environments with repeated redeployments, depending on the framework.

**Practice:** when a context has a per-task/per-request lifetime, place cleanup in `finally`, not only on the success branch. Note that `ThreadLocal` does not automatically propagate context across other threads.

## 36. Runnable: A Thread Pool Reuses the Value If Not Removed

Save **`ThreadLocalLifecycleDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalLifecycleDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> first = pool.submit(
                    () -> CONTEXT.set("request-A"));
            first.get();

            Future<String> second = pool.submit(CONTEXT::get);
            System.out.println(second.get());

            Future<?> third = pool.submit(CONTEXT::remove);
            third.get();

            Future<String> fourth = pool.submit(CONTEXT::get);
            System.out.println(fourth.get() == null);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
```

Stdout:

```text
request-A
true
```

`newSingleThreadExecutor()` executes tasks sequentially on the same worker thread in this demo, so task 2 reads the context stored by task 1. `remove()` causes task 4 to see null. In production, you typically wrap `set/use/remove` inside **a single task** with `try/finally` to prevent old context from surviving to the next task.

## 37. Runnable: The `try/finally` Pattern for ThreadLocal

Save **`ThreadLocalCleanupDemo.java`**:

```java
public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER =
            new ThreadLocal<>();

    static void runRequest(String name) {
        USER.set(name);
        try {
            System.out.println(USER.get());
        } finally {
            USER.remove();
        }
    }

    public static void main(String[] args) {
        runRequest("An");
        System.out.println(USER.get() == null);

        runRequest("Binh");
        System.out.println(USER.get() == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

Stdout:

```text
An
true
Binh
true
```

This is a cleanup pattern **reliable by control flow**, without needing to speculate on when GC collects objects.

## 38. Why Can a Java Program Still Have a Memory Leak?

In a GC environment, a *leak* is not just "forgetting `free(ptr)`". An object can **still be reachable** even though the software **no longer needs it**.

Examples:
- A static `Map` without eviction.
- A list of listeners that are not unregistered.
- A cache keeping both keys and values forever.
- A ThreadLocal not removed in a thread pool.
- An executor queue containing many pending tasks capturing large graphs.
- A long-lived singleton holding lastRequest/session.
- A non-static inner object outliving the outer's intended lifecycle.
- An array still holding an element that was "logically removed".
- A map value pointing back to its key, creating a trap when using WeakHashMap.

**The GC cannot know on its own which object has lost its business meaning.** If a strong reference path still exists and the program could use it, the collector generally must keep it.

### Distinguishing a Logical Leak from a GC Bug

Before concluding that the JVM is not collecting garbage, look for strong reference paths. If the object is already unreachable yet heap usage does not drop immediately, that is not necessarily a leak: the collector may not have run yet, and the heap may keep pages/reserved capacity for future allocations.

## 39. The Reachability Model and GC Make No Promises About Collection Timing

An easily mistaken statement:

> "Setting a variable to null immediately frees memory."

Not true.

What can be said:
- Assigning `null` removes a reference **at that storage location**.
- If no strong path to the object remains from roots, it can become **eligible for garbage collection** in the appropriate context.
- The JVM decides when to detect and reclaim it.
- The heap remaining allocated/reserved does not prove the object is still live.
- `System.gc()` is a request/hint; it does not guarantee GC completes, nor does it guarantee any specific object is collected.
- A program cannot accurately predict the order or timing of finalization/reclamation.

### Subtle Point: Lexical Scope ≠ Liveness

The variable `obj` may still be in the source block yet no longer used. The JVM/JIT can consider it no longer live at some point before the end of the block, within the limits of the specification.

If the application **truly must keep an object reachable up to a specific point** (for example, a native handle wrapper that must stay alive while native code uses the resource), look at `Reference.reachabilityFence` instead of relying on a variable "still being inside curly braces".

## 40. `WeakReference`: Not a Strong Path

The `java.lang.ref` package provides reference types with special GC semantics.

`WeakReference<T>` does not keep its referent alive via strong reachability like a normal local/field/list does. If no strong reachability remains according to GC rules, the weak reference can be **cleared** and `weak.get()` may return null.

**Do not use `WeakReference` as a storage mechanism for data guaranteed to remain present.** It is suitable for certain caches/registries whose values can be recreated or for carefully designed observation/cleanup techniques.

### What Can Be Reliably Verified in the Example

While a strong reference is explicitly being used in the comparison, the newly created weak reference points to that same object. You must not write tests expecting GC to clear the weak ref immediately after `strong = null`.

## 41. Runnable: A Weak Reference While a Strong Reference Exists

Save **`WeakReferenceDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println(weak.get() == strong);

        Reference.reachabilityFence(strong);
        strong = null;

        // Do not assert weak.get() here:
        // GC may or may not have run.
        System.out.println("no-gc-assumption");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WeakReferenceDemo.java
java WeakReferenceDemo
```

Stdout:

```text
true
no-gc-assumption
```

`WeakReference` is not a strong retention edge. `reachabilityFence` in the example serves as a marker to keep the referent strongly reachable up to the fence, but it does not request GC to run afterward.

## 42. Strong, Soft, Weak, Phantom: Concept Map

| Reference Type | Typical Purpose | Does It Keep the Object Like a Strong Reference? | What Not to Assume |
| --- | --- | --- | --- |
| Strong (regular Java reference) | Fields, locals, arrays, collections | Yes, while a live strong path remains | Scope = absolute lifetime |
| `SoftReference` | Certain memory-sensitive caches | Does not hold like a strong reference; GC has a soft reachability policy | "Values always stay alive until RAM is nearly exhausted" |
| `WeakReference` | Weak keys/listeners/caches that may lose their referent | No | `get()` is always non-null after the local becomes null |
| `PhantomReference` | Tracking post-mortem cleanup together with ReferenceQueue | Does not provide the referent via `get()` | That `get()` can be used to obtain the object |
| `ReferenceQueue` | Receiving information about enqueued refs | Does not schedule cleanup code by itself | Enqueuing occurs at a predictable time |

This is a directional overview. `SoftReference`, `WeakReference`, and `PhantomReference` each have their own GC/queue semantics; consult Java SE 17 `java.lang.ref` when designing advanced caches/cleanup.

**Even when using weak/soft refs, you still need to manage data lifecycle, bounds, and errors**. You should not use reference tricks in place of an explicit eviction policy when a cache is bounded.

## 43. Runnable: `PhantomReference.get()` Does Not Return the Referent

Save **`PhantomReferenceDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object resource = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        PhantomReference<Object> phantom =
                new PhantomReference<>(resource, queue);

        System.out.println(phantom.get() == null);

        Reference.reachabilityFence(resource);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
```

Stdout:

```text
true
```

`PhantomReference.get()` always returns null according to the API contract. The example **does not predict** when enqueuing into the queue occurs or when the collector runs.

## 44. `WeakHashMap`: Weak Keys, Yet It Does Not Automatically Prevent Every Leak

`WeakHashMap<K,V>` uses weak references for its keys, so entries can be removed when keys are no longer strongly reachable.

**Important trap:** the map still holds strong references to **values**. If a value directly or indirectly points back to the key, a path can form:

```text
root → WeakHashMap → strongly held Value → Key
```

In that case, the key remains reachable through the value and is not freed merely because the map uses weak keys.

A key can also be held by another collection; the weak map does not interfere with those strong paths.

### Do Not Use WeakHashMap Like a Database

Entries can disappear based on GC behavior, rather than a fixed business expiration time. If you need timeouts/size bounds/a refresh policy, use a cache implementation with explicit, testable eviction.

## 45. Runnable: WeakHashMap While a Key Is Still Strong

Save **`WeakHashMapDemo.java`**:

```java
import java.lang.ref.Reference;
import java.util.WeakHashMap;

public class WeakHashMapDemo {
    public static void main(String[] args) {
        WeakHashMap<Object, String> map = new WeakHashMap<>();

        Object key = new Object();
        map.put(key, "value");

        System.out.println(map.get(key));
        System.out.println(map.containsKey(key));

        Reference.reachabilityFence(key);

        // Do not predict anything after losing the strong key:
        // entry removal depends on GC and other refs.
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WeakHashMapDemo.java
java WeakHashMapDemo
```

Stdout:

```text
value
true
```

Every assertion takes place while `key` still has a clear strong reference path. Do not write examples like "call `System.gc()` and the map will definitely be empty" because there is no such guarantee.

## 46. What Scenario Does `Reference.reachabilityFence` Solve?

Normally, you **do not need** to manually add fences to your application. However, there is a scenario where a resource wrapper holds a native handle:

```text
Java wrapper ──native handle──▶ OS/native resource
```

If the Java compiler/JIT determines that the wrapper is no longer used before the native operation actually finishes, a reachability-based cleanup mechanism can run into trouble. `Reference.reachabilityFence(wrapper)` ensures strong reachability of the referent up to the fence call point according to the API contract.

Schematic example:

```java
nativeUse(handle);
Reference.reachabilityFence(wrapper);
```

This is a **snippet** dependent on an external native API. Do not imagine that `reachabilityFence` keeps the object alive forever; it only establishes a reachability boundary for a specific code path.

### Do Not Turn a Fence into a GC Trigger

`Reference.reachabilityFence` does not invoke GC, does not close a resource, and does not guarantee the object is unreachable after the fence. Its meaning is to bound **the interval during which the object must be considered strongly reachable**.

## 47. GC Reclaiming Memory Is Different from Closing Resources

A Java object can wrap:
- File descriptor;
- Socket;
- JDBC connection;
- Native buffer;
- Thread;
- Lock/transaction;
- Streams.

You should not wait for GC to release those resources in a timely manner.

Java 17 uses `AutoCloseable`/`Closeable` and **try-with-resources** for control-flow-driven cleanup:

```java
try (Resource resource = new Resource()) {
    resource.use();
}
```

`close()` is called upon exiting the try block according to the rules, even if an exception occurs (under appropriate handling conditions). This **is not equivalent** to GC reclaiming the object.

**`finalize()`** has been deprecated and is especially unreliable for resource management; do not use a finalizer as a mechanism to close files/sockets. `Cleaner` is only suitable as a safety net in certain designs, not as a replacement for deterministic close.

## 48. Runnable: try-with-resources Closes at the Right Time

Save **`ResourceLifecycleDemo.java`**:

```java
final class DemoResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("using");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ResourceLifecycleDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }

        System.out.println("after-try");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
```

Stdout:

```text
using
closed
after-try
```

`close` occurs according to program structure, without needing to call `System.gc()`. The `DemoResource` object may still remain in memory temporarily after closing; **resource state** and **object memory lifetime** are two different matters.

## 49. A `final` Reference Field Does Not Prevent the Object from Being Mutated

```java
final class Holder {
    final StringBuilder text = new StringBuilder();
}
```

`final` prevents reassigning `text` after it has been properly initialized, yet:

```java
holder.text.append("new content");
```

is still allowed. The object's contents can change.

Regarding reachability, `final` does not by itself turn a field into a permanent GC root. When the owner Holder is reachable, the field reference helps keep the referent alive; when the owner is no longer reachable, final does not prevent the graph from being collected.

### Runnable

Save **`FinalReferenceDemo.java`**:

```java
final class Holder {
    final StringBuilder buffer = new StringBuilder("a");
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        Holder owner = new Holder();

        owner.buffer.append("b");

        System.out.println(owner.buffer);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

Stdout:

```text
ab
```

"A final reference field" is different from "an immutable object" and different from "an object pinned forever in the heap".

## 50. Weak vs. Strong Path: When Is GC Allowed to Clear a Weak Ref?

In principle, the collector may clear weak references to an object when the object is no longer strongly/softly reachable under the corresponding soft/weak reachability rules, at an appropriate processing phase.

Points API users need to remember:
- `WeakReference.get()` can return null at any time if strong reachability is no longer guaranteed; the result does not keep the object alive throughout another operation unless the returned value is stored in an appropriate strong local.
- If `T value = weak.get()` returns non-null, the local `value` can provide a strong reference for the ongoing usage.
- Do not write `if (weak.get() != null) weak.get().call();` because between the two `get()` calls the same guarantee may no longer hold; store it once.
- Do not predict the enqueue timing of `ReferenceQueue`.
- Do not use weak refs when the application **must** retain data until a business event completes.

### Check-Once Pattern

```java
Object value = weak.get();
if (value != null) {
    use(value);
}
```

This is a **snippet**: `weak` and `use` must be declared in the corresponding context. A local strong reference `value` helps keep the referent usable during usage, though if special native logic requires a boundary extending past the last apparent use, `reachabilityFence` may be appropriate.

## 51. Do Not Rely on `System.gc()` to Test Object Lifetime

Test code that easily goes wrong:

```java
// Pseudocode anti-pattern:
object = null;
System.gc();
assertNull(weak.get());
```

Unreliable because:
- `System.gc()` is not a promise that the collector completes.
- JDK flags/GC implementations can ignore an explicit GC request.
- The runtime may not yet need to reclaim memory.
- Another reference may still be holding the object.
- JVM optimizations/liveness make behavior inconsistent across builds.

**Tests should verify logic under your control**:
- After unsubscribing, the registry size decreases.
- After `remove()`, the ThreadLocal in that thread no longer has a value.
- After closing, the resource state changes and usage is rejected.
- After cache eviction, the map entry is gone.
- After assignment, the aliases point to the expected objects.

When writing in-depth memory-retention tests, use heap dumps, GC diagnostics, and profiling under sufficiently strict conditions; do not turn an incidental GC timing result into a unit-test contract.

## 52. GC "Eligible" Does Not Mean the JVM Must Free Immediately

An object can:
1. Be allocated or optimized according to the runtime;
2. Be used via a local/field/path;
3. Become no longer strongly reachable at a point in time;
4. Be detected and processed by the collector according to policy;
5. Memory may be reclaimed or still managed for subsequent allocations.

Steps 3–5 are not simultaneous, and not all of them can be observed precisely from Java source.

`Runtime.totalMemory()`/`freeMemory()` or OS process RSS also does not equal "how many objects are no longer reachable". The JVM may keep heap committed memory after collection for reuse.

### Note on Finalization and Resurrection

Java 17 still has legacy finalization semantics in certain circumstances, with complex object resurrection possibilities. This is not a lifecycle management technique you should use. Avoid `finalize()`; use `AutoCloseable`/`Cleaner` as appropriate, and do not rely on finalize timing to prove GC.

## 53. Structures That Commonly Retain Unwanted Objects

### 53.1. Static Caches

A long-lived `Map<Key,Value>` without a size/TTL limit retains keys/values and the entire graph behind them.

**Solution:** size bounds, expiry/eviction, clear ownership, metrics.

### 53.2. Event Listeners

A long-lived event bus with a listener capturing a controller. The controller has already closed the UI, yet the callback has not unsubscribed.

**Solution:** a lifecycle-bound registration token, unregistering during cleanup.

### 53.3. ThreadLocals

A thread in a pool lives long across many tasks, and the context is not removed.

**Solution:** try/finally remove; avoid storing heavyweight objects beyond what is needed.

### 53.4. Pending Tasks

An executor queue holds pending Runnable/Callable instances; the callback captures the request payload.

**Solution:** backpressure, bounded queues, cancellation, shutdown, and avoiding capturing the whole graph.

### 53.5. Inner Classes, Lambdas, and Method References

A callback object can retain an enclosing/receiver/captured object.

**Solution:** understand captures, use static nested classes or pass minimal state, unregister at the right time.

### 53.6. Historical Snapshots

A list of snapshots/past states without a retention policy keeps object graphs reachable.

**Solution:** limit the number of snapshots, streaming, persistence + paging, cache eviction.

### 53.7. Maps Holding Values That Point Back to the Key

Especially when using WeakHashMap, a value → key strong edge can defeat the intended weak-key behavior.

**Solution:** separate references/metadata, design appropriate weak-value or explicit eviction.

## 54. Runnable: A Cache Bounded by Application Logic

Save **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {
    public static void main(String[] args) {
        Map<Integer, String> cache =
                new LinkedHashMap<>(16, 0.75f, true) {
                    @Override
                    protected boolean removeEldestEntry(
                            Map.Entry<Integer, String> eldest) {
                        return size() > 2;
                    }
                };

        cache.put(1, "A");
        cache.put(2, "B");
        cache.put(3, "C");

        System.out.println(cache.containsKey(1));
        System.out.println(cache.containsKey(2));
        System.out.println(cache.containsKey(3));
        System.out.println(cache.size());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BoundedCacheDemo.java
java BoundedCacheDemo
```

Stdout:

```text
false
true
true
2
```

The eviction policy prevents the cache from keeping entry 1 after exceeding the size limit of 2. The goal is to **reduce paths to data that is no longer needed**, not to demand that GC immediately reclaim the String or entry nodes.

## 55. Primitive Local Variables Are Not Reference Paths to Objects

```java
int count = 7;
double ratio = 0.5;
boolean active = true;
```

These local primitives hold primitive values, not object references to `Integer`/`Double`/`Boolean` in the way parameterized references are stored.

Conversely:

```java
Integer count = Integer.valueOf(7);
```

is a reference to a wrapper object (or a cached wrapper depending on the API/implementation), and in principle it participates in reference reachability just like other object references.

### What Effect Does Boxing Have?

Autoboxing can create or reuse wrapper objects according to runtime rules. There is no need to use an object wrapper merely to represent a primitive value when a primitive is suitable, especially inside loops or large arrays.

Do not judge the reference identity of arbitrary boxed values using `==`. For wrappers, use `equals` when you want to compare contents.

## 56. Runnable: Primitives Differ from Reference Aliases

Save **`PrimitiveVsReferenceDemo.java`**:

```java
public class PrimitiveVsReferenceDemo {
    public static void main(String[] args) {
        int a = 5;
        int b = a;

        a = 9;

        StringBuilder x = new StringBuilder("X");
        StringBuilder y = x;

        x.append("Y");

        System.out.println(b);
        System.out.println(y);
        System.out.println(x == y);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PrimitiveVsReferenceDemo.java
java PrimitiveVsReferenceDemo
```

Stdout:

```text
5
XY
true
```

A primitive copy produces an independent value; a reference copy creates an alias to the same object.

## 57. Multiple Equal Objects Are Not Necessarily the Same Object

Java `equals` can define value equality. An object reference graph still cares about **which exact instance** is being pointed to.

```java
String one = new String("A");
String two = new String("A");
```

`one.equals(two)` is true; `one == two` is false because the two `new` statements create two String objects with different identities.

In memory analysis:
- A collection holding `one` does not mean the collection holds `two`.
- Two equal objects still have separate reference graphs and lifetimes.
- Record `equals` also does not automatically merge two instances into a single heap object.

### Runnable

Save **`IdentityAndEqualityDemo.java`**:

```java
public class IdentityAndEqualityDemo {
    public static void main(String[] args) {
        String first = new String("same");
        String second = new String("same");

        System.out.println(first.equals(second));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 IdentityAndEqualityDemo.java
java IdentityAndEqualityDemo
```

Stdout:

```text
true
false
```

The GC does not use "two objects are equal according to `equals`" as a reason to automatically merge them into one object under source logic.

## 58. Class Loaders and Static Field Lifetime

In a typical application, static fields of application classes may live for most of the process lifetime. In servers, plugins, testing frameworks, or containers, multiple class loaders can exist.

If a long-lived object in class loader A holds an object/class loader B, a large graph belonging to an old module/redeployment may fail to unload.

Example of the type of path to watch out for:

```text
application-wide root
  └── static registry
        └── plugin callback
              └── plugin instance
                    └── plugin Class
                          └── plugin ClassLoader
```

**Do not oversimplify this as "a static field is a global root forever"** or "a class unloads immediately when we drop the class loader variable". Determine actual reachability and JVM/container behavior.

### Practices When Developing Plugins

- Remove listeners/registrations when unloading a plugin.
- Shut down executors/threads created by the plugin.
- Remove ThreadLocal values from long-lived threads.
- Avoid static caches in a parent loader holding objects from a child loader.
- Use a heap analyzer to trace **GC root paths**.

## 59. Diagnostic Tools When Memory Retention Is Suspected

Signs to watch for:
- Live heap after multiple collections continues growing under a steady workload.
- Object counts of certain classes keep increasing with the number of requests.
- Retained size of a cache/registry exceeds budget.
- Callback queues or pending tasks do not shrink.
- Old plugin class loaders still remain after multiple redeploy cycles.

Java 17 and ecosystem tools:
- **JDK Flight Recorder (JFR)** and Java Mission Control for profiling/analysis.
- **`jcmd`** for certain diagnostics, class histograms, and heap dumps when the environment permits.
- **Heap dump** + Eclipse Memory Analyzer Tool (MAT) to inspect **dominator tree, retained size, paths to GC roots**.
- **GC logs** via `-Xlog:gc*` to observe collector activity, without directly inferring which object is being retained by a listener.
- **Application metrics** for size/age of caches, listener counts, ThreadLocal lifecycle.

Tools have their own versions, arguments, and access permissions. In production, you must weigh overhead/disruption and the privacy of heap dumps containing sensitive data.

## 60. Strategy for Investigating Leaks by Reference Paths

1. **Define expected behavior:** at which event should object A cease to have a purpose?
2. **Reproduce consistently:** create/clean up sessions or screens repeatedly, and observe memory after multiple cycles.
3. **Collect evidence:** heap dump/JFR/metrics in an appropriate environment.
4. **Find suspect object types:** count, retained size, age.
5. **Inspect paths to GC roots:** static map? singleton? thread? listener? lambda capture? class loader?
6. **Read the actual reference graph:** is it a strong path, or are there weak/soft/phantom edges?
7. **Identify ownership:** who registers, who unregisters, who is permitted to clear?
8. **Fix the wrong retention path:** remove/clear/close/cancel, bounded cache, without relying on a GC hint.
9. **Test business behavior:** the object is no longer in the registry, the context is cleared on time, the resource closes.
10. **Re-measure:** compare entry counts/retained size/memory trend before and after on a representative workload.

The strongest question when debugging: **"Which strong reference path, and from which root, is keeping this object alive?"**

## 61. Things You Should Not "Optimize" by Putting `null` Everywhere

In ordinary code:

```java
process(item);
item = null;
```

assigning null after last use is usually **unnecessary**, because the JIT/GC already performs liveness analysis. It also easily makes code harder to read, masks logic bugs, or introduces an NPE if a developer continues using the variable.

Cases where changing a reference may genuinely be worthwhile:
- **Long-lived fields** after a business phase ends.
- **Large arrays** with slots no longer used while the array itself stays alive.
- **Caches/collections** that need to remove old entries.
- **Object pools** holding references that need slots cleared properly.
- **Listeners/registrations** that must unregister.

Focus on **reference paths with long-lived owners**, rather than imposing a habit of nulling out every local variable.

## 62. Understanding an Object's Lifecycle Through a Combined Example

Consider:

```java
final class Customer {
    final String name;

    Customer(String name) {
        this.name = name;
    }
}
```

Steps:

1. `Customer c = new Customer("An");` — creates a Customer and local c pointing to the object.
2. `List<Customer> list = new ArrayList<>();` — creates another list object.
3. `list.add(c);` — the list holds a reference to Customer.
4. `Cache.saved = list;` — the static field points to the list, creating a path from class state through the list to Customer.
5. `c = null;` — local c drops its reference; Customer still has a path through Cache.saved.
6. `list = null;` — local list drops its reference; static Cache.saved still holds the ArrayList.
7. `Cache.saved.clear();` — the list drops its reference to Customer.
8. `Cache.saved = null;` — the static cache drops its reference to the list.
9. If there are no other roots/paths, those objects can become unreachable.
10. The JVM is **not required** to reclaim them immediately at step 9.

The takeaway is not "step 8 triggers GC", but **how each operation transforms the graph**.

## 63. Runnable: Checking the State of the Combined Graph

Save **`ReachabilityPathsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Cache {
    static List<StringBuilder> saved;
}

public class ReachabilityPathsDemo {
    public static void main(String[] args) {
        StringBuilder item = new StringBuilder("important");
        List<StringBuilder> list = new ArrayList<>();

        list.add(item);
        Cache.saved = list;

        item = null;
        list = null;

        System.out.println(Cache.saved.get(0));
        System.out.println(Cache.saved.size());

        Cache.saved.clear();
        System.out.println(Cache.saved.isEmpty());

        Cache.saved = null;
        System.out.println(Cache.saved == null);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ReachabilityPathsDemo.java
java ReachabilityPathsDemo
```

Stdout:

```text
important
1
true
true
```

No step prints "GC succeeded", because that is not a behavior Java source code can promise.

## 64. Checklist for Analyzing Whether an Object Is Being Retained

- [ ] Have you distinguished the reference variable from the object?
- [ ] Do you know **which instance** is being retained, not just the class name?
- [ ] Which local variables or parameters are still being used?
- [ ] Are any instance fields from a reachable owner pointing to the object?
- [ ] From which GC root does the field's owner have a path?
- [ ] Is any static field/cache holding the owner or the object itself?
- [ ] Is the object in an array slot or a collection entry?
- [ ] Are there multiple incoming references/aliases?
- [ ] Does a return value or parameter escape keep the object alive longer than the method?
- [ ] Does a lambda/anonymous class/bound method reference capture the object?
- [ ] Does a non-static inner object retain the enclosing instance?
- [ ] Is there an unregistered listener/subscription?
- [ ] Is there a ThreadLocal surviving across thread pool tasks?
- [ ] Are there executor pending tasks holding a captured payload?
- [ ] Is there a cycle, and is there actually a root path to the cycle?
- [ ] If the cycle has no path from roots, are you avoiding treating the cycle alone as a leak?
- [ ] Have you distinguished static fields from instance fields and locals?
- [ ] Have you distinguished a `final` field from an immutable referent?
- [ ] Have you distinguished `equals` from reference identity?
- [ ] If WeakReference is used, does the code handle null from `get()`?
- [ ] Have you avoided claiming GC occurs immediately after `System.gc()`?
- [ ] Have you separated the `close()` resource lifecycle from GC memory reclamation?
- [ ] Have you used profiling/a heap dump if needed to confirm unintended retention paths?
- [ ] Does cleanup have a defined owner, trigger event, and test path?
- [ ] Have you checked for regressions after the fix, rather than merely setting local variables to null?

## 65. Exercise 1 — Two Aliases

```java
Object first = new Object();
Object second = first;
first = null;
```

Question: does the object still have a reference path from `second`?

**Answer:** Yes. Assigning null to first does not make second null and does not delete the object.

## 66. Exercise 2 — Two Different Objects

```java
Object a = new Object();
Object b = new Object();
a = b;
```

Question: how many objects are created via `new Object()` in the source, and does a's original object still have a path from a?

**Answer:** There are two `new Object()` expressions; a has switched to pointing to b's object. The old object no longer has a path from a, though whether it remains reachable requires considering other paths and optimizations rather than inferring from a single statement.

## 67. Exercise 3 — Returned Object

A method creates an object in a local variable and then `return`s the reference. The caller stores the reference.

**Answer:** The object can survive past the method return because the caller holds the reference. There is no automatic deep copy.

## 68. Exercise 4 — Local Scope

An object is created inside a block, and the reference is assigned to a local outside the block.

**Answer:** The end of scope for the local inside the block does not make the object unreachable if the outer local still holds the reference.

## 69. Exercise 5 — Field Chain

`root.user.cart.items.get(0)`. Which path can retain the item?

**Answer:** A path through root → user → cart → items/list → element. You must consider the root and other aliases to draw a conclusion.

## 70. Exercise 6 — Is an Instance Field a Root?

An object A has a field referencing B, yet A is no longer reachable.

**Answer:** A field is not a GC root by itself. If there are no other paths to A/B, the entire graph can be unreachable.

## 71. Exercise 7 — Static Cache

A static list holds a session; the local that created the session has exited the method.

**Answer:** The session may still be reachable via the static list if the class/static state remains reachable. Appropriate eviction/removal is needed.

## 72. Exercise 8 — Array

`array[0] = customer; customer = null;` with the array still reachable.

**Answer:** The array slot still holds the customer object.

## 73. Exercise 9 — Collection Removal

An object resides in two lists; only the first list is cleared.

**Answer:** The second list still has a reference path. Both lists and any other aliases must be considered.

## 74. Exercise 10 — A↔B Cycle

A and B reference each other, yet there is no path from live GC roots to the two objects.

**Answer:** The cycle by itself is not enough to keep the objects strongly reachable; a tracing GC can reclaim the cycle.

## 75. Exercise 11 — Pass-by-Value

A method receives `StringBuilder p`, then `p = new StringBuilder("X");`.

**Answer:** The caller variable does not change because the parameter is passed by reference value. If the method mutates via `p.append` on the old object, the state changes.

## 76. Exercise 12 — Final Field

`final List<String> values = new ArrayList<>();`. Can `values.add(...)` be called?

**Answer:** Yes, if the object allows it. Final prevents reassigning the field/local; it does not make ArrayList immutable.

## 77. Exercise 13 — Lambda Capture

A long-lived registry holds a lambda that has captured a controller.

**Answer:** It can retain the controller through the callback path. Unregister according to the lifecycle; do not just call GC.

## 78. Exercise 14 — Inner Class

An instance of a non-static inner class is still retained; an inner method needs to use Outer.this.field.

**Answer:** Inner has an enclosing-instance association to access Outer; the outer graph can be retained along that path.

## 79. Exercise 15 — Bound Reference

`Runnable r = printer::print; printer = null; r.run();`.

**Answer:** The bound method reference can still invoke the bound receiver; assigning null to the local does not remove the callback's receiver.

## 80. Exercise 16 — ThreadLocal

A thread pool worker processes request A and stores context, forgetting to remove it. The worker then processes request B.

**Answer:** Context A can be seen/retained in B. Use try/finally remove per task/request.

## 81. Exercise 17 — `System.gc()`

After `obj=null; System.gc();`, can you assert that the weak reference is already null?

**Answer:** No. There is no guarantee on GC execution or timing; other paths may also exist.

## 82. Exercise 18 — Weak Reference

A WeakReference points to an object, with no strong paths remaining.

**Answer:** The collector may clear the weak reference according to GC semantics. Do not require `get()` to definitely be non-null or definitely be null immediately.

## 83. Exercise 19 — WeakHashMap

A weak-key map with key K holds value V; V has a field pointing back to K.

**Answer:** Value has a strong edge to K, which can keep the key reachable. Weak keys do not automatically resolve a strong path loop through the value.

## 84. Exercise 20 — Phantom Get

Does `PhantomReference.get()` return a usable referent?

**Answer:** No; `get()` always returns null. ReferenceQueue is typically used for cleanup coordination without predicting timing.

## 85. Exercise 21 — Close and GC

A file stream is closed when exiting try-with-resources. Is the stream object garbage-collected immediately?

**Answer:** Not necessarily. Resource close is deterministic cleanup; memory reclamation is a separate process.

## 86. Exercise 22 — Resource Finalization

Should `finalize()` be used to close a socket?

**Answer:** No. Finalization is deprecated/unreliable and its timing is indeterminate. Use try-with-resources/close/finally.

## 87. Exercise 23 — Heap Usage

After cache.clear(), process RSS does not drop. Did clear() fail?

**Answer:** You cannot conclude that yet. The JVM may not have run GC yet, may keep committed heap for reuse, or another retention path may remain. You need to measure live objects/the heap graph properly.

## 88. Exercise 24 — Primitive

Does `int x = 42;` mean an `Integer` object is always created?

**Answer:** No. A local int holds a primitive value. Boxing/reference wrappers are a different situation.

## 89. Exercise 25 — Equality vs. Identity

Two `new String("A")` objects are `equals` to each other, yet `==` is false. Does GC treat them as a single object because equals is true?

**Answer:** No. Reachability and identity look at the actual reference graph, and do not use `equals` to treat two instances as the same object.

## 90. Exercise 26 — Multiple Roots

Two registries both hold the same listener; you remove it from one registry.

**Answer:** The listener may still be reachable via the remaining registry. All relevant root paths must be found.

## 91. Exercise 27 — Static Lifecycle

Can we say "all static fields always keep objects alive until JVM exit"?

**Answer:** Not unconditionally. Class-loader reachability/unloading and field assignments affect lifetime; the runtime must be considered.

## 92. Exercise 28 — Liveness and Lexical Scope

A local is still in the source block but past its last use. Is the object necessarily kept alive until the closing brace of the block?

**Answer:** No. The JIT/GC can determine liveness earlier according to semantics; the scope of a name is not identical to reachability lifetime.

## 93. Exercise 29 — Source Leak

A static `List<Screen>` is appended to each time a screen opens, without clearing even after the screen closes.

**Answer:** This is an application-level retained-object memory leak: the static list path still holds the screens. Fix owner cleanup/bounds and test entry removal.

## 94. Exercise 30 — Debugging Retention

A Report object still appears in a heap dump after the request completes. What evidence do you need to look for?

**Answer:** Paths to GC roots, dominators/retained size, listeners, caches, ThreadLocal, pending tasks, and object fields; determine whether the strong path is intentional or a leak. Merely seeing "the object appears in the dump" is not enough to conclude.

## 95. Comprehensive True/False

1. Two variables both pointing to an object mean two objects.
2. Assigning null to a variable can remove the reference edge from that variable.
3. An instance field is itself a GC root regardless of whether the owner is reachable.
4. Exiting local scope does not guarantee immediate GC.
5. Static caches can retain object graphs across multiple method calls.
6. `List.clear()` automatically calls destructors on all elements.
7. A strong reference cycle does not keep objects alive by itself if there is no path from roots.
8. A lambda/bound method reference can capture/retain objects.
9. ThreadLocal values can persist across multiple tasks on the same pooled worker.
10. `WeakReference.get()` is guaranteed to return null immediately after `System.gc()`.
11. A `final` reference makes StringBuilder immutable.
12. `AutoCloseable.close()` and GC reclaiming the object are the same event.
13. `Reference.reachabilityFence` invokes GC.
14. Collections that remain reachable can retain element references.
15. Removing one of multiple independent strong paths is always enough to make an object unreachable.

**Answers:** 1 false; 2 true; 3 false; 4 true; 5 true; 6 false; 7 true; 8 true; 9 true; 10 false; 11 false; 12 false; 13 false; 14 true; 15 false.

## 96. Common Mistakes Table

| Misconception | Reality | How to Handle |
| --- | --- | --- |
| "Local out of scope = object deleted immediately" | Scope ≠ GC timing; references can escape | Trace remaining paths |
| "`a=null` deletes the object" | Only reassigns one reference variable | Check aliases/fields |
| "Methods pass objects by reference" | Java is always pass-by-value, even for reference values | Distinguish mutating the object from reassigning the parameter |
| "An instance field is a GC root" | The owner must be reachable via a root/path | Trace paths from roots |
| "Static always exists forever" | Class-loader lifetime and field updates matter | Inspect the actual root paths |
| "`final` makes the referent immutable" | Final only prevents reassigning the variable/field | Use immutable values/defensive copies |
| "List.remove frees the object immediately" | Removes one reference path, does not schedule GC | Find aliases and measure |
| "A reference cycle automatically causes a memory leak" | Tracing GC handles unreachable cycles | Look for a root path into the cycle |
| "WeakReference reliably keeps cache items" | The referent may be cleared | Handle null/rebuild |
| "System.gc always cleans up immediately" | Only a request/hint; the collector decides | Do not test GC timing |
| "WeakHashMap never leaks" | Values can point back to keys; other refs may hold them | Check value→key paths |
| "ThreadLocal automatically resets each task" | A pooled thread keeps the mapping across tasks if not removed | try/finally remove |
| "Listeners disappear automatically when UI is gone" | The event bus may retain the callback/capture | unsubscribe/dispose |
| "Closing objects via GC" | Resources must be closed via control flow | try-with-resources |
| "Object equals true = same identity" | Equality differs from object reference | Use == when analyzing aliases |
| "RSS not dropping = GC bug" | Committed heap and live objects are different metrics | Heap dumps/JFR/path analysis |

## 97. Lesson Summary

**Local variables, instance fields, static fields, array slots, collection entries, callbacks, and mechanisms like ThreadLocal** can all create **reference paths** to an object. An object can continue to be used even after the local that created it has ended, if the reference has been stored via a field, return value, list, or lambda capture.

In the Java GC model:
- An object with a strong path remaining from live roots is still **reachable**.
- A field is only an edge; by itself it is not a GC root if its owner is not reachable.
- Setting a variable to null, removing an entry from a collection, or dropping one path only changes the graph. You must inspect **all remaining paths**.
- A cyclic graph with no remaining root path can be collected; conversely, a static registry holding an object that is no longer needed is a real source of memory leaks.
- **When an object becomes eligible, when GC executes, and when memory returns to the system are all different**; do not write unit tests depending on `System.gc()`.
- Weak/soft/phantom references have their own mechanisms and do not replace strong ownership or a deterministic lifecycle.
- **Resource cleanup `close()`** must not be delegated to GC; use try-with-resources and manage subscriptions/ThreadLocals/cache entries at the right time.

The question to ask when analyzing an object's lifecycle is not merely **"Has the variable that created the object gone out of scope?"**, but:

> **"Is there still any reference path from a GC root to this object, and does that path still carry business meaning?"**

Being able to answer that question is the foundation for debugging memory leaks, understanding aliasing, designing cache/listener lifecycles, and working safely with Java 17.

## Official Java SE 17 References

- **Java Language Specification `12.6 — Finalization of Class Instances**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JLS `12.6.1 — Implementing Finalization** (definitions of reachability and related limitations): https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1
- **`java.lang.ref` package**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- **`java.lang.ref.Reference` and `reachabilityFence`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- **`java.lang.ref.WeakReference`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **`java.util.WeakHashMap`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html
- **`java.lang.AutoCloseable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **`java.lang.ThreadLocal`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
