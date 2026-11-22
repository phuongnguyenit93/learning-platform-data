# Comparator.comparingInt() and Handling Null Values in Java

When sorting objects in Java, `Comparator.comparingInt()` is a concise and expressive choice if the sort key is an `int` value. However, an element in the list may be `null`, or the field used as the key may be of type `Integer` and currently hold `null`. These two situations are **different**, because `comparingInt()` uses an extractor function that returns a primitive `int`, which cannot represent a “missing value” state.

This article explains the signature and underlying mechanism, how to place `Comparator.nullsFirst()` / `nullsLast()` in the right position, how to sort nullable `Integer` keys, and the pitfalls when combining `thenComparing()` or `reversed()`. Examples use Java 17+ syntax.

## 1. What behavior does `comparingInt()` accept?

The general signature of the API is:

~~~java
public static <T> Comparator<T> comparingInt(
        java.util.function.ToIntFunction<? super T> keyExtractor);
~~~

This is an **illustrative signature**, not a standalone compilable Java file. `ToIntFunction<T>` is a functional interface with the method:

~~~java
int applyAsInt(T value);
~~~

Therefore, `Comparator.comparingInt(Person::age)` creates a comparator that takes two `Person` instances, calls the function to get each object's age, and compares the two `int` values using `Integer.compare` semantics (without subtracting the two numbers to get the difference). Smaller numeric values come first in ascending order.

- `comparingInt()` **creates a comparator**; it does not sort the dataset itself yet.
- `Person::age` or `p -> p.age()` is the key extraction behavior, invoked by the comparator whenever a comparison is needed.
- The key is `int`, so there is no need to allocate an `Integer` just to represent the extractor's result.
- The extractor function may be called **multiple times** during a single sort. It should be kept pure, fast, and free of side effects.
- If the extractor has to dereference a `null` element, or has to unbox a `null` `Integer`, a `NullPointerException` can be thrown.

### Basic example: non-null primitive field

Create the file `PrimitiveComparatorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class PrimitiveComparatorDemo {
    record Candidate(String name, int score) {}

    public static void main(String[] args) {
        List<Candidate> candidates = new ArrayList<>(List.of(
                new Candidate("An", 9),
                new Candidate("Chi", 5),
                new Candidate("Bình", 5)
        ));

        candidates.sort(
                Comparator.comparingInt(Candidate::score)
                        .thenComparing(Candidate::name)
        );

        System.out.println(candidates.stream()
                .map(Candidate::name)
                .toList());
    }
}
~~~

~~~bash
javac --release 17 PrimitiveComparatorDemo.java
java PrimitiveComparatorDemo
~~~

Output:

~~~text
[Bình, Chi, An]
~~~

The primary key is `score` in ascending order; when two scores are both 5, `thenComparing(Candidate::name)` compares names in the natural order of `String`. In this example, all objects and names are non-null.

## 2. You must identify exactly which object can be null

There are two common levels of nullability:

| Situation | Example | Consequence if using `comparingInt()` directly | How to handle |
| --- | --- | --- | --- |
| **The element being compared is null** | The list contains `null` instead of a `Candidate` | `Candidate::score` has no receiver to call | Wrap the *entire object comparator* with `Comparator.nullsFirst(...)` or `Comparator.nullsLast(...)`. |
| **The element exists, but the key is null** | `candidate.score()` returns a `null` `Integer` | Java must unbox `Integer` to `int` and may throw `NullPointerException` | Use `Comparator.comparing(..., Comparator.nullsFirst/Last(...))`, or define an explicit default value rule. |

**Wrapping the outermost comparator only handles null at the level of the object being compared.** It does not protect against a null key inside a non-null object. Conversely, wrapping the key's comparator does not handle a null object if the code still calls a getter on the null object.

Do not rely on the assumption that the data “currently has no nulls”: from databases, JSON, maps, user input sources, legacy data, or when transformed across multiple pipelines, the null policy must be consistent at API boundaries.

## 3. Case A: null element, `int` key is always valid

If the list may contain a `null` object, while every non-null object has an `int` key, place `nullsFirst` or `nullsLast` **around the object comparator**.

~~~java
Comparator<Candidate> byScoreWithNullLast =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score));
~~~

The snippet above is in a context where `Candidate` and `import java.util.Comparator` already exist.

How it works when the comparator receives two inputs:

1. Both are null: returns 0, meaning they are considered equal according to this sort key.
2. Only one side is null: places that side first with `nullsFirst` or last with `nullsLast`.
3. Neither is null: delegates to the inner comparator, at which point the extractor is safely called with respect to object-level nulls.

Standalone example, file `NullElementSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullElementSortDemo {
    record Candidate(String name, int score) {}

    public static void main(String[] args) {
        List<Candidate> items = new ArrayList<>(Arrays.asList(
                new Candidate("An", 9),
                null,
                new Candidate("Chi", 4)
        ));

        Comparator<Candidate> order = Comparator.nullsFirst(
                Comparator.comparingInt(Candidate::score)
        );
        items.sort(order);

        for (Candidate candidate : items) {
            System.out.println(candidate == null
                    ? "<null>"
                    : candidate.name() + "=" + candidate.score());
        }
    }
}
~~~

