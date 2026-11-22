# Comparator.comparing(), thenComparing(), and Reversing Order in Java

When sorting a list of objects, we often need multiple criteria: **department ascending, score descending, then name ascending**. Java provides `Comparator<T>` as a *comparison behavior* that can be passed into `List.sort(...)`, `Stream.sorted(...)`, or other APIs. The `Comparator.comparing(...)`, `thenComparing(...)`, and `reversed()` methods allow you to describe that order declaratively, leveraging lambdas and method references.

This lesson focuses on how to create and compose `Comparator` instances, especially **distinguishing between reversing a single criterion and reversing the entire chain of criteria**.

## 1. Fundamentals: How Does a Comparator Determine Order?

`Comparator<T>` is a functional interface with the abstract method:

~~~java
int compare(T left, T right);
~~~

The return value only needs to guarantee the sign:

- **Negative** if `left` comes before `right`.
- **Zero** if the two objects are equal according to the comparison criterion being used.
- **Positive** if `left` comes after `right`.

It does not need to return exactly `-1`, `0`, or `1`. For example, `String.compareTo` can return other negative/positive numbers.

`compare(left, right) == 0` means the two elements have **equal sort keys**, not necessarily `left.equals(right)`. Well-behaved comparators must adhere to sign antisymmetry, transitivity, and consistency when comparing triplets of elements. During a sort, key data should remain stable to avoid violating the comparison contract.

How to pass comparison behavior into an API:

~~~java
List<String> cities = new ArrayList<>(List.of("Hue", "Ha Noi", "Da Nang"));
cities.sort(Comparator.comparingInt(String::length));
~~~

The code snippet above requires importing `java.util.List`, `java.util.ArrayList`, and `java.util.Comparator`, and must be placed inside a method. `List.sort(...)` **modifies the order of the existing list**, whereas `Stream.sorted(...)` creates a new stream with the sorted order (without sorting the source itself).

## 2. Comparator.comparing(): Creating a Comparator from a Key Extractor

Common form:

~~~java
Comparator.comparing(keyExtractor)
~~~

`keyExtractor` is a `Function<T, U>` that extracts the **sort key** from an element `T`. The key type `U` must have a suitable natural order via `Comparable`, such as `String`, `Integer`, or `LocalDate`.

For example, given `record Member(String team, String name, int points, int age) {}`:

~~~java
Comparator<Member> byName = Comparator.comparing(Member::name);
Comparator<Member> byTeam = Comparator.comparing(m -> m.team());
~~~

`Member::name` is equivalent to the lambda `m -> m.name()`. With `byName.compare(a, b)`, the comparator extracts `a.name()` and `b.name()` and then compares the two keys according to the natural order of `String`. The default is **ascending**.

When the key does not have a suitable natural order or requires a different rule, use the second overload:

~~~java
Comparator.comparing(keyExtractor, keyComparator)
~~~

For example, sorting by name case-insensitively:

~~~java
Comparator<Member> byNameIgnoreCase =
        Comparator.comparing(Member::name, String.CASE_INSENSITIVE_ORDER);
~~~

Here, `String.CASE_INSENSITIVE_ORDER` compares the `String` key, **not** the entire `Member` object. For Vietnamese words, language-specific collation rules may require an appropriate `Collator`; the natural order of `String` is Unicode order, which does not guarantee the desired Vietnamese dictionary order.

### Using Primitive-Specialized Variants

If the key is `int`, `long`, or `double`, prefer:

~~~java
Comparator<Member> byPoints = Comparator.comparingInt(Member::points);
Comparator<Member> byAge = Comparator.comparingInt(Member::age);
~~~

The related methods are `comparingInt(ToIntFunction)`, `comparingLong(ToLongFunction)`, and `comparingDouble(ToDoubleFunction)`. They help avoid the boxing/unboxing of primitive keys that commonly occurs when using `comparing(Function)`.

For example, `Comparator.comparing(Member::points)` can also be used thanks to autoboxing from `int` to `Integer`, but `comparingInt(Member::points)` makes the intent clear and avoids creating boxed keys for that comparison.

## 3. thenComparing(): Adding Secondary Criteria in Priority Order

Multi-key sorting follows the *left-to-right comparison* principle (lexicographic ordering):

1. Compare the primary criterion.
2. **Only if the primary criterion is 0**, evaluate the first secondary criterion.
3. **Only if all preceding criteria are 0**, evaluate the next criterion.
4. If all criteria are 0, `compare(...)` returns 0.

Example:

~~~java
Comparator<Member> order = Comparator.comparing(Member::team)
        .thenComparing(Member::name)
        .thenComparingInt(Member::age);
