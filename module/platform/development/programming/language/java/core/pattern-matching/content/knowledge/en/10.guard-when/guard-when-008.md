# Guards with Side Effects and Risks in Java Pattern Matching

## 1. When a Branch-Selection Condition Mutates the Program

Starting from Java 21, pattern matching in `switch` supports labels of the form:

~~~java
case String text when text.length() >= 3 -> "VALID:" + text;
~~~

The part after `when` is a **guard**: an expression of type `boolean` or `Boolean`, evaluated **after the pattern has matched**. If the guard is true, the case is selected; if the guard is false, Java evaluates the next label.

Even though it looks like a check, a guard is still a **normal Java expression**. It can call methods, access a mutable object, write logs, increment counters, update data, or throw exceptions. Operations that mutate state or produce observable effects are called **side effects**.

A risky example:

~~~java
case Ticket t when consumeCredit(t) -> "APPROVED";
~~~

If `consumeCredit(t)` **deducts a credit before returning its result**, it can mutate data even when the guard returns `false` and Java moves on to the `DECLINED` branch. Pattern matching does not automatically roll back those changes.

**Lesson objectives:**

- Understand exactly when a guard is evaluated and why a guard returning `false` can still leave side effects behind.
- Distinguish observable side effects from pure checking logic (*pure predicate*).
- Recognize risks from mutation, logging/metrics, I/O, runtime errors, nullable `Boolean`, and operation retries.
- Know how Java 21 restricts local variable mutation in guards, yet does not prevent all side effects.
- Structure code around **guard checks – branch body performs the action**, while understanding the concurrency limitations of this separation.
- Write tests that prove guard evaluation order, results, and post-execution state.

Complete programs use `javac --release 21`; **no preview features are required**. Snippets marked “intentionally fails to compile” are solely for analyzing errors.

## 2. Evaluation Mechanism: Pattern First, Guard Second, Branch Last

Consider:

~~~java
String result = switch (value) {
    case String s when checkA(s) -> "A";
    case String s when checkB(s) -> "B";
    case String s -> "OTHER_STRING";
    case null -> "NULL";
    default -> "OTHER";
};
~~~

This is an excerpt inside a method with `Object value`; `checkA` and `checkB` are illustrative methods that need to be defined.

Key execution rules:

1. Java evaluates the selector `value` and then looks for an applicable label in case order.
2. A label `case String s` must match the type `String` first. If it does not match, Java **does not** invoke that label's guard.
3. If the pattern matches, `s` is bound and the guard `checkA(s)` is evaluated.
4. If the guard is true, Java executes the rule `-> "A"` and completes the switch expression; `checkB(s)` is not called.
5. If the guard is false, Java evaluates the next label. If that label has a guard, another guard may be called.
6. A guard returning `false` **does not** restore the initial state. If it has already mutated variables or objects, the side effect remains.
7. If a guard throws an exception, branch selection terminates abruptly with that exception. Java does not treat it as `false` and does not automatically move to the next case.

**A guard is neither a transaction nor a function that is always evaluated:** it only runs if the corresponding pattern match succeeds and label evaluation reaches that position. With multiple guarded cases, a single switch may invoke multiple guards before selecting a branch.

For `null`, the type pattern `String s` does not match, so the `String` guards do not run. However, switching on `null` itself still requires an appropriate handling path such as `case null`; `default` alone generally does not substitute for `case null` in a Java 21 pattern switch.

## 3. What Is a Side Effect in a Guard?

A **pure predicate** only computes a true/false answer from its inputs in a way that does not alter observable state. For example, with an immutable `String`:

~~~java
case String s when s.length() >= 3 && !s.isBlank() -> "VALID";
~~~

Reading length, checking for blank, and Boolean operators do not modify the `String` object. Given the same input and the same relevant state, the result is predictable.

By contrast, the following operations create side effects or depend on mutable state:

| Operation in guard | Side effect or risk |
| --- | --- |
| `counter.incrementAndGet() > 3` | Increments the counter every time the guard is called, even when the branch is not selected |
| `ticket.credits-- > 0` | Mutates business data during branch selection |
| `repository.save(record)` | May write to a database, causing I/O and exceptions |
| `queue.poll() != null` | Consumes a queue element just to check it, making subsequent calls differ |
| `sendEmail(...)` | External action may occur before the final branch is known |
| `clock.instant().isAfter(deadline)` | Usually does not mutate the clock, but the result depends on time; not a stable condition across calls |
| `externalFlag.get()` | Reads shared state that can be modified by another thread; consistency must be considered |

**Not every side effect is always wrong.** For instance, incrementing the number of times a guard is evaluated can serve observability purposes, but it must be intentional behavior. Risk arises when the code author assumes a guard only determines true/false without realizing it can mutate state, write data, or make results depend on case evaluation order.

The methods in the table are conceptual examples; not every Java API has the exact names shown. Any operation not defined in a complete program needs an appropriate implementation.

## 4. Runnable Program: A Guard Is Called Even When Its Case Is Not Selected

To see actual evaluations, we add a counter and print a log whenever a guard runs. Save as `GuardTraceDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class GuardTraceDemo {
    static final AtomicInteger calls = new AtomicInteger();

    static boolean probe(String label, String text, boolean passed) {
        System.out.println("GUARD " + label + " " + text
            + " -> " + passed + ", calls=" + calls.incrementAndGet());
        return passed;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when probe("A", s, s.startsWith("A")) -> "STARTS_A";
            case String s when probe("LONG", s, s.length() >= 3) -> "LONG";
            case String s -> "OTHER_STRING";
            case null -> "NULL";
            default -> "NOT_STRING";
        };
    }

    public static void main(String[] args) {
        System.out.println("RESULT " + classify("Anna"));
        System.out.println("RESULT " + classify("Bob"));
        System.out.println("RESULT " + classify("Hi"));
        System.out.println("RESULT " + classify(42));
        System.out.println("RESULT " + classify(null));
        System.out.println("TOTAL=" + calls.get());
    }
}
~~~

Run on JDK 21+:

~~~bash
javac --release 21 GuardTraceDemo.java
java GuardTraceDemo
~~~

Exact output:

~~~text
GUARD A Anna -> true, calls=1
RESULT STARTS_A
GUARD A Bob -> false, calls=2
GUARD LONG Bob -> true, calls=3
RESULT LONG
GUARD A Hi -> false, calls=4
GUARD LONG Hi -> false, calls=5
RESULT OTHER_STRING
RESULT NOT_STRING
RESULT NULL
TOTAL=5
~~~

Explanation for each call:

- **`"Anna"`:** pattern `String s` matches; guard `A` is called, returns `true`, and increments the counter to 1. Rule `STARTS_A` is selected, and the subsequent `LONG` guard does not run.
- **`"Bob"`:** guard `A` returns `false` but has already incremented the counter to 2; guard `LONG` is called, increments the counter to 3, and returns `true`. The result is `LONG`.
- **`"Hi"`:** both guards return `false`; the counter is incremented twice more (4 and 5). The final result is `OTHER_STRING`.
- **`42`:** does not match `String`, so neither guard is called; `default` returns `NOT_STRING`.
- **`null`:** enters `case null`; neither guard runs.

**Key takeaway:** the number of guard invocations **does not equal** the number of times the guard's branch is selected. A `false` guard can still increment metrics, produce logs, or update data. If tests only inspect the `RESULT` value without checking the counter, bugs are easily missed.

In the demo, `AtomicInteger.incrementAndGet()` makes each increment atomic for the counter variable itself. However, **atomicity of the counter does not turn the entire case-selection and business-processing flow into a transaction**.

## 5. Mutation Risk: A Guard Loses Credits Even When Declined

The following example simulates a ticket with a number of usage credits. The program writes a guard with a side effect **intentionally to expose the design flaw**. Save `GuardMutationDemo.java`:

~~~java
public class GuardMutationDemo {
    static final class Ticket {
        int credits;
        Ticket(int credits) { this.credits = credits; }
    }

    static boolean consumeEvenOnFailure(Ticket t) {
        --t.credits;
        return t.credits >= 0;
    }

    static String attempt(Object value) {
        return switch (value) {
            case Ticket t when consumeEvenOnFailure(t) ->
                "APPROVED, credits=" + t.credits;
            case Ticket t -> "DECLINED, credits=" + t.credits;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(2);
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
    }
}
~~~

~~~bash
javac --release 21 GuardMutationDemo.java
java GuardMutationDemo
~~~

Output:

~~~text
APPROVED, credits=1
APPROVED, credits=0
DECLINED, credits=-1
~~~

The problem:

1. `case Ticket t` matches the ticket object.
2. The guard calls `consumeEvenOnFailure(t)` and **decrements `t.credits` before checking the condition**.
3. On the first two calls, credits decrease from 2 → 1 → 0, the guard returns `true`, and the `APPROVED` branch runs.
4. On the third call, credits decrease from 0 → -1, the guard returns `false`, and Java falls through to the unguarded `Ticket t` case.
5. Even though the result is `DECLINED`, the balance has become **-1**. If this example were a real transaction, it could corrupt business data.

Guards provide no rollback capability. The same situation occurs if a guard sends a payment request, removes an element from a queue, writes user state, or increments failed login attempts **before the final branch is known**.

A code smell indicator: a guard method name contains an action verb such as `charge`, `consume`, `reserve`, `delete`, `publish`, or `send`, when its actual job should only be checking a condition.

## 6. Separating Decision and Action: Let `when` Only Check

A clearer version uses the guard to inspect state, while the credit-consuming operation lives in the **rule body** after the case is selected. Save `GuardActionSeparationDemo.java`:

~~~java
public class GuardActionSeparationDemo {
    static final class Ticket {
        int credits;
        Ticket(int credits) { this.credits = credits; }
    }

    static String attempt(Object value) {
        return switch (value) {
            case Ticket t when t.credits > 0 -> {
                t.credits--;
                yield "SPENT, credits=" + t.credits;
            }
            case Ticket t -> "NO_CREDIT, credits=" + t.credits;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(2);
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt("other"));
    }
}
~~~

~~~bash
javac --release 21 GuardActionSeparationDemo.java
java GuardActionSeparationDemo
~~~

Output:

~~~text
SPENT, credits=1
SPENT, credits=0
NO_CREDIT, credits=0
OTHER
~~~

Unlike the previous demo:

- The guard `t.credits > 0` only **reads** state. When false, the `NO_CREDIT` branch returns a result without deducting any credit.
- Only the rule body `case Ticket t when ... -> { ... }` deducts the credit and `yield`s the result.
- On the third attempt, credits stay at `0` rather than becoming `-1`.

**A very important limitation:** this fixed example only demonstrates correct behavior in a **single thread**. If the same `Ticket` is processed concurrently by multiple threads, one thread may observe `credits > 0` and then have another thread modify `credits` **before the deduction step occurs**. Separating the guard and the action helps eliminate hidden side effects, but **does not automatically create atomicity**.

For shared state, you need an atomic check-and-update operation such as an appropriate compare-and-set, a lock protecting the state, a database transaction, or a business API with concurrency guarantees. Otherwise, you still have a **TOCTOU** (*time-of-check to time-of-use*) bug: the condition was true at check time, but no longer true when the action executes.

For better design, responsibilities are often separated into:

- **Data classification:** patterns and guards focus on validating types/conditions.
- **Decision:** choosing a result or a command/intent model.
- **Action execution:** handled at a clear business boundary, with synchronization/transactions when needed.

Do not use step separation as a substitute for atomic checks where there is resource contention.

## 7. Guard Throwing an Exception: Java Does Not Fall Through to Another Case

A guard can throw an exception during evaluation. That is **abrupt completion**: searching for a `case` label terminates with the exception. A throwing guard is **not** treated as a guard returning `false`.

A common example is parsing data inside a guard. Save `GuardExceptionDemo.java`:

~~~java
public class GuardExceptionDemo {
    static boolean positiveNumber(String text) {
        System.out.println("PARSE " + text);
        return Integer.parseInt(text) > 0;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when positiveNumber(s) -> "POSITIVE";
            case String s -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("RESULT " + classify("7"));
        System.out.println("RESULT " + classify("0"));
        try {
            System.out.println("RESULT " + classify("abc"));
        } catch (NumberFormatException ex) {
            System.out.println("CAUGHT NumberFormatException");
        }
    }
}
~~~

~~~bash
javac --release 21 GuardExceptionDemo.java
java GuardExceptionDemo
~~~

Output:

~~~text
PARSE 7
RESULT POSITIVE
PARSE 0
RESULT OTHER_STRING
PARSE abc
CAUGHT NumberFormatException
~~~

Reading the output:

- `"7"` parses as a positive number, so the guard is true; the `POSITIVE` branch runs.
- `"0"` parses, but the condition `> 0` is false; Java continues to `case String s` and returns `OTHER_STRING`.
- `"abc"` causes `Integer.parseInt` to throw `NumberFormatException`; the `OTHER_STRING` branch **does not run** because guard evaluation terminated with an exception.
- `System.out.println("PARSE " + text)` is also a side effect: the log was already written before the exception occurred.

If data may be unparseable and a “parse failure” should be treated as a non-match, write a predicate with an explicit error policy, such as `try/catch NumberFormatException` returning `false` when parse failure is a normal condition. **Only catch genuinely expected errors**; do not use `catch (Exception) { return false; }` to silently swallow connection errors, data corruption, or serious programming bugs.

If parsing produces a business value needed in the selected branch, consider parsing once at an earlier layer and using a validated data type, rather than repeating potentially throwing operations across multiple guards.

## 8. Nullable `Boolean` Can Also Cause a Guard to Throw `NullPointerException`

Java 21's JLS allows a guard to have type `boolean` **or `Boolean`**. If a guard returns `Boolean`, Java unboxes it to `boolean` to decide the branch. If the value is `null`, unboxing throws `NullPointerException`.

Save `GuardBooleanNullDemo.java`:

~~~java
public class GuardBooleanNullDemo {
    static Boolean nullableFlag(String s) {
        return s.isEmpty() ? null : Boolean.TRUE;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when nullableFlag(s) -> "TRUE";
            case String s -> "FALSE";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("x"));
        try {
            System.out.println(classify(""));
        } catch (NullPointerException ex) {
            System.out.println("CAUGHT NullPointerException");
        }
    }
}
~~~

~~~bash
javac --release 21 GuardBooleanNullDemo.java
java GuardBooleanNullDemo
~~~

Output:

~~~text
TRUE
CAUGHT NullPointerException
~~~

For the empty string `""`, the pattern `String s` matches, but `nullableFlag(s)` returns `null`. The guard does not treat `null` as `false`; it throws during unboxing and does not run the next `case String s`.

**How to avoid:** prefer predicates returning primitive `boolean`. If an API must return a nullable `Boolean`, define an explicit null policy: you can use `Boolean.TRUE.equals(nullableFlag(s))` so that only `true` passes. This approach does not automatically catch other exceptions that the method call itself might throw.

Distinction to keep clear:

- A `null` selector does not match `case String s`, so that pattern's guard is not called.
- A non-null `String` selector whose guard returns `Boolean null` can cause a `NullPointerException` during guard evaluation.

## 9. Java 21 Blocks Some Direct Mutations in Guards, but Not All Side Effects

An easily overlooked detail in JLS `14.11.1: a local variable, formal parameter, or exception parameter **used but not declared in a guard** must be `final` or *effectively final*. This means you cannot arbitrarily increment/decrement a local variable and use it inside a guard.

