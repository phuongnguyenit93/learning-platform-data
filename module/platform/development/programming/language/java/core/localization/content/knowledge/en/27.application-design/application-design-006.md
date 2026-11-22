# Keeping Error Codes, Technical Field Names, and Machine Formats Stable in Java Localization

## 1. Fundamental Rule

In a multilingual application, **what humans read is localized; what machines parse must follow a stable contract**. When the UI switches from `vi-VN` to `en-US`, labels and messages may change, but error codes, JSON field names, data types, status names, and wire formats must not change along with them.

For example, when a user enters a non-positive amount:

~~~text
Technical data (both languages):
  code  = AMOUNT_NOT_POSITIVE
  field = amount

vi-VN: Số tiền phải lớn hơn 0
en-US: Amount must be greater than zero
~~~

If the API changes `amount` to `soTien` when Vietnamese is selected, clients and validators relying on the `amount` schema will fail. Likewise, errors cannot be detected by comparing verbatim English sentences because translated copy is allowed to evolve while the error's meaning remains unchanged.

Separate at least three responsibilities: **domain** determines business values and rules; **machine contract** defines codes/fields/types/formats; **presentation** turns them into locale-appropriate wording, labels, and formatting.

## 2. Data Classification Table

| Element | Example | Stable or localized? |
| --- | --- | --- |
| API error code | `AMOUNT_NOT_POSITIVE` | Stable |
| JSON property name | `amount`, `createdAt` | Stable |
| Failing field path | `items[0].quantity` | Stable |
| ResourceBundle key | `error.amount.notPositive` | Stable |
| Public status/enum | `PENDING`, `APPROVED` | Stable |
| HTTP status, correlation ID | `422`, `req-1042` | Stable |
| JSON boolean | `true`, `false` | Machine syntax |
| JSON number | `1234.50` | Machine syntax |
| Exchange timestamp | `2024-10-28T09:30:00Z` | Formatted per contract |
| Currency code | `VND`, `USD` | Business semantics |
| Field label | "Số tiền" / "Amount" | Localized |
| Error message | "Số tiền phải lớn hơn 0" | Localized |
| On-screen date/money | `28/10/2024`, `1.234,50` | Localized where appropriate |

Distinguish **labels** from **identifiers**. `customerName` is a JSON property; "Tên khách hàng" / "Customer name" is a UI label. The two serve different purposes—they are not two translations of the same machine key.

## 3. Error Codes Differ from Messages

Two responses for the exact same error might be:

~~~json
{
  "code": "AMOUNT_NOT_POSITIVE",
  "field": "amount",
  "message": "Số tiền phải lớn hơn 0"
}
~~~

~~~json
{
  "code": "AMOUNT_NOT_POSITIVE",
  "field": "amount",
  "message": "Amount must be greater than zero"
}
~~~

The property names `code`, `field`, and `message` are identical. The values of `code` and `field` are identical. **Only** the `message` value changes language.

A Java 17 type declaration:

~~~java
public record ApiError(String code, String field, String message) {}
~~~

This is a valid top-level `public record` if placed in its own `ApiError.java` file. In the standalone program in Section 9, the record is declared nested inside a class.

### 3.1. Why Not Compare by Error Sentence?

A client can break if it does:

~~~java
if ("Amount must be greater than zero".equals(error.message())) {
    System.out.println("Invalid amount");
}
~~~

This illustrates code inside a method, where `error` is an object with a `message()` accessor. Simply editing the translation or adding a language breaks this branch.

Replace with:

~~~java
if ("AMOUNT_NOT_POSITIVE".equals(error.code())) {
    System.out.println("Invalid amount");
}
~~~

`AMOUNT_NOT_POSITIVE` is a **stable business-meaningful identifier**. `message` is human-readable data that can contain varying punctuation, arguments, explanations, or languages.

### 3.2. Designing an Error Code Catalog

An error code catalog should document: code, business description, scope, HTTP status or domain status, technical field/arguments, and translation key. Prefer ASCII codes and a consistent convention such as `UPPER_SNAKE_CASE`. Never embed personal data or stack traces inside error codes.

