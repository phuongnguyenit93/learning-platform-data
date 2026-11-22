# LinkedHashMap: Interaction Between Access-Order, Iterators, and Structural Modification

A loop that appears to be read-only can still modify a `LinkedHashMap` if the map was created in access-order mode (`access-order`). The reason is that while the application is reading a value, the map simultaneously records that access in its iteration order.

Imagine a cache with three keys `A, B, C`, ordered from least recently accessed to most recently accessed. When reading `A`, the application wants to retrieve A's value; the ordering structure also needs to move A to the end. If an iterator is currently traversing the old chain, these two operations can conflict even though the number of mappings does not change and the program is single-threaded.

This lesson helps you recognize structural modifications, interpret fail-fast behavior accurately, choose appropriate traversal or update patterns, and avoid using exceptions as a correctness mechanism. Examples use Java 17+; details about `modCount` are presented separately as the mechanism of OpenJDK 17.

## 1. A Map Has Multiple Kinds of State

Do not view a map merely as a set of key-value pairs. With `LinkedHashMap`, you must distinguish at least three kinds of state:

| State | Example of change |
|---|---|
| Mapping membership | Adding D or removing B |
| Value of an existing mapping | Changing A's value from 1 to 10 |
| Iteration order | Moving A from the front to the end |

`size()` only counts the number of mappings. It does not indicate whether the order has just changed, nor whether one key was removed and another added to keep the count the same.

Therefore, reasoning that "the size before and after is the same, so the iterator is still valid" lacks information. A program that tracks structure must care about the history of operations while the iterator is active.

### 1.1. Two Ordering Modes

The constructor with a trailing boolean parameter selects how order is maintained:

~~~java
LinkedHashMap<String, Integer> insertion =
        new LinkedHashMap<>(16, 0.75f, false);

LinkedHashMap<String, Integer> access =
        new LinkedHashMap<>(16, 0.75f, true);
~~~

These are two illustrative declarations, not a standalone program.

In insertion-order mode, position reflects when a key was inserted; updating the value of an existing key does not change that position. In access-order mode, methods defined by the API as accesses can move a mapping toward the most-recent end.

Thus, the exact same call `put("A", 10)` on an existing key A does not necessarily have the same ordering effect in the two modes.

### 1.2. Timeline of a Single Read

With initial order `[A, B, C]`:

~~~text
T0: create iterator over chain A -> B -> C
T1: call get("A") on access-order map
T2: map order becomes B -> C -> A, size is still 3
T3: continue using the iterator created at T0
~~~

At T3, the iterator does not automatically turn into a new traversal starting at B. It was created under a previous state. The change at T1 must be treated as a modification during iteration, rather than as a completely independent read operation.

The `LinkedHashMap` API defines structural modification as adding or deleting mappings and, in access-order mode, affecting iteration order. View iterators are fail-fast when they detect an improper modification. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

## 2. "Access" Is an API Rule, Not a Business Name

A method whose name sounds like a read or a lightweight update can still count as an access under the class's rules.

### 2.1. Typical Cases

The following table considers a map with `accessOrder=true`; "may change order" means you must account for the possibility that the mapping is repositioned, not that every call always moves a node:

| Operation | What to consider while an iterator is active |
|---|---|
| get an existing key | Counts as an access; do not treat as structurally read-only |
| get a missing key | No corresponding mapping to move to the end |
| getOrDefault for an existing key | Not a way to bypass order updates |
| put a new key | Adds a mapping, structural modification |
| put an existing key | May change order even when only reassigning the value |
| putIfAbsent on a mapping with a non-null value | May record an access even without changing the value |
| successful replace | May record an access |
| conditional replace whose condition does not match | No successful value replacement under that rule |
| containsKey, containsValue | Does not create an access that updates recency |
| Reading via keySet, values, entrySet | Does not automatically create get-style accesses |

