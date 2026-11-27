# Null and Officially Supported Selector Types in Java 17

## 1. Lesson scope: selecting branches with `switch expression` in Java 17

`switch expression` is an expression that chooses a branch to **produce a value**. It was standardized in Java 14 and can be used directly in Java 17 without enabling preview features. However, not every data type can be placed after the `switch` keyword, and a selector with a `null` value has specific behavior that must be understood clearly.

Example:

~~~java
int httpStatus = 201;

String result = switch (httpStatus) {
    case 200, 201 -> "Success";
    case 400 -> "Bad request";
    case 404 -> "Not found";
    default -> "Other status";
};

System.out.println(result); // Success
~~~

In `switch (httpStatus)`:

- **Selector expression** is the expression `httpStatus`, from which the program obtains the value used to choose a branch.
- **Selector type** is the static type of that expression, here `int`.
- **Case labels** are the labels `200`, `201`, `400`, `404`, and `default`.
- **Result** is the value produced by the selected branch, here `String`.

This lesson focuses strictly on two questions:

1. Which types can be used as a **selector** in a **standard Java 17** `switch expression`?
2. What happens when the **selector evaluates to `null`**, and how should code be designed?

Basic selector and `null` rules also apply to standard `switch statement` constructs in Java 17. The main difference is that **a switch expression must produce a value and has branch coverage requirements**, whereas a switch statement is typically used to execute actions.

> **Version boundary:** Java 17 includes a preview of *pattern matching for switch*, which introduces new syntax for handling `null`. This lesson uses **the stabilized Java 17 feature set**, requires no `--enable-preview`, and does not rely on preview syntax for primary examples.

## 2. Table of selector types officially supported in Java 17

With `switch` under Java 17's stable rules, the selector must have one of the following types:

| Group | Valid selector type | Example expression | Can be `null`? |
|---|---|---|---|
| Small integer primitive | `byte` | `byte level = 2;` | No |
| Small integer primitive | `short` | `short code = 100;` | No |
| Character primitive | `char` | `char grade = 'A';` | No |
| Integer primitive | `int` | `int status = 200;` | No |
| Corresponding wrapper | `Byte` | `Byte level = 2;` | **Yes** |
| Corresponding wrapper | `Short` | `Short code = 100;` | **Yes** |
| Corresponding wrapper | `Character` | `Character grade = 'A';` | **Yes** |
| Corresponding wrapper | `Integer` | `Integer status = 200;` | **Yes** |
| String | `String` | `String command = "START";` | **Yes** |
| Enumerated type | A specific `enum` type | `Mode mode = Mode.AUTO;` | **Yes** |

This is **the list of selector types in standard Java 17**. An object looking like an integer or string at runtime **is not enough**; the compiler must see that the static type of the selector is an allowed type.

For example, `Integer` is accepted, while `Number` is not, even if a `Number` variable happens to hold an `Integer` instance.

### 2.1. Types not supported as selectors in standard Java 17

| Type / expression | Can be a direct selector? | Reason |
|---|---|---|
| `long`, `Long` | **No** | Not among the selector types allowed in standard Java 17 |
| `float`, `Float` | **No** | Floating-point numbers are not standard Java 17 switch selectors |
| `double`, `Double` | **No** | Same as above |
| `boolean`, `Boolean` | **No** | Not in the allowed type set |
| `Object` | **No** | Static type is too broad |
| `Number` | **No** | Not one of the four listed wrappers |
| `CharSequence` | **No** | Only `String` is allowed in the string category |
| `BigInteger`, `BigDecimal` | **No** | No direct selector support |
| Arbitrary class/record | **No** | Not an enum or allowed selector type |
| Array or `List` | **No** | Not in the selector type set |
| `null` as an untyped selector expression | **No** | Does not form a valid selector; for valid reference selectors with a null value see section 4 |

**Invalid** examples:

~~~java
long code = 200L;
// String text = switch (code) {
//     case 200 -> "OK";
//     default -> "OTHER";
// };
// Does not compile on Java 17: long selector is not supported.
~~~

~~~java
Object command = "START";
// String action = switch (command) {
//     case "START" -> "Run";
//     default -> "Unknown";
// };
// Does not compile: static type of command is Object.
~~~

~~~java
Number number = Integer.valueOf(1);
// String category = switch (number) {
//     case 1 -> "ONE";
//     default -> "OTHER";
// };
// Does not compile: Number is not Integer.
~~~