~~~bash
javac --release 17 NullElementSortDemo.java
java NullElementSortDemo
~~~

Output:

~~~text
<null>
Chi=4
An=9
~~~

`Comparator.nullsFirst` accepts a comparator that can be used for non-null elements. The wrapping itself does not modify the data and does not replace `null` with a dummy object.

Note: `List.of(...)` **does not allow** null elements, and the returned list does not support in-place sorting either. Therefore, the example uses `new ArrayList<>(Arrays.asList(...))` to create a list that can contain null and allows calling `sort`.

## 4. Case B: the key is `Integer` and may be null

If a `score` field is declared as `Integer` (the wrapper type) instead of `int`, the following call can **compile** but fail when comparing an object with a null score:

~~~java
// Snippet intentionally demonstrates an error, not a standalone program:
record Candidate(String name, Integer score) {}
Comparator<Candidate> unsafe =
        Comparator.comparingInt(candidate -> candidate.score());
// candidate.score() is Integer; must auto-unbox to int.
// If score() returns null, the unboxing operation will throw NullPointerException.
~~~

Even if you wrap it with `Comparator.nullsLast(unsafe)`, nulls of *Candidate* are handled, but `Candidate.score() == null` can still throw an error.

To preserve null as a distinct meaningful key, use `Comparator.comparing()` with a comparator for the **reference key type**:

~~~java
Comparator<Candidate> byNullableScore =
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

The difference is:

- `comparingInt()` accepts `ToIntFunction<T>`, forcing the key to be `int`.
- `comparing()` accepts a function returning a reference key type, such as `Integer`, and can accept a dedicated comparator for that key.
- `Comparator.nullsLast(Comparator.naturalOrder())` here sorts **the `Integer` values**, placing `null` `Integer` after all non-null numbers.
- If `Candidate` itself can also be null, you still need **another `nullsLast`/`nullsFirst` layer on the outside**.

### Complete example: both the object and the key can be null

