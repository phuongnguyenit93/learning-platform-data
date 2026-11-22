# Patterns in `instanceof` Expressions (Java)

## 1. The essence of pattern matching with `instanceof`

`instanceof` is a **Boolean expression** in Java. Traditionally, it only asks whether an object is compatible with the specified type:

```java
Object value = "Hello";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length()); // 5
}
```

Here, the developer has to write the cast `(String) value` again even though the `if` branch has already confirmed the type. **Pattern matching for `instanceof`** combines **type checking** and **declaring a variable to hold the matched value**:

```java
Object value = "Hello";
if (value instanceof String text) {
    System.out.println(text.length()); // 5
}
```

`String text` is a **type pattern**: `String` is the type to check, and `text` is the pattern variable assigned when the match succeeds. It does not create a new `String`, but provides a reference to the original value under the checked type.

- Type patterns in `instanceof` became a standard feature in **Java 16** (JEP 394).
- **Record patterns** of the form `Point(var x, var y)`, which allow deconstructing the components of a `record`, became a standard feature in **Java 21** (JEP 440).
- Examples using both kinds of patterns in this article require **JDK 21 or later**; no `--enable-preview` flag is needed.

The content here focuses on **patterns in `instanceof` expressions**. Pattern matching in `switch` has its own rules and forms of expression.

## 2. Reading an `instanceof` expression with a pattern

Basic form:

```java
expression instanceof ReferenceType variable
```

Example:

```java
Object input = "Java";
boolean matches = input instanceof String s;
System.out.println(matches); // true
```

Conditions for a **type pattern** to match:

1. The value produced by `expression` is **not `null`**.
2. That value is runtime-compatible with `ReferenceType` in the pattern, according to the `instanceof` check.
3. When matched, the pattern variable is assigned the value and is in scope at locations where the compiler guarantees the pattern is true.

With `input = 42` or `input = null`, `input instanceof String s` is `false`; the variable `s` will not be in scope in branches that depend on the non-matching result.

**Do not confuse the following three forms:**

| Expression | Meaning |
| --- | --- |
| `input instanceof String` | Checks the runtime type; does not create a pattern variable. |
| `input instanceof String s` | Type pattern: checks and binds the entire value to `s`. |
| `input instanceof Point(var x, var y)` | Record pattern: checks `Point` and deconstructs its two components into `x`, `y`; requires Java 21+. |

A type pattern is not a new cast syntax; the compiler has already proven the type is compatible, so you do not need to cast repeatedly inside the matched branch.

## 3. Flow scoping of pattern variables

Variables declared by a pattern follow **flow scoping**: the variable name is in scope where control flow guarantees that the match succeeded. Therefore, scope cannot be inferred solely from curly braces.

### 3.1. In the true `if` branch

```java
static void printUpper(Object input) {
    if (input instanceof String s) {
        System.out.println(s.toUpperCase());
    }
    // Cannot use s here: input might not be a String.
}
```

The variable `s` can be used in the true `if` branch. The `else` branch cannot assume `s` is assigned because that is the branch where the pattern fails.

### 3.2. Combining `&&` to both match and filter

```java
static boolean hasPrefix(Object input) {
    return input instanceof String s && s.startsWith("J");
}
```

`&&` evaluates with **short-circuiting**: the right-hand side only runs when the left-hand side is `true`. Therefore, `s` is definitely assigned when `s.startsWith(...)` is called. A `null` in `input` makes the left-hand side `false` and does not invoke a method on `s`.

Conversely, the following code is **invalid**:

```java
// Compile-error example: s is not definitely assigned on the right-hand side of ||.
if (input instanceof String s || s.isEmpty()) {
    System.out.println("matched");
}
```

The right-hand side of `||` is evaluated when the left-hand side is `false`, which is precisely when `s` has no value. Do not "fix" the error by copying the variable name outside its guaranteed scope.

### 3.3. Negation and guard clauses

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

If the negated condition is true, the method terminates immediately. Consequently, **every path reaching `return text.length()`** passes through a successful match. Java allows using `text` after the `if` in this case.

If the negated branch **does not complete abruptly**, the compiler cannot guarantee that the pattern variable exists on all paths.

### 3.4. Conditional expressions and loops

