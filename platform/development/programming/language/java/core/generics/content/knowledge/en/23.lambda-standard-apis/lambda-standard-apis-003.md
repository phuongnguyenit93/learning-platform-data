# Generics with `Comparator<T>` and Criteria Chaining in Java

## 1. Goal: type-checked multi-criteria object sorting

In Java applications, we often need to sort a list of objects by multiple attributes: employees by department then name; students by descending score then full name; products by price, update date, then identifier. Writing a single simple comparison is often not enough.

Java provides the generic **`Comparator<T>`** interface and factory/chaining methods to build ordering clearly:

```java
Comparator<Student> order =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name)
                .thenComparingInt(Student::age);
```

The snippet above is illustrative code; it assumes a `Student` record or class with `score()`, `name()`, and `age()` accessors, and importing `java.util.Comparator`.

It expresses an exact sorting contract:

1. **Descending score**: students with higher scores come first.
2. If **scores are equal**, compare **name ascending**.
3. If **both score and name are equal**, compare **age ascending**.

Placing `.reversed()` **immediately after the score comparator** is crucial: it reverses score direction without automatically reversing the two chained criteria.

**Core focus of this lesson:** Understand `Comparator<T>` as a *typed comparison contract*, know how to use lambdas/method references with `Comparator.comparing`, `comparingInt`, and `thenComparing`, place `reversed()` accurately, handle `null`, and preserve ordering correctness in `List.sort`, `Stream.sorted`, and sorted collections.

## 2. What is `Comparator<T>`?

`java.util.Comparator<T>` is a **functional interface** whose primary operation is:

```java
int compare(T left, T right);
```

Meaning of the sign of the return value:

| Result of `compare(a, b)` | Meaning |
|---|---|
| Less than 0 | `a` comes before `b` according to this comparator |
| Equal to 0 | `a` and `b` are equal **with respect to comparison order** |
| Greater than 0 | `a` comes after `b` |

There is no requirement to return strictly `-1`, `0`, or `1`; Java relies only on the **sign** of the result.

Example with integers:

```java
Comparator<Integer> ascending = (a, b) ->
        Integer.compare(a, b);
```

This is a valid lambda when `java.util.Comparator` is imported. If `a = 2`, `b = 8`, `compare(a,b)` is negative; if swapped, it is positive.

The generic type argument `Integer` in `Comparator<Integer>` lets the compiler verify that the lambda works with two `Integer` values. Writing `(a, b)` without explicit type declarations remains safe because the **target type** provides type information to the lambda.

### The comparison contract must be consistent

A Comparator is not just an arbitrary calculation returning a number. It must satisfy key properties:

- **Antisymmetry of sign**: the sign of `compare(a,b)` must be opposite the sign of `compare(b,a)` for values defined by the comparison.
- **Transitivity**: if `a > b` and `b > c` according to the comparator, then `a > c` must hold.
- **Consistency with zero**: if `compare(a,b) == 0`, comparing either `a` or `b` against another `z` must yield the same sign.
- A Comparator should give consistent results while state relevant to the ordering does not change.

Violating the contract can cause sorting algorithms to misbehave, produce unexpected results, or in some situations throw an exception for violating the general contract.

## 3. How do `Comparator<T>` and `Comparable<T>` differ?

`Comparable<T>` describes a **natural ordering** defined by the data type itself:

```java
class Version implements Comparable<Version> {
    private final int number;

    Version(int number) {
        this.number = number;
    }

    @Override
    public int compareTo(Version other) {
        return Integer.compare(number, other.number);
    }
}
```

The class snippet above is valid but has no `main`.

`Comparator<T>` is a **comparison rule external to the type**, which can vary by context:

```java
Comparator<Version> descending = (a, b) ->
        b.compareTo(a);
```

Key differences:

| `Comparable<T>` | `Comparator<T>` |
|---|---|
| The type usually implements `compareTo` itself | Can be defined outside the class |
| One natural ordering chosen by the class | Multiple different orderings can exist |
| `Collections.sort(list)`/`sorted()` without a comparator rely on it | `sort(comparator)`/`sorted(comparator)` use the passed comparator |
| Useful when the type itself has a clear natural order | Useful when business requirements change or multiple criteria exist |

When a record has multiple reasonable ways to sort (by score, name, age…), one or more `Comparator<Student>` instances are usually clearer than trying to cram everything into `compareTo`.

## 4. Lambdas and method references with `Comparator<T>`

Because `Comparator<T>` is a functional interface, we can create a comparator from a lambda:

```java
Comparator<String> byLength = (left, right) ->
        Integer.compare(left.length(), right.length());
```

Or use a static factory method with a **method reference**:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
```

`String::length` represents a function taking a `String` and returning an `int`; it matches `ToIntFunction<? super String>` required by `comparingInt`.

Semantically, both comparators compare strings by ascending length. They **do not automatically add a lexicographical tie-breaker**; two strings of equal length yield `0`.

To add a secondary order:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder());
```

This is an example of using a lambda/method reference **and chaining criteria**; the compiler infers the involved generic types from the target type `Comparator<String>`.

When the compiler has trouble inferring types from a long method chain, you can specify the type on a variable, or use an **explicit type witness** such as `Comparator.<Student>comparingInt(Student::score)`.

## 5. Complete example: descending score, ascending name, ascending age

