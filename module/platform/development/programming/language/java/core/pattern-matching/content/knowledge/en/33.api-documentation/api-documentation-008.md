# Bringing Pattern Guidelines into Code Review: A Practical Checklist for Java 21+

## 1. Why Does a Team Need Dedicated Guidelines for Pattern Matching?

Starting with Java 21, **pattern matching for switch** (JEP 441) and **record patterns** (JEP 440) became standard features, without requiring `--enable-preview`. These features help Java reduce repetitive casts, express record structures more clearly, and let the compiler check many missing branch cases. However, shorter code **does not automatically guarantee** correctness, maintainability, or `null` safety.

In code review, a `switch` block that looks syntactically clean can still contain bugs:

- A general `case` branch placed earlier causes a branch with `when` to be shadowed (*dominance*).
- A `switch` has a `default` branch, yet a `null` input still causes a `NullPointerException`.
- A pattern matches the outer record, but a **nested component** is `null`, so the specialized branch is not selected.
- A reviewer only sees a test that hits the case, without testing **guard false** and the fallback branch.
- Using type patterns to classify a hierarchy that already has polymorphic behavior, introducing unnecessary coupling.
- Writing generic patterns that cannot be checked safely due to type erasure.
- Packing too much validation/I/O into guards, making case selection order hard to predict or test.

**The goal of pattern guidelines in code review** is to standardize how **correctness, clarity, extensibility, testability, and Java version compatibility** are evaluated. Guidelines are not a mandatory rule that “every `instanceof` must be converted to a pattern” or “every dispatch must be converted to a `switch`”.

### Three Recommended Review Levels

| Review level | When to apply | Action |
| --- | --- | --- |
| **Block / Request changes** | Wrong type/scope, fails to compile, `null` error possible under the contract, missing critical tests, breaks business logic, or introduces a security bug | Fix and verify before merging |
| **Should improve** | Duplication, failing to leverage exhaustiveness, hard-to-read guards, missing edge-case tests without a proven bug yet | Improve in the PR or agree on follow-up tracking |
| **Suggestion / Nit** | Naming, line wrapping, choosing `var` vs. explicit type when both are valid | Non-blocking feedback if it does not violate an agreed standard |

Do not use the *Block* label merely for personal style preferences. Every comment should be tied to a **Java rule, an input example, a real impact, or the team's quality criteria**.

## 2. Preparing Context Before Reading Code

A reviewer needs to know the following information before drawing conclusions about a pattern:

1. **Baseline JDK/source level:** does the project build with Java 17, 21, or newer? For example, record patterns and `when` are standard from Java 21, whereas `instanceof String s` has been standard since Java 16.
2. **Static type of the selector:** `Object`, sealed interface, enum, record, or generic type? It determines exhaustiveness and valid patterns.
3. **`null` policy:** can the input be null, and what does null mean? Return a value, reject it, or guarantee non-null at the API boundary?
4. **Domain contract:** is the classification meant for formatting data, parsing commands, mutating state, or handling business logic? Are there authorization, transaction, or invariant preservation requirements?
5. **Test matrix:** which subtypes, guards, null components, and exceptions are allowed to occur?
6. **Extension strategy:** is the hierarchy closed with `sealed`, or are there third-party plugins/subtypes?

Do not review a `switch` pattern in isolation from its data contract. The same `case null` can be valid handling in the presentation layer, while masking an input bug in an API that requires non-null.

## 3. Rules for Choosing Between Patterns and Polymorphism

### 3.1. Patterns Usually Fit When Processing Data by Structure

~~~java
record Point(int x, int y) {}

static String format(Object value) {
    return switch (value) {
        case Point(var x, var y) -> "(" + x + "," + y + ")";
        case null -> "null";
        default -> "khác";
    };
}
~~~

This is a **data-to-string transformation** based on type/shape. A record pattern makes the needed components immediately visible without casting or calling accessors step by step.

### 3.2. Polymorphism Usually Fits When Behavior Belongs to Subtypes

~~~java
interface PriceRule {
    int apply(int price);
}

record FixedDiscount(int amount) implements PriceRule {
    public int apply(int price) {
        return Math.max(0, price - amount);
    }
}

