# Blocks, `yield`, and Result Value Types in Switch Expressions (Java 17)

Since Java 14, Java has had **switch expressions** as a standard feature: `switch` not only chooses a branch to execute statements, it can also **produce a value** to assign to a variable, pass to a method, or combine inside another expression. Java 17 uses this feature stably without needing to enable preview.

When a branch only has a single expression, the arrow syntax `->` is quite direct. But when a branch needs multiple statements — declaring temporary variables, logging, validating data before computing the result — you need to use a **block** and end it with `yield`. At the same time, the data type of the entire switch expression must match the target receiving the result.

This lesson focuses on three interconnected topics:

1. Writing a switch expression branch as a block.
2. Using `yield` to return a branch's value.
3. Understanding how the result type is determined and converted in Java 17.

## 1. From switch statement to switch expression

### 1.1. switch statement performs actions

The traditional switch statement is used to choose a statement branch:

```java
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
        label = "Other day";
}

System.out.println(label);
```

Here `switch` is a **statement**. It controls execution flow; assigning to `label` is written separately inside each branch. If `break` is forgotten in the `case ...:` label style, execution can fall into the next branch (*fall-through*).

### 1.2. switch expression produces a value

With a switch expression, the branch's result is the value of the expression itself:

```java
int day = 2;

String label = switch (day) {
    case 1 -> "Monday";
    case 2 -> "Tuesday";
    default -> "Other day";
};

System.out.println(label);
```

Key differences:

- `switch (...) { ... }` sits in a position expecting a value-producing expression.
- Each branch using `->` creates a *switch rule*; there is no fall-through between rules.
- The switch expression must handle all cases according to Java's rules.
- The branch's value is used as the value of the entire switch expression.
- There is a `;` after `}` when the switch expression is the initializer in the assignment statement in the example above.

A switch expression can appear inside a larger expression:

```java
int price = 100_000;
int discountPercent = 10;

int finalPrice = price - switch (discountPercent) {
    case 0 -> 0;
    case 10 -> price / 10;
    case 20 -> price / 5;
    default -> throw new IllegalArgumentException("Unsupported discount");
};
```

In this example, the switch expression returns the discount amount, while the subtraction is performed in the outer expression.

## 2. Blocks in a switch rule

When a branch only needs a single value, it can be written directly:

```java
String status = switch (code) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Unexpected";
};
```

If multiple steps are needed, a **block** can be written after `->`:

```java
String status = switch (code) {
    case 200 -> {
        System.out.println("Request succeeded");
        yield "OK";
    }
    case 404 -> {
        System.out.println("Resource was not found");
        yield "Not found";
    }
    default -> {
        System.out.println("Unexpected response");
        yield "Unexpected";
    }
};
```

A block can contain normal Java constructs appropriate for the context:

- Local variable declarations.
- Conditional `if` statements.
- Loops.
- Method calls and logging.
- Data validation/normalization statements.
- One or more paths ending with `yield` or completing abruptly with `throw`.

**Important point:** a block does not automatically produce a value just because it contains variables. For every normally completing path of an expression branch, a value must be provided via `yield`. If a valid result cannot be produced, the branch can throw an exception.

## 3. `yield` returns a branch's value

`yield` is the statement used in a switch expression to specify the value that the current branch supplies to the switch expression.

Example:

```java
int score = 85;

String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> {
        String message = "Good";
        yield message;
    }
    case 7 -> "B";
    case 6 -> "C";
    default -> "Needs improvement";
};
```

In the `case 8` branch:

1. Declare the local variable `message`.
2. Assign the value to return to that variable.
3. Use `yield message;` to provide the branch's result.
4. The value is used as the value of the entire switch expression and assigned to `grade`.

`yield` **does not return a result out of the method**. It finishes the targeted switch expression branch. Here is how it differs from `return`:

| Statement | Meaning |
| --- | --- |
| `yield value;` | Supplies `value` as the result of the enclosing switch expression. |
| `return value;` | Terminates the current method and returns the result to the caller. |
| `break;` | Exits a matching loop or switch statement; not a way to return a switch expression value. |
| `continue;` | Jumps to the next loop iteration according to loop rules; does not return a switch expression value. |

### 3.1. `yield` is only needed when a branch uses a block

With an expression rule having a single expression, do not write `yield`:

```java
int value = switch (mode) {
    case 0 -> 10;
    case 1 -> 20;
    default -> 30;
};
```

With a block rule, use `yield`:

```java
int value = switch (mode) {
    case 0 -> {
        int base = 10;
        yield base;
    }
    default -> {
        int base = 20;
        yield base + 10;
    }
};
```

Do not write `case 0 -> { int base = 10; base; }` because a standalone expression statement inside a block does not automatically become the result of the switch expression.

### 3.2. Every path must supply a result

Incorrect example:

```java
String result = switch (code) {
    case 1 -> {
        if (enabled) {
            yield "Enabled";
        }
        // ERROR: if enabled is false, the block completes normally without yielding.
    }
    default -> "Other";
};
```

The compiler reports an error because the `case 1` branch has a path where the block completes normally without supplying a value.

Fix:

```java
String result = switch (code) {
    case 1 -> {
        if (enabled) {
            yield "Enabled";
        }
        yield "Disabled";
    }
    default -> "Other";
};
```

Or if the condition cannot validly continue, throw an exception:

```java
String result = switch (code) {
    case 1 -> {
        if (!enabled) {
            throw new IllegalStateException("Feature is disabled");
        }
        yield "Enabled";
    }
    default -> "Other";
};
```

`throw` ends execution with an exception, so there is no need to produce a normal value for that path.

### 3.3. Do not use `break` in place of `yield`

Incorrect example:

```java
int result = switch (mode) {
    case 1 -> {
        int value = 100;
        break; // ERROR: break does not provide a value for the switch expression.
    }
    default -> 0;
};
```

Fix it to:

```java
int result = switch (mode) {
    case 1 -> {
        int value = 100;
        yield value;
    }
    default -> 0;
};
```

If the goal is to exit the method, use `return` in a method with a matching return type. If the goal is to return a result to the switch expression, use `yield`.

## 4. Using blocks with multiple conditions and calculations

A common scenario is when a switch branch needs multi-step calculations:

```java
public class ShippingDemo {
    static int shippingFee(String zone, int weight) {
        return switch (zone) {
            case "LOCAL" -> {
                int baseFee = 15_000;
                int extra = Math.max(0, weight - 1) * 2_000;
                yield baseFee + extra;
            }
            case "REGIONAL" -> {
                if (weight <= 0) {
                    throw new IllegalArgumentException("weight must be positive");
                }

                int baseFee = 25_000;
                int extra = Math.max(0, weight - 1) * 5_000;
                yield baseFee + extra;
            }
            case "REMOTE" -> {
                if (weight > 20) {
                    throw new IllegalArgumentException("Package is too heavy");
                }
                yield 50_000 + weight * 8_000;
            }
            default -> throw new IllegalArgumentException(
                    "Unknown shipping zone: " + zone);
        };
    }

    public static void main(String[] args) {
        System.out.println(shippingFee("LOCAL", 3));
        System.out.println(shippingFee("REGIONAL", 2));
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 ShippingDemo.java
java ShippingDemo
```

Output:

```text
19000
30000
```

Here each branch can:

- Create temporary variables scoped locally to the block.
- Validate input data.
- Throw an exception if a business condition is invalid.
- Use `yield` to provide the final shipping fee.

The value of the entire switch expression has a type matching the method's `int` return type. As a result, the method only needs a single `return switch (...) { ... };` statement instead of declaring a variable and assigning it in every branch.

Note: this example illustrates switch expression structure. A real fee-calculation application must also clearly specify weight units, rounding, currency, limits, and pricing policies.

