# remove(Object), contains, and the Cost of Searching for Elements

## 1. Fast priority-head selection does not mean fast lookup for every element

A `PriorityQueue` can quickly tell you which task is at the head by priority. However, if the question is "is task beta still in the queue?" or "remove the exact task beta", that is a different kind of operation.

A priority heap is organized to serve head selection. It is not a lookup table by every attribute of a task, nor is it a search tree that can branch left or right according to an arbitrary key.

Therefore, it is necessary to separate:

- `peek()`: inspect the priority head.
- `poll()` or no-argument `remove()`: retrieve and remove the priority head.
- `contains(Object)`: check whether there is an element equal to the queried value.
- `remove(Object)`: find and remove an element equal to the queried value.

In the standard `PriorityQueue`, `contains` and the argument-taking `remove` have a linear search cost in the number of members. If used frequently, this search work can take up more effort than maintaining the heap itself.

This lesson explains identification via `equals`, duplicates, easily confused signatures, and how to evaluate cost using an operation-counting check. The complete program uses APIs available in Java 17.

You need to know variables, objects, methods, and loops. The relationships between `equals`, `Comparator`, and the heap will be introduced to the exact extent needed.

## 2. Three different questions about an element

Consider tasks with two attributes:

~~~text
id       : identifier name in the example
priority : priority number; smaller numbers are selected first
~~~

The program uses `record Task(String id, int priority)`. With this record, default equality considers all components, not just `id`.

When given two `Task` instances, distinguish:

| Question | Mechanism |
| --- | --- |
| Do two variables point to the exact same object? | `==` |
| Are two `Task` values equal? | `equals` |
| Do two `Task` instances have the same rank under the priority rule? | `Comparator.compare(a, b) == 0` |

If the `Comparator` only reads `priority`, `Task("alpha", 2)` and `Task("beta", 2)` yield a comparison result of 0, yet they are not equal according to `equals`. They are at the same priority level, not the same `Task` value.

Conversely, `new Task("beta", 2)` is a new object, yet it is equal to an already stored `Task` `beta/2`. `contains` can find it even though the two references differ.

Do not infer "same priority level" as "the exact task being searched for". Nor is it required to hold onto the original reference in order to find or remove by value, provided the type's `equals` expresses the appropriate relation.

## 3. contains uses equals, not priority groups

The contract of `PriorityQueue.contains(o)` checks whether there is a member `e` for which `o.equals(e)` is true. It does not ask whether there is any element that the `Comparator` compares as 0 with `o`.

For example, if the queue contains `beta/2`:

~~~text
contains(new Task("beta", 2))   → true
contains(new Task("unknown", 2)) → false
~~~

The probe `unknown/2` has the same priority 2, but a different `id`, so `equals` differs. A `Comparator` that only inspects `priority` does not make that probe equal to `beta`.

`contains` is read-only. It does not remove members, does not move the found element to the head, and does not refresh priorities.

The `equals` rule belongs to the element type. If a class does not override `equals` and uses default object identity behavior, a new object with fields that look identical is not guaranteed to be found. If a type defines `equals` by key, the search follows that relation.

