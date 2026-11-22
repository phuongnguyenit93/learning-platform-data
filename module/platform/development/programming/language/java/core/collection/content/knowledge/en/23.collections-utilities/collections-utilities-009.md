# asLifoQueue, newSetFromMap, and Backing Structure Requirements

A data structure sometimes already has the exact storage mechanism needed, while the caller-side interface differs. An algorithm accepting a `Queue` may need to retrieve the newest element first; a problem accepting a `Set` may need to compare membership by object identity or use weak keys.

`Collections.asLifoQueue` and `Collections.newSetFromMap` create adapted views backed by an underlying structure. They do not read all the data and create an independent copy. The behavior of the result depends on how operations are forwarded and on the contract of the deque or map passed in.

This lesson uses Java 17. Before running the code, you should know `Queue`, `Deque`, `Map`, `Set`, and references. The two main focuses are the insertion/removal end for LIFO and the map ownership requirements when creating a set.

## 1. Two Adapters Solving Two Different Problems

| Method | Input | Result | Purpose |
| --- | --- | --- | --- |
| `Collections.asLifoQueue(deque)` | `Deque<T>` | `Queue<T>` | Use queue operations while retrieving elements in LIFO order |
| `Collections.newSetFromMap(map)` | `Map<E, Boolean>` | `Set<E>` | Use map keys as the storage for set membership |

LIFO stands for "last in, first out". If you add A, then B, then C through the LIFO interface, the first element retrieved is C.

A set from a map uses keys to represent membership. The `Boolean` value type is part of the adapter's internal representation; users work with `Set<E>` instead of managing key–value pairs themselves.

What they share is that there is a **live backing structure actually being used**. There is no promise of automatically making elements immutable, changing the `null` policy, or adding concurrency support to a structure that does not already have it.

An important difference: the deque for `asLifoQueue` **does not have to be empty**. The map for `newSetFromMap` **must be empty at creation time**, and should not be accessed directly afterward.

## 2. Why Can a `Queue` Have LIFO Ordering?

