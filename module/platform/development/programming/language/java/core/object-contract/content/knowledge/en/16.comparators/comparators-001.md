# `Comparator<T>`: Defining Order Outside the Class

## 1. Why Is an External Order Needed?

In Java, there are classes whose objects can be sorted by **multiple valid criteria**. For example, an employee has an identifier, a name, and an age. A list of employees might need to be displayed in ascending order by age, alphabetically by name, or by employee ID. There is no reason to force one of those criteria to be hardcoded into the `Employee` class itself.

`java.util.Comparator<T>` addresses that need: it describes **a strategy for comparing two objects of type `T` outside the data class**. You can create multiple comparators, choose the comparator where it is needed, and never have to modify the source code of `Employee`.

```java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> byName =
        Comparator.comparing(Employee::name);
```

These two statements are **illustrative fragments**, requiring `import java.util.Comparator` and an `Employee` type with `age()`/`name()` accessors. In the complete program section below, there will be a concrete data class and a runnable example.

With a valid comparator, `compare(a, b)` returns:

| Result | Meaning |
| --- | --- |
| Negative number | `a` comes **before** `b` |
| `0` | `a` and `b` are **order-equivalent** according to the comparator |
| Positive number | `a` comes **after** `b` |

The values `-1` or `1` are only possible cases. **The contract requires the sign**, not always returning exact `-1, 0, 1`.

## 2. Distinguishing `Comparator`, `Comparable`, and `equals()`

| API | Who defines the order | Suitable use case |
| --- | --- | --- |
| `Comparable<T>` with `compareTo(T)` | **Inside the class** implementing `Comparable` | A single natural, default, and stable order for the type |
| `Comparator<T>` with `compare(T, T)` | **Outside the class**, via object/lambda/method reference | Multiple orders, or a data type that cannot/should not be modified |
| `Object.equals(Object)` | Inside the class (or inherited) | Determining whether two objects are **equal in logical identity** |

`Comparable` is the appropriate choice when there is one clear natural order, such as `String` comparing lexicographically or `Integer` comparing by numeric value. Conversely, `Comparator` is suitable when you need to sort `Employee` by age today and by name tomorrow, or when a library provides a `final` class that cannot be edited.

**`compare(a, b) == 0` does not automatically mean `a.equals(b)`.** A comparator might consider two employees of the same age equivalent **with respect to age order** even though they have different identifiers. This is usually acceptable when merely sorting a list; however, care is needed with structures that use the comparator to identify keys, such as `TreeSet` and `TreeMap`.

A comparator does not alter an object's `equals()` or `hashCode()`. It only provides an ordering relation chosen for the operation at hand.

## 3. How to Create a Comparator Without Writing a Separate Class

Since Java 8, `Comparator` is a **functional interface**: its primary abstract method is `int compare(T o1, T o2)`. Therefore, you can use a lambda or a method reference.

### Writing with a lambda

```java
Comparator<Employee> byAge =
        (left, right) -> Integer.compare(left.age(), right.age());
```

`Integer.compare` is preferred over `left.age() - right.age()`: subtracting two integers can **overflow**, producing an incorrect ordering result. For example, `Integer.MAX_VALUE - (-1)` exceeds the `int` range.

### Writing with factory methods

```java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);

Comparator<Employee> byId =
        Comparator.comparingInt(Employee::id);

Comparator<Employee> byName =
        Comparator.comparing(Employee::name);
```

These comparators all have the type `Comparator<Employee>`, but each uses **a different sort key**. `comparingInt` avoids boxing an `int` key into an `Integer` for comparison. Similar methods include `comparingLong` and `comparingDouble`; use `comparing` for object keys like `String`.

If the key does not have a suitable natural order, pass an additional comparator for the key:

```java
Comparator<Employee> byNameIgnoringCase =
        Comparator.comparing(
                Employee::name,
                String.CASE_INSENSITIVE_ORDER);
```

This snippet assumes names are non-null. If a name can be null, you must explicitly specify the rule for placing nulls first/last or filter out invalid records.

### Combining multiple keys with `thenComparing`

Sort by age ascending, and **if ages are equal, by ID ascending**:

```java
Comparator<Employee> byAgeThenId =
        Comparator.comparingInt(Employee::age)
                  .thenComparingInt(Employee::id);
```

When two people have the same age, the comparator does not immediately return `0`, but uses the ID to decide. If the ID is **unique** and defines the logical identity of `Employee`, comparing by ID last helps avoid treating two different people as the same element in a `TreeSet`.

However, adding a tie-breaker is only correct if the final key is consistent with the class's equality policy. If a class has `equals()` based on multiple fields, understand those fields clearly before expecting `compare(a,b)==0` to be equivalent to `equals()`.

