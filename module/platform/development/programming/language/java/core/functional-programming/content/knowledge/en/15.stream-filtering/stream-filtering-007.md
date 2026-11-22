# Handling Null Elements Before Accessing Properties in Java

## 1. The Problem: Null Elements and Property Access

When filtering, selecting, or transforming elements of a list in Java, we often write lambdas or method references such as:

~~~java
List<String> names = employees.stream()
        .map(Employee::name)
        .toList();
~~~

This is an **illustrative snippet**, assuming you already have a `List<Employee>`, a record/class `Employee` with a `name()` method, and `List` imported. If the list **contains a null element**, at the **Employee::name** step Java attempts to invoke the method on a null receiver and throws a **NullPointerException (NPE)**.

This is a common mistake when doing functional programming: Stream syntax, lambdas, and method references **do not automatically check for null**. Accessing `employee.name()`, `Employee::name`, `employee.getName()`, or `employee.address().city()` all require the corresponding receiver object to be non-null.

The basic solution when the policy allows **skipping null elements**:

~~~java
List<String> names = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name)
        .toList();
~~~

This illustrative snippet requires importing **java.util.Objects** and **java.util.List**. **Objects::nonNull** is a method reference to the static method `boolean Objects.nonNull(Object obj)`. It returns true if the argument is non-null. `filter` keeps non-null elements; afterward, `map(Employee::name)` will no longer encounter a **null Employee receiver** from the data source.

However, another situation remains: **employee is non-null, but employee.name() returns null**. In that case, `map(Employee::name)` can produce a null element in the output Stream. If the next step is `String::strip`, `String::length`, or `String::toUpperCase`, we still need to handle the null property before accessing it.

**Two types of null to distinguish clearly:**

1. **Null in the element itself:** `employee == null` → must not call `employee.name()`.
2. **Null in a property:** `employee != null` but `employee.name() == null` → must not call `employee.name().strip()`.

This lesson focuses on how to properly guard each boundary in a **filtering and element selection** pipeline, rather than just adding a single null check and assuming every subsequent step is safe.

## 2. The Most Important Rule: Check Before Dereferencing

**Dereferencing** is the act of using a reference to access a member of an object: calling a method, reading an instance field, or using operations that require unboxing a wrapper. If the reference is null, these operations can throw an NPE.

Wrong:

~~~java
// MAY THROW NPE when employee == null.
Predicate<Employee> adult = e -> e.age() >= 18;
~~~

This illustrative snippet assumes `Employee.age()` returns an `int` and `Predicate` is imported.

Correct when you want to return false for a null element:

~~~java
Predicate<Employee> adult = e -> e != null && e.age() >= 18;
~~~

The **&&** operator uses short-circuit evaluation (*short-circuit*). If `e != null` is false, Java **does not evaluate the right-hand side** and does not call `e.age()`.

Wrong due to ordering:

~~~java
// MAY THROW NPE: calls e.age() before checking for null.
Predicate<Employee> broken = e -> e.age() >= 18 && e != null;
~~~

This is an intentionally dangerous example, not a pattern to use.

If the property itself can be null (for example, `Integer age` instead of `int age`), an extra step is needed:

~~~java
Predicate<Employee> adult = e ->
        e != null && e.age() != null && e.age() >= 18;
~~~

This illustrative snippet assumes `Employee.age()` returns a nullable **Integer**. In the final expression, Java automatically **unboxes Integer to int** to compare with 18. If `age` is null without a guard, unboxing also causes an NPE.

**Verification rule:** before any `x.method()`, `x.field`, `x::method` (bound method reference), or unboxing operation, make sure `x` is **non-null** by contract or has been guarded before the point of use.

## 3. Ways to Express Null Guards in Streams

### 3.1. Using filter(Objects::nonNull)

~~~java
Stream<Employee> safe = employees.stream()
        .filter(Objects::nonNull);
~~~

This is an illustrative snippet requiring `Stream` and `Objects` to be imported. When the Stream source contains multiple `Employee` instances mixed with nulls, the result keeps only non-null `Employee` instances. This is a readable choice when you want to remove **null elements** before operations that accept the object.

**Order matters very much:**

~~~java
// CORRECT: remove nulls before calling name().
employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name);

// WRONG: method reference may receive null before filter.
employees.stream()
        .map(Employee::name)
        .filter(Objects::nonNull);
~~~

