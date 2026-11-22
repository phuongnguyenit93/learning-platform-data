# Return Values from Each Pattern Branch in switch (Java 21)

## 1. Goal: Classify a Value and Produce a Result

In Java, pattern matching for `switch` allows recognizing the type or structure of a value and then using a **pattern variable** directly in the selected branch. When you want to **obtain a common result from the branches**, the appropriate syntax is usually a **switch expression**: the entire `switch (...) { ... }` expression evaluates to **a single value**.

Example:

~~~java
String label = switch (value) {
    case String text -> "TEXT:" + text.toUpperCase();
    case Number number -> "NUMBER:" + number.intValue();
    case null -> "NULL";
    default -> "OTHER";
};
~~~

This is an illustrative snippet inside a method that has an `Object value` variable. The `label` variable is assigned **the value of the single selected branch**, for example `"TEXT:JAVA"` when `value = "java"`. The `String text` pattern determines the branch; the expression after `->` determines **the resulting value**.

After this lesson, you will be able to:

- Distinguish a **switch statement** (executes statements) from a **switch expression** (produces a value).
- Explain how each pattern branch of the form `case Pattern -> expression` produces a result.
- Use `yield` to return a value from a block branch `{ ... }` or a colon-style statement group `case ...:`.
- Understand `throw` branches, `null` handling, label ordering, and `when` guards.
- Determine the common result type of a switch expression and the effect of the target type context.
- Check *exhaustiveness* (covering all cases), including cases using sealed types.
- Recognize compile-time errors when a value is missing, `return`/`break` is used instead of `yield`, an exhaustive branch is missing, or incompatible return types are used.

**Version:** Pattern matching for `switch` and record patterns have been stable features since **Java 21**. The programs with `case String s -> ...` in this lesson use `javac --release 21` and do not require `--enable-preview`. In Java 17, basic switch expressions were already stable, while pattern matching for switch was still a preview feature.

## 2. Distinguishing Three Concepts: Pattern, Branch, and Value

A switch expression branch can be written as:

~~~java
case String s -> "length=" + s.length();
~~~

Reading in order:

1. **Selector expression**: the value inside `switch (value)`; it is evaluated once to select the matching branch.
2. **Case pattern**: `String s`. The label matches if the selector is a suitable `String` object; in that case, `s` is bound to the object and has static type `String`.
3. **Rule expression**: `"length=" + s.length()`. When that branch is selected, Java evaluates this expression and uses the result as **the value of the entire switch expression**.

A switch expression using arrow syntax has three important forms of rule body:

| Rule body | Effect | Example |
| --- | --- | --- |
| An expression | The value of the expression becomes the branch result | `case String s -> s.length();` |
| A block `{ ... }` | Can execute multiple statements; requires `yield value;` on normal completion paths | `case String s -> { int n = s.length(); yield n; }` |
| A `throw` statement | Throws an exception; the branch does not produce a normal result | `case null -> throw new IllegalArgumentException("null");` |

**Do not confuse** the semicolon after an `->` rule with `return`. The `s.length()` part is an expression that produces a value; a switch expression can be placed on the right-hand side of an assignment, in a method's `return`, or as a method argument.

## 3. Complete Example: Each Pattern Returns a Different String

Save the file `SwitchBranchValueDemo.java`:

~~~java
public class SwitchBranchValueDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s -> "TEXT:" + s.toUpperCase();
            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n.doubleValue();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe("java"));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(new Object()));
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac --release 21 SwitchBranchValueDemo.java
java SwitchBranchValueDemo
~~~

Exact output:

~~~text
NULL
BLANK
TEXT:JAVA
INTEGER:7
NUMBER:2.5
OTHER
~~~

Breakdown of the value from each branch:

| Input | Selected branch | Return value |
| --- | --- | --- |
| `null` | `case null` | `"NULL"` |
| `"   "` | `case String s when s.isBlank()` | `"BLANK"` |
| `"java"` | `case String s` | `"TEXT:JAVA"` |
| `7` | `case Integer n` | `"INTEGER:7"` |
| `2.5` | `case Number n` | `"NUMBER:2.5"` |
| `new Object()` | `default` | `"OTHER"` |

