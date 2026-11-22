# Recognizing When Linguistic Requirements Exceed Java Core APIs

Localization is more than swapping UI labels. A message sentence may need to change **plural forms**, **grammatical gender**, **verb conjugation**, **word order**, **noun grammatical case**, **ordinal forms**, or even the entire sentence structure depending on the language. Java Core supports storing translations with `ResourceBundle`, formatting numbers/dates with `NumberFormat` and `DateFormat`, interpolating variables into sentences with `MessageFormat`, and selecting by numeric intervals via `ChoiceFormat`. However, these APIs are **not a general-purpose grammar system** and do not automatically implement CLDR plural rules for every language.

The goal of this lesson is to know **how to recognize when linguistic requirements have exceeded Java Core APIs** so you can choose the right architecture and tools, rather than forcing complex grammar into a few `if` conditions, into `ResourceBundle`, or into `ChoiceFormat`.

## 1. The Boundary Between Formatting Data and Generating Natural Sentences

Distinguish three tasks:

1. **Retrieving a pre-written translation:** `ResourceBundle.getString("cart.title")` returns text by key and locale, possibly falling back to a parent bundle. It does not inflect nouns on its own.
2. **Formatting values:** `NumberFormat` formats `1234.5` by locale; `DateFormat` formats dates. These APIs do not decide which verb or noun form the whole sentence should use.
3. **Generating grammar-dependent messages:** “1 file” / “2 files”, “1 объект” / “2 объекта” / “5 объектов”, or altering greeting structures depending on the grammatical gender/case of sentence components. This is a linguistic problem, not just number insertion.

Simple English example:

~~~text
0 files
1 file
2 files
~~~

Assuming every language follows the rule “1 is singular, everything else is plural” will make the application wrong for languages with multiple count-dependent forms, for fractions, and in many situations with different grammatical contexts.

An example solely illustrating **Russian integer classification**:

~~~text
1  → one
2  → few
5  → many
11 → many
21 → one
22 → few
~~~

These are **classification group names**, not complete translations and not covering decimal numbers. The key point is that `21` can belong to the same group as `1`, while `11` belongs to a different group: the simple `count == 1` rule is insufficient.

## 2. What Can Java Core Do, and What Can It Not Do?

| Java 17 Tool | Appropriate Capability | Limitation to Recognize |
| --- | --- | --- |
| `Locale` | Describes language/region/script and locale options | Does not contain a built-in sentence-transformation engine or general grammar rules |
| `ResourceBundle` | Loads text/resources by key and locale chain | Does not automatically pick plural categories, gender, case, or verb forms |
| `MessageFormat` (`java.text`) | Substitutes arguments into patterns; formats number/date/time/choice | Does not support ICU MessageFormat `plural`, `select`, `selectordinal` syntax in Java 17 |
| `ChoiceFormat` | Selects strings by numeric thresholds via a declared pattern | Does not automatically apply locale-dependent CLDR rules; not a general plural engine |
| `NumberFormat` | Formats numbers, locale-dependent grouping separators/digits | Does not select word forms or sentence structures |
| `DateFormat` | Formats dates/times by locale | Does not guarantee generating every grammatical structure needed in natural sentences |

Distinguish **Java Core APIs** from external libraries with similar classes or names. For instance, `java.text.MessageFormat` **differs from** ICU4J's `com.ibm.icu.text.MessageFormat`: you cannot take an ICU pattern, pass it into `java.text.MessageFormat`, and expect it to understand all of that syntax.

**Version warning:** The assessments and examples here target Java 17. When upgrading the JDK or adding libraries/frameworks, verify the actual API contract; do not treat every class named `MessageFormat` as equivalent.

## 3. First Signal: Plurals Are No Longer “1 and Many”

When a requirement involves quantities, ask:

- Which languages are in the target language set?
- Are quantities **integers**, or can they be **decimals** (`1.0`, `1.5`, `2.25`)?
- Can they be **negative**, very large, or use numbers displayed after rounding?
- Are we talking about **cardinal** (counting “how many”) or **ordinal** (“which position”)?
- Do accompanying nouns/units change by **gender, case, or context**?

