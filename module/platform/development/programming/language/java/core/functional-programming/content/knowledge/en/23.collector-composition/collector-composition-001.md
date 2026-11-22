# counting(), summingInt() and averagingDouble() in Java Collectors

## 1. Lesson Objectives

In an application with a list of products, invoices, or scores, we often need three basic types of statistics:

- **Count** how many elements satisfy a condition.
- **Sum** an integer quantity from each element, such as the quantity of items sold.
- **Calculate the average** of a numeric quantity, such as the average selling price of each product type.

Java provides three factory methods in **java.util.stream.Collectors** to create the corresponding **Collector**:

~~~java
Collectors.counting()
Collectors.summingInt(ToIntFunction<? super T> mapper)
Collectors.averagingDouble(ToDoubleFunction<? super T> mapper)
~~~

These Collectors are useful when combined with **Stream.collect(...)**, especially as a **downstream collector** in **groupingBy**, **partitioningBy**, **mapping**, **filtering**, or **teeing**.

After this lesson, you will be able to:

1. Understand the return type of each Collector and how to use them directly.
2. Recognize when to use **Stream.count()**, **IntStream.sum()**, or **average()** instead of a Collector.
3. Compute statistics per group using **groupingBy(key, downstream)**.
4. Distinguish total value from the average over the number of elements, and handle **empty streams** properly.
5. Avoid **int** overflow, unit mismatches, null data, floating-point precision errors, and false assumptions about ordering.
6. Design pure, testable mappers and use them safely in parallel streams.

## 2. What is a Collector?

**Collector<T, A, R>** describes how to collect elements of type T into a result R, through an intermediate accumulation state A. The Collector API defines components such as **supplier**, **accumulator**, **combiner**, **finisher**, and **characteristics**.

Usually, you do not need to implement Collector yourself. Java provides factory methods in **Collectors**.

Example:

~~~java
List<String> values = List.of("Java", "Go", "C");

long total = values.stream()
        .collect(Collectors.counting());

System.out.println(total); // 3
~~~

This is an illustrative snippet inside a method with **List** and **Collectors** imported.

Data flow:

~~~text
List<String> (source)
    |
    v
stream()
    |
    v
filter(...) / map(...) (if needed)
    |
    v
collect(Collectors.counting())
    |
    v
Long (result)
~~~

**collect** is a terminal operation: when called, the pipeline is evaluated enough to return the result. **Collectors.counting()** only creates a Collector; it does not start iterating over the data on its own.

### 2.1. Three Collectors Describing One Type of Aggregation

| Collector | Required input value | Result type | Empty stream |
| --- | --- | --- | --- |
| **counting()** | Only needs elements to exist | **Long** | **0L** |
| **summingInt(mapper)** | Mapper produces **int** | **Integer** | **0** |
| **averagingDouble(mapper)** | Mapper produces **double** | **Double** | **0.0** |

Note: The types shown above are the **boxed** results of the Collector when used with Stream<T>; when assigned to a primitive variable, Java performs unboxing where appropriate.

**Stream.count()** directly returns primitive **long**. **IntStream.sum()** returns primitive **int**. **DoubleStream.average()** returns **OptionalDouble**. Those are different APIs; do not assume they all have the same type or the same empty-collection handling.

## 3. counting(): counting the number of elements

Factory method:

~~~java
static <T> Collector<T, ?, Long> counting()
~~~

Usage:

~~~java
long numberOfWords = List.of("a", "b", "c").stream()
        .collect(Collectors.counting());

System.out.println(numberOfWords); // 3
~~~

**counting** counts **the number of elements that actually enter the collector**, without distinguishing element contents on its own.

### 3.1. Counting after filter

~~~java
List<Integer> values = List.of(-2, 0, 3, 4, 7);

long positives = values.stream()
        .filter(value -> value > 0)
        .collect(Collectors.counting());

System.out.println(positives); // 3
~~~

Here, three values **3, 4, 7** pass through the filter, so the count result is 3.

**Counting elements** is different from **counting distinct value types**. If you want to count distinct values, clarify the semantics and you can use **distinct()** before counting:

~~~java
long unique = List.of("A", "A", "B").stream()
        .distinct()
        .collect(Collectors.counting());

System.out.println(unique); // 2
~~~

### 3.2. counting and Stream.count()

If you only need the number of elements in the entire stream, the expression:

~~~java
long n = source.stream().count();
~~~

is usually more concise than:

~~~java
long n = source.stream().collect(Collectors.counting());
~~~

Both return the number of elements according to the contract. **counting()** is especially valuable when used as a downstream collector, for example counting per group:

~~~java
Map<String, Long> counts = items.stream()
        .collect(Collectors.groupingBy(
                Item::category,
                Collectors.counting()));
~~~

