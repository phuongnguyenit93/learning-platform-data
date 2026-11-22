# Version Compatibility Checklist for Java Pattern Matching

## 1. Why check version compatibility before using pattern matching?

A piece of Java code may compile on the author's machine but fail to compile in CI, fail to run in Docker, or fail to be loaded onto an older JVM by a library consumer. With pattern matching, the cause is often **confusing different Java milestones**:

- `switch expression` using the `->` arrow was standardized before Java 21.
- `instanceof String s` and `record Point(...)` both became final in Java 16.
- Sealed classes/interfaces became final in Java 17, but **pattern matching for switch was not yet final in Java 17**.
- `case Point(var x, var y)`, the `when` guard, and nested record patterns were standardized in **Java 21**.
- The `_` syntax for unnamed patterns was standardized after Java 21; simply using JDK 21 does not mean every pattern form is allowed.

Therefore, to evaluate "version compatibility," you must check **source syntax, preview/final features, compiler JDK, release target, class-file version, standard library, dependencies, build tool, test runner, and the actual deployment JVM**. A single run on a laptop is not proof that the product is compatible with the published baseline.

This article is a practical checklist for the **Java Core Pattern Matching** module: determining the minimum Java milestone, choosing between Java 17 and Java 21, using `javac --release`, checking null/guard/dominance, running two programs that produce the same output, configuring Maven/Gradle/CI, and avoiding migration pitfalls.

**Convention:** The version numbers in the table are the **final** milestones of the features. This article does not claim which JDK is the latest version at any given time. When preparing a real release, always check the JDK vendor's support policy and the specific deployment environment.

## 2. Official Feature Milestone Table

| Feature | Illustrative Syntax | First Final JDK | JEP |
| --- | --- | --- | --- |
| Switch expression | `int n = switch (day) { case MONDAY -> 1; default -> 0; };` | **Java 14** | JEP 361 |
| Pattern matching for `instanceof` | `obj instanceof String s` | **Java 16** | JEP 394 |
| Record classes | `record Point(int x, int y) {}` | **Java 16** | JEP 395 |
| Sealed classes and interfaces | `sealed interface Shape permits Circle {}` | **Java 17** | JEP 409 |
| Pattern matching for `switch` | `case String s -> ...` | **Java 21** | JEP 441 |
| `when` guard in pattern switch | `case String s when s.isBlank() -> ...` | **Java 21** | JEP 441 |
| Record patterns | `Point(var x, var y)` | **Java 21** | JEP 440 |
| Nested record patterns | `Box(Point(var x, var y))` | **Java 21** | JEP 440 |
| Unnamed variables and unnamed patterns | Pattern using `_` | **Java 22** | JEP 456 |

Three pairs that are very easily confused:
1. **A switch expression is not a pattern switch.** Java 14 supports computing a value from a switch with compatible enum/int/String types, but does not finally support `case Circle c` in a switch.
2. **A record is not a record pattern.** Java 16 allows declaring and using `record Point(int x, int y)`, but `Point(var x, var y)` requires final Java 21.
3. **Sealed is not a guarded switch.** Java 17 allows `sealed interface`, but `case Type t when ...` is final Java 21 syntax.

**`--enable-preview` is not needed** to use any feature in the table **when building on the right final version or newer that supports it**, noting that Java 21 does not support unnamed patterns finalized in Java 22. Do not force preview flags into production builds when a feature is already stable.

### Minimal examples by baseline

**Java 16 and later — `instanceof` pattern:**

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

**Java 17 and later — sealed model:**

```java
sealed interface Result permits Success, Failure {}
record Success(String message) implements Result {}
record Failure(String reason) implements Result {}
```

**Java 21 and later — switch with guard:**

```java
String label = switch (value) {
    case null -> "null";
    case String text when text.isBlank() -> "blank";
    case String text -> "text";
    default -> "other";
};
```

In the Java 21 example, the guarded branch `String text when ...` must precede the general String branch so it is not dominated. `case null` is an explicit decision about a null selector, not relying on `default`.

## 3. Preview history does not mean default support

Pattern matching for switch went through multiple preview stages:

| JDK | JEP | Status |
| --- | --- | --- |
| Java 17 | 406 | First Preview |
| Java 18 | 420 | Second Preview |
| Java 19 | 427 | Third Preview |
| Java 20 | 433 | Fourth Preview |
| Java 21 | 441 | Final |