The `compute`, `computeIfAbsent`, `computeIfPresent`, and `merge` family of methods also fall under `LinkedHashMap`'s access rules; you must consider the outcome and conditions of each method. `putAll` processes mappings in the source's iteration order. Do not infer the effect solely from whether "the final value looks unchanged." [Access-order rules in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

This lesson uses typical cases with non-null values when illustrating the update methods. The compute methods also have specific rules regarding null, insertion, and removal; they should not be lumped into a single "read-then-assign" operation.

### 2.2. Reading Null Does Not Prove No Access Occurred

If a key is mapped to null, `get` returns null but has still found the mapping. "Returning null" and "key absent" are two different states.

The example in the complete program section sets B's value to null via `Map.Entry.setValue` to preserve the initial order, and then calls `get("B")`. The order becomes `[A, C, B]`. This example isolates the effect of the get from the effect of an earlier put.

`containsKey` lets you check for existence without recording an access like get. However, combining `containsKey` and `get` does not form an atomic operation when another thread is concurrently modifying the map.

### 2.3. Replacing With an Equal Value Still Requires Checking the Method

You cannot determine a loop's validity by saying "I wrote back the exact same old value." In access-order mode, a method call can carry the meaning of recording usage even when the value reference or content is equal.

A more reliable approach is to ask:

1. Can the method add or remove a mapping?
2. Can the method record an access and change order?
3. If you only want to modify the value of the mapping currently being iterated, is there an appropriate way to do so via the entry?

## 3. Structural Modification Does Not Mean Changing Size

### 3.1. Same Number of Mappings, Different Chain

Initially:

~~~text
A=1, B=2, C=3
order: A -> B -> C
size: 3
~~~

After `get("A")` in access-order mode:

~~~text
A=1, B=2, C=3
order: B -> C -> A
size: 3
~~~

No mapping was added, removed, or changed in value, yet the traversal path changed.

Another example is removing A and then adding D. The final count is still three, but that is two membership changes. The old iterator is not revalidated just because the final size returned to the original number.

### 3.2. Matching the Initial Order at the End Is Still Not Enough

Suppose you access A, B, and C in turn on a map whose initial order is A, B, C:

~~~text
initial:   [A, B, C]
get(A):    [B, C, A]
get(B):    [C, A, B]
get(C):    [A, B, C]
~~~

The final order matches the initial order, but in the meantime the chain was modified multiple times. An iterator created before those modifications does not automatically become valid again.

This is the difference between comparing two state snapshots and obeying the operational contract during a traversal. For an iterator, the history of modifications during the traversal matters.

### 3.3. Updating Values via Entry Is a Different Case

During an `entrySet` traversal of a `LinkedHashMap`, `entry.getValue()` reads the current value; `entry.setValue(newValue)` is the supported way to replace that mapping's value. It is not a get or put on the map, so it is not used to record access recency.

Illustrative example:

~~~java
for (Map.Entry<String, Integer> entry : cache.entrySet()) {
    entry.setValue(entry.getValue() + 1);
}
~~~

This snippet assumes non-null values and no concurrent modifications. It updates values in the current traversal order without actively moving each key to the end.

An entry obtained from a view is backed by the original map. You should not retain it for arbitrary use after the traversal ends or after the map has been modified. When you need independent data, copy the key and value into an appropriate form. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)

## 4. What Does an Iterator Track?

### 4.1. The OpenJDK 17 Model

One way to explain the mechanism is to place two counters side by side:

~~~text
map:      modCount
iterator: expectedModCount at creation time

if map changes structurally:
    modCount may be incremented

when iterator performs a checked step:
    if the two counters differ -> modification detected
~~~

This is an explanatory model of the OpenJDK 17 mechanism, not copied source code.

In this version, moving a node that is not already at the end to the end increments `modCount`. The iterator records the expected value; the `next` path checks for a mismatch. Removing through the iterator itself updates that iterator's expected value. `hasNext` only checks whether a next node remains. [OpenJDK 17: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)

