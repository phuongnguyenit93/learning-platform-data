# Java Version Requirement Notes in Java Pattern Matching APIs and Documentation

## 1. Purpose

When writing documentation for **Java Core Pattern Matching**, saying “requires a newer Java version” is not enough for learners or API users to choose the right JDK. The components were finalized across multiple Java releases: `instanceof` type patterns and records in **Java 16**, sealed types in **Java 17**, and record patterns and pattern matching for `switch` in **Java 21**. An example that runs on JDK 21 is **not automatically** compatible with Java 17.

A good version note should specify:

- **Minimum Java runtime**: the lowest JVM that can load and run the artifact.
- **Build JDK**: the JDK version used to perform the build.
- **Compile target**: the syntax and Java SE/JDK APIs that the source code is allowed to use, typically set with `javac --release N`.
- **Preview policy**: whether the code requires `--enable-preview`.
- **Tested/supported JDKs**: the runtimes that have been tested and are officially supported.

This guide focuses on **how to document and verify that information** in READMEs, JavaDoc, code samples, Maven/Gradle, CI, and release notes.

## 2. Key Java Milestones to Remember

| Feature | First Final Release | Notes |
| --- | --- | --- |
| `switch` expressions with constant labels and `yield` | Java 14 — JEP 361 | Different from pattern `switch` |
| `value instanceof String text` | **Java 16 — JEP 394** | Preview in Java 14–15 |
| Record classes `record Point(int x, int y)` | **Java 16 — JEP 395** | A record class is not a record pattern |
| `sealed`, `permits`, `non-sealed` | **Java 17 — JEP 409** | Preview in Java 15–16 |
| Type patterns in `switch` | **Java 21 — JEP 441** | Preview in Java 17–20 |
| Record patterns `Point(var x, var y)` | **Java 21 — JEP 440** | Preview in Java 19–20 |
| `when` guard in pattern `switch` | Java 21 final | Older preview syntax may differ |
| `case null` in pattern `switch` | Java 21 final | `default` does not handle null automatically |
| Unnamed patterns `_` | Not final in Java 21 | Preview in Java 21 — JEP 443 |

This table uses **final feature milestones without preview flags**, which is suitable for defining minimum requirements for documentation and stable applications. Historical preview releases should be labeled separately; do not treat them as proof that a final syntax is available on an older runtime.

Source: [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html).

## 3. JDK, Source, Runtime, and Library Versions Are Four Different Things

For example, a project built with **JDK 21** using `javac --release 17`: if the code and APIs are compatible, the compiler emits class files targeting Java 17. Therefore, **build JDK = 21** does not mean **minimum runtime = 21**.

Conversely, if a project contains Java 21 pattern `switch` code, building with `--release 21` typically produces class files with major version 65; a Java 17 JVM cannot load those classes, even if the public method signature is simply `String classify(Object)`.

Beyond syntax, you also need to check:

1. **JDK APIs called**: targeting an older source release while calling an API introduced in a newer release can cause runtime errors. `--release N` helps catch those errors at compile time.
2. **Dependencies**: a dependent library may publish bytecode with a higher target, even if the current module's source uses older syntax.
3. **Runtime/container**: the Java version installed in a Docker image or on a server may differ from the JDK running the compiler.
4. **Library version**: an artifact version like `2.3.0` is not the Java version `21`.

Release documentation should state the minimum runtime, compile target, and tested JDKs separately if those values differ.

## 4. How to Determine the Actual Minimum Java Version

| Actual Content | Minimum Final Syntax Milestone |
| --- | --- |
| `if (obj instanceof String text)` | Java 16 |
| `record Box<T>(T value)` combined with type pattern | Java 16 |
| Sealed hierarchy + records + `instanceof` type pattern | Java 17 |
| Enum `switch` expression with enum constants only | Java 14 |
| Type pattern `case String s ->` in `switch` | Java 21 |
| Record pattern `case Point(var x, var y) ->` | Java 21 |
| Guard `case String s when ...` | Java 21 |
| Nested record patterns | Java 21 |

Choose the **highest milestone among the features, Java APIs, dependencies, and actual runtime requirements**. Do not simply search for the `switch` keyword and conclude Java 21: `switch` with constants and pattern `switch` are two different capabilities.

## 5. Java 16 Example: Type Pattern in `instanceof`

Save `Java16PatternDemo.java`:

```java
import java.util.Locale;

public class Java16PatternDemo {
    static String classify(Object value) {
        if (value instanceof String text) {
            return "text:" + text.toUpperCase(Locale.ROOT);
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(42));
        System.out.println(classify(null));
    }
}
```

Build and run commands using a compiler that still supports target 16:

```bash
javac --release 16 Java16PatternDemo.java
java Java16PatternDemo
```

Stdout:

```text
text:JAVA
other
other
```

The `instanceof String text` type pattern has been final since Java 16. If `value == null`, matching fails and returns `"other"`. This example **does not use records, sealed types, or pattern `switch`**.

**Suggested label immediately before the example:** “Java 16+ (final). No preview flag. JEP 394.”

## 6. Java 17 Example: Sealed Types and `instanceof`

Java 17 already had final sealed types, but **pattern matching for `switch` was still in preview**. If you need a non-preview API compatible with Java 17, you can handle a sealed hierarchy using type patterns in `instanceof`.

`Java17ModelDemo.java`:

```java
public class Java17ModelDemo {
    sealed interface Event permits Started, Stopped {}

    record Started(String id) implements Event {}
    record Stopped(String id) implements Event {}

    static String label(Event event) {
        if (event instanceof Started started) {
            return "start:" + started.id();
        }
        if (event instanceof Stopped stopped) {
            return "stop:" + stopped.id();
        }
        return "unknown";
    }

    public static void main(String[] args) {
        System.out.println(label(new Started("A-1")));
        System.out.println(label(new Stopped("A-1")));
        System.out.println(label(null));
    }
}
```

```bash
javac --release 17 Java17ModelDemo.java
java Java17ModelDemo
```

Stdout:

```text
start:A-1
stop:A-1
unknown
```

Here, `record` has been final since Java 16, `sealed` since Java 17, and `instanceof` patterns since Java 16. The method chooses `"unknown"` for null according to **the demonstration contract**, not as a mandatory behavior of sealed types.

**Suggested label:** “Java 17+; sealed classes final (JEP 409); no preview features.”

## 7. Java 21 Example: Record Patterns + Pattern `switch`

`Java21PatternsDemo.java`:

```java
public class Java21PatternsDemo {
    sealed interface Event permits Created, Paid {}

    record Created(String id) implements Event {}
    record Paid(String id, long cents) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Created(var id) ->
                    "created:" + id;
            case Paid(var id, var cents) when cents > 0 ->
                    "paid:" + id + ":" + cents;
            case Paid(var id, var cents) ->
                    "invalid-paid:" + id;
            case null ->
                    "missing";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created("E-1")));
        System.out.println(describe(new Paid("E-1", 500)));
        System.out.println(describe(new Paid("E-1", 0)));
        System.out.println(describe(null));
    }
}
```

```bash
javac --release 21 Java21PatternsDemo.java
java Java21PatternsDemo
```

Stdout:

```text
created:E-1
paid:E-1:500
invalid-paid:E-1
missing
```

Points to explain in the documentation:

- `Created(var id)` and `Paid(var id, var cents)` are **record patterns**, final since Java 21.
- `when cents > 0` is a guard in pattern `switch`, final since Java 21.
- The unguarded `Paid` case handles the remaining `Paid` instances.
- `case null` explicitly defines the behavior for a null selector.
- The `switch` expression can be exhaustive without `default` thanks to the sealed hierarchy.

**Suggested label:** “Java 21+ (non-preview), JEP 440 and JEP 441; build with `javac --release 21`.”

Do not label it Java 17+ just because the `Event` interface is sealed: the version actually required for the entire example is 21.

## 8. JavaDoc: `@since` Is Not the Minimum JDK

Suppose a library has release version **2.3.0**, and that artifact requires **Java 21**. These two pieces of information have different meanings:

- `@since 2.3.0` means the API element was introduced in **release 2.3.0 of the library** according to the project's versioning convention.
- “Minimum Java runtime: 21” refers to **the environment that loads and runs the artifact**.

`@since` is a **documentation tag** that generates the “Since” section in JavaDoc; it does not create a binary check and does not configure the compiler.

Example method in an API class (illustrative snippet, not a standalone file):

```java
/**
 * Classifies a value by its runtime type.
 *
 * <p>This artifact requires Java 21 or later.
 *
 * @param value input value, may be null
 * @return classification label
 * @since 2.3.0
*/
public static String classify(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        case Integer n -> "int:" + n;
        case null -> "missing";
        default -> "other";
    };
}
```

If the API has existed since library version 1.8.0 and only the **implementation** switched to pattern `switch` in 2.3.0, do not change `@since` to 2.3.0. API history and the artifact's Java requirement are different.

For classes in the **Java Platform API**, `@since 21` may indicate the release of the Java Platform API specification. Do not automatically apply that convention to third-party libraries that have their own versioning scheme.

## 9. README Template for Java Compatibility

The snippet below is a **template to be tailored to the actual data of your module**:

```markdown
## Java compatibility

- Minimum Java runtime: **21**
- Build JDK: **21**
- Compile target: **21** (`javac --release 21`)
- Pattern-matching preview flag required: **No**
- Language features:
  - Type pattern `instanceof` (final in Java 16)
  - Records (final in Java 16)
  - Sealed types (final in Java 17)
  - Record patterns and pattern `switch` (final in Java 21)

### Quick start

    javac --release 21 Java21PatternsDemo.java
    java Java21PatternsDemo

### Notes

The published artifact requires a Java 21-or-newer runtime.
Java 17 cannot load Java 21-targeted class files.
```

The template does not claim by itself that a specific project has been tested on Java 21. For repositories with multiple Java 16/17/21 examples, add a **version label right before each code block** rather than relying only on a single general statement on the homepage.

## 10. Proving Compatibility with `javac --release`

The following commands illustrate how to verify the three programs:

```bash
javac --release 16 Java16PatternDemo.java
javac --release 17 Java17ModelDemo.java
javac --release 21 Java21PatternsDemo.java
```

Use a compiler that still supports the corresponding target. According to the `javac` manual, `--release N` instructs the compiler to:

1. Check language syntax against release N.
2. Restrict referenced Java SE/JDK APIs to release N.
3. Generate class files targeting release N.

Do not combine `--release` with `--source`/`--target` in the same command. Configuring only `-target 17` is not as strong as `--release 17` for catching references to newer APIs from the JDK running the compiler.

**Intentional negative tests:**

```bash
javac --release 17 Java21PatternsDemo.java
javac --release 16 Java17ModelDemo.java
```

With a compiler that supports those targets, **both commands must be rejected** because the source uses features that were not yet final in the requested release. Keep these tests separate from production source and check for a nonzero exit code; do not rely strictly on exact diagnostic wording.

If the JDK compiler no longer supports an older `--release` value, that is a tool limitation rather than necessarily a syntax error in the original release.

## 11. Class-File Version Is Different Evidence from Source Code

| Java Target | Major Class-File Version |
| --- | --- |
| 16 | 60 |
| 17 | 61 |
| 21 | 65 |

Inspect the compiled class:

```bash
javap -verbose Java21PatternsDemo
```

With a `--release 21` build, the output includes:

```text
major version: 65
```

A Java 17 JVM supports up to major version 61 and therefore **cannot load Java 21 major 65 classes**, typically resulting in `UnsupportedClassVersionError`.

Note that the class-file major version alone is not enough to prove that all dependencies work on the minimum JVM. A dependency or framework with a newer JDK requirement can still cause the application to fail at runtime.

Preview class files from modern Java releases may carry **minor version 65535**. When a preview feature becomes final, perform a clean rebuild with the corresponding JDK and release; do not manually edit the class-file header to bypass checks.

## 12. Maven: Set the Compile Target Explicitly

In the `pom.xml` of a Java 21 module (configuration snippet, not a complete file):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

You need a JDK, Maven, and compiler plugin that support target 21. Pin the compiler plugin version in released projects to avoid differences caused by Maven defaults.

Verify:

```bash
mvn --version
mvn clean verify
```

`mvn --version` shows the JVM running Maven; projects using toolchains may select a different compiler JDK, so check the actual toolchain/CI configuration.

If you want to continue supporting Java 17, set release 17 **and** replace Java 21 code with compatible code. Maven does not backport Java 21 record patterns to Java 17.

## 13. Gradle: Toolchain Is Different from `release`

In `build.gradle.kts` (Kotlin DSL, Java plugin):

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

`toolchain` selects the JDK for the appropriate build tasks; `release` restricts syntax, Java SE/JDK APIs, and bytecode target. You can use a JDK 21 toolchain to build target 17 with `release.set(17)` if the source and dependencies **are genuinely Java 17-compatible**.

Do not copy Kotlin DSL verbatim into a `build.gradle` using Groovy DSL. With newer Gradle versions, ensure the actual Gradle version supports the selected Java toolchain.

## 14. Preview Features Must Be Documented Separately

Pattern `switch` was in preview in Java 17–20. A **historical** example specifically for JDK 20 might be documented as:

```bash
javac --enable-preview --release 20 Example.java
java --enable-preview Example
```

That command does not mean a newer JDK can arbitrarily re-enable JDK 20 preview syntax: preview features are tied to their **corresponding release**.

On Java 21, record patterns and pattern `switch` are final, so the Java 21 examples in this guide **do not require `--enable-preview`**. However, if a project uses **another Java 21 preview feature**, that feature and its flag must be declared separately.

