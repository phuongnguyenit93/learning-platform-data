# Type Pattern Combining Type Check and Variable Declaration — Java 17+

A **type pattern** with `instanceof` lets Java both check the runtime type and declare a **variable with the appropriate static type** when the check succeeds. This has been a standard feature since Java 16 and works on Java 17 **without enabling preview**.

~~~java
Object value = "Hello";

if (value instanceof String text) {
    System.out.println(text.length()); // 5
}
~~~

The syntax `expression instanceof Type variable` performs three things: checks whether the object is compatible with `Type`; if so, binds the object to `variable`; and allows using the variable in the **scope where the compiler is certain the pattern matched** (*flow scoping*).

## 1. How Does It Differ from Traditional `instanceof`?

The old approach required an explicit cast after the check:

~~~java
Object obj = "Java";
if (obj instanceof String) {
    String text = (String) obj;
    System.out.println(text.toUpperCase());
}
~~~

Using a type pattern:

~~~java
Object obj = "Java";
if (obj instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Both print `JAVA`. A type pattern removes the repetitive cast, **creates no new object**, does not turn `obj` into a variable declared as `String`, and does not alter the object's value.

| Aspect | Old Check | Type Pattern |
| --- | --- | --- |
| Type check | `obj instanceof String` | `obj instanceof String text` |
| Use as `String` | `(String) obj` | Variable `text` already has type `String` |
| New object? | No | No |
| `obj == null` | Result is false | Result is false |
| Safety | Must cast correctly | Compiler determines pattern variable scope |

## 2. Standalone Java 17+ Program

Create a UTF-8 file named **`TypePatternDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

public class TypePatternDemo {
    static void describe(Object value) {
        if (value instanceof String text) {
            System.out.println("string=" + text.toUpperCase(Locale.ROOT)
                    + ",length=" + text.length());
        } else if (value instanceof Integer number) {
            System.out.println("integerTwice=" + (number * 2));
        } else if (value == null) {
            System.out.println("null");
        } else {
            System.out.println("other="
                    + value.getClass().getSimpleName());
        }
    }

    static String normalize(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "invalid";
        }
        return text.trim().toLowerCase(Locale.ROOT);
    }

    static String classify(Object input) {
        if (input instanceof String text && text.length() >= 3) {
            return "long-enough:" + text;
        }
        return "other";
    }

    static int lengthOf(Object value) {
        if (value instanceof CharSequence chars) {
            return chars.length();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println("== old versus pattern ==");
        Object first = "Hello";
        if (first instanceof String) {
            String oldText = (String) first;
            System.out.println("old=" + oldText.substring(0, 2));
        }
        if (first instanceof String text) {
            System.out.println("pattern=" + text.substring(0, 2));
        }

        System.out.println("== matching types ==");
        describe("Java");
        describe(21);
        describe(3.5);
        describe(null);

        System.out.println("== guards and flow scope ==");
        System.out.println("normalize1=" + normalize("  JAVA  "));
        System.out.println("normalize2=" + normalize("   "));
        System.out.println("normalize3=" + normalize(12));
        System.out.println("normalize4=" + normalize(null));
        System.out.println("classifyCat=" + classify("cat"));
        System.out.println("classifyHi=" + classify("hi"));
        System.out.println("classifyNull=" + classify(null));

        System.out.println("== null and interfaces ==");
        Object missing = null;
        System.out.println("nullMatches="
                + (missing instanceof String candidate));
        System.out.println("lengthString=" + lengthOf("abc"));
        System.out.println("lengthNumber=" + lengthOf(42));
        Object integer = 7;
        if (integer instanceof Number number) {
            System.out.println("numberValue=" + number.intValue());
        }

        System.out.println("== generic wildcard ==");
        Object unknown = List.of("A", "B");
        if (unknown instanceof List<?> items) {
            System.out.println("listSize=" + items.size());
            System.out.println("firstItem=" + items.get(0));
        }

        System.out.println("== branch scope ==");
        Object item = "ready";
        if (item instanceof String text) {
            System.out.println("then=" + text);
        } else {
            System.out.println("else=not-a-string");
        }
        System.out.println("done");
    }
}
~~~

Run with **JDK 17 or later** in PowerShell or Bash from the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TypePatternDemo.java
java TypePatternDemo
~~~

**Exact expected stdout** of the `java TypePatternDemo` command alone:

~~~text
== old versus pattern ==
old=He
pattern=He
== matching types ==
string=JAVA,length=4
integerTwice=42
other=Double
null
== guards and flow scope ==
normalize1=java
normalize2=invalid
normalize3=invalid
normalize4=invalid
classifyCat=long-enough:cat
classifyHi=other
classifyNull=other
== null and interfaces ==
nullMatches=false
lengthString=3
lengthNumber=-1
numberValue=7
== generic wildcard ==
listSize=2
firstItem=A
== branch scope ==
then=ready
done
~~~

`java -version` and `javac -version` display environment-dependent version information and are not part of the fixed stdout.

## 3. Flow Scoping Through Short Examples

A pattern variable can only be used in branches where the compiler proves the type check succeeded. With `&&`, the right-hand side runs only when `input instanceof String text` is true; with `||` placed directly after a positive check, the right-hand side runs when the pattern does not match, so `text` cannot be used there.

~~~java
static String normalize(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip();
}
~~~

In a negated guard, if Java has to evaluate `text.isBlank()`, the condition `!(...)` was false, so `text` is bound. After a `return` guard, every remaining path is also guaranteed to match String. Conversely, `text` cannot be used in the `else` branch of a positive check. The lesson on pattern variable scope analyzes `if/else`, `!`, `&&`, `||`, and the ternary operator in full.

## 4. `null`, Supertypes, and Interfaces

~~~java
Object value = null;
boolean matched = value instanceof String text; // false.
~~~

An `instanceof` type pattern with `null` **returns false** and does not throw `NullPointerException` on its own. Conversely, if you later call a method on `value` without checking, a null error can still occur.

A pattern checks the **runtime object type** along class inheritance and interface relationships:

~~~java
Object value = "abc";
if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // 3.
}
~~~

`String` implements `CharSequence`, so the pattern matches. The variable `chars` has static type `CharSequence`; you can only call methods declared on that type directly, and do not automatically have all methods specific to `String`.

In an `if/else if` chain, a supertype pattern placed earlier can catch subtype objects as well. Choose the order according to business logic so a subtype branch is never made unreachable because a supertype handled it first.

## 5. Limitations and Common Compile Errors

| Situation | Valid or Invalid? |
| --- | --- |
| `Object o; o instanceof String s` | Valid when `o` has been initialized |
| `o instanceof String s && s.length() > 0` | Valid under flow scoping |
| `o instanceof String s \|\| s.length() > 0` | **Invalid**: `s` may not be bound on the right-hand side |
| `String s = "x"; s instanceof String t` | **Compile error**: static type is always a subtype of the pattern type |
| `o instanceof List<?> items` | Valid with a reifiable wildcard type |
| `o instanceof List<String> items` | Invalid for `Object o`: type erasure |
| `null instanceof String s` | Do not use literal `null` directly as the pattern expression; use a reference variable with a null value as in the example above |

**Generics:** Because of *type erasure*, Java cannot verify that an object is a `List<String>` from runtime `List` information alone. The pattern `List<?> items` is valid, but `items.get(0)` returns `Object` as its static type; if you want to treat elements as Strings, you need to check each element individually.

**Primitive types:** An `instanceof` type pattern works on **reference types**; you do not write `instanceof int x`. An `int` value assigned to `Object` is boxed into an `Integer`, and can be checked with `instanceof Integer number`.

**Overly obvious patterns:** If the left-hand expression has static type `String` and you check `instanceof String text`, Java 17 rejects it because the check is always true by subtyping; use the variable that already has type String.

## 6. Java 17 vs. Newer Pattern Types

`instanceof Type variable` is a **standard** feature in Java 17. However, `case String s -> ...` in **pattern matching for switch** is not yet standard in Java 17 (it is only available as preview when explicitly enabled); do not assume you can use type pattern `case` labels in standard Java 17 switch statements.

**Record patterns** are also not yet standardized in Java 17. Those are different features from checking a type and binding a single variable with `instanceof`.

## 7. Self-Check Exercises

1. For `Object x = "abc"; if (x instanceof String s) ...`, what is `s.length()`?  
   *Answer:* 3.
2. What does `Object x = null; x instanceof String s` produce?  
   *Answer:* false.
3. Why does `x instanceof String s && s.isBlank()` compile?  
   *Answer:* `&&` evaluates the right-hand side only when the pattern matches.
4. Why is replacing `&&` with `||` in the example above usually wrong?  
   *Answer:* The right-hand side of `||` can run when the pattern fails to match and `s` is not bound.
5. After `if (!(x instanceof String s)) return;`, can `s` be used in the next statement?  
   *Answer:* Yes, because the non-matching case has already exited the method.
6. Is `Object x = List.of("a"); x instanceof List<String> items` valid?  
   *Answer:* No; replace with `List<?>` and check elements if needed.
7. Can `instanceof Integer n` be used for a value stored in `Object`?  
   *Answer:* Yes, if the actual runtime object is an `Integer`.

## Checklist

- [ ] `instanceof Type variable` both checks the type and declares a pattern variable with the matching static type.
- [ ] A pattern variable is only usable via **flow scoping** and does not exist automatically in the failing branch.
- [ ] Know how to use `&&` and guards with `!` to guarantee a match.
- [ ] `null` does not match a type pattern.
- [ ] Understand inheritance and interface relationships when choosing a pattern type.
- [ ] Do not use concrete generics like `List<String>` in `instanceof` in a way that cannot be checked at runtime.
- [ ] Do not confuse `instanceof` type patterns with pattern-switch/record patterns from newer Java releases.

**Conclusion:** Type patterns help Java 17 code reduce manual casts, but the most important aspect is that **type-check state and variable scope follow control flow**. Use `instanceof` with `&&`, null checks, and guard clauses properly to write clear and safe code.
