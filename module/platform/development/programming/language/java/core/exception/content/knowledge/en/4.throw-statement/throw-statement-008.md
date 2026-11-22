# Throw in switch Branches and Value-Returning Control Flow in Java

In Java, `throw` **abruptly terminates the current execution path** by throwing an exception object. This is especially important when a `switch` branch must decide whether to **return a value or report an error**: a valid branch provides a result, while an invalid branch can use `throw` to prevent the program from continuing with a dummy value.

Since Java 14, `switch expression` has been a standard feature; Java 17+ supports the arrow syntax `->`, `yield`, and `throw` in `switch` branches without enabling preview features. It is important to distinguish clearly:

- **`switch expression`:** The entire `switch` participates in an expression, producing a value to assign or return. Each selected branch must either provide a value according to the language rules, or complete abruptly, such as with `throw`.
- **`switch statement`:** The entire `switch` is a control statement. A branch can perform operations, exit with `break`, or in an appropriate context use `return` or `throw`.
- **`throw`:** This is a statement that throws an exception, **not an expression that produces a value**. In a `switch expression`, a `throw` branch is valid because that branch does not complete normally; Java does not require a throwing branch to provide a value.

Understanding these three points helps avoid common mistakes when combining `return switch (...)`, `yield`, and exception handling.

## 1. Basic Scenario: Return on Valid Value, Throw on Invalid Value

Consider a method that maps an operation code to a limit:

~~~java
static int quota(String mode) {
    return switch (mode) {
        case "fast" -> 12;
        case "safe" -> 6;
        default -> throw new IllegalArgumentException(
                "Chế độ không hỗ trợ: " + mode);
    };
}
~~~

This is an **illustrative method snippet** that can be placed inside a Java class. Explanation:

1. `switch (mode)` is evaluated and selects a branch.
2. For `"fast"`, the `switch` expression has the value `12`; the method's `return` returns `12`.
3. For `"safe"`, the `switch` expression has the value `6`.
4. For any other string, the statement `throw new IllegalArgumentException(...)` executes. Neither the `switch` expression nor the method returns an `int` on that path; the exception propagates to the caller if uncaught.

Key point: a method declared to return `int` **is not required to return a number on the exception-throwing path**. Every execution path that completes normally must return the right type; the `throw` path completes abruptly, so no `return 0` is needed just to "satisfy the type".

### Why Not Return an Arbitrary Default Value?

~~~java
static int quotaWrong(String mode) {
    return switch (mode) {
        case "fast" -> 12;
        case "safe" -> 6;
        default -> 0;
    };
}
~~~

This snippet **compiles**, but if `0` is not a valid API convention, the caller might assume the operation succeeded and continue with bad data. When input violates the contract, throwing an exception is usually clearer than returning an undefined "magic value".

Conversely, if business rules specify that all unrecognized modes must have a quota of `0`, then `default -> 0` is the right choice. `throw` is not an end in itself: choose the outcome based on the **method's contract**.

## 2. Important Rules of `switch expression`

Consider an expression that assigns a result:

~~~java
int level = switch (name) {
    case "basic" -> 1;
    case "pro" -> 2;
    default -> throw new IllegalArgumentException("Tên không hợp lệ");
};
~~~

This is an **illustrative snippet** requiring an appropriate `name` variable inside a method. The branches selecting `"basic"` or `"pro"` complete normally with an `int` value. The `default` branch throws an exception and does not provide a value.

You should not interpret `throw` as a special `int` value. It is an **abrupt completion** of the branch being executed; therefore, it does not conflict with the `int` type requirement of the value-returning branches.

### Single Expression After the Arrow

~~~java
case "basic" -> 1;
~~~

The right-hand side of the arrow is the expression `1`, providing the value for the `switch expression`.

### Block with Multiple Statements and `yield`

~~~java
case "pro" -> {
    int base = 2;
    int multiplier = 3;
    yield base * multiplier;
}
~~~

