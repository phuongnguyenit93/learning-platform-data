# Transformation Methods Return Results Instead of Modifying the Source String in Java

## 1. Objectives and Core Idea

In Java, `String` is **immutable**: the content of a `String` object cannot be modified after creation. When you need to convert to uppercase, lowercase, remove whitespace, replace text, concatenate, or extract substrings, the corresponding methods **return a result value** for the caller to use; they do not modify the content of the source object.

After this lesson, you should be able to explain and practice:

1. Distinguishing a **reference variable**, a **`String` object**, and a method's **return value**.
2. Spotting bugs where `strip()`, `replace()`, `toUpperCase()`, etc. are called while discarding the result.
3. Knowing when to **reassign a variable**, when to **keep the original and create a result variable**, and when to **return a result** from your own method.
4. Applying *method chaining* in the right order.
5. Contrasting `String` with `StringBuilder` and handling `null`, regex, Unicode, `Locale`, and performance cases.

Examples in this lesson use Java 17+; you should know variables, assignment, objects, method calls, and return value types.

## 2. Immutability Does Not Mean a Variable Cannot Be Reassigned

Look at this code snippet:

~~~java
String source = "java";
String upper = source.toUpperCase();

System.out.println(source); // java
System.out.println(upper);  // JAVA
~~~

The object representing `"java"` **does not change**. `toUpperCase()` returns the result `"JAVA"` and the variable `upper` receives this result. The two variables hold different **values**, while reading `source` again still yields `"java"`.

Three easily confused concepts:

- **String object:** carries immutable content.
- **Reference variable:** can point to a different string object through assignment, unless the variable is declared `final`.
- **Return value:** the result of the operation. If ignored, the expected transformation effect will usually not appear in the source variable.

Illustrative diagram:

~~~text
Initially:
source ───────► "java"

source.toUpperCase() returns:
                 "JAVA"

Without assigning the result:
source ───────► "java"

Assigning source = source.toUpperCase():
source ───────► "JAVA"
               (the original "java" object is not modified)
~~~

**Subtle point:** returning a `String` result **does not mean a new object is always created**. When the value does not need to change, some methods may return the same reference. Immutability guarantees **unchanged source content**; it does not guarantee allocation counts. Therefore, use `equals()` when checking whether two strings have the same content; `==` compares reference identity and is unsuitable for most text comparisons.

## 3. Classic Bug: Calling a Method and Discarding the Return Value

~~~java
String text = "  java string  ";
text.strip();
text.toUpperCase();
text.replace("java", "JAVA");

System.out.println("[" + text + "]");
// [  java string  ]
~~~

The code compiles cleanly and throws no errors, yet `text` does not change. Each transformation returned a result that **was never used**.

Fix it by capturing the result:

~~~java
String text = "  java string  ";
text = text.strip();
text = text.toUpperCase();
text = text.replace("JAVA", "Java");

System.out.println("[" + text + "]");
// [Java STRING]
~~~

Here `text = ...` updates **the reference stored in the variable**; it does not modify a `String` object in place.

If you want to preserve the original input:

~~~java
String raw = "  java string  ";
String display = raw.strip().toUpperCase();

System.out.println("raw=[" + raw + "]");
// raw=[  java string  ]
System.out.println("display=[" + display + "]");
// display=[JAVA STRING]
~~~

Naming variables `raw`/`display` helps distinguish the original copy from the processed copy. Preserving the source is especially useful when you need to explain, compare, or test transformation rules.

## 4. Transformation Methods Returning `String`

| Method | Purpose | Example result |
| --- | --- | --- |
| `toUpperCase()`, `toLowerCase()` | Change letter case | `"Java".toUpperCase()` → `"JAVA"` |
| `strip()`, `stripLeading()`, `stripTrailing()` | Remove whitespace at both ends / start / end | `" a ".strip()` → `"a"` |
| `trim()` | Remove leading/trailing characters with code `<= U+0020` per spec | `" a ".trim()` → `"a"` |
| `replace(old, new)` | Replace **literal** substrings | `"a-b".replace("-", ":")` → `"a:b"` |
| `replaceAll(regex, replacement)` | Replace all **regex** matches | `"a1b2".replaceAll("\\d", "#")` → `"a#b#"` |
| `replaceFirst(regex, replacement)` | Replace first regex match | `"a1b2".replaceFirst("\\d", "#")` → `"a#b2"` |
| `substring(begin, end)` | Extract slice, end index exclusive | `"Java".substring(1, 3)` → `"av"` |
| `concat(other)` and `+` operator | Concatenate strings | `"Java".concat(" 17")` → `"Java 17"` |
| `repeat(count)` | Repeat content | `"ab".repeat(2)` → `"abab"` |
| `formatted(args...)`, `String.format(...)` | Build string from format | `"%s-%d".formatted("A", 2)` → `"A-2"` |
| `indent(n)`, `stripIndent()` | Transform indentation of multiline text | Result may differ in both spaces and line terminators |