```java
static int safeLength(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

In the conditional operator `?:`, the `text.length()` branch only executes when the pattern matches. With loops, you also need to pay attention to the condition:

```java
Object value = "abcd";
while (value instanceof String s && !s.isEmpty()) {
    System.out.println(s);
    value = null; // So the example exits the loop after one iteration.
}
```

Inside the loop body, `s` is valid because the condition has a matched pattern. The loop stops when `value` is assigned `null`.

## 4. Record patterns in `instanceof`: checking and deconstructing

A record has fixed components:

```java
record Sensor(int temperature, String location) {}
```

If you only need the whole object, use a type pattern:

```java
if (value instanceof Sensor sensor) {
    System.out.println(sensor.temperature());
}
```

If you need the components right away, use a record pattern:

```java
if (value instanceof Sensor(var temperature, var location)) {
    System.out.println(temperature + " @ " + location);
}
```

Here:

- `Sensor(...)` checks whether the runtime value matches the `Sensor` record and performs component deconstruction.
- `var temperature` and `var location` are nested patterns; their static types are inferred as `int` and `String`, respectively.
- The nested patterns must correspond **in count, order, and type compatibility** with the components declared by the record. `Sensor(var temperature)` is a compile-time error because it is missing a pattern for `location`.
- A record pattern uses the record's accessor methods to retrieve component values; it does not call the constructor to create a new record.
- A reference-typed component captured with `var` can receive `null`. The outer record pattern itself does not match if the record instance at that level is `null`.

When a record contains another record, patterns can be nested:

```java
record Coordinates(int x, int y) {}
record Reading(String id, Coordinates coordinates) {}

Object item = new Reading("R-1", new Coordinates(2, 3));

if (item instanceof Reading(var id, Coordinates(var x, var y))) {
    System.out.println(id + " => " + (x + y)); // R-1 => 5
}
```

If `coordinates == null`, the nested pattern `Coordinates(...)` does not match, and the entire expression returns `false`. Meanwhile, `Reading(var id, var coordinates)` can match and bind `coordinates = null`. You must distinguish **nested pattern types** from business data validation conditions.

## 5. Complete example, running, and verifying output

Create the file **`InstanceofPatternsDemo.java`**:

```java
public class InstanceofPatternsDemo {
    record Sensor(int temperature, String location) {}

    static String classify(Object value) {
        // String type pattern + short-circuit condition.
        if (value instanceof String s && !s.isBlank()) {
            return "text:" + s.toUpperCase();
        }

        // Integer type pattern + positive number condition.
        if (value instanceof Integer n && n > 0) {
            return "positive:" + n;
        }

        // Record pattern deconstructs two components; still must check for null location.
        if (value instanceof Sensor(var t, var place) && place != null) {
            return "sensor:" + place + ":" + (t >= 30 ? "hot" : "normal");
        }

        return "other";
    }

