# Evaluating the Readability of Pattern Composition in Java (Java 21+)

## 1. Why Evaluate Readability?

**Pattern composition** is a way of combining multiple patterns to recognize data types and structures, deconstruct `record` components, and then select how to handle them. In Java 21+, composition commonly appears as **nested record patterns**, **type patterns**, **`instanceof` combined with conditions**, and **pattern matching for `switch` with `when`**.

For example, the same `Shipment` object can be inspected across multiple levels:

```java
case Shipment(
        var id,
        Customer(var name, var vip),
        Address(var city, Point(var x, var y)),
        var parcels) when vip && parcels > 0 && x >= 0 && y >= 0 ->
    ...
```

This syntax is concise because it expresses both the **shape** of the data and the values needed in one place. However, the deeper the nesting and the more variables and conditions involved, the harder it becomes for readers to tell **which branch matches**, **why it matches**, **at which level a null causes failure**, and **where to make changes when updating a rule**.

This lesson focuses on **evaluating the readability, understandability, and maintainability** of pattern composition. The goal is not to make the code as short as possible; the goal is to make it easy for others to answer three questions:

1. **What data is being recognized?** The outermost type, child records, and required components.
2. **What conditions apply to the branch?** Structural rules, `null`, guards, and precedence.
3. **If a variant is added or a rule is modified, where do changes need to be made?** Maintainability and testability.

**Version:** `record` has been a standard feature since Java 16. **Record Patterns (JEP 440)** and **Pattern Matching for `switch` (JEP 441)** became standard features in **Java 21**. The complete examples in this lesson use **JDK 21+** without requiring `--enable-preview`.

## 2. Recognizing Composition Forms Before Evaluating

### 2.1. Type pattern: caring only about the type

```java
case Shipment s -> "Lô hàng " + s.id()
```

This pattern matches a non-null `Shipment` object and keeps the object intact in the variable `s`. It is often readable when handling multiple properties in another method or when only one accessor is needed.

### 2.2. Record pattern: deconstructing components directly

```java
case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")"
```

With `record Point(int x, int y) {}`, this pattern both matches `Point` and extracts its two components in declaration order. `x` and `y` are inferred as `int`. This form is good when both values are genuinely needed in the branch.

### 2.3. Nested record pattern: checking multiple levels

```java
case Address(var city, Point(var x, var y)) ->
    city + ": " + x + ", " + y
```

With `record Address(String city, Point location) {}`, the pattern checks `Address` on the outside and `Point` in the `location` component. **Each `Type(` starts a new level of checking**; `var` bindings are the stopping points of deconstruction, assigning the entire component to a variable.

### 2.4. Guard: adding value rules

```java
case Point(var x, var y) when x >= 0 && y >= 0 ->
    "Hai tọa độ không âm"
```

`when` is evaluated only after the `case` pattern has matched; when the guard is false, `switch` evaluates the next branch. Guards are suitable for short conditions with clear meaning. Long business conditions can force the reader's eyes to jump across many pairs of parentheses and operators.

### 2.5. Combining `instanceof` with `&&`

```java
if (value instanceof Point(var x, var y)
        && x >= 0
        && y >= 0) {
    System.out.println("Điểm hợp lệ");
}
```

This is a readable combination when there is only one Boolean question. `&&` short-circuits: the variables `x` and `y` are only used on the right-hand side when the pattern has matched. Do not replace `&&` with `||` expecting the variables to still be in scope: the right-hand side of `||` can be evaluated when the pattern does not match.

## 3. Criteria for Evaluating Whether a Pattern Is Readable

There is no single metric for every codebase. When reviewing, check the following criteria and explain using concrete scenarios:

| Criterion | Signs of Readability | Signs That Need Review |
| --- | --- | --- |
| **Intent** | The reader immediately sees the data to be matched and the corresponding action | Having to read the entire record tree just to guess the business rule's name |
| **Depth** | Deconstructs only down to the level truly needed | Deconstructs through multiple child records just to use a single value or check a flag |
| **Number of variables** | Variables are named meaningfully and most are used in the branch | Many `var a, var b, var c`; many variables declared but unused |
| **Guard** | A few clear, null-safe, easy-to-verify conditions | Long `&&`/`||` chains, many negations, order-dependent conditions that are hard to spot |
| **Null and data errors** | Clear which level can be null and which fallback branch catches it | Confusing `Record(...)` with `var component`; guard might call a method on null |
| **`case` ordering** | Specific/guarded branches placed before general branches | General branch shadows later branches or readers struggle to tell precedence |
| **Variable scope and naming** | Easy to find where a variable is extracted and used in `when`/branch body | Reusing ambiguous names, having to trace through many parentheses |
| **Modifiability** | Changing a rule has one clear place to edit and test | The same condition appears in multiple `case`s, easy to miss an update |
| **Testability** | Can enumerate inputs, matching cases, guards, and outputs | Cannot explain the fallback branch or edge cases |

You can use a **diagnostic question**: "Can someone looking at the code for the first time distinguish between **the pattern not matching** and **the pattern matching but the guard failing** in roughly a single read-through?" If that is difficult, reduce the depth, extract conditions, or name the rule.

Thresholds such as "more than two levels of nesting" or "more than three condition groups" are only **signals to consider refactoring**, not language rules or formal quality thresholds. A very familiar three-level nested pattern can sometimes still be more readable than a long series of accessors.

## 4. Example of Clear Pattern Composition, Even When Nested

Suppose:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}
```

When the task is to check the coordinate ordering of two corners, a two-level pattern can be very natural:

```java
case Rectangle(
        Point(var x1, var y1),
        Point(var x2, var y2))
        when x1 <= x2 && y1 <= y2 ->
    "Hai góc theo thứ tự hợp lệ"
```

Strengths:

- The structure `Rectangle(Point, Point)` directly expresses the requirement of having two points.
- The variables `x1, y1, x2, y2` are used immediately in the guard; there are no unused variables.
- The guard checks **one idea**: the first corner is not to the right of or below the last corner under the assumed coordinate system.
- The reader can predict what happens when a `Point` is null: the record pattern at that position does not match, so this branch does not run.

The snippet above is an **illustrative `case` label**, which needs to be placed inside an appropriate `switch`. It does not dictate the coordinate system for the entire application; if the `y` axis increases in the opposite direction, the business rule needs to be adjusted.

Using a nested pattern here **is not bad just because there are two pairs of records**. You need to consider whether the depth accurately reflects the information the branch uses.

## 5. Hard-to-Read Example: Mixing Deep Structure with Multiple Policies

Suppose a shipment has:

```java
record Point(int x, int y) {}
record Address(String city, Point location) {}
record Customer(String name, boolean vip) {}
record Shipment(String id, Customer customer, Address address, int parcels) {}
```

Processing requirement: prioritize when the shipment has a non-blank ID, a VIP customer with a valid name, a non-blank city, non-negative coordinates, and a positive parcel count. All remaining shipments are handled in the standard branch.

We *could* write everything in a single `case`:

```java
case Shipment(
        var id,
        Customer(var name, var vip),
        Address(var city, Point(var x, var y)),
        var parcels)
        when id != null && !id.isBlank()
            && name != null && !name.isBlank()
            && vip
            && city != null && !city.isBlank()
            && x >= 0 && y >= 0
            && parcels > 0 ->
    "Ưu tiên: " + id + " / " + name + " @ " + city;
