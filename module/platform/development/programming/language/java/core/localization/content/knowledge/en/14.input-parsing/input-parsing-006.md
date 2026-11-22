# Locale-Aware Error Messages with Stable Error Codes in Java

## Objectives

When a user enters an invalid number, date, quantity, or form field, an application must solve **two distinct problems**:

1. **Identify the error type stably** so the application, API clients, monitoring, and tests handle it reliably—for example, `INPUT_NUMBER_INVALID`.
2. **Explain the error in a language appropriate** for the recipient—for example, “Số lượng không phải số hợp lệ.” or “Quantity must be a valid number.”

If translated sentences are used as error codes, the same failure ends up with multiple identifiers across languages. If a hardcoded English string is returned to everyone, the UI becomes harder to use and ignores localization requirements. The right design **keeps codes independent of `Locale`, while looking up and formatting messages by `Locale`**.

After this lesson, you will be able to:

- Distinguish **error code**, **message key**, **localized message**, **field identifier**, **HTTP status**, and **technical detail**.
- Design a stable list of error codes for input parsing that does not depend on user names or languages.
- Use `ResourceBundle` with `Locale` and `MessageFormat` to produce multilingual messages from a single validation result.
- Handle parse errors in layers: missing data, invalid syntax, trailing remainder, out-of-range values, and business rule violations.
- Build API contracts and tests where the **code stays constant** while the **message changes** by locale.
- Recognize common pitfalls: branching logic on message text, confusing validation errors with server errors, fallback hiding missing translations, and leaking sensitive data in logs or messages.

This lesson belongs to **Input Parsing**: first detect and classify the error, and only then generate a localized message. Translated text should never become part of the parsing algorithm.

## 1. One Error Can Have Many Phrasings, Only One Identifier

Suppose a form requires a quantity between 1 and 100. The user enters `abc`.

The same validation result can be represented as:

| Component | Vietnamese | English |
| --- | --- | --- |
| Error code | `INPUT_NUMBER_INVALID` | `INPUT_NUMBER_INVALID` |
| Message key | `error.number.invalid` | `error.number.invalid` |
| Message | `Số lượng không phải số hợp lệ.` | `Quantity must be a valid number.` |
| Field identifier | `quantity` | `quantity` |
| Illustrative HTTP status | `400` | `400` |

**Error codes and field identifiers are machine-readable identifiers. Messages are human-readable text.** A user switching languages from Vietnamese to English does not change the validity of `abc`, nor should it force the API to emit a different error type.

Processing flow:

```text
Raw input + input rules/Locale
               |
        Parse + validate
               |
       Structured result
       code=INPUT_NUMBER_INVALID
       field=quantity
               |
        Look up message key
               |
      ResourceBundle + Locale
          /             \
         v               v
    vi-VN message    en-US message
         \               /
          v             v
    Response code unchanged
    Reader-appropriate message
```

**Error detection** does not depend on how a sentence is translated. If a translator edits “không phải số hợp lệ” to “vui lòng nhập số”, the same `INPUT_NUMBER_INVALID` still represents the same error with the same handling policy.

## 2. Distinguishing Related Concepts

| Concept | Purpose | Example | Varies by Locale? |
| --- | --- | --- | --- |
| **Error code** | Public, stable identifier for an error category | `INPUT_NUMBER_INVALID` | No |
| **Message key** | Resource bundle key identifier | `error.number.invalid` | No |
| **Localized message** | Explanation for the user | `Số lượng không phải số hợp lệ.` | Yes |
| **Field identifier** | Identifies the failing data field | `quantity` | No |
| **Localized field label** | Human-readable field name in the UI | `Số lượng` / `Quantity` | Yes |
| **HTTP status** | Protocol-level outcome classification | `400 Bad Request` | No |
| **Context parameters** | Values interpolated into message templates | `min=1`, `max=100` | Values stable; display formatting may vary by locale |
| **Technical detail / diagnostic** | For system troubleshooting | parse position, exception type | Should not be shown as public UI text |

Even though the code and key in the example look similar, they **do not have to be identical strings**:

- `INPUT_NUMBER_INVALID` can be the identifier in the API contract.
- `error.number.invalid` can be the `ResourceBundle` key name.
- A mapping from code to key is maintained in code/configuration, allowing resource structure changes **without breaking client contracts**.

