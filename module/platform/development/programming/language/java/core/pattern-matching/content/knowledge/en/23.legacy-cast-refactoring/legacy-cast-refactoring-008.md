# Comparing the Diff Before and After Refactoring Legacy Casts to Pattern Matching (Java 21)

## Objectives

In the **Legacy Cast Refactoring** topic, the goal of migrating from manual type checks and casts to **pattern matching** is not merely to reduce the number of lines of code. A refactoring is acceptable when **the diff clearly shows the structural change, while the observable behavior before and after remains equivalent** within the committed scope.

This lesson guides you on reading a unified diff, comparing each branch before and after, detecting changes regarding `null`, condition ordering, scope, and fallbacks, and then verifying with a runnable Java 21 program.

After this lesson, you will be able to:

- Read `-`/`+` markers in a unified diff and distinguish "syntactic changes" from parts that could potentially **change logic**.
- Compare the classic `instanceof` + cast pattern with type patterns and nested record patterns.
- Build a **control-flow path** table to confirm valid branches, missing-data branches, and the default branch.
- Verify behavior parity with tests that have an independent **expected result** rather than trusting a shorter diff.
- Review safely before introducing a refactoring into a codebase with many callers.

**Version:** Type patterns for `instanceof` have been standard since Java 16 (JEP 394); **nested record patterns** have been standard since Java 21 (JEP 440). This lesson's program uses `javac --release 21` and does not require enabling preview features.

## 1. A Refactoring Diff Must Answer Two Different Questions

**Question 1 — what changed in the code?** The diff shows which lines were removed and which lines were added. It helps reviewers see that manual casts disappeared, pattern variables are bound directly, and branches may have been reordered.

**Question 2 — did the program's behavior change?** A diff cannot prove this on its own. A refactoring may look shorter while inadvertently changing the result when the input is `null`, a nested record is missing, a boundary condition is wrong, or a fallback branch is dropped.

Therefore, compare the diff along two axes:

| Review Axis | What Must Be Determined |
|---|---|
| **Code structure** | How were type checks, casts, accessors, intermediate variables, and guards transformed? |
| **Behavioral contract** | Given the same input, are outputs, exceptions, and side effects preserved? |
| **Control-flow paths** | Which branch does an input enter before and after? Is any branch newly skipped? |
| **Boundaries** | Are `null`, wrong types, exact-threshold conditions, and missing data still handled the old way? |
| **Maintainability** | Is the new version clear in intent, with fewer repeated casts, an easy-to-understand scope, and no hidden logic? |

Even a syntactic change still requires verification, especially when a refactoring is "conveniently" combined with changing business conditions.

## 2. Minimal Diff: Type Pattern Replacing Cast

Legacy pattern:

```java
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "";
```

In Java 16+, you can write:

```java
if (input instanceof String text) {
    return text.trim();
}
return "";
```

**Illustrative unified diff:**

```diff
-if (input instanceof String) {
-    String text = (String) input;
+if (input instanceof String text) {
     return text.trim();
 }
 return "";
```

This is a simple case: `instanceof String` still classifies the same type, and the `text` variable only exists when the pattern matches. An explicit cast is no longer needed.

Do not interpret `-` as "buggy" code and `+` as "correct" by default. They only indicate the before/after content. The reviewer's task is to determine **whether the set of inputs that can enter the branch has changed**.

## 3. Practical Case: Legacy Cast with Nested Records

Suppose the application data has the following records:

```java
record Reporter(String name, String team) {}
record Order(String id, Reporter reporter, int total) {}
record OrderEvent(Order order) {}
record AuditEvent(String code) {}
```

The sample application classifies events as follows:

- `OrderEvent` with non-`null` `Order` and `Reporter`, team `VIP`, and `total >= 1000` → `PRIORITY:<id>`.
- Remaining `OrderEvent` instances (including missing order/reporter) → `STANDARD`.
- `AuditEvent` → `AUDIT:<code>`.
- Selector of another type or `null` → `IGNORED`.

