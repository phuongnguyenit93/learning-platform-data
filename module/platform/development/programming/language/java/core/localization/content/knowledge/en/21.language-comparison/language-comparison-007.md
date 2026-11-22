# RuleBasedCollator and Custom Sorting Rules in Java

## 1. Why Can't Linguistic Comparison Just Use String.compareTo?

When building Java applications with multilingual data, users typically expect lists of names, entries, or titles to be sorted by **linguistic convention** rather than merely by each character's UTF-16 value.

For example, letter casing, tone marks, accented characters, two letters treated as a single sorting unit, or special symbols can differ between languages. `String.compareTo` compares lexicographically by **UTF-16 code units**, without understanding the linguistic meaning of strings.

Java provides `java.text.Collator` to perform **collation**: comparing two strings according to cultural/linguistic rules. For specialized sorting rules, `java.text.RuleBasedCollator` is a concrete subclass of `Collator` that lets you construct a collation table from a **rule string**.

For instance, a historical catalog might require the digraph `ch` to be treated as one sorting unit coming **after c but before d**. Or a system might need to sort symbols/abbreviations in an internal order confirmed by the product owner. `RuleBasedCollator` supports expressing such relationships.

**Lesson goal:** understand rule string syntax, relation operators `<`, `;`, `,`, `=`, reset `&`, distinction `strength`, contractions/expansions, Unicode normalization, error checking, and safe comparator design.

## 2. Standard Collator or RuleBasedCollator?

In most cases, **start with the Collator provided for a locale**:

~~~java
Collator vietnamese = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
~~~

This is an illustrative statement inside a Java method requiring imports of `java.text.Collator` and `java.util.Locale`.

`Collator.getInstance(locale)` selects the comparator supported by the runtime and locale provider. You do not need to manually define the alphabet, diacritics, or hundreds of Unicode relationships. If you only need to sort lists in the user's language, this is usually the right starting point.

Use `RuleBasedCollator` when you **have sorting requirements that differ from default locale rules**, such as:

- A reference catalog with a custom alphabetical order defined by business documentation.
- A legacy dictionary system treating `ch` as a contraction.
- Testing a specific set of primary/secondary/tertiary relationships.
- Adjusting part of an existing `RuleBasedCollator`'s order with control over the entire resulting rule set.

Never replace a full language collation table with a short `a < b < c` list in production: this class places **unmentioned characters at the end of the collation order**, easily mis-sorting Unicode words outside the table. JDK documentation also notes limitations of rule-based table design; more complex collation tasks may require an appropriate mechanism or dedicated library.

## 3. Core Syntax of RuleBasedCollator

Constructor:

~~~java
RuleBasedCollator custom = new RuleBasedCollator(
        "< a < b < c < d");
~~~

This is an illustrative snippet inside a Java method. The constructor accepts a **rule string**, compiles it into a collation table, and can throw `java.text.ParseException` if syntax or a reset position is invalid.

A rule string can contain:

1. **Relations** positioning a text argument relative to a previously stated item.
2. **Reset** `&` to jump back to an existing position and add or alter relations.
3. **Modifiers** affecting ordering across the entire table per JDK specification.

### 3.1. Relation Symbols and Distinction Levels

| Symbol | Relation in rules | Common meaning |
| --- | --- | --- |
| `<` | Primary difference | Fundamental differences such as letter order |
| `;` | Secondary difference | Accent / secondary variant differences |
| `,` | Tertiary difference | Case / minor variant differences |
| `=` | Equal | Two items are equivalent per the rule table |
| `&` | Reset | Return to an existing item's position to insert subsequent relations |

Example:

~~~text
< a , A ; á < b < c < ch < d
~~~

Meaning under this rule:

- `a` and `A` share the same primary and secondary weights; at **tertiary** they are distinguished.
- `á` differs from `a` at the **secondary** level, so `PRIMARY` can treat them as equal under this table's relations.
- `b`, `c`, `ch`, and `d` differ at the primary level.
- The sequence `ch` is described as a single **comparison unit** (contraction) in this table; it still consists of two code points `c` and `h` in `String`.