Create the file **`StudentComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class StudentComparatorDemo {

    record Student(String name, int score, int age) {
    }

    public static void main(String[] args) {
        List<Student> students = new ArrayList<>(List.of(
                new Student("Binh", 90, 22),
                new Student("An", 90, 21),
                new Student("Chi", 80, 20),
                new Student("An", 90, 19)
        ));

        Comparator<Student> byScoreNameAge =
                Comparator.<Student>comparingInt(Student::score)
                        .reversed()
                        .thenComparing(Student::name)
                        .thenComparingInt(Student::age);

        students.sort(byScoreNameAge);

        for (Student s : students) {
            System.out.println(
                    s.name() + "|" + s.score() + "|" + s.age());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StudentComparatorDemo.java
java StudentComparatorDemo
```

Stdout:

```text
An|90|19
An|90|21
Binh|90|22
Chi|80|20
```

Analysis:

1. `Comparator.<Student>comparingInt(Student::score)` creates a `Comparator<Student>` and extracts the score using a `Student -> int` function.
2. `.reversed()` reverses the order of **the score comparator just created**, putting `90` before `80`.
3. `.thenComparing(Student::name)` compares names only when scores are considered equal. Here `"An"` comes before `"Binh"` by `String` natural order.
4. `.thenComparingInt(Student::age)` runs only when both score **and** name are equal. `"An"` aged `19` comes before `"An"` aged `21`.
5. `students.sort(...)` mutates the element order of a modifiable list.

If you want **descending name** instead of ascending, you need a separate comparator for name in the `thenComparing` step, rather than reversing the entire comparator.

## 6. The short-circuit mechanism of `thenComparing`

`thenComparing(other)` creates a composite comparator. The logical idea is:

```java
int first = primary.compare(a, b);
if (first != 0) {
    return first;
}
return secondary.compare(a, b);
```

This is an **illustrative model**, not the bytecode or the sole implementation in the JDK library.

Key points:

- When the primary criterion already distinguishes two objects, the secondary criterion **does not need** to be called.
- Only when the primary comparator returns `0` does the secondary comparator decide.
- Multiple levels can be chained. Each subsequent level matters only when all preceding levels compare equal.

For a three-level chain, you can visualize it as:

```text
Compare score → different? use that result
              → equal → compare name → different? use that result
                                     → equal → compare age
```

This helps both logical structure and avoiding unnecessary secondary key computations. However, do not put side effects inside comparators or key extractors: sorting algorithms can invoke a comparator multiple times and in non-trivial orders.

## 7. `comparing`, `comparingInt`, `comparingLong`, `comparingDouble`

Java provides several ways to build a comparator from a **sort key**.

### `Comparator.comparing(Function)`

When the key is a type with a natural order (*Comparable*), such as `String`, `LocalDate`, `BigDecimal`:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

The compiler knows `Student::name` returns `String`, and `String` has a natural order. This is an ascending-by-name comparator.

### `Comparator.comparingInt(ToIntFunction)`

When the key is `int`:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

`comparingInt` uses `ToIntFunction<? super T>` and compares `int` values with `Integer.compare` semantics, without requiring wrapper key creation in the API contract.

### Other primitive variants

```java
Comparator<Order> byTimestamp =
        Comparator.comparingLong(Order::timestamp);

Comparator<Order> byAmount =
        Comparator.comparingDouble(Order::amount);
```

These are **illustrative** snippets, assuming an `Order` class with `timestamp(): long` and `amount(): double` accessors.

Primitive-specific variants are especially useful when the key is inherently primitive, clarifying intent and avoiding wrapping keys solely for comparison.

### When do you need the `comparing(extractor, keyComparator)` overload?

If the key has no natural order, or you need a different rule, pass a comparator for **the key type**:

```java
Comparator<Student> byNameIgnoreCase =
        Comparator.comparing(
                Student::name,
                String.CASE_INSENSITIVE_ORDER);
```

In cases where name might be `null`, the key comparator also needs to handle `null`; a later section shows an example.

## 8. Generic signatures and the meaning of `T` and `U`

Much of the power of the `Comparator` API lies in its generic type parameters. Representative signatures (abridged from the Java API) are:

```java
public interface Comparator<T> {

    int compare(T first, T second);

    Comparator<T> thenComparing(
            Comparator<? super T> other);

    <U extends Comparable<? super U>>
    Comparator<T> thenComparing(
            Function<? super T, ? extends U> keyExtractor);

    <U> Comparator<T> thenComparing(
            Function<? super T, ? extends U> keyExtractor,
            Comparator<? super U> keyComparator);
}
```

These are **abridged signatures for learning**, not an interface you can copy verbatim to replace `java.util.Comparator`.

Distinguish the two type parameters:

- `T`: the type of object **being sorted**, e.g., `Student`.
- `U`: the type of **extracted key**, e.g., `String`, `LocalDate`, `BigDecimal`.

Therefore:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

has compared objects of type `Student`, while the `name()` key is `String`. The two types do not have to be the same.

In the `comparing` overload without a key comparator, the key `U` must implement `Comparable<? super U>` to provide natural ordering. When `U` lacks a natural order, use the overload taking `Comparator<? super U>`.

### `? super T` preserves flexibility

A `Comparator<Object>` can compare two values using a general rule because it accepts any `Student`, which is an `Object`. Thus sorting APIs use `Comparator<? super T>` to allow comparing with a comparator for `T` itself or an appropriate **supertype**.

Similarly, `Function<? super T, ? extends U>` accepts a key extractor that can read `T` or a supertype, and produces a value compatible with `U`.

This is an application of the rule commonly called **PECS**: consumers take `? super`, producers return `? extends`. These are not arbitrary wildcards; they describe the direction of data flowing through functional interfaces.