When a branch of a `switch expression` uses a `{ ... }` block, `yield` provides the value of the `switch` expression. In this example, the result is `6`.

### Exception-Throwing Form

~~~java
default -> throw new IllegalArgumentException("Không có cấu hình");
~~~

The right-hand side is a **`throw` statement**; this branch does not complete normally and has no `yield` value.

### Block That Checks and Then Throws or Yields

~~~java
case "custom" -> {
    if (limit < 0) {
        throw new IllegalArgumentException("limit không được âm");
    }
    yield limit * 2;
}
~~~

This is an illustrative branch with a `limit` variable in scope. When `limit < 0`, the branch throws an exception; when valid, the branch provides a value using `yield`. Because the `throw` path does not need to produce a value, this is valid syntax.

In a block branch of a `switch expression`, **any path that can complete normally without `yield` is invalid**. A block that has `throw` on one conditional branch still needs `yield` or an exception throw on the remaining paths.

## 3. Distinguishing `yield`, `return`, and `throw`

All three statements affect control flow, but their purposes differ.

| Statement | What happens | Where is it typically used? |
| --- | --- | --- |
| `yield value;` | Completes a `switch expression` branch, providing the value for the `switch` expression itself | Block branch of a `switch expression` |
| `return value;` | Completes the currently running method normally and returns a value to the caller | Method body, or a `switch statement` block when appropriate |
| `throw exception;` | Completes abruptly by throwing an exception object | Inside a method, in a `switch expression` branch, or in a `switch statement` |

Valid example with `yield`:

~~~java
static int calculate(String key) {
    int result = switch (key) {
        case "double" -> {
            int source = 7;
            yield source * 2;
        }
        case "one" -> 1;
        default -> throw new IllegalArgumentException("Key sai: " + key);
    };
    return result;
}
~~~

The method above is **logically complete** but needs to be placed inside a Java class. `yield 14;` only passes the value `14` out of the `switch expression` to assign to `result`; the `return result;` statement is what returns the value from the `calculate` method.

### Do Not Use `return` Inside a `switch expression` Block

**Invalid, non-compiling** example:

~~~java
static int invalid(String key) {
    return switch (key) {
        case "one" -> {
            return 1;  // Cannot return from inside a switch expression.
        }
        default -> 0;
    };
}
~~~

In a `switch expression`, a block branch must use `yield` to produce a value or `throw` to complete abruptly. Fix it to:

~~~java
static int valid(String key) {
    return switch (key) {
        case "one" -> {
            yield 1;
        }
        default -> 0;
    };
}
~~~

### Do Not Treat `throw` as a Regular Operand

The following syntax is **invalid** in Java:

~~~java
int value = flag ? 10 : throw new IllegalArgumentException("Sai");
~~~

`throw` is a statement, not an expression that can be used as the third operand of `?:`. One might try writing:

~~~java
int value = switch (flag) {
    case true -> 10;
    case false -> throw new IllegalArgumentException("Sai");
};
~~~

**However, the `switch (flag)` snippet above is also invalid in Java 17:** the `switch` selector cannot be the primitive `boolean` type (Java 17 does not support `switch` on `boolean` as in that example). To make it valid in Java 17, use an `int` or `String` selector:

~~~java
int value = switch (flag ? 1 : 0) {
    case 1 -> 10;
    default -> throw new IllegalArgumentException("Sai");
};
~~~

These snippets are **syntax illustrations** where `flag` is an existing `boolean` variable. Showing both invalid forms clarifies two independent restrictions: `throw` is not an expression usable in `?:`, and `boolean` is not a standard `switch` selector in Java 17.

## 4. `switch statement`: `throw` Branch vs. `return` Branch

A `switch statement` is a **statement**, not an expression that returns a value to an assignment operator. However, the enclosing method can still return a value from inside its branch blocks:

~~~java
static int quotaStatement(String mode) {
    switch (mode) {
        case "fast" -> {
            return 12;
        }
        case "safe" -> {
            return 6;
        }
        default -> throw new IllegalArgumentException(
                "Chế độ không hỗ trợ: " + mode);
    }
}
~~~

