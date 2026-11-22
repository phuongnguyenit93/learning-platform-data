# Reordering Arguments to Match Language Sentence Structure with MessageFormat

## 1. Why Argument Order Cannot Be Fixed to One Language

In a multilingual application, the same event can be expressed with different word orders. English might start with the sender; Vietnamese might start with the recipient. The business data **does not change** when the translated sentence changes order.

Suppose the application knows:

| Data role | Argument | Sample value |
| --- | --- | --- |
| Sender | `{0}` | `Lan` |
| File name | `{1}` | `report.pdf` |
| Recipient | `{2}` | `Minh` |

Two valid sentence patterns for the same event:

- English: `{0} sent file {1} to {2}.` → **Lan sent file report.pdf to Minh.**
- Vietnamese: `{2} đã nhận tệp {1} do {0} gửi.` → **Minh đã nhận tệp report.pdf do Lan gửi.**

The English pattern uses the order `{0} → {1} → {2}`; Vietnamese uses `{2} → {1} → {0}`. **The argument index describes the role, not the appearance order in the sentence.** Because of this, translations can change word order while Java still resolves the right sender, file, and recipient.

`java.text.MessageFormat` in Java separates the sentence pattern from the dynamic data array. It does not translate text automatically; **content translators** provide complete sentences for each language, while `MessageFormat` substitutes placeholders by index.

## 2. Mapping Mechanism of MessageFormat

A pattern can contain `{0}`, `{1}`, `{2}`, and format elements like `{0,number}`. Those non-negative integers are **indices into the arguments array**, starting at 0.

```text
Object[] args
  [0] = "Lan"        (sender)
  [1] = "report.pdf" (fileName)
  [2] = "Minh"       (recipient)
         |
         +--> en: {0} sent file {1} to {2}.
         |         Lan        report.pdf  Minh
         |
         +--> vi: {2} đã nhận tệp {1} do {0} gửi.
                   Minh           report.pdf Lan
```

When a pattern starts with `{2}`, the formatter reads the element at index 2 right at the start of the sentence. It **does not** read `args[0]` just because this placeholder appears first.

Illustrative example inside a method with appropriate imports:

```java
Object[] arguments = {"Lan", "report.pdf", "Minh"};
String pattern = "{2} đã nhận tệp {1} do {0} gửi.";
String message = new MessageFormat(
        pattern, Locale.forLanguageTag("vi-VN")).format(arguments);
```

The value of `message` is `Minh đã nhận tệp report.pdf do Lan gửi.`.

A common mistake is changing the array to `{"Minh", "report.pdf", "Lan"}` to match the reading order of the Vietnamese translation. That turns `args[0]` into two different roles depending on the locale, easily causing bugs that swap sender and recipient.

**Rule:** developers define the argument contract **by meaning**, and translators arrange placeholders **by grammar**.

## 3. Complete Java 17+ Example: Same Arguments, Two Translations, Different Order

Create three files in a directory on the classpath:

```text
MessageOrderDemo.java
Messages_en.properties
Messages_vi.properties
```

**`Messages_en.properties`**

```properties
upload.notice={0} sent file {1} to {2}.
review.notice={0} approved {1}. Thank you, {0}!
```

**`Messages_vi.properties`**

```properties
upload.notice={2} đã nhận tệp {1} do {0} gửi.
review.notice=Cảm ơn {0}! {1} đã được {0} duyệt.
```