record PercentDiscount(int percent) implements PriceRule {
    public int apply(int price) {
        return price * (100 - percent) / 100;
    }
}

static int finalPrice(PriceRule rule, int price) {
    return rule.apply(price);
}
~~~

If behavior is a core responsibility of each `PriceRule` type, forcing every caller to distinguish `FixedDiscount`/`PercentDiscount` can increase coupling and make plugins harder to extend. Conversely, when adding many operations outside a closed data domain (formatting, mapping, UI representation), a pattern switch may be more appropriate.

**Guideline:** a review should ask “does this logic belong to the object or to an external transformation?” before debating which syntax is faster. The performance of virtual dispatch and pattern switch depends on the JIT/workload; **do not block a PR with unbenchmarked speed claims**.

## 4. Type Pattern and Flow Scoping Checklist

A type pattern can combine a type check and a variable declaration:

~~~java
static int lengthIfText(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
~~~

Review points:

- The variable `text` has type `String` determined by the compiler.
- The `&&` operator short-circuits: `text.isBlank()` only runs when `input` actually matches `String`, so accessing the variable is valid.
- When `input == null`, `instanceof String text` returns `false`, so the method returns 0 with no NPE from the `instanceof` check itself.
- Pattern variable names should clearly convey meaning; avoid `x`, `s`, `o` in long switches with many cases.

**Scope error, rejected by the compiler:**

~~~java
// DOES NOT COMPILE: text is not in a valid scope on the right-hand side of ||.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
~~~

When the left-hand side of `||` is false, `text` is not yet bound; Java does not allow using it this way. Change `||` to `&&` **only when it matches the business intent**. Do not change the operator just to make the code compile and accidentally alter the condition.

Using an early return is also valid:

~~~java
static String requireNonBlankString(Object value) {
    if (!(value instanceof String text)) {
        return "không phải String";
    }
    return text.isBlank() ? "rỗng" : text.strip();
}
~~~

If code uses a pattern variable after an early-exit branch, the reviewer should check **flow scoping**: does the compiler guarantee it has matched on that execution path? Do not add redundant casts when the pattern already provides the exact type.

## 5. `switch` Pattern Checklist: Ordering, Guards, and Dominance

In Java 21:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT:" + s;
        default -> "OTHER";
    };
}
~~~

The review should verify:

1. **Specific cases before general cases:** `String s when s.isBlank()` must come before `String s`.
2. **Guards use the matched variable:** `s` is only in scope within its matching branch/guard and must not be referenced in other cases.
3. **Intentional ordering:** if two patterns overlap, the earlier branch may determine the result; the precedence rule should be clearly documented.
4. **Both guard true/false are tested:** `"  "` and `"Java"` behave differently even though both are `String`.
5. **Explicit null policy:** there is a `case null` or a clear precondition; `default` does not catch null by default.
6. **Whether `default` is needed:** an `Object` selector usually needs `default`; an exhaustive sealed selector may not.

**Error due to dominance:**

~~~java
// INTENTIONALLY WRONG: the general String case shadows the guarded String case.
// return switch (value) {
//     case String s -> s;
//     case String s when s.isBlank() -> "BLANK";
//     default -> "OTHER";
// };
~~~

This is a **compile-time** error, not just a missing test. A good review comment:

> **Block:** The earlier `case String s` branch dominates the case with `when`, causing the compiler to reject it. Move the guarded branch above the general String branch and add tests for both blank and non-blank strings.

Do not ask to add `default` as a way to mask a dominance error; **the pattern order and semantics** must be fixed.

## 6. `null` Checklist: Null Selector vs. Null Component

### 6.1. Switch Selector Is Null

~~~java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "OTHER";
    };
}
~~~

`unsafe(null)` throws **`NullPointerException`**, rather than returning `"OTHER"`. If the contract allows null, add `case null`. If the contract forbids null, check with `Objects.requireNonNull(value, "...")` or throw a clear exception at the boundary.

**Review level:** usually **Block** if a null input can actually arrive and the current code causes an unexpected NPE. If the contract already guarantees non-null through sufficiently strong conditions, the reviewer should ask for the contract/tests to be made explicit rather than assuming a bug.

