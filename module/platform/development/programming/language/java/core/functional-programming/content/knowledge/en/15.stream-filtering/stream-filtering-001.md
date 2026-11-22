# filter() and Designing Non-Mutating Predicates in Java

## 1. Lesson Objectives

When working with lists of products, orders, or accounts, we often need to **select elements that match a condition** without modifying the original data. In Java, **Stream.filter(Predicate)** is a clear way to express this intent: it describes the rule for checking each element and creates a Stream containing only the elements that satisfy the condition.

This lesson focuses on two closely related skills:

1. **Using filter() to select elements**, understanding it as a lazy intermediate operation that is only evaluated when a terminal operation is invoked.
2. **Designing non-interfering and stateless Predicate<T> instances**, making pipelines easier to test, easier to maintain, and safer when changing execution strategies.

After this lesson, you will be able to write expressive Predicates, compose conditions with and/or/negate, separate filtering from transformation, preserve order when needed, distinguish between not mutating **the source collection structure** and **not mutating mutable elements**, and avoid pitfalls with null, side effects, parallel streams, stateful predicates, and short-circuiting.

## 2. What Does filter() Do?

The key signature on **Stream<T>**:

~~~java
Stream<T> filter(Predicate<? super T> predicate)
~~~

It creates a Stream containing the elements from the source Stream for which **predicate.test(element)** returns **true**. Elements that test false do not proceed further in the pipeline. **The element type T remains unchanged** because filter only selects elements and does not transform their type.

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

List<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(even);   // [2, 4, 6]
System.out.println(numbers); // [1, 2, 3, 4, 5, 6]
~~~

In the sequential example above, the **numbers** list remains intact; **even** is the result list produced by the terminal **toList()**. Java 16+ defines **Stream.toList()** as returning an **unmodifiable** list: you cannot add, remove, or replace elements using standard mutation operations.

To be precise: **filter does not modify the source collection** as long as the Predicate does not do so. However, if a Predicate intentionally mutates an object passed through it, filter itself **does not prevent** side effects. Therefore, Predicate design is a crucial part of this lesson.

### 2.1. True/False Conditions

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> evenNumber = n -> n % 2 == 0;

System.out.println(positive.test(5));  // true
System.out.println(evenNumber.test(5)); // false
~~~

**Predicate<T>** is a functional interface in the **java.util.function** package with a single abstract method:

~~~java
boolean test(T t);
~~~

Think of a Predicate as a **question** about data:

- **isActive(user)** — is the account active?
- **hasStock(product)** — is the product in stock?
- **isEligible(order)** — is the order eligible?
- **isHighValue(order)** — does the order value meet the threshold?

A Predicate should answer a question with a boolean, rather than secretly updating state elsewhere.

## 3. Three Steps: Source, Filter, and Terminal

~~~java
Stream<Integer> pending = List.of(10, 15, 20).stream()
        .filter(n -> n >= 15);

// Here we only build the pipeline; we haven't requested the result yet.
List<Integer> result = pending.toList();
~~~

**filter is a lazy intermediate operation**. Writing **.filter(...)** does not mean the callback runs immediately. Only a terminal operation such as **toList()**, **collect(...)**, **forEach(...)**, **findFirst()**, **count()**, or **anyMatch(...)** triggers enough execution to produce a result.

Visualization:

~~~text
Source List<Order>
      |
      v
stream()
      |
      v
filter(isEligible)  --- only describes element selection
      |
      v
map(toView)         --- only describes transformation
      |
      v
toList()            --- triggers pipeline evaluation
      |
      v
List<OrderView>
~~~

For a source with an encounter order like a List, **filter preserves the relative order of the remaining elements**. If element A precedes B in the source and both are selected, A still precedes B in an ordered pipeline.

### 3.1. Laziness and Fusion

In the pipeline:

~~~java
List<String> names = List.of(" A ", " ", " B ").stream()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase)
        .toList();
~~~

The result is **[A, B]**. On a sequential pipeline with stateless operations like map/filter, Stream typically fuses the steps into **a single pass**, without eagerly creating multiple intermediate Lists for each operation. However, you should not rely on the exact number of callback invocations in every pipeline: terminal operations can short-circuit, stateful operations can change the execution strategy, and the JDK is free to optimize within its contract.

