# IDE Support for Pattern Matching in Java 21

## 1. Overview

IntelliJ IDEA, Eclipse IDE (JDT), Visual Studio Code with Java extensions, and Apache NetBeans can all support programming with **pattern matching** in Java. However, whether the feature works properly does not depend only on the IDE name: you need to check the **IDE/plugin version**, **project JDK**, **language/source level**, **Maven/Gradle JDK**, and **JVM running the application**.

Pattern matching allows checking and binding a variable in a single expression:

```java
if (input instanceof String text) {
    System.out.println(text.strip());
}
```

In Java 21, the same idea can be applied with `switch` and record patterns:

```java
return switch (input) {
    case String text when text.isBlank() -> "blank";
    case String text -> "text:" + text.strip();
    case Point(var x, var y) -> "point:" + x + "," + y;
    case null -> "null";
    default -> "other";
};
```

The second snippet is an **illustrative code fragment** inside a method returning `String`, with `Point` already declared. It requires **Java 21** because it uses record patterns and pattern matching for switch; even if the IDE highlights the syntax, a compiler configured at Java 17 will still reject it.

### Learning Objectives

After this lesson, you can:

1. Determine whether an **IDE and extension** understand type/record patterns, `when`, and `switch` expressions.
2. Configure Java 21 for **IntelliJ IDEA, Eclipse JDT, VS Code/Red Hat Java extension, and NetBeans**.
3. Distinguish between **IDE runtime**, **language server runtime**, **Project SDK/JDK**, **compiler release**, and **Run/Test JDK**.
4. Run a standalone Java 21 program from both the IDE and the terminal, and compare the results.
5. Use code actions, refactoring, inspections, and the debugger without unintentionally changing semantics.
6. Diagnose errors related to source level, preview syntax, dominance, flow scoping, exhaustiveness, and null.
7. Synchronize Maven/Gradle/CI configurations so the entire team compiles consistently.

## 2. Which Java Version Do Pattern Matching Features Belong To?

| Construct | Standard Version | Example | Easily Confused With |
| --- | --- | --- | --- |
| `switch` expression | Java 14 | `return switch(n) { case 0 -> "zero"; default -> "other"; };` | The `->` arrow is not necessarily pattern matching |
| `instanceof` type pattern | Java 16 | `obj instanceof String s` | Manual type cast `(String)obj` |
| Record declaration | Java 16 | `record Point(int x, int y) {}` | Record pattern for deconstruction |
| Sealed types | Java 17 | `sealed interface Event permits A,B {}` | Only "permitted to extend/implement", not yet a pattern switch |
| Record patterns | Java 21 | `obj instanceof Point(var x, var y)` | Using a constructor or casting a record |
| Pattern matching for `switch` | Java 21 | `case String s -> ...` | Constant label `case "go" -> ...` |
| Guard `when` | Java 21 | `case String s when !s.isBlank() -> ...` | Old preview syntax using `&&` in case |

**`--enable-preview` is not needed** when using the standard Java 21 features in this lesson. Java 17–20 had preview versions of pattern switch, so preview tutorials may differ from the final syntax and behavior. To learn stable Java 21, choose source/release 21 and the syntax from JEP 440/441.

When a project requires Java 17, `instanceof String s` is still usable because it has been standard since Java 16. However, `case String s` and `case Point(var x,var y)` in `switch` are standard starting in Java 21, so you cannot simply toggle an IDE setting to "make them valid" in a Java 17 build.

## 3. IDE Support Does Not Equal Compiler Support

An IDE displaying Java code may be using several different JDKs:

| Component | Purpose | Example Scenario |
| --- | --- | --- |
| **IDE boot/runtime** | Runs the IDE | The IDE boots on a newer JDK, while the project still targets Java 17 |
| **Java Language Server** | Parses syntax/diagnostics in VS Code | The extension runs on its own runtime, not necessarily the target JDK |
| **Project/Module SDK/JDK** | Project APIs and compilation tools | Module A uses JDK 17, module B uses JDK 21 |
| **Language/source level** | Determines allowed syntax | Source 17 rejects Java 21 pattern switch |
| **Compiler target/release** | Classfile and platform APIs | `--release 21` compiles for Java 21 |
| **Maven/Gradle JVM/toolchain** | Runs the build and selects the compiler | Terminal and IDE import/build with two different JDKs |
| **Run/Test JDK** | Runs the program/tests | Java 21 classes cannot run on Java 17 |

