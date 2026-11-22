# Declaring Variables in Case Labels in Java Pattern Matching for switch

## 1. When Can a `case` Declare a Variable?

Starting with **Java 21**, *Pattern Matching for switch* (JEP 441) officially allows writing a **case pattern**: the `case` branch both checks the type of an object and declares a variable to use immediately in the matched branch. For example:

```java
static String describe(Object value) {
    return switch (value) {
        case String text  -> "Chuỗi dài " + text.length();
        case Integer n    -> "Số " + n;
        case null         -> "Không có dữ liệu";
        default           -> "Kiểu khác";
    };
}
```

In `case String text`:

- `String` is the type to check at runtime.
- `text` is a **pattern variable** **declared directly in the case label**. If the selector value is actually a `String`, the variable `text` references the matched object, with **static type `String`**.
- The right-hand side of `->` in the selected branch can call `text.length()` without casting `(String) value`.

Similarly, `case Integer n` declares a variable `n` of type `Integer`. A branch that **does not match** does not initialize its variable and does not execute its associated handler.

Unlike those two branches, **`case null` and `default` do not declare pattern variables**. They are used to classify `null` inputs and all remaining values.

This is the core focus of this lesson: **the syntax for declaring variables in `case`, the conditions under which a variable is initialized, its effective scope, and common mistakes when using case labels**.

**Java version:** `instanceof String text` has been standardized since Java 16, whereas **type patterns in `switch`** were standardized in **Java 21**. All complete programs in this lesson use Java 21 or later and do not require `--enable-preview`. Java 17 only had switch patterns as a preview feature and should not be used as the compilation target for the Java 21 examples below.

## 2. Distinguishing Case Constants from Case Patterns

Not every `case` branch declares a variable. Let's distinguish them clearly:

| Case label | Kind | Declares a new variable? | Meaning |
| --- | --- | --- | --- |
| `case 1` | Constant | No | Matches integer value `1` in an allowed context |
| `case "ready"` | String constant | No | Matches the string according to switch rules |
| `case Status.ACTIVE` | Enum constant | No | Matches the exact enum constant `ACTIVE` of `Status` |
| `case null` | `null` label | No | Receives a `null` selector value |
| `default` | Default label | No | Handles values not matched by other cases, per switch rules |
| `case String text` | **Type pattern** | **Yes: `text`** | Matches a value of type `String` and binds the variable |
| `case Number number` | **Type pattern** | **Yes: `number`** | Matches a value of type `Number` and binds the variable |
| `case Point(int x, int y)` | **Record pattern** | **Yes: `x` and `y`** | Deconstructs the components of record `Point` |
| `case String s when !s.isBlank()` | Type pattern with guard | **Yes: `s`** | Matches the type first, then evaluates the additional condition |

The examples in the table are **illustrative syntax snippets**, valid only when the selector type is compatible with the branches used and the switch structure satisfies other rules such as dominance and exhaustiveness.

The syntax for declaring a variable in a case label does not use `=`:

```java
case String text -> text.toUpperCase();
```

Do not write:

```java
// WRONG: not case pattern syntax.
// case String text = value -> text.toUpperCase();
```

The compiler performs the type check and variable binding automatically. **The variable `text` is not a manual cast**, nor is it a method parameter or a global variable.

## 3. Matching Mechanism and Pattern Variable Initialization

Suppose a method receives an object via `Object value`:

```java
static String kind(Object value) {
    return switch (value) {
        case String text -> "String:" + text.length();
        case Integer n   -> "Integer:" + n;
        case null        -> "NULL";
        default          -> "OTHER";
    };
}
```

The case selection process can be understood in the following steps:

1. Evaluate the **selector** `value` once.
2. If the value is `null`, `case null` is selected.
3. For a non-`null` value, Java evaluates matching cases according to switch rules; if the value is a `String`, the pattern `String text` matches and `text` is bound to that value.
4. If it is not a `String` but is an `Integer`, `Integer n` matches and `n` is bound to the corresponding value.
5. If no preceding case applies, the `default` branch handles the remaining value.

Both `kind("Java")` and `kind(7)` compile because the parameter has static type `Object`. At runtime, the objects have different types, so different cases are selected.

A pattern variable is **only initialized when the pattern has matched successfully**. For example, `kind(7)` does not create a `text` variable usable in the `Integer` case; the `n` variable of the `Integer` case is the one for that execution path.

