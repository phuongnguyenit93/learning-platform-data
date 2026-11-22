# Exhaustiveness in Pattern Switch Statements (Java 21)

**Exhaustiveness** means that the compiler can prove a `switch` **covers every value of the selector type that the language requires to be handled**. In Java 21, an **enhanced switch statement** — including a `switch statement` that uses `case` patterns — **must be exhaustive**. Unlike a traditional `switch statement`, you cannot simply write a few pattern branches and leave other types unhandled without a covering branch.

For example, when the selector is `Object`, this code **does not compile**:

```java
// INTENTIONALLY INCORRECT example in Java 21:
static void incomplete(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        case Integer number -> System.out.println(number);
        // Missing a branch covering other Object types.
    }
}
```

`Object` can hold a `Double`, a `Boolean`, an arbitrary class, and many other types. `String` and `Integer` do not cover all cases; the compiler will report that the switch is not exhaustive.

The usual fix:

```java
static void complete(Object value) {
    switch (value) {
        case String text -> System.out.println("text:" + text);
        case Integer number -> System.out.println("integer:" + number);
        default -> System.out.println("other");
    }
}
```

Now every **non-null value** has a matching branch. However, there is an important detail: **compile-time exhaustiveness does not mean `null` is automatically handled safely**. With the method above, passing `null` throws a `NullPointerException`; to handle it explicitly, you need an appropriate `case null` or `case null, default`.

This article walks through compile-time rules, the role of `default`, `sealed`, `enum`, and `when`, runtime behavior, and a complete Java 21 example.

## 1. How do traditional switch statements and enhanced switch statements differ?

Java had `switch statement`s before pattern matching. A traditional switch statement can be **non-exhaustive**:

```java
static void traditional(int value) {
    switch (value) {
        case 1 -> System.out.println("one");
        case 2 -> System.out.println("two");
        // Valid even without default.
    }
}
```

If `value == 3`, no label matches and this `switch statement` completes normally without printing anything. This behavior is allowed for traditional switch statements.

Conversely, a `switch statement` that uses patterns is an **enhanced switch statement**:

```java
static void enhanced(Object value) {
    switch (value) {
        case String s -> System.out.println(s.length());
        default -> System.out.println("not String");
    }
}
```

It must be exhaustive: `case String s` only covers part of the type domain; `default` covers the remaining values according to label-selection rules.

| Criterion | Traditional switch statement | Enhanced switch statement with patterns |
| --- | --- | --- |
| `case` labels | Constants of traditional selector types | Can contain patterns, guards, `null`, and matching constants |
| Does the compiler require exhaustiveness? | **No** | **Yes** |
| No label matches | Can complete normally | Cannot leave a compile-time provable gap; binary change scenarios can cause a runtime error |
| Can `default` be used? | Yes | Yes, and it is the easiest way to cover the remainder |
| Can it be exhaustive without `default`? | Exhaustiveness not required; can still list every constant | Yes, for example when covering all branches of a `sealed` type |

The term *enhanced* is broader than having patterns: Java 21 also treats certain switch forms with `case null` or selectors of broad reference types as enhanced. For this article, the focus is that **any switch statement with a pattern label must be exhaustive**.

Do not confuse this with `switch expression`: **every switch expression must be exhaustive**, whether it uses patterns or only constant labels. The key distinction to learn here is the new exhaustiveness rule applied to **enhanced switch statements**.

## 2. Exhaustiveness is a compile-time type analysis

The compiler does not run test objects to check a switch. It reasons based on:

1. **The static type of the selector**, such as `Object`, `Shape`, or `Color`.
2. **The set of labels**: constants, type patterns, record patterns, `default`, `case null`.
3. **Subtype relationships and type restrictions**, especially `sealed` types with a declared set of permitted direct subtypes.
4. **`when` guards** and whether a branch actually covers every value of that type.
5. **Dominance** and other label validity rules, such as not placing a narrower branch shadowed by an earlier broader branch.

From a type-checking perspective, the question to answer is: "Can there be a selector value in the domain under consideration for which **no label** is selected?" If so, an enhanced switch statement without a covering branch is rejected.

For example, `case Number n` covers `Number` objects, but it does not cover a `String`, `Boolean`, or ordinary object if the selector has static type `Object`. Therefore, it is not enough to replace `default`:

```java
// DOES NOT COMPILE: Object selector has many types other than Number.
static void invalid(Object value) {
    switch (value) {
        case Number n -> System.out.println(n);
    }
}
```

This is an intentionally incorrect illustration; do not copy it into the final runnable program.

## 3. `default`: a straightforward choice when the selector has a broad domain

With `Object`, the most common way to ensure exhaustiveness is to add `default`:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "string";
        case Number n -> "number";
        default -> "other";
    };
}
```

The code above is an illustrative **switch expression**; if converted to a `switch statement` with the same three labels and executable statements, the compiler also recognizes it as exhaustive. `default` handles objects that are neither `String` nor `Number`.

However:

- `default` **does not catch `null` by default** in Java 21 pattern switches.
- A type pattern only matches when the selector is a non-null value compatible with the pattern type.
- If `value == null` and there is no branch handling `null`, the `switch` throws `NullPointerException`.

If you want to classify `null` as well, you can write it explicitly:

```java
static void classifyNullable(Object value) {
    switch (value) {
        case null -> System.out.println("missing");
        case String s -> System.out.println("string:" + s);
        case Number n -> System.out.println("number:" + n);
        default -> System.out.println("other");
    }
}
```

Or if `null` and all remaining types share the **same behavior**, use Java 21's special label:

```java
static void classifyNullableTogether(Object value) {
    switch (value) {
        case String s -> System.out.println("string:" + s);
        case Number n -> System.out.println("number:" + n);
        case null, default -> System.out.println("misc");
    }
}
```

`case null, default` is a special combined syntax; do not generalize this to mean "you can combine any different patterns with commas" in Java 21.

## 4. Sealed types: exhaustive without default

A **sealed class/interface** restricts which types are allowed to directly extend or implement it. The compiler can use the `permits` list to determine whether the case patterns fully cover all possible types.

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}

record Rectangle(double width, double height) implements Shape {}
```

These three declarations are an illustrative example; they can be placed inside the same Java class. `Circle` and `Rectangle` are records, which makes them `final` classes that can directly implement this sealed interface.

An exhaustive enhanced switch statement:

```java
static void showArea(Shape shape) {
    switch (shape) {
        case Circle c ->
                System.out.println(Math.PI * c.radius() * c.radius());
        case Rectangle r ->
                System.out.println(r.width() * r.height());
    }
}
```

**No `default` is needed** because every non-null `Shape` object is either a `Circle` or a `Rectangle`, according to the sealed hierarchy model at compile time.

### Missing a branch causes an error

```java
// DOES NOT COMPILE because Rectangle is missing:
static void incompleteShape(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println(c.radius());
    }
}
```

This is a major advantage of pattern switches on a sealed hierarchy: if you add a permitted subtype and recompile the code containing the switch, the compiler can require you to update the missing branches.

### Adding default can suppress a useful warning

```java
static void showAreaWithDefault(Shape shape) {
    switch (shape) {
        case Circle c -> System.out.println("circle");
        case Rectangle r -> System.out.println("rectangle");
        default -> System.out.println("unrecognized");
    }
}
```

This syntax is still valid. However, if `Triangle` is later added to the sealed hierarchy, `default` already provides a fallback branch, so the compiler will not necessarily force you to add `case Triangle t`. Therefore, for a **closed** set of subtypes where business requirements demand handling each type individually, **omitting `default` is the choice that lets the compiler verify completeness**.

An important condition: the type domain must genuinely be closed enough for the compiler to prove it. If the selector is `Object` or a regular interface with arbitrarily many implementations, you cannot just list a few subtypes and expect exhaustiveness.

## 5. Exhaustiveness on a sealed type still does not handle null automatically

The `showArea(Shape shape)` example above is exhaustive over valid subtypes, yet `showArea(null)` will throw `NullPointerException`.

To handle all inputs, including a nullable reference:

```java
static void showAreaOrMissing(Shape shape) {
    switch (shape) {
        case null -> System.out.println("missing shape");
        case Circle c -> System.out.println("circle:" + c.radius());
        case Rectangle r -> System.out.println("rectangle:" + r.width());
    }
}
```

This snippet is still exhaustive without `default`. `case null` handles `null` first, while the two patterns ensure coverage of all permitted implementations.

Distinguish two goals:

- **Compile-time exhaustiveness**: is the set of labels sufficient according to Java's type rules?
- **Runtime null-safety**: can the selector be `null`, and if so, what should the program do?

