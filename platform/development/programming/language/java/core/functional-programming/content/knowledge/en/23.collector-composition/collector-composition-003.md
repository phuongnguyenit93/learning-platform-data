# Collectors.mapping(): Transforming Elements Within Each Group

## 1. Goal and Problem Statement

When processing data with Java Stream, sometimes we do not just want to **group objects by a key**, but also want to **transform the data kept inside each group**. For example, from a list of employees, we need a result:

```text
Dev → ["Lan", "An", "Binh"]
Ops → ["Minh", "Hoa"]
```

The original data source is `Employee(name, team, active)`, but the values in each group are only `String` employee names. If we write `stream().map(Employee::name)` too early, we may lose the `team` property used to create the grouping key.

A common solution is the **downstream collector** `Collectors.mapping(mapper, downstream)`, placed **inside** `Collectors.groupingBy(...)`. In this way:

1. The outer `groupingBy` collector still receives the `Employee` object to decide which group it belongs to.
2. Once an element has been routed to a group, `mapping` applies the transformation function, such as `Employee::name`.
3. A downstream collector such as `toList()`, `toSet()`, `joining()`, or `counting()` collects the **transformed** values into the result of each group.

Diagram:

```text
                      Employee
                         │
                         ▼
                 groupingBy(team)
                  /            \
                 ▼              ▼
               Dev             Ops
                │               │
          mapping(name)    mapping(name)
                │               │
                ▼               ▼
             toList()         toList()
                │               │
                ▼               ▼
           List<String>     List<String>
```

This is an important application of **composed collectors**: the outer collector controls the grouping structure; the inner collector decides how to process and collect the elements of **each** group.

## 2. Signature and Mechanism of `Collectors.mapping`

The Java SE API provides the static method:

```java
public static <T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream)
```

This is an API signature for study, not a standalone Java program.

Meaning of the type parameters:

| Symbol | Meaning |
| --- | --- |
| `T` | Type of elements **entering** the `mapping` collector, for example `Employee` |
| `U` | Type of elements **after transformation**, for example `String` |
| `A` | Internal accumulation type of the downstream collector; usually does not need to be declared explicitly |
| `R` | **Final result** type of the downstream, for example `List<String>` or `String` |
| `mapper` | Function that transforms a `T` into a `U` |
| `downstream` | Collector that processes the transformed `U` values |

Example:

```java
Collectors.mapping(Employee::name, Collectors.toList())
```

With `Employee::name` transforming `Employee → String`, the collector above receives `Employee` and returns a result of type `List<String>`. When nested inside `groupingBy(Employee::team, ...)`, the final result is usually `Map<String, List<String>>`.

**Key point:** `mapping` **does not group by itself**. It only transforms the input and passes it to the downstream. Grouping is performed by `groupingBy`, separating them into two independent roles.

## 3. Complete Java 17 Example: Getting Names by Department

Save as `MappingGroupsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MappingGroupsDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("Minh", "Ops", false),
                new Employee("An", "Dev", true),
                new Employee("Hoa", "Ops", true),
                new Employee("Binh", "Dev", false)
        );

        Map<String, List<String>> namesByTeam = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        Map<String, String> joinedNamesByTeam = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.joining(" | ")
                        )
                ));

        System.out.println("teams=" + namesByTeam);
        System.out.println("joined=" + joinedNamesByTeam);
    }
}
```

Compile and run with Java 17+:

```bash
javac MappingGroupsDemo.java
java MappingGroupsDemo
```

Exact output:

```text
teams={Dev=[Lan, An, Binh], Ops=[Minh, Hoa]}
joined={Dev=Lan | An | Binh, Ops=Minh | Hoa}
```

Layer-by-layer explanation:

- `employees.stream()` emits five `Employee` objects in the order of the `List`.
- `Employee::team` is the **classifier**: each object is routed to the group key `Dev` or `Ops`.
- `TreeMap::new` creates a Map with ascending key order, so the example displays `Dev` before `Ops`. If you use the default `groupingBy(classifier, downstream)` overload, you should not rely on key order when printing the entire Map.
- After choosing the group, `mapping(Employee::name, toList())` extracts the name and adds it to that group's list. The input element to `groupingBy` is still `Employee`.
- With another collector, `mapping(Employee::name, joining(" | "))` returns **a single String** for each key, not a List.
- Employees with duplicate names can still appear repeatedly in the list or string because `toList` and `joining` do not deduplicate automatically.