## 9. Why are explicit type witnesses needed in some call chains?

With the expression:

```java
Comparator.comparingInt(Student::score)
        .reversed()
        .thenComparing(Student::name)
```

the compiler sometimes lacks enough early target-type information to infer `Student` accurately in a method chain, especially when an intermediate method like `.reversed()` forces return-type checking before the whole chain finishes.

A reliable approach is to place the generic argument explicitly on the **factory method**:

```java
Comparator<Student> order =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
```

`<Student>` right after `Comparator.` is an **explicit method type argument** for `comparingInt`, not a cast and not creating an extra runtime class.

Another approach is extracting the initial comparator:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);

Comparator<Student> order =
        byScore.reversed().thenComparing(Student::name);
```

When reading code, **putting the type on an intermediate variable** also helps both the compiler and maintainers clearly see that the key applies to `Student`, not an unknown `Object`.

### With `Comparator.comparing`, there are two type parameters

The general `comparing` signature has two types: object `T` and key `U`. If a full type witness is needed:

```java
Comparator<Student> byName =
        Comparator.<Student, String>comparing(Student::name);
```

In simple code, normal target typing is sufficient; do not overuse explicit type arguments everywhere.

## 10. What exact scope does `reversed()` reverse?

`reversed()` returns a comparator with the reverse order of the receiving comparator.

Pitfall: calling `.reversed()` **after** chaining multiple criteria reverses **the entire chain**, not just the most recent criterion.

Consider:

```java
Comparator<Student> bothAsc =
        Comparator.comparingInt(Student::score)
                .thenComparing(Student::name);

Comparator<Student> bothDesc = bothAsc.reversed();
```

`bothDesc` prioritizes **descending score**, and if scores tie, **descending name**.

Conversely, if you want descending score **but ascending name**:

```java
Comparator<Student> scoreDescNameAsc =
        Comparator.<Student>comparingInt(Student::score)
                .reversed()
                .thenComparing(Student::name);
```

Place `reversed()` **before** `thenComparing(...)`.

### Example comparing three outcomes

Create the file **`ReversedScopeDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ReversedScopeDemo {

    record Item(String label, int quantity) {
    }

    static String render(List<Item> items, Comparator<Item> order) {
        return items.stream()
                .sorted(order)
                .map(i -> i.label() + ":" + i.quantity())
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("B", 2),
                new Item("A", 2),
                new Item("C", 1));

        Comparator<Item> ascending =
                Comparator.<Item>comparingInt(Item::quantity)
                        .thenComparing(Item::label);

        Comparator<Item> reversedAll = ascending.reversed();

        Comparator<Item> quantityDescLabelAsc =
                Comparator.<Item>comparingInt(Item::quantity)
                        .reversed()
                        .thenComparing(Item::label);

        System.out.println(render(items, ascending));
        System.out.println(render(items, reversedAll));
        System.out.println(render(items, quantityDescLabelAsc));
    }
}
```

Run:

```bash
javac ReversedScopeDemo.java
java ReversedScopeDemo
```

Stdout:

```text
C:1, A:2, B:2
B:2, A:2, C:1
A:2, B:2, C:1
```

The last line is the common requirement: **descending quantity**, **ascending label**. The middle line proves that placing `.reversed()` at the end reverses the secondary criterion as well.

## 11. Reversing only a secondary criterion

If you want **ascending score, descending name**, you do not reverse the comparator after chaining everything. Instead, build a reversed name comparator and pass it to `thenComparing`:

```java
Comparator<Student> scoreAscNameDesc =
        Comparator.<Student>comparingInt(Student::score)
                .thenComparing(
                        Comparator.comparing(
                                Student::name,
                                Comparator.reverseOrder()));
```

In this example, `Comparator.reverseOrder()` provides a comparator for `String` keys in reverse natural order. This is an illustrative snippet using `Student` as previously defined.

A more direct way to express it:

```java
Comparator<Student> byNameDescending =
        Comparator.comparing(
                Student::name,
                Comparator.reverseOrder());

Comparator<Student> scoreAscNameDesc =
        Comparator.comparingInt(Student::score)
                .thenComparing(byNameDescending);
```

When there are multiple alternating ascending/descending directions, **creating a separate comparator per key** or extracting named variables is usually easier to read than a long chain with multiple `.reversed()` calls.

## 12. `thenComparing` and primitive specializations

The API has multiple overloads for chaining criteria:

```java
primary.thenComparing(secondaryComparator);
primary.thenComparing(keyExtractor);
primary.thenComparing(keyExtractor, keyComparator);
primary.thenComparingInt(intKeyExtractor);
primary.thenComparingLong(longKeyExtractor);
primary.thenComparingDouble(doubleKeyExtractor);
```

- `thenComparing(Comparator<? super T>)`: accepts a complete comparator for the same object type `T`.
- `thenComparing(Function...)`: extracts a key with natural order and compares that key.
- `thenComparing(Function..., Comparator...)`: extracts a key and uses a dedicated comparator for the key.
- `thenComparingInt/Long/Double`: extracts primitive keys and compares them accordingly.

Example:

```java
Comparator<Student> byNameThenScore =
        Comparator.comparing(Student::name)
                .thenComparingInt(Student::score);
```

If `Student::score` returns `int`, `thenComparingInt` expresses the key type accurately. If data has `double` with `NaN` values, the comparator uses `Double.compare` with Java's consistent rules; never subtract and cast to `int`.

## 13. Null: distinguishing null **objects** from null **keys**

A common mistake is:

```java
Comparator<Student> byName =
        Comparator.comparing(Student::name);
