# When a Statement Is Clearer Than an Expression in Java Pattern Matching

## 1. Mental model: do you want to **perform work** or **compute a value**?

In Java, a **statement** describes an action or controls execution flow; an **expression** is a construct that evaluates to a value that can be assigned, passed to a method, or returned. With `switch`, Java supports both forms:

```java
// Switch expression: computes a value.
String label = switch (status) {
    case NEW -> "new";
    case DONE -> "done";
};

// Switch statement: performs an action.
switch (status) {
    case NEW -> System.out.println("Start work");
    case DONE -> System.out.println("Archive work");
}
```

These snippets illustrate the syntax, assuming `status` is an enum type with only `NEW` and `DONE`. Both can use arrow-style `case` branches `->`; **the arrow does not determine** whether the code is a statement or an expression. The usage context determines it: after `=` it is an expression; a standalone `switch` construct executed for its effects is a statement.

When combined with **pattern matching** (type patterns, record patterns, `when`), the choice still depends on intent:

- If each branch **produces a value** with the same meaning (a label, status code, or mapped result), a `switch expression` usually expresses this clearly.
- If each branch **executes a workflow** consisting of validation, service calls, logging, publishing events, or returning early from a method, a `switch statement` or a chain of `if` statements using patterns can be easier to follow.
- If different branches do not naturally share the same result type or have steps that should be skipped, forcing everything into an expression can make the code more complex without adding value.

**There is no absolute rule** that a statement is always better when there are side effects. A switch expression still allows blocks and `yield`. The criterion is which construct makes the intent and execution paths of the program clearest.

In Java 21, `switch` officially supports pattern matching (JEP 441) and record patterns (JEP 440). This article uses Java 21+ syntax, without needing to enable preview features.

## 2. When the same branch has to do multiple things, a statement is often more natural

Imagine an order command processing system:

```text
Command
  ├── Register(id, customer)
  │     ├── validate customer
  │     ├── save registration
  │     └── write audit log
  ├── Cancel(id, reason)
  │     ├── cancel registration
  │     └── write log
  └── Ship(id, address)
        ├── validate address
        └── submit shipment request
```

The goal of the handler method is not to produce a single string label; it must **execute the workflow** appropriate for the command type. A `switch statement` with record patterns expresses the steps directly:

```java
switch (command) {
    case Register(var id, var customer) -> {
        validateCustomer(customer);
        saveRegistration(id, customer);
        audit(id, "registered");
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
        audit(id, "cancelled");
    }
    case Ship(var id, var address) -> {
        validateAddress(address);
        submitShipment(id, address);
    }
}
```

This is an architectural illustration: `validateCustomer`, `saveRegistration`, `audit`, `cancelRegistration`, `validateAddress`, and `submitShipment` are application methods that need to be defined; the records also need to be declared. Each branch carries the meaning of *executing a command*. There is no need to create a `result` variable or return a dummy value just to satisfy an expression.

Forcing it into an expression might make each branch return a string such as `"done"`, `"cancelled"`, or `"shipped"` only for the caller to discard the result:

```java
// Illustrates an unsuitable design if the status is not used.
String ignored = switch (command) {
    case Register(var id, var customer) -> "registered";
    case Cancel(var id, var reason) -> "cancelled";
    case Ship(var id, var address) -> "shipped";
};
```

In terms of Java syntax, this is a valid expression when `Command` is an exhaustive sealed hierarchy as in the runnable example below. The problem is that **business behavior has been replaced by labels**; an unused value does not make the code clearer. If an actual status needs to be returned to the caller, an expression may again be a good choice.

## 3. Pattern matching serves both statements and expressions

Suppose we have the model:

```java
sealed interface Command permits Register, Cancel, Ship {}
record Register(String id, String customer) implements Command {}
record Cancel(String id, String reason) implements Command {}
record Ship(String id, String address) implements Command {}
```

We can use the same record patterns in both constructs.

**Statement — each case is an action:**

```java
switch (command) {
    case Register(var id, var customer) -> System.out.println("save " + id);
    case Cancel(var id, var reason) -> System.out.println("cancel " + id);
    case Ship(var id, var address) -> System.out.println("ship " + id);
}
```

