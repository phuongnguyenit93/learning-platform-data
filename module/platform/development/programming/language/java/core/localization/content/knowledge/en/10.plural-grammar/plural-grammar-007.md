# Separating Complete Sentence Templates and Providing Context for Translations

## 1. The Problem: Translation Is Not Word-by-Word Substitution

In Java localization, splitting a sentence into small fragments and concatenating them at runtime often seems convenient:

```java
// Do not use as a design for multilingual content
String message = prefix + count + suffix;
```

However, natural-language sentences have **word order, plurals, grammatical gender, forms of address, and context**. There is no guarantee that every language places the count between the exact same two fragments as English. A short word can also have multiple meanings: `Open` as an action button (e.g., “Mở” in Vietnamese), whereas `Open` as a store status means “Open for business” (e.g., “Đang mở cửa” in Vietnamese); `Save` is a save command, while in another context it can mean saving money.

Important principle:

> **Extract an entire meaningful message as one translation unit**, containing placeholders with clear semantics. Give translators enough context so they can rewrite the whole sentence naturally in the target language.

In Java, a common implementation puts complete sentences in a `ResourceBundle` and uses `MessageFormat` to insert data. This lets translations **reorder placeholders**, adjust phrasing, and, when needed, select variants by quantity or grammar.

This lesson focuses on: **meaningful message units**, **context documentation for translators**, **placeholder contracts**, **plurals and grammatical variants**, and **testing real translations**.

## 2. Why Does String Concatenation Destroy Translation Quality?

### 2.1. Word order is not fixed

Suppose an application has two variables `customer` and `orderId`. Fragment concatenation:

```java
// Anti-pattern: fragments stored across multiple resource keys
String text = bundle.getString("hello.prefix")
        + customer
        + bundle.getString("order.middle")
        + orderId
        + bundle.getString("order.suffix");
```

This assumes translators must preserve the exact order: greeting → customer name → middle text → order ID → ending. However, a Vietnamese translation may be more natural starting with the **order** and then the **customer name**. Translators cannot swap the order of those two values if the program hardcodes it through concatenation.

Replace it with **one complete meaningful message**:

```properties
# Messages_en.properties
order.ready=Hello {0}, order {1} is ready.
```

```properties
# Messages_vi.properties
order.ready=Đơn hàng {1} của {0} đã sẵn sàng.
```

With the same data `{0} = "Lan"`, `{1} = "A-7"`, the two resulting sentences are respectively:

```text
Hello Lan, order A-7 is ready.
Đơn hàng A-7 của Lan đã sẵn sàng.
```

The difference resides entirely in the **sentence template**, without needing `if (locale...)` in Java to swap text segments.

### 2.2. Plurals can change the entire sentence

English example:

```text
You have 1 new message.
You have 3 new messages.
```

If you only translate the noun `message` separately and append `s`, the application has hardcoded English grammar into the program. That approach fails for many languages: some need multiple quantity groups; some inflect words or change other parts of the sentence; some do not inflect nouns by count like English.

Even the zero-message case may require a **distinct sentence**:

```text
You have no new messages.
Bạn không có thông báo mới.
```

Do not treat `0`, `1`, and “many” as merely a few word endings that can be translated in isolation. Choose **complete sentence templates** for the required variants.

### 2.3. Grammatical gender, participant roles, and context

A message may depend on the actor performing an action, the affected object, or an accompanying noun. For instance, content like “{person A} invited {person B}” may have a different structure in the target language. Translators also need to know whether `{0}` displays a **person's name**, an **ID**, a **timestamp**, or a **quantity**.

**Do not infer grammatical gender rules from a user's personal gender** arbitrarily; use only attributes that business data actually supplies and the target language requires. For many systems, designing neutral sentences that avoid grammatical-gender dependencies is easier to localize.

## 3. Identifying the Right Translation Unit

A good **translation unit** is a meaningful message in a specific display context. It does not always have to be a long paragraph; a standalone label like “Search” can be a translation unit. However, **you must not cut a sentence requiring unified grammar into arbitrary fragments**.