Record patterns:
- Java 19: JEP 405 — preview;
- Java 20: JEP 432 — second preview;
- Java 21: JEP 440 — final.

**Consequence:** an example using record patterns labeled "Java 19" may require `--enable-preview` on JDK 19 and syntax/semantics matching that preview version. Do not assume that code works by default on JDK 19, or that it can be copied verbatim to Java 21 without checking.

Guard syntax is an important example. With **final Java 21**, the form to remember is:

```java
case String s when s.length() >= 3 -> "long";
```

Do not take guard usage instructions verbatim from an old preview release and apply them to Java 21 just because they share the topic of pattern matching.

### When to use `--enable-preview`?

Only when the project **actively uses a feature currently in preview in the active JDK version**. In that case, you typically need to synchronize compile, test, and runtime flags, while accepting the risk of the feature changing between releases.

Example command structure for **an actual preview feature belonging to JDK 21**:

```bash
javac --enable-preview --release 21 PreviewExample.java
java --enable-preview PreviewExample
```

This is a **flag illustration pattern**, not a standalone runnable program, and **does not need to be applied** to final record patterns or pattern switch in Java 21. It also does not allow the Java 21 compiler to compile preview syntax from an arbitrary other JDK version.

Preview code may need updates when upgrading the JDK; a class file containing a preview feature should not be treated as an artifact with unlimited compatibility across all future JVMs. For widely used libraries, final features are usually the safer choice.

## 4. Five compatibility layers to verify

You can view the path of the code as follows:

```text
Java source: syntax, patterns, guards
          |
          v
Compiler JDK and --release
          |
          v
Class files + Java SE platform APIs
          |
          v
Libraries, plugins, processors, frameworks
          |
          v
CI test runner + deployment JVM/Docker/server
```

**Source:** If the code contains `case T(var x)`, targeting Java 17 will not accept final Java 21 syntax. Having JDK 21 installed as the compiler does not make this syntax "Java 17 compatible."

**Compiler:** `javac --release 21` can only be used with a JDK compiler that understands release 21. JDK 17 cannot produce target 21 class files with a different flag.

**Class files:** Code targeting Java 17 has major class-file version **61**; targeting Java 21 has **65**. JVM 17 cannot directly run class file 65 and typically throws `UnsupportedClassVersionError`.

**Platform APIs:** A program using Java 17 syntax can still call a standard API added in a newer Java version if the compiler does not properly lock the target's APIs. `--release` helps catch this kind of mistake during the build.

**Dependencies/runtime:** Older frameworks or bytecode instrumentation that do not yet support class version 65 may fail even though the source compiled. The Docker runtime might be JVM 17 even if the build stage is JDK 21. You must test the artifact in the exact environment where it will run.

**In summary:** Source compatibility does not equal bytecode compatibility; bytecode compatibility does not automatically guarantee standard library/dependency compatibility; and none of the three replaces real runtime verification.

## 5. Choosing the Java baseline from product requirements

The first decision is **the lowest JVM that the artifact must support**.

| Requirement | Baseline to consider | Impact on pattern matching |
| --- | --- | --- |
| Application must run on Java 17 without preview | `--release 17` | Use `instanceof` patterns, records, sealed types, and switch expressions as supported |
| Application runs on Java 21+ | `--release 21` | Can use pattern switch, nested record patterns, `when` guards |
| Library must be usable by Java 17 clients | Build Java 17 artifact | Do not put target 21 classes on a JVM 17 execution path |
| Application needs final Java 22 features | Target at least 22 | Do not advertise the artifact as Java 21-compatible if using newer syntax/APIs |
| Experimenting with preview | Lock exact JDK + flags + tests | Do not implicitly treat preview as a stable contract |

You **cannot** use JDK 21 to compile Java 21 syntax into a Java 17 artifact simply by setting `-target 17`. If you use `--release 17`, the compiler will reject syntax not belonging to Java 17, which is its exact purpose.

If there are both Java 17 and Java 21 modules in a monorepo, they can use different toolchains. However, a module running on Java 17 cannot have a required dependency on class version 65 if it must load that class on JVM 17.

### Java 17 LTS or Java 21 LTS?

