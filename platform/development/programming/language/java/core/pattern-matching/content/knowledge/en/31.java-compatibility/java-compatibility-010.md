# Multi-JDK Support Strategies in Java Pattern Matching

## 1. The Java Compatibility Problem and Architectural Goals

A Java library may be used by customers still running **JDK 17**, while internal services have already moved to **JDK 21** and want to use record patterns together with pattern matching for `switch`. If you upgrade the compiler without a clear design, the development team can accidentally introduce new bytecode, new APIs, or syntax valid only in Java 21 into an artifact declared to support Java 17.

The problem of **supporting multiple JDKs** is not simply “code compiles on the developer's machine.” A compatible release must consider:

- **Source compatibility:** Is the syntax/language feature valid for the committed source level?
- **Binary compatibility:** Can `.class` files and dependencies be loaded by the target runtime?
- **API compatibility:** Does the code call Java SE APIs or libraries that only exist in newer Java versions?
- **Runtime compatibility:** Does the application actually start, behave correctly, and integrate properly on every supported JVM?
- **Behavior parity:** If two JDK-specific implementations are provided, do they enforce the same business contract?

The running example has three event types: `Login`, `Logout`, and `Failure`. The Java 17 version uses `sealed interface`, `record`, and type patterns with `instanceof`; the Java 21 version expresses the same logic using record patterns, a `switch` expression, and `when` guards. Both programs can run independently and produce the exact same eight lines of output.

**Goal:** Know how to choose a baseline JDK, use `javac --release`, organize modules/source sets, understand multi-release JARs, build a CI matrix, and troubleshoot common version errors. The example uses **JDK 17 and JDK 21** because they represent two distinct pattern matching feature levels, not as a rule that every product should only support those two versions.

## 2. Feature Matrix: What Can Java 17 Do, and What Does Java 21 Add?

| Feature | Official Java Release | Java 17 Source Baseline |
| --- | --- | --- |
| `switch` on constants and enums | Available for a long time | Yes |
| `switch expression` | Java 14, JEP 361 | Yes, but without type patterns in `case` |
| `instanceof SomeType value` | Java 16, JEP 394 | Yes |
| `record` | Java 16, JEP 395 | Yes |
| `sealed class` / `sealed interface` | Java 17, JEP 409 | Yes |
| Record patterns `Point(int x, int y)` | Java 21, JEP 440 | **No** |
| Pattern matching in `switch` | Java 21, JEP 441 | **No** |
| Pattern `switch` `when` guard | Java 21, JEP 441 | **No** |

Java 17 is enough to build a closed domain model with records and use type patterns via `instanceof`. However, syntax like:

```java
// Java 21 example, assuming the event variable and subtypes already exist:
return switch (event) {
    case Login(String name, int attempts) when attempts >= 3 ->
        "REVIEW:" + name;
    case Login(String name, int attempts) ->
        "LOGIN:" + name;
    default -> "OTHER";
};
```

is not valid when compiled with `--release 17`.

**Do not confuse final features with preview features:** Java 17–20 had preview versions related to pattern `switch` or record patterns. Syntax and rules could change across previews. `when` and record patterns in this article are **official Java 21 syntax**, with no need to enable `--enable-preview`. Enabling preview also does not make a Java 21 program run on JVM 17.

## 3. Distinguishing JDK Compiler, Source, Target, API, and Runtime

The same project can use **JDK 21 to compile** while requiring **class files to run on JVM 17**. You need to distinguish these five axes.

### 3.1. Compiler JDK

This is the `javac` tool that performs compilation. Check with:

```bash
javac -version
java -version
```

The two commands do not necessarily use the same JDK version if `PATH` or `JAVA_HOME` is misconfigured. In CI, you must log both the compiler and the runtime of the test task, not just `JAVA_HOME`.

### 3.2. Source Language Level

The source level determines which syntax is accepted. For example, sealed interfaces and records can both compile with source 17, whereas `case Login(String ...) when ...` requires Java 21.

