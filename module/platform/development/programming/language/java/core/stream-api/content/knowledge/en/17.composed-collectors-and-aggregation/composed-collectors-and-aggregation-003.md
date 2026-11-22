# Finding Per-Group Extrema with minBy and maxBy

When processing grouped data, the question is often not just “how many elements are in each group?” but also **“which record is the smallest/largest in each group?”**. For example: the highest-paid employee per department, the highest-value order per customer, the cheapest product per category, or the earliest transaction per account.

In the **JAVA_STREAM_API** module, this lesson belongs to the **Composed Collectors and Aggregation** chapter. We build declarative pipelines with `filter`, `map`, `collect`, and then use a **downstream collector** inside `Collectors.groupingBy`. The focus is `Collectors.minBy(comparator)` and `Collectors.maxBy(comparator)`: two collectors that find **the extremum element of each group** without creating a `List` of every element in each group.

Key points to master: how to construct a `Comparator`, handling `Optional`, tie cases, the difference between filtering before and after grouping, the impact of `parallelStream()`, and when to use `summarizingInt` or `toMap` instead.

## 1. From stream-wide extremum to per-group extremum

For a single Stream, we have terminal operations:

```java
Optional<Integer> smallest = Stream.of(8, 3, 9, 3)
    .min(Integer::compare);

Optional<Integer> largest = Stream.of(8, 3, 9, 3)
    .max(Integer::compare);

System.out.println(smallest.orElse(-1)); // 3
System.out.println(largest.orElse(-1));  // 9
```

However, for the requirement “**each department** has one highest-paid employee”, `stream.max(...)` only returns **one person across the entire Stream**, not one result per department.

We need two processing layers:

1. **Classify by group key** using `groupingBy(keyMapper, downstream)`.
2. **Find the extremum separately within each group** using `minBy(comparator)` or `maxBy(comparator)`.

Visualization:

```text
Stream<Employee>
       |
       v
groupingBy(Employee::getDepartment, downstream)
       |
       +-- Engineering --> maxBy(bySalary) --> Optional<Employee>
       |
       +-- Sales       --> maxBy(bySalary) --> Optional<Employee>
       |
       +-- Support     --> maxBy(bySalary) --> Optional<Employee>
       |
       v
Map<String, Optional<Employee>>
```

A `Map` is the result of `groupingBy`, while `Optional<Employee>` is the downstream result of each group. `collect(...)` at the end is the **terminal operation** triggering the lazy pipeline.

## 2. Signatures and meaning of the Collectors

Conceptually, the two methods have the form:

```java
Collector<T, ?, Optional<T>> minBy(Comparator<? super T> comparator);
Collector<T, ?, Optional<T>> maxBy(Comparator<? super T> comparator);
```

Placed inside `groupingBy`:

```java
Map<K, Optional<T>> minPerGroup = stream.collect(
    Collectors.groupingBy(
        item -> keyOf(item),
        Collectors.minBy(comparator)
    )
);

Map<K, Optional<T>> maxPerGroup = stream.collect(
    Collectors.groupingBy(
        item -> keyOf(item),
        Collectors.maxBy(comparator)
    )
);
```

Here `K` is the group key type and `T` is the Stream element type. `Comparator<? super T>` decides what counts as **smallest** or **largest** according to a given rule. `Collectors.minBy/maxBy` are **collectors**, not terminal operations; they only execute when passed into `collect` (or wrapped by another collector).

| Component | Role | Example |
| --- | --- | --- |
| `groupingBy(Employee::getDepartment, ...)` | Determines the key of each group | `"Engineering"`, `"Sales"` |
| `Collectors.minBy(bySalary)` | Picks the smallest element by comparator in each group | Lowest-paid person |
| `Collectors.maxBy(bySalary)` | Picks the largest element by comparator in each group | Highest-paid person |
| `Optional<Employee>` | Represents one person or no person | `Optional.empty()` when the downstream receives no elements |