Both are common LTS milestones in the Java ecosystem, but the project must also consider **vendor policy, dependencies, deployment costs, and end users**. "LTS" does not mean every piece of software supports every feature or that verification is unnecessary.

Once you decide to raise the baseline from 17 to 21, document it clearly in the README, release notes, and packaging/runtime docs. For a public library, changing the minimum Java version is a major compatibility change for consumers still running JVM 17.

## 6. `javac --release` instead of just `-source` and `-target`

Java 17 compatibility command:

```bash
javac --release 17 -encoding UTF-8 Java17FallbackDemo.java
```

`--release 17` controls **the source language rules, class-file target, and Java SE APIs of release 17** supported by the compiler. This is the right choice when a library needs to run on Java 17.

Writing only:

```bash
javac -source 17 -target 17 Java17FallbackDemo.java
```

does not provide the same guarantee for platform APIs: if running the compiler on a newer JDK without properly restricting the standard library, code can still accidentally call a newer Java SE method and then fail on JVM 17.

**Limitation:** `--release` does not check all third-party libraries, reflection, service loaders, native code, annotation processors, or runtime configuration. You still need to test on the actual lowest JVM.

### Three pieces of information needed when investigating a build

```bash
java -version
javac -version
```

Along with the actual release flag, confirm:
- Which path `java` is running from;
- Which compiler `javac` is;
- Whether the build tool uses a different toolchain or forked compiler;
- Whether the JAR execution environment has the same minimum Java requirement.

For example, "IDE shows Project SDK 21" does not prove Maven in CI is using compiler 21, nor does it prove the Docker runtime is >= 21.

## 7. Program A: Java 17 compatible without preview

We design a command set: create order, cancel order, and ship order. Data is declared with `record`, and the set of variants with `sealed interface`. Because the target is 17, dispatching uses **`instanceof` type patterns**.

Create the file **`Java17FallbackDemo.java`**:

```java
public class Java17FallbackDemo {

    sealed interface Action permits Create, Cancel, Ship {}

    record Address(String city) {}

    record Create(String id, int quantity) implements Action {}

    record Cancel(String id) implements Action {}

    record Ship(String id, Address address) implements Action {}

    static String describe(Action action) {
        if (action == null) {
            return "NULL";
        }

        if (action instanceof Create created) {
            if (created.quantity() <= 0) {
                return "INVALID_CREATE:" + created.id();
            }
            return "CREATE:" + created.id();
        }

        if (action instanceof Cancel cancelled) {
            return "CANCEL:" + cancelled.id();
        }

        if (action instanceof Ship shipment) {
            Address address = shipment.address();
            if (address != null
                    && address.city() != null
                    && !address.city().isBlank()) {
                return "SHIP:" + shipment.id()
                    + "@" + address.city();
            }
            return "SHIP_WITHOUT_CITY:" + shipment.id();
        }

        throw new IllegalStateException(
            "Unsupported action: " + action.getClass());
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("O-1", 2)));
        System.out.println(describe(new Create("O-2", 0)));
        System.out.println(describe(new Cancel("O-3")));
        System.out.println(
            describe(new Ship("O-4", new Address("Huế"))));
        System.out.println(describe(new Ship("O-5", null)));
        System.out.println(
            describe(new Ship("O-6", new Address(null))));
        System.out.println(describe(null));
    }
}
```

Compile with **JDK 17 or a newer compiler supporting `--release 17`**:

```bash
javac --release 17 -encoding UTF-8 Java17FallbackDemo.java
java Java17FallbackDemo
```

**Expected output:**

```text
CREATE:O-1
INVALID_CREATE:O-2
CANCEL:O-3
SHIP:O-4@Huế
SHIP_WITHOUT_CITY:O-5
SHIP_WITHOUT_CITY:O-6
NULL
```

Why it is Java 17 compatible:
- `sealed interface` was finalized in 17;
- `record` and `instanceof` patterns were finalized in 16;
- Does not use record patterns or pattern switch;
- Null selector is handled with an explicit `if`.

This is **compatibility demonstration code**, not a fully validated domain model. `Ship(null)` and `Address(null)` are allowed in order to test two different null states. In a real domain, the constructor might forbid them and the API boundary would handle invalid input before creating the object.

**Limitation:** The `if/instanceof` chain ends with a runtime fallback. When adding a new permitted subtype, the compiler does not automatically force adding a branch in this `if` logic. Tests and code review must ensure no subtype is missed.

