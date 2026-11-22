# Testing a Custom Collector with Empty Sources, Grouping, and Parallel Execution

## Objectives

A `Collector` may be correct when `stream()` runs sequentially on three records, yet fail when the source is empty, when the Stream is split into parts, or when running `parallelStream()`. The cause usually lies in a `supplier` that does not create a neutral state, a `combiner` that drops data, branches sharing a mutable accumulator, or declaring the wrong `Collector.Characteristics`.

This lesson tests a real custom Collector in Java 17. After studying it, you will be able to define `Collector<T,A,R>`, test empty/singleton cases, actively merge two accumulation containers, use a Collector as a downstream of `groupingBy`, compare sequential/parallel execution, evaluate the finisher and characteristics, and build a test suite with an independent expected result.

## 1. The Contract of Collector.of

A Collector has three types:

- `T`: the input element, for example `Sale`.
- `A`: the intermediate accumulation container, for example an `Accumulator` with mutable fields.
- `R`: the final result, for example a `Report` record containing an unmodifiable result Map.

The factory form with a finisher:

```java
Collector.of(supplier, accumulator, combiner, finisher)
```

Components and functional interfaces:

| Component | Functional interface | What to test |
| --- | --- | --- |
| `supplier` | `Supplier<A>` | Creates a **new** `A` container each time, initially neutral |
| `accumulator` | `BiConsumer<A,T>` | Incorporates each element T into A accurately |
| `combiner` | `BinaryOperator<A>` | Combines two A instances, returns the merged A without losing data |
| `finisher` | `Function<A,R>` | Converts A to R with the right type and contract |
| `characteristics` | Collector attributes | Only declares what is actually guaranteed |

**API distinction:** `Collector.of` takes a combiner of type `BinaryOperator<A>` **returning A**; the `Stream.collect(supplier, accumulator, combiner)` overload takes a combiner of type `BiConsumer<R,R>` returning `void`. Do not confuse these two contracts.

Important invariants: the state from the supplier must be neutral when combined; the accumulator and combiner must be compatible; the observable result must be equivalent when splitting the source in valid ways; and it must not depend on external side effects or uncontrolled shared state.

## 2. Data Design and Expected Results

The model uses two records:

```java
record Sale(String channel, String region, int units, long unitPriceCents) {}

record Report(long count, long units, long revenueCents,
              SortedMap<String, Long> unitsByRegion) {}
```

In the full program, there are five Sales:

| Channel | Region | Units | Price (cents) | Revenue (cents) |
| --- | --- | ---: | ---: | ---: |
| web | north | 2 | 1250 | 2500 |
| store | south | 1 | 600 | 600 |
| web | north | 3 | 200 | 600 |
| store | west | 4 | 400 | 1600 |
| web | south | 2 | 750 | 1500 |

The result must be **count=5, units=12, revenueCents=6800, unitsByRegion={north=5, south=3, west=4}**. This is an *oracle* computed directly from the input, independent of the Collector. If you only verify parallel against sequential, both can be wrong together because they use the same buggy formula.

When grouped by `channel`:

- `store`: count=2, units=5, revenueCents=2200, region `{south=1, west=4}`.
- `web`: count=3, units=7, revenueCents=4600, region `{north=5, south=2}`.

Check each group individually as well; checking only the sum across groups can still hide a classifier bug that assigns elements to the wrong group.

## 3. Accumulator and Bugs to Catch

The Accumulator holds count, units, revenue, and a `TreeMap<String,Long>`. When adding a Sale:

```java
void add(Sale sale) {
    count++;
    units += sale.units();
    revenueCents += (long) sale.units() * sale.unitPriceCents();
    byRegion.merge(sale.region(), (long) sale.units(), Long::sum);
}
```

When combining two branches:

```java
Accumulator combine(Accumulator other) {
    count += other.count;
    units += other.units;
    revenueCents += other.revenueCents;
    other.byRegion.forEach((key, value) ->
            byRegion.merge(key, value, Long::sum));
    return this;
}
```

Every field must be merged. If the combiner only adds `revenueCents` and forgets `count` or `byRegion`, sequential tests may pass while chunk-splitting tests will fail. In this example, `TreeMap` gives the output a deterministic key order; `Map.equals` is used to compare results by entry, independent of thread execution order.