### Reversing order with `reversed()`

```java
Comparator<Employee> descendingAgeThenId =
        byAgeThenId.reversed();
```

`reversed()` reverses the **entire** order, including secondary keys: age descending, and if ages are equal, ID also descending. If you want *age descending but ID ascending*, reverse the age comparator **before** adding the secondary key:

```java
Comparator<Employee> ageDescendingIdAscending =
        Comparator.comparingInt(Employee::age)
                  .reversed()
                  .thenComparingInt(Employee::id);
```

The two strategies differ in their results when people have the same age.

## 4. Runnable Java 17 Program

Create the file `ExternalComparatorDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ExternalComparatorDemo {

    // Record only holds data; does not implement Comparable.
    record Employee(int id, String name, int age) {}

    static List<Integer> ids(List<Employee> employees) {
        return employees.stream()
                .map(e -> e == null ? -1 : e.id())
                .toList();
    }

    public static void main(String[] args) {
        Employee alice = new Employee(2, "Alice", 30);
        Employee bao = new Employee(1, "Bao", 25);
        Employee chi = new Employee(3, "Chi", 25);

        List<Employee> original = List.of(alice, bao, chi);

        Comparator<Employee> byAgeThenId =
                Comparator.comparingInt(Employee::age)
                          .thenComparingInt(Employee::id);

        Comparator<Employee> byNameThenId =
                Comparator.comparing(
                        Employee::name,
                        String.CASE_INSENSITIVE_ORDER)
                          .thenComparingInt(Employee::id);

        List<Employee> byAge = new ArrayList<>(original);
        byAge.sort(byAgeThenId);
        System.out.println("original: " + ids(original));
        System.out.println("age then id: " + ids(byAge));

        List<Employee> byName = new ArrayList<>(original);
        byName.sort(byNameThenId);
        System.out.println("name then id: " + ids(byName));

        List<Employee> reversed = new ArrayList<>(original);
        reversed.sort(byAgeThenId.reversed());
        System.out.println("reversed all keys: " + ids(reversed));

        List<Employee> onlyAgeDescending = new ArrayList<>(original);
        onlyAgeDescending.sort(
                Comparator.comparingInt(Employee::age)
                          .reversed()
                          .thenComparingInt(Employee::id));
        System.out.println("age down, id up: "
                + ids(onlyAgeDescending));

        System.out.println("stream sorted: " +
                ids(original.stream().sorted(byAgeThenId).toList()));

        Comparator<Employee> onlyAge =
                Comparator.comparingInt(Employee::age);
        System.out.println("bao equals chi: " + bao.equals(chi));
        System.out.println("age-only compare bao chi: "
                + onlyAge.compare(bao, chi));

        Set<Employee> loose = new TreeSet<>(onlyAge);
        loose.add(bao);
        loose.add(chi);
        loose.add(alice);
        System.out.println("TreeSet age-only size: " + loose.size());
        System.out.println("TreeSet age-only contains chi: "
                + loose.contains(chi));

        Set<Employee> strict = new TreeSet<>(byAgeThenId);
        strict.add(bao);
        strict.add(chi);
        strict.add(alice);
        System.out.println("TreeSet age-id size: " + strict.size());

        List<Employee> nullable =
                new ArrayList<>(Arrays.asList(chi, null, alice, bao));
        nullable.sort(Comparator.nullsLast(byAgeThenId));
        System.out.println("nulls last IDs: " + ids(nullable));
    }
}
```

Run with JDK 17 or later:

```bash
javac ExternalComparatorDemo.java
java ExternalComparatorDemo
```

Exact stdout output:

```text
original: [2, 1, 3]
age then id: [1, 3, 2]
name then id: [2, 1, 3]
reversed all keys: [2, 3, 1]
age down, id up: [2, 1, 3]
stream sorted: [1, 3, 2]
bao equals chi: false
age-only compare bao chi: 0
TreeSet age-only size: 2
TreeSet age-only contains chi: true
TreeSet age-id size: 3
nulls last IDs: [1, 3, 2, -1]
```

In the `ids` method, the value `-1` is only a **printed marker for a null element**. The people in the example all have positive IDs, so this marker can be distinguished. In a real program, you should not use `-1` as a null sentinel if `-1` is a valid ID.

### Result analysis

