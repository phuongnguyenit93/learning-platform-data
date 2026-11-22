# Mutable State in a Comparator Causes Unstable Sorting Results

## 1. The Problem to Understand

`Comparator<T>` expresses a rule determining the order between two objects of type `T`. APIs such as `List.sort`, `Collections.sort`, `Stream.sorted`, `TreeSet`, `TreeMap`, and `PriorityQueue` can call `compare(a, b)` multiple times to make decisions.

If a comparator **reads mutable state** (a reversal flag, current time, global configuration, call count, data from an external service, or a mutable property of an element), the ordering relation it returns can change between calls.

For example, on the exact same two objects `a` and `b`:

```text
Call 1: compare(a, b) = -1  -> a comes before b
Call 2: compare(a, b) = +1  -> a comes after b
```

If the two objects' data and business comparison criteria should not have changed, two conflicting results mean the algorithm is receiving contradictory decisions. Sorting may produce an unexpected order, or an implementation may detect the contract violation and throw an exception. You must never assume the algorithm will always detect the bug.

The key point: **for a single sort operation, the comparison criteria must produce a consistent ordering relation from start to finish**. For continuously maintained ordered collections such as `TreeSet`/`TreeMap`, the criteria must remain consistent for as long as elements/keys stay inside the structure.

## 2. What Does the `Comparator.compare()` Contract Require?

For a `Comparator<T> comparator`, `compare(x, y)` returns a negative integer, `0`, or a positive integer to express that `x` comes before, is comparator-equivalent to, or comes after `y`. **Specific numeric values** like `-1` or `1` have no special meaning; only the sign matters.

The `Comparator` Javadoc specifies the logical properties of an ordering relation:

1. **Swapping arguments must flip the sign:** `signum(compare(x, y)) == -signum(compare(y, x))`. A comparator must never simultaneously assert `x < y` and `y < x`.
2. **Transitivity:** if `compare(x, y) > 0` and `compare(y, z) > 0`, then `compare(x, z) > 0`.
3. **Consistent equivalence:** if `compare(x, y) == 0`, then for every valid `z`, `compare(x, z)` and `compare(y, z)` must have the same sign.

These properties describe **a consistent ordering relation**. If a comparator changes how it evaluates while an algorithm relies on it, the overall relation may no longer satisfy those assumptions.

Important note: the documentation says a `Comparator` has an ordering **consistent with equals** when `compare(a, b) == 0` is equivalent to `a.equals(b)`. This property is strongly desirable when using `TreeSet`/`TreeMap` to fulfill the `Set`/`Map` contracts, yet a comparator inconsistent with `equals` does **not automatically** mean it mutates over time. Those are **two separate issues**.

## 3. Three Sources of State Causing a Comparator to Change Results

### 3.1. External control variables

Example of a comparator using a `descending` flag:

```java
Comparator<Integer> comparator =
        (a, b) -> descending
                ? Integer.compare(b, a)
                : Integer.compare(a, b);
```

The above is an **illustrative snippet** assuming a state variable `descending` already exists. When the flag flips from `false` to `true`, the same pair `1` and `2` changes from "1 before 2" to "1 after 2."

**Reversing direction between two independent sort operations can be a completely valid business requirement.** Risk arises when the comparator reads the flag **during an ongoing sort**, or when a collection was already structured under the old order yet still uses the same comparator whose direction has now flipped.

### 3.2. Counters, randomness, and clocks

Values such as `System.currentTimeMillis()`, `Instant.now()`, `Random.nextBoolean()`, or a counter incremented on every call can all change even while the two objects remain unchanged.

Conceptual bug example:

```java
int[] calls = {0};
Comparator<Integer> bad = (a, b) -> {
    calls[0]++;
    return (calls[0] % 2 == 0 ? -1 : 1)
            * Integer.compare(a, b);
};
```

Here, the exact same call `bad.compare(1, 2)` can return `-1` then `+1` merely because the call count changed. This is a **method unfit for sorting**. The fact that the code above compiles does not make it satisfy the ordering contract.