Finisher:

```java
Report finish() {
    return new Report(count, units, revenueCents,
            Collections.unmodifiableSortedMap(new TreeMap<>(byRegion)));
}
```

Copying the `TreeMap` isolates the result data from the mutable accumulator. The wrapper prevents modifying the Map through `Report`. This is **shallow immutability**: appropriate when Map values are immutable `Long`s, but if values are mutable objects you still need to consider deep copying.

### Supplier must create a new container

**Correct:** `Accumulator::new`.

**Contract violation:**

```java
Accumulator shared = new Accumulator();
// Do not use: every supplier call returns the exact same object.
() -> shared
```

When running in parallel, branches can mutate the same object, causing races, and the combiner may even receive two references to the same state. Using a `synchronized` container does not automatically fix an identity/combiner bug either.

### Combiner must actually merge

Wrong: `(left,right) -> left` — it has no effect of adding the data from right. This form can compile and pass sequential tests when the combiner is not invoked. Therefore, **creating two separate accumulators and calling the combiner in a test** is essential.

## 4. Testing Empty and Singleton Cases

Start from an empty source:

```java
Report empty = List.<Sale>of().stream().collect(reportCollector());
```

Expected:

```text
Report[count=0, units=0, revenueCents=0, unitsByRegion={}]
```

No Sale is accumulated. The supplier must create a valid state, the finisher must handle an empty state, and it must not assume an element exists to call `get(0)`, `max().get()`, or take the first key.

With a single Sale `("web","north",2,1250)`, expected is count=1, units=2, revenue=2500, region north=2. Empty catches identity/finisher bugs; singleton helps verify `accumulator` before introducing the combiner into the problem.

**Note when using groupingBy:** directly collecting an empty source returns an empty `Report`, whereas `emptyStream.collect(groupingBy(channel, downstream))` returns an **empty Map** because no keys appear. There will not automatically be an entry `store -> empty Report` unless the application populates the expected set of keys.

## 5. Testing the Combiner by Splitting Data

Create a helper:

```java
static Accumulator accumulate(List<Sale> sales) {
    Accumulator acc = new Accumulator();
    sales.forEach(acc::add);
    return acc;
}
```

Split the five Sales into 2 and 3:

```java
Accumulator left = accumulate(sales.subList(0, 2));
Accumulator right = accumulate(sales.subList(2, sales.size()));
Report split = left.combine(right).finish();
Report sequential = sales.stream().collect(reportCollector());

System.out.println(split.equals(sequential)); // true
```

The left part has count=2, units=3, revenue=3100; the right part has count=3, units=9, revenue=3700. `combine` must yield count=5, units=12, revenue=6800 and Map north=5/south=3/west=4. If the right part is dropped, count is only 2.

Expand the tests: split 0+n, 1+(n-1), multiple chunks with duplicate keys across chunks, and three chunks `a,b,c` to compare `combine(combine(a,b),c)` against `combine(a,combine(b,c))`. **You must recreate fresh accumulators for both sides**, because this lesson's combine mutates the left container. Compare `finish` by value, not by object identity.

Integer addition has type bounds. If using `double`, addition order can change rounding error; in that case you need an acceptable tolerance criterion rather than always requiring bit-for-bit equality.

## 6. Testing groupingBy with a Downstream Collector

Place the custom Collector inside `groupingBy`:

```java
Map<String, Report> byChannel = sales.stream().collect(
        Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()
        )
);
```

`Sale::channel` determines the group key. `TreeMap::new` ensures Map keys are iterated in natural order in the example. `reportCollector()` collects each group separately into a `Report`.

Verify that `byChannel.keySet()` contains `store` and `web`, then compare `units`, `count`, `revenueCents`, and `unitsByRegion` **for each Report**. Do not just check the number of groups or the grand total.

Two concepts of "grouping/splitting" must be distinguished:

1. **Business grouping**: the classifier groups by channel, product, region.
2. **Execution partitioning**: the Stream runtime splits the source into chunks and uses the combiner to merge partial results.

