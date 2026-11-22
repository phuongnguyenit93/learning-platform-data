# comparing, comparingInt, and Key-Based Comparators

When sorting a list of products, we might want to sort by name, stock quantity, price, or rating. The object is still `Product`, but the **sort key** is extracted from a property or calculation on that object.

The `Comparator.comparing(...)`, `comparingInt(...)`, `comparingLong(...)`, and `comparingDouble(...)` methods help express this rule: specify how to extract the key, then use an appropriate rule to compare the keys. There is no need to repeat the entire object comparison logic every time the criterion changes.

In this article, a “key” is a value used for comparison, not automatically a primary key, unique identifier, or the key of a `Map`.

## 1. The Model: Extract the Key, Then Compare Keys

Suppose each product has an inventory stock quantity of type `int`:

~~~java
// Illustrative code snippet; Product is a type with a stock() method returning int.
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

When calling:

~~~java
// left and right are two non-null Product instances.
int result = byStock.compare(left, right);
~~~

We can visualize three steps:

1. Extract `left.stock()`.
2. Extract `right.stock()`.
3. Compare the two `int` values to decide the order of the two products.

A longer way to write this with the same comparison meaning in this case:

~~~java
Comparator<Product> byStock =
        (left, right) -> Integer.compare(left.stock(), right.stock());
~~~

The sign of the result carries the meaning:

| Result of `compare(left, right)` | Meaning according to the comparator |
| --- | --- |
| Negative | `left` comes before `right`. |
| Equal to `0` | Both objects are equivalent under the criteria currently considered by the comparator. |
| Positive | `left` comes after `right`. |

Do not test a comparator solely with `result == -1` or `result == 1`. The contract uses the sign; it does not require every comparator to return only the exact three values `-1, 0, 1`.

Creating a comparator does not automatically modify a list:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);

// No sorting operation has happened on the line above yet.
products.sort(byStock); // Only here is the modifiable list sorted.
~~~

This article uses APIs available since Java 8, and the complete example program runs on Java 17 or later. The variant signatures are cross-referenced with the [Java SE 17 Comparator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 2. comparing with the Natural Order of the Key

The single-parameter form accepts a key extraction function whose return type implements `Comparable`:

~~~java
static <T, U extends Comparable<? super U>>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor
)
~~~

This is an API signature for reference, not a method you need to implement yourself in your application.

- `T`: the type of object being sorted, such as `Product`.
- `U`: the type of the extracted key, such as `String`.
- `keyExtractor`: a function that takes an object and returns a key.
- The result is still `Comparator<T>`, not `Comparator<U>`.

Example:

~~~java
// Product.name() returns String.
Comparator<Product> byName = Comparator.comparing(Product::name);
~~~

`Product` does not need to implement `Comparable<Product>`. Only the `String` key in this form of `comparing` needs to have a natural ordering.

The method reference `Product::name` expresses how to extract a name from a product. In this context, it is equivalent to the lambda:

~~~java
Comparator<Product> byName =
        Comparator.comparing((Product product) -> product.name());
~~~

The comparator compares products by their name strings. It does not “sort the fields inside each Product”, rename anything, or create a list of names in place of the list of products.

### Common Object Key Types

You can extract `String`, `LocalDate`, `Instant`, `BigDecimal`, or another type with a suitable ordering. Simply picking an API is not enough: you must verify that the key's ordering matches your business requirements.

For example, the natural order of `String` does not automatically match Vietnamese linguistic collation. If you need to sort names according to locale-specific linguistic rules, you must specify an appropriate comparison rule rather than assuming `String.compareTo` solves every case.

## 3. comparing with a Custom Key Comparator

The two-parameter form cleanly separates how the key is extracted from how the key is compared:

~~~java
static <T, U>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor,
        Comparator<? super U> keyComparator
)
~~~

In this form, the key is not required to implement `Comparable` itself, because `keyComparator` already specifies how to compare it.

