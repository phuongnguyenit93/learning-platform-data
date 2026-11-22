# What is an Exhaustive Switch in Java Pattern Matching?

## 1. Concept: a `switch` that covers all cases

An **exhaustive switch** is a `switch` expression or statement whose `case` labels, according to the **compiler's static** checking rules, cover all possibilities that need to be handled for the **selector type** (the value passed into `switch`). If a form of `switch` is required to be exhaustive and is missing a possibility, Java reports a **compile-time error**.

Example with an enum:

```java
enum Signal { RED, YELLOW, GREEN }

static String traffic(Signal signal) {
    return switch (signal) {
        case RED    -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN  -> "GO";
    };
}
```

This `switch` expression is **exhaustive** because `Signal` has only three declared enum constants: `RED`, `YELLOW`, `GREEN`; all three have corresponding cases. No `default` is needed.

Conversely, the following snippet **does not compile**:

```java
// INVALID: switch expression is missing GREEN.
// static String traffic(Signal signal) {
//     return switch (signal) {
//         case RED    -> "STOP";
//         case YELLOW -> "WAIT";
//     };
// }
```

The compiler knows `signal` can be `GREEN`, but no branch provides a value for that case.

**Key takeaway:** exhaustiveness is a property of **compile-time type coverage**, not a claim that "all cases were executed during testing". A test suite can run through many cases and still miss a valid value; the compiler can point out missing coverage for certain types without running the program.

This article uses **Java 21 or later**, because *Pattern Matching for switch* was finalized in Java 21 (JEP 441). Examples that only use enum switch expressions can work on older versions, whereas examples using case patterns, sealed types, and `case null` are written for Java 21.

## 2. Why does Java need exhaustive switch?

`switch` is commonly used to map an input to a result or choose appropriate behavior. If a branch can be missed, the program can easily encounter an unhandled situation.

With a **switch expression**, Java needs a value to assign or `return`. If a case fails to produce a value, the expression is no longer reliable:

```java
String action = switch (signal) {
    case RED    -> "stop";
    case YELLOW -> "slow";
    case GREEN  -> "go";
};
```

The compiler checks that the cases cover the `Signal` type, ensuring every known enum value leads to a rule.

With **pattern matching**, the selector can be a general type such as `Object` or a `sealed interface`:

```java
static String describe(Object value) {
    return switch (value) {
        case String s  -> "TEXT:" + s;
        case Integer n -> "INT:" + n;
        default        -> "OTHER";
    };
}
```

`Object` can hold many other types besides `String` and `Integer`; therefore `default` helps cover those other values.

Benefits of exhaustiveness:

1. **Catch missing branches at compile time:** errors surface early, before the system runs in production.
2. **Reduce bugs when adding new enum values or subtypes:** when modifying source code and recompiling, the compiler can require updating switches that exhaustively listed all cases.
3. **Clarify the handling contract:** readers know the switch is attempting to handle the entire input type, not just a few cases of interest.
4. **Support domain modeling with sealed types:** bounded states or result types allow a switch to be exhaustive without an arbitrary default.

Exhaustiveness **does not prove** that the branches are business-correct, does not guarantee no exceptions are thrown, and does not replace testing.

## 3. Do switch expressions and switch statements have the same requirements?

Not entirely. This is an important distinction in **Java 21**.

| Switch form | Must be exhaustive? | Explanation |
| --- | --- | --- |
| **Switch expression** `return switch (...) { ... };` | **Yes, always** | Must produce a result or complete appropriately for every value considered |
| **Enhanced switch statement** | **Yes** | Java 21 requires a statement using patterns, `case null`, or a newly supported reference selector type to be exhaustive |
| **Classic switch statement** | **Not required** | Preserves compatibility with existing Java code; missing cases may result in no branch executing |

### 3.1. Switch expression: must be exhaustive

```java
static int grade(Signal signal) {
    return switch (signal) {
        case RED    -> 0;
        case YELLOW -> 1;
        case GREEN  -> 2;
    };
}
```

