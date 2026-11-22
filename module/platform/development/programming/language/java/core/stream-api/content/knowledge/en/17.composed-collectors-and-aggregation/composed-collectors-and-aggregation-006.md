# Filtering Within Each Group with filtering

## 1. Why filter after groups have already been identified?

In the **Java Stream API**, a pipeline typically pulls data from a source, applies intermediate operations like `filter` and `map`, and ends with `collect`, `reduce`, or another terminal operation. When summarizing reports, we often use `Collectors.groupingBy` to split elements by keys such as department, region, or status.

Suppose a system has three teams: **Backend**, **Frontend**, and **Mobile**. The requirement is to report **high-priority unresolved tickets for each team**, even when a team has zero matching tickets.

If you filter at the start of the Stream, a team present in the source data that has no matching tickets disappears from the result. That can be undesirable when the UI needs to display every team with an empty list or a count of 0.

`Collectors.filtering` solves this by placing the filtering step **inside another collector**, typically as the downstream collector of `groupingBy`.

```text
                        Stream<Ticket>
                              |
                              v
                       groupingBy(team)
                          /    |     \
                      Backend Frontend Mobile
                          |      |       |
                 filtering(predicate) within each group
                          |      |       |
                    [T01]    [T06]     []
                              |
                              v
                Map<String, List<Ticket>>
```

The key distinction:

- **`stream.filter(...).collect(groupingBy(...))`:** removes elements **before groups are created**. Groups with no matching elements **will not appear**.
- **`stream.collect(groupingBy(..., filtering(..., toList())))`:** every source element still passes through the classifier to determine its group. A group that appeared in the source can be retained with an **empty list** if all of its elements are rejected by downstream filtering.

In the **Composed Collectors and Aggregation** chapter, this is an essential technique for producing complete category reports, distinguishing “no group” from “group present with zero matching records”.

**Lesson goals:** understand the contract of `Collectors.filtering`; choose the right filter placement; compose `groupingBy`, `mapping`, `counting`, `summingInt`, and `teeing`; recognize empty groups, `null`, ordering, and parallel limitations; and apply it in a standalone runnable Java report.

**Java version:** `Collectors.filtering` was introduced in **Java 9**. Examples using `record` and `Stream.toList()` require Java 16+; the complete example targets Java 17+.

## 2. Contract of Collectors.filtering

Signature in `java.util.stream.Collectors`:

```java
public static <T, A, R> Collector<T, ?, R> filtering(
        Predicate<? super T> predicate,
        Collector<? super T, A, R> downstream
)
```

Components:

| Component | Role |
| --- | --- |
| `T` | Type of elements fed into the downstream collector. |
| `predicate` | Condition deciding whether an element is forwarded to the downstream. |
| `downstream` | Collector that receives **matching elements** and produces result `R`. |
| `Collector<T, ?, R>` | New collector with an added filtering step before the downstream. |

Unlike `Stream.filter`, `Collectors.filtering` **does not return a Stream**. It returns **a Collector** to be passed into `collect` or nested inside another collector.

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> even = numbers.stream()
        .collect(Collectors.filtering(
                n -> n % 2 == 0,
                Collectors.toList()
        ));

System.out.println(even); // [2, 4]
```

In this ungrouped form, the result is equivalent in content to `numbers.stream().filter(n -> n % 2 == 0).toList()` on the sample data. The clear benefit of `filtering` appears when you want to **filter inside a nested collection step**.

`filtering` does not create groups on its own, does not merge elements, and is not required to return a List. **The result type depends on the downstream**: with `counting` it is `Long`, with `summingInt` it is `Integer`, and with `maxBy` it is `Optional<T>`.

## 3. Minimal example: group with data but no matching tickets

Create shared sample data for the examples:

```java
record Ticket(
        String id,
        String team,
        int priority,
        boolean resolved,
        int minutes
) {}

List<Ticket> tickets = List.of(
        new Ticket("T01", "Backend", 5, false, 30),
        new Ticket("T02", "Frontend", 2, false, 15),
        new Ticket("T03", "Backend", 3, true, 20),
        new Ticket("T04", "Backend", 1, false, 45),
        new Ticket("T05", "Mobile", 4, true, 10),
        new Ticket("T06", "Frontend", 4, false, 60)
);
```

Business condition: ticket is **unresolved** and has **priority at least 4**.

### Approach A: filter before groupingBy

```java
Map<String, List<Ticket>> filteredBeforeGrouping = tickets.stream()
        .filter(ticket -> !ticket.resolved() && ticket.priority() >= 4)
        .collect(Collectors.groupingBy(Ticket::team));