From this, you can understand two commonly misunderstood phenomena:

- `get` may complete normally; the exception only appears on the next step of the iterator.
- `hasNext()` returning true does not prove the iterator is still usable after a structural modification.

Do not use knowledge of when checks occur to try to "work around" modifications. The mechanism explains the failure; the usage contract is the basis for writing code.

### 4.2. A Get at the End of the Chain May Not Change Links

OpenJDK 17 only performs repositioning when the accessed node is not already at the end. Accessing the last key or a non-existent key may therefore not cause the iterator to throw in an experiment.

That does not prove the pattern "iterating while calling get on the same map" is valid for all inputs. When the data size or order changes, another key may not be at the end. A single-element example also does not cover multi-element cases.

Your programming choice must hold up for valid inputs in general. If you only need the value of the entry currently being iterated, reading from the entry is clear and does not depend on an accidental position.

### 4.3. An Iterator Is Not a Copy

`keySet()`, `values()`, and `entrySet()` are views backed by the map, not separate copies of the data. Creating a variable `Set<String> keys = cache.keySet()` does not create a snapshot at that point in time.

Similarly, an iterator does not freeze the mapping chain so the application can freely modify the original map. If you want to traverse an independent structure, you must explicitly create an independent structure and understand its copying limits.

## 5. What Does Fail-Fast Mean and What Does It Not Guarantee?

### 5.1. ConcurrentModificationException Does Not Require Multiple Threads

The exception name easily leads learners to look for a second thread even when the bug is caused by the loop itself:

~~~java
for (String key : cache.keySet()) {
    Integer value = cache.get(key);
    System.out.println(key + "=" + value);
}
~~~

This is illustrative problematic code when `cache` maintains access order. The enhanced for-loop uses a hidden iterator. The loop body calls get on the same map and can alter the chain the iterator is traversing.

The program can run entirely on a single thread. "Modification during iteration" here means two operations overlapping the same iterator lifetime, not necessarily two processors executing simultaneously.

### 5.2. The Exception Is a Bug-Detection Signal

Fail-fast is a mechanism for detecting certain improper modifications. It is not a lock, a transaction, a snapshot, or a concurrent map contract.

Do not write algorithms like this:

~~~java
try {
    // Iterate while still modifying the map improperly.
} catch (ConcurrentModificationException exception) {
    // Assume all data has been processed safely.
}
~~~

The snippet above only illustrates an incorrect handling pattern; it is not a solution.

Part of the work may have already happened before the exception. Catching the error and retrying can repeat side effects, send data twice, or miss elements if the algorithm is not specifically designed for retries.