Crucial point: `maxBy` on `Employee` **returns `Optional<Employee>`**, not the salary number itself. If you only need the highest salary number, see the **mapping** and **summarizingInt** sections later.

## 3. Complete Java 8 example: extremum employee per department

The example below compiles with Java 8. So that the result **does not depend on order when two people have the same salary**, the comparator compares salary first and then uses the unique employee ID as a tie-breaker.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class ExtremumByGroupDemo {
    static final class Employee {
        private final String id;
        private final String department;
        private final String level;
        private final int salary;

        Employee(String id, String department, String level, int salary) {
            this.id = id;
            this.department = department;
            this.level = level;
            this.salary = salary;
        }

        String getId() {
            return id;
        }

        String getDepartment() {
            return department;
        }

        String getLevel() {
            return level;
        }

        int getSalary() {
            return salary;
        }
    }

    public static void main(String[] args) {
        List<Employee> staff = Arrays.asList(
            new Employee("E01", "Engineering", "Senior", 4200),
            new Employee("E02", "Engineering", "Senior", 5000),
            new Employee("E03", "Engineering", "Mid",    5000),
            new Employee("S01", "Sales",       "Mid",    3200),
            new Employee("S02", "Sales",       "Junior", 2800),
            new Employee("P01", "Support",     "Junior", 3000)
        );

        Comparator<Employee> bySalaryThenId =
            Comparator.comparingInt(Employee::getSalary)
                      .thenComparing(Employee::getId);

        Map<String, Optional<Employee>> highestByDepartment = staff.stream()
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                Collectors.maxBy(bySalaryThenId)
            ));

        Map<String, Optional<Employee>> lowestByDepartment = staff.stream()
            .collect(Collectors.groupingBy(
                Employee::getDepartment,
                Collectors.minBy(bySalaryThenId)
            ));

        System.out.println(
            highestByDepartment.get("Engineering")
                .map(Employee::getId).orElse("none")
        ); // E03

        System.out.println(
            lowestByDepartment.get("Sales")
                .map(Employee::getId).orElse("none")
        ); // S02

        System.out.println(
            highestByDepartment.get("Support")
                .map(Employee::getSalary).orElse(-1)
        ); // 3000
    }
}
```

Result explanation:

1. The Engineering group has three people. `E02` and `E03` both have salary `5000`, which is higher than `E01`. With `thenComparing(Employee::getId)`, `E03` is chosen because `"E03"` is greater than `"E02"` in string order.
2. The Sales group has salaries `3200` and `2800`, so `minBy` selects `S02`.
3. The Support group has only `P01`, so both `minBy` and `maxBy` select `P01`.

**Do not depend on Map key iteration order:** default `groupingBy` does not guarantee a specific Map class or key iteration order. In this example we look up keys via `get(...)`, so there is no issue.

Collecting extrema **does not create a separate List of employees per department**. Each group's collector only needs to hold the extremum candidate, rather than every element that passed through.

## 4. Which criterion does Comparator use to decide the extremum?

`minBy` and `maxBy` **do not know by themselves** which field is “smaller” or “larger”. They rely on the result from `Comparator`:

```java
Comparator<Employee> bySalary =
    Comparator.comparingInt(Employee::getSalary);

Comparator<Employee> byId =
    Comparator.comparing(Employee::getId);

Comparator<Employee> bySalaryThenId =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);
```

Comparator contract:

- **Negative** number: the first argument is less than the second argument.
- **`0`**: both objects are considered equal **by the comparator's criterion**.
- **Positive** number: the first argument is greater than the second argument.

Therefore, `maxBy(bySalary)` picks the highest-paid person; `minBy(bySalary)` picks the lowest-paid person. Meanwhile `maxBy(byId)` picks the person with the largest ID—a completely different problem.

### Tie cases: define a policy deliberately

If only `bySalary` is used, `E02` and `E03` are evaluated as equal by the comparator since both earn `5000`. In that case, the result can be **any one of the tied extremum candidates**. Do not build business logic assuming the first-encountered element will always win, especially when source order changes or when running in parallel.

A comparator with a tie-breaker:

```java
Comparator<Employee> bySalaryThenId =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);
```

helps select a deterministic extremum **if IDs are unique within each group**. If you want to prefer the **smallest ID when salaries are tied** while still using `maxBy` to select the highest salary, reverse only the ID criterion:

```java
Comparator<Employee> salaryThenSmallestId =
    Comparator.comparingInt(Employee::getSalary)
        .thenComparing(
            Employee::getId,
            Comparator.reverseOrder()
        );
