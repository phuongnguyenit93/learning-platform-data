# Creating Result Objects Instead of Mutating Input Objects in Java

In functional programming, an important principle is **transforming data by returning a new value instead of directly mutating the passed-in value**. In Java, this usually means a method receives a source object, computes the fields that need to change, and then creates a **result object**. The source object can still be used elsewhere without unexpected side effects.

For example, instead of updating the status field of an order referenced by multiple components, we write a function that returns a **new order** with the updated status. When the logic is well-organized, this approach reduces reliance on mutable state and facilitates testing, composing multiple transformation steps, and concurrent processing.

This lesson focuses on **non-mutating transformations** in Java 17+: comparing before-and-after approaches, using records and immutable classes, preventing shallow copies, using Stream.map, handling lists/maps, optimizing performance, and verifying correctness.

## 1. How Do In-Place Mutation and Creating a New Result Differ?

Given a mutable class:

~~~java
class MutableCustomer {
    String name;
    String status;

    MutableCustomer(String name, String status) {
        this.name = name;
        this.status = status;
    }
}
~~~

A direct update approach:

~~~java
static void activate(MutableCustomer customer) {
    customer.status = "ACTIVE";
}
~~~

After calling activate(customer), **the customer instance itself** is modified. If multiple variables or components hold references to this instance, they can all observe the new state.

In a non-mutating input model, instead of a void procedure with a side effect, we can define a result type and return a new object:

~~~java
record Customer(String name, String status) {}

static Customer activate(Customer customer) {
    return new Customer(customer.name(), "ACTIVE");
}
~~~

Now:

~~~java
Customer oldValue = new Customer("An", "NEW");
Customer newValue = activate(oldValue);

System.out.println(oldValue.status()); // NEW
System.out.println(newValue.status()); // ACTIVE
~~~

These are illustrative snippets that need to be placed in a valid class/method context; section 9 has a standalone Java program that has been compiled and run.

**Core point:** the new result does not cause references holding the old object to automatically switch to the new object. The caller **actively** uses the returned result.

### 1.1. Mutation Is Not the Same as Reference Reassignment

~~~java
Customer before = new Customer("An", "NEW");
Customer after = new Customer(before.name(), "ACTIVE");
~~~

Declaring the after variable does not modify before.

~~~java
Customer current = before;
current = new Customer(current.name(), "ACTIVE");
~~~

Reassigning the **local variable current** changes the reference that variable holds; it does not change the fields of the before instance. Therefore, **object immutability** and **whether a reference variable can be reassigned** are two different concepts.

In Java, a final variable prevents reassigning the reference after it has been assigned a value, but it does **not** automatically make the referenced object immutable. A final List<String> can still be a mutable ArrayList and allow add.

## 2. Why Is Creating Result Objects Useful?

There are four common benefits.

**Predictability:** the same input object and the same rules can produce consistent results, provided the function does not depend on changing external state. Nobody has to ask, "Does this method secretly mutate its parameters?".

**Testability:** we can assert both the **correct result** and that the **input was not modified**. With truly immutable data, tests do not need to restore the original state after each run.

**Composability:** each function takes a value and returns a value, which can be used in Stream.map, Function.andThen, or consecutive processing steps. Steps do not need to share a mutable object to pass results implicitly.

**Reduced concurrency risk:** immutable data is generally simpler when shared across threads, because there are no write operations modifying the state of that data itself. However, immutability does not automatically guarantee that all I/O operations, caches, publications, or external dependencies are thread-safe.

In return, this approach can create many objects or collection copies. Therefore, we need to balance **contract clarity** and **data cost**; we should not mechanically copy an entire large graph after every small operation.

## 3. Immutable Result Structures with Java Records

Java 17 supports **records** as a concise class declaration for carrying data:

~~~java
record Product(String sku, String name, int price) {}
~~~

A record automatically provides a constructor, accessors such as sku(), name(), price(), and the equals, hashCode, and toString methods with their corresponding rules.

A transformation function:

~~~java
static Product rename(Product original, String newName) {
    return new Product(original.sku(), newName, original.price());
}
~~~

The state of original does not change. However, it is important to understand the limitations:

- The component fields of a record are **private final**.
- A record **does not automatically perform a deep copy** of components that are mutable objects.
- If a record holds an ArrayList or an array, their contents can still be modified through the reference unless the author designs defensively.
- A record does not guarantee that every method on the record is pure; a method can read/write global state, call I/O, or mutate a mutable object held in a component.