This is a valid illustrative method in Java 17+. When `mode` is valid, the branch block calls `return` to **return from the method**; when invalid, `throw` causes the method to complete abruptly.

Key differences compared to `return switch (...)`:

- With a **`switch expression`**, branches produce values `-> 12`, `-> 6`; the method has a single enclosing `return switch (...)`.
- With a **`switch statement`**, branches use `return` inside blocks to return from the method.
- Both can use `default -> throw ...` to avoid returning a dummy value.

### Why Are Braces Required Around `return` in an Arrow Branch of a `switch statement`?

A `switch rule` after `->` has a body of one of the syntactically permitted forms, such as an expression statement, a block, or a `throw` statement. The following snippet is not valid syntax:

~~~java
switch (mode) {
    case "fast" -> return 12;  // Invalid: return is not a direct body here.
    default -> throw new IllegalArgumentException();
}
~~~

Fix it with a block:

~~~java
switch (mode) {
    case "fast" -> {
        return 12;
    }
    default -> throw new IllegalArgumentException();
}
~~~

Both snippets above must be inside a method returning `int` with an appropriate `mode` variable. With a `switch expression`, `case "fast" -> 12;` is the right way to return an **expression value**.

### Classic `switch statement` Using Colons

Java 17 still supports the `case ...:` syntax and the `break` statement:

~~~java
static int quotaClassic(String mode) {
    switch (mode) {
        case "fast":
            return 12;
        case "safe":
            return 6;
        default:
            throw new IllegalArgumentException(
                    "Chế độ không hỗ trợ: " + mode);
    }
}
~~~

This method is valid. `return` exits the entire method and `throw` completes abruptly, so `break` is not needed in those branches. However, if a classic branch only runs normal statements without `break`, `return`, or `throw`, execution can **fall through** to the next branch; the arrow syntax `->` helps avoid such unintended fall-through.

## 5. Exhaustiveness and Exception-Throwing Branches

**A `switch expression` must cover all possible selector values according to compiler rules.** A common approach with `String` or `int` is to declare `default`. `default` can provide a value or throw an exception.

~~~java
static String stateLabel(int state) {
    return switch (state) {
        case 0 -> "READY";
        case 1 -> "RUNNING";
        default -> throw new IllegalArgumentException(
                "Mã trạng thái không biết: " + state);
    };
}
~~~

Here, the values `0` and `1` produce a string; any other value throws an exception. A `throw` branch **counts as a valid exhaustive branch** even though it does not produce a `String`.

If you omit `default` in a `switch expression` for `int` without another way to cover all values, the compiler reports an error because the `switch` expression is not exhaustive. Writing `default -> throw ...` clearly expresses that out-of-domain values are **not accepted**.

### Enum Case: Full Coverage with Constants

~~~java
enum Stage { NEW, ACTIVE, CLOSED }

static int priority(Stage stage) {
    return switch (stage) {
        case NEW -> 1;
        case ACTIVE -> 2;
        case CLOSED -> throw new IllegalStateException(
                "Giai đoạn đóng không có độ ưu tiên");
    };
}
~~~

Both declarations above can be placed inside a Java class. Because `enum Stage` currently has exactly three constants, the three branches cover all constants, so `default` is not required. The `CLOSED` branch using `throw` is still sufficient to form a valid `switch expression`.

When a new constant is added to the `enum` and the calling code is recompiled, a `switch expression` without `default` typically has to be updated to remain exhaustive. This can be a good design choice: the compiler reminds developers to consider every new state.

Do not assume `default -> throw` is always necessary in every `switch expression`. With an enum whose cases are all listed, omitting `default` often helps catch value-domain changes at build time; which approach to choose should depend on the API contract.

### A Throwing Branch Does Not Make the Whole `switch` Typeless

~~~java
int x = switch (code) {
    case 1 -> 10;
    case 2 -> 20;
    default -> throw new IllegalArgumentException("code sai");
};
~~~

