# Java Core Scope and How to Cross-Reference JDK Versions — Java Core: Numbers

## 1. What Problem Does This Lesson Solve?

When learning number handling in Java, two seemingly simple questions arise: "Is `BigDecimal` an external library?" and "Will an example using `Math.clamp` run on JDK 17?". To answer them, you must distinguish **Java Core knowledge scope**, **standard APIs**, **the JDK version used to compile**, **the Java version where the program runs**, and **the version a project commits to supporting**.

This lesson focuses on **Java Core — Numbers**. The goal is to help you:

1. Know which number-handling components belong to the Java language syntax, the `java.base` standard library, or other standard APIs; without confusing them with application libraries.
2. Determine which Java version introduced an API/method using version-specific documentation, especially `Since`, `Deprecated`, and `Preview` annotations.
3. Understand the difference between source compilability, API availability, bytecode version, and actual runtime execution.
4. Self-verify with `java`, `javac`, and `javac --release` before concluding code runs on the target JDK.
5. Establish a version cross-referencing workflow applicable to every subsequent Numbers lesson.

**Scope limitation:** this is an orientation and version cross-referencing lesson, not a reference for every numeric operation or an exhaustive changelog of each JDK release. Versions 8, 11, 17, and 21 are used as **reference milestones**; they do not imply that only four Java versions exist or that the latest Java version is always 21.

## 2. Five Concepts to Distinguish

| Term | Practical Meaning | Numbers-Related Example |
| --- | --- | --- |
| **Java (the language)** | Syntax, primitive types, operators, and conversion rules defined by the Java Language Specification | `int`, `double`, `+`, `/`, numeric promotion |
| **Java SE (standard platform)** | Standard API set, execution model, and specification for a release | `java.lang.Math`, `java.math.BigDecimal`, `java.text.NumberFormat` |
| **JDK (Java Development Kit)** | Development toolkit containing the compiler, documentation tools, and runtime environment | `javac`, `java`, `javadoc`, `jshell` (since JDK 9) |
| **JVM/runtime** | Environment that loads, verifies, and executes bytecode; an application also depends on available APIs/runtime | Running `NumbersDemo.class`; can hit `UnsupportedClassVersionError` or `NoSuchMethodError` |
| **JDK distribution** | A Java build from a specific vendor, with its own versioning, patches, and support policy | OpenJDK build, Oracle JDK, Eclipse Temurin, or other builds |

**Java Core** is an educational term for foundational Java knowledge and commonly used standard libraries, not the name of an independent Java SE module. Since Java 9, Java SE has a module system; many common number-handling classes live in module **`java.base`**, which every Java module reads implicitly.

**JRE** used to be distributed separately in many older Java lines; with modern JDKs, when saying "runtime" you should verify the actual execution environment rather than assuming a machine necessarily has a standalone JRE installed.

To compare API availability, always note the **feature release number**, such as 17 or 21, before looking at patch updates like 17.0.x or 21.0.x. A patch update and a new feature release do not carry the same compatibility meaning.

## 3. Numbers Map Within Java Core Scope

### 3.1. What Belongs to the Java Language

Primitive types `byte`, `short`, `int`, `long`, `float`, and `double`; literals such as `42`, `42L`, `1.5F`; operators `+`, `-`, `*`, `/`, `%`; casts and numeric promotion rules live in the **Java language**. No external math library needs to be installed to use them.

Core rules must be checked against the **Java Language Specification (JLS)** for the target version, such as how `7 / 2` evaluates, `int` overflow, and the difference between approximate floating-point numbers and exact decimals. Most of this foundation is stable across many releases, yet you should not ignore specification changes to floating-point handling or other language features.

### 3.2. Commonly Used Standard Classes/Libraries