### 6.2. Component Inside a Record Is Null

~~~java
record Point(int x, int y) {}
record Moved(Point target) {}

static String move(Object value) {
    return switch (value) {
        case Moved(Point(var x, var y)) -> "Đến " + x + "," + y;
        case Moved(var target) -> "Chưa có đích";
        case null -> "Thiếu dữ liệu";
        default -> "Khác";
    };
}
~~~

With `new Moved(null)`, the selector is **not null**, but the nested record pattern `Point(...)` does not match because the `target` component is null; the `Moved(var target)` branch handles that data. This is a fallback case completely distinct from the switch's `case null`.

An **unconditional component pattern** such as `var target` can bind a null component reference. Therefore, if a later branch calls `target.toString()` or `target.x()` without checking, an NPE can occur **inside the branch**.

**Guideline:** when seeing `RecordA(RecordB(...))`, check the null contract of the corresponding component. Test at least one null-component case if the data allows it and a fallback is needed.

## 7. Record Pattern Checklist: Structural Correctness and Avoiding Overuse

Record patterns match components **by declaration order**, not by the name of the pattern variable:

~~~java
record User(String name, int age) {}

static String summarize(Object obj) {
    return switch (obj) {
        case User(var name, var age) -> name + " (" + age + ")";
        case null -> "null";
        default -> "khác";
    };
}
~~~

Questions a reviewer should ask:

- Is the outer type actually a **record**? Java 21 does not have general constructor patterns for arbitrary regular classes.
- Does the number of component patterns match the number of components in the record?
- Are the types compatible with each component? `User(String name, int age)` is valid; `User(int age, String name)` is wrong.
- Do variable names clearly reflect their roles, avoiding swapped positions when two components share the `String` type?
- If only one accessor is needed, is `case User user -> user.name()` more readable than `User(var name, var ignoredAge)`?
- Does a pattern nested deeper than three levels still aid readability, or should it be extracted into a helper method / named structure?
- Does the record have mutable collection components or nullable references, and does the code protect them according to the contract?

`var` in a record pattern is **static type inference**, not dynamic typing; nor does it make every component non-null. A record has `final` fields, but one holding a mutable `List` still needs a defensive copy if value immutability is desired.

## 8. `when` Guard Checklist: Purity and Condition Ordering

Guards are a useful tool, but they should not be turned into a place to execute workflows:

~~~java
case LabelChanged(var sku, var label)
        when label == null || label.isBlank() ->
    "Nhãn trống: " + sku;
~~~

Advantages of this guard:

- Reads like a **branch selection condition**.
- Uses short-circuiting to avoid calling `isBlank()` when `label` is null.
- Does not mutate state; the same input always yields the same result.
- Can be tested across each state: null, whitespace-only, and non-empty content.

Forms of guards that should be reconsidered:

~~~java
// Suggested to avoid in guards:
// case Command c when repository.save(c) -> ...
// case Request r when auditService.send(r) -> ...
~~~

Calls that save to a database, send over the network, or write audit logs have side effects and can throw exceptions. Placing them in a guard makes **case selection** depend on I/O, branch evaluation order, and external state; the code becomes hard to reason about, hard to test, and hard to keep transactional. Move that behavior into a handler/service after the appropriate case is selected.

**Not every method call in `when` is wrong.** A pure predicate like `s.isBlank()` or a simple validation function with a clear contract is reasonable. Reviewers should evaluate **side effects, cost, and exception potential**, rather than banning guards mechanically.

## 9. Sealed Hierarchy and Exhaustive Switch Checklist

Example:

~~~java
sealed interface Event permits Created, Deleted {}
record Created(int id) implements Event {}
record Deleted(int id) implements Event {}

static String eventName(Event event) {
    return switch (event) {
        case null -> "NONE";
        case Created(var id) -> "CREATED:" + id;
        case Deleted(var id) -> "DELETED:" + id;
    };
}
~~~

Because Java knows the valid set of subtypes of `Event`, a switch expression can be exhaustive **without `default`**. This is a good signal when reviewing an API with a closed hierarchy: when a new subtype is added, the compiler can force all relevant switches to be updated.

**Checklist:**