**Expression — each case returns a value:**

```java
String label = switch (command) {
    case Register(var id, var customer) -> "register:" + id;
    case Cancel(var id, var reason) -> "cancel:" + id;
    case Ship(var id, var address) -> "ship:" + id;
};
```

Both are valid Java 21 when `command` has type `Command` and the records are declared as above. Both apply the same rules of matching by **record type** and deconstructing components in declaration order. Choosing a statement or an expression **does not change pattern semantics**.

For a multi-step system, a statement helps the reader see the sequence and where a branch can stop. For a mapping from one value to another, an expression helps the reader clearly see the result computed from every branch.

## 4. Complete Java 21 example and verified output

Save the entire program to the file **`StatementVsExpressionDemo.java`**. It shows that the same `Command` hierarchy can serve command processing with a statement and label generation with an expression; `instanceof` combined with `if` is suitable for independent conditional checks.

```java
public class StatementVsExpressionDemo {
    sealed interface Command permits Register, Cancel, Ship {}

    record Register(String id, String customer) implements Command {}
    record Cancel(String id, String reason) implements Command {}
    record Ship(String id, String address) implements Command {}

    // Process workflow: each branch can perform multiple steps or return early.
    static void process(Command command) {
        switch (command) {
            case Register(var id, var customer) -> {
                System.out.println("validate register:" + id);

                if (customer == null || customer.isBlank()) {
                    System.out.println("reject:missing customer");
                    return;
                }

                System.out.println("store:" + id);
                System.out.println("audit:registered");
            }
            case Cancel(var id, var reason) -> {
                System.out.println("cancel:" + id);
                System.out.println("audit:cancelled");
            }
            case Ship(var id, var address) -> {
                if (address == null || address.isBlank()) {
                    System.out.println("reject:missing address");
                    return;
                }

                System.out.println("ship:" + id + "->" + address);
            }
        }
    }

    // Map a command to a string: expression with a clear purpose.
    static String preview(Command command) {
        return switch (command) {
            case Register(var id, var customer) -> "register:" + id;
            case Cancel(var id, var reason) -> "cancel:" + id;
            case Ship(var id, var address) -> "ship:" + id;
        };
    }

    // Sequential checks: if + instanceof pattern can be more readable.
    static String classify(Object input) {
        if (input instanceof String message) {
            if (message.isBlank()) {
                return "empty text";
            }
            return "text:" + message;
        }

        if (input instanceof Number number) {
            return "number:" + number;
        }

        return "other";
    }

    // Traditional statement: not required to cover every integer.
    static void traditional(int priority) {
        switch (priority) {
            case 1 -> System.out.println("urgent");
            case 2 -> System.out.println("normal");
        }
    }

    public static void main(String[] args) {
        process(new Register("O-1", "Lan"));
        process(new Register("O-2", ""));
        process(new Ship("O-3", "Hue"));
        process(new Cancel("O-4", "duplicate"));

        System.out.println(preview(new Ship("O-5", "Hanoi")));
        System.out.println(classify("hello"));
        System.out.println(classify("  "));

        traditional(3); // No matching case, so nothing else is printed.
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 StatementVsExpressionDemo.java
java StatementVsExpressionDemo
```

Exact output:

```text
validate register:O-1
store:O-1
audit:registered
validate register:O-2
reject:missing customer
ship:O-3->Hue
cancel:O-4
audit:cancelled
ship:O-5
text:hello
empty text
```

The program uses ASCII strings in the output to avoid depending on terminal encoding configuration. Comments are compiled with `-encoding UTF-8`.

### Reading the output along the execution flow

