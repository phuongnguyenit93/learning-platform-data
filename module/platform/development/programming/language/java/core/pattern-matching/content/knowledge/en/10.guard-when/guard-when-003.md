# When Is a Guard Condition Evaluated? — Guard `when` in Java

## 1. Short Answer

In Java 21 **pattern matching for switch**, a guard is the conditional expression following the `when` keyword of a `case` label that has a pattern:

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "Long string";
    case String s -> "Other string";
    default -> "Not a string";
};
~~~

**The `when` condition is evaluated only after the selector value has matched the pattern of that `case` label.** If the pattern does not match, the guard **does not run**. If the pattern matches:

- The guard returns `true`: the `case` label is selected and the branch body is executed.
- The guard returns `false`: that label is **not selected**; Java continues checking the next applicable labels.
- The guard throws an exception: the label selection process terminates with that exception; Java **does not** automatically skip it and move to the next case.

In other words, a `case T t when condition(t)` label is selected when **both conditions** are satisfied: *the pattern matches* **and** *the guard is true*. This rule applies to both **switch statements** and **switch expressions** with patterns.

**Version milestone:** `when` with pattern cases became a standard feature in **Java 21** (JEP 441). Standalone `switch` expressions have been standard since Java 14, whereas `case String s when ...` is not supported as a standard feature in Java 17. The runnable examples in this article use JDK 21 or later.

## 2. Step-by-Step Order of Execution in Java

Consider:

~~~java
Object input = "Java";

String label = switch (input) {
    case String s when s.length() > 3 -> "LONG";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

Java executes in the following logical sequence:

1. **Evaluate the selector expression** `input` to obtain a value. In a single execution of the switch, the selector is evaluated once; it is not recomputed just because a guard returns false.
2. **Determine the matching case label**. For a non-null selector, case labels are checked from top to bottom, following the rules of `switch`.
3. **Test the pattern of the guarded label**. For `case String s when ...`, Java first checks whether the value matches `String s`.
4. **Only when the pattern matches**, the pattern variable `s` is initialized and the guard `s.length() > 3` is evaluated.
5. If the guard is true, execute that branch; if false, continue checking the next case. The part after `->` of a branch whose guard is false is **not** executed.
6. If a label without a guard matches, that label is selected directly. If no specific label applies, `default` may be selected, depending on the switch rules.

A diagram to help remember:

~~~text
Evaluate selector once
          |
          v
   Test current case pattern
          |
     +----+----+
     |         |
 No match    Match
     |         |
     |     Has "when"?
     |       /    \
     |     No     Yes
     |     |       |
     |   Select  Evaluate guard
     |   case      / | \
     |         true false exception
     |          |    |       |
     |       Select Try    Exit switch
     |       case   next   with exception
     |              case
     +--> Try next case label
~~~

Key takeaway: the guard expression sits **between two moments**: after a pattern has matched, **before** the case body is selected. Therefore, do not think of `when` as an `if` that runs unconditionally before all cases, nor as an `if` inside the case body after the case has already been selected.

## 3. Scenarios: When Does the Guard Run and When Is It Skipped?

Example:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() >= 5 -> "LONG";
        case String s -> "SHORT";
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n -> "NONPOSITIVE";
        default -> "OTHER";
    };
}
~~~

This is an **illustrative Java 21 method**; place it inside a class before compiling. The following table assumes the pattern cases are evaluated in the order shown in the example:

| Selector value | Guard `s.isBlank()` | Guard `s.length() >= 5` | Guard `n > 0` | Result |
| --- | --- | --- | --- | --- |
| `"   "` | Evaluated → true | Does not run | Does not run | `BLANK` |
| `"Java"` | Evaluated → false | Evaluated → false | Does not run | `SHORT` |
| `"Java21"` | Evaluated → false | Evaluated → true | Does not run | `LONG` |
| `Integer.valueOf(7)` | Does not run | Does not run | Evaluated → true | `POSITIVE` |
| `Integer.valueOf(-1)` | Does not run | Does not run | Evaluated → false | `NONPOSITIVE` |
| `Double.valueOf(2.5)` | Does not run | Does not run | Does not run | `OTHER` |
| `null` | Does not run | Does not run | Does not run | `NULL` |

