# Do Not Use a Shared Mutable Accumulator Object in reduce() — Java Stream

## 1. Objectives

**Stream.reduce()** is a reduction operation that combines multiple elements into a single result. It is well-suited for computing sums, products, maximum values, or aggregating with a combining operation that is **associative** and has an **identity element**.

A dangerous mistake is passing a **mutable object**, such as an **ArrayList**, **StringBuilder**, **HashMap**, or an object holding a counter, as the identity for reduce and then **mutating it directly in the accumulator**. In a parallel stream, the identity may be shared across multiple execution branches; the combiner may even receive duplicate references to the same object. Consequences can include race conditions, duplicated elements, data loss, or results depending on the execution strategy. Using a thread-safe container does not fix the reduce contract either.

This lesson helps you:

- Understand the three **reduce()** overloads and the differences between identity, accumulator, and combiner.
- Know why reduce functions must be **stateless**, **non-interfering**, and satisfy the identity, associativity, and compatibility rules.
- Analyze accurately why **reduce(new ArrayList<>(), ...)** or **reduce(new StringBuilder(), ...)** with a mutating lambda is wrong.
- Use **reduce** for immutable values or appropriate reduction operations; use **collect** when you want to create/mutate an accumulation container.
- Distinguish mutable state **internal to a container created separately by a collector** from **shared mutable state outside the pipeline**.
- Test sequential and parallel execution, and understand the limitations when aggregating monetary data, addition overflow, string concatenation, and side effects.

## 2. Reduce Is a Reduction, Not an Arbitrary Mutating Loop

A simple example:

~~~java
int total = java.util.stream.IntStream.of(2, 4, 6)
        .reduce(0, Integer::sum);

System.out.println(total); // 12
~~~

**0** is the identity of addition; **Integer::sum** is the combining operation for two integers. Key properties:

- **Identity:** 0 + x = x and x + 0 = x.
- **Associativity:** (a + b) + c = a + (b + c), considered within the appropriate value domain/semantics.
- **No shared object needs to be mutated:** each numeric result is computed from the arguments and returned as a value.

In Java int, ordinary addition follows modulo 2^32 overflow rules; under those exact rules, int addition is still associative. However, it can produce negative values or incorrect business meaning when numbers exceed the int range. If you need an exact large sum, choose **long**, **BigInteger**, or an appropriate monetary type, rather than assuming understanding identity/associativity is enough to eliminate overflow issues.

### 2.1. Pipeline Structure

~~~text
Stream<T>
    |
    v
map / filter / ...
    |
    v
reduce(identity, accumulator, combiner)
    |
    +-- combine elements into partial results
    |
    +-- combine partial results
    |
    v
result U
~~~

In a sequential stream, reduce may look like a loop updating a variable. However, the API must also support splitting work into multiple parts and **merging results** when parallel. Therefore, the arguments to reduce have a stronger contract than "my code runs correctly in a single pass."

## 3. Three Important reduce() Overloads

### 3.1. reduce(BinaryOperator<T>): No Identity Required

Signature:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Used when a result may not exist, such as finding the maximum on an empty stream:

~~~java
Optional<Integer> maximum = List.of(4, 9, 2).stream()
        .reduce(Integer::max);

System.out.println(maximum.orElse(-1)); // 9

Optional<Integer> none = Stream.<Integer>empty()
        .reduce(Integer::max);
System.out.println(none.isEmpty()); // true
~~~

The snippet requires importing **List**, **Optional**, and **Stream**. With an empty source, the result is **Optional.empty()**, because there is no first element to serve as an initial value. The function passed must be suitable for combining partial results.

### 3.2. reduce(identity, BinaryOperator<T>): Identity of the Same Type

Signature:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Example:

~~~java
long total = LongStream.of(100, 200, 300)
        .reduce(0L, Long::sum);

System.out.println(total); // 600
~~~

**The identity must be the identity element of the reduction operation**, not an "arbitrary initial value" added exactly once by intuition.

Wrong example when trying to compute **10 + sum of numbers**:

~~~java
// Do not use 10 as the identity for addition:
// int wrong = Stream.of(1, 2, 3).parallel()
//         .reduce(10, Integer::sum);
~~~