This is a snippet with a suitable **Item** type and **items** variable; a complete program will be shown below.

### 3.3. Do not use callbacks to infer traversal count

**Stream.count()** can take advantage of a known source size without executing certain preceding steps when the count result is unaffected. For example:

~~~java
long n = List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .count();
~~~

You must not assume three printed lines from **peek** are guaranteed. The count result is still 3, but the Stream API allows valid optimizations.

**Collectors.counting()** describes an aggregation; you should also not place mandatory business actions inside a mapper, filter, or peek and assume every callback will definitely run exactly once. Counting and performing actions with side effects are two separate responsibilities.

## 4. summingInt(): summing int values extracted from each element

Factory method:

~~~java
static <T> Collector<T, ?, Integer> summingInt(
        ToIntFunction<? super T> mapper)
~~~

The **mapper** argument takes an element T and produces an **int**. The Collector sums those int results and returns **Integer**.

~~~java
record Order(String code, int quantity) { }

List<Order> orders = List.of(
        new Order("A", 2),
        new Order("B", 3),
        new Order("C", 4)
);

int units = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));

System.out.println(units); // 9
~~~

This is an illustrative snippet that needs to be placed in a class/method with List and Collectors imported. The record Order has a compiler-generated **quantity()** accessor.

### 4.1. The summed values are the mapper results

With **summingInt(Order::quantity)**, Order objects are not summed directly. Java calls the mapper to get the quantity:

~~~text
Order("A",2) -> mapper -> 2
Order("B",3) -> mapper -> 3
Order("C",4) -> mapper -> 4
                           |
                           v
                         sum = 9
~~~

If the mapper returns a different value, the collector sums **that value**. For example:

~~~java
int doubleUnits = orders.stream()
        .collect(Collectors.summingInt(
                order -> order.quantity() * 2));

System.out.println(doubleUnits); // 18
~~~

Each quantity is multiplied by 2 before summing. Before coding, you need to determine the **unit of the quantity**: number of items, monetary amount in the smallest unit, minutes, points, etc. Summing values with inconsistent units is a business logic bug even if the code compiles.

### 4.2. Difference from IntStream.sum()

If you only need a direct sum on a stream already converted to a primitive stream:

~~~java
int units = orders.stream()
        .mapToInt(Order::quantity)
        .sum();
~~~

The result matches using **Collectors.summingInt** in the example. This approach expresses primitive addition directly and is usually simpler when no downstream collector is needed.

Use **summingInt()** when you need a structure like:

~~~java
Map<String, Integer> unitsByCategory = orders.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.summingInt(Order::quantity)));
~~~

This snippet assumes the Order type has an additional **category()** accessor and Map/Collectors are imported; it is not the two-field Order record from example 4.1.

### 4.3. Integer overflow

**summingInt** returns Integer and performs the sum in the **int** domain. If the true sum exceeds the range from **Integer.MIN_VALUE** to **Integer.MAX_VALUE**, the result can **overflow**.

~~~java
int total = Stream.of(Integer.MAX_VALUE, 1)
        .collect(Collectors.summingInt(Integer::intValue));

System.out.println(total); // -2147483648
~~~

This is signed int integer behavior according to Java's overflow rules; it is not the desired mathematical sum.

**Do not use summingInt for sums that can exceed the int range.** Choose **Collectors.summingLong(mapper)**, **mapToLong(...).sum()** if the long domain is sufficient, or design the sum with **BigInteger/BigDecimal** and appropriate overflow-control rules.

For total monetary amounts in VND, the fact that each item has an int price **does not mean** the revenue of the entire system also fits in an int.

### 4.4. Multiplication inside the mapper can also overflow

If computing **quantity × unit price** and then summing:

~~~java
Collectors.summingInt(order ->
        order.quantity() * order.unitPriceVnd())
~~~

**The multiplication** can overflow **before summing**. If you need an accurate amount within the long domain:

~~~java
Collectors.summingLong(order ->
        Math.multiplyExact(
                (long) order.quantity(),
                (long) order.unitPriceVnd()))
~~~

This snippet assumes the Order type has the appropriate accessors. **Math.multiplyExact** checks for overflow when multiplying longs, but the total summation in summingLong can still overflow if it exceeds the long domain. For currency with fractional parts, consider **BigDecimal** according to the defined rounding policy and unit.

## 5. averagingDouble(): computing the average from double values

Factory method:

~~~java
static <T> Collector<T, ?, Double> averagingDouble(
        ToDoubleFunction<? super T> mapper)
~~~

Each element is converted by the mapper into a **double**, and then the Collector computes the **arithmetic mean**.

~~~java
List<Integer> scores = List.of(8, 9, 10);

double average = scores.stream()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

System.out.println(average); // 9.0
~~~

The result is 9.0 because (8 + 9 + 10)/3 = 9.

