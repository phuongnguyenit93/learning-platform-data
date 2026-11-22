# Mutable Key Bugs and Concurrent Update Risks

## 1. Two Distinct Sources of Bugs to Identify

A HashMap can return unexpected results even in a single-threaded program: the object used as a key has had the information that defines its identity modified.

A HashMap can also fail when multiple threads access and update it concurrently without an appropriate coordination mechanism: read, write, and iteration operations no longer happen under sequential assumptions.

These two issues are not the same:

| Issue | Question to answer |
| --- | --- |
| Mutable keys | Does the data involved in equals/hashCode remain stable while the key is inside the Map? |
| Concurrent updates | Do threads have an access contract that protects the data and the entire business operation? |

Immutable keys do not by themselves make HashMap thread-safe. Likewise, a ConcurrentHashMap does not by itself make a mutating key object valid for hash-based lookup.

This lesson explains the underlying mechanisms, provides runnable experiments, and points out appropriate ways to organize data. The broken-key examples are documented as observations of a state that violated usage preconditions, not as behavior that every Map must guarantee.

## 2. What Goes Wrong with Mutable Keys?

HashMap locates a mapping using a hash code derived from the key, then checks the key to find the exact entry. When a key is inserted, the internal structure stores location metadata at that moment.

Suppose a key has an `id` field, and both `hashCode` and `equals` are based on `id`:

~~~text
When added:
key.id = 1
the mapping is placed according to the hash code of id 1.

After mutation:
key.id = 2
a new lookup computes the hash code using id 2.
~~~

The key object is still the exact same object in memory, but the new lookup data no longer matches the data used when the mapping was created.

This can lead to an observable situation: `get(key)` does not find the value, `size` still reports one mapping, and iterating over keys still encounters that very object. This is not evidence that HashMap “lost the reference”; the issue is that the lookup path by key is no longer using the same identity.

