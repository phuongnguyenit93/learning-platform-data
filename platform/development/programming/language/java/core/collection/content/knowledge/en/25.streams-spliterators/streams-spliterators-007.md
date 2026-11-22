# Collectors.toMap: Duplicate Keys, Merge Functions, and Target Map Types

## 1. Creating a Map Is a Decision on How to Aggregate Data

Suppose a Stream emits sales rows:

~~~text
code B, quantity 2
code A, quantity 3
code B, quantity 5
code C, quantity 4
code A, quantity 1
~~~

We want to look up entries by code. However, a Map holds at most one value per key, while codes `B` and `A` appear multiple times. Therefore, turning rows into a Map is not merely changing how data is stored. You must decide how rows with the same code are handled.

Several outcomes can be valid, depending on the requirements:

| Rule | Value of B | Value of A |
| --- | --- | --- |
| Keep the first row | `2` | `3` |
| Keep the last row | `5` | `1` |
| Sum the quantities | `7` | `4` |
| Pick the largest quantity | `5` | `3` |
| Keep all quantities as a list | `[2, 5]` | `[3, 1]` |
| Forbid duplicate codes | Throw error | Throw error |

`Collectors.toMap` provides a way to create a collector that aggregates elements into a Map. Two mapping functions determine the key and value; other overloads add a merge function for duplicate keys and a factory to create the target Map. [Java SE 17 — Collectors.toMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toMap(java.util.function.Function,java.util.function.Function)).

This lesson focuses on three decisions: **what key is produced, how values with the same key are merged, and which Map will hold the result**. Understanding these three parts helps avoid both losing data and assuming a collect operation succeeded as intended.

## 2. Reading the Three Overloads by Level of Control

Shorthand signatures:

~~~java
toMap(keyMapper, valueMapper)

toMap(keyMapper, valueMapper, mergeFunction)

toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

These illustrate the overloads, not standalone calls with all variables in scope.

| Parameter | Role |
| --- | --- |
| `keyMapper` | Turns an input element into key `K` |
| `valueMapper` | Turns that element into value `U` |
| `mergeFunction` | Takes two `U` values with the same key and decides the resulting `U` value |
| `mapFactory` | Creates a new, empty Map suitable for the collector to insert/merge data |

With the Java 17 model:

~~~java
record Sale(String code, int quantity) { }
~~~

you can use `Sale::code` to produce the key and `Sale::quantity` to produce the value. `quantity` is an `int`, but it is boxed into `Integer` when used as a value in `Map<String, Integer>`.

Distinguish the terminal operation from the collector:

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                LinkedHashMap::new));
~~~

`Collectors.toMap(...)` describes how to collect. `collect(...)` is the terminal operation that executes the Stream pass. The snippet above assumes `rows` is a list of `Sale` with appropriate imports; the complete program later provides everything needed to run.

## 3. The Two-Argument Form: Forbidding Duplicate Keys

~~~java
Map<String, Integer> byCode = rows.stream()
        .collect(Collectors.toMap(Sale::code, Sale::quantity));
~~~

This form is suitable when each mapped key must appear uniquely. If two inputs produce the same key, the collector throws `IllegalStateException`. It does not default to keeping the first, keeping the last, or summing.

### 3.1. Equal Values Still Count as a Duplicate Key

Two rows `A=1` and `A=1` are still two inputs with the same key. There is no default rule saying "accept if the values are equal."

If the application genuinely wants to accept two equivalent records while failing when their contents differ, you must write a merge function expressing that policy. You cannot infer such a policy from using the two-argument overload.

### 3.2. Duplicates Are Checked on the Key After keyMapper

Source strings can differ:

~~~text
"Java"
" java "
"JAVA"
~~~

However, `trim().toLowerCase(Locale.ROOT)` produces the same key `java`. Duplicates occur at the **mapped key result**, not necessarily in the original input objects.

Normalization policies must be applied consistently. If a key represents a case-insensitive code, you can normalize the code according to the chosen rule and then handle duplicates on the normalized form. Do not arbitrarily strip whitespace or change letter case if business data treats those differences as meaningful.

### 3.3. distinct on Rows Does Not Guarantee Unique Keys