Therefore, treat records as a design tool for **value-oriented data**, rather than a certificate guaranteeing deep immutability or pure functions in every case.

### 3.1. Placing Transformation Rules Near the Data Type

Methods can be provided with clear, readable names:

~~~java
record Product(String sku, String name, int price) {
    Product withPrice(int nextPrice) {
        return new Product(sku, name, nextPrice);
    }
}
~~~

The name withPrice suggests creating a result with one component replaced; it is **not** automatic syntax for every record. Java records do not automatically generate withX methods. We write them ourselves or use an appropriate code-generation technique in a specific project.

~~~java
Product oldProduct = new Product("P1", "Book", 100);
Product updated = oldProduct.withPrice(120);
~~~

oldProduct still has price = 100; updated has price = 120.

There is no need to use withX names for every case. A business-oriented name like applyDiscount or markAsPaid may express the contract better when there is validation, a transition rule, or specific computation.

## 4. Protecting Component Lists with Defensive Copies

An Order containing a list of line items is an important example. The following code **has a problem** even though Order is a record:

~~~java
record UnsafeOrder(String id, List<String> items) {}

List<String> external = new ArrayList<>();
external.add("Book");

UnsafeOrder order = new UnsafeOrder("O-1", external);
external.add("Pen");

// order.items() now also contains "Pen", even though no new Order was created.
~~~

Because the record only holds a List reference, both the external variable and the record share **the same mutable List object**.

Solution:

~~~java
record Order(String id, List<String> items) {
    Order {
        items = List.copyOf(items);
    }
}
~~~

In the record's **compact constructor**, reassigning the items parameter determines the value stored in the component field. List.copyOf creates an unmodifiable List by contract, and takes a snapshot of the elements at the list level (it may reuse the input instance when it is already a suitable collection).

~~~java
List<String> external = new ArrayList<>(List.of("Book"));
Order original = new Order("O-1", external);

external.add("Pen");
System.out.println(original.items()); // [Book]
~~~

Order is not affected by the add operation on external after it has been created.

### 4.1. An Unmodifiable View Is Not a Separate Copy

Be careful with:

~~~java
List<String> view = Collections.unmodifiableList(external);
~~~

The view blocks modifications **through the view**, but when external is an ArrayList still held elsewhere, external.add(...) operations can be observed through the view. Thus, an unmodifiable view over a mutable List **does not** equate to an independent snapshot.

List.copyOf(external) is the right choice when you need an unmodifiable result list and want to isolate structural changes from the input List. Note that List.copyOf **does not accept null elements**, and the objects contained inside can still be mutable.

### 4.2. Shallow Copying and Deep Immutability

Suppose the list contains mutable objects:

~~~java
final class MutableLine {
    int quantity;
    MutableLine(int quantity) {
        this.quantity = quantity;
    }
}
~~~

A List.copyOf(...) only protects the **list structure** from adding/removing/replacing elements through the new list. It does not automatically create a copy of each MutableLine:

~~~java
MutableLine line = new MutableLine(1);
List<MutableLine> snapshot = List.copyOf(List.of(line));

line.quantity = 9;
// snapshot.get(0).quantity is now 9.
~~~

If you want immutability all the way through, use immutable element types (for example, records containing String, int, long) or manually create defensive copies for each mutable element, following a clear deep-copy contract.

**There is no single general operation in the JDK that turns every object graph into deep immutable**. Reference cycles, custom classes, external data, and mutable nested structures require custom design.

## 5. Stream.map: Each Element In, Result Object Out

In Java functional programming, **map** is the typical transformation for creating new data:

~~~java
record Item(String name, int price) {}

List<Item> original = List.of(
    new Item("Book", 100),
    new Item("Pen", 20)
);

List<Item> discounted = original.stream()
    .map(item -> new Item(
        item.name(), item.price() - 10))
    .toList();
~~~

original does not change; discounted contains the resulting Item objects. In this example, the new price of Pen is 10. In real applications, you need to check for non-negativity, overflow, currency units, discount rates, and appropriate rounding policies.

**Rule:** the map lambda returns a value; do not use it as a place to mutate the parameter and then return that same parameter.

### 5.1. Style to Avoid

