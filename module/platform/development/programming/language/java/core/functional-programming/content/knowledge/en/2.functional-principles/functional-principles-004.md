# Immutable Data and Limiting Shared Mutable State in Java

## 1. Why is this a core principle of functional programming?

**Immutable data** is data whose observable state does not change after creation. **Shared mutable state** is data that can be read and modified concurrently by multiple pieces of code or threads of execution. Limiting shared mutable state makes programs easier to reason about, test, compose transformations, and handle concurrency safely.

In Java, functional programming is a *design style*; it does not mean every variable or every object must be immutable. The practical goals are:

1. Each processing step takes inputs and produces a **new result** instead of silently mutating the inputs.
2. Use functions with few or no *side effects* in `map`, `filter`, `reduce`, and other transformations.
3. When multiple places need the same value, prefer sharing **immutable values**; if mutation is needed, clearly define the owner of that mutation.
4. Perform database writes, UI updates, logging, API calls, and other side effects at controlled boundaries.

Consider a list of orders. If a price calculation function silently removes line items, or a lambda modifies a shared counter during a `parallelStream()`, the same call can produce unpredictable results. If the input is protected from unintended modification and the total price is a read-only function, the result will be more stable.

## 2. Distinguishing `final`, immutability, and unmodifiable collections

The following mechanisms have different scopes:

| Mechanism | Guaranteed | What is **not** guaranteed |
| --- | --- | --- |
| `final` local variable | The variable cannot be reassigned to another reference/value | Does not prevent mutating the referenced object |
| `private final` field | The field is assigned during initialization according to Java's rules | If the field references a mutable object, the object's contents can still change |
| `record` | Auto-generates accessors, constructor, `equals`/`hashCode`/`toString` based on components; instance fields are `final` | Does not automatically deep-copy `List`, arrays, or mutable components |
| `Collections.unmodifiableList(list)` | Blocks modifications *through the wrapper* | Data seen through the wrapper still changes if someone mutates the original `list` |
| `List.copyOf(list)` | The resulting list is unmodifiable; creates a structural snapshot unaffected by subsequent structural changes to the source | Does not make the elements inside immutable |
| `Stream.toList()` (Java 16+) | The resulting list cannot be modified via `add`, `set`, `remove` | Does not deep-copy elements; does not automatically protect referenced mutable objects |

For example, `final List<String> names = new ArrayList<>()` still allows `names.add("Lan")`; it only disallows `names = otherList`. `final` protects the *reference variable*, whereas immutability requires protecting the *observable state of the object*.

### A read-only wrapper is a "window" into the original collection

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

The snippet above is an illustration to be placed inside a method or `jshell`. `view` does not allow calling `view.add(...)`, yet it still sees elements added to `source`. `snapshot` does not change when `B` is added to `source`. Neither allows direct modification operations through the list itself. Factory methods for unmodifiable collections like `List.of` and `List.copyOf` also do not accept `null` elements.

> **Shallow immutability vs. deep immutability:** a structurally unmodifiable list can still contain mutable objects. If a `List<PersonMutable>` contains an object with `setName`, changing the name through another reference will still make the name in the list appear to change. You must consider the immutability of the entire related object graph, not just the outermost collection.

## 3. Immutable data modeling with Java 17

We use `record` to represent a line item and an order. `String` and `BigDecimal` are immutable types; the list of line items is defensively copied (*defensive copy*). The total calculation function only reads data and returns a new value.

Four important rules:

- **Validate inputs:** reject blank codes, invalid quantities, negative prices, and `null` values.
- **Copy on entry:** when the constructor receives a `List` from outside, call `List.copyOf`.
- **Do not expose mutation paths via accessors:** the `items()` accessor returns an unmodifiable list.
- **Do not hide mutable state inside a record:** `Item` elements only contain `String`, `int`, and `BigDecimal`.

These rules create an `Order` object whose state is immutable with respect to the operations exposed in the example. A record is **not deeply immutable by default** if its components contain an array, `Date`, or another mutable class.

## 4. Complete program: modifying by creating a new value