```

A higher salary wins; if salaries are equal, a smaller ID is considered **greater under the composite comparator**, and is therefore chosen by `maxBy`. Name comparators according to the **business priority rule**, not merely the fields they read.

### Do not accidentally invert minBy and maxBy

`Comparator.reverseOrder()` or `comparator.reversed()` flips smaller/larger semantics:

```java
Comparator<Employee> bySalary =
    Comparator.comparingInt(Employee::getSalary);

// Both of these select the highest-paid person:
Collectors.maxBy(bySalary);
Collectors.minBy(bySalary.reversed());
```

Writing `maxBy(bySalary)` is usually more direct for the question “who has the highest salary?”. Do not accidentally reverse the comparator and keep using `maxBy`, as you would end up selecting the **lowest salary**.

## 5. Why is the result an Optional?

`Collectors.minBy/maxBy` use `Optional<T>` because an aggregation might **receive zero elements**. On an empty Stream:

```java
Optional<Integer> minimum = Stream.<Integer>empty()
    .collect(Collectors.minBy(Integer::compare));

System.out.println(minimum.isPresent()); // false
```

However, in `groupingBy(keyMapper, Collectors.maxBy(...))` **without downstream filtering**, each key is created from **at least one source element**. Therefore, every group that actually appears in the Map has an `Optional` containing one element (assuming valid data and comparator). Keys absent from the source **are not created automatically**.

Example:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));

Optional<Employee> sales = top.get("Sales"); // Has a value.
Optional<Employee> absent = top.get("Legal"); // null because the Map has no such key.
```

Here, `top.get("Legal")` returns **`null`**, not `Optional.empty()`. Do not call `top.get("Legal").orElse(...)`, as it will throw a `NullPointerException`. Safe usage for a key that might not exist:

```java
Employee legalTop = top.getOrDefault(
    "Legal", Optional.empty()
).orElse(null);
// legalTop == null
```

If you want to reject keys without results, check `containsKey` or use `Optional` with an appropriate `orElseThrow`. Do not call `Optional.get()` without checking.

### Groups that have a key but an Optional.empty() result

Since Java 9, `Collectors.filtering(predicate, downstream)` allows **filtering inside each group**. When a key already exists but **no element passes the downstream filter**, `maxBy` produces `Optional.empty()` for that key:

```java
// Java 9+
Map<String, Optional<Employee>> highEarners = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.filtering(
            employee -> employee.getSalary() >= 6000,
            Collectors.maxBy(bySalaryThenId)
        )
    ));

System.out.println(highEarners.containsKey("Sales")); // true
System.out.println(highEarners.get("Sales").isPresent()); // false
```

Conversely, `stream.filter(predicate).collect(groupingBy(...))` filters **before creating groups**: departments with no matching elements will **have no key in the Map**. The two filtering approaches carry different meanings.

## 6. Unwrapping Optional when you need Map<K, T>

When business rules guarantee that every created key definitely has at least one element, you can use `Collectors.collectingAndThen` to transform the downstream result:

```java
Map<String, Employee> topByDepartment = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.collectingAndThen(
            Collectors.maxBy(bySalaryThenId),
            opt -> opt.orElseThrow(IllegalStateException::new)
        )
    ));

System.out.println(
    topByDepartment.get("Engineering").getId()
); // E03
```

This call has two downstream layers:

1. `maxBy` aggregates within the group, producing `Optional<Employee>`.
2. `collectingAndThen` invokes the **finisher** to turn `Optional<Employee>` into `Employee`.

With standard `groupingBy`, groups are created from actual elements and thus have at least one element. If `Collectors.filtering(...)` is later added in the downstream (Java 9+), a group can become empty under the filter and `orElseThrow` will throw an exception. Therefore, unwrap `Optional` only when **non-emptiness is guaranteed by design**.

Do not overuse `orElse(null)` just for “easy access”; `null` blurs the distinction between **a nonexistent key** and **an existing key with no valid candidate**.

## 7. Need only the extremum value, not the whole object?

If you only care about the **highest salary per department**, `Map<String, Optional<Employee>>` may carry more information than needed. We can use `Collectors.mapping` before `maxBy`:

```java
Map<String, Optional<Integer>> highestSalaryByDepartment =
    staff.stream().collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.mapping(
            Employee::getSalary,
            Collectors.maxBy(Integer::compare)
        )
    ));

System.out.println(
    highestSalaryByDepartment.get("Engineering").orElse(-1)
); // 5000
```

`mapping` transforms each `Employee` in the group into an `Integer`, and then `maxBy` finds the largest integer value. Structure:

```text
groupingBy(department,
    mapping(salary,
        maxBy(integer comparison)
    )
)
```

This is a true **composed collector**: `groupingBy` takes a `mapping` downstream, and `mapping` in turn takes `maxBy`.

### Want min, max, count, and average as well?

If you only need **salary numeric statistics** without keeping a candidate employee, `Collectors.summarizingInt` can compute multiple statistics in **one pass**:

```java
Map<String, IntSummaryStatistics> stats = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.summarizingInt(Employee::getSalary)
    ));

IntSummaryStatistics engineering = stats.get("Engineering");
System.out.println(engineering.getCount());   // 3
System.out.println(engineering.getMin());     // 4200
System.out.println(engineering.getMax());     // 5000
System.out.println(engineering.getSum());     // 14200
System.out.println(engineering.getAverage()); // 4733.333...
```

`summarizingInt` does not identify which employee has the highest salary; it only aggregates **numeric values**. Also, with `int` and large data, watch numeric ranges and overflow when summing. Choose the Collector based on the **required return type**, not merely on the method name.

| Question | Recommended collection | Value type per key |
| --- | --- | --- |
| Highest-paid employee? | `maxBy(bySalaryThenId)` | `Optional<Employee>` |
| Lowest-paid employee? | `minBy(bySalaryThenId)` | `Optional<Employee>` |
| Highest salary number? | `mapping(getSalary, maxBy(Integer::compare))` | `Optional<Integer>` |
| Min, max, count, sum, average? | `summarizingInt(getSalary)` | `IntSummaryStatistics` |
| All employees per department? | `groupingBy(getDepartment)` (default downstream `toList`) | `List<Employee>` |

## 8. Multi-level grouping before finding extrema

A business may need to find the highest-paid person **in each level of each department**. In that case, nest `groupingBy`:

```java
Map<String, Map<String, Optional<Employee>>> topByDepartmentAndLevel =
    staff.stream().collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.groupingBy(
            Employee::getLevel,
            Collectors.maxBy(bySalaryThenId)
        )
    ));

Employee topSeniorEngineer = topByDepartmentAndLevel
    .get("Engineering")
    .get("Senior")
    .orElseThrow(IllegalStateException::new);

System.out.println(topSeniorEngineer.getId()); // E02
```

Type breakdown:

- `groupingBy(Employee::getDepartment, ...)` creates the level-one `String` key.
- `groupingBy(Employee::getLevel, ...)` creates the level-two `String` key inside each department.
- `maxBy(bySalaryThenId)` selects the extremum `Employee` for each **(department, level)** pair.
- The result type is `Map<String, Map<String, Optional<Employee>>>`.

Groups without data do not appear automatically. When accessing a **nonexistent** department or level, `Map.get(...)` can return `null` before reaching `Optional`. In real applications, check each key's existence or create a safe lookup helper.