```

If `name()` can return `null`, `String`'s natural order does not handle `null`; invoking the comparator can throw `NullPointerException`.

There are two distinct situations:

1. **The Student object is non-null, but `name` is null**: wrap **the key comparator** with `Comparator.nullsFirst` or `nullsLast`.
2. **The Student object itself can be null in the list**: wrap **the entire Student comparator** with `Comparator.nullsFirst` or `nullsLast`.

### Null in the key

```java
Comparator<Student> byName =
        Comparator.comparing(
                Student::name,
                Comparator.nullsLast(
                        Comparator.naturalOrder()));
```

This expression places `null` **in the `name` value** after non-null names. It does not automatically protect against `Student` itself being `null`, because the key extractor `Student::name` still has to be invoked on the object.

### Null in the object

```java
Comparator<Student> nullStudentsLast =
        Comparator.nullsLast(
                Comparator.comparingInt(Student::score));
```

Here, `null` at the **Student** level is sorted after non-null objects. If a non-null Student can also have a nullable key, the inner comparator still needs to handle that key separately.

**Do not use `nullsLast` at the key level and assume it automatically covers every null level.**

## 14. Runnable example: null in names and case-insensitive comparison

Create the file **`NullableKeyComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class NullableKeyComparatorDemo {

    record Person(String name, int id) {
    }

    public static void main(String[] args) {
        List<Person> people = new ArrayList<>(List.of(
                new Person("b", 3),
                new Person(null, 2),
                new Person("A", 2),
                new Person("a", 1)));

        Comparator<Person> byNameThenId =
                Comparator.comparing(
                        Person::name,
                        Comparator.nullsLast(
                                String.CASE_INSENSITIVE_ORDER))
                        .thenComparingInt(Person::id);

        people.sort(byNameThenId);

        for (Person p : people) {
            System.out.println(
                    String.valueOf(p.name()) + "#" + p.id());
        }
    }
}
```

Compile/run:

```bash
javac NullableKeyComparatorDemo.java
java NullableKeyComparatorDemo
```

Stdout:

```text
a#1
A#2
b#3
null#2
```

Explanation:

- `String.CASE_INSENSITIVE_ORDER` treats `"a"` and `"A"` as equal on the name key.
- `thenComparingInt(Person::id)` distinguishes those two records, placing id `1` before id `2`.
- `Comparator.nullsLast(...)` applies to **the `name` value**, so the person with `null` name comes last.
- All **Person objects** in the example are non-null. If the list contained an actual `null` element, you would need to wrap the outermost comparator with `Comparator.nullsLast(byNameThenId)`.

`String.CASE_INSENSITIVE_ORDER` does not mean a natural linguistic order for every locale; sorting Vietnamese linguistically is a different question—see the `Collator` section.

## 15. Null for an entire list element

Create the file **`NullElementComparatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullElementComparatorDemo {

    record Entry(int id) {
    }

    public static void main(String[] args) {
        List<Entry> entries = new ArrayList<>(
                Arrays.asList(new Entry(3), null, new Entry(1)));

        Comparator<Entry> byId =
                Comparator.comparingInt(Entry::id);

        entries.sort(Comparator.nullsLast(byId));

        for (Entry e : entries) {
            System.out.println(e == null ? "null" : e.id());
        }
    }
}
```

Run:

```bash
javac NullElementComparatorDemo.java
java NullElementComparatorDemo
```

Stdout:

```text
1
3
null
```

`Arrays.asList` is used here to create an input **containing `null`**, then copied into an `ArrayList`. Do not use `List.of(new Entry(3), null, ...)` because `List.of` rejects `null`.

`Comparator.nullsLast(byId)` checks at the object level before invoking `byId`, so `null` objects are placed after non-null objects without calling the accessor on `null`.

## 16. `List.sort`, `Collections.sort`, and `Stream.sorted`

Multiple APIs share `Comparator<T>` but **differ in how they return results and affect the input**.

### `List.sort(comparator)`

```java
List<Student> mutable = new ArrayList<>(source);
mutable.sort(order);
```

`List.sort` sorts **the receiving list itself**. If the list does not support element modification, the operation can throw `UnsupportedOperationException`.

### `Collections.sort(list, comparator)`

```java
Collections.sort(mutable, order);
```

A utility for sorting a list with a comparator; in modern Java, it delegates to the corresponding list's sort contract. There is no need to choose `Collections.sort` just because the comparator is generic.

### `Stream.sorted(comparator)`

```java
List<Student> sorted =
        source.stream().sorted(order).toList();
