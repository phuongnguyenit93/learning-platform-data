# Collectors.toList, toSet, and toCollection

## 1. What problem do the three collectors solve?

A `Stream` describes how to read and process elements. After filtering or transforming, an application often needs to retain the result for further use: a full sequence, a set of distinct values, or a collection type with specific capabilities.

The three methods `Collectors.toList()`, `Collectors.toSet()`, and `Collectors.toCollection(...)` create a **collector** for that job. They do not produce the data list at the moment they are called; the terminal operation `Stream.collect(...)` uses the collector to accumulate the result.

Three roles should be distinguished:

| Component | Role |
| --- | --- |
| `Stream<T>` | Stream of elements and chain of processing operations |
| `Collector<T,A,R>` | Describes how to accumulate elements to produce a result |
| `Collectors` | Utility class providing common collectors |

In `Collector<T,A,R>`:

- `T` is the type of input elements.
- `A` is the type of the mutable accumulation container used during collection.
- `R` is the type of the returned result.
- The `?` in utility signatures hides the internal accumulator type that callers do not need to depend on.

A typical workflow:

```text
Data source
  -> Stream
  -> filter / map / required processing steps
  -> collect(collector)
  -> result collection
```

For example, duplicate occurrences in a sequence of orders may all need to be kept, whereas a sequence of tags used for UI filtering may only need each tag once. Choosing a collector means choosing the semantics of the result, not just choosing a shorter syntax.

The [`Collector` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html) describes the accumulation process; [`Stream.collect`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)) executes that collection.

### 1.1. Why does calling toList alone not give you a List yet?

The following snippet illustrates the roles and is not a standalone program:

```java
Collector<String, ?, List<String>> plan = Collectors.toList();
List<String> result = Stream.of("sun", "rain").collect(plan);
```

`plan` is the collection plan. `result` is the list containing the data after the terminal operation runs.

The two lines below do not compile; they are error examples to distinguish:

```java
List<String> wrong = Collectors.toList();

Stream.of("x").collect(
        Collectors.toCollection(new ArrayList<String>()));
```

The first line confuses the collector with the result. The second passes a collection instance, whereas `toCollection` requires a factory function of type `Supplier`. The correct approach usually uses a constructor reference like `ArrayList::new` or a lambda that creates a new object.

## 2. Reading the contracts of the three methods

Abbreviated API signatures:

```java
static <T> Collector<T, ?, List<T>> toList();
static <T> Collector<T, ?, Set<T>> toSet();
static <T, C extends Collection<T>>
        Collector<T, ?, C> toCollection(Supplier<C> collectionFactory);
```

| Method | Result | Duplicate elements | Order | Control over target class |
| --- | --- | --- | --- | --- |
| `Collectors.toList()` | `List<T>` | Keeps all occurrences | Preserves stream encounter order if present | No guarantee of specific implementation class |
| `Collectors.toSet()` | `Set<T>` | Deduplicates per set contract | Does not guarantee encounter order | No guarantee of specific implementation class |
| `Collectors.toCollection(factory)` | `C` chosen by factory | Follows the created collection | Accumulates in encounter order; iteration order also depends on target type | Explicitly chosen via factory |

The two general-purpose collectors `toList` and `toSet` make no guarantees regarding the implementation class, mutability, serializability, or thread-safety of the returned result.

Therefore, you should not cast the result of `toList` to `ArrayList`, nor treat `toSet` as a promise to return a `HashSet`. An implementation may use those classes without turning the observed class name into a public contract.

If you definitely need an `ArrayList` where elements can be added/removed, request it via `toCollection(ArrayList::new)`. If you need a read-only result, choose an API or finishing step that carries the corresponding guarantee; do not infer either mutability or immutability solely from the name `toList`.

The [`Collectors` specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) states the limitations of the two general-purpose collectors and the role of `toCollection`.

### 2.1. Encounter order is not the order in which sub-threads finish

**Encounter order** is the order in which the source or operation pipeline supplies elements. A `List` typically provides sequential order; an unordered source does not automatically become ordered just because the result is collected into a list.

A collection operation that preserves encounter order can run in parallel and still return results in that order. This does not require individual worker threads to finish sequentially from the first element to the last.