**Lazy does not mean asynchronous.** A sequential Stream still executes at the time the terminal operation is called; it does not spawn background threads on its own.

## 4. Non-Interfering: Do Not Modify the Source During Traversal

**Non-interference** means that the pipeline's behavioral parameters do not interfere with the data source while it is being traversed, except in cases where the source is specifically designed for concurrent modification according to its contract.

An example of **what not to do**:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> result = numbers.stream()
        .filter(n -> {
            numbers.remove(n); // Modifying the source during traversal.
            return n % 2 == 0;
        })
        .toList();
~~~

This is a **counterexample**, not code to run. With ArrayList, structurally modifying it during traversal can lead to **ConcurrentModificationException**, incorrect results, or unexpected behavior depending on the implementation. You should not write tests expecting a fixed exception to justify this pattern.

The right way when you want to filter:

~~~java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> selected = source.stream()
        .filter(n -> n % 2 == 0)
        .toList();

// source still has [1, 2, 3, 4].
// selected is [2, 4].
~~~

If the business logic genuinely requires **removing elements from the original collection**, use an explicit mutation API like **Collection.removeIf(Predicate)** at the appropriate point, **do not put that mutation inside the Predicate of Stream.filter()**.

### 4.1. Differences Between filter and removeIf

| Criterion | **stream().filter(...).toList()** | **collection.removeIf(...)** |
| --- | --- | --- |
| Purpose | Produce a filtered result | Mutate the original collection by removing elements |
| Return value | Result list from Stream.toList | boolean indicating whether the collection was modified |
| Predicate true | **Keep** the element | **Remove** the element |
| Source modified? | No, if the callback does not interfere | May be modified |
| Suitable for | Selecting data, immutable-style processing | Intentional element removal on a mutable collection |

Example:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));
values.removeIf(n -> n % 2 == 0);
System.out.println(values); // [1, 3]
~~~

**removeIf** removes elements for which the Predicate evaluates to true. Therefore, the condition in removeIf has the opposite meaning regarding **keep/remove** compared to filter. In business APIs, use clear names like **shouldKeep** and **shouldRemove** to avoid inverting the meaning.

## 5. Stateless: Predicates Should Not Rely on Mutable State Across Calls

An ideal Predicate for Stream is typically **stateless**: the result of evaluating an element does not depend on mutable variables modified during the evaluation of previous elements.

A **good** example:

~~~java
Predicate<Integer> atLeastTen = n -> n >= 10;
~~~

For the same value of **n**, the rule above always produces the same result under normal conditions, regardless of how many elements have passed through.

A **problematic** example:

~~~java
AtomicInteger seen = new AtomicInteger();

Predicate<Integer> everySecondCall =
        n -> seen.incrementAndGet() % 2 == 0;
~~~

In the second example, the result depends on **the order and number of calls**, not just on n. When changing the source, terminal operation, short-circuiting, or switching to a parallel stream, the selected elements can change. AtomicInteger makes incrementing the counter atomic, but **does not turn an order-dependent rule into a stateless one**.

If you need to **take the first two elements**, use **limit(2)** on an appropriately ordered source. If you need to select elements at **even indices**, model the index explicitly (for example, using IntStream.range and indexed data) instead of counting how many times the Predicate is called.

### 5.1. Capturing Fixed Configuration Is Valid

~~~java
int minimumScore = 80;
Predicate<Student> passes =
        s -> s.score() >= minimumScore;
~~~

This snippet illustrates a **Student** class/record with a **score()** method. **minimumScore** is an **effectively final** local variable, so it can be captured by the lambda. Using a fixed threshold value does not make the Predicate stateful.

If the threshold resides in a mutable configuration object that is modified concurrently, the logic may produce inconsistent results across elements. Use an immutable configuration snapshot or an appropriate synchronization policy when needed.

### 5.2. Stateless Does Not Automatically Mean Pure Function

A Predicate might only read a clock, database, or external state without writing anything itself. Even without mutating directly, its result can still vary between invocations and create reproducibility issues. When filtering data by **a point in time**, you can pass in a fixed reference timestamp provided by the orchestration layer.

Example:

~~~java
Instant referenceTime = Instant.parse("2026-01-01T00:00:00Z");
Predicate<Event> activeAtReference =
        event -> !event.expireAt().isBefore(referenceTime);
~~~

This is an **illustrative snippet** that requires importing Instant and having a matching Event type. This Predicate relies on a fixed **referenceTime** instead of calling **Instant.now()** each time an Event is checked, so all elements are evaluated against the same timestamp.

## 6. Designing Predicates as Named Business Rules

Suppose we have a list of Orders. Instead of cramming a very long condition into filter:

~~~java
orders.stream().filter(o ->
        o != null && o.quantity() > 0
        && o.unitPriceVnd() >= 0 && o.paid()
        && (o.vip() || o.quantity() >= 5)
);
~~~

We can split it into small, named rules:

~~~java
Predicate<Order> notNull = Objects::nonNull;
Predicate<Order> positiveQuantity = o -> o.quantity() > 0;
Predicate<Order> nonNegativePrice = o -> o.unitPriceVnd() >= 0;
Predicate<Order> paid = Order::paid;

Predicate<Order> valid = notNull
        .and(positiveQuantity)
        .and(nonNegativePrice)
        .and(paid);
~~~

These snippets are **fragments** that require declaring the Order record and importing Predicate and Objects; the standalone program in section 10 will complete the scenario.

Benefits:

- **Names express intent**: no need to read a large expression to guess its purpose.
- **Easy to unit test each rule** and test edge cases.
- **Reusable** in other APIs.
- **Easy to compose** using and/or/negate according to specific policies.
- **No unexpected mutation** or side effects if each rule only reads data.

**No need to over-split:** a simple expression `o -> o.paid()` can be written as the method reference **Order::paid**; extracting it into a rule is only beneficial if a clearer rule name adds value or it is reused.

### 6.1. Null Safety and Condition Order

`notNull.and(positiveQuantity)` is safe for null elements because **Predicate.and** short-circuits: if `notNull.test(null)` is false, the next part does not run.

However:

~~~java
Predicate<Order> unsafe = positiveQuantity.and(notNull);
~~~

will call `positiveQuantity.test(null)` first, leading to a **NullPointerException** when accessing **quantity()**. Placing the **null** check before dereferences is part of the contract.

With `Stream.of(...)`, not all sources allow null elements; for example, `List.of(null)` throws NPE immediately upon list creation. So choose an appropriate source if demonstrating null filtering.

## 7. Composing Predicates: and, or, negate, and not

The methods:

| Operator | Meaning | Key Property |
| --- | --- | --- |
| **p.and(q)** | Both p and q are true | If p is false, q is not called |
| **p.or(q)** | Either p or q is true | If p is true, q is not called |
| **p.negate()** | Inverts the boolean of p | Returns true if p is false |
| **Predicate.not(p)** | Negates p (Java 11+) | Often useful with method references |

Example:

~~~java
Predicate<String> notBlank =
        Predicate.not(String::isBlank);

List<String> names = List.of("An", " ", "Chi")
        .stream()
        .filter(notBlank)
        .toList();

System.out.println(names); // [An, Chi]
~~~

**Short-circuiting should not be used to hide side effects.** If q is responsible for mandatory logging or updating data, `p.and(q)` might skip calling q and lose that effect. Predicates should be used to **make decisions**, not to coordinate transactions.

### 7.1. A Rule May Differ from Its Boolean Equivalent

If both p and q are **pure and stateless**, the expressions **p.and(q)** and **q.and(p)** have the same truth value. However, if either one can throw an exception, dereference null, or have side effects, changing the order can alter behavior. Therefore, keep the order of guard conditions explicit.

## 8. filter Before map or map Before filter?

Determine **which data type the Predicate applies to** and **which state the condition belongs to**.

### 8.1. Filter Order Then Map to DTO

~~~java
List<OrderView> views = orders.stream()
        .filter(isEligible)
        .map(toView)
        .toList();
~~~

Here, **isEligible** takes an Order, while **toView** returns an OrderView. If the goal is to exclude invalid Orders **before computing DTOs**, this style is clear; excluded Orders do not pass through the mapper.

### 8.2. Transform First, Then Filter the Transformed Result