Likewise, `HTTP 400` does not replace error codes. Many failures—missing field, invalid number, malformed date—can all use HTTP 400 while requiring distinct codes so clients can highlight the right field or trigger specific handling.

Do not confuse `Locale` with **time zone**, **currency unit**, or the **user's physical region**. The locale used for parsing/formatting can differ from the preferred locale for displaying messages if the application defines such a policy; never infer sensitive information from a `Locale`.

## 3. First Step: Classify Errors Before Translating

For a numeric field, these cases should not be collapsed together if the application needs distinct behaviors:

| Input Condition | Illustrative Error Code | Meaning |
| --- | --- | --- |
| Missing value or empty string | `INPUT_NUMBER_REQUIRED` | Required field was not entered |
| Cannot start parsing as a number | `INPUT_NUMBER_INVALID` | Invalid numeric syntax |
| Parser reads only prefix `10` of `10abc` | `INPUT_NUMBER_INVALID` | Remainder violates number-only field contract |
| Parsed number exceeds bounds | `INPUT_NUMBER_OUT_OF_RANGE` | Valid numeric type, outside value domain |
| Number has more decimal digits than allowed | `INPUT_NUMBER_SCALE_INVALID` | Violates business precision/scale requirement |

These codes are **sample application designs**, not constants provided by the JDK. Applications may choose different names, provided they remain consistent in meaning and granularity.

Ideal workflow:

1. Receive the input value and context, including the field's locale if users enter numbers/dates in a regional format.
2. Distinguish a *missing field* from a *field with invalid content* if business logic requires separate responses.
3. Parse using the proper grammar/locale and verify **full input consumption** if the field accepts only a single value.
4. Check type, value domain, and business rules; do not treat parse success as proof that all constraints are met.
5. Return a structured result containing the valid value **or** a fixed error code—no translation yet.
6. When building the user response, select the display locale, resolve the message template, format parameters, and output the result.

Separating these steps lets the exact same validation algorithm serve web UIs, mobile apps, CLIs, and batch imports. Each channel can choose an appropriate presentation without altering core logic.

## 4. Why Should Messages Never Drive Logic?

A fragile approach:

```java
if (errorMessage.equals("Số lượng không phải số hợp lệ.")) {
    highlightQuantityField();
}
```

This is an **illustrative anti-pattern**, assuming `errorMessage` and `highlightQuantityField` exist. When the user switches to English, the message changes and the condition stops matching. Even within Vietnamese, a wording or punctuation tweak by a translator can break the logic.

Instead, use:

```java
if (errorCode == ErrorCode.INPUT_NUMBER_INVALID) {
    highlightQuantityField();
}
```

This illustrates application code using an `ErrorCode` enum and corresponding UI handler. `ErrorCode` is a machine-readable type/identifier, not a display sentence.

The same applies to logging and monitoring: if alerts or metrics aggregate by message text, one error splits across languages, placeholders, and translation revisions. Aggregating by error code stays stable.

**Never parse message strings** to recover business semantics. Translated text is not a data protocol, and word order, punctuation, and number formatting can legitimately vary across locales.

## 5. Using `ResourceBundle` to Map Codes to Messages

Java provides `java.util.ResourceBundle` to look up resource strings by base name and `Locale`. For parameterized messages, use `java.text.MessageFormat`.

Example resource family:

```text
messages.properties
messages_en.properties
messages_vi.properties
```

Root bundle:

```properties
# messages.properties
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
error.number.outOfRange={0} must be between {1} and {2}.
```

Vietnamese bundle:

```properties
# messages_vi.properties
field.quantity=Số lượng
error.number.required=Vui lòng nhập {0}.
error.number.invalid={0} không phải số hợp lệ.
error.number.outOfRange={0} phải nằm trong khoảng {1} đến {2}.
```

When producing a message:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);

String pattern = bundle.getString("error.number.invalid");
String fieldLabel = bundle.getString("field.quantity");

String message = new MessageFormat(pattern, locale)
        .format(new Object[] {fieldLabel});