System.out.println(filteredBeforeGrouping.keySet());
// Only Backend and Frontend; key order is not guaranteed.

System.out.println(filteredBeforeGrouping.containsKey("Mobile"));
// false
```

Ticket `T05` is the only ticket belonging to `Mobile`, and it is already resolved, so it does not pass `Stream.filter`. Thus the classifier `Ticket::team` **never sees** the `Mobile` group, and the Map lacks that key.

### Approach B: filtering as downstream of groupingBy

```java
Map<String, List<Ticket>> filteredInsideGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.toList()
                )
        ));

System.out.println(
        filteredInsideGroups.get("Backend").stream().map(Ticket::id).toList()
); // [T01]

System.out.println(
        filteredInsideGroups.get("Frontend").stream().map(Ticket::id).toList()
); // [T06]

System.out.println(filteredInsideGroups.get("Mobile")); // []
System.out.println(filteredInsideGroups.containsKey("Mobile")); // true
```

`groupingBy` encountered `Mobile` from ticket `T05` and created a group for that key. Downstream `filtering` did not pass `T05` to `toList`, so the group's resulting list is empty.

| Case | `filter` before `groupingBy` | `groupingBy` + downstream `filtering` |
| --- | --- | --- |
| Group has matching elements | Has key, has elements | Has key, has elements |
| Group has source elements, **none match** | **No key** | **Has key, empty downstream result** |
| Key never appeared in source | No key | No key |
| Completely empty source | Empty Map | Empty Map |

**Note:** `filtering` does not invent groups for keys that never appeared. If a report must also display team `QA` despite having zero input tickets, you must supplement the team catalog from a trusted source after collecting, or design the source data to include those groups.

## 4. "Empty group" semantics differs from "no group"

The distinction above directly impacts reporting logic:

```java
Map<String, List<Ticket>> report = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.toList()
                )
        ));

System.out.println(report.containsKey("Mobile")); // true
System.out.println(report.get("Mobile").isEmpty()); // true

System.out.println(report.containsKey("QA"));      // false
System.out.println(report.get("QA"));              // null
```

- `Mobile` **appeared in the source data**, yet had no matching tickets. It can display “0 tickets requiring attention”.
- `QA` **did not appear in the source**. You cannot conclude from this Map alone whether the QA team exists in the system.

Therefore, do not equate `report.get(key) == null` with `report.get(key).isEmpty()`. If code wants a safe list to iterate when a key is missing, it can use:

```java
List<Ticket> qaTickets = report.getOrDefault("QA", List.of());
System.out.println(qaTickets.size()); // 0
```

However, `getOrDefault` only makes code cleaner to read; it **does not add the `QA` key** to the Map and does not erase the semantic difference between a group absent from the source and a present yet empty group.

## 5. Combining filtering with counting and summingInt

A report often only needs the count or sum of a property rather than keeping all tickets. In that case, replace `Collectors.toList()` with an aggregating downstream collector.

### Counting matching tickets per team

```java
Map<String, Long> urgentCounts = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(urgentCounts.get("Backend"));  // 1
System.out.println(urgentCounts.get("Frontend")); // 1
System.out.println(urgentCounts.get("Mobile"));   // 0
```

When `filtering` passes zero elements to `counting` for an existing group, the counting collector returns **`0L`**, not `null`. This is useful for KPI tables that need to show every team present in the source data.

### Total time of matching tickets

```java
Map<String, Integer> urgentMinutes = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.summingInt(Ticket::minutes)
                )
        ));

System.out.println(urgentMinutes.get("Backend"));  // 30
System.out.println(urgentMinutes.get("Frontend")); // 60
System.out.println(urgentMinutes.get("Mobile"));   // 0
```

`summingInt` accumulates integers for elements forwarded to the downstream. If there are no elements, the sum is **0**. An `int` sum can overflow if additions exceed its representable range; for large durations, consider `summingLong` and an appropriate data type.

### Optional result when the downstream finds an extremum

Not every downstream collector has a concrete “zero”:

```java
Map<String, Optional<Ticket>> highestUrgent = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.maxBy(
                                Comparator.comparingInt(Ticket::priority)
                        )
                )
        ));

