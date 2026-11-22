# String API Design: Clearly Specifying Null, Empty, and Blank Handling

## 1. The core problem

A Java API that accepts `String` often has to handle three states that are easily conflated:

1. **`null`**: no string object exists. Depending on the contract, this may mean "not provided", "unknown", an allowed value, or invalid data.
2. **Empty string `""`**: a `String` object exists, but its length is 0. This could be a value the user entered and then deleted, or valid content such as an empty note.
3. **Whitespace-only string (blank)**: it has characters, but all of them are considered whitespace by `String.isBlank()`, such as `"   "` or `"\t\n"`. An empty string also returns `true` for `isBlank()`.

In addition, **strings with content** like `" A "` may contain leading/trailing whitespace that the application wants to preserve or normalize. This lesson falls under **API design**, so the focus is on clearly defining meaning and behavior at the API boundary, not merely calling the right library method.

Example of an account creation API accepting a display name, password, and comment:

- Display name is required; `null`/empty/blank are all invalid; it can be `strip()`ped and then checked.
- Password does not allow `null` or empty, but **must not be automatically `trim()`med/`strip()`ped**, because spaces can be actual characters of the password under system policy.
- Comment may allow `null` ("not provided"), `""` ("provided but empty"), and `"   "` ("content consisting of spaces"); if you want to merge states, it must be explicitly documented.
- For partial update APIs, an *absent* field and a *present field with value null* can have different meanings, such as "unchanged" and "clear value".

**Foundational rule:** Do not habitually normalize every string input with `null -> ""` or `strip()`. Every parameter must have an appropriate data contract.

## 2. How Java checks each state

`String` in Java 17 has the following APIs:

| Expression | When `s == null` | `s = ""` | `s = "   "` | `s = " hi "` |
| --- | --- | --- | --- | --- |
| `s == null` | `true` | `false` | `false` | `false` |
| `s.isEmpty()` | Throws `NullPointerException` | `true` | `false` | `false` |
| `s.isBlank()` | Throws `NullPointerException` | `true` | `true` | `false` |
| `s.length() == 0` | Throws `NullPointerException` | `true` | `false` | `false` |
| `s.strip().isEmpty()` | Throws `NullPointerException` | `true` | `true` for standard spaces | `false` |

Since Java 11, `String.isBlank()` determines whether a string is empty or contains only code points recognized by `Character.isWhitespace(int)`. `isEmpty()` only checks whether length is 0 and **does not need to scan each character**.

When `null` may occur, check before calling methods:

```java
static boolean isNullOrBlank(String value) {
    return value == null || value.isBlank();
}
```

The `||` operator short-circuits: if `value == null` is `true`, Java does not call `isBlank()`. This is a **method snippet** placed inside a Java class, not a standalone program.

Note: `isBlank()` returns `true` for an empty string, so it cannot be used alone to distinguish **empty** from **blank but non-empty**. When classifying, check in the order: `null` → `isEmpty()` → `isBlank()` → has content.

## 3. Define the API contract before coding

Good API documentation should clearly answer: is `null` allowed, what does `""` mean, is whitespace preserved, is Unicode normalized, how is invalid data reported, and does the output preserve the input.

Example contract table for a system:

| API Field | `null` | `""` | Whitespace only | Leading/trailing whitespace | Recommended Behavior |
| --- | --- | --- | --- | --- | --- |
| `displayName` | Invalid | Invalid | Invalid | `strip()` and store normalized version | Return a clear error message when the name is invalid |
| `password` | Invalid | Invalid | May be valid if policy allows | **Preserve** | Do not alter secret content unless explicitly required |
| `searchQuery` | No filter | No filter | No filter | `strip()` | Normalize to "no filter" when empty/blank |
| `comment` | Not provided | Empty comment provided | Keep or reject per business logic | Preserve by default | Do not implicitly merge the three states |
| `update.bio` | May mean delete data | May mean set empty bio | May be valid data | Per policy | Must be distinguished from an absent field in update requests |

This table is a **design example**, not a universal rule of Java. The contract should be documented in Javadoc, OpenAPI/schema, validation, client docs, or the appropriate place in the project.

