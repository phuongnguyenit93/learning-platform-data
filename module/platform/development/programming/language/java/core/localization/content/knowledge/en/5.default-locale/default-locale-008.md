# Restoring the Default Locale When Tests Modify Global Configuration in Java

## 1. Context: Why Can One Test Break Another?

`Locale.getDefault()` returns the JVM's default locale when code is not passed a specific `Locale`. Some APIs and libraries rely on that default to choose language, display rules, or formatting. In tests, developers sometimes call `Locale.setDefault(...)` to simulate a user's environment:

```java
Locale.setDefault(Locale.FRANCE);
// Call code that uses Locale.getDefault()...
```

The snippet above changes **shared state for the entire JVM**, not just for the current test method. If a test finishes without resetting the original value, subsequent tests may read a different locale than what was present at startup, creating order-dependent failures, differing formatting outputs, or behavior that is hard to reproduce on CI.

Another mistake: a test author remembers to restore `Locale.getDefault()` but forgets the specialized defaults `Locale.Category.DISPLAY` and `Locale.Category.FORMAT`. Proper restoration must be based on **the actual values that existed before the test**.

**Lesson objectives:** snapshot the relevant locale defaults, test changing them, use `try/finally` to restore them even when a test fails, verify the state after restoration, and understand why parallel tests still require separate management.

## 2. Understanding the Three Default Locale States

Java supports a general default locale and two category defaults:

| Value to read | API | Role |
| --- | --- | --- |
| General default | `Locale.getDefault()` | The JVM's default locale, commonly used when an API does not specify a category. |
| Display default | `Locale.getDefault(Locale.Category.DISPLAY)` | Preferred for names or text meant for display, such as language/place names via category-aware APIs. |
| Format default | `Locale.getDefault(Locale.Category.FORMAT)` | Preferred for formatting numbers, currencies, and dates/times in APIs using the `FORMAT` category. |

Corresponding setters:

```java
Locale.setDefault(Locale.US);
Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
```

These are illustrative statements, not a standalone program.

Two rules to grasp:

1. `Locale.setDefault(Locale)` changes the general default locale **and resets both `DISPLAY` and `FORMAT` category defaults** to the new locale.
2. `Locale.setDefault(Locale.Category, Locale)` changes only the specified category's default; it does not automatically synchronize all categories and the base locale.

As a result, the three values can be completely different. For instance, after the three statements above, base is `en-US`, DISPLAY is `fr-FR`, and FORMAT is `de-DE`.

Even though each category can be configured separately, these values remain **shared state within the JVM**, not per-thread or per-test-case configurations.

## 3. Safe Restoration Rule: Snapshot → try/finally → Restore

Minimal pattern:

```java
Locale originalBase = Locale.getDefault();
Locale originalDisplay = Locale.getDefault(Locale.Category.DISPLAY);
Locale originalFormat = Locale.getDefault(Locale.Category.FORMAT);

try {
    Locale.setDefault(Locale.US);
    Locale.setDefault(Locale.Category.DISPLAY, Locale.FRANCE);
    Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

    // Perform the test assertions.
} finally {
    Locale.setDefault(originalBase);
    Locale.setDefault(Locale.Category.DISPLAY, originalDisplay);
    Locale.setDefault(Locale.Category.FORMAT, originalFormat);
}
```

This snippet belongs inside a Java method. The restoration order **is critical**: restore base first, because `setDefault(Locale)` resets both categories; then restore `DISPLAY` and `FORMAT` from the snapshot to preserve any initially distinct values.

`finally` runs when the `try` block completes normally or when an exception/assertion failure occurs (except when the JVM process terminates abruptly, such as `System.exit`, a crash, or power loss). If an assertion fails, the exception is still propagated after `finally` runs; do not swallow test failures merely to log them.

**Do not hard-code restoring to `Locale.US`, `Locale.ENGLISH`, or calling `Locale.getDefault()` at the end.** The “initial default” differs across personal machines, CI, containers, and test configurations. Default values must be captured **before any locale-changing call**.

### Why not save only the base default?

Suppose before the test we have:

```text
base    = en-US
DISPLAY = fr-FR
FORMAT  = de-DE
```

