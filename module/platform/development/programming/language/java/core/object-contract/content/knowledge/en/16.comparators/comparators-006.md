# `Comparator.nullsFirst()` and `Comparator.nullsLast()` in Java

When sorting, real-world data can contain `null`: a `null` element in a `List`, an unfilled field, or a key extracted from an object whose value is `null`. Passing those values straight into a comparator that does not support `null` can cause a `NullPointerException`. Java provides two static methods—**`Comparator.nullsFirst()`** and **`Comparator.nullsLast()`**—to specify the position of `null` explicitly.

Lesson goal: understand the contract of both methods, distinguish a **null element** from a **null property**, combine them with `comparing`/`thenComparing`/`reversed`, and avoid bugs when using `List.sort`, streams, or `TreeSet`.

## 1. Meaning and API Signatures

In `java.util.Comparator`, the two methods have the form:

~~~java
public static <T> Comparator<T> nullsFirst(
        Comparator<? super T> comparator);

public static <T> Comparator<T> nullsLast(
        Comparator<? super T> comparator);
~~~

These are **API signatures for reference**, not declarations to paste into your class. They produce a **new comparator** from the provided comparator:

| Situation | `nullsFirst(c)` | `nullsLast(c)` |
|---|---|---|
| Both are `null` | Equal: result `0` | Equal: result `0` |
| Left is `null`, right is non-null | Negative number | Positive number |
| Left is non-null, right is `null` | Positive number | Negative number |
| Both are non-null | Delegates to `c.compare(a,b)` | Delegates to `c.compare(a,b)` |

Only the **sign** of the comparison result is part of the contract: never write code that depends on receiving exact `-1` or `1`. The two methods do not mutate lists or remove elements; they only create an **ordering rule** to pass wherever a `Comparator<T>` is needed.

How to read them:

- `Comparator.nullsFirst(Comparator.naturalOrder())`: `null` values come **first**, non-null values ascend in natural order.
- `Comparator.nullsLast(Comparator.naturalOrder())`: `null` values come **last**, non-null values ascend.
- Non-null elements are still compared by the inner comparator. Whether two non-null values are considered tied is decided by the **inner comparator**.

`Comparator.naturalOrder()` requires a type with a suitable natural order (typically implementing `Comparable`). `nullsFirst`/`nullsLast` do not themselves grant comparability to objects that lack an order.

## 2. Basic Example: Sorting a List Containing Null Elements

Suppose we have boxed `Integer` values:

~~~java
List<Integer> numbers =
        new ArrayList<>(Arrays.asList(3, null, 1, null, 2));

numbers.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
System.out.println(numbers); // [null, null, 1, 2, 3]

numbers.sort(Comparator.nullsLast(Comparator.naturalOrder()));
System.out.println(numbers); // [1, 2, 3, null, null]
~~~

This is an illustrative snippet placed inside `main`, requiring imports of `List`, `ArrayList`, `Arrays`, and `Comparator` from `java.util`. `ArrayList` allows `null`; the list is created via `Arrays.asList` and then copied into an `ArrayList` for easy mutation.

If you call `numbers.sort(Comparator.naturalOrder())` directly on a list containing `null`, natural-order comparison cannot handle `null` elements and typically throws `NullPointerException`. The fix is to **wrap the comparator** with `nullsFirst` or `nullsLast`, according to data requirements.

`List.of(3, null, 1)` cannot be used to create a similar fixture, because the `List.of` factory rejects `null` immediately upon creation. That is a policy of the **collection factory**, independent of the comparator.

## 3. Null Objects and Null Sort Keys Are Different Things

Consider a record:

~~~java
record Employee(String name, Integer priority) {}
~~~

A `List<Employee>` can have two kinds of `null`:

1. **Null element**: the `Employee` reference itself in the list is `null`.
2. **Null key**: the element is a valid `Employee`, but `employee.priority()` is `null`.

Two ways of placing `nullsLast` produce different results:

~~~java
// Handles null Employee elements; valid Employees are compared by priority.
Comparator<Employee> objectNullLast =
        Comparator.nullsLast(
                Comparator.comparing(Employee::priority));

