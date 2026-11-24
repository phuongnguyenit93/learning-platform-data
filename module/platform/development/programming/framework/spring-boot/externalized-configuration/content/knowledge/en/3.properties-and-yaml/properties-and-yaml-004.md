# Strings, Numbers, Booleans, and Timestamps That Require Quotes in YAML

When configuring Spring Boot with `application.yml`, quotes are not merely decorative. YAML has rules for parsing **scalars** (single values): `10`, `true`, `null`, a date, or a string containing special characters can be interpreted differently from what the author intended. This issue is especially common with codes containing leading zeros, version names, text-based status flags, URLs, content containing `#`, and date-time strings.

This lesson explains how to choose between **unquoted**, **single-quoted**, and **double-quoted** values, while distinguishing two steps: **the YAML parser reading the value** and **the Spring Boot Binder converting the value into a Java type**. Understanding both steps keeps configuration unambiguous, consistent across environments, and easy to troubleshoot.

## 1. Scalars: single values in YAML

Example:

~~~yaml
app:
  title: Inventory Service
  version: "1.10"
  max-connections: 20
  enabled: true
  release-date: "2026-11-12"
~~~

The lines above use different representations:

| Value | Intent | Style |
| --- | --- | --- |
| `Inventory Service` | Display name | Unquoted string, valid when no conflicting characters appear |
| `"1.10"` | Version whose exact digits must be preserved | Quoted string |
| `20` | Connection count | Unquoted number |
| `true` | Logical flag | Unquoted boolean |
| `"2026-11-12"` | ISO date kept as string before binding | Quoted string |

Three common string styles:

~~~yaml
text:
  plain: hello world
  single: 'hello world'
  double: "hello world"
~~~

All three can represent the same text `hello world`. However, when a scalar looks like a number, boolean, null, or timestamp, or contains YAML syntax characters, quoting can determine whether the value is read correctly.

**YAML 1.1, YAML 1.2, and different parsers/schemas differ in automatic type-detection rules.** For example, words like `yes`, `no`, `on`, and `off` may be treated as booleans in some systems but as strings in others. Therefore, configuration should state its intent explicitly instead of relying on parser guesswork.

## 2. Practical rule: quote when text must be preserved literally

| Desired data | Recommended example | Reason |
| --- | --- | --- |
| Regular name | `name: "Billing API"` or `name: Billing API` | Quotes optional if no special characters appear |
| Code with leading zeros | `region-code: "0012"` | Preserves length and leading zeros |
| Version | `version: "1.20"` | Prevents becoming decimal number 1.2 |
| Number for calculation | `retry-count: 5` | Numeric representation |
| Logical flag | `enabled: true` | Unambiguous boolean |
| Word looking like a flag | `status-label: "off"` | Keeps it as a string |
| Calendar date | `start-date: "2026-11-12"` | Keeps consistent ISO representation |
| Timestamp with offset | `starts-at: "2026-11-12T09:30:00Z"` | Avoids unwanted timestamp inference |
| Duration | `timeout: 5s` or `timeout: "5s"` | Binder can convert to `Duration` |
| Empty string | `description: ""` | Distinguishes from null |
| Literal word "null" | `literal: "null"` | Keeps the word, not actual null |
| String with `: ` or ` #` | `title: "Status: Ready #1"` | Avoids colliding with YAML syntax |

There is no rule that "every YAML value must be quoted". Conversely, quoting an actual number or boolean does not automatically turn a Java field into `String`. You must choose both **YAML syntax** and **Java target type**.

## 3. Digit-only strings: codes are not numbers

Consider postal codes, branch codes, or phone numbers:

~~~yaml
customer:
  postal-code: "00120"
  account-code: "000045"
  telephone: "+840912345678"
  branch-code: "007"
~~~

These values may contain only digits, yet they are not used for addition, subtraction, multiplication, or division. Users usually need their exact spelling preserved, including leading zeros, `+` signs, or separators. Represent them as strings and bind to `String`.

Risky example:

~~~yaml
customer:
  postal-code: 00120
~~~

