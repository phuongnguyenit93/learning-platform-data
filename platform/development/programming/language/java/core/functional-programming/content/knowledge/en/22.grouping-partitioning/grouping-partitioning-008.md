# Reading the Result Types of Composed Collectors in Java Stream

When using **Stream.collect()**, an expression that looks simple like **groupingBy(classifier, counting())** can return **Map<String, Long>**, whereas **groupingBy(classifier, toList())** returns **Map<String, List<Employee>>**. If combined further with **mapping**, **filtering**, **flatMapping**, **partitioningBy**, **collectingAndThen**, or **teeing**, the result type can become a nested Map, Set, List, Optional, or record depending on the collector structure.

The point to learn is not memorizing dozens of syntax patterns by rote. You only need to know how to **read types from the inside out**: the innermost collector determines the data type each group returns; the outer collector determines under which key that data is placed or how it is further transformed.

This lesson belongs to the **Grouping and Partitioning** section of Java Core Functional Programming. The content applies to Java 17 and later, explaining the **Collector<T,A,R>** generic, type inference rules through practical examples, distinguishing groupingBy/partitioningBy and downstream collectors, analyzing common compilation errors, and providing a complete tested program.

## 1. Collector<T, A, R> — Three Letters You Must Know

The Collector interface has the conceptual form:

~~~java
Collector<T, A, R>
~~~

Where:

- **T — input element type:** the type of each element processed by the collector.
- **A — accumulation type:** the intermediate container/accumulation state type during collection.
- **R — result type:** the result type after the collector finishes.

With the code:

~~~java
List<String> names = List.of("An", "Binh", "Mai");
List<String> result = names.stream()
    .collect(Collectors.toList());
~~~

The stream has element type **String** and the collect result has type **List<String>**. The accumulation type A is an implementation detail of the collector and usually does not appear in the result variable declaration.

A convenient way to reason about it:

~~~text
Stream<T>
    .collect(Collector<T, A, R>)
    └───────────────────────┘
              R

The result of the collect call has type R.
~~~

**Do not assume R = A or R = T.** For example, **counting()** processes arbitrary T elements but returns Long; **summingInt(mapper)** returns Integer; **averagingInt(mapper)** returns Double; **joining()** returns String.

### 1.1. A Collector Is a Collection Recipe, Not the Result

~~~java
Collector<String, ?, Long> collector = Collectors.counting();
Long count = names.stream().collect(collector);
~~~

The collector variable is **an object describing how to collect**. count is **the result value**. The ? in the Collector type above represents an intermediate accumulation state that does not need to be named here; you should not guess the exact A of a JDK-provided collector.

What you need to read when using a composed collector is **the R of the child collector**, not the internal details of the accumulator A.

## 2. Distinguishing classifier, downstream, and Result

Suppose we have employee data:

~~~java
record Employee(String department, String name,
                int salary, boolean active) {}
~~~

And Stream<Employee> as the source. When grouping by department, the callback **Employee::department** has the functional type **Employee → String**. It returns **the grouping key**, not the entire collect result.

### 2.1. Default groupingBy(classifier)

~~~java
Map<String, List<Employee>> grouped = employees.stream()
    .collect(Collectors.groupingBy(Employee::department));
~~~

Reading from the outside in:

1. The stream provides **Employee** elements.
2. The classifier transforms **Employee → String**; the Map key is String.
3. Without an explicit downstream, **groupingBy** defaults to collecting the Employee elements of each group into a List<Employee>.
4. The outermost type is **Map<String, List<Employee>>**.

### 2.2. groupingBy(classifier, downstream)

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Here **downstream = counting()** returns Long. Therefore each String key is associated with a Long, **not List<Employee>**.

Type-reading formula:

~~~text
T = Employee
K = String from classifier
D = Long from counting()

groupingBy(classifier, downstream)
    -> Map<K, D>
    -> Map<String, Long>
~~~

This is the core rule of this lesson: **changing the downstream can completely change the value type of the Map**.

### 2.3. groupingBy with map factory

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.counting()
    ));
~~~

The three arguments consist of classifier, **mapFactory**, and downstream. TreeMap::new selects the concrete Map type and key ordering; downstream still determines the Long value type.

Meaningful signature:

~~~java
groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
~~~

returns **M**, with the constraint that M is a Map<K,D>. For example, a Map declared under the Map<String,Long> interface can have TreeMap as its actual implementation when mapFactory selects TreeMap.

**Do not confuse mapFactory with downstream:** TreeMap::new does not turn each group into a TreeMap; it determines the **outer** map containing the groups.

## 3. Inside-Out Type Reading Pattern

Before examining a complex composed collector, follow four steps:

1. **Identify T** from the source Stream, such as Stream<Employee>.
2. **Determine the result of the innermost collector**, e.g., counting() → Long.
3. **Apply downstream adapters**, e.g., mapping(Employee::name, toSet()) → Set<String>.
4. **Wrap with the outer collector**, e.g., groupingBy(Employee::department, ...) → Map<String, Set<String>>.