With `record Sale(String code, int quantity)`, `Sale("B", 2)` and `Sale("B", 5)` are two different rows. `rows.stream().distinct()` does not remove one of them just because they share the same code.

Subsequently, `toMap(Sale::code, Sale::quantity)` still encounters a duplicate key `B`. You must distinguish equality of the entire input element from equality of the key used for the Map.

Similarly, two keys having the same `hashCode` is not enough to conclude they are the same key under `equals`. Hash collisions and post-mapping key duplicates are two different things.

## 4. The Merge Function Decides Which Data Remains

The three- or four-argument forms accept a `BinaryOperator<U>`. Both operands and the result are of the value type `U`, not automatically the two original input elements. [Java SE 17 — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html).

In a sequential pass, when encountering a key that already has a value, you can picture:

~~~text
accumulated value + value from new row -> replacement value
~~~

If you are summing multiple rows, the "accumulated value" may already be the sum of several previous rows, no longer the quantity of a single row.

### 4.1. Keep First or Keep Last Are Two Different Policies

~~~java
(oldValue, newValue) -> oldValue
~~~

Keeps the existing value. With a sequentially ordered source, `B` keeps `2` and `A` keeps `3`.

~~~java
(oldValue, newValue) -> newValue
~~~

Keeps the later value. With that same source, `B` becomes `5` and `A` becomes `1`.

"Later" here means later in the requested encounter order, which does not automatically mean newest in business time. If you need the record with the latest timestamp, compare timestamps with an explicit rule; do not use a later position in a source with no guaranteed order to infer recency.

Nor is there any guarantee that "keep old" skips `valueMapper` for the new row. Each row must still be mapped to produce a value before resolving the conflict; a faulty mapping or one that produces `null` can still cause `collect` to fail.

### 4.2. Summing or Picking the Maximum

Common functions for `Integer` values:

~~~java
Integer::sum
Integer::max
~~~

With the initial data:

~~~text
sum:          B=7, A=4, C=4
max:          B=5, A=3, C=4
~~~

Choosing a rule must follow the data's semantics. Summing fits quantities across multiple transactions; it does not necessarily fit a status code or a measurement where only the latest version should be kept.

If the sum can exceed the `int` range, choose an appropriate numeric model and bounds-checking policy. Choosing `Integer::sum` does not automatically provide overflow checks per business requirements.

### 4.3. Keeping the Whole Object with Function.identity

If you need a Map pointing to the selected sales row:

~~~java
Map<String, Sale> best = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Sale::quantity)),
                LinkedHashMap::new));
~~~

Here the value type is `Sale`, so the merge function receives two `Sale` instances. `Function.identity()` keeps the input object itself as the value; it does not copy the object.

If two rows tie on the quantity criterion but differ in other fields, add an appropriate tie-breaker rule. Choosing one over the other should not be an accidental side effect of traversal order.

## 5. If You Want to Keep Every Row, Do Not Silently Drop Them

If you need to keep `B -> [2, 5]`, `A -> [3, 1]`, and `C -> [4]`, the problem is grouping multiple values per key:

~~~java
Map<String, List<Integer>> all = rows.stream().collect(
        Collectors.groupingBy(
                Sale::code,
                LinkedHashMap::new,
                Collectors.mapping(Sale::quantity, Collectors.toList())));
~~~

This is a more natural choice than adding a "keep first" function just to suppress duplicate-key errors.

You could use `toMap` with a list as the value, but then you must manually decide how to create new lists and how to merge them, avoiding mutating an immutable list or sharing lists across the wrong scope. When the requirement is to keep everything, `groupingBy` expresses the intent much more clearly.

The key takeaway is: **a merge function can intentionally discard information**. If two transactions are merged into a sum, you cannot recover each original transaction from that sum. If you only keep the first row, subsequent rows are no longer in the resulting Map.

Before choosing a merger, answer whether the Map serves to look up a representative, compute an aggregate, or store the entire group of data. That is a modeling decision, not just a short lambda to make the code compile.

## 6. Merge Functions and Parallel Processing: Associativity Is Required