You cannot feed Java 21 source into a Java 17 compiler simply by renaming files, adding casts, or moving code into a `java21` directory while still using compiler 17.

### 3.3. Bytecode / Class-File Target

The JVM must understand the compiled class-file version:

| Java target | Class-file major | Corresponding minimum runtime |
| --- | --- | --- |
| Java 17 | **61** | Java 17 |
| Java 21 | **65** | Java 21 |

JVM 17 cannot normally read a major 65 class file. The common error is `UnsupportedClassVersionError`. Even code that does not use Java 21 APIs will still hit this error if compiled with target 21.

Inspect the compiled class with:

```bash
javap -verbose CompatibilityBaselineDemo
```

Look for the `major version` line. Be careful with classpath and output directories so you do not inspect a stale file by mistake.

### 3.4. Java SE API Level

Source code using Java 17 syntax can accidentally call an API that only exists in Java 21 if compiled on JDK 21 without constraining the standard library. It may compile, yet fail with `NoSuchMethodError` on runtime 17.

**Default solution:** Use `javac --release 17` instead of only combining `-source 17 -target 17`. `--release` aligns the source language level, bytecode version, and Java SE APIs to match the specified release.

However, `--release` does **not** check external non-JDK dependencies, native libraries, or dynamically loaded classes for you.

### 3.5. Runtime JVM and Dependencies

This is the actual JVM when the application runs. Compatibility can be broken by:
- A dependency JAR having a class-file version that is too new.
- A dependency method changing between compile time and runtime.
- Reflection or `ServiceLoader` loading an implementation class that only exists on Java 21.
- Changes in module boundaries, JVM flags, TLS/security providers, or native integration.
- A properly built artifact packaged into a Docker image using an older JVM.

Therefore, **“builds successfully on JDK 21” is not enough to claim it runs on JDK 17**. You must run tests on an actual runtime 17 if the product commits to supporting it.

## 4. Strategy A: A Single Java 17 Source Baseline

When most customers must run Java 17 and the syntactic benefits of Java 21 are not yet large enough, the easiest approach to maintain is:

1. Choose **minimum supported runtime = 17**.
2. Write core source code using up to the final features available in Java 17.
3. Use `javac --release 17` in CI, even when the compiler is JDK 21 or newer.
4. Run tests on **JVM 17** and one or more newer JVMs.
5. Do not introduce Java 21 pattern `switch` into the baseline module.

### 4.1. Complete Java 17 Program

Create the file **`CompatibilityBaselineDemo.java`**:

```java
public class CompatibilityBaselineDemo {
    sealed interface Event permits Login, Logout, Failure {}

    record Login(String user, int attempts) implements Event {}
    record Logout(String user) implements Event {}
    record Failure(int code) implements Event {}

    static String describe(Event event) {
        if (event == null) return "NONE";

        if (event instanceof Login login) {
            if (login.user() == null || login.user().isBlank())
                return "LOGIN_INVALID";
            if (login.attempts() >= 3)
                return "LOGIN_REVIEW:" + login.user();
            return "LOGIN:" + login.user();
        }

        if (event instanceof Logout logout)
            return "LOGOUT:" + logout.user();

        if (event instanceof Failure failure) {
            if (failure.code() >= 500)
                return "FAIL_CRITICAL:" + failure.code();
            return "FAIL:" + failure.code();
        }

        throw new IllegalStateException("Unknown event subtype");
    }

    public static void main(String[] args) {
        Event[] events = {
            new Login("Lan", 0), new Login("Lan", 3),
            new Login("", 1), new Login(null, 1),
            new Logout("Minh"), new Failure(404),
            new Failure(503), null
        };

        for (Event event : events)
            System.out.println(describe(event));
    }
}
```

Compile on JDK 17 or a newer JDK that supports target 17:

```bash
javac --release 17 CompatibilityBaselineDemo.java
java CompatibilityBaselineDemo
```

**Exact stdout:**

```text
LOGIN:Lan
LOGIN_REVIEW:Lan
LOGIN_INVALID
LOGIN_INVALID
LOGOUT:Minh
FAIL:404
FAIL_CRITICAL:503
NONE
```

**Explanation:**
- `Event` is a sealed interface, and the permitted record subtypes are final types; these are all final features introduced before or in Java 17.
- `event instanceof Login login` checks the type and binds a variable already typed as `Login`.
- `login.user()` and `login.attempts()` are record accessors; record deconstruction patterns are not used yet.
- `if` statements handle the business conditions corresponding to `when` guards in the Java 21 version.
- `event == null` must be handled explicitly because `null instanceof Login` is always false.
- The `IllegalStateException` fallback is for subtypes not handled by any branch. **An `if/else` chain is not proven exhaustive by the compiler**, even when `Event` is sealed.

**Trade-off:** Keeps a single implementation and a single easy-to-deploy artifact, but cannot use Java 21 record patterns/switch patterns and lacks compile-time exhaustiveness from enhanced switch.

## 5. Strategy B: Java 17 Contract with a Separate Java 21 Implementation

A project can keep its domain API on Java 17 while adding an implementation optimized for clarity using Java 21 syntax.

Suggested organization:

```text
compat-api/        -- compile --release 17
    Event, Login, Logout, Failure, EventDescriber

compat-impl17/     -- compile --release 17
    Java17EventDescriber

compat-impl21/     -- compile --release 21
    Java21EventDescriber

application/       -- selects the valid implementation per deployment
```

**Note:** This is an architectural diagram. The two standalone demos in this article declare their own nested types so each can be compiled as a single file. In a real multi-module product, the domain types should live in **one shared API module**, rather than copying `Event` definitions into two JARs and causing duplicate class names.

The contract can be a target-17 interface such as:

```java
// Illustrative snippet in compat-api, assuming Event already exists:
interface EventDescriber {
    String describe(Event event);
}
```

Both implementations fulfill the same contract, differing only in the source language level they are allowed to use.

### 5.1. Complete Java 21 Program

Create the file **`CompatibilityPatternDemo.java`** in a **separate Java 21 source set**:

```java
public class CompatibilityPatternDemo {
    sealed interface Event permits Login, Logout, Failure {}

    record Login(String user, int attempts) implements Event {}
    record Logout(String user) implements Event {}
    record Failure(int code) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Login(String user, int attempts)
                    when user == null || user.isBlank() ->
                "LOGIN_INVALID";

            case Login(String user, int attempts) when attempts >= 3 ->
                "LOGIN_REVIEW:" + user;

            case Login(String user, int attempts) ->
                "LOGIN:" + user;

            case Logout(String user) ->
                "LOGOUT:" + user;

            case Failure(int code) when code >= 500 ->
                "FAIL_CRITICAL:" + code;

            case Failure(int code) ->
                "FAIL:" + code;

            case null -> "NONE";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Login("Lan", 0), new Login("Lan", 3),
            new Login("", 1), new Login(null, 1),
            new Logout("Minh"), new Failure(404),
            new Failure(503), null
        };

        for (Event event : events)
            System.out.println(describe(event));
    }
}
```

Compile and run **only on JDK 21 or newer**:

```bash
javac --release 21 CompatibilityPatternDemo.java
java CompatibilityPatternDemo
```

**Exact stdout, matching the Java 17 version:**

```text
LOGIN:Lan
LOGIN_REVIEW:Lan
LOGIN_INVALID
LOGIN_INVALID
LOGOUT:Minh
FAIL:404
FAIL_CRITICAL:503
NONE
```

