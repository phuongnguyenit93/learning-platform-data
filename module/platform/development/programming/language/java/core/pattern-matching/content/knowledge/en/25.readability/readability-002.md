# Limiting the Number of Patterns in a Method: Optimizing Java Pattern Matching Readability

## 1. There Is No Universal “Maximum Number” for Every Method

When using Java Pattern Matching, a method can contain multiple `case Type x` branches, record patterns, nested record patterns, and `when` guards. **The Java specification does not set a rule that a method may only have 3, 5, or 10 patterns.** The compiler checks the validity of each pattern, the selector type, the exhaustiveness of `switch`, branch dominance order (*domination*), and syntax—it does **not** evaluate readability based on a fixed number.

Therefore, a more useful question than “what is the maximum number of patterns?” is:

> Can the reader quickly understand **what this method decides**, how the branches are prioritized, what each branch does, and whether all edge cases have been handled?

**Pattern count** is an easily observable signal, but it does not adequately reflect complexity:

- Five short branches classifying a single simple property can be easier to understand than three branches with deeply nested record patterns and multiple method calls in guards.
- A `switch` expression mapping multiple type variants to simple labels might be best kept in a single method.
- A method with only a few patterns where each branch updates the database, sends messages, and mutates state can be much harder to understand.

**Core principle:** Limit based on **cognitive load and business responsibility**, not an arbitrary pattern count. If a team wants a warning threshold in code reviews, state clearly that it is a **project convention**, not a Java/JVM limit or a rule recommended by a JEP.

**Versions:** Pattern matching for `instanceof` has been standard since Java 16; record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been standard since **Java 21**. The complete examples below use Java 21+ and do not require `--enable-preview`.

## 2. Four Factors to Evaluate Before Splitting a Method

### 2.1. Number of Branches and Number of Decisions

A pattern usually represents a matching possibility; however, **the number of branches does not necessarily equal the number of business decisions**. For example:

```java
return switch (event) {
    case Login(var user, var success) -> ...;
    case Purchase(var buyer, var amount) -> ...;
    case Refund(var buyer, var amount) -> ...;
    case Alert(var message, var severity) -> ...;
    case null -> ...;
};
```

This method branches by **event type**, which is easy to read if each body simply calls an appropriate helper. If each branch instead contains multiple pricing conditions, permission checks, tax calculations, and error handling, then a single method is taking on too many responsibilities.

Consider **fan-out**: how many groups of behavior must a method distinguish? Do the groups share the same goal and result type? Would adding a new variant require modifying many unrelated branches?

### 2.2. Depth of Record Patterns

A record pattern can deconstruct multiple levels:

```java
record Address(String city) {}
record Customer(Address address) {}
record Sale(Customer buyer, int total) {}

// Example illustrating a case in a switch:
case Sale(Customer(Address(String city)), int total)
        when total >= 100 -> "high sale in " + city;
```

This pattern is short, but the reader must simultaneously track `Sale` → `Customer` → `Address` → `String`, the amount condition, and the null rules for nested records. If the branch body is also long, the cost of reading and debugging increases quickly.

You can switch to shallower extraction:

```java
// Illustration continuing from the records above:
case Sale(var buyer, int total) ->
        describeSale(buyer, total);
```

The `describeSale` method will be responsible for inspecting the internal structure if needed. **Do not automatically split every nested record pattern**: for simple rules, explicit components can still be the clearest choice. Only split when it reduces the depth the reader must keep in mind, introduces a clear domain name, or enables independent testing.

### 2.3. Guard Complexity and Precedence

A `when` clause adds a Boolean decision to a branch:

```java
case Purchase(var buyer, int amount) when amount >= 100 ->
        "large";
case Purchase(var buyer, int amount) when amount > 0 ->
        "normal";
case Purchase(var buyer, int amount) ->
        "invalid";
```

Simple guards with a clear order are reasonable. However, if the reader must parse multiple conditions with `&&`/`||`, call methods with unknown side effects, or reason about overlapping relationships between guards, consider moving the `Purchase` group logic into a helper with a business name.

**Important:** Extracting a helper must not accidentally change guard precedence. A branch with a more specific guard must be tried before an unguarded branch covering the same type. When multiple guards evaluate to true, the selected branch depends on the order in the `switch`.

### 2.4. Branch Bodies and Side Effects