A Collector can accumulate chunks of data into separate Maps and then merge those partial results. Therefore, the merge function is not only called as "the old value of one row and the value of the next row"; it can receive values that have already been aggregated.

The `Collector` contract requires accumulation and combination operations to satisfy conditions so that splitting and combining produce an equivalent result. [Java SE 17 — Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).

An important condition for a merge rule is associativity:

~~~text
merge(merge(a, b), c) is equivalent to merge(a, merge(b, c))
~~~

Subtraction does not satisfy this:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

If you use `(a, b) -> a - b` and expect it to always behave like a left-to-right subtraction loop, switching to a parallel pipeline can expose the broken assumption.

Associativity is not the same as commutativity. A keep-first or keep-last rule has its own order-dependent property; it does not allow arbitrarily reordering values or dropping ordering requirements. If the input has no guaranteed order or uses an unordered collection, "first/last" must be re-evaluated.

Mapping functions and merge functions should also not mutate the Stream source or depend on an external counter to determine the result. In a parallel pipeline, shared state can cause contention; even sequentially, it makes the merge rule hard to understand and test.

For special business requirements that are inherently a sequence of non-associative stateful updates, an explicit sequential loop may be a more accurate expression than forcing it into a general collector.

## 7. A Merge Function Returning null Means Removing the Mapping

The overloads with a merger use merge semantics based on `Map.merge`. If the merge function returns `null`, the existing mapping is removed; the key is not retained with a `null` value. [Java SE 17 — Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)).

An example intentionally run sequentially with the merger `(a, b) -> null`:

~~~text
A=10  -> {A=10}
B=1   -> {A=10, B=1}
A=20  -> merging A returns null, removes A -> {B=1}
A=30  -> A is absent, re-added             -> {B=1, A=30}
~~~

The result is not `{A=null, B=1}`. Key `A` can even reappear if a later row with the same key is processed after the mapping was removed.

This is a behavior to know when reading the API, not a default policy to use for avoiding duplicate errors. Removing on collision may also fail to satisfy associativity conditions when running in parallel. The test case in this lesson only illustrates the sequential sequence of operations shown above.

If the intent is to fail on duplicates, throw an exception or use the overload that forbids duplicates. If the intent is to skip certain rows, consider filtering with an explicit condition before collecting. Do not return `null` from a merger just because you have not decided which value to keep.

## 8. The Target Map Determines Ordering and Part of Key Semantics

### 8.1. Without a Factory, No Specific Map Class Is Promised

The first two overloads return `Map` by contract, with no guarantee of a specific implementation class, mutability, serializability, or thread-safety. Do not rely on seeing `HashMap` once in a debugger to cast or infer output order.

If you only need to read and look up entries without a special contract, you can keep the result typed as `Map<K, V>`. If ordering, a comparator, or mutability is part of the requirement, specify the appropriate target using the four-argument overload.

### 8.2. LinkedHashMap: Preserves Key Insertion Order

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                LinkedHashMap::new));
~~~

In the example with an ordered List and a sequential pipeline, keys first appear in the order `B, A, C`. Subsequent merges updating `B` or `A` do not move them to the end in a `LinkedHashMap` in its default insertion-order mode.

The printed result is `{B=7, A=4, C=4}`. This is **key insertion order**, not ascending order and not the order of the last update. [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Choosing `LinkedHashMap` does not automatically give an unordered source a stable business order. If the source does not guarantee which element comes first, you must define or sort the input beforehand as required.

### 8.3. TreeMap: Sorts by Key

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                TreeMap::new));
~~~