- `process(Register("O-1", "Lan"))` performs three operations: printing validation, storing the order, and writing the audit. The `System.out.println` calls merely simulate side effects; a real application can replace them with a repository/service.
- `process(Register("O-2", ""))` prints two lines and then **`return`s from the `process` method**. As a result, there is no `store` or `audit` line for the rejected order. A `return` inside a statement's case block can exit the enclosing method directly.
- `process(Ship(...))` validates the address before the shipping step; these steps are not a value computation that needs `yield`.
- `preview` uses a switch expression because the method's contract is to **return a descriptive string**. There are no operations that need to abort mid-branch.
- `classify` uses two `instanceof` checks with `String` and `Number` type patterns because each case has its own rules and follows a sequential check order. `null` does not match either `instanceof` check, so it reaches `"other"`.
- `traditional(3)` prints nothing: this is a traditional switch statement on `int`, which does not need branches for all integers.

## 5. When a statement is especially clear: validating data and returning early

Consider a command-handling branch that may need to reject early:

```java
case Register(var id, var customer) -> {
    if (customer == null || customer.isBlank()) {
        reportValidationError(id);
        return;
    }

    saveRegistration(id, customer);
    notifySuccess(id);
}
```

This is **part of a switch statement**, assuming the enclosing method returns `void` and `reportValidationError`, `saveRegistration`, and `notifySuccess` are implemented in the application.

This structure is beneficial when:

1. An invalid condition leads to reporting and **ending the method** immediately, without needing to merge all paths into a common result.
2. A valid condition proceeds with side effects in sequence, with each step named to reflect its purpose.
3. Each operation can fail according to its own contract; the reader sees where errors are handled or exceptions are propagated.
4. The workflow has branches with an uneven number of steps; an expression returning a generic label does not adequately reflect the work done.

If the method **must produce a result** after validation, a switch expression is still completely appropriate. The questions to ask are "where is the output used?" and "does the control flow have multiple exit paths?" You should not decide based on the length of the expression.

## 6. When `if` + pattern statements are clearer than a large switch

Pattern matching does not require using `switch`. With `instanceof`, we can follow a sequence of independent conditions:

```java
static String classify(Object input) {
    if (input instanceof String text) {
        if (text.isBlank()) {
            return "empty text";
        }
        return "text:" + text;
    }

    if (input instanceof Number number) {
        return "number:" + number;
    }

    return "other";
}
```

Notable points:

- Each branch contains a type pattern and can check additional **separate conditions**.
- The variable `text` is only in scope where `input` is proven to match `String`; similarly, `number` is scoped to `Number`.
- `return` exits the method in the handled branch, so the end serves as the fallback case.
- There is no compile-time requirement to prove a closed set of patterns; you are deliberately writing a sequence of statements with a fallback exit.

The `if` pattern is useful when processing is a series of **guard clauses** or when branches are ordered by business priority. However, if you have a `sealed` hierarchy with a closed set of cases and want the compiler to check whether you forgot a subtype, `switch` with patterns usually expresses it better.

## 7. Do not confuse them: switch expressions can also have blocks and side effects