A `switch` that performs pure data mapping is usually easier to read than a `switch` that mixes routing and business operations. For example:

```java
// Illustrates routing with side effects; the methods here are hypothetical.
switch (event) {
    case Purchase p -> processPurchase(p);
    case Refund r -> processRefund(r);
    case null -> handleMissing();
    default -> handleOther(event);
}
```

If each action involves saving data, retrying, or publishing events, the reader should see the **action name** in the switch, while the details live in the corresponding responsible methods. Do not move side effects into guards just to keep the body shorter: a guard may execute even if that branch is ultimately not selected.

## 3. Complete Java Example: From a Pattern-Heavy Switch to Clean Dispatching

Hypothetical problem: a system has four event types in a **sealed hierarchy** and needs to return a classification label. The initial `before` version contains many pattern labels to handle both the event type and internal rules at once. The `after` version keeps a switch dispatching across the **four domain types**, while detailed rules live in helpers.

The example intentionally keeps every function **pure**, with no I/O and no external data mutation, so behavior can be compared clearly.

Save as **`PatternCountReadabilityDemo.java`**:

```java
public class PatternCountReadabilityDemo {
    sealed interface Event permits Login, Purchase, Refund, Alert {}

    record Login(String user, boolean success) implements Event {}
    record Purchase(String buyer, int amount) implements Event {}
    record Refund(String buyer, int amount) implements Event {}
    record Alert(String message, int severity) implements Event {}

    static String label(String raw) {
        return raw == null ? "(unknown)" : raw;
    }

    // Before: a switch containing many patterns + guards from
    // different business groups.
    static String before(Event event) {
        return switch (event) {
            case Login(String user, boolean success) when success ->
                    "LOGIN_OK:" + label(user);
            case Login(String user, boolean success) ->
                    "LOGIN_FAIL:" + label(user);

            case Purchase(String buyer, int amount) when amount >= 100 ->
                    "PURCHASE_HIGH:" + label(buyer) + ":" + amount;
            case Purchase(String buyer, int amount) when amount > 0 ->
                    "PURCHASE:" + label(buyer) + ":" + amount;
            case Purchase(String buyer, int amount) ->
                    "PURCHASE_INVALID";

            case Refund(String buyer, int amount) when amount > 0 ->
                    "REFUND:" + label(buyer) + ":" + amount;
            case Refund(String buyer, int amount) ->
                    "REFUND_INVALID";

            case Alert(String message, int severity) when severity >= 3 ->
                    "ALERT_HIGH:" + label(message);
            case Alert(String message, int severity) ->
                    "ALERT:" + label(message);

            case null -> "UNKNOWN";
        };
    }

    // After: a switch dispatching by event type.
    // Each helper handles the internal rules of one group.
    static String after(Event event) {
        return switch (event) {
            case Login(var user, var success) ->
                    describeLogin(user, success);
            case Purchase(var buyer, var amount) ->
                    describePurchase(buyer, amount);
            case Refund(var buyer, var amount) ->
                    describeRefund(buyer, amount);
            case Alert(var message, var severity) ->
                    describeAlert(message, severity);
            case null -> "UNKNOWN";
        };
    }

    static String describeLogin(String user, boolean success) {
        return (success ? "LOGIN_OK:" : "LOGIN_FAIL:") + label(user);
    }

    static String describePurchase(String buyer, int amount) {
        if (amount >= 100) {
            return "PURCHASE_HIGH:" + label(buyer) + ":" + amount;
        }
        if (amount > 0) {
            return "PURCHASE:" + label(buyer) + ":" + amount;
        }
        return "PURCHASE_INVALID";
    }

    static String describeRefund(String buyer, int amount) {
        return amount > 0
                ? "REFUND:" + label(buyer) + ":" + amount
                : "REFUND_INVALID";
    }

    static String describeAlert(String message, int severity) {
        return (severity >= 3 ? "ALERT_HIGH:" : "ALERT:") + label(message);
    }

    public static void main(String[] args) {
        Event[] samples = {
                new Login("Ada", true),
                new Login("Ada", false),
                new Login(null, true),
                new Purchase("Mai", 100),
                new Purchase("Mai", 5),
                new Purchase("Mai", 0),
                new Refund("Mai", 5),
                new Refund("Mai", -1),
                new Alert("disk", 3),
                new Alert("disk", 1),
                null
        };

        for (Event event : samples) {
            String original = before(event);
            String refactored = after(event);

            if (!original.equals(refactored)) {
                throw new AssertionError(
                        original + " != " + refactored);
            }
            System.out.println(refactored);
        }
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 PatternCountReadabilityDemo.java
java PatternCountReadabilityDemo
```

