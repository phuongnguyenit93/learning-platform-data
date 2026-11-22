# Extracting Complex Predicates into Methods When Composing Patterns (Java 21)

## Objectives

In **Pattern Composition**, an `instanceof` expression or a `switch` branch can simultaneously contain a type pattern, a nested record pattern, `&&`/`||` operators, and a `when` guard. When the boolean condition grows long, extracting it into a meaningfully named method helps readers understand the **business condition** without having to decode every individual comparison.

After this lesson, you will be able to:
- Distinguish **structural checks** using patterns from **business predicates** using booleans.
- Extract complex guards into small methods without changing the result.
- Pass pattern variables accurately into helpers from `when` or the right-hand side of `&&`.
- Preserve evaluation order, short-circuiting, `&&`/`||` precedence, `null` handling, and `switch` branch ordering.
- Choose between extracting **only the guard** and encapsulating **the entire domain condition** into a method.

**Requirements:** Java 21 or later. Record Patterns (JEP 440) and Pattern Matching for `switch` (JEP 441) have been standard features since Java 21, requiring no `--enable-preview`.

## 1. The Problem: Clear Pattern, Overly Long Guard

Suppose we have two records:

```java
record Reporter(String email, boolean verified, String team) {}
record Ticket(String id, Reporter reporter, int impact, boolean serviceDown) {}
```

The example system applies **hypothetical rules for learning purposes**, not operational standards: a ticket is routed to the `ESCALATE` flow when it simultaneously satisfies:

1. The service is down (`serviceDown == true`).
2. The impact level is from 3 to 5, inclusive of both bounds.
3. The reporter is verified.
4. The email is non-`null` and ends with `@company.test`.
5. The support team is `SRE` **or** `OPS`.

If the reporter is missing or any condition is false, a `Ticket` is still classified as `NORMAL`. A `null` selector or a non-`Ticket` is classified as `NOT_TICKET`.

The initial `switch` branch typically looks like this:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when down && impact >= 3 && impact <= 5
             && verified && email != null
             && email.endsWith("@company.test")
             && ("SRE".equals(team) || "OPS".equals(team))
        -> "ESCALATE:" + id;
```

This is a **branch of a `switch`**, not a standalone program. The pattern expresses the `Ticket → Reporter` relationship, but the guard forces the caller to know details about impact levels, the email domain, and the team list. If the rule is repeated across multiple branches or services, policy changes could cause places to diverge.

**Refactoring goal:** keep the pattern to recognize the type and extract data, but move the business meaning to a named method:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

This keeps the `id` variable for the result and shifts the complexity from the guard into a helper that can be tested independently.

## 2. Distinguishing Patterns and Predicates

| Component | Responsibility | Example |
|---|---|---|
| Type pattern | Recognizes the type and binds a variable | `case Ticket ticket` |
| Record pattern | Checks the record and deconstructs components | `Ticket(var id, ...)` |
| Nested record pattern | Requires the nested record to exist for deconstruction | `Reporter(var email, ...)` |
| `when` guard | Additional check after the pattern has matched | `when impact >= 3 && verified` |
| Boolean helper | Names a logical/business condition | `meetsEscalationRule(...)` |

**Important boundary:** `Reporter(...)` is a record pattern, so it does not match if `Ticket.reporter() == null`. However, `Reporter(var email, ...)` can bind `email == null` because reference-type leaf components are allowed to be null. Extracting a predicate must not lose either of these behaviors.

A `boolean` method only returns true/false. It does not create pattern variables for the caller, does not change which record type the `switch` matches, and does not act as a new record pattern.

## 3. Extracting the Guard into Named Questions

Split the rule into three methods:

```java
static boolean isWorkEmail(String email) {
    return email != null && email.endsWith("@company.test");
}

static boolean isResponseTeam(String team) {
    return "SRE".equals(team) || "OPS".equals(team);
}