### The variable's type comes from the pattern, not the selector type

With `Object value`, you cannot directly call `value.length()`, because `Object` has no `length()` method. In the branch:

```java
case String text -> text.length();
```

`text` is declared as `String`, so calling `length()` is valid. **The declared type of `value` does not change from `Object` to `String`**. When you need type-specific APIs, use the pattern variable itself.

### Patterns vs. manual type checking and casting

The old way:

```java
static String before(Object value) {
    if (value instanceof String) {
        String s = (String) value;
        return s.strip();
    }
    return "OTHER";
}
```

With Java 21, you can use a case pattern:

```java
static String after(Object value) {
    return switch (value) {
        case String s -> s.strip();
        default       -> "OTHER";
    };
}
```

The difference is that `s` is declared in the **case label**, rather than declared in a separate statement after the check. However, these are simply two ways to organize the same simple classification; it is not necessary to convert every `if` chain into a switch.

## 4. Variable Scope When Using `case ... ->`

With the **switch rule** syntax using `->`, the pattern variable is in scope in **the body of that exact rule**: the expression, block, or `throw` statement after the arrow.

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "TEXT:" + text.strip();
        case Integer n   -> "NUMBER:" + n;
        default          -> "OTHER";
    };
}
```

In the `String` branch, `text` has type `String` and is in scope; in the `Integer` branch, `n` has type `Integer` and is in scope. **`text` cannot be used in the `Integer` or `default` rule**, because those branches can run when the `String` pattern has not matched.

### 4.1. Variable is in scope inside a block after `->`

```java
static String summarize(Object value) {
    return switch (value) {
        case String text -> {
            String clean = text.strip();

            if (clean.isEmpty()) {
                yield "EMPTY_TEXT";
            }

            yield "TEXT:" + clean.length();
        }
        case Integer n -> {
            int doubled = n * 2;
            yield "INT:" + doubled;
        }
        default -> "OTHER";
    };
}
```

The `String` branch is a **block** containing multiple statements. `text` is usable inside this block, including its nested blocks, because the case has already matched before the block executes. The local variable `clean` is declared *inside* the block and also does not appear in other branches.

Because this is a **switch expression** (returning a value), the blocks use `yield` to supply the value of the expression. `yield` is not a method `return`. In the rule `case Integer n -> { ... }`, `n` is only in scope inside that block.

### 4.2. Variables do not leak out after the switch

```java
static void printInfo(Object value) {
    switch (value) {
        case String text -> System.out.println(text);
        case Integer n   -> System.out.println(n);
        default          -> System.out.println("other");
    }

    // INVALID if uncommented:
    // System.out.println(text);
    // System.out.println(n);
}
```

After the switch completes, there is no guarantee that the `String` branch or the `Integer` branch matched. Each case's variable is not a shared local variable of the method.

### 4.3. Reusing the same variable name across independent cases

```java
static String sameName(Object value) {
    return switch (value) {
        case String item  -> "TEXT:" + item;
        case Integer item -> "INT:" + item;
        default           -> "OTHER";
    };
}
```

This is valid: each `item` is a **separate** pattern variable in its own rule. In the first branch `item` is `String`, and in the second it is `Integer`; the two scopes do not overlap.

For readability, when business logic is complex, distinct names like `text`, `count`, or `order` are usually clearer.

## 5. Pattern Variables Can Be Used in a `when` Guard

Java 21 allows adding a **guard** with `when` to check an additional condition after the type pattern matches:

```java
static String check(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "BLANK";
        case String text                     -> "TEXT:" + text.strip();
        default                              -> "OTHER";
    };
}
```

There are two phases:

1. `value` must match `String text`. If it does not match, the guard `text.isBlank()` **is not evaluated**.
2. If it matches, `text` already has type `String` and is available in the guard. Only when the guard evaluates to `true` does Java select that rule.

A non-`null`, non-blank string such as `"Java"` will not select the first branch because `isBlank()` returns `false`; it continues to match the unguarded `case String text` branch. Both branches can use the name `text` because they are two separate declarations.

### Place guarded branches before general branches

```java
static String lengthKind(Object value) {
    return switch (value) {
        case String s when s.length() >= 5 -> "LONG";
        case String s                      -> "SHORT";
        default                            -> "NOT_STRING";
    };
}
```

This ordering is valid and useful:

- First, it catches strings of length at least 5 characters.
- If it is still a `String` but fails the guard, the second branch handles it.
- All remaining types go to `default`.

**Reversing the order causes a domination error:**

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case String s                      -> "ANY_STRING";
//     case String s when s.length() >= 5 -> "LONG";
//     default                            -> "OTHER";
// };
```