Depending on the parser and schema, a number with leading zeros can be interpreted specially or lose its original representation. Quoting does not break a code; it preserves the raw text before Spring converts it.

### Versions, release codes, display ratios

~~~yaml
build:
  version: "1.10"
  api-version: "2.0"
  release-label: "2026.11"
  report-ratio-label: "1.00"
~~~

`1.10` and `1.1` mean different things as version labels, even though they are equal as decimal numbers. If written unquoted, numeric typing can alter the formatting. Likewise, ratios displayed verbatim should be strings, whereas ratios used in calculations need an appropriate numeric type in Java.

### Numbers with special notation

Scalars like `1e3`, `0xFF`, `.inf`, `.nan`, or numbers with underscores can be interpreted differently depending on parser/schema. If the value is a **code** or **label**, quote it:

~~~yaml
identifiers:
  scientific-looking: "1e3"
  hex-looking: "0xFF"
  long-code: "00000000000000123456"
~~~

If you truly need numbers for computation, check the formats supported by both the parser and Java type rather than using unpredictable notation in configuration.

## 4. Booleans: use true/false for flags, quotes for words

A boolean describes a two-state decision:

~~~yaml
features:
  enabled: true
  collect-metrics: false
~~~

This is the clearest way when intending to bind to `boolean` or `Boolean`. Avoid using `on`/`off` or `yes`/`no` instead of `true`/`false` just because they look similar in meaning: YAML readers can infer them differently.

When these words are **display labels**, **text-based enums**, or **codes**, quote them:

~~~yaml
workflow:
  mode: "off"
  answer-label: "yes"
  alternate-label: "no"
  visible-value: "false"
  channel: "ON"
~~~

Compare:

~~~yaml
demo:
  a: false
  b: "false"
~~~

- `a` is written with boolean intent.
- `b` is written with the intent of the five-letter string `false`.
- If Spring binds `b` to a Java `boolean`, the Binder can still convert the string `"false"` into boolean `false`.
- If you want to preserve the literal text `false`, the Java field should be `String`.

Therefore, **quoting is a YAML rule; the Java data type is an independent decision at the binding step**.

If an application has three states `"manual"`, `"auto"`, and `"off"`, an enum or domain-specific type is usually better than combining multiple booleans.

## 5. Null and empty strings

The following forms have different meanings at the YAML layer:

~~~yaml
message:
  empty: ""
  missing:
  explicit-null: null
  tilde-null: ~
  literal-null: "null"
~~~

`empty` is an empty string; `missing`, `explicit-null`, and `tilde-null` are written with null intent; `literal-null` is the string containing the word "null".

In Spring Boot, how configuration is converted into a `PropertySource`, source precedence, placeholders, and the target type can all affect how null or absent values behave. Do not assume null, omitted, and empty-string entries always produce the same result. If you need to distinguish them for a specific setting, define the requirement explicitly and handle it in Java.

A real-world mistake is writing:

~~~yaml
headers:
  auth: null
~~~

and assuming the application will send a header with the literal text `null`. If you truly want that string, write `"null"`; however, reconsider why an application would ever need such a value.

## 6. Dates, times, and timestamps: quote them

Dates and timestamps are easy to misread because they look like strings, yet YAML parsers in some environments can recognize them as timestamp/date objects:

~~~yaml
release:
  date: "2026-11-12"
  announced-at: "2026-11-12T09:30:00Z"
  local-time: "09:30:00"
  timezone: "Asia/Ho_Chi_Minh"
  month-code: "2026-11"
~~~

Use quotes to preserve the input representation. Spring Boot can then convert:

- `"2026-11-12"` to `LocalDate` if the target field declares a date type and conversion is valid.
- `"2026-11-12T09:30:00Z"` to `Instant` or another appropriate instant type if a suitable converter exists.
- `"09:30:00"` to `LocalTime` if the field needs a time of day.
- `"Asia/Ho_Chi_Minh"` to an appropriate timezone/zone ID or keep it as a string depending on design.