A switch can satisfy the first goal while still throwing an exception for `null`. This is **not** a bug in the compiler's exhaustiveness check; it is how label selection works on a null value.

## 6. A `when` guard does not cover an entire type by itself

A guard makes a pattern **selected only when an additional condition is true**. Consequently, a guarded branch generally cannot stand in for a branch that covers every instance of that type.

```java
// DOES NOT COMPILE: Circles with non-positive radius and Rectangles are not handled.
static void badGuard(Shape shape) {
    switch (shape) {
        case Circle c when c.radius() > 0 ->
                System.out.println("positive circle");
        case Rectangle r ->
                System.out.println("rectangle");
    }
}
```

The compiler cannot conclude that every `Circle` will satisfy `c.radius() > 0`. For example, `Circle(0)` is still a `Circle` but does not match that branch. Without a fallback branch, the switch is not exhaustive.

Fix this by placing an unguarded `Circle` branch **after** the guarded branch:

```java
static void handleGuarded(Shape shape) {
    switch (shape) {
        case Circle c when c.radius() > 0 ->
                System.out.println("positive circle");
        case Circle c ->
                System.out.println("other circle");
        case Rectangle r ->
                System.out.println("rectangle");
    }
}
```

The two `Circle` branches are distinct: the first is for positive radii, and the second catches all remaining `Circle` instances; together with `Rectangle`, the hierarchy is covered.

**Label order also matters.** If you place the unguarded `case Circle c` **before** `case Circle c when ...`, the guarded branch behind it is **dominated** because the earlier `case Circle c` already catches every `Circle`; Java reports a compile-time error.

Similarly, with `Object`, having only `case String s when !s.isBlank()` and `case Integer i` is not enough; beyond blank strings, there are many other object types.

## 7. Enums and exhaustiveness in switch statements

A traditional `switch statement` on an enum is **not required** to handle every enum constant:

```java
enum State { NEW, RUNNING, FINISHED }

static void legacy(State state) {
    switch (state) {
        case NEW -> System.out.println("new");
        // RUNNING and FINISHED are not handled; traditional statement is still valid.
    }
}
```

However, a `switch expression` on an enum must be exhaustive:

```java
static String label(State state) {
    return switch (state) {
        case NEW -> "new";
        case RUNNING -> "running";
        case FINISHED -> "done";
    };
}
```

When considering an **enhanced switch statement**, you can also use an enum with a type pattern or a `null` label, and exhaustiveness must be ensured. For example:

```java
static void enhancedEnum(State state) {
    switch (state) {
        case null -> System.out.println("null");
        case NEW -> System.out.println("new");
        case RUNNING -> System.out.println("running");
        case FINISHED -> System.out.println("done");
    }
}
```

Because it has `case null`, this statement is enhanced; the remaining enum constants are all listed. Conversely, writing only `case null` and `case NEW` would fail to cover `RUNNING` and `FINISHED`.

Note: listing all enum constants can be enough for the compiler to prove exhaustiveness, but if the enum type changes between compile time and runtime, you still have to consider binary mismatch possibilities just like with other closed type domains.

## 8. A sufficiently broad type pattern can also be exhaustive

Not every enhanced switch statement has to have `default`. If an **unguarded type pattern** covers the entire non-null selector domain, the compiler can also prove exhaustiveness:

```java
static void inspect(CharSequence value) {
    switch (value) {
        case CharSequence sequence ->
                System.out.println(sequence.length());
    }
}
```

With a `CharSequence` selector, every non-null value is a `CharSequence`, so that pattern alone covers the type domain. A `null` value still throws `NullPointerException` if there is no `case null`.

An overly broad pattern can cause later branches to be dominated:

```java
// DOES NOT COMPILE: String is a CharSequence, so case String is shadowed.
static void dominated(CharSequence value) {
    switch (value) {
        case CharSequence c -> System.out.println("any chars");
        case String s -> System.out.println("text");
    }
}
```

If the goal is to prioritize `String` and then handle every remaining `CharSequence`, place `case String s` **before** `case CharSequence c`.

The ability to use a supertype is a very useful tool when you do not need to handle each subtype individually. But if you want the compiler to enforce checking each subtype in a sealed hierarchy, an overly broad supertype branch can forfeit that benefit just like `default`.

## 9. Record patterns and coverage checking

