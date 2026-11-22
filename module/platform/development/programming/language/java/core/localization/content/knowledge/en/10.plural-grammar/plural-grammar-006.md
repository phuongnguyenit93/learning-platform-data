# Limitations of ChoiceFormat with Plural Rules and Grammatical Gender in Java

## 1. Problem Statement: Numeric Thresholds Are Not Grammar

In multilingual applications, the same message may need multiple phrasings depending on **quantity**, **noun**, **grammatical gender**, **grammatical case**, or other contextual information. For example, English might write:

- `0 files` → “no files”
- `1 file` → “one file”
- `2 files` → “2 files”

Java provides `java.text.ChoiceFormat` to **select a string by numeric value ranges**. When embedded in `java.text.MessageFormat`, the common syntax is:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

For non-negative integers and simple English sentences, this approach can meet requirements. However, it is not equivalent to a multilingual grammar engine:

1. Many languages have **plural categories** depending on modulo remainders, number of decimal digits, and number representation, rather than linear ascending intervals.
2. **Grammatical gender** of a noun, pronoun, or agreeing word cannot be inferred from a quantity.
3. **Plural + gender + grammatical case** can affect multiple words in the same sentence rather than merely changing a noun suffix.
4. `ChoiceFormat` does not directly support grammatical expressions like `plural` and `select` from ICU MessageFormat. Those are two different mechanisms.

**Goal:** understand accurately what `ChoiceFormat` can do, recognize misuse cases, and know how to design proper localized messages when plural rules and grammatical gender are involved.

## 2. ChoiceFormat Actually Selects by Numeric Limits

`ChoiceFormat` defines an ordered set of numeric boundaries and corresponding messages. A pattern like:

```text
0#none|1#one|1<many
```

is interpreted according to the following thresholds:

| Input Condition | Branch | Result |
| --- | --- | --- |
| `n = 0` | `0#none` | `none` |
| `n = 1` | `1#one` | `one` |
| `n > 1` | `1<many` | `many` |

Here:

- `#` (and its corresponding inclusive symbol in ChoiceFormat) marks a branch starting at an **inclusive threshold**.
- `<` denotes **strictly greater than** the threshold.
- `|` separates branches.
- Thresholds are evaluated in ascending order; each choice corresponds to an interval on the number line.
- For numbers **smaller than the first limit**, `ChoiceFormat` still uses the string of the first branch; it does not report that the data is invalid.

You can instantiate `ChoiceFormat` standalone:

```java
ChoiceFormat format =
        new ChoiceFormat("0#none|1#one|1<many");
System.out.println(format.format(2)); // many
```

Or use `MessageFormat` to insert the number back into the branch result:

```java
MessageFormat format = new MessageFormat(
        "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
        Locale.US);
System.out.println(format.format(new Object[] {2})); // 2 files
```

The two snippets above are illustrative code inside a Java method, requiring the corresponding class imports. Notably, `MessageFormat` can process **nested format elements inside a choice result**, but that only helps insert values; it does not magically learn Russian or Arabic plural rules.

### Misconceptions about conditions

`ChoiceFormat` has no general conditional expression API in its pattern:

- You cannot write conditions like `n % 10 == 1` directly.
- It does not compute classifier context or noun gender automatically.
- It does not fetch plural rules from `Locale` to generate `one/few/many` branches.
- It does not restrict inputs to non-negative integers automatically.
- It does not guarantee that a number printed inside `{0,number,integer}` reflects the exact original decimal value: the formatter may round it.

Therefore, treat `ChoiceFormat` as a **numeric range selector**, not a **plural grammar engine**.

## 3. Plural Rules: Classification by Language, Not Just by Number

Unicode CLDR defines **plural categories** to describe how quantities are used per locale. Common category names are `zero`, `one`, `two`, `few`, `many`, and `other`. These names are **rule labels**, not literal statements that the value always equals 0, 1, or 2. Each language may use only a subset.

High-level examples:

| Language / Group | What to Note |
| --- | --- |
| English | Cardinal singular typically applies to integer value `1`, while other values use another form; data with displayed decimal digits needs separate consideration. |
| Vietnamese | Does not use English-style singular/plural noun inflection; sentence choice still depends on context, classifiers, and phrasing. |
| Russian | For integers, forms depend on the last digit and **last two digits**, not just the progression `1, 2, 5, 21...`. |
| Arabic | Has groups such as `zero`, `one`, `two`, `few`, `many`, `other`, with locale-specific conditions. |
| Polish | Has multiple plural classes, where decimal forms and remainder rules can differ from integers. |

CLDR uses operands such as `n` (absolute value), `i` (integer part), `v` (count of visible fraction digits), `w` (count of visible fraction digits without trailing zeros), and fractional digits to determine the category. An important detail is that **displayed form can affect the category**. Formats `1` and `1.0` may be classified differently by rules inspecting `v`, even though their numerical values are equal.

In real systems, you cannot always recover the number of decimal digits a user entered from a `double` alone. If plural policy depends on representation, the input data or formatting layer must preserve the required information.

### Cardinal differs from ordinal

**Cardinal** rules are used for counting quantities (1 file, 2 files), whereas **ordinal** rules are used for order (1st, 2nd, 3rd). A language may have an ordinal grouping system different from its cardinal system. `ChoiceFormat` does not distinguish or choose this rule type from context; it must be part of message design.

## 4. Why Do Fixed Thresholds Fail for Russian?

For **non-negative integers** in a Russian example, a common simplified classification is:

- `one` when the last digit is 1, **except** numbers whose last two digits equal 11.
- `few` when the last digit is 2, 3, or 4, **except** numbers whose last two digits are 12, 13, or 14.
- `many` for the remaining non-negative integers, in this context.

Thus:

| Number | Illustrative Group | Explanation |
| ---: | --- | --- |
| 1 | `one` | Ends in 1, does not end in 11. |
| 2 | `few` | Ends in 2, not 12. |
| 5 | `many` | Does not belong to `one/few`. |
| 11 | `many` | Exception for last two digits 11. |
| 21 | `one` | Last digit 1, last two digits 21. |
| 22 | `few` | Last digit 2, last two digits 22. |
| 25 | `many` | Last digit 5. |

Try expressing these groups with a naive `ChoiceFormat` pattern:

```text
0#many|1#one|2#few|5#many
```

The pattern works for 1, 2, 5, 11, yet at **21** it still selects `many`, whereas the right group for that integer is `one`; at **22** it still selects `many`, whereas the right group is `few`.

We could add thresholds `21`, `22`, `25`, but the cycle repeats again for `31`, `32`, `41`, `42`... A **finite list of contiguous thresholds** cannot generally represent an infinitely repeating modulo rule across all non-negative integers. That is a modeling limitation, not a pattern syntax bug.

**Scope limitation of the illustrative rule above:** it applies only to **non-negative integers** to demonstrate the modulo problem. For decimal numbers, Russian plural rules may select `other`; do not apply modulo arithmetic on `int` and treat it as a complete CLDR engine. In real applications, use plural rule data for the target locale instead of hand-coding rules from a few examples.

## 5. Grammatical Gender: ChoiceFormat Cannot Receive the Necessary Context

**Grammatical gender** is a property of words/structures in a language, such as a masculine or feminine noun in Spanish. This is **not identical** to a user's gender or gender identity.

Spanish examples:

- `un archivo nuevo` — “a new file”, the noun `archivo` is masculine; the article `un` and adjective `nuevo` agree accordingly.
- `una carpeta nueva` — “a new folder”, the noun `carpeta` is feminine; the article `una` and adjective `nueva` agree accordingly.

Suppose both have a **quantity of 1**. Passing only the number 1 into `ChoiceFormat` provides no data to distinguish `archivo` from `carpeta`, or to choose `un/una` and `nuevo/nueva`. Adding any number of thresholds cannot turn numeric data into information about a noun's gender.

In some languages, variations also involve pronouns, verbs, adjectives, grammatical case, quantity, or the role of the person referred to. Morphological selection requires **explicit linguistic context** and proper translations, and should not be guessed from a person's name, address, or an unrelated attribute.

### Data to pass into a message

Depending on product requirements, a message may need variables:

| Variable | Example | Notes |
| --- | --- | --- |
| `count` | `21` | Needs locale plural category; may need to preserve decimal representation. |
| `nounKey` | `file`, `folder` | Noun has lexical form and grammatical gender. |
| `grammaticalGender` | `masculine`, `feminine`, `neuter`, `other` | May belong to the noun; not inferred from count. |
| `grammaticalCase` | `nominative`, `accusative`... | Only when required by the language/sentence. |
| `formality` | `formal`, `informal` | Register of address may affect the sentence. |
| `locale` | `es-ES`, `ru-RU` | Determines the rule set/language of the message. |

Not every product needs to pass every variable. Designing a **minimal yet sufficient parameter contract** per translation key avoids over-generalized code while preserving critical context.

## 6. Standalone Java 17+ Example: Strengths and Weaknesses

The file **`ChoiceFormatLimitsDemo.java`** below has three parts:

1. Uses `MessageFormat` with `choice` to display a simple English file-count message.
2. Uses numeric-threshold `ChoiceFormat` to simulate `one/few/many` groups, contrasting with an illustrative calculation for **Russian integers** to show the failure at 21 and 22.
3. Selects Spanish phrases based on explicitly passed grammatical gender rather than number.

**Note:** the `russianIntegerExampleCategory` method only explains the non-negative integer case in this lesson. It is **not** a production plural-rules library: it does not handle decimals, number formatting, rules for other locales, or CLDR data updates.

```java
import java.text.ChoiceFormat;
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceFormatLimitsDemo {

    enum Gender {
        MASCULINE,
        FEMININE
    }

    // Illustrates the limitation for non-negative integers.
    private static String russianIntegerExampleCategory(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }

        int last = n % 10;
        int lastTwo = n % 100;

        if (last == 1 && lastTwo != 11) {
            return "one";
        }
        if (last >= 2 && last <= 4
                && (lastTwo < 12 || lastTwo > 14)) {
            return "few";
        }
        return "many";
    }

    // Just two lexical examples, not a Spanish inflection
    // engine for all nouns.
    private static String spanishPhrase(Gender gender, String noun) {
        return switch (gender) {
            case MASCULINE -> "un " + noun + " nuevo";
            case FEMININE -> "una " + noun + " nueva";
        };
    }

    public static void main(String[] args) {
        MessageFormat english = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                + "|1<{0,number,integer} files}",
                Locale.US);

        for (int n : new int[] {0, 1, 2, 21}) {
            System.out.println("en(" + n + ")="
                    + english.format(new Object[] {n}));
        }

        ChoiceFormat naiveRu = new ChoiceFormat(
                "0#many|1#one|2#few|5#many");

        for (int n : new int[] {1, 2, 5, 11, 21, 22, 25}) {
            System.out.println("ru(" + n + ")=choice:"
                    + naiveRu.format(n)
                    + ", rule:" + russianIntegerExampleCategory(n));
        }

        System.out.println("es(m)="
                + spanishPhrase(Gender.MASCULINE, "archivo"));
        System.out.println("es(f)="
                + spanishPhrase(Gender.FEMININE, "carpeta"));
    }
}
```

To compile and run in the directory containing the file, use JDK 17 or newer:

```bash
javac -encoding UTF-8 ChoiceFormatLimitsDemo.java
java ChoiceFormatLimitsDemo
```

**Exact stdout:**

```text
en(0)=no files
en(1)=one file
en(2)=2 files
en(21)=21 files
ru(1)=choice:one, rule:one
ru(2)=choice:few, rule:few
ru(5)=choice:many, rule:many
ru(11)=choice:many, rule:many
ru(21)=choice:many, rule:one
ru(22)=choice:many, rule:few
ru(25)=choice:many, rule:many
es(m)=un archivo nuevo
es(f)=una carpeta nueva
```

### Result analysis

