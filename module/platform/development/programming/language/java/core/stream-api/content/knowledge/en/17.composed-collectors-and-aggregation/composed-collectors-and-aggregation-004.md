# Transforming Collector Input with mapping

In the **Composed Collectors and Aggregation** chapter of **Java Stream API**, an aggregation often does not simply return a list of original objects. For instance, from a list of employees, an application might want to group by department and **collect only employee names**, or group orders by customer and **sum only line amounts**. In such cases, we need to retain the information required for grouping while transforming each element before passing it into each group's collection operation.

`Collectors.mapping(mapper, downstream)` solves this need. It is a **collector adapter** (*downstream collector adapter*): it accepts elements of type `T`, applies `mapper` to turn each into `U`, and passes the `U` values to another collector. This collector composition is especially useful with `groupingBy`, `partitioningBy`, and multi-level statistics/aggregations.

This lesson explains the types, collector composition, runnable examples, the difference from `Stream.map`, how it works together with `filtering` and `flatMapping`, as well as issues regarding `null`, ordering, performance, and parallel processing.

## 1. Problem: grouping by original data while collecting transformed data

Suppose an employee has an ID, name, department, active status, and a list of skills:

~~~java
record Employee(
        String id,
        String name,
        String department,
        boolean active,
        List<String> skills
) {}
~~~

The goal is a result like:

~~~text
DEV -> [Lan, An, Huy]
QA  -> [Minh, Hạnh]
OPS -> [Bình]
~~~

We need to keep `department` to form keys, yet only want `name` in the resulting lists. Working with `Collectors.groupingBy`, the direct way to express this is:

~~~java
Map<String, List<String>> namesByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
~~~

Reading from outside in:

1. `employees.stream()` emits `Employee` elements.
2. `groupingBy(Employee::department, ...)` determines the group key from the **original Employee object**.
3. Within each group, `mapping(Employee::name, ...)` turns `Employee` into `String`.
4. `Collectors.toList()` receives those name strings and gathers them into the group's list.
5. `collect(...)` is the terminal operation, triggering the entire pipeline and returning `Map<String, List<String>>`.

Here, **the grouping step sees `Employee`, while the inner collector receives `String`**. That is the practical value of `mapping` in composed collectors.

## 2. Signature and contract of Collectors.mapping

The generic signature (available since Java 8) is:

~~~java
public static <T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream)
~~~

Notation:

| Symbol | Meaning | Example |
| --- | --- | --- |
| `T` | Input element type passed down by the outer composed collector | `Employee` |
| `U` | Type after applying the mapper | `String` |
| `A` | Internal accumulation container type of the downstream collector | Determined by the collector |
| `R` | Final result type of the downstream collector | `List<String>` |
| `mapper` | Function `T -> U`, applied to each element | `Employee::name` |
| `downstream` | Collector processing values of type `U` | `Collectors.toList()` |

`mapping` **is not a terminal operation**. It constructs a `Collector` object to pass to `collect(...)` or nest inside another collector. Only when the pipeline runs a terminal operation is data transformed and accumulated.

One way to visualize it:

~~~text
                Employee
                   |
          groupingBy(department)
                   |
            Within each group
                   |
          mapping(Employee::name)
                   |
                 String
                   |
          downstream: toList()
                   |
              List<String>
                   |
     Map<Department, List<String>>
~~~

Thanks to generics, `mapping` can convert to any type suited to the downstream collector: `Integer` to sum name lengths, `BigDecimal` to aggregate money, a DTO record to export reports, or an identifier key to collect a set of distinct values.

## 3. Complete runnable example on Java 17+