~~~

This means **team ascending → name ascending → age ascending**. `thenComparing` does not sort separately a second time; it creates **a single composite comparator**, where each comparison can fall through to the next criterion if needed.

Common overloads:

| Syntax | How It Applies |
| --- | --- |
| `thenComparing(otherComparator)` | Uses another comparator for the same element type `T` when preceding criteria tie |
| `thenComparing(keyExtractor)` | Compares the secondary key using its natural order |
| `thenComparing(keyExtractor, keyComparator)` | Compares the secondary key using a custom comparator for the key type |
| `thenComparingInt(keyExtractor)` | `int` secondary key, without boxing |
| `thenComparingLong(keyExtractor)` | `long` secondary key |
| `thenComparingDouble(keyExtractor)` | `double` secondary key |

Because `thenComparing` returns a `Comparator<T>`, you can chain multiple calls into a pipeline. The order of calls determines **priority**: place the most important key first.

A comparator that expresses the order clearly is often easier to maintain than writing a long `compare` method with many `if` branches. However, an explicit `compare` method remains appropriate when comparison logic is complex and needs to handle special states.

## 4. Three Ways to Reverse Order and Their Differences

### 4.1. reversed(): Reverses the **Entire** Current Comparator

~~~java
Comparator<Member> byTeamThenAge =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::age);
Comparator<Member> completelyReversed = byTeamThenAge.reversed();
~~~

`completelyReversed` reverses the result of **all criteria in the composed comparator**: team descending and (when in the same team) age descending.

Comparison view:

~~~java
Comparator<Member> allDescending =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::age)
                  .reversed(); // Reverses both team AND age
~~~

`reversed()` is an instance method of `Comparator<T>`; it creates a comparator in the opposite direction of the comparator on which it is called.

### 4.2. Reversing Only One Key While Building the Chain

Suppose the requirement is **team ascending, points descending, name ascending**. If you write:

~~~java
Comparator<Member> incorrectForRequirement =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::points)
                  .thenComparing(Member::name)
                  .reversed();
~~~

then team, points, and name are all reversed, **which does not meet the requirement**. To reverse only points, create a separate comparator for the points key and attach it as a secondary criterion:

~~~java
Comparator<Member> correctOrder =
        Comparator.comparing(Member::team)
                  .thenComparing(Comparator.comparingInt(Member::points).reversed())
                  .thenComparing(Member::name);
~~~

Notice the parentheses: `reversed()` is **inside** the argument to `thenComparing(...)`, because we only want to reverse the points comparator. The equivalent approach for an object key is:

~~~java
Comparator<Member> orderByTeamAndNameDescending =
        Comparator.comparing(Member::team)
                  .thenComparing(Member::name, Comparator.reverseOrder());
~~~

In this case, `Comparator.reverseOrder()` is a comparator for the **`String` key** of `name`, causing names to be descending within each team. Team remains ascending.

### 4.3. Comparator.reverseOrder() vs. reversed()

- `Comparator.reverseOrder()` is a **static** method that returns a comparator using the **reversed natural order** for `Comparable` values (such as `String`, `Integer`). It does not require an existing comparator.
- `someComparator.reversed()` is an **instance** method that reverses the result of `someComparator`, even if the original comparator compares multiple keys or has custom rules.
- `Comparator.naturalOrder()` is a comparator for natural ordering, which clarifies intent when directly comparing `Comparable` objects.

Example:

~~~java
List<String> tags = new ArrayList<>(List.of("b", "a", "c"));
tags.sort(Comparator.reverseOrder());
// tags == [c, b, a]
~~~

This snippet requires importing `List`, `ArrayList`, and `Comparator`, and placing it inside a method.

## 5. Complete Demo Program, Java 17+