Do not turn "who was compared first," "how many comparisons occurred," or "whether the current minute is even or odd" into ordering criteria for values meant to be stably sorted.

### 3.3. Mutable properties of the element itself

Even without the comparator owning its own variable, results can still change. For example:

```java
Comparator<Employee> bySalary =
        Comparator.comparingInt(Employee::getSalary);
```

This is an **illustrative snippet**, assuming class `Employee` and method `getSalary()` exist.

If another thread or task modifies an employee's salary while the list is being sorted, comparator invocations can observe both pre-update and post-update state. Even when the comparator itself writes nothing, mutable input data makes the ordering unstable.

With `TreeSet<Employee>` or `TreeMap<Employee, ...>` ordered by salary, modifying the salary of a stored element/key also causes the already-sorted structure no longer to match the new criteria. The table/tree does not automatically re-sort itself whenever a field inside an object is modified.

## 4. Complete Runnable Java 17 Example

The example clearly separates two scenarios:

- **Safe:** choosing a fixed ascending or descending comparator for each separate sort operation.
- **Unsafe if used within the same operation:** a comparator reading a mutating flag, or flipping results by call count. The program only calls `compare` directly to demonstrate the bug; **do not call `sort` with a broken comparator**, because outcomes and exceptions can depend on the algorithm, data size, and call order.

Create the file **`ComparatorStateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;

public class ComparatorStateDemo {
    record Task(String name, int priority) {}

    static String names(List<Task> tasks) {
        return tasks.stream().map(Task::name)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        Comparator<Task> stable = Comparator
                .comparingInt(Task::priority)
                .thenComparing(Task::name);

        Task a = new Task("api", 3);
        Task b = new Task("db", 1);
        Task c = new Task("web", 2);

        List<Task> tasks = List.of(a, b, c);
        List<Task> ascending = new ArrayList<>(tasks);
        ascending.sort(stable);
        System.out.println("ascending: " + names(ascending));

        List<Task> descending = new ArrayList<>(tasks);
        descending.sort(stable.reversed());
        System.out.println("descending: " + names(descending));

        AtomicBoolean reverseFlag = new AtomicBoolean(false);
        Comparator<Task> mutable = (left, right) -> reverseFlag.get()
                ? stable.compare(right, left)
                : stable.compare(left, right);

        System.out.println("pair before: " + mutable.compare(b, c));
        reverseFlag.set(true);
        System.out.println("pair after: " + mutable.compare(b, c));

        int[] calls = {0};
        Comparator<Integer> changingEachCall = (left, right) -> {
            calls[0]++;
            int sign = (calls[0] % 2 == 0) ? -1 : 1;
            return sign * Integer.compare(left, right);
        };
        System.out.println("unstable first: "
                + changingEachCall.compare(1, 2));
        System.out.println("unstable second: "
                + changingEachCall.compare(1, 2));
    }
}
```

Compile and run:

```bash
javac --release 17 ComparatorStateDemo.java
java ComparatorStateDemo
```

**Stdout verified by compiling and running Java:**

```text
ascending: db, web, api
descending: api, web, db
pair before: -1
pair after: 1
unstable first: -1
unstable second: 1
```

Explanation:

1. `stable` compares `priority` and uses `name` as the secondary criterion on priority ties. Because both fields of record `Task` here are `int` and `String`, and these instances are not modified, the comparison order is fixed.
2. `stable.reversed()` produces a comparator that reverses the order *in a fixed way*. Two independent sort passes can generate ascending and descending outputs as required.
3. `mutable.compare(b, c)` initially returns `-1`, but after changing `reverseFlag` returns `1`. The result of the exact same comparison has become dependent on external state.
4. `changingEachCall` returns `-1` then `1` for the exact same pair of numbers, even though neither number changed. If a sorting algorithm relied on this comparator, partitioning decisions would contradict themselves.
5. `AtomicBoolean` guarantees flag reads/writes have proper cross-thread memory semantics; it does **not** make a comparator with flipping criteria stable. **Thread-safety in reading a variable is not synonymous with consistency of an ordering relation.**

