# Setting Completion Criteria for Refactoring Legacy Casts to Pattern Matching (Java 21)

## 1. Why Are Clear Completion Criteria Needed?

When refactoring legacy Java code from manual type checking and casting to **pattern matching**, the change may look very small:

```java
// Before
if (value instanceof String) {
    String text = (String) value;
    return text.trim();
}

// After
if (value instanceof String text) {
    return text.trim();
}
```

However, "**compiles successfully**" is not enough to declare a refactor complete. A change in branch order, `null` handling, exceptions, accessor methods, or side effects can cause **observable behavior to change**, even though the new syntax is shorter.

A **Definition of Done (DoD)** is a set of **verifiable** conditions before accepting a change. In the context of *Refactoring legacy casts*, the DoD should answer five questions:

1. **What exact parts were replaced?** Are the scope, API, and data flow clearly documented?
2. **Does the new code preserve the behavioral contract?** Outputs, `null`, exceptions, check order, side effects, and compatibility are all considered.
3. **Is there test evidence?** Boundary tests, regression tests, before–after comparisons, and the runtime environment are confirmed.
4. **Does it meet the project's quality standards?** Java version, compiler, static analysis, review, and CI.
5. **What if a risk materializes?** Intentional changes are approved, with monitoring and rollback capability in place.

**Version:** Pattern matching for `instanceof` has been standard since Java 16 (JEP 394); record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been standard since **Java 21**. When using record or `switch` patterns as in the examples in this article, target JDK 21+; no preview flags are needed.

## 2. Defining Scope and Baseline Behavior Before Editing

Before replacing casts, you need to determine **which behaviors must be preserved**. Do not change syntax and business rules at the same time without documenting it clearly.

### 2.1. Classifying Legacy Code

| Legacy code pattern | Refactoring direction | What must be proven |
| --- | --- | --- |
| `if (o instanceof String) { String s = (String) o; ... }` | `if (o instanceof String s) { ... }` | Matched type, result, and variable scope are the same as before |
| `if (!(o instanceof String)) return ...; String s = (String) o;` | `if (!(o instanceof String s)) return ...; ...` | Variable `s` is only used along the matched path |
| `if/else if` chain across multiple subtypes | Type patterns or pattern `switch` | Preserves specific branch precedence and `null` behavior |
| Direct `(String) o` without `instanceof` | **Do not replace mechanically** | Consider `ClassCastException`, `NullPointerException`, and API contract |
| Cast record then read one or more components | Type pattern, sometimes record pattern | Does not accidentally invoke accessors differently/extra times |
| Unchecked generic cast such as `(List<String>) o` | Review/adjust type design appropriately | Patterns cannot verify erased generic element types at runtime |

**Scope** should record: files/methods modified, cast forms in scope, branches preserved, affected call sites, target Java version, and business changes **not** belonging to the same PR.

### 2.2. Creating a Comparable Baseline

Save evidence before editing: baseline commit or revision, existing tests, execution results for representative cases, public contracts, logging patterns, and important exceptions. For logic with performance characteristics or side effects, record the appropriate metrics before making changes.

Never infer "no behavioral change" merely from two code snippets looking equivalent. A **behavioral contract** may include:

- Return value and result data type.
- Precedence among object types, especially subtypes and interfaces.
- Handling of `null`, blank strings, negative numbers, empty collections, or `null` components.
- Exception types and throw conditions that callers depend on.
- Number of accessor calls, order of side effects, data mutations, and I/O.
- Source/binary compatibility and system runtime requirements.

If an old behavior was actually a bug that needs fixing, **mark it as an intentional change** and require separate tests/approval; do not lump it into a "pure refactor".

## 3. Verifiable Definition of Done Criteria

The following table is a DoD framework for a PR migrating legacy casts to Java patterns. Each item requires **evidence**, not just a "done" answer.

