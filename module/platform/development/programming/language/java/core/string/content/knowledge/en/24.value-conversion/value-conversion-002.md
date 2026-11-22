# Distinguishing `String.valueOf(Object)` and `String.valueOf(char[])` When Passing `null`

The same `String.valueOf` call, with the same `null` data, yet the **argument type at compile time** determines which overload is invoked. This is a common trap in Java:

```java
String a = String.valueOf((Object) null); // "null"
String b = String.valueOf((char[]) null); // NullPointerException
String c = String.valueOf(null);          // NullPointerException
```

Among the three statements above, `a` is assigned successfully. The other two statements compile, but **throw a `NullPointerException` at runtime**. This comes from Java's *overload resolution*, not because the `null` value changes.

## 1. Two Important Overloads of `String.valueOf`

`String` has several static methods named `valueOf` to convert data to a string. When passing `null`, the two overloads accepting reference types below are the focus:

```java
public static String valueOf(Object obj);
public static String valueOf(char[] data);
```

The overloads for `boolean`, `char`, `int`, `long`, `float`, and `double` accept **primitive types**. The `null` value cannot be converted to a primitive type for direct invocation, so they do not compete when the argument is the `null` literal.

| Overload | With a non-`null` argument | With `null` |
| --- | --- | --- |
| `valueOf(Object obj)` | Returns the result of `obj.toString()` | Returns the **four-character string `"null"`** |
| `valueOf(char[] data)` | Creates a string containing the characters of the array | Throws **`NullPointerException`** |

### `valueOf(Object)` handles `null` specially

Conceptually, the `Object` overload behaves similarly to:

```java
static String objectToText(Object obj) {
    return (obj == null) ? "null" : obj.toString();
}
```

This is **illustrative behavior code**, not a copy of the JDK source code. When the argument is `null`, the result is a `String` object containing the text `null`, **not a `null` reference**.

```java
String result = String.valueOf((Object) null);
System.out.println(result.equals("null")); // true
System.out.println(result == null);        // false
```

### `valueOf(char[])` requires a real array

The overload taking `char[]` uses the elements of the character array to create a new `String`:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = String.valueOf(letters);
System.out.println(text); // Java
```

If `data` is `null`, there is no array to read. The method **does not convert `null` into the text `"null"`**, but throws `NullPointerException`. Passing an empty array `new char[0]` is valid and creates an empty string `""`: an empty array is different from a `null` array reference.

## 2. Why Does `String.valueOf(null)` Call the `char[]` Overload?

Java decides which method is called based on the **type of the argument expression at compile time**, following the overload selection rules of the Java language.

With the call:

```java
String.valueOf(null)
```

The `null` literal can be used in the argument position of a method accepting a **reference type**. Between the two applicable overloads:

```java
String.valueOf(Object obj);
String.valueOf(char[] data);
```

`char[]` is a **subtype of the reference type `Object`**: every Java array is an object and can be assigned to a variable of type `Object`. Therefore `valueOf(char[])` is considered **more specific** than `valueOf(Object)`.

Java picks the most specific method among the applicable overloads. Thus:

```text
Argument: null literal
    |
    +-- valueOf(Object) : applicable
    |
    +-- valueOf(char[]) : applicable, more specific than Object
                              |
                              +--> selected at compile time
                                    |
                                    +--> executed with a null array
                                              |
                                              +--> NullPointerException
```

**There is no "ambiguous method call" error** here because Java has a more specific choice. Nor is there **any fallback step to try `Object` after the `char[]` overload throws an error**: the overload is already fixed before execution.

Note: `char[]` is not a subtype of `String`. Java does not have a `String.valueOf(String)` overload; casting `(String) null` goes through `Object`. If a custom API has two overloads taking unrelated reference types that are both applicable, a `null` literal may make the call ambiguous; that is a different situation from the `Object` and `char[]` pair.

## 3. Comparing All Common Ways of Passing `null`

| Java expression | Overload chosen at compile time | Result |
| --- | --- | --- |
| `String.valueOf(null)` | `char[]` | `NullPointerException` |
| `String.valueOf((Object) null)` | `Object` | `"null"` |
| `String.valueOf((char[]) null)` | `char[]` | `NullPointerException` |
| `String.valueOf((String) null)` | `Object` | `"null"` |
| `String.valueOf((int[]) null)` | `Object` | `"null"` |
| `Object o = null; String.valueOf(o)` | `Object` | `"null"` |
| `char[] chars = null; String.valueOf(chars)` | `char[]` | `NullPointerException` |
| `String s = null; String.valueOf(s)` | `Object` | `"null"` |

`(Object) null` is an **explicit cast**: we tell the compiler that the passed expression has type `Object`, so the `char[]` overload is no longer applicable.

`(char[]) null` casts in the opposite direction: forcing the compiler to treat the argument as `char[]`, thus selecting the `char[]` overload and failing when using a null array.

`(String) null` has static type `String`, which is a subtype of `Object` but **not** a subtype of `char[]`. Therefore it is treated as an `Object` argument.

Similarly, `int[]` is an array type but **cannot** be converted to `char[]`; hence `String.valueOf((int[]) null)` also calls the `Object` overload.

**Important:** Java does not inspect an object's runtime type to switch from the `Object` overload to `char[]`. Overload selection differs from *overriding* (instance method polymorphism).

## 4. Standalone Runnable Java 17+ Example

Create the file `ValueOfNullOverloadsDemo.java`:

```java
import java.util.function.Supplier;

