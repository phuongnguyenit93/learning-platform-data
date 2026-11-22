# Using -Xlint to Detect Meaningful Warning Categories

**`javac -Xlint` is a static diagnostic tool of the Java compiler.** It detects suspicious symptoms or potentially unintended behavior **right at compile time**, before the program is executed. Particularly useful are warning groups related to unsafe generics (`rawtypes`, `unchecked`), legacy API usage (`deprecation`, `removal`), hard-to-spot control flow (`fallthrough`), serialization contracts (`serial`), resources (`try`), overrides, and several module-related behaviors.

This lesson focuses on how to **select and read meaningful warning groups**, create reproducible examples, fix causes, distinguish warnings from errors, configure strictness levels, and apply them in CI. The examples run on Java 17+, using JDK 21's `javac` to verify results during authoring.

## 1. How Do javac Warnings Differ from Errors?

- **Error:** an error in syntax, types, accessibility, or language rules making the compilation unit invalid. A build with errors does not succeed.
- **Warning:** a case the compiler *can still accept*, yet worth reviewing by the developer. For example, code using a raw `List` is still valid for compatibility with older Java, yet can bypass generics checking and cause `ClassCastException` at runtime.
- **Note:** summary information or a pointer different from a detailed warning, such as "Recompile with -Xlint:unchecked for details". A note is not necessarily a full warning and does not clearly state the location of the cause until the appropriate lint category is enabled.

Do not interpret **"compilation succeeded" as "zero warnings"**, or **"zero warnings" as "correct program"**. `javac` does not replace unit tests, runtime instrumentation, other static analyzers, or security testing.

Example code snippet that compiles yet triggers warnings:

```java
java.util.List raw = new java.util.ArrayList<String>();
raw.add("hello");
```

With `-Xlint:rawtypes,unchecked`, `javac` warns about the raw type `List` and the `add` call not being fully checked by generics. It neither fixes the code automatically nor proves runtime failure is certain. Its benefit is warning about a risky design for us to review.

## 2. Important -Xlint Syntax Forms

```bash
javac -Xlint -d out Example.java
javac -Xlint:all -d out Example.java
javac -Xlint:rawtypes,unchecked -d out Example.java
javac -Xlint:deprecation,removal -d out Example.java
javac -Xlint:all,-serial -d out Example.java
javac -Xlint:none -d out Example.java
```

These are **command templates**; `Example.java` must be a real Java file for them to run.

| Syntax | Meaning |
| --- | --- |
| `-Xlint` | Enables the set of warning groups marked as recommended by `javac` for the current JDK version |
| `-Xlint:all` | Enables all supported lint groups |
| `-Xlint:rawtypes,unchecked` | Specifies the groups to enable in a single argument |
| `-Xlint:all,-serial` | Enables groups and then excludes the `serial` group; the minus sign inside the list excludes a key |
| `-Xlint:none` | Disables warning groups belonging to the lint system; should not be treated as a switch to turn off all diagnostics |
| `-Werror` | Requests treating the presence of warnings as compilation failure; can be combined with `-Xlint` |
| `-Xmaxwarns 10` | Limits the number of detailed warnings displayed; does not fix code and does not remove the underlying nature of warnings |

To find keys **actually supported by the current `javac` build**, use:

```bash
javac --help-lint
javac -X
javac --help
javac -version
```

`--help-lint` is especially useful because the group list can **change across JDK versions**. Do not copy a key that exists only in a newer JDK into an older compiler and assume an "invalid flag" error is a Java code error. For example, `-Xlint:all,-serial` uses a comma inside **the same single argument**; do not add a space that turns `-serial` into a separate option.

**Note:** `-Xlint` and `-Xlint:all` have recommended scopes depending on the version's documentation. Some warnings may already be enabled by default, while other groups are only displayed in detail when requested. To reproduce accurately, always record `javac -version` and the passed flags.

## 3. Choosing Lint Groups by Practical Risk