The unguarded `case String s` already covers every non-`null` `String`. The guarded branch after it can never be selected.

### `when` is not a place to declare an arbitrary new typed variable

The syntax for declaring a pattern variable is in `case String s`; `when` is a **boolean expression** that checks an extra condition. You cannot write:

```java
// INVALID:
// case String s when s.length() -> "text";
```

Because `s.length()` returns `int`, not `boolean` or `Boolean`. The valid form is:

```java
case String s when s.length() > 0 -> "non-empty";
```

The line above is just **an illustrative rule**; when placed in a complete switch, you must add appropriate rules for other types and ensure exhaustiveness.

### Guards and `null`

If `value` is `null`, `case String text when text.isBlank()` does not match, so `isBlank()` is not called on `null`. In Java 21, if you need to handle `null`, write a dedicated `case null`. **`default` does not automatically catch `null`** the way one might expect from `if`; without `case null`, a `null` selector typically throws a `NullPointerException`.

## 6. Declaring Multiple Variables via Record Patterns in Case Labels

In addition to type patterns, Java 21 standardized **record patterns** (JEP 440), allowing variables to be declared from a record's components directly in the case label.

Suppose:

```java
record Point(int x, int y) {}
```

With a selector of type `Object`, you can write:

```java
static String pointInfo(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "POINT:" + x + "," + y;
        default                 -> "OTHER";
    };
}
```

What happens with `new Point(2, 5)`?

1. The record pattern `Point(int x, int y)` checks whether the selector is a `Point`.
2. If it matches, the two record components are extracted and bound to **two pattern variables `x` and `y`**, both of type `int`.
3. The right-hand side of `->` can use `x` and `y` directly without calling `point.x()` and `point.y()` if you do not need to keep the whole object.

Compare this with:

```java
case Point point -> "POINT:" + point.x() + "," + point.y();
```

This is a **type pattern** `Point point`, declaring a single variable `point` of type `Point`; it **does not** directly create variables `x` and `y`. Conversely, the record pattern `Point(int x, int y)` creates the two component variables, and does not create a `point` variable in this example.

### Record patterns with guards

```java
static String position(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == y -> "DIAGONAL";
        case Point(int x, int y)             -> "GENERAL_POINT";
        default                              -> "OTHER";
    };
}
```

In the first branch, both `x` and `y` **are already bound** before evaluating `x == y`. If the two coordinates are not equal, Java checks the next record pattern branch. The two occurrences of `x`, `y` belong to different cases, so they are distinct variables.

### `var` in record patterns

You can let the compiler infer component types:

```java
case Point(var x, var y) -> "POINT:" + x + "," + y;
```

With `record Point(int x, int y)`, `x` and `y` are inferred as `int`. This is **`var` in nested type patterns of a record pattern**. Do not confuse this with writing a standalone case pattern like `case var x` by mechanically applying this syntax; this lesson uses the standardized forms illustrated for Java 21.

### Use meaningful variable names and avoid duplicates in the same record pattern

```java
// DOES NOT COMPILE because a record pattern
// declares two variables with the same name:
// case Point(int x, int x) -> "SAME";
```

If you want to check whether two coordinates are equal, use **two differently named variables** and a guard:

```java
case Point(int x, int y) when x == y -> "SAME";
```

This is both syntactically valid and clearly expresses the domain condition.

## 7. `:` vs. `->`: Avoiding Fall-Through with Pattern Variables

Java still supports the **traditional switch statement** using `:` and statement groups. Pattern variables can also be declared in case labels in this form:

```java
static String oldStyle(Object value) {
    switch (value) {
        case String text:
            return "STRING:" + text.length();

        case Integer n:
            return "INTEGER:" + n;

        case null:
            return "NULL";

        default:
            return "OTHER";
    }
}
```

This is **a valid Java 21 method**. `text` is in scope in the statements of the **statement group** attached to `case String text:`; `n` is in scope in the group of `case Integer n:`. Because each group executes `return`, there is no fall-through path from one group to the next.