**Syntactic differences:**
- `case Login(String user, int attempts)` is a record pattern that binds components directly.
- `when user == null || user.isBlank()` is a guard; the `||` operator prevents calling `isBlank()` on null.
- The `attempts >= 3` guard appears before the unguarded `Login` case; reversing the order causes a *dominated case* error.
- The unguarded `case Failure(int code)` and the other cases cover every subtype of sealed `Event`. The Java 21 compiler verifies that the switch expression is exhaustive; `default` is not needed.
- `case null` handles a **null selector**, whereas `user == null` handles a **null record component**. In the `String` component position, an unconditional type pattern can bind null.

### 5.2. Why Are the Two Versions Equivalent?

In Java 17, `if (event instanceof Login login)` accepts a `Login` and retrieves components via accessors. In Java 21, `case Login(String user, int attempts)` combines the type check and record deconstruction. Both apply the same conditions (`attempts >= 3`, `code >= 500`) and null rules.

Identical output is evidence of **parity on the eight tested cases**, not proof that every possible input is always equivalent. A real application needs additional boundary data, validation, exception cases, and tests when adding subtypes.

### 5.3. Preventing Target-21 Classes from Loading on JVM 17

An implementation compiled with `--release 21` produces major 65 class files; JVM 17 cannot load them. Only calling the Java 21 implementation behind an `if` may not be enough if the system already loads that class during initialization, reflection, classpath scanning, or dependency injection.

**Safe design:**
- The baseline API must not directly depend on classes that require Java 21.
- In runtime 17 deployments, do not include the Java 21 implementation on the codepath to be loaded.
- Select the implementation via module packaging, deployment configuration, or a controlled loading mechanism.
- If using `Runtime.version().feature()` or reflection to select, the check must run **before loading the Java 21 class**.
- Test class loading on an actual JVM 17; do not assume a classpath “containing both versions” is automatically safe.

Reflection cannot make major 65 bytecode run on JVM 17. If you need **a single artifact** that automatically selects an implementation by runtime, see multi-release JARs.

## 6. Strategy C: Multi-Release JAR (MR-JAR)

A **Multi-release JAR** (JEP 238) contains base classes alongside alternative class versions under `META-INF/versions/<number>/`. An MR-JAR-aware runtime picks the appropriate version when the manifest is properly marked.

Example structure:

```text
compat.jar
├── example/
│   └── EventFormatter.class                 # baseline 17
└── META-INF/
    ├── MANIFEST.MF                         # Multi-Release: true
    └── versions/
        └── 21/
            └── example/
                └── EventFormatter.class     # implementation 21
```

Both `EventFormatter.class` files share the **same binary name** and must preserve a compatible public API. Java 17 selects the root version; Java 21 can select the version 21 class. Unlike “dumping Java 21 classes into a regular JAR,” this uses a versioned layout understood by the JVM and `jar`.

### 6.1. Illustrative Packaging Workflow

Suppose the project has two sources for the **same class `example.EventFormatter`**, located under `src/java17` and `src/java21`, with a consistent API. These are the sources for the MR-JAR approach, **not the two standalone programs with different names** from Sections 4 and 5.

```bash
javac --release 17 -d build/java17 src/java17/example/EventFormatter.java
javac --release 21 -d build/java21 src/java21/example/EventFormatter.java

jar --create --file compat.jar --manifest MANIFEST.MF \
  -C build/java17 . --release 21 -C build/java21 .

jar --list --file compat.jar
jar --validate --file compat.jar
```