The following example uses `record` and `List.of`. `record` requires Java 16+, `List.of` requires Java 9+, while `Collectors.mapping` has been available since Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class MappingCollectorDemo {

    record Employee(
            String id,
            String name,
            String department,
            boolean active,
            List<String> skills
    ) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("E1", "Lan", "DEV", true,
                        List.of("Java", "SQL")),
                new Employee("E2", "Minh", "QA", true,
                        List.of("Testing", "Java")),
                new Employee("E3", "An", "DEV", false,
                        List.of("Spring")),
                new Employee("E4", "Huy", "DEV", true,
                        List.of("Docker", "Java")),
                new Employee("E5", "Hạnh", "QA", false,
                        List.of("SQL")),
                new Employee("E6", "Bình", "OPS", false,
                        List.of("Linux"))
        );

        // Each department receives only a list of names.
        Map<String, List<String>> namesByDepartment = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        System.out.println(namesByDepartment.get("DEV"));
        // [Lan, An, Huy]
        System.out.println(namesByDepartment.get("QA"));
        // [Minh, Hạnh]
        System.out.println(namesByDepartment.get("OPS"));
        // [Bình]

        // Each department receives a set of distinct names.
        Map<String, Set<String>> uniqueNames = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toSet()
                        )
                ));

        System.out.println(uniqueNames.get("DEV").contains("Lan"));
        // true
    }
}
~~~

To inspect each group's data, access it by key such as `get("DEV")`. Do not rely on the **key iteration order** of the `Map` created by default `groupingBy`; the API does not guarantee a specific Map class or key order.

In the example, the `List` source has encounter order and `toList` preserves the order in which elements enter each group, so `DEV` receives `[Lan, An, Huy]`. Conversely, `toSet` does not guarantee set iteration order.

## 4. How does mapping differ from Stream.map?

Both transform data using a mapping function, yet **the position of the transformation in the pipeline differs**.

### 4.1. Stream.map transforms before the collector receives elements

~~~java
List<String> names = employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());
~~~

This works when you only want a list of names of **all** employees. After `map`, the Stream's element type is `String`; it no longer directly provides `Employee::department` for a subsequent grouping step.

This example **cannot** classify by `Employee::department` after the Stream has already become `Stream<String>`:

~~~java
// Wrong idea: after map, elements are only String.
// employees.stream()
//         .map(Employee::name)
//         .collect(Collectors.groupingBy(Employee::department));
~~~

Of course, one could construct a DTO carrying both name and department first and then group the DTO. However, when you only need one property to group by and another value to collect into the group, downstream `mapping` is usually cleaner and clearer.

### 4.2. Collectors.mapping transforms inside the composed collector

~~~java
Map<String, List<String>> namesByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

`groupingBy` sees `Employee` before calling the downstream; `mapping` only transforms **the value collected for each key**.

### 4.3. Without nesting, the two approaches are usually equivalent in content

~~~java
List<String> a = employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());

List<String> b = employees.stream()
        .collect(Collectors.mapping(
                Employee::name,
                Collectors.toList()
        ));
~~~

Both produce the same sequence of names for the given source and mapper. In this case, `stream.map(...).collect(toList())` is typically easier to read. The greatest value of `Collectors.mapping` is **its ability to be composed as the downstream of another collector**, such as `groupingBy` or `partitioningBy`.

| Criterion | `Stream.map` | `Collectors.mapping` |
| --- | --- | --- |
| Position | Intermediate operation in the pipeline | Collector adapter, typically in a downstream |
| Intermediate output | A `Stream<U>` | A `Collector<T, ?, R>` |
| Use when | You want to change element type for later steps | You want the parent collector to still see `T`, while the child collector collects `U` |
| Terminates pipeline itself? | No | No; requires calling `collect(...)` |
| Useful with `groupingBy` | Yes, when enough data is retained for grouping | Especially useful to group by `T`, collecting results from `U` |

## 5. Combining mapping with different downstream collectors

`mapping` is not limited to `toList`. The inner collector determines the result shape and how aggregation works.

### 5.1. Set of distinct names

~~~java
Map<String, Set<String>> names = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toSet())
        ));
~~~

The output for each department is a `Set<String>`. If two employees share the same name, the set retains only one value according to `Set` equality rules. If you need to keep both employees, collect IDs or records with unique keys; do not use personal names as identifiers when names can collide.