### Why can fall-through cause a compile error?

Look at this **intentionally invalid** code:

```java
// DOES NOT COMPILE:
// switch (value) {
//     case String text:
//         System.out.println(text);  // No break/return.
//     case Integer number:
//         System.out.println(number.intValue());
//     default:
//         System.out.println("OTHER");
// }
```

If the `String text` branch ran and **fell through** into the `Integer number` branch without exiting, the program could access `number` when the `Integer` pattern never matched. Java 21 rejects this structure to prevent reading an uninitialized pattern variable.

A statement group attached to a case pattern declaring a variable also cannot combine multiple labels in a way that lets the same statement be reached without initializing the required variable:

```java
// DOES NOT COMPILE:
// switch (value) {
//     case String text:
//     case Integer number:
//         System.out.println(number);
//         break;
//     default:
//         break;
// }
```

If entered from `case String text`, `number` has not matched, so the shared group cannot use `number` as initialized.

**Maintainable fix:** prefer `case ... ->` for pattern matching, or ensure every `:` group has a proper exit (`break`, `return`, or `throw`) and never uses a pattern variable in a group reachable from another label.

### Do not confuse with multi-constant case labels

The example below is valid for case constants:

```java
enum Status { NEW, ACTIVE, DONE }

static boolean finished(Status s) {
    return switch (s) {
        case NEW, ACTIVE -> false;
        case DONE        -> true;
    };
}
```

`case NEW, ACTIVE` consists of two **constants** and declares no pattern variables. It is not an example of "two pattern variables in one case label".

In Java 21, a **pattern case label** has the form `case Pattern [when Guard]`; therefore, syntax like `case String s, Integer n -> ...` is not valid for creating two variables for a single rule. Write two separate rules or extract the shared logic into a helper method if needed.

## 8. Variable Naming, Shadowing, and Scope Rules

### 8.1. Cannot declare a name that collides with a local variable already in scope

```java
// DOES NOT COMPILE:
// static String bad(Object value) {
//     String text = "existing";
//     return switch (value) {
//         case String text -> text;
//         default          -> "other";
//     };
// }
```

The local variable `text` is already declared in the method's scope. The compiler does not allow a case pattern to declare another local variable with the same name while it is already in scope.

**Fix by using a different name:**

```java
static String good(Object value) {
    String fallback = "existing";
    return switch (value) {
        case String text -> text;
        default          -> fallback;
    };
}
```

### 8.2. Reusing a name in two different rules is allowed

```java
static String reused(Object value) {
    return switch (value) {
        case String v  -> "S:" + v;
        case Integer v -> "I:" + v;
        default        -> "OTHER";
    };
}
```

The two `v` variables belong to different scopes in separate rules. They do not cause values to be shared across cases.

### 8.3. Pattern variables are not object fields or method-wide locals

```java
// Inside a method receiving Object value:
switch (value) {
    case String text -> System.out.println(text);
    default          -> System.out.println("other");
}

// No variable text is declared for the method here.
// Cannot call text.toUpperCase() after switch.
```

A pattern variable does not "remember" a match result for later use. If you need to use normalized data afterward, **return a result from a switch expression**:

```java
static String normalized(Object value) {
    String result = switch (value) {
        case String s -> s.strip();
        case null     -> "";
        default       -> value.toString();
    };
    return result;
}
```

Here `result` is a normal local variable declared **outside the switch expression**, receiving the value of the expression. That is the variable you can continue using afterward.

### 8.4. Lambdas capturing pattern variables

Inside a case rule, a pattern variable can be used in a lambda if it satisfies the rule that a captured local variable must be `final` or *effectively final*:

```java
// Illustrative snippet in a switch statement only:
case String text -> {
    Runnable action = () -> System.out.println(text.toUpperCase());
    action.run();
}
```

If you reassign `text` and still want a lambda to capture `text`, the compiler will reject it because the variable is no longer *effectively final*. This is the general rule for lambdas capturing local variables, not an exception specific to switch patterns.

## 9. Dominance: When a Broader Case Shadows a Narrower Case