The `\` line continuation in the `jar` command above is for Unix-like shells. In Windows PowerShell, write it on **a single line** or use PowerShell's line continuation rules.

A sample manifest:

```text
Manifest-Version: 1.0
Multi-Release: true
```

The manifest file must follow the JAR manifest format, including the required trailing newline. `jar --validate` helps verify public API consistency in the MR-JAR; `jar --list` lets you inspect whether entries are placed under the right versioned paths. These checks **do not replace** testing on runtime 17 and runtime 21.

### 6.2. When to Choose MR-JAR?

Suitable when:
- You need to distribute **a single library** for both older and newer runtimes.
- Only a small part of the implementation needs newer JDK features.
- The contract/public API remains virtually unchanged.
- Your build system, shading, annotation processing, coverage, and runtime tests handle MR-JARs cleanly.

Not suitable if:
- The two implementations have overly divergent APIs or architectures.
- Your build/deploy pipeline has not been verified for handling versioned classes.
- You only have an internal backend that can already be upgraded entirely to Java 21.
- The cost of maintaining two codepaths outweighs the syntactic or optimization benefits.

**Note:** Do not use MR-JAR just to hide a mandatory Java 21 dependency being pulled onto a Java 17 classpath. Dependencies of the Java 17 base must still be compatible with runtime 17. Check the actual packaged artifact, class loaders, and frameworks.

## 7. Strategy D: Raising the Minimum Runtime to Java 21

A much simpler approach is to drop runtime 17 support after an announced upgrade milestone. Once all environments can run Java 21+, you can compile a single source set using the full set of final Java 21 features.

The transition typically follows this order:

1. Assess the **actual runtimes** of customers, services, CI agents, and Docker images.
2. Check compatibility of dependencies, monitoring agents, and native libraries.
3. Run the baseline 17 artifact on JVM 21 first to separate runtime upgrade issues from source upgrade issues.
4. Raise the compiler target to `--release 21` once no runtime 17 needs to be supported.
5. Adopt pattern `switch`/record patterns intentionally; run regressions and benchmarks under realistic workloads.
6. Announce the new minimum runtime and prepare a rollback plan.

**Different build/runtime states:**

| Build/runtime | Meaning |
| --- | --- |
| Compiler JDK 21, `--release 17`, runtime 17 | Can still maintain baseline 17 if dependencies and tests pass |
| Compiler JDK 21, `--release 17`, runtime 21 | An intermediate step to validate the new runtime before upgrading source |
| Compiler JDK 21, `--release 21`, runtime 17 | **Incompatible** |
| Compiler JDK 21, `--release 21`, runtime 21 | Version-valid; still requires functional testing |

Deciding which JDKs to support or drop is a **product contract**, not just a personal preference of Java developers.

## 8. Compiler Flags: Prefer `--release`

### 8.1. Recommended Configuration

With JDK 21 or newer as the compiler:

```bash
# Java 17 source and bytecode, enforcing Java SE 17 APIs:
javac --release 17 CompatibilityBaselineDemo.java

# Java 21 source and bytecode, enabling record/switch patterns:
javac --release 21 CompatibilityPatternDemo.java
```

`--release` prevents three classes of errors:
- Using syntax unavailable in the baseline.
- Generating class files for a higher runtime than intended.
- Calling Java SE APIs that do not belong to the chosen release.

### 8.2. Why `-source` and `-target` Alone May Not Be Enough

```bash
javac -source 17 -target 17 SomeClass.java
```

This sets the source and bytecode versions, but does not automatically enforce the same Java SE API boundary as `--release 17`. When compiling on a newer JDK, seemingly valid source code risks linking against APIs that do not exist on the older runtime.

**Do not conclude** that using `--release` alone finishes the job. It does not lock Maven/Gradle dependency versions, inspect every native library, automatically run tests on JVM 17, or govern reflection.

### 8.3. Preview Is Not a Downgrade Mechanism

The `--enable-preview` flag is for preview features of the corresponding release. It should not be used to “make Java 21 record patterns run on Java 17.”

In older JDK previews, pattern `switch` underwent syntax and semantic changes. When upgrading to Java 21, move to the **final** feature and standard `when` syntax rather than keeping preview flags out of habit.

## 9. Maven: Separating Compiler Targets by Module

For a baseline module, the typical property in `pom.xml` is:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

For a Java 21-only module, set `maven.compiler.release` to `21` in that specific module or configure `maven-compiler-plugin` separately. Do not change the global property of the entire reactor to 21 if you still intend to publish baseline modules with class-file version 61.

**Maven Toolchains** help select the JDK used for build steps; they do not replace target configuration. A build running Maven on JDK 21 may still need toolchain 17 for testing or specialized tasks. Check the actual build logs to verify which compiler and release are in use.

### A Suggested Module Structure

```text
parent-pom
  ├── compat-api         release 17
  ├── compat-impl17      release 17
  ├── compat-impl21      release 21
  └── compatibility-tests