The branches that complete normally all have `int` values; the `throw` branch does not need to "contribute a type" to produce the result. However, if the remaining branches return types incompatible with the target context, the compiler still reports a type error.

## 6. Checked Exceptions in `switch` Branches

`throw` inside a `switch` is subject to the **exact same checked/unchecked rules** as anywhere else. `throw new IOException(...)` throws a checked exception; the enclosing method must catch or declare it. `throw new IllegalArgumentException(...)` is unchecked and does not require a `throws` declaration.

Checked example:

~~~java
static int loadQuota(String mode) throws java.io.IOException {
    return switch (mode) {
        case "standard" -> 5;
        case "offline" -> throw new java.io.IOException(
                "Không thể tải hạn mức khi ngoại tuyến");
        default -> throw new IllegalArgumentException(
                "Chế độ không hợp lệ: " + mode);
    };
}
~~~

This method compiles cleanly in Java 17+ because it declares `throws IOException`. When `mode` is `"offline"`, no `int` is returned. The caller must obey the checked contract of `IOException`.

### Not Declaring a Checked Exception: Compile Error

**Invalid** example:

~~~java
static int invalidChecked(String mode) {
    return switch (mode) {
        case "offline" -> throw new java.io.IOException("Mất kết nối");
        default -> 5;
    };
}
~~~

The compiler requires catching or declaring `IOException`. Fix it by adding `throws java.io.IOException` to the signature or handling it via `try/catch` at a layer capable of making a decision.

The fact that the `offline` branch only runs when the selector matches does not exempt it from the checked-exception requirement at compile time. Conversely, a checked exception **does not require the method to return a special number in the throwing branch**.

## 7. Complete Java 17+ Example: Returning Results, `yield`, and `throw`

The following program directly tests all three usages:

1. A `switch expression` returning `int` via an expression branch or `yield`.
2. A `switch expression` throwing a checked or unchecked exception per branch.
3. A `switch statement` using `return` in branch blocks and `throw` in `default`.

Save the entire program in **`SwitchThrowDemo.java`**:

~~~java
public class SwitchThrowDemo {
    static class QuotaUnavailableException extends Exception {
        QuotaUnavailableException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        for (String mode :
                new String[] {"fast", "safe", "blocked", "unknown"}) {
            try {
                System.out.println(mode + " => " + quota(mode));
            } catch (QuotaUnavailableException e) {
                System.out.println(
                        mode + " => checked: " + e.getMessage());
            } catch (IllegalArgumentException e) {
                System.out.println(
                        mode + " => unchecked: " + e.getMessage());
            }
        }

        System.out.println(
                "statement safe => " + quotaStatement("safe"));

        try {
            quotaStatement("wrong");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "statement wrong => " + e.getMessage());
        }
    }

    static int quota(String mode)
            throws QuotaUnavailableException {
        return switch (mode) {
            case "fast" -> 12;
            case "safe" -> {
                int base = 4;
                yield base + 2;
            }
            case "blocked" -> throw new QuotaUnavailableException(
                    "Hạn mức tạm khóa");
            default -> throw new IllegalArgumentException(
                    "Chế độ lạ: " + mode);
        };
    }

    static int quotaStatement(String mode) {
        switch (mode) {
            case "fast" -> {
                return 12;
            }
            case "safe" -> {
                return 6;
            }
            default -> throw new IllegalArgumentException(
                    "Không hỗ trợ: " + mode);
        }
    }
}
~~~

Compile and run (JDK 17 or later):

~~~bash
javac SwitchThrowDemo.java
java SwitchThrowDemo
~~~

**Exact stdout:**

~~~text
fast => 12
safe => 6
blocked => checked: Hạn mức tạm khóa
unknown => unchecked: Chế độ lạ: unknown
statement safe => 6
statement wrong => Không hỗ trợ: wrong
~~~

### Tracing Each Branch

