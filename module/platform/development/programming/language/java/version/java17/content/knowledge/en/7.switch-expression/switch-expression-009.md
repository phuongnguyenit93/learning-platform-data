# Refactoring Legacy `if` Chains or `switch` Statements to Clear Expressions in Java 17

In Java code, an if/else chain or a switch statement is often used to choose a result value. The older style can introduce a temporary variable, assign values across multiple branches, and repeat return or break statements. When the goal of the branches is simply **producing a single value**, Java 17 lets you use a **switch expression** to express the choice right where the value is used.

Refactoring properly makes code shorter, makes clear that every branch must produce a result, and reduces the risk of forgetting to assign a variable. However, not every if chain or switch should be turned into an expression. You must preserve the conditions, evaluation order, side effects, null handling, default branch, and fall-through behavior of the original program.

Java 17 supports switch expressions officially since Java 14. This lesson uses only syntax and capabilities stabilized in Java 17; it does not use type-pattern switch, record patterns, or case null from newer Java versions.

## 1. Distinguishing switch statement and switch expression

The two constructs look similar syntactically, but have different roles:

- A **Switch statement** is a control-flow statement. It executes statements in the selected branch and can update variables, call methods, log, or mutate state.
- A **Switch expression** is an expression that produces a value. That value can be assigned to a variable, passed to a method, returned from a method, or combined with another expression.

Switch statement example:

~~~java
int day = 2;
String label;

switch (day) {
    case 1:
        label = "Monday";
        break;
    case 2:
        label = "Tuesday";
        break;
    default:
        label = "Other";
}

System.out.println(label);
~~~

Switch expression example:

~~~java
int day = 2;

String label = switch (day) {
    case 1 -> "Monday";
    case 2 -> "Tuesday";
    default -> "Other";
};

System.out.println(label);
~~~

In the second example, switch itself produces the String value. Readers immediately see that each branch provides one result, without searching for where the variable was assigned or whether a break was forgotten.

| Characteristic | Switch statement | Switch expression |
| --- | --- | --- |
| Purpose | Control statement execution | Produce a value |
| Can assign the result directly | Not the nature of a statement; usually assigns an outer variable | Yes: var x = switch (...) { ... }; |
| Can use return switch (...) | No | Yes |
| Requires exhaustive branches to produce a value | Not necessarily; can do nothing | Yes; every execution path must produce a value or fail to complete normally |
| Arrow rule case ... -> | Yes in Java 17 | Yes in Java 17 |
| Colon label case ...: | Yes | Yes, with yield rules when supplying a value |
| break | Commonly ends a switch statement | Not used to provide a value to a switch expression |
| yield | Not used to return a value from a switch statement | Supplies a value to a switch expression |

A switch expression can appear anywhere Java accepts an expression of a matching type. A switch statement cannot be substituted in those positions.

## 2. Switch expression syntax in Java 17

### Arrow rule with a single expression

Usually the most concise form:

~~~java
String category = switch (code) {
    case 200 -> "Success";
    case 400, 422 -> "Client error";
    case 500, 503 -> "Server error";
    default -> "Unknown";
};
~~~

Key points to remember:

- Use an arrow to separate case labels from the rule.
- Multiple labels can share one branch, such as case 400, 422.
- A branch with a single expression returns that expression's value.
- An arrow rule does not automatically fall through to the next branch.
- Do not write break at the end of an arrow rule just to prevent fall-through.

### Arrow rule with a block

If multiple statements are needed before producing a result, use a block and yield:

~~~java
String description = switch (status) {
    case "PAID" -> {
        audit("Payment completed");
        yield "Paid";
    }
    case "PENDING" -> {
        audit("Payment pending");
        yield "Pending";
    }
    default -> "Unspecified";
};
~~~

Yield ends the current branch of the switch expression and provides the value for the entire expression. It differs from return: return exits the running method; yield only returns the value of the switch expression.

If a block has a final expression without yield, Java does not treat that expression as the result automatically:

~~~java
// Wrong: block does not supply a value to the switch expression.
String text = switch (status) {
    case 1 -> {
        "One";
    }
    default -> "Other";
};
~~~

Must be written:

~~~java
String text = switch (status) {
    case 1 -> {
        String value = "One";
        yield value;
    }
    default -> "Other";
};
~~~

### Colon labels and yield