Example:

~~~java
Map<String, Set<String>> namesByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.toSet()
            )
        )
    );
~~~

Inference:

~~~text
Employee::name             : Employee -> String
toSet()                    : Collector<String, ?, Set<String>>
mapping(Employee::name, ..): Collector<Employee, ?, Set<String>>
Employee::department       : Employee -> String
groupingBy(.., ..)         : Collector<Employee, ?, Map<String, Set<String>>>
collect(..)                : Map<String, Set<String>>
~~~

In an actual call there are hidden generic parameters that the compiler infers automatically. The inference tree above describes the types to understand, not a statement of the exact writing of type A inside every collector.

### 3.1. Arrows Represent Input Transformation, Not Source Modification

**mapping(Employee::name, toSet())** converts each element's data from Employee to String before passing it to the downstream toSet. It does not modify the original Employee.

You should not understand mapping in Collector as Map<K,V>; this is an **adapter operation** wrapping a downstream collector.

## 4. Common Terminal Collectors and Their R Types

| Collector | Common R Type | Meaning |
| --- | --- | --- |
| toList() | List<T> | Result list |
| toSet() | Set<T> | Set of elements |
| toCollection(TreeSet::new) | TreeSet<T> | Collection specified by factory |
| counting() | Long | Number of elements |
| summingInt(mapper) | Integer | Sum of mapped int values |
| summingLong(mapper) | Long | Sum of mapped long values |
| averagingInt(mapper) | Double | Average value as double |
| summarizingInt(mapper) | IntSummaryStatistics | Count, sum, min, max, average |
| joining(delimiter) | String | Concatenate input CharSequences |
| maxBy(comparator) | Optional<T> | Maximum element, may not exist |
| minBy(comparator) | Optional<T> | Minimum element, may not exist |
| reducing(identity, op) | T | Aggregate by operator and identity |
| mapping(mapper, downstream) | R of downstream | Map before collecting |
| filtering(predicate, downstream) | R of downstream | Filter inside downstream |
| flatMapping(mapper, downstream) | R of downstream | Flatten multiple elements before downstream |
| collectingAndThen(downstream, finisher) | RR of finisher | Finish result R into RR |
| teeing(down1, down2, merger) | R of merger | Combine two downstream results |

The R type in the table is **the result value type** returned by the collector; when nested under groupingBy, R becomes **the value type of the Map**.

Example:

~~~java
Map<String, Double> avgSalary = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.averagingInt(Employee::salary)
    ));
~~~

Because averagingInt returns Double, the Map does not have type Integer, even though the mapper Employee::salary returns int.

## 5. mapping: Changing the Element Type Before Collecting

The **mapping(mapper, downstream)** collector is appropriate when you want to keep grouping from Employee, but inside each group only store names, IDs, or transformed values.

~~~java
Map<String, List<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.toList()
            )
        )
    );
~~~

Type at each step:

~~~text
Stream<Employee>
    |
groupingBy(Employee -> String)
    |
mapping(Employee -> String, toList())
    |
Map<String, List<String>>
~~~

**Not Map<String,List<Employee>>**, because mapping has transformed Employee into String before downstream toList.

To remove duplicate names and sort in lexicographical order:

~~~java
Map<String, TreeSet<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            TreeMap::new,
            Collectors.mapping(
                Employee::name,
                Collectors.toCollection(TreeSet::new)
            )
        )
    );
~~~

Here:

- TreeMap::new selects the **outer map** sorting department keys.
- TreeSet::new selects **each group's collection** sorting and deduplicating names.
- Result is Map<String,TreeSet<String>>. If declared as Map<String,Set<String>> with an appropriately inferred collector type, the Set interface can also be a valid general value type at the call site.

### 5.1. Do Not Confuse mapping with Stream.map

Another way to write:

~~~java
List<String> names = employees.stream()
    .map(Employee::name)
    .toList();
~~~

When map runs **before groupingBy**, the stream has already become Stream<String>, and Employee::department is no longer available for grouping unless department information is preserved in an intermediate type.

With groupingBy(Employee::department, mapping(Employee::name,...)), the classifier still sees Employee, while the downstream receives String. This is the fundamental difference when **you need to group by attribute A but collect attribute B**.

## 6. filtering: Filtering Inside a Group and Preserving Downstream Type

The **filtering(predicate, downstream)** collector was added in Java 9. It does not change the R type of the downstream; it selects which elements proceed into that collector.

~~~java
Map<String, Long> activeCounts =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.filtering(
                Employee::active,
                Collectors.counting()
            )
        )
    );
~~~

Types:

~~~text
filtering(Employee -> boolean, counting())
    -> Collector<Employee, ?, Long>

groupingBy(Employee -> String, filtering(...))
    -> Collector<Employee, ?, Map<String, Long>>
~~~

### 6.1. filtering Inside grouping Differs from Stream.filter Outside

Suppose the HR department has employees, but **no one is active**.

