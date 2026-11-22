# Null Records and Nested Components in Record Patterns (Java 21)

## Objectives

After this lesson, you will be able to distinguish `null` in the **outer record object**, in a **component containing a nested record**, and in the **value of a leaf component**; accurately predict when a record pattern matches; and handle these cases using `instanceof`, `switch`, and `when` without accidentally dereferencing `null`.

**Version:** Record Patterns (JEP 440) and Pattern Matching for `switch` (JEP 441) are standard features as of **Java 21**, requiring no `--enable-preview`.

## 1. Three Positions That Can Hold null

Consider two records:

```java
record Address(String city) {}
record Person(String name, Address address) {}
```

Three cases need to be separated:

1. **The root/outer record is `null`:** a variable `Person p = null;`, where there is no `Person` object to deconstruct yet.
2. **A nested record component is `null`:** `new Person("An", null)`; `Person` exists, but `address()` returns `null`.
3. **A component inside the nested record is `null`:** `new Person("An", new Address(null))`; both `Person` and `Address` exist, while `city()` returns `null`.

A `record` is a data type containing components with explicitly declared types; **records do not automatically enforce non-null** on reference-type components. The immutability of a record also does not imply that all components are non-null.

## 2. Pattern Matching Rules in Java 21

A record pattern has the form `Person(String name, Address(String city))`. Java first checks whether the input object is a **non-`null`** `Person`. If so, Java invokes the corresponding accessors and matches each component against the pattern at the same position. Nested record patterns continue doing the same.

There are two easily confused rules:

- **A record pattern itself never matches `null`.** Therefore, `null instanceof Person(...)` is `false`; and `Address(String city)` does not match when `address` is `null`.
- **A direct type pattern for a component can match `null`.** In Java 21, it is *null-matching* when that pattern is *unconditional* for the component's declared type. For example, for the component `String name`, the patterns `String name` or `var name` both accept `null` and bind `null` to the variable. The same applies to `Address address` or `var address` for the component `Address address`.

This differs from a top-level type pattern: `obj instanceof String s` is always `false` if `obj == null`. The *null-matching* mechanism described above applies to **direct type patterns in the component list of a record pattern**, and does not automatically make a nested record pattern null-matching.

### When the Declared Type Differs from the Pattern Type

```java
record Box(Object value) {}

// Suppose obj is new Box(null):
obj instanceof Box(Object data)  // true, data == null
obj instanceof Box(var data)     // true, data == null
obj instanceof Box(String text)  // false
```

`Object data` and `var data` cover all values of a component declared as `Object`, including `null`. `String text` only matches a subset of `Object` values, so it does **not** match `null`. Only if the actual value is a non-`null` `String` does `Box(String text)` match.

## 3. Table of Key Cases

With `Person`, `Address`, and `Box` declared above:

| Value under test | Pattern | Result | Explanation |
|---|---|---|---|
| `null` | `Person(String n, Address a)` | No match | The outer record is `null` |
| `new Person("An", null)` | `Person(String n, Address a)` | Match; `a == null` | `Address a` is a direct type pattern, unconditional for `Address` |
| `new Person("An", null)` | `Person(String n, Address(String c))` | No match | Nested record pattern `Address(...)` does not accept `null` |
| `new Person(null, new Address(null))` | `Person(String n, Address(String c))` | Match; `n == null` and `c == null` | Both records exist; both direct `String` type patterns match `null` |
| `new Box(null)` | `Box(Object x)` | Match; `x == null` | `Object x` is unconditional for `Object` |
| `new Box(null)` | `Box(String s)` | No match | `String s` is not unconditional for `Object` |

With nested patterns, **a non-matching branch does not mean a `NullPointerException`**. `instanceof` returns `false`, while `switch` continues checking the remaining matching `case` labels. An exception can occur when your own code dereferences a variable that is `null`, or when an accessor throws an error; these two situations are distinct from pattern `null`-matching behavior.

## 4. Standalone Runnable Java 21 Example

Create the file **`NullRecordAndNestedDemo.java`**:

```java
public class NullRecordAndNestedDemo {
    record Address(String city) {}
    record Person(String name, Address address) {}
    record Box(Object value) {}

    static String nested(Object value) {
        if (value instanceof Person(String name, Address(String city))) {
            return "MATCH name=" + name + ", city=" + city;
        }
        return "NO MATCH";
    }

    static String status(Object value) {
        return switch (value) {
            case null -> "ROOT NULL";

            // Address must be non-null; city can still be null.
            case Person(String name, Address(String city)) ->
                    "NESTED city=" + city;

            // Separately catch a null nested record component.
            case Person(String name, Address address)
                    when address == null -> "ADDRESS NULL";

            default -> "OTHER TYPE";
        };
    }

    static boolean narrow(Object value) {
        return value instanceof Box(String text);
    }

    static boolean broad(Object value) {
        return value instanceof Box(Object data);
    }

    public static void main(String[] args) {
        System.out.println(nested(null));
        System.out.println(nested(new Person("An", null)));
        System.out.println(nested(new Person(null, new Address(null))));
        System.out.println(status(null));
        System.out.println(status(new Person("An", null)));
        System.out.println(status(new Person("An", new Address(null))));
        System.out.println(narrow(new Box(null)));
        System.out.println(broad(new Box(null)));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 NullRecordAndNestedDemo.java
java NullRecordAndNestedDemo
```

Expected output:

```text
NO MATCH
NO MATCH
MATCH name=null, city=null
ROOT NULL
ADDRESS NULL
NESTED city=null
false
true
```

Explanation of notable lines:

- Line 1: `nested(null)` fails because the root does not match the record pattern.
- Line 2: `Person` exists, but the `address` component is `null`, so `Address(String city)` fails.
- Line 3: `Address` exists even though `city` is `null`; both inner `String` patterns receive `null`.
- Line 4: `switch` encounters a `null` selector, so it enters `case null`.
- Line 5: the branch with the guard `address == null` handles the missing nested record.
- Line 6: `city` being `null` still enters the nested record branch.
- The last two lines distinguish an unconditional `Object` type pattern from a narrowing `String` type pattern on a component declared as `Object`.

## 5. Writing Safe Logic with instanceof

When you only care about a complete structure, nested patterns help rule out `null` at the **record nodes**:

```java
static boolean hasAddressRecord(Object value) {
    return value instanceof Person(var name, Address(var city));
}
```

The method above returns `false` if `value` is `null` or `address` is `null`. However, it returns `true` if `city` is `null`. To require `city` to have content, an additional check is needed:

```java
static boolean hasUsableCity(Object value) {
    return value instanceof Person(var name, Address(String city))
            && city != null
            && !city.isBlank();
}
```

The `&&` operator evaluates from left to right and short-circuits. Therefore, `city` is only used after the pattern matches and the `city != null` check succeeds. The variable `city` is also only in scope where the compiler knows the pattern has matched.

If you want to read `address` even when it is `null`, use the direct pattern `Person(var name, var address)` and handle null explicitly:

```java
static String cityOrUnknown(Object value) {
    if (value instanceof Person(var name, var address)) {
        return address == null || address.city() == null
                ? "Unknown"
                : address.city();
    }
    return "Not a Person";
}
```

These are illustrative methods that can be placed in the class containing the `Person` and `Address` records declared in Section 1. You do not need to call the nested record's accessor before knowing that component is non-`null`.

## 6. switch: Branching by Data Depth

In a `switch` using record patterns, place the **more specific** branch first and the more general branch afterward. For example:

```java
static String route(Object input) {
    return switch (input) {
        case null -> "Không có Person";
        case Person(var name, Address(var city))
                when city != null && !city.isBlank() ->
                "Địa chỉ: " + city;
        case Person(var name, Address(var city)) ->
                "Có Address nhưng city trống hoặc null";
        case Person(var name, var address)
                when address == null ->
                "Chưa có Address";
        default -> "Không phải Person";
    };
}
```

Distinguish three points:

1. `case null` only handles the **selector** `input == null`. If the selector is `null` without a `null`-handling label, this kind of `switch` throws `NullPointerException`; `default` alone does not catch `null`.
2. `case Person(..., Address(...))` requires the nested `Address` to be non-`null`. The `when` guard then checks `city` after the pattern has matched.
3. `case Person(var name, var address) when address == null` preserves the `null` reference for business logic instead of trying to deconstruct it.