Switch expressions also support familiar colon syntax. When a branch needs to provide a value, use yield:

~~~java
String label = switch (number) {
    case 1:
        yield "One";
    case 2:
        yield "Two";
    default:
        yield "Other";
};
~~~

Colon labels can still be grouped:

~~~java
String dayType = switch (day) {
    case 6:
    case 7:
        yield "Weekend";
    default:
        yield "Weekday";
};
~~~

Arrow rules are generally easier to read and avoid confusion with fall-through. Colon labels are useful when preserving legacy structure or sequential logic across labels, though you must trace paths to yield carefully.

## 3. Converting an if/else chain that returns fixed values

This is the simplest case and usually benefits most from conversion.

### Before: each branch returns a value

~~~java
static String roleName(int role) {
    if (role == 1) {
        return "ADMIN";
    } else if (role == 2) {
        return "EDITOR";
    } else if (role == 3) {
        return "VIEWER";
    } else {
        return "GUEST";
    }
}
~~~

### After: switch expression returns the result

~~~java
static String roleName(int role) {
    return switch (role) {
        case 1 -> "ADMIN";
        case 2 -> "EDITOR";
        case 3 -> "VIEWER";
        default -> "GUEST";
    };
}
~~~

The conversion fits because:

1. All branches test the same role variable.
2. All conditions are equality checks against constants.
3. Every branch returns a String.
4. There is a default branch equivalent to else.

If conditions involve value ranges, multiple variables, or complex boolean expressions, if/else may express intent better. Switch labels in Java 17 are not general-purpose syntax for replacing every boolean condition.

### Case with a guard / priority condition

Old code:

~~~java
static String accessLevel(int role, boolean active) {
    if (!active) {
        return "DISABLED";
    }
    if (role == 1) {
        return "ADMIN";
    }
    if (role == 2) {
        return "EDITOR";
    }
    return "GUEST";
}
~~~

You can keep the priority condition outside and use a switch expression for the role selection part:

~~~java
static String accessLevel(int role, boolean active) {
    if (!active) {
        return "DISABLED";
    }

    return switch (role) {
        case 1 -> "ADMIN";
        case 2 -> "EDITOR";
        default -> "GUEST";
    };
}
~~~

Do not force the active check into a switch just to merge everything into one expression. Keeping the priority condition as an if makes an independent rule clear to readers.

## 4. Converting a switch statement assigning a result variable to a switch expression

This is a common pattern in legacy code: declare a variable beforehand, assign a value in each branch, then break.

### Before

~~~java
static int shippingFee(String zone) {
    int fee;

    switch (zone) {
        case "LOCAL":
            fee = 10;
            break;
        case "REGIONAL":
            fee = 25;
            break;
        case "INTERNATIONAL":
            fee = 80;
            break;
        default:
            fee = 50;
    }

    return fee;
}
~~~

### After

~~~java
static int shippingFee(String zone) {
    return switch (zone) {
        case "LOCAL" -> 10;
        case "REGIONAL" -> 25;
        case "INTERNATIONAL" -> 80;
        default -> 50;
    };
}
~~~

The temporary fee variable disappears. The compiler requires the switch expression to produce an int value on every path that can complete normally.

### Choosing a consistent result data type

Branches of a switch expression must have compatible types so the expression can be assigned or passed to its usage site. Example:

~~~java
int value = switch (kind) {
    case 1 -> 10;
    case 2 -> 20;
    default -> 0;
};
~~~

When branches return different types, Java applies expression typing and numeric promotion rules. Avoid relying on subtle implicit conversions when intent is unclear. Choose a concrete result type or convert explicitly:

~~~java
long value = switch (kind) {
    case 1 -> 10L;
    case 2 -> 20L;
    default -> 0L;
};
~~~

## 5. Converting legacy switch statements with fall-through

This is the part requiring the greatest care. In a colon-style switch statement, without break, return, or another control-transfer statement, execution can continue into the next case group. That behavior is called **fall-through**.

### Fall-through used only to group labels

Legacy code:

~~~java
static String dayType(int day) {
    String result;
    switch (day) {
        case 6:
        case 7:
            result = "Weekend";
            break;
        default:
            result = "Weekday";
    }
    return result;
}
~~~

Here two labels share one result without executing separate logic for case 6 before case 7. Convert to a single arrow rule with multiple labels:

~~~java
static String dayType(int day) {
    return switch (day) {
        case 6, 7 -> "Weekend";
        default -> "Weekday";
    };
}
~~~

### Fall-through that genuinely runs multiple pieces of logic

Example of a legacy switch statement intentionally accumulating values:

~~~java
static int legacyScore(int level) {
    int score = 0;
    switch (level) {
        case 3:
            score += 30;
            // Intentionally fall through to case 2.
        case 2:
            score += 20;
            // Intentionally fall through to case 1.
        case 1:
            score += 10;
            break;
        default:
            score = 0;
    }
    return score;
}
~~~

Results:

| level | Result |
| ---: | ---: |
| 1 | 10 |
| 2 | 30 |
| 3 | 60 |
| Other value | 0 |

If mechanically converted into arrow rules:

~~~java
// Behaviorally wrong: each rule runs alone, without accumulating.
return switch (level) {
    case 3 -> 30;
    case 2 -> 20;
    case 1 -> 10;
    default -> 0;
};
~~~

The result would differ. You can express the computed value directly:

~~~java
static int score(int level) {
    return switch (level) {
        case 3 -> 60;
        case 2 -> 30;
        case 1 -> 10;
        default -> 0;
    };
}
~~~

Or explicitly preserve the accumulation steps inside blocks:

~~~java
static int score(int level) {
    return switch (level) {
        case 3 -> {
            int total = 30;
            total += 20;
            total += 10;
            yield total;
        }
        case 2 -> {
            int total = 20;
            total += 10;
            yield total;
        }
        case 1 -> 10;
        default -> 0;
    };
}
~~~

The second snippet preserves the old effect accurately, though with repeated logic. If the rule is complex, you can extract it into a clearly named method or keep a switch statement if that is easier to understand. **The goal is preserving semantics**, not converting at all costs.

### Colon labels in a switch expression

A switch expression can still use colon labels with yield:

~~~java
static int score(int level) {
    return switch (level) {
        case 3:
            yield 60;
        case 2:
            yield 30;
        case 1:
            yield 10;
        default:
            yield 0;
    };
}
~~~

This snippet states the equivalent result directly rather than simulating each accumulation step. With colon labels, if a statement group intentionally falls through into the next group, analyze execution order and actual yield points carefully. Arrow rules are usually safer because there is no implicit fall-through.

## 6. Converting when a branch needs multiple statements

A switch expression does not require every branch to be a single expression. Use a block when you need to calculate, validate, or log before returning a value:

~~~java
static String paymentMessage(String status, long amount) {
    return switch (status) {
        case "PAID" -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount must not be negative");
            }
            yield "Paid " + amount;
        }
        case "PENDING" -> {
            auditPending(amount);
            yield "Awaiting payment";
        }
        case "FAILED" -> "Payment failed";
        default -> "Unrecognized status";
    };
}

static void auditPending(long amount) {
    // Record information per application requirements.
}
~~~

Inside a block:

- You can declare local variables.
- You can call methods or perform side effects.
- You can throw exceptions.
- If the block completes normally as a switch expression branch, it must supply a result via yield.

A branch that only throws an exception or does not complete normally needs no yield, because it creates no normal path lacking a value:

~~~java
int result = switch (kind) {
    case 1 -> 10;
    case 2 -> throw new IllegalArgumentException("Unsupported kind");
    default -> 0;
};
~~~

## 7. Using switch expressions with enums

Enums are usually an ideal fit for switch expressions, because their constants are defined in a fixed set.

~~~java
enum OrderStatus {
    DRAFT,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "Draft";
        case CONFIRMED -> "Confirmed";
        case SHIPPED -> "Shipped";
        case CANCELLED -> "Cancelled";
    };
}
~~~

Because all existing enum constants are listed, this switch expression needs no default. The compiler verifies exhaustiveness based on the enum constants at compile time. When a constant is added to the enum and the code is recompiled, switch expressions that no longer cover all cases will need updating.

If default is used, code can continue compiling after an enum adds a constant:

~~~java
static String label(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "Draft";
        case CONFIRMED -> "Confirmed";
        case SHIPPED -> "Shipped";
        case CANCELLED -> "Cancelled";
        default -> "Other status";
    };
}
~~~

Which approach to choose depends on the contract:

- If the enum is controlled by the project and every new value must be reviewed, omitting default helps catch changes at compile time.
- If a fallback for new values is desired or the enum library may be updated independently, default can be an intentional choice. However, a generic fallback can hide that the application does not yet understand a new state.

When running a previously compiled binary against a newer version of an enum library, do not assume old compile-time exhaustiveness checks covered new constants. Recompile and retest the application with the deployed dependency version.

## 8. Choosing between if and switch based on condition shape

A switch expression only fits when branches select based on **one selector** and valid case values. Java 17 supports switch with selector types such as byte, short, char, int, their corresponding wrappers, String, and enum.

Standard switch cannot be used on long, float, double, or boolean. Case labels are constants matching the selector, not arbitrary conditions such as x > 10.

| Condition shape | Usually clearer construct | Example |
| --- | --- | --- |
| Comparing one variable against fixed values | Switch expression | Status codes or enum constants |
| Multiple values sharing one result | Switch expression with multiple labels | case 400, 404 |
| Range checks | If/else | score >= 80 |
| Combining multiple variables and conditions | If/else or named method | active && verified && amount > limit |
| Priority condition first, then selecting a code | If followed by switch expression | Check active, then switch on role |
| Multiple independent actions with no single shared value | Switch statement | Call handler, log, update state |

A range-check example that should remain an if:

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("score must be from 0 to 100");
    }
    if (score >= 90) {
        return "A";
    }
    if (score >= 80) {
        return "B";
    }
    if (score >= 70) {
        return "C";
    }
    return "D";
}
~~~

These conditions are ranges and priority-ordered. Converting them to switch by enumerating dozens of cases for individual integers would make code verbose, hard to maintain, and obscure its meaning.

## 9. Handling String, null, and wrappers during conversion

### String switch is case-sensitive

String comparison in switch behaves case-sensitively:

~~~java
static String normalizeStatus(String status) {
    return switch (status) {
        case "paid" -> "PAID";
        case "pending" -> "PENDING";
        default -> "UNKNOWN";
    };
}
~~~

"PAID" does not match "paid". If old code used equalsIgnoreCase, converting directly to switch changes behavior. Normalize beforehand if that is the desired contract:

~~~java
static String normalizeStatus(String status) {
    if (status == null) {
        return "UNKNOWN";
    }

    return switch (status.toUpperCase(java.util.Locale.ROOT)) {
        case "PAID" -> "PAID";
        case "PENDING" -> "PENDING";
        default -> "UNKNOWN";
    };
}
~~~

Only normalize when the domain defines status as case-insensitive. Using Locale.ROOT for technical identifiers avoids dependence on the machine's default locale.

### Null switch selector

In Java 17, regular switches and switch expressions **do not accept null as a valid case label**. If the selector is null, evaluating the switch throws NullPointerException. Therefore, conversion must double-check old code behavior:

~~~java
static String label(String status) {
    if (status == null) {
        return "UNKNOWN";
    }

    return switch (status) {
        case "PAID" -> "Paid";
        case "PENDING" -> "Pending";
        default -> "Other";
    };
}
~~~

Do not confuse default with null handling: default handles selectors different from listed labels, but does not make a null selector valid.

If old code intentionally threw an error on null, you can check explicitly:

~~~java
static String label(String status) {
    java.util.Objects.requireNonNull(status, "status");
    return switch (status) {
        case "PAID" -> "Paid";
        case "PENDING" -> "Pending";
        default -> "Other";
    };
}
~~~

Java 21 added support for handling case null in finalized pattern matching for switch. Do not include that syntax in code that must compile with Java 17.

### Wrapper switches can unbox null

Selectors of type Integer, Short, Byte, or Character can be unboxed when executing switch. If the wrapper is null, the program throws NullPointerException. If old code handled null with an if branch, preserve that check before the switch.

## 10. Differences among break, yield, and return

When converting a switch statement to an expression, you cannot blindly find-and-replace break with yield. Each keyword serves a distinct purpose:

| Keyword | Meaning |
| --- | --- |
| break | Exits the nearest matching switch statement or loop; does not provide a value to a switch expression |
| yield value | Supplies a value and terminates a switch expression branch |
| return value | Exits the current method and returns the method's result |
| continue | Advances to the next iteration according to the enclosing loop's rules |
| throw | Ends the execution path with an exception, without producing a normal value |

