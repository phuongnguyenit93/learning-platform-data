# Comparable and Comparator: Two Ways to Represent Comparison

When objects need to be sorted in Java, the first question is: **what is the natural order of this type, and are other orders needed depending on the situation?** Java provides two main mechanisms to answer this:

- `Comparable<T>` allows the data type itself to define its natural order through `compareTo`.
- `Comparator<T>` represents an independent comparison rule, making it possible to create multiple ways to sort the same data type.

Both mechanisms return a comparison result, but they differ in where the rule is placed, flexibility for change, and how multiple criteria are combined. Understanding them properly helps you sort lists, use the Collections API, and avoid bugs with ordered data structures.

## 1. The Problem to Solve

Suppose an application manages products. Each product has a name and a price. Sometimes we want to sort by name, other times by price ascending, or by price descending and then use the name to break ties between products with the same price.

If we write a separate sorting algorithm for each case, the code will be duplicated and hard to maintain. The Java library already provides sorting algorithms; we only need to supply the appropriate comparison rule.

`Comparable` is appropriate when a type has a sensible natural order, such as integers by value or strings in lexicographical order. `Comparator` is appropriate when the order depends on the needs where it is used, or when you cannot or do not want to modify the original data type.

## 2. Comparable and the compareTo Method

`Comparable<T>` resides in `java.lang`, so it does not need to be imported. A type implementing this interface must define:

~~~java
public int compareTo(T other)
~~~

The return value has the following meaning:

| Result | Meaning |
| --- | --- |
| Negative number | The current object comes before `other` |
| Zero | The two objects are equivalent according to the natural order |
| Positive number | The current object comes after `other` |

It is not necessary to return exactly `-1` or `1`. Any negative integer, zero, or positive integer can represent those three states. Callers should check the sign of the result rather than assuming the return value can only be -1, 0, or 1.

For example, a `Product` type can define its natural order by name:

~~~java
record Product(String name, int price) implements Comparable<Product> {
    @Override
    public int compareTo(Product other) {
        return this.name.compareTo(other.name);
    }
}
~~~

In this example, calling `a.compareTo(b)` compares the names of two products. APIs can use that natural order without receiving an additional comparison object. For custom types, choose a natural order that users of the type can predict and explain.

## 3. Comparator and External Comparison Rules

`Comparator<T>` resides in `java.util`. It provides the method:

~~~java
int compare(T left, T right)
~~~

The sign semantics are the same as `compareTo`: negative means `left` comes before `right`, 0 means equivalent according to that comparator, and positive means `left` comes after `right`.

Example of a comparator comparing products by price:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

This rule exists independently of the `Product` class. The same list can be sorted by name, price, creation date, or a custom criterion without modifying the `Product` definition. This is the main benefit of `Comparator` when an application needs multiple different orders.

A comparator is commonly passed to APIs such as `list.sort(comparator)`, `Collections.sort(list, comparator)`, or `stream.sorted(comparator)`. If the type already implements `Comparable`, APIs can also use the natural order when no comparator is passed.

## 4. Complete Runnable Java 17+ Example

The following program demonstrates both mechanisms. `Product` defines the natural order by name; the comparators add orders by ascending and descending price. When prices are equal, `thenComparing` uses the name as the next criterion.

~~~java
import java.util.Comparator;
import java.util.List;

record Product(String name, int price) implements Comparable<Product> {
    @Override
    public int compareTo(Product other) {
        return this.name.compareTo(other.name);
    }

    String label() {
        return name + ":" + price;
    }
}

