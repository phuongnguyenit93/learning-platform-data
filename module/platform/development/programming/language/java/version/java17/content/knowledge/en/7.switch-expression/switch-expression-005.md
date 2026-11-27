# Exception-Throwing Branches in `switch expression` — Java 17

`switch expression` is used when an input value determines **the result value** of an expression. However, not every case is valid for producing a result. In Java 17, a branch of a `switch expression` can **throw an exception with `throw`** instead of returning a value.

Example:

```java
static String label(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 201 -> "Created";
        default -> throw new IllegalArgumentException(
                "Unsupported code: " + code
        );
    };
}
```

When `code` is `200` or `201`, the `switch` expression produces the corresponding string. For any other value, the `default` branch throws `IllegalArgumentException`; no result string is created.

This is standard syntax in **Java 17**, without needing `--enable-preview`. This lesson explains how to write `throw` branches, the relationship between `throw` and `yield`, compilation rules, and how to choose the appropriate exception.

## 1. Distinguishing `switch expression` from `switch statement`

A `switch statement` executes statements by branch; a `switch expression` **is used as an expression that has a value**.

### `switch statement`

```java
String result;
switch (code) {
    case 200:
        result = "OK";
        break;
    case 201:
        result = "Created";
        break;
    default:
        throw new IllegalArgumentException("Unsupported code: " + code);
}
```

In the traditional statement form, branches typically assign to an external variable. `break` is used to stop execution from falling through to the next branch when using colon label syntax `case ...:`.

### `switch expression`

```java
String result = switch (code) {
    case 200 -> "OK";
    case 201 -> "Created";
    default -> throw new IllegalArgumentException(
            "Unsupported code: " + code
    );
};
```

In the expression form:

- The entire `switch (...) { ... }` is **an expression**.
- The `case 200 -> "OK"` branch produces the value `"OK"`.
- The `default -> throw ...` branch **terminates with an exception**.
- No `break` is needed after each branch using the `->` arrow.
- The final `;` in `};` ends the assignment statement containing the `switch expression`.

`throw` is allowed in both switch statements and switch expressions. The key point to grasp is that in a **switch expression**, an exception-throwing branch is accepted even though it **does not return a value**.

## 2. Three branch body forms after `->`

In Java 17, with arrow label syntax (*switch rule*), the right-hand side of `->` can be:

| Branch body form | Syntax | Meaning |
|---|---|---|
| **Expression** | `case A -> expression;` | Evaluates and provides a value for the `switch expression` |
| **Block** | `case B -> { ... }` | Executes multiple statements, typically ending with `yield` or `throw` |
| **`throw` statement** | `case C -> throw new ExceptionType(...);` | Throws an exception without providing a value |

Example combining all three forms:

```java
static String message(int status) {
    return switch (status) {
        case 0 -> "READY";

        case 1 -> {
            String text = "RUNNING";
            yield text.toLowerCase();
        }

        default -> throw new IllegalArgumentException(
                "Unknown status: " + status
        );
    };
}
```

The `case 0` branch supplies a value directly. The `case 1` branch executes multiple statements and then `yield`s a value. The `default` branch throws an exception.

**`throw` is a statement, not a normal Java 17 expression.** Java allows placing it immediately after `->` under the specific grammar rules for switch rules. Therefore `case X -> throw new ...;` is valid, but do not infer that `throw` can arbitrarily substitute for an expression anywhere in Java.

## 3. What happens when a `throw` branch is selected?

Consider:

```java
static int level(String role) {
    return switch (role) {
        case "USER" -> 1;
        case "EDITOR" -> 2;
        case "ADMIN" -> 3;
        default -> throw new IllegalArgumentException(
                "Unknown role: " + role
        );
    };
}
```

When calling `level("EDITOR")`:

1. Java evaluates the selector expression `role`.
2. The value matches the `case "EDITOR"` label.
3. The branch returns `2`.
4. The entire `switch expression` has the value `2`, so the method returns `2`.

When calling `level("GUEST")`:

1. Java evaluates the selector `role`.
2. None of `"USER"`, `"EDITOR"`, or `"ADMIN"` match.
3. The `default` branch runs and constructs an `IllegalArgumentException` object.
4. `throw` throws that exception object.
5. Evaluation of the `switch expression` **completes abruptly** (*abrupt completion*); there is no resulting `int` to pass to `return`.