// Handles null priority values, but still requires Employee to be non-null.
Comparator<Employee> keyNullLast =
        Comparator.comparing(
                Employee::priority,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Both are illustrative snippets requiring an `Employee` record as above. `objectNullLast` is **unsafe when the `priority` property is null**, because `Comparator.comparing(Employee::priority)` compares keys using natural ordering by default. `keyNullLast` handles `priority == null`, but is **unsafe if the entire `Employee` element is null**, because the `Employee::priority` extractor cannot be called on `null`.

To handle **both**, apply `nullsLast` at two layers:

~~~java
Comparator<Employee> byPriority =
        Comparator.nullsLast(
                Comparator.comparing(
                        Employee::priority,
                        Comparator.nullsLast(
                                Comparator.naturalOrder())));
~~~

The **inner** comparator determines the position of a `priority == null` *key* among non-null Employees. The **outer** comparator determines the position of an `Employee == null` *object*. This is the most important pattern when data nests nullable references.

Similarly, `Comparator.comparing(Employee::name, Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER))` permits **null names**, but does not yet permit **null Employees**. If both are needed, wrap the entire comparator with `Comparator.nullsFirst` or `nullsLast` as well.

## 4. Combining with `thenComparing` to Break Ties

An application often sorts employees by ascending `priority`, while employees at the same priority level should be further sorted by name. Rules to define:

- Null `Employee` comes last.
- Null `priority` comes after numeric priorities.
- Within the same priority (including two null keys), compare name ascending.
- If name can also be null, add a dedicated null policy for name.

Example when name is always non-null:

~~~java
Comparator<Employee> order =
        Comparator.nullsLast(
                Comparator.comparing(
                        Employee::priority,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(Employee::name));
~~~

This is an illustrative snippet in a program containing the `Employee` record. `thenComparing` runs when the preceding comparison returns `0` between two **non-null** Employees. If both priorities are null, the key comparator returns `0`; then ordering by name decides who comes first.

If name is also nullable, replace the name part with:

~~~java
.thenComparing(
        Employee::name,
        Comparator.nullsLast(Comparator.naturalOrder()))
~~~

This is only a **method-chaining continuation** of the comparator above, not a standalone Java expression. `thenComparing` makes the order deterministic by key logic; it **does not automatically remove duplicate records**. With `List.sort` and `Stream.sorted`, elements tied under the comparator remain in the result.

## 5. `reversed()` Can Also Flip Null Placement

A common mistake is thinking `reversed()` only reverses the ascending/descending direction of non-null values. In reality, it reverses **the entire ordering relation**, including the position of `null`.

~~~java
Comparator<Integer> firstAscending =
        Comparator.nullsFirst(Comparator.naturalOrder());

Comparator<Integer> reversedWhole = firstAscending.reversed();
// reversedWhole: numbers descending, null moves to the end.

Comparator<Integer> firstDescending =
        Comparator.nullsFirst(Comparator.reverseOrder());
// firstDescending: null stays first, numbers descending.
~~~

Therefore:

| Requirement | How to create the comparator |
|---|---|
| Null first, numbers ascending | `nullsFirst(naturalOrder())` |
| Null last, numbers ascending | `nullsLast(naturalOrder())` |
| Null first, numbers descending | `nullsFirst(reverseOrder())` |
| Null last, numbers descending | `nullsLast(reverseOrder())` |
| Flip an existing rule completely | `existingComparator.reversed()` |

If you already have a multi-layer comparator, calling `reversed()` at the end reverses **its entire order**. To preserve null placement while reversing only one field, reverse **that field's comparator first**, then pass it into `nullsFirst`/`nullsLast` at the appropriate layer.

## 6. Runnable Java 17 Program

Save the file **`ComparatorNullsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorNullsDemo {
    record Employee(String name, Integer priority) {}

    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(Arrays.asList(3, null, 1, null, 2));

        numbers.sort(Comparator.nullsFirst(
                Comparator.naturalOrder()));
        System.out.println("numbers first: " + numbers);

        numbers.sort(Comparator.nullsLast(
                Comparator.naturalOrder()));
        System.out.println("numbers last: " + numbers);

        List<Employee> employees = new ArrayList<>(
                Arrays.asList(
                        new Employee("Lan", null),
                        new Employee("An", 2),
                        new Employee("Binh", null),
                        new Employee("Cuong", 1),
                        null,
                        new Employee("Dung", 2)));

        Comparator<Employee> employeeOrder =
                Comparator.nullsLast(
                        Comparator.comparing(
                                Employee::priority,
                                Comparator.nullsLast(
                                        Comparator.naturalOrder()))
                                .thenComparing(Employee::name));

        employees.sort(employeeOrder);
        List<String> labels = employees.stream()
                .map(e -> e == null
                        ? "<null-employee>"
                        : e.name() + ":" + e.priority())
                .toList();
        System.out.println("employees: " + labels);

        List<Integer> reverseExample =
                new ArrayList<>(Arrays.asList(null, 1, 3));
        Comparator<Integer> firstAscending =
                Comparator.nullsFirst(Comparator.naturalOrder());

        reverseExample.sort(firstAscending.reversed());
        System.out.println("reversed whole: " + reverseExample);

        reverseExample.sort(Comparator.nullsFirst(
                Comparator.reverseOrder()));
        System.out.println("null first descending: " + reverseExample);

        Comparator<String> onlyNullPolicy =
                Comparator.nullsFirst(null);
        System.out.println("null-only rule, a vs z equal: "
                + (onlyNullPolicy.compare("a", "z") == 0));
        System.out.println("null-only rule, null before a: "
                + (onlyNullPolicy.compare(null, "a") < 0));

        TreeSet<String> names = new TreeSet<>(
                Comparator.nullsFirst(
                        String.CASE_INSENSITIVE_ORDER));
        names.add(null);
        names.add("An");
        names.add("AN");
        System.out.println("tree set size: " + names.size());
        System.out.println("tree set contains null: "
                + names.contains(null));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac ComparatorNullsDemo.java
java ComparatorNullsDemo
~~~

Expected output:

~~~text
numbers first: [null, null, 1, 2, 3]
numbers last: [1, 2, 3, null, null]
employees: [Cuong:1, An:2, Dung:2, Binh:null, Lan:null, <null-employee>]
reversed whole: [3, 1, null]
null first descending: [null, 3, 1]
null-only rule, a vs z equal: true
null-only rule, null before a: true
tree set size: 2
tree set contains null: true
~~~

**Reading the results:**

1. The first two comparators only change the position of `null`, while non-null numbers stay ascending.
2. The employee comparator has **two layers of null protection**: a null `priority` field sorts after numeric priorities, while a null `Employee` element goes to the very end of the list. `thenComparing(Employee::name)` orders `An` before `Dung` (both priority 2) and `Binh` before `Lan` (both priority null).
3. `firstAscending.reversed()` moves null from the front to the end, while reversing numbers to descending. To keep null at the front, put `reverseOrder()` **inside** `nullsFirst`.
4. When the comparator passed into `nullsFirst` is `null`, all **non-null** values are treated as equal (comparison result `0`), yet all of them come after null.
5. `TreeSet` is supplied with a null-supporting comparator, so it can hold one null. The two strings `"An"` and `"AN"` are treated as the same key because `CASE_INSENSITIVE_ORDER.compare` returns `0`, even though `String.equals` is case-sensitive.

Note: the `TreeSet` output in the example only prints element count and `contains`; do not assume every `TreeSet` allows null by default. That **depends on the comparator in use**.

## 7. Case Where the Input Comparator Is Null

Java permits:

~~~java
Comparator<String> c = Comparator.nullsLast(null);
~~~

This is valid syntax. When the argument comparator is **`null`**, the wrapper only distinguishes **null** from **non-null**; all non-null values are treated as tied because there is no underlying comparator to order them.

Consequences:

- `c.compare("a","z") == 0` even though the two strings are unequal by `String.equals`.
- A `TreeSet<String>` using `c` can collapse all non-null strings into **a single key**.
- Non-null elements have no lexicographical ordering relation; this option **does not replace** `Comparator.naturalOrder()`.

In most programs that need meaningful sorting, supply a **non-null** comparator such as `naturalOrder()`, `reverseOrder()`, or `comparing(...)`.

## 8. Streams, `List.sort`, and Ordered Collections

The same comparator can be used across multiple APIs:

~~~java
List<Integer> sorted = values.stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .toList();
~~~

Here `values` is an already-declared `List<Integer>`. `Stream.sorted` produces a stream in the appropriate order; `toList()` collects the result into a list without requiring the source list to be mutated. `List.sort(c)` sorts **in place** on a mutable list; `Collections.sort(list, c)` uses the supplied comparator.

When using `TreeSet` or `TreeMap`, `compare == 0` means **duplicate key**. A comparator inspecting only one property or having a `null` underlying comparator can cause multiple objects that differ by `equals` to be merged into one. Safe `null` handling **does not guarantee** that the comparator is consistent with `equals`; verify the contract and intent of the collection.

## 9. Common Mistakes

| Mistake | Why it happens | Fix |
|---|---|---|
| `naturalOrder()` encounters null | No policy for null | Wrap with `nullsFirst`/`nullsLast` |
| Wrapping outer comparator while key is still null | `nullsLast(comparing(...))` only handles **null objects** | Wrap the **key's** comparator with nullsFirst/Last |
| Protecting the key while the object can be null | Key-extracting method reference gets called on null | Wrap the entire comparator at the outer level |
| `comparingInt(Employee::priority)` with null `Integer priority` | Unboxing `null` causes `NullPointerException` | Use `comparing` with a null-safe key comparator or choose a default value |
| `reversed()` flips null placement | Reverses the entire order | Reverse the base comparator **before** wrapping the null policy |
| `nullsFirst(null)` used to sort strings alphabetically | All non-null values tie | Pass `Comparator.naturalOrder()` or a real comparator |
| `TreeSet` drops distinct objects | Comparator returns `0` for multiple values | Add a key-distinguishing tie-breaker or choose another collection |
| Assuming `nullsLast` filters out nulls | The wrapper only specifies ordering | Use `filter(Objects::nonNull)` if the problem actually requires removing nulls |
| Secondary name/key is also null | `thenComparing` is unprotected | Define a null policy for each nullable key |

## 10. Choosing a Solution by Requirement

- **Null first, values ascending:** `Comparator.nullsFirst(Comparator.naturalOrder())`.
- **Null last, values ascending:** `Comparator.nullsLast(Comparator.naturalOrder())`.
- **Null last, values descending:** `Comparator.nullsLast(Comparator.reverseOrder())`.
- **Non-null object, nullable key:** `Comparator.comparing(Foo::key, Comparator.nullsLast(Comparator.naturalOrder()))`.
- **Both object and key can be null:** wrap the key comparator as above, then wrap with `Comparator.nullsLast(...)` for the object.
- **Multiple keys:** use `thenComparing`; apply the null policy **on each key** that needs null handling.

When testing, cover at minimum these pairs: `null/null`, `null/value`, `value/null`, two distinct values, two non-null objects with null keys, two objects with the same key but different secondary attributes, and reversed ordering with `reversed()`.

## 11. Self-Check

**Question 1.** What does `Comparator.nullsFirst(Comparator.naturalOrder())` return when comparing `null` with `5`?  
**Answer:** A negative number; null comes before 5. Do not depend on a specific negative integer value.

**Question 2.** Why can `Comparator.nullsLast(Comparator.comparing(Employee::priority))` still throw an exception?  
**Answer:** It only permits a null **Employee object**. A non-null Employee with `priority == null` still fails when comparing keys under natural ordering.

**Question 3.** To sort priority descending while keeping null priority at the end, what should be used?  
**Answer:** `Comparator.comparing(Employee::priority, Comparator.nullsLast(Comparator.reverseOrder()))` for non-null Employees; add an outer wrapper if Employee itself can be null.

**Question 4.** Given `Comparator<Integer> c = Comparator.nullsFirst(Comparator.naturalOrder())`, does `c.reversed()` still keep null first?  
**Answer:** No. It reverses the entire order, moving null to the end and sorting numbers descending.

**Question 5.** Can `Comparator.nullsLast(null)` compare two Strings alphabetically?  
**Answer:** No. It treats any two non-null Strings as equal, returning `0`.

**Takeaway:** `nullsFirst`/`nullsLast` **wrap a comparator**, placing null at the front or end without comparing non-null contents themselves. For objects with nullable properties, place the null policy **at the right layer**, and account for the effects of `reversed`, `thenComparing`, and the collection being used.