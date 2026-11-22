# `String.compareTo()` and Lexicographical Order by `char` Value in Java

## 1. What Problem Does `compareTo()` Solve?

When you need to know whether two strings have **equal content**, Java provides `String.equals(...)`. Many problems, however, also require knowing which string **comes before or after** another to sort names, keywords, identifiers, or lists.

The `java.lang.String` class provides:

```java
public int compareTo(String anotherString)
```

This is a **lexicographical comparison** of two strings by Java's `char` values (UTF-16 code units). The method scans from left to right, finding the first position where the two strings differ. If all shared positions match, the shorter string comes first.

Examples:

```java
System.out.println("apple".compareTo("banana")); // Negative number
System.out.println("java".compareTo("java"));     // 0
System.out.println("zebra".compareTo("apple"));   // Positive number
```

Short snippets in this article are **illustrative code inside a method**, except for the complete example with a `public class` and `main` method presented later.

The most important thing when reading the return value is the **sign** of the integer:

| Value of `left.compareTo(right)` | Conclusion |
|---|---|
| Less than `0` | `left` comes **before** `right` in `String` order |
| Equal to `0` | Both strings have the same sequence of `char` values |
| Greater than `0` | `left` comes **after** `right` in `String` order |

**Do not check only `compareTo(...) == -1` or `== 1`.** The method can return `-32`, `2`, `5`, or any other negative/positive integer. When you only need ordering, compare against **`0`**.

## 2. Syntax and API Contract

Basic syntax:

```java
String left = "cat";
String right = "car";

int result = left.compareTo(right);
System.out.println(result); // 2
```

- `left` is the `String` object **receiving the call**.
- `right` is the `String` argument **compared against** `left`.
- The result is an `int`; its value carries **ordering** meaning, not a character index in the string.
- `compareTo` **does not modify** either string because `String` is immutable.
- The argument must be a non-`null` `String`. Passing `null` throws `NullPointerException`. Calling the method when the receiver variable is `null` also throws `NullPointerException`.

`String` implements the `Comparable<String>` interface. Thus, Java can use `compareTo` as the **natural ordering** of `String`, such as when calling `Arrays.sort` or `Collections.sort` without supplying a custom `Comparator`.

### Compared to `equals(...)` and `==`

```java
String first = new String("Java");
String second = "Java";

System.out.println(first.equals(second));    // true: same content
System.out.println(first.compareTo(second)); // 0: same content, equal order
System.out.println(first == second);         // false: different references
```

For two non-`null` `String` objects, the condition `a.compareTo(b) == 0` is equivalent to `a.equals(b)` for **string content**. However:

- Use **`equals`** to answer "Is the content equal?".
- Use **`compareTo`** to answer "Which string comes before/after?".
- **`==`** on two `String` variables checks same object reference, not ordering, and is unsuitable for comparing content.

## 3. Left-to-Right `char`-by-`char` Comparison Algorithm

Let the two strings be `left` and `right`.

**Rule 1 – Find the first differing position.** Java inspects each `char` value at indices `0`, `1`, `2`, ... up to the end of their common prefix. If it encounters an index `k` where:

```java
left.charAt(k) != right.charAt(k)
```

then the result has the value:

```java
left.charAt(k) - right.charAt(k)
```

Subtraction here uses the numeric values of the two `char`s. The **sign** determines the order. Characters after the first differing position **no longer affect** the comparison.

**Rule 2 – If the entire common prefix matches.** If one string is a prefix of the other (or both are identical), the result is:

```java
left.length() - right.length()
```

Therefore, the shorter string comes first, and strings with the same length and identical `char` sequence return `0`.

### Example: First Differing Character

```java
"cat".compareTo("car")
```

```text
Index:    0   1   2
String 1: c   a   t
String 2: c   a   r
                  ^
            First difference

't' = 116, 'r' = 114
Result: 116 - 114 = 2
```

Hence `"cat".compareTo("car")` returns `2`. Reversing the call:

```java
"car".compareTo("cat") // -2
```

The result is negative because at the first differing position, `'r'` is less than `'t'`.

### Example: One String Is a Prefix of the Other

```java
"app".compareTo("apple") // -2
"apple".compareTo("app") // 2
"same".compareTo("same") // 0
```

`"app"` is a prefix of `"apple"`. All 3 shared positions match, so the result is `3 - 5 = -2`, **not the position of the letter `l`**.

With empty strings:

```java
"".compareTo("")      // 0
"".compareTo("Java")  // -4
"Java".compareTo("")  // 4
```

The empty string comes before every non-empty string because length `0` is less than their lengths.

## 4. This Order Is Based on `char` Values, Not a Vietnamese Dictionary