Approach A — filter beforehand:

~~~java
Map<String, Long> outerFiltered = employees.stream()
    .filter(Employee::active)
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

HR has no employees reaching groupingBy, so **the HR key may not appear** in the result.

Approach B — group first, filter in downstream:

~~~java
Map<String, Long> innerFiltered = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.filtering(
            Employee::active, Collectors.counting())
    ));
~~~

The classifier has already created the HR group from the source elements. Downstream filtering blocks inactive elements from reaching counting, so **HR can still appear with value 0**. This is an important semantic difference, not just a syntactic one.

Groups are created when the classifier sees a source element; if the source has no elements for a department, filtering does not create a key for a non-existent department on its own.

### 6.2. Combining filtering and mapping

~~~java
Map<String, List<String>> activeNames =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                    Employee::name, Collectors.toList())
            )
        )
    );
~~~

Inferring from the inside out:

1. toList() on String → List<String>.
2. mapping Employee → String, keeps result List<String>.
3. filtering keeps result List<String>.
4. grouping by department String → Map<String,List<String>>.

A group with all inactive employees can be present with an **empty List<String>**.

## 7. partitioningBy: Map<Boolean,D>, Not Map<K,D>

**partitioningBy(predicate)** splits data into two boolean sides: false and true. The default collector uses List<T> as the downstream:

~~~java
Map<Boolean, List<Employee>> byActive =
    employees.stream().collect(
        Collectors.partitioningBy(Employee::active)
    );
~~~

Changing the downstream to counting:

~~~java
Map<Boolean, Long> counts =
    employees.stream().collect(
        Collectors.partitioningBy(
            Employee::active,
            Collectors.counting()
        )
    );
~~~

Reading the types:

~~~text
Employee::active : Employee -> boolean
counting()       : Long
partitioningBy   : Map<Boolean, Long>
~~~

**The Boolean key is determined by partitioningBy**, independent of the predicate's return type; the predicate returns boolean to choose between the two sides.

Important characteristic: the Map returned by partitioningBy has **both false and true keys**, even if one side has no elements. With counting, the empty side has value 0; with toList, the empty side is an empty list.

~~~java
Map<Boolean, Long> counts = employees.stream().collect(
    Collectors.partitioningBy(Employee::active, Collectors.counting()));

System.out.println(counts.get(false));
System.out.println(counts.get(true));
~~~

You should not rely on **the iteration order of Map<Boolean,D>** when printing the whole Map; to ensure deterministic stdout order, access each key with get(false)/get(true).

### 7.1. Is groupingBy boolean Equivalent to partitioningBy?

~~~java
Map<Boolean, List<Employee>> groupByBoolean =
    employees.stream().collect(
        Collectors.groupingBy(Employee::active)
    );
~~~

In terms of value types, both can be Map<Boolean,List<Employee>>. However, **groupingBy does not necessarily create a key for the absent side**. partitioningBy is designed for two partitions and provides both keys.

Therefore, **identical Java types do not prove identical semantics**. You need to examine the collector structure and its contract.

## 8. Nested Grouping: Map<K1,Map<K2,R>>

A groupingBy whose downstream is another groupingBy produces a nested map:

~~~java
Map<String, Map<Boolean, List<Employee>>> nested =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.groupingBy(
                Employee::active
            )
        )
    );
~~~

How to read it:

1. Inner groupingBy(Employee::active) → Map<Boolean,List<Employee>>.
2. Outer groupingBy(Employee::department, inner) → Map<String,Map<Boolean,List<Employee>>>.

If we replace the inner collector with partitioningBy and name mapping:

~~~java
Map<String, Map<Boolean, List<String>>> nested =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                    Employee::name,
                    Collectors.toList()
                )
            )
        )
    );
~~~

Looking from the inside out:

~~~text
toList()                             -> List<String>
mapping(Employee::name, ...)         -> List<String>
partitioningBy(Employee::active,...) -> Map<Boolean,List<String>>
groupingBy(Employee::department,...) -> Map<String,Map<Boolean,List<String>>>
~~~

For each department that has input data, the inner partitioningBy always creates both false and true. For example, a department with only inactive employees will have an empty List<String> at key true.

### 8.1. Three Levels of Map Are Not Always Necessary

A multi-level collector can produce a very complex result:

~~~text
Map<String, Map<Boolean, Map<Integer, List<Employee>>>>
~~~

To understand it, read **from the leaves to the root**, identifying each classifier and its corresponding downstream. When the API becomes hard to read, you can:

- Create a collector variable with the full type.
- Create a record for important result groups.
- Split into named processing steps.
- Use a result DTO if a nested Map structure does not clearly express the business logic.

Do not try to optimize line count by forcing readers to decode an overly deep generic tree.

## 9. flatMapping: One Element Produces Multiple Downstream Values

Since Java 9, **flatMapping(mapper, downstream)** allows each input T to produce a Stream<U>, then collects all U elements into the downstream.

Suppose Employee has List<String> skills:

~~~java
record Employee(String department, String name,
                int salary, boolean active, List<String> skills) {}
~~~

Get the set of skills per department:

~~~java
Map<String, Set<String>> skillsByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.flatMapping(
                employee -> employee.skills().stream(),
                Collectors.toSet()
            )
        )
    );
~~~

Inference:

~~~text
T = Employee
mapper : Employee -> Stream<String>
downstream toSet() : Set<String>
outer grouping key : String
result : Map<String,Set<String>>
~~~

If you replace the downstream with **toCollection(TreeSet::new)**, the value type is TreeSet<String>, which can be used to print stable results in lexicographical order.

**Distinguishing mapping and flatMapping:**

- mapping(Employee::skills, toList()) will produce **List<List<String>>** for each group.
- flatMapping(e -> e.skills().stream(), toList()) produces a flattened **List<String>**.
- flatMapping(..., toSet()) produces a flattened **Set<String>** with duplicates removed by equality.

FlatMapping manages closing the child Stream returned by the mapper according to the API contract once processing finishes. Even so, the callback should not create I/O resources with complex ownership without clearly understanding their lifecycle.

## 10. collectingAndThen: Transforming R into Final Result RR

**collectingAndThen(downstream, finisher)** is an adapter that executes the child collector, then applies a Function to the result:

~~~java
Collector<T, A, RR> wrapped =
    Collectors.collectingAndThen(
        downstream,
        result -> finish(result)
    );
~~~

This is **academic illustrative code**, using T, A, RR, downstream, and finish that are not declared in a class; it is not a standalone runnable file.

The R type of the child collector can **differ** from the RR type of the finisher. For example, if you want each group to have an unmodifiable List<String>:

~~~java
Map<String, List<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.collectingAndThen(
                    Collectors.toList(),
                    List::copyOf
                )
            )
        )
    );
~~~

Inference:

~~~text
toList()                     -> List<String>
collectingAndThen(...copyOf) -> unmodifiable List<String>
mapping(Employee::name,...)  -> List<String>
groupingBy(department,...)   -> Map<String,List<String>>
~~~

The Java type of the result **is still List<String>**: Java generics **do not express immutability** of a List. Unmodifiability comes from the contract of List.copyOf, not from the type parameter.

With a finisher returning **a different type**, the type change is easier to see:

~~~java
Map<String, Integer> nameLengthsByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.collectingAndThen(
                Collectors.mapping(Employee::name, Collectors.toList()),
                names -> names.stream().mapToInt(String::length).sum()
            )
        )
    );
~~~

Here the downstream before the finisher is List<String>, but the finisher computes the sum of lengths and returns Integer, so the Map value is Integer.

### 10.1. Notes on null and Immutability

List.copyOf does not accept null elements; if mapping can return null, it must be handled beforehand. In addition, copyOf only protects **the list structure**; mutable objects inside (if any) can still change state.

Collectors.toList **does not guarantee a specific implementation or fixed mutability**, whereas Stream.toList() (Java 16+) guarantees returning an unmodifiable List. If you need a specific collection type or immutability at a boundary, choose the appropriate collector or finisher.

## 11. teeing: Two Downstreams Produce One Combined Result

Since Java 12, **teeing(downstream1, downstream2, merger)** distributes each element to **two collectors** and then combines the two results using a merger.

For example, counting employees and summing total salary into a record:

~~~java
record DeptStats(long count, int totalSalary) {}

Map<String, DeptStats> stats =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Employee::salary),
                DeptStats::new
            )
        )
    );
~~~

Reading the types layer by layer:

~~~text
counting()                 -> Long
summingInt(Employee::salary) -> Integer
DeptStats::new             : (Long, Integer) -> DeptStats
teeing(...)                -> DeptStats
groupingBy(department,...) -> Map<String,DeptStats>
~~~

**The two child collectors do not create Map<Long,Integer>.** They produce two values, and then the merger determines **the final R**. With a merger returning the DeptStats record, each group's value is DeptStats.

### 11.1. The Merger Can Return Another Type

~~~java
Map<String, String> labels = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingInt(Employee::salary),
            (count, total) -> count + " employees, salary=" + total
        )
    )
);
~~~

Because the merger returns String, the Map value is String.

When aggregated results need multiple data fields, a record is usually easier to understand than a formatted string. Consider int limits when using summingInt for money/salary; in production, summingLong or BigDecimal can be used depending on precision requirements.

## 12. summarizingInt, averagingInt, reducing, and Optional

There are collectors that return non-intuitive types if you only look at the input.

### 12.1. summarizingInt → IntSummaryStatistics

~~~java
Map<String, IntSummaryStatistics> salaries =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.summarizingInt(Employee::salary)
        )
    );
~~~

Each value is not Integer or List<Integer> but **IntSummaryStatistics**, which has the methods **getCount(), getSum(), getMin(), getMax(), getAverage()**. One value can provide multiple metrics.

If the group is non-empty, the statistics contain data; in groupingBy, a group key is only created if the classifier has seen an input element.