With ordinary string keys, the result in natural order is `{A=4, B=7, C=4}`. If a custom comparator is provided, key ordering and how equivalent keys are recognized depend on that comparator. [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

`TreeMap` does not sort by value. If you want total quantities in descending order, you need a step that sorts entries by value and builds an appropriate result representation; switching the factory to `TreeMap` does not solve that requirement.

### 8.4. The Factory Must Create a New, Empty Map Usable for Collection

Do not write a supplier that always returns the same external Map already containing data and expect the collector to distinguish old/new data. Especially when splitting work in parallel, accumulation containers must have proper ownership scope.

`LinkedHashMap::new` and `TreeMap::new` clearly express creating a new instance. For enum keys, you can choose a factory that creates an `EnumMap` for the exact enum class if that is the required target contract.

A Map that does not support insertion/merging cannot serve as a normal accumulator just because it is initially empty. Both the ability to construct the target object and the ability to perform accumulation operations must match.

## 9. Changing the Target Map Can Change How Equal Keys Are Recognized

In a standard Map that follows `equals`, `"a"` and `"A"` are two distinct keys. However, a `TreeMap` using `String.CASE_INSENSITIVE_ORDER` treats them as equal by comparison.

Demonstration case:

~~~java
Map<String, Integer> counts = letters.stream().collect(
        Collectors.toMap(
                Function.identity(),
                text -> 1,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
~~~

With `letters = ["a", "A", "b"]`, the program produces `{a=2, b=1}`. The same data into a `LinkedHashMap` produces three separate keys: `a`, `A`, and `b`.

This example intentionally shows the effect of a comparator. A case-insensitive comparator is inconsistent with `String.equals`; `TreeMap` still has defined comparison behavior, but it does not fully adhere to the `Map` contract based on `equals` in that case.

If the business domain treats both forms of a code as one, it is usually better to normalize the key into a common representation and use a consistent key rule, rather than accidentally passing a comparator into the factory that alters key equivalence.

Do not only check "are the key objects different?" Check **what criterion the target Map uses to consider two keys the same lookup slot**. Also avoid mutating key objects after inserting them into the Map in ways that change `equals`, `hashCode`, or the comparison order needed by the structure.

## 10. null: Distinguishing Mapped Values, Keys, and Merger Results

### 10.1. valueMapper Returning null Is Not Saved by a Target Map That Allows null

In the demonstrated collectors, if `valueMapper` returns `null`, `collect` throws `NullPointerException`. This happens both in the two-argument form and in the form using `LinkedHashMap`, which allows storing `null` via other operations.

The merger form delegates to `Map.merge`, which requires a non-null input value. The non-merger form in OpenJDK 17 also checks that the mapped value is non-null during accumulation. [OpenJDK 17 — Collectors.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/stream/Collectors.java).

Therefore, do not fix the error by merely switching `HashMap` to `LinkedHashMap`. You must choose a policy for missing values: fail at the data boundary, filter out rows, use a sentinel object representing absence, or use a different collection model if `null` mappings are genuinely required.

If failing, you can check explicitly with `Objects.requireNonNull` with an informative message, rather than waiting for a less contextual exception deep inside `collect`. [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)).

### 10.2. Null Keys Also Depend on the Target Map and Policies

The example using an explicit `LinkedHashMap::new` factory can store a `null` key with a non-null value. `TreeMap` using natural ordering does not accept a `null` key in the test case.

Do not turn the behavior of one specific Map into a promise that every overload or every factory accepts `null` keys. If a missing key is invalid application data, validate beforehand; picking a Map that happens to accept `null` does not make business logic correct.

### 10.3. A Merger Returning null Is a Different Behavior

Summary of the three cases:

| Situation | Meaning |
| --- | --- |
| `valueMapper` returns `null` in the shown collector cases | No valid input value to accumulate; causes an error |
| Mapped key is `null` | Depends on the target Map contract and application policy |
| `mergeFunction` returns `null` | Removes the mapping per `Map.merge` |

Do not use a blanket statement like "`toMap` does not handle `null`" and ignore the differences. These `null` positions occur at different stages and carry different meanings.

## 11. The Target Map Type Does Not Determine Whether the Collector Is Concurrent

`toMap` is a non-concurrent collector. It can still be used in a parallel pipeline: the library creates separate accumulation containers, then merges partial Maps according to the contract. Merging keys from multiple Maps can have overhead.

Specifying a Map type that supports concurrent access in the factory does not automatically turn `toMap` into a collector with the `CONCURRENT` characteristic. If you need a suitable concurrent collection model, look at `toConcurrentMap` and its unordered contract.

Do not use `(a, b) -> b` with an unordered collection and call the retained value "the last row in the file" when there is no mechanism preserving that order. Access safety and business ordering are two independent requirements.

The parallel example in the program uses quantity summation and compares the resulting Map with the sequential result using `equals`. It does not print the default Map's order or benchmark speed to conclude one approach is always better.

Beyond the accumulation Map, the source itself and the objects stored as values must also be suitable for the access pattern. `Function.identity` does not automatically make value objects thread-safe or create deep copies.

## 12. An Error Is Not a Full Rollback Transaction

If a forbidden duplicate key, mapping error, or merger exception occurs, `collect` fails and no successful result Map is returned for that call.

However, any external side effects that lambdas already performed beforehand are not automatically undone. For example, logging a record in `valueMapper` and then encountering a duplicate key later does not make the logged record disappear.

Therefore, functions should focus on transforming and merging data. If you need to validate data before an external action that cannot easily be undone, collect and validate the results first, then perform the action in an appropriate subsequent stage.

Do not pass a shared external Map into the supplier to observe "partial results" as a default error mechanism. The collector's supplier must honor the accumulation container contract; design structured error reporting separately if the application needs to report all duplicate codes or all invalid rows.

## 13. Complete Demonstration Program

Save the following code as **ToMapPoliciesDemo.java**. The program uses records and the standard library, compatible with Java 17.

Maps whose stdout depends on order are created with `LinkedHashMap` or `TreeMap`. In the two-argument case, the program creates a separate `TreeMap` solely to print the data in order; that display step is not a claim that the default collector returns a `TreeMap`.

The `rejects` helper only accepts the expected exception family. The null-returning merger case is intentionally run sequentially to observe removing and then re-adding a mapping. The case-insensitive comparator is an example of changing key criteria, not a recommendation to ignore consistency with `equals`.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class ToMapPoliciesDemo {
    record Sale(String code, int quantity) { }
    record Label(String code, String text) { }

    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<Sale> rows = List.of(
                new Sale("B", 2), new Sale("A", 3),
                new Sale("B", 5), new Sale("C", 4), new Sale("A", 1));

        Map<String, Integer> unique = rows.subList(0, 2).stream()
                .collect(Collectors.toMap(Sale::code, Sale::quantity));
        System.out.println("unique-sorted-for-display=" + new TreeMap<>(unique));
        rejects("duplicate-key", IllegalStateException.class,
                () -> rows.stream().collect(Collectors.toMap(Sale::code, Sale::quantity)));
        rejects("equal-values-still-duplicate", IllegalStateException.class,
                () -> List.of(new Sale("A", 1), new Sale("A", 1)).stream()
                        .collect(Collectors.toMap(Sale::code, Sale::quantity)));
        rejects("distinct-rows-not-distinct-keys", IllegalStateException.class,
                () -> rows.stream().distinct()
                        .collect(Collectors.toMap(Sale::code, Sale::quantity)));

        Map<String, Integer> first = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (oldValue, newValue) -> oldValue, LinkedHashMap::new));
        Map<String, Integer> last = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (oldValue, newValue) -> newValue, LinkedHashMap::new));
        Map<String, Integer> total = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum, LinkedHashMap::new));
        Map<String, Integer> largest = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::max, LinkedHashMap::new));
        System.out.println("first=" + first);
        System.out.println("last=" + last);
        System.out.println("total=" + total);
        System.out.println("largest=" + largest);
        System.out.println("insertion-order=" + new ArrayList<>(total.keySet()));

        Map<String, Integer> sorted = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum, TreeMap::new));
        System.out.println("tree-order=" + sorted);

        Map<String, Sale> bestRows = rows.stream().collect(Collectors.toMap(
                Sale::code, Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Sale::quantity)),
                LinkedHashMap::new));
        System.out.println("best-B=" + bestRows.get("B").quantity());

        Map<String, List<Integer>> all = rows.stream().collect(Collectors.groupingBy(
                Sale::code, LinkedHashMap::new,
                Collectors.mapping(Sale::quantity, Collectors.toList())));
        System.out.println("all-values=" + all);

        List<String> spellings = List.of("Java", " java ", "JAVA");
        Map<String, Integer> normalized = spellings.stream().collect(Collectors.toMap(
                text -> text.trim().toLowerCase(Locale.ROOT),
                text -> 1, Integer::sum, LinkedHashMap::new));
        System.out.println("normalized=" + normalized);

        List<String> letters = List.of("a", "A", "b");
        Map<String, Integer> ordinary = letters.stream().collect(Collectors.toMap(
                Function.identity(), text -> 1, Integer::sum, LinkedHashMap::new));
        Map<String, Integer> ignoreCase = letters.stream().collect(Collectors.toMap(
                Function.identity(), text -> 1, Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
        System.out.println("ordinary-keys=" + ordinary);
        System.out.println("comparator-keys=" + ignoreCase);

        List<Label> nullable = List.of(new Label("A", "ok"), new Label("B", null));
        rejects("null-value-two-arguments", NullPointerException.class,
                () -> nullable.stream().collect(Collectors.toMap(Label::code, Label::text)));
        rejects("null-value-linked-map", NullPointerException.class,
                () -> nullable.stream().collect(Collectors.toMap(
                        Label::code, Label::text, (a, b) -> b, LinkedHashMap::new)));

        List<Label> nullKey = List.of(new Label(null, "unknown"));
        Map<String, String> explicitNullKey = nullKey.stream().collect(Collectors.toMap(
                Label::code, Label::text, (a, b) -> b, LinkedHashMap::new));
        System.out.println("explicit-null-key=" + explicitNullKey);
        rejects("null-key-natural-tree", NullPointerException.class,
                () -> nullKey.stream().collect(Collectors.toMap(
                        Label::code, Label::text, (a, b) -> b, TreeMap::new)));

        List<Sale> cancellation = List.of(
                new Sale("A", 10), new Sale("B", 1),
                new Sale("A", 20), new Sale("A", 30));
        Map<String, Integer> removedOnMerge = cancellation.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (a, b) -> null, LinkedHashMap::new));
        System.out.println("null-merge-result=" + removedOnMerge);

        int left = (10 - 3) - 2;
        int right = 10 - (3 - 2);
        System.out.println("subtraction-grouping=" + left + " / " + right);
        Map<String, Integer> parallelTotal = rows.parallelStream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum));
        System.out.println("parallel-equal=" + parallelTotal.equals(total));
        System.out.println("input-size=" + rows.size());
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 -encoding UTF-8 ToMapPoliciesDemo.java
java ToMapPoliciesDemo
~~~

