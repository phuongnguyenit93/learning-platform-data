# Applying `javac -Werror` and Building an Appropriate Warning Policy

## 1. Why Do Warnings Need a Policy?

`javac` emits an **error** when a program cannot compile validly and may emit a **warning** when code still compiles yet harbors risks, uses old APIs, performs unsafe type operations, has suspicious compiler configurations, or contains constructs needing review. For example: using raw generic types, unchecked conversions, APIs marked deprecated, APIs scheduled for removal, and accidental switch fall-through.

If warnings are treated merely as log lines, a large codebase easily accumulates thousands of warnings. At that point, the development team cannot distinguish notable new warnings from old ones. `-Werror` allows turning **warnings emitted by the compiler into compilation errors**, thereby bringing quality policy into builds and CI.

However, `-Werror` itself does not decide which warnings should be emitted. It works together with `-Xlint` and other compiler options. A sustainable policy needs to answer:

1. Which warning groups need to be enabled, and which need immediate handling?
2. Which modules or source sets fall within the enforcement scope?
3. What should be done with old warnings when starting rollout?
4. When is suppression allowed, who is responsible, and when will it be reviewed?
5. How can JDK, Maven/Gradle, annotation processors, and CI avoid producing different results?

**The goal** is to keep the stream of new changes from introducing new meaningful warnings, while handling old warnings on a clear roadmap. You should not force an entire project to immediately reach `-Xlint:all -Werror` if doing so only leads to turning off all warnings or adding suppressions indiscriminately.

## 2. Distinguishing `-Werror`, `-Xlint`, `-nowarn`, and Diagnostics

| Option | Effect |
| --- | --- |
| `-Werror` | Turns the presence of any warning emitted by the compiler into a **compile error**; can also apply to warnings outside lint categories. |
| `-Xlint` | Enables lint warnings recommended by the `javac` version. |
| `-Xlint:all` | Enables all lint categories supported by the current compiler version. |
| `-Xlint:deprecation,unchecked` | Enables the specified warning groups. |
| `-Xlint:all,-deprecation` | Enables all lint categories except the `deprecation` group. |
| `-Xlint:none` or `-nowarn` | Disables the corresponding lint warnings; other diagnostics may still appear, depending on the compiler. Should not be used to hide issues. |
| `-Xmaxwarns 100` | Limits **the number of printed warnings**, not a budget of allowed warnings. |
| `-Xdiags:verbose` | Displays detailed diagnostics, helping understand related symbols/types. |

Example enabling warning groups directly related to Java source:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation,removal,unchecked,rawtypes \
  -Werror -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