### 5.1. Average of the elements entering the collector

Example:

~~~java
record Product(String name, double price) { }

List<Product> products = List.of(
        new Product("A", 10.0),
        new Product("B", 20.0),
        new Product("C", 30.0)
);

double averagePrice = products.stream()
        .collect(Collectors.averagingDouble(Product::price));

System.out.println(averagePrice); // 20.0
~~~

This Collector returns the **simple arithmetic mean** over the selected elements; every element has equal weight.

**Do not confuse this with a weighted average.** For example, the average price of transactions weighted by quantity sold is not necessarily equal to the average unit price per line item. If 1 item is sold at price 10 and 100 items at price 20, the average unit price per line is 15, whereas the average price per item is **(1×10 + 100×20)/(1+100)**.

To compute a weighted average, you need the sum of **(weight × value)** and the sum of weights, then divide in a controlled manner. A simple **averagingDouble(Product::price)** does not perform weighting logic.

### 5.2. Empty stream returns 0.0

~~~java
double avg = Stream.<Integer>empty()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

System.out.println(avg); // 0.0
~~~

**0.0 here is the Collector's result convention when there is no data**, not an observed mathematical average.

If the business logic must distinguish between **no observations** and **an actual average of 0**, do not rely solely on the Double result. You can combine **counting()** with averagingDouble, or use **DoubleStream.average()** which returns **OptionalDouble**.

### 5.3. Difference from DoubleStream.average()

~~~java
OptionalDouble average = DoubleStream.of(4.0, 6.0)
        .average();

System.out.println(average.orElse(-1.0)); // 5.0

OptionalDouble noAverage = DoubleStream.empty()
        .average();

System.out.println(noAverage.isEmpty()); // true
~~~

**Collectors.averagingDouble** returns **Double**, with **0.0** for empty. **DoubleStream.average** returns **OptionalDouble**, with **empty** for empty. Choose the API that matches the missing-data contract the calling layer needs to handle.

### 5.4. Floating-point error and calculation order

**double** arithmetic follows IEEE 754 and has precision limits. The contract of **averagingDouble** does not guarantee an exact result in all cases, and the value may vary slightly when the calculation order changes, especially in parallel processing.

For example: **0.1 + 0.2** does not have an exact binary representation, so you should not compare a double average to an expected value using **==** if the business logic requires decimal precision.

**Special note:** if the data contains **NaN** or **Infinity**, the average result may be NaN/Infinity according to floating-point arithmetic. A single NaN value often makes the aggregated result unusable; define a data validation policy before aggregating.

For monetary amounts, prefer exact arithmetic with **BigDecimal** along with a specified **MathContext/RoundingMode**. **averagingDouble** is suitable for many measurements, statistics, and scenarios where floating-point error is acceptable.

## 6. Choosing the Right API for the Goal

| Need | More direct approach | When to use a Collector |
| --- | --- | --- |
| Count all elements | **stream.count()** | **Collectors.counting()** when used as downstream |
| Count elements matching a condition | **filter(...).count()** | **filtering(..., counting())** in grouping |
| Sum integers | **mapToInt(...).sum()** | **summingInt(mapper)** in grouping/teeing |
| Sum longs | **mapToLong(...).sum()** | **summingLong(mapper)** in grouping |
| Compute double average | **mapToDouble(...).average()** | **averagingDouble(mapper)** when Double/downstream is needed |
| Need count, sum, min, max, avg together | **summaryStatistics()** | **summarizingInt/Long/Double**, teeing, or composite collector |

There is no rule that "using Stream requires using Collectors". Choose the approach that **clearly expresses intent** and returns the result type the caller needs.

## 7. groupingBy: statistics per group

Suppose you need statistics on order count, item quantity, and average unit price for each category. **groupingBy** classifies elements by key; the **downstream collector** performs aggregation within each group.

### 7.1. Count per group

~~~java
Map<String, Long> countByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.counting()));
~~~

This is an illustrative snippet based on a Sale type with category() and a sales list. Each category will have a Long value counting the number of records belonging to that group.

### 7.2. Total quantity per group

~~~java
Map<String, Integer> unitsByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.summingInt(Sale::quantity)));
~~~

The quantity values of each Sale in the same category are summed. Do not call this "order count": **counting counts records**, while **summingInt(Sale::quantity) sums items**.

### 7.3. Average unit price per group

~~~java
Map<String, Double> averagePriceByCategory = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.averagingDouble(Sale::unitPriceVnd)));
~~~

This is the average **unit price of each record** in the group, unweighted by quantity. For a group with multiple records of the same product but different quantity values, choose the exact average definition required by the business logic.

### 7.4. Map ordering

The default groupingBy overload **does not guarantee iteration order of entries in the returned Map**. If you want display output with natural key ordering, use the overload with **mapFactory**:

~~~java
Map<String, Long> ordered = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.counting()));
~~~

You need to import Map, TreeMap, Collectors and have the Sale type. **TreeMap** keeps keys in comparison order; this ordering is for **keys**, not the order of elements within each group.

Standard **groupingBy** does not allow the classifier to return null; if category can be null, decide on a handling policy or normalize before grouping. Do not use null as an arbitrary key and treat it as a valid group if the API rejects it.

## 8. partitioningBy: statistics by true/false condition

A special form of grouping is **partitioning by boolean**:

~~~java
Map<Boolean, Long> byPaid = sales.stream()
        .collect(Collectors.partitioningBy(
                Sale::paid,
                Collectors.counting()));
~~~

The result has boolean keys **true** and **false**, corresponding to the number of paid and unpaid orders.

In conditional statistics, **partitioningBy** often expresses intent more directly than groupingBy(s -> s.paid()) and can ensure you always see both sides of the partition, even if one side has a count of 0.

**Do not rely on the print order of HashMap/Maps without an ordering contract.** To generate a deterministic report, read **byPaid.get(true)** and **byPaid.get(false)** separately or sort the keys before presenting.

## 9. filtering downstream vs. filter before groupingBy

This is an important scenario when you need to keep all groups while computing statistics only on elements that satisfy a condition.

### 9.1. Filtering before groupingBy

~~~java
Map<String, Long> paidOnly = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.counting()));
~~~

If a category only has unpaid orders, that category **does not appear** in the resulting Map, because it was filtered out before grouping.

### 9.2. Filtering in downstream with Collectors.filtering

~~~java
Map<String, Long> paidCounts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting())));
~~~

**Collectors.filtering(predicate, downstream)** has been available since Java 9. In this approach, groups are formed first, and then elements within each group pass through the filtering downstream. A category with only unpaid orders can still appear with a count of **0L** instead of disappearing.

**Business meaning example:** a dashboard needs to display every category, including those with no paid orders, to report a 0 instead of missing an entire row.

Do not automatically replace one style with the other if **preserving keys with a value of 0** is meaningful to the user.

## 10. Combining Collectors with teeing

Since Java 12, **Collectors.teeing** allows taking **one stream of elements** and aggregating with two downstream collectors, then combining the two results into one object.

Example of counting orders and summing total quantity:

~~~java
record Totals(long orders, int units) { }

Totals totals = sales.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Sale::quantity),
                Totals::new));
~~~

This snippet needs to be placed in a class/method with record Totals, type Sale, and Collectors imported. **counting** produces Long; **summingInt** produces Integer; the **Totals(long,int)** constructor receives them via unboxing.

With the same data stream, teeing produces **two metrics** in a single terminal operation, without requiring the caller to run two separate pipelines. One downside is that three or more metrics can make **nested teeing** hard to read. In that case, **summarizingInt** or a carefully designed custom collector may be clearer.

### 10.1. Comparison with summarizingInt

~~~java
IntSummaryStatistics stats = sales.stream()
        .collect(Collectors.summarizingInt(Sale::quantity));

System.out.println(stats.getCount());
System.out.println(stats.getSum());
System.out.println(stats.getAverage());
~~~

**Collectors.summarizingInt** returns **IntSummaryStatistics**, containing count, sum, min, max, and average. Choose it when those are the exact metrics needed and you want to avoid combining multiple collectors unnecessarily.

One thing to note: the sum of **IntSummaryStatistics** is represented as **long**, whereas **summingInt** results in Integer/int. This difference can be important if the dataset is large and the total quantity exceeds the int range.

## 11. Complete Java 17 Example

We have five sales records. Each record contains:

- **id**: record ID.
- **category**: product group.
- **quantity**: number of items in the transaction.
- **unitPriceVnd**: unit price in VND, using int values for this small example.
- **paid**: payment status.

Problem statement:

1. Count the total number of records.
2. Sum the total item quantity.
3. Calculate the average quantity per record.
4. Calculate total revenue as **quantity × unitPriceVnd**.
5. Calculate the average unit price per record.
6. Compute the three metrics per category, sorting keys for deterministic output.
7. Count paid and unpaid transactions.
8. Count **paid** transactions per category using downstream filtering.
9. Demonstrate count/sum/avg on an empty stream and teeing count+sum.

