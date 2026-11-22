# Finisher Converting an Accumulator to a Result in a Custom Java Collector

## 1. The Problem: The Accumulation Object Is Not Always the Final Result

In the Java Stream API, when calling `stream.collect(collector)`, data goes through a **collection** process (*mutable reduction*). A collector can use a temporary **mutable** structure to gather elements, yet return the final result in **a different type** that is cleaner, safer, or better aligned with the business contract.

For example: suppose we need to compute a revenue report from orders. While traversing, we store the count and total amount in a mutable accumulator. Once traversal finishes, the API should only return a `RevenueReport` record containing the final numbers, without giving the caller the ability to mutate the accumulator.

This is the role of the **finisher**:

~~~text
Stream<T>
   |
   v
supplier() --> initial A
                 |
                 v
          accumulator(A,T) -- receives elements
                 |
                 v
          combiner(A,A)    -- merges branch results when needed
                 |
                 v
          finisher(A) --> final result R
~~~

Where:

- **T**: the input element type of the Stream.
- **A**: the **accumulation type**, usually an internal mutable object.
- **R**: the **result type** returned after collection completes.
- **finisher**: a `Function<A,R>` that converts the temporary structure A into the result R.

A short illustrative example, **not a standalone program**:

~~~java
Collector<Order, ReportAccumulator, RevenueReport> collector =
        Collector.of(
                ReportAccumulator::new,   // supplier: () -> A
                ReportAccumulator::add,   // accumulator: (A,T) -> void
                ReportAccumulator::merge, // combiner: (A,A) -> A
                ReportAccumulator::finish // finisher: A -> R
        );
~~~

If `ReportAccumulator` differs from `RevenueReport`, using a finisher **is not an optional extra step**: it is the step that produces the result type promised to the caller. A collector can accumulate conveniently using A while **not exposing A** in the public API.

## 2. Collector<T,A,R> and the Four Component Functions

The `java.util.stream.Collector<T,A,R>` interface models mutable reduction. When creating a custom collector, four components are typically needed:

| Component | Functional Type | Purpose |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Creates a new accumulation container |
| `accumulator()` | `BiConsumer<A,T>` | Incorporates a T into A by updating A |
| `combiner()` | `BinaryOperator<A>` | Merges two A containers into one A container |
| `finisher()` | `Function<A,R>` | Converts the final A into R |

**Semantic execution order:** elements are accumulated into one or more A containers; the A containers may be combined; finally, one complete A is converted into the result R. How branches are split and executed in a parallel stream is up to the Stream implementation and must not be treated as a fixed execution schedule.

A Collector also has **characteristics** such as `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` to describe specific guarantees. They are not decorative labels: declaring them incorrectly can lead to incorrect results.

### 2.1. Finisher Is `Function<A,R>`, Not `Consumer<A>`

A common mistake is writing a finisher that only logs output and assuming it has produced the result. **The finisher must return R**, because `Collector.finisher()` has type `Function<A,R>`. Illustration:

~~~java
Function<Accumulator, Report> finish = acc ->
        new Report(acc.count, acc.sum);
~~~

This is an illustrative snippet, assuming the `Accumulator` and `Report` types already exist. If you only want to log, that is a side effect rather than the collector's result; avoid relying on logging as the primary purpose of a finisher.

### 2.2. R Can Differ From A or Be the Same as A

There are two possibilities:

1. **Non-identity finisher:** A is `ArrayList<T>`, and R is an immutable `List<T>`; or A is `MutableStats`, and R is `Report`.
2. **Identity finisher (identity finish):** the result is the accumulator A itself. Collectors of this kind can be described by the `IDENTITY_FINISH` characteristic if they satisfy all requirements of that characteristic.

Even when A and R have the same type, the finisher is not always an identity finish. For example, A is `List<String>` and R is also `List<String>`, but the finisher returns **an immutable copy**. That is still a real transformation, because **the object and its mutability have changed**.

## 3. Collector.of() and Two Easily Confused Overloads

Java provides two key forms of `Collector.of`:

~~~java
// Identity-finish overload: no explicit finisher passed.
Collector.of(supplier, accumulator, combiner, characteristics...);

// Overload with finisher: A can differ from R.
Collector.of(supplier, accumulator, combiner, finisher,
        characteristics...);
~~~

The two lines above are **syntax descriptions**, not complete Java source code, because the variables are not declared.

**When to use the overload with a finisher?**

- You need to return a report record instead of a mutable accumulator class.
- You need to convert a `StringBuilder` into a `String`.
- You need to compute derived fields such as averages, percentages, or statuses.
- You need to create an immutable snapshot of an accumulated list or map.
- You need to validate final invariants before publishing the result.