When a translated sentence is improved, **there is no need to change the code**. When the underlying business condition changes significantly, do not reuse an old code for an incompatible condition. Have client handling for unknown codes and versioning/deprecation policies for public codes.

HTTP status codes and application error codes complement one another: the HTTP status describes the overall request outcome, while the error code states the specific cause. Pick 400/422 per your API contract, not per locale.

## 4. Field Names, `ResourceBundle` Keys, and Field Paths

An order might be transmitted as:

~~~json
{
  "amount": 1250.50,
  "currencyCode": "VND",
  "createdAt": "2024-10-28T09:30:00Z",
  "status": "PENDING"
}
~~~

A Vietnamese screen displays "Số tiền", "Loại tiền", "Thời gian tạo", "Trạng thái". An English screen displays "Amount", "Currency", "Created at", "Status". Yet the JSON property names remain `amount`, `currencyCode`, `createdAt`, and `status`.

When using `ResourceBundle`, keep **the exact same key names** across files:

~~~properties
error.amount.notPositive=Amount must be greater than zero
label.amount=Amount
label.createdAt=Created at
~~~

Vietnamese version:

~~~properties
error.amount.notPositive=Số tiền phải lớn hơn 0
label.amount=Số tiền
label.createdAt=Thời gian tạo
~~~

This illustrates the contents of two `.properties` files for different locales. `error.amount.notPositive` is a technical key; **only the value to the right of the equals sign is translated**. An error code can map to a separate translation key; they do not have to share the exact same name.

### 4.1. Field Paths in Validation

Example error for the first line item:

~~~json
{
  "code": "QUANTITY_NOT_POSITIVE",
  "field": "items[0].quantity",
  "message": "Số lượng phải lớn hơn 0"
}
~~~

`items[0].quantity` is a technical field path; never translate it to `matHang[0].soLuong` by locale. The UI uses this path to highlight the input control, then looks up the label "Số lượng" or "Quantity" separately. If the API uses JSON Pointer such as `/items/0/quantity`, document the syntax, escaping, and field mapping clearly, and never mix two path formats.

Likewise, database column names like `customer_id`, message queue event names like `ORDER_CREATED`, GraphQL properties, public enum values, and metric keys must not be translated across protocols.

## 5. Numbers, Dates, and Machine Data Types

### 5.1. Machine Decimals Are Not Display Numbers

~~~java
BigDecimal amount = new BigDecimal("1234.50");
String decimal = amount.toPlainString();
~~~

This illustrates Java code inside a method requiring `import java.math.BigDecimal;`. `decimal` is `"1234.50"` and does not vary with `Locale`. When a contract specifies a **decimal string**, this is an appropriate representation.

If the contract specifies a **JSON number**, use a JSON serializer that writes a number token:

~~~json
{"amount":1234.50}
~~~

Never serialize machine numbers as UI-formatted strings:

~~~json
{"amount":"1.234,50"}
~~~

`"1.234,50"` is a JSON **string**, not a JSON number. Switching to a string is a schema change, not merely a different decimal mark. When a protocol intentionally uses a decimal string to preserve precision, emit `"1234.50"` and document that type in the schema.

With `String.format`-style formatting, pass `Locale.ROOT` when machine output must follow locale-neutral formatting rules independent of the default locale:

~~~java
String machineText = String.format(Locale.ROOT, "%.2f", 1234.5);
~~~

This snippet requires `import java.util.Locale;` and yields `"1234.50"`. However, never use `double` for monetary calculations requiring exactness. `BigDecimal` paired with a serializer or a decimal-string contract is far more appropriate.

**Caution:** JavaScript clients can lose precision on some JSON numbers. For large or exact monetary amounts, choosing decimal strings, integer minor units, or exact decimal support must be a system-wide decision.

### 5.2. Instants and Calendar Dates Differ

~~~java
Instant createdAt = Instant.parse("2024-10-28T09:30:00Z");
String timestamp = DateTimeFormatter.ISO_INSTANT.format(createdAt);
~~~

