# Defining a Cleaning Policy Before Input Validation in Java

## 1. Why design the policy first?

A string that looks like `"  Alice  "` does not receive the same treatment in every field. For a **display name**, removing leading and trailing whitespace may make sense. For an **account ID**, spaces can make the ID malformed and should be rejected. For a **password**, those exact spaces may be part of the secret and must not be removed arbitrarily.

Therefore, the first question is not whether to use `strip()` or `trim()`, but: **which characters is this field allowed to transform before validation?**

After this lesson, learners can:

1. Distinguish `null`, empty string `""`, blank string (*blank*), and content-bearing strings.
2. Understand `isBlank()`, `isEmpty()`, `strip()`, `trim()`, and the Unicode limitations of each API.
3. Choose the order **raw checks → allowed transformations → final-form validation**, or skip transformations when preservation is required.
4. Define contracts for display names, identifiers, passwords, and free-form text.
5. Test invisible characters, oversized raw data, `null`, internal whitespace, and Unicode strings.
6. Write Java 17+ code that avoids losing data or accidentally making invalid input valid.

## 2. Four distinct cases: null, empty, blank, content

| Value | Meaning | `isEmpty()` | `isBlank()` | `strip()` |
| --- | --- | --- | --- | --- |
| `null` | No String object | Throws NPE when called | Throws NPE when called | Throws NPE when called |
| `""` | String of length 0 | `true` | `true` | `""` |
| `"   "` | Three ASCII spaces | `false` | `true` | `""` |
| `"\t\n"` | Tab and newline | `false` | `true` | `""` |
| `"  Java  "` | Text with leading and trailing spaces | `false` | `false` | `"Java"` |
| `"A B"` | Space inside the content | `false` | `false` | `"A B"` |

`isEmpty()` only checks `length() == 0`, while `isBlank()` checks whether a string is empty or contains only code points treated as whitespace by `Character.isWhitespace()`. `strip()` removes this whitespace at **both ends** without automatically altering characters in the middle.

`String` is immutable: the result of `strip()` must be assigned, returned, or used directly. Calling `raw.strip();` and discarding the return value does not change `raw`.

~~~java
String raw = "  Java  ";
raw.strip();
System.out.println("[" + raw + "]");   // [  Java  ]

String clean = raw.strip();
System.out.println("[" + clean + "]"); // [Java]
~~~

Do not automatically treat `null` and `""` as identical. In an update API, `null` may mean clear the value, `""` may be an intentional empty value, and an omitted property may mean keep the existing value.

## 3. Analyzing the purpose of each data field

A **decision table** helps avoid using a single shared cleaning function across the entire application:

| Field type | Allowed cleaning | Validation | What to avoid |
| --- | --- | --- | --- |
| Display name | May `strip()` both ends, NFC if specified | Not blank, disallow inappropriate chars, length limit | Stripping diacritics, lowercasing, or collapsing internal spaces without permission |
| Exact account ID | No transformation unless spec defines canonicalization | Exact character-by-character regex/format match | Silently fixing an invalid ID into a valid one |
| Password | Preserve input by default in illustrative policy | Length limits, authentication policy checks | `strip()`, `trim()`, case folding, silent truncation |
| Search query | May `strip()` or collapse whitespace | Does blank mean no filter or an error? | Dropping meaningful characters from the query |
| Multi-line notes | May normalize newlines if the product requires | Size limits, appropriate disallowed characters | Accidentally removing tabs, newlines, or indentation |
| Protocol codes/signatures | Only as defined by the standard | Compare exact agreed representation | Arbitrary normalization that breaks signatures or identifiers |

For each field, the **contract** must state: whether `null` is accepted; how blank strings are interpreted; which transformations are allowed; what unit size limits use; which special characters are permitted; and how the final data is stored, searched, and displayed.

If multiple layers process the field, they must follow the same contract. For example, calling `strip()` on an ID during registration while comparing the raw ID during login creates hard-to-find inconsistencies.

## 4. Processing order and the principle of validating the final form

For a **field that allows removing leading/trailing whitespace**, a pipeline might look like:

~~~text
Raw input
   │
   ├─ Null check / raw size limit
   ▼
Apply only allowed operations
   ├─ strip()
   ├─ NFC (if required by contract)
   └─ other defined transformations
   ▼