**Exact stdout:**

```text
LOGIN_OK:Ada
LOGIN_FAIL:Ada
LOGIN_OK:(unknown)
PURCHASE_HIGH:Mai:100
PURCHASE:Mai:5
PURCHASE_INVALID
REFUND:Mai:5
REFUND_INVALID
ALERT_HIGH:disk
ALERT:disk
UNKNOWN
```

### Why Is the `after` Version Easier to Read in This Scenario?

- **Clear high-level question:** Does this event belong to `Login`, `Purchase`, `Refund`, or `Alert`?
- **Each group has a named handler:** `describePurchase` focuses on the policy for `amount`, instead of forcing everyone to track `Purchase` conditions inside one long switch.
- **Reduces pattern shape duplication:** No need to write `case Purchase(String buyer, int amount)` three times.
- **Preserves exhaustiveness:** `Event` is a sealed interface permitting only four record implementations. The branches cover all four types plus `case null`, so no `default` is needed. Adding a new permitted subtype without adding a matching branch can cause the compiler to require updating the switch.
- **Preserves the contract:** Both `before` and `after` use the same thresholds `amount >= 100` and `amount > 0`, handle a `null` selector as `UNKNOWN`, and handle a null buyer/user name via `label`.
- **Includes a comparison test:** `main` computes both results for 11 inputs and throws `AssertionError` if they differ.

The `after` version is **not “better because it has exactly four patterns”**. It is better here because the main switch only **dispatches a single decision**, while domain-named helpers hold the sub-decisions. If each helper only had a single trivial statement and did not aid understanding through its name, over-splitting could make the code harder to trace.

The example only checks 11 cases and does not prove absolute equivalence for all inputs. When refactoring real production code, write boundary and integration tests appropriate for the domain.

## 4. Criteria for Recognizing When a Method Has Too Many Patterns

You do not need to hit a specific count before splitting. Look for **practical signs**:

1. **You cannot summarize the method's purpose in one sentence.** For example, the method classifies requests, calculates fees, calls APIs, and updates state all at once.
2. **One domain group appears across many guarded cases.** For instance, `Purchase` has multiple interacting branches; understanding one branch forces you to jump back and forth to the others.
3. **Pattern ordering acts as hidden logic.** Parent/child type patterns, null, and overlapping guards force the reader to mentally simulate the entire evaluation order.
4. **Deeply nested record patterns make variable tracking difficult.** The reader has to memorize a chain of components and types to understand the final action.
5. **Multiple branches are identical except for a few constants or formats.** They can be grouped by domain logic or a helper instead of duplicating code.
6. **Testing one rule forces you to set up many unrelated data types.** Splitting by group can create direct testing points.
7. **A small change requires editing multiple areas in the same switch.** This is a sign that responsibilities are not properly separated.
8. **There are many side effects, exception handlers, or shared state.** It becomes hard to deduce which branch has an impact and under what conditions.
9. **Code reviews focus on counting cases instead of understanding the contract.** A large number of branches may not be a problem if they still form a clear classification table.
10. **The method performs multiple sequential processing steps interleaved with matching.** Separate the processing flow from the strategy selection step.

A **team threshold** such as “consider extracting helpers once a switch exceeds a certain number of pattern groups” should only serve as a prompt for discussion during review. Never treat a hard number as the sole reason to refactor code or claim that the compiler limits the number of patterns.

## 5. Appropriate Ways to Reduce Complexity

### 5.1. Keep the Dispatching Switch, Extract Domain Helpers

This is the least intrusive solution when the `switch` mainly selects a **business group**, like `after` in the sample program.

```java
// Illustrates the idea; types/handlers depend on the application.
return switch (event) {
    case Login login -> describeLogin(login.user(), login.success());
    case Purchase purchase ->
            describePurchase(purchase.buyer(), purchase.amount());
    case Refund refund ->
            describeRefund(refund.buyer(), refund.amount());
    case Alert alert ->
            describeAlert(alert.message(), alert.severity());
    case null -> "UNKNOWN";
};
```

