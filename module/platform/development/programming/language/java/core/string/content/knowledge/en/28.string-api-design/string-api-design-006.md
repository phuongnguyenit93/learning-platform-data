# Distinguishing Plain Text from Grammar-Structured Text in Java API Design

## Objectives

A Java variable of type `String` only tells you that it holds a sequence of Unicode characters. The `String` type **does not tell you** whether its content is a sentence for display, an order code, a URL, a regular expression, a SQL query, or a JSON document. All of these kinds of content can be passed via `String`, yet each has **different structural rules, meanings, and handling requirements**.

When designing an API, recognize an important boundary:

- **Plain/free text:** primarily content intended for humans, such as display names, comments, or product descriptions. Characters like commas, parentheses, or `*` may simply be literal characters.
- **Grammar-structured text:** a character sequence read by a parser, such as `ORD-0042` following order-code rules, `https://example.com?q=java` following URI syntax, or `a.*b` following regular expression syntax.
- **Structured data representations:** data with fields, elements, types, and constraint rules, such as JSON or CSV. In Java, data may arrive as text, but it must be parsed according to the proper grammar to understand its structure.

This lesson helps you determine when to keep a string verbatim, when to parse and validate, and when to use structure-building APIs instead of manual string concatenation.

## 1. Same `String`, different meanings

Consider:

```java
String comment = "I like the .* symbol in the example";
String regex = ".*";
String productCode = "ORD-0042";
String jsonText = "{\"name\":\"Java\",\"count\":3}";
```

All four variables are `String`. However:

| Value | Role | Proper Handling |
| --- | --- | --- |
| `comment` | Free text for display or storage | Preserve content per API contract; escape properly when placed into a syntax-sensitive display environment |
| `regex` | Regular expression | Pass through `Pattern.compile` if the application genuinely intends to interpret regex |
| `productCode` | Identifier with a valid pattern | Validate the entire string against business rules; consider a dedicated value object |
| `jsonText` | JSON document | Use a JSON parser to validate syntax and construct data types; do not split manually with simple `split` |

**Punctuation does not have a fixed meaning for every `String`.** A period `.` in prose is a sentence stop, whereas in regex it can represent any character. An `&` is a character in a person's name; when placed in a URL query string, it typically separates parameters. A `"` character in a quoted sentence is not equivalent to string delimiters in JSON unless it goes through a JSON encoder.

In other words, **meaning comes from the API contract and parser**, not merely from the fact that the value has type `String`.

## 2. API design: make clear whether input is content or syntax

A hard-to-use API often lumps everything into a generically named parameter:

```java
void process(String value); // Is value content, a URL, an expression, or a code?
```

Meaningful names and types help callers clearly understand expectations:

```java
void saveDisplayName(String displayName);
void addOrderByCode(OrderCode code);
void fetchDocument(java.net.URI documentUri);
void searchLiteralText(String literalText);
void searchByPattern(java.util.regex.Pattern pattern);
```

These are **illustrative signatures**, not a standalone runnable Java class. `OrderCode` in the example is an application-defined value object.

Several useful design rules:

1. For **display** data, decide whether exact casing, Unicode, spaces, line breaks, and special characters must be preserved. Do not alter original text merely because it contains characters that coincide with syntax tokens of another format.
2. For **identifiers**, define the character set, length, prefix, casing policy, error reporting, and whether normalization applies.
3. For **machine-oriented syntax**, prefer already-parsed object types when appropriate: `URI`, `Path`, `Pattern`, `LocalDate`, enums, or validated value records.
4. For **JSON/XML/CSV** documents, specify the parser/serializer and data model. An arbitrary JSON string is not guaranteed to be valid JSON.
5. For user data placed into **another syntax**, know how to encode or parameterize for that exact context. Do not insert arbitrary data into command/code positions via string concatenation.

An API should separate two cases: **the user enters characters meant literally** and **the user intentionally provides an expression in a published syntax**. For example, a regular search box should not silently interpret `*` or `.` as regex if the UI has not stated so.

## 3. Distinguishing data validation from parsing

Three related but non-synonymous operations:

- **Validation:** checks whether a value satisfies defined constraints. For example, an order code must match `ORD-` and four ASCII digits.
- **Parsing:** interprets a string according to a grammar and converts it into a meaningful structure or type. For example, `LocalDate.parse("2026-10-23")` creates a date object or reports a syntax error.
- **Encoding/escaping:** converts data characters into a valid representation in an output context, such as a URL parameter, JSON string, or HTML text. This does not by itself prove the input content is valid under business rules.

For example, `"ORD-0042"` may be a valid order code under application policy, whereas `"ORD-42 abc"` is invalid. Use `Pattern.matcher(value).matches()` to require **matching the entire string**:

```java
import java.util.regex.Pattern;

Pattern orderCode = Pattern.compile("ORD-[0-9]{4}");

System.out.println(orderCode.matcher("ORD-0042").matches()); // true
System.out.println(orderCode.matcher("ORD-42 abc").matches()); // false
```

`find()` looks for a substring matching the pattern; `matches()` requires the entire input to match. For identifiers, using `find()` can accidentally allow extra prefixes/suffixes.

Distinguish **syntactic validity** from **business validity**. `ORD-0042` matches the format, yet it may not exist in the database, may not belong to the caller, or may have expired. Regex cannot replace permission, state, and uniqueness checks.

## 4. Regex: literal text vs. regular expression language

Regex is the clearest example of a string having a grammar. In regex:

- `.` means a matching character, rather than a literal period;
- `*` is a repetition quantifier for the preceding expression;
- `[ab]` is a character class containing `a` or `b`;
- `|` means alternation between two branches.

If a user wants to search for the exact string `a.b`, then:

```java
Pattern wrong = Pattern.compile("a.b");
System.out.println(wrong.matcher("axb").find()); // true
```

The regex `a.b` also matches `axb`. That is not literal search behavior.

When accepting **content to search literally**, use `Pattern.quote(literal)` to create a regex matching the exact characters of the literal string:

```java
String literal = "a.b";
Pattern exactText = Pattern.compile(Pattern.quote(literal));

System.out.println(exactText.matcher("read a.b now").find()); // true
System.out.println(exactText.matcher("read axb now").find()); // false
```

There is no need to turn every string search into a regex. If the requirement is simply to find an exact character substring, `String.contains` or `indexOf` is usually more direct and easier to understand:

```java
System.out.println("read a.b now".contains("a.b")); // true
```

**The `String.split` pitfall:** the parameter of `split(regex)` is a **regex**, not a literal delimiter. For example, `"A|B|C".split("|")` cannot simply be assumed to split on `|`, because `|` is a regex operator. To split on an exact delimiter from a variable:

```java
String delimiter = "|";
String[] parts = "A|B|C".split(Pattern.quote(delimiter), -1);
```

The `-1` parameter preserves trailing empty elements. For CSV format, calling `split(",")` alone is still insufficient if there are commas inside quoted fields; that case requires a proper CSV parser.

## 5. When strings contain URIs, delimiter meanings come from syntax