## 5. Type of a switch expression's result value

A switch expression is **a typed expression**. That type must fit its usage context: the receiving variable's type, the method's return type, the passed parameter type, or the target type required by an enclosing expression.

Simple example:

```java
int value = switch (option) {
    case 1 -> 10;
    case 2 -> 20;
    default -> 0;
};
```

The branches provide integers and the target context is `int`.

### 5.1. Branches should provide compatible values

Valid example:

```java
Number amount = switch (type) {
    case 1 -> Integer.valueOf(100);
    case 2 -> Double.valueOf(25.5);
    default -> Long.valueOf(0);
};
```

`Integer`, `Double`, and `Long` all have reference conversions to `Number`, so they fit the target type `Number`.

Invalid example:

```java
String result = switch (type) {
    case 1 -> "One";
    case 2 -> 2;
    default -> "Other";
};
```

The `case 2` branch provides an `int`, which cannot be validly converted to `String`. The compiler reports a type error. Decide on a clear result contract:

```java
String result = switch (type) {
    case 1 -> "One";
    case 2 -> Integer.toString(2);
    default -> "Other";
};
```

### 5.2. Target types and target typing

In Java, certain expressions can be type-checked against a **target type** supplied by the usage site. A switch expression can be a *poly expression* when the context supplies an appropriate target type.

Example:

```java
Number result = switch (code) {
    case 1 -> 10;     // int is boxed to Integer, then referenced as Number
    case 2 -> 20.5;   // double is boxed to Double, then referenced as Number
    default -> 0L;    // long is boxed to Long, then referenced as Number
};
```

The target type `Number` allows branch expressions to be checked in that context. This is why a switch expression can combine values of different concrete types if each value is compatible with the target type.

Another example with an interface type:

```java
CharSequence text = switch (kind) {
    case 1 -> "Java";                       // String
    case 2 -> new StringBuilder("17");      // StringBuilder
    default -> new StringBuffer("SE");
};
```

`String`, `StringBuilder`, and `StringBuffer` all implement `CharSequence`, so they can be used in the `CharSequence` target context.

### 5.3. When there is no target type: standalone switch expression

If there is no target type to guide it, Java must determine the type of the switch expression from the result types of its branches. In that case, rules for standalone expressions (*standalone expression*) and compatible common types apply.

Easy-to-understand example:

```java
var message = switch (code) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Other";
};
```

Every branch gives `String`, so `var` infers `message` as `String`.

If branches have different types, the inferred type can be a broader common type or an *intersection type* according to Java type inference rules. Do not guess the type solely from the first branch. When you want a clear contract, declare a concrete target type:

```java
Number value = switch (code) {
    case 1 -> 10;
    default -> 2.5;
};
```

When reading code, distinguish two questions:

- **Is each branch's type convertible to the target type?**
- **If there is no target type, what common type does the compiler infer for the entire expression?**

### 5.4. The result type is not determined only by the branch that actually runs

Suppose:

```java
String result = switch (code) {
    case 1 -> "Success";
    default -> throw new IllegalArgumentException();
};
```

The `default` branch does not provide a normal value because it always throws an exception. The remaining branch provides `String`, so the expression matches the target type `String`.

Conversely, if one branch returns an incompatible type, the fact that the branch **does not execute in the current run** does not make the program compile. The compiler must check every selectable branch, not just the inputs you expect to encounter.

## 6. Numeric conversions, boxing, and result types

When branches return numeric values, pay attention to primitive and wrapper types.

### 6.1. Branches of the same primitive type

```java
int result = switch (level) {
    case 1 -> 100;
    case 2 -> 200;
    default -> 0;
};
```

All branches are `int`, so the result is naturally `int`.

### 6.2. Branches returning wrappers with a Number target type

```java
Number result = switch (level) {
    case 1 -> Integer.valueOf(100);
    case 2 -> Double.valueOf(200.5);
    default -> Long.valueOf(0);
};
```

