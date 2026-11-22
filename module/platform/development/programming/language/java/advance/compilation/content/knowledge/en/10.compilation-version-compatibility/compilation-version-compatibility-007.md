# Enabling Preview When Compiling and Running on the Corresponding Java Version

Java often releases language, JVM, or API capabilities under **preview** status before deciding to make them permanent features. Preview is not synonymous with an incomplete "beta" Java release: the capability is specified and implemented for developers to try out, but **is not yet committed to remain unchanged in future Java releases**. To use preview properly, you must align **the compiling JDK**, **the source/release level**, **the compiler flags**, and **the runtime JDK/flags**.

This article belongs to the **Version Compatibility** group of Java Advance – compilation. The focus is on `javac` and `java` commands, version-mismatch scenarios, indicators of class files compiled with preview, and testing/migration strategies when preview features change or are standardized. The executable example uses **JDK 24** with the *module import declarations* feature in its **second preview state in Java 24**. This is a version-specific example: in Java 25, module import declarations were standardized; do not infer that it remains a preview feature in all newer JDKs.

## 1. What Is a Preview Feature?

A preview feature is a capability provided by Java SE to gather real-world feedback before locking it in long term. Possible states across releases:

1. **First preview:** the feature first appears under a specific JEP.
2. **Second/third/... preview:** continues to be evaluated; its name, syntax, or semantics may change.
3. **Final/permanent:** the feature is accepted as a stable part of that Java version.
4. **Removed:** the feature may be removed instead of becoming standard.

There are several preview categories to distinguish:

- **Preview language feature:** new syntax or language rules, such as a new `import` construct. `javac` must recognize source code using that feature.
- **Preview VM feature:** changes to the execution platform's capabilities according to the corresponding specification. A program depending on a preview VM feature has corresponding runtime requirements.
- **Preview API:** new classes/interfaces/methods in platform API namespaces marked as preview. Preview APIs may require flags at compile time or runtime even when the source syntax looks familiar.
- **Incubator API/module:** a mechanism for experimenting with APIs via incubator modules, which is **different** from preview. Flags such as `--add-modules` may be involved; do not assume `--enable-preview` is how every incubator module is enabled.

Similarly, **experimental VM options**, **early-access JDKs**, **internal JDK APIs**, or *foreign function/native access* features have their own rules and should not automatically be called preview language features. Always check the documentation/JEP for **the exact version** and **the exact feature**.

**Key takeaway:** "Available in a newer JDK" does not mean "finalized"; "was preview in Java 24" also does not mean "requires enabling preview in Java 25". The status belongs to **the feature in a specific release**.

## 2. The Most Important Rule: Compiler and Runtime Must Share the Same Preview Release

Suppose the version used for testing is **Java N**. When compiling source code that uses Java N preview features, use **`javac` from JDK N itself** and enable:

~~~sh
javac --enable-preview --release N MyProgram.java
~~~

Where `N` is the actual version number, such as `24` in this article; the line above only illustrates the syntax and **is not a command to run verbatim**. You can also use `-source N` with `--enable-preview`, though `--release N` is usually more useful because it also restricts platform APIs to the selected release.

When running bytecode that depends on Java N preview features:

~~~sh
java --enable-preview MyProgram
~~~

`java` here must be **a runtime supporting Java N preview**, typically the JDK/JRE of **Java N itself**. The `--enable-preview` flag does not turn a JVM of another generation into a Java N JVM and does not bring back changed syntax/APIs.

| Component | What to check |
|---|---|
| `javac` | `javac -version` actually reports version **N** |
| Language level | `--release N` or `-source N` together with `--enable-preview` |
| Source code | The feature is used according to the preview version of **N** |
| Class files | Bytecode carries the version corresponding to **N**; classes actually using preview language/VM features have the preview marker |
| `java` | `java -version` matches version **N** and `--enable-preview` is passed |
| Libraries | Binaries/APIs and classpath/module path are compatible with the chosen runtime |