```

Creates a pipeline and collects the result into a new list. `Stream.toList()` in Java 17 returns an **unmodifiable** list; it is not a list to which you can freely add elements.

Sorting *stability* also matters:

- `List.sort` is specified to be **stable**: elements with comparator result `0` preserve their relative order.
- `Stream.sorted` is guaranteed stable for **ordered streams**; for **unordered streams**, there is no such guarantee.
- In all cases, stability is no substitute for defining tie-breakers that truly matter to the business domain.

## 17. Runnable example: in-place sort and sorted stream

Create the file **`SortApisDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortApisDemo {

    record Product(String code, int price) {
    }

    static String codes(List<Product> products) {
        return products.stream()
                .map(Product::code)
                .toList()
                .toString();
    }

    public static void main(String[] args) {
        List<Product> original = List.of(
                new Product("B", 200),
                new Product("A", 100),
                new Product("C", 200));

        Comparator<Product> byPriceThenCode =
                Comparator.<Product>comparingInt(Product::price)
                        .thenComparing(Product::code);

        List<Product> mutable = new ArrayList<>(original);
        mutable.sort(byPriceThenCode);

        List<Product> fromStream = original.stream()
                .sorted(byPriceThenCode)
                .toList();

        System.out.println(codes(original));
        System.out.println(codes(mutable));
        System.out.println(codes(fromStream));
    }
}
```

Commands:

```bash
javac SortApisDemo.java
java SortApisDemo
```

Stdout:

```text
[B, A, C]
[A, B, C]
[A, B, C]
```

`original` retains its order in the example because the stream pipeline only **reads** the source and does not call `sort` on `original` itself. `mutable` is a modifiable `ArrayList` copy sorted in place.

`fromStream` is the result list ordered by the comparator, but does not allow adding elements via `add` in Java 17. If you need further modification, create `new ArrayList<>(fromStream)`.

## 18. Common bug: using subtraction as a numeric comparator

Many snippets write:

```java
Comparator<Integer> wrong = (a, b) -> a - b;
```

Although concise, it is **unsafe against integer overflow**. Subtraction can wrap around in Java integer arithmetic, producing the wrong sign and violating the comparator contract.

Use instead:

```java
Comparator<Integer> safe = Integer::compare;
```

Or when comparing an object's key:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

### Overflow demonstration example

Create the file **`ComparatorOverflowDemo.java`**:

```java
public class ComparatorOverflowDemo {
    public static void main(String[] args) {
        int small = Integer.MIN_VALUE;
        int large = Integer.MAX_VALUE;

        System.out.println(small - large);
        System.out.println(Integer.compare(small, large));
    }
}
```

Compile/run:

```bash
javac ComparatorOverflowDemo.java
java ComparatorOverflowDemo
```

Stdout:

```text
1
-1
```

`Integer.MIN_VALUE - Integer.MAX_VALUE` overflows and produces `1`, whereas the true order has the smaller number before the larger number. `Integer.compare` returns a negative value according to contract.

**Never use `a.score() - b.score()` as a comparator** just because small test data has not triggered overflow yet. The `comparingInt/Long/Double` factories avoid this bug class.

## 19. `Comparator` and `TreeSet`/`TreeMap`: comparing as 0 means “same ordering key”

With `List.sort`, two elements whose comparator result is `0` can still coexist in the list. However, **sorted set/map** structures use the comparator to determine **both ordering and key equivalence under comparison**.

For example, a `TreeSet<Person>` comparing only by `age` treats two people of the same age as **equivalent to the set** even when their names/ids differ. Consequently, one element may not be added.

Create the file **`TreeSetComparatorDemo.java`**:

```java
import java.util.Comparator;
import java.util.TreeSet;

public class TreeSetComparatorDemo {

    record Person(String name, int age) {
    }

    public static void main(String[] args) {
        TreeSet<Person> byAge = new TreeSet<>(
                Comparator.comparingInt(Person::age));

        byAge.add(new Person("An", 20));
        byAge.add(new Person("Binh", 20));

        System.out.println(byAge.size());

        TreeSet<Person> byAgeThenName = new TreeSet<>(
                Comparator.comparingInt(Person::age)
                        .thenComparing(Person::name));

        byAgeThenName.add(new Person("An", 20));
        byAgeThenName.add(new Person("Binh", 20));

        System.out.println(byAgeThenName.size());
    }
}
```

Run:

```bash
javac TreeSetComparatorDemo.java
java TreeSetComparatorDemo
```

Stdout:

```text
1
2
```

Why?

- The age-only comparator returns `0` for two people both aged `20`, so `TreeSet` treats the second element as a duplicate in the ordering relation.
- The comparator chaining name distinguishes `"An"` and `"Binh"`, thus keeping both records.

### Must a `Comparator` be consistent with `equals`?

A comparator can work even if not consistent with `equals`, but using it in `TreeSet`/`TreeMap` can produce behavior that diverges from `Set`/`Map` contract expectations based on `equals`. For data with business identity, consider adding a **unique tie-breaker** such as an id.

Do not automatically chain `hashCode()` to distinguish objects: hashes can collide and are not stable identifying keys.

## 20. Zero comparison results and deterministic tie-breakers

A comparator sorting by **score**:

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
```

treats all students with the same score as equivalent in order. This is completely valid if the requirement is only to sort by score. However, if the result must have a completely deterministic order independent of input order, additional criteria must be specified.

Example with a record having a unique id:

```java
record Employee(long id, String name, int score) {
}

Comparator<Employee> order =
        Comparator.<Employee>comparingInt(Employee::score)
                .reversed()
                .thenComparing(Employee::name)
                .thenComparingLong(Employee::id);
```

This is an illustrative snippet that must be placed in an appropriate class/method with `Comparator` imported.

If two objects share the same score and name but have different ids, the id criterion distinguishes them. This is helpful for reports, pagination, or multi-source data where you do not want results depending on arbitrary input order.

**However**, if id can also duplicate, the comparator can still return `0`. To guarantee a total order matching business rules, ensure the final key set truly distinguishes objects that must be distinguished.

## 21. Key extractors can compute values, but should be pure

`Comparator.comparing` does not require the key extractor to return just a field. It can be a computing function:

```java
record Ticket(String category, int basePrice, int fee) {
}

Comparator<Ticket> byTotal =
        Comparator.comparingInt(
                t -> t.basePrice() + t.fee());
```