This is a command for **Bash**; the `\` at the end of a line is the shell line-continuation character. On PowerShell/cmd, all parameters can be placed on a single line.

**Mechanism:** `-Xlint` selects checking groups and emits warnings, `-Werror` causes the invocation to fail if any emitted warning remains. `-Werror` does not fix code itself, does not detect all logic issues itself, and does not turn every `Note:` into an error.

Some warnings are enabled by default even without writing `-Xlint` (depending on the `javac` version), so a project can still fail with `-Werror` alone. Conversely, many issues appear as specific warnings only when selecting `-Xlint:<category>`.

Check the list of categories actually supported by the compiler on your machine:

~~~bash
javac --help-lint
javac --help
javac -version
~~~

Do not copy a category from a newer JDK if the project's compiler does not yet support it. The list of lint categories can expand with JDKs; `-Xlint:all` may therefore emit more warnings after upgrading a toolchain.

## 3. Experiment: Normal Warnings, `-Werror`, and Exit Codes

Create two UTF-8 source files in the structure:

~~~text
project/
  src/demo/LegacyApi.java
  src/demo/WarningDemo.java
  out/
~~~

**`src/demo/LegacyApi.java`:**

~~~java
package demo;

public final class LegacyApi {
    @Deprecated(since = "17", forRemoval = false)
    public static String legacy() {
        return "old";
    }

    public static String modern() {
        return "new";
    }
}
~~~

**`src/demo/WarningDemo.java`:**

~~~java
package demo;

public final class WarningDemo {
    public static void main(String[] args) {
        System.out.println(LegacyApi.legacy());
    }
}
~~~

The two files above are valid Java 17 code. The `@Deprecated` annotation declares that the `legacy()` method is old, yet not necessarily scheduled for removal. The method can still be called, so the compiler may emit a warning instead of a syntax or type error.

### 3.1. Without enabling detailed lint

In the `project` directory, create the `out` directory and run:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
java -cp out demo.WarningDemo
~~~

With the tested `javac 24.0.2`, compilation **succeeds (exit code 0)**; the compiler prints short messages like:

~~~text
Note: .../WarningDemo.java uses or overrides a deprecated API.
Note: Recompile with -Xlint:deprecation for details.
~~~

The `...` in the two lines above represents a system-dependent specific source path. **This is an illustrative diagnostic excerpt**, not a command or path to copy verbatim. Stdout when running the application:

~~~text
old
~~~

Do not infer that every `Note` is a warning counted by `-Werror`. In this case, the compiler is merely reminding you to enable `-Xlint:deprecation` to see the detailed location.

### 3.2. Enabling `-Xlint:deprecation` without `-Werror` yet

~~~bash
javac --release 17 -encoding UTF-8 -Xlint:deprecation \
  -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

Key output:

~~~text
WarningDemo.java:5: warning: [deprecation] legacy() in LegacyApi has been deprecated
        System.out.println(LegacyApi.legacy());
                                    ^
1 warning
~~~

The line containing the absolute path may differ. `javac` still returns **exit code 0** and generates class files because the compiler has not been instructed to treat warnings as errors.

### 3.3. Enabling `-Werror` as well

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation -Werror -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

With `javac 24.0.2`, the end of the diagnostic:

~~~text
warning: [deprecation] legacy() in LegacyApi has been deprecated
error: warnings found and -Werror specified
1 error
1 warning
~~~

The command returns **exit code 1**. The offending code itself is still valid; it is the **warning policy** that caused the compile task to fail. This is the signal that shells, Maven, Gradle, and CI can use to stop a build.

**Watch out for stale artifacts:** after a failed compilation, the `out` directory may still hold `.class` files from a previous successful build. Do not run `java -cp out ...` and treat the running application as proof that the `-Werror` run just succeeded. When needing exact proof, compile into a fresh output directory and check the exit code.

### 3.4. Why does disabling deprecation let `-Werror` pass?

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:all,-deprecation -Werror -d out \
  src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

With **the two files above**, `javac 24.0.2` returns exit code **0** even though it may still print a `Note` about deprecated APIs, because the deprecation warning was not emitted as a lint warning. This illustrates the `-Xlint:all,-deprecation` syntax, **not a recommendation** to turn off deprecation across an entire project. If there are warnings in other categories, `-Werror` still fails compilation.

## 4. Lint Categories to Understand Before Choosing a Policy

Each group has a different impact; not every warning has the same priority level.

| Category | What Does It Warn About? | Usually Appropriate Handling |
| --- | --- | --- |
| `unchecked` | Generic conversions/calls without enough runtime type-safety checks | Use proper generic types, isolate legacy adapters, validate casts |
| `rawtypes` | Using raw generic types like `List` instead of `List<String>` | Declare type parameters or `List<?>` if only an unknown type is needed |
| `removal` | Referencing an API with `@Deprecated(forRemoval=true)` | Prioritize planning an API replacement, as removal risk is high |
| `deprecation` | Using a deprecated API (not necessarily for removal) | Find a replacement API; document temporary reason if not yet fixable |
| `serial` | Issues with serializable classes, such as missing `serialVersionUID` | Define serialization contract, add appropriate UID if needed |
| `fallthrough` | `switch` statement having a suspicious branch continuing to the next case | Add `break`, `return`, or document intent according to appropriate conventions |
| `cast` | Unnecessary cast | Remove meaningless casts |
| `try` | Notable `try` / try-with-resources constructs | Verify resource closing and semantics |
| `options` | Inconsistent or potentially wrong compiler options | Fix compiler flags/toolchain, e.g. using `--release` |
| `processing` | Issues during annotation processing | Check annotation processor path, supported versions, options |
| `path` | Invalid path elements | Fix incorrect classpath/sourcepath/module path |
| `exports`, `module` | Issues related to APIs exported from modules or the module system | Review module descriptors and public APIs |

`deprecation` and `removal` should not be merged into a single item: an API that is deprecated yet maintained for years has a different urgency than an API marked to be removed. When using `@SuppressWarnings`, the suppression key must also match the actual warning kind.

Not every category exists in every JDK. For example, the list expands with additional check groups across compiler releases. Use `javac --help-lint` of the actual toolchain and document the minimum version the project supports.

## 5. Classifying Handling Levels by Risk

A practical policy can divide warnings into tiers by risk and fixability:

| Group | Examples | Recommended Action |
| --- | --- | --- |
| **Block immediately on new code** | `unchecked`, `rawtypes`, `removal` in owned modules | Fix directly or have a reviewed local suppression; build fails if the warning is enabled and remains |
| **Needs handling yet transitional** | `deprecation` from third-party APIs, `serial` in legacy code | Record cause, scope, and deadline; prevent new warning count from increasing |
| **Configuration/environment** | `options`, `path`, `processing` | Adjust build, compiler JDK, processor path; do not hide via suppressions in source |
| **Generated/external code specific** | Sources produced by generators or template code outside edit control | Fix generator, isolate compile task, or manage a clearly scoped exception |

This is **a policy template**, not an official severity table defined by `javac`. Priority levels should reflect project type: public API libraries are sensitive to deprecation and binary compatibility; internal applications may prioritize generic/serialization errors; large systems using annotation processing need to watch processor warnings.

**Do not use `-Werror` as the sole quality metric.** Compiler warnings do not replace tests, static analyzers (Error Prone, SpotBugs, Checkstyle...), security scans, or reviews. Conversely, tools outside the compiler have their own "warning/error" levels and failure flags, not necessarily governed by `javac -Werror`.

## 6. A Rollout Roadmap That Does Not Paralyze CI

### Phase A — Observe Before Blocking

- Lock down **compiler JDK and `--release`**. Use the same toolchain locally and in CI to avoid differences in warning categories.
- Enable a useful lint set, e.g. `-Xlint:deprecation,removal,unchecked,rawtypes`, **without adding `-Werror` yet**.
- Run a **clean compile** and collect diagnostics: category, file/line, module, owner, fixability. Do not just count total `Note`s or lump every log line containing the word warning.
- Identify warnings belonging to team-owned code, generated sources, dependencies/plugins, or compiler configuration.
- Prioritize fixing clear, low-cost, high-impact warnings.

### Phase B — Block New Warnings in a Narrow Scope

Start with a clean module or well-controlled source set, and enable `-Werror` for that exact compile task. If an entire module still has old warnings, you cannot just add `-Werror` and allow "N warnings": **`javac -Werror` is a fail-if-any-warning mechanism, not supporting a numeric warning budget**.

A baseline-comparison dashboard may temporarily allow the existing warning count without increases, yet that log/baseline comparison mechanism must be implemented **outside `javac`**, and compiler/output format must remain stable. Another option is fixing old warnings, splitting modules/tasks, or using justified suppressions. Avoid hiding an entire category across the whole codebase just to pass CI.

### Phase C — Expand and Maintain

Once a module is clean:
- Enable `-Werror` mandatorily in CI and with the same configuration when running locally.
- Expand sequentially to remaining modules, in priority order.
- Monitor warnings when upgrading JDK/compiler plugins and annotation processors.
- Review new suppressions as technical changes with a reason and expiration.
- Run clean builds periodically; incremental compilers may not recompile all sources on every run.

An effective policy needs **ownership**: who fixes warnings in code, who updates generators, who handles build flags, and who approves exceptions. If new warnings begin appearing after a JDK upgrade, the build team must determine whether the new compiler detected a real risk or whether toolchains are out of sync.

## 7. Properly Scoped Suppression: `@SuppressWarnings`

`@SuppressWarnings` is a way to tell the compiler a warning category may be ignored **within the annotated declaration scope**, if the compiler supports that category.

Example of a valid legacy adapter:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SuppressDemo {
    @Deprecated
    static String legacy() {
        return "old";
    }

    @SuppressWarnings("deprecation")
    static String permittedUntilMigrated() {
        return legacy();
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> oldApi() {
        List raw = new ArrayList();
        raw.add("x");
        return raw;
    }

    public static void main(String[] args) {
        System.out.println(permittedUntilMigrated() + ":" + oldApi().get(0));
    }
}
~~~

Save the file `SuppressDemo.java` and run:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation,rawtypes,unchecked -Werror \
  SuppressDemo.java
java SuppressDemo
~~~

With **`javac 24.0.2`** and this source, the compiler returns **exit code 0**, stdout:

~~~text
old:x
~~~

Explanation: warnings are suppressed only where permitted; suppressing does not make `legacy()` stop being deprecated or make raw `List` type-safe. Here raw/unchecked code is intentionally isolated in one method; if data or casts from an external API are uncontrolled, suppressing may hide a real `ClassCastException`.

Good practices:
- Place `@SuppressWarnings` on **the smallest method, local variable, or declaration** the compiler permits and explain why it is safe.
- Add a comment explaining the reason and the condition for removing suppression; it is not necessary to attach it to an entire class/package.
- Check the exact warning key in the diagnostic, such as `[unchecked]`, `[deprecation]`, or `[removal]`.
- Prioritize fixing the root cause first: use generics, update APIs, fix compiler options; suppression is only an intentional exception.
- Do not assume every warning can be suppressed with an annotation: `options`, `path`, `processing`, and invocation-level configuration diagnostics have a different scope and must be handled in the build.

An exception example should include an appropriate note such as: "Compatibility adapter for old version of library X; type-checked at boundary; will be removed when upgrading the library per tracked issue". There is no need to invent a custom annotation or internal mechanism when Java's `@SuppressWarnings` suffices.

## 8. `-Werror` with `-Xlint:all`: When Useful, When Too Strict?

The configuration:

~~~bash
javac --release 17 -Xlint:all -Werror -d out src/demo/LegacyApi.java src/demo/WarningDemo.java
~~~

makes every enabled lint warning a build-failure reason. Advantage: new programs or clean modules maintain broad standards. Drawback: after a JDK upgrade, `-Xlint:all` may add new warning types (or change emission conditions), causing builds to fail on unchanged code. Warnings from annotation processing or module metadata can also be hard to fix all at once.

Operational solutions:
- Use **controlled** toolchain versions, upgrade on a plan, and check breaking changes.
- For already-clean codebases, `-Xlint:all -Werror` can be used and policies adjusted when the JDK changes.
- For large transitioning codebases, start with an **explicit category allowlist**, such as `-Xlint:deprecation,removal,unchecked,rawtypes -Werror`.
- If a category is genuinely unsuitable project-wide, consider `-Xlint:all,-<category>`; document the reason and ensure high-risk groups are not dropped.
- When a warning is a bug in an external generator/plugin, prioritize updating the generator or adjusting the right compile task instead of turning off all warnings.

**Note:** `-Werror` can fail because of warnings outside the categories listed in `-Xlint`. Enabling only a few lint categories **does not guarantee** that is the complete list of every reason a build may fail. Read the actual diagnostic and place policies at the appropriate compiler/task level.

## 9. Configuring Maven Compiler Plugin

For a Maven project targeting Java 17, an example configuration snippet in `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
                <showWarnings>true</showWarnings>
                <failOnWarning>true</failOnWarning>
                <compilerArgs>
                    <arg>-Xlint:deprecation,removal,unchecked,rawtypes</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

