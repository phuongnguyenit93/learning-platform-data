# Java 17 Boundary: Do Not Treat Pattern Switch Preview as Standard Syntax

In Java 17, **switch expression** is an **official, finalized** language feature: you can use `switch` to produce values, write branches using `case ... ->`, and use `yield` when a branch needs multiple statements. However, **pattern matching for switch** — which enables branches such as `case String s ->` or `case Integer n ->` — is only at the **preview stage in Java 17**. Both features involve `switch`, yet they have different statuses.

Distinguishing these properly helps you write code that runs on Java 17 by default, avoid relying on experimental flags, and avoid mistaking modern Java 21 syntax for official Java 17 syntax.

> **Lesson rule:** When writing Java 17 code for standard projects, use only **standard switch expressions**; pattern switch examples here are explicitly marked **preview** and are shown solely to identify version boundaries. If you want pattern matching for switch as official syntax, use JDK 21 or later with its corresponding documentation.

## 1. Two similarly named features with different statuses

| Feature | Switch expression | Pattern matching for switch |
|---|---|---|
| JEP finalizing the feature | [JEP 361](https://openjdk.org/jeps/361) | [JEP 441](https://openjdk.org/jeps/441) |
| First release where finalized | **Java 14** | **Java 21** |
| Status in Java 17 | **Final (standard)** | **Preview**, per [JEP 406](https://openjdk.org/jeps/406) |
| Purpose | Write `switch` expressions that produce values and concise branch syntax | Match types/values by pattern, bind variables, and extend dispatch |
| Typical example | `case "A" -> 10;` | `case String s -> s.length();` |
| Flag in JDK 17 | **Does not require** `--enable-preview` | Must enable `--enable-preview` when compiling and running |
| Use in stable Java 17 code | Yes | Should not be assumed as stably supported syntax |

**LTS does not alter individual feature statuses.** Java 17 is an LTS release, but that does not mean every feature shipped in JDK 17 is finalized. A single JDK can simultaneously include finalized features and preview features.

The most important distinguishing clue is **what immediately follows `case`**:

~~~java
// FINAL in Java 17: matches String constant.
case "READY" -> "Ready";

// FINAL in Java 17: groups constant labels.
case "NEW", "PENDING" -> "Unprocessed";

// PREVIEW in Java 17: matches type pattern and binds variable.
case String text -> text.length();
~~~

The `->` arrow does **not** make syntax a preview feature. It is the **type pattern** like `String text` that belongs to pattern matching for switch.

## 2. What can standard switch expressions do in Java 17?

In Java 17, you can use `switch` as **an expression that returns a value**:

~~~java
static String describeStatus(String status) {
    return switch (status) {
        case "NEW" -> "Newly created";
        case "PROCESSING" -> "Processing";
        case "DONE" -> "Completed";
        default -> "Unknown";
    };
}
~~~

Each branch selects a result expression. The value produced by that branch becomes the value of the whole `switch expression` and is returned from the method.

### 2.1. Distinguishing switch expression and switch statement

A **Switch statement** handles control flow and performs actions:

~~~java
static void printStatus(String status) {
    switch (status) {
        case "NEW" -> System.out.println("Newly created");
        case "DONE" -> System.out.println("Completed");
        default -> System.out.println("Other status");
    }
}
~~~

A **Switch expression** is used where a value is required:

~~~java
static String statusLabel(String status) {
    String label = switch (status) {
        case "NEW" -> "Newly created";
        case "DONE" -> "Completed";
        default -> "Other status";
    };

    return label;
}
~~~

Both can use `->` branches in Java 17. The main difference is that **a switch expression must produce a result**; a switch statement does not.

### 2.2. Grouping multiple constants in a single branch

~~~java
static boolean isWeekend(int dayOfWeek) {
    return switch (dayOfWeek) {
        case 6, 7 -> true;
        case 1, 2, 3, 4, 5 -> false;
        default -> throw new IllegalArgumentException(
                "Day of week must be from 1 to 7");
    };
}
~~~

The list `case 6, 7` is a set of **constant labels**, not pattern matching. This syntax is a standard part of switch expressions/switch rules in Java 17.

### 2.3. Using `yield` when a branch has multiple statements

If a branch needs validation or calculation before producing a result, use a block and `yield`:

~~~java
static int shippingFee(String region, int weightKg) {
    return switch (region) {
        case "LOCAL" -> 10_000;

        case "NATIONAL" -> {
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                        "Weight must be greater than 0");
            }

            int baseFee = 20_000;
            int extraFee = Math.max(0, weightKg - 1) * 5_000;
            yield baseFee + extraFee;
        }

        default -> throw new IllegalArgumentException(
                "Unsupported region: " + region);
    };
}
~~~

