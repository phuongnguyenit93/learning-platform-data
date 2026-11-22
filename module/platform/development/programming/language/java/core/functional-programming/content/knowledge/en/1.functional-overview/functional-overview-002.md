# From Step-by-Step Descriptions to Data Transformation Descriptions in Java

## 1. Step-by-Step Thinking and Transformation Thinking

Consider the requirement: from a list of orders, take only the products of **paid orders with a positive quantity**; normalize the names by trimming whitespace from both ends and converting to uppercase; remove duplicate names and sort them for display.

There are two ways to express this:

- **Imperative (step-by-step description):** create a result list, iterate through each order, check the conditions, extract the name, add it if it does not already exist, and finally sort. The reader follows loops, conditional branches, and the state of the list mutating over time.
- **Declarative (transformation description):** from the orders, **filter** valid orders → **project** to product names → **normalize** → **deduplicate** → **sort** → **collect the result**. The reader sees the rules for transforming input data into output data.

The second expression is closer to the concepts of functional programming; Java provides lambdas, method references, functional interfaces, and the Stream API to implement it. However, Java is a multi-paradigm language: an explicit loop is still sometimes more appropriate than a Stream.

What needs to change first is the question you ask: **“What should the data become at each step?”**, and only then “Which Java syntax should I use?”. Declarative does not mean ignoring algorithms or performance; it is a way of placing business rules in a clearly visible position.

## 2. Analyzing Inputs, Outputs, and Data Contracts

Before writing a pipeline, determine:

1. **Source:** a list of `Order` objects; can it be null, and is the data coming from memory or an external system?
2. **Selection conditions:** the order must be paid and the quantity must be greater than 0.
3. **Transformation:** from `Order` to `String`, then normalizing the `String` content.
4. **Result constraints:** unique names, sorted according to the chosen rule; does the list need to be modifiable?
5. **Side effects:** does the problem only compute a result, or does it also update a database, write to a file, or call a service?
6. **Data errors:** by what rules are null names, whitespace, duplicate data, negative amounts, and missing values handled?

This mindset is close to a function **f(input) → output**: the inputs and rules determine the result, without depending on hidden state. We usually prefer transformation functions with minimal side effects for readability, testability, and reusability. **A lambda is not automatically a pure function**; a lambda can still mutate the state of external objects.

An illustrative pipeline:

~~~text
List<Order>
    ↓ filter: paid orders
    ↓ filter: positive quantity
    ↓ map: Order → product name
    ↓ map: normalize name
    ↓ distinct: unique names
    ↓ sorted: deterministic order
List<String>
~~~

Each step should have a clear business purpose. The order also matters: normalizing **before** deduplicating merges names that differ only in whitespace or letter case.

## 3. Complete Example: Two Solutions to the Same Problem

Create the file **TransformData.java** (JDK 17 or later):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

record Order(String customer, String product,
             int quantity, int unitPrice, boolean paid) {}

public class TransformData {
    static List<String> imperative(List<Order> orders) {
        List<String> names = new ArrayList<>();

        for (Order order : orders) {
            if (!order.paid() || order.quantity() <= 0) {
                continue;
            }

            String name = order.product()
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (!names.contains(name)) {
                names.add(name);
            }
        }

        Collections.sort(names);
        return names;
    }

    static List<String> declarative(List<Order> orders) {
        return orders.stream()
                .filter(Order::paid)
                .filter(order -> order.quantity() > 0)
                .map(Order::product)
                .map(String::strip)
                .map(name -> name.toUpperCase(Locale.ROOT))
                .distinct()
                .sorted()
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("Lan", " Sách ", 2, 120, true),
                new Order("Minh", "Bút", 3, 15, true),
                new Order("Lan", "SÁCH", 1, 120, true),
                new Order("An", "Vở", 1, 30, false),
                new Order("Minh", "Bút", 0, 15, true),
                new Order("An", " Tẩy ", 1, 5, true)
        );

        System.out.println(imperative(orders));
        System.out.println(declarative(orders));
    }
}
~~~

Compile and run in a terminal with JDK 17+:

~~~bash
javac -encoding UTF-8 TransformData.java
java TransformData
~~~

Stdout:

~~~text
[BÚT, SÁCH, TẨY]
[BÚT, SÁCH, TẨY]
~~~

Both approaches filter out unpaid orders and zero-quantity orders, normalize using the same rule, deduplicate, and sort. The difference is that **the imperative version manages the intermediate list manually**, while the Stream version **chains operations that reflect the processing intent**.

Comparison table of the transformations:

| Stream Operation | Task | Element Type After Operation |
| --- | --- | --- |
| **orders.stream()** | Obtain the data source | Order |
| **filter(Order::paid)** | Keep paid orders | Order |
| **filter(o -> o.quantity() > 0)** | Keep orders with positive quantity | Order |
| **map(Order::product)** | Extract name from Order | String |
| **map(String::strip)** | Remove leading/trailing whitespace | String |
| **map(name -> name.toUpperCase(Locale.ROOT))** | Normalize to uppercase | String |
| **distinct()** | Remove duplicate names | String |
| **sorted()** | Sort in natural order | String |
| **toList()** | Create the result list | List<String> |

**Order::paid** is a method reference, equivalent here to **order -> order.paid()**. Similarly, **String::strip** expresses the call **name -> name.strip()** on each string.

Note on the example data scope: the program assumes **product != null**. If a real-world source can contain null, a clear policy and null check are needed before calling **strip()**. **Locale.ROOT** makes the uppercase conversion independent of the default locale; **sorted()** by default compares Strings according to Unicode natural order, which does not mean sorting according to Vietnamese alphabetical order. To sort by specific language rules, choose an appropriate Comparator/Collator for the requirement.

## 4. How Does a Stream Pipeline Execute?

**Source** provides the elements (such as **List.stream()**, **Stream.of(...)**). A Stream is not a new collection that can be traversed repeatedly at will.

**Intermediate operations** such as **filter**, **map**, **distinct**, and **sorted** mainly return a Stream describing the next processing step. These steps are **lazily evaluated**: when only constructing the pipeline, Java generally has not yet traversed the source to compute the output.

**Terminal operations** such as **toList**, **collect**, **count**, **reduce**, **findFirst**, **anyMatch**, and **forEach** trigger the evaluation of the pipeline. A consumed Stream cannot be reused to run a pipeline a second time; call **stream()** again on the source when needed.

Distinguishing the operation groups:

- **filter** keeps or discards elements based on a **Predicate<T>**; the element type does not change.
- **map** transforms elements via a **Function<T,R>**; the output type can differ from the input type.
- **distinct** uses element equality rules (involving **equals/hashCode**) to remove duplicates; it is a stateful operation.
- **sorted** sorts by natural order or a Comparator; it needs to process multiple elements, so it has a different cost than pure **map**.
- **findFirst** and **anyMatch** can short-circuit once a sufficient result is found; do not assume every terminal operation always traverses the entire source.
- **Stream.toList()** (Java 16+) returns a list that does not allow adding, removing, or modifying elements via List update operations. If a mutable list is needed, choose **collect(Collectors.toCollection(ArrayList::new))**.

**A Stream is not inherently faster than a loop.** Evaluate traversal cost, intermediate memory, boxing, sorting, and data volume with appropriate measurements. The primary goal here is clear expression and easily testable transformation logic.

## 5. map or flatMap?

**map** transforms each element into a new value. If the new element is a List, the result at the Stream level will be Stream<List<T>>. **flatMap** is used when each element produces a sub-Stream and we want to flatten those sub-Streams into a single stream.

For example, the following code snippet is placed inside a method with **java.util.List** imported:

~~~java
List<List<String>> groups = List.of(
        List.of("java", "stream"),
        List.of("lambda")
);

List<String> tags = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(tags); // [java, stream, lambda]
~~~

If replaced with **map(List::stream)**, each resulting element would be a Stream instead. Use **flatMap** when flattening matches the business output, such as a list of orders → the line items of all orders.

## 6. Transforming to Aggregate Data

Not all problems end with a List. For example: “Considering only paid transactions, calculate the **total amount per customer**”. The transformation-based description is **filter transactions → group by customer → sum each group**.

Create the file **SummarizePaidSales.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Sale(String buyer, int amount, boolean paid) {}

public class SummarizePaidSales {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Lan", 120, true),
                new Sale("Minh", 50, false),
                new Sale("Lan", 80, true),
                new Sale("An", 40, true),
                new Sale("An", 20, false)
        );

        Map<String, Integer> totalByBuyer = sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::buyer,
                        TreeMap::new,
                        Collectors.summingInt(Sale::amount)
                ));

        System.out.println(totalByBuyer);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SummarizePaidSales.java
java SummarizePaidSales
~~~

Stdout:

~~~text
{An=40, Lan=200}
~~~

**groupingBy** uses **Sale::buyer** as the grouping key, while **summingInt** sums the amount field within each group. **TreeMap::new** provides a deterministic key order. Do not rely on display order when using a Map without an ordering contract like HashMap.

In a real-world project, clearly define the currency unit, rounding mode, and potential integer overflow; **int** is only simple numeric data for the example. You can use integer values in the smallest currency unit or **BigDecimal** according to the business domain specification.