This is a **snippet of an existing POM**, not a standalone POM. Version `3.14.1` is an example for the 3.x plugin line; check the plugin/toolchain version your project uses when deploying.

- `<failOnWarning>true</failOnWarning>` tells the Maven Compiler Plugin to translate the fail-on-warnings policy into `-Werror` in compiler arguments on supporting plugin versions.
- `<showWarnings>true</showWarnings>` keeps useful diagnostics visible in logs, instead of losing investigation evidence.
- `<compilerArgs>` selects compiler categories to enable; do not add `-Werror` again if `failOnWarning` is already selected.
- `<release>17</release>` aligns Java 17 source, target bytecode, and platform APIs, avoiding certain `-source/-target` configuration warnings when using a newer compiler.

Run verification:

~~~bash
mvn clean compile
mvn -X compile
~~~

`mvn -X` helps observe compiler flags and related JDKs, yet logs can be long; do not save secrets/personal configs from logs into reviews. If the project is multi-module, verify whether plugin configuration placed in parent `pluginManagement` was actually applied in each module. A plugin placed only in `pluginManagement` does not necessarily run without a corresponding plugin binding.

Maven has compile/testCompile lifecycles and multiple compiler executions; align policies for source/test sources as needed. A project using generated sources may need to adjust processor paths and plugin versions before turning on the gate.