Exact stdout:

~~~text
unique-sorted-for-display={A=3, B=2}
duplicate-key -> IllegalStateException
equal-values-still-duplicate -> IllegalStateException
distinct-rows-not-distinct-keys -> IllegalStateException
first={B=2, A=3, C=4}
last={B=5, A=1, C=4}
total={B=7, A=4, C=4}
largest={B=5, A=3, C=4}
insertion-order=[B, A, C]
tree-order={A=4, B=7, C=4}
best-B=5
all-values={B=[2, 5], A=[3, 1], C=[4]}
normalized={java=3}
ordinary-keys={a=1, A=1, b=1}
comparator-keys={a=2, b=1}
null-value-two-arguments -> NullPointerException
null-value-linked-map -> NullPointerException
explicit-null-key={null=unknown}
null-key-natural-tree -> NullPointerException
null-merge-result={B=1, A=30}
subtraction-grouping=5 / 9
parallel-equal=true
input-size=5
~~~

The code was compiled with `--release 17` and run on JDK 24.0.2. The compiler flag verifies Java 17 language/API level; this is not a run on a Java 17 JVM.

Result groups to compare:

- The three duplicate-key cases distinguish duplicate keys, equal values, and `distinct` on entire rows.
- `first`, `last`, `total`, and `largest` apply four different policies to the same data.
- `insertion-order` and `tree-order` separate insertion order from key order.
- `best-B` keeps an entire selected `Sale` row, rather than just the quantity.
- `all-values` preserves every quantity via grouping.
- `normalized` shows that different strings can produce the same key after normalization.
- The `ordinary-keys` and `comparator-keys` lines show that the target Map can change how equivalent keys are handled via a comparator.
- The null cases distinguish rejected input values from the chosen Map's ability to store a `null` key.
- `null-merge-result` demonstrates removing a mapping and then re-adding it, rather than storing a `null` value.
- `subtraction-grouping` explains why associativity must be considered.
- `parallel-equal` checks the contents of the summed result; `input-size` confirms the source list still has five rows.

