# Combining Small Transformations into Large Pipelines in Java

## 1. Lesson Objectives

When a problem requires multiple steps such as **filtering data → normalizing → computing → sorting → presenting**, a readable way to organize the code is to split each step into a small transformation, then **compose them in an intentional order** into a large pipeline.

After this lesson, you can:

- Look at a business process and identify the input, output, and responsibility of each step.
- Use **Function**, **andThen**, **compose**, method references, **Predicate**, and Java **Stream** to compose transformations.
- Understand why transformation order matters: **filter**, **map**, **sorted**, and their impact on both results and processing cost.
- Identify steps with side effects, mutable data, exceptions, and issues when reusing or running a pipeline in parallel.
- Test each step independently and test the entire pipeline with sample data that has deterministic results.

## 2. Core Idea: The Output of One Step Is the Input of the Next

Suppose a system needs to process orders:

1. Receive a list of input orders.
2. Select only valid orders according to business rules.
3. Normalize the customer name and calculate the total amount for each order.
4. Sort by total amount in descending order.
5. Convert the results into strings for display.

Each stage should have a clear **input/output contract**:

~~~text
List<Order>
    │
    ├─ filter: Order -> boolean
    ▼
List<Order> (valid)
    │
    ├─ map: Order -> OrderView
    ▼
List<OrderView> (total calculated)
    │
    ├─ sorted: compare OrderView.totalVnd
    ▼
List<OrderView> (sorted)
    │
    ├─ map: OrderView -> String
    ▼
List<String> (result)
~~~

The key point is that each transformation only needs to know **the data it receives and the data it returns**, not the entire screen, database, or API of the application. Computation steps with minimal dependency on external effects are easier to test, reuse, and reorder when there is a valid reason.

Not every step has the same return type. An **Order → OrderView** step cannot be composed directly with a step that only accepts **LocalDate**, unless there is an appropriate type conversion. Java's type system will catch many mismatched-type composition errors at compile time.

### 2.1. Value Transformations and Effectful Operations

Distinguish between two roles:

- **Transformation:** receives a value, returns a new value; for example, normalizing a name, multiplying quantity by unit price, or creating a DTO.
- **Effect:** reads/writes external data; for example, querying a database, getting the current time, printing to the console, sending an HTTP request, or saving results.

A pragmatic design puts I/O at the boundaries, performs computations with explicit values in the middle, and then sends the results outward. There is no need to force every application operation to be a pure function; you need to know which steps cause effects so you can control errors and testing.

## 3. Composing Functions with Function<T, R>

The **java.util.function.Function<T, R>** interface represents a transformation from type **T** to type **R**, with the primary method **R apply(T value)**.

Given two functions **f: A → B** and **g: B → C**, you can create a new function **A → C**:

- **f.andThen(g)**: runs **f** first, then passes the result to **g**.
- **g.compose(f)**: also runs **f** first and then **g**; **compose** reads from the perspective of “which function executes before the current function”.

The two expressions **f.andThen(g)** and **g.compose(f)** have the same execution order—**f**, then **g**—when the two transformations have compatible types.

### 3.1. Execution Order Example

~~~java
import java.util.function.Function;

Function<Integer, Integer> plusThree = x -> x + 3;
Function<Integer, Integer> doubleIt = x -> x * 2;

int first = plusThree.andThen(doubleIt).apply(4);
int second = plusThree.compose(doubleIt).apply(4);
~~~

The value is **first = 14** because **(4 + 3) × 2 = 14**. The value is **second = 11** because **4 × 2 + 3 = 11**.

**Order matters:** addition and multiplication here cannot be arbitrarily swapped. In real-world problems, “rounding before applying tax” and “applying tax before rounding” can also produce different results.

If function **f** returns **B** but **g** only accepts a type incompatible with **B**, the **andThen** call will not compile. This is an advantage of explicitly describing data types between steps.

### 3.2. Functions Named for Clear Purpose

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        value -> value.toUpperCase(java.util.Locale.ROOT);

Function<String, String> normalize = trim.andThen(upper);
String result = normalize.apply("  Java  "); // "JAVA"
~~~

Splitting into **trim** and **upper** allows changing normalization rules, testing them separately, and reusing them in other pipelines. **Locale.ROOT** ensures the result does not depend on the machine's default locale. For specific natural-language rules, choose the locale according to product requirements.

**Note:** the **compose** and **andThen** methods only provide a way to chain calls. They do not turn a function with side effects into a pure function, do not handle null automatically, and do not catch exceptions automatically.

## 4. Combining Conditions with Predicate<T>