```

The code above is **valid** in a Java 21 `switch` and accurately describes the condition. The *readability* problem begins when a reviewer has to hold many pieces of information in mind at once:

1. Looking at the `Shipment → Customer/Address → Point` tree to know when the pattern matches.
2. Remembering that `Customer(...)`, `Address(...)`, and `Point(...)` all require their corresponding record component to be **non-null**.
3. Tracking the variables `id, name, vip, city, x, y, parcels` and their types.
4. Reading a long guard consisting of multiple rules: ID, name, VIP, city, coordinates, parcel count.
5. Predicting the next branch if a record is missing, if a string is empty, or if a Boolean condition is false.

Each of those rules has its own business meaning. When a new requirement is added, such as "VIP customers are only prioritized in a certain region," the `case` easily gets stretched even longer. This is the time to consider **naming the condition** and keeping the `switch` at the orchestration level.

## 6. Two Ways to Write the Same Behavior: Standalone Java 21 Example

Create the file **`PatternReadabilityDemo.java`**:

```java
public class PatternReadabilityDemo {
    record Point(int x, int y) {}
    record Address(String city, Point location) {}
    record Customer(String name, boolean vip) {}
    record Shipment(String id, Customer customer,
                    Address address, int parcels) {}

    // Approach 1: mix nested deconstruction and all guards into one case.
    static String classifyDense(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Shipment(
                    var id,
                    Customer(var name, var vip),
                    Address(var city, Point(var x, var y)),
                    var parcels)
                    when id != null && !id.isBlank()
                        && name != null && !name.isBlank()
                        && vip
                        && city != null && !city.isBlank()
                        && x >= 0 && y >= 0
                        && parcels > 0 ->
                "Ưu tiên: " + id + " / " + name + " @ " + city;

            case Shipment(var id, var customer,
                          var address, var parcels) ->
                "Thông thường: " + id;

            default -> "Không phải lô hàng";
        };
    }

    // Approach 2: each helper expresses one clear rule.
    static boolean isVipCustomer(Object value) {
        return value instanceof Customer(var name, var vip)
            && name != null
            && !name.isBlank()
            && vip;
    }

    static boolean isValidAddress(Object value) {
        return value instanceof Address(
                var city, Point(var x, var y))
            && city != null
            && !city.isBlank()
            && x >= 0 && y >= 0;
    }

    static boolean isPriority(Shipment shipment) {
        return shipment.id() != null
            && !shipment.id().isBlank()
            && shipment.parcels() > 0
            && isVipCustomer(shipment.customer())
            && isValidAddress(shipment.address());
    }

    static String classifyReadable(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Shipment shipment when isPriority(shipment) ->
                "Ưu tiên: " + shipment.id()
                    + " / " + shipment.customer().name()
                    + " @ " + shipment.address().city();

            case Shipment shipment ->
                "Thông thường: " + shipment.id();

            default -> "Không phải lô hàng";
        };
    }

    // Ensure both classification approaches produce the same result for each input.
    static void compare(Object value) {
        String dense = classifyDense(value);
        String readable = classifyReadable(value);

        if (!dense.equals(readable)) {
            throw new AssertionError(
                "Hai cách phân loại khác nhau: "
                    + dense + " <> " + readable);
        }
        System.out.println(readable);
    }

    public static void main(String[] args) {
        compare(new Shipment(
            "S-01",
            new Customer("An", true),
            new Address("Huế", new Point(1, 2)),
            3));

        compare(new Shipment(
            "S-02",
            new Customer("Bình", false),
            new Address("Huế", new Point(1, 2)),
            3));

        compare(new Shipment(
            "S-03",
            new Customer("Chi", true),
            new Address("Huế", null),
            1));

        compare(new Shipment(
            "S-04",
            null,
            new Address("Huế", new Point(1, 2)),
            1));

        compare(new Shipment(
            "S-05",
            new Customer("Dũng", true),
            new Address("", new Point(1, 2)),
            1));

        compare("abc");
        compare(null);
    }
}
```

Compile with JDK 21 or newer in the directory containing the file:

```bash
javac --release 21 -encoding UTF-8 PatternReadabilityDemo.java
java PatternReadabilityDemo
```

Output:

```text
Ưu tiên: S-01 / An @ Huế
Thông thường: S-02
Thông thường: S-03
Thông thường: S-04
Thông thường: S-05
Không phải lô hàng
Không có dữ liệu
```

**Both approaches are valid**, and in this example they produce the same output for every input. The `compare` method checks practical equivalence before printing. It is **not a formal proof for all possible input values**, but it is a good verification step when refactoring.

### Why can the helper-extracted version be more readable?

In `classifyReadable`, the `switch` only answers "priority shipment, standard shipment, or invalid data?". The condition is named `isPriority`. The helper `isVipCustomer` clarifies the customer condition, while `isValidAddress` handles the address and location structure. Reviewers can open each helper to inspect details when needed, and test them independently.

However, **extracting functions is not always better**. If there is only a simple guard like `x >= 0`, jumping through multiple helpers can reduce directness. Conversely, if the same VIP/address criteria are used in multiple places, naming the rules avoids duplication and reduces the risk of updating one place while forgetting another.

Both functions assume that the `record`s have simple default accessors with no side effects. If a custom accessor behaves differently across calls, changing the order or number of accessor reads during a refactoring can affect behavior. In that case, you must check the data type's contract before claiming equivalence.

## 7. Reading the Results as a Pattern Composition Evaluation

The table below analyzes the inputs in the program:

| Input | Why Not / Why Prioritized? | Result |
| --- | --- | --- |
| `S-01`: VIP customer, valid name/city, point (1,2), 3 parcels | Nested records match; all guard conditions are true | `Ưu tiên: S-01 / An @ Huế` |
| `S-02`: `vip == false` | Structure matches, but guard is false | `Thông thường: S-02` |
| `S-03`: `Address.location() == null` | Nested `Point(...)` does not match | `Thông thường: S-03` |
| `S-04`: `customer == null` | Nested `Customer(...)` does not match | `Thông thường: S-04` |
| `S-05`: city is an empty string | Pattern matches; `!city.isBlank()` is false | `Thông thường: S-05` |
| `"abc"` | Not a `Shipment` | `Không phải lô hàng` |
| `null` | Selector is null, handled by `case null` | `Không có dữ liệu` |

This is a **behavior-based** review, not just a source-code-formatting review. A simplified version is only acceptable if it still properly handles the null branch, missing record components, failing guards, and other input types.

In the `classifyReadable` version, `isVipCustomer` takes `Object` and checks with `instanceof Customer(...)`; when the argument is null, the pattern does not match and the method returns false. `isValidAddress` also takes `Object`; if `location` is null, the nested `Point(...)` does not match. Because of this, `isPriority` does not need to call accessors on missing components.

Key takeaway: **reduce depth at the orchestration site, keep structural details in well-named helpers**. Code becomes easier to evaluate if a helper's name accurately describes the invariant it checks.

## 8. Null Checking: Where Pattern Composition Is Easily Misunderstood

When reviewing nested patterns, distinguish between:

- **The record pattern itself**, such as `Customer(...)` or `Point(...)`, requires the object at that level to be non-null.
- **`var customer` or `var location` inside a record pattern** receives the entire component with its inferred type, and may hold a null value.
- **A null `switch` selector** is a separate case: add `case null` if you want to handle it, because `default` is not a general fallback for null in pattern matching `switch`.

For example:

```java
case Shipment(var id, Customer(var name, var vip),
              var address, var parcels) ->
    ...
