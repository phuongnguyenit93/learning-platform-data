# Why Ignoring the Return Value Easily Loses Results When Working with `String`

## 1. The Problem: The Method Call Succeeds, Yet the String Stays the Same

Observe the following code snippet (placed inside a Java method):

```java
String text = "  java  ";
text.trim();
System.out.println("[" + text + "]");
```

**Output:**

```text
[  java  ]
```

Many beginners expect `[java]` because they called `trim()`. In reality, the call `text.trim()` **did compute the whitespace-stripped result**, but the program did not store, pass, or use that return value. The variable `text` therefore still references the original string `"  java  "`.

This is a direct consequence of **`String` immutability**: once a `String` object has been created, the content of that object itself is not modified in place by methods such as `trim()`, `replace()`, or `toUpperCase()`.

Key takeaway: **Calling a method that returns `String` does not automatically update the variable holding the string. To get the transformed result, you must use the return value.**

## 2. The Result Value Can Be Dropped on Either Side of a Call

The bug does not occur only in `text.strip();`. A processing method may return the right value, yet **the caller** drops the result:

```java
public class ReturnValueBoundaryDemo {
    static String clean(String value) {
        return value.strip();       // Method returns the processed result
    }

    public static void main(String[] args) {
        String raw = "  Java  ";
        clean(raw);                 // Result discarded: raw does not change
        String display = clean(raw);
        System.out.println("raw=[" + raw + "]");
        System.out.println("display=[" + display + "]");
    }
}
```

The code runs on JDK 17+ and prints `raw=[  Java  ]` then `display=[Java]`.

If you need to update the variable, use `raw = clean(raw);`; if you need to keep the original, use another variable. Using it directly is also a valid way to consume the result, for example `System.out.println(clean(raw));`. Not **every** return value must be assigned; the question is whether the result reaches the intended consumer.

During code review, trace the path **input → return value → consumer**. A method may compute correctly but have its result dropped at the caller; a caller may assign properly while the helper method inside returns the old input. Those are two independent bug locations to check.

## 3. Complete Java 17+ Example

Save the entire contents below to **`StringReturnValueDemo.java`**:

```java
import java.util.Locale;

public class StringReturnValueDemo {
    public static void main(String[] args) {
        String original = "  java core  ";

        // These results are all ignored.
        original.trim();
        original.toUpperCase(Locale.ROOT);
        original.replace("core", "string");

        System.out.println("After ignoring: [" + original + "]");

        // Capture the return value of each transformation.
        String normalized = original.trim()
                .toUpperCase(Locale.ROOT)
                .replace("CORE", "STRING");

        System.out.println("Used result: [" + normalized + "]");
        System.out.println("Original string: [" + original + "]");

        String word = "Java";
        word.concat(" 21");
        System.out.println("ignored concat: " + word);

        word = word.concat(" 21");
        System.out.println("reassigned concat: " + word);
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 StringReturnValueDemo.java
java StringReturnValueDemo
```

**Exact stdout:**

```text
After ignoring: [  java core  ]
Used result: [JAVA STRING]
Original string: [  java core  ]
ignored concat: Java
reassigned concat: Java 21
```

Step-by-step explanation:

1. The first three calls `trim()`, `toUpperCase(Locale.ROOT)`, and `replace(...)` all compute results without changing the variable `original`, so printing it still shows two spaces on each end and lowercase `java core`.
2. The method chain `original.trim().toUpperCase(Locale.ROOT).replace("CORE", "STRING")` **passes the return value** of each step to the next step. The final result is `"JAVA STRING"`, stored in `normalized`.
3. `original` remains `"  java core  "` because creating and storing another transformed result does not modify the original object.
4. `word.concat(" 21")` is ignored, so `word` stays `"Java"`. After `word = word.concat(" 21")`, the variable `word` references the value `"Java 21"`.

Using `Locale.ROOT` in the example makes uppercasing rules independent of the machine's default language. This is helpful for technical data, identifiers, or outputs needing consistency; when processing text for a specific language, an appropriate `Locale` may be needed.

## 4. Chaining: Why Can a Method Chain Still Lose Its Result?

This is **method chaining**: each method receives the `String` object returned by the previous step.

```java
String input = "  Hello Java  ";
String result = input.strip().replace(" ", "-").toLowerCase(java.util.Locale.ROOT);
System.out.println(result); // hello-java
```

If you only write:

```java
input.strip().replace(" ", "-").toLowerCase(java.util.Locale.ROOT);
```