**This is a simulated policy** and does not represent a real-world order rule.

### Before Refactoring: Type Check, Cast, and Accessor Calls

```java
static String legacy(Object input) {
    if (input instanceof OrderEvent) {
        OrderEvent event = (OrderEvent) input;
        Order order = event.order();
        if (order != null && order.reporter() != null
                && "VIP".equals(order.reporter().team())
                && order.total() >= 1000) {
            return "PRIORITY:" + order.id();
        }
        return "STANDARD";
    }
    if (input instanceof AuditEvent) {
        AuditEvent event = (AuditEvent) input;
        return "AUDIT:" + event.code();
    }
    return "IGNORED";
}
```

Points to note before editing:

1. A root selector that is not an `OrderEvent` can reach the `AuditEvent` branch.
2. Once the root is an `OrderEvent`, even if an inner component is missing, the result is always either `PRIORITY` or `STANDARD`.
3. The condition `order != null && order.reporter() != null` ensures that calling `reporter().team()` does not dereference when the reporter is missing.
4. `"VIP".equals(...)` is safe when `team == null`.
5. The comparison threshold is `>= 1000`; exactly 1000 must be treated as priority.
6. An `AuditEvent` with a null code still produces the string `AUDIT:null` via Java string concatenation.
7. A null selector fails both `instanceof` statements and falls through to `IGNORED`.

### After Refactoring: Nested Record Pattern and Explicit Fallback

```java
static String modern(Object input) {
    if (input instanceof OrderEvent(
            Order(var id, Reporter(var name, var team), var total))
            && "VIP".equals(team) && total >= 1000) {
        return "PRIORITY:" + id;
    }
    if (input instanceof OrderEvent event) {
        return "STANDARD";
    }
    if (input instanceof AuditEvent(var code)) {
        return "AUDIT:" + code;
    }
    return "IGNORED";
}
```

**The most important point of the new version is the `OrderEvent event` fallback branch.** The nested record pattern only matches when both `Order` and `Reporter` exist. If you only keep the nested `PRIORITY` branch and forget the `STANDARD` fallback, `OrderEvent(null)` will fall through to `IGNORED`, differing from the old version.

In this code, `name` and `event` are bound but unused. That is valid; if the actual design does not require deep deconstruction, a shallower pattern can be chosen. Do not remove a required layer during refactoring if it serves as a structural or `null` check on the data.

## 4. Unified Diff: Seeing Exactly What Changed

The following diff describes **the representative changed segments** between the two methods `legacy` and `modern`. Removed lines have `-`, and added lines have `+`.

```diff
-    if (input instanceof OrderEvent) {
-        OrderEvent event = (OrderEvent) input;
-        Order order = event.order();
-        if (order != null && order.reporter() != null
-                && "VIP".equals(order.reporter().team())
-                && order.total() >= 1000) {
-            return "PRIORITY:" + order.id();
-        }
+    if (input instanceof OrderEvent(
+            Order(var id, Reporter(var name, var team), var total))
+            && "VIP".equals(team) && total >= 1000) {
+        return "PRIORITY:" + id;
+    }
+    if (input instanceof OrderEvent event) {
         return "STANDARD";
     }
-    if (input instanceof AuditEvent) {
-        AuditEvent event = (AuditEvent) input;
-        return "AUDIT:" + event.code();
+    if (input instanceof AuditEvent(var code)) {
+        return "AUDIT:" + code;
     }
     return "IGNORED";
```

**Do not treat this as a complete patch to apply with `git apply`**: it is an extracted method body meant to explain the meaning. Exact repository diffs are generated by Git (Section 8).

### Reading the Diff Change by Change