## 14. Practice with Answers

### Exercise 1 — Same Key, Same Value

Two inputs produce `A=1` and `A=1`. Does the two-argument form of `toMap` automatically accept them because the two values are equal?

**Answer:** No. It forbids duplicate keys and throws `IllegalStateException`. If you want to accept equivalent values under a specific rule, express it with an appropriate merger instead of relying on a default.

### Exercise 2 — Does distinct Resolve Duplicate Codes?

Two records `Sale("B", 2)` and `Sale("B", 5)` are passed through `distinct` and then `toMap` by code. Why does it still fail?

**Answer:** The two records differ across their full components, so `distinct` does not merge them. `keyMapper` still produces the same key `B`. Input uniqueness and post-mapping key uniqueness are two different things.

### Exercise 3 — Choosing the Right Merge Policy

The same code has quantities `2` and `5`. If you want the transaction total, do you use keep-last or sum? If you want to keep the row with the largest quantity, should `valueMapper` return the number or the entire row?

**Answer:** The total is `7`, so use summation. If you need other fields from the winning row, `valueMapper` keeps the entire row via `Function.identity` and the merger selects the object using a comparator. Keeping only the number `5` will not retain the remaining fields.

### Exercise 4 — Does LinkedHashMap Sort by Key?

A sequential source encounters keys `B`, `A`, `B`, `C` and merges by sum. What order does the default `LinkedHashMap` preserve? What should you use if you want keys in ascending order?