The snippet above assumes values are small enough that `int` addition does not overflow. If monetary amounts can be large, use `long`, `BigDecimal`, or a currency type per application design.

Good principles:

- Key extractors should be **deterministic** for the same object while data is unchanged.
- Avoid mutating state or side effects inside extractors/comparators.
- Do not make network calls, read current time, or generate random numbers during comparison.
- If computing a key is expensive, consider **precomputing and storing keys** or using a decorate-sort-undecorate pattern; sorting algorithms may call the comparator many times.
- When a compared field is mutable, avoid modifying it while a sorted set/map holds the object as a key. Internal ordering may become inconsistent.

A chained comparator is only valid when every component comparator satisfies the comparison contract.

## 22. `Comparator.naturalOrder`, `reverseOrder`, and `reversed`

Three operations that are easily confused:

- `Comparator.naturalOrder()`: creates a comparator using the natural ordering of `Comparable` values.
- `Comparator.reverseOrder()`: creates a comparator using the reverse of natural ordering.
- `someComparator.reversed()`: reverses **an existing comparator**.

Example:

```java
Comparator<String> normal = Comparator.naturalOrder();
Comparator<String> reverse = Comparator.reverseOrder();

Comparator<String> lengthDesc =
        Comparator.comparingInt(String::length)
                .reversed();
```

The first two comparators compare strings using `String.compareTo`; the last compares by **descending length** rather than alphabetically.

An advanced point: the generic signature of `naturalOrder()` requires `T` to support `Comparable<? super T>`. You cannot use `naturalOrder()` directly on a class lacking a natural order, such as a custom record that does not implement `Comparable`.

To sort such objects, pass a dedicated comparator via `sorted(comparator)` or `List.sort(comparator)`.

## 23. Distinguishing `Comparator<? super T>` from `Comparator<T>`

A generic helper should accept any comparator capable of comparing objects of type `T`:

```java
static <T> void sortInPlace(
        java.util.List<T> values,
        java.util.Comparator<? super T> comparator) {
    values.sort(comparator);
}
```

This is a valid method when placed inside a class.

`Comparator<? super T>` allows:

- `Comparator<T>`: a direct comparator for T.
- `Comparator<Object>`: a supertype comparator usable to compare T if it genuinely implements an appropriate contract.
- Comparators of other superclasses/interfaces where generic compatibility permits.

This flexible declaration does not mean Java treats `Comparator<Object>` as a sensible business ordering. A comparator that merely compares `toString()` on any object, for example, may not be the ordering you actually want.

Do not cast `Comparator<Object>` to `Comparator<Student>` to bypass the compiler if the API already accepts `? super T`: the wildcard type accurately describes the object-consuming direction.

## 24. Generic utility: sorted copy for any Collection

Create the file **`GenericSortedCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

public class GenericSortedCopyDemo {

    static <T> List<T> sortedCopy(
            Collection<? extends T> source,
            Comparator<? super T> order) {

        List<T> copy = new ArrayList<>(source);
        copy.sort(order);
        return copy;
    }

    public static void main(String[] args) {
        List<String> words = sortedCopy(
                List.of("zzz", "a", "bb"),
                Comparator.comparingInt(String::length));

        List<Integer> numbers = sortedCopy(
                List.of(5, 1, 3),
                Comparator.reverseOrder());

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Compile/run:

```bash
javac GenericSortedCopyDemo.java
java GenericSortedCopyDemo
```

Stdout:

```text
[a, bb, zzz]
[5, 3, 1]
```

Signature explanation:

- `Collection<? extends T> source`: a source that can supply elements compatible with T.
- `Comparator<? super T> order`: a comparator that can **accept** T for comparison.
- `new ArrayList<>(source)`: creates a separate list so the original collection is not sorted in place.
- Returns `List<T>`: the caller retains a clear static type without using a raw `List`.

This is a small example combining **Generics + Lambdas/Method References + Comparator + PECS** in a clean API.

## 25. Vietnamese sorting and locale: natural order is not always right for business logic

`String.compareTo` compares according to the order defined for `String` in Java, not the Vietnamese alphabetical sequence users expect. If the data consists of Vietnamese personal or place names, linguistic sorting usually requires a locale-appropriate **collator**.

Illustrative example:

```java
java.text.Collator collator = java.text.Collator.getInstance(
        java.util.Locale.forLanguageTag("vi-VN"));

Comparator<String> vietnameseOrder =
        (a, b) -> collator.compare(a, b);
```

Place the snippet above inside a method and import `java.util.Comparator` if compiling. `Collator.compare` provides a locale-based text comparison rule. You can chain it with a tie-breaker:

```java
Comparator<String> order =
        vietnameseOrder.thenComparing(
                Comparator.naturalOrder());