Why can `s` be accessed in `when s.length() >= 5`? Because **the `String s` pattern has already matched before that**; the pattern variable `s` is in scope for the guard. When the selector is an `Integer`, Java cannot match `String s`, so it **does not attempt** `s.isBlank()` or `s.length()`.

If the first guard returns false, Java can proceed to check the second guard on a subsequent case. There is no rule saying “at most one guard per switch,” nor is there a rule saying “a false guard immediately jumps to `default`.”

## 4. A Java 21 Program to Observe the Exact Evaluation Order

Save as **`GuardTimingDemo.java`**:

~~~java
public class GuardTimingDemo {
    static int checks;

    static boolean probe(String name, boolean result) {
        ++checks;
        System.out.println("guard:" + name);
        return result;
    }

    static String classify(Object input) {
        return switch (input) {
            case null -> "NULL";

            case String s when probe("long", s.length() > 3)
                    -> "LONG:" + s;

            case String s when probe("nonblank", !s.isBlank())
                    -> "TEXT:" + s;

            case String s -> "OTHER_STRING:" + s;

            case Integer n when probe("positive", n > 0)
                    -> "POSITIVE:" + n;

            case Integer n -> "NONPOSITIVE:" + n;

            default -> "OTHER";
        };
    }

    static void run(Object input) {
        checks = 0;
        String result = classify(input);
        System.out.println("result=" + result + ";checks=" + checks);
    }

    public static void main(String[] args) {
        run("Java");
        run("ab");
        run(" ");
        run(-2);
        run(7);
        run(3.14);
        run(null);
    }
}
~~~

Compile and run with JDK 21:

~~~bash
javac GuardTimingDemo.java
java GuardTimingDemo
~~~

Output:

~~~text
guard:long
result=LONG:Java;checks=1
guard:long
guard:nonblank
result=TEXT:ab;checks=2
guard:long
guard:nonblank
result=OTHER_STRING: ;checks=2
guard:positive
result=NONPOSITIVE:-2;checks=1
guard:positive
result=POSITIVE:7;checks=1
result=OTHER;checks=0
result=NULL;checks=0
~~~

Reading the output by group:

- For `"Java"`, `String s` matches and the `long` guard is true, so there is only **one** `probe` call. Subsequent cases are not tested.
- For `"ab"`, the `long` guard is false; Java continues to test the second `String` case, and the `nonblank` guard is true. Hence **two** `probe` calls and result `TEXT:ab`.
- For `" "`, both `String` guards are false; then the unguarded `case String s` matches and produces `OTHER_STRING: `.
- For `-2` and `7`, only the `Integer n` case with the `positive` guard is evaluated; the `String` guards do not run.
- For `3.14` (type `Double`) and `null`, no `probe` calls occur. `Double` goes to `default`, while `null` goes to `case null`.

The `checks` variable is only for demonstrating how many times guards are evaluated; **do not use side effects like this in guard logic in real applications**. Another call to `classify` starts a new case selection process, so the appropriate guards can be evaluated again.

## 5. How Is a False Guard Different from a False `if` Inside a Case Body?

The two snippets look similar, but they are **not equivalent in case-selection flow**.

**With a guard:**

