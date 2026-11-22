# Java Memory Leaks Caused by `static`, Caches, and Unremoved Registrations

## 1. The Problem: Why Does Java Still Leak Memory Even with GC?

Java manages memory for objects based on **reachability**. The garbage collector (GC) can reclaim objects that no longer have an appropriate reference path from GC roots. However, if a program **still holds strong references** to objects that no longer have business value, the GC cannot know they are "no longer needed" and will continue retaining their memory.

For example:

```java
static final java.util.List<byte[]> DATA =
        new java.util.ArrayList<>();
```

If the application keeps adding arrays to DATA indefinitely without removing elements, each array can remain reachable through a reference path from the class/runtime to the static list and then to the element. Even though no code needs the old data anymore, the GC is not allowed to collect the arrays being kept alive.

Similarly:

- A **static collection** holds references to sessions, objects, or callback closures.
- A **cache** lacks size limits, expiration, eviction, or invalidation.
- A **listener/observer registration** is added to a long-lived event source without calling `remove/unsubscribe`.
- A **ThreadLocal** on a thread pool retains request context across multiple tasks.
- A **scheduled task / callback / lambda** retains a large object graph through a captured reference.

This is a form of *logical memory leak* or *unintended object retention*. It differs from native resource leaks such as failing to close a file descriptor/socket, although both issues can occur together.

> **Core principle:** "No longer used" **is not synonymous with** "no longer reachable." You must **sever the right strong reference paths** based on lifecycle/ownership, rather than waiting for `System.gc()` to fix a flawed design.

In this article, all standalone examples use Java 17+, and stdout is chosen so that it can be verified **without depending on GC timing**.

## 2. Object, Reference, and GC Roots Model

Suppose a program has a graph:

```text
GC roots
   │
   └── class/runtime
          │
          └── static SessionRegistry.SESSIONS
                 │
                 └── ArrayList
                        │
                        ├── Session A ──> byte[] payload
                        └── Session B ──> image/metadata...
```

If the static list remains reachable, the elements and the object graph from each element can remain reachable. The GC does not "delete an object because it is too old" unless the application itself or an appropriate collection/cache mechanism severs the reference path.

A **GC root** is a runtime concept: live references from frames/threads, live class/static state, JNI/runtime handles, and VM-specific sources. A static reference is often an important retention path, but **not every class/static field stays alive forever until the process terminates**; class loading/unloading and class-loader lifetime also play a role.

### Three Concepts to Separate

| Concept | Question |
| --- | --- |
| Object reachable | Is there still a reference path from appropriate roots? |
| Object useful | Does the application still need this data for business purposes? |
| Object collected | Has the GC actually reclaimed the memory? |

An object can be reachable yet not useful: that is the exact sign of a retention leak. It can also be no longer reachable yet not collected because the GC has not run yet. Therefore, all tests in this article check **element counts/reference paths** rather than asserting that the GC has collected at a specific moment.

## 3. Mistake 1: static List Growing Without Bound

Create **`UnboundedStaticRegistryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class SessionRegistry {
    static final List<StringBuilder> ACTIVE =
            new ArrayList<>();

    static void add(StringBuilder session) {
        ACTIVE.add(session);
    }
}

public class UnboundedStaticRegistryDemo {
    public static void main(String[] args) {
        for (int i = 1; i <= 3; i++) {
            StringBuilder data =
                    new StringBuilder("session-" + i);
            SessionRegistry.add(data);
        }

        System.out.println(SessionRegistry.ACTIVE.size());
        System.out.println(SessionRegistry.ACTIVE.get(0));
    }
}
```

```bash
javac UnboundedStaticRegistryDemo.java
java UnboundedStaticRegistryDemo
```

```text
3
session-1
```

The code does not "leak" because it creates StringBuilder instances, but because **each reference is added to ACTIVE and there is no removal policy**. After the loop finishes, the local data variable is no longer used, yet SessionRegistry.ACTIVE still holds the references.

As the number of requests grows into the millions, a similar static list can cause the live heap to grow over time. With payloads containing many other objects, the **retained size** can be much larger than the size of the list itself.

**Distinction:** A static list *intentionally* holding active sessions is not wrong. The mistake occurs when closed/expired sessions are still retained.

## 4. Do Not Confuse `static final` with an Immutable Object

In the example:

```java
static final List<String> ITEMS = new ArrayList<>();
```

`final` only prevents **reassigning the field reference** to another list. It does not prevent:

```java
ITEMS.add("A");
ITEMS.add("B");
ITEMS.clear();
```

These methods mutate **the contents of the list itself**. Therefore, a `static final Map` or `static final List` can still cause memory retention if it grows without bound.

### Be Careful with Constant-Like Declarations

`static final int LIMIT = 100` is a primitive value and does not extend the lifetime of millions of objects. In contrast, `static final Map<Key,Value> CACHE` can hold onto a large object graph. You should not lump all static fields together into an "always leaks" category; **the object type, rate of data insertion, and lifecycle** are the deciding factors.

## 5. Fixing the Registry: Adding Ownership-Based Removal Operations

Create **`RegistryLifecycleDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class SessionRegistry {
    private static final Map<String, Session> SESSIONS =
            new HashMap<>();

    static void open(Session session) {
        SESSIONS.put(session.id(), session);
    }

    static void close(String id) {
        SESSIONS.remove(id);
    }

    static int activeCount() {
        return SESSIONS.size();
    }

    private SessionRegistry() {
    }
}

record Session(String id, String user) {
}

public class RegistryLifecycleDemo {
    public static void main(String[] args) {
        SessionRegistry.open(new Session("1", "An"));
        SessionRegistry.open(new Session("2", "Binh"));

        System.out.println(SessionRegistry.activeCount());
        SessionRegistry.close("1");
        System.out.println(SessionRegistry.activeCount());
    }
}
```

```bash
javac RegistryLifecycleDemo.java
java RegistryLifecycleDemo
```

```text
2
1
```

`remove(id)` severs the reference edge from the map entry to the session object. If there are no other strong paths, the session can become unreachable.

### The Important Part Is Not the Method Name

- Who **calls close** when a user logs out, a timeout occurs, or a request ends?
- Is there any exception code path that forgets to close?
- If `open` is called with a duplicate id, does the replaced old entry require external cleanup?
- Does the registry support concurrent access?
- Does app shutdown release owned registrations/resources?

The example uses `HashMap` because it runs single-threaded. In production, when multiple threads access it, proper synchronization or a concurrent data structure is required; switching to `ConcurrentHashMap` **does not fix a memory leak by itself**.

## 6. "Clearing Everything" Is Not Always the Solution

Calling `CACHE.clear()` indiscriminately can break functionality if the entries are still needed. A proper retention policy needs to define:

1. **Owner**: who creates it and who is responsible for removing it?
2. **Lifetime**: is the entry valid for a session, request, transaction, or the entire application?
3. **Maximum size**: does the cache have an element count limit or a total memory weight limit?
4. **Expiry**: does it expire by time, idle time, or a business event?
5. **Invalidation**: when the source data changes, which entries must be removed?
6. **Concurrency**: are additions, removals, and reads thread-safe?
7. **Failure paths**: do exceptions, cancellations, and timeouts perform cleanup?
8. **Monitoring**: are live entries, hit rate, and eviction count observed?

**Static scope typically lives longer** than request scope. Do not store request data in static structures without a clear reason and lifecycle policy.

## 7. Caches Differ from Registries, but Both Hold Strong References

A **registry** typically tracks objects that are currently registered or active. A **cache** holds copies of results to avoid repeated computation or retrieval. They have different removal semantics:

| Structure | When is an element retained? | When must it be removed? |
| --- | --- | --- |
| Active session registry | While the session is active | Logout, timeout, shutdown |
| Listener registry | While the listener has a valid subscription | Unsubscribe, component close |
| Memoization cache | While the result remains useful | Eviction, expiry, invalidation |
| Request context | While the request is being processed | `finally` after the request |
| ThreadLocal context | While the context belongs to the current task | `remove()` at the end of the task |
| Pending task queue | While work has not yet run/been canceled | Completion, cancellation, rejection |
| Static singleton | Service following the app lifecycle | App/classloader shutdown |

