# Combining Generic Records with Record Patterns

**Topic:** Java Core Pattern Matching → Generic and Reifiable Types  
**Practice version:** Java 21 or later. Record patterns have been an official feature since Java 21 (JEP 440); `--enable-preview` does not need to be enabled.

## 1. The Problem and Main Idea

A `record` in Java is a data type with explicitly declared *components*. A record can also carry type parameters (*generic*), such as `Box<T>` holding a value of type `T`. A **record pattern** allows checking whether an object is of a matching record type and deconstructing its components into local variables right at the match site.

For example, when a method receives `Box<String>`, you can write `box instanceof Box(var text)` to extract the `text` component without having to manually call `box.value()`. The compiler infers the type of `text` from the known `Box<String>` type. This is a combination of compile-time **generic type inference** and record pattern **deconstruction**.

However, `Box<String>` does not have the `String` type argument information fully preserved at runtime due to *type erasure*. A record pattern does not "restore" an erased type argument either. It is important to clearly distinguish between checking the **record object**, checking the **component value**, and relying on the **static generic type** of the input expression.

Goals after this lesson: write record patterns with explicit or inferred type arguments; understand `var` and nested patterns; recognize limitations with raw types, wildcards, and non-reifiable types; choose safe checks when the input has a broad type.

## 2. Declaring Generic Records and Record Pattern Syntax

Suppose we have three records:

```java
record Box<T>(T value) {}

record Pair<L, R>(L left, R right) {}

record Envelope<T>(String label, Box<T> box) {}
```

`Box<T>` has one component of type `T`; `Pair<L, R>` has two separate type parameters; `Envelope<T>` shows that a generic record can contain another generic record.

With the object `Box<String> box = new Box<>("Java");`, the corresponding ways to read the data are:

```java
String a = box.value();                   // Access the component using the accessor.
if (box instanceof Box<String>(String b)) {
    System.out.println(b);                // Record pattern with explicit type.
}
if (box instanceof Box(var c)) {
    System.out.println(c.toUpperCase());  // c is inferred as String.
}
```

In `Box<String>(String b)`:

- `Box<String>` is the **record type in the pattern**; here the input type is already known to be `Box<String>`, so the match does not require an unsafe generic cast.
- `String b` is the **component pattern**. The component is deconstructed and bound to `b` when the pattern matches.
- `Box(var c)` omits explicitly writing the type arguments and the component type. The compiler infers the types from context; with `Box<String>`, `c` has the static type `String`.

In an `if` statement, pattern variables are only in scope in control-flow locations where Java knows the pattern has matched. `Box(...)` itself does not match when the outer record object is `null`.

## 3. Type Inference for Generic Record Patterns

### 3.1. Input with a Known Generic Type

```java
static String upper(Box<String> box) {
    if (box instanceof Box(var text)) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
    return "NO_BOX";
}
```

In the matching branch, `text` is `String`, so calling `toUpperCase` is valid. If `box == null`, the record pattern does not match, and the method returns `NO_BOX`. To guard against a component that may be `null`, you still need to check `text == null` before calling methods on it.

With two type parameters, the idea remains the same:

```java
static String pairText(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var label, var count)) {
        return label + ":" + (count + 1);
    }
    return "NO_PAIR";
}
```

The compiler infers `label` as `String` and `count` as `Integer`. The addition `count + 1` uses unboxing of `Integer`, so it can still throw a `NullPointerException` if the `count` component is `null`.

### 3.2. `var` Is Static Type Inference, Not Dynamic Typing

```java
static void inspectUnknown(Object input) {
    if (input instanceof Box(var content)) {
        System.out.println(content);
        // content.toUpperCase(); // Invalid: content is not guaranteed to be String.
    }
}
```

With an input declared as `Object`, the compiler cannot assume the actual `Box<T>` is `Box<String>`. Using `Box(var content)` still deconstructs the component, but it does not grant permission to call `String`-specific methods if the inferred static type of `content` cannot prove it.

This is the difference between **compile-time generic information** and the **runtime type of the component**. The `var` keyword does not make a variable dynamically change its static type per runtime object.

## 4. When the Input Is Only `Object`: Checking the Actual Component