The result types clearly show the difference:

```text
groupingBy(team, mapping(name, toList()))
    → Map<String, List<String>>

groupingBy(team, mapping(name, joining(" | ")))
    → Map<String, String>
```

Each `collect` call in the program uses a new stream, avoiding the error of reusing an already consumed Stream.

## 4. Distinguishing `stream.map(...)` from `Collectors.mapping(...)`

Both use a transformation function, but their **position in the collection process** differs.

### 4.1. `map` upstream: transforms the entire Stream before the outer collector sees it

```java
employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());
```

After `map(Employee::name)`, each element of the Stream is a `String`. If you continue with:

```java
// Intentional counterexample: does not compile.
employees.stream()
        .map(Employee::name)
        .collect(Collectors.groupingBy(Employee::team));
```

it will be invalid in terms of types: `groupingBy` now receives `String`, whereas `Employee::team` is a method reference for `Employee`.

### 4.2. `mapping` downstream: the classifier still receives the original input

```java
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::team,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
```

Here, `groupingBy` selects the key based on `Employee` before passing **the group's value** to `mapping`. Therefore, the `team` property is not lost when creating groups.

### 4.3. Can we create a DTO to `map` before `groupingBy`?

Yes. If the upstream transformation **retains all the keys needed for grouping**, both approaches can produce the same result under certain business rules. For example, a DTO `NameByTeam(team, name)` still keeps the team; using `map(e -> new NameByTeam(e.team(), e.name()))` and then `groupingBy(NameByTeam::team, mapping(NameByTeam::name, toList()))` can produce a similar list of names.

However, creating intermediate objects and unnecessary type conversions can make the pipeline longer. When you already have the original input along with the classifier, using downstream `mapping` is usually more direct: **keep the original key, only transform the data collected within the group**.

**Rule:** use `Stream.map` when all subsequent operations should see the transformed type; use `Collectors.mapping` when only the downstream collector needs the transformed type, while the enclosing collector still needs the original element.

## 5. Downstream Collectors Commonly Combined with `mapping`

| Purpose within each group | Downstream | Map value type |
| --- | --- | --- |
| Keep all names | `mapping(Employee::name, toList())` | `List<String>` |
| Keep distinct names | `mapping(Employee::name, toSet())` | `Set<String>` |
| Unique names, ordered | `mapping(Employee::name, toCollection(TreeSet::new))` | `TreeSet<String>` |
| Join names into a string | `mapping(Employee::name, joining(", "))` | `String` |
| Count elements after transformation | `mapping(Employee::name, counting())` | `Long` |
| Check the longest name | `mapping(Employee::name, maxBy(comparingInt(String::length)))` | `Optional<String>` |

The collectors in the table must be called via `Collectors` (for example `Collectors.mapping(...)`, `Collectors.counting()`), or with appropriate static imports. These are **illustrative expressions**, not a standalone program.

Important:

- `toList()` is often useful if you want to keep multiple elements and preserve encounter order in an ordered pipeline.
- `toSet()` removes duplicate elements by equality, but **does not guarantee a specific Set implementation or iteration order**. If you need a list of names with a clear order, you can use `toCollection(TreeSet::new)` with an appropriate comparator/natural order.
- `joining(", ")` only applies when the values emitted by the mapper are compatible with `CharSequence`. If the mapper returns an `Integer` or an object, it must be converted to String.
- `counting()` after `mapping` is usually unhelpful when the mapper does not filter elements: it counts the transformed elements, but the transformed values are not used. If you only need to count employees per group, `groupingBy(Employee::team, counting())` is simpler.
- A collector like `maxBy(...)` returns `Optional` to represent the case where there are no values in a group after relevant filtering operations. Do not call `get()` without accounting for empty groups.

`mapping` itself **does not filter** and **does not deduplicate**. Those properties are determined by the mapper and the downstream collector.

## 6. Example: Normalizing Names and Deduplicating Within Each Group

Requirement: names in each city must be uppercase, unique, and sorted in ascending order. A useful combination is:

```java
Collectors.mapping(
        item -> item.name().toUpperCase(Locale.ROOT),
        Collectors.toCollection(TreeSet::new)
)
```

Here:

1. `mapping` converts each name to uppercase within its respective group.
2. `toCollection(TreeSet::new)` stores the names as an ordered set, deduplicating according to String's comparator/natural order.
3. `groupingBy` selects the city key from the original record.

Save the program `MappingSetDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class MappingSetDemo {
    record Person(String city, String name) {}

    public static void main(String[] args) {
        List<Person> people = List.of(
                new Person("Hanoi", "Lan"),
                new Person("DaNang", "Minh"),
                new Person("Hanoi", "An"),
                new Person("DaNang", "Hoa"),
                new Person("Hanoi", "Lan")
        );

        Map<String, TreeSet<String>> normalized = people.stream()
                .collect(Collectors.groupingBy(
                        Person::city,
                        TreeMap::new,
                        Collectors.mapping(
                                p -> p.name().toUpperCase(Locale.ROOT),
                                Collectors.toCollection(TreeSet::new)
                        )
                ));

        System.out.println(normalized);
    }
}
```

Compile/run:

```bash
javac MappingSetDemo.java
java MappingSetDemo
```

Output:

```text
{DaNang=[HOA, MINH], Hanoi=[AN, LAN]}
```

In the Hanoi group there are two records named `Lan`. After transforming to `LAN` and putting them into the TreeSet, only one `LAN` element remains. If we replace the downstream with `toList()`, both `LAN` names still appear; if we replace it with `toSet()`, deduplication still happens, but the print order is not guaranteed.

**Locale note:** `Locale.ROOT` provides stable uppercase conversion and is not intended to perform Vietnamese lexical sorting according to natural language rules. If the business logic requires local collation or Unicode normalization, a separate comparator/normalization is needed. Do not assume that `TreeSet<String>` using natural order is the right dictionary order for every locale.

## 7. Combining `filtering` and `mapping` Within Each Group

A common requirement is **to keep the groups that were seen, but only take the names of active members**. With Java 9+, `Collectors.filtering(predicate, downstream)` filters elements **inside the downstream collector**, so they can be combined:

```java
Collectors.groupingBy(
        Employee::team,
        Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        )
)
```

We need to distinguish two filtering positions:

- **Filtering before grouping:** `stream.filter(Employee::active).collect(groupingBy(...))`. If no records remain for a team, that team key **may not appear** in the result.
- **Filtering in the downstream:** `stream.collect(groupingBy(team, filtering(active, mapping(name, toList()))))`. The grouper has already seen the team before the downstream rejects the record, so that group can be kept with an empty list.

