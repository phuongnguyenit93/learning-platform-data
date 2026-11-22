# Accumulator: adding elements to the accumulation container in a custom Collector

## 1. Why understand the accumulator?

A Java Stream pipeline usually ends with the §collect(...)§ method. When collection requirements go beyond §toList()§, §joining()§, or §groupingBy()§, we can create a custom **Collector**. The collector must know how to create a state storage container, add each element to that container, combine containers during segmented execution, and transform the state into the result.

Among those four components, the **accumulator** is the function responsible for the direct work: **receiving the current accumulation container and a Stream element, and updating the accumulation container to record that element**.

For example, with a list of names:

§§§text
Stream<String>           "Lan"   "An"   "Minh"
                            \      |     /
                             \     |    /
Accumulator: add to    ArrayList<String>
                                  |
                                  v
Result:                   [Lan, An, Minh]
§§§

When creating a custom collector, you should not assume §accumulator§ returns a new list for each element. By the §Collector§ contract, it is a **BiConsumer** and returns §void§. It usually **mutates the temporary accumulation container** §A§ provided by §supplier§. This temporary container is distinct from the Stream source and distinct from the result object §R§ after §finisher§ transforms it.

## 2. The four roles of Collector<T, A, R>

The interface §java.util.stream.Collector<T,A,R>§ represents how to collect elements §T§ into a result §R§, via an accumulation container §A§.

| Component | Conceptual type | Role |
| --- | --- | --- |
| §supplier§ | §Supplier<A>§ | Creates a new, independent accumulation container |
| **§accumulator§** | **§BiConsumer<A,T>§** | **Adds an element §T§ into container §A§** |
| §combiner§ | §BinaryOperator<A>§ | Merges two accumulation containers of the same type §A§ |
| §finisher§ | §Function<A,R>§ | Converts the accumulation container into result §R§ |
| §characteristics§ | §Set<Collector.Characteristics>§ | Declares characteristics when appropriate, such as §IDENTITY_FINISH§, §UNORDERED§, §CONCURRENT§ |

Example of concrete types:

§§§text
Collector<String, ArrayList<String>, List<String>>
          T           A                  R

supplier:    () -> new ArrayList<String>()
accumulator: (list, word) -> list.add(word)
combiner:    (left, right) -> { left.addAll(right); return left; }
finisher:    list -> List.copyOf(list)
§§§

Note: §T§ and §A§ do not have to be the same type; §A§ and §R§ do not have to be the same either. For instance, we can collect a Stream of numbers into a statistics object containing count, sum, and average.

**The accumulator does not choose groups** and does not sort on its own. It performs one local task according to the contract: accepting exactly one element and accumulating information into the provided container.

## 3. The accumulator signature and how it works

The abstract method of §BiConsumer<T,U>§ has the signature:

§§§java
void accept(T first, U second);
§§§

For Collector, the types are assigned as follows:

§§§java
BiConsumer<A, T> accumulator
§§§

It receives:

1. **First parameter §A§:** the current accumulation container created by §supplier§, for example §ArrayList<String>§ or §MutableStats§.
2. **Second parameter §T§:** the element currently being passed by the Stream to the collector, for example §String`, §Employee§, or §Integer§.
3. **Return value:** §void§; the effect is recorded into the accumulation container object.

Example:

§§§java
(list, item) -> list.add(item)
§§§

§ArrayList.add(item)§ returns a boolean, but the lambda here is used in a target type context returning §void§: Java allows ignoring the return value of a compatible statement expression. Writing it in block form makes the update intent easier to read:

§§§java
(list, item) -> {
    list.add(item);
}
§§§

Both are **illustrative snippets**, only semantically complete when the compiler knows the types of §list§ and §item§ through the collector. In terms of design, an accumulator should usually **update the exact container passed in**, avoiding returning a new container without recording it.

If a mapper only creates a new value and does not modify the accumulation container, it is not a suitable accumulator yet. With a collector, container §A§ is used as intermediate storage so that the combiner and finisher can observe the right data.

## 4. Complete Java 17+ example: collecting names into a List container

We want to normalize each name with §trim§ and §toUpperCase(Locale.ROOT)§, then place them into a list in source order. Instead of using §map(...).toList()§, the example below creates a custom collector **to learn about the accumulator**.

Save the file §ListAccumulatorDemo.java§:

§§§java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collector;

public class ListAccumulatorDemo {
    public static void main(String[] args) {
        List<String> names = List.of("  lan  ", "minh", " an ");

        Collector<String, ArrayList<String>, List<String>> collector =
                Collector.of(
                        ArrayList::new,
                        (bucket, raw) -> {
                            String cleaned = raw.trim()
                                    .toUpperCase(Locale.ROOT);
                            bucket.add(cleaned);
                        },
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf
                );

        List<String> result = names.stream().collect(collector);

        System.out.println("result=" + result);
        System.out.println("count=" + result.size());
        System.out.println("source unchanged=" +
                names.get(0).equals("  lan  "));
    }
}
§§§

Compile/run:

§§§bash
javac ListAccumulatorDemo.java
java ListAccumulatorDemo
§§§

Exact output:

§§§text
result=[LAN, MINH, AN]
count=3
source unchanged=true
§§§

**Tracing the full cycle:**

1. §ArrayList::new§ creates an empty §ArrayList<String>§ as the temporary container §A§.
2. For each input string, the **accumulator** receives §(bucket, raw)§, normalizes the name, and calls §bucket.add(cleaned)§. The expected state after the elements is §[LAN]§, then §[LAN, MINH]§, and finally §[LAN, MINH, AN]§ if the framework executes sequentially in source order.
3. §combiner§ is provided so two temporary containers can be merged when the framework needs to; a sequential pipeline is not required to call it.
4. §List::copyOf§ finishes, creating a structurally unmodifiable §List<String>§ as the result. The collector does not directly return the mutable §ArrayList§ from the accumulator.
5. The source §names§ still retains the strings with whitespace. The accumulator updates the new container, **without modifying the source List**.

Performance note: in an application that only needs to normalize and get a list, the built-in §names.stream().map(...).toList()§ is shorter and easier to understand. The custom collector here is valuable because it **clarifies the lifecycle of the accumulation container**.

## 5. Why does the accumulator mutate A without mutating the source?

This is an important distinction in functional programming with Java Streams:

- **Mutation inside container §A§ owned by the collector** is the standard approach of mutable reduction.
- **Mutation to the source list being traversed by the stream** can violate the non-interference requirement, causing unreliable results or exceptions.
- **Mutation to a shared variable outside the collector** can cause race conditions when switching to a parallel stream, while also making the pipeline hard to test.

Example to avoid:

§§§java
List<String> external = new ArrayList<>();
source.parallelStream().forEach(external::add);
§§§

This is an **unsafe illustrative code snippet** if §source§ is a collection, requiring imports for §List§ and §ArrayList§. Multiple threads may call §ArrayList.add§ on the same object; §ArrayList§ is not thread-safe. Moreover, the order of additions into external does not necessarily reflect encounter order.

Replace with a collect operation:

§§§java
List<String> collected = source.parallelStream()
        .collect(java.util.stream.Collectors.toList());
§§§

With an ordered source and an appropriate downstream, the result obeys the Collector/Stream contract without manually sharing a mutable ArrayList. The collector can create multiple separate accumulation containers and use the combiner to merge them during parallel processing.

**Subtle point:** having a mutating accumulator does not mean the collector automatically has the §CONCURRENT§ characteristic. Mutating a partition's own container is **different** from supporting multiple threads calling the accumulator **concurrently on the same container**.

## 6. How it works when a Stream processes in parallel

In a simple case, you can imagine:

§§§text
                 Stream<T>
                 /       \
                /         \
          Partition 1   Partition 2
             |             |
          supplier()     supplier()
             |             |
          A(left)        A(right)
             |             |
        accumulator   accumulator
             \             /
              \           /
            combiner(left, right)
                     |
                     v
                A(merged)
                     |
                  finisher
                     |
                     v
                  Result R
§§§

The diagram is a **conceptual model**, not a guarantee of the number of times supplier/combiner are called, the number of threads, or the specific splitting structure. Those details are decided by the implementation and execution plan.

Important contract:

1. Supplier must create a new, independent container, not accidentally return a shared singleton object.
2. Accumulator accurately records the element into the received container.
3. Combiner must completely merge the contents of two containers so the result is equivalent to processing all the data.
4. Finisher turns the merged container into the final output, if the collector does not have §IDENTITY_FINISH§.
5. The supplier/accumulator/combiner functions must obey the compatibility and associativity/identity constraints required by Collector.

Do not assume §parallelStream()§ is always faster. For small datasets, the overhead of creating containers, splitting work, and merging containers can outweigh the benefits of parallelism.

## 7. Accumulator, combiner, and finisher cannot substitute for each other

### Accumulator: receives each element

§§§java
(bucket, value) -> bucket.add(value)
§§§

Each invocation processes only **one element T** and records it into **one container A**.

### Combiner: merges two containers A

§§§java
(left, right) -> {
    left.addAll(right);
    return left;
}
§§§

It does not receive an individual element T, but **two accumulation states A**. If the combiner accidentally returns only §left§ without moving elements from §right§ over, parallel collection can lose data.

### Finisher: converts A to R

§§§java
bucket -> List.copyOf(bucket)
§§§

It operates on the accumulated container, turning it into a result with a different contract. For example, a counting and summing collector will have a mutable container holding §count§ and §sum§, while the result can be an immutable record.

Comparison table:

| Function | Receives | Responsibility |
| --- | --- | --- |
| §accumulator.accept(a, t)§ | container §a§ and element §t§ | Updates the container with one element |
| §combiner.apply(a1, a2)§ | two containers | Merges state |
| §finisher.apply(a)§ | completed container | Creates the result object |

The three separate roles allow a custom collector to accurately replace loop-based data collection while still conforming to the Stream API contract.

## 8. Java 17+ example: an accumulator collecting count/sum statistics

An example that requires a more custom collector is collecting **count, sum, and average** in a single pass, using a mutable accumulation container and an immutable result.

Save §StatisticsAccumulatorDemo.java§:

§§§java
import java.util.List;
import java.util.stream.Collector;

public class StatisticsAccumulatorDemo {
    static final class MutableStats {
        long count;
        long sum;

        void accept(Integer value) {
            count++;
            sum += value;
        }

        MutableStats merge(MutableStats other) {
            count += other.count;
            sum += other.sum;
            return this;
        }

        Summary finish() {
            double average = count == 0
                    ? 0.0
                    : (double) sum / count;
            return new Summary(count, sum, average);
        }
    }

    record Summary(long count, long sum, double average) {}

    public static void main(String[] args) {
        Collector<Integer, MutableStats, Summary> statsCollector =
                Collector.of(
                        MutableStats::new,
                        MutableStats::accept,
                        MutableStats::merge,
                        MutableStats::finish
                );

        List<Integer> numbers = List.of(4, 6, 8);

        Summary sequential = numbers.stream()
                .collect(statsCollector);
        Summary parallel = numbers.parallelStream()
                .collect(statsCollector);
        Summary empty = List.<Integer>of().stream()
                .collect(statsCollector);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
§§§

Compile/run with Java 17:

§§§bash
javac StatisticsAccumulatorDemo.java
java StatisticsAccumulatorDemo
§§§

Output:

§§§text
sequential=Summary[count=3, sum=18, average=6.0]
parallel=Summary[count=3, sum=18, average=6.0]
empty=Summary[count=0, sum=0, average=0.0]
§§§

Detailed explanation:

- Supplier creates a §MutableStats(count=0, sum=0)§ for the temporary container.
- Accumulator §accept(Integer value)§ is called when an element enters that container: it increments §count§ and adds §value§ to §sum§.
- Combiner §merge§ adds the count and sum of two temporary containers; it returns the updated left container.
- Finisher creates the immutable record §Summary(count, sum, average)§, isolating the collector's mutable state.
- For an empty stream, supplier creates an empty state; finisher returns §Summary(0,0,0.0)§ according to the program's illustrative policy.

**Arithmetic issue:** §long§ addition can overflow if the data exceeds the range; the program uses a small set of numbers for illustration. If an application needs exact sums for extremely large quantities, consider §BigInteger`/§BigDecimal` and an input policy. Averaging with §double§ is a decision about the result type; it does not automatically provide absolute decimal precision. These factors are independent of the accumulator mechanism.

### Why is the statistics merge operation correct?

Two containers have states:

```text
left  = (count=c1, sum=s1)
right = (count=c2, sum=s2)
merged = (count=c1+c2, sum=s1+s2)
```

With non-overflowing arithmetic, the additions guarantee a consistent merged result regardless of how the data is split into partitions. Average is computed only **after merging**, avoiding taking the "average of averages" without accounting for the number of elements in each group.

Do not add the existing averages of each container and divide by two if the two group sizes differ: for example, group 1 has one score of 10, group 2 has three scores of 0; the true average is 2.5, not 5.0.

## 9. Implementing the same logic via a loop to understand the accumulator

The core of the accumulator in the statistics example is equivalent to updating a container in a loop:

```java
MutableStats state = new MutableStats();
for (Integer n : numbers) {
    state.accept(n);
}
Summary result = state.finish();
```

This is a code snippet placed inside the §StatisticsAccumulatorDemo` class alongside the §MutableStats` and §Summary` definitions above.

