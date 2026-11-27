# Type Patterns and Pattern Variables in `instanceof` — Java 17

## 1. Lesson Purpose

In Java, a variable declared with a broad type such as `Object` or an interface may refer to an object of a more specific type at runtime. Before using methods specific to that concrete type, the program must determine whether the object is of the expected type.

Java 17 supports **pattern matching for `instanceof`** as a stable feature. This syntax lets you **check the type and declare a properly typed variable in the same expression**:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

In this example:

- `value` is the expression to check, which may have a declared type of `Object`.
- `String` is the **target type** of the type pattern.
- `text` is the **pattern variable**, bound to the object when the check succeeds.
- `text.length()` is valid in branches where the compiler knows `text` has been bound.

These are two distinct concepts: a **type pattern** describes "a value of type `String`, named `text`", while a **pattern variable** is the name that can be used at locations where the check result is guaranteed to have succeeded.

This feature was finalized in **Java 16 (JEP 394)** and is used directly in **Java 17** without `--enable-preview`. This lesson only uses syntax that is stable in Java 17.

## 2. What Does `instanceof` Check?

An `instanceof` expression checks a type relationship at runtime. For a non-`null` reference, the check succeeds if the object is compatible with the target type according to Java's rules.

```java
Object value = "Java 17";

System.out.println(value instanceof String); // true
System.out.println(value instanceof Number); // false
```

The declared type of `value` is `Object`, but the actual object referenced is a `String`. `instanceof` relies on **the type of the actual object**, not solely the declared type of the variable.

When the object does not match, the result is `false`. When the value is `null`, both a regular type check and a type pattern also return `false`:

```java
Object nothing = null;

System.out.println(nothing instanceof String); // false
System.out.println(nothing instanceof String s); // false
```

Therefore, inside the branch `if (value instanceof String text)`, `text` is already established as a reference to a non-`null` `String`.

### Checking the type and obtaining a variable at the same time

Checking the type only:

```java
Object input = "abc";

if (input instanceof String) {
    // Check succeeded, but no separate String variable was declared yet.
}
```

Using a type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

`text` has a static type of `String`, so the compiler accepts `toUpperCase()`. The original variable `input` still has a declared type of `Object`; declaring a pattern **does not change the type of the original variable**.

## 3. Syntax of a Type Pattern

Basic structure in Java 17:

```java
expression instanceof ReferenceType variableName
```

Example:

```java
Object item = Integer.valueOf(42);

if (item instanceof Integer number) {
    System.out.println(number.intValue() + 1);
}
```

The variable `number` is declared directly inside the type pattern. In the true branch, it references the exact same object that `item` references; this does not create a new `Integer` object.

Some valid type patterns:

```java
Object data = "hello";

if (data instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

```java
Object data = java.util.List.of("A", "B");