`toSet` is a collector with the `UNORDERED` characteristic: it makes no guarantee of preserving encounter order. This does not mean it must shuffle elements or produce a different order on every run. Output that happens to look sorted does not add an ordering guarantee to the API.

### 2.2. sorted followed by toSet does not guarantee sorted iteration

If an application sorts a stream and then terminates it with `toSet`, the target's contract still does not promise a corresponding iteration order.

Depending on the requirement, you can choose:

- `sorted(...).collect(Collectors.toList())` to keep a sorted sequence, including duplicate occurrences.
- `collect(Collectors.toCollection(TreeSet::new))` to get a set that maintains natural order and merges elements according to comparison rules.
- `collect(Collectors.toCollection(LinkedHashSet::new))` to deduplicate while preserving insertion order from an ordered source.

These are three different intents. Using `TreeSet` just to “make an ordered list” can lose duplicate occurrences that business logic still needs.

## 3. Program 1: Full sequence, set, and explicit target

This program intentionally does not print a specific order for the `toSet` result. It checks set contents using `Set.equals` and checks the element count, as those are the properties that should be observed.

File `BasicCollectionCollectorsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.LinkedHashSet;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class BasicCollectionCollectorsDemo {
    public static void main(String[] args) {
        List<String> drinks =
                new ArrayList<>(List.of("tea", "coffee", "tea", "juice"));

        List<String> all = drinks.stream().collect(Collectors.toList());
        Set<String> unique = drinks.stream().collect(Collectors.toSet());
        ArrayList<String> editable = drinks.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        LinkedHashSet<String> firstSeen = drinks.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        TreeSet<String> sortedUnique = drinks.stream()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("all=" + all);
        System.out.println("uniqueSize=" + unique.size());
        System.out.println("uniqueValues=" +
                unique.equals(Set.of("tea", "coffee", "juice")));
        System.out.println("firstSeen=" + firstSeen);
        System.out.println("sortedUnique=" + sortedUnique);

        editable.add("water");
        drinks.add("cocoa");
        System.out.println("editable=" + editable);
        System.out.println("sourceNow=" + drinks);
        System.out.println("allStill=" + all);

        System.out.println("emptyList=" +
                Stream.<String>empty().collect(Collectors.toList()).isEmpty());
        System.out.println("emptySet=" +
                Stream.<String>empty().collect(Collectors.toSet()).isEmpty());

        List<String> nullable = Stream.of("milk", null, "milk")
                .collect(Collectors.toList());
        Set<String> nullableSet = Stream.of("milk", null, "milk")
                .collect(Collectors.toSet());
        System.out.println("nullableList=" + nullable);
        System.out.println("nullableSetSize=" + nullableSet.size());
        System.out.println("nullableSetContainsNull=" + nullableSet.contains(null));
    }
}
```

Compile and run in the directory containing the file using a JDK supporting Java 17 or later:

```shell
javac --release 17 -encoding UTF-8 BasicCollectionCollectorsDemo.java
java BasicCollectionCollectorsDemo
```

Output:

```text
all=[tea, coffee, tea, juice]
uniqueSize=3
uniqueValues=true
firstSeen=[tea, coffee, juice]
sortedUnique=[coffee, juice, tea]
editable=[tea, coffee, tea, juice, water]
sourceNow=[tea, coffee, tea, juice, cocoa]
allStill=[tea, coffee, tea, juice]
emptyList=true
emptySet=true
nullableList=[milk, null, milk]
nullableSetSize=2
nullableSetContainsNull=true
```

### 3.1. Results differ because contracts differ

`all` keeps both occurrences of `"tea"`. `uniqueSize=3` shows that the set deduplicated entries; `uniqueValues=true` confirms all three expected values are present regardless of iteration order.

`firstSeen` preserves the first-seen order of each value in this sequential stream thanks to `LinkedHashSet`. `sortedUnique`, on the other hand, iterates in the natural order of `TreeSet`.

`editable` has its target class explicitly requested as `ArrayList`, so the `add("water")` call is within that class's contract. The program does not call a mutating method on the result of `Collectors.toList()`, avoiding turning the behavior of one JDK build into a required API assumption.