System.out.println(highestUrgent.get("Mobile")); // Optional.empty

highestUrgent.get("Backend")
        .ifPresent(ticket -> System.out.println(ticket.id())); // T01
```

The `Mobile` key is still present, yet downstream `maxBy` returns `Optional.empty()` because no ticket matches. Avoid calling `get()` directly on an empty Optional; use `ifPresent`, `orElse`, or `orElseThrow` depending on business semantics.

## 6. filtering and mapping: ordering properly to keep needed data

`Collectors.mapping` is another downstream collector; it transforms each element before passing it to the inner collector. Combine these two collectors to extract only the **IDs** of matching tickets:

```java
Map<String, List<String>> idsByTeam = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(idsByTeam.get("Backend"));  // [T01]
System.out.println(idsByTeam.get("Frontend")); // [T06]
System.out.println(idsByTeam.get("Mobile"));   // []
```

Reading from outside in:

1. `groupingBy(Ticket::team, ...)` determines the group for every source ticket.
2. `filtering(predicate, ...)` decides which tickets are accumulated **within the group**.
3. `mapping(Ticket::id, toList())` extracts only the IDs of kept tickets.
4. `toList()` creates the corresponding list of IDs.

### Swapping mapping and filtering changes the predicate's input type

```java
Map<String, List<String>> idsStartingWithT = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.mapping(
                        Ticket::id,
                        Collectors.filtering(
                                id -> id.startsWith("T0"),
                                Collectors.toList()
                        )
                )
        ));
```

In this pipeline, `filtering` receives **`String id`** instead of `Ticket`. It can filter on the ID string, but cannot call `ticket.resolved()` or `ticket.priority()` because that information was already discarded by `mapping(Ticket::id, ...)`.

**Design rule:** place conditions requiring properties of the original object **before** the step that extracts a single field; place conditions on normalized or transformed values **after** the corresponding mapping step. Different orderings do not necessarily yield the same result.

## 7. Filtering inside multi-level groupingBy

`filtering` can sit at the innermost level of a collector nesting multiple `groupingBy` calls. For example, sales orders are grouped by **region → product category**, and then only IDs of paid orders are collected:

```java
record Sale(
        String id,
        String region,
        String category,
        int quantity,
        boolean paid
) {}

List<Sale> sales = List.of(
        new Sale("S01", "Bắc", "Sách", 2, true),
        new Sale("S02", "Bắc", "Bút", 5, false),
        new Sale("S03", "Nam", "Sách", 3, true),
        new Sale("S04", "Bắc", "Sách", 4, false),
        new Sale("S05", "Nam", "Bút", 1, false)
);

Map<String, Map<String, List<String>>> paidIds = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(
                        Sale::category,
                        Collectors.filtering(
                                Sale::paid,
                                Collectors.mapping(
                                        Sale::id,
                                        Collectors.toList()
                                )
                        )
                )
        ));