Diagram:

```text
                      switch (role)
                           |
              +------------+------------+
              |                         |
         Valid label               No label match
              |                         |
       Receive int value           default -> throw
              |                         |
        return value               Throw exception
                                        |
                               Search for matching catch
                                   or propagate up
```

With a `throw` branch, Java does not need to "invent a dummy default value" to satisfy the result type of the `switch expression`.

### No fall-through to the next branch

Arrow branches `->` have no *fall-through*. Once a branch is chosen, Java never automatically runs the branch below it.

```java
static String select(int value) {
    return switch (value) {
        case 1 -> "ONE";
        case 2 -> throw new IllegalStateException("Rejected");
        default -> "OTHER";
    };
}
```

If `value == 2`, the program throws an exception. It **does not continue** into `default` to return `"OTHER"`.

## 4. Basic syntax: throwing directly from a `case`

You can place `throw` directly after `->`:

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "STANDARD";
        case 2 -> "PREMIUM";
        case 0 -> throw new IllegalArgumentException(
                "Code 0 is reserved"
        );
        default -> throw new IllegalArgumentException(
                "Unsupported category: " + code
        );
    };
}
```

Here there are **two exception-throwing branches**:

- `case 0` has a distinct meaning: code `0` is reserved and cannot be used.
- `default` handles codes outside the defined list.

A `throw` branch does not have to be in `default`. Any valid `case` label can throw an exception.

### Multiple labels throwing the same exception

Java 17 allows grouping `case` labels with commas:

```java
static int retryDelaySeconds(int status) {
    return switch (status) {
        case 200 -> 0;
        case 429, 503 -> 30;
        case 400, 401, 403 -> throw new IllegalArgumentException(
                "Non-retryable status: " + status
        );
        default -> throw new IllegalStateException(
                "Status not covered: " + status
        );
    };
}
```

`case 400, 401, 403` is **one switch rule**. When any of the three values matches, the whole rule executes `throw`; there is no need to repeat the same exception three times.

### Include useful context in error messages

The exception message should state **which value was invalid** and **what constraint was violated**:

```java
default -> throw new IllegalArgumentException(
        "Invalid priority " + priority + "; expected 1, 2 or 3"
);
```

Avoid overly generic messages like `"Error"` that lack enough context to trace the root cause. For sensitive data, do not include secrets or information that should not be logged in the message.

## 5. Using `throw` inside a `case ... -> { ... }` block

When you need to run checks or build the error details before throwing, use a **block**:

```java
static String parseMode(String mode) {
    return switch (mode) {
        case "READ" -> "read-only";
        case "WRITE" -> "read-write";

        default -> {
            String description = "Unsupported mode: " + mode;
            throw new IllegalArgumentException(description);
        }
    };
}
```

The `;` after `throw new ...` belongs to the throw statement. Do **not** place a `;` after the closing `}` of the `default -> { ... }` block; the `;` after the final `};` belongs to the outer `return` or assignment statement.

### When a branch has both a value-returning path and a throwing path

A block switch rule can use conditions to decide whether to **throw or `yield`**:

```java
static int calculateFee(int tier, int amount) {
    return switch (tier) {
        case 1 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }

            yield amount / 10;
        }
        case 2 -> {
            if (amount < 100) {
                throw new IllegalArgumentException(
                        "Tier 2 requires amount >= 100"
                );
            }

            yield amount / 5;
        }
        default -> throw new IllegalArgumentException(
                "Unsupported tier: " + tier
        );
    };
}
```

When `tier == 1`:

- If `amount < 0`, `throw` runs; the branch provides no value.
- If `amount >= 0`, execution reaches `yield amount / 10;`; this becomes the result value of the `switch expression`.

Placing conditions inside a block does not make a `switch expression` lose its expression nature. **Every execution path that can reach the end of the block must end with a `yield` value or an appropriate exception**.

## 6. Important rule: every branch must produce a result or throw

A `switch expression` must be able to **complete normally with a value** or **complete abruptly due to an exception**.

Invalid:

```java
// ERROR: the case 1 block can complete normally without yielding.
static String broken(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Known");
        }
        default -> "Other";
    };
}
```

The compiler does not know what value to obtain for `case 1`.

Fix with `yield`:

```java
static String valid(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Known");
            yield "ONE";
        }
        default -> "Other";
    };
}
```

Or if business rules disallow `code == 1`, fix with `throw`:

```java
static String reject(int code) {
    return switch (code) {
        case 1 -> {
            System.out.println("Rejected");
            throw new IllegalStateException("Code 1 is disabled");
        }
        default -> "Other";
    };
}
```

**Easy-to-miss case: a branch that only throws conditionally**

```java
// ERROR: when invalid == false, the case 1 block can fall off the end.
static int broken(int code, boolean invalid) {
    return switch (code) {
        case 1 -> {
            if (invalid) {
                throw new IllegalArgumentException();
            }
        }
        default -> 10;
    };
}
```

Fix to:

```java
static int valid(int code, boolean invalid) {
    return switch (code) {
        case 1 -> {
            if (invalid) {
                throw new IllegalArgumentException();
            }
            yield 1;
        }
        default -> 10;
    };
}
```

`yield 1` ensures the `invalid == false` path still produces a result. This is a rule about **block completion**, separate from the rule requiring enough `case` labels.

## 7. Distinguishing `yield`, `throw`, `return`, and `break`

These four statements serve different purposes:

| Keyword | Role in a `switch expression` context | Supplies a value to `switch expression`? |
|---|---|---|
| `yield value;` | Terminates the block branch and makes `value` the switch result | **Yes** |
| `throw exception;` | Completes with an exception and transfers control to a matching handler | **No** |
| `return value;` | Returns a result from the method, not a tool to produce a switch value | **No** |
| `break;` | Used in allowed control-flow constructs; not used to provide a switch expression result | **No** |

Correct example with `yield` and `throw`:

```java
static String format(int number) {
    return switch (number) {
        case 0 -> {
            String result = "ZERO";
            yield result;
        }
        case -1 -> {
            throw new IllegalArgumentException("Negative sentinel");
        }
        default -> Integer.toString(number);
    };
}
```

Do not write:

```java
// ERROR: throw is not a value to yield.
// case -1 -> { yield throw new IllegalArgumentException(); }