| Design to Avoid | Why Is It Problematic? | Better Design |
| --- | --- | --- |
| `"You have " + n + " new message" + pluralSuffix` | Plural suffix and word order are hardcoded | Complete sentence templates `inbox.zero`, `inbox.one`, `inbox.other` per language policy |
| `"Hello " + name + ", order " + id + " is ready."` | Translators cannot reorder name and ID | `order.ready=Hello {0}, order {1} is ready.` |
| `"Open"` reused everywhere | Unclear whether it is an action or a status | `file.action.open`, `store.status.open` |
| Concatenating `"From"` + name + `"to"` + name | Word order or prepositions may change in other languages | One complete message with two placeholders |
| Translating a single word and reusing it in titles, buttons, tooltips | The same source word can have different meanings | Separate keys and context per function |

The **“one meaningful unit”** principle does not mean blindly duplicating the exact same sentence in hundreds of places: when two places share the **same meaning, same role, and same UI constraints**, a single key can be reused. But if the contexts differ, sharing a key simply because the English text looks identical easily leads to wrong translations.

## 4. What Context Should Be Provided to Translators?

Translators do not see the entire source code or business flow. A string like `Open`, `Pending`, `1 of 3`, or `{0} added {1}` **does not carry enough information to translate accurately**. Attach **translator context** to each translation unit:

1. **Display purpose:** button, heading, status, toast, email, confirmation notice, accessibility label, or form error?
2. **Location and UI screenshot:** which screen, what precedes/follows it, and who is the reader?
3. **Business meaning:** does “open” mean “open a file” or “currently open for business”? Does “charge” mean billing or battery charging?
4. **Description of every placeholder:** `{0}` is a person's name; `{1}` is an order ID; `{2}` is an already **formatted** monetary amount. Do not just write “arg 0, arg 1”.
5. **Data types and examples:** counts `0/1/2/5`, long sample names, hyphenated IDs, localized dates/times, data containing special characters.
6. **Grammatical variants:** zero, one, many cases; participant roles; grammatical gender if the product actually manages that information.
7. **UI constraints:** suggested length, max label width, line-wrapping capability, RTL support, whether abbreviations are allowed.
8. **Formatting/markup:** does the placeholder contain plain text, links, currency, or markup? Are there special `MessageFormat` characters that must be preserved?
9. **Behavior when translation is missing:** which language does it fall back to? Should tone favor formal or informal register?

Example of a key with good context:

```text
Key: order.ready
Source: Hello {0}, order {1} is ready.
Description: Notification shown after an order finishes preparing.
{0}: displayName — customer's display name, e.g., "Lan".
{1}: orderId — order identifier, e.g., "A-7", keep unchanged.
Audience: buyer/customer.
Tone: concise, polite; placeholder order may be changed.
UI: line wrapping allowed; neither placeholder may be removed.
Screenshot: image of the order-tracking screen in the translation system.
```

`#` comments in `.properties` files can help someone reading the file, but **`ResourceBundle` does not return those comments via `getString`**. Translation management platforms should store context as separate metadata, companion files, or comments preserved by extraction tools. Do not assume every pipeline passes comments verbatim to translators.

## 5. Name Keys by Meaning and Context, Not by Literal English Text

Resource keys should remain stable when wording changes:

```properties
order.ready=Hello {0}, order {1} is ready.
checkout.payment.failed=Payment failed. Please try again.
file.action.open=Open
store.status.open=Open
```

The last two keys have the same English text but **different translation contexts**. In Vietnamese, suitable translations might be `Mở` and `Đang mở cửa`.

Avoid keys like `YouHaveNewMessages`, `hello_prefix`, or keys equal to the full English string if they make copy edits equivalent to API changes and make context hard to maintain. Keys can be grouped by feature and message type: `inbox.empty`, `inbox.count`, `order.ready`, `file.action.open`.

**A key does not necessarily correspond to a single period-terminated sentence:** headings, standalone CTAs, and `aria-label`s are still functionally complete units. The criterion is that the translator knows the **purpose and grammatical context** of that unit.

## 6. Runnable Example: Complete Sentences, Placeholder Order, and Counts

The following example uses Java 17+, `ResourceBundle` + `MessageFormat`. It illustrates:

- Each count variant is translated as a **complete sentence**, without prefix/suffix concatenation.
- Translations are free to **swap the order of `{0}` and `{1}`**.
- Keys and values in resources form a **contract** between code and translators.

