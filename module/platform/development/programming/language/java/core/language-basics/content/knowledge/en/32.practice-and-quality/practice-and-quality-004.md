# Commenting Reasons and Documenting Methods When Needed (Java 17+)

## 1. Purpose of comments and documentation

Java code needs to be clear enough for readers to understand **what the program is doing**; comments and method documentation help explain things that are **hard to infer from code alone**: why a decision was made, internal assumptions, limits, the caller contract, side effects, and error behavior.

Practical principles:

- **Name variables, classes, and methods clearly first.** `calculateTotal()` is easier to understand than `calc()`, and `isEligible` is clearer than `flag`.
- **Comment "why" where a decision is non-obvious**, such as a business threshold or the reason for a half-open interval. Do not paraphrase every line of code in prose.
- **Use Javadoc when a method needs to describe a contract for callers**, especially for public APIs, conditional behavior, constrained parameters, special return values, or predictable exceptions.
- **Keep documentation accurate to the code.** A wrong comment is more dangerous than no comment: it misleads maintainers into trusting behavior that no longer exists.
- **Do not replace validation and good names with long comments.** Comments do not execute, do not validate data, and do not guarantee invariants hold.

This lesson focuses on core Java code and method-level documentation. Javadoc publishes the *contract*, while inline explanations inside a method body preserve non-obvious *design rationale*.

## 2. Three forms of Java comments

Java supports three main comment forms:

| Type | Syntax | When to use |
| --- | --- | --- |
| Single-line | `// content` | Brief explanation right before a decision |
| Multi-line | `/* content */` | Short multi-line note; avoid long blocks that repeat code |
| Javadoc | `/** content */` | Structured documentation for a class, method, constructor, or appropriate member |

Illustrative example **inside a method**, not yet a file with `main`:

```java
// The remainder below one points tier is not converted.
long basePoints = amountVnd / 10_000L;

/*
 * Under this contract, the result is capped according to the threshold
 * previously decided in the product policy.
 */
long limitedPoints = Math.min(basePoints, 500L);
```

The compiler ignores `//` and `/* ... */` comments when parsing the program. However, the **`javadoc`** documentation tool reads `/** ... */` blocks and generates HTML documentation.

Do not write `//` inside a string like `"https://example.org"` thinking it starts a comment: inside a string literal, `//` is just text characters. Do not nest `/* ... */` inside another `/* ... */` because Java does not support nested block comments.

## 3. Comment "why", do not repeat "what"

### Redundant comments

```java
count++;               // Increment count by one.
price = price * 2;     // Multiply price by two.
return price;          // Return price.
```

The text after `//` merely restates the syntax the reader already sees. If every line has comments like this, code review slows down without adding understanding.

### Comments that preserve valuable rationale

```java
// Only award points for each full 10,000 VND tier;
// rounding up would grant points for an incomplete tier.
long basePoints = amountVnd / 10_000L;
```

Here, integer division might look like "accidentally dropping the fractional part." The comment explains why integer division **must** be used: it is the points policy, not a rounding bug.

Another example:

```java
// Half-open interval [start, end) avoids double-counting the shared boundary
// when joining two consecutive shifts [9:00, 10:00) and [10:00, 11:00).
return minute >= startInclusive && minute < endExclusive;
```

A reader immediately sees what the expression does, but may not know why `< endExclusive` is used instead of `<= endExclusive`. The comment preserves the design decision so future edits do not accidentally introduce a boundary bug.

**Comment quality test:** If removing a comment still leaves the reader fully understanding the reason from the method name and expression, that comment is likely unnecessary. If removing it makes someone likely to break an important rule by mistake, the comment should stay.

## 4. Javadoc is the method's contract

Javadoc starts with `/**` and is placed **immediately before the declaration** it describes. Typically, method documentation has a concise summary sentence, followed by important constraints and tags for the caller.

```java
/**
 * Calculates loyalty points based on order amount.
 *
 * <p>Every full 10,000 VND earns one base point. Members
 * receive double points when the order reaches at least 100,000 VND.
 * The result does not exceed 500 points.
 *
 * @param amountVnd order amount in VND, non-negative
 * @param member true if the customer is a member
 * @return points awarded, from 0 to 500
 * @throws IllegalArgumentException if amountVnd is negative
 */
public static int calculatePoints(long amountVnd, boolean member) {
    // The full method body is shown in the example below.
    return 0;
}
```

The snippet above **only illustrates Javadoc structure**; the body returning `0` is a placeholder showing method shape, not the implementation of the described policy. Use the complete version in section 5 to compile and run. Never leave such a dummy body in production code.

