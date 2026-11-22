# ConcurrentHashMap.newKeySet and Key-Set Views

## 1. From a Concurrent Map to a Concurrent Set

Some problems only need to know whether an ID has already been registered: a request ID currently being processed, a name that has already appeared, or a resource that has already been claimed. Using `Map<K, Boolean>` can express that, but callers usually do not need to work with Boolean values; they need the `add`, `contains`, and `remove` operations of a `Set`.

`ConcurrentHashMap.newKeySet()` provides a map-backed concurrent set. At the same time, an existing `ConcurrentHashMap` can also expose a **key-set view** so users can work directly with its keys.

These two approaches look similar when declared as `Set<K>`, but they differ in ownership and how elements are added:

- `newKeySet()` creates a new set with a new backing map.
- `map.keySet()` views the keys of an existing map; it does not support adding through the set.
- `map.keySet(mappedValue)` also views an existing map, but allows adding keys using a specified shared value.

A view is not a copy. Removing a key through a view also removes the key–value mapping in the backing map. If this is overlooked, a call that appears to only edit a "key list" can delete data in a map that another component is using.

The goal of this lesson is to read that relationship accurately, choose the right API, and use the result of set operations in a multithreaded environment. Examples use Java 17 or later; familiarity with `Map`, `Set`, keys, values, and object references is required.

## 2. Three Creation Methods with the Same Apparent Type but Different Semantics

### 2.1. API Comparison Table

| How to obtain the set | Backing map | Supports `add/addAll`? | Value used for added keys |
| --- | --- | --- | --- |
| `ConcurrentHashMap.newKeySet()` | New map created by the method | Yes | `Boolean.TRUE` |
| `ConcurrentHashMap.newKeySet(initialCapacity)` | New map, with an initial sizing hint | Yes | `Boolean.TRUE` |
| `map.keySet()` | The existing map itself | No | No default value for adding |
| `map.keySet(mappedValue)` | The existing map itself | Yes | Non-null `mappedValue` |

These methods return `ConcurrentHashMap.KeySetView`. For the `newKeySet` factory methods, the backing value type is `Boolean`; for a view of `ConcurrentHashMap<K, V>`, the backing value type is `V`. [ConcurrentHashMap — newKeySet and keySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet())

All views in the table support removal. Therefore, "does not support adding" on `keySet()` **does not mean read-only**.

### 2.2. Why Doesn't `keySet()` Know What Value to Add?

Suppose a map holds `String -> Order`. When a caller writes `keys.add("order-7")`, only the key `"order-7"` is provided. The map still needs an `Order` object to create a mapping.

`keySet()` must not guess an `Order` or insert a null value. Hence, addition is not supported.

`keySet(mappedValue)` solves this with an explicit choice: every new key added through this view uses the same passed-in value. It is suitable when sharing that value matches the meaning of the data.

`newKeySet()` solves the pure-set case with a marker value `Boolean.TRUE`. The value only serves as the representation in the backing map; set membership is determined by the key.

### 2.3. Two-Way Linked Views

You can picture it as:

```text
map.keySet() --------\
                      > both view the keys of ONE existing map
map.keySet("NEW") ---/

map.put / map.remove
         <----> membership of the views

ConcurrentHashMap.newKeySet()
         ---> a new set ---> a new ConcurrentHashMap
```

Several consequences follow:

- `map.put(k, v)` with a new key makes the view gain `k`.
- Replacing the value of an existing key does not create an additional set member.
- `keys.remove(k)` removes both the key and its corresponding value from the map.
- `keys.clear()` removes the mappings of the backing map, not just "emptying a copy of the key list."
- Two views obtained from the same map see the same set of keys, even if their default values for adding differ.

This is a live data relationship, not an event notification mechanism or a history log.

### 2.4. `KeySetView<K, V>` Is Still a `Set<K>`

The type parameter `K` is the set element type; `V` is the backing map's value type. It is not a set of `Map.Entry<K, V>` pairs.

You can declare:

```java
Set<String> visited = ConcurrentHashMap.newKeySet();

ConcurrentHashMap.KeySetView<String, Boolean> detailed =
        ConcurrentHashMap.newKeySet();
```