**When is a finisher not strictly needed?** If you want to return the mutable collection created by the Supplier directly—for example, an `ArrayList<T>`—you can use a collector with identity finish or `Collectors.toCollection(ArrayList::new)`.

### 3.1. Do Not Mark IDENTITY_FINISH If the Finisher Actually Transforms

`Collector.Characteristics.IDENTITY_FINISH` states that the finisher can be **omitted**, because an unchecked cast from A to R is sufficient to return the result. This is only valid if A can genuinely serve as the result R under the collector contract.

Therefore, the following snippet is an **anti-pattern**:

~~~java
// CONTRACT VIOLATION: A is StringBuilder, R is String,
// yet IDENTITY_FINISH is declared.
Collector.of(
        StringBuilder::new,
        StringBuilder::append,
        (left, right) -> left.append(right),
        StringBuilder::toString,
        Collector.Characteristics.IDENTITY_FINISH);
~~~

This is an intentionally wrong example and should not be run. If the runtime skips the finisher and tries to return A as R, the code may throw a `ClassCastException` or exhibit contract-violating behavior.

**Important:** Even when both A and R are `List<String>`, if the finisher returns **List.copyOf(accumulator)** to protect the result, you **must not** declare IDENTITY_FINISH. If the framework skips the finisher, the caller could receive the mutable accumulation list instead of the immutable snapshot promised by the API.

## 4. Complete Java 17 Example: Mutable Accumulator → Immutable Report

Create the file **FinisherReportDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

record Order(String id, long amountCents, boolean paid) {}

record RevenueReport(long count, long totalCents,
                     double averageCents, List<String> ids) {}

public class FinisherReportDemo {
    static final class Accumulator {
        private long count;
        private long total;
        private final ArrayList<String> ids = new ArrayList<>();

        void add(Order order) {
            count++;
            total = Math.addExact(total, order.amountCents());
            ids.add(order.id());
        }

        Accumulator combine(Accumulator other) {
            count = Math.addExact(count, other.count);
            total = Math.addExact(total, other.total);
            ids.addAll(other.ids);
            return this;
        }

        RevenueReport finish() {
            double average = count == 0 ? 0.0
                    : (double) total / count;
            return new RevenueReport(
                    count, total, average, List.copyOf(ids));
        }
    }

    static Collector<Order, Accumulator, RevenueReport> reportCollector() {
        return Collector.of(
                Accumulator::new,
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 100, true),
                new Order("B", 150, false),
                new Order("C", 200, true)
        );

        RevenueReport report = orders.stream()
                .filter(Order::paid)
                .collect(reportCollector());

        RevenueReport empty = List.<Order>of()
                .stream().collect(reportCollector());

        System.out.println("Count: " + report.count());
        System.out.println("Total: " + report.totalCents());
        System.out.println("Average: " + report.averageCents());
        System.out.println("IDs: " + report.ids());