Do not use a newer `javac` to "compile an older version's preview" by simply passing `--release <older version>`. For example, on JDK 24, `javac --enable-preview --release 17 ...` **is rejected**, even though Java 17 had its own preview features. The JDK 24 compiler only supports **Java 24's own preview features** when that option is enabled.

### 2.1. Differences between --release and --source

- `--source 24`: selects the language rules of release 24 within the context supported by the compiler, but does not automatically restrict the platform APIs the compiler is using the way `--release` does.
- `--release 24`: selects the language **and** Java SE APIs matching release 24, which helps avoid accidentally using APIs newer than the targeted version.
- `--enable-preview`: enables preview usage for **the current release of javac**, working in combination with `--source` or `--release`.

The `--release` flag does not enable preview on its own. The command `javac --release 24` still rejects Java 24 preview syntax without `--enable-preview`.

For projects that do **not** need preview features, you normally **should not enable preview out of habit**. It complicates the build configuration and makes it easy to accidentally introduce preview features into a codebase branch that requires stability.

## 3. Java 24 Example: Module Import Declarations (Second Preview)

In Java 24, the declaration:

~~~java
import module java.base;
~~~

is a **preview language feature** under JEP 494. It allows importing types belonging to packages exported by the corresponding module, making source code shorter in certain contexts. It does **not** mean your program must declare a separate `module-info.java`; the example below is a regular class in the unnamed module.

The status by release should be clearly noted:

| Version | Status of module import declarations |
|---|---|
| Java 23 | First preview (JEP 476) |
| Java 24 | Second preview (JEP 494) |
| Java 25 | Final/permanent (JEP 511) |

Within the scope of this article we deliberately use **JDK 24**, because in that release both preview flags are required to compile and run the sample program. If you are learning with JDK 25 or later, consult the documentation for that exact JDK: **do not use Java 24's preview status to guess required syntax/flags in Java 25**.

### 3.1. Create PreviewExample.java

Create an empty directory dedicated to this exercise. Inside that directory, create **`PreviewExample.java`** with the full contents:

~~~java
import module java.base;

public class PreviewExample {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai");
        System.out.println(names.get(0));
        System.out.println(names.size());
    }
}
~~~

Because `java.base` exports `java.util`, the compiler recognizes `List` without an explicit `import java.util.List;`. `List.of` is an API already stabilized in earlier Java versions; **the preview part of the example is only the `import module` syntax**.

The filename must match the public class `PreviewExample`; there is no `package`, so operations can be executed directly from the directory containing the source.

### 3.2. Check the tools

From the terminal:

~~~sh
javac -version
java -version
~~~

In the environment used for verification, both commands report JDK/JVM 24.0.2. If either command reports Java 17, 21, 25, or another version, **do not run the exact example expecting the same result**; select JDK 24 or adjust the example/flags to match the preview status of the release you have.

For real projects, `JAVA_HOME`, `PATH`, the IDE Project SDK, and the Java toolchain in Gradle/Maven can select different JDKs. `JAVA_HOME` is merely an environment/tooling convention; setting it does not guarantee the shell is using the expected compiler. You must check both `javac -version` and `java -version`.

### 3.3. Compiling without preview enabled: expected error

Using `javac` from JDK 24, try:

~~~sh
javac --release 24 -encoding UTF-8 PreviewExample.java
~~~

The command **fails**. Key diagnostic content:

~~~text
error: module imports are a preview feature and are disabled by default.
~~~

The compiler recognizes that the `import module` construct belongs to Java 24 preview but does not allow using it by default. This is not an error that `List` does not exist, nor a classpath error; **preview must be enabled at compile time**.

### 3.4. Compiling properly for JDK 24

Run:

~~~sh
javac --enable-preview --release 24 -encoding UTF-8 PreviewExample.java
~~~

The command **succeeds**, producing `PreviewExample.class`. With javac 24.0.2, there is also a note such as:

~~~text
Note: PreviewExample.java uses preview features of Java SE 24.
Note: Recompile with -Xlint:preview for details.
~~~

This is a **note**, not a sign of compilation failure. You can add `-Xlint:preview` to see more detailed warnings:

~~~sh
javac -Xlint:preview --enable-preview --release 24 -encoding UTF-8 PreviewExample.java
~~~