This snippet requires importing `Instant` and `DateTimeFormatter`. The result `2024-10-28T09:30:00Z` is a UTC instant.

The UI may display `28/10/2024 16:30` in Vietnam time or `10/28/2024 9:30 AM` in UTC. Yet an absolute instant **does not change on its own** when the UI locale changes.

If the underlying data is a birth date or expiration calendar date, use `LocalDate` and a machine format such as `2024-10-28`; never turn a calendar date into a 00:00 UTC instant without an explicit zone rule. If an API uses offset datetimes instead of UTC, the contract must specify ISO 8601/RFC 3339 formatting, precision, and validation rules.

### 5.3. Booleans, Currency, Statuses, and CSV

JSON booleans are always `true` or `false`, and JSON null uses `null`. Enum values like `PENDING` are machine identifiers; labels like "Đang chờ" or "Pending" are rendered solely in the UI.

Store currency codes like `VND` and `USD` alongside the amount. Changing locale never changes the currency unit or performs FX conversion. `NumberFormat.getCurrencyInstance(locale)` only formats presentation; it does not turn 100 USD into 100 VND.

CSV has many dialects. When a machine CSV uses commas as column delimiters, specify delimiter, quoting, decimal mark, encoding, and newline rules. Do not write `1.234,50` expecting another system to guess it is a single number without a schema; the comma may be parsed as a column separator.

## 6. Separating Request Locale from Business Decisions

An API flow should look like:

~~~text
HTTP request + JSON payload
          |
          v
Parse against fixed schema
          |
          v
Domain validation -> errorCode, field, typed arguments
          |
          v
Select presentation Locale from supported languages
          |
          v
ResourceBundle / message lookup
          |
          v
Serialize response with fixed JSON keys and data types
~~~

`Accept-Language` is a language preference, not verified information about location, nationality, tax, currency, or permissions. If a user picks an unsupported language, the application applies a deliberate fallback (such as English) **without changing error codes or schemas**.

Never call `Locale.setDefault` per web request: the default locale is JVM-wide and can leak languages between concurrent requests. Pass `Locale` explicitly into presentation and formatting layers.

### 6.1. Parameterized Error Messages

Errors can be returned alongside machine parameters:

~~~json
{
  "code": "AMOUNT_BELOW_MINIMUM",
  "field": "amount",
  "arguments": {
    "minimum": 100.00,
    "currencyCode": "VND"
  },
  "message": "Số tiền tối thiểu là 100 VND"
}
~~~

`arguments.minimum` stays numeric; `currencyCode` keeps the currency code. Only `message` changes under another locale. Never format `minimum` as `"100,00"` pretending to be a JSON number. When using `MessageFormat`, placeholder/argument indices across translations must adhere to a stable contract even when word order varies.

## 7. Domain Models and Wire DTOs Are Not UI Models

A domain layer may store:

~~~java
record Money(BigDecimal amount, String currencyCode) {}
record ApiError(String code, String field, String message) {}
~~~

These are illustrative record declarations inside a class or compilation unit without public top-level declarations, requiring `import java.math.BigDecimal;`. Production code must validate nulls, currency codes, and business constraints.

**Domain** holds explicit amount and currency. **Validation** returns codes and field paths. **Presentation** looks up translations. **Serialization** writes JSON according to schema. When one layer changes, the others can stay intact.

Do not store translated error sentences as the source of truth for an error, do not store `"1.234,50"` as a domain monetary amount, and do not use field labels as column/JSON keys. If an audit log must capture the displayed message too, store it alongside the error code and context without using the message as the error's primary identity.

### 7.1. Use a Serializer Instead of Manual JSON Concatenation

The JSON snippets here illustrate contracts. A real application should use a JSON serializer handling quoting, escaping, types, and field mapping. Never concatenate messages or user-provided strings into JSON unescaped. Running the demo in Section 9 **does not emit JSON**; instead it prints properties to verify localization principles.

## 8. Compatibility and Release Lifecycle

### 8.1. Translation Edits Are Normally Non-Breaking Changes

You can refine message explanations, add a locale, or tweak screen labels without changing codes, fields, or schemas. Well-behaved clients must never depend on translated sentences to drive logic.