System.out.println(paidIds.get("Bắc").get("Sách")); // [S01]
System.out.println(paidIds.get("Bắc").get("Bút"));  // []
System.out.println(paidIds.get("Nam").get("Sách")); // [S03]
System.out.println(paidIds.get("Nam").get("Bút"));  // []
```

Both classifiers `Sale::region` and `Sale::category` observed the records for every combination before `filtering(Sale::paid, ...)` decided the list contents. Therefore, the **Bắc/Bút** and **Nam/Bút** combinations still appear with empty lists.

If `.filter(Sale::paid)` were moved before `collect`, both combinations that only have unpaid orders would vanish; if a region only had unpaid orders, **that entire region** would disappear as well.

This is a major difference for hierarchical reports: “a category with no paid sales in an active region” differs from “a category that never appeared in the data at all”.

## 8. Comparison with partitioningBy

`Collectors.partitioningBy` partitions by a Boolean predicate and always returns a Map with two keys **`true` and `false`**, even when one side has no elements.

We can still nest `filtering` inside the downstream of `partitioningBy`:

```java
Map<Boolean, Long> highPriorityCountsByResolution = tickets.stream()
        .collect(Collectors.partitioningBy(
                Ticket::resolved,
                Collectors.filtering(
                        ticket -> ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(highPriorityCountsByResolution.get(false)); // 2
System.out.println(highPriorityCountsByResolution.get(true));  // 1
```

In our dataset, two unresolved tickets have high priority (`T01` and `T06`), and one resolved ticket has high priority (`T05`).

Differences between the two collectors:

| Scenario | `groupingBy(classifier, filtering(...))` | `partitioningBy(predicate, filtering(...))` |
| --- | --- | --- |
| Keys | Values returned by the classifier | Only `true` and `false` |
| Keys absent from source | Not created automatically | Both Boolean keys remain present |
| Filtering within each group | Yes, via downstream `filtering` | Yes, via downstream `filtering` |
| Use cases | Department, region, category, composite keys | Binary classification such as resolved/unresolved |

If `tickets` is empty, `groupingBy` returns a Map with no teams, whereas `partitioningBy` still contains both Boolean entries with empty or zero downstream results depending on the collector. Do not confuse `partitioningBy`'s special property with `groupingBy`.

## 9. Combining filtering and teeing for multiple KPIs in one group

Since Java 12, `Collectors.teeing` lets you feed the same stream of elements into **two downstream collectors** and combine their results. Place `filtering` outside `teeing` when **both KPIs must operate on the same filtered subset of elements**.

```java
record TeamMetrics(long count, int totalMinutes) {}

Map<String, TeamMetrics> metrics = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingInt(Ticket::minutes),
                                TeamMetrics::new
                        )
                )
        ));

System.out.println(metrics.get("Backend"));
// TeamMetrics[count=1, totalMinutes=30]

System.out.println(metrics.get("Frontend"));
// TeamMetrics[count=1, totalMinutes=60]

System.out.println(metrics.get("Mobile"));
// TeamMetrics[count=0, totalMinutes=0]
```

`teeing` does not decide groups or filtering conditions itself. It simply executes two downstream collections on the elements passed to it:

```text
groupingBy(team)
      |
filtering(urgentAndUnresolved)
      |
      +-------- counting() --------> count
      |
      +-------- summingInt(...) ---> totalMinutes
                                       |
                            TeamMetrics(count, totalMinutes)
```

If two KPIs require **two different conditions**, do not place a shared `filtering` outside and try to infer excluded data from those KPIs. Instead, put `teeing` on the outside, with each branch having its own `filtering`:

```java
record StateMetrics(long unresolved, long highPriority) {}

Map<String, StateMetrics> allStateMetrics = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.teeing(
                        Collectors.filtering(
                                ticket -> !ticket.resolved(),
                                Collectors.counting()
                        ),
                        Collectors.filtering(
                                ticket -> ticket.priority() >= 4,
                                Collectors.counting()
                        ),
                        StateMetrics::new
                )
        ));

System.out.println(allStateMetrics.get("Backend"));
// StateMetrics[unresolved=2, highPriority=1]

System.out.println(allStateMetrics.get("Mobile"));
// StateMetrics[unresolved=0, highPriority=1]
```

Both branches in the last example use **independent** conditions; a single ticket is allowed to contribute to both KPIs or to just one. In composed collectors, `filtering` placement is part of the business model rather than a mere syntactic detail.

## 10. Keeping collected results unmodifiable

`filtering` can use various downstreams, including collectors that build unmodifiable lists such as `toUnmodifiableList` (Java 10+):

```java
Map<String, List<String>> readonlyIds = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.toUnmodifiableList()
                        )
                )
        ));

System.out.println(readonlyIds.get("Mobile")); // []
// readonlyIds.get("Backend").add("T99"); // UnsupportedOperationException
```

Importantly, **the list values** are unmodifiable, yet **the outer Map** from default `groupingBy` is not guaranteed to be unmodifiable. To publish a Map whose structure cannot be altered:

```java
Map<String, List<String>> lockedReport = Map.copyOf(readonlyIds);
```

`Map.copyOf` rejects null keys or values, does not guarantee iteration order, and provides only **shallow** immutability for nested objects. In this example, keys and elements are immutable `String`s and the lists are already unmodifiable, so the result is relatively straightforward to share safely.

Another option is using `Collectors.collectingAndThen` as the downstream, for instance:

```java
Map<String, List<String>> readonlyViaFinisher = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved(),
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        )
                )
        ));
