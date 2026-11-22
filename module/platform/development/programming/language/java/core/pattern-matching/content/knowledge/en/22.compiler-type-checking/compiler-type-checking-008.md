# Incompatible Selector Type Errors in Java Pattern Matching

## 1. What is a selector type and why does the compiler report an error?

In a `switch (selector)` expression or statement, the **selector** is the expression inside the parentheses. The **selector type** is the **compile-time type (static type)** of that expression: the type known to the compiler at compile time, not the runtime type of an object assigned to a variable.

For example:

```java
Object value = "Java";
String result = switch (value) {
    case String s -> "text:" + s;
    case Integer n -> "number:" + n;
    case null -> "null";
    default -> "other";
};
```

The selector `value` has the **static type `Object`**, while the value held at runtime is a `String`. Both patterns `String s` and `Integer n` can be tested against `Object`; the actual case selects the `String` branch.

Conversely:

```java
String value = "Java";

// DOES NOT COMPILE:
// String result = switch (value) {
//     case Integer n -> "number:" + n;
//     default -> "other";
// };
```

The compiler sees that the selector is definitely a `String`, while `Integer` is a type incompatible with `String`. No valid value of a `String` variable can be an `Integer`, so this pattern label is **not applicable**. The compiler reports an error before the program runs; adding `default` does not fix the type error of the `case` label.

In Java Pattern Matching, there are at least three situations to distinguish:

1. **The type of the selector itself is not supported** by `switch` in the Java version being used.
2. **The selector type is supported, but the `case` label is incompatible** with the static type of the selector.
3. **The selector type and `case` labels are valid, but there is another error**, such as a dominated branch, non-exhaustiveness, an unchecked/non-reifiable generic type, or an incompatible result type of the switch expression.

This lesson focuses on the first two groups and shows how to distinguish them from related errors.

## 2. Selector type rules in Java 21

Starting in Java 21, thanks to *pattern matching for switch* (JEP 441), `switch` can use **any reference type** as a selector, in addition to the primitive types that were already allowed.

Valid selector types in **Java 21**:

| Selector type | Supported? | Notes |
| --- | --- | --- |
| `byte`, `short`, `char`, `int` | Yes | Can use compatible constant labels; pay attention to constant values and types. |
| `Byte`, `Short`, `Character`, `Integer` | Yes | Wrapper types are reference types; consider null handling. |
| `String` | Yes | Typically uses `case "literal"` or applicable patterns. |
| `enum` | Yes | Enum labels must match the enum being switched on. |
| `Object`, `Number`, record, sealed interface, class, array, `List<?>`, etc. | Yes | Reference selectors suitable for type/record patterns. |
| `long`, `float`, `double`, `boolean` | **No** in Java 21 | This is a Java 21 language limitation for primitive selectors. |

**Version boundary:** Some newer JDKs have *preview* features for primitive patterns and `switch` over additional primitive types. When teaching or compiling targeting Java 21, you must rely on Java 21 rules; do not infer from a preview feature in a newer JDK that `switch(long)`/`switch(boolean)` is supported in Java 21.

Examples that **do not compile in Java 21**:

```java
long orderId = 5L;

// Invalid with --release 21: long is not a valid selector type.
// String label = switch (orderId) {
//     case 5L -> "five";
//     default -> "other";
// };

boolean enabled = true;

// Invalid with --release 21: boolean is not a valid selector type.
// String label = switch (enabled) {
//     case true -> "yes";
//     default -> "no";
// };
```

How to fix depending on the goal:

- For `boolean` with only two states, use `if/else` or the ternary operator: `enabled ? "yes" : "no"`.
- For `long`, use `if/else` or an appropriate construct. If you are certain all values fall within the `int` range, you can check bounds and convert to `int`; **do not cast arbitrarily**, because truncating bits will corrupt large values.
- If an API returns `Long` instead of `long`, `Long` is a reference type and can be used as a selector in Java 21 with valid patterns, such as `case Long n -> ...`. However, `case 5L` is not equivalent to the type pattern `case Long n when n == 5L`: constant labels are subject to their own rules.

## 3. Pattern labels must be applicable to the selector

For `case T variable`, the pattern type `T` must be **applicable** at the static type of the selector. Simply put, the compiler needs to see a valid type conversion possibility under pattern matching rules; you cannot write a pattern for two mutually exclusive types.

