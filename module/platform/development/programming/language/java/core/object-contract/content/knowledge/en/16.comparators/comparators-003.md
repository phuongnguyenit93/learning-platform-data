# `Comparator.comparing()` and the `comparingInt()`, `comparingLong()`, `comparingDouble()` Variants

When sorting a list of Java objects by a property, you usually do not need to write out `compare(a, b)` in full manually. The `java.util.Comparator<T>` interface provides **static factory methods** that build a comparator from a *key extractor* function:

- `Comparator.comparing(...)`: extracts an object-typed key, comparing keys by natural order or using another comparator.
- `Comparator.comparingInt(...)`: extracts a primitive `int` key.
- `Comparator.comparingLong(...)`: extracts a primitive `long` key.
- `Comparator.comparingDouble(...)`: extracts a primitive `double` key.

All four create a `Comparator<T>` to pass into `List.sort(...)`, `Collections.sort(...)`, `Stream.sorted(...)`, `Arrays.sort(...)`, or any API requiring a sort order. The main differences lie in the **key type** and **how keys are compared**.

## 1. How Does `Comparator<T>` Determine Order?

The factories in this lesson build a `Comparator<T>` by **extracting a key** from each object and comparing those keys. For example:

~~~java
Comparator<Employee> byAge =
        Comparator.comparingInt(Employee::age);
~~~

This is a code fragment assuming `Employee.age()` returns `int`. `Employee::age` is equivalent to `e -> e.age()` as a key extractor.

The result of `compare(a,b)` has a negative sign if `a` comes before `b`, equals 0 if they tie on the chosen key, and is positive if `a` comes after `b`. The rules of sign symmetry, transitivity, and zero-comparison groups still apply; the factory method does not absolve you from ensuring keys are valid and stable. The focus here is **choosing the right overload for the key type**, including primitives, nullables, and `double` with special values.
## 2. Quick Comparison of the Four Factory Methods

| Factory | Key extractor function type | Key comparison | Typical use cases |
| --- | --- | --- | --- |
| `comparing(keyExtractor)` | `Function<? super T, ? extends U>`, where `U` has a natural order | `U.compareTo(...)` via `Comparable` | `String`, `LocalDate`, `BigDecimal`, enums… |
| `comparing(keyExtractor, keyComparator)` | `Function<? super T, ? extends U>` | Custom key comparator | Case-insensitive, nullable keys, business-specific orders |
| `comparingInt(keyExtractor)` | `ToIntFunction<? super T>` | `Integer.compare(...)` | Age, quantity, `int` priority level |
| `comparingLong(keyExtractor)` | `ToLongFunction<? super T>` | `Long.compare(...)` | `long` timestamps, large counts, sequences |
| `comparingDouble(keyExtractor)` | `ToDoubleFunction<? super T>` | `Double.compare(...)` | Scores, ratios, `double` measurements |

The three primitive variants allow the extractor to return `int`, `long`, or `double` directly, avoiding boxing that key into `Integer`, `Long`, or `Double` just to call `compareTo`. This expresses intent clearly and can reduce boxing overhead when sorting many elements. It does not mean every part of the sort process will be completely allocation-free.

Note: `comparingInt`/`Long`/`Double` do **not** have an overload taking an extra `Comparator` for primitive keys. To use a non-natural comparison rule, consider a controlled key transformation, `reversed()`, or a suitable custom comparator. Only `comparing(...)` has an overload accepting a second comparator for object-typed keys.

## 3. `comparing()` with `Comparable` Keys

Suppose `Product` has a `String` name:

~~~java
Comparator<Product> byName =
    Comparator.comparing(Product::name);
~~~

This is a code fragment assuming `Product.name()` returns `String`. Because `String` implements `Comparable<String>`, the new comparator uses string natural order, which is based on lexicographical comparison of UTF-16 values; it does not automatically match locale-specific Vietnamese name sorting rules.

Some common examples:

~~~java
Comparator<Order> byDate =
    Comparator.comparing(Order::createdOn); // LocalDate

Comparator<Invoice> byAmount =
    Comparator.comparing(Invoice::total);   // BigDecimal
~~~

These lines **only illustrate syntax** assuming classes `Order` and `Invoice` have the corresponding methods. `LocalDate` and `BigDecimal` provide `compareTo()`, making them suitable for the single-argument overload.

If the key type does not implement a suitable `Comparable`, the `comparing(keyExtractor)` overload cannot rely on natural order; pass a `Comparator<U>` defining the key comparison rule:

~~~java
Comparator<Product> byNameIgnoringCase =
    Comparator.comparing(
        Product::name,
        String.CASE_INSENSITIVE_ORDER
    );
~~~

This also emphasizes that a comparator describes **ordering**, not necessarily equality matching `equals()`: two strings differing in letter case can yield `compare(...) == 0` under `CASE_INSENSITIVE_ORDER` while `String.equals()` still returns `false`.

## 4. `comparingInt()`, `comparingLong()`, and `comparingDouble()`

### `comparingInt(ToIntFunction)`

~~~java
Comparator<Employee> byAge =
    Comparator.comparingInt(Employee::age);
~~~

If two ages are `22` and `30`, `byAge.compare(e22, e30)` is a negative number. There is no need to write the subtraction `e22.age() - e30.age()`.

**Avoid comparing integers using subtraction:**

~~~java
// WRONG: integer overflow can flip the sign of the result.
Comparator<Employee> risky =
    (a, b) -> a.age() - b.age();

// RIGHT: Comparator.comparingInt uses overflow-safe comparison.
Comparator<Employee> safe =
    Comparator.comparingInt(Employee::age);
~~~

With `int`, subtracting `Integer.MIN_VALUE - Integer.MAX_VALUE` can overflow and return the wrong sign; `Integer.compare` does not suffer from that bug. The snippet above is an illustrative fragment within the scope of class `Employee`.

### `comparingLong(ToLongFunction)`

~~~java
Comparator<Event> byTimestamp =
    Comparator.comparingLong(Event::timestamp);
~~~

Use when the key is `long`, such as epoch milliseconds, record counts, or large sequence numbers. Especially do not cast the difference of two `long` values to `int`:

~~~java
// WRONG: risks both long subtraction overflow and bit truncation.
Comparator<Event> risky =
    (a, b) -> (int) (a.timestamp() - b.timestamp());
~~~

Writing `comparingLong` uses `Long.compare` and preserves order across the entire `long` range. If the data represents timestamps, you must know that the stored numbers share the same unit and time convention; the comparator does not automatically convert seconds to milliseconds.

### `comparingDouble(ToDoubleFunction)`

~~~java
Comparator<Measurement> byValue =
    Comparator.comparingDouble(Measurement::value);
~~~

The factory uses `Double.compare`, which has properties to keep in mind:

- `-0.0` is ordered **before** `+0.0` even though the arithmetic expression `-0.0 == +0.0` is `true`.
- `Double.NaN` is ordered **after** finite numbers and infinities in `Double.compare`'s ascending order; different NaN representations are treated as equal in this comparison.
- `Double.NEGATIVE_INFINITY` comes before finite numbers; `Double.POSITIVE_INFINITY` comes after finite numbers but before NaN.

Therefore, do not arbitrarily replace `comparingDouble` with `(a, b) -> (int) (a.score() - b.score())`: casting a `double` difference to `int` can turn small differences into `0`, losing the desired order; NaN and infinities also cause issues.

If the business domain needs to exclude `NaN` or apply an approximate threshold, state the handling policy explicitly. In particular, do **not** treat two numbers "differing by less than epsilon" as equivalent in a comparator used for sorting or as a `TreeSet` key when that relation is not transitive.

## 5. Complete Java 17 Example and Verifiable Output