Inside the `"NATIONAL"` branch block, `yield baseFee + extraFee;` **returns a value to the switch expression**, rather than exiting the enclosing method. `throw` is permitted because an error branch ends by throwing an exception instead of returning a value.

The `yield` syntax became final in Java 14 alongside switch expressions. Preview does not need to be enabled in Java 17.

### 2.4. `case ... :` can still be used in a switch expression

Colon-style branches can also appear inside a switch expression, provided you supply the result via `yield`:

~~~java
static String gradeLabel(char grade) {
    return switch (grade) {
        case 'A':
            yield "Excellent";
        case 'B':
            yield "Good";
        default:
            yield "Needs effort";
    };
}
~~~

While valid, the `->` form is usually easier to read when each branch produces a single result. In modern Java code, prefer `->` unless there is a clear reason to use `:` branch groups.

### 2.5. Standard supported selector types

With **non-preview** syntax in Java 17, the expression inside `switch (...)` can belong to these groups:

- `byte`, `short`, `char`, `int` along with their corresponding wrappers (`Byte`, `Short`, `Character`, `Integer`).
- `String`.
- An `enum` type.

Example:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}

static int priorityScore(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case MEDIUM -> 2;
        case HIGH -> 3;
    };
}
~~~

In this example, `default` is unnecessary because every constant of `Priority` is listed at compile time. Java also generates a safeguard if the runtime set of enum constants mismatches compile time.

**Do not assume a selector of type `Object` or an arbitrary interface is supported in non-preview Java 17 switch.** Switching on broad object types and using type patterns are extensions of pattern matching for switch.

## 3. Switch expressions must cover all cases

Because a switch expression must produce a value or complete abruptly with an exception, Java needs to prove its branches **cover all possible values** (*exhaustiveness*).

### 3.1. With `String`, `default` is usually needed

~~~java
static int statusCode(String status) {
    return switch (status) {
        case "NEW" -> 1;
        case "DONE" -> 2;
        default -> -1;
    };
}
~~~

If `default` is omitted and only two constant labels are written, the expression fails to cover infinitely many other possible `String` values, so compilation fails.

### 3.2. With an enum, all constants can be listed

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN
}

static String action(TrafficLight light) {
    return switch (light) {
        case RED -> "Stop";
        case YELLOW -> "Prepare";
        case GREEN -> "Go";
    };
}
~~~

This is an example of **official switch expression exhaustiveness** in Java 17. Pattern matching for switch is not needed.

When using enums, omitting `default` helps the compiler detect if you add a new enum constant and recompile the switch code without handling that constant. Conversely, if compatibility with unexpected values is a specific requirement, you can design a default branch according to the application contract.

### 3.3. Do not confuse enum exhaustiveness with sealed-pattern switch

**Sealed classes/interfaces are finalized in Java 17**, yet the following syntax is a type pattern inside `switch`, so it is **still preview in Java 17**:

~~~java
// TO RECOGNIZE PREVIEW — do not use as a standard Java 17 example.
//
// sealed interface Outcome permits Success, Failure {}
// record Success(String data) implements Outcome {}
// record Failure(String reason) implements Outcome {}
//
// static String describe(Outcome outcome) {
//     return switch (outcome) {
//         case Success s -> s.data();
//         case Failure f -> f.reason();
//     };
// }
~~~

Having `sealed` and `record` in Java 17 **does not automatically make** pattern switch on those two types finalized syntax. When handling type branches in regular Java 17 code, use `instanceof` pattern matching combined with `if`, as shown in the next section.

## 4. What is pattern switch in Java 17 and why distinguish it?

