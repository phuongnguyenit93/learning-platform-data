# Do Type Patterns Apply to Primitive Types? — Java 21

**Java 21 Answer:** **You cannot use a type pattern directly to check a primitive value with `instanceof`, nor use a primitive type pattern as a top-level `case` label in a `switch`.** For example, `int n = 7; n instanceof int x` and `case int x -> ...` are invalid in Java 21. Common type patterns like `obj instanceof Integer number` operate on **objects** of the reference type `Integer`, not on the primitive `int`.

There is one detail that is easy to miss: **Java 21 record patterns can contain type patterns for primitive components**, such as `Point(int x, int y)` for `record Point(int x, int y)`. This is *deconstructing primitive components from a matched record object*, not checking a primitive directly with `instanceof`. Distinguishing these three situations helps avoid conclusions like “pattern matching can never be used with `int`.”

## 1. How Do Primitive and Reference Types Differ?

Java has eight primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. A primitive value holds data directly as a language-level value; it **is not an instance of a class** and cannot hold `null`.

The corresponding wrappers are `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`. They are **reference types**, so they can be stored in variables of type `Object`, `Number` (for numeric wrappers), or the interfaces that the wrapper implements.

| Primitive | Wrapper | Type pattern on an `Object` variable in Java 21 |
| --- | --- | --- |
| `boolean` | `Boolean` | `obj instanceof Boolean b` |
| `byte` | `Byte` | `obj instanceof Byte b` |
| `short` | `Short` | `obj instanceof Short s` |
| `char` | `Character` | `obj instanceof Character c` |
| `int` | `Integer` | `obj instanceof Integer i` |
| `long` | `Long` | `obj instanceof Long l` |
| `float` | `Float` | `obj instanceof Float f` |
| `double` | `Double` | `obj instanceof Double d` |

The examples in the last column assume `obj` is an expression of type `Object`. **The type pattern here checks the wrapper**, not turning a primitive into an object type of its own.

## 2. Why Doesn't `instanceof` Check Primitives Directly?

In Java 21, the `instanceof` operator checks the runtime type of a reference value. A standard direct type pattern declares a variable of a reference type:

```java
static void inspect(Object value) {
    if (value instanceof Integer number) {
        System.out.println(number + 1);
    }
}
```

Here, `number` has **type `Integer`**, and is only in scope where the `instanceof` match is proven to succeed.

The examples below **do not compile with JDK 21**:

```java
int n = 7;

// Invalid: the left operand is a primitive and the type pattern here is a primitive.
// if (n instanceof int x) { System.out.println(x); }

// Invalid: a primitive on the left cannot use instanceof with a wrapper.
// if (n instanceof Integer x) { System.out.println(x); }

Object value = Integer.valueOf(7);

// Invalid in Java 21: top-level primitive type pattern.
// if (value instanceof int x) { System.out.println(x); }
```

These lines illustrate compile-time errors, not a standalone runnable Java file. The valid approach is to keep the primitive for direct computation, or use a wrapper when you need to check the dynamic type of a reference.

**Why isn't a type pattern needed for `int n` in many cases?** When a variable is already declared as `int n`, the compiler knows its exact type is `int`. There is no object with a dynamic subtype to check. If you need to inspect its **value**, use conditions like `n > 0`, `n == 0`, or a `switch` over constants.

## 3. Autoboxing Makes Examples Work, Without Changing the Limitation

**Autoboxing** converts a primitive value into a wrapper object in contexts allowed by Java, such as assigning an `int` to an `Object`:

```java
int original = 42;
Object boxed = original; // autoboxing: int -> Integer

if (boxed instanceof Integer number) {
    System.out.println(number + 1);
}
```

This prints `43`. What happens step by step:

1. `original` is a primitive `int`.
2. When assigned to `Object`, Java boxes the value into an `Integer` object.
3. `instanceof Integer number` checks this `Integer` object and creates the pattern variable `number`.
4. The expression `number + 1` uses **unboxing** to extract the `int` from the wrapper during computation.