~~~java
List<OrderView> expensiveViews = orders.stream()
        .map(toView)
        .filter(view -> view.totalVnd() >= 100_000)
        .toList();
~~~

If the condition needs **totalVnd computed by toView**, we must map first and then filter. Swapping the order is not always valid: sometimes the capability of the Predicate only exists **after transformation**.

When both approaches have the same semantics and the mapper is expensive, filtering early **can** reduce the number of transformations. However, optimization should be based on actual equivalence, boundary data, and test results, not guesswork.

### 8.3. filter and distinct

~~~java
List<String> unique = List.of("A", "B", "A", "C")
        .stream()
        .filter(s -> !s.equals("B"))
        .distinct()
        .toList();
~~~

Result: **[A, C]**. **filter** tests the Predicate; **distinct** is a **stateful** intermediate operation that removes duplicates based on equals/hashCode. For an ordered stream, distinct preserves encounter order among unique elements. If a mutable object is used as a hash key and then mutates unexpectedly, both distinct and hash-based structures can behave confusingly.

## 9. filter with limit, findFirst, and anyMatch

### 9.1. limit Changes How Much Input Needs Traversal

~~~java
List<Integer> firstTwoEven = List.of(1, 2, 3, 4, 5, 6)
        .stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
~~~

Result: **[2, 4]**. In a simple ordered sequential pipeline, once two even numbers are found, subsequent elements may not need to be examined.

Conversely:

~~~java
List<Integer> evenAmongFirstTwo = List.of(1, 2, 3, 4, 5, 6)
        .stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList();
~~~

Result: **[2]**, because only the first two elements, 1 and 2, are passed through filter. **Swapping the order of filter and limit can change the meaning**.

### 9.2. findFirst

~~~java
Optional<Integer> firstEven = List.of(1, 3, 4, 6)
        .stream()
        .filter(n -> n % 2 == 0)
        .findFirst();
~~~

`firstEven` contains 4. **findFirst** is a terminal operation that can stop early and returns Optional.empty if no element is selected. It respects encounter order if the stream is ordered.

### 9.3. anyMatch Is Sometimes Better Than filter + find

When you only need to answer **"does any element match the condition?"**:

~~~java
boolean anyEven = List.of(1, 3, 4, 6)
        .stream()
        .anyMatch(n -> n % 2 == 0); // true
~~~

**anyMatch(predicate)** expresses the intent more directly than `filter(predicate).findAny().isPresent()`. Both can short-circuit, but you should not treat the number of callback invocations as a business contract.

### 9.4. filter Does Not Catch Exceptions Automatically

If a Predicate throws an exception, the terminal operation can fail. **filter** does not silently "skip failing elements" unless the Predicate actively catches the error and returns false. Avoid catching all network/database errors and treating them as invalid data if the business logic must distinguish those cases.

## 10. Complete Java 17 Program: Filtering Orders Without Mutating the Source

The example below has five orders. We will:

- Define **named Predicates** for valid data and payment conditions.
- Select eligible orders without mutating the source list.
- Further select VIP orders by composing Predicates.
- Transform the result into display labels after filtering.
- Demonstrate laziness using an observation counter **for test/demo purposes**, without treating the counter as business logic.

Create the file **FilterPredicateDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.stream.Stream;

public class FilterPredicateDemo {
    record Order(
            String id,
            int quantity,
            long unitPriceVnd,
            boolean paid,
            boolean vip) { }

    static List<String> ids(List<Order> orders) {
        return orders.stream().map(Order::id).toList();
    }

