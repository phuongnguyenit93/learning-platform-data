# Comparing Sequential and Parallel Stream Results When the Contract Allows (Java 17)

## 1. The testing question: when must results match?

Java Streams allow running a pipeline in either *sequential* or *parallel* mode:

~~~java
List<Integer> source = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();
~~~

This is an **illustrative snippet inside a method**, requiring `import java.util.List;`. Both variables return the same list:

~~~text
[4, 16, 36, 64, 100]
~~~

The filter selects even numbers, `map` squares them, `sorted` orders by natural order, and `toList()` collects the elements into a list. With pure callbacks and stable data like in this example, the logical result does not depend on how elements are partitioned across workers in a parallel Stream.

However, **not every pair of similar-looking expressions is allowed to be compared with `equals`**. Operations such as `findAny()`, `forEach()`, pipelines that called `unordered()`, or floating-point arithmetic can have different contracts. Sometimes the right test is **same set of elements**, **same sum in the arithmetic sense**, **returned element belongs to the valid set**, or **a business invariant** — rather than two objects having the exact same printed order.

**Goal:** learn how to identify *what the API actually guarantees* before comparing sequential and parallel results, build a runnable Java 17 test suite, and distinguish **permitted** differences from **bugs**.

## 2. What is invariant and what is not

Both modes use the same interfaces and Stream operations; the difference is how the framework may split, process, coordinate, and combine chunks of data.

### 2.1. Results that usually must be equal

If the source is not mutated, callbacks are stateless/non-interfering, operations satisfy reduction contracts, and results have clear ordering conditions, you can compare:

- **Final list with a defined encounter order:** order-preserving operations like `filter`/`map` and terminal `toList()` preserve elements in encounter order; `sorted()` produces order according to the Comparator.
- **Integer sum with a valid combining operation:** `mapToLong(...).sum()` on suitable integer data yields the same result in both modes; watch for overflow if the domain requires exact arithmetic.
- **Reduction with an identity and associative combining operation:** the combined result matches the contract, without arbitrary side effects.
- **`findFirst()` on an ordered Stream:** the first element in encounter order must match in both modes, even if callback execution timing differs.
- **Grouped summary Map:** key-accurate sums/counts can be compared with `Map.equals()`, provided the combiner and classifier are appropriate.
- **Result Set:** if only the set of values matters, `Set.equals()` compares membership without depending on iteration order.

### 2.2. Things that do not have to be identical

- **Thread IDs, scheduling, callback log order:** a parallel Stream does not force callbacks to run in the same chronological order as the sequential version.
- **`findAny()`:** may return any valid element; it is not required to return the first element.
- **`forEach()` on a parallel stream:** the action is not required to run in encounter order.
- **An unordered pipeline with `limit(n)`:** may pick different sets of n elements across runs; you must test validity against the contract.
- **Concrete Map type / default collector iteration order:** a Map with right data does not have to print keys in the same order as another Map.
- **Floating-point operation order:** floating-point addition is not strictly associative in machine arithmetic; results can differ in the last digits when grouping changes.
- **Side effects in callbacks:** do not use external counter increments or print order as an equivalence test for a pipeline.

### 2.3. Quick comparison table

| Result to test | Recommended comparison | Key condition |
| --- | --- | --- |
| `List<T>` with clear order and values | `List.equals()` | Same encounter order/sort, pure functions, suitable element `equals` |
| Exact `long`/`int` sum | `==` | Valid addition, overflow range considered |
| Statistics `Map<K,V>` | `Map.equals()` | Do not compare `toString()` or iteration order when API does not promise it |
| `Set<T>` | `Set.equals()` | Compares membership, unordered |
| `Optional<T> findFirst()` | `Optional.equals()` | Ordered Stream and equivalent pipeline |
| `Optional<T> findAny()` | Check `present`, valid element | Not required to equal sequential result |
| `double` average/sum | Domain-appropriate tolerance/precision | NaN, ±∞, signed zero need explicit policies |
| Non-associative combination | Do not assume equivalence | Fix the reduction, do not weaken the test to pass |
| Parallel `forEach()` results | Check result collection with a safe structure if suitable | Do not check callback order |
| Log lines, thread names, `peek` count | Do not use as business equivalence criteria | Side effects are not guaranteed outputs |

## 3. Step 1: fix the data and define the contract

A test is meaningful only if both pipelines process the same **logical data**. Prefer `List.of(...)` or an immutable snapshot for tests so no other writer mutates the source during testing.

~~~java
List<Integer> inputs = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);
~~~