- **`fast`:** The branch `case "fast" -> 12;` completes the `switch expression` with `12`; the `return` of `quota` passes that value back to `main`.
- **`safe`:** The block branch declares `base = 4` and then `yield base + 2;`, providing `6` to the `switch` expression; the method returns `6`.
- **`blocked`:** The branch `case "blocked" -> throw new QuotaUnavailableException(...)` creates and throws a checked exception. Because `quota` declares `throws QuotaUnavailableException`, `main` handles it with `catch (QuotaUnavailableException e)`. No `int` value is returned on this path.
- **`unknown`:** The `default` branch throws `IllegalArgumentException`, which is caught by the corresponding unchecked `catch` block.
- **`quotaStatement("safe")`:** The `switch statement` is not itself a value-returning expression; `return 6;` inside the branch block exits the method.
- **`quotaStatement("wrong")`:** `default -> throw ...` causes the method to complete abruptly without printing a success result line; the message in `main` is produced by `catch`.

In the program, the two adjacent `catch` blocks do not compete for the same type: `QuotaUnavailableException` is checked, extending `Exception`; `IllegalArgumentException` is unchecked, extending `RuntimeException`. The output contains no stack trace lines because every exception thrown by the example is caught in `main`.

## 8. Control Flow and "Every Path Returns a Value"

A method with a non-`void` return type must satisfy Java's rules for normal completion and returning a value. A method can be modeled as follows:

~~~text
return switch (mode)
    |
    +-- valid branch --> produce value --> return to caller
    |
    +-- disallowed branch --> throw exception --> find matching catch
                                                    |
                                                    +-- caller catches and handles
                                                    +-- or exception continues propagating
~~~

The important point is that the `throw` path does not reach the `return` statement yet is still valid: the method does not complete normally on that path.

### Cases to Distinguish

| Case | Behavior |
| --- | --- |
| `-> 10` branch of a `switch expression` | Provides the value `10` for the entire expression |
| `-> { yield 10; }` branch | Provides the value `10` for the entire expression |
| `-> throw new RuntimeException()` branch | Produces no value, completes abruptly |
| `-> { throw new RuntimeException(); }` branch | Produces no value, completes abruptly |
| `switch statement` block containing `return 10;` | Returns `10` from the method |
| `switch statement` block containing `throw ...;` | Completes abruptly and searches for a handler |
| `switch statement` block that only logs and finishes | Continues after the `switch statement` if another statement follows |

The last example is especially easy to misunderstand:

~~~java
static int value(String mode) {
    switch (mode) {
        case "fast" -> System.out.println("fast");
        default -> System.out.println("other");
    }
    return 1;
}
~~~

This is a **valid** method: the `switch` only prints a message, and then `return 1;` returns the result for all inputs. Do not interpret `System.out.println(...)` in a `switch statement` as a value-producing branch like in a `switch expression`.

### Why Is This Code Invalid?

~~~java
static int broken(String mode) {
    switch (mode) {
        case "fast" -> {
            return 12;
        }
        case "safe" -> {
            System.out.println("safe");
        }
        default -> throw new IllegalArgumentException("mode sai");
    }
}
~~~

This illustrative snippet **does not compile**: if `mode` is `"safe"`, the method can complete normally without returning an `int`. The `default -> throw` path only handles other inputs; it does not provide a `return` for the `safe` path. To fix it, return a result in the `safe` branch or place a common `return` after the `switch statement` according to the appropriate contract.

For a `switch expression`, a block branch that completes normally without `yield` is rejected by the rules specific to `switch` expressions.

## 9. Structuring Exception Handling When Using `return switch`

Depending on the API's semantics, you can let the exception propagate to the caller or catch it at an appropriate boundary:

~~~java
static int quotaOrDefault(String mode, int fallback) {
    try {
        return switch (mode) {
            case "fast" -> 12;
            case "safe" -> 6;
            default -> throw new IllegalArgumentException(
                    "Chế độ không hợp lệ");
        };
    } catch (IllegalArgumentException e) {
        return fallback;
    }
}
~~~