This is an **expression** of type `int`. The compiler requires the set of cases to be exhaustive.

For a block with multiple statements, use `yield` to supply the value:

```java
static int value(Object input) {
    return switch (input) {
        case String s -> {
            int length = s.strip().length();
            yield length;
        }
        case Integer n -> n;
        default -> 0;
    };
}
```

`yield` returns a value for the **switch expression**, not `return` from the method. Whether branches use a direct expression or `yield` does not change the exhaustiveness requirement.

### 3.2. Enhanced switch statement: also must be exhaustive

In Java 21, a `switch statement` is called **enhanced** if it satisfies at least one condition:

- The selector type is not in the set of types allowed by classic switch: `char`, `byte`, `short`, `int`, their corresponding wrappers, `String`, or an enum; for example `Object`, `Number`, or an interface.
- Or the switch contains a **case pattern** or a **`case null`** label.

The following example is an **enhanced switch statement** and is valid:

```java
static void printCategory(Object value) {
    switch (value) {
        case String s -> System.out.println("STRING:" + s);
        default       -> System.out.println("OTHER");
    }
}
```

`default` covers types other than `String`. If `default` is removed in this `Object` example, the code is rejected due to a **non-exhaustive switch statement**.

An enhanced switch statement using all types of a sealed hierarchy can also be exhaustive without `default` (see section 6).

### 3.3. Classic switch statement: exception for backward compatibility

```java
static void printTraffic(Signal signal) {
    switch (signal) {
        case RED -> System.out.println("STOP");
    }
}
```

This snippet **still compiles in Java 21** because it is a classic switch statement on an enum, with no case patterns and no `case null`. If `signal` is `YELLOW` or `GREEN`, no branch matches and the statement finishes without printing anything.

**Do not conclude that every `switch` must be exhaustive.** The exact rule is: **every switch expression and every enhanced switch statement** must be exhaustive; classic switch statements remain flexible for compatibility with legacy code.

## 4. Approach 1: exhaustiveness via `default`

The most obvious way is to add a `default` branch:

```java
static String classify(Object value) {
    return switch (value) {
        case String s  -> "STRING";
        case Integer n -> "INTEGER";
        default        -> "OTHER";
    };
}
```

Here:

- `String` is handled by the type pattern `String s`.
- `Integer` is handled by `Integer n`.
- All remaining non-`null` objects are handled by `default`.

Thanks to `default`, the switch **is considered exhaustive under static checking**. However, there are two caveats:

1. `default` does not automatically handle `null` the way many people assume (section 8).
2. `default` can prevent the compiler from **warning you** later when you add a new enum constant or subtype, because the default branch already covers them. Sometimes that is intentional; sometimes it hides a missing business-logic case.

### When does `default` make sense?

`default` is appropriate when the input is genuinely open, such as `Object`, or when there is a sensible general behavior for all unspecialized values. For closed domains using enums/sealed types, consider letting the compiler verify all cases **without a default** if you want type changes to force you to revisit the logic.

### What does `case null, default` mean?

Java 21 also supports a combined label:

```java
static String safeClassify(Object value) {
    return switch (value) {
        case String s     -> "STRING:" + s;
        case Integer n    -> "INTEGER:" + n;
        case null, default -> "OTHER_OR_NULL";
    };
}
```

The `case null, default` label handles both **`null`** and all remaining values. Under Java 21 syntax, this is a special form of label; it is not a type pattern, and should be placed at the end of the switch.

## 5. Approach 2: listing all enum constants

An enum defines a **finite set of values**. Therefore, the compiler can check exhaustiveness by counting all constants.

```java
enum PaymentStatus { NEW, PAID, REJECTED }

static String paymentText(PaymentStatus status) {
    return switch (status) {
        case NEW      -> "Pending";
        case PAID     -> "Paid";
        case REJECTED -> "Rejected";
    };
}
```