| Group | What It Detects | Why It Matters |
| --- | --- | --- |
| `rawtypes` | Using a generic class/interface while omitting type arguments, like `List` instead of `List<String>` | Loses type checking, often a sign of legacy code needing improvement |
| `unchecked` | Assignments/casts or calls with incomplete generic type checking | Can let type mismatches slip through to runtime |
| `deprecation` | Using an API marked with ordinary deprecated | Need to check replacements and migration timeline |
| `removal` | Using a deprecated API **marked for removal** | Higher JDK compatibility risk, should be prioritized |
| `fallthrough` | A colon-style `switch` branch falling through to the next branch without `break` | Can cause unintended extra logic to run |
| `serial` | For example: a `Serializable` class or exception missing `serialVersionUID` | Can cause surprises regarding the serialization contract |
| `try` | Issues related to `try`/try-with-resources | Helps manage resources and avoid easily overlooked code bugs |
| `cast` | Some unnecessary casts | Reduces noise, avoids hard-to-read code |
| `overrides`, `overloads` | Some suspicious situations with overriding/overloading | Helps find confusing or unintended APIs |
| `static` | Accessing a static member through an instance | Clarifies class-based access semantics |
| `path`, `options` | Issues with paths and compilation options | Can catch misconfigured builds |
| `module`, `exports` | Issues related to the module system | Valuable for JPMS projects |
| `processing` | Issues during annotation processing | Useful with annotation processors |
| `varargs` | Some unsafe varargs declarations/calls | Useful when mixing generics with arrays |
| `this-escape` | Leaking `this` before subclass initialization completes in supporting JDKs | Detects some situations where an object is not yet fully constructed |

**This list is intentionally illustrative, not a complete table of all JDKs.** Newer keys like `this-escape` may not exist on JDK 17; check `javac --help-lint`. Groups like `removal` may be enabled by default. A warning in the groups above does not always mean a runtime error will occur; you must read the code context and API contract.

### Suggested Triage Order

1. **Runtime/behavioral error risks:** `unchecked`, `fallthrough`, `varargs`, and genuine type-safety issues.
2. **Compatibility/upgrade risks:** `removal`, `deprecation`, `serial`, `module`.
3. **Easily checkable code quality:** `rawtypes`, `cast`, `static`, `overrides`.
4. **Build configuration:** `path`, `options`, and `processing` when the environment applies.

The order above is an **impact-based assessment**, not a severity hierarchy mandated by the JLS. For example, an intentional `fallthrough` can be valid; a `path` warning detecting a missing dependency can be far more critical.

## 4. Hands-on Practice: Detecting Five Warning Groups in One Program

Create a single file `LintLab.java`:

```java
import java.util.ArrayList;
import java.util.List;

class LegacyApi {
    @Deprecated(since = "17")
    static String oldName() { return "old"; }
}

class DataProblem extends Exception { }

public class LintLab {
    public static void main(String[] args) {
        List raw = new ArrayList<String>();
        raw.add("one");
        List<String> names = raw;
        System.out.println(names.get(0));
        System.out.println(LegacyApi.oldName());

        int mode = 1;
        switch (mode) {
            case 1:
                System.out.println("one");
            case 2:
                System.out.println("two");
                break;
            default:
                System.out.println("other");
        }
    }
}
```

All non-`public` classes reside in the same file as `public class LintLab`, so this file is valid on Java 17+. `DataProblem extends Exception` is a serializable class via the `Throwable` mechanism that does not declare `serialVersionUID`; this serves the `serial` warning example.