A Collector must be correct in **both**. For missing keys, `Collectors.groupingBy` does not allow the classifier to return `null`, even when the Map factory uses HashMap; you must normalize, use a missing-state key, or reject the input according to requirements. For a null region in the accumulator's natural-order `TreeMap`, `merge` can throw NPE. Do not overlook these cases.

## 7. Testing Parallel Execution and Characteristics

Compare results:

```java
Report sequential = sales.stream().collect(reportCollector());
Report parallel = sales.parallelStream().collect(reportCollector());

boolean same = parallel.equals(sequential);
```

Iterating over multiple datasets and different partitions is better than running just once. Repeating the same test 20 times increases the chance of observing a bug, but **does not prove** the Collector is safe under all schedules. Tests must also rely on independent expected values.

For groups, compare:

```java
Map<String, Report> seqGroups = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()));
Map<String, Report> parGroups = sales.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::channel, TreeMap::new, reportCollector()));

boolean groupedSame = seqGroups.equals(parGroups);
```

Compare Maps by value instead of comparing callback order logs. Do not assume `supplier` is called a fixed number of times, or that threads execute `accumulator` in encounter order.

The Collector in this example **does not declare** `CONCURRENT`, `UNORDERED`, or `IDENTITY_FINISH`. Because `Accumulator` has a `TreeMap` and mutable `long` fields, it is not safe for multiple threads to mutate the same container; because the finisher converts `Accumulator` to `Report`, there is no identity finish. **`CONCURRENT` is not required to be used with `parallelStream`**: the runtime can allocate separate accumulators for partitions and merge them via the combiner.

Do not declare `Collector.Characteristics.CONCURRENT` just to "speed things up"; it is a contract about the ability to update a single result container concurrently, not a switch to enable parallel mode. If you want a true concurrent Collector, you must design a thread-safe concurrent accumulator and test it thoroughly.

## 8. Complete Java 17 Program

Create the file **`CustomCollectorValidationDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CustomCollectorValidationDemo {
    record Sale(String channel, String region,
                int units, long unitPriceCents) {}

    record Report(long count, long units, long revenueCents,
                  SortedMap<String, Long> unitsByRegion) {}

    static final class Accumulator {
        long count;
        long units;
        long revenueCents;
        final TreeMap<String, Long> byRegion = new TreeMap<>();

        void add(Sale sale) {
            count++;
            units += sale.units();
            revenueCents += (long) sale.units() * sale.unitPriceCents();
            byRegion.merge(sale.region(), (long) sale.units(), Long::sum);
        }

        Accumulator combine(Accumulator other) {
            count += other.count;
            units += other.units;
            revenueCents += other.revenueCents;
            other.byRegion.forEach((key, value) ->
                    byRegion.merge(key, value, Long::sum));
            return this;
        }

        Report finish() {
            return new Report(count, units, revenueCents,
                    Collections.unmodifiableSortedMap(
                            new TreeMap<>(byRegion)));
        }
    }

    static Collector<Sale, Accumulator, Report> reportCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    static Accumulator accumulate(List<Sale> sales) {
        Accumulator acc = new Accumulator();
        sales.forEach(acc::add);
        return acc;
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("web", "north", 2, 1_250),
                new Sale("store", "south", 1, 600),
                new Sale("web", "north", 3, 200),
                new Sale("store", "west", 4, 400),
                new Sale("web", "south", 2, 750)
        );

        Report empty = List.<Sale>of().stream()
                .collect(reportCollector());
        Report sequential = sales.stream()
                .collect(reportCollector());
        Report parallel = sales.parallelStream()
                .collect(reportCollector());

        Accumulator left = accumulate(sales.subList(0, 2));
        Accumulator right = accumulate(sales.subList(2, sales.size()));
        Report split = left.combine(right).finish();

        Map<String, Report> groupedSequential = sales.stream().collect(
                Collectors.groupingBy(
                        Sale::channel, TreeMap::new, reportCollector()));
        Map<String, Report> groupedParallel = sales.parallelStream().collect(
                Collectors.groupingBy(
                        Sale::channel, TreeMap::new, reportCollector()));

        boolean allParallelMatch = true;
        for (int i = 0; i < 20; i++) {
            if (!sequential.equals(
                    sales.parallelStream().collect(reportCollector()))) {
                allParallelMatch = false;
                break;
            }
        }

        System.out.println("Empty: " + empty);
        System.out.println("Sequential: " + sequential);
        System.out.println("Parallel equals sequential: "
                + parallel.equals(sequential));
        System.out.println("Split equals sequential: "
                + split.equals(sequential));
        System.out.println("Repeated parallel matches: " + allParallelMatch);
        System.out.println("Channels: " + groupedSequential.keySet());
        System.out.println("Store units: "
                + groupedSequential.get("store").units());
        System.out.println("Web units: "
                + groupedSequential.get("web").units());
        System.out.println("Grouped parallel matches: "
                + groupedParallel.equals(groupedSequential));
        System.out.println("IDENTITY_FINISH: " + reportCollector()
                .characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("CONCURRENT: " + reportCollector()
                .characteristics().contains(
                        Collector.Characteristics.CONCURRENT));
        try {
            sequential.unitsByRegion().put("east", 7L);
        } catch (UnsupportedOperationException e) {
            System.out.println("Result map modifiable: false");
        }

        Accumulator incomplete = accumulate(sales.subList(0, 2));
        System.out.println("Missing combiner loses records: "
                + (incomplete.finish().count() < sequential.count()));
    }
}
```