No `default` is needed because all three constants of `PaymentStatus` appear in the cases.

Constants with the same handling can be grouped:

```java
static boolean finalState(PaymentStatus status) {
    return switch (status) {
        case NEW            -> false;
        case PAID, REJECTED -> true;
    };
}
```

`case PAID, REJECTED` covers **two enum constants**; together with `NEW`, the entire enum is handled.

### What happens if a constant is missing?

```java
// DOES NOT COMPILE: missing REJECTED.
// static String paymentText(PaymentStatus status) {
//     return switch (status) {
//         case NEW  -> "new";
//         case PAID -> "paid";
//     };
// }
```

This is a compile-time error, **not** a case where the switch expression returns `null` or an implicit default value.

### Why is omitting `default` sometimes better?

Suppose the enum initially contains `NEW`, `PAID`, `REJECTED`. If `REFUNDED` is added later and **the source code is recompiled**, a switch expression listing the three old constants will report that it is non-exhaustive. This forces the maintainer to consider how to handle refunds.

If `default -> "OTHER"` was written previously, the code will usually continue to compile without forcing an update for the new business branch. Both approaches are valid; the choice depends on how strongly you want the compiler to enforce the enum contract.

## 6. Approach 3: sealed type + case patterns

**Sealed classes/interfaces** restrict which types are allowed to directly extend or implement them. This is a key foundation for writing an exhaustive pattern switch **without `default`**.

Suppose we have business results:

```java
sealed interface ApiResult permits Success, Failure {}

record Success(String data) implements ApiResult {}

record Failure(int code) implements ApiResult {}
```

Java knows a valid `ApiResult` value belongs to one of the permitted types. We can write:

```java
static String render(ApiResult result) {
    return switch (result) {
        case Success s -> "OK:" + s.data();
        case Failure f -> "ERROR:" + f.code();
    };
}
```

The code is valid and exhaustive because `Success` and `Failure` are the entire set of permitted subtypes. Both `Success` and `Failure` are records, which are implicitly `final`.

**Key points to understand:**

- `case Success s` is a **type pattern**: it matches any non-`null` `Success` object and binds variable `s`.
- `case Failure f` covers any non-`null` `Failure` object.
- Together, the two cases cover the **`ApiResult` type** under sealed hierarchy rules.
- Because no third subtype can be validly declared in this hierarchy, the compiler does not require `default`.

### Not every interface lets you omit default

With an ordinary interface:

```java
interface Work {}
record Task(String name) implements Work {}
```

`Work` can be implemented by many other classes, including classes added later. Therefore:

```java
// DOES NOT COMPILE: an open interface has other possible implementations.
// static String workKind(Work work) {
//     return switch (work) {
//         case Task t -> t.name();
//     };
// }
```

is not exhaustive. You can add `default` or a type pattern covering `Work` values to handle it.

### What if a sealed branch still allows extension?

A type listed in `permits` can be `non-sealed`, allowing new subclasses beneath it. In that case, you cannot assume listing only a few specific subclasses is enough. A type pattern case on **the entire `non-sealed` branch** will cover every object in that branch.

Conceptual example:

```java
sealed interface Message permits TextMessage, SystemMessage {}

record TextMessage(String text) implements Message {}

non-sealed interface SystemMessage extends Message {}
```

To be exhaustive without `default`, you can use `case TextMessage t` together with `case SystemMessage s`; the second pattern covers all implementations of `SystemMessage`, not just one currently existing subclass.

**Rule:** exhaustiveness is determined by **type coverage**, not simply by the number of `case` lines.

## 7. Approach 4: catch-all type pattern (unconditional pattern)

Another way to cover open input is to use a pattern that matches any **non-`null`** value of the selector type.

```java
static String anyNonNull(Object value) {
    return switch (value) {
        case String s -> "TEXT:" + s;
        case Object o -> "OTHER_OBJECT:" + o.getClass().getSimpleName();
    };
}
```