| Category | Acceptance criterion | Suggested evidence |
| --- | --- | --- |
| **Scope** | Only identified casts are changed; no out-of-scope API or business changes | PR diff, list of methods/call sites |
| **Syntax & compatibility** | Code compiles at target Java level (e.g., `--release 21`); no unnecessary preview flags | Build command, CI log, JDK version |
| **Type safety** | No redundant casts remain in migrated branches; no unchecked/raw casts added to "bypass" the compiler | Diff review and compiler/static analysis |
| **Behavior** | Outputs and selected branches match the baseline for accepted input types | Regression tests, differential tests |
| **Null and exceptions** | All `null`/wrong-type cases preserve the contract, or changes are separately approved | Tests for `null`, `ClassCastException`, `NullPointerException` |
| **Pattern scope** | Pattern variables are only used on guaranteed-match paths; `&&`/`||` short-circuit correctly | Compiler and conditional tests |
| **Branch order/coverage** | No dominated cases; `switch` expressions are exhaustive; no branches accidentally dropped | Compiler, subtype tests |
| **Side effects** | Count/order of accessor reads, collection mutations, logging, and I/O are unchanged unless intended | Unit tests, mocks/counters/fakes |
| **Quality** | Project tests, lint/static analysis, review, and mandatory CI policies pass | CI status, review approval |
| **Deployability** | Monitoring and rollback plan appropriate to risk level | PR notes, release checklist |

A criterion should only be marked **PASS** when both the verification method and the result are clear. Not every project needs the exact same coverage/benchmark metrics; thresholds should fit existing policies and actual risk levels.

## 4. Preserving Behavior: Key Pitfalls

### 4.1. `instanceof` May Not Directly Replace a Direct Cast

Consider the legacy snippet:

```java
static int strictCast(Object input) {
    return ((String) input).length();
}
```

When `input` is an `Integer`, the cast throws `ClassCastException`. When `input == null`, casting to `String` succeeds (still `null`), but calling `length()` throws `NullPointerException`.

If replaced with:

```java
static int changedSemantics(Object input) {
    return input instanceof String text ? text.length() : -1;
}
```

then both `Integer` **and** `null` return `-1`. This is an **observable behavioral change**, no longer a pure refactor. It must not be considered complete if the old contract requires throwing an exception or callers rely on that exception.

**DoD Criterion:** For direct casts, explicitly document the status: either original behavior is preserved, or an intentional change is approved with new tests. Do not fake exceptions just to make tests pass without understanding the contract.

### 4.2. `null` and `switch` Branches

With an `if/else if` chain using `instanceof`, a `null` selector normally passes through the branches and falls into the fallback. When converting to a pattern `switch`, **`null` does not automatically fall into `default`**; to preserve the old fallback, add an appropriate `case null -> ...`:

```java
return switch (input) {
    case String text -> "text:" + text;
    case Integer number -> "int:" + number;
    case null -> "other";
    default -> "other";
};
```

If throwing `NullPointerException` for `null` is intentionally chosen, that is an API decision that must be documented, not an accidental side effect of changing the control-flow form.

### 4.3. Subtype Ordering and Dominance

Legacy code often prioritizes subtypes:

```java
if (input instanceof String) {
    return "string";
}
if (input instanceof CharSequence) {
    return "sequence";
}
return "other";
```

When converting to `switch`, `String` must remain before `CharSequence`:

```java
return switch (input) {
    case String text -> "string";
    case CharSequence chars -> "sequence";
    case null -> "other";
    default -> "other";
};
```

If `CharSequence` is moved above, Java 21 rejects `case String` below it as **dominated**. The compiler helps catch one class of errors, but you must still verify precedence among different guards that could overlap.

### 4.4. Flow Scoping of Pattern Variables

The following forms are valid:

```java
if (input instanceof String text && !text.isBlank()) {
    return text.trim();
}

if (!(input instanceof String text)) {
    return "not string";
}
return text.trim();
```

The two snippets are **separate examples inside a method returning `String`**, not placed sequentially in the same method with the same `text` variable name. In the first example, the right-hand side of `&&` only runs after a successful match. In the second example, the false branch returns, so the remaining path proves the variable is bound.

The following form **intentionally does not compile**:

```java
// WRONG: the right-hand side of || only runs when the match fails.
return input instanceof String text || text.isBlank();
```

**DoD Criterion:** Pattern variables are not used outside the matched path; combined conditions preserve the exact logic of `&&`, `||`, and `!`.

### 4.5. Record Deconstruction Can Invoke Accessors Additional Times

This is an important risk when *the primary goal is solely to eliminate casts*:

```java
record Counted(int value) {
    static int reads;
    public int value() {
        reads++;
        return value;
    }
}
```

Compare:

```java
static boolean typeOnly(Object input) {
    return input instanceof Counted;
}

static boolean deconstruct(Object input) {
    return input instanceof Counted(var n);
}
```

