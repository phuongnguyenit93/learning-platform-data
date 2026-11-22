# Empty Strings, Blank Strings, `null`, and the `"null"` String in Java

In Java, a `String` variable may refer to no object (`null`), refer to a string with zero characters (`""`), to a string containing only whitespace (`"   "`), or to a four-letter string `"null"`. These are four distinct cases in terms of **data and handling**. Distinguishing them properly helps validate input, design APIs, handle configuration, and write accurate logs.

## 1. Understanding each case

### 1.1. The `null` reference: no `String` object

`null` is a special literal indicating that a reference variable does not yet point to an object. It **is not a string**.

```java
String name = null;
System.out.println(name == null); // true
// name.length(); // NullPointerException if executed
```

The expression `name == null` checks the reference state. You cannot directly call `length()`, `isEmpty()`, `isBlank()`, or `strip()` on a `null` reference.

### 1.2. Empty string `""`: object exists, length is 0

```java
String empty = "";
System.out.println(empty.length());  // 0
System.out.println(empty.isEmpty()); // true
System.out.println(empty.isBlank()); // true
```

`""` is a valid string value containing no characters. It is different from `null`. An empty string is also considered blank by `isBlank()` because it contains no non-whitespace characters.

### 1.3. Blank string: consists only of whitespace characters

Examples include `" "`, `"   "`, `"\t"`, `"\n"`, or `" \t\n "`. They contain actual characters, so they are generally **not empty**, but `isBlank()` returns `true` if every character is recognized by Java as whitespace.

```java
String spaces = " \t";
System.out.println(spaces.length());  // 2
System.out.println(spaces.isEmpty()); // false
System.out.println(spaces.isBlank()); // true
```

Note: “Looking like whitespace” is not synonymous with `Character.isWhitespace`. For example, NO-BREAK SPACE (`\u00A0`) is not considered whitespace by `String.isBlank()`, whereas EM SPACE (`\u2003`) is considered whitespace. Therefore, checking for blank is not a universal check for all invisible characters or all Unicode space characters.

### 1.4. The string `"null"`: four ordinary characters

```java
String word = "null";
System.out.println(word == null);       // false
System.out.println(word.length());      // 4
System.out.println(word.isBlank());     // false
System.out.println("null".equals(word)); // true
```

This is text consisting of `'n'`, `'u'`, `'l'`, `'l'`. Java does not automatically convert the string `"null"` into a `null` reference. Likewise, `"NULL"` or `" Null "` are strings distinct from `"null"` when compared with `equals`.

## 2. Quick comparison table

The rows below show independent states of the variable `s`; the “equals text null” column uses `"null".equals(s)`.

| Value of `s` | `s == null` | `s != null && s.isEmpty()` | `s != null && s.isBlank()` | `"null".equals(s)` |
| --- | --- | --- | --- | --- |
| `null` | `true` | `false` | `false` | `false` |
| `""` | `false` | `true` | `true` | `false` |
| `" \t"` | `false` | `false` | `true` | `false` |
| `"null"` | `false` | `false` | `false` | `true` |
| `"Java"` | `false` | `false` | `false` | `false` |

**Key takeaway:** `isEmpty()` only checks for length 0; `isBlank()` accepts both length 0 and strings consisting solely of whitespace. Both need protection against `null`.

## 3. APIs you need to know

| Tool | Question answered | Characteristics |
| --- | --- | --- |
| `s == null` | Is the string object missing? | Safe even when `s` is `null` |
| `s.isEmpty()` | Does it have exactly 0 characters? | `NullPointerException` when `s == null` |
| `s.isBlank()` | Is it empty or whitespace-only? | Available since Java 11; `NullPointerException` when `s == null` |
| `s.trim()` | Remove leading/trailing characters with code ≤ U+0020? | Legacy rule, not equivalent to all Unicode whitespace |
| `s.strip()` | Remove leading/trailing whitespace per `Character.isWhitespace`? | Available since Java 11; generally more suitable than `trim()` when Unicode matters |
| `"null".equals(s)` | Is the value literally the text `"null"`? | Safe when `s == null`; case-sensitive |
| `Objects.equals(s, "null")` | Are two values equal, including `null`? | Null-safe comparison, requires `java.util.Objects` |