public class ComparableComparatorDemo {
    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("Pen", 15),
            new Product("Notebook", 32),
            new Product("Pencil", 5),
            new Product("Marker", 15)
        );

        System.out.println("Original: " + labels(products));
        System.out.println("Natural order (name): "
            + labels(products.stream().sorted().toList()));

        Comparator<Product> byPriceThenName = Comparator
            .comparingInt(Product::price)
            .thenComparing(Product::name);
        System.out.println("By price ascending, then name: "
            + labels(products.stream().sorted(byPriceThenName).toList()));

        Comparator<Product> byPriceDescendingThenName = Comparator
            .comparingInt(Product::price).reversed()
            .thenComparing(Product::name);
        System.out.println("By price descending, then name: "
            + labels(products.stream().sorted(byPriceDescendingThenName).toList()));
    }

    private static List<String> labels(List<Product> products) {
        return products.stream().map(Product::label).toList();
    }
}
~~~

Save the program to the file `ComparableComparatorDemo.java`. The example uses a record and `Stream.toList()`, so Java 17 or later is required.

~~~text
javac ComparableComparatorDemo.java
java ComparableComparatorDemo
~~~

Stdout output:

~~~text
Original: [Pen:15, Notebook:32, Pencil:5, Marker:15]
Natural order (name): [Marker:15, Notebook:32, Pen:15, Pencil:5]
By price ascending, then name: [Pencil:5, Marker:15, Pen:15, Notebook:32]
By price descending, then name: [Notebook:32, Marker:15, Pen:15, Pencil:5]
~~~

The second line uses `sorted()` without arguments, so Java uses `Product`'s `Comparable` and sorts by name. The third line passes the ascending price comparator; the two products priced at 15 are tie-broken by name, so `Marker` comes before `Pen`. The last line reverses the price criterion while keeping names in ascending order when prices are equal.

`Stream.sorted()` produces a sorted stream and does not modify the source list. If you need to sort a mutable list directly, use `products.sort(comparator)`; this method changes the element order within the list itself.

## 5. Combining Multiple Criteria with Comparator

`Comparator` provides utility methods for building readable rules instead of writing lengthy comparison logic manually:

- `Comparator.comparing(Product::name)` compares by the extracted key; the key must have an appropriate natural order.
- `Comparator.comparingInt(Product::price)` is specialized for `int` keys; similarly, there are `comparingLong` and `comparingDouble`.
- `thenComparing(...)` adds a secondary criterion when the preceding criterion returns 0.
- `reversed()` creates a comparator that reverses the order of the current comparator.
- `Comparator.nullsFirst(comparator)` and `nullsLast(comparator)` determine the placement of `null` values.
- `Comparator.comparing(keyExtractor, keyComparator)` lets you specify how to compare the extracted key.

For example, sorting by department and then by full name can be expressed by chaining `thenComparing`. The comparator uses the next criterion only when the preceding criteria consider the two objects equal.

Pay attention to the placement of `reversed()`. The expression `comparingInt(Product::price).reversed().thenComparing(Product::name)` means price descending, then name ascending. If you reverse the entire comparator after already chaining the name, the name order within a same-price group will also be reversed.

For numeric keys, avoid writing `a.price() - b.price()` as the comparison result. Integer subtraction can overflow and produce the wrong sign. Use `Integer.compare(a.price(), b.price())` or `Comparator.comparingInt(...)` to express your intent more safely.

## 6. The Comparison Contract

A comparison must not only produce the desired order for a single pair of elements; it must be consistent across the entire dataset. Sorting algorithms and ordered data structures rely on these rules.

For both `compareTo` and `Comparator.compare`, ensure these key properties:

1. **Sign symmetry:** if comparing `a` with `b` yields a negative result, comparing `b` with `a` must yield a positive result, and vice versa. If one direction is 0, the reverse direction must also be 0.
2. **Transitivity:** if `a` comes before `b` and `b` comes before `c`, then `a` must come before `c`.
3. **Consistency with a third element:** if `a` and `b` are considered equal by the comparison, comparing each of them with `c` must yield the same ordering relationship.
4. **Explicit null handling:** `Comparable` normally does not support calling `compareTo(null)` and will throw `NullPointerException`. A comparator may also not accept `null` unless constructed to handle this case.