**Consistent setup for this lesson:** a compiler JDK supporting `--release 21`, project/module source level 21, build release 21, and a JVM running Java 21 or newer. If the IDE is an older version, you also need to upgrade the parser/extension/JDT so the editor recognizes the standard syntax.

Check before blaming the editor:

```bash
java -version
javac -version
```

The two commands can report different versions if environment variables/`PATH` point to different Java installations. On Windows you can use `where.exe java` and `where.exe javac`; on Linux/macOS you typically use `which java` and `which javac`.

### Signs the Compiler Used the Wrong Source Level

If `javac --release 17` reports `patterns in switch statements are not supported in -source 17`, that is a **source version error**, not Java 21 being broken. With JDK 21+, try recompiling with `--release 21`, and also fix the official build file rather than only running a one-off check command.

## 4. Comparing Popular IDEs

| IDE | Java Component | Core Settings to Check | Strengths |
| --- | --- | --- | --- |
| **IntelliJ IDEA** | Built-in Java parser, compiler integration, inspections, and refactoring | Project SDK, Project language level, Modules, Maven/Gradle JVM | Full-featured Java IDE, code intentions, and debugger |
| **Eclipse IDE** | Eclipse Java Development Tools (JDT)/Eclipse Compiler for Java | Installed JREs, Java Build Path, Java Compiler compliance | Well-suited for JDT/legacy workspaces |
| **VS Code** | Language Support for Java by Red Hat/JDT Language Server and Java extensions | Java Runtime config, `java.configuration.runtimes`, project import | Lightweight editor, extension-based Java tooling |
| **Apache NetBeans** | Java platform/project system, editor, and debugger | Java Platforms, Project Properties, source level, Maven/Gradle | Integrated Java IDE, convenient for projects already using NetBeans |

Several support milestones announced by vendors:

- JetBrains lists **IntelliJ IDEA 2023.3** as supporting standard Java 21 features including record patterns and pattern matching for switch.
- Eclipse JDT announced support for Java 21 standard features for **Eclipse 2023-09 (4.29)** via the Java 21 update. The specific Eclipse installation must include this JDT update or a newer version with full support.
- VS Code depends on the installed version of **Language Support for Java** and JDT Language Server. The minimum JDK required to **run the language server** changes by extension version; do not equate it with the project's target JDK.
- Apache NetBeans 20 added support for working with Java 21. On newer versions, verify the actual Java Platform and source level rather than assuming every project automatically uses Java 21.

**Choose an IDE based on your project and existing environment**, not on absolute claims about which IDE "runs patterns fastest." Language support, convenience of quick fixes, and indexing speed are different criteria.

## 5. IntelliJ IDEA: Configuring Project SDK and Language Level

### 5.1. Enabling Java 21 in the Right Places

1. Open **File → Project Structure**.
2. Under **Project**, select **Project SDK** as JDK 21 (or a newer JDK compatible with target 21).
3. Set **Project language level** to **21**, not 17 Preview.
4. Open **Modules → Sources** and check the **Language level** of each module; you can choose Project default or 21.
5. In **Modules → Dependencies**, check the Module SDK if it is overridden individually.
6. For Gradle/Maven, check the JVM/toolchain/runner used when the IDE imports and builds the project.
7. Reload the project and try Building/Running the program in section 10.

If you change Project SDK to 21 while a module still targets 17, the IDE still has reason to report errors on `case String s` or `case Record(...)`. If the IDE reverts to 17 after a Maven/Gradle reload, fix the source configuration in `pom.xml`/`build.gradle(.kts)`.

### 5.2. Supported IDE Features

Depending on the version and enabled inspections, IntelliJ IDEA can:

- Recognize Java 21 syntax and suggest code completion for patterns.
- Highlight pattern variables in `when` guards and branch bodies.
- Detect scope errors, dominance, and non-exhaustive switch expressions.
- Suggest converting `instanceof + cast` to a pattern variable or transforming `if/else` structures where appropriate.
- Format code, rename, and navigate records/components/methods.
- Run, debug, and test.