If group keys need to be sorted alphabetically, use the three-parameter overload of `groupingBy` with `TreeMap::new`:

```java
Map<String, Optional<Employee>> sortedDepartments = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        TreeMap::new,
        Collectors.maxBy(bySalaryThenId)
    ));
```

The Map supplier determines how **group keys** are stored/presented; it does not change the salary comparison criterion for finding the extremum person.

## 9. Difference from groupingBy(toList) followed by finding max

A natural alternative to think of is **collecting all employees into a List per group**, then iterating over each List to find the extremum:

```java
Map<String, List<Employee>> grouped = staff.stream()
    .collect(Collectors.groupingBy(Employee::getDepartment));

Map<String, Optional<Employee>> top = new HashMap<>();
for (Map.Entry<String, List<Employee>> entry : grouped.entrySet()) {
    top.put(
        entry.getKey(),
        entry.getValue().stream().max(bySalaryThenId)
    );
}
```

This approach can be functionally correct, but it must **retain all elements in intermediate Lists** and then perform a second traversal for each group. If you only need one extremum person per group, write directly:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));
```

The direct approach is usually better in terms of intent, memory, and number of passes:

| Approach | Traversal cost | Intermediate data |
| --- | --- | --- |
| `groupingBy(toList)` then `list.stream().max(...)` | Groups elements, then re-traverses each group's members | Stores all elements in Lists |
| `groupingBy(maxBy(comparator))` | Accumulates extremum candidate during traversal | Mainly one candidate per group plus Map structure |

The total number of comparisons to find the extremum generally scales linearly with the number of elements. `maxBy` does not require sorting the entire group; **sorting just to take the last element** usually does more work when only the maximum value is needed.

## 10. Comparison with toMap using a merge function

The same highest-salary-per-department problem can be expressed with `Collectors.toMap`:

```java
Map<String, Employee> top = staff.stream()
    .collect(Collectors.toMap(
        Employee::getDepartment,
        employee -> employee,
        BinaryOperator.maxBy(bySalaryThenId)
    ));
```

Here, each `Employee` contributes a `department → employee` pair; when keys collide, `BinaryOperator.maxBy` merges the two candidates.

Differences:

| Style | Result type | Key characteristic |
| --- | --- | --- |
| `groupingBy(key, Collectors.maxBy(cmp))` | `Map<K, Optional<T>>` | Clearly expresses “aggregate within each group”; convenient for composing further downstreams |
| `toMap(key, identityValue, BinaryOperator.maxBy(cmp))` | `Map<K, T>` | Gets the record directly, without an `Optional` wrapper when the key exists |
| `groupingBy(key, collectingAndThen(maxBy(cmp), ...))` | `Map<K, T>` | Still follows the downstream model, transforming the result at the end of each group |

Do not confuse `Collectors.maxBy(cmp)` with `BinaryOperator.maxBy(cmp)`:

- `Collectors.maxBy` returns **`Collector<T, ?, Optional<T>>`**, used inside `collect` and `groupingBy`.
- `BinaryOperator.maxBy` returns **`BinaryOperator<T>`**, used as a merge function for key collisions in `toMap` or as a reduction operator where appropriate.

Both use a comparator, yet they **are not directly interchangeable** because their types and roles in the API differ.

## 11. Data and performance boundaries

### 11.1. Null data and null keys

With `groupingBy`, the key returned by the classifier **must not be null**. If `Employee::getDepartment` can return null, validate, filter, or map to a meaningful fallback key such as `"UNASSIGNED"`:

```java
Map<String, Optional<Employee>> top = staff.stream()
    .filter(Objects::nonNull)
    .collect(Collectors.groupingBy(
        employee -> employee.getDepartment() == null
            ? "UNASSIGNED" : employee.getDepartment(),
        Collectors.maxBy(bySalaryThenId)
    ));
