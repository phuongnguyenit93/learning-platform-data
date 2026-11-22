# Keeping Whole Sentences Intact So Translators Can Reorder Clauses in Java

## 1. The Problem: Concatenating Fragments Breaks Proper Translation

When building multilingual applications, a common design flaw is splitting a message into small fragments, translating each fragment, and **concatenating them in code**:

```java
// APPROACH TO AVOID
String message = bundle.getString("actor") + " "
        + actor + " "
        + bundle.getString("sent") + " "
        + count + " "
        + bundle.getString("files") + " "
        + bundle.getString("to") + " "
        + receiver + ".";
```

At first glance this looks like word reuse: you already have "sent", "files", and "to", and just swap in the recipient and count. However, human language grammar is **not a one-to-one concatenation following English word order**.

For example, the same event "Lan sent three files to Minh" can be phrased in different orders:

- English: **Lan sent 3 files to Minh.**
- Vietnamese emphasizing the recipient: **Minh đã nhận 3 tệp do Lan gửi.**

These strings do not differ merely word by word. **Subject, verb, quantity position, prepositions, tone, and information order** can all be reorganized. Once Java code locks in the fragment order `actor + sent + count + files + to + receiver`, the translator **cannot move "Minh" to the start of the sentence** without modifying the program.

**Core rule:** every UI message expressing **a complete sentence** should be stored under **one resource key** containing **one complete sentence pattern**, while dynamic data such as names, counts, and timestamps are passed via **positional or named placeholders**. Translators can then move placeholders to grammatically natural positions.

In core Java, you can use:

- `ResourceBundle` to retrieve sentence patterns by `Locale`.
- `MessageFormat` to substitute placeholders like `{0}`, `{1}`, `{2}` and format numbers/dates per locale.
- Advanced plural/select engines such as ICU MessageFormat if the application requires complex grammatical variants.

The goal is not merely "no grammar mistakes": this design ensures **translations have full context, are easy to test, can be compiled/linted automatically, and can change without touching code**.

## 2. The Complete Sentence Is the Unit of Translation, Not Individual Words

Compare the two designs:

| Aspect | Fragment concatenation in Java | Complete sentence pattern in resource |
| --- | --- | --- |
| Unit of translation | Words `"sent"`, `"files"`, `"to"` | Full `"{0} sent {1} files to {2}."` |
| Word order | Hardcoded in Java | Translator arranges placeholders |
| Context | Translator sees isolated words | Sees who did what to whom |
| Plurals | Tends to force `"files"` for all counts | Provides room to pick count-based patterns |
| Punctuation/spacing | Scattered across code and multiple resources | Owned by the sentence pattern |
| Testing | Must assemble many fragment combinations | Can format each message with sample args |
| Maintenance | Changing phrasing may require code edits | Usually updates translation in resource only |

With the English pattern:

```properties
upload={0} sent {1,number,integer} files to {2}.
```

and Vietnamese:

```properties
upload={2} đã nhận {1,number,integer} tệp do {0} gửi.
```

Placeholder semantics are fixed by contract:

- `{0}`: **sender**.
- `{1}`: **file count**.
- `{2}`: **recipient**.

Both locales use **the same argument list**, while the translation reorders where those arguments appear for grammar. `MessageFormat` does not know what "sender" means; **the programming contract and translator notes** must explain those meanings.

If you only use `String.format("%s sent %d files to %s", ...)` with the format string inside Java source, you are still locked into callsite order. `Formatter` supports positional argument syntax (`%1$s`), yet for standard Java localization workflows, `ResourceBundle + MessageFormat` expresses each layer's responsibilities much more clearly.

## 3. Designing a Message from Meaningful Data

Instead of dissecting an English sentence into linguistic pieces, start from **a meaningful event/data record**:

```text
Event: FILES_SENT
senderName   = "Lan"
fileCount    = 3
receiverName = "Minh"
```

This is a **data description**, not Java syntax. The UI selects a message key, such as `notification.filesSent`, and passes the three values to the formatter.