Create file **CollectorStatisticsDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorStatisticsDemo {
    record Sale(
            String id,
            String category,
            int quantity,
            int unitPriceVnd,
            boolean paid) { }

    record Totals(long orders, int units) { }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", "Books", 2, 10_000, true),
                new Sale("B", "Books", 1, 16_000, false),
                new Sale("C", "Games", 3, 8_000, true),
                new Sale("D", "Games", 0, 12_000, true),
                new Sale("E", "Books", 4, 22_000, true)
        );

        long count = sales.stream()
                .collect(Collectors.counting());

        int units = sales.stream()
                .collect(Collectors.summingInt(Sale::quantity));

        double averageUnits = sales.stream()
                .collect(Collectors.averagingDouble(
                        sale -> sale.quantity()));

        int revenue = sales.stream()
                .collect(Collectors.summingInt(
                        sale -> Math.multiplyExact(
                                sale.quantity(),
                                sale.unitPriceVnd())));

        double averageUnitPrice = sales.stream()
                .collect(Collectors.averagingDouble(
                        Sale::unitPriceVnd));

        System.out.println("count: " + count);
        System.out.println("units: " + units);
        System.out.println("average units: " + averageUnits);
        System.out.println("revenue: " + revenue);
        System.out.println("average price: " + averageUnitPrice);

        Map<String, Long> countsByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.counting()));

        Map<String, Integer> unitsByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::quantity)));

        Map<String, Double> averagePricesByCategory =
                sales.stream()
                        .collect(Collectors.groupingBy(
                                Sale::category,
                                TreeMap::new,
                                Collectors.averagingDouble(
                                        Sale::unitPriceVnd)));

        System.out.println("group counts: " + countsByCategory);
        System.out.println("group units: " + unitsByCategory);
        System.out.println("group avg prices: "
                + averagePricesByCategory);

        Map<Boolean, Long> paidCounts = sales.stream()
                .collect(Collectors.partitioningBy(
                        Sale::paid,
                        Collectors.counting()));

        System.out.println("paid: " + paidCounts.get(true)
                + ", unpaid: " + paidCounts.get(false));

        Map<String, Long> paidByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.filtering(
                                Sale::paid,
                                Collectors.counting())));

        System.out.println("paid by category: "
                + paidByCategory);

        Totals totals = sales.stream()
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::quantity),
                        Totals::new));

        System.out.println("totals: " + totals);

        long emptyCount = Stream.<Sale>empty()
                .collect(Collectors.counting());

        int emptySum = Stream.<Sale>empty()
                .collect(Collectors.summingInt(
                        Sale::quantity));

        double emptyAverage = Stream.<Sale>empty()
                .collect(Collectors.averagingDouble(
                        Sale::unitPriceVnd));

        System.out.println("empty: " + emptyCount
                + "/" + emptySum + "/" + emptyAverage);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CollectorStatisticsDemo.java
java CollectorStatisticsDemo
~~~

**Exact output:**

~~~text
count: 5
units: 10
average units: 2.0
revenue: 148000
average price: 13600.0
group counts: {Books=3, Games=2}
group units: {Books=7, Games=3}
group avg prices: {Books=16000.0, Games=10000.0}
paid: 4, unpaid: 1
paid by category: {Books=2, Games=2}
totals: Totals[orders=5, units=10]
empty: 0/0/0.0
~~~

### 11.1. Manual Calculation Verification

Total quantity:

~~~text
Books: A(2) + B(1) + E(4) = 7
Games: C(3) + D(0)        = 3
Total quantity            = 10
~~~

Total revenue in VND:

~~~text
A: 2 × 10.000 =  20.000
B: 1 × 16.000 =  16.000
C: 3 ×  8.000 =  24.000
D: 0 × 12.000 =       0
E: 4 × 22.000 =  88.000
------------------------
Total            148.000
~~~

Average unit price across the five **records**:

~~~text
(10.000 + 16.000 + 8.000 + 12.000 + 22.000) / 5
= 68.000 / 5
= 13.600
~~~

By group:

- **Books** has 3 records, 7 items; average price per record = (10.000 + 16.000 + 22.000)/3 = **16.000**.
- **Games** has 2 records, 3 items; average price per record = (8.000 + 12.000)/2 = **10.000**.
- **paid** has A, C, D, E → 4 records; **unpaid** has B → 1 record.
- By category, Books has A/E paid (2), Games has C/D paid (2).

The average price result for each group is printed as a Double with a **.0** suffix. This is due to the return type of **averagingDouble**, not because the monetary data was converted to an exact financial decimal type.

### 11.2. Why use TreeMap in the example?

**groupingBy(..., TreeMap::new, downstream)** places the key **Books** before **Games**, so exact stdout can be stated. If you use the default two-parameter groupingBy, you should not guarantee the order when printing a regular Map.

### 11.3. Why is revenue not item quantity?

**summingInt(Sale::quantity)** sums **item count**. **summingInt(sale -> quantity × unitPrice)** sums **revenue**. The two summations differ in the mapper and **unit**. A program can return a mathematically correct number yet produce a wrong report if the mapper reads the wrong field.

### 11.4. Why does an empty stream return 0/0/0.0?

This is the contract of the three Collectors:

- Counting: **0L**.
- SummingInt: **0**.
- AveragingDouble: **0.0**.

For averages on empty data, you must have a business-layer policy if you want to display **“no data”** instead of 0.0.

## 12. Distinguishing Transaction Count, Total Items, and Weighted Average

A real-world system often has three concepts:

| Metric | Calculation pattern | Meaning |
| --- | --- | --- |
| Transaction count | **counting()** | Each record is counted once |
| Total items | **summingInt(Sale::quantity)** | Sum of quantity across records |
| Average unit price per line | **averagingDouble(Sale::unitPriceVnd)** | Unweighted average |
| Weighted average unit price per item | **Sum(qty × unitPrice) / Sum(qty)** | Average weighted by quantity |

In the example data:

- Average **unit price per line** = 13.600 VND.
- Total revenue = 148.000 VND.
- Total items = 10.
- Weighted average **unit price per item** = **14.800 VND**, different from 13.600.

If a report requires the **average per item**, do not use **averagingDouble(Sale::unitPriceVnd)** alone. Compute the numerator and denominator properly and then divide, checking for the case where total quantity is 0.

**Weighted average unit price per item** can also differ from “actual selling price” if discounts, refunds, or taxes are present. Clarify the business rules before writing the mapper.

## 13. Controlling Errors and Correctness

### 13.1. The Long of counting is not infinite

**Collectors.counting()** returns Long to have a wider range than int, but **long** is still finite. In extremely large systems, you need to define data limits and storage. Most typical Java problems do not reach the long limit, but “Long” does not mean the value can never overflow in every scenario.

### 13.2. summingInt and summingLong

**summingInt** is suitable when you are certain the sum fits within the int range. For large transaction counts, revenue, or measurements that may exceed the limit, use **summingLong** with a mapper converting to long:

~~~java
long total = sales.stream()
        .collect(Collectors.summingLong(
                sale -> (long) sale.quantity()));
~~~

This is a snippet based on the existing Sale record. For multiplication, cast to long **before multiplying**:

~~~java
long revenue = sales.stream()
        .collect(Collectors.summingLong(
                sale -> (long) sale.quantity()
                        * sale.unitPriceVnd()));
~~~

Do not perform int multiplication first and then cast to long if you need to avoid int multiplication overflow.

**summingLong can still overflow**; if the sum exceeds the long range or you need exact overflow control, use a more appropriate numeric model rather than assuming every sum automatically detects overflow.

### 13.3. Double is not for exact currency

**averagingDouble** makes sense for statistics, not as an exact currency engine. For money with fractional units, multiple currencies, or mandatory rounding rules:

- Choose a clear monetary representation (e.g., integer in the smallest unit, or BigDecimal).
- Define scale, rounding, and when rounding occurs.
- Separate item count, total amount, and weighted average.
- Test cases with 0 records, negative numbers, refunds, and invalid data.

Do not choose Double just because a Collector is named “averaging”.

### 13.4. NaN, Infinity, and invalid data

If the mapper returns **Double.NaN**, **POSITIVE_INFINITY**, or **NEGATIVE_INFINITY**, the average result may not be useful. Decide whether that data should be rejected, filtered out, logged as an error, or grouped separately.

Example when you want to compute statistics only on finite double values:

~~~java
double mean = measurements.stream()
        .mapToDouble(Measurement::value)
        .filter(Double::isFinite)
        .average()
        .orElse(Double.NaN);
~~~

This is a snippet in a context with a Measurement type and a measurements list; it is not a standalone file. **Double::isFinite** fits DoubleStream.filter because it is a static method taking a primitive double and returning boolean.

**Note:** filtering out invalid values changes **the average denominator**; be transparent in reports that those records were excluded.

## 14. Do not use mappers with side effects or mutable state

A suitable mapper is a read/calculation from the element and stable configuration:

~~~java
Collectors.summingInt(Sale::quantity)
Collectors.averagingDouble(Sale::unitPriceVnd)
~~~

A mapper with side effects or reading a mutable counter can produce wrong results depending on invocation order:

~~~java
AtomicInteger sequence = new AtomicInteger();

ToIntFunction<Sale> unstable =
        sale -> sequence.incrementAndGet();
~~~

This is an illustrative snippet with Sale, AtomicInteger, and ToIntFunction in context. **unstable** returns the invocation order instead of the quantity sold; when running in parallel, the callback order can differ and the metrics no longer reflect Sale.

**AtomicInteger** makes the increment atomic, but it does not make the mapper **stateless** or business-correct. Do not use callbacks during aggregation to update a global counter that must be accurate according to business semantics.

### 14.1. Non-interference with the source

Do not modify the source list or Sale fields from the mapper:

~~~java
// Counter-example, do not use in production:
// Collectors.summingInt(sale -> {
//     sale.changeQuantity();
//     return sale.quantity();
// });
~~~

If source objects are mutable, concurrent reads and writes while the pipeline is traversing can cause inconsistent data. Create an appropriate snapshot or use immutable records and manage data ownership clearly.

## 15. Parallel streams and associativity

Standard Collectors are designed to work within the reduction framework. However, for the calculation to be semantically valid, mappers must be non-interfering and not depend on mutable state. Specifically:

- **counting** counts elements and is generally stable for deterministic source data.
- **summingInt** performs int addition according to integer rules; overflow remains a business risk whether executed sequentially or in parallel.
- **averagingDouble** is subject to floating-point error; the order in which subtotals are combined can change the final result in the lower digits.
- **groupingBy** does not guarantee Map ordering without a mapFactory; **groupingByConcurrent** has a different contract and should not be used if you need key ordering or encounter order that it does not guarantee.
- **Do not manually use a shared mutable Map or accumulator to sum results inside forEach** when Collectors already provide a safer aggregation path.

The following example is not a good way to aggregate:

~~~java
Map<String, Integer> totals = new HashMap<>();

sales.parallelStream().forEach(sale ->
        totals.merge(sale.category(),
                sale.quantity(), Integer::sum));
~~~

This is a counter-example with a regular HashMap: updating from multiple threads is not thread-safe. Even when using ConcurrentHashMap, you must clarify associativity, overflow, ordering, and the contract of any side effects. If you only need total quantity per category, using **groupingBy(..., summingInt(...))** expresses the goal properly and is easier to test.

## 16. Some Advanced Options

### 16.1. Sum and average of long

If the mapper produces long, there are collectors:

~~~java
Collectors.summingLong(ToLongFunction<? super T> mapper)
Collectors.averagingLong(ToLongFunction<? super T> mapper)
~~~

**summingLong** returns Long, and **averagingLong** returns Double. They can be more suitable when the input is long; however, the double average result still has precision limits.

### 16.2. Sum and average of double

~~~java
Collectors.summingDouble(ToDoubleFunction<? super T> mapper)
Collectors.averagingDouble(ToDoubleFunction<? super T> mapper)
~~~

These two Collectors handle double data, unlike summingInt which sums int. If you need an integer sum from elements, do not choose summingDouble just because the original data has int and the compiler can cast to double: casting can lose precision for very large numbers.

### 16.3. Creating a Map containing only the needed metrics

If the application only needs a **Long** count of records per group, do not collect the entire List<Sale> and then call size() unless you also need to store the list. **groupingBy(category, counting())** can reduce the amount of data retained and express the requirement accurately.

Conversely, if you genuinely need to access every Sale in each group afterward, **groupingBy(category)** returning Map<String,List<Sale>> is a reasonable approach. Do not optimize prematurely and discard data that a later step needs.

### 16.4. Distinguishing grouping and partitioning with empty data

**groupingBy** on an empty stream returns a Map with no groups. **partitioningBy** has a policy of two boolean keys and the downstream has a nominal value for each side; with **counting**, both sides can have a result of 0L.

If the application wants to report **all categories in a registered catalog**, including categories not present in the source, groupingBy cannot automatically create unseen categories. You need to merge with an externally defined category catalog; do not assume that “groupingBy + counting” automatically generates all keys that have no data.

## 17. Testing Aggregated Metrics

Minimum checks:

1. **counting** on an empty source, single record, multiple records, and after filter.
2. **summingInt** on positive/0/negative numbers, checking units and numeric range.
3. **averagingDouble** on an empty set, single element, equal measurements, differing measurements, and precision error.
4. **groupingBy** on multiple groups, a group with only one element, and a group with quantity=0.
5. **partitioningBy** with all true, all false, and mixed data.
6. **filtering downstream** with a group having no matching elements; the group still exists with value 0.
7. **teeing** producing count and sum in the same aggregation pass.
8. **Key-based output** must be deterministic if the report requires ordering; use TreeMap and assert the Map properly instead of relying on HashMap ordering.
9. **Mapper does not modify the source** and does not rely on global mutable state.
10. When running in parallel, define a double tolerance; do not require floating-point results to be bit-for-bit identical if the algorithm allows combining in different orders.

Simple test example:

~~~java
long c = List.of(3, 5, 7).stream()
        .collect(Collectors.counting());

int s = List.of(3, 5, 7).stream()
        .collect(Collectors.summingInt(Integer::intValue));

double a = List.of(3, 5, 7).stream()
        .collect(Collectors.averagingDouble(
                Integer::doubleValue));

if (c != 3L || s != 15 || Math.abs(a - 5.0) > 1e-12) {
    throw new AssertionError("Unexpected statistics");
}
~~~

This is a snippet inside a method with List/Collectors imported. It checks the three metrics directly, without depending on callback side effects.