// ERROR: using break to return a value from a switch expression.
// case 0 -> { break "ZERO"; }

// ERROR: return at this position is not how to produce a switch result.
// case 0 -> { return "ZERO"; }
```

In Java 17, `yield` exists to supply a value from a switch expression block. `throw` is **the abrupt-completion-by-exception option**, not a special kind of `yield`.

### Where does the result type come from if a branch only has `throw`?

`throw` does not contribute a `String` or `int` value to result type resolution. The branches **that actually supply values** and the usage context of the switch expression determine the type.

Example:

```java
int port = switch (environment) {
    case "development" -> 8080;
    case "production" -> 80;
    default -> throw new IllegalArgumentException(
            "Unknown environment: " + environment
    );
};
```

The two normal branches produce `int` values. The `default` branch does not have to fabricate a dummy `int` value.

## 8. `switch expression` must still cover all values

The concept of **exhaustiveness**: for values within the selector's valid domain, the switch expression must have appropriate labels to handle them.

### With `int` or `String` selectors

Usually `default` is required:

```java
static String weekdayName(int day) {
    return switch (day) {
        case 1 -> "Monday";
        case 2 -> "Tuesday";
        case 3 -> "Wednesday";
        case 4 -> "Thursday";
        case 5 -> "Friday";
        case 6 -> "Saturday";
        case 7 -> "Sunday";
        default -> throw new IllegalArgumentException(
                "Day must be between 1 and 7: " + day
        );
    };
}
```

The `default` branch **throws an exception** yet still makes the switch cover all other values, because it defines the handling outcome for any value not matching a specific `case`.

The following is invalid because it lacks handling for values other than `1`:

```java
// ERROR: switch expression is not exhaustive.
static String broken(int day) {
    return switch (day) {
        case 1 -> "Monday";
    };
}
```

### With an `enum` selector

When listing **all constants of the enum** in `case`, Java 17 allows omitting `default`:

```java
enum DeliveryState {
    READY,
    IN_TRANSIT,
    DELIVERED,
    CANCELLED
}