In CLDR, plural groups are named `zero`, `one`, `two`, `few`, `many`, `other`. These are **rule group names**; they do not mean a language necessarily uses all six groups, nor does `zero` simply mean “the number 0”, nor does `one` always mean the arithmetic value 1. Groups are determined by the language's rules and cardinal/ordinal context.

Examples:

- English in cardinal rules typically distinguishes `one` and `other`, yet decimal handling must follow CLDR rather than relying solely on an arbitrary comparison.
- Russian has `one`, `few`, `many` groups for many integers and decimal cases requiring separate handling; `11` and `21` must not be inferred from the same unit-digit check.
- Arabic has multiple counting groups, going far beyond a singular/plural choice.
- Vietnamese generally does not require English-style noun inflection by count, yet messages may still demand word selection, classifiers, or different phrasing; do not force English formulas onto Vietnamese.

**When does it exceed Java Core?** When a product must determine linguistic plural categories across multiple locales, especially with decimals and cardinal/ordinal distinctions, `ChoiceFormat` does not supply those rule sets automatically. You will either have to maintain custom rules — hard and error-prone — or adopt a tool with corresponding plural data/rules.

### ChoiceFormat is only numeric-threshold selection

`ChoiceFormat` can express:

~~~text
0#no files|1#one file|1<many files
~~~

In the pattern above, `#` selects from an inclusive threshold; `<` selects above a threshold (per `ChoiceFormat` rules). It is useful for a finite problem with defined rules. However, no parameter here tells Java to switch to Russian, Arabic, or Polish plural categories.

Numeric thresholds and CLDR groups are **not the same concept**. Russian rules depend on the units digit and last two digits; a handful of fixed intervals will not generalize to unbounded integers.

## 4. Second Signal: Ordinals Differ from Cardinals

The phrase “3 files” is **cardinal**; “3rd place” is **ordinal** in English. Both use different rules and messages. Do not reuse cardinal `one/other` logic to blindly build `st/nd/rd/th` suffixes:

~~~text
1st, 2nd, 3rd, 4th
11th, 12th, 13th
21st, 22nd, 23rd
~~~

A rule like “if the units digit is 1 then append `st`” fails on `11th`. When deploying multiple languages, some languages have very different ordinal forms or do not use suffixes like English.

**Signal of exceeding API capability:** Requirements to support rankings, calendar days of the month, positions, or ordering across many locales with accurate ordinal rules, rather than merely displaying a number. `NumberFormat` formats numbers without generating sentence ordinals; Java 17 `MessageFormat` does not support ICU's `selectordinal` pattern.

A system might choose to write dedicated full sentences for each finite rank (such as top 3) if business logic only has those exact cases. When inputs span arbitrary numbers and languages, a finite workaround is usually insufficient.

## 5. Third Signal: Selecting Gender and Sentence Structure, Not Just Noun Labels

Some messages must vary by **noun grammatical gender**, **subject category**, **form of address**, or agreement across words in the sentence.

Example specification:

~~~text
subjectCategory = masculine | feminine | neuter | other
count = 1 | 2 | 5 | ...
message = a complete sentence matching subjectCategory and count
~~~

This is a **data model**, not a Java Core pattern. Do not equate `subjectCategory` with a user's biological gender; in many languages, **grammatical gender is a property of words**. Collecting personal gender data solely to inflect sentences may be unnecessary and introduce privacy risks. Model the linguistic information actually needed for the message.

When a sentence varies by **both count and grammatical gender**, the number of branches can be the Cartesian product of choices and sometimes also depends on case, word order, or context. Concatenating “prefix + translated noun + suffix” can produce broken sentences in other languages due to word order and agreement.

**Signal of exceeding API capability:** Translators must author different complete sentences based on `gender/select` and `plural`, especially when nested. Java Core `MessageFormat` has no ICU `select`/plural syntax to express those grammatical branches directly inside translation data.

## 6. Fourth Signal: Case, Agreement, Context, and Inflection

Languages can alter the forms of nouns, adjectives, numerals, or verbs according to:

- **Grammatical case:** a word's role in the sentence changes its morphology, such as subject, object, or possessive roles in certain languages.
- **Agreement:** adjectives or verbs change to match the noun/subject.
- **Sentence context:** a short standalone label may take a different form when placed inside a sentence.
- **Prepositions or contractions:** decided by sound or sentence structure rather than word-by-word translation.
- **Part of speech or politeness level:** imperatives, questions, or prompts can vary substantially.

For instance, a business requirement “Display `{count}` products in `{location}` as a natural sentence for 12 languages” may demand inflecting the noun by count, changing prepositions, inflecting the place name's case, and reordering components. Java Core `MessageFormat` can insert the number and location into a template, but it **does not deduce linguistic syntax**.

Instead of assembling sentences from multiple fragments, let translators control sentence templates **at the level of a complete message**, and use a suitable API or library so grammatical conditions live in managed content. In particularly complex cases, even plural/select formatters may be insufficient; specialized templates, inflection data supplied by linguists, or a separately tested natural-language generation layer may be required.

## 7. Runnable Java 17 Example: How Far Does Java Core Go?

The following program does three things:

1. Uses `java.text.MessageFormat` with a `choice` branch for **a simple English example**.
2. Illustrates a **custom rule** grouping **Russian non-negative cardinal integers**, solely to demonstrate why “1 vs. not 1” logic is insufficient. This method is **not** a general CLDR engine.
3. Shows that an ICU `plural` pattern is **not** accepted by Java 17 `java.text.MessageFormat`.

Create the file **`CoreGrammarLimitsDemo.java`**:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class CoreGrammarLimitsDemo {
    static String simpleEnglish(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        MessageFormat format = new MessageFormat(
                "{0,choice,0#no files|1#one file|1<{0,number,integer} files}",
                Locale.US);
        return format.format(new Object[] { count });
    }

    // Illustrates cardinal grouping for Russian non-negative integers only.
    // Does NOT handle decimals, ordinals, grammatical gender, or case.
    static String russianIntegerCategory(long count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must be >= 0");
        }
        long last10 = count % 10;
        long last100 = count % 100;
        if (last10 == 1 && last100 != 11) {
            return "one";
        }
        if (last10 >= 2 && last10 <= 4
                && (last100 < 12 || last100 > 14)) {
            return "few";
        }
        return "many";
    }

    public static void main(String[] args) {
        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println(
                    "EN " + count + ": " + simpleEnglish(count));
        }
        for (long count : new long[] { 1, 2, 5, 11, 21, 22 }) {
            System.out.println("RU " + count + ": "
                    + russianIntegerCategory(count));
        }

        try {
            new MessageFormat(
                    "{count, plural, one{item} other{items}}",
                    Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "ICU plural pattern: unsupported by Java 17");
        }
    }
}
~~~

Compile and run (JDK 17 or later):

~~~bash
javac -encoding UTF-8 CoreGrammarLimitsDemo.java
java CoreGrammarLimitsDemo
~~~

Stdout verified with the JDK:

~~~text
EN 0: no files
EN 1: one file
EN 2: 2 files
RU 1: one
RU 2: few
RU 5: many
RU 11: many
RU 21: one
RU 22: few
ICU plural pattern: unsupported by Java 17
~~~

Explanation:

- `choice` is a reasonable approach for the illustrative English message with non-negative integers, but this pattern is **hardcoded** by the developer rather than derived from CLDR.
- `russianIntegerCategory` demonstrates grouping by `% 10` and `% 100`, so `11` belongs to `many` while `21` belongs to `one`. Real-world problems also consider decimal forms and other CLDR factors; do not use this illustrative method as a production rule for all number forms.
- The `plural` keyword in an ICU pattern is not a format type in Java 17 `java.text.MessageFormat`. The constructor throws `IllegalArgumentException`, caught here to demonstrate the limitation.
- The answers `one/few/many` are merely **classification labels**, not complete Russian translations. For real translations, translators must supply a template for each applicable category, and may also need to account for case, gender, and context.

**Do not misunderstand:** The fact that an application can write its own `if`, `switch`, or inflection algorithm in Java does not mean **standard Java Core APIs provide that linguistic data and those grammar rules**. When writing it yourself, the entire burden of linguistic accuracy, maintenance, and testing falls on the application.