| Need | Representative APIs | Where It Lives |
| --- | --- | --- |
| Constants and basic math operations | `Math`, `StrictMath` | `java.lang` / `java.base` |
| Wrapping types and integer utilities | `Number`, `Integer`, `Long`, `Short`, `Byte` | `java.lang` / `java.base` |
| Wrapping floating-point and status checks | `Float`, `Double` | `java.lang` / `java.base` |
| Large integers | `BigInteger` | `java.math` / `java.base` |
| Decimals, precision, rounding | `BigDecimal`, `MathContext`, `RoundingMode` | `java.math` / `java.base` |
| Locale-aware parsing/formatting | `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols` | `java.text` / `java.base` |
| Region/language specification | `Locale` | `java.util` / `java.base` |
| Pseudorandom number generation | `Random`, `SplittableRandom`; `RandomGenerator` since JDK 17 | `java.util` and `java.util.random` / `java.base` |
| Numbers as input/output | `Scanner`, `Formatter` | `java.util` / `java.base` |

`java.lang` is imported automatically. Other packages such as `java.math`, `java.text`, and `java.util` require an import or a fully qualified name.

For example, `BigDecimal` is a standard Java SE API. `import java.math.BigDecimal;` does not represent an external Maven or Gradle dependency outside the JDK. Conversely, a numeric type defined by a third-party library must be checked in **that library's own** documentation and version history, without attributing its release version to Java SE.

### 3.3. What Lies Outside This Lesson

JNI, the incubator Vector API, JVM internals, specialized mathematical algorithms, SQL/JPA mapping, and scientific math libraries are related topics, yet **not prerequisites** for understanding Java Core Numbers scope. Expand into them only when a specific problem demands it.

## 4. What Layers of Compatibility Does "Runs on Java X" Actually Mean?

Saying "this code runs on Java 17" is imprecise without specifying:

1. **Source compatibility:** does the compiler accept the syntax/semantics of the target language version? A syntax feature released after Java 17 cannot be used in source 17 mode.
2. **API compatibility:** are all classes and methods present in the Java SE API of the target version? Old syntax can still call an API introduced only in Java 21.
3. **Binary/class-file compatibility:** which bytecode version was the class compiled to; can the target runtime read it?
4. **Runtime behavior:** the API may exist, yet locale data, providers, implementations, configuration, specified behavior, or bug fixes in patches can affect results.
5. **Support/security:** does the vendor's JDK still receive security updates, and which exact build does the organization support? This is an operational decision, not deduced from code compiling.

For example: building a `.class` with JDK 21 defaults and giving it to a Java 17 runtime typically hits a newer class-file version. Yet even if you force the class-file target to 17, code can still accidentally reference an API present only in 21 unless APIs are constrained at compile time.

### 4.1. Direction Rules for Compatibility

- A newer JDK can usually **compile code targeting an older supported version** via `--release`. Exact supported targets must be checked via `javac --help` on the installed build.
- An older JDK **cannot** compile source/APIs introduced in a future release.
- An older runtime is not guaranteed to run class files generated for a newer Java version.
- A newer runtime has very high backward compatibility, though not a promise that every old program runs untouched; removed APIs, module encapsulation, library dependencies, environment, and settings can cause failures.

An **accurate statement** should read: "Compiled with JDK 21 using `--release 17`, uses only Java SE APIs present in Java 17, and tested on the designated JDK 17." This statement carries far stronger evidence than "written in Java 21 but runs everywhere".

## 5. Check Actual Versions Before Learning or Editing Code

In a terminal, run:

```bash
java -version
javac -version
javac --help
```

- `java -version` shows the runtime version selected by the current `java` command.
- `javac -version` shows the compiler version selected; do not assume both commands point to the same JDK when a machine has multiple Java installations.
- `javac --help` lets you check which `--release` values this compiler accepts.
- Since JDK 9, `java --list-modules` lists the modules in the current runtime, including `java.base`.

If the output differs from expectations, inspect tool paths and terminal, IDE, Gradle, or CI configuration:

```powershell
# Windows PowerShell
Get-Command java
Get-Command javac
```