In Java, the `char` type represents **one UTF-16 code unit** with an unsigned integer value from `0` to `65535` (`U+0000` to `U+FFFF` at the code-unit level). The natural ordering of `String` is determined from this sequence of `char` values.

Some easy-to-remember values:

| Character | Decimal `char` Value | Note |
|---|---:|---|
| `'0'` | 48 | Digit as a character |
| `'9'` | 57 | Still a character, not the integer 9 |
| `'A'` | 65 | Uppercase Latin letter |
| `'Z'` | 90 | Uppercase Latin letter |
| `'a'` | 97 | Lowercase Latin letter |
| `'z'` | 122 | Lowercase Latin letter |

Therefore:

```java
"A".compareTo("a")     // -32: 65 - 97
"a".compareTo("A")     // 32: 97 - 65
"9".compareTo("A")     // -8: 57 - 65
"Z".compareTo("a")     // -7: 90 - 97
```

You cannot conclude that `"apple"` always comes before `"Banana"` according to natural-language intuition. Under `String.compareTo`, `"Banana"` comes before `"apple"` because the first character `'B'` (66) is less than `'a'` (97).

### Distinguishing Number Comparison from Numeric-String Comparison

```java
System.out.println("10".compareTo("2")); // -1
System.out.println(Integer.compare(10, 2)); // 1
```

The string `"10"` comes **before** `"2"` because the first character `'1'` (49) is less than `'2'` (50). By contrast, the integer `10` is greater than `2`.

When you need to sort **numbers**, convert to an appropriate numeric type and compare numerically; when you need "natural" sorting of codes like `file2` and `file10`, you need a `Comparator` that splits out numeric parts. `String.compareTo` does not recognize numeric segments inside text.

## 5. Complete Java 17+ Example and Stdout

Create **`StringCompareToDemo.java`** with the following content:

```java
import java.util.Arrays;

public class StringCompareToDemo {
    public static void main(String[] args) {
        System.out.println("cat/car = " + "cat".compareTo("car"));
        System.out.println("car/cat = " + "car".compareTo("cat"));
        System.out.println("app/apple = " + "app".compareTo("apple"));
        System.out.println("apple/app = " + "apple".compareTo("app"));
        System.out.println("java/java = " + "java".compareTo("java"));
        System.out.println("A/a = " + "A".compareTo("a"));
        System.out.println("10/2 = " + "10".compareTo("2"));

        String[] words = {"banana", "Apple", "apple", "Banana", "app"};
        Arrays.sort(words);
        System.out.println("sorted = " + Arrays.toString(words));

        String supplementary = "😀";
        String bmpPrivateUse = "\uE000";
        System.out.println("UTF16 order sign = "
                + Integer.signum(supplementary.compareTo(bmpPrivateUse)));
        System.out.println("Code point order sign = "
                + Integer.signum(Integer.compare(
                        supplementary.codePointAt(0),
                        bmpPrivateUse.codePointAt(0))));
    }
}
```

Run on JDK 17 or later in the directory containing the file:

```bash
javac -encoding UTF-8 StringCompareToDemo.java
java StringCompareToDemo
```

**Stdout:**

```text
cat/car = 2
car/cat = -2
app/apple = -2
apple/app = 2
java/java = 0
A/a = -32
10/2 = -1
sorted = [Apple, Banana, app, apple, banana]
UTF16 order sign = -1
Code point order sign = 1
```

**Explanation of the output:**

1. `"cat"` and `"car"` differ first at `'t'` and `'r'`, returning `2` and `-2` when reversed.
2. `"app"` is a prefix of `"apple"`, so the result is the length difference `3 - 5 = -2`.
3. The two `"java"` literals are identical, returning `0`.
4. `'A'` (65) compared to `'a'` (97) gives `-32`; `"10"` compared to `"2"` compares the leading digits `'1'` and `'2'`, giving `-1`.
5. `Arrays.sort(words)` uses the natural ordering of `String`: items starting with uppercase letters are placed before items starting with lowercase letters in this dataset.
6. The last two lines reveal a UTF-16 quirk: comparing by `char` units can sometimes give a **different order** than comparing Unicode code point values. Section 7 explains this in detail.

## 6. Using `compareTo` for Sorting and Branching

### Checking Order with `if`

```java
String left = "alpha";
String right = "beta";

int order = left.compareTo(right);

if (order < 0) {
    System.out.println("left comes before right");
} else if (order > 0) {
    System.out.println("left comes after right");
} else {
    System.out.println("both strings are equal");
}
```

Comparing against `0` is the proper approach. If you only need the sign, you can use `Integer.signum(order)` to normalize to `-1`, `0`, or `1`.

### Natural Sorting with `Arrays.sort`

