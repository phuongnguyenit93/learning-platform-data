# IDE Plugins, Parsers, and Project Language Levels

## 1. A Java project can compile cleanly while the IDE still reports errors

When upgrading a JDK, development teams typically focus on `javac`, Gradle/Maven versions, and the production runtime. However, another ecosystem of tools reads and parses Java code every day: **IDEs, language servers, plugins, formatters, static analyzers, generators, and test tooling**.

Suppose a project has upgraded its compiler to JDK 21 and uses pattern matching in `switch`:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Integer number -> "integer: " + number;
        case String text -> "text: " + text;
        case null -> "absent";
        default -> "other";
    };
}
~~~

This syntax is officially supported in Java 21. Terminal builds may succeed, yet an older IDE or Java analysis plugin still underlines `case Integer number` in red. In that situation, changing code to satisfy the IDE warning can accidentally strip out a valid Java 21 feature. Conversely, the IDE may understand new syntax, yet CI uses a JDK 17 compiler or `--release 17`, causing the build to fail.

Some common symptoms:

- The IDE flags `record`, `sealed`, or new `switch` syntax as errors even though the target `javac` accepts them.
- Checkstyle/PMD plugins or formatters fail to parse a new file.
- An annotation processor running inside the compiler throws `IllegalAccessError` after switching JDKs.
- A plugin or coverage agent reads class files and reports `Unsupported class file major version`.
- Generated sources from OpenAPI, JAXB, protobuf, or Lombok use APIs/syntax at a different Java level from the module's own level.
- The IDE and terminal show two different check results.
- The IDE imports the project using a different Gradle JVM from the JDK chosen for the project.

The root issue is that **there is not just one "Java version" in a project**. Every tool has its own parser version, runtime, and support scope. This lesson guides you through identifying the exact failing layer, choosing the right language level, managing IDE plugins, and verifying the system during migration in the context of **Java Advance Compatibility Migration – Code Generation and Testing Tools**.

## 2. Distinguishing six concepts often lumped together as "Java version"

| Concept | Role | Example risk |
| --- | --- | --- |
| IDE runtime | JVM running the IDE process itself or the language server | IDE/plugins fail to run on a new JVM |
| Project SDK/JDK | JDK attached to the project/module for compiling or powering code insights | IDE sees Java 21 while CI uses JDK 17 |
| Language level | Java syntax/semantics version permitted in source code | IDE marks `record` as an error if the module level is too low |
| Compiler toolchain | Compiler/JDK selected by the build tool for compilation tasks | `javac` is too old to recognize the requested source release |
| Target release/class-file version | Java APIs and bytecode format targeted by the artifact | A Java 21 artifact does not run on a Java 17 JVM |
| Test/application runtime | JVM actually running tests and the application | Compilation succeeds, yet test runner/agent does not support the new JDK |

There is also **the parser's own version**, which may reside in a Java language server, IDE plugin, code analyzer, or code generator. A parser is often released independently from the JDK and may not support new syntax even when the project compiler does.

Example record of an actual configuration:

~~~text
IDE version:             release verified to support Java 21
IDE runtime:             JBR or JDK used to launch the IDE
Project SDK:             JDK 21
Module language level:   Java 17
Gradle daemon JVM:       JDK supported by the Gradle release
Java compiler toolchain: JDK 21
Java --release target:   17
JUnit test runtime:      JDK 17 and/or JDK 21
Production runtime:      Java 17 (minimum still supported)
~~~

This configuration **can be valid** when the goal is using a newer tool to compile a library that remains Java 17-compatible. It does not mean sources are allowed to use syntax introduced only in Java 21. Choosing a newer compiler and choosing a source language level are two separate decisions.

## 3. IDE parsers, Java compilers, and bytecode readers do not do the same thing

A Java file can pass through multiple analyzers:

~~~text
             .java file
                  |
        +---------+----------+
        |                    |
        v                    v
 IDE / Language Server    javac / ECJ
 parser + AST             compile + type checking
        |                    |
        v                    v
 Inspections, formatter    .class file
 refactoring, navigation      |
                              v
                        ASM / Byte Buddy /
                        JaCoCo / analyzers
                              |
                              v
                           JVM runtime
~~~

A **source parser** recognizes Java syntax and constructs a representation such as an AST (Abstract Syntax Tree). It needs to know the language constructs allowed in the release being analyzed: `record`, `sealed`, switch patterns, text blocks, lambdas, etc.

A **compiler** performs more steps than parsing: name/type resolution, language rule enforcement, annotation processing, and bytecode emission. An IDE parser may understand a construct while the compiler still rejects it due to type errors, APIs missing from `--release`, or invalid configuration.

A **bytecode parser** such as ASM or Byte Buddy reads class files rather than Java sources. It must understand new class-file major versions, constant pools, and attributes. A tool may support Java 21 source while its bytecode reader still fails to understand class-file version 65, or vice versa.

The **JVM runtime** executes bytecode. Success in the IDE and compiler does not prove the runtime has the required modules, dependencies, agents, native libraries, or Java level.

Do not fix a failure in one layer by changing settings in another layer without identifying the cause. For instance, raising the IDE language level does not upgrade `javac`; upgrading `javac` does not automatically upgrade Checkstyle's parser.

## 4. What specifically is the Java language level?

The *language level* governs which **source code syntax and semantic features** can be used. Illustrative milestones:

| Java release | Representative language features |
| --- | --- |
| Java 8 | Lambda expressions, method references, default methods |
| Java 9 | Module declarations (`module-info.java`), several syntax refinements |
| Java 10 | Local-variable type inference with `var` |
| Java 14 | Switch expressions standardized |
| Java 15 | Text blocks standardized |
| Java 16 | Records and pattern matching for `instanceof` standardized |
| Java 17 | Sealed classes standardized |
| Java 21 | Record patterns and pattern matching for `switch` standardized |

This table lists representative milestones rather than every change in each release. A feature may go through preview releases before being standardized. When using preview features, syntax and support must be evaluated against the **exact JDK release**.

### 4.1. Example of a source level lower than the feature

~~~java
public record UserId(String value) {
}
~~~

Records became a standard feature in Java 16. If a module sets its language level to Java 11, the IDE rightly warns; a compiler using `--release 11` will also reject it. In that situation, do not "silence the red IDE squiggles" by switching to language level 21 if the product still must ship for Java 11.

You must intentionally choose one of two directions:

1. Raise the Java level the module commits to support, then update the toolchain, tests, and runtime accordingly.
2. Keep the lower Java level and rewrite the representation using a class appropriate for that release.

### 4.2. Language level is not the runtime version

An IDE allowing Java 17 syntax does not mean the code can run on Java 8. Conversely, running `javac` from JDK 21 with `--release 17` can build an artifact compatible with the Java 17 platform without requiring a Java 21 runtime.

In a multi-module application, one module may have a lower language level than another. This is safe only when **compile/runtime relationships** are clearly defined; shared modules must not accidentally depend on APIs or bytecode requiring a newer runtime than consumers still need to support.

## 5. Source language level, Java APIs, and bytecode are three separate constraints

The following three examples illustrate this:

~~~java
// Requires Java 16+ for record syntax.
public record Point(int x, int y) {
}
~~~

~~~java
// Syntax is not particularly new, but List.of API requires Java 9+.
List<String> roles = List.of("reader", "writer");
~~~

~~~java
// A library compiled to class-file major 65
// requires a JVM capable of loading Java 21 class files.
~~~

If you only set `-source 8` or language level 8 while compiling with a newer JDK without constraining platform APIs, the compiler can see newer Java APIs not belonging to Java 8. To build an artifact usable on an older Java platform, consider `javac --release N` per JDK/toolchain support.

Illustrative command:

~~~bash
javac --release 17 -d build/classes src/main/java/example/Main.java
~~~

`--release 17` restricts syntax/semantics and Java platform APIs to release 17 while generating the matching class-file target. It **does not guarantee** that every third-party dependency used also runs on Java 17: you still must inspect JARs and test on the minimum runtime.

### 5.1. When the IDE and build tool disagree, the build is the source of verification

The IDE's language level can be chosen manually or derived from Maven/Gradle import. If the build script specifies `--release 17` while the IDE displays Java 21, IDE warnings/passes do not represent the CI build. A code change is considered valid only after **compiling with the project's official toolchain and release target**.

Do not disable all IDE warnings thinking "CI is the real source of truth"; the IDE remains valuable for catching errors early. **Synchronize configuration** so both systems reach consistent conclusions.

## 6. IDE versions and plugin versions must be inventoried

An IDE is an ecosystem made of many components:

- IDE core and main Java parser.
- Extensions/plugins adding syntax support, refactoring, and framework integration.
- Language servers or Java extension hosts (in some editors).
- Build integrations such as Gradle, Maven, Kotlin, and Groovy.
- Formatters, static analyzers, and code quality plugins.
- Test runners, coverage/debuggers, and bytecode tooling.
- Schema-based code generation plugins or annotation processors.

**A new IDE version does not automatically prove every installed plugin also supports the new language level.** A plugin may rely on changed IDE AST APIs, carry its own parser lacking new Java syntax, or bundle runtime libraries that do not support new class-file versions.

When selecting versions for a migration, record:

| Component | What to verify |
| --- | --- |
| IDE release | Whether it supports target Java syntax and project model |
| IDE runtime | Whether the IDE runs on a vendor-supported runtime |
| Plugin release | Whether it supports the IDE build, parser/AST APIs, and target JDK |
| Plugin runtime dependencies | Whether bytecode/parser libraries are compatible |
| Build integration | Whether Maven/Gradle import reads toolchains/releases accurately |
| Test support | Whether runners, debuggers, and coverage support target class files |

Do not draw conclusions from plugin names alone or assume "the latest release always works". Read compatibility notes for the **specific version** and verify with a sample project.

## 7. IntelliJ IDEA: Project SDK, language level, and Gradle JVM

In IntelliJ IDEA, you may need to inspect independent settings:

1. **JDK running the IDE:** typically bundled with or configured separately for the IDE; not synonymous with Project SDK.
2. **Project SDK:** JDK bound to the project.
3. **Project language level:** syntax permitted by the IDE across the project.
4. **Module language level:** can differ from the project when configured per module.
5. **Gradle JVM:** JVM running the Gradle daemon when invoked by the IDE.
6. **Maven importer/runner JDK:** JDK used for Maven integration.
7. **Compiler and test run configurations:** may carry separate build-level selections.

Menu paths in the UI change across IDE versions; locate **Project Structure**, **SDK**, **Language Level**, **Gradle settings**, **Maven settings**, and **Run Configurations** in the version in use rather than relying on exact menu paths written for an older version.

### 7.1. When the IDE shows red errors while the Gradle build passes

Example:

~~~text
IDE Project SDK:       Java 17
IDE language level:    17
Gradle toolchain:      Java 21
Gradle compile target: 21
Source:                Java 21 pattern switch
~~~

Gradle can compile Java 21 code, yet an IDE configured for Java 17 flags it as invalid syntax. Re-import the project model and verify the actual language level rather than rewriting source code to appease an outdated IDE configuration.

### 7.2. When the IDE is green while CI fails

~~~text
IDE language level:    21
Gradle release target: 17
Source:                Java 21 pattern switch
~~~

The IDE may accept the syntax while CI rightly rejects it because the artifact must stay compatible with Java 17. The fix is **aligning the Java-level contract**, not just tweaking settings to hide warnings.

### 7.3. Plugins using PSI

On the IntelliJ Platform, Java plugins may use PSI (Program Structure Interface) to manipulate source structures. Old plugins may fail to handle new PSI element kinds for newer language features or depend on changed platform plugin APIs.

If a plugin's refactoring, inspection, or code generation yields incorrect results:

- Record the IDE build and plugin version.
- Reproduce on a minimal Java file.
- Separate IDE core parser errors from inspection/plugin errors.
- Update the plugin per its compatibility guide.
- For internal plugins, update PSI handling code for the new AST/types.

Do not assume a warning from an inspection plugin represents a `javac` verdict.

## 8. Eclipse IDE/JDT: compiler compliance differs from Installed JRE

Eclipse Java Development Tools (JDT) uses its own Java compiler and source analysis model (ECJ/JDT). When upgrading the JDK, confirm:

- Eclipse/JDT release supports the target Java language level.
- Installed JREs/JDKs are configured for the workspace and project.
- Project **Compiler compliance level**.
- Java build path, execution environment, and module dependencies.
- Maven integration (m2e) or Gradle integration (Buildship).
- Plugins relying on JDT AST/ECJ and their syntax support level.

A project with Installed JDK 21 whose compiler compliance is set to Java 17 can reject Java 21 syntax. Conversely, setting compliance higher than the actual JDK may fail to behave as expected.