**Not every method called on `String` returns `String`.** For example:

~~~java
String data = "a,b,c";
int length = data.length();
boolean exists = data.contains("a");
String[] pieces = data.split(",");
~~~

`length()` returns `int`, `contains()` returns `boolean`, and `split()` returns `String[]`. None of them **modify** `data`, yet they have different return types. Methods such as `indexOf()`, `isBlank()`, `matches()`, or `codePoints()` also have their own return types. Read the signatures in the Javadoc before writing code.

## 5. Three Ways to Capture Results Properly

### 5.1. Reassign When You No Longer Need the Variable to Hold the Old Version

~~~java
String name = "  alice  ";
name = name.strip();
name = name.replace("alice", "Alice");
// name now holds "Alice"
~~~

The original string value is not modified. What changes is **the reference value of the variable** `name`.

### 5.2. Use a New Variable to Keep Both Raw and Processed Data

~~~java
String input = "  alice  ";
String normalized = input.strip().replace("alice", "Alice");

// input: "  alice  "
// normalized: "Alice"
~~~

This approach is useful when each version serves a distinct role. Do not strip diacritics, change case, or trim strings automatically unless business rules specify it, because doing so can lose information.

### 5.3. Return the Result When Writing Your Own Method

**Wrong:**

~~~java
static String normalizeWrong(String input) {
    input.strip();
    input.toLowerCase(java.util.Locale.ROOT);
    return input; // Returns the source, not the processed result
}
~~~

**Right:**

~~~java
static String normalizeCorrect(String input) {
    return input.strip().toLowerCase(java.util.Locale.ROOT);
}
~~~

In the correct example, the parameter `input` must be non-`null`. Rules for handling `null` should be clearly stated in the method's contract.

## 6. Method Chaining: Previous Result Is the Next Step's Input

~~~java
String result = "  java core  "
        .strip()
        .replace("java", "Java")
        .toUpperCase();

System.out.println(result); // JAVA CORE
~~~

Process:

~~~text
"  java core  "
       │ strip()
       ▼
"java core"
       │ replace("java", "Java")
       ▼
"Java core"
       │ toUpperCase()
       ▼
"JAVA CORE"
~~~

**The order of transformations can change the result**:

~~~java
String text = "Java";

String first = text.toLowerCase().replace("java", "core");
String second = text.replace("java", "core").toLowerCase();

System.out.println(first);  // core
System.out.println(second); // java
~~~

`replace("java", "core")` is case-sensitive; when applied directly to `"Java"` it replaces nothing. When converted to lowercase first, the segment to replace is found.

**Chaining rules:**

- The next call must be compatible with the **return type** of the previous call: `text.strip().replace(...)` is valid, whereas `text.length().strip()` is invalid because `length()` returns `int`.
- Use intermediate variables when you need to debug step by step or when a pipeline gets too long.
- The final expression must be used (assigned, returned via `return`, passed as an argument, etc.) if the processed result is the goal of the program.
- Chaining is a way to express sequential processing, **not** a way to make a `String` object mutable.

## 7. Contrasting with `StringBuilder`: Truly Mutable

`StringBuilder` differs from `String` in that it **modifies internal state** when calling `append()`, `insert()`, `delete()`, or `replace()`.

~~~java
String text = "A";
text.concat("B");                // Return value is discarded
System.out.println(text);        // A

StringBuilder builder = new StringBuilder("A");
builder.append("B");             // The builder itself changes
System.out.println(builder);     // AB
~~~

With `StringBuilder`, `append()` both mutates the builder and returns a reference to the builder for further calls. With `String`, `concat()` returns the concatenated result while the source value stays intact.

Both approaches below produce the value `"ab"`, but through different mechanisms:

~~~java
String s = "a";
s = s + "b"; // Reassigns variable s to the String result

StringBuilder b = new StringBuilder("a");
b.append("b"); // Modifies the content of object b
~~~

**`final` vs. immutable:**

~~~java
final String fixed = "a";
String changed = fixed.replace("a", "b"); // Valid
// fixed = changed; // Compile error: cannot reassign fixed

final StringBuilder editable = new StringBuilder("a");
editable.append("b"); // Valid: the builder object is still mutable
~~~

`final` prevents **reassigning a reference variable**; it does not automatically make the object the variable points to immutable.

## 8. Edge Cases and Real-World Pitfalls

### 8.1. Empty, Blank, and Null