- If the intent is to handle a sealed hierarchy completely, consider **omitting `default`** to preserve the exhaustiveness signal.
- If a fallback is needed because the API allows unexpected subtypes, document the reason clearly; avoid `default -> null` just to silence the compiler.
- `case null` is a **runtime policy**, not a substitute for subtype exhaustiveness checking.
- Guarded cases must be arranged so that values with **guard false** still have a proper handling branch.
- Adding a subtype or changing record components is an API change and requires updating tests/contracts/documentation.

**Note:** a sealed hierarchy is not necessarily the right choice for an open plugin API. If third parties must implement the interface themselves, `sealed` can prevent desired extensibility. Do not convert an open interface to `sealed` just to write a switch without `default`.

## 10. Generic Pattern and Type Erasure Checklist

A commonly overlooked issue when reviewing Java generics code:

~~~java
record Box<T>(T value) {}
~~~

An input whose static type is only `Object` **cannot** be checked as an arbitrary `Box<String>` at runtime, because generic type arguments are not fully preserved on the instance after **type erasure**:

~~~java
// DOES NOT COMPILE with Object input:
// if (input instanceof Box<String>(var text)) {
//     System.out.println(text);
// }
~~~

Safer approach:

~~~java
static String boxLabel(Object input) {
    if (input instanceof Box<?>(var value)
            && value instanceof String text) {
        return text.toUpperCase();
    }
    return "Không có String";
}
~~~

`Box<?>` makes no promise about a specific generic argument, while `value instanceof String text` verifies the actual component type. Review every pattern on generic records to avoid unchecked casts, raw types, and false promises of type safety.

**Block** if a change introduces an unsafe cast that could cause a `ClassCastException` or violate the type contract. **Suggestion** if the behavior is already type-safe but wildcard/variable naming makes the code hard to follow.

## 11. Exception, Input Data, and Security Checklist

Pattern matching **does not replace validation**. A `case` matching the right subtype does not prove the inner data is valid:

~~~java
record Transfer(String account, long amount) {}
~~~

`case Transfer(var account, var amount)` can match even if `account == null` or `amount <= 0`, unless the constructor already rejected those values. For critical domains:

- Data invariants should be enforced in the constructor/value object or validation layer.
- Rules requiring state, permissions, or external data sources must be handled in the application/domain service.
- `case null` must decide whether to accept empty input or throw an error; do not turn invalid data into a false success.
- Guards should not call untrusted APIs or perform side effects to decide whether to “match”.
- Pattern variables extracted from input **do not automatically become trusted data**: check authorization, length limits, format, quantity, and context-appropriate output escaping.
- Putting everything under `default -> "OK"` can hide unsupported cases; return a meaningful error when needed.

Do not automatically require catching every `NullPointerException`. Prefer **clear input preconditions**, checking at appropriate boundaries, and testing abnormal cases. If a record accessor is custom-implemented and throws an exception, deconstruction should not be treated as completely behavior-free; the reviewer needs to understand the accessor's contract.

## 12. Testing Checklist: Path Coverage, Not Just Case Count

For a pattern switch:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "TEXT";
    default -> "OTHER";
};
~~~

At minimum, four groups should be tested: null selector, blank String, non-blank String, and another type. If a guard contains `||` or `&&`, test the **short-circuit paths** that have business significance.

A minimal matrix for code review:

| Input group | Expected check |
| --- | --- |
| `null` selector | Result/exception per policy |
| Pattern matches and guard true | Specialized branch returns the right result |
| Pattern matches and guard false | Falls through to the general/fallback case properly |
| Type pattern does not match | Other branch or default works properly |
| Record component is null | Nested pattern/fallback and null field handling |
| Adding a sealed subtype | Compiler/tests detect incomplete switch |
| Invalid data | Validation/exception, does not return success |
| Boundary inputs | Zero, negative, blank string, empty, domain maximums |

**JaCoCo branch coverage (C1)** counts control-flow branches from bytecode, **which does not map one-to-one to the number of `case` labels**. High coverage does not prove assertions are strong enough, that guards were tested for all important combinations, or that exception paths were checked. Use an **input matrix + assertions + coverage report**, not just a single percentage number.

