# Illustrating Patterns with Minimal Examples in Java

Documentation on Java Pattern Matching usually does not need to open with a large application, a framework, or multiple domain classes. A **minimal example** is the shortest piece of code that **still provides enough context for the reader to understand and independently verify a specific rule**: what type the pattern checks, which variable is bound, what condition causes a branch to be selected, and what the observable result is.

This lesson belongs to **Java Core Pattern Matching → API and Documentation**. The goal is to learn how to **write, verify, and present small examples** for `instanceof` type patterns, record patterns, nested deconstruction, pattern matching for `switch`, `when` guards, `null`, flow scoping, and exhaustive `switch`; while also distinguishing illustrative snippets in documentation from standalone runnable source code or examples that **intentionally fail to compile**.

**Versions to remember:** Pattern matching for `instanceof` was finalized in **Java 16** (JEP 394); record patterns and pattern matching for `switch` were finalized in **Java 21** (JEP 440, JEP 441). `--enable-preview` is not required for these finalized features in Java 21.

## 1. "Minimal" Means Small Enough, Not Missing Context

A good example should answer four questions:

1. **What is the input?** For example, `Object input = "Java";` or a record `Point(2, 3)`.
2. **Which rule is being illustrated?** Type checking, component deconstruction, variable scope, guard, `null` handling, or exhaustiveness.
3. **In what environment does it run?** Java 16+, Java 21+; is it a snippet or a complete `.java` file?
4. **What is the expected result/diagnostic?** What is printed to stdout, what value is returned, or for what reason must the compiler reject it?

"Minimal" does not mean writing only:

~~~java
if (obj instanceof String s) {
    // ...
}
~~~

The snippet above shows the syntax, but **does not say where `obj` is declared, what its static type is, how `s` is used, or what will happen**. It can serve as a one-line syntax illustration, but **is not yet a standalone example to copy and run**.

A minimal example can run with just one class, one method, one input, and one clear result. Conversely, when illustrating the difference between a true and false guard, at least two inputs are needed. **Keep the cases that clarify the rule; drop what is irrelevant.**

### Two Example Formats That Must Be Distinguished

| Format | When to Use | What Must Be Stated |
| --- | --- | --- |
| **Snippet** | Explaining an expression/statement in an already clear context | Type and name of the input variable, Java version, that this is not a standalone file |
| **Standalone program** | Readers need to copy, compile, and verify on their own | File name = `public class` name; complete source; `javac`/`java` commands; stdout |
| **Intentionally invalid example** | Teaching compiler errors, dominance, or flow scoping | Clearly mark `INTENTIONALLY INVALID`, the expected error, and the fix |
| **Minimal test case** | Proving a behavior that could regress | Input, expected, actual, assertion, and environment version |

In learning materials, you can start with a three-line snippet; when claiming something is "runnable", it should be accompanied by **a complete file** or clear instructions on which file to place it in.

## 2. The Most Basic Pattern: `instanceof` Type Pattern

Place it next to the old style so readers can see what has changed:

~~~java
// Old-style Java: snippet inside a method with Object input.
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
~~~

Since Java 16, you can write:

~~~java
// Java 16+: snippet inside a method with Object input.
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

**There is only one main point:** `instanceof String text` both checks the type and binds `text` as a `String` if the match succeeds; **no manual cast is needed**. In that branch, the compiler knows `text` is bound and has type `String`.

### Standalone Example 1 — Type Pattern and Guard Clause

Create the file **`MinimalInstanceofDemo.java`**:

~~~java
public class MinimalInstanceofDemo {
    static String greet(Object input) {
        if (!(input instanceof String name)) {
            return "Not text";
        }
        if (name.isBlank()) {
            return "Empty";
        }
        return "Hi, " + name.trim();
    }

    public static void main(String[] args) {
        System.out.println(greet("  Lan  "));
        System.out.println(greet("   "));
        System.out.println(greet(42));
        System.out.println(greet(null));
    }
}
~~~