~~~java
List<MutableItem> result = items.stream()
    .map(item -> {
        item.setPrice(item.getPrice() - 10);
        return item;
    })
    .toList();
~~~

This is an illustrative snippet with a hypothetical MutableItem class; it mutates **the source Item instances themselves** and returns them in the result. Both lists can now reference the mutated elements. Even though the list returned by toList is unmodifiable, the MutableItem objects inside can still be mutable.

The preferred approach when there is a clear result data type:

~~~java
List<Item> result = items.stream()
    .map(item -> new Item(item.name(), item.price() - 10))
    .toList();
~~~

map does not automatically enforce new objects; that is the lambda's choice. If the lambda returns the same instance or mutates external state, the Stream API cannot automatically fix purity for the application.

### 5.2. Other Operations with the Same Spirit

- **filter:** selects elements by a condition, usually without mutating the source.
- **map:** transforms each element into a result.
- **flatMap:** transforms each element into a sub-stream and flattens them.
- **sorted:** creates a pipeline with sorted processing order, without directly calling sort on the source List.
- **collect/toList:** gathers the resulting data.

Do not confuse Stream.sorted with List.sort: calling List.sort on a mutable List updates that list directly; Stream.sorted returns a pipeline describing the result order.

### 5.3. An Immutable Result Can Share Original Elements

~~~java
List<Product> filtered = products.stream()
    .filter(product -> product.price() > 0)
    .toList();
~~~

This is a **filtering** operation, not necessarily creating new Products. If Product is immutable, elements can be safely shared according to the data contract. But if Product is mutable, merely creating a new List does not guarantee that each Product inside has been copied.

Therefore, it is necessary to distinguish two goals:

1. **Not mutating input objects during the current computation**.
2. **Ensuring the result is an immutable snapshot unaffected by future changes**.

The second goal is stronger and may require immutable elements or deeper defensive copying.

## 6. Transforming Objects with Method References and Function

A function that receives data and returns a new object can be passed as Function<T,R>:

~~~java
static Product increasePrice(Product product) {
    return new Product(
        product.sku(),
        product.name(),
        Math.addExact(product.price(), 10)
    );
}

List<Product> updated = products.stream()
    .map(MyClass::increasePrice)
    .toList();
~~~

This is an illustrative pattern; MyClass must be the name of the class containing the method. Writing a method reference clarifies behavior and can help with testing independently of the pipeline.

### 6.1. Composing Functions to Organize Multiple Steps

~~~java
Function<Product, Product> normalizeName =
    product -> new Product(
        product.sku(),
        product.name().trim(),
        product.price()
    );

Function<Product, Product> addFee =
    product -> new Product(
        product.sku(),
        product.name(),
        Math.addExact(product.price(), 5)
    );

Function<Product, Product> pipeline =
    normalizeName.andThen(addFee);
~~~

Each Function receives a Product and creates another Product. Function.andThen executes the first step and passes the returned value to the next step.

It is not mandatory that the new result be a different instance **in every branch**: a pure function can return the source instance if the data already satisfies the condition and the data is truly immutable. The key is **not changing the observable state of the source**, not forcing every call to allocate a new object to prove functional style.

### 6.2. Purity: More Than No Mutation

A function that does not mutate its parameters can still be **impure** if it reads the current time, random values, mutable static fields, queries a database, or writes external logs. For example:

~~~java
static Receipt stamp(Order order) {
    return new Receipt(order.id(), Instant.now());
}
~~~

The snippet above is illustrative with appropriate Receipt/Order types; the result depends on Instant.now, so the same order can produce different results.

If determinism is desired, pass the time or Clock as an explicit dependency:

~~~java
static Receipt stamp(Order order, Instant issuedAt) {
    return new Receipt(order.id(), issuedAt);
}
~~~

This snippet can be pure when the related data is immutable and the function has no side effects. Separating environmental dependencies makes testing more accurate.

## 7. Transforming Data in Steps: input → value → output

In business code, distinguishing the **original data model** and the **result model** often clarifies intent:

~~~java
record OrderInput(String sku, int quantity, int price) {}
record OrderSummary(String sku, long amount) {}

static OrderSummary summarize(OrderInput input) {
    long amount = Math.multiplyExact(
        (long) input.quantity(), input.price());
    return new OrderSummary(input.sku(), amount);
}
~~~

The OrderInput object holds the raw data; OrderSummary stores the result form. There is no need to add an amount field to OrderInput or mutate price/status to temporarily store the result.

