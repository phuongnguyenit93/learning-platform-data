# Practicing Fixing Pipelines That Use External State or Misuse `reduce()` in Java

## 1. What Problem Does This Lab Solve?

Java Streams make it easy to express data transformation and aggregation using `filter`, `map`, `reduce`, and `collect`. However, a pipeline that **runs in sequential mode** is not necessarily **contract-correct**, especially when switching to `parallel()`. Two typical sources of bugs are:

1. **External mutable state**: a lambda reads/writes a shared `ArrayList`, `Map`, counter, single-element array, or configuration object; steps are no longer independent, and parallelization can create race conditions.
2. **Misusing `reduce()`**: choosing a non-associative operator, choosing a non-neutral identity, using a combiner incompatible with the accumulator, or using a shared mutable object as the identity and mutating it.

This lesson belongs to **Testing and Practice**. Instead of only reciting theory, each scenario follows the path **read buggy code → explain root cause → refactor → re-verify**, accompanied by a complete Java 17 program and deterministic checks.

After completing it, you will be able to:

- Distinguish *stateless*, *non-interfering* callbacks from callbacks using mutable state.
- Recognize the difference between **mutating the traversed source** and **mutating an external shared accumulator**.
- Fix pipelines that collect into a List, sum, build histograms, assign indices, and join strings using the appropriate reduction/collector APIs.
- Check associativity, identity, and accumulator/combiner compatibility before using `reduce`.
- Avoid using `AtomicInteger` or `synchronizedList` to mask an unnecessary stateful design.
- Distinguish ordered Stream results from the **side-effect** order of `parallel().forEach`.
- Write repeatable tests without relying on a race condition happening to appear on a given run.
- Handle empty cases, duplicates, negative numbers, overflow, and floating-point addition differences.

Snippets marked **“Intentionally wrong”** are for analysis and are not recommended to run on real data systems.

## 2. Three Conditions to Check Before Switching to Parallel

### 2.1. Non-interference: do not interfere with the source

A Stream behavioral parameter (lambda/method reference) generally must not modify **the source being traversed**, unless the source is specifically designed for concurrent modification with clear semantics. For example, a callback traversing an `ArrayList` while calling `add`/`remove` on that same List violates this rule.

### 2.2. Stateless: do not rely on state that changes between invocations

The lambda `n -> n*n` depends only on `n`; conversely, `n -> counter.getAndIncrement() + ":" + n` depends on a shared counter and worker scheduling. Constants or stable immutable configuration may be captured; **stateless does not mean forbidding reading any external variable**. What must be avoided is callback results depending on mutable state that changes across invocations.

### 2.3. Associativity and identity for reduction

A binary combining operation `⊕` must be associative:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

The identity `e` must be neutral:

~~~text
e ⊕ x = x
x ⊕ e = x
~~~

For example, integer addition has identity `0`; multiplication has identity `1`; string concatenation has identity `""`. **Subtraction is not associative**, and `10` is not an identity for addition just because the problem wants to “add 10”.

With the `reduce(identity, accumulator, combiner)` overload, the combiner must also be compatible with the accumulator. Splitting data into separate branches and combining them must have the same meaning as accumulating directly.

### 2.4. Quick diagnostic table

| Code symptom | Question to ask | Usually appropriate fix |
| --- | --- | --- |
| `stream().forEach(shared::add)` | Is an external accumulator mutated by multiple callbacks? | `toList()` or `collect(toCollection(...))` |
| `parallel().forEach(n -> sum[0] += n)` | Does the update have a race? | `sum()` or a valid `reduce` |
| `map(n -> counter.getAndIncrement())` | Does output depend on worker order? | Index source `IntStream.range` or different model |
| `map(x -> { source.remove(x); ... })` | Is the source itself mutated? | Create a new result, filter instead of removing from source |
| `reduce(10,Integer::sum)` | Is the identity neutral? | `reduce(0,Integer::sum)` then add 10 |
| `reduce(0,(a,b)->a-b)` | Is the operation associative? | Use the right operation or ordered fold outside Stream |
| `reduce(new StringBuilder(), ...append...)` | Is a mutable identity used against contract? | `Collectors.joining()` or proper `collect` |
| `reduce(0,Integer::sum,(a,b)->a-b)` | Is combiner compatible with accumulator? | Combine consistently with addition |
| `parallel().forEach(System.out::println)` | Is side-effect order required? | `forEachOrdered` or collect List then print |

## 3. Fix #1 — Collecting a List Using External State

### 3.1. Intentionally buggy code

~~~java
List<Integer> output = new ArrayList<>();

IntStream.range(0, 1000)
        .parallel()
        .forEach(output::add);
~~~

