# A `String` Value Does Not Change After the Object Is Created (Immutability in Java)

## 1. What Is *Immutability*?

In Java, a `String` object is **immutable**: once created, the string content of that object itself cannot be changed. Any operation that needs to represent different content must return/reference a different `String` value; it does not modify the characters already inside the original object.

This is different from a **reference variable**. A variable of type `String` (if not declared `final`) can still be reassigned to point to a different object. For example:

```java
String text = "Java";
text = text + " 17";
```

After the assignment, the `text` variable holds `"Java 17"`. The previous `"Java"` string object **was not mutated**. That is the most important point of this lesson: **changing a variable's value** does not mean **modifying an object's content**.

You can visualize it like this:

```text
Initially:         text ───────> String "Java"

New value created:               String "Java 17"
                   String "Java" (still intact)

Reassigned:        text ───────> String "Java 17"
                                 (the "Java" object is not modified)
```

This diagram illustrates reference semantics; it does not assert how the JVM allocates or collects each individual object.

## 2. The Object Does Not Change, but the Variable Can Point Elsewhere

Another variable can reference the same initial string:

```java
String original = "Hello";
String alias = original;

original = original.concat(" Java");

// original -> "Hello Java"
// alias    -> "Hello"
```

`concat(" Java")` returns a string with new content. The reassignment only changes the reference in `original`; `alias` still references the string `"Hello"`. If the method actually modified the original object, `alias` would see the change too; with `String`, that does not happen.

The statement "`String` cannot be changed" should be understood precisely as **the content of a specific `String` object cannot be changed**, not that a `String` variable must hold the same value forever.

### `final String` vs. `String` Immutability

```java
final String language = "Java";
// language = "Kotlin"; // COMPILE ERROR: cannot reassign a final variable
```

`final` prevents the variable `language` from being reassigned after initialization, whereas `String` immutability prevents the object itself from having its content modified. Even if you remove `final`, `String` itself remains immutable. Conversely, declaring `final StringBuilder builder` only fixes the **reference** `builder`; it does not prevent `builder.append(...)` from modifying the content of the `StringBuilder`.

## 3. What Do Methods That Look Like They "Modify" a String Actually Do?

Many `String` methods return a value to be used, without changing the object the method was called on.

| Call | Represented result | Original string object |
| --- | --- | --- |
| `"cat".concat("s")` | `"cats"` | Still `"cat"` |
| `"cat".replace('c', 'b')` | `"bat"` | Still `"cat"` |
| `"java".toUpperCase(java.util.Locale.ROOT)` | `"JAVA"` | Still `"java"` |
| `"  abc  ".strip()` | `"abc"` | Still `"  abc  "` |
| `"hello".substring(1, 4)` | `"ell"` | Still `"hello"` |

**You must keep the result if you want to use the new content:**

```java
String name = "java";
name.toUpperCase(java.util.Locale.ROOT);
System.out.println(name); // java

name = name.toUpperCase(java.util.Locale.ROOT);
System.out.println(name); // JAVA
```

The first statement only calls the method without using the return value; it has no effect on `name`. The later statement reassigns the variable.

**Do not mistakenly assume every method call must create a new object.** Some methods may return the current object itself when the result is unchanged, such as `"abc".concat("")`. What is guaranteed is **not modifying the content of the original `String` object**; whether a new object is allocated or an existing one is reused is a separate matter. In application programming, do not use the reference comparison `==` to infer content from these operations.

## 4. Complete Runnable Example in Java 17

Save the following program to the file `StringImmutabilityDemo.java`:

```java
import java.util.Locale;

public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String extended = original.concat(" 17");

        System.out.println("original = " + original);
        System.out.println("alias = " + alias);
        System.out.println("extended = " + extended);

        String upper = original.toUpperCase(Locale.ROOT);
        System.out.println("upper = " + upper);
        System.out.println("original after method = " + original);

        original = extended;
        System.out.println("original after assignment = " + original);
        System.out.println("alias after assignment = " + alias);

        char[] source = {'J', 'a', 'v', 'a'};
        String fromArray = new String(source);
        source[0] = 'K';
        System.out.println("source array = " + new String(source));
        System.out.println("string from array = " + fromArray);

        char[] exported = fromArray.toCharArray();
        exported[0] = 'Z';
        System.out.println("exported array = " + new String(exported));
        System.out.println("string after export = " + fromArray);

        StringBuilder builder = new StringBuilder("Go");
        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("builder = " + builder);
        System.out.println("snapshot = " + snapshot);

        String literal = "same";
        String created = new String("same");
        System.out.println("same content = " + literal.equals(created));
        System.out.println("same reference = " + (literal == created));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

Output:

```text
original = Java
alias = Java
extended = Java 17
upper = JAVA
original after method = Java
original after assignment = Java 17
alias after assignment = Java
source array = Kava
string from array = Java
exported array = Zava
string after export = Java
builder = Go!
snapshot = Go
same content = true
same reference = false
```

The example illustrates four points: changing a reference does not modify the old string; `String` methods return a result; an external character array cannot modify the content of an already created `String`; `StringBuilder` is mutable, yet a `String` obtained from `toString()` remains an immutable value.

## 5. Why Cannot a `char[]` Array Modify a `String`?

A character array is a **mutable** structure: you can assign `chars[0] = 'X'`. However, when creating a `String` from a `char[]` array, Java takes the content of the array to create the string and **does not allow subsequent changes to the array to affect the string**.

```java
char[] chars = {'a', 'b', 'c'};
String s = new String(chars);
chars[0] = 'X';

System.out.println(new String(chars)); // Xbc
System.out.println(s);                 // abc
```

Similarly, `s.toCharArray()` creates a separate array for you to modify if needed. Modifying the returned array will not change the content of `s`. `String` also provides no public API for users to directly set a character at a position such as `s.setCharAt(...)`; methods of that kind belong to mutable objects like `StringBuilder`.

Internal implementation details of `String` change across JDK versions (for instance, modern `String` can store data as compact strings). Learners should rely on **the API's immutability contract**, not on internal fields or the assumption that `String` is always backed by a `char[]` array. Do not use reflection/`Unsafe` to tamper with internal representation: doing so breaks program assumptions and is not a supported way to use `String`.

## 6. Immutability and the String Pool

Java has a *string pool* mechanism to share strings with the same content in appropriate cases. In particular, string literals and string constant expressions are interned:

```java
String a = "Java";
String b = "Ja" + "va"; // constant expression folded at compile time
System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Here `a == b` is `true` because both references point to the same interned literal. **Do not generalize** this result to all strings with the same content. For example:

```java
String a = "Java";
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
System.out.println(a == b.intern()); // true
```

`new String("Java")` is used here **only to illustrate** the difference between reference and value; in normal applications there is no need to create such an extra object.

The string pool can safely share a `String` object because no one can modify its content: all sharing sites will always see the same sequence of characters. When you want to compare **content**, use `equals()`; `==` is only appropriate when you genuinely need to compare **the same object** (or check against `null`).

## 7. When Multiple Edits Are Needed: Use `StringBuilder`

`StringBuilder` is a **mutable** object. Operations such as `append()`, `insert()`, `delete()`, `replace()`, and `setCharAt()` update the state of the builder, instead of producing an immutable `String` object after each step.

Standalone example program `BuildMessage.java`:

```java
public class BuildMessage {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Java");
        String before = builder.toString();

        builder.append(" 17");
        builder.setCharAt(0, 'j');

        String after = builder.toString();
        System.out.println("before = " + before);
        System.out.println("builder = " + builder);
        System.out.println("after = " + after);
    }
}
```

Run:

```bash
javac BuildMessage.java
java BuildMessage
```

Output:

```text
before = Java
builder = java 17
after = java 17
```

`before` does not change after the builder is modified. `toString()` provides an immutable `String` value at the moment of the call; modifying the builder afterward does not alter the strings already returned.

### Comparing Options for String Concatenation

| Case | Appropriate approach | Reason |
| --- | --- | --- |
| Concatenating a few simple pieces | `first + " " + last` | Readable; the compiler/JVM can optimize it |
| Concatenating many pieces in a loop | `StringBuilder` then `toString()` | Avoids repeatedly forming unnecessary intermediate string values |
| Needing a stable string to store/share | `String` | The object's content does not change |
| One builder object used from multiple threads | Appropriate synchronization design or a separate builder per thread | `StringBuilder` is not guaranteed thread-safe when mutated concurrently from multiple threads |

