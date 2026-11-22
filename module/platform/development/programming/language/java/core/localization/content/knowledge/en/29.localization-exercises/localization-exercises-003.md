# Creating Parameterized Messages and Quantity Branches in Java

A multilingual application should never hardcode concatenated sentence fragments such as `"Bạn có " + count + " tệp"` across every language. Beyond inserting numbers, names, or dates into a message, **sentence grammar can change depending on quantity**, and component ordering can vary across languages. For example, English distinguishes "one file" from "two files," whereas Vietnamese can use "1 tệp" and "2 tệp" without inflecting the noun.

In Core Java, you can combine **`ResourceBundle`**, **`MessageFormat`**, and **`ChoiceFormat`** to build translated messages, insert arguments, and pick **branches by numeric threshold**. This is a **comprehensive hands-on guide**: we will write a Java 17+ program, define English/Vietnamese resources, analyze patterns, verify output, and learn when standard Java capabilities fall short for plural rules across many languages.

**Important limitation upfront:** `ChoiceFormat` is a threshold/number-based branch selector; **it is not a full implementation of Unicode CLDR plural categories**. `java.text.MessageFormat` in Java 17 does **not** directly understand ICU syntax `{count, plural, ...}`. Systems requiring complex language-specific plural/select rules should use an appropriate engine, such as ICU4J, or a controlled translation strategy.

## 1. The Problem: A Message with Multiple Parameters and Sentence Forms

Suppose a document management page needs to notify user "An" about the number of files:

| File Count | English | Vietnamese |
| ---: | --- | --- |
| 0 | An: no files | An: không có tệp |
| 1 | An: one file | An: 1 tệp |
| 2 | An: 2 files | An: 2 tệp |
| 5 | An: 5 files | An: 5 tệp |

There are two variable pieces of information:

- **`owner`**: user's name, e.g. `An` — text parameter.
- **`count`**: number of files, e.g. `0`, `1`, or `2` — numeric parameter and branch selection condition.

A proper solution **separates translatable source text** from business logic. Code supplies meaningful parameters; locale resources decide which sentence is used. The formatter inserts arguments and formats numbers according to the locale.

### Why Is String Concatenation with + Insufficient?

An easy-to-write but poorly internationalized example:

~~~java
String message = owner + " has " + count + " files";
~~~

When `count = 1`, the result is `"An has 1 files"` — grammatically wrong in English. Replacing it with `count == 1 ? "file" : "files"` still hardcodes English sentence structure in code, ignoring languages with more plural forms or different word orders.

Do not reduce the problem to "word-by-word translation":

~~~text
prefix + number + suffix
~~~

Some languages must change the **entire sentence**, prepositions, grammatical gender, case, word order, or noun forms. Therefore, **translators need control over the complete message for each branch**, not just the single word "file."

## 2. Three Participating APIs and Their Distinct Responsibilities

| API | Package | Role |
| --- | --- | --- |
| `Locale` | `java.util` | Specifies content language/region and formatting conventions |
| `ResourceBundle` | `java.util` | Loads translated text patterns by locale and fallback |
| `MessageFormat` | `java.text` | Inserts `{0}`, `{1}` parameters; invokes number/date/time formatting and handles choices |
| `ChoiceFormat` | `java.text` | Selects a message segment by numeric threshold |
| `NumberFormat` | `java.text` | Formats numbers, currencies, and percentages when separate control is needed |

In the Java 17 example, the flow of responsibility is:

~~~text
Business logic: owner="An", count=2
                   |
                   v
           check count >= 0
                   |
                   v
      determine Locale: en-US / vi-VN
                   |
                   v
     ResourceBundle.getBundle("messages", locale)
                   |
                   v
     retrieve pattern for key "files"
                   |
                   v
       new MessageFormat(pattern, locale)
                   |
                   v
     format(new Object[]{owner, count})
                   |
                   v
     locale-specific message output
~~~

**`Locale` does not translate sentences automatically.** Application translations must be provided in bundles or an equivalent localization system. `MessageFormat` does not guess whether the user wants "file" or "tệp"; it formats according to the pattern supplied by translators or the product team.

## 3. Parameter Syntax in MessageFormat

Some basic patterns:

~~~text
Hello, {0}!
User {0} has {1,number,integer} points.
The price is {0,number,currency}.
The deadline is {0,date,short}.
Completion: {0,number,percent}.
~~~