Design advantages:

- The input layer preserves the meaning of the input data.
- The transformation layer clearly expresses **value type conversion**, such as OrderInput → OrderSummary.
- The output layer can define its own validation, serialization, or formatting.
- Multiple views can be created from the same input without mutating each other.

This approach is useful for DTO mapping, report generation, data normalization, converting entities to responses, calculating shopping cart totals, and ETL pipelines.

### 7.1. Do Not Equate Domain Entities with DTOs

An entity has its own identity, lifecycle, persistence context, and update rules; an immutable DTO usually serves data exchange. Creating a new DTO from an entity is often a good choice for a read-only projection. However, do not assume that the entire persistence system will save the new object just because you created a copy: with JPA/Hibernate, managed entities and dirty checking have a different contract.

Choosing boundaries:

- **Reading and preparing data to return:** usually create a result DTO/record.
- **Executing intentional business changes:** use commands or services that update according to transactions, validation, and persistence.
- **Intermediate calculations:** prefer functions that take values and return values.

The goal is to avoid **unintentional implicit mutation**, not to deny the need for actual database updates.

## 8. Arrays, Maps, and Result Collections

### 8.1. With List

~~~java
List<String> trimmed = original.stream()
    .map(String::trim)
    .toList();
~~~

Stream.toList in Java 17 returns an unmodifiable List. If a mutable ArrayList is needed for a subsequent API:

~~~java
List<String> mutable = original.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));
~~~

These examples require importing java.util.List, java.util.ArrayList, and java.util.stream.Collectors in their containing class.

### 8.2. With Map

You can create a result map instead of using putAll/replaceAll to mutate the source Map:

~~~java
Map<String, Integer> source = Map.of("A", 10, "B", 20);

Map<String, Integer> result = source.entrySet().stream()
    .collect(Collectors.toUnmodifiableMap(
        Map.Entry::getKey,
        entry -> Math.multiplyExact(entry.getValue(), 2)
    ));
~~~

source is unchanged; result contains A → 20 and B → 40. Collectors.toUnmodifiableMap creates an unmodifiable map, **does not accept null keys/values**, and can throw IllegalStateException on duplicate keys when using the two-parameter overload. If you want to handle duplicate keys, use the overload with an appropriate merge function.

Do not assume the iteration order of Map.of or Collectors.toUnmodifiableMap is the insertion order. When a deterministic order is needed, use a structure or collector with a clear ordering contract and consider creating an appropriate copy/wrapper.

### 8.3. With Arrays

Java arrays are mutable, so return a new array instead of mutating the source array:

~~~java
int[] original = {1, 2, 3};

int[] doubled = java.util.Arrays.stream(original)
    .map(value -> Math.multiplyExact(value, 2))
    .toArray();
~~~

original remains [1, 2, 3]; doubled is [2, 4, 6]. However, doubled is still a **mutable array**: creating a copy resolves aliasing with the source array, not automatically making the result immutable.

If a class holds int[] as a field and wants observable immutability, it usually must **clone on input** and **clone on output**, never exposing the internal array directly.

## 9. Standalone Java 17+ Example: Order and Receipt

The following program models orders in a value-oriented way. **Order** contains a structurally immutable list of Items, with result-creating methods **withStatus** and **withAddedItem**. **Receipt** is a separate result derived from Order; its description lines are also defensively copied via List.copyOf.