Compile and run with **JDK 16 or later**:

~~~bash
javac --release 16 -encoding UTF-8 MinimalInstanceofDemo.java
java MinimalInstanceofDemo
~~~

Output:

~~~text
Hi, Lan
Empty
Not text
Not text
~~~

### Reading Each Path

- `"  Lan  "` is a `String`. The pattern matches, and `name` remains in scope after the negated `if` branch because the non-matching branch executes `return`. `isBlank()` is false; `trim()` produces the displayed string `"Lan"`.
- `"   "` is a `String` but blank; the method returns `"Empty"`.
- `42` is not a `String`. The negated branch immediately returns `"Not text"`.
- `null` does not match the type pattern `String name`, and also returns `"Not text"`.

**Note:** `String.isBlank()` has been available since Java 11, so it does not conflict with the Java 16 target here. The code intentionally does not need `record`, `sealed`, or pattern `switch`: each example should focus strictly on the feature being taught.

### Small Illustration of Flow Scoping

~~~java
// Java 16+, valid snippet inside a method returning int.
if (!(input instanceof String text)) {
    return -1;
}
return text.length();
~~~

If it does not match, the method exits; so at the final `return text.length()`, the compiler knows `text` is in scope. Conversely:

~~~java
// INTENTIONALLY INVALID: the non-matching branch can still fall through.
if (!(input instanceof String text)) {
    System.out.println("Not a String");
}
return text.length(); // text is not guaranteed to be bound.
~~~

The second snippet **does not compile** when using `text` on a path where the pattern did not match. A minimal error example must state the exact reason: **flow scoping/definitely matched**, not a cast error.

## 3. Record Pattern: One Record, Two Components

Suppose a point has two coordinates:

~~~java
// Java 21+, record declaration snippet.
record Point(int x, int y) {}
~~~

Only one check is needed to illustrate deconstruction:

~~~java
// Java 21+, snippet; input has type Object.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
~~~

Read this as: "if `input` is a non-`null` `Point`, extract the first component into `x` and the second component into `y`." The compiler infers `x` and `y` as `int`, **not `Object`**. That is a **record pattern**, different from the type pattern `input instanceof Point point` which only binds the whole record.

The **component order** should be stated in documentation: for `record Point(int x, int y)`, the first position is `x` and the second position is `y`. Local variable names in the pattern do not change the order. For example, `Point(var y, var x)` is still syntactically valid, but can easily mislead readers about the values because the name `y` will receive the original `x` component.

### From One Level to Two Levels

~~~java
// Java 21+, record declaration snippet.
record Order(String id, Point destination) {}
~~~

Nested record pattern:

~~~java
// Java 21+, input has type Object; snippet inside an appropriate method.
if (input instanceof Order(var id, Point(var x, var y))) {
    System.out.println(id + " -> " + x + "," + y);
}
~~~

Two records are enough to illustrate **nested deconstruction**. There is no need to build an entire ordering system, database, or DTO framework.

**Important null case:** `new Order("A-2", null)` can still be created if the constructor does not enforce constraints. The pattern `Order(var id, Point(var x, var y))` **does not match** when `destination == null`. Meanwhile, `Order(var id, var destination)` can match and bind `destination == null`. Examples should show both situations so readers do not think `var` always eliminates null.

## 4. `switch` Patterns: Each Case Expresses One Scenario

A Java 21+ example does not need a sealed hierarchy to introduce `switch`:

~~~java
// Java 21+, snippet; input has type Object.
String label = switch (input) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Other";
};
~~~

Concepts to illustrate individually:

- `case String text` is a **type pattern**: it checks the type and binds a variable.
- `case Integer number` handles another type.
- `case null` handles a **`null` selector**. Do not assume `default` covers `null` in the way the code expects.
- `default` is required here because `Object` can hold many other types.
- This is a **`switch expression`**, so the branches produce values and the entire expression must be able to return a result.