Run in the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -d out LintLab.java
java -cp out LintLab
```

Verified with JDK 21, the compilation command reports **6 warnings**: one `serial`, one `rawtypes`, two `unchecked`, one `deprecation`, one `fallthrough`. The start and end of the warnings, rewritten as a **summary excerpt**, are:

```text
warning: [serial] serializable class DataProblem has no definition of serialVersionUID
warning: [rawtypes] found raw type: List
warning: [unchecked] unchecked call to add(E) as a member of the raw type List
warning: [unchecked] unchecked conversion
warning: [deprecation] oldName() in LegacyApi has been deprecated
warning: [fallthrough] possible fall-through into case
6 warnings
```

These are **condensed lines** from the diagnostic; actual `javac` also prints paths, line numbers, `^` positions, and type variable details. Content and line numbers may differ across JDK builds.

Important: **compilation still succeeds** because the issues in the example are classified as warnings, unless using a mode that treats warnings as errors. Running the program gives **exact** stdout:

```text
one
old
one
two
```

The last two lines `one`/`two` show the suspicious part of `fallthrough`: `case 1` runs and then continues into `case 2`. If that is intentional, state it clearly so readers know; if not, fix the `switch` structure to avoid side effects.

### Reading Each Warning at Its Proper Location

| Location in Program | Warning | Cause | Fix Direction |
| --- | --- | --- | --- |
| `class DataProblem extends Exception` | `[serial]` | Serializable without `serialVersionUID` | Declare UID according to serialization contract |
| `List raw = ...` | `[rawtypes]` | Using a raw generic type, omitting type arguments | `List<String>` |
| `raw.add("one")` | `[unchecked]` | Calling `add` via a raw type, bypassing generic type checking | Parameterize the collection at declaration |
| `List<String> names = raw` | `[unchecked]` | Assigning a raw List to a generic List in an unchecked way | Avoid raw types, or validate elements at legacy data boundaries |
| `LegacyApi.oldName()` | `[deprecation]` | Calling an API marked deprecated | Find replacement API based on documentation |
| `case 2:` after `case 1` | `[fallthrough]` | No `break` between two branches | Fix control flow if unintentional |

This is a **map from warnings to code-fixing decisions**, not advice to delete every warning with suppression. For instance, raw collection usage may reside inside an uncontrolled legacy library; in that case, an adapter/checked-cast boundary with data validation is needed rather than uncontrolled changes across the entire API.

## 5. Fixed Version: Clean Compilation with -Werror

Create a separate file `LintClean.java`:

```java
import java.util.ArrayList;
import java.util.List;

class CurrentApi {
    static String name() { return "new"; }
}

class DataIssue extends Exception {
    private static final long serialVersionUID = 1L;
}

public class LintClean {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("one");
        System.out.println(names.get(0));
        System.out.println(CurrentApi.name());

        int mode = 1;
        switch (mode) {
            case 1 -> {
                System.out.println("one");
                System.out.println("two");
            }
            case 2 -> System.out.println("two");
            default -> System.out.println("other");
        }
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintClean.java
java -cp out LintClean
```

Verified on JDK 21 with `--release 17`: the `javac` command finishes successfully without emitting the warnings above. Stdout of the `java` command:

```text
one
new
one
two
```

What changed?

1. `List<String>` replaces raw `List`, so `add` and the generic assignment are checked by the compiler.
2. Replacing the deprecated API with `CurrentApi.name()` is only to illustrate the direction. In real code, you must identify a replacement API **semantically equivalent**, rather than guessing a new name.
3. `DataIssue` declares `serialVersionUID` to make serialization versioning explicit. The UID value must match the compatibility contract of the actual class.
4. Uses **Java 17 switch rule `->`**, where case 1 prints both `one` and `two` to preserve the fall-through behavior of the old example **explicitly**. The runtime output intentionally changes `old` to `new` due to changing the illustrative API.
5. `-Werror` instructs the build to reject warnings, useful once the lint groups have been agreed upon by the development team and the baseline is sufficiently clean.

**Do not take "zero warnings" as proof that the functionality was fixed properly.** After editing, run tests to verify business behavior: for example, here both output lines of `case 1` were intentionally kept, whereas in another application only `one` might be expected.

## 6. Generics: How Do rawtypes and unchecked Differ?

These are two closely related warnings, yet from different perspectives:

- **`rawtypes`** warns about **how a generic type is declared/used without type arguments**: `List`, `Map`, `Class` instead of `List<String>`, `Map<K,V>`, `Class<?>`.
- **`unchecked`** warns about **an operation whose generic type safety the compiler cannot fully verify**, such as an unchecked assignment, cast, or call through a raw generic.

Example:

```java
List raw = new ArrayList<String>();   // rawtypes
raw.add(123);                         // unchecked call
List<String> strings = raw;           // unchecked conversion
// String first = strings.get(0);     // Potential runtime ClassCastException
```

The code above is an **illustrative snippet** placed inside a method with imports `java.util.List`, `java.util.ArrayList`; it is not a standalone Java file. Even though `ArrayList<String>` has a type argument in the initializer, the `raw` variable is still declared raw and loses type guarantees at calls using that variable.

How to fix when **the element type is clearly known**:

```java
List<String> strings = new ArrayList<>();
strings.add("ok");
// strings.add(123); // Compile-time ERROR: Integer is incompatible with String.
```

If data comes from a legacy API returning `List`, do not cast blindly to hide warnings. It can be handled at the **boundary**:

```java
static List<String> validatedStrings(List<?> values) {
    List<String> result = new ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String s)) {
            throw new IllegalArgumentException("Not a String: " + value);
        }
        result.add(s);
    }
    return result;
}
```

This is an **illustrative method**, needing to be placed in a class with imports `java.util.List`, `java.util.ArrayList`. It proactively checks each element and then creates a `String`-typed List, instead of just doing an unchecked cast and assuming the entire collection is valid. With large data, copying and checking has a cost; weigh the API contract and actual data path.

### Why Is the unchecked Warning Important?

Due to type erasure, not every generic parameter of an object can be checked at runtime like primitive types. A cast `(List<String>) someObject` may only check that the object is a raw `List`; whether each element is genuinely `String` remains unverified. Therefore, the warning needs investigation, especially in public APIs or untrusted data entry points.

## 7. Deprecated and forRemoval: Different Priorities

Two common groups:

```java
@Deprecated(since = "17")
public static void oldMethod() {}

