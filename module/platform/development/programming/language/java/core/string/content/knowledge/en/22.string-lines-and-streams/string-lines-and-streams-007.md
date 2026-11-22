# Filtering, Counting, and Transforming Data with IntStream in Java String

## Lesson Objectives

A `String` can produce an `IntStream` to process each character unit as an integer, allowing you to filter elements to keep, count elements matching a condition, compute sums, or transform data. After this lesson, you will be able to:

- Use `String.chars()` and `String.codePoints()` for their intended purposes, understanding the difference between a **UTF-16 code unit** and a **Unicode code point**.
- Build pipelines with `filter`, `map`, `mapToObj`, and terminal operations such as `count`, `sum`, and `collect`.
- Convert processed code points back into a `String` using `StringBuilder.appendCodePoint`.
- Recognize pitfalls involving Unicode, counting, single-use streams, and case transformations.

## 1. What Is IntStream, and Why Does String Return IntStream?

`java.util.stream.IntStream` is a *primitive stream*: it represents a sequence of `int` values, supporting pipeline operations without boxing each element into an `Integer`. This is a stream for processing data **in memory**, not an `InputStream` for reading bytes from a file or network.

`String` provides two key methods:

~~~java
IntStream utf16Units = text.chars();
IntStream unicodePoints = text.codePoints();
~~~

- `chars()` produces a stream of the string's **UTF-16 code units**; each value is widened from `char` to `int`. A Unicode supplementary character (such as a multi-unit emoji in UTF-16) becomes two separate surrogate elements.
- `codePoints()` produces a stream of **Unicode code points**; two consecutive valid surrogates are combined into a single code point. Regular code units remain single elements. This is usually the right choice for filtering or checking characters with methods like `Character.isLetter(int)` and `Character.isDigit(int)`.
- Neither method automatically segments “characters visible on screen” (*grapheme clusters*). One visible character can consist of multiple code points, such as a base letter plus a combining mark or an emoji joined by a Zero Width Joiner.

When working strictly with ASCII, the outputs of `chars()` and `codePoints()` usually match; for multilingual content, decide based on the unit you need to process.

### Example Verifying UTF-16 and Code Points

Save to `UnicodeStreamDemo.java`:

~~~java
import java.util.stream.Collectors;

public class UnicodeStreamDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println(text.length());
        System.out.println(text.chars().count());
        System.out.println(text.codePoints().count());

        String values = text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));
        System.out.println(values);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 UnicodeStreamDemo.java
java UnicodeStreamDemo
~~~

Output:

~~~text
4
4
3
U+0041, U+1F600, U+0042
~~~

`"A😀B"` has three Unicode code points but four UTF-16 code units, because `😀` is stored as a surrogate pair. `String.length()` and `chars().count()` both reflect the code unit count in this example; `codePoints().count()` reflects the code point count. **Do not call all three results “the number of user-visible characters”.**

## 2. What Steps Make Up a Pipeline?

A pipeline typically consists of three parts:

~~~text
String.codePoints()      // source: IntStream of code points
  .filter(...)            // intermediate op: keeps values matching a condition
  .map(...)               // intermediate op: transforms int -> int
  .count()                // terminal op: returns long
~~~

Intermediate operations such as `filter`, `map`, `distinct`, `sorted`, and `limit` generally create a new stream describing what will be processed without immediately running over all data. Terminal operations such as `count`, `sum`, `forEach`, or `collect` trigger the pipeline (subject to valid Stream library optimizations). Each stream can be consumed only once.

| Operation | Characteristic | Example in This Lesson |
| --- | --- | --- |
| `filter(IntPredicate)` | Keeps `int` values when the predicate returns `true` | Filtering digits with `Character::isDigit` |
| `map(IntUnaryOperator)` | Transforms each `int` into another `int` | Converting code points to uppercase |
| `mapToObj(IntFunction<R>)` | Transforms an `int` into an object | Formatting a code point as `"U+...."` |
| `distinct()` | Removes duplicate `int` values | Getting unique code points |
| `sorted()` | Sorts integer values | Sorting by code point value |
| `count()` | Returns element count as `long` | Counting digits |
| `sum()` | Computes total as `int` | Summing ASCII digits after numeric conversion |
| `findFirst()` | Finds the first element, returning `OptionalInt` | Finding the first digit code point |
| `collect(...)` | Accumulates results using a mutable container | Building a `StringBuilder` |

`filter` does not modify the original `String`: `String` is *immutable*. If you need a new string as output, you must collect the remaining elements into another structure or object.