```

`List.copyOf` has existed since Java 10 and rejects `null` elements. Which approach to use depends on Java version requirements, how the result is constructed, and the policy for nulls. Never assume `Collectors.toList()` guarantees a mutable list.

## 11. Errors with null and classifiers

`Collectors.groupingBy` does not allow a classifier to return a **null key**. An inner `filtering` cannot hide that error because the classifier runs **before** the downstream.

```java
record Entry(String team, boolean valid) {}

List<Entry> entries = List.of(
        new Entry("Backend", true),
        new Entry(null, false)
);

// WRONG: the element with team=null is still processed by the classifier before downstream.
Map<String, Long> invalid = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.filtering(
                        Entry::valid,
                        Collectors.counting()
                )
        ));
// Throws NullPointerException even though the team=null entry has valid=false.
```

In the example above, if the business rule is to **exclude all records missing a team**, filter them in the **outer Stream**:

```java
Map<String, Long> validCounts = entries.stream()
        .filter(entry -> entry.team() != null)
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.filtering(
                        Entry::valid,
                        Collectors.counting()
                )
        ));

System.out.println(validCounts.get("Backend")); // 1
```

Distinguish two processing layers:

- **`Stream.filter`** before `groupingBy` is the right choice for records that **cannot or should not be classified**, such as missing group keys, canceled records, or out-of-scope data.
- **`Collectors.filtering`** in the downstream handles **selection conditions within an already-identified group**, in order to retain that group's presence in the report.

When the input contains `null` elements themselves (not merely a null `team` field), `Entry::team` will also fail. Use `filter(Objects::nonNull)` before the classifier or define a missing-data policy.

If `filtering` passes an object with a null field to a downstream such as `Collectors.mapping(Entry::team, ...)`, it can still cause errors inside mapping; do not treat `filtering` as an automatic null check.

## 12. Element ordering, key ordering, and parallel processing

### Map key ordering

Default `groupingBy` does not guarantee Map type or key iteration order. To display groups in **first-seen order** from an ordered sequential Stream, specify `LinkedHashMap::new`:

```java
Map<String, List<String>> orderedGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                LinkedHashMap::new,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(Ticket::id, Collectors.toList())
                )
        ));

System.out.println(orderedGroups.keySet());
// [Backend, Frontend, Mobile]
```

In this sequential example, teams appear first in the order Backend → Frontend → Mobile. The fact that `Mobile` has an empty list does not remove its key.

### Element ordering within groups

With `List.stream()` having encounter order, `groupingBy` with downstream `toList` can preserve the encounter order of tickets forwarded into each group. In a parallel pipeline, the **execution order of predicates and mappers** is not guaranteed; never use side effects inside lambdas to infer or enforce order.

If each group's list must be **sorted by priority**, define an explicit sorting step or comparator; `filtering` does not sort elements.

### Parallel Streams and groupingByConcurrent

`groupingBy` is not a concurrent collector. With `parallelStream()`, the framework can build partial Maps and then combine them. Nested collectors like `filtering`, `mapping`, and `counting` must obey their combiner contracts.

```java
Map<String, Long> parallelCounts = tickets.parallelStream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(parallelCounts.get("Mobile")); // 0
```

If order is not needed, consider `groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentCounts = tickets.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));
```

`groupingByConcurrent` is a concurrent, unordered collector allowing a different collection strategy. However, it **does not automatically make stateful predicates or source mutations safe**; nor does it guarantee faster execution in every scenario.

## 13. Laziness, non-interference, and processing cost

`Stream.filter` is a lazy intermediate operation; `Collectors.filtering` is part of the **collector used at the terminal operation**. Both conditions are evaluated only when the terminal operation begins processing elements flowing through the pipeline.

```java
Stream<Ticket> pipeline = tickets.stream()
        .filter(ticket -> ticket.priority() > 0);

// Only when collect() runs is the pipeline consumed.
Map<String, Long> result = pipeline.collect(
        Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved(),
                        Collectors.counting()
                )
        )
);
```

With `groupingBy(classifier, filtering(...))`, the classifier is applied to determine the group for every element that passed earlier Stream operations; downstream `filtering` does not save the classification cost of rejected elements.

Therefore:

- If you only care about matching records and **do not need empty groups**, `Stream.filter` before `groupingBy` is usually cleaner and reduces the number of elements that must be classified.
- If **preserving groups that have source data but zero matching elements** is part of the report contract, `Collectors.filtering` is the right expression even with the extra classification cost.
- If you only need counts or sums, use `counting`/`summingInt` in the downstream instead of retaining all elements in large Lists.

Predicates must be **non-interfering** and **stateless** without depending on external mutable state:

```java
List<Ticket> mutableTickets = new ArrayList<>(tickets);