### 12.2. averagingInt → Double

~~~java
Map<String, Double> averages = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.averagingInt(Employee::salary)
    )
);
~~~

Even though Employee.salary is int, **the average can have a fractional part**, so the downstream returns Double. The result of an empty group is handled according to the corresponding collector's contract, for example averagingInt can yield 0.0 in a context where a downstream is given an empty group.

### 12.3. maxBy → Optional<Employee>

~~~java
Map<String, Optional<Employee>> highestPaid =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.maxBy(
                Comparator.comparingInt(Employee::salary)
            )
        )
    );
~~~

The maxBy downstream returns Optional<Employee>. Because groupingBy places the downstream result under each department key, the Map value type becomes Optional<Employee>.

You can use collectingAndThen to convert the value to another type:

~~~java
Map<String, String> topNames =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.collectingAndThen(
                Collectors.maxBy(
                    Comparator.comparingInt(Employee::salary)),
                employee -> employee.map(Employee::name).orElse("none")
            )
        )
    );
~~~

**An Optional of an empty group** can appear when a downstream like filtering removes all elements in the group; you must not blindly call Optional.get without checking.

### 12.4. Changing the Overload of reducing Changes the Type

~~~java
Collectors.reducing(Integer::sum)
~~~

This overload without an identity returns **Optional<Integer>** when collecting Integers.

~~~java
Collectors.reducing(0, Integer::sum)
~~~

The overload with an identity returns **Integer**. If you use mapping to convert Employee to salary first:

~~~java
Map<String, Integer> totals = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.mapping(
            Employee::salary,
            Collectors.reducing(0, Integer::sum)
        )
    )
);
~~~

The value type is Integer. However, when only summing an int field, **summingInt(Employee::salary)** is shorter and clearer.

## 13. Type Inference Pattern When Nesting Multiple Collectors

Suppose we need "each department has two groups: active and inactive; each group contains only employee names". Expression:

~~~java
Map<String, Map<Boolean, List<String>>> result =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                    Employee::name,
                    Collectors.toList()
                )
            )
        )
    );
~~~

We can trace from the inside out:

| Step | Result Type R After That Step |
| --- | --- |
| toList for String | List<String> |
| mapping(Employee::name, toList) | List<String> |
| partitioningBy(Employee::active, ...) | Map<Boolean,List<String>> |
| groupingBy(Employee::department, ...) | Map<String,Map<Boolean,List<String>>> |
| Stream<Employee>.collect(...) | Map<String,Map<Boolean,List<String>>> |

Note: **Employee::name returns String, but mapping is still a Collector for Employee input**. Only after mapping is applied does the downstream receive String. Similarly, partitioningBy does not lose the type information of the result collector; it just adds a Map<Boolean, ...> layer.

### 13.1. How to Read a Long Generic Type

~~~java
Map<String, Map<Boolean, List<String>>>
~~~

Break it down into words:

- Outer Map: **String department → ...**
- Inner Map: **Boolean active → ...**
- List at the leaf: **list of String names**.

If a Map is nested three or four levels deep, consider creating a record/DTO type that represents the domain instead of nesting Maps. Not because generic syntax is wrong, but because the deeper the type, the easier it is to misread which data belongs to which key.

## 14. Results Have Many Shapes but Consistent Rules

| Composed Collector | Predicted Result Type |
| --- | --- |
| groupingBy(department) | Map<String,List<Employee>> |
| groupingBy(department, counting()) | Map<String,Long> |
| groupingBy(department, averagingInt(salary)) | Map<String,Double> |
| groupingBy(department, summarizingInt(salary)) | Map<String,IntSummaryStatistics> |
| groupingBy(department, mapping(name,toSet())) | Map<String,Set<String>> |
| groupingBy(department, filtering(active,counting())) | Map<String,Long> |
| groupingBy(department, flatMapping(skills,toSet())) | Map<String,Set<String>> |
| partitioningBy(active) | Map<Boolean,List<Employee>> |
| partitioningBy(active,counting()) | Map<Boolean,Long> |
| groupingBy(department,partitioningBy(active)) | Map<String,Map<Boolean,List<Employee>>> |
| groupingBy(department,teeing(counting(),summingInt(salary),DeptStats::new)) | Map<String,DeptStats> |
| groupingBy(department,collectingAndThen(maxBy(bySalary),toName)) | Map<String,String> |

In the table, department, active, salary, name, and skills are **descriptive names for the corresponding functions/lambdas**, not standalone complete Java syntax. To verify, see the complete Java program in the next section.

## 15. Complete Java 17+ Program

The example uses an Employee record and data for five employees, grouped by department. We use **TreeMap** and **TreeSet** where stable ordering is needed so stdout is easy to verify, instead of relying on the unguaranteed default ordering of HashMap/HashSet.