```

This is an example of a **custom key comparator**. Do not assume one specific Unicode sort result across every JDK/locale provider without defining test requirements. Systems requiring exact business ordering must verify against representative Vietnamese datasets, accent/case policies, and the runtime environment.

For concurrent code, do not share and mutate a mutable `Collator` instance across threads without an appropriate synchronization strategy.

## 26. Common mistakes when chaining multiple criteria

**Mistake 1 — Using subtraction `a.score() - b.score()` as a comparator.** Risks overflow and wrong sign. Use `comparingInt` or `Integer.compare`.

**Mistake 2 — Putting `.reversed()` at the end when only intending to reverse the primary criterion.** It reverses **the entire combined chain**. For descending score / ascending name, reverse the score comparator before `thenComparing`.

**Mistake 3 — Forgetting that `thenComparing` runs only when the preceding criterion returns 0.** If the primary comparator always returns a non-zero value for objects that should tie, the secondary criterion is never evaluated.

**Mistake 4 — Assuming `comparing(Student::name)` handles null automatically.** It does not. Add `nullsFirst`/`nullsLast` at the proper key or object level.

**Mistake 5 — Confusing `nullsLast` on a key with `nullsLast` on the element itself.** `Comparator.comparing(Person::name, nullsLast(...))` still fails on a null `Person`; wrap the outer comparator as well.

**Mistake 6 — Thinking `List.sort` creates a new list.** It mutates the receiving list. For a copy, create a new `ArrayList` or use a stream and collect.

**Mistake 7 — Calling `sort` on `List.of(...)`.** Those lists are unmodifiable; copy before sorting.

**Mistake 8 — Assuming `Stream.sorted` mutates the source.** It creates a stream stage; the source list is not sorted in place merely because a pipeline uses `sorted`.

**Mistake 9 — Comparing by one key in a `TreeSet` while expecting all distinct objects to be kept.** In `TreeSet`, `compare == 0` makes objects equivalent in ordering; add tie-breakers if they must be kept distinct.

**Mistake 10 — Using an inconsistent comparator or one depending on mutable state.** This can break transitivity/ordering contracts. Avoid side effects and unmanaged mutable keys.

**Mistake 11 — Using `Comparator.comparing` on a key that does not implement `Comparable` without providing a key comparator.** You need the `comparing(extractor, keyComparator)` overload.

**Mistake 12 — Thinking `Comparator<T>` must compare fields that are also of type T.** No. A key extractor can return a different `U`, such as `String` or `LocalDate`.

**Mistake 13 — Using raw `Comparator` to work around type-inference errors.** That loses generic checking and can cause `ClassCastException`; use target typing, explicit witnesses, or intermediate variables.

**Mistake 14 — Assuming natural string ordering equals Vietnamese ordering.** When locale requirements apply, use `Collator` or a tested custom rule.

**Mistake 15 — Relying on stable sort instead of declaring tie-breakers.** Stable sort preserves input order among elements comparing equal, but does not establish a total order independent of input.

**Mistake 16 — Failing to distinguish `Comparator.reverseOrder()` from `existingComparator.reversed()`.** The first is reversed natural ordering; the second reverses any comparator, including multi-level ones.

## 27. Self-check exercises with answers

### Question 1 — Sign of `compare`

Is `compare(a,b)` returning `-7` valid?

**Answer:** Yes, if consistent with the comparator contract. Any negative value indicates `a` precedes `b`; it need not be `-1`.

### Question 2 — Reversing only the score criterion

For descending score and ascending name in `Comparator<Student>`, where do you place `.reversed()`?

**Answer:** Right after the score comparator, **before** `.thenComparing(Student::name)`.

### Question 3 — Reversing the whole chain

With `byScore.thenComparing(byName).reversed()`, is the name criterion's order also reversed?

**Answer:** Yes; `.reversed()` reverses the composite comparator, meaning it reverses the entire ordering.

### Question 4 — Null in a key

A non-null `Person` has `name = null`. How should it be handled?

**Answer:** Pass `Comparator.nullsFirst(...)` or `.nullsLast(...)` as the comparator **for the `name` key** in `Comparator.comparing(Person::name, keyComparator)`.

### Question 5 — Null in an object

A list contains an actual `null` `Person` element. How should it be handled?

**Answer:** Wrap the entire `Person` comparator with `Comparator.nullsFirst(personComparator)` or `nullsLast(...)`.

### Question 6 — Key extractor

What type does `Comparator.comparingInt(Student::score)` use as the key?

**Answer:** Primitive `int`; the extractor signature does not require the `Integer` wrapper.

### Question 7 — `TreeSet`

Two `Student` instances with different ids but the same score are added to a `TreeSet` using a comparator **only by score**. Is the set guaranteed to keep both?

**Answer:** No. The comparator can return `0`, causing `TreeSet` to treat them as equivalent under the ordering.

### Question 8 — `List.of`

Can `List.of(3,1,2).sort(Comparator.naturalOrder())` sort in place?

**Answer:** No, per the unmodifiable list contract; create `new ArrayList<>(List.of(3,1,2))` and call `.sort(...)`.

### Question 9 — `Comparator<? super T>`

Why does `List<T>.sort` accept a comparator with `? super T`?

**Answer:** A Comparator is a consumer of T values; a comparator for an appropriate supertype can still compare T objects.

### Question 10 — Method reference

What role does `Student::name` play in `Comparator.comparing(Student::name)`?

**Answer:** Key extractor: it takes a `Student` and returns a `String` so the comparator can compare name keys.

### Question 11 — Overflow

Why should you not use `(a,b) -> a-b` over the full `int` range?

**Answer:** Subtraction can overflow and produce the wrong sign, violating the ordering. Use `Integer.compare`.

### Question 12 — Sort and stream

Does `list.stream().sorted(cmp).toList()` mutate `list`?

**Answer:** No. It creates an ordered result list; `list.sort(cmp)` is what mutates the receiving list.

### Question 13 — Compare by date then id

Given `record Event(LocalDate at, long id)`. How do you chain criteria?

```java
Comparator<Event> byDateThenId =
        Comparator.comparing(Event::at)
                .thenComparingLong(Event::id);