A safe way to handle an input whose generic type argument is unknown is to use **patterns that check the component type**:

```java
static String inspect(Object input) {
    if (input instanceof Box(String text)) {
        return "string:" + text;
    } else if (input instanceof Box(Integer number)) {
        return "integer:" + number;
    } else if (input instanceof Box(var other)) {
        return "other:" + other;
    }
    return "not-box";
}
```

When matching `Object input`, Java can infer the record pattern `Box(...)` with appropriate general type information and check the components according to each pattern:

1. `Box(String text)` only matches when the object is a `Box` and the component value matches `String` in this context.
2. `Box(Integer number)` handles a component of type `Integer`.
3. `Box(var other)` catches the remaining `Box` instances, including a `Box` with a `null` component. This branch must come after the specific branches if you want to distinguish them.
4. Objects that are not `Box`, or `input == null` itself, go to `not-box`.

**A very important point:** `Box(String text)` here checks the **component value**; it does not prove that the object's originally declared type argument was `String`. Due to *type erasure*, a `Box` object does not carry a "`T = String` tag" to compare directly at runtime.

If the application needs a strict type contract, design the API to pass `Box<String>` from the start, pass a type token such as `Class<T>` when appropriate, or validate values when receiving input data. Record patterns do not replace a data validation system.

## 5. Reifiable Types, Type Erasure, and Limits of Patterns with Type Arguments

### 5.1. What Is Reifiable?

A *reifiable* type has enough type information to perform certain safe runtime checks after compilation. For example, `String`, `Box<?>`, and `List<?>` are types that can be used for appropriate checks; conversely, `Box<String>` and `List<String>` are non-reifiable because the concrete generic argument is erased at runtime.

From an object with a broad type:

```java
Object input = new Box<>("Java");
boolean isBox = input instanceof Box<?>; // Valid: checks for Box at runtime.
```

However, it cannot be replaced with a specific parameterized type check if an unchecked conversion is required:

```java
// DOES NOT COMPILE: checking Box<String> from Object is unsafe.
// if (input instanceof Box<String>(var text)) {
//     System.out.println(text);
// }
```

Reason: going from `Object` to `Box<String>` cannot be guaranteed safe at runtime when only the raw class `Box` is known. The compiler does not allow a record pattern that requires such an unchecked conversion.

### 5.2. Why Is `Box<String>(String s)` Sometimes Valid?

```java
Box<String> known = new Box<>("ok");

if (known instanceof Box<String>(String text)) {
    System.out.println(text);
}
```

This pattern is valid because **the static type of the input is already `Box<String>`**. No unchecked conversion is needed to deduce that the object is declared under that contract. Being able to write a type argument in a record pattern **does not mean** Java can check an arbitrary generic type argument at runtime.

Similarly, accepting a raw `Box raw` and writing `raw instanceof Box<String>(var s)` does not produce valid proof for `String`. Avoid raw types and unchecked casts; if you encounter data lacking type information, use `Box<?>`, check the component, and then convert it into an API with explicit types.

### 5.3. Multi-Level Nested Generics

From `Object`, you cannot verify `Box<List<String>>` using type arguments alone. However, you can check that the component is a list with unknown elements:

```java
static int listSize(Object value) {
    if (value instanceof Box(java.util.List<?> list)) {
        return list.size();
    }
    return -1;
}
```

`List<?>` lets you know the component is a `List` and call `size()`. It **does not** prove every element is a `String`. If you want to rely on each element's type, you must check elements individually or establish a separate data contract; do not blindly cast the entire list.

## 6. Nested Record Patterns and Generic Type Inference

Suppose:

```java
Box<Box<String>> nested = new Box<>(new Box<>("inner"));
```

We can deconstruct two levels:

```java
if (nested instanceof Box(Box(var text))) {
    System.out.println(text); // Prints "inner"; text is inferred as String.
}
```

The compiler infers the type arguments of the record pattern based on the known type `Box<Box<String>>`, and then infers the pattern for the inner component. This is a **nested record pattern**, not an `instanceof Box<Box<String>>` check on an uninformative `Object`.

With `Envelope<String>`:

```java
Envelope<String> item =
        new Envelope<>("message", new Box<>("hello"));

if (item instanceof Envelope(var label, Box(var text))) {
    System.out.println(label + ":" + text); // message:hello
}
```