    public static void main(String[] args) {
        List<Order> source = List.of(
                new Order("A", 2, 15_000, true, true),
                new Order("B", 1, 10_000, true, false),
                new Order("C", 0, 7_000, true, true),
                new Order("D", 3, 4_000, false, true),
                new Order("E", 1, 9_000, true, true)
        );

        Predicate<Order> positiveQuantity =
                o -> o != null && o.quantity() > 0;
        Predicate<Order> nonNegativePrice =
                o -> o.unitPriceVnd() >= 0;
        Predicate<Order> paid = Order::paid;
        Predicate<Order> vip = Order::vip;

        Predicate<Order> eligible = positiveQuantity
                .and(nonNegativePrice)
                .and(paid);

        List<Order> accepted = source.stream()
                .filter(eligible)
                .toList();

        List<Order> vipAccepted = source.stream()
                .filter(eligible.and(vip))
                .toList();

        List<String> vipTotals = vipAccepted.stream()
                .map(o -> o.id() + ":" + Math.multiplyExact(
                        (long) o.quantity(), o.unitPriceVnd()))
                .toList();

        System.out.println("source IDs: " + ids(source));
        System.out.println("eligible IDs: " + ids(accepted));
        System.out.println("VIP IDs: " + ids(vipAccepted));
        System.out.println("VIP totals: " + vipTotals);
        System.out.println("source size: " + source.size());

        AtomicInteger examined = new AtomicInteger();
        Stream<Order> pending = source.stream()
                .filter(o -> {
                    examined.incrementAndGet();
                    return eligible.test(o);
                });

        System.out.println("before terminal: " + examined.get());
        long count = pending.count();
        System.out.println("eligible count: " + count);
        System.out.println("after terminal: " + examined.get());
    }
}
~~~

Compile and run with **JDK 17 or higher**:

~~~bash
javac FilterPredicateDemo.java
java FilterPredicateDemo
~~~

**Exact output for this sequential program:**

~~~text
source IDs: [A, B, C, D, E]
eligible IDs: [A, B, E]
VIP IDs: [A, E]
VIP totals: [A:30000, E:9000]
source size: 5
before terminal: 0
eligible count: 3
after terminal: 5
~~~

### 10.1. Output Explanation

1. **source** is a List.of containing five Order records; it preserves the order A, B, C, D, E.
2. **positiveQuantity** returns false for C because quantity=0. The other orders have positive quantity.
3. **paid** returns false for D, so D is excluded. The result of **eligible** is A, B, E; the original encounter order is preserved.
4. **eligible.and(vip)** further excludes B because it is not VIP, leaving A and E.
5. **map** runs after filter, computing the label `id:totalVnd`. A has 2 × 15,000 = 30,000; E has 1 × 9,000 = 9,000. **Math.multiplyExact** detects long overflow if any occurs.
6. **source size: 5** shows that filtering does not remove records from the source.
7. The **pending** pipeline is built with filter but has not been consumed yet, so **before terminal: 0**.
8. The terminal **count()** on a pipeline with filter must determine how many elements match the condition, so for this sequential List it invokes the filter's Predicate for all five Orders: **eligible count: 3**, **after terminal: 5**.

**Important note:** incrementing **examined** inside the Predicate is only for demonstrating lazy evaluation. It is a side effect; do not use this counter as an essential part of business logic, because the callback invocation count can change when the terminal operation, source, or execution strategy changes. With a `count()` pipeline that has `filter` as in the example, counting by traversal is expected; however, `count()` on a sized source **without a filter** can be optimized without running preceding `map/peek` steps.

### 10.2. Why Do Records Help the Example?

**Order** is a record containing String and primitives, so in this example it has stable data state. The Predicate only reads accessors and returns a boolean without mutating the record. This makes the example easy to reason about and test.

However, **records do not automatically guarantee deep immutability**: if a record contains a mutable List, code can still modify the List's contents through its reference. When a snapshot of data is needed for business purposes, clearly define ownership and copying depth.

## 11. Not Changing Source Structure Does Not Mean Not Changing Objects

If a list contains mutable objects:

~~~java
class Product {
    private int stock;

    Product(int stock) {
        this.stock = stock;
    }

    int stock() {
        return stock;
    }

    void decrease() {
        stock--;
    }
}
~~~

A Predicate written like this is **problematic**:

~~~java
Predicate<Product> hasStock = product -> {
    product.decrease();           // Side effect.
    return product.stock() > 0;
};
~~~

This snippet uses the Product declared above; do not use this approach for filtering.

Even though filter does not add/remove elements in the source List, **each Product is still the exact same object referenced from the source**. Calling decrease mutates the Product. Therefore, you cannot conclude "the original list did not change" in the sense that **all element states remained intact**.

The design should be:

~~~java
Predicate<Product> hasStock =
        product -> product != null && product.stock() > 0;
~~~