~~~java
static String guarded(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

For `"ab"`, the first `String` case **does not apply** because the guard is false, so Java tries the second `String` case and returns `SHORT`.

**Only an `if` inside the case:**

~~~java
static String insideCase(Object value) {
    return switch (value) {
        case String s -> {
            if (s.length() > 3) {
                yield "LONG";
            }
            yield "SHORT";
        }
        default -> "OTHER";
    };
}
~~~

For `"ab"`, `case String s` has already been **selected**; the `if` statement only controls how the result is computed **inside the selected branch**—it does not make Java go back and pick another `case` label.

Both examples return the same results for these inputs, but the mechanisms differ:

- `when` decides **whether the case is selected**.
- `if` inside the block decides **what action to take inside the already-selected case**.

Therefore, `when` is especially useful for writing multiple specialized branches on the same type while preserving priority order. When there is only a single branch for that type and the internal handling is simple, an `if` inside the branch can also be easier to read.

## 6. The Selector Is Evaluated Once; Multiple Guards May Run

Another misconception: because Java can try multiple cases, developers sometimes assume the selector expression is also called again.

Standalone example (**Java 21**), save as **`GuardRecordDemo.java`**:

~~~java
public class GuardRecordDemo {
    record Order(int units, String id) {}

    static int sourceCalls;

    static Object source() {
        ++sourceCalls;
        System.out.println("source called");
        return new Order(3, "A1");
    }

    static boolean audit(String name, boolean result) {
        System.out.println("guard:" + name);
        return result;
    }

    static String route(Object order) {
        return switch (order) {
            case null -> "NULL";

            case Order(int units, String id)
                    when audit("bulk", units >= 10)
                    -> "BULK:" + id;

            case Order(int units, String id)
                    when audit("positive", units > 0)
                    -> "SMALL:" + id;

            case Order o -> "EMPTY:" + o.id();

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("result=" + route(source()));
        System.out.println("sourceCalls=" + sourceCalls);
    }
}
~~~

~~~bash
javac GuardRecordDemo.java
java GuardRecordDemo
~~~

Exact output:

~~~text
source called
guard:bulk
guard:positive
result=SMALL:A1
sourceCalls=1
~~~

Here:

1. `source()` is called **once** to produce the selector: an `Order(3, "A1")` record.
2. Java tests the first record pattern. The pattern matches and extracts `units = 3`, `id = "A1"`; **only then** does it call `audit("bulk", units >= 10)`. The guard is false.
3. Java tests the second record pattern; it also matches and calls `audit("positive", units > 0)`. The guard is true.
4. The second case is selected, producing `SMALL:A1`. The `Order o` case below is not used.
5. `sourceCalls` remains 1: testing multiple patterns/guards **does not mean re-evaluating the selector**.

This example also shows that the guard of a **record pattern** is evaluated **after the outermost pattern and its component patterns have matched**. If a component pattern does not match, that label's guard does not run.

## 7. From What Point Can a Guard See the Pattern Variable?

An important scoping rule of `when`:

~~~java
case String s when s.length() > 3 -> "LONG:" + s;
~~~

- `String s` is checked first.
- If it matches, `s` is initialized and **is in scope for the guard expression**.
- If the guard is true and the case is selected, `s` can also be used in the case body.
- If the guard is false, that case label is skipped; you **cannot** use `s` from this label in another case as if it were the same variable.

Error example (code snippet intentionally does not compile):

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "LONG:" + s;
    case Integer n -> "NUMBER:" + s; // Error: s does not belong to this case
    default -> "OTHER";
};
~~~

Each case has its own scope. In a second `case String s` label, if you declare the name `s` again, that is the pattern variable of **another label**, not a variable carried over from the previous case.

Because the pattern has already matched before the guard is evaluated, you do not need to perform a redundant cast:

~~~java
case String s when s.startsWith("ID-") -> s.substring(3);
~~~

Calling `s.startsWith(...)` in the guard is type-safe because `s` has already been successfully assigned a `String`. However, if the pattern is a record pattern with a nullable component, you need to check **that component** for null before calling methods on it (noted in a later section).

## 8. Guards with `&&` and `||`: Short-Circuit Order Still Applies

A guard is a Java expression of type `boolean` or `Boolean`; therefore, the `&&` and `||` operators preserve **short-circuit evaluation**.

Example:

~~~java
case String s when !s.isBlank() && s.length() >= 5 -> "LONG_TEXT";
~~~

Flow:

1. The `String s` pattern must match.
2. Java evaluates `!s.isBlank()`.
3. Only if the left-hand side is true does Java evaluate `s.length() >= 5`.
4. If the final guard result is true, the case is selected; if false, Java tries the next case.

With a guard using `||`:

~~~java
case String s when s.isBlank() || s.startsWith("#") -> "SPECIAL_TEXT";
~~~

The right-hand side runs only when `s.isBlank()` is false. Short-circuit evaluation happens **inside** the guard; the guard itself still starts running only after **the `String` pattern has matched**.

Avoid putting heavy computations, side effects, or state mutations inside a guard. If an expensive expression is called across multiple guards or multiple switch executions, performance and predictability can suffer. Use a guard for a **short, clear boolean condition with minimal or no side effects**.

## 9. False Guard, Guard Throwing an Exception, and Null `Boolean`

Many people only consider true/false and forget the case where a guard **does not complete normally**.

### 9.1. False guard: continue searching for another label

~~~java
static String route(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "EMPTY";
        case String s -> "NON_EMPTY";
        default -> "OTHER";
    };
}
~~~