| Location | Before | After | What the Reviewer Must Confirm |
|---|---|---|---|
| Root check | `instanceof OrderEvent` + cast | `instanceof OrderEvent(...)` | Does the narrower branch miss an OrderEvent with missing components? |
| Data access | `event.order()`, `order.reporter()` | `Order(..., Reporter(...), ...)` | Are null nested records still handled properly? |
| Team condition | `"VIP".equals(order.reporter().team())` | `"VIP".equals(team)` | Does it remain null-safe and use the same comparison? |
| Numeric condition | `order.total() >= 1000` | `total >= 1000` | Are the threshold and the `=` sign preserved? |
| Result construction | `order.id()` | `id` | Is the component bound from the same source with the same behavior for a null ID? |
| OrderEvent fallback | `return "STANDARD"` inside block | Subsequent `instanceof OrderEvent` branch | Can it be entered before the Audit and default branches? |
| AuditEvent | Manual cast | `AuditEvent(var code)` | Is a null code component still bound? |
| Default | `IGNORED` | `IGNORED` | Do a null root and other types still reach here? |

This table helps separate **reduced syntax** from **logic at risk of changing**.

## 5. Complete Java 21 Example for Before/After Comparison

Save the entire program as **`PatternCastDiffDemo.java`**:

```java
import java.util.Objects;

public class PatternCastDiffDemo {
    record Reporter(String name, String team) {}
    record Order(String id, Reporter reporter, int total) {}
    record OrderEvent(Order order) {}
    record AuditEvent(String code) {}

    static String legacy(Object input) {
        if (input instanceof OrderEvent) {
            OrderEvent event = (OrderEvent) input;
            Order order = event.order();
            if (order != null && order.reporter() != null
                    && "VIP".equals(order.reporter().team())
                    && order.total() >= 1000) {
                return "PRIORITY:" + order.id();
            }
            return "STANDARD";
        }
        if (input instanceof AuditEvent) {
            AuditEvent event = (AuditEvent) input;
            return "AUDIT:" + event.code();
        }
        return "IGNORED";
    }

    static String modern(Object input) {
        if (input instanceof OrderEvent(
                Order(var id, Reporter(var name, var team), var total))
                && "VIP".equals(team) && total >= 1000) {
            return "PRIORITY:" + id;
        }
        if (input instanceof OrderEvent event) {
            return "STANDARD";
        }
        if (input instanceof AuditEvent(var code)) {
            return "AUDIT:" + code;
        }
        return "IGNORED";
    }

    static void check(String label, Object input, String expected) {
        String before = legacy(input);
        String after = modern(input);
        if (!Objects.equals(before, after) || !Objects.equals(expected, after)) {
            throw new AssertionError(label + ": legacy=" + before
                    + ", modern=" + after + ", expected=" + expected);
        }
        System.out.println(label + " => " + after);
    }

    public static void main(String[] args) {
        check("vip boundary", new OrderEvent(new Order(
                "O1", new Reporter("An", "VIP"), 1000)), "PRIORITY:O1");
        check("vip high", new OrderEvent(new Order(
                "O2", new Reporter("Binh", "VIP"), 1500)), "PRIORITY:O2");
        check("not vip", new OrderEvent(new Order(
                "O3", new Reporter("Chi", "REGULAR"), 1500)), "STANDARD");
        check("below threshold", new OrderEvent(new Order(
                "O4", new Reporter("Dung", "VIP"), 999)), "STANDARD");
        check("null reporter", new OrderEvent(new Order(
                "O5", null, 1500)), "STANDARD");
        check("null order", new OrderEvent(null), "STANDARD");
        check("null team", new OrderEvent(new Order(
                "O6", new Reporter("Em", null), 1500)), "STANDARD");
        check("null id", new OrderEvent(new Order(
                null, new Reporter(null, "VIP"), 1500)), "PRIORITY:null");
        check("audit", new AuditEvent("A1"), "AUDIT:A1");
        check("audit null code", new AuditEvent(null), "AUDIT:null");
        check("wrong type", "text", "IGNORED");
        check("root null", null, "IGNORED");
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 PatternCastDiffDemo.java
java PatternCastDiffDemo
```

**Verified output:**

```text
vip boundary => PRIORITY:O1
vip high => PRIORITY:O2
not vip => STANDARD
below threshold => STANDARD
null reporter => STANDARD
null order => STANDARD
null team => STANDARD
null id => PRIORITY:null
audit => AUDIT:A1
audit null code => AUDIT:null
wrong type => IGNORED
root null => IGNORED
```