The `var` keyword is not a new selector type. If you write `var status = 200;`, the compiler infers `int` and it works in a switch. If you write `var item = (Object) "START";`, the compiler infers `Object`, so it cannot be used even though the runtime value is a string.

## 3. Switch expressions with each valid selector group

### 3.1. `int` and primitive types `byte`, `short`, `char`

Example with `int`:

~~~java
static String classifyHttpStatus(int status) {
    return switch (status) {
        case 200, 201, 204 -> "SUCCESS";
        case 400, 422 -> "CLIENT_ERROR";
        case 500, 503 -> "SERVER_ERROR";
        default -> "OTHER";
    };
}
~~~

Example with `byte`:

~~~java
static String levelName(byte level) {
    return switch (level) {
        case 1 -> "LOW";
        case 2 -> "MEDIUM";
        case 3 -> "HIGH";
        default -> "UNSUPPORTED";
    };
}
~~~

Example with `short`:

~~~java
static String protocolVersion(short version) {
    return switch (version) {
        case 1 -> "V1";
        case 2 -> "V2";
        default -> "UNKNOWN";
    };
}
~~~

Example with `char`:

~~~java
static String letterGrade(char grade) {
    return switch (grade) {
        case 'A' -> "Excellent";
        case 'B' -> "Good";
        case 'C' -> "Pass";
        default -> "Needs review";
    };
}
~~~

Primitive selectors **cannot hold `null`**, so you never get an NPE from the selector itself being null. However, you still need to handle invalid or out-of-domain codes via `default` or appropriate validation.

Case values must satisfy **compile-time constant** rules and be compatible with the selector. For `byte` or `short` selectors, you can use `int` constants within the representable range, but you cannot use a number outside that range just because the JVM stores it in a wider integer slot.

~~~java
byte value = 1;
String label = switch (value) {
    case 1 -> "ONE";
    default -> "OTHER";
};

// Invalid if adding label case 200 for a byte selector:
// case 200 -> "TWO_HUNDRED";
// 200 is outside the range of byte (-128 to 127).
~~~

Labels that duplicate values after valid conversion rules are also prohibited from appearing twice.

### 3.2. Wrappers: `Byte`, `Short`, `Character`, `Integer`

Java 17 allows using the corresponding wrappers for the four primitive types above:

~~~java
Integer status = Integer.valueOf(200);

String response = switch (status) {
    case 200 -> "OK";
    case 404 -> "NOT_FOUND";
    default -> "OTHER";
};
~~~

Wrappers are convenient when data from an API, database, or object structure may be absent. Yet here an important boundary appears: **a wrapper can be `null`**.

~~~java
Integer status = null;

// Compiles, but when executing the switch it throws
// NullPointerException before selecting a branch:
//
// String result = switch (status) {
//     case 200 -> "OK";
//     default -> "OTHER";
// };
~~~

Under the hood, wrapper selectors follow rules related to extracting the numeric/character value, which involves unboxing. A null wrapper reference cannot provide a value to match against `case` labels, so the switch throws `NullPointerException`.

The same applies to `Byte`, `Short`, and `Character`, not only `Integer`.

### 3.3. `String` selector

`String` allows mapping text codes with a clear set of values:

~~~java
static String actionFor(String command) {
    return switch (command) {
        case "CREATE" -> "Create new";
        case "UPDATE" -> "Update";
        case "DELETE" -> "Delete";
        default -> "Unsupported command";
    };
}
~~~

With a `String` selector:

- Label matching compares string content and is **case-sensitive**.
- `"CREATE"` and `"create"` are two different values.
- `" CREATE "` with spaces differs from `"CREATE"`.
- `default` handles strings that do not match any case, but **does not handle a `null` selector**.
- `case` takes matching constant values; standard Java 17 switch **does not support** regex, pattern guards, or `startsWith` checks directly as a case.

If the business protocol allows ignoring whitespace and letter case, **normalize before the switch**:

~~~java
import java.util.Locale;

static String normalizedAction(String rawCommand) {
    if (rawCommand == null) {
        return "Missing command";
    }

    String command = rawCommand.strip().toUpperCase(Locale.ROOT);

    return switch (command) {
        case "CREATE" -> "Create new";
        case "UPDATE" -> "Update";
        case "DELETE" -> "Delete";
        default -> "Unsupported command";
    };
}
~~~

Using `Locale.ROOT` keeps upper/lowercasing for **technical codes** independent of the environment's default locale. However, only normalize like this when the input contract permits it; exact case-sensitive identifiers or tokens may not allow alteration.

### 3.4. `enum` selector

