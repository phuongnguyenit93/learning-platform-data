# A record pattern is not a regular accessor call

## 1. Understanding the true nature

In Java 21 and later, a **record pattern** allows you to both test the type of a value and *deconstruct* the record's components, binding them to variables. For example:

```java
record Point(int x, int y) {}

Object candidate = new Point(2, 3);
if (candidate instanceof Point(var x, var y)) {
    System.out.println(x + y); // 5
}
```

`Point(var x, var y)` is **a pattern**, not a `Point` creation expression, a `Point(...)` method call, or two explicitly written accessor calls. It expresses the condition "this value is a `Point` and its components match these subpatterns."

There is one very important detail: **a record pattern actually uses the record's accessors**. To obtain the values of the two components, the matching mechanism invokes the corresponding accessors such as `Point.x()` and `Point.y()`; it should not be understood as directly accessing `private final` fields, nor does it bypass developer-defined accessors. The difference lies in **the semantics of the entire matching operation**: type checking, deconstruction, nested matching, success/failure conditions, variable scoping, and exception handling.

Record patterns were standardized in **Java 21** (JEP 440); in Java 19/20 they were a preview feature. All complete examples below use Java 21, without requiring `--enable-preview`.

## 2. How `instanceof` record patterns work

Consider the expression:

```java
value instanceof Point(var x, var y)
```

Semantically, Java performs the following steps:

1. Checks whether the tested value is non-`null` and can be tested/converted to the record type `Point`. If not, the result of `instanceof` is `false`.
2. When the record type matches, retrieves the component values through the record's **corresponding accessors**, rather than invoking a new constructor.
3. Matches each component against its subpattern. `var x` and `var y` infer their types from the component declarations; nested patterns may perform further type checks and deeper deconstruction.
4. **Only when the entire pattern succeeds** are the pattern variables bound and usable in the branch where Java determines that matching succeeded.

That is why writing `value instanceof Point(var x, var y)` is not completely equivalent to manual code:

```java
Point p = (Point) value;
int x = p.x();
int y = p.y();
```

The manual snippet assumes it is safe to cast and call methods; if the type does not match, it can throw `ClassCastException`, and if `p == null`, calling `p.x()` will throw `NullPointerException`. An `instanceof` record pattern on a `null` value or a wrong type simply returns `false`. In addition, patterns have their own rules for matching subpatterns and variable scoping.

| Aspect | Direct accessor call: `p.x()` | Record pattern: `value instanceof Point(var x, var y)` |
| --- | --- | --- |
| Purpose | Get the result of a method | Check a pattern and deconstruct data |
| Input type checking | The caller must already have a suitable reference/cast | Performs record type checking during matching |
| Encountering `null` on the outer object | Calling a method on `null` causes `NullPointerException` | `instanceof` returns `false` |
| Component value | Result of the invoked accessor | Component values are also retrieved via accessors |
| Nested patterns | Checks must be written manually | Java can match recursively |
| Result variables | Variables declared by the programmer | Pattern variables are only in valid scope when the match succeeds |
| Accessor throws an exception | The exception from the direct call propagates out | When an accessor is called during matching and throws an exception, Java throws `MatchException` with the original exception as `cause` |

**Note on names:** given `record Point(int x, int y)`, `Point(var first, var second)` is still valid and binds according to **the declared component order** (`x` then `y`). `first`/`second` are new variable names, not the names of the accessor methods that Java looks up.

## 3. Runnable example: distinguishing type checking from accessor calls

Save the following code in `RecordPatternBasics.java`:

```java
public class RecordPatternBasics {
    record Point(int x, int y) {}

    static void print(Object value) {
        if (value instanceof Point(var x, var y)) {
            System.out.printf("point=(%d, %d), sum=%d%n", x, y, x + y);
        } else {
            System.out.println("not a Point");
        }
    }

    public static void main(String[] args) {
        print(new Point(2, 3));
        print("other");
        print(null);
    }
}
```

Compile and run with JDK 21 or later:

```text
javac --release 21 RecordPatternBasics.java
java RecordPatternBasics
```

Expected output:

```text
point=(2, 3), sum=5
not a Point
not a Point
```

