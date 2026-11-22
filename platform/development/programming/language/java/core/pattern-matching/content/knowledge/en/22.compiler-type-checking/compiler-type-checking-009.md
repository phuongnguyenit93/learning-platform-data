# Errors Due to Incompatible Record Component Patterns in Java 21+

## 1. The Problem: What Does the Compiler Check When Deconstructing a Record?

A **record pattern** lets you check whether an object matches a record class and deconstruct the data of each *record component* in an `instanceof` expression or a `switch` `case` label. For example:

~~~java
record Point(int x, int y) {}

Object value = new Point(2, 3);
if (value instanceof Point(int a, int b)) {
    System.out.println(a + b); // 5
}
~~~

`Point(int a, int b)` has three parts involved in type checking:

1. **`Point`** is the record class chosen as the type of the record pattern.
2. **Two component positions** correspond in order to `x` and `y` of `record Point(int x, int y)`.
3. **`int a` and `int b`** are two component patterns, binding pattern variables if the entire match succeeds.

In Java 21, the compiler does not accept arbitrary sequences of expressions placed inside `Point(...)`. It checks the number of components, the compatibility of each pattern's type with the declared type of the corresponding component, and generic rules. If a component pattern cannot be validly applied to the corresponding component, **the program does not compile**.

The key point is distinguishing two situations:

- **Type-incompatible at compile time:** the compiler proves the pattern is invalid, so it reports an error before running.
- **Valid pattern that does not match data at runtime:** the compiler allows it, but the actual value of the component does not satisfy a specific component pattern; the `instanceof` expression returns `false` or `switch` looks for another case.

Record patterns were standardized in **Java 21 (JEP 440)**, without needing `--enable-preview`. Java 17 supports type patterns in `instanceof` but **does not** yet have standard record patterns like the examples below.

## 2. Compatibility Principles: Position and Declared Type

Consider two records:

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
~~~

Record components have a name, a type, and a **fixed order**. When writing `Point(int a, int b)`, the compiler pairs the first pattern with component `x` of type `int`, and the second pattern with `y` of type `int`. The names `a` and `b` are new variable names, not component names; they can differ from `x` and `y`.

**For a record pattern to be valid:**

- The outer type must be a **record class type**, and the type of the checked value must allow applying that record pattern according to type conversion rules.
- The list of component patterns must have the **exact same number of positions** as the number of components declared in the record.
- Each component pattern must be applicable to the **static type of the component** at the corresponding position. The pattern type does not always have to be identical to the declared type; a narrower reference type check can be valid if Java allows checking it at runtime.
- For generic records, type arguments and patterns inferred from context must satisfy *checked cast* rules; type erasure still applies.
- A nested pattern must be compatible with the **type of the parent component**, not just compatible with the overall input type.

Typically, the compiler can determine these errors from the record declaration and the pattern without **needing to know the actual runtime objects** of the program.

## 3. Component Pattern Count Mismatch Error

This is the most obvious structural error. Record `Point` has **two** components, so two component patterns must be used:

~~~java
record Point(int x, int y) {}

Object input = new Point(1, 2);

// DOES NOT COMPILE: Point has 2 components, but the pattern only has 1.
// if (input instanceof Point(int x)) {
//     System.out.println(x);
// }

// VALID:
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 3
}
~~~

Typical compiler error: `incorrect number of nested patterns`, along with the list of component types the compiler expects.

Adding a third pattern is also an error:

~~~java
// DOES NOT COMPILE:
// if (input instanceof Point(int x, int y, int z)) { ... }
~~~

If you only want to use `x`, you still have to provide a pattern for `y`, for example `Point(int x, var ignored)`. In stable Java 21, you should use a named variable like `ignored` for unused positions. Do not omit positions from the list.

## 4. Incompatible Component Pattern Type Error

The compiler knows the static type of each component. If a component has primitive type `int` but the pattern requires a `String` reference, the pattern cannot be applied:

~~~java
record Point(int x, int y) {}

// DOES NOT COMPILE:
// Object input = new Point(2, 3);
// if (input instanceof Point(String x, int y)) { ... }
~~~

With the Java compiler, the error looks like:

~~~text
incompatible types: int cannot be converted to java.lang.String
~~~

The reason is not that the value `2` "does not look like a string", but that **the declared type of the first component is already `int`**. The pattern `String x` has no valid conversion to check such a primitive component.

How to fix it:

~~~java
Object input = new Point(2, 3);

if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}

// Or let the compiler infer from the record component:
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y); // 5
}
~~~

With `Point(var x, var y)`, the compiler infers both pattern variables as `int`. `var` in a component pattern **does not mean dynamic typing**; it still gives the compiler a definite static type based on the record declaration.

To avoid confusion, do not assume that every Java type convertible by assignment or casting elsewhere can be used as-is inside a type pattern. The applicability rules for type patterns on primitives/references are specific to the Java version being compiled.

## 5. Nested Pattern Incompatible with Parent Component Type

Consider:

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
record NamedPoint(String name, Point point) {}
~~~

The following pattern is **invalid**:

~~~java
// DOES NOT COMPILE:
// Object value = new Person("An", "Hà Nội");
// if (value instanceof Person(String name, Point(var x, var y))) { ... }
~~~

The compiler knows that the `city` component of `Person` has type `String`. However, the pattern at the second position is the record pattern `Point(...)`: it requires a value compatible with the record type `Point`. `String` and `Point` have no permitted conversion in this case.

Typical message:

~~~text
incompatible types: java.lang.String cannot be converted to Point
~~~

Depending on the declaration location and the compiler, the class name in the message may be fully qualified or prefixed with an enclosing class.

Fix it according to the **actual record structure**:

~~~java
// Person has String city:
Object p = new Person("An", "Hà Nội");

if (p instanceof Person(var name, var city)) {
    System.out.println(name + ": " + city); // An: Hà Nội
}

// NamedPoint has a point component of type Point:
Object n = new NamedPoint("A", new Point(4, 7));

if (n instanceof NamedPoint(var name, Point(var x, var y))) {
    System.out.println(name + ": " + x + ", " + y); // A: 4, 7
}
~~~

When debugging multi-level nested patterns, go **from the outside in** and check the component type at each level before placing another record pattern at that position. Naming a variable `point` or `city` does not change the component's type: **the record declaration** is what decides.

## 6. Narrower Reference Types Can Be Valid: Compiles, But Does Not Match at Runtime

**Not every pattern type that differs from the declared type is an error.** For example:

~~~java
record Amount(Number number) {}

static String classify(Object value) {
    if (value instanceof Amount(Integer n)) {
        return "Integer: " + (n + 1);
    }
    if (value instanceof Amount(Double n)) {
        return "Double: " + n;
    }
    return "Không khớp số";
}
~~~

The `number` component is declared as `Number`. `Integer` and `Double` are both subtypes suitable for a reference type check at runtime. Therefore, the compiler **accepts** `Amount(Integer n)` and `Amount(Double n)`.

Output:

~~~java
System.out.println(classify(new Amount(12)));   // Integer: 13
System.out.println(classify(new Amount(1.5)));  // Double: 1.5
System.out.println(classify(new Amount(3L)));   // Không khớp số
~~~

`new Amount(3L)` is valid because `Long` is a `Number`, but it does not match `Integer` or `Double`. This is a **runtime mismatch**, completely different from the compile-time error in section 4.

Comparison table:

| Component declared type | Component pattern | Compiles? | Result |
| --- | --- | --- | --- |
| `int` | `int x` | Yes | Binds `int` value |
| `int` | `var x` | Yes | `x` is inferred as `int` |
| `int` | `String x` | **No** | Reference type incompatible with `int` |
| `Number` | `Integer n` | Yes | Matches at runtime only when component is actually `Integer` |
| `Number` | `Double n` | Yes | Matches at runtime only when component is actually `Double` |
| `Number` | `var n` | Yes | `n` is inferred from declared type `Number` |
| `String` | `Point(var x, var y)` | **No** | Nested record pattern cannot be applied to `String` |

**Practical rule:** when a reference component has a broad supertype, a subtype pattern can act as a **runtime filter**. When the pattern type cannot be applied to the component at all under language rules, the compiler rejects it before running.