An enum is a great choice when the domain is represented by a set of constants defined in Java code:

~~~java
enum PaymentStatus {
    NEW, PAID, CANCELLED
}

static String paymentLabel(PaymentStatus status) {
    return switch (status) {
        case NEW -> "Unpaid";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Because **all enum constants** are listed in the switch expression, the example needs no `default`. The Java 17 compiler can verify coverage of enum cases known at compile time.

In standard Java 17, enum labels in this example use the constant name **without the enum type prefix**:

~~~java
case NEW -> "Unpaid";
~~~

Do not write `case PaymentStatus.NEW` instead of this syntax in a standard Java 17 enum switch.

An enum is a **reference type**, so a `PaymentStatus status` variable can still be `null`:

~~~java
PaymentStatus status = null;

// NullPointerException when evaluating switch:
// String label = switch (status) {
//     case NEW -> "New";
//     case PAID -> "Paid";
//     case CANCELLED -> "Cancelled";
// };
~~~

Listing all enum constants only ensures that all **non-null valid enum values** have a handling branch. It does not mean there is an implicit branch for `null`.

If an enum is changed in a library version different from the one compiled against, review the logic and deploy in sync. When updating source code to add an enum constant, switch expressions listing all previous branches must be updated according to coverage rules.

## 4. `null` selectors in Java 17: what is the official behavior?

### 4.1. A null reference selector makes switch throw `NullPointerException`

Look at this example:

~~~java
String command = null;

String result = switch (command) {
    case "START" -> "RUNNING";
    case "STOP" -> "STOPPED";
    default -> "UNKNOWN";
};
~~~

This snippet **compiles** because the selector has a valid `String` type. Yet at runtime, `command` is null, so branch selection throws `NullPointerException`.

The same rule applies to other reference-type selectors supported by Java 17:

| Selector | If value is `null` | Does `default` receive null? |
|---|---|---|
| `String` | `NullPointerException` | No |
| `Byte` | `NullPointerException` | No |
| `Short` | `NullPointerException` | No |
| `Character` | `NullPointerException` | No |
| `Integer` | `NullPointerException` | No |
| An `enum` | `NullPointerException` | No |

Null is not an unusual string, not an out-of-range numeric code, and not an undeclared enum constant. It is **the absence of a reference** before the branch selector even has a valid value.

### 4.2. Why does `default` not catch null?

`default` is a branch for valid selector values **that do not match any other case labels**. In standard Java 17, when a reference selector is null, switch does not pass null to `default`; it throws an exception.

Example:

~~~java
static String mapCode(Integer code) {
    return switch (code) {
        case 1 -> "ACTIVE";
        case 2 -> "INACTIVE";
        default -> "UNKNOWN";
    };
}
~~~

Results by input:

| Call | Result |
|---|---|
| `mapCode(1)` | `"ACTIVE"` |
| `mapCode(2)` | `"INACTIVE"` |
| `mapCode(99)` | `"UNKNOWN"` |
| `mapCode(null)` | Throws `NullPointerException` |

Having `default` does not change the last row.

### 4.3. Can `case null` be used?

An easy point of confusion across Java versions:

~~~java
// DO NOT use as standard Java 17 syntax:
//
// String result = switch (command) {
//     case null -> "MISSING";
//     case "START" -> "RUNNING";
//     default -> "UNKNOWN";
// };
~~~

In **Java 17**, matching `null` with `case null` belongs to the **preview of pattern matching for switch (JEP 406)**; it is not part of the stable language used by default. Do not use it in Java 17 lessons requiring standard code without preview enabled.

`case null` was later brought into standard switch rules alongside pattern matching for switch in **Java 21 (JEP 441)**. Consequently, an example valid on Java 21 might **not** compile under `--release 17`.

Do not turn on preview flags merely to replace a simple `if (value == null)` check in code that needs Java 17 compatibility.

### 4.4. Returning `null` differs from a `null` selector

The following two scenarios are **completely different**:

**Scenario A: null selector — error during branch selection.**

~~~java
String command = null;
// switch (command) { ... } -> NullPointerException
~~~

**Scenario B: valid selector, branch intentionally returns null.**

~~~java
static String optionalCode(int code) {
    return switch (code) {
        case 0 -> null;
        case 1 -> "READY";
        default -> "UNKNOWN";
    };
}

String value = optionalCode(0); // null
~~~

Scenario B is **valid in Java 17** because the selector `code` is `int` and a switch expression can produce a null reference result when the result type permits it. Decide whether your API actually wants to return `null`; an `Optional<String>`, a dedicated result type, or a meaningful status value can be clearer when representing absence.

Stated precisely: **the rule for a null switch selector** and **the rule for a value returned by a switch expression** are two independent matters.

## 5. Ways to handle null before a switch in Java 17

### 5.1. Null is invalid input: reject immediately at the boundary

If the business domain requires a status to always be present:

~~~java
import java.util.Objects;

static String labelRequired(String status) {
    Objects.requireNonNull(status, "status");

    return switch (status) {
        case "OPEN" -> "Open";
        case "CLOSED" -> "Closed";
        default -> "Unsupported";
    };
}
~~~

`Objects.requireNonNull(status, "status")` throws `NullPointerException` with a clearer message naming the parameter that violated the contract. This is suitable for **internal APIs with a non-null precondition**, provided the contract states it clearly.

Do not use it when null is a valid business state and needs to return information to the user.

### 5.2. Null has business meaning: handle with `if` before the switch

For example, an API allowing the user to leave a filter unselected:

~~~java
static String filterDescription(String filter) {
    if (filter == null) {
        return "No filter selected";
    }

    return switch (filter) {
        case "TODAY" -> "Today";
        case "THIS_WEEK" -> "This week";
        case "ALL" -> "All";
        default -> "Invalid filter";
    };
}
~~~

The code reads clearly: one branch checks **absence**, while the switch processes **present valid values**. If `filter = ""` or `filter = "UNKNOWN"`, the switch goes to `default`; that is distinct from null.

### 5.3. Nullable input needing normalization

Example with a status code entered by a user through a form:

~~~java
import java.util.Locale;

static String normalizeAndDescribe(String input) {
    if (input == null || input.isBlank()) {
        return "Missing status";
    }

    String status = input.strip().toUpperCase(Locale.ROOT);

    return switch (status) {
        case "ACTIVE" -> "Active";
        case "SUSPENDED" -> "Suspended";
        case "DELETED" -> "Deleted";
        default -> "Unrecognized status";
    };
}
~~~

In this example:

1. `null` and whitespace-only strings are treated as **missing** data.
2. Valid strings are normalized based on the input contract.
3. The switch compares against canonical codes.
4. `default` catches non-empty but unsupported values.

Not every domain permits such normalization. For instance, case-sensitive identifiers or digital signatures must not be altered before validation.

### 5.4. Substituting null with a default: only when business rules permit

Java 9 added `Objects.requireNonNullElse`, usable in Java 17:

~~~java
import java.util.Objects;

static String languageLabel(String preferredLanguage) {
    String language = Objects.requireNonNullElse(
            preferredLanguage, "en"
    );

    return switch (language) {
        case "vi" -> "Vietnamese";
        case "en" -> "English";
        default -> "Other";
    };
}
~~~

This approach only makes sense if **an absent preference means defaulting to `en`** per product requirements. Do not automatically turn null into `0`, an empty string, or an enum constant when doing so could hide input errors.

### 5.5. Nullable wrapper: check before unboxing

~~~java
static String ratingText(Integer rating) {
    if (rating == null) {
        return "Not rated";
    }

    return switch (rating) {
        case 1 -> "Very low";
        case 2 -> "Low";
        case 3 -> "Average";
        case 4 -> "Good";
        case 5 -> "Excellent";
        default -> "Invalid score";
    };
}
~~~

This is very common when working with database or JSON data: the Java type is `Integer` because the value can be absent, while classification only makes sense for an existing integer.

## 6. When should you choose an `enum` over a `String` selector?

In domain modeling, `String` often comes from external APIs, requests, files, or integration data. If internal states have a finite set of values, **parsing into an enum at the system boundary** can make code clearer.

~~~java
enum JobState {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED
}

static String jobMessage(JobState state) {
    return switch (state) {
        case QUEUED -> "Queued";
        case RUNNING -> "Running";
        case COMPLETED -> "Completed";
        case FAILED -> "Failed";
    };
}
~~~

Strengths of an enum:

- The compiler knows the constant set at compile time.
- You can write an exhaustive switch expression without `default`.
- Avoids string typos wherever code already uses the enum.
- Restricts out-of-contract states from propagating deep into processing layers.

Still, an enum remains a **nullable reference**. And converting external strings into an enum still requires validation:

~~~java
import java.util.Locale;

static JobState parseJobState(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing job state");
    }

    String normalized = raw.strip().toUpperCase(Locale.ROOT);
    try {
        return JobState.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Invalid state: " + raw, ex
        );
    }
}
~~~

