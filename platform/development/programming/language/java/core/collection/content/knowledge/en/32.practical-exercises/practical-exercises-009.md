# Building a Java Collection Decision Table and Self-Assessment Through Scenarios

> **Objective:** Select a collection based on real-world requirements; justify the choice in terms of uniqueness, ordering, common operations, cost, `null` handling, mutability, and multithreading; then self-assess using scenarios and a scoring rubric.

## 1. Ask the Right Questions Before Choosing a Class

In the Java Collections Framework, `List`, `Set`, and `Queue` belong to the `Collection` hierarchy; `Deque` extends `Queue`. `Map` stores key–value pairs and **does not inherit from `Collection`**.

When given a data storage problem, ask in turn:

1. **Data shape?** Sequence, unique set, key-based lookup, queue, stack, or priority queue?
2. **Duplicates?** Do you need to retain multiple occurrences of the same element? Must keys in a map be unique?
3. **Ordering?** By position, insertion order, comparator-sorted order, FIFO/LIFO, or priority?
4. **Dominant operations?** `get(i)`, `contains`, `get(key)`, add/remove at both ends, range queries, or processing the next job?
5. **Volume and updates?** Large or small dataset, read-heavy or write-heavy, bounded capacity, or an unmodifiable view/copy needed?
6. **Concurrency and constraints?** Multiple threads modifying concurrently? Atomic operations, blocking producer/consumer, `null` values, or enums required?

Workflow: **choose the interface by data contract → determine ordering/duplicates → identify hot operations → evaluate concurrency and capacity → pick the implementation → verify assumptions**. Not every application needs just a single data structure; you can combine a map for key lookups with a queue for job dispatching.

## 2. Decision Table: Choose by Requirements, Not by Habit

| Requirement | Typical Class | Why | Caveats |
|---|---|---|---|
| Ordered sequence, retains duplicates, index access | `ArrayList<E>` | Fast `get(i)`, efficient append at the end | Inserting/removing at the head or middle shifts elements |
| Sequence that does not need structural changes after creation | `List.of`, `List.copyOf` | Disallows `add/remove/set` | Disallows `null`; does not deep-copy nested mutable objects |
| Unique elements, order does not matter | `HashSet<E>` | Fast average `add/contains/remove` | No guaranteed iteration order |
| Unique elements, preserves first-appearance order | `LinkedHashSet<E>` | Set + insertion order | Does not sort by value |
| Unique elements, always sorted or range queries needed | `TreeSet<E>` | Provides `first/last/subSet` and comparator ordering | Operations take roughly `O(log n)`; comparator defines "duplicate" elements |
| Lookup by unique key, order not required | `HashMap<K,V>` | Average `O(1)` `get/put` | Do not rely on iteration order |
| Map ordered by insertion or recent access | `LinkedHashMap<K,V>` | Predictable iteration order; foundation for LRU caches | LRU requires enabling access-order and implementing eviction |
| Sorted-key map requiring `subMap` | `TreeMap<K,V>` | Navigable, iterates in key order | Does not sort by value |
| Single-threaded FIFO or LIFO | `ArrayDeque<E>` | Fast at both ends, implements `Deque` | Disallows `null`, not thread-safe |
| Jobs retrieved by priority | `PriorityQueue<E>` | `offer/poll` in roughly `O(log n)` | Iterator is not guaranteed to be sorted; equal priorities do not automatically follow FIFO |
| Multithreaded bounded queue requiring blocking | `ArrayBlockingQueue<E>` | `put/take` wait when full/empty | Must design task cancellation/shutdown to avoid waiting indefinitely |
| Non-blocking concurrent queue without fixed capacity limit | `ConcurrentLinkedQueue<E>` | Non-blocking FIFO | Does not inherently provide backpressure |
| Map with concurrent multi-threaded writes | `ConcurrentHashMap<K,V>` | `merge/compute/putIfAbsent` support per-key atomic updates | Disallows `null`; separate "read then write" calls can still race |
| Multithreaded list with frequent reads and rare writes | `CopyOnWriteArrayList<E>` | Snapshot iterator | Every modification copies the underlying array |
| Set of values from a single enum | `EnumSet<E>` | Compact, fast, iterates in enum declaration order | Accepts only enum constants, disallows `null` |
| Map with enum keys | `EnumMap<K,V>` | Compact, fast, keys ordered by enum declaration | Keys must belong to the specified enum, disallows `null` |