```

**Answer:** Valid when `Comparator`/`LocalDate` are imported and `at` is non-null. `LocalDate` has natural order; id is the fallback long key.

### Question 14 — Preserving stability

An ordered stream has two elements considered equal by the comparator (`compare == 0`). Is `sorted(cmp)` guaranteed to be stable?

**Answer:** Yes for **ordered streams**. For unordered streams, there is no equivalent guarantee.

## 28. Capstone practice: designing a production-ready business comparator

A product management application wants:

1. In-stock products (`inStock`) before out-of-stock ones.
2. Within each stock group, ascending price.
3. If prices tie, ascending name (case-insensitive).
4. If still tied, compare product code for a deterministic order.

Create the file **`BusinessOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class BusinessOrderDemo {

    record Product(
            String code,
            String name,
            int price,
            boolean inStock) {
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
                new Product("P3", "Beta", 120, true),
                new Product("P2", "Alpha", 100, false),
                new Product("P4", "alpha", 100, true),
                new Product("P1", "Alpha", 100, true)
        ));

        Comparator<Product> order =
                Comparator.<Product, Boolean>comparing(
                                Product::inStock,
                                Comparator.reverseOrder())
                        .thenComparingInt(Product::price)
                        .thenComparing(
                                Product::name,
                                String.CASE_INSENSITIVE_ORDER)
                        .thenComparing(Product::code);

        products.sort(order);

        for (Product p : products) {
            System.out.println(
                    p.code() + "|" + p.inStock()
                    + "|" + p.price() + "|" + p.name());
        }
    }
}
```

Compile/run:

```bash
javac BusinessOrderDemo.java
java BusinessOrderDemo
```

Stdout:

```text
P1|true|100|Alpha
P4|true|100|alpha
P3|true|120|Beta
P2|false|100|Alpha
```

Explanation:

- `Product::inStock` returns primitive `boolean`. In the `comparing` overload with key type `Boolean`, the compiler boxes to compare keys; `Comparator.reverseOrder()` puts `true` before `false` because `Boolean`'s natural order is `false < true`.
- `thenComparingInt(Product::price)` sorts prices from low to high within each stock group.
- `thenComparing(Product::name, String.CASE_INSENSITIVE_ORDER)` compares names case-insensitively.
- For `"Alpha"` and `"alpha"` with the same price and stock status, the name comparator returns `0`, so code `P1` comes before `P4`.
- No raw types, unchecked casts, or long branching `compare` methods are needed.

If product names can be `null`, you must replace the name comparator with `Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)` or another policy before using it on real data.

## 29. Practical workflow when building a comparator chain

When given a multi-key sorting requirement:

1. **Write down the priority order** of each criterion. E.g., status → score → name → id.
2. **Note ascending/descending direction and null policy** for each criterion.
3. **Choose the appropriate key extractor:** `comparingInt` for `int`, `comparingLong` for `long`, `comparing` for object keys with natural order.
4. **Use a custom key comparator** if custom ordering, case-insensitivity, locale, or null placement is needed.
5. **Place `.reversed()` in the exact scope**, or build per-criterion comparators when directions alternate.
6. **Chain `thenComparing` in exact priority order**. Later criteria are evaluated only when earlier ones tie.
7. **Add a strong enough tie-breaker** if the API needs deterministic result order or is used in `TreeSet`/`TreeMap`.
8. **Verify contract** on boundary values: `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `null`, duplicate keys, letter casing, and mutable keys.
9. **Choose the right API:** `List.sort` to mutate a list, `Stream.sorted` for a new result, `TreeSet`/`TreeMap` when ordering is part of the data structure.
10. **Write tests with concrete outputs**, not just testing an already-sorted list.
11. **Keep comparators pure**, avoiding side effects; if key extraction is expensive, consider caching/precomputation.
12. **Preserve full generic types** and use target typing/explicit type witnesses if the compiler cannot infer a method chain.

A proper comparator chain does more than sort a demo list—it maintains correct behavior when data scales and duplicate keys or boundary values appear.

## 30. Summary and references

**`Comparator<T>` is a generic functional interface defining how to compare two objects of type T.** It can be written using lambdas, method references, or factories such as `comparing`, `comparingInt`, `comparingLong`, and `comparingDouble`. When multiple criteria are needed, chain them with `thenComparing` and its key-extractor overloads.

Three particularly important points:

- **Priority order** is determined by the chaining order of comparators. A secondary key is used only when prior keys return `0`.
- **Sort direction** depends on where `.reversed()` is placed: calling it at the end reverses the whole comparator, whereas calling it right after the primary comparator reverses only the primary part before chaining.
- **Type safety and contract correctness** depend on generic signatures, null handling, avoiding overflow, and ensuring a valid comparator. Use `Comparator<? super T>` in appropriate generic APIs and remember `TreeSet`/`TreeMap` rely on `compare == 0` to determine key equivalence.

For Java 17+, expressing criteria is usually clearer when separating keys, using primitive comparators where appropriate, naming complex comparators, and writing tests with tie-breakers. There is no need to resort to raw types or unchecked casts.

Standard references:

- [Java SE 17 — `java.util.Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): `compare`, `comparing`, `thenComparing`, `reversed`, `nullsFirst/nullsLast`.
- [Java SE 17 — `java.util.List.sort`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): in-place list sorting and stability contract.
- [Java SE 17 — `java.util.stream.Stream.sorted`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator)): sorting a stream with a comparator.
- [Java SE 17 — `java.util.TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): comparator determining ordering and element equivalence in a sorted set.
- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): target typing of lambdas.
- [Java Language Specification §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): method references in functional interfaces.
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): generic type argument inference.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): parameterized types and type argument relationships.