    static int lengthOrZero(Object value) {
        if (!(value instanceof String s)) {
            return 0;
        }
        return s.length();
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(12));
        System.out.println(classify(new Sensor(32, "LAB")));
        System.out.println(classify(new Sensor(20, null)));
        System.out.println(classify(null));
        System.out.println(classify(-2));
        System.out.println(lengthOrZero("pattern"));
        System.out.println(lengthOrZero(99));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 InstanceofPatternsDemo.java
java InstanceofPatternsDemo
```

**Exact output**:

```text
text:JAVA
positive:12
sensor:LAB:hot
other
other
other
7
0
```

Explanation of the eight cases:

1. `"java"` matches `String s`, `!s.isBlank()` is true, so it returns `text:JAVA`.
2. `12` is autoboxed to `Integer` when passed as `Object`; `n > 0` is true, so it returns `positive:12`.
3. `new Sensor(32, "LAB")` matches the record pattern, `location` is non-`null`, and `32 >= 30`, so it returns `sensor:LAB:hot`.
4. `new Sensor(20, null)` **still matches the record pattern part** `Sensor(var t, var place)`, but the guard `place != null` is `false`, so it returns `other`.
5. `null` does not match any `instanceof` pattern in the example, returning `other`.
6. `-2` is an `Integer` but does not satisfy `n > 0`, returning `other`.
7. `"pattern"` has 7 characters, passes the guard clause, and returns `7`.
8. `99` is not a `String`, so the negated branch returns early with `0`.

This example demonstrates **type patterns**, **record patterns**, **flow scoping**, **`&&` short-circuiting**, **negation**, and **`null`** in common expressions. The output has been verified on JDK 24 with Java 21 syntax.

## 6. Notes on types and generics

### 6.1. Types allowed in a type pattern

`instanceof` checks reference type compatibility; you cannot write a primitive type pattern like `value instanceof int n`. For boxed data, check the appropriate wrapper type:

```java
Object value = Integer.valueOf(10);
if (value instanceof Integer number) {
    System.out.println(number + 1); // 11
}
```

The compiler also checks conversion validity at **compile time**. Not every arbitrary pair of reference types can be used if the compiler knows a match is impossible.

### 6.2. Generic types and type erasure

You cannot use `instanceof List<String> texts` to check a broadly typed `Object`, because the generic type argument `String` of `List` cannot be fully checked at runtime due to **type erasure**. The safe approach is to check with a wildcard, then check the elements:

```java
Object unknown = java.util.List.of("a", "b");

if (unknown instanceof java.util.List<?> items) {
    for (Object element : items) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

This is a **snippet meant to illustrate code inside a method or JShell**, not a standalone Java class. With the sample data, the output is `A` and `B` on two lines. `List<?>` only tells you this is a list with an unknown element type; it **does not confirm** that every element is a `String`.

### 6.3. An `instanceof` check does not replace validation

`value instanceof String s` confirms the runtime type; it does not confirm that `s` is non-empty, matches an email format, is valid according to business rules, or is safe to pass into SQL. With record patterns, `var` does not automatically validate every component either. You must add guards, such as `&& !s.isBlank()`, or separate validation logic.

### 6.4. Pattern variables and already-declared names

A pattern variable is a real variable declaration and must follow shadowing/renaming rules in its applicable scope. If a local variable named `text` already exists in the same scope, declaring `String text` as well can cause an error. Use a name that reflects the new role and only reference the variable on paths where the pattern has matched.

## 7. Comparing code before and after using type patterns

**Before Java 16**, when a value declared as `Object` needed to be read as a `String`:

```java
static String labelOld(Object input) {
    if (input instanceof String) {
        String text = (String) input;
        return "name:" + text;
    }
    return "unknown";
}
```

**With a type pattern**:

```java
static String labelNew(Object input) {
    if (input instanceof String text) {
        return "name:" + text;
    }
    return "unknown";
}
```

These two illustrative methods have the same type-checking and string-building semantics. The new version eliminates the redundant cast and avoids defining a separate intermediate variable. These are **methods that must be placed inside a Java class**, not a standalone program.

When you want to extract multiple components of a record, Java 21 also lets you omit accessor calls:

```java
// Using a type pattern:
if (value instanceof Sensor sensor) {
    System.out.println(sensor.temperature() + " @ " + sensor.location());
}

// Using a record pattern:
if (value instanceof Sensor(var t, var location)) {
    System.out.println(t + " @ " + location);
}
```

Both approaches are useful: a type pattern fits when you want to keep the whole object, whereas a record pattern fits when you need the components immediately. If you later need to construct a new DTO or normalize data, that mapping step must still be performed separately.

## 8. Common mistakes

| Mistake | Why it is wrong / how to fix it |
| --- | --- |
| Using `value instanceof String s` and accessing `s` everywhere | The variable `s` is only in scope where control flow guarantees the pattern matched. Use it in the true branch or after an early-returning guard clause. |
| Using `|| s.someMethod()` after a type pattern on the left-hand side | The right-hand side of `||` can run when the pattern did not match. Usually use `&&` if the next condition needs the pattern variable. |
| Believing `instanceof` throws `NullPointerException` on `null` | Checking a `null` value with `instanceof` returns `false`. |
| Thinking `var` in a record pattern rejects all `null` values | `var` can bind a `null` reference component; add a guard when needed. |
| Using `instanceof` with primitive `int` | `instanceof` type patterns in these examples use reference types; for boxed data, use `Integer`. |
| Trying to check `List<String>` via `instanceof` on an `Object` | Due to type erasure, use `List<?>` and then verify elements individually. |
| Using `Point(var x, var y)` on Java 17 | Record patterns were standardized in Java 21; choose a JDK 21+ toolchain and corresponding build target. |
| Using `R(...)` to deconstruct a regular class | Record patterns require a record type; use a type pattern + accessors for regular classes. |
| Confusing pattern matching with data mapping | Patterns check and bind values; they do not automatically convert or create a target DTO. |

## 9. Practice exercises and reference answers

Given:

```java
record Result(int code, String message) {}
Object response = new Result(200, "OK");
```

**Exercise 1.** Write an `instanceof` expression using a record pattern to print the message if `code == 200` and `message` is not `null`.

Answer (placed inside a method body):

```java
if (response instanceof Result(var code, var message)
        && code == 200
        && message != null) {
    System.out.println(message); // OK
}
```

**Exercise 2.** When `response = new Result(500, null)`, does the pattern on the left-hand side of `&&` match? Does the `if` branch execute?

Answer: `Result(var code, var message)` itself **still matches** because the object is a valid `Result` record and `var message` can accept `null`. However, `code == 200` is false, so `&&` short-circuits; the `if` branch does not execute. Do not equate "the record pattern matched" with "the entire Boolean expression evaluated to `true`".

**Exercise 3.** Write a method that takes an `Object`, returns `0` if the input is not a `String`, and otherwise returns the string's length, using a guard clause and the pattern variable after the guard.

Answer:

```java
static int textLength(Object input) {
    if (!(input instanceof String s)) {
        return 0;
    }
    return s.length();
}
```

**Official documentation:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java 21 Language Guide — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Java 21 Language Guide — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
