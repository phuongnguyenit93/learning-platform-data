# The Repeated Type-Check-and-Cast Problem: Pattern Matching for `instanceof` in Java 17

In Java code that handles objects with a general type such as `Object`, an interface, or a superclass, developers often have to perform two consecutive operations: **checking the specific type of the object** with `instanceof`, and then **casting** it to call methods of that type. Before *pattern matching for `instanceof`*, this style easily produced repetitive lines and could introduce bugs when checking one type but casting to another.

Since Java 16, **type patterns for `instanceof` have been a standard feature** (JEP 394), so **Java 17 uses them directly without enabling preview**. Instead of checking first and manually declaring a cast variable afterward, you write the check and variable declaration in the same expression:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

In that statement:

- `value` is the expression to check.
- `String` is the type to check against.
- `text` is the **pattern variable**, which can only be used in places where the compiler knows the pattern has matched.
- When `value` is indeed a `String`, the variable `text` references that object with the static type `String`. There is no need to write `(String) value` again.

This lesson moves from the problem of *repeated type checks and casts* to Java 17 syntax, how to understand variable scope via control flow, type limitations, and how to apply it in real-world code.

## 1. The Problem: `instanceof` Followed by a Manual Cast

Suppose an API returns `Object`, because the result could be a string, a number, or another kind of data. To handle each case separately, we previously used to write:

```java
public class BeforePattern {
    static String describe(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "String of length " + text.length() + " characters";
        }

        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Doubled number: " + (number * 2);
        }

        return "Other data type";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java 17"));
        System.out.println(describe(12));
    }
}
```

When reading each branch, we see three operations always going together:

1. Check the type with `value instanceof String`.
2. Repeat the type name in `(String) value`.
3. Assign the cast result to the local variable `text`.

This is where issues easily arise:

| Problem with the old pattern | Consequence |
| --- | --- |
| Writing the type name twice. | Code is longer and must be updated in sync if the type changes. |
| Repeating the source expression. | Easy to accidentally cast a different expression than the one just checked. |
| Manual cast does not match the condition. | Can encounter `ClassCastException` at runtime. |
| Many similar branches. | Type checks and boilerplate obscure the business logic. |

For example, this is a programming bug rather than a flaw in `instanceof`:

```java
if (value instanceof String) {
    // Wrong: checked for String but cast to Integer.
    Integer number = (Integer) value;
}
```

The compiler may allow casting from `Object` to `Integer` syntactically, but when `value` is actually a `String` at runtime, the program will throw `ClassCastException`. Pattern matching reduces the chance of making this mistake by binding **the checked type and the type of the variable used** into the same construct.

## 2. The New Way: Checking and Assigning the Variable in One Step

Rewrite the exact same program in Java 17:

```java
public class AfterPattern {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "String of length " + text.length() + " characters";
        }

        if (value instanceof Integer number) {
            return "Doubled number: " + (number * 2);
        }

        return "Other data type";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java 17"));
        System.out.println(describe(12));
    }
}
```

Output:

```text
String of length 7 characters
Doubled number: 24
```

The difference is that the variables `text` and `number` already have their **specific types**. The compiler checks the `instanceof` expression; if the pattern matches, it provides the properly typed variable in the scope where it can be safely used.

Direct comparison:

| Traditional approach | Pattern matching in Java 17 |
| --- | --- |
| `if (obj instanceof String) { String s = (String) obj; ... }` | `if (obj instanceof String s) { ... }` |
| Check the type and then cast manually. | Check and declare the typed variable at the same time. |
| Must repeat `String` and `obj`. | No need to repeat the cast. |
| Variable `s` is manually declared by the developer inside the block. | The pattern variable is allowed by the compiler at positions where it has matched. |

**What does not change:** `instanceof` still checks the object's type at runtime; pattern matching **does not eliminate polymorphism, does not convert values into another type, and does not automatically fix data design**. It makes writing type checks + casts clearer and safer.

## 3. How Does `instanceof Type variable` Work?