Create the directory structure:

```text
workspace/
├── src/
│   └── demo/
│       └── MessageContextDemo.java
└── demo/
    ├── Messages.properties
    ├── Messages_en.properties
    └── Messages_vi.properties
```

**`demo/Messages.properties`** — base English fallback:

```properties
inbox.zero=You have no new messages.
inbox.one=You have {0} new message.
inbox.other=You have {0} new messages.
order.ready=Hello {0}, order {1} is ready.
```

**`demo/Messages_en.properties`**:

```properties
# inbox.*: Unread message count notice. {0}: non-negative integer count.
inbox.zero=You have no new messages.
inbox.one=You have {0} new message.
inbox.other=You have {0} new messages.
# order.ready: {0} is customer name, {1} is order ID.
order.ready=Hello {0}, order {1} is ready.
```

**`demo/Messages_vi.properties`**:

```properties
# inbox.*: New notification count. {0}: non-negative integer count.
inbox.zero=Bạn không có thông báo mới.
inbox.one=Bạn có {0} thông báo mới.
inbox.other=Bạn có {0} thông báo mới.
# order.ready: {0} is customer name; {1} is order ID, reordered.
order.ready=Đơn hàng {1} của {0} đã sẵn sàng.
```

**`src/demo/MessageContextDemo.java`**:

```java
package demo;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageContextDemo {
    private static final String BASE_NAME = "demo.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static String format(ResourceBundle bundle,
                                 Locale locale,
                                 String key,
                                 Object... arguments) {
        return new MessageFormat(bundle.getString(key), locale)
                .format(arguments);
    }

    private static void showCount(Locale locale, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE_NAME, locale, CONTROL);

        // Illustrative policy only for the two implemented languages.
        String key = count == 0 ? "inbox.zero"
                : count == 1 ? "inbox.one"
                : "inbox.other";

        System.out.println(locale.toLanguageTag() + " | "
                + format(bundle, locale, key, count));
    }

    private static void showOrder(Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE_NAME, locale, CONTROL);
        System.out.println(locale.toLanguageTag() + " | "
                + format(bundle, locale, "order.ready", "Lan", "A-7"));
    }

    public static void main(String[] args) {
        Locale english = Locale.forLanguageTag("en-US");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        showCount(english, 0);
        showCount(english, 1);
        showCount(english, 3);
        showOrder(english);

        showCount(vietnamese, 0);
        showCount(vietnamese, 1);
        showCount(vietnamese, 3);
        showOrder(vietnamese);
    }
}
```

From the `workspace` directory, run with JDK 17+:

```bash
javac -encoding UTF-8 -d . src/demo/MessageContextDemo.java
java -cp . demo.MessageContextDemo
```

Output (with a properly configured UTF-8 terminal):

```text
en-US | You have no new messages.
en-US | You have 1 new message.
en-US | You have 3 new messages.
en-US | Hello Lan, order A-7 is ready.
vi-VN | Bạn không có thông báo mới.
vi-VN | Bạn có 1 thông báo mới.
vi-VN | Bạn có 3 thông báo mới.
vi-VN | Đơn hàng A-7 của Lan đã sẵn sàng.
```

### Why is this example noteworthy?

**No code concatenates “You have”, noun names, or plural suffixes separately.** Java simply selects a **semantic key** and supplies data to the translated sentence. The Vietnamese translator rewrote the whole `order.ready` sentence to put the order ID before the customer name, yet the `{0}` and `{1}` contract remained intact.

`ResourceBundle` finds `Messages_en.properties` when requesting `en-US`, and `Messages_vi.properties` when requesting `vi-VN`. `getNoFallbackControl` skips trying the JVM default locale while still allowing the root resource; this policy keeps the example deterministic. Properties files must be on the runtime classpath at the exact `demo/` path.

**Intentional limitation:** the `count == 0 / 1 / other` condition only illustrates **English and Vietnamese messages in this lesson**; it is **not a shared plural algorithm for all languages**. Some languages have more plural categories or complex decimal rules. For real multilingual applications, use locale plural rules (such as a CLDR/ICU-based system when appropriate) rather than copying these branches to every country.

## 7. Plurals: Separating Sentence Variants and Choosing the Right Language Rules