For a List, encounter order is positional order. For a `HashSet`, by contrast, do not assume an order matching insertion order or ascending values.

Before choosing an assertion, state clearly:

1. **Does the source have encounter order?**
2. **Do any operations drop ordering?** For example, `unordered()`.
3. **Is every function stateless and non-interfering?**
4. **Is the aggregation associative with a neutral identity?**
5. **Does the business requirement need order, a total value, a membership set, or just any matching element?**
6. **Are there float/double values, overflow, exceptions, or side effects?**

Do not test by running sequentially on a source and **simultaneously mutating that source** before running in parallel. Once the inputs differ, differing outputs say nothing about correctness of Stream modes.

### 3.1. Compare the right method, not just sample data

A test can pass by coincidence because the dataset is too simple. For example, all-positive numbers might cause `findAny()` and `findFirst()` to return the same result across several runs, yet that **does not turn findAny's contract into findFirst**.

Include data with:
- Non-matching elements first and matching elements later.
- Multiple groups/keys to catch grouping bugs.
- Duplicate values to test `distinct`.
- Empty source and single-element source.
- Boundary values for addition or Comparator.
- Enough elements to allow splitting in parallel tests, without requiring a fixed thread count.

## 4. Comparing lists when encounter order is guaranteed

### 4.1. Ordered List + filter/map/sorted/toList

~~~java
List<Integer> expected = inputs.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

List<Integer> actual = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sorted()
        .toList();

if (!expected.equals(actual)) {
    throw new AssertionError("Mismatched ordered results");
}
~~~

Illustrative snippet inside a method with `inputs` already declared. With the data in section 3, both lists are `[4,16,36,64,100]`.

Here `sorted()` guarantees value order in the result and `toList()` returns elements in Stream encounter order. Differences in callback scheduling must not corrupt the final logical order.

### 4.2. Not necessarily sorted

If the source already has encounter order and all operations preserve order:

~~~java
List<Integer> seq = inputs.stream()
        .filter(n -> n > 3).toList();

List<Integer> par = inputs.parallelStream()
        .filter(n -> n > 3).toList();
~~~

Both lists must have the same elements in the source's encounter order. Omitting `sorted()` in this case does not lose List encounter order.

However, if the source is an unordered Set or the pipeline calls `unordered()`, do not impose a fixed list order that the API does not promise.

### 4.3. Sorted with equal-key elements

If `sorted(comparator)` uses a Comparator that treats two distinct elements as equal, consider:
- On an **ordered Stream**, `sorted` is *stable* per contract.
- On an **unordered Stream**, there is no similar stability guarantee.
- If the order of equal-key values is a business requirement, add an **explicit tie-breaker** to the comparator instead of relying on timing.

Example comparing orders by total amount then ID:

~~~java
// Design example when Order has amount() and id():
// Comparator<Order> order = Comparator
//         .comparingLong(Order::amount)
//         .thenComparing(Order::id);
~~~

The comment snippet is merely an illustration with an `Order` type not defined in this section. The rule is that if the Comparator defines a fully deterministic order, tests can compare lists after `sorted(order)` directly.

### 4.4. limit/skip on an ordered pipeline

On a List with encounter order, `limit(k)` takes at most the first k elements at the point it is applied, and `skip(n)` drops the first n elements. Therefore, when callbacks and source are valid, equivalent sequential and parallel pipelines must still pick the same logical elements even though the parallel version may coordinate more slowly.

~~~java
List<Integer> a = inputs.stream()
        .filter(n -> n % 2 == 0)
        .skip(1).limit(2).toList();

List<Integer> b = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .skip(1).limit(2).toList();
// Both [4, 6].
~~~

**Do not rewrite** `filter(...).limit(k)` into `limit(k).filter(...)` and compare them, because those are two data-selection algorithms with **different semantics** even before considering parallelism.

## 5. Sums, reduce, and associativity requirements

### 5.1. Summing integers with sum()

~~~java
long sequentialSum = inputs.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallelSum = inputs.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

With the data in section 3, both sums are 55. Integer `long` addition has identity 0, and grouping order does not change the result under Java's `long` arithmetic rules.

Even so, **overflow** can make the `long` value differ from the infinite mathematical sum. If revenue must never overflow, choose a numeric type/validation check (e.g. BigInteger or overflow detection policy). Testing with `==` can prove the two pipelines agree with each other, **not that the sum is domain-correct**.

### 5.2. reduce with valid identity and accumulator

~~~java
int total = inputs.parallelStream()
        .reduce(0, Integer::sum);
// 55
~~~

