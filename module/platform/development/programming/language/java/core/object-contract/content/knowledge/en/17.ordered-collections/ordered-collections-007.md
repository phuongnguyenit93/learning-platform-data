# Mutating Sort Fields While an Object Resides in a `TreeSet` or `TreeMap`

## 1. What happens when a field used for sorting is modified?

Java's `TreeSet<E>` and `TreeMap<K, V>` maintain data in a balanced search tree structure, sorted by **natural ordering** (`Comparable.compareTo`) or a supplied **`Comparator`**. When adding an element or key, the tree uses the comparison result to determine position and balance the structure.

If you **modify a field participating in `compareTo`/`Comparator` while the object is still in the tree**, the correct order under the new value may no longer match the previously determined position. The tree **does not automatically detect changes inside the object**, does not automatically pull the node out and reinsert it, and does not automatically re-sort everything whenever an object changes state.

For example, at insertion time a tree holds three jobs:

```text
Keys in order: A(10), B(20), C(30)
Where the number in parentheses is the priority used for comparison.

Change A.priority: 10 -> 25 while A is still in the tree.
New values should sort as: B(20), A(25), C(30).
Yet the tree may still traverse in the old position: A(25), B(20), C(30).
```

At that point, the assumption that every left subtree contains smaller keys and every right subtree contains larger keys under the current comparator has been broken. **Do not continue relying on find, add, remove, iteration, or range-query results** from that collection as if the structure were still valid.

This is a **mutable ordering key** problem while stored in the tree, independent of whether that field is declared `private`. Setters, reflection, operations through another reference, or changes to external state read by a `Comparator` can all cause the same situation.

## 2. Why don't `TreeSet`/`TreeMap` re-sort automatically?

In an ordered structure, lookup relies on sequential comparisons from a node down to tree branches. Operations like `TreeSet.contains(value)` or `TreeMap.get(key)` do not scan every node to re-check all fields; they rely on **the ordering relation used to organize the tree**.

When a key that used to sit in a branch for smaller values is mutated into a larger value, a lookup with the new key may take a different branch and **fail to encounter the stored object**. Other consequences may also appear:

- `contains()` / `get()` returns surprising results (for example, reporting not found even though the object is still in the collection).
- `remove()` or `TreeMap.remove()` fails to locate the element/key, because the search algorithm follows the changed value.
- Iteration order is no longer ascending according to the current `compareTo()`/`Comparator`.
- Adding a new value may collide with the old key, leaving elements that current comparison considers equivalent or causing unpredictable collection behavior.
- `first()`, `last()`, `floor()`, `ceiling()`, `headSet()`, `tailSet()`, `subSet()`, and range operations on `NavigableMap` may no longer reflect the expected order.

Specific symptoms can vary depending on tree structure and algorithmic path. The fact that a single `contains()` call happens to return `true` **does not prove in-place key mutation is safe**.

## 3. Conditions that must remain stable

While an object is used as a **`TreeSet` element** or **`TreeMap` key**, the data determining comparison results against other elements/keys must remain stable.

For example, if `compareTo()` compares by `priority` then `id`, both `priority` and `id` must have fixed semantics relative to tree position. If a `Comparator` compares by `user.getDepartment().getName()`, renaming the department can also change comparison results **even if direct fields on the `user` object did not change**.

This is why **immutable keys** should be preferred: fields used for comparison are `final`, and nested components also cannot be mutated in ways that affect ordering. A `record` can be helpful for shallowly immutable value keys; keep in mind that a `final` field pointing to a mutable object can still cause data read by the comparator to change.

## 4. Compilable and runnable Java 17+ example

The following program shows how mutating a sort field in place breaks ascending iteration order, along with two ways to restore proper ordering. Save as **`MutableTreeKeyDemo.java`**:

```java
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;

public class MutableTreeKeyDemo {
    private static final class Job implements Comparable<Job> {
        private final String id;
        private int priority;

        Job(String id, int priority) {
            this.id = Objects.requireNonNull(id);
            this.priority = priority;
        }

        void setPriority(int priority) {
            this.priority = priority;
        }

        @Override
        public int compareTo(Job other) {
            int byPriority = Integer.compare(priority, other.priority);
            return byPriority != 0 ? byPriority : id.compareTo(other.id);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof Job other)) return false;
            return priority == other.priority && id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, priority);
        }

        @Override
        public String toString() {
            return id + "(" + priority + ")";
        }
    }

    private static boolean isSorted(TreeSet<Job> set) {
        Job previous = null;
        for (Job current : set) {
            if (previous != null && previous.compareTo(current) > 0) {
                return false;
            }
            previous = current;
        }
        return true;
    }

    public static void main(String[] args) {
        Job a = new Job("A", 10);
        Job b = new Job("B", 20);
        Job c = new Job("C", 30);
        TreeSet<Job> broken = new TreeSet<>();
        broken.add(a);
        broken.add(b);
        broken.add(c);
        System.out.println("before mutation: " + broken);

        a.setPriority(25); // Wrong: element is still inside the tree
        System.out.println("after mutation: " + broken);
        System.out.println("order still valid: " + isSorted(broken));

        TreeSet<Job> rebuilt = new TreeSet<>();
        for (Job job : broken) {
            rebuilt.add(job);
        }
        System.out.println("rebuilt: " + rebuilt);
        System.out.println("rebuilt order valid: " + isSorted(rebuilt));

        Job safeA = new Job("A", 10);
        TreeSet<Job> safe = new TreeSet<>();
        safe.add(safeA);
        safe.add(new Job("B", 20));
        safe.add(new Job("C", 30));
        boolean removed = safe.remove(safeA); // Remove using old value
        safeA.setPriority(25);
        boolean inserted = safe.add(safeA);   // Insert using new value
        System.out.println("safe remove: " + removed);
        System.out.println("safe reinsert: " + inserted);
        System.out.println("safe result: " + safe);

        Job mapKey = new Job("K", 5);
        TreeMap<Job, String> map = new TreeMap<>();
        map.put(mapKey, "pending");
        String oldValue = map.remove(mapKey); // Remove before mutating key
        mapKey.setPriority(7);
        map.put(mapKey, oldValue);
        map.replace(mapKey, "done");
        System.out.println("TreeMap value: " + map.get(mapKey));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac MutableTreeKeyDemo.java
java MutableTreeKeyDemo
```

Output of this program on standard Java implementations complying with the collection contract:

```text
before mutation: [A(10), B(20), C(30)]
after mutation: [A(25), B(20), C(30)]
order still valid: false
rebuilt: [B(20), A(25), C(30)]
rebuilt order valid: true
safe remove: true
safe reinsert: true
safe result: [B(20), A(25), C(30)]
TreeMap value: done
```

Here, `Job.compareTo` checks `priority` first and then `id` so that two jobs sharing priority yet having different IDs are still distinguished. `equals()` and `hashCode()` are implemented consistently with those two fields; this **does not make changing `priority` while the element is in the tree safe**.

The program intentionally avoids relying on `broken.contains(a)` after mutating the field, because the result can depend on tree layout. Seeing the traversal order `[A(25), B(20), C(30)]` fail to be ascending is sufficient to demonstrate the ordering invariant violation; the old tree should no longer be used. The example creates `rebuilt` by inserting **element by element** under current comparisons, without relying on copying the broken tree structure as-is.

In the `safe` section, `remove(safeA)` happens **before** `safeA` mutates, so removal can locate the element via the old sort data. Reinserting after changing the value lets the tree organize the new position. If removal fails, handle the error rather than proceeding to mutate and reinsert as if it succeeded.

## 5. Safe fixes in applications

### Approach 1: Use immutable key objects, replace with a new object

If you want to change an element's priority, construct a new value and update the set:

```java
record JobKey(String id, int priority) { }

// Illustration inside a method:
// TreeSet<JobKey> sorted = new TreeSet<>(
//     Comparator.comparingInt(JobKey::priority).thenComparing(JobKey::id));
// JobKey oldKey = new JobKey("A", 10);
// sorted.add(oldKey);
// sorted.remove(oldKey);
// sorted.add(new JobKey("A", 25));
```

`JobKey` is a `record` and the comment below describes **lines placed inside a method**; to run in full, declare the comparator, import `TreeSet`/`Comparator`, and place the code in an appropriate class/method. The core idea is never modifying fields used for ordering on an object currently stored. With a `record` holding only `String` and `int` as above, both components are immutable.

### Approach 2: `remove` first, mutate next, then `add` back

If you are forced to use a mutable object:

```text
1. Locate the element/key with its old state.
2. Remove it from the tree using its old state.
3. Only after removal succeeds, mutate the comparison fields.
4. Add it back with its new state.
5. Check the add/update result and handle any compareTo == 0 conflict.
```

This is the sequence applicable to `TreeSet`; for `TreeMap`, save **the value associated with the key** before removing, then `put` the modified key with the required value. Do not equate `TreeMap.remove(k)` returning `null` with guaranteeing the key was absent if the map permits `null` values: use `containsKey(k)` before removing or manage state per business logic.

**Important:** Do not mutate the key **first** and then call `remove`; by then the removal algorithm may also fail to find it. If it has already been mutated by mistake, build a new tree from trusted source data, check comparator conflicts, and replace the old tree cleanly.

### Approach 3: Rebuild the entire tree when batch updates are needed

When many keys must change in bulk, gather the elements, complete updates **outside the collection currently in use**, and then insert each element into a new `TreeSet`/`TreeMap` with a stable comparator. This guarantees positioning is based on the new values.

