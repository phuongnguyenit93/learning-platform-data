# Distinguishing Empty Strings, Blank Strings, and `null` in Java 17+

When receiving usernames, notes, or form data, three cases are frequently confused: **`null`**, **empty string `""`**, and **whitespace-only strings**. They carry different meanings, and choosing properly among `isEmpty()`, `isBlank()`, `trim()`, and `strip()` determines whether a program handles input correctly or not.

- **`null`**: the `String` reference variable does not point to any object.
- **Empty string `""`**: a `String` object exists, but its length is **0**.
- **Blank string**: may be empty or contain only characters that Java considers **whitespace** according to `Character.isWhitespace`. Examples include `"   "`, `"\t"`, and `"\n"`. A blank string **does not necessarily have length 0**.

## 1. Exact comparison table

Suppose variable `s` holds the value in the first column:

| Value of `s` | `s == null` | `s.isEmpty()` | `s.isBlank()` | Why |
| --- | --- | --- | --- | --- |
| `null` | `true` | **Throws `NullPointerException`** | **Throws `NullPointerException`** | No String object exists |
| `""` | `false` | `true` | `true` | Empty is also considered blank |
| `" "` | `false` | `false` | `true` | Contains one space |
| `" \t\n"` | `false` | `false` | `true` | Contains only space, tab, newline |
| `"\u2003"` (EM SPACE) | `false` | `false` | `true` | EM SPACE is recognized by `Character.isWhitespace` |
| `"\u00A0"` (NBSP) | `false` | `false` | `false` | Non-breaking space is **not** considered whitespace by `Character.isWhitespace` |
| `"Java"` | `false` | `false` | `false` | Contains letters |
| `" Java "` | `false` | `false` | `false` | Contains letters despite spaces on both sides |

**Key point:** `isBlank()` encompasses empty strings as well; whereas `isEmpty()` only checks `length() == 0`. Both are instance methods, so **neither can be called directly on `null`**.

## 2. Runnable Java 17+ program

Save a UTF-8 file named **`EmptyBlankNullDemo.java`**:

~~~java
public class EmptyBlankNullDemo {
    static String classify(String value) {
        if (value == null) {
            return "NULL";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "TEXT";
    }

    public static void main(String[] args) {
        String[] labels = {
                "null", "empty", "spaces", "mixed",
                "emSpace", "nbsp", "word", "padded"
        };

        String[] values = {
                null, "", "   ", " \t\n",
                "\u2003", "\u00A0", "Java", " Java "
        };

        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            String size = value == null
                    ? "N/A"
                    : Integer.toString(value.length());

            System.out.println(labels[i]
                    + "=" + classify(value)
                    + ",length=" + size);
        }

        String padded = "  Java  ";
        System.out.println("trimAscii=" + padded.trim());
        System.out.println("stripAscii=" + padded.strip());

        String unicodePadded = "\u2003Java\u2003";
        System.out.println("trimUnicodeLength="
                + unicodePadded.trim().length());
        System.out.println("stripUnicodeLength="
                + unicodePadded.strip().length());

        String maybeNull = null;
        System.out.println("safeMissing="
                + (maybeNull == null || maybeNull.isBlank()));

        String onlySpace = "   ";
        String normalized = onlySpace.isBlank()
                ? "(missing)"
                : onlySpace.strip();
        System.out.println("normalized=" + normalized);
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file, using **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EmptyBlankNullDemo.java
java EmptyBlankNullDemo
~~~

**Exact expected output of the program:**

~~~text
null=NULL,length=N/A
empty=EMPTY,length=0
spaces=BLANK,length=3
mixed=BLANK,length=3
emSpace=BLANK,length=1
nbsp=TEXT,length=1
word=TEXT,length=4
padded=TEXT,length=6
trimAscii=Java
stripAscii=Java
trimUnicodeLength=6
stripUnicodeLength=4
safeMissing=true
normalized=(missing)
~~~

**Explanation:** the `classify` method must check for `null` **before** calling methods. For non-null values, it distinguishes empty strings from strings containing whitespace. `String.isBlank()` was introduced in Java 11, so it is available in Java 17. `"\u2003"` is an EM SPACE: `strip()` removes it whereas `trim()` does not. `"\u00A0"` is NBSP, so `isBlank()` returns false.

The code verifies results using labels instead of printing strings containing tabs or spaces directly, letting you clearly see the differences in the terminal.

## 3. Which check should you choose for your business requirement?

### A. Want to check “no object”

~~~java
String input = null;

if (input == null) {
    System.out.println("Not provided");
}
~~~

`null` usually means **not provided**, **not yet available**, or a special state defined by the API design. Do not automatically treat `null` and `""` as identical if the API needs to distinguish “not answered” from “answered empty”.

### B. Want to check “exactly 0 code units”

~~~java
String input = " ";

System.out.println(input.isEmpty()); // false
System.out.println(input.length());  // 1
~~~

`isEmpty()` is appropriate when **even a space is valid data**, such as edited text content or passwords whose requirement is non-zero length. `isEmpty()` does not ignore whitespace.

### C. Want to check “no useful content beyond whitespace”

~~~java
String input = " \t";

if (input != null && !input.isBlank()) {
    System.out.println("Has content");
} else {
    System.out.println("Missing content");
}
~~~

This is usually the right choice for **display names**, **notes**, or **descriptions** where entering only spaces/tabs/newlines counts as missing content. However, the whitespace scope of `isBlank()` does not cover **every** character a human eye perceives as blank space (for example, NBSP).

### D. Combining `null` and blank into the same status

~~~java
static boolean isMissing(String s) {
    return s == null || s.isBlank();
}
~~~

The `||` operator uses **short-circuiting**: if `s == null` is true, the `s.isBlank()` side will not execute, avoiding `NullPointerException`. Never swap the order of the two conditions.

## 4. How does `trim()` differ from `strip()`?

Both produce a result **string with leading and trailing characters removed**, without modifying the original `String` object.

| Method | Rule | Scenario |
| --- | --- | --- |
| `trim()` | Removes leading/trailing characters with code value `<= U+0020` | Older behavior, limited with Unicode |
| `strip()` | Removes leading/trailing whitespace per `Character.isWhitespace` | Usually more suitable for certain Unicode spaces |
| `stripLeading()` | Removes **leading** whitespace only | Preserves trailing part |
| `stripTrailing()` | Removes **trailing** whitespace only | Preserves leading part |

`strip()`, `stripLeading()`, and `stripTrailing()` have existed since Java 11. Example:

~~~java
String raw = "  Java  ";
String clean = raw.strip();

System.out.println(raw.length());   // 8
System.out.println(clean.length()); // 4
~~~

`raw` does not change. If you want to store the result in the variable in use, write `raw = raw.strip();` (when the variable is not `final`).

**Unicode note:** `strip()`/`isBlank()` rely on `Character.isWhitespace`, so some *non-breaking* spaces like U+00A0 are retained. If the application should treat those characters as empty/blank, define the exact set of characters to handle and add explicit rules rather than assuming every visible space is recognized by `isBlank()`.

## 5. Common mistakes

| Code / statement | Problem | Fix |
| --- | --- | --- |
| `text.isEmpty()` when `text == null` | `NullPointerException` | Check `null` first |
| `"".equals(text)` and `text == null` are the same | False: one compares content with empty string, the other compares with null | Choose according to data semantics |
| `text.isEmpty()` considers `"   "` empty | False: length is non-zero | Use `isBlank()` if needed |
| `text.isBlank()` is only true when length > 0 | False: `"".isBlank()` is also true | If you want three separate states, check `isEmpty()` before `isBlank()` |
| `text.trim();` mutates `text` automatically | False: `String` is immutable | Reassign `text = text.trim();` |
| `strip()` removes all Unicode whitespace | False, excludes some non-breaking spaces | Define the application's whitespace policy |
| `text == ""` to check empty | `==` compares references | Use `text.isEmpty()` after checking null |
| `isBlank()` is always available in Java 8 | False: since Java 11 | Available in Java 17+ |

### Null-safe comparison with accurate meaning

~~~java
String text = null;
System.out.println("".equals(text)); // false
System.out.println(text == null);     // true
~~~

`"".equals(text)` does not throw an error because the target object is the literal `""`, which is guaranteed non-null, yet this expression only checks for **empty string** content and does not replace a `null` check.

`java.util.Objects.toString(text, "")` can intentionally convert null to an empty string; however, such normalization **loses the distinction** between the two states. Do this only when product requirements truly intend to merge them.

## 6. Clean and safe input processing flow

If the business rule is “strip leading and trailing whitespace, and discard empty or blank values”, you can write:

~~~java
static String normalizeName(String input) {
    if (input == null || input.isBlank()) {
        return null;
    }

    String cleaned = input.strip();
    return cleaned.isEmpty() ? null : cleaned;
}
~~~

This is only an **example policy**: returning `null` to indicate “no name”. In a real system, you might instead choose to return `""`, `Optional<String>`, or raise a validation error, depending on the API contract. Do not automatically `strip()` data where leading/trailing whitespace is meaningful, such as source code content or text whose formatting must be preserved.

Note: the function above treats a lone NBSP as content (`isBlank() == false`, and `strip()` preserves it too). If that is not the desired behavior, design an explicit cleaning rule rather than relying on the default.

## 7. Self-check exercises

1. **Classification:** Which group do `null`, `""`, `" \t"`, and `"x"` belong to respectively?  
   *Answer:* null, empty, blank, text.
2. **Prediction:** What are `"".isEmpty()`, `"".isBlank()`, and `" ".isEmpty()` respectively?  
   *Answer:* `true`, `true`, `false`.
3. **Safety:** Why does `s == null || s.isBlank()` not throw an error when `s == null`?  
   *Answer:* `||` short-circuits if the left-hand side is true.
4. **Unicode:** Why is `"\u2003".isBlank()` true whereas `"\u00A0".isBlank()` is false?  
   *Answer:* `Character.isWhitespace` considers EM SPACE whitespace but does not consider NBSP whitespace.
5. **Data modification:** Given `String s = "  A  "; s.strip();`, after those two statements, what is `s.length()`?  
   *Answer:* 5, because the result of `strip()` was not reassigned.

## Key takeaways

- `null`: no object; check with `== null`.
- `""`: empty string with `length() == 0`; `isEmpty() == true`.
- Blank string: empty **or** contains only whitespace per `Character.isWhitespace`; `isBlank() == true`.
- `isBlank()` differs from `isEmpty()`, and **does not** handle `null` automatically.
- `trim()`/`strip()` return a new or equivalent result, **without modifying the old `String`**.
- For Unicode non-breaking spaces, establish clear business rules rather than assuming every whitespace character will be removed by `strip()`.

**Conclusion:** Before validating input, decide whether **“missing data” means `null`, empty, blank, or which combination?** Then apply `== null`, `isEmpty()`, and `isBlank()` according to that semantics. This avoids `NullPointerException` errors and prevents accidentally discarding information.