if (data instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

`ReferenceType` is an appropriate reference type. You cannot use a primitive type directly such as `instanceof int value`. For numeric values that might be held in an `Object`, you typically check the corresponding wrapper (`Integer`, `Long`, etc.) or a parent interface/class like `Number`.

Pattern variable names must follow naming rules and avoid conflicts with variables already in the corresponding scope. Choose names that reflect the object after checking, such as `text`, `number`, `request`, or `task`, rather than single-character names in long logic.

## 4. Differences Between a Type Pattern and an Explicit Cast

To understand the problem that patterns solve, compare it with the two-step check-and-cast approach:

```java
static int lengthIfString(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.length();
    }
    return 0;
}
```

With Java 17, the check and variable binding are expressed in one place:

```java
static int lengthIfString(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

| Comparison point | Check + explicit cast | Type pattern in Java 17 |
|---|---|---|
| Checking the object | `value instanceof String` | `value instanceof String text` |
| Obtaining a `String`-typed reference | Write `(String) value` separately | Variable `text` is bound when the check is true |
| Variable availability | Depends on manually declared variable scope | Depends on control-flow analysis |
| Risk of wrong variable / repeated casts | Easy to introduce in long code blocks | Reduces repetition and ties the variable to the check |
| Java 17 compatibility | Yes | Yes, stable syntax |

Type patterns do not render every cast obsolete. Explicit casts remain useful when a type relationship is guaranteed by another contract, or when you want an error if incompatible. However, for **"if it is of this type, handle it as this type"** scenarios, type patterns usually communicate intent more clearly.

## 5. Where Does a Pattern Variable Exist? Flow Scoping

The most important point when learning pattern variables is that **their scope is determined by control flow** (*flow scoping*). The compiler only allows using the variable where it can conclude that the pattern matched and the variable has been assigned a value.

In a typical example:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Valid.
    } else {
        System.out.println("Not a String");
        // System.out.println(text);       // Compile error.
    }

    // System.out.println(text);           // Invalid here.
}
```

When the condition is true, `text` exists in the `if` branch. When the condition is false, Java does not have a `String` bound to `text`. After the entire `if` statement above, control flow could arrive from either the true or false branch, so `text` cannot be safely used.

**Flow scoping does not mean a pattern variable always lives only inside the first pair of curly braces.** If control flow proves the pattern definitely matched at a later position, the variable can still be used.

### 5.1. Scope in the `if` branch

```java
static String show(Object obj) {
    if (obj instanceof String s) {
        return "Length = " + s.length();
    }
    return "Different type";
}
```

`s` is valid inside the `if` branch because that branch only executes when `obj instanceof String s` returns `true`.

### 5.2. Early-exit branches and subsequent scope

```java
static String normalize(Object obj) {
    if (!(obj instanceof String text)) {
        return "Not a String";
    }

    // Can only reach here if the String text pattern matched.
    return text.strip();
}
```

In this case, the non-matching branch returned via `return`, so every remaining path went through a successful pattern match. The compiler allows using `text` **after the `if` statement**.

The same applies to throwing an exception:

```java
static String requireString(Object obj) {
    if (!(obj instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text;
}
```

This is a useful input-checking style in multi-branch methods: check the failure condition first, exit early, and then process the main logic with a properly typed variable.

### 5.3. Scope scenario table

| Expression or flow | Where can the pattern variable be used? | Reason |
|---|---|---|
| `if (o instanceof String s) { ... }` | Inside the true branch | The true branch guarantees `s` is bound |
| `if (o instanceof String s) { ... } else { ... }` | Cannot use `s` in the `else` branch | The false branch does not create a binding |
| `if (o instanceof String s && s.length() > 0)` | Right-hand side of `&&` and body of the true branch | The right-hand side only runs when the left-hand side is true |
| `if (o instanceof String s || condition)` | Cannot freely use `s` on the right-hand side or in the `if` body | The branch can be true due to `condition` even if the pattern did not match |
| `if (!(o instanceof String s)) return; ...` | After `if` once the failure path terminates | All remaining paths guarantee the pattern succeeded |

## 6. Combining Type Patterns with `&&`, `||`, and `!`

### 6.1. `&&` with additional conditions

This is one of the most natural applications:

```java
static boolean hasLongName(Object obj) {
    return obj instanceof String name && name.length() >= 8;
}
```

The `&&` operator evaluates from left to right and *short-circuits*: if the left-hand side is false, the right-hand side does not run. Because the right-hand side can only run when the pattern has matched, `name.length()` is valid and safe.

Multiple conditions can be chained:

```java
static boolean isUsefulLabel(Object obj) {
    return obj instanceof String label
            && !label.isBlank()
            && label.length() <= 50;
}
```

There is no need to check `label != null` in this condition chain, because a `String label` pattern never matches `null`.

### 6.2. Why can't `&&` be replaced with `||`?

```java
static boolean incorrect(Object obj) {
    // COMPILE ERROR — do not use this in an application.
    return obj instanceof String text || text.length() > 3;
}
```

With `||`, the right-hand side is evaluated only when the left-hand side is **false**. At that exact moment `text` has no binding, so the compiler disallows using it.

Valid code corresponding to the intent "is a string and has at least four characters" is:

```java
static boolean correct(Object obj) {
    return obj instanceof String text && text.length() > 3;
}
```

Even when using `if (obj instanceof String text || someOtherCondition)`, inside the `if` body the case where `someOtherCondition` is true and the pattern failed can still occur; thus `text` cannot be considered always bound.

### 6.3. Negating a pattern with `!`

```java
static String trimmedOrDefault(Object obj) {
    if (!(obj instanceof String text)) {
        return "<not text>";
    }
    return text.strip();
}
```

`!(obj instanceof String text)` is the negation of a pattern check. When the negated condition is **false**, the original pattern was **true**. Only after excluding the failure branch with `return` or `throw` can `text` be used afterward.

An **invalid** example:

```java
static void bad(Object obj) {
    if (!(obj instanceof String text)) {
        // System.out.println(text); // Error: the pattern did not match here.
    }
}
```

Read the actual logical direction of the expression rather than guessing variable scope purely from the position of the `if` keyword.

## 7. Type Patterns Combined with Multiple Processing Branches

A method sometimes receives values belonging to several known types. Type patterns allow each branch to use a properly typed variable:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String length: " + text.length();
    } else if (value instanceof Integer number) {
        return "Integer doubled: " + (number * 2);
    } else if (value instanceof java.time.LocalDate date) {
        return "Year: " + date.getYear();
    }
    return "Unsupported";
}
```

In each branch:

- `text` only represents a `String`.
- `number` only represents an `Integer`.
- `date` only represents a `LocalDate`.

With `return` in each branch, execution finishes as soon as a matching type is found.

**Design note:** if all classes are controlled by the application and need the same behavior, **interfaces and polymorphism** are sometimes preferable to a long `instanceof` chain. Pattern matching is especially useful at integration boundaries, when accepting a broad type (`Object`), when classifying values from libraries, or when the concrete types' design cannot be modified.

## 8. Static Type Boundaries and Common Compile Errors

### 8.1. The left-hand type must be compatible with the checked type

Here is a commonly used example:

```java
Object value = "ok";
if (value instanceof String text) {
    System.out.println(text);
}
```

However, not every pair of types can be checked:

```java
Integer number = 10;
// if (number instanceof String text) {} // Incompatible types.
```

Between `Integer` and `String`, there is no reference relationship allowing a type conversion like the expression above. The compiler can catch the mistake immediately rather than waiting until runtime.

### 8.2. Do not use a type pattern when the type is already obvious from the expression

In Java 17, a type pattern is considered **unconditional** if the static type on the left is already a subtype of the target type; using it in `instanceof` as below is invalid:

```java
String text = "hello";
// if (text instanceof String sameText) {} // Error in Java 17.
```

Because `text` already has type `String`, simply use `text` directly. If the concern is whether data is empty or missing, check `text != null` or `!text.isBlank()` according to the actual contract.

A meaningful check is when **the declared type is broader than the type you need to work with**:

```java
CharSequence sequence = "hello";
if (sequence instanceof String actualString) {
    System.out.println(actualString.toUpperCase());
}
```

### 8.3. No type patterns for primitives

```java
Object value = 17;
// if (value instanceof int n) {} // Invalid.