With the `Task` record in this lesson, querying with the same `id` but a different `priority` is also not querying the same value, because both components participate in `equals`. If real business logic identifies tasks solely by `id`, an appropriate key model or equality relation is needed; it must not be assumed from the field name `id`. [Java 17: PriorityQueue.contains](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#contains(java.lang.Object)).

## 4. remove(Object) removes one equal element, not necessarily the head

The argument-taking `remove(o)` searches for a member equal to `o` according to `equals`. If found, it removes one occurrence and returns `true`. If not found, it returns `false`.

For example, suppose the queue contains:

~~~text
first/1
alpha/2
beta/2
later/9
~~~

Calling `remove(new Task("beta", 2))` does not mean "drop the highest-priority task". It searches for `beta/2` and removes that value; `first/1` can still remain at the head.

Another probe with the same priority level that is not equal is not used to arbitrarily remove an element from that group:

~~~text
remove(new Task("unknown", 2)) → false
~~~

This call does not pick `alpha/2` or `beta/2` to remove as a substitute.

If there are multiple equal elements, `remove(Object)` removes only one occurrence. `PriorityQueue` allows duplicates, including inserting the same object multiple times. There is no automatic deduplication upon insertion.

Do not rely on `remove(Object)` to pick "the earliest-arriving equal copy" or "this exact reference" when multiple equal representatives exist. The contract describes removing an element matching `equals`, without providing a historical selection policy among those copies. [Java 17: PriorityQueue.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#remove(java.lang.Object)).

## 5. remove() and remove(Object) have different purposes, results, and costs

| Signature | How is the element chosen? | Result | When no matching object exists |
| --- | --- | --- | --- |
| `remove()` | Selects head by priority | The removed element | Throws `NoSuchElementException` when empty |
| `poll()` | Selects head by priority | The removed element | Returns `null` when empty |
| `remove(Object o)` | Searches by `equals` with `o` | `boolean` | Returns `false` if not found |
| `contains(Object o)` | Searches by `equals` with `o` | `boolean` | Returns `false` if not found |

A common point of confusion with integers:

~~~java
PriorityQueue<Integer> numbers =
        new PriorityQueue<>(List.of(5, 1, 3, 2, 4));

boolean removed = numbers.remove(3);
~~~

This is an illustrative snippet using the corresponding `java.util` types. `PriorityQueue` has no index-based `remove` operation. The `int` value `3` is boxed to be passed into the method taking `Object`, and the code removes an element with value `3`.

It does not remove the element at index 3 of a list. The result is a `boolean`, not an element retrieved from an index.

Afterward, no-argument `numbers.remove()` has a different meaning: retrieving the current smallest head. Always read both the parentheses and the arguments when evaluating behavior or complexity.

## 6. Why doesn't a heap provide O(log n) arbitrary search?

A min-heap only requires that each parent node not come after its children according to the priority rule. It does not have the rule "all values on the left are smaller, all values on the right are larger" like a key-ordered search tree.

Illustrative model:

~~~text
        1
      /   \
     4     2
    / \   /
   8   7 3
~~~

Both branches can contain elements matching a search by value. Comparing a search key against a node does not provide the same branching rule as a search tree.

Moreover, `contains` must obey `equals`, whereas the heap is organized by `Comparator` or `compareTo`. The two relations do not necessarily treat the same group of objects as equivalent.

Therefore, `PriorityQueue` does not use a binary search across its entire backing array to implement `contains`. The sequence observed via `iterator` or `toArray` is also not guaranteed to be sorted, so it cannot be fed directly into a binary search algorithm and assumed correct.

Organizing for head selection and organizing for lookup by identity are two separate data requirements. A structure optimized for the first requirement does not automatically provide an index for the second.

## 7. Search-then-remove has two cost components

In OpenJDK 17, `contains` and `remove(Object)` share an index-finding step that checks `equals` against members. If not found, it stops; if found for removal, it proceeds to a heap-repair step. [PriorityQueue source code, OpenJDK 17](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/PriorityQueue.java).

This can be read as a diagram:

~~~text
contains(o)
  → search for a member equal to o
  → return true / false

remove(o)
  → search for a member equal to o
  → if absent: return false
  → if present: remove at the found position, restore heap, return true
~~~

Searching by value may have to examine all `n` members. Once the position to remove is known, the last element is used to fill the gap and the heap relation is restored in the necessary direction.

Example model before removing 2:

~~~text
        1
      /   \
     2     3
    / \   / \
   4   5 6   7
~~~

Putting 7 into 2's spot is not enough: 7 now sits above children 4 and 5, violating the heap relation. Positions must be repaired so a valid heap is maintained again. This is an explanation of the mechanism, not an assertion that the internal layout of every queue must match this diagram.

Not every removal re-sorts an entire list. The heap-repair step is distinct from the member-search step, and it is the search step that gives `remove(Object)` a linear worst-case cost.

## 8. Reading the complexity table accurately

With `n` as the current number of members, the cost description of `PriorityQueue` is:

| Operation | Cost per class specification |
| --- | --- |
| `peek` / `element` / `size` | O(1) |
| `offer` / `add` | O(log n) |
| `poll` / `remove()` | O(log n) |
| `contains(Object)` | O(n) |
| `remove(Object)` | O(n) |

The O(n) rows do not mean every call must always scan all `n` elements. If found immediately, the search can finish early. If the element is absent or lies late in the search range, the number of checks can grow up to `n`.

For `remove(Object)`, knowing the position right at the start still leaves the heap-repair step. Counting only a single `equals` call at the beginning does not prove the entire removal takes constant time.

In the search step of the referenced implementation, `n` is `size`, not the entire allocated array capacity. Spare slots holding no members do not need to be checked.

The notations above are usually separated from the internal complexity of `equals` and `Comparator`. If each `equals` compares many long fields, the actual cost of the search step includes that work. With cost `C_eq` per `equals` call and `C_cmp` per priority comparison, you can picture search/removal as bounded by `n·C_eq` plus heap repair on the order of `log(n)·C_cmp`.

This is an analysis of work count, not a guarantee of a fixed number of milliseconds on every machine. [Java 17: PriorityQueue, operation cost notes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 9. Complete program using Java 17

Save as `PriorityQueueSearchDemo.java`. The program has three verification groups:

1. `Task` instances with the same priority but different `equals`, and two occurrences of `beta`.
2. Argument-taking `remove` on `PriorityQueue<Integer>`, not removal by index.
3. A `Key` type that counts `equals` calls to observe the search.

`Key` defines `equals`/`hashCode` by `id`. The static counter is solely for a single-threaded test; equality results are still decided by `id`. The program does not use the counter as part of its identification rule.

The `id` lists are sorted to compare contents. They are not presented as `iterator` order or removal order when `Task` instances share the same priority.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueSearchDemo {
    record Task(String id, int priority) {}

    static final class Key {
        static int equalityCalls;
        final int id;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            equalityCalls++;
            return other instanceof Key key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static List<String> sortedIds(PriorityQueue<Task> queue) {
        return queue.stream().map(Task::id).sorted().toList();
    }

    static long countEqual(PriorityQueue<Task> queue, Task probe) {
        return queue.stream().filter(probe::equals).count();
    }

    static List<Integer> drainPriorities(PriorityQueue<Task> queue) {
        List<Integer> result = new ArrayList<>();
        Task task;
        while ((task = queue.poll()) != null) {
            result.add(task.priority());
        }
        return result;
    }

    public static void main(String[] args) {
        Comparator<Task> byPriority = Comparator.comparingInt(Task::priority);
        PriorityQueue<Task> tasks = new PriorityQueue<>(byPriority);
        Task beta = new Task("beta", 2);
        tasks.addAll(List.of(
                new Task("alpha", 2),
                beta,
                new Task("later", 9),
                new Task("first", 1),
                beta));
        System.out.println("initial ids=" + sortedIds(tasks));
        System.out.println("initial size=" + tasks.size());
        System.out.println("head priority=" + tasks.peek().priority());

        Task equalProbe = new Task("beta", 2);
        Task samePriority = new Task("unknown", 2);
        System.out.println("equal probe is same reference=" + (equalProbe == beta));
        System.out.println("equal probe equals beta=" + equalProbe.equals(beta));
        System.out.println("contains equal probe=" + tasks.contains(equalProbe));
        System.out.println("same-priority comparison=" + byPriority.compare(samePriority, beta));
        System.out.println("same-priority equals=" + samePriority.equals(beta));
        System.out.println("contains same-priority probe=" + tasks.contains(samePriority));
        System.out.println("remove same-priority probe=" + tasks.remove(samePriority));
        System.out.println("size after missing removal=" + tasks.size());

        System.out.println("beta count before=" + countEqual(tasks, equalProbe));
        System.out.println("remove one beta=" + tasks.remove(equalProbe));
        System.out.println("beta count after one=" + countEqual(tasks, equalProbe));
        System.out.println("size after one=" + tasks.size());
        System.out.println("head priority after one=" + tasks.peek().priority());
        System.out.println("ids after one=" + sortedIds(tasks));
        System.out.println("still contains beta=" + tasks.contains(equalProbe));
        System.out.println("remove second beta=" + tasks.remove(equalProbe));
        System.out.println("remove beta again=" + tasks.remove(equalProbe));
        System.out.println("ids after both=" + sortedIds(tasks));
        System.out.println("remaining priorities poll=" + drainPriorities(tasks));
        System.out.println("contains null=" + tasks.contains(null));
        System.out.println("remove null=" + tasks.remove(null));

        PriorityQueue<Integer> numbers =
                new PriorityQueue<>(List.of(5, 1, 3, 2, 4));
        boolean removedByValue = numbers.remove(3);
        System.out.println("integer remove(3)=" + removedByValue);
        List<Integer> snapshot = new ArrayList<>(numbers);
        snapshot.sort(Comparator.naturalOrder());
        System.out.println("numbers after value removal=" + snapshot);
        System.out.println("contains text 4=" + numbers.contains("4"));
        System.out.println("remove text 4=" + numbers.remove("4"));
        System.out.println("remove() head=" + numbers.remove());
        System.out.println("poll head=" + numbers.poll());

        for (int n : new int[] {8, 16, 32}) {
            PriorityQueue<Key> counted =
                    new PriorityQueue<>(Comparator.comparingInt(key -> key.id));
            for (int id = 0; id < n; id++) {
                counted.offer(new Key(id));
            }

            Key.equalityCalls = 0;
            boolean found = counted.contains(new Key(-1));
            System.out.println("n=" + n + " contains missing=" + found
                    + " equals calls=" + Key.equalityCalls);

            Key.equalityCalls = 0;
            boolean removedMissing = counted.remove(new Key(-1));
            System.out.println("n=" + n + " remove missing=" + removedMissing
                    + " equals calls=" + Key.equalityCalls);

            Key.equalityCalls = 0;
            boolean removedMinimum = counted.remove(new Key(0));
            System.out.println("n=" + n + " remove minimum by value=" + removedMinimum
                    + " equals calls=" + Key.equalityCalls);
            System.out.println("n=" + n + " next minimum=" + counted.peek().id);
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 PriorityQueueSearchDemo.java
java PriorityQueueSearchDemo
~~~

Use JDK 17 or later. `--release 17` checks code and APIs against Java 17; the filename matches the `public` class.

Expected output:

~~~text
initial ids=[alpha, beta, beta, first, later]
initial size=5
head priority=1
equal probe is same reference=false
equal probe equals beta=true
contains equal probe=true
same-priority comparison=0
same-priority equals=false
contains same-priority probe=false
remove same-priority probe=false
size after missing removal=5
beta count before=2
remove one beta=true
beta count after one=1
size after one=4
head priority after one=1
ids after one=[alpha, beta, first, later]
still contains beta=true
remove second beta=true
remove beta again=false
ids after both=[alpha, first, later]
remaining priorities poll=[1, 2, 9]
contains null=false
remove null=false
integer remove(3)=true
numbers after value removal=[1, 2, 4, 5]
contains text 4=false
remove text 4=false
remove() head=1
poll head=2
n=8 contains missing=false equals calls=8
n=8 remove missing=false equals calls=8
n=8 remove minimum by value=true equals calls=1
n=8 next minimum=1
n=16 contains missing=false equals calls=16
n=16 remove missing=false equals calls=16
n=16 remove minimum by value=true equals calls=1
n=16 next minimum=1
n=32 contains missing=false equals calls=32
n=32 remove missing=false equals calls=32
n=32 remove minimum by value=true equals calls=1
n=32 next minimum=1
~~~

## 10. Reading search and identification results

### 10.1. Different reference but equal value is still found

`equal probe is same reference=false` shows that `equalProbe` is not the exact original `beta` object.

`equal probe equals beta=true` and `contains equal probe=true` show that `equals` is sufficient to find a member. There is no need to keep the exact reference that was inserted into the queue if the type already has an appropriate equality relation.

### 10.2. Same priority level is not the same element

`same-priority comparison=0` yet `same-priority equals=false`. Both `contains` and `remove` with the probe `unknown/2` return `false`.

`size after missing removal=5` confirms that no member was removed as a substitute from the priority 2 group. Removal by value does not randomly pick an element with the same priority level as the probe.

### 10.3. contains is not a retrieval operation

The head has priority 1 before the search calls. Reading `contains` or failing to remove a probe does not move `beta` to the head and does not extract `first/1`.

When you need to process the next priority element, use `poll` or no-argument `remove`. Using `contains` to check for a value does not replace head retrieval.

## 11. Removing one occurrence and restoring the heap

Initially `beta` appears twice. The program checks:

~~~text
beta count before=2
remove one beta=true
beta count after one=1
size after one=4
~~~

This result is not `remove` "failing to remove enough" due to an implementation bug. The contract only requires removing one matching occurrence.

`still contains beta=true` after the first removal is expected because one `beta` remains. The second removal returns `true`; only the third returns `false`.

The head with priority 1 still remains after removing `beta/2`. This helps distinguish removing a specific object from taking the head.

Finally, `remaining priorities poll=[1, 2, 9]` shows that the remaining elements are still retrieved by priority. `alpha/2` remains even though `beta/2` at the same level was removed. This check confirms membership semantics and priority ordering after removal in the example.

If you need to remove **all** elements equal to a value, you must choose a separate contract, such as a conditional removal operation. Looping `remove` can be functionally correct, but each call may have to search again; when the number of removals is large, the repeated cost is no longer just a single O(n).

Do not rely on equal copies being stored together or retrieved in arrival order. `PriorityQueue` provides no such guarantees.

## 12. contains and remove with null or a different probe type

`PriorityQueue` forbids adding `null` members. In the example, both `contains(null)` and `remove(null)` return `false`. Saying "storing null is not allowed" does not mean every method taking a `null` argument must throw an exception like `offer(null)`.

The search/remove signatures take `Object`, so you can also write:

~~~java
numbers.contains("4");
numbers.remove("4");
~~~

on a `PriorityQueue<Integer>`. Both calls in the program return `false` because the string `"4"` is not equal to `Integer` `4` under those types' `equals`.

They do not attempt to insert the string into the queue, nor do they use the natural `Comparator` to turn the string into a number. Therefore, you should not project the comparison policy of inserting a wrong type onto every query method that accepts `Object`.

This does not excuse omitting a proper `equals` definition. A type with an unusual, asymmetric, or contract-violating `equals` that throws unexpected exceptions can make value-based search behavior confusing. Keep equality rules valid and consistent.

With `Task`, the default record inspects both `id` and `priority`. If you need to cancel by `id` without knowing the stored `priority`, a constructed `Task` with the right `id` but a guessed `priority` will not automatically match `equals`. An explicit identification scheme or index by `id` is needed.

## 13. Counting operations to understand cost, rather than relying on a single runtime measurement

The program creates `Key` queues of 8, 16, and then 32 elements. Each `Key` has an `id`, and the `Comparator` orders by `id`. After populating the data, the `equals` counter is reset to 0 before each test.

The probe `id` -1 does not exist. Results:

~~~text
n=8  : missing contains → 8 equals calls
n=16 : missing contains → 16 equals calls
n=32 : missing contains → 32 equals calls
~~~

`remove` with the same missing probe yields the corresponding counts. It needs to confirm no member equals the probe before returning `false`.

This is an observation of the running implementation, consistent with the scan step referenced in OpenJDK 17. The exact `equals` count is not an API contract that applications should force every version to preserve; the important conclusion for choosing a data structure is the linear search cost documented for the class.

The test does not need a stopwatch to show that the number of checks grows with the number of members. Timing small sizes is easily affected by many factors outside the search itself.

### Why does removing the minimum element count only one equals?

With probe `id` 0, the matching element sits at the start of the search range in the example. `equals` matches immediately, so the counter is 1.

However, after removal, the queue still needs to repair the heap so the new head is `id` 1. The counter does not count `Comparator` calls or reference moves.

Therefore:

~~~text
equals calls=1
~~~

does not prove that `remove(Object)` as a whole is O(1). It only describes the portion of work that the instrumentation in the example actually counts.

By the same principle, you cannot measure a few `equals` calls and conclude that all operations on `PriorityQueue` are as fast as peeking at the head.

## 14. Avoiding searching twice when you only need the removal result

The conceptual snippet:

~~~java
if (queue.contains(probe)) {
    queue.remove(probe);
}
~~~

checks and then removes using two independent search operations. It can repeat work in the case where the element exists.

If the goal is "try to remove and know whether it succeeded", the `boolean` returned by `remove` already answers that:

~~~java
boolean removed = queue.remove(probe);
~~~

These are illustrative snippets using the declared `queue` and probe. You do not need `contains` beforehand to be allowed to call `remove`; if not found, `remove` returns `false`.

Calling `contains` beforehand also does not reserve the member for the subsequent `remove`. If other operations intervene, the state between the two calls can change. `PriorityQueue` is not inherently synchronized for arbitrary concurrent modification by multiple threads.

This does not mean a single `remove` solves all concurrency issues. It simply avoids a redundant search when the requirement can be expressed directly by the result of the removal operation.

If you only want to know whether an element is present without modifying the data at all, `contains` remains the functionally right operation. The point is to choose the right intent and understand the cost.

## 15. When queries by identity occur frequently

If an application mainly inserts and then retrieves the head by priority, `PriorityQueue` can serve it directly. If each task is frequently searched or canceled by `id`, those O(n) scans can become a cost center requiring a redesign.

A secondary index by key can help answer presence queries by that key. However, adding a `HashSet` does not automatically make `PriorityQueue`'s `remove(Object)` find the position faster; the queue is still not given an element address from the `HashSet`.

Duplicates must also be considered. If the same value appears twice, removing it once does not make it absent. A simple set of keys can become out of sync if you remove the key immediately after the first `poll` or `remove`. A reference-counting model per key may be more appropriate if duplicates are allowed, with consistent update rules across all add/poll/remove paths.

For cancellation, a design can mark items as invalidated and skip them when they reach the head. That is a logical deletion, not an immediate physical removal from the `PriorityQueue`. You need to understand the impact on retained data size and how to distinguish re-insertions of the same `id`.

If fast arbitrary removal by an address or positional index is required, choose a structure capable of it or build a properly maintained index model. Do not access `PriorityQueue`'s private array to treat an internal index as stable; heap repairs can move elements around.

These choices are data-model changes, not renaming a `contains` call to `remove`. Before adding auxiliary structures, clearly define the key, duplicates, update paths, and actual query frequency.

## 16. Presence does not prove priority order is still valid

A `Task` can be found by `equals` without proving that every priority relationship in the queue matches the intended state.

For example, if you use objects with a mutable `priority` field and mutate it directly while the object is still in the heap, `contains` may still find it by `equals` or identity. However, `PriorityQueue` does not automatically receive a heap-repair event just because an element's internal field changed.

Two concerns must be separated:

- The identification rule decides which probe equals an element.
- The priority rule decides which element must rise to the head.

In this lesson, `Task` is a record whose components are established at creation. There is no reassignment of `priority` while stored, so the test focuses on search/removal semantics.

If you need to change priority, design an explicit update procedure for the specific data item. If the same object or value is inserted multiple times, also understand the impact on all those occurrences.

Do not use `contains=true` as a sufficient check for the correctness of the structure or processing algorithm. It only answers presence according to the method's contract.

## 17. Common misconceptions

| Misconception | What to check |
| --- | --- |
| "It's a heap, so every search is O(log n)" | A heap serves head selection; `PriorityQueue`'s `contains`/`remove(Object)` are linear |
| "Same priority means `contains` is true" | `contains` uses `equals`, not just `Comparator` |
| "Must have the same reference to remove" | A probe with a different reference still matches if `equals` holds |
| "A record has an `id` field, so it defaults to checking only `id`" | The lesson's `Task` record checks both `id` and `priority` |
| "`remove(Object)` removes all duplicates" | Each call removes only one matching member |
| "`remove(Object)` always removes the head" | That is no-argument `remove()`; the argument form searches by value |
| "`PriorityQueue<Integer>.remove(3)` is index 3" | `PriorityQueue` has no index-based `remove` |
| "One `equals` call means the entire removal is O(1)" | Heap repair and work not measured by that counter still remain |
| "`contains` beforehand helps `remove` find faster" | No found position is passed across the two calls |
| "The `toArray` sequence is sorted, so binary search works immediately" | The array is not guaranteed to be in full priority order |
| "`null` is forbidden, so `contains(null)` must also throw" | Storage policy and search parameter behavior are different |
| "Adding a `HashSet` makes heap removal O(1)" | Having a presence index does not automatically provide a heap position index |
| "A key set is enough for every case with duplicates" | You must maintain counts or an appropriate uniqueness model |
| "`contains` true means the heap is definitely updated after mutating priority" | Presence and priority structure are two separate properties |

Quick questions when reviewing code are: which signature is called, does it use `equals` or `Comparator`, does it remove once or all occurrences, and is there unnecessary repeated searching?

## 18. Practice with solutions

### Exercise 1: same priority but different value

A queue contains `Task("A", 5)`. The `Comparator` only inspects `priority`. Is `contains(Task("B", 5))` `true` because both priorities equal 5?

**Solution:** No, under the lesson's `Task` record. The two `id`s differ so `equals` differs, even though `Comparator` returns 0. `contains` does not use priority groups as the definition of the same element.

### Exercise 2: new probe value

A queue contains a `Task("A", 5)`. You create a new object with the same two components. Does `contains` necessarily return `false` due to a different reference?

**Solution:** No. A record has `equals` based on its components, so the new probe still equals the stored value and can be found.

### Exercise 3: duplicates

A `Task` equal to `x` has three occurrences. `remove(x)` succeeds once. Must `contains(x)` be `false`?

**Solution:** No. Two occurrences still remain. `remove(Object)` is not a remove-all operation.

### Exercise 4: taking the head vs. targeted removal

A queue has priorities 1, 2, 9. `remove(Object)` removes the task with priority 9. Must the head with priority 1 also be removed?

**Solution:** No. The argument-taking form searches for the exact value to remove. `poll` or no-argument `remove` is what takes the head by priority.

### Exercise 5: integers and indices

`PriorityQueue<Integer>` contains 1, 2, 3, 4. What does calling `remove(3)` mean?

**Solution:** Removes one `Integer` value `3` if present and returns a `boolean`. `PriorityQueue` does not provide removal at index 3.

### Exercise 6: missing element

A `PriorityQueue` has 10,000 members and the probe does not exist. Can you assume `contains` only needs around `log2(10,000)` checks because this is a heap?

**Solution:** No. In the documented standard implementation, `contains` searches linearly; a missing probe may require checking all members.

### Exercise 7: equals counter

Removing a value at the head counts only one `equals`. Why shouldn't you conclude `remove(Object)` is O(1)?

**Solution:** The counter only measures `equals` in the search step. After removal, comparisons and moves may still be needed to repair the heap. The head case also does not represent all positions or missing probes.

### Exercise 8: searching twice

Code calls `contains(x)`, and if `true`, calls `remove(x)`. If you only need to know whether it was removed, is there a more direct way to express it?

**Solution:** Use the `boolean` returned by `remove(x)` itself. If not found, it returns `false`; if found and removed, it returns `true`. This avoids a prior search step that does not pass the position to `remove`.

### Exercise 9: identification by id

`Task` is a record consisting of `id` and `priority`. You only know the `id` of the task to cancel and pick a different `priority` to create a probe. Is the probe guaranteed to match?

**Solution:** No. A record's default `equals` checks both components. Operating by `id` requires a key model, equality relation, or index suited to the requirement.

### Exercise 10: secondary index and duplicates

You add a `HashSet` of keys alongside a `PriorityQueue`. A key appears twice in the queue. After polling once, is it right to immediately remove the key from the `HashSet`?

**Solution:** No, if another occurrence remains. You need a rule maintaining uniqueness or occurrence counts. The secondary index must accurately reflect all update paths.

### Exercise 11: different probe type

`PriorityQueue<Integer>` contains the number 4. In the example, is `contains("4")` `true` because the string has the same digit character?

**Solution:** No. The string `"4"` and `Integer` `4` are not equal under `equals`. A query taking `Object` does not automatically parse the string into a number or insert the string into the queue.

### Exercise 12: found after mutating the object

A stored object has its `priority` mutated directly, yet `contains` is still `true`. Does that prove `peek` is now selecting correctly according to the new `priority`?

**Solution:** No. `contains` only checks presence via `equals`. Whether the heap is properly organized according to current priority values is a separate issue.

## 19. Applying this in real code

Use `contains` when the question is genuinely presence by `equals` and the scan cost is acceptable. Use `remove(Object)` when you need to attempt removing a specific value, read its `boolean` result, and remember it only removes one equal element per call.

When the task is to take the priority head, use `poll` or no-argument `remove` instead of searching again for an object already known to be at the head. When queries by `id` repeat frequently, evaluate a dedicated index model rather than assuming the heap already provides one.

Complexity must be paired with the exact signature: searching for an arbitrary value, knowing the position to repair the heap, and simply inspecting the head are three different kinds of work.