### 5.2. Comma-separated string of names

~~~java
Map<String, String> joinedNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));

System.out.println(joinedNames.get("DEV"));
// Lan, An, Huy
~~~

`joining` works directly only on strings (more precisely, `CharSequence`). `mapping` turns `Employee` into `String` to satisfy the downstream.

### 5.3. Summing name lengths by department

~~~java
Map<String, Integer> charactersByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.summingInt(String::length)
                )
        ));

System.out.println(charactersByDepartment.get("DEV"));
// 8: Lan(3) + An(2) + Huy(3)
~~~

Here `T = Employee`, `U = String`, and the downstream result is `Integer`. This example highlights that `mapping` does not have to produce a collection: it can feed mapped values into **an aggregating collector**.

For a calculation depending directly on `Employee`, you could write it more briefly as `Collectors.summingInt(employee -> employee.name().length())`. `mapping` fits better when you want to reuse a collector for type `U` or make transformation steps explicit.

### 5.4. Collecting into a chosen collection type

When you need insertion order within each group while keeping distinct names:

~~~java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> orderedNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));
~~~

With a `List` source having encounter order and a sequential pipeline, `LinkedHashSet` preserves insertion order of names within each group. Using `Collectors.toSet()` would **not** guarantee iteration order. Do not confuse the order of the collection **inside each group** with the order of **keys in the outer Map**.

## 6. mapping inside partitioningBy and multi-level groupingBy

### 6.1. Splitting into two groups by a condition

`partitioningBy` divides data by a boolean predicate. A `mapping` downstream lets each branch retain only the necessary data:

~~~java
Map<Boolean, List<String>> namesByActivity = employees.stream()
        .collect(Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));

System.out.println(namesByActivity.get(true));
// [Lan, Minh, Huy]
System.out.println(namesByActivity.get(false));
// [An, Hạnh, Bình]
~~~

Unlike `groupingBy`, `partitioningBy` always returns both `true` and `false` keys, even if one branch has no elements. In that case, the downstream creates an empty result according to the corresponding collector's behavior.

### 6.2. Grouping by department, then by status

~~~java
Map<String, Map<Boolean, List<String>>> nested = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.groupingBy(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(nested.get("DEV").get(true));
// [Lan, Huy]
System.out.println(nested.get("DEV").get(false));
// [An]
~~~

The pipeline has multiple collector layers:

~~~text
Stream<Employee>
    |
groupingBy(department)
    |
    +-- groupingBy(active)
            |
            +-- mapping(name)
                    |
                    +-- toList()
~~~

The result is `Map<String, Map<Boolean, List<String>>>`. The inner `groupingBy` branch only creates a boolean key **if there is an element in that branch**; if you always want both boolean keys present, use downstream `partitioningBy(Employee::active, ...)`.

### 6.3. Collecting results with sorted keys

If department order needs to be sorted by key, you can supply an outer Map factory:

~~~java
import java.util.TreeMap;

Map<String, List<String>> sortedDepartments = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

In the example, `TreeMap` sorts department keys by `String` natural ordering. The `mapping` collector only determines **each group's value**, not how keys are ordered.

## 7. Combining filtering with mapping: distinguishing filter placement

Since **Java 9**, `Collectors.filtering(predicate, downstream)` allows filtering elements **inside an already-created group**.

Suppose the requirement is: “Each department has a list of active employee names; even a department with only inactive employees must appear with an empty list”.

Moving `filter` before `groupingBy` will **completely omit** departments that have no active employees:

~~~java
Map<String, List<String>> onlyActiveDepartments = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));

System.out.println(onlyActiveDepartments.containsKey("OPS"));
// false
~~~

With downstream `Collectors.filtering`, `groupingBy`'s classifier still sees every Employee. The `OPS` group is created, and then inactive employees are excluded from entering the downstream `mapping`:

~~~java
Map<String, List<String>> allDepartments = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(allDepartments.get("DEV"));
// [Lan, Huy]
System.out.println(allDepartments.get("QA"));
// [Minh]
System.out.println(allDepartments.get("OPS"));
// []
~~~

The two results are **not equivalent** because “must keep all department keys” differs from “consider only active employees”.

### mapping before or after filtering?

You can choose the order based on the data type the predicate needs:

~~~java
// Filter on Employee before converting to String:
Collectors.filtering(
        Employee::active,
        Collectors.mapping(Employee::name, Collectors.toList())
)
~~~

Conversely:

~~~java
// Convert to String first, filter on the mapped name:
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                name -> name.length() >= 3,
                Collectors.toList()
        )
)
~~~

In the second approach, the downstream of `mapping` receives `String`, so the predicate sees only the name and no longer has direct access to the Employee's `active` status. Collector ordering must match the **type and semantics** of each step.

## 8. mapping vs. flatMapping: keeping a single value or flattening multiple values?

`Collectors.mapping` converts **each element `T` into exactly one value `U`** and forwards it to the downstream. If `mapper` returns a `List<String>`, the downstream receives **the whole List**, without automatically expanding the List's elements.

An example that misses the goal if you want a set of individual skills:

~~~java
// Set of LISTS of skills, not a set of skill names:
Map<String, Set<List<String>>> skillListsByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::skills,
                        Collectors.toSet()
                )
        ));
~~~

If the requirement is “each department has a set of distinct skills”, use `Collectors.flatMapping` (Java 9+) to turn each Employee into a `Stream<String>` and flatten it into the downstream:

~~~java
Map<String, Set<String>> skillsByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.flatMapping(
                        employee -> employee.skills().stream(),
                        Collectors.toSet()
                )
        ));

System.out.println(skillsByDepartment.get("DEV"));
// Set containing Java, SQL, Spring, Docker (order not guaranteed).
~~~

Comparison table:

| Collector adapter | Input function | Number of elements sent to downstream per input |
| --- | --- | --- |
| `mapping(mapper, downstream)` | `T -> U` | Exactly one value `U`, even if it is a collection or `null` |
| `flatMapping(mapper, downstream)` | `T -> Stream<U>` | Zero, one, or many values `U` |
| `filtering(predicate, downstream)` | `T -> boolean` | Zero or one element `T` |

Adapters can be nested, but you should not use `mapping` to pretend to do `flatMapping`. Look at the **actual data type entering the downstream** to tell whether the result is single-level or nested.

`flatMapping` is responsible for closing the Stream returned by the mapper after that Stream's contents are forwarded to the downstream. However, if the primary source is tied to I/O such as `Files.lines`, you still must manage the primary source's lifecycle with `try-with-resources`.

## 9. mapping with BigDecimal calculations and exact aggregation

Collectors do not only collect names or lists. In a sales application, `mapping` can be used to compute total revenue per customer within the same pipeline.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String customerId, long quantity, BigDecimal unitPrice) {}

List<Sale> sales = List.of(
        new Sale("C-01", 2, new BigDecimal("12.50")),
        new Sale("C-02", 1, new BigDecimal("8.75")),
        new Sale("C-01", 3, new BigDecimal("2.40"))
);

Map<String, BigDecimal> exactRevenue = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::customerId,
                Collectors.mapping(
                        sale -> sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())),
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                BigDecimal::add
                        )
                )
        ));

System.out.println(exactRevenue.get("C-01")); // 32.20
System.out.println(exactRevenue.get("C-02")); // 8.75
~~~

Steps:

1. `groupingBy(Sale::customerId, ...)` classifies by customer ID.
2. `mapping` converts each `Sale` into a `BigDecimal` line total.
3. `reducing(BigDecimal.ZERO, BigDecimal::add)` sums the amounts in each group without intermediate rounding.
4. The result is `Map<String, BigDecimal>`, each key storing an exact monetary total.

