# Overly Deeply Nested Record Patterns: Pitfall Signs and How to Refactor in Java 21

## 1. The Real-World Problem

Record patterns allow Java to perform type checking and **deconstruct** data directly inside `instanceof` or a `case` label. With a domain model that has nested records, you can read values directly from deep layers:

```java
record Point(int x, int y) {}
record Address(String city, Point location) {}
record Buyer(String name, int level) {}
record Purchase(String id, Buyer buyer, Address destination, long total) {}
```

A pattern like the following is valid:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total) when level >= 2 && total >= 1_000L ->
    "Đơn ưu tiên: " + id;
```

It represents the trees `Purchase → Buyer` and `Purchase → Address → Point`, while extracting seven variables at the same time. When this is genuinely the structure that needs to be expressed, the syntax is fairly concise. However, if you add a series of conditions, fallback branches, null checks, and other system accesses, **overly deeply nested record patterns become a readability and maintainability pitfall**.

Readers may struggle to answer all of these at once:

- Which record layers must the object match to enter the branch?
- At which layer does a null component cause the pattern to fail to match?
- Has the `when` guard been evaluated yet?
- What type does each variable have, what scope is it in, and where is it used?
- If a child layer does not match, which branch will handle that data?
- Does modifying a business rule force updating many similar patterns?

**There is no Java rule prohibiting patterns nested three, four, or more levels deep.** "Too deep" is a design judgment based on clarity, resilience when the model changes, testability, and the relevance of each layer to the branch's purpose.

This article focuses on **common pitfalls**, how to recognize them, their concrete consequences, and how to simplify them while preserving behavior.

**Version:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have both been standard features since **Java 21**. The runnable examples in this article use JDK 21+ and do not require `--enable-preview`. `record` has been a standard feature since Java 16, but record pattern syntax such as `Point(var x, var y)` is not available in standard Java 17.

## 2. Reading a Nested Record Pattern Correctly from Outside In

Consider the pattern:

```java
Purchase(
    var id,
    Buyer(var name, var level),
    Address(var city, Point(var x, var y)),
    var total
)
```

The corresponding matching structure:

```text
Purchase                          ← outermost layer
├── id: String                    ← var id
├── buyer: Buyer                  ← Buyer(...)
│   ├── name: String              ← var name
│   └── level: int                ← var level
├── destination: Address          ← Address(...)
│   ├── city: String              ← var city
│   └── location: Point           ← Point(...)
│       ├── x: int                ← var x
│       └── y: int                ← var y
└── total: long                   ← var total
```

How to reason about it:

1. The selector value must be a non-null `Purchase`.
2. `Buyer(...)` requires the `buyer` component to match a non-null `Buyer` object.
3. `Address(...)` requires `destination` to be a non-null `Address`.
4. `Point(...)` requires `destination.location` to be a non-null `Point`.
5. Each `var` binds its component to a variable with **the type inferred from the record declaration**.
6. Only after the **entire pattern** matches is the branch's `when` guard evaluated.

This is a **structural check**; it does not automatically validate the buyer name, city name, or amount against business policies. For example, `var name` receives the `String` value of the component and **can receive null**. Conversely, `Buyer(...)` is a record pattern, so it does not match if the corresponding component is null.

Seeing many parentheses does not mean the compiler will definitely run slowly. The primary risks to watch out for first are **cognitive complexity** and **processing branches that are easily missed**. Performance evaluation must be based on measurements with realistic workloads.

## 3. Six Signs That a Pattern Is Nested Too Deeply

| Sign | What the reader has to do | Possible consequence |
| --- | --- | --- |
| Many layers just to use one leaf value | Trace the entire record tree to find one flag | Code is tightly coupled to unrelated structure |
| Many unused `var` variables | Remember redundant component names and positions | Hard to review; wrong component order is easily missed |
| Long guard with multiple unrelated rules | Decode both the record tree and Boolean logic | Hard to see key conditions and null-safety points |
| Branches repeating a nested pattern | Compare multiple nearly identical trees | Easy to miss updating a branch when the model changes |
| Fallback depending on unpredictable null layers | Distinguish pattern failure from guard false | Data that is valid in another sense may enter an unexpected branch |
| Small domain model change causes many pattern edits | Update many `case`s with new component counts | Increased maintenance cost and regression testing |

These signs are **not necessarily compile errors**. A short nested pattern can be better than multiple accessor calls, but when conditions and structure obscure the *intent of the branch*, you should consider refactoring.

### Example: only needing a VIP buyer, yet checking the entire address

```java
// Assume Purchase, Buyer, Address, Point are already declared.
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total) when level >= 2 ->
    "Khách hạng cao";