With the default Windows/Linux keymap, you can usually view intentions via `Alt+Enter`. However, **not every IDE version has the same quick fixes**, refactoring names may differ, and auto-refactoring does not replace reviewing `null`/exception behavior.

### 5.3. When the Editor Shows Red While the Terminal Compiles Fine

Compare Project SDK, Module language level, Maven/Gradle project model, IntelliJ version, and the actual compiler messages. Code completion failing to recognize `when` can be caused by an outdated parser/setting rather than the code itself. Do not rewrite valid JDK 21 code just to silence a false positive from an older IDE.

Refer to the JetBrains *Supported Java versions and features* and *Project/Module structure settings* pages at the end.

## 6. Eclipse IDE/JDT: Configuring Compiler Compliance

Eclipse relies on **JDT** to parse and compile Java. For Java 21:

1. Use an **Eclipse IDE for Java Developers** build whose JDT supports standard Java 21 features, or apply the corresponding Java 21 update package.
2. Go to **Window → Preferences → Java → Installed JREs** (the UI may vary by OS) and add JDK 21.
3. For the project, check **Properties → Java Build Path → Libraries** and the JRE System Library/Execution Environment.
4. Go to **Project Properties → Java Compiler**, and set **Compiler compliance level = 21**.
5. Check the project-specific compliance setting if the project does not inherit the workspace default.
6. For Maven/Gradle projects, configure the official build file first and then update the project import.
7. Clean/Build and run the Java 21 program.

**The JDK in Installed JREs** and **Compiler compliance** are not the same setting. Having 21 in Installed JREs while the project is configured with compliance 17 will still disallow record patterns.

### 6.1. JDT Quick Fixes and Diagnostics

Eclipse provides Java Quick Fixes/refactorings, though specific automated transformations depend on the version. When JDT reports a dominated case or invalid scope, check the cause against the Java specification. When JDT flags valid Java 21 syntax as an error while `javac --release 21` accepts it, check the JDT update level and the project's Java target.

**Milestone:** the Eclipse 2023-09 (4.29) announcement explicitly states support for Java 21 standard features such as JEP 440 and JEP 441. If you are running an older 2023-09 build without the appropriate update, do not assume it already has the complete Java 21 analyzer.

## 7. VS Code: Java Extensions, JDT LS, and Project JDK

VS Code requires Java extensions. In practice, install **Extension Pack for Java** or at minimum **Language Support for Java by Red Hat**, plus Java Debugger/Test Runner if you want to use those features in the editor.

### 7.1. Configuration Steps

1. Open the **project's root folder/workspace** rather than a single standalone file outside any context.
2. Open the Command Palette and select **Java: Configure Java Runtime**.
3. Check which project is using JDK 21 and which source level.
4. For Java projects without Maven/Gradle, you can configure the list of project JDKs via `java.configuration.runtimes`.
5. For Maven/Gradle, edit `pom.xml` or `build.gradle(.kts)` and let the extension re-import.
6. Check **Problems**, the Java extension **Output**, and compiler output when errors occur.
7. Run the sample file and compare with the terminal.