## 10. Configuring Gradle JavaCompile

With Groovy DSL **`build.gradle`**:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += [
        '-Xlint:deprecation,removal,unchecked,rawtypes',
        '-Werror'
    ]
}
~~~

With Kotlin DSL **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.addAll(
        listOf("-Xlint:deprecation,removal,unchecked,rawtypes", "-Werror")
    )
}
~~~

These snippets are **Gradle configurations**, not Java sources. They apply to tasks of type `JavaCompile`, typically including `compileJava` and `compileTestJava`. If wanting incremental adoption, configure one specific task first, such as only `tasks.named('compileJava', JavaCompile) { ... }` in Groovy DSL; that is an **illustrative snippet** needing placement in a build script with the Java plugin.

Run:

~~~bash
./gradlew clean compileJava
./gradlew compileTestJava
~~~

On Windows, `gradlew.bat` can be used. Gradle Java toolchains, if configured, select the JDK for `JavaCompile`; `options.release` controls the target. Verify that all tasks receive the right arguments and compiler version.

**Practical point:** merely setting `options.warnings = true` (if supported by the Gradle version API) is not synonymous with enabling `-Werror`. Compiler arguments or an equivalent mechanism are needed to actually fail the build when warnings are emitted.

## 11. Annotation Processing, Generated Sources, and Warning Policy