if (value instanceof Integer number) {
    System.out.println(number + 1);
}
```

The literal `17` is boxed into an `Integer` when assigned to an `Object` variable. This is why it can be checked against `Integer`, whereas `int` cannot be used as a reference type pattern.

### 8.4. Generic types and type erasure

An object may be `List<String>` or `List<Integer>` at compile time, but type arguments cannot always be checked at runtime due to **type erasure**.

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> items) {
    System.out.println("Size: " + items.size());
}
```

`List<?>` is a valid choice when you need to confirm an object is a `List` without knowing the element type.

Conversely:

```java
Object value = java.util.List.of("A", "B");
// if (value instanceof java.util.List<String> strings) {}
// Invalid for an Object-typed expression: cannot check
// the String type argument of List this way at runtime.
```

When you need to validate elements, check each value according to the contract:

```java
static boolean allStrings(Object candidate) {
    if (!(candidate instanceof java.util.List<?> items)) {
        return false;
    }
    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }
    return true;
}
```

The check above only validates **the currently present elements**. It does not prove the type parameter declared where the list was created, nor does it protect a mutable list from having non-string elements added later.

### 8.5. Duplicate variable names and actual scope

Do not declare a pattern variable with the same name as a local variable already in scope:

```java
static void print(Object value) {
    String text = "fallback";
    // if (value instanceof String text) {} // Collides with local variable name.

    if (value instanceof String candidate) {
        System.out.println(candidate);
    } else {
        System.out.println(text);
    }
}
```

