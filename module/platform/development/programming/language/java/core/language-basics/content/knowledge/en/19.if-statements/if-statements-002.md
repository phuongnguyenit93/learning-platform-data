# Conditions Must Have Type `boolean` or Unboxed `Boolean` — Java 17+

## 1. The most important rule

In Java, the expression inside the parentheses of an `if` must have type **`boolean`** or **`java.lang.Boolean`** that can be *unboxed* to `boolean`. You cannot directly use a number, string, or object reference as a condition merely because it “has a value”.

~~~java
boolean ready = true;

if (ready) {
    System.out.println("ready");
}
~~~

**Expected stdout:**

~~~text
ready
~~~

With `Boolean`, Java automatically invokes unboxing conversion to obtain a `boolean` when needed:

~~~java
Boolean enabled = Boolean.TRUE;

if (enabled) {
    System.out.println("enabled");
}
~~~

**Expected stdout:**

~~~text
enabled
~~~

**Warning:** if `enabled == null`, unboxing causes a `NullPointerException`. Therefore, distinguish between:

- **Primitive `boolean`:** only `true` or `false`, cannot be null.
- **Wrapper class `Boolean`:** can hold `Boolean.TRUE`, `Boolean.FALSE`, or `null`; you must define how null is handled.

This lesson focuses on the type of the `if` condition and does not expand into branching systems or loops in general.

## 2. `if` syntax and compile-time type checking

Basic syntax:

~~~java
if (condition) {
    // Runs if condition evaluates to true
} else {
    // Runs if condition evaluates to false
}
~~~

The compiler must verify that `condition` has an appropriate boolean/Boolean type **before running**. The actual true or false result only determines which branch executes.

| Expression in `if (...)` | Valid? | Why? |
|---|---|---|
| `true` | Yes | `boolean` literal |
| `ready` with `boolean ready` | Yes | `boolean` variable |
| `enabled` with `Boolean enabled` | Yes | `Boolean` is unboxed |
| `score >= 60` | Yes | Comparison returns `boolean` |
| `value != 0` | Yes | Comparison returns `boolean` |
| `text != null` | Yes | Reference comparison with null returns `boolean` |
| `score` with `int score` | **No** | `int` is not a boolean condition |
| `text` with `String text` | **No** | Java does not treat empty/non-empty String as falsy/truthy |
| `object` with `Object object` | **No** | Java does not treat a non-null object as true |
| `boxedNumber` with `Integer boxedNumber` | **No** | Unboxing `Integer` yields `int`, still not boolean |

Compile-error examples (kept commented out so the example code still runs):

~~~java
int count = 3;
// if (count) { } // WRONG: int cannot be converted to boolean

String title = "Java";
// if (title) { } // WRONG: String cannot be converted to boolean

Object object = Boolean.TRUE;
// if (object) { } // WRONG: static type is Object, not Boolean
~~~

Even when an `Object` variable **is pointing to the `Boolean.TRUE` object**, the compiler sees the static type `Object` in `if (object)`. To use it, you must check/cast the type properly instead of assuming Java infers the object's type at runtime.

## 3. Turning business meaning into boolean expressions

If the input is a number, write an **explicit comparison**:

~~~java
int count = 3;

if (count > 0) {
    System.out.println("positive");
}

if (count != 0) {
    System.out.println("nonzero");
}
~~~

**Expected stdout:**

~~~text
positive
nonzero
~~~

Similarly, with `String`:

~~~java
String title = "Java";
boolean valid = title != null && !title.isBlank();

if (valid) {
    System.out.println("valid title");
}
~~~

Here `title != null`, `!title.isBlank()`, and `valid` all return or hold a **boolean** value; `title` by itself is not a valid condition.

### Common expressions that produce boolean results

| Expression | Result type |
|---|---|
| `a == b`, `a != b` | `boolean` |
| `x < y`, `x >= y` | `boolean` |
| `!active` | `boolean` |
| `hasAccess && isActive` | `boolean` |
| `isAdmin \|\| hasPermission` | `boolean` |
| `name == null` | `boolean` |
| `Boolean.TRUE.equals(flag)` | `boolean` |

**Do not use numeric values 0/1 instead of `false`/`true`**: Java does not perform implicit numeric → boolean conversion.