For instance, `new TreeSet<>(someSortedSet)` should not be treated as a guaranteed fix if the source **already violates ordering**: some implementation paths may leverage the source's “already sorted” assumption. Instead, construct an empty tree and `add`/`put` each element as in the `rebuilt` example.

For `TreeMap`, when rebuilding you must define a policy if **multiple keys compare as `0` after mutation**, because `put` may overwrite the value of an equivalent key; losing a mapping can cause business bugs.

## 6. Distinguish changing the key from changing the value

| Change | Impact on tree ordering |
| --- | --- |
| Changing `priority` of a `TreeSet` element when the comparator inspects `priority` | **Unsafe**, the tree does not update position automatically |
| Changing a field of a `TreeMap` key used by `compareTo`/`Comparator` | **Unsafe**, lookups may fail |
| Changing a field on an element that the comparator **never reads** | Does not break ordering from that change alone, provided the actual comparison relation stays stable |
| Calling `map.put(existingKey, newValue)` or `map.replace(existingKey, newValue)` with a stable key | **Safe for tree ordering** because only the value is updated |
| Modifying the contents of an object serving as a **value** in `TreeMap` when the comparator inspects only keys | Does not itself break key ordering |
| Changing external state used by the comparator (configuration, priority table, nested property) | Can be **unsafe** even if the key object does not change directly |

Note: an object whose `equals()` and `hashCode()` depend on mutable fields can also suffer a similar issue in `HashSet`/`HashMap`, though there the primary cause is **hash buckets** under the old hash. For ordered trees, the primary cause is **comparison relations and node positions**.

## 7. `compareTo() == 0` and conflicts upon reinsertion

`TreeSet` and `TreeMap` use `compareTo()`/`Comparator.compare()` to identify two keys as **equivalent in order**, meaning a comparison result of `0`. After changing a field, the old element may become equivalent to another element already in the tree.

For example, two jobs with the same `priority`, if the comparator **compares only `priority`**, may be treated as one key even when `id` differs. `TreeSet.add()` then returns `false`, while `TreeMap.put()` may update the value of the existing key.

Therefore, decide upfront whether multiple jobs are permitted at the same priority level. If so, the comparator needs a stable secondary criterion, for example:

```java
Comparator<Job> order = Comparator
        .comparingInt((Job job) -> job.priority)
        .thenComparing(job -> job.id);
```

This is a **snippet placed in a context having the `Job` class and `import java.util.Comparator`**; if `Job` is a class like the example above and the code sits outside the nested class, private field access must be handled appropriately. Even with a secondary criterion, `priority` remains a field participating in comparison and **still must not be mutated while the element resides in the tree**.

Additionally, the `Comparable`/`Comparator` contract requires sign antisymmetry, transitivity, and consistency when two values compare as `0` against any third value. A contract-breaking comparator can destabilize the tree **even when fields do not change**.

## 8. Technical checklist when updating an ordered key

- Confirm which data actually participates in `compareTo`/`Comparator`, including nested properties or external state.
- Prefer creating a **new immutable key** and replacing via remove/insert operations.
- If the same mutable object must be used, always verify `remove` succeeded **before** modifying comparison fields.
- For `TreeMap`, preserve the needed value when removing and reinserting the updated key; distinguish key absence from a null value.
- Check whether the new key evaluates to `compareTo == 0` against another key and handle according to business policy.
- When a tree is already corrupted by in-place mutation, rebuild from canonical data by **reinserting each key**; do not rely on querying the corrupted tree to prove correctness.
- In multithreaded programs, synchronize/coordinate updates and reads appropriately; `TreeSet`/`TreeMap` generally do not automatically synchronize concurrent modifications.

## 9. Self-check questions

1. Inserted `Task(priority=10)` into a `TreeSet`, then changed `priority` to `50` via a setter. Does the tree automatically move the node to the right position? **No**; you must remove first and reinsert, or build a new set.
2. Mutated the key field first and then called `remove(key)`. Is removal guaranteed to work? **No**; the search path may no longer reach the stored node.
3. Does modifying a `value` in `TreeMap` break key ordering? **No**, if the comparator depends only on keys and keys remain stable.
4. If the comparator checks only `priority`, what happens after modifying two jobs to have the same priority and reinserting? **A key collision under `compare == 0` can occur**; it must be handled or a secondary criterion added.
5. Does copying directly from a `SortedSet` whose order is already broken always fix it? **No**; create an empty set and insert each element under the current comparator.

**Takeaway:** `TreeSet`/`TreeMap` build their structure from comparison results **at the time of key operations**. Mutating data that determines ordering while the object remains in the tree breaks tree invariants. Use immutable keys, or follow **remove → mutate → add/put** in strict order; if the structure is already invalid, rebuild from trusted data.