You should not claim that every `+` operation is "slow"; Java optimizes string concatenation. What you need to recognize is that `String` provides no mechanism for in-place modification, so when accumulating data over many steps, a builder can be more suitable.

## 8. Benefits of Immutability

### 8.1. Safe Content Sharing

Multiple pieces of code or multiple threads can hold references to **the same** `String` without worrying that one place modifying the content will cause another place to observe new characters. This property is useful when passing parameters, returning results, storing configuration, and sharing constants.

That **does not automatically make every program containing `String` thread-safe**. If multiple threads concurrently read/write a **reference variable** of type `String`, you still have to properly handle shared state, value visibility, and synchronization when needed. Safety of **object content** and safety when **updating a variable** are two different issues.

### 8.2. Serving as Keys for `HashMap` or Elements of `HashSet`

`String.equals()` and `String.hashCode()` depend on the string content. Because the content cannot change, a `String` used as a key will not change how it compares or hashes while residing inside the data structure.

```java
java.util.Map<String, Integer> scores = new java.util.HashMap<>();
String key = "Java";
scores.put(key, 10);

key = key + " 17";

System.out.println(scores.get("Java"));    // 10
System.out.println(scores.get("Java 17")); // null
```

Reassigning `key` does not change the `"Java"` key already placed in the map. Immutability helps prevent the common bug where a mutable key object has its content altered after insertion.

### 8.3. Easier to Reason About Data Flow

A method receiving a `String` can trust that external code will not modify the characters of the passed-in object itself while the method is processing it. If different text is needed, the code returns or receives a new value, making behavior clear and easy to test.

However, immutability **does not mean secrecy or absolute security**: for example, sensitive data in a `String` cannot be actively overwritten character by character the way a mutable array can be overwritten; when the object is collected is decided by the JVM. For sensitive data requiring a policy to wipe it from memory, consider appropriate designs and APIs instead of relying on the ability to "clear String content."

## 9. Common Misconceptions

1. **"`s += "x"` modified the `s` object."** False: the expression produces a string value with new content and reassigns the variable `s`. Aliases referencing the old string still see the old content.
2. **"Calling `s.replace(...)` is enough."** False if you need the result. `replace` returns the resulting string; you must assign it to a variable or pass the return value to the next step.
3. **"`String` is immutable because I declared it `final`."** Incorrect: `String` is inherently immutable even if the reference is not `final`. `final` only forbids reassigning the variable.
4. **"`==` and `equals` both compare text."** `==` compares references; `equals` compares content. The pool may make some `==` pairs evaluate to true, but it is not the rule for comparing strings.
5. **"Every `String` method always allocates a new object."** Not necessarily. If the result does not change, the API or JVM may return the same reference or reuse an existing object; immutability only requires not modifying the original string.
6. **"You can modify a `String` by changing the array passed to the constructor."** No: changing the external array after creating the `String` does not change the string content.
7. **"Builder and String are the same."** No: `StringBuilder` is mutable and can be modified through the same reference; `String` is immutable, and values obtained from a builder remain unchanged.
8. **"Because String content is thread-safe, reassigning a shared variable is also thread-safe."** False: immutability does not replace the synchronization and visibility rules of the Java Memory Model.

## 10. Self-Check

Consider the following code inside the body of a Java method:

```java
String a = "cat";
String b = a;

a.replace('c', 'b');
a = a + "s";

System.out.println(a);
System.out.println(b);
```

The output is:

```text
cats
cat
```

Explanation: `replace` does not change `a` because the return value is discarded. The operation `a + "s"` produces the value `"cats"` and `a` is reassigned. `b` still references the original `"cat"` value.

Try changing the third line to `a = a.replace('c', 'b');`. Then `a` ends up as `"bats"`, while `b` is still `"cat"`.

**Remember:** Immutability is about **the content of a `String` object after it is created**. Whenever you see a string "change," ask: *was the original object modified, or was another value created/received and assigned to the variable?* For `String` in Java, it is the second case.