A user might type \`An & Binh\` as a display name, but when that string becomes a **query value**, \`&\` can be interpreted as a parameter separator if concatenated directly. For form-style query values, \`URLEncoder\` encodes the data according to the proper rules:

~~~java
String value = "An & Binh";
String encoded = java.net.URLEncoder.encode(
        value, java.nio.charset.StandardCharsets.UTF_8);
System.out.println(encoded); // An+%26+Binh
~~~

\`URLEncoder\` is not a general encoder for an **entire URI, path segment, or fragment**. If the contract requires an address, use \`java.net.URI\` or an appropriate URI builder, inspect scheme, host, and path, and validate the destination after resolution. Successful parsing does not prove the address is permitted to be accessed.

## 6. JSON and CSV are structured documents, not a list of characters

In JSON, quotes \`",\`, backslashes, braces/brackets, arrays/objects, and data types carry syntactic meaning. In CSV, a comma or newline **may appear inside a quoted field**, and \`""\` is how an embedded quote is represented in common dialects. Therefore \`split(",")\` and \`split("\n")\` are insufficient for parsing general documents.

~~~json
{"title":"Java, Strings","completed":true}
~~~

~~~csv
name,note
"Nguyen, An","The quote ""Java"" is great"
~~~

Use a JSON parser/serializer such as Jackson or a CSV parser/writer following the agreed dialect; Java SE 17 does not include a general-purpose JSON serializer. Pass parsed objects/records into the domain instead of passing ambiguous raw JSON/CSV strings across multiple layers. The next lesson covers edge cases and library usage in detail.

## 7. Executable syntaxes must keep data separate

For SQL, pass values using \`PreparedStatement\` instead of concatenating into the query string. For HTML, render text using text nodes or templates with context-appropriate auto-escaping; avoid concatenating user content into markup. For system commands, prefer \`ProcessBuilder\` passing the executable and each argument separately rather than passing an entire user string through a shell.

~~~java
String sql = "SELECT id FROM users WHERE name = ?";
try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, userInput); // userInput is data, not SQL syntax
}
~~~

This is an illustrative snippet assuming \`java.sql.Connection connection\` and \`String userInput\` exist. SQL parameters cannot replace table/column names; dynamic structural parts still require an allowlist. Across HTML, JavaScript, CSS, SQL, or shell commands, each boundary has its own syntax: a single universal escape function is insufficient for all of them. The final lesson of the chapter dives into **the responsibilities of each output adapter**, including double escaping and multi-pass decoding.

## 8. A dedicated data type makes the API contract clear

A value object is a useful choice when a string is used in many places with the same structure. For example, an order code of `ORD-` plus four ASCII digits:

```java
import java.util.Objects;
import java.util.regex.Pattern;

record OrderCode(String value) {
    private static final Pattern FORMAT = Pattern.compile("ORD-[0-9]{4}");