For a parallel reduction to be correct, the accumulator must be **associative**, the identity must be neutral, and behavioral parameters must be stateless/non-interfering. Summing with `Integer::sum` and identity 0 satisfies the relevant conditions.

A `reduce` that works in sequential mode is **not** proof that it works when partitioned. Verify the operation:

~~~text
(a op b) op c == a op (b op c)
~~~

and the identity:

~~~text
op(e, x) == x
op(x, e) == x
~~~

For the three-argument overload, you must also check that the combiner is compatible with the accumulator:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

**Do not use** a combiner that only keeps the left value just "to make it compile", because on a parallel Stream results from other segments will be lost.

### 5.3. Counterexample: subtraction

~~~java
// Counterexample: compiles, yet does not satisfy the reduce contract.
// int result = inputs.parallelStream()
//         .reduce(0, (a, b) -> a - b);
~~~

Non-associativity is directly visible:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Because the two groupings yield different results, **do not expect** this kind of reduce to match between sequential and parallel modes. If a test happens to "match" sometimes, that is merely a coincidence of data or task splitting. You must **fix the operation design**, not remove the assertion to make the test pass.

### 5.4. Floating-point: comparing with a tolerance policy

For `float`/`double`, floating-point addition is not strictly associative due to rounding. The JDK may use different summation strategies and grouped addition can produce small differences.

~~~java
double a = seqValues.stream().mapToDouble(Double::doubleValue).sum();
double b = seqValues.parallelStream().mapToDouble(Double::doubleValue).sum();
~~~

This snippet assumes `seqValues` is a valid `List<Double>`; requires `import java.util.List;`. It does not claim `a != b` on every run, nor promise `a == b` on every run.

A tolerance criterion for **finite data** might be:

~~~java
double tolerance = 1e-9;
boolean close = Math.abs(a - b)
        <= tolerance * Math.max(1.0, Math.max(Math.abs(a), Math.abs(b)));
~~~

This is a simple *absolute + relative tolerance* policy example, **not the right threshold for every domain**. For NaN, infinity, underflow, signed zero, or problems requiring exact decimal arithmetic, handle them separately.

In monetary calculations, consider exact numeric representations in the smallest unit (long with appropriate bounds) or `BigDecimal` with clear scale/rounding rules. Do not replace an exact constraint with an arbitrary epsilon.

## 6. Comparing groups and collectors

Two pipelines can use the same valid collector to build a statistics Map. Do not compare `Map.toString()` strings if the Map type does not guarantee key order.

~~~java
Map<String, Integer> a = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));

Map<String, Integer> b = sales.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));

if (!a.equals(b)) {
    throw new AssertionError("Group totals mismatch");
}
~~~

This illustrative snippet needs `java.util.Map`, `java.util.TreeMap`, `java.util.stream.Collectors`, and a `Sale` type with `category()` and `amount()` methods.

`Map.equals()` checks the set of key → value mappings. With `TreeMap`, key iteration order is also determined by natural order/comparator. If report ordering is not needed, you can still use the default collector and compare `Map.equals()` without assuming a specific Map implementation.

### 6.1. Collectors must satisfy their contracts

Comparing two results is meaningful only when the collector combines partial results validly:
- Downstream and combiner must preserve the statistic.
- If using a custom Collector, supplier must provide proper containers, and accumulator/combiner must not violate the contract.
- With grouping or `toMap` having duplicate keys, the merge function must be appropriate.
- Do not mutate an external shared mutable Map from `parallelStream().forEach(...)`.

A standard `Collectors.groupingBy(...)` can be used by the Stream framework on a parallel stream via partial-result combination; that **does not permit** your callback to mutate an unsynchronized shared HashMap/ArrayList.

### 6.2. Key order and element order within a group are two separate questions

`LinkedHashMap` preserves insertion order under suitable conditions; `TreeMap` sorts by key. However, if group values are `List<T>`, the order **inside each group's list** still depends on encounter order and the downstream collector.

With `Collectors.toSet()`, **Set iteration order is not guaranteed**, so compare membership rather than sequence. With `groupingByConcurrent(...)`, the collector has concurrent/unordered characteristics: avoid using thread scheduling as a reporting order rule.

If you want to present groups sorted by descending total amount, a `TreeMap` by key will not do that automatically; you need to sort entries by value with an explicit tie-breaker. Tests must reflect the exact ordering axis the business requires.

## 7. Testing Sets: equality by membership, not iteration order

~~~java
Set<Integer> sequentialSet = inputs.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toSet());

Set<Integer> parallelSet = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toSet());

boolean sameMembers = sequentialSet.equals(parallelSet);
~~~

