# Why Not Append Plural Suffixes Using a Single General Rule?

## 1. The Problem When Localizing Sentences Containing Quantities

An English program might start with a simple idea:

```java
String text = count + " file" + (count == 1 ? "" : "s");
```

Results like `1 file` and `2 files` may seem reasonable in some cases. However, that is **not** a general pluralization algorithm for multilingual applications. Even in English, `child → children`, `person → people`, and `mouse → mice` are morphological exceptions; a phrase like `0 files` might also be better displayed more naturally as `No files`. In Vietnamese, both `1 tệp` and `2 tệp` use the noun `tệp`, so automatically adding `s` is meaningless. Russian, Arabic, and many other languages have more than two forms depending on the quantity.

**Core principle:** do not construct multilingual sentences using the formula `noun + suffix(count)`. Choose **complete message templates** appropriate for the language, grammar, and number type; use standardized plural data (such as Unicode CLDR) when supporting multiple locales.

This lesson explains **why you should not append plural suffixes using a single general rule** and how to design alternatives in Java Core Localization.

After studying this lesson, you should be able to distinguish:

- **Noun morphology rules** (how a noun changes its ending) versus **numeric plural category rules** (based on the language and how the number is represented).
- **Cardinal** (quantities: 1, 2, 5...) versus **ordinal** (order: 1st, 2nd, 3rd...).
- The categories `zero`, `one`, `two`, `few`, `many`, `other` versus lexical meanings like "singular" and "plural".
- How to avoid translating piecemeal, concatenating strings in the wrong word order, and breaking grammatical agreement.
- The capabilities of `java.text.MessageFormat` and `ChoiceFormat`, and when you need ICU4J or an i18n library with CLDR plural rules support.

## 2. Three Different Layers: Number, Grammar, and the Whole Sentence

Consider two English sentences:

```text
1 new message
2 new messages
```

There are at least three issues:

1. **How the number is represented:** `1`, `2`, or decimal numbers; separators and digits may depend on the locale.
2. **Word forms:** `message` or `messages`; adjectives, verbs, pronouns, and other components may also change in other languages.
3. **Sentence structure:** parts may change order or have a different natural phrasing, such as `No new messages` instead of `0 new messages`.

If an application splits the translation into:

```text
prefix + number + noun + guessedPluralSuffix
```

translators cannot rearrange sentence order or replace the entire structure. A suffix is a property of **a specific word**, not of all nouns in a language, and certainly not of every language.

**The right solution:** manage a single message key that has multiple **complete forms**. Each form is selected based on the quantity and language, and then placeholders are formatted with actual values. For example, in English: `noFiles="No files"`, `oneFile="{count} file"`, `otherFiles="{count} files"`. In Vietnamese, the same template `"{count} tệp"` can be chosen for every quantity if that is the contextually appropriate phrasing.

Allowing a dedicated form for `0` does not mean every language has the CLDR `zero` category. This can also simply be a **content decision** for a special case.

## 3. What Are Unicode CLDR Plural Rules?

The **Unicode Common Locale Data Repository (CLDR)** provides locale-specific plural rule data so software can select the appropriate message form. CLDR defines **shared category names**:

| Category | Practical Interpretation | What Should Not Be Inferred |
| --- | --- | --- |
| `zero` | A dedicated form for numbers following the locale's zero rule | Does not mean every number equal to 0 belongs to `zero` in every language |
| `one` | A form typically associated with a quantity of one | Does not mean only the integer 1 belongs to this category |
| `two` | A form used for a quantity of two in some languages | Not every locale has it |
| `few` | A small-number group according to the locale's rules | Not a global condition `2 ≤ n ≤ 4` |
| `many` | Another number group according to the locale's rules | Not `n > 5` by default |
| `other` | The remaining group; always needs to be supported | Not necessarily "plural" in the English sense |