```bash
# Linux/macOS
command -v java
command -v javac
```

These commands show **which executable the shell finds**. For projects using IDEs, Gradle toolchains, Maven toolchains, containers, or CI, also inspect each tool's configuration because the compiler/runtime used by the build may differ from the shell's default.

Inside a Java application, you can query:

```java
System.out.println(System.getProperty("java.version"));
System.out.println(Runtime.version().feature());
```

These two lines are just a **code snippet** run inside a method; `Runtime.version()` exists since Java 9. Output depends on the runtime, so do not hardcode expectations like "17" or "21" without checking. Both build JDK and runtime JDK details should be recorded separately when reproducing bugs.

## 6. Using Version-Matched Documentation: Cross-Referencing Method

Do not just search "Java Math docs" and open the first search result. An API page for a newer JDK may list methods absent from the target release. Follow this order:

1. Lock down the **target JDK**, e.g., Java SE 17; also record the build version if different.
2. Open the **API Specification** for that exact version, and navigate to the relevant package/class/method. For example, `java.lang.Math`, `java.math.BigDecimal`, `java.text.NumberFormat`.
3. Read **Since** on the method, constructor, or class to learn when it was first introduced. Check **overloads** too: an existing method name does not mean every signature existed back then.
4. Read **Deprecated** (especially `forRemoval`), **Preview**, **API Note**, and **Throws**, noting boundary-value behavior and empty/null conditions.
5. If the API exists in the target JDK, verify with `javac --release <target>`; if absent, weigh an older-API solution or intentionally bumping the minimum JDK.
6. When upgrading JDKs, read the **release notes** and **migration guide**, then run tests on the actual deployment runtime; API docs do not replace real execution verification.

Useful root links (open and switch to the right version when needed):