A useful design rule: **arguments are data; the sentence pattern is language**.

- `senderName` and `receiverName` are application data: values vary per request.
- `fileCount` is numeric data: the locale decides whether to show `1,000` or `1.000`, and the translation decides singular/plural phrasing.
- Punctuation, connectors, parameter positions, and overall tone belong to the translation.
- Messages only make sense in concrete context: is "Open" a verb to open a window or an adjective describing an open status? Use **appropriate keys and context notes**.

Do not store an entire rendered sentence like `"Lan gửi 3 tệp cho Minh"` in a data column and try to translate it via search-and-replace on names, because dynamic values can collide with words, contain punctuation, or have structure that is hard to split.

## 4. `ResourceBundle`: Let Each Locale Own the Entire Sentence

For a typical classpath application, structure files as:

```text
src/main/
├── java/
│   └── com/example/app/WholeSentenceDemo.java
└── resources/
    └── com/example/i18n/
        ├── Messages.properties
        ├── Messages_en.properties
        └── Messages_vi.properties
```

The base name used in code is `"com.example.i18n.Messages"`. In Java 17+, property resource bundle files can be saved directly in UTF-8 (per `PropertyResourceBundle` behavior since Java 9; do not confuse with `Properties.load(InputStream)`, which follows different byte rules).

### 4.1. Default File `Messages.properties`

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
invitation={0} invited {1} to {2}.
fallback.help=Contact support.
```

The root `Messages.properties` provides a fallback when a locale is not yet translated or some keys are missing. However, fallback is not a license to let a multilingual UI accidentally display mixed-language sentences; verify translation coverage in CI.

### 4.2. `Messages_en.properties`

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
invitation={0} invited {1} to {2}.
```

English translators see the full sentence and can adjust tone or punctuation to match the product. Placeholders still reference the documented data.

### 4.3. `Messages_vi.properties`

```properties
notification.filesSent={2} đã nhận {1,number,integer} tệp do {0} gửi.
invitation={1} được {0} mời tham gia {2}.
```

The Vietnamese version:

- Moves the recipient `{2}` to the beginning of the file-sent notification.
- Places the invitee `{1}` ahead of the inviter `{0}`.
- Chooses a more natural phrasing without touching Java code.
- Uses Vietnamese characters directly in the UTF-8 file.

**Do not translate placeholders**: `{0}`, `{1}`, and `{2}` are system tokens. Translators may move or repeat them when justified, but must not arbitrarily change indices or drop required parameters without review. The `Locale` used to pick the bundle should also be passed explicitly rather than relying on the server's default locale.

## 5. Standalone Java 17+ Program with Resources: Reorder Without Changing Code

Create **`src/main/java/com/example/app/WholeSentenceDemo.java`**:

```java
package com.example.app;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class WholeSentenceDemo {
    private static String format(
            Locale locale, String key, Object... args) {

        ResourceBundle messages = ResourceBundle.getBundle(
                "com.example.i18n.Messages", locale);
        String pattern = messages.getString(key);
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(args);
    }

    public static void main(String[] args) {
        Locale english = Locale.US;
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        String enInvite = format(english, "invitation",
                "Lan", "Minh", "Java Club");
        String viInvite = format(vietnamese, "invitation",
                "Lan", "Minh", "Câu lạc bộ Java");

        String enUpload = format(english, "notification.filesSent",
                "Lan", 3, "Minh");
        String viUpload = format(vietnamese, "notification.filesSent",
                "Lan", 3, "Minh");

        System.out.println("EN invite: " + enInvite);
        System.out.println("VI invite: " + viInvite);
        System.out.println("EN upload: " + enUpload);
        System.out.println("VI upload: " + viUpload);

        System.out.println("Fallback: " +
                format(vietnamese, "fallback.help"));
    }
}
```

This is a complete Java program, but it requires **the three `.properties` files** on the classpath exactly as in Section 4. Do not copy only the `.java` file and run it without the resources on the classpath.