A cache may **intentionally retain** objects; the problem is not "holding a reference," but holding it **uncontrollably after its benefit has ended**.

## 8. Mistake 2: Memoization Cache Growing Without Bound

Create **`UnboundedCacheDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class NameCache {
    private static final Map<Integer, String> CACHE =
            new HashMap<>();

    static String valueFor(int id) {
        return CACHE.computeIfAbsent(
                id, key -> "user-" + key);
    }

    static int size() {
        return CACHE.size();
    }
}

public class UnboundedCacheDemo {
    public static void main(String[] args) {
        for (int id = 1; id <= 4; id++) {
            NameCache.valueFor(id);
        }

        System.out.println(NameCache.size());
        System.out.println(NameCache.valueFor(2));
        System.out.println(NameCache.size());
    }
}
```

```bash
javac UnboundedCacheDemo.java
java UnboundedCacheDemo
```

```text
4
user-2
4
```

`computeIfAbsent` avoids recomputing for an existing key. However, if **the number of unique keys grows without bound**, CACHE can retain every key/value for the entire lifetime of the app or classloader.

This is especially dangerous when the key is a request ID/UUID/timestamp, causing the hit rate to approach 0 while the cache still keeps growing.

### Do Not Confuse Hit Rate with Correctness

A cache with a high hit rate can still retain millions of stale entries. A cache with a low hit rate can waste memory and CPU without providing any benefit. You need **size limits**, an eviction/expiry policy, and payload size evaluation.

## 9. Bounding a Cache with LRU: Simple Java 17 Pattern

`LinkedHashMap` can be configured for **access-order** and override `removeEldestEntry` to keep a maximum number of entries. This is a single-threaded example, not a production-grade concurrent cache.

Create **`BoundedLruCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

class LruCache<K, V> extends LinkedHashMap<K, V> {
    private final int maximum;

    LruCache(int maximum) {
        super(16, 0.75f, true);
        if (maximum < 1) {
            throw new IllegalArgumentException(
                    "maximum must be positive");
        }
        this.maximum = maximum;
    }

    @Override
    protected boolean removeEldestEntry(
            Map.Entry<K, V> eldest) {
        return size() > maximum;
    }
}

public class BoundedLruCacheDemo {
    public static void main(String[] args) {
        LruCache<String, String> cache =
                new LruCache<>(2);

        cache.put("A", "alpha");
        cache.put("B", "beta");
        cache.get("A");
        cache.put("C", "gamma");

        System.out.println(cache.size());
        System.out.println(cache.containsKey("A"));
        System.out.println(cache.containsKey("B"));
        System.out.println(cache.get("C"));
    }
}
```

```bash
javac BoundedLruCacheDemo.java
java BoundedLruCacheDemo
```

```text
2
true
false
gamma
```

When `get("A")` is called, A becomes most recently used. Adding C exceeds the 2-entry limit, so B is the eldest and is evicted. The memory for B's key/value is not **guaranteed** to be reclaimed immediately, but the cache no longer retains entry B.

### Limitations of the Example

- `LinkedHashMap` is not thread-safe.
- A maximum number of entries does **not** mean a byte limit: a single value can be very large.
- Eviction does not close `AutoCloseable` resources inside a value unless your code implements separate cleanup.
- A production cache needs to consider TTL, concurrency, weights, metrics, cache stampede, and errors.
- `removeEldestEntry` does not necessarily run when the app stops adding entries; TTL still requires its own mechanism.

## 10. TTL: Time-Based Expiration Without Relying on GC

A cache can allow an entry to live for at most a duration measured against a clock. **Clock injection** is chosen so that tests are deterministic without `Thread.sleep`.

Create **`TtlCacheDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.function.LongSupplier;

class TtlCache<K, V> {
    private record Entry<V>(V value, long expiresAt) {
    }

    private final Map<K, Entry<V>> entries = new HashMap<>();
    private final LongSupplier clock;
    private final long ttlMillis;

    TtlCache(LongSupplier clock, long ttlMillis) {
        if (ttlMillis <= 0) {
            throw new IllegalArgumentException("ttl must be positive");
        }
        this.clock = clock;
        this.ttlMillis = ttlMillis;
    }

    void put(K key, V value) {
        entries.put(key,
                new Entry<>(value, clock.getAsLong() + ttlMillis));
    }

    V get(K key) {
        Entry<V> entry = entries.get(key);
        if (entry == null) {
            return null;
        }
        if (clock.getAsLong() >= entry.expiresAt()) {
            entries.remove(key);
            return null;
        }
        return entry.value();
    }

    int size() {
        return entries.size();
    }
}

public class TtlCacheDemo {
    public static void main(String[] args) {
        final long[] clock = {1000L};
        TtlCache<String, String> cache =
                new TtlCache<>(() -> clock[0], 100L);

        cache.put("key", "cached");
        System.out.println(cache.get("key"));

        clock[0] = 1100L;
        System.out.println(cache.get("key") == null);
        System.out.println(cache.size());
    }
}
```

```bash
javac TtlCacheDemo.java
java TtlCacheDemo
```

```text
cached
true
0
```

The entry expires at 1100 (1000 + TTL 100). At time 1100, get removes the entry and returns null. This is **lazy expiration**: an expired entry that is not read again may **still remain in the map**.

In a real-world system, to guarantee a memory bound, you need to add a **max size and appropriate proactive expiry/periodic cleanup**, or use a cache library that already has well-defined policies.

**Note on time sources:** For durations within an application, `System.nanoTime()` is suitable for measuring elapsed time; `currentTimeMillis()` is subject to wall-clock adjustments. The example uses a simulated clock for testing purposes and does not recommend implementing production TTL on your own with just this arithmetic.

## 11. Cache Invalidation When Source Data Changes

A cache with a bounded size but stale data can still cause logic bugs. When the database changes, the corresponding entry needs to be updated or invalidated.

Example pattern:

```java
void onUserUpdated(long userId) {
    userCache.remove(userId);
}
```

This is an **illustrative method snippet**; no `userCache` is declared standalone here.

The cache policy must answer:

- Who knows about the user-changed event?
- Should entries be removed by one key or multiple secondary keys?
- Does the cache value contain references to shared mutable objects?
- Can another request re-insert the old value while invalidation is happening?
- If refresh fails, should the stale result be kept, retried, or should the exception be propagated?

**Cache correctness and memory safety are two separate responsibilities**. Eviction fixes retention, whereas invalidation fixes freshness; usually both are needed.

## 12. Both Cache Keys and Values Can Retain Object Graphs

`Map<K,V>` typically holds strong references to both the key and the value. A small key does not mean a small value; a single value can hold:

```text
CACHE
 └── entry
      ├── key: UserId
      └── value: Report
                 ├── List<Detail>
                 ├── byte[] attachment
                 └── SessionContext
```

If Report accidentally references SessionContext, the cache can extend the lifetime of the entire request graph even though you only intended to keep a report summary.

**Review retained size:** Inspect the fields of cached objects and their nested references. Sometimes the right solution is to store a **small DTO/immutable snapshot** rather than the entire entity/session/request object.

A cache with a maximum of 100 entries where each value is 100 MB can still cause severe memory pressure. Limiting by **bytes/weight** matters more than entry count in cases where payloads vary greatly in size.

## 13. Do Not Use `WeakReference` as a Universal Solution

`WeakReference<T>` does not keep the referent alive if it is only weakly reachable. However:

- The result of `get()` can become null at a time decided by the GC.
- A cache of weak values can lose entries unexpectedly under memory pressure.
- The cache's own metadata/keys/structures can still accumulate if poorly managed.
- Weak references do **not** define TTL, size, eviction, or ownership by themselves.
- Do not write business logic that requires a referent to stay alive until a deadline based on a weak reference.

Create **`WeakReferenceDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println(weak.get() != null);
        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("strong variable cleared");
    }
}
```

```bash
javac WeakReferenceDemo.java
java WeakReferenceDemo
```

