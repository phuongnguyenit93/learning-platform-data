# Handling exceptions in a case body

**Topic:** Java Core Pattern Matching — Exceptions and null. This article uses **Java 21 or later**, the version in which **record patterns (JEP 440)** and **pattern matching for switch (JEP 441)** became standard features. Using **switch expressions** and **yield** has been stable since Java 14; examples combining record patterns with switch in this article require Java 21+.

## 1. Where can an exception occur in a switch?

A **case body** is the statement or expression executed **after a case is selected**. When using pattern matching, processing a value through a switch typically has the following stages:

1. Evaluate the **selector** expression inside the switch parentheses.
2. Test the **case** labels according to matching rules, including type/record patterns and any **when** guard condition.
3. Select the matching case and execute the **case body**.
4. If it is a **switch expression**, provide the result via the expression after the arrow or via **yield** from a block; if an exception occurs, evaluation completes abruptly.

Example:

~~~java
return switch (request) {
    case Register(String username, int age) -> {
        if (age < 18) {
            throw new IllegalArgumentException("underage");
        }
        yield "accepted: " + username;
    }
    case Cancel(var ticket) -> "cancelled: " + ticket;
    case Ping() -> "pong";
    case null -> throw new IllegalArgumentException("request");
};
~~~

This is an **illustrative snippet** based on the records and interface fully declared in section 5, not a standalone program.

How to read it: if request matches Register, the program enters the case block. When age is less than 18, **throw** makes the switch complete with an exception. Otherwise, **yield** produces a String as the result of the switch expression. There is no requirement that every branch return a value on every path: **a branch can always throw an exception**.

**Important distinction:** exceptions created in the **selector**, during **pattern/guard** evaluation, and inside the **case body** do not occur at the same time. A try/catch block placed *inside* a case body only catches exceptions thrown when that try block actually runs.

## 2. Three forms of case body and their relationship to exceptions

An arrow branch (**case ... ->**) in a switch expression can use an expression, a block, or a **throw** statement. All three forms are useful.

### 2.1. Branch returning a result directly

~~~java
case Ping() -> "PONG";
~~~

This branch returns a String directly from the expression after the arrow. If the expression contains a method call and that call throws an exception, the exception propagates out of the switch unless caught in an appropriate scope:

~~~java
// Illustration: format(request) is an application-defined method.
case Ping() -> format(request);
~~~

**A switch expression does not swallow exceptions.** It only produces a value when the branch completes normally.

### 2.2. Block branch with multiple statements and yield

~~~java
case Register(String username, int age) -> {
    if (age < 18) {
        yield "REJECTED: underage";
    }
    yield "REGISTERED: " + username;
}
~~~

A block can contain if statements, loops, try/catch, and other valid business statements. **yield** supplies a value for the entire switch expression; it is different from **return** for the enclosing method.

**Do not use break to return a value from a switch expression.** With a block form in a switch expression, use **yield** or allow a path to complete abruptly with **throw**. A block with a normal completion path that does not provide a value will not compile as a valid switch expression branch.

### 2.3. Branch intentionally throwing an exception

~~~java
case null -> throw new IllegalArgumentException("request");
~~~

This branch clearly defines the contract: a null request is unacceptable input. No String value is produced. Such a throw statement **is allowed** in an arrow branch of a switch expression without needing yield.

With a block containing both a check and a result:

~~~java
case Cancel(String ticket) -> {
    if (ticket == null || ticket.isBlank()) {
        throw new IllegalArgumentException("ticket");
    }
    yield "CANCELLED: " + ticket;
}
~~~

The error path throws an exception; the valid path yields a result. These two behaviors do not conflict.

## 3. Using try/catch inside a case body

Many operations in a branch can fail in a **recoverable** way: parsing data, validating an attribute, or calling a service. In these situations, catching a specific exception type right in the branch can help produce a clear business result.

Example:

~~~java
case Register(String username, int age) -> {
    try {
        String name = normalizedUser(username);
        if (age < 18) {
            yield "REJECTED: underage";
        }
        yield "REGISTERED: " + name;
    } catch (ValidationException ex) {
        yield "REJECTED: " + ex.getMessage();
    }
}
~~~

Here:

- **normalizedUser** may throw **ValidationException**, an application-defined checked exception.
- **try** wraps the call that can fail.
- **catch (ValidationException ex)** handles **the exact group of recoverable errors** for this branch.
- Both the valid path and the caught-error path **yield a String** for the switch expression.
- Other exceptions are not caught by this catch block, so they can still propagate to the caller.