Several conditions need to be agreed upon across **client, server, and database**: whether an empty string is stored as `""` or `NULL`; whether whitespace is stripped during validation but not when storing; what kind of error is returned; and how an absent field is represented in JSON.

## 4. Handling strategies: Reject, Normalize, Preserve

### 4.1. Reject — reject invalid states

Used for required fields with meaningful data, such as display names:

```java
import java.util.Objects;

static String requireNonBlankName(String raw) {
    Objects.requireNonNull(raw, "name must not be null");
    String normalized = raw.strip();

    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return normalized;
}
```

`Objects.requireNonNull` proactively throws `NullPointerException` with a message when `raw` is null. `IllegalArgumentException` reports a value that violates business conditions. This is a design for an internal utility; at an HTTP boundary, applications usually translate validation errors into structured 4xx responses.

**Important:** Checking `raw.isBlank()` can reject blank values before normalization, whereas the example above checks the string **after stripping** because the contract requires storing the string without leading/trailing whitespace. The two approaches are consistent when using the same whitespace rule.

### 4.2. Normalize — intentionally merge states

An optional search box can define "no filter" when the query is `null`, empty, or all spaces:

```java
static String normalizeOptionalQuery(String raw) {
    if (raw == null) {
        return null;
    }
    String normalized = raw.strip();
    return normalized.isEmpty() ? null : normalized;
}
```

Now `null`, `""`, and `" \t "` all yield `null`, while `"  java  "` yields `"java"`. This is an **intentional business decision**, not a mandatory normalization for every String parameter. If you need to record that the user explicitly sent an empty string, do not use this merging approach.

If the contract wants **every output field to be non-null**, it can return `""` to represent "no content", but it must state that clearly and accept that the distinction between absent and empty is lost.

### 4.3. Preserve — keep intact, only check necessary conditions

For passwords (under a policy that allows spaces), do not automatically strip:

```java
static String requireNonEmptyPassword(String raw) {
    Objects.requireNonNull(raw, "password must not be null");
    if (raw.isEmpty()) {
        throw new IllegalArgumentException("password must not be empty");
    }
    return raw; // Preserve both spaces and Unicode characters.
}
```

In a real system, length, complexity, allowed character lists, and size limits may be required per authentication policy. This example only illustrates the **string contract**, not a recommendation for whitespace-only passwords.

Similarly, identifiers, tokens, signatures, hashed content, rich-formatted text, or meaningful whitespace **should not** be arbitrarily `strip()`ped, `toLowerCase()`d, or Unicode-normalized.

## 5. Complete Java 17+ example

Create the file **`StringInputPolicyDemo.java`**:

```java
import java.util.Objects;

public class StringInputPolicyDemo {
    enum Kind { NULL, EMPTY, BLANK, TEXT }

    static Kind kind(String value) {
        if (value == null) {
            return Kind.NULL;
        }
        if (value.isEmpty()) {
            return Kind.EMPTY;
        }
        return value.isBlank() ? Kind.BLANK : Kind.TEXT;
    }

    static String requireNonBlankName(String raw) {
        Objects.requireNonNull(raw, "name must not be null");
        String normalized = raw.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return normalized;
    }

    static String requireNonEmptyPassword(String raw) {
        Objects.requireNonNull(raw, "password must not be null");
        if (raw.isEmpty()) {
            throw new IllegalArgumentException("password must not be empty");
        }
        return raw;
    }

    static String normalizeOptionalQuery(String raw) {
        if (raw == null) {
            return null;
        }
        String normalized = raw.strip();
        return normalized.isEmpty() ? null : normalized;
    }

    public static void main(String[] args) {
        System.out.println("null=" + kind(null));
        System.out.println("empty=" + kind(""));
        System.out.println("blank=" + kind(" \t "));
        System.out.println("text=" + kind(" Java "));

        System.out.println("name=["
                + requireNonBlankName(" \t Lan \n") + "]");
        System.out.println("password-length="
                + requireNonEmptyPassword("   ").length());
        System.out.println("query-is-null="
                + (normalizeOptionalQuery(" \t ") == null));

        String unicodeSpace = "\u2003Java\u2003";
        System.out.println("strip-length=" + unicodeSpace.strip().length());
        System.out.println("trim-length=" + unicodeSpace.trim().length());
        System.out.println("nbsp-isBlank=" + "\u00A0".isBlank());

        try {
            requireNonBlankName(" \t ");
        } catch (IllegalArgumentException ex) {
            System.out.println("name-error=" + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 StringInputPolicyDemo.java
java StringInputPolicyDemo
```