Compile and run:

```bash
javac CustomCollectorValidationDemo.java
java CustomCollectorValidationDemo
```

**Exact stdout** (run with `javac --release 17`):

```text
Empty: Report[count=0, units=0, revenueCents=0, unitsByRegion={}]
Sequential: Report[count=5, units=12, revenueCents=6800, unitsByRegion={north=5, south=3, west=4}]
Parallel equals sequential: true
Split equals sequential: true
Repeated parallel matches: true
Channels: [store, web]
Store units: 5
Web units: 7
Grouped parallel matches: true
IDENTITY_FINISH: false
CONCURRENT: false
Result map modifiable: false
Missing combiner loses records: true
```

The last line is a **negative experiment**: intentionally taking only the first two Sales and comparing the record count with the full five-Sale result. It proves the test can detect dropped data, not that the correct Collector lost data. `Report` is a record so `equals` compares fields by value; `SortedMap.equals` compares Map contents.

The example uses fixed values, performs no I/O, has a filename matching the public class, and requires no libraries outside Java 17.

## 9. Test Matrix Needed in a Project

| Scenario | Test data | Expected |
| --- | --- | --- |
| Empty source | 0 Sales | Report count=0, units=0, revenue=0, empty Map |
| Single element | First Sale | Count=1, units=2, revenue=2500, north=2 |
| Sequential | 5 Sales | Count=5, units=12, revenue=6800 |
| Empty + full chunk | 0+5 elements | Result still matches full source |
| 2+3 chunk | Two separate accumulators | `left.combine(right)` equals sequential |
| Multiple chunks | 1+1+3; 2+1+2 | All valid merge orders are equivalent |
| Duplicate key | north in both chunks | north is summed to 5 |
| groupingBy | store/web | Store units=5, web units=7 |
| groupingBy parallel | Same as above | Every Report by key matches |
| Repeated parallel | Multiple runs and multiple inputs | No difference from oracle |
| Result immutability | Call put on Report Map | UnsupportedOperationException |
| Characteristics | Inspect Collector | Does not declare CONCURRENT/IDENTITY_FINISH |
| Invalid data | null region, null Sale | Handled or throws error per contract |

### Coverage to prioritize

If sequential passes but parallel fails, check whether `supplier` returns the same object, whether `combiner` drops data, whether all statistical fields are merged, and whether external state is used. If both fail, check the calculations in `accumulator` against the oracle. If only `groupingBy` fails, check the classifier/key, null state, ordering, and downstream.

Do not just compare global totals: an incorrect grouping can still preserve the total. Check every key, every Report, and the record counts.

## 10. Anti-patterns and Practical Limitations

### 10.1. Combiner dropping data

Wrong:

```java
(left, right) -> left
```

Fix by merging every field and returning the merged result. Sequential-only tests may never invoke the combiner, so manual split testing is mandatory if you want to catch this bug reliably.

### 10.2. Wrong identity initialization

If `Accumulator` starts with `count=1`, an empty source is already wrong. When running in parallel, each branch may start from count=1, making the total even more wrong. The supplier must create a neutral state.