And if stock needs to be updated, do it in a **separate business step** with a clear contract for validation, locking, transactions, and error handling. Similarly, after `toList()`, the resulting list is unmodifiable, but mutable elements inside it can still be modified through the object's methods.

## 12. Source Snapshots and Concurrent Modification

A standard Stream pipeline **does not mean snapshotting the source at the moment stream() is called**. If a mutable list is modified by another thread while the terminal operation is traversing it, you may encounter exceptions, inconsistent data, or unexpected behavior depending on the source. The Stream API requires non-interfering behavioral parameters except for sources designed for concurrent access.

If you need to filter a snapshot of a list at a specific point in time:

~~~java
List<Order> snapshot = List.copyOf(orders);
List<Order> selected = snapshot.stream()
        .filter(eligible)
        .toList();
~~~

This is a snippet with **orders** and **eligible** in context. **List.copyOf** creates a list that does not support mutation and does not accept null elements; it **does not deep-copy** mutable Orders. In addition, if the source list itself is being modified concurrently while creating the copy, that behavior still needs to be managed with appropriate synchronization/ownership.

The main goal is not always to make a copy—sometimes the source list is already immutable or owned by a single thread—but rather to **know clearly who has the right to modify the source and when**.

## 13. filter on Parallel Streams: The Predicate Must Be Suitable

~~~java
List<Integer> result = numbers.parallelStream()
        .filter(n -> n > 0)
        .toList();
~~~

A Predicate that only reads n and holds no mutable state can be applied concurrently to multiple elements by the library. When the source has an encounter order (such as a List), the result of `toList()` still conforms to the stream's guaranteed order; however, **the order/timing of Predicate invocations across threads is not fixed**.

A dangerous example:

~~~java
int[] counter = {0};

Predicate<Integer> alternate = n ->
        ++counter[0] % 2 == 0;
~~~

The lambda captures an effectively final **array reference** but **modifies the array's contents**, so it still has a side effect. With a parallel stream, this is also unsynchronized shared mutable state, causing a race condition. Even if AtomicInteger is used to fix the race, the filter result still depends on callback order rather than a stable rule over the data.

Better alternatives:

- Turn the predicate into a check based on the element's data, not on invocation order.
- When business logic depends on position, use explicit indices on an ordered source, such as `IntStream.range(0, list.size())`.
- If you genuinely need to update state, separate updates from filter and use a collector or controlled business API.
- Only use parallel after measuring performance, considering split/merge overhead and the safety of the entire pipeline.

Calling `parallel()` does not automatically make things faster; for small datasets or lightweight work, the overhead can outweigh the benefits.

## 14. Nulls, Exceptions, and Filtering Faulty Data

### 14.1. Nulls in the Source

If the source may contain nulls, you can filter them out first:

~~~java
List<String> values = new ArrayList<>();
values.add("An");
values.add(null);
values.add("Chi");

List<String> safe = values.stream()
        .filter(Objects::nonNull)
        .filter(s -> !s.isBlank())
        .toList();
~~~

This snippet requires importing List, ArrayList, and Objects. The result is **[An, Chi]**; the order of conditions matters because `String::isBlank` throws NPE if it encounters null before filtering.

### 14.2. Distinguishing Ineligible Elements from Faulty Data

If a rule checks a normal business condition like "order is paid", **false** means the order is **not selected**. But if the check must query a database and hits a connection error, arbitrarily returning false will **mask an outage as invalid data**.

When you need the reason, instead of a Predicate returning only a boolean, you can use a result type such as `ValidationResult` or `Decision` that carries details. If business requirements demand reporting errors for every invalid order, **filtering and dropping elements** may not be appropriate; split the data into valid and error groups or produce stateful results instead.

### 14.3. Checked Exceptions

The SAM of Predicate is `boolean test(T t)`, which declares no checked exceptions. A lambda calling a method that throws a checked exception must handle it itself or use another suitable abstraction. Do not catch broad `Exception` and return false for all errors just to keep `filter` going.

## 15. Performance and Optimization Order

### 15.1. Cheap Conditions Before Expensive Conditions

In `p.and(q)`, if p is false then q does not run. When two conditions are **pure, logically equivalent, and order-independent**, placing a cheap check that eliminates many elements first can reduce work:

~~~java
Predicate<Order> validQuantity = o -> o.quantity() > 0;
Predicate<Order> expensiveEligibility = o -> checkRule(o);

Predicate<Order> combined =
        validQuantity.and(expensiveEligibility);
~~~

Here `checkRule` is an undefined illustrative method. Only reorder when it does not break semantics, null safety, or error contracts. If expensiveEligibility has a side effect that must execute regardless of the first condition, **it should not be a Predicate used in and**.

### 15.2. Filter Before Heavy Transformations When Semantically Valid

~~~java
List<View> views = orders.stream()
        .filter(isEligible)
        .map(thisService::expensiveView)
        .toList();
~~~

This is a fragment inside a class with corresponding variables and methods. If an Order is excluded, the mapper does not need to construct its View. However, if the eligibility decision depends on a value computed inside expensiveView, you must redesign the data or pipeline order to match the requirements.

### 15.3. Mind Traversal Count and Source Size

If you need to use the filtered results multiple times, you can store the result once:

~~~java
List<Order> eligibleOrders = orders.stream()
        .filter(isEligible)
        .toList();

long count = eligibleOrders.size();
~~~

Do not rebuild the pipeline multiple times when filtering is expensive, state-dependent, or data can change between passes. Conversely, if the dataset is very large and you only need a count, **count()** may be more suitable than creating a List. Choose based on need rather than materializing every stream by default.

## 16. Testing Predicates and filter

### 16.1. Unit Testing Individual Predicates

For the eligible rule in the section 10 example, test:

1. Quantity > 0, unitPrice >= 0, and paid = true → true.
2. Quantity = 0 → false.
3. Negative quantity → false.
4. Negative unitPrice → false.
5. Unpaid → false.
6. Null → false if the rule checks null first.

Example:

~~~java
Order valid = new Order("X", 1, 1000, true, false);
Order invalid = new Order("Y", 0, 1000, true, true);

if (!eligible.test(valid)) {
    throw new AssertionError("Valid order rejected");
}
if (eligible.test(invalid)) {
    throw new AssertionError("Invalid order accepted");
}
~~~

This snippet uses the Order and eligible declarations from the program in section 10; it is not a standalone file.

### 16.2. Testing Source Non-Mutation

In code using immutable records like the example:

~~~java
List<Order> before = List.copyOf(source);

List<Order> selected = source.stream()
        .filter(eligible)
        .toList();

if (!source.equals(before)) {
    throw new AssertionError("Source changed");
}
~~~

With **records containing value-immutable fields** like the Order example, this check helps verify that source elements remain intact in tests. If the data contains mutable objects, merely comparing two Lists holding the same element references may **fail to detect content mutations**; in that case, compare value snapshots of the relevant properties.

### 16.3. Testing Order and Results

For a source List with encounter order, verify the exact list of selected IDs, not just the count. Getting the right result does not mean a Predicate with side effects works safely in all modes; you also need to check non-interference, state independence, and error handling.

### 16.4. Testing Short-Circuiting and Terminal Operations

A test can demonstrate **lazy filtering** by observing a counter before the terminal operation. However, you should not lock the exact callback invocation count of every terminal/parallel pipeline into an invariant if the contract does not guarantee it. Production tests should prioritize the final result and well-defined effects at business boundaries.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mutating the collection inside `filter` | Source interference, unreliable results | Predicate only checks; use removeIf separately if removal is needed |
| Mutating object fields inside Predicate | Results may mutate source data | Separate mutation from filtering |
| Using a mutable counter to decide keep/remove | Depends on callback count and order | Use a stateless rule or explicit indices |
| Using `filter` and forgetting a terminal operation | Pipeline is never consumed | Add an appropriate terminal operation |
| Calling `filter(...).count()` then reusing the stream | A Stream can only be consumed once | Create a new stream |
| Assuming `toList()` creates a deep copy | Mutable elements are still shared | Deep-snapshot when business logic requires it |
| Assuming `toList()` returns a mutable ArrayList | `Stream.toList()` does not support mutation | Use a collector/mutable copy if needed |
| Forgetting null checks before dereferencing | NullPointerException | `Objects::nonNull` or a guard rule first |
| Using `filter` to swallow system errors | Database errors treated as "condition not met" | Distinguish false from exceptions/error results |
| Swapping `limit` and `filter` | Selects a different set of elements | Keep the correct business order |
| Using `parallelStream` with a mutable predicate | Race conditions, instability | Use stateless/non-interfering Predicates |
| Confusing `removeIf` and `filter` | Inverted keep/remove semantics | Remember filter true = keep, removeIf true = remove |
| Putting mandatory logging in `peek` | Callback may be optimized away | Put effects in a step designed for execution |