@Deprecated(since = "17", forRemoval = true)
public static void obsoleteMethod() {}
```

This is an example of declarations inside a class; not a standalone program. Ordinary `@Deprecated` means new usage should be avoided or a replacement planned. With `forRemoval = true`, the API is announced as **intended for future removal** per the library's roadmap; the compiler distinguishes the `removal` warning from ordinary `deprecation`.

Select the flags:

```bash
javac -Xlint:deprecation,removal -d out App.java
```

`App.java` needs to be a real source file using the corresponding API. `-deprecation` is also a way to ask the compiler for deprecated usage details and is described in `javac` documentation as equivalent to `-Xlint:deprecation`.

Some JDKs display `removal` warnings even when you do not write `-Xlint:removal` because this group may be enabled by default. Therefore, using `-Xlint:all` or enabling important groups **does not always increase the total warning count compared to the default**.

When handling:

- Check the library/JDK and version in use, Javadoc, or migration guide.
- Verify whether the replacement API has an equivalent contract regarding data, exceptions, thread-safety, and performance.
- Prioritize `removal` when upgrading JDKs to avoid the application failing to compile/run after an upgrade.
- Document the reason clearly if forced to keep a legacy call in a small region and have a plan to remove it.

Do not treat `@Deprecated` as an automatic error. It is a maintenance signal, whose priority depends on usage scope and when the module changes versions.

## 8. Fallthrough: Distinguishing Logic Bugs from Intent

Traditional colon-style switch **can fall through to the next case** if there is no `break`, `return`, or appropriate exit path:

```java
switch (status) {
    case 1:
        log("started");
    case 2:
        log("stopped");
        break;
    default:
        log("unknown");
}
```

This is an **illustrative snippet**, in which `status` and `log` must be defined by context. If `status == 1`, both `started` and `stopped` are logged: that might be a bug.

`-Xlint:fallthrough` helps detect suspicious structures. Depending on requirements, do one of:

- **Add `break`** if each branch must run independently.
- **Use switch rule `->`** (Java 17+) to avoid implicit fallthrough, making clear which branch executes which logic.
- **Keep intentional fallthrough** when carefully designed and verified. Adding a comment documents intent, yet one should not assume every compiler automatically recognizes comments as an official suppression mechanism.

Example of fixing the logic so each case handles independently:

```java
switch (status) {
    case 1 -> log("started");
    case 2 -> log("stopped");
    default -> log("unknown");
}
```

Do not mechanically add `break` if the application depends on running both tasks. Behavior before and after must be verified against business requirements.

## 9. Serial: Understanding serialVersionUID

A `Serializable` class or a class inheriting from a serializable type like `Exception` may receive a `serial` warning when it does not declare `serialVersionUID`. Java's serialization framework uses this number to identify compatibility between serialized data and the class definition loaded during deserialization. An incorrect or incompatible UID can cause `InvalidClassException`.

Example:

```java
class DomainException extends Exception {
    private static final long serialVersionUID = 1L;

