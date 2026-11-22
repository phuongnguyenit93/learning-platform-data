# Balancing Conciseness, Readability, and Processing Cost in Functional Design in Java

In Java, **functional programming** helps express data transformations using `Stream`, lambdas, method references, `Optional`, and pure functions. However, **concise** code is not automatically **readable** or **efficient**. A single-line pipeline can hide multiple list traversals, database queries, or object allocations; conversely, splitting code into too many tiny helpers can force readers to jump constantly across functions.

The goal is not to minimize character count, but to find a balance among:

1. **Business correctness**: the order of filtering, selection, and aggregation produces accurate results.
2. **Readability/maintainability**: the next developer understands data types, the meaning of steps, error handling, and empty cases.
3. **Processing cost**: time, memory, I/O, algorithmic complexity, boxing, early termination capability, and parallelism overhead.

**Practical principle:** First write correct and readable code; then identify significant costs, measure with real data, and optimize **bottlenecks** without sacrificing correctness or introducing unnecessary complexity.

## 1. Three Dimensions of Trade-Offs and Questions to Answer

| Criterion | Question | Signs to review |
| --- | --- | --- |
| Conciseness | Does this step genuinely reduce boilerplate? | A single line has too many nested conditions or hard-to-read ternaries. |
| Readability | Can you clearly see source → filter → transform → collect? | Long lambdas, `x`/`y` variable names, many `map` calls changing types unclearly. |
| CPU cost | Is the same data traversed, sorted, or hash-looked up repeatedly? | Nested `stream()` inside `filter`, unnecessary `sorted`. |
| Memory cost | Are large intermediate lists, maps, or wrapper objects created? | `boxed()` then unboxing, `toList()` only to stream again. |
| I/O | Are network/database calls or file opens happening in each mapper? | N+1 queries, blocking in parallel streams, missing resource closing. |
| Source characteristics | Is the source small/large, ordered, empty, single-use, or infinite? | Assuming `Stream` is reusable or processing an infinite source with `toList()`. |
| Testing | Are edge cases well-defined? | Nulls, duplicates, ordering, large numbers, empty sources ignored. |

An `O(n)` transformation can become `O(n²)` when nesting a full-list scan inside each element. This is usually a much bigger problem than saving a few characters in a lambda.

## 2. Short, Clear Stream Pipelines That Express Intent

Suppose the requirement is **to get customer names with invoices of 100 or more, remove duplicate names, and sort alphabetically**. For discrete data, a pipeline with clear method names is often easier to read than manual list-updating code.

Create the file `ReadablePipelineDemo.java`:

~~~java
import java.util.List;

public class ReadablePipelineDemo {
    record Order(String customer, int total) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Chi", 130),
                new Order("An", 75),
                new Order("Bình", 160),
                new Order("Chi", 210),
                new Order("An", 120));

        List<String> customers = orders.stream()
                .filter(order -> order.total() >= 100)
                .map(Order::customer)
                .distinct()
                .sorted()
                .toList();

        System.out.println(customers);
    }
}
~~~

~~~bash
javac --release 17 ReadablePipelineDemo.java
java ReadablePipelineDemo
~~~

Output:

~~~text
[An, Bình, Chi]
~~~

**Why does this pipeline read well?** Each step has a clear role:

~~~text
List<Order>
  .stream()                       → Stream<Order>
  .filter(Order -> boolean)        → Stream<Order>
  .map(Order -> String)            → Stream<String>
  .distinct()                      → Stream<String>
  .sorted()                        → Stream<String>
  .toList()                        → List<String>
~~~

`filter` selects objects first, `map` then extracts names; `distinct` removes duplicate names, and `sorted` orders strings naturally. The `List` source has encounter order, and the result is sorted so display order is predictable.

**Potential downside:** `distinct` maintains deduplication state, and `sorted` is a stateful operation with sorting cost. Those steps are necessary when **business requirements** genuinely require deduplication and sorting. If you only need to count qualifying invoices, do not keep unnecessary steps just to make code look “functional”.

## 3. A Shorter Stream Is Not Always Better Than a Loop

The two approaches below have the same goal: summing the quantities of active products. When rules are simple, both a loop and a Stream can be easy to understand; there is no need to turn every loop into a Stream.