These relations **are not the rules for all of Vietnamese, Spanish, or every language**. They merely express an explicitly declared example rule set.

### 3.2. Spaces, Punctuation, and Quoting

Rule strings have their own syntax. Whitespace outside arguments is largely ignored; within text arguments, certain punctuation characters are **special syntax characters**. If you want to sort a string literally containing special punctuation, **enclose the text argument in single quotes** per RuleBasedCollator syntax.

Example:

~~~java
String rules = "< a < b < 'x-y' < c";
RuleBasedCollator c = new RuleBasedCollator(rules);
~~~

This is an illustrative snippet (not a standalone Java file). The hyphen in `x-y` is quoted so the parser does not misinterpret it. Similarly, `'&'` can express a literal `&` character rather than a reset.

Keep especially in mind:

- Write `< a < b` instead of assuming `a < b` is a complete rule string; the leading `<` establishes the relation for the first item.
- Unquoted whitespace may be ignored by the parser; if a **literal space** is needed as an item in rules, quote it per the specification.
- `< a < b-c < d` has an unquoted `-` and can throw `ParseException`.
- Do not use `[before 1]`, `[reorder ...]`, or ICU-specific syntax in `java.text.RuleBasedCollator`: the two rule languages **are not identical**.

## 4. Resetting with &: Adding Relative Order

`&` does not mean string concatenation or a bitwise operator in rules; it resets the insertion point in the collation table.

Example:

~~~text
< a < b < c < d & b < bb
~~~

Before the reset: `a`, `b`, `c`, `d` have an established order. The `& b < bb` part inserts `bb` **immediately after b** at the primary level; hence `bb` comes **before c**.

Another example:

~~~text
< a < c & a < b
~~~

This means `b` is inserted after `a` and before `c`. Placing different resets can alter the final order: rules are **order-dependent**, not an unordered set of interchangeable symbols.

**Reset condition:** the text argument of `&` or an appropriate prefix of it must already appear earlier in the rule string. If the target reset position does not yet exist, the constructor throws `ParseException`. Invalid example:

~~~java
new RuleBasedCollator("< a < b & z < zz");
~~~

`z` has not appeared in the declared table, so requesting `zz` after `z` has no defined anchor point. The program in section 8 tests this exact error.

### 4.1. Contraction and Expansion Are Two Different Concepts

- **Contraction:** a **multi-character** sequence treated as a single weight unit in collation. For example, `< c < ch < d` uses `ch` as a distinct entry between `c` and `d`.
- **Expansion:** an entry can be treated as a sequence of weights of multiple existing entries; a special reset form can express this. Oracle documentation gives `< a < b & ae < e`, where `ae` anchors relative to `a`, giving the expansion comparison semantics.

These rules are **sorting conventions**, and do not mean `String.length()` changes, `ch` becomes a single Unicode code point, or strings are mutated during comparison.

## 5. Strength: When Are Two Strings Considered Same or Different?

`RuleBasedCollator` inherits strength levels from `Collator`:

| Strength | Characteristics |
| --- | --- |
| `Collator.PRIMARY` | Considers only primary differences; ignores secondary/tertiary differences |
| `Collator.SECONDARY` | Considers primary and secondary; can distinguish accents |
| `Collator.TERTIARY` | Considers primary, secondary, and tertiary; can distinguish case |
| `Collator.IDENTICAL` | Stricter comparison level beyond the three levels above; does not mean all raw differing Unicode strings must sort differently, since normalization can also apply |

A default `Collator` gets its strength from the instance and locale provider configuration. With custom rules, **set it explicitly** when business logic has specific validation criteria:

~~~java
custom.setStrength(Collator.PRIMARY);
int result = custom.compare("a", "\u00E1");
~~~

This is an illustrative snippet requiring an already created `custom` collator. Under the rule table `< a , A ; á < b`, comparing at PRIMARY returns **0** because the difference between `a` and `á` is only secondary.

Switching to `SECONDARY`, comparing `a` with `á` returns a **negative** value (`a` before `á`). Switching to `TERTIARY`, `a` and `A` also differ in order as declared.

