# `String` Is an Immutable Object in Java 17+

`String` is a **reference type** representing a sequence of characters. In Java, a `String` object is **immutable**: after creation, the content of that object itself cannot be modified through normal APIs. Operations such as concatenation, replacement, case conversion, or slicing **produce a string result** without modifying the original content.

Distinguish two very important ideas:

- **The object does not change its content:** a created `String` retains the same text value.
- **A variable can be assigned a different reference:** `String name = "Java"; name = "Kotlin";` is valid; you change the `name` variable to point to a different string value, **without modifying** the object containing `"Java"`.

## 1. Declaration and operations: the result must be used

~~~java
String title = "Java";
String extended = title.concat(" 17");

System.out.println(title);    // Java
System.out.println(extended); // Java 17
~~~

`concat` does not change `title`. If you want to keep the result on the **`title` variable** itself, reassign it:

~~~java
title = title.concat(" 17");
System.out.println(title); // Java 17
~~~

This statement **changes the reference stored in the variable**, not the old `String` object. The same applies to the `+` or `+=` operators used for string concatenation.

| Operation | Example | Does it modify the original `String`? |
| --- | --- | --- |
| Concatenation | `s.concat("!")`, `s + "!"` | No |
| Replacement | `s.replace("a", "b")` | No |
| Uppercase conversion | `s.toUpperCase()` | No |
| Trimming outer whitespace | `s.trim()` or `s.strip()` | No |
| Extracting a substring | `s.substring(1)` | No |
| Reading character, length | `s.charAt(0)`, `s.length()` | Read-only |
| Modifying a character position | `s.setCharAt(0, 'A')` | **No such method** exists on `String` |

A method may return **the same object** when the result requires no change (for example, some operations that leave the content unchanged). The definition of immutability **does not mean every call is forced to create a new object**, rather that it does not modify the content of the existing `String` object.

## 2. Runnable Java 17+ program

Create the file **`StringImmutabilityDemo.java`**:

~~~java
import java.util.Locale;

public class StringImmutabilityDemo {
    static void attemptChange(String input) {
        input = input.concat("!");
        System.out.println("insideMethod=" + input);
    }

    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String extended = original.concat(" 17");

        System.out.println("original=" + original);
        System.out.println("alias=" + alias);
        System.out.println("extended=" + extended);
        System.out.println("sameOriginal=" + (original == alias));
        System.out.println("extendedIsOriginal=" + (extended == original));

        String sentence = "red blue";
        String replaced = sentence.replace("blue", "green");
        System.out.println("beforeReplace=" + sentence);
        System.out.println("afterReplace=" + replaced);

        String word = "java";
        word.toUpperCase(Locale.ROOT); // Result is ignored.
        System.out.println("ignoredResult=" + word);
        word = word.toUpperCase(Locale.ROOT); // Reassign reference.
        System.out.println("assignedResult=" + word);

        String hello = "Hi";
        attemptChange(hello);
        System.out.println("afterMethod=" + hello);

        String literalA = "cat";
        String literalB = "cat";
        String explicit = new String("cat");
        System.out.println("literalSame=" + (literalA == literalB));
        System.out.println("newSame=" + (literalA == explicit));
        System.out.println("contentEqual=" + literalA.equals(explicit));

        StringBuilder builder = new StringBuilder("A");
        builder.append("B");
        String snapshot = builder.toString();
        builder.append("C");
        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);
    }
}
~~~

Run on **Windows PowerShell** or **Linux/Bash**, in the directory containing the file with JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StringImmutabilityDemo.java
java StringImmutabilityDemo
~~~

**Expected output (exact order):**

~~~text
original=Java
alias=Java
extended=Java 17
sameOriginal=true
extendedIsOriginal=false
beforeReplace=red blue
afterReplace=red green
ignoredResult=java
assignedResult=JAVA
insideMethod=Hi!
afterMethod=Hi
literalSame=true
newSame=false
contentEqual=true
builder=ABC
snapshot=AB
~~~

### Explanation of each phenomenon

1. `alias = original` copies the **reference value**, so both variables point to the string `"Java"` and `original == alias` is `true`. `extended` has different content and is not the same object.
2. `replace` returns a resulting string `"red green"`; `sentence` still holds `"red blue"`.
3. The first `word.toUpperCase(Locale.ROOT)` call has its result discarded so `word` stays `"java"`. After writing the assignment, `word` becomes a reference to the result `"JAVA"`.
4. `attemptChange` receives a **copy of the reference value**, like all Java parameters (pass-by-value). Reassigning `input` only changes the parameter variable, not the caller's `hello`.
5. Two identical string literals usually share the same object from the **string pool**; thus in the example `literalA == literalB` is `true`. `new String("cat")` creates a new object, so `==` is `false` while `equals` returns `true` because the contents match.
6. `StringBuilder.append` **mutates the builder object itself**. `snapshot = builder.toString()` obtains an immutable `String` object with content `"AB"`; subsequent changes to the builder do not turn `snapshot` into `"ABC"`.