static boolean meetsEscalationRule(boolean down, int impact,
        boolean verified, String email, String team) {
    return down && impact >= 3 && impact <= 5
            && verified && isWorkEmail(email)
            && isResponseTeam(team);
}
```

This is an **illustrative snippet**; the complete runnable code is in section 5.

- `meetsEscalationRule` expresses the escalation decision.
- `isWorkEmail` keeps the `null` check before calling `endsWith`.
- `isResponseTeam` groups the two SRE/OPS options with `||`, avoiding parenthesization mistakes at the caller.
- All helpers are **pure**: no state mutation, no I/O, and no reading of the current time, making them easy to test and less prone to unintended changes.

Not every comparison needs a helper. A simple condition that appears only once and has no distinct meaning can stay inline; extract groups of conditions where a method name makes the intent clearer than the raw expression.

## 4. Safe Refactoring Steps

### Step 1 — Lock down behavior before editing

Record the expected outcomes:

| Input | Result |
|---|---|
| `null` selector or wrong type | `NOT_TICKET` |
| Ticket missing reporter | `NORMAL:<id>` |
| Reporter present but guard fails | `NORMAL:<id>` |
| Reporter exists and all conditions pass | `ESCALATE:<id>` |

This list helps verify equivalence between before and after; do not change the policy during the same refactoring pass.

### Step 2 — Keep the pattern, replace only the guard

Keep `Ticket(var id, Reporter(...), ...)` and the fallback branch unchanged. Move the part after `when` into `meetsEscalationRule(down, impact, verified, email, team)`. This is a small step that avoids changing structure and business logic at the same time.

### Step 3 — Preserve grouping parentheses and operator precedence

Correct condition:

```java
down && verified && ("SRE".equals(team) || "OPS".equals(team))
```

If you accidentally write:

```java
down && verified && "SRE".equals(team) || "OPS".equals(team)
```

then because `&&` has higher precedence than `||`, the expression is equivalent to:

```java
(down && verified && "SRE".equals(team)) || "OPS".equals(team)
```

When `team == "OPS"`, a false condition can become true even if `down == false` or `verified == false`. The `isResponseTeam` helper clarifies the OR group and reduces the chance of altering the meaning.

### Step 4 — Preserve short-circuiting and the null contract

`&&` evaluates from left to right and stops when it encounters `false`:

```java
email != null && email.endsWith("@company.test")
```

This condition is safe; whereas `email.endsWith("@company.test") && email != null` can throw a `NullPointerException`. Do not move a call that has side effects or can throw an exception to a new position without checking the impact on evaluation order. Similarly, `"SRE".equals(team)` is null-safe, while `team.equals("SRE")` is not.

### Step 5 — Compare actual outputs

Test the boundary values 3/5, out-of-bounds 2/6, null email, null team, null reporter, null root, another type, and qualifying cases for both SRE and OPS. Do not test only a single happy path.

## 5. Complete Java 21 Example and Regression Check

Create the file **`PatternPredicateExtractionDemo.java`**:

```java
public class PatternPredicateExtractionDemo {
    record Reporter(String email, boolean verified, String team) {}
    record Ticket(String id, Reporter reporter, int impact, boolean serviceDown) {}