This is an important error when declaring variables in case labels. Suppose the selector is `Object value`:

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case Number number -> "NUMBER";
//     case Integer n     -> "INTEGER"; // Dominated by Number.
//     default            -> "OTHER";
// };
```

An unguarded `case Number number` already matches all `Integer` values, because `Integer` is a subclass of `Number`. Thus `case Integer n` later can never be the first matching branch, so Java reports a **dominated case label** error.

**Correct way: more specific case first:**

```java
static String numberKind(Object value) {
    return switch (value) {
        case Integer n    -> "INTEGER:" + n;
        case Number other -> "NUMBER:" + other;
        default           -> "OTHER";
    };
}
```

Here `numberKind(3)` returns `"INTEGER:3"`; `numberKind(2.5)` returns `"NUMBER:2.5"`. There is no unreachable branch.

### Guards allow placing special cases before general cases

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "NEGATIVE";
        case Integer n            -> "INTEGER";
        default                   -> "OTHER";
    };
}
```

Because the guard is not always true, the first branch **does not dominate** the second branch. Conversely, placing an unguarded `case Integer n` first would dominate the guarded branch after it.

### Catch-all patterns and `default`

On an `Object` selector:

```java
static String everything(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OTHER_OBJECT";
    };
}
```

`case Object o` is a type pattern covering all remaining non-`null` objects, and it creates the variable `o`. For selector type `Object`, this rule is an **unconditional pattern** for objects; do not add `default` after it because it would conflict with the catch-all branch.

**Note:** `case Object o` does not replace the need to handle `null` explicitly if desired. In the example above, `case null` separates that case clearly.

## 10. Exhaustiveness and `null` When Declaring Variables in Case Labels

A **switch expression** must be able to produce a value for every valid case according to Java's exhaustiveness check. For type `Object`, you typically use `default` or an appropriate unconditional pattern:

```java
static int score(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer n   -> n;
        default          -> 0;
    };
}
```

`default` makes the switch expression cover types other than `String` or `Integer`. However, if `null` is passed and there is no `case null`, the switch normally throws `NullPointerException` instead of running `default`. When you want `null` to return `0`, write:

```java
static int safeScore(Object value) {
    return switch (value) {
        case null        -> 0;
        case String text -> text.length();
        case Integer n   -> n;
        default          -> 0;
    };
}
```

`null` is not "an object of every type", so it is not bound to `String text` or `Integer n` in the example above.

### Sealed hierarchies

For types restricted with `sealed`, the compiler knows all subtypes that must be covered:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static String shapeLabel(Shape shape) {
    return switch (shape) {
        case Circle(double r)          -> "CIRCLE:" + r;
        case Rectangle(double w, double h) -> "RECT:" + w + "x" + h;
    };
}
```

The snippet above **illustrates a method** placed in a class alongside matching declarations of `Shape`, `Circle`, and `Rectangle` (which can be member types). Java 21 can prove that the switch expression covers all direct subtypes permitted by `Shape`, so no `default` is needed for non-`null` `Shape` objects.

However, if `shape == null`, omitting `case null` still results in a `NullPointerException`. Exhaustiveness over subtypes does not automatically mean `null` is handled.

**Variable declaration point:** `case Circle(double r)` declares `r`, while `case Rectangle(double w, double h)` declares `w` and `h`. These names are only usable in their respective branches and cannot be accessed across branches.

## 11. Complete Java 21 Example: Type Patterns, Record Patterns, Guards, and Scope

Create a file named **`CaseLabelBindingDemo.java`** with the following content. The types `Point` and `State` are declared inside the class so the example can compile as a single file.

```java
public class CaseLabelBindingDemo {

    record Point(int x, int y) {}

    enum State {
        OPEN, CLOSED
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";

            case String text when text.isBlank() -> "BLANK";
            case String text -> "TEXT:" + text.strip();

            case Integer n when n < 0 -> "NEG:" + n;
            case Integer n -> "INT:" + n;

            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y) -> "POINT:" + x + "," + y;