        System.out.println("Empty count: " + empty.count());
        System.out.println("Empty total: " + empty.totalCents());
        System.out.println("Empty average: " + empty.averageCents());
        System.out.println("Empty IDs: " + empty.ids());
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 FinisherReportDemo.java
java FinisherReportDemo
~~~

Stdout:

~~~text
Count: 2
Total: 300
Average: 150.0
IDs: [A, C]
Empty count: 0
Empty total: 0
Empty average: 0.0
Empty IDs: []
~~~

**Explanation of each component:**

1. **Supplier** is `Accumulator::new`. Each container starts with count=0, total=0, and an empty IDs list.
2. **Accumulator** is `Accumulator::add`, called for each Order after the `filter(Order::paid)` step. Only A and C are collected.
3. **Combiner** is `Accumulator::combine`, which merges count, total, and appends IDs between two accumulation containers. When running sequentially, the combiner might not need to be called.
4. **Finisher** is `Accumulator::finish`, which computes the average and creates a `RevenueReport`. It returns **List.copyOf(ids)** to hold a structurally unmodifiable snapshot of the ID list.
5. The `Math.addExact` method catches `long` addition overflow with an `ArithmeticException`, instead of silently overflowing. This is a policy choice of this example; not every collector needs the same policy.
6. When there are no elements, the finisher still produces a RevenueReport with count=0, total=0, average=0.0, and an empty list. **0.0 here is the program's fallback rule**, not a mathematically defined average for an empty set.

**Choosing the right API:** If the caller needs to distinguish "no data" from "data with an exact average of 0", the record should use **OptionalDouble average** or a dedicated status field instead of defaulting to 0.0. Choose the structure of R based on business semantics, not just printing convenience.

### 4.1. Why Is A Usually Mutable While R Should Be Immutable?

During traversal, each element needs to update counts, sums, lists, and so on, so a mutable accumulator keeps operations simple. After collection completes, however, the caller should generally only see the final report and should not be able to accidentally alter counters or invariants.

In the example, `Accumulator` is a private implementation detail of the class, whereas `RevenueReport` is a record. The IDs list is copied with `List.copyOf`, so the caller cannot add or remove IDs.

**Caution:** A record does not automatically deep-copy every field that holds an object. `List.copyOf` creates a structurally unmodifiable list, but if the ID elements were mutable objects instead of Strings, the contents of those element objects could still be mutated. For data with strict ownership requirements, define an appropriate deep copy.

## 5. Finisher Must Wait for Accumulator and Combiner to Finish

A helpful way to think about it:

~~~text
Sequential source:
  supplier → A
  A = add(T1), add(T2), add(T3) ...
  finisher(A) → R

Parallel source (conceptual model):
  supplier → A1; add a subset
  supplier → A2; add another subset
  supplier → A3; add another subset
  combine(A1,A2) → A12
  combine(A12,A3) → A
  finisher(A) → R
~~~

This is a **semantic model**, not a fixed task schedule. The Stream is free to decide the number of containers, the splitting strategy, and when to combine them in accordance with the collector's characteristics.

**The combiner must return A**, not R. If a combiner accidentally invokes the finisher and turns a container into the result record, subsequent steps no longer have a container of the right type to accumulate into or combine, especially in a parallel stream.

Conceptual anti-pattern:

~~~java
// WRONG: combiner must not return Report when A is Accumulator.
// (left, right) -> new Report(...)
~~~

This is an intentionally wrong illustration; the combiner must have the signature `BinaryOperator<A>`, corresponding to **(A,A) -> A**.

### 5.1. Correctness Law: Partial Combination Must Not Change the Result

If a set of elements is split into multiple groups, collected separately, and then combined, the result after the finisher must be equivalent to collecting the entire set sequentially according to the collector's contract.

Illustration:

~~~text
finish(merge(accumulate(S1), accumulate(S2)))
    equivalent to
finish(accumulate(S1 concatenated with S2))
~~~

For an ordered collector, encounter order must be preserved when combining. In the RevenueReport example, `ids.addAll(other.ids)` preserves order if left and right represent two contiguous segments of data in encounter order; count and total are merged as well.

**Practical rule:** When designing a custom collector, always test both sequential and parallel streams with the same data, especially if the finisher builds an ordered list or performs calculations that depend on how results are merged.

## 6. Java 17 Example: Finisher With StringBuilder → String

StringBuilder is an efficient mutable accumulation container for building strings, while the final result type needs an immutable **String**.

Create the file **StringFinisherDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class StringFinisherDemo {
    static Collector<String, StringBuilder, String> pipeJoiner() {
        return Collector.of(
                StringBuilder::new,
                (builder, value) -> {
                    if (builder.length() > 0) {
                        builder.append("|");
                    }
                    builder.append(value);
                },
                (left, right) -> {
                    if (right.length() == 0) {
                        return left;
                    }
                    if (left.length() > 0) {
                        left.append("|");
                    }
                    left.append(right);
                    return left;
                },
                StringBuilder::toString
        );
    }

    public static void main(String[] args) {
        List<String> values = List.of("a", "b", "c", "d");

        String joined = values.stream().collect(pipeJoiner());
        String parallel = values.parallelStream().collect(pipeJoiner());
        String empty = List.<String>of().stream().collect(pipeJoiner());

        System.out.println("Sequential: " + joined);
        System.out.println("Parallel: " + parallel);
        System.out.println("Empty: [" + empty + "]");
    }
}
~~~

Compile and run:

~~~bash
javac StringFinisherDemo.java
java StringFinisherDemo
~~~

Stdout:

~~~text
Sequential: a|b|c|d
Parallel: a|b|c|d
Empty: []
~~~

**Why is this example valid?**

- The supplier creates an empty StringBuilder for each accumulation container.
- The accumulator adds a delimiter when needed and then appends the new String.
- The combiner joins two StringBuilders, inserting a delimiter between them **if both have content**; it properly ignores empty containers.
- The finisher converts the final StringBuilder into a String.
- This collector **does not have the UNORDERED characteristic**, so the result of a stream with an encounter order is required to preserve order, even when collected in parallel.
- The sample data contains no nulls and no empty Strings. For data where elements can be empty, `builder.length() == 0` cannot distinguish "no elements yet" from "one empty-string element was added"; therefore **this is an example for non-empty tokens**. If you need to support empty tokens, store an additional `count` or `hasElement` flag in the accumulator instead of relying on StringBuilder length.

**Important note:** A Collector using StringBuilder can be valid for parallel streams when each accumulation container is managed separately and the combiner merges them properly. That does not mean StringBuilder itself is **thread-safe** for sharing a single instance across multiple threads. Do not declare CONCURRENT for this collector.

In practice, for simple string joining, **Collectors.joining("|")** is already built in and is usually easier to use. A custom finisher is useful for understanding the mechanism and when the result R has a special contract that standard collectors cannot express conveniently.

## 7. Finisher Creating a Snapshot: Accumulated List to Immutable List

A common use case is allowing the accumulator to be mutated during collection, while preventing structural modification of the returned result.

~~~java
Collector<String, ArrayList<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

This is an **illustrative snippet** requiring imports for Collector, ArrayList, and List. A is ArrayList<String>; R is an **unmodifiable** List<String> created by `List.copyOf`.

With input **["A","B"]**, the result R is a List containing A and B, but `result.add("C")` will throw UnsupportedOperationException.

### 7.1. Distinguishing Three Options

- `Collectors.toCollection(ArrayList::new)`: returns a mutable ArrayList.
- `stream.toList()` (Java 16+): returns an unmodifiable List; there is no need to write a custom collector when you only need an output list.
- `collect(Collector.of(..., List::copyOf))`: expresses the **finisher intent** and can be combined with specialized accumulation logic if needed.

**Do not write a custom collector if a standard API satisfies the entire contract.** The goal of learning about finishers is not to encourage replacing every `toList()` with four custom functions.

### 7.2. Nulls Can Fail in the Finisher

`ArrayList` allows storing `null`, whereas **List.copyOf(collection)** does not accept null elements. Thus, a stream containing null may accumulate into A successfully and **only throw NullPointerException when the finisher runs**.

If nullability is valid, choose an appropriate result type R or filter/transform intentionally. If nullability is a data error, validate early with a clear message. Do not assume that because the accumulator accepts null, the finisher will accept it too.

### 7.3. Warning About Aliasing

A finisher that simply returns the mutable accumulator itself:

~~~java
acc -> acc
~~~

is an identity finish in terms of the object reference (when A/R are compatible), but **does not create a snapshot**. If a caller can hold onto A and mutate it, the intended immutability is broken.

Similarly:

~~~java
acc -> Collections.unmodifiableList(acc)
~~~

is a **view that disallows modification through the view**, yet still reflects changes if another reference to `acc` mutates the underlying list. If you want a clearly isolated snapshot, you can use `List.copyOf(acc)` (when there are no nulls) or `Collections.unmodifiableList(new ArrayList<>(acc))`. Choose based on ownership requirements and null policy.

## 8. When You Only Need an Additional Finisher: Collectors.collectingAndThen()

You do not always need to write a full custom Collector. **Collectors.collectingAndThen(downstream, finisher)** wraps an existing collector and applies a finisher to the downstream collector's result.

Example:

~~~java
List<String> result = Stream.of("B", "A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(TreeSet::new),
                List::copyOf));