In this snippet, the pattern binds an object variable `Login login` rather than deconstructing with a record pattern. Both approaches are valid. When a method only dispatches, keeping the record intact can avoid overly long component lists. The choice depends on the helper signature and domain readability.

### 5.2. Move Complex Guards into Named Predicates

For example:

```java
static boolean isHighValue(Purchase purchase) {
    return purchase.amount() >= 100;
}

// In a switch on Event:
case Purchase p when isHighValue(p) ->
        describePurchase(p.buyer(), p.amount());
```

A named condition is easier to understand than a long Boolean expression. However, **there is no need to keep the guard in the switch if the rules specific to `Purchase` have already been moved entirely into the helper**. Duplicating classification in both the switch and the helper makes the code harder to read.

A predicate used in a guard should produce a stable result and not mutate state. A guard may be evaluated when a pattern matches even if that branch is not ultimately selected.

### 5.3. Use Polymorphism When Behavior Truly Belongs to the Type

If the event variants are designed and owned within the same module, placing behavior in the corresponding classes/records can be appropriate:

```java
// Design idea, not a standalone runnable program:
interface RenderableEvent {
    String description();
}
```

Then calling `event.description()` can replace a multi-branch switch. However, **do not force polymorphism at all costs**: if there are many independent ways to classify events (logging, UI, persistence, reporting), putting all of them into the domain model can bloat the data types and mix responsibilities. With a sealed hierarchy and a centralized classification operation, an explicit exhaustive switch may be the better choice.

### 5.4. Switch to a Data Structure When It Is Just a Simple Mapping

If you are only mapping a fixed `enum`/key to a display name or metadata, a `Map` or configuration table can be easier to maintain than many `case` branches. However, do not replace record patterns that have distinct checking logic with a `Map<Class<?>, Handler>` just to reduce the pattern count: that approach can lose exhaustiveness, struggle with inheritance hierarchies, and turn compile-time errors into runtime errors.

### 5.5. Avoid Pointless Per-Branch Extraction

Anti-pattern:

```java
return switch (value) {
    case String s -> returnString(s);
    case Integer n -> returnInteger(n);
    case null -> returnNull();
    default -> returnOther();
};
```

If the four helpers merely return a literal or a trivial expression, jumping between files/methods can take more effort than reading the code directly. Only extract when the helper name explains **meaning**, the logic is substantial enough, it has a distinct responsibility, or it needs to be tested/changed independently.

## 6. Never Sacrifice Correctness to Reduce Patterns

### 6.1. Do Not Remove Special Subtype Branches

With an inheritance type hierarchy:

```java
class Document {}
class ConfidentialDocument extends Document {}
```

If the domain handles `ConfidentialDocument` specially, collapsing all branches into `case Document d` can lose behavior. Furthermore, placing `case Document d` **before** `case ConfidentialDocument c` makes the latter branch dominated, and the compiler may report an error.

“Reducing pattern count” is not a valid reason to delete a rule that callers rely on.

### 6.2. Do Not Change Null Handling

`instanceof` with a null selector always returns `false`; in a Java 21 pattern switch, a null selector has its own behavior. If you want to preserve a default value like in the sample program, use `case null -> "UNKNOWN"` explicitly. `default` does not always handle null the way the `else` branch of an old `if` chain did.

A null record component is different from a null selector. For example, `new Login(null, true)` is a type-valid `Login` and is handled via `label(null)`; refactored code must not arbitrarily turn it into an error if the old contract accepted that data.

### 6.3. Be Careful with Sealed Hierarchy Exhaustiveness

In the sample program, `Event` is a sealed interface with four records. Omitting `default` **intentionally** helps the compiler detect changes in the set of variants when the code needs to be updated. If you always add `default -> "UNKNOWN"`, a subtype added in the future might be swallowed into the fallback instead of forcing the author to define how to handle it.

When a domain is truly dynamically extensible (plugins, interfaces with implementations outside your control), a fallback may be necessary; do not make it sealed just to shorten a switch without understanding the extension contract.

### 6.4. Preserve Guard Ordering and Thresholds

In the sample program, `amount == 100` enters `PURCHASE_HIGH` because the `>= 100` condition is evaluated before `> 0`. Changing the order or switching to `> 100` alters the boundary result. Extracting a helper is only correct when the original order and boundary values are preserved.