This snippet sits inside a method with `List`, `ArrayList`, and `IntStream` imported. It compiles, but is **unsafe**: multiple tasks concurrently write to an unsynchronized `ArrayList`. Add operations can contend, drop elements, corrupt state, or throw exceptions. Seeing 1000 elements on a few runs **does not prove** it is safe.

If run sequentially only, the code may appear to work; however, the Stream principle is to express collection via a terminal operation to avoid external accumulators.

### 3.2. Proper fix: collect into a List

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();
~~~

`IntStream.range(0,1000)` produces a source with encounter order from 0 to 999. `boxed()` converts `int` to `Integer`. `Stream.toList()` in Java 17 returns an unmodifiable List preserving encounter order when present, so the output has 1000 elements in the right order.

If a **mutable List is needed** afterward:

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

output.add(1000);
~~~

`toCollection(ArrayList::new)` specifies the mutable implementation explicitly. The Stream framework manages accumulators/combiners per the collector contract, unlike callbacks arbitrarily writing to an external shared List.

**Distinction:** a parallel pipeline collecting properly does not make the returned `ArrayList` thread-safe if multiple threads continue mutating it after `collect`.

### 3.3. Test case

Instead of running the buggy code 100 times “waiting for it to fail”, verify correctness of the fixed version:

~~~java
List<Integer> output = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();

if (output.size() != 1000
        || output.get(0) != 0
        || output.get(999) != 999) {
    throw new AssertionError("wrong result");
}
~~~

This is a code fragment inside a method. The test does not rely on race timing; it specifies the desired **result contract**.

## 4. Fix #2 — Summing with a Shared Variable or Array

### 4.1. Reassigning a local variable inside a lambda

~~~java
int sum = 0;

IntStream.rangeClosed(1, 100)
        .forEach(n -> sum += n);
~~~

This **does not compile**: local `sum` is reassigned inside the lambda, so it is not effectively final. The compiler error is a helpful signal, not an invitation to use a one-element array to bypass capture restrictions.

### 4.2. A one-element array does not solve concurrency

~~~java
int[] holder = {0};

IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(n -> holder[0] += n);
~~~

This compiles, but updating `holder[0]` is **not atomic**: read → add → write can interleave across threads. The result may not be 500500, and the race does not necessarily throw an exception.

### 4.3. Proper fix: contract-compliant reduction

~~~java
int sum = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

System.out.println(sum); // 500500
~~~

Or:

~~~java
int sum = IntStream.rangeClosed(1, 1000)
        .parallel()
        .reduce(0, Integer::sum);
~~~

`0` is the additive identity; `int` addition is associative in Java modulo 2^32. For 1..1000, there is no overflow so it also matches the mathematical sum. If the sum may exceed `int` range, switch to an appropriate type:

~~~java
long sum = IntStream.rangeClosed(1, 100_000)
        .mapToLong(n -> n)
        .sum();

System.out.println(sum); // 5000050000
~~~

`IntStream.sum()` can also overflow without throwing an exception. Switch to `long` when data warrants it, and still watch `long` limits for very large ranges.

### 4.4. Self-check question

Why is `AtomicInteger.addAndGet(n)` not preferred here? It makes updates atomic, but remains a side effect on shared state, creates contention, hinders composition, and no longer directly expresses a reduction. `sum()` states the goal clearly and lets the framework parallelize per contract.

## 5. Fix #3 — Using an External Counter to Assign Indices

### 5.1. Wrong: indices depend on scheduling order

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> numbered = names.parallelStream()
        .map(name -> counter.getAndIncrement() + ":" + name)
        .toList();
~~~

This is a snippet with `names` of type `List<String>`. `AtomicInteger` guarantees atomic increments, but **does not guarantee which name gets which index** when callbacks run in parallel. `toList()` preserves encounter order of mapped elements, yet the assigned counter values can be scrambled relative to element positions.

Switching to `forEachOrdered` addresses **action execution order**, and does not automatically make arbitrary side-state reads/writes a good design.

### 5.2. Fix: the index source is data

~~~java
List<String> names = List.of("An", "Binh", "Chi");

List<String> numbered = IntStream.range(0, names.size())
        .parallel()
        .mapToObj(i -> i + ":" + names.get(i))
        .toList();

System.out.println(numbered);
~~~

Output:

~~~text
[0:An, 1:Binh, 2:Chi]
~~~

Each task receives **a unique index from the source**, with no contention on a global counter. Condition: `names` must remain stable during processing; `get(i)` works best with Lists supporting efficient random access (such as `ArrayList` or `List.of`). For large `LinkedList` instances, repeated `get(i)` can be inefficient; a loop/iterator or different numbering strategy can be chosen.