## 8. Program B: Java 21 with record patterns, `switch`, and `when`

Using the same model and producing the same result, Java 21 allows expressing branch selection directly with a `switch expression`.

Create the file **`Java21PatternCompatibilityDemo.java`**:

```java
public class Java21PatternCompatibilityDemo {

    sealed interface Action permits Create, Cancel, Ship {}

    record Address(String city) {}

    record Create(String id, int quantity) implements Action {}

    record Cancel(String id) implements Action {}

    record Ship(String id, Address address) implements Action {}

    static String describe(Action action) {
        return switch (action) {
            case null -> "NULL";

            case Create(var id, var quantity)
                    when quantity <= 0 ->
                "INVALID_CREATE:" + id;

            case Create(var id, var quantity) ->
                "CREATE:" + id;

            case Cancel(var id) ->
                "CANCEL:" + id;

            case Ship(var id, Address(var city))
                    when city != null && !city.isBlank() ->
                "SHIP:" + id + "@" + city;

            case Ship(var id, var address) ->
                "SHIP_WITHOUT_CITY:" + id;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("O-1", 2)));
        System.out.println(describe(new Create("O-2", 0)));
        System.out.println(describe(new Cancel("O-3")));
        System.out.println(
            describe(new Ship("O-4", new Address("Huế"))));
        System.out.println(describe(new Ship("O-5", null)));
        System.out.println(
            describe(new Ship("O-6", new Address(null))));
        System.out.println(describe(null));
    }
}
```

Compile with **JDK 21 or later supporting target 21**:

```bash
javac --release 21 -encoding UTF-8 Java21PatternCompatibilityDemo.java
java Java21PatternCompatibilityDemo
```

**Expected output — identical to the Java 17 program:**

```text
CREATE:O-1
INVALID_CREATE:O-2
CANCEL:O-3
SHIP:O-4@Huế
SHIP_WITHOUT_CITY:O-5
SHIP_WITHOUT_CITY:O-6
NULL
```

### Java 21 features being used

- `case Create(var id, var quantity)` and `case Ship(var id, Address(var city))`: record patterns.
- `case ... when ...`: guarded patterns.
- `case null`: explicit null selector policy.
- `return switch (action) { ... };`: switch expression combined with patterns.
- `Action` is a sealed hierarchy and the non-null branches cover all subtypes, so the switch is exhaustive and does not need `default`.

**`--enable-preview` is not needed** because the above features are final in Java 21.

### Why does case order matter?

`case Create(...) when quantity <= 0` must come before the unguarded `case Create(...)`. If reversed, the general branch already covers every `Create`, so the specialized branch after it is **dominated** and the compiler may report an error.

Similarly, `case Ship(var id, Address(var city)) when ...` needs to precede `case Ship(var id, var address)`. The general `Ship` branch serves as a fallback for values that do not satisfy the priority condition.

### Null in a nested record vs. guard false

- For `new Ship("O-5", null)`: the nested record pattern `Address(var city)` **does not match**, because `address` is null. The guard is not evaluated; the general `Ship` branch is selected.
- For `new Ship("O-6", new Address(null))`: the nested pattern **matches** `Address`, and the `city` variable can receive null. The guard `city != null` evaluates to false; the general `Ship` branch is selected.

Two different paths yield the same output. When migrating from Java 17 to 21, you must test both **pattern fail** and **guard false**, not just a single missing-address case.

### Exhaustive switch when adding a subtype

If you add `record Refund(String id) implements Action` and update `permits`, the current switch expression may no longer be exhaustive. The compiler forces you to consider adding a `Refund` branch. This is an advantage over a hand-written `if/instanceof` chain, where a missing branch might only be discovered at runtime.

Do not add `default -> "UNKNOWN"` just to silence the compiler if business logic requires handling the new subtype explicitly.

## 9. Comparing behavioral compatibility before and after refactoring

Identical console output does not prove complete business-logic equivalence. When migrating, use a test suite with assertions:

| Data | Java 17 | Java 21 | What to verify |
| --- | --- | --- | --- |
| Create quantity 2 | `instanceof Create` | `case Create` | `CREATE:O-1` |
| Create quantity 0 | `if quantity<=0` | `when quantity<=0` | `INVALID_CREATE:O-2` |
| Cancel | `instanceof Cancel` | `case Cancel` | `CANCEL:O-3` |
| Ship with city | Accessor + null checks | Nested pattern + guard | `SHIP:O-4@Huế` |
| Ship address null | `address != null` false | Nested pattern fail | Fallback |
| Ship city null | `city != null` false | Guard false | Fallback |
| Selector null | `if action==null` | `case null` | `NULL` |
| Added subtype | Runtime fallback | Compile exhaustiveness | New business branch |

If a method has side effects, you must also check repository/audit call ordering, exceptions, transactions, and idempotency. Syntax refactoring does not exempt you from preserving behavior.

Record patterns also access components via accessors. For custom accessors with side effects or high cost, deconstruction can affect performance or exception timing. Keep accessors stable and adhere to the contract; test exceptions and specialized guard branches.

## 10. Self-checking release errors with the compiler

### A. Trying to build Java 21 source as Java 17

When JDK 21+ is available, run:

```bash
javac --release 17 -encoding UTF-8 Java21PatternCompatibilityDemo.java
```

**Expected result: compilation fails**, because the source uses Java 21 pattern switch/record patterns that are not part of standard Java 17. The specific diagnostic depends on the compiler; there is no need to predict the exact wording of every error message.

Do not "fix" the error by removing `--release 17` if the product still commits to running on Java 17. You must use Java 17-compatible syntax like Program A or **officially raise the minimum supported JDK**.

### B. JDK 17 does not have a target 21 compiler

If the `javac` command actually comes from JDK 17:

```bash
javac --release 21 Java21PatternCompatibilityDemo.java
```

the compiler does not support release 21. To use source target 21, you must select an appropriate JDK 21+.

### C. Running target 21 classes on JVM 17

Target 21 classes have major version 65; JVM 17 only supports up to major version 61. When loading the new class, `UnsupportedClassVersionError` is typically thrown. Lowering the runtime target is only feasible through appropriate build/source structure, not by renaming the JAR file.

### D. APIs can be wrong even with old syntax

Java 17 syntax does not prevent accidentally using a Java SE API that only exists in a later version if the build uses a newer JDK compiler and does not restrict platform APIs. `--release 17` helps prevent this mistake. However, third-party dependencies must still be tested separately.

## 11. Maven Configuration

In the project's `pom.xml` using a compatible Maven Compiler Plugin:

**Build targeting Java 17 only:**

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

**Build targeting Java 21 only:**

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Choose **one configuration** per artifact, or configure intentionally per module. Do not put Java 21 syntax in a target 17 module and expect the Maven Compiler Plugin to automatically convert it.

Verify:

```bash
mvn -version
mvn -q test
```

`mvn -version` shows the JVM running Maven. If the project uses toolchains or a forked compiler, the actual compiler may differ; check the logs and effective plugin configuration. Test plugins and annotation processors must also support the chosen bytecode/runtime.

If actually using preview features, the compiler, test runner, and runtime must have corresponding flags. **Do not add preview flags to Java 21 just to use finalized record patterns.**

## 12. Gradle Configuration and Java Toolchains

Gradle **Groovy DSL** example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

The toolchain selects the appropriate Java compiler as supported by Gradle; `options.release` constrains the source/class/Java SE API target. If targeting Java 17, change both release and toolchain to 17, **and at the same time** update the source so it does not use Java 21 patterns.

Verify:

```bash
./gradlew --version
./gradlew test
```

On Windows you can use `gradlew.bat`, depending on the shell. Use the project's Gradle Wrapper to prevent a team member from accidentally building with a Gradle version incompatible with a newer JDK. Distinguish between the JVM running the daemon and the toolchain used for compile/test.

**Do not assume that any given build tool supports every new JDK**: check the Gradle version, compiler plugins, code generation, annotation processors, and test framework in the actual system.

## 13. IDE, CI, container, and dependency compatibility