The program `MappingFilteringDemo.java` demonstrates the difference:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MappingFilteringDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> people = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("An", "Dev", false),
                new Employee("Minh", "Ops", false),
                new Employee("Hoa", "QA", true)
        );

        Map<String, List<String>> filterBefore = people.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        Map<String, List<String>> filterWithin = people.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.mapping(
                                        Employee::name,
                                        Collectors.toList()
                                )
                        )
                ));

        System.out.println("upstream=" + filterBefore);
        System.out.println("downstream=" + filterWithin);
    }
}
```

Compile/run:

```bash
javac MappingFilteringDemo.java
java MappingFilteringDemo
```

Output:

```text
upstream={Dev=[Lan], QA=[Hoa]}
downstream={Dev=[Lan], Ops=[], QA=[Hoa]}
```

Explanation: the Ops group has the record Minh, who is inactive. When filtering beforehand, Minh is removed before `groupingBy` sees the Ops team, so there is no Ops key. When filtering downstream, `groupingBy` sees Ops and creates the group, then `filtering` does not pass Minh to `mapping`, resulting in an empty list.

This is why downstream `mapping` and `filtering` are designed for **collector composition**, rather than forcing all operations to happen upstream.

**Pay attention to the order in the downstream:** `filtering(active, mapping(name, toList()))` means checking `Employee::active` first, then transforming `Employee → String`. If you write `mapping(Employee::name, filtering(Employee::active, toList()))`, the inner Predicate no longer receives Employee but receives String, which is a type error.

## 8. `partitioningBy` Can Also Contain `mapping`

Not only `groupingBy`, `partitioningBy(predicate, downstream)` splits data into **two true/false branches**, each with its own collector. For example:

```java
Map<Boolean, List<String>> namesByActive = employees.stream()
        .collect(Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
```

This is a code snippet inside a method that already has `employees` of type `List<Employee>` and imports `Map`, `List`, `Collectors`.

- The `true` key contains the names of active employees.
- The `false` key contains the names of inactive employees.
- `partitioningBy` provides both `true` and `false` keys by contract, even when one branch has no elements.
- Do not rely on the iteration order of a Boolean Map when printing directly; when you need to output results in a specific order, access `get(false)` / `get(true)` as needed.

For groups by arbitrary keys, use `groupingBy`; when splitting into exactly two groups by a Predicate, `partitioningBy` can be simpler. In both cases, `mapping` still transforms **elements in the inner collector**, without changing the group selection condition.

## 9. `mapping` and `flatMapping`: Single Value vs. Multiple Values

`Collectors.mapping(mapper, downstream)` sends **one output value from the mapper per input**, even if that value is a collection. If the mapper returns `List<String>`, the downstream `toList()` will create a **List<List<String>>** in the group, without flattening automatically.

Example:

```java
Collectors.mapping(
        Order::tags,
        Collectors.toList()
)
```

Suppose `Order.tags()` returns `List<String>`; each element in the group's result list is **a List of tags of one Order**.

If you want to merge the tags **of all Orders** into a single set, Java 9+ provides `Collectors.flatMapping(mapperToStream, downstream)`. Example:

```java
Collectors.flatMapping(
        order -> order.tags().stream(),
        Collectors.toSet()
)
```

It converts each Order into a **Stream<String>**, then sends each tag to the downstream, without keeping the sublists. In terms of types:

```text
mapping(tags, toList()):
   Order → List<String> → List<List<String>> in each group

flatMapping(tags.stream, toSet()):
   Order → Stream<String> → Set<String> in each group
```

The two APIs solve two different intents. If the sublist can be null, you need to choose an explicit handling policy instead of directly calling `null.stream()`. You can use an empty Stream to represent having no tags.

## 10. Reading the Generic Types of Nested Collectors Correctly

Below is a typical type chain:

```text
Stream<Employee>
    └── collect(groupingBy(Employee::team,
                mapping(Employee::name, toList())))
        │
        ├── classifier: Employee → String
        ├── mapper:     Employee → String
        ├── downstream: Collector<String, ?, List<String>>
        └── result:     Map<String, List<String>>
```

Although both the classifier and the mapper return String in the example, **they have different roles**: the classifier returns the map key, while the mapper returns the value passed to the inner collector.

We can transform to numeric types:

```java
Map<String, Integer> totalPoints = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.mapping(
                        Entry::points,
                        Collectors.reducing(0, Integer::sum)
                )
        ));
```

This is an illustrative snippet with type `Entry` having `team()` returning String, `points()` returning int, and collection `entries`. The result of the downstream reducing is Integer for each group. However, for a simple sum, `Collectors.summingInt(Entry::points)` directly inside groupingBy is usually more concise, avoids boxing, and has clearer intent:

```java
Map<String, Integer> totalPoints = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.summingInt(Entry::points)
        ));