~~~

This is an illustrative snippet with imports for List, TreeSet, Stream, and Collectors. The downstream collects into a **TreeSet<String>**, which deduplicates and sorts A and B. The finisher **List.copyOf** turns the TreeSet into an **unmodifiable List<String>** in the TreeSet's iteration order. The result is **[A, B]**.

**Design characteristics:**

- `collectingAndThen` reuses the downstream's supplier, accumulator, and combiner.
- The additional finisher produces a new result or performs a final check.
- It creates a new collector **without IDENTITY_FINISH**, because the extra finish step must not be skipped.
- It can be used as a downstream in `groupingBy`: each group is collected and then finished into the desired report or collection.
- You do not need to implement a combiner yourself if the downstream already handles the collection work properly.

### 8.1. Complete Java 17 Example: collectingAndThen

Create the file **CollectingAndThenDemo.java**:

~~~java
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectingAndThenDemo {
    public static void main(String[] args) {
        List<String> ordered = Stream.of(
                "pear", "apple", "pear", "banana")
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(TreeSet::new),
                        List::copyOf));

        System.out.println("Values: " + ordered);

        try {
            ordered.add("kiwi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot add");
        }

        List<String> empty = Stream.<String>empty()
                .collect(Collectors.collectingAndThen(
                        Collectors.toList(), List::copyOf));
        System.out.println("Empty: " + empty);
    }
}
~~~

Run:

~~~bash
javac CollectingAndThenDemo.java
java CollectingAndThenDemo
~~~

Stdout:

~~~text
Values: [apple, banana, pear]
Cannot add
Empty: []
~~~

**Explanation:**