Create the file **CollectorTypeDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class CollectorTypeDemo {
    record Employee(String department, String name,
                    int salary, boolean active, List<String> skills) {}
    record DeptStats(long count, int totalSalary) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("Tech", "An", 100, true, List.of("Java", "SQL")),
            new Employee("Tech", "Binh", 200, false, List.of("Java", "Cloud")),
            new Employee("Sales", "Chi", 80, true, List.of("CRM")),
            new Employee("Sales", "Dung", 120, true, List.of("CRM", "SQL")),
            new Employee("HR", "Em", 90, false, List.of("Excel"))
        );

        Map<String, Long> counts = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.counting()));
        System.out.println("counts=" + counts);

        Map<String, Long> activeCounts = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.filtering(Employee::active, Collectors.counting())));
        System.out.println("activeCounts=" + activeCounts);

        Map<String, TreeSet<String>> names = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.mapping(Employee::name,
                    Collectors.toCollection(TreeSet::new))));
        System.out.println("names=" + names);

        Map<Boolean, Long> activePartitions = employees.stream().collect(
            Collectors.partitioningBy(Employee::active, Collectors.counting()));
        System.out.println("partitions=false:" + activePartitions.get(false)
            + ",true:" + activePartitions.get(true));

        Map<String, DeptStats> stats = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingInt(Employee::salary),
                    DeptStats::new)));
        System.out.println("stats=" + stats);

        Map<String, TreeSet<String>> skills = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.flatMapping(
                    e -> e.skills().stream(),
                    Collectors.toCollection(TreeSet::new))));
        System.out.println("skills=" + skills);

        Map<String, List<String>> immutableNames = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.mapping(Employee::name,
                    Collectors.collectingAndThen(
                        Collectors.toList(), List::copyOf))));
        System.out.println("immutableNames=" + immutableNames);
        try {
            immutableNames.get("HR").add("Someone");
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutableList=true");
        }

        Map<String, Double> averages = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.averagingInt(Employee::salary)));
        System.out.println("averages=" + averages);

        Map<String, IntSummaryStatistics> summaries =
            employees.stream().collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.summarizingInt(Employee::salary)));
        System.out.println("hrMin=" + summaries.get("HR").getMin());

        Map<String, Map<Boolean, List<String>>> nested =
            employees.stream().collect(
                Collectors.groupingBy(Employee::department, TreeMap::new,
                    Collectors.partitioningBy(Employee::active,
                        Collectors.mapping(Employee::name, Collectors.toList()))));
        System.out.println("techInactive=" + nested.get("Tech").get(false));
        System.out.println("hrActive=" + nested.get("HR").get(true));

        Map<String, Long> upstreamFilter = employees.stream()
            .filter(Employee::active)
            .collect(Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.counting()));
        System.out.println("upstreamHasHR=" + upstreamFilter.containsKey("HR"));
        System.out.println("downstreamHasHR=" + activeCounts.containsKey("HR"));
    }
}
~~~

Compile and run (JDK 17+):

~~~bash
javac CollectorTypeDemo.java
java CollectorTypeDemo
~~~

**Verified stdout:**

~~~text
counts={HR=1, Sales=2, Tech=2}
activeCounts={HR=0, Sales=2, Tech=1}
names={HR=[Em], Sales=[Chi, Dung], Tech=[An, Binh]}
partitions=false:2,true:3
stats={HR=DeptStats[count=1, totalSalary=90], Sales=DeptStats[count=2, totalSalary=200], Tech=DeptStats[count=2, totalSalary=300]}
skills={HR=[Excel], Sales=[CRM, SQL], Tech=[Cloud, Java, SQL]}
immutableNames={HR=[Em], Sales=[Chi, Dung], Tech=[An, Binh]}
immutableList=true
averages={HR=90.0, Sales=100.0, Tech=150.0}
hrMin=90
techInactive=[Binh]
hrActive=[]
upstreamHasHR=false
downstreamHasHR=true
~~~

### 15.1. Reading Each Type from the Output

- **counts:** groupingBy(..., counting()) → Map<String,Long>. Long values are 1, 2, 2.
- **activeCounts:** groupingBy(..., filtering(active,counting())) → Map<String,Long>. HR still has a key, but with value 0.
- **names:** groupingBy(..., mapping(name,toCollection(TreeSet))) → Map<String,TreeSet<String>>. Names in each group are sorted.
- **partitions:** partitioningBy(active,counting()) → Map<Boolean,Long>. Has two values false=2 and true=3.
- **stats:** groupingBy(...,teeing(counting(),summingInt(salary),DeptStats::new)) → Map<String,DeptStats>. Each record contains two aggregated results.
- **skills:** flatMapping each List<String> skills into Stream<String>, then collecting into TreeSet<String>; the Map value is not List<List<String>>.
- **immutableNames:** mapping(name,collectingAndThen(toList,List::copyOf)) → unmodifiable List<String>. Testing add throws UnsupportedOperationException.
- **averages:** averagingInt returns Double, not Integer; HR 90.0, Sales 100.0, Tech 150.0.
- **hrMin:** summarizingInt returns IntSummaryStatistics, getMin() for HR = 90.
- **nested:** groupingBy(...,partitioningBy(...,mapping(name,toList()))) → Map<String,Map<Boolean,List<String>>>. Tech inactive has Binh; HR active has no one so the List is empty.
- **upstreamHasHR=false:** filtering active before grouping leaves HR with no elements to create a key.
- **downstreamHasHR=true:** filtering inside downstream still keeps the HR group with counting=0.

