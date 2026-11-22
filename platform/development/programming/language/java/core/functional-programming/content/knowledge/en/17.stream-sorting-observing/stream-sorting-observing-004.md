# Distinguishing Input Sorting from Result Sorting in Java Stream

## 1. Two Different Questions About Sorting

In Java, the phrase "sort a list" can refer to two different actions:

1. **Sorting directly on the input collection**, changing the order of elements stored by the collection. For example: `list.sort(comparator)`.
2. **Producing a result in sorted order**, leaving the input collection unchanged. For example: `list.stream().sorted(comparator).toList()`.

In functional programming with Stream, there is another dimension of distinction: **placing `sorted()` before or after transformations**. Determine the type and value at the moment of sorting:

```text
Source List<A> → Stream<A> → sorted by A → map(A → B) → Stream<B>
Source List<A> → Stream<A> → map(A → B) → sorted by B → Stream<B>
```

These two pipelines are not automatically equivalent. If the `map` transformation does not preserve the ordering relation, the resulting list of B may differ. For example, sorting strings lexicographically and then taking their lengths does not make the lengths ascending.

Three pieces of information should be stated clearly before choosing an API: **whether the source needs to remain unchanged, which type the sorting criterion belongs to, and at which stage in the pipeline sorting occurs?**

## 2. APIs and Contracts to Remember

| Operation | What Happens | Modifies the Source List? |
| --- | --- | --- |
| `list.sort(comparator)` | Sorts the elements of the list itself; returns `void` | Yes |
| `Collections.sort(list)` | Sorts the list in natural order | Yes |
| `list.stream().sorted()` | Creates a Stream stage that sorts in natural order | No |
| `list.stream().sorted(comparator)` | Creates a Stream stage that sorts using the provided comparator | No |
| `list.stream().sorted().toList()` | Collects elements in sorted order into a result list | No |
| `stream.sorted(c).map(f)` | Sorts the input values of `f` using `c` before transforming | No |
| `stream.map(f).sorted(c2)` | Transforms first, then sorts the resulting values using `c2` | No |

`Stream.sorted` is a **stateful intermediate operation**. Merely creating the `stream.sorted()` pipeline does not mean the entire source has been traversed and sorting is complete; processing typically happens when a terminal operation such as `toList()`, `forEachOrdered()`, or `findFirst()` consumes the pipeline.

`List.sort` is an operation directly on the collection; the list must support replacing elements according to its contract. A list from `List.of(...)` is unmodifiable; a list returned by `Stream.toList()` is also **unmodifiable** by contract. Do not call `sort` directly on them; when modification is needed, create `new ArrayList<>(...)`.

## 3. Complete Java 17+ Example: Source and Result Differ

Save the file `SourceVsResultSortDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SourceVsResultSortDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("bbb", "a", "cc"));

        List<String> alphabetical =
                source.stream().sorted().toList();

        List<Integer> lengthAfterWordSort =
                source.stream()
                        .sorted()
                        .map(String::length)
                        .toList();

        List<Integer> sortedLengths =
                source.stream()
                        .map(String::length)
                        .sorted()
                        .toList();

        System.out.println("source=" + source);
        System.out.println("alphabetical=" + alphabetical);
        System.out.println("word order lengths=" + lengthAfterWordSort);
        System.out.println("sorted lengths=" + sortedLengths);

        List<String> mutableCopy = new ArrayList<>(source);
        mutableCopy.sort(Comparator.naturalOrder());
        System.out.println("copy=" + mutableCopy);
        System.out.println("source again=" + source);
    }
}
```

Compile and run:

```bash
javac SourceVsResultSortDemo.java
java SourceVsResultSortDemo
```

Output:

```text
source=[bbb, a, cc]
alphabetical=[a, bbb, cc]
word order lengths=[1, 3, 2]
sorted lengths=[1, 2, 3]
copy=[a, bbb, cc]
source again=[bbb, a, cc]
```

**Why are the lines different?**

- `alphabetical` is the result of sorting by the natural order of `String`: `a` before `bbb`, then `cc`.
- `sorted().map(String::length)` sorts the strings first, then takes their lengths: `a → 1`, `bbb → 3`, `cc → 2`. Because the sorting criterion is **strings**, the numeric result `[1,3,2]` is not ascending.
- `map(String::length).sorted()` extracts the lengths first, then uses the natural order of `Integer`, yielding `[1,2,3]`.
- `mutableCopy.sort(...)` modifies `mutableCopy`, but does not touch `source` because they are two separate lists. If `source.sort(...)` were called, `source` would change its order in place.

With the same reference to a mutable list, calling `sort` can affect other code holding that reference. Conversely, `Stream.sorted` does not modify the source list; it provides ordering in the result stream.

