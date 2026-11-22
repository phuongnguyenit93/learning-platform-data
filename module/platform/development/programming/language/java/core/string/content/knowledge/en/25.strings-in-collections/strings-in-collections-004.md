# Sorting List<String> by Natural Order or Comparator in Java

## Lesson Objectives

When you have a list of strings `List<String>`, you often want to display them from A to Z, Z to A, case-insensitively, by length, or according to language rules. Java provides `String`'s **natural order** and the `Comparator` mechanism to define custom ordering.

After this lesson, you will be able to:

- Use `List.sort(null)`, `Collections.sort(list)`, or `list.sort(Comparator.naturalOrder())` to sort in ascending natural order.
- Explain how `String.compareTo` compares lexicographical order by UTF-16 code units and why the result does not equal Vietnamese alphabetical order.
- Write a `Comparator` for descending order, length, multiple criteria, and case-insensitive comparison.
- Distinguish sorting **in-place on a list** from creating a **new list** via Stream.
- Handle `null` elements, unmodifiable lists, stable sorting requirements, and caveats when using `Collator`.

## 1. What Is Natural Ordering?

`String` implements `Comparable<String>`. Therefore, any string can be compared with another via:

~~~java
int result = first.compareTo(second);
~~~

By `Comparable` convention:

- `result < 0`: `first` comes before `second`.
- `result == 0`: the two strings have equal order under this comparison.
- `result > 0`: `first` comes after `second`.

`String.compareTo` examines **UTF-16** code units from left to right, using the numeric values of the first differing `char`s; if all examined code units match but one string is shorter, the shorter string comes first. As a result, uppercase Latin `A` has a smaller code than lowercase `a`: natural order is **case-sensitive**. For accented characters or non-ASCII characters, the result follows UTF-16 order, which is not natural-language dictionary order by default.

Example:

~~~java
System.out.println("Apple".compareTo("apple") < 0); // true
System.out.println("app".compareTo("apple") < 0);   // true
System.out.println("cat".compareTo("car") > 0);     // true
~~~

**Remember:** The "natural order" of `String` is the ordering defined by `String.compareTo`. It does not strip accents, does not ignore letter case, and does not read Vietnamese or Japanese collation rules.

## 2. Sorting a List<String> In-Place

The three common approaches below share the same meaning—sorting ascending in natural order—when the list contains no `null`:

~~~java
Collections.sort(list);
list.sort(null);
list.sort(Comparator.naturalOrder());
~~~

- `Collections.sort(list)` is a familiar utility API; under the hood it delegates to sorting the list.
- `list.sort(null)` uses the natural order of the elements.
- `list.sort(Comparator.naturalOrder())` explicitly states that the comparator is natural order.

All three **modify the element order of the list itself**. They do not create a new `List` and require the list to support `set`/positional swapping. Not every `List` implementation permits this.

### Standalone Runnable Java 17+ Example