static String display(DeliveryState state) {
    return switch (state) {
        case READY -> "Ready";
        case IN_TRANSIT -> "In transit";
        case DELIVERED -> "Delivered";
        case CANCELLED -> throw new IllegalStateException(
                "Cancelled orders have no delivery label"
        );
    };
}
```

Here `CANCELLED` is still **handled** by throwing an exception, so the switch expression covers all four constants.

If the application must always handle a new constant after an enum changes, consider code-update policies and recompiling. The compiler may emit an implicit handling mechanism for unmatched enum values when `default` is absent; **do not rely on an implicit runtime exception as a substitute for enum version control**.

### Do not abuse `default -> throw` to mask missing functionality

There are two distinct designs:

- **Invalid input data:** `default -> throw new IllegalArgumentException(...)` is an explicit rejection.
- **A new enum state that business logic must handle:** if you write `default` everywhere, the compiler may not force you to update every switch after adding an enum constant. For a fixed status hierarchy, listing all enum values explicitly and omitting `default` helps the compiler catch missing branches on recompilation.

Choose based on the API contract, rather than using `throw` just to fill an undesigned branch.

## 9. `null` values: a special case in Java 17

With basic Java 17 switch expressions, if the selector is a `null` reference, branch selection throws `NullPointerException`; **`default` is not a `null`-catching branch**.

Example:

```java
static String classify(String input) {
    return switch (input) {
        case "A" -> "Alpha";
        case "B" -> "Beta";
        default -> throw new IllegalArgumentException(
                "Unknown input: " + input
        );
    };
}
```

With `classify(null)`, you should not expect an `IllegalArgumentException` from `default`; the selector expression is `null` and standard switch rules throw `NullPointerException` before any normal branch is chosen.

If you want an explicit policy for `null`, check **before the switch**:

```java
static String classify(String input) {
    if (input == null) {
        throw new IllegalArgumentException("input must not be null");
    }

    return switch (input) {
        case "A" -> "Alpha";
        case "B" -> "Beta";
        default -> throw new IllegalArgumentException(
                "Unknown input: " + input
        );
    };
}
```

Or use `Objects.requireNonNull(input, "input")` if the API convention is to throw `NullPointerException` when input is null.

> **Version boundary:** Java 17 has *pattern matching for switch* in **preview**, which includes dedicated syntax for handling `null`. This lesson only uses **standard Java 17 switch expressions**, avoiding preview syntax to avoid compiler flags and version-dependent behavior.

## 10. Choosing the exception type for a `throw` branch

Switch syntax does not mandate throwing a specific exception type. The choice depends on **the semantics of the error condition**:

| Exception | Suitable when | Example |
|---|---|---|
| `IllegalArgumentException` | The caller passes an argument value outside the valid domain | `default -> throw new IllegalArgumentException("Bad code: " + code)` |
| `IllegalStateException` | The current state of the system does not permit the operation | `case CLOSED -> throw new IllegalStateException("Already closed")` |
| `UnsupportedOperationException` | The specific operation is unsupported per the API contract | `case ARCHIVE -> throw new UnsupportedOperationException("Archive disabled")` |
| `IOException` | An I/O error appropriately modeled in the API contract | `default -> throw new IOException("Invalid record data")` |
| Custom domain exception | Wanting to express a structured domain error clearly | `case REJECTED -> throw new OrderRejectedException(...)` |

`IllegalArgumentException`, `IllegalStateException`, and `UnsupportedOperationException` are **unchecked exceptions** because they inherit from `RuntimeException`. `IOException` is a **checked exception**.

An unsupported value is not always an error. If the business domain has an "unknown" option that is considered valid, you can return a value representing that instead of throwing an exception. A `throw` branch is appropriate when continuing without reporting an error would violate the method's contract.

### Example with a status enum

```java
enum AccessState {
    ACTIVE,
    LOCKED,
    DELETED
}

static String accessMessage(AccessState state) {
    return switch (state) {
        case ACTIVE -> "Access granted";
        case LOCKED -> throw new IllegalStateException(
                "The account is locked"
        );
        case DELETED -> throw new IllegalStateException(
                "The account was deleted"
        );
    };
}
```

`LOCKED` and `DELETED` are **known** enum states, yet they can be considered states that do not permit generating an access-granted message. Explicitly throwing exceptions for them differs from using `default` to catch an unrecognized value.

## 11. Checked exceptions in a `throw` branch

A `case ... -> throw ...` branch must obey Java's normal checked-exception rules.

Valid example where the method **declares `throws IOException`**:

```java
import java.io.IOException;

