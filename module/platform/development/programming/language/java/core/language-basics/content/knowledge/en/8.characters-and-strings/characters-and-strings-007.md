# Comparing Content with `equals()` Instead of `==` in Java

> **Java core — language-basics / Characters and Strings**  
> **Requirements:** JDK 17+, no external libraries used.  
> **Goal:** Understand why `==` is not how to check `String` content; use `equals()`, `Objects.equals()`, and `equalsIgnoreCase()` in the right contexts, avoiding `null` errors and seemingly random results caused by the string pool.

## 1. `==` and `equals()` answer two different questions

A `String` variable is a **reference** to a string object. Two variables can point to **two different objects** whose internal text content is identical.

| Expression | With two `String` references | When to use? |
| --- | --- | --- |
| `a == b` | Checks **same reference / same object** (or both `null`) | When you genuinely need to check identity, or check `a == null` |
| `a.equals(b)` | Checks **content** of two strings according to `String.equals` rules | When you want exact text comparison and know `a != null` |
| `Objects.equals(a, b)` | Compares content like `equals` but is safe if one or both values are `null` | When one or both references can be `null` |
| `a.equalsIgnoreCase(b)` | Compares content **case-insensitively** according to Java's rules | When business requirements are truly case-insensitive |

Core example:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: two different objects.
System.out.println(first.equals(second)); // true: identical content.
~~~

`String.equals(Object)` compares strings by their sequence of **UTF-16 code units** and is case-sensitive. It returns `false` when the argument is `null` or not a `String`; it does not coerce numbers or strip whitespace to try to make two values equal.

**Practical rule:** To know whether two strings carry the **same text value**, prefer `equals` (or `Objects.equals` when null-safety is needed), not `==`.

## 2. Why does `==` on Strings sometimes evaluate to `true`?

Java has a **string pool** for string literals. Within the same program, two literals with equivalent content typically share the same interned string object:

~~~java
String a = "Java";
String b = "Java";

System.out.println(a == b);      // true due to the same interned literal.
System.out.println(a.equals(b)); // true because content is identical.
~~~

The `a == b` result in that situation **does not prove** that `==` is content comparison. When creating an object with `new String("Java")` or concatenating strings at runtime, identical content can still have different references:

~~~java
String pooled = "Java";
String copied = new String("Java"); // Used only to illustrate reference identity.
String part = "Ja";
String combined = part + "va";      // Concatenated at runtime.

System.out.println(pooled == copied);    // false
System.out.println(pooled.equals(copied)); // true
System.out.println(pooled == combined);  // false
System.out.println(pooled.equals(combined)); // true
~~~

Do not try to rely on JVM string optimizations or on whether a string came from a literal, file, user input, or API to use `==` instead of `equals`. `new String(...)` is rarely needed in real application code; it appears here to demonstrate two distinct objects.

## 3. Runnable Java 17+ program

Create the file **StringEqualsDemo.java**:

~~~java
import java.util.Objects;

public final class StringEqualsDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String alias = literal;
        String separate = new String("Java");
        String part = "Ja";
        String computed = part + "va";
        String lower = "java";
        String missing = null;

        System.out.println("sameReference=" + (literal == alias));
        System.out.println("differentReference=" + (literal == separate));
        System.out.println("sameContent=" + literal.equals(separate));
        System.out.println("computedReference=" + (literal == computed));
        System.out.println("computedContent=" + literal.equals(computed));

        System.out.println("caseSensitive=" + literal.equals(lower));
        System.out.println("ignoreCase=" + literal.equalsIgnoreCase(lower));
        System.out.println("spacesMatter=" + literal.equals(" Java "));
        System.out.println("trimmed=" + literal.equals(" Java ".trim()));

        System.out.println("isNull=" + (missing == null));
        System.out.println("constantFirst=" + "Java".equals(missing));
        System.out.println("bothNull=" + Objects.equals(missing, null));
        System.out.println("oneNull=" + Objects.equals(literal, missing));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicodeForms=" + composed.equals(decomposed));

        if ("Java".equals(computed)) {
            System.out.println("decision=match");
        }
    }
}
~~~

Compile and run from the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 StringEqualsDemo.java
java StringEqualsDemo
~~~

**Exact expected output:**

~~~text
sameReference=true
differentReference=false
sameContent=true
computedReference=false
computedContent=true
caseSensitive=false
ignoreCase=true
spacesMatter=false
trimmed=true
isNull=true
constantFirst=false
bothNull=true
oneNull=false
unicodeForms=false
decision=match
~~~

**How to verify:**