- The `original` list preserves creation order: Alice (id 2), Bao (id 1), Chi (id 3). `sort` only modifies the **`ArrayList` copy**, leaving `original` unchanged.
- `byAgeThenId` places Bao and Chi (age 25) before Alice (age 30), then breaks the tie with Bao id 1 before Chi id 3.
- `byAgeThenId.reversed()` reverses both the age and ID keys, giving Alice first, then Chi, then Bao. Reversing only the age key before chaining the ID produces Alice, Bao, Chi.
- `stream().sorted(byAgeThenId)` returns a new list in the corresponding order. It does not modify `original`.
- `bao.equals(chi)` is `false` because records compare **all components** automatically; the comparator checking only age returns `0`.
- `TreeSet` uses the sign of `compare` to decide duplicate elements. When comparing only by age, adding 25-year-old Chi after 25-year-old Bao does not add a new element; `contains(chi)` is still `true` because the comparator considers Chi equivalent to Bao.
- `byAgeThenId` distinguishes Bao's and Chi's IDs, so the second `TreeSet` contains all three people.
- `Comparator.nullsLast(byAgeThenId)` places null elements at the end while non-null elements still follow age and id. The program illustrates why null must be actively handled when the data source allows it.

## 5. Mechanics of `List.sort` and `Stream.sorted`

### Sorting directly on a list

`List.sort(Comparator<? super E> c)` **mutates the element order of the list on which the method is called** and does not create a new list. Therefore, on an unmodifiable list that does not allow reordering (such as `List.of(...)`), calling `sort` may throw `UnsupportedOperationException`.

```java
List<Employee> mutable = new ArrayList<>(employees);
mutable.sort(byAgeThenId);
```

This snippet is a fragment assuming `employees` and `byAgeThenId` exist. Creating a mutable copy keeps the input source intact.

By contract, sorting with `List.sort` is **stable**: when the comparator returns `0` for two elements, their original relative order is preserved. Even so, a stable sort **is no substitute for a secondary key** if the business logic wants a repeatable total order regardless of how the input was entered. Chaining `thenComparing` makes the rule explicit.

### Sorting via stream

`stream.sorted(comparator)` returns a sorted stream for subsequent operations; a list can be produced with `toList()` in Java 17:

```java
List<Employee> sorted = employees.stream()
        .sorted(byAgeThenId)
        .toList();
```

The result of `Stream.toList()` is an **unmodifiable** list, so if you want to sort it in-place later, copy it into an `ArrayList`. For streams with an encounter order, `Stream.sorted` guarantees stability; for unordered streams, there is no stability guarantee with respect to a non-existent encounter order.

Besides `List` and streams, methods like `Collections.sort(list, comparator)` or `Arrays.sort(array, comparator)` also accept a comparator matching the element type. Choose the API based on the data type and whether you want to mutate the original collection.

## 6. Contract of a Valid `Comparator`

A comparator must describe a valid ordering relation over the entire domain of values it accepts. With `sgn` denoting the sign of an integer, the three key properties are:

1. **Antisymmetry (sign symmetry):** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
2. **Transitivity:** if `a > b` and `b > c` according to the comparator, then `a > c`.
3. **Consistent equivalence classes:** if `compare(a,b)==0`, comparing `a` and `b` against the same `z` must produce results with the same sign.

Do not use integer subtraction as a general-purpose comparison method, because subtraction can overflow. Use `Integer.compare`, `Long.compare`, `Double.compare`, or the `comparingInt/Long/Double` factories depending on the key type. `Double.compare` also clearly defines the ordering for `NaN`, infinities, and `-0.0`.

If a comparator reads random numbers, the system clock, mutable configuration flags, or fields that are modified during sorting, the order can contradict itself. Java may detect some errors and throw `IllegalArgumentException`, but it does not guarantee detection of every broken comparator. The lesson on *sign contract, transitivity, and zero-groups* will test these conditions using pairs, triples of values, and edge cases.
## 7. `compare(a,b) == 0` and `equals()` in `TreeSet` / `TreeMap`

`Comparator` determines **order**, whereas `equals()` determines **equality according to the object's contract**. With `List.sort`, two employees of the same age are still kept in the list. However, `TreeSet` and `TreeMap` use `compare(a,b)==0` to identify equivalent elements/keys. In the example:

- `bao.equals(chi)` is `false` because the two records differ in ID and name.
- The age-only comparator returns `0`, so `TreeSet` keeps one representative for the age-25 group and `contains(chi)` can still return `true`.
- `TreeMap` uses the same rule and can replace the **value** of an existing mapping when `put` is called with a new key that compares equal to 0.

An ordering is **consistent with equals** when `compare(a,b)==0` *if and only if* `a.equals(b)` (over the valid data domain). **Both directions** must be checked. `byAgeThenId` in the example distinguishes the existing records, but it is not necessarily consistent with `equals` for every `Employee`: two records with the same age and ID but different names still compare equal to 0. With `TreeSet/TreeMap`, identify the proper identity key or use a different structure if you want to retain all elements of the same rank. A dedicated lesson on Comparators used for display versus equality relations analyzes both mismatch directions in depth.
## 8. Handling `null` and Nullable Keys