```text
true
strong variable cleared
```

The example intentionally does **not** assert `weak.get() == null` after System.gc: GC clearing a weak reference is non-deterministic.

`Reference.reachabilityFence(strong)` keeps the referent strongly reachable up to the fence, giving the example a valid basis to check `weak.get() != null`. After the clearing line, we only confirm the assignment, without asserting that the referent has been collected.

## 14. `WeakHashMap` Has Weak Keys, but the Value Still Matters

`WeakHashMap<K,V>` holds weak references to its keys; an entry can be removed after the key is no longer strongly reachable from elsewhere. However, **the value is normally strongly held** inside the entry while the entry still exists.

Particularly dangerous is the case where the value **references back to the key**:

```text
live WeakHashMap
   │
   └── entry (weak key, strong value)
                         │
                         └── value.owner ──> key
```

When the value has a strong path back to the key, the key can remain strongly reachable from the map through the value, preventing the weak-key policy from letting the entry disappear as the author expected.

### Structural Example (No GC Assumptions)

Create **`WeakMapBackReferenceDemo.java`**:

```java
import java.util.WeakHashMap;

record Holder(Object owner) {
}

public class WeakMapBackReferenceDemo {
    public static void main(String[] args) {
        WeakHashMap<Object, Holder> map =
                new WeakHashMap<>();

        Object key = new Object();
        map.put(key, new Holder(key));

        System.out.println(map.size());
        System.out.println(map.get(key).owner() == key);
    }
}
```

```bash
javac WeakMapBackReferenceDemo.java
java WeakMapBackReferenceDemo
```

```text
1
true
```

This is a retention pattern through the value. Do not try to prove it by waiting for GC; observe the object graph and the semantics of the map. **Weak keys offer no protection** when another strong reference path retains the key.

## 15. Mistake 3: Registering a Listener Without Unsubscribing

An event source typically holds its list of listeners using **strong references**. When a component registers a listener, the event source can retain the component or captured objects **longer than the intended lifecycle**.

Visualize:

```text
static EventHub
    └── LISTENERS
         └── listener object/lambda
              └── captured ScreenController
                   ├── big view model
                   └── resources / UI state
```

Closing the screen or dropping the local controller variable is **not enough** if EventHub still retains the listener.

### Faulty Example and How to Detect It

Create **`LeakingListenerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class EventHub {
    private static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static void subscribe(Runnable listener) {
        LISTENERS.add(listener);
    }

    static int listenerCount() {
        return LISTENERS.size();
    }

    static void publish() {
        for (Runnable listener : LISTENERS) {
            listener.run();
        }
    }
}

final class Screen {
    private final String name;

    Screen(String name) {
        this.name = name;
        EventHub.subscribe(() ->
                System.out.println("event:" + name));
    }
}

public class LeakingListenerDemo {
    public static void main(String[] args) {
        new Screen("A");
        new Screen("B");

        System.out.println(EventHub.listenerCount());
        EventHub.publish();
    }
}
```

```bash
javac LeakingListenerDemo.java
java LeakingListenerDemo
```

```text
2
event:A
event:B
```

`Screen` objects are not stored directly after `new Screen(...)`, yet the listeners retain the captured `name`. In this example, the listener captures a String, **not necessarily retaining the entire Screen object**. If the lambda accesses `this` or instance methods/fields of Screen, it can retain the entire Screen.

To avoid overstating the claim, understand this example as retaining **listeners and captured name strings**. The next example illustrates retaining the entire owner object.

## 16. A Lambda Capturing `this` Can Retain the Entire Component

Create **`ListenerCapturesOwnerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Hub {
    private static final List<Runnable> LISTENERS =
            new ArrayList<>();

    static void subscribe(Runnable listener) {
        LISTENERS.add(listener);
    }

    static int count() {
        return LISTENERS.size();
    }
}

final class Screen {
    private final String name;
    private final byte[] snapshot = new byte[1024];

    Screen(String name) {
        this.name = name;
        Hub.subscribe(this::refresh);
    }

    private void refresh() {
        System.out.println(name + ":" + snapshot.length);
    }
}

public class ListenerCapturesOwnerDemo {
    public static void main(String[] args) {
        new Screen("home");
        System.out.println(Hub.count());
    }
}
```

```bash
javac ListenerCapturesOwnerDemo.java
java ListenerCapturesOwnerDemo
```

```text
1
```

`this::refresh` creates a listener object whose receiver is the Screen instance. When Hub holds the callback, Screen (and the snapshot array) remain reachable through the callback.

**Important:** The Screen may no longer be visible in the UI and no longer referenced by any local variable, yet the subscription still remains in Hub. This is a classic scenario where a heap profiler shows a retained path from a static field to an "already closed" object.

To fix this, you need to store **the callback/subscription handle itself** and unregister when the owner closes.

## 17. Fixing the Listener: Keep the Reference and Call `unsubscribe`

Create **`ListenerUnsubscribeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Hub {
    private final List<Runnable> listeners =
            new ArrayList<>();

    void subscribe(Runnable listener) {
        listeners.add(listener);
    }

    void unsubscribe(Runnable listener) {
        listeners.remove(listener);
    }

    int count() {
        return listeners.size();
    }

    void publish() {
        for (Runnable listener : List.copyOf(listeners)) {
            listener.run();
        }
    }
}

final class Screen implements AutoCloseable {
    private final Hub hub;
    private final Runnable listener;

    Screen(Hub hub) {
        this.hub = hub;
        this.listener = this::refresh;
        hub.subscribe(listener);
    }

    private void refresh() {
        System.out.println("screen refreshed");
    }

    @Override
    public void close() {
        hub.unsubscribe(listener);
    }
}

public class ListenerUnsubscribeDemo {
    public static void main(String[] args) {
        Hub hub = new Hub();

        try (Screen screen = new Screen(hub)) {
            System.out.println(hub.count());
            hub.publish();
        }

        System.out.println(hub.count());
        hub.publish();
    }
}
```

```bash
javac ListenerUnsubscribeDemo.java
java ListenerUnsubscribeDemo
```

```text
1
screen refreshed
0
```

- Screen creates the callback once and stores it in the `listener` field.
- Hub stores the callback on subscribe.
- `close` removes the exact callback that was registered.
- `try-with-resources` guarantees close is called when the block ends.
- After close, hub no longer has the listener; `publish()` no longer prints refresh.
- The example is single-threaded; a production event bus requires a concurrency policy.

**An easily forgotten point:** Do not call `unsubscribe(this::refresh)` by recreating the method-reference expression and assuming it will always equal the registered callback. The identity/equality of functional objects is not a contract guaranteeing that separate expressions produce the same object. **Keep the handle or the exact listener reference**.

## 18. Designing a Better `AutoCloseable` Subscription Handle

An event source API can return a **subscription handle** upon registration so that the caller does not have to remember the exact listener object when removing it.

Create **`SubscriptionHandleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class EventSource {
    private final List<Runnable> listeners =
            new ArrayList<>();

    AutoCloseable subscribe(Runnable listener) {
        Objects.requireNonNull(listener);
        listeners.add(listener);

        return new AutoCloseable() {
            private boolean closed;

            @Override
            public void close() {
                if (!closed) {
                    closed = true;
                    listeners.remove(listener);
                }
            }
        };
    }

    void publish() {
        for (Runnable listener : List.copyOf(listeners)) {
            listener.run();
        }
    }

    int count() {
        return listeners.size();
    }
}

public class SubscriptionHandleDemo {
    public static void main(String[] args) throws Exception {
        EventSource events = new EventSource();

        try (AutoCloseable subscription =
                     events.subscribe(() ->
                             System.out.println("received"))) {
            events.publish();
            System.out.println(events.count());
        }

        events.publish();
        System.out.println(events.count());
    }
}
```

```bash
javac SubscriptionHandleDemo.java
java SubscriptionHandleDemo
```

```text
received
1
0
```

`subscribe` returns an AutoCloseable so the client can express **the subscription's lifetime as a resource scope**. This handle closes idempotently (calling it again does not perform a second removal).