### 5.3. When only the count is needed

If the goal is counting:

~~~java
long count = names.parallelStream().count();
~~~

No `counter` variable is needed, nor creating numbered strings. Before fixing code, determine whether the business logic wants **the count** or **each element's position**.

## 6. Fix #4 — Interfering with the Source During Traversal

### 6.1. Wrong: modifying the list currently traversed by the Stream

~~~java
List<String> source = new ArrayList<>(
        List.of("An", "Binh", "Chi"));

List<String> result = source.stream()
        .filter(name -> {
            if (name.startsWith("B")) {
                source.remove(name); // Wrong: source interference.
            }
            return true;
        })
        .toList();
~~~

This is **contract-violating code**, not an example to run for stdout. `source` is mutated while the Stream is traversing it. `ConcurrentModificationException` or unspecified behavior may occur; do not assume an exception will always catch the bug.

### 6.2. Fix: filter while building a new result

~~~java
List<String> source = List.of("An", "Binh", "Chi");

List<String> result = source.stream()
        .filter(name -> !name.startsWith("B"))
        .toList();

System.out.println(source); // [An, Binh, Chi]
System.out.println(result); // [An, Chi]
~~~

The goal “exclude elements from the result” does not require deleting elements from the source. Creating a new result avoids side effects and makes testing clear.

If the problem genuinely requires removing from the collection, do it **in a step outside Stream traversal**, for example calling `source.removeIf(predicate)` on a mutable List in a separate phase after pipelines using the source have finished. Do not mutate the source concurrently across tasks.

### 6.3. Source with mutable elements

A `List.of(...)` source cannot have elements added/removed via the List API, yet if an element is a mutable object, callbacks can still mutate that object. That can alter observable state or race with other callbacks. Non-interference and statelessness must still consider **the data callbacks touch**, not just List structure.

## 7. Fix #5 — `reduce()` Using Non-Associative Subtraction

### 7.1. Wrong: treating parallel reduction like a left-to-right loop

~~~java
int result = IntStream.of(10, 3, 2)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

**Do not use this code to express sequential subtraction.** Subtraction is not associative:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

When the Stream framework splits the sequence and combines partial results in different ways, using subtraction as a reduction operator violates associativity and identity requirements. Observing a value on a single run **does not** prove the reduction is valid.

### 7.2. When you actually want the negated sum

If the business logic is “negate the sum”:

~~~java
int result = -IntStream.of(10, 3, 2)
        .parallel()
        .sum();

System.out.println(result); // -15
~~~

This is a different operation from `10-3-2`: confirm business meaning before refactoring. Do not “fix parallel” by **changing the operation** without checking requirements.

### 7.3. When you want left-to-right subtraction

If the requirement is genuinely `(10-3)-2=5`, operation order is part of the semantics; a sequential loop with an explicit accumulator can be clearer:

~~~java
int[] values = {10, 3, 2};
int difference = values[0];

for (int i = 1; i < values.length; i++) {
    difference -= values[i];
}

System.out.println(difference); // 5
~~~

This example suffices to illustrate sequential subtraction. For an empty array, decide the policy before accessing `values[0]`. Do not use non-associative `reduce` just for one-line syntax.

### 7.4. Expressing subtraction as subtracting the sum of remaining terms

If the problem is `a-b-c` and `a` is given separately, you can compute:

~~~java
int first = 10;
int[] rest = {3, 2};
int difference = first - Arrays.stream(rest).sum();

System.out.println(difference); // 5
~~~

This snippet requires importing `java.util.Arrays`. Within non-overflowing integer range and with proper `first`/`rest` splitting, this transformation preserves the mathematical result. With overflow or rounding rules, evaluate exact semantics instead of assuming every algebraic rewrite is equivalent.

## 8. Fix #6 — Wrong Identity in `reduce()`

### 8.1. Wrong: using an initial value as the identity

~~~java
int result = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(10, Integer::sum);
~~~

If you expect `10 + (1+2+3+4) = 20`, this is **contract-incorrect**. `10` is not the additive identity. In parallel reduction, multiple partial reductions can start from `10`, causing it to be added multiple times.

### 8.2. Fix: neutral identity then apply the “fixed fee” once

~~~java
int subtotal = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

int total = 10 + subtotal;
System.out.println(total); // 20
~~~

`0` is neutral for addition. `10` is the **one-time business addition**, placed after the reduction. If a fee applies per element, the formula differs; clarify before fixing.

### 8.3. Recognizing common identities

