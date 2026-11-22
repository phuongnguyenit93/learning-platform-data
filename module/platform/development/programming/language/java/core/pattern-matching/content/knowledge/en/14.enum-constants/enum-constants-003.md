# Pattern types and enum types in the same switch — Java 21

## 1. When do you need to combine enum constants and type patterns?

An `enum` describes a set of named constant values, such as states `NEW`, `RUNNING`, and `DONE`. Pattern matching in `switch`, on the other hand, classifies values by **runtime type** or **structure**. Since Java 21, both approaches can appear in **the same switch block**:

~~~java
return switch (value) {
    case Status.NEW -> "NEW_CONSTANT";
    case Status s -> "OTHER_STATUS:" + s.name();
    case String text -> "TEXT:" + text;
    case null -> "NULL";
    default -> "OTHER";
};
~~~

This is an **excerpt** belonging to a method that takes `Object value`, requiring a suitable `enum Status` declaration. It expresses two different ideas:

- **`case Status.NEW`**: matches **the exact enum constant `Status.NEW`**, without declaring a pattern variable.
- **`case Status s`**: a **type pattern** that matches **all remaining constants of enum `Status`** after previous cases; it declares variable `s` of static type `Status` so `s.name()` can be called.
- **`case String text`**: classifies values of other types in the same switch.
- **`case null`** and `default`: decide how null and remaining values are handled.

Thus, “pattern types and enum types in the same switch” does not mean that an enum becomes a special kind of pattern. Rather, they are **two different kinds of valid labels**: an *enum constant case label* and a *case pattern*. The same enum type can appear either as an exact constant or as a type pattern matching all values of that type.

### Learning objectives

After this lesson, you will be able to:

1. Write switches over selectors of type `enum`, `Object`, or an interface with enum implementations.
2. Distinguish between `case NEW`, `case Status.NEW`, `case Status s`, and `case Status s when ...`.
3. Know when a **qualified enum constant** like `Status.NEW` is required, especially when the selector **does not have that enum as its static type**.
4. Order constant cases before general type patterns to avoid **dominance**, while recognizing guards that can change branch selection order.
5. Understand **switch compatibility**, pattern variable scope, `null`, `default`, and exhaustiveness.
6. Combine multiple enums implementing an interface/sealed interface with record patterns.
7. Identify compiler errors: constants incompatible with the selector, missing enum type name, duplicate cases, patterns dominating constants, invalidly combining constants with patterns, and missing branches.

**Version:** the sample code uses **Java 21+**, when pattern matching for `switch` and qualified enum constant syntax became standard features, without needing `--enable-preview`. Use JDK 21 or later and compile with `javac --release 21`.

## 2. First: how does an enum constant differ from a type pattern?

Suppose:

~~~java
enum Status {
    NEW, RUNNING, DONE, FAILED
}
~~~

There are four ways of writing labels that are easily confused:

| Case label | Label kind | Matching condition | Variable declared? |
| --- | --- | --- | --- |
| `case NEW` | Unqualified enum constant | Value is exactly `Status.NEW`, when the selector has an appropriate enum context | No |
| `case Status.NEW` | **Qualified** enum constant | Value is exactly `Status.NEW`, even when the selector is `Object` if compatible | No |
| `case Status s` | **Type pattern** | Non-null value with runtime type `Status` | Yes: `s` of type `Status` |
| `case Status s when s == Status.NEW` | **Guarded** type pattern | Matches `Status` and the boolean condition is true | Yes: `s` |

**An enum constant is not a pattern variable.** Writing `case Status.NEW` does not create a variable `NEW` for use in the rule body; it is a single enum constant. Conversely, `case Status s` creates variable `s` to read the state being processed:

~~~java
case Status s -> "STATUS:" + s.name();
~~~

A pattern variable is scoped to the label's guard (if any) and its corresponding rule/statement group; it does **not** leak into other cases.

**An enum type is a special class:** each enum class has a known set of constants, and all constants of the same enum are objects of that enum type. `case Status s` does not select a single constant; it checks the type of the value.

If the selector has type `Status`, you can use `case NEW` in the traditional enum switch style. However, if the selector is `Object`, you cannot simply write `case NEW` and expect the compiler to infer `Status.NEW`. Java 21 allows using the qualified name `case Status.NEW`.