Stdout:

```text
null=NULL
empty=EMPTY
blank=BLANK
text=TEXT
name=[Lan]
password-length=3
query-is-null=true
strip-length=4
trim-length=6
nbsp-isBlank=false
name-error=name must not be blank
```

The results have been verified on the JDK with APIs available in Java 17:

- `kind` checks `null` first, then `isEmpty`, then `isBlank`, so it avoids `NullPointerException` and preserves all four states.
- The name is `strip`ped to `Lan`; the three-space password retains length 3 because the current contract only forbids empty.
- The blank query is merged into `null` by the contract.
- `\u2003` is EM SPACE, recognized by `strip()`; `trim()` only removes characters with code less than or equal to U+0020 so it does not remove it.
- `\u00A0` is NO-BREAK SPACE: in Java, `Character.isWhitespace` does not treat it as whitespace, so `isBlank()` returns `false`. You must clearly understand the definition of "blank" in the contract rather than inferring from visual appearance.
- A standard whitespace-only name is rejected and receives an error with a message.

## 6. Distinguishing trim(), strip(), and isBlank() in Unicode

### 6.1. trim() has narrower historical criteria

`String.trim()` removes characters at both ends with code `<= U+0020` per the Java specification. `strip()` (Java 11+) is based on `Character.isWhitespace`; therefore results differ for some Unicode spaces.

```java
String input = "\u2003Java\u2003";

System.out.println(input.trim().length());  // 6
System.out.println(input.strip().length()); // 4
```

Not all characters commonly called "space" are considered whitespace by `Character.isWhitespace`: **NO-BREAK SPACE (U+00A0)** is an example. If the system needs to define "blank" according to custom rules (for example treating U+00A0 as blank), build a validator normalized to an agreed specification and test it independently.

### 6.2. isBlank() does not modify the string

`"  A  ".isBlank()` is `false`, because it contains the character `A`. `isBlank()` does not remove leading/trailing whitespace; `strip()` is what returns a new normalized string. Do not confuse **checking** with **transforming**.

```java
String value = "  A  ";
System.out.println(value.isBlank());       // false
System.out.println("[" + value.strip() + "]"); // [A]
System.out.println("[" + value + "]");       // [  A  ]
```

`String` is immutable: `strip()` does not modify the `value` variable. To store the normalized version, you must use the return value.

### 6.3. Do not use isEmpty() to check "user has not entered anything"

The string `"    "` is not empty, because it has characters. If a form considers an all-space string invalid, use `isBlank()` (after null check) or `strip().isEmpty()`. Conversely, for whitespace-sensitive data, only use `isEmpty()` if the contract requires it.

## 7. Null in parameters, return values, and update state

### 7.1. Required and optional parameters

For required parameters, the API should clearly state "non-null" and empty/blank conditions. A function accepting a display name can use Javadoc:

```java
/**
 * Stores the display name after stripping leading and trailing whitespace.
 *
 * @param name non-null value; after stripping must have at least one character
 *             that is not whitespace per Character.isWhitespace
 * @return normalized name, non-null and non-blank
 * @throws NullPointerException if name is null
 * @throws IllegalArgumentException if name is blank
 */
static String validateDisplayName(String name) {
    Objects.requireNonNull(name, "name");
    String normalized = name.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("blank name");
    }
    return normalized;
}
```

This is a logically standalone method snippet that needs to be placed inside a class to compile. For public APIs, you may choose the same validation error type for both null and blank, provided **the contract and tests express it consistently**; the example above intentionally distinguishes errors caused by null from invalid values.

For **return values**, agree on whether `null` means "not found" or an exception, and whether `""` is a valid value. You can use `Optional<String>` for results that may be absent:

```java
static java.util.Optional<String> normalizedQuery(String raw) {
    if (raw == null || raw.isBlank()) {
        return java.util.Optional.empty();
    }
    return java.util.Optional.of(raw.strip());
}
```