At the API layer, you can translate the exception into an appropriate protocol response. Never assume every external String is a valid enum constant.

**Note as enums evolve:** Avoid adding `default` merely to make code compile easily if the goal is to require updating logic whenever a new enum constant is added. With switch expressions on enums, listing constants helps the compiler flag unhandled cases upon recompilation.

## 7. Switch expressions must cover selection cases

### 7.1. Difference between `switch expression` and `switch statement`

A switch statement can simply execute an action and finish:

~~~java
static void printStatus(int status) {
    switch (status) {
        case 200 -> System.out.println("OK");
        case 404 -> System.out.println("Not found");
    }
}
~~~

The example above is valid: if `status` does not match, the statement can do nothing.

A switch expression needs to produce a value:

~~~java
static String statusText(int status) {
    return switch (status) {
        case 200 -> "OK";
        case 404 -> "Not found";
        default -> "Other";
    };
}
~~~

With integer or String selectors in Java 17, `default` is normally required to cover remaining values.

~~~java
// INVALID: switch expression does not cover all possible ints.
//
// String text = switch (status) {
//     case 200 -> "OK";
//     case 404 -> "Not found";
// };
~~~

With an enum, a switch expression can be exhaustive by listing **every enum constant**, like the `PaymentStatus` example above. Even so, that rule still **does not make `null` a valid branch** in Java 17.