**Avoid** putting nested record patterns, complex guards, generics, sealed interfaces, and database access all together in the first `switch` example: readers will find it hard to tell which rule determines the result.

## 5. Adding a `when` Guard with an Easily Verifiable Condition

From the simple `switch`, expand by just one idea:

~~~java
// Java 21+, snippet; input has type Object.
String label = switch (input) {
    case String text when !text.isBlank() -> "Text";
    case String text -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
~~~

The guard runs **after the type pattern has matched**. If `input = "Java"`, the first branch is selected; if `input = "   "`, the guard is false and the next `String` case is selected.

This is clearer than a `when` example that calls a series of services or uses obscure conditions. A **pure, side-effect-free guard** is enough to explain the mechanism.

### Case Ordering Must Be Correct

~~~java
// INTENTIONALLY INVALID, Java 21+, input is Object.
String label = switch (input) {
    case String text -> "Any string";
    case String text when text.isBlank() -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
~~~

The general `String` branch placed first already covers every `String`; the guarded branch behind it is **dominated**, so the compiler rejects it. The fix is to place the **specific branch with `when` first**, and the unguarded `String` branch after it.

When creating documentation about dominance, use **exactly one error** so the compiler is not distracted by other errors. State that diagnostic messages may vary by JDK; what matters is the cause: **dominated case label**.

## 6. Standalone Example 2 — Combining Just Enough Record, Guard, and `switch`

Combine several rules into **one small program** so readers can verify them themselves, but with only two records and one classification method. This example performs no I/O other than printing results.

Create the file **`MinimalPatternExamples.java`**:

~~~java
public class MinimalPatternExamples {
    record Point(int x, int y) {}
    record Order(String id, Point destination) {}

    static String describe(Object input) {
        return switch (input) {
            case Order(var id, Point(var x, var y))
                    when x >= 0 && y >= 0 ->
                    "Order " + id + " -> " + x + "," + y;

            case Order(var id, var destination) ->
                    "Incomplete " + id;

            case String text when !text.isBlank() ->
                    "Text: " + text.trim();

            case String text -> "Blank text";
            case null -> "Missing";
            default -> "Unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Order("A-1", new Point(2, 3))));
        System.out.println(describe(new Order("A-2", null)));
        System.out.println(describe(new Order("A-3", new Point(-1, 1))));
        System.out.println(describe("  Java  "));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(describe(7));
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac --release 21 -encoding UTF-8 MinimalPatternExamples.java
java MinimalPatternExamples
~~~

Stdout:

~~~text
Order A-1 -> 2,3
Incomplete A-2
Incomplete A-3
Text: Java
Blank text
Missing
Unsupported
~~~

### Why Are Exactly These Seven Inputs Needed?

| Input | Rule Demonstrated | Result |
| --- | --- | --- |
| `Order("A-1", Point(2,3))` | Nested record matches and guard is true | `Order A-1 -> 2,3` |
| `Order("A-2", null)` | Nested `Point(...)` does not match when component is null | `Incomplete A-2` |
| `Order("A-3", Point(-1,1))` | Nested record matches but guard is false; fallback selected | `Incomplete A-3` |
| `"  Java  "` | `String` type pattern, guard is true, `trim()` | `Text: Java` |
| `"  "` | String matches, guard is false, later String case selected | `Blank text` |
| `null` | `case null` | `Missing` |
| `7` | Other type, falls into `default` | `Unsupported` |

**Note on the fallback name:** `"Incomplete"` in the example merges two different causes: a missing destination and coordinates failing the guard condition. This keeps the focus on **matching behavior**, not a complete business validation policy. If a real API needs separate failure reasons, separate the validation step or use a result type with an error code.

**Note on the static type:** `describe(Object input)` is chosen deliberately so readers can see that `Order`, `String`, `null`, and unknown types can all be passed in. For a dedicated API, declare a narrower parameter type when the domain contract allows.

## 7. Standalone Example 3 — Sealed Hierarchy and Exhaustive `switch`

To illustrate that **the compiler requires handling all types**, you need a model with a controlled set of variants. A minimal example only needs two events:

Create the file **`MinimalSealedSwitchDemo.java`**:

~~~java
public class MinimalSealedSwitchDemo {
    sealed interface Event permits Joined, Left {}

    record Joined(String user) implements Event {}
    record Left(String user) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Joined(var user) -> "Joined: " + user;
            case Left(var user) -> "Left: " + user;
            case null -> "No event";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Joined("Mai")));
        System.out.println(describe(new Left("Lan")));
        System.out.println(describe(null));
    }
}
~~~

Compile/run with **Java 21+**:

~~~bash
javac --release 21 -encoding UTF-8 MinimalSealedSwitchDemo.java
java MinimalSealedSwitchDemo
~~~

Output:

~~~text
Joined: Mai
Left: Lan
No event
~~~

**Key takeaway:** `Event` is a sealed interface that only permits `Joined` and `Left` to implement it directly in this model. The two record cases cover the non-null type set, and `case null` handles a null selector. Therefore, the `switch expression` **does not need `default`**.

If you add a third permitted subtype `Renamed` and recompile without adding a corresponding case, the `switch expression` is no longer exhaustive. The compiler will flag the issue. That is why you should **not add `default` unconditionally** to examples teaching exhaustiveness: `default` can hide the signal when extending the hierarchy.

A small example does not need to build an entire event bus system to demonstrate this property. All it takes is **a sealed type + two records + one switch**.

## 8. What Makes an Example "Minimal Yet Not Misleading"?

Keep the factors that can affect the conclusion:

**8.1. Static type of the selector.** `Object input`, `Event event`, or `String text` can lead to different exhaustiveness/dominance rules. If you only show the `switch` expression without stating the selector type, readers may draw the wrong conclusion.

**8.2. Null policy.** For `record Box(String value)`, `Box(var value)` can bind a `null` reference component; for `Box(String text)`, the nested type pattern `String text` does not match a `null` component. That difference is worth keeping in the example.

~~~java
// Java 21+, snippet; input has type Object and Box is already declared.
record Box(String value) {}

String result = switch (input) {
    case Box(String text) -> "Text " + text;
    case Box(var value) -> "Box without text";
    case null -> "Missing box";
    default -> "Other";
};
~~~

If `input` is `new Box(null)`, the first branch does not match, but the `Box(var value)` branch matches. No validation framework is needed to illustrate this rule.

**8.3. Variable scope.** With `instanceof`, a pattern variable is usable when the compiler can prove a match. Do not move `text` outside the proven path just to shorten the source.

**8.4. Case ordering.** Narrower/guarded branches must come before broader branches when there is a dominance relationship; changing the order can both cause compiler rejection and alter the classification semantics.

**8.5. Observable output.** `System.out.println` or assertions should accurately reflect the rule; do not print output that depends on date/time, randomness, locale, or I/O when they are not part of the lesson.

**8.6. Versions.** Do not label record patterns as "Java 17 stable". Type patterns for `instanceof` have been stable since Java 16; record patterns/switch patterns have been stable in Java 21.

## 9. A Workflow for Creating Minimal Examples in API Documentation

When you need to explain a bug, an API, or a language behavior, you can use the following workflow:

1. **Write a single question.** For example: "Does nested `Point(...)` match a null component?" Do not start with a complete application.
2. **Choose the target JDK version.** State Java 16 or Java 21 clearly at the top of the example to avoid accidentally using preview features or APIs outside the target.
3. **Keep data types minimal.** Use `record Box(Point point)` instead of a 20-class model; only add subtypes when the lesson needs to demonstrate exhaustiveness.
4. **Choose a short method.** One `describe` or `classify` method is enough; avoid side effects, builders, services, or dependency injection.
5. **Choose inputs that distinguish the branches.** At least one matching case and one non-matching case; add null/false guard if that is the focus.
6. **Compile and run.** Use `javac --release ...` and `java ...`; do not rely on memory to write stdout.
7. **Compare against expectations.** If the output is not as expected, determine whether you misunderstood the rule or the example accidentally included another condition.
8. **Trim away unaffected parts.** Remove logging, DB, concurrency, Spring, large datasets, and unnecessary helper classes; re-run after each cut to ensure the phenomenon remains.
9. **Preserve reproducibility details.** File/class name, JDK target, complete source or context for snippets, inputs, and output.
10. **Explain one primary cause.** End with "why" and the applicable conditions, rather than just copying the syntax.

**Final check:** Can the reader create a file with the exact name and run it with two commands? Is it clear which exact Java version is required? Is there at least one input that highlights the rule? Could any other rule accidentally produce the same result?

### "Minimal Reproduction" Example

Suppose a project reports: "An order is missing an address, yet `switch` enters the general branch." Do not rush to send the whole project. Shrink it down to two records and two cases, like `Order`/`Point` in section 6, with one input `new Order("A-2", null)` and stdout `Incomplete A-2`. That way, readers see that **a nested record pattern does not match null**, without noise from repositories, JSON mappers, or business services.

When submitting a bug report, include **expected vs actual** and the actual JDK used. If the issue only occurs after a Java upgrade, specify the relevant compiler/runtime versions; the source should still be kept minimal.

## 10. Presenting Examples in README, API Docs, and Code Reviews

### 10.1. Use a Consistent Structure

A compact documentation entry can follow this format:

~~~text
Feature: record pattern
Version: Java 21+
Input: new Point(2, 3)
Rule: Point(var x, var y) binds two int components
Source: snippet or link to a runnable file
Command: javac --release 21 ...; java ...
Result: one line with a deterministic value
Note: nested patterns do not match null components
~~~

This is an **information template**, not a runnable Java snippet. Not every entry needs all fields; keep the parts that affect self-verification.

### 10.2. Do Not Mix "Syntax Diagrams" with "Complete Programs"

~~~java
// SYNTAX PATTERN, NOT A STANDALONE FILE.
case Point(var x, var y) when x > 0 -> ...
~~~

An ellipsis `...` or undeclared variable names may be valid in an example **illustrating structure**, but cannot compile on their own. Label them clearly as syntax patterns/snippets. If you want to call something **runnable**, use complete source like sections 6 or 7 and leave no placeholders.

### 10.3. Tie Examples to Versions and Tests

Source documentation should be updated alongside the codebase. If examples are copied from passing test sources, the risk of **documentation drift** is lower than rewriting them manually. For projects with Javadoc support, consider **code snippets in Javadoc** (JEP 413, since Java 18) to present code in API docs and cross-reference tested sources. Do not assume every legacy project has a Javadoc tool that supports the snippet tag.

Whether using Markdown code fences or Javadoc snippets, **displaying syntax does not by itself prove the example runs correctly**. A compile/run test step in CI is still needed if the example is critical documentation or serves as an API contract.

### 10.4. Things to Leave Out of a First API Example

- Framework dependencies unrelated to pattern mechanics.
- Database/network calls or environment-dependent conditions.
- Deeply nested patterns when you only want to explain `instanceof`.
- Hard-to-read variable names like `a`, `b`, `c` when components carry domain meaning.
- Multiple new Java features appearing together unnecessarily.
- Overly long or randomly changing output; hard to compare against expectations.
- Unmeasured performance "optimizations" that distract from the syntax lesson.
- Caught and swallowed exceptions that make an example look successful even when the code fails.

A minimal example **does not have to be ideal production code**. A demo snippet may omit unrelated error handling, but must clearly state that limitation, especially when illustrating `null` or invalid data cases.

## 11. Automated Verification of Examples Without a Framework

For a basic tutorial, only `javac` and `java` are needed:

~~~bash
javac --release 16 -encoding UTF-8 MinimalInstanceofDemo.java
java MinimalInstanceofDemo

javac --release 21 -encoding UTF-8 MinimalPatternExamples.java
java MinimalPatternExamples

javac --release 21 -encoding UTF-8 MinimalSealedSwitchDemo.java
java MinimalSealedSwitchDemo
~~~

These commands **compile standalone sources**; each file name must match its `public class`. On JDK 21+ supporting `--release 16`, the first program can be compiled for Java 16. If running directly on JDK 16, it can also be compiled with `javac MinimalInstanceofDemo.java`.

A deeper check uses the **Java Compiler API** to compare targets: for a small program with `instanceof String text`, compilation with `--release 16` should succeed; for a snippet with record patterns and pattern `switch`, `--release 21` succeeds while `--release 17` is rejected. Experimental results on JDK 24 with a pair of reduced sources:

~~~text
type pattern, release 16: true
record switch, release 21: true
record switch, release 17: false
~~~

This is a **compilation-by-release check**, not a performance test or a guarantee that all dependencies/runtimes are supported. When the target source and runtime differ, you still need to check `java -version` of the execution environment.

### Why Not Just Run It Once in an IDE?

An IDE may be configured with a different language level/JDK than CI. A Java 21 example that "works" in the IDE can still fail if the project build uses `--release 17`. Including build commands in documentation helps others **reproduce** it and avoid misjudgment due to toolchain differences.

### Negative Examples Must Have a Purpose

If documentation wants to demonstrate a dominance error, create a snippet with **one** shadowed branch, label it `INTENTIONALLY INVALID`, and state clearly that the compiler will reject it. Do not put intentionally invalid source in `src/main/java` if it causes the main build to always fail. Instead, keep it in documentation or in dedicated compiler tests.

## 12. Common Mistakes When Writing Minimal Examples

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Snippet lacks a selector type | Unclear which rule the compiler applies | State `Object input` or a specific event type |
| Java version not stated | Java 17 readers cannot compile record patterns | Specify Java 16+/21+ and the `--release` command |
| Treating `var` as always having type `Object` | Misunderstanding type inference of record components | State the inferred type from the record declaration |
| Forgetting `null` selector/component | Runtime result differs from expectations | Add at least one null test if null is a focus |
| Placing a broad case before a narrow case | Compiler reports a dominated case | Move the narrow/guarded case earlier |
| Using `default` in an exhaustive sealed example | Hides missing-subtype errors when extending | Use specific cases, no `default` if already covered |
| Copying source with file name different from `public class` | Example does not compile | Synchronize file name, class name, and run command |
| Writing stdout by guessing | Learners waste time hunting nonexistent bugs | Run the real source and capture the exact output |
| Demonstrating syntax while doing I/O/transactions | Readers cannot tell what caused the result | Separate syntax patterns from business examples |
| Invalid snippet only says "compile fails" | Unclear whether failure has the right cause | State the expected diagnostic kind and a positive control |
| Keeping every detail after reducing a bug | MRE remains hard to understand | Remove unaffected parts; re-run after each cut |
| So short that special cases are lost | Readers infer wrong behavior | Keep necessary counterexample inputs like false guard/null |

## 13. Practice Exercises

### Exercise 1 — Complete an `instanceof` Snippet

Given `Object input = "Java";`. Write a Java 16+ expression using a type pattern to print the string's length without casting. If `input` is not a `String`, print `"Other"`.

**Answer:**

~~~java
// Java 16+, snippet.
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Other");
}
~~~

The output is `4`. This example only needs one source value and two branches. To test the non-matching case, change `input` to `42` and run again; the output will be `"Other"`.

### Exercise 2 — Nested Pattern and Null

Given:

~~~java
record Point(int x, int y) {}
record Box(Point point) {}
~~~

With `Object input = new Box(null);`, is `case Box(Point(var x, var y))` selected? Does `case Box(var point)` match?

**Answer:** The nested `Point(...)` branch does not match because the `point` component is null; the `Box(var point)` branch can match and the local variable `point` receives null. This is why an example of nested deconstruction should include one null input to distinguish the two kinds of patterns.

### Exercise 3 — Fix the `when` Example

~~~java
// INTENTIONALLY INVALID, input is Object.
String label = switch (input) {
    case String s -> "text";
    case String s when s.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

**Answer:** Place `case String s when s.isBlank()` before `case String s` to avoid dominance. To verify at runtime, use `" "` and `"A"`; these two inputs must produce different results.

### Exercise 4 — Which Example Is More Minimal?

To explain `instanceof String name`, option A uses a Spring Controller, JSON, a repository, and 8 classes; option B has one method taking `Object`, one `if`, and two representative inputs. Which option should be chosen for syntax documentation?

**Answer:** B. The Spring/repository components do not help prove `instanceof` and can introduce out-of-scope environment errors. However, B still must state the Java version, selector type, and how to verify the result. If the documentation is teaching **real Spring integration**, a larger example would be appropriate.

### Exercise 5 — Write a Focused Exhaustive Example

Create a sealed interface `Action` with two records `Start` and `Stop`. Write a `switch expression` that returns `"start"`/`"stop"` and handles `null`, without using `default`.

**Answer:**

~~~java
// Java 21+, declaration and method snippet within the same valid scope.
sealed interface Action permits Start, Stop {}
record Start() implements Action {}
record Stop() implements Action {}

static String name(Action action) {
    return switch (action) {
        case Start() -> "start";
        case Stop() -> "stop";
        case null -> "none";
    };
}
~~~

If a new permitted subtype is added, the `switch expression` must be revisited to ensure exhaustiveness. This example is just small enough: no need to create an event processing system.

## 14. Checklist Before Publishing an Example

Before putting a pattern example into API documentation, a README, or a technical answer, check:

- [ ] There is **one clear main takeaway** for the reader.
- [ ] The input variable and **static type** are declared or explained.
- [ ] The Java version and preview/final status are stated accurately.
- [ ] Snippets are labeled as **snippets**, and runnable examples have a **complete file/class**.
- [ ] `javac`/`java` commands are provided with the exact file name.
- [ ] Stdout or compiler error type has been **empirically verified**.
- [ ] There is at least one matching case; add non-match, false guard, and null if relevant to the lesson.
- [ ] No unnecessary I/O, dependencies, or business logic cluttering the pattern mechanism.
- [ ] `case` ordering, variable scope, and null semantics are not misrepresented.
- [ ] For a sealed hierarchy, `default` is not used merely to hide missing branches.
- [ ] Reproducible in the described environment; no hidden setup required.
- [ ] If the example is used in long-term CI/docs, the source is stored where it can be recompiled/retested.

## 15. Summary

**The best pattern example is not the one with the fewest characters**, but the one with the **fewest components that still proves a verifiable rule**.

- Teach type patterns with `instanceof` + a variable of static type `Object`.
- Teach record patterns with one simple `record`; nested record patterns only need two levels and one null input.
- Teach `switch` patterns with two types and one fallback; teach `when` with one clear boolean guard.
- Teach exhaustiveness with a **small sealed hierarchy** and a `switch` without `default`.
- Teach compiler errors with **one intentionally invalid example** plus the diagnostic cause, without mixing multiple errors.
- Clearly state the **Java version, complete source vs snippet, run commands, and actual output**.
- When an example becomes API documentation or a regression test, maintain **automated recompile/retest** capability to limit staleness.

**Official sources:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409); [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