class Decoder {
    static String decode(int format) throws IOException {
        return switch (format) {
            case 1 -> "TEXT";
            case 2 -> "BINARY";
            default -> throw new IOException(
                    "Unsupported file format: " + format
            );
        };
    }
}
```

If `throws IOException` is omitted and the exception is not caught appropriately, the code fails with a **compile error** because `IOException` is a checked exception.

It can be caught at the call site:

```java
try {
    String result = Decoder.decode(99);
    System.out.println(result);
} catch (java.io.IOException ex) {
    System.err.println("Decode failed: " + ex.getMessage());
}
```

In this example, `decode(99)` throws `IOException` so `System.out.println(result)` **does not run**; execution jumps to `catch`.

### Checked and unchecked differ only in declaration/handling obligations

Both cause the `switch expression` to **complete abruptly**. The difference lies in Java's compilation rules:

```java
static int selectUnchecked(int value) {
    return switch (value) {
        case 0 -> 10;
        default -> throw new IllegalArgumentException("bad value");
    };
}
```

Here declaring `throws IllegalArgumentException` is not required. Nevertheless, the exception can still propagate to the caller at runtime.

If `IllegalArgumentException` is changed to a checked exception (such as `IOException`), it must be handled or declared according to the contract.

## 12. How exceptions interact with `switch expression` and assignment

Consider:

```java
String label = "unchanged";

try {
    label = switch (code) {
        case 1 -> "ONE";
        case 2 -> "TWO";
        default -> throw new IllegalArgumentException("Invalid: " + code);
    };
} catch (IllegalArgumentException ex) {
    System.out.println("Rejected: " + ex.getMessage());
}