The following example **intentionally fails to compile**:

~~~java
static String invalid(Object value) {
    int attempts = 0;
    return switch (value) {
        case String s when ++attempts > 0 -> "YES";
        default -> "NO";
    };
}
~~~

`javac --release 21` reports:

~~~text
error: local variables referenced from a guard must be final or effectively final
~~~

Because `++attempts` mutates the local variable `attempts`, it violates the *effectively final* rule.

**However, this is not a guarantee that guards are side-effect-free:**

- You can hold a reference to a mutable object in a `final` variable and call methods that mutate its contents. For example, `AtomicInteger.incrementAndGet()` in `GuardTraceDemo` is still valid.
- You can mutate fields of the object referenced by a pattern variable, such as `--t.credits` in `GuardMutationDemo`.
- You can perform I/O, call logging methods, or invoke external APIs directly inside a guard.
- You can read state that changes over time; even without writing anything, the result is not necessarily stable.

**Reference immutability** is different from **object immutability**. `final AtomicInteger counter` prevents reassigning the `counter` variable to another object, not calling `counter.incrementAndGet()`.

Another restriction checked by Java: a guard cannot be a **constant expression** with value `false`. `case String s when false -> ...` causes a compile-time error. Do not confuse this rule with a guard returning `false` at runtime, which is completely valid and happens all the time.