With the expression:

```java
Object payload = "hello";

if (payload instanceof String message) {
    System.out.println(message.toUpperCase());
}
```

We can read it as: "If `payload` is a `String` object, name that object `message`, and then run the `if` branch."

### 3.1. This is a type check, not data conversion

If `payload` holds an `Integer`, the check `payload instanceof String message` returns `false`; Java does not try to convert the number into a string:

```java
Object payload = 42;

if (payload instanceof String message) {
    // Does not run.
    System.out.println(message);
} else {
    System.out.println("Not a String");
}
```

To **convert data** such as a number to a string, use the appropriate API, such as `String.valueOf(payload)`. To **check a subtype**, use `instanceof`.

### 3.2. A pattern variable is not a new object

`message` references **the exact same object** that `payload` holds. No `String` constructor is called, and it is not a copy of the data. The main benefit is that **the static type is narrowed within the control flow**: inside the valid branch, you can call `String.length()` without casting.

### 3.3. `null` does not match a type pattern

```java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Does not match String");
}
```

This code prints "Does not match String". Just like regular `instanceof`, the expression `null instanceof String` evaluates to `false`. The pattern-matched branch does not receive a `null` object, so there is no need to add `text != null` just to guard against that case.

However, **the expression evaluated to obtain the object can still throw an exception**: `service.read() instanceof String s` does not guarantee that `service.read()` itself will not fail. The `instanceof` check only handles the result if the expression executes successfully.

## 4. Scope of a Pattern Variable: The Variable Only Exists When Definitely Matched

The most important difference to learn compared to regular variable declarations is **flow scoping**: the compiler tracks control flow to know when a pattern has definitely matched. The detailed rules are defined in the Java Language Specification.

### 4.1. Inside the matching `if` branch

```java
static void printIfText(Object value) {
    if (value instanceof String text) {
        System.out.println(text.trim()); // Valid
    }

    // System.out.println(text); // Invalid
}
```

After the entire `if`, `text` cannot be used, because the program may have taken the non-matching branch. A pattern variable **does not implicitly exist throughout the entire method**.

### 4.2. Using `else` with negation

```java
static void printIfText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a string");
    } else {
        System.out.println(text.trim()); // Valid
    }
}
```

The `else` branch here means that the condition `!(value instanceof String text)` is `false`, meaning the pattern matched, so `text` can be used.

### 4.3. Guard clause: Check for errors first, then handle the rest

In a method with a return type, if the non-matching branch **exits the method**, the compiler knows all remaining paths have matched:

```java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // Only reaches here when value has matched String.
    return text.length();
}
```