Validate the resulting value
   ├─ blank or empty?
   ├─ post-transformation length limit?
   ├─ disallowed characters?
   └─ valid business format?
   ▼
Use/store the validated value
~~~

For exact-match IDs or passwords, skip the transformation step altogether: **raw input → validate as-is → use as-is**.

### Why not validate only before cleaning?

~~~java
String raw = "  A  ";
System.out.println(raw.length());         // 5
System.out.println(raw.strip().length()); // 1
~~~

If a name is required to be at least 3 length units **after cleaning**, checking only `raw.length() >= 3` is wrong. We must validate the value that will actually be stored.

### Why should we still cap raw size before cleaning?

A string containing millions of spaces can become `""` after `strip()`. If you only check the final length, the system has already received and processed a huge raw payload. Enforce request byte limits and/or raw character unit limits at the ingestion boundary, before expensive transformations.

**There is no universal order for every field.** For inputs allowed to be normalized first, validating after normalization makes sense. For fields requiring exact raw syntax, reject invalid inputs immediately. Each path must be documented in the contract.

## 5. strip(), trim(), isBlank(), and Unicode whitespace types

These Java APIs are similar but do not overlap completely:

- `strip()` and its variants `stripLeading()` and `stripTrailing()` use `Character.isWhitespace()`.
- `isBlank()` checks according to the `Character.isWhitespace()` definition.
- `trim()` by legacy specification removes leading/trailing characters with code unit values less than or equal to `U+0020`.
- Unicode characters that look like spaces are not necessarily classified the same way by `Character.isWhitespace()`.
- `Pattern` regex `\\s` also depends on flags; do not assume it matches the exact same set as `strip()`.

| Character | Unicode code | Note |
| --- | --- | --- |
| ASCII space | U+0020 | Removed by `strip()` when at start/end |
| Tab, newline | U+0009, U+000A | Removed by `strip()` at start/end, not deleted inside |
| IDEOGRAPHIC SPACE | U+3000 | `Character.isWhitespace()` returns `true` |
| NO-BREAK SPACE (NBSP) | U+00A0 | `Character.isWhitespace()` returns `false` |
| ZERO WIDTH SPACE | U+200B | Not considered whitespace by `isBlank()` |

~~~java
System.out.println("\u3000".isBlank()); // true
System.out.println("\u00A0".isBlank()); // false
System.out.println("\u200B".isBlank()); // false
~~~

A string consisting of NBSP can **be treated as non-blank** even though it is nearly invisible. If a single-line field disallows NBSP or zero-width characters, check them explicitly according to **that field's policy**, rather than relying solely on `!isBlank()`.

Do not automatically delete all "invisible" characters: certain combining marks and formatting characters are meaningful in Vietnamese or international text.

### Handling internal whitespace

If the requirement is to collapse consecutive **ASCII spaces** into one:

~~~java
String raw = "An   Bình";
String compact = raw.replaceAll(" +", " ");
System.out.println(compact); // An Bình
~~~

The pattern `" +"` applies only to ASCII spaces and does not automatically handle tabs, NBSP, or all Unicode whitespace. If a broader character set is needed, define and test that set. For multi-line content, source code, indented text, or addresses, collapsing whitespace can destroy important information.

## 6. Distinguishing cleaning, normalization, validation, and escaping

| Operation | Example | Purpose |
| --- | --- | --- |
| Cleaning | `strip()` | Remove permitted boundary characters |
| Unicode normalization | `Normalizer.normalize(s, NFC)` | Unify Unicode representation per contract |
| Validation | Length, disallowed chars, valid pattern | Decide whether to accept or reject |
| Output encoding | HTML escaping, SQL parameterization | Protect systems when using data in a specific context |

Two nearly identical-looking strings can have different Unicode representations:

~~~java
String decomposed = "Cafe\u0301";
String nfc = java.text.Normalizer.normalize(
        decomposed, java.text.Normalizer.Form.NFC);
System.out.println(decomposed.equals("Café")); // false
System.out.println(nfc.equals("Café"));        // true
~~~

NFC is **not** accent stripping, is not dangerous-content filtering, and is not a mandatory step for every field. Many protocols and authentication systems require preserving the exact character sequence.

