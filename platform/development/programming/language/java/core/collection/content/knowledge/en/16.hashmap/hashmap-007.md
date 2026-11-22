# Why Observed Iteration Order Is Not a Contract

## 1. Seeing an order does not mean you can rely on it

When printing a small `HashMap`, you may see keys appear in a very familiar order: ascending order, matching insertion order, or repeating identically across multiple runs. From there, it is easy to write additional code assuming that the first element iterated is the first element added.

What you observe is a real result of that run. However, a repeatable result does not automatically become an API promise.

`HashMap` makes no guarantees as to the iteration order of the map; in particular, it does not guarantee that the order will remain constant over time. Application code must be correct for every order permitted by the contract, not just the order that happens to appear in a test dataset. [HashMap Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

For example, a requirement to “select the earliest entered record” must not be solved by taking the first element of `map.entrySet()` if the map is a `HashMap` and the entry timestamp is not stored separately. Similarly, exporting a report with a fixed order requires a sorting rule or a structure that preserves that order.

This lesson explains why the order can look stable, how to construct a counterexample yourself, and how to design iteration and testing according to actual requirements.

## 2. Three levels of information: observation, implementation, and contract

| Level of information | Example | What can it be used for? |
| --- | --- | --- |
| Observation in a single run | “I saw [0, 16, 1]” | Recording empirical data |
| Implementation explanation | “These keys are in these buckets in the OpenJDK version under study” | Understanding why the observation occurred |
| Public API guarantee | “This Map type iterates in insertion order” | Designing required behavior and testing against the contract |

An accurate internal explanation still does not promote itself into a public guarantee. You can read the source code of a version, accurately predict the order for a given dataset, and still have no right to demand that every future `HashMap` version preserve that order.

Conversely, a public ordering guarantee is something you can build into an application contract once you have chosen the right structure and configuration.

### “Unspecified” does not mean “randomized every time”

`HashMap` has no obligation to shuffle its order on every iteration or every run. If the input, update history, and implementation remain unchanged, frequently seeing the same order does not contradict the fact that the API guarantees no order.

Do not write tests requiring two `HashMap` iterations to be different just to prove it has no ordering contract. Two runs can be identical. Equally, do not require them to be identical just because you have observed them match many times.

The key point to remember is the lack of a guarantee, not a mandatory randomization algorithm.

## 3. Why does a small HashMap sometimes look sorted?

`HashMap` organizes mappings for key-based lookup using hash codes and buckets. The observed iteration order is influenced by how the implementation traverses the table and the nodes within buckets, not by a public rule to “sort by key” or “remember insertion order.”

In OpenJDK 17, the iterator traverses the table slots and the nodes it encounters. That can make a small set of integer keys appear in a predictable pattern. [HashMap Source Code, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

Suppose we add keys in the order:

~~~text
0, 16, 1
~~~

In the example model at capacity 16, `0` and `16` are routed to the same bucket, while `1` is in another bucket. With a larger capacity, `16` can land in a slot separate from `0`. The table traversal path can then produce a different order.

Therefore, the same three mappings with two different initial capacity configurations can produce:

~~~text
An observation on the first Map: [0, 16, 1]
An observation on the second Map: [0, 1, 16]
~~~

The second order looking ascending does not prove `HashMap` is a sorted map. It is a result of the data and the table structure under consideration. The first order also does not prove `HashMap` preserves insertion order in general; it is merely a coincidence with the insertion history in the example.

Factors that can affect an observation include capacity, collision handling, table resizes, insertion/removal history, and implementation version details. Not every factor needs to change the order in every case; as long as the API does not promise an order, code must not depend on it.

### Adding and then removing can also leave a different history

Two `Map`s with the same current mappings do not necessarily have the same internal structure. A `Map` that grew and then had entries removed may still have a different table than a `Map` that was just created small.

This is why a test suite that only creates a fresh `Map` with a few elements does not fully represent a long-lived `Map` in an application.

Do not treat the difference observed after an update history as something every `HashMap` must exhibit. The goal is to see what variations are permitted without violating `Map` semantics.

## 4. Two equal Maps can still iterate differently

A `Map` describes key–value relationships. Under the standard `Map.equals` contract, two `Map`s are equal when they represent the same mappings, without needing the same iteration order. [Map.equals Contract, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

For example, both `Map`s contain:

~~~text
0  -> zero
16 -> sixteen
1  -> one
~~~

One iteration yields `[0, 16, 1]`, while the other yields `[0, 1, 16]`. It can still be true that:

~~~java
first.equals(second) == true
~~~

While:

~~~java
new ArrayList<>(first.keySet())
        .equals(new ArrayList<>(second.keySet())) == false
~~~

The two expressions are comparing objects with different contracts:

- Comparing `Map`s: asks whether they have the same mappings.
- Comparing `List`s: asks whether they have the same elements at the same positions.

Converting to a `List` brings the observed order into the data being compared. It does not prove either `Map` holds the wrong mappings.

If you need to verify computation results that have no ordering requirement, comparing `Map`s directly is usually more appropriate than comparing `toString()` strings or comparing `List`s built from an arbitrary traversal.

If there is an ordering requirement, you must test that requirement separately after choosing a way to produce the order according to the contract.

## 5. A Java 17+ program to observe for yourself

The program uses non-null `Integer` keys and simple string values. It creates two `HashMap`s with the same insertion history of three mappings but different requested capacities, then performs a growth-and-removal history on one `Map`.

The lines labeled `observed` record the **observed order in that run**. Those lines may differ on another implementation or version while the program still uses `HashMap` according to its contract.

The `check` calls do not require a specific `HashMap` order. They only verify the mappings and the orders explicitly established via `LinkedHashMap`, `TreeMap`, or `sorted`.

Save as `HashMapOrderDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class HashMapOrderDemo {
    static void seed(Map<Integer, String> map) {
        map.put(0, "zero");
        map.put(16, "sixteen");
        map.put(1, "one");
    }

    static List<Integer> observedKeys(Map<Integer, String> map) {
        return new ArrayList<>(map.keySet());
    }

    static List<String> sortedReport(Map<Integer, String> source) {
        Map<Integer, String> sorted = new TreeMap<>(source);
        List<String> result = new ArrayList<>();
        for (Map.Entry<Integer, String> entry : sorted.entrySet()) {
            result.add(entry.getKey() + "=" + entry.getValue());
        }
        return result;
    }

    static List<Integer> observedOriginalKeys(Map<Integer, String> map) {
        Set<Integer> original = Set.of(0, 16, 1);
        List<Integer> result = new ArrayList<>();
        for (Integer key : map.keySet()) {
            if (original.contains(key)) {
                result.add(key);
            }
        }
        return result;
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Wrong mapping or explicit order");
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> small = new HashMap<>(16);
        Map<Integer, String> large = new HashMap<>(64);
        seed(small);
        seed(large);

        List<Integer> observedSmall = observedKeys(small);
        List<Integer> observedLarge = observedKeys(large);
        System.out.println("observed small=" + observedSmall);
        System.out.println("observed large=" + observedLarge);
        System.out.println("same mappings=" + small.equals(large));
        System.out.println("same observed list="
                + observedSmall.equals(observedLarge));
        System.out.println("sorted small=" + sortedReport(small));
        System.out.println("sorted large=" + sortedReport(large));

        List<Integer> captured = List.copyOf(observedSmall);
        for (int key = 2; key <= 11; key++) {
            small.put(key, "extra-" + key);
        }
        System.out.println("observed original keys after growth="
                + observedOriginalKeys(small));
        for (int key = 2; key <= 11; key++) {
            small.remove(key);
        }
        System.out.println("same mappings after removing extras="
                + small.equals(large));
        System.out.println("captured earlier list=" + captured);
        System.out.println("fresh observed list=" + observedKeys(small));

        Map<Integer, String> linked = new LinkedHashMap<>();
        seed(linked);
        System.out.println("linked insertion order=" + observedKeys(linked));
        linked.put(16, "updated-sixteen");
        System.out.println("linked after existing put=" + observedKeys(linked));
        linked.remove(0);
        linked.put(0, "reinserted-zero");
        System.out.println("linked after remove and put=" + observedKeys(linked));

        Map<Integer, String> linkedCopy = new LinkedHashMap<>(large);
        System.out.println("linked copy of large=" + observedKeys(linkedCopy));
        Map<Integer, String> tree = new TreeMap<>(large);
        System.out.println("tree key order=" + observedKeys(tree));

        List<Integer> sortedKeys = small.keySet().stream().sorted().toList();
        System.out.println("explicit sorted stream=" + sortedKeys);
        Map<Integer, String> expected = Map.of(
                0, "zero", 16, "sixteen", 1, "one");
        check(small.equals(expected));
        check(large.equals(expected));
        check(sortedReport(small).equals(sortedReport(large)));
        check(observedKeys(linked).equals(List.of(16, 1, 0)));
        check(observedKeys(tree).equals(List.of(0, 1, 16)));
        check(sortedKeys.equals(List.of(0, 1, 16)));
        System.out.println("contract checks=PASS");
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 HashMapOrderDemo.java
java HashMapOrderDemo
~~~

Use JDK 17 or newer supporting target release 17. The code uses Java 17–compatible syntax and APIs.

Exact stdout from the verification run:

~~~text
observed small=[0, 16, 1]
observed large=[0, 1, 16]
same mappings=true
same observed list=false
sorted small=[0=zero, 1=one, 16=sixteen]
sorted large=[0=zero, 1=one, 16=sixteen]
observed original keys after growth=[0, 1, 16]
same mappings after removing extras=true
captured earlier list=[0, 16, 1]
fresh observed list=[0, 1, 16]
linked insertion order=[0, 16, 1]
linked after existing put=[0, 16, 1]
linked after remove and put=[16, 1, 0]
linked copy of large=[0, 1, 16]
tree key order=[0, 1, 16]
explicit sorted stream=[0, 1, 16]
contract checks=PASS
~~~

Do not turn the `HashMap` observation lines into mandatory strings for every machine. The point of this lesson is to distinguish these empirical records from API guarantees. The `contract checks=PASS` line depends on the contract assertions written in `check`, not on the first two `observed` lines being different.

### Results to compare

`same mappings=true` and `same observed list=false` appear together, demonstrating that differing orders do not break mapping equality.

The two `sorted` lines are identical because the report method uses `TreeMap` with natural key ordering. The order has become an intentional processing step, not a guess based on `HashMap`.

After adding extra keys and removing them, the small `Map` once again has the same mappings as the large `Map`. In that run, the newly observed key list differs from the previously captured list. Returning to the same data does not rewind the internal structural history.

The `captured` list still holds the elements and order that were captured. It is a separate `List`; keeping an observation in a `List` does not force the source `HashMap` to iterate in that order later.

The `LinkedHashMap`, `TreeMap`, and sorted stream lines have a different meaning: their order comes from explicitly chosen mechanisms. They will be used to design stable behavior in the following sections.

## 6. When order is needed, choose the right guarantee

### Preserve insertion order with default LinkedHashMap

If the order provided by the user or data source is part of the requirement, you can use:

~~~java
Map<Integer, String> map = new LinkedHashMap<>();
map.put(0, "zero");
map.put(16, "sixteen");
map.put(1, "one");
~~~

A default `LinkedHashMap` iterates in the insertion order of its keys. Re-putting an existing key replaces its value without moving that key to the end. Removing a key and adding it back creates a new insertion, so the key appears at the new insertion position. [LinkedHashMap Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

In the program:

~~~text
Insert 0, 16, 1:    [0, 16, 1]
Re-put 16:          [0, 16, 1]
Remove then put 0:  [16, 1, 0]
~~~

These are sequential operations on a default `LinkedHashMap`. This class also has an access-order mode selected via another constructor; that mode has its own rules and should not be loosely described as “always preserving insertion order.”

### Sort by key with TreeMap

If the requirement is to always iterate in ascending key order or according to a defined `Comparator`:

~~~java
Map<Integer, String> sorted = new TreeMap<>(source);
~~~

With the non-null `Integer` keys in the example, `TreeMap` sorts by natural numeric order, so the result is `0, 1, 16`. This order is independent of the order in which the three keys were inserted.

`TreeMap` provides ordering by the natural order of its keys or by a chosen `Comparator`. It does not sort by value, and it is not synonymous with insertion order. [TreeMap Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

When using other keys or `Comparator`s, ensure that keys are mutually comparable and that the comparison relation aligns with key identity. Do not replace a `HashMap` with a `TreeMap` using a comparator that treats distinct keys as tied and assume all mappings will still be preserved.

A `TreeMap` with natural ordering is also not a drop-in choice for copying any `HashMap` with `null` keys without adjustment. The full example intentionally uses non-null `Integer` keys to focus on ordering.

### Keep HashMap for lookup, sort on export

If you primarily need fast lookup and only require an ordered report at the data-export boundary, you can keep `HashMap` and produce a sorted result:

~~~java
List<Integer> keys = map.keySet().stream()
        .sorted()
        .toList();
~~~

Only the resulting `List` is created in ascending key order. The source `Map` is not turned into a sorted `Map`. If you need the entries as well, build the report from the entries or use a sorted `Map` like `sortedReport` in the program.

Sorting incurs cost proportional to the number of elements and memory for the result. That is part of the work to account for when the requirement genuinely demands a stable sequence.


## 7. Copying can preserve an observation without restoring history

### What order does new LinkedHashMap<>(hashMap) preserve?

Consider:

~~~java
Map<Integer, String> copy = new LinkedHashMap<>(hashMap);
~~~

The new `LinkedHashMap` receives mappings in the order the source is traversed during copying. From then on, the new map preserves its own insertion order.

That does not restore the order in which the user originally inserted keys into the `HashMap` earlier. If the `HashMap` has already dropped that ordering information from your data contract, a later copy operation cannot deduce the history back.

In the program, `seed` inserts `0, 16, 1`, but the `large` `Map` is observed as `0, 1, 16`. Copying `large` into a `LinkedHashMap` yields `0, 1, 16` in that run. That is the order the new `LinkedHashMap` received, not the restored `seed` history.

If you need the original input order, preserve it right at the point of intake: use an appropriately ordered structure or store the needed position/timestamp information. Do not pass data through a `HashMap` and expect to reconstruct an unrecorded order afterward.

### A List captures a single traversal

~~~java
List<Integer> snapshot = new ArrayList<>(hashMap.keySet());
~~~

A `List` has specific element positions. Traversals of that `List` will follow the stored positions as long as the `List` itself is not modified.

However, creating a new `List` from the `HashMap` at a different time can yield a different observation. “This snapshot has an order” is different from “the source has a guaranteed order.”

`List.copyOf` in the program uses non-null keys and creates a structurally unmodifiable `List`. It preserves the elements in the same order as the observed list passed to it, without binding the `HashMap` to replay that order later.

### Map.copyOf and read-only do not mean order-preserving

An unmodifiable `Map` still needs its ordering contract examined separately. Do not treat the “unmodifiable” property as proof that it preserves the source's insertion order.

Similarly, wrapping a `Map` in a read-only view can preserve visibility into the source data, but it does not create an order that the source never promised. Ordering, mutability, and independence from the source are properties that must be chosen separately.

| Desired outcome | Decision required |
| --- | --- |
| Cannot be modified through the returned object | Choose an appropriate wrapper or result type |
| Mappings do not change when the source changes | Choose an appropriate copy |
| Has a stable display order | Choose an explicit ordering rule |
| Preserves exact input history | Store the history or use a history-preserving structure from the start |

One way of constructing data may satisfy one row without satisfying the others. That is why variable names like `readOnly` or `snapshot` are not enough to describe the contract.

## 8. Streams do not turn observed order into business order

### forEach and forEachOrdered

`forEachOrdered` performs an action in the encounter order of the stream if the stream has a defined encounter order. The word “Ordered” does not mean sorting keys automatically, nor does it mean deducing the insertion history of a `HashMap`. [Stream.forEachOrdered Documentation, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

Therefore:

~~~java
hashMap.keySet().stream().forEachOrdered(System.out::println);
~~~

is not a way to require `HashMap` to output keys in insertion order or ascending order. It states no business rule for producing that order.

If you need ascending keys, you must create the order explicitly:

~~~java
hashMap.keySet().stream()
        .sorted()
        .forEachOrdered(System.out::println);
~~~

This example assumes keys are comparable by natural order and contain no `null` unsupported by the comparator. Calling `sorted` adds a rule that the `HashMap` source does not have.

With parallel processing, `forEach` is also not a way to make printing side effects follow a chosen source order. You must distinguish the order of result data from how tasks are executed.

### findFirst and limit do not mean “earliest” or “smallest”

An element visited first by a `HashMap` is not by default:

- The smallest key.
- The first mapping added.
- The record with the earliest timestamp.
- The item with the highest priority.

`findFirst` or `limit` on a source lacking the necessary ordering rule cannot supply those meanings on its own. If you need the element with the earliest timestamp, compare the timestamp field; if you need the smallest key, compute it by key order or use a structure with the appropriate contract.

### Sorting by one criterion while ties remain

Suppose a report must be sorted by descending score. Two items both having a score of 90 still have no relative order decided by score alone.

If the output must be completely reproducible, add a secondary criterion, such as ascending item ID. A stable sorting algorithm can preserve the input order among tied elements; if the input comes from a `HashMap` with an unguaranteed order, that still does not produce a complete business order.

In the program, the `Integer` keys are distinct and sorted by natural key order, so no such ambiguity exists between two different keys. With other key types or comparators, you must review the completeness of the comparison rule.

## 9. Testing the right semantics

### No ordering requirement: compare mappings

For a method returning a `Map`, if the requirement is to return the right key–value pairs, you can test:

~~~java
Map<Integer, String> expected = Map.of(
        0, "zero",
        16, "sixteen",
        1, "one");

if (!actual.equals(expected)) {
    throw new AssertionError("Wrong mappings");
}
~~~

This snippet is placed in a context where `actual` already exists. Do not treat the argument order of `Map.of` as a requirement on the iteration order of `expected`.

Comparing a collection of values alone may not be enough: two keys with swapped values can still produce the same value multiset. Comparing `Map`s ensures the key–value associations are verified.

Also do not compare `actual.toString()` against a string written in an order you happened to observe. If the string is only meant to check `Map` data, that check introduces an out-of-contract requirement.

### With an ordering requirement: test after establishing the right order

If a method returns a report in ascending key order, checking the resulting `List` by position is appropriate:

~~~java
List<Integer> expectedOrder = List.of(0, 1, 16);
if (!sortedKeys.equals(expectedOrder)) {
    throw new AssertionError("Wrong key order");
}
~~~

In this case, you should specify which rule produces `sortedKeys`, such as `sorted` or `TreeMap`. Do not alter the test to ignore order if the product requirement itself demands a clear order.

For a feature that preserves input order, test the sequence of input events alongside the structure that preserves that order. If data passes through an unordered source, decide where the rule should be applied rather than blaming `HashMap`.

### Use data that exposes hidden assumptions

Small datasets with keys `1, 2, 3` easily mask the bug “`HashMap` sorts ascending automatically.” A worthwhile check should include keys that share a bucket in one configuration, different insertion histories, or a source that grew and then had entries removed.

What you should assert is that the algorithm's result remains correct under those histories. You do not need to assert that every pair of test histories must produce different iteration orders, because differing is not something `HashMap` is required to provide.

The full program follows this principle: it prints observations, but its functional checks do not require two `HashMap`s to have different orders.

### Tests cannot fix a missing contract

A hundred passing runs can help catch some bugs, but they cannot turn behavior not guaranteed by the API into guaranteed behavior. When a feature truly depends on order, express that decision in the feature's data structure or algorithm.

Pinning a JDK version helps reproduce an environment, but you should still distinguish an intentional dependency on an implementation from a public library contract. If an experiment relies on implementation details, document the conditions of the experiment clearly.

## 10. Applying at data export boundaries and choosing structures

### Reports and user interfaces

If a list of columns, items, or display groups needs a specific order, state it explicitly: “by ID,” “by name,” “by timestamp,” or “by entry position.” Those phrases tell you which comparator to choose, which field to store, or which structure to use.

“Display like when I print the Map” is not a durable specification. Changing capacity for performance tuning should not alter the business sequence on screen.

### Text, caches, and output comparison

Two equal `Map`s can have display strings in different orders. If text output is diffed line by line, used as input to a hash function, or used as a cache key, the order must be normalized according to a published rule.

Sorting keys is part of normalization, but it does not solve everything on its own: if values contain nested `Map`s, there is still the inner layer's order; if a text format is used, there are still character and value representation rules.

The `sortedReport` method in the example is a human-readable report for specific `Integer`/`String` data, not a general-purpose canonical encoding format. Do not treat `key + "=" + value` concatenation as a universal format for arbitrary data that might contain delimiters.

### Costs and responsibilities

| Primary requirement | Approach |
| --- | --- |
| Key-based lookup, result independent of order | `HashMap` and an algorithm that does not rely on traversal position |
| Iterate in insertion order | Default `LinkedHashMap`, receiving data in the order to be preserved |
| Iterate by key | `TreeMap` with natural order or an appropriate comparator |
| Only certain exports need ordering | Keep the lookup structure, sort the result at export time |
| Need a priority order different from insertion and key order | Store priority information and use a structure/algorithm expressing that rule |

The choices differ in memory and operation costs. `LinkedHashMap` maintains additional ordering links; `TreeMap` performs operations over a tree structure; sorting a report requires building the output and performing comparisons. Changing `Map` types should come from requirements, not merely to make a string test happen to pass.

### Order does not replace other guarantees

Having a clear order does not automatically make data thread-safe. A fail-fast iterator does not create a consistent snapshot. A read-only `Map` is not automatically an independent copy.

In this lesson, all operations occur sequentially and sources are kept stable during each traversal. If an application has concurrent updates, it needs appropriate read/update mechanisms beyond ordering decisions.

## 11. Exercises and solutions

### Exercise 1 — Same order across multiple runs

You insert `3, 1, 2` into a `HashMap` and always observe `[1, 2, 3]` on your current machine. Can you specify that the method returns keys in ascending order without adding any extra processing?

**Solution:** No. The observation may match the current bucket placement, but `HashMap` has no ascending-order contract. If the method must guarantee ascending order, use a key-sorted structure or sort the result explicitly.

### Exercise 2 — Does “not guaranteed” mean it must always change?

A test asserts that two creations of a `HashMap` must yield two different orders because “`HashMap` has no order.” Where is the test wrong?

**Solution:** Not guaranteeing an order does not mean mandatory randomization or mandatory differences. Two runs can be identical. The right requirement is that the algorithm must not depend on a specific order that the contract does not provide.

### Exercise 3 — Equal Maps, different Lists

Two `Map`s have the same key–value pairs, but `List`s built from `keySet` have different orders. `Map.equals` returns `true`, while `List.equals` returns `false`. Is there a contradiction?

**Solution:** No. `Map` compares for the same mappings; `List` compares elements by position. Converting to a `List` introduced an observed order into the object under test.

### Exercise 4 — Copying into a LinkedHashMap

Data is inserted into a `HashMap` in the order A, B, C, but a traversal sees C, A, B. Does copying it into a `LinkedHashMap` restore A, B, C?

**Solution:** No. The new `Map` receives entries in the currently traversed order, C, A, B, in that run and keeps its own insertion history. To preserve A, B, C, you must record the order at the source or use an appropriate structure from the beginning.

### Exercise 5 — Re-putting, removing, and re-adding

A default `LinkedHashMap` currently holds A, B, C. What order does re-putting B with a new value give? What about removing A and then adding A back?

**Solution:** Re-putting B keeps A, B, C. Removing and then adding A gives B, C, A. This is the contract of the chosen insertion-order mode, not something inferred from `HashMap`.

### Exercise 6 — Does forEachOrdered sort?

Can you replace a `for-each` loop over a `HashMap` with `stream.forEachOrdered` to guarantee printing in insertion order?

**Solution:** No. `forEachOrdered` does not create insertion history or sort keys for a source that lacks that guarantee. Choose a source that preserves the needed order, or apply a rule such as `sorted` before output.

### Exercise 7 — Sorting only by score

A report takes items from a `HashMap` and sorts them by descending score. Two items have the same score, with no secondary criterion. Is the entire output guaranteed to always have the same order?

**Solution:** Not yet. The relative order of the two tied items can still depend on an unguaranteed input order. If full reproducibility is required, add an appropriate secondary criterion, such as ascending ID.

### Exercise 8 — Testing the right requirement

A method is only required to return the right ID–name `Map`. The test currently compares `toString` against a string written in insertion order. How should you fix it? What if the real requirement is to return a report ordered by name?

**Solution:** In the first case, compare the `Map` directly against the expected mappings without imposing an unnecessary order. In the second case, express the sorting by name in the report-building code, specify how to handle duplicate names if needed, and then test the `List` or output text against that exact order.

An observed order is empirical data for explaining an implementation. An order used as a requirement must have a clear source of guarantee: the structure's contract or a processing step designed for that goal.