`2 × 12.50 + 3 × 2.40 = 25.00 + 7.20 = 32.20`. In monetary systems, scale and rounding policies belong to the business domain: if totals must be rounded per customer or per invoice, round **only at the defined boundary**, rather than calling `setScale` on every accumulator addition by default.

If only a simple calculation is needed, `Collectors.reducing(identity, mapper, op)` can also combine the mapping and reduction steps, but `mapping(..., reducing(...))` is particularly easy to extend when switching the downstream to another collector type.

## 10. Handling null and invalid data

`Collectors.mapping` **does not check for null automatically**, does not fix source data, and does not guarantee that the downstream accepts every value the mapper returns.

Example where a name can be `null`:

~~~java
record Person(String team, String name) {}

List<Person> persons = java.util.Arrays.asList(
        new Person("DEV", "Lan"),
        new Person("DEV", null)
);
~~~

With `Collectors.mapping(Person::name, Collectors.toList())`, some list collector implementations may store `null`; the contract of the resulting collection type of `Collectors.toList` should not be relied upon to infer business data validation policies. With `Collectors.toUnmodifiableList()` (Java 10+), `null` elements **are rejected** and collection can throw `NullPointerException`.

How to handle it should follow requirements:

~~~java
Map<String, List<String>> validNames = persons.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.mapping(
                        person -> java.util.Objects.requireNonNull(
                                person.name(), "name is required"
                        ),
                        Collectors.toList()
                )
        ));
// A null name field causes an explicit error.
~~~

If business rules allow skipping missing names while still keeping the group key, use `Collectors.filtering` before `mapping` in the downstream:

~~~java
Map<String, List<String>> nonNullNames = persons.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.filtering(
                        person -> person.name() != null,
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()
                        )
                )
        ));
~~~

With the second approach, the `DEV` group still exists, and the list contains only `Lan`. If every member in a group has a `null` name, the group still gets an empty list.

In particular, standard `groupingBy` does not accept a **`null` classifier key**. Normalize or validate `department`/`team` values before collecting; do not confuse `groupingBy`'s outer key policy with the value policy inside `mapping`.

## 11. Ordering and mutability contracts of the result

A nested collector produces **multiple levels of data structures**, each with its own contract. For example:

~~~java
Map<String, List<String>> result = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

- The outer `Map` maps each department key to a list.
- The inner `List` holds the names collected by the downstream collector.
- Default `groupingBy` does not guarantee Map type, iteration order, or thread safety.
- `Collectors.toList()` does not guarantee the List class, mutability, serializability, or thread safety.
- On a Stream with encounter order and collectors not marked unordered, element encounter order is respected when collecting into lists.
- If you need **a specific type** or **a specific order**, choose an appropriate supplier/collector rather than relying on default implementations.

Example requiring both insertion-ordered group keys and a mutable `ArrayList` per group:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;

Map<String, ArrayList<String>> editableByDepartment =
        employees.stream().collect(Collectors.groupingBy(
                Employee::department,
                LinkedHashMap::new,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toCollection(ArrayList::new)
                )
        ));
~~~

This example uses a sequential `List` source and `LinkedHashMap`, so it preserves first-seen order of departments during iteration. Each value explicitly has type `ArrayList<String>`. If the result needs to be **unmodifiable** and reject `null`, use `Collectors.toUnmodifiableList()` in the downstream, while separately considering how to protect the outer Map.

An unmodifiable list also **does not make the element objects themselves immutable**: when a mapper returns mutable objects, external references can still mutate those objects' contents.

## 12. Parallel streams: mapping does not guarantee performance or thread safety

A pipeline can use `parallelStream()`:

~~~java
Map<String, List<String>> parallelNames = employees.parallelStream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
~~~

Standard collectors must support splitting the source, accumulating partial results, and combining per contract. However, **user-supplied mappers** must avoid depending on shared mutable state:

~~~java
// Wrong idea: shared counter causes side effects in the mapper.
int[] counter = {0};