Commonly used tags:

| Tag | What to write | When to use |
| --- | --- | --- |
| Opening description `/** ... */` | What the method means and main contract conditions | Whenever a method needs documentation |
| `@param name` | Meaning, unit, and bounds of each parameter | When documenting parameters |
| `@return` | Meaning of return value, bounds, sentinel if any | For methods that return a value |
| `@throws ExceptionType` | Exception type and the condition that triggers it | When callers need to know error conditions |
| `@see Type#method(...)` | Reference to a related API | When cross-references are helpful |
| `@since` | API version where it was introduced | For versioned APIs |
| `@deprecated` | Explanation of old API and its replacement | When an API is deprecated |

**Distinguishing `@throws` and `throws`:** `@throws` is a **documentation tag** inside a comment; `throws IOException` is **Java syntax** in the method signature declaring checked exceptions that may be thrown. Writing `@throws IOException` does not replace the `throws IOException` clause required by the compiler.

Each `@param` must match the actual parameter name. If you rename `amountVnd` to `orderValue`, update the documentation too. In Javadoc, HTML-like characters must be handled carefully: prefer `{@code >=}`, `{@code <}`, or `&lt;` in Javadoc text to avoid markup parsing errors. `{@code ...}` is generally well suited for short code snippets.

## 5. Complete Java 17+ program: loyalty points policy

Create the file **`LoyaltyPolicy.java`**:

```java
/**
 * Loyalty points rules for orders, using VND as the currency unit.
 */
public final class LoyaltyPolicy {
    private LoyaltyPolicy() {
        // Prevent instantiation of utility class.
    }

    /**
     * Calculates loyalty points awarded for an order.
     *
     * <p>Every full 10,000 VND grants one base point.
     * Members receive double points starting from 100,000 VND.
     * Maximum points per order is 500.
     *
     * @param amountVnd order total, in VND, must be non-negative
     * @param member true if the buyer is a member
     * @return points for the order in the range 0 to 500
     * @throws IllegalArgumentException if amountVnd is negative
     */
    public static int calculatePoints(long amountVnd, boolean member) {
        if (amountVnd < 0) {
            throw new IllegalArgumentException(
                    "amountVnd must be non-negative");
        }

        // Remainder below 10,000 VND does not qualify for a points tier.
        long basePoints = amountVnd / 10_000L;

        long awarded = member && amountVnd >= 100_000L
                ? basePoints * 2
                : basePoints;

        // Cap the points so high-value orders do not earn unlimited points.
        return (int) Math.min(awarded, 500L);
    }
}
```

Create the file **`LoyaltyDemo.java`** in the same directory:

```java
public class LoyaltyDemo {
    public static void main(String[] args) {
        System.out.println("regular="
                + LoyaltyPolicy.calculatePoints(45_000L, false));
        System.out.println("member="
                + LoyaltyPolicy.calculatePoints(120_000L, true));
        System.out.println("capped="
                + LoyaltyPolicy.calculatePoints(3_000_000L, true));

        try {
            LoyaltyPolicy.calculatePoints(-1L, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Run from the directory containing both files using **JDK 17+** (PowerShell, CMD, or bash). Create the `out` directory if it does not exist:

```sh
mkdir out
javac -encoding UTF-8 --release 17 -d out LoyaltyPolicy.java LoyaltyDemo.java
java -cp out LoyaltyDemo
```

**Exact stdout:**

```text
regular=4
member=24
capped=500
error=amountVnd must be non-negative
```

Compare against the contract and comments:

- `45_000 / 10_000` gives `4` full tiers; a non-member receives 4 points.
- `120_000 / 10_000` gives 12 base points; a member meeting the 100,000 VND threshold receives 24 points.
- `3_000_000 / 10_000` gives 300 base points; doubled to 600, then capped at 500.
- Negative values are rejected with `IllegalArgumentException`, matching the `@throws` tag.

The `calculatePoints` method **does not need to declare `throws IllegalArgumentException`**, because it is an unchecked exception; the `@throws` documentation is still useful so callers know the error condition. Using `long` for the monetary amount avoids the limited range of `int` in the example; doubling here does not overflow `long` because the result of `amountVnd / 10_000L` is bounded well within `long` range.

The example has two documentation levels: **Javadoc** describes the method's external contract; **in-body comments** explain why it rounds down and why it caps the points. You do not need comments like `// check if amountVnd is less than 0` because the `if` expression already makes that clear.

## 6. Generating HTML documentation from Javadoc