Create the file **`ComparatorFactoriesDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ComparatorFactoriesDemo {

    record Applicant(String name, int age, long visits, double score) {}

    private static void printSorted(
            String label,
            List<Applicant> source,
            Comparator<Applicant> comparator) {
        String names = source.stream()
                .sorted(comparator)
                .map(Applicant::name)
                .collect(Collectors.joining(", "));
        System.out.println(label + ": " + names);
    }

    public static void main(String[] args) {
        List<Applicant> data = List.of(
                new Applicant("Lan", 22, 5L, 9.5),
                new Applicant("An", 30, 12L, 8.0),
                new Applicant("Binh", 22, 7L, 9.5),
                new Applicant("Mai", 30, 3L, -0.0),
                new Applicant("Hoa", 22, 15L, Double.NaN)
        );

        printSorted("name", data,
                Comparator.comparing(Applicant::name));

        printSorted("age then name", data,
                Comparator.comparingInt(Applicant::age)
                        .thenComparing(Applicant::name));

        printSorted("visits descending", data,
                Comparator.comparingLong(Applicant::visits)
                        .reversed());

        printSorted("score then name", data,
                Comparator.comparingDouble(Applicant::score)
                        .thenComparing(Applicant::name));

        List<Applicant> withNullName = List.of(
                new Applicant(null, 20, 1L, 0.0),
                new Applicant("Zed", 25, 2L, 1.0)
        );
        Comparator<Applicant> nullableName =
                Comparator.comparing(
                        Applicant::name,
                        Comparator.nullsFirst(
                                String.CASE_INSENSITIVE_ORDER));

        String nullableResult = withNullName.stream()
                .sorted(nullableName)
                .map(a -> a.name() == null ? "<null>" : a.name())
                .collect(Collectors.joining(", "));
        System.out.println("nullable names: " + nullableResult);

        Applicant low = new Applicant("MIN", 0, Long.MIN_VALUE, 0.0);
        Applicant high = new Applicant("MAX", 0, Long.MAX_VALUE, 0.0);
        Comparator<Applicant> safeLong =
                Comparator.comparingLong(Applicant::visits);
        System.out.println("long extremes ordered: "
                + (safeLong.compare(low, high) < 0));

        System.out.println("minus zero before plus zero: "
                + (Double.compare(-0.0, +0.0) < 0));
        System.out.println("NaN after positive infinity: "
                + (Double.compare(
                        Double.NaN, Double.POSITIVE_INFINITY) > 0));
    }
}
~~~

Compile and run:

~~~bash
javac ComparatorFactoriesDemo.java
java ComparatorFactoriesDemo
~~~

**Standard output:**

~~~text
name: An, Binh, Hoa, Lan, Mai
age then name: Binh, Hoa, Lan, An, Mai
visits descending: Hoa, An, Binh, Lan, Mai
score then name: Mai, An, Binh, Lan, Hoa
nullable names: <null>, Zed
long extremes ordered: true
minus zero before plus zero: true
NaN after positive infinity: true
~~~

Explanation:

1. `comparing(Applicant::name)` extracts `String` and compares in natural order; names are sorted ascending.
2. `comparingInt(Applicant::age)` puts the age `22` group before the `30` group. `thenComparing(Applicant::name)` breaks ties by name: within group `22` it is `Binh, Hoa, Lan`, and within group `30` it is `An, Mai`.
3. `comparingLong(Applicant::visits).reversed()` produces descending visit counts: `15, 12, 7, 5, 3`.
4. `comparingDouble(Applicant::score)` orders `-0.0, 8.0, 9.5, 9.5, NaN`. `thenComparing(name)` puts `Binh` before `Lan` when scores tie.
5. Nullable names are sorted with `Comparator.nullsFirst(...)` for the **String key**, so the `null` key comes before `"Zed"`.
6. For the two extreme `long` values, the factory uses `Long.compare` and identifies the order properly. The last two lines illustrate `Double.compare`'s rules for signed zero and NaN.

`record Applicant` is used as a compact data model to reduce boilerplate; the accessor methods `name()`, `age()`, `visits()`, `score()` are generated by Java. Java 17 officially supports records.

## 6. Chaining Multiple Criteria with `thenComparing...`

A single key sometimes cannot distinguish all elements. For instance, sorting by `age` yields `0` for two people of the same age. In that case, you chain secondary criteria:

~~~java
Comparator<Applicant> order =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::name)
              .thenComparingLong(Applicant::visits)
              .thenComparingDouble(Applicant::score);
~~~

This is a fragment using `Applicant` from the complete example. Evaluation flow:

1. Compare `age`. If different, return immediately by age.
2. If ages are equal, compare `name`.
3. If names are still equal, compare `visits`.
4. If still equal, compare `score`.

`thenComparingInt`, `thenComparingLong`, and `thenComparingDouble` are suited for primitive secondary criteria and behave like their corresponding factories. The comparator does not evaluate subsequent criteria once an earlier criterion determines the order.

### Reversing with the right scope

~~~java
// Reverses the entire comparator: age descending, then name descending.
Comparator<Applicant> allDescending =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::name)
              .reversed();

// Age descending, but name still ascending when ages tie.
Comparator<Applicant> ageDescNameAsc =
    Comparator.comparingInt(Applicant::age)
              .reversed()
              .thenComparing(Applicant::name);

// Age ascending, name descending when ages tie.
Comparator<Applicant> ageAscNameDesc =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(
                  Comparator.comparing(Applicant::name).reversed()
              );
~~~

These snippets use `Applicant` from the example above and are not separate complete files. `reversed()` reverses the result of the **entire comparator chained up to the point of the call**. To reverse only one key, reverse that key's individual comparator before chaining it. Avoid mistaking `reversed()` as always reversing only the "first column."

If you only need to sort a list without mutating the original list, `stream().sorted(comparator).toList()` (Java 16+) creates a result list in order; `List.sort(comparator)` mutates the target list and cannot be used on structurally unmodifiable lists created by `List.of(...)`. Java guarantees `List.sort` is stable; for elements with `compare(a,b)==0`, the original relative order is preserved. However, when business logic requires a fully deterministic order, add an explicit secondary criterion, especially before pagination or exporting reports.

## 7. Handling `null` at the Right Layer

Default factories typically **do not handle null keys automatically**. If an extractor returns `null` and the key comparator does not support null, sorting can throw `NullPointerException`.

There are two distinct situations:

**A. The element being sorted itself is `null`:**

~~~java
Comparator<Applicant> byAgeAllowNullApplicant =
    Comparator.nullsLast(
        Comparator.comparingInt(Applicant::age)
    );
~~~

The outer `nullsLast` layer sends `null` `Applicant` elements to the end. Only when the element is non-null does the inner comparator access `age()`.

**B. The element is non-null, but the `name()` key can be null:**

~~~java
Comparator<Applicant> byNullableName =
    Comparator.comparing(
        Applicant::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    );
~~~

Here `nullsLast` handles **the String value returned by the extractor**, and does not automatically handle a null `Applicant` element. If both the element itself and the key can be null, wrap at both layers with the appropriate policies.

With primitive extractors like `ToIntFunction`, the return type is `int` so it cannot be `null`. However, if code writes `Comparator.comparingInt(e -> e.getNullableAge())` and `getNullableAge()` returns `Integer`, Java must unbox it; a null value will cause a `NullPointerException`. Determine the policy for nullable fields first: use the `comparing(...)` overload with a null-safe key comparator, map to a meaningful default value, or reject missing data.

## 8. Comparator Order and `equals()` Are Different Concepts

`Comparator.compare(a, b) == 0` means **equivalent in the ordering defined by the comparator**; it does not necessarily mean `a.equals(b)`. For example, two `Applicant` instances of the same age but different names can yield `0` when using `comparingInt(Applicant::age)`.

This is especially important when using the comparator with `TreeSet` and `TreeMap`:

~~~java
Comparator<Applicant> byAge =
    Comparator.comparingInt(Applicant::age);
~~~

The snippet above can be a very useful sorting criterion for a `List`. Yet if passed to a `TreeSet<Applicant>`, applicants of the **same age** will be treated as duplicates by the tree structure according to the comparator, even though their names and other properties differ. `TreeMap` also determines duplicate keys by the comparator's `compare==0` result, rather than relying on `equals()` as `HashMap` does.

If the requirement is to retain all distinct applicants in a `TreeSet`, add a unique, stable tie-breaking criterion consistent with the intended set semantics, such as a business ID:

~~~java
// Assumes a real Applicant type has id() as a stable distinguishing key.
Comparator<Applicant> byAgeThenId =
    Comparator.comparingInt(Applicant::age)
              .thenComparing(Applicant::id);
~~~

This is only a code snippet illustrating the rule; `Applicant` in the runnable example in section 5 does not yet have an `id()` field. Do **not** build a comparator that returns erratic differing results merely to retain all elements: the comparator must still satisfy transitivity and consistency.

In addition, sorting `BigDecimal` ascending with `Comparator.comparing(Invoice::total)` uses `BigDecimal.compareTo`. This method can return `0` between `1.0` and `1.00` even though `BigDecimal.equals()` returns `false`. That is acceptable when merely **sorting**, but needs careful consideration when using this comparator as the duplicate-key rule in a `TreeMap` or `TreeSet`.

## 9. Notes on Performance and Correctness

- **Prefer expressive method references:** `Comparator.comparingInt(Person::age)` is usually clearer than a lambda manually subtracting two ages.
- **Pick the right key type:** if a getter returns `long`, use `comparingLong` instead of casting to `int`; if it returns `double`, understand `Double.compare`'s NaN/signed-zero policy.
- **Keep extractors pure and stable:** do not mutate object state, generate random values, or depend on data changing between comparisons during the same sort operation. The sort may invoke the extractor multiple times and on varying pairs.
- **Do not use approximate equality as a comparison relation:** comparing within an `epsilon` tolerance usually lacks transitivity; separate it into a dedicated check rather than embedding it into a sorting comparator.
- **Do not expect key caching:** factories do not promise to call the extractor only once per element. If computing the key is expensive, consider creating a record holding precomputed keys (*decorate-sort-undecorate*) or a dedicated stable key model.
- **Do not misuse `reversed()`:** specify the direction of each criterion explicitly when chaining multiple keys and verify with examples containing duplicate primary keys.

## 10. Checklist When Applying

Before choosing a comparator factory, check:

1. Is the sort key an object with `Comparable`, an object needing a custom comparator, or a primitive `int`/`long`/`double`?
2. If using `comparing(...)`, does the key truly support natural comparison? If not, have you passed a `keyComparator`?
3. Can `null` occur at the **element** level or the **key** level? Is `nullsFirst`/`nullsLast` placed at the right layer?
4. Can `double` contain NaN, infinity, or `-0.0`? Does `Double.compare`'s ordering fit the business logic?
5. Should a secondary criterion be chained via `thenComparing(...)` for deterministic ordering within tied-key groups?
6. Is `reversed()` reversing the entire comparator or only the intended criterion?
7. Is the comparator used in `TreeSet`/`TreeMap`? If so, does `compare(a,b)==0` match the intended meaning of "duplicate element/key"?
8. Are key-extracting fields stable during sorting or for the duration of their stay in a tree structure?

**Takeaway:** `comparing()` is for **object keys** (using `Comparable` or a custom key comparator). `comparingInt()`, `comparingLong()`, and `comparingDouble()` are for **primitive keys**, expressing the type clearly and avoiding unnecessary key boxing. Use `thenComparing...` to combine criteria, `reversed()` to reverse order, and always explicitly specify rules for null, floating-point numbers, and `compare==0` semantics in sorted collections.