With Java 17+, you can compile manually from the project root:

Linux/macOS:

```bash
javac -encoding UTF-8 -d out src/main/java/com/example/app/WholeSentenceDemo.java
java -cp "out:src/main/resources" com.example.app.WholeSentenceDemo
```

Windows PowerShell:

```powershell
javac -encoding UTF-8 -d out src/main/java/com/example/app/WholeSentenceDemo.java
java -cp "out;src/main/resources" com.example.app.WholeSentenceDemo
```

Output when resources are present and the console supports Unicode:

```text
EN invite: Lan invited Minh to Java Club.
VI invite: Minh được Lan mời tham gia Câu lạc bộ Java.
EN upload: Lan sent 3 files to Minh.
VI upload: Minh đã nhận 3 tệp do Lan gửi.
Fallback: Contact support.
```

### How Does Each Step Work?

1. `format` receives `Locale`, a **key**, and arguments with well-defined meanings.
2. `ResourceBundle.getBundle` picks the English/Vietnamese resource.
3. `getString(key)` returns **the entire sentence pattern**.
4. `new MessageFormat(pattern, locale)` parses the pattern with the given locale; number/date subformats follow the formatter's locale.
5. `formatter.format(args)` binds data by **placeholder index**, regardless of appearance order in the translation.
6. In the Vietnamese sentence, `{1}` can appear before `{0}` — without changing the argument order in Java.
7. `fallback.help` is absent from the `_vi` file, so it is resolved from the root bundle along the parent chain.

Note that this source code intentionally uses simple sample sentences; in production systems, language specialists should review final translations. The key technical point is that **translators have control over the full sentence structure**.

## 6. How Does `MessageFormat` Number Placeholders?

`java.text.MessageFormat` uses placeholders of the form:

```text
{0}
{1}
{2}
{0,number}
{1,number,integer}
{2,date,short}
{3,time,medium}
```

Indices start at **0** and correspond to the passed `Object[]`. Optional type/style segments control how each value is formatted.

Example:

```java
String english = "{0} sent {1,number,integer} files to {2}.";
String vietnamese = "{2} đã nhận {1,number,integer} tệp do {0} gửi.";

Object[] values = {"Lan", 3, "Minh"};

String en = new MessageFormat(english, Locale.US).format(values);
String vi = new MessageFormat(
        vietnamese, Locale.forLanguageTag("vi-VN"))
        .format(values);
```

This is a **snippet** requiring imports `java.text.MessageFormat` and `java.util.Locale`. Output:

```text
Lan sent 3 files to Minh.
Minh đã nhận 3 tệp do Lan gửi.
```

When switching from `{0} ... {2}` to `{2} ... {0}`, the code still passes `{"Lan", 3, "Minh"}`. This is the advantage over hardcoding string concatenation for one language.

### Placeholders Can Be Repeated

A translation may need to mention the recipient's name twice, for example:

```properties
notice={0}, vui lòng kiểm tra tài khoản của {0}.
```

`MessageFormat` reuses the same value for both `{0}` occurrences. **You do not need to pass duplicate arguments** just to match how many times a placeholder appears.

### Do Not Arbitrarily Reassign Index Meanings

In code you can pick any logical argument order, but you must document it:

| Index | Meaning | Java type | Example |
| --- | --- | --- | --- |
| `{0}` | Sender | `String` | `"Lan"` |
| `{1}` | File count | `Integer`/`Number` | `3` |
| `{2}` | Recipient | `String` | `"Minh"` |

Translations **may change appearance order**, but must not arbitrarily turn `{1}` into the recipient. If translators need a different data type or a new argument, that is a **message schema contract change** requiring code and test updates.

## 7. Elements That Must Live Inside the Translated Sentence

Do not keep an "English skeleton" in Java code and push only a few nouns/verbs into resources. The following belong inside **the complete sentence pattern** whenever they play a grammatical role:

- **Word order:** who, did what, to whom, where.
- **Connectors/prepositions:** "to", "from", "by", etc.
- **Articles and determiners:** "a/an/the", or forms matching target grammar.
- **Punctuation:** commas, periods, question marks, exclamation marks, and script-appropriate brackets.
- **Whitespace:** spacing count and placement are determined by each language's orthography, not by adding `" "` between fragments.
- **Tone/register:** active vs. passive voice, polite/formal phrasing, message brevity.
- **Grammatical markers:** singular/plural, gender/person/case if required by the target language.
- **Dynamic info placement:** placeholders sit in the right spot after translation.

If the UI has a "You have ..." message with a count, do not translate "You have" and "items" separately and concatenate them. Vietnamese, English, Arabic, Russian, Polish, etc., use different structures and plural variants.

**Conversely**, not every UI string has to be a full sentence. Standalone button labels like "Save", headings like "Settings", or menu items like "Account" remain **valid translation units** when they are functionally independent and have context. The "keep whole sentences" rule targets **messages with grammatical relationships**, rather than forcing unrelated labels into a single resource key.

## 8. When Quantities Change: Never Concatenate Singular/Plural Endings

The pattern:

```properties
notification.filesSent={0} sent {1,number,integer} files to {2}.
```

suffices to illustrate **reordering** but **does not handle English singular grammar**: `1 files` is unnatural. Do not fix this by appending `file + (count == 1 ? "" : "s")` in code, because plural rules can be far more complex in other languages.

### 8.1. Branching Patterns for Simple Cases

When a language/case genuinely needs only a few branches, the application can choose **one complete sentence key** by count:

```properties
# en (illustrative)
files.one={0} sent one file to {2}.
files.other={0} sent {1,number,integer} files to {2}.
```

and in `Messages_vi.properties`, each branch should likewise be **a complete sentence pattern**:

```properties
files.one={2} đã nhận một tệp do {0} gửi.
files.other={2} đã nhận {1,number,integer} tệp do {0} gửi.
```

The properties above are **illustrative data**; code must select the right key, pass all arguments, and apply plural rules according to the target **locale**.

### 8.2. Never Assume Only `one`/`other` Exist

Many languages have plural categories such as `zero`, `one`, `two`, `few`, `many`, and `other`; category selection often depends on both integer value and fractional digits. For serious multilingual products, consider **ICU MessageFormat** or a CLDR-based plural/select message system. That is a different tool from standard Java SE `java.text.MessageFormat`.

`ChoiceFormat` in Java SE can pick messages by **numeric ranges** and integrates with `MessageFormat` in simple cases. However, `ChoiceFormat` does not provide all CLDR plural categories automatically; do not promote it as a universal plural grammar solution for every locale.

### 8.3. Keep Every Conditional Branch a Complete Translated Sentence

Even when selecting a key in code:

```java
String key = (count == 1) ? "files.one" : "files.other";
```

do not return just a noun `file`/`files` and glue it into a sentence with frozen word order. Every branch should hold **the entire message**, so translators can adjust sentence structure independently. As the app expands to more languages, delegate plural-category selection to a proper locale-aware plural engine.

## 9. Numbers, Dates, and Money Must Be Formatted by Locale

Another benefit of `MessageFormat` is allowing formatting styles directly inside patterns:

```properties
summary={0} đã tạo {1,number,integer} báo cáo.
amount=Giá trị còn lại: {0,number,currency}.
reminder=Hạn chót: {0,date,long}.
```

For example, `{1,number,integer}` uses `MessageFormat`'s integer formatting for the locale; `{0,number,currency}` formats currency per the locale's context. If **the transaction currency** is not determined by the user's locale, design an explicit `Currency` policy instead of relying on the region's default currency.