The safe portion of the example uses a separate comparator per sort pass. The intentionally broken portion only illustrates repeated comparison calls; do not treat output from a sort pass using a mutating comparator as behavior guaranteed by Java.

## 5. What Can Happen in Sorting APIs?

### 5.1. `List.sort` and `Collections.sort`

Both sorting APIs rely on the results of multiple comparisons. When a comparator shifts criteria mid-way, the algorithm can be told "a before b" on one call and "a after b" on another.

Possible consequences include:

- The sorted list **no longer obeys the comparator at the end**.
- The order depends on the accidental count and sequence of comparisons the algorithm happened to make.
- Some implementations may throw `IllegalArgumentException` with a message like "Comparison method violates its general contract!". This is **possible** behavior, not an exception guaranteed for every broken comparator.
- If elements are mutated concurrently by another thread, collection and data access safety issues also arise. You cannot fix the comparator alone and assume all data races are eliminated.

Do not write tests like "a broken comparator must always throw an exception." A small array might finish sorting without detecting the violation; that **does not prove** the comparator obeys the contract.

### 5.2. `Stream.sorted(comparator)`

`Stream.sorted` also requires a consistent comparison relation when executing the terminal operation. Supplying a comparator that depends on a clock, randomness, or configuration mutable during the pipeline is a design bug, even if stream syntax looks immutable.

With parallel streams, a comparator with unsynchronized mutable state can also cause *data races*; even if state is synchronized, threads reading **different valid values** still make the ordering inconsistent. Synchronization is only part of the solution.

### 5.3. `TreeSet` and `TreeMap`

These collections use the **ordering provided by the comparator** (or natural ordering) to organize and look up elements/keys. A critical difference from a one-off sort: they require stable ordering criteria **for the entire duration items remain stored**.

For example, a `TreeSet` is created with an ascending comparator and elements are added. If an external flag later switches that same comparator to descending, the search structure was already built under the previous relation. `contains`, `add`, `remove`, or iteration operations can produce surprising results; the collection does not rebuild the entire tree when the flag changes.

Moreover, with `TreeSet`/`TreeMap`, **`compare(a,b) == 0`** determines whether two elements/keys are order-equivalent. If the comparator uses a mutable field, two previously distinct keys can become "equal" under the new criteria, or vice versa. That impacts uniqueness and lookups in the collection.

**Illustrative code snippet** (not a standalone program):

```java
TreeSet<Employee> employees =
        new TreeSet<>(Comparator.comparingInt(Employee::getSalary));

Employee employee = new Employee("An", 100);
employees.add(employee);

// If a setter changes the very criterion the tree uses for positioning:
employee.setSalary(1000);

// The tree does not automatically restructure itself just because an
// attribute of a stored object was modified; lookups may behave unexpectedly.
```

Necessary imports and the `Employee` class declaration are needed to run standalone. The safe approach is to avoid mutating key/sort attributes while the element resides in the tree; if unavoidable, **remove before mutating**, then modify and **re-add**, or build a new structure from a fixed data snapshot. Do not rely on `remove` with the already-mutated object still finding the old entry.

### 5.4. `PriorityQueue`

`PriorityQueue` uses a comparator to determine the highest-priority element according to the queue's convention. If the comparator changes criteria after elements have been added, the existing heap structure does not automatically reposition all elements into the new order. A subsequent `peek` or `poll` may fail to reflect the changed priority.

When changing the entire priority policy is needed, create a new priority queue using a new fixed comparator and insert elements from a current snapshot, rather than mutating state inside the old comparator and continuing to use the queue.

## 6. Three Easily Confused Kinds of "Stability"

### 6.1. Consistent comparator

Same data, same criteria: repeated comparisons must express the same ordering relation. This is the focus of this lesson. For a comparator to be stable, the inputs used for comparison and its configuration must keep appropriate values throughout the usage window.

### 6.2. Stable sorting algorithm (stable sort)

A sorting algorithm is **stable** if two elements considered equal by the comparator (`compare(a,b) == 0`) preserve their **original relative order** in the result. Per Java documentation, `List.sort` is a stable sort.