    OrderCode {
        Objects.requireNonNull(value, "value");
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
```

This is a valid Java 17 `record` definition suitable for package-private top-level or nested inside a class. Once constructed successfully, the `OrderCode` object represents a value validated **against the specified pattern**. APIs needing an order code can accept `OrderCode` instead of an ambiguous `String`. Note: do not use a syntactically valid code as proof that the order actually exists.

You do not need to create a new class for every ordinary string. Fields like display name, note content, and article title can remain `String` if the contract is clear enough. Value objects provide greater value when a string has a grammar/constraint repeated across many APIs or is easily confused with other string kinds.

## 9. Complete runnable Java 17+ example

This example combines how to:

- keep display text intact as received;
- validate an entire code string against a defined grammar;
- search a literal containing a dot without treating it as regex;
- encode a **form query value**;
- split on a literal delimiter that has special meaning in regex.

Create the file **`TextVsSyntaxDemo.java`**:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.regex.Pattern;

public class TextVsSyntaxDemo {

    private static final Pattern ORDER_CODE =
            Pattern.compile("ORD-[0-9]{4}");

    public static void main(String[] args) {
        String display = "  Mon an #42  ";
        System.out.println("Display: [" + display + "]");

        System.out.println(
                "Valid code: " + ORDER_CODE.matcher("ORD-0042").matches()
        );
        System.out.println(
                "Invalid code: " + ORDER_CODE.matcher("ORD-42 extra").matches()
        );

        String literal = "a.b";
        Pattern literalPattern = Pattern.compile(Pattern.quote(literal));

        System.out.println(
                "Literal found: "
                        + literalPattern.matcher("read a.b now").find()
        );
        System.out.println(
                "Not a regex wildcard: "
                        + literalPattern.matcher("read axb now").find()
        );

        String parameterValue = "An & Binh";
        String formEncoded = URLEncoder.encode(
                parameterValue,
                StandardCharsets.UTF_8
        );
        System.out.println("Query component: name=" + formEncoded);

        String[] parts = "A|B|C".split(Pattern.quote("|"), -1);
        System.out.println("Parts: " + Arrays.toString(parts));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 TextVsSyntaxDemo.java
java TextVsSyntaxDemo
```

Output:

```text
Display: [  Mon an #42  ]
Valid code: true
Invalid code: false
Literal found: true
Not a regex wildcard: false
Query component: name=An+%26+Binh
Parts: [A, B, C]
```

Output explanation:

- `display` is printed intact, including the two leading and trailing spaces. Because the value is display content, it is neither stripped nor parsed as another grammar.
- `matches()` accepts `ORD-0042` and rejects `ORD-42 extra`, because the regex requires the entire code to match the prefix and exactly four digits.
- `Pattern.quote("a.b")` causes the dot to be matched as an actual character; it does not arbitrarily match `x`.
- `URLEncoder` handles spaces and `&` according to form encoding for parameter values.
- `Pattern.quote("|")` tells `split` to treat `|` as a literal delimiter rather than a regex operator.

## 10. Decision table when designing a `String` parameter

| Question to ask | If the answer is… | Design Direction |
| --- | --- | --- |
| Is the value displayed verbatim? | Name, description, comment | Preserve content, define separate whitespace/Unicode policy; escape when outputting to another format |
| Does the value have a clear valid pattern? | Order code, version identifier | Validate the whole string, report clear errors; consider a value object |
| Is the value syntax intentionally entered by the user? | Regex, filter expression | Publish the grammar, parse/catch errors; distinguish from literal search |
| Does the value carry multi-field structure? | JSON, CSV | Use an appropriate parser/serializer; do not manually split or concatenate |
| Is the value placed inside text with another syntax? | URL, SQL, HTML, shell | Use context-appropriate encoding, parameterization, or structure-building APIs |
| Is the value compared in a collection? | Map/set key | Decide whether to normalize or preserve; check for collisions |
| Does the value pass through multiple API layers? | HTTP input → service → repository | Separate parse/validate boundaries at the proper layer, preferring validated types internally |

Remember that **validation, escaping, and authorization are three independent tasks**. A syntactically valid string can still reference a resource the user has no permission to access; an HTML-escaped value can still violate data rules; and a valid value inside JSON is not necessarily safe if later inserted verbatim into a SQL statement.

## 11. Common mistakes

1. **Treating every `String` as plain text.** Passing user text into `Pattern.compile`, SQL, or template expressions lets special characters act as control tokens.
2. **Treating every punctuation mark as structure.** Splitting on commas, periods, or `&` in names/comments even when they are just display text.
3. **Using `split` instead of a proper parser.** JSON/CSV/URL have quoting, escaping, nesting, or encoding rules; naive string splitting corrupts valid data.
4. **Confusing `matches()` and `find()`.** Identifiers must match as a whole; searching for a substring requires different semantics.
5. **Using one escaping scheme across multiple contexts.** SQL parameters, JSON escaping, URL encoding, and HTML escaping address different grammars.
6. **Altering display content when creating keys.** Normalizing for matching may be necessary, but retain the original text if users need to view exactly what they entered.
7. **Assuming successful parsing means full validity.** A syntactically valid URI may not have an allowed scheme/host for the business domain; a pattern-valid order code may not exist.
8. **Building APIs accepting `String` without documenting the contract.** Callers will not know whether to send raw text, normalized codes, raw JSON, or parsed objects.

## 12. Self-check

**Question 1.** A search API lets users enter `"a.b"` and wants to find the exact three characters `a`, `.`, `b`. Should it call `Pattern.compile(userInput)`?

**Answer:** No. This is a literal search; use `String.contains(userInput)` or `Pattern.compile(Pattern.quote(userInput))` if the regex API is needed.

**Question 2.** Why is `"A,B"` not enough to prove it has two CSV columns?

**Answer:** A text string containing a comma may just be ordinary content. For CSV, column count also depends on quoting rules, delimiters, and the full record's syntax. Only a CSV parser can determine the structure under the chosen dialect.

**Question 3.** `ORD-0042` matches the required regex. What does that prove?

**Answer:** It only proves the string satisfies the syntactic pattern. It does not prove a corresponding order exists, that the value is unique, or that the caller has permission to access it.

**Question 4.** If a username contains `&`, can it be placed directly into a URL query via string concatenation?

**Answer:** No. When placed as a parameter value, you must use the proper component encoding mechanism, such as form encoding in the corresponding context; `&` must be preserved as data rather than interpreted as a parameter delimiter.

## Takeaways

**`String` is a container for characters; the API contract decides whether those characters are content or syntax.** For plain text, preserve content and handle output properly. For structured text, specify the grammar, parse/validate with dedicated tools, and convert to appropriate data types whenever possible. Whenever data enters SQL, URLs, JSON, HTML, regex, or shells, maintain the boundary between **data** and **control syntax** using context-appropriate APIs.