Category names are **technical labels** for rules comparing minimal messages by number. They are not names of grammatical variants understood identically across all languages.

**Each language uses only the subset of categories appropriate for it.** For example, Vietnamese and Japanese typically only need `other` for cardinals in CLDR rules; English has `one` and `other`; Russian and Arabic need to distinguish more groups. In particular, **the number 0 does not necessarily correspond to the `zero` category**; standard English uses `other` for `0`.

### Cardinals and ordinals do not share the same rule set

- **Cardinal plural:** sentences about quantity: `1 file`, `2 files`.
- **Ordinal plural:** expressions of order: `1st`, `2nd`, `3rd`, `4th` in English.

For example, in English, the ordinals `11th`, `12th`, `13th` all use `th`, whereas `21st`, `22nd`, `23rd` differ. Trying to reuse the cardinal rule `n == 1` to build ordinals will be wrong. ICU MessageFormat uses `plural` for cardinal and `selectordinal` for ordinal; the two types must not be swapped.

## 4. For the Same Number, Different Languages May Select Different Forms

### English: two cardinal categories are not enough to infer every word

Common examples:

```text
1 file
2 files
0 files
```

English cardinals in CLDR have `one` and `other`, but the `file/files` variation applies only to **this noun**. Irregular or uncountable nouns do not follow the operation of appending `s`:

```text
1 child -> 2 children
1 person -> 2 people
1 sheep -> 2 sheep
1 piece of information -> 2 pieces of information
```

Quantity in a translation can even involve the verb: `There is one message` versus `There are two messages`. Appending `s` to the noun cannot adjust `is/are`.

### Vietnamese: quantity usually does not change noun morphology

Examples:

```text
1 tệp
2 tệp
5 tệp
```

There is no reason to append an "s" suffix. However, that does **not** mean translating every Vietnamese sentence is simply replacing English words with Vietnamese words. Classifiers, counting expressions, and natural phrasing depend on context: `một quyển sách`, `hai cuốn sách`, `ba người`; a UI might choose `Không có tệp nào` when the quantity is 0. The `other` cardinal rule does not automatically solve all grammar and sentence copywriting.

### Russian: grouping by the last digit and last two digits

For many countable nouns, Russian has forms illustrated by these examples:

```text
1 файл
2 файла
5 файлов
21 файл
22 файла
25 файлов
```

The rule is not `count == 1 ? singular : plural`: `21` uses the same form as `1` in this example, `22` matches `2`, while `11` and `12` fall into another group due to the last two digits. For decimal numbers, the rule also inspects digits after the decimal separator and the formatted number representation.

Do not take the Russian example above and write your own `count % 10` condition to apply to every language. Each locale has its own CLDR expression; furthermore, the morphology of nouns, adjectives, and units of measure must be provided by translators.

### Arabic: more number groups

Arabic typically has the cardinal categories `zero`, `one`, `two`, `few`, `many`, and `other`. For non-negative integers, representative cases are:

| Number | Illustrative Category for Arabic |
| --- | --- |
| `0` | `zero` |
| `1` | `one` |
| `2` | `two` |
| `3`, `10` | `few` |
| `11`, `99` | `many` |
| `100` | `other` |

The table shows that **there cannot be a single generic suffix-appending function** for these number groups. This illustrates the categories according to CLDR, not a noun inflection dictionary or a complete guide to writing Arabic sentences.

### Quick comparison

| Language | Notable Cardinal Distinctions | Implementation Takeaway |
| --- | --- | --- |
| Vietnamese | Usually only `other` | Do not generate suffixes based on numbers |
| English | `one`, `other` | Still requires per-sentence/per-noun translations; avoid blindly appending `s` |
| Russian | `one`, `few`, `many`, `other` in current CLDR data | Cannot just check `n == 1` |
| Arabic | Can have all six categories | Must select the form from locale rules and use complete messages |