1. `TreeSet` removes the duplicate "pear" and sorts according to String natural ordering.
2. `List.copyOf` creates a List that cannot have elements added or removed; calling add throws UnsupportedOperationException, which is caught solely to demonstrate the contract.
3. For an empty source, the downstream toList creates an empty List, and the copyOf finisher returns an unmodifiable empty List.
4. **Do not use collection modification tests in production** just to check mutability; in the example, the catch block is used to prove the API behavior.

**Why is this different from `stream.sorted().distinct().toList()`?** For a non-null Stream<String> requiring an unmodifiable output, the latter approach can be more concise. `collectingAndThen` is especially useful when you have a complex downstream collector that needs a common final finish step, rather than being mandatory for every type conversion.

## 9. Finisher and groupingBy(): Transforming Each Group's Accumulator

A collector can be placed as the **downstream** of `Collectors.groupingBy`. In that case, each group has its own accumulation container A; the downstream's finisher converts each A into R.

Example: suppose we want to compute the count and total score of employees by department, with R as a dedicated record.

Create the file **GroupedFinisherDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Employee(String department, int score) {}
record DepartmentStats(long count, long total, double average) {}

public class GroupedFinisherDemo {
    static final class StatsAcc {
        long count;
        long total;

        void add(Employee employee) {
            count++;
            total += employee.score();
        }

        StatsAcc merge(StatsAcc other) {
            count += other.count;
            total += other.total;
            return this;
        }

        DepartmentStats finish() {
            return new DepartmentStats(
                    count, total, count == 0 ? 0.0
                            : (double) total / count);
        }
    }

    static Collector<Employee, StatsAcc, DepartmentStats> collector() {
        return Collector.of(
                StatsAcc::new,
                StatsAcc::add,
                StatsAcc::merge,
                StatsAcc::finish);
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("IT", 10),
                new Employee("HR", 30),
                new Employee("IT", 20),
                new Employee("HR", 50),
                new Employee("Ops", 40)
        );

        Map<String, DepartmentStats> reports =
                employees.stream().collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        collector()));

        reports.forEach((department, stats) ->
                System.out.println(department
                        + ": count=" + stats.count()
                        + ", total=" + stats.total()
                        + ", average=" + stats.average()));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GroupedFinisherDemo.java
java GroupedFinisherDemo
~~~

Stdout:

~~~text
HR: count=2, total=80, average=40.0
IT: count=2, total=30, average=15.0
Ops: count=1, total=40, average=40.0
~~~

**Analysis:**

- groupingBy uses `Employee::department` to determine the key before passing the Employee to the downstream.
- Each group has its own StatsAcc: HR receives scores 30 and 50; IT receives 10 and 20; Ops receives 40.
- When processing each group, the downstream finisher converts StatsAcc into DepartmentStats.
- `TreeMap::new` determines the key iteration order HR, IT, Ops so stdout is deterministic.
- A group with no Employees will **not automatically appear** in the groupingBy result. An empty accumulator is only finished for groups that actually exist; to display a department with count=0 even when it has no Employees, you must supplement it with a canonical list of departments.
- This pattern differs from creating a `Map<String, List<Employee>>` and then iterating over each List again to compute statistics; the downstream custom Collector processes each group's elements immediately.

**Overflow consideration:** `StatsAcc` in the example uses `long total += score`. With very large datasets this could overflow `long`; the small example focuses on the finisher. When you need exact arithmetic and overflow detection, use `Math.addExact` or a domain-appropriate numeric type.

## 10. Finisher Can Validate the Final Result

A finisher does not have to only convert types. It can also **check final conditions** on the accumulator before producing the report, for example:

~~~java
Report finish() {
    if (count == 0) {
        throw new IllegalStateException("Cannot report empty data");
    }
    if (total < 0) {
        throw new IllegalStateException("Invalid total");
    }
    return new Report(count, total);
}
~~~

This is an illustrative snippet, assuming a `Report` type and `count`, `total` fields in the accumulator. This approach is valid in intent if **the invariant can only be evaluated after all data has been merged**.

However, distinguish carefully:

- **Per-record validation** (nulls, negative values, invalid IDs) should be done when reading/receiving data or in the accumulator according to the contract. Do not wait until the end if errors need to report the exact position.
- **Whole-set validation** (the total must meet a threshold, at least one element is required, sufficient count) can be placed in the finisher.
- If the finisher throws an exception, `collect(...)` fails and no valid R is returned.
- If the finisher has mandatory side effects (writing to a DB, sending email), clear transaction/error boundaries must be designed; **do not treat a collector as a platform that guarantees business side effects**.

**Principle:** A finisher should have simple, deterministic behavior and not interfere with the data source; ideally, it converts the accumulator into a **valid result**.

## 11. Identity Finish: Understanding It Accurately to Avoid Misdeclaration

The `IDENTITY_FINISH` characteristic is part of the `Collector` contract, not an arbitrary optimization trick.