Create the file `LoopVsStreamDemo.java`:

~~~java
import java.util.List;

public class LoopVsStreamDemo {
    record Item(boolean active, int quantity) {}

    static long totalWithLoop(List<Item> items) {
        long total = 0;
        for (Item item : items) {
            if (item.active()) {
                total += item.quantity();
            }
        }
        return total;
    }

    static long totalWithStream(List<Item> items) {
        return items.stream()
                .filter(Item::active)
                .mapToLong(Item::quantity)
                .sum();
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item(true, 4),
                new Item(false, 9),
                new Item(true, 6));

        System.out.println("loop=" + totalWithLoop(items));
        System.out.println("stream=" + totalWithStream(items));
    }
}
~~~

~~~bash
javac --release 17 LoopVsStreamDemo.java
java LoopVsStreamDemo
~~~

Output:

~~~text
loop=10
stream=10
~~~

`mapToLong(Item::quantity)` intentionally uses `long` addition to reduce overflow risk compared to an `int` sum. Both approaches have **`O(n)`** time complexity and need no intermediate list; however, exact runtime cost depends on JIT, data size, and environment.

Loops are often appropriate when complex control flow is needed, with `break`/`continue` across multiple states, or when one loop collects multiple specialized results. Streams are often appropriate for short filter/transform/collect chains where steps are independent and have no side effects. **Do not decide based solely on the impression that “having a lambda means more modern”.**

## 4. Avoid Overly Long Lambdas: Name Business Rules

A lambda packing null checks, status checks, thresholds, and formatting into one block may be short in line count but hard to read:

~~~java
// Illustrative with declared orders variable and Order type.
orders.stream().filter(o -> o != null && o.active()
        && o.total() >= 100 && o.customer() != null)
        .map(o -> o.customer().trim().toUpperCase())
        .toList();
~~~

As conditions grow, name steps that carry **business meaning**. Method references or small, well-named methods make the pipeline read like a specification.

Create the file `NamedRulesDemo.java`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NamedRulesDemo {
    record Order(String customer, int total, boolean active) {}

    static boolean isEligible(Order order) {
        return order != null
                && order.active()
                && order.total() >= 100
                && order.customer() != null;
    }

    static String normalizedCustomer(Order order) {
        return order.customer().trim()
                .toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order(" An ", 120, true),
                new Order("Bình", 80, true),
                null,
                new Order("Chi", 150, false),
                new Order("Mai", 130, true));

        List<String> names = orders.stream()
                .filter(NamedRulesDemo::isEligible)
                .map(NamedRulesDemo::normalizedCustomer)
                .toList();

        System.out.println(names);
    }
}
~~~

~~~bash
javac --release 17 NamedRulesDemo.java
java NamedRulesDemo
~~~

Output:

~~~text
[AN, MAI]
~~~

`isEligible` includes null checks, so `normalizedCustomer` can assume the passed element is non-null and has a customer name. That is a **pipeline invariant**; if `normalizedCustomer` is called elsewhere, its contract must be clarified or checked separately.

Naming should be based on **purpose**, not merely extracting every tiny operation into a helper like `getTotal()` just to shorten a lambda. Too many one-line forwarding methods without new meaning force readers to jump around more.

## 5. Choosing Operation Order: Push Cheap Filters Earlier When Semantically Valid

For independent pipelines, it is often beneficial to perform a simple filter before an expensive transformation:

~~~java
// If the business contract allows:
// filter Orders first, then convert to Report.
orders.stream()
        .filter(Order::active)
        .map(this::expensiveReport)
        .toList();
~~~

The snippet above is **illustrative only inside an instance method** where `Order::active` and `expensiveReport` already exist, not a standalone Java class. Report creation cost is incurred only for retained orders.

Writing `.map(this::expensiveReport).filter(Report::active)` may compute reports for the entire source and sometimes is not even equivalent if `Report.active` means something different from `Order.active`. **Only reorder when preserving meaning, errors, and valid side effects.** Do not assume a `filter` whose predicate relies on data **after** `map` can be placed before `map`.

Pay attention to:

- `filter` generally preserves element type and can reduce downstream work.
- `map` changes type from `T` to `R`; lambdas after `map` no longer receive `T`.
- `sorted` has stateful cost and may process the whole set; omit it if ordering is not needed.
- `distinct` only deduplicates the **element type at that position**; placing it before or after `map` can yield different results.
- `limit` and `findFirst` can short-circuit, but filter/map order and encounter order affect what “first” means.

## 6. Conciseness Can Hide an `O(n²)` Nested Traversal

A concerning mistake is calling `stream().anyMatch(...)` over an entire list **inside** a `filter` traversing another list. If both lists grow with `n`, this approach can perform roughly `n²` comparisons in the worst case.

For example, requirement: **keep only orders whose `customerId` is in the valid customer list**.

Simple but potentially slow approach:

~~~java
// Illustrative inside a method with orders and allowedIds.
List<Order> selected = orders.stream()
        .filter(o -> allowedIds.stream()
                .anyMatch(id -> id.equals(o.customerId())))
        .toList();
~~~

With `orders` of `n` elements and `allowedIds` of `m` elements, this has worst-case cost around **`O(n × m)`**. Using a `HashSet` makes membership lookup faster on average:

~~~java
// Illustrative, allowedIds is List<String>.
Set<String> allowed = new HashSet<>(allowedIds);
List<Order> selected = orders.stream()
        .filter(o -> allowed.contains(o.customerId()))
        .toList();
~~~

Building the set costs roughly `O(m)` on average, then `n` `contains` calls cost `O(1)` on average, giving expected total around **`O(n + m)`** with a good hash. This is **average-case analysis**, not an absolute worst-case time guarantee for every hash collection.

### Complete Java example: filtering by an ID set

Create the file `MembershipLookupDemo.java`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class MembershipLookupDemo {
    record Order(String code, String customerId) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O1", "C1"),
                new Order("O2", "C9"),
                new Order("O3", "C2"),
                new Order("O4", "C1"));

        List<String> allowedIds = List.of("C1", "C2");
        Set<String> allowed = new HashSet<>(allowedIds);

        List<String> selected = orders.stream()
                .filter(order -> allowed.contains(order.customerId()))
                .map(Order::code)
                .toList();

        System.out.println(selected);
    }
}
~~~

~~~bash
javac --release 17 MembershipLookupDemo.java
java MembershipLookupDemo
~~~

Output:

~~~text
[O1, O3, O4]
~~~

`HashSet` is created **once before** the pipeline. Do not construct `new HashSet<>(allowedIds)` inside each `filter` invocation, as that allocates memory and repeats work. If IDs can be null, clarify the contract and choose an appropriate structure; this example uses non-null IDs.

## 7. N+1 Queries: Do Not Call the Database in Every `map` Just for Compact Code

A mapper can look very natural:

~~~java
// Illustrative, repository is a blocking I/O service:
List<Customer> customers = orders.stream()
        .map(order -> repository.loadCustomer(order.customerId()))
        .toList();
~~~

If `loadCustomer` executes **one database query per element**, a list of 1,000 orders can trigger 1,000 queries — even though the code is only a few lines. That is a form of the **N+1 query problem** (depending on how the source list was fetched) and typically incurs network, connection pool, serialization, transaction, and retry overhead.

A better option, when the API/data model supports it:

1. Collect the needed customer IDs into a set.
2. Use a **batch** query by ID set, with pagination/chunking if the backend has limits.
3. Build a `Map<ID,Customer>`.
4. Use in-memory `map`/lookup to join the data.

These steps are longer than `map(repository::load)`, but make I/O round trips explicit and make timeouts/data volume easier to control. Still, **a batch query is not always faster** if the set is tiny, the backend has special constraints, or transactional consistency is required; measure on the real system.

Do not use `parallelStream()` to fix N+1 queries by firing 1,000 concurrent requests. It can overload the connection pool/backend and starve worker threads in the common fork/join pool. For blocking I/O, use concurrency limits, timeouts, and a dedicated executor/async model.

## 8. Boxing/Unboxing: Avoid Round-Trip Conversions When Processing Many Numbers

`Stream<Integer>` processes wrapper elements; `IntStream`, `LongStream`, and `DoubleStream` process corresponding primitives. A pipeline:

~~~java
long result = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .boxed()
        .mapToLong(Integer::longValue)
        .sum();
~~~

takes the path `int → Integer → long`. If `Integer` objects are not actually needed, you can write:

~~~java
long result = java.util.stream.IntStream.rangeClosed(1, 100_000)
        .asLongStream()
        .sum();
~~~

In Java 17, both expressions produce the same sum `5_000_050_000`. The `long` type matters because the sum exceeds `int` range.

However, `boxed()` is **not wrong** when the output or a library genuinely requires `List<Integer>` or `Map<Integer,V>`. The goal is to avoid converting primitives to wrappers and back to primitives just out of habit of writing `map` on an object stream.

Create the file `PrimitivePipelineDesignDemo.java`:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitivePipelineDesignDemo {
    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 100_000)
                .asLongStream()
                .sum();

        List<Integer> firstFive = IntStream.rangeClosed(1, 5)
                .boxed()
                .toList();

        System.out.println("sum=" + sum);
        System.out.println("firstFive=" + firstFive);
    }
}
~~~

~~~bash
javac --release 17 PrimitivePipelineDesignDemo.java
java PrimitivePipelineDesignDemo
~~~

Output:

~~~text
sum=5000050000
firstFive=[1, 2, 3, 4, 5]
~~~

Use `mapToInt`/`mapToLong` when performing numeric operations and corresponding counts/sums. For monetary amounts requiring precision, do not use `double` just to keep the pipeline short: prefer minor units with overflow checks or `BigDecimal` per the business contract.

## 9. Materialization: Is `toList()` Followed by `stream()` Again Necessary?

A pipeline like:

~~~java
// Illustrative, source is Collection<Order>.
List<Order> filtered = source.stream()
        .filter(Order::active)
        .toList();

List<String> names = filtered.stream()
        .map(Order::customer)
        .toList();
~~~

creates an **intermediate list**. If `filtered` is only used once, you can chain directly:

~~~java
List<String> names = source.stream()
        .filter(Order::active)
        .map(Order::customer)
        .toList();
~~~

The second approach avoids storing `filtered` separately and is usually cleaner and more memory-efficient. Still, **materialization is reasonable** when the intermediate result is needed for multiple queries, when a point-in-time snapshot is needed, for debugging, or to separate processing stages.

Especially with single-use sources (I/O streams, iterators), materializing lets you reread results if the data is small enough; but it has memory cost and is unsuitable for infinite sources.

In Java 17, `Stream.toList()` returns a list that **does not support structural modification**. It does not deep-copy mutable objects inside; a fully immutable snapshot requires immutable elements or appropriate copying.

## 10. Choose the Right Terminal Operation to Reduce Unnecessary Work

Do not collect a large list just to check whether any element satisfies a condition:

~~~java
// No need to create a list if only asking whether any match exists:
boolean hasMatch = orders.stream()
        .filter(o -> o.total() > 100)
        .toList()
        .size() > 0;
~~~

More natural approach:

~~~java
boolean hasMatch = orders.stream()
        .anyMatch(o -> o.total() > 100);
~~~

`anyMatch` is a **short-circuit terminal operation**: it can stop as soon as it finds one matching element. `filter(...).toList().size()` collects all filtered results before counting; besides traversal cost, it can allocate an unnecessary list.

Terminal operations have different semantics:

| Question | Usually appropriate API | On empty source |
| --- | --- | --- |
| Does at least one element match? | `anyMatch(p)` | `false` |
| Do all elements match? | `allMatch(p)` | `true` |
| Do no elements match? | `noneMatch(p)` | `true` |
| First element in encounter order? | `findFirst()` | `Optional.empty()` |
| Count elements in pipeline? | `count()` | `0L` |
| Sum primitives? | `mapToLong(...).sum()` | `0L` |
| Collect all into a list? | `toList()` | Empty list |

**Optimization must preserve the question's meaning.** Do not replace `findFirst` with `findAny` just to relax ordering constraints if the business logic needs the first object in source order. Do not replace `allMatch` with `anyMatch`: one requires all elements, the other only one witness.

## 11. The `Optional` Case: Handle Absence Clearly Rather Than Writing Ultra-Short Code