At the PR level, a reviewer should request tests stating: “With `Moved(null)` it must enter the `NO_TARGET` branch” rather than “add tests for the switch”.

## 13. Complete Java 21+ Example Following the Guidelines

The following code demonstrates a closed hierarchy with data command records, specialized guards, null selector and null component handling, nested record patterns, and no `default` hiding new subtypes.

Create the file **`PatternReviewGuideDemo.java`**:

~~~java
public class PatternReviewGuideDemo {
    sealed interface Change
            permits QuantityChanged, LabelChanged, Moved, Closed {}

    record QuantityChanged(String sku, int quantity)
            implements Change {}

    record LabelChanged(String sku, String label)
            implements Change {}

    record Point(int x, int y) {}
    record Moved(Point target) implements Change {}
    record Closed(String reason) implements Change {}

    static String describe(Change change) {
        return switch (change) {
            case null -> "Không có thay đổi";

            case QuantityChanged(var sku, var quantity)
                    when quantity <= 0 ->
                "Số lượng không hợp lệ: " + sku;

            case QuantityChanged(var sku, var quantity) ->
                "Đặt " + quantity + " cho " + sku;

            case LabelChanged(var sku, var label)
                    when label == null || label.isBlank() ->
                "Nhãn trống: " + sku;

            case LabelChanged(var sku, var label) ->
                "Đổi nhãn " + sku + ": " + label.strip();

            case Moved(Point(var x, var y))
                    when x == y ->
                "Di chuyển đường chéo: " + x;

            case Moved(Point(var x, var y)) ->
                "Di chuyển đến (" + x + "," + y + ")";

            case Moved(var target) ->
                "Thiếu điểm đến";

            case Closed(var reason) ->
                "Đóng: " + (reason == null
                        ? "không rõ" : reason.strip());
        };
    }

    static void verify(String name, Change change, String expected) {
        String actual = describe(change);
        if (!actual.equals(expected)) {
            throw new AssertionError(name + ": "
                    + actual + " != " + expected);
        }
        System.out.println(name + " -> " + actual);
    }