Create the file `NullableScoreSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullableScoreSortDemo {
    record Candidate(String name, Integer score) {}

    public static void main(String[] args) {
        List<Candidate> candidates = new ArrayList<>(Arrays.asList(
                new Candidate("An", 8),
                new Candidate("Bình", null),
                null,
                new Candidate("Chi", 3),
                new Candidate("Dũng", 8)
        ));

        Comparator<Candidate> order = Comparator.nullsLast(
                Comparator.comparing(
                        Candidate::score,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                    .thenComparing(Candidate::name)
        );
        candidates.sort(order);

        for (Candidate candidate : candidates) {
            System.out.println(candidate == null
                    ? "<null>"
                    : candidate.name() + "=" + candidate.score());
        }
    }
}
~~~

~~~bash
javac --release 17 NullableScoreSortDemo.java
java NullableScoreSortDemo
~~~

Output:

~~~text
Chi=3
An=8
Dũng=8
Bình=null
<null>
~~~

The comparator has **two layers of null policy**. The inner layer protects the `Integer score` key; the outermost layer protects the `Candidate` object itself. Among non-null elements, scores are compared in ascending order, and two people with the same score of 8 are tie-broken by name.

If the name can also be null, then `.thenComparing(Candidate::name)` is unsafe when two scores are equal. Choose a policy for the name as well:

~~~java
// Illustrative snippet placed in a context where Candidate already exists:
Comparator<Candidate> safeAllFields = Comparator.nullsLast(
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(
                Candidate::name,
                Comparator.nullsLast(Comparator.naturalOrder()))
);
~~~

This shows that you need to check **each key** and **the root object** in the sorting contract, not just add a single `nullsLast` anywhere.

## 5. If you must use `comparingInt()` with a nullable key

You can define your own rule to substitute a `null` `Integer` value with some `int` number, so that the extractor always returns a primitive:

~~~java
// Illustration: only use when score() can be null but Candidate is non-null.
Comparator<Candidate> byScoreWithFallback =
        Comparator.comparingInt(candidate ->
                candidate.score() == null ? -1 : candidate.score());
~~~

If valid scores are non-negative numbers, `-1` can express “no score yet, sort first”. However, **this is a business decision**, not an automatic behavior of `comparingInt`. If `-1` is also a valid score, elements with a real score of `-1` and elements with a null score will have the same key; they cannot be distinguished by the primary comparator.

Similarly, using `Integer.MAX_VALUE` to push nulls to the end is not always safe if a valid value can equal `Integer.MAX_VALUE`. If you truly need to keep null distinct from every number, prefer `Comparator.comparing(..., Comparator.nullsLast(...))`.

Another option is to **filter out records missing a score** if business requirements allow it:

~~~java
// Illustration in a Candidate stream context:
List<Candidate> ranked = candidates.stream()
        .filter(java.util.Objects::nonNull)
        .filter(candidate -> candidate.score() != null)
        .sorted(Comparator.comparingInt(candidate -> candidate.score()))
        .toList();
~~~

The result no longer contains null elements or elements missing a score. This is a change to the dataset rather than a way to place nulls first/last. The filtering requirement must be explicitly stated before applying it.

## 6. Pitfall of combining `thenComparing()` with `nullsFirst/nullsLast`

The structure of a multi-key comparator matters more than a single `nullsFirst` call.

**Unsafe if elements can be null:**

~~~java
// Illustrative snippet that fails if both inputs are null:
Comparator<Candidate> unsafeOrder =
        Comparator.nullsLast(Comparator.comparingInt(Candidate::score))
                  .thenComparing(Candidate::name);
~~~

Why? When both objects are null, the `nullsLast` layer returns 0. Then `thenComparing` continues to compare the secondary key, calling `Candidate::name` on null and causing a `NullPointerException`. Even though when only one element is null, the initial comparator returns non-zero and avoids the secondary key, the **two-nulls** case is still enough to make the structure above wrong.

**Safer when placing the null-guard layer on the outside:**

~~~java
// Illustrative snippet that works for non-null Candidate with a valid name:
Comparator<Candidate> safeOrder =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score)
                          .thenComparing(Candidate::name));
~~~

In this structure, any comparison involving a `null` `Candidate` is resolved by the outermost layer, and only when both objects are non-null is the comparator with primary and secondary keys invoked. If the secondary key itself is nullable, you must provide a null-safe comparator at the secondary key itself, as in section 4.

For a multi-key chain, build the complete comparator for **non-null** objects first, then wrap `nullsFirst` or `nullsLast` at the outermost layer.

## 7. The `reversed()` pitfall: reversing the null order too if placed in the wrong spot

`Comparator.reversed()` reverses the order of the **entire comparator** it is applied to, including the position of nulls if that position has already been defined inside the comparator.

~~~java
// Candidate has an int score; snippets are for illustration only:
Comparator<Candidate> nullsLastAndScoreDesc =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score).reversed());

Comparator<Candidate> nullsFirstAfterReverse =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score)).reversed();
~~~

With the first expression, `reversed()` only reverses the score of non-null elements, so **nulls remain at the end**. With the second expression, the entire “score ascending, nulls last” comparator is reversed, so **nulls move to the front** and scores are descending.

Similarly for a nullable `Integer` key:

~~~java
// Keep score == null last when sorting scores in descending order:
Comparator<Candidate> scoreDescNullLast =
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.reverseOrder()));
~~~

If the object itself can also be null, you can wrap this result with `Comparator.nullsLast(...)`. Decide separately on the ascending/descending policy for the **key**, the policy for a **null key**, and the policy for a **null object**, then compose them in the right layers.

## 8. In-place sorting, streams, and stability

The following usages both apply the created comparator:

~~~java
// Illustration inside a method that already has List<Candidate> candidates and Comparator<Candidate> order:
candidates.sort(order);                // Modifies the order of a mutable List.
List<Candidate> copy = candidates.stream()
        .sorted(order)
        .toList();                     // New result list, does not modify the source.
~~~

A few notes:

- `List.sort` requires a list that supports modifying elements; `List.of(...)` is an immutable collection, so calling `sort` on it will throw `UnsupportedOperationException`.
- For an ordered source list, `Stream.sorted` is stable according to encounter order; `List.sort` is also a stable sort. Two elements for which the comparator returns 0 preserve their original relative order under those conditions.
- For an *unordered* stream, `Stream.sorted` does not provide the same stability guarantee.
- A comparator may be called multiple times and not in a fixed order. Avoid lambdas that read frequently changing state or cause side effects; compute stable key values before sorting if needed.
- Do not use `a.score() - b.score()` as an integer comparator because it can overflow and violate ordering; `comparingInt` uses a safer integer comparison.
- Do not catch `NullPointerException` from a comparator and treat it as equal by default: that hides comparison contract bugs and easily produces inconsistent ordering.

## 9. Testing the null policy with boundary data

When building a comparator for production, test at least the following cases:

| Dataset | Expectation to verify |
| --- | --- |
| Two objects with different scores | Ascending/descending order by score is correct. |
| Two objects with the same score | Secondary key (if any) works correctly. |
| One null object and one valid object | `nullsFirst`/`nullsLast` places them in the right position. |
| Both objects are null | No `thenComparing` dereferences a null object. |
| One or two null `Integer` keys | Ordering of null keys is correct, no auto-unboxing error. |
| Null secondary key such as name | A null-safe comparator is present for the secondary key. |
| Negative numbers, 0, `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | Does not rely on subtraction or a sentinel that could collide with valid data. |
| Reversing order with `reversed()` | Null policy still matches requirements. |

