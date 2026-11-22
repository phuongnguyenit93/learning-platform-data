# `Collectors.filtering()` after `groupingBy()` differs from filtering the whole pipeline

## 1. Problem: filter elements before or after groups are formed?

When working with a Stream, we often want to **group data by a key** and then keep only the elements that satisfy a condition within each group. Two seemingly similar ways of writing this produce different results:

~~~java
// A: Filter data before grouping.
employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.toList()));

// B: Group first, filter in the downstream collector.
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

**Key difference:** With approach A, a department that **has no active employees** will have no elements reaching `groupingBy`, so **that department key will not exist in the resulting Map**. With approach B, `groupingBy` sees every employee, so **the department still appears** if it has at least one source employee; downstream `filtering` only removes inactive employees from **the value collected for that department**. That group's value may be an empty list.

Example:

~~~text
Source:
Engineering: An(active), Binh(active)
Sales:       Chi(inactive)
Support:     Dung(inactive)

Filter the entire Stream then groupingBy:
{Engineering=[An, Binh]}

groupingBy then downstream filtering:
{Engineering=[An, Binh], Sales=[], Support=[]}
~~~

The above is a simplified diagram by employee name, not the default `Employee` print representation. If you need a Map with a stable order for display, request a `TreeMap` or sort the result; default `groupingBy` does not guarantee the Map type or key iteration order.

That is the main point of this lesson: **where you place the predicate relative to the grouping step changes the existence of group keys**, even when the non-empty values of both approaches may be the same.

## 2. Quick review: `Stream.filter` and `Collectors.groupingBy`

`Stream.filter` is an **intermediate operation**:

~~~java
Stream<T> filter(Predicate<? super T> predicate);
~~~

It tests each element that the pipeline actually processes and only passes elements that satisfy the condition to subsequent steps. If an element does not pass `filter`, subsequent steps (including `groupingBy`) do not see it.

`Collectors.groupingBy` is a factory method creating a **Collector** to group elements by key:

~~~java
static <T, K> Collector<T, ?, Map<K, List<T>>>
        groupingBy(Function<? super T, ? extends K> classifier);
~~~

The more important overload in this lesson takes a downstream collector:

~~~java
static <T, K, A, D> Collector<T, ?, Map<K, D>>
        groupingBy(
                Function<? super T, ? extends K> classifier,
                Collector<? super T, A, D> downstream);
~~~

How to read it:

- `classifier` produces key `K` for **each element that reaches groupingBy**.
- `downstream` produces value `D` for each key.
- With `toList()`, each value `D` is `List<T>`.
- With `counting()`, each value `D` is `Long`.
- With `mapping(..., toList())`, each value `D` is a list of the transformed type.

The three-parameter overload lets you choose a Map factory:

~~~java
groupingBy(classifier, TreeMap::new, downstream)
~~~

This is useful when you want to iterate over keys in `TreeMap` order, for example so that displayed output and tests have a consistent order. When the key does not have a suitable natural order, you need to provide an appropriate comparator.

## 3. `Collectors.filtering`: filtering at the downstream layer

`Collectors.filtering` was added in Java 9 and is available in Java 17+:

~~~java
static <T, A, R> Collector<T, ?, R> filtering(
        Predicate<? super T> predicate,
        Collector<? super T, A, R> downstream);
~~~

It takes **two arguments**:

1. `predicate`: the condition deciding whether to pass the current element to the inner collector.
2. `downstream`: the collector that will receive elements passing the condition and aggregate them.

Standalone usage example:

~~~java
List<Integer> even = Stream.of(1, 2, 3, 4)
        .collect(Collectors.filtering(
                n -> n % 2 == 0,
                Collectors.toList()));

System.out.println(even); // [2, 4]
~~~

With a standalone collector like above, the resulting value is similar to `stream.filter(predicate).collect(toList())`. **The striking difference appears when `filtering` is placed inside a composed collector**, specifically downstream of `groupingBy`: then an empty list can still be the value of an existing group key.

**Do not confuse the two similar names:**