**There is no need to catch every RuntimeException or Exception** just to make the case look "safe". Doing so can hide programming bugs such as an unintended NullPointerException, resource failures, or bugs in dependencies. Only convert an exception into a normal result when that is a well-defined rule.

### When should you catch in the case?

Catching in the case usually makes sense when the error **belongs specifically to this subtype** and the consumer has a concrete way to handle it. For example, a Register username format error can become **REJECTED: username**, whereas a system-wide data persistence failure may need to go through a higher-level error handling layer.

If multiple cases share the same error policy, copying the same try/catch into every case causes duplication. You can extract a helper method or use a **try/catch wrapping the entire switch** depending on responsibility boundaries.

## 4. Checked exceptions: catch or declare throws

Java checks **checked exceptions** at compile time. When a case body calls a method that declares **throws ValidationException** (extending Exception, not RuntimeException), the code containing the call must either:

- Catch ValidationException with a matching catch block; **or**
- Declare throws ValidationException (or an appropriate supertype) on the method containing the switch.

The example in section 3 catches it directly inside the case. Another method can choose to let the error propagate to the caller:

~~~java
// Illustrative snippet: uses Request, Register, Cancel, Ping and
// normalizedUser, ValidationException from the program in section 5.
static String handleStrict(Request request) throws ValidationException {
    return switch (request) {
        case Register(var username, var age) -> normalizedUser(username);
        case Cancel(var ticket) -> "CANCEL:" + ticket;
        case Ping() -> "PONG";
        case null -> throw new IllegalArgumentException("request");
    };
}
~~~

The difference: handleStrict **does not catch** ValidationException in the Register case. The method declares **throws ValidationException** so the caller decides how to handle it. The switch expression is still exhaustive over the three Request subtypes; having a checked exception **does not change the exhaustiveness requirement**.

For **unchecked exceptions** such as IllegalArgumentException or NullPointerException, Java does not require declaring throws. However, whether an error is allowed to propagate to the caller is still an API contract decision.

Decision table:

| Situation | Usually appropriate handling | Key point to preserve |
| --- | --- | --- |
| Register data fails defined validation | Catch the specific validation error and yield a rejection result | Do not turn system errors into user errors |
| Cancel command is missing a required code | Throw IllegalArgumentException or produce a domain error per contract | Do not return a fake "success" |
| I/O error or timeout needing retry | Let an orchestrator layer handle it, or convert to a typed result | Do not swallow the root cause |
| Unexpected error caused by a bug | Let it propagate to the appropriate error-reporting/observability mechanism | Do not catch broadly and ignore |
| Caller needs to manage a transaction | Let the exception or error result cross the transaction boundary | Do not accidentally commit when the operation fails |

## 5. Complete Java 21 program

The following program demonstrates a **sealed hierarchy**, **record patterns**, **try/catch in a case body**, **yield**, **throw**, null, and how a caller catches an unchecked exception. Save the whole file as **CaseBodyExceptionDemo.java**.

~~~java
public class CaseBodyExceptionDemo {
    sealed interface Request permits Register, Cancel, Ping {}

    record Register(String username, int age) implements Request {}
    record Cancel(String ticket) implements Request {}
    record Ping() implements Request {}

    static final class ValidationException extends Exception {
        ValidationException(String message) {
            super(message);
        }
    }

    static String normalizedUser(String username) throws ValidationException {
        if (username == null || username.isBlank()) {
            throw new ValidationException("username");
        }
        return username.trim();
    }

    static String handle(Request request) {
        return switch (request) {
            case Register(String username, int age) -> {
                try {
                    String name = normalizedUser(username);
                    if (age < 18) {
                        yield "REJECTED: underage";
                    }
                    yield "REGISTERED: " + name;
                } catch (ValidationException ex) {
                    yield "REJECTED: " + ex.getMessage();
                }
            }
            case Cancel(String ticket) -> {
                if (ticket == null || ticket.isBlank()) {
                    throw new IllegalArgumentException("ticket");
                }
                yield "CANCELLED: " + ticket;
            }
            case Ping() -> "PONG";
            case null -> throw new IllegalArgumentException("request");
        };
    }