Key elements:

- `{0}`: parameter at **index 0** in the argument array.
- `{1}`: parameter at **index 1**; does not have to appear after `{0}` in the pattern.
- `{1,number,integer}`: formats as an integer using the `MessageFormat`'s locale.
- `{0,number,currency}`: formats as currency using the locale; does **not** know the transaction's actual currency unit if only a raw number is passed.
- `{0,date,short}` and `{0,time,short}`: rely on `java.text.DateFormat`; in Java 17, you must supply a compatible temporal argument type, typically `java.util.Date`.
- `{1,choice,...}`: selects a branch based on a number.

**Argument indices are 0-based.** Parameter order can change in translations. Given the same two arguments `[name, score]`, one language can place `{0}` before `{1}` while another reverses them.

### MessageFormat Does Not Use String.format Syntax

`MessageFormat` differs from `String.format` or `Formatter`. In `String.format`, you typically see `%s`, `%d`, and `%.2f`, whereas `MessageFormat` uses `{0}`, `{1,number}`, and its own format types.

Do not write `"%s có %d tệp"` and pass that pattern directly into `new MessageFormat(...)` expecting percent specifiers to be substituted like `String.format`.

If argument `{0}` is a text string, `MessageFormat` inserts it verbatim—without translating it, without HTML-escaping it, and without enforcing length limits. Validation and context-safe rendering remain the application's responsibility.

## 4. ChoiceFormat: Selecting Branches by Threshold

A choice pattern:

~~~text
{1,choice,0#no files|1#one file|1<{1,number,integer} files}
~~~

Breakdown:

1. `1` right after `{` is the **argument index** — meaning `count` is the second element in the argument array.
2. `choice` specifies `ChoiceFormat`.
3. `0#no files` means the branch starting at **threshold 0 inclusive**.
4. `1#one file` means the branch starting at **threshold 1 inclusive**.
5. `1<{1,number,integer} files` means the branch for **values strictly greater than 1**, and the selected segment contains `{1,number,integer}`, which gets formatted again.
6. `|` separates the choices.

Branches are matched against **numeric limits** sorted in ascending order. It is not an arbitrary `if/else` expression, does not accept booleans, and does not classify language plurals automatically. For values outside expected thresholds, validate inputs and define an appropriate default branch.

### Meaning of # and <

| Syntax | Conceptual Meaning |
| --- | --- |
| `0#text` | Threshold **inclusive** of 0 |
| `1#text` | Threshold **inclusive** of 1 |
| `1<text` | Threshold **strictly greater than** 1 |
| `2#text` | Threshold **inclusive** of 2 |

Because `ChoiceFormat` uses thresholds and floating-point numbers, behavior with decimals or large numbers must be tested carefully. For **file counts**, business logic should accept **non-negative integers**; do not let `1.5` files slip through and then be surprised when the formatter picks a branch based on the floating-point value and rounds it upon display.

**Do not skip negative-number checks.** With a pattern starting at threshold 0, `ChoiceFormat` selects the first branch for values below the lowest threshold. If `count=-1`, displaying "no files" masks invalid business data. Reject it at the domain layer.

### Branches Can Contain Nested Parameters

In the example:

~~~text
1<{1,number,integer} files
~~~

When `count=2`, `ChoiceFormat` selects the segment containing `{1,number,integer}`; `MessageFormat` recognizes `{...}` and **formats the selected segment again**. This nested choice formatting mechanism is supported by the Java 17 API.

Full pattern example:

~~~text
{0}: {1,choice,0#no files|1#one file|1<{1,number,integer} files}
~~~

With `Object[]{"An", 2}` and `Locale.US`, the result is:

~~~text
An: 2 files
~~~

**Beware of recursion:** manually constructing `ChoiceFormat` and `MessageFormat` instances whose choice branches reference formatters cyclically can trigger infinite recursion. Keep templates reviewed and tested across real data domains.

## 5. Vietnamese Does Not Have to Mirror English Branches

A simple Vietnamese pattern:

~~~text
{0}: {1,choice,0#không có tệp|0<{1,number,integer} tệp}
~~~

Here:

- `count=0` → `An: không có tệp`.
- `count=1` → `An: 1 tệp`.
- `count=2` → `An: 2 tệp`.

The key point is **not forcing every language to have the same number of branches**. English in this example uses three branches; Vietnamese uses two. That is a **content choice specific to this message**, not a claim that every Vietnamese grammatical construction needs only two choices or that every Vietnamese message shares the same quantity rules.

Instead of trying to reuse a single choice pattern across all locales, each translation should have a complete pattern reviewed by someone fluent in that language.

### Translations Can Reorder Parameters

Suppose a message needs two parameters, `user` and `count`. One language might start with the user's name, while another starts with the count. Indexed placeholders allow translators to reorder them **without changing the argument array** in business code.

Avoid concatenating fragments from multiple bundles like:

~~~java
String message = bundle.getString("prefix")
        + count
        + bundle.getString("suffix");
~~~

This locks down sentence structure and can make grammatically accurate translation impossible. Translate the **entire message or complete branch**.

## 6. Hands-On Project Structure

Create the structure:

~~~text
plural-message-demo/
  src/
    PluralMessagesDemo.java
  resources/
    messages_en.properties
    messages_vi.properties
  out/                    (created during compilation)
~~~

The three actual source files needed are one Java file and two resource files. The `out` directory is created by the commands below; it is not a hand-written source directory.

### File 1: resources/messages_en.properties

~~~properties
files={0}: {1,choice,0#no files|1#one file|1<{1,number,integer} files}
today=Today''s total: {0,number,integer}
~~~

### File 2: resources/messages_vi.properties

~~~properties
files={0}: {1,choice,0#không có tệp|0<{1,number,integer} tệp}
today=Tổng hôm nay: {0,number,integer}
~~~

**File explanation:**

- Each file is a properties-based `ResourceBundle`.
- The `files` key holds the complete language-specific pattern.
- The `today` key illustrates single quotes in `MessageFormat`.
- `{0}` is the user name; `{1}` is the file count.
- The English pattern has three branches; the Vietnamese pattern has two branches.
- On **JDK 17**, `PropertyResourceBundle` reads properties as **UTF-8 by default**, with an ISO-8859-1 compatibility fallback when bytes are not valid UTF-8. Save the files as UTF-8 and verify charset handling in your build.
- Do not place `messages_vi.properties` inside a package subdirectory different from the base name if code calls `getBundle("messages", ...)` at the classpath root.

**Single-quote rule:** In `MessageFormat`, a single quote has special meaning for quoting literal pattern characters. `Today''s` (two `'` characters) outputs one apostrophe: `Today's`. Writing `Today's` with a single apostrophe in a pattern can cause subsequent text to be treated as quoted, preventing placeholders from being substituted properly.

### File 3: src/PluralMessagesDemo.java

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class PluralMessagesDemo {
    private static String renderFiles(
            ResourceBundle messages,
            Locale locale,
            String owner,
            int count) {

        if (count < 0) {
            throw new IllegalArgumentException(
                    "count must be >= 0");
        }

        String pattern = messages.getString("files");
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] { owner, count });
    }

    public static void main(String[] args) {
        Locale english = Locale.US;
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        ResourceBundle en =
                ResourceBundle.getBundle("messages", english);
        ResourceBundle vi =
                ResourceBundle.getBundle("messages", vietnamese);

        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println("EN " + count + ": "
                    + renderFiles(en, english, "An", count));
        }

        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println("VI " + count + ": "
                    + renderFiles(vi, vietnamese, "An", count));
        }

        MessageFormat quoted = new MessageFormat(
                en.getString("today"), english);
        System.out.println("Quoted: "
                + quoted.format(new Object[] { 2 }));

        System.out.println("Argument as data: "
                + renderFiles(en, english, "Eva {0}", 2));

        try {
            renderFiles(en, english, "An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Negative count: rejected");
        }
    }
}
~~~

This program is **runnable on Java 17** once both properties files are on the classpath as shown next. It intentionally creates a new formatter per render so no mutable `MessageFormat` state is shared across requests.

### Compiling and Running on macOS/Linux

From the `plural-message-demo` directory:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/PluralMessagesDemo.java
cp resources/messages_en.properties out/
cp resources/messages_vi.properties out/
java -cp out PluralMessagesDemo
~~~

### Compiling and Running on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/PluralMessagesDemo.java
Copy-Item resources/messages_en.properties out/
Copy-Item resources/messages_vi.properties out/
java -cp out PluralMessagesDemo
~~~

`java -cp out` finds `PluralMessagesDemo.class` as well as `messages_en.properties` and `messages_vi.properties` at the classpath root.

### Expected Stdout

When properties files are saved as UTF-8 and the terminal renders Unicode:

~~~text
EN 0: An: no files
EN 1: An: one file
EN 2: An: 2 files
VI 0: An: không có tệp
VI 1: An: 1 tệp
VI 2: An: 2 tệp
Quoted: Today's total: 2
Argument as data: Eva {0}: 2 files
Negative count: rejected
~~~

**Verification:** the example's `MessageFormat`, `ChoiceFormat`, parameter, and apostrophe logic has been verified on the JDK: English/Vietnamese branches, a string containing `{0}` as data, and negative-count rejection all produce the expected results. Loading via `ResourceBundle` depends on placing the two resource files on the classpath as instructed; if a file is missing, Java throws `MissingResourceException` instead of producing the stdout above.

If a Windows terminal displays Vietnamese characters as question marks even though the program read the properties correctly, check the **console and file encodings** rather than concluding `ChoiceFormat` picked the wrong branch.

## 7. Step-by-Step Walkthrough of the Example

### Step 1 — Choose Locales Explicitly

~~~java
Locale english = Locale.US;
Locale vietnamese = Locale.forLanguageTag("vi-VN");
~~~

`Locale.US` represents `en-US`; `Locale.forLanguageTag("vi-VN")` selects Vietnamese in Vietnam. Do not rely on the server's `Locale.getDefault()`, because a server can serve multiple users in different languages.

### Step 2 — Load the Pattern for the Locale

~~~java
ResourceBundle en =
        ResourceBundle.getBundle("messages", english);
~~~

Java resolves the bundle matching `messages` and the locale. For `en-US`, it loads the language bundle `messages_en.properties` when the more specific `messages_en_US.properties` does not exist. For `vi-VN`, `messages_vi.properties` is used when `messages_vi_VN.properties` does not exist.

If **no** matching translation exists, `ResourceBundle` may try falling back to the JVM default locale and the root bundle, depending on API rules. Therefore, real applications must define an **intentional fallback language** (typically a root bundle or explicit product policy) so users do not accidentally receive the server's OS language.

### Step 3 — Business Data Validation

~~~java
if (count < 0) {
    throw new IllegalArgumentException("count must be >= 0");
}
~~~

Numeric thresholds do not replace input validation. A negative file count is meaningless here. If the application has an "unknown count" state, model it as a separate state or dedicated message instead of silently encoding `-1` and feeding it into a choice pattern.

### Step 4 — Select Branch and Substitute Parameters

~~~java
String pattern = messages.getString("files");
MessageFormat formatter = new MessageFormat(pattern, locale);
String output = formatter.format(
        new Object[] { owner, count });
~~~

This **illustrative snippet** corresponds to the method in the main program. `MessageFormat` parses the pattern, selects the `ChoiceFormat` branch by `count`, and inserts `owner`/`count`. The numeric parameter in `{1,number,integer}` is formatted using the locale passed when constructing the formatter.

### Step 5 — Text Inside Arguments Is Not Template Syntax

In the example `owner = "Eva {0}"`, the output is:

~~~text
Eva {0}: 2 files
~~~

`{0}` inside an **argument value** is treated as literal data, not as a placeholder to evaluate a second time. This differs from taking an **untrusted pattern** and calling `new MessageFormat(pattern)`. Patterns carry special syntax and must be treated as curated/reviewed content configuration, never user-editable without validation.

**Note:** argument data still requires escaping for the **output context**. Inserting into HTML requires HTML escaping, SQL requires parameterization, and logs require handling control characters; `MessageFormat` is not a security sanitizer.

## 8. Pluralization in Other Languages

Our example has only two languages and one "file count" context. However, many languages have complex quantity systems:

- English typically has singular and plural forms, plus an optional distinct phrasing for zero if desired by the product.
- Vietnamese in this example does not require noun inflection between 1 and 2.
- Languages such as Russian, Polish, or Arabic have multiple **plural categories** and rules based on modulo remainders or numeric forms, not simply `count == 1`.
- Decimals, numbers with fractional digits, or spoken number forms can also affect the category.

In the Unicode CLDR ecosystem, cardinal/ordinal plural rules divide values into categories such as `zero`, `one`, `two`, `few`, `many`, and `other` depending on the language. **Not every language uses all of these categories**, and categories are not always defined by a simple ascending threshold.

### ChoiceFormat Does Not Understand Plural Categories

A choice pattern such as:

~~~text
0#no files|1#one file|1<some files
~~~

handles only **numeric intervals by threshold**. It cannot compute, for example, a category depending on `n % 10` and `n % 100` according to a language's grammar. For a small fixed numeric domain, you can branch manually; however, emulating a complex plural system with a long list of thresholds is error-prone and hard to maintain.

**Do not translate an English pattern word-for-word and reuse the exact 0/1/2 branches for Russian or Arabic.** Those languages require verified plural category rules and full-sentence translations.

### ICU Plural Syntax Differs from Java 17 MessageFormat

An ICU-style pattern conceptually looks like:

~~~text
{count, plural,
  =0 {No files}
  one {One file}
  other {# files}
}
~~~

This is an **ICU MessageFormat syntax pattern**, **not** a pattern directly supported by `java.text.MessageFormat` in Java 17. On Java 17, `MessageFormat` recognizes format types like `number`, `date`, `time`, and `choice`, and does **not recognize the `plural` format type**.

If accurate plural/select formatting is needed across many languages, you can use **ICU4J** or an equivalent localization platform, while accounting for the added dependency, API versioning, CLDR updates, resource maintenance, and integration testing. Do not assume an external library shares identical syntax or full compatibility with Core Java formatters.

## 9. Important Technical Boundaries

### 9.1. Business Integers vs. Integer Formatting

`{1,number,integer}` means **print in integer format** via the locale's `NumberFormat`. It does not guarantee that an input of `1.5` is a "valid one-and-a-half file." If the product counts discrete items, **use an integer type** and validate at the boundary before formatting.

When working with very large `long` values, remember that `ChoiceFormat` operates on `double` floating-point limits. Domains needing exact integer distinction beyond `double` precision should not rely on choice equality comparisons for business decisions. You can select the branch using exact integer logic first and then pass the selected message to the formatter for printing.

### 9.2. Grouping Separators Depend on Locale

For `count = 1200`, an English `{1,number,integer}` pattern may display `1,200`, while Vietnamese may display `1.200` depending on the JDK's locale data. Rendering also depends on the CLDR/provider version and numbering system settings.

Therefore, do not store the rendered string as the **count value** in a database or API. Store the integer `1200`, and format it at the UI layer using the user's chosen locale.

### 9.3. NumberFormat and MessageFormat Are Mutable

`MessageFormat` exposes `applyPattern`, `setFormat`, `setLocale`, and other state-mutating operations; `NumberFormat` is also commonly mutable. Do not share a single mutable formatter across concurrent multi-threaded requests without synchronization management.

In the example, each render constructs a new `MessageFormat` from the pattern and locale. For high-traffic systems, analyze caching, cloning, or thread confinement according to contract, rather than prematurely optimizing by sharing one mutable formatter across all users.

### 9.4. Locale-Formatted Messages Do Not Imply Timezone Handling

If a message includes date/time:

~~~text
Meeting on {0,date,short} at {0,time,short}
~~~

Default `date/time` formatters delegate to `java.text.DateFormat` and its timezone configuration. On Java 17, the typical compatible argument is `java.util.Date`, **not `LocalDate` directly** for `{0,date,short}`.

If the source data is an `Instant` or a meeting in the user's time zone, resolve the proper `ZoneId` in business logic and configure an appropriate date/time formatter. Switching `Locale` neither infers a time zone nor converts `LocalDate` into `java.util.Date`.

A clean, controlled approach is to format dates/times using `java.time.format.DateTimeFormatter` with `Locale` and `ZoneId`, then pass the **formatted string** as argument `{0}` to the message. That keeps time zone and calendar selection decoupled from sentence grammar.

### 9.5. Currency Formatting Does Not Determine the Transaction Currency

`{0,number,currency}` uses `NumberFormat.getCurrencyInstance(locale)` based on the formatter's locale. If an order is actually in USD while the viewer has a Vietnamese locale, do not present the transaction as VND simply because of the UI locale. Keep `Currency` and `BigDecimal` separate, apply business rounding rules, and format using a formatter configured for the actual currency unit.

### 9.6. MessageFormat Quoting Differs from Java String Literals

There are two separate escaping layers:

1. **Java source literals**: `"` quotes, `\` characters, and escapes must be valid to produce a Java `String`.
2. **MessageFormat patterns**: apostrophe `'` and curly braces `{ }` carry `MessageFormat` syntax meaning.

In properties files, you typically do not escape `"` as in Java string literals, but you still must write `''` for a literal apostrophe if the text is processed by `MessageFormat`.

Example:

~~~java
String pattern = "Today''s total: {0,number,integer}";
System.out.println(new MessageFormat(pattern, Locale.US)
        .format(new Object[] { 2 }));
// Today's total: 2
~~~

This snippet assumes `import java.text.MessageFormat;` and `import java.util.Locale;`. When translators use apostrophes in French or other translations, document this rule clearly; otherwise patterns can render incorrectly or swallow placeholders.

### 9.7. Do Not Build Patterns by Unsanitized String Concatenation

Do not concatenate user input directly into a **pattern** before parsing, for example:

~~~java
String unsafePattern = userText + " {0}";
MessageFormat formatter = new MessageFormat(unsafePattern, locale);
~~~

This is an **anti-pattern**. If `userText` contains `{...}` or apostrophes, it can be interpreted as template syntax, causing exceptions or unexpected output. Keep **fixed, reviewed patterns** in resource files and pass user data solely through the arguments array.

Even so, `MessageFormat` output is not automatically safe for HTML, JSON, SQL, shell, or markdown. Apply appropriate encoding/escaping **at the output sink** while validating untrusted inputs.

## 10. Thorough Branch Testing Before Release

A minimal test matrix for this practice exercise:

| Locale | count | Expected Result |
| --- | ---: | --- |
| `en-US` | 0 | `An: no files` |
| `en-US` | 1 | `An: one file` |
| `en-US` | 2 | `An: 2 files` |
| `vi-VN` | 0 | `An: không có tệp` |
| `vi-VN` | 1 | `An: 1 tệp` |
| `vi-VN` | 2 | `An: 2 tệp` |
| `en-US` | -1 | Throws `IllegalArgumentException` before formatting |
| `en-US` | 2, name `Eva {0}` | `Eva {0}: 2 files` |
| `en-US` | `today=2` | `Today's total: 2` |

Do not test only one default value like 2. For choice branches, every boundary `0`, `1`, `2`, and invalid thresholds must be tested.

### Additional High-Value Tests

- **Missing bundle keys:** `getString("files")` can throw `MissingResourceException`. Verify required keys via build/test checks.
- **Bundle fallback:** test a locale with a full regional file, a locale with only a language file, and an unmatched locale; verify the product's chosen fallback language.
- **Parameter ordering:** translations swapping `{0}` and `{1}` still render the right values.
- **Quoting:** single apostrophes, quoted braces, and patterns with nested choices.
- **Integer boundaries:** 0, 1, 2, very large numbers, negative numbers, null or unknown values.
- **Number formatting:** verify `1,200`, `1.200`, and other locales on the target JDK without assuming invariant grouping separators.
- **Encoding:** names with Vietnamese diacritics, emojis, Unicode combining characters, and UTF-8 properties files.
- **Concurrency:** simultaneous requests/locales do not corrupt shared formatter state.
- **Security:** inputs like `"{0}"`, apostrophes, HTML tags, and line breaks remain literal data rather than becoming template syntax or executable content.
- **JDK/provider changes:** run regression tests when upgrading the JDK or changing CLDR data.

You can write a small test helper:

~~~java
private static void assertEquals(String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected <" + expected + "> but got <" + actual + ">");
    }
}
~~~

This is an **illustrative snippet** inside a class; if using JUnit, choose its standard assertions and test runner. For critical messages, assert the **entire sentence**, not just character length or substring presence of a user's name.

### Testing Against Real Resources Matters More Than Hardcoded Patterns

If a unit test only constructs `new MessageFormat(...)` from a hardcoded string, it has not proven that `messages_vi.properties` contains valid syntax, that resources are packaged into the JAR, that every key is translated, or that product fallback works.

Therefore, include integration tests calling `ResourceBundle.getBundle(...)` against the **actual build artifact**. This is especially important if the build runs encoding conversions on properties files or packages via Maven/Gradle/JAR.

## 11. Designing When Counts Are Asynchronous or Uncertain

Some UIs distinguish "counting in progress," "no permission to view," "no data available," and "count is 0." These are **distinct business states**, so do not collapse all of them into `count=0`.

For example:

~~~text
LOADING       → Checking file count…
FORBIDDEN     → You do not have permission to view this information.
UNKNOWN       → File count unavailable.
KNOWN(0)      → No files.
KNOWN(1)      → 1 file.
KNOWN(2)      → 2 files.
~~~

This diagram **illustrates UI states**, not a standard Java API. Select the **message key** by business state first, and invoke `ChoiceFormat` only when the count is known and valid.

Do not pass `null`, `NaN`, `Infinity`, or a negative sentinel into a choice pattern expecting the formatter to infer business semantics. When counts arrive from multiple sources, validate and reconcile counting policy before rendering.

## 12. Extending with ChoiceFormat in Java Code

Besides embedding `{1,choice,...}` inside a pattern, you can build a `ChoiceFormat` programmatically and attach it to `MessageFormat`:

~~~java
MessageFormat message = new MessageFormat(
        "{0}: {1}", Locale.US);

double[] limits = { 0, 1, 2 };
String[] forms = {
        "no files",
        "one file",
        "{1,number,integer} files"
};

ChoiceFormat choice = new ChoiceFormat(limits, forms);
message.setFormatByArgumentIndex(1, choice);

String output = message.format(
        new Object[] { "An", 2 });
~~~

This **illustrative snippet** assumes `import java.text.MessageFormat;`, `java.text.ChoiceFormat;`, and `java.util.Locale;`. Limits 0/1/2 apply to **integer file counts**. If fractional numbers are permitted, redesign thresholds to match domain semantics rather than arbitrarily reusing those three limits.

Constructing `ChoiceFormat` in code helps when an organization wants branch-selection logic in Java; however, if sentences and word order must be localized, the forms/resources still need to come from the target locale. Also avoid building formatter graphs with infinite recursive references when branches contain nested placeholders.

### When Should Branching Live in Java Instead of ChoiceFormat?

If business branching depends on more than just `count` (e.g., account status, access permissions, product tiers) or requires complex CLDR plural rules, Java code can determine the **message key** via an explicit policy and then format the corresponding sentence. Branching must be tested per **language and grammar**, rather than blindly applying `if (count == 1)` across all locales.

For multilingual interfaces needing flexible plural, gender, or grammatical case handling, consider a plural/select library designed for that purpose instead of stretching `ChoiceFormat` beyond its scope.

## 13. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating English with `"has " + count + " files"` | Wrong for 1; hard to translate word order | Use full-sentence message patterns |
| Using English plural branches for every locale | Broken grammar in other languages | Translate patterns/branches per language |
| Passing ICU plural syntax to Java 17 `MessageFormat` | Unsupported format type | Use appropriate `ChoiceFormat` or an ICU engine |
| Treating `{0}` as a variable name | Argument is not substituted | Pass arguments by 0-based index |
| Omitting `{1,number,integer}` in the plural branch | Prints text only, omits number | Include the nested placeholder |
| Failing to reject negative counts | May wrongly print "no files" | Validate business rules beforehand |
| Using `double` without checking domain | Decimals/large numbers pick unintended branches | Accept integer counts only; handle exact domain |
| Treating formatted numbers as API data | Grouping dots/commas vary by locale | Store raw numbers; format in the UI |
| Relying on `Locale.getDefault()` on multi-tenant servers | Output depends on server OS locale | Pass `Locale` explicitly |
| Using a single apostrophe in a `MessageFormat` pattern | Unintentionally quotes placeholders | Write `''` to output `'` |
| Concatenating user input into the pattern | Input may be parsed as syntax | Keep patterns trusted; pass input in arguments |
| Assuming `MessageFormat` escapes HTML | Can produce unsafe markup | Escape according to the rendering sink |
| Failing to package properties onto classpath | `MissingResourceException` | Run integration tests on the final JAR/build |
| Lacking an intentional fallback bundle | UI falls back to server locale | Define an explicit fallback policy |
| Splitting one sentence into multiple translation keys | Unnatural translations, broken word order | Translate full sentences/branches |
| Sharing a mutable formatter across threads | State can be corrupted concurrently | Create per-use formatters or synchronize properly |
| Treating unknown count as 0 | Masks business state | Separate `LOADING`/`UNKNOWN`/`KNOWN` |
| Testing only `count=2` | Misses `0`/`1` boundary bugs | Test all branches and boundaries |
| Equating `ResourceBundle` with CLDR translations | JDK contains no app UI translations | Manage application resources separately |
| Assuming Vietnamese/English rules cover all plurals | Misses `few`/`many`/`zero`/etc. | Test per language and use an appropriate engine |

## 14. Follow-Up Practice Exercises

**Exercise 1 — Add another locale.** Create `messages_fr.properties` reviewed by someone fluent in French. Do not just swap the word "file"; translate the complete sentence and check `MessageFormat` apostrophes.

**Exercise 2 — Add another parameter.** Extend the message with `{2}` for a folder name, e.g. "An: 2 files in Projects". Allow translators to reorder the user name and folder name. Ensure `{2}` sits at the proper index in the argument array without hardcoded string concatenation.

**Exercise 3 — Expand test coverage.** Run counts 0, 1, 2, 3, 1200, and -1 for both English and Vietnamese; verify negative numbers are rejected and large integers stay exact at the business layer. For formatted large numbers, do not assume identical grouping separators across locales.

**Exercise 4 — Add an unknown state.** When the count is still being computed, use a dedicated `files.loading` key in the bundle instead of passing `-1` into `ChoiceFormat`.

**Exercise 5 — Evaluate ICU.** Pick a language with multiple plural categories. Examine why branching on `count == 1` is insufficient, and compare solving it with a CLDR plural engine versus threshold-based `ChoiceFormat`.

**Exercise 6 — Package and verify.** Build a JAR containing the class and both properties files, then run it on a machine/JVM with a different default locale. Confirm that passing `Locale.US`/`vi-VN` explicitly preserves the right language output.

### Self-Check Questions

**Question 1.** What is the difference between `{1}` and `{1,number,integer}`?

**Answer:** `{1}` formats the argument using the default type-based format, whereas `{1,number,integer}` formats it as a locale-specific integer; neither replaces type or domain validation.

**Question 2.** Why does the Vietnamese pattern in this exercise have two branches while English has three?

**Answer:** It is a translation choice per sentence. English in the example uses distinct "no/one/many files" forms, while Vietnamese uses a dedicated phrasing for zero and "n tệp" for counts of 1 or more.

**Question 3.** Why does `1<{1,number,integer} files` work when `count=2`?

**Answer:** `ChoiceFormat` selects the branch for values strictly greater than 1; because that branch contains `{...}`, `MessageFormat` processes the nested format element against the same arguments.

**Question 4.** If the user enters the name `Eva {0}`, will `{0}` be substituted a second time?

**Answer:** Not in this design: the user name is passed as an **argument**, not inside the pattern. You still must escape output for the target UI context.

**Question 5.** Does Java 17's `MessageFormat` automatically classify `few/many/other` across all languages per CLDR?

**Answer:** No. `ChoiceFormat` matches numeric thresholds; accurate plural categories across many languages require an appropriate engine/rule set, such as an ICU library.

**Question 6.** Can a single mutable `MessageFormat` instance be shared across all requests?

**Answer:** It should not be shared if anything might mutate the formatter or invoke it concurrently without synchronization. Prefer per-call creation, thread confinement, or proper synchronization.

## 15. References

- [MessageFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholder syntax, nested choice, and apostrophe rules.
- [ChoiceFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html): numeric thresholds, `#` and `<` symbols, choice patterns.
- [ResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): bundle lookup by locale, parent/fallback.
- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): properties files, UTF-8 reading and charset fallback.
- [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-specific number formatting.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locales, language tags, and language selection.
- [Unicode CLDR Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): plural categories and language data.
- [ICU MessageFormat Guide](https://unicode-org.github.io/icu/userguide/format_parse/messages/): expressing plural/select rules with an engine beyond Core Java 17.

**Key Takeaway:** **Resource files store translated sentences, `MessageFormat` inserts parameters, and `ChoiceFormat` picks branches by numeric threshold.** Validate numeric domains, pass `Locale` explicitly, translate complete sentences per language, test every branch, and distinguish `ChoiceFormat` from CLDR plural rules when scaling multilingual applications.