## 4. Sorting Before vs. After `map`: Which Data Does the Criterion Belong To?

Suppose products have a name and a price:

```text
Product(name, price)
Zebra, 20
Alpha, 90
Cable, 50
Bee,   20
```

If the requirement is **display names by ascending price**, `Product` must first be sorted by `price`, and only then should `name` be extracted. If the requirement is **names in alphabetical order**, extract `name` first and then call `sorted()`.

Create the file `SortProductDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class SortProductDemo {
    record Product(String name, int price) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Zebra", 20),
                new Product("Alpha", 90),
                new Product("Cable", 50),
                new Product("Bee", 20)
        );

        List<String> namesByPrice = products.stream()
                .sorted(Comparator.comparingInt(Product::price))
                .map(Product::name)
                .toList();

        List<String> namesAlphabetically = products.stream()
                .map(Product::name)
                .sorted()
                .toList();

        List<String> namesOriginal = products.stream()
                .map(Product::name)
                .toList();

        System.out.println("original=" + namesOriginal);
        System.out.println("by price=" + namesByPrice);
        System.out.println("by name=" + namesAlphabetically);
    }
}
```

Run:

```bash
javac SortProductDemo.java
java SortProductDemo
```

Output:

```text
original=[Zebra, Alpha, Cable, Bee]
by price=[Zebra, Bee, Cable, Alpha]
by name=[Alpha, Bee, Cable, Zebra]
```

In `namesByPrice`, the comparator receives two `Product` objects and compares the price field. After `map(Product::name)`, the stream is already a `Stream<String>`; price information is no longer present on each element. In `namesAlphabetically`, sorting happens on the name strings themselves.

Do not write:

```java
// The intent "sort names by price" will no longer have enough information:
// products.stream().map(Product::name)
//         .sorted(Comparator.comparingInt(Product::price))
```

This is an **intentionally type-invalid counterexample**: after `map(Product::name)` it is a `Stream<String>`, whereas `Product::price` is a method on `Product`, not `String`.

If products have equal prices and names are required in alphabetical order, write a multi-key comparator **before losing the Product information**:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);

List<String> names = products.stream()
        .sorted(byPriceThenName)
        .map(Product::name)
        .toList();
```

This snippet is placed inside a method of the program where `Product` and `products` are already declared. `thenComparing` creates an explicit secondary key; sorting a second time by name does not always preserve the price-priority rule.

## 5. The Role of Types at Each Step

When reading a multi-stage expression, write out the type diagram:

```text
products.stream()                      Stream<Product>
  .sorted(byPrice)                     Stream<Product>
  .map(Product::name)                  Stream<String>
  .toList()                             List<String>
```

Compared to:

```text
products.stream()                      Stream<Product>
  .map(Product::name)                  Stream<String>
  .sorted()                             Stream<String>
  .toList()                             List<String>
```

The `sorted()` operation does not change the element type of the Stream. `map(...)` is what changes the type, and therefore also changes the value domain that the comparator must understand if sorting is placed after `map`.

No-argument `sorted()` requires elements to support natural ordering (typically via `Comparable`) and values to be mutually comparable. If objects are not comparable, processing may throw `ClassCastException`. For a class or record without a natural order, use `sorted(Comparator.comparing(...))` to specify the key explicitly.

**Distinguish sorting on original data from sorting on transformed data:** If the mapper discards or alters the key, the two pipelines can differ. Only when you prove that the transformation preserves order under the respective comparator can you conclude they produce the same order.

## 6. `sorted()` Before or After `filter()`

With a pure, stateless filter predicate and the same comparator on the same element type, you can usually switch:

```java
numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();

numbers.stream()
        .sorted()
        .filter(n -> n > 0)
        .toList();
```

This is an illustrative snippet inside a method where `numbers` is a collection of numbers. Both approaches keep positive numbers in ascending order.

**The cost can differ:**

- `filter().sorted()` discards unnecessary data first, making the number of elements to sort smaller.
- `sorted().filter()` may sort the entire dataset before discarding elements.

However, do not reorder arbitrarily if the Predicate or Comparator has side effects, depends on state, changes over time, or if a step needs information at a specific stage. In Stream, passed functions should obey non-interference requirements, typically being stateless and not modifying the source being traversed.

## 7. `sorted()` and `limit()`: Changing Position Can Change the Result Itself

This is the easiest case to confuse:

```text
sorted().limit(n):  sort everything, then take the first n elements
limit(n).sorted():  take the first n elements of the source, then sort that group
```

Both produce an ordered output, but **they do not necessarily contain the same elements**.

Create the file `SortStagePlacementDemo.java`:

```java
import java.util.List;