- The `en(...)` lines show `choice` is useful for small messages, non-negative integer domains, and translator-verified branches.
- `ru(21)` and `ru(22)` are **intentional mismatches** between `ChoiceFormat`'s interval classification and the modulo-based classification in the Russian example.
- `ru(11)` illustrates the exception: last digit 1, yet last two digits 11, so it does not belong to the `one` group.
- Both `es(...)` lines keep the quantity implicitly at one while changing the article and adjective according to the noun's grammatical gender passed into the method. This logic is **custom-written**, not a native capability of `ChoiceFormat`.
- If an application must handle hundreds of nouns, many languages, and additional inflections, this `spanishPhrase` method is insufficient; lexical data sources and accurate translated strings are needed.

## 7. Additional Counterexamples: Decimals and Negative Numbers

Even in a language with relatively simple plurals, a threshold-based pattern can produce misleading output if the input falls outside the defined domain.

### Negative numbers

With:

```text
0#no files|1#one file|1<many files
```

`ChoiceFormat` can output `no files` even when the input is `-1`, because `-1` lies below the first limit. This is not a grammatical rule for negative numbers, but out-of-lower-bound fallback behavior. You must explicitly decide that **count must be a non-negative integer** and validate before formatting.

### Decimal numbers

If the “greater than 1” branch contains `{0,number,integer}` and the input is `1.5`, the numeric part is presented as an integer via the formatter's rounding mechanism. Thus, the message may display a number different from the original value even though `choice` branch selection used `1.5`.

Plural data for products may include weight, volume, duration, or non-integer quantities. Do not force every kind of number into an `integer` file-counting template. Plural rules for decimals can also depend on the number of displayed digits after the decimal separator; simple `ChoiceFormat` cannot manage those semantics.

### Values constrained to a domain

If the domain truly consists of exactly three levels `0`, `1`, `>=2` with non-negative integer counts, `ChoiceFormat` can be used after input validation. The issue is the **validity of the domain assumption**, not that `ChoiceFormat` is always useless.

## 8. Do Not Use ChoiceFormat to Encode Gender as Numbers

A common “trick” is mapping `masculine=0`, `feminine=1` and writing a `choice` pattern to pick text by index. This only creates a **fake numeric lookup** without providing grammatical understanding:

- When adding `neuter` or `other`, magic numbers become hard to maintain.
- It cannot describe agreement between nouns, articles, adjectives, verbs, and grammatical cases.
- It easily confuses a user's `gender` with a word's `grammaticalGender`, leading to inappropriate assumptions.
- It does not help verify or check translation completeness per locale.
- It does not automatically coordinate with the language's proper plural categories.

If the list of options is finite and domain-specific, you can use an `enum` or explicit identifier key to pick a **message key** before formatting. Translation variants still need translator review; do not turn `gender` into a numeric index.

Example of an explicit key design:

```text
file.created.masculine=...
folder.created.feminine=...
notification.formal=...
notification.informal=...
```

This is an **illustrative example of organizing keys**, not a translation rule for every language. At large scale, creating every key combination manually can become hard to maintain. When complex plural + gender + select is required, using a message format with selector support makes more sense.

## 9. Standard Java MessageFormat Differs from ICU MessageFormat

It is easy to confuse similarly named APIs:

| API / Mechanism | Primary Capability | Limitations |
| --- | --- | --- |
| `java.text.ChoiceFormat` (JDK) | Selects text by numeric limits. | No native CLDR plural/gender selectors. |
| `java.text.MessageFormat` (JDK) | Interpolates arguments, formats number/date/time, supports `choice` format element. | Does not natively support ICU `plural`/`select` syntax. |
| ICU4J `com.ibm.icu.text.MessageFormat` | Supports ICU MessageFormat syntax with `plural`, `selectordinal`, and `select` using locale data. | External library outside JDK; requires dependency and matching translations. |
| `ResourceBundle` (JDK) | Selects message file/source by locale and key fallback. | Only looks up resources; does not solve plurals or grammatical gender itself. |

ICU MessageFormat can express the idea:

```text
{count, plural,
    one {# file}
    other {# files}
}
```

This is **illustrative syntax for ICU MessageFormat**, not a valid pattern for standard `java.text.MessageFormat`. Inside an ICU plural branch, `#` means replacing with the formatted quantity per its rules. Locale data decides which plural branch applies, rather than requiring the author to manually partition numeric intervals.

Similarly, ICU has a selector for non-numeric attributes:

```text
{grammaticalGender, select,
    masculine {un archivo nuevo}
    feminine {una carpeta nueva}
    other {un elemento nuevo}
}
```

This is still just an example with three pre-written messages. **`select` does not automatically inflect nouns or adjectives**. It chooses a branch based on the supplied selector value. Grammatical correctness still belongs to the translation and input data contract.

In practice, patterns containing plural and select can be nested when a message depends on both count and gender. That combination produces **multiple grammatical forms** and may require fresh phrasing from translators rather than concatenating sentence fragments. Inspect the actual ICU plural categories used by that locale instead of trying to write a single pattern “for all languages”.

### Tool selection rules

- If a sentence has a few choices by **finite numeric thresholds**, and both the domain and locale text are validated: `ChoiceFormat` is an appropriate choice.
- If a sentence requires **real plural categories** across many locales, decimals, or cardinal/ordinal forms: use ICU4J or a localization framework with equivalent CLDR data.
- If a sentence needs **selection by gender, formality, or role**: use an enum/message-key selector or an engine supporting `select`.
- If a sentence needs **complex agreement**, sometimes it is better to translate complete sentences per specific variant rather than trying to assemble articles, adjectives, and nouns from substrings.

You do not need ICU4J for every small program; you need it when the linguistic problem exceeds the JDK's numeric-range selection capability.

## 10. Message Design and Data Contracts

Before creating a localization key, separate information belonging to each layer:

1. **Business logic:** which quantities are valid, is count always a non-negative integer, is there one or multiple object types, must numbers retain decimal digits?
2. **Linguistics:** which locales are supported, are cardinal or ordinal plurals needed, which words require agreement, which noun owns grammatical gender?
3. **Presentation:** whole-sentence structure, parameter placement, whether shortening/rephrasing is needed for naturalness, whether separate accessibility text is needed?
4. **Tooling:** JDK `MessageFormat` or ICU4J, locale data version, build-time message validation tests.

Do not write directly:

```java
String message = count + " file" + (count == 1 ? "" : "s");
```

in a multilingual product and expect translators to fix it properly. This logic assumes English rules and hardcodes sentence order in code. If a program only runs for English and its domain is strictly non-negative integers, it still needs tests for 0/1/2 and an explicit statement that this scope is intentional.

A good message contract should specify:

- What type `count` has, whether fractions are accepted, and what the unit is.
- Which values are supported for `noun` or `entityType`.
- Which linguistic data provides `grammaticalGender`; **do not guess about people** from counts.
- How translators are allowed to reorder words, rewrite whole sentences, and use placeholders.
- If a translation for a category is missing, what the fallback policy and CI checks are.

## 11. Testing Plurals: Boundary Tests Are Not Enough

For `ChoiceFormat`, testing values just below, equal to, and just above thresholds catches `#`/`<` bugs. However, when an application needs locale-based plurals, **testing only 0, 1, 2, 5 is insufficient**. Numbers like 11, 12, 14, 21, 22, 25, 101 can expose modulo conditions; decimal numbers expose how fractional digits are handled.

Suggested matrix:

| Test Group | Illustrative Values | Purpose |
| --- | --- | --- |
| Simple English branches | 0, 1, 2 | Verify correct messages and placeholder ordering. |
| Choice boundaries | -1, 0, 1, 1.0001, 2 | Check lower bound, `#`, and `<`; validate input domain. |
| Slavic cyclic rules | 1, 2, 5, 11, 12, 14, 21, 22, 25, 101 | Distinguish modulo classification from thresholds. |
| Decimals | 1.0, 1.5, 2.0, 2.5 | Evaluate number representation and locale decimal rules. |
| Arabic cardinal | 0, 1, 2, 3, 11, 100 | Avoid assuming only one/other exist. |
| Noun gender | Two nouns of different gender with the same count | Verify articles/adjectives selected by lexical data. |
| Count + gender combinations | Each plural category × each relevant variant | Verify the complete sentence, not just a suffix. |
| Locale fallback | Translation missing a branch/key | Ensure wrong branch or unreplaced placeholder is never shown. |