The accuracy of rule expressions and category sets must be taken from the **CLDR version deployed in the product**, not hardcoded by looking at a few sample numbers and extrapolating all cases.

## 5. Edge Cases: 0, Decimal Numbers, and Displayed Numbers

### 5.1. `0` does not mean `zero` is always used

The English example `0 files` belongs to the cardinal category `other`, yet in terms of UX copy you may want `No files`. A plural template can support a dedicated `=0` branch to write a natural sentence without assuming the category of `0` in CLDR is `zero`.

Distinguish between:

- **Exact-value branch:** selected when the number *equals* an exact value, such as `=0`.
- **Locale plural category:** selected based on CLDR calculations and rules, such as `one`, `few`, `other`.

Both layers of conditions can coexist and serve different purposes. Do not equate `=0` with the `zero` category.

### 5.2. `1` and `1.0` can have different categories

CLDR inspects not only the numerical value, but in many cases also the **number of displayed decimal digits**, especially trailing zeros. Plural rule operands such as `n`, `i`, `v`, `w`, `f`, `t` describe characteristics of the number in its displayed form.

Therefore, differences can exist between:

```text
1
1.0
1.00
1.5
```

Even though `1 == 1.0` under numerical value comparison, **you cannot assume they have the same plural category in every locale**. An API that only accepts a `double` and loses information about the number of decimal digits can also cause form selection to mismatch the intended display. Choose a library that properly supports CLDR semantics and test numbers after rounding/formatting.

### 5.3. Negative numbers, large numbers, and rounding

Actual counts may appear as signed values, decimals, or compact-formatted values:

```text
-1
1.2
1000
1K
```

You must be consistent about whether the application passes the **raw number** or the **displayed/rounded number** to the selector. Do not infer from the string `"1K"` that the rule for the number `1` should apply. Plural-range mechanisms for number intervals such as `1–2` are also a different topic from single cardinal numbers.

## 6. Why Does Appending a Suffix Break the Whole Sentence, Not Just the Noun?

A localized sentence is a **semantic unit**. Consider these cases:

- **Subject-verb agreement:** `One item is ready` and `Two items are ready` differ in both `item/items` and `is/are`.
- **Prepositions/case/grammatical gender of nouns:** some languages change the morphology of adjectives, nouns, or pronouns by number, gender, and case.
- **Uncountable nouns:** `information` and `advice` cannot simply be changed by an `s` suffix like `file`.
- **Word order:** a natural translation may invert the quantity phrase, unit, and verb.
- **Copy for 0:** `No results found` may be better than `0 results found`, which cannot be inferred directly from the number or category name.
- **Messages with other placeholders:** quantity, grammatical gender, objects, and nouns appearing together; sometimes nested `select` and `plural` mechanisms are needed.

Strings written like `translate("There are ") + count + translate(" items")` restrict the translator's freedom and can be grammatically wrong. Put **the entire sentence with placeholders** into the translation system instead of translating and concatenating multiple fixed fragments.

## 7. Java 17+: Example of Wrong and Right Approaches on a Small Scope

Create `PluralMessagesDemo.java`. The example does not attempt to reimplement full CLDR; it **only supports two languages within the stated scope** and uses complete sentences for each case.

```java
import java.util.Locale;

public class PluralMessagesDemo {
    // Naive approach that is only accidentally correct for a subset of English words.
    static String naiveFiles(int count) {
        return count + " file" + (count == 1 ? "" : "s");
    }

    // Intentional message templates for the example's scope.
    static String describeFiles(int count, Locale locale) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }

        return switch (locale.getLanguage()) {
            case "en" -> switch (count) {
                case 0 -> "No files";
                case 1 -> "1 file";
                default -> count + " files";
            };
            case "vi" -> count + " tệp";
            default -> throw new IllegalArgumentException(
                    "Unsupported language: " + locale.toLanguageTag());
        };
    }

    public static void main(String[] args) {
        Locale english = Locale.forLanguageTag("en-US");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        System.out.println("Naive: " + naiveFiles(0));
        System.out.println("EN 0: " + describeFiles(0, english));
        System.out.println("EN 1: " + describeFiles(1, english));
        System.out.println("EN 2: " + describeFiles(2, english));
        System.out.println("VI 0: " + describeFiles(0, vietnamese));
        System.out.println("VI 1: " + describeFiles(1, vietnamese));
        System.out.println("VI 2: " + describeFiles(2, vietnamese));
    }
}
```