When verified with JDK 24, the compiler emits a warning related to the module import preview. With certain compiler/JDK configurations, the note/warning text may vary; the key factor is **exit code 0** along with the generated class file.

Another syntax also accepted by JDK 24 for this example is:

~~~sh
javac --enable-preview -source 24 -encoding UTF-8 PreviewExample.java
~~~

However, for workflows requiring management of **both language and API compatibility**, `--release 24` should be preferred.

### 3.5. Running without the preview flag: expected error

After compiling successfully with preview, try:

~~~sh
java -cp . PreviewExample
~~~

The command **fails to run** on JDK 24. The JVM rejects the class file using preview, with key output:

~~~text
java.lang.UnsupportedClassVersionError: Preview features are not enabled
~~~

This is a **runtime** error, distinct from the compiler error in section 3.3. The preview flag used in the `javac` command already finished its job for compilation; it **does not automatically propagate** to the subsequent `java` command.

### 3.6. Running properly on Java 24

Use the Java 24 runtime:

~~~sh
java --enable-preview -cp . PreviewExample
~~~

**Verified exact stdout**:

~~~text
Lan
2
~~~

At this point, everything needed is aligned:

1. Compiler JDK 24.
2. `--enable-preview --release 24` for `javac`.
3. Bytecode containing Java 24 preview.
4. JVM 24 with `--enable-preview` at runtime.

If the build tool creates a JAR, do not assume the preview flag lives permanently in the JAR manifest; it is the configuration of **the JVM process being launched** that determines whether preview is enabled.

## 4. Preview Class Files: Major Version and Minor Version

Under Java's modern class file model, each `.class` has a **major** and **minor version** in its header. A class file **that actually depends on a Java 24 preview language/VM feature** can be identified by:

~~~text
minor version: 65535
major version: 68
~~~

The major version **68** corresponds to Java 24, while the minor version **65535** is used to mark a class file that depends on a preview language/VM feature according to the specification mechanism. The JVM will not treat it as an ordinary stable Java 24 class.

Inspect:

~~~sh
javap -verbose PreviewExample.class
~~~

In the output, look for `minor version:` and `major version:`. For `PreviewExample.java` using the module import preview in section 3, those two values **have been verified in practice**.

### 4.1. Enabling --enable-preview does not mean every class carries minor 65535

Suppose **`StableExample.java`** has the contents:

~~~java
public class StableExample {
    public static void main(String[] args) {
        System.out.println("stable");
    }
}
~~~

Compile on JDK 24 with:

~~~sh
javac --enable-preview --release 24 StableExample.java
javap -verbose StableExample.class
~~~

Verified result:

~~~text
minor version: 0
major version: 68
~~~

Running **without** `--enable-preview` still succeeds:

~~~sh
java StableExample
~~~

Stdout:

~~~text
stable
~~~

**Explanation:** the compiler was allowed to use preview during the build, but `StableExample` itself does not use any preview language/VM feature that requires the class file marker. Therefore, you cannot look at the build flags and assert that **every class** in the artifact requires the preview flag when the JVM runs. You need to evaluate the **actual bytecode** and the APIs/features invoked.

Conversely, if a class has the Java 24 preview marker, running on a Java 24 JVM without the flag will fail. A JVM of a different release does not necessarily support this preview class file, even if that JVM accepts a flag of the same name.

### 4.2. Why cannot preview class files be treated as portable like regular classes?

A preview feature may change language/VM rules in the next release. Preview class files are tied to **the release that produced them**. The `--enable-preview` flag of a newer runtime **should not be understood** as a promise to support preview class files from all older Java versions.

Therefore, when upgrading the JDK, **you must recompile from source** and test on the new release. If the feature has become final, you can remove the preview flag after confirming the source/APIs are supported in the target release. If the feature is still in preview but its syntax changed, update the source according to the new JEP and recompile.

Do not remove the class file marker or manually edit major/minor versions to "bypass" the JVM check; that is not a safe conversion method and does not guarantee compatible bytecode semantics.