If the test calls `Locale.setDefault(Locale.JAPAN)`, all three values can become `ja-JP`. Calling only `Locale.setDefault(originalBase)` afterward produces:

```text
base    = en-US
DISPLAY = en-US
FORMAT  = en-US
```

This is **not the original state**, because both categories lost their `fr-FR` and `de-DE` overrides. Only snapshotting all three values restores the state accurately.

## 4. Standalone Java 17+ Program

Create the file **`LocaleDefaultRestoreDemo.java`**. The example uses a `record` to group the three snapshot values. The program prints the altered values during the test, restores them in `finally`, and verifies that all three states match the snapshot. The output does not depend on the machine's initial locale.

```java
import java.util.Locale;

public class LocaleDefaultRestoreDemo {

    private record SavedDefaults(
            Locale base,
            Locale display,
            Locale format) {

        static SavedDefaults capture() {
            return new SavedDefaults(
                    Locale.getDefault(),
                    Locale.getDefault(Locale.Category.DISPLAY),
                    Locale.getDefault(Locale.Category.FORMAT)
            );
        }

        void restore() {
            // Set base first because this operation also resets both categories.
            Locale.setDefault(base);
            Locale.setDefault(Locale.Category.DISPLAY, display);
            Locale.setDefault(Locale.Category.FORMAT, format);
        }

        boolean matchesCurrent() {
            return base.equals(Locale.getDefault())
                    && display.equals(
                            Locale.getDefault(Locale.Category.DISPLAY))
                    && format.equals(
                            Locale.getDefault(Locale.Category.FORMAT));
        }
    }

    public static void main(String[] args) {
        SavedDefaults saved = SavedDefaults.capture();

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.DISPLAY, Locale.FRANCE);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.GERMANY);

            System.out.println("base="
                    + Locale.getDefault().toLanguageTag());
            System.out.println("display="
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("format="
                    + Locale.getDefault(
                            Locale.Category.FORMAT).toLanguageTag());

            if (!Locale.GERMANY.equals(
                    Locale.getDefault(Locale.Category.FORMAT))) {
                throw new AssertionError("FORMAT was not set");
            }
        } finally {
            saved.restore();
        }

        System.out.println("restored=" + saved.matchesCurrent());
    }
}
```

Compile and run in the file's directory using JDK 17 or higher:

```bash
javac -encoding UTF-8 LocaleDefaultRestoreDemo.java
java LocaleDefaultRestoreDemo
```

**Exact stdout:**

```text
base=en-US
display=fr-FR
format=de-DE
restored=true
```

*Why `restored=true`?* `SavedDefaults.capture()` records the three `Locale` values before the code changes state. `try` sets up the simulated environment; `finally` restores base, DISPLAY, and FORMAT in the safe order. `matchesCurrent()` compares the `Locale` objects against the pre-test snapshot, without guessing the machine's locale.

If an assertion in `try` throws `AssertionError`, the `finally` block still runs, and then the error propagates as expected. The `restored=true` line comes after `finally`, so when an assertion fails it will not be printed; that does not mean restoration failed to run.

### Why is a record a good fit here?

A `record` (Java 17) holds the three `Locale` fields as clearly named snapshot data. You can also use a regular class, as long as all three components are saved. The `getDefault(...)` getters return `Locale` objects; capturing these references is sufficient because `Locale` itself is immutable per the API, while the mutable state resides in the JVM's static default variables.

## 5. Applying This with JUnit 5

If a test must alter global defaults, wrap the entire operation in `try/finally` right inside the test. The illustrative snippet below uses JUnit Jupiter 5; running it requires a project with JUnit 5 dependencies and a corresponding test runner. It is **not a standalone Java program compiled solely with `javac`**.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock("jvm-default-locale")
class LocaleSensitiveTest {

    @Test
    void restoresDefaultsAfterAssertions() {
        Locale base = Locale.getDefault();
        Locale display =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale format =
                Locale.getDefault(Locale.Category.FORMAT);

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.GERMANY);