**Conditional defaults:** `ArrayList` for sequences, `HashSet` for sets, `HashMap` for key-value mappings, and `ArrayDeque` for FIFO/LIFO. Switch to another class when *specific requirements* make it necessary.

`LinkedList` is not a default speed optimization for `List`. `get(i)` takes `O(n)` to traverse nodes, and per-node memory overhead is higher; inserting/removing at an already located node can be `O(1)`, but locating that node typically still takes `O(n)`. For standard stacks and queues, `ArrayDeque` is generally preferred over the legacy `Stack` class.

## 3. Complexity Table and Associated Conditions

`n` is the number of elements; hash complexities assume a reasonable hash function and normal distribution. An average `O(1)` operation still carries resize, collision, allocation, and memory-locality costs.

| Structure | Search / Access | Add | Remove | Ordering Semantics |
|---|---|---|---|---|
| `ArrayList` | `get(i): O(1)`, `contains: O(n)` | End `O(1)` amortized; middle `O(n)` | Head/middle `O(n)` | By position (index) |
| `HashSet` / `HashMap` | `contains/get: O(1)` average | `O(1)` average | `O(1)` average | Unspecified |
| `LinkedHashSet` / `LinkedHashMap` | `O(1)` average | `O(1)` average | `O(1)` average | Insertion order; map also supports access order |
| `TreeSet` / `TreeMap` | `O(log n)` | `O(log n)` | `O(log n)` | By comparator / key order |
| `ArrayDeque` | Element search `O(n)` | Both ends `O(1)` amortized | Both ends `O(1)` amortized | Deque order |
| `PriorityQueue` | `peek: O(1)`, `contains: O(n)` | `offer: O(log n)` | `poll: O(log n)` | Head removal follows comparator |

Contract pitfalls to verify:

- `HashSet`/`HashMap` depend on `equals` and `hashCode`: if `a.equals(b)`, both objects must produce the same hash code. Never mutate fields that participate in hashing while an element or key is stored in the collection.
- `TreeSet`/`TreeMap` treat two elements or keys as equivalent if the comparator returns `0`. A comparator that compares only scores can drop students who share the same score. To satisfy the Set/Map equality contract, keep the comparator consistent with `equals`.
- `ArrayList`, `HashMap`, and `HashSet` allow `null` (`HashMap` permits one `null` key and multiple `null` values). `ArrayDeque`, `PriorityQueue`, `ConcurrentHashMap`, and `List.of/Set.of/Map.of` disallow `null`. `TreeSet/TreeMap` using natural ordering do not allow `null`; a custom comparator may define ordering for `null`.
- `List.copyOf` creates a structurally unmodifiable list without deep-copying mutable elements. `Collections.unmodifiableList(original)` creates a read-only view: if the backing list changes, the view reflects those changes.
- `HashSet` iteration may occasionally appear stable, but the API makes no guarantee. `LinkedHashSet` preserves insertion order; `TreeSet` sorts according to its comparator.
- `PriorityQueue` only guarantees priority order when **removing the head via `poll`**; iterating with an iterator does not yield elements in priority order. Ties in priority require a secondary tie-breaking comparator criterion such as a sequence number.
- Fail-fast iterators are neither a synchronization mechanism nor a guarantee to detect every data race. Concurrent collections may use weakly consistent iterators; `CopyOnWriteArrayList` uses a snapshot iterator. Check the exact semantics before choosing.

## 4. Building Your Own Decision Table for a Feature

Tie each row to **a measurable requirement** rather than merely listing class names:

| Question | Example Data | Candidates | Decision |
|---|---|---|---|
| Retain duplicate occurrences and access the *i*-th item? | Action history | `List` / `Set` | `ArrayList` |
| Deduplicate while keeping first-appearance order? | Article tags | `HashSet` / `LinkedHashSet` | `LinkedHashSet` |
| Look up by code thousands of times? | SKU code → product | `ArrayList` / `HashMap` | `HashMap` |
| Query timestamps between A and B? | Sorted milestones | `HashSet` / `TreeSet` | `TreeSet` or `TreeMap` |
| Process earlier arriving jobs first? | Single-threaded FIFO | `ArrayDeque` / `PriorityQueue` | `ArrayDeque` |
| Cap waiting jobs at 500 across multiple threads? | Producer/consumer | `ConcurrentLinkedQueue` / `ArrayBlockingQueue` | `ArrayBlockingQueue<>(500)` |
| Process the most important job first? | Prioritized tickets | `ArrayDeque` / `PriorityQueue` | `PriorityQueue` + tie-breaker |
| Increment counters per key across multiple threads? | Page view counting | `HashMap` / `ConcurrentHashMap` | `ConcurrentHashMap` + `merge` |

State your decision in the form: "I use **X** because I need **property Y** and primarily call **operation Z**; I accept **limitation W**." For large datasets or latency-critical paths, benchmark the realistic workload. Do not optimize solely on Big-O notation.

## 5. Java 17: One Problem, Multiple Fit-for-Purpose Collections

Below is a complete program. Save it as `CollectionChoiceDemo.java`.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.Set;
import java.util.TreeSet;

public class CollectionChoiceDemo {
    record Job(String name, int priority, long sequence) {}

    public static void main(String[] args) {
        List<String> history = new ArrayList<>();
        history.add("đọc");
        history.add("viết");
        history.add("đọc");

        Set<String> unique = new LinkedHashSet<>(history);
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String action : history) {
            counts.merge(action, 1, Integer::sum);
        }

        Deque<String> fifo = new ArrayDeque<>();
        fifo.addLast("A");
        fifo.addLast("B");

        Set<Integer> scores = new TreeSet<>(List.of(7, 9, 8, 7));

        Queue<Job> jobs = new PriorityQueue<>(
            Comparator.comparingInt(Job::priority)
                .reversed()
                .thenComparingLong(Job::sequence)
        );
        jobs.offer(new Job("normal", 2, 0));
        jobs.offer(new Job("urgent", 5, 1));
        jobs.offer(new Job("urgent2", 5, 2));