That **does not mean** `instanceof` accepted a primitive. Boxing happened in the assignment context, **before** the pattern check; the operand of `instanceof` is the `boxed` reference.

Similarly, the following snippet is valid:

```java
Number number = Integer.valueOf(42);

if (number instanceof Integer integer) {
    System.out.println(integer.intValue());
}
```

`Number` is a broader reference type, and `Integer` is a subtype of `Number`; the type pattern checks the runtime subtype and then lets you work with the specific wrapper.

**Note on variables already typed as `Integer`:** if you declare `Integer integer = 42;` and try `integer instanceof Integer i`, the type pattern is an unnecessary check because the expression's type is already a subtype of the pattern type; in Java 21, the compiler may report an error for a type pattern that is always statically true. If you need to check for non-`null`, writing `integer != null` is clearer.

## 4. Numeric Appearance Does Not Imply the Matching Wrapper

Autoboxing preserves the original primitive type. It does not automatically turn every number into an `Integer` just because the displayed value looks the same:

```java
Object first = 7;   // Integer
Object second = 7L; // Long
Object third = 7.0; // Double

System.out.println(first instanceof Integer);  // true
System.out.println(second instanceof Integer); // false
System.out.println(third instanceof Double);   // true
```

`7`, `7L`, and `7.0` all represent the numeric value "seven" in human terms, but they have **different types** and after boxing become **different classes**.

If you want to handle multiple numeric wrappers in the same branch, you can use:

```java
static String formatNumber(Object value) {
    if (value instanceof Number number) {
        return "number=" + number;
    }
    return "not a number";
}
```

`Number` includes numeric wrappers like `Integer`, `Long`, `Double`, as well as some other numeric classes. It **does not include `Boolean` or `Character`**. Calling `number.intValue()` or `number.doubleValue()` may **convert or lose precision**; checking `Number` does not guarantee that the desired numeric conversion is safe for every business rule.

## 5. `switch` with Primitives in Java 21: Constant Labels, Not Primitive Type Patterns

Java 21's classic `switch` and `switch` expressions support several primitive types as selectors, such as `int`, `byte`, `short`, and `char`; when the selector is a primitive, you can use appropriate **case constants**:

```java
static String classify(int value) {
    return switch (value) {
        case -1 -> "negative one";
        case 0 -> "zero";
        case 1 -> "one";
        default -> "another integer";
    };
}
```

This branches on **constant values**, not a pattern introducing a new variable. In Java 21, do not write:

```java
// DOES NOT COMPILE as a switch(int) branch in Java 21:
// case int n -> "number: " + n;
```

At the same time, Java 21 `switch` **does not yet accept `long`, `float`, `double`, or `boolean` directly as a primitive selector**. To classify those types, use `if/else` or an appropriate data model.

A `switch` with a **reference selector** can match wrappers:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case Integer i when i > 0 -> "positive int wrapper: " + i;
        case Integer i -> "int wrapper: " + i;
        case Long l -> "long wrapper: " + l;
        default -> "other";
    };
}
```

Here, `case Integer i` and `case Long l` are **type patterns for reference types**. `when` checks a condition on the value after the pattern has matched. The `case null` branch explicitly handles a null selector; `default` does not automatically cover `null` in a pattern switch.

This snippet is an illustrative method and must be placed inside a class to compile.

## 6. Important Exception: Primitive Components in Java 21 Record Patterns

The claim that “Java 21 does not support primitives in any type pattern” is **false**. Java 21 standardized **record patterns** (JEP 440). For a record with primitive components, developers can use primitive type patterns **inside a record pattern** to extract data:

```java
record Point(int x, int y) {}