            assertEquals(Locale.US, Locale.getDefault());
            assertEquals(
                    Locale.GERMANY,
                    Locale.getDefault(Locale.Category.FORMAT));
        } finally {
            Locale.setDefault(base);
            Locale.setDefault(Locale.Category.DISPLAY, display);
            Locale.setDefault(Locale.Category.FORMAT, format);
        }
    }
}
```

`@ResourceLock("jvm-default-locale")` helps JUnit Jupiter coordinate tests using **the same lock resource name** when executing in parallel within the same test plan. Every test that mutates/reads the default locale in a state-dependent way must cooperate using the same appropriate lock; the annotation cannot lock application threads or libraries outside the test framework's mechanism. If the overall test suite has uncooperative components or background threads reading the locale, a more reliable approach is **not mutating global state** or isolating the test in a separate JVM.

### `@BeforeEach` / `@AfterEach` or `try/finally`?

`@BeforeEach` can save the snapshot into fields and `@AfterEach` can restore it, which is convenient if multiple tests follow the same pattern. However, it requires lifecycle management and avoiding nulls if setup fails. For a single test, `try/finally` is easier to verify because snapshot and restore sit side by side. If using lifecycle hooks, still snapshot before any setup alters defaults, and restore all three values.

When a framework provides a helper or extension for temporary locale management, you can use it to avoid boilerplate, provided you verify that it supports and restores **both DISPLAY and FORMAT** as required by the test.

## 6. Scenarios to Test

| Scenario | What to verify |
| --- | --- |
| Test runs normally | After the test, all three defaults match the snapshot; no order-dependent side effects remain. |
| Assertion throws `AssertionError` | `finally` still restores; the framework still reports the test failure. |
| Code under test throws `RuntimeException` | Restoration happens and then the exception propagates; no error swallowing. |
| Base, DISPLAY, and FORMAT differ initially | All three are restored, not just base. |
| Test modifies only one category | The other category and base are not corrupted during restoration. |
| Nested tests on the same thread | Each level snapshots at entry and restores in LIFO order. |
| Tests running in parallel on the same JVM | Requires lock coordination or JVM isolation; `try/finally` alone does not guard against race conditions. |
| Tests on CI with a different locale from personal machine | Do not assume fixed input locales; assert relative to the snapshot. |

### Example of a test-order bug

```text
Test A:
  Locale.setDefault(Locale.FRANCE)
  assertion succeeds
  forgets to restore
         ↓
Test B:
  creates formatter without passing Locale
  receives fr-FR instead of the initial environment
         ↓
