# Why Is `String` a `final` Class and Immutable in Java?

`String` is a reference type used to represent character strings in Java. The class declaration in Java 17+ has the form `public final class String ...`. The Java documentation states clearly: **the value of a `String` object cannot be changed after the object is created** (*immutable*). Both `final` and *immutable* complement each other so that strings can be safely shared, behave predictably, and be optimized effectively.

After this lesson, you should be able to distinguish `final` on a class, `final` on a reference variable, and object immutability; explain why string operations do not modify the original string; and apply that understanding when comparing strings, using the String Pool, using strings as `HashMap` keys, or handling strings in multi-threaded programs.

## 1. `final` and immutable are two different concepts

| Concept | What is guaranteed | What is **not** automatically guaranteed |
| --- | --- | --- |
| `final class` | Cannot declare a subclass inheriting from that class. | Objects of the class are not necessarily immutable. |
| `final` on a reference variable | Cannot reassign the variable to point to another object after initialization. | The object the variable points to can still change if its type allows it. |
| Immutable object | The observable state of the object does not change after creation. | The class itself does not have to be declared `final` in every design. |

**`String` is `final`** means `class MyString extends String` is invalid: the compiler reports an error because a final class cannot be subclassed. This is a **data-type-level** constraint.

**`String` is immutable** means that after creating `String s = "Java";`, the content of the `"Java"` object cannot be changed into `"Kava"` through the regular API. This is a guarantee about **object state**.

The following example illustrates that `final class` alone does not make an object immutable (class definition snippet, without a `main` method):

```java
final class Counter {
    private int value;

    void increment() {
        value++; // The state of Counter still changes.
    }

    int value() {
        return value;
    }
}
```

Conversely, even without writing `final String s`, a `String` object is still immutable:

```java
String s = "Java";
s = "Kotlin"; // Valid: variable s is reassigned to another String object.
```

If you declare `final String s = "Java";`, then `s = "Kotlin";` is a compile error due to **reference reassignment**. It does not make the `"Java"` object “more immutable” because that object is already immutable. Similarly, `final StringBuilder builder = new StringBuilder("A");` still allows `builder.append("B")`, because `StringBuilder` has mutable state.

## 2. How does `String` preserve immutability?

A class that provides immutability must protect its internal state and provide no path to modify that state from the outside. `String` achieves this through its API contract and Java library implementation:

1. **Provides no in-place modification methods.** There is no `setCharAt`, `append`, or `delete` on `String`. Methods such as `concat`, `replace`, `substring`, `toUpperCase`, `toLowerCase`, etc. return a `String` result; they do not alter the content of the receiving object.
2. **Does not let caller code tamper with the memory holding string content.** For instance, the `String(char[])` constructor copies the passed-in array's contents. `toCharArray()` returns a new array; modifying that input or output array cannot modify the string.
3. **Prevents inheritance with `final`.** No subclass can add mutable state or override behavior to break `String`'s contract when an object is used through the `String` type.
4. **Keeps internal state under the library/JVM's control.** In modern JDKs, the internal representation can be optimized without changing the semantics of the public API.

`final` **does not create immutability by itself**; designing without a path to mutate values is the foundation. However, `final` helps Java guarantee that every object of type `String` adheres to the class's exact contract, preventing external code from creating a subclass with unexpected behavior.

### Internal representation is not a public contract

Many Java 8 resources describe `String` as holding a `char[]` array. Since Java 9, OpenJDK uses **Compact Strings** (JEP 254): content can be stored in a `byte[]` together with Latin-1 or UTF-16 encoding information to reduce memory when appropriate. This is an implementation detail; **do not infer immutability merely from the existence of `final byte[]`**. A `final` variable pointing to an array can still point to an array whose elements are modified if access is not protected. `String`'s immutability comes from its overall design and contract.

## 3. Experiment: operations produce new results while the original string stays intact

Create the file `StringImmutabilityDemo.java`:

```java
import java.util.Locale;

public class StringImmutabilityDemo {
    public static void main(String[] args) {
        String source = "Java";
        String extended = source.concat(" 17");

        System.out.println("source = " + source);
        System.out.println("extended = " + extended);
        System.out.println("same object = " + (source == extended));

        String lower = source.toLowerCase(Locale.ROOT);
        System.out.println("lower = " + lower);
        System.out.println("source after toLowerCase = " + source);

        char[] input = {'J', 'a', 'v', 'a'};
        String copied = new String(input);
        input[0] = 'X';
        System.out.println("copied after input changed = " + copied);

        char[] output = copied.toCharArray();
        output[0] = 'Y';
        System.out.println("copied after output changed = " + copied);
    }
}
```