A standalone runnable illustration:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageNumberDemo {
    public static void main(String[] args) {
        String pattern =
                "{0} sent {1,number,integer} files to {2}.";
        Object[] values = {"Lan", 1234, "Minh"};

        String result = new MessageFormat(
                pattern, Locale.US).format(values);
        System.out.println(result);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 MessageNumberDemo.java
java MessageNumberDemo
```

Stdout with `Locale.US`:

```text
Lan sent 1,234 files to Minh.
```

The code avoids pasting `count.toString()` into a formatted slot, letting digit grouping and display adapt to the locale. When formatting dates/times, remember that **Locale only governs spelling/layout**, while the display time zone must be chosen explicitly from context. Legacy `MessageFormat` is also tied to older date/time types; with modern `java.time`, format dates/times with `DateTimeFormatter` or an explicit adapter before passing them into the pattern. Never silently convert an `Instant` to a date using the server's default time zone.

Still distinguish data formatting from sentence grammar: digit grouping is handled automatically, whereas quantities affecting plural/case of surrounding words require message patterns with appropriate variants.

## 10. Single Quotes and Curly Braces in `MessageFormat`

`MessageFormat` has its own pattern syntax:

- `{0}`, `{1}`... are placeholders.
- Single quote `'` **quotes literal text** inside a pattern.
- To output **a single literal apostrophe**, in many cases you must write `''` (two single quotes).
- To output literal curly braces, quote them per `MessageFormat` rules.

Common bug example:

```properties
# LIKELY BROKEN: single quotes alter how the pattern is parsed
owner=It's {0}'s book.
```

Valid pattern under `MessageFormat` syntax:

```properties
owner=It''s {0}''s book.
```

Standalone Java 17+ program:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "It''s {0}''s book.", Locale.US);

        System.out.println(format.format(
                new Object[]{"Lan"}));
    }
}
```

Run:

```bash
javac -encoding UTF-8 MessageQuoteDemo.java
java MessageQuoteDemo
```

Stdout:

```text
It's Lan's book.
```

**Warning:** `'` in English, French, apostrophe-heavy languages, and examples containing `{braces}` is a very common source of localization bugs. When handing resources to translators, give clear format syntax guidance and **automatically parse/format all translations** in tests to catch invalid patterns.

Do not replace `{0}` tokens using arbitrary regex or `String.replace` just to bypass `MessageFormat` syntax. That skips number formatting, escaping, and pattern validation, and can break when dynamic values contain strings resembling placeholders.

## 11. Translation Contract: Context Notes for Translators

Writing a grammatically natural sentence requires translators to know **who does what to whom**. A resource key and placeholder numbers alone may not be enough.

Information to include alongside a message catalog:

| Field | Example |
| --- | --- |
| Key | `notification.filesSent` |
| Source | `{0} sent {1,number,integer} files to {2}.` |
| Context | Notification when one user sends files to a recipient in the app |
| `{0}` | Sender's display name; may contain spaces or Unicode characters |
| `{1}` | File count, `Number` type, non-negative |
| `{2}` | Recipient's display name |
| UI area | Notification list and detail view |
| Style requirements | Neutral tone, do not add extra business claims |
| Plural | Needs locale-appropriate count branch when product supports `count=1` |
| Rich text | Plain data only; do not embed arbitrary HTML |

If the application uses XLIFF, ARB, ICU message catalogs, or a translation management system, store notes in the corresponding metadata. For plain `.properties` files, comments can help translators in the repository, though not every QA tool reads comments automatically; store placeholder contracts where the translation pipeline can validate them.

**Never share one key across two distinct meanings merely because English uses the same word.** For example, `"Open"` as a button verb and `"Open"` as a support-ticket status may translate differently. Pick separate keys by intent, such as `action.openDocument` and `status.open`.

## 12. When a UI Component Sits Inside a Sentence

A tricky scenario:

```text
I agree to [Terms] and [Privacy Policy].
```

If code hardcodes component order:

```java
label("I agree to") + link("Terms") + label("and")
        + link("Privacy Policy")
```

the translation loses the ability to move the links. In some languages, clause order, document name placement, and conjunctions differ.