In a sequential pipeline it may produce 16, but when splitting the source into multiple branches, the identity 10 can be applied to each branch; the result is not guaranteed to be 16. The right way:

~~~java
int result = 10 + IntStream.of(1, 2, 3).parallel().sum();
System.out.println(result); // 16
~~~

If an initial value has business meaning outside the reduction, **add/combine it after the aggregation** or design a valid monoid instead of pretending it is the identity.

### 3.3. reduce(identity, accumulator, combiner): Result Type Differs from Element Type

Simplified signature:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

- **T:** source element type.
- **U:** accumulated result type.
- **identity:** an identity value of type U.
- **accumulator:** takes the current result U and an element T, **returns a U**.
- **combiner:** combines two results of type U into one U.

Example converting a list of Strings into total length **without mutating a shared result object**:

~~~java
int length = List.of("Java", "Go", "C").parallelStream()
        .reduce(
                0,
                (subtotal, text) -> subtotal + text.length(),
                Integer::sum
        );

System.out.println(length); // 7
~~~

This is a snippet placed in a context where List is already imported. **subtotal + text.length()** produces a new int result rather than mutating a shared container. **Integer::sum** validly combines two subtotals.

## 4. Algebraic Contract of reduce

For the result to have consistent meaning when Stream changes how it splits and merges work, the author must satisfy the appropriate conditions.

### 4.1. Proper Identity

For a combining operation **⊕**, an identity e must satisfy:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

Examples:

| Reduction | Identity | Combining operation |
| --- | --- | --- |
| Integer sum | 0 | addition |
| Integer product | 1 | multiplication |
| String concatenation | empty string | concatenation |
| Set union without mutating arguments | empty set in an immutable model | union creating a new set |
| Maximum with a well-defined domain bound | appropriate minimum element, or reduce without identity | max |

If no natural identity can be determined, using **reduce(BinaryOperator)** returning **Optional** can express the intent more accurately than inventing an unsuitable sentinel.

### 4.2. Associativity

A combining operation must satisfy:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

**Ordinary addition** is a classic example; **subtraction** is not associative:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

If you use subtraction in reduce on a parallel stream, changing how work is split/merged can change the result. Do not use reduce as an execution engine for "first element minus second element minus third element" when you need that order while still expecting parallel equivalence.

For **double** floating-point numbers, mathematical addition is associative, but IEEE 754 arithmetic performs **rounding at intermediate steps**; therefore, sums computed with different groupings may differ due to floating-point error. If financial results require exactness, you need appropriate types and rounding rules, such as **BigDecimal**.

### 4.3. Compatibility of accumulator and combiner

For the three-argument overload, Java also requires the accumulator and combiner to be **compatible**. Intuitively: adding an element T to a subtotal U must be equivalent to accumulating that element into a new subtotal created from the identity, and then combining them.

This condition can be written as:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

With **U as int**, **T as String**, accumulator as **subtotal + length**, identity as **0**, and combiner as **Integer::sum**:

~~~text
u + (0 + length(t)) = u + length(t)
~~~

This contract allows parallel branches to partially aggregate and then merge back into the overall result.

### 4.4. Stateless and Non-interfering

Stream behavioral parameters in general must be:

- **Non-interfering:** do not modify the Stream source being traversed.
- **Stateless:** the lambda's result does not depend on any external mutable state that changes across invocations.
- For reduce, you must additionally respect identity, associativity, and compatibility.

**Do not use an external variable like a global sum in place of the return value from the accumulator.** This makes the reduction depend on the number of calls and callback order, and is especially prone to errors in parallel execution.

## 5. Counterexample: reduce(new ArrayList<>(), ...)

A common mistake:

~~~java
List<String> source = List.of("A", "B", "C");

List<String> result = source.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item);  // Wrong: mutates the identity/subtotal.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right); // Wrong: assumes two independent lists.
                    return left;
                }
        );
~~~

**This is an intentional counterexample; do not run it in an application.** It may compile if List and ArrayList are imported, but it **violates the reduction contract** and produces unreliable results when run in parallel.

Why is it wrong?