```

Do not let `compat-api` import classes that exist only in `compat-impl21`; dependencies should flow from implementations to the contract, not the other way around.

## 10. Gradle: A Toolchain Is Not a Release

In the baseline module's `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

**Meaning:**
- Java toolchain 21: uses the JDK 21 compiler for compile tasks.
- `options.release.set(17)`: emits Java 17 bytecode, source level, and APIs.

In the Java 21 module you can set `options.release.set(21)`, though those classes still cannot be used on runtime 17.

**Important:** The test JVM does not necessarily match the compile target. If `test` runs on JVM 21, green tests do **not** prove runtime 17 compatibility. You must configure a Java launcher/test task or CI matrix running on a real JVM 17.

Depending on the Gradle/JDK versions, verify compatibility of the build tool itself, plugins, and dependencies before upgrading.

## 11. Minimum CI Matrix and Parity Tests

A suitable matrix for a runtime 17/21 scope:

| Artifact | Compile | JVM 17 | JVM 21 |
| --- | --- | --- | --- |
| `compat-api` + `compat-impl17` | `--release 17` | **Must PASS** | **Must PASS** |
| `compat-impl21` | `--release 21` | Unsupported / not loaded | **Must PASS** |
| MR-JAR base 17 + version 21 | Compile each part accordingly | Tests run base 17 | Tests run version 21 |
| Java 21 source forced to target 17 | **Does not compile validly** | No artifact | No artifact |

### 11.1. Job Organization

```text
compile-baseline:
    build api + impl17 with --release 17

test-java17:
    run baseline artifact on real JVM 17

test-java21:
    run baseline artifact on real JVM 21

compile-impl21:
    build implementation 21 with --release 21

test-impl21:
    run Java 21 implementation on JVM 21
    compare results against baseline

validate-package:
    check class major versions,
    manifest and MR-JAR if used,
    dependency graph and class-loading capability
```

This is a CI blueprint, not ready-to-run YAML for a specific provider. For a real build system, translate it into jobs or a matrix using the syntax of GitHub Actions, GitLab, Jenkins, etc.

### 11.2. Eight Verified Parity Cases

Both programs in Sections 4–5 use the same inputs and outputs:

| Input | Output |
| --- | --- |
| `Login("Lan", 0)` | `LOGIN:Lan` |
| `Login("Lan", 3)` | `LOGIN_REVIEW:Lan` |
| `Login("", 1)` | `LOGIN_INVALID` |
| `Login(null, 1)` | `LOGIN_INVALID` |
| `Logout("Minh")` | `LOGOUT:Minh` |
| `Failure(404)` | `FAIL:404` |
| `Failure(503)` | `FAIL_CRITICAL:503` |
| `null` | `NONE` |

The pair `Login("", 1)` and `Login(null, 1)` tests invalid data inside a component. `null` in the last row is a **null selector**, which is distinct from a null component.

Extend tests to compare both sides of thresholds—such as `attempts=2/3` and `code=499/500`—as well as exception cases. A codepath that changes `>= 500` to `> 500` might pass generic tests while failing at the `500` boundary.

### 11.3. When a Sealed Hierarchy Is Extended

If you add:

```java
// Illustrative model change; do not add to the two programs
// without updating the corresponding handling logic:
record Locked(String user) implements Event {}
```

you must update `Event`'s `permits` clause. When you do:

- The Java 17 `if/else` chain may **still compile**, but will fall through to `IllegalStateException` if logic for `Locked` is not added.
- The Java 21 `switch` that was exhaustive over the previous three subtypes will **fail to compile** if `case Locked(...)` is missing and there is no appropriate fallback.
- Tests must add new cases for both implementations and verify parity.

Exhaustiveness is helpful in Java 21, but it does not replace **business tests**; the compiler knows the set of subtypes, not which output string is correct.

## 12. Dependencies, Reflection, and Class Loading

### 12.1. Transitive Dependencies Can Unintentionally Raise the Baseline

Even when all project code compiles with `--release 17`, a newer library version may contain major 65 class files. Symptoms might only appear at runtime when a specific API is exercised, not necessarily at startup.

You should inspect:
- `dependency:tree`/dependency graph or equivalent tooling.
- The declared minimum JDK of each key dependency.
- The final artifact after shading/packaging.
- Real runtime paths, especially rarely executed features.

### 12.2. Reflection Does Not Bypass Class-File Limits

`Class.forName("example.Java21Impl")` still requires the runtime to be able to load the target class's bytecode. JVM 17 cannot “skip” version 65 via reflection.

If you need runtime-based implementation selection, do it at the boundary:
- Check the runtime version before loading newer classes.
- Separate classpath/modulepath per deployment.
- Use MR-JAR if a single self-selecting artifact by version is a real requirement.
- Avoid static references that cause the newer class to be loaded along the baseline codepath.

### 12.3. Running on a Newer JDK Is Not Guaranteed

A target-17 class can usually load on runtime 21, yet the application may still encounter changes in JVM flags, module encapsulation, security providers, native integrations, or dependencies. Therefore **forward runtime compatibility** must be tested, not merely inferred from class-file versions.

## 13. Troubleshooting Common Compatibility Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Class file is newer than the running JVM | Check major 61/65, target release, dependencies, and runtime |
| `switch patterns are not supported in -source 17` or similar diagnostic | Java 21 syntax placed in a source-17 module | Switch to `instanceof` or separate into target-21 source |
| Diagnostics about `when`/record patterns | Wrong compiler/source level or old preview code | Check `javac -version`, `--release`, and final Java 21 syntax |
| `NoSuchMethodError` | Runtime API/dependency differs from compile time | Lock APIs with `--release`, check dependency binary versions |
| `NoClassDefFoundError` | Required class is missing or cannot be loaded | Check classpath/modulepath, runtime, and dependency isolation |
| `IncompatibleClassChangeError` | Binary definitions are incompatible with compile time | Align modules/dependencies, audit API changes |
| `switch expression does not cover all possible input values` | Added a sealed subtype but missed a case | Add the case and tests; avoid hiding gaps with `default` |
| `this case label is dominated` | Broader pattern precedes a more specific pattern | Place guarded/specific cases first |
| MR-JAR picks the wrong version | Incorrect manifest or versioned path | Check layout, `jar --list`, `jar --validate`, and runtime tests |
| Build passes on JDK 21, fails in production JDK 17 | Lowest supported runtime was not tested | Add a real JVM 17 job; inspect artifacts and dependencies |

Do not look only at the top of a stack trace and conclude the new source is at fault. If `UnsupportedClassVersionError` names a class inside a dependency, inspect **that dependency**, not just project code.

### Common Anti-Patterns

- Switching all modules to `--release 21` just because the CI compiler was upgraded.
- Running a single test on JVM 21 and declaring JDK 17 support.
- Copying Java 21 source into a shared target-17 module and trying to “fix” it with `--enable-preview`.
- Packing Java 21 classes into a regular JAR and hoping JVM 17 never sees them.
- Letting the baseline API directly depend on the Java 21 implementation.
- Using a broad `default` to avoid updating subtypes of a sealed hierarchy.
- Assuming an MR-JAR automatically preserves API parity without tests.
- Ignoring dependency minimum JDKs or container images.
- Using `-source/-target` instead of `--release` and forgetting API boundaries.
- Raising the minimum JDK without updating documentation and the rollout plan.