~~~java
String empty = "";
String blank = "   ";

System.out.println(empty.isEmpty()); // true
System.out.println(blank.isEmpty()); // false
System.out.println(blank.isBlank()); // true
System.out.println(blank.strip().isEmpty()); // true
~~~

`null` is not an empty string: `null.strip()` throws `NullPointerException`. Two example policies:

~~~java
static String normalizeNullable(String text) {
    return text == null ? null : text.strip();
}

static String normalizeRequired(String text) {
    java.util.Objects.requireNonNull(text, "text");
    return text.strip();
}
~~~

Choose a contract according to your needs: return `null`, convert missing data to `""`, or reject `null`. Do not change the meaning of data implicitly.

### 8.2. When Nothing Is Replaced, the Result Still Equals the Old Content

~~~java
String original = "Hello";
String after = original.replace("x", "y");
System.out.println(original.equals(after)); // true
~~~

`"x"` is not found, so the result's content equals the source. This does not prove the two variables definitely hold the same reference; the stable rule is **the source does not change**, not **every call always produces a new object**.

### 8.3. Literal `replace` vs. Regex `replaceAll`

~~~java
String path = "a.b.c";

String a = path.replace(".", "-");        // a-b-c
String b = path.replaceAll("\\.", "-");   // a-b-c
~~~

`replace(".", "-")` searches for a literal dot. `replaceAll` takes a regular expression; the symbol `.` in regex matches almost any character, so to match a real dot you must use `\.`, written in Java source code as `"\\."`.