## 10. Designing Pure, Predictable, and Testable Guards

A predicate that only checks a condition is usually the best way to write `when`. Save the complete program `GuardPureDemo.java`:

~~~java
public class GuardPureDemo {
    static boolean eligible(String s) {
        return s != null && s.length() >= 3
            && s.chars().allMatch(Character::isLetter);
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when eligible(s) -> "ACCEPT:" + s;
            case String s -> "REJECT:" + s;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("a2"));
        System.out.println(classify(""));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardPureDemo.java
java GuardPureDemo
~~~

Output:

~~~text
ACCEPT:Java
REJECT:a2
REJECT:
NULL
~~~

The `eligible` method only reads the string and returns `boolean`; it does not increment a counter, deduct credits, or write data. In this lesson, the test inputs are ASCII character strings; if a system must handle full Unicode characters outside the Basic Multilingual Plane, consider `codePoints()` instead of `chars()` when checking for “letters”.

This style brings several benefits:

1. **Clear intent:** a reader seeing `when eligible(s)` understands it is a check, not an action.
2. **Easy to test:** `eligible` can be tested independently across passing/failing cases.
3. **Easy to maintain:** adding a fallback `case String s` branch does not mutate data simply because an earlier guard returned false.
4. **Easy to instrument:** if logging or metrics are needed, place them where responsibility boundaries are clear—such as an outer coordinator or the selected branch—rather than hiding them in a predicate.
5. **Clear null handling:** `case String s` does not match null; `case null` is handled explicitly instead of relying on the guard to shoulder every kind of input.

A predicate can still depend on mutable data without writing to it; in a multithreaded environment, you must ensure consistent reads and an appropriate data lifecycle. “Side-effect-free” **does not mean** “automatically thread-safe” or “results remain immutable forever”.

## 11. Risks Around Case Ordering and Check Timing

Some guard outcomes only hold in a specific context because case order determines **which guards get called**.

~~~java
switch (value) {
    case String s when checkA(s) -> actionA();
    case String s when checkB(s) -> actionB();
    case String s -> fallback();
    default -> other();
}
~~~

This is an **illustrative** snippet in a switch statement with user-defined functions. If `checkA(s)` returns `true`, `checkB(s)` is not called. If `checkA(s)` returns `false` after already updating state, `checkB(s)` may observe the **post-mutation state**, no longer the initial state.

Dangerous example: `checkA` deducts a quota and returns `false`, while `checkB` decides another action based on the remaining quota. Merely swapping the order of the two cases can change the business outcome. A change that looks like “refactoring classification rules” can introduce hard-to-spot state bugs.

**Dominance** also applies: an unguarded `case String s -> ...` placed before `case String s when ...` dominates the later case and is rejected by the compiler. However, Java cannot reason about all complex intersections across multiple guards; the programmer must manage the meaning of condition ordering.

When handling multiple cases, you should:

- Place specific conditions before general labels and keep mutations out of conditions.
- Include a fallback case of the same type to handle when guards are false.
- Use predicate names that suggest **checking**, such as `isEligible`, `hasEnoughCredit`, `isValidPeriod`.
- If classification logic becomes too complex, move it into a standalone function returning a value that describes the state, then switch on that state.
- Never assume a guard will be called only once in a business operation's lifetime: the same switch may be invoked multiple times due to retries, event redelivery, loops, or other requests.

## 12. External Side Effects: Retries, Transactions, and Concurrency

In a server application, guard side effects can go far beyond an in-memory counter.

**Retries and idempotency.** If a request is retried after a timeout or a job is redelivered, the switch may also be executed again. If a guard sends an email, places an order, or writes to a database, the action can happen **multiple times**. Separate command execution from conditions; for actions that can be retried, consider an *idempotency key* and appropriate deduplication mechanisms.

**Transactions.** Java evaluating a guard does not open, commit, or roll back a transaction. If a guard mutates data and then returns false, the side effects that already occurred do not vanish on their own. If an application-managed transaction is active, commit/rollback rules are decided by the transaction manager and application code, **not** by a guard's true/false result.

**Concurrency.** If a guard reads a balance or shared state and only the selected branch performs the update, another thread can change the state between those two steps. `AtomicInteger` makes an individual operation atomic, but the “read/check → write update” pair is not automatically atomic. You may need locks, compare-and-set, optimistic locking, or transactions depending on the data.

**Observability.** Logs, audits, and metrics are also side effects. A counter incremented in a guard usually represents **the number of condition evaluations**, not **the number of successful actions**. Name metrics accurately, or update the “success” metric in the success branch. If a guard intentionally has side effects for timing/call-count measurement, tests must verify both the counts and the results.

**Security.** Do not use a guard to perform sensitive actions such as granting permissions, charging money, or issuing tokens before the entire request is validated. A guard may reject the branch while the sensitive effect has already taken place. Authorization should be a pure check, while actions are protected and executed within a consistent boundary.

## 13. Short-Circuiting in Guards Makes Side Effects Harder to Predict

A guard can combine `&&`, `||`, or other conditional operators. Java uses short-circuit evaluation:

~~~java
case String s when !s.isEmpty() && expensiveCheck(s) -> "MATCH";
~~~

If `s.isEmpty()` is true, `expensiveCheck(s)` is not called. If non-empty, the right-hand method runs. This is useful for avoiding unnecessary work; however, if `expensiveCheck` has side effects, **the number of times it is called depends on the input value and operand order**.

With `||`:

~~~java
case String s when s.isEmpty() || expensiveCheck(s) -> "MATCH";
~~~

If `s.isEmpty()` is true, the right-hand side does not run. Reordering conditions can change how many times a side-effecting method is called, even when the Boolean result stays the same in some cases.

These examples are **snippets** requiring a `expensiveCheck(String)` method returning `boolean`, not standalone programs. Ensure that state-checking methods like `expensiveCheck` do not arbitrarily mutate data.

A pure guard with short-circuiting usually makes code safer:

~~~java
case String s when !s.isEmpty() && s.charAt(0) == 'A' -> "A";
~~~

Here `charAt(0)` does not run on an empty string, so there is no index-out-of-bounds error. The condition only inspects data without modifying the string. Still, a guard can throw an exception if an inner method violates a precondition; short-circuiting only protects paths that are written correctly.

## 14. Compile-Time Errors vs. Runtime Risks

Not every dangerous guard is rejected by the compiler. The following examples distinguish **valid Java rules** from **business safety**.

### 14.1. Incrementing a Local Variable Outside the Guard

~~~java
static String invalid(Object value) {
    int attempts = 0;
    return switch (value) {
        case String s when ++attempts > 0 -> "YES";
        default -> "NO";
    };
}
~~~

**Intentionally fails to compile:** `attempts` is no longer effectively final; `javac --release 21` rejects it because local variables referenced from a guard must be final or effectively final.

### 14.2. Constant `false` Guard

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s when false -> "NEVER";
        default -> "OTHER";
    };
}
~~~