**`MessageOrderDemo.java`**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageOrderDemo {
    private static String translate(
            Locale locale, String key, Object... values) {

        ResourceBundle.Control noDefaultFallback =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle(
                        "Messages", locale, noDefaultFallback);

        String pattern = bundle.getString(key);
        return new MessageFormat(pattern, locale).format(values);
    }

    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en");
        Locale vi = Locale.forLanguageTag("vi");

        Object[] upload = {"Lan", "report.pdf", "Minh"};
        System.out.println("EN: " +
                translate(en, "upload.notice", upload));
        System.out.println("VI: " +
                translate(vi, "upload.notice", upload));

        Object[] review = {"Lan", "PR-17"};
        System.out.println("EN review: " +
                translate(en, "review.notice", review));
        System.out.println("VI review: " +
                translate(vi, "review.notice", review));
    }
}
```

Save the source file and `.properties` files in UTF-8. Run with JDK 17 or later:

```bash
javac -encoding UTF-8 MessageOrderDemo.java
java -cp . MessageOrderDemo
```

**Exact stdout (on a UTF-8 terminal):**

```text
EN: Lan sent file report.pdf to Minh.
VI: Minh đã nhận tệp report.pdf do Lan gửi.
EN review: Lan approved PR-17. Thank you, Lan!
VI review: Cảm ơn Lan! PR-17 đã được Lan duyệt.
```

Observations:

1. `upload` is always the array `{"Lan", "report.pdf", "Minh"}`. Only the sentence pattern in the resource bundle changes.
2. `review.notice` uses `{0}` **twice** to mention the reviewer again, yet the application only needs to pass this name once. There is no rule prohibiting multiple occurrences of an index.
3. Vietnamese `{1} đã được {0} duyệt` switches to passive voice for natural phrasing. Choosing active or passive voice is the responsibility of the translation, not decided automatically by the formatter.
4. `ResourceBundle` looks up the **translation pattern** by key and locale; `MessageFormat` processes the **arguments** of the pattern. The two responsibilities are separate.
5. The example uses `Control.FORMAT_PROPERTIES` on the **classpath/unnamed module**, avoiding fallback to the JVM default locale. Overloads accepting `ResourceBundle.Control` are not supported when called from a named module; JPMS environments require an appropriate bundle/module mechanism.

Since Java 9, `PropertyResourceBundle` reads UTF-8 by default with ISO-8859-1 compatibility fallback; in practice, manage encoding consistently from source, build, to terminal.

## 4. Role Contract: What Translators Must Know

A key does not just have a name and a pattern string; it also has **the meaning of each placeholder**. Document the contract clearly:

| Key | `{0}` | `{1}` | `{2}` |
| --- | --- | --- | --- |
| `upload.notice` | Sender name | File name | Recipient name |
| `review.notice` | Reviewer name | Request ID | Unused |
| `project.summary` | Project name | Status | Owner |

This contract is tied to **each individual key**. There is no global rule that `{0}` is always a person's name. For example, another key might define `{0}` as a quantity and `{1}` as a date.

For handoff to translators, you can use illustrative metadata like:

```yaml
upload.notice:
  description: "Notification that a file was transferred from sender to recipient."
  arguments:
    0: "senderName: sender's name"
    1: "fileName: file name"
    2: "recipientName: recipient's name"
  example:
    en: "{0} sent file {1} to {2}."
    vi: "{2} đã nhận tệp {1} do {0} gửi."