Map<String, List<String>> broken = employees.parallelStream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        employee -> employee.name() + "-" + (++counter[0]),
                        Collectors.toList()
                )
        ));
~~~

Incrementing `++counter[0]` is unsafe when multiple tasks run concurrently, and the resulting name strings can depend on execution scheduling. If stable ordering or sequence numbers are needed, generate indices from an ordered source **before** running the pipeline, or design a separate numbering step with an explicit contract.

For standard `groupingBy` on parallel streams, merging sub-Maps can be costly; `groupingByConcurrent` may fit when processing does not depend on encounter order and the downstream meets the requirements. Yet `groupingByConcurrent` is not an automatic speedup: results and performance depend on key count, task contention, ordering, data size, and inner accumulation.

With `mapping(..., reducing(...))`, exact operations like `BigDecimal::add` are associative and parallelize cleanly; if you round after every addition, results can depend on partitioning. Ensure correctness before benchmarking performance.

## 13. Design patterns and common mistakes

| Need or symptom | Cause / choice | Solution approach |
| --- | --- | --- |
| Want to group by department but keep only names | `Stream.map` before grouping loses department info | `groupingBy(Employee::department, mapping(Employee::name, toList()))`. |
| `mapping(Employee::skills, toSet())` creates a set of lists | One Employee produces one `List<String>`, with no flattening step | Use `flatMapping(e -> e.skills().stream(), toSet())`. |
| Missing group keys whose elements were all filtered out | `stream.filter` runs before `groupingBy` | Use `groupingBy(..., filtering(..., mapping(...)))` when empty groups must stay. |
| Want a set of distinct elements | Downstream is using `toList()` | Choose `toSet()` or `toCollection(LinkedHashSet::new)`. |
| Want mutable lists per group | `Collectors.toList()` does not guarantee mutability | Use `toCollection(ArrayList::new)` in the downstream. |
| Need unmodifiable lists with no nulls | Mapper might return `null` | Validate source, use `toUnmodifiableList()` after guaranteeing validity. |
| Type mismatch when composing collectors | Mapper returns `U` differing from what downstream expects | Check `T -> U` signature and downstream input type. |
| Monetary total differs when running in parallel | Rounding inside combiner or side effects | Aggregate exact `BigDecimal`; round at a defined business step. |
| Unexpected Map key order | `groupingBy` does not guarantee key order | Supply `LinkedHashMap::new` or `TreeMap::new` as needed. |
| High memory usage with many groups | Accumulating many lists/sets in a Map | Reduce stored groups/values, aggregate directly, or process in batches. |

Collector adapters can be used like small building blocks: `groupingBy` determines **the grouping level**, `filtering` determines **which elements stay in the group**, `mapping` determines **what value to transform into**, and the final downstream determines **how to collect or aggregate**. Each layer has an independent role and can be verified by its types.

## 14. Performance, resources, and laziness

`Collectors.mapping` is part of the collection specification; it **does not traverse the Stream by itself**. Intermediate operations like `filter` and `map` are typically lazy. Only when `collect(...)` is called are elements processed through the pipeline.

Composability does not eliminate the inherent cost of the result:

- `groupingBy(..., mapping(..., toList()))` must store collected elements in each group's list; memory grows with the number of resulting elements.
- `groupingBy(..., mapping(..., toSet()))` must store distinct values, saving duplicates at the cost of managing set structures.
- `groupingBy(..., mapping(..., reducing(...)))` stores only one aggregated result per group (plus coordination structures), suitable when keeping every element is unnecessary.
- Heavy mappers, I/O inside a mapper, or creating many DTOs can dominate runtime regardless of collector choice.
- An unbounded infinite source cannot be collected into a finite Map/list if the collector must consume the entire source. Bound the input or ensure finite termination by contract.
- For Streams backed by resources such as `Files.lines`, use `try-with-resources` to close the source; `collect` does not automatically guarantee closing external resources.