The Map contract states that behavior is undefined if a key object is mutated in a manner that affects equals comparisons while it is being used as a key. Do not design applications around a specific broken outcome of this condition. [Map documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Having the Same Reference Does Not Guarantee Lookup

A common misconception is “I passed the exact same object I put, so `get` is guaranteed to find it.” In hash-based lookup, there is still a bucket selection step and a stored hash check before reference equality even becomes useful.

If the key produces a different hash code after mutation, the object may reside in a location the new lookup never visits, or be rejected because the stored hash no longer matches. Therefore, do not use `==` as a justification for mutating key identity data.

### Not Every Change to a Key Object Breaks the Hash Contract

An object might have an immutable identifier and a mutable descriptive label. If `equals`/`hashCode` only use the stable identifier, changing the label does not necessarily break lookups.

However, the label is still data that may be shared across threads and needs its own access policy if mutated concurrently. Stability of key identity and thread-safety when mutating any field of an object are two different things.

## 3. Choosing Stable Keys and Avoiding Shallow Immutability

For an account with a stable id:

~~~java
record AccountKey(int id) {
}
~~~

The key consists of simple immutable data, so a new `AccountKey` instance with the same `id` can be used to look up the existing mapping. There is no need to retain and reuse the exact same key reference.

Conversely, merely declaring a key variable as `final` does not make the referenced object immutable:

~~~java
final MutableKey key = new MutableKey(1);
key.changeId(2);
~~~

Here, `final` prevents reassigning the `key` variable to another object; it does not block method calls that mutate the object.

### Records Containing Collections Still Need Content Inspection

The following snippet does not automatically freeze the list:

~~~java
record GroupKey(List<String> parts) {
}
~~~

If a list is passed in and later modified through an external reference, the contents participating in the record's `equals`/`hashCode` can change accordingly.

One design approach with `String` elements in the example:

~~~java
record GroupKey(List<String> parts) {
    GroupKey {
        parts = List.copyOf(parts);
    }
}
~~~

The constructor takes an unmodifiable structural copy of the list. Since `String` elements are immutable, the content used to identify the key in this example stays stable against external modifications to the input list.

`List.copyOf` does not deep-copy every element. If elements are mutable objects and `GroupKey`'s `equals`/`hashCode` depend on those objects' contents, you must also decide how to protect those components.

The null policy must also be clear: `List.copyOf` in this example rejects a null list or null elements. That is part of the chosen key construction contract, not a universal rule for all Map keys.

### The Same Key May Be Used in Multiple Maps

Copying mappings into another Map usually still shares the same key objects. If a key is mutated afterward, multiple structures may break at the same time.

Switching Map classes or making a shallow copy is no substitute for creating a stable key value. Identity data must be decided where keys are constructed, rather than hoping the container structure will protect them on its own.

## 4. HashMap Provides No Internal Synchronization

HashMap is not synchronized. When multiple threads access it concurrently and at least one thread modifies its structure, it must be synchronized externally using an appropriate mechanism. [HashMap documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Structural modifications include adding or deleting mappings. Changing the value associated with an existing key does not change `size` and is generally not called a structural modification, but that does **not** make uncoordinated concurrent value updates safe.

Three requirements are easily conflated:

| Requirement | Meaning |
| --- | --- |
| Consistent internal state | The structure holding mappings is accessed according to its contract |
| Visibility of updates | Reading threads have proper memory relationships to observe published state |
| Atomicity of business operations | Steps that must execute together cannot be interleaved by another operation to produce wrong results |

An immutable `String` key only helps with identity; it does not provide any of these three properties for HashMap.

Declaring the Map reference variable as `volatile` also does not turn a `get`-then-`put` sequence into an atomic operation. `volatile` establishes publication/visibility relationships under the memory model, not multi-step compound update rules. Locking mechanisms and happens-before relationships must be applied properly to shared data. [Java Language Specification 17, Threads and Locks chapter](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-17.html).

Do not characterize concurrency bugs by a single mandatory outcome such as “always throws an exception” or “always loses exactly one update.” Without an access contract, outcomes can depend on execution scheduling. A passing test run does not prove that the access pattern is correct.

## 5. Locking Individual Calls Is Not Enough for Compound Operations

Suppose a counter is currently 0. Two tasks both want to increment it by one:

~~~text
Task A reads 0.
Task B reads 0.
Task A writes 1.
Task B writes 1.
Final result: 1, even though there were two increment requests.
~~~

This bug is called a lost update: a later task overwrites a result computed from stale state.

It can still happen even when every individual `get` and every individual `put` is protected by a lock, if the “read-compute-write” sequence is not inside the same protected region.

Example illustrating an insufficient lock scope:

~~~java
int before;
synchronized (lock) {
    before = map.get("count");
}

// Another task may read or update in between.

synchronized (lock) {
    map.put("count", before + 1);
}
~~~

The variables `map` and `lock` are assumed to already exist. This code protects each individual Map access with the same `lock`, but does not protect the decision based on `before`.

How to express the entire increment under one lock:

~~~java
synchronized (lock) {
    map.put("count", map.get("count") + 1);
}
~~~

For this approach to be correct, every party touching that data must follow the same locking mechanism and the increment's preconditions—such as the `"count"` key always holding a valid integer.

If one party uses `lockA` and another uses `lockB`, the two `synchronized` blocks do not mutually exclude each other. If one party bypasses the rule and accesses the Map directly, the shared contract is broken again.

## 6. A Java 17+ Program with Verifiable Results

The following program has three groups:

1. Mutating the `id` of a key already inside a `HashMap` and a `ConcurrentHashMap`, executed sequentially to observe key identity failure.
2. Using an immutable key and copying the component list to keep keys stable.
3. Two tasks incrementing a counter using split lock regions, a full lock region, and `ConcurrentHashMap.compute`.

In the lost-update example, each `HashMap` access is still inside `synchronized`. `CountDownLatch` forces both tasks to finish reading before either can write, so the result `1` is produced by an intentional coordination schedule. This demonstrates an incorrect atomicity scope rather than running unsynchronized writes on a `HashMap` and hoping for an accidental failure.

File `HashMapSafetyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HashMapSafetyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && id == key.id;
        }
    }

    record AccountKey(int id) {
    }

    record GroupKey(List<String> parts) {
        GroupKey {
            parts = List.copyOf(parts);
        }
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected safe-case result");
        }
    }

    static void awaitBoth(Future<Void> first, Future<Void> second)
            throws Exception {
        first.get(10, TimeUnit.SECONDS);
        second.get(10, TimeUnit.SECONDS);
    }

    static int splitCriticalSections(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new HashMap<>();
        map.put("count", 0);
        Object lock = new Object();
        CountDownLatch bothRead = new CountDownLatch(2);
        Callable<Void> task = () -> {
            int before;
            synchronized (lock) {
                before = map.get("count");
            }
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Both readers did not arrive");
            }
            synchronized (lock) {
                map.put("count", before + 1);
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        synchronized (lock) {
            return map.get("count");
        }
    }

    static int wholeCriticalSection(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new HashMap<>();
        map.put("count", 0);
        Object lock = new Object();
        Callable<Void> task = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    map.put("count", map.get("count") + 1);
                }
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        synchronized (lock) {
            return map.get("count");
        }
    }

    static int atomicCompute(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new ConcurrentHashMap<>();
        map.put("count", 0);
        Callable<Void> task = () -> {
            for (int i = 0; i < 1000; i++) {
                map.compute("count", (key, old) -> old + 1);
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        return map.get("count");
    }

    public static void main(String[] args) throws Exception {
        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> hash = new HashMap<>();
        Map<MutableKey, String> concurrent = new ConcurrentHashMap<>();
        hash.put(key, "value");
        concurrent.put(key, "value");
        System.out.println("before mutation hash=" + key.hashCode()
                + " hashMap=" + hash.get(key)
                + " concurrent=" + concurrent.get(key));

        key.changeId(2);
        System.out.println("observed after mutation hash=" + key.hashCode()
                + " hashMap=" + hash.get(key)
                + " concurrent=" + concurrent.get(key));
        System.out.println("observed sizes after mutation="
                + hash.size() + "," + concurrent.size());
        System.out.println("observed stored key same reference="
                + hash.keySet().stream().anyMatch(stored -> stored == key));

        Map<AccountKey, String> accounts = new HashMap<>();
        accounts.put(new AccountKey(7), "stable");
        String stable = accounts.get(new AccountKey(7));
        check(Objects.equals(stable, "stable"));
        System.out.println("immutable key lookup=" + stable);

        List<String> input = new ArrayList<>(List.of("team", "A"));
        GroupKey group = new GroupKey(input);
        Map<GroupKey, String> groups = new HashMap<>();
        groups.put(group, "group-value");
        input.set(1, "B");
        String groupValue = groups.get(new GroupKey(List.of("team", "A")));
        check(Objects.equals(groupValue, "group-value"));
        System.out.println("defensive key lookup=" + groupValue);
        System.out.println("defensive key parts=" + group.parts());
        try {
            group.parts().add("C");
            throw new AssertionError("Expected unmodifiable parts");
        } catch (UnsupportedOperationException exception) {
            System.out.println("parts modification=UnsupportedOperationException");
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            int split = splitCriticalSections(pool);
            int whole = wholeCriticalSection(pool);
            int atomic = atomicCompute(pool);
            check(split == 1);
            check(whole == 2000);
            check(atomic == 2000);
            System.out.println("split critical sections count=" + split
                    + " expected=2");
            System.out.println("whole critical section count=" + whole);
            System.out.println("concurrent compute count=" + atomic);
            System.out.println("safe-case checks=PASS");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 HashMapSafetyDemo.java
java HashMapSafetyDemo
~~~

Use JDK 17 or newer supporting target release 17. The code uses Java 17-compatible APIs and syntax.

Stdout from the verification run:

~~~text
before mutation hash=1 hashMap=value concurrent=value
observed after mutation hash=2 hashMap=null concurrent=null
observed sizes after mutation=1,1
observed stored key same reference=true
immutable key lookup=stable
defensive key lookup=group-value
defensive key parts=[team, A]
parts modification=UnsupportedOperationException
split critical sections count=1 expected=2
whole critical section count=2000
concurrent compute count=2000
safe-case checks=PASS
~~~

The lines labeled `observed` record behavior seen after mutating the key; they are not a requirement that every Map implementation must handle a key violating its contract in that exact way. The `check` assertions in the code do not treat those observed outcomes as correctness conditions.

### Why Does the Concurrency Experiment Have Deterministic Results?

Both tasks write only after `CountDownLatch` confirms both have read. Because no write has happened yet, both hold `before` equal to 0. The two subsequent writes are individually locked, but both write 1; their order does not change the result.

The `wholeCriticalSection` example performs 1000 increments per task and keeps both `get` and `put` inside the same lock region. Both tasks completing yields 2000.

The `atomicCompute` example uses `ConcurrentHashMap` with the `"count"` key already initialized to 0, and no party removes the key. Each `compute` increments from the current value under that Map type's atomic contract, so two groups of 1000 iterations also yield 2000.

The program awaits `Future` completion to retrieve results and propagate task errors to the main thread. The wait timeout prevents coordination bugs from turning into an infinite hang in the example; it does not participate in the counter's correctness. `ExecutorService` is shut down in `finally`.

### Why Does ConcurrentHashMap Still Encounter the Key Bug?

Both Maps in the first part hold the exact same `MutableKey` object. Changing `id` alters the identity data in both places. The fact that `ConcurrentHashMap` protects concurrent structural updates does not automatically relocate a mapping to a valid new identity.

In the run, `size` remains 1, yet `get` with the mutated key returns `null` in both Maps. The takeaway must be the requirement to keep keys stable, not a workflow of “change id and then use size to repair the Map.”


## 7. Choosing an Appropriate Access Contract

### Single Data Owner and Sequential Access

If the Map belongs to a single task, an object with clear ownership, or a single thread, `HashMap` is a natural choice when other requirements align.

Avoid exposing the Map itself or mutable key objects outside the owner. A method that directly returns the internal Map's `keySet`, `values`, or `entrySet` can expose additional paths to mutate mappings.

Clear ownership reduces synchronization needs, but you still need keys with stable identity. Even a single thread can cause mutable-key bugs like in the first part of the program.

### HashMap with a Shared Guard Lock

For data accessed by multiple threads, you can keep a dedicated `lock` object and require all related operations to obey it.

What needs to be determined is not merely “is there `synchronized` or not,” but:

- Which data is protected by the lock?
- Which steps of a business operation must stay inside the same region?
- Do iterations or copies use the same mechanism?
- Are there any paths bypassing the lock via the underlying Map, collection views, or value objects?

For the increment in the program, the scope to protect is reading the current number, computing the new number, and writing the new number. For a transfer operation between two keys, even more state may need to move together.

Placing the lock where the data is owned and keeping it stable is usually clearer than having each method create a `new Object()` to synchronize on. Different newly created locks do not coordinate access to the same Map.

### Collections.synchronizedMap

You can wrap it:

~~~java
Map<String, Integer> counters =
        Collections.synchronizedMap(new HashMap<>());
~~~

All accesses to the backing structure must go through the returned wrapper or its views according to the contract. Do not keep another reference and use the underlying `HashMap` directly to bypass the wrapper.

If you combine multiple calls into an increment, protect the entire sequence with the wrapper's monitor:

~~~java
synchronized (counters) {
    int current = counters.getOrDefault("count", 0);
    counters.put("count", current + 1);
}
~~~

This snippet assumes the counter does not store `null` and all parties follow the same contract. The fact that the wrapper synchronizes individual `get` and `put` calls does not automatically turn a hand-written get-compute-put sequence into an uninterruptible operation.

When traversing collection views via `iterator`, `spliterator`, or `stream`, the `synchronizedMap` contract requires synchronizing on the returned Map itself. Locking on `counters.keySet()` uses a different monitor and does not substitute for locking on `counters`. [Collections.synchronizedMap documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

If you need a snapshot of data for long-running processing outside the lock region, you can copy it inside the protected region and process the copy:

~~~java
Map<String, Integer> snapshot;
synchronized (counters) {
    snapshot = new HashMap<>(counters);
}
~~~

With immutable `String` keys and `Integer` values in the example, the structural copy has straightforward semantics. If keys or values contain mutable objects, a shallow copy does not by itself protect deep contents from other tasks.

### ConcurrentHashMap and Contracted Atomic Operations

`ConcurrentHashMap` supports concurrent access and provides operations such as `putIfAbsent`, conditional `replace`, `compute`, or `merge` with appropriate guarantees. For a per-key counter, `compute` as shown in the program keeps the computation and update within the atomic operation defined by that class. [ConcurrentHashMap documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Limitations to understand:

- A hand-written `get`-then-`put` sequence is still two operations, even though each individual operation is thread-safe.
- A single-key `compute` does not create a multi-key transaction.
- The computation function should be short and must not mutate the same Map from within.
- `ConcurrentHashMap` does not allow `null` keys or `null` values to be stored.
- Keys must still uphold their identity and hash code contract.
- Mutable value objects still need their own access policy.

Do not replace `HashMap` with `ConcurrentHashMap` while keeping all old business assumptions unchanged. For example, an application that uses `null` to represent a “looked up but not found” state needs a different value model before switching Map classes.

`Map`'s `compute` methods in general also do not share a single universal atomicity promise across all implementations. You must rely on the contract of the specific implementation used, rather than just seeing identical method names.

## 8. A Thread-Safe Map Does Not Protect Its Inner Values

Suppose a Map stores task lists:

~~~java
Map<String, List<String>> tasks = new ConcurrentHashMap<>();
tasks.computeIfAbsent("team", key -> new ArrayList<>()).add("job");
~~~

`ConcurrentHashMap` can protect putting or retrieving the mapping from `"team"` to the list. However, `add` operates on the returned `ArrayList`; it is not automatically protected by Map operations as an action on the list.

If multiple threads mutate that list concurrently, you need a value type that supports concurrent usage or a proper locking mechanism for it. Another approach is updating with new immutable values and only swapping the mapping under an appropriate atomic rule.

Similarly, a value object with a mutable `count` field is not automatically protected just because it is stored in a `ConcurrentHashMap`. Four layers of responsibility must be distinguished:

~~~text
Key identity
    -> stability of equals/hashCode.

Map structure
    -> access and mapping update contract.

Multi-step business operation
    -> proper atomicity scope.

Value object contents
    -> appropriate dedicated read/write mechanism.
~~~

Fixing one layer does not mean the remaining layers are correct.

This also explains why a read-only wrapper does not make deep data immutable. Someone holding a reference to a value object may still mutate that object through another reference.

## 9. ConcurrentModificationException Is a Failure-Detection Signal, Not a Safety Barrier

A `HashMap` iterator may detect illegal structural modifications and throw `ConcurrentModificationException`. However, this detection is a best-effort bug-catching mechanism of the implementation, not a synchronization system.

This exception does not necessarily require two threads. A single thread iterating with `for-each` while removing directly via the Map can also violate the iterator contract. [ConcurrentModificationException documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html).

Example illustrating improper usage:

~~~java
for (String key : map.keySet()) {
    if (key.startsWith("old-")) {
        map.remove(key);
    }
}
~~~

To remove elements during iteration in an appropriate sequential context, use `iterator.remove` on the active iterator or a supported filtering operation. If updates come from other threads, you must also follow the source's coordination mechanism; changing the removal method does not by itself resolve all contention.

Do not handle this by catching `ConcurrentModificationException` and treating the partial traversal result as a complete snapshot. Likewise, do not conclude “no exception was thrown, so multi-threaded usage is safe.” Visibility bugs or lost updates do not need to trigger this exception.

For a concurrent Map type, iterators may have a different traversal contract. The fact that an iterator does not throw an exception during concurrent updates does not mean it captures the entire Map at a single point in time.

If you need reporting data consistent as of a single point in time or invariants across multiple mappings, design a snapshotting mechanism or read region tailored to that requirement.

## 10. Changing Keys and Handling Contract-Violated Data

### When Identity Truly Needs to Change

Instead of mutating the `id` of an object already serving as a key, you can use immutable key objects and perform an explicit mapping replacement.

When the new key differs from the old key, the business workflow must decide:

1. Does the old key exist?
2. Does the new key already have a mapping, and how are conflicts handled?
3. What value is transferred?
4. Are readers allowed to observe the intermediate state between removal and insertion?
5. If one step fails, what is the desired resulting state?

If the entire process must appear as an uninterruptible change, protect it with an appropriate mechanism. Two consecutive `remove` and `put` calls on `ConcurrentHashMap` still do not form a key-replacement transaction.

If the old identifier was also needed to link external data, changing it is also a domain-model decision. Do not assume changing one Java field is enough to update all related relationships.

### If a Key Has Already Been Mutated While Inside a Map

Do not assume calling `remove` with the mutated key is guaranteed to find the old mapping, or that calling `put` with that same object is guaranteed to merely “fix its position” without other consequences. You have left the usage conditions guaranteed by the contract.

Rebuilding the Map from the broken key references may not recover the original identity. Two keys that were mutated to become equal could even collide during reconstruction.

Remediation must start from a data source that can determine true identity, halt the problematic updates, and rebuild state according to an explicit conflict policy in a controlled context. Do not rely on an internal quirk of a specific `HashMap` version to consider data repaired from a business perspective.

The long-term fix lies where keys are created and owned: restrict mutation of identity fields, copy component data when needed, and audit paths that expose mutable references.

### Shared Reading of Unchanged State

Data can be shared for read-only access once the state is completely constructed, published through a mechanism that guarantees proper visibility, and not further modified in violation of the contract. Keys and values must also remain stable to the extent assumed by readers.

This condition is different from “nobody mutated it during the last test run.” An exposed Map reference modified from an uncontrolled path breaks the read-only assumption.

## 11. Quick Bug-Identification Table

| Symptom or Pattern | What to Check |
| --- | --- |
| `size` is non-zero, but `get` with the old key returns `null` | Was the key's `equals`/`hashCode` data mutated? Could the value itself be `null`? |
| Switched to `ConcurrentHashMap`, yet key lookup still fails | Is the key actually stable, or was only the container class changed? |
| Declared `final`, yet key data changes | Is `final` only protecting the reference or truly protecting internal state? |
| Record has a `List` component and lookups fail | Was the list or its elements mutated through another reference? |
| Two increments result in only +1 | Does the lock scope cover read-compute-write? |
| Every method is `synchronized`, yet business logic is wrong | Are calls that must be atomic split across multiple regions? |
| Both sides have `synchronized`, yet they fail to coordinate | Do both sides use the same monitor and the same data rules? |
| `synchronizedMap` behaves unexpectedly during iteration | Is iteration protected on the wrapper Map itself per its contract? |
| `compute` on `HashMap` is assumed thread-safe | Which class contract is being relied upon? |
| `ConcurrentHashMap` holds an `ArrayList` that is mutated directly | What mechanism protects the value list? |
| No `ConcurrentModificationException` observed | Not enough information to conclude thread-safety |
| Copying the Map to fix a key bug | Does the copy still share the mutated key? |

These questions help classify the bug before choosing a fix. Not every `null` result is caused by concurrency, and not every multi-threaded bug is caused by mutable keys.

## 12. Exercises and Solutions

### Exercise 1 — Is `final` Enough?

A `final` variable points to a `MutableKey` that has an `id` setter. After `put`, the setter is called. The variable is never reassigned, so is lookup guaranteed to remain valid?

**Solution:** No. `final` only prevents changing the variable's reference. The object's identity data was still mutated, which can violate the Map key usage contract.

### Exercise 2 — Does Changing the Description Break the Key?

A key has an immutable `id` and a mutable `description`. `equals`/`hashCode` only examine `id`. Does changing `description` necessarily break hash-based lookup?

**Solution:** Not necessarily, because the identity data does not change. However, if `description` is read and modified across threads, that field still needs its own access contract.

### Exercise 3 — A Record Containing a List

`record Key(List<String> parts)` receives an `ArrayList` from outside. External code mutates the `ArrayList` after `Key` is put into a Map. Why is the `record` keyword not enough?

**Solution:** `record` does not automatically deep-copy component objects. The list contents participating in equality and hash codes can change. You can take an unmodifiable copy of the list when constructing the key; if elements themselves are mutable, deeper handling is required.

### Exercise 4 — Can `ConcurrentHashMap` Fix Mutable Keys?

You replace `HashMap` with `ConcurrentHashMap` but still mutate the `id` used in `equals`/`hashCode` after `put`. Is the issue solved?

**Solution:** No. Concurrent structural update safety does not automatically maintain the position of a key whose identity changed. Stable keys are still required.

### Exercise 5 — Why Does the Split-Lock Example Always Produce 1?

In the program, every `get` and `put` uses the same `lock`, yet the result is still 1 after two tasks. What role does the latch play?

**Solution:** The latch forces both tasks to read before either can write, so both compute from 0 and both write 1. The lock prevents two Map accesses from happening simultaneously, but fails to protect the read-compute-write span as a single unit. This is an atomicity-scope bug.

### Exercise 6 — Different Locks on Each Side

Thread A runs `synchronized(lockA)` and Thread B runs `synchronized(lockB)`, both modifying the same `HashMap`. Can the Map be considered protected because `synchronized` is used everywhere?

**Solution:** No. Two different monitors do not exclude each other. You need a single shared contract for the shared data and the required operation scope.

### Exercise 7 — Iterating a `synchronizedMap`

Given a `synchronizedMap` `m`, you want to iterate over `m.keySet()`. Does locking on the `keySet` object substitute for locking on `m` under the wrapper's contract?

**Solution:** No. You must protect the traversal using the returned Map's monitor, such as `synchronized(m)`, and ensure no access path to the backing Map bypasses the wrapper.

### Exercise 8 — No Exception Thrown

A multi-threaded test with `HashMap` runs hundreds of times without throwing `ConcurrentModificationException`. Is that enough to conclude it is correct?

**Solution:** No. The exception is only a mechanism to catch certain violations; lost updates and visibility issues may never trigger it. You must verify the access contract and atomicity, not just wait for a failure to surface.

### Exercise 9 — Safe Map, Safe Values?

A `ConcurrentHashMap` stores an `ArrayList`. Two threads retrieve the same list and both call `add`. Does the Map's thread-safety cover this operation?

**Solution:** No. `add` is an operation on the value object. You need a suitable value type or protection mechanism for the list, or a design that updates with new values.

### Exercise 10 — Moving from an Old Key to a New Key

You need to change an identifier and plan to remove `oldKey` and then put `newKey` on a `ConcurrentHashMap`. Do the two calls automatically form a transaction so readers never see an intermediate state?

**Solution:** No. You must define multi-step consistency and use an appropriate mechanism. Use immutable key objects, check for new-key collisions, and define a failure policy rather than mutating a key object already inside the Map.

## 13. Keeping the Four Boundaries Intact

Before fixing a `HashMap` bug, determine whether the key identity data is stable, what mechanism governs access to the Map structure, how wide the atomicity scope of the business operation must be, and whether inner values are mutated separately.

The mutable-key example explains why even the exact same reference can fail lookup. The counter example explains why individually protected calls can still compose into a broken operation. The two fixes must target those respective root causes.

Stable keys, clear ownership, and a consistent update contract enable `HashMap` to be used correctly. A container class alone cannot replace all of these decisions.