### 7.2. A branch can produce a value via expression, `yield`, or `throw`

~~~java
static String responseMessage(int code) {
    return switch (code) {
        case 200 -> "OK";
        case 400 -> {
            String description = "Bad request";
            yield "Client error: " + description;
        }
        case 500 -> throw new IllegalStateException("Server error");
        default -> "Unknown";
    };
}
~~~

- `case 200 -> "OK"`: directly produces a value.
- `case 400 -> { ... yield ...; }`: multiple statements in the branch; `yield` provides the switch expression's value.
- `case 500 -> throw ...`: branch throws an exception without producing a normal value.
- `default`: covers codes other than 200/400/500.

`yield` in a switch expression is not like `return`: `return` exits the method, whereas `yield` hands a value back to the switch expression.

This syntax rule is independent of whether a reference selector can be null. If the selector is null, no branch is chosen to run `yield` or `throw` inside.

### 7.3. The selector is evaluated before branch selection

The selector is an **expression**, not necessarily a variable name:

~~~java
static int readStatus() {
    System.out.println("Reading status");
    return 200;
}

String text = switch (readStatus()) {
    case 200 -> "OK";
    default -> "OTHER";
};
~~~

The expression `readStatus()` is evaluated to get the selector value, and only then does the switch pick a branch. With a nullable reference expression, a null result causes `NullPointerException` per the rules discussed.

Consequently, avoid embedding complex side effects inside the selector. Reading the value once, validating it, and then switching usually makes code easier to understand and log.

## 8. Complete Java 17 example: numbers, nullable wrapper, nullable String, and enum

Save the following code in **SwitchSelectorJava17Demo.java**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class SwitchSelectorJava17Demo {

    enum JobState {
        QUEUED, RUNNING, COMPLETED
    }

    static String fromInt(int statusCode) {
        return switch (statusCode) {
            case 200, 201 -> "SUCCESS";
            case 400 -> "BAD_REQUEST";
            case 404 -> "NOT_FOUND";
            default -> "OTHER";
        };
    }

    static String fromNullableInteger(Integer statusCode) {
        if (statusCode == null) {
            return "NOT_PROVIDED";
        }
        return fromInt(statusCode);
    }

    static String fromNullableString(String rawCommand) {
        if (rawCommand == null || rawCommand.isBlank()) {
            return "MISSING_COMMAND";
        }

        String command =
                rawCommand.strip().toUpperCase(Locale.ROOT);

        return switch (command) {
            case "START" -> "RUN";
            case "STOP" -> "HALT";
            case "RETRY" -> "TRY_AGAIN";
            default -> "UNSUPPORTED_COMMAND";
        };
    }

    static String fromEnum(JobState state) {
        Objects.requireNonNull(state, "state");

        return switch (state) {
            case QUEUED -> "WAITING";
            case RUNNING -> "WORKING";
            case COMPLETED -> "DONE";
        };
    }

    static String fromChar(char grade) {
        return switch (grade) {
            case 'A' -> "EXCELLENT";
            case 'B' -> "GOOD";
            default -> "OTHER_GRADE";
        };
    }

    public static void main(String[] args) {
        System.out.println(fromInt(200));
        System.out.println(fromNullableInteger(null));
        System.out.println(fromNullableString(" start "));
        System.out.println(fromNullableString(null));
        System.out.println(fromEnum(JobState.RUNNING));
        System.out.println(fromChar('A'));
    }
}
~~~