This is an illustrative snippet with `inputs` of type List; requires importing `java.util.Set` and `Collectors`.

`Collectors.toSet()` does not guarantee a concrete Set type or iteration order. Thus asserting `Set.equals()` is appropriate when business logic only cares about membership, while asserting `Set.toString()` equality may be invalid.

If you want **stable stdout** when explaining tests, turn the Set into a sorted list:

~~~java
List<Integer> sorted = sequentialSet.stream().sorted().toList();
// [2, 4, 6, 8, 10]
~~~

This sorting is for **presentation and verification**, not because the `toSet` collector guarantees order.

### 7.1. Comparing multisets when occurrence counts also matter

A Set **deduplicates**, so comparing Sets can miss bugs if expected data contains multiple records with the same value.

For example, source `[1,1,2]` and source `[1,2,2]` produce the same Set `{1,2}`, yet differ in **occurrence counts**. When business rules require preserving the count of each value:
- Compare sorted lists if all elements are comparable.
- Or use `groupingBy(identity(), counting())` to compare a Map of value → occurrence count.
- Or compare an application-defined multiset structure.

**Choose assertions based on data semantics**, not merely on the API you happen to be calling.

## 8. findFirst and findAny: two different contracts

### 8.1. findFirst on a List with encounter order

~~~java
int sequentialFirst = inputs.stream()
        .filter(n -> n % 2 == 0)
        .findFirst().orElseThrow();

int parallelFirst = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst().orElseThrow();
~~~

With the source in section 3, both must return `2`. That is the **first even number in encounter order**, not necessarily the smallest even number by value. `findFirst()` may incur extra coordination cost to preserve order in parallel.

For an empty source or no matching element, `findFirst()` returns `Optional.empty()` and code using `orElseThrow()` will throw an exception. A general test should compare the two Optionals rather than forcing every source to be non-empty.

### 8.2. findAny does not promise the same element

~~~java
int any = inputs.parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny().orElseThrow();

boolean valid = inputs.contains(any) && any % 2 == 0;
~~~

It is true that `any` must belong to the matching even elements of the source in the example, yet **do not** require it to equal 2 or equal `findAny()` from another run.

Also do not write the inverse test "two results must differ", because `findAny()` **is allowed to return the same element**. A proper test when the source has valid elements:
- Checks that the Optional is present.
- Checks that the value belongs to the filtered input domain.
- Checks business properties.
- Does not check which exact element was chosen, unless the pipeline has a single valid element.

When the source has no matching elements, verify `Optional.empty()`. With sources allowing null—since the Stream API rejects null as a found value in many situations—avoid feeding null values uncontrollably into `findAny`/`findFirst`.

## 9. forEach() and forEachOrdered(): testing ordered actions

`forEach()` in a parallel stream **does not guarantee action order**. For example:

~~~java
// Do not predict the printed line order:
// inputs.parallelStream().forEach(System.out::println);
~~~

One run may print numbers in a different order from the next, and that alone does not prove the pipeline is wrong.

If **action execution in encounter order is required**, there is `forEachOrdered()`:

~~~java
StringJoiner output = new StringJoiner(",");
inputs.parallelStream()
        .forEachOrdered(n -> output.add(Integer.toString(n)));
~~~

This is an illustrative snippet with an ordered List; requires importing `java.util.StringJoiner`. Stream documentation guarantees `forEachOrdered` actions run in encounter order and establishes a **happens-before** relationship between earlier and later element actions in that order. Thus building a string this way in the Java 17 program in section 11 can be compared to the sequential version within the scope of sequential actions under that contract.

**Warning:** `forEachOrdered()` does not mean every preceding map/filter callback runs on the same thread or in source chronological order. And writing to a database in action order does not automatically create a transaction; if an exception occurs, Stream does not roll back actions already performed.

### 9.1. Avoid shared mutable state

Wrong:

~~~java
// UNSAFE with parallel forEach:
// List<Integer> output = new ArrayList<>();
// inputs.parallelStream().forEach(output::add);
~~~

Multiple threads can concurrently modify an unsynchronized ArrayList. If you need a List result, use `map(...).toList()` or an appropriate Collector. If external actions are unavoidable, design thread safety and error policies separately; do not use a single matching-result test to "prove" side effects are safe.

## 10. Cases where differences are permitted

### 10.1. unordered() + limit(n)

With an unordered pipeline:

~~~java
List<Integer> anyThree = inputs.parallelStream()
        .unordered()
        .filter(n -> n % 2 == 0)
        .limit(3)
        .toList();
~~~