**Note on dominance:** if you place `case Person(String name, Address address)` (without a guard) **before** `case Person(String name, Address(String city))`, the nested branch afterward is dominated by the general branch, resulting in a compilation error. Similarly, placing an unguarded `case` before a guarded `case` with the same pattern makes the later branch unreachable.

You cannot write `case Person(var name, null)` or `case Person(var name, Address(null))` in Java 21: the component list of a record pattern contains **patterns**, not a `null` literal as a component pattern. Bind the component with `var` or a specific type, then check `== null` in `when` or in the branch body.

## 7. Should null Be Allowed in the First Place?

Pattern matching helps **read** missing data, but it does not decide whether the domain accepts missing data. If `address` is required to exist, enforce that in the compact constructor:

```java
import java.util.Objects;

record SafePerson(String name, Address address) {
    SafePerson {
        Objects.requireNonNull(address, "address");
    }
}
```

This example uses the `Address` record already declared. It prevents creating `SafePerson` with `address == null`, but does **not** guarantee that `name` or `address.city()` is non-`null`. To guarantee those as well, you must validate the corresponding components too (or clearly specify nullability in the API contract).

When receiving JSON, database records, responses from external services, or legacy objects, do not assume every nested record is present just because its declared type is a record.

## 8. Common Mistakes and How to Fix Them

- **Mistaking `String s` as always excluding null.** With `record Person(String name, ...)`, `Person(String s, ...)` accepts `name == null` because this type pattern is unconditional for `String`. Check `s != null` if your logic requires it.
- **Mistaking `Address(String city)` as matching `address == null`.** This is a **record pattern**, so it does not match. Use `Address address` or `var address` if you want to keep a potentially null reference.
- **Mistaking `case null` as catching all null nested components.** It only catches the selector. Null at a component must be handled with a guard or a check inside the branch.
- **Calling `city.isBlank()` when `city == null`.** A pattern match does not mean leaf components are non-null. Check before dereferencing.
- **Placing a broad branch before a narrow branch in `switch`.** The compiler may report a dominated case. Move the more specific nested/guarded branch earlier.
- **Copying Java preview syntax into stable Java 21.** Record patterns and `switch` patterns do not need preview flags as of Java 21; however, the unnamed pattern `_` in Java 21 is still a preview feature. The examples here intentionally use named variables.
- **Assuming pattern matching can never throw an exception.** A nested component failing to match `null` normally just causes the match to fail. However, a customized accessor that throws an exception during deconstruction causes pattern matching to throw a `MatchException` wrapping the cause according to the Java 21 specification. Exceptions from a guard or branch body still follow the behavior of that expression itself.

## 9. Self-Check Questions

Given:

```java
record Child(String code) {}
record Parent(Child child) {}
Object a = new Parent(null);
Object b = new Parent(new Child(null));
```

1. What is `a instanceof Parent(Child(String code))`? **`false`**, because `Child(...)` does not match a `null` component.
2. What is `a instanceof Parent(Child child)`? **`true`**, with `child == null`, because the declared component type is `Child` and the direct type pattern `Child child` is unconditional.
3. What is `b instanceof Parent(Child(String code))`? **`true`**, with `code == null`, because both records are non-`null` and `String code` is null-matching on a component declared as `String`.
4. How do you write a condition that only accepts a code with at least one non-whitespace character? **`b instanceof Parent(Child(String code)) && code != null && !code.isBlank()`**.
5. If `Parent` must never be missing `child`, where should that be prevented? **In the compact constructor or an input validation step**, rather than relying solely on patterns at read time.

## Key Takeaways

**A record pattern checks the existence and structure of each record object; a direct type pattern checks the component value against its declared type.** Therefore, `Person(..., Address(...))` requires `Person` and `Address` to be non-`null`, while leaf components such as `String name` or `String city` can still be `null`. With `switch`, handle the selector with `case null`, handle a missing nested record with a guard, and always check before calling methods on a potentially `null` variable.

## Official References

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21, §14.30: Kinds of Patterns and Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
