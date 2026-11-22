# Compiling with the Appropriate \`--release\` When Using Java Pattern Matching

## 1. The Problem: The JDK Installed on Your Machine Is Not the Java Version the Application Supports

Suppose a development machine runs JDK 24, while the application must run on Java 17. A developer writes:

```java
record Address(String city) {}
record Shipment(String id, Address destination) {}

static String describe(Object value) {
    return switch (value) {
        case Shipment(var id, Address(var city))
                when city != null -> "ship:" + id + ":" + city;
        default -> "other";
    };
}
```

This is a **non-standalone illustration snippet**: the declarations must be placed inside a valid class. It uses **record patterns**, **pattern matching for switch**, and the `when` guard—features finalized in Java 21. This code may be accepted by JDK 24 when compiling for Java 21+, but it **does not conform to the Java 17 contract**.

A common mistake is running `javac Shipment.java` with a newer JDK, seeing no compiler errors, and concluding that the `.class` file will work on Java 17. Without specifying a release, the compiler usually defaults to the running JDK's version, so it can emit newer bytecode and allow APIs/syntax that do not exist on the target platform.

The standard option to express **the Java SE version that the source code must be compatible with** is:

```bash
javac --release 17 -encoding UTF-8 Release17Demo.java
```

This command is not a way to "install Java 17" on the machine or a switch to change the running JVM; it instructs the **current compiler** to compile the code under the rules of Java SE 17 and check against the corresponding platform APIs.

**Lesson objectives:** choose `--release` based on the actual minimum runtime; identify which pattern matching features are permitted in Java 17/21; check new APIs; distinguish compile-time errors from runtime errors; and integrate release configuration into build/CI so code does not work only on the author's machine and fail upon deployment.

## 2. \`javac --release N\` Controls Three Things Simultaneously

The `javac` documentation describes `--release N` as covering three aspects:

| Aspect | With `--release 17` | Rejected example |
| --- | --- | --- |
| **Syntax and language rules** (*source*) | Accepts only Java 17 syntax and rules for the compiled source | `case Shipment(var id, Address(var city))`, `when` guard from Java 21 |
| **Class file version** (*target*) | Generates class files compatible with Java 17, major version **61** | Does not emit Java 21 class files (major **65**) from target 17 code |
| **Published Java SE/JDK APIs of the target release** (*platform API*) | Allows only APIs supported in Java 17 | `List.getFirst()`, added in Java 21 |

Summary:

```text
               Current JDK's javac
                        │
                  --release 17
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
      Source 17   Class file 17  Java API 17
           │            │            │
           └────────────┴────────────┘
                        │
             Project code conforms to
               the Java 17 contract
```

**Note:** `--release` applies to the source code being compiled and the platform APIs visible to the compiler. It **does not automatically downgrade the bytecode version of dependency JARs**, does not change the actual runtime on the server, and does not guarantee that all third-party libraries are Java 17-compatible.

In other words, `--release` is a **compile-time compatibility guardrail** that must be combined with testing on the target runtime and checking dependencies.

## 3. Choosing the Right Java Milestone for Each Pattern Matching Feature

Java capabilities were not released all at once. Therefore, you should not see the word "pattern" and assume any single version suffices.

| Feature | Finalized version | Example | Compiles with `--release 17` | Compiles with `--release 21` |
| --- | --- | --- | --- | --- |
| `instanceof` type pattern | **Java 16** (JEP 394) | `obj instanceof String text` | Yes | Yes |
| Record class | **Java 16** (JEP 395) | `record Point(int x, int y) {}` | Yes | Yes |
| Sealed classes/interfaces | **Java 17** (JEP 409) | `sealed interface Event permits A, B` | Yes | Yes |
| Switch expression (value-returning) | **Java 14** (JEP 361) | `return switch (state) { ... };` | Yes, if using only valid 17 cases | Yes |
| Record pattern (deconstruction) | **Java 21** (JEP 440) | `obj instanceof Point(var x, var y)` | No | Yes |
| Pattern matching for `switch` | **Java 21** (JEP 441) | `case String text -> ...` | Not as a final feature | Yes |
| `when` guard in pattern switch | **Java 21** (JEP 441) | `case String s when s.isBlank() -> ...` | No | Yes |
| `case null` in enhanced `switch` | **Java 21** (JEP 441) | `case null -> "missing"` | Not as a final feature | Yes |
| `SequencedCollection` / `List.getFirst()` | **Java 21** | `List.of("a").getFirst()` | No | Yes |