Both can return `true` for the same `Counted`, but **record patterns invoke the accessor** to extract components, incrementing the `reads` counter. If an accessor has side effects, throws an exception, or performs expensive computation, replacing a type check with a record pattern can unintentionally alter the result.

**DoD Criterion:** Apply record deconstruction only when components are actually needed and the side effects of calling accessors have been evaluated. When you only need to remove a cast, `input instanceof Counted c` is usually the safer conversion.

### 4.6. Generics and Mutable Data

A cast such as `(List<String>) input` cannot be fully proven safe by runtime type checking alone due to **type erasure**. `List<?>` checks the container type, not every element's type; do not replace one unchecked cast with another unchecked cast without explicitly documenting the risk.

Pattern matching also **does not copy** objects or components. If legacy logic passed/returned the same mutable `List` or array, the new code may still expose the same reference. Only create a defensive copy if the contract requires it and tests confirm the impact.

## 5. Designing Tests as Acceptance Criteria

Tests should be layered. No fixed coverage percentage alone proves a refactor is correct; prioritize high-risk logic paths.

### 5.1. Before–After Test Matrix

For a method dispatching on `String`, `Integer`, and `Point`, prepare at minimum:

| Input group | Example | What to compare |
| --- | --- | --- |
| Normal matching types | `"Java"`, `7`, `Point(2,3)` | Return value, formatting |
| Boundaries within same type | `""`, `"   "`, `-2`, `Point(-1,0)` | Blank/negative/zero conditions |
| Different but related type | `StringBuilder` when `CharSequence` exists | Precedence and fallback |
| Unrelated type | `new Object()` | Fallback, exception |
| `null` value | `null` | Fallback or exception per contract |
| `null` component | Record with a `null` reference component | Nested pattern/guard and getter |
| Unguarded cast | `(String) Integer.valueOf(42)` | Is `ClassCastException` preserved? |
| Side effect | Record accessor counting invocations | No extra reads/side operations |
| Generic container | `List<String>`, `List<Integer>` | No false assumptions about element types |
| Subclass/extension | Existing subtype or sealed hierarchy | No lost branch, no changed precedence |

Tests typically consist of three types of evidence:

1. **Regression tests** re-running known important scenarios.
2. **Differential tests** feeding the same inputs to legacy code and refactored code; comparing outputs and, when required by the contract, exception types and side effects.
3. **Negative/boundary tests** actively checking `null`, wrong types, subtypes, boundaries, faulty components, and true/false guards.

For functions involving randomness, time, I/O, or concurrent data, control nondeterministic sources before comparing directly. If a test only compares output `String`s, it does not prove equivalence in exceptions, logs, dependency call counts, or race conditions.

### 5.2. Coverage Level to Prove

For a dispatch chain, every meaningful branch must have at least one test proving it is selected. Every guard needs true and false cases; `null` must have a clear expectation. When a module has a coverage policy, maintain the existing threshold. If none exists, set thresholds based on risk and the branches that genuinely need protection, rather than asserting an arbitrary number like "100% coverage is enough".

**Exit criterion:** If a test detects a difference, classify it as a refactoring bug or a requested change; do not adjust expected output just to make tests pass without explaining the root cause.

## 6. Complete Java 21 Program: Self-Comparing Legacy and New Code

Create the file **`RefactorDoneDemo.java`** below. The program has three implementations: legacy code, a type-pattern refactor, and a `switch`-pattern refactor. It checks **parity** across multiple inputs, then intentionally demonstrates two behavioral differences that regression tests must catch.