Two tasks must be distinguished:

1. **Selecting the grammatical variant** for a specific count/quantity.
2. **Formatting the printed number** for the selected locale.

`NumberFormat` handles number representation, not overall noun grammar. Standard `java.text.MessageFormat` supports formats like `number` and `choice`, but it is **not a complete CLDR plural engine** with `zero`, `one`, `two`, `few`, `many`, `other` labels automatically applied for every locale.

For example, `ChoiceFormat` can select among branches based on numeric thresholds:

```java
// Illustrative snippet: not a general plural rule.
String pattern = "{0,choice,0#No items|1#One item|1<Many items}";
String text = new MessageFormat(pattern, Locale.US)
        .format(new Object[] {3});
```

The result `text` is `Many items`. However, those thresholds only express a **specific policy** of the pattern, not a replacement for plural rules of Arabic, Russian, Polish, and other languages.

If using a system that supports **CLDR plural categories**, the labels `zero/one/two/few/many/other` must be selected **by locale rules**, rather than naively assuming `one` always equals 1 or `few` always equals 2–4. Even the value 0 is sometimes expressed by `other` under a language's rules; a sentence like “No items” can still be an **explicit business special case** designed deliberately.

### Why keep complete sentences in every branch?

You should not define only:

```text
singularSuffix=""
pluralSuffix="s"
```

Instead, use complete sentence units such as `inbox.one` and `inbox.other`, or a plural message supported by an l10n tool. Translators may need to change **verbs, grammatical cases, articles, adjectives, count placement, and nouns** all at once. The translation system should display all branches side by side and indicate where they appear.

## 8. Providing an Explicit Placeholder Contract

Placeholders are **variables/semantic slots**, not text to be translated arbitrarily. With Java `MessageFormat`, common forms are `{0}`, `{1}`, `{2,number}`, `{3,date}`.

Example contract:

| Placeholder | Meaning | Data Type | Example | What Translators Need to Know |
| --- | --- | --- | --- | --- |
| `{0}` | Customer display name | `String` | `Lan` | May be long or contain quotes; do not alter meaning |
| `{1}` | Order ID | `String` | `A-7` | Do not translate code content; position may move |
| `{2}` | Unread count | `int` or `Number` | `3` | Plural rules require separate handling |
| `{3}` | Timestamp | `Temporal/Date` per API used | Delivery date | Choose appropriate timezone/calendar and formatting style |

In `MessageFormat`, **the element order of `Object[]` must obey the contract** even when translators are allowed to **reorder placeholders inside the pattern**. If Vietnamese content places `{1}` before `{0}`, Java still passes arguments in the original order `{"Lan", "A-7"}`.

Do not tell translators to “keep placeholder positions unchanged”, because that defeats grammatical reordering. Instead require: **preserve the placeholder set, indices, and meanings**, allowing positions to move if the sentence needs it; if repeating an argument in a translation is needed, verify whether the API supports it.

### Meaningful parameter names and `MessageFormat` limits

Standard Java `MessageFormat` uses **numeric indices** such as `{0}` and does not natively support named placeholders like `{customerName}`. Thus a service layer can define semantic names in code/metadata and map them to indices when building `Object[]`. With l10n platforms supporting named placeholders, an explicit contract on types and meanings is still required.

Do not arbitrarily mix ICU MessageFormat syntax with `java.text.MessageFormat`; another library's `plural` or `select` features do not run out of the box in the standard Java parser. Choose one engine, document its syntax, and validate all resources against that engine.

## 9. Caution with `MessageFormat`, Escaping, and Dynamic Data

When complete sentences contain single quotes and curly braces, `MessageFormat` has its own escaping rules:

- `{0}` is a placeholder; to display the text `{0}` literally as characters, use `'{0}'` in the pattern.
- `''` in a pattern prints one literal single quote. For example, `It''s {0}.` produces `It's Lan.`.
- `'{'` and `'}'` print literal opening and closing braces respectively.
- An unclosed single quote can cause placeholders to be printed verbatim **without throwing an exception**.
- Backslashes belong to Java source or properties escaping at separate layers; they do not replace `MessageFormat`'s single-quote mechanism.