| Combining op | Common identity | Notes |
| --- | --- | --- |
| `Integer::sum` | `0` | Watch overflow if mathematical sum is needed |
| Integer multiplication | `1` | Do not use `0` as identity |
| `String::concat` | `""` | Element order matters |
| `Math::max` | No natural `int` identity for all domains without choosing min bound | Can use `max()` returning `OptionalInt` |
| `Math::min` | No natural `int` identity for all domains without choosing max bound | Can use `min()` returning `OptionalInt` |

For `Math.max` on `int`, `Integer.MIN_VALUE` can serve as identity for the full int range; for `Math.min`, `Integer.MAX_VALUE` can serve as identity. However, `max()`/`min()` overloads returning Optional express empty data clearly and are usually better than attaching a sentinel as a result.

## 9. Fix #7 — Conflicting Accumulator and Combiner

### 9.1. Wrong: adding in accumulator but subtracting in combiner

~~~java
int result = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left - right);
~~~

This compiles, but **violates the contract**: the accumulator builds partial sums while the combiner subtracts partial sums. The result depends on how branches are split.

For the three-argument overload:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

This is the general signature of `Stream.reduce`. The identity must be neutral for the combiner; accumulator/combiner must be compatible. An important conceptual law is:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

`==` in the diagram denotes **semantic value equality**, not necessarily Java reference equality.

### 9.2. Fix: both express summation

~~~java
int result = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, Integer::sum, Integer::sum);

System.out.println(result); // 10
~~~

With the same input/output type `Integer` and addition, the two-argument `reduce(0,Integer::sum)` is shorter. If only processing integers, `mapToInt(Integer::intValue).sum()` also makes intent clear.

### 9.3. What if the two steps have different types?

Suppose a Stream contains `Order` and the result is `long`. Depending on the problem, you can use:

~~~java
long total = orders.stream()
        .mapToLong(Order::amount)
        .sum();
~~~

This snippet has `orders` of type `List<Order>` and `Order.amount()` returning `long`. Do not rush to use `reduce(identity, accumulator, combiner)` just because element type differs from result type: mapping to a primitive stream expresses summation simply and reduces errors.

## 10. Fix #8 — Using a Mutable Identity in `reduce()`

### 10.1. Wrong: accumulating into a shared `StringBuilder`

~~~java
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                StringBuilder::append,
                StringBuilder::append);
~~~

This is an **anti-pattern**: the `append` accumulator mutates the mutable identity itself. In parallel reduction, the same identity object can participate in multiple branches in ways incompatible with the reduce contract. This mutation also breaks identity/combiner compatibility and can yield duplicated or wrong results.

**Do not fix by adding `synchronized` on StringBuilder while keeping `reduce`.** The problem lies in both reduction semantics and using a mutable identity.

### 10.2. Direct fix: `Collectors.joining()`

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining());

System.out.println(text); // ABC
~~~

If a delimiter is needed:

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.joining("|"));

System.out.println(text); // A|B|C
~~~

`Collectors.joining` is a collector specialized for string concatenation; the framework manages internal accumulation state and combines per contract. For an ordered Stream, the returned content preserves element encounter order.

### 10.3. When `reduce` on immutable values is valid

~~~java
String text = Stream.of("A", "B", "C")
        .parallel()
        .reduce("", String::concat);

System.out.println(text); // ABC
~~~

`String` is immutable; each `concat` produces a new String value, and string concatenation is associative by content. However, the number of intermediate objects can be large, so `Collectors.joining` is usually preferable for substantial string volume.

### 10.4. `collect` with a mutable container is a different API

Not all mutable accumulation is wrong. `collect` is specifically designed with a supplier, accumulator, and combiner and can coordinate mutable containers safely per contract. For example:

~~~java
ArrayList<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

The framework does not ask you to provide **a single shared `ArrayList`** for all workers. This differs from `reduce(new ArrayList<>(), ... mutate list...)`.

## 11. Fix #9 — Grouping and Counting with an External `Map`

### 11.1. Wrong: updating `HashMap` from multiple callbacks

~~~java
Map<String, Integer> counts = new HashMap<>();

events.parallelStream().forEach(event -> {
    String key = event.category();
    counts.merge(key, 1, Integer::sum);
});
~~~

This is a **non-independent** pattern: it requires `Event` with `category()`, source `events`, and imports `Map`, `HashMap`. `HashMap` is generally unsafe for concurrent mutation. Even though `merge` looks like a single operation, it is not a promise of thread safety when multiple threads mutate one HashMap.

### 11.2. Fix: `groupingBy` with downstream `counting`

~~~java
Map<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingBy(
                Event::category,
                Collectors.counting()));
~~~

Each `count` is `Long`; accumulation and combining are coordinated by the framework. If a Map with ordered keys is needed for testing or display:

~~~java
Map<String, Long> counts = events.parallelStream()
        .collect(Collectors.groupingBy(
                Event::category,
                TreeMap::new,
                Collectors.counting()));
~~~

`TreeMap` provides key order per the appropriate comparator/natural ordering. The result is still not automatically safe for multiple threads to mutate concurrently without synchronization after `collect`.

### 11.3. When integers are already keys

~~~java
List<Integer> values = List.of(2, 3, 2, 5, 3);

Map<Integer, Long> histogram = values.parallelStream()
        .collect(Collectors.groupingBy(
                n -> n,
                TreeMap::new,
                Collectors.counting()));

System.out.println(histogram); // {2=2, 3=2, 5=1}
~~~

This illustrative snippet runs in Java 17 with imports `List`, `Map`, `TreeMap`, `Collectors`. No external mutable Map is directly mutated by callbacks.

### 11.4. `groupingByConcurrent` has a different contract

`groupingByConcurrent` is a concurrent/unordered collector that can be useful when encounter order is not needed; however, do not replace `groupingBy` with it unconditionally. If the downstream is a List where group order matters, read the contract carefully. Do not use `ConcurrentHashMap` just to mask races in a pipeline that could be collected safely with a standard collector.

## 12. Fix #10 — `peek` and Unreliable Side Effects

### 12.1. Wrong: using `peek` to mutate business state

~~~java
List<String> names = List.of("A", "B", "C");
AtomicInteger observed = new AtomicInteger();

long count = names.stream()
        .peek(name -> observed.incrementAndGet())
        .count();
~~~

You must not conclude `observed.get()` **must equal 3**. `peek` is an intermediate operation primarily for observation/debugging; Streams may optimize away execution of intermediate stages if the terminal result can still be determined. `count()` on a sized source is an example where intermediate callbacks may not need to be invoked.

If you need to count elements, `count` itself is the measurement. If you need auditing or external service calls, define a dedicated phase with explicit retry/error/transaction and ordering; do not hide it inside `peek`.

### 12.2. Observing for debugging without depending on it

~~~java
List<Integer> result = values.stream()
        .peek(n -> System.out.println("seen " + n))
        .map(n -> n * 2)
        .toList();
~~~

This snippet has `values` of type `List<Integer>` and should only use `peek` for temporary observation. Do not write logic whose correctness depends on every `seen` line always being printed in a fixed order across every pipeline/implementation.

### 12.3. A valid side effect still needs clear design

There are cases where terminal `forEach` is used to write files, send results, or output logs. This is not inherently wrong, but you must clarify:
- Who owns the resource?
- Is encounter order required?
- Can callbacks run concurrently?
- How are exceptions and partial effects handled?
- Are transactions, idempotency, or concurrency limits needed?

A mandatory business step should not rely solely on `peek` being called “as expected”.

## 13. Complete Java 17 Program: Fixed Versions

The following program tests the learned rules **without running race-inducing anti-patterns**. The input includes duplicate elements to test the histogram; pipelines run in parallel where appropriate; expectations are checked with a helper that throws `AssertionError` on mismatch. It does not depend on callback order or timing.