    static void show(Request request) {
        try {
            System.out.println(handle(request));
        } catch (IllegalArgumentException ex) {
            System.out.println("ERROR: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show(new Register(" Lan ", 20));
        show(new Register("   ", 20));
        show(new Register("Minh", 16));
        show(new Cancel("T-01"));
        show(new Cancel(null));
        show(new Ping());
        show(null);
        show(new Register(null, 20));
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac CaseBodyExceptionDemo.java
java CaseBodyExceptionDemo
~~~

Exact output:

~~~text
REGISTERED: Lan
REJECTED: username
REJECTED: underage
CANCELLED: T-01
ERROR: ticket
PONG
ERROR: request
REJECTED: username
~~~

**Explanation of the execution paths:**

1. **Register(" Lan ", 20):** the record pattern binds username and age; normalizedUser trims whitespace; the branch yields **REGISTERED: Lan**.
2. **Register("   ", 20):** normalizedUser throws checked ValidationException; the catch inside the case turns the validation error into **REJECTED: username**.
3. **Register("Minh", 16):** username validation succeeds, the condition age < 18 causes the case to **yield REJECTED: underage**, with no exception.
4. **Cancel("T-01"):** valid input, the block **yields CANCELLED: T-01**.
5. **Cancel(null):** the check in the case body throws **IllegalArgumentException("ticket")**; show catches it and prints **ERROR: ticket**.
6. **Ping():** the case body is a direct String expression, returning **PONG**.
7. **request == null:** the switch selects **case null**, directly throwing IllegalArgumentException("request"); show prints **ERROR: request**.
8. **Register(null, 20):** the Register pattern still matches the record, but the username component is null. A validation error arises from normalizedUser, is caught, and is turned into **REJECTED: username**.

The output above clearly distinguishes **controlled rejection** (yield) from **exceptions propagating to the caller** (throw). The cases have no default because Request is a sealed interface and all three subtypes Register, Cancel, and Ping have covering branches. Case null handles a null selector separately; if omitted, subtype exhaustiveness does not guarantee the desired null handling.

## 6. Errors before the case body: a catch inside the case cannot catch them

A common misconception is thinking that placing a catch in a case block will catch every error "related to that case". In reality, you must consider **when the error occurs**.

### 6.1. The selector expression can throw

~~~java
// Illustration: loadRequest() may throw IOException.
String answer = switch (loadRequest()) {
    case Ping() -> "pong";
    case Register(var name, var age) -> "register";
    case Cancel(var ticket) -> "cancel";
    case null -> "null";
};
~~~

If **loadRequest()** throws IOException while producing the selector, **no case is selected**. A catch *inside the Register case* will never have a chance to run. If you want to manage retrieval errors, catch around the selector-producing call or around the entire switch, and declare/catch IOException according to checked exception rules.

This is **non-standalone illustrative code**; in a real project you must declare loadRequest and import IOException if used.

### 6.2. The when guard runs before the body

~~~java
// Illustration: isAllowed(name) may throw RuntimeException.
case Register(var name, var age) when isAllowed(name) ->
        "allowed";
~~~

If the Register pattern matches but **isAllowed(name)** throws an exception during guard evaluation, the case body **"allowed"** has not run yet. A catch placed in that case's body cannot handle errors coming from the guard. When a guard is a simple condition, this style is usually easy to read; for complex rules with error risk or side effects, consider moving the check into a block with try/catch for explicit management.

A **false** guard only means that case is not selected; the program tries the next matching branch. A guard **throwing an error** is completely different: the switch completes abruptly rather than falling through to the next case as if the guard returned false.

### 6.3. Record deconstruction can invoke accessors

A record pattern obtains components through accessors. If a record overrides an accessor and that accessor throws an exception when the pattern is tested, the error occurs **during matching**, not inside the case body.

According to Java 21 record pattern behavior, when an accessor completes abruptly due to a throwable, matching may throw **MatchException** with the original throwable as its **cause**. This is especially important if code overrides an accessor with logic that has side effects: a catch inside a case where matching has not completed will not catch that error.

For ordinary value records, keep accessors simple, consistent, and side-effect-free whenever possible. If the caller needs to handle matching errors, place a catch boundary **around the switch** and classify exceptions based on the contract, without assuming every error can be caught inside a branch.

### 6.4. Null selector versus null component

- **Null selector:** case null can handle it; without appropriate null handling, switching on a null reference can throw NullPointerException.
- **Null component:** a record such as Register(null, 20) can still match the pattern Register(var username, var age); the username variable can be null. Code in the body must check it before calling methods on it.
- **Nested record patterns:** if a subpattern requires a specific record, such as Outer(Inner(...)), a null nested component does not match that nested pattern; a fallback branch may be needed to ensure exhaustiveness.

Do not confuse **case null** with checking every null field inside a record.

## 7. Should you catch exceptions inside a case or outside the switch?

The two approaches serve different goals.

**Catch inside the case** when the error and its handling belong specifically to that branch:

~~~java
case Register(var username, var age) -> {
    try {
        yield normalizedUser(username);
    } catch (ValidationException ex) {
        yield "REJECTED: " + ex.getMessage();
    }
}
~~~

**Catch around the switch** when you need a shared error policy or when errors can arise from the selector, guard, or matching:

~~~java
// Illustrative snippet, Request and handle are declared in section 5.
static String handleSafely(Request request) {
    try {
        return handle(request);
    } catch (IllegalArgumentException ex) {
        return "ERROR: " + ex.getMessage();
    }
}
~~~

The handleSafely example only catches **IllegalArgumentException**, not every exception type. Boundary handling can vary by application: an API may map it to an HTTP status, a CLI may print a message, and a job processor may retry or send the message to a dead-letter queue.

### Do not turn every error into a success result

A dangerous anti-pattern:

~~~java
// Do not apply blindly: loses the error cause.
try {
    return handle(request);
} catch (Exception ex) {
    return "OK";
}
~~~

If the caller interprets **OK** as completed, invalid data may be treated as a success. For payment or state-changing operations, this can even cause a transaction to proceed down the wrong path.

Depending on requirements, you can: let the exception propagate; log and rethrow; or return an explicit result type such as **Success** / **ValidationFailure** / **InfrastructureFailure**. If you choose a result type, a sealed hierarchy and exhaustive switch are also good tools to force consumers to consider every case.

## 8. How does a switch statement differ from a switch expression?

With a **switch expression**, branches produce a value (or throw an exception). Value-returning branch blocks use **yield**. The value of the entire switch can be returned from a method:

~~~java
// Illustration inside a String handle(...) method.
return switch (request) {
    case Ping() -> "PONG";
    case Register(var name, var age) -> "REGISTER";
    case Cancel(var ticket) -> "CANCEL";
    case null -> throw new IllegalArgumentException("request");
};
~~~

With a **switch statement**, the goal is to execute statements; a case body can call methods, log, and catch exceptions without yielding a value:

~~~java
// Illustration inside a void method, using Request as in section 5.
switch (request) {
    case Ping() -> System.out.println("PONG");
    case Register(var name, var age) ->
            System.out.println("REGISTER:" + name);
    case Cancel(var ticket) -> {
        if (ticket == null) throw new IllegalArgumentException("ticket");
        System.out.println("CANCEL:" + ticket);
    }
    case null -> throw new IllegalArgumentException("request");
}
~~~

When pattern matching is used in a switch statement in Java 21, the compiler also checks exhaustiveness according to pattern switch rules. **Do not infer** that every Java switch statement must be exhaustive: traditional switch statements using only constant labels have different rules and can omit default.

**yield is not a way to exit a switch statement.** When you need to return a result from a method using a statement, you can use return according to method rules; when you need to return a result from a switch expression, use a case expression or yield.

## 9. Combining exceptions with guards, exhaustiveness, and dominance

There are three independent checks to keep in mind:

1. **Matching and guards:** a case has a matching pattern; if it has **when**, the guard must be true for the body to be selected.
2. **Exhaustiveness:** a switch expression must cover all relevant type cases (or have a general branch). A branch with an arbitrary guard generally does not cover the entire subtype.
3. **Dominance:** if a broader case precedes a narrower case, the narrower case can no longer be selected and causes a compile error.

Example:

~~~java
// Illustrative snippet: can be part of return switch (request).
case Register(var name, int age) when age >= 18 -> "ADULT";
case Register(var name, int age) -> "OTHER REGISTER";
~~~

The first branch is only for people aged 18 or older, and the second branch covers the remaining Register cases. If you place the **unguarded** Register branch first, the guarded branch after it is dominated.

When an error occurs in a guard, the error **does not make the guard false**. It propagates according to exception rules. If you need to turn a validation error into a business value, moving the validation into a block with try/catch is usually clearer.

**Throw does not replace exhaustiveness:** writing a case for only one subtype and throwing an exception in that case still does not cover the remaining subtypes. For a switch expression to compile, the branches must cover every value in the type's domain, including branches whose behavior is throw.

For example, with Request having Register, Cancel, and Ping, a switch containing only **case Register(...) -> throw ...** will not be exhaustive. You still need matching cases for Cancel and Ping or an intentional catch-all branch.

## 10. Limiting errors in case bodies through clear design

**Avoid overly long cases:** if each branch has multiple try/catch blocks, loops, logging, and service calls, a switch expression can become harder to read than dedicated helper methods. Extract the handling:

~~~java
// Illustrative snippet: registerSafely(...) is a separate method.
return switch (request) {
    case Register r -> registerSafely(r);
    case Cancel c -> cancelSafely(c);
    case Ping p -> "PONG";
    case null -> throw new IllegalArgumentException("request");
};
~~~

This way, the switch dispatches by subtype while helper methods manage specialized errors. If you want to test caught errors and exceptions left to propagate, the helper methods are convenient test targets.

**Do not use exceptions for ordinary control flow** when a boolean condition is clear enough. For example, age < 18 can be expressed by yielding a rejection result without necessarily throwing an exception. Exceptions fit situations that cannot complete normally or when the API contract defines errors that way.

**Do not lose stack traces:** if you catch and throw a new exception, consider passing the cause to the new exception's constructor. Do not merely concatenate messages and discard all cause information, especially for system errors.

**Do not catch Throwable or Error indiscriminately:** Error usually represents a problem more serious than an ordinary business failure. Usually it is better to catch specific checked/unchecked exception types.

**Be careful with side effects:** if a case calls an external service and then throws an exception, a caller retry can repeat the side effect. Define clear transaction boundaries, idempotency, and compensation mechanisms in real applications.

## 11. Recommended test matrix

| Scenario | Outcome to verify |
| --- | --- |
| Valid subtype | Correct case runs and yields the expected result |
| Valid validation | Does not enter catch, data is normalized |
| Validation throws checked exception | Catches the right type, produces rejection result per contract |
| Data violates condition and intentionally throws | Exception propagates to caller and is handled in the right place |
| Null selector | Case null or clear rejection policy |
| Record with null component | Pattern/validation behaves as expected |
| Guard returns false | Proceeds to the next matching branch |
| Guard throws an error | Error propagates, not mistaken for false |
| Error when creating selector or during matching | Catch inside body is not assumed to run |
| Adding a new subtype to the sealed hierarchy | Compiler requires updating branches if switch has no default |

You can write simple tests for both flows:

~~~java
// Illustrative test snippet inside the CaseBodyExceptionDemo class.
String result = handle(new Register("Lan", 20));
if (!result.equals("REGISTERED: Lan")) {
    throw new AssertionError("wrong result");
}

try {
    handle(new Cancel(null));
    throw new AssertionError("expected exception");
} catch (IllegalArgumentException ex) {
    if (!"ticket".equals(ex.getMessage())) {
        throw new AssertionError("wrong exception", ex);
    }
}
~~~

A test for an error that **yields instead of throwing** should verify the rejection result directly. A test for a throwing branch should use assertThrows (if a test framework is available) or try/catch as above. You should also check side effects and resources if the case calls external services.

## 12. Code review checklist

Before finalizing a switch with exception logic, ask yourself:

- [ ] Does each matching case have a clear contract: **return a result**, **yield a rejection result**, or **throw**?
- [ ] For a switch expression, does every normal path in a block supply a valid value?
- [ ] Are checked exceptions from calls inside a case caught or declared with throws?
- [ ] Is there an overly broad catch turning system errors into success results?
- [ ] Are null selectors, null components, and nested record patterns distinguished?
- [ ] Could an error occur in the selector, guard, or matching **before** the case body?
- [ ] Do the cases satisfy exhaustiveness without out-of-order dominance?
- [ ] Does exception behavior affect transactions, retries, logging, or resources?
- [ ] Are there tests for yield, catch, throw, and caller-propagated exception paths?

**Conclusion:** In Java Pattern Matching, a case body can **return a value**, **use a block with yield**, **catch specific errors with try/catch**, or **throw an exception to complete abruptly**. Good design means identifying **at which stage** an exception arises and **at which boundary** it should be handled, rather than catching everything in every case. Combining that approach with exhaustiveness, null, and flow scoping rules produces branching code that is both readable and preserves expected error behavior.