## 4. `Boolean` in `if`: Java performs unboxing

~~~java
Boolean boxedTrue = Boolean.TRUE;
Boolean boxedFalse = Boolean.FALSE;

if (boxedTrue) {
    System.out.println("true branch");
}

if (boxedFalse) {
    System.out.println("unexpected");
} else {
    System.out.println("false branch");
}
~~~

**Expected stdout:**

~~~text
true branch
false branch
~~~

Semantically, `if (boxedTrue)` needs to convert the `Boolean` value to `boolean` to decide the branch. This is an **unboxing conversion**, not a reference address comparison.

`Boolean` commonly appears in nullable data, collections/generics, or APIs returning three-state results. Unboxing is convenient when the value is guaranteed **non-null**, but can cause runtime errors if data is missing.

## 5. `Boolean null`: valid at compile time, error at runtime

~~~java
Boolean flag = null;

try {
    if (flag) {
        System.out.println("never printed");
    }
} catch (NullPointerException ex) {
    System.out.println("null Boolean -> NullPointerException");
}
~~~

**Expected stdout:**

~~~text
null Boolean -> NullPointerException
~~~

The code **compiles cleanly** because the variable has static type `Boolean`. However, at runtime, Java needs to unbox the null value and throws `NullPointerException` **before selecting a branch**.

The error is not because `if` rejects `Boolean`; it is because the wrapper value cannot be unboxed when null.

**Distinguish the two kinds of errors:**

- `if (123)`: **compile-time** error because the condition has type `int`.
- `Boolean flag = null; if (flag)`: compiles, but fails at **runtime** during unboxing.

## 6. Safe ways to check a nullable `Boolean`

Suppose the requirement is: **allow only when the value is strictly true**.

**Approach 1 — Guard with `&&`:**

~~~java
Boolean enabled = null;
boolean allowed = enabled != null && enabled;
System.out.println(allowed); // false
~~~

`&&` skips the right operand when `enabled != null` is false. Thus, `enabled` is not unboxed when null.

**Approach 2 — Use `Boolean.TRUE.equals`:**

~~~java
Boolean enabled = null;
boolean allowed = Boolean.TRUE.equals(enabled);
System.out.println(allowed); // false
~~~

Calling on the constant object `Boolean.TRUE` does not unbox `enabled`, and is null-safe.

**Approach 3 — Distinguish all three states:**

~~~java
static String describe(Boolean flag) {
    if (flag == null) {
        return "UNKNOWN";
    }
    return flag ? "ON" : "OFF";
}
~~~

| `Boolean` value | `Boolean.TRUE.equals(flag)` | `describe(flag)` |
|---|---|---|
| `Boolean.TRUE` | true | `ON` |
| `Boolean.FALSE` | false | `OFF` |
| `null` | false | `UNKNOWN` |

**Important:** If null means **unknown/unconfirmed**, do not automatically treat null as false without a business decision. `Boolean.TRUE.equals(flag)` fits a “only true passes” rule, but intentionally does not distinguish false from null in the boolean result.

## 7. `flag == true` is not a null guard

~~~java
Boolean flag = null;

// if (flag == true) { }
// At runtime: NullPointerException because flag must be unboxed.
~~~

Comparing with primitive `true` causes `Boolean` to be unboxed, so it is still dangerous when flag is null.

**Use instead:**

~~~java
if (Boolean.TRUE.equals(flag)) {
    // Runs only when flag is non-null and has value true
}
~~~

Or:

~~~java
if (flag != null && flag) {
    // Check null before unboxing
}
~~~

**Do not confuse these meanings:**

- `flag == null`: reference null check, safe.
- `flag == true`: logical comparison to true, can unbox and cause NPE.
- `Boolean.TRUE.equals(flag)`: null-safe **object value** comparison.

To check explicitly for false (not null):

~~~java
boolean explicitlyFalse = Boolean.FALSE.equals(flag);
~~~

When `flag == null`, both `Boolean.TRUE.equals(flag)` and `Boolean.FALSE.equals(flag)` are false.

## 8. `&&` and `||`: place guards before using the value

Java evaluates the operands of `&&` and `||` from left to right, with **short-circuiting**.