**Calendar dates and instants are not the same.** A date like `2026-11-12` does not specify 00:00 in any particular timezone; `2026-11-12T09:30:00Z` identifies a specific instant with UTC offset. When handling local schedules, specify the timezone explicitly; do not implicitly rely on the server's timezone.

Quotes do not fix an invalid format. For example:

~~~yaml
report:
  report-date: "12/11/2026"
~~~

A `LocalDate` field normally expects ISO `yyyy-MM-dd`. If a project needs `dd/MM/yyyy`, an explicit conversion/formatter must be configured. Simply adding quotes will not make the Binder understand arbitrary formats.

### Durations vs. timestamps

A duration describes a span of time:

~~~yaml
network:
  connect-timeout: 2s
  read-timeout: "750ms"
  retry-delay: 1m
~~~

`2s`, `750ms`, and `1m` are unit-qualified duration representations. They are not integers or calendar timestamps. When binding to `java.time.Duration`, Spring Boot supports converting these unit notations appropriately. Whether quotes are used does not decide the final Java type.

Unitless durations such as `timeout: 30` force readers to guess whether it means 30 ms, 30 s, or another default unit. Write explicit units whenever possible; if using `@DurationUnit`, make sure that convention is clearly understood.

Similarly, data sizes can be written as:

~~~yaml
storage:
  max-upload-size: 10MB
  buffer-size: "512KB"
~~~

Spring Boot can convert these values to `DataSize` when the target type matches; they are unit-qualified representations, not pure "YAML numbers".

## 7. When a value contains `:` and `#`

YAML uses `:` to separate keys from values. `#` can start a comment. Strings containing `: ` or ` #` should be quoted:

~~~yaml
messages:
  title: "Result: Success"
  text: "Completed #1"
  template: "name: value"
  label: "Product #A"
~~~

Error-prone or content-truncating examples:

~~~yaml
messages:
  title: Result: Success    # ': ' can easily be treated as a separator
  text: Completed #1        # '#1' may become a comment
~~~

Not every `:` requires quotes: `https://example.invalid` is normally a valid plain scalar because there is no space after `:`. Still, when a URL has fragments, queries, or placeholders, quoting often improves readability:

~~~yaml
endpoints:
  base-url: "https://api.example.invalid/v1"
  docs-url: "https://docs.example.invalid/guide#install"
~~~

Leading or trailing spaces must also be explicitly preserved with quotes if they are an intentional part of the string.

## 8. When a value starts with special characters

A plain scalar can be invalid or interpreted as YAML syntax when starting with `*`, `&`, `!`, `[`, `{`, `@`, `%`, or certain other indicator characters.

~~~yaml
examples:
  wildcard: "*"
  literal-tag: "!important"
  account: "@ops"
  progress: "%ready"
  bracket-text: "[draft]"
  brace-text: "{status}"
  literal-comment: "#not-a-comment"
~~~

Quotes state explicitly that this is a **string**, not an alias, anchor, tag, or collection structure.

Also distinguish **a comma-containing string** from **a YAML list**:

~~~yaml
roles:
  list:
    - ADMIN
    - SUPPORT
  comma-separated-text: "ADMIN, SUPPORT"
  inline-list: [ADMIN, SUPPORT]
  literal-list: "[ADMIN, SUPPORT]"
~~~

`list` and `inline-list` are YAML sequences. `comma-separated-text` and `literal-list` are strings. Do not assume the same type just by glancing at commas or brackets.

## 9. How do single quotes differ from double quotes?

Both single quotes and double quotes can keep a scalar as a string. The main difference is **escaping**.

~~~yaml
text:
  single-quote: 'It''s ready'
  double-quote: "It's ready"
  single-path: 'C:\new\test'
  double-path: "C:\\new\\test"
  line-break: "line 1\nline 2"
  literal-slash-n: '\n'
~~~

Explanation:

- Inside single quotes, write `''` to include a `'` character. Backslashes are generally preserved as ordinary characters.
- Inside double quotes, a backslash starts an escape sequence: `\n` is a newline, `\t` is a tab, `\"` is a double quote, and `\\` is a single backslash.
- Single quotes are convenient when content has many Windows paths or regexes without needing escapes.
- Double quotes are convenient when you genuinely want to represent tabs, newlines, or special characters with escapes.