```

`minBy/maxBy` apply the comparator to group elements. The example comparator reads `getSalary()`, `getId()`, and is not designed for `null` elements. Therefore, if the source may contain null, filter with `Objects::nonNull` or define an explicit null-comparison policy before collecting.

### 11.2. Fields used for comparison should not mutate

Do not modify `salary` or `id` of objects while the pipeline is running; `groupingBy` and `maxBy` must operate **without interfering with the source** and **without depending on mutating external state**. In the example, `Employee` is immutable with respect to the used fields, making the result easy to reason about.

If salary is stored as `double`, account for `NaN`, infinity, and `-0.0`. Use `Comparator.comparingDouble(...)` and define a policy for non-finite values before choosing extrema. For currency, `BigDecimal` or integers representing the smallest unit are usually more appropriate when decimal precision is required.

### 11.3. Parallel execution does not guarantee faster performance

`groupingBy` can run in a parallel stream:

```java
Map<String, Optional<Employee>> parallelTop = staff.parallelStream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(bySalaryThenId)
    ));
```

The library can create partial Maps, compute extremum candidates in each partition, and then **merge** the results. The comparator should be pure and consistent; selecting an extremum under a consistent comparison order allows combining candidates cleanly. When there is a **tie** that the comparator cannot break, different sources or merge trees can cause different candidates to be picked; use a tie-breaker key if business rules require a deterministic result.

`Collectors.groupingBy` is not a **concurrent collector**. When executed in parallel, merging partial Maps can be expensive; group count, element distribution, source splittability (`Spliterator`), and comparator cost all affect performance. `Collectors.groupingByConcurrent` exists for other needs, but it has unordered/concurrent characteristics; do not substitute it mechanically when output order or encounter-order tie-breaking is required.

For practical optimization, benchmark with representative data. For small lists, sequential `stream()` is simpler and often faster than `parallelStream()`.

### 11.4. Infinite sources and memory cost

`groupingBy(..., maxBy(...))` typically keeps only one candidate per group instead of the whole group, yet `collect` still needs to **consume the Stream to completion** before returning the finished Map. On an unbounded infinite Stream, the terminal operation may never terminate.

The solution depends on the problem:

```java
Map<Integer, Optional<Integer>> topByRemainder =
    IntStream.iterate(1, n -> n + 1)
        .limit(100)
        .boxed()
        .collect(Collectors.groupingBy(
            n -> n % 3,
            Collectors.maxBy(Integer::compare)
        ));
```

Here, `limit(100)` makes the output source finite; the extremum is found **within the first 100 numbers**, not across an infinite sequence in general. `limit` is not a substitute for a timeout and cannot rescue a pipeline when an earlier stage never emits enough elements.

## 12. Common pitfalls

| Pitfall | Consequence | How to fix |
| --- | --- | --- |
| Using `stream.max(...)` to get per-group extrema | Returns only one element for the whole Stream | `groupingBy(key, Collectors.maxBy(...))` |
| Thinking `maxBy` gets highest salary and returns `Integer` | Actual type is `Optional<Employee>` when input is `Employee` | Use `mapping(getSalary, maxBy(...))` when only the number is needed |
| Calling `map.get("Legal").orElse(...)` when group has no key | `Map.get` returns `null`, causing `NullPointerException` | Check key or `getOrDefault("Legal", Optional.empty())` |
| Assuming every `Optional` in a group is always present even with downstream filtering | `Collectors.filtering` can leave a group with `Optional.empty()` | Handle the empty case before calling `get()` |
| Comparing only salary when multiple people tie and a deterministic result is needed | Selected candidate may not follow policy | Add a unique tie-breaker criterion |
| Using `sorted().findFirst()` inside each group just to get an extremum | Can do more work than necessary | Use `minBy/maxBy` with an appropriate comparator |
| Collecting the entire group into a List and then scanning for max | Increases memory and traversal passes | Collect directly with downstream `maxBy` |
| Treating default Map order as source order | Report may output unstable key order | Use `TreeMap` or sort when presenting |
| Equating `Collectors.maxBy` with `BinaryOperator.maxBy` | Wrong type or wrong API position | Distinguish Collector and BinaryOperator |
| Assuming `parallelStream()` is always faster | Can incur splitting and merging overhead | Benchmark; prefer pure comparators |

## 13. Self-check exercises with answers

### Exercise 1 — Who has the highest salary in each group?

Using the employee data from the full example, write a pipeline to get the **highest-paid person by department**, breaking salary ties by ID.

```java
Comparator<Employee> cmp =
    Comparator.comparingInt(Employee::getSalary)
              .thenComparing(Employee::getId);