Case conversion has locale-dependent rules if you use the default overload. When a **technical code** is specified as case-insensitive, you can use an explicit canonicalization rule such as `toLowerCase(Locale.ROOT)`; for personal names, passwords, or meaningful content, do not automatically convert case just for comparison convenience.

Input cleaning does not replace **parameterized SQL**, context-appropriate output escaping, path checks, resource limits, or authorization. Nor does it turn every invalid string into a safe string.

## 7. Three concrete policies: display name, account ID, and password

### 7.1. Display name

**Illustrative** contract:

1. Reject `null` and raw input longer than 200 UTF-16 code units.
2. Apply `strip()` at both ends and normalize to `NFC`.
3. Reject if the processed string is blank.
4. Reject ISO control characters, NBSP (U+00A0), and ZERO WIDTH SPACE (U+200B) per the example's custom rule.
5. Cap at a maximum of 40 Unicode code points after cleaning.
6. Preserve spaces between words, including multiple consecutive spaces.

The rule disallowing NBSP/zero-width characters and preserving internal spaces is an **illustrative** decision that may not suit every language or product. A system supporting multilingual names must consider grapheme clusters, combining marks, and real-world input habits.

### 7.2. Account ID

Suppose the specification requires 3–12 ASCII characters: starting with a lowercase letter, followed by lowercase letters, digits, or underscores:

~~~java
boolean valid = input != null
        && input.matches("[a-z][a-z0-9_]{2,11}");
~~~

`"alice"` is valid, whereas `" alice "`, `"Alice"`, and `"a b"` must be rejected. Do not silently call `strip()` or `toLowerCase()` to turn an invalid ID into a valid one unless the product specification intentionally permits it and all layers apply the same rule.

### 7.3. Password

In this illustrative example, the password policy is:

- Preserve every entered character, including leading and trailing spaces.
- Do not call `trim()`, `strip()`, lowercase, strip accents, or apply Unicode normalization.
- Check the specified length limits without silently truncating.
- Use the exact accepted representation during both registration and authentication.

A specific authentication system may define its own Unicode policy; if normalization is used, it must be designed consistently across the entire credential lifecycle and clearly communicated to users.

## 8. Complete example running on Java 17+

Create file **`InputCleaningPolicyDemo.java`**:

~~~java
import java.text.Normalizer;

public class InputCleaningPolicyDemo {
    record Result(boolean valid, String value, String reason) {}

    static Result displayName(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        if (raw.length() > 200) {
            return new Result(false, null, "RAW_TOO_LONG");
        }

        String clean = Normalizer.normalize(
                raw.strip(), Normalizer.Form.NFC);

        if (clean.isBlank()) {
            return new Result(false, null, "BLANK");
        }

        boolean forbidden = clean.codePoints().anyMatch(cp ->
                Character.isISOControl(cp)
                || cp == 0x00A0
                || cp == 0x200B);

        if (forbidden) {
            return new Result(false, null, "DISALLOWED_CHARACTER");
        }
        if (clean.codePointCount(0, clean.length()) > 40) {
            return new Result(false, null, "TOO_LONG");
        }
        return new Result(true, clean, "OK");
    }

    static Result accountId(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        if (!raw.matches("[a-z][a-z0-9_]{2,11}")) {
            return new Result(false, null, "FORMAT");
        }
        return new Result(true, raw, "OK");
    }

    static Result password(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        // Illustrative rule: 8..64 UTF-16 code units.
        if (raw.length() < 8 || raw.length() > 64) {
            return new Result(false, null, "LENGTH");
        }
        return new Result(true, raw, "OK");
    }