then the final result is still **discarded**: chaining does not automatically write the result back into `input`. Intermediate results were used as receivers for the next steps, but the final step needs a value consumer, such as an assignment, `return`, an argument passed to another method, or a comparison.

To return the result from a processing method:

```java
static String normalize(String source) {
    return source.strip().toLowerCase(java.util.Locale.ROOT);
}
```

And **the caller** must also use the return value:

```java
String normalized = normalize("  JAVA  "); // "java"
```

Merely calling `normalize("  JAVA  ");` as a standalone statement will likewise discard the processed string.

## 5. Real-World Bug Scenarios and Fixes

### Scenario 1: normalizing input before checking

**Wrong:**

```java
String role = "  ADMIN  ";
role.strip();
if (role.equals("ADMIN")) {
    System.out.println("Admin role");
}
```

The condition is false because `role` is still `"  ADMIN  "`.

**Right:**

```java
String role = "  ADMIN  ";
role = role.strip();
if (role.equals("ADMIN")) {
    System.out.println("Admin role");
}
```

Note: this is only a string-checking illustration; real authorization mechanisms require properly designed authentication and access control rather than relying solely on an input string.

### Scenario 2: replacing characters but using the old value

**Wrong:**

```java
String slug = "hello java";
slug.replace(" ", "-");
System.out.println(slug); // hello java
```

**Right:**

```java
String slug = "hello java";
slug = slug.replace(" ", "-");
System.out.println(slug); // hello-java
```

### Scenario 3: helper method computes it, then the caller ignores it

```java
static String clean(String value) {
    return value.strip();
}
```

**Wrong at the call site:**

```java
String value = "  hello  ";
clean(value); // The returned value is ignored
```

**Right:**

```java
String value = "  hello  ";
value = clean(value);
```

The bug can happen in either place: forgetting to `return` the appropriate result inside the method, or the method returning properly while the caller fails to use it.

## 6. How to Spot the Bug Yourself When Reading Code

When encountering a `String` that appears to have been processed yet the output has not changed, follow this sequence:

1. **Locate the method call**: `trim`, `strip`, `replace`, `substring`, `toUpperCase`, `concat`, or a helper function returning `String`.
2. **Trace where the return value goes**: is it assigned to a variable, returned with `return`, passed to another method, or used in an expression?
3. **Check which variable the program is reading**: is it printing or checking the original variable while the actual result was stored in a different variable?
4. **Check whether the API modifies in place**: `String` is immutable, whereas types like `StringBuilder`, `StringBuffer`, and many collections have mutable behavior.
5. **Add a small test**: assert both before- and after-processing values to catch logic bugs early.

Example check without external libraries, placed in `main`:

```java
String source = "  Java  ";
String result = source.strip();

if (!"Java".equals(result)) {
    throw new AssertionError("Processed value is incorrect");
}
if (!"  Java  ".equals(source)) {
    throw new AssertionError("Original string was modified");
}
```

These assertions check both important sides: **the returned result is right** and **the original value remains intact**.

## 7. Self-Check Questions

**Question 1.** What does the following code print and why?

```java
String s = "abc";
s.replace("a", "x");
System.out.println(s);
```

**Answer:** `abc`; `replace` returns a result, but the call's return value is ignored.

**Question 2.** Fix one line to print `XBC`:

```java
String s = "abc";
s.toUpperCase(java.util.Locale.ROOT);
System.out.println(s.replace("A", "X"));
```

**Answer:** Change the second line to `s = s.toUpperCase(java.util.Locale.ROOT);`. Then `s` is `"ABC"`; `replace` on the last line returns `"XBC"` and `println` uses that result directly.

**Question 3.** Does calling `s.strip()` and discarding the return value always create a new object?

**Answer:** No. Some operations may return the same object when no change is needed. Regardless of which object the returned result points to, the call **does not change the content of the original `String` object**.

**Question 4.** Why can `builder.append("x");` change the output when printing `builder`, whereas `s.concat("x");` does not change the output when printing `s`?

**Answer:** `StringBuilder` is designed to mutate the content of the object itself; `String` is designed to be immutable and `concat` returns a string value rather than modifying the receiver object.

**Remember:** When you want to transform `String` content, identify clearly **who will receive the return value**. You can reassign it, store it in a new variable, `return` it, pass it as an argument, or use it immediately in an expression. A correctly computed value that goes unused will not produce the desired effect in the original variable.