```

This is an **illustrative snippet inside a method**, requiring imports for `ResourceBundle` and `MessageFormat`, plus a `locale` variable of type `Locale`. With Vietnamese, the result is `Số lượng không phải số hợp lệ.`; English yields the corresponding message.

**Separate error keys from field labels**:

- The code `INPUT_NUMBER_INVALID` does not embed the text “Số lượng”.
- The key `field.quantity` identifies the field's localized label.
- The pattern `error.number.invalid` has a `{0}` placeholder for the label.
- Other fields can reuse the same error type with different labels, while the technical `field` remains that field's stable identifier.

Do not build translated sentences by concatenating `"Sai " + fieldLabel` or `fieldLabel + " invalid"`: languages differ in word order and grammar. Put the entire sentence in the pattern so translators can reorder placeholders freely.

### Placeholders Also Need a Contract

In the pattern `"{0} must be between {1} and {2}."`:

- `{0}`: localized field label.
- `{1}`: minimum bound.
- `{2}`: maximum bound.

Translators may reorder parameters to sound natural, but **must not delete them, use wrong indices, or change their meanings**. Every key should include translator comments describing where it is used, tone, and placeholder meanings.

`MessageFormat` has special escaping syntax for single quotes `'` and curly braces. Messages with apostrophes or nested patterns must be tested through `MessageFormat` itself; never substitute `String.replace("{0}", ...)`.

Note that `ResourceBundle` uses a fallback mechanism: if a locale bundle lacks a key, Java may fall back to the parent/root bundle. Thus the program keeps running, but users may see an English sentence inside a Vietnamese UI. Verify translation completeness in your pipeline rather than treating fallback success as complete localization.

## 6. Complete Java 17+ Example: Fixed Codes, Varying Translations

Let us build a simple parser for a quantity field accepting range `1..100`. The example clearly demonstrates:

- Missing input: `INPUT_NUMBER_REQUIRED`.
- Non-numeric input or trailing characters after a numeric prefix: `INPUT_NUMBER_INVALID`.
- Valid number out of bounds: `INPUT_NUMBER_OUT_OF_RANGE`.
- Valid input: returns numeric value, no error.
- For the same invalid input, Vietnamese and English `Locale`s yield the **same code** with different messages.

The example uses `DecimalFormat#setParseBigDecimal(true)` to obtain a decimal object and `ParsePosition` to check full string consumption. It does not claim to strictly validate every grouping rule across all locales; add that separately if required by the product.

Create **four files** in the same directory, saving `.properties` files in UTF-8.

### File 1: `messages.properties`

```properties
# Root bundle: fallback when a locale-specific translation is absent.
# TRANSLATORS: {0} = localized field label.
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
# TRANSLATORS: {0} = field label, {1} = min, {2} = max.
error.number.outOfRange={0} must be between {1} and {2}.
```

### File 2: `messages_en.properties`

An explicit English bundle is provided so the example does not rely on the JVM default locale when resolving bundles:

```properties
field.quantity=Quantity
error.number.required={0} is required.
error.number.invalid={0} must be a valid number.
error.number.outOfRange={0} must be between {1} and {2}.
```

### File 3: `messages_vi.properties`

```properties
# TRANSLATORS: {0} = localized field label.
field.quantity=Số lượng
error.number.required=Vui lòng nhập {0}.
error.number.invalid={0} không phải số hợp lệ.
# TRANSLATORS: {0} = field label, {1} = min, {2} = max.
error.number.outOfRange={0} phải nằm trong khoảng {1} đến {2}.
```