```

Choose the smallest collector that accurately expresses the business logic; do not use `mapping` in every operation just because you can.

## 11. Execution Nature, Ordering, and Side Effects

`mapping` does not run at the time you merely create the lambda expression or reference the collector. When the terminal operation `collect(...)` is executed, the framework feeds elements into the accumulator, where the mapper is applied before passing the value to the downstream.

Things to keep in mind:

- **Encounter order:** With an ordered stream and a suitable downstream like `toList()`, the order of elements in each group reflects the encounter order of the elements belonging to that group. However, the order of **keys** is determined by the Map; the default `HashMap` does not guarantee key order.
- **No automatic sorting:** `mapping(Employee::name, toList())` does not sort names. If you want each group's output sorted, you can use `TreeSet` or apply an appropriate sorting step to the result after collecting.
- **No automatic deduplication:** only `toSet`, `TreeSet`, or another dedicated step is responsible for that.
- **Does not mutate the source:** if the mapper only returns a result, the collector does not modify the original object. However, if the lambda has side effects, it can still mutate external state; you must avoid such behavior unless there is a genuinely clear contract.
- **Parallel stream:** a collector may use multiple internal accumulators and combine the results. Do not rely on logging order inside the mapper; shared mutable state can cause race conditions.
- **Exceptions:** If the mapper throws a runtime exception, the terminal `collect(...)` may fail; the collector does not swallow errors or return fallback values on its own.
- **Checked exceptions:** `Function.apply` used in `mapping` does not declare checked exceptions. If the mapper needs to call an API that throws a checked exception, you must handle it appropriately or design a different API; an unhandled checked exception cannot escape directly through the lambda.

With a fixed data source and a pure mapper, results are easier to test when grouping logic, transformation, and downstream collectors are clearly separated.

## 12. Nulls and Invalid Data

A mapper **can return null**; `Collectors.mapping` does not automatically turn null into "no element". The consequences depend on the downstream:

- With `Collectors.joining(", ")`, a null element may appear as the text `"null"`, which is usually not the desired result.
- With `Collectors.toUnmodifiableList()`, null elements are **not accepted**.
- With `toList`, instead of relying on the implementation's null policy, you should decide the business rule explicitly and avoid inserting null if unnecessary.
- If the mapper calls `e.name().toUpperCase(...)` on a null name, a `NullPointerException` will be thrown before the downstream processes it.

When you need to **ignore null mapping results**, you can combine downstream `mapping` and `filtering` on the transformed type:

```java
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                java.util.Objects::nonNull,
                Collectors.toList()
        )
)
```

This snippet is an illustrative collector placed in the context of `groupingBy(Employee::team, ...)`, requiring Java 9+. Unlike `filtering(Employee::active, mapping(Employee::name, ...))`: here filtering receives **String** after mapping, so it can check whether the name is null.

If the grouping key returns null, the JDK's `groupingBy` does not accept a null classifier key; you need to validate, filter, or convert null into an explicit placeholder key before grouping. Do not use `groupingBy(e -> e.team())` and assume null is a valid group.

For business data that must be complete, **reporting an error/validating** may be more appropriate than silently dropping elements. Transforming within a group does not replace data validation rules.

## 13. Testing Collector Logic Layer by Layer

Instead of only checking one large Map and then hunting for the cause when it is wrong, you should test each part:

1. **Classifier:** Does `Employee::team` return the right team for each object, including edge cases?
2. **Mapper:** Does `Employee::name`, uppercasing, or converting to a DTO have the right type and data?
3. **Downstream:** Does using `toList`, `toSet`, `joining`, or `reducing` have the right semantics and handle duplicates properly?
4. **Aggregation:** With a small dataset, does the resulting Map have all keys and the correct list/string in each group?
5. **Empty groups:** When using downstream `filtering`, is the key preserved and is the empty group value correct?
6. **Ordering:** If printing the entire Map as test output, you must choose an ordered Map or compare contents by key instead of relying on HashMap.
7. **Nulls and exceptions:** Does the mapper handle invalid input according to the contract?

You can create minimal test data with at least two groups, one group whose elements are all filtered out, and one group with duplicate names. The results will clearly show the individual effects of `groupingBy`, `filtering`, and `mapping`.

## 14. Common Mistakes

1. **Converting objects to names upstream and still using a classifier on the original object.** After `stream.map(Employee::name)`, the Stream has type String; `groupingBy(Employee::team)` will be invalid.
2. **Assuming `mapping` creates groups by itself.** No; it is only a downstream collector and needs an outer collector such as `groupingBy` or `partitioningBy` if you want to group.
3. **Assuming `mapping` flattens sublists.** With a mapper returning a List, `mapping(..., toList())` creates `List<List<...>>`. Use `flatMapping` when you need to merge individual elements from substreams.
4. **Assuming `mapping` automatically deduplicates or sorts.** Those properties belong to the downstream collector or another stage.
5. **Mixing up the positions of `filtering` and `mapping`.** A Predicate that needs Employee must run before the Employee→String mapper; a Predicate checking String must run after the mapper.
6. **Using `toSet` and then expecting a specific display order.** A default Set does not guarantee order; choose TreeSet/comparator when order is a requirement.
7. **Assuming every group must appear after an upstream filter.** Groups with no remaining elements disappear; downstream filtering can keep the key with an empty value when the group has already been seen in the data.
8. **Passing null through a mapper without defining a policy.** Some downstreams do not accept null or print it as "null".
9. **Using `counting()` after mapping unnecessarily.** If you only count elements, drop the mapper and use counting directly.
10. **Attaching side effects to the mapper.** With parallel streams, ordering and concurrency conditions are hard to control; use pure transformation functions.
11. **Confusing the map key with the value inside the group.** The classifier determines the key, mapping determines the value, and the downstream determines the result.
12. **Forgetting to create a new stream when collecting multiple results.** A Stream already consumed by a terminal operation cannot be reused; create a new stream from the collection.
13. **Assuming `groupingBy` returns a TreeMap.** By default the Map type is not guaranteed; use the overload with a mapFactory if you need an ordered Map.
14. **Ignoring the performance of the mapper.** If the mapper makes network calls or expensive computations on each element, placing it inside a collector does not automatically make the work lighter; measure and redesign the source/logic when needed.

## 15. Self-Check Exercises

Given the data:

```java
record Task(String project, String owner, boolean done) {}