## 7. Generic Record Patterns: Errors Due to Uncheckable Types After Erasure

A record can carry type parameters:

~~~java
record Box<T>(T value) {}
~~~

If the static type of the input is already `Box<String>`, the compiler has enough information to infer the component type:

~~~java
static String typed(Box<String> box) {
    if (box instanceof Box(var text)) {
        return text == null ? "null" : text.toUpperCase();
    }
    return "Không khớp";
}
~~~

`text` has static type `String`. You can write `Box<String>(var text)` in this appropriate context; this is a contract checked based on the **static type**, not because the JVM stores generic type arguments inside each instance.

Conversely, the following **does not compile**:

~~~java
// DOES NOT COMPILE:
// static void invalid(Object input) {
//     if (input instanceof Box<String>(var text)) {
//         System.out.println(text);
//     }
// }
~~~

The compiler cannot use a runtime check to prove that an `Object` is a `Box<String>` rather than a `Box<Integer>`: the generic argument `String` is subject to **type erasure**. The error is typically of the form `Object cannot be safely cast to Box<String>`.

Even with `Box<String>`, requesting a different type argument is still an error:

~~~java
// DOES NOT COMPILE:
// static void invalidTyped(Box<String> box) {
//     if (box instanceof Box<Integer>(var number)) { ... }
// }
~~~

The compiler knows `Box<String>` cannot be treated as `Box<Integer>` due to the *invariance* rule of generic type arguments.

The way to handle an unknown input is to use a **wildcard** and then check the component value when needed:

~~~java
static String inspect(Object input) {
    if (input instanceof Box<?>(var payload)) {
        if (payload instanceof String text) {
            return "String: " + text.toUpperCase();
        }
        return "Giá trị khác";
    }
    return "Không phải Box";
}
~~~

`Box<?>` can be safely matched from `Object` without promising that `T` is `String`. The check `payload instanceof String text` tests **the actual component value** at runtime, rather than verifying an erased generic argument.

You can also use `input instanceof Box(var payload)` when the compiler can safely infer the pattern type; if the input is only `Object`, do **not** assume `payload` is `String`.

## 8. `null`: Distinguishing Incompatible Pattern Types from Non-Matching Values

`null` is easy to misunderstand because of two different levels of checking.

**A. The entire record value is null.**

~~~java
Object input = null;
if (input instanceof Point(var x, var y)) {
    // Does not execute: record pattern does not match null.
}
~~~

This is a **runtime false** result, not a compile error.

**B. A nested record component is null.**

~~~java
Object value = new NamedPoint("B", null);

if (value instanceof NamedPoint(var name, Point(var x, var y))) {
    // Does not execute: nested record pattern Point(...) does not match null.
}
~~~

The nested pattern `Point(...)` is valid for the `point` component of type `Point`, but the **runtime value** of the component is null.

**C. A reference component is null, but the component pattern is unconditional.**

~~~java
record Contact(String email) {}

Contact contact = new Contact(null);
if (contact instanceof Contact(String email)) {
    System.out.println(email == null); // true
}
~~~

In record patterns, an **unconditional type pattern** applied to a component can bind `null`. In this example, the `email` component is already declared as `String`, so the type pattern `String email` matches unconditionally; it receives the `null` value. `var email` can also receive null.

Do not conflate the component pattern rule inside a record pattern with a standalone `null instanceof String` check (which is always `false`).

**D. A narrower reference pattern does not match null.**

~~~java
record Amount(Number number) {}
Object value = new Amount(null);

if (value instanceof Amount(Integer n)) {
    // Does not execute: Integer is a narrower check than Number; null does not match.
}
~~~

`Amount(Integer n)` still **compiles validly**. Null data simply causes this component pattern not to match at runtime. If you need to accept null, use `Amount(var number)` and check `number == null` explicitly.

## 9. Workflow for Reading Compiler Errors and Fixing Patterns

When encountering an error in `instanceof RecordType(...)` or `case RecordType(...)`, check in the following order:

1. **Inspect the record declaration**: identify the type name and the actual component list. For example, `record Point(int x, int y)` has exactly two positions.
2. **Count the patterns**: if the number of arguments in parentheses differs from the number of components, fix the position count first. Even unused components must have a corresponding pattern.
3. **Compare each position with its declared type**: for `Point`, position 1 is `int`, position 2 is `int`. Do not rely on variable names in the pattern to infer types.
4. **Check nested patterns**: if you see `SomeRecord(...)` in the second position, the second component of the outer record must have a type compatible with `SomeRecord`.
5. **Check generic source types**: if the expression has type `Object` or a raw type, avoid writing a specific unverifiable type argument. Use a wildcard and check the component when needed.
6. **Distinguish compile errors from runtime no-match**: `Number -> Integer` can be a valid runtime check; `int -> String` is wrong-typed from the start.
7. **Consider null and flow scoping**: with nested record patterns, null can cause a branch not to match; pattern variables can only be used where the compiler guarantees a match.

Do not "fix" type mismatch errors by using unsafe casts or converting everything to raw generics. If the actual data structure differs from the declaration the pattern expects, update the pattern to match the **correct data contract**.

## 10. Complete, Runnable Java 21+ Example

Save as **`RecordPatternCompatibilityDemo.java`**:

~~~java
public class RecordPatternCompatibilityDemo {
    record Point(int x, int y) {}
    record NamedPoint(String name, Point point) {}
    record Amount(Number number) {}
    record Box<T>(T value) {}

    static String point(Object input) {
        if (input instanceof Point(int x, int y)) {
            return "Tổng: " + (x + y);
        }
        return "Không phải Point";
    }

    static String nested(Object input) {
        if (input instanceof NamedPoint(var name, Point(var x, var y))) {
            return name + ": " + x + ", " + y;
        }
        return "Nested không khớp";
    }

    static String amount(Object input) {
        if (input instanceof Amount(Integer n)) {
            return "Integer: " + (n + 1);
        }
        if (input instanceof Amount(Double n)) {
            return "Double: " + n;
        }
        return "Không khớp số";
    }

    static String unknownBox(Object input) {
        if (input instanceof Box<?>(var payload)) {
            if (payload instanceof String s) {
                return "String: " + s.toUpperCase();
            }
            return "Khác: " +
                (payload == null ? "null" : payload.getClass().getSimpleName());
        }
        return "Không phải Box";
    }

    static String typedBox(Box<String> box) {
        if (box instanceof Box(var text)) {
            return "Dài: " + (text == null ? "null" : text.length());
        }
        return "Không khớp";
    }