```

If the goal is **only** to check `level >= 2`, the pattern above unnecessarily depends on `destination` and `location`. A `Purchase` with a high-tier buyer whose address is currently missing `Point` **will not match**, even though the logic for identifying buyer tier does not need coordinates.

A choice closer to the intent:

```java
case Purchase(var id, Buyer(var name, var level),
              var destination, var total)
        when level >= 2 ->
    "Khách hạng cao";
```

Or if you want to dispatch at the entity level:

```java
case Purchase p when isHighTierBuyer(p.buyer()) ->
    "Khách hạng cao";
```

The last two snippets need to be placed inside a `switch` with appropriate helpers/components; they are **illustrative snippets**, not standalone programs. The key point: when you do not need address data, do not add address-matching conditions that the problem does not require.

## 4. Distinguishing Between "Pattern Does Not Match" and "Guard Is False"

This is the most common source of bugs in nested record patterns.

Example:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total)
        when level >= 2 && total >= 1_000L ->
    "Ưu tiên";
```

Different inputs can lead to different outcomes:

| Data | Does the pattern match? | Is the guard evaluated? |
| --- | --- | --- |
| `buyer == null` | No, stops at `Buyer(...)` | No |
| `destination == null` | No, stops at `Address(...)` | No |
| `destination.location() == null` | No, stops at `Point(...)` | No |
| `buyer.level() == 1`, all child records present | Yes | Yes, but returns false |
| `buyer.level() == 2`, `total >= 1000`, all child records complete | Yes | Yes, returns true |

**In terms of semantics:** null in a **nested record pattern** causes the entire pattern not to match; null in a component captured by `var` can still be a bound value. The `when` guard is not executed when the pattern fails beforehand.

Reading fallback branches clearly is important because authors can easily assume a null-check guard can "rescue" a child pattern:

```java
// INTENTIONALLY WRONG BY DESIGN: when location is null,
// Point(var x, var y) already fails to match,
// so the trailing guard cannot run to handle null.
case Purchase(var id, var buyer,
              Address(var city, Point(var x, var y)),
              var total)
        when city == null ->
    "Thành phố thiếu";
```

The `city == null` guard can work when Address/Point exist and city is null. **It does not handle the case where Point is null**, even though the author might think it does.

To check for a missing Point, stop at a shallower level:

```java
case Purchase(var id, var buyer,
              Address(var city, var location),
              var total)
        when location == null ->
    "Thiếu tọa độ";
```

This way, `var location` can hold null; only after the Address pattern succeeds does the guard decide that coordinates are missing. Note: if `destination == null`, `Address(...)` itself still does not match. To handle a null destination as well, you need to capture the component with `var destination` at the Purchase level.

## 5. Overly Long Guards Obscure the Reason for Choosing a Case

A deep nested pattern combined with a long guard often mixes two different kinds of checks:

- **Structural checks**: whether the required child records are present.
- **Business policies**: valid name, customer tier, allowed region, order value, risk threshold, etc.

Example:

```java
case Purchase(
        var id,
        Buyer(var name, var level),
        Address(var city, Point(var x, var y)),
        var total)
        when id != null && !id.isBlank()
            && name != null && !name.isBlank()
            && level >= 2
            && city != null && !city.isBlank()
            && x >= 0 && y >= 0
            && total >= 1_000L ->
    "Ưu tiên: " + id;
```

This code may be correct, but the reader has to trace through **multi-level structure + seven variables + many conditions**. As business rules grow, it is very easy to add a check in the wrong branch or introduce a guard with hard-to-spot side effects.

One way to simplify is to give the policy a name:

```java
case Purchase purchase when isPriority(purchase) ->
    "Ưu tiên: " + purchase.id();
```

`isPriority` can be broken down into understandable sub-checks: buyer, destination, total amount, ID. The `switch` then answers the question at the business level, while the helper takes responsibility for the details.

**Do not name helpers things like `check1`, `validateStuff`, or `doThing`**: vague names merely move the difficulty from one long expression across multiple files. A good helper should have a clear contract (inputs, output, null handling) and be easy to test.

## 6. Complete Java 21 Program: Deep Version vs. Readable Version