System.out.println(label);
```

If `code == 1`, `label` becomes `"ONE"`.

If `code == 99`, the switch expression throws before finishing the value to be assigned; **the assignment does not occur**, so `label` remains `"unchanged"`. Then the `catch` block can handle the exception.

This helps explain why you should not treat `throw` as a special expression value. It performs a **transfer of control**, rather than producing a value of the switch's type.

### Principle of avoiding error swallowing

Do not wrap the entire switch in `catch (Exception ex)` and return a fake success value if you do not know how to recover. For example, picking `"OK"` after hitting an unexpected exception can mislead the system about the actual state.

Instead:

- Catch the exception type that the current layer is responsible for handling.
- Log/express errors according to the API contract.
- Let exceptions propagate when the current layer has no appropriate recovery path.

This is a general exception-handling principle that applies equally whether `throw` is inside or outside a switch.

## 13. Colon label syntax `case ...:` also supports `throw`

In addition to `->`, `switch expression` in Java 17 still supports **switch-labeled statement groups** using `case ...:` and `yield`.

Example:

```java
static String getLabel(int code) {
    return switch (code) {
        case 1:
            yield "ONE";

        case 2:
            System.out.println("Preparing TWO");
            yield "TWO";

        default:
            throw new IllegalArgumentException(
                    "Unsupported: " + code
            );
    };
}
```

Even with colon syntax, the `default` branch can directly `throw`. Key points to remember:

- `yield` passes a value out of the **switch expression**.
- `throw` throws an exception, without needing `yield`.
- With `case ...:`, you must understand statement-group rules and *fall-through* behavior. Unless there is a reason to keep the old syntax, `case ... ->` is usually clearer for value-selection logic.

Do not write `break` to return a value from a switch expression: `break value;` is not how results are supplied in Java 17.

## 14. Common compilation and design errors

### Error 1 — Trying to write `yield throw ...`

Wrong:

```java
// ERROR: throw is a statement, not an expression to yield.
// return switch (code) {
//     case 1 -> 10;
//     default -> {
//         yield throw new IllegalArgumentException();
//     }
// };
```

Right:

```java
return switch (code) {
    case 1 -> 10;
    default -> throw new IllegalArgumentException("Invalid code");
};
```

Or:

```java
return switch (code) {
    case 1 -> 10;
    default -> {
        throw new IllegalArgumentException("Invalid code");
    }
};
```

### Error 2 — Block can reach the end without `yield` or `throw`

Wrong:

```java
// ERROR:
// return switch (code) {
//     case 1 -> {
//         if (invalid) {
//             throw new IllegalStateException();
//         }
//         System.out.println("Still running");
//     }
//     default -> 0;
// };
```

Fix by having the non-throwing path produce a value:

```java
return switch (code) {
    case 1 -> {
        if (invalid) {
            throw new IllegalStateException();
        }
        yield 1;
    }
    default -> 0;
};
```

### Error 3 — Assuming `default` catches `null`

Wrong expectation:

```java
// When input == null, this does not enter default to throw
// IllegalArgumentException as the author might think.
String result = switch (input) {
    case "YES" -> "accepted";
    default -> throw new IllegalArgumentException("invalid value");
};
```

For standard switches in Java 17, handle `null` beforehand if a custom error message is needed.

### Error 4 — Using the wrong exception type

For example, `IllegalArgumentException` is usually right when an API argument is invalid, but not ideal if an operation fails because the system is already in a disallowed state. Choose an exception type that reflects the cause in a way callers can understand and handle.

### Error 5 — Catching the exception and returning a fake success value

```java
// Usually poor handling if the fallback is not part of the contract:
// try {
//     return switch (code) {
//         case 1 -> "ONE";
//         default -> throw new IllegalArgumentException();
//     };
// } catch (Exception ignored) {
//     return "ONE"; // Can misrepresent data meaning
// }
```

If the API defines a valid fallback, express it explicitly in the design, such as a branch returning `"UNKNOWN"`. If the input must be valid, letting the exception propagate is clearer.

### Error 6 — Using preview `switch` features in Java 17

In Java 17, *type pattern case labels* like `case String s -> ...` belong to the preview feature **pattern matching for switch**, not basic syntax guaranteed to compile by default under Java 17.

This lesson uses constant labels like `case 1`, `case "A"`, or `case ENUM_CONSTANT`, which are stable in Java 17. No preview flag is needed to learn exception-throwing branches in switch expressions.

## 15. Complete runnable example with JDK 17

Create file `SwitchThrowDemo.java`:

```java
public class SwitchThrowDemo {
    enum OrderState {
        NEW,
        PAID,
        SHIPPED,
        CANCELLED
    }

    static String nextAction(OrderState state) {
        return switch (state) {
            case NEW -> "Collect payment";
            case PAID -> "Prepare shipment";
            case SHIPPED -> "Track delivery";
            case CANCELLED -> throw new IllegalStateException(
                    "Cancelled order cannot continue"
            );
        };
    }

    static int parsePriority(String text) {
        if (text == null) {
            throw new IllegalArgumentException("priority is null");
        }

        return switch (text) {
            case "LOW" -> 1;
            case "MEDIUM" -> 2;
            case "HIGH" -> 3;
            default -> throw new IllegalArgumentException(
                    "Unsupported priority: " + text
            );
        };
    }