## 3. Filtering, Counting, and Summing Digits

Suppose the input is `"a1B2c3😀"`. We want to count digit code points, count letter code points, and compute the sum of **the ASCII digit values**.

Save to `FilterCountDemo.java`:

~~~java
public class FilterCountDemo {
    public static void main(String[] args) {
        String text = "a1B2c3😀";

        long digitCount = text.codePoints()
                .filter(Character::isDigit)
                .count();

        long letterCount = text.codePoints()
                .filter(Character::isLetter)
                .count();

        int asciiDigitSum = text.codePoints()
                .filter(cp -> cp >= '0' && cp <= '9')
                .map(cp -> cp - '0')
                .sum();

        System.out.println("Digits: " + digitCount);
        System.out.println("Letters: " + letterCount);
        System.out.println("ASCII digit sum: " + asciiDigitSum);
    }
}
~~~

Run with `javac -encoding UTF-8 FilterCountDemo.java` and `java FilterCountDemo`:

~~~text
Digits: 3
Letters: 3
ASCII digit sum: 6
~~~

Step by step:

1. `codePoints()` produces a stream of `a`, `1`, `B`, `2`, `c`, `3`, `😀` (represented as `int`s).
2. `filter(Character::isDigit)` keeps only the three digits, and `count()` yields `3L` (type `long`).
3. `filter(Character::isLetter)` keeps `a`, `B`, `c`, so the result is also `3L`.
4. The filter `cp >= '0' && cp <= '9'` deliberately restricts to **ASCII 0–9**. Then `map(cp -> cp - '0')` converts the codes of `'1'`, `'2'`, `'3'` to numeric values 1, 2, 3, and `sum()` yields `6`.

**Be careful:** `Character.isDigit(int)` can recognize digits from many scripts beyond ASCII. Therefore, never blindly apply `cp - '0'` to all code points accepted by `isDigit`. If you need the numeric value of a Unicode digit, use `Character.digit(cp, 10)` and handle `-1` when there is no value in the requested radix.

For example, `codePoints().filter(Character::isDigit).count()` is an operation that **counts code points classified as digits**; it does not automatically tell you a numeric value, the number of characters in a string, or validate that the entire input is numeric. To validate an entire string, use `String.matches` with an appropriate pattern or check all code points and length rules separately.

## 4. Transforming and Keeping Characters to Build a New String

`map` on an `IntStream` returns one `int` for each input element. When working with Unicode code points, you must construct the output string with an operation that understands **code points**, rather than casting `int` to `char`.

For example, suppose you want to extract letter code points and convert them to uppercase. Save `TransformStreamDemo.java`:

~~~java
public class TransformStreamDemo {
    public static void main(String[] args) {
        String text = "a1B2c3😀";

        String result = text.codePoints()
                .filter(Character::isLetter)
                .map(Character::toUpperCase)
                .collect(
                        StringBuilder::new,
                        (builder, cp) -> builder.appendCodePoint(cp),
                        StringBuilder::append)
                .toString();

        System.out.println(result);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TransformStreamDemo.java
java TransformStreamDemo
~~~

Output:

~~~text
ABC
~~~

Meaning of the steps:

- `filter(Character::isLetter)` removes digits and the emoji from the example, keeping `a`, `B`, `c`.
- `map(Character::toUpperCase)` converts each code point to its uppercase code point equivalent if one exists.
- `collect(supplier, accumulator, combiner)` creates a `StringBuilder`, appends each code point via `appendCodePoint`, and provides a combiner to merge builders (if the pipeline runs in parallel); `toString()` yields the final string.

Why not use `(char) cp`? Because that cast keeps only the low 16 bits and can corrupt characters outside the Basic Multilingual Plane. `StringBuilder.appendCodePoint(int)` appends the proper one or two UTF-16 code units for a valid code point.

**Limitation of code-point uppercasing:** `Character.toUpperCase(int)` returns only **one** code point per input and does not handle all locale-dependent casing rules or one-to-many character expansions. If the task is to convert an **entire string** to uppercase for a given language, consider `text.toUpperCase(locale)` and a Unicode normalization policy rather than assuming the pipeline above always produces the same result.

## 5. Using mapToObj When the Output Is No Longer an int

`mapToObj` is useful when each code point must be represented as an object, such as a label string or data record. Example:

~~~java
import java.util.stream.Collectors;

public class CodePointListDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        String names = text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", "));

        System.out.println(names);
    }
}
~~~