**Predicate<T>** represents a check that returns a **boolean**, with the method **test(T)**. The methods **and**, **or**, and **negate** help build larger rules from small conditions.

~~~java
import java.util.function.Predicate;

Predicate<String> notNull = value -> value != null;
Predicate<String> notBlank = value -> !value.isBlank();

Predicate<String> validName = notNull.and(notBlank);
~~~

**and** and **or** perform **short-circuiting**: with **and**, if the first condition is false, the second condition does not run. Therefore, **validName.test(null)** returns false without accessing **null.isBlank()**.

When combining conditions, order still matters if a predicate can throw an exception, is expensive, or causes effects. In practice, place safety checks such as null checks before dereference operations, place cheap conditions before expensive ones when appropriate, and avoid side effects in predicates.

Order evaluation example:

~~~java
Predicate<Order> hasCustomer =
        order -> order != null
                && order.customer() != null
                && !order.customer().isBlank();

Predicate<Order> valid = hasCustomer
        .and(order -> order.quantity() > 0)
        .and(order -> order.unitPriceVnd() >= 0);
~~~

The snippet above assumes an **Order** type with accessors **customer()**, **quantity()**, and **unitPriceVnd()**; this type will be declared in full in the standalone runnable example below.

The “filter out invalid orders” rule is only appropriate if the system **intentionally ignores** those orders. For business logic requiring full error feedback, classify inputs into valid and error groups to display or record, rather than silently dropping them.

## 5. Java Stream: Chaining Multiple Steps Over a Data Set

**Stream** lets you describe a sequence of operations over multiple elements without manually writing intermediate loops for each step. Common operations:

| Operation | Meaning | Typical Return Type |
| --- | --- | --- |
| **filter(predicate)** | Keep elements matching the condition | Stream<T> |
| **map(function)** | Transform each element | Stream<R> |
| **flatMap(function)** | Turn one element into a stream and flatten | Stream<R> |
| **distinct()** | Remove duplicates using **equals/hashCode** | Stream<T> |
| **sorted(comparator)** | Sort elements | Stream<T> |
| **limit(n)** | Limit to at most **n** elements | Stream<T> |
| **toList()** | Collect into a list | List<T> |
| **reduce(...)** | Combine elements into a single value | Value or Optional |

**filter**, **map**, **flatMap**, **distinct**, **sorted**, and **limit** are **intermediate operations** and are typically **lazy**: declaring the chain of operations does not mean the data has been traversed yet. **toList**, **forEach**, **count**, and **reduce** are examples of **terminal operations** that trigger processing.

~~~java
List<String> names = List.of(" An ", " ", "Binh");

List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(value -> !value.isEmpty())
        .map(value -> value.toUpperCase(java.util.Locale.ROOT))
        .toList();
~~~

The result **cleaned** is **[AN, BINH]**. **Stream.toList()** (Java 16+) returns a list that does not support mutating operations such as **add**; it does not automatically make every element deeply immutable.

**A Stream is not reusable data:** once a **Stream** object has terminated, it cannot be used for another terminal operation. When you need to execute again, create a new stream from the source, for example **names.stream()**. Mutable data sources can lead to different results if modified between runs.

## 6. Complete Java 17 Example: Order Processing Pipeline

The example below combines small transformations into a runnable program. All computations use explicit input data; only **main** prints results to the console.

Save as **OrderPipelineDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Function;
import java.util.function.Predicate;

public class OrderPipelineDemo {
    record Order(String customer, int quantity, long unitPriceVnd) {
    }

    record OrderView(String customer, long totalVnd) {
    }

    static String normalizeName(String name) {
        return name.strip().toUpperCase(Locale.ROOT);
    }

    static long total(Order order) {
        return Math.multiplyExact((long) order.quantity(),
                                  order.unitPriceVnd());
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(" an ", 2, 15_000),
                new Order("Binh", 0, 20_000),
                new Order(" Chi ", 3, 12_000),
                new Order("Dung", 1, 10_000)
        );

        Predicate<Order> hasCustomer =
                order -> order != null
                        && order.customer() != null
                        && !order.customer().isBlank();

        Predicate<Order> valid = hasCustomer
                .and(order -> order.quantity() > 0)
                .and(order -> order.unitPriceVnd() >= 0);

        Function<Order, OrderView> summarize =
                order -> new OrderView(
                        normalizeName(order.customer()),
                        total(order)
                );

        Function<OrderView, String> render =
                view -> view.customer() + ": "
                        + view.totalVnd() + " VND";

        Function<Order, String> describe = summarize.andThen(render);