public class SortStagePlacementDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 1, 5, 2, 4);

        System.out.println("sorted then limit=" +
                numbers.stream().sorted().limit(2).toList());

        System.out.println("limit then sorted=" +
                numbers.stream().limit(2).sorted().toList());

        System.out.println("even then sorted=" +
                numbers.stream()
                        .filter(n -> n % 2 == 0)
                        .sorted()
                        .toList());

        System.out.println("source=" + numbers);
    }
}
```

Run:

```bash
javac SortStagePlacementDemo.java
java SortStagePlacementDemo
```

Output:

```text
sorted then limit=[1, 2]
limit then sorted=[1, 9]
even then sorted=[2, 4]
source=[9, 1, 5, 2, 4]
```

Explanation:

- The entire list in ascending order is `[1,2,4,5,9]`, so the first two elements after sorting are `[1,2]`.
- The first two elements **before sorting** are `[9,1]`; sorting this group produces `[1,9]`.
- Filtering even numbers first gives `[2,4]`, and sorting does not change the order of those two numbers.
- Even though the result is sorted, the `numbers` list remains intact.

Similarly, carefully check the placement of `skip(n)`, `findFirst()`, or selection operations that depend on encounter order. If the business definition is "the n cheapest products", the order must normally be `sorted(byPrice).limit(n)`; if you only want to sort the first products taken from the source, that is `limit(n).sorted(byPrice)`.

## 8. Stability and Encounter Order

A stream from a `List` has an **encounter order** matching the list order. For such an ordered source, `Stream.sorted(comparator)` is **stable**: elements considered equal by the comparator (comparison result equals 0) retain their relative order from the input.

In the product example, `Zebra` and `Bee` both have price 20, so they still appear in the order Zebra then Bee when sorted by price from an ordered list. For a stream without an encounter order, the specification does not guarantee stable sorting with respect to the original order.

When stable output is needed even if the source changes order, a secondary key can be used:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);
```

This is an illustrative snippet in the context of the already declared `Product` record. The second criterion eliminates the situation where different names with the same price are still treated as "equal according to the comparator".

Do not use comparators with inconsistent logic, non-transitivity, or dependence on random variation. A meaningful sort order must be clearly defined; if a comparator returns 0 for multiple distinct objects, you must decide whether that is "the same sort key" allowed to preserve encounter order or whether a secondary key is needed.

## 9. Null, Comparators, Numeric Types, and Precision

### Null

Natural sorting with `sorted()` is usually unsuitable when the source contains null elements. If the contract requires keeping nulls at the end, use a comparator:

```java
List<String> sorted = values.stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .toList();
```

The snippet above assumes `values` is a collection containing possibly null `String` elements, with `List` and `Comparator` imported. If null is invalid data, it is usually filtered/validated beforehand rather than implicitly defining an order for null.

### Numeric Sorting

Use `Comparator.comparingInt(Product::price)` when the getter returns `int`. For `long` or `double`, there are `comparingLong` / `comparingDouble`. Do not subtract two values to compare like `(a, b) -> a.price() - b.price()` if integer overflow is possible; `Integer.compare(a.price(), b.price())` or comparator factory methods are safer.

### Natural Order and Display Order

`String.compareTo` uses Java's natural ordering, not a language/locale-specific sorting algorithm for all kinds of names. If users need Vietnamese alphabetical order, do not assume `sorted()` automatically provides appropriate collation; you must design a comparator based on the specific locale and normalization requirements. Changes in collation can alter the order without changing the data.

## 10. Observing the Pipeline Properly

During debugging, many people write:

```java
stream.peek(System.out::println).sorted().toList();
```

`peek` is an intermediate operation intended for observation, but **it is not suitable as a mandatory business logging mechanism**. Intermediate stages can be optimized away when they do not affect the terminal result; with parallel streams, the timing/order of side effects is even more complex.

If you only need to verify the order and state of the source, a clearer way is to materialize two independent results:

```java
List<String> before = source.stream().toList();
List<String> after = source.stream().sorted().toList();

System.out.println(before);
System.out.println(after);
System.out.println(source);
```

This snippet is placed inside a method with a `source` variable of type `List<String>`. Each `source.stream()` call creates **a new stream**. Do not call two terminal operations on the same already-consumed stream object.

Another point: creating the pipeline `Stream<String> sorted = source.stream().sorted();` does not necessarily perform the entire sort yet. To inspect the output, call a terminal operation such as `sorted.toList()` once. Afterward, if you want to sort again with a different comparator, build a new stream.

## 11. Cost and Data Scope

Sorting is an operation that requires **global** observation of the elements to be sorted, typically taking around `O(n log n)` time for comparison-based sorting algorithms and requiring memory to store intermediate ordering depending on the implementation.