    DomainException(String message) {
        super(message);
    }
}
```

This is a complete Java class without `main`; it can be placed in `DomainException.java` or used inside a project.

**Not every class needs serialVersionUID.** Only classes participating in the Java serialization mechanism relate to this warning category. For DTOs in JSON, protocol buffers, or DB data, examine the actual serialization protocol used; do not add `implements Serializable` just to look "standard".

Nor should you choose an arbitrary UID for a class that already has stored serialized data needing compatibility with old binaries. Review the versioning/compatibility contract.

## 10. Varargs and Generic Arrays: Warnings Come with Conditions

A generic varargs method can cause **heap pollution** when the element type is non-reifiable. `-Xlint:varargs` and `-Xlint:unchecked` help identify situations that need inspection:

```java
static <T> void showAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

This is an illustrative method inside a class. Depending on the declaration context and call site, the compiler may emit warnings because generic varargs use an array at runtime. Do not conclude that any `T...` declaration guarantees an error; a failure occurs only if the code actually does something dangerous with the array type or call.

For some qualifying helpers, `@SafeVarargs` allows the author to **pledge** that the method performs no unsafe operations on the varargs array; this is **not** a way to silence warnings to skip checking. Before using it, verify that no wrong-typed elements are written, the varargs array is not exposed where it causes heap pollution, and the rules allowing the annotation in the Java version used are met.

Design-wise, you can accept `List<T>` or `Collection<T>` instead of generic varargs if the API does not need flexible vararg argument syntax.

## 11. Other Useful Warnings Depending on Architecture

`-Xlint:all` typically expands scope beyond the initial groups. When reading additional warnings that arise, classify them:

- **`try`:** issues around try-with-resources, such as ignored resources or suspicious constructs detectable by javac. It does not prove every resource is properly closed along all runtime paths.
- **`cast`:** unnecessary casts, which can lengthen code and obscure intent.
- **`static`:** accessing static fields/methods through an instance; use the class name to express static members and avoid confusion with virtual dispatch.
- **`overrides`, `overloads`:** some method declaration situations that can cause confusion; these warnings do not replace JLS overload resolution checks.
- **`processing`:** unexpected annotation processing situations, for example a processor not handling annotations the compiler is inspecting.
- **`path`, `options`:** discrepancies in compiler arguments or paths, especially when building on CI, another JDK, or another OS.
- **`module` and related groups:** useful for JPMS applications such as named modules, exports, and automatic module requirements.

Some keys exist only in certain compiler versions. The final list must be confirmed with `javac --help-lint` on the running toolchain. Do not modify the entire project just because one machine with a newer JDK automatically turns on extra warnings.

### Warnings That May Not Directly Relate to Safety

For example, redundant `cast` or `static` access via an instance does not necessarily cause immediate errors. They are still meaningful because they clean up code, reduce API misunderstandings, and facilitate automated checks. Conversely, an `unchecked` warning in an external data deserialization layer can be a much higher real-world risk.

**Choose groups based on codebase and maintenance expectations**, not based on the highest warning count.

## 12. -Werror, -Xmaxwarns, and Strictness Levels in CI

After selecting useful lint groups, you can require warnings to fail the build:

```bash
javac --release 17 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintClean.java
```

Command verified with `LintClean.java` in section 5: compilation succeeds.

Whereas with `LintLab.java` in section 4, with the same warning groups and `-Werror`, the compiler emits warnings and then reports failure because of warnings:

```bash
javac --release 17 -Xlint:rawtypes,unchecked,deprecation,fallthrough,serial -Werror -d out LintLab.java
```

Do not use an output file from an old compilation as proof that the new compile succeeded. When using `-Werror`, check `javac`'s **exit code** and build logs; having `.class` files already in the directory is insufficient proof that the current run passed.

`-Xmaxwarns 10` only limits the number of detailed warnings printed; it does not mean "allow up to 10 warnings and still pass" and does not change the semantics of `-Werror`. The compiler may report the count of additional hidden warnings when capped.

### Incremental Adoption in Large Codebases

1. **Run a baseline:** compile with desired groups, save logs, count/classify warnings and their origins.
2. **Fix new code first:** set rules for modules or scopes owned by the team to avoid introducing new issues.
3. **Prioritize high-value warnings:** such as `unchecked` at API boundaries, `removal` before JDK upgrades, `fallthrough` in business control-flow code.
4. **Resolve old warnings with a plan:** fix sources or upgrade dependencies, distinguishing generated/vendor code outside your control.
5. **Enable `-Werror`** for modules with a clean baseline, testing thoroughly to avoid mass build failures from uncontrolled environment changes.
6. **Record toolchain/version:** warning differences between JDK 17 and newer JDKs need verification.
7. **Review exceptions:** suppressions or disabled categories must have specific reasons and scopes.