1. **The identity is a mutable ArrayList object** created once and passed to reduce.
2. The accumulator lambda receives the list reference and **mutates that very object**. Returning the list does not turn it into an independent U value.
3. In parallel execution, branches may share or see the same identity. **ArrayList is not thread-safe**, so add calls can race, causing data loss or corrupting the structure.
4. The combiner assumes **left** and **right** are two separate results. However, they may reference **the same object**. Calling **left.addAll(right)** with the same reference can duplicate data or throw errors.
5. Even when run sequentially and seemingly producing the right result, the identity has been mutated, violating the reduction's expectations. Happening to run correctly in an example does not make the pattern valid for parallel execution.

Note the distinction: the problem is not merely that ArrayList "lacks a lock." **A shared mutable identity is the wrong model** even if you wrap it in a synchronized collection.

### 5.1. Why Doesn't synchronizedList Fully Solve It?

One might think of:

~~~java
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());
~~~

Even if **shared** is used as the identity and every individual add is guarded, the combiner can still encounter **left == right** and merge that list into itself; the reduction no longer corresponds to a valid combining operation. Adding locks only addresses part of the race condition; it **does not create an independent identity and does not fix the algebraic laws**.

An implementation that "happens to work for three elements" still has no guarantee when data grows, on a different machine, with different parallelism levels, or when the optimizer changes.

## 6. Counterexample: StringBuilder in reduce

**StringBuilder** can concatenate strings efficiently when used locally, but it is not suitable as a **shared mutable identity** for reduce as shown below:

~~~java
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                (builder, item) -> builder.append(item),
                (left, right) -> left.append(right)
        );
~~~

This snippet may also compile, but it is **not a valid reduction**:

- **append** mutates the receiver object.
- Multiple branches may see the same identity.
- **StringBuilder is not thread-safe**.
- The combiner may append a builder to itself, causing duplicated or unexpected data.
- Even when not run in parallel, the result relies on mutation and aliasing rather than following the value-oriented combination style that reduce expects.

**StringBuffer**, which has synchronized methods, does not turn the reduce recipe above into a good design either. Do not fix it by swapping the mutable class; change the **abstraction** to collect or use a non-mutating reduction.

## 7. First Right Way: reduce with Immutable Results

Use **reduce** when each combination produces a new result or uses a value with immutable semantics.

### 7.1. Numeric Sum

~~~java
long total = List.of(10L, 20L, 30L).parallelStream()
        .reduce(0L, Long::sum);

System.out.println(total); // 60
~~~

**Long** is an immutable wrapper; the accumulator returns a new Long with value semantics. There is no shared mutable accumulator object.

If working with large primitive numbers, you can use **mapToLong(...).sum()** to express addition more directly and avoid boxing in Stream<Long> when unnecessary.

### 7.2. Immutable String Concatenation

~~~java
String joined = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", String::concat);

System.out.println(joined); // ABC
~~~

String is immutable. **""** is the identity of concatenation, and string concatenation is associative with respect to content. With an ordered stream, the result in encounter order is ABC.

However, this approach can create many intermediate Strings when the source is large. If the goal is to build a long string efficiently, **Collectors.joining** or **collect(StringBuilder::new,...)** is usually better in terms of copying cost.

### 7.3. BigDecimal for Exact Addition

~~~java
BigDecimal total = Stream.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).parallel().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
~~~

**BigDecimal** is immutable. Here, no rounding MathContext is passed on each addition; values are added exactly. If rounding is applied at each step, associativity with respect to the rounded result may no longer hold as desired; the rounding policy must be designed at the appropriate boundary.

## 8. Second Right Way: collect for Mutable Reduction

If the goal is to **create a container and add elements one by one**, use **collect**, not reduce with a mutable identity.

### 8.1. collect(Supplier, BiConsumer, BiConsumer)

Simplified signature:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner)
~~~

Three parts completely different from reduce:

- **supplier:** creates **a new result container** when needed. In parallel reduction, multiple separate containers may be created for different work chunks.
- **accumulator:** updates the work chunk's container with an element T; this is **intentional mutable reduction**.
- **combiner:** merges **the contents of the second container into the first container** when work chunks are combined.
- **Result:** a container R returned to the caller.

Example:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(result); // [A, B, C]
~~~