```

The branch above requires `customer` to be a non-null `Customer`, but **does not require `address` to be non-null**, because the third component only uses `var address`. If deeper constraints are needed, write `Address(var city, Point(...))` at that position.

A null-safe guard:

```java
case Shipment(var id, var customer, var address, var parcels)
        when customer == null || address == null ->
    "Thiếu thông tin";
```

Here both `customer` and `address` are already bound by the pattern; the `||` guard uses them validly. Do not confuse this with:

```java
// WRONG: variable x on the right-hand side of || is not guaranteed to be bound.
if (value instanceof Point(var x, var y) || x >= 0) {
    // ...
}
```

When `instanceof` is false, the right-hand side of `||` can still be evaluated, so `x` is not guaranteed to be in scope. Conversely, using `&&` is appropriate because conditions on the right-hand side are only evaluated after the pattern matches.

Another issue: `var name` can receive a null string; before calling `name.isBlank()`, the guard needs `name != null`. Extracting a clearly named helper must not break this null-check ordering.

## 9. Branch Ordering and Dominance Affect Readability

In pattern matching `switch`, branches are evaluated in order; a general branch placed too early can shadow a specific branch.

An **intentionally wrong example that does not compile**:

```java
return switch (value) {
    case Shipment shipment -> "Mọi lô hàng";
    case Shipment(var id, Customer(var name, var vip),
                  var address, var parcels) when vip ->
        "VIP"; // Branch shadowed by case Shipment above.
    default -> "Khác";
};
```

`case Shipment shipment` matches every non-null `Shipment`. The nested branch after it is therefore **dominated**. An ordering that is easier to verify:

```java
return switch (value) {
    case Shipment(
            var id, Customer(var name, var vip),
            var address, var parcels) when vip ->
        "VIP";
    case Shipment shipment -> "Mọi lô hàng khác";
    default -> "Khác";
};
```

The two snippets above are **illustrative examples placed inside a method** that has `value` and the relevant records, not standalone programs. If `value` can be null, you must decide how to handle null separately.

Regarding **exhaustiveness**, a `switch` expression needs branches covering all values that can arrive. With an `Object` selector, patterns matching only `Shipment` are not exhaustive, so `default` is usually needed. With a `sealed interface` covering all permitted variants, the compiler can help check exhaustiveness in `switch`; however, **an arbitrary guard is not considered to cover all values of that type**. A general branch for the variant after guarded branches is still valuable.

When reviewing, ask: "If a new message type is added to the `sealed` hierarchy, do I know which branch must handle it?" and "If the VIP guard is false, does the next branch catch the shipment?" These two questions often reveal issues more clearly than merely counting lines.

## 10. When to Keep Patterns Inline, When to Extract?

| Situation | Usually More Readable Choice | Reason |
| --- | --- | --- |
| Only need two components and one comparison | Keep record pattern and guard inline | The entire intent fits on one screen |
| Nested record structure matches the domain model directly, using many leaf values | Keep nested record pattern with clear indentation | Directly expresses structural relationships |
| Guard consists of multiple distinct policies (age, status, region, amount...) | Extract a helper named after the rule | Separates business logic from branch orchestration |
| The same condition appears in multiple `case`s | Use a shared, pure, tested check function | Reduces duplication and avoids missed updates |
| A branch uses only one component of a deep record | Deconstruct at a shallower level or call an accessor | Avoids binding many unused variables |
| Need different error messages for each missing field | Split into multiple branches or separate validation | Reader clearly sees the branch handling each error |
| Many `sealed` variants | Use explicit `switch` over each variant, small guards | Leverages compile-time exhaustiveness checking |

A tip when reviewing: try **reading the statement aloud**. If you can say "For a shipment with complete data, if the customer is VIP and the address is valid then prioritize; otherwise handle normally" without having to mention seven variable names at once, the code is communicating intent well.

## 11. Workflow for Reviewing and Refactoring Without Changing Behavior

1. **Write down inputs and outputs.** Which branch handles `null`, other types, null components, a false guard, and valid data?
2. **Draw the boundary between structure and rules.** The `Record(...)` part answers "what is the shape?"; `when` answers "what conditions must the values satisfy?".
3. **Read from outside → inside.** Identify each component according to the record declaration; do not infer based on variable names in the pattern.
4. **Count variables actually used.** If many components are extracted just to check one flag, try a shallower pattern or a helper.
5. **Try naming the condition.** A name like `isPriority` is only useful when it has a clear contract; if the name is generic like `check` or `valid`, consider making it more specific.
6. **Check `case` ordering.** Guarded/specific branches must be evaluated before broad catch-all branches; do not create dominance.
7. **List edge cases in a table.** At minimum: full match, false guard, null at each nested record, null/empty string, null selector, other type.
8. **Compare results before and after.** Run the same set of inputs and verify expected outputs/exceptions, especially when there are custom accessors or order-dependent checks.

Extracting functions also has a cost: more navigation steps and in some cases reading the same data twice. Therefore, the goal is a **balance** between structure visible in `case` and business rule names in helpers. No single format always wins.

When refactoring logic with side effects, be cautious: guards may be evaluated in order, and custom accessors can throw exceptions or have side effects. The illustrative example in this lesson uses records with default accessors, making behavior comparison clear. If an accessor throws an exception during deconstruction, Java may report a `MatchException` wrapping the root cause; do not mask error differences with a helper that catches exceptions arbitrarily.

## 12. Common Code Review Comment Mistakes

| Too-Vague Comment | More Helpful Comment |
| --- | --- |
| "This pattern is too long." | "The branch deconstructs `Shipment → Address → Point`, but only needs to know whether coordinates are valid; try introducing `isValidAddress` and checking null on `Point` separately." |
| "Add `default`." | "The selector is `Object`; besides `Shipment` there are other types. Add a branch for other types and check the null-selector policy." |
| "Use patterns everywhere to be modern." | "The branch only needs `shipment.id()`; a type pattern `Shipment s` can be easier to understand than a four-component record pattern." |
| "Just swap the branches." | "`case Shipment s` is shadowing `Shipment(...) when vip`. Move the VIP branch first and add tests for VIP/non-VIP." |
| "Null will probably never happen." | "`Customer(...)` does not match when `customer == null`; define the fallback branch or disallow null in the constructor." |
| "Extract it into any function." | "The condition has three independent rules; extract `isVipCustomer` and `isValidAddress` for clear naming and testing." |

A good review points out the **location**, **specific risk**, **reasoned suggestion**, and **how to verify**. Beautifying indentation without checking null, guards, and dominance does not guarantee the code is easier to understand behaviorally.

## 13. Practice Exercises

**Exercise 1 — Evaluate two ways of writing.** Given `record Pair(Point first, Point second) {}`, to check that both x-coordinates are positive, compare:

```java
// Option A: deconstruct directly.
case Pair(Point(var x1, var y1), Point(var x2, var y2))
        when x1 > 0 && x2 > 0 ->
    "Hai x dương";