For `Comparable`, the Java documentation strongly recommends that `compareTo` be consistent with `equals`, meaning `a.compareTo(b) == 0` if and only if `a.equals(b)` returns true. However, this is not required for every type; if the two concepts differ, you should document this clearly so users understand the implications.

With `Comparator`, consistency with `equals` is also often helpful, though not required. A comparator may intentionally treat two different objects as equivalent under a specific criterion, such as comparing only full names while ignoring identifiers.

## 7. Interaction with List, Stream, TreeSet, and TreeMap

The choice of comparator affects how APIs use ordering:

- `List.sort(comparator)` sorts a mutable list directly. `Collections.sort(list)` uses the natural order, while the overload accepting a comparator allows choosing a different order.
- `stream.sorted()` uses the natural order of the elements. `stream.sorted(comparator)` uses the provided comparator and returns a sorted stream.
- `Arrays.sort(array)` has overloads using the natural order or a comparator for reference arrays.
- `TreeSet` and `TreeMap` use the natural order or a comparator to organize elements/keys.

Special care is needed with `TreeSet` and `TreeMap`. In these structures, two elements or keys are considered to occupy the same position if the comparison returns 0, even though `equals` may return false. If a comparator compares only price, two products with different names but the same price may be treated as duplicates in a `TreeSet`, and one element will not be added as expected.

If you need to store objects with the same price as well, add a distinguishing criterion such as an identifier or name, as long as that criterion fits the data requirements. Before using a custom type as a key in an ordered structure, check the comparison contract and clearly decide what constitutes two equivalent keys.

## 8. Common Mistakes and How to Avoid Them

**Using subtraction to compare numbers.** Subtraction can cause integer overflow. Use `Integer.compare`, `Long.compare`, or `Comparator` factory methods.

**Trying to modify a library type to implement Comparable.** You cannot add `implements Comparable` to a source type you do not own. Provide a `Comparator` externally.

**Using an unreasonable natural order.** `Comparable` is a commitment of the type; if multiple orders are equally meaningful, you can choose one stable natural order and leave the remaining orders to comparators.

**Assuming compare returns -1, 0, or 1.** Check the sign of the result rather than checking for exact equality with -1 or 1.

**Ignoring the equal case.** If two products have the same price, a price comparator returns 0. If you need a more deterministic result, add `thenComparing` with a secondary criterion.

**Using an inconsistent Comparator.** A comparator that violates transitivity or changes its result depending on state can cause incorrect sorting or throw `IllegalArgumentException` when the algorithm detects a contract violation.

**Confusing sorting with modifying the source list.** `stream.sorted()` does not sort the original list in place; `List.sort()` does modify that list. Choose the API based on whether you need to preserve the original order.

## 9. Should You Choose Comparable or Comparator?

| Question | Appropriate Choice |
| --- | --- |
| Does the data type have a clear natural order? | Implement `Comparable<T>` |
| Need multiple ways to sort the same type? | Create separate `Comparator<T>` instances |
| Does the type come from a library and cannot be modified? | Use `Comparator<T>` |
| Want to combine multiple criteria concisely? | Use `comparing` and `thenComparing` |
| Need to reverse the order? | Use `reversed()` at the right criterion level |
| Using the type in `TreeSet` or `TreeMap`? | Check the meaning of a 0 comparison result and consistency with `equals` |

The two mechanisms complement each other. A type can implement `Comparable` for its natural order while also being used with various comparators across different screens or business workflows. There is no need to force every sorting requirement into a single `compareTo` method.

## 10. Key Takeaways

`Comparable` places the natural order inside the data type via `compareTo`. `Comparator` places the comparison rule externally via `compare`, allowing the same dataset to be sorted by multiple criteria. Both must obey the contract for sign and transitivity; when using multiple criteria, `thenComparing` helps express the order clearly. In particular, avoid subtraction that risks numeric overflow, handle `null` intentionally, and check the consequences of a 0 result when using ordered data structures.