With an ordered Stream from **Stream.of**, collect preserves encounter order in the result semantics; multiple internal ArrayLists can be created separately and merged, rather than using a single shared identity ArrayList across all branches. ArrayList itself is still **not thread-safe if you share it externally** after collect; collect does not grant safe concurrent access for all subsequent operations.

### 8.2. StringBuilder via collect

~~~java
String result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();

System.out.println(result); // ABC
~~~

Here **supplier** creates a separate StringBuilder for each partial aggregation; accumulator appends characters into that chunk's builder; combiner appends two builders to produce the merged result. This is the exact API designed for **mutable accumulation**.

**Key distinction:** collect allows mutating **the container created by the supplier for the purpose of collecting**, which does not mean you are allowed to mutate **a global container** captured by all lambdas.

### 8.3. Built-in Collectors Are Often More Readable

In applications, a standard collector is usually chosen:

~~~java
List<String> names = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toList());

String csv = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining(","));

System.out.println(names); // [A, B, C]
System.out.println(csv);   // A,B,C
~~~

**Collectors.toList()** makes no guarantees on the implementation type or mutability of the returned List. If you need to guarantee a mutable ArrayList, use a collector that takes a collection factory, such as **Collectors.toCollection(ArrayList::new)**. If you need an unmodifiable list, in Java 17 you can use **Stream.toList()** or an appropriate collector matching the desired semantics.

### 8.4. Collect Does Not Automatically Guarantee Thread Safety for Other Side Effects

Another mistake:

~~~java
List<String> shared = new ArrayList<>();

List<String> result = source.parallelStream()
        .collect(
                ArrayList::new,
                (local, item) -> {
                    shared.add(item); // Wrong: mutates a shared external list.
                    local.add(item);
                },
                ArrayList::addAll
        );
~~~

This is a counterexample. Even though the **local** container created by the supplier is managed as a mutable reduction, writing to **shared** from multiple tasks is still a shared side effect, risking races and falling outside the collector's safe collection contract. Only mutate the container provided to the accumulator, adhering to the Collector's design and any additional constraints if using a concurrent collector.

## 9. Complete Java 17 Program: Total Revenue and ID List

This program intentionally **does not run the wrong mutable reduce examples**. Instead, it verifies the right patterns: reduce for long and BigDecimal, reduce returning Optional, collect into ArrayList/StringBuilder, and Collectors.joining.

Create the file **SafeReductionDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SafeReductionDemo {
    record Sale(String id, int quantity, long unitPriceVnd) {
        long amount() {
            return Math.multiplyExact((long) quantity, unitPriceVnd);
        }
    }

    static long revenue(List<Sale> sales, boolean parallel) {
        Stream<Sale> pipeline = parallel
                ? sales.parallelStream()
                : sales.stream();

        return pipeline
                .mapToLong(Sale::amount)
                .reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2, 1_500),
                new Sale("B", 1, 700),
                new Sale("C", 3, 400)
        );

        long sequential = revenue(sales, false);
        long parallel = revenue(sales, true);

        System.out.println("sequential revenue: " + sequential);
        System.out.println("parallel revenue: " + parallel);

        List<String> ids = sales.parallelStream()
                .map(Sale::id)
                .collect(ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll);
        System.out.println("collected ids: " + ids);

        StringBuilder builder = sales.parallelStream()
                .map(Sale::id)
                .collect(StringBuilder::new,
                        StringBuilder::append,
                        StringBuilder::append);
        System.out.println("builder: " + builder);

        String joined = sales.parallelStream()
                .map(Sale::id)
                .collect(Collectors.joining(","));
        System.out.println("joined: " + joined);

        Optional<Long> biggest = sales.stream()
                .map(Sale::amount)
                .reduce(Long::max);
        Optional<Long> emptyBiggest = Stream.<Long>empty()
                .reduce(Long::max);

        System.out.println("max amount: " + biggest.orElse(-1L));
        System.out.println("empty max present: "
                + emptyBiggest.isPresent());

        BigDecimal decimal = Stream.of(
                new BigDecimal("0.10"),
                new BigDecimal("0.20")
        ).parallel().reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("decimal sum: " + decimal);

        System.out.println("source quantities: "
                + sales.stream().map(Sale::quantity).toList());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SafeReductionDemo.java
java SafeReductionDemo
~~~