Run:

```bash
javac -encoding UTF-8 PluralMessagesDemo.java
java PluralMessagesDemo
```

Output:

```text
Naive: 0 files
EN 0: No files
EN 1: 1 file
EN 2: 2 files
VI 0: 0 tệp
VI 1: 1 tệp
VI 2: 2 tệp
```

Lessons from the example:

1. `naiveFiles` is a hardcoded suffix-concatenation formula. It does not know that `No files` is the natural sentence choice for `0`, and it is completely unsuitable for Vietnamese or the diversity of English nouns.
2. `describeFiles` selects **messages by language** without mutating the global `Locale.setDefault()`; different users can request different locales on the same server.
3. The code actively rejects unsupported languages, avoiding arbitrarily defaulting to an incorrect translation.
4. This is an **illustration of how to set policy** within an English/Vietnamese scope, **not** a plural engine for all locales. When an application supports many languages, use maintained rule data (CLDR/ICU) together with translation resources instead of writing a huge switch or inventing formulas for Russian/Arabic.

Translations should live in separate files/resource catalogs for translators to maintain; application logic passes `count` and `Locale` into the message formatting system.

## 8. `MessageFormat` and `ChoiceFormat` in the JDK: Useful but Limited

Java SE has two classes:

- `java.text.MessageFormat`: substitutes parameters and formats numbers/dates by locale; in the traditional JDK, patterns can invoke `choice`.
- `java.text.ChoiceFormat`: selects a string based on numeric thresholds; can help describe some simple sentences.

### Java 17+ example with `choice`

File `EnglishChoiceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class EnglishChoiceDemo {
    public static void main(String[] args) {
        MessageFormat formatter = new MessageFormat(
                "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
                Locale.forLanguageTag("en-US"));

        for (int count : new int[] {0, 1, 2, 21}) {
            System.out.println(count + " => "
                    + formatter.format(new Object[] {count}));
        }
    }
}
```

```bash
javac EnglishChoiceDemo.java
java EnglishChoiceDemo
```

Stdout:

```text
0 => no files
1 => one file
2 => 2 files
21 => 21 files
```

In the pattern above:

- `0#no files`: branch starting from threshold 0.
- `1#one file`: branch starting from threshold 1.
- `1<{0,number,integer} files`: branch greater than 1, with number formatting inside.

This is a **threshold-based selection for a specific English sentence**, not a CLDR rule; applying it to `ru` or `ar` without changing the logic and translations will be wrong. For negative numbers, non-integers, or values outside the assumed domain, this illustrative pattern must be redesigned. Do not treat `ChoiceFormat` as a multilingual tool that automatically understands categories.

### What JDK `MessageFormat` does not provide out of the box

In Java 17/21, the traditional `java.text.MessageFormat` **does not have ICU `plural` or `selectordinal` syntax**, nor does it automatically map every number to its corresponding CLDR category. Creating an instance with locale `ru-RU` does not make `ChoiceFormat` understand Russian rules. If you must support multiple languages with complex plural systems, choose a library capable of applying CLDR.

*Version note:* message formatting APIs may evolve in future Java versions; the statement above refers specifically to `java.text.MessageFormat`/`ChoiceFormat` commonly used in Java 17+ within the scope of JDK 17/21.

## 9. ICU4J: Selecting Locale Plural Categories and Keeping the Whole Sentence in the Template