```java
import java.util.function.IntSupplier;

public class RefactorDoneDemo {
    record Point(int x, int y) {}
    record Counted(int value) {
        static int reads;
        public int value() {
            reads++;
            return value;
        }
    }

    static String legacy(Object input) {
        if (input instanceof String) {
            String text = (String) input;
            return text.isBlank() ? "blank" : "text:" + text.trim();
        }
        if (input instanceof Integer) {
            Integer number = (Integer) input;
            return "int:" + number;
        }
        if (input instanceof Point) {
            Point point = (Point) input;
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String refactored(Object input) {
        if (input instanceof String text) {
            return text.isBlank() ? "blank" : "text:" + text.trim();
        }
        if (input instanceof Integer number) {
            return "int:" + number;
        }
        if (input instanceof Point point) {
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String asSwitch(Object input) {
        return switch (input) {
            case String text ->
                    text.isBlank() ? "blank" : "text:" + text.trim();
            case Integer number -> "int:" + number;
            case Point point -> "point:" + point.x() + "," + point.y();
            case null -> "other";
            default -> "other";
        };
    }

    static int strictCast(Object input) {
        return ((String) input).length();
    }

    static int changedSemantics(Object input) {
        return input instanceof String text ? text.length() : -1;
    }

    static String outcome(IntSupplier supplier) {
        try {
            return "returned " + supplier.getAsInt();
        } catch (RuntimeException error) {
            return error.getClass().getSimpleName();
        }
    }

    static boolean typeOnly(Object input) {
        return input instanceof Counted;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Counted(var n);
    }

    public static void main(String[] args) {
        Object[] cases = {
                "  Java  ", "", "   ", 7, -2, new Point(2, 3),
                new Point(-1, 0), new StringBuilder("x"), null
        };
        for (Object input : cases) {
            String expected = legacy(input);
            String actual = refactored(input);
            String alternate = asSwitch(input);
            if (!expected.equals(actual) || !expected.equals(alternate)) {
                throw new AssertionError("Behavior mismatch for " + input);
            }
            System.out.println(expected);
        }
        System.out.println("PARITY PASS: " + cases.length);

        System.out.println("cast 42: " + outcome(() -> strictCast(42)));
        System.out.println("pattern 42: " + outcome(() -> changedSemantics(42)));
        System.out.println("cast null: " + outcome(() -> strictCast(null)));
        System.out.println("pattern null: " + outcome(() -> changedSemantics(null)));

        Counted counted = new Counted(4);
        System.out.println("type-only: " + typeOnly(counted)
                + ", reads=" + Counted.reads);
        System.out.println("deconstruct: " + deconstruct(counted)
                + ", reads=" + Counted.reads);
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 RefactorDoneDemo.java
java RefactorDoneDemo
```

**Exact stdout:**

```text
text:Java
blank
blank
int:7
int:-2
point:2,3
point:-1,0
other
other
PARITY PASS: 9
cast 42: ClassCastException
pattern 42: returned -1
cast null: NullPointerException
pattern null: returned -1
type-only: true, reads=0
deconstruct: true, reads=1
```

### 6.1. Reading the Results Correctly

- Nine tests in the loop compare `legacy`, `refactored`, and `asSwitch`. If any mismatch occurs, the program throws `AssertionError`; reaching `PARITY PASS: 9` means all nine cases passed.
- Blank and whitespace-only `String`s are tested separately, avoiding the assumption that testing a normal string is enough.
- `StringBuilder` is a subtype of `CharSequence` but not `String`; it enters the fallback just like the legacy code.
- `null` falls through to `"other"` in both the legacy `if` chain and the `switch` expression thanks to `case null`.
- The `strictCast` and `changedSemantics` cases **intentionally differ**: the direct cast throws exceptions on wrong type or `null`, whereas the pattern version returns `-1`. This signals **NOT DONE for a contract-preserving refactor**, unless the change has been approved.
- `typeOnly` only checks the class; `deconstruct` invokes the `Counted.value()` accessor, incrementing `reads` from 0 to 1. If an accessor has side effects, evaluate them before choosing a record pattern.

### 6.2. Why Is This Test Not Yet Absolute Proof?

Nine cases are an illustrative sample, not exhaustive coverage of every input or system state. For real APIs, you must also test subtypes, generic types, external dependencies, exceptions, concurrency, and the appropriate deployment environment. The program only proves the specific **inputs that were tried**, and does not replace code review or the system's contract.

Using `throw new AssertionError` directly (instead of the `assert` statement) ensures the comparison runs even when the JVM is started without `-ea`. If the project uses JUnit/TestNG, convert the parity matrix into automated tests run in CI.

## 7. Compile-Time Errors to Check When Refactoring

Runtime logic errors are not the only concern. Pattern syntax introduces additional compile-time safety rules.

### 7.1. Pattern Variable Out of Scope

```java
// INTENTIONALLY WRONG — does not compile:
return input instanceof String text || text.isBlank();
```

When `instanceof` returns `false`, the right-hand side of `||` is evaluated, yet `text` has not been bound. The right way if you want a non-blank string:

```java
return input instanceof String text && !text.isBlank();
```

### 7.2. Dominated Type Pattern Branch