Common mistake:

~~~yaml
paths:
  input: "C:\new\temp"
~~~

`\n` and `\t` inside double quotes can alter the string. Prefer:

~~~yaml
paths:
  input: 'C:\new\temp'
~~~

or escape backslashes properly:

~~~yaml
paths:
  input: "C:\\new\\temp"
~~~

For long multiline strings (such as banner text or templates), YAML also provides block scalars `|` and `>`. They have their own rules for line breaks and folding; that is a different choice from writing a short quoted scalar.

## 10. Spring Boot: YAML parser and Binder are two separate steps

Example configuration:

~~~yaml
catalog:
  code: "0012"
  display-name: "Catalog: Summer #1"
  max-items: 100
  enabled: true
  release-date: "2026-11-12"
  request-timeout: 5s
  label: "off"
~~~

Target Java type:

~~~java
package example.config;

import java.time.Duration;
import java.time.LocalDate;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        String code,
        String displayName,
        int maxItems,
        boolean enabled,
        LocalDate releaseDate,
        Duration requestTimeout,
        String label
) {}
~~~

In the Spring Boot application class, enable scanning for `@ConfigurationProperties` if no other registration mechanism is configured:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Meaning of each pair:

| YAML value | Java type | Expected result |
| --- | --- | --- |
| `"0012"` | `String code` | Preserves code `0012` |
| `"Catalog: Summer #1"` | `String displayName` | Preserves all punctuation and text |
| `100` | `int maxItems` | Integer 100 |
| `true` | `boolean enabled` | Boolean true |
| `"2026-11-12"` | `LocalDate releaseDate` | ISO date |
| `5s` | `Duration requestTimeout` | 5 seconds |
| `"off"` | `String label` | Text "off" |

High-level processing flow:

~~~text
application.yml
      |
      v
YAML parser
  - parses maps, lists, scalars
  - handles quotes / value types
      |
      v
Spring Environment / PropertySource
  - manages key/value pairs and precedence
      |
      v
Spring Boot Binder
  - converts values to Java field types
      |
      v
CatalogProperties
  - String, int, boolean, LocalDate, Duration
      |
      v
Bean consuming configuration
~~~

Thus, `max-items: "100"` can still bind to `int`. Meanwhile, `code: "0012"` only preserves `"0012"` if the target is `String`; bound to `int`, the numeric result is 12. **Quotes protect representation at the YAML layer but do not override the Binder's target type.**

Invalid fields can cause startup failures: for instance, `max-items: "many"` cannot be converted to `int`, and an improperly formatted date cannot be converted to `LocalDate`.

## 11. Distinguishing YAML from .properties

The same configuration can be written in both formats:

~~~properties
catalog.code=0012
catalog.max-items=100
catalog.enabled=true
catalog.release-date=2026-11-12
catalog.display-name=Catalog: Summer #1
~~~

~~~yaml
catalog:
  code: "0012"
  max-items: 100
  enabled: true
  release-date: "2026-11-12"
  display-name: "Catalog: Summer #1"
~~~

A `.properties` file reads values as text before Spring converts them to the target type. YAML has its own parser handling structure and scalars, so authors must pay closer attention to numbers, booleans, nulls, and dates/times that might undergo type inference.

Both are application configuration sources; Spring Boot can combine multiple sources such as environment variables, command-line arguments, and configuration files by precedence. Quotes in YAML do not decide which source wins when keys collide.

## 12. Placeholders and secrets

A configuration value can use placeholders resolved by Spring, such as URLs or access keys read from environment variables. Regardless of whether YAML uses single or double quotes, quotes are primarily processed by the YAML parser; they **do not automatically disable Spring's placeholder mechanism**.

Key points to remember:

- Only use quotes to keep syntax/values accurate; do not treat quotes as encryption or a way to hide secrets.
- Secrets should come from a secrets management mechanism or controlled environment variables, not stored verbatim in a repository.
- Do not log bound tokens/passwords.
- Strings with placeholders can still fail during configuration/binding if a variable is missing or has an incompatible value.
- For overridden values, verify target types and conversion rules, not just how the value looks in `application.yml`.