The illustrative method above **returns a fallback** for unsupported input. This only makes sense if the contract truly allows using a fallback. If an invalid mode is an error that must be reported to the caller, let the exception propagate.

Do not wrap every `switch` in `catch (Exception e)` and silently return a fixed value: that can hide logic or state bugs that the application ought to investigate.

### Role of `finally` When a Branch Throws or Returns

~~~java
static int example(boolean fail) {
    try {
        return switch (fail ? "fail" : "ok") {
            case "ok" -> 9;
            default -> throw new IllegalStateException("không thành công");
        };
    } finally {
        System.out.println("cleanup");
    }
}
~~~

This is a valid illustrative method. Under normal execution conditions:

- `example(false)` prints `cleanup` and then returns `9`.
- `example(true)` prints `cleanup`, and then `IllegalStateException` continues propagating outward.

`finally` normally runs when leaving `try`, both when a branch has produced a `return` value and when a branch throws an exception. Avoid accidentally placing a `return` or throwing another exception inside `finally`, as that can mask the propagating result or error. Abnormal JVM termination scenarios can prevent `finally` from running.

## 10. `switch`, `null`, and Selector Types in Java 17

The `throw` branch syntax does not change the type restrictions of `switch` in Java 17.

### `null` Selector

If a reference selector such as `String mode` is `null`, `switch (mode)` in standard Java 17 will throw `NullPointerException` before selecting any branch; `default` is **not** a branch that automatically handles `null`.

~~~java
static int level(String name) {
    return switch (name) {
        case "low" -> 1;
        default -> throw new IllegalArgumentException("Tên không hợp lệ");
    };
}
~~~

With `level(null)`, Java 17 normally throws `NullPointerException` when evaluating the selector. If you want an error matching your own contract, you can check beforehand:

~~~java
static int levelChecked(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name không được null");
    }
    return switch (name) {
        case "low" -> 1;
        default -> throw new IllegalArgumentException("Tên không hợp lệ");
    };
}
~~~

These two methods merely illustrate input handling. Do not use `case null` or pattern matching for `switch` as if it were standard non-preview Java 17 syntax; pattern-matching `switch` features vary across Java versions.

### `boolean` Type in Java 17 `switch`

Standard Java 17 supports `switch` on certain integral primitive types, their related wrapper types, `String`, and `enum`; it **does not support a `boolean` selector** in standard Java 17 syntax. Therefore:

~~~java
int x = switch (flag) {
    case true -> 1;
    default -> throw new IllegalArgumentException();
};
~~~

is a **counterexample that does not compile in Java 17**, even though the intent to use `throw` is completely clear. When you only have a boolean condition, use `if/else`:

~~~java
static int requireEnabled(boolean enabled) {
    if (!enabled) {
        throw new IllegalStateException("Chưa bật");
    }
    return 1;
}
~~~

This is a logically complete method that can be placed inside a Java class. There is no need to force every simple condition into a `switch`.

## 11. Common Mistakes

**Mistake 1: Thinking `throw` produces a default value for a `switch expression`.**  
False. `throw` does not provide a value; it completes abruptly. When caught by the caller, the caller handles the exception according to the contract rather than receiving a dummy `int` or `String`.

**Mistake 2: Using `return` inside a `switch expression` block.**  
A block branch must `yield value`, `throw`, or otherwise complete abruptly in a valid way. `return` inside a `switch expression` is a compile error; `return switch (...)` outside the expression is what returns from the method.

**Mistake 3: Missing `yield` on a path that can complete normally.**  
If a block branch conditionally throws, the remaining path must provide a value; you cannot just log and reach the end of the block when the entire `switch` needs a value.

**Mistake 4: Writing `case X -> return value;` in a `switch statement`.**  
The valid syntax with `return` is `case X -> { return value; }`. For a `switch expression`, simply use `case X -> value;` or a `yield` block.

**Mistake 5: Forgetting exhaustiveness of a `switch expression`.**  
For selectors like `int` or `String`, use `default` when you need to cover unlisted values. `default -> throw ...` is a valid way to handle out-of-domain inputs that should be rejected.

