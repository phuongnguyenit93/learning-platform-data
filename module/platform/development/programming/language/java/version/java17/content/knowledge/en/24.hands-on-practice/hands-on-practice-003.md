# Handling Variants with instanceof and Switch Expressions in Java 17

## 1. The Problem of Handling Multiple Data Variants

In an application, a variable can represent several different data types or states: a payment result that succeeded/was declined/is pending, an email/SMS/push notification, or a create/update/delete event. The program needs to identify the actual variant and execute the appropriate behavior.

Java 17 includes stable features that express this logic cleanly:

- **Pattern matching for `instanceof`**: checks the type and declares a typed variable within the same expression.
- **Switch expression**: selects and returns a value based on an enum, string, or supported integer type.
- **Sealed types**: restricts the direct subtypes of a supertype.
- **Records**: concisely represent data variants.

These features combine to handle variants without manual casts in every branch. However, in stable Java 17, `switch` does not yet support type patterns such as `case Circle c -> ...`. Therefore, this lesson uses `instanceof` to branch by subtype and switch expressions for enums or statuses inside each variant.

After this lesson, you should be able to:

1. Use pattern matching for `instanceof` to check types and obtain a typed variable.
2. Understand flow scoping of pattern variables across conditions and control-flow branches.
3. Use switch expressions to return values, handle enums, and write multi-statement branches with `yield`.
4. Combine sealed interfaces, records, `instanceof`, and switch expressions in a variant model.
5. Handle `null`, generic type erasure, and unsupported subtypes.
6. Distinguish stable switch expressions in Java 17 from pattern matching for `switch`, which was in preview.

## 2. Pattern Matching for instanceof

### 2.1. The Traditional Approach

Before pattern matching for `instanceof`, code had to test the type and then cast again:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

There are two repetitive steps: checking whether `value` is a `String`, then casting `value` to `String` to call string methods.

### 2.2. Pattern Matching for instanceof

Java 16 finalized pattern matching for `instanceof` (JEP 394). Java 17 supports it directly:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Syntax:

~~~java
expression instanceof Type patternVariable
~~~

If the expression is an instance compatible with `Type`, the condition evaluates to `true` and `patternVariable` is initialized with the tested value. Inside the true branch, it can be used as a variable of type `Type`.

Benefits:

- Eliminates separate cast expressions.
- Combines type checking and binding a typed variable in one expression.
- The pattern variable is in scope only where the compiler proves it has been initialized.
- Reduces the risk of incorrect casts or using the wrong variable.

### 2.3. Example with Multiple Subtypes

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "String with " + text.length() + " characters";
    } else if (value instanceof Integer number) {
        return "Integer: " + number;
    } else if (value instanceof Boolean flag) {
        return "Boolean value: " + flag;
    }
    return "Other data type";
}
~~~

Each branch checks the type and declares the corresponding variable. There is no need to write `(String) value`, `(Integer) value`, or `(Boolean) value`.

Note: `instanceof` returns `false` if the left-hand expression is `null`. If the method does not accept `null`, establish an explicit policy rather than letting `null` fall through to the "other type" branch.

## 3. Flow Scoping of Pattern Variables

A pattern variable does not have the same scope as a variable declared before a block. The compiler determines where the variable is in scope based on control flow.

### 3.1. Inside the True Branch of an if

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
// text is no longer in scope here.
~~~

The variable `text` is only usable where the `instanceof` condition is proven true.

### 3.2. With the && Operator

In an `&&` expression, the right-hand side is evaluated only when the left-hand side is true. Therefore, the pattern variable can be used on the right-hand side:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
~~~

Here `text` is used only after `value` has been confirmed to be a `String`.

### 3.3. With the || Operator

A pattern variable cannot be used on the right-hand side of `||` in the same way:

~~~java
// Invalid:
// if (!(value instanceof String text) || text.isBlank()) { ... }
~~~

If the left-hand side of `||` is true, the right-hand side is not evaluated. In that case, `text` may not have been initialized, so the compiler does not allow using it on the right-hand side.