### 6.5. Side Effects of Branches, Guards, and Accessors

A method using multiple patterns may invoke record accessors/guards during matching. If those methods have side effects, splitting or merging patterns can change when or whether they are called. When refactoring is needed, document observed behavior and avoid assuming all pattern matching is pure. The helpers in the main example only read inputs and return strings to demonstrate a safe structural change.

## 7. How to Test When Splitting a Pattern-Heavy Method

**At a minimum**, build a matrix of **input type × state/condition × fallback/null**. For the sample program:

| Group | Cases to test |
| --- | --- |
| `Login` | `success = true`, `false`, `user = null` |
| `Purchase` | `amount = 0`, positive under 100, exactly 100, over 100, negative |
| `Refund` | positive, 0, negative |
| `Alert` | `severity` under 3, exactly 3, over 3 |
| Selector | `null` |
| Future | adding a new `Event` subtype: ensure the exhaustive switch is updated |

The example test compared the outputs of `before` and `after` across 11 inputs. In real code, add boundary inputs not covered in the demo, and if there are side effects, verify events, errors, operation counts, or interactions with key dependencies.

**Do not run the old and new functions in parallel in production just to compare them** if they can both transfer money, write to a database, or emit events: that would create duplicate side effects. Use unit tests in an isolated environment, fakes/mocks, or a controlled test environment. A simple equivalence test is useful for pure logic, but it does not prove every domain state is handled.

For large changes, refactor in multiple small PRs and verify each group. Any change in business behavior should be marked as an intentional behavior change, not called “cleanup”.

## 8. Common Mistakes When “Reducing Pattern Count”

1. **Treating a hard number as a language rule.** Java has no published limit on patterns per method as a design rule; code reviews should use understandability and testability.
2. **Merging by parent type and losing child branches.** A subclass relationship does not imply identical business handling.
3. **Over-splitting into tiny helpers.** A clean switch gets turned into meaningless jumps to trivial helpers.
4. **Hiding complex guards behind vague names.** `check1` or `valid` does not convey the domain; name it to reflect the rule.
5. **Duplicating conditions in both the switch and the helper.** Makes it hard to keep thresholds and ordering consistent.
6. **Converting code to `Map<Class<?>, Handler>` without considering inheritance.** Can change handler selection and lose compile-time checks.
7. **Unconditionally adding `default` to a sealed type.** Can mask newly added unhandled subtypes.
8. **Forgetting null selectors and nullable components.** Changes behavior even though the pattern count is lower.
9. **Changing guard order, leading to different boundary results.** Always test `<`, `==`, and `>` around thresholds.
10. **Overlooking side effects.** Counting patterns does not reflect external operations, exceptions, or transactions.
11. **Assuming every switch expression with many cases is bad.** A consistent lookup table with many short branches can be more readable than arbitrary splitting.
12. **Measuring only method length.** Fewer lines do not prove that business complexity or maintainability has improved.

## 9. Review Checklist: Should You Split the Method?

Before refactoring, ask yourself:

- [ ] Does the method have **one clear purpose** that its name accurately expresses?
- [ ] Can the patterns be **grouped by a domain type or responsibility** rather than technical details?
- [ ] Does the reader have to remember many variables/nested record levels or overlapping guards to understand one branch?
- [ ] Do the new helper names explain “why/what” rather than just repeating a single line of code?
- [ ] Do the branches preserve precedence order, `when` boundaries, null handling, and fallbacks?
- [ ] Is the exhaustiveness of the sealed hierarchy preserved, avoiding a `default` that hides missing cases?
- [ ] Do side effects, exceptions, and pattern variable scopes remain unchanged?
- [ ] Are there tests for each variant group and boundary case before/after refactoring?
- [ ] Does the result help code reviewers spot business rules faster without opening too many helpers?

**Conclusion:** **Do not limit the number of patterns by an absolute count.** Limit **the number of decisions and responsibilities that must be understood simultaneously in a single method**. When a `switch` is a clear classification table, you can keep many cases. When a method mixes multiple domain groups, complex guards, nested patterns, and side effects, split it into a readable dispatching switch with clearly named helpers—and test to prove behavior is unchanged.

### References

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11 (switch statements) and `14.30 (patterns): https://docs.oracle.com/en/java/javase/21/specs/jls/jls21.html