| Place | Check | Sign of mismatch |
| --- | --- | --- |
| IDE | Project SDK, module language level | IDE allows writing 21 syntax while build targets 17 |
| Terminal | `java -version`, `javac -version` | PATH/JAVA_HOME selects the wrong JDK |
| Maven | Release, toolchain, compiler/test plugins | IDE is green but Maven fails |
| Gradle | Wrapper, toolchain, options.release, test JVM | Daemon and toolchain differ |
| CI | JDK image, test matrix, cache | CI uses 17 for 21 source |
| Docker build | Build-stage JDK | Image build differs from local |
| Docker runtime | Runtime JVM launching the artifact | JRE 17 loads class 65 |
| Framework | Bytecode instrumentation, reflection, proxies | Runtime error even though javac succeeded |
| Annotation processors | Language/class-file version support | Code generation fails after upgrade |
| Library consumers | Minimum supported JDK | Clients cannot upgrade JVM yet |
| Native/integrations | JVM flags, architecture, JNI, test containers | Integration fails in deployment environment |

**Rule:** test the artifact on **the lowest published runtime**. If the artifact targets 17 and supports both 17/21, run tests on JVM 17 and JVM 21. If the artifact targets 21, run tests on 21 and newer JVMs within the support contract; do not expect that artifact to run backwards on 17.

A multi-stage Dockerfile using JDK 21 to build but JRE 17 to run is a predictable compatibility error. For real projects, prefer base images and digests verified by the organization; do not guess versions from unchecked tag names.

### Checking runtime/class files in the build pipeline

A good pipeline should include:
- A step printing `java -version` and the compiler/toolchain version;
- Clean compile with `--release`;
- Unit tests on the baseline;
- Integration tests for critical frameworks/dependencies;
- Startup smoke test on the real image;
- Checking for class-loading and API errors at runtime;
- Regression tests for null, pattern fail, guard false, dominance/exhaustiveness.

There is no need to log entire business payloads just to determine which branch was taken. Use Case IDs and appropriate mock test data.

## 14. Version-based syntax decision table

| Problem | If target 17 | If target 21 |
| --- | --- | --- |
| Type checking Object | `instanceof Type t` | `instanceof Type t` or pattern switch |
| Deconstructing record | Call accessors on record after type check | Can use `Record(var x, var y)` |
| Dispatching sealed subtypes | `if/instanceof` or polymorphism | Exhaustive `switch` patterns |
| Guarding on String content | `if (value instanceof String s && condition)` | `case String s when condition` |
| Null selector | Reject upfront or handle separately | Appropriate `case null` or reject upfront |
| Deeply nested data | Type check then call accessors | Nested record patterns when truly needed |
| Adding a subtype | Review `if`, tests | Compiler can prompt to update exhaustive switch |
| Avoiding preview | Avoid preview switch patterns | Use final JEP 440/441 without flags |

**Do not migrate just for shorter syntax.** If `if/instanceof` is already clear, or the policy requires complex I/O/side effects, a clearly named helper/domain method may be better than a large `switch`. Compatibility is only one criterion; readability and behavior must be preserved.

## 15. Semantics to check when moving to Java 21

### Pattern variables and scope

`instanceof String s` (Java 16+) binds the variable `s` when the compiler knows the pattern matched. In an `if` with `&&`, the pattern variable can be used on the right-hand side where the pattern succeeded:

```java
if (value instanceof String s && !s.isBlank()) {
    System.out.println(s.strip());
}
```

Do not treat `s` as a variable in scope across every branch or after control-flow that does not guarantee the pattern.

### Nested record null

```java
record Address(String city) {}
record Ship(Address address) {}

// Java 21:
if (value instanceof Ship(Address(var city))) {
    // Ship and Address have matched non-null types;
    // city can still be null.
}
```

`new Ship(null)` does not match the nested pattern. `new Ship(new Address(null))` can match, because `var city` receives the null component. The guard `when city != null` is only evaluated **after** matching succeeds.

### Pattern guard vs. runtime exception

When a `when` guard returns false, the switch can evaluate the next case. However, if the guard throws an exception, it cannot be treated as false. Similarly, a custom record accessor may throw an exception during deconstruction; Java 21 has `MatchException` rules with the original cause. Do not treat every exception during matching as "pattern did not match."

### Case ordering and dominance

```java
// INTENTIONALLY WRONG ORDER:
case String s -> "ANY";
case String s when s.isBlank() -> "BLANK";
```

The general `String` case shadows the guarded branch; the Java 21 compiler may report dominance. Place specific cases before broad cases. With a sealed hierarchy, avoid having `default` hide unhandled new subtypes if the compiler can help check exhaustiveness.

### Null selector in switch