- If you can safely filter beforehand, `filter(...).sorted()` can help reduce the input size to sorting.
- If you only need the smallest or largest element, `min(comparator)` or `max(comparator)` usually expresses the intent better than sorting everything and taking one element.
- `sorted().limit(n)` on a finite source generally needs to examine the entire source to know the global top n elements, even if the output is small.
- `limit(n).sorted()` can be lighter because it only sorts the first n elements, but that is **a different question about the data**.
- On an infinite stream, global sorting generally cannot complete to produce the first element; you must choose a way to bound the source and design a different operation.
- Using a parallel stream does not automatically make sorting faster; you must weigh coordination overhead, comparator cost, and actual scale.

Only adjust stage order after verifying business equivalence. Avoid using side effects in `map`, `filter`, or comparators to infer execution counts and order if the pipeline may be optimized.

## 12. Common Mistakes and Fixes

1. **Mistaking `Stream.sorted()` for an operation that modifies the source collection.** Check `source` again after the terminal operation; when you want to modify the source, use `List.sort` on a mutable list.
2. **Calling `sort` on `List.of(...)` or a list from `Stream.toList()`.** Both types of lists do not allow modification; copy into an `ArrayList`.
3. **Sorting before `map` while expecting the result after `map` to be ascending.** If the mapper does not preserve order, sort by the post-transformation value or reconsider the criterion.
4. **Sorting after `map` while needing information that was already lost.** Move sorting before `map` so the comparator can still access the original object.
5. **Swapping `sorted()` and `limit()` without considering meaning.** The two orders can select two different sets of elements.
6. **Omitting a comparator when objects have no natural ordering.** Use a comparator defined by the business key.
7. **Forgetting elements with equal keys.** Stable sorting is conditional on encounter order; use `thenComparing` when a deterministic order is needed.
8. **Using `(a, b) -> a - b` to compare large ints.** Prone to overflow; use `Integer.compare` or comparator factories.
9. **Not considering null.** Filter nulls beforehand or use `Comparator.nullsFirst/nullsLast` according to the contract.
10. **Using `peek` to mutate important state.** Keep intermediate transformations free of side-effect dependencies; verify the collected result via a terminal operation.
11. **Modifying the source list while the stream is running.** Can violate non-interference and cause wrong results, exceptions, or unstable behavior.
12. **Reusing a stream after `toList()`.** Each new pipeline should start from a fresh stream.

## 13. Self-Check Exercise

Suppose:

```java
List<String> words = List.of("zz", "a", "bbb");

List<Integer> a = words.stream()
        .sorted().map(String::length).toList();

List<Integer> b = words.stream()
        .map(String::length).sorted().toList();

List<String> c = words.stream()
        .sorted(Comparator.comparingInt(String::length))
        .limit(2).toList();

List<String> d = words.stream()
        .limit(2)
        .sorted(Comparator.comparingInt(String::length))
        .toList();
```

This snippet is inside a Java 17 method with `List` and `Comparator` imported.

Questions: What are `a`, `b`, `c`, `d` respectively? Does the `words` list change order? Why can pipelines `c` and `d` differ when the data changes?

**Answers:**

- The lexicographical order of the strings is `["a","bbb","zz"]`, so `a = [1,3,2]`.
- The lengths of the source are `[2,1,3]`; sorting numbers ascending gives `b = [1,2,3]`.
- Sorting all words by length and then selecting the first two words gives `c = ["a","zz"]`.
- The first two words of the source are `["zz","a"]`, and sorting them by length also gives `d = ["a","zz"]`. **Matching results on this dataset are coincidental with respect to the structure of the operations**, and do not prove the two pipelines are equivalent.
- With `List.of("long", "bbb", "a")`, sorting everything and taking the two shortest words gives `["a","bbb"]`; taking the first two words and sorting only gives `["bbb","long"]`.
- `words` keeps its original order because all pipelines only use `Stream.sorted`.

## 14. Summary Rules

When sorting is needed in functional programming, check four questions:

1. **Does the source collection need to be modified?** If yes, use a collection-mutating API; if no, use a pipeline that sorts the result.
2. **At the moment of sorting, what type does each element have?** Before `map` it is the source type; after `map` it is the transformed type.
3. **Which key is the comparator sorting by?** Lexicographical order, price, length, secondary keys, and nulls must be decided explicitly.
4. **Do stages like `filter`, `limit`, `skip` come before or after sorting?** Their placement is part of the semantics and processing cost.

**Remember:** `List.sort` modifies the list; `Stream.sorted` sorts elements emitted from the pipeline without modifying the source. `sorted().map(...)` sorts **the input to the transformation**, whereas `map(...).sorted()` sorts **the output of the transformation**. Choose the right sorting placement before optimizing or shortening code.

**References:** Java SE API: `List.sort`, `Stream.sorted`, `Stream.toList`, `Comparator`; Java Stream package specification on stateful intermediate operations, ordering, and non-interference.