This example uses the same domain model with two classification approaches:

- `classifyDeep` nests record patterns inside a `switch` branch.
- `classifyReadable` keeps the dispatch at the `Purchase` level, calling `isPriority` to check structure and conditions in two smaller groups.
- The `verify` method compares **both versions** and checks the expected result. The goal is to show that a refactor can preserve behavior on representative inputs.

Create the file **`DeepRecordPatternDemo.java`**:

```java
public class DeepRecordPatternDemo {

    record Point(int x, int y) {}

    record Address(String city, Point location) {}

    record Buyer(String name, int level) {}

    record Purchase(String id, Buyer buyer,
                    Address destination, long total) {}

    static boolean nonBlank(String text) {
        return text != null && !text.isBlank();
    }

    // Version 1: one deep pattern and one long guard.
    static String classifyDeep(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Purchase(
                    var id,
                    Buyer(var name, var level),
                    Address(var city, Point(var x, var y)),
                    var total)
                    when nonBlank(id)
                        && nonBlank(name)
                        && level >= 2
                        && nonBlank(city)
                        && x >= 0 && y >= 0
                        && total >= 1_000L ->
                "Ưu tiên: " + id;

            case Purchase(var id, var buyer,
                          var destination, var total)
                    when buyer == null || destination == null ->
                "Thiếu dữ liệu: " + id;

            case Purchase(var id, var buyer,
                          var destination, var total) ->
                "Thông thường: " + id;

            default -> "Không phải Purchase";
        };
    }

    // Check conditions by group, can be unit-tested independently.
    static boolean isPriority(Purchase purchase) {
        if (!(purchase.buyer() instanceof Buyer(var name, var level))) {
            return false;
        }

        if (!(purchase.destination() instanceof
                Address(var city, Point(var x, var y)))) {
            return false;
        }

        return nonBlank(purchase.id())
            && nonBlank(name)
            && level >= 2
            && nonBlank(city)
            && x >= 0 && y >= 0
            && purchase.total() >= 1_000L;
    }

    // Version 2: each case represents a clearly meaningful situation.
    static String classifyReadable(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Purchase purchase when isPriority(purchase) ->
                "Ưu tiên: " + purchase.id();

            case Purchase purchase when
                    purchase.buyer() == null
                    || purchase.destination() == null ->
                "Thiếu dữ liệu: " + purchase.id();

            case Purchase purchase ->
                "Thông thường: " + purchase.id();

            default -> "Không phải Purchase";
        };
    }

    static void verify(Object value, String expected) {
        String deep = classifyDeep(value);
        String readable = classifyReadable(value);

        if (!deep.equals(readable) || !deep.equals(expected)) {
            throw new AssertionError(
                "Không khớp: " + deep + " / " + readable);
        }
        System.out.println(readable);
    }

    public static void main(String[] args) {
        verify(new Purchase(
            "P-1",
            new Buyer("An", 2),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Ưu tiên: P-1");

        verify(new Purchase(
            "P-2",
            new Buyer("Bình", 1),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thông thường: P-2");

        verify(new Purchase(
            "P-3",
            null,
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thiếu dữ liệu: P-3");

        verify(new Purchase(
            "P-4",
            new Buyer("Chi", 2),
            new Address("Huế", null),
            1_200L), "Thông thường: P-4");

        verify(new Purchase(
            "P-5",
            new Buyer(null, 2),
            new Address("Huế", new Point(1, 2)),
            1_200L), "Thông thường: P-5");

        verify(new Purchase(
            "P-6",
            new Buyer("Dũng", 2),
            new Address("", new Point(1, 2)),
            1_200L), "Thông thường: P-6");

        verify(new Purchase(
            "P-7",
            new Buyer("Em", 2),
            new Address("Huế", new Point(1, 2)),
            999L), "Thông thường: P-7");

        verify("abc", "Không phải Purchase");
        verify(null, "Không có dữ liệu");
    }
}
```

Compile and run from the directory containing the file using **JDK 21 or newer**:

```bash
javac --release 21 -encoding UTF-8 DeepRecordPatternDemo.java
java DeepRecordPatternDemo
```

Expected output:

```text
Ưu tiên: P-1
Thông thường: P-2
Thiếu dữ liệu: P-3
Thông thường: P-4
Thông thường: P-5
Thông thường: P-6
Thông thường: P-7
Không phải Purchase
Không có dữ liệu
```