For **argument** text such as `O'Brien` or `{0}` inside a person's name, `MessageFormat` does not re-parse it as an ordinary pattern. Do not double single quotes in input data and produce corrupted display names. Apply `MessageFormat` quoting rules only to **patterns**.

**Security boundary:** an i18n system does not automatically prevent XSS when the resulting string is inserted into HTML. If a web app displays messages, escape/encode for the **output context** and use safe component/template APIs. Do not treat translators or placeholders as trusted HTML, and do not concatenate unvalidated markup/URLs into sentences; bold text and links should be represented as separate UI components or allowed structures with clear boundaries.

## 10. Context for Translators When Complex Grammar Applies

### 10.1. Do not force translators to guess gender or roles

For example, the message “{0} sent {1} an invitation” involves two participants. A target language may need to adjust phrasing depending on the actor or recipient. If a translator only sees `{0} invited {1}` without knowing roles, they can easily reverse the action's direction.

Describe it explicitly:

```text
{0}: invitation sender (actor)
{1}: invitation recipient (recipient)
Reader: notification recipient
Context: system notification immediately after a successful send action
```

If the product lacks the required grammatical data, consider a **neutral sentence** instead of assuming gender or guessing from a person's name.

### 10.2. Do not reuse the same word across different contexts

A label `Archive` can be an **archive action**, a **records folder**, or an **archived status**. Even when the source uses the exact same word, translations may differ in part of speech and nuance. Use separate keys per meaning:

```properties
document.action.archive=Archive
navigation.archive=Archive
document.status.archived=Archived
```

Do not share keys merely to reduce line counts in resources. What matters is not minimizing key count, but **preserving accurate semantics**.

### 10.3. Mind UI length and text layout

A complete, natural sentence can be longer than the English version. Allow the UI to wrap lines or resize appropriately, and test on mobile and across font sizes and accessibility settings. If applying character limits, clarify whether they are hard limits or guidelines; do not force translators to drop essential information without a design solution.

### 10.4. Proper names, numbers, dates, currency, and units

Translators need to know whether a placeholder holds **raw data** or an **already-formatted string**. For example:

- Order IDs and identifiers: usually kept unchanged, untranslated.
- Monetary amounts: use numeric value + currency code from business data; never convert currency just because the locale changed.
- Dates and times: locale determines display format, while `ZoneId` is separate information.
- Quantities: may require a **numeric value** to select plural branches, not just a formatted string.

Do not let translators edit or replace placeholders with fixed characters in the sentence. Messages must work for every valid application value, not just a sample screenshot.

## 11. Test Both Translations and Context, Not Just Syntax

An ideal verification step combines **automated tests** with **in-UI linguistic review**:

1. **Check key completeness:** every committed supported locale has required keys or an explicitly defined fallback. Missing keys can make `ResourceBundle` silently pull strings from a parent bundle without errors.
2. **Check placeholders:** translations do not drop required `{0}`, `{1}` or mix up indices; allow grammatically valid reordering. Use a parser/contract check aligned with the engine rather than merely counting strings with regex.
3. **Parse patterns:** try constructing `MessageFormat` for all patterns; check single quotes, braces, and subformats. Note that parser acceptance does not prove the message means the right thing.
4. **Check formatted output:** use representative values; compare complete sentences across deployed locales.
5. **Check quantity cases:** 0, 1, 2, 5, large numbers, and decimals if applicable. With CLDR plural libraries, use representative values per **locale** to hit every category.
6. **Check reordered parameters:** translations may print `{1}` before `{0}`; use two easily distinguishable values (such as name `Lan` and ID `A-7`) to catch swapped indices.
7. **Check UI context:** take screenshots with real/mocked data, inspect button placement, headings, statuses, Vietnamese diacritics, fonts, widths, small screens, and accessibility.
8. **Check strings with apostrophes:** `It's`, `don't`, names like `O'Brien`; distinguish quotes in patterns from data.
9. **Check languages with different grammar:** are additional variants needed by role, quantity, grammatical gender, or register? Do not treat English as the sole grammatical model.
10. **Check versioned contracts:** when adding/modifying placeholders, notify the translation team, update context, and test old translations before release.