Compile and run on **JDK 17**, without preview enabled:

~~~shell
java -version
javac --release 17 SwitchSelectorJava17Demo.java
java SwitchSelectorJava17Demo
~~~

Output:

~~~text
SUCCESS
NOT_PROVIDED
RUN
MISSING_COMMAND
WORKING
EXCELLENT
~~~

Key design points:

1. `fromInt` uses primitive `int`: selector cannot be null.
2. `fromNullableInteger` handles null **before** delegating to numeric branch selection.
3. `fromNullableString` separates missing input from unsupported command codes.
4. `fromEnum` validates the non-null precondition, then lists all enum constants.
5. `fromChar` illustrates that `char` is a valid selector even though it is not an integer in ordinary usage.
6. All cases use switch syntax standardized in or before Java 17, without `case null`, type patterns in `switch`, or preview guards.

## 9. Common misconceptions about static types and conversions

### 9.1. An `Object` holding a `String` is still not a `String` selector

~~~java
Object raw = "READY";

// INVALID:
// String result = switch (raw) {
//     case "READY" -> "OK";
//     default -> "OTHER";
// };
~~~

If input arrives as `Object` from a generic API, verify the type first:

~~~java
static String classifyObject(Object raw) {
    if (!(raw instanceof String text)) {
        return "Value is not a string";
    }

    return switch (text) {
        case "READY" -> "OK";
        default -> "OTHER";
    };
}
~~~

`instanceof String text` is **pattern matching for instanceof**, stabilized in Java 16 and supported in Java 17. It differs from using a type pattern like `case String text` **inside switch**, which is not stabilized in Java 17.

If `raw` is null, `raw instanceof String text` evaluates to `false`, so the example has dedicated handling for non-string data. There is no need to switch directly on `Object`.

### 9.2. `Number` and `Integer` are not equivalent as selectors

~~~java
Number number = Integer.valueOf(3);

// Cannot switch directly on Number in Java 17.
// String name = switch (number) { ... };
~~~

If an integer value of type `Integer` is needed:

~~~java
static String classifyNumber(Number number) {
    if (!(number instanceof Integer integer)) {
        return "Requires Integer";
    }
    return switch (integer) {
        case 1 -> "ONE";
        case 2 -> "TWO";
        default -> "OTHER";
    };
}
~~~

Do not blindly convert any `Number` to `int` via `intValue()` without domain verification: floating-point numbers can lose fractional parts, `long` can be narrowed out of range, and null throws an error. If the business logic specifically requires one data type, express that via the appropriate type or deliberate value checking.

### 9.3. `long` is not directly supported

~~~java
long id = 2_500_000_000L;

// Invalid in Java 17:
// String label = switch (id) {
//     case 2500000000L -> "LARGE";
//     default -> "OTHER";
// };
~~~

If the domain truly has values larger than `Integer.MAX_VALUE`, use `if`/`else`, `Map<Long, ...>`, or another design. **Do not cast `(int)` on every `long` just to use switch**, as that can lose data.

If the domain is guaranteed to fit in `int` and casting must be checked, `Math.toIntExact(longValue)` can detect out-of-range values with an exception; still, consider whether switch is actually necessary.

### 9.4. `boolean` is not a Java 17 selector

~~~java
boolean enabled = true;

// Invalid:
// String state = switch (enabled) {
//     case true -> "ON";
//     case false -> "OFF";
// };
~~~

For booleans, the conditional operator is usually clearer:

~~~java
String state = enabled ? "ON" : "OFF";
~~~

There is no reason to encode `true`/`false` into `1`/`0` just to use switch.

### 9.5. `case` label type must match the selector

~~~java
int status = 200;

String result = switch (status) {
    case 200 -> "OK";
    default -> "OTHER";
};

// Invalid:
// case "200" -> "OK";
// The string "200" is not a constant matching an int selector.
~~~

With a `String` selector, case labels must be compatible `String` constants. With an enum, use constants belonging to that exact enum. You cannot use pattern type syntax in standard Java 17 switch to mix different value types.

## 10. Real-world problem: distinguishing null, unknown values, and valid values

Suppose a service receives order status from external data. Three categories need to be separated:

| Category | Example | Meaning |
|---|---|---|
| **Missing** | `null` or empty string per API convention | No reliable status data |
| **Unsupported** | `"IN_TRANSIT_UNKNOWN"` | Has a value, but the application does not recognize it yet |
| **Valid** | `"NEW"`, `"PACKED"`, `"SHIPPED"` | Can be processed by business branches |

Example:

~~~java
import java.util.Locale;

static String orderStatusMessage(String externalValue) {
    if (externalValue == null || externalValue.isBlank()) {
        return "Missing order status";
    }

    String status = externalValue.strip()
            .toUpperCase(Locale.ROOT);

    return switch (status) {
        case "NEW" -> "New order";
        case "PACKED" -> "Packed";
        case "SHIPPED" -> "Shipped";
        default -> "Unsupported status: " + status;
    };
}
~~~

This design benefits logs, metrics, and API responses because **missing data** is distinct from **new values or formatting errors**. If an integrating system unexpectedly introduces a new status, the `default` branch makes it clear that this is a case requiring contract review.

For already-validated internal data, converting statuses into an enum can reduce magic strings. Even so, if statuses can expand outside the service's control, plan properly for codes outside the current list.

## 11. Plan for choosing the right solution

When writing a switch expression in Java 17, you can follow this thought process:

**Step 1 — Determine the static type.** Is the selector `int`, a wrapper, `String`, or an enum? If it is `Object`, `Number`, `long`, or an unsupported type, redesign the selection expression.

**Step 2 — Determine whether null is possible.** Primitives cannot be null. `String`, enums, and wrappers can be null, even when business data is "supposed" to always exist.

**Step 3 — Decide what null means.** Is it a contract violation that must throw an exception, an absent input case needing a distinct response, or a request to apply a default value?

**Step 4 — Handle null before the switch.** Use `Objects.requireNonNull`, `if (value == null)`, or a business-meaningful fallback.

**Step 5 — Write exact cases.** Case labels must be compatible with the selector type, using valid constants or enum constants. Ensure the switch expression has complete branches: typically `default` for String/numbers, and listing all enum constants when applicable.

**Step 6 — Only use stable Java 17 syntax.** Do not copy `case null`, `case String s`, `when` guards, or record patterns from newer Java documentation into code required to run with `--release 17`.

**Step 7 — Consider future evolution.** Could status codes grow? Should the selector be an enum or String? Should encountering an unknown code return `UNKNOWN`, throw an error, or be logged for later handling?

### Quick decision table

| Context | Recommended Java 17 approach |
|---|---|
| `int` HTTP status code | `switch (status)` and `default` |
| Nullable `Integer` code | Check null first, then switch |
| String from a request | Check null/blank, normalize if contract allows, then switch |
| Internal status enum | Validate/ensure non-null, list enum constants |
| Large `long` numbers | `if`/`else` or suitable mapping structure |
| Pure true/false logic | `if` or conditional operator |
| Unknown-type `Object` input | Verify type first, then switch on the properly typed value |
| Need `case String s`, `case null` | Consider requiring a newer JDK; do not treat as standard Java 17 syntax |

## 12. Common pitfalls

### Pitfall 1 — Thinking `default` also handles `null`

~~~java
String command = null;
// switch (command) with default still throws NullPointerException.
~~~

**Right:** if null can appear, handle it before the switch.

### Pitfall 2 — Using `case null` from an article about newer Java

~~~java
// case null -> "MISSING"; // preview in Java 17
~~~

**Right:** standard Java 17 does not use this branch. Handle `if (selector == null)` or enforce a non-null contract before the switch.

### Pitfall 3 — Assuming all numbers are supported selectors

`int` is supported, whereas `long`, `float`, and `double` are not standard selectors in stable Java 17. Wrappers such as `Long` and `Double` are also unsupported.

**Right:** check allowed types before picking a switch construct.

### Pitfall 4 — Using `Number`/`Object` because the runtime value is `Integer`/`String`

The compiler relies on the static type of the expression. **Right:** type or check the type before switching, rather than assuming runtime will accept `Object`.

### Pitfall 5 — Forgetting that wrappers and enums can both be null

`Integer` does not have the same null guarantees as `int`. Enums are reference types and can also be null. **Right:** state the contract clearly and check at the appropriate boundary.

### Pitfall 6 — Adding `default` to an enum to mask all new cases

If the team wants the compiler to require updates when adding enum constants, an exhaustive switch expression covering each enum constant can be better than a catch-all `default`. **Right:** choose the strategy based on compatibility requirements and new-state handling.