Do not aim for "0 warnings" at all costs by silencing real errors in the build. An intentional baseline with clear feedback loops is more valuable than disabling diagnostics wholesale.

## 13. SuppressWarnings and Choosing Exclusion Scope

Java allows `@SuppressWarnings` to turn off certain compiler warnings within an appropriate declaration scope:

```java
@SuppressWarnings("deprecation")
static void callLegacy() {
    // Intentional deprecated API call in a compatibility adapter.
}
```

The snippet above is an annotation scope example, not a standalone program. In real Java, corresponding code and a reason for using the legacy API are needed.

Multiple-key example:

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static void legacyBridge() {
    // Use only when data from the legacy API has been clearly verified.
}
```

**Do not use the illustrative snippet above as a way to ignore type errors.** If you need to convert a raw `List` to a typed `List<String>`, you still must know whether the list contains elements of the right type. `@SuppressWarnings` does not add runtime validation or fix logic errors.

Points to remember:

- Keys in `@SuppressWarnings` typically use forms like `"unchecked"`, `"deprecation"`, `"rawtypes"`, **without adding the `-Xlint:` prefix**.
- Not every lint type can be suppressed at source locations. For example, some warnings about command-line options, paths, or annotation processing are outside class/method suppression scope.
- Suppress **as narrowly as possible**: an audited bridge method is usually better than silencing an entire package or module.
- If using suppression, document the cause, assumptions, and controls. When the environment upgrades, revisit and re-evaluate.
- Normally you should **fix the cause first**, using suppression as an approved last-resort exception.

### Disabling Lint Groups on the Command Line When Truly Necessary

```bash
javac -Xlint:all,-serial -d out LintClean.java
```

This example specifically disables `serial` within the `all` set. If a codebase has many legacy serializable types with a separate policy, this approach may be considered per module; yet applying it everywhere ignores warnings in new code. Do not judge design quality as better merely because the warning count dropped.

`-Xlint:none` should only be used in specific cases needing reduced output or reproducing toolchain conditions, and it must be understood that it is **not equivalent to "no issues remaining"**.

## 14. Reading Diagnostics Properly

With `javac -Xlint:unchecked ...`, a warning typically contains:

```text
Example.java:12: warning: [unchecked] unchecked conversion
    List<String> values = rawValues;
                          ^
  required: List<String>
  found:    List