In a pipeline, `findFirst`, `min`, `max`, or `reduce` without identity returns `Optional<T>`. Instead of calling `get()` unconditionally, choose a clear contract:

~~~java
// Illustrative with a Stream<Order>:
String name = orders.stream()
        .filter(o -> o.total() >= 100)
        .map(Order::customer)
        .findFirst()
        .orElse("No matching customer");
~~~

This reads clearly: if not found, return a fallback message. If absence is an error, use `orElseThrow(() -> new IllegalStateException(...))` with an appropriate message.

`Optional` should not be used as a replacement for **all** program control flow or to hide data errors. With complex branching, an `if` with clear state names can be more readable than deeply nested `map/flatMap/orElseGet` chains.

`orElse(expensiveFallback())` evaluates the fallback argument before calling the method, even when the Optional has a value; if the fallback is costly, use `orElseGet(() -> expensiveFallback())` so it is only called when absent. Both snippets are **illustrative**, not standalone programs.

## 12. `flatMap`: Use When Resolving Multi-Valued Structures, Not Just to Shorten Code

Given a list of member groups:

~~~text
List<List<String>>
    .stream()                → Stream<List<String>>
    .map(List::stream)       → Stream<Stream<String>>
    .flatMap(List::stream)   → Stream<String> (replaces map at the same position)
~~~

`map` and `flatMap` in the diagram are **two different choices**, not consecutive calls.

Create the file `FlattenReadableDemo.java`:

~~~java
import java.util.List;

public class FlattenReadableDemo {
    public static void main(String[] args) {
        List<List<String>> groups = List.of(
                List.of("An", "Bình"),
                List.of("Chi"),
                List.of());

        List<String> all = groups.stream()
                .flatMap(List::stream)
                .toList();

        System.out.println(all);
    }
}
~~~

~~~bash
javac --release 17 FlattenReadableDemo.java
java FlattenReadableDemo
~~~

Output:

~~~text
[An, Bình, Chi]
~~~

`flatMap` is clear in meaning when one source element corresponds to 0 or more result elements. However, with a huge nested list, `flatMap` performance also depends on source characteristics and the terminal operation; do not conclude it is always faster than nested loops. When the need is clear and avoids multiple intermediate variables, it generally improves readability.

## 13. Boundaries of Pure Functions and Side Effects

In functional design, lambdas in `map`, `filter`, and `sorted` should be **stateless and non-interfering**. Using them to push data outward makes code shorter but very error-prone:

~~~java
// Concurrency-unsafe when using parallel:
List<String> shared = new ArrayList<>();
names.parallelStream().forEach(shared::add);
~~~

`ArrayList` is not safe when multiple threads add concurrently. A more correct pipeline when a list is needed:

~~~java
List<String> selected = names.parallelStream()
        .filter(s -> !s.isBlank())
        .toList();
~~~

Both illustrative snippets sit inside a method with `names: List<String>` and appropriate imports. `toList()` collects results via Stream mechanisms; for ordered sources it preserves encounter order, which does not mean lambdas run sequentially.

**Side effects also hurt readability.** A mapper that queries a database, mutates a cache, and returns a string makes it hard for readers to know its true function and cost. Replace it with independent phases: fetch data, perform pure transformations, then execute controlled I/O.

Do not rely on `peek` for business execution: it is primarily useful for observation and is not guaranteed to run once per element in every pipeline/terminal operation structure due to optimizations and short-circuiting.

## 14. `parallel()` Is Not a Free Optimization

A short pipeline with `.parallel()` can be **slower** due to:

- Cost of splitting data via `Spliterator`;
- Scheduling and coordinating tasks on fork/join;
- Combining local results in `reduce` or `collect`;
- Stateful operations such as `sorted`, `distinct`, `limit` on ordered streams;
- Memory contention, cache misses, GC, and synchronization contention;
- Blocking I/O in `map` causing workers to wait and starving the common pool.

`parallel()` is usually worth trying when the source is **large enough and easy to split** (arrays, `ArrayList`), computations are **CPU-bound** and independent, combiners are cheap, and there are no side effects or awkward ordering requirements. Even then, **benchmark with real data**.