### Pitfall 7 — Assuming flexible string matching

`"start"`, `"START"`, and `" START "` are different values. **Right:** normalize deliberately according to the data contract.

### Pitfall 8 — Confusing a null result with a null selector

A switch expression branch can return null if the result type allows it; that is **not** `case null`. **Right:** distinguish the value fed into the switch from the value returned by the switch.

## 13. Practice exercises

### Exercise 1 — Classify selector types

Given the variables:

~~~java
byte b = 1;
short s = 2;
char c = 'A';
int i = 3;
long l = 4L;
Integer boxed = 5;
Long boxedLong = 6L;
String text = "OPEN";
Object object = "OPEN";
~~~

Determine which variables can be used directly in `switch (variable)` in standard Java 17. For each unsupported variable, explain why **the static type**, rather than the runtime value, determines compilation outcome.

### Exercise 2 — Null and default

Predict the outcome:

~~~java
static String check(Integer code) {
    return switch (code) {
        case 1 -> "ONE";
        default -> "OTHER";
    };
}
~~~

For `check(1)`, `check(3)`, and `check(null)`, distinguish the case branch, the default branch, and the exception. Then modify the method so null returns `"MISSING"` while still using only standard Java 17 syntax.

### Exercise 3 — Parse a nullable status string

Write `String parseCommand(String value)` satisfying:

- `null` or a whitespace-only string returns `"EMPTY"`.
- `"START"` (case-insensitive, may have leading/trailing whitespace) returns `"RUN"`.
- `"STOP"` returns `"HALT"`.
- Other codes return `"UNSUPPORTED"`.

Use `strip()`, `toUpperCase(Locale.ROOT)`, and a switch expression. Explain why the null check must come **before** `strip()`.

### Exercise 4 — Enum branch coverage

Declare:

~~~java
enum DeliveryState {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED
}
~~~

Write a switch expression mapping the enum to a message without `default`. Try adding `RETURNED` to the enum and recompiling to observe the requirement to update branches. Then consider `DeliveryState state = null`: does listing all constants prevent `NullPointerException`?

### Exercise 5 — Handling `Object` data

An API receives `Object rawStatus` from an external library, but only accepts the string codes `"READY"` and `"BLOCKED"`.

Write Java 17 code that:

1. If `rawStatus` is not a `String`, returns a message indicating the wrong input type.
2. If it is a `String`, checks for blank or invalid cases.
3. Uses a switch expression on the verified `String` variable.
4. Does not switch directly on `Object` or use preview `case String s` or `case null`.

### Exercise 6 — Redesigning selection over `long`

You receive `long` IDs and want to map a few special codes to messages. Propose at least two lossless standard Java 17 approaches; explain when `if`/`else` makes sense, when `Map<Long, String>` is more maintainable, and why casting `(int)` can cause bugs.

## 14. Self-check questions

1. What is a selector expression? How does it differ from the result of a switch expression?
2. Which four primitive types can serve as selectors in standard Java 17?
3. Which four corresponding wrappers are allowed? When do they throw `NullPointerException`?
4. Can `String` and enums be selectors? Can they be null?
5. Why can `long` or `Boolean` not be direct selectors in Java 17?
6. Why can `Object raw = "READY"` still not be switched directly with string labels?
7. Does `default` catch a null selector? Why or why not?
8. What is the status of `case null` in Java 17? When did it become a stable feature?
9. Can a switch expression branch return null? How does this differ from a null selector?
10. Why can a switch expression on an enum omit `default` when all constants are listed?
11. When is `yield` used in a switch expression?
12. Why should null checking, input normalization, and branch selection be separated when handling external data?

## 15. References

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): standardization process of switch expressions in Java 14, the foundation for Java 17.
- [Java Language Specification 17, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): selector rules, `case` labels, supported types, and switch handling.
- [Java Language Specification 17, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): semantics of switch expressions and branch coverage requirements.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): why `case null` and type patterns are not part of Java 17's stable feature set.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): milestone stabilizing pattern matching in switch in Java 21, helping avoid confusion when reading newer documentation.
- [Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/): official documentation for `String`, `Integer`, `Objects`, `Locale`, and other types.

In standard Java 17, keep two independent boundaries in mind: **selectors only support specifically defined types**, and **a null reference selector throws `NullPointerException` before case selection, even when `default` is present**. Checking for null before the switch along with choosing an appropriate static type makes code express its domain contract clearly while avoiding reliance on Java 17 preview syntax.