    // BEFORE: nested record pattern and multiple conditions in the guard.
    static String before(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket(var id, Reporter(var email, var verified, var team),
                        var impact, var down)
                    when down && impact >= 3 && impact <= 5
                         && verified && email != null
                         && email.endsWith("@company.test")
                         && ("SRE".equals(team) || "OPS".equals(team))
                    -> "ESCALATE:" + id;
            case Ticket(var id, var reporter, var impact, var down) -> "NORMAL:" + id;
            default -> "NOT_TICKET";
        };
    }

    // Named, null-safe conditions.
    static boolean isWorkEmail(String email) {
        return email != null && email.endsWith("@company.test");
    }

    static boolean isResponseTeam(String team) {
        return "SRE".equals(team) || "OPS".equals(team);
    }

    static boolean meetsEscalationRule(boolean down, int impact,
            boolean verified, String email, String team) {
        return down && impact >= 3 && impact <= 5
                && verified && isWorkEmail(email)
                && isResponseTeam(team);
    }

    // AFTER: original pattern, guard calls a named predicate.
    static String after(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket(var id, Reporter(var email, var verified, var team),
                        var impact, var down)
                    when meetsEscalationRule(down, impact, verified, email, team)
                    -> "ESCALATE:" + id;
            case Ticket(var id, var reporter, var impact, var down) -> "NORMAL:" + id;
            default -> "NOT_TICKET";
        };
    }

    // Second refactoring level: helper accepts a domain type.
    static boolean isEscalatable(Ticket ticket) {
        if (ticket == null || ticket.reporter() == null) {
            return false;
        }
        Reporter reporter = ticket.reporter();
        return meetsEscalationRule(ticket.serviceDown(), ticket.impact(),
                reporter.verified(), reporter.email(), reporter.team());
    }

    static String byDomainPredicate(Object input) {
        return switch (input) {
            case null -> "NOT_TICKET";
            case Ticket ticket when isEscalatable(ticket) -> "ESCALATE:" + ticket.id();
            case Ticket ticket -> "NORMAL:" + ticket.id();
            default -> "NOT_TICKET";
        };
    }

    // instanceof combined with &&: helper is only called after the pattern matches.
    static boolean predicateOnly(Object input) {
        return input instanceof Ticket(
                var id, Reporter(var email, var verified, var team),
                var impact, var down)
                && meetsEscalationRule(down, impact, verified, email, team);
    }

    static void check(String label, Object input) {
        String initial = before(input);
        String extracted = after(input);
        String domain = byDomainPredicate(input);
        boolean predicate = predicateOnly(input);
        if (!initial.equals(extracted)
                || !initial.equals(domain)
                || predicate != initial.startsWith("ESCALATE:")) {
            throw new AssertionError(label + ": " + initial + "/"
                    + extracted + "/" + domain + "/" + predicate);
        }
        System.out.println(label + " -> " + extracted);
    }

    public static void main(String[] args) {
        check("null root", null);
        check("wrong type", "text");
        check("SRE qualifies", new Ticket("T01",
                new Reporter("a@company.test", true, "SRE"), 3, true));
        check("OPS qualifies", new Ticket("T02",
                new Reporter("b@company.test", true, "OPS"), 5, true));
        check("not down", new Ticket("T03",
                new Reporter("a@company.test", true, "SRE"), 4, false));
        check("low impact", new Ticket("T04",
                new Reporter("a@company.test", true, "SRE"), 2, true));
        check("too high impact", new Ticket("T05",
                new Reporter("a@company.test", true, "SRE"), 6, true));
        check("unverified", new Ticket("T06",
                new Reporter("a@company.test", false, "SRE"), 4, true));
        check("null email", new Ticket("T07",
                new Reporter(null, true, "OPS"), 4, true));
        check("other email", new Ticket("T08",
                new Reporter("a@elsewhere.test", true, "OPS"), 4, true));
        check("other team", new Ticket("T09",
                new Reporter("a@company.test", true, "DEV"), 4, true));
        check("null team", new Ticket("T10",
                new Reporter("a@company.test", true, null), 4, true));
        check("missing reporter", new Ticket("T11", null, 4, true));
        check("null id", new Ticket(null,
                new Reporter("a@company.test", true, "SRE"), 4, true));
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 PatternPredicateExtractionDemo.java
java PatternPredicateExtractionDemo
```

**Stdout verified with Java:**

```text
null root -> NOT_TICKET
wrong type -> NOT_TICKET
SRE qualifies -> ESCALATE:T01
OPS qualifies -> ESCALATE:T02
not down -> NORMAL:T03
low impact -> NORMAL:T04
too high impact -> NORMAL:T05
unverified -> NORMAL:T06
null email -> NORMAL:T07
other email -> NORMAL:T08
other team -> NORMAL:T09
null team -> NORMAL:T10
missing reporter -> NORMAL:T11
null id -> ESCALATE:null
```

Each `check(...)` call compares **four results**: the string before refactoring, after refactoring, when encapsulated by domain type, and the boolean from `instanceof` combined with `&&`. Any mismatch throws an `AssertionError`. The cases above ran successfully with `javac --release 21`; this serves as evidence for the sample inputs, while production tests should also cover additional domain invariants.

The `null id` case intentionally preserves the old behavior: `var id` in a record pattern can bind null, so `"ESCALATE:" + id` produces `ESCALATE:null`. If the domain requires a mandatory ID, validate it separately instead of silently changing the rule during a refactoring.

## 6. Scope of Pattern Variables When Extracting Methods

In a `switch` branch, the `email` variable is only used after the pattern containing it matches:

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

In `instanceof` combined with `&&`, the compiler knows the variables have been bound on the left-hand side before calling the helper on the right-hand side:

```java
static boolean predicateOnly(Object input) {
    return input instanceof Ticket(
            var id, Reporter(var email, var verified, var team),
            var impact, var down)
            && meetsEscalationRule(down, impact, verified, email, team);
}
```

Thanks to short-circuiting, `meetsEscalationRule` is not called if the selector is not a `Ticket` or if `Reporter` is null. This **matches the method in the executed program**, without requiring manual casts.

**Pattern variables cannot be carried out of a boolean helper:**

```java
boolean escalated = predicateOnly(input);
// Variables 'email' and 'id' declared in predicateOnly()
// are not in scope at this caller.
```

If the caller needs `id`/`email` for display or processing, keep the pattern in the caller and extract only the guard. Alternatively, bind a `Ticket ticket` at the caller, call `isEscalatable(ticket)`, and then retrieve `ticket.id()`. When you genuinely need to return multiple values after validation, use a structured result type (a record or `Optional<Result>`) rather than expecting pattern variables to exist outside their scope.

**Syntax:** `when` belongs to the guard of a `case` in `switch`; it is not used directly after `instanceof`. With `instanceof`, use `&& predicate(...)`.

## 7. Two Refactoring Levels and How to Choose

### Level A — Keep the nested pattern, extract only the guard

```java
case Ticket(var id, Reporter(var email, var verified, var team),
            var impact, var down)
        when meetsEscalationRule(down, impact, verified, email, team)
        -> "ESCALATE:" + id;
```

This approach fits when the `switch` branch still needs the deconstructed variables, wants to show the input structure, and the guard is the main source of unreadability. The small change makes equivalence easy to verify.

### Level B — Move to a predicate accepting the domain type

```java
case Ticket ticket when isEscalatable(ticket)
        -> "ESCALATE:" + ticket.id();
```

This approach fits when multiple callers ask "does this ticket need to be escalated?". The caller does not need to know that `Reporter` contains an email or a team. The `isEscalatable(Ticket)` method must check for a null reporter, because the original nested record pattern excluded null reporters.

In larger systems, you can place the predicate on `Ticket` or in a policy/domain service depending on where the rule belongs. If it depends on changing configuration, time, a database, or the network, supply the dependency/policy explicitly rather than hiding I/O inside a `switch` predicate.

Do not dump every helper into a generic `Utils` class just for reusability; names and locations should reflect the domain.

## 8. Semantics That Must Be Preserved

### 8.1. Root null and nested null

- `case null` catches a null selector. `default` does not automatically handle a null selector in a pattern `switch`; omitting a handling branch can cause a `NullPointerException`.
- `case Ticket(var id, Reporter(...), ...)` does not match when `reporter == null`. The broader `case Ticket(var id, var reporter, ...)` branch handles it and returns `NORMAL`.
- `case Ticket ticket when isEscalatable(ticket)` matches the `Ticket` type first, and then the helper must check `ticket.reporter() == null` to preserve the same result as the old nested pattern.
- Inside a non-null `Reporter`, `email == null` or `team == null` can still occur: the helper uses `email != null` and `"SRE".equals(team)` for safety.

### 8.2. Switch branch ordering

```java
case Ticket ticket when isEscalatable(ticket) -> "ESCALATE";
case Ticket ticket -> "NORMAL";
```

The guarded branch must come before the unguarded `Ticket ticket` branch. If reversed, the broader branch covers the narrower one (**dominated case label**), and Java reports a compile error. For independent guards that could be true simultaneously, the `case` order also determines the result; do not reorder them without verification.

### 8.3. Numeric bounds and OR logic

If the original code had `impact >= 3 && impact <= 5`, the helper must keep both bounds. Changing it to `impact < 5` alters the decision for impact 5. Changing the `SRE || OPS` group to `SRE && OPS` makes it impossible for a ticket to qualify if a team has only one code. Such changes are business policy changes, not refactorings.

### 8.4. Side effects and call order

An `&&`/`||` expression evaluates only the necessary parts. Adding logging, querying a service, incrementing a counter, reading the system clock, or throwing an exception from a helper can make the program behave differently even if the boolean result is the same in normal cases. For complex data and predicates, prefer pure helpers and make external dependencies explicit.

### 8.5. Readability does not mean the maximum number of methods

If a guard is simply `when impact >= 3`, creating `isImpactAtLeastThree(...)` can make the code longer. If it contains multiple groups of conditions, is repeated, or expresses a policy with its own domain name, extraction is usually far more valuable. Extract along meaning and responsibility boundaries.

## 9. Codebase Application Checklist

| Check | Must ensure |
|---|---|
| Pattern structure | Preserve record types, component order, and nested null-matching |
| Scope | Every pattern variable is used only where Java knows the pattern matched |
| Guard | Helper receives the exact bound variables and returns an equivalent result |
| Operators | Preserve grouping parentheses, `&&`/`||` precedence, and short-circuiting |
| Nulls | Root, nested record, and leaf components produce equivalent results |
| Bounds | Keep `>=`, `<=`, and the exact value sets |
| Switch | Keep guarded branches before general branches, and handle `case null` |
| Side effects | Do not add side effects or exceptions beyond the original contract |
| Testing | Compare before/after with passing, failing, and boundary inputs |

In real projects, JUnit parameterized tests can be used to pass many ticket configurations and verify outputs. There is no need to test every helper just to mirror the implementation; prioritize boundary cases and observable logic changes.

## 10. Common Mistakes and How to Fix Them

- **Vague helper names like `checkEverything`:** harder to understand than the original expression. Choose a business-aligned name, such as `meetsEscalationRule`.
- **Writing `input instanceof Ticket(...) when ...`:** invalid syntax. Use `instanceof Pattern && predicate(...)`.
- **Dropping parentheses around OR conditions:** can cause the OPS branch to bypass the `down`/`verified` checks.
- **Using pattern variables after a boolean method returns:** those variables exist only within the method's scope and are not exported.
- **Changing the order of null checks and method calls:** can introduce a `NullPointerException` that did not exist in the old code.
- **Placing `case Ticket ticket` before a guarded branch:** causes the specific branch to be dominated.
- **Removing the `NORMAL` fallback:** tickets of a valid type that do not meet the condition will be handled differently.
- **Assuming a record pattern guarantees all components are non-null:** the record at each level must exist, but reference-type components can still be null.
- **Moving conditions with side effects arbitrarily:** changes evaluation counts or order; keep predicates pure.
- **Mixing policy changes with refactoring:** makes it hard to tell whether a result mismatch is a bug or a new requirement; separate them into distinct changes.

## 11. Self-Check Questions

1. If `Reporter` is `null`, does `Ticket(..., Reporter(...), ...)` match? **No.** The nested record pattern excludes this case before the guard.
2. If `email == null` but the reporter is non-null, can the pattern match? **Yes, it can match.** `var email` receives null; the email helper will return `false`.
3. Why does `isResponseTeam` return `"SRE".equals(team) || "OPS".equals(team)`? **Because it is a unified OR group**, used alongside higher-level AND conditions.
4. If `predicateOnly(input)` returns `true`, can the caller use the `id` variable inside it? **No.** Returning a boolean does not transfer the scope of a pattern variable.
5. How do you attach a predicate to `instanceof`? **Use `&&`** after the pattern: `input instanceof Ticket(...) && meetsEscalationRule(...)`.
6. Why must `case Ticket ticket when isEscalatable(ticket)` come before `case Ticket ticket`? **The unguarded branch dominates the guarded branch** if placed first.
7. If a helper changes `impact <= 5` to `impact < 5`, is it still a behavior-preserving refactoring? **No.** A ticket with impact 5 changes from ESCALATE to NORMAL.

## Key Takeaways

**Patterns recognize and deconstruct structure; named predicates express business conditions.** When combining nested patterns and multiple operators, you can extract the guard into a boolean helper, and then consider moving the decision to a domain method if multiple callers need it. To refactor safely in Java 21, preserve variable scope, short-circuiting, `&&`/`||` grouping, null handling, `switch` branch order, and verify outputs for boundary cases.

## Official Documentation

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 — §15.23 Conditional-And Operator &&](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.23)
- [JLS SE 21 — §15.24 Conditional-Or Operator ||](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.24)