The two pipelines above are **illustrative snippets**, without a terminal operation, and are not standalone programs. The second pipeline only filters out **nulls produced by name()**, and cannot prevent an NPE when `Employee::name` attempts to invoke the method on a null `Employee`.

A useful question for each step is: **“Right before this operation runs, which values can still be null?”**

### 3.2. Using a Lambda with an Explicit Condition

~~~java
employees.stream()
        .filter(e -> e != null)
        .map(Employee::name);
~~~

This is an illustrative snippet. In terms of intent to remove null elements, `e -> e != null` and `Objects::nonNull` are equivalent. Use a method reference when the method name clearly expresses the intent; use a lambda when additional logic is needed.

### 3.3. Filtering Both Null Elements and Nullable Properties

~~~java
List<String> names = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name)
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();
~~~

This is an illustrative snippet requiring `List` and `Objects` to be imported, where `Employee.name()` returns a nullable `String`:

- The first `filter(Objects::nonNull)` removes null `Employee` elements.
- `map(Employee::name)` may return a null `String`.
- The second `filter(Objects::nonNull)` removes null `String` values.
- `map(String::strip)` is called on a `String` guaranteed to be non-null.
- `filter(!isEmpty())` removes empty strings after normalization.

**No single filter(Objects::nonNull) automatically guarantees safety for all nested properties.** Every time you transform to a new value type with `map`, consider whether it can produce null.

## 4. Runnable Java 17 Example: Filtering Null Elements and Null Properties

Create the file **NullSafeFilterDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

record Employee(String id, String name, Integer age) {}

public class NullSafeFilterDemo {
    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
                new Employee("E1", " Lan ", 20),
                null,
                new Employee("E2", null, 25),
                new Employee("E3", "Minh", 17),
                new Employee("E4", " An ", 22),
                new Employee("E5", "   ", 30),
                new Employee("E6", "Hà", null)
        );

        Predicate<Employee> validAdult = employee ->
                employee != null
                && employee.name() != null
                && !employee.name().isBlank()
                && employee.age() != null
                && employee.age() >= 18;

        List<String> adultNames = employees.stream()
                .filter(validAdult)
                .map(Employee::name)
                .map(String::strip)
                .toList();

        List<String> allPresentNames = employees.stream()
                .filter(Objects::nonNull)
                .map(Employee::name)
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(name -> !name.isEmpty())
                .toList();

        System.out.println("Adults: " + adultNames);
        System.out.println("Names: " + allPresentNames);
        System.out.println("Source size: " + employees.size());
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 NullSafeFilterDemo.java
java NullSafeFilterDemo
~~~

Stdout:

~~~text
Adults: [Lan, An]
Names: [Lan, Minh, An, Hà]
Source size: 7
~~~

**Why is the output correct?**

1. The data has a null element in the middle of the list: **E1, null, E2, E3, E4, E5, E6**.
2. The predicate `validAdult` checks **employee is non-null**, **name is non-null and not blank**, **age is non-null**, and only then compares **age >= 18**. Thanks to short-circuiting, there is no unsafe dereference or unboxing on the failing branches.
3. **E1** qualifies and `" Lan "` is stripped to **"Lan"**; **E4** qualifies and `" An "` becomes **"An"**.
4. **E2** is excluded due to null name; **E3** due to age under 18; **E5** due to blank name; **E6** due to null age.
5. The `allPresentNames` pipeline only requires `name` to exist and not be blank, not a valid age. Therefore **Minh** and **Hà** still appear.
6. `Arrays.asList(...)` **allows null elements** in the input. Java's `List.of(...)` **does not allow null elements** and will throw an NPE immediately when creating the list. This difference is important when preparing test data.

**This is a policy example:** skipping employees with missing data without reporting an error. If the business domain treats an `Employee` missing a name or age as a corrupted record **that must be reported**, you should not silently filter it out; validate the input and report errors at the appropriate boundary.

## 5. Two Different Filter Positions: Before or After map?

A pipeline can use multiple filters because the value has **changed type** through `map`.

~~~text
Stream<Employee>
    │
    ├─ filter(Objects::nonNull)   → non-null Employee
    │
    ├─ map(Employee::name)        → Stream<String>, may contain null
    │
    ├─ filter(Objects::nonNull)   → non-null String
    │
    ├─ map(String::strip)         → normalized String
    │
    └─ filter(s -> !s.isEmpty())  → non-empty strings only
~~~