By default, comparators from `Comparator.comparingInt(Employee::age)` invoke the getter and do not handle `null` objects, so comparing against a null element can throw `NullPointerException`.

To place **all null employees** at the end:

```java
Comparator<Employee> nullableEmployees =
        Comparator.nullsLast(byAgeThenId);
```

To place nulls at the beginning, use `Comparator.nullsFirst(byAgeThenId)`. These two methods handle **the compared object itself being null**.

This differs from the case of **a nullable key field inside an object**. For example, `name` can be null while `Employee` itself is a non-null object. In that case, you must wrap the key's comparator:

```java
Comparator<Employee> nullableNames =
        Comparator.comparing(
                Employee::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

This snippet sorts `name == null` after non-null names, within the scope of non-null employee objects. If both the employee and the name can be null, combine **two policy layers**:

```java
Comparator<Employee> bothNullable =
        Comparator.nullsLast(nullableNames);
```

The snippets above are illustrative fragments assuming the `Employee` record and appropriate comparators exist. You should not arbitrarily treat an empty string `""` as null or replace null with a default value if doing so could erase business data distinctions.

## 9. Common Mistakes When Defining External Order

- **Omitting a tie-breaker when uniqueness is needed.** Comparing solely by age can cause a `TreeSet` to drop another employee of the same age.
- **Forgetting that `reversed()` reverses secondary keys too.** If you want opposite directions for primary/secondary keys, place `reversed()` at the right position in the factory method chain.
- **Writing `return a.age() - b.age()`.** Subtraction can overflow; use `Integer.compare` or `Comparator.comparingInt`.
- **Confusing `compare() == 0` with `equals()`.** The two relations do not share the same default meaning; check separately when using them as collection keys.
- **Misreading `sort` as immutable.** `List.sort` mutates the list it is called on; `stream.sorted(...).toList()` creates a result list.
- **Overlooking null.** `nullsFirst/nullsLast` for null objects does not automatically handle a null `name` key inside the object.
- **Trying to use a comparator on mutable data in `TreeSet`/`TreeMap`.** If the age/id fields used to position an entry in the tree change after insertion, lookups and ordering can become invalid. Prefer immutable keys, or remove and re-insert with the new state.
- **Comparator returning arbitrary values or depending on call order.** This can violate antisymmetry/transitivity, causing sorting failures and undefined behavior in terms of business semantics.

## 10. Checklist and Self-Check Exercises

### Checklist

1. Is the required order natural to the class or specific to a screen/business use case? If there are multiple options, create an external `Comparator<T>`.
2. What is the sort key? Are multiple keys (`thenComparing`) needed to break ties?
3. Do individual keys need independent ascending/descending directions, or should the entire comparator be reversed?
4. Can objects or key fields be null? Define the placement of null explicitly.
5. Does the comparator satisfy antisymmetry, transitivity, and stability when data is unchanged?
6. Is the comparator only used to sort a list, or also to determine uniqueness in a `TreeSet`/`TreeMap`?
7. If used for sorted collection keys, does `compare(a,b)==0` match the desired `equals()` policy and logical identity?
8. Are integers being compared via overflow-prone subtraction, or floating-point numbers via inconsistent rules?

### Exercises

**Exercise 1.** There are three employees: A age 30 id 2, B age 25 id 1, C age 25 id 3. With `comparingInt(age).thenComparingInt(id)`, what is the order?

**Answer:** B, C, A; age ascending first, then id ascending when ages are equal.

**Exercise 2.** What order will calling `reversed()` after chaining `age` then `id` produce?

**Answer:** A, C, B; both criteria are reversed together. To get A, B, C, reverse the age comparator before chaining ascending id.

**Exercise 3.** If `a.equals(b)` is false but `compare(a,b)` is `0`, is the comparator necessarily wrong when used with `List.sort`?

**Answer:** No. It can form a valid equal-order group, such as people of the same age; the list still keeps both elements. However, if that comparator is used as the key policy of a `TreeSet`, the two people may be merged.

**Exercise 4.** Does `Comparator.nullsLast(comparing(Employee::name))` automatically handle `employee.name() == null`?

**Answer:** No. The outer `nullsLast` only handles null `Employee` objects. To handle a null `name` field, apply `nullsLast` to the **name key** comparator inside `comparing`.

## Key Takeaways

**`Comparator<T>` allows placing sorting rules outside the data class**, so a type can be sorted by multiple criteria without modifying the class itself. Use `comparing...`, `thenComparing...`, and `reversed()` to express policies clearly, avoid overflow-prone subtraction, and define null handling when needed. With `TreeSet`/`TreeMap`, `compare(a,b)==0` is also the criterion for treating elements/keys as duplicates; therefore, the comparator must be compatible with the intended logical identity and the collection's contract.