Use the `||` operator with *short-circuit* evaluation to avoid calling methods on `null`:

```java
boolean missingOrBlank = s == null || s.isBlank();
boolean hasText = s != null && !s.isBlank();
```

These two lines are **illustrative snippets** assuming a `String s` variable already exists. The first checks for “no useful text” according to `isBlank`; the second checks for at least one non-whitespace character. If business logic needs to distinguish “field omitted” from “empty field sent,” do not collapse those states into a single condition.

## 4. Compilable and runnable Java 17 example

Save the following content into `StringStates.java`:

```java
public class StringStates {
    private static void show(String label, String s) {
        System.out.printf(
                "%s -> null=%b, empty=%b, blank=%b, textNull=%b%n",
                label,
                s == null,
                s != null && s.isEmpty(),
                s != null && s.isBlank(),
                "null".equals(s)
        );
    }

    public static void main(String[] args) {
        show("missing", null);
        show("empty", "");
        show("blank", " \t");
        show("literal", "null");
        show("normal", "Java");

        String emSpace = "\u2003";
        String nbsp = "\u00A0";
        System.out.printf(
                "EM SPACE -> blank=%b, trimLength=%d, stripLength=%d%n",
                emSpace.isBlank(),
                emSpace.trim().length(),
                emSpace.strip().length()
        );
        System.out.printf(
                "NBSP -> blank=%b, stripLength=%d%n",
                nbsp.isBlank(),
                nbsp.strip().length()
        );
    }
}
```

Compile and run with JDK 17+:

```bash
javac StringStates.java
java StringStates
```

Expected output:

```text
missing -> null=true, empty=false, blank=false, textNull=false
empty -> null=false, empty=true, blank=true, textNull=false
blank -> null=false, empty=false, blank=true, textNull=false
literal -> null=false, empty=false, blank=false, textNull=true
normal -> null=false, empty=false, blank=false, textNull=false
EM SPACE -> blank=true, trimLength=1, stripLength=0
NBSP -> blank=false, stripLength=1
```

Here the `s != null && ...` conditions guard the method calls. `EM SPACE` demonstrates that `strip()` handles Unicode whitespace differently from `trim()`. `NBSP` demonstrates that `isBlank()` does not automatically recognize every character that looks like a space.

## 5. Application: classifying input data without losing meaning

Suppose a text field is received from an API or a form:

- `null`: may mean “not provided,” depending on the API contract.
- `""`: a string value was supplied with length 0; may indicate an intent to clear the data.
- `"   "`: characters were sent, but there is no meaningful text content.
- `"null"`: may be text the user genuinely intended to enter; **do not automatically treat it as missing data**.
- `"  Minh  "`: contains text with leading/trailing spaces; may need normalization before saving.

You can use the following classification method **inside a Java class**:

```java
enum TextKind { MISSING, EMPTY, BLANK, LITERAL_NULL, TEXT }

static TextKind classify(String s) {
    if (s == null) {
        return TextKind.MISSING;
    }
    if (s.isEmpty()) {
        return TextKind.EMPTY;
    }
    if (s.isBlank()) {
        return TextKind.BLANK;
    }
    if ("null".equals(s)) {
        return TextKind.LITERAL_NULL;
    }
    return TextKind.TEXT;
}
```

**The order of checks matters:** an empty string is also blank according to `isBlank()`, so `isEmpty()` must be checked first if you want to separate the two categories. Checking for the literal `"null"` is only useful when the problem requires explicitly identifying that exact text; do not turn it into a default rule for discarding data.

