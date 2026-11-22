# Sealed Hierarchies and Exhaustive Analysis in Java

## 1. Why Does a Sealed Hierarchy Help the Compiler Know a `switch` Is Exhaustive?

In Java, a **sealed class/interface** restricts which types are permitted to directly extend or implement it. Since Java 17, this has been a standard feature (JEP 409). When **pattern matching for `switch`** became a standard feature in **Java 21** (JEP 441), the compiler can combine information from `sealed` with `case` labels to check **exhaustiveness**: every valid value according to the static type of the selector (except for the special handling of `null`) has a matching branch.

Example structure:

```text
Shape (sealed interface)
├── Circle (record, final)
└── Quad (sealed interface)
    ├── Rectangle (record, final)
    └── Square (record, final)
```

If a variable has the static type `Shape`, in terms of its declared type, the valid branches of this hierarchy are restricted by `permits`. A `switch` that covers `Circle`, `Rectangle`, and `Square` can **compile without `default`**. The compiler checks not only a flat list of `case` labels, but also the sealed inheritance tree structure.

```java
static String describe(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

The snippet above is just the method placed in a context where `Shape`, `Circle`, `Rectangle`, and `Square` are declared accordingly; the complete program is in Section 5.

**Distinguishing three concepts:**

- **Sealed hierarchy:** a type model with a list of *permitted direct subclasses/subinterfaces*, allowing the compiler to know which direct inheritance branches can appear.
- **Exhaustive analysis:** static checking that the `case` labels cover all possibilities that need to be considered for the selector type; this is the compiler's responsibility.
- **Runtime matching:** at runtime, Java selects the first label that matches the actual object and the `when` guard (if any). This is an execution-time decision, not a count of `case` labels.

**Foundational takeaway:** a `switch` can be **exhaustive without `default`**, but a `switch` proven to be exhaustive still does not mean it automatically handles `null` the way you intend.

## 2. How Are `sealed`, `final`, and `non-sealed` Related?

A sealed declaration has the form:

```java
sealed interface Shape permits Circle, Quad {
}
```

`permits` specifies the **direct subtypes** allowed to implement/extend `Shape`. Each valid direct subtype must choose how to continue the inheritance restriction:

1. **`final`:** terminates the branch; no new subclasses of that class are allowed. A `record` is implicitly `final`, making it well suited as a leaf of the tree.
2. **`sealed`:** keeps the branch closed in a controlled way, further declaring which direct types are permitted to extend it.
3. **`non-sealed`:** reopens the branch for extension/implementation by other types, without needing to declare all future subclasses.

Example:

```java
sealed interface Shape permits Circle, Quad {}

record Circle(int radius) implements Shape {}

sealed interface Quad extends Shape permits Rectangle, Square {}

record Rectangle(int width, int height) implements Quad {}