### 8.1. Eclipse builds do not necessarily match `javac` builds

The JDT compiler can produce different diagnostics and incremental build behavior from `javac` in certain cases. That alone does not prove code is right or wrong; use the **official compiler in the build pipeline** to determine the release contract.

For example, when a warning appears in Eclipse but not in Maven:

1. Check project compliance and execution environment.
2. Check whether m2e/Buildship properly imported the Maven/Gradle model.
3. Determine whether annotation processor plugins run inside Eclipse or only during terminal builds.
4. Reproduce with a clean build and inspect actual generated source outputs.

For internal plugins using `org.eclipse.jdt.core.dom`, check the AST level and API handling new Java nodes; do not reuse an overly old parser mode to analyze newer sources.

## 9. VS Code Java: language server, extensions, and project runtimes

In VS Code, standard Java features are provided through a Java language server and extensions. Distinguish:

- The JVM running the Java language server.
- The list of runtimes/JDKs used to import projects.
- The JDK used by Gradle/Maven when invoked from the editor.
- Java source level and compiler/release target pulled from build configuration.
- Extension versions and supplemental code analysis tools.

Illustrative configuration example in `settings.json`:

~~~json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "/path/to/jdk-17"
    },
    {
      "name": "JavaSE-21",
      "path": "/path/to/jdk-21",
      "default": true
    }
  ]
}
~~~

Paths are placeholders only; replace them with actual JDK installation locations on the machine. Configuring the JVM that runs the language server may use a separate setting depending on extension version; do not infer it from `java.configuration.runtimes` alone.

If the editor understands syntax while terminal builds fail, check Maven/Gradle settings. If terminal builds pass while the editor fails to parse syntax, inspect the language server/Java extension release and project import status. Once environments are aligned, refresh project import or clean the language-server workspace according to editor documentation.

Do not wipe all workspace caches as your first step; first confirm that the extension version supports the new syntax and the build model imported properly.

## 10. Apache NetBeans and other IDEs

With NetBeans or other Java IDEs, troubleshooting still rests on the same questions:

1. Does the IDE release recognize the target Java language level?
2. Which Java platform does the project use?
3. Where is the source/binary format defined in project/build configuration?
4. Does Maven/Gradle project import synchronize the model?
5. Do editor, refactoring, or analyzer plugins bundle their own parsers?
6. Are different compilers/test runners/JDKs used between the IDE and CI?

Do not migrate an entire team to another IDE simply because one plugin reports an error when its parser has not been updated. Separate IDE core, plugin, and build compatibility accurately before deciding.

## 11. Maven: compiler release configuration is the clear reference source

In Maven, the Java language target is commonly managed through the Maven Compiler Plugin and matching version properties. Key excerpt in `pom.xml`:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Or plugin configuration:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>APPROVED_PLUGIN_VERSION</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`APPROVED_PLUGIN_VERSION` is a placeholder and must not remain in real builds. Choose a plugin confirmed by the vendor to support the target Maven/JDK versions.

Commands to inspect the environment and effective model:

~~~bash
mvn -version
mvn help:effective-pom
mvn -DskipTests=false test
~~~

`mvn -version` shows which Java runtime Maven actually runs on. It does not by itself prove a separately configured toolchain or forked test process uses the same JDK. When using the Maven Toolchains Plugin or forking, verify the chosen toolchain in logs.

### 11.1. Common mismatch

A developer opens a project in an IDE with SDK 21, while Maven runs on JDK 17 and the POM sets `release 21`. The compiler may report:

~~~text
error: release version 21 not supported
~~~

The cause is that the running compiler does not recognize that target release. Changing the language level in the IDE does not replace configuring the right JDK for the compiler.

### 11.2. Multi-module parent POM

In a Maven reactor, the parent POM may set a common `maven.compiler.release`, while certain modules require a different target due to public APIs or downstream consumers. When using profiles/properties/module overrides, document them clearly in the module matrix to prevent "a module accidentally getting upgraded" when parent properties change.

## 12. Gradle: Java toolchain, compiler target, and Gradle JVM

Gradle Groovy DSL example using JDK 21 to compile sources that still support Java 17:

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
    options.release = 17
}
~~~

Here:

- Java toolchain identifies the compiler JDK used for `JavaCompile`, depending on Gradle and provisioning setup.
- `options.release = 17` enforces the Java 17 source/API target.
- **Gradle daemon JVM** is a separate component; the Gradle version must support running on the daemon JVM.
- The IDE may need to re-import the model to reflect the exact Java level.

Reference commands:

~~~bash
./gradlew --version
./gradlew :service:compileJava
./gradlew :service:test
~~~

If Gradle is too old to run on the JDK chosen by the IDE as the Gradle JVM, failure can occur **before any compiler toolchain is selected**. Upgrade the build tool per its compatibility matrix; do not assume an old Gradle daemon runs on Java 21 just because JDK 21 is used for the toolchain.

### 12.1. Test runtime may differ from compiler toolchain

A project may need to run tests on both JDK 17 and JDK 21 to confirm a library still supports both. In Gradle, `Test` tasks can configure an appropriate `javaLauncher`; in Maven, inspect plugin test JVM/fork/toolchain settings.

Keep them distinct:

~~~text
compileJava  -> javac JDK 21, --release 17
testOn17     -> JVM JDK 17
testOn21     -> JVM JDK 21
production   -> min supported runtime from policy
~~~

Running tests only on Java 21 can miss a new dependency compiled for Java 21 while the artifact still promises Java 17 support.

### 12.2. IDE importing a Gradle project

The IDE can derive language levels from the Gradle model, yet module-specific overrides, generated sources, or mixed projects can carry custom setups. When the two environments diverge:

1. Confirm the Gradle Wrapper version in use.
2. Confirm the Gradle JVM.
3. Confirm the module's Java toolchain and `options.release`.
4. Re-import/sync the project via the IDE mechanism.
5. Check the actually imported module language level.
6. Run the module's compile task to verify the source is valid.

Do not manually tweak an SDK setting in the IDE and forget to sync with the build model, as the next import can overwrite that setting.

## 13. Multi-module projects: each module may need a different Java level

Example:

~~~text
root
 ├─ api-contract      Java 17 minimum
 ├─ shared-model      Java 17 minimum
 ├─ service-runtime   Java 21
 ├─ admin-ui-backend  Java 21
 └─ codegen-tools     JVM running the generator per tool support
~~~