## 5. Cases Where --enable-preview Is Used with the Wrong Version

A common mistake is installing JDK 24 and trying to test a preview that existed in Java 17 using the command:

~~~sh
javac --enable-preview --release 17 SomeSource.java
~~~

On **javac 24**, the command is rejected **before** inspecting what preview features the source uses, with the key message:

~~~text
error: invalid source release 17 with --enable-preview
(preview language features are only supported for release 24)
~~~

That does not mean Java 17 "had no preview features". It simply means **the JDK 24 compiler does not provide Java 17's preview mode**. If you want to reproduce a preview feature according to Java 17's design, select **JDK 17** to compile and run with the appropriate flags, and consult the JEP from that time.

Similarly, on javac 24:

~~~sh
javac --enable-preview --source 23 SomeSource.java
~~~

is also not a way to use Java 23's preview features. `--source` can select the stable language of an earlier release, whereas `--enable-preview` applies the preview features of **javac's current release**, not historical previews.

### 5.1. Valid/invalid configuration examples with JDK 24

| Command or combination | For PreviewExample.java in Java 24 |
|---|---|
| `javac --release 24 PreviewExample.java` | Invalid: preview is disabled |
| `javac --enable-preview --release 24 PreviewExample.java` | Valid: produces a preview class |
| `javac --enable-preview -source 24 PreviewExample.java` | Valid for JDK 24's source level/preview |
| `javac --enable-preview --release 17 PreviewExample.java` | Invalid: javac 24 only allows preview for release 24 |
| `java PreviewExample` | Invalid: Java 24 preview class is rejected by JVM 24 when not enabled |
| `java --enable-preview PreviewExample` | Valid with Java 24 runtime, given an appropriate classpath environment |

This table **is not** a guide for JDK 25 or 26. Version numbers are part of the experimental contract and must change along with the feature status per release.

## 6. Distinguishing the Runtime Version from the Compilation Target

In a project that must run Java 17 in production while developers use JDK 24, you can write **stable** Java 17 code and compile:

~~~sh
javac --release 17 -encoding UTF-8 StableExample.java
~~~

Using the JDK 24 compiler while targeting Java 17 class files/APIs is supported. Such a stable program can be deployed on Java 17 when dependencies are also compatible and the runtime environment meets the requirements.

**That reasoning cannot be applied directly to preview features.** Preview is not an immutable set of capabilities across releases. To use Java 24 preview features, you must target Java 24; you cannot simultaneously require Java 24 preview features and target a Java 17 runtime with `--release 17`.

Three cases need to be distinguished:

1. **Stable and backwards-targeted:** a newer JDK can compile code for an older Java version using the corresponding `--release`.
2. **Preview of the current release:** the compiler and runtime are chosen to match the release that contains the preview; both phases enable the flag.
3. **Preview finalized in a newer release:** you can upgrade the source/build to use the finalized state and drop the preview flag, but you must check API/syntax changes and recompile.

For example, module import declarations were **finalized in Java 25**. This is why this article does not state "every Java version using `import module` must always enable preview"; that requirement is accurate for **the Java 24 exercise**, not an immutable rule.

## 7. How Do Preview APIs Differ from Preview Syntax?

From a learner's perspective, a source file can **contain no unfamiliar syntax** yet still call an API marked by Java as preview. Conceptual illustration:

~~~java
// Pseudocode for some preview API: not a standalone runnable program.
// somePreviewApi.operation();
~~~

In this case, you need to check the documentation of that API itself in **the JDK being used**. Depending on the API's characteristics and how it is declared, using it may trigger diagnostics/warnings from `javac` if preview is not enabled; execution also has corresponding preview restrictions.

Do not infer whether flags are needed solely by looking at whether the source has new keywords. Conversely, **an experimental API that is not preview** may have its own module-enabling rules or flags. Always read the JEP, javadoc, and option descriptions corresponding to the release.

Practical guidelines:

- Distinguish between **preview language/VM feature**, **preview API**, **incubator module**, and **experimental runtime option**.
- Document the JEP name and release in which the API/syntax is in preview.
- Test the compiler with the exact flags and inspect diagnostics; test the actual runtime with the same release.
- For public libraries, consider carefully before exposing preview types in public APIs because doing so can force downstream consumers to use the same release/flags.