Once a program has an API that others need to read, the **`javadoc`** tool included with the JDK can generate HTML pages from `/** ... */` blocks:

```sh
javadoc -encoding UTF-8 -docencoding UTF-8 -d docs LoyaltyPolicy.java
```

Depending on OS, shell, and JDK, progress output from `javadoc` will vary; there is no fixed stdout to memorize. After running it successfully, open the corresponding documentation page for `LoyaltyPolicy` in the `docs` directory (for example `docs/LoyaltyPolicy.html`).

`-encoding UTF-8` applies when reading source files; `-docencoding UTF-8` specifies the encoding of generated documentation. `javac` remains responsible for compiling code, whereas `javadoc` produces documentation for readers. HTML documentation does not guarantee correct logic and does not replace testing.

You can run `javadoc -Xdoclint:all ...` in environments that support it to check Javadoc content and structure further. This is a documentation quality check, not a guarantee that all business rules are implemented correctly.

## 7. A case needing rationale: half-open time intervals

When joining consecutive work shifts, using a half-open interval `[startInclusive, endExclusive)` is very helpful: the end time of the previous shift equals the start time of the next shift without counting the boundary in both shifts.

Create the file **`TimeWindowDemo.java`**:

```java
public class TimeWindowDemo {
    /**
     * Checks whether a minute falls within a half-open time window.
     *
     * <p>The window has the form [startInclusive, endExclusive), meaning
     * the start minute is included while the end minute is excluded.
     *
     * @param minute minute to check, counted from the start of the day
     * @param startInclusive first included minute
     * @param endExclusive first excluded minute
     * @return true if minute belongs to the window
     */
    static boolean contains(int minute, int startInclusive, int endExclusive) {
        // Excluding the upper bound prevents adjacent shifts from overlapping.
        return minute >= startInclusive && minute < endExclusive;
    }

    public static void main(String[] args) {
        System.out.println("09:59=" + contains(599, 540, 600));
        System.out.println("10:00-before=" + contains(600, 540, 600));
        System.out.println("10:00-next=" + contains(600, 600, 660));
    }
}
```

Here, minutes are counted from the start of the day: 09:00 is 540, 09:59 is 599, and 10:00 is 600.

```sh
javac -encoding UTF-8 --release 17 -d out TimeWindowDemo.java
java -cp out TimeWindowDemo
```

Stdout:

```text
09:59=true
10:00-before=false
10:00-next=true
```

The comment is valuable because it helps maintainers understand why `minute < endExclusive` is used. The signature names `startInclusive`/`endExclusive` make the "what" clear; Javadoc adds the measurement unit and meaning of the result.

**Limitation of the example:** the method assumes valid minutes are passed (`0`–`1439` for `minute`; sensible daily bounds for `startInclusive` and `endExclusive`, with `startInclusive <= endExclusive`). It does not yet validate inputs. If converted into a public API accepting user data, you must design and enforce validation and document the error rules; writing `@param` alone does not enforce bounds.

## 8. When is Javadoc needed and when can it be omitted?

| Case | Recommendation |
| --- | --- |
| Public API used by other classes/modules/people | Document purpose, units, conditions, output, exceptions, and key side effects |
| Method with non-obvious business rules | Describe the contract with Javadoc; add inline rationale right next to surprising decisions |
| Short internal helper whose name and types speak for themselves | Comments can be omitted to reduce noise |
| Complex method with assumptions or uncommon algorithms | State invariants, pre/postconditions, and why the approach was chosen; add examples if helpful |
| Override implementing an already clear parent/interface contract | Avoid duplicating docs; use `{@inheritDoc}` if appropriate |
| API with side effects, state mutation, or control-flow impact | State key behavior so callers do not misuse it |
| Old API being replaced | Use `@Deprecated` in Java and Javadoc `@deprecated` with migration guidance |
| Very short one-off test with clear variable names | No need to write lengthy documentation for every line |

The goal is not the highest comment count or Javadoc coverage percentage. The goal is for readers to **predict the contract** and **avoid deleting an important design decision** just because the code looks like it could be simplified.

## 9. Writing good Javadoc: what to state explicitly

For methods that need documentation, check each of the following areas if relevant:

1. **Meaning of the result:** e.g., "loyalty points," not just "returns an `int`" since the signature already shows the type.
2. **Units:** `amountVnd` is VND, `durationSeconds` is seconds; do not force readers to guess.
3. **Valid domain:** whether negative numbers are rejected, whether `null` is allowed, and how empty lists are handled.
4. **Boundaries:** closed interval `[a,b]` or half-open `[a,b)`, and how thresholds `>=` vs. `>` behave.
5. **Error conditions:** exact exception type and when it is thrown. `@throws` describes actual behavior; do not list random Java exceptions.
6. **Side effects:** updating state, performing I/O, mutating arguments, closing resources, or affecting processing order.
7. **Determinism:** whether identical inputs yield identical outputs, or whether it depends on current time, locale, configuration, or external data sources.
8. **Rounding or sentinel rules:** e.g., integer division drops the remainder, `-1` means not found, or `Optional.empty()` means absent, if applicable.

Write for the caller's needs. Javadoc for `calculatePoints` does not need to narrate "declares `basePoints` and calls `Math.min`"; those are implementation details callers do not need to know and may change.

## 10. Common comment and Javadoc mistakes

**Outdated comments.** Example:

```java
// 10% discount.
int discounted = price * 80 / 100;
```

The code now applies a 20% discount while the comment says 10%. When changing a rule, update code, tests, and documentation together; even better, define a named constant like `DISCOUNT_PERCENT` so the value is not repeated across places.

**Vague comments:** `// fix bug`, `// complex logic`, `// special handling` help nobody. Explain the concrete condition and what breaks if the decision is removed. Do not use comments to keep blocks of dead old code; Git history is much better suited for that.

**Javadoc contradicting behavior:** documenting `@return null if missing` when the code throws an exception, or writing `@throws IOException` when no execution path actually throws it per the contract, causes confusion. Write documentation once behavior is settled and re-check it after edits.

**Repeating the name:** `/** Gets customer. */ Customer getCustomer()` adds almost no information. If a getter simply returns a field, a simple internal API may need no separate explanation; if it returns a defensive copy or fetches data remotely, state that clearly.

**Wrong tag names:** `@param amount` when the method declares `amountVnd`; or `@return` on a `void` method. Run `javadoc`/doclint to catch structural issues.

**Confusing Javadoc with regular comments:** `// @param value ...` does not create a `@param` tag in generated docs; tags belong inside a Javadoc block. Java code still compiles if comments are incomplete, but caller documentation does not fix itself.

**Incorrect embedded markup:** in Javadoc, `<`, `>`, and `&` can interact with HTML syntax. Use `{@code ...}` or proper escapes when displaying code and operators. Do not drop arbitrary multiline Java snippets into HTML in ways that break the generated page; use supported constructs and inspect the output page.

**Writing overly long docs for tiny methods:** excess prose is hard to keep in sync. When a clear method name and parameter types already convey the contract, a few focused sentences beat a page repeating the code.

## 11. Workflow for maintaining comments alongside code

When modifying a method:

1. Read the name, signature, Javadoc, and nearby comments around the code to change; identify the **current contract**.
2. Update code and tests per requirements; keep track of what changed in inputs, calculations, outputs, and exceptions.
3. Update the summary, `@param`/`@return`/`@throws` tags, thresholds/units, and "why" comments if decisions changed.
4. Remove redundant or outdated comments; never leave comments contradicting expressions.
5. Run `javac`, verify stdout/tests, and regenerate `javadoc` when relevant APIs or docs change.
6. Ask another reader to look at the documentation **before reading the body**: can they predict the results and errors accurately?

A good review does not just ask "are comments present?"—it asks "are the comments still true, and do they explain rationale that names and code alone do not?"

## 12. Self-check

**1. Is the comment `// increment i by one` after `i++` necessary?** Usually no; it repeats the exact operation already shown.

**2. Why add a comment when using `[start, end)`?** To explain that it avoids double-counting the shared boundary between consecutive intervals, not merely to remind readers that `<` means "less than."

**3. If a method has parameter `amountVnd` but Javadoc writes `@param amount`, what is wrong?** The name in the documentation does not match the signature; update the tag and use `javadoc`/doclint to check.

**4. Does `@throws IllegalArgumentException` automatically throw an exception on negative numbers?** No. It only documents the contract; the `throw new IllegalArgumentException(...)` branch in code is what actually raises the error.

**5. When an API changes a threshold from 100,000 to 200,000 VND, what must be updated?** The rule in code, the tests, and all Javadoc/comments describing that threshold. Otherwise, the documentation becomes misleading.

**6. Does `javac` automatically generate HTML pages from `/** ... */`?** No. The `javadoc` tool generates documentation, while `javac` compiles the program.

**Remember:** Let names and code structure explain *what*; comments should preserve *why*, and Javadoc should tell callers the *contract* — valid inputs, results, exceptions, and limits. Write documentation when it adds value, and maintain it whenever behavior changes.