Note that the `replacement` argument of `replaceAll` also has special syntax for `$` and `\`; when using a literal replacement string coming from external data, using `java.util.regex.Matcher.quoteReplacement(replacement)` is appropriate.

### 8.4. Locale and Case Conversion

Parameterless `toLowerCase()` and `toUpperCase()` use the **default locale**. When handling fixed technical identifiers, pass `Locale.ROOT` so behavior does not depend on the user's locale:

~~~java
String key = "CONTENT-TYPE";
String lower = key.toLowerCase(java.util.Locale.ROOT);
System.out.println(lower); // content-type
~~~

For natural language, use the locale matching the business rule. Some case conversions can **change string length**, so do not assume one input character always produces one output `char`.

### 8.5. Unicode When Slicing Strings

`length()` counts **UTF-16 code units**, not user-perceived characters:

~~~java
String value = "A😀B";
System.out.println(value.length()); // 4
System.out.println(value.codePointCount(0, value.length())); // 3
~~~

An emoji can take two `char`s. `substring()` slices by UTF-16 indices; slicing in the middle of a surrogate pair can produce a result that does not represent a complete Unicode character. When you need to handle code points, use APIs like `codePoints()` and `offsetByCodePoints()`. A user-perceived *grapheme* can also consist of multiple code points. Immutability is **not** a substitute for proper Unicode handling.

### 8.6. Methods Can Throw Exceptions

`substring(begin, end)` can throw `StringIndexOutOfBoundsException` when indices are invalid; `repeat(n)` with `n < 0` throws `IllegalArgumentException`. A failed transformation does not modify the source string, but you still must validate inputs.

## 9. Complete Compilable and Runnable Program (Java 17+)

Create file **`ImmutableStringDemo.java`**:

~~~java
import java.util.Locale;

public class ImmutableStringDemo {
    public static void main(String[] args) {
        String raw = "  java-core  ";

        raw.strip();
        raw.toUpperCase(Locale.ROOT);
        System.out.println("raw=[" + raw + "]");

        String output = raw.strip()
                .replace("-", " ")
                .toUpperCase(Locale.ROOT);
        System.out.println("output=[" + output + "]");
        System.out.println("raw again=[" + raw + "]");

        String title = " hello ";
        title = title.strip();
        title = title.replace("hello", "Hello");
        System.out.println("title=[" + title + "]");

        String token = "a1b2";
        String redacted = token.replaceAll("\\d", "#");
        System.out.println("redacted=[" + redacted + "]");
        System.out.println("token=[" + token + "]");

        StringBuilder builder = new StringBuilder("A");
        builder.append("B");
        System.out.println("builder=" + builder);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac ImmutableStringDemo.java
java ImmutableStringDemo
~~~

**Exact stdout:**

~~~text
raw=[  java-core  ]
output=[JAVA CORE]
raw again=[  java-core  ]
title=[Hello]
redacted=[a#b#]
token=[a1b2]
builder=AB
~~~

Output explanation:

1. The two calls on `raw` do not assign the result, so the source string retains leading/trailing spaces and lowercase letters.
2. `output` receives the result of `strip()` → `replace("-", " ")` → `toUpperCase(Locale.ROOT)`, becoming `"JAVA CORE"`. Printing `raw again` proves the source remained unchanged.
3. `title` is **reassigned** twice, so the variable holds the final copy `"Hello"`.
4. `replaceAll("\\d", "#")` replaces digits in the result `redacted`, while `token` remains `"a1b2"`.
5. `append("B")` mutates the content of `builder`, demonstrating that a mutable object behaves differently from `String`.

Try changing the inputs yourself, predicting the entire stdout, and then running to verify. Consistency between prediction and actual execution matters more than memorizing method names.

## 10. Impact on Performance and Design

Immutability can cause building a string across many operations to produce intermediate values; specific allocations and optimizations depend on the method and compiler/JVM. Do not infer that **every** call returns a new object, or that using `String` is always slow.

Example concatenating strings in a loop:

~~~java
String result = "";
for (int i = 0; i < 1000; i++) {
    result += i;
}
~~~

The code is logically correct, yet cumulative concatenation can create many intermediate values. Instead, it is often appropriate to use:

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 0; i < 1000; i++) {
    builder.append(i);
}
String result = builder.toString();
~~~

Tool selection rule: use `String` to **store and exchange text values**, use `StringBuilder` when **building text over many additions**, then convert back to `String` with `toString()`. Measure performance if this is an actual bottleneck; short `+` concatenations do not need to be mechanically converted to a builder.

Because a `String` object cannot have its content modified, concurrently reading a string across multiple references is safe with respect to content. However, a **reassignable reference variable** shared between threads still needs proper publication and synchronization rules; immutability does not solve every concurrency issue on its own.

## 11. Exercises and How to Self-Check

### Exercise 1 — Predict Then Run

~~~java
String a = "Hello";
a.replace("H", "J");
String b = a.toLowerCase();
System.out.println(a);
System.out.println(b);
~~~

Result: `Hello` and `hello`. The letter `H` does not change because the result of `replace()` was discarded. `b` receives the lowercase result, so its content differs from `a`.

### Exercise 2 — Fix the Bug

Write a method returning `"java core"` from `"  Java CORE  "` using `strip()` and `toLowerCase(Locale.ROOT)`. Try writing a **wrong version that discards the return value**, then fix it with `return input.strip().toLowerCase(Locale.ROOT);`.

### Exercise 3 — Different Order, Different Result

Given `String x = "JAVA";`. Compare:

~~~java
x.toLowerCase(java.util.Locale.ROOT).replace("java", "core");
x.replace("java", "core").toLowerCase(java.util.Locale.ROOT);
~~~

The results are `"core"` and `"java"`, respectively. Explain that `replace()` is case-sensitive.

### Exercise 4 — Null Contract

Create a method `normalize(String s)` accepting a nullable string. Pick **one** clearly documented rule: return `null`, return `""`, or throw an exception. Test with `null`, `""`, `" "`, `" A "`.

### Exercise 5 — Preserve the Original Input

With `String raw = "  Cà phê Đắk Lắk  ";`, create variable `display` using `strip()`. Prove `raw` still contains spaces. Do not arbitrarily remove diacritics or change case, as that alters text meaning beyond the requirement.

### Exercise 6 — Mutable vs. Immutable

Use `StringBuilder` to join numbers `1`, `2`, `3` with commas; call `toString()` to keep the completed copy. Then append `4` to the builder and print both to prove the newly created `String` copy remained unchanged.

### Code Review Checklist

- What type does the call on `String` return: `String`, array, number, boolean, or stream?
- Has the result value been **assigned, returned, passed onward, or used**?
- Should the original copy be preserved? If so, give the processed copy a separate name.
- Are there conditions depending on step order or case sensitivity?
- Are there special requirements for `null`, blank strings, Unicode, or `Locale`?
- Is `replaceAll()` receiving a **regex** when the author mistook it for a literal string?
- Is a `final` variable being misunderstood as making any mutable object immutable?
- When concatenating many times, is `StringBuilder` needed?

**Rule to remember long-term:**

> Transformation methods on `String` do not modify the source string. Use the return value. Reassigning a variable changes **the reference** the variable holds; it does not change the content of the original `String` object.

You have mastered this lesson when you can predict variable values before and after calls, spot operations whose results are discarded, write transformation methods that preserve the source, and clearly distinguish `String` from `StringBuilder`.

## 12. Standard References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): signatures and contracts for `strip()`, `replace()`, `substring()`, `toLowerCase()`, `concat()`, `repeat()`, `formatted()`, etc.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): operations that mutate builder content and `toString()`.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): the role of locale when processing text.
- [Java SE 17 — Matcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html): regex replacement rules and `quoteReplacement()`.