## 8. Compatibility with Build Tools

In real projects, the commands you type manually are only part of the picture. The IDE, Gradle, Maven, or CI may run **a different compiler JDK** from your terminal, or a test JVM different from the application JVM. Because preview requires both sides, configure and verify them **separately**.

### 8.1. Gradle: compiler and test/run process are two separate configurations

An **illustrative** Groovy DSL configuration using Java toolchain 24:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['--enable-preview']
    options.release = 24
}

tasks.withType(Test).configureEach {
    jvmArgs += ['--enable-preview']
}

tasks.withType(JavaExec).configureEach {
    jvmArgs += ['--enable-preview']
}
~~~

This illustrates the preview configuration portion; to run the `application`, you still need to configure the main class/source sets/dependencies appropriately. The Gradle version must support JDK 24/toolchains; not every older Gradle version can run with a newer JDK. Do not treat this snippet as a complete Gradle project.

Why are three parts needed?

- `JavaCompile` runs `javac`, which needs preview enabled when processing sources.
- `Test` runs a separate test JVM, which needs preview enabled if tests load preview classes.
- `JavaExec` runs the program in a separate JVM, so it also needs the flag when using preview.

When packaging and deploying via another JVM mechanism, such as `java -jar` outside Gradle, ensure that launch command also includes `--enable-preview`.

### 8.2. Maven: release property and plugin/compiler args

Directional example in `pom.xml` (this is a **configuration snippet**, not a self-contained runnable POM):

~~~xml
<properties>
    <maven.compiler.release>24</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <compilerArgs>
                    <arg>--enable-preview</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

For tests, the Surefire/Failsafe plugins launch a JVM and need the appropriate **argLine**/JVM args configuration, such as `--enable-preview` when tests need to load preview classes. Details of how plugins inherit args, how the Java toolchain is selected, and supported versions depend on the Maven/plugin versions; check the documentation and actual executed commands.

Do not just add `--enable-preview` to compilerArgs and declare that all tests/builds/runtimes have it enabled. In CI, check both `mvn -version` and the JVM commands for testing/packaging.

### 8.3. IDE and CI

In the IDE, verify simultaneously:

1. Project/module SDK is the JDK of the target preview release.
2. Language level has the corresponding preview enabled.
3. Compiler options include `--enable-preview` when IDE configuration does not add the right flag automatically.
4. Run/Debug configuration has the JVM argument `--enable-preview`.
5. The test runner and integrated terminal are not accidentally running a different JDK.
6. CI uses the same JDK release and source/dependency/configuration, not just the same branch name.

Across IntelliJ IDEA, Eclipse, or VS Code, exact UI setting locations vary by version; the principle is that **compiler level** and **runtime arguments** must stay in sync. Do not try to fix preview errors by blindly adding a JAR or opening module access; those belong to different mechanisms.

## 9. Preview Features in Dependencies and Published Artifacts

Preview features can appear not only in the application module but also inside a **dependency library JAR**. When compiling an application against a library containing preview class files, you may encounter compiler diagnostics or release compatibility issues; at runtime, the JVM must still handle preview-dependent class files according to that release's rules.

Several consequences:

- **Public libraries** using preview features can restrict the set of JDKs that downstream clients are allowed to use.
- Publishing a JAR containing Java 24 preview class files does not make it a JAR that can run freely on a Java 25 JVM; check version rules, especially the `65535` minor marker.
- If preview is only used for experimentation, keep experimental artifacts separate rather than mixing them into published stable releases.
- Mark the release/JDK and build instructions in the artifact documentation so others do not have to guess.
- Bytecode analysis, coverage, instrumentation, or shading/packaging tools must understand the class file version in use; older plugins may fail even before running the application.

Do not rely on "the developer's machine has JDK 24" to conclude that production/CI environments can read that bytecode. Check **the JDK actually running** and the actual packaged artifact.