In Java 21, `case Object o` is an **unconditional type pattern** for a selector of type `Object`; it covers all remaining non-`null` object values. Thus, the switch expression is considered exhaustive without `default`.

However, `anyNonNull(null)` still throws `NullPointerException` because **there is no `case null`**.

If you want to explicitly define how `null` is handled, add it:

```java
static String anyValue(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OBJECT:" + o.getClass().getSimpleName();
    };
}
```

Here `case Object o` covers non-`null` values that are not `String`, while `case null` handles the null case.

### Ordering rule: narrower cases first, broader cases later

```java
// DOES NOT COMPILE: String is already covered by Object first.
// return switch (value) {
//     case Object o -> "OBJECT";
//     case String s -> "STRING";
// };
```

Java rejects the `String` branch as **dominated** by `Object`. To handle `String` separately, place `case String s` before `case Object o`.

Also, do not add `default` after an unconditional pattern on the same selector: two catch-all labels conflict under switch rules.

## 8. `null` is an exception that requires explicit handling

This is the most important misconception about exhaustiveness.

**Exhaustiveness does not mean `null` is handled automatically.** Java checks value coverage by type, but `null` is not an enum value and does not match an ordinary type pattern.

```java
static String color(Signal signal) {
    return switch (signal) {
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

This expression is exhaustive for the `Signal` type, yet:

```java
// If executed:
// color(null);
// -> NullPointerException.
```

Because there is no `case null`, a null input leads to an exception, **even though compilation succeeded**.

### Choosing how to handle `null` by business logic

**Option 1: catch `null` in a Java 21 switch**

```java
static String safeColor(Signal signal) {
    return switch (signal) {
        case null   -> "missing";
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

**Option 2: reject `null` at the start of the method**

```java
static String requiredColor(Signal signal) {
    java.util.Objects.requireNonNull(signal, "signal");
    return switch (signal) {
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

Option 2 does not turn `null` into an enum constant; it simply makes the non-null precondition explicit.

**Option 3: combine `null` with `default`** if you want the same result for both:

```java
static String category(Object value) {
    return switch (value) {
        case String s     -> "TEXT:" + s;
        case null, default -> "UNKNOWN";
    };
}
```

**Note:** `default` alone does not handle `null`. In a Java 21 pattern switch, if you want `null` to enter a branch, use `case null` or `case null, default`.

## 9. Does a `when` guard make a switch exhaustive?

A **guard** is an additional condition checked after a type pattern matches. For example:

```java
static String numberCase(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n            -> "NON_POSITIVE_INTEGER";
        default                   -> "OTHER";
    };
}
```

`case Integer n when n > 0` **does not cover every `Integer`**: it only matches positive numbers. An `Integer` that is zero or negative falls through to the unguarded `case Integer n`. `default` handles other types.

If there is only a guarded pattern:

```java
// DOES NOT COMPILE: not exhaustive.
// static String onlyPositive(Object value) {
//     return switch (value) {
//         case Integer n when n > 0 -> "POSITIVE";
//     };
// }
```

then the switch expression still leaves many values uncovered: zero, negative numbers, strings, and other objects.

### Guards are not a static guarantee covering all values

When analyzing exhaustiveness, the compiler uses **case constants** and **case patterns not restricted by dynamic guards**, along with type coverage rules. You must not assume the compiler can deduce completeness from arbitrary boolean expressions.

Conceptual example:

```java
// DO NOT ASSUME this is exhaustive just because two guards seem
// to partition all Integer cases:
// case Integer n when n >= 0 -> ...
// case Integer n when n < 0  -> ...
```

For selector `Integer`, the compiler does not treat the two business conditions `n >= 0` and `n < 0` as a general proof replacing an unguarded case.

**Clear approach:** place guarded cases first, followed by an unguarded case of the same type. For an `Object` selector, add branches for other types or `default` to be exhaustive.

### Dominance is not the same as exhaustiveness

If an unguarded `case Integer n` is placed **before** `case Integer n when n > 0`, the later guarded branch is completely covered and causes a **dominated case** error. Thus Java has at least two distinct checks:

- **Exhaustiveness:** are any required cases missing?
- **Dominance:** is any later case unreachable because an earlier case already covers it?

A switch with `default` can still fail dominance; the two rules do not replace each other.

## 10. Record patterns and exhaustiveness

A **record pattern** (finalized in Java 21, JEP 440) can deconstruct record components and participate in exhaustiveness checking.

Example:

```java
record Point(int x, int y) {}

static String pointKind(Point point) {
    return switch (point) {
        case Point(int x, int y) -> "POINT:" + x + "," + y;
    };
}
```

Since `Point` contains **two `int` components**, the record pattern above covers every valid non-`null` `Point` value: every point has an integer value for `x` and `y`. Therefore, the switch expression is exhaustive for type `Point`.

### What if a record pattern matches only part of a component's type?

```java
record Box(Object content) {}
```

A `Box` can hold a `String`, `Integer`, `null`, or another type. Therefore:

```java
// DOES NOT COMPILE: many Box possibilities are missing.
// static String onlyString(Box box) {
//     return switch (box) {
//         case Box(String text) -> text;
//     };
// }
```

is not exhaustive. `case Box(String text)` only matches `Box` instances whose corresponding component fits `String`; it is not enough to cover every `Box`.

**Clear and safe fix:**

```java
static String boxKind(Box box) {
    return switch (box) {
        case Box(String text) -> "TEXT:" + text;
        case Box other        -> "OTHER_BOX";
    };
}
```

`case Box other` is a **type pattern** that covers all remaining non-`null` `Box` instances, regardless of content. It comes after the specialized branch, avoiding dominance.

Note: complex record patterns also have rules for combining multiple branches to prove coverage. For an introductory lesson, check whether the component patterns cover **every possible value of each component**. If unsure, a general type pattern for the record or `default` is a readable solution.

### `null` in a record pattern component vs. `null` in the selector

`new Box(null)` is **not** a `null` selector value; it is a valid `Box` object whose `content` field is `null`. The `case Box other` branch receives this object, whereas `case Box(String text)` does not match when the component is `null`. This distinction is important when writing cases with record deconstruction.

## 11. Relationship with sealed hierarchies, generics, and evolution

### 11.1. Adding a new subtype can break exhaustiveness

Suppose currently:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

A switch with two cases `Success` and `Failure` can be exhaustive.

If later you **modify the sealed interface source** to permit `Pending`:

```java
// Illustrating a design change; do not place alongside the previous declarations:
// sealed interface Result permits Success, Failure, Pending {}
// record Pending() implements Result {}
```

then when recompiling related code, switch expressions without a `Pending` branch can be flagged by the compiler as non-exhaustive. This is a major value of **sealed + pattern switch**.

### 11.2. Generics can make coverage subtler

With a parameterized sealed interface, a subtype may implement only a specific parameterization. Therefore, it is not always necessary to list every `permits` subtype for **every generic instantiation of the selector**. The compiler evaluates whether each subtype is compatible with the actual selector type.

The general rule remains: **the compiler proves coverage based on static types**, not on runtime data. When using complex generics, prefer checking with your project's exact Java language level, and read JLS §14.11.1.1 for details.

### 11.3. What happens if a class/enum changes without recompiling callers?

Exhaustiveness checking happens at **compile time**. In systems distributing multiple independent libraries, code containing a switch compiled against an older enum or sealed hierarchy might load a modified library version at runtime.

In Java 21, if an **exhaustive switch** executes and no case label actually applies to a non-`null` value, the runtime can throw **`MatchException`**. This reflects that the compile-time coverage assumption no longer holds in the runtime environment.

Therefore, exhaustiveness is a very strong compile-time guarantee, **but it does not replace binary compatibility management, dependency upgrades, and integration testing**.

## 12. A complete Java 21 program

Create **`ExhaustiveSwitchDemo.java`**:

```java
public class ExhaustiveSwitchDemo {

    enum Signal {
        RED, YELLOW, GREEN
    }

    sealed interface Event permits Started, Finished {}

    record Started(String name) implements Event {}

    record Finished(int code) implements Event {}

    record Point(int x, int y) {}

    // Exhaustive by listing all enum constants.
    static String traffic(Signal signal) {
        return switch (signal) {
            case RED    -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN  -> "GO";
        };
    }

    // Exhaustive via sealed hierarchy.
    static String event(Event value) {
        return switch (value) {
            case Started s  -> "START:" + s.name();
            case Finished f -> "FINISH:" + f.code();
        };
    }

    // Object selector: must cover all remaining types.
    // Includes case null to handle null explicitly.
    static String classify(Object value) {
        return switch (value) {
            case null                          -> "NULL";
            case String s when s.isBlank()      -> "BLANK";
            case String s                       -> "TEXT:" + s.strip();
            case Number n                       -> "NUMBER:" + n;
            default                             -> "OTHER";
        };
    }

    // General record pattern covers every non-null Point.
    static String pointKind(Point point) {
        return switch (point) {
            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y)             -> "POINT:" + x + "," + y;
        };
    }

    // This is an enhanced switch STATEMENT, which must also be exhaustive.
    static void printAction(Object value) {
        switch (value) {
            case null     -> System.out.println("ACTION:NULL");
            case String s -> System.out.println("ACTION:TEXT");
            default       -> System.out.println("ACTION:OTHER");
        }
    }

    public static void main(String[] args) {
        System.out.println(traffic(Signal.RED));
        System.out.println(traffic(Signal.YELLOW));
        System.out.println(traffic(Signal.GREEN));

        System.out.println(event(new Started("Job")));
        System.out.println(event(new Finished(0)));

        System.out.println(classify("  Java  "));
        System.out.println(classify("   "));
        System.out.println(classify(3.5));
        System.out.println(classify(true));
        System.out.println(classify(null));

        System.out.println(pointKind(new Point(2, 2)));
        System.out.println(pointKind(new Point(2, 5)));

        printAction("abc");
        printAction(10);
        printAction(null);
    }
}
```

Compile and run with **JDK 21 or later** (no preview needed):

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

**Expected output:**

```text
STOP
WAIT
GO
START:Job
FINISH:0
TEXT:Java
BLANK
NUMBER:3.5
OTHER
NULL
DIAGONAL:2
POINT:2,5
ACTION:TEXT
ACTION:OTHER
ACTION:NULL
```

### Why is each switch in the program exhaustive?

| Method | Selector type | Why is it exhaustive? | Handles `null`? |
| --- | --- | --- | --- |
| `traffic` | `Signal` | Covers `RED`, `YELLOW`, `GREEN` | No: `null` causes NPE |
| `event` | Sealed `Event` | Covers both permitted types: `Started`, `Finished` | No: `null` causes NPE |
| `classify` | `Object` | Has `default` covering remaining types | Yes: `case null` |
| `pointKind` | `Point` | Unguarded record pattern covers every `Point`; specialized guard first | No: `null` causes NPE |
| `printAction` | `Object` | Enhanced switch statement with `default` | Yes: `case null` |

The program does not call the methods that do not handle `null` with a `null` value; the last column explains the boundary of exhaustiveness checking rather than describing printed program output.

`printAction` is a **switch statement**, so the rules after `->` are valid `System.out.println(...)` statements. The other methods return **switch expressions** and must supply an appropriate result.

## 13. Common mistakes

### Mistake A: thinking a few common cases are enough

```java
// DOES NOT COMPILE:
// static String kind(Object value) {
//     return switch (value) {
//         case String s  -> "TEXT";
//         case Integer n -> "NUMBER";
//     };
// }
```

Because `Object` also includes `Double`, `Boolean`, lists, records, etc., the switch expression is not exhaustive. You need `default` or an appropriate type pattern to cover the rest.

### Mistake B: confusing classic switch statements with enhanced switch statements

A classic statement on `Signal` with only `case RED` is still allowed. However, a statement taking `Object` with only `case String s` is rejected if it lacks a catch-all branch. Both use the `switch` keyword, but their exhaustiveness rules differ in Java 21.

### Mistake C: thinking `default` catches `null`

```java
// When value == null, default is NOT selected just because default exists.
// static String kind(Object value) {
//     return switch (value) {
//         case String s -> s;
//         default       -> "OTHER";
//     };
// }
```

If the selector is null and there is no `case null`, the switch throws `NullPointerException`. Add `case null` or `case null, default` if you want to handle it instead of throwing an exception.

### Mistake D: thinking a guard always covers the entire type

`case Integer n when n > 0` does not match `0` or negative numbers. A switch expression with only this guarded case is not exhaustive. Add a general `case Integer n` after it or an appropriate `default`.

### Mistake E: using `default` to "fix" dominance

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case Number n  -> "NUMBER";
//     case Integer i -> "INTEGER";
//     default        -> "OTHER";
// };
```

