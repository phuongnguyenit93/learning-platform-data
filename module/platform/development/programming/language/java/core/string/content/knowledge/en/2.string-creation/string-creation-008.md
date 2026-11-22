# `new String` and Why You Usually Don't Need to Copy an Existing `String`

In Java, when you already have a `String` value, you usually only need to reuse the reference to it. Writing `new String(existing)` creates a **different `String` object with the same content** as `existing`. Because `String` is immutable, creating this new object usually does not make the data any safer and can introduce unnecessary allocation overhead.

This lesson clearly distinguishes **reference variables**, **object identity**, **content value**, and the cases where a `String` constructor is genuinely useful.

## 1. Assigning a Reference vs. Calling `new String(...)`

```java
String original = "Java";
String alias = original;
String copy = new String(original);
```

- `original` references a `String` object carrying the content `"Java"`. String literals are managed in the *string pool*.
- `alias = original` copies the **reference value**. `original` and `alias` point to the same object; no extra `String` is created.
- `copy = new String(original)` calls the `String(String original)` constructor. It creates a new object that has **equal content** to `original` but **different identity**.

```text
original ──┐
           ├────────> object A: String "Java"
alias ─────┘

copy ────────────────> object B: String "Java"
```

Note carefully: "a new object" does not mean "guaranteed to copy the entire internal backing byte array". Java guarantees the semantics of creating a new `String` object; how the JVM stores or shares internal data is an implementation detail, not an API guarantee.

### Runnable Example on Java 17+

Create the file `StringCopyDemo.java`:

```java
public class StringCopyDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String copy = new String(original);

        System.out.println(original == alias);
        System.out.println(original == copy);
        System.out.println(original.equals(copy));
        System.out.println(copy.equals("Java"));
    }
}
```

Compile and run:

```bash
javac StringCopyDemo.java
java StringCopyDemo
```

Expected output:

```text
true
false
true
true
```

Explanation: `==` on two reference variables checks **whether they are the same object**, whereas `String.equals` checks **whether they have the same character sequence**. Thus `original == copy` is false while `original.equals(copy)` is true.

When comparing content, prefer `a.equals(b)`. If `a` might be `null`, use `Objects.equals(a, b)` after importing `java.util.Objects`; or place a constant on the left like `"Java".equals(a)`. Do not rely on `==` just because some literals may share the pool.

## 2. `String` Is Immutable: Why Is Defensive Copying Unnecessary?

A `String` object is *immutable*. Standard public APIs provide no operations to modify the character sequence stored inside that object. Methods like `replace`, `concat`, `trim`, `substring`, `toUpperCase`, etc. create or return a **resulting string value**; they do not mutate the source object's content. A method may return the same reference when nothing changes, depending on the method's contract.

Consider `StringImmutabilityDemo.java`:

```java
public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String original = "cat";
        String alias = original;
        String modified = original.replace('c', 'b');

        System.out.println(original);
        System.out.println(alias);
        System.out.println(modified);

        original = "dog";
        System.out.println(alias);
        System.out.println(original);
    }
}
```

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

```text
cat
cat
bat
cat
dog
```

In the first three lines, `replace` produces `"bat"` while both `original` and `alias` still see `"cat"`. Afterward, `original = "dog"` only changes the reference stored in the **variable** `original`; `alias` still points to the old `"cat"` object. **Reassigning a variable is different from mutating an object's content.**

Therefore, when writing a class with a `String` field, you normally do not need to copy in constructors and getters:

```java
public final class UserLabel {
    private final String label;

    public UserLabel(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
```

This is an illustrative class for use in another program, without its own `main`. Writing `this.label = new String(label)` and `return new String(label)` usually just creates extra objects without adding any content protection. `final` ensures the `label` field cannot be reassigned after initialization; the immutability of the `String` object itself is a separate property.

If business logic requires `label` not to be `null` or empty, you must **validate the input** appropriately; wrapping with `new String(label)` does not replace validation.

## 3. Impact of the String Pool

The *String pool* lets the JVM reuse canonical references for literals and interned strings. For example:

```java
String a = "hello";
String b = "hello";
String c = new String("hello");

System.out.println(a == b);      // true
System.out.println(a == c);      // false
System.out.println(a.equals(c));  // true
```

Here `a` and `b` both point to the interned literal, whereas `new String("hello")` creates a different object. There is no need to write `new String("hello")` to "activate" the pool: literals already belong to the pool mechanism from the start.

The `intern()` method returns the canonical reference of a string with matching content in the pool; it has a different purpose from `new String(String)`. Using `intern()` to force `==` to work in business logic usually introduces unnecessary coupling. `equals` expresses the intent of content comparison accurately.

Remember that **not all strings with the same content share the same reference**. Strings computed at runtime, read from files, retrieved from APIs, or created from other objects can be equal in content yet differ in identity.

## 4. Consequences of Overusing `new String(existing)`

Given the same need to declare a new variable:

```java
String source = "Java Core";
String first = source;             // Preferred.
String second = new String(source); // Usually redundant.
```

Both `first` and `second` give the content `"Java Core"`. However:

1. **New object**: by Java's semantics, the `new` expression creates a separate object, bringing potential extra allocation and garbage collection. The JIT compiler may optimize away unobservable allocations, so a fixed overhead across every run cannot be assumed.
2. **Changed identity**: `first == second` is `false` even though `first.equals(second)` is `true`. When code accidentally depends on identity, a new copy can alter behavior.
3. **Obscures code intent**: readers may think two strings must be separated to prevent one side from mutating the other, even though `String` is already immutable.
4. **Worse `null` handling**: the assignment `String alias = source` accepts `source == null`; by contrast, `new String((String) null)` throws `NullPointerException`. The cast in the example disambiguates the `String(String)` overload.