```

This is a **translation contract document**, not the default `ResourceBundle` structure. With `.properties` files, the actual value remains the pattern as shown in section 3. Metadata helps translators avoid changing placeholder numbers to "renumber" them according to the new order.

## 5. Types of Changes Supported by MessageFormat

### 5.1. Reordering

```text
en: {0} approved {1}.
vi: {1} đã được {0} duyệt.
```

Arguments `{0}=Lan` and `{1}=PR-17` produce `Lan approved PR-17.` and `PR-17 đã được Lan duyệt.`. Same data, different emphasis.

### 5.2. Repeating an Argument

```text
en: {0} approved {1}. Thank you, {0}!
vi: Cảm ơn {0}! {1} đã được {0} duyệt.
```

No need to pass the reviewer's name twice. This is not a "new argument"; both `{0}` placeholders read from `args[0]`.

### 5.3. One Language Omitting Inferable Information

A pattern does not have to use every value in the array. `MessageFormat` does not force each argument to appear exactly once. However, omitting information can cause business ambiguity: hiding the sender in a payment/approval notice, or omitting a quantity or recipient name, can make the sentence incomplete in meaning. The contract must state **which arguments are mandatory to display** and which only support phrasing.

### 5.4. Reordering While Preserving Data Types

Suppose `{0}` is a count, `{1}` is the recipient, and `{2}` is the sender:

```text
en: {1} received {0,number,integer} items from {2}.
vi: {2} đã gửi {0,number,integer} mục cho {1}.
```

Reordering does not turn `{0}` into a person's name, and the `number,integer` meaning must not be stripped if the message requires integer formatting.

## 6. Do Not Confuse Argument Index with Format Element Index

A `MessageFormat` has two kinds of positions:

- **Argument index:** the number inside `{0}`, `{1}`, `{2}`, corresponding to the element in the data array.
- **Format element index:** the ordinal position of the placeholder **as it appears in the pattern**, counted from left to right.

Given the pattern `"{2} / {0} / {1}"`:

| Format element index | Format element | Argument index |
| ---: | --- | ---: |
| 0 | `{2}` | 2 |
| 1 | `{0}` | 0 |
| 2 | `{1}` | 1 |

APIs that are easy to confuse:

| API | Which index does it apply to? |
| --- | --- |
| `setFormat(int formatElementIndex, Format f)` | Appearance order of placeholder |
| `setFormats(Format[] fs)` | Appearance order of placeholder |
| `setFormatByArgumentIndex(int argumentIndex, Format f)` | Index inside `{n}` |
| `setFormatsByArgumentIndex(Format[] fs)` | Index inside `{n}` |

When translations swap positions, **`setFormatByArgumentIndex` is usually more appropriate**, because the format stays attached to the data role. If an index appears multiple times, this method applies the formatter to every format element with that same argument index.

### Complete Java 17 Example with Quantity

File `NumberArgumentOrder.java`:

```java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberArgumentOrder {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "{1} received {0} items from {2}; {1} will review.",
                Locale.US);

        // Format argument 0 (quantity), not the
        // first appearing placeholder {1}.
        format.setFormatByArgumentIndex(
                0, NumberFormat.getIntegerInstance(Locale.US));

        Object[] values = {1200, "Minh", "Lan"};
        System.out.println(format.format(values));
    }
}
```

```bash
javac -encoding UTF-8 NumberArgumentOrder.java
java NumberArgumentOrder
```

Stdout with `Locale.US`:

```text
Minh received 1,200 items from Lan; Minh will review.
```

If you used `setFormat(0, ...)` in this example, the integer formatter would attach to **the first format element `{1}`**, which is the recipient's name, causing a data type error during formatting. `setFormatByArgumentIndex(0, ...)` properly attaches to the quantity `{0}` even though `{0}` appears after `{1}`.

## 7. Allowed Format Syntaxes

The general form of a replacement element is:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Some forms in Java SE 17:

| Form | Meaning |
| --- | --- |
| `{0}` | Value of argument 0 |
| `{0,number}` | Format number according to locale |
| `{0,number,integer}` | Format integer |
| `{0,number,currency}` | Format currency according to locale and numeric value |
| `{1,date,short}` | Short date format, for date types supported by `DateFormat` |
| `{1,time,short}` | Short time format |
| `{2,choice,...}` | Branch selection via `ChoiceFormat` |

Numeric and date arguments are not simply converted to strings first and then substituted. `MessageFormat` creates or uses a **subformat**; the output depends on the locale, argument type, and format style. When working with `java.time.LocalDate`, you should format beforehand with `DateTimeFormatter` or use a compatible `Format`; standard `{0,date}` does not automatically guarantee direct support for all `java.time` types.

Vietnamese formatting example (snippet inside a method):

```java
Locale locale = Locale.forLanguageTag("vi-VN");
String pattern = "{2} đã gửi {0,number,integer} mục cho {1}.";
Object[] arguments = {1200, "Minh", "Lan"};
String sentence = new MessageFormat(pattern, locale).format(arguments);
```

The message will have the role order **Lan → quantity → Minh**, while the number grouping separator depends on locale data from the JDK/CLDR. You should not lock assertions to identical localized formatted strings across different JDK versions.

**Business note:** `{0,number,currency}` does not automatically obtain the currency from the transaction. It relies on the locale's formatter/currency unless configured otherwise. A USD transaction for a `vi-VN` user is still USD; to display the proper currency unit you must pass and apply the business `Currency`, either by pre-formatting the monetary string or using a custom formatter.

## 8. Single Quotes and Curly Braces: Translation Errors That Break Placeholders

`MessageFormat` has special syntax for the single quote `'`. In a pattern:

- A pair `''` represents a real apostrophe.
- A segment inside single quotes can be interpreted as literal text, so `'{0}'` outputs the text `{0}` instead of substituting the argument.
- If a pattern has an opening single quote without a closing one, the way the parser interprets the rest can prevent placeholders from being substituted.

Java example inside a method:

```java
String pattern = "It''s {0}''s file.";
String message = new MessageFormat(pattern, Locale.ENGLISH)
        .format(new Object[]{"Lan"});
System.out.println(message);
```

Output:

```text
It's Lan's file.
```

If a translator writes `"It's {0}'s file."` without escaping apostrophes for `MessageFormat`, the output may contain a literal `{0}` or incorrect content. Translations with apostrophes should routinely be tested separately.

Another case:

```java
String pattern = "Literal: '{0}', actual: {0}.";
String message = new MessageFormat(pattern, Locale.ENGLISH)
        .format(new Object[]{"VALUE"});
```

The result is `Literal: {0}, actual: VALUE.`. Here `'{0}'` is quoted to **print the placeholder literally**, while the remaining `{0}` is actually substituted with data.