**Two important distinctions:**

1. **A record class does not imply record patterns.** Java 17 already lets you define `record Person(String name) {}`, but you cannot yet use `case Person(var name)` or `instanceof Person(var name)` as a final feature.
2. **A switch expression does not imply pattern switch.** Java 17 already has `return switch (enumValue) { case A -> ...; ... };`, but `case String text` inside a switch over `Object` is not valid final syntax with `--release 17` alone.

In Java 17, pattern matching for switch existed in **preview** form (JEP 406); record patterns were not yet a final feature. This **does not mean** that taking JDK 24 or JDK 21 and adding `--enable-preview --release 17` will recreate Java 17's preview feature set. See section 9 for details.

## 4. Complete Java 17-Compatible Example

The following example uses `instanceof` type patterns, `record`, `sealed`, and a switch expression over an enum—all finalized before or in Java 17. No record patterns or pattern switch are used.

Save verbatim to **`Release17Demo.java`**:

```java
public class Release17Demo {
    enum Stage { NEW, DONE }

    sealed interface Event permits Created, Cancelled {}

    record Created(String eventId) implements Event {}
    record Cancelled(String eventId, String reason) implements Event {}

    static String describe(Object event) {
        if (event instanceof Created created) {
            return "created:" + created.eventId();
        }
        if (event instanceof Cancelled cancelled) {
            return "cancelled:" + cancelled.eventId();
        }
        return "other";
    }

    static String stageName(Stage stage) {
        return switch (stage) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created("E-17")));
        System.out.println(describe(new Cancelled("E-18", "duplicate")));
        System.out.println(describe(null));
        System.out.println(stageName(Stage.DONE));
    }
}
```

Compile with a JDK that supports the Java 17 target (such as JDK 17 or a newer JDK that supports `--release 17`):

```bash
javac --release 17 -encoding UTF-8 Release17Demo.java
java Release17Demo
```

**Exact output:**

```text
created:E-17
cancelled:E-18
other
done
```

### Why is this example compatible with 17?

- `Created` and `Cancelled` are record classes — finalized in Java 16.
- `sealed interface Event permits ...` and its implementing sub-records — finalized in Java 17.
- `if (event instanceof Created created)` is a type pattern for `instanceof` — finalized in Java 16.
- `return switch (stage) { case NEW -> ...; ... };` is a switch expression using ordinary **enum constants** — finalized in Java 14.
- The code does not require `record deconstruction` or `case Type var` in a switch.

For `describe(null)`, both `instanceof` checks return `false`, so the result is `"other"`. This is the behavior of the `if` chain; you should not arbitrarily convert it to a pattern switch while overlooking the null-handling policy.

**Technical verification:** this snippet was executed with the compiler running in `--release 17` mode (via JShell), producing the exact four lines above. To prove it runs on a real Java 17 runtime, you must also run it with `java` from **JDK/JRE 17**, not just run the 17 class file on a newer JVM.

## 5. Complete Example Requiring Java 21: Record Patterns and Pattern Switch

When a project **has upgraded its minimum runtime to Java 21**, it can use more concise syntax to process data structures.

Save to **`Release21Demo.java`**:

```java
import java.util.List;

public class Release21Demo {
    record Address(String city) {}
    record Shipment(String shipmentId, Address destination) {}

    static String route(Object request) {
        return switch (request) {
            case null -> "missing";

            case Shipment(var shipmentId, Address(var city))
                    when city != null && !city.isBlank() ->
                    "ship:" + shipmentId + ":" + city.strip();

            case Shipment(var shipmentId, var destination) ->
                    "invalid:" + shipmentId;

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(null));
        System.out.println(route(
                new Shipment("S-1", new Address(" Ha Noi "))));
        System.out.println(route(new Shipment("S-2", null)));
        System.out.println(route(
                new Shipment("S-3", new Address("  "))));
        System.out.println(route(42));

        System.out.println(
                "first:" + List.of("alpha", "beta").getFirst());
    }
}
```

Compile:

```bash
javac --release 21 -encoding UTF-8 Release21Demo.java
java Release21Demo
```

**Exact output:**

```text
missing
ship:S-1:Ha Noi
invalid:S-2
invalid:S-3
unsupported
first:alpha
```

### There are two independent reasons this example requires Java 21