~~~java
Boolean approved = null;

boolean allowed = approved != null && approved;
boolean deniedOrUnknown = approved == null || !approved;

System.out.println(allowed);         // false
System.out.println(deniedOrUnknown); // true
~~~

- `approved != null && approved`: if approved is null, skips the right side, safe.
- `approved == null || !approved`: if approved is null, skips the right side, safe.
- `approved != null & approved`: the boolean `&` operator **does not short-circuit**, evaluates the right side, and can throw NPE.
- `approved == null | !approved`: `|` also **does not short-circuit**, and can throw NPE.

Example of `Boolean` on the **right-hand side**:

~~~java
Boolean missing = null;

System.out.println(false && missing); // false, does not unbox missing
System.out.println(true || missing);  // true, does not unbox missing
~~~

However, if the branch containing null **must be evaluated**, unboxing still throws NPE:

~~~java
// boolean bad = true && missing; // NPE at runtime
// boolean bad = false || missing; // NPE at runtime
~~~

**The guard condition must be placed before the unsafe operation.** Simply having `&&` somewhere is not enough for safety if the reference has already been used before being checked.

## 9. Distinguishing `=` from `==` in boolean conditions

A dangerous logic bug:

~~~java
boolean granted = false;

if (granted = true) {
    System.out.println("entered");
}

System.out.println(granted);
~~~

**Expected stdout:**

~~~text
entered
true
~~~

`granted = true` is an **assignment expression** whose type and value are `boolean`. It compiles validly, sets `granted` to true, and causes the `if` branch to run.

If the intent is only to **check**, write:

~~~java
if (granted) {
    // Check true, do not assign
}
~~~

With integers, `if (number = 1)` **does not compile** because the assignment expression has type `int`, not boolean. This is why the `if (booleanVariable = true)` bug easily slips past compile time.

**Recommendation:** avoid assigning state inside an `if` condition unless there is a very clear reason; separate assignments into their own statements.

## 10. Strings `"true"` and `"false"` are not boolean types

~~~java
String input = "true";
// if (input) { } // WRONG: String is not boolean/Boolean
~~~

If data comes from text, you need to **parse the value** first:

~~~java
boolean enabled = Boolean.parseBoolean(input);
if (enabled) {
    System.out.println("parsed true");
}
~~~

**Expected stdout:**

~~~text
parsed true
~~~

`Boolean.parseBoolean(String)` returns true **only if the string equals `"true"` ignoring case**; any other value (including null) returns false. Therefore:

~~~java
System.out.println(Boolean.parseBoolean("yes")); // false
~~~

If the API must **reject invalid text** instead of silently treating it as false, define a strict parser yourself:

~~~java
static boolean parseStrictBoolean(String value) {
    if ("true".equalsIgnoreCase(value)) {
        return true;
    }
    if ("false".equalsIgnoreCase(value)) {
        return false;
    }
    throw new IllegalArgumentException("invalid boolean text");
}
~~~

The parser above distinguishes `"true"` and `"false"` from `"yes"`, `"1"`, or null. Policies for trimming whitespace or accepting other words must be defined according to specific input requirements.

## 11. Complete Java 17 example, runnable via CLI

Create the exact file **`IfBooleanConditionDemo.java`**:

~~~java
public final class IfBooleanConditionDemo {
    private IfBooleanConditionDemo() {}

    static boolean inScoreRange(int score) {
        return score >= 0 && score <= 100;
    }

    static String describe(Boolean flag) {
        if (flag == null) {
            return "UNKNOWN";
        }
        return flag ? "ON" : "OFF";
    }

    static boolean parseStrictBoolean(String value) {
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        throw new IllegalArgumentException("invalid boolean text");
    }