If a pipeline performs blocking HTTP/JDBC/file I/O, prefer designs that bound concurrency, manage timeouts, and consider dedicated I/O/async executors instead of wrapping casually with `parallelStream()`. Concise code like `ids.parallelStream().map(api::fetch).toList()` can trigger an uncontrollable number of concurrent calls.

## 15. Readability When Sorting and Grouping Data

With multiple sort keys, `Comparator.comparing(...).thenComparing(...)` is usually easier to read than a multi-branch manual comparison lambda. However, when a key can be null, concise code like `Comparator.comparing(Person::department)` can throw `NullPointerException`.

Illustrating a comparator with an explicit policy:

~~~java
// Illustrative with Person::department returning nullable String
// and Person::age returning int:
Comparator<Person> comparator = Comparator.comparing(
        Person::department,
        Comparator.nullsLast(Comparator.naturalOrder()))
        .thenComparingInt(Person::age);
~~~

This snippet assumes **Person is non-null** and `Comparator` is imported. Wrapping `nullsLast` around the **key** comparator differs from wrapping it around the **whole Person** comparator. When data is nullable or has multiple keys, a few extra lines to describe the exact null policy are worth it.

`Collectors.groupingBy(classifier)` producing `Map<K,List<T>>` can express intent more clearly than a loop manually managing `computeIfAbsent`, especially with downstream collectors like `summingInt`, `mapping`, or `counting`. However, if the source is empty or keys are null, check the collector's contract; do not assume it accepts null keys or creates groups that never appeared.

## 16. Practice Exercise: Customer Report with Total Spending by ID

Problem: each order has a customer ID and a `long` `amount`. Create a report of total value per customer, sorted by customer ID, **without repeatedly scanning** to find each customer's total.