```java
// INTENTIONALLY WRONG — does not compile:
return switch (input) {
    case CharSequence chars -> "sequence";
    case String text -> "string";
    case null -> "null";
    default -> "other";
};
```

Every `String` is a `CharSequence`, so the first case subsumes the second. Place `case String` before `case CharSequence`.

### 7.3. Difference Between `var` and Typed Components in Record Patterns

`Point(var x, var y)` binds both `int` values, with no `null` risk on primitive components. However, `record Person(String name) {}` can contain `name == null`: `Person(var name)` matches and binds `null`, whereas `Person(String name)` does not match a `null` component. When refactoring from accessors to nested patterns, test the `null`-component case to ensure the desired behavior.

### 7.4. Do Not Use Pattern Matching to Assert Parameterized Generics

`obj instanceof java.util.List<?> list` can verify that the object is a `List`, but cannot confirm that all elements are `String`. If legacy code had an unchecked cast, a refactor is only sound when API design/tests verify the data and ensure no new unchecked warnings are introduced.

**Completion condition:** Zero compiler errors, zero new risky warnings, and zero unexplained behavioral changes; the build at the actual Java target level is verified by CI.

## 8. Post-Coding Verification Checklist

You can attach this checklist directly to a PR, with each item requiring a status and evidence:

- [ ] Identify the baseline commit, refactored methods, and out-of-scope behaviors.
- [ ] List replaced casts; any casts that must remain have a documented reason.
- [ ] Compile with the project's official Java target; do not add preview flags unless required.
- [ ] Preserve results for normal inputs and contracted types/subtypes.
- [ ] Include dedicated tests for `null`, blank/empty, boundaries, and wrong types.
- [ ] Compare key exceptions with the legacy version; any exception change must be approved.
- [ ] Check `if/else` branch order and dominance/exhaustiveness when converting to `switch`.
- [ ] Check `&&`, `||`, negation, pattern variable scope, and `when` guards.
- [ ] Evaluate accessor call counts, side effects, mutations, and concurrent dependencies if applicable.
- [ ] Do not introduce raw/unchecked casts or false assumptions about generic element types.
- [ ] Relevant tests have run; CI and static analysis pass per project policy.
- [ ] Diff is easy to review; no unapproved business changes mixed into the refactor.
- [ ] Non-equivalent cases are resolved or explicitly documented as intentional changes.
- [ ] Post-merge/deploy monitoring plan and rollback procedure are ready if impact is significant.

The checklist is not a formality. If an item does not apply (for example, no mutable data or no `switch` conversion), mark **N/A with a reason** rather than claiming to have tested something that does not exist.

## 9. Automating Criteria with Build, Test, and CI

A simple workflow:

1. **Compile gate:** Build on the target JDK, at least `javac --release 21` for programs using Java 21. In real projects, use the Maven/Gradle configuration already established in the repository.
2. **Regression gate:** Run the existing test suite plus new tests for the modified branches.
3. **Diff gate:** Run the same input suite against the baseline and the refactored version; compare outputs and exception contracts. If side effects exist, add spies/fakes/counters.
4. **Static gate:** Run static analysis/lint tools per project policy, focusing on unchecked casts, unreachable/dominated cases, and API requirements.
5. **Review gate:** Reviewers can see the change table, tested edge cases, and rationale for using type patterns/record patterns/`switch`.
6. **Release gate:** If the change touches high-risk production behavior, document error monitoring, metrics, and a rollback plan.

For the example file in section 6, these two commands are enough to verify with the JDK:

```bash
javac --release 21 RefactorDoneDemo.java
java RefactorDoneDemo
```

For repositories using Maven Wrapper or Gradle Wrapper, use only commands that actually exist and fit the environment, such as `./mvnw test` or `./gradlew test` on systems supporting the corresponding shell; these commands are **not guaranteed to exist by default** in every project.

### Criteria for CI Pass

A PR only has sufficient evidence when the pipeline actually runs on the reviewed commit, not from tests that "passed earlier" locally on a different version of the code. If CI runs tests conditionally, ensure the changed code is covered by the appropriate job. Do not disable failing jobs or lower quality-gate thresholds just to mark a refactor as done.

In multi-Java-version environments, distinguish between using a newer JDK to compile with `--release 21` and running integration tests on the system's actual runtime. If deployment uses Java 21, verify at least one environment running Java 21 in the appropriate testing stage.