`Optional.empty()` makes it possible to express "no result" explicitly; however, it also **merges** null and blank according to policy. `Optional` does not replace making decisions about empty/blank, and does not need to be used on every field or parameter just to avoid designing a contract.

### 7.2. Partial update APIs must distinguish absent from null

Suppose a profile update request has a `bio` field. Input states can carry these meanings:

| Request State | Example Meaning |
| --- | --- |
| Property `bio` is absent | Keep current bio unchanged |
| `bio: null` is present | Delete/clear bio (if the API allows) |
| `bio: ""` is present | Set bio to empty string |
| `bio: "   "` is present | Set to three spaces or reject per rule |

An object with only a `String bio` field sometimes cannot distinguish **absent** from **present but null** after deserialization. If the contract needs to distinguish them, the request model must carry both the **field present** state and its value, or use an update mechanism with well-defined semantics such as JSON Merge Patch. Do not assume `null` means "do not update" if the protocol defines `null` as "delete".

### 7.3. Do not convert null to empty across too many layers

If the HTTP binder, service, and repository each apply a different rule, data can change meaning between layers. Normalize at a **boundary with a clear contract**, then pass the validated value to subsequent layers under a documented invariant. For example, the service receives `displayName` already non-null and non-blank; the repository does not call `strip()` again using a different criterion.

## 8. Errors and how to notify the caller

A good API clearly states how it responds to invalid data:

- **Internal Java methods:** `Objects.requireNonNull` or manual checks; `IllegalArgumentException` for value violations; messages identifying the field name and requirement. Keep error types consistent within the same API group.
- **REST/HTTP:** an input validation error is typically mapped to a client-side error status (usually HTTP 400 or a code matching API conventions) with field, reason/code, and clear message. Do not expose secret data in errors or logs.
- **Validation on DTO/schema:** declare appropriate constraints (`non-null`, `non-empty`, `non-blank`) and ensure binder and validation configurations actually execute. In Jakarta Bean Validation, common annotations are `@NotNull`, `@NotEmpty`, and `@NotBlank`; these are **library dependencies**, not built-in Java SE 17 annotations.
- **Database:** check support for storing `NULL`/`""`, column constraints, and comparison rules. Some DBMSs handle empty strings differently; do not rely on assumptions across databases.

Do not return a generic "invalid" if the client needs to know which field failed. However, when a field holds a password, token, or sensitive data, messages and logs should not echo the entire input.

## 9. Designing tests from a state table

For a parameter, test cases should cover both **states** and **whitespace character variants**. Example for the `requireNonBlankName` contract:

| Input | Expected Result |
| --- | --- |
| `null` | `NullPointerException` per example contract |
| `""` | `IllegalArgumentException` |
| `"   "` | `IllegalArgumentException` |
| `"\t\n"` | `IllegalArgumentException` |
| `" A "` | Returns `"A"` |
| `"A B"` | Preserves internal whitespace, returns `"A B"` |
| `"\u2003A\u2003"` | Returns `"A"` |
| `"\u00A0"` | Not treated as blank by default `isBlank()`; requires a business decision |
| Overly long string | May be rejected if the contract sets a length limit |

If there is a length limit, state the **unit of measurement**: `String.length()` counts **UTF-16 code units**, not necessarily the number of Unicode code points or user-perceived characters. For example, a non-BMP emoji typically has `length() == 2` and `codePointCount(...) == 1`. Do not use one length criterion and interpret it as another.

Avoid writing tests that only prove `String.isBlank()` works as specified by the JDK; valuable tests verify the **business contract of the API**, including errors, normalization, and whitespace preservation behavior.

## 10. Common mistakes

