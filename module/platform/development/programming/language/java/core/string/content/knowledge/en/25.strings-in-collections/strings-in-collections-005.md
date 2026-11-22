# Case-Insensitive Comparator and Its Relationship with equals When Storing Strings in Collections

## 1. Problem and Goal

When putting Java strings into collections, we often want to sort **case-insensitively**. Java provides `String.CASE_INSENSITIVE_ORDER`, a `Comparator<String>` for that purpose. However, an important trap arises when this comparator is used as **the rule for detecting duplicate keys** in `TreeSet` and `TreeMap`:

> **`compare(a, b) == 0` does not imply `a.equals(b)`.**

Example with `"Java"` and `"java"`:

- `"Java".equals("java")` is `false` because `String.equals` compares content case-sensitively.
- `"Java".equalsIgnoreCase("java")` is `true`.
- `String.CASE_INSENSITIVE_ORDER.compare("Java", "java")` is `0`: the two strings are equivalent **according to the comparator**.
- `"Java".compareToIgnoreCase("java")` is also `0`.

If you are only sorting for display, that behavior is usually what you want. If you use it to decide **which elements are allowed to exist** in a set or **which keys count as the same key**, the consequence can be losing a casing variant.

This lesson clarifies the relationship between `Comparator`, `String.equals`, `equalsIgnoreCase`, and how collections use them.

## 2. String Comparisons to Distinguish

| API | Result / Meaning | Case-sensitive? |
| --- | --- | --- |
| `a.equals(b)` | Whether two strings have identical content under `String.equals` | Yes |
| `a.equalsIgnoreCase(b)` | Checks equivalence ignoring case using `String` rules | No |
| `a.compareTo(b)` | Natural-order comparison; returns negative, 0, or positive | Yes |
| `a.compareToIgnoreCase(b)` | Order comparison ignoring case | No |
| `String.CASE_INSENSITIVE_ORDER.compare(a,b)` | Corresponding `Comparator<String>` performing case-insensitive comparison | No |

`Comparator.compare(a,b)` returns a **negative** value if `a` precedes `b`, **0** if equivalent under the comparator, and **positive** if `a` follows `b`. When testing, do not depend on the exact magnitude of negative/positive numbers; rely only on the **sign of the result**.

With `String.CASE_INSENSITIVE_ORDER`, the result aligns with `compareToIgnoreCase`. Two strings differing in case can compare as 0 even though `equals` returns `false`. This is called a comparator **inconsistent with equals**.

Crucial point: `equalsIgnoreCase` is a separate test on `String`; it **does not change** how `String.equals` or `hashCode` behaves. Passing a comparator to one collection does not mean other collection types automatically adopt that equivalence rule.

## 3. Why Does Consistency with equals Matter?

By Java convention, a comparator is **consistent with equals** if, for all suitable objects `a` and `b`:

~~~text
compare(a, b) == 0   if and only if   a.equals(b) == true
~~~

For two strings with different casing like `"Java"` and `"java"`, a case-insensitive comparator violates this condition:

~~~text
String.equals:                  false
String.CASE_INSENSITIVE_ORDER:      0
~~~

A comparator that is inconsistent with equals **can still sort validly** and is accepted by `TreeSet`/`TreeMap`. However, `SortedSet`/`SortedMap` in general require a comparator consistent with equals to uphold all expectations of the `Set`/`Map` contracts. Otherwise, the set or map can behave differently from `HashSet`/`HashMap` when users assume every collection detects duplicates identically to `equals`.

**Main point to remember:** `TreeSet` and `TreeMap` algorithms rely on **`compare(...) == 0` to determine key equivalence**. By contrast, `HashSet` and `HashMap` use `equals` combined with the key's `hashCode`. The two collection families can end up holding different numbers of elements for the same input.

## 4. How Do TreeSet and HashSet Differ?

The following is an **illustrative code snippet** that can be placed inside `main` after importing `java.util.*`:

~~~java
Set<String> hash = new HashSet<>();
hash.add("Java");
hash.add("java");
hash.add("JAVA");
// hash.size() == 3