In `check(...)`, the program **not only** compares `legacy(input)` and `modern(input)` but also compares both against the `expected` result string. This reduces the risk of "both versions being wrong together". If they differ, an `AssertionError` is thrown and the program cannot print the full output above.

Keeping `legacy` and `modern` in the same class is only for **demonstration and regression checking**. In a real codebase, the old version is typically kept in Git history and only a single production implementation is retained after the refactoring is approved.

## 6. Path Table: Proving the Fallback Is Not Lost

You can re-read the results from a *control-flow diff* perspective:

| Case | Path Before | Path After | Result |
|---|---|---|---|
| VIP and total = 1000 | OrderEvent → guard true | Nested OrderEvent → guard true | `PRIORITY:O1` |
| VIP and total = 999 | OrderEvent → guard false → STANDARD | Nested match but `total >= 1000` false → OrderEvent fallback | `STANDARD` |
| Null reporter | OrderEvent → `reporter != null` false | Nested `Reporter(...)` does not match → OrderEvent fallback | `STANDARD` |
| Null order | OrderEvent → `order != null` false | Nested `Order(...)` does not match → OrderEvent fallback | `STANDARD` |
| Null team | `"VIP".equals(null)` is false | `team` binds null; same safe comparison | `STANDARD` |
| Null ID, eligible | `"PRIORITY:" + order.id()` | `"PRIORITY:" + id` | `PRIORITY:null` |
| Audit null code | Cast AuditEvent; concatenate null code | `AuditEvent(var code)` binds null | `AUDIT:null` |
| Wrong type or null root | No branch matches | No branch matches | `IGNORED` |

This is the **most valuable** part of a review: not just reading the patch line by line, but also seeing whether the **input partitioning** is preserved.

### Why Does `AuditEvent(var code)` Still Accept a Null Code?

In Java 21, the record pattern `AuditEvent(...)` requires a **non-null AuditEvent object**. However, the `var code` pattern directly on a component can bind the value `null`. Therefore, it preserves the string concatenation behavior with null just like the version calling `event.code()`.

Conversely, `OrderEvent(Order(...))` and `Reporter(...)` are **nested record patterns**, which do not match when the record at that level is null. That is why a broader `OrderEvent` branch is necessary to reproduce `STANDARD`.

## 7. Diffs That "Look Clean" but Change Behavior

### 7.1. Deleting the Fallback Branch Entirely

**Semantically wrong for the example requirements:**

```java
if (input instanceof OrderEvent(
        Order(var id, Reporter(var name, var team), var total))
        && "VIP".equals(team) && total >= 1000) {
    return "PRIORITY:" + id;
}
return "IGNORED"; // OrderEvent missing reporter is now IGNORED!
```

The old version returns `STANDARD` for every ineligible OrderEvent. Adding the fallback `if (input instanceof OrderEvent ...) return "STANDARD";` is necessary. A shorter patch that drops a branch is not a behavior-preserving refactoring.

### 7.2. Replacing a Null-Safe Comparison with a Call That May Throw

```java
// Preserve semantics when team may be null:
"VIP".equals(team)

// Not equivalent if team == null:
team.equals("VIP")
```

The second version throws a `NullPointerException` when `team` is null. The diff must be reviewed even on lines that merely swap the two operands of `equals`.

### 7.3. Changing the Evaluation Order of a Boolean Expression

```java
// Safe guard if text may be null:
text != null && text.startsWith("A")

// May throw an exception when text is null:
text.startsWith("A") && text != null
```

`&&` and `||` in Java short-circuit in order. Moving a condition or calling a helper in a different position can change whether a method gets executed.

### 7.4. Changing a Threshold During Refactoring

```java
// Before: includes total = 1000.
total >= 1000

// After: excludes total = 1000.
total > 1000
```