These are illustrative declarations requiring imports for `Set` and `ConcurrentHashMap`. Use `Set` when you only want the standard set operation surface. Use `KeySetView` when you actually need its dedicated methods such as `getMap` and `getMappedValue`.

The `KeySetView` class is not instantiated directly via a public constructor. The `ConcurrentHashMap` factory/instance methods above are the documented creation points. [KeySetView Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html)

## 3. `keySet(mappedValue)`: Shared Value for New Keys, Not a Command to Replace All Values

### 3.1. Adding an Existing Key Does Not Overwrite

Non-standalone illustrative snippet:

```java
ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
states.put("task-1", "DONE");

Set<String> pending = states.keySet("PENDING");
boolean changed = pending.add("task-1");
```

Result in this sequential context:

- `changed` is false because the key is already a member.
- The value of `"task-1"` remains `"DONE"`.
- `"PENDING"` is only used if the addition creates a missing mapping.

If you need to transition the state of an existing key, use an appropriate map operation, such as a conditional `replace`. Adding a key through a set is not a state-update command.

### 3.2. One Map Can Have Multiple Views with Different Default Values

Example:

```java
Set<String> pending = states.keySet("PENDING");
Set<String> queued = states.keySet("QUEUED");

pending.add("task-2");
queued.add("task-3");
```

This snippet builds on `states` from the previous example. Afterward, the map can contain `DONE`, `PENDING`, and `QUEUED` simultaneously. The default value is tied to **the addition path through a specific view**, not a rule forcing all values in the map to be identical.

If both views concurrently add a key that was absent, whichever creates the mapping first determines the value used for that insertion. The later caller sees that the key already exists and does not use the addition to overwrite it.

**Key takeaway:** `keySet("PENDING")` does not filter for keys whose value is PENDING. It still views every key, including keys currently holding DONE or ACTIVE. The argument only determines the value used when adding a missing key.

### 3.3. What Do `getMappedValue` and `getMap` Return?