Here `label` is `String`, and the second-level record pattern `Box(var text)` deconstructs the content `hello`. If the `box` component is `null`, the nested `Box(...)` pattern does not match. If `item` itself is `null`, the outer record pattern does not match either.

**Note on `null`:** a component of a generic record can hold `null` even when the type argument is `String`. A type pattern nested directly inside a record pattern can be *null-matching* if it is *unconditional* for the statically determined component type. For instance, with `Box<String> knownNull = new Box<>(null)`, `knownNull instanceof Box(String s)` can match and yield `s == null`. On the other hand, when the same object is viewed only as `Object unknown`, `unknown instanceof Box(String s)` does not match a `null` component by default, because the compiler does not know the component has static type `String`. Always guard potentially null variables before calling methods.

## 7. Combining with `switch` in Java 21

Record patterns can appear in `instanceof` and in `switch` `case` branches. Here is an example of a descriptor that also handles a null selector:

```java
static String describeEnvelope(Envelope<String> input) {
    return switch (input) {
        case null -> "no-envelope";
        case Envelope(var label, Box(var text)) -> label + ":" + text;
        default -> "no-box";
    };
}
```

Processing order:

- `case null` is dedicated to a `null` selector.
- `case Envelope(var label, Box(var text))` deconstructs the `label` component and the inner `Box` record when both levels match.
- `default` handles unmatched values, such as an existing `Envelope<String>` whose `box` component is `null`.

A `switch` expression must ensure exhaustiveness. If you omit `default` and the remaining patterns do not cover every possible value, the compiler may report a lack of *exhaustiveness*. Do not use `case Box<String>(...)` on an `Object` as a way to check a runtime type argument.

## 8. Complete Java 21 Program

The program below brings together the cases: known generic type, object with unknown type argument, nested record, `switch`, `List<?>`, and `null`.