**Language reasons:**
- `Shipment(var shipmentId, Address(var city))` is a nested record pattern.
- `case ... when ...` is a guard in a pattern switch.
- `case null` handles a null selector.
- `case Shipment(var shipmentId, var destination)` after the guarded branch handles cases missing a valid address.

**API reason:** `List.getFirst()` belongs to the platform API introduced in Java 21, via ordered collections supporting the sequenced collections API. Even if you replaced the entire switch with old-style `if` statements, the `getFirst()` call still does not exist in the Java 17 API.

Thus, when "downgrading" an example to Java 17, you must check **both syntax and APIs**. Replacing `case` patterns with `instanceof` alone is not enough if standard library methods added in Java 21 are still being used.

The example also shows null at two different levels: `route(null)` enters `case null`, whereas `route(new Shipment("S-2", null))` is a non-null `Shipment` that fails to match the nested `Address(...)` pattern and falls through to the broader `Shipment` case.

**Technical verification:** the program was executed with the compiler in `--release 21` mode, producing all six lines of output shown above.

## 6. Lowering the Release to Test Compatibility: Which Errors Are Expected?

Try compiling `Release21Demo.java` with:

```bash
javac --release 17 -encoding UTF-8 Release21Demo.java
```

**Expected result: compilation fails.** The code uses constructs beyond the Java 17 language set; the compiler may report errors on `case Shipment(...)`, record patterns, or the `when` guard. The exact text, order, and wording of diagnostics can vary by `javac` version.

A minimal snippet intentionally designed not to compile under `--release 17`:

```java
class Java21PatternUnder17 {
    record Address(String city) {}
    record Shipment(String id, Address address) {}

    static String label(Object value) {
        return switch (value) {
            case Shipment(var id, Address(var city)) -> "ship:" + city;
            default -> "other";
        };
    }
}
```

With the JDK 24 compiler running in source 17 mode, checks show diagnostics such as:

```text
patterns in switch statements are not supported in -source 17
deconstruction patterns are not supported in -source 17
```

That is a **useful signal**: the build is rejecting syntax that violates the Java 17 contract instead of silently emitting incompatible bytecode.

If you want to stay on Java 17, **rewrite** the logic using `instanceof` type patterns, record accessors, and `if/else` chains. If you want to use pattern switch and record patterns, coordinate upgrading the **minimum runtime, build configuration, dependencies, and CI** to Java 21, and then choose `--release 21`.

Never "fix" the error by disabling release checks or compiling without a specified release just to make the build green.

## 7. API Errors: Code That Looks Like Java 17 Syntax but Still Uses Java 21 APIs

Consider a snippet that uses only ordinary class and method syntax:

```java
import java.util.List;

class Java21ApiUnder17 {
    static String first() {
        return List.of("alpha", "beta").getFirst();
    }
}
```

The command:

```bash
javac --release 17 -encoding UTF-8 Java21ApiUnder17.java
```

must fail because `java.util.List` in Java 17 does not yet have a `getFirst()` method. The message may look like:

```text
cannot find symbol
symbol: method getFirst()
```

Rewritten for Java 17:

```java
import java.util.List;

class Api17Compatible {
    static String first() {
        List<String> names = List.of("alpha", "beta");
        return names.get(0);
    }
}
```

`List.of(...)` has existed since Java 9 and `List.get(int)` has existed for a long time, so this works under `--release 17`. In practice, handle an empty `List` according to your own contract: both `get(0)` and `getFirst()` can throw an exception if there are no elements, and this is not a transformation that preserves all semantics of every `List` implementation under all conditions.

**Note for pattern matching:** many "downgrade" errors are mistakenly blamed on `case` or `instanceof`. A program may have already removed all new patterns and still fail because it calls a new API. Read the compiler error and distinguish an **unsupported language feature** from a **symbol/method unavailable in platform API**.

## 8. Why Doesn't \`-source 17 -target 17\` Fully Replace \`--release 17\`?

These two options are not equivalent.

```bash
javac -source 17 -target 17 SomeClass.java
```

- `-source 17` selects Java 17 source rules.
- `-target 17` selects the Java 17-compatible class file format.
- When using those two flags on a newer JDK, the compiler **does not automatically restrict the Java SE APIs** to Java 17; it can still see the APIs of the running JDK unless you also configure the corresponding platform classes.

Comparison (verified with JDK 24):