Example of case-insensitive name comparison:

~~~java
Comparator<Product> byNameIgnoringCase =
        Comparator.comparing(
                Product::name,
                String.CASE_INSENSITIVE_ORDER
        );
~~~

There are two comparators with two distinct roles:

- `String.CASE_INSENSITIVE_ORDER` compares **two String keys**.
- `byNameIgnoringCase` compares **two Product instances**, after extracting their names.

Do not pass a `Comparator<Product>` where a comparator for a `String` key is expected. The comparator type depends on what is being compared at each level.

### When the Key Type Has No Natural Order

Suppose a program has:

~~~java
// Illustrates declarations inside a class; requires import java.util.Comparator.
record Category(int rank, String label) {}
record Item(String code, Category category) {}

Comparator<Category> categoryOrder =
        Comparator.comparingInt(Category::rank)
                .thenComparing(Category::label);

Comparator<Item> itemOrder =
        Comparator.comparing(Item::category, categoryOrder);
~~~

`Category` does not declare `implements Comparable<Category>`. Therefore, the single-parameter `Comparator.comparing(Item::category)` has no basis for using a natural order on `Category`.

The two-parameter form solves the exact problem: extract `Category` from `Item`, then compare using `categoryOrder`. These examples assume that objects and keys are non-null; `null` handling is covered separately below.

## 4. comparingInt: int Key, Object Remains T

Signature:

~~~java
static <T> Comparator<T> comparingInt(
        ToIntFunction<? super T> keyExtractor
)
~~~

`ToIntFunction<T>` is a function that takes a `T` and returns a primitive `int` value. Compared to `Function<T, Integer>`, it does not need to represent the key as an `Integer` object.

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

Choose `comparingInt` when the natural key of the problem is an `int`, such as quantity, retry count, or string length.

A key can also be extracted via a calculation:

~~~java
Comparator<Product> byNameLength =
        Comparator.comparingInt(product -> product.name().length());
~~~

Here, products with shorter names come first. Two different names with the same length will be considered equivalent by this comparator unless a secondary tie-breaker is added.

### Is comparing with int Necessarily Wrong?

No. The following code compiles:

~~~java
Comparator<Product> boxed =
        Comparator.comparing(Product::stock);
~~~

Because `comparing` expects an object key, the `int` value can be autoboxed into an `Integer` and then compared using `Integer`'s natural order.

However, when the intent is clearly to compare primitive numbers, `comparingInt` expresses that more directly and avoids requiring boxing on the key comparison path. That said, you should not claim from this alone that every program will be faster by a fixed amount: actual cost still depends on the data, number of comparisons, JVM behavior, and other work done inside the key extractor.

More importantly, `comparingInt` does **not** turn `Comparator<Product>` into a comparator for `Integer`, nor does it change the data type stored in the list.

## 5. Variants for long and double

| Suitable key type | Comparator factory API | Key extractor type |
| --- | --- | --- |
| Object with natural order | `comparing(extractor)` | `Function<? super T, ? extends U>` |
| Object with custom comparison rule | `comparing(extractor, keyComparator)` | `Function` plus comparator for the key |
| `int` | `comparingInt(extractor)` | `ToIntFunction<? super T>` |
| `long` | `comparingLong(extractor)` | `ToLongFunction<? super T>` |
| `double` | `comparingDouble(extractor)` | `ToDoubleFunction<? super T>` |

Example:

~~~java
Comparator<Product> byPrice =
        Comparator.comparingLong(Product::priceInCents);

Comparator<Product> byRating =
        Comparator.comparingDouble(Product::rating);
~~~

Choose the API based on the key type and data semantics. Do not cast a `long` value to `int` just to use `comparingInt`; narrowing conversions can lose information and alter the ordering.

Similarly, do not arbitrarily convert data requiring exact integer precision from `long` to `double`. Just because a signature accepts a type conversion does not mean the conversion preserves the meaning of every value.