In this case, **filtering before map** protects the `Employee` receiver. **Filtering after map** protects the `String` receiver for the next step. They do not replace each other.

When both conditions are simple, you can write them directly:

~~~java
employees.stream()
        .filter(e -> e != null && e.name() != null)
        .map(Employee::name)
        .map(String::strip);
~~~

This is an illustrative snippet. It is safe against null elements and null names, but **does not automatically remove blank strings**. If you need to check `name.isBlank()`, you must add an appropriate condition or filter.

**A note:** Calling `e.name()` twice in the same pipeline may be fine for immutable accessors like records, but for getters with side effects or mutable data changing concurrently, two reads might not be equivalent. Converting to `String` with `map(Employee::name)` and then processing the `String` in subsequent steps avoids unnecessary re-reading of the getter.

## 6. Null Elements vs. Null Nested Properties

An object may exist, while one of its child objects is null.

For example:

~~~java
record Address(String city) {}
record Customer(String id, Address address) {}
~~~

The two records above are **illustrative type declarations**. Given a non-null `Customer customer`, the expression below still risks an NPE if `customer.address() == null`:

~~~java
String city = customer.address().city();
~~~

Guards need to protect each layer:

~~~java
if (customer != null && customer.address() != null
        && customer.address().city() != null) {
    String city = customer.address().city();
    // Use city here.
}
~~~

This is an illustrative snippet inside a method. In a Stream, a clearer approach is usually to split the layers into separate `map` and `filter` steps:

~~~java
List<String> cities = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::address)
        .filter(Objects::nonNull)
        .map(Address::city)
        .filter(Objects::nonNull)
        .toList();
~~~

You need to import `List` and `Objects` and have an appropriate `customers` variable. First remove null `Customer` elements, then remove null `Address` values, and finally remove null `city` values. If you need to remove blank cities, add `filter(city -> !city.isBlank())` after the non-null city step.

**Key takeaway:** `Objects::nonNull` does not automatically “drill down” into fields; it only checks **the exact object being passed to the Predicate at that moment**.

## 7. Runnable Java 17 Example: Nested Properties and Optional

Create the file **NullablePropertyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

record Address(String city) {}
record Customer(String id, Address address) {}

public class NullablePropertyDemo {
    static Optional<String> cityOf(Customer customer) {
        return Optional.ofNullable(customer)
                .map(Customer::address)
                .map(Address::city)
                .filter(city -> !city.isBlank());
    }