| Code containing `List.of("alpha", "beta").getFirst()` | With a newer JDK | Meaning |
| --- | --- | --- |
| `javac --release 17 ...` | **Rejected** | Java 17 API does not have `getFirst()` |
| `javac -source 17 -target 17 ...` | **May compile** | Java 17 syntax and class format, but APIs "leak" from the compiler's JDK |
| `javac --release 21 ...` | **Compiles** | `getFirst()` API is allowed in Java 21 |

If you run the class from the middle case on Java 17, calling `List.getFirst()` can lead to `NoSuchMethodError` when the runtime lacks the referenced method. This is a very hard bug to catch if you only test on a newer JDK on a development machine.

For the simple goal of "compiling for Java 17/21 compatibility," **prefer `--release`**. Configuring `-source/-target` with separate platform classes may be needed in special scenarios, but it is a more complex tooling problem and easy to misconfigure.

An **invalid** command:

```bash
javac --release 17 -source 17 Release17Demo.java
```

`--release` cannot be used together with `--source` or `--target`. Choose **one mechanism**, usually `--release`, to avoid conflicting configuration.

## 9. Preview Features and the Limits of \`--enable-preview\`

This is a common source of confusion in Pattern Matching lessons.

**Java 17** had *pattern matching for switch* in preview form, not yet as final syntax. **Java 21** finalized this feature (JEP 441), along with record patterns (JEP 440). There are semantic and syntactic differences between the preview versions and the final release.

If you are running JDK 24's `javac`, the command:

```bash
javac --release 17 --enable-preview MyClass.java
```

does not allow "re-enabling Java 17 preview." The Java compiler only supports **preview features of the currently running compiler version** when using `--enable-preview`; it does not resurrect the preview set of an older release. The compiler may report a message such as:

```text
invalid source release 17 with --enable-preview
(preview language features are only supported for release 24)
```

This is an example message observed in a JDK 24 environment; the release number in the diagnostic will depend on the compiler.

If you genuinely need to study Java 17 preview features, you must use a **JDK 17** toolchain and **Java 17's own** preview compile/runtime configuration; however, you should not put old preview code into projects that require long-term compatibility. For new projects that want stable pattern switch/record patterns, the clearer choice is **Java 21+ with `--release 21`**, which does not need `--enable-preview` for these two features.

**Key takeaway:** `--release` selects a **supported compatibility level**. It is not a switch to enable every syntax that may have ever appeared in historical preview JEPs.

## 10. Checking the Toolchain and Class Files Before Concluding a Build Is Correct

### 10.1. Check which JDK is actually invoked

```bash
java -version
javac -version
javac --help
```

Cross-check:
- Which JVM does `java` run the application with?
- Which compiler does `javac` compile with?
- Which versions does the current compiler support for `--release`?

`javac` only supports the current release and **a number of older releases**; there is no guarantee that every JDK supports arbitrary version numbers. For example, Java 17's `javac` cannot compile for Java 21 simply by passing `--release 21`. When you need to target Java 21, you must have a compiler new enough to support release 21.

In environments with multiple JDKs, `java` and `javac` on `PATH` may differ. CI may also use a different JDK than your personal terminal. Check the compiler that your build tool actually selects as well.

### 10.2. Check the bytecode version

After compiling to an actual class file, run:

```bash
javap -verbose Release17Demo | grep "major version"
```

On Windows PowerShell, you can use:

```powershell
javap -verbose Release17Demo | Select-String "major version"
```

Common values:

| Java target | Class-file major version |
| --- | --- |
| 17 | **61** |
| 21 | **65** |
| 24 | **68** |

A handy formula for class-file versions of modern releases is `major = release + 44`. This is a quick check of the **bytecode format**; it does not check whether dependencies or third-party APIs are compatible.

When a Java 21 class file (major 65) is loaded by Java 17 (which supports up to major 61), the runtime typically throws **`UnsupportedClassVersionError`**. That is a very different symptom from a compile-time `cannot find symbol` error or a `NoSuchMethodError` when calling a nonexistent API.

## 11. Building with Maven: Configure Release in One Place

Example for a project requiring Java 17, with the Maven Compiler Plugin configured using the release property:

```xml
<project>
    <!-- The project's groupId/artifactId/version elements are declared separately. -->
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
</project>
```

This is a **configuration illustration snippet**, not a complete `pom.xml`; place the `properties` block inside a valid POM appropriate for your project's Maven/compiler-plugin version.

If the baseline moves to Java 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Reference commands:

```bash
mvn --version
mvn clean test
```

`mvn --version` shows the Java runtime that Maven is currently using. However, a project may configure Maven Toolchains so that the compiler is chosen from a different JDK; check the actual POM/toolchain rather than looking only at the Maven process's Java.

Important: setting release 17 in the POM **does not mean tests ran on Java 17**. A pipeline that uses JDK 21 to build with `--release 17` and then runs all unit tests on JDK 21 still has not proven that the program runs correctly under JDK 17. You should have a test job running on an actual JVM 17 if that is the minimum supported environment.

## 12. Building with Gradle: Separating the Compiler JDK from the Target Release

Gradle Groovy DSL example allowing a Java 21 compiler toolchain while requiring the production code to be Java 17-compatible:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
```

This is an illustrative `build.gradle` configuration snippet for a Java project; it is not `build.gradle.kts` (Kotlin DSL). Use a Gradle version and JDK toolchain supported by your project's documentation.

- `java.toolchain.languageVersion = 21` selects an appropriate compiler/JDK for Java tasks.
- `options.release = 17` instructs the compiler to generate code according to Java 17 language rules, bytecode, and APIs.
- These two settings answer **two different questions**: "Which compiler do we use?" and "Which Java version does the artifact support?"

If the product target is Java 21, change `options.release = 21` and test on a Java 21 runtime. If a project has different source sets/modules (for example, one Java 17 module and one Java 21 module), configure the release per module rather than setting a project-wide default and assuming all artifacts are the same.

Reference commands:

```bash
./gradlew --version
./gradlew clean test
```

In Windows PowerShell, you can use `.\gradlew.bat --version` and `.\gradlew.bat clean test`. As with Maven, do not forget that the test JVM may differ from the compiler JVM.

## 13. Process for Choosing \`--release\` per Project

### Step 1 — Identify the real baseline

Ask: **what is the lowest Java version that the artifact must run on?**

- If the service deploys on Java 17 and has not been upgraded: target Java **17**.
- If all runtimes are Java 21 or higher and dependencies support it: you can target **21**.
- If a library must serve both Java 17 and Java 21 applications: the shared library API should generally **be compiled for Java 17**, unless there is a clear multi-version distribution strategy.

Do not choose a release based on "the newest JDK on my laptop" or the syntax you want to use. Choose based on the **deployment and support contract**.

### Step 2 — Inventory the features in use

For example, if a module has:
- `record` and `sealed`: 17-compatible.
- `obj instanceof Type variable`: 17-compatible.
- `switch (obj) { case Type x -> ... }`: requires 21 for the final feature.
- `record Type(var x, var y)`: requires 21.
- `List.getFirst()`: 21 API.

If even a single feature requires 21, you cannot claim the entire module is 17-compatible merely by changing the class-file target. You must either rewrite the feature or raise the baseline.

### Step 3 — Use a compiler that supports the target

Run `javac -version` and `javac --help`. Choose a JDK version new enough to support the target release; a compiler older than the target release cannot know future syntax or APIs.

### Step 4 — Compile with a fixed release

```bash
javac --release 17 -encoding UTF-8 -d out17 Release17Demo.java
```

Or:

```bash
javac --release 21 -encoding UTF-8 -d out21 Release21Demo.java
```

The two commands above create the output directory if needed and write class files when **learners run them in their own environment**; the file name must match the public class in each example. Using separate output directories avoids accidentally picking up stale class files compiled with a different release.

### Step 5 — Run on the minimum JVM

To verify target 17, use an **actual Java 17** `java` executable, not just a newer JDK:

```bash
java -cp out17 Release17Demo
```

To verify target 21, run with Java 21:

```bash
java -cp out21 Release21Demo
```

Running the program on Java 24 does not prove it will run properly on Java 17, even if the class file's major version has been lowered.

### Step 6 — Repeat in CI

CI should enforce at least two independent gates:

1. **Build/compile gate:** code does not use syntax or APIs beyond the baseline; e.g., `--release 17`.
2. **Runtime gate:** run tests/integration on the minimum JVM 17, while optionally testing on newer JVMs as well if the project commits to supporting them.

If Java 21 artifacts are not permitted in a target-17 module, a `javac --release 17` command will block them directly before release.

## 14. Common Errors and How to Identify Them

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` | Using Java 21 pattern switch under release 17 | Language features and baseline |
| `deconstruction patterns ... not supported in -source 17` | Record patterns are not supported in Java 17 final | Replace with accessors/type pattern or raise release |
| `cannot find symbol: getFirst()` | `List.getFirst()` API does not exist in Java 17 | API version and `--release` |
| `invalid target release: 21` or `release version 21 not supported` | Compiler is too old to target 21 | `javac -version`, `javac --help` |
| `UnsupportedClassVersionError` | Runtime is too old for the class-file version | Major version of class/dependency and `java -version` |
| `NoSuchMethodError` when calling an API | Code references a method missing at runtime or mismatched version | Use `--release`, check classpath and libraries |
| `invalid source release 17 with --enable-preview` | Trying to use an old preview via a newer compiler | Use a stable baseline or the matching preview toolchain |
| `--release cannot be used with --source/--target` | Mixing two release-selection mechanisms | Use only one mechanism |
| Works on author's machine, fails in CI | Different JDK/Gradle/Maven toolchain or dependencies | Print versions and run tests on the target JVM |
| Java 17 code still fails to compile at target 17 | Using a new API or hidden Java 21 syntax in the module | Distinguish language errors from API errors |