The absence of an exception also does not prove correctness. You must verify actual operations and data contracts, rather than using the silence of the detection mechanism as proof of safety. [Java 17: LinkedHashMap fail-fast policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

### 5.3. Do Not Try to "Repair" an Old Iterator

If you have already modified the map structure in a way that invalidates the traversal, do not call `iterator.remove` hoping it will resynchronize everything. Valid removal via an iterator requires the traversal itself to still follow the rules.

When an algorithm needs a separate modification phase, finish the old traversal, apply the changes, and create a new traversal if needed. Creating a new iterator should happen at a point where the algorithm has a clear state, not as a blind retry to dodge an error.

## 6. Choosing a Traversal Approach by Purpose

### 6.1. Reading Key-Value Pairs Only

Use the entry currently being iterated:

~~~java
for (Map.Entry<String, Integer> entry : cache.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

This avoids a key lookup and avoids having get record an access on the map. It does not rely on any assumption about which key is at the end.

If you only need keys, iterate `keySet`. If you only need values, iterate `values`. Using the right view avoids unnecessary work.

### 6.2. Modifying Values While Preserving Order

You can use `entry.setValue` inside an entrySet traversal as shown earlier. Decide clearly whether that matches the business semantics.

For example, a job adjusting prices of all items might not be considered a user accessing an item. Preserving access order makes sense. Conversely, if business logic requires that update to refresh recency, do not use setValue just to avoid an exception and accidentally change semantics. Split the operation into appropriate phases.

### 6.3. Removing During the Traversal Itself

When you need to remove certain mappings, use an explicit iterator and remove through that iterator itself:

~~~java
Iterator<Map.Entry<String, Integer>> iterator =
        cache.entrySet().iterator();

while (iterator.hasNext()) {
    Map.Entry<String, Integer> entry = iterator.next();
    if (entry.getValue() < 0) {
        iterator.remove();
    }
}
~~~

This illustrative snippet assumes non-null values and no other operations modifying the map. Do not call `cache.remove(entry.getKey())` instead of `iterator.remove()` during the same traversal.

The iterator's `remove` may only be called after `next` and at most once per next call. Calling it before next or calling it twice in a row is a state error, distinct from a structural-modification detection error. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html)

### 6.4. The Exception for One Iterator Does Not Carry Over to Another

Suppose there are two iterators on the same map. The first iterator removes an element using its own `remove`. The first traversal is allowed to continue under that rule; the second iterator is not automatically updated along with it.

Therefore, saying "I used iterator.remove so all iterators are safe" is wrong. The right to modify belongs to the specific traversal performing the operation, not as a blanket license for any other traversals.

## 7. What If You Really Need to Get or Put Each Key?

### 7.1. Iterating Over a Copy of the Key List

If you need get calls to refresh order, you can iterate over an independent list of keys:

~~~java
List<String> keys = new ArrayList<>(cache.keySet());
for (String key : keys) {
    Integer value = cache.get(key);
    process(key, value);
}
~~~

This snippet is an illustrative pattern; `process` represents an application-defined handler. The example assumes a single thread and no other modifications while building the list.

The for-loop's iterator belongs to the list, not to the map whose order is changing. That is why this pattern avoids a structural conflict between that loop itself and calling get on the map.

However, you must understand the consequences:

- The list is a snapshot of key references, not a snapshot of all values.
- Get reads the map's value at the time of the call.
- Get still actively refreshes the map's order.
- If other modifications occur, a key in the list may no longer be in the map.
- Building the list from a concurrently modified map still requires a synchronization policy.

The copy solves one specific boundary; it does not automatically solve all concurrency or consistency issues.

### 7.2. If You Want to Report Without Refreshing Order

Reading via entrySet may already suffice when the traversal is properly protected. If you want to run a long-running report outside the protected section, you can copy the mappings into a new `LinkedHashMap` and iterate over the copy.

The copy constructor from a map creates an insertion-order map containing the mappings in the order encountered in the source. The copy does not automatically become an access-order map just because the source uses that mode. In this scenario, it preserves the existing order for independent reading.

You must copy while the source is in a stable state; if multiple threads are involved, perform the copy step under the application's synchronization policy. Keys and values are still reused references; mutable objects inside them are not automatically deep-copied.

### 7.3. Copying an Entry List May Not Separate the Data

`new ArrayList<>(cache.entrySet())` creates a new list, but the elements may still be entries backed by the map. Do not treat it as an independent record just because a new List object was created.

When you need independent pairs, you can create an `AbstractMap.SimpleImmutableEntry` from each key and value. An independent pair record still does not deep-copy the key or value objects.

What you need to choose is the level of separation actually required: separating the traversal structure, separating the mapping pairs, or separating all mutable data. These three requirements are not the same.

## 8. Callbacks, forEach, and Streams Do Not Eliminate the Problem

Changing loop syntax does not change the underlying nature if the processing body still calls back into the map:

~~~java
cache.forEach((key, value) -> {
    cache.get(key);
});
~~~

This is an illustrative problematic pattern on an access-order map. `forEach` already supplies the value; calling get is unnecessary and can alter the order during the traversal itself.

An indirect call has the same effect. For example, a report-building helper receives the key and then calls a lookup service backed by the same map. The loop body looks short and "just logging," yet the call chain may still contain a get.

With streams, processing functions must obey the non-interference requirement of the pipeline contract. Switching from a for-loop to `stream().forEach(...)` does not grant permission to arbitrarily modify the source structure. In particular, `parallelStream` does not turn a LinkedHashMap into a concurrent map. [Java 17: Stream non-interference requirement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)

Callbacks for `compute` and `merge` should also not modify the same map during computation. On an access-order map, even a call that looks like a mere lookup must be scrutinized because it can modify order. Compute from the callback parameters already provided or from properly organized external data. [Java 17: Map.compute and Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 9. Synchronization Must Cover Access Order Too

### 9.1. Do Not Treat Get as a Structure-Preserving Operation

`LinkedHashMap` is not thread-safe. If your design involves multiple threads, you must include get calls that can change order in the set of operations that need protection.

For example, a design using a read-write lock that allows multiple gets on an access-order map to hold only a "read lock" may rest on a false assumption: those calls are not necessarily structurally read-only. Locking rules must be designed around the state actually being modified.

### 9.2. SynchronizedMap Does Not Lock an Entire Loop Automatically

For a map wrapped with `Collections.synchronizedMap`, the documentation requires synchronizing on the returned map itself when iterating over its views. All accesses must go through the same protection mechanism; avoid holding a reference to the underlying map and accessing it around the wrapper. [Java 17: Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Illustrative example, assuming imports and data population are performed in the program:

~~~java
Map<String, Integer> shared =
        Collections.synchronizedMap(
                new LinkedHashMap<String, Integer>(16, 0.75f, true));

synchronized (shared) {
    for (Map.Entry<String, Integer> entry : shared.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
~~~

The lock is `shared`, not the `shared.entrySet()` object. The traversal reads values directly from the entry.

### 9.3. Holding a Lock Still Allows You to Invalidate Your Own Iterator

A lock prevents concurrent accesses that obey the same lock. It does not turn changing order inside the loop body into a valid operation for the old iterator.

If inside a synchronized block you still call `shared.get(key)` while iterating over that same access-order map, the same thread can still alter the chain. Therefore, you must address two separate issues:

1. How threads access the data.
2. How a single traversal's algorithm modifies the very data it is traversing.

A measure that solves the first issue does not automatically prove the second issue has been solved.

## 10. Complete Java Program

Save all the following code into `AccessOrderIteratorDemo.java`. The program uses independent maps for each scenario so that results from an earlier section do not interfere with a later one.

The assertions verify order, sums, and data for valid paths. The `observedCme` helper only records whether an exception was observed in scenarios that intentionally render an old iterator unusable. It is not a tool for determining application correctness.

~~~java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AccessOrderIteratorDemo {
    private static LinkedHashMap<String, Integer> sample(boolean accessOrder) {
        LinkedHashMap<String, Integer> map =
                new LinkedHashMap<>(16, 0.75f, accessOrder);
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        return map;
    }

    private static List<String> keys(Map<String, Integer> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void requireOrder(Map<String, Integer> map,
                                     List<String> expected) {
        if (!keys(map).equals(expected)) {
            throw new AssertionError("Unexpected order");
        }
    }

    // Observation only: application correctness must not depend on CME.
    private static boolean observedCme(Iterator<?> iterator) {
        try {
            iterator.next();
            return false;
        } catch (ConcurrentModificationException exception) {
            return true;
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> access = sample(true);
        Iterator<String> old = access.keySet().iterator();
        access.get("A");
        requireOrder(access, List.of("B", "C", "A"));
        System.out.println("access/size=" + access.size());
        System.out.println("access/order=" + keys(access));
        System.out.println("access/oldIteratorCME=" + observedCme(old));

        LinkedHashMap<String, Integer> insertion = sample(false);
        Iterator<String> insertionIterator = insertion.keySet().iterator();
        insertion.put("A", 10);
        requireOrder(insertion, List.of("A", "B", "C"));
        System.out.println("insertion/afterPut=" + insertion);
        System.out.println("insertion/next=" + insertionIterator.next());

        LinkedHashMap<String, Integer> views = sample(true);
        Iterator<String> viewIterator = views.keySet().iterator();
        boolean containsA = views.containsKey("A");
        int sum = 0;
        for (Map.Entry<String, Integer> entry : views.entrySet()) {
            sum += entry.getValue();
        }
        requireOrder(views, List.of("A", "B", "C"));
        if (!containsA || sum != 6) {
            throw new AssertionError("Unexpected view result");
        }
        System.out.println("views/containsA=" + containsA + ", sum=" + sum);
        System.out.println("views/order=" + keys(views));
        System.out.println("views/next=" + viewIterator.next());

        LinkedHashMap<String, Integer> updated = sample(true);
        for (Map.Entry<String, Integer> entry : updated.entrySet()) {
            entry.setValue(entry.getValue() * 10);
        }
        requireOrder(updated, List.of("A", "B", "C"));
        System.out.println("setValue/map=" + updated);

        LinkedHashMap<String, Integer> removed = sample(true);
        List<String> visited = new ArrayList<>();
        Iterator<Map.Entry<String, Integer>> removalIterator =
                removed.entrySet().iterator();
        while (removalIterator.hasNext()) {
            Map.Entry<String, Integer> entry = removalIterator.next();
            visited.add(entry.getKey());
            if (entry.getValue() == 2) {
                removalIterator.remove();
            }
        }
        requireOrder(removed, List.of("A", "C"));
        System.out.println("remove/visited=" + visited);
        System.out.println("remove/map=" + removed);

        LinkedHashMap<String, Integer> two = sample(true);
        Iterator<String> first = two.keySet().iterator();
        Iterator<String> second = two.keySet().iterator();
        first.next();
        first.remove();
        requireOrder(two, List.of("B", "C"));
        System.out.println("twoIterators/otherCME=" + observedCme(second));

        LinkedHashMap<String, Integer> snapshotMap = sample(true);
        List<String> snapshot = keys(snapshotMap);
        List<List<String>> orders = new ArrayList<>();
        for (String key : snapshot) {
            snapshotMap.get(key);
            orders.add(keys(snapshotMap));
        }
        requireOrder(snapshotMap, List.of("A", "B", "C"));
        System.out.println("snapshot/keys=" + snapshot);
        System.out.println("snapshot/orders=" + orders);

        LinkedHashMap<String, Integer> sameSize = sample(true);
        Iterator<String> beforeReplacement = sameSize.keySet().iterator();
        sameSize.remove("A");
        sameSize.put("D", 4);
        requireOrder(sameSize, List.of("B", "C", "D"));
        System.out.println("sameSize/size=" + sameSize.size()
                + ", order=" + keys(sameSize));
        System.out.println("sameSize/oldIteratorCME="
                + observedCme(beforeReplacement));

        LinkedHashMap<String, Integer> nullable = sample(true);
        for (Map.Entry<String, Integer> entry : nullable.entrySet()) {
            if (entry.getKey().equals("B")) {
                entry.setValue(null);
            }
        }
        requireOrder(nullable, List.of("A", "B", "C"));
        Integer value = nullable.get("B");
        requireOrder(nullable, List.of("A", "C", "B"));
        System.out.println("nullAccess/value=" + value
                + ", order=" + keys(nullable));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 AccessOrderIteratorDemo.java
java AccessOrderIteratorDemo
~~~

Stdout from the verification run:

~~~text
access/size=3
access/order=[B, C, A]
access/oldIteratorCME=true
insertion/afterPut={A=10, B=2, C=3}
insertion/next=A
views/containsA=true, sum=6
views/order=[A, B, C]
views/next=A
setValue/map={A=10, B=20, C=30}
remove/visited=[A, B, C]
remove/map={A=1, C=3}
twoIterators/otherCME=true
snapshot/keys=[A, B, C]
snapshot/orders=[[B, C, A], [C, A, B], [A, B, C]]
sameSize/size=3, order=[B, C, D]
sameSize/oldIteratorCME=true
nullAccess/value=null, order=[A, C, B]
~~~

The code was compiled with `--release 17` and ran successfully. The release option specifies the compatible API level and target bytecode; it does not assert that the executing JVM is specifically JDK 17.

The `CME=true` lines are observed results in the environment tested, consistent with the OpenJDK mechanism explained. Do not turn those results into a rule that "every improper modification always throws an exception at this exact spot."

## 11. Reading the Output by the Question Each Section Answers

### 11.1. Access: Size Unchanged, Traversal Path Changed

The first three lines show that size is still three, the order became B, C, A, and using the old iterator observed a CME.

There is no secondary thread in the program. There is no value change. The trigger is the get call in access-order mode.

### 11.2. Insertion: Replacing the Value of an Existing Key

The insertion section creates an iterator before `put("A", 10)`. The map is in insertion-order mode, so updating a value does not change mapping membership or insertion order. The iterator continues to return A in that scenario.

Do not infer that put is always safe during iteration: adding a new key is a different case, and access-order also has different rules.

### 11.3. Views and setValue: Reading or Modifying in Place

`containsKey("A")` along with the entrySet traversal computing the sum does not move A to the end. The previously created iterator can still retrieve A.

In the setValue section, the program modifies each entry's value to ten times its old value. The order remains A, B, C. It does not use put to update each key and does not use get to read values.

### 11.4. Remove: The Right Iterator and Another Iterator

The removal pass visits A, B, C; only B is removed via `removalIterator.remove()`. A and C remain.

In the two-iterator scenario, the first iterator validly removes via its own remove. The second iterator observes a CME when used next. That illustrates the scope limit of the exception granted to the iterator itself.

### 11.5. Snapshot: The Final Order May Return to the Initial One

The independent key list holds A, B, C. The loop iterates over the list, so it can get each key from the map without modifying the very structure the list iterator is traversing.

The snapshots after each get are B, C, A; C, A, B; and A, B, C. The final order matches the initial one, but there is a history of changes. You must not use that final match to validate an old map iterator.

### 11.6. SameSize and nullAccess

Removing A and then adding D keeps the size at three, yet the old iterator is still affected. A size counter does not replace change tracking.

With nullAccess, B's value is set to null via the entry before calling get. The order verified before get is A, B, C. After get, the returned value is null and the order becomes A, C, B: a null value does not prevent an access from affecting order.

## 12. How to Find Bugs in Real Code

When encountering an iterator-related bug, write down a timeline instead of looking only at the line that threw the exception:

| Milestone | Information to determine |
|---|---|
| Map creation | Insertion-order or access-order mode? |
| Iterator creation | Created before or after the suspected operation? |
| Loop body | Are there get, put, remove, or indirect calls into the same map? |
| View | Is this a live view or an independent copied structure? |
| Update mechanism | Through the iterator itself, the entry, or the map? |
| Concurrency | Do all accesses obey the same locking policy? |
| Error handling | Have any side effects already occurred before the exception? |

If the failure occurs at `iterator.next()`, the trigger may lie in an earlier call. Read the entire chain of helper functions, callbacks, and state-tracking functions.

Do not conclude the root cause just because changing the data makes the error temporarily disappear. A key that happens to be at the end or a single-element map can mask the fact that calling get changes order in other cases.

## 13. Exercises and Solutions

### Exercise 1. Reading a Timeline

An access-order map has order A, B, C. An iterator is created and then get(B) is called. What is the new order? Why does size not prove the old iterator is still valid?

**Solution:** The order becomes A, C, B. The number of mappings is still three, but the chain changed, which counts as structural state to consider. The old iterator was created before the change; size only counts mappings.

### Exercise 2. Is a Second Thread Needed?

A single-threaded program iterates over keySet and calls get for each key on the same map. Why can a CME still occur?

**Solution:** The enhanced for-loop uses an iterator. Calling get in access-order mode can alter the chain the iterator is using. The conflict between traversal and modification can be caused by the same thread; the exception name does not require a second thread.

### Exercise 3. Fixing the Read Pattern

You only need to print key-value pairs, but you are iterating over keySet and then calling get. Fix it and state two benefits.

**Solution:** Iterate over entrySet and use entry.getKey and entry.getValue. This avoids an extra lookup and avoids having get refresh the order on the map. It does not by itself solve modifications from other threads.

### Exercise 4. Does the Update Match Business Semantics?

A job increments every entry's value but must not change access recency. Is using entry.setValue appropriate? What if the update must refresh recency?

**Solution:** Using setValue during an entrySet traversal fits the requirement to preserve order, when the traversal is properly protected. If the update must refresh recency, you need to organize a separate phase or iterate over independent keys and then perform an operation with access semantics; do not drop the business effect just to avoid an exception.

### Exercise 5. Removing in the Wrong Place

A while-loop uses an iterator but removes elements with cache.remove(key). Why does switching to iterator.remove matter? What are the rules for calling remove?

**Solution:** Removing through the iterator itself allows that traversal to maintain a matching expected state. Remove must be called after next, at most once per next call. It does not permit arbitrary other modifications and does not automatically keep a second iterator valid.

### Exercise 6. HasNext Returns True

After a get that changes order, hasNext still returns true in an OpenJDK experiment. Should you continue because "the iterator confirmed it"?

**Solution:** No. In the mechanism explained, hasNext only sees whether a next node remains; the next step is what checks the modification counter. More importantly, an algorithm must obey the traversal contract rather than relying on when a particular method performs its check.

### Exercise 7. No Exception Observed

A test with only one key iterates and calls get without throwing an exception. Is that enough to keep the pattern in a multi-key system?

**Solution:** No. The single key is already at the end; the implementation may not need to relink anything. Other data can trigger a change. Silence from fail-fast is not proof that the pattern is valid in general.

### Exercise 8. Key Snapshot

What does switching to a new ArrayList of keySet avoid? Does it create a snapshot of all values and guarantee thread safety?

**Solution:** The loop's iterator walks the independent list, so calling get on the map does not modify that list structure itself. Values are still read from the map at the time of get; keys or values may have changed if other activity occurred. Both the copy step and subsequent accesses still require an appropriate concurrency policy.

### Exercise 9. Full Locking Yet Still Wrong

An application holds synchronized on a wrapped map for the entire loop, but inside the body calls get on that same access-order map. Why is the lock not enough?

**Solution:** A lock prevents concurrent operations that obey the same lock. It does not stop the very thread holding the lock from changing the map's order and invalidating its own traversal. You must also fix the traversal's algorithm, such as reading the value from the entry.

### Exercise 10. Final State Matches Initial State

Create an iterator on A, B, C, then call get A, get B, get C. The final order is A, B, C again. Can you use the old iterator as if nothing happened?

**Solution:** No. Multiple order transitions occurred in between. The traversal contract considers modifications during the process, not just comparing the start and end states.

## 14. Questions to Answer Before Writing a Loop

Clearly determine whether the data being traversed is a view or a copy, which ordering mode is in use, and which kinds of state the operations in the body can change. If you only read pairs, use the entry. If you modify values while preserving order, consider setValue during traversal. If you remove, use the traversal's own iterator. If you need to refresh access per key, separate the traversal structure or split into deliberate phases.

Correctness comes from how operations are organized and an appropriate concurrency policy. Fail-fast helps detect bugs; it does not replace those decisions.