### 8.2. Changes That Require Schema Migration

- Renaming `createdAt` to `created_at` after the field is public.
- Replacing `AMOUNT_NOT_POSITIVE` with another code without a compatibility plan.
- Changing `amount`'s type from number to string.
- Switching an ISO instant to a localized date string without an offset.
- Returning a translated label like `Đang chờ` instead of enum value `PENDING`.
- Changing technical field-path syntax that clients rely on.

These changes require documentation, API versioning/deprecation, controlled rollout, and regression tests. Adding new error codes also requires clients to handle unknown codes gracefully; never assume every client upgrades simultaneously.

### 8.3. Ownership of the Error Catalog

Maintain a catalog of error codes documenting descriptions, trigger rules, HTTP status, fields/arguments, translation keys, remediation guidance, and deprecation policies. Never repurpose an existing code for a new meaning simply because the message sounds similar.

## 9. Complete Java 17 Program

This standalone program uses a `Map` as a compact translation source. In production, `ResourceBundle` or a framework message source is usually more appropriate. The example prints ASCII stdout and verifies Vietnamese text using Unicode escapes so it does not depend on console font support.

**File `StableContractDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Map;

public class StableContractDemo {
    private static final String ERROR_CODE = "AMOUNT_NOT_POSITIVE";
    private static final String FIELD = "amount";

    record ApiError(String code, String field, String message) {}
    record Transfer(BigDecimal amount, Instant createdAt) {}

    static ApiError validate(Transfer transfer, Locale locale) {
        if (transfer.amount().signum() > 0) {
            throw new IllegalArgumentException(
                    "This demo expects a nonpositive amount");
        }
        Map<String, String> templates = Map.of(
                "vi", "S\u1ED1 ti\u1EC1n ph\u1EA3i l\u1EDBn h\u01A1n 0",
                "en", "Amount must be greater than zero");
        String message = templates.getOrDefault(
                locale.getLanguage(), templates.get("en"));
        return new ApiError(ERROR_CODE, FIELD, message);
    }

    public static void main(String[] args) {
        Transfer transfer = new Transfer(new BigDecimal("0.00"),
                Instant.parse("2024-10-28T09:30:00Z"));
        ApiError vi = validate(
                transfer, Locale.forLanguageTag("vi-VN"));
        ApiError en = validate(transfer, Locale.US);

        System.out.println("vi: code=" + vi.code()
                + ", field=" + vi.field());
        System.out.println("en: code=" + en.code()
                + ", field=" + en.field());
        System.out.println("same technical identity=" +
                (vi.code().equals(en.code())
                && vi.field().equals(en.field())));
        System.out.println("localized messages differ=" +
                !vi.message().equals(en.message()));
        System.out.println("vi message verified=" +
                vi.message().equals(
                        "S\u1ED1 ti\u1EC1n ph\u1EA3i l\u1EDBn h\u01A1n 0"));
        System.out.println("machine amount=" +
                transfer.amount().toPlainString());
        System.out.println("machine time=" +
                DateTimeFormatter.ISO_INSTANT.format(
                        transfer.createdAt()));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 StableContractDemo.java
java StableContractDemo
~~~

**Verified stdout:**

~~~text
vi: code=AMOUNT_NOT_POSITIVE, field=amount
en: code=AMOUNT_NOT_POSITIVE, field=amount
same technical identity=true
localized messages differ=true
vi message verified=true
machine amount=0.00
machine time=2024-10-28T09:30:00Z
~~~

**Explanation:** `code` and `field` remain identical across both locales, while messages differ. `vi message verified=true` confirms the Vietnamese Unicode content without requiring Vietnamese rendering on the console. `BigDecimal.toPlainString` prints `0.00` unaffected by locale; `ISO_INSTANT` prints `2024-10-28T09:30:00Z`. This example demonstrates validation for a **non-positive amount**—it is not a JSON library or a complete monetary processing solution.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Translating error codes by locale | Clients cannot recognize errors | Keep codes stable |
| Switching on error `message` | Copy edits break logic | Branch on `code` |
| Translating JSON keys | Incompatible with serializers/client schemas | Keep property names fixed |
| Returning UI labels as technical fields | Clients cannot map fields | Return standard field paths |
| Using `NumberFormat` for JSON numbers | Locale-specific grouping/decimal marks | Use machine number serializer |
| Sending UI dates as machine datetimes | Ambiguous day/month, zone, and offset | Use ISO per contract |
| Changing currency when language changes | Alters monetary meaning | Keep currency in domain |
| Calling `Locale.setDefault` per request | Language leaks between requests | Pass `Locale` explicitly |
| Comparing errors by message text | Breaks multilingual support | Use error code + typed args |
| Using default locale for logs/schemas | Inconsistent results across servers | Use locale-neutral contracts |
| No fallback for unknown new codes | Older clients crash | Add unknown-code handler |
| Concatenating JSON strings manually | Escaping/injection/type bugs | Use a JSON serializer |
| Missing Unicode/locale tests | Broken diacritics, fonts, charsets | Test `vi`/`en`/RTL/emoji |
| Changing schemas under the guise of translation | Silent breaking change | Version and migrate properly |

## 11. Tests You Should Write

A strong test suite runs the same input across multiple locales (`vi-VN`, `en-US`, `de-DE`, `tr-TR`, and an unsupported locale) and verifies:

1. `code`, `field`, and HTTP status remain unchanged.
2. JSON property names and types remain unchanged.
3. Amount and currency keep consistent values and domain semantics.
4. ISO timestamps carry the exact same instant and contract precision.
5. Enum values, IDs, and log fields remain unchanged.
6. Translations differ properly or fall back intentionally.
7. `BigDecimal` serializes independently of `Locale.getDefault()`.
8. Schema tests catch `createdAt` accidentally turning into `thoiGianTao`.
9. Unknown error codes are handled safely without crashing.
10. Nested field path `items[0].quantity` does not change with UI language.
11. Unicode messages encode/decode in UTF-8 properly; JSON escaping is safe.
12. Concurrent requests with different locales never contaminate one another's languages.

Beyond testing Java objects, also test **actual serialized HTTP responses**, because a serializer or framework may be configured differently from domain code.

## 12. Practice Exercises

1. Run the demo with `fr-FR`, receiving the English fallback message while keeping technical identity intact.
2. Add `CURRENCY_UNSUPPORTED` with field `currencyCode`; create `vi`/`en` labels and messages without translating the field name.
3. Create `Order(BigDecimal amount, String currencyCode, Instant createdAt)`, defining a fixed JSON schema and two UI presentations.
4. Compare `BigDecimal("1234.50").toPlainString()` with `NumberFormat.getNumberInstance(Locale.GERMANY)`; explain the difference.
5. Write a test varying `Accept-Language` while verifying `code` and `field` stay constant.
6. Design a multi-error response with an `errors` array where each element has fixed-type `code`/`field`/`message`.
7. Create an error message carrying a numeric `minimum` and currency code; format per locale only in the presentation layer.
8. Set default locale `tr-TR` in an isolated test environment; verify machine decimals and timestamps.
9. Write a client fallback for unknown error codes that still displays a safe message.
10. Compare editing a translated sentence with renaming a JSON key: which change requires an API version bump?

## 13. Summary

**Localization must never alter the meaning or shape of machine data.** Error codes, field names, field paths, JSON schemas, enum values, timestamps, and decimal representations must follow a stable contract. `Locale` is used to pick `ResourceBundle`s, message languages, labels, and UI formatting. For wire numbers and dates, use `BigDecimal`, `Instant`, and appropriate formatters/serializers; `Locale.ROOT` is helpful for certain technical formatting cases, though it does not replace explicit schemas or precision rules.

Separating domain, API contract, and presentation lets applications add languages, refine messages, and improve UIs without breaking clients, reports, databases, or business rules.

**References:**

- Java SE 17, `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `Instant`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java SE 17, `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 17, `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- JSON syntax: https://www.rfc-editor.org/rfc/rfc8259