static String readPoint(Object source) {
    if (source instanceof Point(int x, int y)) {
        return "x=" + x + ", y=" + y;
    }
    return "not a point";
}
```

How to read this accurately:

- `source` has type `Object`, and `Point` is a **reference type** (a record class).
- `source instanceof Point(...)` checks whether the object matches the `Point` record.
- The `x` and `y` components of `Point` have type `int`, so `int x` and `int y` are valid **component type patterns** within this record pattern.
- `x` and `y` are pattern variables holding the extracted primitive values. There is no `instanceof` running directly on a standalone `int` variable.

The shorter syntax using `var` is also valid; the compiler infers `x` and `y` as `int`:

```java
if (source instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

The snippet above illustrates code inside a method with an `Object source` parameter and the `Point` declaration shown earlier.

### Do Not Arbitrarily Convert Primitives When Matching Record Components

If a record declares `int x`, in Java 21 you should use the corresponding component pattern `int x` or `var x`. Do not assume that a pattern like `long x`, `double x`, or another numeric check will automatically perform implicit primitive conversion like regular assignment.

For example, replacing `Point(int x, int y)` with `Point(long x, long y)` to “match any `int` and automatically widen it” **is not a component pattern syntax supported by Java 21 in that way**. Use `int`/`var` to extract the components and then cast in a normal Java expression if needed:

```java
if (source instanceof Point(int x, int y)) {
    long sum = (long) x + y;
    System.out.println(sum);
}
```

Casting `x` to `long` before addition also avoids intermediate overflow when the sum of two `int` values exceeds the `int` range.

## 7. Distinguishing Three Easily Confused Syntaxes

| Java 21 Code | Valid? | What Is Actually Checked |
| --- | --- | --- |
| `Object obj = 7; obj instanceof Integer i` | Yes | The `Integer` object after boxing |
| `int n = 7; n instanceof Integer i` | No | A primitive cannot be used directly as the operand of `instanceof` |
| `Object obj = 7; obj instanceof int i` | No | Top-level primitive type pattern in `instanceof` |
| `switch (n) { case 7 -> ... }` | Yes | Compares a primitive value against a constant |
| `switch (n) { case int i -> ... }` | No | Primitive type pattern in a `case` label |
| `switch (obj) { case Integer i -> ... }` | Yes, if branches are exhaustive | Pattern for the `Integer` wrapper |
| `obj instanceof Point(int x, int y)` | Yes, when `Point` is a record with `int x, int y` | Matches a record, then extracts primitive components |
| `obj instanceof Point(var x, var y)` | Yes, with an appropriate record | Matches a record; compiler infers component types |

The `switch` forms in the table are **illustrative syntax snippets**, and `...` is not runnable code. For a `switch` expression, you need branches covering all possible values and a valid result expression in each branch. Pattern variables also follow *flow scoping*: they can only be used where the compiler is certain the pattern has matched.

## 8. `null`, Unboxing, and Type Safety

Primitives do not have a `null` value, whereas wrappers can be `null`. This leads to two important rules.

**The pattern `instanceof Integer i` does not match `null`:**

```java
Object value = null;
System.out.println(value instanceof Integer); // false
```

**Unboxing a `null` wrapper throws `NullPointerException`:**

```java
Integer maybeNull = null;
// int n = maybeNull; // compiles, but throws NullPointerException at runtime
```

Do not mistake an `Integer` match for a guarantee that all wrappers can be safely unboxed everywhere. Only when the match itself succeeds along the current execution path is that pattern variable guaranteed to be a non-`null` object.

A safe pattern:

```java
static int incrementOrZero(Object value) {
    if (value instanceof Integer i) {
        return i + 1; // i is a non-null Integer here
    }
    return 0;
}
```

The addition `i + 1` uses unboxing, but the `if` branch already guarantees that `i` is not `null`. However, `int` addition can still overflow at `Integer.MAX_VALUE`; if you need overflow detection, use `Math.addExact(i, 1)`.

## 9. Generic Containers Do Not Turn Elements into Primitive Patterns Either

Java generics only accept **reference types** as type arguments. You cannot declare `List<int>`; you must use `List<Integer>`. However, due to *type erasure*, the type pattern `instanceof List<Integer> list` is not a way to check whether an `Object` contains only `Integer` elements.

The appropriate approach is to check the container using a type that can be checked at runtime, and then check each element against the wrapper:

```java
static int sumIntegers(Object input) {
    if (!(input instanceof java.util.List<?> list)) {
        return 0;
    }

    int sum = 0;
    for (Object element : list) {
        if (element instanceof Integer number) {
            sum += number; // unboxing during addition
        }
    }
    return sum;
}
```

This is an illustrative method; it intentionally **skips non-`Integer` elements**. If the business requirement is “every element must be an integer,” you need to validate all elements and report an error instead of silently skipping them. Also watch out for overflow when summing; type patterns do not check arithmetic conditions.

## 10. Complete Program Running on JDK 21

Create the file **`PrimitivePatternDemo.java`**:

```java
public class PrimitivePatternDemo {
    record Reading(int amount, String unit) {}

    static String examine(Object value) {
        return switch (value) {
            case null -> "null";
            case Integer number when number > 0 -> "positive wrapper:" + number;
            case Integer number -> "wrapper:" + number;
            case Reading(int amount, String unit) ->
                    "record:" + amount + " " + unit;
            default -> "other";
        };
    }

    static String byConstant(int code) {
        return switch (code) {
            case 0 -> "zero";
            case 1 -> "one";
            default -> "different";
        };
    }

    public static void main(String[] args) {
        int primitive = 7;
        Object boxed = primitive; // int -> Integer

        if (boxed instanceof Integer number) {
            System.out.println("instanceof:" + (number + 1));
        }

        System.out.println(examine(boxed));
        System.out.println(examine(-3));
        System.out.println(examine(new Reading(12, "items")));
        System.out.println(byConstant(1));
        System.out.println(examine(null));
    }
}
```

Compile/run with **JDK 21**:

```bash
javac --release 21 PrimitivePatternDemo.java
java PrimitivePatternDemo
```

Expected stdout:

```text
instanceof:8
positive wrapper:7
wrapper:-3
record:12 items
one
null
```

Line-by-line explanation:

1. `boxed` holds an `Integer` object created by boxing `primitive`; the pattern `Integer number` matches and the addition produces `8`.
2. `examine(boxed)` matches `case Integer number when number > 0`, printing `positive wrapper:7`.
3. `examine(-3)` receives an `Integer` via boxing when passing the argument to the `Object` parameter; the `> 0` guard is false, so the next `Integer` branch returns `wrapper:-3`.
4. `new Reading(12, "items")` is a record object. The record pattern successfully extracts the primitive component `int amount` and the reference component `String unit`, printing `record:12 items`.
5. `byConstant(1)` is a `switch` over primitive constants, returning `one`, with no type pattern.
6. `examine(null)` is handled explicitly by `case null`.

This example simultaneously distinguishes **primitives used directly**, **wrappers checked with type patterns**, and **primitive components extracted via record patterns**. The `--release 21` flag checks Java 21 syntax and APIs without requiring `--enable-preview`.

## 11. When to Choose Which Approach?

- **The variable is already a primitive `int`/`double`/...:** use arithmetic operators, comparisons, `if`, and constant `switch` with primitive selectors supported by Java 21. No pattern is needed just to “confirm the type.”
- **A variable of type `Object` or a supertype that may hold a wrapper:** use `instanceof Integer i`, `instanceof Double d`, or a pattern `switch` on the reference to distinguish runtime types.
- **Wanting to handle multiple numeric wrappers:** `instanceof Number n` is useful, but choose the appropriate conversion and data-loss/overflow policy.
- **Wanting to extract primitive components from a record:** use a record pattern `Point(int x, int y)` or `Point(var x, var y)` matching the record's component types.
- **Needing value-range validation:** combine `when` in a pattern `switch`, an `&&` condition after `instanceof`, or separate validation. Pattern matching does not turn “right type” into “valid data.”
- **Needing `null` support:** distinguish primitives from nullable wrappers; in a reference `switch`, consider `case null`; when unboxing, avoid `null` wrappers.

### Further Reading

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441

**Conclusion:** In Java 21, direct `instanceof` type patterns and top-level `case` labels work on **reference types**; for standalone primitive values, use standard conditional constructs. Primitives still play a role in pattern matching through **component type patterns inside record patterns**. Correctly identifying the *location* of the pattern and the *actual type* of the selector will help you choose valid syntax and explain behavior accurately.