For money in the example program, `priceInCents` is a `long` value denominated in the smallest unit of the sample system. This is a data modeling choice for the example, not a mandatory rule that every financial application must use `long`.

`comparingDouble` performs numerical comparison according to Java's `double` comparison behavior. If the data domain includes `NaN`, infinity, or positive/negative zero, you must determine whether those values are valid for your business domain. Never write a custom comparator by subtracting two `double` values and casting to `int`: two distinct numbers can be truncated to `0`, not to mention special floating-point values.

There are no dedicated factory methods named `comparingBoolean`, `comparingFloat`, or `comparingShort` in the `Comparator` interface. For keys of other types, choose an appropriate mapping or comparator and state the ordering semantics clearly. For example, a `float` can be widened to `double` for comparison, whereas the priority ordering of a boolean state is usually best expressed explicitly according to business requirements.

## 6. Do Not Use Subtraction in Place of Numeric Comparison

An error-prone implementation:

~~~java
Comparator<Product> unsafe =
        (left, right) -> left.stock() - right.stock();
~~~

`int` subtraction can overflow. With:

~~~text
left.stock()  = Integer.MIN_VALUE
right.stock() = Integer.MAX_VALUE
~~~

In numerical value, the left side is smaller than the right side. However, `int` subtraction in Java produces `1`, causing the comparator to return a positive sign and claim the exact opposite.

Safe ways to write this criterion:

~~~java
Comparator<Product> byStock =
        Comparator.comparingInt(Product::stock);

// Or when you truly need to write a lambda:
Comparator<Product> byStockExplicit =
        (left, right) -> Integer.compare(left.stock(), right.stock());
~~~

With `long`, do not write this either:

~~~java
// Bad example: can overflow during subtraction or lose information when cast to int.
Comparator<Product> unsafePrice =
        (left, right) -> (int) (left.priceInCents() - right.priceInCents());
~~~

Use `comparingLong` or `Long.compare`. The goal is to produce the correct comparison sign, not to compute an arithmetic difference and hope the sign survives every transformation intact.

## 7. Adding Secondary Criteria with thenComparing

If you sort only by stock quantity, many products may share the same `stock`. When ties in stock should be broken by product code:

~~~java
Comparator<Product> byStockThenCode =
        Comparator.comparingInt(Product::stock)
                .thenComparing(Product::code);
~~~

Comparison process:

1. Compare `stock`.
2. If the result is non-zero, use that result.
3. Only when `stock` values are equal is `code` evaluated.

This is sequential comparison by criteria, not adding comparison results together or summing key values.

Correspondingly named variants allow chaining primitive keys:

~~~java
Comparator<Product> order =
        Comparator.comparing(Product::category)
                .thenComparingInt(Product::stock)
                .thenComparingLong(Product::priceInCents)
                .thenComparingDouble(Product::rating)
                .thenComparing(Product::code);
~~~

This example assumes `category` and `code` are non-null; it illustrates syntax rather than a mandatory sorting rule for a retail application.

You can also specify a custom rule for a secondary key:

~~~java
Comparator<Product> order =
        Comparator.comparingInt(Product::stock)
                .thenComparing(
                        Product::name,
                        String.CASE_INSENSITIVE_ORDER
                )
                .thenComparing(Product::code);
~~~

If two products are equal across all selected keys, the comparator returns `0`. Do not tack on an arbitrary criterion just to “force them to differ”; determine the true ordering requirement and equivalence definition for your data.

## 8. Descending Order: Where reversed Is Placed Determines What Gets Reversed

Descending by stock quantity, then ascending by price:

~~~java
Comparator<Product> stockDescPriceAsc =
        Comparator.comparingInt(Product::stock)
                .reversed()
                .thenComparingLong(Product::priceInCents)
                .thenComparing(Product::code);
~~~

