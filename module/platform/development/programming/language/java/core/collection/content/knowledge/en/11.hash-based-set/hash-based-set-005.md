# LinkedHashSet and Insertion Order

## 1. When You Need Deduplication While Preserving First-Seen Order

Suppose the input data is:

```text
sql, java, sql, http, java
```

The requirement is to keep each value once and present them in the order of their first appearance:

```text
sql, java, http
```

Here, two requirements coexist:

- Do not keep multiple equal elements: the semantics of `Set`.
- Have a deterministic iteration order based on insertion history: the characteristic of `LinkedHashSet`.

`LinkedHashSet<E>` is a hash-based set that also maintains links between elements to iterate in insertion order. It is suitable when you need deduplication without losing a meaningful input sequence.

It is important to understand “insertion order” accurately:

> Elements currently in the set are iterated in the order they were newly added. Attempting to re-add an element that is already present does not move it to the end.

It does not mean elements are automatically sorted alphabetically or numerically. Nor does it mean an element just looked up with `contains` becomes the last element.

The examples in this article use a Java 17-compatible API. We focus on `add`, `contains`, `remove`, iteration, and copying to clearly see the ordering rules. [Java 17 LinkedHashSet Specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 2. Two Cooperating Structures: Hashing for Lookup, Linking for Iteration

`LinkedHashSet` can be understood through two responsibilities:

| Mechanism | Responsibility |
| --- | --- |
| Hash structure | Check whether an element is already present, look up, and remove by value |
| Linked chain between entries | Record the iteration order of the currently stored elements |

For example, after newly adding `"sql"`, `"java"`, and `"http"`, the ordering part can be visualized as follows:

```text
head → sql ↔ java ↔ http ← tail
```

This is a conceptual diagram of doubly-linked entries for ordering, not a list that callers can access by index.

When calling `contains("java")`, the set uses the hashing mechanism to search by equality rules. It does not need to treat `"java"` as “element at index 1” in a list.

When iterating with `for-each`, the iterator traverses the maintained order:

```java
// Illustrative snippet: topics is a LinkedHashSet<String>.
for (String topic : topics) {
    System.out.println(topic);
}
```

With the state shown in the diagram, the output order of lines is `sql`, `java`, `http`.

Changing the capacity of the hash structure does not turn the iteration rule into sorting by hash code. The linked chain for ordering is a separate part of the design. Users do not need to know internal bucket indices to reason about iteration order.

## 3. Ordering Rules After Each Operation

### 3.1. Adding an Absent Value: Placed at the End

Starting from an empty set:

```text
add("sql")  → [sql]
add("java") → [sql, java]
add("http") → [sql, java, http]
```

All calls return `true`, because each time a new element is added to the set.

This order is insertion order, not alphabetical order. If `"http"` is inserted before `"sql"`, the iteration sequence reflects that choice.

### 3.2. Adding an Existing Value: Keeps Its Old Position

If the set is currently `[sql, java, http]`:

```java
// Illustrative snippet.
boolean changed = topics.add(new String("sql"));
```

The result is `false`; the set remains:

```text
[sql, java, http]
```

A string created with `new String("sql")` has a different reference from another string instance, but they are equal by value. The set does not add a duplicate and does not move `"sql"` to the end.

The word “insertion” must not be interpreted as counting every `add` call. Only when an element is not present and is actually newly added does it receive a new position in the order.

The `LinkedHashSet` contract explicitly states that re-adding an element already present does not affect insertion order. [LinkedHashSet: re-insertion rule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

### 3.3. contains Does Not Change Order

A membership check:

```java
boolean exists = topics.contains("java");
```

does not move `"java"` to the front or to the end. If the state before was `[sql, java, http]`, the state after remains the same.

Therefore, a standard `LinkedHashSet` is not a “most recently accessed element becomes newest” structure. If a problem requires access order or a dedicated caching mechanism, choose a design that meets that requirement; do not infer it from the word `Linked`.

### 3.4. Removing an Element: Drops Its Position, Preserves Relative Order of the Rest

From `[sql, java, http]`, calling `remove("java")` succeeds:

```text
before: [sql, java, http]
after:  [sql, http]
```

`"sql"` is still before `"http"`. The set does not reorder the remaining elements.

Removing a value not in the set returns `false` and does not change the order. `remove` takes the value to remove; `LinkedHashSet` on Java 17 does not provide removal by index like a `List`.

### 3.5. Remove Then Re-add: This Is a New Insertion

If `"java"` was removed leaving `[sql, http]`, then calling `add("java")` produces:

```text
[sql, http, java]
```

The element no longer existed immediately before the `add`, so it is newly added at the end.

Distinguish between these two operation sequences:

| Operation when set is `[sql, java, http]` | Final result |
| --- | --- |
| Call `add("java")` only | `[sql, java, http]` |
| Call `remove("java")`, then `add("java")` | `[sql, http, java]` |

If using a remove–add sequence to change position, understand that it modifies the set's contents across two operations. It is not inherently atomic and is not safe to perform arbitrarily while another iterator is active.

### 3.6. addAll: Existing Elements Keep Their Places, New Elements Append in Encounter Order

Suppose the set is currently:

```text
[sql, http, java]
```

Add an ordered list:

```java
topics.addAll(List.of("http", "git", "sql", "docker"));
```

Result:

```text
[sql, http, java, git, docker]
```

`"http"` and `"sql"` are already present so they keep their positions. `"git"` and `"docker"` are added at the end in the order they are encountered in the list.

If the source of `addAll` has no guaranteed iteration order, a guaranteed new sequence cannot be inferred solely from the values the source contains. `LinkedHashSet` preserves the order it receives; it does not recreate insertion history that was already lost on the source side.

### 3.7. null Follows the Same Uniqueness and Ordering Rules

`LinkedHashSet` allows `null`, but at most one `null` element.

If the set is `[a, null, b]`:

- `add(null)` returns `false`, and the order does not change.
- Removing `null` and then re-adding it produces `[a, b, null]`.

To create a source containing `null` in examples, use `Arrays.asList(...)`. `List.of(...)` does not allow `null` elements, so it is unsuitable for that input.

## 4. Complete Program: Observing Order After Each Operation

Save the full code in **LinkedHashSetOrderDemo.java**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class LinkedHashSetOrderDemo {
    public static void main(String[] args) {
        Set<String> topics = new LinkedHashSet<>();
        topics.add("sql");
        topics.add("java");
        topics.add("http");
        System.out.println("initial: " + topics);

        System.out.println("contains java: " + topics.contains("java"));
        System.out.println("after contains: " + topics);
        System.out.println("add equal sql: " + topics.add(new String("sql")));
        System.out.println("after duplicate: " + topics);

        System.out.println("remove java: " + topics.remove("java"));
        System.out.println("after removal: " + topics);
        System.out.println("add java again: " + topics.add("java"));
        System.out.println("after re-add: " + topics);

        System.out.println("addAll changed: "
                + topics.addAll(List.of("http", "git", "sql", "docker")));
        System.out.println("after addAll: " + topics);

        Iterator<String> iterator = topics.iterator();
        while (iterator.hasNext()) {
            if (iterator.next().equals("git")) {
                iterator.remove();
            }
        }
        System.out.println("after iterator removal: " + topics);

        Set<String> nullable =
                new LinkedHashSet<>(Arrays.asList("a", null, "b"));
        System.out.println("nullable: " + nullable);
        System.out.println("add null again: " + nullable.add(null));
        System.out.println("after duplicate null: " + nullable);
        nullable.remove(null);
        nullable.add(null);
        System.out.println("after null re-add: " + nullable);
    }
}
```

Compile targeting Java 17 and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashSetOrderDemo.java
java LinkedHashSetOrderDemo
```

Stdout:

```text
initial: [sql, java, http]
contains java: true
after contains: [sql, java, http]
add equal sql: false
after duplicate: [sql, java, http]
remove java: true
after removal: [sql, http]
add java again: true
after re-add: [sql, http, java]
addAll changed: true
after addAll: [sql, http, java, git, docker]
after iterator removal: [sql, http, java, docker]
nullable: [a, null, b]
add null again: false
after duplicate null: [a, null, b]
after null re-add: [a, b, null]
```

Key points to verify from the output:

1. Initially `sql` comes before `java` even though that is not alphabetical order.
2. `contains("java")` only answers the membership question; it does not change the order.
3. Attempting to add a string equal to `"sql"` does not create a new element and does not push `sql` to the end.
4. After removing `java`, re-adding it places it after `http`.
5. `addAll` preserves the positions of existing elements and only appends `git` and `docker`.
6. Removing `git` with `Iterator.remove` does not alter the relative order of the remaining elements.
7. `null` is handled as an accepted value by this implementation and still appears only once.

The example uses `Set<String>` as the declared variable type and `LinkedHashSet` as the runtime object. Having the variable type be `Set` does not strip away the runtime object's behavior. However, if an API only promises to return an arbitrary `Set` without promising order, callers should not assume every future replacement implementation will preserve insertion order.

## 5. Stable Deduplication from an Ordered Source

A common usage pattern:

```java
// Illustrative snippet.
List<String> input = List.of("sql", "java", "sql", "http", "java");
Set<String> distinct = new LinkedHashSet<>(input);
```

The order of `distinct` is:

```text
[sql, java, http]
```

What happened step by step:

- First encounter of `sql`: added.
- First encounter of `java`: added after `sql`.
- Second encounter of `sql`: unchanged.
- First encounter of `http`: added at the end.
- Second encounter of `java`: unchanged.

This is deduplication while preserving first-appearance order. The `input` list is not structurally modified by creating the new set.

If a result list is needed after deduplication:

```java
List<String> result = new ArrayList<>(distinct);
```

The list is built according to the set's iteration order at the time of copying. From there, the list can serve an API that requires a sequence or indexed access.

Do not create a `HashSet` first and then convert to `LinkedHashSet` if the requirement is to preserve the list's original order. The first step already drops any guarantee of preserving that order:

```java
// Do not use this conversion sequence to guarantee the original order of input.
Set<String> intermediate = new HashSet<>(input);
Set<String> tooLate = new LinkedHashSet<>(intermediate);
```

`tooLate` will preserve the order it receives from `intermediate`, not restore the first-appearance order from the original list.

Similarly, copying a `HashSet` into a `LinkedHashSet` preserves the iteration sequence observed during that copy for the new copy. It does not turn an unguaranteed source order into an insertion history that can be relied upon across runs.

## 6. Which Element Is Kept When an Equal Value Is Encountered?

Deduplication is based on `equals` and `hashCode`, not on how elements print or whether two references are identical.

When `add(candidate)` returns `false` because an equal element already exists, the set stays unchanged. Do not treat that operation as “updating the stored object with the new object.”

For example, suppose a tag class defines equality only by ID. Two objects with the same ID but different display labels are considered equal under the class's rule. Adding the second object to a set that already contains the first is not a command to update the label.

Three distinct requirements must be distinguished:

| Requirement | What needs to be designed |
| --- | --- |
| Keep the first-encountered representative | Deduplication with `LinkedHashSet` from an appropriately ordered source |
| Keep the latest data by an ID | Requires key-based update/overwrite rules, typically fitting a `Map` |
| Keep the first position while updating some data | Requires custom design of identity, updatable data, and ordering |

Do not mutate fields participating in `equals` or `hashCode` while the object is inside the set. `LinkedHashSet` still relies on hashing; having a linked chain for ordering does not make mutable keys safe.

If an element class uses reference equality, two objects with identical contents can still both be stored. To deduplicate by value, you must design value equality rules first. There is no “automatically match identical fields” mode simply by choosing `LinkedHashSet`. [Set: element contract and mutable data](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 7. Insertion Order Does Not Become Part of Set Equality

Consider two sets:

```text
first:  [sql, java, http]
second: [http, java, sql]
```

They contain the same elements, so they are equal according to `Set.equals` even though their iteration sequences differ.

`LinkedHashSet` maintains order for iteration; it still adheres to set equality semantics. A set's hash code also does not include iteration order as a distinguishing criterion: two equal sets must have the same hash code. [Set.equals and hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

If a problem needs to compare two display orders, compare lists constructed from their iteration orders:

```java
// Illustrative snippet: first and second are two LinkedHashSet instances.
boolean sameMembers = first.equals(second);
boolean sameSequence =
        new ArrayList<>(first).equals(new ArrayList<>(second));
```

Two different questions:

- `sameMembers`: do the two sets have the same members?
- `sameSequence`: are the two current iteration sequences identical?

Do not use `Set.equals` to check order and then conclude the method is broken when it returns `true` for two different sequences.

## 8. Preserving Order Across Copies, Views, and Streams

### 8.1. Structural Copy with LinkedHashSet

```java
Set<String> copy = new LinkedHashSet<>(source);
```

The copy receives elements in `source`'s iteration order at the time of creation. Afterward, additions or removals in `source` do not automatically add or remove members in `copy`.

This is a structural copy of the set, not a deep copy of each element. Both sets can still hold references to the same element objects.

If the source has a guaranteed order, such as a `List` or `LinkedHashSet`, the copy's order can be inferred from that guarantee. If the source has no order guarantee, the copy only records the order it happened to receive and does not create a source-order guarantee.

### 8.2. Read-Only Does Not Mean a Copy

```java
Set<String> view = Collections.unmodifiableSet(source);
```

This is an **unmodifiable view** through the `view` reference. It still reads data from `source`. When the original set is modified elsewhere, changes can be observed through the view.

If `source` is a `LinkedHashSet`, removing and re-adding an element in `source` can change the order observed through `view`, even though `view` itself rejects mutating calls.

When the requirement is an independent snapshot that preserves current order and prevents the recipient from modifying the structure, copy first and then wrap:

```java
Set<String> snapshot =
        Collections.unmodifiableSet(new LinkedHashSet<>(source));
```

This separates the snapshot's set structure from the source set. Element objects still need separate consideration if they are mutable. [Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

### 8.3. Set.copyOf Does Not Promise Insertion Order

`Set.copyOf(source)` creates an unmodifiable set per its contract, but sets returned by those factory methods do not guarantee iteration order matching the source's insertion order.

Therefore, do not replace an order-sensitive copy expression with `Set.copyOf` and assume the output must preserve the sequence. Unmodifiability and iteration order are two separate properties. [Set: unmodifiable sets and iteration order](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

### 8.4. Specify LinkedHashSet in the Collector When You Need That Result

Given an ordered list:

```java
Set<String> distinct = input.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

`toCollection` accumulates in the source's encounter order and uses the specified factory to create the result set. Combined with `LinkedHashSet`, this matches the requirement of deduplicating while preserving first-encounter order.

Do not use `Collectors.toSet()` and assume the result is always a `LinkedHashSet` or always preserves order. That collector does not guarantee a specific set implementation and is an unordered collector.

The source must also have a meaningful encounter order if you want to promise a corresponding result order. Choosing the set type at the end does not recover an order that was discarded earlier. [Collectors.toCollection and toSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

## 9. Complete Program: Deduplication, Comparison, and Creating a Snapshot

Save the code in **LinkedHashSetCopyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class LinkedHashSetCopyDemo {
    public static void main(String[] args) {
        List<String> input = List.of("sql", "java", "sql", "http", "java");
        Set<String> distinct = new LinkedHashSet<>(input);
        Set<String> viaStream = input.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println("input: " + input);
        System.out.println("distinct: " + distinct);
        System.out.println("distinct as list: " + new ArrayList<>(distinct));
        System.out.println("via stream: " + viaStream);

        Set<String> otherOrder =
                new LinkedHashSet<>(List.of("http", "java", "sql"));
        System.out.println("other order: " + otherOrder);
        System.out.println("set equality: " + distinct.equals(otherOrder));
        System.out.println("hash equality: "
                + (distinct.hashCode() == otherOrder.hashCode()));
        System.out.println("iteration lists equal: "
                + new ArrayList<>(distinct).equals(new ArrayList<>(otherOrder)));

        Set<String> source =
                new LinkedHashSet<>(List.of("first", "second"));
        Set<String> view = Collections.unmodifiableSet(source);
        Set<String> snapshot =
                Collections.unmodifiableSet(new LinkedHashSet<>(source));

        source.remove("first");
        source.add("first");
        System.out.println("source after reorder: " + source);
        System.out.println("read-only view: " + view);
        System.out.println("copied snapshot: " + snapshot);
        try {
            view.add("third");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view mutation: UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 LinkedHashSetCopyDemo.java
java LinkedHashSetCopyDemo
```

Stdout:

```text
input: [sql, java, sql, http, java]
distinct: [sql, java, http]
distinct as list: [sql, java, http]
via stream: [sql, java, http]
other order: [http, java, sql]
set equality: true
hash equality: true
iteration lists equal: false
source after reorder: [second, first]
read-only view: [second, first]
copied snapshot: [first, second]
view mutation: UnsupportedOperationException
```

How to read the output:

1. The input retains duplicate elements; creating the new set does not modify the original list.
2. The set and the list copied from it preserve first-appearance order: `sql`, `java`, `http`.
3. A collector explicitly specifying `LinkedHashSet` produces the same sequence for an ordered input list.
4. Two sets with the same members but different orders are still equal and have the same hash code.
5. Two lists created from the two iteration orders are not equal, because lists consider position.
6. After the source set removes and re-adds `first`, the read-only view reflects the new order.
7. The previously copied snapshot still retains the order `first`, `second`.
8. Attempting to modify through `view` is rejected with `UnsupportedOperationException`.

Both programs in this article were compiled with `--release 17` and executed to verify exact stdout. This option checks the language/API level and generates Java 17-compatible bytecode; it does not assert that the executing JVM itself is JDK 17.

## 10. Performance and the Cost of Maintaining Order

`LinkedHashSet` still uses hashing for `add`, `contains`, and `remove` operations. Expected constant time depends on the assumption that hash codes distribute elements well and element equality checks have controlled cost.

It maintains additional links for ordering, so it incurs memory and link-update overhead. There is no basis for claiming it is always faster than `HashSet` simply because its order is predictable.

One useful difference is full iteration:

| Structure | Iteration order | Documented iteration work |
| --- | --- | --- |
| `HashSet` | Unspecified | Proportional to size plus capacity of the backing table |
| `LinkedHashSet` | Insertion order | Proportional to number of elements, independent of capacity per class documentation |

This does not make capacity or load factor meaningless for `LinkedHashSet`. They still affect the hash structure and memory used for storage. Only traversing the element sequence has a different cost model. [LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html), [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Do not use output print counts or print order as a measure of lookup speed. To evaluate real performance, consider element count, numbers of adds/removals/lookups/iterations, and key types.

## 11. Choosing a Structure by Ordering Semantics

| Primary requirement | Suitable structure or approach |
| --- | --- |
| Deduplicate, no iteration order requirement | `HashSet` can be used |
| Deduplicate, preserve first-seen order from an ordered source | `LinkedHashSet` |
| Iterate in sorted order of values | Consider `TreeSet` with an appropriate comparison rule |
| Keep both duplicates and positions | `List` |
| Store latest data by ID, with ordering requirements | Design with `Map` and explicit update/ordering rules |

`TreeSet` uses natural ordering or a comparator, not insertion order, to determine iteration sequence. At the same time, the comparison rule must be designed to align with element equality semantics. [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Some scenarios well suited for `LinkedHashSet`:

- A selected set of tags that needs deduplication while displaying in selection order.
- Configuration options merged in read order, keeping first-seen positions.
- A list of IDs imported from a file that needs deduplication without automatic re-sorting.
- Results of a processing step that must preserve received order for easy reconciliation against the source.

If the original order has no meaning or is already undefined from the start, using `LinkedHashSet` does not magically create a valid business order. For instance, it cannot know priority order, creation timestamps, or alphabetical order if that information is not represented in the source or processing rules.

## 12. Iterating and Modifying Safely

`LinkedHashSet` is not automatically synchronized for concurrent modifications by multiple threads. Predictable insertion order does not mean concurrent operations have a guaranteed business order.

Within a single thread, when an element must be removed during iteration, use an appropriate mechanism such as `Iterator.remove`, as demonstrated in the first program.

Do not use the following pattern to remove through a path other than the active iterator:

```java
// Illustrative snippet of what to avoid, not a valid removal pattern.
for (String topic : topics) {
    if (topic.equals("git")) {
        topics.remove(topic);
    }
}
```

The iterator may detect invalid structural modification and throw `ConcurrentModificationException`. The fail-fast mechanism is only best-effort; not seeing an exception in one run does not prove the iteration pattern is correct.

Removing and re-adding an element to change its position is also a structural modification. Do not perform that operation arbitrarily during an active iteration loop and expect the iterator to adjust itself as desired. [LinkedHashSet: synchronization and fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

## 13. Common Mistakes

| Misconception or pattern | Issue | Correct way of thinking |
| --- | --- | --- |
| Calling `add` on an existing element to push it to the end | Adding a duplicate does not change order | Distinguish re-adding while present from removing then newly adding |
| Calling `contains` and expecting the element to become newest | Queries do not change insertion order | This is not access-order |
| Thinking `LinkedHashSet` sorts automatically | It preserves new-insertion history | Value ordering requires explicit sorting rules |
| Creating a `HashSet` first and then converting to `LinkedHashSet` | Original order guarantee may already be lost | Create `LinkedHashSet` directly from an ordered source |
| Using `equals` to compare display order | `Set.equals` ignores order | Compare a sequence representation when order matters |
| Using `Set.copyOf` to promise preserving insertion order | That factory has no corresponding order guarantee | Choose a copy approach that satisfies both mutability and order |
| Assuming `unmodifiableSet` is a copy | It is a view reading through to the source set | Copy before wrapping if a snapshot is needed |
| Using `Collectors.toSet` and assuming `LinkedHashSet` | The collector does not promise that set type | Specify `toCollection` when needed |
| Adding an equal-by-value object to update stored data | Duplicate `add` leaves the set unchanged | Design key-based updates appropriately |
| Mutating identity fields while the element is in the set | Still carries hash-based key risks | Keep `equals`/`hashCode` stable |
| Relying on no exception when modifying directly during iteration | Fail-fast is not proof of correctness | Use supported removal-during-iteration mechanisms |

When the result has the wrong order, trace from the source: does the source guarantee order, did it pass through a step that lost that guarantee, is the element truly new or equal to an existing element, and is the final requirement comparing membership or sequence?

## 14. Practice and Verification

### Exercise 1: Tracing Order

Initialize:

```java
Set<String> values =
        new LinkedHashSet<>(List.of("p", "q", "p", "r"));
```

Execute sequentially:

```java
values.add("q");
values.contains("p");
values.remove("p");
values.add("p");
values.addAll(List.of("r", "s", "q"));
```

Verification:

| Step | Operation result | Order after step |
| --- | --- | --- |
| Initialization | Not a boolean expression to evaluate | `[p, q, r]` |
| `add("q")` | `false` | `[p, q, r]` |
| `contains("p")` | `true` | `[p, q, r]` |
| `remove("p")` | `true` | `[q, r]` |
| `add("p")` | `true` | `[q, r, p]` |
| `addAll(...)` | `true` | `[q, r, p, s]` |

Explain why the two `add` calls for `q` and `p` have different effects on order at their respective points in time.

### Exercise 2: Same Members or Same Sequence?

Given:

```java
Set<Integer> a = new LinkedHashSet<>(List.of(3, 1, 2));
Set<Integer> b = new LinkedHashSet<>(List.of(1, 2, 3));
```

Predict:

- `a.equals(b)`: `true`.
- `a.hashCode() == b.hashCode()`: `true`.
- `new ArrayList<>(a).equals(new ArrayList<>(b))`: `false`.

A correct answer must distinguish the set contract from sequence comparison. Do not use “it has an order” to conclude that set `equals` must consider order.

### Exercise 3: Choosing the Right Copy Approach

A component receives `LinkedHashSet<String> source` and must return a result that prevents the recipient from modifying its structure, preserves the order at creation time, and does not reflect additions/removals made elsewhere to `source`.

Choose among:

```java
Collections.unmodifiableSet(source);
Collections.unmodifiableSet(new LinkedHashSet<>(source));
Set.copyOf(source);
```

The second option fully satisfies the stated requirements for structure and order. The first option still reads through the source. The third option does not provide the required insertion-order guarantee.

If the element type changes from `String` to a mutable class, you must also consider the stability and mutability of each element object; a set copy is not automatically a deep copy.

### Exercise 4: Unordered Source

A `HashSet` is passed into `new LinkedHashSet<>(source)`. It can be concluded that the copy:

1. Preserves the iteration order it received during that copy.
2. Recovers the order in which the user originally added elements to the `HashSet`.
3. Always has the same copy order across every application run.

Only the first conclusion is valid. The latter two require information or guarantees that the source does not provide.

## 15. References

- [LinkedHashSet Java 17 — insertion order, re-insertion, performance, and iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)
- [HashSet Java 17 — unspecified order and hash-based mechanism](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
- [Set — equality contract and unmodifiable sets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)
- [Collections.unmodifiableSet — unmodifiable view](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))
- [Collectors — specifying result set type with toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [TreeSet — natural ordering or Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)