The lesson on how to think: instead of starting with **initializing a Map, checking keys, and adding to the old value**, first determine the **transaction scope, grouping key, and aggregation operation**. Collectors are the implementation of those three rules.

## 7. Process for Converting Step-by-Step Code to Transformation Code

1. **Write down the input/output contract:** data types, cardinality, nulls, ordering, deduplication, and whether the result may be mutated.
2. **Separate business behavior from control-flow details:** a condition usually becomes **filter**; an element conversion becomes **map**; grouping/summing becomes **collect** or the corresponding collector.
3. **Order transformations meaningfully:** normalize before deduplicating; keep filtering before expensive processing if it does not change the result; do not swap steps just to write shorter code.
4. **Isolate side effects:** compute the result separately before writing files, saving to a database, or calling services; steps that produce side effects may need loops and explicit error handling.
5. **Name complex rules:** if a lambda is hard to read, use a method such as **isEligibleOrder** or **normalizeProductName**.
6. **Compare the behavior of the old and new versions:** test empty input, all-filtered-out elements, duplicate names with different formatting, nulls, ordering, errors, and state immutability.
7. **Measure before optimizing:** a shorter Stream line does not guarantee better CPU/memory efficiency.

When writing a long pipeline, read from left to right and try to express each step in a single sentence. If two or three steps have business dependencies that are hard to explain, consider extracting them into a clearly named method.

## 8. Common Mistakes

| Mistake | Why It Is a Problem | How to Handle It |
| --- | --- | --- |
| Using **map** to add elements to an external mutable List | Has side effects, makes code hard to reason about, and is dangerous when parallelizing | Use map to produce values and collect with a terminal operation |
| Ignoring null elements | Can throw NullPointerException at a method reference/call | Define a policy and filter with **Objects::nonNull** in the appropriate place |
| Putting **distinct** before normalization | Strings with different formatting may still be duplicates after normalization | Keep the order that reflects business logic |
| Using **peek** to perform required state updates | Side effects in peek are not a reliable mechanism for executing business logic | Only use peek for observation/debugging where appropriate; use a collector or loop for necessary updates |
| Reusing a Stream that has already terminated | May throw **IllegalStateException** | Create a new Stream |
| Assuming **toList()** is always modifiable | Adding/removing throws **UnsupportedOperationException** | Use a mutable collector when needed |
| Relying on the default order of **groupingBy** | The resulting Map may not guarantee the desired display order | Provide a Map supplier with an ordering contract |
| Assuming **parallelStream()** is fast and safe by default | Overhead and shared state updates can cause bugs/degrade performance | Prefer sequential; only try parallel after measuring and considering thread safety |

A lambda can capture a reference to a mutable object. Code like **parallelStream().forEach(item -> sharedList.add(item))** with a shared ArrayList is an unsafe design; thread safety must not be inferred from functional syntax.

You should also distinguish **data order** from **operation application order**. A declarative pipeline still has meaningful ordering. **filter → map → distinct** can yield a different result than **distinct → filter → map**, depending on the data and equality rules; only reorder operations after proving equivalence.

## 9. Choosing the Appropriate Style

**Stream is suitable** when the problem involves filtering, type conversion, normalization, grouping, summing, or transforming from one dataset to another. These operations can be composed into a relatively readable chain of independent rules.

**A loop is suitable** when the algorithm carries heavily interdependent state across steps, needs to break or continue across multiple complex branches, performs in-place updates, executes sequential I/O, or when a loop expresses the algorithm more clearly. There is no requirement to convert every **for** loop into a Stream.

A solid Java developer chooses based on **the output contract, clarity, correctness, testability, and measured performance**. Functional programming provides a powerful way of thinking about data transformation; it does not replace every imperative technique.

## 10. Self-Check Questions

1. In the product name example, why must **distinct()** come after normalization if we want “ Sách ” and “SÁCH” to be treated as the same name?
2. Why does **filter(Order::paid)** preserve the **Order** type, while **map(Order::product)** changes the element type to **String**?
3. In the total amount problem, which step determines valid transactions, which step selects the grouping key, and which step performs the addition?
4. If the product name can be null, what rule do you need to add and where should the check be placed?
5. When the result must allow adding elements, why do you need to change how the list is collected after the pipeline?
6. Rewrite a data-filtering loop you are currently using, then verify equivalence on empty input, duplicates, and edge-case data.

Mastering the expression **source → selection rules → transformations → output structure** is the foundation for using lambdas and Streams intentionally, rather than merely replacing loops with shorter syntax.