**Note:** `Collator.compare` returns negative/0/positive; **it is not guaranteed to return exactly -1 or +1**. If printing qualitative signs, use `Integer.signum(compare(...))` as in section 8.

### 5.1. Equal in Collation Is Not String.equals

A rule with `=`:

~~~text
< a = á < b
~~~

allows the example collator to treat `a` and `á` as having the same collation weight. However:

~~~java
"a".equals("\u00E1")  // false
~~~

`String.equals` comparison still depends on Java `String` content and is unaffected by rules.

This directly impacts collections:

- `TreeSet<String>` given a `Collator` comparator may treat two strings with `compare(a, b) == 0` as the same element under the ordering relation.
- `HashSet<String>` relies on `String.equals` and `hashCode`, so it can keep **both**.
- Using collation for **sorting** does not automatically make it suitable for determining unique user identifiers.

If you need to store a sorted list while keeping every value intact, use `List.sort(collator)` with an explicit tie-breaker per contract. Decide requirements carefully: a `String.compareTo` tie-breaker breaks treating two strings as equivalent when used as a duplicate-key criterion.

## 6. Standalone Rules or Tailoring from a Locale?

### 6.1. Standalone Rules: Useful for Learning and Closed Alphabets

~~~java
RuleBasedCollator simple =
        new RuleBasedCollator("< a < b < c < ch < d");
~~~

The snippet above is a standalone example for the listed items. **Unmentioned characters may be sorted at the end**, so this very short rule is unsuitable for sorting full Vietnamese, accented letters, emoji, Greek, Japanese, or free-form user input.

### 6.2. Extracting Locale Rules and Extending Under Control

If the runtime returns a `RuleBasedCollator`, you can inspect `getRules()` and build a new instance from that rule string plus adjustments:

~~~java
Collator base = Collator.getInstance(Locale.US);
if (base instanceof RuleBasedCollator rb) {
    String tailored = rb.getRules() + " & c < ch";
    RuleBasedCollator custom = new RuleBasedCollator(tailored);
    custom.setStrength(Collator.TERTIARY);
    // Use custom to test the rules on a realistic dataset.
}
~~~

This is an **illustrative snippet** needing `java.text.*` and `java.util.Locale` imports inside a method handling `ParseException`. Verify at runtime that base is a `RuleBasedCollator`; `Collator.getInstance(locale)` does not guarantee every provider returns this exact class.

**Do not blindly append new rules**:

1. `rb.getRules()` can be very long and contain many relations, contractions/expansions, and modifiers.
2. Appending `& c < ch` only works if the reset target is recognized and does not break existing rules.
3. Check whether `ch` is already defined as a contraction or has special ordering.
4. Compiling new rules can throw `ParseException`; any change needs regression tests with accented words, uppercase letters, and mixed-script data.
5. JDK/CLDR/locale provider versions can alter base rules, so concatenating rule strings into a new table can create cross-environment differences.

For large-scale multilingual products, prefer **collation tailoring** supported by libraries and locale data rather than rebuilding an entire language solely with manual rules.

## 7. Unicode Decomposition, Accents, and Special Modifiers

### 7.1. Decomposition When Comparing Accented Strings

An accented letter can be stored in **precomposed** form (e.g., `á`, U+00E1) or **decomposed** form (`a` + U+0301). Users usually see the same letter, yet the UTF-16 strings differ.

`RuleBasedCollator` handles some canonical equivalences automatically when building the rule table, though not all combining-mark data yields expected results automatically when users enter mark sequences in unusual orders. You can configure:

~~~java
custom.setDecomposition(Collator.CANONICAL_DECOMPOSITION);
~~~

This requests canonical decomposition handling during comparison. For **compatibility decomposition** forms, such as full-width/half-width in some scripts, `Collator.FULL_DECOMPOSITION` may need to be considered, with different cost and semantics.

`Collator` options:

- `NO_DECOMPOSITION`: does not decompose inputs per this mode before comparison.
- `CANONICAL_DECOMPOSITION`: uses canonical equivalence handling, appropriate for many combining-mark cases.
- `FULL_DECOMPOSITION`: additionally considers compatibility equivalence per the collator mechanism.