- `Stream.filter(predicate)` is a Stream operation that filters **before** data reaches the collector.
- `Collectors.filtering(predicate, downstream)` creates a **Collector** to filter during collection; inside `groupingBy`, it applies to **the downstream value of each group**.

## 4. How groups are formed: why can keys be retained?

Suppose:

~~~java
record Employee(String name, String department, boolean active) {}

List<Employee> employees = List.of(
        new Employee("An", "Engineering", true),
        new Employee("Binh", "Engineering", true),
        new Employee("Chi", "Sales", false));
~~~

**Approach A — filter before grouping:**

~~~java
Map<String, List<Employee>> early = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));
~~~

The stream reaching the collector only has An and Binh left. `classifier` is never called for Chi. Therefore, there is no `Sales` group in the `early` Map.

**Approach B — filter inside the group:**

~~~java
Map<String, List<Employee>> late = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

Each Employee reaching `groupingBy` is first classified by department. Because Chi belongs to `Sales`, the Map gets the `Sales` key. Downstream `filtering` does not pass Chi to `toList` because `active == false`. The collector for Sales can still finish with an empty list.

~~~java
System.out.println(early.containsKey("Sales")); // false
System.out.println(late.containsKey("Sales"));  // true
System.out.println(late.get("Sales").isEmpty()); // true
~~~

These are two different data models regarding **the meaning of group existence**:

- Missing key: the source after upstream steps did not send any element to the classifier for that key.
- Present key with empty value: the source had elements belonging to that key, but none of them satisfied the downstream predicate.

**Very important limitation:** downstream `filtering` does not invent keys that do not exist in the source at all. If no Employee belongs to `Legal`, neither approach automatically adds the `Legal` key. To represent all departments according to an independent catalog, you need an extra initialization/reconciliation step with the department catalog.

## 5. Pipeline diagram: what does the filter position decide?

### 5.1. Early filtering — groups can disappear

~~~text
Stream<Employee>
    |
    v
filter(Employee::active)
    |  drops Chi of Sales
    v
groupingBy(Employee::department)
    |
    +--- Engineering --> [An, Binh]
    |
    +--- Sales does not exist
~~~

Here `groupingBy` **does not receive** the dropped element. Thus the key based on that element is not formed either.

### 5.2. Filtering in downstream — groups can exist but be empty

~~~text
Stream<Employee>
    |
    v
groupingBy(Employee::department)
    |
    +--- Engineering --- filtering(active) ---> [An, Binh]
    |
    +--- Sales --------- filtering(active) ---> []
~~~

The classifier sees Chi of Sales and builds the group. Downstream filters the members but does not instruct the Map to remove the group's key.

This difference affects reports, UIs, dashboards, inventories, and problems that need to distinguish “no group” from “group with source data but no qualifying items”.

## 6. A particularly clear example: `counting()`

If the downstream is `Collectors.counting()`, keeping empty groups appears as **a value of 0**, instead of an empty list.

~~~java
Map<String, Long> countAfterEarlyFilter = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.counting()));

Map<String, Long> countWithDownstreamFilter = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.counting())));
~~~

With `Engineering` having 2 active people and `Sales` having only inactive people:

~~~text
countAfterEarlyFilter:
Engineering -> 2
Sales       -> no key

countWithDownstreamFilter:
Engineering -> 2
Sales       -> 0
~~~

Right mindset:

- Use `filter` **before the collector** if the result only needs to contain groups **with at least one matching element**.
- Use downstream `filtering(..., counting())` if the result needs to contain **every group that appeared in the source**, even when the number of matching elements is 0.

Do not write `map.get("Sales") == 0L` as a way to check for an empty group with early filtering; `get` can return `null` when the key does not exist, and unboxing or wrong-type comparison can cause errors. Use `containsKey` or `getOrDefault("Sales", 0L)` with clear intent.

### 6.1. Application to department statistics

Suppose total employee count and active employee count need to be displayed for the same set of departments. With downstream filtering, departments with 0 active employees still appear in the statistics. This is an **output data** property, not just “a cleaner way to write it”.