### 6.1. Tracing Each Case's Outcome

| Input | What happens in the deep version? | Why do both versions produce the same result? |
| --- | --- | --- |
| P-1: buyer level 2, non-empty city, Point (1,2), total 1200 | All child records match; guard is true | `isPriority` also returns true |
| P-2: buyer level 1 | Pattern matches; guard `level >= 2` is false | Helper returns false, enters standard branch |
| P-3: `buyer == null` | `Buyer(...)` does not match; second branch catches null | Helper returns false; missing-data branch also catches null |
| P-4: `Address.location == null` | `Point(...)` does not match; missing-data branch does not catch it because Address still exists | Helper returns false; enters standard branch |
| P-5: `Buyer.name == null` | Pattern matches; `nonBlank(name)` is false | Helper also uses `nonBlank(name)` |
| P-6: `Address.city == ""` | Pattern matches; `nonBlank(city)` is false | Helper also checks city |
| P-7: total 999 | Pattern matches; threshold guard 1000 is false | Helper also checks total |
| `"abc"` | Not a `Purchase` | Both enter default |
| `null` | `case null` | Both handle null explicitly |

**Special note on P-4:** the `Address` object is present, but `Point` is missing. According to the branches written, it is treated as **standard**, not "missing data", because the missing-data branch only checks buyer/destination at the Purchase level. This is a **demo rule to preserve equivalent behavior**, not a suggestion that missing coordinates are always acceptable in a real domain.

If the application requires classifying missing coordinates as an error, **change the policy intentionally**, add tests, and update both versions accordingly. Do not silently change behavior during a refactor meant only to improve readability.

### 6.2. Why Is the Helper-Extracted Version Easier to Review?

The second `switch` exposes three situations at the same level:

1. Purchase satisfies the priority policy.
2. Purchase is missing Buyer or Address.
3. Remaining Purchases.

The `isPriority` helper still needs to check the child records, but it separates them by group and returns `false` early if a required group is absent. Reviewers can inspect this logic separately without having to trace through multiple `case` branches.

**Do not assume every refactor is automatically equivalent.** The example above uses records with **default accessors and no side effects**. A record with custom accessors that throw exceptions or change results between calls can make deconstruction behave differently from direct accessor calls. Changing access positions or call counts in such code requires verifying the specific behavior.

## 7. Alternatives to Reduce Depth

### A. Use a type pattern followed by a helper

Instead of unpacking the entire tree directly inside `case`:

```java
case Purchase purchase when isPriority(purchase) ->
    "Ưu tiên: " + purchase.id();
```

This is good when the business rule is long, repeated, or needs testing. The helper does not have to live in a separate file; a clearly named `private static` method in the same class is often sufficient.

### B. Deconstruct only to the layer actually needed

If you need to process the entire `destination`, use:

```java
case Purchase(var id, var buyer, var destination, var total) ->
    describeDestination(destination);
```

`var destination` infers the `Address` type from the component. It **can be null**, so `describeDestination` must have a null contract or the caller must check it. This approach avoids requiring `Point` to exist when the action only needs Address metadata.

### C. Use a nested pattern with appropriate depth

If a rule genuinely relates to `Buyer` but does not involve `Address.Point`:

```java
case Purchase(var id, Buyer(var name, var level),
              var destination, var total)
        when level >= 2 ->
    "Buyer hạng cao: " + id;
```

This is an inline example that remains clear. **Do not avoid record patterns at all costs**: the right depth is the depth the reader needs to see the important condition right at the branching point.

### D. Enforce invariants in the constructor when appropriate

If every `Purchase` must have a buyer, destination, location, and valid field values, the constructor can reject invalid data early. A small example:

```java
record Address(String city, Point location) {
    Address {
        java.util.Objects.requireNonNull(location, "location");
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city required");
        }
    }
}
```

This is an **illustrative declaration snippet**, not a replacement for the `Address` record in the main program. When constructors protect invariants, data consumers need fewer null branches.

However, **do not alter the domain contract just to reduce the number of cases**. A domain that allows temporarily missing addresses or partial input cannot simply forbid null without considering data creation/editing flows.

### E. Name the condition instead of adding more layers

Replacing a `when` clause with ten conditions by `when isPriority(purchase)` is only worthwhile if the name accurately expresses the policy. You can further split it into `hasEligibleBuyer`, `hasServiceableAddress`, or `meetsMinimumAmount`, but there is no need to create a series of pointless one-line helpers.

