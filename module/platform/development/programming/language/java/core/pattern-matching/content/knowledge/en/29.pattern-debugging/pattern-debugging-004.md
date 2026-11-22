# Analyzing Why a Pattern Does Not Match in Java 21

## Objectives

In **Debugging**, a pattern matching expression returning `false` or a `switch` branch not being selected does not mean there is a bug in the compiler or the JVM. Usually there are multiple "gates" to pass through: the selector's type must match, records at nested levels must exist, the component patterns must match, and finally the business guard must evaluate to true. Failing just one gate prevents the expected branch from executing.

This lesson walks through how to **analyze why a pattern does not match** systematically, separating **compile-time** errors from **runtime** failures, checking `null` at the right level, diagnosing `when` guards and `instanceof` expressions with `&&`, and building a test suite with independent expected results.

After this lesson, you will be able to:

- Determine whether a pattern is **not applicable at compile time**, **does not match structurally at runtime**, or **matched structurally but the guard returned false**.
- Diagnose a `null` selector, wrong type, `null` nested record, and `null` leaf component.
- Inspect `case` ordering, `when`, enum/string values, boundary conditions, and string comparison logic.
- Write a diagnostic method that isolates each condition step by step **without altering the production logic**.
- Use tests to verify the selected branch, the rejection reason, and `null` behavior.

**Version:** Java 21 or later. Type patterns for `instanceof` have been stable since Java 16 (JEP 394); record patterns (JEP 440) and pattern matching for `switch` (JEP 441) are standard features as of Java 21. Examples use `javac --release 21`, without needing `--enable-preview`.

## 1. Mental Model: Checking from the Outside In

For a complex pattern, evaluate it across four layers:

| Layer | Question | If Not Satisfied |
|---|---|---|
| **Compile time** | Is the pattern applicable to the static type of the expression, and is the `switch` branch valid? | `javac` reports an error; this is **not** a runtime no-match |
| **Root type / null** | Is the selector non-`null` and of the record/class type required by the pattern? | `instanceof` returns false; `switch` considers another matching branch or handles null |
| **Nested structure** | Is each nested record non-`null` and do the component patterns match? | The entire record pattern fails to match, even if the root has the right type |
| **Guard / extra condition** | After binding variables, does the `when` expression or the right-hand side of `&&` evaluate to true? | The pattern may have matched structurally, yet the guarded branch is still skipped |

A "no-match" gate does not automatically produce a reason message. `instanceof` only returns a `boolean`, and `switch` picks the first matching branch; to know *why*, you must build observable data or an explicit diagnostic function.

**Useful debugging rule:** proceed from the selector down through each component layer, and only then check business conditions. Do not tweak the guard when a nested record is actually `null` and the guard was never evaluated at all.

## 2. Domain Example: A Priority Ticket

Suppose we have the following records:

```java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
record Ticket(String id, Customer customer, int severity, boolean active) {}
```

This lesson uses a **hypothetical learning policy**: a Ticket is classified as `PRIORITY` when all of the following hold:

1. The root is a `Ticket` and its nested `Customer` and `Address` are non-`null`.
2. `active == true`.
3. `severity >= 3`.
4. `country` equals `"VN"` exactly.
5. `city` is non-null and equals `"HCM"` ignoring case differences.

Any `Ticket` that fails the above conditions is classified as `STANDARD:<id>`; a `null` input returns `ROOT_NULL`; a non-Ticket input returns `OTHER_TYPE`. This gives a clear contract for writing tests.

The corresponding `switch` branch:

```java
case Ticket(var id,
            Customer(var name, Address(var city, var country)),
            var severity, var active)
        when active && severity >= 3
             && "VN".equals(country)
             && city != null
             && city.equalsIgnoreCase("HCM")
        -> "PRIORITY:" + id;
```

**This is an illustrative case label**, not a complete program. There are two main reasons why it may not be selected:

- **The pattern does not match structurally:** wrong root type/null; `Customer(...)` or `Address(...)` points to null; or a corresponding component pattern does not match.
- **The pattern matched structurally, but the guard is false:** inactive Ticket, low severity, country other than VN, or city is null or not HCM.

In this version, `var id` and `var name` **do not check for non-null**. Reference-type record components can bind `null` when using `var` directly. Therefore, `id == null` or `name == null` is not necessarily the reason the pattern failed.

## 3. Root Null vs. Wrong Type: Similar Symptoms, Different Causes

With an `instanceof` expression:

```java
Object input = null;
boolean a = input instanceof Ticket ticket; // false
boolean b = input instanceof Ticket(var id, var customer,
                                    var severity, var active); // false
```

When the selector is null, `instanceof` returns false. Pattern variables are not bound, and any guard on the right-hand side of `&&` is not executed.

When the selector is `"text"` while checking for `Ticket`, the expression also returns false. These two cases produce the same boolean but have different causes:

```java
if (input == null) {
    System.out.println("root-null");
} else if (!(input instanceof Ticket ticket)) {
    System.out.println("wrong-type");
} else {
    System.out.println("ticket-id=" + ticket.id());
}
```

This is an **illustrative snippet inside a method**. This `if` structure preserves diagnostic information: null is distinct from a wrong-type value.

With Java 21 pattern `switch`, a null selector must be handled explicitly if you want a dedicated result:

```java
return switch (input) {
    case null -> "ROOT_NULL";
    case Ticket t -> "TICKET:" + t.id();
    default -> "OTHER_TYPE";
};
```

A plain `default` does not automatically catch a null selector in a pattern switch. If `case null` is omitted, the program can throw a `NullPointerException` when the selector is null instead of entering `default`. This differs from `instanceof`, which returns false for a null root.

## 4. Null Nested Records: An Easily Overlooked Cause

Two record patterns may look similar but differ in inspection depth:

```java
input instanceof Ticket(var id, var customer, var severity, var active)
```

and

```java
input instanceof Ticket(
        var id,
        Customer(var name, Address(var city, var country)),
        var severity, var active)
```

In the first expression, `var customer` directly receives the `Customer`-typed component, which **can bind `null`**. In the second expression, the compiler/JVM must further match `Customer(...)` and `Address(...)`. A nested record pattern **does not match null**.

| Input | Shallow Ticket pattern | Deep Ticket → Customer → Address |
|---|---|---|
| `null` | Does not match | Does not match |
| `"text"` | Does not match | Does not match |
| `new Ticket("T1", null, 4, true)` | Matches | Does not match |
| `Ticket` with Customer but null Address | Matches | Does not match |
| `Ticket` with Address(city=null, country="VN") | Matches | **Matches structurally**, guard may be false |
| `Ticket` with Address(city="HCM", country=null) | Matches | **Matches structurally**, guard may be false |
| `Ticket` with null ID and complete nested records | Matches | Matches (if other components satisfy) |

**Note on leaf components:** `var city` and `var country` can bind null if the `Address` record itself exists. Do not assume that "a record pattern always excludes every null inside." It only requires the record at the **deconstructed level** to be non-null; nullable leaves still need a guard.

When inspecting in a debugger, you can check the exact paths:

```java
ticket.customer() == null
ticket.customer().address() == null
```

However, **do not evaluate the second line** when the first line is true, otherwise it will cause an NPE during debugging. Safe order: root → Customer → Address → city/country.

## 5. A False Guard Is Different from a Non-Matching Pattern

In a `case` with `when`, the guard is evaluated only **after** the primary pattern has matched and its variables are bound. Thus:

```java
case Ticket(var id,
            Customer(var name, Address(var city, var country)),
            var severity, var active)
        when active && severity >= 3
             && "VN".equals(country)
             && city != null
             && city.equalsIgnoreCase("HCM")
        -> "PRIORITY:" + id;
```

can be skipped because:

- `active` is false;
- `severity` is 2 (below the threshold of 3);
- `country` is not exactly `"VN"`, or is null;
- `city` is null or differs from `"HCM"` under `equalsIgnoreCase`.

If the country check fails, the subsequent `city` part is not executed due to `&&` short-circuiting. This does not change the final boolean result, but it **affects how traces are interpreted**: a log placed at the last condition might never run, which is not enough to conclude that execution never reached the guard.

### String Comparisons Must Match the Exact Policy

- `"VN".equals(country)` is case-sensitive and `null`-safe.
- `city.equalsIgnoreCase("HCM")` ignores case but **does not automatically trim**. `" HCM "` still does not equal `"HCM"`.
- `city != null` must precede the `city.equalsIgnoreCase(...)` call.
- `severity >= 3` accepts the boundary value 3; changing it to `> 3` alters behavior at the threshold.
- If the source API uses different city codes, do not assume `"HCM"`, `"Ho Chi Minh"`, and internal codes are equivalent. Normalization should be defined at the boundary if required by business rules.

Debug guards using the **actual values after binding**, not merely by looking at variable names in code.

## 6. Complete Java 21 Program: Routing, Diagnostics, and Cross-Checking

Create a file named **`PatternMismatchDiagnosticsDemo.java`** with the following code. The program has three methods:

- `isPriority` is an `instanceof` check with a nested record pattern and `&&`.
- `route` is a `switch` with a guarded branch, a Ticket fallback branch, a null branch, and a default for wrong types.
- `diagnose` checks each condition by name and returns a human-readable reason.

`check` compares the results of all three methods against independent expected values and throws an `AssertionError` if there is any mismatch.

```java
import java.util.Objects;

public class PatternMismatchDiagnosticsDemo {
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Ticket(String id, Customer customer, int severity, boolean active) {}

    static boolean isPriority(Object input) {
        return input instanceof Ticket(
                var id,
                Customer(var name, Address(var city, var country)),
                var severity, var active)
                && active
                && severity >= 3
                && "VN".equals(country)
                && city != null
                && city.equalsIgnoreCase("HCM");
    }

    static String route(Object input) {
        return switch (input) {
            case null -> "ROOT_NULL";
            case Ticket(var id,
                        Customer(var name, Address(var city, var country)),
                        var severity, var active)
                    when active && severity >= 3
                         && "VN".equals(country)
                         && city != null
                         && city.equalsIgnoreCase("HCM")
                    -> "PRIORITY:" + id;
            case Ticket ticket -> "STANDARD:" + ticket.id();
            default -> "OTHER_TYPE";
        };
    }

    static String diagnose(Object input) {
        if (input == null) return "root-null";
        if (!(input instanceof Ticket ticket)) return "wrong-type";
        if (ticket.customer() == null) return "customer-null";
        Customer customer = ticket.customer();
        if (customer.address() == null) return "address-null";
        Address address = customer.address();
        if (!ticket.active()) return "inactive";
        if (ticket.severity() < 3) return "low-severity";
        if (!"VN".equals(address.country())) {
            return address.country() == null ? "country-null" : "country-other";
        }
        if (address.city() == null) return "city-null";
        if (!address.city().equalsIgnoreCase("HCM")) return "city-other";
        return "matched";
    }

    static void check(String label, Object input, String expectedRoute,
                      String expectedReason, boolean expectedPriority) {
        String actualRoute = route(input);
        String actualReason = diagnose(input);
        boolean actualPriority = isPriority(input);
        if (!Objects.equals(expectedRoute, actualRoute)
                || !Objects.equals(expectedReason, actualReason)
                || expectedPriority != actualPriority) {
            throw new AssertionError(label + ": route=" + actualRoute
                    + ", reason=" + actualReason
                    + ", priority=" + actualPriority);
        }
        System.out.println(label + " => " + actualRoute
                + " | " + actualReason + " | priority=" + actualPriority);
    }

    public static void main(String[] args) {
        check("root null", null, "ROOT_NULL", "root-null", false);
        check("wrong type", "text", "OTHER_TYPE", "wrong-type", false);
        check("customer null", new Ticket("T01", null, 4, true),
                "STANDARD:T01", "customer-null", false);
        check("address null", new Ticket("T02", new Customer("An", null), 4, true),
                "STANDARD:T02", "address-null", false);
        check("inactive", new Ticket("T03", new Customer("An",
                new Address("HCM", "VN")), 4, false),
                "STANDARD:T03", "inactive", false);
        check("low severity", new Ticket("T04", new Customer("An",
                new Address("HCM", "VN")), 2, true),
                "STANDARD:T04", "low-severity", false);
        check("country null", new Ticket("T05", new Customer("An",
                new Address("HCM", null)), 4, true),
                "STANDARD:T05", "country-null", false);
        check("country other", new Ticket("T06", new Customer("An",
                new Address("HCM", "TH")), 4, true),
                "STANDARD:T06", "country-other", false);
        check("city null", new Ticket("T07", new Customer("An",
                new Address(null, "VN")), 4, true),
                "STANDARD:T07", "city-null", false);
        check("city other", new Ticket("T08", new Customer("An",
                new Address("HN", "VN")), 4, true),
                "STANDARD:T08", "city-other", false);
        check("city lowercase", new Ticket("T09", new Customer("An",
                new Address("hcm", "VN")), 4, true),
                "PRIORITY:T09", "matched", true);
        check("boundary severity", new Ticket("T10", new Customer("An",
                new Address("HCM", "VN")), 3, true),
                "PRIORITY:T10", "matched", true);
        check("id null", new Ticket(null, new Customer("An",
                new Address("HCM", "VN")), 4, true),
                "PRIORITY:null", "matched", true);
        check("name null", new Ticket("T11", new Customer(null,
                new Address("HCM", "VN")), 4, true),
                "PRIORITY:T11", "matched", true);
        check("high severity", new Ticket("T12", new Customer("An",
                new Address("HCM", "VN")), 9, true),
                "PRIORITY:T12", "matched", true);
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 PatternMismatchDiagnosticsDemo.java
java PatternMismatchDiagnosticsDemo
```