Compile and run with JDK 17+:

```bash
javac StringImmutabilityDemo.java
java StringImmutabilityDemo
```

Output:

```text
source = Java
extended = Java 17
same object = false
lower = java
source after toLowerCase = Java
copied after input changed = Java
copied after output changed = Java
```

Explanation:

- `source.concat(" 17")` returns a string with different content. `source` remains `"Java"`, while `extended` contains `"Java 17"`; since their contents differ, they are definitely not the same object.
- `toLowerCase(Locale.ROOT)` returns the lowercase result without modifying `source`. For methods whose result is **unchanged** (e.g., concatenating an empty string), the implementation **may return the current object itself**. Therefore, you must not claim “every call on `String` always allocates a new object.”
- Changing `input` after the constructor, or changing the array returned by `toCharArray()`, does not affect `copied`. This is a direct example of not exposing mutable internal state.

The statement `s += "!"` must also be understood correctly: its result is equivalent to `s = s + "!"`, meaning the expression produces the concatenated string value and then **reassigns the variable `s`**; the old string object is not altered. If multiple variables reference the old string, they continue to see the old content.

## 4. Why did Java design `String` to be both `final` and immutable?

### 4.1. Safe string sharing and the String Pool

Java uses the **String Pool** to reuse objects representing the same string constants, especially literals like `"java"`. If one party could modify the content of a shared object, other places sharing that object would be affected unintentionally. Immutability makes sharing safe.

Complete example, saved as `StringPoolDemo.java`:

```java
public class StringPoolDemo {
    public static void main(String[] args) {
        String a = "java";
        String b = "java";
        String c = new String("java");
        String canonical = c.intern();

        System.out.println("a == b: " + (a == b));
        System.out.println("a == c: " + (a == c));
        System.out.println("a.equals(c): " + a.equals(c));
        System.out.println("a == canonical: " + (a == canonical));
    }
}
```

Run:

```bash
javac StringPoolDemo.java
java StringPoolDemo
```

Output:

```text
a == b: true
a == c: false
a.equals(c): true
a == canonical: true
```

- Both `"java"` literals in the example point to the same interned string object.
- `new String("java")` creates a different `String` object with the **same content**.
- `intern()` returns the canonical reference for the corresponding string in the pool.
- Use `equals()` to check **content**; `==` compares **references**. Do not use `==` to compare string content coming from user input, files, or APIs.

Note: a concatenation expression of **compile-time string constants** can become a single literal; concatenating runtime data creates results via a different mechanism. Do not guess the result of `==` solely from how a concatenation expression is written.

### 4.2. Stable `HashMap` and `HashSet` keys

Hash-based structures use `hashCode()` and `equals()` to organize and look up elements. When a `String` is used as a key, its content never changes, so the key's hash value and content-comparison result remain stable. As a result, a key does not logically “move” after being placed into a hash table.

Small snippet inside a Java method:

```java
Map<String, Integer> counts = new HashMap<>();
String key = "user:42";
counts.put(key, 1);

key = key.concat(":active"); // Reassigns the key variable to another string.
System.out.println(counts.get("user:42"));    // 1
System.out.println(counts.get(key));          // null
```

This snippet requires `import java.util.Map;` and `import java.util.HashMap;` if placed in a standalone class. The `"user:42"` key inside `counts` remains intact. Caching the hash code for reuse in certain `String` implementations is also feasible because the content never changes; the exact caching strategy is an implementation detail.

With **a key object whose fields used in `equals()/hashCode()` are mutated after insertion into a `HashMap`**, lookups can fail. `String` completely avoids this category of bugs at the string-content level.

### 4.3. Easy sharing across threads

Multiple threads can simultaneously **read and share the same `String` object** without locks to guard against content modification: no thread can change that object's content through the normal API. This reduces race conditions related to object state.