### Things to Consider in a Real Implementation

- `AutoCloseable.close()` can declare `throws Exception`; the API can return a separate interface like `Subscription extends AutoCloseable` with a narrower signature.
- If a listener is registered multiple times, a single removal may delete only one occurrence; a duplicates policy should be defined.
- In concurrent event sources, subscribe/close/publish require synchronization or a concurrent collection.
- A callback that is currently executing may continue running even after unsubscribe; the contract for *in-flight events* must be clear.
- An event source that lives shorter than its owner also needs its own shutdown/clear.

## 19. Why Is `List.copyOf(listeners)` Used During Publish?

If an event handler unsubscribes while Hub is iterating over `ArrayList` directly with a for-each loop, it can cause a `ConcurrentModificationException` or unexpected behavior.

Taking a snapshot:

```java
for (Runnable listener : List.copyOf(listeners)) {
    listener.run();
}
```

lets you iterate over an unchanging list during the callback loop **in the single-threaded demo**. It does **not** automatically make subscribe/unsubscribe from multiple threads thread-safe; achieving concurrency safety requires coordinating writes/reads.

The snapshot also holds references to listeners for the duration of publish, so unsubscribing mid-publish does not guarantee the callback will not be called during the current publish pass.

**Lesson:** Memory retention, mutation semantics, and concurrency are separate contracts that must be designed and tested.

## 20. Listeners Can Be Closures Retaining Large Payloads

A listener lambda can capture objects, not just a few values.

Create **`CapturedPayloadDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CapturedPayloadDemo {
    private static final List<Runnable> CALLBACKS =
            new ArrayList<>();

    public static void main(String[] args) {
        byte[] report = new byte[2048];

        CALLBACKS.add(() ->
                System.out.println(report.length));

        System.out.println(CALLBACKS.size());
        CALLBACKS.get(0).run();

        CALLBACKS.clear();
        System.out.println(CALLBACKS.isEmpty());
    }
}
```

```bash
javac CapturedPayloadDemo.java
java CapturedPayloadDemo
```

```text
1
2048
true
```

The lambda reference is held in static CALLBACKS; the listener captures `report`, keeping the array potentially reachable longer than the original main code needed. `clear` removes the path from the list; there is no assertion that the GC runs immediately.

### Reducing Retention

- If the handler only needs an ID, capture an **immutable ID** instead of the entire request context.
- Unsubscribe when the owner closes.
- Avoid re-registering duplicate listeners on every render/screen open.
- If the event system supports weak listeners, understand the semantics thoroughly before using them; a weak listener can disappear while the caller still thinks it is active.
- Do not build listeners that rely on GC merely to avoid remembering cleanup.

## 21. Duplicate Registrations and Growing Listener Counts Across Screen Opens

A leak-prone pattern:

```java
void onOpen() {
    eventHub.subscribe(this::onEvent);
}
```

If `onOpen` is called multiple times and adds a new callback each time, the number of listeners grows. There is no "register once per instance" invariant unless the API enforces it.

A good component lifecycle needs:

1. The subscription is established **exactly once** in the appropriate start/open phase.
2. The handle is held by the owner.
3. Stop/close calls unsubscribe **at the right time**.
4. Repeated stop/close calls do not cause errors or accidentally remove another instance's subscription.
5. If restartable, a new subscription must be created and state fields must be updated validly.
6. Test multiple open/close cycles and assert that the count returns to baseline.

**Do not use an arbitrary boolean guard** if multiple threads/async callbacks can race. When the lifecycle is concurrent, an appropriate state machine and synchronization are required.

## 22. Other Registration Types Carry the Same Risk

It is not just UI event buses; the exact same reference structure exists in:

- The Observer pattern and service callbacks.
- Property change listeners.
- Message subscriptions and pub/sub consumers.
- Scheduled tasks, timers, and executor queues.
- Database change listeners.
- Metrics registries attaching labels to an object graph.
- Monitoring/tracing hooks.
- Watch services / file watchers.
- Global event bus.
- Application contexts holding beans/request data in the wrong scope.

**How to trace it:** Which object **registers** with a manager that outlives it? Does the manager hold a **strong or weak** reference? Is there a `close/unsubscribe/remove/cancel` API, and who calls it?

Being able to answer these four questions is usually faster than adding a bunch of null assignments.

## 23. `ThreadLocal` in a Thread Pool: Leaks Through Long-Lived Worker Threads

`ThreadLocal<T>` associates a value with the current thread. When using a thread pool, threads are **reused**, so data from a previous task can remain long after the task completes if `remove()` is not called.

Conceptual retention path:

```text
live worker Thread
   └── ThreadLocalMap
         └── entry
               └── value: RequestContext
                     └── large payload/session references
```

Even though the ThreadLocal key uses a weak reference internally, values can continue to be retained until an appropriate cleanup mechanism runs; do not treat the weak key as automatic on-time cleanup.

### Safe and Deterministic Example

Create **`ThreadLocalCleanupDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            Future<?> first = pool.submit(() -> {
                CONTEXT.set("request-1");

                try {
                    System.out.println(CONTEXT.get());
                } finally {
                    CONTEXT.remove();
                }
            });
            first.get();

            Future<?> second = pool.submit(() ->
                    System.out.println(CONTEXT.get() == null));
            second.get();
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

```text
request-1
true
```

`newSingleThreadExecutor` reuses one worker thread for both tasks in the example. `Future.get()` is used to wait for tasks to finish and produce a clear output order. `finally` ensures removal even when a task throws an exception.

**Do not merely reset with `CONTEXT.set(null)` and assume it is enough:** `remove()` is the explicit API way to remove the ThreadLocal entry from the thread-local map. Setting null has different semantics and easily obscures the lifecycle.

## 24. What Happens If You Forget `ThreadLocal.remove()`?

Logically, a subsequent task on the same worker thread can read the leftover request context from the previous task. This poses both a **memory retention** risk and a **cross-request data contamination** risk.

**Intentionally lifecycle-broken code** (no cleanup):

```java
static final ThreadLocal<String> REQUEST =
        new ThreadLocal<>();

void handleRequest(String id) {
    REQUEST.set(id);
    // process request; forgot REQUEST.remove()
}
```

This is only an illustrative snippet inside a valid class, not a standalone program.

### Fix

```java
void handleRequest(String id) {
    REQUEST.set(id);
    try {
        // Process request.
    } finally {
        REQUEST.remove();
    }
}
```

**Does not promise to eliminate every leak automatically:** If the request context has already been captured into a static callback/cache, removing the ThreadLocal only severs **one reference path**. You must inspect the entire graph.

In application servers, thread pools live for a long time, so ThreadLocal cleanup is especially critical.

## 25. Task Queues and Cancellation Can Also Retain Callbacks

A `Runnable` or `Callable` can capture large objects. If the task is queued in a long-lived executor and is neither executed nor removed, the queue retains the task → captured references.

A scheduled future with a long delay can also retain a payload that the app assumes has been canceled. `cancel` and executor cleanup policies have implementation/configuration specifics, so you must design according to the actual APIs.

**Questions:**

- Is there a limit on pending tasks/queue capacity?
- Does canceling a job remove the reference to the task from the storage structure, and when?
- Does the task capture the entire request/controller instead of an immutable identifier?
- Are pending futures removed from the registry after completion?
- Are shutdown and shutdownNow handled clearly?
- Are there timeout, backpressure, and cancellation contracts?

This is the **same pattern**: a long-lived owner retaining a closure/object graph beyond its needed lifecycle.

## 26. Resource Leaks and Heap Memory Leaks Are Two Distinct Classes of Problems

A FileInputStream object can go out of scope in Java while the file descriptor is still not closed on time. That is a **resource leak**, and should not be treated as "the GC will definitely clean it up."

Conversely, a static list containing thousands of byte arrays is **heap retention**, even though it holds no external resource.

| Symptom | Heap retention | Resource leak |
| --- | --- | --- |
| What is retained | Java object graphs | File/socket/DB/native handles |
| Diagnosis | Heap dump, retained paths, live-set trend | Open descriptors, pools, native memory metrics |
| Common mistake | Static cache/listener not removed | Forgetting close/rollback/unsubscribe |
| Fix | Sever strong references according to lifecycle | Use `AutoCloseable`/`try-with-resources` |
| Can `System.gc()` fix it? | Does not fix ownership | Does not guarantee timely cleanup |
| Can they occur together? | Yes | Yes |

**An unremoved listener registration** can both retain Java objects and keep a resource wrapper unclosed if the owning component is also responsible for the resource.

## 27. `try-with-resources` Pairs Well with Subscription Lifetimes

Instead of relying on garbage collection, an API can model a registration as an `AutoCloseable`.

Example from SubscriptionHandleDemo:

```java
try (AutoCloseable subscription =
         events.subscribe(this::handle)) {
    // Active while the subscription is alive.
}
// close() removes the listener.
```

This is an **illustrative snippet** assuming `events`, `handle`, and `this` are in the appropriate scope; if the method returning AutoCloseable can throw a checked exception from close, a corresponding signature/catch is needed.

Better yet, for an event source with a long lifecycle, the owning component also implements AutoCloseable:

- Construction/start creates the subscription handle.
- Close/stop closes the handle.
- Owner stop is called when the UI screen, request, or service is torn down.
- Do not recreate the handle inside every callback.
- Clean up in `finally` for failed startup/cancellation.

**Unlike GC:** `close` is invoked according to the designed control flow, **without depending on when the object disappears**.

## 28. Do Not Retain an Entire Object When You Only Need an Identifier

A static cache:

```java
static final Map<String, RequestContext> REQUESTS =
        new java.util.HashMap<>();