In projects using JSR 269, Lombok, MapStruct, or code generators, warnings can come from multiple places:

- **Processor diagnostics** via `Messager.printMessage(Diagnostic.Kind.WARNING, ...)` can become a compile failure cause under `-Werror`.
- **Generated Java sources** are compiled by the compiler, and thus can produce lint warnings just like handwritten sources.
- **Processor path differs from compile classpath**: missing dependencies, processors running on an incompatible JDK, or processors reporting configuration warnings need to be handled in the build.
- **Sources generated from old generator versions**: warnings should not be resolved by manually editing files under `build/generated` or `target/generated-sources` because the next build will regenerate them.

Priority handling direction:
1. Determine whether the warning is emitted from handwritten source or from a generator/processor.
2. Upgrade or configure the processor/generator if it produces code that fails policy.
3. If the processor has an official suppression mechanism and its scope can be controlled, use it with justification; verify what warnings it still emits.
4. When needing to separate policies for generated sources, configure a separate compile task with clear paths and ownership; do not disable warnings for the entire application.
5. Test on a **clean** build because generated sources and the number of processing rounds may differ during incremental builds.

**Do not confuse `Note:` and `warning:` messages**. `Diagnostic.Kind.NOTE` is usually not equivalent to `Diagnostic.Kind.WARNING`. Decide failure based on the actual diagnostic emitted by the compiler.

## 12. Typical Mistakes When Enabling `-Werror`

### 12.1. Converting all warnings to errors immediately in a large codebase

Hundreds of legacy warnings block CI from merging; people start adding `@SuppressWarnings` recklessly. A better approach is cleaning up module by module, classifying risk, and applying the gate once a module is clean.

### 12.2. Disabling warnings with `-nowarn` while keeping `-Werror`

This can render the gate meaningless for disabled lint warnings; nor does it guarantee all non-lint warnings vanish. Do not equate "green build" with "no issues".

### 12.3. Looking only at exit code when stale artifacts exist

When the compiler fails, old `.class` files can still run. You must inspect the exit code, compiler output, and perform a clean build; `java` running after a compile failure does not prove the new compile succeeded.

### 12.4. Adding `-Werror` on only one machine

Compiler plugins or other IDEs do not use those flags, so CI and local produce divergent results. Configure it in the repository, use a wrapper/toolchain, and run the gate in CI.

### 12.5. Upgrading JDK without checking the warning set

A new compiler version can add lint categories and change diagnostic thresholds. Run a test build with the new JDK, read `javac --help-lint`, and then update policies/suppressions based on engineering judgment.

### 12.6. Using `@SuppressWarnings("all")` across an entire package/class

Although a compiler may understand some broad keys, this approach reduces the ability to catch new bugs and is not a reliable solution for every diagnostic. Suppress the exact key in the smallest scope, with a reason and periodic review.

### 12.7. Mixing javac warnings with warnings from other tools

`-Werror` belongs to `javac`. Warnings from Kotlin compilers, linters, formatters, tests, or quality plugins have their own flags and failure policies. If CI still passes after a linter error, adjust the linter task; if CI fails due to a `javac` warning, read the compiler diagnostic.

## 13. Sample Policy for Development Teams

A Java 17 project can agree on rules:

**Scope:** Java sources owned by the team, compiled with the pinned JDK toolchain; every clean module must have the same lint flags in local builds and CI.

