# WeakHashMap: Weak Keys and Garbage Collection Effects

## 1. When a Lookup Table Should Not Decide an Object's Lifetime

Suppose a UI analysis tool stores extra information for each window object. The window is managed elsewhere; this table only attaches auxiliary data to it.

If a long-lived `HashMap` is used, the table itself can keep holding onto the window object after everywhere else has stopped using it. The auxiliary data inadvertently becomes the owner of the object's lifetime.

`WeakHashMap` provides a different option: **mappings in the map do not themselves keep keys alive with strong references**. When a key object is no longer held in a way that prevents collection and the GC processes its weak references, the mapping can disappear.

This is the right structure for thinking about auxiliary data tied to an object's lifecycle. It makes no promise to "keep entries for five minutes," "hold at most one thousand entries," or "evict the least recently used entry."

Three concepts must be separated right from the start:

| Concept | Question It Answers |
| --- | --- |
| Key equality | Which key's mapping is a `get` call looking up? |
| Object reachability | Through which reference paths is the key object still kept alive? |
| Stale mapping cleanup | When are entries whose keys have been processed removed from the table? |

Two keys that are equal according to `equals` are not necessarily the same object tracked by the GC. A key having no remaining strong references also does not mean the map must shrink its `size` on the very next statement.

This lesson moves from the reference graph to `Map` behavior, and then runs three Java 17 programs to distinguish what is guaranteed from results that depend on the GC.

## 2. "Weak" Is a Property of a Reference Path

### 2.1. Strong References and Weak References

In the normal model, a usable strong reference path from the program to an object keeps that object alive.

`WeakReference` allows holding a link to an object such that the weak link itself does not prevent the object from being collected. The referenced object is called the target of the reference, commonly named the *referent* in the API documentation.

For a live `WeakHashMap`, the simplified model is:

```text
program --strong--> map --strong--> entry
entry --weak--> key
entry --strong--> value
```

The weak arrow lies only on the relationship from the entry to the key. Do not infer that the map, the storage nodes, or the value are held weakly.

### 2.2. Every Path to the Key Must Be Considered

If the program still holds the key in an active list, the key stays alive even though the map only references it weakly.

If the value contains a field pointing strongly back to the key, the path `map → value → key` can also keep the key alive.

If only a cycle remains that is unreachable from the program, having a cycle does not by itself keep objects alive forever. What matters is whether there is a live path reaching that cycle, not merely a reference count.

Therefore, "I set the `key` variable to `null`" only says that one reference path was dropped. It does not prove that all other paths are gone.

### 2.3. Variable Scope Does Not Equal Object Lifetime

A variable name still appearing in a code block does not by itself guarantee that the JVM keeps the object until the closing brace. Conversely, an object with no remaining local variable name can still be held through a field, a collection, or a running task.

[JLS 17, Section 12.6.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1) describes how optimizing transformations can make an object unreachable earlier than a naive reading of the code suggests.

Examples that need to keep a key alive reliably will use `Reference.reachabilityFence` at the end of the observation section. The purpose is to establish a reachability boundary for the experiment, not to force GC or lock another thread.

### 2.4. You Do Not Need to Learn Every Reference Type to Use This Lesson Correctly

Java also has `SoftReference` and `PhantomReference` with different purposes and rules. `WeakHashMap` uses weak keys; it does not automatically provide a soft policy based on memory pressure or the resource-closing mechanisms of the other types.

Reachability concepts and reference groups are introduced in the [Java 17 java.lang.ref package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html). In this lesson, the focus is on paths that keep keys alive, not on the algorithms of individual garbage collectors.

## 3. From a Key Losing Reachability to Its Mapping Disappearing

### 3.1. Dropping Usage Does Not Trigger an Immediate Synchronous Remove

A conceptual sequence can be pictured as follows:

1. The application drops normal live paths to the key object.
2. The GC determines that the object is in a state eligible for processing via weak references.
3. Eligible weak references are cleared of their link to the target object.
4. Registered references may be placed into a `ReferenceQueue`.
5. The map processes internal notifications and cleans up entries whose keys have become stale.

Do not tie each step to a specific Java statement or a fixed waiting interval.

The [Java 17 WeakReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html) documentation distinguishes the time weak references are cleared from the time they are enqueued; enqueuing may happen at the same time or later.

### 3.2. `ReferenceQueue` Notifies About References, Not Returned Lost Keys

`ReferenceQueue` lets you receive `Reference` objects that have been enqueued. It is not a queue containing full copies of keys that were collected.

In the example below, a separate observer `WeakReference` is registered with its own queue. When `poll` returns that exact reference, we know the observer reference has been enqueued. Do not infer that we have directly read the internal queue of `WeakHashMap`.

[`ReferenceQueue` Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html) is the API reference for `poll` and the reference registration mechanism.

### 3.3. Distinguish Mapping Lookup Visibility from Storage Awaiting Cleanup

OpenJDK 17 implementation detail: `WeakHashMap` uses an internal queue; table access paths and `size` can process entries reported as stale. During cleanup, the implementation unlinks the entry and clears the link to the value.

Because there are multiple steps, a `size` measurement should not be used as proof that all associated memory has been reclaimed immediately. An infrequently accessed map may still hold storage awaiting cleanup; a value still held elsewhere remains alive after the mapping disappears.

That explanation follows the [OpenJDK 17 WeakHashMap source](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/WeakHashMap.java). Do not treat internal method names or specific cleanup timing as a contract across all Java implementations.

## 4. Weak Lifecycle Does Not Mean Identity-Based Key Comparison

`WeakHashMap` is still a hash-table-based `Map`. Lookups follow the key's `equals`/`hashCode` relation; it does not replace `equals` with the `==` operator by default.

Distinguish two axes:

| Axis | Example Question |
| --- | --- |
| Identity by `equals` | Does a new `Key(7)` find an existing mapping for `Key(7)`? |
| Specific object lifetime | Which `Key(7)` object is actually held as the target of the weak reference? |

If two objects are distinct instances but `equals` returns `true`, a new object can find or update an existing mapping. However, keeping the new object alive does not automatically create a strong reference path to the old key object.