In the program, the outer Map is created with TreeMap to print keys HR, Sales, Tech in a verifiable order. For partitioningBy, instead of printing the map directly and relying on implementation ordering, the program accesses each Boolean key.

## 16. Common Type-Reading and Design Mistakes

### 16.1. Assigning the Wrong Type Because You Only Look at Stream<T>

~~~java
// WRONG: counting() returns Long, not List<Employee>.
Map<String, List<Employee>> counts =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department, Collectors.counting()));
~~~

Fix:

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department, Collectors.counting()));
~~~

The compiler will report a generic constraint error if the Map value type does not match the downstream. Read the child collector result first.

### 16.2. Confusing Count with Total Salary

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department, Collectors.counting()));
~~~

This is **the number of employees**. To get total salary:

~~~java
Map<String, Integer> totals = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.summingInt(Employee::salary)));
~~~

Naming a variable totalSalary does not turn a counting result into a sum. Check the specific downstream signature and mapper.

### 16.3. Assuming groupingBy Returns a TreeMap by Default

Default groupingBy(classifier,downstream) does not guarantee a concrete Map type or iteration order. If you need a TreeMap:

~~~java
Map<String, Long> ordered = employees.stream().collect(
    Collectors.groupingBy(Employee::department,
        TreeMap::new, Collectors.counting()));
~~~

Do not depend on Map.toString accidentally sorting keys on a particular run.

### 16.4. Confusing HashSet/TreeSet with List

Collectors.toSet does not guarantee iteration order; a set does not have positional iteration like a List. If sorting is needed, use toCollection(TreeSet::new) with Comparable keys or an appropriate Comparator.

### 16.5. Forgetting Downstream filtering Differs from Upstream filter

Placing Stream.filter(active) before grouping removes the keys of groups that have no remaining elements; Collectors.filtering(active,counting()) inside grouping can keep the key with 0. Both results are Map<String,Long>, but **they are not equivalent in their key sets**.

### 16.6. Assuming collectingAndThen Always Keeps Type R

A finisher can turn List<T> into Integer, Optional<T> into String, or statistics into a DTO. **The final type is the finisher's return type**, not necessarily the original downstream's type.

### 16.7. Assuming teeing Automatically Returns a Pair of Values

teeing requires a merger to produce **a single result R**. It does not automatically return a Pair, Map, or List; the final type is specified by the merger.

### 16.8. Assuming partitioningBy Only Contains Present Keys

partitioningBy has both false and true. When one side is empty, it still has the value produced by the downstream, such as 0, an empty List, or Optional.empty.

### 16.9. Using List.copyOf with null

List.copyOf does not accept null elements. If the mapper can return null, you must filter, replace, or explicitly design a value representing absence.

### 16.10. Confusing Declared Type with Runtime Class

~~~java
Map<String, List<String>> names = ...;
~~~

This declared type does not prove the outer map is HashMap or TreeMap, or that the inner list is ArrayList. Similarly, Map<String,Double> tells you the value type is Double, not guaranteeing order, rounding level, or that all keys are present.

### 16.11. Using Raw Types to Bypass the Compiler

~~~java
// Avoid: loses generic information.
Map grouped = employees.stream().collect(...);
~~~

This is an illustrative expression with ellipses, not a standalone compilable program. Raw types hide information about K and D, making bugs likely when retrieving values from the Map. Use **Map<String,Long>**, **Map<String,Set<String>>**, **var** when the expression is clear, or extract a collector variable with the full type.

### 16.12. A Concurrent-Friendly Collector Does Not Mean External Variables Are Safely Shared

Collectors.groupingBy and Collectors.groupingByConcurrent differ in contract and characteristics. You should not manually update an external mutable Map from a lambda to "build your own collector", especially with parallelStream. Use appropriate Collectors and read characteristics like CONCURRENT, UNORDERED, IDENTITY_FINISH when designing custom collectors.

Do not infer that Stream.parallel automatically turns every downstream List/Set into a concurrent collection for the caller to freely modify. Once collected, the result must still be used according to its mutability contract.

## 17. Procedure for Reading Generic Inference Errors

When the compiler reports it cannot infer type variables T, K, A, D, M, analyze in order:

1. **Identify the actual Stream<T>.** Employee or String? An earlier map on the Stream may have changed T.
2. **Identify the classifier T → K.** What is the Map key type?
3. **Identify whether the downstream receives T or U.** mapping changes element type, filtering keeps element type, flatMapping produces multiple U from one T.
4. **Identify the final R type of the downstream.** counting → Long, averagingInt → Double, toSet → Set<T>, teeing → merger result, collectingAndThen → finisher result.
5. **Wrap the outer Map.** groupingBy → Map<K,R>, partitioningBy → Map<Boolean,R>.
6. **Compare with the variable type on the left.** If incompatible, fix the collector logic or the variable type; do not rush to cast to a raw Map.
7. **Check null and mutability.** Even if generics are right, data can cause NullPointerException or UnsupportedOperationException.
8. **Ensure an ordering strategy.** If testing stdout, choose TreeMap/TreeSet or access keys explicitly instead of relying on HashMap iteration.

### 17.1. Does Using var Help?

~~~java
var grouped = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.counting()));
~~~

The compiler can infer the expression type without you writing Map<String,Long>. However, that **does not change the actual type** or fix a bad design. For public API logic or hard-to-read sections, declaring the full type sometimes helps readers quickly recognize the result structure.

### 17.2. Reading Types at Method Boundaries

A service method can declare:

~~~java
static Map<String, Long> countByDepartment(List<Employee> employees) {
    return employees.stream()
        .collect(Collectors.groupingBy(
            Employee::department, Collectors.counting()));
}
~~~

When business logic has a clear meaning, naming the method **countByDepartment** spares callers from having to decipher the entire collector tree at every call site.

## 18. Quick Inference Checklist

| Question | Suggested Answer |
| --- | --- |
| What element type does the Stream process? | T in Stream<T> |
| What key type does groupingBy use? | K is the classifier result |
| What key type does partitioningBy use? | Boolean |
| What does counting return? | Long |
| What does summingInt return? | Integer |
| What does averagingInt return? | Double |
| What does summarizingInt return? | IntSummaryStatistics |
| What does mapping change? | Converts input T to U for downstream |
| What does filtering change? | Keeps input type, selects elements entering downstream |
| What does flatMapping change? | Creates Stream<U> then feeds multiple U to downstream |
| What does collectingAndThen return? | Type after finisher |
| What does teeing return? | Merger result type |
| What type does groupingBy wrap into? | Map<K, downstream result> |
| What type does partitioningBy wrap into? | Map<Boolean, downstream result> |
| Are toList/toSet immutable? | Read the specific contract; do not guess from the type |
| Need deterministic result order? | Choose an appropriate mapFactory/collectionFactory |

## 19. Self-Check Questions

1. Why does groupingBy(Employee::department) give Map<String,List<Employee>>, while adding counting gives Map<String,Long>?
2. In Collector<T,A,R>, what does A describe and why is it usually unnecessary to state when reading the collect result?
3. What input type does mapping(Employee::name,toSet()) accept and what result type does it return?
4. How does groupingBy(department,mapping(name,toList())) differ from Stream.map(name) before groupingBy(department)?
5. Why can filtering(active,counting()) inside groupingBy produce HR=0, whereas Stream.filter(active) before groupingBy has no HR key?
6. What type does partitioningBy(active,counting()) return? Are both false and true present when there are no active employees?
7. How many Map layers does groupingBy(department,partitioningBy(active,mapping(name,toList()))) have, and what does each key mean?
8. How does flatMapping(e -> e.skills().stream(),toSet()) differ from mapping(Employee::skills,toList()) in type and List depth?
9. Given teeing(counting(),summingInt(salary),DeptStats::new), what is the value type of the grouped Map?
10. Does collectingAndThen(toList(),List::copyOf) change the generic type or only the unmodifiability contract?
11. Does summarizingInt(salary) return IntSummaryStatistics or Integer? Which method accesses the average?
12. maxBy(comparator) inside groupingBy returns Map<K,Optional<T>>; why does Optional appear?
13. If the finisher of collectingAndThen returns String, why can the final Map value be String even though the downstream produces a List?
14. In the code grouping by department, does mapFactory TreeMap::new determine the outer map or the inner list?
15. When Java reports incompatible types between Map<String,List<Employee>> and Map<String,Long>, which part of the collector do you check first?
16. Why can two results with the same type Map<Boolean,List<T>> from groupingBy(Boolean) and partitioningBy differ in their key sets?
17. Why does a Map<String,List<String>> type not prove the inner List is mutable?
18. To ensure grouped results have a stable print order, at which layer should you specify the factory?
19. If a Stream has become Stream<String> after map, why is Employee::department no longer a valid classifier?
20. When nesting another groupingBy collector, how do you update the generic type Map<K1,Map<K2,R>> without guessing?

**Conclusion:** To read the result type of a composed collector, first identify **Stream<T>**, next identify **the R type of the deepest collector**, then sequentially apply **mapping/filtering/flatMapping**, **collectingAndThen/teeing**, and finally wrap with **groupingBy → Map<K,R>** or **partitioningBy → Map<Boolean,R>**. Do not confuse the source element type with the value type of the resulting Map. Also remember the differences between outer/inner group filtering, Boolean partitioning, Optional, immutability, and collection ordering so your code both compiles cleanly and has the right semantics.