You can use `return` to exit early following the same principle:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "";
    }
    return text.strip();
}
```

This is a convenient pattern when the input data must belong to a specific type. It avoids deep `if` nesting and avoids manual casts.

### 4.4. Cannot use a pattern variable if the match cannot be proven

```java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }

    // Wrong: value might not be a String.
    // System.out.println(text.toUpperCase());
}
```

The rule is not merely about curly braces; it depends on **the paths that can reach the point of use**. Looking at the condition and the `return`, `throw`, and `else` branches is usually enough to explain why the compiler accepts or rejects it.

## 5. Combining Conditions with `&&` and `||`

Pattern matching is especially concise when, after checking the type, you need to **check additional conditions on the narrowed data**.

### 5.1. `&&`: Check the type, then use the variable

```java
static boolean isValidUserName(Object input) {
    return input instanceof String name
            && !name.isBlank()
            && name.length() <= 30;
}
```

Java evaluates `&&` from left to right and **stops when an operand is `false`**. Therefore, if execution reaches `!name.isBlank()`, the pattern `input instanceof String name` has already matched. `name` can be used in the subsequent operands.

The old pattern usually required multiple lines:

```java
static boolean isValidUserNameOld(Object input) {
    if (!(input instanceof String)) {
        return false;
    }
    String name = (String) input;
    return !name.isBlank() && name.length() <= 30;
}
```

Both approaches express the validation rule, but the Java 17 version needs no separate cast line.

### 5.2. `||`: Cannot use the variable on the right-hand side in the same way

```java
static boolean invalidCondition(Object input) {
    // Wrong: if input is not a String, the right-hand side can still be evaluated.
    // return input instanceof String name || name.isBlank();
    return false;
}
```

Reason: when the right-hand side of `||` is evaluated, the left-hand side must be `false`; that is precisely the case where the pattern **did not match**, so `name` is unavailable.

It is usually rewritten using `&&`:

```java
static boolean isNonBlankText(Object input) {
    return input instanceof String text && !text.isBlank();
}
```

Or using negation with an early-exit condition:

```java
static String requireNonBlankText(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Expected non-blank text");
    }
    return text;
}
```

In the latter expression, `text.isBlank()` is evaluated **only when** `!(input instanceof String text)` is `false`, meaning the initial pattern matched. The difference between the two examples shows that you need to understand both **negation** and **short-circuit evaluation**.

### 5.3. Quick-reference rules

| Expression | Can the pattern variable be used afterward? | Why |
| --- | --- | --- |
| `obj instanceof String s && s.length() > 3` | Yes | The right-hand side of `&&` only runs when the pattern matches. |
| `obj instanceof String s || s.isEmpty()` | No | The right-hand side of `||` runs when the pattern does not match. |
| `!(obj instanceof String s) || s.isEmpty()` | Yes | The right-hand side of `||` only runs when the negation is `false`, i.e., the pattern matched. |
| `if (!(obj instanceof String s)) return;` then use `s` | Yes | All continuing paths have already matched. |
| `if (obj instanceof String s) { ... }` then use `s` outside the block | No | The `if` condition might have been `false`. |

## 6. Applying Pattern Matching When Handling Polymorphic Data

The check-then-cast problem commonly arises when:

- Reading data from a library with a general API that returns `Object`.
- Handling an interface with multiple implementation classes, each holding its own data.
- Working with message queues, events, or results represented by multiple subtypes.
- Maintaining legacy code with many repeated `instanceof` branches and casts.

The following example describes a notification formatter. We have two variants with different data:

```java
interface Notice {}

record EmailNotice(String address, String subject)
        implements Notice {}

record SmsNotice(String phoneNumber, String body)
        implements Notice {}

public class NoticeDemo {
    static String format(Notice notice) {
        if (notice instanceof EmailNotice email) {
            return "Email to " + email.address()
                    + ": " + email.subject();
        }

        if (notice instanceof SmsNotice sms) {
            return "SMS to " + sms.phoneNumber()
                    + ": " + sms.body();
        }

        throw new IllegalArgumentException("Unsupported notice: " + notice);
    }