Create the file **`PipelineRepairLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PipelineRepairLab {

    record Summary(long count, long sum) {}

    static void verify(String name, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + ": expected "
                    + expected + ", actual " + actual);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 3, 2, 5, 3);

        // Fix shared accumulator: use proper reduce.
        int sum = source.parallelStream()
                .reduce(0, Integer::sum);

        // Fix map with side effects: create a new List.
        List<Integer> squares = source.parallelStream()
                .map(n -> n * n)
                .toList();

        // Fix shared HashMap: groupingBy + counting.
        Map<Integer, Long> histogram = source.parallelStream()
                .collect(Collectors.groupingBy(
                        n -> n,
                        TreeMap::new,
                        Collectors.counting()));

        // Fix AtomicInteger used as an index.
        List<String> indexed = IntStream.range(0, source.size())
                .mapToObj(i -> i + ":" + source.get(i))
                .toList();

        // Fix mutable StringBuilder identity: joining.
        String joined = source.parallelStream()
                .map(String::valueOf)
                .collect(Collectors.joining("|"));

        // Need a mutable result List? Choose an explicit supplier.
        List<Integer> mutableCopy = source.parallelStream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutableCopy.add(99);

        // Multiple metrics in one collect, without mutating external state.
        Summary stats = source.parallelStream()
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Integer::longValue),
                        Summary::new));

        verify("sum", 15, sum);
        verify("squares",
                List.of(4, 9, 4, 25, 9), squares);
        verify("histogram",
                Map.of(2, 2L, 3, 2L, 5, 1L), histogram);
        verify("indexed",
                List.of("0:2", "1:3", "2:2", "3:5", "4:3"), indexed);
        verify("joined", "2|3|2|5|3", joined);
        verify("source unchanged",
                List.of(2, 3, 2, 5, 3), source);
        verify("stats", new Summary(5L, 15L), stats);

        System.out.println("sum=" + sum);
        System.out.println("squares=" + squares);
        System.out.println("histogram=" + histogram);
        System.out.println("indexed=" + indexed);
        System.out.println("joined=" + joined);
        System.out.println("mutableCopy=" + mutableCopy);
        System.out.println("source=" + source);
        System.out.println("stats=" + stats);
        System.out.println("checks=PASS");
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 PipelineRepairLab.java
java PipelineRepairLab
~~~

**Exact stdout:**

~~~text
sum=15
squares=[4, 9, 4, 25, 9]
histogram={2=2, 3=2, 5=1}
indexed=[0:2, 1:3, 2:2, 3:5, 4:3]
joined=2|3|2|5|3
mutableCopy=[2, 3, 2, 5, 3, 99]
source=[2, 3, 2, 5, 3]
stats=Summary[count=5, sum=15]
checks=PASS
~~~

### 13.1. Why is the program's output deterministic despite using parallel?

The source `List.of(2,3,2,5,3)` has encounter order and is not mutated; addition/counting are valid reductions; `toList` preserves encounter order; `joining` joins in source order; `TreeMap` gives key order when printing the histogram. There is no `System.out.println` inside parallel callbacks.

### 13.2. Why does `mutableCopy` contain 99 while `source` does not?

Collector `toCollection(ArrayList::new)` creates a mutable result separate from the source List. After `collect`, adding 99 only mutates `mutableCopy`. `source` retains its five initial values, and `verify("source unchanged", ...)` verifies this.

### 13.3. Why does `stats` have two fields?

`Collectors.teeing` (available in Java 12+) uses two downstream collectors: `counting()` and `summingLong(...)`, then merger `Summary::new` combines both results into one record. It expresses the count/sum requirement **as a result value**, not via a shared external mutable counter.

### 13.4. Why is the histogram accurate?

The source contains `2` twice, `3` twice, and `5` once. `groupingBy(...,TreeMap::new,counting())` collects exact occurrences; key order when printed is `2,3,5`. No `HashMap.merge` in a parallel `forEach` callback is needed.

### 13.5. Why is `verify` better than logging threads?

It checks the values and order promised by the API without assuming which thread runs first. When testing correctness of a parallel pipeline, compare results against expected sets and verify invariants on source/result types, rather than relying on log output or a single race-free run.

## 14. Writing Better Tests: Edge Cases

### 14.1. Empty source

~~~java
List<Integer> empty = List.of();

int sum = empty.stream().reduce(0, Integer::sum);
long count = empty.stream().count();
List<Integer> result = empty.stream().toList();

System.out.println(sum);    // 0
System.out.println(count);  // 0
System.out.println(result); // []
~~~

The identity must be valid when there are no elements. `max()`/`min()` usually return `Optional` because an empty set has no extremum; do not pick a sentinel that causes “no data” to be mistaken for real data.

### 14.2. Data with duplicates

The source `[2,3,2,5,3]` has duplicates to test the histogram. If the problem requires keeping duplicates, do not add `distinct()` arbitrarily: it changes semantics, reduces counts, and can alter sums.

### 14.3. Negative numbers and 0

~~~java
List<Integer> values = List.of(-2, 0, 3);
int sum = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sum); // 1
~~~

This test helps catch code that accidentally works only for positive data, or uses an improper identity.

### 14.4. Overflow

~~~java
int wrapped = IntStream.of(Integer.MAX_VALUE, 1).sum();
System.out.println(wrapped); // -2147483648
~~~

This is Java `int` arithmetic overflowing; modular addition is still bit-pattern associative, but the result is **not the intended mathematical sum**. If the domain forbids overflow, use a wider type:

~~~java
long exactForTheseInputs =
        IntStream.of(Integer.MAX_VALUE, 1)
                .mapToLong(n -> n)
                .sum();

System.out.println(exactForTheseInputs); // 2147483648
~~~

For data wider than `long`, control input bounds or use `BigInteger` when appropriate. `Math.addExact` helps detect overflow within a range, but when used with parallel reduction and multiple branches, exception detection order can vary; correctness must follow the domain data policy.

### 14.5. Floating-point numbers and rounding error

`double` uses floating-point addition, so bitwise it may not be associative:

~~~text
a = 1.0e16
b = -1.0e16
c = 1.0

(a + b) + c = 1.0
a + (b + c) = 0.0
~~~

Changing how groups are split can affect rounding error. Do not claim that every parallel `DoubleStream.sum()` or custom reduce will always match sequential results bitwise across all workloads. If the business logic needs monetary totals or high precision/repeatability, choose numeric types and accumulation methods meeting the requirement, such as `BigDecimal` with explicit scale/rounding or error-compensated floating-point summation.

### 14.6. Do not rely on random failure of buggy code

A race condition may not appear in a single test run; race detectors or repeated tests can assist investigation, but proper fixes must be based on contracts and callback structure. Conversely, anti-patterns like `reduce(10,Integer::sum)` might happen to give the right answer in some sequential runs yet still violate identity for general reduction.

### 14.7. Comparing sequential and parallel requires conditions

You can write a test:

~~~java
int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

if (sequential != parallel) {
    throw new AssertionError("inconsistent sum");
}
~~~

This is a code fragment with `values` of type `List<Integer>`. With pure `int` addition, a valid identity, stable source, and no side effects, values must match Java addition semantics. However, **merely comparing two equal outputs does not prove all reduction laws**: a buggy operation can coincidentally produce the same result on one input. You must also check associativity, identity, and compatibility.

## 15. Review Practice: Read Code Then Decide to Fix or Keep Sequential

### Scenario A — Joining names into CSV

Buggy code:

~~~java
StringBuilder csv = new StringBuilder();

names.parallelStream()
        .forEach(name -> csv.append(name).append(","));
~~~

Because `StringBuilder` is not thread-safe, callbacks mutate the same object concurrently; joining order is also not guaranteed by `forEach`. If you want a proper delimiter between names:

~~~java
String csv = names.stream()
        .collect(Collectors.joining(","));
~~~

When names may contain commas, quotes, or newlines, real CSV generation requires proper escaping/quoting; `joining(",")` only illustrates delimiter-based string joining.

### Scenario B — Calling a service for each element

~~~java
requests.parallelStream()
        .forEach(api::send);
~~~

You cannot conclude “safe” or “wrong” from syntax alone. You must know whether `api.send` is thread-safe, concurrent request count, rate limits, timeouts, required ordering, retries, and idempotency. For mandatory business side effects, a controlled concurrency mechanism is usually needed rather than defaulting to parallel Stream and hoping.

### Scenario C — Depending on print order

~~~java
values.parallelStream().forEach(System.out::println);
~~~

Output may appear out of order. If encounter order is required:

~~~java
values.parallelStream().forEachOrdered(System.out::println);
~~~

`forEachOrdered` guarantees action order for an ordered Stream, though it can limit performance and **does not fix all races** in callback code. To test data, collecting with `toList()` and comparing Lists is usually simpler.

### Scenario D — Updating a database inside `map`

~~~java
List<Result> results = records.parallelStream()
        .map(record -> repository.save(record))
        .toList();
~~~

This is a **design pattern requiring review**, not guaranteed safe. `repository.save` has I/O side effects and may involve transactions, connection pools, and mid-flight failures. If the pipeline is meant to be a pure transformation, this `map` is not pure. Separate result computation from persistence when appropriate; if processing I/O concurrently, manage explicit concurrency, retries, and transactions.

## 16. Hands-On Exercises

### Exercise 1 — Refactor shared List

Input `IntStream.range(0,1000)`. Code uses `parallel().forEach(shared::add)`. Fix to `boxed().toList()`, verify count/order; then add a version needing a mutable `ArrayList` using `toCollection(ArrayList::new)`.

### Exercise 2 — Shared sum array

Use `int[] holder={0}` and update inside `parallel().forEach` to sum 1..1000. Analyze the race, then write `sum()` and `reduce(0,Integer::sum)`. Write a test expecting 500500 and try switching to `mapToLong` when the sum range can exceed `int`.

### Exercise 3 — Numbering with AtomicInteger

Create List `["An","Binh","Chi"]`. Write a version using `AtomicInteger.getAndIncrement` in `parallel().map`, explain why labels/indices have no position guarantee; fix using `IntStream.range(0,size).mapToObj(i -> i+":"+list.get(i))`.

### Exercise 4 — Non-interference with source

Given ArrayList `["A","B","C"]`; a pipeline removes element B inside `filter`. Rewrite as `filter(name -> !name.equals("B"))` and collect a new List. Write a test confirming the source remains `["A","B","C"]`.

### Exercise 5 — Subtraction and associativity

Compute `(10-3)-2` and `10-(3-2)`. Explain why the two results differ. Choose a sequential loop for “left-to-right subtraction”, or `first - sum(rest)` when algebraically and numerically valid; do not put subtraction into parallel reduce arbitrarily.

### Exercise 6 — Identity vs. fixed fee

Code uses `reduce(10,Integer::sum)` to “add fee 10” to the sum 1..4. Fix using `reduce(0,Integer::sum)` then adding 10 once; explain why parallel splitting makes identity 10 wrong.

### Exercise 7 — Compatible combiner

Given `reduce(0,Integer::sum,(a,b)->a-b)`. Point out the issue and fix the combiner to `Integer::sum`. State the compatibility law when accumulator and combiner have different types.

### Exercise 8 — Mutable StringBuilder

Given `Stream.of("A","B","C").parallel().reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)`. Explain why a mutable identity violates the contract; fix using `collect(Collectors.joining())` and `joining("|")`. Compare with `reduce("",String::concat)`.

### Exercise 9 — Counting by key

Given `List.of(2,3,2,5,3)`; write histogram `{2=2,3=2,5=1}` using `groupingBy(n->n,TreeMap::new,counting())`. Do not use a shared HashMap in `parallel().forEach`. Try an empty source and explain the resulting Map.

### Exercise 10 — `peek` and optimization

Use `List.of(1,2,3).stream().peek(...).count()`. Explain why you should not test a counting policy by how many times `peek` is called. Fix using `count` or `collect` appropriately.

### Exercise 11 — Creating Summary without shared state

Use `Collectors.teeing(Collectors.counting(),Collectors.summingLong(Integer::longValue),Summary::new)` with `record Summary(long count,long sum)`. Test `Summary(5,15)` for `[2,3,2,5,3]`. Compare with two global variables `count`/`sum`.

### Exercise 12 — Writing invariant-based tests

For a parallel pipeline in a project, list assertable expectations: unchanged source, element count, element set, order if encounter-ordered, required sums/groups, no leaked mutable references. Add empty, duplicate, negative, and overflow cases. Do not treat “ran 100 times without error” as absolute proof.

## 17. Acceptance Checklist for a Fixed Pipeline

1. Is the business requirement **preserving order, counting, summing, grouping, or external updating**? Was the right operation chosen?
2. Do behavioral parameters mutate the source being traversed?
3. Do lambdas read/write external mutable state over time?
4. If `AtomicInteger`/synchronized collections are present, are they masking unnecessary stateful accumulation?
5. With `reduce`, is the combining operation **associative**?
6. Is the identity properly neutral for both sequential and parallel reduction?
7. For the three-argument overload, are accumulator/combiner semantically compatible?
8. Is a mutable identity used in `reduce`? Should it be switched to `collect`?
9. Is `parallel().forEach` used to accumulate into a shared List/Map?
10. Does the collected collection type match mutable/unmodifiable requirements?
11. Is `Collectors.toList()` being assumed to always be a mutable `ArrayList`?
12. Does the source have encounter order? If order is needed, does the terminal operation preserve it?
13. Does anything rely on how many times `peek`/`map` runs for business side effects?
14. Did refactoring subtraction to addition or changing identity alter semantics?
15. Could large data cause overflow, excessive memory use, or parallel overhead?
16. Do unit tests cover empty, duplicate, negative, boundary cases, and sequential/parallel comparison when valid?
17. Does the fixed code compile on Java 17 and produce stdout matching the contract?
18. If the pipeline performs I/O, transactions, API calls, logging, or email, are appropriate retry, failure, concurrency-limit, and idempotency policies in place?

## 18. Summary and Reference Documentation

**Fixing pipelines that use external state** usually means moving from `forEach(shared::add)`, shared sum arrays, or contended counters to **pure `map`/`filter` and contract-compliant `collect`/`reduce`**. For element order, prefer deriving indices from data or collecting into a List rather than relying on scheduling order. Do not mutate the source being traversed by the Stream.

**Fixing broken `reduce()`** requires understanding the exact algebra of the combining operation: associativity, identity, and accumulator/combiner compatibility. Do not use non-associative subtraction, do not treat an “initial fee” as an identity, and do not mutate a `StringBuilder`/`List` used as a `reduce` identity. Use `sum`, `count`, `max`, `joining`, `groupingBy`, `toCollection`, or `teeing` when they directly model the problem.

Finally, **test by contract**, not by race luck. Verify results, source immutability, guaranteed ordering, empty data, duplicate elements, and numeric boundaries. Parallel Stream is an execution strategy; correctness must come before optimization.

Official documentation: Java SE 17 Javadoc for `java.util.stream.Stream` (especially `reduce`, `collect`, `forEach`, `forEachOrdered`, `peek`), `IntStream`, `java.util.stream.Collectors` (`joining`, `groupingBy`, `counting`, `toCollection`, `teeing`), and the Java Stream package documentation on *Non-interference*, *Stateless behaviors*, *Reduction*, *Side-effects*, and *Ordering*.