## 18. Practice Exercises

### Exercise 1 — Filtering In-Stock Products

Given the record:

~~~java
record Product(String name, int stock, boolean active) { }
~~~

Write a Predicate that selects products that are **active** and have **stock > 0**.

**Suggested answer:**

~~~java
Predicate<Product> hasStock = p -> p.stock() > 0;
Predicate<Product> active = Product::active;
Predicate<Product> available = hasStock.and(active);
~~~

This is a fragment using the Product record above; in systems allowing nulls, add `p != null` before dereferencing. Products with stock=0 are not selected; products with active=false are also excluded.

### Exercise 2 — filter with limit

Given the sequence `[1, 2, 3, 4, 5, 6]`. Compare:

~~~java
numbers.stream().filter(n -> n % 2 == 0).limit(2).toList();
numbers.stream().limit(2).filter(n -> n % 2 == 0).toList();
~~~

**Answer:** **[2, 4]** and **[2]**, respectively. The first takes **the first two even numbers**, while the second only checks **the first two elements**.

### Exercise 3 — Fixing Side Effects in filter

Old code:

~~~java
List<Customer> selected = customers.stream()
        .filter(c -> {
            c.setChecked(true);
            return c.isActive();
        })
        .toList();
~~~

Redesign it so the Predicate only asks **c.isActive()**. If the business logic needs to mark them as processed, create a separate step responsible for writing state and handling errors, rather than assuming a Predicate call is guaranteed to be a transaction.

**Hint:**

~~~java
Predicate<Customer> active = Customer::isActive;
List<Customer> selected = customers.stream()
        .filter(active)
        .toList();
~~~

This snippet illustrates a Customer class with `isActive()`. If marking is still required, do it in a business operation with a clear contract, not inside the Predicate.

### Exercise 4 — Designing an API Accepting a Predicate

Write a method that takes a list of T and a selection condition, returning a new list:

~~~java
static <T> List<T> select(
        List<T> source,
        Predicate<? super T> predicate) {
    return source.stream().filter(predicate).toList();
}
~~~

**Improvement hint:** validate null for source/predicate according to the API contract. `? super T` allows passing a Predicate that accepts a supertype of T. Test with List<String> and Predicate<CharSequence>.

### Exercise 5 — Filtering Data While Still Reporting Errors

A batch has ten orders, three of which have invalid data. Business requirements demand **displaying an error list for all three orders**, not just dropping them. Should you use `filter(valid)` alone?

**Answer:** not enough. `filter` only keeps/drops based on a boolean and does not store the reason. Create a `ValidationResult` or a workflow that splits data into valid and error groups with details, then process the valid group. You can still use Predicates for simple checks, but you need a richer result type for error reporting.

## 19. Takeaways

**Stream.filter(Predicate)** describes an **element selection** operation, returning a Stream of the same type T without needing to modify the source collection. **filter itself is lazy**; only a terminal operation triggers pipeline evaluation. With an ordered source, filter preserves the relative order of the selected elements.

A good Predicate for use in a Stream should:

- **Only check** and return a boolean; do not modify the source being traversed.
- **Not depend on mutable state across invocations**; use stable configuration.
- **Have a clear name and contract**, especially for business rules that can be composed with and/or/negate.
- **Handle nulls/exceptions intentionally**, without conflating false with infrastructure failures.
- **Not rely on callback count or order** when short-circuiting, optimizations, or parallelism are involved.
- **Distinguish list structure from object state**: the toList result does not modify the source structure, but it does not deep-copy mutable elements.

When you need to filter, use **filter**. When you need to delete from the original collection, use a clearly named mutation operation like **removeIf**. When you need to report errors instead of dropping elements, choose a result model that carries validation details. Separating these three responsibilities keeps Java pipelines both readable and reliable.