**Program output:**

~~~text
sequential revenue: 4900
parallel revenue: 4900
collected ids: [A, B, C]
builder: ABC
joined: A,B,C
max amount: 3000
empty max present: false
decimal sum: 0.30
source quantities: [2, 1, 3]
~~~

### 9.1. Why Do Both Revenue Calculations Return 4900?

- A: 2 × 1,500 = 3,000.
- B: 1 × 700 = 700.
- C: 3 × 400 = 1,200.
- Total: 3,000 + 700 + 1,200 = **4,900**.

**mapToLong(Sale::amount)** produces a long value for each Sale; **reduce(0L, Long::sum)** reduces by addition with a valid identity. Because no shared mutable subtotal is used, the same stable data source yields the same numeric result in both sequential and parallel execution.

**Math.multiplyExact** detects multiplication overflow for each item. The example uses **Long::sum** for summing the total; with production data that could exceed the long range, you should check for sum overflow or choose BigInteger/BigDecimal as required. Do not assume that because each multiplication is safe, the sum of many elements will definitely fit in a long.

### 9.2. Why Are collected ids and builder Still Correct in Parallel?

**collect** is designed for mutable reduction:

- Creates internal containers via **ArrayList::new** or **StringBuilder::new**.
- Each work chunk puts elements into its own container.
- Merges containers via the appropriate combiner.

With a source **List** having an encounter order, the output displays **[A,B,C]** and **ABC** in source order. Do not rely on the **invocation** order of accumulator/combiner across threads, but rather on the **semantics of an ordered result**.

**Collectors.joining(",")** conveniently creates a comma-separated String, avoiding manual separator logic.

### 9.3. Optional from reduce Without Identity

**reduce(Long::max)** has no identity, so it returns **Optional<Long>**. For non-empty data, max=3000. For Stream.empty, the Optional is empty and isPresent=false. This is better than picking an arbitrary sentinel if the entire long domain can be valid data.

### 9.4. BigDecimal Does Not Mutate

**BigDecimal.ZERO** and **BigDecimal::add** do not mutate old BigDecimals; addition creates a new result. The sequence 0.10 and 0.20 yields **0.30**. If rounding rules are used at each step or with double floating-point data, precision and associativity must be analyzed further.

## 10. So Can collect Mutate?

**Yes, but within the right scope.** The purpose of collect is mutable reduction. Distinguish two forms:

**Right:**

~~~java
List<String> out = values.parallelStream()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
~~~

Here the accumulator receives the container created by the supplier for the collection process; the code does not pass a single shared ArrayList to all branches.

**Wrong:**

~~~java
List<String> shared = new ArrayList<>();
List<String> out = values.parallelStream()
        .collect(
                () -> shared,    // Wrong: every supplier call returns the same object.
                List::add,
                List::addAll
        );
~~~

This is a counterexample. The supplier of collect **must provide an appropriate new container**, not return a single shared object. If all branches receive the same reference, races/aliasing reappear and the combiner may merge an object with itself.

**Rule of thumb:** if a lambda must reference an external **shared** variable to add/sum while reducing data, ask yourself whether you are bypassing the contract of collect/reduce.

## 11. Three Levels of Safety That Must Be Separated

A correct reduction design has at least three independent questions:

1. **Type safety:** does the compiler accept the return type, accumulator, and combiner?
2. **Algebraic and partitioning correctness:** do identity/associativity/compatibility allow splitting and merging work into the same result?
3. **Concurrency safety and ownership:** is a mutable object being modified by multiple branches, or does the combiner receive aliases that the code cannot handle?

Compiling successfully only answers the first question. **Collections.synchronizedList**, **AtomicInteger**, synchronized blocks, or locks can handle some races, but they do not automatically create a proper identity or proper compatibility. Do not assume "it's locked, so reduce will be correct."

### 11.1. Is AtomicInteger in reduce a Solution?

If using **AtomicInteger** as a mutable identity:

~~~java
// Do not use as a mutable identity in reduce:
// AtomicInteger shared = new AtomicInteger();
// stream.parallel().reduce(
//     shared,
//     (counter, n) -> { counter.addAndGet(n); return counter; },
//     (a, b) -> { a.addAndGet(b.get()); return a; }
// );
~~~