`getMappedValue()` returns the default value used for additions, or null if the view does not support adding. `getMap()` returns the linked backing map. [KeySetView — accessor methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html#getMappedValue())

A null from `map.keySet().getMappedValue()` does not mean the map stores a null value. It is a signal about the view's addition capability.

Nor is `getMappedValue()` a command to read all current values in the map. Mappings created through other paths may hold different values. `getMap()` does not create a copy and does not return a read-only map; keeping that reference provides another access path to the same data.

## 4. Program: Observing Two-Way Changes and Modification Scope

Save as **`KeySetViewDemo.java`**:

```java
import java.util.Iterator;
import java.util.List;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;

public class KeySetViewDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
        states.put("kept", "DONE");
        states.put("remove-me", "ACTIVE");

        ConcurrentHashMap.KeySetView<String, String> keys = states.keySet();
        System.out.println("plain default = " + keys.getMappedValue());
        System.out.println("same backing map = " + (keys.getMap() == states));
        expectUnsupported("plain add", () -> keys.add("late"));
        expectUnsupported("plain addAll", () -> keys.addAll(List.of("late")));

        require(keys.remove("remove-me"), "remove through plain view");
        System.out.println("after view removal = " + new TreeMap<>(states));

        states.put("from-map", "ACTIVE");
        System.out.println("after map insertion = " + new TreeSet<>(keys));

        ConcurrentHashMap.KeySetView<String, String> pending =
                states.keySet("PENDING");
        boolean existingAdded = pending.add("kept");
        boolean newAdded = pending.add("new");
        require(!existingAdded && newAdded, "conditional addition");
        require("DONE".equals(states.get("kept")), "existing value overwritten");
        System.out.println("existing added = " + existingAdded);
        System.out.println("new added = " + newAdded);
        System.out.println("after mapped additions = " + new TreeMap<>(states));

        ConcurrentHashMap.KeySetView<String, String> other =
                states.keySet("OTHER");
        other.add("alternative");
        System.out.println("defaults = "
                + pending.getMappedValue() + ", " + other.getMappedValue());
        System.out.println("same keys in both views = " + pending.equals(other));

        Iterator<String> iterator = keys.iterator();
        while (iterator.hasNext()) {
            if ("new".equals(iterator.next())) {
                iterator.remove();
            }
        }
        require(!states.containsKey("new"), "iterator removal");
        System.out.println("removed via iterator = " + !states.containsKey("new"));
        System.out.println("final map = " + new TreeMap<>(states));

        pending.clear();
        System.out.println("clear view clears map = " + states.isEmpty());
    }

    private static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected UnsupportedOperationException");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all KeySetViewDemo.java
java KeySetViewDemo
```

Stdout on a successful run:

```text
plain default = null
same backing map = true
plain add -> UnsupportedOperationException
plain addAll -> UnsupportedOperationException
after view removal = {kept=DONE}
after map insertion = [from-map, kept]
existing added = false
new added = true
after mapped additions = {from-map=ACTIVE, kept=DONE, new=PENDING}
defaults = PENDING, OTHER
same keys in both views = true
removed via iterator = true
final map = {alternative=OTHER, from-map=ACTIVE, kept=DONE}
clear view clears map = true
```

Key observations:

1. The `keys` view has no default value for adding, so both attempted additions throw `UnsupportedOperationException`.
2. It can still remove `"remove-me"`, and the map loses that mapping.
3. Inserting via `states.put` shows up in the same view.
4. The `pending` view adds `"new" -> "PENDING"` but does not change `"kept" -> "DONE"`.
5. The `other` view uses a different default, yet has the exact same set of keys as `pending`.
6. Removing via `keys`'s iterator and calling `clear` via `pending` both affect the backing map.

The print statements use `TreeMap`/`TreeSet` so stdout ordering is deterministic. That is a presentation step in a sequential program; there is no guarantee that `ConcurrentHashMap`'s iterator orders keys.

Two views are equal in set contents because they see the same keys at the time of comparison, not because their default values are equal. Under concurrent updates, do not treat a whole-set comparison as a transaction that locks state.

## 5. `newKeySet`: A New Set and Conditional Addition

### 5.1. When You Only Need to Record Presence

The typical declaration is:

```java
Set<String> registeredIds = ConcurrentHashMap.newKeySet();
```

This set does not use an existing map of yours. The static factory creates a backing map for the new set itself. Calling it via the class name `ConcurrentHashMap` expresses the intent clearly; calling the static factory through a map variable does not make the result a view of that variable.

An element in the set corresponds to a key in the backing map. When adding through the set API, the marker value used is `Boolean.TRUE`. You usually do not need to read that value; `Set` already expresses the membership-check requirement cleanly.

Duplicate elements under the `Set` contract are determined by the key's equality/hashing rules, not by requiring the same `==` object reference. Therefore, keys must have proper `equals`/`hashCode` implementations that remain stable while the key is in the set. [Set Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 5.2. Use the Result of `add`, Do Not Combine `contains` Then `add`

This illustrative snippet is intentionally insufficient for choosing a single winner when multiple threads run concurrently:

```java
if (!registeredIds.contains("job-1")) {
    registeredIds.add("job-1");
    System.out.println("Bat dau xu ly job-1");
}
```

Two threads can both observe that the key is absent and both enter the processing branch. The set still will not contain duplicate keys, but the program ignored the return values of the two additions.

A more appropriate expression is:

```java
if (registeredIds.add("job-1")) {
    System.out.println("Lan dang ky nay da them job-1");
}
```

This is a non-standalone illustrative snippet. For a set from `newKeySet`, the backing map's conditional insertion governs mapping creation per key. When the key is initially absent, no removal occurs during contention, and multiple callers add concurrently, only one addition modifies the set.

A `true` result only describes that specific registration attempt. If the application removes the key and allows re-registration, a later addition can return `true` again.

### 5.3. Complete Program with Two Tasks

Save as **`ConcurrentKeySetDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentKeySetDemo {
    private static final int DISTINCT_PER_TASK = 1_000;

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap.KeySetView<String, Boolean> ids =
                ConcurrentHashMap.newKeySet();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> north = pool.submit(() -> addIds(ids, start, "north"));
            Future<Boolean> south = pool.submit(() -> addIds(ids, start, "south"));
            start.countDown();

            boolean a = north.get(10, TimeUnit.SECONDS);
            boolean b = south.get(10, TimeUnit.SECONDS);
            int successfulAdds = (a ? 1 : 0) + (b ? 1 : 0);
            require(successfulAdds == 1, "one shared-key addition must win");
            require(ids.size() == 2 * DISTINCT_PER_TASK + 1, "distinct count");
            boolean boundaryKeys = ids.contains("north-999")
                    && ids.contains("south-999");
            require(boundaryKeys, "missing boundary key");
            require(Boolean.TRUE.equals(ids.getMap().get("job-1")),
                    "set insertion must use the mapped value");

            System.out.println("successful shared-key adds = " + successfulAdds);
            System.out.println("total keys = " + ids.size());
            System.out.println("boundary keys present = " + boundaryKeys);
            System.out.println("default mapped value = " + ids.getMappedValue());

            ids.getMap().put("manual", Boolean.FALSE);
            boolean addedExisting = ids.add("manual");
            require(ids.contains("manual"), "presence is determined by the key");
            require(!addedExisting, "existing mapping must not be replaced");
            require(Boolean.FALSE.equals(ids.getMap().get("manual")),
                    "false value must be preserved");
            System.out.println("false-valued key is a member = "
                    + ids.contains("manual"));
            System.out.println("add existing manual key = " + addedExisting);
            System.out.println("manual mapping after add = "
                    + ids.getMap().get("manual"));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static boolean addIds(
            ConcurrentHashMap.KeySetView<String, Boolean> ids,
            CountDownLatch start, String prefix) throws InterruptedException {
        if (!start.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("start timed out");
        }
        boolean won = ids.add("job-1");
        for (int i = 0; i < DISTINCT_PER_TASK; i++) {
            String id = prefix + "-" + i;
            require(ids.add(id), "new id must be inserted");
            require(!ids.add(id), "duplicate id must not be inserted");
        }
        return won;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ConcurrentKeySetDemo.java
java ConcurrentKeySetDemo
```

Stdout on a successful run:

```text
successful shared-key adds = 1
total keys = 2001
boundary keys present = true
default mapped value = true
false-valued key is a member = true
add existing manual key = false
manual mapping after add = false
```

Both tasks add `"job-1"` and then each adds 1,000 distinct keys. Each distinct key is added twice: the first attempt must modify the set, and the second must not. There is no removal path during that phase.

The main thread waits for both tasks to complete before checking the count. Thus, the total of 2,001 consists of 2,000 distinct keys and one shared key. It does not rely on reading `size` while the tasks are still inserting.

Which task wins the shared key is not printed as a fixed outcome because that depends on scheduling. The program only asserts that exactly one addition succeeds. Timeouts help report errors instead of hanging; any assertion failure inside a task is propagated to the main thread via `Future.get`.

### 5.4. A `Boolean.FALSE` Value Still Creates Membership if Placed in the Backing Map

The end of the program intentionally retrieves `getMap` and inserts `"manual" -> Boolean.FALSE`. The key is still a member of the set because the set views **existing keys**, rather than filtering by whether the value equals true.

The subsequent `ids.add("manual")` returns false and preserves the existing false value. `getMappedValue()` remains true because that is the default for new keys, not the result of inspecting all stored values.

This illustrates backing-map access. If a component only needs an ordinary set, limiting exposure of the map reference helps avoid unnecessary mutation paths. There is no reason to actively write false into the map when using `newKeySet`.

If you want to represent an on/off state using Boolean values, operate on the map with an explicit state contract. Membership in a key-set view is not synonymous with "the Boolean value is true."

## 6. The Default Value Is a Shared Reference

### 6.1. Not a Per-Key Value Factory Function

`keySet(mappedValue)` accepts a single value, not a `Supplier<V>` or a key-based function. When new keys are added through the view, they share the same passed-in value reference.

For a `String`, an enum, or an immutable marker object, sharing is usually what you want. For a mutable list, it can be a major mistake: modifying the list for key A also modifies the exact same object that key B points to.

This is different from an algorithm that creates a fresh value for each key. If you need per-key values, use an appropriate map operation with a factory function, and still manage the thread safety of the created values.

### 6.2. Program: Shared Reference, Nulls, and Initial Sizing

Save as **`MappedValueContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;

public class MappedValueContractDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, List<String>> groups = new ConcurrentHashMap<>();
        List<String> shared = new ArrayList<>();
        ConcurrentHashMap.KeySetView<String, List<String>> keys =
                groups.keySet(shared);
        keys.add("a");
        keys.add("b");
        require(groups.get("a") == groups.get("b"), "expected shared value");
        shared.add("tag");
        System.out.println("same value reference = "
                + (groups.get("a") == groups.get("b")));
        System.out.println("values after edit = " + new TreeMap<>(groups));

        ConcurrentHashMap.KeySetView<String, Boolean> ids =
                ConcurrentHashMap.newKeySet(1);
        ids.add("one");
        ids.add("two");
        ids.add("three");
        System.out.println("size with initialCapacity 1 = " + ids.size());

        expectFailure("add null", NullPointerException.class,
                () -> ids.add(null));
        expectFailure("contains null", NullPointerException.class,
                () -> ids.contains(null));
        expectFailure("remove null", NullPointerException.class,
                () -> ids.remove(null));
        expectFailure("null mapped value", NullPointerException.class,
                () -> groups.keySet(null));
        expectFailure("negative initialCapacity", IllegalArgumentException.class,
                () -> ConcurrentHashMap.newKeySet(-1));
    }

    private static void expectFailure(
            String label, Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected " + expected.getSimpleName());
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all MappedValueContractDemo.java
java MappedValueContractDemo
```

Stdout on a successful run:

```text
same value reference = true
values after edit = {a=[tag], b=[tag]}
size with initialCapacity 1 = 3
add null -> NullPointerException
contains null -> NullPointerException
remove null -> NullPointerException
null mapped value -> NullPointerException
negative initialCapacity -> IllegalArgumentException
```

The program runs on a single thread. It uses `==` to verify that `a` and `b` point to the same list, then edits the list once and observes that both mappings see `[tag]`.

This experiment demonstrates reference sharing; it does not demonstrate that multiple threads are allowed to concurrently mutate an `ArrayList`. `ConcurrentHashMap` protects the mappings; it does not automatically make a value list a concurrent collection.

### 6.3. No Null Elements

`ConcurrentHashMap` keys do not accept null, so a set from `newKeySet` cannot store null elements. In the program, `add`, `contains`, and `remove` with null are tested on a set that supports adding, and all throw `NullPointerException`.

`map.keySet(null)` is also invalid: to obtain a view that supports adding, you must supply a non-null default value. This does not contradict `map.keySet().getMappedValue()` returning null to indicate that adding is unsupported.

For an operation that is both unsupported and given an invalid argument, do not build an algorithm around which exception check runs first. Choose the right view type and pass only valid arguments.

### 6.4. `initialCapacity` Is a Sizing Hint, Not a Limit

`newKeySet(1)` can still hold three elements, as the program shows. The argument hints internal sizing for the expected number of elements; it does not create a fixed-capacity set or a registration quota.

Negative values are rejected with `IllegalArgumentException`. Do not test huge values just to observe allocation; choose estimates based on realistic data. [ConcurrentHashMap — newKeySet(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet(int))

If you need a maximum cap of N members, `if (set.size() < N) set.add(x)` still has a race window. You must have a proper mechanism to enforce the limit; the sizing parameter does not replace that mechanism.

## 7. Concurrency Guarantees of Views

### 7.1. Weakly Consistent Iterators, Not Snapshots

`KeySetView`'s iterator is specified as weakly consistent. It can traverse while the map is being updated without using a fail-fast mechanism to report source changes. However, an entire traversal is not locked into a point-in-time snapshot of the map. [KeySetView — iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html#iterator())

Do not require every key added after creating an iterator to appear in that traversal, and do not treat one observed order on a single JDK build as a guaranteed order.

A single task should own its iterator. The fact that one thread can iterate while another modifies the map does not mean two threads can safely share a single iterator cursor.

`size`, `isEmpty`, and aggregate traversal results can change while other threads update the map. The two-task program waited for all writers to finish before asserting the exact count of 2,001; that condition is not automatically present in every application.

### 7.2. Set Mutability Does Not Combine Operations into a Transaction

`addAll` on a view that supports adding inserts elements with the semantics of individual `add` calls. Do not infer from this that readers only see either the state completely before or completely after the whole batch.

`removeAll`, `retainAll`, `removeIf`, or `clear` can also affect multiple mappings. They are not promises to coordinate every business invariant of the map. In particular, an invalid input or predicate exception should not be assumed to roll back earlier modifications.

If the source collection passed to `addAll` is concurrently being modified, you must still respect that source's traversal contract. A concurrent target set does not automatically fix issues in the source collection.

When you need to "remove a key only if its state is still PENDING," a plain removal through the key set cannot express the value condition. A non-standalone snippet should operate on the map:

```java
boolean removed = states.remove("task-7", "PENDING");
```

This conditional operation combines checking and removing according to the `ConcurrentMap` contract. A key set ignores the value dimension, so it is not the right tool to express state-transition rules. [ConcurrentMap — conditional remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#remove(java.lang.Object,java.lang.Object))

### 7.3. Registering an ID Does Not Mean Work Completes Exactly Once

`if (ids.add(id))` can select one winning registration within the scope of the set and its defined key lifecycle. It does not by itself prove that the subsequent task completes successfully exactly once.

You must define what state the set represents:

- **In progress:** the key may be removed when the work finishes so a future run can enter again.
- **Processed:** the key may need to be retained to recognize prior completion.
- **Registered in session:** losing the set when the process/session ends may be the intended behavior.

If you mark the key first and the work fails, the program must decide how to handle retries. If you remove the key to allow a retry, you must account for tasks still in flight. If you need to store status, results, or versions, a map with an explicit value type may fit better than a presence-only set.

A set also does not automatically provide expiration times or element count limits. Those requirements must be designed around the data lifecycle; they cannot be inferred from the container being thread-safe.

## 8. Choosing the Right API and Preserving Caller Permissions

### 8.1. Decision Table

| Need | Suitable API / representation to consider | Point to keep clear |
| --- | --- | --- |
| Standalone concurrent set, presence only | `ConcurrentHashMap.newKeySet()` | Not a view of an existing map |
| Similar set with an initial size estimate | `newKeySet(initialCapacity)` | Not a maximum capacity limit |
| View/remove keys of an existing map, no adding via set | `map.keySet()` | Still has permission to remove mappings |
| Allow adding keys to a map with a shared default value | `map.keySet(value)` | Does not filter by value; does not overwrite existing keys' values |
| Each key needs its own created value or state transitions | Appropriate map API | A single shared value is not a per-key factory |
| Expose read-only access to live keys | Unmodifiable wrapper around the view | The backing source can still change |
| Want a copy structurally detached from the map | Copy the key set under suitable collection conditions | A concurrent source does not automatically form a globally consistent snapshot |

Variable names should also reflect their actual meaning. `pendingKeys = map.keySet("PENDING")` can easily mislead readers into thinking it is a filter; if you use that name, documentation or surrounding design must clarify it. A name like `keysWithPendingDefault` better communicates its role as an insertion-capable view.

If you genuinely need the set of keys currently holding the value PENDING, you must define a separate query or collection pass. While the map is changing, you also need to decide whether the query result may mix points in time.

### 8.2. Wrapping to Prevent Modification by Recipients

Illustrative snippet:

```java
Set<String> visibleKeys =
        Collections.unmodifiableSet(states.keySet());
```

With `states` as a `ConcurrentHashMap<String, String>`, recipients cannot modify it through `visibleKeys` or its iterator. However, if the owner modifies `states`, the view still reflects the backing data; this is not a frozen copy. [Collections — unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

Simply changing the declared variable type from `KeySetView` to `Set` does not forbid removal. The declared type selects the general API surface, whereas mutability is determined by the actual object and any wrapper around it.

If callers should not have permission to delete map data, do not return `map.keySet()` directly and describe it as read-only.

### 8.3. Independent Copies and Consistency During Copying

You can create a new `HashSet` from the key set so that subsequent additions or removals on the copy do not modify the original map. However, if the original map is being updated, reading its keys still follows the source's traversal policy.

A copy that is stable **after creation** and source data belonging to **the same version at collection time** are two different requirements. If you need the second requirement, all writers and the snapshot process must follow a compatible protocol.

An external lock around a view or map does not force threads that only call `ConcurrentHashMap` APIs to acquire that lock. What must be proven is that all relevant paths actually coordinate, not merely the presence of a `synchronized` keyword in one place.

### 8.4. Relationship to `Collections.newSetFromMap`

Another way to compose a set is:

```java
Set<String> ids = Collections.newSetFromMap(
        new ConcurrentHashMap<String, Boolean>());
```

This is an illustrative declaration with the corresponding imports. The set inherits the ordering, concurrency, and performance characteristics of the backing map per the factory contract.

With `Collections.newSetFromMap`, the input map must be empty, and the documentation instructs not to access that map directly after the factory returns. Passing a fresh map inline as above helps adhere to this usage. [Collections — newSetFromMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#newSetFromMap(java.util.Map))

Do not confuse that rule with `existingMap.keySet(value)`: a key-set view is used on a map that already contains data and is designed to stay linked to a map that continues to be used. When the requirement is simply a `ConcurrentHashMap`-backed set, `newKeySet` expresses the intent more directly.

### 8.5. Type Inference with `var`

These two illustrative declarations do not have the same element type:

```java
var broad = ConcurrentHashMap.newKeySet();
var strings = ConcurrentHashMap.<String>newKeySet();
```

The first declaration has no target type `Set<String>` to constrain the type parameter, so the element type is inferred as `Object`. The second declaration specifies `String` explicitly.

If you only want to hold strings, use a target type:

```java
Set<String> ids = ConcurrentHashMap.newKeySet();
```

or the `var strings` form with `<String>` above. When the element type is `String`, `strings.add(42)` is rejected by the compiler. Do not use raw types to bypass this check.

## 9. Practice

### Exercise 1 — Is the Default Value a Filter?

A map contains `"a" -> "DONE"` and `"b" -> "PENDING"`. You obtain `keys = map.keySet("PENDING")`.

**Question:** Does `keys` contain `"a"`? Does `keys.clear()` remove only `"b"`?

**Answer:** `keys` contains both keys. The passed-in value is only used when adding new keys. `clear` removes every mapping in the backing map; it does not filter by the value PENDING.

### Exercise 2 — Does Not Supporting Add Mean Read-Only?

An API returns `map.keySet()` directly. Callers cannot add keys, but one calls `remove("invoice-7")`.

**Question:** Is the value data at that key preserved in the map? What needs to change if you only want to expose read access?

**Answer:** Removing a key through the view removes the entire mapping, so the value at that key is not preserved. You can wrap the view with `Collections.unmodifiableSet` if the requirement is a live key set that cannot be modified through the public path; if a detached snapshot is needed, you must create and publish an appropriate copy.

### Exercise 3 — Adding an Existing Key

A map contains `"task" -> "DONE"`. A view with default value `"PENDING"` calls `add("task")`.

**Question:** Is the old value replaced? When should you use a map operation instead of adding through the set?

**Answer:** It is not replaced; the addition does not modify the set and returns false in a context without interleaved operations. If the goal is to transition the state of an existing key, you need a map operation with an appropriate value or version condition.

### Exercise 4 — Two Keys, One List

A view created with `map.keySet(sharedList)` adds `"x"` and `"y"`, and then the program modifies `sharedList`.

**Question:** Are there two separate lists? Does the concurrent map automatically make list mutations thread-safe across multiple threads?

**Answer:** Both mappings reference the exact same passed-in value. There is no copying or per-key factory invocation. Thread safety of the list's state is a separate requirement.

### Exercise 5 — Boolean False in the Backing Map

From a `KeySetView<String, Boolean>` created by `newKeySet`, you retrieve the backing map and write `"x" -> false`.

**Question:** Does `set.contains("x")` return false because the value is false? Does `set.add("x")` change the value to true?

**Answer:** The key is present, so `contains` returns true. Adding does not overwrite an existing mapping, so in a sequential context it returns false and keeps the value false.

### Exercise 6 — A Duplicate-Free Set Still Allows Duplicate Processing

Two threads use `if (!ids.contains(id))` followed by `ids.add(id)` and both run the downstream work.

**Question:** Why is having a set without duplicate elements not enough? Which return value should you rely on?

**Answer:** Both threads can pass the check before either inserts the key. You must rely on the return value of `ids.add(id)` itself to select the registration attempt that actually modified the set, and you still need to define the key lifecycle and how task success or failure is handled.

## 10. References

- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `newKeySet` factories and the two `keySet` overloads.
- [ConcurrentHashMap.KeySetView Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.KeySetView.html): add/remove capabilities, backing map, default value, and iterator.
- [Set Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): membership rules, duplicates, and equality contract.
- [ConcurrentMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): conditional mapping operations.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): unmodifiable views and `newSetFromMap`.