Each wrapper is a subclass of `Number`. Using the target type `Number` avoids coupling callers to a specific wrapper.

### 6.3. Avoiding unintended type mixing

Example:

```java
var result = switch (level) {
    case 1 -> 10;
    default -> 20L;
};
```

The compiler must apply numeric typing and common-type rules for a standalone expression. If the logic requires a `long` result, declare it explicitly:

```java
long result = switch (level) {
    case 1 -> 10;
    default -> 20L;
};
```

Choosing an explicit target type makes intent easier to read and spares readers from having to deduce arithmetic/boxing rules across branches.

### 6.4. Distinguishing casts from choosing a contract type

Do not cast arbitrarily just to silence compiler errors:

```java
Object result = switch (kind) {
    case 1 -> "Text";
    default -> 100;
};
```

This snippet can compile because both values are objects referenceable via `Object`. However, the caller receives an overly broad type and has to classify it further. If the result should really only be a string, standardize all branches to `String`; if it is a numeric group, consider `Number`; if it represents states with distinct meanings, consider a sealed interface or a dedicated result type.

The result type is part of the **API contract**. Pick a type expressive enough for the data domain without being broader than necessary.

## 7. Using switch expressions with colon labels

Switch expressions do not require every branch to use arrows. Java also allows traditional `case ...:` labels, though you must watch out for fall-through and ending with `yield`.

Example:

```java
int result = switch (option) {
    case 1:
        System.out.println("Option 1");
        yield 10;
    case 2:
    case 3:
        System.out.println("Option 2 or 3");
        yield 20;
    default:
        yield 0;
};
```

Here:

- `case 2:` and `case 3:` are grouped together, entering the same handling code.
- `yield` terminates the branch and supplies the value.
- No path may fall past another label without producing an appropriate result.

With the colon form, without `yield` or abrupt completion, the switch expression may fail to compile. This is an easy spot to confuse with traditional switch statements that typically use `break`.

### 7.1. Do not mix arrow rules and colon labels in the same switch block

Do not write:

```java
int result = switch (option) {
    case 1 -> 10;
    case 2: yield 20; // ERROR: cannot mix two label styles in the same switch block.
    default -> 0;
};
```

Choose one consistent style for the entire switch block. In new Java 17 code, the arrow form is usually easier to read and reduces the risk of fall-through.

### 7.2. When is the colon form needed?

The colon form can be useful when grouping multiple labels or preserving a familiar structure from older code. However, if intentional fall-through is not needed, arrow rules are usually the safer and clearer choice.

In particular, **a switch expression does not use fall-through to produce results**. If multiple labels should share one result, list multiple labels on a single rule:

```java
String dayType = switch (day) {
    case 1, 7 -> "Weekend";
    case 2, 3, 4, 5, 6 -> "Weekday";
    default -> "Invalid day";
};
```

## 8. Exhaustiveness of switch expressions

A switch expression must be **exhaustive**: every possible value of the selector must be handled according to language rules.

### 8.1. With int or String

Types like `int` and `String` can take many values, so `default` is usually needed:

```java
String category = switch (code) {
    case 200 -> "SUCCESS";
    case 400, 404 -> "CLIENT_ERROR";
    case 500 -> "SERVER_ERROR";
    default -> "OTHER";
};
```

If `default` is omitted and not all possible values are covered, the compiler reports that the switch expression is not exhaustive.

### 8.2. With enum

If the selector is an enum and all enum constants are listed, `default` can be omitted:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