### File 4: `LocalizedInputErrorsDemo.java`

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedInputErrorsDemo {

    private enum ErrorCode {
        INPUT_NUMBER_REQUIRED("error.number.required"),
        INPUT_NUMBER_INVALID("error.number.invalid"),
        INPUT_NUMBER_OUT_OF_RANGE("error.number.outOfRange");

        private final String messageKey;

        ErrorCode(String messageKey) {
            this.messageKey = messageKey;
        }
    }

    private record ParseResult(BigDecimal value, ErrorCode error) {}

    private static ParseResult parseQuantity(
            String raw, Locale inputLocale) {
        if (raw == null || raw.isBlank()) {
            return new ParseResult(null, ErrorCode.INPUT_NUMBER_REQUIRED);
        }

        DecimalFormat parser = (DecimalFormat)
                NumberFormat.getNumberInstance(inputLocale);
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(raw, position);

        if (!(parsed instanceof BigDecimal)
                || position.getIndex() != raw.length()) {
            return new ParseResult(null, ErrorCode.INPUT_NUMBER_INVALID);
        }

        BigDecimal quantity = (BigDecimal) parsed;
        BigDecimal min = BigDecimal.ONE;
        BigDecimal max = new BigDecimal("100");

        if (quantity.compareTo(min) < 0
                || quantity.compareTo(max) > 0) {
            return new ParseResult(
                    null, ErrorCode.INPUT_NUMBER_OUT_OF_RANGE);
        }

        return new ParseResult(quantity, null);
    }

    private static String localize(
            ErrorCode code, Locale displayLocale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", displayLocale);

        String pattern = bundle.getString(code.messageKey);
        String field = bundle.getString("field.quantity");

        return new MessageFormat(pattern, displayLocale)
                .format(new Object[] {
                    field,
                    BigDecimal.ONE,
                    new BigDecimal("100")
                });
    }

    private static void show(
            String language, Locale locale, String raw) {
        ParseResult result = parseQuantity(raw, locale);

        if (result.error() == null) {
            System.out.println(language
                    + " | OK | " + result.value().toPlainString());
        } else {
            System.out.println(language + " | "
                    + result.error().name() + " | "
                    + localize(result.error(), locale));
        }
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale en = Locale.US;

        show("VI", vi, "");
        show("EN", en, "");

        show("VI", vi, "abc");
        show("EN", en, "abc");

        show("VI", vi, "150");
        show("EN", en, "150");

        show("VI", vi, "10x");
        show("EN", en, "10x");

        show("VI", vi, "10");
        show("EN", en, "10");
    }
}
```

Compile and run with JDK 17 or later from the directory containing all four files:

```bash
javac -encoding UTF-8 LocalizedInputErrorsDemo.java
java -cp . LocalizedInputErrorsDemo
```

Stdout:

```text
VI | INPUT_NUMBER_REQUIRED | Vui lòng nhập Số lượng.
EN | INPUT_NUMBER_REQUIRED | Quantity is required.
VI | INPUT_NUMBER_INVALID | Số lượng không phải số hợp lệ.
EN | INPUT_NUMBER_INVALID | Quantity must be a valid number.
VI | INPUT_NUMBER_OUT_OF_RANGE | Số lượng phải nằm trong khoảng 1 đến 100.
EN | INPUT_NUMBER_OUT_OF_RANGE | Quantity must be between 1 and 100.
VI | INPUT_NUMBER_INVALID | Số lượng không phải số hợp lệ.
EN | INPUT_NUMBER_INVALID | Quantity must be a valid number.
VI | OK | 10
EN | OK | 10
```

### Interpreting the Results

1. `""` is missing data: code `INPUT_NUMBER_REQUIRED`. In Vietnamese, the pattern puts the action before the field; in English, the field label precedes `is required`.
2. `"abc"` cannot parse as a number: code `INPUT_NUMBER_INVALID`, regardless of the response locale.
3. `"150"` parses into `BigDecimal` but exceeds 100: code `INPUT_NUMBER_OUT_OF_RANGE`. `MessageFormat` fills the two bounds into the translated sentence; no English sentence is hardcoded inside the parser.
4. `"10x"` starts with prefix `10`, but `ParsePosition` shows the parser did not read the whole input: returns the same syntax-error code.
5. `"10"` is a valid number and returns a decimal object; formatting choices happen only when displaying to a user or serializing to another schema.

**In this example, the input locale and display locale happen to be the same.** In a real system, you can keep two separate variables if a user enters data in one chosen convention while preferring error messages in another language. The key is defining both contracts explicitly instead of assuming they are always identical.

Note that the example relies on a standard JDK provider where `NumberFormat.getNumberInstance(...)` returns `DecimalFormat`. If building a library that must support custom providers, check the runtime type or select an alternative parsing path instead of casting unconditionally. The test inputs here do not depend on locale-specific decimal separators, so error codes and integer values remain deterministic.

## 7. Stable Error Codes in APIs

When returning errors over HTTP/JSON, the payload should clearly separate the code from the display text:

```json
{
  "code": "INPUT_NUMBER_INVALID",
  "message": "Số lượng không phải số hợp lệ.",
  "field": "quantity"
}
```

The same error for locale `en-US`:

```json
{
  "code": "INPUT_NUMBER_INVALID",
  "message": "Quantity must be a valid number.",
  "field": "quantity"
}
```

Both responses share the same `code` and `field`; only `message` changes. This is an **illustrative application schema**, not a mandatory JSON format defined by Java or HTTP.

API clients should branch on the code:

```java
switch (error.code()) {
    case "INPUT_NUMBER_REQUIRED" -> showRequiredState();
    case "INPUT_NUMBER_INVALID" -> highlightInvalidNumber();
    case "INPUT_NUMBER_OUT_OF_RANGE" -> showRangeHint();
    default -> showGenericError();
}
```

This is an illustrative snippet inside a method where `error` and UI helper methods are already defined; not a standalone program. Never compare `message` to branch logic, because translations can change.

### HTTP Status Is Not an Error Code

You might choose HTTP `400 Bad Request` for malformed input or `422 Unprocessable Content` for syntactically valid data that violates business rules, depending on your API contract. No universal rule forces every system to use the same status code for all validation types. Once published, stick to your contract consistently.

A single status like 400 can cover many error codes. Conversely, one public error code may map to different statuses across protocols (HTTP, CLI, batch) if documented clearly. Avoid embedding `"400"` inside translated text for clients to parse out.

### Multiple Errors in a Single Request

If a form has multiple invalid fields, a response can contain a list:

```json
{
  "errors": [
    {
      "code": "INPUT_NUMBER_REQUIRED",
      "field": "quantity",
      "message": "Vui lòng nhập Số lượng."
    },
    {
      "code": "INPUT_DATE_INVALID",
      "field": "deliveryDate",
      "message": "Ngày giao hàng không hợp lệ."
    }
  ]
}
```

`INPUT_DATE_INVALID` in this example is a custom application error code, not a Java API constant. The `field` property should remain a stable identifier like `deliveryDate`, not be replaced by the label “Ngày giao hàng”. A localized label can be provided separately if needed by the UI.

Do not assume every error belongs to a single field: cross-field errors (such as an end date preceding a start date) can apply to multiple fields or the entire form. Your schema should support representing those cleanly.

## 8. Selecting the Locale for Error Messages

To return the right language, define a **Locale resolution policy**:

- Application has a saved user language preference: prioritize that verified setting if that is your product rule.
- HTTP request includes `Accept-Language`: can be used as a language-negotiation signal when permitted by the contract.
- No valid/supported language found: fall back to a documented product fallback locale.
- Pure machine-to-machine API: may return stable codes and default-language messages, or let the client render translations; document the choice clearly.

`Accept-Language` can contain a prioritized list of languages with `q` weights, such as `vi-VN,vi;q=0.9,en;q=0.7`. This is **not** a single language tag: do not pass the raw header directly to `new Locale.Builder().setLanguageTag(...)` or expect `Locale.forLanguageTag(...)` to parse the whole list. Java provides `Locale.LanguageRange.parse(...)` and `Locale.lookup(...)`/`Locale.filter(...)` to select a locale from a supported list.

**Support only locales for which your product has proper resources.** A syntactically valid language tag does not guarantee translations exist, and `ResourceBundle.getBundle(...)` has its own fallback chain. Choose `resolvedLocale` from the product's supported list first, then look up resources; if fallback occurs, log or monitor it to track translation coverage.

### Use the Same Locale for `MessageFormat`

When inserting numbers or dates into a message:

```java
String pattern = bundle.getString("error.amount.max");
String message = new MessageFormat(pattern, displayLocale)
        .format(new Object[] {limit});