**Pattern matching for switch** extends `switch` to test data types, bind pattern variables, and handle more complex type structures. This mechanism first appeared in **preview in JDK 17** via [JEP 406](https://openjdk.org/jeps/406).

Example for **recognizing preview syntax in Java 17**:

~~~java
// ONLY ILLUSTRATES Java 17 PREVIEW SYNTAX.
// Do not put into the Java17SwitchDemo file in the practice section.
//
// static String describe(Object value) {
//     return switch (value) {
//         case String text -> "String: " + text;
//         case Integer number -> "Number: " + number;
//         default -> "Other type";
//     };
// }
~~~

In the snippet above:

1. `switch` accepts `Object` as a selector. This extended capability is tied to pattern matching for switch in Java 17.
2. `case String text` is a **type pattern**: instead of comparing against a string constant, it checks whether the value is a `String`.
3. `case Integer number` does the same for `Integer`.
4. `text` and `number` are **pattern variables**, scoped only to the matching branch.

This is an example of **syntax shipped in the JDK 17 distribution that is not part of the default finalized feature set**. To use it in an application, you would have to enable preview at both compile time and runtime.

### 4.1. Why should the example above not be taught as standard switch expression syntax?

If learners copy it directly into a Java 17 project and simply run:

~~~bash
javac --release 17 SomeFile.java
~~~

the compiler rejects the preview pattern switch. Learners may mistakenly think their JDK is misconfigured or that `switch expression` is unsupported, when the real cause is **the code using a different preview feature**.

The accurate explanation is:

- Java 17 **has finalized switch expressions**, including `case "VALUE" -> result` and `yield`.
- Java 17 **has pattern matching for switch in preview**, such as `case String s -> ...`.
- An example containing both a `switch expression` and a `type pattern` is not finalized merely because it uses `switch`; you must inspect **the specific syntax of each branch**.

### 4.2. Status in later Java versions

Pattern matching for switch remained in preview across Java 18–20 and was **finalized in Java 21** under [JEP 441](https://openjdk.org/jeps/441).

Therefore, writing a type pattern like:

~~~java
case String text -> text.length();
~~~

can be used in standard Java 21 `switch` when placed in a valid context and structure. However, **do not assume every detail of the Java 17 preview was kept unchanged**: the language adjusted several rules and syntax forms during stabilization.

An easily confused example is **guarded patterns**: the syntax for guard conditions changed during the preview cycle. When working with Java 21+, consult the grammar documentation for the target version; do not blindly carry Java 17 preview patterns into newer code.

## 5. Distinguishing types of `case` in Java 17

All using `->`, the following branches have fundamentally different natures:

| Branch | Status in Java 17 | Explanation |
|---|---|---|
| `case 1 -> "One";` | Final | Matches integer constant |
| `case 'A' -> "A";` | Final | Matches character constant |
| `case "NEW" -> "New";` | Final | Matches string constant |
| `case "NEW", "DRAFT" -> "Incomplete";` | Final | Multiple constants in one branch |
| `case HIGH -> 3;` with enum selector | Final | Matches enum constant |
| `case String s -> s.length();` | **Preview** | Type pattern, binds variable `s` |
| `case Integer n -> n.intValue();` | **Preview** | Type pattern, binds variable `n` |
| `case null -> 0;` | **Preview** | `null` label introduced with Java 17's preview pattern switch mechanism |
| `case null, default -> 0;` | **Preview** | Extended syntax handling null in pattern switch |
| `default -> "Other";` | Final | Default branch |

Specifically, **`case "hello"` and `case String s` are completely different**:

- `case "hello"` compares against **a String constant value**. Usable in standard Java 17.
- `case String s` checks **the object's type** and introduces variable `s` into the branch's scope. This is preview pattern switch in Java 17.

Keep in mind:

~~~text
switch expression with constant cases -> final in Java 17
                          |
                          +--> case "OK" -> 1        [final]
                          +--> case 1, 2 -> 10       [final]
                          +--> case HIGH -> 3        [final, with enum]
                          +--> block { yield ...; }  [final]

pattern matching for switch in Java 17 -> preview
                          |
                          +--> case String s -> ...   [preview]
                          +--> case Integer n -> ...  [preview]
                          +--> case null -> ...       [preview]
~~~

## 6. How to dispatch on object types **without preview** in Java 17

If the business requirement is **handling objects based on their runtime type**, use **pattern matching for `instanceof`**, which has been standard since Java 16 (JEP 394).

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String: " + text;
    }
    if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    if (value == null) {
        return "Null value";
    }
    return "Other type";
}
~~~

The snippet above works with `javac --release 17` without enabling preview. It achieves similar results to the pattern switch example while relying exclusively on standard Java 17 syntax.

### 6.1. When cases are determined by enum values or String constants