**ICU4J** is a standalone Java library (not bundled in the JDK) that provides plural handling based on ICU/CLDR data. The `com.ibm.icu.text.MessageFormat` API supports `plural` and `selectordinal` patterns.

Example **illustrative ICU pattern** (not a `java.text.MessageFormat` pattern):

```text
{count, plural,
    =0 {No files}
    one {# file}
    other {# files}
}
```

With an English locale and `count` of 0, 1, 2, this pattern produces `No files`, `1 file`, `2 files` respectively (using the locale's number formatting). Here:

- `=0` is an **exact-value** branch to produce the sentence "No files"; it is not the `zero` category.
- `one` and `other` are locale-specific cardinal plural category labels.
- `#` inside a plural branch represents the number formatted according to ICU logic and the locale; there is no need to append `s` outside the template.

Sample Java snippet **depending on ICU4J**, not a standalone JDK-only runnable program:

```java
// Requires adding the appropriate ICU4J dependency to the project.
com.ibm.icu.text.MessageFormat formatter =
        new com.ibm.icu.text.MessageFormat(
                "{count, plural, =0{No files} one{# file} other{# files}}",
                java.util.Locale.forLanguageTag("en-US"));

java.util.Map<String, Object> arguments =
        java.util.Map.of("count", 2);
String result = formatter.format(arguments); // "2 files"
```

In a real application, **put the patterns in each language's resource catalog**; do not hardcode an English template and just change `Locale` to `vi-VN` or `ru-RU` assuming the content has been translated. Locale determines category selection and number formatting, **it does not translate words automatically**. The presence of the library also does not replace translation review by native speakers.

For English ordinals, ICU supports `selectordinal`, which differs from `plural`, for example this conceptual pattern:

```text
{rank, selectordinal,
    one {#st}
    two {#nd}
    few {#rd}
    other {#th}
}
```

This pattern illustrates suffixes for **English ordinals**, not a method for forming noun plurals. It cannot be applied uniformly to all languages, and complex ordinal phrases still require complete translations.

## 10. Designing a Safe Resource Catalog and API

Instead of fragmented keys like `file.name` + `file.suffix`, use a single key **by sentence meaning** containing all plural branches. Conceptual model:

```text
key: inbox.unreadCount

locale en:
  =0: No unread messages
  one: You have # unread message
  other: You have # unread messages

locale vi:
  other: Bạn có # tin nhắn chưa đọc

locale ru:
  one: <Russian sentence for one form>
  few: <Russian sentence for few form>
  many: <Russian sentence for many form>
  other: <Russian sentence for other form, if required by data>
```

This is an **illustrative data schema**, not mandatory Java `.properties` syntax and not a completed Russian translation. The Russian content must be supplied by translators, including every sentence component that varies with the number.

Recommended processing flow:

1. **Resolve the locale per user/request** from a valid preference source; apply a supported-locale whitelist and fallback policy.
2. **Define the domain of count**: non-negative integers, decimals, negative values, rounded numbers, or displayed numbers. Do not silently coerce `1.0` to `1` if the rules require distinguishing them.
3. **Choose the message key by meaning**, such as `inbox.unreadCount`, without concatenating self-translated fragments.
4. **Use the library's plural selector** based on locale and count. Prioritize exact-value branches when UX copy requires them (such as `=0`); for other values, apply the category.
5. **Format placeholders and the entire sentence** according to the locale, escaping/quoting properly for the engine in use.
6. **Verify all required branches are present**, especially `other`, and avoid falling back to an English sentence if content fallback rules prohibit it.
7. **Test realistic number groups** and have native speakers review grammar, word order, classifiers, gender/case, and special-meaning sentences.

For pure-JDK Java Core without complex multilingual requirements, a switch over **supported languages and a narrow context** can be used as in the `PluralMessagesDemo` example. However, as translation scale grows, code logic must be separated from translations and rely on a trusted source of plural rules.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Appending `s` when `count != 1` for all locales | Grammar is not uniform across languages | Use locale-specific translations and plural rules |
| Using `n == 1` to handle every language | There are `few`, `many`, `two`, and teens exceptions | Select categories from CLDR |
| Assuming `0` always belongs to `zero` | Not every language has a `zero` category | Distinguish `=0` from the `zero` category |
| Translating only the noun and keeping verbs/adjectives unchanged | The whole sentence structure may change | Translate complete sentence templates |
| Using `ChoiceFormat` as a CLDR engine | It only selects by developer-defined thresholds | Use ICU4J/equivalent library or clearly scoped logic |
| Treating `plural` and `selectordinal` as the same | Cardinal and ordinal rules differ | Choose the right mechanism |
| Assuming `1` and `1.0` always take the same form | Displayed trailing decimal zeros can affect the category | Preserve precision information in the API |
| Computing `n % 10` yourself for all languages | Rules depend on locale, teens groups, and decimals | Use versioned CLDR data |
| Testing only `1` and `2` | Misses `0`, `3`, `5`, `11`, `21`, and decimal numbers | Build a test matrix suited to each locale |
| Changing only the formatter's `Locale` while keeping English templates | Locale does not translate sentence text | Maintain separate resource catalogs per language |
| Calling `Locale.setDefault()` per request | Mutates shared JVM state, easily causes conflicts | Pass `Locale` explicitly |
| Ignoring classifiers/gender/case | A right category can still yield a broken sentence | Review full-sentence translations with native speakers |

## 12. Exercises and Self-Check Questions

1. Why is `count == 1 ? "file" : "files"` not a multilingual solution? **Because it only describes a single English noun and does not handle the morphology, sentence structure, and categories of other languages.**
2. Do Vietnamese `1 tệp` and `2 tệp` need to change a noun suffix? **Not in the example's form; instead of appending a suffix, use an appropriate Vietnamese sentence template.**
3. Why does Russian `21 файл` differ from `n == 1` logic? **Plural groups are determined by the language's numeric rules, including the last digit and exception cases.**
4. Does `0` always belong to the `zero` category in CLDR? **No.** An exact branch `=0` can be used for special copy.
5. Can `1` and `1.0` differ when selecting a form? **Yes, in some languages**, because CLDR operands can consider the number of displayed decimal digits.
6. Does Java 17 `java.text.MessageFormat` natively understand the ICU pattern `{count, plural, ...}`? **No.** That is ICU MessageFormat syntax and requires the corresponding dependency.
7. Can you translate only the suffix instead of the whole sentence? **No**, because word order, verbs, adjectives, and grammar can change.
8. If you want the phrasing `No files` when count=0 even though CLDR English uses the `other` category for 0, how should you handle it? **Use an exact-value branch `=0` in a supporting template or an explicit policy; do not redefine the `other` category.**
9. For a new i18n tool, which numbers should appear in tests? **At least 0, 1, 2, 3, 5, 11, 21; along with decimals and forms like 1.0/1.00 if supported and meaningful for the locale.**
10. When should native speakers review translations? **After category selection rules are right, review the complete sentence, because categories alone do not solve every grammatical phenomenon.**

## References

- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): category concepts, minimal pairs, and integer/decimal differences.
- [Unicode CLDR — Language Plural Rules](https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html): table of plural forms by language for the corresponding CLDR version.
- [Unicode TR35 — Numbers and Plural Rules](https://unicode.org/reports/tr35/tr35-numbers.html): plural operands and rules.
- [ICU4J — MessageFormat](https://unicode-org.github.io/icu-docs/apidoc/released/icu4j/com/ibm/icu/text/MessageFormat.html): `plural`/`selectordinal` patterns and differences from JDK `MessageFormat`.
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html): standard JDK message formatting templates.
- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html): string selection by numeric thresholds, not a full replacement for CLDR plural rules.