Design around **a complete message containing typed placeholder regions**:

```text
agree=I agree to {termsLink} and {privacyLink}.
```

The line above **illustrates a message system supporting named placeholders/rich text**; it is **not** a valid pattern to feed straight into standard `java.text.MessageFormat`, because standard Java SE `MessageFormat` uses **integer indices** like `{0}`.

In Java SE, you can use positional-index messages with a UI renderer layer to resolve **text spans and link components**, or use a message framework supporting structured rich-text placeholders. What matters is:

1. The translation owns the entire sentence, including link ordering.
2. Placeholders reference **declared components** rather than containing arbitrary raw HTML.
3. Link text has localized accessibility labels.
4. Rendered output is escaped/sanitized by the UI framework so neither translations nor user data turn into uncontrolled HTML.
5. Never slice the formatted string to guess link offsets by counting bytes/characters of the source sentence.

If the layout requires **two separate buttons/checkboxes**, a single sentence is not always appropriate for semantic HTML or accessibility. Redesign the UI structure so messages still have full translation context without mixing interactive logic into raw text strings.

## 13. Do Not Let Formatting Mask Security Bugs

A message pattern and a dynamic value have different roles:

```java
String pattern = bundle.getString("notification.filesSent");
Object[] arguments = {senderName, fileCount, receiverName};
String display = new MessageFormat(
        pattern, locale).format(arguments);
```

This is a snippet; `senderName` and `receiverName` are data and must never be treated as a pattern. If `senderName` contains `"{0}"`, passing it as **an argument** prevents it from being parsed as a template. Conversely, if code lets user data freely become the `pattern`, users can trigger syntax errors or disrupt formatting—even if the app has no "code execution".

**Message formatting does not automatically escape HTML, SQL, or JavaScript.** When rendering onto a web page, the renderer must escape for context; when logging names, enforce log-injection defenses; when querying SQL, use prepared statements rather than string concatenation.

Do not use `MessageFormat` to assemble HTML from fragments marked "safe" unless the UI contract guarantees escaping and structure. For rich text, use a UI-level framework with typed placeholders.

## 14. Avoid Splitting One Sentence into Multiple Keys for "Reuse"

An anti-pattern against proper translation:

```properties
message.prefix=You have
message.quantity=files
message.suffix=remaining.
```

and in Java:

```java
String result = prefix + " " + count + " " + noun + " " + suffix;
```

Translators cannot reorder key parts; if `message.quantity` is shared across dozens of sentences, a plural/gender/case adjustment breaks other places.

Replace with a whole-sentence pattern:

```properties
storage.remaining=You have {0,number,integer} files remaining.
```

Vietnamese can be:

```properties
storage.remaining=Bạn còn {0,number,integer} tệp.
```

Even when sentences currently share a similar order, the translation owns **the full sentence** and can evolve independently later.

### When Is Reuse Appropriate?

Reusing **the same message key** should happen only when contexts truly match across:

- action/semantics;
- speaker/listener roles;
- formality level;
- argument count and types;
- singular/plural rules;
- UI placement/style suitability.

Do not reuse a key merely because both spots use the word "Save", "Back", or "Account". Two separate keys help translators get each context right and prevent an edit in one place from unintentionally changing another.

## 15. Testing Translations with Reordered Placeholders

A good test suite verifies **actual formatting** rather than only checking key existence. Test:

| Case | Example | Expectation |
| --- | --- | --- |
| English version | `{0} ... {2}` | Sender appears first |
| Vietnamese version | `{2} ... {0}` | Recipient appears first |
| Varying data | Names other than Lan/Minh | Every placeholder renders its exact value |
| Large number | `1234` | `{1,number,integer}` follows locale, not `toString` |
| Count of one | `1` | Uses proper plural branch; never `"1 files"` |
| Pattern with apostrophes | `It''s {0}''s book` | Prints literal apostrophes properly |
| Missing parameter | Translation uses `{3}` while code passes `0..2` | QA flags schema error, not just visual check |
| Wrong argument type | Passing `String` to `{1,number}` | Test catches format failure |
| Missing key | Locale lacks message key | Explicit fallback or policy-driven error |
| Longer text | Translation 1.5–2× longer | UI wraps/resizes without clipping content |
| Right-to-left | RTL locale | Layout order and bidi isolation are accurate |
| Unicode names | `Đặng Văn A`, emoji, quotes | No garbled characters; escaped for UI context |