Even though increments are atomic, the combiner can receive the same object a==b and add its own value to itself; the reduction semantics are no longer correct. Use **mapToInt(...).sum()** or **reduce(0, Integer::sum)** for sums, or **collect** when you truly need a mutable result structure.

### 11.2. Stateful Callbacks Are Also a Risk

A reducer can create new values and still be wrong if it calls random/time or reads a mutable global variable:

~~~java
// Counterexample of depending on external state:
// int extra = externalCounter.incrementAndGet();
// return subtotal + item + extra;
~~~

The result depends on the number of reducer invocations and scheduling, not just the input data. Predicates/mappers before reduce should also be non-interfering and stateless to keep the entire pipeline stable.

## 12. A Tricky Example: String Concatenation with reduce

The following snippet is **correct in value**:

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", (left, right) -> left + right);

System.out.println(text); // ABC
~~~

Because String is immutable and concatenation has the empty string as its identity element, there is no shared mutable identity.

However, it can be inefficient when concatenating very many elements, because new Strings must be allocated and contents copied at many steps. **Collectors.joining** or **collect(StringBuilder::new, StringBuilder::append, StringBuilder::append)** usually expresses the intent better and reduces intermediate String creation.

An API does not become "more correct" just by using functional style. Choose **the tool that matches the result structure**.

## 13. Do Not Use reduce to Mutate the Source or Write Transactions

Besides mutating the identity, there is another mistake: letting the accumulator mutate **the source elements themselves**:

~~~java
// Counterexample:
// stream.reduce(identity, (acc, item) -> {
//     item.markProcessed(); // Side effect on the source.
//     ...
// }, combiner);
~~~

Stream behavioral parameters must be non-interfering; if the source contains mutable objects, Stream does not automatically deep-copy them. Calling **markProcessed** can alter the source data, causing races or making other pipelines see different state.

Similarly, do not put **sending emails**, **recording payments**, or **writing mandatory audit logs** inside the accumulator, because splitting/merging strategies and optimizations are not designed to guarantee one business transaction per element.

If you need to process every record and update systems, design an **orchestration workflow with clear error contracts, idempotency, transactions, and auditing**; reduction functions should only compute results, not replace data-writing workflows.

## 14. Parallel Streams and Collectors Do Not Guarantee Everything Automatically

That collect works on parallel streams **does not mean** every collector or arbitrary callback is safe:

- Accumulator/combiner must obey Collector rules.
- Supplier must create an appropriate new container, not return the same shared object.
- Concurrent collectors (CONCURRENT) have specific characteristics, and some unordered collectors may not preserve the ordering expected by business logic.
- If a lambda writes to a mutable structure **outside** the collector, you can still encounter races.
- If the result is an ArrayList, after collect returns, **multiple threads arbitrarily mutating that same ArrayList** is still unsafe.
- If order is a business requirement, you must understand the source's encounter order, collector characteristics, and execution behavior.

Only enable **parallelStream()** when the reduction is valid for parallel execution and there is a measured performance benefit. For small datasets, splitting/merging overhead can outweigh the benefits.

### 14.1. Collectors.toConcurrentMap

Some collectors are designed for concurrency, such as **Collectors.toConcurrentMap** and **groupingByConcurrent**. However, they still require appropriate mappers, key classifiers, and merge functions, and may return results with different ordering characteristics than regular collectors. Do not treat the word "Concurrent" as a guarantee that all business logic or objects stored in the map are thread-safe.

## 15. Overflow, Floating-Point Numbers, and Precision

### 15.1. int/long

With Java int/long, ordinary addition can overflow according to integer semantics. If business logic cannot accept this:

- Use a larger type when sufficient: long instead of int.
- Use **BigInteger/BigDecimal** when the numeric domain exceeds long's capacity or for monetary requirements.
- Apply validation and bounds checking before/after reduction.
- Be careful with **Math.addExact**: if run on different groups of elements, one grouping may have an **intermediate sum exceeding the long range** even though the final sum would fit. Thus, exception-throwing behavior across partitions may differ. If you need exact calculations independent of partitioning, use a numeric type with a sufficiently wide range.

### 15.2. double