- [Java SE 8 API](https://docs.oracle.com/javase/8/docs/api/) — baseline reference for long-standing APIs.
- [Java SE 11 API](https://docs.oracle.com/en/java/javase/11/docs/api/) — compare against pre-JDK 12 APIs.
- [Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/) — baseline for Java 17+ examples.
- [Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/) — check APIs and methods added in 21.
- [Java Language Specification](https://docs.oracle.com/javase/specs/) — rules for types, operators, and language semantics.
- [JDK Enhancement Proposals (JEP)](https://openjdk.org/jeps/0) — context and status of major changes.

**Read at the right level:** use the JLS to verify `int / int` and type conversions; use API docs to verify `Math.addExact` or `NumberFormat.getCompactNumberInstance`; use release notes/migration docs to investigate behavior impacted by a JDK upgrade.

## 7. Version Milestones Illustrated Directly with Numbers

The table below focuses on a few verifiable APIs and is **not an exhaustive list of changes** in each release.

| Milestone | Numbers Example | Since Version | Cross-Referencing Implication |
| --- | --- | --- | --- |
| Java 8 | `Math.addExact(int, int)`, `Integer.compareUnsigned` | 8 | When targeting below 8, cannot assume these APIs exist |
| Java 9 | `Math.multiplyHigh(long, long)` | 9 | Must check `Since` on the exact overload |
| Java 12 | `NumberFormat.getCompactNumberInstance(...)`, `CompactNumberFormat` | 12 | Valid Java 11 syntax still cannot use this API if targeting 11 |
| Java 17 | `java.util.random.RandomGenerator` and new random API family | 17 | Must verify version when switching from legacy `Random` to the new API |
| Java 17 | JEP 306 restores always-strict floating-point semantics | 17 | Floating-point cross-referencing is not just finding new APIs |
| Java 21 | `Math.clamp(...)` | 21 | Method unavailable in Java 17; requires target 21 or writing equivalent logic |

**A common mistake:** seeing that `Math` has existed for ages and assuming `Math.clamp` works on Java 8. The age of a **class** and of a **method** are two different facts.

**Floating-point note:** JEP 306 in Java 17 makes floating-point operations follow uniform strict semantics, replacing the earlier strict/default distinction. That does not make `double` an exact decimal number. For code sensitive to floating-point results or performance, read the spec and run accuracy tests on the relevant runtimes.

**Random generation note:** `RandomGenerator` provides new pseudorandom interfaces/algorithms since 17; do not use it by default for cryptography. When security-grade randomness is needed, use `SecureRandom` under an appropriate security contract.

## 8. Example A — Basic Numbers Operations Running on JDK 17+

This example illustrates long-standing standard APIs without depending on new JDK 21 features. Save **`NumbersBase.java`**:

```java
import java.math.BigDecimal;

public class NumbersBase {
    public static void main(String[] args) {
        int total = 7;
        int groups = 2;

        System.out.println(total / groups);
        System.out.println((double) total / groups);
        System.out.println(Math.addExact(20, 22));

        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println(exact);
    }
}
```

Run on JDK 17 or newer:

```bash
javac NumbersBase.java
java NumbersBase
```

Result:

```text
3
3.5
42
0.3
```

Explanation:

- `int / int` drops the fractional part; casting one operand to `double` **before division** yields `3.5`.
- `Math.addExact` performs integer addition with overflow checking. `20 + 22` fits in `int`, returning `42`.
- `BigDecimal` initialized from **decimal strings** performs exact decimal addition in this example.
- Results follow standard arithmetic rules; API existence must be cross-referenced from the corresponding version's docs, not inferred from compiling with a newer JDK by default.

If this program must be Java 17 compatible when built on JDK 21, use:

```bash
javac --release 17 NumbersBase.java
java NumbersBase
```

`--release 17` instructs the compiler to compile under version 17 language rules, emit version 17 class files, and restrict Java SE/JDK APIs to version 17. The `java NumbersBase` line above runs on **whichever runtime the terminal selects**, so you still need to test on a real JDK 17 if that is the supported target.

## 9. Example B — API Introduced After the Target Release: Compact Number Formatting

Create **`CompactNumbers.java`**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactNumbers {
    public static void main(String[] args) {
        NumberFormat format = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);
        System.out.println(format.format(1200));
    }
}
```

`NumberFormat.getCompactNumberInstance` was introduced in **Java 12**. Therefore, with a JDK 17 or 21 compiler supporting target 11:

```bash
javac --release 11 CompactNumbers.java
```

The command **must report a compile error** because compact formatting methods do not exist in the Java 11 API; exact error wording/line numbers depend on the compiler version and how `javac` is invoked. Next:

```bash
javac --release 17 CompactNumbers.java
java CompactNumbers
```

The code can compile because Java 17 contains this API. The compact string printed depends on locale data and runtime version, so do not treat a single output string observed on one machine as an immutable contract across all JDKs. If the project requires Java 11, pick legacy `NumberFormat` or define and test your own compact-formatting rules; do not just change `--target`.

### Why Are `--source` and `--target` Alone Insufficient?

- `--source 11` checks Java 11 **syntax/language rules**.
- `--target 11` selects the **class-file format** for the target version.
- Those two options **do not guarantee** that every referenced Java SE API exists in Java 11 if compiling against the current platform APIs/classpath.
- `--release 11` combines all three: syntax, class file, and the documented Java SE/JDK APIs of version 11. `--release` cannot be combined with `--source` or `--target` in the same invocation.

Therefore, for projects needing to run on an older Java version, **`--release` is the right starting point**. You still need to audit dependencies and test against the actual target runtime.

## 10. Example C — Reading `Since` Accurately for a JDK 21 Method

Create **`ClampNumbers.java`**:

```java
public class ClampNumbers {
    public static void main(String[] args) {
        System.out.println(Math.clamp(150, 0, 100));
        System.out.println(Math.clamp(-5, 0, 100));
    }
}
```

The `Math.clamp` overloads exist since **Java 21**. Run with JDK 21:

```bash
javac --release 21 ClampNumbers.java
java ClampNumbers
```

Result:

```text
100
0
```

If the compiler supports `--release 17`, running `javac --release 17 ClampNumbers.java` reports that no matching method exists in the Java 17 API. That is an **API-version** error, not that numeric clamping is impossible on Java 17.

When Java 17 support is required, you can write an equivalent helper for a specific data domain:

```java
public static int clampInt(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return Math.max(min, Math.min(max, value));
}
```

The snippet above is an **illustrative method**, placed inside a class before calling; it does not replace every overload or every contract detail of `Math.clamp` (especially floating-point, `NaN`, signed zero). This is precisely why you must read the **signature and contract** before writing your own replacement.

## 11. Bytecode: Why Compiled Code Can Still Fail to Run

A source file can be compiled into class files targeting a newer version than the target runtime. Common **class-file major version** milestones:

| Java release | Class-file major |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

When a class is compiled for Java 21 (major 65), a Java 17 runtime (supporting up to major 61) cannot load it. The error typically mentions `UnsupportedClassVersionError`. This is a **bytecode-level** error, distinct from missing a class or method at runtime.

You can inspect class-file info using:

```bash
javap -verbose NumbersBase
```

Look for the `major version: ...` line in the output. The `javap` tool ships with the JDK toolkit. Practical verification steps:

1. Compile with the project compiler using `--release` set to the proper target.
2. Check the major version when needing proof that an artifact matches the target.
3. Run tests on the actual deployment Java runtime.
4. Ensure all dependencies use class files and APIs supported by the target runtime.

`--release` controls compilation of **sources compiled in that invocation**; it does not recompile dependency JARs built with a newer JDK or resolve differences in non-Java-SE providers.

## 12. Subtle Differences Easy to Miss Even When Code Compiles

### 12.1. Comparison and Precision Behavior

A `double` operation can produce an approximate result due to binary representation. Changing JDKs does not automatically fix `0.1 + 0.2 == 0.3`. Set a tolerance for measurements, or use `BigDecimal` and scale/rounding rules when exact decimal contracts are required. Numerically sensitive operations should have boundary tests across all supported JDKs.

### 12.2. Locale and Formatting Data

`NumberFormat`, `DecimalFormat`, locale/CLDR data, and locale service providers can affect how the same number is formatted across environments. Do not write tests comparing a string `"1.234,50"` observed on one machine against strings from arbitrary locales.

For predictable output, pass an explicit `Locale`, standardize currency, rounding rules, and provider data; avoid accidentally relying on the default locale. Even with a fixed locale, formatting data/conventions can be updated between JDKs; any test asserting exact characters should state the runtime version and business requirement.

### 12.3. Deprecation, Preview, Incubator, Internal APIs

- An API marked `@Deprecated` may **still compile** on the current release, yet you should check the reason, when the warning was introduced, and whether it is marked "for removal".
- **Preview features/APIs** have special activation requirements and can change or be removed in a later release. Do not rely on preview features for foundational Numbers tasks unless explicitly testing that feature.
- **Incubator modules** are not stable standard APIs of `java.base`; check exact status in the version used.
- `sun.*` and `jdk.internal.*` are not standard API surfaces and should not be relied on for everyday numeric operations.

### 12.4. Differences Across Versions and Vendors

Even within the same Java SE feature release, different vendors/builds/updates may carry different patches, system data, or support schedules. When reproducing a bug, record the exact `java -version` output, OS/architecture, required JVM flags, and input data. When deciding to upgrade a JDK, cross-reference the support policy of **the vendor you use**, rather than inferring from a generic LTS label.

## 13. Seven-Step Workflow to Check Any Numbers Code Snippet

Suppose you see `Math.clamp(amount, 0, 100)` in documentation or on a forum.

**Step 1 — Record the target environment.** For example: the project compiles on JDK 21, yet production must run on Java 17; record 17 as the **minimum runtime**.

**Step 2 — Separate syntax from API calls.** `amount` is `int`, and calling `Math.clamp` belongs to the standard library; the issue may lie in the method, not in Java operators or syntax.

**Step 3 — Look up the exact signature.** Open the `Math` API docs for Java 17 and 21, and compare name, parameter types, overloads, `Since`, and `Throws`.

**Step 4 — Test-compile against the target.** On a newer compiler supporting target 17, run `javac --release 17 ...`. If it fails, read the error to distinguish missing API, type errors, class-name errors, and syntax errors.

**Step 5 — Choose an action.** If the API is from 21, either raise the minimum runtime **by project decision**, or replace it with 17-compatible logic and test boundaries.

**Step 6 — Test on the real runtime.** Check the class-file major version and run tests on the committed JDK 17. For numeric data, include 0, negatives, min/max, tolerances, `NaN`/infinity (if taking `double`), scale/rounding, and locale when relevant.

**Step 7 — Record evidence.** A reproducible note includes code, target release, compile JDK, runtime JDK, test commands, output, and API doc sources; do not merely write "supports Java 17" after just glancing at the code.

Example of a clear technical report:

```text
Target: run on Java 17
Build JDK: 21
Compiler flags: javac --release 17
Verified API: Math.addExact(int,int) - Since 8
Runtime check: tested on deployment environment's JDK 17
Remaining risks: external non-JDK dependencies and provider/locale need separate tests
```

This is a **report template**, not test results executed for a real project.

## 14. Self-Check Questions

1. Do `BigInteger` and `BigDecimal` require adding a Maven dependency? **No.** They are standard APIs in `java.math`.
2. Why does code calling `NumberFormat.getCompactNumberInstance` run on JDK 17 yet fail to compile with `--release 11`? **Because this API was introduced in Java 12**, so it is not in the target 11 API.
3. Using JDK 21, does compiling with `--source 17 --target 17` automatically prevent referencing a method introduced only in 21? **No guarantee**; use `--release 17` to restrict the APIs as well.
4. Can a major version 65 class file run on Java 17? **No**; Java 17 supports class files up to major 61.
5. `Math` has been in Java for a long time, so is `Math.clamp` in Java 17? **No**; check `Since 21` on the corresponding overload.
6. Can two JDKs both on Java 17 differ in locale data or patches? **Yes**; record vendor/build/update and test in the actual environment.
7. Is compiling cleanly enough to claim "runs on Java 17"? **Not yet.** You must cross-reference APIs, class files, dependencies, and runtime.
8. When learning Numbers, what is the right starting point? **Stick to the target JDK**, practice primitives/`Math`/wrappers/`BigDecimal` against the matching APIs, and only then explore newer features.

## 15. Checklist When Reading Every Subsequent Java Core — Numbers Lesson

- [ ] I know the **minimum supported Java release** of the exercise/project.
- [ ] I have separated language syntax from classes/methods in the Java SE API.
- [ ] I open the **API docs for the exact target version**, not just the latest JDK page.
- [ ] I check `Since` on the exact **method/overload** being used, along with `Throws`, `Deprecated`, and preview status if applicable.
- [ ] I know the active compiler JDK and runtime JDK, without confusing IDE/CI/shell settings.
- [ ] I use `--release` when compiling for an older target supported by the compiler.
- [ ] I test execution on the target runtime, auditing external dependencies and class-file versions.
- [ ] I verify numeric results, overflow, precision, rounding, locale, and boundary data where relevant.
- [ ] I record versions, commands, and results so others can reproduce them.

**Official references** for self-verification: [JDK 17 Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [JDK 21 Math API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html), [JDK 17 BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [JDK 12 NumberFormat API](https://docs.oracle.com/en/java/javase/12/docs/api/java.base/java/text/NumberFormat.html), [JDK 17 random package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html), [javac command specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), and [JDK 17 migration notes](https://docs.oracle.com/en/java/javase/17/migrate/significant-changes-jdk-release.html).