Save as `CodePointListDemo.java`, compile and run with `javac -encoding UTF-8 CodePointListDemo.java` then `java CodePointListDemo`. Output:

~~~text
U+0041, U+1F600, U+0042
~~~

Here `mapToObj` converts each `int` into a `String`; then `Collectors.joining(", ")` joins the parts into one string. This approach works well when you need to display metadata for each code point. If you only need to rebuild a Unicode string from filtered/transformed code points, the `collect(StringBuilder::new, ...appendCodePoint..., StringBuilder::append)` approach in the previous section avoids creating many small intermediate strings.

## 6. When Should You Use chars(), codePoints(), or IntStream.range()?

All three approaches are useful, but they answer different questions:

| Source | Unit Iterated | Best Suited For |
| --- | --- | --- |
| `text.chars()` | UTF-16 code unit (`char` as `int`) | ASCII processing, operations explicitly based on `char` or code units |
| `text.codePoints()` | Unicode code point (`int`) | Filtering/counting letters, digits, Unicode characters, and `Character`-based transforms |
| `IntStream.range(0, text.length())` | `char` index 0 to `length() - 1` | When you need the **UTF-16 position** (offset) of characters for `charAt` |

Example finding UTF-16 indices of letters in an ASCII string:

~~~java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class IndexStreamDemo {
    public static void main(String[] args) {
        String text = "a1B2";

        String positions = IntStream.range(0, text.length())
                .filter(i -> Character.isLetter(text.charAt(i)))
                .mapToObj(i -> i + ":" + text.charAt(i))
                .collect(Collectors.joining(", "));

        System.out.println(positions);
    }
}
~~~

Save `IndexStreamDemo.java`, run `javac -encoding UTF-8 IndexStreamDemo.java` and `java IndexStreamDemo`. Output:

~~~text
0:a, 2:B
~~~

This pattern works for `"a1B2"` because all data is ASCII. With Unicode supplementary characters, `charAt(i)` returns only one surrogate of the pair and index `i` is a **code unit offset**, not a code point index. When you need code point offsets, look at `String.offsetByCodePoints`, `String.codePointAt`, or an offset-aware traversal loop. Do not equate a code unit index with the position of the “Nth character” in displayed text.

### Counting Code Points Is Not Counting Grapheme Clusters

For example, the character `é` can be represented by one code point `U+00E9` or two code points `U+0065` and `U+0301` (letter `e` with a combining mark). `codePoints().count()` can give different counts for two strings that look identical. For emoji with combining components, a single displayed glyph can also consist of multiple code points.

If a product requirement is to count “user-visible characters”, truncate strings at grapheme boundaries, or enforce character limits in an input field, an `IntStream` over code points alone is not enough. You need an appropriate Unicode segmenter and should consider text normalization for your specific problem.

## 7. Pipelines Run Once, and Counting Should Not Rely on Side Effects

A common mistake is saving an `IntStream` and trying to reuse it:

~~~java
// Error illustration: not a complete program.
var stream = "A1B2".codePoints();
long count = stream.filter(Character::isDigit).count();
// stream.count(); // Error: stream has already been consumed, throws IllegalStateException.
~~~

Create a **new stream** for each terminal operation:

~~~java
String text = "A1B2";
long digitCount = text.codePoints()
        .filter(Character::isDigit)
        .count();
long letterCount = text.codePoints()
        .filter(Character::isLetter)
        .count();
~~~

Do not put side effects inside `filter`/`map` just to count invocations. The Stream library can optimize pipelines; for instance, `count()` on a sized source can return the result without executing intermediate operations that do not affect the count. Use the return value of the terminal operation to determine output, rather than assuming every intermediate operation runs once per element.

`forEach` also does not guarantee encounter order on a parallel stream; if encounter order truly matters, use `forEachOrdered`. For typical string character processing, prefer sequential, concise, readable pipelines before considering parallelization.

## 8. Additional Techniques: Finding, Deduplicating, and Limiting

Some practical needs beyond filtering/counting/transforming:

~~~java
import java.util.OptionalInt;

public class MoreIntStreamDemo {
    public static void main(String[] args) {
        String text = "a1b2a3";

        OptionalInt firstDigit = text.codePoints()
                .filter(Character::isDigit)
                .findFirst();
        System.out.println(firstDigit.isPresent()
                ? Character.toString(firstDigit.getAsInt())
                : "None");

        long uniqueLetters = text.codePoints()
                .filter(Character::isLetter)
                .distinct()
                .count();
        System.out.println(uniqueLetters);
    }
}
~~~