        List<String> lines = orders.stream()
                .filter(valid)
                .map(summarize)
                .sorted(Comparator.comparingLong(
                        OrderView::totalVnd).reversed())
                .map(render)
                .toList();

        System.out.println("andThen: "
                + describe.apply(orders.get(0)));
        System.out.println("compose: "
                + render.compose(summarize).apply(orders.get(0)));
        System.out.println("pipeline: " + lines);
        System.out.println("source size: " + orders.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac OrderPipelineDemo.java
java OrderPipelineDemo
~~~

**Exact output:**

~~~text
andThen: AN: 30000 VND
compose: AN: 30000 VND
pipeline: [CHI: 36000 VND, AN: 30000 VND, DUNG: 10000 VND]
source size: 4
~~~

### 6.1. Step-by-Step Explanation

**Step 1 — filter:** **valid** keeps three orders that have a valid customer, positive quantity, and non-negative unit price. **Binh**'s order is excluded because **quantity = 0**. With this rule, an order with a unit price of 0 is still considered valid; change the rule if the business does not allow it.

**Step 2 — transform:** **summarize** creates a new **OrderView**, normalizes the name, and calculates the total amount. **Math.multiplyExact** throws **ArithmeticException** if **long** multiplication overflows; therefore, the program does not silently return an incorrect monetary result. **normalizeName** assumes the name is non-null because it has already passed the filter condition.

**Step 3 — sort:** **Comparator.comparingLong(OrderView::totalVnd).reversed()** sorts **OrderView** by total amount in descending order. Sorting based on the **numeric value** happens **before** converting to a string, avoiding lexicographical sorting bugs on formatted values.

**Step 4 — render:** **render** converts each **OrderView** into a string. Both **summarize.andThen(render)** and **render.compose(summarize)** have the same execution order and produce the same string for the same input order.

**Step 5 — collect:** **toList()** terminates the pipeline and creates the result list. The source list **orders** still has four elements because the pipeline does not modify or remove elements in the source.

### 6.2. Why Not Put Everything into One Giant Function?

You could write everything in one long method, but when changing how totals are calculated, wanting to return JSON instead of strings, or needing to test the order-selection rule separately, the reader has to modify multiple pieces of logic at once.

Splitting into small pieces creates units with their own names, responsibilities, data types, and tests. The orchestration part only states **how the steps are connected**. However, you should not split to the point where every trivial operation gets an extra class or interface if it makes the code harder to follow.

## 7. Pipeline Order Affects Results and Performance

The following two sequences of operations are **not always equivalent**:

~~~java
// Keep only valid data before doing the transformation work.
stream.filter(valid).map(transform)

// Do the transformation work for every element before checking.
stream.map(transform).filter(validTransformed)
~~~

If the transformation is expensive, filtering early often avoids unnecessary computation. However, if the condition can only be evaluated **after transform**, they cannot be swapped like this. You must also consider side effects, exceptions, and data rules to ensure behavior is not altered.

### 7.1. Sort Before or After Limiting?

~~~java
// Take the three elements with the largest values.
numbers.stream()
        .sorted(Comparator.reverseOrder())
        .limit(3)
        .toList();

// Take only the first three elements from the source, then sort those three elements.
numbers.stream()
        .limit(3)
        .sorted(Comparator.reverseOrder())
        .toList();
~~~

The two approaches only produce the same result by coincidence. For the input **[1, 9, 2, 8, 3]**, the first returns **[9, 8, 3]**, while the second returns **[9, 2, 1]**. **limit** affects which set of elements is allowed to proceed, so its position is part of the business contract.

### 7.2. flatMap When One Element Produces Multiple Elements

Suppose each order has multiple tags:

~~~java
List<List<String>> groups = List.of(
        List.of("java", "stream"),
        List.of("function", "java")
);

List<String> tags = groups.stream()
        .flatMap(List::stream)
        .distinct()
        .toList();
~~~

The result **tags** is **[java, stream, function]**, in first-seen order from an ordered source. **map(List::stream)** produces **Stream<Stream<String>>**, whereas **flatMap(List::stream)** flattens it into **Stream<String>** so subsequent steps process each tag individually. **distinct** distinguishes elements according to their **equals/hashCode** contract.

## 8. Combining Computed Results

A pipeline does not only turn **List<A>** into **List<B>**, it can also reduce elements into a single value:

~~~java
int totalLength = List.of("An", "Binh", "Chi")
        .stream()
        .mapToInt(String::length)
        .sum();
~~~

**totalLength = 9** because the string lengths are 2, 4, and 3 respectively. Using **mapToInt** makes the result a primitive stream with a convenient **sum()** method.

A **reduce** operation is appropriate when you have an identity element and a combining operation that satisfies the required rules:

~~~java
int sum = List.of(2, 3, 4).stream()
        .reduce(0, Integer::sum); // 9
~~~

For a pipeline that may run in parallel, the combining operation must be **associative** and compatible with the identity so that the result does not depend on how elements are grouped. Subtraction is not associative: **(a - b) - c** can differ from **a - (b - c)**, so it cannot be used arbitrarily as a parallel reduction with arbitrary grouping order.

**Integer::sum** is Java's **int** addition, which can overflow according to **int** rules; for financial data, use an appropriate numeric type and rounding/overflow policy, such as **long** with **Math.addExact**, or **BigDecimal** as required by the domain.

## 9. Keeping Effects Outside the Computation Pipeline

A lambda inside **map** can still do unintended work:

~~~java
List<String> names = List.of("An", "Binh");
List<String> result = names.stream()
        .map(name -> {
            System.out.println("Processing: " + name);
            return name.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

This snippet compiles and runs, but the **map** step has a console side effect. Refactoring, changing the terminal operation, or running in parallel can cause the order or number of callback executions to differ from what the author expected. **Stream.peek** is useful for observing/debugging, but it is not a place to guarantee execution of critical business operations; some optimizations may skip steps unnecessary for computing the terminal result.

Instead, separate the data transformation part:

~~~java
List<String> upper = names.stream()
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();

upper.forEach(System.out::println);
~~~

**forEach** is now the effectful operation, separated from data creation. Even **forEach** is not a pure place; it is a deliberate choice at the display boundary.

For databases/APIs, read data in the adapter/service layer, pass a snapshot or DTO to the computation layer, and then persist results in an outer step. When performing multiple sequential effects (such as writing to a database and then sending an email), you need to design transactions, retries, idempotency, and failure handling separately; **Function.andThen** does not provide those mechanisms on its own.

## 10. Handling Errors, Nulls, and Invalid Data

A multi-step pipeline will fail if one step throws an exception without proper handling. For example, **Integer.parseInt("12x")** throws **NumberFormatException**; **map(Integer::parseInt)** does not automatically turn it into a friendly error result.

Three handling approaches depending on the business contract:

1. **Fail fast** on invalid data when every element must be valid; let the error propagate to a layer that can respond clearly.
2. **Filter with explanation** when the business allows skipping data, while recording statistics or a list of exclusion reasons at the processing boundary.
3. **Model errors as data**, such as a record carrying **value/error** or a custom **Result<T, E>** type; then branch into success and failure before continuing.

A simple example with **Optional** is only suitable when the “absent value” state is enough to represent the decision:

~~~java
import java.util.Optional;

static Optional<Integer> parsePositive(String raw) {
    if (raw == null || !raw.matches("[0-9]+")) {
        return Optional.empty();
    }
    try {
        int parsed = Integer.parseInt(raw);
        return parsed > 0 ? Optional.of(parsed) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty(); // Example intentionally collapses errors into "absent".
    }
}
~~~

This is an **illustrative method snippet** placed inside a Java class; it is not a standalone runnable file. Note that this approach does not distinguish between format errors, **int** overflow, or non-positive numbers. If you need to report each error, use a result with an explicit error code/message instead of **Optional.empty()**.

**Function** often accepts/returns **null** if the logic allows it, but most subsequent steps will encounter **NullPointerException** if unhandled. Define a clear null contract: forbid null and check early, or use **Optional**/a result type to describe the possibility of missing data.

## 11. Testing Each Step and the Entire Chain

**Testing each transformation:** verify outputs for representative and boundary inputs.

- **normalizeName(" an ")** must return **"AN"**.
- **total(new Order("An", 2, 15000))** must return **30000**.
- **valid.test(new Order("Binh", 0, 20000))** must return false.
- **render.apply(new OrderView("CHI", 36000))** must return **"CHI: 36000 VND"**.

**Testing the pipeline contract:** provide a set of orders with equal total amounts, invalid orders, and names needing normalization; verify that the result is filtered, sorted, and rendered according to specification. If the order between orders with the same total amount matters, explicitly define a secondary criterion (such as order ID) instead of relying on accidental order.

A simple example that can self-verify right inside **main** after creating **lines**:

~~~java
List<String> expected = List.of(
        "CHI: 36000 VND",
        "AN: 30000 VND",
        "DUNG: 10000 VND"
);
if (!lines.equals(expected)) {
    throw new AssertionError("Unexpected pipeline result: " + lines);
}
~~~

This check belongs to the **OrderPipelineDemo** program where **lines** is already declared, and does not run standalone. It only tests one case; real tests should add empty data, null according to contract, large numbers causing overflow, already-sorted data, equal values, and data source failures.

A pure computation pipeline, separated from I/O, allows tests to verify formulas and filtering rules without needing a network or database connection.

## 12. Common Mistakes When Composing Pipelines

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Confusing **compose** with **andThen** | Runs operations in the wrong order | Draw an A → B → C type diagram and verify with a numeric example |
| Unnecessary **map** before **filter** | Transforms data that will be discarded, increasing cost or causing errors | Check whether you can safely filter on the original data first |
| **sorted** after formatting numbers into strings | Lexicographical sorting instead of numeric sorting | Sort by the numeric property before rendering |
| Mutating an external collection inside **map/forEach** | Prone to bugs when reordering, repeating, or running in parallel | Return new values or use an appropriate collector |
| Keeping a Stream to use a terminal operation a second time | **IllegalStateException** because the stream is already consumed | Create a new stream from the source |
| Using **peek** to write mandatory data | Effects may not run as expected | Move write operations to an intentional boundary |
| Skipping invalid data with **filter** without reporting | Silent record loss | Choose an explicit error policy |
| Allowing a mutable source to change during traversal | Incorrect, non-deterministic results or access errors | Snapshot, immutability, or proper synchronization |
| Using **parallelStream** with lambdas having shared state | Race conditions, hard-to-reproduce results | Stateless functions, associative reduction, actual performance measurement |
| Over-splitting with vague names | Pipeline is harder to read than the original code | Give each step a clear business purpose |

**Not every pipeline should run in parallel.** A sequential chain of operations is often simple and fast enough. Parallel execution should only be considered when the workload is large enough, steps are independent, data/collectors are safe, reductions are valid, and actual benchmarks show a benefit. Parallel streams do not guarantee that callback side effects run in encounter order.

## 13. Practice Exercises

### Exercise 1: Composing Functions in Two Ways

Given **trim: String → String**, **lower: String → String**, and **length: String → Integer**. Write a **Function<String, Integer>** that returns the string length after trimming whitespace and converting to lowercase. Use both **andThen** and **compose**, with an explicit locale if case conversion is involved.

**Suggested solution:**

~~~java
Function<String, String> trim = String::strip;
Function<String, String> lower =
        s -> s.toLowerCase(Locale.ROOT);
Function<String, Integer> length = String::length;

Function<String, Integer> a =
        trim.andThen(lower).andThen(length);
Function<String, Integer> b =
        length.compose(lower).compose(trim);
~~~

Both functions return **4** when given **"  JAVA  "**. These declarations are code snippets placed in a context where **Function** and **Locale** are already imported, not a standalone file. Note that **String.length()** counts UTF-16 code units, which does not necessarily equal the number of user-perceived characters in all languages/emojis.

### Exercise 2: Ordering Operations

Given the numbers **[8, 1, 3, 5]**, design a pipeline to “keep only odd numbers, double them, sort ascending”. The result must be **[2, 6, 10]**.

~~~java
List<Integer> answer = List.of(8, 1, 3, 5)
        .stream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 2)
        .sorted()
        .toList();
~~~

Try swapping **filter** and **map** while keeping the predicate **n % 2 != 0**: when doubling first, every element becomes even and gets filtered out, proving that **order changes the meaning of the pipeline**.

### Exercise 3: Designing from a Business Description

A list of employees has **full name, department, salary**. Requirements:

1. Select only active employees.
2. Normalize the department name.
3. Calculate income after applying the given allowance rules.
4. Sort by income in descending order.
5. Create result records to return from an API.

Write the type contract for each step before writing the Stream; determine which step needs the allowance information and how to pass it in as an **input parameter**, rather than reading global configuration inside a lambda. Specify the rounding method and monetary type before computing. Write tests for each transformation before testing the full chain.

## 14. Key Takeaways

**From small transformations to large pipelines** means designing functions with clear contracts and composing them in the right order. **Function.andThen/compose** composes value transformations; **Predicate.and/or/negate** composes conditions; **Stream.filter/map/flatMap/sorted/toList** expresses pipelines over multiple elements.

Clearly map out **input data → each step → output**, consider the placement of filtering/sorting/reducing, keep computation reproducible, push I/O effects to the boundaries, and decide on error handling before putting the pipeline into production. This organization keeps a long process readable as a sequence of small, meaningful operations.