```

can retain all fields of RequestContext (HTTP request, user profile, buffers, attachments...). If you only need the ID/status, consider storing a simple value such as a String, an immutable record summary, or a small DTO.

For example:

```java
record RequestSummary(String id, int status) {
}
```

**Do not always copy every object:** You need to weigh memory/cost and semantics. However, replacing a reference to a large graph with a small immutable snapshot can reduce retained size many times over.

**The optimal solution is to retain the right data for the right lifetime**, rather than simply replacing strong references with weak references in every case.

## 29. ClassLoader Retention and Static Fields: An Advanced Topic

Each class is identified in the JVM by the pair consisting of its binary name and defining class loader. Static fields belong to the class associated with that classloader. In applications with reloadable plugins/webapps, a classloader can be kept alive if there are references from a longer-lived component to the associated objects/classes.

Simple retention path:

```text
long-lived platform/service
    └── listener registry
          └── callback from plugin
                └── plugin object
                      └── plugin class / loader relationships
```

If a module/plugin is "unloaded" from a business perspective without unregistering its callback, the associated classloader may be unable to be unloaded.

**Caution:** Not every static field is automatically an immortal GC root; class unloading and reachability semantics are complex. However, retaining references across **boundaries between classloaders/lifecycles** is a very common source of memory retention in plugin/app-server environments.

### Properly Targeted Cleanup

- The platform registry must remove plugin callbacks when the plugin stops.
- Threads created by the plugin must stop.
- ThreadLocal values/classes tied to the plugin on shared worker threads must be cleaned up.
- Caches whose keys/values are plugin classes need appropriate invalidation.
- Resources opened by the plugin must be closed.
- Use heap analysis to confirm classloader paths before drawing conclusions.

## 30. Example of a Lifecycle Manager That Closes All Registrations

When a component registers **multiple** subscriptions, you should manage the set of handles belonging to the same owner and close all of them.

Create **`SubscriptionGroupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class CloseGroup implements AutoCloseable {
    private final List<AutoCloseable> resources =
            new ArrayList<>();
    private boolean closed;

    void add(AutoCloseable resource) {
        if (closed) {
            throw new IllegalStateException("group closed");
        }
        resources.add(resource);
    }

    @Override
    public void close() throws Exception {
        if (closed) {
            return;
        }
        closed = true;

        Exception first = null;
        for (int i = resources.size() - 1; i >= 0; i--) {
            try {
                resources.get(i).close();
            } catch (Exception ex) {
                if (first == null) {
                    first = ex;
                } else {
                    first.addSuppressed(ex);
                }
            }
        }
        resources.clear();

        if (first != null) {
            throw first;
        }
    }
}

public class SubscriptionGroupDemo {
    public static void main(String[] args) throws Exception {
        try (CloseGroup group = new CloseGroup()) {
            group.add(() -> System.out.println("unregister A"));
            group.add(() -> System.out.println("unregister B"));
            System.out.println("active");
        }
        System.out.println("closed all");
    }
}
```

```bash
javac SubscriptionGroupDemo.java
java SubscriptionGroupDemo
```

```text
active
unregister B
unregister A
closed all
```

**Why is there exception handling?** If one close fails, the group still attempts to close the remaining handles. The first exception is rethrown, and subsequent exceptions are attached as suppressed exceptions. This is an illustrative policy; in production, you need to clearly define error reporting, concurrency, and registration rollback if `add` fails.

**Remember:** Grouping handles does not turn all subscriptions into weak references. It provides **a single place responsible for cleanup**, helping avoid forgetting individual registrations.

## 31. Designing an Observer API to Avoid Forgetting Ownership

A subscriber API should make clear:

- Does `subscribe` return a **handle**, or must the listener object be passed back?
- Is the handler held **strongly or weakly**?
- Is `unsubscribe/close` **idempotent**?
- Does removing a listener during publish allow the current callback to continue running?
- Are duplicate registrations allowed?
- Does the owner outlive the source, or does the source outlive the owner?
- Who closes subscriptions if initialization fails halfway through?
- Is the API thread-safe?
- Do subscriptions have a timeout/TTL, or do they expire with the connection?

Example responsibility assignment:

| Party | Responsibility |
| --- | --- |
| Event source | Manage listeners, emit events, remove the right entry |
| Subscriber owner | Hold the handle and close it when the lifecycle ends |
| Application lifecycle | Call stop/close on owners |
| Test | Assert that the listener count returns to baseline |
| Monitoring | Observe registration count/retained size over time |

**Do not hide the lifecycle:** If an API simply returns void from subscribe, callers easily forget how to remove it. Returning a `Subscription` handle makes the cleanup path visible during code review.

## 32. Heap Dump: Tracing from a Retained Object Back to the Root

A profiler/heap dump analyzer can typically inspect:

1. **Shallow size**: the memory corresponding to the object itself.
2. **Retained size**: the total memory that could be freed if a particular object/retention branch were no longer reachable (according to the tool and dominator graph definition).
3. **Paths to GC roots**: why is the object still reachable?
4. **Dominators**: the objects keeping large groups alive in the graph.
5. **Class histogram**: how many instances exist for each class and their estimated total heap footprint.

Process:

- Capture measurements after warm-up or before/after a defined workload.
- Observe the **live set after appropriate collections**, not just allocated bytes.
- Find classes growing in live instance count or retained size.
- Trace the root path back to a static map/listener registry/ThreadLocal/queue.
- Correlate that path with the expected lifecycle.
- Fix by removing the right reference edge.
- Re-verify with a similar workload to avoid drawing conclusions from a single snapshot.

**Do not claim an object is "leaking" simply because it is still alive when a heap dump is captured.** You must cross-check it against its functionality, lifecycle, and actual growth rate.

## 33. Metrics to Monitor

| Metric | Purpose |
| --- | --- |
| Cache entry count | Is it approaching/exceeding the limit? |
| Cache weight/bytes | Actual memory footprint |
| Hit/miss rate | Is the cache providing any benefit? |
| Eviction/expiry count | Is the removal policy working? |
| Active sessions | Does it decrease after logout/timeout? |
| Listener count | Does it grow after each open/close cycle? |
| Pending task count | Is the queue/scheduler accumulating work? |
| ThreadLocal cleanup failures | Could context leak between tasks? |
| Post-GC live heap trend | Are live objects growing over the long term? |
| Native resource count | Non-heap leaks? |
| ClassLoader instances | Do plugins/redeploys unload properly? |

Metrics do not prove the root cause by themselves. However, **maintaining lifecycle expectations** such as "each time a screen closes, the listener count drops by 1" often helps detect regressions early.

## 34. Why Is `Runtime.freeMemory()` a Poor Leak Check?

JVM heap management may retain committed heap, allocate more memory, compact, optimize, or run GC asynchronously relative to application calls. The `totalMemory/freeMemory` values change for many reasons beyond just the live object count.

Example of an unreliable assertion:

```java
// long before = Runtime.getRuntime().freeMemory();
// registry.clear();
// long after = Runtime.getRuntime().freeMemory();
// assert after > before; // Not guaranteed.
```

This is **faulty code regarding measurement assumptions**.

### Alternative Tests

Check deterministic business invariants:

- Cache size does not exceed the limit.
- After close, the listener count returns to baseline.
- On timeout, get returns null and the entry is removed.
- After a task, ThreadLocal is removed, and the next task does not see the old context.
- After shutdown, pending handles are closed.
- No duplicate registrations remain after 100 open/close cycles.

Meanwhile, proving an actual leak requires profiling over time and under workload.

## 35. Mistake 4: Retaining a Request/Session in a Singleton

A singleton/service typically lives for the duration of the app. If the service stores an `HttpRequest` or `UserSession` in a field/static list "for later use," the request graph will live unexpectedly long.

Conceptual example:

```java
class AuditService {
    private Object lastRequest;

