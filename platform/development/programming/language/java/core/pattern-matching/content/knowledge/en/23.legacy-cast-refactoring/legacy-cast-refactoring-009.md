# Avoid refactoring when the domain is unclear: preserving behavior when replacing legacy casts with pattern matching

## 1. Nature of the problem

**Refactoring** means changing code structure without **changing observable behavior** under the current contract. In Java, a very tempting operation is changing:

```java
if (value instanceof Customer) {
    Customer customer = (Customer) value;
    handle(customer);
}
```

to:

```java
if (value instanceof Customer customer) {
    handle(customer);
}
```

With the same `value` object and the same control flow, this is usually a **small syntactic improvement that can preserve behavior**. However, when the **domain** is not yet clearly understood (the actual data types, business states, precedence order, exceptions, policies for unknown values, side effects, etc.), do not automatically assume you can go further by turning an entire `if/else` chain into a `switch`, adding `sealed`, replacing casts with nested record patterns, or deleting branches considered "redundant".

**This topic is not "avoid using pattern matching".** The goal is to know when to **pause refactoring to investigate the contract**. A change that is valid in Java syntax is not necessarily right for the business semantics.

A typical example: class `UrgentText` is a kind of `Text`, but needs to be handled **before** ordinary `Text` instances. If the two branches are merged into a single `Text text` pattern, the program may still compile, yet lose the domain's precedence rule.

### What does an unclear domain mean?

Answers to one or more of the following questions may be missing:

- What object variants exist in the system? Are there subclasses, plugins, proxies, legacy data, or types not yet seen in tests?
- Which branch has precedence, and is that order a business rule?
- How must `null`, unsupported types, invalid values, or data with missing fields be handled?
- Does the legacy code intentionally throw `ClassCastException`, `NullPointerException`, data validation errors, or return a fallback value?
- Which branches write logs, record metrics, cache, call the database, emit events, or mutate state?
- Are there compatibility constraints with public APIs, serialization, other modules, or already-deployed versions?

**Rule:** If you cannot explain the branches using a domain contract or characterization tests, you should not call a large "cleanup" a behavior-preserving refactor.

## 2. Distinguishing safe syntactic changes from business rule changes

| Operation | When is it relatively safe? | Risk when the domain is unclear |
| --- | --- | --- |
| `instanceof Type` followed by casting **the same variable** to `instanceof Type name` | Same object, same check site, same branch body and fallback | Changing the source variable, variable scope, or an expression with side effects can alter behavior |
| Preserving the order of `if/else if` branches | Existing conditions/priorities are preserved | Reordering can change how subclasses are handled |
| Merging multiple branches into a supertype pattern | Subtypes are proven to share the same handling contract | Losing a special business branch |
| Converting `if` to a pattern `switch` | Null handling, precedence, guards, side effects, and fallback are understood | Dominated case, changed null handling, or changed evaluation order |
| Replacing casts/getter calls with a nested record pattern | Domain and accessor contracts are clear | Changing timing or number of component accesses; null may match differently |
| Changing a regular interface/class to `sealed` | All direct implementations and module compatibility have been inventoried | Blocking valid subclasses/plugins of the system |
| Replacing a generic cast with a pattern | Type can be checked at runtime under Java rules | Type erasure; "verifying" `List<String>` may be invalid |
| Deleting a "never happens" fallback | Proven by contract, telemetry, and tests | Losing ability to accept new/legacy data; changing exceptions or responses |

**Boundary:** A mechanical change that makes code easier to read while keeping every branch is usually much less risky than "normalizing the model" based on assumptions. Do not mix these two goals into the same pull request when the domain is unclear.

## 3. Complete example: a safe refactor and one that loses business logic

Suppose a system receives multiple types of messages. No documentation guarantees that all message types are known, and `UrgentText` is a subclass of `Text`.

Save the program as **`LegacyCastRefactorDemo.java`**. The example runs on **Java 17+** because pattern matching for `instanceof` became standard in Java 16 (JEP 394); no preview features are used.