**Stdout verified by running the actual program:**

```text
root null => ROOT_NULL | root-null | priority=false
wrong type => OTHER_TYPE | wrong-type | priority=false
customer null => STANDARD:T01 | customer-null | priority=false
address null => STANDARD:T02 | address-null | priority=false
inactive => STANDARD:T03 | inactive | priority=false
low severity => STANDARD:T04 | low-severity | priority=false
country null => STANDARD:T05 | country-null | priority=false
country other => STANDARD:T06 | country-other | priority=false
city null => STANDARD:T07 | city-null | priority=false
city other => STANDARD:T08 | city-other | priority=false
city lowercase => PRIORITY:T09 | matched | priority=true
boundary severity => PRIORITY:T10 | matched | priority=true
id null => PRIORITY:null | matched | priority=true
name null => PRIORITY:T11 | matched | priority=true
high severity => PRIORITY:T12 | matched | priority=true
```

**Explanation of notable cases:**

1. **Root null**: `instanceof` returns false; `switch` selects `case null`; `diagnose` reports `root-null`.
2. **Wrong type**: input is a String, not a Ticket; `default` in `switch` handles other types.
3. **Customer null**: Ticket exists, but `Customer(...)` does not match; the guarded `switch` branch is skipped and `case Ticket ticket` returns STANDARD.
4. **Address null**: similarly, fails at the Address deconstruction level.
5. **Inactive / low severity**: the records are complete, but the guard is false; this is not a structural failure.
6. **Country or city null**: `var country` and `var city` still bind null because the nested Address exists; the guard returns false per the condition.
7. **City lowercase**: `"hcm"` matches because `equalsIgnoreCase` is used. If the code used `equals`, the result would differ — something to review.
8. **Severity = 3**: confirms the threshold is inclusive of 3.
9. **Null ID or Customer name**: does not prevent the nested pattern from matching because `var` is used directly on the component. `PRIORITY:null` comes from string concatenation; this is sample behavior, not a recommendation to skip ID validation in production.