If the comparator is used long-term in `TreeSet`, `TreeMap`, or an ordered tree structure, ensure the comparison relation is consistent, antisymmetric, and transitive. Returning 0 for two different objects can cause comparator-based structures to treat them as the same key; a unique secondary key may be needed. A comparator is not required to be consistent with `equals`, but if it is not, you must understand the consequences for sorted sets/maps.

## 10. Quick selection rules

| Actual data | Recommended expression |
| --- | --- |
| Non-null object, `int` key | `Comparator.comparingInt(Person::age)` |
| Nullable object, `int` key | `Comparator.nullsLast(Comparator.comparingInt(Person::age))` |
| Non-null object, nullable `Integer` key | `Comparator.comparing(Person::age, Comparator.nullsLast(Comparator.naturalOrder()))` |
| Both object and `Integer` key can be null | `Comparator.nullsLast(Comparator.comparing(Person::age, Comparator.nullsLast(Comparator.naturalOrder())))` |
| Secondary key and null objects | Wrap `Comparator.nullsLast(...)` **after** chaining all `thenComparing(...)` |
| Descending score but null must be last | Reverse the inner key comparator, then wrap `nullsLast` by layer. |

**Remember:** `Comparator.comparingInt()` is ideal for **non-null `int` keys**. `Comparator.nullsFirst()/nullsLast()` must be placed at the right level: around the **object** comparator to guard against null elements, and around the **key** comparator when using `comparing()` with a nullable `Integer` key. Clearly distinguish the null policy before adding secondary keys and reversing order.