**Mistake 6: Throwing a checked exception without catching or declaring it.**  
`case "offline" -> throw new IOException(...)` still obeys checked-exception rules just like any other `throw` statement.

**Mistake 7: Assuming `default` always handles `null`.**  
With a `null` `String` selector in Java 17 without preview features, a `NullPointerException` normally occurs before the `default` branch runs. Check for `null` beforehand if the API wants a clearer error.

**Mistake 8: Returning a dummy value just to force every path to have a value.**  
If the input is invalid, `default -> throw new IllegalArgumentException(...)` usually reflects the contract better than a meaningless `default -> 0`.

**Mistake 9: Assuming a `switch statement` must always return a value.**  
A `switch statement` can simply execute operations and continue after the construct. However, if the enclosing method itself declares a return type, it must still satisfy the `return` rule on every normally completing path.

**Mistake 10: Trying to place `throw` as an arbitrary expression operand.**  
`throw` is a statement. The `case ... -> throw ...` syntax is specially supported by the language; it does not mean `throw` is allowed in place of any expression in `?:` or as an operand of addition.

## 12. Self-Check Exercises

1. Why does `int quota(String mode)` still compile when the `default` branch only executes `throw new IllegalArgumentException(...)` without returning an `int`?
2. In `return switch (...)`, when do you write `case X -> 10;`, and when do you write `case X -> { yield 10; }`?
3. What is wrong with `case X -> { return 10; }` when it is inside a `switch expression`? What is the right way to write it?
4. In a `switch statement`, why can `case X -> { return 10; }` be valid inside a method returning `int`?
5. If a `switch expression` branch throws `IOException`, what requirement must the enclosing method satisfy?
6. Why can `default -> throw ...` make a `switch` expression on `int` satisfy exhaustiveness?
7. In Java 17, when calling a method that uses `switch (someString)` with a `null` selector, is it guaranteed to enter `default`?
8. When `return switch (...)` is inside `try/finally`, does `finally` normally run before the method actually returns the value or throws the error outward?
9. Can `throw new RuntimeException(...)` be used as the third branch of the `?:` operator like a regular Java expression?
10. Why can a `switch statement` version that only logs in one branch and continues cause a "missing return statement" error for a method returning `int`?
11. For an `enum` whose constants are all listed in a `switch expression`, is `default` required? What is the benefit of omitting `default` as the enum evolves?
12. If a `catch` around `return switch` catches `IllegalArgumentException` and returns `fallback`, what must be clarified in the API contract before choosing this approach?

### Answer Key

1. The exception-throwing path does not complete normally, so it does not need to produce an `int`.
2. Use the short arrow form when there is only a single expression; use a `yield` block when you need to execute additional statements.
3. `return` is forbidden inside a `switch expression` block; change it to `yield 10;`.
4. That is a `switch statement`; `return` inside the block is valid and exits the method.
5. Catch or declare the checked `IOException`.
6. Because handling all remaining selectors via abrupt completion is also valid.
7. No; a `null` selector normally causes a `NullPointerException` in standard Java 17.
8. Yes, when control leaves the `try` scope normally; avoid writing `finally` code that masks the error or result.
9. No, `throw` is a statement rather than a regular expression operand.
10. Because that path completes normally without returning a value for the method.
11. No, if the enum is already fully covered; omitting `default` can help the compiler flag missing cases when the enum changes and is recompiled.
12. Determine whether invalid input is allowed to fall back to a default value or must report an error to the caller.

## 13. Takeaways

In a **`switch expression`**, valid branches produce a value using an expression or `yield`; a rejecting branch can use **`throw`** and does not have to produce a value. In a **`switch statement`**, a branch block can directly **`return`** from the method or **`throw`** to report an error. Both forms obey Java's checked exceptions, exception-handling rules, and control-flow rules. When designing code, ask: *should this branch provide a valid result, or should it terminate abruptly because of invalid input or state?*