If business logic **intentionally decides** that all missing/empty/blank strings should be represented as `null`, you can use the following method snippet (placed inside a class):

```java
static String normalizeOptionalText(String s) {
    if (s == null) {
        return null;
    }
    String stripped = s.strip();
    return stripped.isEmpty() ? null : stripped;
}
```

For example: `normalizeOptionalText(null)`, `normalizeOptionalText("")`, and `normalizeOptionalText("  \t ")` all return `null`; `normalizeOptionalText("  Java  ")` returns `"Java"`; `normalizeOptionalText("null")` still returns `"null"`. This is a **business-driven choice**: do not use it when you must preserve the distinction between an absent field, an empty field, and a whitespace-only field. The method also follows `strip()`'s Unicode rules, so NBSP is not automatically removed.

## 6. Why can logging or type conversion cause confusion?

Java can produce the **string** `"null"` from a `null` reference during string concatenation or text conversion:

```java
String absent = null;
String literal = "null";

System.out.println("value=" + absent);                 // value=null
System.out.println("value=" + literal);                // value=null
System.out.println(String.valueOf((Object) absent));   // null
System.out.println(java.util.Objects.toString(absent, "<missing>")); // <missing>
```

The first two lines produce identical output, even though the inputs differ. `String.valueOf((Object) absent)` returns the string `"null"` (not a `null` reference). Casting to `(Object)` in the example clarifies which overload is intended, avoiding confusion with overloads such as `valueOf(char[])`. To distinguish them in logs, log the state explicitly (`absent == null`) or use a consistent placeholder like `"<missing>"`. When transferring data via JSON, keep the distinction clear between a `null` value, the string `"null"`, the string `""`, and an omitted property according to the data contract.

## 7. Common mistakes

1. **Calling methods directly on `null`:** `s.isEmpty()`, `s.isBlank()`, and `s.trim()` cause `NullPointerException` if `s == null`. Check the reference before calling.
2. **Using `isEmpty()` to reject blank strings:** `"   ".isEmpty()` returns `false`. To reject whitespace-only input, use `isBlank()` on a non-null value.
3. **Using `s.equals("null")` when `s` can be `null`:** change it to `"null".equals(s)` or `Objects.equals(s, "null")`.
4. **Comparing strings with `==`:** `==` compares object references (aside from checking against `null`), not text content; use `equals` for content. Do not rely on the string pool for checks.
5. **Using `trim().isEmpty()` assuming it is identical to `isBlank()`:** they have different whitespace rules; Unicode cases yield different results.
6. **Automatically treating the text `"null"` as missing data:** only convert it when there is an explicit convention; otherwise you will lose valid user text.
7. **Normalizing too early:** collapsing all states into `null` or `""` can lose the information distinguishing “not sent,” “cleared,” and “whitespace-only.”

## 8. Choosing the right condition for your requirement

| Requirement | Condition or approach |
| --- | --- |
| Detect only a missing reference | `s == null` |
| Detect only a string with exactly 0 characters | `s != null && s.isEmpty()` |
| Detect a blank string, including empty (excluding `null`) | `s != null && s.isBlank()` |
| Detect `null` or an empty string | `s == null || s.isEmpty()` |
| Detect `null` or a blank string | `s == null || s.isBlank()` |
| Detect the exact text `"null"` | `"null".equals(s)` |
| Need to preserve all four states separately | Check in order: `null` → `isEmpty()` → `isBlank()` → `"null".equals(s)` |
| Want to strip leading/trailing whitespace in Java 11+ | `s == null ? null : s.strip()`; consider Unicode rules |

**Self-check:** Predict `isEmpty()` and `isBlank()` for `""`, `"  "`, and `"abc"`; then test `null`, `"null"`, and the `\u00A0` character. If a result surprises you, check first whether you are thinking about the **reference**, the **length**, **Java's whitespace definition**, or the **text content**.