`Integer` is a `Number`, so the later `Integer` case is **dominated**. `default` cannot fix this error; you must put narrower cases before broader cases.

### Mistake F: listing a few subtypes of an open interface and omitting default

If an interface is not `sealed` and can be implemented by many classes, the compiler cannot assume the currently visible classes are all possibilities. To be exhaustive, use `default` or a general pattern covering the interface. Only use `sealed` when it fits the domain design.

### Mistake G: treating exhaustiveness as a guarantee of "never throwing exceptions"

A case can still throw an exception itself, call a failing method, or mishandle `null` input. Exhaustiveness only checks **label coverage**. You still need input validation, exception handling, and tests.

## 14. Checklist to verify whether a switch is exhaustive

When reviewing Java 21 code, ask in order:

1. **Is this an expression or a statement?** If it is an expression, exhaustiveness is mandatory. If it is a statement, is it an enhanced form (pattern/`case null`/new selector)?
2. **What is the static type of the selector?** `enum`, sealed interface/class, `Object`, open interface, record?
3. **Is there a `default`?** If yes, the switch is usually exhaustive under coverage rules; still check dominance and `null`.
4. **If there is no default, do the cases truly cover the selector type?** For enum: all constants. For sealed: all permitted type branches. For `Object`: a catch-all pattern. For record patterns: are components sufficiently covered?
5. **Do guards leave values uncovered?** `when` with a dynamic condition usually cannot replace a general branch.
6. **Is any case covered by an earlier case?** If so, a dominance error exists independently of exhaustiveness.
7. **How is `null` handled?** Is there `case null`, `case null, default`, explicit null rejection, or is NPE acceptable?
8. **Could libraries change between compile time and runtime?** If so, compile-time exhaustiveness does not replace binary compatibility testing.