### Reordering Must Be Tested Intentionally

Do not pass identical values like `"A"` for both `{0}` and `{2}`: a translation that swaps placeholders by mistake will still look right.

In the Java example, using `"Lan"` and `"Minh"` makes swapping obvious. In automated tests, pass distinct marker values like `"SENDER_0"`, `"RECEIVER_2"`, and `1234`, and assert each appears in the right role.

To detect missing placeholders, CI can parse patterns with `MessageFormat` or a dedicated validation library. However, **counting `"{0}"` substrings with a naive regex is insufficient** because `MessageFormat` syntax includes escaping, nested subformats, choice branches, and quoted literals. Your checker should understand the message syntax in use.

### Testing Translation Coverage

Not every locale always has every sentence translated if some rely on fallback. Define a policy: allow base-language fallback in development builds, or fail releases when keys are missing for supported locales. `ResourceBundle` automatic fallback is a runtime mechanism, not a substitute for translation coverage reports in your release pipeline.

## 16. Length, Layout, and UI Responsibility

When keeping whole sentences in translations, translated sentences can become significantly longer or shorter than the source. This is a **UI design concern**, never something to solve by chopping sentences into fragments.

- Allow wrapping and vertical expansion rather than hardcoding English-sized fixed widths.
- Avoid arbitrary `substring` truncation, which can split surrogate pairs or grapheme clusters and destroy sentence meaning.
- Do not append a period in UI code when the translated sentence already owns punctuation.
- Do not implicitly inject spaces before/after placeholders: some scripts do not space words like English.
- For RTL, handle text direction and label/button placement via proper layout and bidi systems, never by reversing strings.
- Names or IDs inserted into RTL sentences may require Unicode bidi isolation or supportive UI primitives to prevent character-order scrambling.
- For accessibility, screen readers should hear content that makes sense **as a sentence**, rather than stitched unrelated labels.

A flexible UI is a **prerequisite for whole-sentence translation to succeed**. If the English layout already forces a label onto one non-wrapping row, translators remain boxed in even when resource files allow reordering placeholders.

## 17. Common Bugs and Fixes

| Bug | Harm | Fix |
| --- | --- | --- |
| Concatenating `prefix + count + suffix` | Locks sentence word order | Put whole sentence under one resource key |
| Translating verbs/prepositions individually | Lost context, broken grammar | Translate complete messages with placeholders |
| `String.format` with hardcoded Java pattern | Translations cannot reorder | Load pattern from `ResourceBundle`, format by locale |
| Passing args in one locale's display order | Unmaintainable code, swapped meanings | Fixed schema arg order; translations reorder placeholders |
| Producing `"1 files"` | Unhandled plurals | Pick sentence branch per locale plural rules |
| Sharing key across status and action | Out-of-context translations | Split keys by role and intent |
| Skipping `MessageFormat` apostrophe escaping | Pattern parses improperly | Use `''` for literal apostrophes where needed, test |
| Changing `{1}` to `{2}` to reorder words | Alters parameter meaning | Move slot positions, never reassign indices arbitrarily |
| Missing placeholder descriptions | Translators guess who is who | Document role, type, and examples |
| Skipping translation coverage checks | Mixed-language releases | QA key sets and fallback behavior |
| Calling `count.toString()` | Numbers ignore locale | Pass `Number` and use number formatting |
| Letting user data become `MessageFormat` pattern | Syntax errors / uncontrolled behavior | Use vetted catalog patterns; pass user data as args |
| Assuming `MessageFormat` escapes HTML | Risks HTML injection | Escape per UI context |
| Truncating translated sentences to fit buttons/toasts | Lost meaning, broken Unicode | Fix layout, or author a dedicated short variant if needed |
| Splitting sentences to embed UI links | Translators cannot reorder links | Use structured rich-text placeholders/components |
| Testing only English | Misses reordering bugs in other locales | Test at least one placeholder-reordering locale |
| Using JVM default locale on servers | Concurrent requests get wrong formats | Pass `Locale` per user/request |