If you intentionally change a policy, separate the behavior-changing commit and its tests rather than mixing it into a pattern syntax migration commit.

### 7.5. Changing Variable Scope and Missing a Path

A pattern variable is only in scope where the compiler determines the pattern has matched:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
// Cannot arbitrarily use 'text' here: the pattern may not have matched.
```

A refactoring may need to restructure control flow, such as using a *guard clause*, but must ensure that early-exit branches and the remaining path preserve the exact result.

### 7.6. Adding or Removing Calls to an Accessor with Side Effects

In a regular record, the compiler-generated accessor simply returns the component. However, an author can **explicitly declare an accessor** with custom logic. If the old code calls `order.reporter()` twice and the new pattern deconstructs once, the observable effect may differ if the customized accessor has side effects or if internal referenced data changes unexpectedly.

**Recommendation:** only consider a refactoring behavior-preserving after understanding the relevant accessors, exceptions, and side effects. Do not rely solely on both versions returning the same string in a sample test suite.

## 8. How to Inspect Real Diffs in Git

When performing a refactoring in a repository, Git helps track the exact regions of code that changed. The following commands are **usage instructions**, not the output of running the example in Section 5.

View the diff of the edited file (replace the example path with the actual file):

```bash
git diff --unified=12 -- src/main/java/example/EventRouter.java
```

The `--unified=12` option keeps extra surrounding context so you can see fallback branches and `if` ordering. For long diffs, you can use word diff to see the exact syntactic changes:

```bash
git diff --word-diff=plain -- src/main/java/example/EventRouter.java
```

Check for whitespace issues:

```bash
git diff --check
```

If the changes are already staged:

```bash
git diff --staged -- src/main/java/example/EventRouter.java
```

Compare two separately saved files, even when they do not belong to the same commit:

```bash
git diff --no-index before.java after.java
```

Note: `git diff --no-index` may return **exit code 1** when differences are detected; this does not mean the command failed. When reviewing real changes, do not only inspect a diff that hides whitespace or a single-file diff if the refactoring also affects callers or other tests.

**Do not put the example paths/filenames above into production mechanically**; place them according to the actual project structure. Reviewers need to look at the new code, all call sites, and regression tests.

## 9. Pull Request Diff Review Checklist

1. **Scope:** Does it only convert old casts to patterns, or does it also change policy, default values, APIs, exceptions, or processing order?
2. **Root type:** Is the input still identified by the same `instanceof` type? Where do `null` and wrong-type values go?
3. **Nested types:** If the new pattern deconstructs deeper, do cases where nested components are null still produce the same result?
4. **Fallback:** Does every previous `else`, `return`, `continue`, or default branch have a corresponding path after refactoring?
5. **Guard:** Check `==`/`equals`, null safety, boundary thresholds, `&&`/`||` ordering, and short-circuiting.
6. **Scope:** Are variables bound in the pattern only used in valid locations? Is there any shadowing or misleading renaming?
7. **Side effects:** Have the count or execution order of casts, accessors, method calls, logging, or exceptions changed?
8. **API:** Is the Java version appropriate? Type patterns for `instanceof` are available from Java 16, while nested record patterns require Java 21.
9. **Tests:** Are there tests for eligible inputs, ineligible inputs, both sides of the threshold, nested nulls, root null, and wrong types?
10. **Git diff:** Are there out-of-scope changes? Are there accidentally deleted lines, unnecessary new imports, or formatting noise diluting the patch?

A good review should be able to state a concise **invariant**, for example: "Every OrderEvent yields PRIORITY or STANDARD; AuditEvent yields AUDIT; other inputs yield IGNORED; a null ID is still concatenated as the string 'null'." Then verify every path against this invariant.

## 10. Comparing Behavior: Adding Tests Without Making Them a Copy of the Logic

Comparing only:

```java
assert legacy(input).equals(modern(input));
```

is useful, but not sufficient: both functions could contain the same bug. You should add an **expected output** determined from the requirements or behavior contract before refactoring, for example in the program:

```java
check("vip boundary",
        new OrderEvent(new Order(
                "O1", new Reporter("An", "VIP"), 1000)),
        "PRIORITY:O1");