Create the file **`ImmutableOrderDemo.java`**. The example runs on **Java 17+** and requires no libraries outside the JDK.

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class ImmutableOrderDemo {
    record Item(String sku, int quantity, BigDecimal unitPrice) {
        Item {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Order(String id, List<Item> items) {
        Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(items, "items");
            if (id.isBlank()) {
                throw new IllegalArgumentException("Blank order id");
            }
            items = List.copyOf(items); // Prevent external structural modification
        }

        BigDecimal total() {
            return items.stream()
                    .map(Item::total)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }

    // Do not mutate the original order: create a new Order with a new list.
    private static Order withAdditionalItem(Order order, Item additional) {
        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(additional, "additional");
        List<Item> next = new ArrayList<>(order.items());
        next.add(additional);
        return new Order(order.id(), next);
    }

    public static void main(String[] args) {
        List<Item> editable = new ArrayList<>(List.of(
                new Item("BOOK", 2, money("120000")),
                new Item("PEN", 3, money("10000"))
        ));

        Order original = new Order("A01", editable);

        // Mutating the source after creating Order does not mutate data inside Order.
        editable.clear();
        System.out.println("Nguon sau clear: " + editable.size());
        System.out.println("Don goc - so dong: " + original.items().size());
        System.out.println("Don goc - tong: " + original.total().toPlainString());

        Order updated = withAdditionalItem(
                original,
                new Item("BAG", 1, money("200000"))
        );
        System.out.println("Don moi - so dong: " + updated.items().size());
        System.out.println("Don moi - tong: " + updated.total().toPlainString());
        System.out.println("Don goc sau bien doi: "
                + original.total().toPlainString());

        Order second = new Order("A02", List.of(
                new Item("PEN", 5, money("10000"))
        ));
        List<Order> orders = List.of(original, second);

        // map + reduce: no shared accumulator variable needed.
        BigDecimal revenue = orders.stream()
                .map(Order::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tong hai don: " + revenue.toPlainString());

        // Collector produces a new result from the input data.
        Map<String, BigDecimal> totalsById = orders.stream()
                .collect(Collectors.toUnmodifiableMap(
                        Order::id,
                        Order::total
                ));
        System.out.println("A02 trong map: "
                + totalsById.get("A02").toPlainString());

        // Read-only functions + reduce allow safe parallel aggregation.
        BigDecimal parallelTotal = orders.parallelStream()
                .map(Order::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tong song song: "
                + parallelTotal.toPlainString());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 ImmutableOrderDemo.java
java ImmutableOrderDemo
```

**Exact expected stdout:**

```text
Nguon sau clear: 0
Don goc - so dong: 2
Don goc - tong: 270000
Don moi - so dong: 3
Don moi - tong: 470000
Don goc sau bien doi: 270000
Tong hai don: 320000
A02 trong map: 50000
Tong song song: 320000
```

The values can be verified by hand:

- Initial A01: `2 × 120000 + 3 × 10000 = 270000`.
- New A01: `270000 + 1 × 200000 = 470000`. The value of `original` remains `270000`.
- A02: `5 × 10000 = 50000`.
- Sum of `original` and A02 in `orders`: `270000 + 50000 = 320000`. The `orders` list intentionally contains **original**, not `updated`; this is why the result is not `520000`.
- `parallelStream` applies `map` and `reduce` on the same set of two orders with `BigDecimal` addition, so the sum is still `320000`.

The program prints the value directly by order ID instead of iterating over the `Map`, because `Collectors.toUnmodifiableMap` **does not guarantee key iteration order**. `toUnmodifiableMap` also requires unique keys in its two-argument overload; two orders with the same `id` will throw `IllegalStateException` during the collect step. This is something to check when order IDs come from real data.

## 5. Functional-style "transformation": creating a new value from an old value

The `withAdditionalItem` function performs three steps:

1. Accepts the input `Order` and a new `Item`.
2. Creates an **internal** `ArrayList` from the old list, adding the element on the copy.
3. Creates a new `Order`; the constructor protects the list again using `List.copyOf`.

Using a **local** mutable variable while building a result does not violate the goal of reducing shared mutable state: the temporary list is owned solely by a single function call and is never returned outside. The key point is that the function **does not mutate the input object** and does not retain that mutable variable for other callers to affect.

Compare two approaches to fulfilling a "add item to order" requirement:

```java
// Approach with side effects, assuming MutableOrder has a getter returning a mutable List:
void addItemInPlace(MutableOrder order, Item item) {
    order.getItems().add(item); // Callers may observe the old Order changing state.
}

// Approach creating a new value, using the program's immutable Order type:
Order withAdditionalItem(Order order, Item item) {
    List<Item> next = new ArrayList<>(order.items());
    next.add(item);
    return new Order(order.id(), next);
}
```

The `MutableOrder` snippet is **illustrative code**, not an addition to paste into `ImmutableOrderDemo.java`. Immutable transformations usually cost more allocations/copies than in-place mutations, but in return they reduce hidden dependencies. For very large collections or frequent updates, consider persistent/structural sharing data structures from an appropriate library; JDK `List.copyOf` does not provide a general-purpose persistent data structure for appending elements.

## 6. Pure functions, side effects, and testability

A **pure function** has two properties:

- Given the same inputs by value, it returns the same result.
- It has no observable side effects: it does not modify inputs, global variables, files, databases, UI, or external state.

`Item.total()`, `Order.total()`, and `withAdditionalItem(...)` are examples close to pure design in this article. These functions are easy to test by passing deterministic data and comparing outputs; there is no need to set up a database, fake clock, or global variables. `Order.total()` also uses immutable `BigDecimal`, so `add` produces a new value without mutating the previous sum.

Conversely, the following operations have side effects: `System.out.println`, sending HTTP requests, writing files, calling `repository.save(...)`, updating an `AtomicInteger`, or adding an element to a list to which someone else holds a reference. Side effects **are not always wrong**. Application code must interact with the outside world; you should organize them at the orchestration/I/O layer, while business transformation logic can run independently and be tested conveniently.

Example illustrating how to separate computation and display:

```java
// Computation function: does not print and does not mutate the orders list.
BigDecimal calculateRevenue(List<Order> orders) {
    return orders.stream()
            .map(Order::total)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
}

// At the calling layer:
BigDecimal revenue = calculateRevenue(orders);
System.out.println(revenue.toPlainString());
```

This is a **method sketch** using the `Order` types defined in the earlier program; it is not a standalone program. This design lets you test `calculateRevenue` without capturing stdout.

## 7. Lambdas, `effectively final` variables, and the real limits of the rule

Lambdas can read local variables declared `final` or **effectively final** (never reassigned after initialization):

```java
BigDecimal threshold = new BigDecimal("100000");
List<Order> expensive = orders.stream()
        .filter(order -> order.total().compareTo(threshold) > 0)
        .toList();
```

Even without writing the `final` keyword, `threshold` is still effectively final because it is not reassigned. If you try to reassign `threshold` elsewhere in the same scope, the lambda using it will not compile. However, being effectively final **does not make the state of the captured object immutable**:

```java
// Counterexample: compiles, but has side effects.
List<String> output = new ArrayList<>();
orders.stream()
        .map(Order::id)
        .forEach(output::add); // Writes to an external mutable list.
```

The `output` variable is not reassigned, yet the list's contents are mutated. In a small sequential pipeline, this operation may produce the expected result, but it increases hidden dependencies and easily turns into a bug when switching to parallel execution.

Prefer collecting results with a terminal operation:

```java
List<String> ids = orders.stream()
        .map(Order::id)
        .toList(); // Creates a result list that cannot be modified via the List API.
```

`map` should describe a transformation. `peek` should also not be used as a place to put state-updating logic: it primarily supports observation/debugging and does not guarantee that every side effect will run under all pipeline optimizations (for example, short-circuiting or `count` on a sized source).

## 8. Why does shared mutable state cause bugs especially in parallel processing?

Suppose we want to sum the numbers from 1 to 10000. The following snippet uses an array as a sum holder and has multiple threads mutate it concurrently:

```java
// COUNTEREXAMPLE: do not use to compute a correct sum.
int[] shared = {0};
java.util.stream.IntStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(n -> shared[0] += n);

System.out.println(shared[0]); // No guarantee this equals 50005000.
```

`shared[0] += n` consists of a read, an addition, and a write; it is not an atomic operation. Multiple threads can read the same stale value and overwrite each other's results (*lost update*). The Java Memory Model also does not guarantee that these unsynchronized accesses have a proper happens-before relationship. Running once and getting the right answer does not prove the code is safe.

How to express the computation as a **reduction**:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 10_000)
        .parallel()
        .sum();
System.out.println(sum); // 50005000
```

`sum()` lets the Stream API manage intermediate results and combining operations. For the range 1..10000, the result fits in an `int`; for sums that may exceed `int` limits, choose `LongStream` or `BigInteger` as required.

If you must update a shared counter for a specific reason (for example, an external task metric outside the pipeline), you can use `AtomicLong`/`LongAdder` or appropriate locking. However, counting/aggregating **stream results** should usually be done with `count()`, `sum()`, `reduce()`, or `collect()`, avoiding unnecessary shared mutable state.

### Notes on collectors and associative operators

Operators used in parallel reduction must have the right **associativity**, **identity element**, and no unintended side effects:

- Integer addition without overflow and `BigDecimal` addition are straightforward examples.
- Do not use subtraction `a - b` as an arbitrary operator for `reduce(identity, accumulator)` in a parallel stream because subtraction is not associative.
- Do not let an accumulator mutate the same `ArrayList` or `HashMap` shared across multiple stream branches.
- `Collectors.toList()`/`groupingBy(...)` have their own container/combiner mechanisms under the collector contract; the result itself may be mutable, and that **does not mean** threads are racing to write into a single container in an ad-hoc manner.

`parallelStream()` is also not automatically faster: splitting, coordination, allocation, and data size affect performance. Choose parallelism only after semantic correctness is established and actual performance is measured.

## 9. Thread safety: what immutability helps with and what it does not

A properly initialized immutable object is generally easy to share across threads because threads only read the same state. For objects with `final` fields, the Java Memory Model provides important initialization guarantees when the constructor completes properly; do not let `this` escape while the object is still being constructed. In the example, `Order` holds a `List.copyOf` of `Item`s with immutable components, so reading `total()` needs no locks to protect `Order`'s internal state.

However, we must distinguish:

1. **Immutable object**: the state of that value itself does not change.
2. **Safely published/handed-off reference**: other threads receive the reference through an appropriate mechanism. Use `final`, `volatile`, locks, concurrent queues, or synchronization mechanisms depending on the situation.
3. **Atomic business operation sequence**: for example, "check balance then deduct money" still requires a transaction/synchronization even when each transaction record is an immutable value.

For example, replacing an entire application configuration with a new immutable configuration value can be safe when the configuration reference is published via `volatile` or `AtomicReference`. If concurrent updates based on the previous value are needed, you must use atomic compare-and-set operations or proper synchronization; merely creating an immutable object is not enough.

Avoid two overgeneralizations: **"records are always thread-safe"** (false if they contain mutable components or methods accessing external state) and **"using Streams is automatically thread-safe"** (false if lambdas touch shared mutable variables).

## 10. Choosing a strategy in real applications

| Scenario | Approach | Reason |
| --- | --- | --- |
| Read-only DTOs, configuration, value objects | `record` + immutable components + defensive copy | Easy to share and compare by value |
| Input list received from caller | `List.copyOf` after validation | Cannot be structurally modified from outside |
| Building a result in multiple steps | Mutable builder or local `ArrayList`, then snapshot | Convenient to construct without leaking temporary state |
| Filtering, sorting, aggregating data | `filter`/`map`/`toList`/`reduce`/`collect` | Each step clearly describes the transformation |
| Truly concurrent counter updates | `AtomicLong` or `LongAdder` when appropriate | Synchronizes updates to state that must be shared |
| Updating relationships across multiple records | Transaction/lock/appropriate conditional update | Preserves business invariants across multiple operations |
| Mutable cache or dynamic configuration | Clear state ownership, synchronization/atomic publication | Immutability of a single value does not replace coordination mechanisms |

Creating copies is not always the cheapest option. For very large arrays, high-performance algorithms, or high-volume processing, you can use a mutable buffer with exclusive ownership within a small scope. What to avoid is passing mutable references to many places without clearly defining mutation rights and synchronization.

## 11. Mistakes to spot during code review

**Mistake 1 — Believing `final` makes a list immutable.** `final List<Item> items = new ArrayList<>()` still allows `items.add(...)`. To protect data, control the constructor, accessors, and the type of each element.

**Mistake 2 — A record keeping the caller's mutable reference as-is.**

```java
// Counterexample: the caller can still mutate the items list.
record UnsafeOrder(String id, List<String> items) {}

List<String> source = new ArrayList<>(List.of("BOOK"));
UnsafeOrder unsafe = new UnsafeOrder("A01", source);
source.add("PEN");
System.out.println(unsafe.items()); // [BOOK, PEN]
```

The snippet above illustrates the **shallow immutability** mistake in a record. The `Order` constructor in the main program uses `List.copyOf(items)` to address this case.

**Mistake 3 — Returning `Collections.unmodifiableList` and assuming it is a snapshot.** The wrapper still reflects modifications made to the original list. Choose `List.copyOf` if you want a snapshot of the list's structure.

**Mistake 4 — Using `forEach` to accumulate results manually.** `list.parallelStream().forEach(x -> total[0] += x)` has a data race. Replace it with a reduction/collector or a synchronized update mechanism if a side effect is truly required.

**Mistake 5 — Assuming `collect` returns immutable data by default.** `Collectors.toList()` makes no guarantees about the `List` type, mutability, serializability, or thread safety of the result. Java 17's `Stream.toList()` guarantees an unmodifiable list; for maps, use `Collectors.toUnmodifiableMap(...)` when appropriate and handle duplicate/`null` keys explicitly.

**Mistake 6 — Mutating elements inside an unmodifiable list.** `List.copyOf` only protects the structure of the list; it does not turn `Date`, arrays, `StringBuilder`, or user-defined objects into immutable ones.

**Mistake 7 — Calling code with side effects inside `map` and relying on execution count.** Streams have lazy evaluation and may short-circuit; write transformations without side effects, and do not depend on how many times a lambda is invoked beyond what the API guarantees.

**Mistake 8 — Confusing "no shared state" with "no state".** Local mutable state that does not escape the method and is not shared can be a safe and simple implementation detail. Clarity of data ownership is the core point.

## 12. Self-check exercises

1. Change `editable.clear()` to `editable.add(new Item("BAG", 1, money("200000")))` after creating `original`. Explain why `original.total()` is still `270000`.
2. Create a record containing `int[] scores`. Show two ways the data can be mutated after the record is created: through the source array and through the accessor. Fix it by cloning/copying on input and on return, or design the API using a safe collection and immutable elements.
3. From `orders`, build a list of order IDs whose total is greater than `100000` using only `filter`, `map`, and `toList`, without writing to a list outside the stream. With the program's data, the result must contain only `A01`.
4. Explain why `int[] acc = {0}; parallelStream().forEach(n -> acc[0] += n);` is unreliable even though `acc` is effectively final.
5. Write your own version of `calculateRevenue(List<Order>)` using `reduce`. Verify that an empty list produces `BigDecimal.ZERO` and the data above produces `320000`.
6. Evaluate one scenario that requires `AtomicInteger`, one scenario that requires a database transaction, and one scenario that only needs `List.copyOf`. Clearly state **which state is shared**, **who has mutation rights**, and **the guaranteeing mechanism**.

**Checklist when applying:** can input data be mutated from outside; does the object contain mutable components; does the lambda read/write shared state; does the aggregation have appropriate associativity and identity; is the object safely published when used across threads; does a multi-step operation need a lock or transaction. If you can answer these questions, designing an immutability-oriented pipeline will have a solid, verifiable foundation.