        System.out.println("Lịch sử: " + history);
        System.out.println("Duy nhất: " + unique);
        System.out.println("Số lần: " + counts);
        System.out.println("FIFO: " + fifo.removeFirst() + " -> " + fifo.removeFirst());
        System.out.println("Điểm tăng dần: " + scores);
        System.out.println("Ưu tiên: "
            + jobs.remove().name() + ", "
            + jobs.remove().name() + ", "
            + jobs.remove().name());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 CollectionChoiceDemo.java
java CollectionChoiceDemo
~~~

Exact output:

~~~text
Lịch sử: [đọc, viết, đọc]
Duy nhất: [đọc, viết]
Số lần: {đọc=2, viết=1}
FIFO: A -> B
Điểm tăng dần: [7, 8, 9]
Ưu tiên: urgent, urgent2, normal
~~~

**Explanation:** `ArrayList` retains both occurrences of `"đọc"` in the history; `LinkedHashSet` deduplicates while preserving encounter order; `LinkedHashMap` tallies counts and keeps key insertion order. `ArrayDeque` handles FIFO at both ends; `TreeSet` deduplicates while sorting scores; `PriorityQueue` extracts the highest priority first. The two priority-5 jobs are ordered by `sequence`; if the comparator only compared priority, you could not assume that the earlier-arriving job would always be polled first.

## 6. 12 Self-Assessment Scenarios

**How to proceed:** Before reading the reference answers in Section 7, write down for each scenario: (a) the interface/class, (b) the decisive property, and (c) one risk or assumption to verify. Multiple solutions can be valid as long as they satisfy the contract.

1. **Action log:** Preserves execution order and repeated actions; the UI needs to fetch the *i*-th action.
2. **Hashtags:** Removes duplicates, displays tags in first-appearance order, does not sort alphabetically.
3. **Product inventory:** Fast product lookup by SKU; no display ordering required; each SKU maps to a single product.
4. **Calendar milestones:** Sorted chronologically in ascending order with range queries between timestamps A and B.
5. **Undo stack:** Retrieves the most recent action first; single-threaded, no index-based lookup required.
6. **Image processing:** Producer and consumer run on different threads; maximum 1000 pending tasks; producer must block when the queue is full.
7. **Support tickets:** Higher priority is processed first, ties broken by arrival order; no need to iterate over the entire queue in sorted order.
8. **View counter:** Multiple threads increment counters for the same key; increments must never be lost.
9. **Listener list:** Multiple threads iterate frequently with very rare writes; each traversal needs a stable snapshot.
10. **User permissions:** Consists solely of enum constants `ADMIN/EDITOR/VIEWER`; a user holds a duplicate-free set of roles.
11. **Top score leaderboard:** Multiple students can share the same score; display scores in descending order while retaining all students.
12. **LRU cache:** Lookup by key; single-threaded; when exceeding 100 entries, evict the entry that has been **least recently accessed** (not the oldest inserted entry).

If a scenario does not specify `null` handling, mutability, dataset size, or concurrency, state your assumptions explicitly. Do not grade a class as "wrong" simply because it differs from the reference key if it satisfies every constraint.

## 7. Reference Answers and Rationale

| # | Suitable Collection | Explanation / Pitfalls to Avoid |
|---|---|---|
| 1 | `List<Action>` via `ArrayList<>` | Preserves order and duplicates; fast `get(i)`. A `Set` would erase repeated history. |
| 2 | `LinkedHashSet<String>` | Deduplicates while preserving first-appearance order. `HashSet` does not guarantee ordering. |
| 3 | `HashMap<String, Product>` | Average `O(1)` key lookup; keys must maintain stable `equals/hashCode`. |
| 4 | `TreeSet<Instant>` or `TreeMap<Instant, List<Event>>` | Sorted with range-query APIs. If timestamps can collide, store multiple events per timestamp rather than overwriting. |
| 5 | `Deque<Action>` via `ArrayDeque<>` | `push/pop` provides LIFO; avoid defaulting to the legacy `Stack` class. |
| 6 | `BlockingQueue<Task>` via `ArrayBlockingQueue<>(1000)` | `put` waits when full, `take` waits when empty. Plan for shutdown, cancellation, and interrupt handling. |
| 7 | `PriorityQueue<Ticket>` | Comparator orders by priority descending, then sequence ascending. Do not use an iterator expecting sorted output. |
| 8 | `ConcurrentHashMap<Key, Long>` with `merge(key, 1L, Long::sum)` | Thread-safe per-key increment; a two-step `put(k, get(k) + 1)` causes race conditions. Under high contention, consider `LongAdder`. |
| 9 | `CopyOnWriteArrayList<Listener>` | Snapshot iterator suits read-heavy workloads with rare updates; frequent writes incur expensive array copies. |
| 10 | `EnumSet<Role>` | Compact, fast bit-vector representation restricted to enum constants; disallows `null`. |
| 11 | `List<Student>` sorted by score descending; or `TreeMap<Integer, List<Student>>` with reverse order | Retains all students sharing a score. `TreeMap<Integer, Student>` would overwrite colliding score keys. |
| 12 | Access-ordered `LinkedHashMap<K,V>` overriding `removeEldestEntry` | Recent accesses reorder entries; use in a single thread or wrap with proper synchronization. |

Standalone Java 17 example illustrating Scenario 12 (capacity capped at 2 for readability; change to 100 for the actual prompt):

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class LruExample {
    public static void main(String[] args) {
        Map<String, Integer> cache = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Integer> eldest) {
                return size() > 2;
            }
        };
        cache.put("A", 1);
        cache.put("B", 2);
        cache.get("A");
        cache.put("C", 3);
        System.out.println(cache);
    }
}
~~~

Running `javac -encoding UTF-8 LruExample.java` followed by `java LruExample` outputs `{A=1, C=3}`. `"B"` is evicted because `"A"` was accessed more recently. Because an access-ordered `LinkedHashMap` mutates internal ordering even during `get`, never share it across threads without external synchronization.

## 8. Scoring Rubric and Self-Grading Sheet

Each scenario is worth **up to 2 points**, for a total of **24**:

- **1 point for the right selection:** The class/interface satisfies all stated requirements. Alternative solutions are accepted if backed by sound reasoning; choosing a structure that drops required duplicates, loses ordering, loses updates, or violates concurrency requirements scores 0 for this part.
- **1 point for the explanation:** Clearly state one core property *and* one risk/precondition (e.g., hash contract, comparator behavior, capacity, atomicity, snapshot cost, ordering). Naming only the class does not earn the explanation point.

| Total /24 | Mastery Level | Next Practice Step |
|---|---|---|
| 21–24 | Solid decisions and rationale | Experiment with large datasets and multithreading; benchmark real workloads |
| 17–20 | Mostly accurate | Re-explain the risks and edge cases for missed scenarios |
| 12–16 | Familiar with collection families but confuses contracts | Review ordering vs. sorting, and `Set`/`Map`/`Queue` contracts |
| 0–11 | Not yet selecting by requirements | Re-apply the six questions in Section 1 before every scenario |

**Self-Assessment Worksheet to Fill Out:**

| Scenario | Chosen Class | Decisive Property | Risk / Assumption | Score /2 |
|---|---|---|---|---|
| 1, 2, 3, 4 | Record each separately | Duplicates / order / key / range | Equality, comparator | ... |
| 5, 6, 7, 8 | Record each separately | LIFO / bounded blocking / priority / concurrent | `null`, queue shutdown, tie-break, atomicity | ... |
| 9, 10, 11, 12 | Record each separately | Snapshot / enum / duplicate scores / LRU | Write cost, colliding keys, synchronization | ... |

When you miss a scenario, rewrite your reasoning using the template: "I need ___ because of requirement ___; I did not choose ___ because it would violate ___." Then **change one constraint** in the prompt: what if the list needs sorted order instead of insertion order? What if multiple threads are introduced—how does the structure or synchronization change? What if the consumer is slow—should the queue be bounded? This tests whether you understand the underlying mechanisms rather than memorizing answer keys.

## 9. Common Pitfalls in Practice

1. **Confusing insertion order with sorted order:** `LinkedHashSet` preserves insertion order, `TreeSet` sorts by comparator, and `PriorityQueue` only orders head removal by priority.
2. **Using `HashSet`/`HashMap` and relying on an iteration order that "looks stable":** The API makes no such guarantee.
3. **Putting mutable keys into a hash collection and modifying fields used in `hashCode`:** Subsequent `get/contains` lookups can fail.
4. **Using a comparator that compares only one attribute when distinct objects must coexist:** `TreeSet` may drop elements; `TreeMap` may overwrite values.
5. **Seeing `map.get(key) == null` and concluding the key is absent:** In `HashMap`, the key may exist with a `null` value; use `containsKey` when you need to distinguish the two cases.
6. **Assuming `Collections.synchronizedList` makes compound action sequences atomic:** Check-then-act (`contains` followed by `add`) or iteration still requires external synchronization across the entire block.
7. **Using `HashMap` for concurrent counter increments because single-threaded tests pass:** Read–modify–write is not atomic; use appropriate atomic update APIs.
8. **Using `CopyOnWriteArrayList` for write-heavy workloads:** Every write copies the entire array, which quickly becomes expensive.
9. **Treating `PriorityQueue` as a sorted list that can be iterated directly:** Its iterator makes no ordering guarantee; poll from a copy or sort a list instead.
10. **Confusing unmodifiable with deeply immutable:** You cannot add or remove elements via `List.copyOf`, but mutable objects stored inside the list can still be mutated.

## 10. Final Checklist for Every Decision

- [ ] Have you identified whether duplicates, key lookup, index access, insertion order, sorting, FIFO/LIFO, or priority are required?
- [ ] Have you stated the dominant access operation and the Big-O complexity of **that specific operation**, not just the class in general?
- [ ] Have you checked `equals/hashCode`, `Comparator` consistency, `null` rules, mutable keys, and duplicate values?
- [ ] Have you distinguished among thread-safety, compound atomic operations, and queues with backpressure?
- [ ] Have you evaluated write amplification, memory footprint, and snapshot iteration requirements?
- [ ] Have you declared variables using the appropriate interface (`List`/`Set`/`Map`/`Queue`/`Deque`) where possible and verified behavior with a small test example?

A sound decision always links **requirement → data structure → rationale → limitation**. The decision table and self-grading rubric help you justify your choice—even when changing requirements later force you to switch implementations.