String label = switch (priority) {
    case LOW -> "Low";
    case NORMAL -> "Normal";
    case HIGH -> "High";
};
```

When a new constant is added to the enum and the same source code is recompiled, the compiler can remind you that the switch expression needs updating. This is useful because an enum type has an explicitly declared set of values.

If `default` is used, the code can keep compiling without flagging the new constant. Therefore, for internal enums where you want the compiler to catch changes, consider listing all constants explicitly rather than adding `default` just in case.

### 8.3. Null selector

In Java 17, switching on a reference expression whose value is `null` throws a `NullPointerException` when evaluating the switch. Pattern switch syntax with a `case null` label is not a standard switch feature of Java 17.

If `null` is a possible input, handle it beforehand:

```java
String label = value == null
        ? "UNKNOWN"
        : switch (value) {
            case "A" -> "Alpha";
            case "B" -> "Beta";
            default -> "OTHER";
        };
```

Or use an explicit check before evaluating the switch. Do not assume `default` will catch `null`.

## 9. Nested switch expressions and the scope of yield

A switch expression can appear inside the block of another switch expression. `yield` belongs to its nearest enclosing switch expression.

Example:

```java
String message = switch (role) {
    case "ADMIN" -> {
        String permission = switch (level) {
            case 1 -> "READ";
            case 2 -> "WRITE";
            default -> "FULL";
        };
        yield "ADMIN: " + permission;
    }
    case "USER" -> "USER: READ";
    default -> "GUEST";
};
```

Here:

1. The inner switch expression produces the value `permission`.
2. After the inner switch finishes, the `ADMIN` branch block continues executing.
3. The outer `yield` returns `"ADMIN: " + permission` for the outer switch expression.

When writing nested blocks, read each `yield` with respect to its nearest enclosing switch expression. Naming intermediate variables often makes code easier to read than deeply nested expressions.

## 10. Practical example: normalizing data with a switch expression

Suppose an application receives a delivery status code and needs to return a unified result object. Some branches need to validate data, normalize information, and log before returning the result.

Create file **`DeliveryStatusDemo.java`**:

```java
public class DeliveryStatusDemo {
    enum StatusCode {
        CREATED, IN_TRANSIT, DELIVERED, FAILED
    }

    record DeliveryStatus(String code, String message, boolean completed) {
    }

    static DeliveryStatus toStatus(StatusCode code, String reference) {
        if (code == null) {
            throw new IllegalArgumentException("code is required");
        }

        return switch (code) {
            case CREATED -> {
                String normalized = normalizeReference(reference);
                yield new DeliveryStatus(
                        "CREATED",
                        "Shipment " + normalized + " was created",
                        false);
            }
            case IN_TRANSIT -> {
                String normalized = normalizeReference(reference);
                System.out.println("Tracking shipment " + normalized);
                yield new DeliveryStatus(
                        "IN_TRANSIT",
                        "Shipment is on the way",
                        false);
            }
            case DELIVERED -> new DeliveryStatus(
                    "DELIVERED",
                    "Shipment delivered",
                    true);
            case FAILED -> new DeliveryStatus(
                    "FAILED",
                    "Delivery failed",
                    true);
        };
    }