    public static void main(String[] args) {
        boolean active = true;
        if (active) {
            System.out.println("primitive true=entered");
        }
        if (!active) {
            System.out.println("not active=entered");
        } else {
            System.out.println("primitive else=entered");
        }

        int score = 75;
        if (inScoreRange(score)) {
            System.out.println("score in range=true");
        }
        int count = 3;
        if (count > 0) {
            System.out.println("numeric comparison=true");
        }

        Boolean enabled = Boolean.TRUE;
        if (enabled) {
            System.out.println("boxed true=entered");
        }

        Boolean disabled = Boolean.FALSE;
        if (disabled) {
            System.out.println("boxed false=entered");
        } else {
            System.out.println("boxed false=else");
        }

        Boolean missing = null;
        try {
            if (missing) {
                System.out.println("never printed");
            }
        } catch (NullPointerException ex) {
            System.out.println("null condition=NullPointerException");
        }

        System.out.println("safe &&="
                + (missing != null && missing));
        System.out.println("safe true equals="
                + Boolean.TRUE.equals(missing));
        System.out.println("safe false equals="
                + Boolean.FALSE.equals(missing));
        System.out.println("null state=" + describe(missing));
        System.out.println("true state=" + describe(Boolean.TRUE));
        System.out.println("false state=" + describe(Boolean.FALSE));

        try {
            boolean result = missing == true;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("null == true=NullPointerException");
        }

        try {
            boolean result = missing != null & missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("eager guard=NullPointerException");
        }

        System.out.println("skip &&=" + (false && missing));
        System.out.println("skip ||=" + (true || missing));

        try {
            boolean result = true && missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("evaluated null=NullPointerException");
        }

        boolean granted = false;
        if (granted = true) {
            System.out.println("assignment in if=entered");
        }
        System.out.println("granted after assignment=" + granted);

        String input = "TrUe";
        if (parseStrictBoolean(input)) {
            System.out.println("strict parsed=true");
        }
        System.out.println("strict false="
                + parseStrictBoolean("FALSE"));
        System.out.println("lenient yes="
                + Boolean.parseBoolean("yes"));

        try {
            parseStrictBoolean("yes");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later; terminal in the directory containing the file. The program uses only the JDK standard library.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfBooleanConditionDemo.java
java -cp . IfBooleanConditionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfBooleanConditionDemo.java
java -cp . IfBooleanConditionDemo
~~~

### Exact expected stdout

~~~text
primitive true=entered
primitive else=entered
score in range=true
numeric comparison=true
boxed true=entered
boxed false=else
null condition=NullPointerException
safe &&=false
safe true equals=false
safe false equals=false
null state=UNKNOWN
true state=ON
false state=OFF
null == true=NullPointerException
eager guard=NullPointerException
skip &&=false
skip ||=true
evaluated null=NullPointerException
assignment in if=entered
granted after assignment=true
strict parsed=true
strict false=false
lenient yes=false
invalid input=invalid boolean text
~~~

### Points to verify yourself

1. Primitive `boolean` behaves as expected for true/false; integers are only used through the comparison `count > 0`.
2. `Boolean.TRUE` and `Boolean.FALSE` are unboxed to control `if`.
3. `if (missing)` compiles but throws NPE at runtime when unboxing null.
4. `missing != null && missing` and `Boolean.TRUE.equals(missing)` evaluate to false **without throwing an error**.
5. `describe(missing)` preserves the distinct UNKNOWN state, without conflating it with false.
6. `missing == true` and `missing != null & missing` throw NPE because they still require unboxing null.
7. `false && missing` and `true || missing` skip the right operand without unboxing; conversely `true && missing` must evaluate the right side, causing an NPE.
8. `if (granted = true)` demonstrates how assignment instead of a check can compile and mutate state.
9. The strict parser accepts uppercase/lowercase forms of `true`/`false` and rejects `"yes"`; `Boolean.parseBoolean("yes")` silently returns false.

## 12. Common mistakes and how to avoid them

| Mistake | Consequence | Appropriate approach |
|---|---|---|
| `if (1)` | Compile error: int is not boolean | `if (number != 0)` if checking non-zero |
| `if (text)` | Compile error: String is not boolean | `text != null && !text.isBlank()` |
| `if (object)` with Object pointing to Boolean.TRUE | Static type Object is invalid | Use typed Boolean or type check/cast |
| `if (nullableFlag)` when null | Runtime NPE due to unboxing | Guard or `Boolean.TRUE.equals` |
| `if (nullableFlag == true)` thought to be null-safe | Still requires unboxing | `Boolean.TRUE.equals(nullableFlag)` |
| `flag != null & flag` | `&` evaluates the right side too | `flag != null && flag` |
| `flag == null \| !flag` | `\|` evaluates the right side too | `flag == null \|\| !flag` |
| Treating `null` as `false` without business consideration | Loses “unknown” information | Keep UNKNOWN state if needed |
| `if (flag = true)` when intending to check | Assigns true and runs branch | `if (flag)` |
| Using `Boolean.parseBoolean("yes")` as a validating parser | Returns false instead of reporting invalid input | Validate text explicitly |
| Changing `Boolean` to `boolean` when data is nullable | Loses null state or throws NPE during unboxing | Define data contract before changing |

## 13. Exercises with answers

### Exercise A — why is `if (number)` wrong?

~~~java
int number = 5;
// if (number) { System.out.println("yes"); }
~~~

**Answer:** `number` has type `int`, and Java does not allow implicit `int → boolean` conversion. To check for positive, write `if (number > 0)`; for non-zero, write `if (number != 0)`.

### Exercise B — unboxing null

~~~java
Boolean accepted = null;
// if (accepted) { System.out.println("accepted"); }
~~~

**Answer:** If the `if` executes, the program throws `NullPointerException`. You can replace it with:

~~~java
if (Boolean.TRUE.equals(accepted)) {
    System.out.println("accepted");
}
~~~

Prints nothing and does not throw NPE.

### Exercise C — three states

Require a `Boolean` accepting true, false, or null, printing `ON`, `OFF`, `UNKNOWN` respectively.

**Answer:**

~~~java
static String state(Boolean flag) {
    if (flag == null) return "UNKNOWN";
    return flag ? "ON" : "OFF";
}
~~~

You must check for null **before** letting `Boolean` participate in `?:` with two branches that may trigger unboxing.

### Exercise D — short-circuit vs `&` operator

~~~java
Boolean flag = null;
System.out.println(flag != null && flag);
// System.out.println(flag != null & flag);
~~~

**Answer:** the first line prints `false` without NPE. The commented line, if executed, throws NPE because `&` does not short-circuit.

### Exercise E — assignment or comparison?

~~~java
boolean ready = false;
if (ready = true) {
    System.out.println("inside");
}
System.out.println(ready);
~~~

**Answer:**

~~~text
inside
true
~~~

This is a type-valid assignment `ready = true`, though usually unintended. Use `if (ready)` to check the variable.

### Exercise F — handling text input

Given inputs `"TRUE"`, `"FALSE"`, `"yes"`. Only the first two values are considered valid, case-insensitively.

**Answer:** use `parseStrictBoolean` from the full program, returning true for TRUE, false for FALSE, and throwing `IllegalArgumentException` for yes. Do not rely solely on `Boolean.parseBoolean` when you need to distinguish a valid false from invalid text.

## 14. Checklist and conclusion

- [ ] Know that an `if` condition must have type `boolean` or unboxed `Boolean`.
- [ ] Understand that Java **has no implicit truthiness** for numbers, String, or objects.
- [ ] Know that comparisons return boolean, e.g., `count > 0`, `text != null`.
- [ ] Know that `if (Boolean.TRUE)` is valid, while `if ((Boolean) null)` can throw NPE.
- [ ] Distinguish compile-time type errors from runtime null-unboxing errors.
- [ ] Use `Boolean.TRUE.equals(flag)` for a “true only” policy, or `flag != null && flag`.
- [ ] Do not treat null as false if the business logic needs all three states.
- [ ] Know that `flag == true` can unbox null; `flag == null` is a safe null check.
- [ ] Know that `&&`/`||` short-circuit; boolean `&`/`|` do not short-circuit.
- [ ] Do not mistakenly write `if (flag = true)` as a check.
- [ ] Validate String format before converting to boolean if invalid inputs must be rejected.
- [ ] Run `IfBooleanConditionDemo.java` with Java 17+ and compare against exact stdout.

**Conclusion:** Java strictly requires the conditional expression of `if` to have type `boolean` or `Boolean`. With `Boolean`, the compiler allows **unboxing**, but runtime will throw `NullPointerException` if the value is null. Writing clear conditions, guarding null before unboxing, and intentionally choosing a three-state handling policy keep `if` branches type-safe, logically sound, and easy to maintain.