B may fail even though it passes when run alone
```

Adding `try/finally` to A prevents B from receiving lingering effects from A in sequential runs. If A and B actually run **concurrently**, B can still observe A's temporary locale; therefore concurrency control must be addressed separately.

## 7. Parallel Testing and the Limits of `try/finally`

Suppose two tests run concurrently on one JVM:

```text
Time           Test A                         Test B
t0             save base=vi-VN
t1             setDefault(en-US)
t2                                            save base=en-US
t3                                            setDefault(fr-FR)
t4             restore(vi-VN)
t5                                            run assertion, sees vi-VN
t6                                            restore(en-US)
End            JVM ends with en-US, even though it started as vi-VN
```

Both tests have `try/finally`, yet because snapshots and restores interleave, the final state is still wrong. **`try/finally` guarantees a cleanup path within one flow of control; it does not make JVM state thread-local and does not ensure isolation between parallel tests.**

Appropriate options:

1. **Prefer passing `Locale` directly into the code under test.** For example, use `NumberFormat.getNumberInstance(locale)` or `DateTimeFormatter.withLocale(locale)`; then unit tests do not need to call `Locale.setDefault(...)`.
2. **If you must test legacy code that reads the default locale, run sequentially or lock on the same resource.** Synchronization is only useful when all relevant code follows the exact same locking rule. JUnit `@ResourceLock` is a JUnit test coordination mechanism, not a JVM-wide lock.
3. **When strict isolation from other tests is needed, run the test in a separate process/JVM.** Each JVM has its own default locale; no static state is shared.

A `synchronized` block on an object inside a test class only protects threads that also synchronize on that exact same object. It does not stop code outside the lock from calling `Locale.setDefault(...)`, so it cannot be treated as a universal safeguard for all tests.

## 8. How to Verify a Locale Change Takes Effect as Intended

Different APIs use defaults in different ways:

- `Locale.getDefault()` returns base; `Locale.getDefault(Locale.Category.DISPLAY)` returns the DISPLAY default; `Locale.getDefault(Locale.Category.FORMAT)` returns the FORMAT default.
- Some formatters created without a locale look up the corresponding category default **when created**. Previously initialized formatters may continue holding old configurations; do not assume changing the default automatically updates all existing objects.
- APIs taking an explicit `Locale` parameter normally use that parameter instead of defaults; testing them does not require mutating the JVM default.

When writing assertions, check state via the corresponding getters rather than assuming changing one getter immediately affects every library. When testing string formatting, JDK/CLDR locale data can change slightly across versions; distinguish application contract requirements from JDK-data-dependent representations.

In particular, `Locale.setDefault(...)` is **not** an operation to change `TimeZone.setDefault(...)`. If a test modifies both locale and time zone, snapshot/restore each kind of state independently; do not confuse `Locale.Category.FORMAT` with a time zone.

## 9. Common Mistakes When Restoring Locales

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Restoring to a hardcoded `Locale.US` | CI's initial state might differ from `US`. | Capture `Locale.getDefault()` before the test. |
| Saving base while ignoring DISPLAY/FORMAT | Loses pre-existing category overrides. | Save and restore all three. |
| Restoring categories first and calling `setDefault(base)` last | The last call resets the categories just restored. | Restore **base first, categories second**. |
| Placing restore after assertions without `finally` | An assertion failure skips restoration. | Wrap mutating operations in `try/finally`. |
| Capturing the snapshot after calling `setDefault(...)` | The snapshot captures the temporary configuration itself. | Snapshot before changing any default. |
| Swallowing test exceptions inside `catch` | Reports false passes even though assertions failed. | Let test failures propagate; use `finally` solely for cleanup. |
| Trusting `try/finally` to handle parallelism | Races between snapshot, mutation, and restore. | Lock cooperating tests, run sequentially, or isolate the JVM. |
| Calling `getDefault()` at the end to infer the old value | By then it may be the temporary locale itself. | Use the saved snapshot. |
| Thinking the format category means time zone | Dates/times also depend on `ZoneId`/`TimeZone`. | Manage time zones separately. |
| Creating formatters before changing the default | Old formatters may not reflect the new default. | Create formatters inside the test scope or pass locales directly. |

## 10. Practice Exercises

**Exercise 1 — Restoring after failure:** starting from `LocaleDefaultRestoreDemo`, intentionally throw `new AssertionError("simulated failure")` inside `try`. In an outer caller class, observe that the exception is still reported, while the snapshot of all three locales has been restored. Do not turn a failing test into a passing one.

**Exercise 2 — Initial category overrides:** before capturing the snapshot for another test scope, set base `en-US`, DISPLAY `fr-FR`, and FORMAT `de-DE`. Inside the test scope, call `setDefault(Locale.JAPAN)`. Verify that restoring only base loses the two overrides, whereas full restoration preserves all three. Afterward, still restore the JVM's original configuration for the lab exercise.

**Exercise 3 — Avoiding global state mutation:** write a `formatAmount(BigDecimal amount, Locale locale)` method using `NumberFormat.getNumberInstance(locale)`. Test two locales passed directly; prove `Locale.getDefault()` does not change before and after both calls.

**Exercise 4 — Controlling parallelism:** explain the interleaved execution schedule in section 7. Then design a rule using a shared `@ResourceLock` for JUnit tests accessing the default locale; state the limitation regarding background threads not participating in the test framework.

### Completion Checklist

- [ ] Distinguish `Locale.getDefault()` from the two category defaults `DISPLAY` and `FORMAT`.
- [ ] Understand the effect of `Locale.setDefault(Locale)` on both categories.
- [ ] Snapshot all three values **before** any default-mutating operation.
- [ ] Use `finally` and restore in the order **base → DISPLAY → FORMAT**.
- [ ] Never hide assertion failures; be able to verify post-restoration state.
- [ ] Identify race conditions when multiple tests modify JVM defaults concurrently.
- [ ] Know when to pass an explicit `Locale` or isolate tests in a separate JVM.

Rule to remember: **a test that modifies JVM-wide locale configuration must restore the exact state observed at the start, even when the test fails; and if tests run in parallel, all affected tests must have an isolation/coordination mechanism.**