`api-contract` and `shared-model` have consumers on JDK 17 and must preserve source/API/class-file target 17. `service-runtime` runs solely on Java 21 and may use Java 21 language features. `codegen-tools` depends on whichever JDK the generator and build plugin support.

Risks:

- Setting a shared root language level causes public library modules to emit Java 21 class files.
- A Java 17 module exposes public APIs using types introduced only in Java 21.
- Generated sources share a source set while the generator emits Java 21 syntax.
- The IDE assigns one language level project-wide and misreports modules.
- The test runner loads a newly built module inside an older JDK runtime.

Maintain a constraint table:

| Module | Source level | `--release`/target | Compiler JDK | Minimum runtime | Consumers |
| --- | --- | --- | --- | --- | --- |
| `api-contract` | 17 | 17 | 21 | 17 | External SDKs |
| `shared-model` | 17 | 17 | 21 | 17 | Multiple services |
| `service-runtime` | 21 | 21 | 21 | 21 | Internal |
| `codegen-tools` | Per tool support | Per tool support | Per build | Build-time | CI |

The values are illustrative; apply actual project policy. "A different language level per module" only makes sense when the dependency graph and runtime support allow the combination.

## 14. Java parsers in plugins have independent lifecycles

Many tools use parsers independent of the main compiler:

- **IntelliJ PSI**: source model for IntelliJ Platform inspections, navigation, and refactorings.
- **Eclipse JDT AST/ECJ**: Eclipse ecosystem analysis/tooling and compiler.
- **JavaParser**: Java parsing and AST representation library.
- **`javac` compiler tree API**: AST within compiler/tooling scope.
- **ANTLR grammars**: custom or grammar-generated parsers requiring grammar updates when new syntax appears.
- **Tree-sitter grammars**: parsers used in certain editors/tooling, with separate releases and support levels.
- **ASM/Byte Buddy/Javassist**: primarily bytecode analysis and manipulation rather than Java source parsers.

AST systems are not identical. An old plugin assuming every class declaration has a single node structure can mishandle `record` or `sealed class`. An outdated formatter may treat pattern `switch` as invalid tokens. Bytecode analyzers may reject unknown class-file versions.

### 14.1. Test parsers by feature, not solely by version number

There is no uniform "Java 21 parser" across libraries. Verify which features a parser version actually supports:

- Records.
- Sealed types and `permits`.
- Switch expressions and pattern matching.
- Text blocks.
- Record patterns.
- Preview syntax if enabled by the project.
- Javadoc/documentation comments and annotation forms.

For an internal plugin, minimum tests should cover each syntax feature actually present in the project's codebase. Do not create only `class Foo {}` and conclude the parser supports the new JDK.

### 14.2. Parsing successfully does not guarantee safe refactoring

A parser may construct a valid AST while a refactoring plugin still misbehaves if it:

- Fails to handle a new node type.
- Drops comments/formatting.
- Fails to resolve symbols accurately.
- Alters pattern variable semantics or scopes.
- Loses annotations/modifiers when rewriting source.

Therefore, when upgrading a plugin parser, test the full **read → transform → output** path across cases containing new syntax. A "does not crash" test does not prove code transformations are accurate.

## 15. New syntax and example parser errors vs. compiler errors

Consider Java 17:

~~~java
public sealed interface Payment
        permits CardPayment, CashPayment {
}

public record CardPayment(String token) implements Payment {
}

public record CashPayment(long amount) implements Payment {
}
~~~

An outdated analyzer may report:

~~~text
Unexpected token "sealed"
Unexpected token "record"
Could not parse Java source
~~~

If a JDK 17+ compiler with `--release 17` accepts this source, the defect lies in the analyzer/parser version. Follow this path:

1. Identify which tool emitted the diagnostic (IDE core, plugin, Checkstyle, PMD, formatter, compiler).
2. Confirm the target source level/release is valid.
3. Check the tool version and compatibility matrix.
4. Upgrade the tool/parser or switch to a release supporting the corresponding syntax.
5. Re-verify tool behavior, not just that it stopped throwing errors.

Do not disable all quality checks merely to get a passing build when one parser has not been upgraded. You may temporarily narrow scope or log a time-boxed waiver, with an assigned owner and remediation plan.

## 16. Static analysis: each tool has its own analysis model and limits

A Java project can involve multiple checking layers:

| Tool/group | Typical scope | What to check when upgrading JDK |
| --- | --- | --- |
| Checkstyle | Style rules on Java source | Whether parser understands new syntax; rule configuration compatibility |
| PMD | Source analysis and rules | Java language version/parser/ruleset |
| SpotBugs | Bytecode analysis | Class-file version and parser dependencies |
| Error Prone | Compiler-integrated analysis (`javac`) | Compiler JDK and plugin/tool version |
| Sonar analyzers | Source, bytecode, and quality rules per analyzer | Scanner, analyzer, and Java language support |
| Formatters | Rewriting source formatting | New syntax and output stability |
| IDE inspections | Source semantics inside the IDE | Compatible IDE/parser/plugin versions |

Not all parser failures have the same fix. Checkstyle/PMD may need a version upgrade or language-version setting, whereas SpotBugs may fail reading `.class` files due to bytecode version. Error Prone can depend heavily on the compiler JDK's internal `javac` APIs.

### 16.1. Do not only edit the `languageVersion` setting

If an older parser release lacks grammar rules for pattern `switch`, setting config to "Java 21" achieves nothing. The tool needs a release that implements support. Conversely, a tool that supports the syntax while the project still sets Java 8 mode can also reject valid code.

The right investigation flow is **tool version → parser capabilities → language-level setting → test source**.

### 16.2. Quality gates silently skipped despite a green build

During migration, a team might disable Checkstyle or PMD because a parser crashes, then run only `compileJava` to report completion. That silently degrades verification quality.

Specify explicitly which quality tasks must pass in CI, for example:

~~~text
compile
unit tests
integration tests
checkstyle / PMD
SpotBugs / bytecode analysis
formatter verification
generated-code validation
~~~

Whenever a tool must be paused temporarily, record the risk and re-enable milestone; never equate passing compilation with "all quality gates passed".

## 17. Formatters and codemods: faulty parsers can corrupt source across the repo

Formatters and codemods often **rewrite source files**, not just analyze them. Thus, risks go beyond a warning:

- An old formatter fails to recognize new syntax and rejects files.
- A plugin rewrites ASTs and drops comments or modifiers.
- A refactoring tool alters imports, pattern variable scopes, or generic types.
- An OpenRewrite/codemod recipe mismatches the library/framework version.
- Two different formatting tools fight back and forth in CI diffs.

### 17.1. Reproducible configuration

Best practices:

1. Pin formatter/recipe versions in the build.
2. Do not rely on one developer's local IDE plugin as the sole formatting authority.
3. Separate "upgrade formatter" commits from "logic change" commits whenever feasible.
4. Run the formatter on sample files with new syntax and inspect the diff.
5. Enforce formatting checks in CI with the exact approved tool and version.

Do not blindly run "format all" across the whole repository immediately after upgrading an IDE before verifying whether the new plugin changes output rules. Tens of thousands of formatting diff lines obscure real regressions.

### 17.2. Plugins accessing `javac` internals

Some formatters or compiler plugins access internal JDK compiler APIs. Switching JDKs can trigger `IllegalAccessError` or `NoSuchFieldError` even when Java syntax has not changed. This is a **tool/JDK API compatibility** issue, not simply a parser language-level issue.

Do not treat `--add-exports` or `--add-opens` as permanent substitutes for upgrading the tool. When temporary workarounds are unavoidable, track the internal API usage and a removal date.

## 18. Annotation processors and compiler-time generated code

Within "Code generation and testing tools", an important category is annotation processors such as Lombok, MapStruct, Dagger, AutoValue, and internal tools.

### 18.1. Processors are not IDE plugins

Annotation processors normally run inside the build/compiler or a matching processing pipeline. IDEs may support annotation processing directly or rely on plugins to display generated code in a specialized way.

Consequently, situations like these can arise:

- The IDE recognizes Lombok fields/getters while Maven compilation fails.
- Maven compiles because processors are configured, while the IDE flags missing methods because annotation processing is not enabled/imported.
- Old processors crash on a new `javac` due to `com.sun.tools.javac.*` dependencies.
- Generated sources compile cleanly while runtime dependencies required by generated APIs are missing.

### 18.2. MapStruct example

Source code:

~~~java
@Mapper
public interface OrderMapper {
    OrderDto toDto(OrderEntity entity);
}
~~~

The processor generates `OrderMapperImpl` at build time. If the IDE has not executed/updated the annotation processing model, it may not see the implementation or generated sources. If `javac` 21 runs an overly old processor, the error may live inside the processor rather than the interface above.

When taking inventory, track separately:

- Processor artifact and version.
- Annotation API/runtime artifact and version (if any).
- Compiler JDK.
- Build tool integration.
- Generated output directory.
- IDE annotation processing setup.
- Consumers of generated code.

Never edit `OrderMapperImpl.java` directly to work around errors, as the processor overwrites it on the next build.

## 19. OpenAPI, JAXB, and Protocol Buffers can emit code exceeding the language level

Contract-driven generators have their own tool versions and options. A pipeline may emit Java classes valid only in Java 21 while a public SDK module still requires Java 17.

Example code emitted by a newer template:

~~~java
// Template selects record; requires Java 16+.
public record OrderDto(String id, long totalCents) {
}
~~~

If the SDK still supports Java 11, this output is invalid. The bug lies in generator/template/model-style selection and target Java policy, not an "outdated IDE parser".

### 19.1. OpenAPI

Check:

- Generator/version and library template.
- Generated Java syntax and imports.
- `javax`/`jakarta` annotation family.
- JSON library and nullability/date mappings.
- Generated Java class/method names of the SDK.

### 19.2. JAXB/XJC

Check:

- XJC/plugin version and binding customizations.
- `javax.xml.bind` vs. `jakarta.xml.bind` API/runtime generation.
- Generated annotations and reflection/module access.
- XML schema/namespace compatibility.

### 19.3. Protocol Buffers/gRPC

Check:

- `protoc` version and Java code generator.
- `protobuf-java` runtime and gRPC plugin/runtime if used.
- Whether generated classes call APIs present on the minimum Java runtime.
- Java package/class layout alongside wire schema compatibility.

Changing generated Java APIs does not necessarily change the wire format, and vice versa. Both directions must be tested according to product requirements.

### 19.4. Rule for generated directories

Do not hand-edit files under `build/generated` or `target/generated-sources`. Update schemas, generator options, templates, or JDK targets, then regenerate from clean. If custom logic is needed, place adapters/hooks in hand-written sources.

## 20. Preview features: a special compatibility axis

Some language features ship in **preview** in a Java release before being finalized or changed. Preview status is not a promise that syntax/APIs will remain unchanged across subsequent releases.

When using preview features:

- The compiler must match the JDK release supporting that preview.
- The build must enable preview and select matching source/release flags per compiler rules.
- Tests/runtimes must enable preview when running bytecode that requires it.
- IDEs/parsers/plugins must understand preview syntax for the exact release in use.
- CI and production runtimes must stay consistently configured.

Example on the JDK offering preview features for that exact release:

~~~bash
javac --enable-preview --release 21 -d out Example.java
java --enable-preview -cp out Example
~~~

This command only illustrates enabling preview for a **Java 21 preview feature**; not all Java 21 syntax requires preview. For example, pattern matching for `switch` was finalized in Java 21 and needs no preview flags just to use that standard feature.

### 20.1. Do not "enable preview language level" to dodge unrelated errors

If an outdated Checkstyle parser fails on `record`, which is already a standard feature, turning on preview will not fix missing parser support. If a bytecode parser dependency does not recognize a new class-file major version, enabling preview in the IDE will not help either.

Preview features represent a product decision carrying version-lock risk and must be tracked separately; never treat preview as a global "enable all syntax" toggle.

### 20.2. Standardized features can still require IDE updates

When a feature progresses from preview to final, syntax and semantics can change between releases. A plugin that once supported a preview version may not handle the final syntax properly. Identify the **exact version of the feature** rather than merely claiming "the plugin supports pattern switch".

## 21. Parser errors and bytecode version errors: two distinct error families

### 21.1. Source parser errors

Examples:

~~~text
Unexpected token: record
Parse error at "case String s ->"
Java language level 11 does not support sealed types
~~~

These errors usually point to the source language level or an outdated parser. Identify which tool emitted the message before modifying source code.

### 21.2. Bytecode reader errors

Example:

~~~text
Unsupported class file major version 65
~~~

Class-file major version 65 corresponds to Java 21. When this appears inside ASM, JaCoCo, a mocking framework, or a plugin, the tool or its embedded bytecode parser may not yet support the new class-file format.

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |

When failure stems from the **JVM runtime** loading a newer class than it supports, it often throws `UnsupportedClassVersionError`. When failure comes from a **bytecode-parsing library**, it typically throws a library-specific exception. Fixes differ:

- Runtime JVM lower than class-file target → select a compatible runtime or compile with a lower `--release`.
- Outdated ASM/Byte Buddy/coverage parser → upgrade the tool/library per compatibility matrix.
- Transitive JAR exceeding minimum Java version → review dependency versions and artifact release targets.

Do not simply change "Project SDK" in the IDE to dodge an error coming from a bytecode parser inside an agent running in the test JVM.

## 22. Test runners, mocking, and coverage are Java analysis tools too

A migration can pass source compilation yet fail during `test`:

- The JUnit engine/plugin fails to start or discovers incomplete tests.
- Mockito/Byte Buddy instrumentation does not support the class-file version or JDK behavior.
- The coverage agent/JaCoCo cannot analyze new class files.
- A test framework relying on deep reflection hits access restrictions.
- The IDE test runner uses a different JVM from the Maven/Gradle runner.
- Preview bytecode was compiled while the test JVM omits preview flags.

### 22.1. Distinguishing test-only blockers from production blockers

An error in Mockito/coverage during unit tests does not by itself prove the production runtime is incompatible. However, broken test infrastructure means the team lacks quality evidence to ship. Classify accordingly:

| Category | Scope | How to handle |
| --- | --- | --- |
| Build blocker | Cannot compile | Inspect compiler/toolchain/processors |
| Test tooling blocker | Test runner/agent/analyzer fails | Upgrade the right test dependency/tool |
| Runtime blocker | App fails to start/load dependencies | Inspect JDK/module/runtime paths |
| Behavioral regression | App runs yet produces wrong results | Run contract tests and check non-compiler changes |

Do not disable all unit tests simply to declare migration complete. If a test runner needs upgrading, treat it as a tracked dependency inside the cutover plan.

### 22.2. IDE test runtime is not always the CI test runtime

For example, the IDE uses JDK 21 to run JUnit while the Gradle test task is configured to run on JDK 17. Tests loading Java 21 classes can pass in the IDE and fail in CI. Compare the executed test JVM, classpath, and build outputs rather than trusting a green bar in one IDE.

## 23. Classifying failures before changing configuration

| Symptom | Where to check first | What not to do immediately |
| --- | --- | --- |
| IDE shows red errors, terminal `javac` passes | IDE/module language level, parsers, plugins, sync | Rewrite valid code for an old parser |
| IDE is green, CI reports `release version not supported` | Actual compiler JDK and `--release` | Merely bump IDE Project SDK |
| Checkstyle reports syntax error on `record` | Checkstyle version/parser settings | Turn off all rules |
| Formatter crashes on pattern switch | Formatter/parser version | Reformat whole repo with another tool |
| `Unsupported class file major version 65` | Which JVM or ASM/Byte Buddy/agent reported it | Randomly change source compatibility |
| Lombok fails on `javac` internals | Lombok/processor version and compiler JDK | Hand-edit generated getters |
| IDE misses `MapperImpl` | Annotation processing model/output | Commit a temporary implementation |
| Gradle fails to start on new JDK | Gradle Wrapper/daemon JVM support | Only set toolchain = new JDK |
| Runtime `NoClassDefFoundError` | Resolved runtime dependencies/modules | Only wipe IDE caches |
| OpenAPI generated imports are wrong | Generator template/options/runtime APIs | Find-and-replace in generated directory |
| Protobuf generated code calls missing runtime method | `protoc`/`protobuf-java` version alignment | Arbitrarily add JARs to silence errors |
| JUnit passes in IDE, fails in CI | Test JDK, classpath, agents | Blame IDE differences without verification |

This is an initial triage guide, not a substitute for stack traces and real environment facts. An exception can originate across multiple layers; confirm **which tool failed first**.

## 24. Minimum diagnostic command set

A team can capture the output of the commands below in real environments during migration:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

For Gradle:

~~~bash
./gradlew :module:compileJava
./gradlew :module:test
./gradlew :module:dependencies --configuration testRuntimeClasspath
~~~

For Maven:

~~~bash
mvn help:effective-pom
mvn test
mvn dependency:tree
~~~

For bytecode:

~~~bash
javap -verbose -classpath build/classes/java/main \
    com.example.Main
~~~

Check the `major version: ...` line to determine the class-file level. On Windows, path syntax and classpath separators differ from Unix shell examples; adapt to the shell and JDK in use.

### 24.1. Goal when recording evidence

Include alongside:

- Commit/hash of source and build configuration.
- Actual JDK distribution/version.
- IDE release and plugin versions.
- Build tool, compiler, parser/analyzer/formatter versions.
- Module source/release targets.
- Command and exit code.
- Failing file/source construct.
- First stack trace, not merely a summary.

For transitive dependencies, check the actually resolved version using `dependencyInsight` (Gradle) or `dependency:tree` (Maven). Do not treat a declared number in a build file as sole proof.

## 25. Walkthrough example: IDE rejects Java 21 syntax

Hypothetical scenario:

~~~text
Module:     search-service
Source:     pattern matching for switch
Gradle:     Java toolchain 21, --release 21
CLI build:  success
IDE:        parser error at case String s
~~~

Steps:

1. Use the module's compiler task to confirm Java 21 source is accepted.
2. Check the IDE project/module language level.
3. If already 21, determine whether the message comes from IDE core or an inspection plugin.
4. Check whether the IDE build and plugin versions support final Java 21 syntax.
5. Sync/re-import the Gradle project model if IDE settings drifted.
6. Reproduce with a minimal source file containing pattern `switch` to separate plugin behavior from business code.
7. After updating the IDE/plugin, re-verify navigation, refactoring, and formatter actions on that file.

Do not rewrite valid Java 21 code into `if-else` chains merely to satisfy an old parser if the product has officially adopted Java 21. Conversely, if the module genuinely must support Java 17, the compiler release target governs how the source must be written.

## 26. Walkthrough example: generated source exceeds Java release target

Scenario:

~~~text
Module:         client-sdk
Minimum Java:   11
Compiler JDK:   21
--release:      11
Code generator: new template using record
Build result:   compilation error
~~~

Generated file:

~~~java
public record ApiResponse(String code, String message) {
}
~~~