**Reading the exact message matters more than guessing.** Message formats depend on the `javac` version. Do not treat a specific error wording as an invariant interface guaranteed across all JDKs.

## 15. Limitations of \`--release\`: Real Testing Is Still Needed Even If Compilation Passes

`--release 17` is a strong guardrail, not a promise that **everything** will run on a machine with only Java 17.

### 15.1. Third-party dependencies

If a target-17 module depends on a JAR compiled with Java 21 (class major 65), compiling your own code with `--release 17` alone does not convert the classes in that JAR to major 61. The compiler may report a class-version error when reading the dependency; if the dependency is only loaded at runtime, it can fail at runtime. You must check the compatibility and class versions of dependencies.

### 15.2. APIs not checked statically

Reflection such as `Class.forName(...)`, `Method.invoke(...)`, loading classes by string name, dynamically generated code, or service loaders can depend on APIs not checked by the compiler at the call site. Testing on the minimum runtime remains necessary.

### 15.3. Annotation processors and code generation

Processors or build plugins can run on the compiler's JDK and generate code containing new APIs or syntax. Apply the release setting to every actual compilation step and inspect generator output rather than assuming a single flag in one module protects the whole project.

### 15.4. Native libraries, OS, runtime flags, and configuration

Class-file/API compatibility does not guarantee identical native libraries, environment variables, module access, TLS, charsets, operating systems, or JVM configuration. CI/integration tests on the target environment are an essential part of the deployment contract.

### 15.5. Binary compatibility when updating libraries

`NoSuchMethodError` can also occur when the runtime library version differs from the library version used at compile time, even when all classes belong to the same Java release. Do not assume every `NoSuchMethodError` is caused by a wrong `--release`.

### 15.6. Multi-release JARs and modules

Projects that intentionally ship multiple class variants for multiple JDKs may use multi-release JARs or complex module configurations. This is a specialized distribution design that requires testing each variant; do not mistakenly assume a single `javac --release 17` invocation will automatically produce a multi-version artifact.

## 16. Review Checklist Before Merging or Releasing

- [ ] Is there documentation stating the **minimum supported Java runtime**?
- [ ] Does `--release` match the minimum runtime?
- [ ] Does the JDK compiler in use **support** that release?
- [ ] Does any pattern matching in the code require Java 21? `instanceof` type patterns differ from record patterns and pattern switch.
- [ ] Are platform APIs restricted to the right version? Are `List.getFirst()` or similar new APIs used?
- [ ] Are `--release` and `-source`/`-target` not mixed in the same compilation task?
- [ ] Are old previews not being used by enabling `--enable-preview` on a newer JDK?
- [ ] Does source code consistently use `UTF-8` if it contains non-ASCII characters (e.g., Vietnamese diacritics)?
- [ ] Has the class-file major version been verified to match the target?
- [ ] Are dependencies built for a compatible Java version?
- [ ] Have unit/integration tests been run on the **actual minimum JVM**?
- [ ] Do IDE, Maven, Gradle, and CI builds share the same target release?
- [ ] Are output directories separated to avoid stale class files from another release?
- [ ] If raising the baseline from 17 to 21, have the compiler, runtime, Docker image, CI, and release documentation all been updated?

A baseline can change over time, but **every related place must change together**. Treat raising `--release` as a product/infrastructure decision, not a quick way to silence compiler errors.