When you already have a known set of constants to branch on, a standard **switch expression** is usually clearer and shorter:

~~~java
enum ShipmentStatus {
    CREATED, IN_TRANSIT, DELIVERED
}

static String label(ShipmentStatus status) {
    return switch (status) {
        case CREATED -> "Created";
        case IN_TRANSIT -> "In transit";
        case DELIVERED -> "Delivered";
    };
}
~~~

This is branching on **enum constant values**, so pattern switch is unnecessary.

### 6.2. When you have a sealed hierarchy

Example:

~~~java
sealed interface Command permits StartCommand, StopCommand {
}

record StartCommand(String jobId) implements Command {
}

record StopCommand(String jobId) implements Command {
}
~~~

In Java 17, the approach that does not depend on preview is:

~~~java
static String description(Command command) {
    if (command instanceof StartCommand start) {
        return "Start " + start.jobId();
    }
    if (command instanceof StopCommand stop) {
        return "Stop " + stop.jobId();
    }
    throw new IllegalStateException(
            "Unhandled Command type: " + command);
}
~~~

`sealed`, `record`, and pattern matching for `instanceof` **are all finalized in Java 17**. However, Java 17 does not provide **pattern switch over sealed types as standard syntax**. Thus, `if/instanceof` is the appropriate choice when strictly adhering to Java 17.

When updating permitted records or subtypes in the hierarchy, you must still manually review every place handling subtypes. Do not assume an `if` chain is automatically exhaustiveness-checked by the compiler like a pattern switch in newer Java.

## 7. `null` inside `switch` in Java 17

This is an important limitation to remember because `null` appears frequently in real-world data.

**Standard switch in Java 17 does not use `case null` to handle null values**. With reference-type selectors like `String` or enum, if the selector expression evaluates to `null`, a regular switch throws `NullPointerException` during evaluation. The `default` branch **does not** catch `null`.

Example:

~~~java
static String label(String value) {
    return switch (value) {
        case "A" -> "Group A";
        default -> "Other group";
    };
}
~~~

Calling `label(null)` throws `NullPointerException`; it does not return `"Other group"`.

### 7.1. How to handle null with standard syntax

If null is a valid input in the problem domain, check before using switch:

~~~java
static String labelNullable(String value) {
    if (value == null) {
        return "No value";
    }

    return switch (value) {
        case "A" -> "Group A";
        case "B" -> "Group B";
        default -> "Other group";
    };
}
~~~

If null is a programming error or API contract violation, use an explicit check:

~~~java
import java.util.Objects;

static String labelRequired(String value) {
    Objects.requireNonNull(value, "value");

    return switch (value) {
        case "A" -> "Group A";
        default -> "Other group";
    };
}
~~~

The fact that `case null` is supported in Java 17's preview pattern switch **does not make it an official way to handle null in Java 17 switches**. When upgrading to Java 21+, you can adopt the finalized `case null`.

## 8. Practical example using only standard Java 17 features

Create file **`Java17SwitchDemo.java`**:

~~~java
public class Java17SwitchDemo {

    enum Membership {
        BASIC, PLUS, PREMIUM
    }

    // Switch expression on enum: standard in Java 17.
    static int discountPercent(Membership membership) {
        return switch (membership) {
            case BASIC -> 0;
            case PLUS -> 5;
            case PREMIUM -> 15;
        };
    }

    // Switch expression on String, including multi-constant cases and yield.
    static String processStage(String stage) {
        if (stage == null) {
            return "No status";
        }

        return switch (stage) {
            case "NEW", "QUEUED" -> "Not started";

            case "RUNNING" -> {
                String action = "Processing";
                yield action + " job";
            }

            case "DONE" -> "Completed";
            default -> "Unknown status";
        };
    }

    // Pattern instanceof: standard in Java 17.
    static String describeInput(Object input) {
        if (input instanceof String text) {
            return "String of length " + text.length() + " characters";
        }
        if (input instanceof Integer number) {
            return "Integer: " + number;
        }
        if (input == null) {
            return "Null input";
        }
        return "Other input type";
    }