    void audit(Object request) {
        lastRequest = request;
    }
}
```

This declaration is valid, but it can cause retention if the service is long-lived and lastRequest holds a large graph. Sometimes storing the latest request object briefly is intentional; however, you must evaluate **retained size and ownership**.

A better approach:

```java
record AuditRecord(String requestId, int status) {
}
```

Store only the small piece of data needed for auditing instead of retaining the entire request object, stream/body buffers, and session refs.

**Do not mistake this:** Not every singleton field is a memory leak; **a lifetime extending beyond the necessary lifecycle** is the problem.

## 36. Caching Mutable Objects vs. Immutable Snapshots

If a cache holds a mutable entity that callers can modify, you run into two problems:

- **Memory retention**: long-lived references.
- **State consistency**: the cache contains an object mutated unintentionally or shared with a request.

Using an immutable snapshot such as small record components or a copy of a collection helps avoid certain side effects. However, an immutable object can still be retained if it stays indefinitely in a static map.

**Note:** `List.copyOf` only creates/provides an unmodifiable list structure; it does not deep-copy mutable elements. A cached list containing `byte[]` objects can still share mutable contents in each element.

Choose the representation based on domain and size; do not use "immutable" as an excuse to skip eviction.

## 37. A Static Cache in Tests Leaks State Between Test Cases

Tests in the same JVM can share static fields. If test A puts data into a static cache, test B can observe that data if it is not reset; tests become order-dependent.

Create **`StaticStateIsolationDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class TestRegistry {
    private static final Set<String> VALUES =
            new HashSet<>();

    static void add(String value) {
        VALUES.add(value);
    }

    static int size() {
        return VALUES.size();
    }

    static void reset() {
        VALUES.clear();
    }
}

public class StaticStateIsolationDemo {
    public static void main(String[] args) {
        TestRegistry.add("from-test-A");
        System.out.println(TestRegistry.size());

        TestRegistry.reset();
        System.out.println(TestRegistry.size());
    }
}
```

```bash
javac StaticStateIsolationDemo.java
java StaticStateIsolationDemo
```

```text
1
0
```

**In production:** A global reset is not always valid when there are active users. In tests, if a component owns temporary state, cleaning up via a fixture/afterEach or dependency injection is cleaner.

A design that avoids static mutable fields also makes testing/isolation easier: inject the cache/registry instance into the code that needs it, then create a new instance for each test.

## 38. Refactoring from Static Scope to Instance Scope

If a registry only serves a single request/session/component, instead of a global static registry, we can create a registry instance belonging to the owner. When the owner is no longer reachable and external subscriptions/threads do not retain it, the entire graph can be reclaimed naturally by the GC.

Create **`ScopedRegistryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class RequestRegistry {
    private final List<String> messages =
            new ArrayList<>();

    void add(String message) {
        messages.add(message);
    }

    int size() {
        return messages.size();
    }
}

public class ScopedRegistryDemo {
    static int handleRequest() {
        RequestRegistry registry = new RequestRegistry();
        registry.add("one");
        registry.add("two");
        return registry.size();
    }

    public static void main(String[] args) {
        System.out.println(handleRequest());
        System.out.println(handleRequest());
    }
}
```

```bash
javac ScopedRegistryDemo.java
java ScopedRegistryDemo
```

```text
2
2
```

Each request has its own registry without using static state. However, if the registry is returned/stored in a static field or captured in a long-lived callback, it can still be kept alive. **An instance field does not automatically guarantee no leaks**; it only makes the ownership boundary easier to control.

## 39. Exception Handling Scenario: Cleanup in `finally`

When a registration or ThreadLocal is temporary, cleanup is needed on success, failure, early return, and cancellation (according to controllable control flow).

Create **`FinallyCleanupDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Registry {
    private static final List<String> ACTIVE =
            new ArrayList<>();

    static void enter(String id) {
        ACTIVE.add(id);
    }

    static void leave(String id) {
        ACTIVE.remove(id);
    }

    static int size() {
        return ACTIVE.size();
    }
}

public class FinallyCleanupDemo {
    static void execute(String id) {
        Registry.enter(id);
        try {
            throw new IllegalStateException("failed");
        } finally {
            Registry.leave(id);
        }
    }