Here, the parameter type of `describe` is `Object`. At runtime, exactly one branch is selected. In the `String s` branch, the compiler knows `s` is a `String`; in the `Number n` branch, the compiler knows `n` is a `Number`. Each rule evaluates to a `String`, so the result can be returned from the `describe` method, which has return type `String`.

**Note on ordering:** `case Integer n` must appear before `case Number n` if you want to distinguish `Integer`, because `Integer` is a subtype of `Number`. If `Number n` is placed first, the `Integer n` case after it is *dominated* (unreachable) and is rejected by the compiler.

## 4. The `when` Guard Affects Branch Selection, Not the Value Itself

In the example above, `case String s when s.isBlank()` further classifies empty or whitespace-only strings:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "TEXT:" + s.toUpperCase();
~~~

Process:

1. Java attempts to match `String s`. If it is not a `String`, the `when` guard is not evaluated.
2. If it matches, `s` has type `String` and is used in `s.isBlank()`.
3. If the guard is true, Java selects the rule returning `"BLANK"`.
4. If the guard is false, Java checks the next label and may select the `case String s` rule returning `"TEXT:..."`.

The `when` guard is a **condition for selecting the branch**, not the value of the switch expression. The resulting value is still determined by the expression or `yield` in the rule body.

A broader branch placed before a more specific branch can cause a dominance error. Place special cases (such as blank strings) before the general case (any string), and subtypes (such as `Integer`) before supertypes (such as `Number`) when both need to be handled.

## 5. When Multiple Statements Are Needed: Blocks and `yield`

A rule may need intermediate calculations, logging, or multiple steps. In that case, write a block:

~~~java
case String s -> {
    int normalizedLength = s.strip().length();
    yield normalizedLength * 10;
}
~~~

In a **switch expression**, `yield` is the statement that returns a value **for the innermost enclosing switch expression**. It differs from `return`, which returns from the method (and is forbidden inside a switch expression block in this context), and differs from `break`, which is used to control a traditional switch statement.

Complete example using both a type pattern and a record pattern (Java 21). Save `SwitchYieldValueDemo.java`:

~~~java
record Point(int x, int y) {}