```

This line requires both the old and new versions to return `PRIORITY:O1` at the threshold of 1000. In a codebase using JUnit, convert this into parameterized tests where inputs and expected outputs are decoupled from the implementations of both versions.

In addition to the cases run in Section 5, check depending on the application contract:

- Exceptions that may be thrown by customized accessors, not just the output string.
- Mutable data inside a record's reference component, especially when the input can be modified elsewhere.
- Side effects, business-meaningful logs, repository/service interactions, or event processing order.
- Integration tests at key callers, because changing from `instanceof` to record patterns can impact multiple places.
- Compilation checks against the exact Java version the project runs on, e.g. `javac --release 21` if using nested record patterns.

You can refer to branch coverage metrics, but a high coverage percentage does not by itself prove semantic equivalence. **Business-meaningful edge cases** must still be explicitly stated.

## 11. When Not to Use Nested Record Patterns to Replace Casts

Pattern matching is not an end in itself. Keep a shallow style or move logic into the domain when:

- You only need to know `input instanceof OrderEvent` and do not need all inner components.
- A nested pattern forces the caller to know too much about the data structure's depth, making maintenance harder when records change.
- The logic is governed by a named business policy that fits a domain method (e.g., `order.isPriority()`).
- Accessors have side effects, complex data flow, or branches requiring very specific error handling, making a long pattern obscure the behavior.
- The codebase still must run on Java versions below 21; nested record patterns are unavailable for the target release.

You can use a simple type pattern:

```java
if (input instanceof OrderEvent event) {
    Order order = event.order();
    // Keep Order handling here when it is easier to understand.
}
```

This snippet also eliminates the manual cast without forcing a multi-level deconstruction. Choose a refactoring level that fits the intent, not the syntax with the fewest lines.

## 12. Self-Check Questions

**Question 1.** If a refactoring replaces an `if (input instanceof OrderEvent) { ... return "STANDARD"; }` block with a single nested pattern checking for a non-null reporter, what behavior could the diff change?

**Answer:** An `OrderEvent` with `order == null` or `reporter == null` will no longer return `STANDARD` without an OrderEvent fallback branch.

**Question 2.** Why can't the `PRIORITY:null` output in the example be arbitrarily changed to an error in the same refactoring commit?

**Answer:** That is the observable behavior of the old logic when the ID is null. Tightening invariants or validating the ID is a separate business change that requires its own analysis and tests.

**Question 3.** When reviewing a diff, why are `"VIP".equals(team)` and `team.equals("VIP")` not equivalent?

**Answer:** The `team` variable can be null. The former returns false, while the latter may throw a `NullPointerException`.

**Question 4.** When an `OrderEvent` record exists but its `order` component is null, what does `input instanceof OrderEvent(Order(...))` return?

**Answer:** `false`, because the nested record pattern `Order(...)` does not match null. However, `input instanceof OrderEvent event` is still true.

**Question 5.** Why should tests check both parity and expected results?

**Answer:** Before/after comparison catches behavioral divergence; independent expected results help detect when both versions return the wrong result relative to the requirements.

**Question 6.** If `git diff --no-index before.java after.java` returns exit code 1 while printing a diff, did the refactoring fail?

**Answer:** No. Exit code 1 normally just indicates that the two files differ. You must read the differences and run tests to evaluate quality.

## Summary

Comparing the diff before and after refactoring is a process of **cross-checking syntax against behavior**. Converting `instanceof` + cast to pattern matching can reduce boilerplate, but a nested record pattern has stricter matching conditions than the outer record type. Therefore, you must preserve fallbacks, null contracts, thresholds, branch ordering, and outputs. Read diffs using a path table, run before/after tests with independent expected results, and review any out-of-scope changes. **A shorter diff is not proof of a correct refactoring; equivalent behavior is the primary criterion.**

## Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 JLS — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Git documentation — git diff](https://git-scm.com/docs/git-diff)