    public static void main(String[] args) {
        List<Customer> customers = Arrays.asList(
                new Customer("A", new Address("Hà Nội")),
                null,
                new Customer("B", null),
                new Customer("C", new Address(null)),
                new Customer("D", new Address("Đà Nẵng"))
        );

        List<String> cities = customers.stream()
                .filter(Objects::nonNull)
                .map(Customer::address)
                .filter(Objects::nonNull)
                .map(Address::city)
                .filter(Objects::nonNull)
                .toList();

        System.out.println("Cities: " + cities);
        System.out.println("A: " + cityOf(customers.get(0))
                .orElse("unknown"));
        System.out.println("B: " + cityOf(customers.get(2))
                .orElse("unknown"));
        System.out.println("C: " + cityOf(customers.get(3))
                .orElse("unknown"));
        System.out.println("null: " + cityOf(null).orElse("unknown"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 NullablePropertyDemo.java
java NullablePropertyDemo
~~~

Stdout:

~~~text
Cities: [Hà Nội, Đà Nẵng]
A: Hà Nội
B: unknown
C: unknown
null: unknown
~~~

**Explanation:**

- The first pipeline removes null `Customer` elements, removes null `Address` values, and then removes null `city` values. Therefore only two cities remain: **Hà Nội** and **Đà Nẵng**.
- `Optional.ofNullable(customer)` creates an empty `Optional` when `Customer` is null. `map(Customer::address)` yields `Optional.empty()` if `Address` is null, so `Address::city` is not called on null.
- `Optional.map` turns a null mapper result into `Optional.empty()`; thus a null `city` field is also safe in this example.
- `filter(city -> !city.isBlank())` only executes when the `Optional` contains a non-null `city`.
- `orElse("unknown")` demonstrates **the example's fallback policy**. In a real system, a missing address might require a validation error instead of silently substituting `"unknown"`.

**Optional** is typically useful when a method **returns** a potentially absent value, such as `Optional<String> cityOf(...)`. There is no need to make every field of `Customer`/`Address` an `Optional<...>` just to handle nulls in Streams.

## 8. Selecting the First Element with findFirst/findAny

When selecting an element from a Stream, many people assume **findFirst()** is always null-safe. In reality, according to the Stream API contract, **findFirst()** and **findAny()** can throw a `NullPointerException` if **the selected element is null**. They return **Optional<T>**, and `Optional` cannot hold null.

Therefore, when the source may contain nulls and you need to select the first valid element, filter first:

~~~java
Optional<String> first = codes.stream()
        .filter(Objects::nonNull)
        .findFirst();
~~~

This is an illustrative snippet requiring `Optional`, `Objects`, and a suitable `codes` collection. If all elements are null or the list is empty, the result is `Optional.empty()`.

Similarly, when selecting an element based on a property, you must guard before the predicate accesses the property:

~~~java
Optional<Employee> firstAdult = employees.stream()
        .filter(Objects::nonNull)
        .filter(e -> e.age() != null && e.age() >= 18)
        .findFirst();
~~~

This is an illustrative snippet where `Employee.age()` returns `Integer`, with `Optional` and `Objects` imported. **findFirst() does not skip nulls automatically**; it is the filter steps that guarantee the selected element is non-null.

### 8.1. findFirst vs. findAny

- **findFirst()** returns the first element according to the **encounter order** if the Stream is ordered.
- **findAny()** may return any element, especially suited for parallel processing; you should not rely on a specific position.
- Both return **Optional<T>** and both are invalid if the actually selected element is null.
- When no element matches, they return `Optional.empty()`.

If it does not matter which element is chosen, **findAny()** may be appropriate; if you need a deterministic result based on sequential list order, **findFirst()** expresses the intent better.

## 9. Runnable Java 17 Example: Null-Safe Selection, Normalization, and Sorting

Create the file **NullSafeSelectionDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

record Item(String id, Integer price) {}

public class NullSafeSelectionDemo {
    public static void main(String[] args) {
        List<String> codes =
                Arrays.asList(null, "  ", " ab ", null, " xy ");

        Optional<String> firstCode = codes.stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty())
                .findFirst();

        System.out.println("First: " + firstCode.orElse("(none)"));

        List<Item> items = Arrays.asList(
                new Item("A", 20),
                null,
                new Item("B", null),
                new Item("C", 10)
        );

        Comparator<Item> byPrice =
                Comparator.comparing(
                        Item::price,
                        Comparator.nullsLast(
                                Comparator.naturalOrder()));

        List<String> sortedIds = items.stream()
                .filter(Objects::nonNull)
                .sorted(byPrice)
                .map(Item::id)
                .toList();

        System.out.println("Sorted ids: " + sortedIds);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NullSafeSelectionDemo.java
java NullSafeSelectionDemo
~~~

Stdout:

~~~text
First: ab
Sorted ids: [C, A, B]
~~~

**Points to distinguish:**

1. `codes` has null elements, a blank string, and strings with whitespace. `Objects::nonNull` removes nulls **before** `String::strip`.
2. `strip` turns `"  "` into `""` and `" ab "` into `"ab"`; the `filter(!isEmpty())` step removes empty strings.
3. `findFirst()` finds `"ab"` and returns an `Optional` containing that value.
4. The `items` list contains a null `Item` and a valid `Item` with a **null price**. `filter(Objects::nonNull)` removes the null `Item` before the `Comparator` reads `Item::price`.
5. `Comparator.nullsLast(Comparator.naturalOrder())` only handles **null price values**, so Item **B** is placed last, while **C** with price 10 comes before **A** with price 20.
6. **A property-level nullsLast Comparator does not automatically make a null Item object safe.** Here we proactively remove null `Item` elements before sorting.

In real-world problems, you need to decide whether products missing a price should be placed last, excluded from the list, or reported as an error. `nullsLast` is a **sorting rule**, not validation.

## 10. Comparator and Accessing Nullable Properties

When sorting a list of objects, the following expression risks failing:

~~~java
items.stream()
        .sorted(Comparator.comparing(Item::price));
~~~

This is an illustrative snippet. There are **two sources of NPE**:

1. **Null Item:** `Item::price` attempts to invoke a method on null.
2. **Null Item.price():** A `Comparator` using natural order on `Integer` can encounter null and throw an NPE.

Solutions depend on policy:

**Remove null Items and Items missing a price:**

~~~java
items.stream()
        .filter(Objects::nonNull)
        .filter(item -> item.price() != null)
        .sorted(Comparator.comparing(Item::price));
~~~

**Remove null Items but keep Items missing a price, placing them last:**

~~~java
items.stream()
        .filter(Objects::nonNull)
        .sorted(Comparator.comparing(
                Item::price,
                Comparator.nullsLast(Comparator.naturalOrder())));
~~~

These are two illustrative snippets with `Objects` and `Comparator` imported. **Preconditions** must match how missing data is handled:

- If a missing price is an invalid record: validate or discard it.
- If a missing price means “not yet priced” and must still be displayed: use `nullsLast` or `nullsFirst` as required.
- If a null `Item` object is a serious data-structure error: fail early instead of silently filtering it out.

You can also use **Comparator.nullsLast(itemComparator)** at the **Item object** level, but you must place null handling at the right layer for the right type: **a null Item** is different from **a null price**. Two layers require two policies if both can be null.

## 11. Cases Where NPE Still Occurs Despite Initial Null Filtering

### 11.1. Unboxing a Nullable Wrapper

~~~java
// May throw NPE if age() returns a null Integer.
Predicate<Employee> adult = employee ->
        employee != null && employee.age() >= 18;
~~~

You must add `employee.age() != null` before the comparison, because **Integer** is unboxed to **int**. Java does not automatically infer that a non-null receiver means its fields are also non-null.

### 11.2. Intermediate Getter Returning Null

~~~java
// May throw NPE if address() returns null.
String city = customer.address().city();
~~~

Checking `customer != null` only protects `Customer`, not `Address`. Use separate guards or split the pipeline as in Section 6.

### 11.3. Method Reference Accessing an Element's Receiver

~~~java
// May throw NPE if the source contains a null employee.
employees.stream().map(Employee::name);
~~~

A method reference **does not** automatically include a null guard. It is just a concise syntax for a method call matching a SAM type.

### 11.4. Stream.map Can Produce New Nulls

~~~java
employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name);
~~~

This is an illustrative snippet. The pipeline removes null `Employee` elements, yet can still produce null `String` values if `name()` returns null. **Stream.map does not require the mapper result to be non-null**. Only add `filter(Objects::nonNull)` after `map` if the goal is to remove missing values.

### 11.5. Collection-Accepting APIs May Forbid Null

- **List.of(...)**, **Set.of(...)**, and **Map.of(...)** do not allow null elements/keys/values respectively.
- **Arrays.asList(...)** can contain null elements.
- **Stream.toList()** in Java 17 can contain nulls in the result and returns an **unmodifiable** list.
- **Collectors.toUnmodifiableList()** does not allow null elements: if the stream has nulls, the collection can throw an NPE at the terminal operation.

This is why you should not infer from a single successful `toList()` call that a pipeline contains no nulls. Clarify the output contract.

## 12. Null Guards and Short-Circuit Evaluation with Predicate

In functional programming, **Predicate.and()** and **Predicate.or()** allow combining conditions. **Predicate.and** uses short-circuit evaluation: if the left predicate is false, the right predicate **does not run**.

~~~java
Predicate<Employee> present = Objects::nonNull;
Predicate<Employee> hasName = e -> e.name() != null;

Predicate<Employee> safe = present.and(hasName);
~~~

This is an illustrative snippet with `Predicate` and `Objects` imported. **safe.test(null)** returns false without calling `hasName.test(null)`.

Reversing the order can be dangerous:

~~~java
// May throw NPE for null because hasName runs first.
Predicate<Employee> unsafe = hasName.and(present);
~~~

**Short-circuit evaluation is a property of the composition operation**, not something Java infers from having two `Predicate` instances somewhere. Similarly, `e != null || e.name().isBlank()` is wrong if you want to guard a dereference: when `e == null`, the left side is true so the right side is not called, yet the logical result may defeat your intent; when `e` is non-null, the right side runs. Choose **&&** or **||** according to the desired logical meaning.

An example of a condition that allows null or allows a valid name:

~~~java
Predicate<Employee> optionalName = e ->
        e == null || (e.name() != null && !e.name().isBlank());
~~~

This illustrative snippet is safe under short-circuiting, but **returns true for a null Employee**. That may be valid if the business requirement genuinely accepts absence, but it is inappropriate when **filtering out null elements**. Avoid confusing dereference safety with proper data-filtering semantics.

## 13. When Should You Not Skip Null Elements?

**filter(Objects::nonNull)** is usually right for pipelines meant to discard missing data. However, not every null element should be silently discarded.

Cases to consider:

- **Mandatory records:** a critical transaction missing an object may need to report an error instead of being dropped from aggregation.
- **Data positioning:** if the position of a null is meaningful (for example, the 3rd record is missing), filtering loses the original index.
- **Auditing and data quality:** dropping elements lets the pipeline continue, but if you need to count invalid records you must measure/log them separately per policy.
- **Output APIs:** if the caller expects the output element count to match the input, filtering changes cardinality; you may need a result type that represents missing state.
- **Domain data:** a null property may represent “unknown”, “unapproved”, or “not applicable” — distinct states should not be lumped together arbitrarily.

If null violates the input contract, you can **fail fast**:

~~~java
List<Employee> checked = employees.stream()
        .map(e -> Objects.requireNonNull(e, "employee"))
        .toList();
~~~

Illustrative snippet with `Objects` and `List` imported. **Objects.requireNonNull** throws an NPE upon encountering null, instead of dropping the record. `checked` is only created successfully if every element is valid; this rule is appropriate when missing `Employee` instances are not permitted.

If you need to distinguish multiple error types or preserve the original element position, build a dedicated validation result model (**record ValidationResult(...)**, index-based error reporting, or an appropriate `Result` type) rather than just filtering “so it doesn't crash.”

## 14. Streams and Null Sources: Do Not Confuse a Null Stream with Null Elements

There is a very important difference:

~~~java
List<String> names = null;
// names.stream() → NPE before creating the Stream.
~~~

This is an illustrative snippet. **filter(Objects::nonNull)** only checks **elements inside the Stream**; it cannot protect `names.stream()` if the `names` variable itself is null.

A good API should explicitly specify that returned collections are **non-null**; when there are no elements, return **List.of()** or an appropriate empty collection. If integrating with a legacy source that may return null, normalize at the boundary:

~~~java
List<String> source = legacyResult == null
        ? List.of()
        : legacyResult;

List<String> valid = source.stream()
        .filter(Objects::nonNull)
        .toList();
~~~

This is an illustrative snippet with a `legacyResult` variable of type `List<String>` and `List` and `Objects` imported. The two steps have different responsibilities: the first protects the collection reference; the second handles null elements inside the collection.

**Do not do this automatically** if a null collection actually indicates a data error that must be reported. Do not turn every null into empty just to make the Stream run.

## 15. Being Careful with Performance, Parallelism, and Mutable State

### 15.1. filter Is Usually Better Than try/catch NPE

Writing `filter(Objects::nonNull)` or explicit guards is a predictable approach. You should not wrap an entire pipeline in `catch(NullPointerException)` to skip data, because it can hide bugs unrelated to the expected null data.

Anti-pattern example:

~~~java
// Illustrative anti-pattern: do not swallow all NPEs.
try {
    return employees.stream()
            .map(Employee::name)
            .toList();
} catch (NullPointerException ignored) {
    return List.of();
}
~~~

This is an illustrative snippet inside a method returning `List<String>`, not a standalone program. It returns an empty list even if only a single element is malformed, which can lose valid data and mask programming bugs.

### 15.2. Predicates Should Not Rely on Side Effects

Do not mutate data inside `filter` just to “fix null” before processing. It is better to create a clearly named transformation step, use immutable objects, or validate at the boundary. In Streams, side effects can be hard to reason about, especially when the pipeline runs in parallel.

### 15.3. Concurrent Mutation Can Make Null Guards Insufficient

If an object has a mutable field and another thread modifies that field between two reads, the code:

~~~java
if (employee.name() != null) {
    System.out.println(employee.name().length());
}
~~~

still carries a risk when the getter returns different values across the two calls. For multithreaded programs, you need synchronization rules, an immutable snapshot, or reading into a safe local variable per policy:

~~~java
String name = employee.name();
if (name != null) {
    System.out.println(name.length());
}
~~~

These are illustrative snippets inside a method and assume `employee` is already non-null. Reading into a local variable only avoids **reading the same field twice**; it does not by itself create visibility or thread-safety guarantees for the whole program. In immutable domain code (such as a record containing a `String`), field mutation issues are much less likely.

### 15.4. Primitive Streams and Null Wrappers

A **mapToInt(Employee::age)** pipeline with a nullable `Integer age` can throw an NPE due to unboxing. You must filter `age != null` first, or use a conversion step with a policy for missing values:

~~~java
int sum = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::age)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
~~~

This is an illustrative snippet requiring `Objects` to be imported and assuming `employees` contains `Employee` instances with `Integer age`. The `mapToInt(Integer::intValue)` step is only called after null `Integer` values are removed. If a missing `age` property is a business error, validate and report it instead of excluding it from the aggregation.

## 16. Checklist When Writing Filtering and Element-Selection Pipelines

Before implementing a `stream().filter(...).map(...).findFirst()` chain, answer these questions:

1. **Can the collection/stream itself be null?** Normalize or report an error at the boundary.
2. **Can the elements be null?** Choose `filter(Objects::nonNull)` or fail fast.
3. **Are there nullable properties?** Place a guard before calling methods on that property.
4. **Are there nested properties?** Check every layer: `Customer → Address → City`.
5. **Is there unboxing from wrappers?** Null `Integer`, `Long`, and `Boolean` all need a policy.
6. **Are you selecting with findFirst/findAny?** Do not allow the selected element to be null.
7. **Are you sorting or comparing properties?** Distinguish a null object from a null sort key; choose `Comparator.nullsFirst/Last` when appropriate.
8. **Should missing data be dropped, replaced, or reported as an error?** Do not let filter syntax decide business logic for you.
9. **Are there side effects or concurrently mutated data?** Avoid side effects and unstable repeated getter reads.
10. **Have you tested nulls in every position?** Null elements, null fields, null nested objects, null collections, all-null lists, and empty lists are all worth testing.

## 17. Practice Exercises

### Exercise 1: Identify the NPE Location

Given the list:

~~~java
List<String> values = Arrays.asList("A", null, "B");
~~~

This is an illustrative snippet with `List` and `Arrays` imported. Predict the behavior of `values.stream().map(String::length).toList()`. Fix it using `filter(Objects::nonNull)` before `map` and predict the resulting list **[1, 1]**.

### Exercise 2: Null Elements and Nullable Fields

Given a `List<Employee>` containing one null `Employee`, one `Employee` with a null `name`, and one `Employee` with `name` `" Linh "`. Write a pipeline that returns only **["Linh"]**. Explain why two kinds of null checks are needed at two different positions.

### Exercise 3: Nested Properties

Given a `Customer` that may not have an `Address`, and an `Address` that may not have a `city`. Write a Stream pipeline that returns a list of non-null cities; then write a method `Optional<String> cityOf(Customer c)` using `ofNullable` and `map`.

### Exercise 4: Selecting the First Valid Element

The list `[null, "  ", "ab", null, "cd"]` needs the first non-blank code selected. Use `filter(Objects::nonNull)`, `filter(s -> !s.isBlank())`, and then `findFirst()`. Explain why `findFirst()` is not used before `filter`.

### Exercise 5: Nullable Comparator

Given an `Item` with an `Integer price` field and a list containing a null `Item`, an `Item` with a null price, an `Item` with price 10, and an `Item` with price 20. Write two solutions: **removing all Items missing a price** and **keeping Items with a null price but placing them last**. Explain the different roles of `filter(Objects::nonNull)` and `Comparator.nullsLast`.

### Exercise 6: Designing Business Requirements

A revenue report contains a null transaction line. Should you use `filter(Objects::nonNull)` and sum the revenue, or stop processing and report an error? State the conditions that guide the choice, especially when missing data affects financial accuracy.

## 18. Key Takeaways

- **Check for null before dereferencing**: place `filter(Objects::nonNull)` **before** `map(Type::getter)` when elements can be null.
- **Null elements differ from nullable properties**: after mapping to a property that can be null, add another guard before calling methods on that property.
- **&& and Predicate.and() use short-circuit evaluation**, but are only safe when guards are placed in the right order.
- **findFirst/findAny do not automatically skip nulls**, and `Optional` cannot hold null; remove null elements before selecting.
- **Comparators and primitive unboxing** can also cause NPEs even when the outer object is non-null.
- **The decision to drop, replace, or report errors must belong to the business contract**, not merely to avoiding exceptions.

Practical mindset: **“At this step, which receiver is about to be accessed, and what guarantee ensures that receiver is non-null?”** Asking that question at each filtering, selection, and transformation step makes Java pipelines easier to read, test, and trust.