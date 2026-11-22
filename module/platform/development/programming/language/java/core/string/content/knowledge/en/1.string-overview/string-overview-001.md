# What is String and Its Role in Representing Text in Java

## 1. What is String?

**String** is the **java.lang.String** class used to store and manipulate text in Java. A String value is an object representing a **sequence of UTF-16 code units**, such as a username, a message, a file path, text data received from an API, or content to be written to a file.

~~~java
String greeting = "Hello";
String language = "Java";
String sentence = greeting + ", " + language + "!";
~~~

This is an **illustrative code snippet** that can be placed inside a method; the **sentence** variable holds the text “Hello, Java!”. The String class resides in the **java.lang** package, so it does not require an import.

Fundamental characteristics:

- **Reference type:** String is a class, not a primitive type like **int**, **boolean**, or **char**. A String variable can refer to a String object or have the value **null**.
- **Immutable:** after a String object is created, its content does not change. Operations like **replace**, **concat**, **toUpperCase**, or **strip** return the resulting String value; they do not modify the original object.
- **Final class:** String cannot be subclassed to alter its behavior.
- **UTF-16 representation at the API level:** many methods such as **length()**, **charAt()**, and **substring()** operate by UTF-16 code unit position. A character a user sees on screen does not necessarily correspond to exactly one position.
- **Has an empty value:** the string **""** is a valid String with a length of 0. It is different from **null**, which means no String object is being referenced.

The role of String is the **text data model** in a program: receiving and displaying input, passing messages between classes, handling formatting, and integrating with I/O libraries, databases, HTTP, JSON, and language-processing APIs. String is solely a data type for representing text; it does not automatically determine a file's character encoding or sanitize input.

## 2. Creating Strings, literals, and the string pool

The most common way is to use a **string literal** in double quotes:

~~~java
String first = "Java";
String second = "Java";
String third = new String("Java");
~~~

Literals can be reused via the JVM's **string pool**. In this example, **first** and **second** reference the same interned literal object; **new String("Java")** creates a new object with the same content. However, when checking **content**, always use **equals()** instead of relying on object addresses.

Other ways to form a string:

- **Concatenation:** **"Hel" + "lo"**, or concatenating with variables using the **+** operator.
- **From a character array:** **new String(charArray)** creates a String from the array's elements; modifying the array afterward does not modify the created String.
- **From bytes:** **new String(bytes, StandardCharsets.UTF_8)** uses an explicit UTF-8 decoder; do not treat each byte as a character.
- **From other values:** **String.valueOf(42)** produces “42”; **String.valueOf((Object) null)** produces the text “null”, which is different from a null reference.
- **Text block (Java 15+):** triple-double-quote syntax for multi-line text, suitable for JSON, sample SQL, or long messages. Text block newline and indentation rules must be accounted for when comparing results.

~~~java
String message = """
        Hello,
        Java!
        """;
~~~

The text block snippet above is a declaration example, not a complete program. The resulting content has a trailing newline at the end of the “Java!” line due to how the literal is written.

**String.intern()** returns the canonical reference in the pool for the same content; this is an intentional optimization/canonicalization mechanism, not a standard way to compare strings. Do not use **==** expecting all strings with the same text to always share a single reference.

## 3. Concept map: focus on what matters

This introductory lesson helps you see the role of String in a program and try a combined example. Each topic below has its own dedicated lesson for deeper study, so here we only identify the core differences:

| Practical question | Initial orientation | Deep-dive topic |
| --- | --- | --- |
| How does a text value differ from a char array? | `String` is immutable; `char[]` is mutable; `CharSequence` is a read interface. | Relationships between String, char[], CharSequence, and Object |
| Do two variables both written as `"Java"` necessarily refer to the same object? | Distinguish reference from content; use `equals()` to compare content. | String content vs. reference variables |
| Are `null`, `""`, spaces, and the text `"null"` the same? | They are distinct data states; `isEmpty()` is not synonymous with `isBlank()`. | Empty strings, blank strings, and null |
| Why doesn't calling `replace()` change the original string? | A String object is immutable; transformations return a String value. | Final class and immutability |
| How to search, slice, compare, replace, or convert bytes? | Choose APIs by purpose and by character unit/charset. | String operation categories |
| When to use StringBuilder/StringBuffer? | When building text across multiple steps; also consider thread sharing. | Choosing String, StringBuilder, or StringBuffer |

**Three key boundaries:** (1) a reference variable can be reassigned even though the String object is immutable; (2) `length()` counts UTF-16 code units, which does not always equal the number of visible characters; (3) `String` represents text, while files/HTTP transmit bytes that require an appropriate charset, typically UTF-8.

For example, `"Java".equals(candidate)` compares content and handles `candidate == null`; `"a.b".replace(".", "-")` replaces a literal dot, whereas `replaceAll` takes a regex. Those choices will be practiced systematically in the String operations lesson.

**When leaving memory:** reading/writing files, JSON, SQL, and HTML require context-appropriate APIs. Charsets, serialization, query parameters, and escaping are not automatic features of String. Sensitive data inside a String also cannot be actively erased from the object in place.

## 4. Runnable Java 17+ example

Save the following code into **StringOverviewDemo.java**, ensuring the filename matches the **public** class name.

~~~java
import java.nio.charset.StandardCharsets;

public class StringOverviewDemo {
    public static void main(String[] args) {
        String raw = "  Xin chào Java  ";
        String cleaned = raw.strip();

        System.out.println(cleaned);
        System.out.println(cleaned.length());
        System.out.println("Java".equals("java"));

        String literal = "Java";
        String copy = new String("Java");
        System.out.println(literal == copy);
        System.out.println(literal.equals(copy));

        String emoji = "😊";
        System.out.println(emoji.length());
        System.out.println(emoji.codePointCount(0, emoji.length()));

        System.out.println("a.b".replace(".", "-"));
        System.out.println("a.b".replaceAll("\\.", "-"));

        byte[] encoded = "Việt".getBytes(StandardCharsets.UTF_8);
        System.out.println(new String(encoded, StandardCharsets.UTF_8));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 StringOverviewDemo.java
java StringOverviewDemo
~~~

Stdout output (one result per line):

~~~text
Xin chào Java
13
false
false
true
2
1
a-b
a-b
Việt
~~~

Explanation: **strip()** removes the leading and trailing spaces; the remaining length is 13 code units. Two strings differing in letter case are not equal via **equals()**. **new String(...)** creates a different object from the literal even with equal content. The emoji uses two code units but is one code point. Both **replace** and **replaceAll** replace the dot properly when the regex is escaped. UTF-8 bytes encode and then decode back to the original text.

## 5. Knowledge self-check

1. **Why is String immutable yet we can still write s = s + "!"?** Because the assignment changes the reference to the new result; it does not modify the original object.
2. **When should you use equals instead of ==?** When you need to compare text content, regardless of how the objects were created.
3. **What do "".isEmpty() and " ".isBlank() return?** Both return **true**, but they apply to two different situations; **" ".isEmpty()** is **false**.
4. **Why does "😊".length() return 2?** This emoji is represented by two UTF-16 code units, even though it consists of only one Unicode code point.
5. **What should you use to join many labels in a loop?** Usually **StringBuilder**; when you already have a collection of elements, **String.join** is also very convenient.
6. **Why should you specify StandardCharsets.UTF_8 when reading/writing?** To keep the encoding consistent and independent of the system's default charset.

**Takeaway:** String is the central data type for text in Java, characterized by immutability and an API designed primarily around UTF-16. Properly understanding the differences between **content and reference**, **code units and visible characters**, and **String and encoded bytes** will help prevent most text-processing bugs.