Rewrite the check so the condition is clear:

~~~java
if (!(value instanceof String text)) {
    return;
}

if (text.isBlank()) {
    return;
}

System.out.println(text.trim());
~~~

### 3.4. With Negation and Early Return

~~~java
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("Expected a String");
}

// If execution reaches here, the condition was false, meaning value is a String.
System.out.println(text.length());
~~~

The compiler knows the `if` branch cannot complete normally after throwing an exception. Therefore, `text` remains in scope afterward.

Similarly, `return`, `throw`, `break`, or other control-flow statements affect flow scoping. Keep check branches short and readable so both the compiler and code reviewers can easily follow the condition.

### 3.5. Pattern Variables Cannot Be Reassigned

A pattern variable is treated as a final-like local variable in the pattern-matching context; a new value cannot be assigned to it:

~~~java
if (value instanceof String text) {
    // text = "other"; // Invalid.
    System.out.println(text);
}
~~~

If you need a mutable variable, declare a separate local variable after the type check.

## 4. Switch Expressions in Java 17

### 4.1. Switch Expressions Returning a Value

Switch expressions were standardized in Java 14 (JEP 361), so they are stable in Java 17.

Unlike a switch statement that primarily executes actions, a switch expression computes a value:

~~~java
int days = switch (month) {
    case 1, 3, 5, 7, 8, 10, 12 -> 31;
    case 4, 6, 9, 11 -> 30;
    case 2 -> 28;
    default -> throw new IllegalArgumentException("Invalid month");
};
~~~

The result of the switch expression is assigned directly to `days`. Branches using `->` do not fall through to subsequent branches like traditional switch statements.

The example above does not account for leap years; it only illustrates switch expression syntax. For real calendar logic, use `YearMonth.lengthOfMonth()` or the appropriate `java.time` API.

### 4.2. Switch Expressions with Enums

An enum is a natural fit when the set of states is fixed:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Newly created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Because a switch expression must produce a value for every possible case, the compiler requires it to be exhaustive. With enums, listing every constant explicitly is clean and clear. If a new constant is added and the code is recompiled, the compiler flags the missing case.

Do not add `default` mechanically if you want the compiler to catch newly added enum constants. `default` can be useful when a fallback is intended, but it can also hide un-updated logic for new constants.

### 4.3. Switch Expressions with String

~~~java
static String normalizeCommand(String command) {
    return switch (command) {
        case "start" -> "START";
        case "stop" -> "STOP";
        case "reload" -> "RELOAD";
        default -> throw new IllegalArgumentException(
                "Unsupported command: " + command);
    };
}
~~~

Switching on `String` is case-sensitive. If the protocol is case-insensitive, normalize the string before switching, such as `command.toLowerCase(Locale.ROOT)`. Do not use the default locale for normalizing technical tokens.

### 4.4. Switch Expressions with Multiple Labels

Multiple constants can be combined into a single branch:

~~~java
static String category(int code) {
    return switch (code) {
        case 200, 201, 202 -> "Success";
        case 400, 401, 403, 404 -> "Request error";
        case 500, 502, 503 -> "Server error";
        default -> "Other code";
    };
}
~~~

This syntax is useful when multiple values share the same outcome. Do not group values with different meanings into one branch merely to shorten code.

## 5. Using Blocks and yield in Switch Expressions

A switch expression branch can contain multiple statements. In that case, use `yield` to return the branch's value:

~~~java
static String describeStatus(int code) {
    return switch (code) {
        case 200 -> {
            String message = "Request";
            message += " succeeded";
            yield message;
        }
        case 404 -> {
            String message = "Resource not found";
            yield message;
        }
        default -> {
            String message = "HTTP status: " + code;
            yield message;
        }
    };
}
~~~

`yield` returns a value from a switch expression branch. It differs from `return`, which exits the enclosing method.

Do not use `break` to return a value from a switch expression. If a branch uses a block `{ ... }`, every normal completion path must produce a value via `yield` or terminate abruptly (such as with `throw`).

## 6. Combining instanceof with Switch Expressions

