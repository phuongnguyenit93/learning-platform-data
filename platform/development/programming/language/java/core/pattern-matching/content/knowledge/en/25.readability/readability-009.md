# Keeping Code Compatible with Legacy Java Readers When Using Pattern Matching

When a development team transitions from the Java 8/11 style to **pattern matching** in Java 16–21, the source code may become shorter, yet not necessarily **easier to read** for colleagues accustomed to `instanceof`, manual casting, and `if/else` chains. The goal of this article is not to avoid new Java features, but to **use them in a way that allows readers to quickly map them to familiar syntax**, recognize the control flow, and accurately understand which cases are handled.

This article belongs to **Java Core Pattern Matching → Readability**. The focus is on a controlled transition between **`instanceof` + cast**, **type patterns**, **record patterns**, and **pattern-matching `switch`**, along with guidance on comments, naming, code review, and avoiding overly terse constructs.

**Important: there are two different kinds of “compatibility”.** Code that is **easy for legacy Java users to understand** does not mean code that **can compile/run on an older JDK**. For example, Java 21 code can still be presented in a very friendly way for Java 8 users, whereas a project that must run on Java 8 cannot directly include `record` or `case Type variable` syntax in its source code.

## 1. Identify the Right Type of Compatibility Before Modifying Code

### Readability compatibility

Code that is friendly to developers familiar with Java 8/11 typically has these characteristics:

- Variable names clearly state their roles: `customerId`, `delta`, `reason` instead of `a`, `b`, `v`.
- Each `case` branch answers a clear question: “If this is `UserRegistered`, what do we do?”.
- Multiple new syntactic constructs are not woven together in one long expression; when needed, extract guards or processing steps into small helper methods.
- It can be read from top to bottom without forcing the reader to deduce multiple levels of deconstruction or complex variable scopes.
- Comments emphasize **business logic or the rationale behind choosing a construct**, rather than annotating every Java keyword.

### Source/binary/runtime compatibility

This is a different technical requirement: a project has a specific target JDK version, language level, libraries/APIs, and runtime environment. Pattern matching syntax cannot be understood by a Java 8 compiler merely by adding a comment or renaming variables.

| Java Version | Stabilized Related Syntax | What Readers Need to Know |
| --- | --- | --- |
| Java 8/11 | Traditional `instanceof`, casting, `if/else`; classic `switch` statement | Requires a cast when calling subtype-specific methods |
| Java 14 | `switch expression`, arrow form `->` and `yield` (JEP 361) | `switch` can produce a value, not just execute statements |
| Java 16 | `instanceof Type variable` (JEP 394), `record` (JEP 395) | Eliminates boilerplate casts; records have clear accessors/components |
| Java 17 | `sealed class` / `sealed interface` (JEP 409) | Allows controlling the permitted set of subtypes |
| Java 21 | Record patterns (JEP 440), pattern matching for `switch` (JEP 441) | `case Type variable`, `case Record(var ...)`, and `when` guards are stabilized |

Java 11 adds several APIs such as `String.isBlank()` compared to Java 8; this API itself is not a pattern matching feature. Do not rely solely on coding style to guess the minimum supported version.

**Expectation-setting rule:** This article includes two standalone sample programs: one example using only constructs familiar in Java 8, and one **Java 21+** example comparing the classic style with modern pattern matching in the same program. “Classic style” in the second example only describes the handling style; it does **not** mean the entire file can run on Java 8 because the `sealed`/`record` declarations still require a newer version.

## 2. Teach One Simple Transformation Rule First

Here is familiar Java 8 syntax:

```java
// Java 8 snippet: 'value' has type Object.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.trim());
}
```

Starting from Java 16, you can write:

```java
// Java 16+ snippet: 'value' has type Object.
if (value instanceof String text) {
    System.out.println(text.trim());
}
```

It can be explained in **one sentence**: `instanceof String text` performs two previously separate actions — **checking the `String` type** and **declaring the variable `text` of type `String` when matched**, so no additional cast is needed.

If you are only modifying a short block, this kind of conversion is usually a good starting point: keep the `if` structure, keep the condition order, and just remove the redundant cast. It is easier to review than simultaneously converting the whole method to `switch`, renaming variables, and changing error-handling policies.

### How to read a type pattern

```java
if (value instanceof String customerName) {
    // customerName is a String here.
}
```

Readers should break it down into three parts:

1. `value`: the data being inspected.
2. `String`: the type that must match at runtime.
3. `customerName`: the new variable name used **after a match**.

Naming it `customerName` helps explain the meaning better than `s` when the data is a customer name. For a snippet of just a few lines, `text` or `number` is also clear enough.

**Do not say “the compiler implicitly casts it everywhere in the method”.** A pattern variable is only in scope where control flow proves the pattern has matched; outside that scope, the variable does not exist.

## 3. Standalone Example Using Java 8 Syntax

Here is a complete program that does not use `record`, `sealed`, `var`, `switch expression`, or pattern variables. It illustrates how to write code readable by a team not yet using newer Java versions.

Save the file **`Java8ReadableDemo.java`**:

```java
public class Java8ReadableDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    static String describe(Object input) {
        if (input == null) {
            return "Missing";
        }

        if (input instanceof Ticket) {
            Ticket ticket = (Ticket) input;
            return "Ticket: " + ticket.code();
        }

        if (input instanceof String) {
            String text = (String) input;
            return "Text: " + text.trim();
        }

        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ticket("T-19")));
        System.out.println(describe("  note  "));
        System.out.println(describe(null));
        System.out.println(describe(23));
    }
}
```

Compile with a JDK that supports targeting Java 8 (for example, JDK 8 or a newer JDK supporting `--release 8`). On a suitable newer JDK:

```bash
javac --release 8 Java8ReadableDemo.java
java Java8ReadableDemo
```

If using **JDK 8**, the compile command is `javac Java8ReadableDemo.java` because JDK 8 does not have the `--release` flag.

Output:

```text
Ticket: T-19
Text: note
Missing
Other
```

**Why is this example easy to follow?** `instanceof` checks the type, the cast line is placed immediately after the check, and each branch handles one input kind and ends with `return`. This is the mental model a Java 8/11 reader can carry over when learning modern pattern matching.

**Note:** This snippet contains no `String.isBlank()`, `List.of()`, or APIs added after Java 8; it uses basic Java 8 constructs. When a project must support an older JDK, you must check the **entire source base and dependencies**, not just a few lines containing patterns.

## 4. Keep the Logic Unchanged When Switching to Pattern Matching

A safe way to learn is to **change the expression without changing the processing rules**:

| Step | Old Way | Pattern Way |
| --- | --- | --- |
| Check if object is of type `T` | `value instanceof T` | `value instanceof T item` |
| Create cast variable | `T item = (T) value;` | `item` is bound if matched |
| Call subtype method | `item.method()` | `item.method()` as before |
| Handle non-match | Old `else`/`return` branch | Keep unchanged in the first refactor |
| Check business rule | `if (item.valid())` | Keep `if` if it is easier to read |

There is no need to replace every `if` with `switch` just because newer Java allows it. If a method only cares about one type, `if (value instanceof T item)` is usually clearest.

### Guard clauses and variable scope

A readable snippet for someone familiar with `if`:

```java
// Java 16+ snippet: inside a method returning String.
if (!(input instanceof String customerName)) {
    return "Unsupported";
}

return "Customer: " + customerName.trim();
```

By the final `return` line, the compiler knows that if the pattern did not match, the method would have already exited. Therefore, `customerName` is valid after the `if`.

Do not blindly use this pattern if you only log on mismatch:

```java
// WRONG: 'customerName' is not guaranteed to be bound.
if (!(input instanceof String customerName)) {
    System.out.println("Unsupported");
}
return customerName.trim();
```

Legacy Java readers may find “a variable declared inside a condition” slightly unfamiliar. A short comment such as “non-matching returns above; from here customerName is String” is helpful in the first few places where pattern matching is adopted. There is no need to scatter identical comments across every branch once the team is used to it.

## 5. When to Switch from `if/else` to Pattern-Matching `switch`?

When a method genuinely has to handle **multiple related data types**, `switch` can clarify the **set of cases**. First, write each type in an easy-to-read branch:

```java
// Java 21+ snippet: 'value' is Object.
String label = switch (value) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Other";
};
```

Read it as equivalent to a chain of conditions:

- If it is a `String`, bind `text` and take the first result.
- If it is an `Integer`, bind `number` and take the second result.
- If it is `null`, use the dedicated branch.
- If it falls into none of the above, use `default`.

**Differences from classic `switch`:**