If a collector accumulates directly into an `ArrayList<T>` and returns that same ArrayList, you can use the three-function overload:

~~~java
Collector<String, ArrayList<String>, ArrayList<String>> listCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

This is an illustrative snippet requiring imports for ArrayList and Collector. This type of collector has an identity finish; R is A itself.

If you add a finisher that turns `ArrayList<String>` into `List.copyOf(acc)`:

~~~java
Collector<String, ArrayList<String>, List<String>> snapshot =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

then you must not declare IDENTITY_FINISH because **R must be a snapshot** rather than returning A directly.

**Subtle bug:** If you only look at the static types `A` and `R` both implementing List and attach IDENTITY_FINISH, you can break the **immutable, sorted, validated** contract that the finisher actually provides.

### 11.1. Is It Allowed to Skip the Finisher?

When a collector **has IDENTITY_FINISH**, an implementation may skip the finisher because the accumulator itself is the result. When a collector **does not have this characteristic**, the finisher serves as a required transformation in the collection operation by contract. You should not write tests assuming the finisher is always called an exact number of times in every context (especially when the collector is used as a downstream of a composed collector); instead, verify the **final R** and its invariants.

## 12. UNORDERED and CONCURRENT Are Not Directly Tied to the Finisher

Other collector characteristics are also very easy to misuse:

### 12.1. UNORDERED

`UNORDERED` states that the result **does not depend on the encounter order** of elements. If the finisher builds a List preserving the original order or a string joined in order, **do not** declare UNORDERED.

In the `StringFinisherDemo` example, the result `a|b|c|d` differs from `d|c|b|a`, so you must not assert that order does not matter.

If you are only summing integers without order constraints and the combination operation is valid, the collector may have the unordered characteristic depending on design. However, with floating-point numbers or side effects, changing the order can affect the result; evaluate carefully.

### 12.2. CONCURRENT

`CONCURRENT` allows multiple threads to accumulate concurrently into **the same container** under the collector's contract in appropriate cases. To attach this characteristic, the accumulator must guarantee thread safety, and the combination/ordering semantics must be compatible.

A collector using `ArrayList`, `StringBuilder`, or `long` fields is typically **not concurrently safe** if the container is shared for updates; do not attach CONCURRENT just because the code is called from `parallelStream()`.

**Distinction:** A parallel stream can use multiple separate containers + a combiner; that does not mean the collector has the CONCURRENT characteristic.

### 12.3. Do Not Try to "Optimize" by Declaring Every Characteristic

Characteristics are **commitments made by the collector**. If you are unsure whether a collector satisfies a characteristic, omitting it is usually safer than declaring it falsely. Focus first on the core rules: the supplier returns a new container, the accumulator adds data correctly, the combiner produces results equivalent to sequential processing, and the finisher returns the exact R.

## 13. Avoid Side Effects in the Finisher

The finisher is a result transformation step, yet it can throw exceptions or cause side effects like any other Java function. You should not place actions here that the system needs to guarantee happen exactly once, such as:

~~~java
// Design anti-pattern: finisher both returns a result
// and sends a business notification.
acc -> {
    mailService.sendReport(acc); // External side effect.
    return acc.toReport();
}
~~~

This is an illustrative snippet requiring appropriate types and variables. Why is it risky?

- When using the collector as a downstream of another collector, how finish is invoked depends on the composed collector's structure; it should not be treated as an email-dispatching orchestrator.
- If the finisher fails after performing part of a side effect, the caller must handle transactions/retries, otherwise duplicate or missing notifications easily occur.
- Unit tests or exploratory collections could unintentionally trigger side effects.
- When an API promises that **R is a value**, adding mandatory I/O obscures responsibility boundaries.

Better:

~~~java
Report report = records.stream().collect(reportCollector());
mailService.sendReport(report);
~~~

This is an illustrative snippet. Sending the notification happens **after the result R has been created**, so the application can design retries, logging, idempotency, and error handling separately. This separation does not create a transaction by itself, but it places responsibilities where they belong.

## 14. Aliasing, Mutable Data, and Ownership Boundaries

Suppose a finisher returns a record containing a List built by the accumulator:

~~~java
record Report(List<String> ids) {}
~~~

Finisher:

~~~java
acc -> new Report(acc.ids)
~~~

This is an illustrative snippet. If another reference can still mutate `acc.ids`, Report's contents can change after being published. Even if the accumulator is private, you should clearly define ownership and whether any mutable container is exposed through the API.

One way to protect it:

~~~java
acc -> new Report(List.copyOf(acc.ids))
~~~

`List.copyOf` creates a structurally unmodifiable list, and with the example's immutable String elements, the report result is stable. If nulls must be allowed, `List.copyOf` is not suitable when elements can be null.