That **cannot rescue** a mutating comparator. Stable sort is meaningful only when the comparator already provides a valid ordering relation. If `compare` flips results mid-way, the question "which two elements are equal under the comparator" no longer has a consistent answer.

### 6.3. Reproducible results across multiple runs

Even with a completely valid comparator, multiple elements sharing the same sort key can yield different outputs when the **input order differs**. A stable sort preserves the order of elements deemed equivalent, so differences in input order can still carry over.

If a fully deterministic output order is needed, add an appropriate **tie-breaker**, such as sorting by `priority` then `id`:

```java
Comparator<Task> byPriorityAndId = Comparator
        .comparingInt(Task::priority)
        .thenComparing(Task::id);
```

This is an **illustrative snippet** assuming `Task` has `priority()` and `id()` accessors. This comparator yields a deterministic order only when accessor values are stable and the secondary criterion is sufficient to distinguish the elements that need distinguishing. If two distinct objects still share both criteria, the comparator continues to treat them as equal.

## 7. Designing Comparators Independent of Mutable State

### 7.1. Freeze configuration when creating the comparator

Instead of reading a mutable configuration variable on **every** `compare` call, capture the configuration value before starting:

```java
boolean descendingSnapshot = currentDescendingSetting;
Comparator<Item> base =
        Comparator.comparingInt(Item::getRank);

Comparator<Item> chosen = descendingSnapshot
        ? base.reversed()
        : base;
```

This is an **illustrative snippet**, assuming `currentDescendingSetting`, `Item`, and `getRank()` are suitably defined. The variable `descendingSnapshot` fixes the sort direction for the chosen comparator. To switch policy, build a new comparator and re-sort.

Do not mutate a global variable between comparisons while hoping the algorithm only reads it once.

### 7.2. Snapshot property data before sorting

When criteria depend on changing data (market prices, live scores, view counts, business status), you can create an **immutable snapshot**:

```java
record RankedItem(String id, int scoreSnapshot) {}

Comparator<RankedItem> byScore =
        Comparator.comparingInt(RankedItem::scoreSnapshot)
                  .thenComparing(RankedItem::id);
```

This is an **illustrative snippet**. The proper workflow is reading scores at a defined point in time, constructing `RankedItem` instances, and then sorting the snapshot. When the data source changes, build a new snapshot rather than silently altering the comparison relation of elements already in a structure.

A record only makes its fields `final`; if a record holds a reference to a mutable object, **the contents inside that reference can still change**. Choose immutable components or defensive copies when needed.

### 7.3. Separate comparison from side effects

`compare` should only **read relevant data** and return a result. Avoid:

- Incrementing a counter that **affects ranking criteria** on every comparison.
- Calling setters, updating a database, or writing to objects inside the comparator.
- Calling external APIs to fetch fresh values for the same object across comparison calls.
- Generating random numbers to break ties.
- Reading current time to continuously shift ordering.

If business logic needs random tie-breaking, **generate a seed or secondary order before sorting** and keep that value fixed throughout the sort pass. If business logic needs time comparisons, compare already-stored/snapshotted timestamps rather than asking "what time is it right now?" inside the comparator each time.

### 7.4. Avoid numeric overflow and logic bugs

Even a comparator with no mutable state can be wrong. For example:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Subtraction can overflow `int` and cause unreasonable sign flips on boundary values. Use:

```java
Comparator<Integer> right = Integer::compare;
```

When sorting by properties, prefer `Comparator.comparingInt`, `comparingLong`, `comparing`, `thenComparing`; they express criteria clearly and avoid many manual comparison bugs.

This is an independent yet related issue: a "state-frozen" comparator that violates transitivity or sign symmetry is still not valid.

## 8. Comparators, Concurrency, and Data Mutation Rights

In multithreaded systems, using `AtomicBoolean` or `volatile` to read a flag lets one thread **observe** updates from another thread. Yet if the observed value changes between two calls, the ordering relation still flips. Better solutions:

1. Lock in configuration before starting the sort operation.
2. Create a consistent snapshot of the attributes to be compared.
3. Prevent other threads from mutating data/snapshots used during sorting.
4. If results must be published after completion, publish the new list or collection using an appropriate thread-safe publication strategy.
5. For continuously ordered collections like `TreeMap`, `TreeSet`, and `PriorityQueue`, rebuild the structure whenever the ranking relation genuinely changes.

Do not treat `Collections.synchronizedList`, `volatile` on a single field, or a thread-safe flag as an automatic fix for **a comparison depending on multiple pieces of data**. Immutability or a consistent snapshot is what guarantees criterion stability.

## 9. Checking and Reviewing a Comparator

You can evaluate a comparator using the following questions:

- When calling `compare(a,b)` multiple times on unchanged data, do results have the **same sign**?
- Do `compare(a,b)` and `compare(b,a)` have opposite signs?
- Do `a > b` and `b > c` imply `a > c`?
- When `compare(a,b)==0`, are the comparison signs of `a` and `b` against any `c` identical?
- Does the comparator read `now()`, randomness, environment state, mutable config, a database, or a mutable field of the element?
- Are those values **fixed over the usage window**?
- If used with `TreeSet/TreeMap`, is the order consistent with `equals` when the application needs full `Set/Map` contract compliance?
- After an element is inserted into an ordered structure, does any code mutate its positioning criterion?

A short repeatability test (placed **inside a method** of a test class with a valid comparator and data):

```java
int first = Integer.signum(comparator.compare(a, b));
int second = Integer.signum(comparator.compare(a, b));
if (first != second) {
    throw new AssertionError("Unstable comparator");
}
```

This is an **illustrative test fragment**, not a standalone program. It catches some mutable-state bugs, but does not prove every input or every multithreaded schedule. Combine it with testing triples of elements, boundary data, and reviewing the comparator's data-reading paths.

If a sort run produces abnormal results or throws an `IllegalArgumentException` regarding the comparison contract, prioritize inspecting **the comparator's logic, data, and state** before investigating the sorting algorithm. Still, that exception is not the only diagnostic method and does not trigger in every case.

## 10. Real-World Scenarios

**Leaderboard:** scores update continuously in the database. Do not call an API to fetch new scores inside `compare`; instead, snapshot scores at publication time and sort the snapshots.

**UI with a reverse-order button:** each button click produces a new sorted list with `comparator.reversed()`. That is valid behavior; ensure clicking the button mid-sort does not flip the comparator currently in flight.

**Task priority queue:** when the priority policy changes, create a new `PriorityQueue` with the new comparator and reload the tasks to keep. Do not mutate a priority variable referenced by the old heap.

**Employee set ordered by salary:** if salary changes, do not mutate the sort field directly while the object remains in a `TreeSet`, expecting the tree to move the element automatically. Design around immutable keys, or manage remove/re-add operations using old and new values.

**Sorting by linguistic names:** you can use `Collator` to compare strings by locale, but do not alter configuration or share a mutable configuration object during sorting. Instantiate a comparator with fixed configuration for the task at hand.

## 11. Summary of Key Takeaways

- A comparator must provide a **consistent ordering relation** for the data the algorithm processes; the same pair must not flip signs merely because an external variable changed or the call count increased.
- Avoid reading current time, randomness, mutable config, counters, or fields being mutated inside `compare`.
- **Swapping comparators between two independent sorts is valid** if each sort uses a consistent criterion; **changing criteria during a sort** is what causes direct risk.
- `TreeSet`, `TreeMap`, and `PriorityQueue` maintain structural organization according to the comparator; when the ordering relation changes, the structure generally must be rebuilt.
- A stable sorting algorithm, a thread-safe flag, and a "consistent comparator" are distinct concepts; one does not automatically guarantee the others.
- Use fixed comparators, data snapshots, explicit tie-breakers, and helpers like `Comparator.comparingInt`/`thenComparing` for easily verifiable results.
- Java may detect violations in some situations and throw an exception, yet **does not guarantee always detecting them**; responsibility for preserving the contract lies in comparator design.