public class ValueOfNullOverloadsDemo {

    private static void check(String label, Supplier<String> action) {
        try {
            System.out.println(label + " -> " + action.get());
        } catch (NullPointerException ex) {
            System.out.println(label + " -> NullPointerException");
        }
    }

    public static void main(String[] args) {
        check("literal", () -> String.valueOf(null));
        check("(Object)null", () -> String.valueOf((Object) null));
        check("(char[])null", () -> String.valueOf((char[]) null));
        check("(String)null", () -> String.valueOf((String) null));

        Object obj = null;
        char[] chars = null;
        String string = null;

        check("Object variable", () -> String.valueOf(obj));
        check("char[] variable", () -> String.valueOf(chars));
        check("String variable", () -> String.valueOf(string));

        char[] data = {'J', 'a', 'v', 'a'};
        System.out.println("char[] content -> " + String.valueOf(data));

        // Do not print the object hash code because it can change across runs.
        String objectText = String.valueOf((Object) data);
        System.out.println("Object-char[] uses array identity -> "
                + objectText.startsWith("[C@"));
    }
}
```

Use JDK 17 or newer to run:

```bash
javac ValueOfNullOverloadsDemo.java
java ValueOfNullOverloadsDemo
```

Stdout result:

```text
literal -> NullPointerException
(Object)null -> null
(char[])null -> NullPointerException
(String)null -> null
Object variable -> null
char[] variable -> NullPointerException
String variable -> null
char[] content -> Java
Object-char[] uses array identity -> true
```

The `check` method intentionally catches `NullPointerException` **only to demonstrate and allow the program to continue running** through every case. In real programs, check the data before calling if `null` may appear; do not use exceptions as normal control flow.

`ex.getMessage()` or a stack trace is not included in stdout because the exact error message may vary across JDK versions. The example keeps the output clear and stable by printing the exception type name.

## 5. What Happens with a Non-`null` `char[]` Array?

The difference between the two overloads exists **even when the array has content**:

```java
char[] data = {'O', 'K'};

String byChars = String.valueOf(data);          // char[] overload
String byObject = String.valueOf((Object) data); // Object overload