Save `MoreIntStreamDemo.java`, then run `javac -encoding UTF-8 MoreIntStreamDemo.java` and `java MoreIntStreamDemo`. Output:

~~~text
1
2
~~~

`findFirst()` returns `OptionalInt`, because no matching element might exist; use `isPresent`/`orElse`/`ifPresent` as appropriate instead of calling `getAsInt()` unconditionally. `distinct()` removes duplicate code points; in the example there are two distinct letters, `a` and `b`. This operation compares **code point values** and does not automatically merge canonically equivalent Unicode forms or perform case-insensitive comparison.

`limit(n)` can cap the number of elements passing through the stream, but limiting to `n` **code points** is not necessarily limiting to `n` UI-rendered characters. With `sorted()`, ordering is numeric code point order, not locale-sensitive alphabetical order.

## 9. Common Mistakes

**1. Choosing chars() for multilingual text and treating each element as one Unicode character.** Surrogate pairs are split in two, so filtering with `Character.isLetter(int)` or reconstructing via `char` cast can fail. Use `codePoints()` when processing code points.

**2. Calling count() and assuming it is the number of characters on screen.** `chars().count()` is the UTF-16 code unit count; `codePoints().count()` is the Unicode code point count; neither inherently counts grapheme clusters.

**3. Confusing count with sum.** `filter(...).count()` counts matching elements; `filter(...).map(...).sum()` adds the transformed values. `count()` returns `long`; `IntStream.sum()` returns `int` and can overflow if values are large.

**4. Converting code points via a char cast.** `(char) cp` can lose the upper bits. Use `appendCodePoint` or `Character.toChars(cp)` when building strings.

**5. Applying cp - '0' to all Unicode digits.** Simple subtraction only works assuming consecutive ASCII digit codes. For Unicode digits, use `Character.digit(cp, 10)` and handle characters without a numeric value.

**6. Trying to reuse a consumed stream.** After `count()`, `sum()`, `collect()`, or `forEach()`, call `text.codePoints()` again to create a new pipeline.

**7. Equating toUpperCase(code point) with toUpperCase(Locale).** Per-code-point conversion may miss locale-specific variants or one-to-many uppercase expansions. Choose the API based on whether you need **character-level** or **text-level** conversion.

**8. Overusing streams for trivial logic.** For checking a single position or a fixed operation, a loop or specialized `String` API can be clearer. Streams shine when expressing chains of filters, transformations, combinations, or aggregations.

**9. Assuming filtering letters keeps combining marks attached to letters.** A combining mark may fail `Character.isLetter` and be dropped, altering the text. Before filtering Unicode characters, define your policy for combining marks, normalization, and graphemes.

## 10. Self-Check Exercises

Given the string `"A7b0C3"`, predict the following expressions:

~~~java
String value = "A7b0C3";

long digits = value.codePoints()
        .filter(Character::isDigit)
        .count();

int sum = value.codePoints()
        .filter(cp -> cp >= '0' && cp <= '9')
        .map(cp -> cp - '0')
        .sum();

long differentLetters = value.codePoints()
        .filter(Character::isLetter)
        .map(Character::toLowerCase)
        .distinct()
        .count();
~~~

**Answers:** `digits = 3` because of `7`, `0`, `3`; `sum = 10`; `differentLetters = 3` because the three letters `a`, `b`, `c` are distinct after converting to lowercase.

Extension exercise: modify the filter to accept only ASCII letters `A-Z` or `a-z`; next, test a string containing `😀` and a letter with a combining mark, then compare `length()`, `chars().count()`, and `codePoints().count()`. Observe the differences to choose the appropriate processing unit.

## Project Application Checklist

1. Determine whether the input is ASCII, UTF-16 code units, Unicode code points, or grapheme clusters.
2. Choose the right source: `chars()`, `codePoints()`, or `IntStream.range(...)` depending on the unit.
3. Write clear `filter` predicates, avoiding equating ASCII digits with all Unicode digits.
4. When using `map` on code points, keep values in valid ranges; when building strings, use `appendCodePoint`.
5. Choose the appropriate terminal operation: `count` for element counts, `sum` for totals, `findFirst` for searching, `collect` for string assembly.
6. Use a fresh stream for each terminal operation; test empty strings, supplementary characters, combining marks, and inputs that violate assumptions.

## Official Documentation

- [Java SE 17 — String.chars() and String.codePoints()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Java SE 17 — StringBuilder.appendCodePoint(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#appendCodePoint(int))
- [Java SE 17 — Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)