This is not an IDE "not understanding record" issue: the compiler rightly rejected syntax absent from Java 11. The layer to fix is the source generator/template or the SDK's minimum Java policy.

Options:

- Choose a generator/template emitting Java 11-compatible POJOs.
- Use a generator version verified with Java 11.
- If intentionally raising SDK minimum runtime to Java 17/21, announce the breaking support change and test with consumers.

Never patch generated Java after every build; make the generation pipeline respect the contract from the start.

### 26.1. If compiler passes yet older runtime still fails

Check whether generated code references runtime libraries compiled for a higher Java release. `--release 11` does not automatically guarantee external library JARs only target Java 11. Changing runtime library versions or intentionally raising the minimum runtime may be required.

## 27. Walkthrough example: formatter or static analyzer breaks after JDK upgrade

A service uses records and sealed classes, JDK 17 compiles normally, yet `checkstyleMain` reports:

~~~text
ParseException: unexpected token "record"
~~~

Remediation steps:

1. Identify which Checkstyle version the plugin/build resolved.
2. Cross-check release notes for Java 17 syntax support.
3. Check whether the Gradle/Maven plugin uses the expected analyzer version.
4. Upgrade the analyzer and plugin integration if needed, keeping the ruleset explicit.
5. Re-run the analyzer across both new and existing files.
6. Review rule changes unrelated to syntax to avoid quietly lowering standards.

If upgrading the analyzer alters violation counts due to rule behavior changes, separate "tool/parser updated" from "coding standard changed" so each is evaluated clearly. Do not treat every new warning as a JDK error.

## 28. Walkthrough example: test plugin fails to understand class-file version

Scenario:

~~~text
compileJava: success
test:        fails before tests execute
message:     Unsupported class file major version 65
stack:       coverage/mocking/bytecode library
~~~

Because Java 21 emits class-file major 65 when targeting 21, an older bytecode parser inside a coverage or mocking tool may fail to read it. Actions:

1. Confirm the offending class file's major version via `javap -verbose`.
2. Identify the first tool parsing that class (ASM, agent, Byte Buddy, framework).
3. Cross-check vendor-supported versions.
4. Upgrade the matching test dependency/agent rather than arbitrarily overriding a transitive engine outside the support matrix.
5. Re-run discovery, tests, coverage, and integration suites.

If the stack trace shows `UnsupportedClassVersionError` from a JDK 17 JVM trying to load class-file 65, the fix is running on JDK 21 or building the artifact for Java 17 if required by contract. Both mention "class-file version", yet belong to different layers.

## 29. Workspace settings are not the sole source of truth

A repository can contain:

~~~text
.idea/
.settings/
.classpath
.project
.vscode/settings.json
build.gradle / build.gradle.kts
pom.xml
gradle.properties
gradle/wrapper/...
.mvn/wrapper/...
CI pipeline configuration
Dockerfile
~~~

These files have different purposes and scopes; some hold personal developer preferences while others define shared build configuration.

Principles:

- **Build files and toolchains** should describe the official compilation contract.
- **IDE settings** should help developers import and analyze that exact contract.
- **CI** must use reproducible toolchain versions.
- **Runtime images** must reflect production Java support policy.
- **Generated source directories** must be clearly governed by the build rather than depending on IDE cache state.

Do not commit developer-local absolute JDK paths into team configurations. Replace them with toolchains, environment variables, or portable IDE configurations wherever possible.

### 29.1. Mind IDE caches

Corrupted caches/indexes can cause false warnings. However, clearing caches should happen only **after** confirming the project SDK, module language level, parser/plugin support, and build import. If a plugin genuinely lacks Java 21 support, clearing caches a hundred times will not add grammar rules to its parser.

## 30. Practice designing a support matrix

A matrix should separate **syntax support**, **compiler support**, and **runtime/test support**:

| Component | Current | Target | Required evidence |
| --- | --- | --- | --- |
| IDE core | Current version | Release supporting target Java syntax | Source insight/inspection tested on real features |
| IDE plugins | Old plugin versions | Versions supporting IDE/JDK | Plugin compatibility notes and tests |
| Parser libraries | JavaParser/JDT/ANTLR/other | Version parsing project syntax | Parser fixtures, transformation tests |
| Gradle/Maven | Current Wrapper | Version running on build JVM | Official compatibility matrix, clean build |
| Java compiler | Current JDK | Target toolchain | Compilation with proper `--release` |
| Annotation processors | Lombok/MapStruct/custom | Version supporting compiler | Generated code compiles + runtime behavior |
| Formatters/static analyzers | Current tool version | Parser/rules supporting language level | Full quality tasks execute |
| Test tooling | JUnit/Mockito/coverage | Version supporting class files | Test discovery, execution, coverage |
| Runtime dependencies | Application/SDK libs | Version matching minimum Java | Runtime smoke/integration |
| Production JVM | Current image | Approved JDK runtime | Deployment and startup tests |

Do not mark "SUPPORTED" merely because a library threw no errors in one unit test. Distinguish:

- **Vendor-supported:** vendor docs publish support for the combination.
- **Observed working:** passed a defined test suite.
- **Untested:** no evidence yet.
- **Known incompatible:** documented limitation/issue or reproducible failure.

For every risk cell, assign an owner, upgrade plan, and priority. The goal is a mutually supported combination of versions, not upgrading every plugin blindly to newest.

## 31. Stepwise upgrade approach

### Phase 1: Lock down the baseline

Record JDKs, build tools, IDEs, plugin versions, parser libraries, source/release targets, and existing test/quality tasks. Keep a small source fixture containing language syntax the project actually uses.

### Phase 2: Update toolchain/build

Select a Gradle/Maven version able to run on the target build JVM. Verify the compiler toolchain, `--release`, and test JVM. Avoid changing source syntax and framework major versions simultaneously if avoidable.

### Phase 3: Update the IDE and parser ecosystem

Choose IDE releases and plugin versions matching the language level. Upgrade source analyzers, formatters, compiler extensions, and annotation processors per the compatibility matrix.

### Phase 4: Regenerate code cleanly

If using OpenAPI/JAXB/Protobuf or annotation processing, eliminate reliance on stale generated sources via a clean generation pipeline. Review generated API/behavior differences; never hand-edit generated files.

### Phase 5: Test across layers

Run compilation, unit tests, integration tests, static analysis, formatting, coverage, runtime smoke checks, and tests on the minimum supported Java runtime. Verify source APIs, bytecode compatibility, and behavior independently.