Example:

~~~java
static int toCode(String name) {
    return switch (name) {
        case "A" -> 1;
        case "B" -> {
            int code = 2;
            yield code;
        }
        default -> throw new IllegalArgumentException("Unknown name");
    };
}
~~~

Here yield returns 2 to the switch expression, and then the outer return returns that result from the toCode method.

If an old branch used an early return, do not automatically convert it to yield without considering semantics. In a switch expression inside a return statement, yield can end the expression so the method returns the result; however, a return inside a branch may have existed to exit the method early and skip operations after the switch. Preserve the exact control flow.

## 11. Not every switch statement should be converted into an expression

Keep a switch statement if the primary goal is **performing actions** rather than producing a value:

~~~java
static void handle(String event) {
    switch (event) {
        case "CREATED" -> sendCreatedNotification();
        case "DELETED" -> removeSearchIndex();
        case "UPDATED" -> refreshCache();
        default -> logUnknownEvent(event);
    }
}
~~~

The snippet above already uses Java 17 arrow labels inside a switch statement. There is no need to invent a dummy expression just to turn method calls into a value.

Keep a statement or clear if when:

- Each branch has independent side effects with no single shared result.
- Branches execute break, continue, or return to alter enclosing control flow.
- Logic depends on multiple conditions more complex than a single selector.
- Converting would introduce many yield statements or nested blocks that obscure intent.
- Complex sequential fall-through must be preserved.

A switch expression is a tool for expressing **value selection**, not a mandate to replace every control-flow statement.

## 12. Safe workflow for converting legacy code

Before modifying an if chain or switch, clarify current behavior in order:

1. **Identify the selector or condition variable.** Do all branches really classify the same value? If not, keep if or separate the rules.
2. **List every branch and precedence order.** Note the trailing else, default, null branches, and unhandled cases.
3. **Identify the result to produce.** What type does each branch return or assign? Does any branch only perform side effects or exit the method?
4. **Examine break/fall-through carefully.** Distinguish stacked shared labels from intentional multi-group execution.
5. **Check evaluation order and side effects.** A method call, variable increment, or logging call may execute before or after conditions; do not change order accidentally.
6. **Decide null and default behavior.** Default does not handle null; determine whether old code returned a fallback or threw an exception.
7. **Choose arrow rules or colon labels.** Prefer arrows when branches are independent; use blocks and yield when multiple statements are needed.
8. **Compile with the right Java 17 target and test branches.** Do not assume compatibility with Java 17 just because code compiles on a newer JDK.

### Example on evaluation order

Legacy code:

~~~java
if (isAllowed(user) && isReady(loadResource())) {
    return "READY";
}
return "WAIT";
~~~

This cannot be converted to a switch expression just because its result is a string. The condition uses short-circuiting: loadResource() only runs when isAllowed(user) is true. Creating an intermediate variable or precomputing both conditions during a refactor could alter side effects and performance. Keeping if makes sense.

### Example with a shared calculation

If branches simply pick a factor, you can extract the choice into a switch expression and perform the calculation once:

~~~java
static long finalPrice(long basePrice, String tier) {
    int discountPercent = switch (tier) {
        case "GOLD" -> 20;
        case "SILVER" -> 10;
        case "BRONZE" -> 5;
        default -> 0;
    };

    return basePrice * (100 - discountPercent) / 100;
}
~~~

This separates **policy selection** from **policy application**. Still, in real applications you must define rounding rules, overflow handling, and currency units; this integer arithmetic example only illustrates selection structure.

## 13. Combined example: refactoring a request classifier

### Legacy version with if/else

~~~java
static String describe(int statusCode) {
    String message;

    if (statusCode == 200 || statusCode == 201) {
        message = "Success";
    } else if (statusCode == 400 || statusCode == 404) {
        message = "Client error";
    } else if (statusCode == 500 || statusCode == 503) {
        message = "Server error";
    } else {
        message = "Unknown";
    }

    return message;
}
~~~

### Switch expression version

~~~java
static String describe(int statusCode) {
    return switch (statusCode) {
        case 200, 201 -> "Success";
        case 400, 404 -> "Client error";
        case 500, 503 -> "Server error";
        default -> "Unknown";
    };
}
~~~

Branches test discrete values of the same selector, so a switch expression groups values sharing the same result. The meaning of unlisted codes stays unchanged: they still return "Unknown".