    private static String normalizeReference(String reference) {
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException("reference is required");
        }
        return reference.trim().toUpperCase();
    }

    public static void main(String[] args) {
        DeliveryStatus status =
                toStatus(StatusCode.IN_TRANSIT, "  sh-1701 ");
        System.out.println(status);
    }
}
```

Compile and run:

```bash
javac --release 17 DeliveryStatusDemo.java
java DeliveryStatusDemo
```

Output:

```text
Tracking shipment SH-1701
DeliveryStatus[code=IN_TRANSIT, message=Shipment is on the way, completed=false]
```

The example demonstrates:

- The switch result type is `DeliveryStatus`.
- Simple branches return a record directly.
- Branches needing multi-step processing use a block and `yield`.
- The selector is an enum; all constants are listed exhaustively so `default` is not needed.
- `null` is checked before the switch, because Java 17 switch does not treat `null` as an enum constant or a default case.

When expanding the enum, the compiler can help locate places that need updating. When expanding logic, a block should only contain steps related to producing the branch's result; if processing becomes long or depends on many services, extract it into a separate method to keep the switch readable.

## 11. Common compilation errors

| Pattern | Problem | Fix |
| --- | --- | --- |
| Block ends without `yield` | There is a normally completing path that produces no value | Add `yield` on every path or throw an exception |
| Using `break` to return a value | `break` does not supply a result to a switch expression | Use `yield value;` |
| One branch returns `String`, another returns `int` in a `String` context | Incompatible result types | Standardize branches to a compatible target type |
| Omitting a selector value | Switch expression is not exhaustive | Add missing case(s) or `default` |
| Mixing `case ->` and `case:` | A single switch block cannot mix the two rule/label styles | Consistently choose arrow or colon |
| Writing `yield` in a regular switch statement | No target switch expression to receive the value | Use the appropriate construct; `yield` is for switch expressions |
| Assuming `default` handles `null` | Switching on a null reference throws `NullPointerException` in Java 17 | Check for null before the switch |

### 11.1. Verify the right Java version

Switch expressions have been a standard feature since Java 14. With JDK 17:

```bash
javac -version
java -version
```

You can compile the demo targeting Java 17:

```bash
javac --release 17 ShippingDemo.java
java ShippingDemo
```

If using a newer JDK to build a Java 17 application, `--release 17` makes the compiler restrict standard APIs and bytecode version to Java 17 level. It does not replace testing third-party libraries and the actual runtime environment.

You do not need to enable `--enable-preview` to use switch expressions, block rules, or `yield` in Java 17. The pattern matching for switch syntaxes that were in preview in Java 17 are a separate feature.

## 12. Quick comparison of branch forms

| Branch form | Syntax | When to use |
| --- | --- | --- |
| Arrow expression rule | `case X -> expression;` | Short branch directly producing a value. |
| Arrow block rule | `case X -> { statements; yield value; }` | Branch needing multiple steps, temporary variables, or conditions. |
| Colon labels | `case X: statements; yield value;` | When traditional label structure is needed; must manage fall-through and paths. |
| Exception-throwing branch | `case X -> throw new ...;` | Case where no valid result can be produced. |

For new code, prefer arrow rules when suitable because each branch is independent and has no fall-through. Switch to a block only when multiple steps are genuinely needed; avoid creating a block just to hold a single simple statement.

## 13. Self-check questions

**1. Why is `case 1 -> { int x = 10; }` invalid in a switch expression?**  
Because the block completes normally without producing a value. You need to write `yield x;` or throw an exception.

**2. How do `yield` and `return` differ?**  
`yield` ends the branch and returns a value to the nearest enclosing switch expression; `return` terminates the current method.

**3. Must a simple arrow branch use `yield`?**  
No. `case 1 -> 10;` already supplies the value directly. `yield` is used inside a block of a switch expression.

**4. Can a switch expression branch throw an exception instead of returning a value?**  
Yes. A branch completing abruptly via `throw` does not need to produce a normal value.

**5. Why does `String result = switch (...)` reject a branch returning an `int`?**  
Because the branch's type cannot be converted to the target type `String`. You must normalize the value or choose another result type.

**6. When can `var` make the result type hard to predict?**  
When branches have different types. The compiler must infer a common type according to Java rules; declaring a concrete target type usually makes the contract clearer.

**7. Does `default` catch `null` in Java 17?**  
No. Switching on a null reference expression throws `NullPointerException`; you must handle null before the switch.

**8. Is a preview flag needed for switch expressions in Java 17?**  
No. Switch expressions have been standard since Java 14. Pattern matching for switch is a separate preview feature in Java 17.

## Official references

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expressions, arrow rules, blocks, and `yield`.
- [Java Language Specification, Java SE 17 — `14.11 The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statements and switch rules.
- [Java Language Specification, Java SE 17 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): types, evaluation, and exhaustiveness of switch expressions.
- [Java Language Specification, Java SE 17 — `14.21 The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): rules and target of `yield`.
- [Java 17 javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler and the `--release` option.