In stable Java 17, these two constructs solve two different levels of classification:

1. `instanceof` identifies which object variant is present.
2. A `switch` expression handles a known classification value, typically an enum or status code.

For example, a payment result can be paid, declined, or pending. Each variant holds an additional enum describing the details.

~~~java
enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    CASH
}

enum DeclineReason {
    INSUFFICIENT_FUNDS,
    INVALID_ACCOUNT,
    RISK_CHECK
}

enum PendingStage {
    CREATED,
    WAITING_FOR_BANK,
    VERIFYING
}

sealed interface PaymentResult
        permits Paid, Declined, Pending {
}

record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
}

record Declined(String transactionId, DeclineReason reason)
        implements PaymentResult {
}

record Pending(String transactionId, PendingStage stage)
        implements PaymentResult {
}

static String describe(PaymentResult result) {
    Objects.requireNonNull(result, "result");

    if (result instanceof Paid paid) {
        String methodName = switch (paid.method()) {
            case CARD -> "card";
            case BANK_TRANSFER -> "bank transfer";
            case CASH -> "cash";
        };

        return "Transaction " + paid.transactionId()
                + " paid via " + methodName;
    } else if (result instanceof Declined declined) {
        String reasonText = switch (declined.reason()) {
            case INSUFFICIENT_FUNDS -> "insufficient funds";
            case INVALID_ACCOUNT -> "invalid account";
            case RISK_CHECK -> "failed risk check";
        };

        return "Transaction " + declined.transactionId()
                + " declined: " + reasonText;
    } else if (result instanceof Pending pending) {
        String stageText = switch (pending.stage()) {
            case CREATED -> "created";
            case WAITING_FOR_BANK -> "waiting for bank";
            case VERIFYING -> "verifying";
        };

        return "Transaction " + pending.transactionId()
                + " pending: " + stageText;
    }

    throw new IllegalArgumentException(
            "Unsupported result type: " + result.getClass().getName());
}
~~~

In this example:

- `PaymentResult` is a sealed interface restricting the permitted variants.
- `Paid`, `Declined`, and `Pending` are records, each carrying its own data.
- `instanceof` pattern matching selects the right branch and binds `paid`, `declined`, or `pending`.
- Switch expressions handle each variant's enum and return a descriptive string.
- `Objects.requireNonNull` makes it explicit that the method does not accept `null`.

The trailing `throw` is a defensive branch. Java 17 does not yet infer exhaustiveness of an `instanceof` chain over a sealed hierarchy the way pattern switch does in later Java releases. When adding a new subtype to `permits`, update the handling logic and tests accordingly.

## 7. Sealed Types and Records in Variant Models

### 7.1. Sealed Interfaces Restrict Subtypes

Sealed classes/interfaces were standardized in Java 17 (JEP 409). A sealed type explicitly declares which types may extend or implement it:

~~~java
sealed interface PaymentResult
        permits Paid, Declined, Pending {
}
~~~

Each direct subtype must declare one of the permitted modifiers:

- `final`: disallows further extension.
- `sealed`: continues restricting its own subtypes.
- `non-sealed`: reopens inheritance.

In the example, records are implicitly `final`, so they can serve as permitted subtypes directly.

### 7.2. Records Fit Data-Carrying Variants

~~~java
record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
}
~~~

Records automatically provide component accessors, a canonical constructor, `equals`, `hashCode`, and `toString`. They offer a concise way to represent a variant whose field references are immutable.

Records do not automatically enforce every business rule. If data constraints are needed, use a compact constructor or validator:

~~~java
record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
    Paid {
        Objects.requireNonNull(transactionId, "transactionId");
        Objects.requireNonNull(method, "method");
        if (transactionId.isBlank()) {
            throw new IllegalArgumentException(
                    "transactionId must not be blank");
        }
    }
}
~~~

### 7.3. Why Is a Trailing Branch Still Needed?

A sealed hierarchy tells readers the permitted direct subtypes, but an `if/else instanceof` chain in Java 17 has no compile-time exhaustiveness check.