`diagnose` prioritizes reporting **one reason in check order**, rather than listing all causes simultaneously. For example, a ticket that is inactive and has the wrong country will return `inactive`. To list all reasons, you could build a separate list of errors, while keeping in mind that this behaves differently from the **short-circuit** behavior of the original guard.

## 7. Building a Diagnostic Method Without Changing Semantics

A common debugging habit is inserting logging inside a pattern or adding a side-effecting function to `when`. This can alter evaluation order, exceptions, or the number of accessor calls. For production code, prefer:

1. **Keep the running classification function intact.**
2. **Set a breakpoint** at the start of the `switch` or at the caller to inspect the input and its components.
3. Create a **pure diagnostic function** (when possible) that takes the same input and separates each condition with clear names.
4. Use the same test dataset to prove the selected branch and the reported failure reason are consistent.
5. Once the root cause is identified, fix the data or logic as required and run regression tests; do not leave unnecessary instrumentation in place.

Example of an unsafe approach:

```java
// Illustrates an idea that should not be overused:
if (input instanceof Ticket ticket && logAndCheck(ticket)) {
    // ...
}
```

If `logAndCheck` writes logs, increments metrics, makes network calls, or throws errors, the runtime path can change. When adding tracing to a real system, control side effects and collect only necessary information; avoid printing personal data or tokens/secrets from components.

If a record accessor is explicitly declared (rather than the default accessor) and has side effects, even reading a component multiple times for diagnostics can cause differences. For plain data records without custom accessors, separating each check like `diagnose` is very effective.

## 8. Case Ordering: Code Runs, Yet the Branch Is Not Selected

In `switch`, the JVM evaluates case labels in declaration order and selects only the first matching branch whose guard is satisfied.

Valid version:

```java
return switch (input) {
    case null -> "ROOT_NULL";
    case Ticket(var id,
                Customer(var name, Address(var city, var country)),
                var severity, var active)
            when active && severity >= 3
                 && "VN".equals(country)
                 && city != null
                 && city.equalsIgnoreCase("HCM")
            -> "PRIORITY:" + id;
    case Ticket ticket -> "STANDARD:" + ticket.id();
    default -> "OTHER_TYPE";
};
```

Placing the guarded Ticket branch **before** the general Ticket branch is essential. If reversed:

```java
case Ticket ticket -> "STANDARD";
case Ticket(var id, var customer, var severity, var active)
        when active -> "PRIORITY";
```

this is **not a runtime "pattern did not match" bug**. In Java 21, the second guarded branch is dominated by the preceding `case Ticket ticket` (*dominated case label*), so the compiler rejects it. Distinguish compile-time dominance errors from situations where the code compiles but the guard evaluates to false.

Ordering also matters when **multiple guards evaluate to true** without type-level dominance: the first branch wins. When debugging, read the entire `switch` rather than only the suspected `case`.

## 9. Compile-Time Errors vs. Runtime No-Match

Some symptoms look like "the pattern didn't match," yet the program has not even compiled:

| Symptom | Error Category | How to Handle |
|---|---|---|
| Compiler reports incompatible types between selector and pattern | **Compile-time applicability** | Check the static type of the selector and the validity of a checked cast |
| Compiler reports wrong number of components in a record pattern | **Syntax / arity** | Cross-check record components and declaration order |
| Compiler reports dominated case label | **Case ordering / coverage** | Place narrower or guarded cases before broader cases |
| Compiler reports switch expression is not exhaustive | **Incomplete case set** | Add missing domain cases; do not arbitrarily add default to hide errors |
| Code runs, `instanceof` returns false | **Runtime no-match** | Check root type/null and each nested pattern |
| Code runs, Ticket fallback is selected | **Specific pattern/guard failed** | Separate structural checks from business guards |
| Code throws NullPointerException in guard | **Unsafe dereference** | Check nullable leaves, `&&`/`||` ordering, and accessors |
| Code throws NullPointerException when switch selector is null | **Unhandled null selector** | Add `case null` or validate non-null at the boundary |