Distinguish **three layers of escaping** when necessary: Java string literals, `.properties` content, and `MessageFormat` syntax. Unbalanced `{`, `}` or an invalid format type can cause `new MessageFormat(pattern, locale)` to throw `IllegalArgumentException`.

## 9. Common Mistakes When Reordering

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Renumbering `{0}`, `{1}` by word position in translation | Indices are bound to roles, so data gets swapped | Keep indices per the contract |
| Swapping array elements by language | Application logic is forced to know sentence structure | Keep array consistent, change pattern |
| Translating word-by-word / concatenating strings | Grammar, prepositions, inflections, and order may differ | Translate whole sentences with placeholders |
| Using `setFormat(0, f)` thinking it targets `{0}` | That targets the first format element | Use `setFormatByArgumentIndex` when binding to a role |
| Forgetting `''` in patterns | Incorrect quoting disables placeholders | Test apostrophes and literal braces |
| Missing argument without checking output | Unavailable argument may display literal `{n}` | Validate contract and argument count |
| Using `{0,number}` with a String | Numeric subformat requires a compatible type | Pass a Number or pre-format |
| Converting a date to default String and embedding it | Easily gets locale and time zone wrong | Choose formatter and `ZoneId` explicitly |
| Treating `MessageFormat` as an automatic translator | It only substitutes and formats data | Write each translated pattern |
| Sharing mutable `MessageFormat` across requests | `applyPattern`, `setFormat` can mutate state | Create separate instances or synchronize access |
| Using `MessageFormat` for unescaped HTML | It does not prevent XSS | Encode for the output context |

### 9.1. Missing Arguments and `null` Arguments

According to the Java specification, when a placeholder has an argument index outside the array bounds, `MessageFormat` may leave a literal like `{2}` in the output, **without necessarily throwing an error**. Therefore, "formatting ran without errors" does not guarantee complete data.

A `null` argument can be rendered as the text `null`. In a real UI, you need a clear policy for handling missing data to avoid exposing placeholders or `null` to users. If a subformat requires a Number or Date and an incompatible type is passed, it may throw `IllegalArgumentException`.

### 9.2. Using One Language as the Reference Template

Using English as a reference template is fine, but you must not force every translation to keep the **exact same placeholder order** as English. Keep the **argument roles** and event meaning; let translators decide the sentence structure.

## 10. Reordering Alone Does Not Solve All Grammatical Variants

Changing `{0} {1}` to `{1} {0}` shifts information order, but many languages also have:

- Singular/plural rules depending on quantity;
- Grammatical gender, verb conjugation, and noun/pronoun inflection;
- Units of measurement, numbers, currency, and dates;
- Politeness forms and formality levels;
- Right-to-left (RTL) text and bidi handling for strings mixed with Latin characters.

JDK 17's `MessageFormat` has `ChoiceFormat`, but **does not directly support** ICU syntax like `{count, plural, ...}` or `{gender, select, ...}` as standard format types. If the product needs complex plurals, consider ICU MessageFormat or an appropriate message-pattern selection layer. Reordering placeholders alone cannot replace grammatical translation.

For example, `"{1} đã được {0} duyệt"` is a passive sentence, requiring the translator to ensure the meaning stays accurate; `MessageFormat` does not verify who actually performed the approval.

## 11. Organizing Resources and Formatting in an Application

A typical flow:

```text
Event / domain
  senderName = "Lan"
  fileName = "report.pdf"
  recipientName = "Minh"
        |
        v
App determines user locale (vi/en/...)
        |
        v
ResourceBundle loads pattern by key + locale
        |
        v
MessageFormat(pattern, locale)
        |
        v
format(new Object[] {senderName, fileName, recipientName})
        |
        v
Rendered string -> output encoding appropriate for UI
```

`ResourceBundle` selects the translation pattern and provides candidate/fallback mechanisms across locale, base, and parent. `MessageFormat` does not detect languages or load bundles. When a bundle lacks a key, it can inherit from its parent or throw `MissingResourceException` if not found anywhere in the chain.

Pass the `Locale` explicitly from the request/profile rather than calling `Locale.setDefault(...)` on a multi-user server. `Locale.setDefault` mutates the JVM-wide default and can affect other requests. Static `MessageFormat.format(pattern, args...)` uses the default locale of the internally created formatter; for a deterministic locale, use `new MessageFormat(pattern, locale).format(args)`.