For `"abc"`, the first `String` pattern matches, the `isEmpty()` guard returns false, and the second `String` case is selected. Java does not throw an exception just because a guard returns false.

### 9.2. Guard throws an exception: the switch terminates with that exception

~~~java
static boolean fail(String text) {
    throw new IllegalStateException("invalid guard");
}

static String risky(Object value) {
    return switch (value) {
        case String s when fail(s) -> "A";
        case String s -> "B";
        default -> "OTHER";
    };
}
~~~

This is **valid illustrative code when placed inside a Java 21 class**. For a `String` selector, the guard `fail(s)` throws an exception. Java **does not** automatically fall through to `case String s -> "B"`; the exception propagates out. If the selector is an `Integer`, the `String` pattern does not match, `fail` **is not called**, and the `default` branch can run.

### 9.3. Null `Boolean` guard: error when unboxing

A guard can have type `Boolean`. Java will **unbox** the returned `Boolean` value to determine true/false. If the `Boolean` is `null`, the unboxing step throws `NullPointerException`. This is **not** a false guard.

Standalone program showing both cases, save as **`GuardFailureDemo.java`**:

~~~java
public class GuardFailureDemo {

    static boolean explode(String text) {
        System.out.println("guard:throw");
        throw new IllegalStateException("guard failed");
    }

    static Boolean maybeNull(String text) {
        return null;
    }

    static String risky(Object input) {
        return switch (input) {
            case String s when explode(s) -> "MATCH";
            case String s -> "FALLBACK";
            default -> "OTHER";
        };
    }