Do not invent a false rule that "an expression can only be written on one line" or "you cannot log inside an expression." Java allows `case` blocks with `yield`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> {
            System.out.println("trace:string");
            yield text.isBlank() ? "empty" : text.toUpperCase();
        }
        case null -> "missing";
        default -> "other";
    };
}
```

Example:

```java
System.out.println(describe("hello"));
System.out.println(describe(null));
```

Output:

```text
trace:string
HELLO
missing
```

The syntax above is valid Java 21 (assuming the method is placed inside a class with an appropriate `main` call). `yield` **returns a value from the switch expression branch**, whereas the outer `return` in `return switch (...)` returns the result from the method.

In an expression, each branch must produce a value or complete abruptly (for example, by throwing an exception). You should not "invent" a dummy value just to make an expression valid when the sole goal is executing commands. If a branch is primarily a sequence of actions and `yield` only outputs a low-meaning constant, a statement usually expresses the intent better.

## 8. Control-flow rules to distinguish

| Construct | Purpose | Key points to remember |
| --- | --- | --- |
| `switch statement` | Execute actions | A `case ... -> { ... }` branch can contain multiple statements and can `return` from the method |
| `switch expression` | Compute a value | A block branch uses `yield value;` when it needs to pass a value out |
| `if (...)` with `instanceof` pattern | Sequential conditional checks | Can exit early with `return`, `throw`, or continue processing |
| `break;` in a statement | Exit the matching enclosing switch/loop | Not the way to yield a value from a switch expression |
| `throw` | Abrupt completion | Can be used when any kind of branch encounters an unrecoverable error |

With `case ... ->` (in both statements and expressions), there is **no fall-through** from one branch to the next. Unlike traditional `case:`, which can fall through if `break` is omitted, the arrow form gives each branch clearer, isolated behavior.

In a switch statement using `case ... -> { ... }`, you can place multiple statements in the block, call methods, mutate state, or `return` early. In a switch expression using `case ... -> { ... }`, the block must end with `yield` on every normal completion path (or throw an exception on that path).

**Do not arbitrarily swap `yield` and `return`:** `yield` produces the value of the switch expression; `return` exits the enclosing method in contexts where that is allowed. A `void` method can use `return;` to stop, while `return switch (...)` is for methods with a compatible return type.

## 9. Exhaustiveness rules: traditional statements and pattern statements differ

A dangerous misconception is that "a switch statement does not need to cover all cases." That is only true for **traditional switch statements** within the scope Java retains for backward compatibility.

### 9.1. Traditional switch statements can omit cases

```java
static void printPriority(int priority) {
    switch (priority) {
        case 1 -> System.out.println("urgent");
        case 2 -> System.out.println("normal");
        // priority == 3: no matching branch; the method continues.
    }
}
```

This is a switch statement on `int` using constant labels; Java allows omitting `default`. If the value is `3`, no statement inside the switch is executed. Add `default` if an unknown value needs to be logged or rejected.

### 9.2. Enhanced switch statements with patterns must be exhaustive

The following snippet **intentionally fails to compile** on Java 21:

```java
static void inspect(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
        case Number number -> System.out.println(number);
        // No default or pattern covering the remaining types.
    }
}
```

Typical error:

```text
the switch statement does not cover all possible input values
```

Because `Object` includes many other types, the pattern statement above is not exhaustive. A fix:

```java
static void inspect(Object input) {
    switch (input) {
        case String text -> System.out.println(text);
        case Number number -> System.out.println(number);
        case null -> System.out.println("null");
        default -> System.out.println("other");
    }
}
```

In Java 21, enhanced switch statements have exhaustiveness rules similar to switch expressions. Exhaustiveness proofs from the selector type also apply to `enum` and `sealed` types, such as the `Register`, `Cancel`, and `Ship` records belonging to `Command` in the complete program.

### 9.3. A branch with `when` does not necessarily cover the whole type

```java
switch (command) {
    case Ship(var id, var address)
            when address != null && !address.isBlank() -> {
        submitShipment(id, address);
    }
    case Ship(var id, var address) -> {
        reportInvalidAddress(id);
    }
    case Register(var id, var customer) -> {
        saveRegistration(id, customer);
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
    }
}
```

This is an **illustrative snippet**, assuming the application methods are already declared. The guarded `Ship` branch handles valid addresses; another `Ship` branch is still needed for missing or blank addresses. If you only write `case Ship(...) when ...` and forget the path where the guard fails, the switch may not be exhaustive.

Branch order also matters: placing an unguarded `Ship(...)` pattern **before** a `Ship(...) when ...` pattern can cause the narrower branch to be dominated (*dominated case*) and trigger a compile-time error. With a sealed hierarchy, listing all subtypes helps the compiler remind you to update the code when a new command type is added.

## 10. Handling `null`, business errors, and exceptions

Both statements and expressions need clear data contracts.

- With `if (obj instanceof Type t)`, an input of `obj == null` makes `instanceof` evaluate to `false`, without throwing an NPE for the check itself.
- With `switch (reference)` on a reference type, if the selector is `null` and there is no matching `case null`, the switch normally throws `NullPointerException`, **even when the remaining type branches are exhaustive**.
- When a nested record pattern encounters a `null` child record component, the sub-pattern does not match; by contrast, `var child` can bind a reference component whose value is `null`. A pattern match does not prove that the data is valid.

You can choose to handle `null` directly in a statement:

```java
switch (command) {
    case null -> System.out.println("reject:null command");
    case Register(var id, var customer) -> System.out.println("register " + id);
    case Cancel(var id, var reason) -> System.out.println("cancel " + id);
    case Ship(var id, var address) -> System.out.println("ship " + id);
}
```

Or reject it at the start of the method:

```java
java.util.Objects.requireNonNull(command, "command");
// Then use switch with the appropriate patterns.
```

These are **illustrative snippets** using the `Command` type from section 4. Choose a consistent behavior: reject `null` with an exception or handle it in a meaningful branch, depending on the API contract.

**Exceptions do not automatically make a statement better.** A switch expression can use `throw new IllegalArgumentException(...)` in an invalid branch. A statement is usually clearer when you must perform multiple recovery steps, log, route, and return early; an expression is usually clearer when you want to reduce every path to a **result or an error**.

## 11. Common design mistakes and how to fix them

### 11.1. Creating a dummy value just to use a switch expression

Hard-to-read form:

```java
// Illustrates the idea, not a standalone program.
String unused = switch (command) {
    case Register(var id, var customer) -> {
        saveRegistration(id, customer);
        yield "ok";
    }
    case Cancel(var id, var reason) -> {
        cancelRegistration(id, reason);
        yield "ok";
    }
    case Ship(var id, var address) -> {
        submitShipment(id, address);
        yield "ok";
    }
};
```

If `unused` is never read, you can switch to a switch statement and remove `yield "ok"`. Conversely, if you need an `OperationResult` object representing the outcome of each branch (success/failure, error code, response data), keep the expression and return a **meaningful value**.

### 11.2. Hiding multiple ordered steps inside an expression

Nesting multiple calls with side effects inside the `?:` operator or method chaining can make the execution order hard to follow. A block statement makes it clear when validation happens, when data is written, when notifications are sent, and when execution stops.

### 11.3. Confusing `->` with a switch expression

`switch (x) { case A -> doWork(); }` is a statement when it stands alone. `return switch (x) { case A -> "a"; ... };` is an expression used inside `return`. Do not decide the construct type based solely on the arrow token.

### 11.4. Ignoring exhaustiveness of enhanced statements

A statement with type/record patterns must have branches covering the entire selector. If you hit a missing-case error, check the `sealed` hierarchy, `when` guards, and open selector types. Do not ignore the error thinking "a statement is allowed to omit cases."

### 11.5. Using `default` and losing useful warnings

With a `sealed` hierarchy that has a known set of subtypes, listing `Register`, `Cancel`, and `Ship` explicitly lets the compiler warn you when a new type is added that needs handling. Adding `default` mechanically can throw away the chance to catch business changes. For an open selector type like `Object`, `default` is usually appropriate.

### 11.6. Writing overly long branches and mixing responsibilities

A statement fits multi-step workflows, but it is **not a license for a hundred-line method**. When a registration-handling branch needs validation, querying, database writes, service calls, and notifications, extract clearly named methods or services: `handleRegister`, `handleCancel`, `handleShip`. The switch statement should only dispatch to the right place.

### 11.7. Using a statement with a result variable instead of a simple expression

If the sole purpose is to produce a label, the following pattern easily leads to variable-initialization issues:

```java
String label;
switch (stage) {
    case NEW -> label = "new";
    case DONE -> label = "done";
}
```

The `label` variable might remain unassigned if `stage` has another state. Even for an enum with exactly two states `NEW` and `DONE`, the compiler does not automatically treat a traditional statement without `default` as definite assignment on every path. When the goal is mapping values, a switch expression usually avoids managing a potentially unassigned result variable.

## 12. Decision table by goal

| Primary goal | Usually more readable approach | Why |
| --- | --- | --- |
| Convert `Stage` into a UI string | `switch expression` | Each branch produces a value, fitting `return` or assignment |
| Receive `Command` and run an action workflow | `switch statement` with record patterns | Each branch is a clear sequence of actions |
| Validate and `return` early on error | `if` or `switch statement` | Clearly shows the exit paths from the method |
| Return a result object for each command type | `switch expression` | The result value is meaningful and used by the caller |
| Distinguish all subtypes of a sealed hierarchy | Switch with exhaustive type/record patterns | The compiler helps detect missing branches |
| Check a few independent conditions with a fallback | `if` + `instanceof` patterns | Easy to express priority order and separate guards |
| Log and then return a simple value | Depends on complexity; an expression with `yield` is still valid | No need to switch to a statement just because of a single log line |
| Coordinate multiple functions/services with recovery steps | Statement or dedicated handler methods | The workflow is the primary thing to understand |
| Handle `null` values explicitly | `case null` or input validation | Type exhaustiveness does not automatically define null behavior |

A practical question before writing code: **"Am I building a value-to-value mapping, or am I describing how the program does work?"** If it is a mapping, think of an expression; if it is a workflow, start from a statement. Then consider exhaustiveness, null handling, extensibility, and testability.

## 13. Exercises and answers

**Exercise 1 — Choosing the switch form.** A method receives a `Command`, must validate information, update the order, and then emit an event; the method returns `void`. Which form is easier to understand?

Answer: A `switch statement` with patterns for each command type. You can extract each case into a handler if the workflow grows long; there is no need to invent a value just to satisfy expression syntax.

**Exercise 2 — A different goal.** A method receives a `Command` and returns the display name of the command. Which form is easier to understand?

Answer: A `switch expression` returning `String`. All branches produce a value, and the compiler checks for missing cases in the sealed hierarchy.

**Exercise 3 — Passing null.** If you call `process(null)` in the section 4 example, what happens?

Answer: The pattern-based switch statement on `Command` has no `case null`, so it throws `NullPointerException`. To handle `null`, add `case null` or check before entering the switch.

**Exercise 4 — Can a pattern-based statement omit cases?** Given `Object input` and a switch with only `case String s` and `case Number n`. What is the compilation result?

Answer: An exhaustiveness error (`the switch statement does not cover all possible input values`) because this is an enhanced switch statement with patterns on type `Object`. You can add `default` or an appropriate catch-all pattern.

**Exercise 5 — When `when` fails.** Does a `case Ship(var id, var address) when address != null` handle every `Ship`?

Answer: No. When `address == null`, the guard is false so the case does not match. If exhaustiveness on sealed `Command` is required, add an unguarded `Ship` branch and place it after the guarded branch.

**Exercise 6 — `yield` or `return`?** In a switch expression with a `case String s -> { ... }` block, what do you use to make the expression evaluate to `s.toUpperCase()`?

Answer: `yield s.toUpperCase();`. In `return switch (...)`, the outer `return` returns that value from the method. In a switch statement inside a `void` method, `return;` inside a case block can stop the entire method.

**Exercise 7 — Checking the output.** In the complete example, why is there no `store:O-2` line?

Answer: `customer` is an empty string, so the `Register` case prints `reject:missing customer` and `return`s from `process` before the store step. If a design needs to write an audit log even on rejection, you must explicitly place the audit step on the rejection path before `return` or use an appropriate shared handling mechanism.

## 14. Key takeaways

- **Statements** describe work to be done and are usually clearer when there are multiple steps, side effects, and early returns.
- **Expressions** represent a value to be computed and are usually clearer when the cases are mappings with a shared purpose.
- Pattern matching (`instanceof`, type patterns, record patterns, `when`) can appear in both statements and expressions; type-checking semantics do not change with the choice of switch form.
- The `->` arrow appears in both forms. In an expression, multi-statement blocks use `yield` to produce a value; a statement can use `return` to exit the method.
- **Enhanced switch statements** using patterns must be exhaustive; only traditional statements have the backward-compatibility exception for not covering all values.
- `null`, missing data, and unmatched guard cases must be handled according to the API contract and should not be conflated with compiler-proven exhaustiveness.
- Choose the construct that makes the method's responsibility easy to read; overly long branches should be extracted into handlers rather than debated as statement versus expression.

**Official references:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Java Language Specification 21 — switch statements (`14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11), [Java Language Specification 21 — switch expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