    public static void main(String[] args) {
        Notice first = new EmailNotice("team@example.org", "Java 17");
        Notice second = new SmsNotice("+84123456789", "Sent");

        System.out.println(format(first));
        System.out.println(format(second));
    }
}
```

Save to **`NoticeDemo.java`** and run:

```bash
javac --release 17 NoticeDemo.java
java NoticeDemo
```

The example produces:

```text
Email to team@example.org: Java 17
SMS to +84123456789: Sent
```

Without pattern matching, each branch would require an extra line:

```java
if (notice instanceof EmailNotice) {
    EmailNotice email = (EmailNotice) notice;
    // ...
}
```

With patterns, the type is checked and the variable is declared in the same place. When adding handling for `PushNotice`, the developer only needs to write one new type branch without creating repeated check/cast pairs.

**Design limitation:** the example above uses a regular interface; the program cannot infer that the code has handled every possible implementation. If subtypes are added frequently and each subtype needs its own behavior, placing polymorphic behavior directly on the interface or implementation classes may make more sense than a long `instanceof` chain. Pattern matching solves the **syntax** of subtype checking well, but it does not replace all object-oriented design approaches.

## 7. Leveraging Safe Type Check + Cast at the Beginning of a Method

When a method accepts a general parameter and only handles one type, there are two common styles:

### 7.1. Manual cast after the condition

```java
static int wordCountOld(Object input) {
    if (!(input instanceof String)) {
        return 0;
    }

    String text = (String) input;
    if (text.isBlank()) {
        return 0;
    }
    return text.strip().split("\\s+").length;
}
```

### 7.2. Pattern variable with a guard clause

```java
static int wordCount(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }

    if (text.isBlank()) {
        return 0;
    }
    return text.strip().split("\\s+").length;
}
```

In this example, the word-counting logic is unchanged; only the manual cast is removed. `String.isBlank()` and `strip()` are available in Java 17. The `split("\\s+")` part is a regular expression for whitespace sequences; it is not part of pattern matching.

A shorter option:

```java
static int lengthIfText(Object input) {
    return input instanceof String text ? text.length() : 0;
}
```

The true branch of the conditional operator `?:` is only evaluated when the pattern has matched. However, if the expression is complex or has multiple branches, an `if` block is usually easier to read.

## 8. Type Limitations You Need to Know

### 8.1. The checked type must be compatible with the static type of the expression

Java only accepts checks that make sense under the language's type and conversion rules. One specific rule for **type patterns**:

```java
Object value = "Hello";
if (value instanceof String text) { // Valid
    System.out.println(text.length());
}
```

Meanwhile:

```java
String value = "Hello";

// Invalid in Java 17:
// if (value instanceof String text) { ... }
```

In the second example, **the static type of `value` is already `String`**, which is a subtype of the pattern type `String`. This is a redundant pattern check and the compiler rejects it. If you already have a `String` variable, use that variable directly:

```java
String value = "Hello";
System.out.println(value.length());
```

Do not add pattern matching just to use a new feature. This tool is useful when **the static type is broader than the type you need**.

### 8.2. `instanceof` does not fully check generic type arguments

Because Java performs type erasure, you cannot write a type pattern with non-*reifiable* type arguments such as `List<String>`:

```java
import java.util.List;

class GenericsExample {
    static void inspect(Object value) {
        // Wrong: cannot check List<String> this way.
        // if (value instanceof List<String> strings) { ... }

        if (value instanceof List<?> elements) {
            for (Object element : elements) {
                if (element instanceof String text) {
                    System.out.println(text.toUpperCase());
                }
            }
        }
    }
}
```

`List<?>` is a type that can be checked this way; the elements still need to be checked individually if they must be guaranteed to be `String`. Do not treat `instanceof List<?>` as proof that all elements share a specific type.

### 8.3. No primitive pattern matching in Java 17

```java
Object value = 10; // auto-boxed to Integer

if (value instanceof Integer number) {
    int doubled = number * 2; // unboxing in arithmetic
    System.out.println(doubled);
}
```

The `value` object holds an `Integer`, not a primitive `int` object. In Java 17, type patterns for `instanceof` use an appropriate **reference type**, such as `Integer`, `String`, or an interface. Do not write `value instanceof int number`.

### 8.4. A type pattern is not a record pattern

With a record:

```java
record Point(int x, int y) {}