// Option B: keep both Points intact.
case Pair(var first, var second)
        when first != null && second != null
            && first.x() > 0 && second.x() > 0 ->
    "Hai x dương";
```

These are two **illustrative `case` label snippets representing two implementation approaches**, not placed side by side as duplicate branches in one `switch`. Both achieve the same goal when `Point` has default accessors; Option A clearly shows the nested structure, while Option B has more null checks but does not extract unused `y1` and `y2`. Which approach would you choose for a newcomer on the team? Explain based on the branch's purpose.

**Exercise 2 — Find the dominance error.** Why does placing `case Shipment s -> ...` before `case Shipment(...) when ... -> ...` make the latter branch unreachable? Rewrite the order and point out the case where the guard is false.

**Exercise 3 — Design a test suite.** For `PatternReadabilityDemo`, add three scenarios: `id == null`, `Customer.name() == null`, and `parcels == 0`. Predict the results of both classification functions and run them to verify.

**Exercise 4 — Weigh refactoring.** If `isPriority` adds the requirements that the city belongs to a supported list and the point lies within a certain region, would you keep all conditions inline or extract `isServiceableDestination`? State your reasoning based on readability, testing, and future modifiability.

**Exercise 5 — Use the review table.** Read a pattern composition in your own project (if any) and answer: intent, depth, unused variables, `case` ordering, null possibility, guards, fallback branch, and the most important test. Do not modify the code before understanding its actual behavior.

## 14. Key Takeaways

**Pattern composition is readable when the structure is expressed just enough, conditions have clear names, paths through branches are predictable, and behavior remains unchanged after refactoring.** With nested record patterns, type/record checks happen across levels; `var` receives components, and `when`/`&&` filter values further. Do not only look for the shortest expression: look for the expression that helps others understand **why a branch is chosen** and **what happens if the data changes**.

References:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