// WRONG: mutating the source itself while collect is traversing it.
Map<String, Long> broken = mutableTickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> {
                            mutableTickets.clear();
                            return ticket.priority() >= 4;
                        },
                        Collectors.counting()
                )
        ));
```

Mutating the source here violates non-interference and can cause `ConcurrentModificationException` or unreliable behavior. Also avoid using external counters to drive predicates, especially in parallel pipelines. If the source needs updating, finish collecting first and update in a separate step.

With very large datasets and multi-group KPIs, consider the memory footprint of the resulting Map, number of groups, classifier and downstream cost, and parallel coordination overhead. Business correctness must take priority over speed optimization.

## 14. Complete Java 17+ example: team KPI table

The following example produces three independent reports: list of urgent unresolved ticket IDs, count of urgent tickets, and combined count/time metrics. Team `Mobile` must **appear with empty or zero data** even though it has no qualifying tickets.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class FilteringWithinGroupsDemo {
    record Ticket(
            String id,
            String team,
            int priority,
            boolean resolved,
            int minutes
    ) {}

    record Metrics(long count, int totalMinutes) {}

    static boolean urgentUnresolved(Ticket ticket) {
        return !ticket.resolved() && ticket.priority() >= 4;
    }

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("T01", "Backend", 5, false, 30),
                new Ticket("T02", "Frontend", 2, false, 15),
                new Ticket("T03", "Backend", 3, true, 20),
                new Ticket("T04", "Backend", 1, false, 45),
                new Ticket("T05", "Mobile", 4, true, 10),
                new Ticket("T06", "Frontend", 4, false, 60)
        );

        Map<String, List<String>> urgentIds = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.mapping(
                                        Ticket::id,
                                        Collectors.toList()
                                )
                        )
                ));

        Map<String, Long> urgentCounts = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.counting()
                        )
                ));

        Map<String, Metrics> kpis = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.teeing(
                                        Collectors.counting(),
                                        Collectors.summingInt(Ticket::minutes),
                                        Metrics::new
                                )
                        )
                ));

        System.out.println(urgentIds);
        // {Backend=[T01], Frontend=[T06], Mobile=[]}

        System.out.println(urgentCounts);
        // {Backend=1, Frontend=1, Mobile=0}

        System.out.println(kpis);
        // {Backend=Metrics[count=1, totalMinutes=30],
        //  Frontend=Metrics[count=1, totalMinutes=60],
        //  Mobile=Metrics[count=0, totalMinutes=0]}

        System.out.println(urgentIds.containsKey("Mobile")); // true
        System.out.println(urgentIds.containsKey("QA"));     // false
    }
}
```

**Analysis:**

1. `Ticket::team` groups all tickets. `LinkedHashMap::new` preserves the appearance order of groups from the List source in the sequential pipeline.
2. `urgentUnresolved` is a **pure input-data predicate**: it only reads `Ticket` without modifying the source or shared variables.
3. `filtering` retains groups that appeared even when no ticket enters the downstream.
4. `mapping(Ticket::id, toList())` places only qualifying ticket IDs into the list.
5. `counting` produces `0` for the `Mobile` group; `teeing` combines count and total minutes.
6. Each report creates a fresh Stream from `tickets`. Never attempt to reuse a Stream already consumed by `collect`.

In a real application, if all three reports always need to be computed over the same large dataset, you can design an appropriate aggregate downstream collector to avoid traversing the source multiple times. The example here prioritizes clearly teaching the contract of each collector composition.