static int distanceSquared(Object value) {
    if (value instanceof Point point) {
        return point.x() * point.x() + point.y() * point.y();
    }
    return 0;
}
```

Java 17 allows `instanceof Point point` but **does not support record pattern syntax to directly deconstruct into `x` and `y`** in the form `value instanceof Point(int x, int y)`. Only use syntax that actually exists in the Java 17 specification; do not copy examples from newer JDK versions.

### 8.5. Do not confuse with pattern matching in `switch`

Java 17 supports **switch expressions** on standard types and enums, but **pattern matching for `switch` is a preview feature in Java 17** (JEP 406):

```java
// Not default stable Java 17 syntax:
// return switch (value) {
//     case String s -> s.length();
//     case Integer i -> i;
//     default -> 0;
// };
```

To write stable Java 17 code without preview features, choose `if (value instanceof String s)` or appropriate polymorphism techniques. Pattern matching for `instanceof` does not require `--enable-preview`.

## 9. Evaluate Complex Expressions Only Once

Besides repeating casts, old code also carried the risk of **re-invoking data-producing expressions**:

```java
// Avoid this style:
// if (service.fetch() instanceof String) {
//     String text = (String) service.fetch();
// }
```

Calling `fetch()` twice can waste resources, cause side effects, or return different values. The clear way:

```java
Object result = service.fetch();
if (result instanceof String text) {
    System.out.println(text);
}
```

You can write `if (service.fetch() instanceof String text)` to evaluate `fetch()` once directly in the condition, but extracting it into a `result` variable is more convenient if you need to log, check for exceptions, or reuse the result.

**Note:** pattern matching helps avoid repeated casts; it does not automatically make an API with side effects safe or prevent an expression from being called multiple times across a method. Developers still have to decide when to evaluate expressions.

## 10. Check Subtypes in Order from Specific to General

An object can simultaneously match multiple types—for example, `String` is both a `String` and implements `CharSequence`. If a broader type is checked first, a later branch might never be selected for that object:

```java
static String describe(Object input) {
    if (input instanceof String text) {
        return "String: " + text;
    }
    if (input instanceof CharSequence sequence) {
        return "CharSequence of length " + sequence.length();
    }
    return "Other";
}
```

This is the appropriate order when `String` needs special handling. If `CharSequence` is placed first, every `String` will be caught by the general branch.

Do not assume a single universal order for every problem. If the checked types have no subtype relationship or serve different business goals, choose an order that reflects the meaning of each branch. `instanceof` checks **runtime type compatibility**, not an exact class equality comparison like `getClass() == String.class`.

## 11. When to Use Pattern Matching, and When to Redesign the API?

Pattern matching for `instanceof` is particularly suitable when **you cannot or should not change** the input type structure, such as:

- An external API returns a supertype and your code only needs to handle a few specific subtypes.
- Upgrading legacy code that contains many `instanceof` + cast pairs.
- Needing to check before accessing fields or methods that only exist on one subtype.
- Writing a quick guard condition: `obj instanceof Type typed && typed.isValid()`.

However, if a system has dozens of subtype branches across multiple services, a long chain of `if (x instanceof A a) ... else if (x instanceof B b) ...` may signal **missing polymorphic behavior**.

For example, if all implementations of `Notice` should know how to display themselves, we can define:

```java
interface Notice {
    String format();
}

record Email(String to, String subject) implements Notice {
    public String format() {
        return "Email to " + to + ": " + subject;
    }
}

record Sms(String phone, String body) implements Notice {
    public String format() {
        return "SMS to " + phone + ": " + body;
    }
}