    public static void main(String[] args) {
        verify("null", null, "Không có thay đổi");

        verify("qty-invalid",
                new QuantityChanged("SKU-1", 0),
                "Số lượng không hợp lệ: SKU-1");
        verify("qty-valid",
                new QuantityChanged("SKU-1", 3),
                "Đặt 3 cho SKU-1");

        verify("label-null",
                new LabelChanged("SKU-2", null),
                "Nhãn trống: SKU-2");
        verify("label-blank",
                new LabelChanged("SKU-2", "  "),
                "Nhãn trống: SKU-2");
        verify("label-valid",
                new LabelChanged("SKU-2", "  Mới  "),
                "Đổi nhãn SKU-2: Mới");

        verify("move-diagonal",
                new Moved(new Point(2, 2)),
                "Di chuyển đường chéo: 2");
        verify("move-other",
                new Moved(new Point(2, 5)),
                "Di chuyển đến (2,5)");
        verify("move-null", new Moved(null),
                "Thiếu điểm đến");

        verify("close-null", new Closed(null),
                "Đóng: không rõ");
        verify("close-valid",
                new Closed("  hoàn tất  "),
                "Đóng: hoàn tất");
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewGuideDemo.java
java PatternReviewGuideDemo
~~~

Output:

~~~text
null -> Không có thay đổi
qty-invalid -> Số lượng không hợp lệ: SKU-1
qty-valid -> Đặt 3 cho SKU-1
label-null -> Nhãn trống: SKU-2
label-blank -> Nhãn trống: SKU-2
label-valid -> Đổi nhãn SKU-2: Mới
move-diagonal -> Di chuyển đường chéo: 2
move-other -> Di chuyển đến (2,5)
move-null -> Thiếu điểm đến
close-null -> Đóng: không rõ
close-valid -> Đóng: hoàn tất
~~~

### Looking at the Demo Through a Reviewer's Eyes

**Good points:**

- The `Change` hierarchy is closed; the `switch` handles all four subtypes and `case null`, with no `default` needed.
- Specialized guards appear before the general cases for `QuantityChanged`/`LabelChanged`/`Moved`.
- The guard for `label` uses `||` correctly: if `label == null`, `label.isBlank()` is not called.
- Nested `Point(...)` only matches when `Moved.target` holds a `Point` object; `Moved(null)` goes to the general case, not conflated with a null selector.
- `verify` includes an assertion; if a result is wrong, the program throws `AssertionError` instead of merely printing a claim.

**Points to consider in a real application:**

- The demo uses records without constructor validation to illustrate invalid input paths. In a business system, decide clearly which invariants must be rejected as soon as the command is constructed.
- `Closed(null)` is turned into `"không rõ"` in the formatter; if the close reason is required, it should **not** silently accept null.
- Displaying `sku`/`label` directly fits a demo, but external application data may need context-dependent escaping/encoding in the UI or logs.
- A long pattern switch should be split into helpers like `describeQuantity`, `describeMove` if logic grows; the goal is reviewable code, not maximizing the number of patterns on one screen.

## 14. Review Matrix for the Example Program

| ID | Input | Branch or condition proven |
| --- | --- | --- |
| T1 | `null` | Null selector, matches no record |
| T2 | `QuantityChanged("SKU-1", 0)` | Quantity guard true |
| T3 | `QuantityChanged("SKU-1", 3)` | Quantity guard false, general case |
| T4 | `LabelChanged("SKU-2", null)` | Guard: left-hand side `label == null` true, short-circuit |
| T5 | `LabelChanged("SKU-2", "  ")` | Guard: left-hand side false, `isBlank()` true |
| T6 | `LabelChanged("SKU-2", "  Mới  ")` | Guard false, normal case and `strip()` |
| T7 | `Moved(Point(2,2))` | Nested Point matches, guard `x == y` true |
| T8 | `Moved(Point(2,5))` | Nested Point matches, guard false |
| T9 | `Moved(null)` | Nested Point does not match, `Moved(var target)` case |
| T10 | `Closed(null)` | Unconditional component pattern receives null, branch handles it |
| T11 | `Closed("  hoàn tất  ")` | Normal Closed and text normalization |

The matrix above proves the **executed behavioral paths** in the demo. This is **not** a JaCoCo C1 metric; to obtain actual coverage percentages, run a build/test instrumented by a coverage tool.

## 15. Code Review Comment Templates: Concise, Evidence-Based, Actionable

A helpful comment should include: **location → issue → trigger case → impact → fix/test**. Below are applicable templates:

### Comment A — `default` does not handle null

> **Request changes — null handling:** `switch (input)` receives data from an API that can be null. The `default` branch does not match null, so a request with `input == null` will throw an NPE. Please add `case null` per the contract or validate non-null at the boundary; add a test for `input == null`.

### Comment B — guard shadowed by an earlier case

> **Block — dominance:** `case String s` already catches every String before `case String s when s.isBlank()`. Java will report the later branch as dominated. Please move the guard above the general case; test both blank and non-blank strings.

### Comment C — nested component can be null

> **Request changes — nested record:** `case Moved(Point(var x,var y))` does not match when `target == null`. If legacy data can omit `target`, we need a `Moved(var target)` fallback case or early validation; add a test with `Moved(null)`.

### Comment D — using a pattern increases coupling

> **Suggestion — responsibility:** The handler is switching over multiple implementations just to invoke a behavior that belongs to each implementation. Consider a method on the interface if the hierarchy needs to be extensible or if the behavior must protect its own invariants; keep the pattern switch if this is truly a data transformation at a boundary.

### Comment E — guard false not tested

> **Request changes — tests:** Currently there is only a test for `LabelChanged(null)`. Please add a blank label and a valid label to verify both the `isBlank() == true` branch after the null-check is false, and the unguarded `LabelChanged` branch.

### Comment F — unsubstantiated performance claim

> **Suggestion — performance:** The claim “pattern switch is always faster than method dispatch” has no data. Please remove the absolute claim; if latency matters, compare with JMH under the same workload and verify end-to-end impact.

**Do not copy sample comments verbatim** into every PR. Use a collaborative tone, only raise blocker requests when justified, and provide an actionable way to verify.

## 16. Checklist Ready to Copy into a Pull Request Template

A team can add the following section to the repository's PR template. This is a **checklist template**; not every item needs to apply to every PR:

~~~markdown
### Pattern matching review (if the PR contains instanceof/switch/record patterns)

- [ ] Project source/release matches the syntax used (Java 21 for record/switch patterns).
- [ ] Pattern matching has a clear rationale over casts or polymorphic dispatch.
- [ ] Type/record patterns are statically type-compatible and have the right component count.
- [ ] Pattern variables are only used within valid flow scoping.
- [ ] Cases with `when`/guards precede general patterns when needed.
- [ ] Guards have no unintended side effects; `&&`/`||` conditions are null-safe.
- [ ] Null selector has an explicit policy (`case null`, `requireNonNull`, or contract).
- [ ] Null components of nested records are considered if data may be missing.
- [ ] Sealed switches are exhaustive without `default` hiding missing new subtypes when needed.
- [ ] Generic patterns do not rely on unchecked casts or wrong type erasure assumptions.
- [ ] Unit tests cover guard true/false, other subtypes, null, and relevant invalid inputs.
- [ ] If the PR claims performance gains, representative profiling/benchmarks are included instead of guesses.
- [ ] API contracts, subtype/record component changes, and docs are updated.
~~~

During code review, each checklist item should be tied to **actual code or tests**. Not every PR needs to check “null component” if all relevant components are primitives or constructor invariants guarantee non-null.

## 17. Integrating Guidelines into the Team's Workflow

So that guidelines do not exist only on paper:

1. **Lock the version contract** in the build (e.g., Maven compiler release 21) and put it at the top of the checklist.
2. **Keep a short review doc** in the repository, with links to JEPs/JLS and a runnable example.
3. **Add a PR template** as in section 16; separate *Block* and *Suggestion* to align feedback severity.
4. **Require compile/test in CI**: the compiler catches dominance, type/scope/exhaustiveness errors; tests verify semantic cases that compilation alone cannot catch.
5. **Create a test matrix table** for switches with many guards or nested record patterns. Put specific input groups into test names.
6. **Pair-review sample PRs** to align on `when`, `case null`, `sealed`, and acceptable nesting depth.
7. **Track recurring bugs**: if a bug class appears repeatedly, add a guideline or appropriate static analysis rule; do not write absolute bans without justification.
8. **Re-evaluate after upgrading JDK/JaCoCo/compiler** because bytecode, language features, and JIT optimization opportunities may change.

### What Should the CI Gate Check?

**Compile:** run the build at the locked Java release, for example:

~~~bash
javac --release 21 -encoding UTF-8 PatternReviewGuideDemo.java
java PatternReviewGuideDemo
~~~

With Maven/Gradle, use `mvn test` or `./gradlew test` depending on how the project is configured. A test coverage gate can be set per team policy, but **do not** use a single coverage number to replace reviewing the test matrix and assertions.

**Static analysis:** Checkstyle, SpotBugs, Error Prone, or custom rules can help with certain issues, depending on the tool and Java version; do not assume default tools catch every pattern matching bug. Rules about domain contracts, guard clarity, null policy, and polymorphism trade-offs still require reviewer judgment.

**Do not auto-fix blindly:** a lint rule may suggest converting `instanceof` to a pattern or adding `default`, but the reviewer must confirm the change does not break exhaustiveness, alter logic, or mask a null path.

## 18. Common Guideline Pitfalls

| Review anti-pattern | Why it is bad | How to improve |
| --- | --- | --- |
| “Every `instanceof` must become a `switch`” | Unsuitable for code with a single type check; can add complexity | Choose the smallest construct that expresses the business logic |
| “Always add `default` to avoid compile errors” | Can hide new subtypes in a sealed hierarchy | Prefer an exhaustive case list when needed |
| “`case Object obj` will catch null too” | Null selectors have separate rules | `case null` or a precondition |
| “Record patterns always make components non-null” | Reference components can be null | Check nested patterns and unconditional components |
| “`var` means dynamic typing” | The compiler infers the static type of the component | Check the record declaration, use clear names |
| “Guards can call any service” | Prone to side effects, I/O, and hard-to-control exceptions | Keep guards pure; handle actions in the handler |
| “One test per case label is enough” | Misses guard false/short-circuit and null nested components | Use a path matrix |
| “100% branch coverage means no bugs” | Coverage measures execution, not correctness | Add assertions and boundary/exception tests |
| “Patterns are faster than virtual dispatch” | Depends on JIT, profiling, and workload | Benchmark if performance is a bottleneck |
| “Long code must use deeply nested patterns” | Overly deep patterns can be hard to maintain | Extract helpers and consider accessors/type patterns |
| “Commenting 'wrong style' without explanation” | Lacks basis, leads to fruitless debates | Tie to contract, example, bug/test, and a proposal |
| “Block every minor suggestion” | PRs pile up, reducing trust in reviews | Separate Block / Should improve / Suggestion |

## 19. Review Exercises

**Exercise 1 — Identify the blocker.** A PR adds:

~~~java
static String status(Object input) {
    return switch (input) {
        case String s -> s;
        case String s when s.isEmpty() -> "EMPTY";
        default -> "OTHER";
    };
}
~~~

Which part is guaranteed to cause a compile-time error? If `input` can be null, what runtime issue also occurs? Write a review comment with a concrete fix.

**Exercise 2 — Distinguish two kinds of null.** Given `record Moved(Point target) {}`, are `null` and `new Moved(null)` the same in a `switch`? Which tests should be added?

**Exercise 3 — Test a guard.** For `label == null || label.isBlank()`, which paths do the three inputs `null`, `"  "`, and `"ok"` test? Why is testing only `null` insufficient?

**Exercise 4 — Sealed API.** A reviewer suggests adding `default -> "UNKNOWN"` to every switch on a sealed interface that already covers all subtypes. When should this suggestion be rejected, and when is a fallback genuinely justified?

**Exercise 5 — Review priority.** Mark *Block* or *Suggestion* for three cases: (a) `when` calls `repository.save()` causing a side effect; (b) a pattern variable named `s` in a two-line method; (c) a PR claims “40% optimization” without benchmarks and changes business logic. Explain the severity based on real impact.

**Exercise 6 — Generic pattern.** Why can `Object input instanceof Box<String>(var s)` not be checked safely? Give an alternative using a wildcard and checking the component value.

**Suggested answers:**

- Exercise 1: `case String s` comes first, causing the guarded case to be **dominated**. Move the guarded branch first; if null can occur, handle `case null` or reject at the boundary, since `default` does not catch null.
- Exercise 2: a null selector requires its own `case null`; `new Moved(null)` is a non-null record with a null component, which can enter the `Moved(var target)` branch.
- Exercise 3: they test left-hand side true, left-hand side false / right-hand side true, and both sides false, respectively. Also add other subtype inputs if the switch accepts a wider type and the logic requires it.
- Exercise 4: do not use `default` out of habit if you want the compiler to force updating handlers for new subtypes. A fallback is justified when the API/domain actually defines behavior for unsupported values.
- Exercise 5: (a) usually Request changes because behavior and branch selection are mixed; (b) usually Nit/Suggestion; (c) Request changes because of unsubstantiated claims and unverified logic changes.
- Exercise 6: type erasure; use `Box<?>(var item)` and then check `item instanceof String text`.

## 20. Conclusion

An effective pattern matching guideline in code review is not a set of rules about favorite syntax. It is a **verifiable engineering agreement**:

- Choose patterns when they clarify data shape and transformations; choose polymorphism when behavior belongs to subtypes.
- Keep **case order, guards, type compatibility, and flow scoping** valid; let the compiler catch dominance and missing exhaustive cases.
- Handle **null selectors**, **null record components**, and generic erasure according to the actual contract.
- Review with an **input/test matrix**, not just line/label counts or coverage percentages.
- Leave comments with **severity, reproducible examples, and proposed fixes**, rather than blocking on arbitrary style.
- Maintain the checklist in the PR template and CI, updating it with the project's Java baseline.

### References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch patterns, `when` guards, exhaustiveness, dominance, and null (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction, nested record patterns, and component matching (Java 21).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): permitted subtypes and closed models.
- [JLS 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): pattern semantics and checking.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