Summary table:

| Java 21 scenario | Exhaustive? | Conclusion |
| --- | --- | --- |
| Expression on enum, listing all constants | Yes | No `default` needed |
| Expression on enum, missing a constant, no `default` | No | Compile-time error |
| Classic statement on enum, only one case | Not required | Compiles; other values may be skipped |
| Expression on `Object` with `case String` and `default` | Yes | Covers types other than `String` as well |
| Enhanced statement on `Object` with only `case String` | No | Compile-time error |
| Expression on sealed interface with all type patterns | Yes | Compiler proves all type branches are covered |
| Expression on open interface listing one implementation | No | Needs a branch covering the rest |
| Expression on record `Point(int,int)` with `case Point(int x,int y)` | Yes | Covers every non-`null` `Point` |
| Expression with only guarded pattern `case Integer i when i > 0` | No | Remaining values are unhandled |
| Expression with `default` but no `case null` | Yes for types | `null` can still cause `NullPointerException` |

## 15. Exercises and answers

### Exercise 1: missing enum constant

Given:

```java
enum Priority { LOW, MEDIUM, HIGH }
```

Is the following snippet exhaustive?

```java
static int weight(Priority p) {
    return switch (p) {
        case LOW    -> 1;
        case MEDIUM -> 2;
    };
}
```