Here, `reversed()` reverses only the stock comparator constructed before it. Criteria chained afterward remain in ascending order.

Conversely:

~~~java
Comparator<Product> allDesc =
        Comparator.comparingInt(Product::stock)
                .thenComparingLong(Product::priceInCents)
                .thenComparing(Product::code)
                .reversed();
~~~

The final line reverses the **entire composed chain** of comparators, including both price and code.

Read the chain from left to right according to the comparators formed at each step, rather than simply counting how many times `reversed` appears.

For object keys, you can reverse a single key individually using the two-parameter form:

~~~java
Comparator<Product> nameDescending =
        Comparator.comparing(Product::name, Comparator.reverseOrder());
~~~

This is the reverse of the name's natural order. It does not replace a locale-sensitive rule or a case-insensitive rule if business requirements call for those.

## 9. Null Elements and Null Keys Are Two Separate Issues

Consider a list that may contain:

- A non-null `Product` whose `product.category()` returns `null`.
- A `Product` element that is itself `null`.

These two cases fail at two different layers.

### Nullable Keys

To place uncategorized products at the end:

~~~java
Comparator<Product> byCategory =
        Comparator.comparing(
                Product::category,
                Comparator.nullsLast(Comparator.naturalOrder())
        ).thenComparing(Product::code);
~~~

The inner wrapped comparator is a `Comparator<String>` for the `category` key. It handles a `null` key.

This code does not yet handle a `Product` element that is `null`: attempting to invoke `Product::category` on that element will still fail.

### Nullable Elements as Well

Wrap the complete comparator on the outside:

~~~java
Comparator<Product> safe =
        Comparator.nullsLast(byCategory);
~~~

The outer layer handles a `null` `Product`. For non-null products, it delegates comparison to `byCategory`.

An easy structure to remember:

~~~text
Is the Product null?
    -> outer wrapping comparator

Product exists, but category is null?
    -> comparator for the category key
~~~

If `code` can also be `null`, the secondary criterion `thenComparing(Product::code)` needs its own `null` policy. A `null`-handling layer for `category` does not automatically cover other keys.

### Nested Key Extractors

With an expression such as:

~~~java
product -> product.category().label()
~~~

If `category()` returns `null`, the failure occurs right inside the key extractor, before the key comparator ever gets a chance to handle the return value.

Choose one of the following appropriate designs:

- Disallow missing `category` values and validate data upfront.
- Have the key extractor return `null` when the intermediate object is missing, then use a null-friendly key comparator.
- Compare the `Category` object directly using a comparator that handles `null`.

Do not substitute an empty string or an arbitrary number for `null` if doing so conflates “missing data” with valid data.

### Reversing Order Can Flip Null Placement

Reversing a comparator that placed `null` last will also reverse that relationship, moving `null` to the front.

If you want non-null keys in descending order while keeping `null` at the end, write:

~~~java
Comparator<Product> categoryDescendingNullLast =
        Comparator.comparing(
                Product::category,
                Comparator.nullsLast(Comparator.reverseOrder())
        );
~~~

This is another reason to be explicit about where each wrapper layer sits.

## 10. Generic Types, Lambdas, and Type Inference

Method references usually keep types clear:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

In some complex method chains, a lambda without an explicit parameter type can prevent the compiler from inferring `Product` where needed. You can supply type information in either of two ways:

~~~java
Comparator<Product> first =
        Comparator.comparingInt((Product product) -> product.stock())
                .reversed();

Comparator<Product> second =
        Comparator.<Product>comparingInt(product -> product.stock())
                .reversed();
~~~

Do not fix type inference errors by dropping to the raw type `Comparator` and casting. Doing so throws away the type checking that generics provide.

With the two-parameter form of `comparing`, remember that `T` is the element type and `U` is the key type. Both the key extractor and the key comparator must agree on `U`.