    public static void main(String[] args) {
        System.out.println(nextAction(OrderState.NEW));
        System.out.println(nextAction(OrderState.PAID));
        System.out.println(parsePriority("HIGH"));

        try {
            System.out.println(nextAction(OrderState.CANCELLED));
        } catch (IllegalStateException ex) {
            System.out.println("Order error: " + ex.getMessage());
        }

        try {
            System.out.println(parsePriority("URGENT"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Priority error: " + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 SwitchThrowDemo.java
java SwitchThrowDemo
```

Expected output:

```text
Collect payment
Prepare shipment
3
Order error: Cancelled order cannot continue
Priority error: Unsupported priority: URGENT
```

Explanation:

1. `OrderState.NEW` and `OrderState.PAID` lead to branches returning `String`.
2. `OrderState.CANCELLED` is a listed enum constant whose branch **throws an exception**.
3. There is no `default` in the enum switch because all four enum values are covered.
4. `parsePriority("HIGH")` produces `3`.
5. `parsePriority("URGENT")` goes to `default -> throw`.
6. The `catch` blocks in `main` merely handle expected exceptions; they do not turn a `throw` branch into a value-returning branch.

## 16. Practice exercises

### Exercise 1 — Complete `default -> throw`

Write a method accepting status codes `0`, `1`, `2`. Any other code must throw `IllegalArgumentException`.

One approach:

```java
static String statusName(int status) {
    return switch (status) {
        case 0 -> "PENDING";
        case 1 -> "RUNNING";
        case 2 -> "DONE";
        default -> throw new IllegalArgumentException(
                "Invalid status: " + status
        );
    };
}
```

Test your understanding: does the method return `null` when given `99`?

**Answer:** No. It throws an exception, so no result `String` is produced.

### Exercise 2 — Combining `yield` and `throw`

Requirement: compute a processing fee for code `1` or `2`; if the amount is negative, throw an exception; other codes are also rejected.

```java
static int fee(int code, int amount) {
    return switch (code) {
        case 1 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }
            yield amount / 10;
        }
        case 2 -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount < 0");
            }
            yield amount / 5;
        }
        default -> throw new IllegalArgumentException(
                "Invalid fee code: " + code
        );
    };
}
```

Identify the two path types: paths yielding a result via `yield` and paths ending with `throw`. No path falls off the end of a block without producing an outcome.

### Exercise 3 — With an enum, does an exception-throwing branch count as handled?

```java
enum Light {
    RED,
    YELLOW,
    GREEN
}

static int seconds(Light light) {
    return switch (light) {
        case RED -> 30;
        case YELLOW -> 5;
        case GREEN -> throw new IllegalStateException(
                "No waiting time for green light"
        );
    };
}
```

**Answer:** Yes. `GREEN` has a branch handled by `throw`; the switch expression covers all three enum constants. A branch does not have to return an `int` in every case, but each path must end with a value or an exception.

### Exercise 4 — Find the error in the block

```java
// Does not compile:
static int getValue(int key, boolean rejected) {
    return switch (key) {
        case 1 -> {
            if (rejected) {
                throw new IllegalStateException();
            }
        }
        default -> 0;
    };
}
```

**Cause:** If `key == 1` and `rejected == false`, the block completes normally without producing a value. Fix with `yield` on that path:

```java
static int getValue(int key, boolean rejected) {
    return switch (key) {
        case 1 -> {
            if (rejected) {
                throw new IllegalStateException();
            }
            yield 100;
        }
        default -> 0;
    };
}
```

### Exercise 5 — Identify checked exceptions

What needs to change for the following method to compile?

```java
// Snippet missing throws declaration:
static String load(int type) {
    return switch (type) {
        case 1 -> "TEXT";
        default -> throw new java.io.IOException("Unsupported");
    };
}
```

**Answer:** Since `IOException` is a checked exception, you must declare `throws java.io.IOException` on the method signature (or catch/handle the exception appropriately). With the declaration approach:

```java
static String load(int type) throws java.io.IOException {
    return switch (type) {
        case 1 -> "TEXT";
        default -> throw new java.io.IOException("Unsupported");
    };
}
```

## 17. Quick rule summary

Common pattern:

```java
Result result = switch (selector) {
    case VALID_A -> createResultA();
    case VALID_B -> {
        if (someInvalidCondition()) {
            throw new IllegalStateException("Invalid state");
        }
        yield createResultB();
    }
    default -> throw new IllegalArgumentException(
            "Unsupported value: " + selector
    );
};
```

When reading a switch expression with `throw`, check:

1. **Which branches return a value?** Use an expression after `->` or `yield` inside a block.
2. **Which branches throw an exception?** Use `throw` directly after `->` or inside a block.
3. **Is there any execution path reaching the end of a block without returning a value or throwing?** If so, the code typically fails to compile.
4. **Is the case list exhaustive?** For `int`/`String`, `default` is usually used; for enums, all constants can be listed.
5. **Are exceptions declared/handled properly?** Especially when using checked exceptions.
6. **If the selector can be `null`, does the API define how to handle it?** In basic Java 17 switches, `default` does not catch `null`.

`throw` branches help clearly express cases where **there is no valid result to return**, instead of returning a dummy value just to make the expression compile.

## Official references

- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html).
- [Java Language Specification 17 — `15.28`: Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28).
- [Java Language Specification 17 — `14.11`: Switch Statements and Switch Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11).
- [Java Language Specification 17 — `14.21`: The `yield` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21).
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361).
