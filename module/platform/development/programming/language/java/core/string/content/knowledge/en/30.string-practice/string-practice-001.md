# Building an Explicit Policy-Based Input Cleaner in Java

When receiving data from forms, APIs, CSV files, or external sources, developers often write a chain of operations such as `trim()`, replacing multiple spaces with one, converting to lowercase, or stripping strange characters. This approach easily creates bugs when each data field has **different meanings and requirements**: usernames, display names, passwords, email addresses, article bodies, and file paths cannot share a single rule.

A reliable input cleaner must state clearly **which data is accepted, which transformations are allowed, which cases must be rejected, and the order of application**. This practice builds a Java 17+ cleaner with immutable policies for two input types:

- **Username:** Unicode NFKC normalization, stripping leading/trailing whitespace, locale-independent lowercasing, accepting only ASCII letters, digits, and underscores in a defined structure.
- **Display name:** NFC normalization, collapsing multiple whitespace characters into one, allowing Unicode letters and combining marks, preserving letter case; reporting an error rather than arbitrarily stripping invalid characters.

This is a **policy example for a specific application**, not a filter permitted to be applied verbatim to all languages, personal names, or systems.

## 1. Distinguishing cleaning, normalization, validation, and output encoding

| Concept | Purpose | Example |
| --- | --- | --- |
| **Normalization** | Bring representations considered equivalent by the application into a uniform form. | Convert a string with combining marks into NFC form. |
| **Cleaning / canonicalization** | Apply transformations explicitly declared by the policy. | Collapse whitespace in a display name into a single space. |
| **Validation** | Check whether data after transformation conforms to the field's contract. | A username must match `[a-z][a-z0-9_]{2,15}`. |
| **Context-aware output encoding/escaping** | Protect data when placed into HTML, JSON, URLs, SQL statements, shell commands, and other contexts. | Escape text when rendering HTML; use parameters for SQL statements. |

**Input cleaning does not replace protection mechanisms at the point where data is used.** For example, a string that already matches the display name rule must still be escaped when inserted into HTML; any SQL query receiving user data should use prepared statements/parameters instead of string concatenation. Avoid naming a generic function `sanitizeEverything()` and assuming that the output is safe in every context.

It is also necessary to distinguish:

- **Rejecting invalid data:** Tell the caller the exact type of violation without silently losing information.
- **Transforming valid data according to rules:** For example, stripping leading/trailing whitespace accepted by the product.
- **Arbitrarily fixing errors:** For example, silently dropping every character outside the allowlist can turn `ad!min` into `admin`; two different identifiers could become one. This example chooses to **reject** to prevent that case.

## 2. Writing the policy before writing the algorithm

The policy should define each decision dimension:

| Decision | Username | Display name |
| --- | --- | --- |
| `null` input | Reject | Reject |
| Unicode normalization | `Normalizer.Form.NFKC` | `Normalizer.Form.NFC` |
| Leading/trailing whitespace | Remove with `strip()` | Remove with `strip()` after collapsing |
| Internal whitespace | Unchanged; final character pattern will reject | Collapse whitespace sequences into a single ASCII space |
| Letter case | `toLowerCase(Locale.ROOT)` | Preserve |
| Unusual Unicode control/format chars | Reject | Reject, except whitespace allowed to be normalized |
| Structurally invalid UTF-16 string | Reject | Reject |
| Length after transformation | 3–16 code points | 1–40 code points |
| Allowed characters | `[a-z][a-z0-9_]{2,15}` | Unicode letters and combining marks, words separated by a single space |

Scope explanation:

- For username, `[a-z][a-z0-9_]{2,15}` requires the first character to be a lowercase ASCII letter, followed by 2 to 15 characters from `a-z`, `0-9`, or `_`. Total length is 3–16.
- For display name, the expression `[\p{L}][\p{L}\p{M}]*(?: [\p{L}][\p{L}\p{M}]*)*` uses the Unicode Letter/Mark categories. It intentionally **disallows** digits, hyphens, apostrophes, emoji, or many other ways of writing names. Real applications must adjust the allowlist to fit their user base; this illustrative policy must not be used to declare a user's name "invalid".
- `NFC` merges canonically equivalent Unicode representations under canonical normalization rules; `NFKC` also applies compatibility transformations, such as fullwidth Latin `Ａ` to `A`. NFKC can change the visual meaning of some characters: only use it if the identifier contract intends to treat those representations as equivalent.
- `Locale.ROOT` prevents letter case results from changing with the host machine's locale. This is *lowercasing*, not full Unicode *case folding*. For usernames that only accept ASCII after processing, the illustrative rule is clear enough.
- This practice measures length in **Unicode code points**, not the UTF-16 length of `String.length()`. A code point still does not always equal one human-perceived character (grapheme cluster); when limiting display names by "visible characters", choose another suitable definition.

## 3. Defining the pipeline order

A verifiable pipeline must run in its published order:

~~~text
Input String
    |
    v
1. Check null and raw data limits at the system boundary
    |
    v
2. Apply Unicode normalization NFC or NFKC per policy
    |
    v
3. Iterate code points; handle whitespace or reject control/format/surrogate
    |
    v
4. Strip leading/trailing whitespace when policy allows
    |
    v
5. Lowercase with Locale.ROOT if username
    |
    v
6. Check length and allowlist on the resulting value
    |
    +---- fails ----> REJECT: return actionable error
    |
    v
7. Return cleaned string for business logic use
~~~

**Why check after transformation?** `ＮＡＭＥ` can become `NAME` via NFKC and then `name` via lowercasing; structure and length must be evaluated on the value **actually stored or compared**. Request/raw string size should also be bounded **before** calling CPU/memory-intensive operations, avoiding processing an unbounded input string only to report it as too long at the end. The Java example below focuses on field rules; message size limits need to be configured at the application's ingress layer.

Field-specific decisions must be explicit. For instance, the display name pipeline allows turning tabs or newlines into spaces; an HTTP header field or a single-line identifier may need to **reject CR/LF** right at the start. Do not reuse the display name policy for such contexts.

## 4. Complete Java 17+ program

