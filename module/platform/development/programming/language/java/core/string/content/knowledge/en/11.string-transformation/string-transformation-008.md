# Keeping the Original String When Needed for Comparison or Redisplay

When transforming text content in Java, keeping the **original string** and creating a separate **transformed value** is an important design practice. The original data may be needed to display exactly what the user entered, compare against the processed version, explain validation errors, undo edits, or satisfy business rules. Meanwhile, the transformed version is convenient for searching, comparing, categorizing, or normalizing.

**Main point:** String is *immutable*. Methods such as strip(), trim(), replace(), toLowerCase(), toUpperCase(), and concatenation create/return a resulting String value without altering the original String object's content. However, if a programmer **overwrites the reference variable** or persists only the normalized version, the application can still **lose access to the original data**.

## 1. Distinguishing Immutable String Content from the Variable Pointing to It

Consider the following Java snippet:

~~~java
String original = "  Java  ";
String cleaned = original.strip();

System.out.println("original=[" + original + "]");
System.out.println("cleaned=[" + cleaned + "]");
~~~

Output:

~~~text
original=[  Java  ]
cleaned=[Java]
~~~

Calling strip() does not delete the two leading and trailing spaces from the original object. It returns a String representing the content with edge whitespace removed. The cleaned variable holds the result, while original retains the old value.

What often causes confusion:

~~~java
String text = "  Java  ";
text = text.strip();

System.out.println("[" + text + "]"); // [Java]
~~~

The original String object remains immutable, but text now points to the stripped result. If no other useful reference points to the input content, the program cannot recover exactly what the user entered from text. **Immutability does not mean the application automatically keeps history.**

You can keep the original using another variable:

~~~java
String original = textFromUser;
String normalized = original == null ? null : original.strip();
~~~

This is an **illustrative snippet**, assuming textFromUser has already been declared. In Java, original and normalized are merely references to String values; keeping two variables does not force duplicating the underlying object.

## 2. When Must You Keep the Original Data?

| Scenario | Role of the original version | Role of the transformed version |
|---|---|---|
| Display name input box | Preserves capitalization, spaces, or diacritics per UI requirements | Creates a search key or whitespace-trimmed version |
| Case-insensitive search | Displays verbatim text | Uses a consistently normalized string for searching |
| Data validation and error reporting | Shows which input was invalid | Passes data through processing or comparison steps |
| Importing data from files or APIs | Supports auditing or discrepancy detection if retention policy allows | Produces the required internal format |
| Text editing with an "Undo" feature | Stores the version prior to transformation | Uses the current version for display or processing |
| Identifiers or values under strict rules | Preserves exact bytes/characters per contract, when needed | Normalizes only when permitted by the system |
| Analyzing Unicode differences | Distinguishes the representation submitted by the user | Applies Unicode normalization for matching as required |

Keeping original data **does not mean storing every string indefinitely**. For passwords, tokens, personal information, or sensitive data, keeping multiple copies can increase risk. Retain the original only with an appropriate purpose, retention period, and access control; never dump raw sensitive data into logs just to "make comparison easy."

## 3. Using Variable Names or a `record` to Clearly Express Both Purposes

For small logic, two clearly named variables are usually enough:

~~~java
String rawTitle = "  Java Basics  ";
String displayTitle = rawTitle.strip();

System.out.println("raw=[" + rawTitle + "]");       // [  Java Basics  ]
System.out.println("display=[" + displayTitle + "]"); // [Java Basics]
~~~

When data flows through multiple application layers, you can use a Java 17 **record** to group representations into one structured value, such as raw, display, and searchKey. This helps receiving methods know which version they are operating on.

| Field | Meaning |
|---|---|
| original / raw | Input data preserved untouched per contract |
| display | Value used for presentation, possibly with edge whitespace stripped if business rules allow |
| searchKey | Normalized value used for lookup, typically not displayed in place of the original |
| validationMessage | Input evaluation outcome, kept separate from the input string itself |

Not every program needs to keep all three versions. Determine which versions are needed from business requirements and name them so searchKey is never accidentally passed where verbatim display is expected.

### Complete Java 17+ Program: `original`, `display`, and `searchKey`

Save the file **KeepOriginalStringDemo.java**:

~~~java
import java.util.Locale;

public class KeepOriginalStringDemo {
    record TextVersions(String original, String display, String searchKey) {}