## 10. Review, Rollout, and Rollback Criteria

### Reviewing Changes

The PR description should be brief and clear:

- **Before/After:** one representative example, no need to paste the entire diff.
- **Preserved contract:** outputs, `null`, exceptions, branch order, side effects.
- **Intentional changes:** clearly state the reason and tests instead of labeling everything "refactor".
- **Test evidence:** commands/jobs run and input groups verified.
- **Remaining risks:** uncovered areas and impact mitigation.

Reviewers should prioritize checking changes that can hide inside shorter code: a direct cast replaced by a fallback, a `switch` missing `case null`, reordered conditions, or a record pattern invoking an accessor extra times.

### Rollout and Rollback Capability

For small refactors with no contract changes and full tests, deployment can follow the standard process. For refactors spanning multiple modules, runtimes, or APIs, consider splitting PRs by functional group, monitoring existing error metrics post-deploy, keeping commits/releases easy to revert, and maintaining a safe fallback path when needed.

**Rollback does not mean keeping legacy code forever.** It is a way to protect users if an untested discrepancy is discovered; after analyzing the root cause and adding tests, the fixed refactor can be reapplied.

## 11. When Must It Be Marked NOT DONE?

A change has not met the DoD if it encounters at least one of the following situations without resolution or approval:

| Situation | Why is it not done? |
| --- | --- |
| Only compiled locally, behavior not tested | Lacks evidence of output/branch equivalence |
| Changed direct cast from throwing an exception to a fallback | Altered behavioral contract without confirmation |
| Converted `if/else` to `switch` causing `null` to throw NPE | Lost previous handling branch |
| Used record deconstruction causing extra accessor calls | Side effects or exceptions may differ |
| Reordered parent/child type patterns | Compiler reports dominance or precedence changed |
| Wrote tests with `assert` but ran without `-ea` | Test assertions may not execute |
| Tested only a single valid string | Does not cover blank, null, wrong type, or subtype |
| New unchecked warning ignored without justification | Unresolved type-safety risk |
| Updated test expectations to match new output just to pass | Lost baseline without evaluating business change |
| CI passed on an older commit, new commit not run | Merged version is unverified |
| Unreviewed out-of-scope changes remain | Cannot conclude this is a pure refactor |

**Completion decision:** Only confirm **DONE** when scope is clear, behaviors are preserved or changes are approved, testing matches risk, required builds and CI pass, review is complete, and deployment risks have controls in place.

## 12. Self-Check Questions

**1.** Why is "no casts left in the diff" insufficient as a DoD?  
*Answer:* Because the new code can still alter `null` handling, exceptions, branch precedence, or side effects.

**2.** Does refactoring a direct `(String) input` to `input instanceof String s ? ... : fallback` always preserve semantics?  
*Answer:* No. A direct cast can throw `ClassCastException` on the wrong type, whereas the pattern can enter the fallback.

**3.** Why does replacing an `if/else` chain with `switch` require testing `null`?  
*Answer:* `instanceof` with `null` evaluates to `false`, whereas a pattern `switch` does not route `null` to `default` automatically; `case null` is needed to preserve the fallback.

**4.** When refactoring legacy casts, when should you choose a type pattern over a record pattern?  
*Answer:* When you only need to identify the type and eliminate the cast. A record pattern is useful when you genuinely need the components and have evaluated accessors/side effects.

**5.** Does testing nine inputs and getting `PARITY PASS: 9` prove absolute equivalence?  
*Answer:* No. It only proves the results for those nine tested cases; exceptions, state, other inputs, and runtime dependencies still remain.

**6.** If a different output is found because an old bug was fixed, must that change be discarded?  
*Answer:* Not necessarily; however, the behavioral change must be separated/documented clearly, with expected behavior and appropriate approval.

**7.** Why should there be regression tests for `ClassCastException` and `NullPointerException`?  
*Answer:* Callers may depend on exception behavior; pattern matching does not automatically guarantee the same exception type or conditions as a legacy cast.

**8.** Why might high test coverage still be insufficient?  
*Answer:* Coverage does not fully prove expected behavior, especially for boundary inputs, side-effect ordering, API compatibility, and unexpected data.

**9.** If `case CharSequence` appears before `case String` in Java 21, how is the DoD affected?  
*Answer:* The compiler reports dominance; the compile gate fails.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