## 3. Why is the static type of the selector the starting point?

For an expression:

~~~java
switch (expression) {
    // case labels
}
~~~

the compiler checks labels based on the **static type** of `expression`. This is the **switch compatibility** check in JLS `14.11.1:

- An **enum constant case** must belong to an enum whose type is assignment-compatible with the static type of the selector.
- A **type pattern** must be *applicable* to the static type of the selector.
- Integer/String constants have their own compatibility rules; having an `Object` selector does not mean every literal constant is accepted.
- `null` is only allowed when the selector has a reference type.

Three common selectors:

**Selector is the enum itself:**

~~~java
static String classify(Status status) {
    return switch (status) {
        case NEW -> "NEW";
        case RUNNING -> "RUNNING";
        case DONE -> "DONE";
        case FAILED -> "FAILED";
    };
}
~~~

This is an illustrative method (not including the enum declaration), where `Status` has all four constants as declared. The switch expression covers all enum constants, so `default` is not needed. However, passing `null` without `case null` will throw a `NullPointerException` at runtime.

**Selector is `Object`:**

~~~java
static String classify(Object value) {
    return switch (value) {
        case Status.NEW -> "NEW";
        case Status s -> "OTHER_STATUS:" + s;
        case String s -> "TEXT:" + s;
        case null -> "NULL";
        default -> "OTHER";
    };
}
~~~

These cases are **qualified enum constants** or **type patterns**. Using bare `case NEW` here would lack the necessary `Status` enum context.

**Selector is an interface implemented by enums:** Java 21 lets you use `case SomeEnum.VALUE` directly if that enum value is type-compatible with the interface selector. This is an important use case for qualified enum constants, instead of having to write `case SomeEnum e when e == SomeEnum.VALUE`.

## 4. Program 1: enum constant + enum type pattern + String in switch(Object)

Save the complete program as `MixedEnumObjectDemo.java`:

~~~java
public class MixedEnumObjectDemo {
    enum Status { NEW, RUNNING, DONE, FAILED }

    static String describe(Object value) {
        return switch (value) {
            case Status.NEW -> "NEW_CONSTANT";
            case Status.DONE -> "DONE_CONSTANT";
            case Status s when s.name().startsWith("FAIL") ->
                "FAIL_PATTERN:" + s;
            case Status s -> "OTHER_STATUS:" + s.name();
            case String text -> "TEXT:" + text;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Status.NEW));
        System.out.println(describe(Status.DONE));
        System.out.println(describe(Status.FAILED));
        System.out.println(describe(Status.RUNNING));
        System.out.println(describe("hello"));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac --release 21 MixedEnumObjectDemo.java
java MixedEnumObjectDemo
~~~

Exact output:

~~~text
NEW_CONSTANT
DONE_CONSTANT
FAIL_PATTERN:FAILED
OTHER_STATUS:RUNNING
TEXT:hello
NULL
OTHER
~~~

Tracing each path:

- `Status.NEW` and `Status.DONE` match their respective **constant labels** first.
- `Status.FAILED` does not match the two constants above; type pattern `Status s` matches, guard `s.name().startsWith("FAIL")` evaluates to `true`, yielding `FAIL_PATTERN:FAILED`.
- `Status.RUNNING` matches type pattern `Status` but fails the guard; the next **unguarded** `Status s` case handles it.
- The string `"hello"` is not a `Status` enum, so it matches `String text`.
- `null` is handled explicitly by `case null`.
- `42` is boxed into an `Integer`, does not match any of the earlier types, and goes to `default`.

**Key takeaway:** This is a **single switch** performing enum constant matching, pattern-based enum type checking, and other type checks. There is no need to nest a separate switch for the enum inside a long `if/else` chain.

### Guards and ordering

A guarded label:

~~~java
case Status s when s.name().startsWith("FAIL") -> "FAIL";
~~~

only evaluates the guard **after** the value matches type `Status`. Place prioritized constants and specific guarded cases **before** an unguarded `case Status s`. If you put the general `case Status s` first, subsequent constants of the same enum will be dominated.

## 5. Program 2: an enum selector can still combine constant cases and type patterns

Another misconception: “If the selector is already an `enum`, you can no longer use type patterns.” This is false in Java 21.

Save `EnumSelectorPatternDemo.java`:

~~~java
public class EnumSelectorPatternDemo {
    enum Level { LOW, MEDIUM, HIGH }

    static String decide(Level level) {
        return switch (level) {
            case LOW -> "LOW_CONSTANT";
            case Level value when value.ordinal() == 2 -> "HIGH_PATTERN";
            case Level value -> "REST:" + value;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(decide(Level.LOW));
        System.out.println(decide(Level.MEDIUM));
        System.out.println(decide(Level.HIGH));
        System.out.println(decide(null));
    }
}
~~~

~~~bash
javac --release 21 EnumSelectorPatternDemo.java
java EnumSelectorPatternDemo
~~~

Output:

~~~text
LOW_CONSTANT
REST:MEDIUM
HIGH_PATTERN
NULL
~~~

In this program:

1. The static type of the selector is `Level`, so `case LOW` written in traditional enum syntax is valid.
2. `case Level value when ...` is a guarded type pattern; if the enum value is `HIGH`, `ordinal() == 2` is true.
3. The unguarded `case Level value` matches all remaining `Level` values. Therefore, for `MEDIUM`, the result is `REST:MEDIUM`.
4. `case null` handles null separately. Type pattern `Level value` does not match null.

**Do not overuse `ordinal()` for real business logic.** `ordinal` depends on the enum declaration order; adding, removing, or reordering constants can change its meaning. The example above uses `ordinal()` to illustrate how a guard reads a pattern variable. In applications, if you need the `HIGH` state, prefer `case HIGH`, or use a stable domain property declared on the enum.

### When is a type pattern more useful than an enum constant?

- You want to group **many remaining constants** into a single rule without listing each constant individually.
- You need to call methods, read fields, or check complex conditions on the enum through a pattern variable.
- The selector is `Object` or an interface, and you want to handle an entire enum group by runtime type.
- You have a special branch for a specific constant, followed by a branch using a type pattern to handle the rest.

Conversely, when only distinguishing a single specific constant, `case Level.HIGH` or `case HIGH` is usually clearer than `case Level x when x == Level.HIGH`.

## 6. Qualified enum constants: why does Java 21 support them?

Before Java 21's new syntax, enum constant labels in a switch were tightly coupled to selectors whose static type was that exact enum. With a selector of an interface type that has **multiple implementing enums**, that syntax was not flexible enough.

Java 21 allows writing qualified enum constant names such as:

~~~java
case StandardEvent.OPEN -> "STANDARD_OPEN";
case SpecialEvent.ALERT -> "SPECIAL_ALERT";
~~~

inside a switch whose selector has an interface type implemented by those two enums. Both enums can contain a constant named `OPEN`, yet `StandardEvent.OPEN` and `SpecialEvent.OPEN` are **two different objects of two different enum types**.

**Why must it be qualified?** A selector of type interface or `Object` does not identify a single enum class as the context for `OPEN`. Writing `StandardEvent.OPEN` removes ambiguity and lets the compiler check whether that enum type is compatible with the selector.

Conversely, with a selector directly of type `StandardEvent`, both forms:

~~~java
case OPEN -> "OPEN";
case StandardEvent.CLOSE -> "CLOSE";
~~~

can be valid as separate labels in an appropriate switch. You may not declare **the same constant** in both forms in the same switch (e.g., `case OPEN` and `case StandardEvent.OPEN`); that is still a **duplicate case label**.

## 7. Program 3: multiple enums + record in a sealed-interface switch

Save `SealedEnumMixedDemo.java`:

~~~java
sealed interface Event permits StandardEvent, SpecialEvent, TextEvent {}

enum StandardEvent implements Event { OPEN, CLOSE }
enum SpecialEvent implements Event { OPEN, ALERT }
record TextEvent(String message) implements Event {}

public class SealedEnumMixedDemo {
    static String render(Event value) {
        return switch (value) {
            case StandardEvent.OPEN -> "STANDARD_OPEN";
            case SpecialEvent.ALERT -> "SPECIAL_ALERT";
            case StandardEvent e -> "STANDARD:" + e.name();
            case SpecialEvent e -> "SPECIAL:" + e.name();
            case TextEvent(var message) -> "TEXT:" + message;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(render(StandardEvent.OPEN));
        System.out.println(render(StandardEvent.CLOSE));
        System.out.println(render(SpecialEvent.ALERT));
        System.out.println(render(SpecialEvent.OPEN));
        System.out.println(render(new TextEvent("hi")));
        System.out.println(render(null));
    }
}
~~~

~~~bash
javac --release 21 SealedEnumMixedDemo.java
java SealedEnumMixedDemo
~~~

Output:

~~~text
STANDARD_OPEN
STANDARD:CLOSE
SPECIAL_ALERT
SPECIAL:OPEN
TEXT:hi
NULL
~~~

Analysis:

- `Event` is a **sealed interface** permitting only three direct implementations in the example: two enums and one record.
- `StandardEvent.OPEN` and `SpecialEvent.ALERT` are **case constants**, targeting specific constants.
- `case StandardEvent e` and `case SpecialEvent e` are **type patterns** for the remaining enum constants of each respective type not already matched by earlier labels.
- `case TextEvent(var message)` is a **record pattern**, extracting the `message` component of the record object.
- `case null` handles `null` explicitly.

This switch expression **does not need `default`** because the compiler can prove a branch exists for every permitted subtype of the sealed interface: `StandardEvent`, `SpecialEvent`, and `TextEvent` all have general case patterns. The `null` label adds the null-handling path according to the contract.

**Why aren't two constants both named OPEN considered duplicates?** They belong to different enum classes: `StandardEvent.OPEN` and `SpecialEvent.OPEN` are not equal and do not have the same type. Writing the qualified name makes both the type and the matched value explicit.

### When is a sealed interface beneficial?

If a domain has a fixed set of event variants, a sealed interface lets the compiler determine the permitted set of subtypes. A switch can combine:

- **Enum constants** for specific state variants that need priority.
- **Enum type patterns** for all remaining states of each enum.
- **Record patterns** for other structured data.
- **Case null** if you want to handle null explicitly.

If you change the permitted set of subtypes, you need to recompile and check the affected switches. You should not add `default` just to mask gaps in classification design when the goal is compiler-verified exhaustiveness.

## 8. Program 4: with an enum selector, qualified and unqualified labels can be mixed

Save `QualifiedEnumConstantsDemo.java`:

~~~java
public class QualifiedEnumConstantsDemo {
    enum Basic { RED, GREEN, BLUE }

    static String classify(Basic color) {
        return switch (color) {
            case Basic.RED -> "R";
            case GREEN -> "G";
            case BLUE -> "B";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(Basic.RED));
        System.out.println(classify(Basic.GREEN));
        System.out.println(classify(Basic.BLUE));
    }
}
~~~

~~~bash
javac --release 21 QualifiedEnumConstantsDemo.java
java QualifiedEnumConstantsDemo
~~~

Output:

~~~text
R
G
B
~~~

This shows that in Java 21, choosing the qualified or unqualified form often depends on the selector's type context and desired clarity. `case Basic.RED` and `case RED` refer to the exact same `RED` constant when the selector is `Basic`; they are **not two different values**.

All three enum constants are listed, so the switch expression is exhaustive without `default`. However, **there is no `case null`**, so `classify(null)` will throw a `NullPointerException` at runtime.

### Distinguishing null from exhaustiveness

- **Exhaustiveness by enum constants**: listing all constant values of an enum is enough for the compiler to accept a switch expression without `default`.
- **Null**: is not an enum constant; Java has separate rules for it. A switch that is exhaustive over constants can still throw on null.
- **Default**: if you omit an enum constant in a switch expression, `default` can provide coverage, but it does not automatically handle null the way you might expect.

Do not treat `case null` as syntactically mandatory in every switch; only add it when you need to handle null with a dedicated result branch.

## 9. Program 5: grouping multiple enum constants in the same case

If multiple enum constants share the same business meaning, you can place multiple **case constants** in a single label.

Save `EnumGroupedLabelsDemo.java`:

~~~java
public class EnumGroupedLabelsDemo {
    enum Status { NEW, IN_PROGRESS, DONE, BLOCKED }

    static String stage(Object value) {
        return switch (value) {
            case Status.NEW, Status.IN_PROGRESS -> "ACTIVE";
            case Status.DONE, Status.BLOCKED -> "INACTIVE";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(stage(Status.NEW));
        System.out.println(stage(Status.IN_PROGRESS));
        System.out.println(stage(Status.DONE));
        System.out.println(stage(Status.BLOCKED));
        System.out.println(stage(null));
        System.out.println(stage("x"));
    }
}
~~~

~~~bash
javac --release 21 EnumGroupedLabelsDemo.java
java EnumGroupedLabelsDemo
~~~

Output:

~~~text
ACTIVE
ACTIVE
INACTIVE
INACTIVE
NULL
OTHER
~~~

This grouping works because `Status.NEW`, `Status.IN_PROGRESS`, `Status.DONE`, and `Status.BLOCKED` are all **case constants**. No pattern variables need to be initialized differently across paths.

**However, you cannot mix an enum constant and a type pattern in the same label:** the following intentionally fails to compile:

~~~java
case Status.NEW, Status s -> "VALUE"; // COMPILE ERROR
~~~

Java 21 reports `invalid case label combination`. Instead, use two **separate** labels:

~~~java
case Status.NEW -> "NEW";
case Status s -> "OTHER_STATUS:" + s;
~~~

The snippets above assume a switch with an appropriate selector and an already-declared `Status` enum; they are illustrative snippets, not standalone programs. If you want multiple constants to share one branch, group **constant with constant** rather than adding a variable-declaring pattern to the same label.

## 10. Ordering and dominance: constants first, general patterns after

A common mistake is placing a broad type pattern before an enum constant of the same type:

~~~java
case Color c -> "COLOR";
case Color.RED -> "RED"; // COMPILE ERROR: dominated
~~~

If the selector is compatible, `case Color c` already matches **every constant of Color**, including `Color.RED`. The compiler rejects the `Color.RED` label afterward because it can never be selected.

The right way:

~~~java
case Color.RED -> "RED";
case Color c -> "OTHER_COLOR:" + c.name();
~~~

This follows the principle “**specific values first, general types after**”. It applies equally to `Object` selectors, interfaces, or the enum type itself when the type pattern is valid.

### Dynamic guards do not necessarily dominate a subsequent constant

An ordering that is allowed but can be surprising:

~~~java
case Status s when s == Status.NEW -> "GUARDED_NEW";
case Status.NEW -> "CONSTANT_NEW";
case Status s -> "OTHER";
~~~

This is an **excerpt** with a suitable `Status`. The guard `s == Status.NEW` is a dynamic condition, so Java does not treat it like an unguarded pattern for dominance. For `Status.NEW`, the first guard is true and the subsequent constant case **will not execute**. The code still compiles, but it easily causes logic bugs if a developer assumes constants always have higher priority.

Complete program `GuardedEnumConstantDemo.java`:

~~~java
public class GuardedEnumConstantDemo {
    enum Status { NEW, ACTIVE, DONE }

    static String select(Status s) {
        return switch (s) {
            case Status value when value == Status.NEW -> "GUARDED_NEW";
            case NEW -> "CONSTANT_NEW";
            case ACTIVE -> "ACTIVE";
            case Status value -> "REST:" + value;
            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(select(Status.NEW));
        System.out.println(select(Status.ACTIVE));
        System.out.println(select(Status.DONE));
    }
}
~~~

~~~bash
javac --release 21 GuardedEnumConstantDemo.java
java GuardedEnumConstantDemo
~~~

Output:

~~~text
GUARDED_NEW
ACTIVE
REST:DONE
~~~

For `Status.NEW`, the earlier guard selected the `GUARDED_NEW` branch, so the later `NEW` case is not chosen, even though the syntax is valid. If the intent is to always prioritize the `NEW` constant, place `case NEW` before the guarded pattern.

If a guard is the **constant expression `true`**, Java treats that label as unguarded when checking dominance. Placing `case Status s when true` before `case Status.NEW` will cause a dominance error just like an unguarded type pattern. Conversely, a guard that is the constant expression `false` is not allowed in a case label at all.

### Code organization tips

A practical ordering when combining enums and patterns:

1. Specific enum constants that need priority, e.g., `case Status.NEW`.
2. Guarded type patterns for states with extra conditions, e.g., `case Status s when s.name().startsWith("FAIL")`.
3. Unguarded type pattern for the remaining constants, e.g., `case Status s`.
4. Patterns of other types and an appropriate fallback.

This is a **readability and maintainability strategy**, not an automatic priority rule: the actual evaluation order is always the order of the labels in code.

## 11. Type compatibility: an enum constant not belonging to the selector is rejected

Every qualified enum constant must still be **assignment-compatible** with the static type of the selector.

The following **intentionally fails to compile**:

~~~java
enum Color { RED }
enum Size { SMALL }

static String test(Size value) {
    return switch (value) {
        case Color.RED -> "RED"; // ERROR: Color is not Size
        default -> "OTHER";
    };
}
~~~

If this code is placed inside a class, the compiler reports an error like:

~~~text
error: incompatible types: Color cannot be converted to Size
~~~

Using a qualified type name **does not bypass** Java's type checking. With a `Size` selector, a `Color.RED` constant is not compatible and therefore cannot be a case label.

Conversely, with an `Object` selector, `Color.RED` belongs to a reference type assignable to `Object`; thus it can be used as in `MixedEnumObjectDemo`. With an interface selector, the enum must implement that interface (or be in an appropriate assignment-compatible relationship).

### Is an unqualified constant enough for an Object selector?

An example that **intentionally fails to compile**:

~~~java
enum Color { RED, BLUE }

static String test(Object value) {
    return switch (value) {
        case RED -> "RED"; // No Color enum context
        default -> "OTHER";
    };
}
~~~

The compiler reports `cannot find symbol: variable RED` in this example. Change `case RED` to `case Color.RED`.

Do not use `import static` to try to work around enum context before understanding label kinds: the clear, unambiguous way for a switch over `Object` or an interface is a qualified enum constant.

## 12. Duplicate case constants: the same enum constant may appear only once

In a switch over `Color`, the two labels:

~~~java
case RED -> "A";
case Color.RED -> "B";
~~~

are **duplicates**, even though one omits the enum name and the other includes it. `javac --release 21` reports:

~~~text
error: duplicate case label
~~~

Similarly, `case RED, RED` also duplicates the constant. The compiler distinguishes constants by **enum value**, not by how short or long the label is written.

Unlike duplicate constants, two different enum classes can both declare `OPEN`; they are **two distinct values** and can appear together in a switch over an interface or `Object`, provided each enum constant is compatible with the selector.

An enum constant label also does not declare a pattern variable; if you want to read properties on the matched constant without hardcoding extra operations, use a general case pattern of the same type in another branch.

## 13. Exhaustiveness: enum selector, Object selector, and sealed selector

### 13.1. Enum selector

Given:

~~~java
enum Status { NEW, RUNNING, DONE }
~~~

a switch expression covering **all** enum constants:

~~~java
return switch (status) {
    case NEW -> "N";
    case RUNNING -> "R";
    case DONE -> "D";
};
~~~

is exhaustive if `status` has type `Status`. No `default` is needed. However, if only `NEW` and `RUNNING` are listed, the compiler reports:

~~~text
error: the switch expression does not cover all possible input values
~~~

An unguarded `case Status s` pattern can match the unlisted enum constants and help ensure coverage, provided labels are not dominated.

### 13.2. Object selector

With `switch (Object value)`, having only `Status.NEW` and `Status.DONE` is **not exhaustive** because `value` can still be any other class. You must have `default`, an appropriate general type pattern, or another Java-accepted form of coverage.

The `MixedEnumObjectDemo` example uses `default` because the selector is `Object` and many types are not listed.

### 13.3. Sealed interface selector

If the selector has a sealed interface type and the switch contains case patterns covering all permitted implementations, the compiler can prove exhaustiveness **without `default`**. The `SealedEnumMixedDemo` example uses `StandardEvent e`, `SpecialEvent e`, and `TextEvent(...)` to cover the three subtypes, while enum constant cases handle special constants.

**Note:** listing a few enum constants from each subtype does not necessarily cover the entire subtype. If you want exhaustiveness using enum constants, you must cover cases according to the JLS rules; using an unguarded type pattern for each enum subtype is usually simpler.

### 13.4. Null

Even when a switch expression is considered exhaustive at compile time, passing `null` can still cause it to throw a `NullPointerException` if there is no appropriate null-handling label. `default` does not automatically handle null as a normal value in a pattern switch.

Therefore, decide on `case null` according to the API contract; do not confuse it with any enum constant.

## 14. Both switch statements and switch expressions work together

Use a switch expression when you need **a value**:

~~~java
String result = switch (value) {
    case Status.NEW -> "NEW";
    case Status s -> "STATUS:" + s;
    case null -> "NULL";
    default -> "OTHER";
};
~~~

Use a switch statement when you need to perform **actions**:

~~~java
switch (value) {
    case Status.NEW -> System.out.println("NEW");
    case Status s -> System.out.println("STATUS:" + s);
    case null -> System.out.println("NULL");
    default -> System.out.println("OTHER");
}
~~~

Both snippets are excerpts requiring an `enum Status` declaration and an `Object value` variable inside a method.

With arrow rules `->`, there is no fall-through. If you use the colon form `case ...:`, you must manage `break` or `return`; Java also restricts falling through **into** a pattern label that declares a variable, because that variable might remain uninitialized.

**A Java 21 note:** a switch statement is an *enhanced switch statement* when it contains a pattern, a null label, or a selector of certain broad reference types (such as `Object`); in that case it must be exhaustive under Java 21's rules. Do not confuse this with a traditional enum switch statement without patterns, which retains certain backward-compatibility rules for exhaustiveness.

## 15. Common errors and how to fix them

The following snippets illustrate intentionally erroneous situations. Error conclusions have been verified against `javac --release 21`.

| Situation | Symptom/error | How to fix |
| --- | --- | --- |
| `case RED` in `switch(Object)` without an enum context | `cannot find symbol: variable RED` | Use `case Color.RED` |
| `case Color.RED` in `switch(Size)`, two unrelated enums | `Color cannot be converted to Size` | Only use enum constants assignment-compatible with the selector |
| `case Color c` before `case Color.RED` | `dominated by a preceding case label` | Put constants before general type patterns |
| `case RED` and `case Color.RED` in the same switch | `duplicate case label` | Use only one label for that constant |
| `case RED when true` | Syntax error / guard cannot attach directly to a constant | Use `case RED` or `case Color c when ...` |
| `case Color.RED, Color c` | `invalid case label combination` | Split into two separate case labels |
| Enum switch expression omits a constant without a fallback | `switch expression does not cover all possible input values` | List all constants or add a valid covering branch |
| General type pattern placed before a constant of the same enum | Constant is dominated | Move specific constants first |
| Assuming `default` will catch null | May throw `NullPointerException` | Write `case null` if you want to handle it |
| Using `ordinal()` to identify states long-term | Fragile when enum declaration order changes | Use the constant name or a stable property |

### Example 1 — Constant after general pattern is dominated

~~~java
static String invalid(Object value) {
    return switch (value) {
        case Color c -> "COLOR";
        case Color.RED -> "RED"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

This snippet is inside a class with `enum Color { RED, BLUE }`. Case `Color c` already covers `Color.RED`.

### Example 2 — Guarded label only attaches to a pattern

~~~java
static String invalid(Color value) {
    return switch (value) {
        case RED when true -> "RED"; // COMPILE ERROR
        default -> "OTHER";
    };
}
~~~

Replace with:

~~~java
case RED -> "RED";
~~~

If an extra condition is needed, use:

~~~java
case Color c when customCondition(c) -> "MATCH";
~~~

Here `customCondition(Color)` is an illustrative application-defined boolean method, not a built-in Java Core API.

### Example 3 — Constant and type pattern cannot share a label

~~~java
case Color.RED, Color c -> "COLOR"; // COMPILE ERROR
~~~

Replace with:

~~~java
case Color.RED -> "RED";
case Color c -> "OTHER_COLOR";
~~~

Java only allows grouping multiple **case constants** in one label under the corresponding syntax. A pattern introducing a variable cannot be mixed with a constant in the same label.

## 16. Self-check exercises and answers

### Exercise 1 — Reading the output of switch(Object)

Given `enum State { NEW, DONE }`:

~~~java
static String inspect(Object x) {
    return switch (x) {
        case State.NEW -> "NEW";
        case State s -> "STATE:" + s;
        case String s -> "TEXT";
        case null -> "NULL";
        default -> "OTHER";
    };
}
~~~

Predict the results of `inspect(State.NEW)`, `inspect(State.DONE)`, `inspect("x")`, `inspect(null)`, and `inspect(3)`.

**Answer:** `NEW`, `STATE:DONE`, `TEXT`, `NULL`, `OTHER`. The constant case catches `NEW` specifically, the type pattern `State s` catches the remaining constant, the `String` pattern catches the string, and `default` catches the integer.

### Exercise 2 — Fixing a constant name in an Object selector

In `switch(Object value)`, why is:

~~~java
case OPEN -> "OPEN";
~~~

wrong when `OPEN` is an enum constant of `EventType`?

**Answer:** The `Object` selector does not provide an enum context to infer `EventType.OPEN`. Write `case EventType.OPEN -> "OPEN";` if the enum constant is compatible with the selector.

### Exercise 3 — Ordering cases correctly

Reorder the following two cases so that `Color.RED` can still be handled specifically:

~~~java
case Color c -> "COLOR";
case Color.RED -> "RED";
~~~

**Answer:**

~~~java
case Color.RED -> "RED";
case Color c -> "COLOR";
~~~

### Exercise 4 — Two enums with identically named constants

Suppose `enum A implements Event { OPEN }` and `enum B implements Event { OPEN }`, where `Event` is a valid interface. Are `case A.OPEN` and `case B.OPEN` duplicates?

**Answer:** No. The two constants belong to different enum types, and both can be valid in a switch with selector `Event` if assignment-compatible. Write qualified names to distinguish them clearly.

### Exercise 5 — Exhaustiveness with an enum selector

Given `enum Mode { START, STOP, PAUSE }`, is a switch expression with only `case START` and `case STOP` valid without `default`?

**Answer:** Not exhaustive because `PAUSE` is omitted. You can add `case PAUSE`, `default`, or an appropriate pattern that matches the remaining constants.

### Exercise 6 — Guard on an enum type pattern

How can the following compile yet return an unexpected result?

~~~java
case Status s when s == Status.NEW -> "GUARD";
case Status.NEW -> "CONST";
case Status s -> "OTHER";
~~~

**Answer:** For `Status.NEW`, the first guard is true so the result is `GUARD`; the constant case afterward does not run. If you want the constant to take precedence, move `case Status.NEW` before it.

### Exercise 7 — Null and default

If a switch expression lists all enum constants but has no `case null`, what can happen when `null` is passed? Does adding `default` automatically turn null into an enum constant?

**Answer:** Runtime may throw a `NullPointerException`; `null` is not an enum constant. `default` does not automatically handle null the way you might expect in a pattern switch. Write `case null` if the API needs to return a result instead of throwing.

### Exercise 8 — Combining a constant and a pattern

Can you write:

~~~java
case State.NEW, State s -> "STATE";
~~~

?

**Answer:** No, Java 21 reports `invalid case label combination`. You can group multiple constants like `case State.NEW, State.DONE`, or split the constant and the pattern into two independent branches.

## 17. Checklist when reviewing a switch combining enums and patterns

Before finishing, check:

1. Is the static type of the selector a **specific enum**, `Object`, or an interface?
2. For an enum constant, does the label need to be qualified (`Status.NEW`) or can it be unqualified (`NEW`)?
3. Is every enum constant **assignment-compatible** with the selector?
4. Do you need to match **one constant** or **all constants of the enum type**? Use a constant or a type pattern accordingly.
5. Are special constants placed **before** unguarded type patterns of the same type?
6. Does the guard return a boolean and use the pattern variable within its valid scope?
7. Do any two cases duplicate the same constant, including one qualified form and one unqualified form?
8. Are you invalidly combining a constant with a pattern in the same label?
9. If the selector is a sealed interface, do the cases cover all permitted subtypes?
10. If the selector is an enum, does the switch expression cover all constants or have an appropriate fallback?
11. Is `null` handled according to the API contract?
12. Are there real tests for enum values where multiple cases could match (constant + guarded pattern + type pattern)?
13. Are you compiling with Java 21+ and not accidentally relying on old Java 17–20 preview rules?

**Remember:** `case EnumType.VALUE` checks **a single enum constant**; `case EnumType variable` checks **the enum type** and introduces a pattern variable. Java 21 allows combining them in the same switch over an enum, `Object`, or a compatible interface. **Label ordering and coverage determine both compile-time validity and runtime behavior.**

### References

- Oracle Java 21 — Pattern Matching for switch, section *Qualified enum Constants as case Constants*: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- JLS Java SE 21 `14.11.1 — Switch Blocks, compatibility, dominance, enum case labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1
- JLS Java SE 21 `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441