A design rarely genuinely needs a separate `String` *identity*. If it does, that requirement should be stated explicitly and reviewed carefully because comparisons, synchronization, or data structures based on string identity are error-prone. For ordinary text data, content value is what matters.

## 5. When Should You Use `new String(...)` Constructors?

Distinguish the input types:

| Syntax | Input / Goal | Assessment |
| --- | --- | --- |
| `String b = a;` | `a` is already a `String`; reuse an immutable value | **Recommended** in normal cases |
| `new String(a)` | `a` is already a `String`; create a new identity with the same content | **Almost never needed** |
| `new String(chars)` | Mutable `char[]`; snapshot character content | **Useful** when converting an array to a string |
| `new String(bytes, StandardCharsets.UTF_8)` | Decode `byte[]` with a specific charset | **Useful** when handling bytes |
| `builder.toString()` | Obtain a string from `StringBuilder` | **Appropriate**, no need to wrap with `new String(...)` |
| `new String()` | Create an empty string | Using `""` is simpler |

### Why Is a Character Array a Different Case?

`char[]` is mutable, whereas `String` is immutable. Creating a `String` from an array captures its content at the moment of the call; reusing an existing `String` reference needs no such step. The following example compares both cases directly:

Create the file `StringSourceChoiceDemo.java`:

```java
public class StringSourceChoiceDemo {
    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String redundant = new String(original);
        char[] letters = {'J', 'a', 'v', 'a'};
        String fromArray = new String(letters);
        letters[0] = 'K';

        System.out.println(original == alias);
        System.out.println(original == redundant);
        System.out.println(original.equals(redundant));
        System.out.println(fromArray);
        System.out.println(new String(letters));
    }
}
```

Run `javac -encoding UTF-8 StringSourceChoiceDemo.java` then `java StringSourceChoiceDemo`:

```text
true
false
true
Java
Kava
```

`alias` only copies the reference, while `redundant` creates a separate string object despite having the same content. `fromArray` retains `"Java"` after the array changes to `Kava`. That is why converting from an array is meaningful, whereas copying an existing `String` is usually redundant. The earlier lessons on `char[]`, `byte[]`, and `StringBuilder` cover each conversion mechanism in detail.

## 6. Choosing the Right Pattern for Your Goal

### Case A: Reusing an Existing String

```java
String title = "Java";
String displayTitle = title;
```

Reuse the reference. There is no risk that a later string concatenation will mutate the old object.

### Case B: Producing a Transformed Text Value

```java
String raw = " java ";
String normalized = raw.trim().toUpperCase();
```

`raw` still has the content `" java "`, while `normalized` has the content `"JAVA"`. We call processing methods to get a **different value**, rather than copying `raw` and expecting it to mutate in place.

### Case C: Building a String Over Multiple Steps

```java
StringBuilder builder = new StringBuilder();
builder.append("Hello");
builder.append(", ");
builder.append("Java");
String message = builder.toString();
```

`message` contains `"Hello, Java"`. `StringBuilder` is suitable when characters are appended multiple times; `toString()` finishes construction and provides an immutable `String` value. No `new String(message)` is needed.

### Case D: Validating a `String` Parameter

```java
import java.util.Objects;

public final class Greeting {
    private final String message;

    public Greeting(String message) {
        this.message = Objects.requireNonNull(message, "message");
    }

    public String message() {
        return message;
    }
}
```

This is a standalone design-illustration class without `main`. `Objects.requireNonNull` enforces an input precondition, which is separate from the question of copying. Storing and returning the `String` directly is sound because `String` is immutable.

## 7. Common Misconceptions

**"With `b = a`, modifying `b` will modify `a`?"** No. There is no API to modify a `String` object's content in place. Writing `b = b + "!"` gives `b` a new value/reference; `a` is unchanged.

**"`new String(a)` definitely deep-copies the internal data?"** There is no such public guarantee. What matters at the language level is a new object identity and matching string content. Do not rely on how the JVM represents characters in memory.

**"If two strings have the same text, `==` must be true?"** False. `equals` is for comparing content. `==` can be true for the same literal or the same reference, but it is not a general rule for text values.

**"A class constructor must defensively copy a `String` parameter with `new String(name)`?"** Usually no. Reassigning the caller's variable does not alter the string held by the field. If the parameter were `char[]` or a mutable object, that would be a different matter.

**"A Java method can mutate the caller's string because of pass-by-reference?"** Java passes parameters **by value**; for objects, that value is the reference. Reassigning the parameter variable inside the method does not reassign the caller's variable, and strings have no in-place mutation methods.

**"`new String()` is better than `""` because it creates a dedicated empty value?"** For normal empty-string needs, the `""` literal is shorter, clearer, and avoids deliberately creating an extra wrapper.

## 8. Self-Check

Predict the four lines of output:

```java
String first = "core";
String second = first;
String third = new String(first);

second = second.concat("-java");

System.out.println(first);
System.out.println(second);
System.out.println(first == third);
System.out.println(first.equals(third));
```

Answer:

```text
core
core-java
false
true
```

`second` is reassigned the result of `concat`; `first` remains `"core"`. `third` is a different object because of `new`, yet its content still equals `first`.

Two self-assessment questions:

1. In a getter returning a `private final String name` field, does `return new String(name)` make the data safer? **No:** `String` is already immutable.
2. Can `new String(bytes, StandardCharsets.UTF_8)` be replaced with `String text = bytes` when reading network data? **No:** `byte[]` is not a `String`; bytes must be decoded with an appropriate charset.

**Remember:** `String b = a` reuses an immutable value; `new String(a)` creates a new `String` object with the same content, which is usually redundant. `String` constructors are genuinely useful when the input is **a character array, bytes, or data that must be converted into a string**.