record Square(int side) implements Quad {}
```

These declarations must be placed in a valid Java context (the same compilation unit/package/module according to sealed rules), or you can use the full program in Section 5. They mean:

- `Circle` directly implements `Shape` and is automatically `final` because it is a record.
- `Quad` is a direct subtype of `Shape`, but not a leaf: it is itself sealed and only permits `Rectangle` and `Square`.
- `Rectangle` and `Square` directly implement `Quad`.
- The compiler can reason from `Shape` down to the leaves of the `Quad` branch when checking `case` labels.

**Do not think of `permits` as a list of all subtypes at every level.** It lists **the direct types** that are permitted; the compiler recursively uses the sealed information in the lower branches to analyze coverage.

Placing declarations in the appropriate package/module is also part of Java's sealed rules: in a named module, permitted direct classes must belong to the same module; in an unnamed module, they must belong to the same package. Do not split the examples into arbitrary files/packages and assume that simply adjusting `permits` is enough.

## 3. Exhaustiveness Is Determined Based on the Static Type of the Selector

Suppose:

```java
Shape shape = new Circle(2);
```

When writing `switch (shape)`, the static type that the compiler inspects is `Shape`, not just the runtime class `Circle` of the object assigned in a single run.

```java
static String kind(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        case Quad q -> "quad";
    };
}
```

This is **exhaustive** because:

- Any non-`null` `Shape` value belongs to the direct branch `Circle` or `Quad`.
- The pattern `case Circle c` handles the `Circle` branch.
- The pattern `case Quad q` handles **all** of `Quad`, including every current `Rectangle` and `Square`, as well as any valid subtype of `Quad` if the structure is extended in the future.

Coverage can be achieved in two different ways:

| Approach | Branches | Benefits and Limitations |
| --- | --- | --- |
| **Group by supertype** | `case Circle`, `case Quad` | Concise; all subtypes of `Quad` share the same handling |
| **List down to leaves** | `case Circle`, `case Rectangle`, `case Square` | Distinguishes each subtype; easy to update individual behavior |

Both approaches can be exhaustive. Which one to choose **depends on business logic**; you are not forced to always list every leaf record.

Conversely, the following snippet is **not exhaustive**:

```java
// Compile ERROR on Shape:
// static String incomplete(Shape shape) {
//     return switch (shape) {
//         case Circle c -> "circle";
//         case Rectangle r -> "rectangle";
//         // Missing Square.
//     };
// }
```

Because the `Square` branch has no label covering it, the compiler reports an error similar to:

```text
the switch expression does not cover all possible input values
```

You can fix it by adding `case Square s`, changing to `case Quad q` to cover both branches under `Quad`, or using `default` if you genuinely want a fallback rather than separate handling.

## 4. Why Doesn't Java 21 Require `default` in the Sealed Example?

A `switch expression` must be **exhaustive**: when used as an expression, it needs handling for the entire domain of values the compiler considers possible. Java 21 also requires an **enhanced `switch` statement** (for example, one using type patterns) to be exhaustive.

The most common way to make a `switch` on `Object` exhaustive is to add `default`:

```java
static String generic(Object input) {
    return switch (input) {
        case String s -> "string";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

However, a sealed hierarchy gives the compiler another way: if the branches cover the entire type tree, **no `default` is needed**.

With sealed `Shape`, omitting `default` is often **intentional**. When the development team adds a new permitted subtype and recompiles the code, the compiler can pinpoint where existing `switch`es have not yet handled the new subtype. Adding `default` upfront would allow the program to compile without forcing developers to update each specific branch.

However, **omitting `default` is not always the right choice**:

- If an API needs to return a generic message for unsupported cases, `default` may be reasonable behavior.
- If each subtype requires dedicated handling and introducing a new subtype is a contract change, you should let the compiler detect missing branches.
- If the selector has an open type, such as `Object`, the compiler cannot infer all subtypes from another `sealed` type nested underneath; you must consider the **static type of the selector** and the branches that actually cover that type.

**Version difference:** sealed types became standard in Java 17, whereas pattern `switch` using `case Circle c ->` and `when` as shown in this article became standard in Java 21. To compile the examples, use `javac --release 21`, not `--release 17`.

## 5. Complete Java 21 Program: Two-Level Sealed Hierarchy

Create the file **`SealedExhaustiveDemo.java`**:

```java
public class SealedExhaustiveDemo {
    sealed interface Shape permits Circle, Quad {}

    record Circle(int radius) implements Shape {}

    sealed interface Quad extends Shape permits Rectangle, Square {}

    record Rectangle(int width, int height) implements Quad {}

    record Square(int side) implements Quad {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c ->
                "circle:" + c.radius();
            case Rectangle r ->
                "rectangle:" + (r.width() * r.height());
            case Square s ->
                "square:" + (s.side() * s.side());
        };
    }

    static String grouped(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle";
            case Quad q -> "quad";
        };
    }

    public static void main(String[] args) {
        Shape[] shapes = {
            new Circle(2),
            new Rectangle(3, 4),
            new Square(5)
        };

        for (Shape s : shapes) {
            System.out.println(describe(s));
        }

        System.out.println(grouped(new Square(5)));

        try {
            describe(null);
        } catch (NullPointerException e) {
            System.out.println("null=>NPE");
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 SealedExhaustiveDemo.java
java SealedExhaustiveDemo
```

Output:

```text
circle:2
rectangle:12
square:25
quad
null=>NPE
```

Explanation:

1. `describe` lists the three leaves `Circle`, `Rectangle`, and `Square`; the compiler knows there are no other valid `Shape` branches under the declared sealed structure, so the `switch` is exhaustive.
2. `grouped` does not list every leaf, instead using `Quad` to cover the entire quadrilateral branch; `Square` is classified as `quad`.
3. Neither branch uses `default`, yet both methods **compile**.
4. `describe(null)` throws `NullPointerException`, which `main` catches and prints `null=>NPE`. This is **not** evidence that the `switch` lacks exhaustiveness: `null` is handled according to the specific rules of pattern `switch`.

### How to Handle `null` While Still Omitting `default`

When you want `null` to have its own meaning, add a `case null`:

```java
static String safeDescribe(Shape shape) {
    return switch (shape) {
        case null -> "no shape";
        case Circle c -> "circle";
        case Rectangle r -> "rectangle";
        case Square s -> "square";
    };
}
```

This is still a `switch` without `default`. `case null` matches a `null` selector; the three type patterns handle all remaining `Shape` values.

A common mistake is thinking that `default` will catch `null`:

```java
static String misleading(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle";
        default -> "other";
    };
}
```

The snippet above is **exhaustive for non-null values**, but passing `null` still throws `NullPointerException`. If you want an explicit null-handling policy, use `case null` or `case null, default`.

## 6. `non-sealed` Opens a Branch, Yet Can Still Be Exhaustive

Sealed does not necessarily mean **every** subtype at **every depth** is fixed. A `non-sealed` permitted subtype reopens extensibility within that branch.

Example:

```text
Message (sealed interface)
├── Text (record)
├── Binary (record)
└── Event (non-sealed interface)
    ├── Ping
    └── ... other future implementations
```

Even though `Event` is **non-sealed**, the `switch` below is still exhaustive:

```java
static String classify(Message msg) {
    return switch (msg) {
        case Text t -> "text";
        case Binary b -> "binary";
        case Event e -> "event";
    };
}
```

Why? `Message` only permits three direct branches—`Text`, `Binary`, and `Event`—and `case Event e` matches **every object of type Event**, including implementations not yet written today. The compiler does not need to list every class that might implement `Event`.

What is invalid is writing:

```java
// Not exhaustive if Event is an open branch:
// return switch (msg) {
//     case Text t -> "text";
//     case Binary b -> "binary";
//     case Ping p -> "ping";
// };
```

`Ping` is only one implementation of `Event`. If `UpdateEvent implements Event` is added later, the `switch` above does not know how to handle it. To be exhaustive, it must have `case Event e` or another appropriate fallback label.

### Second Java 21 Program, Standalone

Create **`SealedOpenDemo.java`**:

```java
public class SealedOpenDemo {
    sealed interface Message permits Text, Binary, Event {}

    record Text(String value) implements Message {}

    record Binary(byte[] bytes) implements Message {}

    non-sealed interface Event extends Message {}

    record Ping(String id) implements Event {}

    static String classify(Message msg) {
        return switch (msg) {
            case Text t -> "text:" + t.value();
            case Binary b -> "bytes:" + b.bytes().length;
            case Event e -> "event";
        };
    }

    static String guarded(Message msg) {
        return switch (msg) {
            case Text t when t.value().isEmpty() -> "empty";
            case Text t -> "text";
            case Binary b -> "binary";
            case Event e -> "event";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Text("Hello")));
        System.out.println(classify(new Binary(new byte[]{1, 2, 3})));
        System.out.println(classify(new Ping("p1")));
        System.out.println(guarded(new Text("")));
        System.out.println(guarded(new Text("abc")));
    }
}
```

Run commands:

```bash
javac --release 21 SealedOpenDemo.java
java SealedOpenDemo
```

Output:

```text
text:Hello
bytes:3
event
empty
text
```

`Ping` belongs to the `Event` branch, so it is matched by `case Event e`. `guarded` can use `when` to handle empty `Text` separately; the subsequent unguarded `case Text t` branch still catches other `Text` instances. Because there is a fallback of the same type, the entire `Text` branch remains covered.

**Limitation of the example:** `guarded(new Text(null))` can throw `NullPointerException` in `t.value().isEmpty()`; the compiler checks type coverage, **not** that component data is always non-null. To guard actual data, validate the record's invariant or check `t.value() != null` before calling `isEmpty()`.

## 7. A `when` Guard Can Break Exhaustiveness

A type pattern with `when` usually covers only **a subset** of objects of that subtype. The compiler cannot treat an arbitrary guarded branch as sufficient for the entire subtype.

```java
// Not exhaustive, even though all three Message branches are named:
// return switch (msg) {
//     case Text t when t.value().isEmpty() -> "empty";
//     case Binary b -> "binary";
//     case Event e -> "event";
// };
```

The `Text` branch only handles `Text` objects with an empty `value`. A `Text("abc")` has no case to match. The Java 21 compiler rejects this `switch expression` because it **does not cover all possible values**.

Fix it by adding an unguarded branch after the guarded branch:

```java
return switch (msg) {
    case Text t when t.value().isEmpty() -> "empty";
    case Text t -> "text";
    case Binary b -> "binary";
    case Event e -> "event";
};
```

`when true` is a special case: a guard with the constant expression `true` is considered not to restrict the pattern when evaluating dominance/coverage. However, `when t.value().isEmpty()`, `when n > 0`, and most real-world conditions **cannot** be treated by the compiler as covering the full subtype.

**Do not equate** "in our current data there are no values that fail the guard" with "the compiler can prove exhaustiveness." The compiler relies on type relationships and pattern rules; it does not analyze arbitrary business invariants.

## 8. Generic Sealed Hierarchies: Beyond Counting Names in `permits`

With a sealed generic interface, a permitted subtype may be **incompatible with a specific type argument instantiation**. Java computes exhaustiveness based on the **selector type**, including the relevant type arguments.

Example:

```java
sealed interface Token<T> permits StrToken, BoxToken {}

record StrToken(String value) implements Token<String> {}

record BoxToken<T>(T value) implements Token<T> {}
```

If a variable has type `Token<Integer>`, the type `StrToken` (which only implements `Token<String>`) cannot be a valid runtime type for a `Token<Integer>` variable in a type-safe generic program. Therefore, the compiler can prove that a `switch` with only the `BoxToken<Integer>` branch is exhaustive, without mechanically listing `StrToken`:

```java
static String asInteger(Token<Integer> value) {
    return switch (value) {
        case BoxToken<Integer> box -> "box:" + box.value();
    };
}
```

If the selector has type `Token<String>`, both `StrToken` and `BoxToken<String>` can appear:

```java
static String asString(Token<String> value) {
    return switch (value) {
        case StrToken text -> "str:" + text.value();
        case BoxToken<String> box -> "box:" + box.value();
    };
}
```

This is a valid Java 21 example that must be placed in the context of the generic sealed interface and record declarations above. To run it standalone, use the complete program **`GenericSealedDemo.java`**:

```java
public class GenericSealedDemo {
    sealed interface Token<T> permits StrToken, BoxToken {}

    record StrToken(String value) implements Token<String> {}

    record BoxToken<T>(T value) implements Token<T> {}

    static String asInteger(Token<Integer> value) {
        return switch (value) {
            case BoxToken<Integer> box -> "box:" + box.value();
        };
    }

    static String asString(Token<String> value) {
        return switch (value) {
            case StrToken text -> "str:" + text.value();
            case BoxToken<String> box -> "box:" + box.value();
        };
    }

    public static void main(String[] args) {
        System.out.println(asInteger(new BoxToken<>(42)));
        System.out.println(asString(new StrToken("hi")));
    }
}
```

Run:

```bash
javac --release 21 GenericSealedDemo.java
java GenericSealedDemo
```

Output:

```text
box:42
str:hi
```

**Key point to remember:** *exhaustiveness is a question about the possible values of the selector type*, not simply counting the entries in `permits`. In complex generic cases, do not extrapolate from the `Token<Integer>` example to every other type parameterization; let the appropriate compiler version verify it.

## 9. Why Can a Sealed `switch` Catch Bugs as the System Evolves?

Suppose the first version has two permitted types:

```java
sealed interface Transport permits Car, Bike {}
record Car() implements Transport {}
record Bike() implements Transport {}
```

And there is a `switch`:

```java
static String dispatch(Transport value) {
    return switch (value) {
        case Car c -> "car";
        case Bike b -> "bike";
    };
}
```

In this version, the compiler sees both branches are covered. Later, a developer updates the sealed interface to also permit `Bus`:

```java
// MODIFIED VERSION (illustrative; do not declare alongside the old version):
// sealed interface Transport permits Car, Bike, Bus {}
// record Bus() implements Transport {}
```

When dependent `switch` code is recompiled, the new `Bus` branch can make `dispatch` non-exhaustive, and the compiler reports an error. This is a **major maintainability benefit**: missing handling is caught early instead of silently falling into an unexamined default branch.

If you had previously written:

```java
return switch (value) {
    case Car c -> "car";
    case Bike b -> "bike";
    default -> "other";
};
```

then the `default` branch would still handle `Bus`, and the compiler would not force you to update the `switch` on recompilation. That is good when "other" is truly the desired contract; it is undesirable if each transport type needs dedicated business logic.

### Note on Separate Compilation and `MatchException`

The compiler analyzes only the **type system at compile time**. If a program is compiled against an old sealed hierarchy and then run with classes/binaries that were changed such that at runtime a subtype appears for which the old `switch` code has no matching branch, Java's prior exhaustiveness proof **does not guarantee** that a matching label will always be found for the new data. In the event of a missing runtime label after such an out-of-sync change, an exhaustive pattern `switch` can throw **`java.lang.MatchException`** (Java 21+).

This differs from `NullPointerException` caused by a `null` selector:

- `NullPointerException` occurs when the selector is `null` and there is no `case null` handler.
- `MatchException` can occur when no label matches a non-null value at runtime in a context where the design previously allowed the compiler to conclude exhaustiveness (for example, changing a hierarchy without recompiling dependent code in sync).

**Best practice:** when changing a sealed hierarchy, recompile and test dependent modules in sync; do not treat `default` as a substitute for managing binary compatibility.

## 10. Sealed Hierarchies vs. `enum`, Legacy `switch`, and `if` Chains

**An `enum`** has a finite domain of constants. A `switch expression` on an enum can be exhaustive by listing all constants:

```java
enum Status { NEW, DONE }

static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Unlike a sealed hierarchy, an enum cannot have new subtypes added to it; the domain changes by adding enum constants. In both cases, omitting `default` lets the compiler report when the list of cases changes.

**A legacy `switch` statement** (for example, `switch(int)` with only constant labels) is not always required to be exhaustive:

```java
static void legacy(int x) {
    switch (x) {
        case 1 -> System.out.println("one");
        // default is not necessarily required in a legacy statement.
    }
}
```

**An enhanced `switch` statement** with pattern labels on a type like `Shape` must be exhaustive under Java 21. That explains why the old Java rule "a statement does not need `default`" does not mechanically apply to pattern `switch`.

**An `if/else if (x instanceof ...)` chain** is also not checked for exhaustiveness by the compiler the way a `switch` expression is, even if `x` is a sealed type. You can forget a subtype and Java will still compile:

```java
static String byIf(Shape shape) {
    if (shape instanceof Circle) {
        return "circle";
    }
    // Missing Quad: Java does not automatically report "non-exhaustive if".
    return "other";
}
```

This is not a syntax error: the programmer intentionally returns `other`. However, if the goal is to enforce complete handling of every type, a pattern `switch` on a sealed hierarchy expresses that intent much better.

## 11. Dominance vs. Exhaustiveness

Exhaustiveness asks: **have all values been covered?** Dominance asks: **is any branch completely shadowed by an earlier branch?**

Invalid example:

```java
// ERROR: the later Circle branch is covered by the earlier Shape branch.
// return switch (shape) {
//     case Shape s -> "some shape";
//     case Circle c -> "circle";
// };
```

`case Shape s` is a catch-all pattern for the selector type `Shape` (for non-null objects), so the later `case Circle c` has no chance of ever being selected. The compiler reports a **dominated case label**. In terms of coverage, the first branch may already be broad enough; the issue here is an **invalid case structure**, not a missing branch.

Putting the specific type first is valid:

```java
return switch (shape) {
    case Circle c -> "circle";
    case Shape s -> "other shape";
};
```

You also should not write a separate `default` after an unconditional `case Shape s` pattern on a `Shape` selector: Java 21 does not allow both an unconditional pattern for the selector and a separate `default` branch.

With a sealed hierarchy whose subtypes can be enumerated, **you usually do not need a catch-all `case Shape`** just to silence a non-exhaustive compiler error: doing so hides future additions of subtypes that need dedicated handling.

## 12. Common Mistakes and How to Fix Them

| Misconception | Reality | Correct Approach |
| --- | --- | --- |
| "With `sealed`, every `switch` is automatically exhaustive" | Full coverage of the selector type is still required | List the subtypes or use a pattern for the appropriate supertype branch |
| "You must add `default` for a `switch` to compile" | Sealed/enum types can be covered explicitly | Omit `default` if you want the compiler to catch missing subtypes |
| "Just count the names in `permits`" | `permits` only lists direct subtypes; sealed types can be nested | Analyze recursively or cover the parent branch |
| "`non-sealed` breaks exhaustiveness for the whole hierarchy" | The `non-sealed` branch still has a common supertype | Use a pattern on the `non-sealed` branch itself, e.g., `case Event e` |
| "Listing one implementation of `non-sealed` is enough" | A `non-sealed` type can have any number of other subtypes | Cover the `non-sealed` interface/class or use an appropriate fallback |
| "A guarded case covers an entire subtype" | An arbitrary guard can evaluate to false | Add an unguarded case for the subtype or `default` |
| "`default` automatically handles `null`" | A standalone `default` does not match a `null` selector | Add `case null` when you want to handle `null` |
| "Exhaustive means no runtime errors" | Guards can throw exceptions; `null` can cause NPE; binary drift can cause `MatchException` | Validate data and maintain version compatibility |
| "You can put a superclass `case` before a subclass `case`" | The later subclass branch is dominated | Place specific patterns before general ones |
| "Generic sealed always requires every subclass in `permits`" | A specific instantiation can rule out incompatible subtypes | Consider the selector's type arguments and compile with the right release |
| "Java 17 supports pattern `switch` like Java 21" | Java 17 does not have standard pattern `switch` | Use JDK 21+ for the examples |

## 13. Checklist for Designing a `switch` with Sealed Types

1. **Identify the static type of the selector**, including generic arguments.
2. **Map out the direct `permits` tree**, marking which branches are `final`, `sealed`, and `non-sealed`.
3. **Decide the level of granularity**: individual leaves or a shared pattern for a parent branch?
4. **Check coverage recursively**: for every possible subtype, is there a case guaranteed to apply?
5. **Inspect guards**: `when` can fail; an unguarded branch is needed to cover the remainder.
6. **Define the `null` policy**: let Java throw `NullPointerException` or handle it with `case null`?
7. **Decide whether `default` is needed**: fallback for an open type, or do you want the compiler to warn on new subtypes?
8. **Order branches to avoid dominance**: specific before general, guarded branches before unguarded branches of the same type.
9. **Test hierarchy evolution**: add a subtype in a test environment and verify the expected compile-time errors.
10. **Compile with the right version and keep binaries in sync**: use `javac --release 21` for pattern `switch`, and rebuild dependent modules when changing a sealed hierarchy.

## 14. Self-Check

**Q1.** `sealed interface S permits A, B`, where both `A` and `B` are records. What happens if `switch(S)` has `case A` and `case B` without `default`?

**Answer:** It is valid and exhaustive in Java 21, provided the permitted direct subclasses are indeed `A` and `B` and the cases cover them completely. `null` still needs to be considered separately.

**Q2.** `S permits A, Branch`, and `Branch` is `sealed` permitting `B1` and `B2`. Is writing only `case A` and `case Branch` sufficient?

**Answer:** Yes, because `case Branch` matches every object that is a subtype of `Branch`, including `B1` and `B2`.

**Q3.** A permitted direct subtype `Event` is `non-sealed`. If you only list `Ping implements Event`, is the `switch` exhaustive?

**Answer:** No, because other `Event` implementations may exist. `case Event e` covers the entire open branch.

**Q4.** You only have `case Text t when t.value().isEmpty()` for the `Text` branch of sealed `Message`; is that sufficient?

**Answer:** No. `Text("abc")` is a valid value for which the guard is false; you need an unguarded `case Text t` or an appropriate fallback.

**Q5.** Why can `switch(Token<Integer>)` in the generic example only need `BoxToken<Integer>` without `StrToken`?

**Answer:** `StrToken` only implements `Token<String>`, which is incompatible with the selector type `Token<Integer>`; the generic type argument changes which subtypes are possible.

**Q6.** A sealed `switch` without `default` compiled successfully. Is it guaranteed never to throw a runtime exception?

**Answer:** No. `null` can cause `NullPointerException`, operations inside a branch can throw exceptions, and out-of-sync binary/sealed hierarchy changes can lead to `MatchException`.

**Q7.** Why can `default` be undesirable when adding a new subtype that requires dedicated handling?

**Answer:** `default` keeps the old code exhaustive upon recompilation, so the compiler does not force the developer to write a branch for the new subtype. Omitting `default` lets compile errors act as a warning for missing handling.

### Core Takeaway

**`sealed` closes the set of direct inheritance branches; exhaustive analysis uses the selector type and that type tree to prove every required value is handled by a `case`.** You do not always need `default`, but you must always account for `non-sealed` branches, guards that can evaluate to false, generic type arguments, and the `null` policy. This is the practical benefit of sealed hierarchies combined with pattern `switch` in Java 21: data modeling and completeness checking of control logic are tied together at compile time.

### Official References

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 §14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java SE 21 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JLS Java SE 21 §8.1.1.2 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