The `settings.json` example **is only illustrative for a Linux machine with the exact JDK path shown**:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-21",
      "path": "/usr/lib/jvm/java-21-openjdk",
      "default": true
    }
  ]
}
```

On another machine you must use the **actual JDK path**, not copy the `path` verbatim. `default: true` is especially useful for projects **without a build tool**; Maven/Gradle can still specify their own source/release.

### 7.2. Separating the Language Server JDK from the Project JDK

The Java language server (Eclipse JDT LS) is a separate running process. Some platform-specific extension builds bundle an embedded runtime; universal builds may require an external JDK that meets the startup requirement. The `java.jdt.ls.java.home` setting (when needed) specifies the JDK used to launch the server, whereas `java.configuration.runtimes` describes the JDKs for Java projects.

**The JDK required to run JDT LS may be higher than the target JDK 21 in newer extension releases**. When you see a message like "language server requires newer Java", read the **JDK Requirements** documentation for the installed version instead of forcing the entire project onto that JDK. An extension can run on a newer runtime while still supporting builds targeting older Java versions via toolchains.

### 7.3. Troubleshooting When the Java Extension Does Not Recognize Patterns

If the code compiles with `javac --release 21` but VS Code reports errors:

- Verify that the extension is enabled and the Java Language Server has started.
- Check the Project JDK and Maven/Gradle import, not just the Java version in the terminal.
- Run **Java: Configure Java Runtime** to see the actual active selections.
- If the cache/workspace model is corrupted, run **Java: Clean Java Language Server Workspace**, then let the extension re-import the project. This rebuilds the cache without modifying source code.
- If errors persist, read the Output logs and check the extension/JDT LS version.

Code Action/Refactor operations typically appear in the editor menu when the Java language service is active. Do not assume VS Code has the exact same refactorings or shortcuts as IntelliJ/Eclipse.

## 8. Apache NetBeans: Java Platform and Source Level

Apache NetBeans integrates an editor, project support, and a debugger for Java. For Java 21 practice:

1. Use a recent NetBeans release compatible with your current JDK (NetBeans 20 and newer support Java 21; choose a currently supported release).
2. Open **Tools → Java Platforms** to verify that JDK 21 is registered.
3. In **Project Properties**, check the Java Platform and Source/Binary Format or Java source level of the project.
4. For Maven/Gradle projects, ensure the compiler release/toolchain in the build file is not reset to 17.
5. Run Build/Clean and test the Java 21 file; compare diagnostics with the terminal.

The JDK running NetBeans is not necessarily the JDK compiling the project. If the editor recognizes a record declaration but rejects `case Point(var x, var y)`, check both the parser/support version and the source level. Do not equate "the IDE is running on JDK 21" with "the project is targeting Java 21."

## 9. Maven, Gradle, and CI Builds Must Match the IDE

### 9.1. Maven Compiler Plugin

In `pom.xml`, the typical configuration value is:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This is a **snippet belonging in `pom.xml`**, not a complete POM. The Compiler Plugin translates this target to the equivalent of `javac --release 21` with the appropriate toolchain. You need a Maven/Compiler Plugin version that understands this property and a sufficiently recent JDK. `--release` checks source syntax, classfile format, and target platform APIs, unlike setting `-source` alone.

Check the build environment:

```bash
mvn -version
```

The `mvn -version` command shows the Java runtime that Maven actually uses. When the repository includes a Maven Wrapper, prefer the project's wrapper, such as `./mvnw test` on Unix-like environments or `mvnw.cmd test` on Windows.

### 9.2. Gradle Java Toolchains

Example for `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

This is **Gradle Kotlin DSL**, not Java source code. The toolchain selects the JDK used for tasks; `options.release` enforces the Java 21 target with `javac`. Older Gradle versions may not support JDK 21 properly, so check the compatibility matrix and upgrade in a controlled manner.

If the repository uses the Gradle Wrapper, run `./gradlew test` or `gradlew.bat test` depending on the OS. **Gradle daemon JVM**, **Java Toolchain**, and **IDE JVM** can differ, which is why "green in IDE, red in Gradle" often happens when one of these layers is out of sync.

### 9.3. Do Not Misuse Preview Flags

Record patterns, switch patterns, and `when` are standard in Java 21. Do not add `--enable-preview` just because an old Java 17 preview tutorial required it. Preview flags apply to features that are **not yet standard in the release being used**, and must be managed consistently at both compile and run time if actually needed.

### 9.4. Standalone Compilation

For the sample file in section 10:

```bash
javac --release 21 IdePatternSmokeTest.java
java IdePatternSmokeTest
```

This is an IDE-independent verification gate. If `javac` succeeds while the IDE parser reports errors, investigate the IDE configuration. If the compiler reports errors, prioritize fixing the Java source or target first.

## 10. Complete Java 21 Program to Test Your IDE

Create the exact file **`IdePatternSmokeTest.java`**. This code uses only the Java standard library and exercises the features an IDE must analyze: nested record patterns, `when` guards, sealed hierarchies, `null`, and `instanceof` flow scoping.