## 10. Common Errors and Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `... is a preview feature and is disabled by default` | Source uses preview, but compiler has not enabled it | Select the matching JDK release and add `--enable-preview --release N` |
| `invalid source release X with --enable-preview` | Compiler JDK does not support preview for release X | Use `javac` from the exact release you want to test, or drop preview if using stable language features |
| `UnsupportedClassVersionError: Preview features are not enabled` | Runtime encountered a preview class file, but JVM has not enabled preview | Run with the corresponding release's JVM and add `--enable-preview` |
| `UnsupportedClassVersionError` with a newer major version | Runtime is too old to read the class file | Check `javac -version`, `java -version`, target `--release`, and dependencies |
| Java N preview syntax fails to compile in Java N+1 | Feature changed syntax, was finalized, or was removed | Read the new release's JEP/docs, update code, and recompile |
| Runs from IDE, but JAR in terminal fails | Run configuration has the JVM flag, terminal is missing it | Compare JVM args across each execution path |
| Tests pass locally, but fail in CI | Toolchain, plugin, or runner picked a different JDK | Lock the release/toolchain, inspect logs, and run tests with the same JVM flags |
| Error in a dependency JAR containing preview | Artifact has a mismatched version or incompatible compiler/runtime | Confirm the dependency supports the target release, upgrade/recompile the library if needed |
| `--release 17` does not accept Java 24 preview syntax | Target release is lower than the desired preview | Re-evaluate runtime requirements; you cannot ship Java 24 preview to a Java 17 runtime with a flag |
| Preview flag enabled, yet JVM reports another error | Error may stem from classpath, module access, binary mismatch, or logic | Read the detailed stack trace; do not blame every error on preview |

### 10.1. Quick inspection procedure

~~~sh
javac -version
java -version
javac --help
java --help
~~~

For a specific class file:

~~~sh
javap -verbose PreviewExample.class
~~~

Read `major version` and `minor version`; distinguish stable bytecode from bytecode using preview. For class files not found, check the classpath/module path and file location first; there is no need to add a preview flag if the problem is merely a missing path.

In build tools, inspect the actual compiler/test JVM invocation rather than reading only part of the configuration. Do not treat `javac -version` output from a terminal as proof of the toolchain across the entire IDE/CI.

## 11. Managing the Preview Lifecycle Across JDK Upgrades

A disciplined approach to using preview features:

1. **Identify the JEP/release.** Record which Java version the feature is in preview for, and link the appropriate documentation.
2. **Use only where justified.** Learning, experimentation, syntax/API evaluation, or prototyping; do not introduce them into every library by default.
3. **Lock the environment.** Select the exact JDK N via controlled toolchains, containers, or CI images; avoid relying on whatever JDK is on PATH.
4. **Enable on both sides.** Compile with `--enable-preview --release N`, and run/test with JVM N and `--enable-preview` when preview classes/features are present.
5. **Add negative/control tests.** Verify that a build without the flag fails as expected on preview source, and the properly configured build runs with expected stdout.
6. **Inspect the artifact.** Check the class file version, packaged JAR, and actual runtime.
7. **Track subsequent releases.** When a feature is re-previewed, finalized, or removed, read the new JEP before upgrading.
8. **Recompile and test.** Do not carry raw preview bytecode onto a new JVM and just add the flag hoping it will run.
9. **Remove redundant flags.** Once code moves to a stable version and uses no other preview APIs/VM features, remove `--enable-preview` from compile and run.
10. **Do not break the version contract.** If the product commits to running on Java 17, do not introduce Java 24 preview into the main execution path.

### 11.1. When a feature becomes final

After a preview feature is finalized, its syntax may remain similar or may have changed across preview iterations. Do not simply remove the flag and assume all APIs and behaviors remain compatible. The proper process is:

- Read the specification/JEP **of the final release**.
- Verify source compatibility with the final syntax and APIs.
- Compile **without** enabling preview for the target release.
- Run unit/integration tests using the exact production JVM.
- Check whether there are other preview dependencies in the same source/dependencies.
- Finalize the release and runtime support information in project documentation.