Create the file **`GenericRecordPatternDemo.java`**:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}

    record Envelope<T>(String label, Box<T> box) {}

    static String known(Box<String> box) {
        if (box instanceof Box(var text)) {
            return "known:" + text.toUpperCase(java.util.Locale.ROOT);
        }
        return "missing";
    }

    static String inspect(Object input) {
        if (input instanceof Box(String text)) {
            return "string:" + text;
        } else if (input instanceof Box(Integer number)) {
            return "integer:" + number;
        } else if (input instanceof Box(var other)) {
            return "other:" + other;
        }
        return "not-box";
    }

    static String nested(Box<Box<String>> value) {
        if (value instanceof Box(Box(var text))) {
            return "nested:" + text;
        }
        return "nested-unmatched";
    }

    static String describeEnvelope(Envelope<String> input) {
        return switch (input) {
            case null -> "no-envelope";
            case Envelope(var label, Box(var text)) -> label + ":" + text;
            default -> "no-box";
        };
    }

    static int listSize(Object input) {
        if (input instanceof Box(java.util.List<?> list)) {
            return list.size();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println(known(new Box<>("Java")));
        System.out.println(known(null));

        System.out.println(inspect(new Box<>("hello")));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(inspect(new Box<>(3.5)));
        System.out.println(inspect("plain"));
        System.out.println(inspect(new Box<String>(null)));

        System.out.println(nested(new Box<>(new Box<>("inner"))));
        System.out.println(nested(new Box<Box<String>>(null)));

        System.out.println(
                describeEnvelope(new Envelope<>("msg", new Box<>("OK"))));
        System.out.println(
                describeEnvelope(new Envelope<String>("missing", null)));
        System.out.println(describeEnvelope(null));

        System.out.println(
                "size=" + listSize(new Box<>(java.util.List.of("a", "b"))));
        System.out.println("size=" + listSize(new Box<>(42)));
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Output:

```text
known:JAVA
missing
string:hello
integer:42
other:3.5
not-box
other:null
nested:inner
nested-unmatched
msg:OK
no-box
no-envelope
size=2
size=-1
```

Explanation of key parts:

1. `known(new Box<>("Java"))` receives `Box<String>` as its static type; `Box(var text)` infers `text` as `String`, returning `known:JAVA`. `known(null)` does not match the record pattern, returning `missing`.
2. `inspect` receives `Object`. The pattern `Box(String text)` detects the `"hello"` component; `Box(Integer number)` detects `42`; `3.5` goes to the general branch; `"plain"` is not a `Box`.
3. `new Box<String>(null)` is passed to `inspect(Object)`. In the `Object` context, `Box(String text)` does not match a null component; `Box(var other)` can accept null, so it prints `other:null`.
4. `Box(Box(var text))` only matches when both the outer record and the inner record component exist. `new Box<Box<String>>(null)` produces `nested-unmatched`.
5. `describeEnvelope` produces `msg:OK` when fully nested; uses `default` when the `Box` component is null; uses `case null` for a null selector.
6. `listSize` accepts a `List<?>` component and reads its size; for `42`, the `List<?>` pattern does not match, so it returns `-1`.

The type patterns `String`, `Integer`, and `List<?>` in `inspect` and `listSize` check the **runtime component**; they do not certify the original type argument of the record.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Understanding / Fix |
| --- | --- | --- |
| Assuming `Box<String>` retains `String` like a type token at runtime | Writing generic checks that the JVM cannot verify | Distinguish type erasure from component checks; use `Box<?>` or component patterns |
| Writing `obj instanceof Box<String>(var x)` when `obj` is `Object` | Compile error because an unchecked conversion is required | Use `Box(String x)` to check the component value or design the API to accept `Box<String>` |
| Using a raw type and casting to `Box<String>` without checking | Risk of `ClassCastException` when using data of the wrong type | Avoid raw types; handle with wildcards and component checks |
| Thinking `Box(var x)` always makes `x` a `String` | Cannot call `String`-specific methods if context does not prove the type | Check the static type of the input expression; use `Box(String x)` if needed |
| Assuming `List<?>` also proves `List<String>` | Risk of wrong element casts or method calls | Iterate and check elements or use a data source with a type contract |
| Thinking a generic record containing `null` cannot match | Missing `null` component cases or causing `NullPointerException` | Distinguish a null outer record from a null component; check components before use |
| Placing a general `Box` branch before specific patterns | Specific branches may become unreachable | Put specific patterns first, general ones later; follow `switch` dominance rules |
| Treating `Box<String>` as if it were `Box<Object>` | Java generics are *invariant* | Use `Box<?>` when you only need to read without knowing `T` |
| Copying record patterns into a Java 17 compiler | Fails to compile because record patterns are not an official feature in JDK 17 | Use JDK 21+; check the JDK used by your IDE, Gradle/Maven, and `javac` |

## 10. Exercises and Self-Check Criteria

1. Declare `record Pair<L, R>(L left, R right) {}` and a method accepting `Pair<String, Integer>`. Use `Pair(var label, var count)` to return `label + ":" + count`; explain which two types the compiler infers.
2. With `Object data = new Box<>(42);`, try `data instanceof Box(Integer n)` and `data instanceof Box(String s)`; explain which condition matches and what this says about the **component**, not the type argument.
3. Try compiling `data instanceof Box<String>(var s)` when `data` has type `Object`. Note the unchecked conversion error and replace it with an appropriate component check.
4. Create a `Box<Box<String>>` with two real levels and a case where the inner `Box` component is `null`. Use `Box(Box(var text))` to distinguish them; avoid assuming every component is non-null.
5. Write a `switch` for `Envelope<String>` with `case null`, a nested record pattern, and `default`. Explicitly handle both a null record and a null component.
6. Test `Box<List<String>>` and `Box<List<Integer>>` in a method accepting `Object`; use `Box(List<?> list)` to read `size()`, then explain why that is not enough to conclude each element is a `String`.
7. Create `Box<String> known = new Box<>(null);` and test `known instanceof Box(String text)`. Compare with `Object opaque = known; opaque instanceof Box(String text)` to explain when a nested type pattern is null-matching based on static context.

**Lesson passed when:** you can read generic record patterns with `var`, explicit type arguments, and nesting; accurately state the difference between compile-time inference and runtime checks; identify non-reifiable types, unchecked conversions, and `null`; and handle edge cases with a runnable Java 21 program.

**References:**

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [Java Language Specification 21, §18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5).
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