Because the encounter-order constraint has been dropped, there is no promise that `anyThree` is the **first** three even numbers in the source List. It must have at most 3 matching elements, but the selected subset may vary by execution conditions.

A proper test can check:
- `size() <= 3`.
- Each element is an even number present in the source.
- When the source has at least three matching results and no other stage trims them, the result has three elements.
- Do not hardcode the exact list `[2,4,6]`.

If business rules require taking the **first three even numbers from the source**, **do not add `unordered()`** just hoping to make the pipeline faster.

### 10.2. Unordered Maps

`Map.equals()` can be true even if `entrySet()` is iterated in a different order. If an API expects entries in ascending group order, choose `TreeMap` or represent the output as a sorted list of entries; do not infer order from `HashMap` or default `groupingBy`.

### 10.3. Double and summation order

Combination order in a reduction can affect the lowest bits of floating-point numbers. A discrepancy within the numeric policy's tolerance may be allowed; a very large discrepancy or unexpected NaN still needs investigation. Do not excuse every bug with "parallel floating point can drift".

### 10.4. Logging, peek, map with side effects

Some terminal operations can optimize away intermediate callbacks. For example, `count()` on a List source with a known size may skip calling `map`/`peek` if those steps do not change cardinality.

Do not design tests like:

~~~java
// Not a valid contract test:
// AtomicInteger calls = new AtomicInteger();
// long total = inputs.stream()
//       .peek(n -> calls.incrementAndGet())
//       .count();
// assert calls.get() == inputs.size();
~~~

The number of `peek` invocations is not a business result guaranteed by `count`. If a mandatory action must run for every element, use a terminal action or separate workflow with proper error handling and transactions.

## 11. Complete Java 17 program: contract-based comparison tests

Create the file **SequentialParallelContractDemo.java**. The program uses self-written assertions to run immediately with JDK 17, **without JUnit**. It intentionally prints deterministic output and does not print the arbitrary value of `findAny()`; instead it only prints that the found element is valid.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SequentialParallelContractDemo {
    record Sale(String category, int amount) {}

    static void requireEqual(Object expected, Object actual, String caseName) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(caseName + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    static List<Integer> evenSquares(List<Integer> input, boolean parallel) {
        var stream = parallel ? input.parallelStream() : input.stream();
        return stream.filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .sorted()
                .toList();
    }

    static Map<String, Integer> totals(List<Sale> sales, boolean parallel) {
        var stream = parallel ? sales.parallelStream() : sales.stream();
        return stream.collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)));
    }

    static String orderedText(List<Integer> numbers, boolean parallel) {
        StringJoiner result = new StringJoiner(",");
        var stream = parallel ? numbers.parallelStream() : numbers.stream();
        stream.forEachOrdered(n -> result.add(Integer.toString(n)));
        return result.toString();
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 2, 7, 4, 6, 1, 8, 3, 5, 10);
        List<Integer> seq = evenSquares(numbers, false);
        List<Integer> par = evenSquares(numbers, true);
        requireEqual(seq, par, "ordered pipeline");
        System.out.println("ordered lists equal=" + seq.equals(par));
        System.out.println("even squares=" + par);

        long sequentialSum = numbers.stream().mapToLong(Integer::longValue).sum();
        long parallelSum = numbers.parallelStream().mapToLong(Integer::longValue).sum();
        requireEqual(sequentialSum, parallelSum, "exact long sum");
        System.out.println("long sums=" + sequentialSum + "/" + parallelSum);

        int firstSequential = numbers.stream()
                .filter(n -> n % 2 == 0).findFirst().orElseThrow();
        int firstParallel = numbers.parallelStream()
                .filter(n -> n % 2 == 0).findFirst().orElseThrow();
        requireEqual(firstSequential, firstParallel, "ordered findFirst");
        System.out.println("first even=" + firstParallel);

        List<Sale> sales = List.of(
                new Sale("Books", 10),
                new Sale("Games", 5),
                new Sale("Books", 20),
                new Sale("Food", 8));
        Map<String, Integer> seqGroups = totals(sales, false);
        Map<String, Integer> parGroups = totals(sales, true);
        requireEqual(seqGroups, parGroups, "group totals");
        System.out.println("groups equal=" + seqGroups.equals(parGroups));
        System.out.println("groups=" + parGroups);

        Set<Integer> seqSet = numbers.stream().filter(n -> n % 2 == 0)
                .collect(Collectors.toSet());
        Set<Integer> parSet = numbers.parallelStream().filter(n -> n % 2 == 0)
                .collect(Collectors.toSet());
        requireEqual(seqSet, parSet, "unordered set contents");
        System.out.println("sets equal=" + seqSet.equals(parSet));
        System.out.println("set sorted=" + seqSet.stream().sorted().toList());

        int anyEven = numbers.parallelStream()
                .filter(n -> n % 2 == 0).findAny().orElseThrow();
        if (!numbers.contains(anyEven) || anyEven % 2 != 0) {
            throw new AssertionError("findAny contract");
        }
        System.out.println("findAny valid=true");

        String orderedSequential = orderedText(numbers, false);
        String orderedParallel = orderedText(numbers, true);
        requireEqual(orderedSequential, orderedParallel, "forEachOrdered");
        System.out.println("forEachOrdered equal=" +
                orderedSequential.equals(orderedParallel));

        List<Integer> empty = List.of();
        requireEqual(empty.stream().toList(), empty.parallelStream().toList(),
                "empty input");
        requireEqual(0L, empty.parallelStream().mapToLong(Integer::longValue).sum(),
                "empty sum");
        System.out.println("empty tests=PASS");

        List<Integer> duplicates = List.of(2, 2, 1, 1, 3);
        requireEqual(duplicates.stream().distinct().sorted().toList(),
                duplicates.parallelStream().distinct().sorted().toList(),
                "distinct sorted");
        System.out.println("distinct sorted=" +
                duplicates.parallelStream().distinct().sorted().toList());

        System.out.println("all contract tests=PASS");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SequentialParallelContractDemo.java