**Answer:** No. This is a switch expression missing `HIGH`, so it causes a compile-time error. Adding `case HIGH -> 3;` makes the expression exhaustive.

### Exercise 2: classic statement

```java
static void show(Priority p) {
    switch (p) {
        case HIGH -> System.out.println("High");
    }
}
```

**Answer:** Compiles in Java 21. This is a classic switch statement on an enum, with no patterns or `case null`, so exhaustiveness is not required. For `LOW` or `MEDIUM`, the method prints nothing.

### Exercise 3: sealed hierarchy

Given:

```java
sealed interface Node permits Leaf, Branch {}
record Leaf(int value) implements Node {}
record Branch(Node left, Node right) implements Node {}
```

Write a switch expression counting direct children: `Leaf` returns 0, `Branch` returns 2.

**Answer:**

```java
static int childCount(Node node) {
    return switch (node) {
        case Leaf l   -> 0;
        case Branch b -> 2;
    };
}
```

This is exhaustive because `Node` permits only `Leaf` and `Branch` as direct implementations. Note that this does not automatically recurse through the tree, and `node == null` still causes an NPE without `case null`.

### Exercise 4: handling null

Consider:

```java
static String kind(Object o) {
    return switch (o) {
        case String s -> "S";
        default       -> "OTHER";
    };
}
```