For example, the preview guard `case String s && condition ->` is not the final Java 21 guard syntax. The final version uses `case String s when condition ->`.

## 15. CI and Runtime Must Be Consistent with Documentation

A common mistake:

- The IDE uses JDK 21.
- The compiler targets 17.
- The Docker image uses JVM 17.
- Yet the README says “Java 21 only”.
- Or CI tests only one Java version, while the documentation assumes other versions are also supported.

Start with:

```bash
java --version
javac --version
```

Then cross-check the JVM running Maven/Gradle, toolchains, the test runner, and the deployed application.

Documentation should have two separate sections: **minimum supported runtime** and **JDKs actually tested**. Do not claim “tested on 21 and 22” unless tests have been run on both.

For a library shared across multiple services, raising the baseline from Java 17 to Java 21 can be a breaking runtime change for older clients even if public API method signatures do not change. Document this in the release notes and verify actual consumers.

## 16. Supporting Multiple Java Baselines

If a product needs an API for Java 17 and a newer implementation using Java 21 pattern `switch`, you can:

- Maintain a **Java 17** module/artifact using `instanceof` patterns.
- Publish a **Java 21+** module/artifact using record patterns and pattern `switch`.
- Document the artifact coordinates, minimum Java runtime, and CI compatibility matrix **for each variant**.

Multi-Release JARs can be an advanced option, but they do not automatically solve every issue around public APIs, dependencies, and runtime class loading.

You cannot publish a JAR containing Java 21 classes and claim Java 17 will run it as long as only “simple methods” are called: the JVM may reject major 65 class files before any code executes.

## 17. Release Notes Template When Raising Minimum Java

Example for a **hypothetical** library raising Java 17 → Java 21 in version `3.0.0`:

```markdown
## Java requirement changed in 3.0.0

- Old minimum runtime: Java 17
- New minimum runtime: Java 21
- Compile target: `javac --release 21`
- Reason: final record patterns and pattern `switch`
- Preview flags: not required for those features
- Upgrade: update runtime, build toolchains, CI,
  and rerun integration tests for all consumers
```

The snippet above is only a template for a verified case, not the history of any specific library. Do not write “last Java 17-compatible version” without verifying the actual release.

## 18. Common Documentation Mistakes

| Misconception | Correct Documentation |
| --- | --- |
| “All pattern matching requires Java 21” | `instanceof` pattern has been final since Java 16 |
| “Sealed interfaces require Java 21” | Sealed types have been final since Java 17 |
| “Pattern `switch` has been final since Java 17” | Preview in 17–20, final in 21 |
| “`@since 21` always means min JVM 21” | `@since` usually tracks API/library history |
| “Building with JDK 21 means all artifacts only run on JVM 21” | Check `--release` and the build output |
| “Setting `-target 17` alone is enough” | Prefer `--release 17` to restrict APIs |
| “Having `default` means pattern `switch` accepts null” | `case null` must be handled per contract |
| “A preview flag enables any older syntax” | Preview features are tied to each release |
| “Major 65 still runs on Java 17” | JVM 17 cannot load Java 21 major 65 classes |
| “Tested on JDK 21 means higher JDKs are tested too” | Only list runtimes that were actually tested |
| “Updating the README is enough when raising the Java baseline” | Update artifacts, CI, and release notes as well |

## 19. Pre-Publication Checklist for API Documentation

- [ ] Have you identified the newest final feature in each example?
- [ ] Have you distinguished Java 16 `instanceof`, Java 17 sealed types, and Java 21 record/switch patterns?
- [ ] Did you avoid confusing Java 14 `switch` expressions with Java 21 pattern `switch`?
- [ ] Do complete Java code fences have matching file/class names and outputs?
- [ ] Are preview/final status and minimum Java version labeled right before the examples?
- [ ] Is the compile target constrained with `--release`?
- [ ] Does JavaDoc `@since` reflect the software version according to project conventions?
- [ ] Does the minimum runtime match the class-file major version and dependencies?
- [ ] Are “tested” JDKs actually verified by CI?
- [ ] Are Maven/Gradle, IDE, Docker image, README, and release notes consistent?
- [ ] If the minimum Java version was raised, have the breaking compatibility change and upgrade steps been documented?

**Conclusion:** Java version notes are part of the **API usage contract**. Determine the Java milestone based on the newest feature used (especially **16 / 17 / 21** for Pattern Matching), document library and JDK versions separately, and prove compatibility with `--release`, class-file inspection, and runtime tests rather than just writing a number in the README.

## Official References

- [Oracle Java SE 21 — Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [Oracle Java SE 21 — Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [Oracle Java 21 `javac` — `--release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Oracle Javadoc — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [Oracle JVM SE21 — ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