Java 21 also supports record patterns, allowing you to both test the record type and deconstruct its components:

```java
record Point(int x, int y) {}

static void show(Object value) {
    switch (value) {
        case Point(int x, int y) ->
                System.out.println(x + "," + y);
        default ->
                System.out.println("not Point");
    }
}
```

This is an illustrative method in the same class as `record Point`. The `Point(int x, int y)` branch can match any `Point` object compatible with the primitive `int` components, but `Object` still has countless other types, so `default` is still needed for the switch on `Object` to be exhaustive.

With nested record patterns, the compiler must consider **both the record type and whether its components match**. A narrow pattern on a component can miss valid values, especially when the component has a broad reference type. Do not assume that "having a record case covers the whole record" if the pattern further constrains subtypes or data structures.

The reliable approach is to evaluate all component variants, or use a pattern that covers the record type when you want to handle the record uniformly. Do not use `default` mindlessly just to silence errors; decide whether unhandled cases need to be caught explicitly at compile time.

## 10. Exhaustiveness is also required when using colon groups

The rule is not limited to `case ... ->` syntax. With **colon groups**, a switch statement containing patterns must still be exhaustive:

```java
static void classifyWithColon(Object input) {
    switch (input) {
        case null:
            System.out.println("missing");
            break;
        case String s:
            System.out.println("text:" + s);
            break;
        default:
            System.out.println("other");
    }
}
```

`default` makes the statement exhaustive for the remaining non-null values, while `case null` handles a null reference.

There are two separate issues to check:

1. **Exhaustiveness**: do the labels cover all required values?
2. **Fall-through and definite matching**: can one group fall through into a subsequent group that declares an unmatched pattern variable?

`break` in a colon group prevents fall-through, but it **does not create a new case** to cover a missing type. Conversely, adding `default` can make a switch exhaustive, but it does not fix an invalid fall-through path on its own. Therefore, the two sets of rules must be checked separately.

In a `switch expression` using colon groups, paths that produce a result must `yield` or `throw`; `break` does not replace `yield`. This is a separate concern from label exhaustiveness.

## 11. Type exhaustiveness differs from business-logic completeness

A switch can be **syntactically valid and exhaustive** yet still fail to handle all business scenarios adequately:

```java
static void process(Object value) {
    switch (value) {
        case String s -> System.out.println("string");
        default -> System.out.println("other");
    }
}
```

The compiler accepts this thanks to `default`, yet this example:

- does not distinguish between an empty string and a non-empty string;
- does not distinguish between `Integer`, `Double`, and `Boolean`;
- throws `NullPointerException` if given `null`.

Thus, "exhaustive" only describes **label selection according to Java's rules**; it does not prove that the code performs all necessary validation, authorization, or computation. If an API accepts nullable data or sealed subtypes with distinct meanings, express those as explicit branches and test them.

## 12. Runtime behavior when a hierarchy changes

A switch on a sealed type can be judged exhaustive by the compiler based on the set of subtypes at compile time. In systems compiled and deployed incrementally, the relevant classes may have changed between compile time and runtime.

For example, switch code may be compiled when `Shape` only permits `Circle` and `Rectangle`, and later the library is updated to add a new subtype while **the client containing the switch is not recompiled**. If runtime encounters the new case with no matching branch, Java 21 can throw a **`MatchException`** in an enhanced switch.

This differs from a missing branch at compile time: when recompiling all sources against the new hierarchy, the compiler can detect non-exhaustiveness and reject it. A runtime `MatchException` is a safeguard when the exhaustiveness assumption in an older binary no longer holds.

You should not put `default` in every switch just to avoid this scenario if the business requirement is to **force updating handlers when a subtype is added**. Decide between two strategies: *fail fast when a new type appears* or *define fallback behavior*. Testing deployments across versions helps reduce the risk of binary mismatch.

## 13. Complete runnable example on Java 21

Create the file **`ExhaustiveSwitchStatementDemo.java`**:

```java
public class ExhaustiveSwitchStatementDemo {
    sealed interface Command permits Open, Close {}

    record Open(String path) implements Command {}

    record Close(int code) implements Command {}

    static void handle(Command command) {
        // Exhaustive by covering both permitted subtypes.
        switch (command) {
            case Open open ->
                    System.out.println("open:" + open.path());
            case Close close ->
                    System.out.println("close:" + close.code());
        }
    }

    static void handleNullable(Command command) {
        switch (command) {
            case null -> System.out.println("missing command");
            case Open open ->
                    System.out.println("open:" + open.path());
            case Close close ->
                    System.out.println("close:" + close.code());
        }
    }

    static void classify(Object input) {
        // Exhaustive for Object thanks to default.
        switch (input) {
            case null -> System.out.println("null");
            case String s when s.isBlank() ->
                    System.out.println("blank");
            case String s ->
                    System.out.println("text:" + s.strip());
            case Integer n ->
                    System.out.println("integer:" + n);
            default ->
                    System.out.println("other");
        }
    }

    static void traditional(int value) {
        // Traditional switch statement: not required to be exhaustive.
        switch (value) {
            case 1 -> System.out.println("one");
        }
    }

    public static void main(String[] args) {
        handle(new Open("report.txt"));
        handle(new Close(7));
        handleNullable(null);

        classify(null);
        classify("  ");
        classify("  Java  ");
        classify(4);
        classify(2.5);

        traditional(2); // Prints nothing.
        System.out.println("done");
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 ExhaustiveSwitchStatementDemo.java
java ExhaustiveSwitchStatementDemo
```

`--enable-preview` is not needed: pattern matching for switch is standardized in Java 21.

**Stdout:**

```text
open:report.txt
close:7
missing command
null
blank
text:Java
integer:4
other
done
```

Matching the output:

1. `handle(new Open(...))` and `handle(new Close(...))` use a sealed hierarchy with exactly two subtypes. The compiler proves the `switch statement` exhaustive without `default`.
2. `handleNullable(null)` uses `case null` to handle a null reference, still without `default`.
3. `classify(...)` uses two `String` branches (one guarded), one `Integer` branch, `case null`, and `default`; no `Object` input is left unhandled by label-selection rules.
4. `traditional(2)` uses a traditional switch statement with only `case 1`; the call prints nothing and is not rejected by the compiler for being non-exhaustive.
5. `"  "` is identified as blank by `s.isBlank()`, while `"  Java  "` enters the subsequent `case String s` and is stripped via `strip()` to `"Java"`.
6. The value `4` is boxed to `Integer` when passed to the `Object` parameter; `2.5` becomes `Double` and enters `default`.

To test the rule yourself, try **removing `default` in `classify`** or **removing `case Close close` in `handle`** one at a time, then recompile. Both changes make an enhanced switch statement non-exhaustive. Do not modify the final demo class if you want to keep a runnable example.

## 14. Checklist for quickly reading exhaustiveness

When you see a `switch statement` with patterns, check in order:

1. **What is the static type of the selector?** Broad `Object`, a relatively closed `sealed interface`, a finite `enum`, or another supertype?
2. **Is this an enhanced switch statement?** If it has a pattern label, the answer is yes, and the compiler requires exhaustiveness.
3. **Is there a `default`?** If so, that branch usually covers the remaining non-null values; if not, the patterns/constants must be proven to cover everything.
4. **If the selector is a sealed type, are all permitted subtypes covered?** A single missing subtype can make the switch non-exhaustive.
5. **Does a `when` branch handle only part of a type?** There should be an unguarded branch of the same type after it if the remainder needs coverage.
6. **How is `null` handled?** Do not confuse compile-time exhaustiveness with null-safety; look for `case null` or `case null, default`.
7. **Are any cases dominated?** An earlier unguarded broad-type branch can shadow a narrower branch after it.
8. **Is there any illegal fall-through in colon groups?** Pattern variable scope is a separate rule from exhaustiveness.
9. **Should `default` be omitted to get warnings when extending a sealed hierarchy?** It depends on business requirements: if adding a subtype is a change that must be handled explicitly, a fallback branch can hide the need for updates.
10. **Have real-world data cases and binary changes been tested?** The compiler helps a lot, but it does not replace testing `null`, guards, validation, and version compatibility.

**Conclusion:** In Java 21, **a pattern switch statement must be exhaustive** because it is an enhanced switch statement. For an open selector like `Object`, `default` is a clear way to provide coverage; for sealed types, you can list all subtypes to **avoid needing `default`** and receive compiler verification support. Still, `when`, `null`, dominance, and potential hierarchy changes must all be considered separately — exhaustiveness does not mean the program is safe from all runtime errors or satisfies every business rule.

### References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21, §14.11.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