**Do not infer** that enabling `CANONICAL_DECOMPOSITION` makes two strings equal under `String.equals` or alters source contents. It only controls how the collator processes inputs during comparison.

### 7.2. Two Special Modifiers

JDK 17 further describes:

- `@`: enables **reverse secondary (accent) weight** ordering in the table, supporting traditional French accent sorting.
- `!`: enables **Thai/Lao vowel–consonant reordering** for applicable cases in Thai and Lao.

These do not correspond to a distinct difference level like `<` or `;`, and can affect **the entire collator**. Do not add `@` or `!` to rules merely hoping for "better Unicode sorting"; use them only when a specific language/domain requires them and real dictionary tests verify them.

## 8. Complete Java 17 Program: Contraction, Reset, Strength, and Rule Errors

The example below intentionally uses a **small** alphabet to observe behavior. Results are printed using **ASCII labels** rather than depending on console font/encoding to display `á`.

**File `CustomCollationDemo.java`:**

~~~java
import java.text.CollationKey;
import java.text.Collator;
import java.text.ParseException;
import java.text.RuleBasedCollator;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CustomCollationDemo {
    static int sign(RuleBasedCollator c, String a, String b) {
        return Integer.signum(c.compare(a, b));
    }

    public static void main(String[] args) throws ParseException {
        String rules = "< a , A ; \u00E1 < b < c < ch < d & b < bb";
        RuleBasedCollator c = new RuleBasedCollator(rules);

        c.setStrength(Collator.PRIMARY);
        System.out.println("PRIMARY a/A=" + sign(c, "a", "A"));
        System.out.println("PRIMARY a/acute=" +
                sign(c, "a", "\u00E1"));

        c.setStrength(Collator.SECONDARY);
        System.out.println("SECONDARY a/A=" + sign(c, "a", "A"));
        System.out.println("SECONDARY a/acute=" +
                sign(c, "a", "\u00E1"));

        c.setStrength(Collator.TERTIARY);
        System.out.println("TERTIARY a/A=" + sign(c, "a", "A"));
        System.out.println("TERTIARY c/ch=" + sign(c, "c", "ch"));
        System.out.println("TERTIARY ch/d=" + sign(c, "ch", "d"));
        System.out.println("TERTIARY bb/c=" + sign(c, "bb", "c"));

        List<String> words = new ArrayList<>(
                Arrays.asList("d", "ch", "c", "bb", "b", "\u00E1", "A", "a"));
        words.sort(c);
        String sortedLabels = words.stream()
                .map(s -> s.equals("\u00E1") ? "a-acute" : s)
                .collect(Collectors.joining(", "));
        System.out.println("sorted=" + sortedLabels);

        CollationKey keyCh = c.getCollationKey("ch");
        CollationKey keyD = c.getCollationKey("d");
        System.out.println("key ch/d=" +
                Integer.signum(keyCh.compareTo(keyD)));

        RuleBasedCollator equivalent =
                new RuleBasedCollator("< a = \u00E1 < b");
        System.out.println("equal-rule a/acute=" +
                sign(equivalent, "a", "\u00E1"));

        try {
            new RuleBasedCollator("< a < b & z < zz");
            System.out.println("invalid reset=ACCEPTED");
        } catch (ParseException ex) {
            System.out.println("invalid reset=REJECTED");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CustomCollationDemo.java
java CustomCollationDemo
~~~

**Stdout verified on JDK:**

~~~text
PRIMARY a/A=0
PRIMARY a/acute=0
SECONDARY a/A=0
SECONDARY a/acute=-1
TERTIARY a/A=-1
TERTIARY c/ch=-1
TERTIARY ch/d=-1
TERTIARY bb/c=-1
sorted=a, A, a-acute, b, bb, c, ch, d
key ch/d=-1
equal-rule a/acute=0
invalid reset=REJECTED
~~~

Meaning:

1. At **PRIMARY**, `a`/`A` and `a`/`á` match on primary weight.
2. At **SECONDARY**, the acute accent puts `a` before `á`, while `a`/`A` remain equal because case difference is tertiary.
3. At **TERTIARY**, `a` comes before `A` **per the sample rule**. This is not a claim that lowercase precedes uppercase in every locale.
4. The relation `c < ch < d` holds; `ch` is a contraction in the comparison table.
5. `& b < bb` places `bb` after `b` and before `c`.
6. `List.sort(c)` uses the configured comparator, producing a stable ordering of the sample input.
7. `CollationKey.compareTo` generated from **the same collator/configuration** agrees with the comparison direction of `ch` and `d`.
8. With rule `=`, `a` and `á` are treated as collation-equivalent.
9. Resetting to nonexistent `z` is rejected by the parser with `ParseException`.

**Important limitation:** a short rule table does not describe all characters of a language; unlisted data may sort at the end. Do not drop a demo rule directly into a production system sorting addresses, personal names, or large international text without expanding and testing it.

## 9. CollationKey: Optimizing Repeated Comparisons

If the same set of strings must be compared many times (such as during a large sort), `CollationKey` lets you precompute comparison weights for each string:

~~~java
CollationKey a = custom.getCollationKey("ch");
CollationKey b = custom.getCollationKey("d");
int relation = a.compareTo(b);
~~~

This is an illustrative snippet; `custom` is an already constructed `RuleBasedCollator`. In the example, `relation` is negative because `ch` precedes `d`.

Never treat keys from **two different collators/configurations** as sharing the same standard:

- `strength` levels may differ.
- `decomposition` modes may differ.
- Rule tables or locale providers differ.
- JDK versions may carry differing collation data.

Therefore, do not store `CollationKey` long-term and compare against new keys generated after changing rules or upgrading runtime versions. If persistence is needed, define a key versioning/rebuild mechanism and test compatibility.

`CollationKey` can increase memory usage; for small lists or few comparisons, calling `collator.compare` directly is usually simpler. If performance is the primary reason, **benchmark** with real data rather than assuming keys are always faster in every situation.

## 10. Thread Safety, Stability, and Databases

`Collator` has setters like `setStrength` and `setDecomposition`; `RuleBasedCollator` also holds a rule table. **Never share a single mutable instance across threads** without appropriate synchronization management. A common pattern is creating/configuring the comparator before sorting, keeping it scoped to the operation, or cloning from a configured template:

~~~java
RuleBasedCollator configured =
        new RuleBasedCollator("< a < b < c");
configured.setStrength(Collator.SECONDARY);

RuleBasedCollator forThisTask =
        (RuleBasedCollator) configured.clone();
~~~

This is an illustrative snippet inside a method throwing or catching `ParseException`; the clone can be used by a separate operation without altering strength on an object used elsewhere.

**Do not confuse Java collation with database collation**: sorting a list with `RuleBasedCollator` on the JVM does not ensure `ORDER BY` in the database uses the same rules. If pagination happens in the DB and Java re-sorts each page, global ordering can be wrong. Unify the sort/pagination/search contract at one layer or define compatible collation data on both sides.

When upgrading the JDK/locale provider or modifying rules, any ordering change can affect caches, indexes, page boundaries, exported catalogs, and snapshot tests. For applications needing long-term stable ordering, maintain **rule versioning** and a regression dataset testing order.

## 11. Common Mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Using `String.compareTo` for multilingual person names | Compares UTF-16, ignores local conventions | Use `Collator` by locale |
| Using a short demo rule for all of Unicode | Undeclared characters sort at the end | Start from locale rules or full tailoring |
| Writing `a < b` instead of a complete rule | Missing initial relation | Write `< a < b` |
| Omitting quotes around punctuation in text arguments | Parser misreads syntax / `ParseException` | Quote special characters |
| Resetting `& z` before declaring `z` | No insertion anchor | Reset only to an existing point |
| Confusing `;` and `,` | Wrong weight level | Specify secondary/tertiary explicitly, test strength |
| Thinking a `ch` contraction changes `String.length()` | Collation only alters comparison weights | Keep Unicode processing separate from sorting |
| Setting `PRIMARY` and treating `compare==0` as unique ID | Ignores accents/case per policy | Use an independent, explicit uniqueness criterion |
| Using `TreeSet` with a collator without checking duplicates | Can drop strings with `compare==0` | Decide tie-breaker/semantics |
| Mixing `CollationKey`s from two rules/versions | No shared comparison standard | Build keys from the same collator/configuration |
| Sharing an instance and changing strength across threads | Non-deterministic results | Manage instances/clones/synchronization |
| Assuming Java rules equal ICU rules | Syntax/features do not fully match | Follow the exact API/implementation docs |
| Assuming JVM sort determines DB order | DB uses a different collation | Align sort contract across the whole system |
| Skipping Unicode decomposition checks | Combining-mark strings may behave unexpectedly | Test and configure appropriate decomposition |

## 12. Tests to Write Before Deployment

Build a dataset containing at minimum:

1. Base letters `a`, `A`, `b`, `c`, `d`.
2. Accented letters, e.g., `á` and `a` + U+0301.
3. Contraction `ch` and words with `ch` at the start, middle, or end.
4. Reset position `bb` and strings near `b`/`c`.
5. Punctuation, whitespace, and symbols not declared in the rules.
6. Digits, case variants, and other languages if present in real data.
7. Rules missing quotes, missing arguments, or resetting to nonexistent characters.
8. Cases where `compare(a, b) == 0` while `!a.equals(b)`.
9. Differences when switching `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL`.
10. Effects of `CANONICAL_DECOMPOSITION` and `FULL_DECOMPOSITION` if needed by the app.
11. `CollationKey` vs. `compare` under the same configuration.
12. Order stability after upgrading JDK, rules, and DB.

Comparator invariants to preserve: sign antisymmetry (`sign(compare(a,b)) = -sign(compare(b,a))`), transitivity, and equivalence consistency. Especially when adding a **tie-breaker**, test on real data so no contradictory order arises.

If business logic requires **standard Vietnamese** sorting, never hand-write a handful of relations and call it standard. Use locale-managed collation sources and reference product conventions, adjusting rules only when an explicit exception is required.

## 13. Practice Exercises

1. Change `< c < ch < d` to `< c < d < ch`; compare list ordering to see the role of contraction.
2. Change `& b < bb` to `& c < bb` in a rule containing c; predict and verify the new position of `bb`.
3. Replace `;` before `á` with `<`; compare outcomes at `PRIMARY` and `SECONDARY`.
4. Replace `< a , A` with `< a < A`; explain why `PRIMARY` can now distinguish case.
5. Create a table with `< a = á < b`; test `TreeSet` vs. `HashSet` when inserting both strings.
6. Test rules `< a < b < 'x-y' < c` and compare `x-y` against `b`, `c`. Then remove quotes to observe the parser error.
7. Build a word list containing `á` in NFC and NFD forms; test `NO_DECOMPOSITION` and `CANONICAL_DECOMPOSITION`.
8. Inspect `Collator.getInstance(Locale.forLanguageTag("vi-VN"))`, observe the returned class, and only call `getRules()` if it is actually a `RuleBasedCollator`.
9. Clone a collator, set `PRIMARY` on the copy and `TERTIARY` on the original; verify neither alters the other's strength.
10. Write a test saving sample list order; re-run after upgrading JDK or modifying rules.
11. Compare `ch` with `c` and `d` via `CollationKey` and compare signs against `compare`.
12. Propose a sorting policy for a customer list containing Vietnamese names, Latin names, and technical IDs; specify which parts use `Collator` and which use technical ordering.

## 14. Summary

`RuleBasedCollator` lets you build a string comparator from a **textual rule table** rather than relying on UTF-16 order. Symbols `<`, `;`, `,` define primary/secondary/tertiary levels, `=` expresses collation equivalence, and `&` resets to insert rules at an existing position. Contractions and expansions alter **how comparisons work**, without altering string contents.

In localized applications, prefer `Collator.getInstance(locale)` for general languages; use custom rules when requirements are clear and syntax, Unicode/decomposition, strength, tie cases, and regression tests have been verified. Remember that short rules do not cover all characters and can sort unexpectedly; Java's order must also align with the database and business rules.

**References:**

- Java SE 17, `RuleBasedCollator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/RuleBasedCollator.html
- Java SE 17, `Collator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html
- Java SE 17, `CollationKey`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html
- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