`Point(var x, var y)` matches the first value, then binds `x = 2`, `y = 3`. The string `"other"` is not a `Point` and `null` does not match a record pattern, so both take the `else` branch. No calls to `x()` or `y()` need to appear explicitly in the source code to obtain the two values.

## 4. Redefined accessors are still invoked

Normally, a record automatically generates accessors with the same names as its components (`code()` rather than `getCode()`). However, a record can declare an explicit accessor, as long as it conforms to a valid signature. The pattern will observe **the value returned by that accessor**, even when it differs from reading the backing field directly.

Save to `AccessorIsInvoked.java`:

```java
import java.util.Locale;

public class AccessorIsInvoked {
    record Ticket(String code) {
        public String code() {
            System.out.println("Ticket.code() invoked");
            return code.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Object value = new Ticket(" ab-12 ");

        if (value instanceof Ticket(var extracted)) {
            System.out.println("Pattern: " + extracted);
        }

        Ticket ticket = (Ticket) value;
        System.out.println("Direct: " + ticket.code());
    }
}
```

```text
javac --release 21 AccessorIsInvoked.java
java AccessorIsInvoked
```

Output:

```text
Ticket.code() invoked
Pattern: AB-12
Ticket.code() invoked
Direct: AB-12
```

The first `Ticket.code() invoked` line appears while **the record pattern deconstructs `Ticket`**; the second line comes from the direct `ticket.code()` call. Therefore, the statement "a record pattern only reads fields and does not call accessors" is **false**. The statement "a record pattern is just syntactic sugar for a regular accessor call" is also **inaccurate** because it omits the checking and matching parts of the pattern.

With accessors that have side effects, matching can produce logs, update state, or throw errors. In record design, you should keep accessors simple, stable, and free of side effects; do not write programs that depend on how many times or in what order a complex pattern invokes each accessor.

## 5. `null` for the outer record differs from `null` in a component

**`null` never matches a record pattern**. However, a record component can certainly hold `null`. When a subpattern is a *null-matching* type pattern such as `var` applied directly to a matching component, it can bind a `null` value. A **nested record pattern**, on the other hand, still does not match `null`.

Save to `NestedNulls.java`:

```java
public class NestedNulls {
    record City(String name) {}
    record Route(City destination) {}

    public static void main(String[] args) {
        Object first = new Route(new City("Hue"));
        Object second = new Route(null);
        Object third = null;

        System.out.println("first nested: "
                + (first instanceof Route(City(var name))));
        System.out.println("second nested: "
                + (second instanceof Route(City(var name))));
        System.out.println("second direct: "
                + (second instanceof Route(var destination)));
        System.out.println("third outer: "
                + (third instanceof Route(var destination)));

        if (first instanceof Route(City(var city))) {
            System.out.println("City: " + city);
        }
    }
}
```

```text
javac --release 21 NestedNulls.java
java NestedNulls
```

Output:

```text
first nested: true
second nested: false
second direct: true
third outer: false
City: Hue
```

Analysis:

- `Route(City(var name))` requires both `Route` and the `destination` component to match the record pattern `City(...)`. Because `second.destination()` returns `null`, the `City(...)` part fails.
- `Route(var destination)` only binds the direct component; here `destination` can receive `null`, because the type pattern inferred from `City` is null-matching at this component position.
- `third` is `null`, so `Route(...)` itself does not match.
- After the successful `if` branch, the variable `city` has type `String` and can only be used in the permitted scope. You cannot use `city` outside as if it were always initialized.

Therefore, a record pattern should not be described as a chain of accessor calls combined with automatic "null-safe navigation". **Whether `null` matches depends on the kind of pattern at each position.**

## 6. Exceptions from accessors: an important behavioral difference

An accessor can throw an *unchecked exception*. When called directly, that exception propagates out of the method call. When an accessor is invoked implicitly by Java during record pattern matching, the Java 21 specification requires throwing `java.lang.MatchException`, with the original exception preserved in `getCause()`.

Save to `AccessorExceptions.java`:

```java
public class AccessorExceptions {
    record Broken(String value) {
        public String value() {
            throw new IllegalStateException("cannot read value");
        }
    }

    public static void main(String[] args) {
        Broken broken = new Broken("data");

        try {
            broken.value();
        } catch (IllegalStateException ex) {
            System.out.println("Direct: "
                    + ex.getClass().getSimpleName());
        }

        try {
            Object input = broken;
            if (input instanceof Broken(var value)) {
                System.out.println(value);
            }
        } catch (MatchException ex) {
            System.out.println("Pattern cause: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

```text
javac --release 21 AccessorExceptions.java
java AccessorExceptions
```

Output:

```text
Direct: IllegalStateException
Pattern cause: IllegalStateException
```

**Distinguish three situations:**

- The outer value has the wrong type or is `null` in an `instanceof` record pattern expression: matching fails and returns `false`.
- A subpattern does not match: the overall record pattern may return `false`; this does not mean an accessor error occurred.
- An accessor throws an exception while Java is retrieving a component: matching completes abruptly with `MatchException`; this is **not** a `false` result, and the cause can be inspected via `getCause()`.

This is an important behavioral difference when handling errors, logging, or migrating from manual deconstruction code to pattern matching.

## 7. Record patterns in `switch` are also matching

Record patterns are not limited to `instanceof`. Java 21 allows using them in `switch` with the same idea of type checking and deconstruction. The snippet below **illustrates this inside a class that has already declared** `record Point(int x, int y)`:

```java
static String describe(Object candidate) {
    return switch (candidate) {
        case null -> "null";
        case Point(var x, var y) -> "Point(" + x + ", " + y + ")";
        default -> "other";
    };
}
```

`case Point(...)` is not a constructor call or a handwritten accessor call; it is a pattern case. `case null` handles a `null` selector explicitly. Do not infer that a record pattern automatically absorbs `null` for the entire `switch` expression: without an appropriate `null`-handling case, `switch` can throw `NullPointerException`.

When you need additional business conditions, you can place a condition after matching, such as `if (candidate instanceof Point(var x, var y) && x > 0)`. The condition `x > 0` is only evaluated when the pattern has matched and the variable `x` has a valid value.

## 8. Common misconceptions

1. **"Patterns access `private final` fields directly."** False. Component values are retrieved through the corresponding accessors; an explicit accessor can alter the returned value or throw an exception.
2. **"If a regular class has `x()` and `y()` methods, it can also use the `Point(x, y)` pattern."** False. Record pattern syntax applies to record types; having methods named like accessors does not turn a regular class into a record.
3. **"The variable names in the pattern determine the accessors."** False. The order and number of components follow the record declaration: `record Point(int x, int y)` requires a pattern with exactly two positions, such as `Point(var left, var top)`.
4. **"Once a pattern succeeds, the variables always exist in every branch."** False. Pattern variables are only in scope where Java proves that matching succeeded (flow scoping).
5. **"Any `null` inside a record causes matching to fail."** False. A `null` at the position of a nested record pattern does not match; `var` or a null-matching type pattern on a direct component can bind `null`.
6. **"If an accessor fails, `instanceof` returns `false`."** False. Java 21 throws `MatchException` with the original cause when an accessor throws an error during matching.
7. **"Record patterns have been stable since Java 17."** False. Record patterns became a standard feature in **Java 21**; JDK 21 and later compile these examples without enabling preview.

## 9. When to use patterns, and when to call accessors?

Use a **record pattern** when the goal is to branch on data shape/type, extract multiple components at once, or deconstruct nested data in `instanceof` or `switch`. Use **direct accessors** when you already have an object of the right type and only want to read a specific component clearly.

In both cases, pay attention to the accessors—whether auto-generated by the record or declared by the developer. When a data structure may contain `null`, decide clearly whether you need to bind `null` or require a nested pattern to match. When an accessor can throw an error, check the difference between a direct-call exception and a pattern's `MatchException`.

**Remember:** *a record pattern calls accessors to obtain components, but the record pattern itself is a check-and-deconstruct operation with its own rules for types, `null`, variable scoping, and exceptions.*

## Official references

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification 21 — §14.30.2 Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java SE 21 API — `MatchException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