    public static void main(String[] args) {
        System.out.println(point(new Point(2, 3)));
        System.out.println(nested(new NamedPoint("A", new Point(4, 7))));
        System.out.println(nested(new NamedPoint("B", null)));
        System.out.println(amount(new Amount(12)));
        System.out.println(amount(new Amount(1.5)));
        System.out.println(amount(new Amount(3L)));
        System.out.println(unknownBox(new Box<>("java")));
        System.out.println(unknownBox(new Box<>(42)));
        System.out.println(unknownBox(new Box<>(null)));
        System.out.println(typedBox(new Box<>("hello")));
        System.out.println(typedBox(new Box<>(null)));
        System.out.println(point(null));
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac --release 21 RecordPatternCompatibilityDemo.java
java RecordPatternCompatibilityDemo
~~~

Output:

~~~text
Tổng: 5
A: 4, 7
Nested không khớp
Integer: 13
Double: 1.5
Không khớp số
String: JAVA
Khác: Integer
Khác: null
Dài: 5
Dài: null
Không phải Point
~~~

What the program demonstrates:

- `Point(int x, int y)` and `NamedPoint(var name, Point(var x, var y))` are valid in component count, order, and types.
- `NamedPoint("B", null)` can still be instantiated, but the **nested Point pattern** does not match when the component is null.
- `Amount(Integer n)` and `Amount(Double n)` are two valid runtime checks for the `Number` component; `Long` matches neither pattern.
- `Box<?>(var payload)` checks the record class without requiring a specific generic argument; `payload instanceof String s` is what checks the actual String.
- For `Box<String>`, `Box(var text)` infers `text` as `String`; a null reference component is handled explicitly.
- A `null` selector itself does not match `Point(...)`.

## 11. Five Compile-Time Errors to Identify Yourself

The following examples **intentionally do not compile**. Read them separately as diagnostic cases; do not put them into the file from section 10.

~~~java
record Point(int x, int y) {}
record Person(String name, String city) {}
record Box<T>(T value) {}

class InvalidPatterns {
    static void wrongArity(Object v) {
        // ERROR 1: Point requires 2 component patterns.
        if (v instanceof Point(int x)) {}
    }

    static void wrongComponentType(Object v) {
        // ERROR 2: component x has type int, cannot be a String pattern.
        if (v instanceof Point(String x, int y)) {}
    }

    static void wrongNestedType(Object v) {
        // ERROR 3: city is String, cannot apply Point record pattern.
        if (v instanceof Person(String name, Point(var x, var y))) {}
    }

    static void wrongGenericFromObject(Object v) {
        // ERROR 4: Object -> Box<String> requires an unchecked conversion.
        if (v instanceof Box<String>(var text)) {}
    }

    static void wrongGenericArgument(Box<String> v) {
        // ERROR 5: Box<String> cannot be converted to Box<Integer>.
        if (v instanceof Box<Integer>(var number)) {}
    }
}
~~~

Classification table:

| Snippet | Error | How to fix |
| --- | --- | --- |
| `Point(int x)` | Wrong number of component patterns | `Point(int x, var ignored)` |
| `Point(String x, int y)` | `int` incompatible with `String` | `Point(int x, int y)` or `Point(var x, var y)` |
| `Person(String name, Point(...))` | Component `city` is `String`, not `Point` | `Person(var name, var city)`; or use a record that actually has a `Point` component |
| `Object -> Box<String>(var s)` | Type erasure, requires unchecked cast | `Box<?>(var value)`, then check `value instanceof String s` |
| `Box<String> -> Box<Integer>(var n)` | Conflicting generic arguments | Use `Box(var text)` and the correct input type |

All of these errors can be caught by the **compiler**. Do not try to fix them by adding `if (value != null)`: a null check cannot make an incompatible component type valid.

## 12. Exercises with Guided Answers

**Exercise 1 — Wrong arity.** Given `record RGB(int red, int green, int blue) {}`, why does `RGB(int r, int g)` fail? If you only need `red`, how should you fix it?

**Exercise 2 — Wrong static type.** Given `record Task(String name, int priority) {}`, fix the pattern `Task(String name, String priority)` to print `name + " / " + priority`.

**Exercise 3 — Valid pattern but no match.** Given `record Amount(Number number) {}`, does `Amount(Integer n)` compile? Does `new Amount(3.5)` match? Distinguish the two answers.

**Exercise 4 — Nested record and null.** Given `record Holder(Point point) {}`, why does `Holder(Point(var x, var y))` compile yet fail to match `new Holder(null)`?

**Exercise 5 — Generics.** Why can't `Object obj` use `obj instanceof Box<String>(var text)`? Rewrite a safe check to extract the string when the component is `String`.

**Hints:**

~~~java
// 1: RGB has 3 components, always requires 3 positions.
if (obj instanceof RGB(int r, var ignoredG, var ignoredB)) {
    System.out.println(r);
}

// 2: priority is int.
if (obj instanceof Task(String name, int priority)) {
    System.out.println(name + " / " + priority);
}

// 5: keep the generic type as a wildcard and check the component value.
if (obj instanceof Box<?>(var value)
        && value instanceof String text) {
    System.out.println(text);
}
~~~

Exercise 3: the pattern `Amount(Integer n)` **compiles** because `Integer` is a valid subtype of `Number`; `new Amount(3.5)` holds a `Double`, so it does not match at runtime. Exercise 4: the `Point` component type is valid for a nested record pattern; a null value is not accepted by a record pattern.

## 13. References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns, nested patterns, types of component patterns, type inference (Java 21).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): syntax and examples.
- [JLS Java 21 — `14.30 Patterns](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type patterns, record patterns, applicability rules, and constraints.
- [JLS Java 21 — `4.6 Type Erasure](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-4.html#jls-4.6): runtime limitations with generic arguments.