**Intentionally fails to compile:** Java 21's JLS forbids a guard from being a constant expression equal to `false`; the compiler reports `this case label has a guard that is a constant expression with value 'false'`. This differs from a predicate returning `false` at runtime.

### 14.3. Non-Boolean Guard Condition

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s when s.length() -> "YES";
        default -> "NO";
    };
}
~~~

**Intentionally fails to compile:** `s.length()` returns `int`, not `boolean` or `Boolean`. The fix is `s.length() > 0`.

### 14.4. Guard Shadowed by an Earlier Broad Label

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s -> "ALL_STRINGS";
        case String s when s.isBlank() -> "BLANK";
        default -> "OTHER";
    };
}
~~~

**Intentionally fails to compile:** the first `String s` case already catches every `String` object, so the guarded label after it is dominated. Swap the order of the two cases.

### 14.5. Code That Compiles but Still Has Unwanted Side Effects

~~~java
case Ticket t when consumeEvenOnFailure(t) -> "APPROVED";
~~~

**Compiles** if `Ticket` and `consumeEvenOnFailure` are defined accordingly, as in `GuardMutationDemo` in Section 5. The compiler does not guarantee that this is a pure check. If the guard returns false, it may still have mutated `t.credits`.

**Conclusion:** the compiler checks syntax, type compatibility, final/effectively final rules, dominance, and exhaustiveness; it **does not** verify idempotency, automatically roll back mutations, or guarantee transactions for business logic.