## 8. Guards, Nulls, and Flow Scoping: Three Things to Preserve When Refactoring

### 8.1. Scope of pattern variables

`x` and `y` in `Point(var x, var y)` can only be used where the compiler knows the pattern matched, such as the `when` guard and that `case` body. They do not automatically become variables in the next `case`.

In an `if`, `&&` short-circuits:

```java
if (value instanceof Purchase(var id, var buyer,
                              var destination, var total)
        && buyer != null && destination != null) {
    System.out.println(id);
}
```

The pattern binds `buyer` and `destination`, and then the condition checks for null. Do not use them on the right-hand side of `||` after `instanceof` when the pattern might not have matched.

### 8.2. Null in a child record differs from null in a `var` component

`Buyer(var name, var level)` does not match when buyer is null. However, `var name` can bind a null `String` if the Buyer record exists and its name component is null.

Therefore:

```java
case Purchase(var id, var buyer, var destination, var total)
        when buyer == null || destination == null ->
    "Thiếu dữ liệu";
```

can handle a null Buyer or Address. Whereas:

```java
case Purchase(var id,
              Buyer(var name, var level),
              Address(var city, Point(var x, var y)),
              var total) when name == null ->
    "Thiếu tên buyer";
```

cannot run if `buyer`, `destination`, or `location` is null, because those nested record patterns already failed beforehand.

### 8.3. Dominance and fallback branches

For the same `Purchase` type, place the specialized guarded case before the unguarded case:

```java
// Correct order:
case Purchase p when isPriority(p) -> "Ưu tiên";
case Purchase p -> "Thông thường";
```

An **intentionally wrong example that does not compile**:

```java
case Purchase p -> "Thông thường";
case Purchase p when isPriority(p) -> "Ưu tiên"; // Dominated
```

The first `case Purchase p` already catches every non-null Purchase, so the following branch can never be selected. Reducing depth must not break the priority order of conditions or the exhaustiveness of a `switch` expression.

## 9. When Is a Nested Record Pattern a Good Choice?

A nested pattern is considered **useful** when it directly expresses the structural feature needed for classification, uses few variables, has a short guard, and does not obscure the policy.

For example, checking a rectangle with two start/end points:

```java
record Rectangle(Point first, Point second) {}

// Illustrative case label in switch:
case Rectangle(Point(var x1, var y1), Point(var x2, var y2))
        when x1 <= x2 && y1 <= y2 ->
    "Hai điểm theo đúng thứ tự";
```

Here, the fact that both components are non-null `Point`s is **an essential part of the condition**, and all leaf variables are used. A two-level nested pattern reveals the data relationship more clearly than a long chain of accessors.

Conversely, if the condition only needs `rectangle.first() != null`, unpacking all of `x1/y1/x2/y2` is redundant and can drop cases that should have been handled.

**Rule of thumb:** do not count parentheses mechanically. Compare the **depth required by the business logic** against the **actual depth of the syntax**.

## 10. Risks When Changing the Domain Model and Using Custom Accessors

Record patterns depend on **component order** and **declared types**. Changing a component in a public API record can affect constructors, accessors, and all `Record(...)` patterns with the corresponding number of components. If the same nested pattern is duplicated across many branches, the amount of change increases.

Establishing a data-unpacking boundary via helpers or domain methods reduces the number of places to update when records change. However, helpers also need to be designed with clear contracts; simply pushing a nested tree into an arbitrary method does not solve coupling.

In addition, records can declare custom accessors. During deconstruction, calling an accessor is not guaranteed to be side-effect-free; an accessor can throw an exception. **Do not assume that switching from a record pattern to a chain of accessors will always preserve the order and number of calls.** If the system has unusual accessors, you must test results, exceptions, and side effects. For value objects, simple and stable accessors are usually the easier-to-understand design.

## 11. Safe Refactoring Workflow

1. **Write down the purpose of each case.** For example, "which orders get priority?" rather than "which components can be unpacked?".
2. **Draw or read the record tree.** Mark the layers actually needed for the business question.
3. **Audit used variables.** Do not deconstruct components that play no role in the condition or result.
4. **Separate structure from policy.** Record patterns check shape; `when`/helpers check data.
5. **Give helpers meaningful names.** A name like `isPriority` clarifies policy better than a long Boolean chain.
6. **Identify null branches.** Test null at Buyer, Address, Point, and string fields; distinguish pattern failure from guard false.
7. **Check case ordering.** Guarded cases come before broader cases; do not create dominance.
8. **Compare before/after.** Test every important path, including outputs, exceptions, and side effects if any.
9. **Re-read the entire switch.** Can a newcomer state why a branch is chosen without tracing through five records and many pairs of parentheses?
10. **Optimize performance only with data.** Shorter patterns or fewer helpers do not by themselves prove better speed.

