# Configuring sourceCompatibility for Java Pattern Matching

**Context:** Java Core Pattern Matching — Build and tooling. This guide covers configuring the language version for different pattern syntaxes, focusing on **Gradle** (Groovy DSL and Kotlin DSL), while comparing with Maven and running directly with the JDK. The main examples use **Java 21 or later**, because record patterns (JEP 440) and pattern matching for switch (JEP 441) were finalized in Java 21.

## 1. What problem does sourceCompatibility solve?

In a Gradle Java project, **sourceCompatibility** specifies **the Java language version level allowed when compiling source code**. For example, when sourceCompatibility is set to Java 17, the compiler checks the code as Java 17 source; finalized syntax that only appeared in Java 21 will not be accepted.

A common error:

~~~java
// Illustrates Java 21; does not compile at Java 17 source level.
return switch (value) {
    case Point(int x, int y) -> x + y;
    case null -> 0;
    default -> -1;
};
~~~

This snippet uses a **record pattern in a case**. If the project sets sourceCompatibility to 17, having JDK 21 installed on the machine does not automatically allow this syntax: the source level configuration still requires Java 17.

Three separate questions must be distinguished:

1. **Source level:** Which version's syntax is the compiler allowed to understand? Related to sourceCompatibility or the javac flag **--source**.
2. **Actual compiling JDK:** Which version of the javac compiler is used? Related to **Java toolchain** or the JDK that Gradle uses.
3. **Runtime compatibility and allowed APIs:** What is the minimum JVM on which the bytecode can run, and which version's JDK APIs is the source code allowed to call? Related to **--release**, targetCompatibility, and the runtime environment.

**Changing sourceCompatibility alone is not enough.** If sourceCompatibility is 21 but Gradle still selects javac from JDK 17, the older compiler will not understand source level 21. Conversely, javac 24 can compile Java 17 source, but that does not automatically guarantee the code only calls Java 17 APIs unless properly constrained with --release.

## 2. Which patterns require which Java version?

The term "pattern matching" can refer to multiple features finalized at different milestones. Choose the source version based on **the syntax actually used**, rather than bumping to 21 just because the topic name contains the word pattern.

| Feature | Example | Minimum finalized version |
| --- | --- | --- |
| Type pattern in instanceof | **obj instanceof String s** | Java 16 (JEP 394) |
| Record declaration | **record Point(int x, int y) {}** | Java 16 (JEP 395) |
| Sealed class/interface | **sealed interface Shape permits Circle {}** (conceptual example; requires valid subtypes) | Java 17 (JEP 409) |
| Switch expression (not necessarily with patterns) | **switch (n) { case 1 -> "one"; default -> "other"; }** | Java 14 (JEP 361) |
| Record pattern in instanceof | **obj instanceof Point(int x, int y)** | Java 21 (JEP 440) |
| Nested record pattern | **obj instanceof Segment(Point(var x, var y), var end)** | Java 21 (JEP 440) |
| Pattern matching for switch | **case String s -> ...** | Java 21 (JEP 441) |
| Case null and when guard in finalized pattern switch | **case String s when !s.isBlank() -> ...** | Java 21 (JEP 441) |

**Scenario 1:** A Java 17 project that only uses **instanceof String s** and a sealed hierarchy can keep sourceCompatibility 17.

**Scenario 2:** A project that wants to use **case Point(int x, int y)** or **case String s when ...** in switch without using preview must choose **source level 21 or newer**, the corresponding compiler, and a compatible runtime environment.

**Note on Java versions before 21:** Earlier versions of pattern switch and record patterns existed as **preview** features. Syntax, guard keywords, and rules changed between preview releases. For new projects, prefer finalized Java 21+ rather than trying to copy preview code from an older JDK release.

## 3. Recommended approach: Gradle Java toolchain + --release 21

In a project using the Gradle Java plugin, a reliable configuration is:

- **Toolchain 21:** instructs Gradle to use a **JDK 21** to compile Java.
- **Release 21:** instructs javac to compile against the **language, class-file target, and platform APIs** of Java 21.
- **Compatible wrapper:** use a Gradle version that supports JDK 21. Whether Gradle supports running its daemon on a JDK and whether it supports using that JDK via toolchain are two separate capabilities to check.

### 3.1. Gradle Groovy DSL — build.gradle

This is a sample configuration for a standard Java project:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}
~~~

Explanation:

1. **plugins { id 'java' }** enables the Java plugin, creating tasks such as compileJava, compileTestJava, and test.
2. **java.toolchain.languageVersion** selects a compiler from JDK 21 for Java tasks managed by Gradle.
3. **options.release = 21** uses the javac **--release 21** feature to constrain the source level, bytecode, and JDK APIs that can be referenced.
4. **options.encoding = 'UTF-8'** ensures source code containing Vietnamese and Unicode characters is decoded consistently across developer machines and CI.

When a toolchain is set to 21 and no other configuration overrides it, Gradle typically derives the source/target compatibility level from the toolchain version. Setting **options.release** makes the compilation and target API requirement more explicit. There is no need to declare sourceCompatibility/targetCompatibility again if they merely repeat the same value.

### 3.2. Gradle Kotlin DSL — build.gradle.kts

Equivalent configuration:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.encoding = "UTF-8"
}
~~~

The two files above are **two DSL choices for the same goal**, not to be combined into one file. Kotlin DSL uses typed syntax like **languageVersion.set(...)** and **options.release.set(...)**; Groovy DSL typically uses direct assignment.

**Why not just set sourceCompatibility?** Because this property **does not automatically install or select JDK 21**. Toolchains decouple compiler requirements from the JDK used to launch the Gradle daemon, making it better suited for multi-machine and CI environments.

## 4. Configuring sourceCompatibility directly: how to use it properly?

If a project does not use toolchains, Gradle still allows setting sourceCompatibility and targetCompatibility. Groovy DSL example:

~~~groovy
plugins {
    id 'java'
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
~~~

Equivalent Kotlin DSL:

~~~kotlin
plugins {
    java
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
~~~

This approach **only specifies Java source/target** and does not automatically ensure the task uses JDK 21. You must still provide a sufficiently new JDK as the compiler and ensure Gradle can run in your environment.

**When is this appropriate?** Small projects where the compilation JDK is already standardized by another process; or tightly managed legacy configurations. However, for projects with multiple developer machines, build agents, and CI, toolchains generally make the design intent clearer.

### Distinguishing targetCompatibility and --release

- **sourceCompatibility:** Java source syntax level.
- **targetCompatibility:** class file version produced by the compiler.
- **--release N:** instructs javac to compile as Java N for **syntax, class-file target, and Java SE APIs available in N**.

Suppose javac is JDK 24 and you set sourceCompatibility/targetCompatibility to 17, but the code calls a Java 21 API: source/target alone do not necessarily prevent calling the newer API if the compiler sees it. The code may compile but fail with linkage errors when running on JDK 17. **--release 17** catches APIs that do not exist in Java 17 at compile time.

Conversely, **--release 21** requires the javac being used to support release 21. A JDK 17 cannot compile Java 21 merely because Gradle is configured with **options.release = 21**.

**Keep values consistent.** Avoid configuring sourceCompatibility 17 in one place and --release 21 in another, or having multiple plugins override compiler tasks. Choose one clear policy, prefer toolchain + release, and verify the actual compile command.

## 5. Java source level, class-file version, and runtime

A project compiled with Java 21 and target/release 21 produces class files with major version **65**. Meanwhile, Java 17 uses major version **61**.

Therefore:

| Compilation configuration | Key outcome |
| --- | --- |
| JDK 21, --release 21 | Java 21 syntax/API, class files run on compatible Java 21+ |
| JDK 24, --release 21 | Still constrains source/API and class files to Java 21 |
| JDK 17, sourceCompatibility 21 | Cannot compile Java 21 source with javac 17 |
| JDK 21, --release 17 | Cannot use finalized Java 21 record patterns/switch patterns |
| Build produces class file 65 then runs on JDK 17 | Cannot run; may throw UnsupportedClassVersionError |

Distinguish between the **compiling JDK** and the **application runtime JRE/JDK**. Toolchains solve the build side; they do not deploy a JVM runtime to production. CI/CD, container images, and servers must still use a Java version compatible with the class files.

**Example:** A project uses **case Point(int x, int y)**, but production is required to run Java 17. You cannot "keep Java 21 syntax while setting targetCompatibility 17" as a trick to run directly on a Java 17 JVM. You must use Java 17-compatible syntax, upgrade the runtime, or split into modules with separate compatibility strategies communicating across appropriate boundaries.

## 6. Complete Java 21 example using record patterns and switch

Save the following program to **src/main/java/PatternBuildDemo.java** in a Gradle project using the default package for minimal illustration. In a real application, place the class in an appropriately named package.

~~~java
public class PatternBuildDemo {
    sealed interface Message permits Text, NumberValue {}

    record Text(String value) implements Message {}
    record NumberValue(int value) implements Message {}

    static String display(Message message) {
        return switch (message) {
            case Text(String value) when value != null && !value.isBlank() ->
                    "TEXT: " + value.trim();

            case Text(var value) -> "EMPTY TEXT";

            case NumberValue(int value) -> "NUMBER: " + value;

            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Text("  hello  ")));
        System.out.println(display(new Text(" ")));
        System.out.println(display(new Text(null)));
        System.out.println(display(new NumberValue(7)));
        System.out.println(display(null));
    }
}
~~~

### 6.1. Pattern syntax used

- **sealed interface Message:** variant domain consists only of Text and NumberValue.
- **record Text/NumberValue:** simple data structures and implicitly final.
- **case Text(String value):** record pattern extracting the value component.
- **when value != null && !value.isBlank():** guard that only matches the first branch if the string is non-null and non-blank.
- **case Text(var value):** handles the remaining Text instances, including blank or null value; leaves no gap when the guard is false.
- **case NumberValue(int value):** extracts the integer from the NumberValue record.
- **case null:** specifies the result for a null selector.
- **No default:** because the subtypes of sealed Message are completely covered, the switch expression is exhaustive.

**Why is source level 21 needed?** Record patterns in switch with when guards are finalized features in Java 21. Lowering sourceCompatibility to 17 makes this construct invalid Java 17 source, even though records and sealed types individually can be used in earlier versions.

### 6.2. Compiling and running directly with javac

In the directory containing **PatternBuildDemo.java**, using JDK 21+:

~~~bash
javac --release 21 PatternBuildDemo.java
java PatternBuildDemo
~~~

Exact output:

~~~text
TEXT: hello
EMPTY TEXT
EMPTY TEXT
NUMBER: 7
NULL
~~~

The code was verified with a JDK newer than Java 21 by running equivalent definitions directly: the five output lines match the result above. The **--release 21** flag specifies the target compilation level; when running in Gradle, configuring **options.release = 21** carries this same meaning.

### 6.3. Building with Gradle

With the project's existing Gradle wrapper:

~~~bash
./gradlew clean compileJava
./gradlew test
~~~

On Windows PowerShell, use the corresponding wrapper:

~~~powershell
.\gradlew.bat clean compileJava
.\gradlew.bat test
~~~

These commands **only compile and run tests**; they do not automatically run main(). You can run the compiled class with Java 21+ (if using a simple project and package as above):

~~~bash
java -cp build/classes/java/main PatternBuildDemo
~~~

Or use the **application plugin** and configure mainClass to run via the Gradle run task in a real project:

~~~groovy
// Illustrative Gradle Groovy DSL snippet for an application project.
plugins {
    id 'application'
}
application {
    mainClass = 'PatternBuildDemo'
}
~~~

If the class is in a package, mainClass needs the fully qualified name including the package. Do not mix two separate plugins blocks into the same file uncontrollably; the application snippet is only an option for specific project setups.

## 7. Checking which Java the build actually uses

A step-by-step way to inspect:

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
./gradlew compileJava --info
~~~

On Windows, replace **./gradlew** with **.\gradlew.bat**. Depending on task configuration and Gradle version, the detailed output varies, but you can use them to inspect:

1. **java -version:** the JDK/JRE on the terminal PATH, not necessarily the compiler toolchain Gradle selects.
2. **javac -version:** the default javac on PATH, also not necessarily the same as the compiler toolchain.
3. **gradlew --version:** Gradle wrapper version and Gradle's JVM runtime.
4. **gradlew javaToolchains:** Java installations/toolchains detected by Gradle.
5. **gradlew compileJava --info:** build task details, compiler, configuration errors, and sometimes the toolchain path.

Do not equate the output of **java -version** with Gradle's actual compiler. The toolchain may select a different JDK from the one launching the daemon. If you are unsure which compiler is selected, inspect the task/Gradle toolchain output instead of guessing.

**Gradle wrapper:** Support for using Java 21 via toolchains and support for running Gradle itself on Java 21 depend on the Gradle version. A wrapper that is too old may not recognize JavaVersion.VERSION_21 or may fail when running on a newer JDK. Check the Java compatibility matrix for the Gradle version used in your project and upgrade the wrapper when needed, rather than only editing sourceCompatibility.

## 8. Common configuration errors and how to resolve them

| Error or symptom | Possible cause | Resolution |
| --- | --- | --- |
| **invalid source release: 21** or **release version 21 not supported** | Selected javac is too old to support Java 21 | Check compiler JDK/toolchain; use JDK 21+ |
| **case Type(...)** code does not compile when sourceCompatibility is 17 | Record/switch pattern syntax belongs to Java 21 | Set source/release 21 and use a sufficiently new compiler |
| **Unsupported class file major version 65** when building with an old wrapper | Build/Gradle component cannot read Java 21 class files | Upgrade Gradle/plugins to compatible versions and check the JVM running Gradle |
| **UnsupportedClassVersionError** when running the application | Runtime JVM is older than the class-file target | Use a compatible runtime or compile for a lower target with compatible syntax/APIs |
| **Java toolchain not found** | Machine/CI lacks the required JDK or Gradle cannot locate it | Install JDK 21 or configure valid toolchain provisioning/repositories |
| **preview feature ... not enabled** | Using a feature still in preview on the selected JDK, or source level differs from expected | Identify the exact feature/version; switch/record patterns are final as of Java 21 |
| **switch expression does not cover all possible input values** | Cases are not exhaustive, not a Gradle configuration error by default | Add cases for missing subtypes/guards; avoid using default to mask the error |
| Runs in IDE but fails in Gradle | IDE and Gradle are using different JDKs, source levels, or tasks | Sync the Gradle project and check toolchain/compileJava instead of only IDE settings |
| Builds locally, fails in CI | Different JDK/Gradle wrapper/agent image or environment | Pin wrapper, toolchain, release, and runtime in the pipeline |
| Using newer JDK APIs while project claims to target an older JDK | Only constrained source/target without checking target Java APIs | Use options.release, and compile and test on the target runtime |

### 8.1. Source level errors vs. pattern logic errors

For example, a switch expression over a sealed hierarchy without a case for a new subtype is **not exhaustive**. Even when both toolchain and release are 21, the compiler will still report an error. Do not "fix" that error by changing the Java version or blindly adding default; update the branches according to the domain.

Similarly, a branch with **when** may miss values when the guard is false; changing Gradle configuration does not make that branch exhaustive. Compiler configuration only enables the syntax, while correctness and completeness remain the responsibility of the code.

### 8.2. Preview flags are not used for Java 21 final patterns

With Java 21, **record patterns** and **pattern matching for switch** do not require **--enable-preview**. Adding preview flags to these finalized examples provides no benefit and can complicate or confuse the build/test process.

If a real project uses **another feature** that is still in preview in a specific JDK version, that is a separate decision: the compiler and runtime may need preview enabled for that exact version, and that feature's requirements must be checked. Do not mechanically apply Java 17/19/20 preview tricks to source level 21.

## 9. Multi-module Gradle: avoiding source level drift

In a multi-project Gradle build, each subproject can have its own Java plugin, compiler tasks, and compatibility policy. Configuring one module with source 21 does not automatically make every other module use Java 21.

For example:

- **core-model:** still uses Java 17 instanceof type patterns and sealed types, required to run on JDK 17.
- **pattern-app:** uses Java 21 record patterns and switch patterns, requiring compiler/release 21.
- **integration-tests:** must run in an environment capable of loading classes from pattern-app.

You cannot have one module emit Java 21 class files and expect a Java 17 application to load those classes directly. The runtime level of the **final dependency chain** must be compatible with the actual binaries.

In a multi-module project, centralize the policy in a convention plugin or shared build logic when modules share the same target. If there is an intentional reason for multiple targets, clearly document which module must run on which JDK; avoid a root-level configuration overriding a module that must remain on Java 17.

**Additional checks:** compileTestJava tasks, test runtimes, annotation processors, code generators, and other plugins can also be affected by the JDK/toolchain. In particular, build plugins must be compatible with Gradle and the JVM running the plugins themselves, not just with the application code's sourceCompatibility.

## 10. Maven equivalent: maven.compiler.release

Although the name **sourceCompatibility** belongs to Gradle, the language level requirement also exists in Maven. With the Maven Compiler Plugin, the release configuration is typically used:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Or in the appropriate compiler plugin configuration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

These are configuration snippets **placed inside pom.xml**, not standalone XML files. A Maven project needs a Maven Compiler Plugin version compatible with the project and the JDK being used.

**maven.compiler.release=21** is equivalent in meaning to **javac --release 21**, but it does not automatically install JDK 21. If Maven is running with an older javac and has no suitable toolchain, the build will still fail. Maven has its own toolchains mechanism, similar to needing to select the right JDK in Gradle.

Check the environment:

~~~bash
mvn -version
mvn clean test
~~~

Note that Maven and Gradle are two independent build systems; only apply the configuration for the system actually in use, and do not copy Gradle properties into pom.xml.

## 11. IDE and CI: do not let sourceCompatibility work only on a personal machine

A project may run in an IDE yet fail when using the Gradle wrapper because the IDE selects its own JDK 21 while the Gradle daemon or toolchain uses a different JDK.

Verification checklist:

1. **Select JDK 21 for Java 21 source requirements**, or configure a Gradle toolchain so every machine selects the right compiler.
2. **Import the project via Gradle** and run the Gradle tasks themselves; do not treat the IDE Run button as sufficient proof for CI.
3. **Use the Gradle wrapper** committed in the project; avoid relying on globally installed Gradle versions that differ across machines.
4. **Configure CI with the required JDK/toolchain** and ensure Gradle can locate the compiler.
5. **Run tests on the actual runtime** or image that will be deployed; Java 21 code cannot run directly on a Java 17 runtime.
6. **Check annotation processors and plugins** if they manipulate bytecode or compiler APIs, as they have their own JDK compatibility histories.
7. **Keep encoding consistent** for source code and resources when Vietnamese text is present.
8. **Use build logs when errors occur:** distinguish missing-JDK errors, source-level errors, Java logic errors, and plugin errors.

You do not have to force the **Gradle daemon** and **Java compilation toolchain** to always use the same JDK; Gradle supports decoupling them within the compatibility limits of the Gradle version. What matters is verifying each component uses the right JDK and the deployment environment is sufficiently new.

## 12. Do not mix compatibility targets within the same module

Configurations can conflict in intent:

~~~groovy
// Illustrative example of a confusing configuration, not recommended.
java {
    sourceCompatibility = JavaVersion.VERSION_17
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

If a task uses --release 21, the compiler will apply release 21 semantics for that task, while compatibility metadata elsewhere states Java 17. Plugins, IDE integrations, or auxiliary tasks may interpret this differently.

A better design:

- Each module has **one documented Java target**.
- The toolchain is new enough to compile that target.
- Compiler tasks use **--release with that same target**.
- Test runtime and production runtime satisfy the class-file target.
- If publishing a library for Java 17, do not accidentally include code that only compiles on Java 21 in the Java 17 artifact.

If you genuinely need multiple compatibility artifacts, use an appropriate module structure, source set, or multi-release JAR strategy with separate builds/tests. That is an intentional packaging design, not just changing sourceCompatibility on a single line.

## 13. Quick configuration and verification workflow

When tasked with adding record patterns or pattern switch to a Gradle project, follow this sequence:

1. **Identify the syntax needed:** Java 16+ instanceof type pattern or Java 21+ switch/record patterns?
2. **Check the target runtime:** if production requires Java 17, consider keeping Java 17 syntax instead of bumping source to 21 on your own.
3. **Check the Gradle wrapper:** use a Gradle version that supports Java toolchains and the target JDK.
4. **Select the toolchain:** for Java 21, set languageVersion 21 for the Java compiler.
5. **Set release:** options.release = 21 (Groovy) or options.release.set(21) (Kotlin DSL).
6. **Avoid conflicts:** do not use sourceCompatibility/targetCompatibility different from release without reason and verification.
7. **Compile with the wrapper:** run clean compileJava, test; read javac errors for the true root cause.
8. **Verify runtime:** run the class/JAR on the target JDK, not only on the developer JDK.
9. **Test pattern cases:** including new subtypes, false guards, null record components, and a null selector.
10. **Pin CI:** ensure compiler, plugins, and test runtime align with the release target.

A code review checklist:

- [ ] Identified which pattern features require Java 21 rather than just Java 17?
- [ ] Gradle wrapper supports the selected JDK and build tools?
- [ ] Java toolchain or compiler path actually uses JDK 21+?
- [ ] sourceCompatibility, targetCompatibility, and --release settings are consistent?
- [ ] No unnecessary preview flags added for finalized Java 21 patterns?
- [ ] Code builds with the wrapper and passes tests on CI?
- [ ] Class files run on the production JVM?
- [ ] Compile errors from missing cases/guards fixed in logic rather than masked with default?
- [ ] Multi-module and IDE configurations are aligned?

**Conclusion:** To write finalized **record patterns** and **pattern matching for switch**, use **Java 21+** source level, a compiler supporting Java 21, and a compatible runtime. In Gradle, a maintainable approach is **Java toolchain 21 + options.release 21**, rather than just setting sourceCompatibility and assuming every environment is ready. Keeping a clear boundary between **syntax**, **APIs/bytecode**, and **execution JDK** ensures pattern examples both compile and run properly on developer machines, CI, and production.