java SequentialParallelContractDemo
~~~

**Stdout directly compiled/run and verified:**

~~~text
ordered lists equal=true
even squares=[4, 16, 36, 64, 100]
long sums=55/55
first even=2
groups equal=true
groups={Books=30, Food=8, Games=5}
sets equal=true
set sorted=[2, 4, 6, 8, 10]
findAny valid=true
forEachOrdered equal=true
empty tests=PASS
distinct sorted=[1, 2, 3]
all contract tests=PASS
~~~

### 11.1. Analysis of each assertion

1. **Ordered pipeline:** the two modes create Streams differently yet use the same pure filter/square/sort operations, so the lists are equal; the concrete result is the five even squares.
2. **Long sum:** both pipelines sum 9+2+7+4+6+1+8+3+5+10 = 55. Thread IDs are not used in the check.
3. **findFirst:** the first even number in the source List is 2; even in parallel, the result must follow encounter order.
4. **Groups:** same mapping Books→30, Games→5, Food→8; `TreeMap` makes the printed key order Books, Food, Games.
5. **Set:** membership checked via `Set.equals()`; the `set sorted` line is solely for stable display.
6. **findAny:** the returned value must belong to the source and be even; the test intentionally does not assert "must equal 2" or another fixed number.
7. **forEachOrdered:** on an ordered List source, actions run in encounter order so the two resulting strings are comparable for equality.
8. **Empty source:** two empty lists are equal; the long sum of an empty source is 0.
9. **Distinct:** data contains duplicates, yet `distinct().sorted().toList()` produces `[1,2,3]` in both modes.
10. **Final PASS:** all assertions passed in one run. Across other data and JVMs, tests must still rely on the explained contracts, not on a specific thread-splitting schedule.

### 11.2. Why is there no line printing the findAny value?

If `anyEven` were printed, the output could vary across environments/modes. To include a **valid and verifiable** stdout in documentation, the program only prints the result of **checking the validity condition**. This is an important test design technique: avoid forcing an order-unspecified API to produce fixed output just to make an example easier to write.

### 11.3. Why does the test not allocate an ArrayList inside parallel forEach?

Because doing so introduces a race condition unrelated to contract comparison. Collecting results with a Stream collector or `toList()` is more appropriate. `forEachOrdered` is used specifically to illustrate an ordered terminal action, not as a replacement collector for all data structures.

## 12. Extending tests with JUnit 5

If a project already has **JUnit Jupiter 5**, assertions can be organized more concisely. This section is **illustrative code inside a test class with JUnit 5 dependencies**, not a standalone file compiled with `javac` without libraries.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class StreamContractTest {
    @Test
    void orderedPipelineHasSameResult() {
        List<Integer> input = List.of(9, 2, 7, 4, 6);
        List<Integer> sequential = input.stream()
                .filter(n -> n % 2 == 0).sorted().toList();
        List<Integer> parallel = input.parallelStream()
                .filter(n -> n % 2 == 0).sorted().toList();

        assertEquals(sequential, parallel);
        assertEquals(List.of(2, 4, 6), parallel);
    }

    @Test
    void findAnyReturnsValidElement() {
        List<Integer> input = List.of(9, 2, 7, 4, 6);
        int result = input.parallelStream()
                .filter(n -> n % 2 == 0)
                .findAny().orElseThrow();
        assertTrue(input.contains(result));
        assertEquals(0, result % 2);
    }
}
~~~