1. **Calling `s.isBlank()` when `s` may be null.** The result is an unexpected `NullPointerException`. Check null first or establish a non-null invariant at the start of the method.
2. **Treating `isEmpty()` and `isBlank()` as identical.** `"  "` is not empty, yet it is blank.
3. **Treating null and empty string as the same.** This can lose the distinction between "not provided" and "provided as empty", especially in updates.
4. **Always stripping every input.** This can alter passwords, tokens, identifiers, signatures, or content meant to be preserved.
5. **Checking blank only and not using the normalized copy.** If the output must drop leading/trailing whitespace, you must return/store the result of `strip()`.
6. **Confusing `trim()` and `strip()`.** The two methods differ on certain Unicode whitespace; not all characters that look like spaces are removed by `strip()`.
7. **Automatically converting every blank to null without agreement.** This can discard data the user intentionally submitted.
8. **Defining null differently between Java services and HTTP/JSON.** A String parameter is not enough to express all field-present states; preserve presence state if needed.
9. **Assuming validation annotations work automatically.** `@NotBlank` requires a configured and executing framework/provider; Java SE does not enforce that constraint by itself.
10. **Returning inconsistent errors.** One API rejects null with NPE while another silently converts it to empty; users and integrating systems struggle to predict behavior.
11. **Ignoring special Unicode strings.** U+00A0, U+2003, zero-width characters, and normalization can produce unexpected results. Define the accepted character set if there are security or business requirements.
12. **Misunderstanding String size.** `length()` measures UTF-16 units; APIs regulating visible character counts should choose appropriate criteria and tests.

## 11. Self-check exercises

### Exercise 1 — Accurately classify four cases

Write `kind(String)` to classify `null` → `NULL`, `""` → `EMPTY`, `" \t"` → `BLANK`, `"x"` → `TEXT`. The solution is in the `StringInputPolicyDemo` program: check null first, followed by empty, then blank. If you check `isBlank` before `isEmpty`, the empty string will be grouped into BLANK and one state needing distinction will be lost.

### Exercise 2 — Design a tag input policy

Problem: a tag must have content after removing leading/trailing whitespace, be lowercased (for ASCII tags), and null is invalid.

```java
static String normalizeAsciiTag(String raw) {
    java.util.Objects.requireNonNull(raw, "tag must not be null");
    String tag = raw.strip();
    if (tag.isEmpty()) {
        throw new IllegalArgumentException("tag must not be blank");
    }
    return tag.toLowerCase(java.util.Locale.ROOT);
}
```

This is a method snippet. `Locale.ROOT` makes case conversion independent of the default locale, though it does not automatically guarantee correctness for all complex Unicode identifier rules. Only use lowercase normalization when the tag contract is truly case-insensitive.

### Exercise 3 — Empty data in PATCH

One request omits `nickname`, one request has `nickname: null`, and one request has `nickname: ""`. Design the meaning for each case before writing the DTO. Hint: "keep unchanged", "delete", and "set empty" is one way to distinguish them; if both null and empty mean delete, that must be a rule documented in the contract.

### Exercise 4 — Password with spaces

With `password = "  secret  "`, why can calling `strip()` before verifying the hash be wrong? Because it altered the data the user entered. An authentication system must use a published and consistent normalization rule from setup through verification, rather than silently dropping characters.

### Exercise 5 — Display field containing only Unicode whitespace

A form receives `"\u2003"` (EM SPACE) and `"\u00A0"` (NO-BREAK SPACE). `String.isBlank()` considers the first blank but does not consider the second blank. Explicitly decide whether the second case is allowed or needs a custom validator; the outcome cannot be inferred solely from "looks like whitespace".

## 12. Checklist when publishing an API

Before implementing a `String` parameter or field, check:

- Are **null**, **empty**, and **blank** allowed independently?
- Are **absent field** and **present field = null** distinguished in update operations?
- Are leading/trailing whitespace, internal spaces, and special Unicode characters kept or removed?
- Where is normalization performed, before or after validation, and what value is passed to the next layer?
- What error do invalid values produce, is it predictable, and does it leak sensitive data?
- Does the result have any invariants, such as "normalized, non-null, non-blank name"?
- Is maximum length measured in UTF-16 code units, Unicode code points, or another rule?
- Do examples, schemas, tests, and client documentation use the same policy?

**Conclusion:** `null`, `""`, and whitespace-only strings have distinct meanings. Java provides `isEmpty()`, `isBlank()`, `trim()`, `strip()`, and `Objects.requireNonNull()`, but **the API itself must decide when to reject, normalize, or preserve**. Writing a clear contract helps callers accurately predict what data is accepted, stored, and returned, especially with Unicode, partial updates, and multi-layered systems.

**References:** [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — Character.isWhitespace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#isWhitespace(int)), [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)), [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).