```java
String[] labels = {"zebra", "Apple", "banana"};
java.util.Arrays.sort(labels);
System.out.println(java.util.Arrays.toString(labels));
// [Apple, banana, zebra]
```

`Arrays.sort` uses the elements' `compareTo` when the array has type `String[]` and no `Comparator` is specified. Similarly, `java.util.Collections.sort(list)` sorts a mutable `List<String>` in natural order; `list.sort(null)` also uses natural order.

If you want to **reverse** the order:

```java
java.util.Arrays.sort(
        labels,
        java.util.Comparator.reverseOrder()
);
```

Note that `Comparator.reverseOrder()` on strings also reverses the UTF-16 natural ordering; it does not turn sorting into a user-language dictionary sort.

### Using with Ordered Collections

`TreeSet<String>` or `TreeMap<String, ...>` can use the natural ordering of `String` when no comparator is provided. The ordering rule affects both **lookup and key equivalence** in those structures.

```java
java.util.Set<String> set = new java.util.TreeSet<>();
set.add("apple");
set.add("Apple");

System.out.println(set); // [Apple, apple]
```

These two strings differ according to `compareTo`, so they are kept as two separate elements in a default `TreeSet`.

## 7. Unicode Details: `char` Does Not Always Equal a Visible Character

This is the most important point in the phrase **"lexicographical order by `char` value"**.

Java's `String` uses UTF-16 code units. A Unicode code point in the BMP is typically represented by one `char`; however, code points greater than `U+FFFF` (such as many emojis) use a **surrogate pair** of two `char`s.

Example:

```java
String smile = "😀";

System.out.println(smile.length()); // 2
System.out.println(smile.codePointCount(0, smile.length())); // 1
```

Therefore, `compareTo` compares **UTF-16 code units**, not always the integer values of Unicode code points directly.

### A Potentially Surprising Example

- The emoji `"😀"` has Unicode code point `U+1F600`, represented in UTF-16 by the pair `U+D83D U+DE00`.
- The character at `U+E000` is a BMP code point, represented by a `char` with value `U+E000`.
- Comparing code points as integers, `U+1F600` is **greater than** `U+E000`.
- Yet `String.compareTo` inspects the **first** `char`: `U+D83D` is **less than** `U+E000`, so `"😀".compareTo("\uE000")` returns a **negative** number.

That is why the last two lines of the demo in Section 5 output signs `-1` and `1` respectively.

**Unicode takeaway:** `String.compareTo` ordering is deterministic and consistent over UTF-16 code-unit sequences, but it must not be interpreted as "code point ordering for all Unicode characters", much less dictionary order in Vietnamese or another language.

### Composed Characters and Normalization

Two strings can look identical while containing different code point sequences. For example, `é` can be represented by a single code point `U+00E9` or by `e` (`U+0065`) plus a combining acute accent (`U+0301`).

```java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed));    // false
System.out.println(composed.compareTo(decomposed)); // Positive number
```

At the very first code unit, `U+00E9` (233) is greater than `U+0065` (101), so `compareTo` returns a positive number. If business logic treats both representations as the same text, you can **normalize Unicode** with `java.text.Normalizer` before comparing. Choose NFC or NFD according to requirements and apply it consistently to all sides.

## 8. Case-Insensitive Comparison and Language-Aware Comparison

### `compareToIgnoreCase` Solves a Different Problem

When you want to compare strings while **ignoring case differences** using Java's case-insensitive rules, you can use:

```java
System.out.println("JAVA".compareToIgnoreCase("java")); // 0
```

However, `compareToIgnoreCase` is **not** a natural-language sorter. Complex Unicode case conversions, language-specific rules, and diacritics may require separate handling. Do not assume that ignoring case also strips Vietnamese diacritics, unifies all character styles, or produces alphabetical order for a specific language.

For case-insensitive sorting:

```java
String[] words = {"b", "A", "a"};
java.util.Arrays.sort(words, String.CASE_INSENSITIVE_ORDER);
```

This comparator uses Java's case-insensitive comparison rules. For distinct strings treated as equal by the comparator, understand stability guarantees or add a secondary tie-breaker if business requirements demand a unique deterministic order.

### `Collator` for Language-Specific Ordering

For personal names, Vietnamese words, UI labels, or content that must follow a specific language's rules, consider `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Arrays;
import java.util.Locale;