## 13. Typical mistakes and fixes

### Code loses leading zeros

~~~yaml
shipment:
  tracking-code: 0000123
~~~

If this is a code rather than a quantity, write `tracking-code: "0000123"` and use `String trackingCode`.

### Version `1.20` becomes `1.2`

~~~yaml
app:
  version: 1.20
~~~

If you need literal "1.20", write `version: "1.20"` and use type `String`.

### Word "off" parsed as boolean or changing meaning across parsers

~~~yaml
notification:
  channel-label: off
~~~

Write `channel-label: "off"` if it is a text status name/code. If it is a boolean flag, rename it clearly and use `enabled: false`.

### Colons and `#` in a message

~~~yaml
banner:
  message: Deployment: complete #1
~~~

This string easily collides with YAML syntax. Write:

~~~yaml
banner:
  message: "Deployment: complete #1"
~~~

### Using the wrong date format

~~~yaml
release:
  date: "12/11/2026"
~~~

If the Java target is `LocalDate` using standard ISO conversion, write `date: "2026-11-12"`. If `dd/MM/yyyy` is required, configure an appropriate conversion/formatter rather than just changing quotes.

### Wanting "empty" but declaring null

~~~yaml
profile:
  nickname:
~~~

If an empty string is required, use `nickname: ""`. If "not provided" is intended, define explicitly how Java handles missing/null values.

### Quoting a value that still fails Java type conversion

~~~yaml
limits:
  max-users: "ten"
~~~

If the field is `int maxUsers`, do not expect the Binder to turn `"ten"` into 10. Valid YAML quotes do not guarantee valid type conversion.

### Assuming editing the YAML file updates a running bean automatically

Spring Boot applications normally load and bind configuration at startup. Editing a file on disk does not automatically recreate every bean or update injected dependencies. If dynamic reconfiguration is required, design refresh mechanisms and component lifecycles explicitly.

## 14. Choosing quotes with four questions

Whenever you add a new scalar in `application.yml`, ask:

1. **Is this a value for calculation or a code whose exact text must stay intact?** Quantities are usually unquoted; codes, phone numbers, and versions are usually quoted and bound to `String`.
2. **Does the value look like a special keyword?** If it is genuinely boolean, use `true`/`false`. If it is text like `"no"`, `"off"`, or `"null"`, quote it.
3. **Does the value contain YAML syntax characters?** Especially `: `, ` #`, or leading `*`/`!`/`[`/`{`; quote it to preserve the text.
4. **Which Java type will receive the value?** The target type may convert strings to `int`, `boolean`, `LocalDate`, or `Duration`. Choose an appropriate format and annotations.

### Short exercise

Read the configuration:

~~~yaml
demo:
  a: 12
  b: "12"
  c: true
  d: "true"
  e: "0008"
  f: "off"
  g: "2026-11-12"
  h: null
  i: "null"
  j: "Welcome: YAML #1"
  k: 500ms
~~~

Predict the intent:

- `a` is a number; `b` is a string that looks like a number.
- `c` is a boolean; `d` is a string containing the word "true".
- `e` is a code preserving leading zeros; `f` is the string "off".
- `g` is a date written as text before Binder processing.
- `h` is null; `i` is the word "null".
- `j` is a string containing both `:` and `#`.
- `k` is a unit-qualified value that can bind to `Duration` when the target type matches.

Each value's meaning is only complete when you know both **how it is written in YAML** and **the Java type receiving the data**.

## 15. Takeaways

Use `true`/`false` for booleans, unquoted numbers for numeric quantities, and quote strings that could be misinterpreted: codes like `"0007"`, versions like `"1.10"`, words like `"off"`/`"null"`, dates like `"2026-11-12"`, and strings containing `: ` or ` #`. For durations and data sizes, include units; for timestamps, use ISO representations with explicit timezone/offset as needed.

**Quotes control how YAML reads a scalar. The Spring Boot Binder and Java type declarations determine the value the application uses.**