## 3. Immutability differs from `final` variables

~~~java
String name = "Mai";
name = "An";            // Valid: variable name is not final.

final String greeting = "Hello";
// greeting = "Hi";     // Invalid: cannot reassign a final variable.

StringBuilder mutable = new StringBuilder("A");
mutable.append("B");    // Valid: modifies StringBuilder content.

final StringBuilder fixedReference = new StringBuilder("X");
fixedReference.append("Y"); // Valid: final does not freeze the object.
~~~

`final` is a rule about **variable reassignment**. By contrast, `String` immutability is a property of **object type design**. A non-`final` `String` reference still points to immutable string objects; a `final StringBuilder` reference can still point to an object whose content changes.

`String` is also a `final` class in Java; you cannot create a subclass of `String` to provide content-mutating methods.

## 4. Equal content does not mean the same reference

Immutability allows safely sharing a `String` object by **content**, but it does not make two distinct objects have the same reference. Compare content with `equals`:

~~~java
String pooled = "hello";
String separate = new String("hello");
System.out.println(pooled == separate);      // false
System.out.println(pooled.equals(separate)); // true
~~~

`==` checks reference identity (or whether both are `null`). `equals` compares UTF-16 content when the left-hand side is non-`null`; `"OK".equals(value)` or `Objects.equals(a, b)` helps handle potentially `null` values. The **string pool** can make two equal literals share a reference, but that does not turn `==` into a reliable content comparison.

When you need to check content, use the `equals` APIs according to their contract. Case-sensitivity cases, Unicode normalization, and pool details are verified separately in the dedicated lesson on comparing `String`s.


## 5. Why is immutability useful?

- **Safer sharing:** two references pointing to the same `String` cannot mutate its content to surprise each other.
- **Convenient as `Map` keys:** the content and `hashCode` result of a `String` cannot be altered during storage/lookup. `HashMap` itself still needs proper synchronization if shared across threads.
- **Helpful when shared across threads:** string content has no mutating operations that can cause races. This does not automatically make all operations on reference variables or collections holding it thread-safe.
- **Easier to reason about:** a method receiving a `String` cannot silently modify the text inside the object the caller is using.

You should not assume that immutability **automatically guarantees optimal memory or performance** for every string concatenation operation.

## 6. Use mutable objects when accumulating many times

Immutability makes `String` values easy to reason about, but repeated `+=` can create many intermediate string results. When building text incrementally across loops, `StringBuilder` stores **mutable** content and provides `append`:

~~~java
StringBuilder out = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        out.append(",");
    }
    out.append(i);
}
String result = out.toString(); // "1,2,3"
~~~

Short concatenations like `"Hello, " + name` remain clear and are usually optimized by the JVM; there is no need to replace every `+` with a builder. `StringBuilder` is not automatically synchronized when multiple threads mutate it concurrently; `StringBuffer` provides synchronized methods if genuinely needed. The dedicated `StringBuilder` lesson further explains buffer management, delimiters, `length`/`capacity`, and content-editing methods.


## 7. Self-check exercises

**Exercise 1 — Predict the output.**

~~~java
String s = "abc";
s.replace("a", "x");
System.out.println(s);
~~~

*Answer:* `abc`. The replacement result was discarded. Writing `s = s.replace("a", "x");` makes `s` reference the string `"xbc"`.

**Exercise 2 — Two variables referencing the same string.** Given `String a = "hi"; String b = a; a += "!";`, what are the values of `a` and `b` afterward?

*Answer:* `a` is `"hi!"`; `b` is still `"hi"`. No `"hi"` object had its content modified.

**Exercise 3 — `final`.** Why is `final StringBuilder b = new StringBuilder("x"); b.append("y");` valid?

*Answer:* `final` prevents reassigning variable `b`; `append` mutates the mutable object that `b` references.

**Exercise 4 — Comparison.** Why does `new String("a") == new String("a")` yield `false` while `equals` yields `true`?

*Answer:* Two `new` calls create two objects; `==` checks identity, `equals` checks content.

**Exercise 5 — Parameters.** A method receives `String text` and writes `text = text.toUpperCase();`. Does the `String` variable passed by the caller change?

*Answer:* No. Java copies the reference value into the parameter; if the caller needs the new value, `return` the resulting string and assign it in the caller.

## Key takeaway

**Immutability is a property of the `String` object, not a ban on reassigning `String` variables.** `concat`, `replace`, `toUpperCase`, and `substring` do not modify the original string; make sure to **use the returned result**. Use `equals` instead of `==` to compare content, and use `StringBuilder` when accumulating or editing text repeatedly.