System.out.println(byChars);                    // OK
System.out.println(byObject.startsWith("[C@")); // true
```

When calling `valueOf(char[])`, Java converts **the character elements** into a string. When calling `valueOf(Object)` with a character array, Java calls `toString()` on the **array object** itself. Java arrays by default do not override `Object.toString()` to list their elements, so they are usually represented by their type name and identity code, such as `[C@...`, where `[C` is the JVM type name for `char[]` and the suffix may vary.

Therefore, casting `(Object) data` is a way to **select the `Object` overload**, not a way to convert `char[]` content to a string. It is only useful in contexts where `Object` conversion rules are needed, especially when you want `null` represented as the string `"null"`.

In addition, `valueOf(char[])` creates string content independent of the original array:

```java
char[] data = {'O', 'K'};
String text = String.valueOf(data);
data[0] = 'N';
System.out.println(text); // OK
```

Arrays are mutable, whereas `String` is immutable; modifying the array after creating the string does not change `text`.

## 6. Why Doesn't an `Object` Variable Automatically Call `char[]`?

Consider:

```java
char[] source = {'H', 'i'};
Object asObject = source;

String s1 = String.valueOf(source);   // char[] overload
String s2 = String.valueOf(asObject); // Object overload
```

`source` and `asObject` point to **the same array object**, yet the compiler sees their types as `char[]` and `Object`, respectively. Hence, `s1` holds `"Hi"`; `s2` holds the default array object representation such as `[C@...`.

The same applies to `null`:

```java
char[] chars = null;
Object obj = chars;

String a = String.valueOf(obj);   // "null"
String b = String.valueOf(chars); // NullPointerException
```

The difference arises **from the static type of the expression**. Do not guess the overload based on the runtime type a variable might point to.

A method taking a parameter of type `Object` will always call the `valueOf(Object)` version for the call inside it:

```java
static String convert(Object value) {
    return String.valueOf(value);
}
```

This is an **illustrative snippet that must be placed inside a class**, not a standalone program. Calling `convert(null)` returns `"null"`. Calling `convert(new char[] {'A', 'B'})`, however, does not produce `"AB"`, because the `Object` overload treats the array as an object.

## 7. Safe Handling in Real Code

### Goal A: every `null` becomes the string `"null"`

If the argument can have various types and you want `null` to become the text `"null"`, call the `Object` overload explicitly:

```java
String result = String.valueOf((Object) null);
```

With a variable of static type `Object value`, simply use `String.valueOf(value)`. However, if the value is **not null** and happens to be an array, `Object.toString()` does not necessarily return the contents of its elements. Choose according to your exact intent.

### Goal B: need `char[]` content and `null` may occur

Check the array before calling the `char[]` overload:

```java
static String safeChars(char[] chars) {
    return chars == null ? "null" : String.valueOf(chars);
}
```

The method above must be declared inside a class. It returns the string `"null"` when the array does not exist, and returns the **character content** when the array has data. If `null` should mean "no value" instead of the word `"null"`, use an appropriate convention, for example:

```java
static String displayChars(char[] chars) {
    return chars == null ? "<missing>" : String.valueOf(chars);
}
```

`"<missing>"` is just a program-defined placeholder; it is not a value automatically produced by Java.

### Goal C: need a default string for any object

`java.util.Objects.toString(obj, nullDefault)` lets you specify replacement text for `null`:

```java
import java.util.Objects;

// Illustrative snippet inside a method.
Object obj = null;
String result = Objects.toString(obj, "<none>");
System.out.println(result); // <none>
```

If `obj` actually points to a non-null `char[]`, `Objects.toString` still calls `toString()` on the array object, **not** converting each character into a `String`. This method helps handle `null` in the `Object` style, not as a replacement for `String.valueOf(char[])`.

### Goal D: want the characters `"null"` printed without worrying about overload selection

If you only need to print diagnostic information, you can write:

```java
System.out.println("value=" + null);
// value=null
```

This is Java's **string concatenation (`String` concatenation)** rule, not a direct `String.valueOf(null)` call in source code. Do not infer from a concatenation expression that `String.valueOf(null)` will also return `"null"`.

## 8. Common Misconceptions

1. **"`String.valueOf(null)` always returns `"null"`."** False: calling with the null literal selects `valueOf(char[])` and throws `NullPointerException`.
2. **"Java chooses overloads based on runtime data."** False in this case: overload selection relies on the **static type** at compile time. Thus an `Object` variable and a `char[]` variable can produce different results even when pointing to the same array.
3. **"It is an ambiguity error between `Object` and `char[]`."** False: `char[]` is a subtype of `Object`, so the `char[]` overload is more specific and gets selected.
4. **"Casting to `(Object)` still returns the array content."** False for non-null `char[]` arrays: switching to the `Object` overload causes the array's default `toString()` to be used.
5. **"An empty `char[]` is equivalent to `null`."** False: `new char[0]` is a valid array and yields an empty string; `(char[]) null` is not an array and causes `NullPointerException`.
6. **"The result `"null"` is Java null."** False: it is a `String` of four characters `n`, `u`, `l`, `l`; the string object exists normally.
7. **"You should catch `NullPointerException` to fix the data."** Usually unnecessary. If `null` is allowed to appear, check with `if` or the ternary operator and decide the appropriate meaning for the application.
8. **"Using `Objects.toString` converts every array to its contents."** False: for a non-null array object, it uses that object's `toString()`.

## 9. Practice Exercises

**Question 1.** What do the three expressions below return?

```java
String.valueOf((Object) null);
String.valueOf((char[]) null);
String.valueOf(null);
```

Answers respectively: `"null"`; `NullPointerException`; `NullPointerException`.

**Question 2.** Given:

```java
Object a = null;
char[] b = null;
```

How do the calls `String.valueOf(a)` and `String.valueOf(b)` differ?

Answer: `a` has static type `Object`, so it receives the string `"null"`. `b` has static type `char[]`, so it throws `NullPointerException`.

**Question 3.** Why does `String.valueOf((String) null)` return `"null"`?

Answer: `String` is a subtype of `Object` but is incompatible with `char[]`; only the `Object` overload can accept this argument.

**Question 4.** Convert a potentially null `char[] chars` variable to text while preserving character content when the array is non-null.

Answer:

```java
String result = chars == null ? "<empty>" : String.valueOf(chars);
```

Here `"<empty>"` is an application-defined replacement value and has no direct connection to overload selection.

**Question 5.** Given `Object data = new char[] {'A', 'B'};`, does `String.valueOf(data)` return `"AB"`?

Answer: no. The `Object` overload is selected based on the static type `Object` of `data`. It uses the array object's `toString()`, producing a representation like `[C@...`, not the concatenated characters.

**Key takeaway:** `String.valueOf(null)` is dangerous because `char[]` is a more specific overload than `Object`. To handle `null` via `Object`, cast `(Object) null` or pass a variable of type `Object`. To get the content of a character array, use `valueOf(char[])` with a **non-null** array and check for null explicitly.

## Official Documentation

- [`String.valueOf(Object)` and `String.valueOf(char[])` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [JLS §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2)
- [JLS §15.12.2.5 — Choosing the Most Specific Method](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2.5)