Set<String> tree = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
tree.add("Java");
tree.add("java");
tree.add("JAVA");
// tree.size() == 1
// tree.contains("JAVA") == true
~~~

With `HashSet`, the three strings have different content under `equals` and are treated as three distinct elements; `HashSet` does not sort elements.

With `TreeSet`, the three strings compare as 0 under the case-insensitive comparator, so only one representative element is stored. Typically the first successfully added element is kept: if `"Java"` is added first, adding `"java"` or `"JAVA"` does not replace the stored string content. Calling `contains("JAVA")` returns `true` because it uses the tree's equivalence rule; this **does not prove** that the string `"JAVA"` itself is stored as a separate object.

If the business requirement is "a case-insensitive keyword list where each word appears only once," `TreeSet<>(String.CASE_INSENSITIVE_ORDER)` may be exactly what is desired. If you need to store **both variants** `"Java"` and `"java"`, that comparator is unsuitable for key uniqueness.

## 5. TreeMap and HashMap: Equivalent Keys Can Overwrite Values

Similarly with `TreeMap`:

~~~java
TreeMap<String, Integer> map =
        new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

map.put("Java", 1);
map.put("java", 2);

// map.size() == 1
// map.get("JAVA") == 2
// map.firstKey().equals("Java") == true
~~~

The second `put` does not create an independent key because the comparator says `"Java"` and `"java"` are equivalent. The value associated with the existing key is **replaced from 1 to 2**. In this case, the key object/string kept in the tree remains `"Java"`, the key from the first insertion. Looking up `"JAVA"` still retrieves the value because `TreeMap` also uses the comparator for lookup.

Conversely, in `HashMap<String,Integer>`, the keys `"Java"` and `"java"` differ according to `equals`; two entries can coexist, and `get("JAVA")` returns `null` unless an entry matching `"JAVA"` exactly exists.

**Design implication:** before using `TreeMap`/`TreeSet`, clarify whether "duplicate key" is defined by **`String.equals`** or by **case-insensitive comparison**. This is a choice about **identity rules**, not merely display ordering.

## 6. Complete Java 17+ Code for Verification

Create the file **CaseInsensitiveComparatorDemo.java**:

~~~java
import java.util.*;

public class CaseInsensitiveComparatorDemo {
    private static int passed;

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
        passed++;
    }

    public static void main(String[] args) {
        Comparator<String> insensitive = String.CASE_INSENSITIVE_ORDER;
        String first = "Java";
        String second = "java";

        check(insensitive.compare(first, second) == 0, "compare");
        check(first.compareToIgnoreCase(second) == 0, "compareToIgnoreCase");
        check(first.equalsIgnoreCase(second), "equalsIgnoreCase");
        check(!first.equals(second), "equals distinguishes case");

        Set<String> hash = new HashSet<>();
        hash.add("Java");
        hash.add("java");
        hash.add("JAVA");
        check(hash.size() == 3, "HashSet uses equals/hashCode");

        NavigableSet<String> folded = new TreeSet<>(insensitive);
        folded.add("Java");
        folded.add("java");
        folded.add("JAVA");
        check(folded.size() == 1, "TreeSet comparator equality");
        check(folded.contains("JAVA"), "TreeSet contains by comparator");

        NavigableMap<String, Integer> treeMap = new TreeMap<>(insensitive);
        treeMap.put("Java", 1);
        treeMap.put("java", 2);
        check(treeMap.size() == 1, "TreeMap key equivalence");
        check(treeMap.get("JAVA") == 2, "TreeMap lookup");
        check(treeMap.firstKey().equals("Java"), "original key retained");

        Comparator<String> insensitiveThenExact =
                String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder());
        TreeSet<String> distinct = new TreeSet<>(insensitiveThenExact);
        distinct.add("Java");
        distinct.add("java");
        distinct.add("JAVA");
        check(distinct.size() == 3, "tie breaker keeps distinct keys");
        check(distinct.toString().equals("[JAVA, Java, java]"),
                "tie breaker ordering");
        check(insensitiveThenExact.compare(first, second) != 0,
                "not comparator-equal if !equals");

        List<String> orderedList = new ArrayList<>(List.of("b", "A", "a", "B"));
        orderedList.sort(insensitive);
        check(orderedList.equals(List.of("A", "a", "b", "B")),
                "List.sort stable with ties");

        check(insensitive.compare("I", "\u0131") == 0,
                "Unicode case matching differs from locale conventions");

        System.out.println("equals=" + first.equals(second));
        System.out.println("ignoreCaseCompare=" + insensitive.compare(first, second));
        System.out.println("HashSet.size=" + hash.size());
        System.out.println("TreeSet.size=" + folded.size());
        System.out.println("TreeMap.size=" + treeMap.size());
        System.out.println("TreeMap.get(JAVA)=" + treeMap.get("JAVA"));
        System.out.println("TieBreakerSet=" + distinct);
        System.out.println("SortedList=" + orderedList);
        System.out.println("PASS: " + passed + " checks");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CaseInsensitiveComparatorDemo.java