Save as `NaturalSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class NaturalSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("banana", "Apple", "apple", "Banana", "Zebra", "áo"));

        words.sort(Comparator.naturalOrder());
        System.out.println(words);

        words.sort(Comparator.reverseOrder());
        System.out.println(words);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NaturalSortDemo.java
java NaturalSortDemo
~~~

Output:

~~~text
[Apple, Banana, Zebra, apple, banana, áo]
[áo, banana, apple, Zebra, Banana, Apple]
~~~

Reason: `A`, `B`, `Z` are uppercase Latin code units preceding `a`, `b`, while `á` (`U+00E1`) comes after `b` in natural comparison in this example. `Comparator.reverseOrder()` reverses natural order. For linguistically meaningful data, see the `Collator` section below.

**Note:** `List.of("a", "b")` returns an unmodifiable list. That is why the example above wraps it in `new ArrayList<>(...)` before calling `sort`. Calling sort directly on `List.of(...)` can throw `UnsupportedOperationException`.

## 3. How Does Comparator Work?

`Comparator<String>` describes a rule for comparing two strings:

~~~java
Comparator<String> byLength = (left, right) ->
        Integer.compare(left.length(), right.length());
~~~

The return value is negative, zero, or positive with the same meaning as `compareTo`. In modern Java, you usually do not need to write a manual lambda to compare lengths:

~~~java
Comparator<String> byLength = Comparator.comparingInt(String::length);
~~~

`Comparator.comparingInt` extracts an `int` key from each element; here the key is `length()`. A comparator can be passed to `List.sort`, `Stream.sorted`, `Collections.sort`, or other APIs accepting a comparison order.

**Avoid writing** `left.length() - right.length()` as a comparison result when keys can be arbitrary large integers, because subtraction can overflow. Using `Integer.compare` or `comparingInt` prevents this bug. Even though `String.length()` is non-negative in practice, `comparingInt` still expresses intent more clearly.

### Sorting by Length, Then Alphabetically

If only length is used, strings of equal length are treated as tied. `thenComparing` adds a secondary criterion to make the result predictable:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class LengthSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("pear", "fig", "apple", "kiwi", "plum", "fig"));

        Comparator<String> lengthThenNatural =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        words.sort(lengthThenNatural);
        System.out.println(words);

        words.sort(Comparator.comparingInt(String::length)
                .reversed()
                .thenComparing(Comparator.naturalOrder()));
        System.out.println(words);
    }
}
~~~

Save `LengthSortDemo.java` and run:

~~~bash
javac -encoding UTF-8 LengthSortDemo.java
java LengthSortDemo
~~~

Output:

~~~text
[fig, fig, kiwi, pear, plum, apple]
[apple, kiwi, pear, plum, fig, fig]
~~~

Explanation:

1. First sort: ascending length, then natural order on ties. `fig` (3 characters) comes before 4-character words; `apple` (5 characters) is last.
2. Second sort: descending length; when lengths are equal, natural order remains ascending because `reversed()` is placed **before** `thenComparing(...)`.

Call order matters greatly:

~~~java
Comparator<String> a = Comparator
        .comparingInt(String::length)
        .reversed()
        .thenComparing(Comparator.naturalOrder());

// Different from the comparator below:
Comparator<String> b = Comparator
        .comparingInt(String::length)
        .thenComparing(Comparator.naturalOrder())
        .reversed();
~~~

In `a`, only the length criterion is reversed and then an ascending secondary criterion is added; in `b`, **the entire composite comparator** is reversed, including the secondary criterion. Choose the form matching business requirements.

## 4. Case-Insensitive List Sorting

`String.CASE_INSENSITIVE_ORDER` uses `String`'s case-insensitive comparison rule:

~~~java
List<String> words = new ArrayList<>(
        List.of("apple", "Banana", "banana", "Apple", "pear"));
words.sort(String.CASE_INSENSITIVE_ORDER);
System.out.println(words); // [apple, Apple, Banana, banana, pear]
~~~

`List.sort` is **stable**: when the comparator returns `0` for `"apple"` and `"Apple"`, their original relative order is preserved. The list does not drop elements even when the comparator treats them as equal.

When deterministic order is needed among case variants, add a secondary criterion:

~~~java
words.sort(String.CASE_INSENSITIVE_ORDER
        .thenComparing(Comparator.naturalOrder()));
System.out.println(words); // [Apple, apple, Banana, banana, pear]
~~~

`CASE_INSENSITIVE_ORDER` is not a linguistic sorter for every locale. Furthermore, if this comparator is used in `TreeMap` or `TreeSet`, `compare == 0` can **merge keys that differ by `equals`**. The next lesson on the Comparator/equals relationship analyzes that exact behavior.

## 5. Sorting Strings by Language: Collator

For user-facing interfaces in a specific language, `String`'s natural order or `CASE_INSENSITIVE_ORDER` may be unsuitable. For example, when sorting word lists, personal names, or Vietnamese display labels, accented character ordering and comparison rules can differ from UTF-16 code order.

`java.text.Collator` is a `Locale`-dependent character comparator:

~~~java
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class LocaleSortDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        Collator collator = Collator.getInstance(locale);

        List<String> words = new ArrayList<>(
                List.of("áo", "An", "ăn", "anh", "Ánh", "ao"));
        words.sort(collator);

        System.out.println(words);
    }
}
~~~

Save `LocaleSortDemo.java`; run `javac -encoding UTF-8 LocaleSortDemo.java` and `java LocaleSortDemo`. The printed list is sorted according to **the collation rules provided by the JDK/provider for `vi-VN`**. The exact order may vary across JDK versions or locale data, so do not hardcode an accented stdout for this example. Run and verify on your application's target runtime.

### Comparison Strength and Consistency

`Collator` has strength levels `PRIMARY`, `SECONDARY`, and `TERTIARY` to distinguish different character features (such as base letter, diacritics, and letter case), depending on the locale's collation data. Example:

~~~java
collator.setStrength(Collator.PRIMARY);
words.sort(collator);
~~~

For certain locales or string pairs, `PRIMARY` strength may treat multiple variants as equal. Define your product's policy on accents and case rather than assuming `PRIMARY` always means "strip all accents." For internationalized content, test with real word pairs.

`Collator` holds mutable configuration state and should not have the same instance mutated concurrently without synchronization. If you want a completely deterministic order when two strings are equal under collation, you can add a natural-order tie-breaker:

~~~java
Comparator<String> localeOrder = (left, right) -> collator.compare(left, right);
words.sort(localeOrder.thenComparing(Comparator.naturalOrder()));
~~~

Note: the tie-breaker clarifies how to handle cases where the collation comparator returns `0`; it does not replace the language rules themselves. When results are persisted, shared across systems, or used as index keys, collation version/data management is also needed to avoid ordering shifts across environments.

## 6. Nulls in Lists and Unmodifiable Objects

`Comparator.naturalOrder()` and `String.compareTo` do not handle `null` automatically. When a list contains a `null` element, natural sorting can throw `NullPointerException`. If data rules allow missing values, choose where to place them:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullSortDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                Arrays.asList("pear", null, "apple"));

        words.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println(words);

        words.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println(words);
    }
}
~~~

Save `NullSortDemo.java`, compile, and run:

~~~bash
javac -encoding UTF-8 NullSortDemo.java
java NullSortDemo
~~~

Output:

~~~text
[apple, pear, null]
[null, apple, pear]
~~~

`Comparator.nullsLast(inner)` places `null` after all other strings; `nullsFirst(inner)` places it at the start. The inner comparator still governs the ordering of non-`null` strings.

In addition, distinguish the following:

| Creation or source | Can be sorted in-place? | Notes |
| --- | --- | --- |
| `new ArrayList<>(...)` | Yes | Element order can be modified |
| `Arrays.asList(...)` | Usually yes | Fixed size, but supports replacing elements by index via `set` |
| `List.of(...)` | No | Unmodifiable list; calling `sort` throws `UnsupportedOperationException` |
| `stream.toList()` (Java 16+) | No | Returned list is unmodifiable |
| `Collections.unmodifiableList(...)` | No | View blocks mutating operations |

When unsure whether a source list is modifiable, **make a copy** first:

~~~java
List<String> sorted = new ArrayList<>(source);
sorted.sort(Comparator.naturalOrder());
~~~

This also preserves the order of `source`, avoiding side effects on data elsewhere. If the source may contain `null`, use a comparator wrapped with `nullsFirst`/`nullsLast` as shown above.

## 7. Creating a Sorted List Without Modifying the Original List

`List.sort` mutates the source data directly. If you only want to compute a new display result, create a copy or use a Stream:

~~~java
import java.util.Comparator;
import java.util.List;

public class StreamSortedDemo {
    public static void main(String[] args) {
        List<String> original = List.of("pear", "apple", "banana");

        List<String> sorted = original.stream()
                .sorted(Comparator.naturalOrder())
                .toList();

        System.out.println(original);
        System.out.println(sorted);
    }
}
~~~

Save `StreamSortedDemo.java` and run `javac -encoding UTF-8 StreamSortedDemo.java` then `java StreamSortedDemo`:

~~~text
[pear, apple, banana]
[apple, banana, pear]
~~~

`Stream.sorted` is an intermediate operation returning a new stream in the specified order. `toList()` (Java 16+) is a terminal operation producing the result list, and that list is **unmodifiable**. `original` remains unchanged.

Quick comparison:

- `list.sort(comparator)`: sorts a modifiable list in-place; the method returns `void`.
- `Collections.sort(list, comparator)`: also modifies the list in-place.
- `list.stream().sorted(comparator).toList()`: creates a result list without modifying the source; the result is unmodifiable.
- `new ArrayList<>(list)` then `sort`: creates an independent list **and** allows further modification after sorting.

Choose based on list ownership/mutability requirements, not just syntax brevity.

## 8. What Rules Must a Proper Comparator Obey?

A Comparator should define a consistent ordering:

1. **Antisymmetry of sign:** the sign of `compare(a, b)` must be the opposite of `compare(b, a)`.
2. **Transitivity:** if `a` comes before `b` and `b` comes before `c`, then `a` must come before `c`.
3. **Consistency on equality:** if `compare(a, b) == 0`, comparing `a` and `b` against any value `c` must yield compatible relations.
4. Avoid comparators with mutable state or dependence on timing/randomness during sorting.

A comparator that violates the contract can produce unpredictable ordering, and some sorting algorithms may throw `IllegalArgumentException` when detecting a comparison relation that breaks the contract.

**Distinguishing `equals` from `compare == 0`:** `String.CASE_INSENSITIVE_ORDER.compare("Apple", "apple") == 0`, yet `"Apple".equals("apple")` is `false`. For `List.sort`, both elements are retained; the list does not automatically remove duplicates according to the comparator. However, if that comparator is passed into `TreeSet` or `TreeMap`, `compare == 0` can cause two keys to be treated as the same key in the sorted set/map. When designing comparators for those collections, consider consistency with `equals` and business key policy.

### Stability and Performance

`List.sort` requires **stable** sorting: when the comparator considers two elements equal, their original relative order is preserved. Comparison cost and comparison count depend on list length, data distribution, and the comparator's operations. Sorting in general is typically analyzed at `O(n log n)` comparisons for standard cases, though string comparison may also scan multiple characters to find a difference.

For large datasets, avoid expensive transformations (such as repeated normalization or external data reads) inside each comparator invocation. You can precompute sort keys and sort by the prepared keys if that cost is significant. Avoid premature optimization when lists are small and the comparator is already clear.

## 9. Common Mistakes

**Mistake 1 — Assuming natural order means Vietnamese A–Z.** `compareTo` is UTF-16-based and unaware of alphabets/languages. Use `Collator` with an appropriate `Locale` for language-ordered display lists, and test on the actual JDK.

**Mistake 2 — Calling sort on List.of.** `List.of` does not allow content mutation. Create `new ArrayList<>(...)` or use `stream().sorted(...).toList()`.

**Mistake 3 — Having null elements while using naturalOrder.** If data permits `null`, explicitly place nulls first/last using `Comparator.nullsFirst` or `nullsLast`, or filter them out before sorting if business rules allow.

**Mistake 4 — Confusing natural order with case-insensitive order.** `Comparator.naturalOrder()` distinguishes `"Apple"` and `"apple"`; `String.CASE_INSENSITIVE_ORDER` may treat them as equal. When deterministic tie-breaking is needed, use `thenComparing(Comparator.naturalOrder())`.

**Mistake 5 — Placing reversed() in the wrong position.** `comparingInt(...).reversed().thenComparing(...)` reverses only the primary criterion, whereas `comparingInt(...).thenComparing(...).reversed()` reverses the entire composite order.

**Mistake 6 — Using toLowerCase() without a locale to build sort keys.** Case-conversion rules can vary by locale; conversion can increase character count, and lowercased keys do not necessarily reflect proper collation. If simple case-insensitive comparison is the goal, use `CASE_INSENSITIVE_ORDER`; if language-specific, use `Collator` with an explicit locale.

**Mistake 7 — Using subtraction to write a numeric Comparator.** Replace `a.length() - b.length()` with `Integer.compare(a.length(), b.length())` or `Comparator.comparingInt(String::length)`.

**Mistake 8 — Logically unstable Comparator.** Avoid comparators that return different values for the same pair of elements within a single sort; do not use random variables or unexpectedly mutable data as comparison keys.

**Mistake 9 — Wanting to keep the source unchanged yet calling List.sort.** `sort` mutates the existing list. Use a copy or `stream().sorted(...).toList()` when an independent result is needed.

**Mistake 10 — Confusing a comparator with Collection equality checks.** `List.sort` only reorders elements; it does not remove duplicates and does not change `String.equals`. `TreeSet` and `TreeMap`, by contrast, use the comparator to identify duplicate keys according to comparison order.

## 10. Practice Exercise

Given the list:

~~~java
List<String> names = new ArrayList<>(
        List.of("bob", "Amy", "ann", "BOB", "Joe"));
~~~

Predict the result after three independent sorts, each starting from the original data (create a new list for each operation):

1. `names.sort(Comparator.naturalOrder())`.
2. `names.sort(String.CASE_INSENSITIVE_ORDER)`.
3. `names.sort(Comparator.comparingInt(String::length).thenComparing(Comparator.naturalOrder()))`.

Self-check program:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SortPractice {
    public static void main(String[] args) {
        List<String> original = List.of("bob", "Amy", "ann", "BOB", "Joe");

        List<String> natural = new ArrayList<>(original);
        natural.sort(Comparator.naturalOrder());
        System.out.println("Natural: " + natural);

        List<String> insensitive = new ArrayList<>(original);
        insensitive.sort(String.CASE_INSENSITIVE_ORDER);
        System.out.println("Ignore case: " + insensitive);

        List<String> byLength = new ArrayList<>(original);
        byLength.sort(Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder()));
        System.out.println("Length: " + byLength);
    }
}
~~~

Save as `SortPractice.java` and run:

~~~bash
javac -encoding UTF-8 SortPractice.java
java SortPractice
~~~

Output:

~~~text
Natural: [Amy, BOB, Joe, ann, bob]
Ignore case: [Amy, ann, bob, BOB, Joe]
Length: [Amy, BOB, Joe, ann, bob]
~~~

In the third example, every name is three UTF-16 code units long, so the length criterion does not distinguish any elements; the natural-order tie-breaker determines the result, matching the first sort.

**Try extending:** add `"Bình"`, `"Binh"`, and `"Ánh"` and compare the output with `Comparator.naturalOrder()`, `String.CASE_INSENSITIVE_ORDER`, and `Collator.getInstance(Locale.forLanguageTag("vi-VN"))`. Do not extrapolate Vietnamese ordering from UTF-16; observe the output on the runtime you use.

## Checklist When Applying

- Is the list allowed to be modified? If not, make a copy or use `Stream.sorted`.
- Do you want UTF-16 code order, case-insensitive order, length order, or language order? Choose the right comparator.
- Are there `null` values? Specify `nullsFirst`/`nullsLast` handling or filter them intentionally.
- Are there multiple criteria? Use `comparingInt`, `thenComparing`, and place `reversed()` carefully.
- Can elements tie under the comparator? Decide whether a tie-breaker is needed while leveraging `List.sort`'s stability.
- Does the ordering affect `TreeSet`/`TreeMap` or need consistency across JDKs/locales? Check comparator, `equals`, and collation semantics before making it a data contract.

## Official References

- [Java SE 17 — List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator))
- [Java SE 17 — Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
- [Java SE 17 — String.compareTo and CASE_INSENSITIVE_ORDER](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — Collections.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [Java SE 17 — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator))