Do not assume `default` in an enhanced `switch` accepts a null selector. In Java 21, use `case null` when null is a valid state, or reject null with `Objects.requireNonNull` before the switch when the contract forbids it.

## 16. Pre-release review checklist

| Check | Specific Question | Passing Sign |
| --- | --- | --- |
| Supported version | Is the minimum JVM 17, 21, or other? | Documented |
| Feature set | `instanceof`, records, sealed, pattern switch, record patterns? | Cross-checked against final milestones |
| Preview | Are features final in the baseline? | Preview not enabled unless needed |
| Syntax | Uses `when`, nested record, `_`? | Valid for target |
| Compiler | Does the build JDK support `--release`? | Version confirmed |
| Class file | Target <= lowest runtime? | No class version errors |
| Platform APIs | Does the build restrict Java SE APIs? | Appropriate `--release` |
| Dependencies | Can libraries/frameworks read the bytecode? | Integration tests PASS |
| Build plugins | Do Maven/Gradle/processors support the JDK? | CI clean build PASS |
| Test runner | Are test JVMs the right versions? | Clear matrix |
| Null selector | Is there a contract and test? | No reliance on ambiguous `default` |
| Null component | Null nested record vs. null `var`? | Tested |
| Guard | Correct order, pure, null-safe? | No unexpected side effects |
| Dominance | Specific cases before general cases? | Compile PASS |
| Exhaustiveness | All sealed variants covered? | No `default` hiding gaps |
| Migration | Output/exceptions/side effects preserved? | Regression tests PASS |
| Docker/server | Is the real JVM compatible with the artifact? | Smoke test PASS |
| Documentation | Is minimum Java updated? | Release notes/README accurate |

For widely distributed libraries, include additional details such as ABI/API compatibility, module path/classpath, and testing on all JVMs committed to by the product. For closed applications running in a single Docker image, focus on verifying the real image and upgrade/rollback mechanisms.

## 17. Java 17 → Java 21 Migration Process

1. **Lock the baseline:** identify what still runs Java 17, who owns the environment, and whether it can upgrade to 21.
2. **Assess dependencies:** frameworks, plugins, instrumentation, annotation processors, JVM flags, and runtime images.
3. **Upgrade toolchain/build:** JDK 21+, `--release 21`, no preview for final pattern switch/record patterns.
4. **Run regression before refactoring:** create an input suite with subtypes, guard true/false, nested null, and exceptions.
5. **Refactor incrementally:** convert `if/instanceof` to pattern switch when it genuinely improves clarity.
6. **Preserve business policies:** do not casually change validation, ordering, null contracts, or side effects at the same time.
7. **Check the compiler:** fix dominance/exhaustiveness at the root cause, do not add `default` arbitrarily.
8. **Run unit/integration tests:** especially logic using sealed hierarchies and record deconstruction.
9. **Verify deployment:** run the artifact on the finalized Java 21 Docker/server runtime.
10. **Publish the change:** update minimum Java requirements, release notes, and user guides.

If the product must still **support Java 17**, migration cannot be completed by converting all source code to Java 21 syntax in a shared artifact. You can keep a Java 17 module or establish clear module/deployment boundaries.

## 18. Common Mistakes

| Misconception | Risk | Fix |
| --- | --- | --- |
| "Switch `->` is from 14 so pattern switch is from 14" | Compile fail | Distinguish JEP 361 from JEP 441 |
| "Record is from 16 so record pattern is from 16" | Compile fail | Record patterns are final in 21 |
| "Sealed is from 17 so switch with type patterns is from 17" | Preview confusion | Pattern switch is final in 21 |
| "Preview flag unlocks all future syntax" | Incompatible | Only use preview features of that exact JDK |
| "JDK 21 is on my machine so server 17 will run it" | `UnsupportedClassVersionError` | Upgrade runtime or actually lower source/target |
| "`-target 17` alone is enough" | May call newer APIs | `--release 17` + test on JVM 17 |
| "`_` always works in Java 21" | Unsupported syntax | Unnamed patterns are final in Java 22 |
| "`default` automatically handles null selector" | Wrong null handling | `case null` or reject upfront |
| "Guard false means the branch ran" | Wrong debug/metrics | Track the selected case |
| "Nested null Address still enters `when`" | Guard does not run | Understand structural matching |
| "Swapping cases has no effect" | Dominance / wrong logic | Specific branches first |
| "Adding a sealed subtype needs no switch update" | Missed business logic | Exhaustive switch + tests |
| "One local run proves compatibility" | CI/prod uses different JDK | Run on the lowest runtime |
| "Old frameworks always read class 65" | Bytecode parser fail | Upgrade/test dependencies |
| "Changing syntax always preserves behavior" | Different null/exception/side effects | Regression tests |
| "LTS means every vendor supports it indefinitely" | Wrong support policy | Check vendor and maintenance schedule |