`MessageFormat` is mutable; methods like `applyPattern` and `setFormat` can alter its configuration. Do not share one instance and mutate its pattern/locale concurrently across requests. `ResourceBundle` has caching, but that does not make `MessageFormat` immutable.

For HTML content, `MessageFormat` only returns text; **it does not automatically escape HTML/URLs**. User-supplied values must be properly encoded at the HTML, DOM, or other output boundary. Do not use placeholder substitution as a security layer.

## 12. Testing Argument Order and Translations

Use **distinct sentinel values** for each role to detect swaps:

```text
args[0] = SENDER_A
args[1] = FILE_B
args[2] = RECIPIENT_C

en: SENDER_A sent file FILE_B to RECIPIENT_C.
vi: RECIPIENT_C đã nhận tệp FILE_B do SENDER_A gửi.
```

If you use the same name for sender and recipient, tests can miss swap bugs.

Cases to verify:

1. **Different order:** the same array produces semantically accurate sentences across locales.
2. **Repeated indices:** `{0}` appearing multiple times holds the same value.
3. **Missing required placeholders:** validate the key's contract.
4. **Extra/missing arguments:** test invalid index references, missing values, or `null`.
5. **Data types:** `{0,number}` always receives a Number, `{1,date}` receives a type compatible with `DateFormat`.
6. **Apostrophes and braces:** French/English patterns containing single quotes still substitute properly.
7. **Locale and resource fallback:** all keys and desired languages are present, independent of JVM default.
8. **Sentence semantics:** native speakers or reviewers confirm correct sender/recipient roles and active/passive voice.
9. **Special characters:** user names, file names, and content may contain non-Latin characters, braces, apostrophes, and HTML characters.
10. **Mutable formatter:** no race conditions when running concurrent requests.

Do not use simple regex on `{...}` strings to validate all patterns, because `MessageFormat` has quoting, subformats, and nested patterns with `ChoiceFormat`. Use a proper parser combined with sample-value tests and translation rules.

## 13. Hands-On Exercises

### Exercise 1 — Changing the Subject When Translating

Given `args = {"Hoa", "contract.pdf", "Nam"}`, where `{0}` is the sender, `{1}` is the file, and `{2}` is the recipient. Write an English pattern starting with the sender and a Vietnamese pattern starting with the recipient, without changing the array.

**Answer:**

```text
en: {0} sent file {1} to {2}.
vi: {2} đã nhận tệp {1} từ {0}.
```

Outputs respectively: `Hoa sent file contract.pdf to Nam.` and `Nam đã nhận tệp contract.pdf từ Hoa.`.

### Exercise 2 — Format Element Index Differs from Argument Index

Given the pattern `"{2}: {0} - {1}"`, what is the first placeholder element? How does `setFormat(0, f)` differ from `setFormatByArgumentIndex(0, f)`?

**Answer:** The first format element is `{2}`; `setFormat(0, f)` affects `{2}`. `setFormatByArgumentIndex(0, f)` affects `{0}` in the second position.

### Exercise 3 — Repeating the Same Argument

With `args = {"Lan", "PR-17"}` and pattern `"Cảm ơn {0}! {1} đã được {0} duyệt."`, what is the output?

**Answer:** `Cảm ơn Lan! PR-17 đã được Lan duyệt.`.

### Exercise 4 — Apostrophes

Where can the pattern `"It's {0}'s file."` break? How should it be written properly?

**Answer:** `'` belongs to `MessageFormat`'s quoting syntax. Write `"It''s {0}''s file."` to get `It's Lan's file.` when `{0}=Lan`.

### Exercise 5 — Limits of Reordering

A language needs multiple plural forms based on `count`. Can you simply swap `{0}` and `{1}` to translate it correctly?

**Answer:** No. Reordering resolves word/phrase position; a separate mechanism is needed to choose plural variants per language.

## 14. Key Takeaways

- **Placeholder appearance order can differ across languages.** Each `{n}` always points to argument index `n`.
- **Keep roles and input array order stable** for the same message key; place placeholders according to each translation's phrasing.
- **Placeholders can be repeated or moved**, while preserving meaning and all required business information.
- **`setFormatByArgumentIndex` binds a formatter to a role**, whereas `setFormat` binds to format element order; this distinction is especially important when translations reorder placeholders.
- **Test with role-distinguishing data** and verify apostrophes, argument types, argument counts, and sentence semantics.
- **`MessageFormat` does not auto-translate, handle complex grammar, or escape HTML**; the rest requires good translations and proper handling at the application layer.

References: [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) and [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html).