With binary floating-point numbers, sums computed across different groupings can yield rounding differences:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Therefore, when doing parallel reduction with double, do not demand bit-for-bit exact matches with a fixed-order sequential sum. Test within an acceptable tolerance, or choose an appropriate numeric model if business logic requires absolute precision.

## 16. Unit Testing and Property Checks

### 16.1. Testing Sequential and Parallel Results

For a valid reducer:

1. Reducing an empty source: identity must be returned if using an overload with identity.
2. Single element: result must match the element itself.
3. Multiple elements: result matches expectations.
4. Compare sequential/parallel on a stable source.
5. Shuffle element order if the operation is expected to be commutative; if non-commutative like string concatenation, verify encounter order and the right collector.
6. Large source: check accuracy, overflow, and memory.
7. No mutable state is unexpectedly modified.

Example with addition:

~~~java
int sequential = IntStream.rangeClosed(1, 1000)
        .reduce(0, Integer::sum);

int parallel = IntStream.rangeClosed(1, 1000)
        .parallel()
        .reduce(0, Integer::sum);

if (sequential != 500_500 || parallel != 500_500) {
    throw new AssertionError("Unexpected sum");
}
~~~

This snippet requires importing IntStream and placing it inside a method. The range 1..1000 has a sum of 500,500 within the int range, so matching results are expected.

### 16.2. Testing Identity/Associativity Laws

If you define a custom **BinaryOperator<T> combine**, verify:

~~~text
combine(identity, x) == x
combine(x, identity) == x

combine(combine(a, b), c)
    == combine(a, combine(b, c))
~~~

For object types, compare **business values/properties** rather than just references. For floating-point numbers or operations with overflow/rounding, clearly define the appropriate notion of equivalence; do not write property tests with flawed premises.

### 16.3. Testing for Aliasing Risks by Reading Code

You do not need a stress test for races that might pass by luck to know it is wrong. Simply seeing:

~~~java
U identity = new MutableU();
return stream.parallel().reduce(
        identity,
        (u, t) -> { u.mutate(t); return u; },
        (left, right) -> { left.merge(right); return left; }
);
~~~

is enough to see that **the identity object can be mutated** and the combiner makes wrong ownership assumptions. The counterexample must be refactored to **collect** or use an appropriate immutable U. Running it many times and seeing "mostly right" is not proof of safety.

### 16.4. Testing Collectors

For collect(ArrayList::new, ArrayList::add, ArrayList::addAll):

- Verify the right elements, all elements, and no duplicates beyond the source data.
- For ordered sources, verify the corresponding order.
- Verify the source remains unchanged.
- For mutable objects, explicitly check whether elements share references with the source (collect does not deep-copy).
- If the collector must not encounter null, define the policy for each component.

## 17. Common Mistakes and Fixes

| Mistake | Consequence | Right way |
| --- | --- | --- |
| **reduce(new ArrayList<>(), (list,x)->{list.add(x);return list;},...)** | Mutable identity, aliasing, race/wrong merge | **collect(ArrayList::new, ArrayList::add, ArrayList::addAll)** |
| **reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)** | Mutation of identity and combiner, prone to data duplication | **collect(StringBuilder::new, StringBuilder::append, StringBuilder::append)** |
| Using synchronizedList as reduce identity | Still violates identity law and aliasing risk | Switch to collect, do not just add locks |
| Using AtomicInteger as identity and mutating it | Atomicity does not fix the reduction contract | Immutable integer reduce or IntStream.sum |
| Using identity=10 for addition | Can be applied on multiple branches | identity=0; add 10 after reduction |
| Using subtraction with parallel reduce | Subtraction is not associative | Design sequential algorithm or proper combining operation |
| collect supplier returns the same shared list | Multiple branches use the same object | Supplier creates a new object |
| Using a mutable global counter in accumulator | Result depends on call count/threads | Compute from parameters, return result |
| Using side effects to write audit logs in reduce | No proper transaction per element | Separate business processing step |
| Using Collectors.toList while assuming a guaranteed mutable ArrayList | No implementation/mutability guarantee | toCollection(ArrayList::new) |
| Using Double::sum while demanding exact arithmetic associativity | Floating-point rounding differences | Use acceptable tolerance or exact numeric type |
| Using Math.addExact without considering per-partition results | Exception behavior may differ due to intermediate overflow | Choose a type with sufficient range, define rules |
| Enabling parallel assuming it is faster | Overhead and harder state control | Benchmark after ensuring correctness |