**Design point:** the first test asserts a concrete output because the pipeline has a deterministic order; the second test asserts a **valid property** instead of a value not promised by the API.

If JUnit 5 dependencies are not present, use the standalone program from section 11 for Java 17 core testing. Do not put JUnit examples into a `.java` file and expect `javac --release 17` to find the test library automatically.

### 12.1. Property-based testing

For pipelines that must hold across many kinds of data, you can apply property-based testing:

~~~text
For any finite list of integers, with no side effects:
    sort(map(filter(input), f)) in sequential
    equals the same pipeline in parallel (by equals),
    provided f causes no overflow outside defined bounds
    and sort has a valid comparator.
~~~

Use the data generator of an appropriate property-based testing tool to test many combinations; always include empty, duplicate, extreme, and special-data cases. A property must be stated according to the **guaranteed contract**; do not write a property "findAny always equals findFirst" and blame Java when the test fails.

### 12.2. Repeated runs and what they prove

Running a parallel pipeline many times helps uncover race conditions or stateful-callback bugs. However, **passing a hundred test runs does not prove multithreaded safety**; bugs can depend on hard-to-reproduce schedules.

You should also add:
- Code review for stateless/non-interfering callbacks and mutable sources.
- Large-data tests with varying cardinalities.
- Tests for custom Collectors and reductions regarding associativity/combiners.
- Dedicated concurrency testing mechanisms when shared state exists.
- Error and retry tests at I/O boundaries instead of treating Stream as a transaction engine.

## 13. Benchmarking differs from correctness testing

A parallel pipeline returning the right result **does not mean it is faster**. Splitting, scheduling, combining results, memory, and contention overhead can outweigh benefits if the list is small or callbacks are cheap.

Do not put speed into an assertion like "parallel must be faster than sequential", because speed is affected by JVM warm-up, CPU, GC, OS scheduler, and background load.

If you truly need to evaluate performance:
1. Finish the contract-correctness test suite first.
2. Use representative data and volumes.
3. Run JMH or a benchmarking methodology with warm-up, multiple measurements, and dead-code elimination prevention.
4. Compare throughput/latency, memory, GC, and impact on other requests.
5. Choose parallel only when gains are consistent and do not degrade operability.

In particular, for a pipeline that only calls `count()` on a sized source, both modes can compute the result without traversing; enabling parallel creates no "speedup" for work that does not exist.

## 14. Common mistakes when comparing both modes

| Testing mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Comparing `findAny()` with `findFirst()` using `equals` | findAny picks any valid element | Check membership/predicate |
| Comparing `Set.toString()` or iteration order | Set collector does not promise order | Compare `Set.equals()` or sort for display |
| Comparing `HashMap.toString()` by key order | HashMap does not promise order | Compare Map.equals or use TreeMap |
| Using `reduce(0, (a,b)->a-b)` in parallel | Subtraction is not associative | Change operation/design |
| Putting `ArrayList.add` inside parallel forEach | Races/lost elements, not thread-safe | Use toList/collect or proper synchronization |
| Using `peek` to count callbacks | JDK may optimize away callbacks | Check terminal values |
| Comparing `double` with `==` for all data | Precision error and regrouping | Choose domain-appropriate tolerance/numeric type |
| Assuming Lists with the same elements suffice when business order matters | List.equals also checks positions | Choose an order-sensitive assertion |
| Assuming Set.equals suffices when duplicates matter | Set drops occurrence counts | Compare multiset/counts |
| Adding `unordered()` yet still demanding the first List element | Order contract was dropped | Do not use unordered if first element is needed |
| Testing only non-empty sources | Misses Optional.empty and identity | Add empty sources |
| Running once and concluding there are no races | Concurrency bugs can be rare | Review contract and test varied data/schedules |
| Using a concurrently modified List in tests | Two pipelines do not process the same snapshot | Fix/snapshot the source |
| Comparing outputs yet forgetting overflow | Both sums can be wrong for the business | Check numeric range and policy |
| Treating right results as good performance | Correctness and performance are separate goals | Benchmark separately with appropriate tools |

## 15. Practical testing checklist

Before declaring a sequential and parallel pipeline **equivalent**, verify in order:

1. **Data:** do both versions have the same stable logical source, not modified during processing?
2. **Encounter order:** is the source a List/ordered, or HashSet/unordered? Was `unordered()` added?
3. **Intermediate steps:** do `map`/`filter`/`sorted` have the exact same logic in both branches?
4. **Side effects:** do callbacks depend on external variables, clock, random, thread ID, or I/O?
5. **Parallel reduction:** are identity and combination operation associative? Is the combiner right?
6. **Result type:** List, Set, Map, Optional, primitive, or a domain object?
7. **Comparison:** List.equals, Map.equals, Set.equals, optional equality, tolerance, or predicate invariant?
8. **Multiple valid results:** are findAny and unordered limit tested by properties rather than a fixed value?
9. **Action order:** is forEach used instead of forEachOrdered when order is mandatory?
10. **Arithmetic:** are there unchecked integer overflow or floating-point precision constraints?
11. **Collector:** do custom collectors have contract-compliant supplier/accumulator/combiner/finisher?
12. **Empty and singleton sources:** are they included in tests?
13. **Duplicates/ties:** do tests catch lost records, wrong group selection, or missing tie-breakers?
14. **Short-circuiting:** are callback counts confused with result element counts?
15. **Stable tests:** do tests avoid printing/comparing thread scheduling, Set order, or findAny values?
16. **Performance:** is correctness separated from benchmarking, avoiding forcing parallel to be faster?

## 16. Self-check exercises

**Exercise 1.** With `List.of(3,2,4,1)` and pipeline `filter(even).sorted().toList()`, must sequential and parallel produce the same List?

**Answer:** Yes, with pure callbacks and a stable List source; the result is `[2,4]`.

**Exercise 2.** Should you test `findAny()` on `parallelStream()` by requiring the result to equal `findFirst()`?

**Answer:** No. The result only needs to belong to the set satisfying the condition; if the source has no matching elements, the Optional must be empty.

**Exercise 3.** If two Sets have the same elements but different print order, is that a test failure?

**Answer:** No when business logic only cares about membership. Use `Set.equals()`; if order is needed, use an ordered structure/operation.

**Exercise 4.** If two Lists have the same Set of elements in different order, what does `List.equals()` return?

**Answer:** False, because List.equals compares elements at each position; if order is part of the contract, that is a difference worth catching.

**Exercise 5.** Why must subtraction not be used as an associative parallel reducer?

**Answer:** `(a-b)-c` differs from `a-(b-c)`; the result depends on grouping and does not satisfy the reduction contract.

**Exercise 6.** If a `double sum()` differs only in the last digit, should the test be removed automatically?

**Answer:** No. Define a domain-appropriate tolerance policy, handle NaN/∞, and consider a numeric type with the required precision.

**Exercise 7.** A grouped `Map<String,Long>` in sequential and parallel has different printed key order but the same mappings. Which assertion is appropriate?

**Answer:** `Map.equals()` if order is not a requirement; use TreeMap/sorting when report order is required.

**Exercise 8.** Is `parallelStream().forEach(output::add)` with a shared ArrayList a valid test for checking order?

**Answer:** No; the test itself has a race condition and is not thread-safe. Use a Collector or an appropriate terminal operation.

**Exercise 9.** Why should the findAny test print `findAny valid=true` instead of the chosen element?

**Answer:** Because stdout of a specific element is not guaranteed by the API, whereas the result of checking the validity condition is deterministic.

**Exercise 10.** When can sequential and parallel `limit(3)` results be compared element-for-element?

**Answer:** When the source/pipeline has encounter order and no order-dropping operation; limit selects the logical prefix. If `unordered()` is present, do not impose a specific prefix.

## 17. Java 17 references

- [Stream API: pipeline, encounter order, behavioral parameters, and valid optimizations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java Stream package summary: parallelism, ordering, side-effects, and associativity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).
- [Collectors: groupingBy, groupingByConcurrent, toSet, summingInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Collector: characteristics, combiner, identity/associativity, and parallel reduction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).
- [DoubleStream.sum(): floating-point arithmetic and summation order](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html#sum()).
- [List.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).
- [Set.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object)).
- [Map.equals()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

**Conclusion:** Do not test parallel Streams with the rule "everything must behave identically to a sequential loop". Test **the exact contract guaranteed by the API and business domain**: ordered lists compare exact Lists; unordered Sets/Maps compare membership/mappings; reductions use associative operators and valid identities; `findFirst()` follows encounter order, while `findAny()` checks valid values; floating-point numbers need a tolerance policy. A pipeline is considered right when its result satisfies the contract **regardless of how threads are split**, not when logs and execution schedules look the same.