class NoticeRenderer {
    static String render(Notice notice) {
        return notice.format();
    }
}
```

When you can change the design of the entire type family, polymorphism lets you completely eliminate type checks and casts for shared behavior. Conversely, if you are handling data from an API you do not control or only need a special operation for a few types, type patterns are concise and fit for purpose.

Do not replace `instanceof` with reflection (`getClass()` or `Class.cast()`) just to avoid a normal cast. Reflection serves other runtime needs; it offers no clear benefit in simple type-check-and-cast cases that Java 17 already supports directly.

## 12. Misconceptions to Avoid

| Misconception | Correct understanding and handling in Java 17 |
| --- | --- |
| A pattern variable always has method-wide scope. | Scope is based on **flow scoping**: only usable where the compiler proves the pattern matched. |
| After checking `obj instanceof String s`, you still have to cast `(String) obj`. | Use `s` directly; that is the whole point of pattern matching. |
| `obj instanceof String s || s.isEmpty()` is valid. | No; the right-hand side of `||` is evaluated when the pattern did not match. |
| `null` will match a type pattern because the variable has a reference type. | No; `null instanceof String s` evaluates to `false`. |
| Pattern matching turns a number into a string or a string into a number. | No; it checks the runtime type and binds a name to the matched object. |
| You can use `List<String>` to verify that all elements are `String`. | No; such generic type arguments cannot be checked due to type erasure. Use `List<?>` and check elements individually. |
| Java 17 already has all the latest pattern forms. | Java 17 has type patterns for `instanceof`; record patterns and type-pattern `switch` from later versions are not default stable features in Java 17. |
| A `String s` can use `s instanceof String text` to redeclare a variable of the same type. | Avoid redundant patterns: the Java 17 compiler rejects a type pattern when the expression's type is already a subtype of the pattern type. |
| Using pattern matching always makes the application faster. | The main benefits are clarity and reducing repeated casts. Performance must be measured in context, not inferred from syntax alone. |

## 13. Practice Exercises

### Exercise 1 — Remove repeated casts

Convert this code snippet to Java 17 pattern matching while preserving its exact behavior:

```java
static String classify(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "text(" + text.length() + ")";
    }

    if (value instanceof Long) {
        Long number = (Long) value;
        return "long(" + (number + 1) + ")";
    }

    return "other";
}
```

Requirement: do not use casts in the branches after checking the type; handle `null` identically to the original code.

### Exercise 2 — Explain variable scope

Determine which lines are valid and explain based on control flow:

```java
static void check(Object input) {
    if (input instanceof String s && s.length() > 5) {
        System.out.println(s);
    }

    // System.out.println(s);

    if (!(input instanceof Integer n)) {
        return;
    }
    System.out.println(n + 10);
}
```

Hint: the `return` statement causes all paths that do not match `Integer` to terminate before reaching the addition.

### Exercise 3 — Write a guard clause

Write a method `static String normalizeId(Object input)`. If `input` is a `String` that is non-empty after `strip()`, return the trimmed string; otherwise throw `IllegalArgumentException`. Use pattern matching in the condition without any cast.

### Exercise 4 — Handle a list with unknown element types

Write a method taking an `Object`. If the object is a `List<?>`, iterate over each element and print only the elements that are `String` in uppercase. If it is not a list, print nothing. Do not use `instanceof List<String>` and do not cast to `List<String>`.

### Exercise 5 — Decide whether `instanceof` is needed

An application has a `Shape` interface where every shape must compute its area. Compare:

- Writing a single method with `instanceof Circle` and `instanceof Rectangle` branches;
- Declaring `double area()` in `Shape` and letting each implementation provide it.

Choose the appropriate approach if you have permission to modify all shape types and expect to add new shape types frequently. Then describe a situation where an `instanceof` pattern is still useful.

## 14. Official Documentation

- **JEP 394 — Pattern Matching for `instanceof`:** <https://openjdk.org/jeps/394>. Explains the motivation for eliminating check-then-cast sequences, flow scoping, and standard status since Java 16.
- **Java Language Specification, Java SE 17, §15.20.2 — The `instanceof` Operator:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2>. Specification of type checking and the meaning of `instanceof`.
- **Java Language Specification, Java SE 17, §14.30 — Patterns:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30>. Pattern concepts in the language.
- **Java Language Specification, Java SE 17, §6.3.1 — Scope of a Pattern Variable Declaration:** <https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1>. Explains variable scope based on control flow.
- **JEP 406 — Pattern Matching for `switch` (Preview):** <https://openjdk.org/jeps/406>. Reference to distinguish the preview feature in Java 17 from the already-standard `instanceof` pattern.
- **Java SE 17 API Documentation:** <https://docs.oracle.com/en/java/javase/17/docs/api/index.html>. Look up `String.isBlank()`, `String.strip()`, `List`, and other APIs used in the examples.

Whenever you encounter code like **“`if (x instanceof T)` followed by `T value = (T) x`”**, consider converting it to **“`if (x instanceof T value)`”** to eliminate repetition. The deeper concept to understand is **the variable's scope based on the condition's outcome**: Java 17 only allows using the pattern variable on paths where the compiler determines the type has matched.