List<Task> tasks = List.of(
        new Task("A", "Lan", true),
        new Task("B", "Minh", false),
        new Task("A", "An", false),
        new Task("B", "Hoa", false),
        new Task("A", "Lan", true)
);
```

These snippets are placed inside a Java 17 class/method with `List` imported.

Build collectors on your own to get:

1. A Map from project to a **list of owner names**, keeping duplicate names.
2. A Map from project to a **set of unique owners**.
3. A Map from project to a list of **owners of completed tasks**, while still keeping key B with an empty list.
4. Explain why `tasks.stream().map(Task::owner).collect(groupingBy(Task::project))` has a type error.
5. State when to use `flatMapping` instead of `mapping`.

**Reference answers** (placed in a method, importing `Map` and `Collectors`):

```java
Map<String, List<String>> all = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.mapping(Task::owner, Collectors.toList())
        ));

Map<String, java.util.Set<String>> unique = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.mapping(Task::owner, Collectors.toSet())
        ));

Map<String, List<String>> completed = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.filtering(
                        Task::done,
                        Collectors.mapping(
                                Task::owner,
                                Collectors.toList()
                        )
                )
        ));
```

Contents by key (without relying on Map iteration order):

```text
all.get("A")       = [Lan, An, Lan]
all.get("B")       = [Minh, Hoa]
unique.get("A")    = {Lan, An}  (Set order is not guaranteed)
unique.get("B")    = {Minh, Hoa}
completed.get("A") = [Lan, Lan]
completed.get("B") = []
```

Answer to question 4: after `map(Task::owner)`, the Stream has type String, so it no longer has enough data to call `Task::project` as the classifier. Question 5: use `flatMapping` when one Task produces **multiple** elements via a substream that need to be merged into the same group, such as when each task has multiple tags and you want to collect each tag together.

## 16. Rule of Thumb

When you need to "**group by A but collect B in each group**", picture this:

```java
Map<Key, List<Value>> result = source.stream()
        .collect(Collectors.groupingBy(
                item -> keyOf(item),
                Collectors.mapping(
                        item -> valueOf(item),
                        Collectors.toList()
                )
        ));
```

This is an **illustrative template**: you need to define `Key`, `Value`, `source`, `keyOf`, and `valueOf` appropriately in a real program.

**Distinguish the three roles:**

- **Classifier (outer):** determines which group an element belongs to.
- **Mapper (inner):** determines what information from the element is put into the group.
- **Downstream collector (innermost):** determines whether each group's result is a List, Set, String, sum, statistics, or another structure.

If the upstream still needs fields from the original object to determine the key, do not transform those fields away too early. `Collectors.mapping` helps design a pipeline that groups by the original data while storing transformed output—concise, type-safe, and composable with `filtering`, `flatMapping`, and other collectors.

**References:** Java SE API `java.util.stream.Collectors.mapping`, `Collectors.groupingBy`, `Collectors.partitioningBy`, `Collectors.filtering`, `Collectors.flatMapping`, `Collectors.toCollection`, `Collectors.joining`, and `java.util.stream.Stream.collect`.