```java
public class IdePatternSmokeTest {
    record Customer(String name, int age) {}
    record Purchase(Customer customer, int cents) {}

    sealed interface Command permits Print, Close {}
    record Print(String text) implements Command {}
    record Close() implements Command {}

    static String describe(Object input) {
        return switch (input) {
            case Purchase(Customer(var name, var age), var cents)
                    when name != null && !name.isBlank()
                            && age >= 18 && cents > 0 ->
                    "approved:" + name.trim() + ":" + cents;
            case Purchase(Customer(var name, var age), var cents) ->
                    "review:" + age + ":" + cents;
            case Purchase(var customer, var cents) ->
                    "missing customer";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.strip();
            case null -> "null";
            default -> "other";
        };
    }

    static String route(Command command) {
        return switch (command) {
            case Print(var text) when text != null && !text.isBlank() ->
                    "print:" + text.strip();
            case Print(var text) -> "empty print";
            case Close c -> "close";
            case null -> "null command";
        };
    }

    static String tag(Object value) {
        if (!(value instanceof String s)) {
            return "not text";
        }
        return "len=" + s.length();
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", got=" + actual);
        }
        System.out.println(name + " => " + actual);
    }

    public static void main(String[] args) {
        check("eligible", "approved:Lan:150",
                describe(new Purchase(new Customer(" Lan ", 22), 150)));
        check("minor", "review:17:150",
                describe(new Purchase(new Customer("Mai", 17), 150)));
        check("zero", "review:22:0",
                describe(new Purchase(new Customer("Mai", 22), 0)));
        check("null-name", "review:22:150",
                describe(new Purchase(new Customer(null, 22), 150)));
        check("missing-customer", "missing customer",
                describe(new Purchase(null, 150)));
        check("blank-text", "blank", describe(" \t "));
        check("plain-text", "text:Java", describe(" Java "));
        check("null-value", "null", describe(null));
        check("other", "other", describe(9));
        check("print", "print:hello", route(new Print(" hello ")));
        check("empty-print", "empty print", route(new Print(null)));
        check("close", "close", route(new Close()));
        check("null-command", "null command", route(null));
        check("scope", "len=3", tag("JDK"));
        check("scope-fallback", "not text", tag(10));
        System.out.println("SMOKE TEST PASS");
    }
}
```

Run:

```bash
javac --release 21 IdePatternSmokeTest.java
java IdePatternSmokeTest
```

**Verified exact stdout output:**

```text
eligible => approved:Lan:150
minor => review:17:150
zero => review:22:0
null-name => review:22:150
missing-customer => missing customer
blank-text => blank
plain-text => text:Java
null-value => null
other => other
print => print:hello
empty-print => empty print
close => close
null-command => null command
scope => len=3
scope-fallback => not text
SMOKE TEST PASS
```

### Features Covered in the Test

- **Nested record pattern:** `Purchase(Customer(var name, var age), var cents)`.
- **Guard:** `when name != null && !name.isBlank() && age >= 18 && cents > 0`. The guard does not run if the pattern fails to match.
- **Null component:** `new Customer(null, 22)` still matches the `var` components; the guard prevents an NPE.
- **Nested null record:** `new Purchase(null,150)` does not match `Customer(...)` but matches `Purchase(var customer, var cents)`.
- **Null selector:** `case null` is handled explicitly; `default` does not automatically handle null.
- **Sealed interface:** `route(Command)` lists `Print` and `Close`, requiring no `default` because it covers all permitted subtypes.
- **Flow scoping:** in `tag`, variable `s` is validly in scope after the early return on the negated `instanceof`.
- **Always-active assertions:** `check` uses `throw new AssertionError`, independent of the JVM `-ea` flag.

The program has 15 test cases and the final **`SMOKE TEST PASS`** line, totaling 16 lines of stdout. If any result does not match, the program throws `AssertionError`.

## 11. Testing the Wrong Language Level to Understand IDE Errors

Using the same sample file, intentionally try:

```bash
javac --release 17 IdePatternSmokeTest.java
```

**Expected: compilation fails.** On a recent JDK using `--release 17`, the compiler reports messages along the lines of:

```text
patterns in switch statements are not supported in -source 17
deconstruction patterns are not supported in -source 17
```

These are **excerpted core diagnostic messages**, not the full output with file paths and line numbers; exact diagnostics may vary by JDK. This test proves that Java 17 does not accept Java 21 syntax.

When an IDE reports similar errors, prioritize checking the **project/module language level** and build configuration, rather than rewriting standard Java 21 syntax into old preview forms or enabling preview unnecessarily.

**Note:** Do not put this intentionally failing command into a normal build pipeline; use it only for learning or diagnosing source level issues.

## 12. Using the IDE to Debug and Inspect Pattern Variables

An IDE that supports Java 21 lets you set breakpoints and inspect pattern variables:

```java
case Purchase(Customer(var name, var age), var cents)
        when name != null && !name.isBlank()
                && age >= 18 && cents > 0 ->
        "approved:" + name.trim() + ":" + cents;
```

For a customer aged 22, named `" Lan "`, with amount 150, the branch returns `approved:Lan:150`. For a customer aged 17, the pattern still matches but the guard is false, so Java evaluates the unguarded `Purchase(Customer(...))` branch below and returns `review:17:150`.

**Debugging recommendations:**

- Set breakpoints inside the handler branch or inside a boolean helper method used as a guard.
- Inspect `name`, `age`, and `cents` after they are bound. The debugger may not display pattern variables on paths where a match is not yet guaranteed.
- If a `when` guard is too long, extract it into a clearly named predicate to test/step into the helper, while **preserving short-circuit order**.
- With nested record patterns, check for `null` at each level; do not assume a record component is always non-null.
- When a statement runs fine but the editor shows a warning, check the version/configuration instead of rushing to change Java semantics.

Whether a breakpoint stops directly on a `case` label or on individual `when` expressions depends on the debugger; not all IDEs stop at the exact same positions. Debugging helps observe runtime behavior, while the **compiler/JLS** determines valid language semantics.

## 13. IDE Refactoring: When to Trust It and When to Double-Check

IDEs can suggest converting manual type checks/casts into type patterns.

**Before:**

```java
static String textLabel(Object input) {
    if (input instanceof String) {
        String s = (String) input;
        return s.strip();
    }
    return "other";
}
```

**After:**

```java
static String textLabel(Object input) {
    if (input instanceof String s) {
        return s.strip();
    }
    return "other";
}
```

When the guard and branches are preserved, this is a good candidate for refactoring via a quick fix/inspection. However, refactoring must not alter **null behavior**, exceptions, or the order of side effects.

### 13.1. A Direct Cast Is Not Equivalent to Match + Fallback

```java
static int oldApi(Object input) {
    return ((String) input).length();
}
```

With an `Integer` input, the old code throws `ClassCastException`. With `null`, the cast returns null and then `length()` throws `NullPointerException`.

```java
static int newApi(Object input) {
    return input instanceof String s ? s.length() : -1;
}
```

The new version returns `-1` when it does not match, **changing the contract**, so it is no longer a pure syntactic refactor. Even when the IDE helps generate code, the developer must still review the change.

### 13.2. Converting `if/else` to `switch` Requires Extra Checks

- With `if (value instanceof String s) ... else ...`, a `null` selector usually enters the fallback. In a pattern switch, `null` requires `case null` if you want to preserve that fallback.
- Placing `case CharSequence cs` before `case String s` causes dominance; put subtypes before supertypes.
- `when` guards are ordered: if two guards can both be true, the earlier branch takes precedence.
- Record deconstruction invokes accessors; if a custom accessor has side effects or throws exceptions, refactoring can change behavior.
- A `switch` expression must be exhaustive, and blocks inside an expression use `yield` to produce a value.

A good auto-refactor is a starting point for code review and tests, **not proof that the programs are equivalent**.

## 14. Diagnosing Common Errors