With the imperative style, we control the loop and choose the container ourselves. With §collect(statsCollector)§, the Stream framework controls calling supplier/accumulator/combiner/finisher according to the contract. Therefore, the accumulator should only describe **one update step**, without depending on the number of iterations, loop index, or number of threads.

**Do not declare an accumulator with global state** like:

```java
// Anti-pattern: unsuitable for parallel reuse
static long sharedTotal;
(bucket, n) -> sharedTotal += n;
```

The above is only illustrative pseudocode in a context with a static variable and a lambda needing a target type, **not a standalone Java class**. It ignores the §bucket§ container and updates a global variable; the collector's result is no longer determined by the accumulation container it owns, easily causing race conditions and wrong results when called multiple times.

## 10. Collector.of() and choosing IDENTITY_FINISH

Java has two particularly useful factory forms:

```java
Collector.of(supplier, accumulator, combiner)
Collector.of(supplier, accumulator, combiner, finisher)
```

The expressions above are **abbreviated overload descriptions**, not full method declarations.

- The **three-component** form applies when the output result is the accumulation container §A§ itself, and the collector receives the §IDENTITY_FINISH§ characteristic from this factory.
- The **four-component** form is used when container §A§ needs to be converted into a different result type or form using a finisher, for example §MutableStats → Summary§, or a copied §ArrayList<String> → List<String>§.
- Both have overloads accepting additional §Collector.Characteristics...§, but **do not declare a characteristic if the collector does not truly satisfy it**.