When `"cocoa"` is added to the source after collection, `all` still retains the accumulated sequence. The result is not a live view of the source list. The element objects inside may still be shared; the third program will test that separately.

### 3.2. Empty streams and null elements

An empty stream still collects into an empty result; there is no need to manually branch and return `null` to represent “no elements”.

The last two results containing `null` demonstrate the behavior of the implementation running the example. In OpenJDK 17 source code, `toList` uses `ArrayList` and `toSet` uses `HashSet` for accumulation. This is an implementation detail, not a promise that the result will always have those exact classes.

If a `null` policy is a mandatory part of the application contract, validate explicitly or choose a target type with a known policy via `toCollection`. Do not rely on a general-purpose collector as if it automatically enforces a business rule to “strip all null elements”.

The [OpenJDK 17 `Collectors` source code](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/stream/Collectors.java) is useful for explaining these observations; application code should still rely on the public contract or an explicitly chosen target.

## 4. toCollection: providing a factory function that meets the contract

### 4.1. The factory must return a new, empty collection

`Supplier<C>` is a functional interface that takes no arguments and returns a `C` when `get()` is called. Specifically, the `toCollection` contract requires the supplied function to return **a new, empty collection** for accumulating data.

This distinction matters: the [`Supplier`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html) interface in general does not require every call to create a distinct object. The new/empty requirement here comes from the [`Collectors.toCollection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)) context, not from the name `Supplier` in isolation.

Two equivalent ways to express the factory:

```java
// Snippet illustrating the factory function, not a standalone program.
Collectors.toCollection(ArrayList::new);
Collectors.toCollection(() -> new ArrayList<String>());
```

Because it needs to accumulate elements and merge intermediate results, the created collection must support the required operations. Returning a collection that disallows adding elements does not fulfill that role, even though the object implements the `Collection` interface.

You should not return a shared collection variable, even if it is empty on the first call. Another collection run may receive the previously accumulated data; when running in parallel, containers that are supposed to be independent could end up pointing to the same object.

### 4.2. The factory can carry target configuration

When a comparator is needed, a lambda can supply the configuration for each new collection:

```java
// Snippet: order is an already-defined Comparator<String>.
Collectors.toCollection(() -> new TreeSet<String>(order));
```

Separate collections can share the same stable comparator. What must be avoided is sharing the result container itself or letting the comparison rules change during collection.

The target type also determines the semantics of the add operation:

- `ArrayList` preserves occurrences and insertion order.
- `LinkedHashSet` deduplicates using `equals/hashCode` and preserves insertion order.
- `TreeSet` determines duplicates by a comparison result of `0` while maintaining comparator order.
- Another type may have its own `null` policy or constraints.

Therefore, `toCollection` accumulating in encounter order does not mean every target type's iterator will traverse in that order. For example, `TreeSet` reflects the comparator's order during iteration. If you pick a set that makes no iteration-order guarantee, the collector does not turn it into an ordered set.

[`LinkedHashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) and [`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) have very different contracts. For `TreeSet`, the comparator should be consistent with `equals` to obey the general `Set` contract; comparing on only a single attribute that is insufficient to distinguish records can cause unintended merging of data.

### 4.3. A collector can be reused, but accumulators must not be shared

A properly configured collector can be reused across independent streams. Each collection operation will obtain its own collection from the factory.

These are two different levels:

- Reusing the description of how to collect.
- Reusing the same collection that holds the result from a previous run.

The first level is useful for encapsulating policy. The second violates the factory requirement of `toCollection`.

Also distinguish a collector from a `Stream`: a stream object can only be used for a single traversal/terminal operation chain by contract. To collect the same source into a list and then into a set, create separate streams from the source, as the first program did.

### 4.4. Program 2: Valid factory, invalid factory, and TreeSet configuration

The `invalidPlan` section intentionally demonstrates misuse using local data and sequential collections. It is not a pattern to use in applications.

File `CollectorFactoryContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorFactoryContractDemo {
    public static void main(String[] args) {
        Collector<String, ?, LinkedHashSet<String>> plan =
                Collectors.toCollection(LinkedHashSet::new);
        LinkedHashSet<String> first = Stream.of("blue", "red", "blue").collect(plan);
        LinkedHashSet<String> second = Stream.of("green").collect(plan);
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("sameResult=" + (first == second));

        Comparator<String> order =
                Comparator.nullsFirst(Comparator.reverseOrder());
        TreeSet<String> custom = Stream.of("tea", null, "juice", "coffee", "tea")
                .collect(Collectors.toCollection(() -> new TreeSet<>(order)));
        System.out.println("customOrder=" + custom);

        try {
            Stream.of("one", null)
                    .collect(Collectors.toCollection(TreeSet::new));
            throw new AssertionError("Natural-order tree accepted null");
        } catch (NullPointerException expected) {
            System.out.println("naturalNull=NullPointerException");
        }

        try {
            Stream.of("one")
                    .collect(Collectors.toCollection(() -> List.<String>of()));
            throw new AssertionError("Read-only accumulator accepted data");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readOnlyFactory=UnsupportedOperationException");
        }

        ArrayList<String> shared = new ArrayList<>();
        Collector<String, ?, ArrayList<String>> invalidPlan =
                Collectors.toCollection(() -> shared);
        ArrayList<String> badFirst = Stream.of("first").collect(invalidPlan);
        ArrayList<String> badSecond = Stream.of("second").collect(invalidPlan);
        ArrayList<String> badEmpty = Stream.<String>empty().collect(invalidPlan);
        System.out.println("badSameResult=" + (badFirst == badSecond));
        System.out.println("badFirstNow=" + badFirst);
        System.out.println("badEmpty=" + badEmpty);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectorFactoryContractDemo.java
java CollectorFactoryContractDemo
```

Output:

```text
first=[blue, red]
second=[green]
sameResult=false
customOrder=[null, tea, juice, coffee]
naturalNull=NullPointerException
readOnlyFactory=UnsupportedOperationException
badSameResult=true
badFirstNow=[first, second]
badEmpty=[first, second]
```

`sameResult=false` confirms that the valid collector creates separate results for the two collections. The first result is not polluted by elements from the subsequent run.

`customOrder` is a set using a comparator that places `null` first and then reverses natural order. Meanwhile, the natural-order tree rejects `null` elements. This policy comes from the target type and comparator, not from `toCollection` filtering data itself.

`readOnlyFactory` fails when attempting to add an element to the list created by `List.of`. An empty input might not expose the element-addition issue, so succeeding on empty data does not prove a factory is suitable for all inputs.

The last three lines show the shared-collection bug clearly: the old result changes after a new collection run, and collecting an empty stream returns a collection that already contains data. You do not need to wait for a random concurrency bug to recognize that the factory violates the contract.

## 5. Parallel collection and result containers

### 5.1. Why can ArrayList be used in a parallel collect?

A collector can describe four coordinated parts:

| Component | Role |
| --- | --- |
| Container provider, `supplier` | Creates the initial accumulation container |
| Accumulator function, `accumulator` | Incorporates an element into the accumulation container |
| Combiner function, `combiner` | Merges intermediate results |
| Finishing step, `finisher` | Transforms the accumulation container into the final result if needed |

With non-concurrent collection that does not share a single container across accumulating threads, the library can split data into chunks, create a separate container for each chunk, and merge them after accumulation finishes. Each individual `ArrayList` does not have to endure concurrent add calls from multiple threads.

The [`Collector` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html) specifies accumulator isolation for non-concurrent collectors. This is the foundation for using parallel collection properly.

This does not grant permission to share the same `ArrayList` externally and let multiple threads mutate it directly. Nor does it make the final list safe for arbitrary concurrent access after it is returned.

### 5.2. Parallel does not mean CONCURRENT

The `Collector.Characteristics.CONCURRENT` characteristic means the accumulator function can be called concurrently on **the same result container**. This is a different guarantee from the library's ability to perform multiple independent accumulations in parallel.

A target collection with thread-safe mechanisms also does not replace checking the collector's characteristics. In the OpenJDK 17 implementation, `toCollection` does not automatically become a `CONCURRENT` collector just because the supplied factory returns a thread-safe queue.

`UNORDERED` is yet another characteristic, stating that encounter order is not guaranteed to be preserved. Do not infer that `UNORDERED` means multiple threads are allowed to arbitrarily mutate the same container.

[`Collector.Characteristics`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.Characteristics.html) defines these attributes. When analyzing a specific implementation, you can inspect `characteristics()`; do not infer an unadvertised collector characteristic from the target class name.

### 5.3. Preserving input order does not require a fixed execution order

An ordered stream can process chunks at different times and then merge the results in the exact encounter order. Thus, `parallel().collect(Collectors.toList())` does not inherently scramble the list order.

The source and preceding operations must still provide the ordering guarantee to preserve. An unordered source, or a step that intentionally drops ordering, will not have its history restored by the collector.

Do not replace collection with a side effect into an external collection, as in the following pattern to avoid:

```java
// Pattern to avoid: shared is not an isolated accumulator of the collector.
List<String> shared = new ArrayList<>();
source.parallelStream().forEach(shared::add);
```

The snippet above risks race conditions when multiple threads add to the same list; it also lacks the ordered merging mechanism of a collection operation. Passing once does not prove that pattern is correct. Use `collect` with an appropriate collector so the library manages the accumulation containers.

### 5.4. Program 3: Parallel results, mutability, and element references

File `ParallelCollectorDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ParallelCollectorDemo {
    public static void main(String[] args) {
        List<Integer> sequential = IntStream.range(0, 5000)
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toList());
        List<Integer> parallel = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toList());
        System.out.println("sameOrderedList=" + sequential.equals(parallel));
        System.out.println("parallelSize=" + parallel.size());

        Set<Integer> unique = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toSet());
        LinkedHashSet<Integer> orderedUnique = IntStream.range(0, 5000)
                .parallel()
                .map(value -> value % 13)
                .boxed()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        System.out.println("parallelSetSize=" + unique.size());
        System.out.println("parallelFirstSeen=" + orderedUnique);

        Collector<Integer, ?, ConcurrentLinkedQueue<Integer>> queueCollector =
                Collectors.toCollection(ConcurrentLinkedQueue::new);
        System.out.println("queueCollectorConcurrent=" +
                queueCollector.characteristics()
                        .contains(Collector.Characteristics.CONCURRENT));

        List<Integer> directList = IntStream.range(0, 3).boxed().toList();
        System.out.println("streamToList=" + directList);
        try {
            directList.add(99);
            throw new AssertionError("Stream.toList result was editable");
        } catch (UnsupportedOperationException expected) {
            System.out.println("streamToListAdd=UnsupportedOperationException");
        }

        List<Integer> editable = IntStream.range(0, 3).boxed()
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add(99);
        System.out.println("explicitEditable=" + editable);

        StringBuilder message = new StringBuilder("status");
        List<StringBuilder> collected = Stream.of(message)
                .collect(Collectors.toList());
        message.append("-updated");
        System.out.println("sameElement=" + (collected.get(0) == message));
        System.out.println("elementAfter=" + collected);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

Output:

```text
sameOrderedList=true
parallelSize=5000
parallelSetSize=13
parallelFirstSeen=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
queueCollectorConcurrent=false
streamToList=[0, 1, 2]
streamToListAdd=UnsupportedOperationException
explicitEditable=[0, 1, 2, 99]
sameElement=true
elementAfter=[status-updated]
```

`sameOrderedList=true` checks both the order and occurrence counts of all 5,000 elements. `parallelSetSize=13` checks the deduplicated result for values from `0` to `12`. `parallelFirstSeen` also preserves first-encounter order via a `LinkedHashSet` target.

`queueCollectorConcurrent=false` is an observation of the collector's characteristics created in the example. The key takeaway is that the target collection and the collector's accumulation mechanism have separate contracts; choosing a thread-safe queue does not turn every kind of collection operation into concurrent accumulation into a single container.

The `streamToListAdd` section will be contrasted with `Collectors.toList` in the next section. The `sameElement` and `elementAfter` sections show another boundary: creating a new result collection does not automatically deep-copy the element objects.

## 6. Mutability is a separate contract of the result

In the Collector examples in sections 3–5, `Collectors.toList()` creates a `List` but **does not guarantee mutability or a specific implementation class**. `Collectors.toCollection(ArrayList::new)` actively selects an `ArrayList` that supports adding, removing, and replacing elements. Meanwhile, `Stream.toList()` (Java 16+) is a direct terminal operation that guarantees an **unmodifiable** result. These three forms are not equivalent simply because they all produce a `List`.

| Need | Choice |
| --- | --- |
| Collect elements into a List without needing a specific class | `collect(Collectors.toList())` |
| Collect into a List with clearly defined add or edit capabilities | `collect(Collectors.toCollection(ArrayList::new))` |
| Only need an unmodifiable result list, may still contain null | `stream.toList()` |
| Need an unmodifiable result that rejects null | `collect(Collectors.toUnmodifiableList())` |

You can also accumulate into a new `ArrayList` and then use `collectingAndThen` with `Collections.unmodifiableList` to return a read-only wrapper. Do not use the read-only wrapper itself as the accumulator in `toCollection`, because the accumulator still needs to add elements. When a collector runs in parallel, the library may create multiple containers and merge them; the final result does not automatically become safe for arbitrary concurrent mutations later.

As for the element objects themselves, they may still share references with the source. For example, `StringBuilder` in Program 3 mutates its state without changing any slot in the `List`. When an independent snapshot at the data level is needed, new element instances must be created appropriately. The article *Stream.toList, collect, and mutability guarantee boundaries* analyzes `set`, `sort`, null policies, type conversions, and these boundaries in detail.

## 7. Choosing and using collectors for specific requirements

### 7.1. Quick selection table

| Requirement | Appropriate choice |
| --- | --- |
| Keep all occurrences, need a `List`, no specific class required | `Collectors.toList()` |
| Only need distinct values, no order or specific class required | `Collectors.toSet()` |
| Definitely need a mutable list per the `ArrayList` contract | `Collectors.toCollection(ArrayList::new)` |
| Deduplicate and preserve encounter order of an ordered source | `Collectors.toCollection(LinkedHashSet::new)` |
| Need a set maintaining a custom comparator | `toCollection` with a factory creating a new `TreeSet` with that comparator |
| Need a read-only result | Choose an API/finishing step with a read-only guarantee and the right `null` policy |
| Need to keep duplicate data and sort it | Keep a sequence type and use sorting rules; do not replace with a set |

A requirement like “distinct” must be tied to an identity rule. For a standard hash set, `equals/hashCode` must obey their contract. For a tree, a comparison result of `0` determines merging. You cannot swap set types and assume every element type retains the same notion of equality.

If objects are equal according to `equals` but differ in other state, `toSet` does not provide a business policy such as “always keep the exact first record” to pick the representative state. Define that policy explicitly and use a pipeline with the appropriate guarantees.

### 7.2. Distinguishing data filtering from data storage

Choosing `ArrayList` or `TreeSet` does not replace input validation. These questions must be defined separately:

- Is `null` valid data, something to be filtered out, or something that must fail the operation?
- Do duplicate occurrences carry distinct meaning, or may they be merged?
- Do you need to preserve input order, sorted order, or no order?
- Can the target type hold and compare all incoming values?

If business logic chooses to drop `null` elements, perform an explicit filter step. If business logic chooses to reject missing data, that is a different rule. Do not lump both behaviors together as “sanitization” and let the collection type decide by accident.

Similarly, `toSet` does not count frequencies. Once equal occurrences are merged, you cannot deduce from the set alone how many times each value appeared.

### 7.3. Be careful with streams and external state

Factories, mapping functions, and rules used during collection must satisfy their respective contracts. Do not modify the source while the stream is traversing it, and do not use an external collection as a shared destination instead of library-managed accumulators.

An ordinary `ArrayList` source can be read by a parallel stream when used under the right conditions—without being modified during traversal. There is no need to turn every source into a concurrent structure just because `parallel()` is present. What must be controlled is how the source is accessed and how accumulation containers are managed.

After collection, if the result is handed to multiple threads for concurrent modification, an appropriate access policy is needed for that result. The success of a parallel `collect` does not prove the returned list inherently has all concurrency-safety properties for the rest of the application.

The [`Stream` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) requires processing functions to be non-interfering with the source and explains the single-use traversal of a stream.

### 7.4. Cost of materializing results

These collectors create a collection holding the results, not a lazy view that continues reading from the source later. For a list holding `n` elements, space is needed for the corresponding references. For a set, the number of retained values also depends on the number of distinct elements and the target's policy.

An infinite result stream cannot be fully collected into a finite collection. You must design appropriate bounds or consumption mechanisms instead of treating `collect` as a self-terminating operation.

Parallel execution also incurs the cost of creating separate containers and merging results. `parallel()` does not automatically guarantee faster execution. Pre-allocating a very large capacity in the `toCollection` factory can also cause waste if that factory is invoked for many data partitions.

Do not rely on the assumption that “the factory is called only once” for capacity calculations, business logging, or sharing a buffer. When performance matters, benchmark on real data and pipelines while adhering to the factory contract.

### 7.5. Testing results against the guaranteed properties

When testing a collection operation:

- For an ordered list, verify both the sequence and occurrence counts.
- For `toSet`, verify the set of values; do not hardcode an order the API does not promise.
- For an explicit target, verify the capabilities that target type is expected to provide.
- Test empty inputs, duplicate data, and `null` policy as required.
- If reusing a collector, verify that results across collection runs are not unintentionally shared.
- If using parallelism, compare results according to the contract, not the order in which tasks complete.

Do not use a type cast, an internal class name, or a successful mutation on one JDK to substitute for a published API guarantee.

## 8. Practice and explanations

### Exercise 1: A list with duplicates that must be preserved

Given an ordered source `[tea, coffee, tea, juice]`. Extract a list that keeps all four positions and supports adding more elements later.

**Key points to explain:** keeping a sequence type satisfies the occurrence-count requirement; choosing `toCollection(ArrayList::new)` additionally expresses mutability. `toSet` loses one occurrence of `tea`; `Collectors.toList` is insufficient to guarantee a specific mutable class.

### Exercise 2: Distinct tags, preserving encounter order

Given an ordered stream, merge tags that are equal per `equals` while preserving first-seen order.

**Key points to explain:** `toCollection(LinkedHashSet::new)` provides a target with the matching contract. `toSet` does not guarantee order. If the source has already lost the required order, choosing an ordered target class cannot recover the lost history.

### Exercise 3: A factory returning a shared collection variable

A factory returns a `shared` variable. To “fix” it, the author calls `clear()` on it before each return.

**Key points to explain:** clearing data does not create a distinct object. Sequential collections can still end up holding the same collection; when multiple accumulators exist, a `clear()` call can even wipe another partition's data. A new, empty collection must be allocated per the contract instead of reusing a shared object.

### Exercise 4: Using a read-only collection as an accumulator

An empty input running through `toCollection(() -> List.of())` appears to succeed without error. Later, the same code fails on non-empty input.

**Key points to explain:** the empty case never executes the element-addition path. The supplied collection does not support the required accumulation role. If the final result must be read-only, use a collection that supports accumulation and then apply an appropriate finishing step.

### Exercise 5: Switching from collect(toList()) to Stream.toList()

Downstream code adds elements to the result. After a syntax simplification, the add operation throws `UnsupportedOperationException`.

**Key points to explain:** the two APIs have different contracts; `Stream.toList` is unmodifiable. The need for mutability should be stated explicitly using an appropriate target type, rather than relying on the current version of `Collectors.toList` happening to allow mutation.

### Exercise 6: Parallel collection using an external list

An author uses `parallelStream().forEach(shared::add)` where `shared` is an `ArrayList`, and observes that one run produces the full element count.

**Key points to explain:** this lacks a collector's accumulator isolation and merging mechanism; a single successful run does not prove safety. Using `collect` properly lets the library manage separate results, after which you can evaluate the list's access policy once collection finishes.

When reading a collection call, identify **the result type, duplicate handling, ordering guarantee, mutability, and where each accumulator is created**. Those details explain why three syntactically similar collectors serve different needs.