For module import declarations, Java 24 is the second preview and Java 25 is final. Therefore, **the example using Java 24 is kept fixed** in this article to clearly illustrate the need to enable preview in both phases; to learn the finalized syntax, consult Java 25 or later documentation.

## 12. Practice Exercises with Guided Solutions

**Exercise 1 — Distinguish two errors.** Using JDK 24, compile `PreviewExample.java` without `--enable-preview`, then compile it properly and run without `--enable-preview`. In the first case the error comes from **javac**, and in the second case from the **JVM**. Why do both require independent flags?

**Exercise 2 — Inspecting class files.** Use `javap -verbose` to compare `PreviewExample.class` and `StableExample.class`, both compiled with `--enable-preview --release 24`. Both have major 68; the minor version of the class using preview is 65535, while the sample stable class is 0. Why does the stable class run without preview enabled?

**Exercise 3 — Wrong source level.** On javac 24, try `--enable-preview --release 17`. Explain why javac rejects it even before inspecting the source syntax. If you want to test Java 17 preview features, which JDK should you choose?

**Exercise 4 — Moving to the final release.** Research module import declarations in Java 24 and Java 25. State the status in each version. Why should you not continue describing that feature as "preview in every new Java version"?

**Exercise 5 — IDE differs from terminal.** The project runs from the IDE, but `java -cp . PreviewExample` in the terminal fails. Check the running JDK, launcher flags, classpath/module path, and bytecode location before modifying source code.

**Exercise 6 — Build tool.** In Gradle/Maven, the compiler has preview enabled, but the test JVM does not. Identify where JVM arguments need to be configured; verify whether the test runner uses the right JDK release.

**Exercise 7 — Deployment strategy.** Production only supports Java 17, while an experimental team wants to use Java 24 preview features. How would you separate modules/branches/test artifacts, toolchains, CI, and the release pipeline so Java 24 preview class files are not shipped into the system running Java 17?

## 13. Checklist Before Using Preview Features in a Java Project

- **Right feature:** confirmed whether the feature is preview, incubator, or final in the specific release.
- **Right compiler:** `javac -version` matches the release containing the desired preview.
- **Right target:** `--enable-preview --release N` (or `-source N` when genuinely appropriate).
- **Right runtime:** JVM **N** and `--enable-preview` when running preview classes/features.
- **Right bytecode:** inspect `major/minor version`; do not manually edit class files to bypass the check.
- **Right dependencies:** do not accidentally pull in preview libraries from another release.
- **Right tooling:** IDE/Gradle/Maven/CI/test runner pass flags to the right processes.
- **Right lifecycle:** have an update plan for when the preview changes or becomes final.
- **Right scope:** experiments are isolated; do not publish preview artifacts if the product requires a stable/older runtime.
- **Right verification:** test both the missing-flag case (expected failure) and the full-flag case (successful execution).

**Conclusion:** preview is not a mode where "enabling it lets you use every future or past Java feature". It is a contract **tightly bound to a specific JDK/release**. For classes that actually use Java N preview features, compile targeting Java N with preview enabled and run on a correspondingly configured Java N runtime. When upgrading releases, review feature status, recompile from source, and test the entire execution path.

## 14. Official References

- Oracle, *Preview Language and VM Features* — Java SE 24: https://docs.oracle.com/en/java/javase/24/language/preview-language-and-vm-features.html
- Oracle, *Module Import Declarations* — Java SE 24: https://docs.oracle.com/en/java/javase/24/language/module-import-declarations.html
- Oracle, *Java Language Changes by Release* — Java SE 25: https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html
- Oracle, *The javac Command* — Java SE 24: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Oracle, *The java Command* — Java SE 24: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- OpenJDK, *JEP 12: Preview Features*: https://openjdk.org/jeps/12
- OpenJDK, *JEP 494: Module Import Declarations (Second Preview)*: https://openjdk.org/jeps/494
- OpenJDK, *JEP 511: Module Import Declarations*: https://openjdk.org/jeps/511

When online content broadly states "the latest Java supports preview X", identify **which release it refers to**. A feature name may stay the same across multiple JEPs, while its exact status and usage differ by release.