## 14. Decision-Making Process for Real Projects

**Step 1 — Lock down support.** Document the lowest JDK, the actual committed runtimes/vendors, support timelines, and relevant customers/deployment targets.

**Step 2 — Inventory code.** Identify Java 21-only features (record patterns, pattern `switch`, `when`) and APIs/dependencies only present on newer runtimes. Distinguish features finalized in Java 17 from previews of earlier releases.

**Step 3 — Choose a structure:**
- Must run broadly on Java 17, small need for new syntax → **single baseline 17**.
- Only a few modules need Java 21 → **API 17 + implementation 21**.
- Must ship a single library artifact while optimizing per JDK → consider **MR-JAR**.
- Can upgrade all runtimes → **raise baseline to 21**, reducing codepaths.

**Step 4 — Lock compile targets.** Record `--release` per module; pin toolchains and avoid accidentally compiling all source for target 21.

**Step 5 — Build the runtime matrix.** Use real JVM 17 for the baseline, real JVM 21 for both baseline and implementation 21; add other runtimes/versions if required by the support contract.

**Step 6 — Add parity tests.** Identical inputs must produce results/exceptions matching the contract across both implementations, including new subtypes, nulls, and guard boundaries.

**Step 7 — Validate binaries/packages.** Check major versions, dependency graphs, service loading, MR-JAR manifest/layout, and runtime class selection.

**Step 8 — Roll out with control.** Upgrade the JVM, verify operations, and only then adopt newer source features once older runtimes are no longer committed. Prepare rollback and announce minimum JDK changes.

## 15. Hands-On Exercises

**Exercise 1 — Check class-file version.** On JDK 21+, compile `CompatibilityBaselineDemo.java` with `--release 17`, run `javap -verbose`, and observe major 61. Run the artifact on an actual Java 17 if available.

**Exercise 2 — Reject source 21 on target 17.** Try `javac --release 17 CompatibilityPatternDemo.java`. Explain why the error is about syntax/features rather than missing imports. Recompile with `--release 21` and verify major 65.

**Exercise 3 — Boundary parity.** Add `Login("An", 2)`, `Login("An", 4)`, `Failure(499)`, and `Failure(500)` to both programs. Compare outputs. Change one implementation from `>=500` to `>500` to confirm boundary tests catch the divergence.

**Exercise 4 — Add a subtype.** Add `Locked(String user)` to `Event`. Compare the compile-time error in the Java 21 exhaustive switch with the runtime behavior of the Java 17 `if/else` if a case is forgotten. Fix both versions and expand tests.

**Exercise 5 — CI matrix.** Design jobs to build target 17, run runtime 17, run runtime 21, and build/test implementation 21. State which job verifies source, binary, API, and runtime compatibility.

**Exercise 6 — MR-JAR design.** Diagram a root class 17 and a versioned class 21 sharing the same FQCN. Explain why `Multi-Release: true` and API parity matter, as well as how to use `jar --validate` and runtime tests.

## 16. Summary

**A multi-JDK strategy is a strategy for source, bytecode, APIs, dependencies, and runtime—not just the `javac` version.** Java 17 already supports sealed hierarchies, records, and type patterns in `instanceof`; Java 21 standardizes record patterns, pattern `switch`, and `when` guards.

When runtime 17 must be supported, choosing a Java 17 source baseline with `--release 17` is usually the simplest option. When Java 21 features are needed, separate a Java 21 implementation, use an MR-JAR if a single shared artifact is genuinely required, or raise the minimum runtime if the product contract allows. In every case, test on the lowest committed JVM and guarantee behavior parity whenever multiple implementations exist.

No compiler flag can replace testing **the right artifact**, **the right dependencies**, and **the right JDK runtime**.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — `jar` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- OpenJDK JEP 238 — Multi-Release JAR Files: https://openjdk.org/jeps/238
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