`Queue` describes operations for inserting, removing, and inspecting the head element to be processed. It does not require every implementation to be FIFO. Priority queues and LIFO queues are examples with different orderings. [Queue Contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

If you simply pass an `ArrayDeque` directly as a `Queue`, standard queue operations insert at the tail and remove from the head, producing FIFO. Casting to the interface does not change the insertion end.

`asLifoQueue` changes how operations are mapped: insertions through the queue go to the **head of the deque**, and removals also come from the **head of the deque**. That is why the most recently added element is retrieved first.

~~~text
offer(A): head [A] tail
offer(B): head [B, A] tail
offer(C): head [C, B, A] tail
poll():   returns C, remaining [B, A]
~~~

There is no step that reverses the entire deque on each insertion. The LIFO relationship comes from using the same end for both insertion and removal.

### Mapping Each Group of Operations Correctly

| Operation on adapted queue | Deque head operation | Meaning when no element / no space |
| --- | --- | --- |
| `add(e)` | `addFirst(e)`, equivalent to push | Fails to add when full: exception |
| `offer(e)` | `offerFirst(e)` | May return `false` if full |
| `remove()` | `removeFirst()`, equivalent to pop | Empty: `NoSuchElementException` |
| `poll()` | `pollFirst()` | Empty: `null` |
| `element()` | `getFirst()` | Empty: `NoSuchElementException` |
| `peek()` | `peekFirst()` | Empty: `null` |

Queue methods have two groups for handling failure. Choose the group that matches your intended contract; do not call `remove()` when you actually want to probe for missing data with `poll()`.

The table refers to the **no-argument** `remove()`. `remove(value)` is an operation that searches for and removes a matching element, not a synonym for popping the head element. [Double-ended Deque Operations, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 3. `asLifoQueue` Is a Live View Over the Deque

### Does Not Create an Independent Stack

Illustrative code inside a method:

~~~java
Deque<String> storage = new ArrayDeque<>();
Queue<String> pending = Collections.asLifoQueue(storage);

pending.add("A");
pending.add("B");
~~~

Both interfaces use the same data. Iterating the deque from head to tail will see B, A. Removing through the queue also removes from that same structure.

The deque may already contain elements before creating the view. The factory does not reverse existing elements to guess their insertion history. It provides a rule for operations performed through the view from the moment it is used.

For example, if the deque currently holds `[old-first, old-last]`, adding `"new"` through the queue yields `[new, old-first, old-last]`. The `new` element is prioritized for removal because it is placed at the head, while the relative order of the two old elements is not reversed.

### Keeping Both References Requires Controlling Both Access Paths

Modifying the deque directly will be visible through the queue. That proves they share the same storage, but in application code you must avoid accidentally mixing head/tail insertion rules.

If one component inserts via `deque.addLast` while another inserts through the LIFO queue, the "last in, first out" story only holds for the designated operations. You cannot ignore a tail-insertion path and still promise a different global order.

A simple encapsulation pattern when you only want to expose LIFO is not to expose the deque:

~~~java
Queue<String> pending =
        Collections.asLifoQueue(new ArrayDeque<String>());
~~~

Callers only have the adapted queue interface. If all of your code already uses `Deque` directly and wants push/pop, using `Deque` itself is usually enough; there is no need to add an adapter just to write different method names.

### Iterating Does Not Mean Removing Elements

The view's iterator uses the deque's head-to-tail traversal order. With A, B, C added through LIFO, `new ArrayList<>(queue)` represents C, B, A without popping the elements.

By contrast, looping with `poll` is an actual removal operation. You must distinguish reading for display from consuming work.

## 4. `addAll` and Backing Structure Limits

### Bulk Insertion Reverses the Group Order at the Head

`asLifoQueue` implements `addAll` as a sequence of `addFirst` calls on the deque, in the order elements are read from the input. [asLifoQueue API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#asLifoQueue(java.util.Deque)).

With an empty queue:

~~~java
pending.addAll(List.of("A", "B", "C"));
~~~

Afterward, the head-to-tail order is `[C, B, A]`. If the queue already has data, this group sits in front of the old data according to the same rule.

Do not equate this operation with a standard `deque.addAll` that appends at the tail. Calls with the same method name on different receiver objects can use different placement policies.

### A Bounded Deque Keeps Its Capacity Limit

Using a deque bounded to two elements:

~~~java
Queue<String> pending =
        Collections.asLifoQueue(new LinkedBlockingDeque<String>(2));
~~~

Adding A then B with `offer` succeeds. `offer("C")` returns `false` when full; `add("C")` throws `IllegalStateException` in that situation.

The adapter does not allocate extra space to bypass the limit, nor does it wait for space to become available. The `Queue` return type does not provide blocking operations like `put` or `take`, even if the backing structure has a separate blocking interface.

`LinkedBlockingDeque` can have a capacity bound, whereas `ArrayDeque` has no fixed limit of that kind and grows as needed. This policy comes from the chosen deque type. [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### A Bulk Operation Is Not Automatically a Transaction

If an empty queue bounded to two elements calls `addAll(A, B, C)`, the first two insertions can complete before the third fails. The runnable example below confirms that B, A remain after the exception.

Do not infer "either add all or change nothing" from "one Java call". If business logic requires the whole group to be accepted as a single unit, you must design an appropriate mechanism for that.

### The `null` Policy Is Not Removed

`ArrayDeque` does not allow `null` elements, so a LIFO queue backed by it also rejects `null`. Another deque may have a different policy, but `null` makes empty-probe results from `poll`/`peek` ambiguous.

Use elements with clear meaning for the chosen queue protocol. Do not treat the view as a way to legitimize an element that the backing structure rejects.

## 5. `newSetFromMap`: An Empty Map Handed Over to a Set to Manage

Signature:

~~~java
public static <E> Set<E> newSetFromMap(Map<E, Boolean> map)
~~~

This is the API declaration for reading the types, not implementation code to copy into a program.

Map keys represent set members. `set.add(e)` is implemented through a write operation on the map; membership, removal, and iteration operations go through the map or its key view.

### The Map Must Truly Have No Mappings

A map containing the key `"already"` with value `Boolean.FALSE` is still a **non-empty map**. `False` does not mean "the key does not exist". Passing that map to the factory throws `IllegalArgumentException`.

The factory does not accept a map that already contains data to "convert all keys into a set". If you only need a set of keys from an existing map, that is a different need, usually involving `keySet` or copying the keys under the required contract.

### After Creation, Do Not Access the Backing Map Directly

The documentation requires the map to be empty at call time and warns against accessing the map directly after the factory returns. The clean, maintainable way is to construct the map inline in the call and keep no external reference:

~~~java
Set<Object> visited = Collections.newSetFromMap(
        new IdentityHashMap<Object, Boolean>());
~~~

All membership operations go through `visited`. Do not keep an alias to the map, an old `keySet`, or another view that could mutate the data through a different path.

This differs from the LIFO section's example of observing a deque through two interfaces. For a set from a map, **do not use direct reads/writes on the backing map after creation as an experiment**; the program below only operates on the set once it is successfully created.

The ownership rule prevents external code from putting a different `Boolean` value or altering mappings, which would break assumptions that set operations rely on. [newSetFromMap API, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map)).

### Being Empty Is a Creation Precondition, Not a Guarantee of All Supported Operations

An empty but unmodifiable map can satisfy the emptiness check. The set adapted from it still cannot `add` if the map does not support writes.

Do not treat successful factory creation as proof that the backing map supports every desired operation. When the application needs to add/remove members, choose a map with the appropriate mutability from the start.

## 6. Set Characteristics Inherited from the Map

### Iteration Order

With an insertion-ordered `LinkedHashMap`, the adapted set iterates in the order keys were inserted. Re-adding an existing member does not create a new position; removing and re-adding moves it to the end of the insertion order.

This example is useful for verifying the mechanism, though a typical insertion-ordered set need is already expressed directly by `LinkedHashSet`. There is no need to use the factory for every map that already has a familiar corresponding set type. [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html).

Do not promise insertion order for a set backed by `HashMap`, `IdentityHashMap`, or `ConcurrentHashMap` just because the code executes `add` calls in a specific order.

### Reference Identity

`IdentityHashMap` treats two keys as the same when they are the same reference, i.e., `==`. Therefore, two distinct `new String("item")` instances can both be members in the set even though their `equals` returns `true`.

A new object with a different reference but equal content will not match the old member. This rule is useful when tracking specific visited object nodes and you do not want to merge two nodes merely because their data is equal. [IdentityHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html).

This is specialized semantics. Do not use an identity-based set as an ordinary value set and expect all set comparisons, set operations, or utilities combined with an `equals`-based set to have standard meaning.

In experiments, use `new String` to ensure distinct references. Two identical string literals are not a suitable test because they may be interned/shared.

### Weak Keys

You can create a set backed by `WeakHashMap`:

~~~java
Set<Object> tracked = Collections.newSetFromMap(
        new WeakHashMap<Object, Boolean>());
~~~

This is an illustrative snippet requiring imports for `Set`, `Collections`, and `WeakHashMap`. It does not create a set that strongly retains every member object.

When there are no remaining appropriate strong references to a key, garbage collection can cause the member to disappear. Do not use a weak-key set as a registry that must retain every entry until `remove` is called.

Do not print stdout claiming "after calling `System.gc()`, size is guaranteed to be 0". Collection timing and key reachability are not determined by a single GC request line. The main program does not use a GC result as fixed proof. [WeakHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html).

### Concurrency and `null` Policy

A set backed by `ConcurrentHashMap` inherits the map's concurrent operation capabilities, including rejecting `null` keys. The set does not add external locking or turn multi-step operations into a single transaction.

For standard concurrent set needs, `ConcurrentHashMap.newKeySet()` is the direct API available in Java 17:

~~~java
Set<String> active = ConcurrentHashMap.newKeySet();
~~~

`newSetFromMap` remains useful for understanding and using other suitable backing maps. Choose the API that expresses intent clearly rather than wrapping with an adapter just to add layers. [ConcurrentHashMap and newKeySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet()).

A set backed by a regular map that accepts `null` can accept `null`; a map that rejects `null` keys passes that restriction to the set. The `Set<E>` interface does not define a single universal `null` policy across all implementations.

## 7. Complete Program

Save all the code into **`BackedAdaptersDemo.java`**. All maps used to successfully create sets are constructed directly inside the factory call, with no alias kept for later reading or modification.

A non-empty map is created separately solely to test the rejected case. The concurrent set examples run on a single thread to verify add/duplicate/`null` behavior; concurrency guarantees come from the backing class's contract, not from a single-threaded run.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingDeque;

public class BackedAdaptersDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> backing = new ArrayDeque<>();
        Queue<String> lifo = Collections.asLifoQueue(backing);
        lifo.offer("A");
        lifo.offer("B");
        lifo.add("C");
        System.out.println("lifo.view=" + new ArrayList<>(lifo));
        System.out.println("lifo.backing=" + new ArrayList<>(backing));
        System.out.println("lifo.peek=" + lifo.peek());
        System.out.println("lifo.remove=" + lifo.remove());
        System.out.println("lifo.poll=" + lifo.poll());
        System.out.println("lifo.element=" + lifo.element());
        System.out.println("lifo.lastPoll=" + lifo.poll());
        System.out.println("lifo.emptyPoll=" + lifo.poll());
        System.out.println("lifo.emptyPeek=" + lifo.peek());
        rejects("lifo.emptyRemove", NoSuchElementException.class,
                lifo::remove);
        rejects("lifo.null", NullPointerException.class,
                () -> lifo.offer(null));

        Deque<String> existing =
                new ArrayDeque<>(List.of("old-first", "old-last"));
        Queue<String> adapted = Collections.asLifoQueue(existing);
        System.out.println("existing.before=" + new ArrayList<>(adapted));
        adapted.add("new");
        System.out.println("existing.afterAdd=" + new ArrayList<>(adapted));
        System.out.println("existing.removeLast=" + existing.removeLast());
        System.out.println("existing.afterBackingEdit="
                + new ArrayList<>(adapted));

        Queue<String> bulk = Collections.asLifoQueue(new ArrayDeque<>());
        bulk.addAll(List.of("A", "B", "C"));
        System.out.println("bulk.view=" + new ArrayList<>(bulk));

        Queue<String> bounded =
                Collections.asLifoQueue(new LinkedBlockingDeque<>(2));
        System.out.println("bounded.offers="
                + bounded.offer("A") + "/"
                + bounded.offer("B") + "/"
                + bounded.offer("C"));
        System.out.println("bounded.peek=" + bounded.peek());
        rejects("bounded.addFull", IllegalStateException.class,
                () -> bounded.add("C"));
        System.out.println("bounded.polls="
                + bounded.poll() + "/" + bounded.poll());

        Queue<String> partial =
                Collections.asLifoQueue(new LinkedBlockingDeque<>(2));
        rejects("partial.addAll", IllegalStateException.class,
                () -> partial.addAll(List.of("A", "B", "C")));
        System.out.println("partial.afterFailure=" + new ArrayList<>(partial));

        Set<String> ordered = Collections.newSetFromMap(
                new LinkedHashMap<String, Boolean>());
        System.out.println("ordered.firstAdd=" + ordered.add("beta"));
        ordered.add("alpha");
        System.out.println("ordered.equalAdd="
                + ordered.add(new String("beta")));
        System.out.println("ordered.values=" + new ArrayList<>(ordered));
        ordered.remove("beta");
        ordered.add("beta");
        System.out.println("ordered.reinserted=" + new ArrayList<>(ordered));
        ordered.add(null);
        System.out.println("ordered.null=" + ordered.contains(null));

        String first = new String("item");
        String second = new String("item");
        Set<String> identity = Collections.newSetFromMap(
                new IdentityHashMap<String, Boolean>());
        System.out.println("identity.equalValues=" + first.equals(second));
        System.out.println("identity.adds="
                + identity.add(first) + "/" + identity.add(second));
        System.out.println("identity.size=" + identity.size());
        System.out.println("identity.containsSame=" + identity.contains(first));
        System.out.println("identity.containsEqualOther="
                + identity.contains(new String("item")));
        System.out.println("identity.removeSame=" + identity.remove(first));
        System.out.println("identity.afterRemove.size=" + identity.size());

        Map<String, Boolean> nonempty = new HashMap<>();
        nonempty.put("already", Boolean.FALSE);
        rejects("nonempty.map", IllegalArgumentException.class,
                () -> Collections.newSetFromMap(nonempty));
        Set<String> readonlyBacking = Collections.newSetFromMap(
                Collections.<String, Boolean>emptyMap());
        rejects("readonly.mapAdd", UnsupportedOperationException.class,
                () -> readonlyBacking.add("x"));

        Set<String> concurrent = Collections.newSetFromMap(
                new ConcurrentHashMap<String, Boolean>());
        System.out.println("concurrent.adds="
                + concurrent.add("job") + "/" + concurrent.add("job"));
        System.out.println("concurrent.size=" + concurrent.size());
        rejects("concurrent.null", NullPointerException.class,
                () -> concurrent.add(null));
    }
}
~~~

Compile and run from the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 BackedAdaptersDemo.java
java BackedAdaptersDemo
~~~

JDK 17 or later is required for this compile command. The code was compiled with `--release 17` and run on OpenJDK 24.0.2, exiting successfully. Exact stdout:

~~~text
lifo.view=[C, B, A]
lifo.backing=[C, B, A]
lifo.peek=C
lifo.remove=C
lifo.poll=B
lifo.element=A
lifo.lastPoll=A
lifo.emptyPoll=null
lifo.emptyPeek=null
lifo.emptyRemove=NoSuchElementException
lifo.null=NullPointerException
existing.before=[old-first, old-last]
existing.afterAdd=[new, old-first, old-last]
existing.removeLast=old-last
existing.afterBackingEdit=[new, old-first]
bulk.view=[C, B, A]
bounded.offers=true/true/false
bounded.peek=B
bounded.addFull=IllegalStateException
bounded.polls=B/A
partial.addAll=IllegalStateException
partial.afterFailure=[B, A]
ordered.firstAdd=true
ordered.equalAdd=false
ordered.values=[beta, alpha]
ordered.reinserted=[alpha, beta]
ordered.null=true
identity.equalValues=true
identity.adds=true/true
identity.size=2
identity.containsSame=true
identity.containsEqualOther=false
identity.removeSame=true
identity.afterRemove.size=1
nonempty.map=IllegalArgumentException
readonly.mapAdd=UnsupportedOperationException
concurrent.adds=true/false
concurrent.size=1
concurrent.null=NullPointerException
~~~

### Explanation of Result Groups

**`lifo`:** adding A, B, C produces head-to-tail order C, B, A on both the view and the deque. `peek` does not remove; `remove`/`poll` take from the head. `element` sees the remaining A. The two empty-probing calls return `null`, while `remove` on empty throws `NoSuchElementException`.

**`lifo.null`:** the backing `ArrayDeque` rejects `null`; the view does not change that policy.

**`existing`:** a non-empty deque can still be adapted. The factory does not reverse the two old elements; adding `new` places `new` at the head. Removing from the tail directly on the deque is visible through the view, proving shared storage. This is an experiment demonstrating the view relationship, not a recommendation to let multiple components arbitrarily mix mutation paths.

**`bulk`:** `addAll` of A, B, C becomes sequential `addFirst` calls, resulting in order C, B, A.

**`bounded`:** the first two `offer` calls succeed; the third returns `false` when out of space. `add` when full throws an exception. Retrieval is still B then A, not FIFO offer order.

**`partial`:** a single `addAll` call can add two elements before failing. Data B, A remains after the exception, with no automatic rollback to empty.

**`ordered`:** adding `beta` the first time modifies the set; adding a new string equal to `beta` does not change membership under `equals`. Initial order is `beta, alpha`; removing and re-adding `beta` gives `alpha, beta`. The backing map was handed exclusively to the set and never accessed after creation.

**`identity`:** two strings equal in content but with different references are both added. Looking up the exact reference succeeds; looking up a new string with equal content fails. Removing the exact reference removes only one of the two members.

**`nonempty.map`:** a key mapped to `Boolean.FALSE` still makes the map non-empty and is rejected. A `false` value is not interpreted as "not a member" to bypass the precondition.

**`readonly.mapAdd`:** an empty unmodifiable map does not grant add capability to the set. Checking emptiness is not enough to conclude all mutation permissions.

**`concurrent`:** adding the same string a second time does not modify the set. `null` keys are rejected according to `ConcurrentHashMap` policy. Order is not printed for this backed set because it does not promise insertion order.

## 8. Usage in Program Design

### An Algorithm Accepting a `Queue` That Needs Different Retrieval Rules

If an algorithm only calls `offer`/`poll` and accepts a caller-chosen ordering policy, you can supply a FIFO queue or a LIFO view of a deque.

For example, pending-work processing might use FIFO to prioritize older tasks or LIFO for a depth-first traversal workflow. However, substitution is only valid when the algorithm's contract does not implicitly require FIFO for correctness.

The interface name `Queue` does not replace documentation about ordering. When order determines behavior, explicitly document which policy the supplied queue uses.

### Tracking Visited Objects by Identity

When traversing an object graph, two nodes can have equal data yet still be two distinct objects that both need processing. An identity-based set satisfies that identification rule.

If the domain requires a set of codes or values, standard `equals` is usually more appropriate. Do not choose identity just to avoid calling `equals`; changing the equality relation changes the meaning of the data.

### A Tracking List That Does Not Keep Objects Alive

A weak-key set can be suitable when you only want to track objects without becoming the reason they stay alive. You must accept that members can disappear according to reference lifetimes.

If data must reliably persist, choose a strongly-referencing structure with an explicit removal lifecycle. Weak keys are not a precise size-bounding mechanism or a cache with a deterministic expiration schedule.

### Membership Shared Across Multiple Threads

A set backed by a concurrent map can be suitable for individual membership operations. Still, `contains` followed by `add` is two steps; consider using the return value of `add` itself if the question is "did this call add a new member?".

Operation groups, full-set iteration, size state, or updates to data outside the set still need their own consistency contract. Do not promise a snapshot merely because individual backing operations are thread-safe.

For an adapted queue over a concurrent deque, operations are forwarded to the deque with its own policies. The view does not add an atomic protocol for `addAll`, consumption loops, or the state of elements currently being processed.

## 9. What to Check on the Backing Structure

For a LIFO queue, first verify the insertion/removal behavior, full/empty policies, and `null` handling. Then decide whether to keep the deque exposed externally. If it is exposed, every mutation path must be accounted for when explaining the system's ordering.

For a set from a map, verify that the map is empty, supports the required updates, and is transferred into exclusive ownership. Then determine key equality semantics, iteration order, key retention/reachability, and concurrency policy.

You cannot determine these properties from the declared type `Queue<T>` or `Set<E>` alone. You must know how it was constructed and the contract of the backing class.

In terms of cost, the adapter forwards operations to the backing structure, so cost depends on the corresponding backing operation. `addAll` is a sequence of individual operations, not a zero-cost bulk merge. Ordering or concurrency properties of the backing structure do not automatically make elements deeply immutable.

If a direct type such as `LinkedHashSet`, `HashSet`, or `ConcurrentHashMap.newKeySet()` meets the exact goal, choosing it directly helps readers recognize intent faster. The strength of the factories in this lesson is adapting a backing structure that provides needed semantics, not replacing every standard collection with a wrapper.

## 10. Practice with Answers

### Exercise 1 — `Queue` Does Not Automatically Mean FIFO

An empty deque is adapted with `asLifoQueue`. Call `add` A, `add` B, `add` C, then call `poll` three times.

**Question:** What is the returned order? If you simply held an `ArrayDeque` under a `Queue` variable without using the factory, how would normal insertion differ?

**Answer:** The LIFO view returns C, B, A because `add` and `poll` both use the head of the deque. A normal queue over a deque inserts at the tail and removes from the head, producing FIFO. Changing the variable type does not change the underlying operations the way the adapter does.

### Exercise 2 — A Deque That Already Contains Data

A deque from head to tail is `[old1, old2]`. Create a LIFO view and call `offer("new")`.

**Question:** Does the factory require the deque to be empty or automatically reverse it to `old2, old1`? What is the current order?

**Answer:** No. The deque does not have to be empty, and existing data is not automatically reversed. After `offer`, it is `[new, old1, old2]`. The head-insertion rule applies to operations through the view; it does not infer the creation history of old elements.

### Exercise 3 — Bulk Insertion When Full

An empty view is backed by a deque with capacity 2. Call `addAll` with A, B, C.

**Question:** Can you assume that the exception means no elements were added?

**Answer:** No. `addAll` executes a sequence of `addFirst` calls; the first two elements can already be added before the failure on the third element. As shown in the lesson's experiment, the state after failure is B, A. If the whole group must be accepted as a single unit, you must design a different protocol.

### Exercise 4 — A Map with Value `false`

~~~java
Map<String, Boolean> map = new HashMap<>();
map.put("x", Boolean.FALSE);
~~~

**Question:** Can you pass that map to `newSetFromMap` because "`x` is not active yet"?

**Answer:** No. The map has one mapping, so it is not empty; the factory throws `IllegalArgumentException`. The requirement is no mappings at all, not that all values are `false`. If you need a key set from existing map data, use a different approach suited to that goal.

### Exercise 5 — Keeping the Map for Debugging After Creation

A component creates an empty map, passes it to `newSetFromMap`, and still keeps the map to call `put`/`get` or read `keySet` elsewhere.

**Question:** Does this ownership pattern satisfy the contract? What creation pattern reduces the risk?

**Answer:** It violates the API's recommendation: do not access the map directly after creating the set. Construct the map inline in the factory call and keep only the resulting `Set`; all mutations and observations should go through the set. Do not retain a view of the map that creates another indirect access path.

### Exercise 6 — Two Equal Strings in an Identity Set

Two variables are created with two separate `new String("x")` calls, then added to a set backed by `IdentityHashMap`.

**Question:** Can the size be 2? Will `contains` with a third `new String("x")` find a match?

**Answer:** The size is 2 in this case because the two references are distinct. The third string is not one of the stored references, so it is not found. This is intentional identity semantics, unlike a value set using `String.equals`.

### Exercise 7 — An Empty but Unwritable Map

An empty unmodifiable map is passed to the factory, and then `set.add("x")` is called.

**Question:** Does successful set creation prove that `add` is supported?

**Answer:** No. The factory's emptiness check does not make the map modifiable; `add` must write to the map and can throw `UnsupportedOperationException`, as shown in the example. Choose a backing map with the needed mutability from the start.

### Exercise 8 — Weak Keys and Concurrency

One set uses `WeakHashMap`; another set uses `ConcurrentHashMap`.

**Question:** Is a weak-key set guaranteed to lose elements only when `remove` is called? Is a concurrent set guaranteed to accept `null` and make every `addAll` group atomic?

**Answer:** No. Weak-key members can disappear when the key is no longer appropriately strongly retained and gets collected. `ConcurrentHashMap` rejects `null`, and single-operation guarantees do not combine multiple steps into a single transaction. Choosing a backing structure means choosing all of those policies, not just an internal storage layout.

These two adapters are only useful when the backing contract is incorporated into the usage contract. For `asLifoQueue`, the core points are using the same end for insertion/removal and sharing the deque through a live view. For `newSetFromMap`, the core points are an empty map, exclusive ownership, and key characteristics inherited by the set.