Put the entire following snippet into the file **`ComparatorChainDemo.java`**. The data has multiple elements with the same team and points so you can see `thenComparing` in action.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorChainDemo {
    record Member(String team, String name, int points, int age) {}

    public static void main(String[] args) {
        List<Member> members = new ArrayList<>(List.of(
                new Member("Backend", "An", 90, 24),
                new Member("Frontend", "Binh", 75, 22),
                new Member("Backend", "Binh", 90, 30),
                new Member("Backend", "Chi", 70, 28),
                new Member("Frontend", "An", 75, 26),
                new Member("Backend", "An", 90, 21)
        ));

        Comparator<Member> byPriority =
                Comparator.comparing(Member::team)
                        .thenComparing(Comparator.comparingInt(Member::points).reversed())
                        .thenComparing(Member::name)
                        .thenComparingInt(Member::age);

        System.out.println("TEAM ASC, POINTS DESC, NAME ASC, AGE ASC:");
        members.sort(byPriority);
        members.forEach(ComparatorChainDemo::print);

        System.out.println("REVERSE ENTIRE ORDER:");
        members.sort(byPriority.reversed());
        members.forEach(ComparatorChainDemo::print);

        System.out.println("REVERSED NATURAL STRINGS:");
        List<String> tags = new ArrayList<>(List.of("b", "a", "c"));
        tags.sort(Comparator.reverseOrder());
        System.out.println(tags);
    }

    static void print(Member member) {
        System.out.printf("%s | %s | %d | %d%n",
                member.team(), member.name(), member.points(), member.age());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac ComparatorChainDemo.java
java ComparatorChainDemo
~~~

**Exact output:**

~~~text
TEAM ASC, POINTS DESC, NAME ASC, AGE ASC:
Backend | An | 90 | 21
Backend | An | 90 | 24
Backend | Binh | 90 | 30
Backend | Chi | 70 | 28
Frontend | An | 75 | 26
Frontend | Binh | 75 | 22
REVERSE ENTIRE ORDER:
Frontend | Binh | 75 | 22
Frontend | An | 75 | 26
Backend | Chi | 70 | 28
Backend | Binh | 90 | 30
Backend | An | 90 | 24
Backend | An | 90 | 21
REVERSED NATURAL STRINGS:
[c, b, a]
~~~

Analysis:

- All `Backend` entries come before `Frontend` because the `team` key is compared in ascending order.
- Within `Backend`, the `points=90` group comes before `points=70` because only the **points key** is reversed.
- The two `Backend / An / 90` elements are distinguished by the final `age` key: `21` then `24`.
- When calling `byPriority.reversed()`, the ordering relationships are **completely reversed**, so `Frontend` comes first; within each group, the order of the remaining keys is also reversed.
- `Comparator.reverseOrder()` sorts the three strings `a, b, c` in descending natural order.

The code uses `record`, available since Java 16, so it runs validly on Java 17+. `List.of(...)` returns a structurally unmodifiable list; `new ArrayList<>(...)` is needed to use `List.sort(...)` directly.

## 6. Using a Comparator in Behavioral APIs

`Comparator` is data representing **comparison behavior**, so it can be passed as an API parameter. For example, a method that accepts a caller-chosen comparator:

~~~java
static <T> List<T> sortedCopy(List<T> source, Comparator<? super T> comparator) {
    return source.stream().sorted(comparator).toList();
}
~~~

This is a **method snippet** that must be placed inside a class with `List` and `Comparator` imported. The result of `Stream.toList()` is a list that does not support structural modifications; you should not call `sort` on that result.

Callers can reuse a single sorting rule in multiple places:

~~~java
Comparator<Member> byNameThenAge =
        Comparator.comparing(Member::name)
                  .thenComparingInt(Member::age);

members.sort(byNameThenAge);            // Mutates the existing list
List<Member> copy = members.stream()
        .sorted(byNameThenAge)
        .toList();                      // Creates a new result
~~~

`copy` is the result list; sorting the stream does not require modifying the order of `members`. This is an important benefit of behavioral APIs: the processing logic can be independent of the criteria provided by the caller.

`Collections.sort(list, comparator)` also accepts a `Comparator`; with modern APIs, `list.sort(comparator)` is usually more concise.

## 7. Null Keys and Null Objects: Explicit Handling

**`Comparator.comparing(Member::name)` does not handle `null` keys by default.** When encountering a `null` name, natural comparison can throw a `NullPointerException`. If the application allows missing names, explicitly specify where the missing key should go:

~~~java
Comparator<Member> byNullableName =
        Comparator.comparing(
                Member::name,
                Comparator.nullsLast(Comparator.naturalOrder())
        );
~~~

With the comparator above, a Member with `name == null` comes **after** Members with non-null names. `Comparator.nullsFirst(...)` does the opposite; these two methods are wrapper comparators for intentional null handling.

**Distinguish between a null key and a null element itself.** `nullsLast` inside `comparing` only handles the `name` key value, and does not guard the `Member::name` call when the `Member` element itself is null. To handle null elements:

~~~java
Comparator<Member> nullableMembers =
        Comparator.nullsLast(Comparator.comparing(Member::name));
~~~

Here, **null elements** come last. If both the element and the key can be null, combine both layers:

~~~java
Comparator<Member> bothNullCases =
        Comparator.nullsLast(
                Comparator.comparing(
                        Member::name,
                        Comparator.nullsLast(Comparator.naturalOrder())
                )
        );
~~~

When descending order with nulls is needed, pay attention to the order in which `reversed()` is applied: reversing the comparator after wrapping with `nullsLast` can move nulls to the front. If you want **non-nulls descending, nulls still last**, place `reverseOrder()` inside:

~~~java
Comparator<Member> nameDescNullLast =
        Comparator.comparing(
                Member::name,
                Comparator.nullsLast(Comparator.reverseOrder())
        );
~~~

The examples in this section are illustrative code snippets placed in a class with `Member` and appropriate imports.

## 8. Common Pitfalls, Comparison Contract, and Best Practices

### Reversing the Wrong Scope

`comparing(A).thenComparing(B).reversed()` reverses **both A and B**; `comparing(A).thenComparing(comparing(B).reversed())` reverses only **B**. Place `reversed()` in the right spot in the expression.

### Returning the Subtraction of Two Numbers as the Compare Result

Do not write:

~~~java
Comparator<Member> unsafe = (a, b) -> a.points() - b.points();
~~~

`int` subtraction can overflow, breaking the comparison sign. Use `Integer.compare(a.points(), b.points())` or `Comparator.comparingInt(Member::points)` for safety. When you need to reverse the order, use `reversed()`, without manually flipping the sign via subtraction.

### Confusing a Comparison Result of 0 with Object Equality

If comparing only by `name`, two Members with different `age` values can still cause `compare` to return 0. `List.sort` and `Stream.sorted` are stable sorts on ordered sources: elements that compare equal according to the comparator preserve their original relative order. However, `TreeSet` and `TreeMap` use the comparator to determine duplicate keys; `compare(a, b) == 0` causes them to treat two keys as equivalent even though `equals` may differ. If you need to distinguish entities, add an appropriate tie-breaker, such as a unique ID.

### Distinguishing Natural Order from Custom Comparison

`Comparator.comparing(Member::name)` uses the natural order of `String`, which is case-sensitive; `comparing(Member::name, String.CASE_INSENSITIVE_ORDER)` replaces the key comparison rule. Do not apply English alphabetical comparison order to natural-language sorting requirements without considering locale.

### Keys Mutating During a Sort

A comparator should be stable and free of side effects. Do not make a key extractor update data, call network APIs, generate random numbers, or mutate the fields used for comparison. If a key is expensive to compute, consider precomputing/caching it outside the comparator and controlling consistency.

### Assuming Every List Can Be Sorted in Place

`List.of(...)` and lists from `Stream.toList()` do not support reordering via `sort`. Create `new ArrayList<>(source)` before sorting in place; or use `source.stream().sorted(comparator).toList()` when you want a new result.

### Inconsistent or Omitted Secondary Criteria

For example, comparing only by `team` then `points` can leave multiple Members with the same keys. If the application needs deterministic result ordering even when the input has different orders, add tie-breakers such as `thenComparing(Member::name).thenComparingInt(Member::age)` or a unique ID. Do not add a tie-breaker just to change semantics if the requirement wants elements to be treated as equal.

### Nulls and Reversing Order

`Comparator.reverseOrder()` does not automatically handle `null`. Use `nullsFirst` or `nullsLast` at the appropriate level, and double-check the null policy after calling `reversed()`. Additionally, `Comparator.comparing(...)` will not be able to extract a key from a null object without an outer wrapper comparator.

## 9. Quick Reference for Choosing

| Requirement | Comparator Pattern |
| --- | --- |
| Single ascending key | `Comparator.comparing(Member::name)` |
| Ascending `int` key | `Comparator.comparingInt(Member::age)` |
| Single key with custom comparator | `Comparator.comparing(Member::name, String.CASE_INSENSITIVE_ORDER)` |
| Multiple ascending keys | `Comparator.comparing(Member::team).thenComparing(Member::name)` |
| Primary key ascending, secondary key descending | `Comparator.comparing(Member::team).thenComparing(Comparator.comparingInt(Member::points).reversed())` |
| Reverse an entire comparator | `existingComparator.reversed()` |
| Reverse natural order of `Comparable` elements | `Comparator.reverseOrder()` |
| Nullable key, nulls last | `Comparator.comparing(Member::name, Comparator.nullsLast(Comparator.naturalOrder()))` |

The deciding factor is **position in the chain**: `comparing` defines the first key, `thenComparing` appends subsequent keys in priority order, and `reversed` reverses the comparator on which it is called. Writing comparators with the right structure makes sorting behavior clear, reusable, and easy to verify.