Save the following as **InputCleanerDemo.java** (UTF-8). `record Policy` centralizes all choices into one configuration object, and the two constants `USERNAME` and `DISPLAY_NAME` are separate input contracts. `Pattern` is compiled once per contract, while `Matcher` is created anew when checking each string.

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class InputCleanerDemo {
    record Policy(
            Normalizer.Form normalization,
            boolean trim,
            boolean collapseWhitespace,
            boolean lowercaseRoot,
            int minCodePoints,
            int maxCodePoints,
            Pattern allowed) {}

    static final Policy USERNAME = new Policy(
            Normalizer.Form.NFKC, true, false, true, 3, 16,
            Pattern.compile("[a-z][a-z0-9_]{2,15}"));

    static final Policy DISPLAY_NAME = new Policy(
            Normalizer.Form.NFC, true, true, false, 1, 40,
            Pattern.compile(
                "[\\p{L}][\\p{L}\\p{M}]*(?: [\\p{L}][\\p{L}\\p{M}]*)*"));

    static boolean whitespace(int codePoint) {
        return Character.isWhitespace(codePoint)
                || Character.isSpaceChar(codePoint);
    }

    static String clean(String raw, Policy policy) {
        if (raw == null) {
            throw new IllegalArgumentException("null");
        }

        String normalized =
                Normalizer.normalize(raw, policy.normalization());
        StringBuilder builder = new StringBuilder();
        boolean previousSpace = false;

        for (int offset = 0; offset < normalized.length();) {
            int cp = normalized.codePointAt(offset);
            offset += Character.charCount(cp);

            if (policy.collapseWhitespace() && whitespace(cp)) {
                if (!previousSpace) builder.append(' ');
                previousSpace = true;
                continue;
            }

            // Reject control/format characters and malformed UTF-16.
            if (Character.isISOControl(cp)
                    || Character.getType(cp) == Character.FORMAT
                    || (cp >= 0xD800 && cp <= 0xDFFF)) {
                throw new IllegalArgumentException(
                        "control/format/surrogate");
            }

            builder.appendCodePoint(cp);
            previousSpace = false;
        }

        String value = builder.toString();
        if (policy.trim()) value = value.strip();
        if (policy.lowercaseRoot()) {
            value = value.toLowerCase(Locale.ROOT);
        }

        int size = value.codePointCount(0, value.length());
        if (size < policy.minCodePoints()
                || size > policy.maxCodePoints()) {
            throw new IllegalArgumentException("length");
        }
        if (!policy.allowed().matcher(value).matches()) {
            throw new IllegalArgumentException("not allowed");
        }
        return value;
    }

    static void show(String label, String value, Policy policy) {
        try {
            System.out.println(
                    label + " -> " + clean(value, policy));
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    label + " -> REJECT (" + ex.getMessage() + ")");
        }
    }

    public static void main(String[] args) {
        show("username fullwidth",
                "  \uFF21lice_12  ", USERNAME);
        show("username invalid", "abc!", USERNAME);
        show("username control", "al\0ice", USERNAME);

        show("display NFC",
                "  Ca\u0300   phe\u0302  ", DISPLAY_NAME);
        show("display whitespace",
                "  Cà  \t phê \n", DISPLAY_NAME);
        show("display emoji", "Lan 🙂", DISPLAY_NAME);
        show("display empty", " \t  ", DISPLAY_NAME);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 InputCleanerDemo.java
java InputCleanerDemo
~~~

Output:

~~~text
username fullwidth -> alice_12
username invalid -> REJECT (not allowed)
username control -> REJECT (control/format/surrogate)
display NFC -> Cà phê
display whitespace -> Cà phê
display emoji -> REJECT (not allowed)
display empty -> REJECT (length)
~~~

**Case-by-case breakdown:**

1. `\uFF21` is the fullwidth Latin letter `Ａ`; NFKC converts it to `A`, `strip()` removes leading/trailing whitespace, then `Locale.ROOT` converts it to `alice_12`. This name is valid under the username regex.
2. `abc!` meets the length requirement, but `!` is not in the allowlist so it is rejected; the program **does not silently turn it** into `abc`.
3. `al\0ice` contains the NUL control character; the `Character.isISOControl` check rejects it before the regex check.
4. The string `Ca\u0300   phe\u0302` contains combining marks; NFC normalizes it to `Cà   phê` and then the whitespace collapser produces `Cà phê`.
5. The display name string containing a tab and a newline is collapsed into a single space because **the display name's own policy allows it**. Do not infer that all input types are allowed to convert CR/LF in this way.
6. The emoji `🙂` is not in the chosen Letter/Mark regex; the input is explicitly rejected, not silently deleted. Products supporting emoji in names must change the policy.
7. A whitespace-only string becomes an empty string; the length check detects and rejects it.

## 5. Explaining key technical decisions

### Unicode normalization: NFC and NFKC

`java.text.Normalizer.normalize(input, form)` returns a string in the requested normalization form. With `NFC`, canonically equivalent character sequences under the Unicode standard are brought to a unified form (when a composed form exists). With `NFKC`, compatibility characters are transformed more broadly. This is useful for identifiers but can make **two originally distinct inputs become one value**.

If username is used as a lookup key or unique constraint in a database, the system must perform normalization **before checking duplicates and before storing the identifier key**, following the same policy on every data entry path. When changing the policy in the future, collisions with existing usernames must be evaluated; you cannot simply change the normalization method and assume old data is unaffected.

Normalization does **not** resolve all visually similar characters (*confusables*, such as certain Latin and Cyrillic letters), nor does it replace business validation. For public or security-sensitive identifiers, consider character-confusion defenses at the product level.

### Whitespace is not just the `' '` character

`String.strip()` removes leading and trailing characters based on `Character.isWhitespace`, unlike `trim()` which has legacy character-value rules. Some Unicode whitespace characters such as non-breaking space are not recognized by `isWhitespace`. The example chooses `Character.isWhitespace(cp) || Character.isSpaceChar(cp)` for broader recognition **within the whitespace-collapsing policy**, converting them to an ASCII space before calling `strip()`.

The collapser uses `codePointAt`, `Character.charCount`, and `StringBuilder.appendCodePoint` so valid surrogate pairs are not split in half. Unpaired UTF-16 surrogate characters are rejected instead of being automatically replaced with replacement characters. `Character.FORMAT` cases are also rejected, including certain invisible formatting controls. However, some writing systems legitimately use formatting characters like zero-width joiner; this policy must be relaxed/adjusted if the product supports them. Do not apply a blanket removal of all formatting characters without considering context.

### Applying the allowlist after processing

`Pattern.matcher(value).matches()` verifies that **the entire value** matches the regex, unlike `find()` which only searches for a matching substring. This is why `abc!` is not accepted even though it contains a matching `abc` substring. Regex is part of the data contract and must be paired with length checks; a single regex should not be treated as sufficient to protect the system.

The display name character rule in the example is only an illustrative subset. Real names may contain hyphens, apostrophes, digits, scripts with complex rules, or emoji. Designers must explicitly decide which forms to accept, add tests for those scripts, and document rejection reasons.

### When to report errors instead of silently fixing?

In the demo, allowed transformations are recorded as properties of `Policy`. Cases outside the policy are rejected with `IllegalArgumentException` and stable illustrative reason labels: `null`, `control/format/surrogate`, `length`, `not allowed`. Production applications should turn these errors into **structured error codes** (such as an enum or result record) and return appropriate messages to users. Avoid exposing raw sensitive strings in logs or error responses.

Because transformations can lose distinctions between multiple inputs, it is sometimes necessary to store the **original value** for business purposes with proper access controls and use the **normalized value** for comparison/lookup. Do not retain the original value if the field is a secret or security policy forbids it.

## 6. Testing: cases needed beyond manual demo runs

The cleaner should have automated tests for each policy, especially at Unicode and length boundaries. The test suite should cover:

| Scenario group | Input / condition | Expected |
| --- | --- | --- |
| Missing value | `null` | Reject, without throwing an unexpected `NullPointerException`. |
| Empty after processing | `" \t "` for display name | Reject because length is less than 1. |
| Equivalent Unicode forms | `"Ca\u0300"` and `"Cà"` in display name | Same result `"Cà"` after NFC. |
| Compatibility form | `"\uFF21lice_12"` for username | Becomes `"alice_12"` after NFKC and lowercasing. |
| Disallowed characters | `"abc!"` for username | Reject; do not silently strip `!`. |
| Control/format | NUL, tab in username, invisible format characters | Reject according to username policy. |
| Multiple whitespace types | Space, tab, newline, non-breaking space in display name | Collapse into a single space; strip at both ends. |
| Length | 2, 3, 16, 17 ASCII characters in username matching structure | Accurate at boundaries, no `<`/`<=` off-by-one errors. |
| Non-BMP Unicode | Emoji / supplementary code points | Process whole code points; finally accept/reject per policy. |
| Policy switching | Same input, two different policies | Output follows each policy; no "hidden" exceptions. |
| Stability | `clean(clean(x, p), p)` for accepted data | Result equals `clean(x, p)` for the illustrative policies. |

Additional testing is needed for raw data limits at the API, high load, and behavior with untrusted inputs. Note that the **idempotence** test above is an expected property of this pipeline, not an automatic property of every normalization/cleaning operation; new policies must prove it themselves.

## 7. Integrating into an application: placement and responsibility boundaries

At the data-ingestion boundary layer (controllers, DTO mappers, import parsers), select the policy by **data field** instead of calling a generic contextless function:

~~~java
// Illustration snippet in an application that already has InputCleanerDemo.
String username = InputCleanerDemo.clean(
        requestUsername, InputCleanerDemo.USERNAME);
String displayName = InputCleanerDemo.clean(
        requestDisplayName, InputCleanerDemo.DISPLAY_NAME);
~~~

This snippet is illustrative, **not a standalone runnable program**: `requestUsername` and `requestDisplayName` are provided by the controller. Policies in the demo class are package-private; when extracting into a library in another package, expose an appropriate API and version the policies. Validation should be centralized in a shared place so all entry points (web, batch, migration) apply it consistently.

For **passwords**, do not trim, lowercase, apply NFKC, or silently replace characters unless the authentication protocol has defined the exact transformation and applies it consistently; changing the input string can alter the secret the user intended to use. For **emails, URLs, filenames, path addresses, and HTML text**, type-specific parsers, normalization rules, and protections are required. For example, preventing path traversal requires checking the path after resolving it inside an allowed directory; collapsing whitespace does not solve the problem.

For strings used in **SQL**, use `PreparedStatement` parameters or an ORM; for **HTML**, escape according to output context; for **shell commands**, avoid building commands by concatenating user strings; for **logs**, handle control characters and sensitive data according to logging policy. Do not assign `clean()` the responsibility of replacing those mechanisms.

## 8. Common design mistakes

| Mistake | Risk | Remedy |
| --- | --- | --- |
| Using one rule for username, display name, password, and body text | Data loss, altered meaning, or rejecting valid data. | Explicit policies per field and product contract. |
| `replaceAll("[^a-z0-9]", "")` to strip invalid characters | Can cause identifier collisions and mask input errors. | Reject when outside the allowlist; only apply agreed transformations. |
| Checking regex before normalize/lowercase, then storing the changed string | Final data may no longer have the properties that were checked. | Validate on the final representation after all transformations. |
| Using `String.length()` and assuming it is the visible character count | UTF-16 surrogate pairs and grapheme clusters make counts differ. | Choose code points or grapheme clusters according to actual requirements. |
| Using locale-dependent `toLowerCase()` for identifiers | Can produce different results across environments. | Use `Locale.ROOT` if policy allows locale-independent lowercasing. |
| Applying NFKC by default to all strings | Compatibility folding can alter data meaning. | Choose NFC/NFKC per data type and test for collisions. |
| Removing all Unicode characters in category FORMAT | Corrupts names/text in certain writing systems. | Only reject/transform if the field contract permits. |
| Trusting a cleaned string as automatically safe for HTML/SQL/URL | Different attack surfaces interpret strings differently. | Use prepared statements, output escaping, and context-specific parsers. |
| Only enforcing length limits after processing a huge input | Can waste CPU/memory unnecessarily. | Bound raw size at ingress first, then normalize and validate. |
| Not checking duplicates after username normalization | Two different representations can collide on one identifier key. | Normalize before uniqueness check and apply consistently on write/query. |

## 9. Follow-up exercises

1. Add a **product code** policy: only allow uppercase ASCII letters, digits, and hyphens, length 6–20; do not collapse internal whitespace. Write tests for valid/invalid inputs, as well as inputs after normalization.
2. Replace `IllegalArgumentException` with `record CleanResult(String value, String errorCode)` or a typed error model, ensuring callers receive a clear reason code and cannot accidentally use an invalid string.
3. Split out a display name policy supporting names with hyphens and apostrophes, and write multilingual tests before expanding the regex.
4. Add a raw string length limit before `Normalizer.normalize`, and specify whether this limit applies to code units or bytes when received over HTTP.
5. Create a stability test `clean(clean(input, policy), policy)` and a collision test after NFKC on a sample set of identifiers.

**Takeaway:** A good input cleaner starts with an **explicit policy on transformations and errors**, and only then moves to Java APIs. Normalize in the right order, iterate Unicode safely, check length and allowlists on the resulting value, reject out-of-policy cases, and apply context-appropriate protections when storing/displaying/using data.