## 15. Testing Strategies for Risky Guards

Checking only the switch return value is insufficient if a guard performs actions. A good test should inspect both the **result** and the **post-execution state/effects**.

| Scenario | What to verify |
| --- | --- |
| Pattern does not match | Guard is not called; side effects in the guard do not occur |
| Pattern matches, guard is true | Appropriate branch is selected; verify guard invocation count |
| Pattern matches, guard is false | Falls through to fallback label; verify no unwanted mutation occurred |
| Multiple guarded cases of the same type | Evaluation order is correct, and method call counts are controlled |
| Guard throws an exception | Exception propagates to the proper handling boundary; fallback does not accidentally run |
| Guard returns `Boolean null` | Check null policy to avoid unboxing NPE |
| Repeating the same operation | No unexpected duplicate charges or duplicate requests |
| Multiple threads sharing state | Concurrency/transactional rules are tested independently |

Three key checks visible directly from the program outputs:

1. `GuardTraceDemo` proves that 3 calls to `classify` with strings produce **5 guard invocations**, even though only 2 guarded branches are selected.
2. `GuardMutationDemo` proves that a failed attempt still reduces `credits` to **-1**.
3. `GuardActionSeparationDemo` proves that a single-threaded rejection keeps `credits` at **0**.

When writing real JUnit tests, you can use spies/mocks to count dependency calls, but you should also verify the actual state of objects. Do not treat mock interactions as proof of atomicity in a concurrent environment.