public class SwitchYieldValueDemo {
    static int score(Object value) {
        return switch (value) {
            case null -> 0;
            case String s -> {
                int normalizedLength = s.strip().length();
                yield normalizedLength * 10;
            }
            case Point(int x, int y) -> {
                int squaredDistance = x * x + y * y;
                yield squaredDistance;
            }
            case Number n -> n.intValue();
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(score(" java "));
        System.out.println(score(new Point(3, 4)));
        System.out.println(score(7));
        System.out.println(score(null));
        System.out.println(score(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchYieldValueDemo.java
java SwitchYieldValueDemo
~~~

Output:

~~~text
40
25
7
0
-1
~~~

Explanation:

- `" java "` matches `String s`; after `strip()`, 4 characters remain, and `yield 4 * 10` produces the value `40` from the switch expression.
- `new Point(3, 4)` matches the record pattern `Point(int x, int y)`; the two component variables `x` and `y` can be used in the block; `yield 3*3 + 4*4` is `25`.
- `7` matches `Number n` and the single-expression rule `n.intValue()` directly returns `7`, without needing `yield`.
- `null` has its own rule producing `0`.
- Any value other than those patterns goes to `default` and produces `-1`.

All branches that complete normally produce an `int`. A block branch in a switch expression **cannot complete normally without `yield`**. If the block neither produces a value nor throws an exception or terminates control flow validly, the compiler reports an error.

### `yield` Does Not Exit the Method

Consider:

~~~java
int result = switch (value) {
    case String s -> {
        yield s.length();
    }
    default -> 0;
};
System.out.println(result);
~~~

This is an illustrative snippet inside a method that has `Object value`. The statement `yield s.length();` causes the switch expression to complete with the corresponding value; afterward, the program continues to `System.out.println(result)`. If `yield` were replaced with `return`, the semantics would be different, and Java does not allow `return` to exit out of a switch expression.

## 6. Switch Expressions Can Still Use Colon Syntax and `yield`

The arrow form is easy to read, but Java also allows writing a **switch expression** with colon-style *switch-labeled statement groups*. To make each path produce a value, use `yield` in those groups.

Save `SwitchColonValueDemo.java`:

~~~java
public class SwitchColonValueDemo {
    static String describe(Object value) {
        String result = switch (value) {
            case null:
                yield "NULL";
            case String s:
                if (s.isBlank()) {
                    yield "EMPTY";
                }
                yield s.toUpperCase();
            case Number n:
                yield "N:" + n.intValue();
            default:
                yield "OTHER";
        };
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("java"));
        System.out.println(describe(12));
        System.out.println(describe(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchColonValueDemo.java
java SwitchColonValueDemo
~~~

Output:

~~~text
NULL
EMPTY
JAVA
N:12
OTHER
~~~

Analysis:

- `case String s:` has two paths: if `s.isBlank()`, `yield "EMPTY";`; otherwise, `yield s.toUpperCase();`. Both supply a value for **the entire switch expression**.
- `case Number n:` uses the pattern variable `n` to construct the string `"N:..."`.
- Each group ends with `yield` on its respective paths, so it does not fall through to the next group.
- The colon form differs from a traditional `switch statement`: in a **switch expression**, `yield` returns a value; `break` does not provide a value for the expression.

**Tip:** Prefer `->` whenever possible. Use `case ...:` with `yield` when there is a clear structural reason involving multiple statements; avoid accidentally applying `switch statement` `break`/fall-through thinking to a switch expression.

## 7. How Is the Result Type of the Entire Switch Expression Determined?

Even when branches have different patterns, **a switch expression still has a single type** at its use site. This type is governed by Java's typing rules and can depend on the **target type** (the context of an assignment, `return`, or method call) or be inferred from the expressions of the individual branches.

In `SwitchBranchValueDemo`, every branch produces a `String`, so it is straightforward. For a method returning `int` like `score`, the branches produce `int`.

A noteworthy case is when each branch produces a different kind of number. Save `SwitchPolymorphicValueDemo.java`:

~~~java
public class SwitchPolymorphicValueDemo {
    static Number number(String tag) {
        return switch (tag) {
            case "integer" -> 1;
            case "decimal" -> 2.5;
            default -> 3L;
        };
    }

    static String format(Object value) {
        return switch (value) {
            case String s -> "S:" + s;
            case Number n -> "N:" + n;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Number a = number("integer");
        Number b = number("decimal");
        Number c = number("other");
        System.out.println(a.getClass().getSimpleName() + ":" + a);
        System.out.println(b.getClass().getSimpleName() + ":" + b);
        System.out.println(c.getClass().getSimpleName() + ":" + c);
        System.out.println(format(3));
    }
}
~~~

~~~bash
javac --release 21 SwitchPolymorphicValueDemo.java
java SwitchPolymorphicValueDemo
~~~

Output:

~~~text
Integer:1
Double:2.5
Long:3
N:3
~~~

Here, `return switch (tag)` is a switch expression in a **target type context of `Number`**. The expressions `1`, `2.5`, and `3L` are boxed into `Integer`, `Double`, and `Long` respectively; all three are compatible with the `Number` return type. The actual runtime values retain their respective wrapper classes as shown in the output.

This **does not mean** every switch expression mixing `int`/`double`/`long` will always produce `Number`: if there is no target type and the expression is evaluated as a *standalone* expression, Java may apply numeric promotion and produce a different result type. Do not guess the type simply by looking at the first branch.

### Branches Must Be Compatible with the Target Type

This snippet **intentionally does not compile**:

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> "text"; // String cannot be converted to int
        default -> 1;
    };
}
~~~

The compiler reports that the `String` result type of the first branch is incompatible with `int`. Every branch that produces a normal value must be an expression compatible with the typing rules at the use site; a `throw` branch does not need to produce a value.

## 8. A Branch Can Throw an Exception Instead of Producing a Value

A switch expression can use a `throw` rule body to indicate invalid input. If that branch is selected, evaluating the switch **completes abruptly** with an exception and has no normal result value.

Save `SwitchThrowDemo.java`:

~~~java
public class SwitchThrowDemo {
    static int lengthOfString(Object value) {
        return switch (value) {
            case String s -> s.length();
            case null -> throw new IllegalArgumentException("null value");
            default -> throw new IllegalArgumentException("not string");
        };
    }

    public static void main(String[] args) {
        System.out.println(lengthOfString("Java"));
        try {
            lengthOfString(42);
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR:" + error.getMessage());
        }
        try {
            lengthOfString(null);
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR:" + error.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 21 SwitchThrowDemo.java
java SwitchThrowDemo
~~~

Output:

~~~text
4
ERROR:not string
ERROR:null value
~~~

`case String s` returns an `int` from `s.length()`; the other two branches throw exceptions. The `lengthOfString` method only returns an `int` when the input is valid. There is no need to invent a sentinel value like `-1` for error cases if the API contract requires throwing an exception.

Inside a multi-statement block, you can also `throw` an exception on an error path and `yield` on the success path; all allowed paths must follow the rules of switch expressions.

## 9. Exhaustiveness: No Path Can Be Missing a Result

A switch expression must be **exhaustive**: the compiler must determine that every selector value in the applicable domain has a matching branch. Without a handling branch, the expression cannot guarantee that it will produce a value.

For a selector of type `Object`, which has infinitely many possible runtime classes, `default` is usually required:

~~~java
String label = switch (value) {
    case String s -> "S:" + s;
    case Integer n -> "I:" + n;
    default -> "OTHER";
};
~~~

This is an illustrative snippet inside a method with `Object value`. If `default` is omitted in this case, the compiler reports that the switch expression does not cover all possible values.

Example that **intentionally does not compile**:

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s -> "S:" + s;
        case Integer i -> "I:" + i;
    };
}
~~~

Typical `javac --release 21` error message:

~~~text
error: the switch expression does not cover all possible input values
~~~

### When Can `default` Be Omitted?

If the selector has a **sealed interface/class** type and the case patterns cover all permitted subtypes, the compiler can prove exhaustiveness without `default`.

Save `SwitchSealedExhaustiveDemo.java`:

~~~java
sealed interface Outcome permits Success, Failure {}
record Success(int count) implements Outcome {}
record Failure(String reason) implements Outcome {}

public class SwitchSealedExhaustiveDemo {
    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(var count) -> "OK:" + count;
            case Failure(var reason) -> "FAIL:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success(2)));
        System.out.println(describe(new Failure("invalid")));
    }
}
~~~

~~~bash
javac --release 21 SwitchSealedExhaustiveDemo.java
java SwitchSealedExhaustiveDemo
~~~

Output:

~~~text
OK:2
FAIL:invalid
~~~

There are only two permitted implementations of `Outcome`, and each is covered by a record pattern. Therefore, the compiler accepts the switch expression without `default`. **This does not mean it automatically handles `null`:** if `describe(null)` is called without `case null`, the switch throws `NullPointerException`.

If the system changes the subtype hierarchy or the state of the sealed hierarchy, you must recheck coverage and recompile the affected switches.

## 10. Null: `default` Does Not Replace `case null` in a Pattern Switch

With a reference-type selector:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

Java 21 allows handling `null` explicitly with `case null`. Without a matching label for `null`, switching on `null` typically throws `NullPointerException`, **even when `default` is present**.

Distinction:

- `case String s` does not match `null`, so `s` cannot be bound.
- `case null` matches the `null` value and can return an explicit value such as `"NULL"`.
- `default` is the fallback branch for other values that do not match earlier cases; it does not implicitly replace `case null`.
- If you want to treat `null` as an error, choose `case null -> throw new IllegalArgumentException("null value");` as in `SwitchThrowDemo`.

Depending on business logic, you can choose to return a default value, throw an exception, or handle `null` before the switch. What matters is that the behavior is explicitly designed.

## 11. A Switch Statement Does Not Produce a Value Like a Switch Expression

Both can use pattern matching in Java 21, but their purposes differ.

**Switch statement:** executes statements, and may log, update state, or call methods; the `switch (...) { ... }` syntax here is a **statement**, not an expression assigned to a variable.

~~~java
switch (value) {
    case String s -> System.out.println("Text:" + s);
    case Number n -> System.out.println("Number:" + n);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
~~~

**Switch expression:** computes a value, and the caller decides how to use that value:

~~~java
String message = switch (value) {
    case String s -> "Text:" + s;
    case Number n -> "Number:" + n;
    case null -> "Null";
    default -> "Other";
};
System.out.println(message);
~~~

The two snippets above are **Java excerpts inside a method with `Object value`**, not standalone programs. With a switch expression, each branch supplies exactly one normal result or throws an exception; with a switch statement, the rules execute statements and there is no common value to assign.

**Having `case ... ->` does not automatically mean it is a switch expression.** The `->` arrow can be used in both switch statements and switch expressions. Check whether the switch is being used in **an expression position**—such as the right-hand side of `=`, in a `return`, or in a method call—or standing alone as a statement.

## 12. Compile-Time Errors Related to Branch Values

These are typical scenarios verified with `javac --release 21`. The snippets below are **intentionally invalid examples**, not runnable code.

### 12.1. Block Completes Without `yield`

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> {
            int result = s.length();
            // Missing yield result;
        }
        default -> 0;
    };
}
~~~

The compiler reports:

~~~text
error: switch rule completes without providing a value
~~~

Fix: add `yield result;` after the assignment. **Computing a variable inside a block is not the same as returning a value from the block.**

### 12.2. Using `return` Instead of `yield`

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> { return s.length(); } // COMPILE ERROR
        default -> 0;
    };
}
~~~

The compiler reports:

~~~text
error: attempt to return out of a switch expression
~~~

Fix inside the block: `yield s.length();`. Using `return` outside the switch expression at the start of the method is valid, as in the complete programs above: `return switch (value) { ... };`.

### 12.3. Using `break` Instead of `yield`

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> { break; } // COMPILE ERROR
        default -> 0;
    };
}
~~~

The compiler reports:

~~~text
error: attempt to break out of a switch expression
~~~

In a colon-style switch statement, `break` is used to exit the switch. In a switch expression, `break` does not produce the required value; use `yield` in a block branch or a direct expression in the rule.

### 12.4. Missing Exhaustive Coverage

With `switch (Object value)`, having only `case String s` and `case Integer i` leaves many types uncovered. The compiler reports that the switch expression does not cover all possible input values. Add `default` or design a type model whose exhaustiveness can be proven, such as a sealed hierarchy.

### 12.5. Branch Value Incompatible with the Return Type

If the method returns `int` but has `case String s -> "text";`, the compiler rejects it because `String` cannot be converted to `int`. Ensure all branches produce results conforming to the same type contract, such as `String`, `int`, or an appropriate interface/supertype.

### 12.6. Placing a Broad Branch Before a Specific Branch

~~~java
return switch (value) {
    case Number n -> "NUMBER";
    case Integer i -> "INTEGER"; // Dominated by case Number
    default -> "OTHER";
};
~~~

This is an error illustration with `Object value`. `Integer` is a `Number`, so the compiler does not allow the `Integer` branch to appear after an unguarded `Number` type pattern. Order more specific cases first.

## 13. Common Mistakes When Designing Branch Values

1. **Confusing the pattern check with the value-producing part.** `case String s` only checks/binds the variable; `-> expression` or `yield` is what supplies the value to the switch expression.
2. **Using `break` or `return` inside a switch expression block.** Neither statement can replace `yield`.
3. **Only assigning a local variable and forgetting `yield`.** A block that completes normally must supply a value; the compiler does not automatically use the last variable as the result.
4. **Omitting input cases.** A switch expression must be exhaustive; with an `Object` selector, `default` is usually used.
5. **Believing `default` catches `null` automatically.** In a Java 21 pattern switch, handle `null` with its own case if you want to return a value for null input.
6. **Thinking all branches must have the exact same runtime type.** With an appropriate target type like `Number`, `Integer`/`Double`/`Long` branches can all be valid while keeping their distinct runtime wrapper types.
7. **Thinking a rule with `throw` must also `yield`.** `throw` completes abruptly; it does not need a normal result value.
8. **Forgetting the order of guarded cases and subtypes.** Specific guards and subtypes must come before broader branches if they need separate handling.
9. **Using a pattern variable outside its branch.** `s` from `case String s` is only in scope within its guard and corresponding rule or group; it cannot be used in `case Number n`.
10. **Using an older Java configuration.** The pattern switch examples here require JDK 21+.

## 14. Exercises and Answers

### Exercise 1 — Predict the Value

Suppose:

~~~java
static String category(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isEmpty() -> "EMPTY";
        case String s -> "TEXT:" + s.length();
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
~~~

For `category("")`, `category("hi")`, `category(12)`, and `category(null)`, what are the respective results?

**Answer:** `EMPTY`, `TEXT:2`, `NUMBER`, `NULL`. The `isEmpty()` guard is only true for a string with zero characters (unlike `isBlank()`, which is also true for whitespace-only strings).

### Exercise 2 — Fill in `yield`

Fill in the missing content:

~~~java
static int score(Object input) {
    return switch (input) {
        case String s -> {
            int n = s.length();
            // Which statement is needed to return n * 2?
        }
        default -> 0;
    };
}
~~~

**Answer:** `yield n * 2;`. This is the statement that supplies a value from a switch expression block.

### Exercise 3 — Choosing Between `return` and `yield`

In a method `static int calculate(Object value)`, do the following two statements have the same meaning?

~~~java
return switch (value) {
    case String s -> s.length();
    default -> 0;
};
~~~

~~~java
return switch (value) {
    case String s -> {
        yield s.length();
    }
    default -> 0;
};
~~~

**Answer:** Yes, for those inputs, both return the same `int`. The first form uses a rule expression; the second uses a block and `yield`. `return` is **outside** the switch expression to return from the method.

### Exercise 4 — Exhaustiveness and Sealed Interfaces

Given `sealed interface Shape permits Circle, Rectangle`, where both are valid implementing classes/records, why can a switch expression with `case Circle ...` and `case Rectangle ...` omit `default`?

**Answer:** The selector type `Shape` has a defined set of permitted subtypes. When all subtypes are covered by matching patterns, the compiler can prove exhaustiveness. However, `null` still needs to be considered separately at runtime.

### Exercise 5 — Result Type

A method returning `Number` uses a switch expression with branches `-> 1`, `-> 2.5`, and `-> 3L`. Why is this valid, and what classes do the runtime values belong to?

**Answer:** The three values can be boxed into `Integer`, `Double`, and `Long`; all are subtypes of `Number`. Do not assume every switch expression mixing numbers will yield type `Number` without a corresponding target type.

### Exercise 6 — Branch Throwing an Exception

Fix a `switch(Object value)` so that it only accepts `String` and reports an error for everything else:

~~~java
static int length(Object value) {
    return switch (value) {
        case String s -> s.length();
        // Write how to handle null and other types
    };
}
~~~

**Reference answer:**

~~~java
static int length(Object value) {
    return switch (value) {
        case String s -> s.length();
        case null -> throw new IllegalArgumentException("null");
        default -> throw new IllegalArgumentException("wrong type");
    };
}
~~~

If `value` is a `String`, the expression evaluates to `int`. All other cases terminate with an exception, without needing to produce a dummy value.

## 15. Checklist for Writing Switch Expressions with Patterns

Before finishing a switch expression, check:

1. What static type does the selector have, and what kinds of runtime values can appear?
2. Which case patterns and guards are chosen? Are specific subtypes and guards placed before broader branches?
3. Does each `-> expression` rule actually produce the intended **value**?
4. Does each `-> { ... }` block have `yield` on all normal completion paths?
5. If using the `case ...:` form, does every execution path validly `yield` or throw an exception?
6. Are the branch values compatible with the target type or inferred type of the switch expression?
7. Is the switch exhaustive? Is `default` or sealed type coverage needed?
8. Is `null` handled explicitly when business requirements call for it?
9. Is there any confusion among `break`/`return`/`yield` or pattern variable scope between branches?
10. Is the code using Java 21+ for pattern matching in `switch`?

**Remember:** *the pattern selects the branch*, while *the expression or `yield` determines the branch's value*. A switch expression completes normally only when the selected branch supplies a value compatible with the expression's type; a `throw` branch instead completes abruptly.

### Java 21 Specification References

- JLS `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- JLS `14.21 — Yield Statement: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21
- JLS `14.11.1 — Switch Blocks, case labels, dominance: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