- A `switch expression` **produces a value**, which can be assigned or used in `return switch (...)`.
- Arrow branches `case ... ->` **do not fall through** like the old `case ...:` syntax.
- A multi-statement branch in a `switch expression` requires `yield result;` to supply the value, instead of `break result;`.
- `case null` handles a `null` selector; do not assume `default` automatically replaces a null check.
- A `switch expression` must be **exhaustive**: every possible selector value must have a matching branch or corresponding handler.

If someone used to Java 8 easily confuses `return` and `yield`, prefer **single-expression arrow branches** when possible, or extract complex logic into a helper method to avoid scattered `yield` statements.

## 6. Introduce Record Patterns as a Shorter Way to Call Accessors

Java 21+ example:

```java
record UserRegistered(String userId, String displayName) {}
```

Before using a record pattern, a simple readable form (still using modern Java's `record` type) is:

```java
// Snippet: 'event' has type Object.
if (event instanceof UserRegistered registered) {
    String id = registered.userId();
    String name = registered.displayName();
    System.out.println(id + ": " + name);
}
```

Once readers understand record types and accessors, it can be shortened with a record pattern:

```java
// Java 21+, snippet: 'event' has type Object.
if (event instanceof UserRegistered(var id, var name)) {
    System.out.println(id + ": " + name);
}
```

This pattern reads as: **if `event` is `UserRegistered`, extract the first component into `id` and the second component into `name`**. The order is determined by the record declaration, not by the names `id`/`name`.

### Avoid nesting too many levels

With nested records:

```java
record Address(String city, String street) {}
record Customer(String id, Address address) {}
```

Two-level deconstruction:

```java
// Java 21+, illustrating when both city and street are genuinely needed.
if (value instanceof Customer(var customerId,
                              Address(var city, var street))) {
    System.out.println(customerId + ": " + city + "/" + street);
}
```

However, if the code only needs the city, or business logic also needs to check `address == null`, a step-by-step approach is sometimes easier to read:

```java
if (value instanceof Customer(var customerId, var address)) {
    if (address != null) {
        System.out.println(customerId + ": " + address.city());
    }
}
```

**Important difference:** a nested record pattern `Address(...)` **does not match** when the `address` component is `null`; whereas `var address` can receive `null`. When refactoring, you must preserve the null policy and error branches—do not replace code simply because it looks shorter.

In a problem with many business conditions, avoid nesting patterns three or four levels deep on a single line. Extracting one or two levels of components and then calling clearly named helper methods is usually friendlier to newcomers reading pattern matching.

## 7. Java 21+ Example: Comparing “Classic” and “Modern” on the Same Data

The following program uses **`sealed interface` and `record`**, so it **only compiles with Java 21+ for the modern syntax demonstrated**. Both `describeClassic` and `describeModern` use the **same data model** to compare **handling styles**, not to suggest the entire classic method can be copied into a Java 8 project.

Create the file **`ReadablePatternsDemo.java`**:

```java
public class ReadablePatternsDemo {
    sealed interface DomainEvent permits UserRegistered, PointsChanged, UserDisabled {}

    record UserRegistered(String userId, String displayName)
            implements DomainEvent {}

    record PointsChanged(String userId, int delta)
            implements DomainEvent {}

    record UserDisabled(String userId, String reason)
            implements DomainEvent {}

    static String describeClassic(DomainEvent event) {
        if (event == null) {
            return "Missing event";
        }

        if (event instanceof UserRegistered) {
            UserRegistered registered = (UserRegistered) event;
            return "Registered " + registered.userId()
                    + ": " + registered.displayName();
        }

        if (event instanceof PointsChanged) {
            PointsChanged points = (PointsChanged) event;
            if (points.delta() > 0) {
                return "Points +" + points.delta()
                        + " for " + points.userId();
            }
            return "Points " + points.delta()
                    + " for " + points.userId();
        }

        if (event instanceof UserDisabled) {
            UserDisabled disabled = (UserDisabled) event;
            return "Disabled " + disabled.userId()
                    + " (" + disabled.reason() + ")";
        }

        throw new IllegalStateException("Unhandled event");
    }

    static String describeModern(DomainEvent event) {
        return switch (event) {
            case UserRegistered(var id, var name) ->
                    "Registered " + id + ": " + name;

            case PointsChanged(var id, var delta) when delta > 0 ->
                    "Points +" + delta + " for " + id;

            case PointsChanged(var id, var delta) ->
                    "Points " + delta + " for " + id;

            case UserDisabled(var id, var reason) ->
                    "Disabled " + id + " (" + reason + ")";

            case null -> "Missing event";
        };
    }

    static String greetClassic(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            if (!text.isBlank()) {
                return "Hi, " + text.trim();
            }
        }
        return "Unknown";
    }

    static String greetModern(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Hi, " + text.trim();
        }
        return "Unknown";
    }

    public static void main(String[] args) {
        DomainEvent[] events = {
                new UserRegistered("u7", "Lan"),
                new PointsChanged("u7", 5),
                new PointsChanged("u7", -2),
                new UserDisabled("u8", "requested"),
                null
        };

        for (DomainEvent event : events) {
            System.out.println(
                    describeClassic(event) + " | " + describeModern(event));
        }

        System.out.println(
                greetClassic("  Mai  ") + " | " + greetModern("  Mai  "));
        System.out.println(greetClassic(42) + " | " + greetModern(42));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 ReadablePatternsDemo.java
java ReadablePatternsDemo
```

Output:

```text
Registered u7: Lan | Registered u7: Lan
Points +5 for u7 | Points +5 for u7
Points -2 for u7 | Points -2 for u7
Disabled u8 (requested) | Disabled u8 (requested)
Missing event | Missing event
Hi, Mai | Hi, Mai
Unknown | Unknown
```

### Reading each equivalent pair

**`describeClassic`** checks the runtime type with `instanceof`, performs a cast, and then calls accessors. `describeModern` uses `case UserRegistered(var id, var name)` to check the record and extract components. The results are **identical** for the tested inputs.

**`PointsChanged`** has two branches in the modern version: the `delta > 0` case precedes the general branch. The `when` guard corresponds to `if (points.delta() > 0)` in the classic version. If you reverse the order of the two `case PointsChanged(...)` branches, the compiler may report a **dominated case**: the broader earlier branch already covers the narrower later branch.

**`UserDisabled`** illustrates record deconstruction: `var id` extracts the `userId` component, and `var reason` extracts `reason`. These names are local variables in the case and do not automatically rename the original accessors.

**`case null`** preserves the `if (event == null) return ...` behavior from the classic version. The `switch` is also checked for exhaustiveness by the compiler because `DomainEvent` is a sealed hierarchy listing the subtypes in the example.

**`greetClassic` and `greetModern`** illustrate a lower-risk conversion: only replacing the `instanceof + cast` pair with a type pattern, keeping the `isBlank()` and `trim()` checks intact. This is typically the first type of PR to apply with a team new to pattern matching.

### What the example does not prove

The program was run with the test cases above, but some business invariants are not checked: `displayName`/`reason` could be `null`; `delta` could be negative. Both methods return identical strings **on the sample data**, which does not mean every similar refactor is automatically valid for all inputs. When applying to production, you need additional tests for null cases, boundary values, and every branch per contract.

## 8. Keep Variable Names “Self-Explanatory” for New Syntax

Because a pattern can both check a type and declare variables, naming choices become even more important:

```java
// Hard to read when context is complex.
if (value instanceof UserRegistered(var a, var b)) {
    System.out.println(a + b);
}
```

Prefer meaningful names:

```java
if (value instanceof UserRegistered(var userId, var displayName)) {
    System.out.println(userId + ": " + displayName);
}
```

| Habit to Adopt | Reason |
| --- | --- |
| Name variables by role (`userId`, `displayName`) | Readers do not have to remember component order elsewhere |
| Use short names for small, familiar structures (`x`, `y` in `Point`) | Avoid overly long names that dilute the expression |
| Place guards next to specific branches (`when delta > 0`) | Immediately shows why the branch is selected |
| Avoid `var` when the inferred type is unclear | You can use a typed component pattern or split the step |
| Do not change variable names, case order, and null behavior in the same PR | Makes before–after behavior easy to compare |
| Keep a consistent style across the module | Readers only need to learn one reading convention |

Using `var` in a record pattern does not mean every variable has type `Object`. The compiler infers the component type from the record; for example, `PointsChanged(String userId, int delta)` gives `var id` type `String` and `var delta` type `int`. When the input object has less specific generic types, inspect the inferred type carefully to avoid confusion.

## 9. Avoid “Code Golf”: When Does New Syntax Hurt Readability?

### 9.1. Do not nest multiple patterns just to save lines

An overwhelming example:

```java
// Java 21+ illustration, assuming the corresponding records are declared.
if (value instanceof Order(var id,
        Customer(var customerId, Address(var city, var street)))) {
    // ...
}
```

Nested patterns are valuable when you need **that exact structure**. However, if the goal is to check null fields with different error messages, a series of guard clauses after extracting `Order` is usually easier to understand. You can split a condition into named steps:

```java
// Snippet with corresponding record types.
if (!(value instanceof Order(var orderId, var customer))) {
    return "Not an order";
}
if (customer == null) {
    return "Missing customer";
}
Address address = customer.address();
if (address == null) {
    return "Missing address";
}
return orderId + " / " + address.city();
```

The two forms **are not entirely equivalent in error flow**: the nested form only distinguishes “match or no match”; the guarded form returns specific reasons. Choose the style based on expressive needs rather than line count alone.

### 9.2. Do not force `switch` on single-type checks

If you only need to check a string and return a result, `if (input instanceof String text)` is simpler than a `switch` with a couple of branches that add no new meaning. Use `switch` when it helps present a set of variants with a shared focus, especially with `sealed` types or multi-type dispatch.

### 9.3. Do not hide side effects inside guards

`when` is suited for checking conditions like `delta > 0` or `name != null && !name.isBlank()`. You should not perform operations with unpredictable side effects directly inside a guard (DB writes, API calls, state mutations). Legacy Java readers understand those operations much more easily when written as explicit statements inside the handler branch.

### 9.4. Do not confuse “readable” with “one line per branch”

A `switch` can be short yet hard to understand if it has long conditions, single-letter variables, four-level record patterns, and a fallback with no clear meaning. Conversely, adding a few lines of `if` to express validation clearly can be the better choice.

## 10. `null`, Scope, and Case Ordering: Where Legacy Java Readers Get Tripped Up

### `null`: ask clearly where null can appear

- **`null` selector**: `instanceof` type patterns and record patterns do not match; a `switch` on a null reference normally throws `NullPointerException` if there is no explicit null handling. Use `case null` when null is a valid input.
- **`null` component inside a record**: `record Box(String text) {}` allows `text` to be `null` if the constructor does not prevent it; `Box(var text)` can match and bind `text == null`.
- **Nested record pattern** like `Outer(Inner(var x))` does not match when the `Inner` component is `null`. Do not refactor `if (outer.inner() == null)` into a nested pattern and forget the null case that needs its own message.

### Scope: where can the variable be used?

```java
// Java 16+, valid: if it does not match, return early.
if (!(value instanceof String text)) {
    return "Not string";
}
return text.trim();
```

Below the guard clause, `text` is allowed because the non-matching path has terminated. Do not reference it after an `if` whose non-matching branch can continue execution. Use `if (value instanceof String text && !text.isBlank())` when the guard needs to inspect the bound variable.

### Case ordering: narrow before wide

```java
// Java 21+, selector has type Object.
String kind = switch (input) {
    case String text when text.isBlank() -> "Blank";
    case String text -> "Text";
    case CharSequence sequence -> "Other text-like";
    case null -> "Missing";
    default -> "Other";
};
```

- The guarded `String` branch comes before the general `String` branch.
- The `CharSequence` branch comes after `String` because `String` implements `CharSequence`.
- If you reverse the wide/narrow branches, Java may report a dominance error because the later branch is shadowed by the earlier one.
- Even when code compiles, complex business guard ordering still needs to be verified by tests; the compiler cannot infer arbitrary logical relationships.

A friendly way to explain it: “Go from specific cases to remaining cases, just like `if / else if / else`”, and add that the compiler also checks for certain unreachable branches.

## 11. Incremental PR Roadmap, Avoiding Big-Bang Changes

A team with many developers familiar with Java 8/11 can introduce pattern matching into a project incrementally:

1. **Align on the runtime/build target first.** Determine which Java version the project runs on; do not use new syntax in codebases requiring Java 8/11.
2. **Start with simple type patterns.** Replace `instanceof + cast` in `if` without changing business logic. Add tests to preserve behavior.
3. **Use consistent variable naming and formatting.** Do not force every spot to be as short as possible; the criterion is that someone opening the file for the first time can understand each branch.
4. **Introduce `record` and accessors before record deconstruction.** Once readers know that a `record` holds components in order, convert select spots to `Record(var a, var b)` where it genuinely helps.
5. **Use `switch` when there are multiple variants.** If the domain has a closed set of subtypes, `sealed` + exhaustive `switch` benefits both the compiler and code reviews.
6. **Keep “why” comments, limit “what” comments.** Explain the reason for a guard or fallback rather than repeating the meaning of `instanceof` on every line.
7. **Measure quality via reviews and tests.** Reviewers familiar with legacy Java should be able to answer: what data enters this branch, where does null go, what happens if a new type is added, and does it still produce the same result?
8. **Make small, purposeful edits.** Do not mix pattern-matching refactors with API contract or schema changes in the same PR when they can be separated, as it becomes hard to tell where a bug came from.

In internal documentation, a short side-by-side “before / after” pair is sometimes more helpful than a full chapter of theory. However, you do not need to keep both styles in production; in most cases, keeping the chosen style with clear tests is enough.

## 12. Checking Technical Compatibility When You Truly Must Support Older JDKs

If the product requirement is to **run on Java 8**, writing code that “looks like Java 8” is not enough. You must compile/test against the corresponding target:

```bash
# Example with a modern JDK that supports compiling for Java 8.
javac --release 8 Java8ReadableDemo.java
```

For files using sealed types, records, or `case ... when ...`:

```bash
# Example with JDK 21+ and Java 21 source code.
javac --release 21 -encoding UTF-8 ReadablePatternsDemo.java
```

**`--release`** checks the language syntax, bytecode, and Java Platform APIs matching the target as supported by `javac`. It does not automatically make third-party dependencies compatible, does not turn Java 21 syntax into Java 8, and does not replace running integration tests on an actual JVM.

With Gradle/Maven, set a consistent project toolchain or compiler release, run CI against the target version, and let the IDE flag errors immediately if newer APIs or syntax are accidentally used. If a team needs to publish a library for both Java 8 and Java 21, consider separating compatibility modules/APIs or providing appropriate adapters rather than forcing a single codebase to use new syntax on an old target.

### Distinguish these statements

| Statement | Is It True? |
| --- | --- |
| “Someone who used Java 8 can understand Java 21 code if it is written clearly.” | Possible, when supported by comparative examples, good naming, and reasonable complexity |
| “Using `instanceof String s` still runs on Java 8.” | **No**; type patterns stabilized in Java 16, and Java 8 does not understand the syntax |
| “Not using pattern matching means it is Java 8 code.” | **Not sufficient**; it may still use `record`, `sealed`, switch expressions, or newer APIs |
| “Using `--release 8` guarantees all dependencies and runtime are safe.” | **No**; you must verify dependencies and run/test on the target environment |
| “Shorter modern code is always easier to read.” | **No**; naming, scope, pattern depth, and business clarity matter more than brevity |

## 13. Review Checklist for Teams Familiar with Legacy Java

When reviewing a PR that uses pattern matching, reviewers can check:

- **Version:** are the features compatible with the JDK/build target?
- **Before–after comparison:** does switching from `instanceof + cast` to a pattern preserve the same match/fallback flow?
- **Variable names:** can someone unfamiliar with the component order guess what each variable holds?
- **Scope:** are pattern variables used only where a match is guaranteed?
- **Nulls:** are null selectors and null nested components handled according to the old contract?
- **Case ordering:** do guarded/narrower branches appear before broader branches?
- **Exhaustiveness:** for sealed hierarchies, does the compiler flag missing variants, or is `default` masking them?
- **Business rules:** was any validation dropped when shortening the expression?
- **Complexity:** is a multi-level nested pattern worth it compared to clearly named access steps?
- **Testing:** are success, failure, null, boundary values, and new variants covered?

The key point is not “did we use every Java 21 feature”, but **whether the next maintainer can modify it correctly without having to decode a cryptic expression**.

## 14. Common Mistakes and How to Fix Them

| Mistake | Cause | Fix |
| --- | --- | --- |
| Claiming code “supports Java 8” just because it still uses `if` | Other declarations or APIs may require a newer JDK | Check `--release 8` and test at runtime; use genuine Java 8 constructs |
| Converting every `if` chain to `switch` | Changes syntax without improving clarity | Use `if` for simple cases; `switch` for a set of variants |
| Using `var a, var b, var c` in a large record | Readers cannot tell which component each variable comes from | Use meaningful names or extract components in separate steps |
| Refactoring to a nested record pattern and losing `null` handling | Nested patterns do not match null record components | Keep equivalent null guards/fallbacks |
| Assuming `default` handles null | A null selector has distinct semantics | Use `case null` or reject null explicitly |
| Placing a general case before a guarded case | Narrower branch is shadowed, causing a dominance error | Order specific cases first |
| Using a pattern variable outside its match scope | The compiler cannot prove the variable is bound | Use it inside the matched branch or after a guard clause with `return` |
| Mixing syntax migration with business changes in the same PR | Hard to verify whether results remain equivalent | Separate the changes and write tests specifying behavior |
| Explaining new code with too much jargon and no examples | Increases cognitive load | Provide classic/modern code pairs and explain step by step |
| Believing a shorter refactor is always better | Line count does not measure clarity | Optimize for understandability, testability, and maintainability |

## 15. Practice Exercises

### Exercise 1 — Step-by-step conversion without changing behavior

Given the legacy Java snippet:

```java
// Snippet inside a method returning String.
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "Other";
```

Rewrite it for Java 16+ while still using `if`.

**Answer:**

```java
if (input instanceof String text) {
    return text.trim();
}
return "Other";
```

This preserves the return type and null behavior: when `input == null`, `instanceof` does not match, so the result remains `"Other"`.

### Exercise 2 — Choosing variable names for a record pattern

Given `record Refund(String paymentId, long amountCents) {}`, which version is easier to read in a refund-processing block?

```java
// A
if (value instanceof Refund(var x, var y)) {
    System.out.println(x + " " + y);
}

// B
if (value instanceof Refund(var paymentId, var amountCents)) {
    System.out.println(paymentId + ": " + amountCents);
}
```

**Answer:** B is easier to read in most business contexts because the reader does not have to jump back to the record declaration to recall `x` and `y`. Both are valid Java 21+ syntax.

### Exercise 3 — Fixing dominance

Given `Object input`, reorder the branches:

```java
// INTENTIONALLY WRONG because the general String branch precedes the guarded one.
String label = switch (input) {
    case String text -> "Text";
    case String text when text.isBlank() -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
```

**Answer:**

```java
String label = switch (input) {
    case String text when text.isBlank() -> "Blank";
    case String text -> "Text";
    case null -> "Missing";
    default -> "Other";
};
```

The specific branch must precede the general branch. It reads like `if (isString && blank) ... else if (isString) ...`.

### Exercise 4 — Reading equivalence between accessors and deconstruction

Suppose `record Ticket(String code, int priority) {}`. Do the following two snippets always behave the same?

```java
// First form
if (input instanceof Ticket ticket) {
    System.out.println(ticket.code());
}

// Second form
if (input instanceof Ticket(var code, var priority)) {
    System.out.println(code);
}
```

**Answer:** For a valid `Ticket` object matching this model, both extract the `code` component and print it; neither executes when the selector `input` is null. However, the second form requires record patterns from **Java 21**, whereas `instanceof Ticket ticket` is a type pattern stabilized in **Java 16**. If the Java target is too old, neither will compile as written here; you would need `instanceof Ticket` + cast and a `Ticket` type valid for that target.

### Exercise 5 — Migration plan

A team is running Java 11, wants readable code, and plans to upgrade to Java 21. Should they merge Java 21 record patterns into the Java 11 branch before upgrading the target?

**Answer:** No. Before upgrading the JDK/build target, refactor only within Java 11 syntax/API limits, add tests, and prepare comparative examples. Once the target has switched to Java 21, consider migrating gradually to type patterns, record patterns, or `switch` in clearly scoped PRs.

## 16. Takeaways and References

- **“Readable by legacy Java developers” does not mean “compilable by an older JDK”.** Distinguish readability compatibility from source/runtime compatibility.
- Introduce pattern matching by mapping **`instanceof + cast` → `instanceof Type variable`**, and only then expand to record patterns and `switch`.
- Keep code readable with **meaningful names, short branches, purposeful guards, explicit null handling**, and a reasonable deconstruction depth.
- Do not alter business behavior just because new syntax is shorter; use tests to verify match, non-match, and boundary cases.
- Choose `if` for simple checks and `switch` for multiple related variants. With a sealed hierarchy, an exhaustive `switch` without `default` can let the compiler warn when a subtype is added.
- Controlled, step-by-step migration is the fastest way to help Java 8/11 developers understand Java 21 while preserving maintainability.

**Official references:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 395 — Records](https://openjdk.org/jeps/395), [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361), [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