## 8. When Is Java Core Still Enough?

Not every message containing a number requires an external library. Java Core can suffice when:

- The system supports only **a few languages with bounded, verified rules**.
- Each grammatical choice has a **small finite set** and the product can use separate complete messages.
- Sentences do not depend on complex gender/case/ordinals; they only need data formatting and choosing a pre-written template.
- The team can verify the entire input set and update translations through proper workflows.

A simple, explicit design:

~~~properties
# messages_en.properties
notification.one=You have {0} notification.
notification.other=You have {0} notifications.
~~~

~~~java
// Illustrative snippet inside a program that already has ResourceBundle bundle,
// valid int count, and the user's Locale locale.
String key = (count == 1)
        ? "notification.one"
        : "notification.other";

String template = bundle.getString(key);
String message = new MessageFormat(template, locale)
        .format(new Object[] { count });
~~~

This snippet only illustrates how the **application** selects a key. `ResourceBundle` does not pick `one/other` itself; `MessageFormat` merely inserts values into the template. If switching to Russian or Arabic, you must not keep the `count == 1` selection logic.

Put complete sentences in each branch instead of giving translators separate fragments like `prefix`, `noun`, `suffix` and joining them with `+`. Word order and inflection can differ across languages.

## 9. When Must You Choose an i18n Library with Linguistic Rules?

Evaluate a specialized solution when one or more of the following requirements appear:

| Requirement Signal | Risk If Using Only Java Core | Required Solution Criteria |
| --- | --- | --- |
| Multiple languages with differing plurals | Wrong counts or wrong noun forms | Locale-aware CLDR cardinal plurals |
| Decimals and complex rules | `count == 1` / integer modulo is wrong | Accurate operands and decimal grouping |
| Locale-specific ordinals | Produces wrong rankings | Dedicated ordinal rules |
| Selecting by grammatical gender | Broken concatenation or wrong agreement | `select` conditions or equivalent sentence templates |
| Nesting plural and select | Explosion of `if/else` in code | Support for expressing nested branches and testing |
| Multiple case/agreement variants | Broken sentence structure | Translator-controlled sentence template data/strategy |
| Frequently updated translations | Linguistic logic scattered in source code | Centralized template management, validation, and versioning |
| Templates translated by a multilingual team | Translators cannot edit Java logic | Consistent message syntax and tooling |

A common choice in the Java ecosystem is **ICU4J** along with CLDR-based data and rules. ICU4J provides APIs for plural rules and message formatting, including plural/select branch selection in supported versions. However:

- ICU4J is a **library outside the JDK**; you must declare the dependency and check versions and licensing per project policy.
- **Do not** pass ICU patterns into `java.text.MessageFormat`; use the formatter class of the corresponding library.
- Even a good plural/select library **does not translate content automatically**. Translators must still provide accurate messages and clarify linguistic requirements.
- Verify the CLDR data and ICU version used when rules change; upgrading the library can alter classification results at edge cases.
- Do not assume a single API automatically solves all case/agreement/inflection issues. Complex grammar may require multiple complete templates, inflection data, or linguistic editing workflows.

Example of a **conceptual pattern in ICU MessageFormat syntax**, **not runnable with Java 17 `java.text.MessageFormat`**:

~~~text
{count, plural,
    one {# item}
    other {# items}
}
~~~

This pattern only illustrates storing plural choices in translator-managed resources. Do not use it directly as runnable Java code. Which groups are needed, the text of each group, and number insertion must be verified against the target locale. For languages other than English, writing only `one/other` may not be enough.

## 10. You Cannot Rely Solely on Locale and ResourceBundle

`Locale.forLanguageTag("ru-RU")` creates a valid `Locale`, yet **it is not proof that the program has Russian plural rules**. `NumberFormat.getInstance(locale)` formats numbers by locale, yet does not distinguish `one/few/many` in messages. `ResourceBundle.getBundle("messages", locale)` selects resource sets by locale and can traverse parent bundles, yet **it does not inspect count or grammatical gender itself**.

Another mistake is treating parent-resource fallback as grammatical fallback. When the `ru-RU` bundle lacks the plural key `files.few`, Java may find a string from a parent bundle; that string is not guaranteed to fit Russian plural grammar. Treat **complete and accurate language branches** as a translation data requirement, not just whether `containsKey` returns `true`.

Typical processing order:

~~~text
User request / locale
       |
       v
Select an application-supported locale
       |
       v
Classify grammatical conditions by locale
    (count, ordinal, select, context...)
       |
       v
Retrieve the appropriate translator-supplied message
       |
       v
Format values and placeholders
       |
       v
Test the complete output sentence
~~~

Steps may be combined inside a single API of a dedicated formatter library, yet each responsibility should still be audited when designing the system.

## 11. Checklist of Questions Before Choosing Tooling

Before picking Java Core `MessageFormat` or ICU4J/an i18n framework, write down clearly:

1. **Which languages and regional variants** are required? E.g., `en-US`, `ru-RU`, `ar`, `pl-PL`, `vi-VN`.
2. **What kind of count data is used?** Only non-negative integers, or also `0`, `-1`, `1.0`, `1.5`, `2.25`, very large numbers?
3. **Are cardinals or ordinals used?** One UI may contain both “3 items” and “3rd item”.
4. **Are there non-numeric conditions?** Grammatical gender, roles, object types, action states, forms of address?
5. **Do selections nest?** For example, count and gender simultaneously affecting the sentence.
6. **Who manages translation data?** Developers or translators; is updating copy without code releases required?
7. **How far is fallback allowed?** Can another language be used, or must missing proper templates be rejected?
8. **What are the test criteria?** A few illustrative examples or a matrix of locale × category × number type × context?
9. **Is updated linguistic data required?** If using CLDR, which version and what upgrade policy?
10. **Are there legal or high-accuracy constraints?** For sensitive content, linguist/translator approval is required.

After answering, you can make a verifiable technical decision:

- If messages are completely static: `ResourceBundle` is enough.
- If interpolating dates/numbers with a small finite set of choices: `MessageFormat`/Java Core may suffice.
- If multilingual CLDR-based cardinals/ordinals are needed: consider a library with corresponding rules.
- If gender/case/agreement or nested conditions exist: you need a formatter and resource model for grammatical branches, plus linguistic review.
- If natural inflection in open contexts is required: verify whether a formatter suffices or a specialized architecture and linguistic editing are needed.

## 12. Common Mistakes and Consequences

| Mistake | Why It Is Wrong | Prevention |
| --- | --- | --- |
| Using `count == 1` for all languages | Locales have differing group counts and rules | Determine rules by locale and plural type |
| Using the same logic for cardinal and ordinal | Groups and contexts differ | Separate counting and ordering purposes |
| Using `ChoiceFormat` as a CLDR plural engine | Choice selects by thresholds; lacks linguistic rules | Use a rule engine when supporting multiple locales |
| Passing an ICU `plural` pattern to `java.text.MessageFormat` | Syntax is unsupported in Java 17 | Use a formatter that actually supports the syntax |
| Assuming `ResourceBundle` picks `files.one`/`files.other` automatically | Bundle only looks up values by key | Write explicit logic or use a specialized formatter |
| Concatenating prefix + number + noun | Wrong word order, agreement, or grammatical case | Use complete sentence templates authored by translators |
| Classifying plurals from rounded numbers only | Decimal operands can change the category | Design formatting/counting policy and test it |
| Using “user gender” in place of grammatical gender | Wrong model and unnecessary data collection | Separate linguistic attributes from personal data |
| Assuming any missing key can safely fall back to source language | Fallback template may be grammatically wrong | QA key coverage and content-aware fallback policy |
| Using a few examples 1, 2, 3 as proof of language support | Fails to check 0, 11, 21, decimals, and ordinals | Test across CLDR groups and boundaries |
| Scattering unverified linguistic rules across many `if` statements | Hard to maintain and bug-prone when adding languages | Centralize rules/templates with expert verification |

## 13. Test the Right Boundaries, Not Just Formatting

A test plan for a localization system with plurals/grammar should include:

- **By locale:** test every genuinely supported language, not just `Locale.US`.
- **By category:** test representatives of every plural category that can occur in that locale.
- **By number type:** `0`, `1`, `2`, `5`, `11`, `21`, `22`, `101`, fractions, and decimals if business logic permits them.
- **By context:** cardinal, ordinal, gender/case/agreement where applicable.
- **By resource data:** missing branches, missing keys, wrong placeholders, wrong argument counts, escaping errors, and post-update translation regressions.
- **By stability:** changing the JVM default locale must not silently alter business decisions; ICU/CLDR version upgrades require deliberate output verification.
- **By final output:** test not only the category, but the full sentence after substituting numbers and arguments, reviewed by someone fluent in the language.

Example boundary test table for the illustrative Russian method **accepting non-negative integers only** in section 7:

| Input | Expected Category | Explanation |
| ---: | --- | --- |
| 0 | `many` | Zero case in the illustrated integer set |
| 1 | `one` | Units digit 1, not ending in 11 |
| 2 | `few` | Units digit 2, not ending in 12 |
| 5 | `many` | Not in one/few branches |
| 11 | `many` | Exception 11 |
| 12 | `many` | Exception 12 |
| 14 | `many` | Exception 14 |
| 21 | `one` | Last two digits 21 |
| 22 | `few` | Last two digits 22 |
| 101 | `one` | Last two digits 01 |

**Do not extrapolate this conclusion to decimals.** In CLDR, the number 1 and representations like `1.0` can affect operands or plural rules depending on the language and API. Decide the numeric data model and library formatter before setting expectations.

## 14. Self-Assessment Exercises

**Question 1.** A system only has Vietnamese and English, displaying only static labels and one locale-formatted number. Is ICU4J mandatory?

**Answer:** No. Without complex grammatical requirements, `ResourceBundle` and `NumberFormat` can suffice. Base the decision on requirements, not on how many libraries are used.

**Question 2.** A product wants to support Russian, Polish, and Arabic with integer and decimal counts. Is using only `ChoiceFormat` considered proper plural support?

**Answer:** That cannot be concluded. `ChoiceFormat` does not automatically apply CLDR rules per language and number type. Choose an appropriate rule set/engine, check number representation, and test each category.

**Question 3.** Why does `Locale.forLanguageTag("ru-RU")` not automatically make messages grammatically correct Russian?

**Answer:** `Locale` only describes linguistic context; translations, plural rules, and inflections still require appropriate data and logic.

**Question 4.** Can `"{count, plural, one{...} other{...}}"` be passed to Java 17 `java.text.MessageFormat`?

**Answer:** No. That is an ICU pattern form, not Java 17 `java.text.MessageFormat` plural syntax; a formatter supporting ICU patterns or a different design is needed.

**Question 5.** Why should a `gender` variable in a sentence template not default to user gender data?

**Answer:** Grammatical gender can be a property of nouns/objects in the sentence, independent of human gender. Collect and use only data genuinely needed by business logic and appropriate for the context.

**Practice task.** Write a requirements specification for the message “{count} items were processed by {actor}” across three locales with an optional rank display. Indicate which parts are handled by `NumberFormat`, which need plural/ordinal/select, and which must be confirmed by translators. Build a test table containing 0, 1, 2, 11, 21, and a decimal number. Then assess whether Java Core suffices or another grammar engine is needed, stating reasons for each decision.

## 15. References

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): syntax of `java.text.MessageFormat`, format types, and `choice`.
- [Java SE 17 — ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html): range-based selection and pattern limitations.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): storing messages by locale, not a grammar engine.
- [Unicode CLDR — Language Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): language plural rules and grouping principles.
- [ICU User Guide — Formatting Messages](https://unicode-org.github.io/icu/userguide/format_parse/messages/): plural/select concepts in the ICU ecosystem.

**Conclusion:** Java Core excels at **selecting locales, finding resources, formatting data, and interpolating arguments**. When requirements demand **locale-accurate plurals/ordinals, gender selection, agreement, case, or nested grammatical conditions**, recognize this as a **rule-governed linguistic problem**, evaluate an appropriate formatter/library, and build tests with approved translations. Do not assume a few `if` branches or `ChoiceFormat` solve every language properly.