### Phase 6: Deploy and monitor

Ensure containers/runtimes/JVM flags/agents match the tested environment. Monitor startup, exceptions, coverage, latency, and relevant business metrics. Keep rollback or roll-forward plans ready if generated APIs or data formats changed irreversibly across runtimes alone.

## 32. Checklist to avoid confusing "green IDE" with "build-ready"

- [ ] Identified the JDK running the IDE/language server separately from the Project SDK.
- [ ] Recorded the exact language level of each module.
- [ ] Identified the compiler JDK, `--release`, and minimum runtime.
- [ ] Confirmed Gradle/Maven wrapper supports the intended build JVM.
- [ ] Imported Maven/Gradle model properly in the IDE rather than configuring SDKs manually alone.
- [ ] Confirmed IDE core/parsers support the Java syntax in use.
- [ ] Confirmed internal and external IDE plugins support corresponding AST/PSI/JDT APIs.
- [ ] Verified Checkstyle/PMD/formatters/other source analyzers parse new syntax.
- [ ] Verified SpotBugs/ASM/Byte Buddy/coverage tools understand emitted class-file versions.
- [ ] Confirmed annotation processors work with the new compiler without depending on changed internal APIs.
- [ ] Ensured generated sources come from pinned schema/tool/template versions.
- [ ] Verified generated code does not exceed the module's language level.
- [ ] Confirmed runtime libraries for generated code match the target JDK/framework.
- [ ] Enabled preview features (if used) consistently across compiler, IDE, and tests/runtime.
- [ ] Kept unit tests and quality tasks active instead of skipping them for a green build.
- [ ] Tested on the minimum Java runtime if supporting multiple JDKs.
- [ ] Avoided hand-editing generated files to hide toolchain errors.
- [ ] Confirmed class-file major versions of critical artifacts.
- [ ] Ran integration tests on production runtime images and agents.
- [ ] Documented minimum Java requirement changes or generated public API changes in release notes.

This checklist is a migration planning aid and does not substitute for verifying compatibility of each tool at its exact version.

## 33. Common misconceptions

**"Once JDK 21 is installed, the IDE automatically understands all Java 21 syntax."** False. IDE parsers, language servers, and plugins require supporting versions, and the module must set the proper language level.

**"IDE red errors mean `javac` is guaranteed to fail."** False. Diagnostics may come from an outdated plugin parser or stale IDE model. Run the official compiler with the target configuration.

**"Green IDE means the artifact works on Java 17."** False. You need `--release`/bytecode/API compatibility and Java 17 runtime tests if Java 17 is supported.

**"Gradle toolchain = 21 means the Gradle daemon also runs on Java 21."** False. Toolchain and the JVM running Gradle are two separate mechanisms; check the Gradle Java compatibility matrix.

**"Upgrading the compiler automatically upgrades Checkstyle/formatters/parsers."** False. Tools have independent releases and parsers.

**"Setting the parser config to Java 21 makes old plugins understand all new syntax."** Incorrect if the parser implementation lacks grammar for that syntax.

**"Class-file major errors are always caused by `javac`."** Incorrect. They can stem from an older JVM or an unsupported bytecode analyzer/agent.

**"Just add `--enable-preview` and every new syntax feature works."** False. Preview depends on specific releases; many features are finalized without preview, and old parsers still require upgrades.

**"If generated code fails to compile, edit the generated file directly."** Wrong in code-regeneration pipelines. Fix schemas, options, templates, or runtime/tool versions instead.

**"Changing IDE plugins never alters refactoring outputs."** Not guaranteed. Plugins may traverse ASTs differently and emit wrong code; test transformations.

**"Passing unit tests is enough; no need to run Checkstyle, PMD, or coverage."** False if those are project quality gates. Migrations must preserve them or follow an approved policy change.

**"If one Java 21 module runs fine, every library in the repo can be released for Java 17."** False. Each artifact has its own bytecode, API dependencies, and minimum runtime.

## 34. Technical documentation to cross-reference

When implementing in practice, consult documentation for the exact release rather than extrapolating from another version:

- **Java Language Specification (JLS):** grammar and semantics of each Java release.
- **`javac` Tool Guide:** `--release`, `--enable-preview`, source/target options, and compiler toolchains.
- **Java Virtual Machine Specification:** class-file formats and version support.
- **Gradle Java Compatibility Matrix and Toolchains documentation:** JVM running Gradle vs. compiler toolchain.
- **Maven Compiler Plugin and Maven Toolchains documentation:** release targets, plugin versions, and compiler JDKs.
- **IntelliJ IDEA Java support/SDK/language level documentation:** project/module SDKs, Gradle/Maven import, plugin compatibility.
- **Eclipse JDT/ECJ and Buildship/m2e documentation:** compiler compliance, Installed JREs, and AST support.
- **VS Code Java Extension documentation:** Java runtimes, language servers, and project configuration.
- **Checkstyle, PMD, SpotBugs, Error Prone, and formatter release notes:** supported parser/bytecode/compiler levels.
- **OpenAPI Generator, JAXB/XJC, Protocol Buffers/gRPC Java documentation:** generators, generated sources, and runtime version compatibility.
- **JUnit, Mockito/Byte Buddy, JaCoCo documentation:** test runners, instrumentation, and class-file support.

For fast-moving tools, obtain **exact version numbers and support matrices** from vendor documentation at upgrade time; never write down a single version as universally right for every project.

## 35. Conclusion

IDE plugins, parsers, and language levels are an essential part of Java compatibility migration. A Java file is analyzed by multiple toolchains before execution: the IDE parser, inspection/refactoring plugins, compiler, annotation processors, formatters, bytecode analyzers, test agents, and finally the JVM. Each layer carries its own version and support contract; therefore, "red IDE yet green build" or "green IDE yet red CI" can occur without contradiction.

To handle this properly, **separate the JDK running the IDE, the project SDK, the module language level, the compiler toolchain, `--release`, and the test/runtime JVM**. Inventory plugin/parser versions, synchronize the project model with Maven/Gradle, pin generators and runtime dependencies, and verify with real syntax samples alongside clean builds and contract tests. When errors happen, pinpoint the first failing tool before altering code or bumping versions blindly.

A successful migration does more than let sources compile on a new JDK. It ensures the IDE interprets source code accurately, plugins analyze and refactor safely, generated code stays within minimum Java constraints, quality gates and test infrastructure keep functioning, and the final artifact runs properly on every runtime committed by the product.