Map<String, Optional<Employee>> winners = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.maxBy(cmp)
    ));
```

**Answer:** Engineering → `E03`, Sales → `S01`, Support → `P01`. On tied salaries, the larger ID wins according to the declared comparator.

### Exercise 2 — Querying a nonexistent group

Is the expression `winners.get("Legal").orElse(null)` safe?

**Answer:** No. Because the Legal group is not in the source, `Map.get("Legal")` returns `null`; calling `orElse` on null throws `NullPointerException`. You can use:

```java
Employee legal = winners.getOrDefault(
    "Legal", Optional.empty()
).orElse(null);
```

### Exercise 3 — Need only the highest salary number

Collect a `Map<String, Optional<Integer>>` containing the highest salary in each department:

```java
Map<String, Optional<Integer>> maximumSalary = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.mapping(
            Employee::getSalary,
            Collectors.maxBy(Integer::compare)
        )
    ));
```

**Answer:** Engineering → `5000`, Sales → `3200`, Support → `3000`. `mapping` converts `Employee` into `Integer` before collecting the extremum.

### Exercise 4 — Two-level grouping

To find the lowest-paid person **for each level within each department**, what collector structure is needed?

```java
Map<String, Map<String, Optional<Employee>>> result = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.groupingBy(
            Employee::getLevel,
            Collectors.minBy(bySalaryThenId)
        )
    ));
```

**Answer:** Nest two `groupingBy` collectors, placing `minBy` as the innermost downstream. The result has two-level keys: department then level.

### Exercise 5 — Group that may become empty after filtering

In Java 9+, if you use `groupingBy(department, filtering(salary >= 6000, maxBy(...)))` on the example source, what is the result for the Sales group?

**Answer:** The Map still contains the `"Sales"` key, but its value is `Optional.empty()`, because Sales employees caused the group to exist before downstream filtering excluded all of them. If you filter **before** `groupingBy`, the Sales key will not appear.

### Exercise 6 — When to use summarizingInt?

A requirement asks to output **employee count, minimum, maximum, and average salary** for each department. Should you call `minBy` and `maxBy` and then compute the remaining numbers?

**Answer:** If **you do not need to know the specific employees**, `Collectors.summarizingInt(Employee::getSalary)` inside `groupingBy` expresses everything cleanly and can aggregate in a single pass:

```java
Map<String, IntSummaryStatistics> stats = staff.stream()
    .collect(Collectors.groupingBy(
        Employee::getDepartment,
        Collectors.summarizingInt(Employee::getSalary)
    ));
```

Only when you also need the **representative employee object** do `minBy/maxBy` directly satisfy the requirement.

## Key takeaway

To find **per-group** extrema in **JAVA_STREAM_API**, use `Collectors.groupingBy(classifier, Collectors.minBy(comparator))` or `maxBy(comparator)`. Each key maps to an `Optional<T>` holding the extremum element, not a List of all members. The `Comparator` determines which value wins; add a **tie-breaker criterion** when deterministic results are needed. You can combine `mapping` to find the extremum of a single field, `collectingAndThen` to transform `Optional` into another type, or nest `groupingBy` for multi-level aggregation. Distinguish **a missing key** from **an empty Optional**, handle null data appropriately, and avoid relying on parallel processing order. If you only need numeric statistics, `summarizingInt` may make more sense than finding individual extremum objects.