Even though the API also supports Spliterator, parallel streams, and Stream Gatherers, using those features does not change the core job of downstream `mapping`: converting each element to a type the next collector can process. Source lifecycle, termination conditions, and resource limits must still be considered separately.

## 15. Practice exercises

### Exercise 1 — Reading result types

Given:

~~~java
Map<String, Set<Integer>> lengths = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        e -> e.name().length(),
                        Collectors.toSet()
                )
        ));
~~~

**Question:** What do `T`, `U`, and the result for group `DEV` mean?

**Answer:** `T = Employee`; `U = Integer` because the mapper takes the name length. The downstream creates a `Set<Integer>` containing **distinct** name lengths in each department. With `Lan`, `An`, `Huy`, the `DEV` group has the set `{2, 3}`; Set element print order is not guaranteed.

### Exercise 2 — Keeping a group with only inactive members

The employee dataset has department `OPS` containing only `Bình` with `active = false`. Should you use `employees.stream().filter(Employee::active).collect(groupingBy(...))` if the `OPS` key must be preserved?

**Answer:** No. Use `groupingBy(Employee::department, filtering(Employee::active, mapping(Employee::name, toList())))` to retain `OPS -> []`.

### Exercise 3 — Multi-valued nested data

Each `Employee` has `List<String> skills`. You need `Map<String, Set<String>>` containing the skill set by department, without keeping per-person boundaries.

**Answer:**

~~~java
Map<String, Set<String>> skills = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.flatMapping(
                        employee -> employee.skills().stream(),
                        Collectors.toSet()
                )
        ));
~~~

`mapping(Employee::skills, toSet())` would collect **Lists** instead of individual skills.

### Exercise 4 — Writing a joined-names report

Requirement: `DEV -> "Lan, An, Huy"`. Which collector should you use?

**Answer:**

~~~java
Map<String, String> names = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));
~~~

`mapping` converts `Employee` to `String`, and `joining` concatenates strings within each group in encounter order.

### Exercise 5 — Keyed aggregation

Given `Stream<Sale>` with `customerId`, `quantity`, and `unitPrice`, compute exact total revenue per customer without retaining a list of `Sale` objects.

**Answer:** Use `groupingBy(Sale::customerId, mapping(sale -> sale.unitPrice().multiply(BigDecimal.valueOf(sale.quantity())), reducing(BigDecimal.ZERO, BigDecimal::add)))`. This sums exact amounts per group. Add a rounding step **after** defining the policy at the appropriate reporting level.

### Exercise 6 — Result of partitioningBy

If every employee has `active = true`, does the result of `partitioningBy(Employee::active, mapping(Employee::name, toList()))` contain the `false` key?

**Answer:** Yes. `partitioningBy` always returns both `true` and `false`. When no employee belongs to the `false` branch, the downstream `toList` creates an empty list for that branch.

## 16. Summary

- `Collectors.mapping(mapper, downstream)` is a **Collector adapter** since Java 8 that transforms each element `T` into `U` before the downstream collects or aggregates it.
- When nested inside `groupingBy`, the classifier can continue using the original `T`, while each group's list/set/aggregate result is built from `U`.
- Choose the downstream to match the goal: `toList` to keep all values, `toSet` for distinct values, `joining` to concatenate strings, `summingInt` or `reducing` to aggregate.
- `Collectors.filtering` can preserve group keys even when every element in the group is rejected by the downstream predicate; `stream.filter` before `groupingBy` does not have this property.
- `Collectors.flatMapping` takes a Stream per element and flattens it; `mapping` converts one element into one value, even when that value is a List.
- Check `null`, encounter order, specific collection types, side effects, and associativity when using collectors in parallel pipelines.
- `mapping` configures the Collector, while `collect` triggers the terminal operation; memory and resources must be managed according to source size and kind.

**Main takeaway:** Use `Collectors.mapping` when you want to **keep the outer information for grouping, while converting into the type to collect at the inner level**. Clear collector composition keeps pipelines declarative, readable, and easy to scale from simple lists to multi-level summary reports.