**Answer:** The first-insertion order is `B, A, C`; updating `B` does not move it to the end. If you want natural key order, choose `TreeMap`. Neither Map automatically sorts by the summed value.

### Exercise 5 — Merge Function Returning null

A sequential source has `A=10`, `A=20`, `A=30`, and the merger always returns `null` when called. Is the final result for `A` equal to `null`?

**Answer:** No. The second row causes the merger to return `null` and remove `A`. The third row encounters an absent key, so it adds `A=30` without merging with an existing value. This behavior is not a way to store a mapping from `A` to `null`.

### Exercise 6 — Does Switching the Target to LinkedHashMap Accept null Values?

A `valueMapper` returns `null`. Can the error be fixed simply by using `LinkedHashMap::new` because `LinkedHashMap` allows `null`?

**Answer:** Not in the demonstrated overloads. A `null` value still does not satisfy the collector's accumulation process, especially `Map.merge` semantics requiring a non-null input value. You need an explicit missing-data policy rather than just switching the Map class.

### Exercise 7 — Subtraction and parallelStream

The merger is `(a, b) -> a - b`. Why can you not assume the result will always match left-to-right sequential subtraction when switching to parallel?

**Answer:** Subtraction is not associative: `(10-3)-2` differs from `10-(3-2)`. Partial Maps and the combine step can group values differently. If the requirement is genuinely sequential stateful updates, choose an explicit sequential model.

### Exercise 8 — Changing the Comparator Causes Keys to Merge

The source has strings `a` and `A`, two distinct keys under `equals`. When the target is a `TreeMap` using a case-insensitive comparator, why can they merge into the same slot?

**Answer:** `TreeMap` recognizes key equivalence via the comparator; that comparator returns `0` for the two strings. It is inconsistent with `String.equals`, so you must understand the `Map` contract caveats. If the business domain treats both forms as one code, normalizing keys with an explicit rule usually yields a more consistent model.

## 15. Decisions to Make Explicit in Code

Before a `toMap` call, determine the normalized key domain, duplicate policy, value semantics, and target Map type. If duplicate keys are a data error, let the error surface; if they are valid data, choose an appropriate merge or grouping operation.

Next, consider input ordering, merger associativity, `null` handling, and ownership of the resulting objects. Do not use a keep-first/keep-last lambda as a universal fix for all data, and do not expect the factory to solve requirements it does not express.

Reading `keyMapper`, `valueMapper`, `mergeFunction`, and `mapFactory` together makes it clear exactly what information the resulting Map will keep, what it will discard, and what rules it will follow when a key appears multiple times.