Using `var` does not mean Java can always guess the element type from an untyped lambda. When context is lacking, use a clearly typed method reference, an explicit lambda parameter type, or an explicit type witness.

## 11. Key Extractors Must Be Stable and Reasonably Cheap

Factory methods do not promise to call the key extractor only once per element across an entire sort. Sorting may compare the same element multiple times.

Therefore, avoid key extractors that:

- Make network calls or database queries.
- Read the current clock time to decide order.
- Mutate object properties each time they are called.
- Depend on changing global state.
- Generate random values.

If a key changes between comparisons, the comparator's consistency can be violated. Even if a key is stable, if it is expensive to compute, sorting time can be dominated by repeated key recalculation.

For expensive computed keys, consider precomputing them into auxiliary data used for the sort pass:

~~~java
// Illustrates the concept, not a standalone program.
record RankedProduct(Product product, int computedRank) {}

Comparator<RankedProduct> order =
        Comparator.comparingInt(RankedProduct::computedRank)
                .thenComparing(value -> value.product().code());
~~~

The step that constructs `RankedProduct` instances computes the key according to business rules, and the sort only reads back the precomputed key. This approach uses extra memory and requires deciding when the data snapshot is taken. Do not introduce a naive global cache just to avoid recalculation while ignoring that underlying keys might change.

Factory comparators also do not protect keys from mutating after elements have been inserted into a `TreeSet` or another comparator-based structure. If a key that determines position is mutated in place, you must update the structure through a proper removal/re-insertion workflow rather than expecting the comparator to relocate the object automatically.

## 12. Complete Program

Save as **KeyComparatorDemo.java**. The sample data uses:

- `name`: `String` key.
- `stock`: `int` key.
- `priceInCents`: `long` key.
- `rating`: `double` key.
- `category`: nullable `String` key.
- `code`: secondary tie-breaker so the example output is deterministic.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class KeyComparatorDemo {
    record Product(
            String code,
            String name,
            int stock,
            long priceInCents,
            double rating,
            String category
    ) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P3", "banana", 4, 250L, 4.6, "food"),
                new Product("P1", "Apple", 10, 500L, 4.2, "food"),
                new Product("P4", "cable", 4, 1000L, 4.8, null),
                new Product("P2", "apple", 4, 300L, 4.2, "tools")
        );

        Comparator<Product> byName = Comparator.comparing(Product::name);
        Comparator<Product> byNameIgnoringCase =
                Comparator.comparing(
                        Product::name,
                        String.CASE_INSENSITIVE_ORDER
                ).thenComparing(Product::code);

        Comparator<Product> byStockThenCode =
                Comparator.comparingInt(Product::stock)
                        .thenComparing(Product::code);

        Comparator<Product> byPrice =
                Comparator.comparingLong(Product::priceInCents)
                        .thenComparing(Product::code);

        Comparator<Product> byRatingDescending =
                Comparator.comparingDouble(Product::rating)
                        .reversed()
                        .thenComparing(Product::code);

        Comparator<Product> byStockDescendingThenPrice =
                Comparator.comparingInt(Product::stock)
                        .reversed()
                        .thenComparingLong(Product::priceInCents)
                        .thenComparing(Product::code);

        Comparator<Product> wholeOrderReversed =
                Comparator.comparingInt(Product::stock)
                        .thenComparingLong(Product::priceInCents)
                        .thenComparing(Product::code)
                        .reversed();

        Comparator<Product> byNullableCategory =
                Comparator.comparing(
                        Product::category,
                        Comparator.nullsLast(Comparator.naturalOrder())
                ).thenComparing(Product::code);

        printCodes("Name natural", products, byName);
        printCodes("Name ignoring case", products, byNameIgnoringCase);
        printCodes("Stock then code", products, byStockThenCode);
        printCodes("Price", products, byPrice);
        printCodes("Rating descending", products, byRatingDescending);
        printCodes("Stock descending, price ascending",
                products, byStockDescendingThenPrice);
        printCodes("Whole chain reversed", products, wholeOrderReversed);
        printCodes("Category nulls last", products, byNullableCategory);

        List<Product> includingNull = new ArrayList<>(products);
        includingNull.add(null);

        printCodes("Null elements last",
                includingNull, Comparator.nullsLast(byNullableCategory));

        System.out.println("Original = " + codes(products));

        Product min = new Product(
                "MIN", "min", Integer.MIN_VALUE, 0L, 0.0, "demo");
        Product max = new Product(
                "MAX", "max", Integer.MAX_VALUE, 0L, 0.0, "demo");

        Comparator<Product> bad =
                (left, right) -> left.stock() - right.stock();
        Comparator<Product> safe =
                Comparator.comparingInt(Product::stock);

        System.out.println("Subtraction sign = "
                + Integer.signum(bad.compare(min, max)));
        System.out.println("comparingInt sign = "
                + Integer.signum(safe.compare(min, max)));
    }

    private static void printCodes(
            String label,
            List<Product> source,
            Comparator<? super Product> order
    ) {
        List<Product> copy = new ArrayList<>(source);
        copy.sort(order);
        System.out.println(label + " = " + codes(copy));
    }

    private static List<String> codes(List<Product> products) {
        List<String> result = new ArrayList<>();
        for (Product product : products) {
            result.add(product == null ? "<null>" : product.code());
        }
        return result;
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 KeyComparatorDemo.java
java KeyComparatorDemo
~~~

Stdout:

~~~text
Name natural = [P1, P2, P3, P4]
Name ignoring case = [P1, P2, P3, P4]
Stock then code = [P2, P3, P4, P1]
Price = [P3, P2, P1, P4]
Rating descending = [P4, P3, P1, P2]
Stock descending, price ascending = [P1, P3, P2, P4]
Whole chain reversed = [P1, P4, P2, P3]
Category nulls last = [P1, P3, P2, P4]
Null elements last = [P1, P3, P2, P4, <null>]
Original = [P3, P1, P4, P2]
Subtraction sign = 1
comparingInt sign = -1
~~~

### Explanation of Key Results

- The two name-based lines produce the same code sequence on this sample dataset, but through different rules: `"Apple"` and `"apple"` compare as different under natural order, whereas the case-insensitive rule treats them as equal and falls back to the product code tie-breaker.
- When sorting by stock then code, the stock `4` group comes before stock `10`; within the stock `4` group, the codes are ordered `P2, P3, P4`.
- Ascending prices are `250, 300, 500, 1000`, corresponding to `P3, P2, P1, P4`.
- Descending rating places `P4` ahead of `P3`. `P1` and `P2` share the rating `4.2`, so their product codes break the tie.
- With descending stock followed by ascending price, `P1` comes first; the stock `4` group follows ascending prices `250, 300, 1000`.
- Reversing the entire chain makes the stock `4` group follow the reverse of ascending price, producing `P4, P2, P3`.
- The `category == null` group is placed after named categories; a `Product == null` element is handled by the outer wrapper comparator and placed at the very end.
- `printCodes` copies the list before sorting. The `Original` line confirms that the source list retains its initial sequence of codes.
- The last two lines demonstrate boundary values: subtraction produces the wrong sign `1`, whereas `comparingInt` produces `-1`, matching `MIN_VALUE < MAX_VALUE`.

## 13. Single-Key Comparators and What compare Returning 0 Means

If you only use:

~~~java
Comparator<Product> byStock = Comparator.comparingInt(Product::stock);
~~~

then any products with the same stock quantity will compare equal (`0`), even if they have different codes, names, or prices.

When sorting a list, this does not discard products. A stable sort preserves the relative pre-sort order of elements that the comparator considers equivalent.

However, if you pass that comparator to a `TreeSet<Product>`, the set uses the comparison result to determine element equivalence and position. Two products with the same stock quantity will occupy only a single slot in the set. Consequently, a comparator that makes sense for **presenting a list by a criterion** may not make sense for **a set that defines uniqueness**.

Only add `thenComparing(Product::code)` when the code is genuinely an appropriate distinguishing criterion. If you need a comparator that is consistent with `equals`, you must align it with the type's complete `equals` definition, rather than adding one extra field and assuming every case is covered.

## 14. Testing a Key-Based Comparator

Start with a small dataset where a reader can trace the expected result by hand:

1. Two elements with different primary keys.
2. Two elements with equal primary keys but different secondary keys.
3. Two elements that are equal across all criteria.
4. Boundary `int` or `long` values when numeric keys are involved.
5. A `null` key, a `null` element, and a `null` intermediate object if the data domain allows them.
6. Descending order combined with `null` to verify the scope of `reversed()`.

You can also verify the mathematical properties of the comparison relation:

- Swapping the two arguments must invert the sign, except when both directions return `0`.
- If `a` comes after `b` and `b` comes after `c`, then `a` must come after `c`.
- If `a` and `b` compare as equal, they must yield the same sign relationship when compared against any third element `c`.

With comparator factories, bugs usually lie in the key rule, data assumptions, null-wrapper placement, or chaining order rather than in low-level comparison algorithms. Tests should verify actual business rules, not merely prove that a list runs through `sort` without throwing.

## 15. Common Mistakes

| Code pattern or misconception | Problem | Solution |
| --- | --- | --- |
| Calling `comparing` and thinking the list is already sorted | Only creates a comparator instance | Pass the comparator to the operation that needs it. |
| Using `comparingInt` with a lambda returning `long` | Type mismatch or narrowing cast that loses data | Use `comparingLong`. |
| Using subtraction as the comparison result | Can overflow or lose precision | Use a primitive comparator factory or `compare` method. |
| Using single-argument `comparing` for a key that does not implement `Comparable` | No natural order available to use | Pass a second argument specifying the key comparator. |
| Wrapping `nullsLast` only on the outside | Handles `null` elements, but not `null` keys | Apply null policies at each layer where data can actually be missing. |
| Wrapping `nullsLast` only on the key comparator | Does not prevent invoking the extractor on a `null` element | Wrap the element comparator as well if elements can be `null`. |
| Calling `reversed` at the end of a chain when only one key should be descending | Reverses the entire composed ordering | Reverse the individual component comparator before chaining the next criterion. |
| Eagerly computing an expensive secondary key on every comparison even when not needed | Increases cost and may introduce side effects | Use proper comparator chaining; consider precomputing keys at the data level when appropriate. |
| Mutating an element's key while it resides in an ordered structure | The structure's internal position is not updated automatically | Design a remove-update-reinsert workflow or use immutable key data. |
| Reusing a list-display comparator for a `TreeSet` without considering uniqueness | Elements sharing the same key can be silently dropped | Redefine the equivalence relation or choose a different collection type. |

## 16. Exercises

1. Add a rule: case-insensitive name ascending, stock descending, then code ascending. Write the comparator and explain the scope of each `reversed` call.
2. Write a comparator for products by name length, then by name in natural order. List the cases that must be handled if the name can be `null`.
3. Modify the example so that `category` sorts in descending order while `null` category keys remain last, but `null` product elements come first.
4. Create two products with different codes but identical stock quantities. Compare the results when using the stock-only comparator with a `List` versus a `TreeSet`.
5. Create a key type that does not implement `Comparable`; write a comparator for that key and use the two-parameter form of `comparing`.
6. If a key is a rating score that is very expensive to compute, design a way to capture the key once per element during a processing pass, and explain how to handle changes to the underlying source data.

Before choosing a factory method, answer three questions: what object type is being compared, what is the type of the extracted key, and what rule determines the order among those keys. Only after that should you consider secondary tie-breakers, ascending/descending direction, and missing-data policies.