**Do not claim a finisher returns an immutable object just because R is a record.** A record does not prevent a mutable List from being held inside. Do not claim **Collections.unmodifiableList(acc.ids)** is a deep immutable snapshot: it is a view that cannot be modified through the view, yet it can still reflect changes to the underlying list.

**A good collector** does not expose a mutable accumulation container if the public API promises an immutable result. When a snapshot is needed, create a copy with the right depth and null policy.

## 15. Nulls and Exceptions at Each Stage

A custom collector can fail at multiple stages:

| Stage | Common Failure | How to Handle |
| --- | --- | --- |
| Supplier | Returning null or an invalid shared container | Return a new valid A |
| Accumulator | Dereferencing a null element, invalid conversion | Validate inputs and null contract |
| Combiner | Incorrect merge, missing elements, lost order, overflow | Design a proper merge operation and test in parallel |
| Finisher | Invariant violation, List.copyOf encountering null, division by 0 | Check/define empty state, handle errors clearly |
| After collect | Caller mutates R despite contract forbidding it | Publish the exact R type and mutability |

If A holds counts and sums, define an **overflow policy**. If computing an average, do not accidentally divide `0/0`; you can use `OptionalDouble` in R to represent a non-existent result for an empty set.

If A holds objects with mutable state, creating a snapshot at the end does not necessarily solve all thread-safety issues **during accumulation**. The accumulator and combiner must still obey the contract in a parallel stream.

## 16. Testing a Custom Collector With a Finisher

A useful test suite should cover:

1. **Empty source:** supplier creates a valid A; finisher returns R according to policy.
2. **Single element:** accurate result.
3. **Multiple elements:** correct count/sum/list.
4. **Sequential and parallel streams:** identical results per contract; for ordered results, verify encounter order.
5. **Combiner merging empty branches:** no extra delimiters added, no elements lost.
6. **Null input:** contract explicitly allows or rejects it.
7. **Overflow:** if the domain requires detection, use checked addition and test boundary values.
8. **Immutability of R:** caller cannot modify the collection if the API promises unmodifiable.
9. **Characteristics:** do not declare IDENTITY_FINISH when the finisher creates a new type or snapshot.
10. **Independence:** two collections from two new streams do not accidentally share an accumulator.

### 16.1. Testing Immutability After Finish

With the RevenueReport example:

~~~java
RevenueReport report = orders.stream()
        .collect(reportCollector());

// Contract: cannot structurally modify the ID list
// report.ids().add("X"); -> UnsupportedOperationException.
~~~

This is an illustrative snippet requiring the classes/methods from `FinisherReportDemo`. A unit test can use `assertThrows(UnsupportedOperationException.class, () -> report.ids().add("X"))` with JUnit properly declared. JUnit is not part of Java SE and requires a separate dependency, so this article does not use JUnit assertions as a standalone Java 17 example.

### 16.2. Compare Results, Do Not Guess Invocation Schedules

In a parallel stream, you should not assert that the Supplier is called exactly 4 times or the Combiner exactly 3 times. Execution schedules and work-splitting granularity can vary by JVM, data size, and configuration.

Verify the **final R**, such as totals and lists, against the sequential approach. If R differs, investigate the combination rules, ordering, and mutable state—do not rush to attach CONCURRENT to "fix" performance.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating finisher as a Consumer just for logging | Does not produce R, wrong role | Finisher has type Function<A,R> |
| Assuming combiner may return R | Type mismatch, no A left to combine | Combiner must return A |
| Attaching IDENTITY_FINISH when A is StringBuilder, R is String | Finisher may be skipped, causing type errors | Do not declare incorrect characteristics |
| Attaching IDENTITY_FINISH when finisher returns a snapshot | R may fail to achieve desired immutability | Mark contract accurately |
| Supplier returns a shared accumulator | Wrong results/races during collection, especially parallel | Create a new A on every invocation |
| Combiner fails to merge all count/sum/list fields | Data loss in parallel | Test full merge logic |
| Returning a mutable List inside a record and assuming it is immutable | Caller or alias can mutate contents | Copy appropriately into R |
| Using List.copyOf on a list containing null | NPE during finish | Define a null policy |
| Dividing by count=0 in finisher | Error or semantically wrong result | Handle empty explicitly |
| Using StringBuilder.length() to detect prior tokens when empty tokens are valid | Incorrect delimiters | Keep a dedicated flag/count |
| Attaching UNORDERED to an order-preserving String-joining collector | Allows changing encounter order unexpectedly | Do not declare UNORDERED |
| Attaching CONCURRENT just because parallelStream is used | Mutable accumulator is not thread-safe | Use parallel contract with separate containers + combiner |
| Putting mandatory I/O in finisher | Hard to retry/transact, unwanted side effects | Move side effects after collect |
| Using a custom collector for simple toList | Unnecessary complexity | Use standard collectors/APIs |
| Expecting empty groups to appear automatically in groupingBy | No key to create the group | Supplement with canonical keys when needed |
| Summing without overflow checks in sensitive domains | Silent wrong reports | Use appropriate numeric types or checked addition |