Example of a three-component collector:

```java
Collector<String, ?, List<String>> collector = Collector.of(
        java.util.ArrayList::new,
        (list, item) -> list.add(item),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

This is an illustrative declaration inside a method, requiring imports for §Collector` and §List`; when writing real code, you can specify type arguments or use a lambda with explicit types if the compiler cannot infer them as desired.

In this form, the result is the collector's accumulation container, usually a mutable list. Use the form with a finisher like §List::copyOf` if you want an unmodifiable result while ensuring **all elements are non-null** (since §List.copyOf` rejects null). Do not attach §IDENTITY_FINISH§ to a collector that uses a finisher to create a different object or a copy: the framework is allowed to skip the finisher when that characteristic is declared, leading to a wrong type/contract.

## 11. Collector.Characteristics and thread safety

Three commonly seen characteristics:

| Characteristic | Meaning | When to be cautious |
| --- | --- | --- |
| §IDENTITY_FINISH§ | The accumulated state can be treated directly as the result without conversion | Do not use if the finisher creates a copy or DTO |
| §UNORDERED§ | The collector does not guarantee preserving encounter order in the result | Do not use if list/string order is required |
| §CONCURRENT§ | The accumulator can be called concurrently from multiple threads on **the same container** | Do not use with §ArrayList`, §StringBuilder`, or unsynchronized mutable state |

For the examples in this article:

- A collector using §ArrayList::new` and §List::copyOf` does **not** have §IDENTITY_FINISH`.
- A collector accumulating names in source order should not declare §UNORDERED§ if name order is an API requirement.
- Accumulators mutating §ArrayList` or §MutableStats` **must not be marked §CONCURRENT§** because they are not designed for multiple threads to modify the same object simultaneously.

A very important point: **without declaring §CONCURRENT`, a collector can still be used with parallel streams**. The framework manages separate containers for partitions and then merges them via the combiner according to the contract. There is no need to add synchronization to every operation just because a Stream might run in parallel, if the collector uses a standard non-concurrent type and does not share containers improperly.

Do not force performance by enabling §CONCURRENT`. Characteristics must reflect **guaranteed behavior**, not a "trick to run fast".

## 12. Common mistakes with accumulators

### 12.1. Not updating the container passed in

Wrong approach:

```java
(list, value) -> {
    new ArrayList<String>().add(value);
}
```

This is an illustrative snippet in a context needing §BiConsumer<ArrayList<String>,String>`. It adds the element to a new list and discards that list, **without modifying §list§**, so the collection result loses data.

Correct:

```java
(list, value) -> list.add(value)
```

### 12.2. Accumulating into an external variable instead of the container

Operations like §total[0] += n` with a shared array outside the accumulator cause multiple collections to interfere with each other, especially during parallel processing. You should put the sum state into container §A` and merge containers using the combiner.

### 12.3. Using a combiner that only returns left and drops right

Wrong:

```java
(left, right) -> left
```

If the framework splits data into multiple containers, the right container is ignored. This might "pass" sequential tests but fail in parallel.

Correct for a list:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

### 12.4. Declaring a shared mutable supplier

Wrong:

```java
ArrayList<String> shared = new ArrayList<>();
Supplier<ArrayList<String>> supplier = () -> shared;
```

This is a code snippet inside a method with imports for §ArrayList` and §Supplier`. Every call to supplier returns **the exact same** list, causing state to be shared across collections or partitions. Better is §ArrayList::new` so a new container is created each time.

### 12.5. Marking CONCURRENT when the container is not thread-safe

If multiple threads call §bucket.add(...)§ concurrently on the same §ArrayList`, elements can be lost, state corrupted, or exceptions thrown. Do not mark §CONCURRENT` for accumulators based on ArrayList/MutableStats like in the examples.

### 12.6. Using a finisher incompatible with characteristics

For example, a collector with §finisher = List::copyOf` must not declare §IDENTITY_FINISH`. The output result is a different list, not the internal container. Wrong characteristics can cause the framework not to call the finisher as you expect.

### 12.7. Rely on execution details

Do not write business logic in the accumulator under assumptions like "each element is guaranteed to arrive on one thread", "supplier is always called once", or "combiner definitely runs in sequential". The API provides a **result contract**, not a guarantee of specific execution plan details.

## 13. Exercise: write an accumulator to collect a list of emails

Suppose each employee has a name and an email, and we need a collector that collects normalized emails (trim + lowercase), skips blank emails, and produces an unmodifiable list in source order.

Definition:

```java
record User(String name, String email) {}
```

Answer these yourself before looking at the solution:

1. What is the element type §T§?
2. What is a reasonable container §A§?
3. What steps does the accumulator need to take when receiving a §User§?
4. How does the combiner join two containers?
5. What should the finisher return, and can §IDENTITY_FINISH§ be declared?

### Complete Java 17+ reference solution

Create §EmailAccumulatorDemo.java§:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collector;

public class EmailAccumulatorDemo {
    record User(String name, String email) {}

    public static void main(String[] args) {
        List<User> users = List.of(
                new User("Lan", " Lan@Example.COM "),
                new User("An", " "),
                new User("Minh", "MINH@example.com")
        );

        Collector<User, ArrayList<String>, List<String>> emails =
                Collector.of(
                        ArrayList::new,
                        (acc, user) -> {
                            String email = user.email().trim()
                                    .toLowerCase(Locale.ROOT);
                            if (!email.isBlank()) {
                                acc.add(email);
                            }
                        },
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf
                );

        List<String> result = users.stream().collect(emails);

        System.out.println(result);
        System.out.println("count=" + result.size());
        System.out.println("users=" + users.size());
    }
}
```

Run:

```bash
javac EmailAccumulatorDemo.java
java EmailAccumulatorDemo
```

Output:

```text
[lan@example.com, minh@example.com]
count=2
users=3
```

Explanation:

- §T = User§, §A = ArrayList<String>§, and §R = List<String>§.
- The accumulator receives a §User§ and converts the email into a normalized string. If the string is blank, no element is added to the list. This is an illustrative business policy, not automatic Collector behavior.
- The combiner concatenates the email lists across containers without dropping data.
- The finisher creates an unmodifiable list using §List.copyOf`, so **do not use §IDENTITY_FINISH`**.
- The source §users§ still has three records; the collector only collects two non-blank emails.

If the input has §email == null`, the line §user.email().trim()` will throw a §NullPointerException`. In a real application, the policy must be stated clearly: reject null, treat null as blank, or label it. Do not assume a null email means an empty string.

Also, normalizing email addresses in real life depends on domain and system rules; the example is only meant to illustrate an accumulator, **not** a complete email normalizer.

## 14. When is a custom Collector not needed?

If you only need to collect a transformed list, prefer the built-in APIs:

```java
List<String> result = names.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();
```

This is a code snippet inside a method with a §names§ list; `String::toUpperCase` uses the default locale when taking no arguments; for data requiring deterministic locale rules, use §name -> name.toUpperCase(Locale.ROOT)` instead of this method reference.

Built-in collectors include:

- §Collectors.toList()§, §toSet()§, §toCollection(...)§.
- §Collectors.mapping(...)§, §filtering(...)§, §flatMapping(...)§ to transform/filter within a group or child collector.
- §Collectors.groupingBy(...)§, §partitioningBy(...)§ to split by key/condition.
- §Collectors.joining(...)§ to join CharSequences.
- §Collectors.summingInt(...)§, §summarizingInt(...)§, §counting()§, §reducing(...)§ for many aggregation operations.

A custom collector is worth considering when you need a specialized accumulation state, a single pass aggregating multiple metrics, or want to encapsulate create/merge/finish rules into an independently testable abstraction. **Do not write a custom accumulator just to replace a simple library call**.

In addition, if the problem is summing numbers, §reduce(identity, accumulator)§ has different semantics from mutable reduction with §collect(...)§: in immutable reduction, the accumulator of reduce **returns a new combined value**; whereas the BiConsumer of Collector **mutates container A and returns void**. Do not apply the habit of writing reduce lambdas directly to Collector.

## 15. Rules for reading and writing a correct accumulator

You can use the following checklist whenever designing a collector:

1. **What is T?** Identify the element the Stream actually supplies to the accumulator, possibly after §map/filter§.
2. **What does A hold?** Choose the minimal mutable structure sufficient to build the final result.
3. **Does the supplier create a new A each time?** Do not use a shared mutable singleton.
4. **Does the accumulator actually record the element into A?** Do not create a new object and discard it, and do not write to an external variable by mistake.
5. **Does the combiner merge both containers A completely?** Test especially with parallel streams.
6. **Is the merge operation associative per contract?** Try grouping data into different partitions and comparing results.
7. **Does the finisher convert A into R properly?** If creating a copy/DTO, do not attach IDENTITY_FINISH.
8. **Is encounter order needed?** Do not declare UNORDERED if list/sequence order is meaningful.
9. **Is it safe to call the accumulator concurrently on the same A?** If not, do not attach CONCURRENT.
10. **Are there side effects outside the collector?** Prefer letting container A manage all state.
11. **How are empty and null inputs handled?** Supplier/finisher must produce a valid result per contract; null needs a specific rule.
12. **Have sequential and parallel been tested?** Only use parallel if the collector meets the contract and the performance is worthwhile.

**Conclusion:** the accumulator in a Collector is a **BiConsumer<A,T> that updates the accumulation container A with each element T**. It is not the combiner, not the finisher, and does not modify the data source itself. When you understand that supplier creates a new container, accumulator records data, combiner merges containers, and finisher produces the result, you will design custom Collectors that are correct, easy to test, and able to work with sequential or parallel Streams according to the contract.

**References:** Java SE 17 API §java.util.stream.Collector§, §Collector.of§, §java.util.stream.Stream.collect§, §java.util.function.BiConsumer§, §java.util.stream.Collectors§; the Collector specification sections on identity/associativity, Characteristics, and mutable collection.