### 10.3. Using a shared object

Do not let a static/captured `Accumulator` be returned on every supplier call. An external `AtomicLong` should also not replace the `count` field inside Report, because the result can depend on how many times the pipeline is run. Proper mutable reduction **mutates a private container managed within the collect operation**, rather than arbitrarily mutating external state.

### 10.4. Associativity and numeric values

`combine` must be associative with respect to the result's semantics. Regular subtraction is not associative; using it to combine multiple chunks will yield results that depend on how chunks are grouped. With `double` numbers, rounding error can depend on addition order; you must test with an acceptable error tolerance and choose numeric types according to business needs. The example uses `long` yet still carries overflow risk; if data can be large, use `Math.addExact`/`multiplyExact` or a wider numeric type.

### 10.5. Nulls, exceptions, and resources

A null `Sale` causes the accumulator to dereference null. `TreeMap` with natural ordering does not accept a null region. `groupingBy` does not accept a classifier returning null. You need a clear policy to validate, normalize, or filter out records before collecting.

Standard functional interfaces do not declare checked exceptions in `accept/apply`; I/O inside callbacks must be handled per contract. `collect` also does not automatically close a source from `Files.lines`; use `try-with-resources` when the source holds resources.

### 10.6. Performance

A Collector can be correct in parallel yet slower than sequential because it must create multiple accumulators and merge Maps. For small sources, parallel is usually not worth the coordination overhead. When only aggregate numbers are needed, a small accumulator avoids holding the entire list of Sales in memory; however, `byRegion` still grows with the number of distinct keys.

## 11. Exercises

1. Why must an empty stream return a Report with all zero fields and an empty Map?
2. Write a singleton test with the first Sale. What are the expected `count`, `units`, `revenue`, and region?
3. Why can `(left,right) -> left` pass a sequential test yet fail when splitting into chunks?
4. Write a test splitting the source into 1 and 4 elements; compare the result with sequential.
5. Write a test combining three Accumulators with two different parenthesizations; what must you watch out for when `combine` mutates left?
6. Use `groupingBy(Sale::channel, TreeMap::new, reportCollector())`. Compute the store/web values.
7. If both sequential and parallel produce revenue 7000 instead of 6800, why is comparing the two results against each other not enough?
8. Why not mark `IDENTITY_FINISH` when the finisher returns Report?
9. Why does `parallelStream()` not require a Collector to be `CONCURRENT`?
10. If region is null, what error can occur in TreeMap? Choose a data handling policy.
11. A combiner only merges `revenueCents`. Which test detects that the remaining fields are wrong?
12. Report contains a mutable `SortedMap`. How do you prevent the caller from mutating the structure and the accumulator from leaking state?
13. With new data, how do you verify that groupingBy places each Sale into the right group, not just preserves the total?
14. Why does repeating a parallel run 20 times not prove a Collector is 100% correct?

**Suggested answers:** (1) Supplier creates the identity; even with no elements there must be a valid result. (2) 1, 2, 2500, north=2. (3) Does not merge right; sequential may not invoke the combiner. (4) Create two independent accumulators then `combine`. (5) Recreate accumulators for each side to avoid mutation from the previous trial. (6) store count2/units5/revenue2200, web count3/units7/revenue4600. (7) An independent oracle is needed. (8) A and R are different types, so finisher must run. (9) The framework can use independent containers and then merge them. (10) NPE; validate or use a non-null missing-state key. (11) Check count, units, and byRegion in split/parallel tests. (12) Copy the TreeMap then wrap with `unmodifiableSortedMap`. (13) Assert the keys and the full Report for each group. (14) Test coverage is finite; diverse inputs, partitions, and boundaries are needed.

## Conclusion

A **reliable custom Collector** does not just produce the right result on a sequential Stream. It needs to create a valid identity for an empty source, accumulate each element accurately, **completely merge accumulation containers** when partitioned, produce the right result type via the finisher, and declare accurate characteristics.

Test empty, singleton, chunk split/merge, groupingBy downstream, and parallel execution by **observable values**; verify against an independently computed expected result. That is how you catch supplier/combiner/shared-state bugs that are easily masked in a single sequential run, while making the Collector safely reusable in Java applications.