    public static void main(String[] args) {
        Result name = displayName(" \u3000An   Bình\u3000 ");
        System.out.println("name.valid=" + name.valid());
        System.out.println("name.value=[" + name.value() + "]");
        System.out.println("name.spacesKept="
                + name.value().contains("   "));

        Result id = accountId(" alice ");
        System.out.println("id.valid=" + id.valid());
        System.out.println("id.reason=" + id.reason());

        Result secret = password(" pass1234 ");
        System.out.println("password.valid=" + secret.valid());
        System.out.println("password.kept="
                + " pass1234 ".equals(secret.value()));

        Result blank = displayName(" \t\u3000 ");
        System.out.println("blank.reason=" + blank.reason());

        Result newline = displayName(" A\nB ");
        System.out.println("newline.reason=" + newline.reason());

        Result nbsp = displayName("\u00A0");
        System.out.println("nbsp.reason=" + nbsp.reason());
        System.out.println("nbsp.isBlank=" + "\u00A0".isBlank());
        System.out.println("ideographic.isBlank="
                + "\u3000".isBlank());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 InputCleaningPolicyDemo.java
java InputCleaningPolicyDemo
~~~

Stdout:

~~~text
name.valid=true
name.value=[An   Bình]
name.spacesKept=true
id.valid=false
id.reason=FORMAT
password.valid=true
password.kept=true
blank.reason=BLANK
newline.reason=DISALLOWED_CHARACTER
nbsp.reason=DISALLOWED_CHARACTER
nbsp.isBlank=false
ideographic.isBlank=true
~~~

**Explanation:** the display name has spaces and IDEOGRAPHIC SPACE stripped at both ends, while the three spaces in the middle remain intact. The padded ID is rejected. The dummy password is preserved; the program prints only status, not the secret. Whitespace-only input returns `BLANK`. Internal newline and NBSP are caught by the explicit check; `isBlank()` does not consider NBSP to be whitespace.

`record Result` is available in Java 17. In a real project, you can replace it with your framework's validation result type, while keeping the key rule: **never use `value` if `valid` is `false`**.

## 9. Optional fields, PATCH, and the absent state

In an update API, there are at least three different states:

1. **Property omitted:** usually means keep the existing stored value.
2. **Property sent as `null`:** may mean a request to clear it or be rejected.
3. **Property sent as `""` / blank:** may mean clear, store empty, or return an error.

You cannot infer whether a property **appeared in the request** from a single `String` reference that has already collapsed to `null`. Keep presence state separate or design an appropriate DTO/PATCH model.

Illustrative snippet (assuming both variables were resolved from the request):

~~~java
if (!fieldPresent) {
    // Keep the existing nickname unchanged.
} else if (input == null) {
    // Apply policy for an explicitly sent null.
} else {
    // Clean/validate the string according to the contract.
}
~~~

This is a *fragment* example, not a standalone program. The meaning of each case must be defined in the API contract and covered by dedicated tests.

## 10. Length limits and Unicode: do not use the ambiguous word "characters"

Different measurement units:

- `String.length()`: number of **UTF-16 code units**.
- `String.codePointCount(0, length())`: number of **Unicode code points**.
- `getBytes(StandardCharsets.UTF_8).length`: number of **UTF-8 bytes**.
- Number of **grapheme clusters**: closest to user-perceived characters, which may contain multiple code points.

For example:

~~~java
String emoji = "😀";
System.out.println(emoji.length()); // 2
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 1
System.out.println(emoji.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length); // 4
~~~

If the product says "40 characters," the development team must specify whether that means code points, graphemes, or another unit. Checking raw bytes to block oversized payloads serves a different purpose from capping display name length. Include at least a few tests with decomposed Vietnamese text and emojis to avoid confusing `char` with visible characters.

## 11. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `strip()` on `null` | `NullPointerException` | Check and define a contract for `null` |
| Calling `strip()` without capturing the result | Source value remains unchanged | Assign or `return` the new value |
| Using only `isEmpty()` | Spaces are treated as non-empty data | Use an appropriate blank rule |
| Assuming `isBlank()` catches all "invisible" chars | NBSP/zero-width slip through | Define the allowed character set |
| Automatically calling `strip()` on passwords | Alters the user's secret | Preserve input per the published policy |
| Lowercasing/stripping accents on every code before validation | Can make invalid codes valid or cause collisions | Define canonicalization explicitly |
| Collapsing internal whitespace for all text | Loses indentation, newlines, and meaning | Collapse only when the field permits |
| Checking raw length instead of cleaned length | Allows names that are too short | Validate the final stored form |
| Checking length only after `strip()` | Still accepts huge raw payloads | Enforce limits at the ingestion layer |
| Treating `trim()` and `strip()` as completely equivalent | Wrong for certain Unicode whitespace | Choose and test the right API |
| Believing regex `\\s` is Unicode everywhere | Misses character groups | Verify flags and regex character sets |
| Treating cleaning as a substitute for SQL/XSS protection | Risks at the usage layer | Parameterized SQL, context-appropriate output encoding |

An ideal cleaning rule should also be **idempotent** when business rules permit: running it twice yields the same content as running it once. For example, `"  A  ".strip().strip()` has the same content as `"  A  ".strip()`. Custom multi-step pipelines must be tested so they do not keep mutating data on every run.

## 12. Minimum test matrix

| Case | Example | What to verify |
| --- | --- | --- |
| Missing data | `null` | No unintended NPE |
| Empty | `""` | Reject/accept/convert policy |
| ASCII spaces | `"   "` | `strip` and `isBlank` |
| Unicode blank | `"\u3000"` | Known Unicode behavior |
| NBSP | `"\u00A0"` | Not confused with Java blank |
| Zero-width | `"\u200B"` | Explicit policy for hidden characters |
| Padding | `"  Alice  "` | Original and processed forms |
| Internal whitespace | `"An   Bình"` | Collapsed or preserved per contract |
| Internal newline | `"A\nB"` | Should single-line fields reject it? |
| Combining mark | `"Cafe\u0301"` | Is NFC allowed? |
| Emoji | `"A😀B"` | Appropriate length unit |
| Oversized input | Thousands of characters | Raw and final limits |
| Different-case ID | `"Alice"` | Silently altered or rejected? |
| Password with spaces | `" pass1234 "` | Must be preserved |

Also test **consistency** across UI, backend, API, stored data, and search operations. Layers should not independently apply different normalization steps to the same field.

## 13. Applied exercises

1. **Classification:** predict the results of `isBlank()`, `isEmpty()`, and `strip()` for `null`, `""`, `"  "`, `"\u3000"`, and `"\u00A0"`. Explain why `null` must be checked separately.
2. **Changing validation order:** a name must have at least three code points after `strip()`. Show how `"  A  "` can pass a raw-length check yet fail the final-form check.
3. **Two contrasting policies:** write `validateDisplayName()` with `strip()` and `validateAccountId()` without silent modification. Test both with the same input `" alice "`.
4. **Password:** pass a dummy passphrase with leading and trailing spaces. Verify that the validation function neither removes nor alters any character.
5. **Unicode:** compare `Character.isWhitespace(0x00A0)`, `Character.isSpaceChar(0x00A0)`, and `"\u00A0".isBlank()`. Why do they not necessarily give the same result?
6. **Dual limits:** design a raw limit of 200 UTF-16 units and a final limit of 40 code points; test a long string of only spaces and a string of emojis.
7. **PATCH:** explicitly specify omitting nickname, sending `null`, and sending `""`. Write three tests to ensure they are not collapsed into one state.
8. **Idempotence:** test `normalizeName(normalizeName(s)).equals(normalizeName(s))` across multiple inputs; analyze any failure.

## 14. Pre-production checklist

- What does the field mean? Are users entering free text, an exact code, a secret, or multi-line content?
- **Which part** of the data may be transformed? Only both ends, or inside as well?
- Do `null`, `""`, and blank carry the same meaning?
- Does `strip()`/`trim()` match the chosen whitespace definition? How are NBSP and zero-width handled?
- Is Unicode normalization or case folding applied? Does it lose information or meaning?
- Is validation performed on the raw value, final form, or both?
- Is the length limit in UTF-16 units, code points, graphemes, or bytes? Is there a pre-processing payload cap?
- Are control characters or invalid inputs rejected rather than silently fixed?
- Is the **omitted** property state preserved separately in PATCH?
- Has consistency been tested across creation, update, authentication, storage, and retrieval?

**Core rule:** before validating input, **define the cleaning policy for each field**. Transform only the permitted parts of the data and validate the exact form the application will use. **Not blank** does not mean **valid**; and cleaning does not mean safe in every context.

## 15. References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `strip()`, `trim()`, `isBlank()`, `isEmpty()`, `length()`, `matches()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `isWhitespace()`, `isSpaceChar()`, `isISOControl()`, Unicode code points.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD representations.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\\s`, Unicode regex flags, and character classes.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 bytes when calculating interchange data limits.