A small Java test can lock down a two-parameter contract:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ContextContractTest {
    public static void main(String[] args) {
        String english =
                "Hello {0}, order {1} is ready.";
        String vietnamese =
                "Đơn hàng {1} của {0} đã sẵn sàng.";

        Object[] values = {"Lan", "A-7"};

        String en = new MessageFormat(english, Locale.US)
                .format(values);
        String vi = new MessageFormat(vietnamese,
                Locale.forLanguageTag("vi-VN"))
                .format(values);

        if (!en.equals("Hello Lan, order A-7 is ready.")) {
            throw new AssertionError(en);
        }
        if (!vi.equals("Đơn hàng A-7 của Lan đã sẵn sàng.")) {
            throw new AssertionError(vi);
        }
        System.out.println("2 context checks passed");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ContextContractTest.java
java -cp . ContextContractTest
```

Output when the contract and sentence templates are correct:

```text
2 context checks passed
```

This is a **contract** test and cannot replace translation quality review; grammatically broken sentences that still contain all placeholders can still pass automated checks.

## 12. Collaboration Workflow Between Developers and Translators

**Before sending source text to translators:**

- Choose keys carrying business meaning rather than relying on English phrasing.
- Design each message as a **complete unit**; do not split it into fragments just to concatenate at runtime.
- For messages with variables, write context for each placeholder; supply screenshots, example values, and quantity branches.
- Specify the message engine (`java.text.MessageFormat`, ICU, or another mechanism) and corresponding escaping rules.
- Choose the fallback policy and the list of locales the product actually supports.

**During translation:**

- Allow reordering placeholders while requiring **meaning/index/type** to stay intact.
- Do not force translators to match English word counts, sentence structures, or punctuation usage.
- Provide preview tooling per locale with sample data, including 0, 1, and many.
- Allow translators to ask questions or raise feedback when source content is ambiguous.

**Before release:**

- Validate pattern syntax and placeholders against the engine running in production.
- Check real values in the UI, length limits, line wrapping, Vietnamese diacritics, RTL where applicable, and accessibility.
- Test easily confused contexts such as “Open”, “Save”, status labels, and two-participant messages.
- Ensure every change to a placeholder contract is accompanied by updated translations and context documentation.

## 13. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Concatenating `prefix + count + suffix` | Locks sentence order, makes plurals hard to handle | Translate a complete sentence template and select branches per locale |
| Translating “message” separately and appending `s` | Forces English grammar onto every language | Use locale-accurate plural rules and complete sentences |
| Using one `open` key for every screen | Ambiguity between action and status | Keys by meaning, accompanied by description/context screenshots |
| Sending `{0}`, `{1}` with no explanation | Translators confuse person names with numbers/codes | Placeholder contract with roles, types, and examples |
| Requiring placeholder positions to stay fixed | Prevents grammatically valid word reordering | Preserve **indices and meanings**, allow reordering |
| Treating `0/1/other` as the rule for every language | Wrong plurals for many locales | Use language-specific plural data and test categories |
| Giving translators a word without screenshots or context | Polysemous words get mistranslated | Provide screenshots, placement, and business action |
| Putting raw HTML in resources without control | Layout breakage or XSS risks | Use safe components and context-appropriate encoding |
| Translating fragments but testing only the English sentence | Fails to catch reordering/grammar bugs | Test full messages in every locale |
| Checking only that `MessageFormat` throws no errors | Sentence may lose meaning or drop placeholders due to quotes | Compare outputs and perform linguistic review |
| Assuming fallback means translations are complete | Some sentences fall back to the source language | Audit key coverage and monitor fallbacks |

## 14. Key Takeaways

- **The translation unit should be a complete meaningful message.** Do not assemble fixed text fragments hoping every language shares the same grammar.
- **Placeholders must have a clear contract:** position, meaning, data type, examples, and permission to reorder during translation.
- **Context is part of translation quality:** UI screenshots, function, target audience, data roles, and tone must be provided alongside source strings.
- **Plurals and grammatical gender are not suffix-appending operations.** When needed, select complete sentence templates according to locale rules or use an l10n library supporting the appropriate grammar.
- **`ResourceBundle` finds translated sentences; `MessageFormat` inserts data.** Neither decides on its own whether a sentence is natural, contextually right, or culturally appropriate; review and testing are essential.