Key types must have correct and stable `equals`/`hashCode` while used as keys. Mutating fields used to compute the hash or `equals` can break lookups according to hash map rules; using weak keys does not fix that bug. See the key contract of [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

`WeakHashMap` accepts both a `null` key and `null` values. Therefore, `get` returning `null` may mean an absent key or a mapping with a `null` value; `containsKey` is useful when you need to distinguish them.

The `null` key is not an application object that can lose strong references like `new Object()`. In OpenJDK 17, it is represented by a statically held sentinel object. Do not expect a `null` mapping to expire automatically via GC; call `remove(null)` or `clear` when needed.

## 5. Example 1: Map Behavior While Keys Are Kept Alive

Save as **WeakKeyBasics.java**:

```java
import java.lang.ref.Reference;
import java.util.Map;
import java.util.WeakHashMap;

public class WeakKeyBasics {
    record Key(int id) {}

    public static void main(String[] args) {
        Map<Key, String> map = new WeakHashMap<>();
        Key original = new Key(7);
        Key equalKey = new Key(7);
        Key nullableValueKey = new Key(8);

        map.put(original, "first");
        System.out.println("same object: " + (original == equalKey));
        System.out.println("equal keys: " + original.equals(equalKey));
        System.out.println("lookup equal key: " + map.get(equalKey));
        System.out.println("previous value: " + map.put(equalKey, "updated"));
        System.out.println("size after update: " + map.size());

        map.put(nullableValueKey, null);
        map.put(null, "null-key value");
        System.out.println("null value lookup: " + map.get(nullableValueKey));
        System.out.println("null value key present: " + map.containsKey(nullableValueKey));
        System.out.println("absent key present: " + map.containsKey(new Key(9)));
        System.out.println("null key lookup: " + map.get(null));
        System.out.println("total size: " + map.size());

        System.out.println("removed value: " + map.remove(equalKey));
        System.out.println("original key present: " + map.containsKey(original));
        System.out.println("size after remove: " + map.size());

        Reference.reachabilityFence(original);
        Reference.reachabilityFence(equalKey);
        Reference.reachabilityFence(nullableValueKey);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WeakKeyBasics.java
java WeakKeyBasics
```

Stdout:

```text
same object: false
equal keys: true
lookup equal key: first
previous value: first
size after update: 1
null value lookup: null
null value key present: true
absent key present: false
null key lookup: null-key value
total size: 3
removed value: updated
original key present: false
size after remove: 2
```

The programs in this lesson were compiled with `--release 17` and run on OpenJDK 24.0.2. `--release 17` selects the language/API level and target bytecode; the executing JVM is still the version stated.

### 5.1. Equal Keys Do Not Have to Be the Same Object

The two variables `original` and `equalKey` hold two different record instances, so `==` returns `false`. Their `id` data is equal, so `equals` returns `true`.

`get` with `equalKey` finds `"first"`; `put` with `equalKey` returns the old value and updates it to `"updated"`. The number of mappings remains 1.

This example proves that `WeakHashMap` is not an `IdentityHashMap` by default. It does not prove that the mapping survives after the stored key object is no longer kept alive.

### 5.2. Null Values Are Unrelated to Collection Here

The key `nullableValueKey` has a mapping with a `null` value, while `Key(9)` is absent. `containsKey` distinguishes the two cases.

The `null` key mapping is a separate entry with value `"null-key value"`. The total `size` is 3 before `remove`.

There is no rule where a `null` value automatically causes its key to be collected. Key lifetime depends on the reference graph, not on whether the value happens to be `null`.

### 5.3. Why Keep Both `original` and `equalKey` Alive?

The experiment is testing `Map` behavior, so we do not want the results mixed with keys losing reachability between print statements.

`reachabilityFence` at the end ensures the necessary objects remain alive throughout the observation section. Keeping both alive also avoids relying on assumptions about which object the constructor or `put` chooses as the stored target for an equal key.

Do not use a `put` call with an equal key as a protocol guaranteeing a "change of lifetime ownership" for the mapping.

## 6. Example 2: Observing GC Without Pretending to Control GC

### 6.1. What to Observe

We create three mappings:

- A `held` key kept alive until the end of the measurement section.
- A `null` key.
- A temporary key returned to the caller only via a `WeakReference`.

The `addTemporaryKey` method creates the temporary key and returns, ensuring `main` holds no extra strong variable to that key.

An observer `WeakReference` is registered with its own `ReferenceQueue`. It is a measurement tool; `WeakHashMap` has its own internal mechanism.

### 6.2. Complete Program

Save as **WeakKeyGcObservation.java**:

```java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

public class WeakKeyGcObservation {
    private static WeakReference<Object> addTemporaryKey(
            WeakHashMap<Object, String> map, ReferenceQueue<Object> queue) {
        Object temporary = new Object();
        map.put(temporary, "temporary value");
        return new WeakReference<>(temporary, queue);
    }

    public static void main(String[] args) throws InterruptedException {
        WeakHashMap<Object, String> map = new WeakHashMap<>();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object held = new Object();
        map.put(held, "held value");
        map.put(null, "null-key value");
        WeakReference<Object> observer = addTemporaryKey(map, queue);

        boolean cleared = false;
        boolean enqueued = false;
        boolean removed = false;
        for (int attempt = 0; attempt < 100; attempt++) {
            System.gc();
            Thread.sleep(10);
            cleared = observer.refersTo(null);

            Reference<?> notification;
            while ((notification = queue.poll()) != null) {
                if (notification == observer) {
                    enqueued = true;
                }
            }

            removed = map.size() == 2;
            if (cleared && enqueued && removed) {
                break;
            }
        }

        System.out.println("observer cleared: " + cleared);
        System.out.println("observer enqueued: " + enqueued);
        System.out.println("temporary mapping removed: " + removed);
        System.out.println("held lookup: " + map.get(held));
        System.out.println("null-key lookup: " + map.get(null));
        System.out.println("remaining size: " + map.size());
        Reference.reachabilityFence(held);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 WeakKeyGcObservation.java
java WeakKeyGcObservation
```

**The stdout below is the observed output of one run on OpenJDK 24.0.2, not a result Java guarantees will appear on every run:**

```text
observer cleared: true
observer enqueued: true
temporary mapping removed: true
held lookup: held value
null-key lookup: null-key value
remaining size: 2
```

### 6.3. Three Separately Measured Things

`observer cleared` indicates that the observer reference no longer has a target object. `refersTo(null)` checks this without acquiring a new strong reference via `get`.

`observer enqueued` indicates that the observer reference was retrieved from the experiment's queue. Do not use `isEnqueued` to wait, because queue state can change and that API has been marked deprecated.

`temporary mapping removed` is inferred from `size` being 2 under the conditions that the program only has the three described mappings, no other application thread modifies the map, `held` is kept alive, and the `null` key is not removed. That is not a general formula for detecting all dead keys in an arbitrary map.

The `size` calls also give the implementation opportunities to clean up stale internal entries.

### 6.4. What If the Three Flags Do Not Become True?

The loop runs at most 100 iterations; each iteration hints for GC and sleeps 10 ms. It is not a guarantee that GC must finish within one second, nor does it guarantee a total execution time of exactly one second.

If the observation has not completed, the program still finishes and prints the state it observed. There is no `AssertionError` forcing collection timing to be a correctness condition of the application.

According to [System.gc Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()), this call only suggests that the JVM expend effort toward recycling. It does not guarantee reclaiming a specific object, clearing/enqueuing specific references, or completing at the requested time.

`Thread.sleep` does not create that guarantee either. Looping `System.gc` many times also does not turn a hint into a reliable expiration timer.

### 6.5. Another Run on the Same JVM

OpenJDK/HotSpot supports the following experimental option:

```shell
java -XX:+DisableExplicitGC WeakKeyGcObservation
```

In this lesson's test environment, that run printed:

```text
observer cleared: false
observer enqueued: false
temporary mapping removed: false
held lookup: held value
null-key lookup: null-key value
remaining size: 3
```

This option causes explicit GC requests to be ignored in the running JVM; it does not mean all automatic GC activity is disabled. Other JVMs may not recognize this option.

Both distinct stdout outputs are consistent with the program's purpose. A run that does not yet see the temporary key disappear is not enough to conclude that `WeakHashMap` is leaking. You must analyze live reference paths and whether the GC has actually processed the references yet.

## 7. The Most Important Trap: Values Holding Strong References Back to Keys

### 7.1. Dropping External Variables May Not Drop Paths Holding the Key

If a value has an `owner` field pointing back to the key itself, the graph gains an extra strong path; the [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) documentation explicitly calls out this case:

```text
program --strong--> map --strong--> value --strong--> key
                             entry --weak--> key
```

A weak edge does not neutralize a strong edge. As long as the map is kept alive, the value is still in the map, and the value still holds the key, the key has a path keeping it alive.

Similarly, value A can hold key B while value B holds key A. If both values are held strongly by the map, an indirect cycle can still keep the keys alive as long as the map lives.

This is why you must read the entire object graph, not just look at the `WeakHashMap` type in the declaration.

### 7.2. A Program That Makes the Strong Path Visible

Save as **ValueBackReference.java**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.util.WeakHashMap;

public class ValueBackReference {
    static final class Metadata {
        Object owner;

        Metadata(Object owner) {
            this.owner = owner;
        }
    }

    public static void main(String[] args) {
        WeakHashMap<Object, Metadata> map = new WeakHashMap<>();
        Object key = new Object();
        Metadata metadata = new Metadata(key);
        WeakReference<Object> observer = new WeakReference<>(key);
        map.put(key, metadata);

        key = null;
        metadata = null;
        System.gc();

        Metadata stored = map.values().iterator().next();
        Object owner = stored.owner;
        System.out.println("value holds key: " + (owner != null));
        System.out.println("observer refers to owner: " + observer.refersTo(owner));
        System.out.println("lookup through owner: " + (map.get(owner) == stored));

        stored.owner = null;
        System.out.println("owner field detached: " + (stored.owner == null));
        System.out.println("local owner still finds value: " + (map.get(owner) == stored));

        map.clear();
        System.out.println("size after explicit clear: " + map.size());
        System.out.println("observer still refers to local owner: " + observer.refersTo(owner));
        Reference.reachabilityFence(owner);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ValueBackReference.java
java ValueBackReference
```

Stdout:

```text
value holds key: true
observer refers to owner: true
lookup through owner: true
owner field detached: true
local owner still finds value: true
size after explicit clear: 0
observer still refers to local owner: true
```

This example checks an existing strong reference path. It does not need the GC to perform a successful collection to produce the output above.

### 7.3. How to Read Each Stage

After `key` and `metadata` are set to `null`, the map still holds `Metadata`, and `Metadata` still holds `owner`. Therefore, you can traverse from the value in the map to the key, and then use that key to look up the value itself.

Calling `System.gc` cannot turn a key that still has a valid live path into an unused key just because the map is named `WeakHashMap`.

After `stored.owner` is set to `null`, the local `owner` variable in the program still holds the key. `reachabilityFence` at the end makes this boundary explicit. Clearing only the `owner` field is not enough to make all strong paths disappear.

`clear` explicitly detaches the mappings, so `size` becomes 0. That still does not collect the `owner` object immediately, because the program still holds it.

Three distinct actions are: cutting a reference path, removing a mapping, and the GC reclaiming an object. Do not use the same word "remove" to assume all three have happened.

### 7.4. Choosing Values Appropriate for Auxiliary Purposes

If you want auxiliary data not to keep the primary object alive, the value should contain information that does not strongly lead back to that object: for example, precomputed metrics or detached descriptive data.

You also need to check indirect links through callbacks, enclosing objects, collections, and other values.

Another option is to deliberately use weak references in the value part when it fits the business requirement. That changes the data retention policy: the value can disappear, and readers must accept that.

Do not mechanically replace every field with `WeakReference`. If the application needs data to remain stably present, a weak policy can violate the requirement instead of solving it.

## 8. The Real Key Object Differs from "The Same Business ID"

### 8.1. Why Does the Documentation Mention Identity-Based Keys?

For an object using `Object`'s default `equals`, only that exact object equals itself by identity. Once the object is truly no longer usable, the application does not create a new object and expect it to equal the lost object.

This makes the lifecycle policy easy to understand: auxiliary data follows the exact live object.

The [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html) documentation describes this group of keys as the primary intended use case, while still allowing types that use value-based `equals`.

That is guidance for choosing keys, not `WeakHashMap` changing how equality works for every type.

### 8.2. Value-Based Keys Can Be Recreated, but the Mapping Is Not Promised to Stay

Suppose a call creates a new customer ID object and puts a lookup result. When the call finishes, nothing else holds the stored key object.

A later call may create a new ID object that is `equals` to the old ID. However, the new object does not automatically keep the old object alive, and the old mapping may already have disappeared after GC.

If the goal is to remember results by an ID string across multiple requests, the lifetime of a temporary ID object is usually not the desired retention policy.

An immutable key type keeps `equals`/`hashCode` stable. It does not by itself keep that object alive longer in a weak-key map.

### 8.3. Unintended Sources Retaining Keys

If an experiment does not see a key disappear, check the places that might still be holding it:

- A `HashMap`, list, `static` field, or live manager object.
- A value pointing back to the key.
- A task or callback still holding the related object.
- A data copy containing the key object itself.
- An observation tool or measurement snippet that kept the key it just read.

With `String`, shared data and cached library objects can also make experiments hard to reason about. Do not use a string literal or a shared object and assume only the map references it.

In the GC example, `new Object()` was created in a separate method to intentionally produce an unshared temporary key. That helps reason about the experiment; it still does not control collection timing.

### 8.4. Observation Itself Can Extend Lifetime

`WeakReference.get` returns a normal reference to the target object if it is still alive. If the result is kept in an active variable, the experiment has added a strong path during that period.

`refersTo(null)` is suitable when you only need to ask whether the reference's link has been cleared. `ReferenceQueue` is suitable when you need to track enqueue notifications.

A list holding keys taken from the map or a `HashMap` copying the mappings will strongly hold the copied keys while the copy is in use. Do not keep such a copy during measurement and conclude that `WeakHashMap` fails to release keys.

The `keySet` view alone is not the same as a copy strongly holding all keys. Distinguish views, iterators, and copied-out data.

Reference operations and reachability boundaries are described in [Reference Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html).

## 9. Changes That Can Happen Even Without the Application Calling `remove`

A single-threaded program can still observe mappings shrinking when the GC processes keys. This behavior is described in [WeakHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html). Having no `remove` calls in business code does not mean the contents must remain unchanged.

Valid observations can include a smaller `size`, `isEmpty` changing, or a later lookup no longer finding a mapping that once existed.

This has direct implications for how applications are written:

- Do not use an earlier `size` to guarantee the exact number of entries that will be processed in a later traversal.
- Do not use weak auxiliary data as mandatory proof that a transaction existed.
- When a missing mapping is a normal state of the design, prepare an appropriate way to recompute or skip it.
- When an object must be kept throughout an operation, deliberately hold a strong reference path to the exact object needed.

One important exception in reasoning: if the program strongly holds the exact stored key throughout the entire operation and nothing else removes or modifies it, the GC is not allowed to make that key object disappear on its own. Do not phrase uncertainty as "any entry can vanish arbitrarily even while the key is still in use."

### 9.1. Concurrency Is a Separate Concern

`WeakHashMap` is not synchronized. If multiple threads access it with modifications, an appropriate protection mechanism must be chosen.

`Collections.synchronizedMap` can wrap the map; all accesses must go through the wrapper. When iterating over a collection view with an iterator, you must synchronize on the returned map per the API contract. See [Collections.synchronizedMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

Synchronization protects application thread access. It does not turn weak keys into strong keys and does not forbid the GC from processing a key that is no longer kept alive.

Similarly, a check-then-act sequence still needs to be designed as a consistent business operation when data is shared. A wrapper does not infer the business semantics of the entire sequence.

### 9.2. Fail-Fast Is Not a Notification That a Key Was Collected

Iterators have a fail-fast mechanism for structural modifications under their contract and best-effort limits. Do not write programs relying on `ConcurrentModificationException` to detect that a key died or to guarantee thread safety.

In OpenJDK 17, the GC-driven entry cleanup path does not act like a normal `put`/`remove` call that increments the modification count. An iterator may also temporarily hold the key currently being examined in order to use it.

Therefore, do not assume every GC key removal must throw an exception, nor assume an iterator is an immutable snapshot of the entire map.

## 10. Practical Limits: This Is Not a Complete Cache Policy

### 10.1. No Expiration Time or Entry Limit

`WeakHashMap` can keep a mapping for a very long time if the key is still used elsewhere. It can also lose a mapping sooner than expected if the key is just a temporary object.

It does not define a time-to-live (TTL), does not cap the number of mappings at a business limit, and does not evict the least recently used entry.

Initial capacity is a hash table organization parameter, not the maximum number of entries allowed. Changing the load factor also does not turn key lifetime into an expiration time.

If the requirement is to retain data by time or capacity, choose a policy that expresses that requirement. Do not substitute the question "when does the key stop being alive?" for "when must the data expire?"

### 10.2. Weak Keys Do Not Mean Weak Values

Suppose a key is kept strongly by the application for a long time and the value contains a large array. `WeakHashMap` still holds that array strongly while the mapping exists.

If you choose `Map<K, WeakReference<V>>` or combine weak values, readers must also distinguish: no mapping, wrapper present but target cleared, or usable value present.

You should read the value from a `WeakReference` once into a local variable, then check and use the retrieved value. Two consecutive `get` calls are not a guarantee that the value remains intact between calls if you do not hold it.

This is a different data retention design, not a built-in feature activated by the name `WeakHashMap`.

### 10.3. Do Not Use GC Timing to Close Mandatory Resources

If an operation needs to close files, connections, or release resources at a deterministic time, use an appropriate explicit ownership and closing mechanism.

An entry disappearing on its own is not equivalent to a `close` call having run successfully. `WeakHashMap` does not provide a resource finalization protocol or reliable business notification.

Do not tie application correctness to whether a GC cycle occurs.

### 10.4. Overhead Includes Reference Mechanics and Table Cleanup

The structure still uses hashing, but adds objects/mechanisms for weak references and processing stale entries. An access operation may carry cleanup work.

Do not measure one call and conclude every `get` has constant latency. Hash distribution, table size, and pending cleanup work all affect observed cost.

`WeakHashMap` is a separate implementation class; do not assume every internal optimization detail of `HashMap` is copied into it.

## 11. Choosing Usage and Testing Strategies

### 11.1. A Suitable Scenario

A tool stores auxiliary analysis results for objects kept alive by the main system. Results can be recomputed, missing results are handled normally, and values do not strongly point back to keys.

This is a design where weak keys make sense because auxiliary data should not dictate the lifetime of primary objects.

Before implementing, still answer who holds the map, who holds the keys, whether values indirectly retain keys, and how threads access the map.

### 11.2. Requirements That Should Be Expressed with Different Policies

| Requirement | What Needs to Be Explicitly Designed |
| --- | --- |
| Store mandatory business evidence | A retention mechanism whose lifetime is decided by business rules |
| Keep results for at least a duration | An explicit time-based policy |
| Do not exceed an allowed capacity | An explicit capacity and eviction policy |
| Attach auxiliary data to a live object | Reference relationships and ability to recompute when missing |
| Close resources when an operation ends | Explicit closing workflow and error handling |
| Look up by an ID recreatable across requests | Storage policy keyed by ID, not defaulting to temporary ID object lifetime |

Do not choose a structure merely because it can shrink its `size` on its own.

### 11.3. Separate Map Behavior Tests from GC Observations

Tests of `Map` behavior can hold keys strongly and verify `equals`/`hashCode`, value updates, `remove`, `null` handling, and how the application handles missing data.

GC experiments should:

1. Intentionally create unshared temporary keys.
2. Avoid holding copies of keys in measurement data.
3. Use observer references and a queue if needed.
4. Have a finite number of observation attempts.
5. Clearly report whether the effect was observed or not, without treating an arbitrary wait limit as a JVM contract.
6. Separately inspect strong retention paths if results differ from expectations.

To test handling of "no auxiliary data," you can directly create the missing-mapping situation with `remove`/`clear` in business tests. There is no need to force GC to act as a timer to verify that branch.

If you manually call `clear` on a `WeakReference` you created, note clearly that it is an explicit reference clear; do not treat it as proof that GC collected the key or that `WeakHashMap` cleaned up its internal reference.

## 12. Self-Check Exercises

### Exercise 1. Why Does `put` Not Guarantee Keeping a Key Alive?

An object is only held by a `WeakHashMap` as a key; the value is data that does not point to that object. Does having a mapping in the map prevent the key from being collected?

**Answer hint:** The edge from the entry to the key is weak, so the mapping itself does not keep the key alive via a strong reference. The timing of GC processing is still not guaranteed.

### Exercise 2. Why Is Setting `key` to `null` Not Enough?

After `put(key, metadata)`, `metadata.owner` still equals `key`. Does setting the `key` variable to `null` leave the key only weakly referenced?

**Answer hint:** Not yet. If the map is still alive, the path `map → metadata → owner` still strongly holds the key.

### Exercise 3. Can an Equal Key Keep the Old Object Alive?

A new `Key(12)` is created that is `equals` to the stored key. Does holding only the new object automatically keep the old object alive?

**Answer hint:** No. The `equals` relation is an equality rule, not a reference path from the new object to the old object.

### Exercise 4. Is Seeing No Size Decrease After One Second a Bug?

After `System.gc` and a sleep interval, `size` remains the same. Can you conclude that `WeakHashMap` is not working?

**Answer hint:** No. There is no guarantee that GC cleared the reference, enqueued it, and cleaned up the mapping within that limit; you also need to check whether any strong paths remain.

### Exercise 5. Why Does a Large Value Still Persist?

The application holds the key strongly for a long time. The value is a large array used nowhere else. Does `WeakHashMap` automatically hold values weakly?

**Answer hint:** No. The value is still held strongly by the map while the mapping exists; weakness is a policy for keys.

### Exercise 6. Does the `null` Key Expire Automatically?

Put `null` → data into a `WeakHashMap` and keep no additional key variable. Should you wait for the `null` entry to be collected?

**Answer hint:** No. `null` is not a temporary key object that can lose reachability; the OpenJDK implementation uses a statically held sentinel object. When you need to remove that entry, remove it explicitly.

### Exercise 7. Does Synchronization Freeze the Map?

Wrap a `WeakHashMap` with `synchronizedMap` and synchronize properly during iteration. Are keys that are no longer kept alive prevented from being collected just because the map is synchronized?

**Answer hint:** No. Protecting application access does not change the reference policy toward keys.

### Exercise 8. Does a Measurement Copy Skew the Experiment?

Copy the visible keys into a list and keep the list throughout the GC experiment. What has changed?

**Answer hint:** The list strongly holds the copied key objects. The measurement tool itself can extend their lifetime.

### Exercise 9. What Does `poll` Return?

A `WeakReference` is registered with a `ReferenceQueue` and later appears when polling. Does `poll` return the old key object or the reference object?

**Answer hint:** The enqueued reference object. It is not a copy of the key to continue using as before.

### Exercise 10. When Should Another Policy Be Chosen?

A result table needs to keep at most N entries by most recent access time. Does using `WeakHashMap` alone meet the requirement?

**Answer hint:** No. You need a capacity and access-based eviction policy; key object lifetime does not express that rule.

## 13. References

- [WeakHashMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak key contract, strong values, `null`, and GC-driven changes.
- [WeakReference — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reference processing and enqueue timing.
- [Reference — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): `get`, `refersTo`, `clear`, and `reachabilityFence`.
- [ReferenceQueue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): queue for reference notifications.
- [System.gc — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()): limits of explicit GC requests.
- [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `equals`, `hashCode`, and mutable key contracts.
- [Collections.synchronizedMap — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)): rules for accessing through the wrapper and synchronizing during iteration.
- [JLS 17, Section 12.6.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6.1): object reachability and lifetime optimizations.
- [WeakHashMap.java — OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/WeakHashMap.java): `null` sentinel object, internal queue, entry cleanup, and iterator. These details are tied to the implementation version and do not replace the API contract.