## 18. Practice Exercises

### Exercise 1 — Spot the Mutable Identity Bug

Consider:

~~~java
List<String> result = Stream.of("A", "B")
        .parallel()
        .reduce(
                new ArrayList<>(),
                (list, item) -> { list.add(item); return list; },
                (left, right) -> { left.addAll(right); return left; }
        );
~~~

**Question:** Why can't you rely on the result? **Answer:** the mutable ArrayList identity can be shared across multiple branches; the accumulator mutates the identity; the combiner can receive aliases and merge incorrectly. Use collect with a supplier that creates a new ArrayList. The snippet requires importing List, Stream, and ArrayList.

### Exercise 2 — Choose reduce or collect

Choose the appropriate API:

1. Compute the sum of quantities from an IntStream.
2. Create an ArrayList containing the IDs of each order.
3. Join a large number of strings with commas.
4. Find the max when the stream might be empty.
5. Add BigDecimal values exactly.

**Suggested answer:** (1) IntStream.sum or reduce(0,Integer::sum); (2) collect(toCollection(ArrayList::new)) or three-argument collect; (3) Collectors.joining(","); (4) reduce(max) or corresponding max returning Optional; (5) reduce(BigDecimal.ZERO, BigDecimal::add) if the addition rules match.

### Exercise 3 — Fix an Incorrect Identity

~~~java
int result = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
~~~

**Requirement:** compute 10 + sum of elements while remaining correct in parallel.

**Answer:**

~~~java
int result = 10 + IntStream.of(1, 2, 3)
        .parallel()
        .reduce(0, Integer::sum);
~~~

Result **16**. The identity must be 0 for addition; 10 is extra data outside the reduction.

### Exercise 4 — Fix StringBuilder

The old code used reduce(new StringBuilder(), ...). Replace it with:

~~~java
String text = words.parallelStream()
        .collect(
                StringBuilder::new,
                StringBuilder::append,
                StringBuilder::append
        )
        .toString();
~~~

**words** is assumed to be a List<String> with an encounter order. Explain why collect's supplier works properly with partial containers and why using a mutable StringBuilder identity in reduce is wrong.

### Exercise 5 — Why Isn't AtomicInteger Enough?

A colleague replaced ArrayList with AtomicInteger so that writes become atomic, but still used an AtomicInteger identity and mutated/merged it in reduce.

**Answer:** AtomicInteger only solves the atomicity of individual operations on the counter; it does not ensure a valid identity, prevent the combiner from receiving the same reference, or prevent values from being added twice. Choose a pure numeric reduction or collect with clear result ownership.

### Exercise 6 — Write an Associativity Test

Design a test for a custom combine operation on triples a,b,c, checking identity and associativity. Add sequential/parallel tests with datasets of various sizes. Running tests many times can uncover bugs, but does not replace proving the contract, especially when shared mutable state exists.

## 19. Key Takeaways

**Do not use a shared mutable accumulator object in reduce().** Reduce requires a **valid identity**, **associative** combining operations, and **stateless, non-interfering, compatible** accumulator/combiner functions so that splitting and merging results does not change semantics.

- **reduce**: suited for producing a **reduced value** such as a sum, max, BigDecimal sum, or an immutable result via a proper combining operation.
- **collect**: meant for **mutable reduction** needing an ArrayList, StringBuilder, Map, or result structure created separately by a supplier and then combined.
- **Do not mutate the identity** of reduce, even sequentially; "passing a test run" is not enough to prove correctness.
- **Adding synchronized/AtomicInteger does not fix identity and aliasing.**
- **Do not use a supplier that returns the same shared container** in collect.
- **Avoid side effects on source/global state** in reduction functions, especially in parallel.
- **Consider overflow, associativity, and floating-point error** so you do not trade correctness for speed.

Self-check question before writing: **"Is this a combination of independent values, or do I need to create and mutate a container?"** If it is a combination of values, consider reduce. If it is mutable accumulation, use collect with a contract-compliant supplier/accumulator/combiner.