**Default warnings:** enable `deprecation`, `removal`, `unchecked`, `rawtypes`; consider adding `serial`, `fallthrough`, `try`, `path`, `options`, `processing` after evaluating the codebase. Warnings belonging to compiler/toolchain must be routed to the build team.

**CI blocking:** clean modules use `-Werror`; changes causing a module's compile task to emit new warnings must not be merged. Existing warnings in unclean modules are tracked in a remediation table with owners and review cycles, while preventing new warnings from being ignored.

**Exceptions:** allow suppression only at the narrowest scope, documenting safety rationale or library constraints, requiring reviewer verification and tracking removal deadlines. Do not disable `unchecked` project-wide just because of one legacy adapter.

**Upgrades:** every upgrade of JDK, Maven Compiler Plugin, Gradle, or annotation processor must run a test job on the new compiler, compare warnings by category, and verify when the gate applies.

**Expected outcome:** if a developer introduces a new deprecated call into a warning-locked module, the build fails early with a specific location; that person fixes the API or proposes a small reviewable exception. When warnings arise from inconsistent compiler options like `-source/-target`, the team fixes the build configuration.

## 14. Checklist Before Making the Gate Mandatory

- [ ] `javac -version` and the actual toolchain on CI/local are identified.
- [ ] `--release`/encoding are configured consistently.
- [ ] Selected lint categories exist in the compiler's `javac --help-lint`.
- [ ] A clean build has tabulated warnings by category, module, and source owner.
- [ ] Source warnings have been distinguished from processor/generated code warnings.
- [ ] Modules enabling `-Werror` **have no unhandled warnings remaining**.
- [ ] Exceptions have a scope, rationale, and suppression removal process.
- [ ] Maven/Gradle actually pass `-Werror` and `-Xlint` into the compile tasks needing protection.
- [ ] CI fails when intentionally adding a test warning and passes after fixing.
- [ ] When upgrading the compiler JDK, a process exists to review new warning categories.

## 15. Self-Check

**Question 1.** Does `-Werror` automatically enable all `-Xlint` categories?  
**Answer:** No. It turns warnings **emitted by the compiler** into errors; select categories using `-Xlint` and related compiler options.

**Question 2.** When not using `-Xlint:deprecation`, the compiler prints `Note: ... uses or overrides a deprecated API`. Does this `Note` line alone necessarily make `-Werror` fail?  
**Answer:** No. Distinguish `Note` diagnostics from warnings; the experiment in section 3 shows the compiler still succeeds in this case.

**Question 3.** Does `-Xmaxwarns 20 -Werror` allow up to 20 warnings?  
**Answer:** No. `-Xmaxwarns` only limits the number of **displayed** warnings; `-Werror` still fails when any warning is emitted.

**Question 4.** Does `@SuppressWarnings("unchecked")` make a generic cast truly safe?  
**Answer:** No. It only turns off the diagnostic in the annotated scope; the programmer must prove the type boundary is safe by design and tests.

**Question 5.** Why does `-Xlint:all -Werror` easily fail after a JDK upgrade even when source code has not changed?  
**Answer:** A newer `javac` version may add lint categories or detect additional warnable situations.

**Question 6.** When a warning comes from `target/generated-sources`, should the generated file be edited by hand?  
**Answer:** No. Fix the generator, processor configuration, or manage the compile task/generator version; generated files will be overwritten.

**Question 7.** Why can `-source 17 -target 17 -Werror` on a newer compiler fail due to `[options]`?  
**Answer:** The compiler may warn about system modules not being selected for the target release. For applications needing Java 17, use `--release 17` to also bind platform APIs and reduce misconfiguration.

**Question 8.** If a module still has 60 legacy warnings, can you add `-Werror` while giving a "budget of 60"?  
**Answer:** `javac -Werror` has no budget mechanism. Clean up warnings, split scopes, or use an external baseline mechanism outside the compiler during the transition phase.

## 16. Official Documentation

- [Oracle javac Command — `-Werror`, `-Xlint`, `--help-lint`](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Maven Compiler Plugin — compile goal and `failOnWarning`](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Gradle CompileOptions — `compilerArgs`](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html)
- [Java `@SuppressWarnings` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html)

**Remember:** `-Werror` is a **blocking gate** for warnings already emitted by the compiler, while `-Xlint` decides which warning groups to check. For a gate to be genuinely useful, choose categories purposefully, keep the toolchain stable, handle old warnings with ownership, and use small, justified suppressions. Then CI helps catch new risks instead of merely producing red builds or warnings disabled wholesale.