## 17. Self-Study Exercises with Answers

**Exercise 1 — Choosing a release.** A service uses JDK 24 to build, while production is still on Java 17. The project uses `instanceof` type patterns and `record`, with no Java 21 syntax. Which release should be used?

**Answer:** `--release 17`. JDK 24 can compile for Java 17 if it supports this target; tests must still be run on an actual JVM 17.

**Exercise 2 — Record patterns.** Why is `if (candidate instanceof Point(var x, var y))` rejected under `--release 17` even though `record Point(int x, int y) {}` compiles?

**Answer:** Record classes were finalized in Java 16, whereas **deconstruction record patterns** were finalized in Java 21. For 17 compatibility, use the type pattern `instanceof Point point` and call `point.x()`, `point.y()`.

**Exercise 3 — Two independent errors.** A snippet has `case String s when s.isBlank()` and `List.of("a").getFirst()`. Under `--release 17`, can you fix only the `case` and get it to build?

**Answer:** No. Guarded pattern switch requires Java 21; `List.getFirst()` is also a Java 21 API. You must replace both the syntax and the API, or raise the baseline to Java 21.

**Exercise 4 — Source/target.** Why can `-source 17 -target 17` on JDK 24 still compile a call to `List.getFirst()`, whereas `--release 17` does not?

**Answer:** `source/target` restrict syntax and class format, without automatically locking the platform API to Java 17. `--release` restricts all three aspects.

**Exercise 5 — Class files.** Which Java target corresponds to major version 65? Can Java 17 load that class?

**Answer:** Java 21. A Java 17 runtime typically throws `UnsupportedClassVersionError` when attempting to load a major 65 class.

**Exercise 6 — Preview.** When running `javac` 24, is enabling `--enable-preview --release 17` valid for using Java 17's preview patterns?

**Answer:** No. Preview can only be enabled for the current compiler's release, not to replay historical previews. For the final features, use Java 21+ and `--release 21`.

**Exercise 7 — Maven/Gradle.** A project uses a JDK 21 compiler but must support a Java 17 runtime. Is it necessary to switch the compiler back to JDK 17 to use `--release 17`?

**Answer:** Not necessarily. A JDK 21 compiler can target 17. However, you must **check dependencies** and run tests on an actual JVM 17; the compiler toolchain and the target runtime are two separate concerns.

**Exercise 8 — Library dependency.** Your code is built with `--release 17`, but a dependency contains a major 65 class. Is Java 17 production guaranteed to work?

**Answer:** No. `--release` does not transform dependency bytecode into Java 17 bytecode. You must choose a compatible dependency or adjust the baseline.

**Exercise 9 — Runtime.** You compile with `--release 17` and test only on JDK 24; can this be considered verified to run properly on JDK 17?

**Answer:** Not yet. Run the artifact on an actual JVM 17 in CI/test deployment to catch runtime, dependency, reflection, and configuration differences.

**Exercise 10 — Upgrading versions.** When a team decides to move from Java 17 to Java 21 to use record patterns, what must change besides the compiler flag?

**Answer:** Production runtime, a build JDK supporting 21, Maven/Gradle configuration, container/images, dependencies, CI toolchain, and compatibility test suites. Raising `--release` on a developer machine alone is not enough.

## 18. Key Takeaways

- **`javac --release N` selects the language rules, class-file target, and Java SE/JDK APIs of release N all at once.**
- With **Java 17**, you can use `instanceof` type patterns, record classes, sealed hierarchies, and switch expressions with ordinary cases, but **not** finalized Java 21 record patterns or pattern switch.
- With **Java 21**, you can use record patterns, pattern matching for switch, `when` guards, and new APIs such as `List.getFirst()`.
- **`-source/-target` is not a safe substitute for `--release`** when you need to restrict APIs to an older JDK.
- **Preview features are tied to the compiler version**; you cannot use a newer compiler to "re-enable" historical Java 17 previews.
- **The compiler JDK differs from the minimum runtime**; a passing build on a newer JDK does not prove it runs on an older runtime.
- **`--release` does not automatically guarantee compatibility of dependencies, reflection, configuration, and environment**; always test on the actual minimum JVM.
- Lock in the release according to the project's support contract and keep it consistent across the IDE, Maven/Gradle, and CI.

**Official references:**
- [Oracle JDK 21 — The javac Command, option --release](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Java 21 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