- `kind(5)` → `"OTHER"`.
- `kind("Java")` → `"S"`.
- `kind(null)` → throws `NullPointerException`, not `"OTHER"`.

**Fix if you want `null` to return `"EMPTY"`:**

```java
static String kind(Object o) {
    return switch (o) {
        case null     -> "EMPTY";
        case String s -> "S";
        default       -> "OTHER";
    };
}
```

### Exercise 5: does a dynamic condition replace a general case?

```java
static String score(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n when n < 0 -> "NEGATIVE";
    };
}
```

**Answer:** Not exhaustive: `Integer.valueOf(0)` already fails to match either guard, not to mention non-`Integer` types. A clear fix is to add `case Integer n -> "ZERO";` after the two guarded branches and `default -> "OTHER";` for the remaining types.

### Exercise 6: designing a `switch` that alerts you when the domain expands

An application has `sealed interface Payment permits Cash, Card` and two corresponding record classes. You want the compiler to prompt the author to review payment routing logic when a `Transfer` type is added in source code. What should you do?

**Answer:** Use an **exhaustive switch expression with the two type patterns `case Cash c` and `case Card c`**, without adding `default` unless there is a clear business need. When updating `permits` and recompiling, the missing `Transfer` branch will be caught if no pattern covers it yet.

## 16. Conclusion

An **exhaustive switch** in Java is a `switch` whose selector type the compiler can prove is fully covered. Java 21 requires:

- **Every switch expression** must be exhaustive.
- **Every enhanced switch statement** must be exhaustive.
- **Classic switch statements** are not required to be exhaustive, preserving compatibility with legacy code.

Ways to achieve exhaustiveness include **`default`**, **all enum constants**, **all subtypes in a sealed hierarchy**, or a **catch-all pattern**. **Record patterns** can participate in proving coverage when component patterns are sufficient.

Especially remember: **exhaustiveness does not mean automatic `null` handling**, does not guarantee correct business logic, and does not prevent all runtime exceptions. Distinguish three questions: *are enough branches covered?* (exhaustiveness), *is any branch shadowed?* (dominance), and *how is null handled?* (null handling). Answering all three helps you write pattern switches that are safe, extensible, and maintainable.

## Official references

- [Java SE 21 Language Specification, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification, §14.11.2 — The Switch Block of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Java SE 21 Language Specification, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