## 18. Finisher Design Checklist

Before creating `Collector<T,A,R>`, ask yourself:

1. **What is T?** The input element type.
2. **What is A?** A container suited for updating and merging.
3. **What is R?** The result the public API actually needs.
4. **Does R need to differ from A?** If not, a built-in collector or identity finish may suffice.
5. **What must the finisher produce?** A record, String, immutable Map, normalized list, or report with computed ratios?
6. **What should R be for empty input?** Zero values, Optional, or an exception?
7. **Does the supplier create a new A?** No shared mutable container.
8. **Does the accumulator handle null T and overflow properly?**
9. **Does the combiner return A properly, merge all state, and preserve order per contract?**
10. **Does R expose a mutable alias from A?** Choose the right snapshot.
11. **Did you accidentally declare IDENTITY_FINISH when the finisher is not identity?**
12. **Are UNORDERED or CONCURRENT genuinely needed?** Do not attach characteristics to "optimize" without guarantees.
13. **Should you use collectingAndThen instead of a full custom collector?**
14. **Have you tested sequential, parallel, empty, and error cases?**

## 19. Exercises

### Exercise 1: Identifying A and R

A collector uses `StringBuilder` to accumulate user names, but returns a finished `String`. Identify T, A, and R; write the signatures of supplier, accumulator, combiner, and finisher.

### Exercise 2: Fixing a Combiner Missing Fields

A `StatsAcc` has `count`, `sum`, and `ids`, but the combiner only adds `sum`. Explain why the result might be right on a sequential Stream yet wrong on a parallel stream. Write a merge that handles all three fields correctly.

### Exercise 3: Protecting a Snapshot

A collector gathers Strings into an ArrayList. Write a finisher that returns an unmodifiable list using `List.copyOf`. Compare this with `Collections.unmodifiableList(acc)` in the case where the underlying list is still mutated via an alias.

### Exercise 4: IDENTITY_FINISH

Does the following snippet have a valid contract?

~~~java
Collector.of(
        StringBuilder::new,
        StringBuilder::append,
        (a,b) -> a.append(b),
        StringBuilder::toString,
        Collector.Characteristics.IDENTITY_FINISH);
~~~

This is an intentionally wrong anti-pattern. Explain why A = StringBuilder and R = String do not allow skipping the finisher.

### Exercise 5: Grouped Report

Given a List<Employee> with department and score. Write a downstream collector using StatsAcc and finishing into DepartmentStats(count,total,average). Place that collector into `groupingBy(Employee::department, TreeMap::new, collector)`. Calculate the expected output for two departments and one department with no employees.

### Exercise 6: Empty Input

If a collector computes an average when count is 0, design two policies:
- Return a record with `OptionalDouble.empty()`.
- Throw `IllegalStateException` if the domain requires at least one record.

Which policy is right when "no data" is a normal state?

### Exercise 7: Comparing collectingAndThen

Collect the words `["b","a","b"]` into a TreeSet and convert to an unmodifiable List using `collectingAndThen(toCollection(TreeSet::new), List::copyOf)`. Why don't you need to rewrite supplier/accumulator/combiner?

### Exercise 8: Ensuring Parallel Behavior

Write a custom collector that joins non-empty tokens with `|`. Run it on a List source with encounter order using `stream()` and `parallelStream()`. Check the final result instead of counting how many times supplier/combiner are called.

## 20. Takeaways

**A finisher is the `A → R` transformation of a Collector**: after T elements have been gathered and A containers have been combined as required, the finisher turns the accumulation container into the result value. It can produce a report record, a String from a StringBuilder, an unmodifiable snapshot, or a validated state.

For a custom collector to be correct, **supplier must create a new A**, **accumulator updates A**, **combiner merges A with A and returns A**, and **finisher returns R**. If R differs from A or the finisher creates a real snapshot, **do not mark IDENTITY_FINISH**.

Prefer **Collectors.collectingAndThen** when a suitable downstream collector already exists and you only need an extra final transformation step. When the business logic requires a specialized A and R has its own contract, use **Collector.of(supplier, accumulator, combiner, finisher)** along with tests for empty input, ordered sources, and parallel execution.

The design-deciding question: **"What do I need to hold during accumulation, and what type and immutability do I want to publish as the final result?"** That is precisely why the finisher exists in a Java Collector.