    public static void main(String[] args) {
        try {
            execute("R1");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println(Registry.size());
    }
}
```

```bash
javac FinallyCleanupDemo.java
java FinallyCleanupDemo
```

```text
failed
0
```

The code intentionally throws an exception; finally still removes the entry. **The case where initialization fails before enter** needs to be handled according to your specific design; do not blindly remove another task's entry when keys collide.

With async workflows, the lifecycle may not fit inside a single lexical try block; in that case, explicitly use subscription handles, structured ownership, or task completion callbacks.

## 40. Concurrency in Caches and Registries: Distinguishing Races from Leaks

A `HashMap` accessed concurrently without synchronization can lead to races, visibility problems, and broken structure/behavior. Switching to `ConcurrentHashMap` can solve some thread-safety issues, but **does not bound the size by itself**.

For example:

```java
static final java.util.concurrent.ConcurrentMap<String, Object>
        CACHE = new java.util.concurrent.ConcurrentHashMap<>();
```

Even though it is thread-safe at the map-operation level, if `CACHE.put(...)` is called with ever-growing keys, the map can still retain objects indefinitely.

**Two independent policies:**

- Concurrency control: safety when multiple threads read/write.
- Lifetime/memory control: bounding, expiring, removing, invalidating.

Both are needed when a cache is shared across threads.

## 41. Misconceptions About `System.gc()` and GC Tuning

An application hitting an `OutOfMemoryError` due to an unboundedly growing static registry sometimes tries:

```java
System.gc();
```

This **does not sever strong references**. The GC can find that the list and entries are still reachable, so it is not allowed to remove them merely because the program no longer needs them.

Increasing the heap size can delay an `OutOfMemoryError`, but it also **does not fix the root-path cause**. GC tuning can help latency/throughput when retention is legitimate, but when logic retains data indefinitely, the first problem to solve is lifecycle/eviction.

**Priority workflow:** Find the reference graph → identify the owner/retention policy → fix cleanup/limits → re-verify the live set → and only then tune if still needed.

## 42. If Memory Keeps Growing After Removal, What Should You Check?

Do not jump to the conclusion that the fix had no effect just because process memory has not dropped immediately. Check:

1. Was the entry removed from the right map/list with the right key/callback instance?
2. Is another map, snapshot, closure, or future still retaining the object?
3. Is a thread-local context retaining the value?
4. Is a classloader or JNI handle holding references?
5. Is the post-GC object count/live set still growing?
6. Is the JVM holding committed heap for reuse?
7. Are there unreleased native/off-heap allocations?
8. Have the workload, cache warm-up, and allocation rate changed?

**Memory leak diagnosis is a retained object graph problem**, not merely printing `Runtime.freeMemory()` before and after a removal.

## 43. Classification: Normal Caching, High Memory Use, Leak

| Case | Assessment |
| --- | --- |
| Fixed cache of 100 entries, fitting the load and payload | Usually intentional retention |
| Cache with TTL but lazy cleanup, old keys never read again | Still risks accumulation |
| Unbounded static list with request data | Very high leak risk |
| Listener count returns to baseline after every close | A good lifecycle sign |
| Listener count grows after every open/close | Sign of duplicate/unremoved subscription |
| Committed heap stays large after GC but live set is stable | Not enough to conclude a leak |
| Live objects grow indefinitely under a similar workload | Root paths need investigation |
| WeakHashMap where values retain keys | Weak-key eviction may be ineffective |
| Resource already closed while object remains reachable | Not necessarily a resource leak; may be retention |
| Object unreachable while external resource is not closed | Resource leak may occur |

**There is no single threshold that applies to every application.** What decides it is business lifetime, load pattern, and data retention policy.

## 44. Practice Exercise: Measuring Listener Invariants Across Multiple Open/Close Cycles

Create **`RepeatedSubscriptionSelfTest.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Bus {
    private final List<Runnable> listeners =
            new ArrayList<>();

    AutoCloseable subscribe(Runnable listener) {
        listeners.add(listener);
        return () -> listeners.remove(listener);
    }

    int count() {
        return listeners.size();
    }
}

public class RepeatedSubscriptionSelfTest {
    static void check(boolean result, String label) {
        if (!result) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) throws Exception {
        Bus bus = new Bus();

        for (int i = 0; i < 100; i++) {
            try (AutoCloseable ignored =
                         bus.subscribe(() -> {})) {
                check(bus.count() == 1, "registered");
            }
            check(bus.count() == 0, "unregistered");
        }

        System.out.println("listener lifecycle PASS");
    }
}
```

```bash
javac RepeatedSubscriptionSelfTest.java
java RepeatedSubscriptionSelfTest
```

```text
listener lifecycle PASS
```

The test does not observe GC. It proves that the current subscribe/close cycle does not cause Bus.listeners to grow after 100 open/close iterations.

### Additional Cases to Test

- Callback throwing an exception.
- Registering two different listeners and removing one.
- Unsubscribing multiple times (idempotency policy).
- Registering a duplicate listener reference if the API allows it.
- Unsubscribing during publish.
- Shutting down the entire event source.
- Concurrent subscription/delivery if required.

## 45. Practice Exercise: Checking Cache Capacity Across Repeated Insertions

Create **`CacheCapacitySelfTest.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

class LimitedCache<K, V> extends LinkedHashMap<K, V> {
    private final int capacity;

    LimitedCache(int capacity) {
        super(16, 0.75f, true);
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity");
        }
        this.capacity = capacity;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > capacity;
    }
}

public class CacheCapacitySelfTest {
    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError();
        }
    }

    public static void main(String[] args) {
        LimitedCache<Integer, String> cache =
                new LimitedCache<>(3);

        for (int i = 0; i < 100; i++) {
            cache.put(i, "value-" + i);
            check(cache.size() <= 3);
        }

        System.out.println(cache.size());
        System.out.println(cache.containsKey(99));
        System.out.println(cache.containsKey(0));
        System.out.println("capacity PASS");
    }
}
```

```bash
javac CacheCapacitySelfTest.java
java CacheCapacitySelfTest
```

```text
3
true
false
capacity PASS
```

With 100 distinct keys and capacity 3, the map holds at most three entries. The test does not rely on bytes or GC scheduling. Production may also need a weight bound, time eviction, and synchronization.

## 46. Practice Exercise: Fixing an Unbounded Static Cache

Problematic code:

```java
static final Map<String, byte[]> CACHE =
        new HashMap<>();

static void remember(String id, byte[] payload) {
    CACHE.put(id, payload);
}
```

This is an **illustrative snippet**. With continuously new ids, the map retains all arrays via strong references.

**Requirement:** Propose a policy:

- A reasonable maximum entry count or maximum weighted bytes.
- Domain-based TTL/idle expiry.
- Invalidation when source data changes.
- Cleanup when the application/module closes.
- Do not retain the request object graph when only a snapshot is needed.
- Metrics for size/evictions/weight.
- If values own external resources, provide a cleanup contract on eviction.
- If shared, include concurrency control.

**A minimal fix** is the bounded LRU from section 9. However, if payload sizes vary greatly, limiting only the entry count is not enough; choose weight-based eviction or store the data at an appropriate storage tier.

## 47. Practice Exercise: Fixing an Unremoved UI Registration

Lifecycle-broken code:

```java
class Editor {
    Editor(EventHub hub) {
        hub.addListener(this::onChange);
    }

    void onChange() {
        // Update UI.
    }
}
```

`EventHub` is a hypothetical API. Because it does not retain the listener/subscription handle, the owner has no clear way to call `removeListener`.

One way to fix it:

```java
class Editor implements AutoCloseable {
    private final EventHub hub;
    private final Runnable listener;

    Editor(EventHub hub) {
        this.hub = hub;
        this.listener = this::onChange;
        hub.addListener(listener);
    }

    private void onChange() {
        // Update.
    }

    @Override
    public void close() {
        hub.removeListener(listener);
    }
}
```

This is an **illustrative pattern**; EventHub must be defined with the matching signatures. The takeaway is that the owner **retains the exact listener reference that was registered** and unsubscribes on close.

**In real code:** Ensure close is called during UI teardown, and test the listener count after multiple open/close cycles.

## 48. Practice Exercise: ThreadLocal Context Left Over Between Two Requests

Lifecycle-broken code:

```java
static final ThreadLocal<String> USER =
        new ThreadLocal<>();