### Exhaustive enum variant

~~~java
enum HttpOutcome {
    SUCCESS,
    CLIENT_ERROR,
    SERVER_ERROR
}

static String describe(HttpOutcome outcome) {
    return switch (outcome) {
        case SUCCESS -> "Success";
        case CLIENT_ERROR -> "Client error";
        case SERVER_ERROR -> "Server error";
    };
}
~~~

Enums represent finite value sets better than arbitrary integers. A switch expression forces code to list existing constants when omitting default, helping catch missing branches upon recompilation after an enum changes.

## 14. Compiling and verifying with Java 17

Save the standalone example below as SwitchRefactorDemo.java:

~~~java
public class SwitchRefactorDemo {

    static String roleName(int role) {
        return switch (role) {
            case 1 -> "ADMIN";
            case 2 -> "EDITOR";
            case 3 -> "VIEWER";
            default -> "GUEST";
        };
    }

    static int shippingFee(String zone) {
        return switch (zone) {
            case "LOCAL" -> 10;
            case "REGIONAL" -> 25;
            case "INTERNATIONAL" -> 80;
            default -> 50;
        };
    }

    static String dayType(int day) {
        return switch (day) {
            case 6, 7 -> "Weekend";
            default -> "Weekday";
        };
    }

    static int score(int level) {
        return switch (level) {
            case 3 -> 60;
            case 2 -> 30;
            case 1 -> 10;
            default -> 0;
        };
    }

    public static void main(String[] args) {
        System.out.println(roleName(2));
        System.out.println(shippingFee("LOCAL"));
        System.out.println(dayType(7));
        System.out.println(score(3));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 SwitchRefactorDemo.java
java SwitchRefactorDemo
~~~

Output:

~~~text
EDITOR
10
Weekend
60
~~~

The --release 17 option tells the compiler to enforce Java 17 target language rules, platform APIs, and bytecode format. It helps avoid accidentally using syntax only available in a newer Java release when writing code meant for Java 17.

## 15. Common errors during conversion

| Error | Why it happens | How to fix |
| --- | --- | --- |
| Missing default in switch expression on int or String | Switch expression does not cover all selector values | Add a fallback branch or throw an appropriate exception |
| Using break to return a result | break does not provide a value to a switch expression | Use an arrow expression or yield inside a block |
| Using yield inside a switch statement | yield is for switch expressions | Use break or an appropriate control construct |
| Turning fall-through into independent arrow rules | Arrow rules do not fall through to the next branch | Group labels if only sharing a result; explicitly model steps if fall-through had logic |
| Assuming default also catches null | Null selector throws NullPointerException in Java 17 | Check null before the switch |
| Converting equalsIgnoreCase to a String switch | String switch is case-sensitive | Normalize according to domain rules before switching |
| Using switch for value ranges | Case labels are not arbitrary conditions | Keep if/else for ranges |
| Block branch missing yield | Block completes normally without providing a result | Add yield or change structure |
| Adding an overly broad default for an enum | New constants may silently fall into the fallback | Consider omitting default so the compiler flags them on recompile |
| Creating a result variable just to assign once | Keeping old statement pattern when only a value is needed | Return the switch expression directly |
| Conversion changes method call order | Refactoring precomputes conditions or data | Preserve short-circuiting and side-effect ordering |
| Using Java 21 pattern switch syntax | Not yet officially supported in Java 17 | Use switch expressions with constant labels or stabilized instanceof patterns |

## 16. Selection guidelines after refactoring

After converting, review the structure:

- If each branch **chooses a value**, a switch expression is usually the clearer choice.
- If each branch **performs an action**, a switch statement usually fits.
- If conditions **do not share a single selector**, if/else usually expresses intent better.
- If logic **has priority ordering or range checks**, keep if/else or extract named methods.
- If an enum has **constants controlled by the project**, a switch expression without default can help catch new cases on recompilation.
- If data can be **null**, define the null contract clearly before switching.
- If an old switch had **fall-through**, only convert after understanding what the case groups actually do.

The goal of refactoring is to turn selection logic into a readable value-producing expression while keeping program behavior intact. Java 17 switch expressions shine most when replacing discrete branches that merely compute or choose a value; switch statements and if/else still have clear roles when code requires control flow or complex conditions.