```java
public class LegacyCastRefactorDemo {
    interface Message {}

    static class Text implements Message {
        private final String value;

        Text(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    static final class UrgentText extends Text {
        UrgentText(String value) {
            super(value);
        }
    }

    static final class Count implements Message {
        private final int value;

        Count(int value) {
            this.value = value;
        }

        int value() {
            return value;
        }
    }

    static final class Unknown implements Message {}

    // Legacy code: check type first, then cast manually.
    static String legacy(Message message) {
        if (message instanceof UrgentText) {
            UrgentText urgent = (UrgentText) message;
            return "urgent:" + urgent.value();
        }
        if (message instanceof Text) {
            Text text = (Text) message;
            return "text:" + text.value();
        }
        if (message instanceof Count) {
            Count count = (Count) message;
            return "count:" + count.value();
        }
        return "unsupported";
    }

    // Small refactor: only replace instanceof + cast.
    // Preserves the original order, branch rules, and fallback.
    static String safe(Message message) {
        if (message instanceof UrgentText urgent) {
            return "urgent:" + urgent.value();
        }
        if (message instanceof Text text) {
            return "text:" + text.value();
        }
        if (message instanceof Count count) {
            return "count:" + count.value();
        }
        return "unsupported";
    }

    // Premature refactor: accidentally deletes the UrgentText precedence rule.
    // The program still compiles, but produces different results.
    static String premature(Message message) {
        if (message instanceof Text text) {
            return "text:" + text.value();
        }
        if (message instanceof Count count) {
            return "count:" + count.value();
        }
        return "unsupported";
    }

    static void compare(String label, Message input) {
        System.out.println(label + " -> legacy=" + legacy(input)
                + " | safe=" + safe(input)
                + " | premature=" + premature(input));
    }

    public static void main(String[] args) {
        compare("ordinary", new Text("hello"));
        compare("urgent", new UrgentText("alert"));
        compare("count", new Count(3));
        compare("unknown", new Unknown());
        compare("null", null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 LegacyCastRefactorDemo.java
java LegacyCastRefactorDemo
```

Stdout:

```text
ordinary -> legacy=text:hello | safe=text:hello | premature=text:hello
urgent -> legacy=urgent:alert | safe=urgent:alert | premature=text:alert
count -> legacy=count:3 | safe=count:3 | premature=count:3
unknown -> legacy=unsupported | safe=unsupported | premature=unsupported
null -> legacy=unsupported | safe=unsupported | premature=unsupported
```

### What changed?

- Both `legacy` and `safe` check `UrgentText` **before** `Text`. An `UrgentText` is also a `Text`, but the specific branch is selected just as in the old rule.
- `premature` no longer has the `UrgentText` precedence branch. Because `UrgentText extends Text`, the `instanceof Text` condition still evaluates to true. The result `urgent:alert` turns into `text:alert`.
- For `Unknown` and `null`, all versions still return `unsupported` thanks to the fallback. If the fallback were removed and an exception were thrown instead, behavior would also change.
- **The compiler cannot detect the loss of a business rule that is not expressed in the type system.** The `premature` version is valid Java, but it does not preserve behavior.

Lesson learned: knowing the class/subclass relationship is not enough; you need to know the **meaning and ordering** of the branches.

## 4. Five pitfalls when converting legacy casts to pattern matching

### 4.1. `getClass() == Type.class` differs from `instanceof Type`

Legacy code may intentionally accept only the exact class and exclude subclasses:

```java
if (message != null && message.getClass() == Text.class) {
    Text text = (Text) message;
    return "ordinary text:" + text.value();
}
```

If converted to:

```java
if (message instanceof Text text) {
    return "ordinary text:" + text.value();
}
```

then `UrgentText` is also accepted. This is **not** an equivalent syntactic change. You must investigate why the legacy code required an exact class check before changing the condition.

### 4.2. Unconditional casts differ from `instanceof` checks with fallback

Consider:

```java
static String strict(Object value) {
    Text text = (Text) value;
    return text.value();
}
```

- If `value` holds a type that cannot be cast to `Text`, the cast may throw `ClassCastException`.
- If `value` is null, casting to a reference type yields null; the subsequent `text.value()` call then throws `NullPointerException`.

Replacing it with:

```java
static String permissive(Object value) {
    if (value instanceof Text text) {
        return text.value();
    }
    return "unsupported";
}
```

turns two error paths into the result `unsupported`. This might fit an **approved business requirement change**, but it is **not a behavior-preserving refactor**. If callers depend on those exceptions, either preserve the contract or coordinate changes to callers and tests.

### 4.3. Changing `if/else` order or using an overly broad pattern

For example, placing `if (message instanceof Text)` before `if (message instanceof UrgentText)` makes the `UrgentText` branch unreachable in an `if` chain, even though the compiler may not warn about it.

With Java 21 pattern `switch`:

```java
// Illustrative code that DOES NOT COMPILE:
// return switch (message) {
//     case Text text -> "text";
//     case UrgentText urgent -> "urgent"; // dominated
//     case null -> "null";
//     default -> "other";
// };
```

Here, the compiler can detect that the `UrgentText` branch is dominated by `Text`. However, if the person refactoring **deletes** the UrgentText branch completely just to "fix the compiler error", the business rule is still lost. The right approach is to understand and preserve branch precedence, not merely satisfy the compiler.

### 4.4. Pattern `switch` has its own null-handling rules

With legacy `if (value instanceof Text)`, `null` makes the condition return `false` and flow continues to the fallback. In a Java 21 pattern `switch`, a null selector does not automatically select the `default` branch like any unknown type. Without an appropriate null case, you may get a `NullPointerException`.

If the legacy code returned `unsupported` for null, converting to switch must state this explicitly:

```java
// Java 21+, illustrative snippet inside a method accepting Message.
return switch (message) {
    case UrgentText urgent -> "urgent:" + urgent.value();
    case Text text -> "text:" + text.value();
    case Count count -> "count:" + count.value();
    case null -> "unsupported";
    default -> "unsupported";
};
```

Even if the example appears to preserve part of the behavior, only convert to `switch` after checking all branches and side effects. `case null` handles null for the **selector**, not automatically every null component inside a nested record pattern.

### 4.5. Getters, accessors, and side effects

Legacy code sometimes calls a getter exactly once in one branch. Refactoring into a nested record pattern can extract components **during matching**, before executing the body. If a record has a custom accessor that logs, computes, reads mutable state, or throws an exception, the timing or number of invocations may differ.

Illustrative code:

```java
record LoggedValue(String text) {
    @Override
    public String text() {
        System.out.println("getter called");
        return text;
    }
}
```

Before replacing:

```java
// Illustrative snippet, not a standalone program.
if (value instanceof LoggedValue logged) {
    String text = logged.text();
    process(text);
}
```

with a nested record pattern or multiple `case` labels, you need to know whether invoking the accessor is allowed to cause side effects. Do not assume every "failed pattern match attempt" is harmless, especially with nested record patterns.

## 5. Type erasure: do not "recover" generic types at runtime

Legacy code may contain raw casts or unchecked casts:

```java
// Legacy illustrative code, not recommended.
@SuppressWarnings("unchecked")
static java.util.List<String> strings(Object value) {
    return (java.util.List<String>) value;
}
```

Even though this cast compiles (with an unchecked warning suppressed), the JVM generally cannot distinguish `List<String>` from `List<Integer>` because type arguments are erased. An "equivalent" refactor such as:

```java
// DOES NOT COMPILE if the input only has type Object:
// if (value instanceof java.util.List<String> list) { ... }
```

does not magically become valid just because we use pattern matching.

You can check the container with `List<?>`:

```java
if (value instanceof java.util.List<?> list) {
    System.out.println("size=" + list.size());
}
```

but that **does not prove** every element is a String. If the domain genuinely requires a list of strings, you need a typed API contract or per-element checks before processing. Do not hide an unchecked cast warning behind a pattern that looks type-safe but does not guarantee the invariant.

## 6. Signs you must pause refactoring to understand the domain

**Stop at local syntactic changes** and switch to gathering evidence if any of the following signs appear:

1. **Uninventoried type hierarchy:** an interface is implemented by other modules, a library has subclasses, plugins may supply subtypes, or code uses proxies.
2. **Unclear branch order:** multiple `instanceof` checks on parent/child types, branches with specific guards, or branches with side effects occurring before a fallback branch.
3. **External data without a stable schema:** JSON APIs, legacy databases, message queue events, or data from multiple system versions.
4. **Fallback with error-handling history:** returning a default code, logging, retrying, sending to a dead-letter queue, or throwing an exception; it is unclear who consumes that result.
5. **No contract for null and invalid data:** unknown whether null is a valid case, an invariant violation, or a special signal.
6. **Unchecked generic casts present:** raw types, `Object` holding collections, suppressed warnings, or deserialized data.
7. **Side effects present:** audit/logging, metrics, state mutations, caching, transactions, or service calls inside conditions/getters/branches.
8. **No characterization tests:** no test suite describing the current behavior of critical paths.
9. **Need to change public APIs, sealed hierarchies, or serialization:** affects code outside the current scope.
10. **Temptation to merge cases just because "they look similar":** no confirmation yet that they are truly equivalent in business policy.

These signs do not forbid all changes. They mean **you should not make semantic changes based on assumptions**. An intentional bug fix is still valid, but it must be described as a behavior change, not a pure refactor.

## 7. How to gather evidence before deciding

### 7.1. Determine the contract first, syntax second

For each legacy branch, document:

| Question | Evidence to look for |
| --- | --- |
| Which types does the branch accept? | Class declarations, subtypes, data from callers or plugins |
| What is the precedence condition? | `if/else if` order, `getClass` vs `instanceof` comparisons |
| What are valid values? | Validation, schemas, business rules, sanitized real data examples |
| What happens on failure? | Exceptions, fallbacks, logging, retries, return codes |
| Are there any side effects? | Getter call paths, database, events, metrics, mutable state |
| Who depends on this behavior? | API contracts, downstream consumers, integration tests, backward compatibility |

Do not rely solely on class names: `UrgentText`, `PremiumUser`, or `SpecialRequest` may be suggestive names, but they are not sufficient proof of processing rules.

### 7.2. Write characterization tests

A **characterization test** records **current behavior**, including confusing behavior. The initial goal is to protect what the system currently does before evaluating what should be changed.

A minimal suite should include:

- Ordinary types, special subtypes, and closely related subtypes.
- `null`, unsupported types, empty data, and boundary values.
- Branch selection order, outputs, and exception types (when part of the contract).
- Observable side effects: whether an important event/log is recorded, or the number of business calls if required by the contract.
- Generic/wildcard types or data from legacy APIs if present.
- Cases with older serialization versions or vetted sample data.

In the full program above, the `legacy`/`safe` pair produces the same output across all five cases; however, `legacy`/`premature` differs on `urgent`. A test suite covering only `Text` and `Count` would miss this regression.

If the expected output cannot be determined from the domain, you can initially "freeze" the current output to detect differences, **without** automatically claiming that the old behavior is correct.

### 7.3. Distinguish comparison testing from shadow execution

A common idea is to run both the old and new logic and compare them. This is only safe when both paths are **pure and free of side effects**. Do not run both versions in parallel if either can charge money, write to a database, send emails, or emit messages.

For functions with side effects, use isolated tests with mocks/fakes, controlled test environments, or replay sanitized inputs from logs. Measure outputs, exceptions, and side effects—not just returned strings.

## 8. A cautious refactoring roadmap

### Step 1 — Scope the change

Pick a single `instanceof + cast` branch with a clear relationship and low risk. Do not casually reorder processing, alter the null contract, or turn an interface into `sealed` in the same step.

### Step 2 — Keep conditions and fallbacks intact

Apply a local transformation:

```java
// Before:
if (value instanceof Text) {
    Text text = (Text) value;
    return text.value();
}

// After:
if (value instanceof Text text) {
    return text.value();
}
```

Treat it as equivalent only when `value` is the same expression/object, there is no state change in between, and the body and fallback remain unchanged.

### Step 3 — Run behavior-preserving tests

Run characterization tests, integration tests, and subtype/null/error paths. If a difference appears, classify it as:

- **Unintended regression:** revert the change or fix it to restore the old behavior.
- **Evidenced legacy bug:** open a separate business change with acceptance criteria.
- **Undefined domain:** do not merge a large refactor; ask the module owner to confirm the contract.

### Step 4 — Expand to `switch`/record patterns only with justification

Once all branches and null/fallback behavior are proven, you may consider pattern `switch` (Java 21) for clearer dispatch. If proposing nested record patterns, confirm that the data has a stable record structure and that accessors are suitable for deconstruction. If proposing `sealed`, verify all possible implementations.

### Step 5 — Observe after deployment

For systems receiving external data, monitor the frequency of the fallback branch, unknown types, and casting errors. Do not log sensitive data just to figure out the domain. Once behavior is understood, deeper changes should be split into PRs with clear tests and goals.

## 9. When is not refactoring yet the right decision?

Choosing **not to change the architecture yet** can be a deliberate engineering decision if:

- The legacy code works reliably, touching the domain carries high risk, and test coverage is lacking.
- A plugin system has external implementations; switching to a sealed hierarchy could break compatibility.
- The fallback branch performs an important but undocumented task.
- Type erasure or deserialized data prevents reliably determining the true runtime type.
- Delivery is urgent: small, testable syntactic improvements are better than a large, unproven refactor.

Leave clear notes in the issue/PR about **unknowns, evidence to gather, and conditions to proceed**, rather than a vague comment like "legacy code, TODO refactor".

Example short note:

> Kept `UrgentText` ordered before `Text` because current outputs differ. Not all `Message` implementations from plugins have been verified yet; this phase only replaces casts with pattern variables while preserving fallback and exception behavior. Characterization tests for plugin messages are needed before migrating the full logic to switch.

## 10. Common thinking traps

1. **"If it compiles, the semantics must be unchanged."** The compiler only checks language rules; it does not know every business rule.
2. **"Pattern matching is always safer than casting."** Type patterns avoid some redundant casts, but do not automatically preserve legacy exceptions, fallbacks, and side effects.
3. **"A subtype branch is a case of the parent branch, so they can be merged."** True for type relationships, not necessarily true for the domain.
4. **"Not seeing a subtype in the repo means it doesn't exist."** There may be plugins, dependencies, subclasses in other modules, or deployed data.
5. **"A switch's `default` will handle everything like a legacy else."** A null selector has special rules in a pattern switch; and `default` may change exception behavior.
6. **"Record patterns just mean less code."** Deconstruction has accessor-invocation and null rules; it can change when errors or side effects occur.
7. **"An unchecked cast can be replaced with a `List<String>` pattern."** Java type erasure does not allow proving such generic information from an `Object`.
8. **"One happy-path test is enough."** Critical regressions often hide in subclasses, null, unknown types, and boundary values.
9. **"We can shadow-run both branches to compare."** Not if the logic has side effects on real systems.
10. **"Not refactoring means abandoning the code."** Setting change boundaries and gathering the contract is an essential part of system maintenance.

## 11. Pre-PR approval checklist

- [ ] Is the scope strictly a syntactic change, or is there a domain/behavior change?
- [ ] Are subtype/parent branches and their ordering preserved, or is there an approved new requirement?
- [ ] Are `null`, unsupported types, exceptions, and fallbacks covered by tests?
- [ ] Have getters, record accessors, guards, and branches with side effects been inspected?
- [ ] Have generic type erasure, raw types, or unchecked casts been evaluated?
- [ ] Have we avoided adding `sealed`, changing APIs, or altering serialization without knowing all consumers?
- [ ] Are there characterization tests for key domain cases, and have regressions been checked?
- [ ] If there is a behavior change, does the PR clearly state *what changed, why, who approved it, and the impact on callers*?

**Conclusion:** When the domain is unclear, prioritize **narrowly scoped mechanical refactors** (such as replacing `instanceof + cast` with a pattern variable in the same branch) and preserve observable behavior. **Defer** merging branches, migrating wholesale to switch/record patterns, changing exceptions/fallbacks, or sealing type hierarchies until you have the contract and test evidence. The goal of pattern matching is to make code clearer, not to obscure business rules that are not yet understood.

### References

- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