java CaseInsensitiveComparatorDemo
~~~

Exact output:

~~~text
equals=false
ignoreCaseCompare=0
HashSet.size=3
TreeSet.size=1
TreeMap.size=1
TreeMap.get(JAVA)=2
TieBreakerSet=[JAVA, Java, java]
SortedList=[A, a, b, B]
PASS: 15 checks
~~~

The program verifies 15 assertions via `check`; if any result differs from expectations, it throws `AssertionError` and does not print the final `PASS` line. Inspecting `equals`, `compareToIgnoreCase`, and the comparator side by side makes it clear where the comparisons actually diverge.

`List.sort` in the example also checks **stability (stable sort)**: the strings `"A"` and `"a"` compare as 0 with the comparator, so they keep their relative order from the initial list. Similarly, `"b"` and `"B"` preserve their relative order. `List.sort` uses the comparator to sort **without removing duplicate elements according to the comparator**.

## 7. How to Sort Case-Insensitively While Retaining All Variants

If you need to group strings case-insensitively while still allowing each string **that differs by `equals`** to exist in `TreeSet`, add a secondary comparison criterion (*tie-breaker*):

~~~java
Comparator<String> byCaseInsensitiveThenExact =
        String.CASE_INSENSITIVE_ORDER
              .thenComparing(Comparator.naturalOrder());

TreeSet<String> set = new TreeSet<>(byCaseInsensitiveThenExact);
set.add("Java");
set.add("java");
set.add("JAVA");
// 3 elements in order: [JAVA, Java, java]
~~~

How it works:

1. Compare **case-insensitively** first to group strings with the same spelling when ignoring case.
2. When step one returns 0, compare next by **`String`'s natural order** (case-sensitive).
3. Ultimately, the result is 0 **only when the two Strings have the same content under equals**. Thus this combined comparator is consistent with `String.equals`.

Thanks to the second criterion, `"JAVA"`, `"Java"`, and `"java"` are all kept in `TreeSet` while sitting adjacent in sorted order. This is the right option when **case-insensitive sorting** is a display requirement while **key uniqueness by equals** must still be maintained.

If **insertion order** needs to be preserved, use a collection with that property (for example `LinkedHashSet`); do not choose `TreeSet` merely because it accepts a comparator.

## 8. Another Option: Sorting a List Without Dropping Strings

With `List`, you can sort case-insensitively while **keeping all elements**, even when the comparator returns 0:

~~~java
List<String> names = new ArrayList<>(
        List.of("b", "A", "a", "B"));
names.sort(String.CASE_INSENSITIVE_ORDER);
// [A, a, b, B]
~~~

`List.sort` performs a stable sort, so elements tied under the comparator preserve their relative order; there is no "deduplicate" step. Thus when the requirement is **sorting only**, a `List` can be a better structure than `TreeSet` or `TreeMap`.

When you need both **deduplication** and sorting, define the two requirements separately: deduplicate by `equals` or case-insensitively? Sort using which comparator? You may need one structure for storing keys and a separate list for display.

## 9. Unicode, Language, and the Limits of "Case-Insensitive"