```

This is an illustrative snippet inside a method with `bundle`, `displayLocale`, and `limit` declared. Passing `displayLocale` explicitly ensures format elements like `{0,number}` or `{0,date}` render in the reader's locale.

Do not use `String.format` with the default locale on a `MessageFormat` pattern: the two APIs have different placeholder syntax (`%s` vs `{0}`), and handle language/formatting details differently.

### Distinguish Input Locale from Output Locale

An input system may deal with:

- `inputLocale`: convention used to parse user-entered strings, e.g., German number `1.234,50`.
- `displayLocale`: language used to display messages, e.g., Vietnamese.
- `wireFormat`: schema for API data exchange, e.g., canonical decimal `1234.50`.

Never infer `inputLocale` or database number serialization from how localized messages are written. Each purpose has its own contract.

## 9. Do Not Turn Exceptions into Public Messages

A parser failure can originate from `NumberFormat.parse`, `LocalDate.parse`, `Integer.parseInt`, or business validation. Those exceptions can contain technical details, raw input strings, or implementation internals unsuitable for display.

Do not do this:

```java
catch (Exception ex) {
    return ex.getMessage(); // Not a localized UX message.
}
```

This illustrates an anti-pattern inside a method returning a string; not a complete application.

Instead, classify **expected** failures into stable codes, log technical details in a controlled manner, and translate the code into a friendly message. For example:

```java
try {
    int quantity = Integer.parseInt(raw);
    // Apply subsequent range checks.
} catch (NumberFormatException ex) {
    // Assign code INPUT_NUMBER_INVALID to the validation result.
}
```

This is an illustrative snippet assuming `raw` is declared. In locale-aware numeric input, `Integer.parseInt` is appropriate only if the input grammar is defined that way; never use it as a drop-in replacement for a UI locale parser.

**Never catch every `RuntimeException` and return `INPUT_NUMBER_INVALID`.** Configuration bugs, `NullPointerException`s in code, database failures, and user input parse errors are completely different incidents. Collapsing internal bugs into user validation errors blinds operations and tells users to “fix their input” when the system itself is broken.

Specifically, never return stack traces, internal class names, SQL statements, or sensitive data inside `message`. Use correlation IDs/tracing when needed to locate technical logs.

## 10. Never Embed Sensitive Data in Codes or Messages

Codes should remain stable and low-cardinality:

```text
INPUT_NUMBER_INVALID
ACCOUNT_LOGIN_FAILED
DATE_OUT_OF_RANGE
```

Do not generate dynamic codes:

```text
INPUT_NUMBER_INVALID_USER_12345
INVALID_VALUE_4111111111111111
USER_PASSWORD_WRONG_AT_2026_10_28
```

The examples above are **anti-patterns**, not recommended error codes. Embedding user inputs or identities into codes causes code explosion, risks exposing personal data, and breaks metrics aggregation.

Similarly, messages may use placeholders, but should echo user input only when truly needed and properly sanitized. For passwords, tokens, card numbers, or sensitive fields, it is safer **not to echo the value** in responses. Instead of “Value [sensitive data] is invalid”, use a generic message: “Invalid input value.”

Some flows also require preventing account enumeration: for instance, login authentication may return a generic code/message to avoid confirming whether an email address exists. That choice is a security requirement, not a wording detail.

## 11. Managing the Lifecycle of Error Codes

“Stable error codes” does not mean you can never add or evolve codes. It means **each published code has a clear meaning and is never arbitrarily repurposed**.

### Practical Rules

1. Pick a naming convention such as `INPUT_*`, `AUTH_*`, `ORDER_*` or `validation.number.invalid` and use it consistently.
2. Document clearly when each code appears and what clients should do.
3. Never put translated text, environment names, or request data into codes.
4. When revising display phrasing without changing the error's meaning, **keep the code** and usually keep the message key.
5. When semantics change significantly, consider **adding a new code** and migrating clients under a compatibility plan.
6. Avoid renaming a public code just to match a refactored Java class name; codes are part of the API contract, not internal variable names.
7. Maintain a safe fallback for clients receiving an unrecognized code (typically showing a generic error and logging), rather than crashing or assuming client enums contain every possible value.

Examples:

- `INPUT_NUMBER_INVALID` stays unchanged when a translator changes “invalid” to “please enter a valid number”.
- If a product splits `INPUT_NUMBER_INVALID` into “contains letters” and “invalid grouping,” specialized codes can be introduced while accounting for older clients. Keeping a single general code is fine if clients do not need the distinction; do not multiply codes unnecessarily.
- A code like `PAYMENT_REJECTED` must not be reused when the system loses network connectivity to the payment gateway; those two conditions require different handling.

The relationship between **error code** and **message key** is often one-to-one for a primary sentence, though not strictly required. One code can be rendered with different patterns across UI channels (toast, email, form) without changing the business contract. Keep that choice inside the presentation layer rather than letting clients infer codes from text.

## 12. Fallback Behavior and Translation Management

Creating a root bundle like `messages.properties` gives `ResourceBundle` fallback content. However, root fallback is a technical safeguard, not proof that a language is fully translated.

Common risks:

- `messages_vi.properties` lacks key `error.number.outOfRange`; Java pulls the English string from `messages.properties`.
- A translation adds or drops placeholders; `MessageFormat` can print literal `{2}` if an argument is missing, or omit information.
- A translation shifts the meaning from “invalid” to “missing,” steering the user toward the wrong corrective action.
- Some locales use apostrophes routinely in normal prose; `MessageFormat` requires specific escaping rules for single quotes.

Quality checks should include:

- Comparing keys **defined directly in each individual file** against a reference key set, rather than calling `ResourceBundle.containsKey` where fallback can hide missing translations.
- Validating every locale's pattern via `new MessageFormat(pattern, locale)`.
- Checking placeholder indices and meanings against the contract, without requiring identical ordering to the source language.
- Reviewing strings in the real UI: excessive length causing truncation, missing context, mismatched tone, or untranslated field names.
- Defining a policy for missing bundles or keys. For internal resource configuration bugs, never pretend the user entered invalid data; use a controlled fallback message and alert on the configuration error.

In Java 17+, `.properties` files read by `PropertyResourceBundle` via byte streams default to UTF-8. Save translations in UTF-8, test Vietnamese diacritics, and enforce encoding in the build pipeline. Do not confuse `java.util.Properties.load(InputStream)` behavior with `PropertyResourceBundle`'s encoding contract.

## 13. Testing Stable Codes and Multilingual Messages

A test suite for parsers/validators should separate two groups.

### A. Error Classification Tests (Language-Independent)

| Input | Expected Result | Meaning |
| --- | --- | --- |
| `null` or `""` | `INPUT_NUMBER_REQUIRED` | Missing value |
| `"abc"` | `INPUT_NUMBER_INVALID` | Invalid numeric syntax |
| `"10x"` | `INPUT_NUMBER_INVALID` | Parser read only a prefix |
| `"150"` with max 100 | `INPUT_NUMBER_OUT_OF_RANGE` | Valid type, out of range |
| `"10"` | Success, no error code | Valid value |

Re-run this suite across supported input locales. When numeric syntax differs between two locales, supply corresponding valid inputs; do not demand that the same string with separators mean the same value in every locale.

### B. Message Localization Tests

For the same `INPUT_NUMBER_INVALID` outcome:

- With `vi-VN`, the rendered message is in Vietnamese with a localized field label.
- With `en-US`, the rendered message is in English.
- **The code remains strictly `INPUT_NUMBER_INVALID`**, and the field remains `quantity`.
- If translation wording changes, business-logic tests should not break. I18n tests can verify patterns, keys, and placeholders independently or validate rendered text in integration tests per product policy.

Never write business-logic tests using `assertEquals("Số lượng không phải số hợp lệ.", response.getMessage())` to verify error classification. That couples validation to copywriting; editing resource text breaks business tests even when the code is right. Dedicated localization tests can verify expected translations, but they should have a clear scope.

### C. Testing Fallbacks and Unknown Codes

If a service returns a new code that an older client does not recognize, the client should degrade safely with a default fallback. If a message key is missing for a locale, the program should not crash the entire validation flow. At the same time, missing translations should be logged for pipeline remediation.

### D. Testing Sensitive Data Handling

Test long inputs, special characters, script-like text, and dummy tokens. Ensure sensitive values are not echoed directly in messages unnecessarily and never inflate code/metric cardinality. Verify that any values rendered into HTML are escaped by the rendering layer; a correct translation does not automatically make output safe for every UI framework.

## 14. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using an English/Vietnamese sentence as `errorCode` | Code changes with translations and copy edits | Use stable machine-readable identifiers |
| Using `message.equals(...)` to drive UI behavior | Language switches break logic branches | Check code and field identifier |
| Embedding user input in error code names | Data leaks and uncontrolled code cardinality | Choose codes from a fixed set of identifiers |
| Sending raw `exception.getMessage()` to users | Can leak internals and is unlocalized | Map expected errors to codes and resource messages |
| Collapsing every exception into `INPUT_INVALID` | Hides bugs, outages, and config errors | Distinguish validation failures from internal errors |
| Naming keys solely after original source wording | Copy edits make IDs misleading | Name keys after relatively stable semantics |
| Omitting placeholder comments for translators | Wrong parameters, bounds, or broken syntax | Document `{0}`, `{1}` meanings clearly |
| Using JVM default `Locale` for all requests | Users receive messages in the wrong language | Determine and pass display locale explicitly |
| Parsing raw `Accept-Language` as a single tag | Header holds a weighted list with `q` values | Negotiate against supported locales |
| Checking only that `getString(key)` throws no error | Fallback can mask missing translations | Diff key sets across each locale file |
| Using display locale to parse standard API numbers | Same payload can parse to different values | Parse machine formats by schema, UI input by input locale |
| Treating `NumberFormat.parse(String)` as a strict validator | Can read only prefix `10` of `10x` | Check `ParsePosition` and grammar |
| Letting clients parse messages to extract bounds | Translations and number formatting vary | Return structured metadata if clients need min/max |
| Returning HTTP 400 with no error code | Clients struggle to tell error types apart | Return stable error codes per contract |
| Treating message keys as permanent public codes | Reorganizing bundles breaks clients | Map public codes to internal keys |
| Changing a code because of a punctuation edit | Unnecessary breaking change | Keep the code when meaning has not changed |

## 15. Hands-On Exercises

**Exercise 1 — contract design.** A `deliveryDate` field has three errors: “empty,” “invalid date syntax,” and “date before today.” Propose three stable codes, three message keys, and corresponding `vi-VN`/`en-US` sample messages. Explain why codes should not contain Vietnamese diacritics or full translated sentences.

**Exercise 2 — same error, two languages.** Using `INPUT_NUMBER_INVALID` and field `quantity`, create two properties files producing Vietnamese and English sentences. Use `ResourceBundle`/`MessageFormat` to obtain the message while keeping the code unchanged in the response.

**Exercise 3 — prefix-reading parser.** A user enters `"10kg"` into a quantity-only field. Why can `NumberFormat.parse("10kg")` return a number? Add `ParsePosition` so trailing data produces `INPUT_NUMBER_INVALID`.

**Exercise 4 — fallback.** The Vietnamese bundle is missing `error.number.outOfRange`, while the root bundle defines it. What happens when calling `getString`? Why does `ResourceBundle` succeeding not prove translations are complete? How would you detect missing translations?

**Exercise 5 — API client.** A client receives JSON with code `INPUT_NUMBER_OUT_OF_RANGE` and a German message. How can the client still determine which field to highlight and how to respond without parsing the German sentence?

**Exercise 6 — security.** A parse exception contains raw input holding sensitive data. Write an appropriate messaging/logging policy and explain why input should not be embedded in error codes or default messages.

**Exercise 7 — evolution across versions.** Translators revise a sentence from “invalid” to “please enter a valid value”. Should you change the error code? If a new business rule splits two distinct error conditions that clients need to handle separately, how would you add codes without breaking older clients?

## 16. Key Takeaways

**Error messages are for humans; error codes are contracts for machines.** Parse and validate input to produce a stable error category like `INPUT_NUMBER_INVALID`, then map that category to a message key and render the display sentence using `ResourceBundle` + `MessageFormat` for the chosen `Locale`.

An effective architecture separates the layers:

```text
Parse/validate -> stable error code
Stable code    -> message key + parameters
Message key    -> ResourceBundle(displayLocale)
Pattern        -> MessageFormat(displayLocale)
Response       -> stable code + localized message + stable metadata
```

When the language changes, the wording changes while the code stays fixed. When business rules change, evaluate whether a new code is needed instead of repurposing an old code with a different meaning. And when parsing locale-sensitive numbers or dates, never skip checking remainders, grammar, value ranges, or translation fallbacks.

**Core rule:** *Machines rely on codes; users read messages. Both must reflect the same error, without depending on each other linguistically.*

### API Reference

- [`ResourceBundle` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`MessageFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)
- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