### Case A: `String` cannot match `Integer`

```java
String text = "hello";

// DOES NOT COMPILE:
// String kind = switch (text) {
//     case Integer n -> "integer";
//     default -> "other";
// };
```

Typical message: `String cannot be converted to Integer` or `incompatible types`.

**Purpose-driven fix:** If the data can only be a `String`, use string constant/`String` branches instead of `Integer`:

```java
String kind = switch (text) {
    case "hello" -> "greeting";
    default -> "another string";
};
```

If the problem genuinely needs to handle multiple different runtime types, declare the parameter to accept **`Object`** and classify using type patterns:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string:" + s;
        case Integer n -> "integer:" + n;
        case null -> "null";
        default -> "other";
    };
}
```

Only widen the input type to `Object` when the API genuinely needs to accept different types of data; do not change the signature just to mask a data design flaw.

### Case B: `Number` cannot match `String`

```java
Number number = Integer.valueOf(12);

// DOES NOT COMPILE:
// String output = switch (number) {
//     case String s -> s;
//     default -> "not string";
// };
```

`String` is not a subtype of `Number`, and there is no valid type test for this pattern from a `Number` selector.

Fix to classify **numeric types**:

```java
String output = switch (number) {
    case Integer i -> "int:" + i;
    case Double d -> "double:" + d;
    case null -> "null number";
    default -> "another number";
};
```

`Integer` and `Double` both belong to the `Number` hierarchy. `default` is still required in this example because `Number` has other subtypes (e.g., `Long`, `Float`, `BigDecimal`).

### Case C: Incompatible component of a generic record

The selector can be a record, yet a nested pattern on its component has the wrong type:

```java
record Box<T>(T value) {}

Box<String> strings = new Box<>("abc");

// DOES NOT COMPILE:
// String kind = switch (strings) {
//     case Box(Integer n) -> "integer";
//     default -> "other";
// };
```

With `Box<String>`, the compiler knows the `value` component has type `String`, so `Integer n` cannot match. This is a **component pattern** error, even though the message still mentions incompatible types.

Fix with the exact component type or `var`:

```java
String kind = switch (strings) {
    case Box(String s) -> "text:" + s;
};
```

`Box(var s)` also infers `s` as `String` from the static type `Box<String>`.

## 4. Constant labels differ from pattern labels: `case 1` with `Object`

This is a common pitfall after `switch` gained support for `Object` in Java 21.

```java
Object value = 1;

// DOES NOT COMPILE in Java 21:
// String result = switch (value) {
//     case 1 -> "one";
//     default -> "other";
// };
```

Even though the runtime value is `Integer(1)`, the **constant label** `case 1` is incompatible with a selector of type `Object` under switch label rules. Typical error: `constant label of type int is not compatible with switch selector type Object`.

How to fix when you want to classify an `Object` by numeric value:

```java
String result = switch (value) {
    case Integer n when n == 1 -> "one";
    case Integer n -> "another int:" + n;
    case null -> "null";
    default -> "other";
};
```

This is a **type pattern `Integer n`** with a guard `when n == 1`, which is different from the constant label `case 1`.

If the input is already guaranteed to be an `int`, keep the selector type as `int` and use constant labels:

```java
int valueAsInt = 1;

String result = switch (valueAsInt) {
    case 1 -> "one";
    default -> "other";
};
```

**Practical rule:** With an `Object` or broad interface/class selector, use type/record patterns to identify the runtime type. Do not copy `case 1` or `case "A"` verbatim from a switch on `int`/`String` to a switch on `Object` without checking constant label compatibility rules.

## 5. Complete runnable example: choosing appropriate selector types and cases

Save the code as **`SelectorTypeDemo.java`**. The Java 21+ program below classifies `Object`, `Number`, `String`, and uses sealed record patterns.

```java
public class SelectorTypeDemo {
    sealed interface Result permits Success, Failure {}

    record Success(String message) implements Result {}
    record Failure(int code) implements Result {}

    static String classify(Object selector) {
        return switch (selector) {
            case String text -> "text:" + text;

            case Integer n when n > 0 -> "positive-int:" + n;
            case Integer n -> "other-int:" + n;

            case Success(var message) -> "success:" + message;
            case Failure(int code) -> "failure:" + code;

            case null -> "null";
            default -> "other:"
                    + selector.getClass().getSimpleName();
        };
    }