## 16. Exercises and Solutions

### Exercise 1 — Does a `false` Guard Have Side Effects?

Consider:

~~~java
case String s when metrics.incrementAndGet() > 10 -> "HIGH";
case String s -> "LOW";
~~~

Suppose `metrics` is a valid `AtomicInteger` with an initial value of 9. What does a single switch with selector `"abc"` return, and what is the counter's value?

**Solution:** The guard increments the counter to 10, the condition `10 > 10` is false, and the switch selects `LOW`. The counter **remains 10**. A false guard does not roll back side effects.

### Exercise 2 — Guard Throwing an Exception

With the guard `Integer.parseInt(s) > 0` and a subsequent label `case String s -> "OTHER"`, what happens if the selector is `"abc"`?

**Solution:** `parseInt` throws `NumberFormatException`; the switch terminates abruptly. Java **does not** automatically jump to `"OTHER"`. To treat parse errors as non-matches, you need checking/parsing logic with an appropriate exception policy.

### Exercise 3 — Distinguishing `final` and Immutable

Why does using `final AtomicInteger counter` with `counter.incrementAndGet()` in a guard compile, whereas `++attempts` with a local `int attempts` outside the guard fails?

**Solution:** `final` on a reference only prevents reassigning the variable to another object; it does not prevent mutating the contents of the `AtomicInteger` object. Java 21 guards require external local variables referenced inside them to be final/effectively final; `++attempts` violates this rule.