```

This is a **formal example**, and must not be treated as the output of a real `Example.java` file in the lesson. Common parts:

1. `Example.java:12`: file and code line pointed out.
2. `warning`: diagnostic level; if it is `error`, its nature is different.
3. `[unchecked]`: key helping filter and route handling.
4. `unchecked conversion`: description of the suspicious operation.
5. `^`: position of the relevant expression.
6. `required`/`found`: expected type and type found by the compiler.

Reasonable reading workflow: identify **the code line and type**, then find where the **data source** or **control flow structure** creates the warning. Do not only edit at the `^` position while ignoring the cause in an earlier method or type declaration.

### Diagnostics Are Not Necessarily on stdout

`javac` normally writes diagnostics to **stderr**, while sample Java programs may print to **stdout**. Therefore, CI logs may interleave lines; when reporting, distinguish compiler output from application output.

In scripting environments, check the **exit code** instead of grepping messages. Each JDK/vendor may vary wording, ordering, columns, and extra information sections.

## 15. Quick Diagnostic Practice

**Exercise 1 — Reading rawtypes warning:**

```java
java.util.List items = new java.util.ArrayList<Integer>();
```

What is the design flaw? **Answer:** the `items` variable uses raw `List`, losing generic checking. If the collection holds Integer, declaring `List<Integer> items = new ArrayList<>();` is more appropriate.

**Exercise 2 — Choosing groups to prepare for a JDK upgrade:**

A project has many old libraries, risking removed APIs. Which keys should be used first? **Answer:** `-Xlint:removal,deprecation` helps find calls to APIs deprecated or marked for removal; then consult migration guides.

**Exercise 3 — Switch with fallthrough:**

```java
switch (level) {
    case 1:
        notifyUser();
    case 2:
        notifyAdmin();
        break;
    default:
        break;
}
```

This snippet only illustrates inside a method having `level` and corresponding methods. If `level == 1`, which two calls occur? **Answer:** both `notifyUser()` and `notifyAdmin()`. If that is not intentional, add `break` or change to an appropriate switch rule.

**Exercise 4 — Warning became a build failure:**

A file has an `unchecked` warning, and adding `-Werror` makes compilation return a failure exit code. Does that mean the code suddenly became a type error under the JLS? **Answer:** No. The code still has a warning, yet build policy requires rejecting warnings. Inspect the operation's risk before suppressing.

**Exercise 5 — Warnings in generated code:**

A code-generation tool has many `rawtypes`, yet the files are automatically regenerated. Should each generated file be edited directly? **Answer:** Usually no. Fix the template/codegen or generator configuration to avoid new warnings. If not yet fixable, apply a narrowly scoped local exception, not a project-wide disable.

**Exercise 6 — -Xmaxwarns:**

Running `javac -Xlint:all -Xmaxwarns 5 ...` shows only five detailed warnings. Can you conclude there are only five issues? **Answer:** No. Display limits are not limits on actual issues; the compiler may report additional hidden warnings.

**Exercise 7 — Suppression:**

Does `@SuppressWarnings("unchecked")` make the cast `(List<String>) rawObject` safer at runtime? **Answer:** No; the annotation only affects diagnostics, without checking or converting elements.

## 16. Practical Workflow When Adding -Xlint to a Project

For each specific module or set of classes, follow these steps:

1. Confirm `javac -version`, the actual compiler running in terminal/build/CI, and supported keys with `javac --help-lint`.
2. Compile with `-Xlint:rawtypes,unchecked,deprecation,removal,fallthrough,serial` first. Adjust according to source code and runtime; do not force every project to use one identical set.
3. Read warnings by **file, line, category, and operation**. Tag warnings coming from code you own, dependencies, generated sources, and build configuration.
4. Pick an important warning, write a test or minimal example demonstrating before/after behavior. For generics, consider wrong-type data; for fallthrough, check execution branches; for deprecation, check API compatibility.
5. Fix the cause and recompile; confirm that the warning disappears along with expected program behavior.
6. Once the baseline is clean and the team agrees, introduce `-Werror` into the appropriate task/module; do not enable it across the board while neglecting blocked-build consequences.
7. Monitor new warnings when upgrading toolchains: a new category or new diagnostic may require updating rules.
8. Use suppression or disable a key intentionally, narrowly, and under review, instead of using `-Xlint:none` by default.

### When Using Maven or Gradle

In Maven, Gradle, or IDEs, the compiler may be invoked via tasks/plugins/toolchains. Pass **compiler arguments** through the tool's official mechanism so `-Xlint` actually reaches `javac`. Do not assume passing flags to the JVM running the build tool equals passing flags to the compiler.

- **Compiler options:** `-Xlint:...`, `-Werror`, `--release 17`, `-encoding UTF-8`.
- **JVM options:** such as `-Xmx` for a separate daemon/worker/compiler JVM, depending on the process model.

Build systems may set a different Java toolchain from `javac` in the terminal. When warnings appear solely in CI, compare JDKs, source/target releases, dependencies, option lists, and generated code in that exact job.

## 17. Summary and References

`-Xlint` is valuable when **a meaningful warning leads to a verifiable action**: fixing generic types, validating data conversions, replacing legacy APIs, clarifying control flow, maintaining serialization contracts, or adjusting build flags. One `javac` run can output many diagnostics, yet decision quality lies in **analyzing risk, fixing the cause, and preserving application behavior**.

Authoritative sources:

- [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): syntax for `-Xlint`, `-Xlint:key`, `-Werror`, `-Xmaxwarns`, and examples of lint groups.
- [OpenJDK — javac manual](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md): key catalog from current sources, helping spot categories that change across JDKs.
- [Oracle JDK 21 — @SuppressWarnings](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SuppressWarnings.html): suppression scope and effect.
- [Oracle JDK 21 — @Deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html): `since` and `forRemoval`.
- [JLS Java SE 21 — `4.8 Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8) and [`5.1.9 Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9): foundations of generics warnings.

**Key takeaway:** `-Xlint` helps spot issues; `-Werror` enforces a policy; whereas fixing the code properly and verifying functionality decide whether the warning is truly resolved.