## 18. Practice Exercises

**Exercise 1.** Code builds the sentence:

```java
String text = "Welcome " + user + " to " + product + ".";
```

Design the resource so translators can swap `user` and `product`.

**Suggested answer:**

```properties
welcome=Welcome {0} to {1}.
```

Another locale can write `welcome={1} chào đón {0}.` — changing the order of `{1}` and `{0}` without altering Java's argument order.

**Exercise 2.** Why is a `ResourceBundle` containing `files=files` and `prefix=You have` insufficient for a multilingual UI?

**Answer:** Those are isolated fragments; translators cannot control full-sentence grammar, including count placement and plural variants. Design `files.remaining=You have {0,number,integer} files remaining.` with an appropriate plural policy instead.

**Exercise 3.** Given `Object[] args = {"Lan", 3, "Minh"}`, the translator wants the recipient to appear first. Does the array element order need to change?

**Answer:** No. Keep the contract `{0}` = sender, `{1}` = count, `{2}` = recipient; the translation simply starts with `{2}`.

**Exercise 4.** What does `It''s {0}''s book.` print for `{0} = Lan`?

**Answer:** `It's Lan's book.`. In `MessageFormat` syntax, literal single quotes must be escaped.

**Exercise 5.** A translator wants to emphasize the recipient and writes `"{2} đã nhận {1} tệp do {0} gửi."`. What must QA verify?

**Answer:** All three placeholders keep their exact roles, `{1}` is formatted by locale when needed, no required keys or plural variants are missing, and the UI has room to display the sentence.

**Exercise 6.** A page has a "Terms" link inside a sentence. Should the sentence be split into three resource keys and joined with text/links in Java?

**Answer:** No, if doing so locks grammatical order. Use a rich-text pattern with component-style placeholders or an equivalent UI design so translators can arrange the link safely.

**Exercise 7.** Why shouldn't the same key `open` be used for a button to open a document and an "open" status label?

**Answer:** The English word looks identical, yet grammatical role and meaning differ; target languages may require two different translations. Split keys by context.

**Exercise 8.** If translating the full sentence produces longer text than the source, should you trim the message in `ResourceBundle` to fit the UI?

**Answer:** Not as the default measure. Prefer flexible layouts, wrapping/resizing, and multi-locale testing; if a short variant is genuinely needed, provide **an independent short message** with its own context and QA rather than blindly chopping the long sentence.

## 19. Summary

- **A message is a meaningful linguistic unit**: store **the complete sentence** in one resource entry rather than splitting words/phrases and concatenating in Java.
- **Arguments are data; word order belongs to the translation.** `MessageFormat` lets translators place `{2}` before `{0}` while Java argument passing stays unchanged.
- Use **`ResourceBundle` + `MessageFormat(pattern, locale)`** with documented placeholder schemas, managed translations, and explicit fallback policies.
- **Plurals, gender/person/case, and rich text** may require message variants or stronger frameworks; never solve them with naive string concatenation.
- Verify **`MessageFormat` escaping, parameter types, key completeness, context, reorderability, flexible UI layouts, and accessibility**.
- Separate natural-language content from **UI behavior/security**: never embed raw HTML in translations or turn user data into templates.
- Localization quality comes from **code structures that allow proper translation**, not merely swapping isolated strings.

**References:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
- [Unicode UTS #35 — MessageFormat and locale data](https://unicode.org/reports/tr35/)
