# String Pool and Literal Sharing in Java

## 1. What Is the String Pool?

The **String pool** (or *string intern pool*) is the mechanism Java uses to manage *interned* strings: each string content has one *canonical reference* in the pool at a given time. When Java code uses a literal such as `"Java"`, the JVM uses the reference of the corresponding interned string; multiple occurrences of the same literal can share a single `String` object.

```java
String first = "Java";
String second = "Java";

System.out.println(first == second);      // true
System.out.println(first.equals(second)); // true
```

Both comparisons return `true`, but **for two different reasons**:

- `first == second` is true because both variables reference **the same interned `String` object**.
- `first.equals(second)` is true because the two strings have **the same content**.

`String` itself is **immutable**: once an object is created, its characters do not change. Because of that, places sharing a reference to a literal cannot modify its content and affect one another. This is an important foundation for safely sharing strings through the pool.

**Limitation to remember:** The pool does not mean that every `String` object with the same content is the same object. Java still allows creating distinct `String` objects for which `equals()` returns `true`.

## 2. How Are Literals Shared?

A **string literal** is a string written directly in source code, for example `""`, `"hello"`, `"Hello, Java"`. The Java Language Specification specifies that string literals (and the values of constant expressions of type `String`) are interned, so that equal contents share a canonical reference.

```java
String a = "hello";
String b = "hello";
String c = "world";

System.out.println(a == b); // true
System.out.println(a == c); // false
```

The first line compares two identical literals, so it is `true`. The second line has two different contents, so they cannot be the same string, returning `false`.

You can picture it as:

```text
                  String pool (conceptual model)

a --------------------+
                      +----> String "hello"
b --------------------+

c --------------------------> String "world"
```

The diagram only illustrates **reference sharing**; it does not assert the memory layout, addresses, or implementation algorithm of any specific JVM.

### Identical literals can appear in multiple places in a program

If different classes, methods, or parts of a program running in the same JVM use string literals with the same content, those literals are interned and can share references to the canonical string. This mechanism does not require the programmer to manually call `intern()` on each literal.

**Do not infer the number of objects merely by counting lines of code:** A literal appearing multiple times does not imply that many objects exist, and when objects are created or retrieved from the pool depends on class loading, linking, execution, and implementation details.

## 3. Verifying Literal Sharing Across Two Classes

The example above used only one method; let's try writing literals with the same content in **two different classes** in the file `LiteralAcrossClasses.java`:

~~~java
class LiteralProvider {
    static String getLabel() {
        return "java-pool";
    }
}

public class LiteralAcrossClasses {
    public static void main(String[] args) {
        String local = "java-pool";
        String anotherClass = LiteralProvider.getLabel();
        String constructed = new String("java-pool");

        System.out.println(local == anotherClass);
        System.out.println(local == constructed);
        System.out.println(local.equals(constructed));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LiteralAcrossClasses.java
java LiteralAcrossClasses
~~~

~~~text
true
false
true
~~~

Two identical literals share a reference even across two classes. `constructed` is a separate object created by `new`, yet it has equal content. The fact that class files have their own constant pool tables does **not** mean each class has its own separate string pool: class file metadata and runtime interned objects are two different layers.

## 4. Connection to Immutability and Data Structures

The pool works safely because `String` is immutable. For example:

```java
String one = "color";
String two = "color";

one = one.replace('c', 'C');

System.out.println(one); // Color
System.out.println(two); // color
```

`replace()` returns a string with different content; the original `"color"` object is not modified. Changing `one`'s reference does not affect `two`.

Similarly, `String` is suitable as a key for `HashMap` because the content used by `equals()` and `hashCode()` does not mutate after insertion. Being interned is **not a requirement** for `HashMap` to recognize two string keys as equal:

```java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
counts.put("Java", 5);

String key = new String("Java");
System.out.println(counts.get(key)); // 5
```

`HashMap` uses `hashCode()` and `equals()` according to the key contract; it does not require two keys to point to the same object.

Nor do the pool and immutability automatically make every operation on a `String` variable shared across threads safe with respect to execution order or visibility. Sharing **immutable object content** and updating a **shared reference variable** are two different things; the latter still must follow the Java Memory Model and an appropriate synchronization strategy.

## 5. Limits of What Can Be Observed

- The pool manages **interned strings**, not every `String` created from files, requests, JSON, or runtime concatenation.
- `"Ja" + "va"` is a constant expression whose value is `"Java"`, so it is interned; concatenation with a non-constant variable is a different case. The lesson on constant expressions and runtime concatenation analyzes this boundary.
- `intern()` retrieves the **canonical reference** for the content; it does not modify the variable on which the method is called, nor does it normalize letter case, whitespace, or Unicode.
- Do not infer memory locations or allocation counts from the number of literals in source code. Class resolution, timing of use, and JVM optimizations may vary.
- In content-checking logic, use `equals()`; a `== true` result on literals only proves that two references point to the same object.

## 6. Self-Check

Predict the following four outputs:

```java
String x = "code";
String y = "co" + "de";
String part = "co";
String z = part + "de";
String t = new String("code");

System.out.println(x == y);
System.out.println(x == z);
System.out.println(x == t);
System.out.println(z.intern() == x);
```

Output:

```text
true
false
false
true
```

Explanation: `y` is the result of a constant expression and is interned; `z` is a concatenation with a variable performed at runtime; `t` is a separate object created via `new`; `z.intern()` returns the canonical reference of the literal `"code"`.

**Remember:** *Same content* (`equals`) and *same object* (`==`) are two different concepts. The String pool lets literals and interned strings share a canonical reference; it is not the content-comparison rule for Java programs.