Create the file **ImmutableTransformDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableTransformDemo {
    record Item(String sku, int quantity, int unitPrice) {
        Item {
            Objects.requireNonNull(sku);
            if (sku.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        long amount() {
            return Math.multiplyExact((long) quantity, unitPrice);
        }
    }

    record Order(String id, List<Item> items, String status) {
        Order {
            Objects.requireNonNull(id);
            Objects.requireNonNull(status);
            items = List.copyOf(items);
        }

        Order withStatus(String next) {
            return new Order(id, items, next);
        }

        Order withAddedItem(Item item) {
            List<Item> copy = new ArrayList<>(items);
            copy.add(item);
            return new Order(id, copy, status);
        }

        long total() {
            return items.stream().map(Item::amount)
                .reduce(0L, Math::addExact);
        }
    }

    record Receipt(String orderId, String status,
                   long total, List<String> lines) {
        Receipt {
            lines = List.copyOf(lines);
        }
    }

    static Receipt toReceipt(Order order) {
        List<String> lines = order.items().stream()
            .map(item -> item.sku() + " x" +
                item.quantity() + "=" + item.amount())
            .toList();
        return new Receipt(order.id(), order.status(),
            order.total(), lines);
    }

    public static void main(String[] args) {
        List<Item> seed = new ArrayList<>(List.of(
            new Item("Book", 2, 40)
        ));
        Order original = new Order("O-1", seed, "NEW");
        seed.add(new Item("Hidden", 9, 9));

        Order paid = original.withStatus("PAID");
        Order extended = paid.withAddedItem(new Item("Pen", 3, 10));
        Receipt receipt = toReceipt(extended);

        System.out.println("original=" + original.status() +
            ",total=" + original.total() +
            ",items=" + original.items().size());
        System.out.println("paid=" + paid.status() +
            ",total=" + paid.total() +
            ",items=" + paid.items().size());
        System.out.println("extended=" + extended.status() +
            ",total=" + extended.total() +
            ",items=" + extended.items().size());
        System.out.println("receipt=" + receipt);
        System.out.println("same-instance=" + (original == paid));

        try {
            original.items().add(new Item("Eraser", 1, 5));
        } catch (UnsupportedOperationException error) {
            System.out.println("items-unmodifiable=true");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ImmutableTransformDemo.java
java ImmutableTransformDemo
~~~

**Exact stdout:**

~~~text
original=NEW,total=80,items=1
paid=PAID,total=80,items=1
extended=PAID,total=110,items=2
receipt=Receipt[orderId=O-1, status=PAID, total=110, lines=[Book x2=80, Pen x3=30]]
same-instance=false
items-unmodifiable=true
~~~

### 9.1. Analyzing the Results

**Step 1:** original is created from seed containing Book × 2 × 40, totaling 80. Order's compact constructor uses List.copyOf(items), creating a structurally unmodifiable snapshot. Therefore, after seed.add(Hidden), original.items still has exactly 1 item.

**Step 2:** original.withStatus("PAID") returns a new Order keeping the existing Item list but changing the status. original.status remains NEW, while paid.status is PAID. The two Orders are different instances.

**Step 3:** paid.withAddedItem(Pen × 3 × 10) creates a temporary ArrayList from the old list, adds the Pen item, and then creates a new Order; Order's constructor converts it into an unmodifiable List. paid keeps 1 item; extended has 2 items, totaling 80 + 30 = 110.

**Step 4:** toReceipt transforms Order into a completely different Receipt type, containing order ID, status, total, and a list of descriptive strings. Receipt does not need to modify Order to add UI-facing fields.

**Step 5:** original == paid is false because the withStatus method created a different Order instance. If data is compared using equals, Java records provide component-based value equality, but **reference identity** should not be used as the sole criterion to evaluate whether a function causes mutation.

**Step 6:** attempting to add an element to original.items() throws UnsupportedOperationException; the example catches that exact error solely to print the illustrative flag. In production code, exceptions should not be used as a routine test for a collection's mutability.

### 9.2. Why Is There No Mutation Leak Through Item?

Item is a record with a String component and int primitives. String is immutable and primitives have no object state to mutate through a reference, so Item itself in this example is an immutable data type by design.

If Item were replaced by a class with a mutable List or mutable Calendar without defensive copying, the same Order code using List.copyOf **would not be enough** to preserve deep immutability. To guarantee data is safe to share, the entire component structure must be checked.

### 9.3. Costs and Limitations of the Example

- withStatus creates a new Order but can share the existing immutable Item list.
- withAddedItem creates a temporary List and a result snapshot; the cost generally scales with the number of elements.
- toReceipt creates a new list of strings and a new Receipt.
- Every call to total() computes the sum from the Items; for large data, a carefully designed caching model or computation at snapshot creation time can be considered.
- Math.multiplyExact and Math.addExact detect overflow in the total calculation path; however, using int for unitPrice is a simplified model to focus on immutability, not a complete monetary architecture.
- The example does not include a database, transactions, event sourcing, or handling multiple concurrent writers. Creating a new Order in memory **does not mean** the data has been persisted to an external system.

## 10. Performance: Full Copy, Structural Sharing, and Trade-offs

### 10.1. Copying Has Real Cost

For a List with n elements, copying via new ArrayList<>(old) typically has **O(n)** memory and time cost. If List.copyOf subsequently creates another snapshot, there may be an additional copy step depending on the source and implementation.

If a large object has many immutable components and only one small component changes, you can share the existing immutable components instead of copying every value.

For example:

~~~java
Order withStatus(String nextStatus) {
    return new Order(id, items, nextStatus);
}
~~~

items is already an unmodifiable List in the example Order, and Item is immutable, so it **can be safely shared** between old and new Orders. Do not unnecessarily deep-copy all components if they are truly immutable and the contract allows it.

### 10.2. Persistent Data Structures and Structural Sharing

Some libraries provide persistent data structures, where updates can create a new version while **sharing many immutable nodes** with the old version. This can reduce costs compared to copying an entire large list/map on every change.

Standard JDK Collections do not provide a full vector/trie-style persistent collection API as a general replacement for ArrayList/HashMap. If you need to optimize a huge structure updated frequently, consider a project-supported library, actual access patterns, and benchmark measurements.

**Do not implicitly assume records automatically use structural sharing.** A record simply stores components according to its class design; whether structure is shared depends on component types and how the result is created.

### 10.3. When Intentional Mutation Is Still Reasonable

In in-place algorithms, buffers processing large data, I/O communication, or entity persistence, updating mutable state can be the right choice. Clearly separate **code regions with controlled mutation** from **value-based data transformation regions**, rather than trying to avoid every assignment or state change.

For example, when building a result with millions of elements, using an internal mutable ArrayList to accumulate and then returning an immutable snapshot can be more efficient than creating a List copy after each element. The function can still satisfy the contract of **not mutating the input and not exposing mutable internals**:

~~~java
static List<String> normalize(List<String> source) {
    List<String> buffer = new ArrayList<>();
    for (String text : source) {
        buffer.add(text.trim());
    }
    return List.copyOf(buffer);
}
~~~

Mutation on a **local, unshared** buffer differs from mutation on source held by the caller. Purity still depends on element types, nulls, concurrent interference, and the external environment, but this design demonstrates a clear boundary.

## 11. Testing: Verifying Both the Result and Unchanged Input

An appropriate unit test should check:

1. Does the result have the expected data?
2. Does the input object retain its observable state?
3. If there are multiple references to the source, do old references still see old data?
4. If there are nested collections, do external changes affect the created value?
5. Do collections declared as unmodifiable actually block modification operations?
6. Are null, overflow, and invalid value cases handled according to the contract?

JUnit 5 example based on the model in section 9:

~~~java
// Illustrates JUnit 5 assertions, requires JUnit 5 dependency.
Order original = new Order("O-1",
    List.of(new Item("Book", 2, 40)), "NEW");

Order updated = original.withStatus("PAID");

assertEquals("NEW", original.status());
assertEquals("PAID", updated.status());
assertEquals(80L, original.total());
assertNotSame(original, updated);
~~~

The records in the sample program are nested types of ImmutableTransformDemo; when writing tests outside the class, import or qualify ImmutableTransformDemo.Order if visibility/package allows.

Defensive copy tests should also be added:

~~~java
List<Item> seed = new ArrayList<>();
seed.add(new Item("Book", 1, 40));

Order original = new Order("O-1", seed, "NEW");
seed.add(new Item("Pen", 1, 10));

assertEquals(1, original.items().size());
assertThrows(UnsupportedOperationException.class,
    () -> original.items().clear());
~~~

This test confirms that Order's list is unaffected by additions/removals from seed and does not allow modification through the accessor. It does **not** prove that all nested items are immutable in the general model; the Item type must be checked separately.

## 12. Common Mistakes

**Mistake 1 — mutating and returning the source object itself.** A map lambda that calls a setter on the parameter and returns that parameter breaks the non-mutating contract, potentially causing multiple places to see modified data.

**Mistake 2 — believing final means immutable.** final on a field/reference prevents reassignment, not mutating the contents of an ArrayList or inner object.

**Mistake 3 — believing every record is deeply immutable.** A record can hold a mutable List, array, or custom object. Proper defensive copying and choosing immutable components are required.

**Mistake 4 — using Collections.unmodifiableList as an absolute snapshot.** This is usually an unmodifiable view that can reflect changes in the original List. List.copyOf helps create a structural snapshot when needed.

**Mistake 5 — forgetting to copy when returning an array.** A class that holds an array and returns the internal array to the caller allows modification through the accessor; consider cloning on both input and output.

**Mistake 6 — thinking Stream.filter/map automatically guarantees purity.** Callbacks can mutate external fields, send logs, or update a DB. The Stream API only provides a processing framework; it does not prevent developer side effects.

**Mistake 7 — using Stream.toList and assuming elements are immutable.** The resulting List is unmodifiable, but elements can be mutable; distinguish collection immutability from element immutability.

**Mistake 8 — copying an object while forgetting nested references.** Two "different instance" objects can still share a mutable List, causing aliasing. Sharing design is only safe when the shared part has an appropriate immutability contract.

**Mistake 9 — excessive full copying.** Deep-copying a large graph for every transformation can waste resources. Consider sharing immutable elements, batching multiple updates into a single result construction, or using appropriate persistent collections.

**Mistake 10 — not using the return value.** If the withStatus method returns a new Order, calling original.withStatus("PAID") while ignoring the result will not update original. The caller must explicitly assign or pass along the new instance.

**Mistake 11 — treating Object identity as content.** Records provide component-based equals; two different instances can be equal in value. Do not decide business state solely based on == when equality is required.

**Mistake 12 — skipping validation when creating a new instance.** Every constructor/factory must maintain invariants such as positive quantity, valid unit price, valid status, and no null elements if the contract forbids them.

**Mistake 13 — assuming an immutable DTO automatically saves to the database.** A new object is only an in-memory value; persistence, transactions, and update concurrency are the responsibility of the storage layer.

**Mistake 14 — a function does not mutate input but depends on global state.** A function reading a clock, random generator, or mutable static map can be impure even without calling setters on parameters.

**Mistake 15 — premature optimization with a shared mutable cache.** Caching can complicate thread-safety and invalidation. If caching is needed, design around the immutability contract of input/output and test concurrency appropriately.

## 13. Design Choice Checklist

| Scenario | Typically Appropriate Approach |
| --- | --- |
| Normalizing an input object | Create a result object with normalized values |
| Controlled state change | withStatus/markAsPaid function returning a new object |
| Converting domain entity to response | Create a new DTO/record, do not attach display fields to entity |
| Transforming multiple elements | Stream.map returning results, appropriate toList/collector |
| Need to keep original for audit/comparison | Immutable value object or defensive snapshot |
| Result has nested List/Map | Defensive copy, check element mutability |
| Need to share across threads | Data immutability and proper publication contract |
| Large computation with many updates | Local mutation or persistent structure, measure performance |
| Need to save changes to DB | Explicit command/service/transaction |
| Input data is an array | Clone or create a new result array as required |

There is no rule forcing every operation in an application to create a new object. Choose abstractions based on business meaning and cost, while **avoiding input mutations unexpected by the caller**.

## 14. Self-Check Questions

1. What is the difference between reassigning a reference variable and mutating a field of the object the variable points to?
2. Why is a record with a List<MutableItem> component not automatically considered deeply immutable?
3. How do List.copyOf and Collections.unmodifiableList differ when the source ArrayList is still held externally?
4. If Stream.map mutates a field of each element and then returns that element, does the new List protect the original data?
5. When using a withStatus method that returns a new Order, what happens if the caller does not use the result?
6. Why is a new DTO created from an entity not automatically persisted?
7. Why can sharing an immutable Item between two Orders be safe, while sharing a MutableItem is risky?
8. In what cases does a local mutable buffer still fit a non-mutating input design?
9. In what cases should persistent data structures or structural sharing be considered?
10. How can you verify both the correct result and unchanged input simultaneously in a unit test?
11. Stream.toList returns an unmodifiable List; does this prove that the element objects are also immutable?
12. If a function always creates a new record but calls Instant.now, is that function completely pure?
13. When actual stored data needs to be changed, at which boundary should mutation be placed?
14. Why is a final List not enough to prevent source.add from modifying the list?
15. Where should invariants regarding quantity, price, null, and status be checked when creating a new object?

**Conclusion:** In Java data transformation, prefer **functions that take input and return a result object** instead of secretly mutating instances passed in by the caller. Records, immutable classes, defensive copies, and Stream.map are useful tools, but you must understand **aliasing, shallow/deep immutability, internal mutation, copying costs, and persistence**. Correctness lies in the observable contract: the result has the desired value and the input data remains reliable after the transformation.