For real-world business systems, the test suite should include valid inputs, empty fields, null record layers, fallback branches, other types, a null selector, and amount/threshold boundaries.

## 12. Common Mistakes When "Fixing" Overly Deep Patterns

| Wrong fix | Problem | Better approach |
| --- | --- | --- |
| Removing `Point(...)` from the pattern without checking logic | Branch may start catching inputs with null Point | Decide the null Point policy and test behavior |
| Putting all conditions into a helper named `check` | Only hides complexity, intent remains unclear | Name after the domain, group conditions |
| Treating `var address` as a guaranteed non-null address | `var` can receive a null component | Add a null guard or constructor invariant |
| Assuming a null guard runs before nested record patterns | Once the pattern fails, the guard is not evaluated | Capture the component at a shallower level to handle null |
| Placing a general case before a guarded case | The later case is dominated | Order specific cases first |
| Using record patterns to validate the entire domain | Matching does not replace invariants/validation | Constructors or application validation have their own responsibilities |
| Extracting a helper and changing custom accessor call order | May change exceptions/side effects | Check the record contract and test |
| Testing only the successful priority case | Misses null, guard false, and fallback | Write a scenario table like in Section 6 |
| Assuming more layers always slow down runtime | No evidence from code alone | Run appropriate benchmarks if there is real doubt |
| Avoiding nested patterns altogether | Loses directness when structure itself is the business rule | Keep patterns just deep enough, concise, and readable |

## 13. Exercises and Suggested Answers

**Exercise 1 — Count structural conditions.** For `Purchase(var id, Buyer(var name, var level), Address(var city, Point(var x, var y)), var total)`, which record components must be non-null for the pattern to match? Answer: **Purchase, Buyer, Address, and Point** must all be non-null instances of their respective records. `id`, `name`, and `city` can be null if they are only captured with `var`.

**Exercise 2 — Reduce depth.** The rule only requires a buyer of level 2 or higher. Rewrite the pattern so it does not depend on destination/Point. Hint: `Purchase(var id, Buyer(var name, var level), var destination, var total) when level >= 2`.

**Exercise 3 — Distinguish null.** Given a Purchase with a valid Buyer, a valid Address, but `Address.location == null`, is the guard of the priority branch in `classifyDeep` evaluated? Answer: **no**; the nested `Point(...)` fails to match.

**Exercise 4 — Verify equivalence.** Run `DeepRecordPatternDemo.java`. Add inputs with `destination == null`, `id == null`, `Point(-1, 2)`, and total equal to 1000. Predict the same output from both classification methods.

**Exercise 5 — Intentionally change policy.** A new business rule requires "null location must report missing data". Point out why the two original versions do **not** do this for P-4. Update the helper/fallback branch and verify that P-4 is classified under the new category, without treating this as a behavior-preserving refactor.

**Exercise 6 — Name the policy.** If you add checks for serviceable region, risk level, and account status, would you keep everything in `when` or extract `isPriorityPurchase`? Explain based on rule count, testing, and likelihood of change.

**Exercise 7 — Review.** Find a pattern-matching `switch` in your project and record: nesting depth, number of variables actually used, guards, fallback, null at each layer, dominated branches (if any), and two tests to add. Do not modify the code before determining its behavioral contract.

## 14. Summary

**Overly deeply nested record patterns** are not a syntax error, but a design flaw that appears when the pattern tree is longer than the branch needs, hiding matching conditions, increasing coupling, and making null/guard/fallback handling harder to manage.

How to handle it:

- Deconstruct only the layers **actually needed** to make the decision.
- Distinguish **nested record patterns that require non-null type matching** from **`var` capturing a potentially null component**.
- Place complex policies in clearly named helpers; keep `switch` at the right level of dispatch/classification.
- Preserve null handling, case ordering, dominance, and exceptions when refactoring.
- Use before/after comparison tests; do not guess that a shorter expression is definitely equivalent.

### References

- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