**Static type differs from runtime type:** `Object value = new Ticket(...)` can be tested with `value instanceof Ticket t`. However, if a pattern kind is not applicable to the **static type** of the expression, the compiler rejects it immediately; there is no runtime match to analyze. When you see a `javac` error, resolve it before writing runtime tests.

## 10. Common Debugging Misconceptions

### 10.1. "If the root has the right type, the deep record pattern must match"

False. The root Ticket may exist while Customer or Address is null. A nested record pattern fails to match at that null level, before the guard is ever considered.

### 10.2. "A null String component always makes the record pattern fail"

False in Java 21 `var` examples: `var city` directly on a String component can bind null. The `city != null` condition inside the guard is what blocks it.

### 10.3. "If a println at the end of the guard doesn't log, the pattern didn't match"

Not necessarily. `&&` short-circuits: an earlier false condition prevents later expressions from being evaluated; or the structural pattern may not have matched. No log at the end **does not prove** execution never entered the guard.

### 10.4. "Adding default will reveal the cause"

`default` only handles the remaining cases by design; it does not provide a reason on its own. In closed sealed/enum domains, adding `default` indiscriminately can also mask exhaustiveness checks when new variants are introduced. With open `Object` input, `default` is a normal fallback, but you still need separate logging or diagnostics for details.

### 10.5. "Lowercasing a String and comparing is equivalent"

Not necessarily. `equalsIgnoreCase`, `toLowerCase`, and `trim`/`strip` have different semantics and Unicode/locale behavior. Establish the domain's normalization policy rather than swapping expressions just because a specific value failed to match.

### 10.6. "One passing test input is enough"

A single passing test cannot distinguish root null, nested null, false guard, wrong threshold, or wrong group name. Your test suite should include a representative case for each rejection gate.

### 10.7. "If a variable is visible after instanceof, it can be used anywhere"

False. Pattern variables have scopes governed by **flow scoping**. With `input instanceof Ticket ticket && ticket.active()`, `ticket` is in scope on the right-hand side of `&&` because the left-hand side must match first. You cannot arbitrarily use it in a branch where the pattern may have failed.

### 10.8. "A no-match is a Java bug rather than a data issue"

Many no-match cases are the intended behavior of the pattern. Compare against the contract: if an inactive Ticket is supposed to go to STANDARD, not selecting PRIORITY is **correct**. A bug exists only when the outcome differs from the intended policy.

## 11. Diagnostic Testing: Independent Expectations and Boundary Matrix

The program in section 6 intentionally accepts `expectedRoute`, `expectedReason`, and `expectedPriority`. This avoids the testing pitfall of only writing:

```java
assert route(input).startsWith("PRIORITY") == isPriority(input);
```

If both functions share the same classification bug, they will still agree. Independent expectations derived from the policy make tests stronger.

When converting to JUnit 5, you can use parameterized tests with these columns:

| Scenario | Expect deep structural match? | Expect guard? | Expected route |
|---|---|---|---|
| Root null | No | Not evaluated | ROOT_NULL |
| Wrong type | No | Not evaluated | OTHER_TYPE |
| Customer null | No | Not evaluated | STANDARD |
| Address null | No | Not evaluated | STANDARD |
| Country null | Yes | False | STANDARD |
| City null | Yes | False | STANDARD |
| Inactive | Yes | False | STANDARD |
| Severity = 2 | Yes | False | STANDARD |
| City = `hcm`, severity = 4 | Yes | True | PRIORITY |
| Severity = 3 | Yes | True | PRIORITY |
| Null ID, remaining components valid | Yes | True | PRIORITY:null |