| Message / Symptom | Likely Cause | Check / Fix |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` | Compiler source/release = 17 | Select Java 21 in build/project/module |
| `record/deconstruction patterns not supported` | Target JDK or parser is too old | Java 21 and IDE/JDT/extension supporting standard Java 21 |
| `this case label is dominated...` | General case precedes specific case | Place guarded/specific/subtype cases before general ones |
| `switch expression does not cover all possible input values` | Missing exhaustive branch | Add `default` or cover all sealed subtypes |
| `cannot find symbol: s` after a pattern condition | Invalid flow scope | Only use `s` where the match is guaranteed |
| `NullPointerException` when converting `if` to pattern switch | `null` selector not handled per contract | Check `case null`, add null tests |
| `UnsupportedClassVersionError` at Run time | Runtime JVM is older than target classfile | Run with Java 21+ or build for the right target |
| IDE shows red errors but `javac --release 21` works | Project model, cache, parser/version, or module level | Check JDK, reload/reimport, update tooling |
| `mvn test` fails while IDE build passes | Different Maven JVM/Compiler Plugin/source level | Check `mvn -version`, `maven.compiler.release` |
| `gradlew test` fails while editor is green | Toolchain/Gradle JVM/Gradle version mismatch | Check Gradle toolchains and wrapper |
| VS Code has no Java completion | Java extension/JDT LS not running or not imported | Configure Java Runtime, check Output logs |
| Eclipse project compliance is 17 | Java Compiler project settings | Set compliance to 21 and JRE System Library |
| IntelliJ reverts to level 17 on reload | Maven/Gradle config is the source of truth | Edit the build file, then reload the project |
| NetBeans runs on JDK 21 but source is 17 | IDE boot JDK differs from project source level | Check Project Properties |
| Quick fix breaks null/exception tests | Refactoring changed behavior | Compare against baseline, rollback or fix with tests |

### Safe Troubleshooting Sequence

1. **Classify the error:** is it an editor/JDT error or a real `javac` error?
2. **Verify the compiler:** run `javac -version` and test `javac --release 21` on the sample file.
3. **Check the build:** Maven `release` or Gradle toolchains; the build can override the IDE.
4. **Check project/module language level** and Java Platform/Installed JRE.
5. **Check the IDE/parser/extension version** for standard Java 21 support.
6. If the configuration is correct but diagnostics are stale, reload/clean the workspace in a controlled way.
7. If the compiler still reports errors, inspect the code itself: flow scoping, dominance, exhaustiveness, null.
8. Run regression tests before finalizing changes.

Do not disable all IDE inspections to hide compiler errors. Conversely, do not rewrite valid Java 21 syntax just because an outdated Java analyzer plugin does not understand it yet.

## 15. Multi-Module Projects and CI Reproducibility

A repository may contain both Java 17 modules and Java 21 modules. **Project SDK=21** does not automatically mean every module is allowed to use `case Type variable` in `switch`. Define the release per module, each module's dependencies, and the deployment runtime.

CI should verify:

- The JDK/toolchain version is pinned or explicitly declared.
- The project's source/release build file is committed.
- Tests cover `null` selectors, nested records, true/false guards, subtypes, and sealed switches.
- Refactoring `instanceof + cast` does not change outputs/exceptions/side effects.
- Terminal builds and IDE builds produce the same result, independent of a single developer's local machine.

If CI targets Java 17, **do not introduce Java 21 syntax** and assume "it runs in my IDE" is enough. Either get approval to upgrade the target/deployment JDK or keep the syntax compatible.

### Choosing an IDE for a Team

Use tools whose versions and testing the team can manage:

- IntelliJ: strong in inspections, navigation, and multi-module support.
- Eclipse: fits workspace/JDT setups with explicit project compliance.
- VS Code: convenient for polyglot projects, though Java extensions/JDT LS must be managed.
- NetBeans: suitable if the project and team are already familiar with the Java Platform/project workflow.

All of them require an **independent build/test gate**. Do not treat IDE syntax highlighting as proof of proper Java 21 support.

## 16. Setup Completion Checklist

- [ ] Identified whether the feature requires Java 16 `instanceof` or Java 21 record/switch patterns.
- [ ] The JDK used for compilation supports `--release 21`.
- [ ] The IDE/extension/JDT supports Java 21 standard features.
- [ ] Project/Module Language Level/Compliance is set to 21.
- [ ] Maven Compiler Plugin or Gradle toolchain/options.release targets Java 21.
- [ ] Run/Test JDK is not lower than the target classfile version.
- [ ] IntelliJ Module language level does not unexpectedly override the project setting.
- [ ] Eclipse Installed JRE/JRE System Library/Compiler compliance are consistent.
- [ ] VS Code Language Server is running, Project JDK is configured properly, and not confused with the server runtime JDK.
- [ ] NetBeans Java Platform and project source level are consistent.
- [ ] `IdePatternSmokeTest.java` compiles, runs, and prints exactly 16 lines.
- [ ] `null`, nested records, guards, and sealed switches are tested.
- [ ] IDE diagnostics are compared against the actual compiler when discrepancies arise.
- [ ] Quick fixes/refactorings have been reviewed for behavioral changes.
- [ ] CI build/test matches the developer environment.

**Definition of Done:** Open the sample file in the chosen IDE with no false syntax errors, compile and run at source level 21 with correct output, verify execution paths in the debugger/test runner, and ensure the project configuration is reproducible for others.

## 17. Self-Check Questions

**1. Is using `case 1 -> ...` already pattern matching?**  
No. That is a switch rule with a constant label; pattern matching uses labels such as `case String s`.

**2. Does Java 17 support `instanceof String s`?**  
Yes, because this feature became standard in Java 16. That does not mean Java 17 supports standard pattern switch.

**3. If IntelliJ has Project SDK 21 but Module language level 17, is `case Point(...)` valid?**  
Not at the module's source level. You need to update the module override or the build file.

**4. Is installing JDK 21 in Eclipse's Installed JREs enough?**  
No. Check the JRE System Library, Java Compiler compliance 21, and the build tool.

**5. If VS Code runs the Java Language Server on a JDK newer than 21, is the project forced to use that JDK?**  
No. The Project JDK/release can differ from the language server's runtime.

**6. Is `--enable-preview` required for Java 21 pattern switch?**  
No. Pattern switch and record patterns are standard features in Java 21.

**7. Why does the compiler reject `case String s` placed below `case CharSequence c`?**  
Every `String` is a `CharSequence`; the narrower case is dominated by the broader case before it.

**8. Why can omitting `case null` change behavior when refactoring `if instanceof` to switch?**  
`instanceof` on null returns false; `switch` on null normally throws NPE without an appropriate branch. `default` does not handle null automatically.

**9. Should you trust an IDE Quick Fix without running tests?**  
No. A change can alter null handling, exceptions, guard order, or side effects.

**10. What does the `SMOKE TEST PASS` line prove?**  
The assertions in the sample program passed for the 15 tested inputs; it does not automatically prove all code across the entire repository is correct.

**11. When `javac --release 21` works fine but the IDE reports errors, what should you do?**  
Check JDK/module language level, build import, parser/extension/JDT version, workspace cache, and logs; do not rush to change valid Java code.

**12. If Maven and Gradle targets differ from the IDE, which result should you trust when merging?**  
Align on the official target of the repository and CI. Build reproducibility across the compiler/test suite matters more than warning highlights in a single IDE.

## 18. Official References

### Java

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification — switch](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)

### IDE / Java support

- [JetBrains — Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html)
- [JetBrains — Project structure settings](https://www.jetbrains.com/help/idea/project-settings-and-structure.html)
- [JetBrains — Module structure settings](https://www.jetbrains.com/help/idea/configure-modules.html)
- [Eclipse JDT — Java Compiler Preferences](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.user/reference/preferences/java/ref-preferences-compiler.htm)
- [Eclipse — Java 21 support for Eclipse 2023-09](https://www.eclipse.org/lists/eclipse-dev/msg12203.html)
- [VS Code — Managing Java Projects](https://code.visualstudio.com/docs/java/java-project)
- [Red Hat Java extension — JDK Requirements](https://github.com/redhat-developer/vscode-java/wiki/JDK-Requirements)
- [Red Hat Java extension — Language Support for Java](https://github.com/redhat-developer/vscode-java)
- [Apache NetBeans — Version 20/Java 21](https://netbeans.apache.org/front/main/download/nb20/)

### Build tools

- [Apache Maven Compiler Plugin — Setting compiler release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