If you also want to display departments with **0 total employees**, grouping over the Employee list is still not enough; you must start from the department list or merge the result with the full department catalog.

## 7. Combining `filtering` with `mapping`

Besides `counting` and `toList`, downstream collectors are often nested to **both filter and transform** the retained elements.

For example, taking only the names of active employees in each group:

~~~java
Map<String, List<String>> activeNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()))));
~~~

Type flow:

~~~text
Stream<Employee>
   |
   v
groupingBy(Employee::department)
   |
   +--- downstream filtering(Employee::active)
                  |
                  +--- mapping(Employee::name)
                              |
                              +--- toList() -> List<String>
~~~

The resulting Map has type `Map<String, List<String>>`. In the Sales group, which has source employees but none active, the value is an empty `List<String>`.

You can reverse the nesting order of `filtering` and `mapping` **only if the predicate is written for the right type**:

~~~java
// After mapping Employee -> String,
// filtering receives String, no longer Employee.
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                name -> !name.isBlank(),
                Collectors.toList()))
~~~

You cannot write `Collectors.mapping(Employee::name, Collectors.filtering(Employee::active, toList()))` because downstream filtering now receives `String`, no longer `Employee`. **Read the nesting order from outside to inside and deduce the input type of each collector** to avoid generic errors.

### 7.1. Filtering by two conditions at once

~~~java
Collectors.filtering(
        e -> e.active() && e.name() != null,
        Collectors.mapping(Employee::name, Collectors.toList()))
~~~

In the code above, the predicate receives `Employee` and prevents null names from being passed downstream. The condition should reflect business policy, rather than just adding a null filter to hide missing data.

## 8. Before–after scenarios in business reporting

Imagine a data table:

| Department | Employee | Active |
| --- | --- | --- |
| Engineering | An | true |
| Engineering | Binh | true |
| Sales | Chi | false |
| Support | Dung | false |

Requirement 1: “Display **departments that have active employees**, along with the list of active people.” Here upstream filtering is appropriate.

~~~java
employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));
~~~

Requirement 2: “Display **all departments that appear in the Employee list**, including departments with no active employees, to show an empty state.” Here downstream filtering is appropriate.

~~~java
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

If you need to display all departments declared in the system, even **without any Employee**, neither pipeline above is sufficient. You can start from the department catalog and look up the corresponding group with `getOrDefault`, or use a merge step with the required keys.

**Neither approach is “always better”**: the placement of `filter`/`filtering` must come from the data question that the API or report needs to answer.

## 9. Empty source vs. source with groups that have no matching results

Three situations must be distinguished:

1. The source Stream is completely empty.
2. The Stream has group `A` but all elements of A are filtered out downstream.
3. The Stream has group A and some elements are kept.

~~~java
List<Employee> emptySource = List.of();

Map<String, List<Employee>> emptyResult = emptySource.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));

System.out.println(emptyResult.isEmpty()); // true
~~~

**No** keys are created because there are no Employees to classify. Downstream `filtering` does not generate keys out of thin air.

~~~java
List<Employee> inactiveOnly = List.of(
        new Employee("Chi", "Sales", false));

Map<String, List<Employee>> result = inactiveOnly.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));

System.out.println(result.containsKey("Sales")); // true
System.out.println(result.get("Sales").isEmpty()); // true
~~~

This is a direct, more stable way to check than printing the entire Map and relying on iteration order or object `toString()`.

## 10. `null` and classifier errors: downstream filtering is not a shield

An easy mistake to make: in `groupingBy(classifier, filtering(...))`, **the classifier must process the element before downstream knows whether to keep it**. Therefore, a downstream filter does not protect the classifier from invalid data.

Suppose an inactive Employee has `department == null`:

~~~java
List<Employee> source = List.of(
        new Employee("An", "Engineering", true),
        new Employee("Unknown", null, false));
~~~

Upstream filtering:

~~~java
Map<String, List<Employee>> early = source.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));

// Succeeds: the inactive element with null department is filtered out first.
~~~

Downstream filtering:

~~~java
// May throw NullPointerException because groupingBy must obtain
// key = null from Employee "Unknown" before filtering drops this person.
Map<String, List<Employee>> late = source.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

JDK `Collectors.groupingBy` overloads do not accept a classifier returning a null key; if the classifier returns null, they throw `NullPointerException`. Thus **choosing where to filter also affects validation and where errors occur**, not just the resulting key set.

If the data can contain null source elements, `Employee::department` can also throw an error immediately when applied to a null reference. Handle `Objects::nonNull` upstream when that is a valid filtering condition, or perform explicit validation if null data is an error that should be reported.

### 10.1. Null in downstream value

`Collectors.filtering` is not responsible for turning null results into valid values. If `mapping(Employee::name, toList())` returns a null name, the list created by `Collectors.toList()` can contain null; other downstreams like `toUnmodifiableList()` reject null and may throw `NullPointerException`. You must consider the **inner collector** itself and its data requirements.

## 11. `groupingBy` does not guarantee Map type or iteration order

`groupingBy(classifier, downstream)` returns `Map<K,D>`, but the API contract does not guarantee a specific Map such as `HashMap` or `LinkedHashMap`, nor does it guarantee iteration order. If you display results in department order, you can use the three-parameter overload:

~~~java
Map<String, List<Employee>> grouped = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                java.util.TreeMap::new,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

`TreeMap` keeps `String` keys sorted in natural order. The order of elements **within each List** depends on the source's encounter order and the downstream collector's contract; with a `List` source and a sequential pipeline, `toList` reflects the encounter order of the group's elements.

Do not assume `Collectors.filtering` always returns a List: **the result type belongs to the downstream**. For example:

~~~java
Collectors.filtering(Employee::active, Collectors.counting())
~~~

returns a Collector with result `Long`, whereas:

~~~java
Collectors.filtering(Employee::active, Collectors.mapping(
        Employee::name, Collectors.toSet()))
~~~

returns a Collector with result `Set<String>`. With `toSet`, the Set's iteration order is not guaranteed.

## 12. Complete Java 17+ program with deterministic stdout