    static String classifyNumber(Number selector) {
        return switch (selector) {
            case Integer n -> "int:" + n;
            case Double d -> "double:" + d;
            case null -> "null number";
            default -> "another number";
        };
    }

    static boolean nonBlankText(Object selector) {
        return selector instanceof String s && !s.isBlank();
    }

    static String classifyString(String selector) {
        return switch (selector) {
            case "A" -> "letter A";
            case "B" -> "letter B";
            case null -> "null string";
            default -> "other string";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("hello"));
        System.out.println(classify(7));
        System.out.println(classify(-2));
        System.out.println(classify(new Success("OK")));
        System.out.println(classify(new Failure(404)));
        System.out.println(classify(2.5));
        System.out.println(classify(null));

        System.out.println(classifyNumber(4));
        System.out.println(classifyNumber(2.5));
        System.out.println(classifyNumber(null));

        System.out.println(nonBlankText("Java"));
        System.out.println(nonBlankText(" "));
        System.out.println(classifyString("A"));
    }
}
```

Compile with JDK 21 or newer, but **enforce Java 21 rules**:

```bash
javac --release 21 SelectorTypeDemo.java
java SelectorTypeDemo
```

Output:

```text
text:hello
positive-int:7
other-int:-2
success:OK
failure:404
other:Double
null
int:4
double:2.5
null number
true
false
letter A
```

**Why does this program work?**

1. `classify(Object)` has a static selector of `Object`, so the patterns `String`, `Integer`, `Success`, and `Failure` can all be tested.
2. `Integer n when n > 0` must come before the general `Integer n`. If the general branch is placed first, the compiler will report the guarded branch as **dominated**.
3. `Success(var message)` and `Failure(int code)` are record patterns; each record type is a valid variant of the sealed interface `Result`, but the `Object` parameter still allows other types. Therefore `default` is still needed for `Object`.
4. `classifyNumber(Number)` only has patterns compatible with the `Number` hierarchy. `String` would be invalid, whereas `Integer` and `Double` are valid.
5. `classifyString(String)` uses valid string constant labels for a `String` selector.
6. `case null` isolates a null selector; without a matching branch, a pattern switch does not route null into `default` by default.

## 6. Generics and type erasure: confusing selector type with generic arguments

An `Object` selector can hold a `List<String>` at runtime, but the JVM generally does not retain the `String` type argument for testing via `instanceof`/type patterns.

```java
Object source = java.util.List.of("a", "b");

// DOES NOT COMPILE:
// String result = switch (source) {
//     case java.util.List<String> list -> "texts";
//     default -> "other";
// };
```

An error like `Object cannot be safely cast to List<String>` is related to **non-reifiable generic types**, not simply missing a `default` branch.

Fix using a reifiable wildcard:

```java
String result = switch (source) {
    case java.util.List<?> list ->
            "size=" + list.size();
    case null -> "null";
    default -> "other";
};
```

If you genuinely need the elements to be `String`, iterate and check each element or preserve the generic information in the API signature from the start:

```java
static String joinUpper(java.util.List<String> values) {
    return values.stream()
            .map(String::toUpperCase)
            .collect(java.util.stream.Collectors.joining(","));
}
```

`List<?>` guarantees the object is a `List`, **not** that all elements are `String`. Similarly, do not arbitrarily replace `Box<?>` with `Box<String>` if the input only has type `Object`.

## 7. Similar errors that are not selector type mismatches

### 7.1. Dominated branch

```java
Object input = "Java";

// DOES NOT COMPILE:
// String answer = switch (input) {
//     case Object any -> "any";
//     case String s -> "text"; // dominated
// };
```

Here `String` is a **valid** pattern type for an `Object` selector. The error occurs because the unguarded `Object` branch dominates the `String` branch after it. The fix is to place specific patterns before broader patterns.

### 7.2. Non-exhaustive switch expression

```java
Object input = 1;