Create the file `FunctionalReportDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class FunctionalReportDemo {
    record Order(String customerId, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("C2", 40L),
                new Order("C1", 20L),
                new Order("C2", 15L),
                new Order("C1", 5L));

        Map<String, Long> totalByCustomer = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::customerId,
                        TreeMap::new,
                        Collectors.summingLong(Order::amount)));

        totalByCustomer.forEach((id, amount) ->
                System.out.println(id + "=" + amount));
    }
}
~~~

~~~bash
javac --release 17 FunctionalReportDemo.java
java FunctionalReportDemo
~~~

Output:

~~~text
C1=25
C2=55
~~~

`groupingBy` groups by `customerId`, `summingLong` sums `amount` per group, and `TreeMap::new` makes key iteration order deterministic in the example. This clearly expresses the output structure `Map<String,Long>` without calling `orders.stream().filter(...)` separately **for each customer**.

Note that `summingLong` and `long` addition still risk overflow if values exceed the `long` range. For money requiring precision/overflow checks, choose an appropriate value model. If key ordering is not needed, omit `TreeMap` and use a simpler `groupingBy` overload to avoid tree-maintenance cost.

## 17. Measure Performance Properly Instead of Optimizing by Intuition

Do not conclude “Stream is faster than a loop” or “loop is faster than Stream” from a single `System.nanoTime()` measurement. Results are affected by JIT, warmup, GC, CPU throttling, escape analysis, input data, cache warmth, and compiler/JVM optimizations.

If performance matters:

1. Define **representative inputs**: size, filter selectivity, duplicate key distribution, run count, nullable data.
2. Verify **equivalence of correctness** across alternatives (same results, same ordering/null/overflow policies).
3. Measure **end-to-end** if I/O or network costs are significant.
4. Use **JMH** for CPU microbenchmarks: warmup, multiple iterations, benchmark state, forks, and proper result consumption.
5. Observe **allocations, GC, p95/p99 latency, and throughput**, not just single-call time.
6. Keep an optimization only if the gain is significant, stable, and does not make code excessively hard to understand.

Do not construct a `List` inside each benchmark iteration of the algorithm alone if one candidate does not pay that same initialization cost. Do not compare implementations with different semantics or different filtered elements. For I/O, microbenchmarking a `map` function is not enough to understand backend, connection pool, and retry costs.

Algorithmic complexity usually matters more than micro-tuning: switching from `O(n × m)` to an `O(n + m)` Set lookup can yield far greater gains than replacing a lambda with a method reference or shaving off a minor call.

## 18. When Should You Keep a Loop Instead of Chaining More Streams?

**An explicit loop** can be better when:

- Business state must change step by step, with multiple `break/continue` branches hard to express via Stream;
- Checked exceptions or per-element resource rollbacks must be handled;
- Multiple correlated results must be collected where a custom Collector would be complex;
- The operation requires clear sequential ordering and controlled side effects;
- Profiling confirms a tiny hot path incurs significant pipeline overhead.

**A clear Stream** is usually suitable when:

- The source → filter → transform → collect chain has easy-to-read step names;
- Processing functions are pure and do not rely on external mutable state;
- Specialized APIs fit naturally, such as `anyMatch`, `findFirst`, `mapToLong`, `groupingBy`;
- Composability and per-transformation unit testability are desired.

Loops are not “less functional” in terms of software quality; functional thinking helps in both styles: **limiting side effects, separating pure logic, naming meaningfully, and managing data consistently**.

## 19. Common Mistakes to Avoid

1. **Minimizing line count at all costs:** a long lambda packed with side effects is harder to maintain than a few named helpers.
2. **Splitting into too many tiny methods:** jumping through 5 methods just to read `x -> x.getValue()` breaks logical flow.
3. **Using a nested Stream inside `filter` for membership lookup:** easily turns `O(n)` into `O(n × m)`; preindex with a `Set` when appropriate.
4. **Calling database/network inside each `map`:** N+1 I/O can dominate execution time.
5. **Collecting `toList()` then streaming again unnecessarily:** adds memory and extra traversal; chain directly if used only once.
6. **Round-trip boxing/unboxing:** `int → Integer → int` in large numeric pipelines can add overhead.
7. **Adding `sorted` or `distinct` to look “clean” without business need:** wastes CPU/memory and can change semantics.
8. **Using `count()` or `toList()` to answer an existence question:** `anyMatch` can short-circuit.
9. **Using `Optional.get()` when presence is uncertain:** can throw `NoSuchElementException` on empty sources.
10. **Hiding side effects in `peek`, `map`, `filter`:** creates dependence on lazy/short-circuit evaluation.
11. **Calling `parallel()` as a default optimization:** scheduling, combiners, boxing, stateful ops, and I/O can make it slower.
12. **Assuming `Stream.toList()` is a mutable List:** on Java 17 the returned list does not support structural modification.
13. **Arbitrarily reordering `filter`, `map`, `distinct`:** can change types and result semantics.
14. **Reusing a Stream instance:** terminal operations consume the stream; create a new stream from the source if reprocessing is needed.
15. **Ignoring collector null/duplicate policies:** `toMap` can throw on duplicate keys, and `groupingBy` does not accept null keys by default.
16. **Running a single benchmark on tiny data:** does not reflect JIT, GC, saturation, or real workloads.

## 20. Three-Axis Code Review Checklist

Before finalizing a functional pipeline, ask yourself:

- **Meaning:** can someone else read the step names and understand the output requirement?
- **Conciseness:** which lines are genuinely redundant, and which should stay to explain a business decision?
- **State:** are lambdas pure, stateless, and free from mutating the source or shared state?
- **Types:** after each `map`/`flatMap`/primitive conversion, what is the element type?
- **Algorithm:** is there a repeated list scan per element, repeated I/O query, or unnecessary sort?
- **Memory:** are unnecessary intermediate Lists/Maps or boxing being created?
- **Short-circuiting:** is the goal all elements or finding just one matching element?
- **Source:** could it be empty, null, duplicated, huge, infinite, or single-use?
- **Ordering:** is encounter order needed, and does the result depend on `findFirst`/`sorted`?
- **Cost:** has performance been measured properly on a representative workload? Is the optimization worth it?
- **Design:** is there a clearer standard Java method/collector that preserves meaning?
- **Testing:** are empty, single-element, large-data, duplicate-key, boundary-value, and error-handling cases tested?

**Remember:** Writing good functional code does not mean “the longer or shorter the pipeline, the better.” A quality design clarifies **business intent**, keeps transformations simple, recognizes the costs of **re-traversal, sorting, boxing, I/O, and parallelism**, and optimizes only after understanding the algorithm and measuring the real bottleneck. **Concise enough, readable first, optimize with evidence.**