Pattern variables follow Java's naming and scoping rules. Clear naming reduces confusion when there are multiple branches and checked types.

### 8.6. Pattern variables are not required to be `final`

In Java 17, a pattern variable is not implicitly `final`. However, assigning another value to a newly bound variable can make readers unsure whether the variable represents the checked object or a new value.

Generally, treat the pattern variable as a **type-confirmed reference** for reading or calling methods, and create a new variable if a transformed result is needed:

```java
if (value instanceof String text) {
    String normalized = text.strip().toLowerCase(java.util.Locale.ROOT);
    System.out.println(normalized);
}
```

Pattern variables still follow Java's rules for lambda capture: if used inside a lambda, it must be `final` or *effectively final* in that context.

## 9. `instanceof` Patterns with Records, Interfaces, and Inheritance

Type patterns work with many reference types, including interfaces and records. The key point is that **the pattern checks the object's type**, rather than automatically extracting fields inside the object.

Record example in Java 17:

```java
record Point(int x, int y) {}

static String format(Object value) {
    if (value instanceof Point point) {
        return "(" + point.x() + ", " + point.y() + ")";
    }
    return "Not a point";
}
```

When the `Point point` pattern matches, we use the accessors `point.x()` and `point.y()` to read the components.

Do not confuse the syntax above with a **record pattern** such as `Point(int x, int y)`. Record patterns were finalized in Java 21 and are **not stable syntax available in Java 17**. When targeting Java 17, the standard approach is binding `Point point` and then accessing the components.

With interfaces, a type pattern can check whether an object implements an interface:

```java
interface Named {
    String name();
}

record Employee(String name) implements Named {}

static String display(Object value) {
    if (value instanceof Named person) {
        return person.name();
    }
    return "Unnamed";
}
```

`person` has static type `Named`, so only methods declared by this interface can be called directly. Java does not automatically infer `person` to be `Employee` just because one concrete implementation is used somewhere.

### The order of checks matters

```java
static String categorize(Object value) {
    if (value instanceof Number number) {
        return "Number: " + number;
    }
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    return "Other";
}
```

This snippet is valid, but if `value` is an `Integer`, the `Number` branch already matches first, so the `Integer` branch below never runs. To handle `Integer` separately, check it **before** `Number`:

```java
static String categorize(Object value) {
    if (value instanceof Integer integer) {
        return "Integer: " + integer;
    }
    if (value instanceof Number number) {
        return "Number: " + number;
    }
    return "Other";
}
```

This technique applies to subtype/supertype relationships and when checking multiple interfaces that might be implemented by the same object.

## 10. Comprehensive Example Runnable on Java 17

The following program receives data via an `Object` parameter and uses type patterns to handle each type. The `Ticket` record is used to illustrate binding a record like a normal object.

Create the file `Main.java`:

```java
import java.util.List;

public class Main {
    record Ticket(String code, int priority) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text (" + text.length() + "): " + text;
        }

        if (value instanceof Ticket ticket) {
            return "Ticket " + ticket.code()
                    + ", priority=" + ticket.priority();
        }

        if (value instanceof List<?> items) {
            return "List size: " + items.size();
        }

        if (value == null) {
            return "No value";
        }

        return "Other: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new Ticket("T-42", 2)));
        System.out.println(describe(List.of(10, 20, 30)));
        System.out.println(describe(null));
        System.out.println(describe(""));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Expected output:

```text
Text (4): Java
Ticket T-42, priority=2
List size: 3
No value
Other: String
```

Analysis:

1. `"Java"` matches `String text`, then `!text.isBlank()` is true; the first branch can use `text.length()`.
2. `new Ticket(...)` is not a `String`, but matches `Ticket ticket`; `ticket.code()` is a record accessor.
3. `List.of(...)` matches `List<?> items`; we use general `List` operations without assuming the element type.
4. `null` does not match any type pattern and is handled by the `value == null` check.
5. The empty string is still a `String` but `!text.isBlank()` is false, so it falls through to the final branch. This example clearly shows that **type matching** and **satisfying an additional condition** are two distinct logical steps.

Note: if you want all `String` values to enter the same branch, move the `isBlank()` check inside the `if (value instanceof String text)` branch instead of combining it with `&&`.

## 11. Suitable Scenarios in Real-World Code

### 11.1. Checking return values at API boundaries

When an API or plugin handler returns `Object`, type patterns help check before calling specialized methods:

```java
static int resultCount(Object response) {
    if (response instanceof java.util.Collection<?> collection) {
        return collection.size();
    }
    throw new IllegalArgumentException("Expected a collection");
}
```

Instead of casting unconditionally and waiting for `ClassCastException`, the method raises an error with a meaning that better matches the input contract.

### 11.2. Handling multiple event types

```java
interface Event {}
record Connected(String clientId) implements Event {}
record Disconnected(String clientId) implements Event {}