### Exercise 4 — Improving Guard Safety

You have:

~~~java
case Order o when repository.save(o) != null -> "SAVED";
case Order o -> "REJECTED";
~~~

What is the issue, and how should it be refactored?

**Solution:** `save` is an I/O action performed during branch selection; it can mutate the database or throw an error even when the guard result does not lead to the `SAVED` branch. Let the guard only check eligibility conditions, then perform `repository.save(o)` in the selected processing flow within an appropriate transaction/retry policy. Handle errors and idempotency for the write operation instead of treating a false guard as a rollback.

`Order` and `repository` here are illustrative application components, not built-in Java Core APIs.

### Exercise 5 — Two Forms with the Same Boolean Result but Different Side Effects

~~~java
case String s when isShort(s) || auditAndCheck(s) -> "YES";
~~~

versus:

~~~java
case String s when auditAndCheck(s) || isShort(s) -> "YES";
~~~

If `isShort(s)` returns true, is `auditAndCheck` guaranteed to be called the same number of times in both cases?

**Solution:** No. In the first form, `||` short-circuits, so `auditAndCheck` does not run. In the second form, `auditAndCheck` runs first; if it has side effects, they have already occurred before `isShort` is evaluated. Thus, having side effects in a guard makes operand order matter beyond just the Boolean result.

### Exercise 6 — Concurrency

Two threads concurrently process a `Ticket` with `credits = 1`. Each thread checks the guard `t.credits > 0` and deducts a credit in the selected branch. Is it guaranteed that only one thread succeeds?

**Solution:** No. Without synchronization, both threads can observe `credits > 0` before either thread updates the state. Moving the mutation out of the guard makes the code transparent, but **does not** guarantee atomicity. You need an atomic check-and-update operation or an appropriate transaction/lock.

## 17. Review Checklist and Takeaways

When reviewing a `case Pattern p when predicate(p)`, ask:

1. Does the guard genuinely only check a condition, or is it calling an API that creates side effects?
2. Can the guard return false **after already mutating state**?
3. Can the guard expression throw an exception or return `Boolean null`?
4. If the pattern does not match, is the guard skipped as expected?
5. Could the ordering of guarded cases cause a side effect to occur multiple times or out of order?
6. Do local variables outside the guard satisfy Java 21's final/effectively final rule?
7. Do metrics count **condition evaluations** or **successful branches**? Are they named accurately?
8. If the operation retries or runs across multiple threads, is the action appropriately idempotent and atomic/transactional?
9. Have business side effects been moved to explicit processing code with proper error boundaries?
10. Do tests verify both results and state changes, exceptions, and false-guard paths?

**Core principle:** `when` is a **branch-selection** tool, not a commit or rollback boundary. Prefer concise, pure-checking guards with minimal dependence on mutable state; place business actions in explicit execution paths, and use synchronization/transactions when data is shared.

### Official Documentation

- Java SE 21 JLS `14.11.1 — Switch Blocks, guard conditions, and evaluation rules: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Java SE 21 JLS `6.3.3 — Scope for Pattern Variables in case Labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