void handle(String name) {
    USER.set(name);
    System.out.println(USER.get());
}
```

In a thread pool, the value can remain for the next task.

Fix:

```java
void handle(String name) {
    USER.set(name);
    try {
        System.out.println(USER.get());
    } finally {
        USER.remove();
    }
}
```

These are **method snippets** assumed to be placed inside a class that has the USER static field.

**Note:** Even with remove, if an async callback retains the name/context, the context can persist along another path. Avoid sharing request-scoped mutable objects indiscriminately.

## 49. Memory Retention Review Checklist

- [ ] Is there a static `Map/List/Set` storing per-request/user/session data?
- [ ] Do static fields retain necessary objects, or were they placed there just for convenience?
- [ ] Is it understood that `static final` does not make a mutable collection immutable?
- [ ] Are the owner and lifecycle defined for each cache/registry?
- [ ] Is removal performed on logout, timeout, stop, close, and failure?
- [ ] Does the cache have a capacity limit or weight-based bound?
- [ ] Does TTL perform cleanup even when keys are never read again?
- [ ] Does the cache perform invalidation when source data changes?
- [ ] Is there near-unbounded cache key cardinality causing a low hit rate?
- [ ] Does the cached value accidentally retain a request/controller/large payload graph?
- [ ] Are there metrics for size, weight, evictions, expiry, and hit rate?
- [ ] Is `ConcurrentHashMap` being used under the assumption that it bounds size automatically?
- [ ] Does listener registration have a matching unregistration path?
- [ ] Is the **exact listener reference/handle** used during subscribe retained?
- [ ] Is `close`/unsubscribe called during the appropriate teardown?
- [ ] Are there duplicate subscriptions after multiple open/close cycles?
- [ ] Does a lambda/method reference capture `this`/a buffer/a large object graph?
- [ ] Are there subscriptions left unclosed when initialization fails?
- [ ] Is the event delivery/unsubscribe concurrency contract clear?
- [ ] Do ThreadLocal values have `remove()` in `finally`?
- [ ] Are worker threads/thread pools reused across requests?
- [ ] Does the scheduled task queue have limits, cancellation, and completion cleanup?
- [ ] Do `WeakHashMap` values have a strong back-reference to keys?
- [ ] Are weak references avoided as a default cache eviction solution?
- [ ] Are System.gc/finalize/Cleaner avoided as fixes for ownership leaks?
- [ ] Are `AutoCloseable` resources closed according to contract?
- [ ] Have heap retention and native resource leaks been distinguished?
- [ ] During analysis, did you trace from the object to the GC root path?
- [ ] Did you inspect retained size and live set trends rather than only committed heap?
- [ ] Are there regression tests checking cache bounds and listener baseline?
- [ ] Is the classloader/redeployment lifecycle considered if the application is a server/plugin?
- [ ] Are concurrency and semantics verified when multiple users/tasks run?
- [ ] Do all Java 17+ examples have matching file names, class names, and deterministic stdout?

## 50. Solution Decision Table

| Source of retention | Root cause | Priority remediation |
| --- | --- | --- |
| Static list of sessions | Entries not removed when session ends | Logout/timeout cleanup, proper scope |
| Static unbounded memoization | Unbounded key cardinality | Capacity/weight, TTL, invalidation |
| Cache with lazy TTL | Entries expired but never read with get | Periodic/batched expiry and max bound |
| Cache value retains request graph | Large retained size | Cache a small immutable DTO |
| UI listener | Event source retains callback after close | Unsubscribe/AutoCloseable handle |
| Method-reference listener | Removing with a different listener object | Retain the exact listener reference/handle |
| Duplicate subscriptions | Start/open calls subscribe multiple times | Lifecycle state and repeated tests |
| ThreadLocal on pool | Value not removed after task | `try/finally { remove(); }` |
| Queued tasks/futures | Queue retains captured contexts | Backpressure, cancel/cleanup |
| Classloader fails to unload | Plugin callbacks/static cross-links | Stop/unregister/clear at the proper boundary |
| WeakHashMap key not cleared | Value references back to key | Break strong back-reference/use another design |
| File/socket/DB connection | Forgetting explicit close | `try-with-resources` |
| Committed heap does not decrease | JVM may keep heap for reuse | Inspect live set/object graph before concluding |

**There is no single "GC switch" that fixes everything.** All effective solutions come down to a *right-sized retention policy*, *clear ownership*, and *reliable cleanup*.

## 51. Review Questions with Answers

**1.** If Java has a garbage collector, can memory leaks still happen?

*Yes. Objects that are no longer useful but remain reachable through strong references can continue occupying memory.*

**2.** Is a `static final List` automatically immutable?

*No. Final fixes the field reference; the list contents can still be modified.*

**3.** Why can a static cache holding request data leak?

*A static map lives long and retains values/entire object graphs beyond the request lifecycle.*

**4.** Does setting a local variable to null free an object that is inside a static list?

*No, the list still holds a strong reference.*

**5.** When removing an entry from a map, does the GC reclaim the object immediately?

*There is no timing guarantee, and the object may still have other references.*

**6.** Is a cache bounded by entry count guaranteed to be bounded in bytes?

*No; payload sizes can vary dramatically.*

**7.** What does `LinkedHashMap` with access-order + removeEldestEntry support?

*It can be used to build a simple bounded LRU cache in suitable contexts.*

**8.** Is the LRU example automatically thread-safe?

*No; LinkedHashMap is not thread-safe.*

**9.** What risk remains with TTL lazy cleanup?

*Expired entries that are never read again can continue taking up space.*

**10.** How does cache invalidation differ from eviction?

*Invalidation removes stale values when source data changes; eviction removes entries based on capacity/usage/time policies.*

**11.** How can a listener registry retain a component?

*By holding a callback that references/captures the component, thereby retaining the entire object graph.*

**12.** If you register `this::onEvent` and later remove `this::onEvent` with a separate expression, is it guaranteed to be the same listener object?

*No. You should store the exact listener reference or subscription handle.*

**13.** Why is returning an AutoCloseable subscription handle useful?

*It ties ownership and cleanup clearly to a scope/close operation.*

**14.** What does a growing listener count after every screen open/close suggest?

*Likely duplicate registrations or missing unsubscription.*

**15.** Does `List.copyOf(listeners)` during publish guarantee thread safety by itself?

*No; it only supports snapshot iteration, and a concurrency policy is still needed.*

**16.** Can a lambda capturing a byte[] extend the array's lifetime?

*Yes, if the lambda remains strongly reachable.*

**17.** Why is `ThreadLocal` risky on a thread pool?

*A reused worker thread can retain the value from a previous request if remove is not called.*

**18.** Where should ThreadLocal cleanup be performed?

*In finally after the task/request using the context completes.*

**19.** Does `ConcurrentHashMap` automatically limit the number of entries?

*No.*

**20.** Does `WeakReference` guarantee that the referent stays alive until a deadline?

*No.*

**21.** Do `WeakHashMap` weak keys always automatically remove every unneeded entry?

*No; values or other references can still retain the key.*

**22.** Should you assert WeakReference.get()==null right after System.gc?

*No, GC timing is non-deterministic.*

**23.** How do a heap leak and a resource leak differ?

*Heap retention is objects being kept alive; a resource leak is external/native resources not being released according to contract.*

**24.** Does `System.gc()` fix a static registry that never removes entries?

*No; it does not sever strong references.*

**25.** Why is increasing the heap size only a temporary fix for an unbounded cache?

*Memory still grows with key cardinality if there is no eviction.*

**26.** Can a small cached value object retain a huge amount of memory?

*Yes; it can retain a large graph through nested references.*

**27.** What does a heap dump path to GC root help with?

*Identifying the exact reference path keeping the object reachable.*

**28.** How does retained size differ from shallow size?

*Retained size reflects the portion of the object graph kept alive by a dominator reference/retention branch, not just the footprint of that single object.*

**29.** Why is a large committed heap not enough to prove a leak?

*The JVM may hold onto committed memory for reuse even when the live set is stable.*

**30.** When a plugin classloader fails to unload, which sources should you inspect?

*Global registrations, ThreadLocals, worker tasks, caches, and cross-loader references.*

**31.** Does replacing a static registry with an instance registry automatically guarantee no leaks?

*No; the instance can also be retained by a callback/another static field. However, scoped ownership can be easier to manage.*

**32.** If closing a listener can throw, should you skip closing the remaining handles?

*Usually not; you can use group cleanup to continue closing and aggregate exceptions according to policy.*

**33.** Without using GC as a test check, how should you test memory lifecycle?

*Deterministic invariants such as listener count returning to baseline, bounded caches, and subsequent tasks not seeing old ThreadLocal contexts.*

**34.** What is the most important rule to avoid this kind of leak?

*Clearly design who holds the strong reference, why it is held, how long it is bounded, and who severs it when the lifecycle ends.*

## 52. Java 17+ References

- *Java API — `java.lang.ref`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html — reference reachability levels.
- *Java API — `WeakHashMap`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html — weak keys and caveats when values reference back to keys.
- *Java API — `ThreadLocal`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html — `set/get/remove` and thread-bound values.
- *Java API — `LinkedHashMap`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html — access-order and `removeEldestEntry`.
- *Java API — `AutoCloseable`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html — deterministic cleanup and try-with-resources.
- *Java API — `Reference.reachabilityFence`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html — intentional reachability boundaries.
- *Java API — `ExecutorService`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html — managing tasks and shutdown.

---

**Final takeaway:** Java's GC reclaims memory for objects that are **no longer reachable**, not objects that are merely "no longer useful" in application logic. A `static Map/List`, an unbounded cache, or an event source holding a listener long-term can create a **strong reference** path from roots to the entire object graph. The right fix is to establish clear **ownership/lifecycle**: remove entries when finished, bound caches with capacity/weight/expiry/invalidation, return and close subscription handles, call `ThreadLocal.remove()` in `finally`, and manage tasks and resources with appropriate cleanup APIs. **Weak references and `System.gc()` do not replace a retention policy**. Inspect reference paths with heap analysis when needed, and write tests based on **deterministic count/bound/cleanup invariants**, not on when GC runs.