    public static void main(String[] args) {
        System.out.println(discountPercent(Membership.PLUS));
        System.out.println(processStage("QUEUED"));
        System.out.println(processStage("RUNNING"));
        System.out.println(processStage(null));
        System.out.println(describeInput("Java 17"));
        System.out.println(describeInput(17));
        System.out.println(describeInput(null));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 Java17SwitchDemo.java
java Java17SwitchDemo
~~~

Expected output:

~~~text
5
Not started
Processing job
No status
String of length 7 characters
Integer: 17
Null input
~~~

All language constructs used in the example above — `switch expression`, `->` branches, `yield`, `enum`, and pattern `instanceof` — are finalized when compiled with Java 17.

There are no `case String text`, `case Integer number`, or `case null` branches, because those belong to Java 17's preview pattern switch.

## 9. When and how can preview pattern switch be tried on JDK 17?

If you read research articles or want to understand language design history, you may encounter an example marked **Java 17 preview**. To understand why it fails to compile by default, you need to know two flags:

~~~bash
# Only for code using preview features of that exact JDK 17.
javac --enable-preview --release 17 PatternSwitchPreview.java
java --enable-preview PatternSwitchPreview
~~~

- `--enable-preview` allows JDK 17's `javac` to accept preview features of **JDK 17**.
- `--release 17` sets the corresponding target language/API version during compilation.
- `java --enable-preview` must also be enabled when running a class that uses preview features.
- You must use **the matching JDK 17 toolchain** for Java 17 preview code. Passing `--release 17` to a `javac` from a newer Java version does not turn old preview syntax into something supported by the newer compiler.

Preview-identification example file, **do not use as standard switch expression study code**:

~~~java
// PatternSwitchPreview.java
// ONLY RUNS IN JDK 17 WITH PREVIEW ENABLED.
public class PatternSwitchPreview {

    static String describe(Object value) {
        return switch (value) {
            case String text -> "String: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(17));
    }
}
~~~

Output when using the exact JDK 17 with preview flags:

~~~text
String: Java
Integer: 17
~~~

The purpose of this section is to **recognize preview code in older articles or projects**. For production code pinned to Java 17, prefer the `if/instanceof` approach from section 6. If the project upgrades its Java version, evaluate and use **the finalized syntax of the target version**, such as Java 21 or later.

### 9.1. Preview does not mean permanently obsolete

A feature can go through multiple preview iterations and eventually become standardized. **Pattern switch has been finalized since Java 21**, so the concept itself remains valuable today.

What to avoid:

- Writing "Java 17 officially supports `case String s ->`" — inaccurate regarding its status in Java 17.
- Assuming preview code written for Java 17 is standard code compatible with Java 21+ without checking grammar changes.
- Turning on preview across an entire project just to use things Java 17 already supports natively, such as `switch expression` or `instanceof` pattern matching.

## 10. Common errors and misconceptions

### 10.1. "Using the arrow symbol means preview"

**False.** The arrow in switch branches is standard Java 17 syntax.

~~~java
static int score(String tier) {
    return switch (tier) {
        case "A" -> 100;
        case "B" -> 80;
        default -> 0;
    };
}
~~~

No preview needed.

### 10.2. "Having switch expressions means you can use `case String s`"

**False in default Java 17.** Switch expressions and pattern matching for switch are two separate features. Adding type patterns makes the program depend on Java 17 preview.

### 10.3. "`default` handles null too"

**False in standard Java 17 switch.** A null selector makes switch throw `NullPointerException`. Check for null before entering the switch, or explicitly document that null is disallowed.

### 10.4. "Since sealed classes are final, switching on sealed types is also final"

**False.** `sealed` was finalized in Java 17 (JEP 409), but **switch type patterns** over that hierarchy were still preview. Separate JEPs follow independent timelines.

### 10.5. "Omitting `default` in a String switch expression is still valid"

Usually **false**, if cases are only specific String values; the compiler must guarantee exhaustiveness. With an enum listing all constants, `default` can be omitted.

### 10.6. "`yield` is preview syntax"

**False.** `yield` has been a standard component of switch expressions since Java 14. Inside a block branch, `yield` returns a result to the switch expression; `return` returns from the method, while `break` is not syntax for returning a switch expression value.

### 10.7. "If it runs in JDK 17, it works with `--release 17`"

**False.** The JDK ships preview features, but disables them by default. If code only compiles with `--enable-preview`, that is a key sign the example **does not meet standard default Java 17 constraints**.

### 10.8. "Pattern matching for `instanceof` is also preview in Java 17"

**False.** Pattern matching for `instanceof` has been a standard feature since Java 16 under [JEP 394](https://openjdk.org/jeps/394). Using:

~~~java
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

is valid in Java 17 without enabling preview. Do not confuse pattern `instanceof` with pattern switch.

## 11. Choosing the right construct for real-world requirements

| Problem | Appropriate style when targeting non-preview Java 17 |
|---|---|
| Selecting a value by String codes like `"OPEN"`, `"CLOSED"` | Switch expression with String constant branches |
| Selecting a result by an enum with a finite value set | Switch expression with enum cases |
| Each branch needs multi-step calculation before returning | Switch expression with block and `yield` |
| Checking runtime type is `String`, `Integer`, record type... | `if` + pattern matching for `instanceof` |
| Handling null before branching | `if (value == null)` or `Objects.requireNonNull(value)` |
| Handling subtypes of a sealed hierarchy | `if/instanceof` and an appropriate fallback branch |
| Wanting `case Type variable` directly inside switch | Consider upgrading to Java 21+ or explicitly accepting JDK 17 preview testing |

For production projects, **the target Java version** matters more than the latest code snippet you find online. Syntax valid in Java 21 is not automatically valid in Java 17.

## 12. Comprehension check exercises

### Exercise 1 — Classify syntax

Given the branches:

~~~java
case "A" -> 1;
case "B", "C" -> 2;
case String text -> text.length();
case null -> 0;
default -> -1;
~~~

**Question:** In Java 17, which branches belong to standard switch expressions and which belong to preview pattern switch?

**Answer:** The constant-matching branches `"A"`, `"B"`, `"C"`, and `default` are standard. `case String text` and `case null` belong to Java 17's preview pattern switch capability. The list above is for identifying each syntax independently, not a single switch block you can paste and compile directly.

### Exercise 2 — Write a standard switch expression

Requirement: given parameter `String size`, return:

- `"S"` → `1`.
- `"M"` → `2`.
- `"L"` → `3`.
- Other values → `0`.

**Reference answer:**

~~~java
static int sizeRank(String size) {
    if (size == null) {
        return 0;
    }

    return switch (size) {
        case "S" -> 1;
        case "M" -> 2;
        case "L" -> 3;
        default -> 0;
    };
}
~~~

The snippet runs with `javac --release 17` and handles null itself before the switch.

### Exercise 3 — Convert a type-pattern switch to non-preview Java 17

Given the goal (pattern switch code only for illustration):

~~~java
// PREVIEW in Java 17:
// return switch (value) {
//     case String s -> "String=" + s;
//     case Integer n -> "Integer=" + n;
//     default -> "Other";
// };
~~~

**Write an implementation using only standard Java 17 features.**

**Reference answer:**

~~~java
static String describe(Object value) {
    if (value instanceof String s) {
        return "String=" + s;
    }
    if (value instanceof Integer n) {
        return "Integer=" + n;
    }
    return "Other";
}
~~~

### Exercise 4 — Handling `yield`

Why does the following snippet not require enabling preview?

~~~java
static int cost(String kind) {
    return switch (kind) {
        case "SIMPLE" -> 10;
        case "COMPLEX" -> {
            int base = 10;
            yield base * 3;
        }
        default -> 0;
    };
}
~~~

**Answer:** Because `switch expression`, `->` branches, and `yield` are all standard features in Java 17. There are no type patterns or preview extensions.

### Exercise 5 — Choosing an upgrade path

A project compiles on JDK 17 with `--release 17`. A colleague proposes using `switch (obj)` with `case String s`, claiming it is standard Java 17 because the code works when preview is enabled.

**Explain how to evaluate this.**

**Suggested answer:** That syntax is *pattern matching for switch*, which is preview in Java 17, so it fails the requirement of using only standard Java 17 features. You can stay on Java 17 and use `if/instanceof`, or upgrade Java to 21+ per the project roadmap to use finalized pattern switch. Enabling preview is an experimental opt-in choice, not a change to the feature's standardization status.

## 13. References

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): specification and finalization of switch expressions in Java 14.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): pattern switch in JDK 17, preview status.
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): standard Java 17 syntax alternative.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): finalized status of sealed hierarchies in Java 17.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): finalized pattern switch since Java 21.
- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): `->` syntax, `yield`, result types, and exhaustiveness.
- [Oracle Java SE 17 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-switch-expressions-and-statements.html): JDK 17 preview documentation.
- [Java Language Specification 17 — `14.11 The switch Statement`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11) and [`15.28 switch Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): formal Java 17 language rules.