    static TextVersions prepare(String input) {
        if (input == null) {
            return new TextVersions(null, null, null);
        }

        String display = input.strip();
        String searchKey = display.toLowerCase(Locale.ROOT);
        return new TextVersions(input, display, searchKey);
    }

    public static void main(String[] args) {
        String received = "  Hello  JAVA  ";
        TextVersions versions = prepare(received);

        System.out.println("original=[" + versions.original() + "]");
        System.out.println("display=[" + versions.display() + "]");
        System.out.println("searchKey=[" + versions.searchKey() + "]");

        System.out.println("originalLength=" + versions.original().length());
        System.out.println("displayLength=" + versions.display().length());
        System.out.println("originalUnchanged="
                + received.equals(versions.original()));

        TextVersions missing = prepare(null);
        System.out.println("missing=" + (missing.original() == null));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac KeepOriginalStringDemo.java
java KeepOriginalStringDemo
~~~

Exact output:

~~~text
original=[  Hello  JAVA  ]
display=[Hello  JAVA]
searchKey=[hello  java]
originalLength=15
displayLength=11
originalUnchanged=true
missing=true
~~~

In the example:

1. original keeps all **two leading spaces, two spaces between Hello and JAVA, and two trailing spaces**.
2. display only removes edge whitespace. strip() does not automatically delete the two spaces in the middle.
3. searchKey converts display content to lowercase using Locale.ROOT, appropriate when the application has **chosen** a locale-independent lookup policy.
4. Calling prepare(null) does not invoke instance methods on null. From here, the application can distinguish "no text" from an empty String.
5. Keeping these values does not turn normalization into a reversible transformation. If only searchKey is stored, the exact capitalization and whitespace of original cannot be recovered.

**Note on Locale.ROOT:** it avoids depending on the machine's default locale when building technical keys. However, case conversion can still change length or character relationships in certain Unicode cases; natural-language comparison needs its own rules rather than assuming toLowerCase() works for every locale.

## 4. Do Not Overwrite Input When Comparison Is Needed

The following snippet easily loses context:

~~~java
String input = "  AbC  ";
input = input.strip();
input = input.toLowerCase(java.util.Locale.ROOT);
System.out.println(input); // abc
~~~

Each transformation is valid and does not mutate the old String object. The issue is that the name input no longer accurately describes **the value currently held**: the initial string with whitespace and uppercase letters is no longer accessible through input.

Writing each step explicitly makes verification easy:

~~~java
String rawInput = "  AbC  ";
String trimmedInput = rawInput.strip();
String lookupInput = trimmedInput.toLowerCase(java.util.Locale.ROOT);

System.out.println("raw=[" + rawInput + "]");         // [  AbC  ]
System.out.println("trimmed=[" + trimmedInput + "]"); // [AbC]
System.out.println("lookup=[" + lookupInput + "]");   // [abc]
~~~

raw stays intact, and each derived version has a clear purpose. If search results look wrong, you can tell whether the cause lies in the original content, the strip rule, or the lowercasing rule, provided the system lets you inspect those corresponding versions.

Another point to remember: **a final variable does not make strip an in-place mutation**. You can write:

~~~java
final String original = "  AbC  ";
final String key = original.strip().toLowerCase(java.util.Locale.ROOT);
~~~

Both variables hold stable references, and String objects were already immutable to begin with. final mainly reduces the chance of accidentally reassigning those variables.

## 5. When Comparing, Define What "Equal" Means

There is no single comparison rule for every scenario. Two versions may be equal by **exact content** yet differ under a normalization rule, or vice versa.

| Goal | How to check | Meaning |
|---|---|---|
| Exact comparison of two Strings | original.equals(other) when receiver is non-null | Compares UTF-16 code unit sequences, sensitive to case and whitespace |
| Comparing two potentially null Strings | java.util.Objects.equals(a, b) | null/null is considered equal; null/empty string remains unequal |
| Ignore edge whitespace then compare | a.strip().equals(b.strip()), after null-check | Appropriate only when business rules treat edge whitespace as insignificant |
| Compare after Unicode normalization | Normalizer.normalize(a, Form.NFC).equals(Normalizer.normalize(b, Form.NFC)) | Unifies canonically equivalent Unicode forms under NFC |
| Case-insensitive comparison | Appropriate case-folding/collation policy | Not simply discarding all linguistic differences |

String.equals() **does not automatically call strip(), trim(), normalize(), or toLowerCase()**. If you want comparison under a normalization rule, perform that step deliberately while keeping the original when needed.

### Unicode Example: Visually Identical Text with Different Codes

`"Caf\u00E9"` has the precomposed `é` character, whereas `"Cafe\u0301"` consists of `e` and a combining acute accent. `String.equals()` distinguishes the two code sequences; if business rules treat them as canonically equivalent, normalize consistently to NFC; in the example, `composed` is already in NFC form:

~~~java
String original = "Cafe\u0301";
String composed = "Caf\u00E9";
String normalized = java.text.Normalizer.normalize(
        original, java.text.Normalizer.Form.NFC);
System.out.println(original.equals(composed));   // false
System.out.println(normalized.equals(composed)); // true
System.out.println(original.length());           // 5
System.out.println(normalized.length());         // 4
~~~

`Normalizer` returns a new value without modifying `original`. When storing only the NFC version, you cannot reliably reconstruct the exact representation the user entered. This example directly illustrates why keeping both **raw** and a **comparison** version matters; the previous lesson on data preservation explains reversibility and collisions in detail.

## 6. Notes on `trim()`, `strip()`, `replace()`, and Redisplay Representation

Common transformations can discard information that matters for redisplay:

- **strip()** removes leading/trailing whitespace per Java's Character.isWhitespace. For a string containing only whitespace from this set, it can return an empty String.
- **trim()** removes code units at both ends with value <= U+0020; the removed set differs from strip().
- **replace()** substitutes content per specified rules; the result does not show exactly which parts were replaced unless original information is kept.
- **toLowerCase()/toUpperCase()** can change capitalization, and even the number of code units in some cases.
- **Normalizer.normalize()** can change the Unicode representation while keeping a similar visual appearance.

For example, when a user enters identifier **" AB-01 "**, if the system stores **"AB-01"** after strip(), it can no longer tell afterward whether the user typed one or several spaces at either end. That may not matter for searching, yet it can matter when investigating input mistakes, showing drafts, or supporting undo.

### Redisplaying the Original Means Preserving Content, Not Bypassing Output Safety

When rendering user-provided text in HTML, terminals, CSV, or logs, each environment has its own escaping rules. **Keeping the original does not mean concatenating unescaped content straight into HTML or SQL statements.** You can preserve original in your data model, and then use safe UI rendering, parameterized SQL queries, or proper formatters when exporting data.

Likewise, never log verbatim tokens, passwords, or personal data just for comparison. Check retention requirements and log only what is genuinely necessary.

## 7. `StringBuilder` and Mutable Buffers: Different from Keeping an Original `String`

Immutable Strings let you hold two references to the same object without worrying that calling replace()/strip() will mutate the original object:

~~~java
String a = "Java";
String b = a;

a = a.concat(" 17");

System.out.println(a); // Java 17
System.out.println(b); // Java
~~~

With **StringBuilder**, two variables can point to the same mutable object:

~~~java
StringBuilder first = new StringBuilder("Java");
StringBuilder second = first;

first.append(" 17");

System.out.println(first);  // Java 17
System.out.println(second); // Java 17
~~~

Therefore, keeping an extra **reference** to a StringBuilder **is not** keeping a snapshot of its content. If you are building text with StringBuilder and need to keep a stable version, call toString() at the point where you want the snapshot:

~~~java
StringBuilder draft = new StringBuilder("version 1");
String snapshot = draft.toString();

draft.replace(0, draft.length(), "version 2");

System.out.println(snapshot); // version 1
System.out.println(draft);    // version 2
~~~

String snapshot holds an immutable value; subsequent changes in builder do not affect snapshot.

However, **do not assume a String always suffices to reconstruct raw byte input verbatim**. If source data is a UTF-8 file, decoding, newline normalization, or malformed-character replacement can prevent a String from restoring the original bytes. When byte-level auditing is required, preserve the source bytes with an appropriate mechanism independent of the String used for text manipulation.

## 8. Auditable Input-Processing Workflow

A processing pipeline is usually easier to maintain when split into clear stages:

1. **Receive input:** determine whether data can be null and whether exact space counts, newlines, and Unicode representations must be preserved.
2. **Keep raw:** store only within required scope, with appropriate security policies and retention periods.
3. **Transform into new variables:** call strip(), replace(), normalize(), or case conversion per rules without overwriting raw if comparison is still needed.
4. **Validate:** validate raw, the transformed version, or both depending on business contracts; for example, login codes may require strict original syntax.
5. **Use the right version:** raw for comparison/audit, display for presentation, searchKey for search. Never accidentally substitute searchKey for raw in a "redisplay" feature.
6. **Clarify storage permissions:** avoid keeping extra copies of sensitive data unnecessarily.

Example helper accepting potentially null input:

~~~java
record DisplayValue(String original, String visible) {}

static DisplayValue prepareDisplay(String value) {
    if (value == null) {
        return new DisplayValue(null, null);
    }
    return new DisplayValue(value, value.strip());
}
~~~

This is an **illustrative code snippet**, which must be placed inside a Java class. It distinguishes null from an empty string and keeps both raw and stripped versions. A dedicated record avoids putting two versions in separate variables that can easily be mixed up across method calls.

Another design is keeping raw in an immutable object and **computing the normalized version on demand**, instead of storing every version. The choice depends on access frequency, normalization cost, policy stability, and storage requirements. What matters is that raw remains accessible when business logic genuinely needs it.

## 9. Common Mistakes

1. **Thinking String is modified in place:** calling raw.strip() or raw.replace() does not alter raw; use the return value for the transformed version.
2. **Overwriting the variable before saving raw:** text = text.strip() is valid, yet loses the original reference through text; if comparison is needed, keep rawInput and normalizedInput separate.
3. **Assuming two different String references must be unequal:** use equals() to compare content rather than ==. Two versions with identical content may be the same or different objects.
4. **Automatically stripping all inputs:** whitespace can be data that must be preserved, especially for passwords, free-form text, or formatted strings.
5. **Using searchKey for display:** normalizing for search can drop capitalization, diacritics, or original formatting; display from the original/display version per policy.
6. **Thinking Unicode normalization always keeps length() unchanged:** NFC can compose a code point sequence into another representation; e.g., "Cafe\u0301" and "Café".
7. **Skipping null checks:** raw.strip() when raw is null causes NullPointerException. Check for null before any instance call.
8. **Keeping a StringBuilder reference as a snapshot:** builder is mutable; to snapshot text, call toString().
9. **Confusing keeping a String with keeping source bytes:** String is a decoded text representation; byte-exact file recovery requires retaining the original bytes.
10. **Logging all raw inputs automatically:** storing raw data can increase exposure of sensitive data; retain only for the duration and scope genuinely required.
11. **Assuming every search case uses the same normalization rules:** Locale.ROOT and NFC are common choices for technical keys, yet do not replace proper language/collation policies.
12. **Mixing raw and normalized versions inconsistently in comparisons:** when policy requires normalization, both sides must follow the same explicit pipeline.

## 10. Self-Check Questions

Given:

~~~java
String raw = "  JaVa  ";
String display = raw.strip();
String key = display.toLowerCase(java.util.Locale.ROOT);
~~~

Predict:

1. What are the contents of raw and display respectively?
2. What are raw.length() and display.length()?
3. What does raw.equals(display) return? Why?
4. What is the content of key? If only key is stored, can you reliably know the capitalization of raw?
5. If you then assign raw = key, is the object containing "  JaVa  " modified?
6. Why must you call toString() to keep a StringBuilder snapshot instead of just creating a second reference variable?

**Answers:**

1. raw remains **"  JaVa  "**, and display is **"JaVa"**.
2. raw has length **8** (two spaces + four letters + two spaces); display has length **4**.
3. **false**, because the contents of the two strings differ.
4. key is **"java"**; from it alone, original capitalization and whitespace cannot be reliably recovered.
5. **No**. The assignment only makes variable raw point to another String, without altering the old object's content. However, if no other reference remains, the application may no longer access the original.
6. Two variables referencing the same StringBuilder still observe mutations on one mutable object; toString() creates an immutable String value at snapshot time.

**Key takeaway:** When text is transformed for searching, normalization, or display, **keep the input string according to business needs and create a separate result version**. String immutability protects each value's content; **retaining the original, choosing the right version when using it, and managing sensitive data** are the responsibility of program design.