## 19. Practice Exercises

**Exercise 1 — Look up milestones.** Identify the first final version of `switch expression`, `instanceof String s`, `record`, `sealed`, `case String s when ...`, and `Point(var x,var y)`. Answer: **14, 16, 16, 17, 21, 21**.

**Exercise 2 — Build both programs.** Compile `Java17FallbackDemo.java` with `--release 17` and `Java21PatternCompatibilityDemo.java` with `--release 21` on an appropriate compiler. Run both on JVM 21 and compare stdout.

**Exercise 3 — Lower the release.** Try `javac --release 17 Java21PatternCompatibilityDemo.java`. Explain why compilation fails even though JDK 21 is installed. Do not use preview as a way to lower the target.

**Exercise 4 — Guard/dominance.** Swap the order of the two `Create` branches in the Java 21 program. Observe the compiler and restore the guarded branch first.

**Exercise 5 — Two kinds of null.** With `Ship("O-5", null)` and `Ship("O-6", new Address(null))`, describe why one input is **pattern fail** and the other is **guard false**.

**Exercise 6 — Add a subtype.** Create `Refund implements Action` and update `permits`. Why does the Java 21 switch expression flag a missing case, while the Java 17 `if` chain only has a runtime fallback?

**Exercise 7 — Gradle/Maven.** Choose min runtime 17 and write a release 17 config. If the source uses Java 21 record patterns, should you change the code or change the runtime commitment?

**Exercise 8 — Preview.** Find a JDK 19 record pattern preview example. Why can't you conclude it runs by default on Java 19 without preview? When porting to Java 21, what syntax and tests need to be checked?

**Exercise 9 — CI and Docker.** IDE is JDK 21, CI is JDK 17, Docker runtime is JRE 17. Which components need upgrading if the code targets 21? Is changing the Project SDK in the IDE enough?

**Exercise 10 — Public library.** If clients still use JVM 17, can you release a target 21 JAR to them? State how to keep the artifact 17-compatible.

**Exercise 11 — Platform APIs.** Explain why `-source 17 -target 17` on a newer JDK does not fully constrain Java SE 17 APIs, and the benefit of `--release 17`.

**Exercise 12 — Migration regression.** Build a test matrix for Create quantity 0/1, Ship address null/city null/blank/valid, null selector, and a new subtype. Should you compare output, branch IDs, exceptions, or side effects?

## 20. Takeaways

The **Java Pattern Matching Version Compatibility Checklist** should be followed in order:

1. Identify the lowest JVM the product must actually run on.
2. Look up the **final milestone** of each syntax; do not confuse preview with default features.
3. Choose the appropriate compiler and `--release`; verify class-file/API targets.
4. Synchronize Maven/Gradle/CI and runtime images; test dependencies/frameworks.
5. Check the semantics of null, guards, dominance, exhaustiveness, record deconstruction, and exceptions.
6. Use regression tests when upgrading from Java 17 to 21, rather than relying only on compile success.
7. Publish the minimum Java version clearly and update it when raising the baseline.

**Core milestones:** Java **14** has switch expressions; Java **16** has records and pattern `instanceof`; Java **17** has sealed types; Java **21** has final pattern switch/`when`/record patterns; Java **22** has final unnamed patterns/variables.

### References

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 406 — Pattern Matching for switch (First Preview)](https://openjdk.org/jeps/406)
- [JEP 420 — Pattern Matching for switch (Second Preview)](https://openjdk.org/jeps/420)
- [JEP 427 — Pattern Matching for switch (Third Preview)](https://openjdk.org/jeps/427)
- [JEP 433 — Pattern Matching for switch (Fourth Preview)](https://openjdk.org/jeps/433)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 405 — Record Patterns (Preview)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — javac options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