    static String boxed(Object input) {
        return switch (input) {
            case String s when maybeNull(s) -> "TRUE";
            case String s -> "FALSE";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(risky("text"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(risky(42));

        try {
            System.out.println(boxed("abc"));
        } catch (NullPointerException ex) {
            System.out.println("guard unboxing NPE");
        }
    }
}
~~~

~~~bash
javac GuardFailureDemo.java
java GuardFailureDemo
~~~

Output:

~~~text
guard:throw
guard failed
OTHER
guard unboxing NPE
~~~

Explanation:

- `risky("text")`: matches `String`, calls `explode`; the exception is caught **outside** the switch.
- `risky(42)`: does not match `String`; the `explode` guard does not run; `default` returns `OTHER`.
- `boxed("abc")`: matches `String`, the guard returns a `null` `Boolean`; unboxing throws `NPE`; the fallback `String` case **does not run**.

If a `Boolean` value can be null, handle it explicitly in the guard, such as `Boolean.TRUE.equals(maybeNull(s))`, rather than letting Java unbox null. Choosing between false behavior, an exception, or custom error reporting depends on business requirements.

## 10. Guards and a `null` Selector

In Java 21, `switch` supports the `case null` label:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        default -> "OTHER";
    };
}
~~~

When `value == null`:

- `case null` receives the selector.
- The `s.isBlank()` guard **is not called** because no `String` matches `String s` on a null input.
- Without a label handling null, a `switch` on a reference selector can throw `NullPointerException`; `default` generally **does not automatically match null** in Java 21.

Do not write `case null when ...` as if `null` were a type pattern that can take a guard. In Java 21, `when` attaches to a **case pattern**, not to an ordinary constant/null label.

When you want special conditional handling for null, the clearest approach is to handle `case null` (or check for null before the `switch`), and then use `when` for non-null patterns.

## 11. Record Patterns, Null Components, and Guard Timing

In Java 21, a record pattern deconstructs a record object:

~~~java
record Payment(String currency, int amount) {}

static String label(Object value) {
    return switch (value) {
        case Payment(String currency, int amount)
                when currency != null
                        && currency.equals("USD")
                        && amount >= 100
                -> "LARGE_USD";
        case Payment p -> "OTHER_PAYMENT";
        default -> "OTHER";
    };
}
~~~

This is **illustrative code**; place the record and method inside a Java 21 class.

The `when` condition is evaluated only **after** the `Payment(String currency, int amount)` pattern matches and the component variables have been populated. A null component **is not equivalent** to the entire selector being null:

- An actual `Payment` instance can have `currency == null`. With a matching record pattern, the guard can still start running; `currency != null && ...` prevents calling `equals` on null.
- If the outermost selector is null, there is no `Payment` record to match, so the `Payment` case guard does not run.
- If a nested component pattern does not match, that case's guard does not run either.

Do not assume that “because a pattern variable is in the guard, every component variable is non-null.” The null rules for **component patterns** differ from a direct `instanceof` type pattern check; guard design still needs to account for the actual data types.

## 12. Guards Do Not Bypass Other Compile-Time Checks

A guard only affects case selection **at run time**; it cannot make an invalid label valid.

### 12.1. Dominance: specific cases before general ones

Intentionally erroneous code:

~~~java
return switch (value) {
    case String s -> "ALL_STRINGS";
    case String s when s.isBlank() -> "BLANK"; // COMPILE ERROR
    default -> "OTHER";
};
~~~

The first `String` case already covers all `String` values. The guarded branch after it is **dominated**, even though the guard could be true for some strings. The correct order:

~~~java
return switch (value) {
    case String s when s.isBlank() -> "BLANK";
    case String s -> "OTHER_STRING";
    default -> "OTHER";
};
~~~

Both snippets are **illustrative switch method fragments** and must be placed in an appropriate class/method. With `when true`—a constant-true guard—Java treats the label similarly to an unguarded label under dominance rules; do not rely on a constant-true guard to bypass dominated-label checks.

### 12.2. Applicability: pattern type must be compatible with the selector

If the selector has static type `String`, you cannot add `case Integer n when n > 0` just because a guard would “never run.” Java must prove pattern applicability at compile time first. Adding `when` does not fix type incompatibility.

### 12.3. Exhaustiveness: a guard does not cover all values on its own

For a switch expression, the compiler requires the labels to cover all possible values. A guarded label depends on runtime evaluation and can return false, so **it cannot arbitrarily be considered to cover everything**:

~~~java
// INTENTIONALLY INCOMPLETE
static String incomplete(Object value) {
    return switch (value) {
        case String s when s.length() > 0 -> "NONEMPTY";
        // Missing fallback case String s or default.
    };
}
~~~

Fix this by adding an unguarded `String` case and a `default` (or using a complete set of patterns appropriate for the selector type).

**Separate three questions:** Is the pattern applicable? Is any case dominated? Is the switch exhaustive? When the guard is evaluated at run time is only the fourth question; all four matter.

## 13. Performance and Side Effects: How Many Times Is a Guard Called?

In a single case-selection pass:

- Guard of a label whose pattern **does not match**: **0 times**.
- Guard of a label whose pattern matches and is tested: **1 time** for that label check.
- A label with a false guard can lead to **several different guards** being tested next.
- Once a case is selected, subsequent labels do not need to be evaluated for case selection.
- When the `switch` is executed **again** in a loop or another method call, guards can execute again.

Because a guard is a normal Java expression, it **can** call methods, read state, or have side effects. However, writing it like this is often hard to predict:

~~~java
case String s when auditAndMutateState(s) -> "ACCEPT";
~~~

If `auditAndMutateState` mutates global state, behavior can depend on **how many times and in what order** guards are tested, making it very hard to test. A safer way to write it:

~~~java
case String s when s.length() >= 4 -> "ACCEPT";
~~~

Then place operations with side effects inside the **selected case body** (or handle them separately) when truly needed. Keeping guards as pure label-deciding conditions makes code easier to review and maintain.

Do not confuse “the selector is evaluated once” with “all checks run only once.” Different patterns/guards may be tested one after another against **the same selector value**.

## 14. Using Guards in Switch Statements vs. Switch Expressions

The guard evaluation timing rules are **the same** in both Java 21 constructs:

**Switch expression** returns a value:

~~~java
static String asExpression(Object value) {
    return switch (value) {
        case String s when s.length() >= 4 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

**Switch statement** performs an effect:

~~~java
static void asStatement(Object value) {
    switch (value) {
        case String s when s.length() >= 4
                -> System.out.println("LONG");
        case String s -> System.out.println("SHORT");
        default -> System.out.println("OTHER");
    }
}
~~~

Both do: **test pattern → evaluate guard if matched → select case if guard is true**. The difference lies in purpose: a switch expression produces a value, whereas a switch statement executes statements.

In a switch expression using a block, the `yield` keyword provides the value **after the case has been selected**:

~~~java
return switch (value) {
    case String s when s.length() >= 4 -> {
        String cleaned = s.strip();
        yield "LONG:" + cleaned;
    }
    case String s -> "SHORT";
    default -> "OTHER";
};
~~~

`yield` plays no part in deciding whether the guard runs; it is part of the processing **inside the selected branch**.

## 15. Common Mistakes and How to Avoid Them

| Misconception / mistake | Fact | Correct approach |
| --- | --- | --- |
| Guard is checked for every selector value | Guard runs only when **that case's** pattern matches | Place shared checks before the `switch` if needed |
| Guard runs before the pattern variable is assigned | Pattern matches and initializes the variable first, then the guard runs | Use the pattern variable directly in `when` |
| False guard means `default` runs immediately | Java continues checking the next cases | Order fallback cases properly |
| False guard is the same as false `if` inside the case | False guard excludes the case from selection; `if` inside the case only controls the selected branch | Choose the construct that matches your intent |
| At most one guard is evaluated per switch | Multiple guarded cases can be evaluated in sequence | Avoid repeating heavy checks |
| If a guard throws an exception, the next case still runs | An exception aborts label selection | Handle exceptions explicitly if needed |
| A `null` `Boolean` in a guard is false | Unboxing `null` throws `NPE` | Use `Boolean.TRUE.equals(...)` when appropriate |
| Putting `case String s` before a specialized `String` guard | The later case is dominated | Put specialized cases before general ones |
| `when` can be used with `case null` | `when` is part of a guarded pattern label | Handle null via `case null` |
| Adding `when` makes an incompatible pattern compile | Applicability is an independent compile-time condition | Fix the selector/pattern type |
| A guard makes a switch exhaustive on its own | A guard can be false and does not cover all values | Add an unguarded label or `default` |
| Selector is called again for each subsequent guard | Selector is evaluated once per switch execution | Distinguish the selector from each pattern/guard check |

## 16. Self-Check

**Question 1.** Given `Object x = 42;`, does `case String s when expensive(s) -> ...` call `expensive`?

**Answer:** No. `Integer` does not match `String s`; Java does not evaluate the guard.

**Question 2.** With `x = "ab"`, what happens?

~~~java
return switch (x) {
    case String s when s.length() > 3 -> "LONG";
    case String s when s.length() > 0 -> "TEXT";
    case String s -> "EMPTY";
    default -> "OTHER";
};
~~~

**Answer:** The first guard is evaluated and is false; the second guard is evaluated and is true; result is `TEXT`. The third `String` case does not run.

**Question 3.** Does `when s.length() > 0` run before or after the `String s` pattern matches?

**Answer:** After. The variable `s` is initialized from the pattern match first, and then the guard is evaluated.

**Question 4.** When a guard calls a method that throws `IllegalStateException`, does the switch automatically select the next case?

**Answer:** No. Label selection terminates abruptly with the exception; it is not treated as a false guard.

**Question 5.** If `source()` is the selector expression and the first case's guard is false, is `source()` called again for the second case?

**Answer:** Not within the same switch execution. The selector value has been computed once; Java tests the cases against that value.

**Question 6.** With `when Boolean.TRUE.equals(flag)` and `flag == null`, does the guard cause an NPE from auto-unboxing null?

**Answer:** No. `Boolean.TRUE.equals(null)` returns `false`, so the guard is false and Java can test the next case. This differs from writing `when flag` when `flag` is a `null` `Boolean`: that case requires unboxing and can throw `NPE`.

## 17. Official References

The key points are based on the **Java Language Specification 21** and Oracle documentation:

- [JLS `14.11.1.2 — Determining which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): selector, matching, when guards are evaluated, unboxing, true results, and exceptions.
- [JLS `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): case labels, dominance, exhaustiveness.
- [JLS `14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2): how a value matches a pattern and initializes pattern variables.
- [JLS `15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): case selection rules and producing a value from a switch expression.
- [Oracle Java 21 — When Clauses](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `p when e` syntax and pattern variable scope in guards.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): history of standardizing pattern switch in Java 21.

**Key takeaway to remember:** In a Java 21 pattern `switch`, Java **tests the pattern first**. Only when it matches does it **evaluate `when`**. A true guard selects the case; a false guard allows trying the next case; a guard throwing an exception terminates the switch with that exception. The selector is evaluated once per switch execution, though multiple patterns and guards may be tested in sequence.