static String eventMessage(Event event) {
    if (event instanceof Connected connected) {
        return "Connected: " + connected.clientId();
    }
    if (event instanceof Disconnected disconnected) {
        return "Disconnected: " + disconnected.clientId();
    }
    return "Unknown event";
}
```

This is a simple approach when classifying a few event types. If the API is designed by the project and the behavior belongs on each event type, you should still consider polymorphism or an appropriate sealed hierarchy to avoid concentrating too many branches in one method.

### 11.3. Avoiding unsafe `null` handling

```java
static String title(Object candidate) {
    if (candidate instanceof CharSequence text && text.length() > 0) {
        return text.toString();
    }
    return "Untitled";
}
```

The `CharSequence text` branch only runs with a compatible non-null object. This avoids repeated `null` checks inside that branch. However, if the logic needs to distinguish between `null` and "wrong type", you must still explicitly check each case.

## 12. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| “`instanceof String s` changes the declared type of the original variable.” | The original variable keeps its static type; the pattern variable `s` has type `String` where the binding is valid. |
| “You can use `s` everywhere after writing the pattern.” | Scope depends on control flow: only where the pattern is guaranteed to have matched. |
| “`&&` and `||` give the same scope for the pattern variable.” | `&&` evaluates the right-hand side when the left-hand side is true, while `||` evaluates the right-hand side when the left-hand side is false; their scopes differ. |
| “`instanceof` can match `null` with a type pattern.” | A type pattern `T t` returns false for `null`. |
| “You can check `List<String>` from an arbitrary `Object`.” | Type erasure prevents checking type arguments in this situation; typically use `List<?>` and validate elements when needed. |
| “A type pattern can use the primitive `int`.” | Java 17 `instanceof` type patterns accept reference types, such as `Integer`, not primitives. |
| “Pattern `instanceof` and pattern `switch` are completely the same in Java 17.” | Type patterns in `instanceof` are a stable feature; pattern matching for `switch` is still a preview feature in Java 17. |
| “A type pattern automatically deconstructs record components.” | `obj instanceof Point p` only binds variable `p`; read components with accessors like `p.x()`. |

## 13. Practice Exercises with Solutions

### Exercise 1 — Predict the result

```java
static String inspect(Object value) {
    if (value instanceof String text && text.length() > 2) {
        return "LONG: " + text;
    }
    return "OTHER";
}
```

Predict the results for:

```java
inspect("AB")
inspect("ABC")
inspect(null)
inspect(Integer.valueOf(5))
```

**Answer:** `OTHER`, `LONG: ABC`, `OTHER`, `OTHER`, respectively. The pattern only binds the variable when the value is actually a `String`; the `length() > 2` condition is checked afterward.

### Exercise 2 — Identify invalid pattern variable usage

```java
static String bad(Object obj) {
    if (obj instanceof String text) {
        return text.toUpperCase();
    }
    return text;
}
```

The final `return text;` line is invalid: that is the path where `obj instanceof String text` **did not match**, so `text` is not bound. Fix it as follows:

```java
static String fixed(Object obj) {
    if (obj instanceof String text) {
        return text.toUpperCase();
    }
    return "Not text";
}
```

### Exercise 3 — Write a concise and safe condition

Requirement: `true` only when `value` is a `String`, is not blank, and is at most 20 characters long.

```java
static boolean validLabel(Object value) {
    return value instanceof String label
            && !label.isBlank()
            && label.length() <= 20;
}
```

The solution combines type checking and additional conditions without calling methods on a `null` reference.

### Exercise 4 — Check type then exit early

Write a method taking an `Object`, returning a normalized version of the string with leading/trailing whitespace removed; throw `IllegalArgumentException` if the data is not a string.

```java
static String normalizeOrFail(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected text");
    }
    return text.strip();
}
```

`text` is allowed after the `if` statement because the failure branch terminated via `throw`.

### Exercise 5 — Distinguish `List<?>` from `List<String>`

Write a method taking an `Object` and counting how many elements are non-blank strings when the value is a `List`; if it is not a `List`, return 0.

```java
static long countNonBlankStrings(Object value) {
    if (!(value instanceof java.util.List<?> items)) {
        return 0;
    }
    return items.stream()
            .filter(item -> item instanceof String text && !text.isBlank())
            .count();
}
```

Note: `List<?>` does not assert the type of each element. The type pattern `String text` is evaluated individually for each element inside the `filter` predicate.

## 14. Lesson Completion Criteria

Learners understand **type patterns and pattern variables in `instanceof`** when they can:

1. Clearly explain the three parts of `expression instanceof Type variable`, distinguishing a type pattern from a pattern variable.
2. Predict behavior when the object has a matching type, a non-matching type, or is `null`.
3. Write `if (obj instanceof SomeType x)` and use `x` without casting again.
4. Explain why `x` is valid in the true branch, on the right-hand side of `&&`, and after a negated branch ending with `return`/`throw`.
5. Point out scoping errors in examples using `||`, `else` branches, and code outside the binding region.
6. Recognize static type constraints, primitive restrictions, and type erasure limits with generics.
7. Apply type patterns in scenarios involving interfaces, records, or broad return types.
8. Compile examples with `javac --release 17` without using preview syntax or syntax finalized only in newer versions.

## 15. Official Documentation

- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394): describes the motivation, binding behavior, and flow scoping of pattern variables.
- [Java Language Specification, Java SE 17 — `instanceof` Operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): rules for `instanceof` expressions.
- [Java Language Specification, Java SE 17 — Scope of Pattern Variables (§6.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scope based on control flow.
- [Java Language Specification, Java SE 17 — Patterns (§14.30)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): grammar and semantics of type patterns.

The core takeaway is: **`instanceof` confirms the object's type; a type pattern simultaneously binds a properly typed variable; the compiler only allows using the variable when control flow guarantees the pattern has matched**. Understanding this rule helps you write concise and safe conditions in Java 17 while avoiding variable-scoping errors when combining logical operators.