`String.CASE_INSENSITIVE_ORDER` is `String`'s comparison rule and **does not use the user's locale** to determine natural-language ordering. For instance, with ASCII `I` and `ı` (Latin small dotless i, U+0131), Java can treat them as equivalent when ignoring case:

~~~java
boolean same =
        String.CASE_INSENSITIVE_ORDER.compare("I", "\u0131") == 0;
// same == true
~~~

This **does not mean** the comparator produces correct dictionary order for every language. For lists of personal names, titles, or vocabulary that must be sorted according to specific language rules, consider `java.text.Collator` created for an appropriate `Locale`, and test the letter/accent rules of the target language. `Collator` can also treat multiple strings differing by `equals` as equivalent; when used in `TreeSet`/`TreeMap`, you still must decide clearly what `compare == 0` means.

Do not default to replacing a comparator by passing every string through `toLowerCase()` or `toUpperCase()` without choosing a locale and checking Unicode. Case conversions can be locale-dependent, can alter string length, and do not necessarily produce the exact same equivalence relation as `equalsIgnoreCase`. If the goal is simply Java's built-in case-insensitive order, using the provided comparator is more direct and clearer.

## 10. Common Mistakes

1. **Thinking `compare(...) == 0` always equals `equals`:** false for `String.CASE_INSENSITIVE_ORDER`. Test both comparisons.
2. **Switching from `HashSet` to `TreeSet` without checking duplicate rules:** variants differing only by case may disappear.
3. **Assuming `TreeMap.put` with a differently cased key always adds an entry:** it can overwrite the old entry's value.
4. **Seeing `TreeSet.contains("JAVA") == true` and assuming `"JAVA"` was added:** the tree looks up by comparator; it might only be holding `"Java"`.
5. **Adding a tie-breaker when business logic truly wants case-insensitive deduplication:** a tie-breaker will let `"Java"` and `"java"` coexist, defeating the deduplication goal.
6. **Assuming a case-insensitive comparator gives valid ordering for every locale:** test Unicode and consider `Collator` when language rules matter.
7. **Using `hashCode` as a tie-breaker for String keys:** hash values can collide and do not guarantee `compare == 0` iff `equals`; use `String.compareTo`/`naturalOrder` as the secondary criterion.

## 11. Exercises to Check Understanding

**Exercise 1.** `new TreeSet<>(String.CASE_INSENSITIVE_ORDER)` receives `"A"`, `"a"`, `"B"` in turn. How many elements does the set contain?

Answer: **2**. `"A"` and `"a"` are equivalent under the comparator so only one representative is kept; `"B"` differs from them.

**Exercise 2.** `new HashSet<String>()` receives `"A"` and `"a"` in turn. What is its size?

Answer: **2** because `String.equals` is case-sensitive.

**Exercise 3.** Why does the comparator `String.CASE_INSENSITIVE_ORDER.thenComparing(Comparator.naturalOrder())` keep both `"A"` and `"a"` in `TreeSet`?

Answer: when the case-insensitive comparison ties, the second criterion compares case-sensitively and returns a non-zero result. The two strings are not treated as the same key.

**Exercise 4.** When should a case-insensitive comparator **without a tie-breaker** be used?

Answer: when **business rules explicitly specify** that all casing variants of a string are **the same key**. When only display ordering is needed, sort a `List` or add a tie-breaker depending on the data structure.

## 12. Takeaways

- `String.equals` and `String.hashCode` define **case-sensitive** equivalence for `HashSet` and `HashMap`.
- `String.CASE_INSENSITIVE_ORDER` and `compareToIgnoreCase` establish a **case-insensitive** equivalence relation; `compare == 0` can occur for two strings where `equals == false`.
- `TreeSet`/`TreeMap` use the comparator to decide duplicate keys, so comparator choice directly affects **which data is retained**.
- If you need case-insensitive **sorting** while **keeping all Strings that differ by equals**, use a primary case-insensitive comparator followed by `thenComparing(Comparator.naturalOrder())`.
- If you need language-specific ordering, evaluate a locale-configured `Collator` and continue checking consistency with `equals`.

Clearly define **what it means for "two Strings to be the same key"** before picking a collection structure and comparator. This determines program correctness, not merely how words are ordered.