**No framework is needed to verify a small bug:** running a self-contained Java program is enough to test a hypothesis. In a real repository, however, tests should live alongside domain code and run in CI. Do not turn a production diagnostic helper into an unmonitored duplicate of the policy: if rules change, the two can drift; make ownership of the conditions clear.

## 12. Step-by-Step Practical Debugging Workflow

When a pattern you expect to match does not:

1. **Read build messages first.** If `javac` does not compile, it is an applicability, scope, dominance, or exhaustiveness error, not runtime behavior.
2. **Identify the selector and its static type.** Compare the `Object`/interface/generic declaration against the pattern type. Use a debugger to inspect runtime values and nulls; avoid guessing from `toString` logs.
3. **Check null at the root.** If the root is null, `instanceof` is false; for `switch`, check whether `case null` is present.
4. **Check the root type.** If the type is wrong, nested records and guards are not evaluated.
5. **Walk each nested record in order.** Is Customer null? Is Address null? One null level is enough to fail a deep pattern.
6. **Record the bound leaf components.** ID, name, city, and country can be null even when the deep pattern matched.
7. **Check the guard independently.** For `&&`, inspect each sub-condition's value (when safe), find the first false condition, and verify parentheses grouping. Preserve short-circuit order.
8. **Read earlier cases above.** If the code compiled, check whether another guard caught the input first; if there were dominance, `javac` would already have reported it.
9. **Verify the fallback.** After the priority branch fails to match, does the input fall into the Ticket fallback or default? A missing fallback can change output during refactoring.
10. **Write a test with independent expectations** for the failing input and a corresponding passing case.
11. **Check for exceptions/side effects.** An accessor or guard might throw an exception, which should not be misread as a boolean false.
12. **Fix the exact failing layer**, then run regression tests before concluding the issue is resolved.

The goal of this workflow is to answer one concrete question: **"At which gate was the input rejected, by which rule, and does that match the contract?"**

## 13. Self-Check Exercises

Consider:

```java
record Location(String zone) {}
record User(String name, Location location) {}
Object value = new User("Lan", new Location(null));
```

**Exercise 1:** Does `value instanceof User(var name, Location(var zone))` match?  
**Answer:** Yes. The root User and nested Location are non-null, and `var zone` can bind null.

**Exercise 2:** Is adding `&& zone.startsWith("A")` safe?  
**Answer:** No. The pattern matched, but `zone` can be null, causing `startsWith` to throw an NPE. You need `&& zone != null && zone.startsWith("A")`.

**Exercise 3:** If `value` is replaced with `new User("Lan", null)`, does the deep pattern match?  
**Answer:** No. `Location(...)` is a nested record pattern and does not match null.

**Exercise 4:** If the deep pattern is replaced with `User(var name, var location)`, does it match when `location` is null?  
**Answer:** Yes. `var location` directly binds the null value of the component.

**Exercise 5:** If the selector is `null`, can `instanceof User u` be used to obtain `u`?  
**Answer:** No; `instanceof` is false and `u` is not bound.

**Exercise 6:** If a guarded `case` is not selected while `case User u` is selected, what could have happened?  
**Answer:** Either the guard was false or a more specific pattern did not match, while the broader `User` type pattern matched. Inspect both structure and guard.

**Exercise 7:** When `city` is `" HCM "`, does `city.equalsIgnoreCase("HCM")` return true?  
**Answer:** False, because the method ignores case differences but does not trim whitespace.

## Conclusion

Analyzing **why a pattern does not match** requires stepping through the right layers: **compile time → root type/null → nested record structure → leaf components → guard → case/fallback order**. Two `false` outcomes from `instanceof` can stem from completely different causes; likewise, a `switch` branch not running does not mean the structural pattern failed, because the guard may have returned false.

In Java 21, a **null nested record** prevents a deep pattern from matching, whereas a **null leaf component** can still be bound. Isolating diagnostic conditions into a named method, adding expected tests for each cause, and guarding `&&`/`||` against NPEs are effective ways to find bugs without obscuring pattern matching semantics.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS Java SE 21 — instanceof §15.20.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