## 15. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Group with no matching tickets disappears | Placed `Stream.filter` before `groupingBy` | Use downstream `Collectors.filtering` if groups that appeared must be kept. |
| Group that never appeared is still missing from Map | `groupingBy` only creates keys from elements seen by the classifier | Merge with a separate group catalog if all valid keys must be included. |
| Cannot call `filtering` as a Stream operation | `Collectors.filtering` returns a `Collector`, not a `Stream` | Pass it to `collect` or as a downstream of `groupingBy`. |
| Predicate cannot access original object fields | Placed `mapping` before `filtering`, changing elements to another type | Swap collector nesting order or keep enough data for filtering. |
| `NullPointerException` in classifier despite downstream skipping record | Grouping happens before downstream filtering | Filter/handle unclassifiable records with `Stream.filter` upfront. |
| Calling `get(...).isEmpty()` fails for missing group | Map has no such key so `get` returns null | Use `containsKey`, `getOrDefault`, and distinguish the two states. |
| Expecting an empty List but receiving `Optional.empty` | Used `maxBy`/`minBy` instead of `toList` | Handle according to the actual downstream result type. |
| Assuming key order of `groupingBy` | Default Map does not guarantee order | Choose `LinkedHashMap` when sequential appearance order is needed. |
| Group KPI is wrong because all branches share one condition | Placed a single `filtering` outside `teeing` while KPIs need different criteria | Use `teeing` with each branch having its own `filtering`. |
| Incorrect or unstable stats in parallel execution | Predicate depends on shared variables or mutates source | Keep predicates stateless and non-interfering; test with realistic data and group counts. |

## 16. Practice exercises

Given employee data:

```java
record Employee(String department, String name, int age, boolean active) {}

List<Employee> employees = List.of(
        new Employee("IT", "An", 28, true),
        new Employee("IT", "Bình", 21, false),
        new Employee("HR", "Chi", 35, false),
        new Employee("Sales", "Dũng", 26, true),
        new Employee("HR", "Hà", 29, false)
);
```

**Requirements:**

1. Group employees by `department`, using `Collectors.filtering` to keep only `active` employees in each group.
2. Transform the result to `Map<String, List<String>>` containing only active employee names.
3. Count active employees per department. The `HR` department must have a count of `0`.
4. Compare with using `employees.stream().filter(Employee::active)` before `groupingBy`.
5. Write a report with two KPIs per department: number of active employees and number of employees aged 30 or above (two **independent** conditions).

**Reference solution:**

```java
Map<String, List<String>> activeNames = employees.stream()
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

System.out.println(activeNames.get("IT"));    // [An]
System.out.println(activeNames.get("HR"));    // []
System.out.println(activeNames.get("Sales")); // [Dũng]

Map<String, Long> activeCounts = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.counting()
                )
        ));

System.out.println(activeCounts.get("HR")); // 0

Map<String, List<Employee>> filteredFirst = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));

System.out.println(filteredFirst.containsKey("HR")); // false

record EmployeeMetrics(long active, long agedAtLeast30) {}

Map<String, EmployeeMetrics> twoKpis = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.teeing(
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting()
                        ),
                        Collectors.filtering(
                                employee -> employee.age() >= 30,
                                Collectors.counting()
                        ),
                        EmployeeMetrics::new
                )
        ));

System.out.println(twoKpis.get("HR"));
// EmployeeMetrics[active=0, agedAtLeast30=1]
```

In the last requirement, `HR` has **0 active employees** yet **1 employee aged 30 or above** (Chi, age 35); the two filters must reside in separate branches. This exercise helps distinguish keeping groups, changing element types with `mapping`, and choosing `filtering` placement in multi-level aggregation.

**Extension:** Add a `Legal` department with no employees in the list. Does `groupingBy` automatically create the `Legal` key? If the system has a separate department catalog, propose a post-collection step to populate missing keys with empty values and explain why fake data should not be fabricated inside a predicate.

## Key takeaway

`Collectors.filtering(predicate, downstream)` is a **downstream collector** for filtering elements **after the group classifier has been applied**. Placing it inside `groupingBy` preserves group keys present in the source data, even when all elements of a group are filtered out. This differs from `Stream.filter` running before `groupingBy`, which causes groups with no remaining matching elements to vanish completely.

Each group's value type depends on the downstream: `toList` gives an empty list, `counting` gives `0`, `summingInt` gives `0`, and `maxBy` gives `Optional.empty()` when no element matches. When composing with `mapping` or `teeing`, pay attention to element types and the semantics of each condition. Always keep predicates stateless and non-interfering; handle null keys before the classifier; do not assume Map ordering or `parallelStream` gains by default; and populate never-seen groups only from a trusted catalog source.