## 18. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Thinking counting() returns Integer | Variable declared with wrong type | Remember the result is Long |
| Thinking summingInt() returns Long | Wrong type or insufficient numeric range chosen | Use Integer; switch to summingLong if needed |
| Thinking averagingDouble() returns OptionalDouble | Empty case is not handled | It returns Double; empty is 0.0 |
| Assuming 0.0 guarantees observations exist | Confusing empty data with a true average of 0 | Pair with counting or use OptionalDouble |
| Summing unit price with summingInt and calling it revenue | Wrong unit | Mapper must compute quantity × price |
| Averaging unit price per line and calling it per item | Wrong weighting | Compute total amount / total quantity per definition |
| Ignoring int overflow | Sum returns wrong value | summingLong or larger numeric type |
| Multiplying two ints before casting to long | Overflow happens before the cast | Cast operands before multiplying |
| Using averagingDouble for money requiring exact precision | Precision error and hard-to-guarantee rounding | BigDecimal / rounding policy |
| Ignoring NaN/Infinity | Aggregated result may be unusable | Validation or filtering with reporting |
| Printing groupingBy and assuming Map order is always fixed | Non-deterministic report | Use TreeMap/mapFactory or sort on output |
| Filtering before grouping and expecting 0-count groups to still appear | Groups with all elements filtered out disappear | Use filtering downstream when you want to keep keys |
| Mapper with side effects or mutable counter | Result depends on order/execution | Use pure mappers and stable data |
| Manually updating HashMap in parallel forEach | Race condition | Use a Collector with the proper contract |

## 19. Practice Exercises

### Exercise 1 — Count per classroom

Given a list of Student with accessor **className()**. Count the number of Student per class using **groupingBy** and **counting**.

**Suggested answer:**

~~~java
Map<String, Long> counts = students.stream()
        .collect(Collectors.groupingBy(
                Student::className,
                Collectors.counting()));
~~~

This snippet requires declarations for Student, students, and imports for Map/Collectors.

### Exercise 2 — Sum quantity sold

Given a list of Order with **quantity()** of type int. Write a pipeline returning the total quantity using **summingInt**.

**Answer:**

~~~java
int units = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));
~~~

If the sum can exceed the int range, switch to **summingLong** or design a wider numeric range.

### Exercise 3 — Average processing time

A list of Job has **durationSeconds()** as double. Compute the average and handle the case where an empty list means “no data yet”.

**Suggested answer:** use **mapToDouble(Job::durationSeconds).average()** returning OptionalDouble to represent absence, or combine **counting() + averagingDouble(...)** if the reporting API needs both the count and the average as Double.

### Exercise 4 — Difference between two types of averages

Given two transactions: **1 item × 10.000** and **3 items × 20.000**.

- Average unit price per line = (10.000 + 20.000)/2 = **15.000**.
- Average per item = (10.000 + 3 × 20.000)/(1 + 3) = **17.500**.

**Question:** Which one does averagingDouble(Order::unitPrice) return? **Answer:** it returns **15.000**, because each Order contributes one observation, not weighted by quantity.

### Exercise 5 — Keeping a group with count=0

Given a list of orders with categories A and B; all orders in A are unpaid. You need a Map containing A=0, B=number of paid orders. Should you filter before groupingBy or use filtering downstream?

**Answer:** **groupingBy(category, filtering(isPaid, counting()))** to keep key A and yield 0, whereas filtering before grouping would drop group A.

### Exercise 6 — Testing empty data and overflow

Write tests for the three collectors on an empty stream. Then create a sequence summing to **Integer.MAX_VALUE + 1** and observe summingInt. Explain why the overflowed result is not a Collector syntax bug but an **int arithmetic limit**. Rewrite using summingLong.

## 20. Key Takeaways

**Collectors.counting(), summingInt(), and averagingDouble()** are three fundamental data reduction tools:

- **counting()** returns **Long** counting elements, **0L** when empty.
- **summingInt(mapper)** returns **Integer** summing int values produced by the mapper, **0** when empty, with risk of **int overflow**.
- **averagingDouble(mapper)** returns **Double** arithmetic mean of double values produced by the mapper, **0.0** when empty, and may have floating-point error.

When computing only a single simple metric, you can use **count()**, **sum()**, or **average()** on a Stream/primitive Stream. When statistics **per group** are needed, Collectors shine as **downstream collectors of groupingBy or partitioningBy**. With **filtering downstream**, distinguish a group with a result of 0 from a group removed from the Map.

Before generating a report, always determine: **are we counting records or summing which quantity; is the average weighted; how is empty data interpreted; does the numeric type have sufficient range and precision?** Choosing the right Collector is a necessary condition, but **defining the statistic correctly** is what makes the result meaningful.