If a new subtype is added:

- The compiler does not automatically flag every `instanceof` chain.
- The trailing branch may receive the new subtype.
- Tests must cover every permitted subtype.
- You can use the visitor pattern if you want to group behavior by type and make update points explicit when the hierarchy changes.

Do not make the trailing branch return a default success string if an unknown subtype must be handled explicitly. Usually, throw an exception or route to intentional error handling.

## 8. Limitations of Stable Switch Expressions in Java 17

### 8.1. Supported Selector Types

In Java 17, stable switch statements/expressions support selectors of types:

- `byte`, `short`, `char`, `int`, and their corresponding wrappers.
- `String`.
- Enum.

You cannot use `long`, `float`, `double`, or `boolean` directly as a switch selector.

Valid example:

~~~java
String label = switch (statusCode) {
    case 0 -> "OK";
    case 1 -> "WARNING";
    default -> "UNKNOWN";
};
~~~

Invalid example:

~~~java
// Invalid in Java 17:
// switch (longValue) { ... }
// switch (booleanValue) { ... }
~~~

If you need to classify `long` values, use `if/else` or perform a controlled conversion to a supported selector type. Do not cast arbitrarily if data loss is possible.

### 8.2. Java 17 Has No Stable Type Patterns in Switch

In Java 17, the following syntax is not part of stable switch features:

~~~java
// Does not compile as Java 17 stable:
// return switch (shape) {
//     case Circle circle -> circle.radius() * circle.radius() * Math.PI;
//     case Rectangle rectangle -> rectangle.width() * rectangle.height();
// };
~~~

Pattern matching for `switch` was provided as a preview feature in JDK 17 (JEP 406). Preview features require explicit flags and can change across preview releases; do not rely on that preview syntax as the foundation for stable Java 17 source code.

Pattern matching for `switch` was only finalized in Java 21 (JEP 441). When targeting a Java 17 runtime, combine `instanceof` pattern matching with switch expressions on enums or supported scalar/string values as shown in this lesson.

### 8.3. Switch Expressions Do Not Handle null Automatically

If the selector of a switch expression is `null`, Java 17 throws `NullPointerException`:

~~~java
OrderStatus status = null;

// Throws NullPointerException:
// String label = switch (status) { ... };
~~~

If `null` is a valid state in your data, handle it beforehand:

~~~java
static String label(OrderStatus status) {
    if (status == null) {
        return "Unspecified";
    }

    return switch (status) {
        case NEW -> "Newly created";
        case PAID -> "Paid";
        case SHIPPED -> "Shipped";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Stable Java 17 does not support `case null` in switch expressions. Do not rely on preview syntax to handle null if your code must remain compatible with stable JDK 17.

## 9. Generic Types and instanceof

### 9.1. Parameterized Types Cannot Be Tested Directly

Due to type erasure, you cannot write:

~~~java
// Invalid:
// if (value instanceof List<String> strings) { ... }
~~~

`List<String>` is not a reifiable type at runtime. You can test the unbounded wildcard generic type:

~~~java
if (value instanceof List<?> values) {
    System.out.println(values.size());
}
~~~

Each element still has type `Object` until checked individually:

~~~java
if (value instanceof List<?> values) {
    for (Object item : values) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
~~~

Do not cast the entire list to `List<String>` just because the first few elements are strings. If you need a list of strings, validate every element before creating or returning the typed list.

### 9.2. Arrays Retain Component Type Information

Arrays retain their component type at runtime, so you can test:

~~~java
if (value instanceof String[] texts) {
    System.out.println(texts.length);
}
~~~

This differs from generic collections affected by type erasure. Even so, if the array reference is `null`, `instanceof` still returns `false`.

## 10. Comparing if/else instanceof with Switch Expressions

The two constructs are not complete substitutes for each other. Choose based on the kind of data being dispatched:

| Need | Suitable construct in Java 17 |
|---|---|
| Branching by object subtype | `if/else` with `instanceof` pattern matching |
| Branching by enum | Switch expression |
| Branching by `String` command | Switch expression |
| Branching by integer code | Switch expression |
| Dispatching a sealed hierarchy by subtype in `switch` | Not in stable Java 17; use `instanceof` or visitor |
| Checking whether a value has a specific type | `instanceof` |
| Needing multiple statements to compute a switch result | Switch expression with block and `yield` |

Do not turn an `if/else` chain over object types into an enum switch by adding a `type` field if that field could get out of sync with the actual subtype. Two redundant sources of type information easily create inconsistent states.

## 11. Complete Example: Handling Application Events

The following example demonstrates a sealed event hierarchy, pattern matching for `instanceof`, and switch expressions to classify severity:

~~~java
import java.util.Objects;

public class EventDemo {
    enum Severity {
        INFO,
        WARNING,
        ERROR
    }

    enum RetryPolicy {
        NEVER,
        ONCE,
        EXPONENTIAL
    }

    sealed interface AppEvent permits UserCreated, PaymentFailed, ServiceUnavailable {
    }

    record UserCreated(String userId) implements AppEvent {
    }

    record PaymentFailed(String paymentId, Severity severity)
            implements AppEvent {
    }

    record ServiceUnavailable(String serviceName, RetryPolicy retryPolicy)
            implements AppEvent {
    }

    static String describe(AppEvent event) {
        Objects.requireNonNull(event, "event");

        if (event instanceof UserCreated created) {
            return "Created user " + created.userId();
        } else if (event instanceof PaymentFailed failed) {
            String action = switch (failed.severity()) {
                case INFO -> "log";
                case WARNING -> "alert";
                case ERROR -> "investigate immediately";
            };
            return "Payment " + failed.paymentId()
                    + " failed; " + action;
        } else if (event instanceof ServiceUnavailable unavailable) {
            String retry = switch (unavailable.retryPolicy()) {
                case NEVER -> "do not retry";
                case ONCE -> "retry once";
                case EXPONENTIAL -> "retry with exponential backoff";
            };
            return "Service " + unavailable.serviceName()
                    + " unavailable; " + retry;
        }

        throw new IllegalArgumentException(
                "Unsupported event type: " + event.getClass().getName());
    }

    public static void main(String[] args) {
        AppEvent event = new PaymentFailed("PAY-1024", Severity.ERROR);
        System.out.println(describe(event));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 EventDemo.java
java EventDemo
~~~

Output:

~~~text
Payment PAY-1024 failed; investigate immediately
~~~

Here `instanceof` identifies the event type. Switch expressions handle the enums to decide the action. Because no preview pattern switch is used, the source runs on stable Java 17 without `--enable-preview`.

## 12. Common Mistakes

### 12.1. Checking instanceof and Casting Again

The following code is unnecessary:

~~~java
if (value instanceof String) {
    String text = (String) value;
}
~~~

Use a pattern:

~~~java
if (value instanceof String text) {
    // Use text directly.
}
~~~

### 12.2. Using a Pattern Variable Outside Its Flow Scope

A pattern variable exists only where the compiler proves it is initialized. Do not declare it in one condition and assume it is available after every branch.

**How to handle:** use an `if` block or early return to clarify control flow.

### 12.3. Using a Switch Statement When a Value Is Needed

When the goal is to produce a value to assign or return, a switch expression is usually more concise and avoids fall-through bugs:

~~~java
String label = switch (status) {
    case NEW -> "New";
    case PAID -> "Paid";
    case CANCELLED -> "Cancelled";
};
~~~

### 12.4. Forgetting yield in a Block Branch

A switch expression branch using a `{ ... }` block must produce a value via `yield` if it completes normally.

**How to handle:** add `yield result;` or use a simple arrow expression if there is only one expression.

### 12.5. Adding an Unnecessary default to an Enum Switch

`default` can prevent the compiler from warning when a new enum constant is added.

**How to handle:** when you want to handle every enum constant explicitly, list all of them and let the compiler identify where code needs updating.

### 12.6. Forgetting null

`instanceof` with `null` evaluates to `false`; switching on `null` throws `NullPointerException` in stable Java 17.

**How to handle:** decide whether `null` is valid and handle it before branching.

### 12.7. Using instanceof with a Generic Parameterized Type

`instanceof List<String>` is invalid due to type erasure.

**How to handle:** test `List<?>`, then validate each element.

### 12.8. Treating Preview Pattern Switch as a Stable Java 17 Feature

Type patterns in `switch` are not part of stable Java 17.

**How to handle:** when targeting Java 17, use `instanceof` pattern matching. Only use pattern switch after upgrading runtime/compiler to a version where that feature is finalized and the codebase intentionally targets it.

## 13. Practice Exercises

### Exercise 1 — Rewrite Traditional instanceof

Given `Object value`, rewrite an `instanceof` and cast chain for `String`, `Integer`, and `Boolean` using pattern matching for `instanceof`. Return a description from each branch.

### Exercise 2 — Flow Scoping

Write a method accepting only non-blank strings. Use a pattern variable with `&&` and a negated pattern with early return/throw. Explain why a pattern variable cannot be used on the right-hand side of an `||` expression when the condition could skip initializing the variable.

### Exercise 3 — Switch Expression with Enum

Create an enum `DeliveryStatus` with `CREATED`, `IN_TRANSIT`, `DELIVERED`, and `FAILED`. Write a switch expression returning a message. Add a new enum constant and observe where the compiler requires updates.

### Exercise 4 — Combining Subtypes and Enums

Create a sealed interface `Notification` with three records: `Email`, `Sms`, and `Push`. Use `instanceof` to branch by notification type and a switch expression to handle a `Priority` enum inside each variant.

### Exercise 5 — Sealed Hierarchy

Create a sealed interface `Shape` with `Circle`, `Rectangle`, and `Triangle`. Write a method calculating area using an `instanceof` pattern-matching chain. Add a new subtype and explain why Java 17 does not automatically flag missing branches in an `if/else` chain.

### Exercise 6 — Generic Type Erasure

Accept an `Object` that may be a `List<?>`. Use pattern matching to check for a list, then process only `String` elements. Explain why `List<String>` cannot be tested directly.

### Exercise 7 — Recognizing Preview Features

Read a JDK 17 pattern matching for `switch` example and compare it with stable Java 17 syntax. Explain why source code targeting Java 17 should not depend on preview switch patterns.

## 14. Completion Criteria

You have mastered this lesson when you can:

1. Write `value instanceof String text` and use the pattern variable within its valid scope.
2. Explain flow scoping with `if`, `&&`, `||`, negation, and early return.
3. Use switch expressions returning values with enums, `String`, or supported integer types.
4. Write multi-statement switch expression branches using `yield`.
5. Combine `instanceof`, sealed interfaces, records, and switch expressions to handle variants.
6. Handle `null` explicitly before switching.
7. Understand type erasure limitations when using `instanceof` with generics.
8. Distinguish stable switch expressions in Java 17 from pattern matching for `switch` in preview status in JDK 17.
9. Choose `instanceof`, switch expressions, or visitors based on data types and maintenance needs.
10. Compile examples using `javac --release 17` without enabling preview features.

## 15. Official Documentation

- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern matching for `instanceof` standardized in Java 16.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expressions standardized in Java 14.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): sealed classes/interfaces standardized in Java 17.
- [Java SE 17 Language Specification — Pattern Matching for instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): syntax and type-checking rules.
- [Java SE 17 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): switch expressions, exhaustiveness, and expression results.
- [Java SE 17 Language Specification — Scope of Pattern Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): scope and flow scoping of pattern variables.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): preview status of pattern `switch` in Java 17; not stable syntax for this release.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): finalized status in Java 21 for comparison when upgrading.

**Key takeaway:** In stable Java 17, use `instanceof` pattern matching to identify subtypes, switch expressions to handle enums/Strings/numeric codes, and sealed types to restrict variants. Pattern matching for `switch` is not yet a stable feature in Java 17; do not introduce preview syntax into code that must run reliably on JDK 17.