class VietnameseSortingExample {
    public static void main(String[] args) {
        String[] names = {"Đào", "An", "Ân", "Ánh"};
        Collator vi = Collator.getInstance(Locale.forLanguageTag("vi-VN"));

        Arrays.sort(names, vi);
        System.out.println(Arrays.toString(names));
    }
}
```

This is a **standalone** illustrative program (a non-`public` class can still run when compiled in `VietnameseSortingExample.java`), though this article does not assert a single fixed stdout line: exact ordering can depend on locale collation data and Java version configuration. `Collator` has settings such as sensitivity to diacritics, case, and comparison *strength* levels that must be chosen per requirements.

`compareTo` fits when you want **Java's natural `char` ordering**; `Collator` fits when **language-specific** ordering is required. These are two different contracts.

## 9. `null`, `Comparator`, and Consistency

With a nullable reference variable, calling `compareTo` directly is unsafe:

```java
String value = null;
// value.compareTo("Java");  // NullPointerException
// "Java".compareTo(null);   // NullPointerException
```

If your problem allows `null` in a list, define an explicit ordering rule using `Comparator`:

```java
java.util.Comparator<String> order =
        java.util.Comparator.nullsFirst(
                java.util.Comparator.naturalOrder()
        );

System.out.println(order.compare(null, "Java")); // Negative number
System.out.println(order.compare("Java", null)); // Positive number
System.out.println(order.compare(null, null));   // 0
```

`naturalOrder()` uses `String.compareTo`; `nullsFirst(...)` adds the rule placing `null` before valid strings.

When writing a custom comparator for ordered structures like `TreeSet` or `TreeMap`, pay attention to **equivalence under the comparator**: two values for which the comparator returns `0` can be treated as the same element/key even if their `equals` returns `false`. For example, `String.CASE_INSENSITIVE_ORDER.compare("A","a") == 0`, while `"A".equals("a")` is `false`. In a `TreeSet` using that comparator, only one of the two values can be stored as the representative of the equivalence group.

Natural `String.compareTo` is **consistent with `equals`**, so this mismatch does not occur when comparing `String`s with the default natural comparator.

## 10. Common Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| `if (a.compareTo(b) == 1)` | A positive return value does not have to be `1` | `if (a.compareTo(b) > 0)` |
| Treating `compareTo` as `equals` | `compareTo` returns an `int` for ordering | Use `equals` when only testing equality |
| Thinking `"10"` comes after `"2"` | Strings are compared `char`-by-`char` from left to right | Convert to numbers or use a number-aware comparator |
| Thinking lowercase always precedes uppercase | `'A'` has a smaller value than `'a'` | Understand UTF-16 ordering, or choose another comparator |
| Thinking comparing by `char` is always comparing by code point | Emojis can consist of two UTF-16 code units | Understand code units and the rules you need |
| Thinking `compareTo` order is Vietnamese dictionary order | The API does not use language rules | Use an appropriate `Collator` when sorting names/words |
| Calling `text.compareTo(null)` | A `null` argument throws an exception | Validate input or use a null-handling comparator |
| Using `==` to test word equality | `==` compares references, not text | Use `equals` or `compareTo(...) == 0` |

## 11. Self-Check Exercises

**Question 1.** What value does `"dog".compareTo("dot")` return?

**Answer:** `'g'` (103) minus `'t'` (116) equals `-13`. The first two characters match, so the third character is compared.

**Question 2.** Is `"car".compareTo("carpet")` negative, zero, or positive?

**Answer:** **Negative**, specifically `3 - 6 = -3`, because `"car"` is a prefix of `"carpet"` and is shorter.

**Question 3.** Why does `"20".compareTo("100")` return a positive number even though the number `20` is smaller than `100`?

**Answer:** Comparing the first characters `'2'` (50) and `'1'` (49) gives `+1`; this is string ordering, not numeric comparison.

**Question 4.** Fix the following condition to check whether `a` comes before `b`:

```java
if (a.compareTo(b) == -1) {
    System.out.println("a comes before b");
}
```

**Answer:** Replace `== -1` with `< 0`. Any negative value carries the same ordering meaning.

**Question 5.** If two strings have the same content but are two distinct `String` objects, what does `compareTo` return?

**Answer:** `0`, because `compareTo` inspects the `char` sequence of the **content**, not object identity.

**Question 6.** When sorting Vietnamese names for user display, should you use `compareTo` by default?

**Answer:** No, if business requirements expect Vietnamese alphabetical order. `compareTo` only provides UTF-16 `char` ordering; consider `Collator` and appropriate locale settings.

## 12. Knowledge Summary

`String.compareTo(other)` traverses two strings from left to right by **UTF-16 `char` code units**. If there is a first differing position, the result has the sign of the difference between the two `char` values there; if the entire shared prefix matches, the result is the difference in lengths. **Negative / 0 / positive** mean before / equal / after in `String`'s natural ordering, respectively.

This rule lets Java sort strings deterministically, yet it **does not understand numbers, does not ignore case, does not follow Vietnamese dictionary order**, and differs notably from Unicode code-point order on supplementary characters. Choose `equals` to check content, `compareTo` or the natural comparator to sort by UTF-16, and `Collator` when human-language dictionary order is needed.