Create the file **`GroupingFilteringDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingFilteringDemo {
    record Employee(String name, String department, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("An", "Engineering", true),
                new Employee("Binh", "Engineering", true),
                new Employee("Chi", "Sales", false),
                new Employee("Dung", "Support", false));

        Map<String, List<String>> earlyNames = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList())));

        Map<String, List<String>> lateNames = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.mapping(
                                        Employee::name,
                                        Collectors.toList()))));

        System.out.println("earlyNames=" + earlyNames);
        System.out.println("lateNames=" + lateNames);
        System.out.println("earlyHasSales="
                + earlyNames.containsKey("Sales"));
        System.out.println("lateHasSales="
                + lateNames.containsKey("Sales"));
        System.out.println("lateSalesEmpty="
                + lateNames.get("Sales").isEmpty());

        Map<String, Long> earlyCounts = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.counting()));

        Map<String, Long> lateCounts = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting())));

        System.out.println("earlyCounts=" + earlyCounts);
        System.out.println("lateCounts=" + lateCounts);

        Map<String, List<Employee>> emptyGroups =
                List.<Employee>of().stream()
                        .collect(Collectors.groupingBy(
                                Employee::department,
                                Collectors.filtering(
                                        Employee::active,
                                        Collectors.toList())));
        System.out.println("emptySourceMap=" + emptyGroups.isEmpty());

        List<Employee> withNullGroup = List.of(
                new Employee("An", "Engineering", true),
                new Employee("Unknown", null, false));

        Map<String, Long> earlyNull = withNullGroup.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.counting()));
        System.out.println("earlyNullSize=" + earlyNull.size());

        try {
            withNullGroup.stream()
                    .collect(Collectors.groupingBy(
                            Employee::department,
                            Collectors.filtering(
                                    Employee::active,
                                    Collectors.counting())));
        } catch (NullPointerException ex) {
            System.out.println("downstreamCannotHideNullGroup=true");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac GroupingFilteringDemo.java
java GroupingFilteringDemo
~~~

**Stdout:**

~~~text
earlyNames={Engineering=[An, Binh]}
lateNames={Engineering=[An, Binh], Sales=[], Support=[]}
earlyHasSales=false
lateHasSales=true
lateSalesEmpty=true
earlyCounts={Engineering=2}
lateCounts={Engineering=2, Sales=0, Support=0}
emptySourceMap=true
earlyNullSize=1
downstreamCannotHideNullGroup=true
~~~

Explanation:

1. `earlyNames` only has Engineering because the Sales and Support departments had no active employees surviving `Stream.filter`.
2. `lateNames` contains Sales and Support with empty Lists, because the classifier already created those groups from the source data before filtering decided which elements to keep.
3. `earlyHasSales` and `lateHasSales` show the difference using `containsKey`, not just by comparing empty lists.
4. `earlyCounts` drops keys with no active people; `lateCounts` keeps them with a count of 0.
5. With a completely empty source stream, `groupingBy` has no keys to create, so the Map remains empty.
6. When an inactive element carries a null key, upstream `Stream.filter` removes the element before the classifier; in the downstream filtering form, the classifier encounters null and throws `NullPointerException`.

Both printed Maps are requested with `TreeMap::new` so key order can be compared deterministically. Employee names are collected into `List`s in the encounter order of the sequential `List` source. There are no asynchronous tasks so stdout does not depend on execution scheduling.

## 13. When to choose which in practice?

### Use `stream.filter(...).collect(groupingBy(...))` when:

- You only want to group valid or qualifying records.
- You want groups **with no remaining matching elements** to disappear from the result.
- You need to block ineligible data before running the classifier (for example, test records that must not enter the main report).
- You want to reduce the amount of data reaching the grouping step, if that matches the semantics and benefits performance.

~~~java
Map<String, List<Employee>> activeDepartments =
        employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(Employee::department));
~~~

### Use `groupingBy(..., filtering(..., downstream))` when:

- You need to keep every key **that appeared in the source data**, even when there are no matching elements.
- You need per-group reports with count 0, sum 0 via a suitable downstream, or an empty list.
- You want to keep the group structure independent of a specific downstream condition.
- You need to combine `filtering` with `mapping` or other collectors to produce various value types per group.

~~~java
Map<String, Long> activeCounts =
        employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting())));
~~~

**Do not choose based on syntactic brevity.** The two pipelines solve different requirements; the difference can become a subtle bug when a group only has elements that fail the condition.

## 14. Parallel characteristics and side-effect requirements

Both `Stream.filter` and `Collectors.filtering` accept a `Predicate<T>`. Predicates should not depend on external mutable state and should not interfere with the source. Using callbacks with side effects to count exact invocation counts is unsafe because:

- Streams are lazy pipelines and some terminal operations may short-circuit or be optimized.
- A parallel stream may invoke the predicate from multiple threads, not in the expected order.
- Composed collectors may split and merge intermediate results according to their implementation.

For `groupingBy`, downstream filtering does not guarantee that a group will be processed sequentially in every execution model; adhere to the non-interference/stateless contract of Streams and collectors.

Note that `groupingByConcurrent` has different goals and characteristics from `groupingBy`; do not assume changing the collector name is harmless to encounter order or result structures. If you need parallelism and a specific Map order/type, check the API contract and benchmark with representative data.

## 15. Common mistakes

| Misconception / misuse | Why it is wrong | How to fix |
| --- | --- | --- |
| “The two filtering approaches are always equivalent” | They differ in keeping keys with no matching elements | Check `containsKey` and whether the business requirement wants to keep the key |
| Using upstream `filter` while wanting to show groups with 0 results | Groups whose elements are all filtered out will not be created | Move `filtering` into the downstream of `groupingBy` |
| Using downstream filtering while wanting to completely remove empty groups | Downstream usually just produces an empty value, without removing the key | Use upstream filter or intentionally post-process the Map |
| Assuming downstream filtering creates all keys from a catalog | It only keeps keys appearing in the source that reach the classifier | Use an independent key catalog if you need groups with no source data |
| Assuming filtering shields the classifier from null keys | The classifier runs before downstream filtering decides what to keep/drop | Validate/filter upstream or define key rules |
| Using `get(key).isEmpty()` on an upstream Map where the key might be absent | `get` may return null | Check `containsKey` or `getOrDefault` |
| Mistaking `Collectors.filtering` for a standalone terminal operation | It creates a Collector to be passed to `collect` | Distinguish a Collector from a Stream operation |
| Printing a plain Map to assert key order | `groupingBy` does not guarantee iteration order | Choose `TreeMap::new` or assert by key |
| Using `Employee::active` after `mapping(Employee::name,...)` | Downstream already has type `String` at that point | Place filtering before mapping or change the predicate to match the type |
| Thinking downstream always produces a `List` | The result type depends on the inner collector | Check `counting`, `toSet`, `mapping`, etc. |
| Adding side effects to infer predicate call counts | Parallel/lazy pipelines do not guarantee such counting | Use statistics/collectors with explicit contracts |

## 16. Self-check questions

**Question 1.** The Sales group has one employee, but `active=false`. How do the two pipelines below differ?

~~~java
employees.stream().filter(Employee::active)
        .collect(groupingBy(Employee::department));

employees.stream()
        .collect(groupingBy(Employee::department,
                filtering(Employee::active, toList())));
~~~

**Answer:** The first pipeline does not have the `Sales` key if Sales has no active employees. The second pipeline has the `Sales` key with an empty list, because the source has a Sales employee to form the group.

**Question 2.** If the downstream is changed to `counting()`, how is a group with no matching elements represented?

**Answer:** The group is kept with value `0L` in the downstream filtering Map. With an upstream filter, the key may not exist.

**Question 3.** If no Employee belongs to `Legal` in the source stream, does downstream filtering automatically create the Legal key?

**Answer:** No. `groupingBy` only knows the keys returned by the classifier from source elements that reach the collector. To include Legal, you must start from the department catalog or add merge logic.

**Question 4.** If an inactive Employee has `department=null`, can downstream filtering prevent `groupingBy` from throwing an error?

**Answer:** No. The classifier must be called to determine the key before downstream decides whether to keep the element; a classifier returning null is rejected by `groupingBy`. Upstream filtering can remove that element before the classifier runs.

**Question 5.** What should you do if you want a `Map<String,List<String>>` that keeps empty groups and only collects active employee names?

**Answer:**

~~~java
employees.stream().collect(groupingBy(
        Employee::department,
        filtering(
                Employee::active,
                mapping(Employee::name, toList()))));
~~~

To compile this snippet when using static imports, you need `import static java.util.stream.Collectors.*;`. This snippet illustrates how to nest collectors; the full program in section 12 uses explicit `Collectors` names.

**Question 6.** Is upstream filtering always “faster” than downstream filtering?

**Answer:** No general conclusion can be drawn. Upstream filtering can reduce the number of elements reaching the classifier, but the two approaches have different semantics and performance depends on characteristics of the source/predicate/collector. Prioritize matching the data requirement, and only optimize after measuring.

## 17. Key takeaways

**`Stream.filter` removes elements before they reach `groupingBy`; `Collectors.filtering` placed downstream of `groupingBy` removes elements from each group's result after the group key has been identified.** Therefore:

- `stream.filter(p).collect(groupingBy(key))`: groups with no elements satisfying `p` can **disappear completely**.
- `stream.collect(groupingBy(key, filtering(p, downstream)))`: groups that appeared in the source usually **still have their key**, though the downstream result may be `[]`, `0L`, or another neutral value depending on the collector.
- Groups that never appeared in the source will **not be created automatically**.
- Downstream filtering does not avoid `classifier` errors, such as null keys.
- You can nest `filtering` with `mapping`, `counting`, and other collectors; you must track the data type through each layer.
- Do not assume the iteration order of the Map returned by default `groupingBy`; request a Map factory or query by key when stable results are needed.

Choose **where to place the filter** based on the business question: “only get groups with results” or “keep every encountered group, even when the result is zero”.