- `literal` and `alias` point to the same object, so `==` is `true`. `separate` is a new object, so `==` is `false` even though `equals()` is `true`.
- `computed` is created by a variable-dependent concatenation at runtime. Its content equals `"Java"`, yet it does not share a reference with the literal.
- `equals()` distinguishes `"Java"` and `"java"`; `equalsIgnoreCase()` returns `true`. Leading/trailing whitespace also makes `equals` return `false` if data has not been normalized.
- `"Java".equals(missing)` is safe and returns `false`. `Objects.equals(null, null)` returns `true`; `Objects.equals("Java", null)` returns `false`.
- `"\u00E9"` is the character `é` written as one code point, whereas `"e\u0301"` is `e` plus a combining acute accent; they may look identical visually, yet they have **different UTF-16 sequences**, so `equals` returns `false`.

## 4. Safe comparison when `null` is possible

If `input` can be `null`, calling `input.equals("OK")` will throw `NullPointerException`.

~~~java
String input = null;
// boolean bad = input.equals("OK"); // Throws NullPointerException if executed.
boolean safe = "OK".equals(input);   // false
~~~

**Three common approaches:**

| Situation | How to write |
| --- | --- |
| Know `input` is not `null` | `input.equals(expected)` |
| Comparing against a fixed string when `input` can be `null` | `"OK".equals(input)` |
| Both variables can be `null` | `Objects.equals(left, right)` |

`Objects.equals(left, right)` returns `true` if **both are `null`**. If business logic treats “two missing values” as *not equal*, write a dedicated rule such as `left != null && left.equals(right)`.

Note: `String.equals(null)` **does not throw an exception** when the left-hand object is non-`null`; it returns `false`. The exception happens when the **left-hand reference** is `null` and you still call a method on it.

## 5. Distinguishing exact content from normalized content

Because `String.equals` checks exact content, nearly similar strings are not automatically considered equal:

- **Letter case:** `"Java".equals("java")` is `false`.
- **Whitespace:** `"Java".equals(" Java ")` is `false`.
- **Unicode:** strings with visually identical characters using different code point sequences may not be `equals`.

When business requirements allow normalization, perform it **explicitly before comparing**:

~~~java
String expected = "Java";
String input = " java ";
boolean accepted = expected.equalsIgnoreCase(input.strip());
System.out.println(accepted); // true
~~~

However, **do not always strip or ignore case**: passwords, case-sensitive identifiers, and content that must be preserved verbatim may require exact comparison. `equalsIgnoreCase` is also not a universal tool for all locale-specific casing rules, Unicode normalization, or locale-aware comparison.

When Unicode normalization is genuinely needed, Java provides `java.text.Normalizer`; that is a separate processing step and is **not** performed automatically by `equals`.

## 6. Common traps

| Code line or statement | What is wrong and how to fix |
| --- | --- |
| `if (username == "admin")` | `==` compares references; use `"admin".equals(username)` for exact content comparison |
| `new String("x") == new String("x")` | `false` because of two distinct objects; use `equals` |
| “Two literals give `== true`, so comparing content with `==` is enough.” | False: the string pool does not guarantee all `String`s with equal content share a reference |
| `input.equals("YES")` when `input` can be `null` | Risk of NPE; use `"YES".equals(input)` or `Objects.equals` |
| `"a".equals("A")` | `false`; only use `equalsIgnoreCase` if case-insensitivity is required |
| `"a".equals(" a ")` | `false` because whitespace differs |
| Comparing `StringBuilder` with `equals` expecting character comparison | `StringBuilder` does not override `Object.equals` to compare content; if needed, compare `toString()` of the two builders |

### Self-practice exercises

**Exercise 1.** Given `String x = "hello"; String y = new String("hello");`, predict `x == y` and `x.equals(y)`, explaining without relying on whether the string pool exists or not.

**Exercise 2.** Given `String input = null;`, write three safe ways to check whether input has content `"YES"` or report missing data. Is `Objects.equals(null, null)` appropriate if two fields have both been left blank?

**Exercise 3.** Write a condition that accepts `"yes"`, `"YES"`, and `" Yes "`, while rejecting `"y"`. Normalize only when business logic permits.

**Exercise 4.** Try comparing `"\u00E9"` with `"e\u0301"` yourself. Why can a user see the same letter while `equals` returns `false`? Under what conditions is Unicode normalization needed?

**Exercise 5.** Create two `StringBuilder`s containing `"abc"`, and test `a.equals(b)` and `a.toString().equals(b.toString())`. When is content comparison appropriate for your goal?

### Key takeaway

**For `String`, `==` asks “same object?”; `equals()` asks “same content?”.** Use `equals` to compare text values; prefer `"literal".equals(value)` or `Objects.equals(a, b)` when `null` safety is needed. Do not confuse string pool effects, data normalization, or `equalsIgnoreCase` with the exact comparison rules of `String.equals`.