However, **immutable does not mean the entire program is automatically thread-safe**. For example, if two threads both reassign a `String currentName` field, publishing the new value, cross-thread visibility, and multi-step operations may still require `volatile`, `synchronized`, or an appropriate synchronization mechanism. Immutability only guarantees that the content of **each individual `String` object** is not mutated.

### 4.4. Preserving API contracts and preventing unintended data changes

`String` often represents filenames, paths, configuration keys, URLs, identifiers, or validated parameters. A method accepting a `String` can trust that **the content of that exact object** will not be silently altered by the caller after being passed in. If subclasses could alter behavior or state could be mutated, API assumptions, hash codes, and shared-reference sites could all break.

This benefit does not replace input validation, authorization, or synchronization when new data is assigned to a variable. Nor does immutability automatically make user-supplied values safe.

## 5. Which API should you choose when working with `String`?

| Need | Suitable choice | Reason |
| --- | --- | --- |
| Stable text values, passing between methods, map keys | `String` | Easy to share, no in-place content mutation. |
| Building a few simple concatenation expressions | `+` operator with `String` | Clear, compiler/JVM can optimize; no need for premature optimization. |
| Joining many parts in a loop or building text step by step | `StringBuilder` | Provides `append`, `insert`, `delete` mutating a buffer; typically avoids creating many intermediate values. |
| Mutable text buffer shared across threads needing synchronized methods | `StringBuffer` in appropriate contexts | Main methods are synchronized; multi-step operations still require considering atomicity. |

Example of building a string in a loop using `StringBuilder`:

```java
StringBuilder builder = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        builder.append(", ");
    }
    builder.append(i);
}
String result = builder.toString(); // "1, 2, 3"
```

`StringBuilder` mutates its state while assembling the result. `toString()` returns an immutable `String` for further use or sharing. `StringBuilder` does not automatically guarantee safety when multiple threads concurrently modify one instance.

## 6. Common misconceptions and mistakes

1. **“`final` is enough to make an object immutable.”** False: the `Counter` example above is a `final` class yet has a `value` field that gets incremented.
2. **“`final String s` means the content is now immutable.”** False: every `String` is immutable; `final` on `s` only forbids reassigning the reference.
3. **“`replace()` or `toUpperCase()` modifies the original variable.”** False: you must capture the result if you want to use it, e.g., `s = s.replace("a", "b");`. Calling it and discarding the return value does not change the held string.
4. **“Every `String` processing method creates a new instance.”** False: a method may return the same instance if the result is unchanged (and literals are shared by the pool).
5. **“If two strings have equal content, `==` is always `true`.”** False: `==` asks whether they share the same reference; `equals()` compares content per `String`'s API.
6. **“The String Pool is the reason `String` is immutable.”** The relationship actually goes the other way: immutability **enables** the pool to share objects without worrying that one consumer will mutate another consumer's data.
7. **“Using `String` means you never need to worry about synchronization.”** False for variables or data structures referencing `String` that are updated by multiple threads.
8. **“The length of a `String` always equals the number of visible characters.”** `length()` counts **UTF-16 code units**; a Unicode character outside the BMP can occupy two units. Use `codePointCount(0, s.length())` when counting code points; visible characters with combining marks remain a separate concern.
9. **“Passwords should always be stored in `String`.”** Because `String` content cannot be erased in place, applications handling sensitive secrets may prefer `char[]` or `byte[]` when protocols/libraries allow zeroing the buffer after use. That must still be paired with proper data lifecycle management and security practices.

## 7. How to test your understanding

Consider the snippet:

```java
String x = "Hi";
String y = x;
x = x.concat(" Java");

System.out.println(x);
System.out.println(y);
System.out.println(x == y);
```

The output is:

```text
Hi Java
Hi
false
```

Explanation: initially `x` and `y` both reference `"Hi"`. Concatenation creates the value `"Hi Java"`; only variable `x` is assigned the resulting reference. `y` continues holding `"Hi"` and the old object does not change.

**Remember the three layers:** `final class String` blocks inheritance; immutability protects each object's content; and `final String variable` only prevents reassigning a reference variable. This combined design lets `String` be shared safely in the pool and across threads, keeps hash keys stable, and makes text data flow easier to reason about.

## References

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `final` declaration, immutability, constructors, `equals`, `intern`, and string APIs.
- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254): internal representation change since Java 9; does not change the public interface or immutability contract.