With CLDR, build **golden tests based on the right categories of each locale**, rather than treating `ChoiceFormat` output as ground truth. Keep test data stable and record the localization library version if the product requires strictly reproducible output.

### Note on 1 versus 1.0

If the engine inspects `v` (number of visible decimal digits), `1` and `1.0` may receive different categories. A test suite using `double 1.0` without preserving presentation precision will not adequately describe this condition. Choose the appropriate data type and plural-selection API, especially when quantities come from measurements or reports.

## 12. Common Implementation Mistakes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Applying `0#...|1#...|1<...` to every locale | Other languages may use more categories and modulo arithmetic. | Rely on locale plural rules or translate full sentences. |
| Thinking `one` always equals 1 | Category is a grammatical label and may depend on number form. | Use a proper plural engine and preserve number representation when needed. |
| Using `ChoiceFormat` to pick masculine/feminine via magic numbers | Cannot model agreement and confuses data types. | Use enum/select/message keys and grammatically correct text. |
| Conflating grammatical gender with user gender | Two distinct concepts that cannot substitute for each other. | Use only necessary, transparent linguistic metadata. |
| Placing nouns and suffixes in separate placeholders | Can break word order or agreement. | Prefer full-sentence translations and specific variants. |
| Testing only 1 and 2 | Misses 11, 21, 22, 101, and decimals. | Test counterexample sets per locale. |
| Using `{0,number,integer}` for non-integer counts | May round when displayed. | Validate domain and choose a suitable formatter. |
| Assuming `java.text.MessageFormat` understands `plural`/`select` | That is not JDK MessageFormat syntax. | Choose ICU4J or a framework supporting it. |
| Passing only count without noun context | Insufficient data to select articles/adjectives. | Design an informative message contract. |
| Hardcoding plural tables for all locales with `if` | Hard to maintain, prone to missing cases and CLDR drift. | Use an updated library and test on real locales. |

## 13. Practice Exercises

**Exercise 1 — Scope ChoiceFormat:** create an English message with three branches `0`, `1`, and `>1`. Test integers 0, 1, 2, 20, as well as -1 and 1.5. State clearly which values fall outside the file-counting domain and what validation mechanism should be added.

**Exercise 2 — Russian counterexample:** with the pattern `0#many|1#one|2#few|5#many`, test 1, 2, 5, 11, 21, 22, 25, 101. Analyze why adding a few more thresholds still does not produce a right rule for **all** non-negative integers. Do not use the illustrative modulo snippet for decimal numbers.

**Exercise 3 — Gender independent of count:** given `archivo` and `carpeta`, both with count=1. Design an `enum` holding the necessary lexical metadata, then select translations for both nouns. Explain why count is insufficient to determine articles and adjectives.

**Exercise 4 — Choose an engine:** an application needs English, Vietnamese, Russian, and Arabic; quantities can be 1, 2, 21, 22, and 1.5. Compare handling this with JDK `ChoiceFormat` versus a framework with CLDR plural/select. Specify which situations can use a simple choice pattern and which cannot.

**Exercise 5 — Test translations:** take a message with count and grammatical gender. Write a test matrix covering the cardinal categories actually used by the locale, valid enum values, fallback translations, and missing-argument cases. Verify the **complete sentence** after formatting instead of only checking that the string contains the count.

## 14. Summary and Self-Assessment Criteria

- **`ChoiceFormat` selects a branch by numeric limits**, without computing CLDR plural categories.
- Plural rules such as Russian cycle by the last digit / last two digits; other languages may inspect decimal operands, ordinals, or additional categories.
- **Grammatical gender is lexical/grammatical data**, not a count value and not synonymous with user gender.
- Standard `java.text.MessageFormat` supports `choice`, but **does not support ICU `plural`/`select` syntax**.
- For complex grammar, use a locale-aware plural/select engine, full-sentence translations, and an explicit parameter contract; avoid twisting `ChoiceFormat` into a general-purpose grammar engine.

Learners meet the goal when they can identify **a suitable `ChoiceFormat` case**, **a modulo-based plural counterexample**, **a gender case that cannot be inferred from numbers**, and explain how to choose APIs to handle each issue properly for localization.