            default -> "OTHER";
        };
    }

    static String colonStyle(Object value) {
        switch (value) {
            case String text:
                return "COLON-S:" + text.length();

            case Integer n:
                return "COLON-I:" + n;

            case null:
                return "COLON-NULL";

            default:
                return "COLON-OTHER";
        }
    }

    static String stateLabel(Object value) {
        return switch (value) {
            case State.OPEN -> "OPEN";
            case State state -> "STATE:" + state.name();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("  Java  "));
        System.out.println(classify("   "));
        System.out.println(classify(-3));
        System.out.println(classify(7));
        System.out.println(classify(new Point(4, 4)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(true));
        System.out.println(classify(null));

        System.out.println(colonStyle("Cat"));
        System.out.println(colonStyle(12));
        System.out.println(colonStyle(null));

        System.out.println(stateLabel(State.OPEN));
        System.out.println(stateLabel(State.CLOSED));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 CaseLabelBindingDemo.java
java CaseLabelBindingDemo
```

**Expected output:**

```text
TEXT:Java
BLANK
NEG:-3
INT:7
DIAGONAL:4
POINT:2,5
OTHER
NULL
COLON-S:3
COLON-I:12
COLON-NULL
OPEN
STATE:CLOSED
```

### Output explanation

1. `classify("  Java  ")`: matches `String text`; `isBlank()` is false, so the following `String text` branch runs `strip()` and returns `TEXT:Java`.
2. `classify("   ")`: the guard `text.isBlank()` is true, returning `BLANK`.
3. `classify(-3)`: the `int` value is boxed into `Integer` when passed to `Object`. The guard `n < 0` is true, returning `NEG:-3`; for `7`, the guard is false and the general `Integer n` branch returns `INT:7`.
4. Both `Point` values are checked using record patterns. `Point(4, 4)` matches the `x == y` guard; `Point(2, 5)` falls into the remaining `Point(int x, int y)` branch.
5. `true` is boxed into `Boolean` and matches none of `String`, `Integer`, or `Point`, so it returns `OTHER`. `null` is caught by `case null`.
6. `colonStyle` uses `:` syntax; every branch executes `return`, avoiding fall-through and using pattern variables only in their appropriate statement groups.
7. `stateLabel(State.OPEN)` matches the **case constant** `State.OPEN`, creating no variable. `stateLabel(State.CLOSED)` matches the **type pattern** `State state`, so it can call `state.name()` and return `STATE:CLOSED`.

All features used in this program are standardized in Java 21; no preview flags are required. If your IDE is configured with a Java language level lower than 21, raise the project configuration when running this example.

## 12. Common Compile Errors and How to Fix Them

### Error 1: declaring a variable like a local variable right after `case`

```java
// WRONG:
// case String text = (String) value -> text.length();
```

**Fix:** write `case String text -> ...`. This is a type pattern, not a variable declaration statement with assignment.

### Error 2: using a pattern variable in another case

```java
// DOES NOT COMPILE:
// return switch (value) {
//     case String text -> text.length();
//     case Integer n -> text.length(); // text is out of scope
//     default -> 0;
// };
```

**Fix:** use `n` in the `Integer` branch, or place shared logic in a helper method outside the switch with its own parameter when genuinely needed.

### Error 3: combining type patterns with variables into one case list

```java
// DOES NOT COMPILE on Java 21:
// case String s, Integer n -> "MATCHED";
```

**Fix:** use two separate rules or group actual constants into a case list; do not mix case patterns with a list of case constants in Java 21 syntax.

### Error 4: name collision with a variable in an enclosing scope

```java
// DOES NOT COMPILE:
// String text = "outer";
// switch (value) {
//     case String text -> System.out.println(text);
//     default -> {}
// }
```

**Fix:** rename the pattern variable, e.g. `case String matchedText`.

### Error 5: writing a guard before the variable is declared

```java
// INVALID:
// case when text.isBlank() String text -> "BLANK";
```

**Fix:** declare the pattern first, then add the guard: `case String text when text.isBlank() -> ...`.

### Error 6: treating `case null` as a type pattern

```java
// No nullValue variable exists just because of this branch:
// case null -> System.out.println(nullValue);
```

**Fix:** handle `null` directly according to your logic, such as `case null -> "MISSING"`; do not try to access an undeclared pattern variable.

### Error 7: falling through into a branch that declares a variable

```java
// DOES NOT COMPILE:
// switch (value) {
//     case String s:
//         System.out.println(s);
//     case Integer n:
//         System.out.println(n);
//     default:
//         break;
// }
```

**Fix:** use `case String s -> ...` and `case Integer n -> ...`; or separate `:` statement groups and ensure no execution path falls into a group with an unmatched variable.

### Error 8: placing a general pattern before a specific pattern

```java
// DOES NOT COMPILE:
// case Number n -> "NUMBER";
// case Integer n -> "INTEGER";
```

**Fix:** place `case Integer n` before `case Number n`. Variables with the same name in two independent rules are allowed; the real issue in this example is **dominance**.

## 13. Self-Assessment Exercises

### Exercise 1: identifying declared variables

Given the labels:

```java
case "OK" -> "ok";
case String s -> s.strip();
case Point(int x, int y) -> x + "," + y;
case null -> "missing";
```

**Question:** Which labels declare variables? The lines above are only syntax snippets, not necessarily a complete valid switch.

**Answer:** `case String s` declares `s`; `case Point(int x, int y)` declares `x` and `y`. `case "OK"` and `case null` declare no variables.

### Exercise 2: analyzing guards

```java
static String test(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
```

Predict the output:

- `test("Java")` → `"LONG"`.
- `test("Go")` → `"SHORT"`.
- `test(100)` → `"OTHER"`.

Explanation: the guard is only evaluated after the `String s` pattern matches; the rules with `s` have separate scopes. Note that the method does not have `case null`; if `null` is passed, do not assume `default` automatically handles `null`.

### Exercise 3: fixing an out-of-order switch

The following does not compile:

```java
// return switch (value) {
//     case Number n -> "NUMBER";
//     case Double d -> "DOUBLE";
//     default -> "OTHER";
// };
```

**Answer:** `Number n` dominates the `Double d` branch after it. Fix it by putting `case Double d -> "DOUBLE";` before `case Number n -> "NUMBER";`.

### Exercise 4: using a record pattern

Given `record Size(int width, int height) {}`. Write a switch expression accepting `Object` that returns `"SQUARE"` if `width == height`, `"RECTANGLE"` for other `Size` values, and `"OTHER"` for all other types.

**Suggested solution:**

```java
static String kind(Object value) {
    return switch (value) {
        case Size(int w, int h) when w == h -> "SQUARE";
        case Size(int w, int h) -> "RECTANGLE";
        default -> "OTHER";
    };
}
```

This assumes `Size` is appropriately declared in scope. The variables `w`, `h` of the first branch are **not** the same declarations as `w`, `h` of the second branch.

### Exercise 5: choosing `:` or `->`

You are writing a switch that accepts `Object` with multiple type patterns, where each branch has its own variable and complex logic. Explain why `case T t -> { ... }` is usually easier to maintain than `case T t: ...`.

**Suggested answer:** `->` creates a rule with a clear handler scope and no fall-through to other rules, helping prevent paths that access an uninitialized pattern variable. The `:` form is still valid in Java 21, but you must be especially careful with statement groups and `break`, `return`, or `throw`.

## 14. Checklist and Takeaways

Before bringing pattern switch code into a project, verify:

1. **Language version:** use Java 21+ for stable pattern switch support.
2. **Selector:** has a type compatible with each case pattern (especially in inheritance hierarchies and generics).
3. **Variable declaration:** `case T name` declares `name`; `case CONSTANT`, `case null`, and `default` do not.
4. **Guard:** `when` comes **after the pattern**, returns a boolean, and may use the matched pattern variable(s).
5. **Scope:** only use a pattern variable inside the rule or statement group attached to that case, and in its corresponding guard; never in another case or after the switch.
6. **Ordering:** put specific or guarded patterns before general patterns to avoid dominance errors.
7. **Fall-through:** if using `:`, avoid execution paths that leave pattern variables uninitialized; prefer `->` where appropriate.
8. **Exhaustiveness:** switch expressions and enhanced switch statements must cover all required cases; use `default`, an unconditional pattern, or a suitable sealed hierarchy.
9. **Null:** if `null` needs to be handled, write an explicit `case null`; do not assume `default` covers `null`.
10. **Variable names:** avoid colliding with local variables already in scope; choose meaningful names for readability.

**Summary:** A variable in a case label is the result of **pattern matching**, not a variable created for every branch. `case String text` only binds `text` when the selector matches `String`; Java guarantees the variable is initialized inside the guard and the handler of the corresponding branch. When used within its proper scope, case patterns eliminate repetitive casting and make object-classification branches clearer and safer.

## Official References

- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification §6.3.3 — Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3)
- [Java SE 21 Language Specification §14.11 — Switch Statement and Case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