// DOES NOT COMPILE:
// String answer = switch (input) {
//     case String s -> "text";
// };
```

`String s` is applicable to `Object`, but it does not cover `Integer`, records, null, etc. A switch expression requires exhaustive branches; add `default` or appropriate covering patterns. For sealed hierarchies, the compiler can infer exhaustiveness from the permitted subtypes.

### 7.3. Incompatible return value type of a switch expression

```java
// DOES NOT COMPILE:
// String answer = switch (1) {
//     case 1 -> 100;
//     default -> 200;
// };
```

The selector `1` of type `int` is **valid**; the error is that the branches return integers while the receiving variable requires `String`. Fix by changing them to `"100"`/`"200"` or changing the receiving variable type to `int`.

### 7.4. Invalid pattern/guard variable scope

```java
Object input = 10;

// DOES NOT COMPILE:
// if (input instanceof Integer n || n > 0) {
//     System.out.println(n);
// }
```

The right-hand side of `||` can execute when `instanceof` is false, so `n` is not bound. Use `&&` if you want to check an additional condition after the pattern matches:

```java
if (input instanceof Integer n && n > 0) {
    System.out.println(n);
}
```

This flow scoping error happens outside `switch` and is not caused by the selector type.

### 7.5. Null: type-valid but fails at runtime

A reference selector can have the value `null`. The pattern `case Integer n` does not match a null selector; if there is no matching null branch, the program can throw a `NullPointerException` instead of selecting `default`. That is a separate runtime error, not a compile-time type compatibility error.

## 8. How to diagnose and fix quickly

When you see messages like `incompatible types`, `cannot be converted to`, `constant label ... is not compatible`, or `selector type ... is not allowed`, check in this order:

1. **Identify the version and compiler flags.** For this lesson, use `javac --release 21`. Preview features of newer JDKs are not part of Java 21 semantics.
2. **Note the exact static type of the expression in `switch (...)`.** Do not just look at the object created with `new` on the previous line. If the selector is declared as `Object`, the compiler does not treat it as `String` just because it holds a string.
3. **Check whether the selector type is allowed.** Primitive `long`, `float`, `double`, and `boolean` are not valid selector types in Java 21.
4. **Determine whether the label is a constant or a pattern.** `case 1` has different rules from `case Integer n when n == 1`. Do not rely on autoboxing to assume every constant label is valid for `Object`.
5. **Match the pattern type against the selector.** `String` cannot match `Integer`; `Number` cannot match `String`; but `Object` can match both. For record patterns, check each component as well.
6. **If generics are involved, consider type erasure.** `List<String>` cannot be safely checked from `Object`; `List<?>` is valid for checking the container's raw type.
7. **If all types are compatible, check branch ordering, exhaustiveness, null, and result type.** These errors have similar messages but different root causes.

**Do not fix by casting unconditionally.** Adding `(Integer) input` can turn a compile-time error into a runtime `ClassCastException` if the input is not actually an `Integer`. Prefer keeping the API properly typed, using applicable patterns, and handling non-matching values explicitly.

## 9. Self-check exercises

**Exercise 1.** Why is the following snippet invalid?

```java
Object raw = 10;
// String out = switch (raw) {
//     case 10 -> "ten";
//     default -> "other";
// };
```

Answer: `case 10` is a constant label of type `int`, which is incompatible with an `Object` selector under Java 21 rules. Fix it to `case Integer n when n == 10 -> "ten"`, and add appropriate branches.

**Exercise 2.** With `Number number = 2.5;`, can you use `case Double d`?

Yes. `Double` is a subtype of `Number`, so the pattern is applicable. `case String s` in a switch on `Number` is not.

**Exercise 3.** With `Box<String> box`, what should you use to extract the string in the component?

Use `Box(String s)` or `Box(var s)`; the compiler knows the component is a `String`. `Box(Integer n)` is invalid in that context.

**Exercise 4.** What happens if a switch expression on `Object` has `case String s` and `default` but is missing `case null`?

The `String` branch does not accept null, and a regular `default` does not handle a null selector in a pattern switch; when the selector is null, it can throw a `NullPointerException`. Add `case null` or an explicit null-handling construct if null is a valid input.

## 10. Key takeaways

**The selector type determines which kinds of `case` labels the compiler allows.** Java 21 supports `char`, `byte`, `short`, `int`, and any reference type as a selector; primitive `long`, `float`, `double`, and `boolean` are not yet supported. A pattern must be able to match values of the selector's static type, while constant labels are subject to their own constant compatibility rules. When encountering an error, identify the exact failure category—**selector type, label type, component/generic, domination, exhaustiveness, or result type**—and fix it at the root cause.

### References

- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11, `14.30.3: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
